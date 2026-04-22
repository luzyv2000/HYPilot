# Dateiname:     tests/test_db/test_dividend_repository.py
# Version:       2026-04-22
"""
tests/test_db/test_dividend_repository.py

Integrationstests für das Dividend-Repository.
Laufen gegen temporäre SQLite-DB (kein Produktionszustand).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from core.dividend_source import DividendPayment, DividendSnapshot
from db.dividend_repository import (
    get_isins_without_dividend_data,
    get_snapshot,
    insert_history,
    upsert_snapshot,
)


@pytest.mark.integration
class TestUpsertSnapshot:

    def test_insert_new(
        self,
        db_with_instruments: Path,
        sample_snapshot: DividendSnapshot,
    ) -> None:
        upsert_snapshot(sample_snapshot, db_path=db_with_instruments)
        result = get_snapshot("US7561091049", db_path=db_with_instruments)
        assert result is not None
        assert result.yield_bps == 550

    def test_update_existing(
        self,
        db_with_instruments: Path,
        sample_snapshot: DividendSnapshot,
    ) -> None:
        upsert_snapshot(sample_snapshot, db_path=db_with_instruments)
        # Rendite aktualisieren
        updated = DividendSnapshot(
            isin=sample_snapshot.isin,
            yield_bps=600,
            frequency="monthly",
            last_amount_micro=280_000,
            last_ex_date=date(2026, 4, 30),
            currency="USD",
            payout_ratio_bps=27_500,
            data_source="yfinance",
        )
        upsert_snapshot(updated, db_path=db_with_instruments)
        result = get_snapshot("US7561091049", db_path=db_with_instruments)
        assert result is not None
        assert result.yield_bps == 600


@pytest.mark.integration
class TestInsertHistory:

    def test_insert_payments(
        self,
        db_with_instruments: Path,
        sample_payments: list[DividendPayment],
    ) -> None:
        count = insert_history(sample_payments, db_path=db_with_instruments)
        assert count == len(sample_payments)

    def test_duplicate_ignored(
        self,
        db_with_instruments: Path,
        sample_payments: list[DividendPayment],
    ) -> None:
        insert_history(sample_payments, db_path=db_with_instruments)
        count = insert_history(sample_payments, db_path=db_with_instruments)
        assert count == 0  # alle bereits vorhanden

    def test_empty_list(self, db_with_instruments: Path) -> None:
        assert insert_history([], db_path=db_with_instruments) == 0


@pytest.mark.integration
class TestGetIsinsWithoutDividendData:

    def test_returns_isins_without_data(
        self, db_with_instruments: Path
    ) -> None:
        isins = get_isins_without_dividend_data(
            db_path=db_with_instruments, limit=10
        )
        assert "US7561091049" in isins

    def test_excludes_isins_with_data(
        self,
        db_with_dividends: Path,
    ) -> None:
        isins = get_isins_without_dividend_data(
            db_path=db_with_dividends, limit=10
        )
        assert "US7561091049" not in isins

    def test_limit_respected(self, db_with_instruments: Path) -> None:
        isins = get_isins_without_dividend_data(
            db_path=db_with_instruments, limit=2
        )
        assert len(isins) <= 2
