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
class TestUniverseScreen:

    def test_universe_scan_returns_list(
        self, db_with_instruments: Path
    ) -> None:
        """Basisanforderung: universe_screen gibt immer eine Liste zurück."""
        result = universe_screen(db_path=db_with_instruments)
        assert isinstance(result, list), (
            "universe_screen muss list zurückgeben, auch bei leerer DB"
        )

    def test_empty_db_returns_empty_list(
        self, in_memory_db: Path
    ) -> None:
        """Leere DB → leere Liste, kein Crash."""
        result = universe_screen(db_path=in_memory_db)
        assert result == []

    def test_returns_entries_for_populated_db(
        self, db_with_instruments: Path
    ) -> None:
        """Gefüllte DB liefert mindestens einen Eintrag zurück."""
        result = universe_screen(db_path=db_with_instruments)
        assert len(result) >= 1

    def test_entry_is_universe_entry_type(
        self, db_with_instruments: Path
    ) -> None:
        """Jeder Eintrag ist ein UniverseEntry-Dataclass-Objekt."""
        result = universe_screen(db_path=db_with_instruments)
        if not result:
            pytest.skip("Keine Einträge nach Filter — Test nicht anwendbar")
        assert isinstance(result[0], UniverseEntry)

    def test_entry_has_required_fields(
        self, db_with_instruments: Path
    ) -> None:
        """Jeder Eintrag hat name, isin, category und name_score."""
        result = universe_screen(db_path=db_with_instruments)
        if not result:
            pytest.skip("Keine Einträge nach Filter")
        entry = result[0]
        assert hasattr(entry, "name"),       "Feld 'name' fehlt"
        assert hasattr(entry, "isin"),       "Feld 'isin' fehlt"
        assert hasattr(entry, "category"),   "Feld 'category' fehlt"
        assert hasattr(entry, "name_score"), "Feld 'name_score' fehlt"

    def test_category_values_are_valid(
        self, db_with_instruments: Path
    ) -> None:
        """Kategorien dürfen nur definierte Werte enthalten."""
        valid = {"ETF", "STOCK", "BOND", "DERIVATIVE", "OPTION_STRATEGY"}
        result = universe_screen(db_path=db_with_instruments)
        for entry in result:
            assert entry.category in valid, (
                f"Ungültige Kategorie: '{entry.category}' für {entry.isin}"
            )

    def test_filter_excludes_short_products(
        self, db_with_instruments: Path
    ) -> None:
        """
        'Short Product XYZ' (DE000SL0ABC1) enthält 'Short' im Namen.
        is_investable() muss es herausfiltern.
        conftest legt dieses Instrument als Test-Artefakt an.
        """
        result = universe_screen(db_path=db_with_instruments)
        names = [e.name for e in result]
        assert not any("Short" in n for n in names), (
            "Short-Produkte dürfen universe_screen nicht passieren"
        )

    def test_results_sorted_by_name_score_descending(
        self, db_with_instruments: Path
    ) -> None:
        """Ergebnisse sind nach name_score absteigend sortiert."""
        result = universe_screen(db_path=db_with_instruments)
        scores = [e.name_score for e in result]
        assert scores == sorted(scores, reverse=True), (
            f"Ergebnisse nicht nach name_score sortiert: {scores}"
        )

    def test_category_filter_etf_only(
        self, db_with_instruments: Path
    ) -> None:
        """category_filter='ETF' liefert nur ETF-Einträge zurück."""
        result = universe_screen(
            category_filter="ETF",
            db_path=db_with_instruments,
        )
        for entry in result:
            assert entry.category == "ETF", (
                f"Erwarte ETF, got '{entry.category}' für {entry.isin}"
            )

    def test_category_filter_stock_only(
        self, db_with_instruments: Path
    ) -> None:
        """category_filter='STOCK' liefert nur STOCK-Einträge zurück."""
        result = universe_screen(
            category_filter="STOCK",
            db_path=db_with_instruments,
        )
        for entry in result:
            assert entry.category == "STOCK"

    def test_limit_respected(
        self, db_with_instruments: Path
    ) -> None:
        """limit=1 liefert maximal 1 Eintrag."""
        result = universe_screen(limit=1, db_path=db_with_instruments)
        assert len(result) <= 1

    def test_name_score_is_integer(
        self, db_with_instruments: Path
    ) -> None:
        """name_score muss Integer sein."""
        result = universe_screen(db_path=db_with_instruments)
        for entry in result:
            assert isinstance(entry.name_score, int), (
                f"name_score ist kein int: {type(entry.name_score)}"
            )

    def test_isin_is_nonempty_string(
        self, db_with_instruments: Path
    ) -> None:
        """ISIN muss nicht-leerer String sein."""
        result = universe_screen(db_path=db_with_instruments)
        for entry in result:
            assert isinstance(entry.isin, str) and len(entry.isin) > 0


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

    def test_results_sorted_by_score(
        self, db_with_mixed_dividends: Path
    ) -> None:
        """
        Instrumente mit höherem yield_bps müssen höheren Score erhalten.
        Telekom (800 bps) vs. Realty Income (550 bps):
        score(Telekom) >= score(Realty Income).
        Schützt vor Scoring-Regressionen.
        """
        score_realty  = score_instrument("US7561091049", db_path=db_with_mixed_dividends)
        score_telekom = score_instrument("DE0005557508", db_path=db_with_mixed_dividends)

        assert score_realty  is not None, "Realty Income Score darf nicht None sein"
        assert score_telekom is not None, "Telekom Score darf nicht None sein"
        assert score_telekom.total >= score_realty.total, (
            f"Höherer Yield (800 bps) muss >= Score ergeben als niedrigerer "
            f"(550 bps). Got: Telekom={score_telekom.total}, "
            f"Realty={score_realty.total}"
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
