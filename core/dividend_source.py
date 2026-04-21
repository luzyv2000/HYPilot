# Dateiname:     core/dividend_source.py
# Version:       2026-04-21
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine
"""
core/dividend_source.py

Abstrakte Basisklasse für Dividenden-Datenquellen sowie gemeinsam
genutzte Datenklassen.

Neue Quellen (Divvydiary, eigene DB, etc.) implementieren DividendSource
und registrieren sich in core/dividend_service.py.

Finanz-Konventionen:
  yield_bps         : int, Basispunkte  — 10,5 % → 1050
  amount_micro      : int, Micro-Units  — 0,25 EUR → 250_000
  payout_ratio_bps  : int, Basispunkte  — 65 % → 6500
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)


# ── Konvertierungshelfer ──────────────────────────────────────────────────────

def float_to_bps(value: float | None) -> int | None:
    """
    Konvertiert einen Prozentwert (als Dezimalzahl) in Basispunkte.
    Beispiel: 0.105 → 1050

    Verwendet str()-Umweg um float-Darstellungsfehler zu vermeiden.
    """
    if value is None:
        return None
    try:
        result = Decimal(str(value)) * Decimal("10000")
        return int(result.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        logger.warning("float_to_bps: Konvertierung fehlgeschlagen für %r", value)
        return None


def float_to_micro(value: float | None) -> int | None:
    """
    Konvertiert einen Betrag in Micro-Units.
    Beispiel: 0.25 → 250_000

    Verwendet str()-Umweg um float-Darstellungsfehler zu vermeiden.
    """
    if value is None:
        return None
    try:
        result = Decimal(str(value)) * Decimal("1000000")
        return int(result.to_integral_value(rounding=ROUND_HALF_UP))
    except Exception:
        logger.warning("float_to_micro: Konvertierung fehlgeschlagen für %r", value)
        return None


def bps_to_decimal(bps: int | None) -> Decimal | None:
    """Konvertiert Basispunkte zurück in Decimal-Prozent. 1050 → Decimal('0.1050')"""
    if bps is None:
        return None
    return Decimal(str(bps)) / Decimal("10000")


def micro_to_decimal(micro: int | None) -> Decimal | None:
    """Konvertiert Micro-Units zurück in Decimal-Betrag. 250_000 → Decimal('0.250000')"""
    if micro is None:
        return None
    return Decimal(str(micro)) / Decimal("1000000")


# ── Datenklassen ──────────────────────────────────────────────────────────────

@dataclass
class DividendSnapshot:
    """
    Aggregierte Dividenden-Kennzahlen für ein Instrument.
    Entspricht einer Zeile in dividend_data.
    """
    isin: str
    yield_bps: int | None          # Trailing-12M-Rendite in bps
    frequency: str | None          # 'monthly'|'quarterly'|'semi_annual'|'annual'|'irregular'
    last_amount_micro: int | None  # letzte Ausschüttung in Micro-Units
    last_ex_date: date | None
    currency: str | None
    payout_ratio_bps: int | None   # Ausschüttungsquote in bps
    data_source: str               # 'yfinance', 'divvydiary', 'manual', ...

    VALID_FREQUENCIES: frozenset[str] = field(
        default_factory=lambda: frozenset({
            "monthly", "quarterly", "semi_annual", "annual", "irregular"
        }),
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if self.frequency is not None:
            if self.frequency not in self.VALID_FREQUENCIES:
                logger.warning(
                    "Ungültige Frequenz '%s' für ISIN %s — wird auf None gesetzt.",
                    self.frequency, self.isin,
                )
                self.frequency = None

    @property
    def yield_percent(self) -> Decimal | None:
        """Rendite als Decimal-Prozent für Berechnungen."""
        return bps_to_decimal(self.yield_bps)

    @property
    def last_amount(self) -> Decimal | None:
        """Letzter Ausschüttungsbetrag als Decimal."""
        return micro_to_decimal(self.last_amount_micro)

    def meets_yield_threshold(self, min_yield_percent: Decimal) -> bool:
        """Prüft ob die Rendite den Mindest-Schwellwert erreicht."""
        y = self.yield_percent
        if y is None:
            return False
        return y >= min_yield_percent


@dataclass
class DividendPayment:
    """
    Einzelne Dividendenzahlung. Entspricht einer Zeile in dividend_history.
    """
    isin: str
    ex_date: date
    amount_micro: int   # in Micro-Units der Währung
    currency: str
    data_source: str

    @property
    def amount(self) -> Decimal:
        """Betrag als Decimal für Berechnungen."""
        return micro_to_decimal(self.amount_micro)  # type: ignore[return-value]


# ── Abstrakte Basisklasse ─────────────────────────────────────────────────────

class DividendSource(ABC):
    """
    Abstrakte Basisklasse für alle Dividenden-Datenquellen.

    Implementierungen:
      core/sources/yfinance_source.py  — yfinance (aktiv)
      core/sources/divvydiary_source.py — Divvydiary (geplant)
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Eindeutiger Bezeichner der Quelle (z.B. 'yfinance')."""
        ...

    @abstractmethod
    def fetch_snapshot(
        self,
        isin: str,
        ticker: str,
    ) -> DividendSnapshot | None:
        """
        Liefert aggregierte Dividenden-Kennzahlen.

        Args:
            isin:   ISIN des Instruments
            ticker: Börsen-Ticker (z.B. 'AAPL')

        Returns:
            DividendSnapshot oder None wenn keine Daten verfügbar.
        """
        ...

    @abstractmethod
    def fetch_history(
        self,
        isin: str,
        ticker: str,
    ) -> list[DividendPayment]:
        """
        Liefert historische Einzelzahlungen.

        Args:
            isin:   ISIN des Instruments
            ticker: Börsen-Ticker

        Returns:
            Liste von DividendPayment, leer wenn keine Historie verfügbar.
        """
        ...
