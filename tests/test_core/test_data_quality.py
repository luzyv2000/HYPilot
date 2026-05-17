# Dateiname:     tests/test_core/test_data_quality.py
# Version:       2026-05-15
# Abhängigkeiten (intern): core.data_quality
# Abhängigkeiten (extern): pytest
"""
tests/test_core/test_data_quality.py

Tests für core/data_quality.py.

Alle Tests laufen gegen temporäre SQLite-DB.
Kein Netzwerk, kein systemd.

Abgedeckte Pfade:
  - run_quality_check(): Abdeckung, Ausreißer, Staleness, Quellen
  - save_report() / load_report(): Roundtrip via metadata
  - Robustheit: leere DB, ungültige DB
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import date, timedelta

import pytest

from core.data_quality import (
    QualityReport,
    load_report,
    run_quality_check,
    save_report,
)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _insert_dividend(
    db_path: Path,
    isin: str,
    yield_bps: int | None,
    data_source: str = "yfinance",
    updated_at: str  = "2026-05-01T10:00:00",
    skip_until: str | None = None,
) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO dividend_data
                (isin, yield_bps, data_source, updated_at, skip_until)
            VALUES (?, ?, ?, ?, ?)
            """,
            (isin, yield_bps, data_source, updated_at, skip_until),
        )
        conn.commit()


# ── run_quality_check ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestRunQualityCheck:

    def test_returns_quality_report(
        self, db_with_instruments: Path
    ) -> None:
        result = run_quality_check(db_path=db_with_instruments)
        assert isinstance(result, QualityReport)

    def test_total_instruments_correct(
        self, db_with_instruments: Path
    ) -> None:
        result = run_quality_check(db_path=db_with_instruments)
        # db_with_instruments hat 5 Instrumente
        assert result.total_instruments == 5

    def test_without_div_data_all_missing(
        self, db_with_instruments: Path
    ) -> None:
        result = run_quality_check(db_path=db_with_instruments)
        assert result.with_div_data == 0
        assert result.without_div_data == 5

    def test_coverage_zero_without_data(
        self, db_with_instruments: Path
    ) -> None:
        result = run_quality_check(db_path=db_with_instruments)
        assert result.coverage_pct == 0.0

    def test_coverage_correct_with_data(
        self, db_with_dividends: Path
    ) -> None:
        # db_with_dividends hat 1 von 5 Instrumenten mit Daten
        result = run_quality_check(db_path=db_with_dividends)
        assert result.with_div_data == 1
        assert result.coverage_pct == 20.0

    def test_no_outliers_initially(
        self, db_with_instruments: Path
    ) -> None:
        result = run_quality_check(db_path=db_with_instruments)
        assert result.outliers_above_cap == 0
        assert result.outlier_isins == []

    def test_outlier_detected(
        self, db_with_instruments: Path
    ) -> None:
        _insert_dividend(
            db_with_instruments, "US7561091049",
            yield_bps=9_999,  # > 5000 Cap
        )
        result = run_quality_check(db_path=db_with_instruments)
        assert result.outliers_above_cap == 1
        assert len(result.outlier_isins) == 1
        assert "US7561091049" in result.outlier_isins[0]

    def test_outlier_warning_generated(
        self, db_with_instruments: Path
    ) -> None:
        _insert_dividend(
            db_with_instruments, "US7561091049", yield_bps=9_999
        )
        result = run_quality_check(db_path=db_with_instruments)
        assert any("Ausreißer" in w for w in result.warnings)

    def test_no_outliers_at_exactly_cap(
        self, db_with_instruments: Path
    ) -> None:
        _insert_dividend(
            db_with_instruments, "US7561091049", yield_bps=5_000
        )
        result = run_quality_check(db_path=db_with_instruments)
        assert result.outliers_above_cap == 0

    def test_skip_until_active_counted(
        self, db_with_instruments: Path
    ) -> None:
        future = (date.today() + timedelta(days=5)).isoformat()
        _insert_dividend(
            db_with_instruments, "US7561091049",
            yield_bps=0, skip_until=future,
        )
        result = run_quality_check(db_path=db_with_instruments)
        assert result.skip_until_active == 1

    def test_zero_yield_counted(
        self, db_with_instruments: Path
    ) -> None:
        _insert_dividend(
            db_with_instruments, "US7561091049", yield_bps=0
        )
        result = run_quality_check(db_path=db_with_instruments)
        assert result.zero_yield == 1

    def test_sources_populated(
        self, db_with_instruments: Path
    ) -> None:
        _insert_dividend(
            db_with_instruments, "US7561091049",
            yield_bps=550, data_source="divvydiary",
        )
        _insert_dividend(
            db_with_instruments, "DE0005557508",
            yield_bps=300, data_source="yfinance",
        )
        result = run_quality_check(db_path=db_with_instruments)
        assert "divvydiary" in result.sources
        assert "yfinance"   in result.sources
        assert result.sources["divvydiary"] == 1
        assert result.sources["yfinance"]   == 1

    def test_generated_at_is_iso_timestamp(
        self, db_with_instruments: Path
    ) -> None:
        from datetime import datetime
        result = run_quality_check(db_path=db_with_instruments)
        parsed = datetime.fromisoformat(result.generated_at)
        assert parsed is not None

    def test_no_exception_on_invalid_db(self) -> None:
        """Ungültige DB → kein Crash, leerer Report mit Warnung."""
        bad_path = Path("/nonexistent/path/hypilot.db")
        result = run_quality_check(db_path=bad_path)
        assert isinstance(result, QualityReport)
        assert len(result.warnings) > 0


