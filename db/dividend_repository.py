# Dateiname:     db/dividend_repository.py
# Version:       2026-04-25
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): python-dateutil
"""
db/dividend_repository.py

Datenbankoperationen für dividend_data, dividend_history
und threshold_crossings.

Einzige Stelle im Projekt die direkt auf diese Tabellen schreibt.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from dateutil.relativedelta import relativedelta

from core.dividend_source import DividendPayment, DividendSnapshot

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# Schwellwert für HYPilot-Kernziel
_HIGH_YIELD_BPS: int = 1000          # 10 %

# Nach 18 Monaten ohne Dividende → skip für 7 Tage
_NO_DIV_MONTHS:  int = 18
_SKIP_DAYS:      int = 7

# Nur ISINs aktualisieren die älter als 6 Stunden sind
_UPDATE_INTERVAL_HOURS: int = 6


# ── Verbindung ────────────────────────────────────────────────────────────────

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
    Fügt Snapshot ein oder aktualisiert ihn.
    Speichert alten yield_bps in yield_bps_prev vor dem Überschreiben.
    """
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dividend_data
                (isin, yield_bps, yield_bps_prev, frequency,
                 last_amount_micro, last_ex_date, currency,
                 payout_ratio_bps, data_source, updated_at)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                yield_bps_prev    = dividend_data.yield_bps,
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


def set_skip_until(
    isin: str,
    skip_days: int = _SKIP_DAYS,
    db_path: Path = DB_PATH,
) -> None:
    """Setzt skip_until auf heute + skip_days (18-Monats-Regel)."""
    skip_date = (date.today() + timedelta(days=skip_days)).isoformat()
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dividend_data
                (isin, yield_bps, skip_until, data_source, updated_at)
            VALUES (?, 0, ?, 'yfinance', ?)
            ON CONFLICT(isin) DO UPDATE SET
                yield_bps  = 0,
                skip_until = excluded.skip_until,
                updated_at = excluded.updated_at
            """,
            (isin, skip_date, now),
        )
        conn.commit()
    logger.info(
        "ISIN %s: 0-Dividende gesetzt, Abruf pausiert bis %s.",
        isin, skip_date,
    )


def record_threshold_crossing(
    isin: str,
    yield_bps_old: int | None,
    yield_bps_new: int,
    direction: str,
    db_path: Path = DB_PATH,
) -> None:
    """Speichert eine 10 %-Schwellwert-Überschreitung."""
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO threshold_crossings
                (isin, yield_bps_old, yield_bps_new, direction, detected_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (isin, yield_bps_old, yield_bps_new,
             direction, datetime.now().isoformat()),
        )
        conn.commit()
    logger.info(
        "Schwellwert-Überschreitung: %s %s (alt: %s bps → neu: %s bps)",
        isin, direction, yield_bps_old, yield_bps_new,
    )


def mark_crossings_shown(
    crossing_ids: list[int],
    db_path: Path = DB_PATH,
) -> None:
    """Markiert Überschreitungen als im GUI angezeigt."""
    if not crossing_ids:
        return
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.executemany(
            "UPDATE threshold_crossings SET shown_at = ? WHERE id = ?",
            [(now, cid) for cid in crossing_ids],
        )
        conn.commit()


def insert_history(
    payments: list[DividendPayment],
    db_path: Path = DB_PATH,
) -> int:
    """
    Fügt Dividenden-Einzelzahlungen ein. Duplikate (isin + ex_date) werden
    ignoriert.

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
        "%d neue Zahlungen eingefügt (%d ignoriert).",
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

    last_ex = (
        date.fromisoformat(row["last_ex_date"])
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


def get_isins_due_for_update(
    db_path: Path = DB_PATH,
    limit: int = 100,
    interval_hours: int = _UPDATE_INTERVAL_HOURS,
) -> list[str]:
    """
    Gibt ISINs zurück die für ein Update fällig sind:
      - Noch nie aktualisiert ODER updated_at älter als interval_hours
      - UND skip_until ist NULL oder bereits vergangen

    Reihenfolge: ISIN-Länderpräfix-Priorität zuerst.
    US/CA-ISINs haben beste yfinance-Abdeckung → zuerst verarbeiten.
    Verhindert dass der erste Batch ausschließlich aus AU/AT-Kleinsttiteln
    besteht.

    Prioritätsstufen (CASE WHEN):
      1  → US, CA        (beste Abdeckung)
      2  → DE, GB, FR,
           CH, NL, SE,
           DK, FI, NO   (gute europäische Abdeckung)
      3  → alle anderen  (unsichere Abdeckung)
    """
    cutoff = (
        datetime.now() - timedelta(hours=interval_hours)
    ).isoformat()
    today = date.today().isoformat()

    with _get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT i.isin
            FROM instruments i
            LEFT JOIN dividend_data d ON i.isin = d.isin
            WHERE
                (d.isin IS NULL OR d.updated_at < ?)
                AND (d.skip_until IS NULL OR d.skip_until <= ?)
            ORDER BY
                CASE SUBSTR(i.isin, 1, 2)
                    WHEN 'US' THEN 1
                    WHEN 'CA' THEN 1
                    WHEN 'DE' THEN 2
                    WHEN 'GB' THEN 2
                    WHEN 'FR' THEN 2
                    WHEN 'CH' THEN 2
                    WHEN 'NL' THEN 2
                    WHEN 'SE' THEN 2
                    WHEN 'DK' THEN 2
                    WHEN 'FI' THEN 2
                    WHEN 'NO' THEN 2
                    ELSE 3
                END ASC,
                d.updated_at ASC NULLS FIRST
            LIMIT ?
            """,
            (cutoff, today, limit),
        ).fetchall()
    return [row["isin"] for row in rows]

def get_isins_without_dividend_data(
    db_path: Path = DB_PATH,
    limit: int = 100,
) -> list[str]:
    """Gibt ISINs ohne jegliche Dividendendaten zurück (für manuellen Batch)."""
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


def get_unshown_threshold_crossings(
    db_path: Path = DB_PATH,
) -> list[dict]:
    """Gibt noch nicht angezeigte Schwellwert-Überschreitungen zurück."""
    with _get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT tc.id, tc.isin, tc.yield_bps_old, tc.yield_bps_new,
                   tc.direction, tc.detected_at,
                   COALESCE(i.name_override, i.name) AS display_name
            FROM threshold_crossings tc
            JOIN instruments i ON i.isin = tc.isin
            WHERE tc.shown_at IS NULL
            ORDER BY tc.direction DESC, tc.yield_bps_new DESC
            """,
        ).fetchall()
    return [dict(row) for row in rows]


def has_recent_dividends(
    isin: str,
    months: int = _NO_DIV_MONTHS,
    db_path: Path = DB_PATH,
) -> bool:
    """
    Prüft ob in den letzten `months` Monaten eine Dividende geflossen ist.
    Basis: dividend_history.

    Verwendet dateutil.relativedelta für präzise Monatsberechnung
    (verhindert Fehler bei Monaten unterschiedlicher Länge).
    """
    cutoff = (date.today() - relativedelta(months=months)).isoformat()

    with _get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM dividend_history
            WHERE isin = ? AND ex_date >= ?
            """,
            (isin, cutoff),
        ).fetchone()
    return (row["cnt"] if row else 0) > 0
