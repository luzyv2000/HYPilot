# Dateiname:     ingestion/updater.py
# Version:       2026-04-22-A
# Abhängigkeiten (intern): ingestion.parser, db.instrument_repository
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
ingestion/updater.py

Importiert geparste Instrument-Datensätze in die SQLite-Datenbank.

Namenslogik beim Update:
  - Neue ISIN          → INSERT (name aus PDF)
  - Bekannte ISIN,
    name_override gesetzt → kein Konflikt (Nutzer hat eigenen Namen)
  - Bekannte ISIN,
    PDF-Name ≠ aktueller Name,
    name_override nicht gesetzt → pending_name_changes-Eintrag
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from ingestion.parser import InstrumentRecord, parse_pdf
from db.instrument_repository import add_pending_name_change

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Datenbankoperationen ──────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _process_instruments(
    conn: sqlite3.Connection,
    instruments: list[InstrumentRecord],
    db_path: Path,
) -> tuple[int, int]:
    """
    Verarbeitet alle Datensätze aus dem Parser.

    Returns:
        (neue_eintraege, konflikte)
    """
    cursor = conn.cursor()
    new_count      = 0
    conflict_count = 0

    for item in instruments:
        # Prüfen ob ISIN bereits bekannt
        existing = cursor.execute(
            "SELECT name, name_override FROM instruments WHERE isin = ?",
            (item["isin"],),
        ).fetchone()

        if existing is None:
            # Neue ISIN → einfach einfügen
            cursor.execute(
                "INSERT OR IGNORE INTO instruments (name, isin, wkn) "
                "VALUES (?, ?, ?)",
                (item["name"], item["isin"], item["wkn"]),
            )
            new_count += cursor.rowcount

        else:
            # Bekannte ISIN — Namensvergleich
            name_override = existing["name_override"]
            name_db       = existing["name"]

            if name_override:
                # Nutzer hat eigenen Namen gesetzt → still ignorieren
                continue

            if item["name"] != name_db:
                # PDF liefert anderen Namen → Konflikt speichern
                add_pending_name_change(
                    isin=item["isin"],
                    name_current=name_db,
                    name_pdf=item["name"],
                    db_path=db_path,
                )
                conflict_count += 1

    conn.commit()
    return new_count, conflict_count


# ── Öffentliche API ───────────────────────────────────────────────────────────

def run(db_path: Path = DB_PATH) -> int:
    """
    Führt den vollständigen Import durch: PDF parsen → DB aktualisieren.

    Returns:
        Anzahl neu eingefügter Instrumente.
    """
    logger.info("Starte DB-Update.")

    instruments = parse_pdf()
    logger.info("%d Einträge aus Parser erhalten.", len(instruments))

    with _get_connection(db_path) as conn:
        new_count, conflicts = _process_instruments(conn, instruments, db_path)

    logger.info(
        "%d neue Einträge eingefügt, %d Namenskonflikte erkannt.",
        new_count, conflicts,
    )
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