"""
retriever берёт коллекцию ChromaDB из этого модуля, не создавая новых клиентов,
и применяет встроенную функцию эмбеддинга (локальную), чтобы запросы были полностью совместимы с проиндексированными документами:
поиск выполняется через collection.query(query_texts=[query], ...), что гарантирует использование той же модели эмбеддингов,
которая применялась при индексации (по умолчанию all-MiniLM-L6-v2).
"""
import logging
from typing import List, Optional
# from dotenv import load_dotenv
#
# load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
from config import RETRIEVAL_ENABLED

# ---------------------------------------------------------------------------
# Класс-обёртка для поиска по уже созданной коллекции ChromaDB
# ---------------------------------------------------------------------------
class Retriever:
    """
    Предоставляет единый интерфейс для поиска релевантных документов
    в векторной базе знаний, которая была наполнена модулем knowledge_base.py.
    """
    def __init__(self, collection):
        """
        Принимает готовый объект коллекции ChromaDB.
        Предполагается, что коллекция уже инициализирована и использует
        ту же функцию эмбеддинга, что и при добавлении документов.
        """
        self.collection = collection
        self._count = self.collection.count()
        logger.info(f"Retriever подключён к коллекции '{collection.name}', документов: {self._count}")

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        """
        Возвращает список из top_k наиболее релевантных фрагментов документов.
        Использует встроенный механизм ChromaDB: передаёт текст запроса напрямую,
        чтобы коллекция сама сгенерировала эмбеддинг и выполнила поиск.
        """
        if self._count == 0:
            return []
        # query_texts запускает ту же embedding-функцию, что и при индексации
        results = self.collection.query(query_texts=[query], n_results=top_k)
        # Извлекаем сами документы (тексты чанков)
        documents = results.get('documents', [[]])[0]
        return documents

# ---------------------------------------------------------------------------
# Глобальный экземпляр Retriever (ленивая инициализация)
# ---------------------------------------------------------------------------
_retriever_instance: Optional[Retriever] = None

def get_retriever() -> Optional[Retriever]:
    """
    Возвращает объект Retriever, если RAG включён и база знаний не пуста.
    Использует коллекцию из knowledge_base.py.
    В противном случае возвращает None.
    """
    global _retriever_instance

    if not RETRIEVAL_ENABLED:
        logger.info("RAG отключён (RETRIEVAL_ENABLED=false).")
        return None

    if _retriever_instance is None:
        try:
            # Импортируем коллекцию, уже созданную в knowledge_base.py
            from knowledge_base import collection
            # Проверяем, что в коллекции есть хотя бы один документ
            if collection.count() == 0:
                logger.warning("Коллекция ChromaDB пуста. RAG-верификация недоступна.")
                return None
            _retriever_instance = Retriever(collection)
        except ImportError:
            logger.error("Модуль knowledge_base не найден.")
            return None
        except Exception as e:
            logger.error(f"Не удалось инициализировать retriever: {e}")
            return None

    return _retriever_instance