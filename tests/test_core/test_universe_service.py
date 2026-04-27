# Dateiname:     tests/test_core/test_universe_service.py
# Version:       2026-04-27
# Abhängigkeiten (intern): core.universe_service
# Abhängigkeiten (extern): pytest
"""
tests/test_core/test_universe_service.py

Tests für core.universe_service.
Alle Tests laufen gegen die temporäre In-Memory-DB aus conftest.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.universe_service import get_all_instruments, get_by_isin, search_instruments


@pytest.mark.integration
class TestGetAllInstruments:

    def test_returns_list(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(db_path=db_with_instruments)
        assert isinstance(result, list)

    def test_contains_expected_count(self, db_with_instruments: Path) -> None:
        # conftest legt 5 Instrumente an (inkl. 1 mit 'Short' im Namen)
        result = get_all_instruments(db_path=db_with_instruments)
        assert len(result) == 5

    def test_limit_respected(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(limit=2, db_path=db_with_instruments)
        assert len(result) == 2

    def test_limit_zero_returns_all(self, db_with_instruments: Path) -> None:
        result = get_all_instruments(limit=None, db_path=db_with_instruments)
        assert len(result) == 5

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
        assert names == sorted(names, key=str.lower)

    def test_name_override_takes_precedence(
        self, db_with_instruments: Path
    ) -> None:
        """name_override muss COALESCE-Logik korrekt anwenden."""
        import sqlite3
        with sqlite3.connect(db_with_instruments) as conn:
            conn.execute(
                "UPDATE instruments SET name_override = 'Mein Tesla' "
                "WHERE isin = 'US88160R1014'"
            )
            conn.commit()

        result = get_all_instruments(db_path=db_with_instruments)
        names = [r["name"] for r in result]
        assert "Mein Tesla" in names
        assert "Tesla Inc"  not in names


@pytest.mark.integration
class TestSearchInstruments:

    def test_finds_by_partial_name(self, db_with_instruments: Path) -> None:
        result = search_instruments("Tesla", db_path=db_with_instruments)
        assert len(result) == 1
        assert result[0]["isin"] == "US88160R1014"

    def test_case_insensitive_upper(self, db_with_instruments: Path) -> None:
        result = search_instruments("TESLA", db_path=db_with_instruments)
        assert len(result) == 1

    def test_case_insensitive_lower(self, db_with_instruments: Path) -> None:
        result = search_instruments("tesla", db_path=db_with_instruments)
        assert len(result) == 1

    def test_finds_by_isin(self, db_with_instruments: Path) -> None:
        result = search_instruments("US88160R1014", db_path=db_with_instruments)
        assert len(result) == 1
        assert result[0]["isin"] == "US88160R1014"

    def test_no_match_returns_empty_list(
        self, db_with_instruments: Path
    ) -> None:
        result = search_instruments("XYZNOTEXIST999", db_path=db_with_instruments)
        assert result == []

    def test_returns_list_type(self, db_with_instruments: Path) -> None:
        result = search_instruments("a", db_path=db_with_instruments)
        assert isinstance(result, list)

    def test_limit_max_50(self, db_with_instruments: Path) -> None:
        # Wildcard die alle 5 Einträge treffen sollte
        result = search_instruments("", db_path=db_with_instruments)
        assert len(result) <= 50

    def test_finds_by_name_override(self, db_with_instruments: Path) -> None:
        import sqlite3
        with sqlite3.connect(db_with_instruments) as conn:
            conn.execute(
                "UPDATE instruments SET name_override = 'Mein MSCI ETF' "
                "WHERE isin = 'IE00B4L5Y983'"
            )
            conn.commit()

        result = search_instruments("MSCI ETF", db_path=db_with_instruments)
        assert any(r["isin"] == "IE00B4L5Y983" for r in result)


@pytest.mark.integration
class TestGetByIsin:

    def test_finds_existing(self, db_with_instruments: Path) -> None:
        result = get_by_isin("US88160R1014", db_path=db_with_instruments)
        assert result is not None
        assert result["isin"] == "US88160R1014"
        assert result["name"] == "Tesla Inc"

    def test_returns_none_for_unknown(self, db_with_instruments: Path) -> None:
        result = get_by_isin("XX9999999999", db_path=db_with_instruments)
        assert result is None

    def test_returns_dict(self, db_with_instruments: Path) -> None:
        result = get_by_isin("US7561091049", db_path=db_with_instruments)
        assert isinstance(result, dict)

    def test_wkn_present_when_set(self, db_with_instruments: Path) -> None:
        result = get_by_isin("US88160R1014", db_path=db_with_instruments)
        assert result is not None
        assert result["wkn"] == "A1CX3T"

    def test_wkn_none_when_not_set(self, db_with_instruments: Path) -> None:
        result = get_by_isin("IE00B4L5Y983", db_path=db_with_instruments)
        assert result is not None
        assert result["wkn"] is None
