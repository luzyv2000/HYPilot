import sqlite3
from pathlib import Path


DB_PATH = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


def create_connection():
    return sqlite3.connect(DB_PATH)


def create_tables(conn):
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS instruments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        isin TEXT NOT NULL UNIQUE,
        wkn TEXT,
        symbol TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # optional für spätere Erweiterung
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS metadata (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    conn.commit()


def main():
    print("Initialisiere Datenbank...")

    conn = create_connection()
    create_tables(conn)

    conn.close()

    print(f"Datenbank erstellt unter: {DB_PATH}")


if __name__ == "__main__":
    main()
