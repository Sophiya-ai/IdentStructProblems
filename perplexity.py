import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Характеристики моделей
# ---------------------------------------------------------------------------
#  - meta-llama/Llama-3.2-1B-Instruct
    #  - Параметры: 1 миллиард (1B).
    #  - Тип: инструктивная (instruction‑tuned) авторегрессионная LLM.
    #  - Контекст: до 128k токенов (ограничиваем через параметр max_length).
#  - distilgpt2
    #  - Параметры: 82 млн.
    #  - Тип: авторегрессионная LLM.
    #  - Контекст: до 1024 токенов (ограничиваем через параметр max_length).
#  - Токенизатор: BPE, наследует Llama 2, содержит специальные токены.
#  - Применение: оценка «естественности» текста через перплексию.
# ---------------------------------------------------------------------------

# DEFAULT_MODEL_NAME = "meta-llama/Llama-3.2-1B-Instruct"
# DEFAULT_MAX_LENGTH = 8192   # можно менять до 128k
DEFAULT_MODEL_NAME = "distilgpt2"
DEFAULT_MAX_LENGTH = 1024

_tokenizer = None
_model = None

def _load_model(model_name: str = DEFAULT_MODEL_NAME):
    """Загружает токенизатор и модель при первом обращении."""
    global _tokenizer, _model
    if _model is None:
        logger.info(f"Загрузка модели {model_name} для вычисления перплексии...")
        _tokenizer = AutoTokenizer.from_pretrained(model_name)

        # Для авторегрессионных моделей pad_token обычно eos_token
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token
        _tokenizer.padding_side = "left"

        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float32,   # для CPU стабильнее float32
            device_map="auto" if torch.cuda.is_available() else None
        )
        _model.eval()
    return _tokenizer, _model


def compute_ppl(
    text: str,
    model_name: str = DEFAULT_MODEL_NAME,
    use_chat_template: bool = True,
    max_length: int = DEFAULT_MAX_LENGTH
) -> float:
    """
    Вычисляет перплексию текста.
    Если use_chat_template=True и модель поддерживает чат‑шаблон,
    текст оборачивается в сообщение пользователя (рекомендовано для инструктивных моделей).
    В противном случае используется обычная токенизация.
    """
    tokenizer, model = _load_model(model_name)

    # Проверяем, есть ли у токенизатора чат‑шаблон
    chat_available = hasattr(tokenizer, "chat_template") and tokenizer.chat_template is not None
    apply_chat = use_chat_template and chat_available

    if apply_chat:
        # Инструктивный режим: применяем чат‑шаблон
        messages = [{"role": "user", "content": text}]
        # apply_chat_template возвращает BatchEncoding с ключами input_ids и attention_mask
        enc = tokenizer.apply_chat_template(
            messages,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding=False  # паддинг не нужен, маска будет из единиц
        )
    else:
        enc = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=max_length,
            padding=False
        )

    # enc всегда BatchEncoding (словарь), поэтому безопасно извлекаем тензоры по ключам
    input_ids = enc.input_ids.to(model.device)

    # attention_mask всегда присутствует при return_tensors="pt" для гарантии стабильной работы с любыми моделями
    # и исключения предупреждений(даже без паддинга — все единицы)
    # attention_mask — это бинарный тензор той же длины,
    # что и input_ids, который указывает модели, какие токены являются реальными
    # данными (значение 1), а какие — паддингом (заполнением, значение 0)
    attention_mask = enc.attention_mask.to(model.device)

    with torch.no_grad():
        outputs = model(input_ids, attention_mask=attention_mask, labels=input_ids)
        loss = outputs.loss

    return torch.exp(loss).item()


def perplexity_confidence(
    prompt: str,
    response: str,
    model_name: str = DEFAULT_MODEL_NAME,
    max_length: int = DEFAULT_MAX_LENGTH
) -> float:
    """
    Оценка уверенности ответа на основе сравнения PPL ответа и запроса.
    Возвращает число от 0 до 1.
    """
    try:
        ppl_prompt = compute_ppl(prompt, model_name, max_length=max_length)
        ppl_response = compute_ppl(response, model_name, max_length=max_length)
    except Exception as e:
        logger.warning(f"Ошибка при вычислении перплексии: {e}")
        return 0.5

    epsilon = 1e-9
    ppl_ratio = ppl_response / (ppl_prompt + epsilon)
    confidence = 1.0 / (1.0 + ppl_ratio)
    return min(max(confidence, 0.0), 1.0)

