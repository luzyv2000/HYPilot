# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-21
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): yfinance
"""
core/ticker_resolver.py

Löst ISIN → Ticker-Symbol auf.

Strategie (zwei Stufen):
  1. Lokale DB (ticker_mapping) — schnell, offline
  2. yfinance-Direktabfrage    — langsam, erfordert Netz
     yfinance akzeptiert ISINs in neueren Versionen direkt.
     Das aufgelöste Symbol wird in der DB gespeichert.

Zukünftige Erweiterung: OpenFIGI als primäre Quelle vor yfinance.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import yfinance as yf

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── DB-Operationen ────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_db(isin: str, db_path: Path = DB_PATH) -> str | None:
    """Sucht Ticker in der lokalen DB."""
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT ticker FROM ticker_mapping WHERE isin = ?", (isin,)
        ).fetchone()
    return row["ticker"] if row else None


def _store_mapping(
    isin: str,
    ticker: str,
    source: str,
    exchange: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Speichert oder aktualisiert ein ISIN→Ticker-Mapping."""
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO ticker_mapping (isin, ticker, exchange, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                ticker     = excluded.ticker,
                exchange   = excluded.exchange,
                source     = excluded.source,
                updated_at = excluded.updated_at
            """,
            (isin, ticker, exchange, source, now),
        )
        conn.commit()
    logger.debug("Mapping gespeichert: %s → %s (Quelle: %s)", isin, ticker, source)


# ── yfinance-Auflösung ────────────────────────────────────────────────────────

def _resolve_via_yfinance(isin: str) -> str | None:
    """
    Versucht ISIN direkt via yfinance aufzulösen.
    yfinance akzeptiert ISINs und gibt das Symbol im info-Dict zurück.

    Returns:
        Ticker-Symbol oder None bei Misserfolg.
    """
    try:
        ticker_obj = yf.Ticker(isin)
        info = ticker_obj.info

        symbol = info.get("symbol")
        exchange = info.get("exchange")

        if not symbol:
            logger.debug("yfinance: kein Symbol für ISIN %s", isin)
            return None

        logger.info(
            "yfinance: ISIN %s aufgelöst → %s (Börse: %s)",
            isin, symbol, exchange,
        )
        _store_mapping(isin, symbol, source="yfinance", exchange=exchange)
        return symbol

    except Exception as exc:
        logger.warning("yfinance-Auflösung fehlgeschlagen für %s: %s", isin, exc)
        return None


# ── Öffentliche API ───────────────────────────────────────────────────────────

def resolve(isin: str, db_path: Path = DB_PATH) -> str | None:
    """
    Löst ISIN → Ticker auf. DB-first, yfinance als Fallback.

    Args:
        isin: ISIN des Instruments (z.B. 'US88160R1014')

    Returns:
        Ticker-Symbol (z.B. 'TSLA') oder None wenn nicht auflösbar.
    """
    # Stufe 1: lokale DB
    ticker = _lookup_db(isin, db_path)
    if ticker:
        logger.debug("Ticker aus DB: %s → %s", isin, ticker)
        return ticker

    # Stufe 2: yfinance
    logger.debug("Kein DB-Eintrag für %s — versuche yfinance.", isin)
    return _resolve_via_yfinance(isin)


def store_manual_mapping(
    isin: str,
    ticker: str,
    exchange: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """
    Speichert ein manuell erfasstes ISIN→Ticker-Mapping.
    Überschreibt automatisch ermittelte Mappings.
    """
    _store_mapping(isin, ticker, source="manual", exchange=exchange, db_path=db_path)
    logger.info("Manuelles Mapping gespeichert: %s → %s", isin, ticker)
