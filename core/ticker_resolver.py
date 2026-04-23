# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-23-B2
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): requests, python-dotenv, yfinance
"""
core/ticker_resolver.py

Löst ISIN → Ticker-Symbol auf.

Auflösungsstrategie (drei Stufen):
  1. Lokale DB (ticker_mapping)  — sofort, offline
  2. OpenFIGI API                — zuverlässig, strukturiert
     → Ticker wird via yfinance validiert bevor er gespeichert wird
  3. yfinance-Direktabfrage      — Fallback

OpenFIGI:
  - Kostenlose API, kein Key erforderlich (25 req/min ohne Key)
  - Mit Key (OPENFIGI_API_KEY in .env): 250 req/min
  - Endpoint: https://api.openfigi.com/v3/mapping

Sicherheit:
  - API-Key wird ausschließlich aus .env geladen
  - Key wird niemals geloggt
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_OPENFIGI_URL    = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()

_PREFERRED_EXCHANGES: tuple[str, ...] = (
    "US",    # NYSE / NASDAQ
    "GY",    # XETRA
    "LN",    # London
    "FP",    # Paris
    "GF",    # Frankfurt
    "SW",    # Schweiz
    "AV",    # Wien
)

_OPENFIGI_DELAY = 0.25


# ── DB-Operationen ────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_db(isin: str, db_path: Path = DB_PATH) -> str | None:
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
    logger.debug(
        "Mapping gespeichert: %s → %s (Quelle: %s, Börse: %s)",
        isin, ticker, source, exchange,
    )


def _delete_mapping(isin: str, db_path: Path = DB_PATH) -> None:
    """Löscht ein ungültiges Mapping aus der DB."""
    with _get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM ticker_mapping WHERE isin = ?", (isin,)
        )
        conn.commit()
    logger.debug("Ungültiges Mapping gelöscht: %s", isin)


# ── Ticker-Validierung ────────────────────────────────────────────────────────

def _validate_ticker(ticker: str) -> bool:
    """
    Prüft ob ein Ticker von yfinance erkannt wird.
    Vermeidet dass OpenFIGI-Ticker (Y9B, KSEUR etc.) blind gespeichert werden.

    Returns:
        True wenn yfinance einen gültigen Symbol-Eintrag zurückgibt.
    """
    try:
        info = yf.Ticker(ticker).info
        # yfinance gibt bei ungültigem Ticker ein fast leeres Dict zurück
        # 'symbol' oder 'quoteType' sind zuverlässige Indikatoren
        return bool(info.get("symbol") or info.get("quoteType"))
    except Exception:
        return False


# ── OpenFIGI-Auflösung ────────────────────────────────────────────────────────

def _select_best_figi(results: list[dict]) -> dict | None:
    if not results:
        return None
    for exchange in _PREFERRED_EXCHANGES:
        for item in results:
            if item.get("exchCode") == exchange:
                return item
    return results[0]


def _resolve_via_openfigi(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """
    Löst ISIN via OpenFIGI auf und validiert das Ergebnis via yfinance.
    Nur validierte Ticker werden in der DB gespeichert.
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _OPENFIGI_APIKEY:
        headers["X-OPENFIGI-APIKEY"] = _OPENFIGI_APIKEY

    payload = [{"idType": "ID_ISIN", "idValue": isin}]

    try:
        response = requests.post(
            _OPENFIGI_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        time.sleep(_OPENFIGI_DELAY)

        if response.status_code == 429:
            logger.warning(
                "OpenFIGI Rate-Limit für %s — verwende yfinance.", isin
            )
            return None

        if response.status_code != 200:
            logger.warning(
                "OpenFIGI HTTP %s für %s.", response.status_code, isin
            )
            return None

        data = response.json()
        if not data or not isinstance(data, list):
            return None

        first = data[0]
        if "warning" in first:
            logger.debug(
                "OpenFIGI: kein Ergebnis für %s — %s",
                isin, first["warning"],
            )
            return None

        items = first.get("data", [])
        best  = _select_best_figi(items)
        if not best:
            return None

        ticker   = best.get("ticker")
        exchange = best.get("exchCode")

        if not ticker:
            return None

        # ── Validierung (neu) ────────────────────────────────────────────────
        logger.debug(
            "OpenFIGI: %s → %s (Börse: %s) — validiere …",
            isin, ticker, exchange,
        )
        if not _validate_ticker(ticker):
            logger.warning(
                "OpenFIGI-Ticker %s für %s von yfinance nicht erkannt — "
                "verwerfe und versuche yfinance-Direktauflösung.",
                ticker, isin,
            )
            return None

        logger.info(
            "OpenFIGI: %s → %s (Börse: %s) ✓ validiert",
            isin, ticker, exchange,
        )
        _store_mapping(
            isin, ticker,
            source="openfigi",
            exchange=exchange,
            db_path=db_path,
        )
        return ticker

    except requests.RequestException as exc:
        logger.warning("OpenFIGI-Anfrage fehlgeschlagen für %s: %s", isin, exc)
        return None
    except Exception:
        logger.exception("Unerwarteter Fehler bei OpenFIGI für %s", isin)
        return None


# ── yfinance-Fallback ─────────────────────────────────────────────────────────

def _resolve_via_yfinance(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """Löst ISIN direkt via yfinance auf. Letzter Fallback."""
    try:
        ticker_obj = yf.Ticker(isin)
        info       = ticker_obj.info
        symbol     = info.get("symbol")
        exchange   = info.get("exchange")

        if not symbol:
            logger.debug("yfinance: kein Symbol für ISIN %s", isin)
            return None

        logger.info(
            "yfinance (Fallback): %s → %s (Börse: %s)",
            isin, symbol, exchange,
        )
        _store_mapping(
            isin, symbol,
            source="yfinance",
            exchange=exchange,
            db_path=db_path,
        )
        return symbol

    except Exception as exc:
        logger.warning("yfinance-Auflösung fehlgeschlagen für %s: %s", isin, exc)
        return None


# ── Öffentliche API ───────────────────────────────────────────────────────────

def resolve(
    isin: str,
    db_path: Path = DB_PATH,
    skip_openfigi: bool = False,
) -> str | None:
    """
    Löst ISIN → Ticker auf.

    Reihenfolge:
      1. Lokale DB        (sofort)
      2. OpenFIGI API     (mit yfinance-Validierung)
      3. yfinance         (Fallback)
    """
    # Stufe 1: DB-Cache
    ticker = _lookup_db(isin, db_path)
    if ticker:
        logger.debug("Ticker aus DB-Cache: %s → %s", isin, ticker)
        return ticker

    # Stufe 2: OpenFIGI (mit Validierung)
    if not skip_openfigi:
        ticker = _resolve_via_openfigi(isin, db_path)
        if ticker:
            return ticker

    # Stufe 3: yfinance
    logger.debug("OpenFIGI erfolglos — versuche yfinance für %s.", isin)
    return _resolve_via_yfinance(isin, db_path)


def store_manual_mapping(
    isin: str,
    ticker: str,
    exchange: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Speichert ein manuell erfasstes Mapping. Überschreibt automatische."""
    _store_mapping(
        isin, ticker,
        source="manual",
        exchange=exchange,
        db_path=db_path,
    )
    logger.info("Manuelles Mapping gespeichert: %s → %s", isin, ticker)
