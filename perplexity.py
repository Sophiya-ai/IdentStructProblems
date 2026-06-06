import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Характеристика модели meta-llama/Llama-3.2-1B-Instruct
# ---------------------------------------------------------------------------
#    - Параметры: 1 миллиард (1B).
#    - Тип: инструктивная (instruction‑tuned) авторегрессионная LLM.
#    - Контекст: до 128k токенов (но мы ограничиваем 1024 для скорости).
#    - Токенизатор: основан на BPE (Byte‑Pair Encoding), наследует Llama 2,
#       автоматически загружается вместе с моделью через AutoTokenizer.
#       Содержит специальные токены: <|begin_of_text|>, <|end_of_text|> и т.д.
#    - Преимущества: легковесна, запускается на CPU, высокая скорость инференса.
#    - Применение в оценке перплексии: модель оценивает «естественность»
#      текста, не требуя дообучения.
# ---------------------------------------------------------------------------

# Идентификатор модели на Hugging Face Hub
DEFAULT_MODEL_NAME = "meta-llama/Llama-3.2-1B-Instruct"

# Глобальные переменные для ленивой загрузки (один раз за сессию)
_tokenizer = None
_model = None

def _load_model(model_name: str = DEFAULT_MODEL_NAME):
    """
    Загружает токенизатор и модель при первом обращении.
    Использует кэширование, чтобы не загружать повторно.
    """
    global _tokenizer, _model
    if _model is None:
        logger.info(f"Загрузка модели {model_name} для вычисления перплексии...")
        # Токенизатор – автоматически определяется конфигурацией модели
        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        # Для авторегрессионных моделей padding_side должен быть слева
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token
        _tokenizer.padding_side = "left"

        # Загрузка модели (CPU/GPU выбирается автоматически, если доступен CUDA)
        _model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float32,   # для CPU стабильнее float32
            device_map="auto" if torch.cuda.is_available() else None
        )
        _model.eval()  # отключаем dropout и другие обучающие слои
    return _tokenizer, _model

def compute_ppl(text: str, model_name: str = DEFAULT_MODEL_NAME) -> float:
    """
    Вычисляет перплексию (perplexity) переданного текста.
    Возвращает число >= 1.0. Чем ниже значение, тем текст «более ожидаем»
    для модели.
    """
    tokenizer, model = _load_model(model_name)

    # Токенизируем текст, обрезая до 1024 токенов для эффективности
    # и возвращая тензоры PyTorch
    encodings = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=1024
    )

    input_ids = encodings.input_ids.to(model.device)
    attention_mask = encodings.attention_mask.to(model.device)   # attention_mask — это бинарный тензор той же длины,
                                        # что и input_ids, который указывает модели, какие токены являются реальными
                                        # данными (значение 1), а какие — паддингом (заполнением, значение 0)

    # Вычисляем лосс (кросс‑энтропию) на предсказании каждого токена
    with torch.no_grad():
        outputs = model(input_ids, attention_mask=attention_mask, labels=input_ids)
        loss = outputs.loss  # средняя кросс‑энтропия по токенам

    # Перплексия = exp(loss)
    return torch.exp(loss).item()

def perplexity_confidence(prompt: str, response: str, model_name: str = DEFAULT_MODEL_NAME) -> float:
    """
    Оценивает уверенность сгенерированного ответа на основе
    сравнения его перплексии с перплексией промпта.
    Логика:
    - Чем ближе PPL ответа к PPL промпта, тем выше уверенность.
    - Используется нормировка: confidence = 1 / (1 + PPL_ratio),
      где PPL_ratio = PPL_response / (PPL_prompt + ε).
    Возвращает значение от 0 до 1.
    """
    try:
        ppl_prompt = compute_ppl(prompt, model_name)
        ppl_response = compute_ppl(response, model_name)
    except Exception as e:
        logger.warning(f"Ошибка при вычислении перплексии: {e}")
        return 0.5  # нейтральная оценка в случае сбоя

    epsilon = 1e-9
    ppl_ratio = ppl_response / (ppl_prompt + epsilon)

    # Преобразование: при равных PPL → 1/(1+1)=0.5,
    #                 при PPL ответа много меньше → стремится к 1,
    #                 при PPL ответа много больше → стремится к 0.
    confidence = 1.0 / (1.0 + ppl_ratio)

    # Ограничиваем диапазон [0, 1] (на случай численных погрешностей)
    return min(max(confidence, 0.0), 1.0)

