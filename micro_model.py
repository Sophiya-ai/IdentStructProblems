import json
import os
from pathlib import Path
from typing import Optional
from prompts import PROMPT_MICROMODEL
from call_llm import call_openrouter


OPENROUTER_MODEL = os.getenv("DEFAULT_GENERATION_MODEL")


# ---------------------------------------------------------------------------
# Загрузка макро‑модели
# ---------------------------------------------------------------------------
DEFAULT_MACRO_FILE = "macro_model.json"

def load_macro_model_from_console() -> dict:
    """Интерактивный ввод полей макромодели с консоли"""
    print("Введите макроуровневую модель проблемы.")
    model = {'id': input("id (идентификатор проблемы): "), 'sit': input("sit (описание проблемной ситуации): "),
             'sbj': input("sbj (субъект): "), 'est': input("est (негативная оценка ситуации): ")}
    return model

def load_macro_model_from_file(file_path: str = DEFAULT_MACRO_FILE) -> dict:
    """Чтение макромодели из JSON‑файла."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_macro_model(
    macro_dict: Optional[dict] = None,
    file_path: str = DEFAULT_MACRO_FILE
) -> dict:
    """
    Возвращает макромодель, выбирая источник по приоритету:
    1. Переданный словарь macro_dict (если не None).
    2. Локальный JSON‑файл, если существует.
    3. Интерактивный ввод с консоли.
    """
    if macro_dict is not None:
        return macro_dict

    if Path(file_path).exists():
        return load_macro_model_from_file(file_path)

    return load_macro_model_from_console()

# ---------------------------------------------------------------------------
# Генерация промпта - подставляет макромодель в шаблон PROMPT_MICROMODEL
# ---------------------------------------------------------------------------
def build_prompt(macro_model: dict) -> str:
    macro_json_str = json.dumps(macro_model, ensure_ascii=False)
    return PROMPT_MICROMODEL.format(macro_m_prb_json=macro_json_str)

# ---------------------------------------------------------------------------
# Парсинг ответа БЯМ в микромодель - извлекает JSON из ответа БЯМ и возвращает как словарь
# ---------------------------------------------------------------------------
def parse_micro_model(llm_response: str) -> dict:
    """."""
    # Иногда LLM может обернуть JSON в ```json ... ```, убираем
    cleaned = llm_response.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    # иногда перед JSON может быть текст, ищем первую '{' и последнюю '}'
    start_idx = cleaned.find('{')
    end_idx = cleaned.rfind('}')
    if start_idx != -1 and end_idx != -1:
        cleaned = cleaned[start_idx:end_idx+1]
    try:
        micro = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"Не удалось распарсить JSON из ответа LLM: {e}\nОтвет был:\n{llm_response}")
    return micro

# ---------------------------------------------------------------------------
# Основная функция генерации микромодели
# ---------------------------------------------------------------------------
def generate_micro_model(
    macro_dict: Optional[dict] = None,
    model: str = OPENROUTER_MODEL
) -> tuple[dict, dict]:
    """
    Полный цикл:
    - Загрузка макромодели (из словаря, файла или консоли)
    - Построение промпта
    - Запрос к OpenRouter
    - Парсинг и возврат микро‑модели
    """
    macro = get_macro_model(macro_dict)
    prompt = build_prompt(macro)
    print("Отправка запроса в OpenRouter...")
    llm_answer = call_openrouter(prompt, model=model)
    micro = parse_micro_model(llm_answer)
    return macro, micro