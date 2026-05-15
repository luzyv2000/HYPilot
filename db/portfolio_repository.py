# Dateiname:     db/portfolio_repository.py
# Version:       2026-05-15
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/portfolio_repository.py

CRUD-Operationen für die portfolio-Tabelle.

Speicherformat:
  shares_micro    : INTEGER, 1_000_000 = 1 Anteil (unterstützt Bruchteile)
  buy_price_micro : INTEGER, Micro-Units der Kaufwährung (1 EUR = 1_000_000)

Pro ISIN genau eine Position (PRIMARY KEY = isin).
Mehrere Käufe → Anteile + Durchschnittskurs manuell pflegen.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Datenklasse ───────────────────────────────────────────────────────────────

@dataclass
class PortfolioEntry:
    """Eine gehaltene Position im Portfolio."""
    isin:            str
    name:            str            # COALESCE(name_override, name)
    wkn:             str | None
    shares_micro:    int            # 1_000_000 = 1 Anteil
    buy_price_micro: int | None     # Kaufkurs pro Anteil in Micro-Units
    currency:        str            # Kaufwährung
    notes:           str
    added_at:        str            # ISO-Timestamp


# ── Verbindung ────────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ── Schreiboperationen ────────────────────────────────────────────────────────

def add_position(
    isin:            str,
    shares_micro:    int,
    buy_price_micro: int | None = None,
    currency:        str        = "EUR",
    notes:           str        = "",
    db_path:         Path       = DB_PATH,
) -> bool:
    """
    Fügt eine neue Position zum Portfolio hinzu.

    Returns:
        True wenn neu hinzugefügt, False wenn ISIN bereits vorhanden.
    """
    try:
        with _get_connection(db_path) as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO portfolio
                    (isin, shares_micro, buy_price_micro, currency, notes, added_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (isin, shares_micro, buy_price_micro, currency,
                 notes.strip(), datetime.now().isoformat()),
            )
            conn.commit()
            added = cursor.rowcount > 0
    except sqlite3.Error:
        logger.exception("Fehler beim Hinzufügen zur Portfolio: %s", isin)
        return False

    if added:
        logger.info("Portfolio: %s hinzugefügt.", isin)
    else:
        logger.debug("Portfolio: %s bereits vorhanden.", isin)
    return added


def update_position(
    isin:            str,
    shares_micro:    int,
    buy_price_micro: int | None = None,
    currency:        str        = "EUR",
    notes:           str        = "",
    db_path:         Path       = DB_PATH,
) -> None:
    """Aktualisiert eine bestehende Position (Anteile, Kaufkurs, Währung, Notiz)."""
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE portfolio
               SET shares_micro    = ?,
                   buy_price_micro = ?,
                   currency        = ?,
                   notes           = ?
             WHERE isin = ?
            """,
            (shares_micro, buy_price_micro, currency, notes.strip(), isin),
        )
        conn.commit()
    logger.info("Portfolio-Position aktualisiert: %s", isin)


def remove_position(isin: str, db_path: Path = DB_PATH) -> bool:
    """
    Entfernt eine Position aus dem Portfolio.

    Returns:
        True wenn entfernt, False wenn nicht gefunden.
    """
    with _get_connection(db_path) as conn:
        cursor = conn.execute(
            "DELETE FROM portfolio WHERE isin = ?", (isin,)
        )
        conn.commit()
        removed = cursor.rowcount > 0
    if removed:
        logger.info("Portfolio: %s entfernt.", isin)
    return removed


# ── Leseoperationen ───────────────────────────────────────────────────────────

def get_portfolio(db_path: Path = DB_PATH) -> list[PortfolioEntry]:
    """Gibt alle Positionen zurück, sortiert nach Hinzufügedatum (neueste zuerst)."""
    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    p.isin,
                    COALESCE(i.name_override, i.name) AS name,
                    COALESCE(i.wkn, '')               AS wkn,
                    p.shares_micro,
                    p.buy_price_micro,
                    p.currency,
                    p.notes,
                    p.added_at
                FROM portfolio p
                JOIN instruments i ON i.isin = p.isin
                ORDER BY p.added_at DESC
                """,
            ).fetchall()
    except sqlite3.Error:
        logger.exception("Fehler beim Laden des Portfolios.")
        return []

    return [
        PortfolioEntry(
            isin=row["isin"],
            name=row["name"],
            wkn=row["wkn"] or None,
            shares_micro=row["shares_micro"],
            buy_price_micro=row["buy_price_micro"],
            currency=row["currency"],
            notes=row["notes"] or "",
            added_at=row["added_at"],
        )
        for row in rows
    ]


def get_position(isin: str, db_path: Path = DB_PATH) -> PortfolioEntry | None:
    """Gibt eine einzelne Position per ISIN zurück."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                """
                SELECT
                    p.isin,
                    COALESCE(i.name_override, i.name) AS name,
                    COALESCE(i.wkn, '')               AS wkn,
                    p.shares_micro,
                    p.buy_price_micro,
                    p.currency,
                    p.notes,
                    p.added_at
                FROM portfolio p
                JOIN instruments i ON i.isin = p.isin
                WHERE p.isin = ?
                """,
                (isin,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return PortfolioEntry(
        isin=row["isin"],
        name=row["name"],
        wkn=row["wkn"] or None,
        shares_micro=row["shares_micro"],
        buy_price_micro=row["buy_price_micro"],
        currency=row["currency"],
        notes=row["notes"] or "",
        added_at=row["added_at"],
    )


def is_in_portfolio(isin: str, db_path: Path = DB_PATH) -> bool:
    """Prüft ob eine ISIN im Portfolio ist."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM portfolio WHERE isin = ?", (isin,)
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


def count_portfolio(db_path: Path = DB_PATH) -> int:
    """Anzahl der Positionen im Portfolio."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM portfolio"
            ).fetchone()
        return row["cnt"] if row else 0
    except sqlite3.Error:
        return 0