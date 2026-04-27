# Dateiname:     core/universe_service.py
# Version:       2026-04-27
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
core/universe_service.py

Lesende Zugriffsschicht auf das Instrument-Universum (instruments-Tabelle).

Alle Funktionen akzeptieren db_path als Parameter — ermöglicht
testbaren Betrieb gegen temporäre Datenbanken ohne Produktionsdaten.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_all_instruments(
    limit: int | None = None,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """
    Gibt alle Instrumente zurück, alphabetisch nach Name sortiert.

    Args:
        limit:   Maximale Anzahl Einträge (None = alle).
        db_path: Pfad zur SQLite-DB.

    Returns:
        Liste von Dicts mit 'name', 'isin', 'wkn'.
    """
    query = """
        SELECT COALESCE(name_override, name) AS name, isin, wkn
        FROM instruments
        ORDER BY name ASC
    """
    if limit:
        query += f" LIMIT {limit}"

    with _get_connection(db_path) as conn:
        rows = conn.execute(query).fetchall()

    return [{"name": r["name"], "isin": r["isin"], "wkn": r["wkn"]}
            for r in rows]


def search_instruments(
    query_str: str,
    db_path: Path = DB_PATH,
) -> list[dict]:
    """
    Sucht Instrumente nach Name oder ISIN (Teilstring, case-insensitiv).

    Args:
        query_str: Suchbegriff.
        db_path:   Pfad zur SQLite-DB.

    Returns:
        Bis zu 50 Treffer, alphabetisch sortiert.
    """
    sql = """
        SELECT COALESCE(name_override, name) AS name, isin, wkn
        FROM instruments
        WHERE name        LIKE ? COLLATE NOCASE
           OR name_override LIKE ? COLLATE NOCASE
           OR isin        LIKE ? COLLATE NOCASE
        ORDER BY name ASC
        LIMIT 50
    """
    pattern = f"%{query_str}%"

    with _get_connection(db_path) as conn:
        rows = conn.execute(sql, (pattern, pattern, pattern)).fetchall()

    return [{"name": r["name"], "isin": r["isin"], "wkn": r["wkn"]}
            for r in rows]


def get_by_isin(
    isin: str,
    db_path: Path = DB_PATH,
) -> dict | None:
    """
    Gibt ein einzelnes Instrument per ISIN zurück.

    Returns:
        Dict mit 'name', 'isin', 'wkn' oder None wenn nicht gefunden.
    """
    sql = """
        SELECT COALESCE(name_override, name) AS name, isin, wkn
        FROM instruments
        WHERE isin = ?
    """
    with _get_connection(db_path) as conn:
        row = conn.execute(sql, (isin,)).fetchone()

    if not row:
        return None
    return {"name": row["name"], "isin": row["isin"], "wkn": row["wkn"]}
