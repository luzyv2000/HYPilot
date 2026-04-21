# Dateiname:     core/sources/yfinance_source.py
# Version:       2026-04-21
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): yfinance
"""
core/sources/yfinance_source.py

Implementiert DividendSource via yfinance.

Bekannte Einschränkungen von yfinance:
  - dividendYield im info-Dict ist nicht immer vorhanden oder aktuell
  - dividends-Historie kann lückenhaft sein
  - Keine Garantie für Datenverfügbarkeit (Yahoo ändert API ohne Ankündigung)

Alle empfangenen float-Werte werden sofort via Decimal konvertiert.
Kein float verlässt dieses Modul.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

import yfinance as yf

from core.dividend_source import (
    DividendPayment,
    DividendSnapshot,
    DividendSource,
    float_to_bps,
    float_to_micro,
)

logger = logging.getLogger(__name__)

# Minimale Historie in Jahren für Frequenzberechnung
_HISTORY_YEARS: int = 3


def _detect_frequency(payments: list[DividendPayment]) -> str | None:
    """
    Leitet die Ausschüttungsfrequenz aus der Zahlungshistorie ab.
    Zählt Zahlungen im letzten vollständigen Jahr.
    """
    if not payments:
        return None

    now = date.today()
    last_year_payments = [
        p for p in payments
        if (now - p.ex_date).days <= 365
    ]
    count = len(last_year_payments)

    if count == 0:
        return None
    if count >= 10:
        return "monthly"
    if count >= 3:
        return "quarterly"
    if count >= 2:
        return "semi_annual"
    if count == 1:
        return "annual"
    return "irregular"


class YFinanceSource(DividendSource):
    """Dividenden-Datenquelle via yfinance."""

    @property
    def source_name(self) -> str:
        return "yfinance"

    def fetch_snapshot(
        self,
        isin: str,
        ticker: str,
    ) -> DividendSnapshot | None:
        """
        Liefert aggregierte Dividenden-Kennzahlen via yfinance.
        Gibt None zurück wenn keine Daten verfügbar oder Ticker ungültig.
        """
        logger.debug("Hole Snapshot für %s (%s)", isin, ticker)

        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            if not info or info.get("symbol") is None:
                logger.warning(
                    "yfinance: kein gültiger info-Dict für %s (%s)",
                    isin, ticker,
                )
                return None

            # ── Rohdaten aus yfinance ────────────────────────────────────────
            raw_yield = info.get("dividendYield")          # float, z.B. 0.105
            raw_payout = info.get("payoutRatio")           # float, z.B. 0.65
            raw_last_div = info.get("lastDividendValue")   # float, z.B. 0.25
            raw_last_date = info.get("lastDividendDate")   # Unix-Timestamp int
            currency = info.get("currency", "USD")

            # ── Konvertierung (float → int, niemals float weiterreichen) ─────
            yield_bps = float_to_bps(raw_yield)
            payout_bps = float_to_bps(raw_payout)
            last_amount_micro = float_to_micro(raw_last_div)

            last_ex_date: date | None = None
            if raw_last_date:
                try:
                    last_ex_date = datetime.fromtimestamp(raw_last_date).date()
                except (OSError, ValueError, OverflowError) as exc:
                    logger.warning(
                        "Ungültiger lastDividendDate für %s: %s", ticker, exc
                    )

            # ── Frequenz aus Historie ────────────────────────────────────────
            history = self.fetch_history(isin, ticker)
            frequency = _detect_frequency(history)

            snapshot = DividendSnapshot(
                isin=isin,
                yield_bps=yield_bps,
                frequency=frequency,
                last_amount_micro=last_amount_micro,
                last_ex_date=last_ex_date,
                currency=currency,
                payout_ratio_bps=payout_bps,
                data_source=self.source_name,
            )

            logger.info(
                "Snapshot: %s → Rendite %s bps, Frequenz %s",
                isin,
                yield_bps,
                frequency,
            )
            return snapshot

        except Exception:
            logger.exception(
                "Unerwarteter Fehler beim Snapshot-Abruf für %s (%s)",
                isin, ticker,
            )
            return None

    def fetch_history(
        self,
        isin: str,
        ticker: str,
    ) -> list[DividendPayment]:
        """
        Liefert historische Dividendenzahlungen der letzten _HISTORY_YEARS Jahre.
        Gibt leere Liste zurück bei Fehlern oder fehlenden Daten.
        """
        logger.debug("Hole Historie für %s (%s)", isin, ticker)

        try:
            ticker_obj = yf.Ticker(ticker)
            dividends = ticker_obj.dividends  # pandas Series

            if dividends is None or dividends.empty:
                logger.debug("Keine Dividenden-Historie für %s", ticker)
                return []

            currency = ticker_obj.info.get("currency", "USD")
            cutoff = date.today().replace(
                year=date.today().year - _HISTORY_YEARS
            )

            payments: list[DividendPayment] = []

            for timestamp, amount_raw in dividends.items():
                try:
                    ex_date = timestamp.date()
                except AttributeError:
                    ex_date = datetime.fromtimestamp(
                        int(timestamp) / 1e9
                    ).date()

                if ex_date < cutoff:
                    continue

                amount_micro = float_to_micro(float(amount_raw))
                if amount_micro is None or amount_micro <= 0:
                    continue

                payments.append(
                    DividendPayment(
                        isin=isin,
                        ex_date=ex_date,
                        amount_micro=amount_micro,
                        currency=currency,
                        data_source=self.source_name,
                    )
                )

            logger.info(
                "Historie: %s → %d Zahlungen (letzte %d Jahre)",
                isin, len(payments), _HISTORY_YEARS,
            )
            return payments

        except Exception:
            logger.exception(
                "Fehler beim Abruf der Dividenden-Historie für %s (%s)",
                isin, ticker,
            )
            return []