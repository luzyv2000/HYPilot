# Dateiname:     core/dividend_service.py
# Version:       2026-05-08-cascade
# Abhängigkeiten (intern): core.dividend_source, core.ticker_resolver,
#                          core.sources.divvydiary_source,
#                          core.sources.boerse_frankfurt_source,
#                          core.sources.yfinance_source,
#                          db.dividend_repository
# Abhängigkeiten (extern): keine
"""
core/dividend_service.py

Orchestriert den Dividenden-Datenabruf via Multi-Source-Kaskade.

Kaskaden-Reihenfolge (sequenziell, erste Non-None-Antwort gewinnt):
  1. DivvyDiary REST-API    — beste Qualität EU-Titel, benötigt API-Key
  2. Boerse Frankfurt Feed  — gut für Xetra-Titel (DE/AT/CH/FR/NL)
  3. yfinance               — breite Abdeckung, Fallback

Quelle wird in dividend_data.data_source protokolliert.

Bestehende Logik unverändert:
  - 18-Monats-Regel (skip_until)
  - Schwellwert-Tracking (10%-Grenze)
  - Batch-Verarbeitung (update_batch / update_batch_due)
"""

from __future__ import annotations

import logging
import time
from decimal import Decimal
from pathlib import Path
from typing import Callable

from core.dividend_source import DividendSnapshot
from core.sources.divvydiary_source import DivvyDiarySource
from core.sources.boerse_frankfurt_source import BoerseFrankfurtSource
from core.sources.yfinance_source import YFinanceSource
from core import ticker_resolver
from db import dividend_repository

logger = logging.getLogger(__name__)

# Quellen-Singletons — einmal instanziiert beim Modul-Import
_DIVVYDIARY        = DivvyDiarySource()
_BOERSE_FRANKFURT  = BoerseFrankfurtSource()
_YFINANCE          = YFinanceSource()

HIGH_YIELD_THRESHOLD = Decimal("0.10")
_HIGH_YIELD_BPS      = 1000
_BATCH_PAUSE_SECONDS = 2.0

ProgressCallback = Callable[[int, int, str, str], None]


# ── Kaskaden-Orchestrator ─────────────────────────────────────────────────────

def _cascade_fetch_snapshot(
    isin: str,
    ticker: str | None,
    db_path: Path,
) -> DividendSnapshot | None:
    """
    Versucht Dividenden-Snapshot sequenziell über alle konfigurierten Quellen.
    Erste Non-None-Antwort gewinnt. Alle Quellen werden bei Fehler still
    übersprungen — kein harter Abbruch.

    Args:
        isin:    ISIN des Instruments
        ticker:  Aufgelöster Ticker (wird nur von yfinance benötigt)
        db_path: Pfad zur SQLite-DB

    Returns:
        DividendSnapshot der ersten erfolgreichen Quelle, oder None.
    """
    sources = [
        (_DIVVYDIARY,       isin,   ""),            # ISIN-nativ
        (_BOERSE_FRANKFURT, isin,   ""),            # ISIN-nativ
        (_YFINANCE,         isin,   ticker or ""),  # Ticker benötigt
    ]

    for source, src_isin, src_ticker in sources:
        # yfinance überspringen wenn kein Ticker aufgelöst wurde
        if source is _YFINANCE and not src_ticker:
            logger.debug(
                "Kaskade: yfinance für %s übersprungen — kein Ticker.", isin
            )
            continue

        try:
            snapshot = source.fetch_snapshot(src_isin, src_ticker)
            if snapshot is not None:
                logger.info(
                    "Kaskade: %s → Quelle '%s' erfolgreich.",
                    isin, source.source_name,
                )
                return snapshot
            logger.debug(
                "Kaskade: %s → '%s' kein Ergebnis.",
                isin, source.source_name,
            )
        except Exception:
            logger.debug(
                "Kaskade: %s → '%s' fehlgeschlagen (Exception).",
                isin, source.source_name,
            )
            continue

    logger.debug("Kaskade: %s → alle Quellen erschöpft.", isin)
    return None


def _cascade_fetch_history(
    isin: str,
    ticker: str | None,
) -> list:
    """
    Holt Dividenden-Historie aus der ersten erfolgreichen Quelle.
    Reihenfolge identisch zur Snapshot-Kaskade.
    """
    sources = [
        (_DIVVYDIARY,       isin,   ""),
        (_BOERSE_FRANKFURT, isin,   ""),
        (_YFINANCE,         isin,   ticker or ""),
    ]

    for source, src_isin, src_ticker in sources:
        if source is _YFINANCE and not src_ticker:
            continue
        try:
            history = source.fetch_history(src_isin, src_ticker)
            if history:
                logger.debug(
                    "Kaskade Historie: %s → '%s' (%d Einträge).",
                    isin, source.source_name, len(history),
                )
                return history
        except Exception:
            continue

    return []


