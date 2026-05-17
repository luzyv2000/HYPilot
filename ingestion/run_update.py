# Dateiname:     ingestion/run_update.py
# Version:       2026-04-20
# Abhängigkeiten (intern): ingestion.downloader, ingestion.updater
# Abhängigkeiten (extern): keine
"""
ingestion/run_update.py

Orchestriert die vollständige Update-Pipeline:
  1. PDF-Download prüfen / herunterladen
  2. Neue Instrumente in SQLite importieren

Wird täglich via systemd-Timer oder Cron aufgerufen.
Direkte Python-Aufrufe statt subprocess — kein venv-Pfadproblem.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from ingestion import downloader, updater

# ── Logging-Konfiguration ─────────────────────────────────────────────────────

LOG_DIR: Path = Path("/home/luzy/workspace/openclaw-min/logs")
LOG_FILE: Path = LOG_DIR / "update.log"


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"

    # Konsole
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    # Datei (append)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(fmt, datefmt=datefmt))

    logging.basicConfig(
        level=logging.INFO,
        handlers=[console_handler, file_handler],
    )


logger = logging.getLogger(__name__)


# ── Pipeline ──────────────────────────────────────────────────────────────────

def run_pipeline() -> bool:
    """
    Führt die vollständige Update-Pipeline aus.

    Returns:
        True bei Erfolg, False bei kritischem Fehler.
    """
    logger.info("=" * 60)
    logger.info("START UPDATE-PIPELINE")
    logger.info("=" * 60)

    # ── Schritt 1: PDF-Download ───────────────────────────────────────────────
    logger.info("Schritt 1/2: PDF-Download")
    try:
        pdf_ok = downloader.run()
    except Exception:
        logger.exception("Unerwarteter Fehler im Downloader.")
        pdf_ok = False

    if not pdf_ok:
        logger.critical(
            "PDF nicht verfügbar — Pipeline wird abgebrochen. "
            "Kein Update möglich."
        )
        return False

    # ── Schritt 2: DB-Update ─────────────────────────────────────────────────
    logger.info("Schritt 2/2: Datenbank-Update")
    try:
        new_count = updater.run()
        logger.info("Neue Instrumente importiert: %d", new_count)
    except Exception:
        logger.exception("Unerwarteter Fehler im Updater.")
        return False

    logger.info("=" * 60)
    logger.info("UPDATE-PIPELINE ABGESCHLOSSEN")
    logger.info("=" * 60)
    return True


# ── CLI-Einstiegspunkt ────────────────────────────────────────────────────────

if __name__ == "__main__":
    _setup_logging()
    success = run_pipeline()
    sys.exit(0 if success else 1)