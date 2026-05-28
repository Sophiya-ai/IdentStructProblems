"""
Модуль для сбора иерархии проблем и их связей от одной корневой проблемы.
Использует общую функцию get_full_hierarchy из hierarchy_repo и фильтрует поддерево.
"""
from repositories.hierarchy_repo import get_full_hierarchy
from repositories.subproblems_repo import get_root_problems

def find_node_by_db_id(nodes: list[dict], target_db_id: int) -> dict | None:
    """
    Рекурсивный поиск узла с заданным db_id в дереве.
    """
    for node in nodes:
        if node['db_id'] == target_db_id:
            return node
        if node['children']:
            found = find_node_by_db_id(node['children'], target_db_id)
            if found:
                return found
    return None

def get_hierarchy_for_root(root_db_id: int) -> dict | None:
    """
    Возвращает корневой узел поддерева с указанным техническим id.
    Узел содержит всё дерево потомков и их связи.
    Если проблема с таким id не найдена или не существует, возвращает None.
    """
    full_tree = get_full_hierarchy()
    return find_node_by_db_id(full_tree, root_db_id)

def get_hierarchy_by_macro_id(macro_id: str) -> dict | None:
    """
    Удобная обёртка: сначала находит корневую проблему по её macro_model->>'id',
    затем возвращает полное поддерево.
    """
    roots = get_root_problems()
    target_root = next((r for r in roots if r['macro_id'] == macro_id), None)
    if target_root is None:
        return None
    return get_hierarchy_for_root(target_root['id'])