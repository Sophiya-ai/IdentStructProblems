import json
from typing import Any

from db import get_connection, put_connection


def add_subproblem(
        parent_id: int | None,
        macro_model: dict,
        micro_model: dict,
        confidence: dict | None = None,  # {"conf_macro": ..., "conf_micro": ..., "conf_prbfld": ...}
        reasoning: dict | None = None    # {"reas_macro": ..., "reas_micro": ..., "reas_prbfld": ...}
) -> int:
    print(">>> add_subproblem started", flush=True)
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1. Явно преобразуем словари в JSON-строки.
            # Если словарь есть, делаем dumps. Если нет — передаем None (будет SQL NULL).
            macro_json = json.dumps(macro_model) if macro_model is not None else None
            micro_json = json.dumps(micro_model) if micro_model is not None else None
            conf_json = json.dumps(confidence) if confidence is not None else None
            reas_json = json.dumps(reasoning) if reasoning is not None else None

            # --- ВРЕМЕННЫЙ PRINT ДЛЯ ОТЛАДКИ ---
            # print("\n[DEBUG] Отправляем в БД:", flush=True)
            # print(f"  confidence JSON: {conf_json}", flush=True)
            # print(f"  reasoning JSON:  {reas_json}\n", flush=True)
            # -----------------------------------

            # 2. Добавляем ::jsonb к параметрам, чтобы PostgreSQL ГАРАНТИРОВАННО
            # воспринял строку как JSON-объект, а не как обычный текст или NULL.
            cur.execute(
                """
                INSERT INTO "subproblems" 
                    ("parent_id", "macro_model", "micro_model", "confidence", "reasoning")
                VALUES (%s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                RETURNING "id";
                """,
                (parent_id, macro_json, micro_json, conf_json, reas_json)
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
                       "confidence", "reasoning"
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
                    "confidence": row[4],
                    "reasoning": row[5],
                }
            return None
    finally:
        put_connection(conn)


def update_subproblem(
        problem_id: int,
        macro_model: dict | None = None,
        micro_model: dict | None = None,
        parent_id: int | None = None,
        confidence: dict | None = None,
        reasoning: dict | None = None
) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fields = []
            values = []

            # Добавляем ::jsonb для всех полей, которые хранятся как JSONB в БД
            if macro_model is not None:
                fields.append('"macro_model" = %s::jsonb')
                values.append(json.dumps(macro_model))

            if micro_model is not None:
                fields.append('"micro_model" = %s::jsonb')
                values.append(json.dumps(micro_model))

            # parent_id остается обычным %s, так как это целое число (integer)
            if parent_id is not None:
                fields.append('"parent_id" = %s')
                values.append(parent_id)

            if confidence is not None:
                fields.append('"confidence" = %s::jsonb')
                values.append(json.dumps(confidence))

            if reasoning is not None:
                fields.append('"reasoning" = %s::jsonb')
                values.append(json.dumps(reasoning))

            # Если ни одно поле не передано для обновления, выходим
            if not fields:
                return False

            values.append(problem_id)

            # Формируем и выполняем запрос
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
                       "confidence", "reasoning"
                FROM "subproblems"
                WHERE "macro_model"->>'sbj' ILIKE %s
                   OR "macro_model"->>'sit' ILIKE %s;
                """,
                (pattern, pattern)
            )
            return [
                {
                    "id": r[0],
                    "parent_id": r[1],
                    "macro_model": r[2],
                    "micro_model": r[3],
                    "confidence": r[4],
                    "reasoning": r[5],
                }
                for r in cur.fetchall()
            ]
    finally:
        put_connection(conn)


def get_root_problems() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "macro_model", "confidence", "reasoning"
                FROM "subproblems"
                WHERE "parent_id" IS NULL
                ORDER BY "id";
                """
            )
            result = []
            for r in cur.fetchall():
                db_id = r[0]
                macro = r[1]
                # Защитная проверка: если macro почему-то None, используем db_id
                macro_id = macro.get('id', str(db_id)) if isinstance(macro, dict) else str(db_id)
                result.append({
                    "id": db_id,
                    "macro_id": macro_id,
                    "macro_model": macro,
                    "confidence": r[2],
                    "reasoning": r[3],
                })
            return result
    finally:
        put_connection(conn)


def get_all_problems_light() -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT "id", "parent_id", "macro_model"
                FROM "subproblems"
                ORDER BY "id";
                """
            )
            return [
                {
                    "id": r[0],
                    "parent_id": r[1],
                    "macro_model": r[2]
                }
                for r in cur.fetchall()
            ]
    finally:
        put_connection(conn)


# Универсальная функция для обновления поля внутри JSONB-колонки
def _update_jsonb_field(problem_id: int, column_name: str, field: str, value: Any) -> bool:
    """
    Универсальная функция для обновления значения конкретного поля внутри указанного JSONB-столбца.
    Если целевой столбец равен NULL, он будет инициализирован пустым объектом {}.

    Аргументы:
        problem_id (int): техническое ID проблемы, которую нужно обновить.
        column_name (str): имя JSONB-столбца в таблице (например, 'micro_model', 'confidence', 'reasoning').
        field (str): название поля внутри JSON‑объекта, например 'sbjm', 'conf_macro', 'reas_integ'.
        value (Any): новое значение – может быть строкой, числом, словарём, списком
                     или None (будет записан как SQL NULL / JSON null).

    Возвращает:
        bool: True, если обновлена хотя бы одна строка, иначе False.
    """

    # Получаем соединение с БД из пула
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Преобразуем значение Python в JSON-строку.
            # Если value is None, передаем None напрямую,
            # чтобы драйвер (psycopg2) корректно записал SQL NULL, а не строку "null".
            json_value = json.dumps(value) if value is not None else None

            # Используем встроенные возможности PostgreSQL:
            # - jsonb_set(target_jsonb, path, new_value) – функция для изменения JSONB по указанному пути.
            # - COALESCE гарантирует, что если столбец равен NULL, мы начинаем с пустого объекта '{}'::jsonb.
            # - путь: '{имя_поля}' – это текстовый массив из одного элемента.
            #   Мы формируем его через f'{{{field}}}', что даст, например, '{sbj}' или '{conf_macro}'.
            # - новое значение приводится к типу jsonb через ::jsonb.
            cur.execute(
                f"""
                UPDATE "subproblems"
                SET "{column_name}" = jsonb_set(
                    COALESCE("{column_name}", '{{}}'::jsonb),
                    %s,
                    %s::jsonb
                )
                WHERE "id" = %s;
                """,
                (f'{{{field}}}', json_value, problem_id)
            )

            # Фиксируем транзакцию
            conn.commit()

            # Возвращаем True, если запись с таким id найдена и действительно обновлена
            return cur.rowcount > 0
    finally:
        put_connection(conn)


# --- Обертки для обновления полей ---

def set_micro_model_field(problem_id: int, field: str, value: Any) -> bool:
    """Устанавливает значение поля внутри JSONB-столбца micro_model."""
    return _update_jsonb_field(problem_id, "micro_model", field, value)


def set_confidence_field(problem_id: int, field: str, value: Any) -> bool:
    """Устанавливает значение поля внутри JSONB-столбца confidence."""
    return _update_jsonb_field(problem_id, "confidence", field, value)


def set_reasoning_field(problem_id: int, field: str, value: Any) -> bool:
    """Устанавливает значение поля внутри JSONB-столбца reasoning."""
    return _update_jsonb_field(problem_id, "reasoning", field, value)