# ── save_report / load_report ─────────────────────────────────────────────────

@pytest.mark.integration
class TestSaveLoadReport:

    def _make_report(self) -> QualityReport:
        from datetime import datetime
        return QualityReport(
            generated_at=datetime.now().isoformat(),
            total_instruments=100,
            with_div_data=92,
            without_div_data=8,
            coverage_pct=92.0,
            outliers_above_cap=0,
            outlier_isins=[],
            stale_entries=50,
            stale_threshold_days=7,
            skip_until_active=12,
            zero_yield=30,
            unresolvable_tickers=5,
            missing_ticker=10,
            sources={"yfinance": 60, "divvydiary": 32},
            warnings=[],
        )

    def test_save_and_load_roundtrip(
        self, in_memory_db: Path
    ) -> None:
        report = self._make_report()
        save_report(report, db_path=in_memory_db)
        loaded = load_report(db_path=in_memory_db)
        assert loaded is not None
        assert loaded.total_instruments == 100
        assert loaded.coverage_pct      == 92.0

    def test_load_returns_none_when_no_report(
        self, in_memory_db: Path
    ) -> None:
        result = load_report(db_path=in_memory_db)
        assert result is None

    def test_second_save_overwrites(
        self, in_memory_db: Path
    ) -> None:
        r1 = self._make_report()
        save_report(r1, db_path=in_memory_db)

        from datetime import datetime
        r2 = QualityReport(
            generated_at=datetime.now().isoformat(),
            total_instruments=200,
            with_div_data=180,
            without_div_data=20,
            coverage_pct=90.0,
            outliers_above_cap=3,
            outlier_isins=["US123 (60.0 %)"],
            stale_entries=10,
            stale_threshold_days=7,
            skip_until_active=5,
            zero_yield=8,
            unresolvable_tickers=2,
            missing_ticker=3,
            sources={"yfinance": 180},
            warnings=["3 Ausreißer entdeckt."],
        )
        save_report(r2, db_path=in_memory_db)
        loaded = load_report(db_path=in_memory_db)
        assert loaded is not None
        assert loaded.total_instruments   == 200
        assert loaded.outliers_above_cap  == 3
        assert len(loaded.warnings)       == 1

    def test_sources_dict_preserved(
        self, in_memory_db: Path
    ) -> None:
        report = self._make_report()
        save_report(report, db_path=in_memory_db)
        loaded = load_report(db_path=in_memory_db)
        assert loaded is not None
        assert loaded.sources == {"yfinance": 60, "divvydiary": 32}

    def test_outlier_isins_list_preserved(
        self, in_memory_db: Path
    ) -> None:
        from datetime import datetime
        report = QualityReport(
            generated_at=datetime.now().isoformat(),
            total_instruments=10,
            with_div_data=10,
            without_div_data=0,
            coverage_pct=100.0,
            outliers_above_cap=2,
            outlier_isins=["AU0000221251 (681.0 %)", "DE000ABC (60.0 %)"],
            stale_entries=0,
            stale_threshold_days=7,
            skip_until_active=0,
            zero_yield=0,
            unresolvable_tickers=0,
            missing_ticker=0,
            sources={},
            warnings=["2 Ausreißer entdeckt."],
        )
        save_report(report, db_path=in_memory_db)
        loaded = load_report(db_path=in_memory_db)
        assert loaded is not None
        assert len(loaded.outlier_isins) == 2
        assert "AU0000221251" in loaded.outlier_isins[0]

    def test_no_exception_on_invalid_db(self) -> None:
        """save_report auf ungültiger DB → kein Crash."""
        from datetime import datetime
        report = QualityReport(
            generated_at=datetime.now().isoformat(),
            total_instruments=0, with_div_data=0, without_div_data=0,
            coverage_pct=0.0, outliers_above_cap=0, outlier_isins=[],
            stale_entries=0, stale_threshold_days=7,
            skip_until_active=0, zero_yield=0,
            unresolvable_tickers=0, missing_ticker=0,
            sources={}, warnings=[],
        )
        bad_path = Path("/nonexistent/path/hypilot.db")
        save_report(report, db_path=bad_path)  # darf nicht crashen


# ── run_quality_check + save + load (Integrationsfluss) ──────────────────────

@pytest.mark.integration
class TestQualityCheckFullFlow:

    def test_full_flow(self, db_with_dividends: Path) -> None:
        """run_quality_check → save_report → load_report: vollständiger Fluss."""
        report = run_quality_check(db_path=db_with_dividends)
        save_report(report, db_path=db_with_dividends)
        loaded = load_report(db_path=db_with_dividends)

        assert loaded is not None
        assert loaded.total_instruments == report.total_instruments
        assert loaded.coverage_pct      == report.coverage_pct
        assert loaded.generated_at      == report.generated_at
