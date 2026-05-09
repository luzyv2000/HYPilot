# Dateiname:     tests/test_core/test_email_service.py
# Version:       2026-05-09
# Abhängigkeiten (intern): core.email_service
# Abhängigkeiten (extern): pytest
"""
tests/test_core/test_email_service.py

Tests für core/email_service.py.

Kein echter SMTP-Call — smtplib wird via unittest.mock gepatcht.
Credentials werden via patch gesetzt — keine .env nötig.

Abgedeckte Pfade:
  - Fehlende Konfiguration → False ohne Exception
  - SMTP-Authentifizierungsfehler → False
  - Erfolgreicher Versand (STARTTLS Port 587) → True
  - Erfolgreicher Versand (SSL Port 465) → True
  - HTML-Body enthält Statistiken und Crossings
  - Leere Crossings-Liste → Platzhaltertext im Body
"""

from __future__ import annotations

import smtplib
from unittest.mock import MagicMock, patch

import pytest

from core.email_service import send_batch_summary, _build_body


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _make_env(
    host: str = "smtp.example.com",
    port: str = "587",
    user: str = "test@example.com",
    password: str = "secret",
    from_addr: str = "",
    to_1: str = "a@example.com",
    to_2: str = "b@example.com",
) -> dict[str, str]:
    return {
        "SMTP_HOST":     host,
        "SMTP_PORT":     port,
        "SMTP_USER":     user,
        "SMTP_PASSWORD": password,
        "SMTP_FROM":     from_addr,
        "SMTP_TO_1":     to_1,
        "SMTP_TO_2":     to_2,
    }


def _patch_env(env: dict[str, str]):
    return patch.dict("os.environ", env, clear=False)


_STATS = {"processed": 100, "updated": 80, "skipped": 20}

_CROSSINGS = [
    {
        "isin":          "US7561091049",
        "display_name":  "Realty Income Corp",
        "yield_bps_old": 950,
        "yield_bps_new": 1050,
        "direction":     "up",
    },
]


# ── Fehlende Konfiguration ────────────────────────────────────────────────────

@pytest.mark.unit
class TestMissingConfig:

    def test_no_host_returns_false(self) -> None:
        env = _make_env(host="")
        with _patch_env(env):
            assert send_batch_summary(_STATS, [], "Test") is False

    def test_no_user_returns_false(self) -> None:
        env = _make_env(user="")
        with _patch_env(env):
            assert send_batch_summary(_STATS, [], "Test") is False

    def test_no_password_returns_false(self) -> None:
        env = _make_env(password="")
        with _patch_env(env):
            assert send_batch_summary(_STATS, [], "Test") is False

    def test_no_recipients_returns_false(self) -> None:
        env = _make_env(to_1="", to_2="")
        with _patch_env(env):
            assert send_batch_summary(_STATS, [], "Test") is False


# ── SMTP-Fehler ───────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestSmtpErrors:

    def test_auth_error_returns_false(self) -> None:
        env = _make_env()
        mock_smtp = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(
            side_effect=smtplib.SMTPAuthenticationError(535, b"Auth failed")
        )
        with _patch_env(env):
            with patch("smtplib.SMTP", mock_smtp):
                result = send_batch_summary(_STATS, [], "Test")
        assert result is False

    def test_generic_exception_returns_false(self) -> None:
        env = _make_env()
        with _patch_env(env):
            with patch("smtplib.SMTP", side_effect=OSError("Connection refused")):
                result = send_batch_summary(_STATS, [], "Test")
        assert result is False


# ── Erfolgreicher Versand ─────────────────────────────────────────────────────

@pytest.mark.unit
class TestSuccessfulSend:

    def _make_mock_smtp(self) -> MagicMock:
        mock_server = MagicMock()
        mock_smtp   = MagicMock()
        mock_smtp.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp.return_value.__exit__  = MagicMock(return_value=False)
        return mock_smtp, mock_server

    def test_starttls_port_587_returns_true(self) -> None:
        env = _make_env(port="587")
        mock_smtp, mock_server = self._make_mock_smtp()
        with _patch_env(env):
            with patch("smtplib.SMTP", mock_smtp):
                result = send_batch_summary(_STATS, _CROSSINGS, "Test-Lauf")
        assert result is True

    def test_ssl_port_465_returns_true(self) -> None:
        env = _make_env(port="465")
        mock_smtp, mock_server = self._make_mock_smtp()
        with _patch_env(env):
            with patch("smtplib.SMTP_SSL", mock_smtp):
                result = send_batch_summary(_STATS, _CROSSINGS, "Test-Lauf")
        assert result is True

    def test_sendmail_called_with_recipients(self) -> None:
        env = _make_env(port="587")
        mock_smtp, mock_server = self._make_mock_smtp()
        with _patch_env(env):
            with patch("smtplib.SMTP", mock_smtp):
                send_batch_summary(_STATS, [], "Test-Lauf")
        mock_server.sendmail.assert_called_once()
        call_args = mock_server.sendmail.call_args
        recipients = call_args[0][1]
        assert "a@example.com" in recipients
        assert "b@example.com" in recipients

    def test_login_called_with_credentials(self) -> None:
        env = _make_env(port="587", user="u@x.com", password="pw123")
        mock_smtp, mock_server = self._make_mock_smtp()
        with _patch_env(env):
            with patch("smtplib.SMTP", mock_smtp):
                send_batch_summary(_STATS, [], "Test-Lauf")
        mock_server.login.assert_called_once_with("u@x.com", "pw123")


# ── HTML-Body ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildBody:

    def test_body_contains_run_label(self) -> None:
        body = _build_body(_STATS, [], "Mein Test-Lauf")
        assert "Mein Test-Lauf" in body

    def test_body_contains_processed_count(self) -> None:
        body = _build_body(_STATS, [], "Test")
        assert "100" in body

    def test_body_contains_updated_count(self) -> None:
        body = _build_body(_STATS, [], "Test")
        assert "80" in body

    def test_body_contains_skipped_count(self) -> None:
        body = _build_body(_STATS, [], "Test")
        assert "20" in body

    def test_body_with_crossing_contains_isin(self) -> None:
        body = _build_body(_STATS, _CROSSINGS, "Test")
        assert "US7561091049" in body

    def test_body_with_crossing_contains_name(self) -> None:
        body = _build_body(_STATS, _CROSSINGS, "Test")
        assert "Realty Income Corp" in body

    def test_body_with_crossing_contains_direction_arrow(self) -> None:
        body = _build_body(_STATS, _CROSSINGS, "Test")
        assert "▲" in body

    def test_empty_crossings_shows_placeholder(self) -> None:
        body = _build_body(_STATS, [], "Test")
        assert "Keine Schwellwert" in body

    def test_body_is_html(self) -> None:
        body = _build_body(_STATS, [], "Test")
        assert "<html" in body
        assert "</html>" in body
