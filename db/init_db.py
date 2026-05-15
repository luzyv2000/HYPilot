# Dateiname:     db/init_db.py
# Version:       2026-05-15-portfolio
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/init_db.py

Neu 2026-05-15: portfolio-Tabelle
  (isin, shares_micro, buy_price_micro, currency, notes, added_at).
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


_TABLE_DDL: list[str] = [

    """
    CREATE TABLE IF NOT EXISTS instruments (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        isin         TEXT NOT NULL UNIQUE,
        wkn          TEXT,
        symbol       TEXT,
        name_override TEXT,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS metadata (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,

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
            source IN (
                'yfinance',
                'openfigi',
                'openfigi_unvalidated',
                'manual',
                'unresolvable',
                'unknown'
            )
        )
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS dividend_data (
        isin               TEXT PRIMARY KEY
                           REFERENCES instruments(isin) ON DELETE CASCADE,
        yield_bps          INTEGER,
        yield_bps_prev     INTEGER,
        frequency          TEXT,
        last_amount_micro  INTEGER,
        last_ex_date       DATE,
        currency           TEXT,
        payout_ratio_bps   INTEGER,
        skip_until         DATE,
        data_source        TEXT NOT NULL DEFAULT 'yfinance',
        updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_frequency CHECK (
            frequency IS NULL OR frequency IN (
                'monthly', 'quarterly', 'semi_annual', 'annual', 'irregular'
            )
        )
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS dividend_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        isin          TEXT NOT NULL
                      REFERENCES instruments(isin) ON DELETE CASCADE,
        ex_date       DATE NOT NULL,
        amount_micro  INTEGER NOT NULL,
        currency      TEXT NOT NULL,
        data_source   TEXT NOT NULL DEFAULT 'yfinance',
        UNIQUE (isin, ex_date)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS pending_name_changes (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        isin         TEXT NOT NULL
                     REFERENCES instruments(isin) ON DELETE CASCADE,
        name_current TEXT NOT NULL,
        name_pdf     TEXT NOT NULL,
        detected_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (isin)
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS threshold_crossings (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        isin           TEXT NOT NULL
                       REFERENCES instruments(isin) ON DELETE CASCADE,
        yield_bps_old  INTEGER,
        yield_bps_new  INTEGER NOT NULL,
        direction      TEXT NOT NULL,
        detected_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        shown_at       TIMESTAMP,
        CONSTRAINT chk_direction CHECK (direction IN ('up', 'down'))
    )
    """,

    # ── Watchlist ──────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS watchlist (
        isin       TEXT PRIMARY KEY
                   REFERENCES instruments(isin) ON DELETE CASCADE,
        notes      TEXT NOT NULL DEFAULT '',
        added_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── Portfolio ──────────────────────────────────────────────────────────────
    # shares_micro    : 1_000_000 = 1 Anteil (unterstützt Bruchteile)
    # buy_price_micro : Kaufkurs pro Anteil in Micro-Units (optional)
    # currency        : Kaufwährung (ISO 4217)
    # notes           : Freitext (optional)
    """
    CREATE TABLE IF NOT EXISTS portfolio (
        isin             TEXT PRIMARY KEY
                         REFERENCES instruments(isin) ON DELETE CASCADE,
        shares_micro     INTEGER NOT NULL,
        buy_price_micro  INTEGER,
        currency         TEXT NOT NULL DEFAULT 'EUR',
        notes            TEXT NOT NULL DEFAULT '',
        added_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]


_MIGRATIONS: list[str] = [
    "ALTER TABLE instruments    ADD COLUMN name_override TEXT",
    "ALTER TABLE dividend_data  ADD COLUMN yield_bps_prev INTEGER",
    "ALTER TABLE dividend_data  ADD COLUMN skip_until DATE",
]

_TICKER_MAPPING_CONSTRAINT_MIGRATION = """
BEGIN;
CREATE TABLE IF NOT EXISTS ticker_mapping_new (
    isin       TEXT PRIMARY KEY
               REFERENCES instruments(isin) ON DELETE CASCADE,
    ticker     TEXT NOT NULL,
    exchange   TEXT,
    source     TEXT NOT NULL DEFAULT 'unknown',
    verified   INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_source CHECK (
        source IN (
            'yfinance',
            'openfigi',
            'openfigi_unvalidated',
            'manual',
            'unresolvable',
            'unknown'
        )
    )
);
INSERT OR IGNORE INTO ticker_mapping_new
    SELECT isin, ticker, exchange, source, verified, updated_at
    FROM ticker_mapping;
DROP TABLE ticker_mapping;
ALTER TABLE ticker_mapping_new RENAME TO ticker_mapping;
COMMIT;
"""

_INDEX_DDL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_instruments_isin    ON instruments(isin)",
    "CREATE INDEX IF NOT EXISTS idx_instruments_name    ON instruments(name)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_isin    ON dividend_history(isin)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_date    ON dividend_history(ex_date)",
    "CREATE INDEX IF NOT EXISTS idx_ticker_mapping_tick ON ticker_mapping(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_crossings_shown     ON threshold_crossings(shown_at)",
    "CREATE INDEX IF NOT EXISTS idx_div_skip_until      ON dividend_data(skip_until)",
    "CREATE INDEX IF NOT EXISTS idx_watchlist_added     ON watchlist(added_at)",
    "CREATE INDEX IF NOT EXISTS idx_portfolio_added     ON portfolio(added_at)",
]


def _needs_ticker_mapping_migration(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ticker_mapping'"
    ).fetchone()
    if not row:
        return False
    return "openfigi_unvalidated" not in (row[0] or "")


def init_database(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Initialisiere Datenbank: %s", db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        for ddl in _TABLE_DDL:
            conn.execute(ddl)

        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
                logger.info("Migration: %s", migration[:70])
            except sqlite3.OperationalError:
                pass

        if _needs_ticker_mapping_migration(conn):
            conn.executescript(_TICKER_MAPPING_CONSTRAINT_MIGRATION)
            logger.info("ticker_mapping Constraint-Migration abgeschlossen.")

        for ddl in _INDEX_DDL:
            conn.execute(ddl)

        conn.commit()

    logger.info("Schema erfolgreich erstellt/aktualisiert.")


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    init_database()
    sys.exit(0)