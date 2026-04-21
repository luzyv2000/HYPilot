# Dateiname:     db/dividend_repository.py
# Version:       2026-04-21
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/dividend_repository.py

Datenbankoperationen für dividend_data und dividend_history.
Einzige Stelle im Projekt die direkt auf diese Tabellen schreibt.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from core.dividend_source import DividendPayment, DividendSnapshot

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ── Schreiboperationen ────────────────────────────────────────────────────────

def upsert_snapshot(
    snapshot: DividendSnapshot,
    db_path: Path = DB_PATH,
) -> None:
    """
    Fügt einen DividendSnapshot ein oder aktualisiert ihn.
    Bestehende Einträge für dieselbe ISIN werden überschrieben.
    """
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dividend_data
                (isin, yield_bps, frequency, last_amount_micro,
                 last_ex_date, currency, payout_ratio_bps,
                 data_source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                yield_bps         = excluded.yield_bps,
                frequency         = excluded.frequency,
                last_amount_micro = excluded.last_amount_micro,
                last_ex_date      = excluded.last_ex_date,
                currency          = excluded.currency,
                payout_ratio_bps  = excluded.payout_ratio_bps,
                data_source       = excluded.data_source,
                updated_at        = excluded.updated_at
            """,
            (
                snapshot.isin,
                snapshot.yield_bps,
                snapshot.frequency,
                snapshot.last_amount_micro,
                snapshot.last_ex_date.isoformat() if snapshot.last_ex_date else None,
                snapshot.currency,
                snapshot.payout_ratio_bps,
                snapshot.data_source,
                now,
            ),
        )
        conn.commit()
    logger.debug("Snapshot gespeichert: %s", snapshot.isin)


def insert_history(
    payments: list[DividendPayment],
    db_path: Path = DB_PATH,
) -> int:
    """
    Fügt Dividenden-Einzelzahlungen ein. Duplikate (isin + ex_date)
    werden ignoriert.

    Returns:
        Anzahl neu eingefügter Zahlungen.
    """
    if not payments:
        return 0

    inserted = 0
    with _get_connection(db_path) as conn:
        for payment in payments:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO dividend_history
                    (isin, ex_date, amount_micro, currency, data_source)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    payment.isin,
                    payment.ex_date.isoformat(),
                    payment.amount_micro,
                    payment.currency,
                    payment.data_source,
                ),
            )
            inserted += cursor.rowcount
        conn.commit()

    logger.debug(
        "%d neue Zahlungen eingefügt (%d ignoriert)",
        inserted, len(payments) - inserted,
    )
    return inserted


# ── Leseoperationen ───────────────────────────────────────────────────────────

def get_snapshot(
    isin: str,
    db_path: Path = DB_PATH,
) -> DividendSnapshot | None:
    """Lädt einen DividendSnapshot aus der DB."""
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM dividend_data WHERE isin = ?", (isin,)
        ).fetchone()

    if not row:
        return None

    from datetime import date as date_type
    last_ex = (
        date_type.fromisoformat(row["last_ex_date"])
        if row["last_ex_date"]
        else None
    )

    return DividendSnapshot(
        isin=row["isin"],
        yield_bps=row["yield_bps"],
        frequency=row["frequency"],
        last_amount_micro=row["last_amount_micro"],
        last_ex_date=last_ex,
        currency=row["currency"],
        payout_ratio_bps=row["payout_ratio_bps"],
        data_source=row["data_source"],
    )


def get_isins_without_dividend_data(
    db_path: Path = DB_PATH,
    limit: int = 100,
) -> list[str]:
    """
    Gibt ISINs zurück die noch keinen Eintrag in dividend_data haben.
    Nützlich für Batch-Importe.
    """
    with _get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT i.isin FROM instruments i
            LEFT JOIN dividend_data d ON i.isin = d.isin
            WHERE d.isin IS NULL
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [row["isin"] for row in rows]