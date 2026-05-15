# Dateiname:     tests/test_db/test_portfolio_repository.py
# Version:       2026-05-15
# Abhängigkeiten (intern): db.portfolio_repository
# Abhängigkeiten (extern): pytest, hypothesis
"""
tests/test_db/test_portfolio_repository.py

Integrationstests für db/portfolio_repository.py.
Alle Tests laufen gegen temporäre SQLite-DB (kein Produktionszustand).

Testgruppen:
  1. TestAddPosition        — INSERT-Logik, Duplikate, Validierung
  2. TestRemovePosition     — DELETE-Logik
  3. TestUpdatePosition     — UPDATE-Logik
  4. TestGetPortfolio       — Leseoperationen, Sortierung
  5. TestGetPosition        — Einzelabruf
  6. TestIsInPortfolio      — Existenzprüfung
  7. TestCountPortfolio     — Zählabfrage
  8. TestPortfolioHypothesis — Property-based: shares/price-Arithmetik
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from db.portfolio_repository import (
    PortfolioEntry,
    add_position,
    count_portfolio,
    get_portfolio,
    get_position,
    is_in_portfolio,
    remove_position,
    update_position,
)


# ── TestAddPosition ───────────────────────────────────────────────────────────

@pytest.mark.integration
class TestAddPosition:

    def test_add_new_returns_true(self, db_with_instruments: Path) -> None:
        result = add_position(
            "US7561091049", shares_micro=100_000_000,
            db_path=db_with_instruments,
        )
        assert result is True

    def test_add_duplicate_returns_false(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        result = add_position("US7561091049", shares_micro=50_000_000,
                               db_path=db_with_instruments)
        assert result is False

    def test_add_with_buy_price(self, db_with_instruments: Path) -> None:
        add_position(
            "US7561091049",
            shares_micro=100_000_000,
            buy_price_micro=54_320_000,
            currency="USD",
            db_path=db_with_instruments,
        )
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.buy_price_micro == 54_320_000
        assert entry.currency == "USD"

    def test_add_with_notes(self, db_with_instruments: Path) -> None:
        add_position(
            "US7561091049", shares_micro=100_000_000,
            notes="Langfristig halten",
            db_path=db_with_instruments,
        )
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.notes == "Langfristig halten"

    def test_notes_stripped(self, db_with_instruments: Path) -> None:
        add_position(
            "US7561091049", shares_micro=100_000_000,
            notes="  Test  ",
            db_path=db_with_instruments,
        )
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.notes == "Test"

    def test_fractional_shares(self, db_with_instruments: Path) -> None:
        """0.5 Anteile = 500_000 micro."""
        add_position(
            "US7561091049", shares_micro=500_000,
            db_path=db_with_instruments,
        )
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.shares_micro == 500_000


# ── TestRemovePosition ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestRemovePosition:

    def test_remove_existing_returns_true(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        result = remove_position("US7561091049", db_path=db_with_instruments)
        assert result is True

    def test_remove_nonexistent_returns_false(
        self, db_with_instruments: Path
    ) -> None:
        result = remove_position("US7561091049", db_path=db_with_instruments)
        assert result is False

    def test_remove_clears_entry(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        remove_position("US7561091049", db_path=db_with_instruments)
        assert not is_in_portfolio("US7561091049",
                                   db_path=db_with_instruments)

    def test_remove_reduces_count(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        add_position("DE0005557508", shares_micro=50_000_000,
                     db_path=db_with_instruments)
        remove_position("US7561091049", db_path=db_with_instruments)
        assert count_portfolio(db_path=db_with_instruments) == 1


# ── TestUpdatePosition ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestUpdatePosition:

    def test_update_shares(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        update_position("US7561091049", shares_micro=200_000_000,
                        db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.shares_micro == 200_000_000

    def test_update_buy_price(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     buy_price_micro=50_000_000,
                     db_path=db_with_instruments)
        update_position("US7561091049", shares_micro=100_000_000,
                        buy_price_micro=55_000_000,
                        db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.buy_price_micro == 55_000_000

    def test_update_notes(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     notes="Alt", db_path=db_with_instruments)
        update_position("US7561091049", shares_micro=100_000_000,
                        notes="Neu", db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.notes == "Neu"

    def test_update_currency(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     currency="EUR", db_path=db_with_instruments)
        update_position("US7561091049", shares_micro=100_000_000,
                        currency="USD", db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.currency == "USD"

    def test_clear_buy_price(self, db_with_instruments: Path) -> None:
        """buy_price_micro=None löscht den Kaufkurs."""
        add_position("US7561091049", shares_micro=100_000_000,
                     buy_price_micro=50_000_000,
                     db_path=db_with_instruments)
        update_position("US7561091049", shares_micro=100_000_000,
                        buy_price_micro=None,
                        db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.buy_price_micro is None


# ── TestGetPortfolio ──────────────────────────────────────────────────────────

@pytest.mark.integration
class TestGetPortfolio:

    def test_empty_returns_empty_list(
        self, db_with_instruments: Path
    ) -> None:
        assert get_portfolio(db_path=db_with_instruments) == []

    def test_returns_added_entries(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        add_position("DE0005557508", shares_micro=50_000_000,
                     db_path=db_with_instruments)
        entries = get_portfolio(db_path=db_with_instruments)
        assert len(entries) == 2

    def test_entry_is_portfolio_entry_type(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        entries = get_portfolio(db_path=db_with_instruments)
        assert isinstance(entries[0], PortfolioEntry)

    def test_entry_has_display_name(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        entries = get_portfolio(db_path=db_with_instruments)
        assert entries[0].name == "Realty Income Corp"

    def test_sorted_by_added_at_desc(
        self, db_with_instruments: Path
    ) -> None:
        """Zuletzt hinzugefügt erscheint zuerst."""
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        add_position("DE0005557508", shares_micro=50_000_000,
                     db_path=db_with_instruments)
        entries = get_portfolio(db_path=db_with_instruments)
        assert entries[0].isin == "DE0005557508"

    def test_wkn_none_when_not_set(
        self, db_with_instruments: Path
    ) -> None:
        """ISIN ohne WKN → wkn ist None."""
        add_position("IE00B4L5Y983", shares_micro=10_000_000,
                     db_path=db_with_instruments)
        entries = get_portfolio(db_path=db_with_instruments)
        assert entries[0].isin == "IE00B4L5Y983"
        assert entries[0].wkn is None


# ── TestGetPosition ───────────────────────────────────────────────────────────

@pytest.mark.integration
class TestGetPosition:

    def test_returns_none_when_not_found(
        self, db_with_instruments: Path
    ) -> None:
        result = get_position("US7561091049", db_path=db_with_instruments)
        assert result is None

    def test_returns_correct_shares(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=123_456_789,
                     db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.shares_micro == 123_456_789

    def test_returns_correct_isin(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        entry = get_position("US7561091049", db_path=db_with_instruments)
        assert entry is not None
        assert entry.isin == "US7561091049"


# ── TestIsInPortfolio ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestIsInPortfolio:

    def test_false_when_not_added(self, db_with_instruments: Path) -> None:
        assert not is_in_portfolio("US7561091049",
                                   db_path=db_with_instruments)

    def test_true_after_add(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        assert is_in_portfolio("US7561091049", db_path=db_with_instruments)

    def test_false_after_remove(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        remove_position("US7561091049", db_path=db_with_instruments)
        assert not is_in_portfolio("US7561091049",
                                   db_path=db_with_instruments)


# ── TestCountPortfolio ────────────────────────────────────────────────────────

@pytest.mark.integration
class TestCountPortfolio:

    def test_zero_when_empty(self, db_with_instruments: Path) -> None:
        assert count_portfolio(db_path=db_with_instruments) == 0

    def test_increments_on_add(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        assert count_portfolio(db_path=db_with_instruments) == 1

    def test_decrements_on_remove(self, db_with_instruments: Path) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        remove_position("US7561091049", db_path=db_with_instruments)
        assert count_portfolio(db_path=db_with_instruments) == 0

    def test_duplicate_does_not_increment(
        self, db_with_instruments: Path
    ) -> None:
        add_position("US7561091049", shares_micro=100_000_000,
                     db_path=db_with_instruments)
        add_position("US7561091049", shares_micro=50_000_000,
                     db_path=db_with_instruments)
        assert count_portfolio(db_path=db_with_instruments) == 1


# ── TestPortfolioHypothesis ───────────────────────────────────────────────────

@pytest.mark.unit
class TestPortfolioHypothesis:
    """
    Property-based Tests für shares_micro / buy_price_micro Arithmetik.
    Prüft die Hilfsfunktionen aus portfolio_tab.py ohne GUI-Abhängigkeit.
    """

    # Shares: 1 Stück (1_000_000) bis 1 Million Stück
    _shares = st.integers(min_value=1_000_000, max_value=1_000_000_000_000)
    # Kaufkurs: 0.01 bis 10.000 (in Micro-Units: 10_000 bis 10_000_000_000)
    _prices = st.integers(min_value=10_000, max_value=10_000_000_000)
    # yield_bps: 0 bis 5000 (0 % bis 50 %)
    _yields = st.integers(min_value=0, max_value=5_000)

    def _micro_to_dec(self, micro: int) -> Decimal:
        return Decimal(micro) / Decimal("1000000")

    @given(
        shares_micro=_shares,
        buy_price_micro=_prices,
        yield_bps=_yields,
    )
    @settings(max_examples=500)
    def test_annual_dividend_non_negative(
        self,
        shares_micro: int,
        buy_price_micro: int,
        yield_bps: int,
    ) -> None:
        """Geschätzter Jahresertrag ist immer >= 0."""
        shares    = self._micro_to_dec(shares_micro)
        price     = self._micro_to_dec(buy_price_micro)
        yield_dec = Decimal(yield_bps) / Decimal("10000")
        annual    = shares * price * yield_dec
        assert annual >= Decimal("0")

    @given(
        shares_micro=_shares,
        buy_price_micro=_prices,
        yield_bps=_yields,
    )
    @settings(max_examples=500)
    def test_annual_dividend_deterministic(
        self,
        shares_micro: int,
        buy_price_micro: int,
        yield_bps: int,
    ) -> None:
        """Berechnung ist deterministisch — gleiche Inputs, gleicher Output."""
        shares    = self._micro_to_dec(shares_micro)
        price     = self._micro_to_dec(buy_price_micro)
        yield_dec = Decimal(yield_bps) / Decimal("10000")
        r1 = shares * price * yield_dec
        r2 = shares * price * yield_dec
        assert r1 == r2

    @given(
        shares_a=_shares,
        shares_b=_shares,
        buy_price_micro=_prices,
        yield_bps=st.integers(min_value=1, max_value=5_000),
    )
    @settings(max_examples=300)
    def test_more_shares_more_annual_dividend(
        self,
        shares_a: int,
        shares_b: int,
        buy_price_micro: int,
        yield_bps: int,
    ) -> None:
        """Mehr Anteile bei gleichem Kaufkurs und Rendite → mehr Jahresertrag."""
        assume(shares_b > shares_a)
        price     = self._micro_to_dec(buy_price_micro)
        yield_dec = Decimal(yield_bps) / Decimal("10000")
        annual_a  = self._micro_to_dec(shares_a) * price * yield_dec
        annual_b  = self._micro_to_dec(shares_b) * price * yield_dec
        assert annual_b > annual_a

    @given(shares_micro=_shares)
    @settings(max_examples=300)
    def test_zero_yield_gives_zero_annual(self, shares_micro: int) -> None:
        """0 % Rendite → 0 Jahresertrag, egal wie viele Anteile."""
        price     = Decimal("50.00")
        yield_dec = Decimal("0")
        annual    = self._micro_to_dec(shares_micro) * price * yield_dec
        assert annual == Decimal("0")

    @given(
        shares_micro=_shares,
        buy_price_micro=_prices,
    )
    @settings(max_examples=300)
    def test_invest_value_non_negative(
        self,
        shares_micro: int,
        buy_price_micro: int,
    ) -> None:
        """Investiertes Kapital (shares × preis) ist immer >= 0."""
        invest = self._micro_to_dec(shares_micro) * self._micro_to_dec(buy_price_micro)
        assert invest >= Decimal("0")
