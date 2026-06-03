"""
Консольное меню для работы с проектом identProblem.
Если в базе данных много проблем, полная загрузка всего дерева (пункты 2–3) может занять много памяти и времени.
Рекурсивный CTE (пункты 4–5) извлекает только нужное поддерево, что гораздо эффективнее.
"""
import json
from db import close_all, get_connection, put_connection
from repositories import subproblems_repo, relclass_repo, relname_repo, problem_rels_repo
from repositories.subproblems_repo import load_problems_lowconfident
from repositories.show_data_DB import (
    full_hierarchy,
    list_roots,
    show_hierarchy_by_db_id,
    show_hierarchy_by_macro_id,
    show_hierarchy_recursive_by_db_id,
    show_hierarchy_recursive_by_macro_id)
from index_manager import ensure_indexes
from knowledge_base import load_knowledge_base
from micro_model import generate_micro_model
from verification_universal import verify_micro_model
from macro_model import generate_macro_model

# ---------------------------------------------------------------------------
# Тестовое наполнение БД, чтобы проверить ввод-вывод данных из нее
# ---------------------------------------------------------------------------
def get_or_create_relclass(name, description):
    # Поиск существующего класса по имени
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


# ---------------------------------------------------------------------------
# Консольное меню
# ---------------------------------------------------------------------------
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
        print("7. Идентификация проблемы")
        print("8. Просмотр проблем с низкой уверенностью.")
        print("9. Выход")
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
            print("\n=== Идентификация проблемы ===")
            macro, micro = generate_micro_model()
            print("\nМикроуровневая модель корневой проблемы сгенерирована:")
            print(json.dumps(micro, ensure_ascii=False, indent=2))

            # Верификация – сигнатура полностью совместима с предыдущей версией
            result = verify_micro_model(
                macro_model=macro,
                initial_micro=micro,
                use_rag=True,  # автоматически задействует retriever, если доступен
                num_samples=5,
                temperature=0.7,
                confidence_threshold=0.7
            )

            final_micro = result["final_micro"]
            confidence = result["confidence"]
            acceptable = result["acceptable"]
            reasoning = result["reasoning"]

            # Определяем уровень уверенности для сохранения
            micro_confidence = None if acceptable else "low"

            print(f"Итоговая уверенность: {confidence:.2f}")
            print(f"Микроуровневая модель корневой проблемы {'пригодна' if acceptable else 'требует доработки'}")

            if acceptable or True:  # даже если не прошла, можем сохранить с пометкой 'low'
                new_id = subproblems_repo.add_subproblem(
                    parent_id=None,
                    macro_model=macro,
                    micro_model=final_micro,
                    confidence_micro=micro_confidence,  # 'low' или None
                    reasoning_micro=reasoning
                )
                print(f"Корневая проблема сохранена с id = {new_id}")
        elif choice == '8':
            load_problems_lowconfident()
        elif choice == '9':
            print("Выход из программы.")
            break
        else:
            print("Неверный выбор. Пожалуйста, введите число от 1 до 8.")


if __name__ == "__main__":
    # гарантирует наличие всех нужных индексов
    ensure_indexes()

    # Сначала можно заполнить БД (если нужно)
    #fill_demo_data()

    # Показать всю иерархию
    full_hierarchy()

    menu()

    close_all()
