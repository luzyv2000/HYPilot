# Dateiname:     db/dividend_repository.py
# Version:       2026-05-16-freq
# Abhängigkeiten (intern): core.dividend_source
# Abhängigkeiten (extern): python-dateutil
"""
db/dividend_repository.py

Datenbankoperationen für dividend_data, dividend_history,
threshold_crossings und Wachstumsmetriken.

Neu 2026-05-16:
  get_unshown_threshold_crossings() liefert jetzt auch das
  frequency-Feld aus dividend_data — wird für E-Mail-Spalte genutzt.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from dateutil.relativedelta import relativedelta

from core.dividend_source import DividendPayment, DividendSnapshot

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_HIGH_YIELD_BPS: int = 1000
_NO_DIV_MONTHS:  int = 18
_SKIP_DAYS:      int = 7
_UPDATE_INTERVAL_HOURS: int = 6

# Wachstumsanalyse: Vergleich über bis zu 4 Jahre
_GROWTH_HISTORY_YEARS: int = 4


# ── Wachstumsmetriken ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GrowthMetrics:
    """
    Dividenden-Wachstumsmetriken aus dividend_history.

    Felder:
      years_of_data : Anzahl vollständiger Kalenderjahre mit Zahlungen
                      (aktuelles Jahr wird für Konsistenz ausgeschlossen)
      yoy_growth    : YoY-Wachstumsrate als Decimal (0.05 = 5%).
                      None wenn weniger als 2 Jahres-Datenpunkte vorhanden.
      has_cut       : True wenn in einem vollständigen Jahr die
                      Gesamtdividende gegenüber dem Vorjahr gesunken ist.
    """
    years_of_data: int
    yoy_growth:    Decimal | None
    has_cut:       bool


def _compute_growth_metrics(
    year_data: list[tuple[str, int]],
) -> GrowthMetrics:
    """
    Berechnet GrowthMetrics aus einer sortierten Liste von (Jahr, Betrag).

    Args:
        year_data: [(year_str, total_amount_micro), ...] aufsteigend sortiert.
                   Enthält NUR vollständige Kalenderjahre (aktuelles Jahr
                   bereits herausgefiltert).

    Returns:
        GrowthMetrics-Instanz.
    """
    if not year_data:
        return GrowthMetrics(years_of_data=0, yoy_growth=None, has_cut=False)

    totals = [total for _, total in year_data]
    years_of_data = len(totals)

    # YoY-Wachstum: letztes vollständiges Jahr vs. vorletztes
    yoy_growth: Decimal | None = None
    if years_of_data >= 2 and totals[-2] > 0:
        yoy_growth = (
            Decimal(str(totals[-1] - totals[-2]))
            / Decimal(str(totals[-2]))
        )

    # Kürzungserkennung: jedes Jahr wo Gesamtbetrag < Vorjahr
    has_cut = any(
        totals[i] < totals[i - 1]
        for i in range(1, len(totals))
    )

    return GrowthMetrics(
        years_of_data=years_of_data,
        yoy_growth=yoy_growth,
        has_cut=has_cut,
    )


def get_growth_metrics_bulk(
    db_path: Path = DB_PATH,
) -> dict[str, GrowthMetrics]:
    """
    Berechnet Wachstumsmetriken für alle ISINs in einem einzigen DB-Abruf.
    Geeignet für Tabellen-Rendering (einmal aufrufen, dict weitergeben).

    Strategie:
      - Jahressummen der letzten _GROWTH_HISTORY_YEARS Jahre via SQL
      - Aktuelles Kalenderjahr ausgeschlossen (unvollständige Daten)
      - Python-seitige Aggregation pro ISIN

    Returns:
        {isin: GrowthMetrics} für alle ISINs mit Historiedaten.
        ISINs ohne Historie fehlen im Dict.
    """
    current_year = str(date.today().year)

    query = """
        SELECT
            isin,
            strftime('%Y', ex_date) AS yr,
            SUM(amount_micro)       AS total
        FROM dividend_history
        WHERE
            ex_date >= date('now', :neg_years)
            AND strftime('%Y', ex_date) < :current_year
        GROUP BY isin, yr
        ORDER BY isin ASC, yr ASC
    """

    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(query, {
                "neg_years":    f"-{_GROWTH_HISTORY_YEARS} years",
                "current_year": current_year,
            }).fetchall()
    except sqlite3.Error:
        logger.exception("Fehler beim Laden der Wachstumsmetriken (bulk).")
        return {}

    # Gruppierung nach ISIN
    by_isin: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in rows:
        by_isin[row["isin"]].append((row["yr"], row["total"]))

    return {
        isin: _compute_growth_metrics(year_data)
        for isin, year_data in by_isin.items()
    }


def get_growth_metrics(
    isin: str,
    db_path: Path = DB_PATH,
) -> GrowthMetrics | None:
    """
    Wachstumsmetriken für eine einzelne ISIN.
    Geeignet für Detail-Panel (pro Klick aufgerufen).

    Returns:
        GrowthMetrics oder None wenn keine Historiedaten vorhanden.
    """
    current_year = str(date.today().year)

    query = """
        SELECT
            strftime('%Y', ex_date) AS yr,
            SUM(amount_micro)       AS total
        FROM dividend_history
        WHERE
            isin = :isin
            AND ex_date >= date('now', :neg_years)
            AND strftime('%Y', ex_date) < :current_year
        GROUP BY yr
        ORDER BY yr ASC
    """

    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(query, {
                "isin":         isin,
                "neg_years":    f"-{_GROWTH_HISTORY_YEARS} years",
                "current_year": current_year,
            }).fetchall()
    except sqlite3.Error:
        logger.exception("Fehler beim Laden der Wachstumsmetriken für %s.", isin)
        return None

    if not rows:
        return None

    year_data = [(row["yr"], row["total"]) for row in rows]
    return _compute_growth_metrics(year_data)


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
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM dividend_data WHERE isin = ?", (isin,)
        ).fetchone()
    if not row:
        return None
    last_ex = (
        date.fromisoformat(row["last_ex_date"])
        if row["last_ex_date"] else None
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
    cutoff = (
        datetime.now() - timedelta(hours=interval_hours)
    ).isoformat()
    today = date.today().isoformat()
    with _get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT i.isin
            FROM instruments i
            LEFT JOIN dividend_data d  ON i.isin = d.isin
            LEFT JOIN ticker_mapping tm ON i.isin = tm.isin
            WHERE
                (d.isin IS NULL OR d.updated_at < ?)
                AND (d.skip_until IS NULL OR d.skip_until <= ?)
                AND (tm.isin IS NULL OR tm.source != 'unresolvable')
            ORDER BY
                CASE SUBSTR(i.isin, 1, 2)
                    WHEN 'US' THEN 1 WHEN 'CA' THEN 1
                    WHEN 'DE' THEN 2 WHEN 'GB' THEN 2
                    WHEN 'FR' THEN 2 WHEN 'CH' THEN 2
                    WHEN 'NL' THEN 2 WHEN 'SE' THEN 2
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
    """
    Gibt ungesehene Schwellwert-Überschreitungen zurück.
    Enthält jetzt auch das frequency-Feld aus dividend_data
    für die E-Mail-Spalte und den GUI-Popup.
    """
    with _get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT tc.id, tc.isin, tc.yield_bps_old, tc.yield_bps_new,
                   tc.direction, tc.detected_at,
                   COALESCE(i.name_override, i.name) AS display_name,
                   d.frequency
            FROM threshold_crossings tc
            JOIN instruments i ON i.isin = tc.isin
            LEFT JOIN dividend_data d ON d.isin = tc.isin
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
