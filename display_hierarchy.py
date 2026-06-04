"""
Модуль для отображения иерархии проблем в консоли и сохранения в JSON.
"""

import json
from typing import List, Dict

def print_tree(nodes: List[Dict], indent: int = 0):
    """Рекурсивный вывод иерархии в читаемом виде."""
    for node in nodes:
        prefix = "  " * indent
        print(f"{prefix}Проблема: {node['problem_id']} (db_id={node['db_id']})")
        # Дополнительные связи (не иерархические)
        for rel in node.get('relations', []):
            print(f"{prefix}  -> {rel['relationship_name']} [{rel['relationship_class']}] "
                  f"к {rel['target_problem_id']} (db_id={rel['target_db_id']})")
        # Рекурсивный вывод дочерних проблем
        print_tree(node.get('children', []), indent + 1)

def save_to_json(hierarchy: List[Dict], filename: str = "hierarchy.json"):
    """Сохраняет иерархию в JSON-файл."""
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(hierarchy, f, ensure_ascii=False, indent=2, default=str)
    print(f"Иерархия сохранена в {filename}")

def show(hierarchy: List[Dict], save_json: bool = False, json_filename: str = "hierarchy.json"):
    """
    Основная функция отображения:
    - Выводит дерево в консоль.
    - При save_json=True сохраняет в файл.
    """
    if not hierarchy:
        print("Иерархия пуста. Заполните базу данных.")
        return
    print("=== Иерархия проблем ===")
    print_tree(hierarchy)
    if save_json:
        save_to_json(hierarchy, json_filename)