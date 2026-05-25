from db import get_connection, put_connection

def add_relclass(rel_class_name: str, description: str = None) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'INSERT INTO "relClass" ("relClassName", "descriptionRelClass") VALUES (%s, %s) RETURNING "id_relClass";',
                (rel_class_name, description)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        put_connection(conn)

def get_relclass(relclass_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "id_relClass", "relClassName", "descriptionRelClass" FROM "relClass" WHERE "id_relClass" = %s;',
                (relclass_id,)
            )
            row = cur.fetchone()
            return {"id": row[0], "name": row[1], "description": row[2]} if row else None
    finally:
        put_connection(conn)

def update_relclass(relclass_id: int, name: str = None, description: str = None) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fields = []
            values = []
            if name is not None:
                fields.append('"relClassName" = %s')
                values.append(name)
            if description is not None:
                fields.append('"descriptionRelClass" = %s')
                values.append(description)
            if not fields:
                return False
            values.append(relclass_id)
            cur.execute(
                f'UPDATE "relClass" SET {", ".join(fields)} WHERE "id_relClass" = %s;',
                values
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)

def delete_relclass(relclass_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "relClass" WHERE "id_relClass" = %s;', (relclass_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)