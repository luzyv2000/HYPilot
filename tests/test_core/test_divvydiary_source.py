# Dateiname:     tests/test_core/test_divvydiary_source.py
# Version:       2026-05-09
# Abhängigkeiten (intern): core.sources.divvydiary_source
# Abhängigkeiten (extern): pytest, responses
"""
tests/test_core/test_divvydiary_source.py

Tests für core/sources/divvydiary_source.py.

Alle HTTP-Calls via responses-Mock — kein Netzwerk.
Kein API-Key nötig: _API_KEY wird via patch gesetzt.

Abgedeckte Pfade:
  - Kein API-Key → sofort None
  - HTTP 404    → None
  - HTTP 429    → None (Rate-Limit)
  - HTTP 500    → None
  - Leere Dividenden-Liste → None (kein Snapshot ohne Daten)
  - Gültige Antwort → DividendSnapshot mit korrekten Werten
  - Frequenzerkennung aus Zahlungsanzahl
  - Ungültige Einträge in dividends-Liste werden übersprungen
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest
import responses as resp

from core.sources.divvydiary_source import DivvyDiarySource

_ISIN = "US7561091049"
_URL  = f"https://api.divvydiary.com/symbols/{_ISIN}"

# Minimale gültige API-Antwort
_VALID_RESPONSE = {
    "isin":          _ISIN,
    "currency":      "USD",
    "dividendYield": 0.055,
    "payoutRatio":   0.65,
    "dividends": [
        {"exDate": "2026-03-15", "amount": 0.271},
        {"exDate": "2026-02-15", "amount": 0.271},
        {"exDate": "2026-01-15", "amount": 0.271},
        {"exDate": "2025-12-15", "amount": 0.271},
        {"exDate": "2025-11-15", "amount": 0.271},
        {"exDate": "2025-10-15", "amount": 0.271},
        {"exDate": "2025-09-15", "amount": 0.271},
        {"exDate": "2025-08-15", "amount": 0.271},
        {"exDate": "2025-07-15", "amount": 0.271},
        {"exDate": "2025-06-15", "amount": 0.271},
        {"exDate": "2025-05-15", "amount": 0.271},
        {"exDate": "2025-04-15", "amount": 0.271},
    ],
}


@pytest.fixture
def source() -> DivvyDiarySource:
    return DivvyDiarySource()


@pytest.fixture(autouse=True)
def patch_api_key():
    """Setzt einen Dummy-API-Key für alle Tests in dieser Datei."""
    with patch("core.sources.divvydiary_source._API_KEY", "test-key-123"):
        yield


@pytest.fixture(autouse=True)
def patch_delay():
    """Unterdrückt time.sleep in allen Tests."""
    with patch("core.sources.divvydiary_source.time.sleep"):
        yield


# ── fetch_snapshot: Kein API-Key ─────────────────────────────────────────────

@pytest.mark.unit
class TestNoApiKey:

    def test_returns_none_without_api_key(self, source: DivvyDiarySource) -> None:
        with patch("core.sources.divvydiary_source._API_KEY", ""):
            result = source.fetch_snapshot(_ISIN)
        assert result is None

    def test_fetch_history_returns_empty_without_api_key(
        self, source: DivvyDiarySource
    ) -> None:
        with patch("core.sources.divvydiary_source._API_KEY", ""):
            result = source.fetch_history(_ISIN)
        assert result == []


# ── fetch_snapshot: HTTP-Fehlerfälle ─────────────────────────────────────────

@pytest.mark.unit
class TestHttpErrors:

    @resp.activate
    def test_404_returns_none(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, status=404)
        assert source.fetch_snapshot(_ISIN) is None

    @resp.activate
    def test_429_returns_none(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, status=429)
        assert source.fetch_snapshot(_ISIN) is None

    @resp.activate
    def test_500_returns_none(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, status=500)
        assert source.fetch_snapshot(_ISIN) is None

    @resp.activate
    def test_network_error_returns_none(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, body=Exception("Connection refused"))
        assert source.fetch_snapshot(_ISIN) is None


# ── fetch_snapshot: Leere / unvollständige Antworten ─────────────────────────

@pytest.mark.unit
class TestEmptyResponses:

    @resp.activate
    def test_empty_dividends_and_no_yield_returns_none(
        self, source: DivvyDiarySource
    ) -> None:
        """Kein yield_bps + keine Historie → None."""
        resp.add(resp.GET, _URL, json={
            "isin": _ISIN, "currency": "USD",
            "dividendYield": None, "dividends": [],
        }, status=200)
        assert source.fetch_snapshot(_ISIN) is None

    @resp.activate
    def test_yield_without_dividends_returns_snapshot(
        self, source: DivvyDiarySource
    ) -> None:
        """yield_bps vorhanden aber keine Historie → Snapshot ohne Ex-Datum."""
        resp.add(resp.GET, _URL, json={
            "isin": _ISIN, "currency": "USD",
            "dividendYield": 0.055, "dividends": [],
        }, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.yield_bps == 550
        assert result.last_ex_date is None


# ── fetch_snapshot: Erfolgreiche Antwort ─────────────────────────────────────

@pytest.mark.unit
class TestSuccessfulSnapshot:

    @resp.activate
    def test_returns_dividend_snapshot(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None

    @resp.activate
    def test_source_name_is_divvydiary(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.data_source == "divvydiary"

    @resp.activate
    def test_yield_bps_correct(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.yield_bps == 550   # 0.055 * 10000

    @resp.activate
    def test_payout_ratio_correct(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.payout_ratio_bps == 6500  # 0.65 * 10000

    @resp.activate
    def test_currency_preserved(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.currency == "USD"

    @resp.activate
    def test_frequency_detected_as_monthly(self, source: DivvyDiarySource) -> None:
        """12 Zahlungen in einem Jahr → monthly."""
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.frequency == "monthly"

    @resp.activate
    def test_last_ex_date_is_most_recent(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.last_ex_date == date(2026, 3, 15)

    @resp.activate
    def test_last_amount_micro_correct(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.last_amount_micro == 271_000  # 0.271 * 1_000_000

    @resp.activate
    def test_isin_preserved(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.isin == _ISIN


# ── fetch_history: Frequenzerkennung ─────────────────────────────────────────

@pytest.mark.unit
class TestFrequencyDetection:

    def _make_payments(self, count: int) -> list[dict]:
        """Erzeugt `count` monatliche Zahlungen ab heute rückwärts."""
        from datetime import timedelta
        today = date.today()
        return [
            {
                "exDate": (today.replace(day=15) - __import__('datetime').timedelta(days=30 * i)).isoformat(),
                "amount": 0.25,
            }
            for i in range(count)
        ]

    @resp.activate
    def test_one_payment_annual(self, source: DivvyDiarySource) -> None:
        data = {**_VALID_RESPONSE, "dividends": self._make_payments(1)}
        resp.add(resp.GET, _URL, json=data, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.frequency == "annual"

    @resp.activate
    def test_two_payments_semi_annual(self, source: DivvyDiarySource) -> None:
        data = {**_VALID_RESPONSE, "dividends": self._make_payments(2)}
        resp.add(resp.GET, _URL, json=data, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.frequency == "semi_annual"

    @resp.activate
    def test_four_payments_quarterly(self, source: DivvyDiarySource) -> None:
        data = {**_VALID_RESPONSE, "dividends": self._make_payments(4)}
        resp.add(resp.GET, _URL, json=data, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.frequency == "quarterly"

    @resp.activate
    def test_twelve_payments_monthly(self, source: DivvyDiarySource) -> None:
        resp.add(resp.GET, _URL, json=_VALID_RESPONSE, status=200)
        result = source.fetch_snapshot(_ISIN)
        assert result is not None
        assert result.frequency == "monthly"


# ── fetch_history: Robustheit ─────────────────────────────────────────────────

@pytest.mark.unit
class TestFetchHistoryRobustness:

    @resp.activate
    def test_skips_entries_without_ex_date(
        self, source: DivvyDiarySource
    ) -> None:
        data = {
            **_VALID_RESPONSE,
            "dividends": [
                {"amount": 0.271},                      # kein exDate
                {"exDate": "2026-03-15", "amount": 0.271},
            ],
        }
        resp.add(resp.GET, _URL, json=data, status=200)
        payments = source.fetch_history(_ISIN)
        assert len(payments) == 1

    @resp.activate
    def test_skips_entries_with_zero_amount(
        self, source: DivvyDiarySource
    ) -> None:
        data = {
            **_VALID_RESPONSE,
            "dividends": [
                {"exDate": "2026-03-15", "amount": 0.0},
                {"exDate": "2026-02-15", "amount": 0.271},
            ],
        }
        resp.add(resp.GET, _URL, json=data, status=200)
        payments = source.fetch_history(_ISIN)
        assert len(payments) == 1
        assert payments[0].amount_micro == 271_000

    @resp.activate
    def test_skips_entries_older_than_3_years(
        self, source: DivvyDiarySource
    ) -> None:
        data = {
            **_VALID_RESPONSE,
            "dividends": [
                {"exDate": "2010-01-01", "amount": 0.271},  # zu alt
                {"exDate": "2026-03-15", "amount": 0.271},
            ],
        }
        resp.add(resp.GET, _URL, json=data, status=200)
        payments = source.fetch_history(_ISIN)
        assert len(payments) == 1
        assert payments[0].ex_date == date(2026, 3, 15)

    @resp.activate
    def test_alternate_field_name_value(
        self, source: DivvyDiarySource
    ) -> None:
        """Feldname 'value' statt 'amount' wird akzeptiert."""
        data = {
            **_VALID_RESPONSE,
            "dividends": [{"exDate": "2026-03-15", "value": 0.5}],
        }
        resp.add(resp.GET, _URL, json=data, status=200)
        payments = source.fetch_history(_ISIN)
        assert len(payments) == 1
        assert payments[0].amount_micro == 500_000

    @resp.activate
    def test_alternate_field_name_ex_date(
        self, source: DivvyDiarySource
    ) -> None:
        """Feldname 'ex_date' statt 'exDate' wird akzeptiert."""
        data = {
            **_VALID_RESPONSE,
            "dividends": [{"ex_date": "2026-03-15", "amount": 0.271}],
        }
        resp.add(resp.GET, _URL, json=data, status=200)
        payments = source.fetch_history(_ISIN)
        assert len(payments) == 1
