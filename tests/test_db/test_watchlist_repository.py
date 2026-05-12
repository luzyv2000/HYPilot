# Dateiname:     tests/test_db/test_watchlist_repository.py
# Version:       2026-05-09
# Abhängigkeiten (intern): db.watchlist_repository
# Abhängigkeiten (extern): pytest
"""
tests/test_db/test_watchlist_repository.py

Integrationstests für db/watchlist_repository.py.
Alle Tests laufen gegen temporäre SQLite-DB.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from db.watchlist_repository import (
    add_to_watchlist,
    count_watchlist,
    get_watchlist,
    is_on_watchlist,
    remove_from_watchlist,
    update_notes,
)


@pytest.mark.integration
class TestAddToWatchlist:

    def test_add_new_returns_true(self, db_with_instruments: Path) -> None:
        result = add_to_watchlist("US7561091049", db_path=db_with_instruments)
        assert result is True

    def test_add_duplicate_returns_false(
        self, db_with_instruments: Path
    ) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        result = add_to_watchlist("US7561091049", db_path=db_with_instruments)
        assert result is False

    def test_add_with_notes(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", notes="Gute Dividende",
                         db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].notes == "Gute Dividende"

    def test_notes_stripped(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", notes="  Test  ",
                         db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].notes == "Test"


@pytest.mark.integration
class TestRemoveFromWatchlist:

    def test_remove_existing_returns_true(
        self, db_with_instruments: Path
    ) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        result = remove_from_watchlist("US7561091049",
                                       db_path=db_with_instruments)
        assert result is True

    def test_remove_nonexistent_returns_false(
        self, db_with_instruments: Path
    ) -> None:
        result = remove_from_watchlist("US7561091049",
                                       db_path=db_with_instruments)
        assert result is False

    def test_remove_clears_entry(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        remove_from_watchlist("US7561091049", db_path=db_with_instruments)
        assert not is_on_watchlist("US7561091049",
                                   db_path=db_with_instruments)


@pytest.mark.integration
class TestGetWatchlist:

    def test_empty_returns_empty_list(
        self, db_with_instruments: Path
    ) -> None:
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries == []

    def test_returns_added_entries(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        add_to_watchlist("DE0005557508", db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert len(entries) == 2

    def test_entry_has_correct_isin(
        self, db_with_instruments: Path
    ) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].isin == "US7561091049"

    def test_entry_has_display_name(
        self, db_with_instruments: Path
    ) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].name == "Realty Income Corp"

    def test_sorted_by_added_at_desc(
        self, db_with_instruments: Path
    ) -> None:
        """Zuletzt hinzugefügt erscheint zuerst."""
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        add_to_watchlist("DE0005557508", db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].isin == "DE0005557508"


@pytest.mark.integration
class TestIsOnWatchlist:

    def test_returns_false_when_not_added(
        self, db_with_instruments: Path
    ) -> None:
        assert not is_on_watchlist("US7561091049",
                                   db_path=db_with_instruments)

    def test_returns_true_after_add(
        self, db_with_instruments: Path
    ) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        assert is_on_watchlist("US7561091049", db_path=db_with_instruments)

    def test_returns_false_after_remove(
        self, db_with_instruments: Path
    ) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        remove_from_watchlist("US7561091049", db_path=db_with_instruments)
        assert not is_on_watchlist("US7561091049",
                                   db_path=db_with_instruments)


@pytest.mark.integration
class TestUpdateNotes:

    def test_update_existing_notes(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", notes="Alt",
                         db_path=db_with_instruments)
        update_notes("US7561091049", "Neu", db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].notes == "Neu"

    def test_clear_notes(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", notes="Alt",
                         db_path=db_with_instruments)
        update_notes("US7561091049", "", db_path=db_with_instruments)
        entries = get_watchlist(db_path=db_with_instruments)
        assert entries[0].notes == ""


@pytest.mark.integration
class TestCountWatchlist:

    def test_zero_when_empty(self, db_with_instruments: Path) -> None:
        assert count_watchlist(db_path=db_with_instruments) == 0

    def test_increments_on_add(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        assert count_watchlist(db_path=db_with_instruments) == 1

    def test_decrements_on_remove(self, db_with_instruments: Path) -> None:
        add_to_watchlist("US7561091049", db_path=db_with_instruments)
        remove_from_watchlist("US7561091049", db_path=db_with_instruments)
        assert count_watchlist(db_path=db_with_instruments) == 0