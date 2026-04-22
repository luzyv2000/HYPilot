# Dateiname:     tests/test_analysis/test_rules.py
# Version:       2026-04-22
"""
tests/test_analysis/test_rules.py

Tests für Instrument-Klassifikation und Filterlogik.
"""

from __future__ import annotations

import pytest

from analysis.filter import is_investable
from analysis.rules import classify_instrument


class TestClassifyInstrument:

    @pytest.mark.unit
    @pytest.mark.parametrize("name,isin,expected", [
        ("iShares MSCI World (Acc)",          "IE00B4L5Y983", "ETF"),
        ("Vanguard FTSE All-World (Dist)",    "IE00B3RBWM25", "ETF"),
        ("MSCI World UCITS ETF",              "LU0274208692", "ETF"),
        ("Tesla Inc",                         "US88160R1014", "STOCK"),
        ("Deutsche Telekom AG",               "DE0005557508", "STOCK"),
        ("US Treasury Bond",                  "US912810TM86", "BOND"),
        ("3x Leveraged S&P 500",              "IE00BLPK3577", "DERIVATIVE"),
        ("Covered Call Strategy USD (Dist)",  "IE000ABCDEF1", "OPTION_STRATEGY"),
    ])
    def test_classification(
        self, name: str, isin: str, expected: str
    ) -> None:
        assert classify_instrument(name, isin) == expected

    @pytest.mark.unit
    def test_ads_tec_is_stock(self) -> None:
        """Regressionstest: ADS TEC darf nicht als ETF klassifiziert werden."""
        assert classify_instrument("ADS TEC", "IE000XYZ1234") == "STOCK"


class TestIsInvestable:

    @pytest.mark.unit
    @pytest.mark.parametrize("name,expected", [
        ("Realty Income Corp",        True),
        ("iShares MSCI World (Acc)",  True),
        ("100 (Acc)",                 False),  # Parser-Artefakt
        ("100 EUR Hedged (Acc)",      False),  # Parser-Artefakt
        ("Short ETF USD",             False),  # short
        ("Covered Call Strategy",     False),  # covered call
        ("Euro Swap Fund",            False),  # swap
        ("AB",                        False),  # zu kurz
    ])
    def test_investable_filter(self, name: str, expected: bool) -> None:
        assert is_investable({"name": name}) == expected
