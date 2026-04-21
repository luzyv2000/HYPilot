# Dateiname:     core/dividend_service.py
# Version:       2026-04-21
# Abhängigkeiten (intern): core.dividend_source, core.ticker_resolver,
#                          core.sources.yfinance_source,
#                          db.dividend_repository
# Abhängigkeiten (extern): keine
"""
core/dividend_service.py

Orchestriert den Dividenden-Datenabruf:
  1. Ticker via ticker_resolver auflösen
  2. Snapshot + Historie via DividendSource abrufen
  3. Ergebnisse via dividend_repository persistieren

Dies ist der einzige Einstiegspunkt für HYPilot-Analyselogik.
GUI und Agent rufen ausschließlich diesen Service auf.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

from core.dividend_source import DividendSnapshot
from core.sources.yfinance_source import YFinanceSource
from core import ticker_resolver
from db import dividend_repository

logger = logging.getLogger(__name__)

# Standardquelle — kann später erweitert werden
_DEFAULT_SOURCE = YFinanceSource()

# Rendite-Schwelle für HYPilot-Kernziel (10 %)
HIGH_YIELD_THRESHOLD = Decimal("0.10")


# ── Einzelabruf ───────────────────────────────────────────────────────────────

def update_dividend_data(
    isin: str,
    db_path: Path = dividend_repository.DB_PATH,
) -> DividendSnapshot | None:
    """
    Aktualisiert Dividendendaten für eine einzelne ISIN.

    Ablauf:
      1. Ticker auflösen
      2. Snapshot + Historie via Quelle abrufen
      3. In DB persistieren

    Returns:
        DividendSnapshot oder None wenn Ticker nicht auflösbar
        oder keine Daten verfügbar.
    """
    logger.info("Starte Dividenden-Update für %s", isin)

    # Schritt 1: Ticker auflösen
    ticker = ticker_resolver.resolve(isin, db_path=db_path)
    if not ticker:
        logger.warning("Kein Ticker für %s — übersprungen.", isin)
        return None

    # Schritt 2: Daten abrufen
    snapshot = _DEFAULT_SOURCE.fetch_snapshot(isin, ticker)
    history = _DEFAULT_SOURCE.fetch_history(isin, ticker)

    if snapshot is None:
        logger.warning("Keine Snapshot-Daten für %s (%s).", isin, ticker)
        return None

    # Schritt 3: Persistieren
    dividend_repository.upsert_snapshot(snapshot, db_path=db_path)
    new_payments = dividend_repository.insert_history(history, db_path=db_path)

    logger.info(
        "Update abgeschlossen: %s → Rendite %s bps, %d neue Zahlungen",
        isin, snapshot.yield_bps, new_payments,
    )
    return snapshot


# ── Batch-Abruf ───────────────────────────────────────────────────────────────

def update_batch(
    limit: int = 50,
    db_path: Path = dividend_repository.DB_PATH,
) -> dict[str, int]:
    """
    Aktualisiert Dividendendaten für ISINs ohne vorhandene Einträge.

    Args:
        limit: Maximale Anzahl ISINs pro Lauf (yfinance ist langsam).

    Returns:
        Dict mit Statistiken: {'processed': N, 'updated': N, 'skipped': N}
    """
    isins = dividend_repository.get_isins_without_dividend_data(
        db_path=db_path, limit=limit
    )

    logger.info("Batch-Update: %d ISINs ohne Dividendendaten.", len(isins))

    stats = {"processed": 0, "updated": 0, "skipped": 0}

    for isin in isins:
        stats["processed"] += 1
        result = update_dividend_data(isin, db_path=db_path)
        if result is not None:
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    logger.info(
        "Batch abgeschlossen: %d verarbeitet, %d aktualisiert, %d übersprungen.",
        stats["processed"], stats["updated"], stats["skipped"],
    )
    return stats


# ── Abfragen ──────────────────────────────────────────────────────────────────

def get_high_yield_instruments(
    min_yield: Decimal = HIGH_YIELD_THRESHOLD,
    db_path: Path = dividend_repository.DB_PATH,
) -> list[DividendSnapshot]:
    """
    Gibt alle Instrumente zurück die den Mindest-Rendite-Schwellwert erfüllen.
    Sortiert nach Rendite absteigend.
    """
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        min_bps = int(min_yield * 10000)
        rows = conn.execute(
            """
            SELECT * FROM dividend_data
            WHERE yield_bps >= ?
            ORDER BY yield_bps DESC
            """,
            (min_bps,),
        ).fetchall()

    from datetime import date as date_type
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