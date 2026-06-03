import json, os
from db import get_connection, put_connection
from repositories import  hierarchy_repo
from display_hierarchy import show as display_hierarchy
from repositories.subproblems_repo import get_root_problems
from repositories.hierarchy_by_root import get_hierarchy_for_root, get_hierarchy_by_macro_id
from repositories.hierarchy_recursive import get_hierarchy_for_root_recursive, get_hierarchy_by_macro_id_recursive


def full_hierarchy():
    """Показать полную иерархию из БД."""
    hierarchy = hierarchy_repo.get_full_hierarchy()
    display_hierarchy(hierarchy, save_json=True)  # выведет в консоль и сохранит в JSON


def list_roots():
    """Вывод всех корневых проблем."""
    roots = get_root_problems()
    if not roots:
        print("Корневые проблемы отсутствуют.")
        return

    # Заголовок таблицы – печатается заголовок с тремя колонками, разделёнными пробелами
    print("\n=== Список корневых проблем ===")
    print(f"{'db_id':<6} {'macro_id':<12} {'sbj (субъект)':<20}")
    # Например, строка 'db_id' выравнивается влево в поле шириной 6 символов (знак <).
    # Если название короче, остальное место заполняется пробелами справа
    print("-" * 45)
    for r in roots:
        sbj = r['macro_model'].get('sbj', '?') if r['macro_model'] else '?'
        print(f"{r['id']:<6} {r['macro_id']:<12} {sbj:<20}")


def show_hierarchy_by_db_id():
    """Запрашивает db_id и выводит иерархию."""
    raw = input("Введите db_id корневой проблемы (число): ").strip()
    if not raw.isdigit():
        print("Ошибка: db_id должен быть целым числом.")
        return
    db_id = int(raw)
    hierarchy = get_hierarchy_for_root(db_id)
    if hierarchy is None:
        print(f"Проблема с db_id={db_id} не найдена.")
        return
    print(f"\n=== Иерархия для корневой проблемы db_id={db_id} ===")
    display_hierarchy([hierarchy], save_json=False)


def show_hierarchy_by_macro_id():
    """Запрашивает макромодельный идентификатор и выводит иерархию."""
    macro_id = input("Введите макромодельный идентификатор (например, P1): ").strip()
    if not macro_id:
        print("Ошибка: идентификатор не может быть пустым.")
        return
    hierarchy = get_hierarchy_by_macro_id(macro_id)
    if hierarchy is None:
        print(f"Корневая проблема с macro_id='{macro_id}' не найдена.")
        return
    print(f"\n=== Иерархия для корневой проблемы macro_id='{macro_id}' ===")
    display_hierarchy([hierarchy], save_json=False)


def show_hierarchy_recursive_by_db_id():
    raw = input("Введите db_id корневой проблемы (число): ").strip()
    if not raw.isdigit():
        print("Ошибка: db_id должен быть целым числом.")
        return
    db_id = int(raw)
    hierarchy = get_hierarchy_for_root_recursive(db_id)
    if hierarchy is None:
        print(f"Проблема с db_id={db_id} не найдена.")
        return
    print(f"\n=== Иерархия (рекурсивный CTE) для корневой проблемы db_id={db_id} ===")
    display_hierarchy([hierarchy], save_json=False)


def show_hierarchy_recursive_by_macro_id():
    macro_id = input("Введите макромодельный идентификатор (например, P1): ").strip()
    if not macro_id:
        print("Ошибка: идентификатор не может быть пустым.")
        return
    hierarchy = get_hierarchy_by_macro_id_recursive(macro_id)
    if hierarchy is None:
        print(f"Корневая проблема с macro_id='{macro_id}' не найдена.")
        return
    print(f"\n=== Иерархия (рекурсивный CTE) для корневой проблемы macro_id='{macro_id}' ===")
    display_hierarchy([hierarchy], save_json=False)


def load_problems_lowconfident(filepath: str = "low_confidence_problems.json") -> list[dict]:
    """
    Выбирает из БД все подпроблемы с низкой уверенностью верификации
    (confidence_micro = 'low' ИЛИ confidence_macro = 'low').

    - Выводит их на консоль в удобочитаемом формате.
    - Сохраняет в JSON‑файл.
    - Возвращает список найденных записей (словарей).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "parent_id", "macro_model", "micro_model",
                       "confidence_macro", "reasoning_macro",
                       "confidence_micro", "reasoning_micro"
                FROM "subproblems"
                WHERE "confidence_micro" = 'low' OR "confidence_macro" = 'low'
                ORDER BY "id";
                """
            )
            rows = cur.fetchall()
            problems = []
            for r in rows:
                problems.append({
                    "id": r[0],
                    "parent_id": r[1],
                    "macro_model": r[2],
                    "micro_model": r[3],
                    "confidence_macro": r[4],
                    "reasoning_macro": r[5],
                    "confidence_micro": r[6],
                    "reasoning_micro": r[7],
                })
    finally:
        put_connection(conn)

    # Вывод на консоль
    if not problems:
        print("Проблем с низкой уверенностью не найдено.")
    else:
        print(f"Найдено {len(problems)} проблем(ы) с низкой уверенностью:\n")
        for p in problems:
            print(f"ID: {p['id']}")
            print(f"Родительский ID: {p['parent_id']}")
            print(f"Макромодель: {json.dumps(p['macro_model'], ensure_ascii=False, indent=2)}")
            print(f"Микромодель: {json.dumps(p['micro_model'], ensure_ascii=False, indent=2)}")
            print(f"Confidence macro: {p['confidence_macro']}")
            print(f"Reasoning macro: {p['reasoning_macro']}")
            print(f"Confidence micro: {p['confidence_micro']}")
            print(f"Reasoning micro: {p['reasoning_micro']}")
            print("-" * 60)

    # Сохранение в файл
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(problems, f, ensure_ascii=False, indent=2)
    print(f"Данные сохранены в файл: {os.path.abspath(filepath)}")

    return problems