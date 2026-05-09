# Dateiname:     core/dividend_source.py
# Version:       2026-05-08-cascade-fix2
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine
"""
core/dividend_source.py

Abstrakte Basisklasse und Datenmodelle für Dividenden-Datenquellen.

Änderungen:
  2026-05-08         : ticker-Parameter optional (Default "")
  2026-05-08-fix1    : micro_to_decimal hinzugefügt
  2026-05-08-fix2    : float_to_bps rundet statt trunciert;
                       DividendSnapshot erhält yield_percent-Property,
                       meets_yield_threshold()-Methode und
                       __post_init__-Validierung für frequency.

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
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


# ── Gültige Frequenz-Werte ────────────────────────────────────────────────────

VALID_FREQUENCIES: frozenset[str] = frozenset({
    "monthly", "quarterly", "semi_annual", "annual", "irregular",
})


# ── Konvertierungshilfen ──────────────────────────────────────────────────────

def float_to_bps(value: float | None) -> int | None:
    """
    float 0.055 → 550 bps. None-safe.
    Verwendet ROUND_HALF_UP via Decimal um Truncation-Fehler zu vermeiden.
    Beispiel: 0.10555 → 1056 (nicht 1055).
    """
    if value is None:
        return None
    try:
        d = Decimal(str(value)) * 10_000
        return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def float_to_micro(value: float | None) -> int | None:
    """float 0.271 → 271_000 micro-units. None-safe."""
    if value is None:
        return None
    try:
        d = Decimal(str(value)) * 1_000_000
        return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return None


def bps_to_decimal(bps: int | None) -> Decimal | None:
    """550 bps → Decimal('0.0550'). None-safe."""
    if bps is None:
        return None
    return Decimal(bps) / Decimal(10_000)


def micro_to_decimal(micro: int | None) -> Decimal | None:
    """271_000 micro → Decimal('0.271000'). None-safe."""
    if micro is None:
        return None
    return Decimal(micro) / Decimal(1_000_000)


# ── Datenmodelle ──────────────────────────────────────────────────────────────

@dataclass
class DividendSnapshot:
    """
    Aggregierte Dividenden-Kennzahlen für ein Instrument.

    Validierung in __post_init__:
      frequency: Werte außerhalb von VALID_FREQUENCIES → None gesetzt.
                 Verhindert ungültige Werte in der DB (chk_frequency-Constraint).
    """
    isin:              str
    yield_bps:         int | None
    frequency:         str | None
    last_amount_micro: int | None
    last_ex_date:      date | None
    currency:          str
    payout_ratio_bps:  int | None
    data_source:       str

    def __post_init__(self) -> None:
        # Ungültige Frequenz-Werte auf None normalisieren
        if self.frequency is not None and self.frequency not in VALID_FREQUENCIES:
            self.frequency = None

    # ── Abgeleitete Eigenschaften ─────────────────────────────────────────────

    @property
    def last_amount(self) -> Decimal | None:
        """Letzter Dividendenbetrag als Decimal (für Anzeige)."""
        return micro_to_decimal(self.last_amount_micro)

    @property
    def yield_percent(self) -> Decimal | None:
        """
        Rendite als Decimal-Prozentwert.
        550 bps → Decimal('0.0550')
        """
        return bps_to_decimal(self.yield_bps)

    def meets_yield_threshold(self, threshold: Decimal) -> bool:
        """
        Prüft ob die Rendite den angegebenen Schwellwert erreicht oder
        überschreitet.

        Args:
            threshold: Schwellwert als Decimal (z.B. Decimal('0.10') für 10%)

        Returns:
            False wenn yield_bps None ist.
        """
        yp = self.yield_percent
        if yp is None:
            return False
        return yp >= threshold


@dataclass
class DividendPayment:
    """Einzelne Dividendenzahlung aus der Historie."""
    isin:         str
    ex_date:      date
    amount_micro: int
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