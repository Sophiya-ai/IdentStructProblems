import os
import openai


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
            messages=[
                {
                    "role": "user",
                    "content": prompt
                },
            ],
            temperature=temperature,   # используем переданное значение
            max_tokens=4096,
            extra_body={"reasoning": {"enabled": True}}
        )
        return response.choices[0].message.content
    except Exception as e:
        raise RuntimeError(f"Ошибка при обращении к OpenRouter: {e}")