# ── Schwellwert-Erkennung ─────────────────────────────────────────────────────

def _check_threshold_crossing(
    isin: str,
    old_bps: int | None,
    new_bps: int | None,
    db_path: Path,
) -> None:
    if new_bps is None:
        return

    was_above = old_bps is not None and old_bps >= _HIGH_YIELD_BPS
    is_above  = new_bps >= _HIGH_YIELD_BPS

    if not was_above and is_above:
        dividend_repository.record_threshold_crossing(
            isin=isin, yield_bps_old=old_bps,
            yield_bps_new=new_bps, direction="up", db_path=db_path,
        )
    elif was_above and not is_above:
        dividend_repository.record_threshold_crossing(
            isin=isin, yield_bps_old=old_bps,
            yield_bps_new=new_bps, direction="down", db_path=db_path,
        )


# ── Einzelabruf ───────────────────────────────────────────────────────────────

def update_dividend_data(
    isin: str,
    db_path: Path = dividend_repository.DB_PATH,
) -> DividendSnapshot | None:
    """
    Aktualisiert Dividendendaten für eine ISIN via Multi-Source-Kaskade.
    Wendet 18-Monats-Regel und Schwellwert-Tracking an.
    """
    logger.info("Dividenden-Update: %s", isin)

    # Ticker für yfinance auflösen (wird von ISIN-nativen Quellen ignoriert)
    ticker = ticker_resolver.resolve(isin, db_path=db_path)

    # Vorherigen Wert für Schwellwert-Vergleich merken
    old_snapshot = dividend_repository.get_snapshot(isin, db_path=db_path)
    old_bps      = old_snapshot.yield_bps if old_snapshot else None

    # Kaskade: Snapshot
    snapshot = _cascade_fetch_snapshot(isin, ticker, db_path)

    # Kaskade: Historie (für 18-Monats-Regel)
    history = _cascade_fetch_history(isin, ticker)

    if snapshot is None:
        logger.warning("Kein Snapshot für %s aus keiner Quelle.", isin)
        return None

    # ── 18-Monats-Regel ───────────────────────────────────────────────────────
    if not dividend_repository.has_recent_dividends(
        isin, months=18, db_path=db_path
    ):
        if not history:
            logger.info(
                "%s: keine Dividende in 18 Monaten → yield=0, "
                "Abruf pausiert für 7 Tage.", isin,
            )
            dividend_repository.set_skip_until(isin, db_path=db_path)
            return None

    # ── Speichern ─────────────────────────────────────────────────────────────
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
        "Update: %s → %s bps [%s], %d neue Zahlungen",
        isin, snapshot.yield_bps, snapshot.data_source, new_payments,
    )
    return snapshot


# ── Batch-Verarbeitung ────────────────────────────────────────────────────────

def update_batch(
    limit: int = 100,
    db_path: Path = dividend_repository.DB_PATH,
    progress_callback: ProgressCallback | None = None,
    stop_flag: Callable[[], bool] | None = None,
) -> dict[str, int]:
    """Manueller Batch aus der GUI — ISINs ohne vorhandene Daten."""
    isins = dividend_repository.get_isins_without_dividend_data(
        db_path=db_path, limit=limit
    )
    return _run_batch(
        isins=isins,
        db_path=db_path,
        progress_callback=progress_callback,
        stop_flag=stop_flag,
    )


def update_batch_due(
    limit: int = 100,
    db_path: Path = dividend_repository.DB_PATH,
    progress_callback: ProgressCallback | None = None,
    stop_flag: Callable[[], bool] | None = None,
    batch_pause: float = _BATCH_PAUSE_SECONDS,
) -> dict[str, int]:
    """Automatischer Batch — nur ISINs die seit >6h nicht aktualisiert wurden."""
    isins = dividend_repository.get_isins_due_for_update(
        db_path=db_path, limit=limit
    )
    logger.info("Auto-Batch: %d ISINs fällig für Update.", len(isins))
    result = _run_batch(
        isins=isins,
        db_path=db_path,
        progress_callback=progress_callback,
        stop_flag=stop_flag,
    )
    if batch_pause > 0:
        time.sleep(batch_pause)
    return result


def _run_batch(
    isins: list[str],
    db_path: Path,
    progress_callback: ProgressCallback | None,
    stop_flag: Callable[[], bool] | None,
) -> dict[str, int]:
    total = len(isins)
    stats = {"processed": 0, "updated": 0, "skipped": 0}

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
            status = f"✓ {result.yield_bps} bps [{result.data_source}]"
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