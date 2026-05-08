# Dateiname:     core/sources/boerse_frankfurt_source.py
# Version:       2026-05-08
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): requests, python-dotenv
"""
core/sources/boerse_frankfurt_source.py

Boerse Frankfurt / Deutsche Börse Datenfeed-Adapter.

API-Endpunkt:
  GET https://api.boerse-frankfurt.de/v1/data/dividend_information
      ?isin={ISIN}&mic=XETR

Öffentlicher Datenfeed ohne API-Key. Kein Rate-Limit dokumentiert;
0.5s Delay als höfliches Crawling. HTTP-Header User-Agent gesetzt.

Antwortstruktur (vereinfacht):
  {
    "data": [
      {
        "exDate": "2025-04-02",
        "dividendValue": 0.77,
        "currency": "EUR",
        "frequency": "annual"
      },
      ...
    ]
  }

Geeignet für: DE, AT, CH, NL, FR und weitere Xetra-gelistete Titel.
Für nicht-Xetra-Titel (US, GB, AU, ...) liefert dieser Endpunkt
typischerweise keine oder unvollständige Daten → Kaskade fällt
auf yfinance zurück.
"""

from __future__ import annotations

import logging
import time
from datetime import date
from pathlib import Path

import requests

from core.dividend_source import (
    DividendPayment,
    DividendSnapshot,
    DividendSource,
    float_to_bps,
    float_to_micro,
)

logger = logging.getLogger(__name__)

_BASE_URL  = "https://api.boerse-frankfurt.de/v1/data/dividend_information"
_MIC       = "XETR"
_TIMEOUT   = 10
_DELAY     = 0.5
_HISTORY_YEARS = 3

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.boerse-frankfurt.de/",
}

# Frequenz-Mapping aus boerse-frankfurt-Feldern
_FREQ_MAP: dict[str, str] = {
    "annual":      "annual",
    "yearly":      "annual",
    "quarterly":   "quarterly",
    "monthly":     "monthly",
    "semi-annual": "semi_annual",
    "semi_annual": "semi_annual",
    "irregular":   "irregular",
}


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


class BoerseFrankfurtSource(DividendSource):
    """Dividenden-Datenquelle via Boerse Frankfurt / Deutsche Börse Datenfeed."""

    @property
    def source_name(self) -> str:
        return "boerse_frankfurt"

    def fetch_snapshot(
        self,
        isin: str,
        ticker: str = "",
    ) -> DividendSnapshot | None:

        history = self.fetch_history(isin, ticker)
        if not history:
            return None

        # Rendite: letzter Betrag relativ zum aktuellen Kurs ist nicht
        # verfügbar in diesem Feed → yield_bps bleibt None,
        # Stabilität/Frequenz/Historie werden trotzdem gespeichert.
        # Die Kaskade füllt yield_bps ggf. aus einer anderen Quelle —
        # da wir aber sequenziell vorgehen und bei erster Antwort stoppen,
        # wird boerse-frankfurt nur genutzt wenn DivvyDiary keinen Treffer
        # liefert. yield_bps=None führt zu 0 Rendite-Punkten im Scorer,
        # aber Frequenz/Stabilität fließen ein.

        latest = max(history, key=lambda p: p.ex_date)

        frequency = _detect_frequency(history)

        # Versuche yield_bps aus den Rohdaten zu lesen (falls vorhanden)
        yield_bps = self._fetch_yield_bps(isin)

        logger.info(
            "BoerseFrankfurt: %s → %s bps, Frequenz %s, %d Zahlungen",
            isin, yield_bps, frequency, len(history),
        )

        return DividendSnapshot(
            isin=isin,
            yield_bps=yield_bps,
            frequency=frequency,
            last_amount_micro=latest.amount_micro,
            last_ex_date=latest.ex_date,
            currency=latest.currency,
            payout_ratio_bps=None,   # Nicht im Feed verfügbar
            data_source=self.source_name,
        )

    def fetch_history(
        self,
        isin: str,
        ticker: str = "",
    ) -> list[DividendPayment]:

        params = {"isin": isin, "mic": _MIC}

        try:
            response = requests.get(
                _BASE_URL,
                params=params,
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            time.sleep(_DELAY)

            if response.status_code == 404:
                logger.debug("BoerseFrankfurt: kein Eintrag für %s.", isin)
                return []

            if response.status_code != 200:
                logger.warning(
                    "BoerseFrankfurt: HTTP %d für %s.",
                    response.status_code, isin,
                )
                return []

            data = response.json()

        except requests.RequestException as exc:
            logger.warning(
                "BoerseFrankfurt: Netzwerkfehler für %s: %s", isin, exc
            )
            return []
        except Exception:
            logger.exception(
                "BoerseFrankfurt: unerwarteter Fehler für %s.", isin
            )
            return []

        entries = data.get("data", [])
        if not isinstance(entries, list) or not entries:
            logger.debug("BoerseFrankfurt: leere Antwort für %s.", isin)
            return []

        cutoff   = date.today().replace(year=date.today().year - _HISTORY_YEARS)
        payments: list[DividendPayment] = []

        for entry in entries:
            try:
                ex_date_str = entry.get("exDate", "")
                if not ex_date_str:
                    continue
                ex_date = date.fromisoformat(ex_date_str[:10])
                if ex_date < cutoff:
                    continue

                amount_raw   = entry.get("dividendValue")
                amount_micro = float_to_micro(float(amount_raw)) if amount_raw else None
                if not amount_micro or amount_micro <= 0:
                    continue

                currency = entry.get("currency", "EUR")

                payments.append(DividendPayment(
                    isin=isin,
                    ex_date=ex_date,
                    amount_micro=amount_micro,
                    currency=currency,
                    data_source=self.source_name,
                ))
            except (KeyError, ValueError, TypeError) as exc:
                logger.debug(
                    "BoerseFrankfurt: Eintrag übersprungen für %s: %s",
                    isin, exc,
                )
                continue

        logger.info(
            "BoerseFrankfurt: %s → %d Zahlungen (letzte %d Jahre)",
            isin, len(payments), _HISTORY_YEARS,
        )
        return payments

    def _fetch_yield_bps(self, isin: str) -> int | None:
        """
        Versucht Dividendenrendite aus dem Key-Data-Endpunkt zu lesen.
        Gibt None zurück wenn nicht verfügbar — kein harter Fehler.
        """
        try:
            url = "https://api.boerse-frankfurt.de/v1/data/key_data"
            response = requests.get(
                url,
                params={"isin": isin, "mic": _MIC},
                headers=_HEADERS,
                timeout=_TIMEOUT,
            )
            time.sleep(_DELAY)

            if response.status_code != 200:
                return None

            data    = response.json()
            raw     = data.get("dividendYield")  # Erwartet: Dezimalform 0.055
            return float_to_bps(float(raw)) if raw is not None else None

        except Exception:
            return None