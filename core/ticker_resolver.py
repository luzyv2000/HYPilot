# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-27-fixed
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): requests, python-dotenv, yfinance
"""
core/ticker_resolver.py

Löst ISIN → Ticker-Symbol auf.

Auflösungsstrategie (drei Stufen):
  1. Lokale DB (ticker_mapping)  — sofort, offline
     Sonderfall: source='unresolvable' → sofort None (kein API-Call)
  2. OpenFIGI + Exchange-Suffix  — ISIN-land-basierte Börsenpräferenz
  3. yfinance-Direktabfrage      — Fallback; für bestimmte Präfixe deaktiviert

Unresolvable-Tracking:
  Nicht auflösbare ISINs erhalten source='unresolvable' für UNRESOLVABLE_TTL_DAYS.
  Nach TTL-Ablauf wird automatisch erneut versucht.

Sicherheit:
  API-Key ausschließlich via .env — niemals geloggt.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum

import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Statusmodell ─────────────────────────────────────────────────────

class ResolveStatus(str, Enum):
    SUCCESS = "success"
    NO_DATA = "no_data"
    RATE_LIMIT = "rate_limit"
    ERROR = "error"


# ── Konfiguration ────────────────────────────────────────────────────

_OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()
_OPENFIGI_DELAY = 0.25

UNRESOLVABLE_TTL_DAYS: int = 30

_EXCHANGE_SUFFIX: dict[str, str] = {
    "GY": ".DE", "GF": ".F", "AV": ".VI", "AU": ".AX",
    "LN": ".L", "FP": ".PA", "SM": ".MC", "SW": ".SW",
    "IM": ".MI", "HK": ".HK", "JP": ".T", "BB": ".BR",
    "NA": ".AS", "DC": ".CO", "SS": ".ST", "HE": ".HE",
    "OS": ".OL",
}

_ISIN_PRIMARY_EXCHANGE: dict[str, str] = {
    "US": "US", "CA": "US",
    "DE": "GY", "AT": "AV", "CH": "SW", "GB": "LN",
    "FR": "FP", "IT": "IM", "ES": "SM", "NL": "NA",
    "BE": "BB", "DK": "DC", "SE": "SS", "FI": "HE",
    "NO": "OS", "AU": "AU", "HK": "HK", "JP": "JP",
}

_FALLBACK_EXCHANGES: tuple[str, ...] = (
    "US", "GY", "LN", "FP", "SW", "NA", "BB"
)

_ISIN_PREFIXES_SKIP_YF_DIRECT: frozenset[str] = frozenset({
    "AT", "AU", "HK", "JP", "SG", "NZ",
})


# ── DB ──────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_db(isin: str, db_path: Path = DB_PATH):
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT ticker, source, updated_at FROM ticker_mapping WHERE isin = ?",
            (isin,),
        ).fetchone()

    if not row:
        return None, None

    if row["source"] == "unresolvable":
        try:
            stored_at = datetime.fromisoformat(row["updated_at"])
            if datetime.now() - stored_at < timedelta(days=UNRESOLVABLE_TTL_DAYS):
                return None, "unresolvable"
            _delete_mapping(isin, db_path)
            return None, None
        except Exception:
            return None, None

    return row["ticker"], row["source"]


def _store_mapping(isin: str, ticker: str, source: str,
                   exchange: str | None = None,
                   db_path: Path = DB_PATH):
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


def _store_unresolvable(isin: str, db_path: Path = DB_PATH):
    _store_mapping(isin, "NOT_FOUND", source="unresolvable", db_path=db_path)


def _delete_mapping(isin: str, db_path: Path = DB_PATH):
    with _get_connection(db_path) as conn:
        conn.execute("DELETE FROM ticker_mapping WHERE isin = ?", (isin,))
        conn.commit()


# ── Exchange Auswahl ────────────────────────────────────────────────

def _get_preferred_exchanges(isin: str):
    primary = _ISIN_PRIMARY_EXCHANGE.get(isin[:2].upper())
    if primary:
        others = tuple(ex for ex in _FALLBACK_EXCHANGES if ex != primary)
        return (primary,) + others
    return _FALLBACK_EXCHANGES


def _select_best_figi(results: list[dict], isin: str = ""):
    if not results:
        return None

    preferred = _get_preferred_exchanges(isin) if isin else _FALLBACK_EXCHANGES

    for exchange in preferred:
        for item in results:
            if item.get("exchCode") == exchange:
                return item

    return results[0]


# ── Validation ──────────────────────────────────────────────────────

def _apply_suffix(ticker: str, exchange: str | None):
    if exchange and exchange in _EXCHANGE_SUFFIX:
        suffix = _EXCHANGE_SUFFIX[exchange]
        if not ticker.endswith(suffix):
            return ticker + suffix
    return ticker


def _validate_ticker(ticker: str, exchange: str | None = None) -> str | None:
    suffixed = _apply_suffix(ticker, exchange)
    # Duplikat vermeiden wenn kein Suffix angewendet wurde
    candidates: list[str] = [suffixed]
    if suffixed != ticker:
        candidates.append(ticker)

    for candidate in candidates:
        try:
            info = yf.Ticker(candidate).info
            if info.get("symbol") or info.get("quoteType"):
                logger.debug("Ticker validiert: %s", candidate)
                return candidate
        except Exception:
            continue
    return None

# ── OpenFIGI intern (NEU) ───────────────────────────────────────────

def _resolve_via_openfigi_internal(isin: str, db_path: Path = DB_PATH):
    headers = {"Content-Type": "application/json"}
    if _OPENFIGI_APIKEY:
        headers["X-OPENFIGI-APIKEY"] = _OPENFIGI_APIKEY

    try:
        r = requests.post(
            _OPENFIGI_URL,
            json=[{"idType": "ID_ISIN", "idValue": isin}],
            headers=headers,
            timeout=10,
        )
        time.sleep(_OPENFIGI_DELAY)

        if r.status_code == 429:
            return None, ResolveStatus.RATE_LIMIT
        if r.status_code != 200:
            return None, ResolveStatus.ERROR

        data = r.json()
        if not data or "warning" in data[0]:
            return None, ResolveStatus.NO_DATA

        best = _select_best_figi(data[0].get("data", []), isin)
        if not best:
            return None, ResolveStatus.NO_DATA

        ticker = _validate_ticker(best["ticker"], best.get("exchCode"))
        if not ticker:
            return None, ResolveStatus.NO_DATA

        _store_mapping(isin, ticker, "openfigi", best.get("exchCode"), db_path)
        return ticker, ResolveStatus.SUCCESS

    except Exception:
        return None, ResolveStatus.ERROR


# ── OpenFIGI public (kompatibel) ────────────────────────────────────

def _resolve_via_openfigi(isin: str, db_path: Path = DB_PATH):
    ticker, _ = _resolve_via_openfigi_internal(isin, db_path)
    return ticker


# ── yfinance ───────────────────────────────────────────────────────

def _resolve_via_yfinance(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """Letzter Fallback. Gibt String oder None zurück (kein Tupel)."""
    if isin[:2].upper() in _ISIN_PREFIXES_SKIP_YF_DIRECT:
        logger.debug("yfinance-Direktauflösung für %s übersprungen.", isin[:2])
        return None

    try:
        info     = yf.Ticker(isin).info
        symbol   = info.get("symbol")
        exchange = info.get("exchange")

        if not symbol:
            logger.debug("yfinance: kein Symbol für %s", isin)
            return None

        logger.info("yfinance (Fallback): %s → %s (Börse: %s)", isin, symbol, exchange)
        _store_mapping(isin, symbol, "yfinance", exchange, db_path)
        return symbol

    except Exception as exc:
        logger.warning("yfinance fehlgeschlagen für %s: %s", isin, exc)
        return None

# ── Public API ─────────────────────────────────────────────────────

def resolve(
    isin: str,
    db_path: Path = DB_PATH,
    skip_openfigi: bool = False,
) -> str | None:
    ticker, source = _lookup_db(isin, db_path)
    if source == "unresolvable":
        return None
    if ticker:
        logger.debug("Ticker aus DB-Cache: %s → %s", isin, ticker)
        return ticker

    openfigi_found = False
    if not skip_openfigi:
        ticker, status = _resolve_via_openfigi_internal(isin, db_path)
        if ticker:
            return ticker
        openfigi_found = (status == ResolveStatus.NO_DATA)

    ticker = _resolve_via_yfinance(isin, db_path)
    if ticker:
        return ticker

    # Nur als unresolvable markieren wenn beide Quellen NO_DATA meldeten
    # (nicht bei RATE_LIMIT oder ERROR — dann später erneut versuchen)
    if openfigi_found or skip_openfigi:
        _store_unresolvable(isin, db_path)

    return None

def store_manual_mapping(isin: str, ticker: str,
                         exchange: str | None = None,
                         db_path: Path = DB_PATH):
    _store_mapping(isin, ticker, "manual", exchange, db_path)
