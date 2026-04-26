# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-25-final
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

import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# ── Konfiguration ─────────────────────────────────────────────────────────────

_OPENFIGI_URL    = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()
_OPENFIGI_DELAY  = 0.25  # 4 req/sec — weit unter 25/min ohne Key

# Wie lange ein 'unresolvable'-Eintrag gilt (danach erneut versuchen)
UNRESOLVABLE_TTL_DAYS: int = 30

# OpenFIGI exchCode → yfinance-Ticker-Suffix
_EXCHANGE_SUFFIX: dict[str, str] = {
    "GY": ".DE",  "GF": ".F",   "AV": ".VI",  "AU": ".AX",
    "LN": ".L",   "FP": ".PA",  "SM": ".MC",  "SW": ".SW",
    "IM": ".MI",  "HK": ".HK",  "JP": ".T",   "BB": ".BR",
    "NA": ".AS",  "DC": ".CO",  "SS": ".ST",  "HE": ".HE",
    "OS": ".OL",
}

# ISIN-Länderpräfix → bevorzugter OpenFIGI exchCode (Primärbörse)
_ISIN_PRIMARY_EXCHANGE: dict[str, str] = {
    "US": "US", "CA": "US",
    "DE": "GY", "AT": "AV", "CH": "SW", "GB": "LN",
    "FR": "FP", "IT": "IM", "ES": "SM", "NL": "NA",
    "BE": "BB", "DK": "DC", "SE": "SS", "FI": "HE",
    "NO": "OS", "AU": "AU", "HK": "HK", "JP": "JP",
}

# Standard-Fallback wenn kein Eintrag in _ISIN_PRIMARY_EXCHANGE
_FALLBACK_EXCHANGES: tuple[str, ...] = (
    "GY", "LN", "FP", "SW", "NA", "BB", "US",
)

# Für diese ISIN-Präfixe schlägt yfinance-Direktauflösung zuverlässig fehl
_ISIN_PREFIXES_SKIP_YF_DIRECT: frozenset[str] = frozenset({
    "AT", "AU", "HK", "JP", "SG", "NZ",
})


# ── DB-Operationen ────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_db(
    isin: str,
    db_path: Path = DB_PATH,
) -> tuple[str | None, str | None]:
    """
    Sucht ISIN in der lokalen DB.

    Returns:
        (ticker, source) oder (None, None) wenn nicht gefunden.
        source='unresolvable' → kein API-Call nötig.
    """
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
                logger.debug(
                    "ISIN %s als unresolvable markiert (bis %s) — übersprungen.",
                    isin,
                    (stored_at + timedelta(days=UNRESOLVABLE_TTL_DAYS)).date(),
                )
                return None, "unresolvable"
            # TTL abgelaufen → erneut versuchen
            logger.info("Unresolvable-TTL für %s abgelaufen — erneuter Versuch.", isin)
            _delete_mapping(isin, db_path)
            return None, None
        except (ValueError, TypeError):
            return None, None

    return row["ticker"], row["source"]


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
    logger.debug(
        "Mapping gespeichert: %s → %s (Quelle: %s, Börse: %s)",
        isin, ticker, source, exchange,
    )


def _store_unresolvable(isin: str, db_path: Path = DB_PATH) -> None:
    """Markiert ISIN als nicht auflösbar für UNRESOLVABLE_TTL_DAYS."""
    _store_mapping(isin, "NOT_FOUND", source="unresolvable", db_path=db_path)
    logger.info(
        "ISIN %s als unresolvable markiert (%d Tage).",
        isin, UNRESOLVABLE_TTL_DAYS,
    )


def _delete_mapping(isin: str, db_path: Path = DB_PATH) -> None:
    """Löscht ein Mapping (z. B. nach TTL-Ablauf)."""
    with _get_connection(db_path) as conn:
        conn.execute("DELETE FROM ticker_mapping WHERE isin = ?", (isin,))
        conn.commit()


# ── Exchange-Präferenz ────────────────────────────────────────────────────────

def _get_preferred_exchanges(isin: str) -> tuple[str, ...]:
    """
    Gibt Börsenpräferenz-Reihenfolge für eine ISIN zurück.
    Heimatbörse zuerst — verhindert OTC/ADR-Bevorzugung für EU-Titel.
    """
    primary = _ISIN_PRIMARY_EXCHANGE.get(isin[:2].upper())
    if primary:
        others = tuple(ex for ex in _FALLBACK_EXCHANGES if ex != primary)
        return (primary,) + others
    return _FALLBACK_EXCHANGES


def _apply_suffix(ticker: str, exchange: str | None) -> str:
    """Gibt Ticker mit yfinance-Suffix zurück. ('CLEN', 'AV') → 'CLEN.VI'"""
    if exchange and exchange in _EXCHANGE_SUFFIX:
        suffix = _EXCHANGE_SUFFIX[exchange]
        if not ticker.endswith(suffix):
            return ticker + suffix
    return ticker


