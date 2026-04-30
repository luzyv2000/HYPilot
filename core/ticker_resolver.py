# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-30-fix2
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): requests, python-dotenv, yfinance
"""
core/ticker_resolver.py  —  ISIN → Ticker-Auflösung.

Auflösungsstrategie (drei Stufen):
  1. Lokale DB  — sofort, offline; 'unresolvable' → sofort None
  2. OpenFIGI   — ISIN-land-basierte Börsenpräferenz,
                  regionale Validierungsstrategie
  3. yfinance   — Fallback; für bestimmte Präfixe deaktiviert

Validierungsstrategie:
  Mainstream (US/CA/DE/GB): yfinance-Validierung ERFORDERLICH
  Exotisch:                 OpenFIGI-Ergebnis reicht →
                            als 'openfigi_unvalidated' gespeichert
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

import requests
import yfinance as yf
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Statusmodell ──────────────────────────────────────────────────────────────

class ResolveStatus(str, Enum):
    SUCCESS    = "success"
    NO_DATA    = "no_data"
    RATE_LIMIT = "rate_limit"
    ERROR      = "error"


# ── Konfiguration ─────────────────────────────────────────────────────────────

_OPENFIGI_URL    = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()
_OPENFIGI_DELAY  = 0.25

UNRESOLVABLE_TTL_DAYS: int = 30

_EXCHANGE_SUFFIX: dict[str, str] = {
    "GY": ".DE", "GF": ".F",  "AV": ".VI", "AU": ".AX",
    "LN": ".L",  "FP": ".PA", "SM": ".MC", "SW": ".SW",
    "IM": ".MI", "HK": ".HK", "JP": ".T",  "BB": ".BR",
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
    "US", "GY", "LN", "FP", "SW", "NA", "BB",
)

_ISIN_PREFIXES_SKIP_YF_DIRECT: frozenset[str] = frozenset({
    "AT", "AU", "HK", "JP", "SG", "NZ",
})

# Für diese Präfixe ist yfinance-Validierung ZWINGEND erforderlich.
# Schlägt sie fehl → kein Speichern.
_ISIN_PREFIXES_REQUIRE_YF_VALIDATION: frozenset[str] = frozenset({
    "US", "CA", "DE", "GB",
})


# ── DB ────────────────────────────────────────────────────────────────────────

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
            "SELECT ticker, source, updated_at "
            "FROM ticker_mapping WHERE isin = ?",
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
    logger.info("ISIN %s als unresolvable markiert (%d Tage).",
                isin, UNRESOLVABLE_TTL_DAYS)


def _delete_mapping(isin: str, db_path: Path = DB_PATH) -> None:
    with _get_connection(db_path) as conn:
        conn.execute("DELETE FROM ticker_mapping WHERE isin = ?", (isin,))
        conn.commit()


# ── Exchange-Präferenz ────────────────────────────────────────────────────────

def _get_preferred_exchanges(isin: str) -> tuple[str, ...]:
    """
    Börsenpräferenz-Reihenfolge für eine ISIN.
    Heimatbörse zuerst — verhindert OTC/ADR-Bevorzugung für EU-Titel.
    """
    primary = _ISIN_PRIMARY_EXCHANGE.get(isin[:2].upper())
    if primary:
        others = tuple(ex for ex in _FALLBACK_EXCHANGES if ex != primary)
        return (primary,) + others
    return _FALLBACK_EXCHANGES


def _select_best_figi(
    results: list[dict],
    isin: str = "",
) -> dict | None:
    """Wählt bestes OpenFIGI-Ergebnis anhand ISIN-land-basierter Präferenz."""
    if not results:
        return None
    preferred = _get_preferred_exchanges(isin) if isin else _FALLBACK_EXCHANGES
    for exchange in preferred:
        for item in results:
            if item.get("exchCode") == exchange:
                return item
    return results[0]


# ── Ticker-Validierung ────────────────────────────────────────────────────────

def _apply_suffix(ticker: str, exchange: str | None) -> str:
    """(ticker='DTE', exchange='GY') → 'DTE.DE'"""
    if exchange and exchange in _EXCHANGE_SUFFIX:
        suffix = _EXCHANGE_SUFFIX[exchange]
        if not ticker.endswith(suffix):
            return ticker + suffix
    return ticker


def _validate_ticker_with_retry(
    ticker: str,
    exchange: str | None = None,
    max_retries: int = 2,
) -> str | None:
    """
    Validiert Ticker via yfinance.

    Strategie:
      1. Suffixed Ticker probieren (z. B. DTE.DE)
      2. Fallback: unsuffixed (z. B. DTE)
    Retry nur bei HTTP-500-Fehlern (Exponential Backoff).
    Leeres Info-Dict → sofort nächsten Kandidaten probieren (kein Retry).
    """
    suffixed = _apply_suffix(ticker, exchange)
    candidates: list[str] = [suffixed]
    if suffixed != ticker:
        candidates.append(ticker)

    for candidate in candidates:
        for attempt in range(max_retries):
            try:
                info = yf.Ticker(candidate).info
                if info.get("symbol") or info.get("quoteType"):
                    logger.debug("Ticker validiert: %s", candidate)
                    return candidate
                # Leeres Info-Dict → kein Retry, nächsten Kandidaten versuchen
                break
            except Exception as exc:
                if "500" in str(exc) and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.debug("yfinance 500 — Retry in %ds: %s",
                                 wait, str(exc)[:80])
                    time.sleep(wait)
                    continue
                logger.debug("yfinance-Validierung fehlgeschlagen für %s: %s",
                             candidate, str(exc)[:80])
                break

    return None


def _validate_ticker(
    ticker: str,
    exchange: str | None = None,
) -> str | None:
    """Wrapper für Abwärtskompatibilität."""
    return _validate_ticker_with_retry(ticker, exchange)


# ── OpenFIGI ──────────────────────────────────────────────────────────────────

def _resolve_via_openfigi_internal(
    isin: str,
    db_path: Path = DB_PATH,
) -> tuple[str | None, ResolveStatus]:
    """
    OpenFIGI-Auflösung mit intelligenter regionaler Validierung.

    Mainstream (US/CA/DE/GB): yfinance-Validierung ERFORDERLICH.
      Fehlschlag → (None, NO_DATA)
    Exotisch:                 OpenFIGI-Ergebnis reicht.
      Fehlschlag → (raw_ticker, SUCCESS) als 'openfigi_unvalidated'
    """
    headers: dict[str, str] = {"Content-Type": "application/json"}
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
            logger.warning("OpenFIGI Rate-Limit für %s.", isin)
            return None, ResolveStatus.RATE_LIMIT
        if r.status_code != 200:
            logger.warning("OpenFIGI HTTP %s für %s.", r.status_code, isin)
            return None, ResolveStatus.ERROR

        data = r.json()
        if not data or "warning" in data[0]:
            logger.debug("OpenFIGI: kein Ergebnis für %s.", isin)
            return None, ResolveStatus.NO_DATA

        best = _select_best_figi(data[0].get("data", []), isin)
        if not best:
            return None, ResolveStatus.NO_DATA

        raw_ticker: str | None = best.get("ticker")
        exchange:   str | None = best.get("exchCode")

        if not raw_ticker:
            return None, ResolveStatus.NO_DATA

        validated = _validate_ticker(raw_ticker, exchange)

        if validated:
            _store_mapping(isin, validated, "openfigi", exchange, db_path)
            logger.info("OpenFIGI (validiert): %s → %s", isin, validated)
            return validated, ResolveStatus.SUCCESS

        # Validierung fehlgeschlagen
        isin_prefix = isin[:2].upper()
        if isin_prefix in _ISIN_PREFIXES_REQUIRE_YF_VALIDATION:
            logger.debug(
                "OpenFIGI (Validierung fehlgeschlagen, Mainstream): %s → %s",
                isin, raw_ticker,
            )
            return None, ResolveStatus.NO_DATA
        else:
            # Exotischer Markt: trotzdem speichern
            _store_mapping(isin, raw_ticker, "openfigi_unvalidated",
                           exchange, db_path)
            logger.warning(
                "OpenFIGI (unvalidiert gespeichert): %s → %s (%s)",
                isin, raw_ticker, exchange,
            )
            return raw_ticker, ResolveStatus.SUCCESS

    except Exception:
        logger.exception("OpenFIGI-Fehler für %s.", isin)
        return None, ResolveStatus.ERROR


def _resolve_via_openfigi(isin: str, db_path: Path = DB_PATH) -> str | None:
    """Wrapper für Abwärtskompatibilität (gibt nur Ticker zurück)."""
    ticker, _ = _resolve_via_openfigi_internal(isin, db_path)
    return ticker


# ── yfinance-Fallback ─────────────────────────────────────────────────────────

def _resolve_via_yfinance(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """Letzter Fallback. Für bekannte inkompatible Präfixe deaktiviert."""
    if isin[:2].upper() in _ISIN_PREFIXES_SKIP_YF_DIRECT:
        logger.debug("yfinance-Direktauflösung für Präfix %s übersprungen.",
                     isin[:2])
        return None

    try:
        info     = yf.Ticker(isin).info
        symbol   = info.get("symbol")
        exchange = info.get("exchange")

        if not symbol:
            logger.debug("yfinance: kein Symbol für %s.", isin)
            return None

        logger.info("yfinance (Fallback): %s → %s (Börse: %s)",
                    isin, symbol, exchange)
        _store_mapping(isin, symbol, "yfinance", exchange, db_path)
        return symbol

    except Exception as exc:
        logger.warning("yfinance fehlgeschlagen für %s: %s",
                       isin, str(exc)[:80])
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

    openfigi_no_data = False
    if not skip_openfigi:
        ticker, status = _resolve_via_openfigi_internal(isin, db_path)
        if ticker:
            return ticker
        openfigi_no_data = (status == ResolveStatus.NO_DATA)

    ticker = _resolve_via_yfinance(isin, db_path)
    if ticker:
        return ticker

    # Nur als unresolvable markieren wenn NO_DATA (nicht RATE_LIMIT/ERROR)
    if openfigi_no_data or skip_openfigi:
        _store_unresolvable(isin, db_path)

    return None


def store_manual_mapping(
    isin: str,
    ticker: str,
    exchange: str | None = None,
    db_path: Path = DB_PATH,
) -> None:
    """Manuelles Mapping — überschreibt alles inkl. 'unresolvable'."""
    _store_mapping(isin, ticker, "manual", exchange, db_path)
    logger.info("Manuelles Mapping gespeichert: %s → %s", isin, ticker)