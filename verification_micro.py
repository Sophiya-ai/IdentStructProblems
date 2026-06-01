import os
import json
import logging
from typing import Dict, Any, List, Tuple
from dotenv import load_dotenv

from micro_model import (
    build_prompt,
    call_openrouter,
    parse_micro_model as parse_json,
    OPENROUTER_MODEL as DEFAULT_GENERATION_MODEL,
)
from prompts import PROMPT_JUDGE_VARIANTS_MICROMODEL, PROMPT_RAG_CONFIDENCE_MICROMODEL

load_dotenv()

# ---------------------------------------------------------------------------
# Логирование
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
    """Возвращает объект retriever'а или None."""
    try:
        from retrieval import get_retriever as _get_retriever
        return _get_retriever()
    except ImportError:
        logger.info("Модуль retrieval не найден, RAG недоступен.")
        return None

def rag_confidence(macro_model: dict, micro_model: dict, top_k: int = 3) -> Tuple[float, str]:
    """Оценка соответствия микро‑модели документам."""
    retriever = get_retriever()
    if retriever is None:
        return 1.0, "RAG недоступен"

    query = f"Проблема: {macro_model.get('sit', '')}\nСубъект: {macro_model.get('sbj', '')}\nОценка: {macro_model.get('est', '')}"
    docs = retriever.retrieve(query, top_k)
    if not docs:
        return 0.5, "Нет релевантных документов"

    documents_text = "\n\n".join(docs)
    micro_json_str = json.dumps(micro_model, ensure_ascii=False, indent=2)
    prompt = PROMPT_RAG_CONFIDENCE_MICROMODEL.format(
        documents_text=documents_text,
        micro_model_json=micro_json_str
    )

    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL)
    result = parse_json(raw)
    score = result.get("score", 0.5)
    reason = result.get("reason", "")
    return score, reason

# ---------------------------------------------------------------------------
# Судья: синтез лучшей микро‑модели из вариантов
# ---------------------------------------------------------------------------
def judge_variants(macro_model: dict, variants: List[dict]) -> Tuple[dict, float, str]:
    """Передаёт все варианты судье и получает итоговую микро‑модель."""
    macro_json_str = json.dumps(macro_model, ensure_ascii=False, indent=2)
    variants_text = ""
    for i, var in enumerate(variants):
        variants_text += f"Вариант {i+1}:\n{json.dumps(var, ensure_ascii=False, indent=2)}\n\n"

    prompt = PROMPT_JUDGE_VARIANTS_MICROMODEL.format(
        macro_model_json=macro_json_str,
        variants_text=variants_text
    )

    raw = call_openrouter(prompt, model=DEFAULT_JUDGE_MODEL)
    result = parse_json(raw)
    final_micro = result.get("final_micro", variants[0])
    confidence = result.get("confidence", 0.5)
    reasoning = result.get("reasoning", "")
    return final_micro, confidence, reasoning

# ===================================================================
# ОСНОВНОЙ МЕТОД ВЕРИФИКАЦИИ
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

    Если generation_prompt не передан, он будет построен из macro_model.
    Возвращает словарь с полями:
        final_micro, confidence, acceptable,
        judge_confidence, rag_confidence, reasoning.
    """
    if generation_prompt is None:
        generation_prompt = build_prompt(macro_model)

    logger.info(f"Генерация {num_samples-1} дополнительных вариантов (температура {temperature})...")
    variants = [initial_micro]
    for i in range(num_samples - 1):
        raw = call_openrouter(generation_prompt, model=generation_model)
        micro = parse_json(raw)
        if micro and validate_micro_structure(micro):
            variants.append(micro)
        else:
            logger.warning(f"Вариант {i+1} не прошёл структурную валидацию, пропущен.")
    if len(variants) < 2:
        raise RuntimeError("Слишком мало валидных вариантов для синтеза")

    logger.info("Синтез итоговой модели судьёй...")
    final_micro, judge_conf, reasoning = judge_variants(macro_model, variants)

    if not validate_micro_structure(final_micro):
        logger.warning("Итоговая модель имеет структурные нарушения, уверенность снижена.")
        judge_conf *= 0.8
        reasoning += "\nВнимание: модель имеет структурные нарушения."

    rag_conf = None
    if use_rag:
        rag_conf, rag_reason = rag_confidence(macro_model, final_micro)
        reasoning += f"\nRAG‑оценка: {rag_reason}"

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