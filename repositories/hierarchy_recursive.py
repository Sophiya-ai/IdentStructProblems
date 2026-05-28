"""
Модуль для сбора иерархии проблем с использованием рекурсивного CTE (WITH RECURSIVE).
Эффективен при больших объёмах данных.

Функция get_subtree_db_ids выполняет рекурсивный запрос, обходя иерархию от корня.
Индекс idx_subproblems_parent_id на parent_id ускоряет каждый шаг рекурсии.
Затем загружаются только те проблемы, чьи id попали в поддерево, и только связи, где один из концов принадлежит поддереву.
Индексы на subject_id и object_id в problem_relationships ускоряют фильтрацию связей.
"""
from db import get_connection, put_connection

def get_subtree_db_ids(root_db_id: int) -> list[int]:
    """
    Возвращает список всех db_id (технических id) в поддереве, начиная с root_db_id.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH RECURSIVE subtree AS (
                    SELECT "id"
                    FROM "subproblems"
                    WHERE "id" = %s
                    UNION ALL
                    SELECT s."id"
                    FROM "subproblems" s
                    JOIN subtree st ON s."parent_id" = st."id"
                )
                SELECT "id" FROM subtree;
                """,
                (root_db_id,)
            )
            return [row[0] for row in cur.fetchall()]
    finally:
        put_connection(conn)

def get_hierarchy_for_root_recursive(root_db_id: int) -> dict | None:
    """
    Возвращает полное поддерево (узел с детьми и связями) для заданного корневого db_id.
    Использует рекурсивный CTE для выборки узлов и отдельный запрос для связей.
    """
    # 1. Получить все id поддерева
    subtree_ids = get_subtree_db_ids(root_db_id)
    if not subtree_ids:
        return None

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 2. Загрузить все проблемы из поддерева
            cur.execute(
                'SELECT "id", "parent_id", "macro_model" FROM "subproblems" WHERE "id" = ANY(%s) ORDER BY "id";',
                (subtree_ids,)
            )
            problem_rows = cur.fetchall()

            # 3. Загрузить связи, где субъект или объект в поддереве
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
                WHERE pr."subject_id" = ANY(%s) OR pr."object_id" = ANY(%s)
                ORDER BY pr."subject_id", pr."object_id";
                """,
                (subtree_ids, subtree_ids)
            )
            relationship_rows = cur.fetchall()
    finally:
        put_connection(conn)

    # 4. Построение дерева в памяти (аналогично get_full_hierarchy, но только для поддерева)
    nodes_by_id: dict[int, dict] = {}
    parent_map: dict[int, int | None] = {}
    macro_ids: dict[int, str] = {}

    for row in problem_rows:
        db_id, parent, macro = row
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

    # Связи: добавляем только те, где оба конца внутри поддерева
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

    # Формируем дерево: корень — root_db_id
    root_node = nodes_by_id.get(root_db_id)
    if not root_node:
        return None

    for db_id, node in nodes_by_id.items():
        if db_id == root_db_id:
            continue
        parent = parent_map[db_id]
        if parent is not None and parent in nodes_by_id:
            nodes_by_id[parent]["children"].append(node)
        # Игнорируем узлы, у которых родитель не попал в поддерево (теоретически невозможно)

    return root_node


def get_hierarchy_by_macro_id_recursive(macro_id: str) -> dict | None:
    """
    Находит корневую проблему по macro_model->>'id' и возвращает её поддерево рекурсивно.
    """
    from repositories.subproblems_repo import get_root_problems
    roots = get_root_problems()
    target_root = next((r for r in roots if r['macro_id'] == macro_id), None)
    if target_root is None:
        return None
    return get_hierarchy_for_root_recursive(target_root['id'])