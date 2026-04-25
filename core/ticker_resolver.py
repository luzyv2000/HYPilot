# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-24
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): requests, python-dotenv, yfinance
"""
core/ticker_resolver.py

Löst ISIN → Ticker-Symbol auf.

Auflösungsstrategie (drei Stufen):
  1. Lokale DB (ticker_mapping)       — sofort, offline
  2. OpenFIGI API + Exchange-Suffix   — zuverlässig, mit Suffix-Validierung
  3. yfinance-Direktabfrage           — Fallback (nur für US-ISINs zuverlässig)

Exchange-Suffix-Logik:
  OpenFIGI liefert exchCode (z. B. 'AV' für Wien).
  Ohne Suffix schlägt yfinance für regionale Ticker fehl.
  Das Mapping _EXCHANGE_SUFFIX übersetzt exchCode → yfinance-Suffix.
  Validierung versucht erst Ticker pur, dann Ticker + Suffix.

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

# ── OpenFIGI-Konfiguration ───────────────────────────────────────────────────

_OPENFIGI_URL    = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()
_OPENFIGI_DELAY  = 0.25  # 4 req/sec → weit unter 25/min ohne Key

# Bevorzugte Börsen-Reihenfolge (erste Übereinstimmung gewinnt)
_PREFERRED_EXCHANGES: tuple[str, ...] = (
    "US",   # NYSE / NASDAQ
    "GY",   # XETRA
    "LN",   # London
    "FP",   # Paris
    "GF",   # Frankfurt
    "SW",   # Schweiz
    "AV",   # Wien
    "AU",   # ASX Australien
)

# OpenFIGI exchCode → yfinance-Ticker-Suffix
# Ohne Suffix scheitert yfinance bei regionalen Titeln (z. B. CLEN statt CLEN.VI)
_EXCHANGE_SUFFIX: dict[str, str] = {
    "GY": ".DE",   # XETRA
    "GF": ".F",    # Frankfurt
    "AV": ".VI",   # Wien
    "AU": ".AX",   # ASX Australien
    "LN": ".L",    # London
    "FP": ".PA",   # Paris
    "SM": ".MC",   # Madrid
    "SW": ".SW",   # Schweiz
    "IM": ".MI",   # Mailand
    "HK": ".HK",   # Hongkong
    "JP": ".T",    # Tokio
    "BB": ".BR",   # Brüssel
    "NA": ".AS",   # Amsterdam
    "DC": ".CO",   # Kopenhagen
    "SS": ".ST",   # Stockholm
    "HE": ".HE",   # Helsinki
    "OS": ".OL",   # Oslo
}

# ISINs die yfinance direkt nicht auflösen kann (zu strenge interne Validierung)
# Für diese Länder-Präfixe den yfinance-Direktfallback überspringen.
_ISIN_PREFIXES_SKIP_YF_DIRECT: frozenset[str] = frozenset({
    "AT",  # Österreich
    "AU",  # Australien
    "HK",  # Hongkong
    "JP",  # Japan
    "SG",  # Singapur
    "NZ",  # Neuseeland
})


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
    logger.debug(
        "Mapping gespeichert: %s → %s (Quelle: %s, Börse: %s)",
        isin, ticker, source, exchange,
    )


# ── Exchange-Suffix-Logik ─────────────────────────────────────────────────────

def _apply_suffix(ticker: str, exchange: str | None) -> str:
    """
    Gibt Ticker mit yfinance-Suffix zurück falls bekannt.
    Beispiel: ('CLEN', 'AV') → 'CLEN.VI'
    """
    if exchange and exchange in _EXCHANGE_SUFFIX:
        suffix = _EXCHANGE_SUFFIX[exchange]
        if not ticker.endswith(suffix):
            return ticker + suffix
    return ticker


def _validate_ticker(ticker: str, exchange: str | None = None) -> str | None:
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


# ── OpenFIGI-Auflösung ────────────────────────────────────────────────────────

def _select_best_figi(results: list[dict]) -> dict | None:
    """
    Wählt das beste Ergebnis aus einer OpenFIGI-Antwortliste.
    Bevorzugt bekannte Primärbörsen in _PREFERRED_EXCHANGES-Reihenfolge.
    """
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
    Berücksichtigt Exchange-Suffix für regionale Ticker.
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
            logger.warning("OpenFIGI Rate-Limit für %s — verwende yfinance.", isin)
            return None

        if response.status_code != 200:
            logger.warning("OpenFIGI HTTP %s für %s.", response.status_code, isin)
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

        items   = first.get("data", [])
        best    = _select_best_figi(items)
        if not best:
            return None

        raw_ticker = best.get("ticker")
        exchange   = best.get("exchCode")

        if not raw_ticker:
            return None

        logger.debug(
            "OpenFIGI: %s → %s (Börse: %s) — validiere ...",
            isin, raw_ticker, exchange,
        )

        # Validierung mit Exchange-Suffix-Unterstützung
        validated_ticker = _validate_ticker(raw_ticker, exchange)
        if not validated_ticker:
            logger.warning(
                "OpenFIGI-Ticker %s für %s von yfinance nicht erkannt"
                " — verwerfe und versuche yfinance-Direktauflösung.",
                raw_ticker, isin,
            )
            return None

        logger.info(
            "OpenFIGI: %s → %s (Börse: %s) ✓ validiert",
            isin, validated_ticker, exchange,
        )
        _store_mapping(
            isin, validated_ticker,
            source="openfigi",
            exchange=exchange,
            db_path=db_path,
        )
        return validated_ticker

    except requests.RequestException as exc:
        logger.warning("OpenFIGI-Anfrage fehlgeschlagen für %s: %s", isin, exc)
        return None
    except Exception:
        logger.exception("Unerwarteter Fehler bei OpenFIGI für %s", isin)
        return None


# ── yfinance-Direktauflösung ──────────────────────────────────────────────────

def _resolve_via_yfinance(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """
    Versucht ISIN direkt via yfinance aufzulösen. Letzter Fallback.

    Für ISINs mit Länder-Präfixen in _ISIN_PREFIXES_SKIP_YF_DIRECT wird
    der Versuch übersprungen — yfinance validiert diese intern zu streng
    und liefert nur „Invalid ISIN number".
    """
    country_prefix = isin[:2].upper()
    if country_prefix in _ISIN_PREFIXES_SKIP_YF_DIRECT:
        logger.debug(
            "yfinance-Direktauflösung für ISIN-Präfix %s übersprungen"
            " (bekannte Inkompatibilität).",
            country_prefix,
        )
        return None

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
        logger.warning(
            "yfinance-Auflösung fehlgeschlagen für %s: %s", isin, exc
        )
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
      1. Lokale DB (sofort)
      2. OpenFIGI API (mit Exchange-Suffix-Validierung)
      3. yfinance (Fallback; für einige Länder-Präfixe deaktiviert)

    Args:
        isin:          ISIN des Instruments
        db_path:       Pfad zur SQLite-DB
        skip_openfigi: True = OpenFIGI überspringen (z. B. in Tests)

    Returns:
        Ticker-Symbol oder None wenn nicht auflösbar.
    """
    # Stufe 1: DB-Cache
    ticker = _lookup_db(isin, db_path)
    if ticker:
        logger.debug("Ticker aus DB-Cache: %s → %s", isin, ticker)
        return ticker

    # Stufe 2: OpenFIGI
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
    """
    Speichert ein manuell erfasstes ISIN→Ticker-Mapping.
    Überschreibt automatisch ermittelte Mappings.
    """
    _store_mapping(isin, ticker, source="manual", exchange=exchange, db_path=db_path)
    logger.info("Manuelles Mapping gespeichert: %s → %s", isin, ticker)