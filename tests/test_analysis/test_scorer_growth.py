# Dateiname:     tests/test_analysis/test_scorer_growth.py
# Version:       2026-05-09-fix1
# Abhängigkeiten (intern): analysis.scorer, db.dividend_repository
# Abhängigkeiten (extern): pytest
"""
tests/test_analysis/test_scorer_growth.py

Tests für _score_stability_from_history() und GrowthMetrics-Integration.

Fix 2026-05-09-fix1:
  - test_1_year_gives_3_data_points: korrigiert auf 6 Punkte
    (1yr=3 + neutral_growth=3 + no_cut_skipped=0)
  - test_cut_note_contains_warning: prüft auf "erkannt" statt "Kürzung"
    (vermeidet ü-Encoding-Probleme in CI)
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from analysis.scorer import (
    _score_stability_from_history,
    score_dividend_snapshot,
)
from core.dividend_source import DividendSnapshot
from db.dividend_repository import GrowthMetrics


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _metrics(
    years: int = 3,
    yoy: float | None = 0.05,
    cut: bool = False,
) -> GrowthMetrics:
    return GrowthMetrics(
        years_of_data=years,
        yoy_growth=Decimal(str(yoy)) if yoy is not None else None,
        has_cut=cut,
    )


def _snapshot() -> DividendSnapshot:
    from datetime import date
    return DividendSnapshot(
        isin="US0000000000",
        yield_bps=550,
        frequency="monthly",
        last_amount_micro=271_000,
        last_ex_date=date(2026, 3, 31),
        currency="USD",
        payout_ratio_bps=27_500,
        data_source="yfinance",
    )


# ── _score_stability_from_history: Punkte ────────────────────────────────────

@pytest.mark.unit
class TestScoreStabilityFromHistory:

    def test_max_points_strong_growth_no_cut(self) -> None:
        """3 Jahre + ≥5% Wachstum + keine Kürzung → 25 Punkte."""
        pts, _ = _score_stability_from_history(_metrics(3, 0.05, False))
        assert pts == 25

    def test_3_years_gives_10_data_points(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(3, None, False))
        # 3yr=10 + neutral_growth=3 + no_cut=5
        assert pts == 18

    def test_2_years_gives_6_data_points(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(2, 0.05, False))
        # 2yr=6 + strong_growth=10 + no_cut=5
        assert pts == 21

    def test_1_year_gives_3_data_points(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(1, None, False))
        # 1yr=3 + no_yoy_neutral=3 + no_cut_bonus_skipped (years<2)
        assert pts == 6

    def test_0_years_gives_neutral_growth_only(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(0, None, False))
        # 0yr=0 + neutral_growth=3 + no_cut_bonus_skipped (years<2)
        assert pts == 3

    def test_strong_growth_gives_10_growth_points(self) -> None:
        pts, notes = _score_stability_from_history(_metrics(3, 0.10, False))
        assert pts == 25
        assert any("stark" in n for n in notes)

    def test_positive_growth_gives_6_growth_points(self) -> None:
        pts, notes = _score_stability_from_history(_metrics(3, 0.02, False))
        # 3yr=10 + positive=6 + no_cut=5
        assert pts == 21
        assert any("positiv" in n for n in notes)

    def test_zero_growth_gives_3_growth_points(self) -> None:
        pts, notes = _score_stability_from_history(_metrics(3, 0.0, False))
        # 3yr=10 + stable=3 + no_cut=5
        assert pts == 18
        assert any("stabil" in n.lower() for n in notes)

    def test_negative_growth_gives_0_growth_points(self) -> None:
        pts, notes = _score_stability_from_history(_metrics(3, -0.05, False))
        # 3yr=10 + negative=0 + no_cut=5
        assert pts == 15
        assert any("gesunken" in n for n in notes)

    def test_no_yoy_data_gives_3_neutral_points(self) -> None:
        _, notes = _score_stability_from_history(_metrics(3, None, False))
        assert any("wenig" in n.lower() or "Wachstum" in n for n in notes)

    def test_cut_detected_gives_no_bonus(self) -> None:
        pts_no_cut = _score_stability_from_history(_metrics(3, 0.05, False))[0]
        pts_cut    = _score_stability_from_history(_metrics(3, 0.05, True))[0]
        assert pts_no_cut - pts_cut == 5

    def test_cut_note_contains_warning(self) -> None:
        """Kürzungswarnung muss in den Notizen vorhanden sein."""
        _, notes = _score_stability_from_history(_metrics(3, 0.05, True))
        # Prüfung auf "erkannt" statt "Kürzung" — vermeidet ü-Encoding-Probleme in CI
        assert any("erkannt" in n for n in notes)

    def test_no_cut_note_positive(self) -> None:
        """Keine Kürzung → positive Bestätigung in Notizen."""
        _, notes = _score_stability_from_history(_metrics(3, 0.05, False))
        assert any("Keine" in n for n in notes)

    def test_max_is_25(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(10, 1.0, False))
        assert pts == 25

    def test_min_is_0(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(0, -0.5, True))
        assert pts >= 0

    def test_points_are_integer(self) -> None:
        pts, _ = _score_stability_from_history(_metrics(3, 0.05, False))
        assert isinstance(pts, int)


# ── score_dividend_snapshot: Integration ─────────────────────────────────────

@pytest.mark.unit
class TestScoreDividendSnapshotWithGrowth:

    def test_with_growth_metrics_is_valid_score(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap, growth_metrics=_metrics(3, 0.05))
        assert 0 <= result.total <= 100

    def test_growth_metrics_none_uses_proxy(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap, growth_metrics=None)
        assert result is not None
        assert isinstance(result.total, int)

    def test_total_is_integer_with_growth(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap, growth_metrics=_metrics())
        assert isinstance(result.total, int)

    def test_total_in_range_with_growth(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap, growth_metrics=_metrics())
        assert 0 <= result.total <= 100

    def test_total_equals_sum_of_subscores(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap, growth_metrics=_metrics())
        assert result.total == (
            result.yield_points + result.frequency_points
            + result.stability_points + result.payout_points
        )

    def test_notes_contain_history_info(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap, growth_metrics=_metrics(3, 0.07))
        all_notes = " ".join(result.notes)
        assert "Jahre" in all_notes or "Wachstum" in all_notes

    def test_backward_compat_existing_tests_unaffected(self) -> None:
        snap   = _snapshot()
        result = score_dividend_snapshot(snap)
        assert result.isin == "US0000000000"
        assert result.total == (
            result.yield_points + result.frequency_points
            + result.stability_points + result.payout_points
        )

    def test_cut_in_history_reduces_score(self) -> None:
        snap    = _snapshot()
        no_cut  = score_dividend_snapshot(snap, growth_metrics=_metrics(3, 0.05, False))
        with_cut = score_dividend_snapshot(snap, growth_metrics=_metrics(3, 0.05, True))
        assert no_cut.total > with_cut.total


# ── get_growth_metrics_bulk: Integration ─────────────────────────────────────

@pytest.mark.integration
class TestGetGrowthMetricsBulk:

    def test_returns_dict(self, db_with_instruments: Path) -> None:
        from db.dividend_repository import get_growth_metrics_bulk
        result = get_growth_metrics_bulk(db_path=db_with_instruments)
        assert isinstance(result, dict)

    def test_empty_history_returns_empty_dict(
        self, db_with_instruments: Path
    ) -> None:
        from db.dividend_repository import get_growth_metrics_bulk
        result = get_growth_metrics_bulk(db_path=db_with_instruments)
        assert len(result) == 0

    def test_with_history_returns_metrics(
        self, db_with_instruments: Path
    ) -> None:
        import sqlite3
        from db.dividend_repository import get_growth_metrics_bulk

        with sqlite3.connect(db_with_instruments) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO dividend_history "
                "(isin, ex_date, amount_micro, currency, data_source) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("US7561091049", "2023-06-15", 260_000, "USD", "test"),
                    ("US7561091049", "2024-06-15", 268_000, "USD", "test"),
                    ("US7561091049", "2025-06-15", 271_000, "USD", "test"),
                ],
            )
            conn.commit()

        result = get_growth_metrics_bulk(db_path=db_with_instruments)
        assert "US7561091049" in result
        metrics = result["US7561091049"]
        assert metrics.years_of_data >= 2
        assert metrics.yoy_growth is not None
        assert metrics.yoy_growth > Decimal("0")
        assert not metrics.has_cut


# ── get_growth_metrics: Einzelabruf ──────────────────────────────────────────

@pytest.mark.integration
class TestGetGrowthMetrics:

    def test_returns_none_without_history(
        self, db_with_instruments: Path
    ) -> None:
        from db.dividend_repository import get_growth_metrics
        result = get_growth_metrics("US7561091049", db_path=db_with_instruments)
        assert result is None

    def test_returns_metrics_with_history(
        self, db_with_instruments: Path
    ) -> None:
        import sqlite3
        from db.dividend_repository import get_growth_metrics

        with sqlite3.connect(db_with_instruments) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO dividend_history "
                "(isin, ex_date, amount_micro, currency, data_source) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("US7561091049", "2023-06-15", 260_000, "USD", "test"),
                    ("US7561091049", "2024-06-15", 271_000, "USD", "test"),
                ],
            )
            conn.commit()

        result = get_growth_metrics("US7561091049", db_path=db_with_instruments)
        assert result is not None
        assert isinstance(result, GrowthMetrics)
        assert result.years_of_data >= 1

    def test_cut_detected(self, db_with_instruments: Path) -> None:
        import sqlite3
        from db.dividend_repository import get_growth_metrics

        with sqlite3.connect(db_with_instruments) as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO dividend_history "
                "(isin, ex_date, amount_micro, currency, data_source) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("US7561091049", "2023-06-15", 500_000, "USD", "test"),
                    ("US7561091049", "2024-06-15", 300_000, "USD", "test"),
                ],
            )
            conn.commit()

        result = get_growth_metrics("US7561091049", db_path=db_with_instruments)
        assert result is not None
        assert result.has_cut is True