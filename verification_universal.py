import os
import json
import logging
from typing import Dict, Any, List, Tuple, Callable, Optional
from dotenv import load_dotenv

from micro_model import (
    build_prompt as build_micro_prompt,  # формирование промпта для генерации микро‑модели
    parse_micro_model as parse_json
)
from call_llm import call_openrouter
from prompts import (
    PROMPT_JUDGE_VARIANTS,
    PROMPT_RAG_CONFIDENCE,
    PROMPT_SEMANTIC_VALIDATION
)
from validation_criteria import MICRO_VALIDATION_CRITERIA#, MACRO_VALIDATION_CRITERIA
from perplexity import perplexity_confidence

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_GENERATION_MODEL = os.getenv("DEFAULT_GENERATION_MODEL")

# Модель-судья из .env
DEFAULT_JUDGE_MODEL = os.getenv("DEFAULT_JUDGE_MODEL")
if not DEFAULT_JUDGE_MODEL:
    raise RuntimeError("Переменная окружения DEFAULT_JUDGE_MODEL не установлена")


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------
def semantic_validate_model(
        context: dict,  # контекст, в рамках которого модель создана (макромодель, описание подпроблемы и т.п.)
        model: dict,  # проверяемая модель (микро, макро и др.)
        model_type: str,  # название типа модели для промпта, например "микроуровневая модель"
        validation_criteria: str,  # текстовое описание критериев проверки (структура, осмысленность и т.д.)
        judge_model: str = DEFAULT_JUDGE_MODEL,
        accept_threshold: float = 0.6
) -> Tuple[bool, float, str]:
    """
    УНИВЕРСАЛЬНАЯ СЕМАНТИЧЕСКАЯ ПРОВЕРКА: Проверяет модель на соответствие контексту по заданным критериям.
    Возвращает: (passed: bool, score: float, reasoning: str).
    """
    context_json_str = json.dumps(context, ensure_ascii=False, indent=2)
    model_json_str = json.dumps(model, ensure_ascii=False, indent=2)

    prompt = PROMPT_SEMANTIC_VALIDATION.format(
        model_type=model_type,
        context_json=context_json_str,
        model_json=model_json_str,
        validation_criteria=validation_criteria
    )

    raw = call_openrouter(prompt, model=judge_model, temperature=0.4)
    result = parse_json(raw)

    score = float(result.get("score", 0.0))
    accept = bool(result.get("accept", False))
    reasoning = result.get("reasoning", "")

    passed = accept and score >= accept_threshold
    return passed, score, reasoning


# Проверка обязательных полей и их типов для микромодели
def validate_micro_structure(micro: dict) -> bool:
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


# Проверяет обязательные поля и их типы для макро‑модели
""" в разработке
def validate_macro_structure(macro: dict) -> bool:
    required = {"id", "sit", "sbj", "est"}
    return all(k in macro for k in required)
"""


def create_combined_validator(
        context: dict,  # контекст для семантической проверки
        structure_validator: Callable[[dict], bool],  # функция структурной валидации
        model_type: str,  # тип модели (для промпта)
        validation_criteria: str,  # описание критериев семантической проверки
        enable_semantic: bool = True,
        semantic_model: str = DEFAULT_JUDGE_MODEL,
        semantic_threshold: float = 0.6
) -> Callable[[dict], bool]:
    """
    УНИВЕРСАЛЬНЫЙ КОМБИНИРОВАННЫЙ ВАЛИДАТОР (СТРУКТУРА + СЕМАНТИКА).
    Возвращает функцию-валидатор, которая сначала проверяет структуру,
    затем (опционально) выполняет семантическую проверку через БЯМ.
    Возвращает True, только если модель прошла все проверки.
    """

    def validator(model: dict) -> bool:
        if not structure_validator(model):
            return False
        if not enable_semantic:
            return True
        passed, score, _ = semantic_validate_model(
            context, model, model_type,
            validation_criteria=validation_criteria,
            judge_model=semantic_model,
            accept_threshold=semantic_threshold
        )
        if not passed:
            logger.info(f"Модель типа '{model_type}' отклонена семантической проверкой (score={score:.2f})")
        return passed

    return validator


# Возвращает объект retriever'а или None
def get_retriever():
    try:
        from retrieval import get_retriever as _get_retriever
        return _get_retriever()
    except ImportError:
        logger.info("Модуль retrieval не найден, RAG недоступен.")
        return None


