"""
Управление индексами базы данных identProblem.
Создаёт предусмотренные заранее индексы, если они ещё не существуют,
и предоставляет функции для их удаления.
Созданные индексы будут автоматически использоваться планировщиком PostgreSQL для ускорения тех операций,
которые присутствуют в запросах модулей проекта
"""
from db import get_connection, put_connection

INDEX_DEFINITIONS = {
    # Таблица subproblems:
        # - Индекс для ускорения обхода иерархии (parent_id) (в get_root_problems() – быстрое нахождение корневых проблем)
        # - GIN-индекс для поиска внутри macro_model (ILIKE, существование ключей, @>) – ускоряет извлечение текстовых значений из JSONB
        # - Индекс по конкретному ключу macro_model->>'id' (идентификатор макромодели)
        # - GIN для micro_model - быстрый поиск по полям микромодели
        # - GIN-индексы по macro_model на конкретные выражения с текстовым типом, напрямую ускоряющие ILIKE,
            # например в search_by_name (subproblems_repo.py)

    "idx_subproblems_parent_id": (
        'CREATE INDEX IF NOT EXISTS idx_subproblems_parent_id ON "subproblems" ("parent_id");'
    ),
    "idx_subproblems_macro_gin": (
        'CREATE INDEX IF NOT EXISTS idx_subproblems_macro_gin ON "subproblems" USING gin ("macro_model");'
    ),
    "idx_subproblems_macro_id": (
        'CREATE INDEX IF NOT EXISTS idx_subproblems_macro_id ON "subproblems" (("macro_model"->>\'id\'));'
    ),
    "idx_subproblems_micro_gin": (
        'CREATE INDEX IF NOT EXISTS idx_subproblems_micro_gin ON "subproblems" USING gin ("micro_model");'
    ),
    "idx_subproblems_macro_sbj_gin": (
        'CREATE INDEX idx_subproblems_macro_sbj_gin ON "subproblems" USING gin (("macro_model"->>\'sbj\') gin_trgm_ops);'
    ),
    "idx_subproblems_macro_sit_gin": (
        'CREATE INDEX idx_subproblems_macro_sit_gin ON "subproblems" USING gin (("macro_model"->>\'sit\') gin_trgm_ops);'
    ),
    # Таблица relName - индекс для ускорения JOIN по внешнему ключу id_relClass
    # Полезен, если надо будет получить все типы отношений, принадлежащие определённому классу,
    # или в отчётах, где нужно группировать/фильтровать по классу отношений
    "idx_relName_id_relClass": (
        'CREATE INDEX IF NOT EXISTS idx_relName_id_relClass ON "relName" ("id_relClass");'
    ),
    # Таблица problem_relationships - индекс для поиска всех связей конкретной проблемы (subject_id или object_id)
    # и составной индекс для полного соответствия (subject, relationship, object)
    "idx_problem_rels_subject": (
        'CREATE INDEX IF NOT EXISTS idx_problem_rels_subject ON "problem_relationships" ("subject_id");'
    ),
    "idx_problem_rels_object": (
        'CREATE INDEX IF NOT EXISTS idx_problem_rels_object ON "problem_relationships" ("object_id");'
    ),
    "idx_problem_rels_triple": (
        'CREATE INDEX IF NOT EXISTS idx_problem_rels_triple ON "problem_relationships" ("subject_id", "id_relationship", "object_id");'
    ),
}

def create_all_indexes():
    """Создать все индексы из конфигурации (если они ещё не существуют)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for name, sql in INDEX_DEFINITIONS.items():
                cur.execute(sql)
        conn.commit()
        print("Все индексы успешно созданы (или уже существовали).")
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при создании индексов: {e}")
    finally:
        put_connection(conn)

def drop_index(index_name: str):
    """Удалить конкретный индекс по имени."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f'DROP INDEX IF EXISTS "{index_name}";')
        conn.commit()
        print(f"Индекс {index_name} удалён.")
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при удалении индекса {index_name}: {e}")
    finally:
        put_connection(conn)

def drop_all_project_indexes():
    """Удалить все индексы, перечисленные в INDEX_DEFINITIONS."""
    for name in INDEX_DEFINITIONS:
        drop_index(name)

def list_project_indexes():
    """Показать состояние индексов проекта (существуют ли в БД)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for name in INDEX_DEFINITIONS:
                cur.execute(
                    "SELECT 1 FROM pg_indexes WHERE indexname = %s;",
                    (name,)
                )
                exists = cur.fetchone() is not None
                print(f"Индекс {name}: {'существует' if exists else 'отсутствует'}")
    finally:
        put_connection(conn)

# Для удобства можно добавить функцию, которая проверяет и создаёт недостающие
def ensure_indexes():
    """Проверить наличие индексов и создать отсутствующие."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            for name, sql in INDEX_DEFINITIONS.items():
                cur.execute("SELECT 1 FROM pg_indexes WHERE indexname = %s;", (name,))
                if cur.fetchone() is None:
                    cur.execute(sql)
                    print(f"Создан индекс {name}.")
                else:
                    print(f"Индекс {name} уже существует.")
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Ошибка при проверке/создании индексов: {e}")
    finally:
        put_connection(conn)