from db import close_all, get_connection, put_connection
from repositories import subproblems_repo, relclass_repo, relname_repo, problem_rels_repo, hierarchy_repo
from display_hierarchy import show as display_hierarchy

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

def demo_hierarchy():
    """Показать иерархию из БД."""
    hierarchy = hierarchy_repo.get_full_hierarchy()
    display_hierarchy(hierarchy, save_json=True)  # выведет в консоль и сохранит в JSON

if __name__ == "__main__":
    # Сначала можно заполнить БД (если нужно)
    # fill_demo_data()

    # Показать иерархию
    demo_hierarchy()

    close_all()