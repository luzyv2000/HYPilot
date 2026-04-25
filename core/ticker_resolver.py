# Dateiname:     core/ticker_resolver.py
# Version:       2026-04-25
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): requests, python-dotenv, yfinance
"""
core/ticker_resolver.py

Löst ISIN → Ticker-Symbol auf.

Auflösungsstrategie (drei Stufen):
  1. Lokale DB (ticker_mapping)  — sofort, offline
     Sonderfall: source='unresolvable' → sofort None zurück (kein API-Call)
  2. OpenFIGI + Exchange-Suffix  — mit ISIN-land-basierter Börsenpräferenz
  3. yfinance-Direktabfrage      — Fallback; für bestimmte ISIN-Präfixe deaktiviert

ISIN-land-basierte Börsenpräferenz:
  Für nicht-amerikanische ISINs wird die heimische Börse bevorzugt,
  US-Listings (häufig OTC/ADR) werden als letztes betrachtet.
  Verhindert dass DE0005557508 → DTEGF statt DTE.DE auflöst.

Unresolvable-Tracking:
  ISINs die in keiner Quelle gefunden werden, erhalten einen DB-Eintrag
  mit source='unresolvable'. Nächster resolve()-Aufruf gibt sofort None
  zurück ohne API-Call. Einträge älter als UNRESOLVABLE_TTL_DAYS werden
  automatisch erneut versucht (Marktänderungen möglich).

Sicherheit:
  - API-Key wird ausschließlich aus .env geladen
  - Key wird niemals geloggt
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

# ── OpenFIGI-Konfiguration ───────────────────────────────────────────────────

_OPENFIGI_URL    = "https://api.openfigi.com/v3/mapping"
_OPENFIGI_APIKEY = os.getenv("OPENFIGI_API_KEY", "").strip()
_OPENFIGI_DELAY  = 0.25  # 4 req/sec — weit unter 25/min ohne Key

# Wie lange ein 'unresolvable'-Eintrag gültig bleibt (danach erneut versuchen)
UNRESOLVABLE_TTL_DAYS: int = 30

# OpenFIGI exchCode → yfinance-Ticker-Suffix
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

# ISIN-Länderpräfix → bevorzugter OpenFIGI exchCode (Primärbörse)
# Wenn OpenFIGI mehrere Listings zurückgibt, wird dieses zuerst geprüft.
_ISIN_PRIMARY_EXCHANGE: dict[str, str] = {
    "US": "US",
    "CA": "US",   # Kanadische ADRs oft US-listed, sonst fallback
    "DE": "GY",
    "AT": "AV",
    "CH": "SW",
    "GB": "LN",
    "FR": "FP",
    "IT": "IM",
    "ES": "SM",
    "NL": "NA",
    "BE": "BB",
    "DK": "DC",
    "SE": "SS",
    "FI": "HE",
    "NO": "OS",
    "AU": "AU",
    "HK": "HK",
    "JP": "JP",
}

# Standard-Fallback-Reihenfolge wenn ISIN-Länderpräfix nicht in _ISIN_PRIMARY_EXCHANGE
_FALLBACK_EXCHANGES: tuple[str, ...] = (
    "GY", "LN", "FP", "SW", "NA", "BB", "US",
)

# Für diese ISIN-Präfixe schlägt yfinance-Direktauflösung mit "Invalid ISIN" fehl
_ISIN_PREFIXES_SKIP_YF_DIRECT: frozenset[str] = frozenset({
    "AT", "AU", "HK", "JP", "SG", "NZ",
})


# ── DB-Operationen ────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _lookup_db(isin: str, db_path: Path = DB_PATH) -> tuple[str | None, str | None]:
    """
    Sucht ISIN in der lokalen DB.

    Returns:
        (ticker, source) — (None, None) wenn nicht gefunden.
        source='unresolvable' signalisiert: kein API-Call nötig.
    """
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT ticker, source, updated_at FROM ticker_mapping WHERE isin = ?",
            (isin,),
        ).fetchone()

    if not row:
        return None, None

    # Unresolvable-Einträge auf TTL prüfen
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
            # TTL abgelaufen → Eintrag löschen, erneut versuchen
            logger.info(
                "Unresolvable-TTL für %s abgelaufen — erneuter Auflösungsversuch.",
                isin,
            )
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
    """
    Markiert eine ISIN als dauerhaft nicht auflösbar.
    Verhindert wiederholte API-Calls für den TTL-Zeitraum.
    """
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


# ── Exchange-Präferenz-Logik ──────────────────────────────────────────────────

def _get_preferred_exchanges(isin: str) -> tuple[str, ...]:
    """
    Gibt die Börsenpräferenz-Reihenfolge für eine ISIN zurück.

    Nicht-US-ISINs bekommen ihre Heimatbörse zuerst, US als Fallback.
    Verhindert OTC/ADR-Bevorzugung für europäische Titel.
    """
    country = isin[:2].upper()
    primary = _ISIN_PRIMARY_EXCHANGE.get(country)

    if primary:
        # Primärbörse zuerst, dann alle anderen ohne Duplikate
        others = tuple(
            ex for ex in _FALLBACK_EXCHANGES if ex != primary
        )
        return (primary,) + others

    return _FALLBACK_EXCHANGES


def _select_best_figi(results: list[dict], isin: str) -> dict | None:
    """
    Wählt das beste Ergebnis aus einer OpenFIGI-Antwortliste.
    Verwendet ISIN-land-basierte Präferenzreihenfolge.
    """
    if not results:
        return None

    preferred = _get_preferred_exchanges(isin)
    for exchange in preferred:
        for item in results:
            if item.get("exchCode") == exchange:
                return item

    return results[0]


# ── Ticker-Validierung ────────────────────────────────────────────────────────

def _apply_suffix(ticker: str, exchange: str | None) -> str:
    """Gibt Ticker mit yfinance-Suffix zurück falls Börse bekannt."""
    if exchange and exchange in _EXCHANGE_SUFFIX:
        suffix = _EXCHANGE_SUFFIX[exchange]
        if not ticker.endswith(suffix):
            return ticker + suffix
    return ticker


def _validate_ticker(ticker: str, exchange: str | None = None) -> str | None:
    """
    Prüft ob ein Ticker von yfinance erkannt wird.

    Versucht zuerst Ticker + Exchange-Suffix, dann Ticker pur.

    Returns:
        Valides Ticker-Symbol (ggf. mit Suffix) oder None.
    """
    candidates: list[str] = []

    suffixed = _apply_suffix(ticker, exchange)
    if suffixed != ticker:
        candidates.append(suffixed)
    candidates.append(ticker)

    for candidate in candidates:
        try:
            info = yf.Ticker(candidate).info
