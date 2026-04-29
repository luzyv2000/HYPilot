# Dateiname:     db/init_db.py
# Version:       2026-04-27-improved
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/init_db.py 

Erstellt oder aktualisiert das HYPilot-Datenbankschema.
Idempotent: kann sicher mehrfach ausgeführt werden.

Drei-Phasen-Strategie (Reihenfolge ist zwingend):
  Phase 1 — Tabellen: CREATE TABLE IF NOT EXISTS
  Phase 2 — Migrationen: ALTER TABLE (try/except pro Statement)
  Phase 3 — Indizes: CREATE INDEX IF NOT EXISTS
             (erst nach Migrationen, damit neue Spalten existieren)

Schema-Übersicht:
  instruments        — Wertpapier-Stammdaten + name_override
  metadata           — Schlüssel-Wert-Paare
  ticker_mapping     — ISIN → Ticker-Zuordnung
  dividend_data      — Aggregierte Dividenden-Kennzahlen
                       + yield_bps_prev (Vorwert für Schwellwert-Erkennung)
                       + skip_until     (Pausierung bei 0-Dividende)
  dividend_history   — Einzelne Dividendenzahlungen
  pending_name_changes — PDF-Namenskonflikte (warten auf Nutzer-Zustimmung)
  threshold_crossings  — 10%-Schwellwert-Überschreitungen für GUI-Popup

Finanz-Konventionen:
  - Renditen als INTEGER in Basispunkten (bps): 1 % = 100 bps
  - Beträge als INTEGER in Micro-Units:         1 EUR = 1_000_000
  - Alle Berechnungen im Python-Code via decimal.Decimal — kein float

Ticker-Source-Typen (CHECK constraint):
  - 'yfinance'              — via yfinance-Direktabfrage validiert
  - 'openfigi'              — via OpenFIGI, von yfinance validiert
  - 'openfigi_unvalidated'  — via OpenFIGI, NICHT von yfinance validiert
                              (typisch für europäische/exotische Börsen)
  - 'manual'                — manuell vom Nutzer eingetragen
  - 'unknown'               — Legacy/unbekannte Quelle
  - 'unresolvable'          — nicht auflösbar (TTL: 30 Tage, dann Retry)
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Pfad-Konstante ──────────────────────────────────────────────────────────

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Phase 1: Basis-Schema ───────────────────────────────────────────────────────

_TABLE_DDL: list[str] = [
    # ── Instrumente (Grunddaten) ─────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS instruments (
        isin          TEXT PRIMARY KEY,
        wkn           TEXT UNIQUE,
        name          TEXT NOT NULL,
        name_override TEXT,
        isin_type     TEXT,
        currency      TEXT DEFAULT 'EUR',
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── Ticker-Mappings (ISIN → Ticker-Symbol) ──────────────────────────────────
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
            source IN ('yfinance', 'openfigi', 'openfigi_unvalidated', 
                       'manual', 'unknown', 'unresolvable')
        )
    )
    """,

    # ── Dividenden-Kennzahlen ────────────────────────────────────────────────────
    # yield_bps_prev : Rendite vor letztem Update  (für Schwellwert-Vergleich)
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

    # ── Dividenden-Historie ──────────────────────────────────────────────────────
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

    # ── Ausstehende Namensänderungen ─────────────────────────────────────────
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

    # ── Schwellwert-Überschreitungen (10%-Grenze) ────────────────────────────
    # direction : 'up'   = neu über 10 %  (war darunter)
    #             'down' = neu unter 10 % (war darüber)
    # shown_at  : NULL   = noch nicht im GUI angezeigt
    """
    CREATE TABLE IF NOT EXISTS threshold_crossings (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        isin            TEXT NOT NULL
                        REFERENCES instruments(isin) ON DELETE CASCADE,
        yield_bps_old   INTEGER,
        yield_bps_new   INTEGER NOT NULL,
        direction       TEXT NOT NULL,
        detected_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        shown_at        TIMESTAMP,
        CONSTRAINT chk_direction CHECK (direction IN ('up', 'down'))
    )
    """,
]

# ── Phase 2: Migrationen (für bestehende DBs) ─────────────────────────────────
# ALTER TABLE ist NICHT idempotent → try/except pro Statement.

_MIGRATIONS: list[str] = [
    # Migration: 'unresolvable' + 'openfigi_unvalidated' zu erlaubten Quellen
    # Nur für alte Datenbanken — Neu-DBs haben das bereits in Phase 1
    """
    ALTER TABLE ticker_mapping
    DROP CONSTRAINT chk_source
    """,
    
    """
    ALTER TABLE ticker_mapping
    ADD CONSTRAINT chk_source CHECK (
        source IN ('yfinance', 'openfigi', 'openfigi_unvalidated', 
                   'manual', 'unknown', 'unresolvable')
    )
    """,
]

# ── Phase 3: Indizes ────────────────────────────────────────────────────────
# Erst nach Migrationen ausführen — neue Spalten müssen existieren.

_INDEX_DDL: list[str] = [
    "CREATE INDEX IF NOT EXISTS idx_instruments_isin ON instruments(isin)",
    "CREATE INDEX IF NOT EXISTS idx_instruments_name ON instruments(name)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_isin ON dividend_history(isin)",
    "CREATE INDEX IF NOT EXISTS idx_div_history_date ON dividend_history(ex_date)",
    "CREATE INDEX IF NOT EXISTS idx_ticker_mapping_tick ON ticker_mapping(ticker)",
    "CREATE INDEX IF NOT EXISTS idx_crossings_shown ON threshold_crossings(shown_at)",
    # Dieser Index benötigt skip_until — darf erst nach Migration laufen
    "CREATE INDEX IF NOT EXISTS idx_div_skip_until ON dividend_data(skip_until)",
]


# ── Öffentliche API ────────────────────────────────────────────────────────────

def init_database(db_path: Path = DB_PATH) -> None:
    """
    Erstellt oder aktualisiert alle Tabellen und Indizes.

    Drei-Phasen-Strategie (Reihenfolge zwingend):
      1. Tabellen  — CREATE TABLE IF NOT EXISTS
      2. Migrationen — ALTER TABLE (idempotent via try/except)
      3. Indizes   — CREATE INDEX IF NOT EXISTS (nach Migrationen!)

    Bestehende Daten bleiben erhalten.
    
    Args:
        db_path: Pfad zur Datenbankdatei (default: /home/luzy/workspace/openclaw-min/db/hypilot.db)
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

        # Phase 2 — Migrationen
        logger.debug("Phase 2: Migrationen ausführen ...")
        for migration in _MIGRATIONS:
            try:
                conn.execute(migration)
                logger.debug("Migration ausgeführt: %s", migration[:70])
            except sqlite3.OperationalError as e:
                # Spalte existiert bereits oder Constraint existiert bereits
                # — erwartetes Verhalten bei idempotenten Migrationen, kein Fehler
                logger.debug("Migration skipped (bereits vorhanden): %s", str(e)[:70])
                pass

        # Phase 3 — Indizes (nach Migrationen!)
        logger.debug("Phase 3: Indizes anlegen ...")
        for ddl in _INDEX_DDL:
            conn.execute(ddl)

        conn.commit()

    logger.info("Schema erfolgreich erstellt/aktualisiert.")


# ── CLI-Einstiegspunkt ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    init_database()
    sys.exit(0)
