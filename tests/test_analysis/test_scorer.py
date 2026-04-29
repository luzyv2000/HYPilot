# Dateiname:     tests/test_analysis/test_scorer.py
# Version:       2026-04-29
# Abhängigkeiten (intern): analysis.scorer, core.dividend_source
# Abhängigkeiten (extern): pytest
"""
tests/test_analysis/test_scorer.py

Vollständige Testabdeckung für analysis/scorer.py.

Priorität: KRITISCH — Scorer ist die Kernlogik für Anlageentscheidungen.
Ein Berechnungsfehler hier führt zu falschen Investment-Empfehlungen.

Testgruppen:
  1. _score_yield          — Rendite-Scoring (max 40 Punkte)
  2. _score_frequency      — Frequenz-Scoring (max 20 Punkte)
  3. _score_stability      — Stabilitäts-Scoring (max 25 Punkte)
  4. _score_payout         — Payout-Scoring (max 15 Punkte)
  5. score_dividend_snapshot — Integration + Gesamtscore
  6. Regressionstests      — Randfälle und Arith.-Fehler

Alle Tests sind Unit-Tests (kein Netzwerk, keine DB).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from analysis.scorer import (
    DividendScore,
    _rating_from_score,
    _score_frequency,
    _score_payout,
    _score_stability,
    _score_yield,
    score_dividend_snapshot,
)
from core.dividend_source import DividendSnapshot


# ── Hilfsfunktionen für Tests ─────────────────────────────────────────────────

def _make_snapshot(
    isin: str = "US0000000000",
    yield_bps: int | None = 550,
    frequency: str | None = "monthly",
    last_amount_micro: int | None = 271_000,
    last_ex_date: date | None = date(2026, 3, 31),
    currency: str = "USD",
    payout_ratio_bps: int | None = 27_500,
    data_source: str = "yfinance",
) -> DividendSnapshot:
    """Erstellt einen DividendSnapshot mit Standardwerten für Tests."""
    return DividendSnapshot(
        isin=isin,
        yield_bps=yield_bps,
        frequency=frequency,
        last_amount_micro=last_amount_micro,
        last_ex_date=last_ex_date,
        currency=currency,
        payout_ratio_bps=payout_ratio_bps,
        data_source=data_source,
    )


# ── _score_yield ──────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestScoreYield:

    def test_none_yields_zero_points(self) -> None:
        """Kein Rendite-Wert → 0 Punkte, erklärende Note."""
        pts, notes = _score_yield(None)
        assert pts == 0
        assert any("unbekannt" in n.lower() for n in notes)

    def test_exact_10_percent_yields_full_points(self) -> None:
        """10,00% (1000 bps) → 40 Punkte (Kernziel exakt erreicht)."""
        pts, notes = _score_yield(1000)
        assert pts == 40
        assert any("Kernziel" in n for n in notes)

    def test_above_10_percent_yields_full_points(self) -> None:
        """12,5% (1250 bps) → 40 Punkte (über Kernziel)."""
        pts, notes = _score_yield(1250)
        assert pts == 40

    def test_7_percent_yields_partial_points(self) -> None:
        """7,0% (700 bps) → Punkte zwischen 0 und 40."""
        pts, _ = _score_yield(700)
        assert 0 < pts < 40

    def test_7_percent_note_says_gut(self) -> None:
        """7% → Note enthält 'gut'."""
        _, notes = _score_yield(700)
        assert any("gut" in n.lower() for n in notes)

    def test_5_percent_yields_partial_points(self) -> None:
        """5,0% (500 bps) → Punkte zwischen 0 und 40."""
        pts, _ = _score_yield(500)
        assert 0 < pts < 40

    def test_5_percent_note_says_akzeptabel(self) -> None:
        """5% → Note enthält 'akzeptabel'."""
        _, notes = _score_yield(500)
        assert any("akzeptabel" in n.lower() for n in notes)

    def test_3_percent_yields_zero_points(self) -> None:
        """3,0% (300 bps) → 0 Punkte (unter Mindestrendite 4%)."""
        pts, _ = _score_yield(300)
        assert pts == 0

    def test_zero_yield_yields_zero_points(self) -> None:
        """0% (0 bps) → 0 Punkte, kein Crash."""
        pts, _ = _score_yield(0)
        assert pts == 0

    def test_points_increase_with_yield(self) -> None:
        """Höhere Rendite → gleich viele oder mehr Punkte."""
        pts_4  = _score_yield(400)[0]   #  4%
        pts_7  = _score_yield(700)[0]   #  7%
        pts_10 = _score_yield(1000)[0]  # 10%
        assert pts_4 <= pts_7 <= pts_10

    def test_points_are_integer(self) -> None:
        """Scoring-Punkte müssen Integer sein (kein float-Drift)."""
        pts, _ = _score_yield(750)
        assert isinstance(pts, int)

    def test_no_float_arithmetic_error_at_boundary(self) -> None:
        """
        Klassischer float-Fehler: 0.1 + 0.2 ≠ 0.3.
        bps_to_decimal-Konvertierung via str() muss das verhindern.
        Ergebnis muss deterministisch und stabil sein.
        """
        pts_a = _score_yield(1000)[0]
        pts_b = _score_yield(1000)[0]
        assert pts_a == pts_b, "Scoring muss deterministisch sein"

    @pytest.mark.parametrize("bps,expected_pts", [
        (1000, 40),   # exakt 10% → voll
        (1500, 40),   # 15% → voll (über Tier 1)
        (999,  39),   # knapp unter 10%
        (400,  16),   # knapp über 4%
        (399,   0),   # knapp unter 4%
    ])
    def test_tier_boundaries(self, bps: int, expected_pts: int) -> None:
        """Grenzwerte der drei Tier-Stufen korrekt berechnen."""
        pts, _ = _score_yield(bps)
        assert pts == expected_pts, (
            f"yield_bps={bps}: expected {expected_pts}, got {pts}"
        )


# ── _score_frequency ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestScoreFrequency:

    @pytest.mark.parametrize("freq,expected", [
        ("monthly",     20),
        ("quarterly",   14),
        ("semi_annual",  8),
        ("annual",       4),
        ("irregular",    2),
        (None,           0),
    ])
    def test_all_known_frequencies(self, freq: str | None, expected: int) -> None:
        """Alle bekannten Frequenzwerte liefern korrekte Punkte."""
        pts, _ = _score_frequency(freq)
        assert pts == expected, f"Frequenz '{freq}': expected {expected}, got {pts}"

    def test_unknown_frequency_yields_zero(self) -> None:
        """Unbekannte Frequenz → 0 Punkte, kein Crash."""
        pts, notes = _score_frequency("weekly")
        assert pts == 0
        assert any("weekly" in n or "Unbekannt" in n for n in notes)

    def test_none_frequency_returns_note(self) -> None:
        """None-Frequenz → erklärende Note."""
        _, notes = _score_frequency(None)
        assert len(notes) == 1
        assert "unbekannt" in notes[0].lower()

    def test_monthly_has_highest_points(self) -> None:
        """Monatlich hat die höchste Punktzahl aller Frequenzen."""
        monthly_pts = _score_frequency("monthly")[0]
        for freq in ("quarterly", "semi_annual", "annual", "irregular"):
            assert monthly_pts > _score_frequency(freq)[0]

    def test_points_are_integer(self) -> None:
        """Punkte müssen Integer sein."""
        pts, _ = _score_frequency("quarterly")
        assert isinstance(pts, int)


# ── _score_stability ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestScoreStability:

    def test_full_snapshot_yields_25_points(self) -> None:
        """Vollständiger Snapshot → 25 Punkte."""
        snapshot = _make_snapshot(
            yield_bps=550,
            last_ex_date=date(2026, 3, 31),
            last_amount_micro=271_000,
        )
        pts, _ = _score_stability(snapshot)
        assert pts == 25

    def test_no_yield_bps_loses_10_points(self) -> None:
        """Kein yield_bps → 10 Punkte weniger (max 15)."""
        snapshot = _make_snapshot(
            yield_bps=None,
            last_ex_date=date(2026, 3, 31),
            last_amount_micro=271_000,
        )
        pts, _ = _score_stability(snapshot)
        assert pts == 15

    def test_no_last_ex_date_loses_10_points(self) -> None:
        """Kein last_ex_date → 10 Punkte weniger (max 15)."""
        snapshot = _make_snapshot(
            yield_bps=550,
            last_ex_date=None,
            last_amount_micro=271_000,
        )
        pts, _ = _score_stability(snapshot)
        assert pts == 15

    def test_no_last_amount_loses_5_points(self) -> None:
        """Kein last_amount_micro → 5 Punkte weniger (max 20)."""
        snapshot = _make_snapshot(
            yield_bps=550,
            last_ex_date=date(2026, 3, 31),
            last_amount_micro=None,
        )
        pts, _ = _score_stability(snapshot)
        assert pts == 20

    def test_zero_amount_loses_5_points(self) -> None:
        """last_amount_micro=0 → wie kein Betrag (5 Punkte weniger)."""
        snapshot = _make_snapshot(
            yield_bps=550,
            last_ex_date=date(2026, 3, 31),
            last_amount_micro=0,
        )
        pts, _ = _score_stability(snapshot)
        assert pts == 20

    def test_empty_snapshot_yields_zero_points(self) -> None:
        """Snapshot ohne Daten → 0 Punkte, kein Crash."""
        snapshot = _make_snapshot(
            yield_bps=None,
            last_ex_date=None,
            last_amount_micro=None,
        )
        pts, _ = _score_stability(snapshot)
        assert pts == 0

    def test_points_are_integer(self) -> None:
        """Punkte müssen Integer sein."""
        pts, _ = _score_stability(_make_snapshot())
        assert isinstance(pts, int)

    def test_notes_mention_ex_date(self) -> None:
        """Bei vorhandenem last_ex_date muss das Datum in einer Note stehen."""
        snapshot = _make_snapshot(last_ex_date=date(2026, 3, 31))
        _, notes = _score_stability(snapshot)
        assert any("2026-03-31" in n for n in notes)

    def test_notes_mention_amount(self) -> None:
        """Bei vorhandenem Betrag muss Betrag + Währung in Note stehen."""
        snapshot = _make_snapshot(
            last_amount_micro=271_000,
            currency="USD",
        )
        _, notes = _score_stability(snapshot)
        assert any("USD" in n for n in notes)


# ── _score_payout ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestScorePayout:

    def test_none_payout_yields_neutral_5_points(self) -> None:
        """Unbekannte Payout-Ratio → 5 Punkte (neutraler Wert)."""
        pts, notes = _score_payout(None)
        assert pts == 5
        assert any("neutral" in n.lower() for n in notes)

    def test_sustainable_payout_60pct_yields_full(self) -> None:
        """60% Payout (6000 bps, ≤70%) → 15 Punkte."""
        pts, _ = _score_payout(6000)
        assert pts == 15

    def test_exact_70pct_yields_full(self) -> None:
        """70% Payout (7000 bps) → 15 Punkte (Grenzwert ≤70%)."""
        pts, _ = _score_payout(7000)
        assert pts == 15

    def test_risky_95pct_yields_zero(self) -> None:
        """95% Payout (9500 bps, >90%) → 0 Punkte."""
        pts, notes = _score_payout(9500)
        assert pts == 0
        assert any("Risiko" in n for n in notes)

    def test_exact_90pct_yields_zero(self) -> None:
        """90% Payout (9000 bps) → 0 Punkte (Grenzwert >90%)."""
        pts, _ = _score_payout(9000)
        assert pts == 0

    def test_reit_275pct_yields_neutral_8_points(self) -> None:
        """275% REIT-Payout (27500 bps, >100%) → 8 Punkte (neutral)."""
        pts, notes = _score_payout(27_500)
        assert pts == 8
        assert any("REIT" in n or "strukturell" in n for n in notes)

    def test_reit_threshold_exactly_100pct(self) -> None:
        """Exakt 100% (10000 bps) → NICHT als REIT behandelt (>1.0 Bedingung)."""
        # 10000 bps = 1.0 → Grenzfall: ratio > Decimal("1.0") ist False
        pts, _ = _score_payout(10_000)
        # 100% ist nicht > 100% → fällt in die >90% (Risiko) Kategorie
        assert pts == 0

    def test_elevated_80pct_is_between_0_and_15(self) -> None:
        """80% Payout (8000 bps, 70–90%) → Punkte zwischen 0 und 15."""
        pts, notes = _score_payout(8_000)
        assert 0 < pts < 15
        assert any("erhöht" in n for n in notes)

    def test_points_are_integer(self) -> None:
        """Punkte müssen Integer sein."""
        pts, _ = _score_payout(8_000)
        assert isinstance(pts, int)

    def test_80pct_payout_interpolation_correct(self) -> None:
        """
        80% liegt in der Mitte zwischen 70% und 90%.
        Lineare Interpolation: (90-80)/(90-70) * 15 = 0.5 * 15 = 7 Punkte.
        """
        pts, _ = _score_payout(8_000)
        assert pts == 7


# ── score_dividend_snapshot (Integration) ────────────────────────────────────

@pytest.mark.unit
class TestScoreDividendSnapshot:

    def test_returns_dividend_score_type(self) -> None:
        """Rückgabetyp ist DividendScore."""
        result = score_dividend_snapshot(_make_snapshot())
        assert isinstance(result, DividendScore)

    def test_isin_preserved(self) -> None:
        """ISIN wird unverändert weitergegeben."""
        snapshot = _make_snapshot(isin="US7561091049")
        result = score_dividend_snapshot(snapshot)
        assert result.isin == "US7561091049"

    def test_total_equals_sum_of_subscores(self) -> None:
        """Gesamtpunktzahl = Summe aller Teilscores."""
        result = score_dividend_snapshot(_make_snapshot())
        computed = (
            result.yield_points
            + result.frequency_points
            + result.stability_points
            + result.payout_points
        )
        assert computed == result.total

    def test_total_within_valid_range(self) -> None:
        """Gesamtscore liegt immer zwischen 0 und 100."""
        result = score_dividend_snapshot(_make_snapshot())
        assert 0 <= result.total <= 100

    def test_total_is_integer(self) -> None:
        """Gesamtscore ist Integer (kein float-Drift)."""
        result = score_dividend_snapshot(_make_snapshot())
        assert isinstance(result.total, int)

    def test_notes_not_empty(self) -> None:
        """Mindestens eine Begründungsnotiz vorhanden."""
        result = score_dividend_snapshot(_make_snapshot())
        assert len(result.notes) >= 1

    def test_rating_strong_buy_for_high_yield_monthly(self) -> None:
        """
        12,5% Rendite, monatlich, volle Daten → STRONG_BUY.
        12,5%: 40 Pkt + monatlich: 20 Pkt + Stabilität: 25 Pkt + Payout 65%: 15 Pkt = 100
        → STRONG_BUY (≥75).
        """
        snapshot = _make_snapshot(
            yield_bps=1250,
            frequency="monthly",
            last_ex_date=date(2026, 3, 31),
            last_amount_micro=500_000,
            payout_ratio_bps=6_500,
        )
        result = score_dividend_snapshot(snapshot)
        assert result.rating == "STRONG_BUY", (
            f"Score {result.total}: erwartet STRONG_BUY, got {result.rating}"
        )

    def test_rating_reject_for_zero_yield(self) -> None:
        """0% Rendite, keine Daten → REJECT."""
        snapshot = _make_snapshot(
            yield_bps=0,
            frequency=None,
            last_ex_date=None,
            last_amount_micro=None,
            payout_ratio_bps=None,
        )
        result = score_dividend_snapshot(snapshot)
        assert result.rating == "REJECT", (
            f"Score {result.total}: erwartet REJECT, got {result.rating}"
        )

    def test_higher_yield_gives_higher_or_equal_score(self) -> None:
        """
        Gleiche Parameter, nur yield_bps verschieden:
        höherer Yield → höherer oder gleicher Gesamtscore.
        """
        low  = _make_snapshot(yield_bps=400)
        high = _make_snapshot(yield_bps=1200)
        assert (score_dividend_snapshot(high).total
                >= score_dividend_snapshot(low).total)

    def test_monthly_better_than_annual_with_same_yield(self) -> None:
        """Monatliche Ausschüttung erzielt mehr Punkte als jährliche."""
        monthly = _make_snapshot(frequency="monthly")
        annual  = _make_snapshot(frequency="annual")
        assert (score_dividend_snapshot(monthly).total
                > score_dividend_snapshot(annual).total)

    @pytest.mark.parametrize("score,expected_rating", [
        (75, "STRONG_BUY"),
        (74, "BUY"),
        (55, "BUY"),
        (54, "WATCH"),
        (35, "WATCH"),
        (34, "REJECT"),
        (0,  "REJECT"),
    ])
    def test_rating_thresholds(self, score: int, expected_rating: str) -> None:
        """Ratinggrenzen an allen Schwellwerten korrekt."""
        assert _rating_from_score(score) == expected_rating


# ── Regressionstests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestScorerRegressions:

    def test_no_zero_division_on_zero_yield(self) -> None:
        """yield_bps=0 darf keinen ZeroDivisionError auslösen."""
        try:
            score_dividend_snapshot(_make_snapshot(yield_bps=0))
        except ZeroDivisionError as e:
            pytest.fail(f"ZeroDivisionError bei yield_bps=0: {e}")

    def test_no_assertion_error_on_zero_payout(self) -> None:
        """payout_ratio_bps=0 (0%) darf keinen AssertionError auslösen."""
        try:
            score_dividend_snapshot(_make_snapshot(payout_ratio_bps=0))
        except AssertionError as e:
            pytest.fail(f"AssertionError bei payout_ratio_bps=0: {e}")

    def test_all_none_values_no_crash(self) -> None:
        """Snapshot ohne jeden Wert → kein Crash, Score ≥ 0."""
        snapshot = _make_snapshot(
            yield_bps=None,
            frequency=None,
            last_ex_date=None,
            last_amount_micro=None,
            payout_ratio_bps=None,
        )
        result = score_dividend_snapshot(snapshot)
        assert result.total >= 0

    def test_very_high_yield_no_crash(self) -> None:
        """Extrem hohe Rendite (50%, 5000 bps) → kein Crash, max 40 Punkte."""
        pts, _ = _score_yield(5_000)
        assert pts == 40

    def test_negative_yield_yields_zero_points(self) -> None:
        """Negative Rendite (falls je aus DB käme) → 0 Punkte, kein Crash."""
        try:
            pts, _ = _score_yield(-100)
            assert pts == 0
        except Exception as e:
            pytest.fail(f"Unerwarteter Fehler bei negativem yield_bps: {e}")

    def test_scoring_is_deterministic(self) -> None:
        """Zweimaliger Aufruf mit gleichen Daten → identisches Ergebnis."""
        snapshot = _make_snapshot()
        result_a = score_dividend_snapshot(snapshot)
        result_b = score_dividend_snapshot(snapshot)
        assert result_a.total  == result_b.total
        assert result_a.rating == result_b.rating

    def test_subscores_never_exceed_max(self) -> None:
        """Kein Teilscore überschreitet sein Maximum."""
        result = score_dividend_snapshot(_make_snapshot(
            yield_bps=2000,
            frequency="monthly",
            last_ex_date=date(2026, 1, 1),
            last_amount_micro=1_000_000,
            payout_ratio_bps=5_000,
        ))
        assert result.yield_points      <= 40
        assert result.frequency_points  <= 20
        assert result.stability_points  <= 25
        assert result.payout_points     <= 15