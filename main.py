"""
Консольное меню для работы с проектом identProblem.
Если в базе данных много проблем, полная загрузка всего дерева (пункты 2–3) может занять много памяти и времени.
Рекурсивный CTE (пункты 4–5) извлекает только нужное поддерево, что гораздо эффективнее.
"""

from db import close_all, get_connection, put_connection
from repositories import subproblems_repo, relclass_repo, relname_repo, problem_rels_repo, hierarchy_repo
from display_hierarchy import show as display_hierarchy
from repositories.subproblems_repo import get_root_problems
from repositories.hierarchy_by_root import get_hierarchy_for_root, get_hierarchy_by_macro_id
from index_manager import ensure_indexes
from repositories.hierarchy_recursive import get_hierarchy_for_root_recursive, get_hierarchy_by_macro_id_recursive
from knowledge_base import load_knowledge_base

def get_or_create_relclass(name, description):
    # Поиск существующего класса по имени (можно добавить функцию в репозиторий)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "id_relClass" FROM "relClass" WHERE "relClassName" = %s', (name,))
            row = cur.fetchone()
            if row:
                return row[0]
    finally:
        put_connection(conn)
    return relclass_repo.add_relclass(name, description)

def get_or_create_relname(name, relclass_id, description):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT "id_relName" FROM "relName" WHERE "name" = %s', (name,))
            row = cur.fetchone()
            if row:
                return row[0]
    finally:
        put_connection(conn)
    return relname_repo.add_relname(name, relclass_id, description)

def fill_demo_data():
    tax_class_id = get_or_create_relclass("Таксономические", "Иерархические связи")
    is_a_id = get_or_create_relname("is-a", tax_class_id, "Отношение класс-подкласс")

    macro_root = {"id": "P1", "sit": "Высокая текучесть кадров", "sbj": "HR-отдел", "est": "Критично"}
    micro_root = {"sitm": "...", "sbjm": "...", "STHM": "...", "pfmt": "...", "metm": ""}
    root_id = subproblems_repo.add_subproblem(None, macro_root, micro_root)

    macro_child = {"id": "P1.1", "sit": "Недостаток мотивации", "sbj": "HR-отдел", "est": "Высокая"}
    child_id = subproblems_repo.add_subproblem(root_id, macro_child, micro_root)

    problem_rels_repo.add_relationship(child_id, is_a_id, root_id, {"weight": 0.9})

    results = subproblems_repo.search_by_name("HR")
    for p in results:
        print(p["macro_model"]["sbj"], p["macro_model"]["sit"])

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

def menu():
    while True:
        print("\n" + "=" * 50)
        print("МЕНЮ РАБОТЫ С БАЗОЙ ДАННЫХ 'identProblem'")
        print("=" * 50)
        print("1. Вывести список корневых проблем")
        print("2. Показать иерархию по db_id (полная загрузка)")
        print("3. Показать иерархию по макромодельному id (полная загрузка)")
        print("4. Показать иерархию по db_id (рекурсивный CTE)")
        print("5. Показать иерархию по макромодельному id (рекурсивный CTE)")
        print("6. Загрузить файлы в векторную  БД")
        print("7. Выход")
        choice = input("Выберите пункт меню: ").strip()

        if choice == '1':
            list_roots()
        elif choice == '2':
            show_hierarchy_by_db_id()
        elif choice == '3':
            show_hierarchy_by_macro_id()
        elif choice == '4':
            show_hierarchy_recursive_by_db_id()
        elif choice == '5':
            show_hierarchy_recursive_by_macro_id()
        elif choice == '6':
            load_knowledge_base()
        elif choice == '7':
            print("Выход из программы.")
            break
        else:
            print("Неверный выбор. Пожалуйста, введите число от 1 до 6.")

if __name__ == "__main__":

# гарантирует наличие всех нужных индексов
    ensure_indexes()

# Сначала можно заполнить БД (если нужно)
    #fill_demo_data()

    # Показать всю иерархию
    full_hierarchy()

    menu()

    close_all()