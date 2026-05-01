# Dateiname:     tests/test_core/test_ticker_resolver.py
# Version:       2026-04-30-fix3
# Abhängigkeiten (intern): core.ticker_resolver
# Abhängigkeiten (extern): pytest, responses
"""
tests/test_core/test_ticker_resolver.py

Tests für core/ticker_resolver.py.

Abgedeckte Logik:
  - _get_preferred_exchanges()       — ISIN-land-basierte Börsenpräferenz
  - _select_best_figi()              — Auswahl aus OpenFIGI-Ergebnissen
  - _lookup_db()                     — Tupel-Rückgabe, unresolvable-TTL
  - _validate_ticker() / _with_retry — Suffix-Logik, keine Duplikate
  - _resolve_via_openfigi_internal() — regionaler Validierungsmodus
  - resolve()                        — Gesamtfluss
  - store_manual_mapping()           — manuelle Überschreibung
  - Unresolvable-Tracking            — TTL, Markierung, Überschreibung

HTTP-Schicht wird via responses-Library gemockt.
Netzwerk-Tests als 'slow' markiert — nicht in CI.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import responses as resp

from core.ticker_resolver import (
    UNRESOLVABLE_TTL_DAYS,
    ResolveStatus,
    _apply_suffix,
    _get_preferred_exchanges,
    _lookup_db,
    _resolve_via_openfigi_internal,
    _select_best_figi,
    _store_mapping,
    _store_unresolvable,
    _validate_ticker,
    resolve,
    store_manual_mapping,
)


# ── _get_preferred_exchanges ──────────────────────────────────────────────────

@pytest.mark.unit
class TestGetPreferredExchanges:

    def test_de_isin_prefers_xetra(self) -> None:
        assert _get_preferred_exchanges("DE0005557508")[0] == "GY"

    def test_us_isin_prefers_us(self) -> None:
        assert _get_preferred_exchanges("US88160R1014")[0] == "US"

    def test_at_isin_prefers_vienna(self) -> None:
        assert _get_preferred_exchanges("AT0000A38M45")[0] == "AV"

    def test_gb_isin_prefers_london(self) -> None:
        assert _get_preferred_exchanges("GB0002634946")[0] == "LN"

    def test_unknown_prefix_uses_fallback(self) -> None:
        assert len(_get_preferred_exchanges("XX0000000000")) > 0

    def test_primary_not_duplicated(self) -> None:
        assert _get_preferred_exchanges("DE0005557508").count("GY") == 1

    def test_returns_tuple(self) -> None:
        assert isinstance(_get_preferred_exchanges("US7561091049"), tuple)


# ── _select_best_figi ─────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSelectBestFigi:

    def test_de_isin_prefers_xetra_over_us(self) -> None:
        items = [
            {"ticker": "DTEGF", "exchCode": "US"},
            {"ticker": "DTE",   "exchCode": "GY"},
        ]
        result = _select_best_figi(items, isin="DE0005557508")
        assert result is not None
        assert result["ticker"] == "DTE"

    def test_us_isin_prefers_us_exchange(self) -> None:
        items = [
            {"ticker": "O.L", "exchCode": "LN"},
            {"ticker": "O",   "exchCode": "US"},
        ]
        result = _select_best_figi(items, isin="US7561091049")
        assert result is not None
        assert result["ticker"] == "O"

    def test_falls_back_to_first_if_no_preferred(self) -> None:
        items = [
            {"ticker": "XYZ.TK", "exchCode": "TK"},
            {"ticker": "XYZ.ZZ", "exchCode": "ZZ"},
        ]
        result = _select_best_figi(items, isin="XX0000000000")
        assert result is not None
        assert result["ticker"] == "XYZ.TK"

    def test_empty_list_returns_none(self) -> None:
        assert _select_best_figi([], isin="US0000000000") is None

    def test_backward_compat_no_isin(self) -> None:
        assert _select_best_figi([{"ticker": "ABC", "exchCode": "US"}]) is not None


# ── _apply_suffix ─────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestApplySuffix:

    def test_gy_adds_de_suffix(self) -> None:
        assert _apply_suffix("DTE", "GY") == "DTE.DE"

    def test_av_adds_vi_suffix(self) -> None:
        assert _apply_suffix("CLEN", "AV") == "CLEN.VI"

    def test_us_no_suffix(self) -> None:
        assert _apply_suffix("O", "US") == "O"

    def test_unknown_exchange_no_suffix(self) -> None:
        assert _apply_suffix("XYZ", "ZZ") == "XYZ"

    def test_no_duplicate_suffix(self) -> None:
        assert _apply_suffix("DTE.DE", "GY") == "DTE.DE"

    def test_none_exchange_no_suffix(self) -> None:
        assert _apply_suffix("ABC", None) == "ABC"


# ── _validate_ticker ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestValidateTicker:

    def test_suffix_candidate_tried_first(self) -> None:
        tried: list[str] = []

        def make_ticker(sym: str) -> MagicMock:
            tried.append(sym)
            m = MagicMock()
            m.info = {"symbol": sym, "quoteType": "EQUITY"}
            return m

        with patch("core.ticker_resolver.yf.Ticker", side_effect=make_ticker):
            result = _validate_ticker("DTE", exchange="GY")

        assert result == "DTE.DE"
        assert tried[0] == "DTE.DE"

    def test_falls_back_to_unsuffixed(self) -> None:
        call_num = 0

        def make_ticker(sym: str) -> MagicMock:
            nonlocal call_num
            call_num += 1
            m = MagicMock()
            m.info = {} if call_num == 1 else {"symbol": sym, "quoteType": "EQUITY"}
            return m

        with patch("core.ticker_resolver.yf.Ticker", side_effect=make_ticker):
            result = _validate_ticker("DTE", exchange="GY")

        assert result == "DTE"
        assert call_num == 2

    def test_returns_none_if_all_fail(self) -> None:
        m = MagicMock()
        m.info = {}
        with patch("core.ticker_resolver.yf.Ticker", return_value=m):
            assert _validate_ticker("UNKNOWN", exchange="GY") is None

    def test_no_duplicate_call_when_no_suffix(self) -> None:
        call_count = 0

        def make_ticker(sym: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            m = MagicMock()
            m.info = {"symbol": sym, "quoteType": "EQUITY"}
            return m

        with patch("core.ticker_resolver.yf.Ticker", side_effect=make_ticker):
            result = _validate_ticker("O", exchange="US")

        assert result == "O"
        assert call_count == 1


# ── _lookup_db ────────────────────────────────────────────────────────────────

@pytest.mark.integration
class TestLookupDb:

    def test_returns_none_tuple_when_not_found(
        self, db_with_instruments: Path
    ) -> None:
        ticker, source = _lookup_db("XX9999999999", db_path=db_with_instruments)
        assert ticker is None
        assert source is None

    def test_returns_ticker_and_source(
        self, db_with_instruments: Path
    ) -> None:
        _store_mapping("US7561091049", "O", "manual",
                       db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O"
        assert source == "manual"

    def test_unresolvable_returns_none_with_source(
        self, db_with_instruments: Path
    ) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker is None
        assert source == "unresolvable"

    def test_openfigi_unvalidated_stored_and_retrieved(
        self, db_with_instruments: Path
    ) -> None:
        _store_mapping("US7561091049", "SOME_TICKER", "openfigi_unvalidated",
                       db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "SOME_TICKER"
        assert source == "openfigi_unvalidated"


# ── Manuelle Mappings ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestManualMapping:

    def test_store_and_lookup(self, db_with_instruments: Path) -> None:
        store_manual_mapping("US7561091049", "O", exchange="US",
                             db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O"
        assert source == "manual"

    def test_manual_overwrites_yfinance(self, db_with_instruments: Path) -> None:
        _store_mapping("US7561091049", "O_AUTO", "yfinance",
                       db_path=db_with_instruments)
        store_manual_mapping("US7561091049", "O_MANUAL",
                             db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O_MANUAL"
        assert source == "manual"

    def test_manual_overwrites_unresolvable(
        self, db_with_instruments: Path
    ) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        store_manual_mapping("US7561091049", "O_MANUAL",
                             db_path=db_with_instruments)
        ticker, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O_MANUAL"
        assert source == "manual"


# ── Unresolvable-Tracking ─────────────────────────────────────────────────────

@pytest.mark.integration
class TestUnresolvableTracking:

    def test_marked_as_unresolvable(self, db_with_instruments: Path) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        _, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert source == "unresolvable"

    def test_resolve_returns_none_for_unresolvable(
        self, db_with_instruments: Path
    ) -> None:
        _store_unresolvable("US7561091049", db_path=db_with_instruments)
        result = resolve("US7561091049", db_path=db_with_instruments,
                         skip_openfigi=True)
        assert result is None


# ── OpenFIGI Mock-Tests ───────────────────────────────────────────────────────

@pytest.mark.unit
class TestOpenFIGIMocked:

    @resp.activate
    def test_us_isin_requires_yfinance_validation(
        self, db_with_instruments: Path
    ) -> None:
        """US-ISIN: yfinance-Validierung fehlgeschlagen → (None, NO_DATA)."""
        resp.add(
            resp.POST, "https://api.openfigi.com/v3/mapping",
            json=[{"data": [{"ticker": "O", "exchCode": "US",
                             "figi": "BBG000BTXHJ4"}]}],
            status=200,
        )
        with patch("core.ticker_resolver._validate_ticker", return_value=None):
            ticker, status = _resolve_via_openfigi_internal(
                "US7561091049", db_path=db_with_instruments
            )
        assert ticker is None
        assert status == ResolveStatus.NO_DATA

    @resp.activate
    def test_exotic_isin_stored_as_unvalidated(
        self, db_with_instruments: Path
    ) -> None:
        """
        IE-ISIN nicht in _ISIN_PREFIXES_REQUIRE_YF_VALIDATION.
        yfinance-Validierung fehlgeschlagen → als openfigi_unvalidated gespeichert.
        IE00B4L5Y983 ist in db_with_instruments vorhanden.
        """
        resp.add(
            resp.POST, "https://api.openfigi.com/v3/mapping",
            json=[{"data": [{"ticker": "IWRD", "exchCode": "LN"}]}],
            status=200,
        )
        with patch("core.ticker_resolver._validate_ticker", return_value=None):
            ticker, status = _resolve_via_openfigi_internal(
                "IE00B4L5Y983", db_path=db_with_instruments
            )
        assert ticker == "IWRD"
        assert status == ResolveStatus.SUCCESS
        _, source = _lookup_db("IE00B4L5Y983", db_path=db_with_instruments)
        assert source == "openfigi_unvalidated"

    @resp.activate
    def test_successful_validated_resolution(
        self, db_with_instruments: Path
    ) -> None:
        """Erfolgreiche Auflösung mit Validierung → source='openfigi'."""
        resp.add(
            resp.POST, "https://api.openfigi.com/v3/mapping",
            json=[{"data": [{"ticker": "O", "exchCode": "US",
                             "figi": "BBG000BTXHJ4"}]}],
            status=200,
        )
        with patch("core.ticker_resolver._validate_ticker", return_value="O"):
            ticker, status = _resolve_via_openfigi_internal(
                "US7561091049", db_path=db_with_instruments
            )
        assert ticker == "O"
        assert status == ResolveStatus.SUCCESS
        stored, source = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert stored == "O"
        assert source == "openfigi"

    @resp.activate
    def test_rate_limit_returns_rate_limit_status(
        self, db_with_instruments: Path
    ) -> None:
        resp.add(resp.POST, "https://api.openfigi.com/v3/mapping", status=429)
        _, status = _resolve_via_openfigi_internal(
            "US7561091049", db_path=db_with_instruments
        )
        assert status == ResolveStatus.RATE_LIMIT

    @resp.activate
    def test_warning_response_returns_no_data(
        self, db_with_instruments: Path
    ) -> None:
        resp.add(
            resp.POST, "https://api.openfigi.com/v3/mapping",
            json=[{"warning": "No identifier found."}],
            status=200,
        )
        _, status = _resolve_via_openfigi_internal(
            "US7561091049", db_path=db_with_instruments
        )
        assert status == ResolveStatus.NO_DATA

    @resp.activate
    def test_de_isin_gets_xetra_ticker_not_otc(
        self, db_with_instruments: Path
    ) -> None:
        """Regressionstest: DE-ISIN → DTE.DE (XETRA), nicht DTEGF (OTC)."""
        resp.add(
            resp.POST, "https://api.openfigi.com/v3/mapping",
            json=[{"data": [
                {"ticker": "DTEGF", "exchCode": "US"},
                {"ticker": "DTE",   "exchCode": "GY"},
            ]}],
            status=200,
        )
        with patch("core.ticker_resolver._validate_ticker",
                   return_value="DTE.DE"):
            ticker, status = _resolve_via_openfigi_internal(
                "DE0005557508", db_path=db_with_instruments
            )
        assert ticker == "DTE.DE"
        assert status == ResolveStatus.SUCCESS

    @resp.activate
    def test_unresolvable_marked_after_all_fail(
        self, db_with_instruments: Path
    ) -> None:
        """
        OpenFIGI NO_DATA + yfinance fehlgeschlagen → unresolvable.
        IE00B4L5Y983 ist in db_with_instruments vorhanden.
        """
        resp.add(
            resp.POST, "https://api.openfigi.com/v3/mapping",
            json=[{"warning": "No identifier found."}],
            status=200,
        )
        with patch("core.ticker_resolver._resolve_via_yfinance",
                   return_value=None):
            result = resolve("IE00B4L5Y983", db_path=db_with_instruments)
        assert result is None
        _, source = _lookup_db("IE00B4L5Y983", db_path=db_with_instruments)
        assert source == "unresolvable"