# Dateiname:     tests/test_core/test_dividend_service.py
# Version:       2026-05-10-fix1
# — nur TestIsPlausible wird geändert, Rest der Datei identisch —
# Abhängigkeiten (intern): core.dividend_service, core.dividend_source
# Abhängigkeiten (extern): pytest
"""
tests/test_core/test_dividend_service.py

Tests für core/dividend_service.py.

Abgedeckte Pfade:
  - _is_plausible(): Cap-Logik, Grenzwerte, None-Handling
  - _cascade_fetch_snapshot(): Kaskaden-Logik, Quellenauswahl
  - _check_threshold_crossing(): Richtungserkennung
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.dividend_service import (
    _CASCADE_SOURCES,
    _MAX_PLAUSIBLE_YIELD_BPS,
    _check_threshold_crossing,
    _is_plausible,
    _cascade_fetch_snapshot,
)
from core.dividend_source import DividendSnapshot


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_snapshot(yield_bps: int | None, source: str = "test") -> DividendSnapshot:
    return DividendSnapshot(
        isin="US7561091049",
        yield_bps=yield_bps,
        frequency="monthly",
        last_amount_micro=271_000,
        last_ex_date=date(2026, 3, 31),
        currency="USD",
        payout_ratio_bps=6_500,
        data_source=source,
    )


# ── _is_plausible ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestIsPlausible:

    def test_none_yield_is_plausible(self) -> None:
        """yield_bps=None → plausibel (kein Rendite-Wert, kein Ausreißer)."""
        assert _is_plausible(_make_snapshot(None), "US7561091049") is True

    def test_zero_yield_is_plausible(self) -> None:
        assert _is_plausible(_make_snapshot(0), "US7561091049") is True

    def test_high_but_plausible_yield(self) -> None:
        """3000 bps (30%) — hoher aber realer Wert für BDC/REIT."""
        assert _is_plausible(_make_snapshot(3_000), "US7561091049") is True

    def test_exactly_at_cap_is_plausible(self) -> None:
        """Exakt am Cap (5000 bps = 50%) → noch plausibel (> nicht >=)."""
        assert _is_plausible(_make_snapshot(_MAX_PLAUSIBLE_YIELD_BPS), "US7561091049") is True

    def test_one_above_cap_is_implausible(self) -> None:
        """5001 bps → über Cap → nicht plausibel."""
        assert _is_plausible(_make_snapshot(_MAX_PLAUSIBLE_YIELD_BPS + 1), "US7561091049") is False

    def test_extreme_value_is_implausible(self) -> None:
        """68177 bps (Leo Lithium) → klar nicht plausibel."""
        assert _is_plausible(_make_snapshot(68_177), "AU0000221251") is False

    def test_100_percent_yield_is_implausible(self) -> None:
        """
        10000 bps (100%) → nicht plausibel.
        Konami/yfinance-Wert war ein Datenfehler (Sonderausschüttung),
        kein strukturelles JP-Marktmerkmal.
        100% Dividendenrendite ist in keinem realen Markt dauerhaft möglich.
        """
        assert _is_plausible(_make_snapshot(10_000), "JP3300200007") is False

    def test_implausible_value_logs_warning(self, caplog) -> None:
        """Unplausibler Wert muss als WARNING geloggt werden."""
        import logging
        with caplog.at_level(logging.WARNING, logger="core.dividend_service"):
            _is_plausible(_make_snapshot(68_177, "divvydiary"), "AU0000221251")
        assert any("68177" in r.message for r in caplog.records)
        assert any("AU0000221251" in r.message for r in caplog.records)

    @pytest.mark.parametrize("bps,expected", [
        (0,              True),
        (550,            True),
        (1_000,          True),
        (3_000,          True),
        (5_000,          True),   # exakt am Cap
        (5_001,          False),  # 1 bps über Cap
        (10_000,         False),  # 100% — Datenfehler
        (36_855,         False),  # East West Minerals
        (68_177,         False),  # Leo Lithium
    ])
    def test_cap_boundaries(self, bps: int, expected: bool) -> None:
        result = _is_plausible(_make_snapshot(bps), "XX0000000000")
        assert result == expected, (
            f"yield_bps={bps}: erwartet plausibel={expected}, got {not expected}"
        )


# ── _cascade_fetch_snapshot ───────────────────────────────────────────────────

@pytest.mark.unit
class TestCascadeFetchSnapshot:

    def _make_db_path(self) -> Path:
        return Path("/nonexistent/test.db")

    def test_returns_first_successful_source(self) -> None:
        """Erste Quelle liefert Ergebnis → zweite wird nicht aufgerufen."""
        snapshot = _make_snapshot(550)
        mock_divvy = MagicMock()
        mock_divvy.fetch_snapshot.return_value = snapshot
        mock_divvy.source_name = "divvydiary"

        mock_yf = MagicMock()
        mock_yf.fetch_snapshot.return_value = _make_snapshot(600)
        mock_yf.source_name = "yfinance"

        with patch(
            "core.dividend_service._CASCADE_SOURCES",
            [(mock_divvy, True), (mock_yf, False)],
        ):
            result = _cascade_fetch_snapshot(
                "US7561091049", "O", self._make_db_path()
            )

        assert result is not None
        assert result.yield_bps == 550
        mock_yf.fetch_snapshot.assert_not_called()

    def test_falls_back_to_second_source(self) -> None:
        """Erste Quelle gibt None → zweite Quelle wird versucht."""
        snapshot = _make_snapshot(600)
        mock_divvy = MagicMock()
        mock_divvy.fetch_snapshot.return_value = None
        mock_divvy.source_name = "divvydiary"

        mock_yf = MagicMock()
        mock_yf.fetch_snapshot.return_value = snapshot
        mock_yf.source_name = "yfinance"

        with patch(
            "core.dividend_service._CASCADE_SOURCES",
            [(mock_divvy, True), (mock_yf, False)],
        ):
            result = _cascade_fetch_snapshot(
                "US7561091049", "O", self._make_db_path()
            )

        assert result is not None
        assert result.yield_bps == 600

    def test_skips_non_isin_native_source_without_ticker(self) -> None:
        """yfinance (isin_native=False) wird ohne Ticker übersprungen."""
        mock_yf = MagicMock()
        mock_yf.source_name = "yfinance"

        with patch(
            "core.dividend_service._CASCADE_SOURCES",
            [(mock_yf, False)],
        ):
            result = _cascade_fetch_snapshot(
                "US7561091049", None, self._make_db_path()
            )

        assert result is None
        mock_yf.fetch_snapshot.assert_not_called()

    def test_skips_implausible_and_tries_next(self) -> None:
        """Unplausibler Snapshot (>50%) → nächste Quelle wird versucht."""
        implausible = _make_snapshot(68_177, "divvydiary")
        plausible   = _make_snapshot(550,    "yfinance")

        mock_divvy = MagicMock()
        mock_divvy.fetch_snapshot.return_value = implausible
        mock_divvy.source_name = "divvydiary"

        mock_yf = MagicMock()
        mock_yf.fetch_snapshot.return_value = plausible
        mock_yf.source_name = "yfinance"

        with patch(
            "core.dividend_service._CASCADE_SOURCES",
            [(mock_divvy, True), (mock_yf, False)],
        ):
            result = _cascade_fetch_snapshot(
                "AU0000221251", "LEO.AX", self._make_db_path()
            )

        assert result is not None
        assert result.yield_bps == 550
        assert result.data_source == "yfinance"

    def test_returns_none_when_all_sources_exhausted(self) -> None:
        """Alle Quellen geben None → Ergebnis ist None."""
        mock_source = MagicMock()
        mock_source.fetch_snapshot.return_value = None
        mock_source.source_name = "divvydiary"

        with patch(
            "core.dividend_service._CASCADE_SOURCES",
            [(mock_source, True)],
        ):
            result = _cascade_fetch_snapshot(
                "US7561091049", "O", self._make_db_path()
            )

        assert result is None

    def test_exception_in_source_does_not_abort_cascade(self) -> None:
        """Exception in einer Quelle → nächste Quelle wird trotzdem versucht."""
        snapshot = _make_snapshot(550)

        mock_broken = MagicMock()
        mock_broken.fetch_snapshot.side_effect = RuntimeError("API down")
        mock_broken.source_name = "broken"

        mock_ok = MagicMock()
        mock_ok.fetch_snapshot.return_value = snapshot
        mock_ok.source_name = "yfinance"

        with patch(
            "core.dividend_service._CASCADE_SOURCES",
            [(mock_broken, True), (mock_ok, True)],
        ):
            result = _cascade_fetch_snapshot(
                "US7561091049", "O", self._make_db_path()
            )

        assert result is not None
        assert result.yield_bps == 550


# ── _check_threshold_crossing ─────────────────────────────────────────────────

@pytest.mark.integration
class TestCheckThresholdCrossing:

    def test_crossing_up_recorded(self, db_with_instruments: Path) -> None:
        """War unter 10%, jetzt drüber → 'up' aufzeichnen."""
        with patch(
            "core.dividend_service.dividend_repository.record_threshold_crossing"
        ) as mock_record:
            _check_threshold_crossing(
                isin="US7561091049",
                old_bps=950,
                new_bps=1050,
                db_path=db_with_instruments,
            )
        mock_record.assert_called_once()
        _, kwargs = mock_record.call_args
        assert mock_record.call_args[1]["direction"] == "up" or \
               mock_record.call_args[0][3] == "up"

    def test_crossing_down_recorded(self, db_with_instruments: Path) -> None:
        """War über 10%, jetzt drunter → 'down' aufzeichnen."""
        with patch(
            "core.dividend_service.dividend_repository.record_threshold_crossing"
        ) as mock_record:
            _check_threshold_crossing(
                isin="US7561091049",
                old_bps=1050,
                new_bps=950,
                db_path=db_with_instruments,
            )
        mock_record.assert_called_once()

    def test_no_crossing_when_both_above(self, db_with_instruments: Path) -> None:
        """Beide über 10% → kein Crossing."""
        with patch(
            "core.dividend_service.dividend_repository.record_threshold_crossing"
        ) as mock_record:
            _check_threshold_crossing(
                isin="US7561091049",
                old_bps=1050,
                new_bps=1100,
                db_path=db_with_instruments,
            )
        mock_record.assert_not_called()

    def test_no_crossing_when_both_below(self, db_with_instruments: Path) -> None:
        """Beide unter 10% → kein Crossing."""
        with patch(
            "core.dividend_service.dividend_repository.record_threshold_crossing"
        ) as mock_record:
            _check_threshold_crossing(
                isin="US7561091049",
                old_bps=800,
                new_bps=900,
                db_path=db_with_instruments,
            )
        mock_record.assert_not_called()

    def test_no_crossing_when_new_bps_is_none(
        self, db_with_instruments: Path
    ) -> None:
        """new_bps=None → kein Crossing, kein Crash."""
        with patch(
            "core.dividend_service.dividend_repository.record_threshold_crossing"
        ) as mock_record:
            _check_threshold_crossing(
                isin="US7561091049",
                old_bps=1050,
                new_bps=None,
                db_path=db_with_instruments,
            )
        mock_record.assert_not_called()

    def test_crossing_up_when_old_is_none(
        self, db_with_instruments: Path
    ) -> None:
        """old_bps=None (neues Instrument) + new_bps >= 1000 → 'up'."""
        with patch(
            "core.dividend_service.dividend_repository.record_threshold_crossing"
        ) as mock_record:
            _check_threshold_crossing(
                isin="US7561091049",
                old_bps=None,
                new_bps=1050,
                db_path=db_with_instruments,
            )
        mock_record.assert_called_once()
