import os
import json
import logging
from typing import Dict, Any, List, Tuple, Callable, Optional
from dotenv import load_dotenv

from micro_model import (
    build_prompt as build_micro_prompt,        # формирование промпта для генерации микро‑модели
    parse_micro_model as parse_json
)
from call_llm import call_openrouter
from prompts import (
    PROMPT_JUDGE_VARIANTS_MICROMODEL,
    PROMPT_RAG_CONFIDENCE,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_GENERATION_MODEL = os.getenv("DEFAULT_GENERATION_MODEL")

# Модель-судья из .env
DEFAULT_JUDGE_MODEL = os.getenv("DEFAULT_JUDGE_MODEL")
if not DEFAULT_JUDGE_MODEL:
    raise RuntimeError("Переменная окружения DEFAULT_JUDGE_MODEL не установлена")

# ---------------------------------------------------------------------------
# Вспомогательные функции (не зависят от типа модели)
# ---------------------------------------------------------------------------

def validate_micro_structure(micro: dict) -> bool:

    """Проверяет обязательные поля и их типы для микро‑модели."""

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

""" в разработке
def validate_macro_structure(macro: dict) -> bool:
    required = {"id", "sit", "sbj", "est"}
    return all(k in macro for k in required)
"""

def get_retriever():

    """Возвращает объект retriever'а или None."""

    try:
        from retrieval import get_retriever as _get_retriever
        return _get_retriever()
    except ImportError:
        logger.info("Модуль retrieval не найден, RAG недоступен.")
        return None

def rag_confidence(
    macro_context: dict,          # контекст (макро‑модель) для формирования запроса
    model: dict,                  # проверяемая модель (микро или макро)
    top_k: int = 3,
    rag_prompt_template: str = PROMPT_RAG_CONFIDENCE
) -> Tuple[float, str]:

    """
    Оценивает соответствие модели документам из базы знаний.
    - macro_context – словарь, который содержит информацию для поиска
    (обычно поля 'sit', 'sbj', 'est').
    - model – сериализуемая модель (микро или макро).
    """

    retriever = get_retriever()
    if retriever is None:
        return 1.0, "RAG недоступен"

    query = f"Проблема: {macro_context.get('sit', '')}\nСубъект: {macro_context.get('sbj', '')}\nОценка: {macro_context.get('est', '')}"
    docs = retriever.retrieve(query, top_k)
    if not docs:
        return 0.5, "Нет релевантных документов"

    documents_text = "\n\n".join(docs)
    model_json_str = json.dumps(model, ensure_ascii=False, indent=2)

    prompt = rag_prompt_template.format(
        documents_text=documents_text,
        model_json=model_json_str
    )

    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL)
    result = parse_json(raw)
    score = result.get("score", 0.5)
    reason = result.get("reason", "")
    return score, reason

# ---------------------------------------------------------------------------
# Судья: синтез лучшей модели из вариантов
# ---------------------------------------------------------------------------

def judge_variants(
    macro_model: dict,
    variants: List[dict],
    judge_prompt_template: str = PROMPT_JUDGE_VARIANTS_MICROMODEL
) -> Tuple[dict, float, str]:

    macro_json_str = json.dumps(macro_model, ensure_ascii=False, indent=2)
    variants_text = ""
    for i, var in enumerate(variants):
        variants_text += f"Вариант {i+1}:\n{json.dumps(var, ensure_ascii=False, indent=2)}\n\n"

    prompt = judge_prompt_template.format(
        macro_model_json=macro_json_str,
        variants_text=variants_text
    )

    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL)
    result = parse_json(raw)
    final_model = result.get("final_micro", variants[0])   # имя поля 'final_micro' – можно сделать универсальным
    confidence = result.get("confidence", 0.5)
    reasoning = result.get("reasoning", "")
    return final_model, confidence, reasoning