"""ВАРИАНТ с МОДЕЛЬЮ
# Модель по умолчанию (маленькая, быстрая, не требует GPU)
DEFAULT_MODEL_NAME = "distilgpt2"

# Глобальные переменные для хранения загруженной модели и токенизатора (загружаются один раз)
# Префикс _ указывает на то, что переменная предназначена для внутреннего использования внутри данного модуля.
# Импортировать из другого модуля такую переменную нельзя
_tokenizer = None
_model = None

def _load_model(model_name: str = DEFAULT_MODEL_NAME):
    #Ленивая загрузка модели и токенизатора (только при первом обращении).
    global _tokenizer, _model
    if _model is None:
        logger.info(f"Загрузка модели {model_name} для перплексии...")
        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        _model = AutoModelForCausalLM.from_pretrained(model_name)
        _model.eval() # переводим в режим оценки

        # GPT-2 ожидает токен паддинга (pad_token), если его нет, используем eos
        if _tokenizer.pad_token is None:
            _tokenizer.pad_token = _tokenizer.eos_token
    return _tokenizer, _model

def compute_ppl(text: str, model_name: str = DEFAULT_MODEL_NAME) -> float:
    
    #Вычисляет перплексию (perplexity) текста с помощью указанной модели.
    #Перплексия — это экспонента кросс‑энтропии модели на данном тексте.
    #Низкая перплексия = текст более «естественен» для модели.
    
    tokenizer, model = _load_model(model_name)

    # Токенизация: возвращаем тензоры PyTorch и обрезаем до 1024 токенов для эффективности
    encodings = tokenizer(text, return_tensors="pt", truncation=True, max_length=1024)
    input_ids = encodings.input_ids

    # Вычисляем лосс (кросс‑энтропию) модели на собственных предсказаниях
    with torch.no_grad():
        outputs = model(input_ids, labels=input_ids)
        loss = outputs.loss         # кросс‑энтропия для языкового моделирования
    return torch.exp(loss).item()   # Перплексия = exp(loss)

def perplexity_confidence(prompt: str, response: str, model_name: str = DEFAULT_MODEL_NAME) -> float:
    
    #Оценивает уверенность сгенерированного ответа на основе сравнения его перплексии
    #с перплексией запроса.
    #Использует эвристику: чем ближе перплексия ответа к перплексии запроса, тем выше уверенность.

    #Возвращает число в диапазоне [0, 1], где 1 — максимальная уверенность.
    
    try:
        ppl_prompt = compute_ppl(prompt, model_name)
        ppl_response = compute_ppl(response, model_name)
    except Exception as e:
        logger.warning(f"Не удалось вычислить перплексию: {e}")
        return 0.5   # нейтральная оценка при любых сбоях

    # Используем отношение: ppl_ratio = ppl_response / (ppl_prompt + ε)
    epsilon = 1e-9
    ppl_ratio = ppl_response / (ppl_prompt + epsilon)

    # Преобразуем отношение в уверенность: confidence = 1 / (1 + ppl_ratio)
    # Если ppl_ratio → 0 (ответ гораздо «проще» запроса), то confidence → 1.
    # Если ppl_ratio → ∞ (ответ «сложнее»), то confidence → 0.
    confidence = 1.0 / (1.0 + ppl_ratio)
    return min(max(confidence, 0.0), 1.0)

"""