def _validate_ticker(ticker: str, exchange: str | None = None) -> str | None:
    """
    Prüft Ticker via yfinance. Versucht zuerst mit Suffix, dann ohne.

    Returns:
        Valides Symbol (ggf. mit Suffix) oder None.
    """
    candidates: list[str] = []
    suffixed = _apply_suffix(ticker, exchange)
    if suffixed != ticker:
        candidates.append(suffixed)
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


# ── OpenFIGI ──────────────────────────────────────────────────────────────────

def _select_best_figi(results: list[dict], isin: str = "") -> dict | None:
    """
    Wählt bestes OpenFIGI-Ergebnis anhand ISIN-land-basierter Präferenz.
    isin-Parameter optional für Abwärtskompatibilität.
    """
    if not results:
        return None
    preferred = _get_preferred_exchanges(isin) if isin else _FALLBACK_EXCHANGES
    for exchange in preferred:
        for item in results:
            if item.get("exchCode") == exchange:
                return item
    return results[0]


def _resolve_via_openfigi(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """Löst ISIN via OpenFIGI auf, validiert Ticker mit Suffix-Support."""
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if _OPENFIGI_APIKEY:
        headers["X-OPENFIGI-APIKEY"] = _OPENFIGI_APIKEY

    try:
        response = requests.post(
            _OPENFIGI_URL,
            json=[{"idType": "ID_ISIN", "idValue": isin}],
            headers=headers,
            timeout=10,
        )
        time.sleep(_OPENFIGI_DELAY)

        if response.status_code == 429:
            logger.warning("OpenFIGI Rate-Limit für %s.", isin)
            return None
        if response.status_code != 200:
            logger.warning("OpenFIGI HTTP %s für %s.", response.status_code, isin)
            return None

        data = response.json()
        if not data or not isinstance(data, list):
            return None

        first = data[0]
        if "warning" in first:
            logger.debug("OpenFIGI: kein Ergebnis für %s — %s", isin, first["warning"])
            return None

        best = _select_best_figi(first.get("data", []), isin)
        if not best:
            return None

        raw_ticker = best.get("ticker")
        exchange   = best.get("exchCode")
        if not raw_ticker:
            return None

        validated = _validate_ticker(raw_ticker, exchange)
        if not validated:
            logger.warning(
                "OpenFIGI-Ticker %s für %s nicht validiert — verwerfe.",
                raw_ticker, isin,
            )
            return None

        logger.info("OpenFIGI: %s → %s (Börse: %s) ✓", isin, validated, exchange)
        _store_mapping(isin, validated, source="openfigi",
                       exchange=exchange, db_path=db_path)
        return validated

    except requests.RequestException as exc:
        logger.warning("OpenFIGI fehlgeschlagen für %s: %s", isin, exc)
        return None
    except Exception:
        logger.exception("Unerwarteter Fehler bei OpenFIGI für %s", isin)
        return None


# ── yfinance-Fallback ─────────────────────────────────────────────────────────

def _resolve_via_yfinance(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """Letzter Fallback. Für bekannte inkompatible ISIN-Präfixe deaktiviert."""
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
        _store_mapping(isin, symbol, source="yfinance",
                       exchange=exchange, db_path=db_path)
        return symbol

    except Exception as exc:
        logger.warning("yfinance fehlgeschlagen für %s: %s", isin, exc)
        return None


# ── Öffentliche API ───────────────────────────────────────────────────────────

def resolve(
    isin: str,
    db_path: Path = DB_PATH,
    skip_openfigi: bool = False,
) -> str | None:
    """
    Löst ISIN → Ticker auf (DB → OpenFIGI → yfinance).
    Nicht auflösbare ISINs werden für UNRESOLVABLE_TTL_DAYS gecacht.
    """
    ticker, source = _lookup_db(isin, db_path)
    if source == "unresolvable":
        return None
    if ticker:
        logger.debug("Ticker aus DB-Cache: %s → %s", isin, ticker)
        return ticker

    if not skip_openfigi:
        ticker = _resolve_via_openfigi(isin, db_path)
        if ticker:
            return ticker

    ticker = _resolve_via_yfinance(isin, db_path)
    if ticker:
        return ticker

    _store_unresolvable(isin, db_path)
    return None


def store_manual_mapping(
    isin: str,
    ticker: str,
    exchange: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Manuelles Mapping — überschreibt alles inkl. 'unresolvable'."""
    _store_mapping(isin, ticker, source="manual", exchange=exchange, db_path=db_path)
    logger.info("Manuelles Mapping gespeichert: %s → %s", isin, ticker)