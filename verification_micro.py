import os
import json
import logging
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

from micro_model import (
    build_prompt,                                     # формирование промпта для генерации микро‑модели
    call_openrouter,                                  # отправка запроса в OpenRouter
    parse_micro_model as parse_json,                  # извлечение JSON из ответа LLM
    OPENROUTER_MODEL as DEFAULT_GENERATION_MODEL,
)
from prompts import PROMPT_JUDGE_VARIANTS_MICROMODEL, PROMPT_RAG_CONFIDENCE_MICROMODEL

load_dotenv()                                  # загрузка переменных окружения из .env файла

# ---------------------------------------------------------------------------
# Логирование: уровень INFO, вывод временных меток и сообщений
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация модели-судьи (обязательна в .env)
# ---------------------------------------------------------------------------
DEFAULT_JUDGE_MODEL = os.getenv("DEFAULT_JUDGE_MODEL_MICRO")
if not DEFAULT_JUDGE_MODEL:
    raise RuntimeError("Переменная окружения DEFAULT_JUDGE_MODEL_MICRO не установлена")

# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def validate_micro_structure(micro: dict) -> bool:
    """Проверяет обязательные поля и их типы."""
    required = ["sitm", "sbjm", "STHM", "pfmt", "metm"]
    for key in required:
        if key not in micro:
            return False
    if not isinstance(micro["sitm"], list) or not isinstance(micro["sbjm"], list):
        return False
    if micro["pfmt"] is not None or micro["metm"] is not None:
        return False
    if micro["STHM"] is not None and not isinstance(micro["STHM"], list):
        return False
    return True

# ---------------------------------------------------------------------------
# RAG‑верификация
# ---------------------------------------------------------------------------
def get_retriever():
    """Пытается импортировать и инициализировать retriever из модуля retrieval.
    Возвращает объект retriever'а или None."""
    try:
        from retrieval import get_retriever as _get_retriever
        return _get_retriever()
    except ImportError:
        logger.info("Модуль retrieval не найден, RAG недоступен.")
        return None

def rag_confidence(macro_model: dict, micro_model: dict, top_k: int = 3) -> Tuple[float, str]:
    """
    Оценивает, насколько микро‑модель соответствует методическим документам.
    Возвращает кортеж:
      - оценка соответствия (0.0 – 1.0)
      - текстовое пояснение
    """
    retriever = get_retriever()
    if retriever is None:
        return 1.0, "RAG недоступен"

    # Формируем поисковый запрос из ключевых полей макро‑модели
    query = f"Проблема: {macro_model.get('sit', '')}\nСубъект: {macro_model.get('sbj', '')}\nОценка: {macro_model.get('est', '')}"

    # Извлекаем top_k наиболее релевантных фрагментов
    docs = retriever.retrieve(query, top_k)
    if not docs:
        return 0.5, "Нет релевантных документов"

    # Объединяем документы в один текстовый блок
    documents_text = "\n\n".join(docs)

    # Сериализуем микро‑модель для подстановки в промпт
    micro_json_str = json.dumps(micro_model, ensure_ascii=False, indent=2)

    # Подставляем в шаблон промпта для RAG‑оценки
    prompt = PROMPT_RAG_CONFIDENCE_MICROMODEL.format(
        documents_text=documents_text,
        micro_model_json=micro_json_str
    )

    # Отправляем запрос модели-судье
    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL)
    result = parse_json(raw) # Парсим JSON‑ответ

    # Извлекаем score и reason; используем значения по умолчанию, если отсутствуют
    score = result.get("score", 0.5)
    reason = result.get("reason", "")
    return score, reason

# ---------------------------------------------------------------------------
# Судья: синтез лучшей микро‑модели из вариантов
# ---------------------------------------------------------------------------
def judge_variants(
        macro_model: dict,
        variants: List[dict]                # список вариантов микро‑моделей
    ) -> Tuple[dict, float, str]:

    """
    Отправляет все варианты модели‑судье, которая создаёт итоговую
    микро‑модель, объединяя лучшие стороны каждого варианта.
    Возвращает:
      - итоговый словарь микро‑модели
      - уверенность судьи (0.0 – 1.0)
      - текстовое обоснование
    """

    # Сериализуем макро‑модель
    macro_json_str = json.dumps(macro_model, ensure_ascii=False, indent=2)

    # Формируем текстовое представление всех вариантов
    variants_text = ""
    for i, var in enumerate(variants):
        variants_text += f"Вариант {i+1}:\n{json.dumps(var, ensure_ascii=False, indent=2)}\n\n"

    # Заполняем шаблон промпта для судьи
    prompt = PROMPT_JUDGE_VARIANTS_MICROMODEL.format(
        macro_model_json=macro_json_str,
        variants_text=variants_text
    )

    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL) # Отправляем запрос модели-судье
    result = parse_json(raw)                                 # Парсим JSON‑ответ

    # Извлекаем поля; fallback – первый вариант и низкая уверенность
    final_micro = result.get("final_micro", variants[0])
    confidence = result.get("confidence", 0.5)
    reasoning = result.get("reasoning", "")
    return final_micro, confidence, reasoning

