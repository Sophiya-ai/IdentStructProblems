import json
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import openai

from prompts import PROMPT_MICROMODEL

# ---------------------------------------------------------------------------
# Конфигурация OpenRouter
# ---------------------------------------------------------------------------
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_MODEL = os.getenv("DEFAULT_GENERATION_MODEL")

if not OPENROUTER_API_KEY:
    raise RuntimeError("Переменная окружения OPENROUTER_API_KEY не установлена")

if not OPENROUTER_MODEL:
    raise RuntimeError("Переменная окружения DEFAULT_GENERATION_MODEL_MICRO не установлена")

client = openai.OpenAI(
    base_url=OPENROUTER_BASE_URL,
    api_key=OPENROUTER_API_KEY,
)

# ---------------------------------------------------------------------------
# Загрузка макро‑модели
# ---------------------------------------------------------------------------
DEFAULT_MACRO_FILE = "macro_model.json"

def load_macro_model_from_console() -> dict:
    """Интерактивный ввод полей макро‑модели с консоли."""
    print("Введите макроуровневую модель проблемы.")
    model = {'id': input("id (идентификатор проблемы): "), 'sit': input("sit (описание проблемной ситуации): "),
             'sbj': input("sbj (субъект): "), 'est': input("est (негативная оценка ситуации): ")}
    return model

def load_macro_model_from_file(file_path: str = DEFAULT_MACRO_FILE) -> dict:
    """Чтение макро‑модели из JSON‑файла."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_macro_model(
    macro_dict: Optional[dict] = None,
    file_path: str = DEFAULT_MACRO_FILE
) -> dict:
    """
    Возвращает макро‑модель, выбирая источник по приоритету:
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
# Генерация промпта
# ---------------------------------------------------------------------------
def build_prompt(macro_model: dict) -> str:
    """Подставляет макро‑модель в шаблон PROMPT_MICROMODEL."""
    macro_json_str = json.dumps(macro_model, ensure_ascii=False)
    return PROMPT_MICROMODEL.format(macro_m_prb_json=macro_json_str)

# ---------------------------------------------------------------------------
# Вызов LLM через OpenRouter - все существующие вызовы call_openrouter без указания температуры работают с temperature=0.7
# ---------------------------------------------------------------------------
def call_openrouter(
    prompt: str,
    model: str = OPENROUTER_MODEL,
    temperature: float = 0.7
) -> str:
    """Отправляет промпт в OpenRouter и возвращает текст ответа."""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,   # используем переданное значение
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Ошибка при обращении к OpenRouter: {e}")

# ---------------------------------------------------------------------------
# Парсинг ответа LLM в микро‑модель
# ---------------------------------------------------------------------------
def parse_micro_model(llm_response: str) -> dict:
    """Извлекает JSON из ответа LLM и возвращает как словарь."""
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
# Основная функция генерации микро‑модели
# ---------------------------------------------------------------------------
def generate_micro_model(
    macro_dict: Optional[dict] = None,
    model: str = OPENROUTER_MODEL
) -> tuple[dict, dict]:
    """
    Полный цикл:
    - Загрузка макро‑модели (из словаря, файла или консоли)
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