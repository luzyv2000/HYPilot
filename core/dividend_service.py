# Dateiname:     core/dividend_service.py
# Version:       2026-04-23-P3pp
# Abhängigkeiten (intern): core.dividend_source, core.ticker_resolver,
#                          core.sources.yfinance_source,
#                          db.dividend_repository
# Abhängigkeiten (extern): keine
"""
core/dividend_service.py

Orchestriert den Dividenden-Datenabruf.

P3++-Erweiterungen:
  - update_batch_due(): holt nur ISINs die seit >6h nicht aktualisiert wurden
  - 18-Monats-Regel: kein Zahlungseingang → yield=0, 7 Tage Pause
  - Schwellwert-Tracking: Überschreitung der 10%-Grenze wird protokolliert
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Callable

from core.dividend_source import DividendSnapshot
from core.sources.yfinance_source import YFinanceSource
from core import ticker_resolver
from db import dividend_repository

logger = logging.getLogger(__name__)

_DEFAULT_SOURCE = YFinanceSource()

HIGH_YIELD_THRESHOLD    = Decimal("0.10")
_HIGH_YIELD_BPS         = 1000   # 10 % in bps
_BATCH_PAUSE_SECONDS    = 2.0    # Pause zwischen Batches à 100

ProgressCallback = Callable[[int, int, str, str], None]


# ── Schwellwert-Erkennung ─────────────────────────────────────────────────────

def _check_threshold_crossing(
    isin: str,
    old_bps: int | None,
    new_bps: int | None,
    db_path: Path,
) -> None:
    """
    Prüft ob die 10%-Grenze überschritten wurde und protokolliert.
    Erkennt Übergänge in beide Richtungen.
    """
    if new_bps is None:
        return

    was_above = old_bps is not None and old_bps >= _HIGH_YIELD_BPS
    is_above  = new_bps >= _HIGH_YIELD_BPS

    if not was_above and is_above:
        # Neu über 10%
        dividend_repository.record_threshold_crossing(
            isin=isin,
            yield_bps_old=old_bps,
            yield_bps_new=new_bps,
            direction="up",
            db_path=db_path,
        )
    elif was_above and not is_above:
        # Neu unter 10%
        dividend_repository.record_threshold_crossing(
            isin=isin,
            yield_bps_old=old_bps,
            yield_bps_new=new_bps,
            direction="down",
            db_path=db_path,
        )


# ── Einzelabruf ───────────────────────────────────────────────────────────────

def update_dividend_data(
    isin: str,
    db_path: Path = dividend_repository.DB_PATH,
) -> DividendSnapshot | None:
    """
    Aktualisiert Dividendendaten für eine ISIN.
    Wendet 18-Monats-Regel und Schwellwert-Tracking an.
    """
    logger.info("Dividenden-Update: %s", isin)

    ticker = ticker_resolver.resolve(isin, db_path=db_path)
    if not ticker:
        logger.warning("Kein Ticker für %s — übersprungen.", isin)
        return None

    # Vorherigen Wert für Schwellwert-Vergleich merken
    old_snapshot = dividend_repository.get_snapshot(isin, db_path=db_path)
    old_bps      = old_snapshot.yield_bps if old_snapshot else None

    snapshot = _DEFAULT_SOURCE.fetch_snapshot(isin, ticker)
    history  = _DEFAULT_SOURCE.fetch_history(isin, ticker)

    if snapshot is None:
        logger.warning("Kein Snapshot für %s (%s).", isin, ticker)
        return None

    # ── 18-Monats-Regel ───────────────────────────────────────────────────────
    if not dividend_repository.has_recent_dividends(isin, months=18,
                                                     db_path=db_path):
        # Auch Zahlungen aus aktuellem Fetch berücksichtigen
        if not history:
            logger.info(
                "%s: keine Dividende in 18 Monaten → yield=0, "
                "Abruf pausiert für 7 Tage.", isin,
            )
            dividend_repository.set_skip_until(isin, db_path=db_path)
            return None

    # ── Snapshot speichern ────────────────────────────────────────────────────
    dividend_repository.upsert_snapshot(snapshot, db_path=db_path)
    new_payments = dividend_repository.insert_history(history, db_path=db_path)

    # ── Schwellwert-Tracking ──────────────────────────────────────────────────
    _check_threshold_crossing(
        isin=isin,
        old_bps=old_bps,
        new_bps=snapshot.yield_bps,
        db_path=db_path,
    )

    logger.info(
        "Update: %s → %s bps, %d neue Zahlungen",
        isin, snapshot.yield_bps, new_payments,
    )
    return snapshot


# ── Batch: manuell (aus GUI) ──────────────────────────────────────────────────

def update_batch(
    limit: int = 100,
    db_path: Path = dividend_repository.DB_PATH,
    progress_callback: ProgressCallback | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """
    Manueller Batch aus der GUI — ISINs ohne vorhandene Daten.
    """
    isins = dividend_repository.get_isins_without_dividend_data(
        db_path=db_path, limit=limit
    )
    return _run_batch(
        isins=isins,
        db_path=db_path,
        progress_callback=progress_callback,
        stop_flag=stop_flag,
    )


# ── Batch: automatisch (systemd) ─────────────────────────────────────────────

def update_batch_due(
    limit: int = 100,
    db_path: Path = dividend_repository.DB_PATH,
    progress_callback: ProgressCallback | None = None,
    stop_flag: Callable[[], bool] | None = None,
    batch_pause: float = _BATCH_PAUSE_SECONDS,
) -> dict[str, int]:
    """
    Automatischer Batch — nur ISINs die seit >6h nicht aktualisiert wurden
    und deren skip_until abgelaufen ist.

    Wird von ingestion/auto_dividend_update.py aufgerufen.
    """
    isins = dividend_repository.get_isins_due_for_update(
        db_path=db_path, limit=limit
    )
    logger.info(
        "Auto-Batch: %d ISINs fällig für Update.", len(isins)
    )
    result = _run_batch(
        isins=isins,
        db_path=db_path,
        progress_callback=progress_callback,
        stop_flag=stop_flag,
    )
    if batch_pause > 0:
        time.sleep(batch_pause)
    return result


# ── Interne Batch-Logik ───────────────────────────────────────────────────────

def _run_batch(
    isins: list[str],
    db_path: Path,
    progress_callback: ProgressCallback | None,
    stop_flag: Callable[[], bool] | None,
) -> dict[str, int]:
    total  = len(isins)
    stats  = {"processed": 0, "updated": 0, "skipped": 0}

    for isin in isins:
        if stop_flag and stop_flag():
            logger.info("Batch abgebrochen.")
            break

        stats["processed"] += 1

        if progress_callback:
            progress_callback(stats["processed"], total, isin, "wird abgefragt …")

        result = update_dividend_data(isin, db_path=db_path)

        if result is not None:
            stats["updated"] += 1
            status = f"✓ {result.yield_bps} bps" if result.yield_bps else "✓"
        else:
            stats["skipped"] += 1
            status = "übersprungen"

        if progress_callback:
            progress_callback(stats["processed"], total, isin, status)

    logger.info(
        "Batch: %d verarbeitet, %d aktualisiert, %d übersprungen.",
        stats["processed"], stats["updated"], stats["skipped"],
    )
    return stats


# ── Abfragen ──────────────────────────────────────────────────────────────────

def get_high_yield_instruments(
    min_yield: Decimal = HIGH_YIELD_THRESHOLD,
    db_path: Path = dividend_repository.DB_PATH,
) -> list[DividendSnapshot]:
    import sqlite3
    from datetime import date as date_type
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        min_bps = int(min_yield * 10000)
        rows = conn.execute(
            "SELECT * FROM dividend_data WHERE yield_bps >= ? "
            "ORDER BY yield_bps DESC",
            (min_bps,),
        ).fetchall()
    result = []
    for row in rows:
        last_ex = (
            date_type.fromisoformat(row["last_ex_date"])
            if row["last_ex_date"] else None
        )
        result.append(DividendSnapshot(
            isin=row["isin"],
            yield_bps=row["yield_bps"],
            frequency=row["frequency"],
            last_amount_micro=row["last_amount_micro"],
            last_ex_date=last_ex,
            currency=row["currency"],
            payout_ratio_bps=row["payout_ratio_bps"],
            data_source=row["data_source"],
        ))
    return result
