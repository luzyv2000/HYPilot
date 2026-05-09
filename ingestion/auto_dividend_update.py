# Dateiname:     ingestion/auto_dividend_update.py
# Version:       2026-05-09-fix1
# Abhängigkeiten (intern): core.dividend_service, core.email_service,
#                          db.dividend_repository
# Abhängigkeiten (extern): keine
"""
ingestion/auto_dividend_update.py

Einstiegspunkt für den automatischen Dividenden-Abruf (systemd).

Ablauf:
  1. Alle ISINs die seit >6h nicht aktualisiert wurden in Batches à 100
  2. Pause zwischen Batches
  3. Schwellwert-Überschreitungen aus DB lesen
  4. Zusammenfassung via E-Mail senden
  5. Ergebnis in metadata speichern (GUI liest beim nächsten Start)

Wird gestartet von:
  systemd/hypilot-dividends.timer (08:00 + 13:00)

Kapazitätsplanung:
  _TOTAL_PER_RUN = 3500 → ~117 Min pro Lauf bei ~2s/ISIN
  2 Läufe/Tag × 3500 = 7000 ISINs → deckt gesamtes fälliges Universum ab

Fehlerbehandlung:
  send_batch_summary und _save_run_summary werden in try/except gekapselt —
  ein E-Mail- oder DB-Fehler darf den Daemon nicht zum Absturz bringen.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

_PROJECT = Path(__file__).parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from core.dividend_service import update_batch_due
from core.email_service import send_batch_summary
from db.dividend_repository import (
    DB_PATH,
    get_unshown_threshold_crossings,
)

LOG_DIR  = Path("/home/luzy/workspace/openclaw-min/logs")
LOG_FILE = LOG_DIR / "auto_dividend.log"

_TOTAL_PER_RUN = 3500
_BATCH_SIZE    = 100


def _setup_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt     = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


def _save_run_summary(stats: dict, crossings: list[dict]) -> None:
    """Speichert Zusammenfassung in metadata für GUI-Anzeige beim Start."""
    import sqlite3
    summary = {
        "run_at":    datetime.now().isoformat(),
        "stats":     stats,
        "crossings": len(crossings),
    }
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                "INSERT INTO metadata (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                ("last_auto_run", json.dumps(summary)),
            )
            conn.commit()
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "Konnte Run-Summary nicht speichern: %s", exc
        )


def main() -> int:
    _setup_logging()
    logger = logging.getLogger(__name__)

    run_label = f"Auto-Lauf {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    logger.info("=" * 60)
    logger.info("START: %s", run_label)
    logger.info("=" * 60)

    total_stats = {"processed": 0, "updated": 0, "skipped": 0}
    processed   = 0

    while processed < _TOTAL_PER_RUN:
        remaining = min(_BATCH_SIZE, _TOTAL_PER_RUN - processed)
        stats = update_batch_due(
            limit=remaining,
            batch_pause=2.0,
        )

        for key in total_stats:
            total_stats[key] += stats.get(key, 0)

        processed += stats["processed"]

        if stats["processed"] < remaining:
            logger.info(
                "Keine weiteren fälligen ISINs nach %d verarbeiteten.",
                processed,
            )
            break

    logger.info(
        "Gesamt: %d verarbeitet, %d aktualisiert, %d übersprungen.",
        total_stats["processed"],
        total_stats["updated"],
        total_stats["skipped"],
    )

    # Schwellwert-Überschreitungen
    crossings = get_unshown_threshold_crossings()
    logger.info("%d neue Schwellwert-Überschreitungen.", len(crossings))

    # E-Mail — Fehler darf Daemon nicht beenden
    try:
        send_batch_summary(
            stats=total_stats,
            crossings=crossings,
            run_label=run_label,
        )
    except Exception as exc:
        logger.error("E-Mail-Versand fehlgeschlagen: %s", exc)

    # In metadata speichern — Fehler darf Daemon nicht beenden
    try:
        _save_run_summary(total_stats, crossings)
    except Exception as exc:
        logger.error("Run-Summary konnte nicht gespeichert werden: %s", exc)

    logger.info("=" * 60)
    logger.info("ENDE: %s", run_label)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())