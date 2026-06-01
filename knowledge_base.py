import os
import chromadb

# Папка, где лежат текстовые и PDF-файлы с базой знаний
KNOWLEDGE_DIR = "knowledge_files"

# Инициализируем ChromaDB
chroma_client = chromadb.PersistentClient(path="./chroma_db")

# Создаём или открываем коллекцию
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
        import PyMuPDF as pymupdf
    except ImportError:
        raise ImportError(
            "Для работы с PDF установите PyMuPDF: pip install PyMuPDF"
        )

    doc = pymupdf.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def split_text_into_chunks(text: str, chunk_size: int = 500) -> list[str]:
    """
    Разбивает длинный текст на маленькие кусочки (чанки).
    Это нужно, потому что модель лучше работает с небольшими
    релевантными фрагментами, а не с огромным текстом целиком.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = ""

    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(current_chunk) + len(paragraph) + 2 <= chunk_size:
            current_chunk = f"{current_chunk}\n\n{paragraph}".strip()
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = paragraph

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


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

    collection.add(
        documents=all_chunks,
        ids=all_ids,
        metadatas=all_metadata
    )

    print(f"Загружено {len(all_chunks)} фрагментов из обработанных файлов")


