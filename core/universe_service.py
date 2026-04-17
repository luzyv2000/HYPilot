import sqlite3
from pathlib import Path

DB_PATH = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def get_all_instruments(limit=None):
    conn = get_connection()
    cursor = conn.cursor()

    query = "SELECT name, isin, wkn FROM instruments ORDER BY name ASC"

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    return [
        {"name": r[0], "isin": r[1], "wkn": r[2]}
        for r in rows
    ]


def search_instruments(query_str):
    conn = get_connection()
    cursor = conn.cursor()

    query = """
    SELECT name, isin, wkn FROM instruments
    WHERE name LIKE ?
    ORDER BY name ASC
    LIMIT 50
    """

    cursor.execute(query, (f"%{query_str}%",))
    rows = cursor.fetchall()
    conn.close()

    return [
        {"name": r[0], "isin": r[1], "wkn": r[2]}
        for r in rows
    ]


def get_by_isin(isin):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name, isin, wkn FROM instruments WHERE isin = ?",
        (isin,)
    )

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return {"name": row[0], "isin": row[1], "wkn": row[2]}
