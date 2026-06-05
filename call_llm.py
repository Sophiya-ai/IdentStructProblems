import time
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
# Вспомогательная функция для извлечения времени ожидания из ошибки
# ---------------------------------------------------------------------------
def _extract_retry_after(error: Exception, default: float) -> float:
    """
    Извлекает рекомендованное время ожидания (Retry-After) из объекта ошибки.
    OpenRouter может возвращать его в разных местах, поэтому проверяем все возможные варианты.
    """
    # 1. Стандартный атрибут библиотеки openai (если SDK сам распарсил заголовок)
    if hasattr(error, 'retry_after') and error.retry_after:
        try:
            return float(error.retry_after)
        except (ValueError, TypeError):
            pass

    # 2. Прямой поиск в HTTP заголовках (Retry-After)
    if hasattr(error, 'headers') and error.headers and 'Retry-After' in error.headers:
        try:
            return float(error.headers['Retry-After'])
        except (ValueError, TypeError):
            pass

    # 3. Специфика OpenRouter: они кладут время ожидания в тело ответа
    # (в поле metadata -> retry_after_seconds)
    if hasattr(error, 'body') and isinstance(error.body, dict):
        metadata = error.body.get('metadata', {})
        if 'retry_after_seconds' in metadata:
            try:
                return float(metadata['retry_after_seconds'])
            except (ValueError, TypeError):
                pass

    # Если ничего не нашли, возвращаем значение по умолчанию
    return default

# ---------------------------------------------------------------------------
# Вызов LLM через OpenRouter
# - все существующие вызовы call_openrouter без указания температуры работают с temperature=0.7
# - с механизмом повторных попыток (Retry with Exponential Backoff)
# ---------------------------------------------------------------------------
def call_openrouter(
    prompt: str,
    model: str = OPENROUTER_MODEL,
    temperature: float = 0.7,
    max_retries: int = 5,          # Максимальное количество попыток "дозвона"
    initial_delay: float = 5.0     # Начальная задержка в секундах (если сервер не указал свою)
) -> str:
    delay = initial_delay

    # Запускаем цикл попыток
    for attempt in range(1, max_retries + 1):
        try:
            # Пытаемся выполнить запрос к API
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
            # Если запрос прошёл успешно, сразу возвращаем результат и выходим из функции
            return response.choices[0].message.content
        except openai.RateLimitError as e:
            # --- ОБРАБОТКА ОШИБКИ 429 (Превышен лимит запросов) ---
            # Достаём время ожидания, которое подсказал OpenRouter (например, 30 секунд)
            retry_after = _extract_retry_after(e, default=delay)

            print(f"⚠️  [Попытка {attempt}/{max_retries}] Превышен лимит запросов (429). "
                  f"Ожидание {retry_after} сек. перед повторной попыткой...")
            time.sleep(retry_after)

            # Увеличиваем задержку для следующей попытки (Exponential Backoff)
            # Если в первый раз ждали 30 сек, то в следующий раз (если снова будет ошибка)
            # будем ждать 60 сек, затем 120 и т.д.
            delay = retry_after * 2

        except openai.APIStatusError as e:
            # --- ОБРАБОТКА ДРУГИХ ОШИБОК API ---
            if e.status_code >= 500:
                # Ошибки 5xx (500, 502, 503, 504) означают, что сервер "упал" или перегружен.
                # В этом случае имеет смысл подождать и попробовать снова.
                print(f"⚠️  [Попытка {attempt}/{max_retries}] Ошибка сервера ({e.status_code}). "
                      f"Ожидание {delay} сек...")
                time.sleep(delay)
                delay *= 2
            else:
                # Ошибки 4xx (кроме 429), например 400 (Bad Request), 401 (Unauthorized).
                # Это клиентские ошибки. Повторять их бессмысленно — сервер всё равно ответит отказом.
                # Поэтому сразу прерываем выполнение и пробрасываем ошибку.
                raise RuntimeError(f"Ошибка при обращении к OpenRouter (статус {e.status_code}): {e.message}") from e

        except Exception as e:
            # --- ОБРАБОТКА СЕТЕВЫХ И ДРУГИХ ОШИБОК ---
            # Например, обрыв интернет-соединения, таймаут DNS и т.д.
            print(f"⚠️  [Попытка {attempt}/{max_retries}] Сетевая ошибка: {e}. "
                  f"Ожидание {delay} сек...")
            time.sleep(delay)
            delay *= 2

        # Если цикл завершился, и мы ни разу не вернули response (все попытки исчерпаны)
    raise RuntimeError(f"Не удалось получить ответ от OpenRouter после {max_retries} попыток")