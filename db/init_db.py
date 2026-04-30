# Dateiname:     db/init_db.py
# Version:       2026-04-30
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/init_db.py

Erstellt oder aktualisiert das HYPilot-Datenbankschema.
Idempotent: kann sicher mehrfach ausgeführt werden.

Drei-Phasen-Strategie (Reihenfolge ist zwingend):
  Phase 1 — Tabellen:     CREATE TABLE IF NOT EXISTS
  Phase 2 — Migrationen:  ALTER TABLE (try/except pro Statement)
  Phase 3 — Indizes:      CREATE INDEX IF NOT EXISTS (nach Migrationen!)

Schema-Übersicht:
  instruments        — Wertpapier-Stammdaten + name_override
  metadata           — Schlüssel-Wert-Paare
  ticker_mapping     — ISIN → Ticker-Zuordnung
  dividend_data      — Aggregierte Dividenden-Kennzahlen
                       + yield_bps_prev (Vorwert für Schwellwert-Erkennung)
                       + skip_until    (Pausierung bei 0-Dividende)
  dividend_history   — Einzelne Dividendenzahlungen
  pending_name_changes — PDF-Namenskonflikte (warten auf Nutzer-Zustimmung)
  threshold_crossings  — 10%-Schwellwert-Überschreitungen für GUI-Popup

Finanz-Konventionen:
  - Renditen als INTEGER in Basispunkten (bps): 1 % = 100 bps
  - Beträge als INTEGER in Micro-Units: 1 EUR = 1_000_000
  - Alle Berechnungen im Python-Code via decimal.Decimal — kein float
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Phase 1: Tabellen (ohne Indizes) ──────────────────────────────────────────

_TABLE_DDL: list[str] = [

    # ── Stammdaten ─────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS instruments (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        name         TEXT NOT NULL,
        isin         TEXT NOT NULL UNIQUE,
        wkn          TEXT,
        symbol       TEXT,
        name_override TEXT,
        -- Manuell gesetzter Name; hat Vorrang vor name.
        -- Anzeige via: COALESCE(name_override, name)
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── Metadaten ──────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS metadata (
        key   TEXT PRIMARY KEY,
        value TEXT
    )
    """,

    # ── ISIN → Ticker-Mapping ──────────────────────────────────────────────────
    # source-Werte:
    #   'yfinance'            — via yfinance-Direktauflösung
    #   'openfigi'            — via OpenFIGI, von yfinance validiert
    #   'openfigi_unvalidated'— via OpenFIGI, yfinance-Validierung fehlgeschlagen
    #                           (nur bei exotischen Märkten gespeichert)
    #   'manual'              — manuell eingetragen
    #   'unresolvable'        — alle Quellen erschöpft (TTL-basiert)
    #   'unknown'             — Fallback
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

    # ── Dividenden-Kennzahlen ──────────────────────────────────────────────────
    # yield_bps_prev : Rendite vor letztem Update (für Schwellwert-Vergleich)
    # skip_until     : Datum bis zu dem der Abruf pausiert wird
    #                  (gesetzt wenn >18 Monate keine Dividende)
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

    # ── Dividenden-Historie ────────────────────────────────────────────────────
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

    # ── Ausstehende Namensänderungen ───────────────────────────────────────────
    # PDF liefert anderen Namen → erst nach Nutzer-Zustimmung übernehmen
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

    # ── Schwellwert-Überschreitungen (10%-Grenze) ──────────────────────────────
    # direction : 'up'   = neu über 10 % (war darunter)
    #             'down' = neu unter 10 % (war darüber)
    # shown_at  : NULL = noch nicht im GUI angezeigt
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
]


# ── Phase 2: Migrationen (für bestehende DBs) ─────────────────────────────────
# ALTER TABLE ist NICHT idempotent → try/except pro Statement.
# Fehler = Spalte existiert bereits → korrekt ignorieren.
#
# ticker_mapping Constraint-Migration:
#   SQLite unterstützt kein ALTER TABLE ... DROP/MODIFY CONSTRAINT.
#   Strategie: Tabelle umbenennen → neu erstellen → Daten kopieren → alte löschen.
#   Nur ausführen wenn neuer Constraint noch nicht aktiv (Prüfung via sqlite_master).

_MIGRATIONS: list[str] = [
    "ALTER TABLE instruments    ADD COLUMN name_override TEXT",
    "ALTER TABLE dividend_data  ADD COLUMN yield_bps_prev INTEGER",
    "ALTER TABLE dividend_data  ADD COLUMN skip_until DATE",
]

_TICKER_MAPPING_CONSTRAINT_MIGRATION = """
-- Rekonstruiert ticker_mapping mit erweitertem chk_source-Constraint.
-- Wird nur ausgeführt wenn 'openfigi_unvalidated' noch nicht im Constraint steht.
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


# ── Phase 3: Indizes ──────────────────────────────────────────────────────────
# Erst nach Migrationen ausführen — neue Spalten müssen existieren.

_INDEX_DDL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_instruments_isin   ON instruments(isin)",
    "CREATE INDEX IF NOT EXISTS idx_instruments_name   ON instruments(name)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_isin   ON dividend_history(isin)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_date   ON dividend_history(ex_date)",
    "CREATE INDEX IF NOT EXISTS idx_ticker_mapping_tick ON ticker_mapping(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_crossings_shown    ON threshold_crossings(shown_at)",
    # Dieser Index benötigt skip_until — darf erst nach Migration laufen
    "CREATE INDEX IF NOT EXISTS idx_div_skip_until     ON dividend_data(skip_until)",
]


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _needs_ticker_mapping_migration(conn: sqlite3.Connection) -> bool:
    """
    Prüft ob der ticker_mapping-Constraint 'openfigi_unvalidated' noch nicht enthält.
    Liest den CREATE TABLE-Statement aus sqlite_master.
    """
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ticker_mapping'"
    ).fetchone()
    if not row:
        return False  # Tabelle existiert noch nicht → wird neu angelegt
    return "openfigi_unvalidated" not in (row[0] or "")


