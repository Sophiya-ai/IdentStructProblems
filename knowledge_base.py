import os
import chromadb

# Папка, где лежат текстовые и PDF-файлы с базой знаний
KNOWLEDGE_DIR = "knowledge_files"

# Инициализируем ChromaDB - PersistentClient сохраняет базу данных на диск в папку ./chroma_db.
# Это позволяет данным сохраняться между запусками программы
chroma_client = chromadb.PersistentClient(path="./chroma_db")


"""
Создаём или открываем коллекцию: "коллекция" в ChromaDB аналогична "таблице" в реляционных базах данных.
metadata={"hnsw:space": "cosine"} - это важная настройка алгоритма поиска:
- hnsw (Hierarchical Navigable Small World) — это алгоритм, который ChromaDB использует для быстрого приближённого поиска ближайших соседей;
- cosine (косинусное сходство) измеряет угол между векторами. Для текстовых эмбеддингов это лучший выбор.
 cosine оценивает смысловую близость, игнорируя длину текста (в отличие от евклидова расстояния).
"""
collection = chroma_client.get_or_create_collection(
    name="knowledge_base",
    metadata={"hnsw:space": "cosine"}
)


def extract_text_from_pdf(filepath: str) -> str:
    """
    Извлекает весь текст из PDF-файла с помощью PyMuPDF.
    Возвращает строку с содержимым всех страниц.
    """
    try:
        import fitz    #PyMuPDF
    except ImportError:
        raise ImportError(
            "Для работы с PDF установите PyMuPDF: pip install PyMuPDF"
        )

    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def split_text_into_chunks(
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50
) -> list[str]:
    """
    Разбиваем текст на смысловые фрагменты (чанки) с учётом токенов и перекрытий.
    Аргументы:
        - text (str): Исходный текст для разбиения.
        - chunk_size (int): Максимальный размер одного чанка в токенах (по умолчанию 500).
        - chunk_overlap (int): Количество перекрывающихся токенов между соседними чанками.
                             Это нужно, чтобы не терять контекст на границах разбиения.
    Возвращает:
        list[str]: Список текстовых фрагментов, готовых для векторизации.
    """

    # 1. Проверяем наличие необходимых библиотек (ленивый импорт)
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        import tiktoken
    except ImportError:
        raise ImportError(
            "Для умного разбиения текста установите зависимости: "
            "pip install langchain langchain-text-splitters tiktoken"
        )

    # 2. Инициализируем токенайзер.
    #    "cl100k_base" — это стандартный токенайзер для моделей GPT-3.5, GPT-4 и многих других.
    #    Он корректно считает токены, что критически важно для соблюдения лимитов контекста LLM.

    tokenizer = tiktoken.get_encoding("cl100k_base")

    # 3. Создаём экземпляр рекурсивного разделителя текста
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,        # Целевой размер чанка в токенах
        chunk_overlap=chunk_overlap,  # Перекрытие (overlap) для сохранения контекста

        # Функция, которая говорит разделителю, как измерять длину текста (токены).
        length_function=lambda x: len(tokenizer.encode(x)),

        # Иерархия разделителей. Сплиттер будет пытаться разбить текст по порядку:
        #      1. \n\n (между абзацами) - самый приоритетный, сохраняет смысловые блоки
        #      2. \n (между строками)
        #      3. " " (между словами)
        #      4. "" (между символами) - используется только в крайнем случае, если слово длиннее chunk_size
        separators=["\n\n", "\n", " ", ""]
    )

    # 4. Выполняем разбиение текста
    #    Метод split_text возвращает список строк, гарантируя, что ни один чанк не превысит chunk_size токенов,
    #    и что границы будут максимально "естественными".
    chunks = text_splitter.split_text(text)

    # 5. Дополнительная очистка: удаляем чанки, которые после разбиения оказались пустыми
    #    или состоят только из пробелов (редкий, но возможный случай).
    cleaned_chunks = [chunk.strip() for chunk in chunks if chunk.strip()]

    return cleaned_chunks

def load_knowledge_base():
    """
    Загружает все поддерживаемые файлы (.txt и .pdf) из папки knowledge_files
    и добавляет их в векторную базу данных.

    Запускать нужно ОДИН РАЗ или после обновления файлов.
    """

    # Проверяем, есть ли уже данные в базе
    if collection.count() > 0:
        print(f"База знаний уже загружена: {collection.count()} фрагментов")
        return

    # Создаём папку, если её нет
    if not os.path.exists(KNOWLEDGE_DIR):
        os.makedirs(KNOWLEDGE_DIR)
        print(f"Создана папка '{KNOWLEDGE_DIR}'. Положи туда .txt или .pdf файлы")
        return

    all_chunks = []
    all_ids = []
    all_metadata = []
    chunk_counter = 0

    # Получаем список файлов
    files = os.listdir(KNOWLEDGE_DIR)
    pdf_found = False  # Флаг для подсказки об установке PyMuPDF

    for filename in files:
        filepath = os.path.join(KNOWLEDGE_DIR, filename)
        ext = os.path.splitext(filename)[1].lower()

        # Пропускаем файлы, которые не можем обработать
        if ext not in (".txt", ".pdf"):
            continue

        # Проверяем, не PDF ли это, и если да, то есть ли библиотека
        if ext == ".pdf":
            pdf_found = True
            try:
                text = extract_text_from_pdf(filepath)
            except ImportError as e:
                print(f"⚠️  {e}. PDF-файл '{filename}' пропущен.")
                continue
            except Exception as e:
                print(f"❌ Ошибка при чтении PDF '{filename}': {e}")
                continue
        else:  # .txt
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()

        # Если текст пустой, пропускаем файл
        if not text.strip():
            print(f"⚠️  Файл '{filename}' не содержит текста, пропущен.")
            continue

        print(f"Загружаю файл: {filename}")
        chunks = split_text_into_chunks(text)

        for i, chunk in enumerate(chunks):
            chunk_counter += 1
            all_chunks.append(chunk)
            all_ids.append(f"chunk_{chunk_counter}")
            all_metadata.append({
                "source": filename,
                "chunk_index": i
            })

    if not all_chunks:
        if pdf_found and not any(os.path.splitext(f)[1].lower() == ".txt" for f in files):
            print("Не удалось загрузить ни одного PDF-файла. Убедитесь, что установлен PyMuPDF.")
        else:
            print("Не найдено подходящих файлов (.txt или .pdf) в папке knowledge_files/")
        return

    # При добавлении ChromaDB автоматически использует встроенную функцию эмбеддинга
    # (по умолчанию all-MiniLM-L6-v2 через sentence-transformers),
    # чтобы превратить текст из all_chunks в векторы и сохранить их
    collection.add(
        documents=all_chunks,
        ids=all_ids,
        metadatas=all_metadata
    )

    print(f"Загружено {len(all_chunks)} фрагментов из обработанных файлов")


