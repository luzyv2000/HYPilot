# Dateiname:     db/watchlist_repository.py
# Version:       2026-05-10
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/watchlist_repository.py

CRUD-Operationen für die watchlist-Tabelle.

Einzige Stelle im Projekt die direkt auf watchlist schreibt.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


@dataclass
class WatchlistEntry:
    isin:     str
    name:     str          # COALESCE(name_override, name)
    wkn:      str | None
    notes:    str
    added_at: str          # ISO-Timestamp


# ── Verbindung ────────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ── Schreiboperationen ────────────────────────────────────────────────────────

def add_to_watchlist(
    isin: str,
    notes: str = "",
    db_path: Path = DB_PATH,
) -> bool:
    """
    Fügt ISIN zur Watchlist hinzu.

    Returns:
        True wenn neu hinzugefügt, False wenn bereits vorhanden.
    """
    try:
        with _get_connection(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO watchlist (isin, notes, added_at)
                VALUES (?, ?, ?)
                """,
                (isin, notes.strip(), datetime.now().isoformat()),
            )
            conn.commit()
            added = cursor.rowcount > 0
    except sqlite3.Error:
        logger.exception("Fehler beim Hinzufügen zur Watchlist: %s", isin)
        return False

    if added:
        logger.info("Watchlist: %s hinzugefügt.", isin)
    else:
        logger.debug("Watchlist: %s bereits vorhanden.", isin)
    return added


def remove_from_watchlist(
    isin: str,
    db_path: Path = DB_PATH,
) -> bool:
    """
    Entfernt ISIN aus der Watchlist.

    Returns:
        True wenn entfernt, False wenn nicht gefunden.
    """
    try:
        with _get_connection(db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM watchlist WHERE isin = ?", (isin,)
            )
            conn.commit()
            removed = cursor.rowcount > 0
    except sqlite3.Error:
        logger.exception("Fehler beim Entfernen aus Watchlist: %s", isin)
        return False

    if removed:
        logger.info("Watchlist: %s entfernt.", isin)
    return removed


def update_notes(
    isin: str,
    notes: str,
    db_path: Path = DB_PATH,
) -> None:
    """Aktualisiert den Notiztext für einen Watchlist-Eintrag."""
    with _get_connection(db_path) as conn:
        conn.execute(
            "UPDATE watchlist SET notes = ? WHERE isin = ?",
            (notes.strip(), isin),
        )
        conn.commit()
    logger.debug("Watchlist-Notiz aktualisiert: %s", isin)


# ── Leseoperationen ───────────────────────────────────────────────────────────

def get_watchlist(db_path: Path = DB_PATH) -> list[WatchlistEntry]:
    """Gibt alle Watchlist-Einträge zurück, sortiert nach Hinzufügedatum."""
    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    w.isin,
                    COALESCE(i.name_override, i.name) AS name,
                    COALESCE(i.wkn, '')               AS wkn,
                    w.notes,
                    w.added_at
                FROM watchlist w
                JOIN instruments i ON i.isin = w.isin
                ORDER BY w.added_at DESC
                """,
            ).fetchall()
    except sqlite3.Error:
        logger.exception("Fehler beim Laden der Watchlist.")
        return []

    return [
        WatchlistEntry(
            isin=row["isin"],
            name=row["name"],
            wkn=row["wkn"] or None,
            notes=row["notes"],
            added_at=row["added_at"],
        )
        for row in rows
    ]


def is_on_watchlist(isin: str, db_path: Path = DB_PATH) -> bool:
    """Prüft ob eine ISIN auf der Watchlist ist."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM watchlist WHERE isin = ?", (isin,)
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def count_watchlist(db_path: Path = DB_PATH) -> int:
    """Anzahl der Watchlist-Einträge."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM watchlist"
            ).fetchone()
        return row["cnt"] if row else 0
    except sqlite3.Error:
        return 0