def rag_confidence(
        macro_context: dict,  # контекст (макро‑модель) для формирования запроса
        model: dict,  # проверяемая модель (микро или макро)
        top_k: int = 6,
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

    query = f"Проблема: {macro_context.get('id', '')}\nСитуация: {macro_context.get('sit', '')}\nСубъект: {macro_context.get('sbj', '')}\nОценка: {macro_context.get('est', '')}"
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


# СУДЬЯ: синтез лучшей модели из вариантов - отправляет полный промпт судье и возвращает синтезированную модель
def judge_variants(judge_prompt: str) -> Tuple[dict, float, str]:
    raw = call_openrouter(judge_prompt, model=DEFAULT_JUDGE_MODEL)
    result = parse_json(raw)
    final_model = result.get("final_model")
    confidence = result.get("confidence", 0.5)
    reasoning = result.get("reasoning", "")
    return final_model, confidence, reasoning


# ===================================================================
# УНИВЕРСАЛЬНАЯ ФУНКЦИЯ ВЕРИФИКАЦИИ
# ===================================================================
def verify_model(
        # Основные данные
        initial_model: dict,  # исходная модель для верификации
        context_for_generation: dict,  # данные для генерации промпта (макро‑модель)
        generation_prompt_builder: Callable[[dict], str] = None,  # функция(context) -> str
        model_validator: Callable[[dict], bool] = lambda x: True,
        judge_prompt_builder: Optional[Callable[[dict, List[dict]], str]] = None,
        generation_model: str = DEFAULT_GENERATION_MODEL,
        use_rag: bool = True,
        use_perplexity: bool = True,
        rag_prompt_template: str = PROMPT_RAG_CONFIDENCE,
        num_samples: int = 5,
        temperature: float = 0.7,
        confidence_threshold: float = 0.7,
        context_for_rag: Optional[dict] = None,  # данные для RAG‑запроса (если отличаются)
) -> Dict[str, Any]:
    """
    Универсальная верификация модели (микро, макро и др.)
    методом множественной генерации + БЯМ‑судья + RAG.
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

    while len(variants) < 3 and current_temp <= max_temp:
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
            if model and model_validator(model):
                logger.info(f"Получено: {len(variants)} валидных вариантов. Сэмплируем дальше...")
                variants.append(model)
            else:
                logger.warning(
                    f"Вариант {i + 1} из попытки #{attempt} не прошёл валидацию, пропущен."
                )
        if len(variants) < 3:
            current_temp += 0.1
            current_extra_samples = max(3, current_extra_samples + 1)
            logger.info(
                f"Недостаточно валидных вариантов (текущее: {len(variants)}). "
                f"Повышаем температуру до {current_temp}, "
                f"увеличиваем число генераций до {current_extra_samples}."
            )

    if len(variants) < 3:
        raise RuntimeError(
            f"Ошибка синтеза: недостаточно валидных вариантов\n"
            f"  Получено: {len(variants)}\n"
            f"  Попыток: {attempt}\n"
            f"  Макс. температура: {max_temp}\n"
            f"Рекомендация: заменить модель БЯМ для сэмплирования"
        )

    logger.info(f"Накоплено {len(variants)} валидных вариантов. Запуск судьи...")

    # 2. Синтез итоговой модели судьёй
    judge_prompt = judge_prompt_builder(context_for_generation, variants)
    final_model, judge_conf, reasoning = judge_variants(judge_prompt)
    reasoning += f"\nИсходная оценка модели самим судьей: {judge_conf}."
    logger.info(f"\nИсходная оценка модели самим судьей: {judge_conf}")
    # 3. Структурная + семантическая (опционально) валидация итога
    if not model_validator(final_model):
        logger.warning("Итоговая модель имеет структурные нарушения, уверенность снижена.")
        judge_conf *= 0.8
        reasoning += f"\nВнимание: модель имеет структурные/семантические нарушения! Оценка снижена - {judge_conf}!"
        logger.info(f"Оценка модели после валидации: {judge_conf} Причина: модель имеет структурные/семантические нарушения!")

    # 4. RAG‑верификация (если возможна)
    rag_conf = None
    if use_rag:
        rag_conf, rag_reason = rag_confidence(
            context_for_rag, final_model, rag_prompt_template=rag_prompt_template
        )
        reasoning += f"\nRAG‑оценка {rag_conf}: {rag_reason}"
        logger.info(f"RAG‑оценка: {rag_conf} Причина: {rag_reason}")

    # 5. Perplexity-based Confidence
    ppl_conf = None
    if use_perplexity:
        # generation_prompt
        # final_model – словарь, преобразуем в JSON-строку для вычисления PPL
        response_text = json.dumps(final_model, ensure_ascii=False)
        ppl_conf = perplexity_confidence(generation_prompt, response_text)
        reasoning += f"\nУверенность на основе перплексии : {ppl_conf:.2f}"
        logger.info(f"Уверенность на основе перплексии : {ppl_conf:.2f}")

    # 6. Комбинированная уверенность
    # Судья: 0.7, RAG: 0.15, Перплексия: 0.15
    total_weight = 0.0
    overall_conf = 0.0

    if judge_conf is not None:
        overall_conf += 0.7 * judge_conf
        total_weight += 0.7
    if rag_conf is not None:
        overall_conf += 0.15 * rag_conf
        total_weight += 0.15
    if ppl_conf is not None:
        overall_conf += 0.15 * ppl_conf
        total_weight += 0.15

    # Нормируем на сумму присутствующих весов
    if total_weight > 0:
        overall_conf /= total_weight
    else:
        overall_conf = 0.5  # fallback - полная неопределённость

    acceptable = overall_conf >= confidence_threshold

    return {
        "final_model": final_model,
        "confidence": overall_conf,
        "acceptable": acceptable,
        "judge_confidence": judge_conf,
        "rag_confidence": rag_conf,
        "perplexity_confidence": ppl_conf,
        "reasoning": reasoning
    }


# Функция формирования промпта судьи для микромоделей (использует универсальный промпт)
def _build_judge_prompt_for_micro(context: dict, variants: List[dict]) -> str:
    context_description = json.dumps({
        "задача": "Построить микроуровневую модель проблемы по заданной макромодели",
        "макромодель": context,
        "требования_к_микромодели": MICRO_VALIDATION_CRITERIA
    }, ensure_ascii=False, indent=2)
    variants_text = "\n\n".join(
        f"Вариант {i + 1}:\n{json.dumps(v, ensure_ascii=False, indent=2)}"
        for i, v in enumerate(variants)
    )
    return PROMPT_JUDGE_VARIANTS.format(
        model_type="микроуровневая модель проблемы",
        context_description=context_description,
        variants_text=variants_text
    )


""" в разработке
def _build_judge_prompt_for_macro(context: dict, variants: List[dict]) -> str:
    context_description = json.dumps({
        "задача": "Построить макроуровневое описание подпроблемы",
        "описание_подпроблемы": context,
        "требования": MACRO_VALIDATION_CRITERIA
    }, ensure_ascii=False, indent=2)
    variants_text = "\n\n".join(...)
    return PROMPT_JUDGE_VARIANTS_UNIVERSAL.format(
        model_type="макроуровневая модель подпроблемы",
        context_description=context_description,
        variants_text=variants_text
    )
"""


# ===================================================================
# ОБЁРТКА ДЛЯ МИКРО‑МОДЕЛИ
# ===================================================================
def verify_micro_model(
        macro_model: dict,
        initial_micro: dict,
        generation_model: str = DEFAULT_GENERATION_MODEL,
        use_rag: bool = True,
        use_perplexity: bool = True,
        num_samples: int = 5,
        temperature: float = 0.7,
        confidence_threshold: float = 0.7,
        enable_semantic_validation: bool = True,
        semantic_accept_threshold: float = 0.6
) -> Dict[str, Any]:
    # Верификация микромодели (частный случай verify_model)
    combined_validator = create_combined_validator(
        context=macro_model,
        structure_validator=validate_micro_structure,
        model_type="микроуровневая модель проблемы",
        validation_criteria=MICRO_VALIDATION_CRITERIA,
        enable_semantic=enable_semantic_validation,
        semantic_model=DEFAULT_JUDGE_MODEL,
        semantic_threshold=semantic_accept_threshold
    )

    return verify_model(
        initial_model=initial_micro,
        context_for_generation=macro_model,
        generation_prompt_builder=build_micro_prompt,
        model_validator=combined_validator,
        judge_prompt_builder=_build_judge_prompt_for_micro,
        generation_model=generation_model,
        use_rag=use_rag,
        use_perplexity=use_perplexity,
        rag_prompt_template=PROMPT_RAG_CONFIDENCE,
        num_samples=num_samples,
        temperature=temperature,
        confidence_threshold=confidence_threshold
    )


""" В разработке
def verify_macro_model(
    context: dict,
    initial_macro: dict,
    generation_prompt_builder: Callable,
    ...
):
    
    combined_validator = create_combined_validator(
        context=context,
        structure_validator=validate_macro_structure,
        model_type="макроуровневая модель подпроблемы",
        validation_criteria=MACRO_VALIDATION_CRITERIA,
        ...
    )
    return verify_model(...)
"""