# ===================================================================
# ОСНОВНОЙ МЕТОД ВЕРИФИКАЦИИ (модифицированный)
# ===================================================================
def verify_micro_model(
    macro_model: dict,
    initial_micro: dict,
    generation_prompt: str = None,
    generation_model: str = DEFAULT_GENERATION_MODEL,
    use_rag: bool = True,
    num_samples: int = 5,
    temperature: float = 0.7,
    confidence_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Верификация микро‑модели методом множественной генерации + LLM‑судья + RAG.
    При недостатке валидных вариантов запускает дополнительные итерации
    с постепенным повышением температуры до 1.2 и увеличенным числом генераций.

    Возвращает словарь с полями:
        final_micro, confidence, acceptable,
        judge_confidence, rag_confidence, reasoning.
    """
    if generation_prompt is None:
        generation_prompt = build_prompt(macro_model)

    # Начальный список вариантов: уже имеющаяся initial_micro
    variants = [initial_micro]

    # Переменные для управления повторными попытками
    current_temperature = temperature      # температура для текущей итерации
    current_num_samples_to_gen = num_samples - 1  # сколько вариантов нужно сгенерировать (помимо исходного)
    max_temperature = 1.2                  # предел повышения температуры
    attempt = 0                            # счётчик попыток (для логирования)

    # Цикл генерации дополнительных вариантов
    while len(variants) < 2 and current_temperature <= max_temperature:
        attempt += 1
        logger.info(
            f"Попытка #{attempt}: генерация {current_num_samples_to_gen} вариантов "
            f"с температурой {current_temperature}"
        )

        # Генерируем заданное количество вариантов
        for i in range(current_num_samples_to_gen):
            raw = call_openrouter(
                generation_prompt,
                model=generation_model,
                temperature=current_temperature
            )
            micro = parse_json(raw)
            if micro and validate_micro_structure(micro):
                variants.append(micro)
            else:
                logger.warning(
                    f"Вариант {i+1} из попытки #{attempt} не прошёл структурную валидацию, пропущен."
                )

        # Если всё ещё недостаточно вариантов, готовим параметры для следующей итерации
        if len(variants) < 2:
            current_temperature += 0.1                       # увеличиваем температуру
            # Увеличиваем число генерируемых вариантов: минимум 3, либо на 1 больше предыдущего
            current_num_samples_to_gen = max(3, current_num_samples_to_gen + 1)
            logger.info(
                f"Недостаточно валидных вариантов (текущее количество: {len(variants)}). "
                f"Повышаем температуру до {current_temperature}, "
                f"увеличиваем число дополнительных генераций до {current_num_samples_to_gen}."
            )

    # Если после всех попыток валидных вариантов меньше двух, выбрасываем ошибку
    if len(variants) < 2:
        raise RuntimeError(
            f"Ошибка синтеза: недостаточно валидных вариантов\n"
            f"  Получено: {len(variants)}\n"
            f"  Попыток: {attempt}\n"
            f"  Макс. температура: {max_temperature}\n"
            f"Рекомендация: заменить модель БЯМ для сэмплирования"
        )

    logger.info(f"Накоплено {len(variants)} валидных вариантов. Запуск судьи...")

    # Синтез итоговой модели судьёй
    final_micro, judge_conf, reasoning = judge_variants(macro_model, variants)

    # Структурная валидация итога
    if not validate_micro_structure(final_micro):
        logger.warning("Итоговая модель имеет структурные нарушения, уверенность снижена.")
        judge_conf *= 0.8
        reasoning += "\nВнимание: модель имеет структурные нарушения."

    # RAG‑верификация (опционально)
    rag_conf = None
    if use_rag:
        rag_conf, rag_reason = rag_confidence(macro_model, final_micro)
        reasoning += f"\nRAG‑оценка: {rag_reason}"

    # Комбинированная уверенность
    overall_conf = (0.5 * judge_conf + 0.5 * rag_conf) if rag_conf is not None else judge_conf
    acceptable = overall_conf >= confidence_threshold

    return {
        "final_micro": final_micro,
        "confidence": overall_conf,
        "acceptable": acceptable,
        "judge_confidence": judge_conf,
        "rag_confidence": rag_conf,
        "reasoning": reasoning
    }