# Dateiname:     core/sources/divvydiary_source.py
# Version:       2026-05-08
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): requests, python-dotenv
"""
core/sources/divvydiary_source.py

DivvyDiary REST-API Adapter.

API-Endpunkt:  https://api.divvydiary.com/symbols/{ISIN}
Authentifikation: Bearer-Token via DIVVYDIARY_API_KEY in .env
Rate-Limit Free Tier: ~100 Requests/Tag → 429 wird abgefangen,
  Quelle überspringt bei 429 ohne Fehler.

Antwortstruktur (vereinfacht):
  {
    "isin": "...",
    "currency": "EUR",
    "dividendYield": 0.055,          # Dezimalform
    "payoutRatio": 0.65,
    "dividends": [
      {"exDate": "2025-03-15", "amount": 0.271, "frequency": "monthly"},
      ...
    ]
  }

HINWEIS: Endpunkt-URL und Feldnamen via DIVVYDIARY_BASE_URL in .env
  überschreibbar — ermöglicht Anpassung ohne Code-Änderung falls API
  sich ändert.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime
from decimal import Decimal

import requests
from dotenv import load_dotenv
from pathlib import Path

from core.dividend_source import (
    DividendPayment,
    DividendSnapshot,
    DividendSource,
    float_to_bps,
    float_to_micro,
)

load_dotenv(dotenv_path=Path(__file__).parent.parent.parent / ".env")

logger = logging.getLogger(__name__)

_BASE_URL    = os.getenv("DIVVYDIARY_BASE_URL", "https://api.divvydiary.com")
_API_KEY     = os.getenv("DIVVYDIARY_API_KEY", "").strip()
_TIMEOUT     = 10
_DELAY       = 0.5          # Sekunden zwischen Requests (höfliches Crawling)
_HISTORY_YEARS = 3


def _detect_frequency(payments: list[DividendPayment]) -> str | None:
    """Leitet Frequenz aus Zahlungsanzahl im letzten Jahr ab."""
    if not payments:
        return None
    today = date.today()
    count = sum(1 for p in payments if (today - p.ex_date).days <= 365)
    if count == 0:
        return None
    if count >= 10:
        return "monthly"
    if count >= 3:
        return "quarterly"
    if count == 2:
        return "semi_annual"
    if count == 1:
        return "annual"
    return "irregular"


class DivvyDiarySource(DividendSource):
    """Dividenden-Datenquelle via DivvyDiary REST-API."""

    @property
    def source_name(self) -> str:
        return "divvydiary"

    def fetch_snapshot(
        self,
        isin: str,
        ticker: str = "",
    ) -> DividendSnapshot | None:

        if not _API_KEY:
            logger.debug("DivvyDiary: kein API-Key konfiguriert — übersprungen.")
            return None

        url = f"{_BASE_URL}/symbols/{isin}"
        headers = {
            "Authorization": f"Bearer {_API_KEY}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=_TIMEOUT)
            time.sleep(_DELAY)

            if response.status_code == 404:
                logger.debug("DivvyDiary: kein Eintrag für %s.", isin)
                return None

            if response.status_code == 429:
                logger.warning(
                    "DivvyDiary: Rate-Limit erreicht — Quelle für diesen Lauf übersprungen."
                )
                return None

            if response.status_code != 200:
                logger.warning(
                    "DivvyDiary: HTTP %d für %s.", response.status_code, isin
                )
                return None

            data = response.json()

        except requests.RequestException as exc:
            logger.warning("DivvyDiary: Netzwerkfehler für %s: %s", isin, exc)
            return None
        except Exception:
            logger.exception("DivvyDiary: unerwarteter Fehler für %s.", isin)
            return None

        # Daten extrahieren
        raw_yield    = data.get("dividendYield")
        raw_payout   = data.get("payoutRatio")
        currency     = data.get("currency", "EUR")

        yield_bps   = float_to_bps(raw_yield)
        payout_bps  = float_to_bps(raw_payout)

        # Letztes Ex-Datum + Betrag aus Dividenden-Liste
        history = self.fetch_history(isin, ticker)

        last_amount_micro: int | None = None
        last_ex_date:      date | None = None

        if history:
            latest = max(history, key=lambda p: p.ex_date)
            last_ex_date      = latest.ex_date
            last_amount_micro = latest.amount_micro

        frequency = _detect_frequency(history)

        if yield_bps is None and not history:
            logger.debug("DivvyDiary: keine verwertbaren Daten für %s.", isin)
            return None

        logger.info(
            "DivvyDiary: %s → %s bps, Frequenz %s",
            isin, yield_bps, frequency,
        )

        return DividendSnapshot(
            isin=isin,
            yield_bps=yield_bps,
            frequency=frequency,
            last_amount_micro=last_amount_micro,
            last_ex_date=last_ex_date,
            currency=currency,
            payout_ratio_bps=payout_bps,
            data_source=self.source_name,
        )

    def fetch_history(
        self,
        isin: str,
        ticker: str = "",
    ) -> list[DividendPayment]:

        if not _API_KEY:
            return []

        url = f"{_BASE_URL}/symbols/{isin}"
        headers = {
            "Authorization": f"Bearer {_API_KEY}",
            "Accept": "application/json",
        }

        try:
            response = requests.get(url, headers=headers, timeout=_TIMEOUT)
            time.sleep(_DELAY)

            if response.status_code != 200:
                return []

            data = response.json()

        except Exception:
            logger.debug("DivvyDiary: fetch_history fehlgeschlagen für %s.", isin)
            return []

        raw_dividends = data.get("dividends", [])
        if not isinstance(raw_dividends, list):
            return []

        currency = data.get("currency", "EUR")
        cutoff   = date.today().replace(year=date.today().year - _HISTORY_YEARS)
        payments: list[DividendPayment] = []

        for entry in raw_dividends:
            try:
                ex_date_str = entry.get("exDate") or entry.get("ex_date", "")
                if not ex_date_str:
                    continue
                ex_date = date.fromisoformat(ex_date_str[:10])
                if ex_date < cutoff:
                    continue

                amount_raw   = entry.get("amount") or entry.get("value")
                amount_micro = float_to_micro(float(amount_raw)) if amount_raw else None
                if not amount_micro or amount_micro <= 0:
                    continue

                payments.append(DividendPayment(
                    isin=isin,
                    ex_date=ex_date,
                    amount_micro=amount_micro,
                    currency=currency,
                    data_source=self.source_name,
                ))
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug(
                    "DivvyDiary: Eintrag übersprungen für %s: %s", isin, exc
                )
                continue

        logger.info(
            "DivvyDiary: %s → %d Zahlungen (letzte %d Jahre)",
            isin, len(payments), _HISTORY_YEARS,
        )
        return payments