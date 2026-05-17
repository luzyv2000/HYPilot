# Dateiname:     ingestion/auto_dividend_update.py
# Version:       2026-05-15-quality-fix1
# Abhängigkeiten (intern): core.dividend_service, core.email_service,
#                          core.data_quality, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
ingestion/auto_dividend_update.py

Einstiegspunkt für den automatischen Dividenden-Abruf (systemd).
Fix 2026-05-16: noqa E402 für sys.path-Manipulation (bewusst, kein Fehler).
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

from core.dividend_service import update_batch_due  # noqa: E402
from core.email_service    import send_batch_summary  # noqa: E402
from core.data_quality     import run_quality_check, save_report  # noqa: E402
from db.dividend_repository import (  # noqa: E402
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
        stats = update_batch_due(limit=remaining, batch_pause=2.0)

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
        total_stats["processed"], total_stats["updated"], total_stats["skipped"],
    )

    crossings = get_unshown_threshold_crossings()
    logger.info("%d neue Schwellwert-Überschreitungen.", len(crossings))

    try:
        send_batch_summary(stats=total_stats, crossings=crossings, run_label=run_label)
    except Exception as exc:
        logger.error("E-Mail-Versand fehlgeschlagen: %s", exc)

    try:
        _save_run_summary(total_stats, crossings)
    except Exception as exc:
        logger.error("Run-Summary konnte nicht gespeichert werden: %s", exc)

    try:
        report = run_quality_check(db_path=DB_PATH)
        save_report(report, db_path=DB_PATH)
        logger.info(
            "Qualitätsbericht: Abdeckung %.1f %%, Ausreißer %d, Warnungen %d.",
            report.coverage_pct, report.outliers_above_cap, len(report.warnings),
        )
    except Exception as exc:
        logger.error("Datenqualitäts-Check fehlgeschlagen: %s", exc)

    logger.info("=" * 60)
    logger.info("ENDE: %s", run_label)
    logger.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
