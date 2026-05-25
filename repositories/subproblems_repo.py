import json
from db import get_connection, put_connection

def add_subproblem(parent_id: int | None, macro_model: dict, micro_model: dict) -> int:
    """Добавить подпроблему. Возвращает id новой записи."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subproblems (parent_id, macro_model, micro_model)
                VALUES (%s, %s, %s)
                RETURNING id;
                """,
                (parent_id, json.dumps(macro_model), json.dumps(micro_model))
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        put_connection(conn)

def get_subproblem(problem_id: int) -> dict | None:
    """Получить подпроблему по id."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, parent_id, macro_model, micro_model FROM subproblems WHERE id = %s;",
                (problem_id,)
            )
            row = cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "parent_id": row[1],
                    "macro_model": row[2],      # psycopg2 автоматически преобразует JSONB в dict
                    "micro_model": row[3]
                }
            return None
    finally:
        put_connection(conn)

def update_subproblem(problem_id: int, macro_model: dict = None, micro_model: dict = None,
                      parent_id: int = None) -> bool:
    """Обновить данные подпроблемы. Передаются только изменяемые поля."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fields = []
            values = []
            if macro_model is not None:
                fields.append("macro_model = %s")
                values.append(json.dumps(macro_model))
            if micro_model is not None:
                fields.append("micro_model = %s")
                values.append(json.dumps(micro_model))
            if parent_id is not None:
                fields.append("parent_id = %s")
                values.append(parent_id)
            if not fields:
                return False
            values.append(problem_id)
            cur.execute(
                f"UPDATE subproblems SET {', '.join(fields)} WHERE id = %s;",
                values
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)

def delete_subproblem(problem_id: int) -> bool:
    """Удалить подпроблему (каскадно удалятся дочерние и связи)."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM subproblems WHERE id = %s;", (problem_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)

def search_by_name(search_term: str) -> list[dict]:
    """
    Поиск подпроблем по наименованию (ищет в macro_model->>'sbj' и macro_model->>'sit').
    Используется ILIKE для нечувствительности к регистру.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            pattern = f"%{search_term}%"
            cur.execute(
                """
                SELECT id, parent_id, macro_model, micro_model
                FROM subproblems
                WHERE macro_model->>'sbj' ILIKE %s
                   OR macro_model->>'sit' ILIKE %s;
                """,
                (pattern, pattern)
            )
            rows = cur.fetchall()
            return [
                {"id": r[0], "parent_id": r[1], "macro_model": r[2], "micro_model": r[3]}
                for r in rows
            ]
    finally:
        put_connection(conn)