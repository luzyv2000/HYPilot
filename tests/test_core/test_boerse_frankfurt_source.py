# Dateiname:     tests/test_core/test_boerse_frankfurt_source.py
# Version:       2026-05-09
# Abhängigkeiten (intern): core.sources.boerse_frankfurt_source
# Abhängigkeiten (extern): pytest
"""
tests/test_core/test_boerse_frankfurt_source.py

Tests für core/sources/boerse_frankfurt_source.py (Stub).

Der Stub ist bewusst inaktiv — alle Methoden geben None / []
zurück ohne Netzwerk-Call. Tests verifizieren dieses Verhalten
und stellen sicher dass der Stub keinen Fehler produziert.
"""

from __future__ import annotations

import pytest

from core.sources.boerse_frankfurt_source import BoerseFrankfurtSource


@pytest.fixture
def source() -> BoerseFrankfurtSource:
    return BoerseFrankfurtSource()


@pytest.mark.unit
class TestBoerseFrankfurtStub:

    def test_source_name(self, source: BoerseFrankfurtSource) -> None:
        assert source.source_name == "boerse_frankfurt"

    def test_fetch_snapshot_returns_none(
        self, source: BoerseFrankfurtSource
    ) -> None:
        """Stub gibt immer None zurück — kein Netzwerk-Call."""
        result = source.fetch_snapshot("DE0005557508")
        assert result is None

    def test_fetch_snapshot_with_ticker_returns_none(
        self, source: BoerseFrankfurtSource
    ) -> None:
        result = source.fetch_snapshot("DE0005557508", ticker="DTE.DE")
        assert result is None

    def test_fetch_history_returns_empty_list(
        self, source: BoerseFrankfurtSource
    ) -> None:
        """Stub gibt immer leere Liste zurück — kein Netzwerk-Call."""
        result = source.fetch_history("DE0005557508")
        assert result == []

    def test_fetch_history_with_ticker_returns_empty_list(
        self, source: BoerseFrankfurtSource
    ) -> None:
        result = source.fetch_history("DE0005557508", ticker="DTE.DE")
        assert result == []

    def test_no_network_call_on_fetch_snapshot(
        self, source: BoerseFrankfurtSource
    ) -> None:
        """Stub darf keine Netzwerk-Verbindung aufbauen."""
        import socket
        original = socket.socket

        def fail_if_called(*args, **kwargs):
            raise AssertionError("Stub hat eine Netzwerk-Verbindung versucht.")

        socket.socket = fail_if_called
        try:
            source.fetch_snapshot("DE0005557508")
        finally:
            socket.socket = original

    def test_no_network_call_on_fetch_history(
        self, source: BoerseFrankfurtSource
    ) -> None:
        import socket
        original = socket.socket

        def fail_if_called(*args, **kwargs):
            raise AssertionError("Stub hat eine Netzwerk-Verbindung versucht.")

        socket.socket = fail_if_called
        try:
            source.fetch_history("DE0005557508")
        finally:
            socket.socket = original
