# Dateiname:     tests/test_analysis/test_scorer.py
# Version:       2026-04-22
"""
tests/test_analysis/test_scorer.py

Tests für das Dividenden-Scoring-System.
Kritisch: Scoring-Logik beeinflusst Anlageentscheidungen.
"""

from __future__ import annotations

from datetime import date

import pytest

from analysis.scorer import (
    DividendScore,
    _score_frequency,
    _score_payout,
    _score_yield,
    score_dividend_snapshot,
)
from core.dividend_source import DividendSnapshot


class TestScoreYield:

    @pytest.mark.unit
    def test_high_yield_full_points(self) -> None:
        """>=10% → 40 Punkte."""
        pts, _ = _score_yield(1000)
        assert pts == 40

    @pytest.mark.unit
    def test_above_ten_percent_full_points(self) -> None:
        """12.5% → 40 Punkte."""
        pts, _ = _score_yield(1250)
        assert pts == 40

    @pytest.mark.unit
    def test_medium_yield_partial_points(self) -> None:
        """5.5% → zwischen 0 und 40."""
        pts, _ = _score_yield(550)
        assert 0 < pts < 40

    @pytest.mark.unit
    def test_zero_yield_no_points(self) -> None:
        """0% → 0 Punkte."""
        pts, _ = _score_yield(0)
        assert pts == 0

    @pytest.mark.unit
    def test_none_yield_no_points(self) -> None:
        pts, notes = _score_yield(None)
        assert pts == 0
        assert any("unbekannt" in n.lower() for n in notes)


class TestScoreFrequency:

    @pytest.mark.unit
    @pytest.mark.parametrize("freq,expected", [
        ("monthly",     20),
        ("quarterly",   14),
        ("semi_annual",  8),
        ("annual",       4),
        ("irregular",    2),
        (None,           0),
    ])
    def test_all_frequencies(self, freq: str | None, expected: int) -> None:
        pts, _ = _score_frequency(freq)
        assert pts == expected


class TestScorePayout:

    @pytest.mark.unit
    def test_sustainable_payout(self) -> None:
        """60% → 15 Punkte."""
        pts, _ = _score_payout(6000)
        assert pts == 15

    @pytest.mark.unit
    def test_high_payout_risk(self) -> None:
        """95% → 0 Punkte."""
        pts, _ = _score_payout(9500)
        assert pts == 0

    @pytest.mark.unit
    def test_reit_payout_neutral(self) -> None:
        """275% (REIT) → 8 Punkte (neutral)."""
        pts, notes = _score_payout(27_500)
        assert pts == 8
        assert any("reit" in n.lower() or "strukturell" in n.lower()
                   for n in notes)

    @pytest.mark.unit
    def test_none_payout_neutral(self) -> None:
        """Unbekannt → 5 Punkte (neutral)."""
        pts, _ = _score_payout(None)
        assert pts == 5


class TestScoreDividendSnapshot:

    @pytest.mark.unit
    def test_total_max_100(self, high_yield_snapshot: DividendSnapshot) -> None:
        """Gesamtscore nie > 100."""
        score = score_dividend_snapshot(high_yield_snapshot)
        assert score.total <= 100

    @pytest.mark.unit
    def test_total_min_0(self) -> None:
        """Gesamtscore nie < 0."""
        snap = DividendSnapshot(
            isin="US0000000000",
            yield_bps=0,
            frequency=None,
            last_amount_micro=None,
            last_ex_date=None,
            currency="USD",
            payout_ratio_bps=9500,
            data_source="test",
        )
        score = score_dividend_snapshot(snap)
        assert score.total >= 0

    @pytest.mark.unit
    def test_high_yield_strong_buy(
        self, high_yield_snapshot: DividendSnapshot
    ) -> None:
        """12.5%, monatlich, nachhaltige Payout → STRONG_BUY."""
        score = score_dividend_snapshot(high_yield_snapshot)
        assert score.rating == "STRONG_BUY"

    @pytest.mark.unit
    def test_subscores_sum_to_total(
        self, sample_snapshot: DividendSnapshot
    ) -> None:
        """Teilscores müssen in Summe dem total entsprechen."""
        score = score_dividend_snapshot(sample_snapshot)
        computed = (
            score.yield_points
            + score.frequency_points
            + score.stability_points
            + score.payout_points
        )
        assert computed == score.total

    @pytest.mark.unit
    def test_notes_not_empty(self, sample_snapshot: DividendSnapshot) -> None:
        """Jeder Score liefert mindestens eine Begründung."""
        score = score_dividend_snapshot(sample_snapshot)
        assert len(score.notes) >= 1
