# Dateiname:     tests/test_core/test_dividend_source.py
# Version:       2026-04-22
"""
tests/test_core/test_dividend_source.py

Tests für Konvertierungshelfer und DividendSnapshot-Logik.
Diese Tests sind rein deterministisch — kein Netzwerk, keine DB.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from core.dividend_source import (
    DividendSnapshot,
    bps_to_decimal,
    float_to_bps,
    float_to_micro,
    micro_to_decimal,
)


# ── float_to_bps ──────────────────────────────────────────────────────────────

class TestFloatToBps:

    @pytest.mark.unit
    def test_typical_yield(self) -> None:
        """5,5% → 550 bps."""
        assert float_to_bps(0.055) == 550

    @pytest.mark.unit
    def test_ten_percent(self) -> None:
        """10% → 1000 bps (HYPilot-Kernziel)."""
        assert float_to_bps(0.10) == 1000

    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert float_to_bps(None) is None

    @pytest.mark.unit
    def test_zero(self) -> None:
        assert float_to_bps(0.0) == 0

    @pytest.mark.unit
    def test_rounding(self) -> None:
        """0.10555 → 1056 bps (ROUND_HALF_UP)."""
        result = float_to_bps(0.10555)
        assert result == 1056

    @pytest.mark.unit
    def test_no_float_arithmetic_error(self) -> None:
        """
        Klassischer float-Fehler: 0.1 + 0.2 ≠ 0.3 in float.
        Unsere Konvertierung via str() muss korrekt runden.
        """
        result = float_to_bps(0.1 + 0.2)
        # 0.30000000000000004 → 3000 bps (korrekt gerundet)
        assert result == 3000

    @pytest.mark.unit
    @given(st.floats(min_value=0.0, max_value=1.0,
                     allow_nan=False, allow_infinity=False))
    @settings(max_examples=500)
    def test_result_in_valid_range(self, value: float) -> None:
        """Alle Werte 0–100% → Ergebnis 0–10000 bps."""
        result = float_to_bps(value)
        if result is not None:
            assert 0 <= result <= 10_000


# ── float_to_micro ────────────────────────────────────────────────────────────

class TestFloatToMicro:

    @pytest.mark.unit
    def test_typical_dividend(self) -> None:
        """0.271 USD → 271_000 micro."""
        assert float_to_micro(0.271) == 271_000

    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert float_to_micro(None) is None

    @pytest.mark.unit
    def test_zero(self) -> None:
        assert float_to_micro(0.0) == 0

    @pytest.mark.unit
    def test_rounding_up(self) -> None:
        assert float_to_micro(0.2715) == 271_500


# ── bps_to_decimal / micro_to_decimal ────────────────────────────────────────

class TestRoundtrip:

    @pytest.mark.unit
    def test_bps_roundtrip(self) -> None:
        """550 bps → Decimal → 0.0550."""
        assert bps_to_decimal(550) == Decimal("0.0550")

    @pytest.mark.unit
    def test_micro_roundtrip(self) -> None:
        assert micro_to_decimal(271_000) == Decimal("0.271000")

    @pytest.mark.unit
    def test_none_returns_none(self) -> None:
        assert bps_to_decimal(None) is None
        assert micro_to_decimal(None) is None


# ── DividendSnapshot ──────────────────────────────────────────────────────────

class TestDividendSnapshot:

    @pytest.mark.unit
    def test_yield_percent_property(self, sample_snapshot: DividendSnapshot) -> None:
        """550 bps → 0.0550."""
        assert sample_snapshot.yield_percent == Decimal("0.0550")

    @pytest.mark.unit
    def test_meets_yield_threshold_below(
        self, sample_snapshot: DividendSnapshot
    ) -> None:
        """5.5% erfüllt 10%-Schwelle nicht."""
        assert not sample_snapshot.meets_yield_threshold(Decimal("0.10"))

    @pytest.mark.unit
    def test_meets_yield_threshold_above(
        self, high_yield_snapshot: DividendSnapshot
    ) -> None:
        """12.5% erfüllt 10%-Schwelle."""
        assert high_yield_snapshot.meets_yield_threshold(Decimal("0.10"))

    @pytest.mark.unit
    def test_invalid_frequency_set_to_none(self) -> None:
        """Ungültige Frequenz wird auf None gesetzt."""
        snap = DividendSnapshot(
            isin="US0000000000",
            yield_bps=500,
            frequency="weekly",        # ungültig
            last_amount_micro=100_000,
            last_ex_date=None,
            currency="USD",
            payout_ratio_bps=None,
            data_source="test",
        )
        assert snap.frequency is None

    @pytest.mark.unit
    def test_none_yield_threshold(self) -> None:
        """Kein yield_bps → meets_yield_threshold gibt False zurück."""
        snap = DividendSnapshot(
            isin="US0000000000",
            yield_bps=None,
            frequency=None,
            last_amount_micro=None,
            last_ex_date=None,
            currency="USD",
            payout_ratio_bps=None,
            data_source="test",
        )
        assert not snap.meets_yield_threshold(Decimal("0.05"))