# ===================================================================
# УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ВЕРИФИКАЦИИ
# ===================================================================
def verify_model(
    # Основные данные
    initial_model: dict,                      # исходная модель для верификации
    context_for_generation: dict,             # данные для генерации промпта (макро‑модель)
    context_for_rag: Optional[dict] = None,   # данные для RAG‑запроса (если отличаются)
    # Параметры генерации вариантов
    generation_prompt_builder: Callable[[dict], str] = None,  # функция(context) -> str
    generation_model: str = DEFAULT_GENERATION_MODEL,
    # Параметры валидатора структуры
    structure_validator: Callable[[dict], bool] = lambda x: True,
    # Параметры судьи
    judge_prompt_template: str = PROMPT_JUDGE_VARIANTS_MICROMODEL,
    # Параметры RAG
    use_rag: bool = True,
    rag_prompt_template: str = PROMPT_RAG_CONFIDENCE,
    # Общие настройки
    num_samples: int = 5,
    temperature: float = 0.7,
    confidence_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Универсальная верификация модели (микро, макро и др.)
    методом множественной генерации + LLM‑судья + RAG.

    Возвращает словарь:
        final_model, confidence, acceptable,
        judge_confidence, rag_confidence, reasoning.
    """
    # Если контекст для RAG не задан, используем основной контекст
    if context_for_rag is None:
        context_for_rag = context_for_generation

    # Построение промпта для генерации вариантов
    if generation_prompt_builder is None:
        raise ValueError("generation_prompt_builder обязателен")
    generation_prompt = generation_prompt_builder(context_for_generation)

    # 1. Генерация дополнительных вариантов с повторными попытками при нехватке
    variants = [initial_model]
    current_temp = temperature
    current_extra_samples = num_samples - 1  # сколько сгенерировать дополнительно
    max_temp = 1.2
    attempt = 0

    while len(variants) < 2 and current_temp <= max_temp:
        attempt += 1
        logger.info(
            f"Попытка #{attempt}: генерация {current_extra_samples} вариантов "
            f"с температурой {current_temp}"
        )
        for i in range(current_extra_samples):
            raw = call_openrouter(
                generation_prompt,
                model=generation_model,
                temperature=current_temp
            )
            model = parse_json(raw)
            if model and structure_validator(model):
                variants.append(model)
            else:
                logger.warning(
                    f"Вариант {i+1} из попытки #{attempt} не прошёл валидацию, пропущен."
                )
        if len(variants) < 2:
            current_temp += 0.1
            current_extra_samples = max(3, current_extra_samples + 1)
            logger.info(
                f"Недостаточно валидных вариантов (текущее: {len(variants)}). "
                f"Повышаем температуру до {current_temp}, "
                f"увеличиваем число генераций до {current_extra_samples}."
            )

    if len(variants) < 2:
        raise RuntimeError(
            f"Ошибка синтеза: недостаточно валидных вариантов\n"
            f"  Получено: {len(variants)}\n"
            f"  Попыток: {attempt}\n"
            f"  Макс. температура: {max_temp}\n"
            f"Рекомендация: заменить модель БЯМ для сэмплирования"
        )

    logger.info(f"Накоплено {len(variants)} валидных вариантов. Запуск судьи...")

    # 2. Синтез итоговой модели судьёй
    final_model, judge_conf, reasoning = judge_variants(
        context_for_generation, variants, judge_prompt_template
    )

    # 3. Структурная валидация итога
    if not structure_validator(final_model):
        logger.warning("Итоговая модель имеет структурные нарушения, уверенность снижена.")
        judge_conf *= 0.8
        reasoning += "\nВнимание: модель имеет структурные нарушения."

    # 4. RAG‑верификация (если возможна)
    rag_conf = None
    if use_rag:
        rag_conf, rag_reason = rag_confidence(
            context_for_rag, final_model, rag_prompt_template=rag_prompt_template
        )
        reasoning += f"\nRAG‑оценка: {rag_reason}"

    # 5. Комбинированная уверенность
    overall_conf = (0.5 * judge_conf + 0.5 * rag_conf) if rag_conf is not None else judge_conf
    acceptable = overall_conf >= confidence_threshold

    return {
        "final_model": final_model,
        "confidence": overall_conf,
        "acceptable": acceptable,
        "judge_confidence": judge_conf,
        "rag_confidence": rag_conf,
        "reasoning": reasoning
    }


# ===================================================================
# ОБЁРТКА ДЛЯ МИКРО‑МОДЕЛИ (обратная совместимость)
# ===================================================================
def verify_micro_model(
    macro_model: dict,
    initial_micro: dict,
    generation_model: str = DEFAULT_GENERATION_MODEL,
    use_rag: bool = True,
    num_samples: int = 5,
    temperature: float = 0.7,
    confidence_threshold: float = 0.7
) -> Dict[str, Any]:
    """
    Верификация микро‑модели (частный случай verify_model).
    Сохранены прежние аргументы для совместимости.
    """
    return verify_model(
        initial_model=initial_micro,
        context_for_generation=macro_model,
        generation_prompt_builder=build_micro_prompt,
        structure_validator=validate_micro_structure,
        judge_prompt_template=PROMPT_JUDGE_VARIANTS_MICROMODEL,
        generation_model=generation_model,
        use_rag=use_rag,
        rag_prompt_template=PROMPT_RAG_CONFIDENCE,
        num_samples=num_samples,
        temperature=temperature,
        confidence_threshold=confidence_threshold
    )

"""
def verify_macro_model (

)-> Dict[str, Any]:
    return verify_model(
    initial_model=initial_macro,
    context_for_generation=subproblem_description,
    generation_prompt_builder=build_macro_prompt,
    structure_validator=validate_macro_structure,
    judge_prompt_template=PROMPT_JUDGE_VARIANTS_MACROMODEL,  # нужно добавить в prompts.py
    ...
)
"""