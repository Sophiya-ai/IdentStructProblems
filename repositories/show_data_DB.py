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