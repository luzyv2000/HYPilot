# Dateiname:     core/sources/yfinance_source.py
# Version:       2026-04-22-fix2
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): yfinance
"""
core/sources/yfinance_source.py

Implementiert DividendSource via yfinance.

Bekannte Eigenheiten (yfinance):
  - dividendYield: je nach Version Dezimalzahl (0.055) oder
    Prozentwert (5.5) — wird normalisiert auf Dezimalzahl
  - dividends: liefert je nach Version Series oder DataFrame,
    Index enthält gelegentlich String-Einträge ('Dividends')
  - Keine API-Stabilitätsgarantie
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import yfinance as yf

from core.dividend_source import (
    DividendPayment,
    DividendSnapshot,
    DividendSource,
    float_to_bps,
    float_to_micro,
)

logger = logging.getLogger(__name__)

_HISTORY_YEARS: int = 3


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _normalize_yield(raw: float | None) -> float | None:
    """
    Normalisiert dividendYield auf Dezimalform (0.055 = 5.5%).

    yfinance liefert je nach Version:
      - Dezimalzahl: 0.055  → direkt verwenden
      - Prozentwert: 5.5    → durch 100 dividieren

    Grenzwert: Werte > 1.0 werden als Prozentwert behandelt.
    Plausibilitätsgrenze: > 99.0 (= 9900%) wird als Datenfehler verworfen.
    """
    if raw is None:
        return None
    if raw > 99.0:
        logger.warning(
            "dividendYield = %.4f — unplausibler Wert (>9900%%), wird verworfen.",
            raw,
        )
        return None
    if raw > 1.0:
        logger.debug(
            "dividendYield = %.4f — als Prozentwert interpretiert → %.6f",
            raw, raw / 100,
        )
        return raw / 100
    return raw

def _detect_frequency(payments: list[DividendPayment]) -> str | None:
    """Leitet Ausschüttungsfrequenz aus Zahlungsanzahl im letzten Jahr ab."""
    if not payments:
        return None
    now = date.today()
    count = sum(
        1 for p in payments
        if (now - p.ex_date).days <= 365
    )
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


def _parse_dividends_series(raw) -> pd.Series:
    """
    Normalisiert die Rückgabe von ticker.dividends.

    yfinance liefert je nach Version:
      - pandas.Series mit DatetimeIndex
      - pandas.DataFrame mit Spalte 'Dividends'

    Gibt immer eine Series mit DatetimeIndex zurück.
    """
    if isinstance(raw, pd.DataFrame):
        if "Dividends" in raw.columns:
            return raw["Dividends"]
        # erste numerische Spalte nehmen
        numeric_cols = raw.select_dtypes(include="number").columns
        if len(numeric_cols) > 0:
            return raw[numeric_cols[0]]
        logger.warning("dividends-DataFrame hat keine numerische Spalte.")
        return pd.Series(dtype=float)

    if isinstance(raw, pd.Series):
        return raw

    logger.warning("Unbekannter dividends-Typ: %s", type(raw))
    return pd.Series(dtype=float)


# ── DividendSource-Implementierung ────────────────────────────────────────────

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
        logger.debug("Hole Snapshot für %s (%s)", isin, ticker)
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            if not info or info.get("symbol") is None:
                logger.warning(
                    "Kein gültiger info-Dict für %s (%s)", isin, ticker
                )
                return None

            # ── Rohdaten ────────────────────────────────────────────────────
            raw_yield   = info.get("dividendYield")
            raw_payout  = info.get("payoutRatio")
            raw_last    = info.get("lastDividendValue")
            raw_date    = info.get("lastDividendDate")
            currency    = info.get("currency", "USD")

            # ── Normalisierung + Konvertierung ───────────────────────────────
            normalized_yield = _normalize_yield(raw_yield)
            yield_bps        = float_to_bps(normalized_yield)
            payout_bps       = float_to_bps(raw_payout)
            last_micro       = float_to_micro(raw_last)

            last_ex_date: date | None = None
            if raw_date:
                try:
                    last_ex_date = datetime.fromtimestamp(
                        int(raw_date)
                    ).date()
                except (OSError, ValueError, OverflowError, TypeError) as exc:
                    logger.warning(
                        "Ungültiger lastDividendDate für %s: %s", ticker, exc
                    )

            # ── Frequenz aus Historie ────────────────────────────────────────
            history   = self.fetch_history(isin, ticker)
            frequency = _detect_frequency(history)

            snapshot = DividendSnapshot(
                isin=isin,
                yield_bps=yield_bps,
                frequency=frequency,
                last_amount_micro=last_micro,
                last_ex_date=last_ex_date,
                currency=currency,
                payout_ratio_bps=payout_bps,
                data_source=self.source_name,
            )

            logger.info(
                "Snapshot: %s → Rendite %s bps (%.2f%%), Frequenz %s",
                isin,
                yield_bps,
                (yield_bps / 100) if yield_bps else 0,
                frequency,
            )
            return snapshot

        except Exception:
            logger.exception(
                "Unerwarteter Fehler beim Snapshot für %s (%s)", isin, ticker
            )
            return None

    def fetch_history(
        self,
        isin: str,
        ticker: str,
    ) -> list[DividendPayment]:
        logger.debug("Hole Historie für %s (%s)", isin, ticker)
        try:
            ticker_obj = yf.Ticker(ticker)
            raw        = ticker_obj.dividends
            dividends  = _parse_dividends_series(raw)

            if dividends.empty:
                logger.debug("Keine Dividenden-Historie für %s", ticker)
                return []

            currency = ticker_obj.info.get("currency", "USD")
            cutoff   = date.today().replace(
                year=date.today().year - _HISTORY_YEARS
            )

            payments: list[DividendPayment] = []

            for timestamp, amount_raw in dividends.items():
                # ── Timestamp normalisieren ──────────────────────────────────
                ex_date: date | None = None

                if isinstance(timestamp, str):
                    # String-Einträge ('Dividends' o.ä.) überspringen
                    logger.debug(
                        "String-Index übersprungen: %r", timestamp
                    )
                    continue

                try:
                    ex_date = pd.Timestamp(timestamp).date()
                except Exception:
                    logger.debug(
                        "Timestamp nicht parsebar: %r — übersprungen",
                        timestamp,
                    )
                    continue

                if ex_date < cutoff:
                    continue

                # ── Betrag konvertieren ──────────────────────────────────────
                try:
                    amount_micro = float_to_micro(float(amount_raw))
                except (TypeError, ValueError):
                    logger.debug(
                        "Ungültiger Betrag %r — übersprungen", amount_raw
                    )
                    continue

                if amount_micro is None or amount_micro <= 0:
                    continue

                payments.append(DividendPayment(
                    isin=isin,
                    ex_date=ex_date,
                    amount_micro=amount_micro,
                    currency=currency,
                    data_source=self.source_name,
                ))

            logger.info(
                "Historie: %s → %d Zahlungen (letzte %d Jahre)",
                isin, len(payments), _HISTORY_YEARS,
            )
            return payments

        except Exception:
            logger.exception(
                "Fehler bei Dividenden-Historie für %s (%s)", isin, ticker
            )
            return []