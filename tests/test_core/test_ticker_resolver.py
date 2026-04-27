# Dateiname:     tests/test_core/test_ticker_resolver.py
# Version:       2026-04-27
"""
tests/test_core/test_ticker_resolver.py

Tests für core.ticker_resolver.
Netzwerk-Tests als 'slow' markiert — nicht in CI.
HTTP-Schicht wird via responses-Library gemockt.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp

from core.ticker_resolver import (
    UNRESOLVABLE_TTL_DAYS,
    _get_preferred_exchanges,
    _lookup_db,
    _select_best_figi,
    _store_mapping,
    _store_unresolvable,
    resolve,
    store_manual_mapping,
)


# ── _get_preferred_exchanges ──────────────────────────────────────────────────

class TestGetPreferredExchanges:

    @pytest.mark.unit
    def test_de_isin_prefers_xetra(self) -> None:
        pref = _get_preferred_exchanges("DE0005557508")
        assert pref[0] == "GY"

    @pytest.mark.unit
    def test_us_isin_prefers_us(self) -> None:
        pref = _get_preferred_exchanges("US88160R1014")
        assert pref[0] == "US"

    @pytest.mark.unit
    def test_at_isin_prefers_vienna(self) -> None:
        pref = _get_preferred_exchanges("AT0000A38M45")
        assert pref[0] == "AV"

    @pytest.mark.unit
    def test_unknown_prefix_uses_fallback(self) -> None:
        pref = _get_preferred_exchanges("XX0000000000")
        assert len(pref) > 0

    @pytest.mark.unit
    def test_primary_not_duplicated(self) -> None:
        pref = _get_preferred_exchanges("DE0005557508")
        assert pref.count("GY") == 1


# ── _select_best_figi ─────────────────────────────────────────────────────────

class TestSelectBestFigi:

    @pytest.mark.unit
    def test_de_isin_prefers_xetra_over_us(self) -> None:
        """Deutsche ISINs sollen XETRA (GY) vor US-OTC bekommen."""
        items = [
            {"ticker": "DTEGF", "exchCode": "US"},
            {"ticker": "DTE",   "exchCode": "GY"},
        ]
        result = _select_best_figi(items, isin="DE0005557508")
        assert result is not None
        assert result["ticker"] == "DTE"

    @pytest.mark.unit
    def test_us_isin_prefers_us_exchange(self) -> None:
        items = [
            {"ticker": "O.L", "exchCode": "LN"},
            {"ticker": "O",   "exchCode": "US"},
        ]
        result = _select_best_figi(items, isin="US7561091049")
        assert result is not None
        assert result["ticker"] == "O"

    @pytest.mark.unit
    def test_falls_back_to_first_if_no_preferred(self) -> None:
        items = [
            {"ticker": "XYZ.TK", "exchCode": "TK"},
            {"ticker": "XYZ.ZZ", "exchCode": "ZZ"},
        ]
        result = _select_best_figi(items, isin="XX0000000000")
        assert result is not None
        assert result["ticker"] == "XYZ.TK"

    @pytest.mark.unit
    def test_empty_list_returns_none(self) -> None:
        assert _select_best_figi([], isin="US0000000000") is None

    @pytest.mark.unit
    def test_backward_compat_no_isin(self) -> None:
        """Aufruf ohne isin darf nicht crashen."""
        items = [{"ticker": "ABC", "exchCode": "US"}]
        result = _select_best_figi(items)
        assert result is not None


# ── _lookup_db ────────────────────────────────────────────────────────────────

class TestLookupDb:

    @pytest.mark.integration
    def test_returns_none_tuple_when_not_found(
        self, db_with_instruments: Path
    ) -> None:
        ticker, source = _lookup_db("XX9999999999", db_path=db_with_instruments)
        assert ticker is None
        assert source is None

    @pytest.mark.integration
    def test_returns_ticker_and_source(
        self, db_with_instruments: Path
    ) -> None:
        _store_mapping(
            "US7561091049", "O", "manual",
            db_path=db_with_instruments,
        )
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O"
        assert source == "manual"

    @pytest.mark.integration
    def test_unresolvable_returns_none_with_source(
        self, db_with_instruments: Path
    ) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker is None
        assert source == "unresolvable"


# ── Manuelle Mappings ─────────────────────────────────────────────────────────

class TestManualMapping:

    @pytest.mark.integration
    def test_store_and_lookup(self, db_with_instruments: Path) -> None:
        store_manual_mapping(
            "US7561091049", "O",
            exchange="US",
            db_path=db_with_instruments,
        )
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O"
        assert source == "manual"

    @pytest.mark.integration
    def test_manual_overwrites_yfinance(self, db_with_instruments: Path) -> None:
        _store_mapping(
            "US7561091049", "O_AUTO", "yfinance",
            db_path=db_with_instruments,
        )
        store_manual_mapping(
            "US7561091049", "O_MANUAL",
            db_path=db_with_instruments,
        )
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O_MANUAL"
        assert source == "manual"


# ── Unresolvable-Tracking ─────────────────────────────────────────────────────

class TestUnresolvableTracking:

    @pytest.mark.integration
    def test_marked_as_unresolvable(self, db_with_instruments: Path) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        _, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert source == "unresolvable"

    @pytest.mark.integration
    def test_resolve_returns_none_for_unresolvable(
        self, db_with_instruments: Path
    ) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        result = resolve(
            "US7561091049",
            db_path=db_with_instruments,
            skip_openfigi=True,
        )
        assert result is None

    @pytest.mark.integration
    def test_manual_overrides_unresolvable(
        self, db_with_instruments: Path
    ) -> None:
        """Manuelles Mapping soll unresolvable überschreiben."""
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        store_manual_mapping(
            "US7561091049", "O_MANUAL",
            db_path=db_with_instruments,
        )
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O_MANUAL"


# ── OpenFIGI Mock-Tests ───────────────────────────────────────────────────────

class TestOpenFIGIMocked:

    @pytest.mark.unit
    @resp.activate
    def test_successful_resolution(self, db_with_instruments: Path) -> None:
        resp.add(
            resp.POST,
            "https://api.openfigi.com/v3/mapping",
            json=[{"data": [{"ticker": "O", "exchCode": "US",
                              "figi": "BBG000BTXHJ4"}]}],
            status=200,
        )
        # yfinance-Validierung mocken — kein echter Netzwerk-Call in CI
        with patch("core.ticker_resolver._validate_ticker", return_value="O"):
            ticker = resolve(
                "US7561091049",
                db_path=db_with_instruments,
            )
        assert ticker == "O"

    @pytest.mark.unit
    @resp.activate
    def test_rate_limit_returns_none_without_crash(
        self, db_with_instruments: Path
    ) -> None:
        resp.add(
            resp.POST,
            "https://api.openfigi.com/v3/mapping",
            status=429,
        )
        with patch("core.ticker_resolver._resolve_via_yfinance", return_value=None):
            result = resolve(
                "US0000000001",
                db_path=db_with_instruments,
            )
        assert result is None

    @pytest.mark.unit
    @resp.activate
    def test_warning_response_returns_none(
        self, db_with_instruments: Path
    ) -> None:
        resp.add(
            resp.POST,
            "https://api.openfigi.com/v3/mapping",
            json=[{"warning": "No identifier found."}],
            status=200,
        )
        from core.ticker_resolver import _resolve_via_openfigi
        with patch("core.ticker_resolver._validate_ticker", return_value=None):
            result = _resolve_via_openfigi(
                "XX0000000000",
                db_path=db_with_instruments,
            )
        assert result is None

    @pytest.mark.unit
    @resp.activate
    def test_de_isin_uses_xetra_ticker(
        self, db_with_instruments: Path
    ) -> None:
        """Regressionstest: DE-ISIN darf nicht DTEGF bekommen."""
        resp.add(
            resp.POST,
            "https://api.openfigi.com/v3/mapping",
            json=[{"data": [
                {"ticker": "DTEGF", "exchCode": "US"},
                {"ticker": "DTE",   "exchCode": "GY"},
            ]}],
            status=200,
        )
        with patch("core.ticker_resolver._validate_ticker",
                   side_effect=lambda t, e=None: t):
            from core.ticker_resolver import _resolve_via_openfigi
            ticker = _resolve_via_openfigi(
                "DE0005557508",
                db_path=db_with_instruments,
            )
        assert ticker == "DTE"
