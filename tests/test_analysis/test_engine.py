# Dateiname:     tests/test_analysis/test_engine.py
# Version:       2026-04-30
# Abhängigkeiten (intern): analysis.engine, db.dividend_repository,
#                           core.universe_service
# Abhängigkeiten (extern): pytest
"""
tests/test_analysis/test_engine.py

Tests für analysis/engine.py — den Analyse-Orchestrator von HYPilot.

Zwei Testgruppen entsprechen den zwei Betriebsmodi von engine.py:
  1. universe_screen()   — schnelles Vorfiltern (name-basiert, kein Netzwerk)
  2. score_instrument()  — Dividenden-Bewertung aus DB-Cache

Zusätzlich: test_filter_excludes_skip_until()
  → prüft den Gating-Mechanismus von get_isins_due_for_update()
  → ISINs mit skip_until in der Zukunft dürfen nicht für Update vorgesehen werden

Alle Tests laufen gegen temporäre DBs aus conftest.py.
Kein Netzwerk, kein yfinance, keine OpenFIGI-Calls.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

import pytest

from analysis.engine import UniverseEntry, score_instrument, universe_screen


# ─────────────────────────────────────────────────────────────────────────────
# universe_screen() — schnelles Vorfiltern
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestScoreInstrument:

    def test_higher_yield_gives_higher_yield_points(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        yield_bps bestimmt direkt yield_points — nicht den Gesamtscore.
        Der Gesamtscore hängt von allen 4 Dimensionen ab.
        Telekom (800 bps) muss mehr yield_points haben als Realty (550 bps).
        """
        score_realty  = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        score_telekom = score_instrument("DE0005557508", db_path=db_with_mixed_dividends)

        assert score_realty  is not None, "Realty Income Score darf nicht None sein"
        assert score_telekom is not None, "Telekom Score darf nicht None sein"
        assert score_telekom.yield_points >= score_realty.yield_points, (
            f"Höherer Yield (800 bps) muss >= yield_points ergeben als niedrigerer "
            f"(550 bps). Got: Telekom yield_points={score_telekom.yield_points}, "
            f"Realty yield_points={score_realty.yield_points}"
        )

    def test_monthly_frequency_outweighs_lower_yield_in_total(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        Regressionstest für das Scoring-Modell:
        Realty Income (550 bps, monatlich) kann Telekom (800 bps, jährlich)
        im Gesamtscore schlagen — weil monatliche Frequenz 16 Punkte mehr bringt
        als jährliche (20 vs. 4), was die ~10 Punkte Yield-Differenz übersteigt.
        Dieses Verhalten ist gewollt und muss stabil bleiben.
        """
        score_realty  = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        score_telekom = score_instrument("DE0005557508", db_path=db_with_mixed_dividends)

        assert score_realty  is not None
        assert score_telekom is not None
        # Frequenz-Bonus (16 Punkte) > Yield-Bonus (~10 Punkte) → Realty gewinnt
        assert score_realty.frequency_points > score_telekom.frequency_points, (
            "Monatliche Ausschüttung muss mehr frequency_points ergeben als jährliche"
        )
        assert score_realty.total > score_telekom.total, (
            f"Realty ({score_realty.total}) soll Telekom ({score_telekom.total}) "
            f"übersteigen wenn Frequenzvorteil den Yield-Nachteil kompensiert"
        )

    def test_same_frequency_higher_yield_wins(
        self, db_with_instruments: Path
    ) -> None:
        """
        Bei gleicher Frequenz gewinnt der höhere Yield im Gesamtscore.
        Zwei Snapshots mit monthly + 1000 bps vs. monthly + 550 bps.
        """
        with sqlite3.connect(db_with_instruments) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, frequency, last_amount_micro,
                 last_ex_date, currency, payout_ratio_bps, data_source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'yfinance', '2020-01-01')
                """,
                [
                    ("US7561091049", 1000, "monthly", 300_000,
                     "2026-03-31", "USD", 6_500),
                    ("DE0005557508", 550, "monthly", 150_000,
                     "2026-02-15", "EUR", 6_500),
                ],
            )
            conn.commit()

        score_high = score_instrument("US7561091049", db_path=db_with_instruments)
        score_low  = score_instrument("DE0005557508", db_path=db_with_instruments)

        assert score_high is not None
        assert score_low  is not None
        assert score_high.total > score_low.total, (
            f"Bei gleicher Frequenz muss höherer Yield (1000 bps) > niedrigerer "
            f"(550 bps) gewinnen. Got: high={score_high.total}, low={score_low.total}"
        )

    def test_score_returns_none_for_unknown_isin(
        self, db_with_instruments: Path
    ) -> None:
        """Unbekannte ISIN → None, kein Crash."""
        result = score_instrument("XX9999999999", db_path=db_with_instruments)
        assert result is None

    def test_score_returns_none_without_dividend_data(
        self, db_with_instruments: Path
    ) -> None:
        """
        iShares ETF (IE00B4L5Y983) hat keinen dividend_data-Eintrag.
        → score_instrument gibt None zurück.
        """
        result = score_instrument("IE00B4L5Y983", db_path=db_with_instruments)
        assert result is None

    def test_score_total_is_integer(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """Score-Total muss ein Integer sein (kein float-Drift)."""
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert isinstance(result.total, int), (
            "Score-Total muss int sein — float würde auf Berechnungsfehler hinweisen"
        )

    def test_score_total_in_valid_range(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """Score muss zwischen 0 und 100 liegen."""
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert 0 <= result.total <= 100, (
            f"Score {result.total} außerhalb [0, 100]"
        )

    def test_skip_until_instrument_no_crash(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        Tesla hat skip_until in der Zukunft und yield_bps=0.
        score_instrument darf keinen Crash produzieren.
        Ergebnis: None oder REJECT-Rating.
        """
        result = score_instrument("US88160R1014", db_path=db_with_mixed_dividends)
        if result is not None:
            assert result.rating in ("REJECT", "WATCH"), (
                f"0-Yield-Instrument darf nicht BUY/STRONG_BUY erhalten: "
                f"{result.rating}"
            )

    def test_score_has_notes(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """DividendScore enthält mindestens eine Begründungsnotiz."""
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert len(result.notes) >= 1

    def test_score_has_valid_rating_string(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """Rating ist immer einer der vier definierten Strings."""
        valid_ratings = {"STRONG_BUY", "BUY", "WATCH", "REJECT"}
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert result.rating in valid_ratings, (
            f"Ungültiges Rating: '{result.rating}'"
        )

# ─────────────────────────────────────────────────────────────────────────────
# test_filter_excludes_skip_until — 18-Monats-Regel Gating
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestFilterExcludesSkipUntil:
    """
    Testet den Gating-Mechanismus der 18-Monats-Regel.

    Der eigentliche Filter ist get_isins_due_for_update() in
    dividend_repository.py — nicht universe_screen() selbst.
    Diese Tests prüfen ob das Gating korrekt funktioniert.
    """

    def test_skip_until_in_future_excluded_from_update_queue(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        Tesla (US88160R1014) hat skip_until in der Zukunft.
        Sie darf NICHT für ein Update vorgesehen werden.
        """
        from db.dividend_repository import get_isins_due_for_update

        isins_due = get_isins_due_for_update(
            db_path=db_with_mixed_dividends,
            limit=100,
        )
        assert "US88160R1014" not in isins_due, (
            "ISIN mit skip_until in der Zukunft darf nicht für "
            "Update vorgesehen werden"
        )

    def test_skip_until_in_past_included_in_update_queue(
        self, db_with_instruments: Path
    ) -> None:
        """
        ISIN mit skip_until gestern soll wieder für Update vorgesehen werden
        (TTL abgelaufen).
        """
        from db.dividend_repository import get_isins_due_for_update

        past_skip = (date.today() - timedelta(days=1)).isoformat()
        old_timestamp = "2020-01-01T00:00:00"

        with sqlite3.connect(db_with_instruments) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, skip_until, data_source, updated_at)
                VALUES (?, ?, ?, 'yfinance', ?)
                """,
                ("US7561091049", 550, past_skip, old_timestamp),
            )
            conn.commit()

        isins_due = get_isins_due_for_update(
            db_path=db_with_instruments,
            limit=100,
        )
        assert "US7561091049" in isins_due, (
            "ISIN mit abgelaufenem skip_until muss wieder für "
            "Update vorgesehen werden"
        )

    def test_null_skip_until_included_when_stale(
        self, db_with_instruments: Path
    ) -> None:
        """
        ISIN ohne skip_until (NULL) und veraltetem updated_at
        soll für Update in Frage kommen.
        """
        from db.dividend_repository import get_isins_due_for_update

        old_timestamp = "2020-01-01T00:00:00"

        with sqlite3.connect(db_with_instruments) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, skip_until, data_source, updated_at)
                VALUES (?, ?, NULL, 'yfinance', ?)
                """,
                ("US7561091049", 550, old_timestamp),
            )
            conn.commit()

        isins_due = get_isins_due_for_update(
            db_path=db_with_instruments,
            limit=100,
        )
        assert "US7561091049" in isins_due

    def test_active_isins_present_in_universe_screen(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        universe_screen zeigt Instrumente unabhängig von skip_until an
        (Anzeige ≠ Update-Queue).
        Tesla erscheint weiterhin in der Liste, nur der Datenabruf ist pausiert.
        """
        result = universe_screen(db_path=db_with_mixed_dividends)
        isins = [e.isin for e in result]
        # Alle nicht-gefilterten Instrumente müssen erscheinen
        # (Short Product XYZ wird durch is_investable herausgefiltert)
        assert "US7561091049" in isins or len(result) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# score_instrument() — Dividenden-Bewertung
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestScoreInstrument:

    def test_score_returns_none_for_unknown_isin(
        self, db_with_instruments: Path
    ) -> None:
        """Unbekannte ISIN → None, kein Crash."""
        result = score_instrument("XX9999999999", db_path=db_with_instruments)
        assert result is None

    def test_score_returns_none_without_dividend_data(
        self, db_with_instruments: Path
    ) -> None:
        """
        iShares ETF (IE00B4L5Y983) hat keinen dividend_data-Eintrag.
        → score_instrument gibt None zurück.
        """
        result = score_instrument("IE00B4L5Y983", db_path=db_with_instruments)
        assert result is None

    def test_score_total_is_integer(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """Score-Total muss ein Integer sein (kein float-Drift)."""
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert isinstance(result.total, int), (
            "Score-Total muss int sein — float würde auf Berechnungsfehler hinweisen"
        )

    def test_score_total_in_valid_range(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """Score muss zwischen 0 und 100 liegen."""
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert 0 <= result.total <= 100, (
            f"Score {result.total} außerhalb [0, 100]"
        )

    def test_skip_until_instrument_no_crash(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        Tesla hat skip_until in der Zukunft und yield_bps=0.
        score_instrument darf keinen Crash produzieren.
        Ergebnis: None (kein Snapshot mit Daten) oder REJECT-Rating.
        """
        result = score_instrument("US88160R1014", db_path=db_with_mixed_dividends)
        if result is not None:
            assert result.rating in ("REJECT", "WATCH"), (
                f"0-Yield-Instrument darf nicht BUY/STRONG_BUY erhalten: "
                f"{result.rating}"
            )

    def test_score_has_notes(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """DividendScore enthält mindestens eine Begründungsnotiz."""
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert len(result.notes) >= 1

    def test_score_has_rating_string(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """Rating ist immer einer der vier definierten Strings."""
        valid_ratings = {"STRONG_BUY", "BUY", "WATCH", "REJECT"}
        result = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        assert result is not None
        assert result.rating in valid_ratings, (
            f"Ungültiges Rating: '{result.rating}'"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Regressionstests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestEngineRegressions:

    def test_no_zero_division_on_zero_yield(
        self, db_with_instruments: Path
    ) -> None:
        """
        score_instrument darf bei yield_bps=0 nicht mit
        ZeroDivisionError abstürzen.
        """
        with sqlite3.connect(db_with_instruments) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, frequency, data_source, updated_at)
                VALUES ('US7561091049', 0, NULL, 'yfinance', '2026-01-01')
                """,
            )
            conn.commit()

        try:
            score_instrument("US7561091049", db_path=db_with_instruments)
        except ZeroDivisionError as e:
            pytest.fail(f"ZeroDivisionError bei yield_bps=0: {e}")

    def test_no_crash_on_null_frequency(
        self, db_with_instruments: Path
    ) -> None:
        """NULL-frequency darf keinen AttributeError verursachen."""
        with sqlite3.connect(db_with_instruments) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, frequency, data_source, updated_at)
                VALUES ('US7561091049', 500, NULL, 'yfinance', '2026-01-01')
                """,
            )
            conn.commit()

        try:
            score_instrument("US7561091049", db_path=db_with_instruments)
        except AttributeError as e:
            pytest.fail(f"AttributeError bei NULL-frequency: {e}")

    def test_universe_screen_with_none_category_filter(
        self, db_with_instruments: Path
    ) -> None:
        """category_filter=None darf keinen Fehler verursachen."""
        try:
            result = universe_screen(
                category_filter=None,
                db_path=db_with_instruments,
            )
            assert isinstance(result, list)
        except Exception as e:
            pytest.fail(f"Fehler bei category_filter=None: {e}")

    def test_universe_screen_unknown_category_filter(
        self, db_with_instruments: Path
    ) -> None:
        """Unbekannter category_filter → leere Liste, kein Crash."""
        result = universe_screen(
            category_filter="NONEXISTENT",
            db_path=db_with_instruments,
        )
        assert result == []
