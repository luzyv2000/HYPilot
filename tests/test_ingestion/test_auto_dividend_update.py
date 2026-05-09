# Dateiname:     tests/test_ingestion/test_auto_dividend_update.py
# Version:       2026-05-09-fix1
# Abhängigkeiten (intern): ingestion.auto_dividend_update
# Abhängigkeiten (extern): pytest
"""
tests/test_ingestion/test_auto_dividend_update.py

Tests für ingestion/auto_dividend_update.py.

Kein echter Batch-Lauf, kein SMTP, kein Netzwerk.
update_batch_due, send_batch_summary und get_unshown_threshold_crossings
werden vollständig gemockt.

Fix 2026-05-09: _setup_logging() wird in allen main()-Tests gepatcht —
  verhindert PermissionError beim Erstellen des Log-Verzeichnisses
  in CI-Umgebungen ohne /home/luzy.

Abgedeckte Pfade:
  - _save_run_summary() schreibt korrekte Struktur in metadata
  - main() ruft update_batch_due in einer Schleife auf
  - main() bricht früh ab wenn keine fälligen ISINs mehr vorhanden
  - main() ruft send_batch_summary mit aggregierten Stats auf
  - main() speichert Zusammenfassung in DB
  - Summen aus mehreren Batches werden korrekt addiert
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ingestion.auto_dividend_update import _save_run_summary, main


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _read_last_auto_run(db_path: Path) -> dict:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'last_auto_run'"
        ).fetchone()
    assert row is not None, "last_auto_run nicht in metadata vorhanden"
    return json.loads(row[0])


def _run_main_with_mocks(
    batch_returns: list[dict],
    crossings: list | None = None,
) -> tuple[int, MagicMock, MagicMock]:
    """
    Führt main() mit vollständig gemockten Abhängigkeiten aus.
    _setup_logging wird immer gepatcht — verhindert PermissionError in CI.

    Args:
        batch_returns: Stats-Dicts die update_batch_due nacheinander liefert.
        crossings:     Rückgabe von get_unshown_threshold_crossings.

    Returns:
        (exit_code, mock_batch, mock_email)
    """
    if crossings is None:
        crossings = []

    mock_batch     = MagicMock(side_effect=batch_returns)
    mock_email     = MagicMock(return_value=True)
    mock_crossings = MagicMock(return_value=crossings)

    with patch("ingestion.auto_dividend_update._setup_logging"), \
         patch("ingestion.auto_dividend_update.update_batch_due", mock_batch), \
         patch("ingestion.auto_dividend_update.send_batch_summary", mock_email), \
         patch("ingestion.auto_dividend_update.get_unshown_threshold_crossings",
               mock_crossings), \
         patch("ingestion.auto_dividend_update._save_run_summary"):
        result = main()

    return result, mock_batch, mock_email


# ── _save_run_summary ─────────────────────────────────────────────────────────

@pytest.mark.integration
class TestSaveRunSummary:

    def test_writes_to_metadata(self, in_memory_db: Path) -> None:
        with patch("ingestion.auto_dividend_update.DB_PATH", in_memory_db):
            _save_run_summary(
                stats={"processed": 50, "updated": 40, "skipped": 10},
                crossings=[{"id": 1}, {"id": 2}],
            )
        data = _read_last_auto_run(in_memory_db)
        assert data["stats"]["processed"] == 50
        assert data["stats"]["updated"]   == 40
        assert data["stats"]["skipped"]   == 10

    def test_crossings_count_stored(self, in_memory_db: Path) -> None:
        with patch("ingestion.auto_dividend_update.DB_PATH", in_memory_db):
            _save_run_summary(
                stats={"processed": 10, "updated": 8, "skipped": 2},
                crossings=[{"id": 1}, {"id": 2}, {"id": 3}],
            )
        data = _read_last_auto_run(in_memory_db)
        assert data["crossings"] == 3

    def test_run_at_is_iso_timestamp(self, in_memory_db: Path) -> None:
        with patch("ingestion.auto_dividend_update.DB_PATH", in_memory_db):
            _save_run_summary(
                stats={"processed": 0, "updated": 0, "skipped": 0},
                crossings=[],
            )
        data = _read_last_auto_run(in_memory_db)
        from datetime import datetime
        parsed = datetime.fromisoformat(data["run_at"])
        assert parsed is not None

    def test_overwrites_previous_entry(self, in_memory_db: Path) -> None:
        """Zweiter Aufruf überschreibt ersten — kein Duplikat."""
        with patch("ingestion.auto_dividend_update.DB_PATH", in_memory_db):
            _save_run_summary({"processed": 10, "updated": 5, "skipped": 5}, [])
            _save_run_summary({"processed": 99, "updated": 90, "skipped": 9}, [])
        data = _read_last_auto_run(in_memory_db)
        assert data["stats"]["processed"] == 99

    def test_no_exception_on_invalid_db_path(self) -> None:
        """Ungültiger DB-Pfad → kein Crash, nur Warning."""
        bad_path = Path("/nonexistent/path/hypilot.db")
        with patch("ingestion.auto_dividend_update.DB_PATH", bad_path):
            _save_run_summary({"processed": 0, "updated": 0, "skipped": 0}, [])


# ── main(): Schleifensteuerung ────────────────────────────────────────────────

@pytest.mark.unit
class TestMainLoop:

    def test_main_returns_zero_on_success(self) -> None:
        # Letzter Batch liefert 0 processed → Schleife endet
        full  = {"processed": 100, "updated": 80, "skipped": 20}
        empty = {"processed": 0,   "updated": 0,  "skipped": 0}
        result, _, _ = _run_main_with_mocks(
            batch_returns=[full] * 35 + [empty]
        )
        assert result == 0

    def test_main_breaks_early_when_no_isins_left(self) -> None:
        """
        Wenn ein Batch weniger ISINs verarbeitet als angefordert,
        bricht die Schleife früh ab.
        """
        batch_returns = [
            {"processed": 100, "updated": 80, "skipped": 20},
            {"processed": 50,  "updated": 40, "skipped": 10},  # < 100 → Abbruch
        ]
        _, mock_batch, _ = _run_main_with_mocks(batch_returns=batch_returns)
        assert mock_batch.call_count == 2

    def test_stats_aggregated_across_batches(self) -> None:
        """Statistiken aus mehreren Batches werden korrekt summiert."""
        batch_returns = [
            {"processed": 100, "updated": 70, "skipped": 30},
            {"processed": 100, "updated": 60, "skipped": 40},
            {"processed": 50,  "updated": 30, "skipped": 20},  # → Abbruch
        ]
        _, _, mock_email = _run_main_with_mocks(batch_returns=batch_returns)

        call_args = mock_email.call_args
        stats = call_args.kwargs.get("stats") or call_args.args[0]

        assert stats["processed"] == 250
        assert stats["updated"]   == 160
        assert stats["skipped"]   == 90

    def test_send_batch_summary_called_once(self) -> None:
        batch_returns = [
            {"processed": 100, "updated": 80, "skipped": 20},
            {"processed": 0,   "updated": 0,  "skipped": 0},
        ]
        _, _, mock_email = _run_main_with_mocks(batch_returns=batch_returns)
        assert mock_email.call_count == 1

    def test_crossings_passed_to_email(self) -> None:
        """Crossings aus DB werden korrekt an send_batch_summary übergeben."""
        crossings = [{"id": 1, "isin": "US123"}, {"id": 2, "isin": "DE456"}]
        batch_returns = [{"processed": 0, "updated": 0, "skipped": 0}]
        _, _, mock_email = _run_main_with_mocks(
            batch_returns=batch_returns,
            crossings=crossings,
        )
        call_args = mock_email.call_args
        passed = call_args.kwargs.get("crossings") or call_args.args[1]
        assert len(passed) == 2

    def test_update_batch_due_called_with_correct_limit(self) -> None:
        """Jeder Batch-Call nutzt _BATCH_SIZE als limit."""
        from ingestion.auto_dividend_update import _BATCH_SIZE
        batch_returns = [
            {"processed": 100, "updated": 80, "skipped": 20},
            {"processed": 0,   "updated": 0,  "skipped": 0},
        ]
        _, mock_batch, _ = _run_main_with_mocks(batch_returns=batch_returns)

        first_call = mock_batch.call_args_list[0]
        limit = first_call.kwargs.get("limit") or first_call.args[0]
        assert limit == _BATCH_SIZE


# ── Regressionstests ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestMainRegressions:

    def test_no_crash_when_email_fails(self) -> None:
        """E-Mail-Fehler darf main() nicht zum Absturz bringen."""
        with patch("ingestion.auto_dividend_update._setup_logging"), \
             patch("ingestion.auto_dividend_update.update_batch_due",
                   return_value={"processed": 0, "updated": 0, "skipped": 0}), \
             patch("ingestion.auto_dividend_update.send_batch_summary",
                   side_effect=Exception("SMTP down")), \
             patch("ingestion.auto_dividend_update.get_unshown_threshold_crossings",
                   return_value=[]), \
             patch("ingestion.auto_dividend_update._save_run_summary"):
            try:
                main()
            except Exception as e:
                pytest.fail(f"main() ist bei E-Mail-Fehler abgestürzt: {e}")

    def test_no_crash_when_save_summary_fails(self) -> None:
        """DB-Fehler beim Speichern darf nicht abstürzen."""
        with patch("ingestion.auto_dividend_update._setup_logging"), \
             patch("ingestion.auto_dividend_update.update_batch_due",
                   return_value={"processed": 0, "updated": 0, "skipped": 0}), \
             patch("ingestion.auto_dividend_update.send_batch_summary",
                   return_value=True), \
             patch("ingestion.auto_dividend_update.get_unshown_threshold_crossings",
                   return_value=[]), \
             patch("ingestion.auto_dividend_update._save_run_summary",
                   side_effect=Exception("DB locked")):
            try:
                main()
            except Exception as e:
                pytest.fail(
                    f"main() ist bei _save_run_summary-Fehler abgestürzt: {e}"
                )