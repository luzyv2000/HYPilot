# Dateiname:     tests/test_core/test_ticker_resolver.py
# Version:       2026-04-23-B
"""
Tests für ticker_resolver.

Netzwerk-Tests sind als 'slow' markiert und werden im Normalbetrieb
übersprungen. Unit-Tests mocken die HTTP-Schicht via responses.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import responses as resp

from core.ticker_resolver import (
    _select_best_figi,
    _store_mapping,
    _lookup_db,
    resolve,
    store_manual_mapping,
)


# ── _select_best_figi ─────────────────────────────────────────────────────────

class TestSelectBestFigi:

    @pytest.mark.unit
    def test_prefers_us_exchange(self) -> None:
        items = [
            {"ticker": "O.L",  "exchCode": "LN"},
            {"ticker": "O",    "exchCode": "US"},
            {"ticker": "O.DE", "exchCode": "GY"},
        ]
        result = _select_best_figi(items)
        assert result is not None
        assert result["ticker"] == "O"

    @pytest.mark.unit
    def test_falls_back_to_first_if_no_preferred(self) -> None:
        items = [
            {"ticker": "XYZ.TK", "exchCode": "TK"},
            {"ticker": "XYZ.AU", "exchCode": "AU"},
        ]
        result = _select_best_figi(items)
        assert result is not None
        assert result["ticker"] == "XYZ.TK"

    @pytest.mark.unit
    def test_empty_list_returns_none(self) -> None:
        assert _select_best_figi([]) is None


# ── Manuelle Mappings ─────────────────────────────────────────────────────────

class TestManualMapping:

    @pytest.mark.integration
    def test_store_and_lookup(self, db_with_instruments: Path) -> None:
        store_manual_mapping(
            "US7561091049", "O",
            exchange="US",
            db_path=db_with_instruments,
        )
        ticker = _lookup_db("US7561091049", db_path=db_with_instruments)
        assert ticker == "O"

    @pytest.mark.integration
    def test_manual_overwrites_yfinance(self, db_with_instruments: Path) -> None:
        _store_mapping(
            "US7561091049", "O_AUTO",
            source="yfinance",
            db_path=db_with_instruments,
        )
        store_manual_mapping(
            "US7561091049", "O_MANUAL",
            db_path=db_with_instruments,
        )
        ticker = _lookup_db("US7561091049", db_path=db_with_instruments)
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
        ticker = resolve(
            "US7561091049",
            db_path=db_with_instruments,
        )
        assert ticker == "O"

    @pytest.mark.unit
    @resp.activate
    def test_rate_limit_falls_back_gracefully(
        self, db_with_instruments: Path
    ) -> None:
        resp.add(
            resp.POST,
            "https://api.openfigi.com/v3/mapping",
            status=429,
        )
        # Kein Crash erwartet — None oder yfinance-Ergebnis
        result = resolve(
            "US0000000001",
            db_path=db_with_instruments,
            skip_openfigi=False,
        )
        # Nur prüfen dass kein Exception geworfen wird
        assert result is None or isinstance(result, str)

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
        result = _resolve_via_openfigi(
            "XX0000000000",
            db_path=db_with_instruments,
        )
        assert result is None
