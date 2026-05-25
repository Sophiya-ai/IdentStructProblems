import json
from db import get_connection, put_connection

def add_relationship(subject_id: int, relationship_id: int, object_id: int, metadata: dict = None) -> int:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO "problem_relationships" ("subject_id", "id_relationship", "object_id", "metadata")
                VALUES (%s, %s, %s, %s)
                RETURNING "id";
                """,
                (subject_id, relationship_id, object_id, json.dumps(metadata) if metadata else None)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
            return new_id
    finally:
        put_connection(conn)

def get_relationship(rel_id: int) -> dict | None:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "id", "subject_id", "id_relationship", "object_id", "metadata" FROM "problem_relationships" WHERE "id" = %s;',
                (rel_id,)
            )
            row = cur.fetchone()
            return {"id": row[0], "subject_id": row[1], "relationship_id": row[2],
                    "object_id": row[3], "metadata": row[4]} if row else None
    finally:
        put_connection(conn)

def delete_relationship(rel_id: int) -> bool:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM "problem_relationships" WHERE "id" = %s;', (rel_id,))
            conn.commit()
            return cur.rowcount > 0
    finally:
        put_connection(conn)

def find_relationships_for_problem(problem_id: int) -> list[dict]:
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT pr."id", pr."subject_id", pr."id_relationship", pr."object_id", pr."metadata",
                       rn."name" AS rel_name, rc."relClassName"
                FROM "problem_relationships" pr
                JOIN "relName" rn ON pr."id_relationship" = rn."id_relName"
                JOIN "relClass" rc ON rn."id_relClass" = rc."id_relClass"
                WHERE pr."subject_id" = %s OR pr."object_id" = %s;
                """,
                (problem_id, problem_id)
            )
            rows = cur.fetchall()
            return [
                {"id": r[0], "subject_id": r[1], "relationship_id": r[2], "object_id": r[3],
                 "metadata": r[4], "rel_name": r[5], "rel_class": r[6]}
                for r in rows
            ]
    finally:
        put_connection(conn)