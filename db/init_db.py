# Dateiname:     db/init_db.py
# Version:       2026-04-20
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/init_db.py

Erstellt oder aktualisiert das HYPilot-Datenbankschema.
Idempotent: kann sicher mehrfach ausgeführt werden.

Schema-Übersicht:
  instruments     — Wertpapier-Stammdaten (aus TR-PDF)
  metadata        — Schlüssel-Wert-Paare (z.B. letzter PDF-Hash)
  ticker_mapping  — ISIN → Ticker-Zuordnung (yfinance, OpenFIGI, manuell)
  dividend_data   — Aggregierte Dividenden-Kennzahlen je Instrument
  dividend_history — Einzelne Dividendenzahlungen (Historie)

Finanz-Konventionen:
  - Renditen als INTEGER in Basispunkten (bps): 1% = 100 bps
  - Beträge als INTEGER in Micro-Units (1 EUR = 1_000_000)
  - Alle Berechnungen im Python-Code via decimal.Decimal
  - Keine REAL-Spalten für Geldwerte oder Renditen
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# ── Schema-Definitionen ───────────────────────────────────────────────────────

_DDL_STATEMENTS: list[str] = [

    # ── Bestehend (unverändert) ───────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS instruments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT    NOT NULL,
        isin       TEXT    NOT NULL UNIQUE,
        wkn        TEXT,
        symbol     TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    """
    CREATE TABLE IF NOT EXISTS metadata (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,

    # ── Neu: ISIN → Ticker-Mapping ────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS ticker_mapping (
        isin       TEXT PRIMARY KEY
                       REFERENCES instruments(isin) ON DELETE CASCADE,
        ticker     TEXT NOT NULL,
        exchange   TEXT,
        source     TEXT NOT NULL DEFAULT 'unknown',
        -- Mögliche Werte: 'yfinance', 'openfigi', 'manual'
        verified   INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_source CHECK (
            source IN ('yfinance', 'openfigi', 'manual', 'unknown')
        )
    )
    """,

    # ── Neu: Aggregierte Dividenden-Kennzahlen ────────────────────────────────
    # yield_bps: Trailing-12-Monate-Rendite in Basispunkten (INTEGER)
    #            Beispiel: 10,5% → 1050 bps
    # last_amount_micro: letzte Dividendenzahlung in Micro-Units
    #            Beispiel: 0.25 EUR → 250_000 micro-EUR
    """
    CREATE TABLE IF NOT EXISTS dividend_data (
        isin              TEXT PRIMARY KEY
                              REFERENCES instruments(isin) ON DELETE CASCADE,
        yield_bps         INTEGER,
        -- Trailing-12M-Rendite in Basispunkten; NULL = unbekannt
        frequency         TEXT,
        -- 'monthly'|'quarterly'|'semi_annual'|'annual'|'irregular'|NULL
        last_amount_micro INTEGER,
        -- letzte Ausschüttung in Micro-Units der Währung
        last_ex_date      DATE,
        currency          TEXT,
        payout_ratio_bps  INTEGER,
        -- Ausschüttungsquote in Basispunkten; NULL = unbekannt
        data_source       TEXT NOT NULL DEFAULT 'yfinance',
        updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT chk_frequency CHECK (
            frequency IS NULL OR frequency IN (
                'monthly', 'quarterly', 'semi_annual', 'annual', 'irregular'
            )
        )
    )
    """,

    # ── Neu: Dividenden-Einzelzahlungen (Historie) ───────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dividend_history (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        isin          TEXT    NOT NULL
                          REFERENCES instruments(isin) ON DELETE CASCADE,
        ex_date       DATE    NOT NULL,
        amount_micro  INTEGER NOT NULL,
        -- Betrag in Micro-Units der Währung
        currency      TEXT    NOT NULL,
        data_source   TEXT    NOT NULL DEFAULT 'yfinance',
        UNIQUE (isin, ex_date)
    )
    """,

    # ── Indizes ───────────────────────────────────────────────────────────────
    "CREATE INDEX IF NOT EXISTS idx_instruments_isin ON instruments(isin)",
    "CREATE INDEX IF NOT EXISTS idx_instruments_name ON instruments(name)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_isin ON dividend_history(isin)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_date ON dividend_history(ex_date)",
    "CREATE INDEX IF NOT EXISTS idx_ticker_mapping_ticker ON ticker_mapping(ticker)",
]


# ── Öffentliche API ───────────────────────────────────────────────────────────

def init_database(db_path: Path = DB_PATH) -> None:
    """
    Erstellt oder aktualisiert alle Tabellen und Indizes.
    Bestehende Daten bleiben erhalten (IF NOT EXISTS).
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Initialisiere Datenbank: %s", db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        for ddl in _DDL_STATEMENTS:
            conn.execute(ddl)

        conn.commit()

    logger.info("Schema erfolgreich erstellt/aktualisiert.")


# ── CLI-Einstiegspunkt ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    init_database()
    sys.exit(0)