# Dateiname:     tests/test_core/test_conversions_hypothesis.py
# Version:       2026-05-15
# Abhängigkeiten (intern): core.dividend_source, core.dividend_service
# Abhängigkeiten (extern): pytest, hypothesis
"""
tests/test_core/test_conversions_hypothesis.py

Property-based Tests via hypothesis für:
  - float_to_bps()      — float → integer Basispunkte
  - float_to_micro()    — float → integer Micro-Units
  - bps_to_decimal()    — integer Basispunkte → Decimal
  - micro_to_decimal()  — integer Micro-Units → Decimal
  - _is_plausible()     — Rendite-Plausibilitätsprüfung

Warum property-based:
  Parametrize-Tests prüfen bekannte Grenzwerte.
  Hypothesis findet unbekannte Grenzfälle durch systematisches
  Suchen nach Gegenbeispielen — besonders wertvoll bei
  Konvertierungsfunktionen die float-Präzision berühren.

Abgedeckte Eigenschaften:
  - Monotonie: höherer Input → gleicher oder höherer Output
  - Keine Überläufe bei extremen aber validen Werten
  - Rundungsrichtung deterministisch (ROUND_HALF_UP)
  - None-Safety: None-Input → None-Output, nie Exception
  - Nicht-Negativität: nicht-negative Inputs → nicht-negative Outputs
  - Invertierbarkeit: bps_to_decimal(float_to_bps(x)) ≈ x
  - Cap-Konsistenz: _is_plausible respektiert _MAX_PLAUSIBLE_YIELD_BPS
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from core.dividend_source import (
    bps_to_decimal,
    float_to_bps,
    float_to_micro,
    micro_to_decimal,
)
from core.dividend_service import _MAX_PLAUSIBLE_YIELD_BPS, _is_plausible


# ── Strategien ────────────────────────────────────────────────────────────────

# Realistische Dividendenrenditen: 0 % bis 60 % (als Dezimalzahl)
_yield_floats = st.floats(
    min_value=0.0, max_value=0.60,
    allow_nan=False, allow_infinity=False,
)

# Realistische Dividendenbeträge: 0.0001 bis 50.0 (in Währungseinheiten)
_amount_floats = st.floats(
    min_value=0.0001, max_value=50.0,
    allow_nan=False, allow_infinity=False,
)

# Basispunkte: 0 bis 10000 (0 % bis 100 %)
_bps_ints = st.integers(min_value=0, max_value=10_000)

# Micro-Units: 0 bis 50_000_000 (0 bis 50 Währungseinheiten)
_micro_ints = st.integers(min_value=0, max_value=50_000_000)

# yield_bps-Werte rund um den Cap
_near_cap_bps = st.integers(
    min_value=0, max_value=_MAX_PLAUSIBLE_YIELD_BPS + 5_000
)


# ── float_to_bps ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFloatToBpsProperties:

    @given(value=_yield_floats)
    @settings(max_examples=500)
    def test_none_safety_none_input(self, value: float) -> None:
        """None-Input gibt immer None zurück — nie Exception."""
        assert float_to_bps(None) is None

    @given(value=_yield_floats)
    @settings(max_examples=500)
    def test_returns_integer(self, value: float) -> None:
        """Rückgabe ist immer ein Integer."""
        result = float_to_bps(value)
        assert isinstance(result, int)

    @given(value=_yield_floats)
    @settings(max_examples=500)
    def test_non_negative_for_non_negative_input(self, value: float) -> None:
        """Nicht-negativer Input → nicht-negativer Output."""
        result = float_to_bps(value)
        assert result is not None
        assert result >= 0

    @given(a=_yield_floats, b=_yield_floats)
    @settings(max_examples=500)
    def test_monotone(self, a: float, b: float) -> None:
        """Größerer Input → gleicher oder größerer Output (Monotonie)."""
        assume(b >= a)
        r_a = float_to_bps(a)
        r_b = float_to_bps(b)
        assert r_a is not None and r_b is not None
        assert r_b >= r_a

    @given(value=_yield_floats)
    @settings(max_examples=500)
    def test_deterministic(self, value: float) -> None:
        """Zweimaliger Aufruf mit gleichem Input → identisches Ergebnis."""
        assert float_to_bps(value) == float_to_bps(value)

    @given(value=st.floats(min_value=0.0, max_value=1.0,
                            allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_result_in_valid_bps_range(self, value: float) -> None:
        """Input in [0, 1] → Output in [0, 10000]."""
        result = float_to_bps(value)
        assert result is not None
        assert 0 <= result <= 10_000

    @given(value=_yield_floats)
    @settings(max_examples=300)
    def test_roundtrip_approximate(self, value: float) -> None:
        """
        float_to_bps → bps_to_decimal ≈ original.
        Toleranz: ±0.5 bps (Rundungsfehler durch ROUND_HALF_UP).
        """
        bps = float_to_bps(value)
        assert bps is not None
        back = bps_to_decimal(bps)
        assert back is not None
        # Differenz in Basispunkten berechnen
        original_bps = Decimal(str(value)) * 10_000
        diff = abs(back * 10_000 - original_bps)
        assert diff <= Decimal("0.5"), (
            f"Rundungsfehler zu groß: input={value}, bps={bps}, "
            f"back={back}, diff={diff}"
        )


# ── float_to_micro ────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestFloatToMicroProperties:

    @given(value=_amount_floats)
    @settings(max_examples=500)
    def test_returns_integer(self, value: float) -> None:
        """Rückgabe ist immer ein Integer."""
        result = float_to_micro(value)
        assert isinstance(result, int)

    @given(value=_amount_floats)
    @settings(max_examples=500)
    def test_non_negative(self, value: float) -> None:
        """Positiver Input → positiver Output."""
        result = float_to_micro(value)
        assert result is not None
        assert result > 0

    @given(a=_amount_floats, b=_amount_floats)
    @settings(max_examples=500)
    def test_monotone(self, a: float, b: float) -> None:
        """Größerer Input → gleicher oder größerer Output."""
        assume(b >= a)
        r_a = float_to_micro(a)
        r_b = float_to_micro(b)
        assert r_a is not None and r_b is not None
        assert r_b >= r_a

    @given(value=_amount_floats)
    @settings(max_examples=500)
    def test_deterministic(self, value: float) -> None:
        """Deterministisch."""
        assert float_to_micro(value) == float_to_micro(value)

    def test_none_returns_none(self) -> None:
        assert float_to_micro(None) is None

    @given(value=_amount_floats)
    @settings(max_examples=300)
    def test_roundtrip_approximate(self, value: float) -> None:
        """
        float_to_micro → micro_to_decimal ≈ original.
        Toleranz: ±0.5 micro (Rundungsfehler).
        """
        micro = float_to_micro(value)
        assert micro is not None
        back = micro_to_decimal(micro)
        assert back is not None
        original_micro = Decimal(str(value)) * 1_000_000
        diff = abs(back * 1_000_000 - original_micro)
        assert diff <= Decimal("0.5"), (
            f"Rundungsfehler: input={value}, micro={micro}, diff={diff}"
        )


# ── bps_to_decimal ────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBpsToDecimalProperties:

    @given(bps=_bps_ints)
    @settings(max_examples=300)
    def test_returns_decimal(self, bps: int) -> None:
        result = bps_to_decimal(bps)
        assert isinstance(result, Decimal)

    @given(bps=_bps_ints)
    @settings(max_examples=300)
    def test_non_negative(self, bps: int) -> None:
        result = bps_to_decimal(bps)
        assert result is not None
        assert result >= Decimal("0")

    @given(a=_bps_ints, b=_bps_ints)
    @settings(max_examples=300)
    def test_monotone(self, a: int, b: int) -> None:
        assume(b >= a)
        assert bps_to_decimal(b) >= bps_to_decimal(a)  # type: ignore[operator]

    def test_none_returns_none(self) -> None:
        assert bps_to_decimal(None) is None

    @given(bps=_bps_ints)
    @settings(max_examples=300)
    def test_exact_division(self, bps: int) -> None:
        """bps / 10000 muss exakt sein — kein float-Drift."""
        result = bps_to_decimal(bps)
        assert result is not None
        expected = Decimal(bps) / Decimal(10_000)
        assert result == expected


# ── micro_to_decimal ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMicroToDecimalProperties:

    @given(micro=_micro_ints)
    @settings(max_examples=300)
    def test_returns_decimal(self, micro: int) -> None:
        result = micro_to_decimal(micro)
        assert isinstance(result, Decimal)

    @given(micro=_micro_ints)
    @settings(max_examples=300)
    def test_non_negative(self, micro: int) -> None:
        result = micro_to_decimal(micro)
        assert result is not None
        assert result >= Decimal("0")

    def test_none_returns_none(self) -> None:
        assert micro_to_decimal(None) is None

    @given(micro=_micro_ints)
    @settings(max_examples=300)
    def test_exact_division(self, micro: int) -> None:
        """micro / 1_000_000 muss exakt sein."""
        result = micro_to_decimal(micro)
        assert result is not None
        expected = Decimal(micro) / Decimal(1_000_000)
        assert result == expected


# ── _is_plausible ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestIsPlausibleProperties:

    def _make_snapshot(self, yield_bps: int | None):
        from datetime import date
        from core.dividend_source import DividendSnapshot
        return DividendSnapshot(
            isin="US0000000000",
            yield_bps=yield_bps,
            frequency="monthly",
            last_amount_micro=271_000,
            last_ex_date=date(2026, 3, 31),
            currency="USD",
            payout_ratio_bps=6_500,
            data_source="test",
        )

    @given(bps=st.integers(min_value=0, max_value=_MAX_PLAUSIBLE_YIELD_BPS))
    @settings(max_examples=500)
    def test_at_or_below_cap_always_plausible(self, bps: int) -> None:
        """Jeder Wert ≤ Cap ist plausibel."""
        snap = self._make_snapshot(bps)
        assert _is_plausible(snap, "US0000000000") is True

    @given(bps=st.integers(
        min_value=_MAX_PLAUSIBLE_YIELD_BPS + 1,
        max_value=_MAX_PLAUSIBLE_YIELD_BPS + 100_000,
    ))
    @settings(max_examples=500)
    def test_above_cap_always_implausible(self, bps: int) -> None:
        """Jeder Wert > Cap ist implausibel."""
        snap = self._make_snapshot(bps)
        assert _is_plausible(snap, "US0000000000") is False

    def test_none_yield_always_plausible(self) -> None:
        """None-Rendite ist immer plausibel (kein Datenpunkt = kein Ausreißer)."""
        snap = self._make_snapshot(None)
        assert _is_plausible(snap, "US0000000000") is True

    @given(bps=_near_cap_bps)
    @settings(max_examples=500)
    def test_no_exception_for_any_bps(self, bps: int) -> None:
        """_is_plausible darf bei keinem Integer-Input crashen."""
        snap = self._make_snapshot(bps)
        try:
            result = _is_plausible(snap, "XX0000000000")
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"Exception bei yield_bps={bps}: {e}")

    @given(bps=_near_cap_bps)
    @settings(max_examples=500)
    def test_returns_bool(self, bps: int) -> None:
        """Rückgabe ist immer bool."""
        snap = self._make_snapshot(bps)
        assert isinstance(_is_plausible(snap, "US0000000000"), bool)

    @given(bps=st.integers(min_value=0, max_value=_MAX_PLAUSIBLE_YIELD_BPS))
    @settings(max_examples=200)
    def test_deterministic(self, bps: int) -> None:
        """Deterministisch: gleicher Input → gleicher Output."""
        snap = self._make_snapshot(bps)
        r1 = _is_plausible(snap, "US0000000000")
        r2 = _is_plausible(snap, "US0000000000")
        assert r1 == r2

    def test_cap_boundary_exact(self) -> None:
        """Exakt am Cap (5000 bps) ist noch plausibel (> nicht >=)."""
        snap = self._make_snapshot(_MAX_PLAUSIBLE_YIELD_BPS)
        assert _is_plausible(snap, "US0000000000") is True

    def test_one_above_cap_implausible(self) -> None:
        """Cap + 1 bps ist nicht mehr plausibel."""
        snap = self._make_snapshot(_MAX_PLAUSIBLE_YIELD_BPS + 1)
        assert _is_plausible(snap, "US0000000000") is False
