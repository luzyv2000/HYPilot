# Dateiname:     ingestion/updater.py
# Version:       2026-04-20
# Abhängigkeiten (intern): ingestion.parser
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
ingestion/updater.py

Importiert geparste Instrument-Datensätze in die SQLite-Datenbank.
Bestehende ISINs werden übersprungen (INSERT OR IGNORE).

Gibt die Anzahl neu eingefügter Datensätze zurück — dieser Wert
wird von run_update.py geloggt.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from ingestion.parser import InstrumentRecord, parse_pdf

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Datenbankoperationen ──────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")   # bessere Concurrency
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def _insert_instruments(
    conn: sqlite3.Connection,
    instruments: list[InstrumentRecord],
) -> int:
    """
    Fügt Datensätze ein. Bereits vorhandene ISINs werden ignoriert.

    Returns:
        Anzahl neu eingefügter Zeilen.
    """
    cursor = conn.cursor()
    new_count = 0

    for item in instruments:
        cursor.execute(
            """
            INSERT OR IGNORE INTO instruments (name, isin, wkn)
            VALUES (?, ?, ?)
            """,
            (item["name"], item["isin"], item["wkn"]),
        )
        new_count += cursor.rowcount  # 1 wenn eingefügt, 0 wenn ignoriert

    conn.commit()
    return new_count


# ── Öffentliche API ───────────────────────────────────────────────────────────

def run(db_path: Path = DB_PATH) -> int:
    """
    Führt den vollständigen Import durch: PDF parsen → DB aktualisieren.

    Returns:
        Anzahl neu eingefügter Instrumente.

    Raises:
        Exception: Bei Datenbankfehlern oder PDF-Parsing-Fehlern.
    """
    logger.info("Starte DB-Update.")

    instruments = parse_pdf()
    logger.info("%d Einträge aus Parser erhalten.", len(instruments))

    with _get_connection(db_path) as conn:
        new_count = _insert_instruments(conn, instruments)

    logger.info("%d neue Einträge in DB eingefügt.", new_count)
    return new_count


# ── CLI-Einstiegspunkt ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    count = run()
    print(f"Fertig. {count} neue Einträge.")
    sys.exit(0)