from db import get_connection, put_connection

def add_relname(name: str, relclass_id: int, description: str = None) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO relName (name, id_relClass, descriptionRel) VALUES (%s, %s, %s) RETURNING id_relName;",
                (name, relclass_id, description)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        put_connection(conn)

def get_relname(relname_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id_relName, name, id_relClass, descriptionRel FROM relName WHERE id_relName = %s;",
                (relname_id,)
            )
            row = cur.fetchone()
            return {"id": row[0], "name": row[1], "relclass_id": row[2], "description": row[3]} if row else None
    finally:
        put_connection(conn)

def update_relname(relname_id: int, name: str = None, relclass_id: int = None, description: str = None) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            fields = []
            values = []
            if name is not None:
                fields.append("name = %s")
                values.append(name)
            if relclass_id is not None:
                fields.append("id_relClass = %s")
                values.append(relclass_id)
            if description is not None:
                fields.append("descriptionRel = %s")
                values.append(description)
            if not fields:
                return False
            values.append(relname_id)
            cur.execute(
                f"UPDATE relName SET {', '.join(fields)} WHERE id_relName = %s;",
                values
            )
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)

def delete_relname(relname_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM relName WHERE id_relName = %s;", (relname_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)