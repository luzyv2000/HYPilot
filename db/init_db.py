# Dateiname:     db/init_db.py
# Version:       2026-04-23-P3pp
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/init_db.py

Erstellt oder aktualisiert das HYPilot-Datenbankschema.
Idempotent: kann sicher mehrfach ausgeführt werden.

Schema-Übersicht:
  instruments          — Wertpapier-Stammdaten + name_override
  metadata             — Schlüssel-Wert-Paare
  ticker_mapping       — ISIN → Ticker
  dividend_data        — Dividenden-Kennzahlen
                         + yield_bps_prev  (Vorwert für Schwellwert-Erkennung)
                         + skip_until      (Pausierung bei 0-Dividende)
  dividend_history     — Einzelzahlungen
  pending_name_changes — PDF-Namenskonflikte
  threshold_crossings  — 10%-Schwellwert-Überschreitungen (für GUI-Popup)

Finanz-Konventionen:
  - Renditen als INTEGER in Basispunkten (bps): 1% = 100 bps
  - Beträge als INTEGER in Micro-Units (1 EUR = 1_000_000)
  - Berechnungen via decimal.Decimal — kein float
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_DDL_STATEMENTS: list[str] = [

    # ── Stammdaten ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS instruments (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        name          TEXT    NOT NULL,
        isin          TEXT    NOT NULL UNIQUE,
        wkn           TEXT,
        symbol        TEXT,
        name_override TEXT,
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS metadata (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,

    # ── Ticker-Mapping ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS ticker_mapping (
        isin       TEXT PRIMARY KEY
                       REFERENCES instruments(isin) ON DELETE CASCADE,
        ticker     TEXT NOT NULL,
        exchange   TEXT,
        source     TEXT NOT NULL DEFAULT 'unknown',
        verified   INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_source CHECK (
            source IN ('yfinance', 'openfigi', 'manual', 'unknown')
        )
    )
    """,

    # ── Dividenden-Kennzahlen ─────────────────────────────────────────────────
    # yield_bps_prev: Rendite vor letztem Update (für Schwellwert-Vergleich)
    # skip_until:     Datum bis zu dem der Abruf pausiert wird
    #                 (gesetzt wenn >18 Monate keine Dividende)
    """
    CREATE TABLE IF NOT EXISTS dividend_data (
        isin              TEXT PRIMARY KEY
                              REFERENCES instruments(isin) ON DELETE CASCADE,
        yield_bps         INTEGER,
        yield_bps_prev    INTEGER,
        frequency         TEXT,
        last_amount_micro INTEGER,
        last_ex_date      DATE,
        currency          TEXT,
        payout_ratio_bps  INTEGER,
        skip_until        DATE,
        data_source       TEXT NOT NULL DEFAULT 'yfinance',
        updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_frequency CHECK (
            frequency IS NULL OR frequency IN (
                'monthly', 'quarterly', 'semi_annual', 'annual', 'irregular'
            )
        )
    )
    """,

    # ── Dividenden-Historie ───────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dividend_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        isin          TEXT    NOT NULL
                          REFERENCES instruments(isin) ON DELETE CASCADE,
        ex_date       DATE    NOT NULL,
        amount_micro  INTEGER NOT NULL,
        currency      TEXT    NOT NULL,
        data_source   TEXT    NOT NULL DEFAULT 'yfinance',
        UNIQUE (isin, ex_date)
    )
    """,

    # ── Ausstehende Namensänderungen ──────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS pending_name_changes (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        isin          TEXT    NOT NULL
                          REFERENCES instruments(isin) ON DELETE CASCADE,
        name_current  TEXT    NOT NULL,
        name_pdf      TEXT    NOT NULL,
        detected_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (isin)
    )
    """,

    # ── Schwellwert-Überschreitungen (10%-Grenze) ─────────────────────────────
    # direction: 'up'   = neu über 10% (war darunter)
    #            'down' = neu unter 10% (war darüber)
    # shown_at:  NULL = noch nicht im GUI angezeigt
    """
    CREATE TABLE IF NOT EXISTS threshold_crossings (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        isin          TEXT    NOT NULL
                          REFERENCES instruments(isin) ON DELETE CASCADE,
        yield_bps_old INTEGER,
        yield_bps_new INTEGER NOT NULL,
        direction     TEXT    NOT NULL,
        detected_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        shown_at      TIMESTAMP,
        CONSTRAINT chk_direction CHECK (direction IN ('up', 'down'))
    )
    """,

    # ── Indizes ───────────────────────────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_instruments_isin    ON instruments(isin)",
    "CREATE INDEX IF NOT EXISTS idx_instruments_name    ON instruments(name)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_isin    ON dividend_history(isin)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_date    ON dividend_history(ex_date)",
    "CREATE INDEX IF NOT EXISTS idx_ticker_mapping_tick ON ticker_mapping(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_crossings_shown     ON threshold_crossings(shown_at)",
    "CREATE INDEX IF NOT EXISTS idx_div_skip_until      ON dividend_data(skip_until)",
]

# ── Migrationen (für bestehende DBs) ─────────────────────────────────────────

_MIGRATIONS: list[str] = [
    "ALTER TABLE instruments    ADD COLUMN name_override  TEXT",
    "ALTER TABLE dividend_data  ADD COLUMN yield_bps_prev INTEGER",
    "ALTER TABLE dividend_data  ADD COLUMN skip_until     DATE",
]


def init_database(db_path: Path = DB_PATH) -> None:
    """
    Erstellt oder aktualisiert alle Tabellen und Indizes.
    Bestehende Daten bleiben erhalten.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Initialisiere Datenbank: %s", db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        for ddl in _DDL_STATEMENTS:
            conn.execute(ddl)

        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
                logger.info("Migration: %s", migration[:70])
            except sqlite3.OperationalError:
                pass  # Spalte existiert bereits

        conn.commit()

    logger.info("Schema erfolgreich erstellt/aktualisiert.")


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_database()
    sys.exit(0)
