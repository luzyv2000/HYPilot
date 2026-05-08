# Dateiname:     core/dividend_source.py
# Version:       2026-05-08-cascade
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine
"""
core/dividend_source.py

Abstrakte Basisklasse und Datenmodelle für Dividenden-Datenquellen.

Änderung 2026-05-08: ticker-Parameter in fetch_snapshot / fetch_history
auf Default "" gesetzt — ermöglicht ISIN-native Quellen (DivvyDiary,
boerse-frankfurt.de) ohne Dummy-Ticker-Übergabe.

Finanz-Konventionen:
  yield_bps        : INTEGER, Basispunkte (1% = 100 bps)
  last_amount_micro: INTEGER, Micro-Units  (1 EUR = 1_000_000)
  payout_ratio_bps : INTEGER, Basispunkte (100% = 10000 bps)

Alle Konvertierungen via decimal.Decimal — kein float.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation


# ── Konvertierungshilfen ──────────────────────────────────────────────────────

def float_to_bps(value: float | None) -> int | None:
    """float 0.055 → 550 bps. None-safe."""
    if value is None:
        return None
    try:
        return int(Decimal(str(value)) * 10_000)
    except (InvalidOperation, ValueError):
        return None


def float_to_micro(value: float | None) -> int | None:
    """float 0.271 → 271_000 micro-units. None-safe."""
    if value is None:
        return None
    try:
        return int(Decimal(str(value)) * 1_000_000)
    except (InvalidOperation, ValueError):
        return None


def bps_to_decimal(bps: int | None) -> Decimal | None:
    """550 bps → Decimal('0.0550'). None-safe."""
    if bps is None:
        return None
    return Decimal(bps) / Decimal(10_000)


# ── Datenmodelle ──────────────────────────────────────────────────────────────

@dataclass
class DividendSnapshot:
    """Aggregierte Dividenden-Kennzahlen für ein Instrument."""
    isin:              str
    yield_bps:         int | None        # Rendite in Basispunkten
    frequency:         str | None        # monthly/quarterly/semi_annual/annual/irregular
    last_amount_micro: int | None        # Letzter Betrag in Micro-Units
    last_ex_date:      date | None       # Letztes Ex-Datum
    currency:          str               # ISO-4217
    payout_ratio_bps:  int | None        # Ausschüttungsquote in Basispunkten
    data_source:       str               # Quellenbezeichnung

    @property
    def last_amount(self) -> Decimal | None:
        """Betrag als Decimal (für Anzeige)."""
        if self.last_amount_micro is None:
            return None
        return Decimal(self.last_amount_micro) / Decimal(1_000_000)


@dataclass
class DividendPayment:
    """Einzelne Dividendenzahlung aus der Historie."""
    isin:         str
    ex_date:      date
    amount_micro: int     # Betrag in Micro-Units
    currency:     str
    data_source:  str


# ── Abstrakte Basisklasse ─────────────────────────────────────────────────────

class DividendSource(ABC):
    """
    Abstrakte Schnittstelle für Dividenden-Datenquellen.

    ticker ist optional (Default ""):
      - yfinance:          ticker erforderlich (z.B. "O", "DTE.DE")
      - DivvyDiary:        arbeitet direkt mit ISIN
      - boerse-frankfurt:  arbeitet direkt mit ISIN
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Eindeutiger Quellenname (wird in data_source-Spalte gespeichert)."""
        ...

    @abstractmethod
    def fetch_snapshot(
        self,
        isin: str,
        ticker: str = "",
    ) -> DividendSnapshot | None:
        """
        Holt aggregierte Kennzahlen für eine ISIN.

        Returns:
            DividendSnapshot oder None wenn Quelle keine Daten liefert.
        """
        ...

    @abstractmethod
    def fetch_history(
        self,
        isin: str,
        ticker: str = "",
    ) -> list[DividendPayment]:
        """
        Holt Dividenden-Einzelzahlungen der letzten Jahre.

        Returns:
            Liste von DividendPayment, leer wenn keine Daten verfügbar.
        """
        ...