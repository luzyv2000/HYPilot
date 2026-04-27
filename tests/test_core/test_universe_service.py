# Dateiname: tests/test_core/test_universe_service.py
# Version:   2026-04-27
"""
tests/test_core/test_universe_service.py

Tests für core.universe_service.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from core.universe_service import get_all_instruments, search_instruments


@pytest.mark.integration
class TestGetAllInstruments:

    def test_returns_list(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(db_path=db_with_instruments)
        assert isinstance(result, list)

    def test_limit_respected(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(limit=2, db_path=db_with_instruments)
        assert len(result) <= 2

    def test_entry_has_required_keys(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(limit=1, db_path=db_with_instruments)
        assert result, "Ergebnis darf nicht leer sein"
        entry = result[0]
        assert "name" in entry
        assert "isin" in entry
        assert "wkn"  in entry

    def test_sorted_by_name(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(db_path=db_with_instruments)
        names = [r["name"] for r in result]
        assert names == sorted(names)


@pytest.mark.integration
class TestSearchInstruments:

    def test_finds_existing(self, db_with_instruments: Path) -> None:
        result = search_instruments("Tesla", db_path=db_with_instruments)
        assert any("Tesla" in r["name"] for r in result)

    def test_case_insensitive(self, db_with_instruments: Path) -> None:
        upper = search_instruments("TESLA", db_path=db_with_instruments)
        lower = search_instruments("tesla", db_path=db_with_instruments)
        assert len(upper) == len(lower)

    def test_no_match_returns_empty(self, db_with_instruments: Path) -> None:
        result = search_instruments("XYZNOTEXIST", db_path=db_with_instruments)
        assert result == []

    def test_limit_respected(self, db_with_instruments: Path) -> None:
        # Suche mit Wildcard die viele Treffer erzeugt
        result = search_instruments("a", db_path=db_with_instruments)
        assert len(result) <= 50  # universe_service hat internes Limit 50
