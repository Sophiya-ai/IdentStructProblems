import json
from db import get_connection, put_connection

def add_subproblem(
    parent_id: int | None,
    macro_model: dict,
    micro_model: dict,
    confidence_macro: str | None = None,      # None или 'low'
    reasoning_macro: str | None = None,
    confidence_micro: str | None = None,      # None или 'low'
    reasoning_micro: str | None = None
) -> int:
    """
    Добавляет новую подпроблему.
    confidence_* – None (норма) или 'low' (низкая уверенность).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "subproblems" 
                    ("parent_id", "macro_model", "micro_model", 
                     "confidence_macro", "reasoning_macro", 
                     "confidence_micro", "reasoning_micro")
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING "id";
                """,
                (
                    parent_id,
                    json.dumps(macro_model),
                    json.dumps(micro_model),
                    confidence_macro,          # строка или None
                    reasoning_macro,
                    confidence_micro,          # строка или None
                    reasoning_micro,
                )
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        put_connection(conn)


def get_subproblem(problem_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "parent_id", "macro_model", "micro_model",
                       "confidence_macro", "reasoning_macro",
                       "confidence_micro", "reasoning_micro"
                FROM "subproblems"
                WHERE "id" = %s;
                """,
                (problem_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "parent_id": row[1],
                    "macro_model": row[2],
                    "micro_model": row[3],
                    "confidence_macro": row[4],       # str или None
                    "reasoning_macro": row[5],
                    "confidence_micro": row[6],       # str или None
                    "reasoning_micro": row[7],
                }
            return None
    finally:
        put_connection(conn)


def update_subproblem(
    problem_id: int,
    macro_model: dict = None,
    micro_model: dict = None,
    parent_id: int = None,
    confidence_macro: str | None = None,    # 'low' или None
    reasoning_macro: str | None = None,
    confidence_micro: str | None = None,    # 'low' или None
    reasoning_micro: str | None = None
) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fields = []
            values = []

            if macro_model is not None:
                fields.append('"macro_model" = %s')
                values.append(json.dumps(macro_model))
            if micro_model is not None:
                fields.append('"micro_model" = %s')
                values.append(json.dumps(micro_model))
            if parent_id is not None:
                fields.append('"parent_id" = %s')
                values.append(parent_id)
            if confidence_macro is not None:
                fields.append('"confidence_macro" = %s')
                values.append(confidence_macro)
            if reasoning_macro is not None:
                fields.append('"reasoning_macro" = %s')
                values.append(reasoning_macro)
            if confidence_micro is not None:
                fields.append('"confidence_micro" = %s')
                values.append(confidence_micro)
            if reasoning_micro is not None:
                fields.append('"reasoning_micro" = %s')
                values.append(reasoning_micro)

            if not fields:
                return False

            values.append(problem_id)
            cur.execute(
                f'UPDATE "subproblems" SET {", ".join(fields)} WHERE "id" = %s;',
                values
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)


def delete_subproblem(problem_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "subproblems" WHERE "id" = %s;', (problem_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)


def search_by_name(search_term: str) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            pattern = f"%{search_term}%"
            cur.execute(
                """
                SELECT "id", "parent_id", "macro_model", "micro_model",
                       "confidence_macro", "reasoning_macro",
                       "confidence_micro", "reasoning_micro"
                FROM "subproblems"
                WHERE "macro_model"->>'sbj' ILIKE %s
                   OR "macro_model"->>'sit' ILIKE %s;
                """,
                (pattern, pattern)
            )
            rows = cur.fetchall()
            return [
                {
                    "id": r[0],
                    "parent_id": r[1],
                    "macro_model": r[2],
                    "micro_model": r[3],
                    "confidence_macro": r[4],
                    "reasoning_macro": r[5],
                    "confidence_micro": r[6],
                    "reasoning_micro": r[7],
                }
                for r in rows
            ]
    finally:
        put_connection(conn)


def get_root_problems() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "macro_model",
                       "confidence_macro", "reasoning_macro",
                       "confidence_micro", "reasoning_micro"
                FROM "subproblems"
                WHERE "parent_id" IS NULL
                ORDER BY "id";
                """
            )
            rows = cur.fetchall()
            result = []
            for r in rows:
                db_id = r[0]
                macro = r[1]
                macro_id = macro.get('id', str(db_id)) if macro else str(db_id)
                result.append({
                    "id": db_id,
                    "macro_id": macro_id,
                    "macro_model": macro,
                    "confidence_macro": r[2],
                    "reasoning_macro": r[3],
                    "confidence_micro": r[4],
                    "reasoning_micro": r[5],
                })
            return result
    finally:
        put_connection(conn)


def load_problems_lowconfident(filepath: str = "low_confidence_problems.json") -> list[dict]:
    """
    Выбирает из БД все подпроблемы с низкой уверенностью верификации
    (confidence_micro = 'low' ИЛИ confidence_macro = 'low').

    - Выводит их на консоль в удобочитаемом формате.
    - Сохраняет в JSON‑файл по указанному пути.
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