# ── Öffentliche API ───────────────────────────────────────────────────────────

def init_database(db_path: Path = DB_PATH) -> None:
    """
    Erstellt oder aktualisiert alle Tabellen und Indizes.

    Drei-Phasen-Strategie (Reihenfolge zwingend):
      1. Tabellen   — CREATE TABLE IF NOT EXISTS
      2. Migrationen — ALTER TABLE (idempotent via try/except)
                       + Constraint-Migration für ticker_mapping
      3. Indizes    — CREATE INDEX IF NOT EXISTS (nach Migrationen!)

    Bestehende Daten bleiben erhalten.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Initialisiere Datenbank: %s", db_path)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        # Phase 1 — Tabellen
        logger.debug("Phase 1: Tabellen anlegen ...")
        for ddl in _TABLE_DDL:
            conn.execute(ddl)

        # Phase 2a — Spalten-Migrationen
        logger.debug("Phase 2a: Spalten-Migrationen ...")
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
                logger.info("Migration ausgeführt: %s", migration[:70])
            except sqlite3.OperationalError:
                pass  # Spalte existiert bereits — erwartetes Verhalten

        # Phase 2b — ticker_mapping Constraint-Migration
        if _needs_ticker_mapping_migration(conn):
            logger.info(
                "ticker_mapping Constraint-Migration: "
                "füge 'openfigi_unvalidated' hinzu ..."
            )
            # executescript benötigt keine open Transaction
            conn.executescript(_TICKER_MAPPING_CONSTRAINT_MIGRATION)
            logger.info("ticker_mapping Constraint-Migration abgeschlossen.")

        # Phase 3 — Indizes (nach Migrationen!)
        logger.debug("Phase 3: Indizes anlegen ...")
        for ddl in _INDEX_DDL:
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
