"""
Модуль для сбора иерархии проблем и их связей из БД.
Все имена таблиц и столбцов заключены в двойные кавычки.
"""
from db import get_connection, put_connection

def get_full_hierarchy() -> list[dict]:
    """
    Возвращает полную иерархию проблем в виде списка корневых узлов.
    Каждый узел содержит:
        - problem_id: идентификатор из макромодели (macro_model->>'id')
        - db_id: технический id записи в таблице subproblems
        - macro_model: полная макромодель (dict)
        - children: список дочерних узлов (та же структура)
        - relations: список связей (от данной проблемы к другим), где каждый элемент:
            - relationship_name: тип отношения (из relName.name)
            - relationship_class: класс отношения (из relClass.relClassName)
            - target_problem_id: идентификатор макромодели целевой проблемы
            - target_db_id: технический id целевой проблемы
            - metadata: дополнительные атрибуты связи (JSONB)
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1. Загружаем все проблемы
            cur.execute(
                'SELECT "id", "parent_id", "macro_model" FROM "subproblems" ORDER BY "id";'
            )
            problem_rows = cur.fetchall()

            # 2. Загружаем все связи с типами и классами отношений
            cur.execute(
                """
                SELECT 
                    pr."subject_id",
                    pr."object_id",
                    pr."metadata",
                    rn."name" AS rel_name,
                    rc."relClassName" AS rel_class
                FROM "problem_relationships" pr
                JOIN "relName" rn ON pr."id_relationship" = rn."id_relName"
                JOIN "relClass" rc ON rn."id_relClass" = rc."id_relClass"
                ORDER BY pr."subject_id", pr."object_id";
                """
            )
            relationship_rows = cur.fetchall()

    finally:
        put_connection(conn)

    # 3. Строим словари для быстрого доступа
    nodes_by_id: dict[int, dict] = {}
    parent_map: dict[int, int | None] = {}
    macro_ids: dict[int, str] = {}

    for row in problem_rows:
        db_id, parent, macro = row
        # Если в макромодели нет поля id, используем технический id как строку
        macro_id = macro.get('id', str(db_id)) if macro else str(db_id)
        node = {
            "problem_id": macro_id,
            "db_id": db_id,
            "macro_model": macro,
            "children": [],
            "relations": []
        }
        nodes_by_id[db_id] = node
        parent_map[db_id] = parent
        macro_ids[db_id] = macro_id

    # 4. Добавляем связи (problem_relationships)
    for subj, obj, metadata, rel_name, rel_class in relationship_rows:
        if subj not in nodes_by_id or obj not in nodes_by_id:
            continue
        rel_entry = {
            "relationship_name": rel_name,
            "relationship_class": rel_class,
            "target_problem_id": macro_ids[obj],
            "target_db_id": obj,
            "metadata": metadata
        }
        nodes_by_id[subj]["relations"].append(rel_entry)

    # 5. Формируем дерево
    roots = []
    for db_id, node in nodes_by_id.items():
        parent = parent_map[db_id]
        if parent is None:
            roots.append(node)
        else:
            if parent in nodes_by_id:
                nodes_by_id[parent]["children"].append(node)
            else:
                # битая ссылка — делаем корнем
                roots.append(node)

    return roots