import sqlite3
from pathlib import Path
from ingestion.parser import parse_pdf


DB_PATH = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def insert_instruments(conn, instruments):
    cursor = conn.cursor()

    new_count = 0

    for item in instruments:
        try:
            cursor.execute("""
                INSERT INTO instruments (name, isin, wkn)
                VALUES (?, ?, ?)
            """, (item["name"], item["isin"], item["wkn"]))

            new_count += 1

        except sqlite3.IntegrityError:
            # ISIN existiert bereits → skip
            continue

    conn.commit()

    return new_count


def main():
    print("[INFO] Starte DB-Update...")

    conn = get_connection()

    try:
        instruments = parse_pdf()

        print(f"[INFO] {len(instruments)} Einträge aus Parser erhalten")

        new_entries = insert_instruments(conn, instruments)

        print(f"[INFO] {new_entries} neue Einträge in DB eingefügt")

    except Exception as e:
        print(f"[ERROR] Update fehlgeschlagen: {e}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
