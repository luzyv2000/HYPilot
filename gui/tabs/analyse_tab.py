# Dateiname: gui/tabs/analyse_tab.py
# Version: 2026-05-12-repair
# Abhängigkeiten (intern):
#   db.dividend_repository
#   analysis.scorer
#   core.dividend_source
# Abhängigkeiten (extern):
#   customtkinter

"""
gui/tabs/analyse_tab.py

Analyse-Tab mit fünf Bereichen:

  1. Scoring-Verteilung
  2. Top-20 Score
  3. Wachstums-Highlights
  4. Threshold-Crossings
  5. Datenstand & Quellen

Alle Daten werden im Hintergrund geladen.
Keine Netzwerkzugriffe.
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
import tkinter as tk

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tkinter import ttk
from typing import Any

import customtkinter as ctk

logger = logging.getLogger(__name__)

DB_PATH: Path = Path(
    "/home/luzy/workspace/openclaw-min/db/hypilot.db"
)

# ────────────────────────────────────────────────────────────────
# Farbpalette
# ────────────────────────────────────────────────────────────────

_RATING_COLORS_DARK = {
    "STRONG_BUY": "#66bb6a",
    "BUY": "#aed581",
    "WATCH": "#ffb74d",
    "REJECT": "#ef5350",
}

_RATING_COLORS_LIGHT = {
    "STRONG_BUY": "#1b5e20",
    "BUY": "#558b2f",
    "WATCH": "#e65100",
    "REJECT": "#b71c1c",
}

_RATING_ORDER = [
    "STRONG_BUY",
    "BUY",
    "WATCH",
    "REJECT",
]

_RATING_LABEL = {
    "STRONG_BUY": "STRONG BUY",
    "BUY": "BUY",
    "WATCH": "WATCH",
    "REJECT": "REJECT",
}

# ────────────────────────────────────────────────────────────────
# Datenmodelle
# ────────────────────────────────────────────────────────────────


@dataclass
class TopEntry:
    name: str
    isin: str
    score: int
    rating: str
    yield_pct: str
    frequency: str
    yoy_pct: str


@dataclass
class CrossingEntry:
    direction: str
    name: str
    isin: str
    yield_old: str
    yield_new: str
    detected_at: str


@dataclass
class AnalyseData:
    rating_counts: dict[str, int]
    top20: list[TopEntry]
    growth_top10: list[TopEntry]
    crossings: list[CrossingEntry]
    totals: dict[str, int]
    sources: list[dict[str, Any]]
    total_scored: int
    load_time_ms: int


# ────────────────────────────────────────────────────────────────
# SQL
# ────────────────────────────────────────────────────────────────

_QUERY_ALL = """
SELECT
    COALESCE(i.name_override, i.name) AS display_name,
    i.isin,
    d.yield_bps,
    d.frequency,
    d.last_amount_micro,
    d.last_ex_date,
    d.currency,
    d.payout_ratio_bps,
    d.data_source
FROM instruments i
JOIN dividend_data d
    ON i.isin = d.isin
WHERE d.yield_bps IS NOT NULL
"""


# ────────────────────────────────────────────────────────────────
# Hilfsfunktionen
# ────────────────────────────────────────────────────────────────

def _freq_display(freq: str | None) -> str:
    mapping = {
        "monthly": "monatlich",
        "quarterly": "quartalsw.",
        "semi_annual": "halbjährl.",
        "annual": "jährlich",
        "irregular": "unregel.",
    }
    return mapping.get(freq or "", "—")


# ────────────────────────────────────────────────────────────────
# Daten laden
# ────────────────────────────────────────────────────────────────

def _load_analyse_data() -> AnalyseData:
    import time as _time

    t0 = _time.monotonic()

    from analysis.scorer import score_dividend_snapshot
    from core.dividend_source import DividendSnapshot
    from db.dividend_repository import get_growth_metrics_bulk

    growth_map = get_growth_metrics_bulk(db_path=DB_PATH)

    rating_counts = {r: 0 for r in _RATING_ORDER}
    all_entries: list[TopEntry] = []

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row

            rows = conn.execute(_QUERY_ALL).fetchall()

            cutoff = (
                date.today() - timedelta(days=30)
            ).isoformat()

            crossing_rows = conn.execute(
                """
                SELECT
                    tc.direction,
                    tc.yield_bps_old,
                    tc.yield_bps_new,
                    tc.detected_at,
                    COALESCE(
                        i.name_override,
                        i.name
                    ) AS name,
                    tc.isin
                FROM threshold_crossings tc
                JOIN instruments i
                    ON i.isin = tc.isin
                WHERE tc.detected_at >= ?
                ORDER BY tc.detected_at DESC
                LIMIT 50
                """,
                (cutoff,),
            ).fetchall()

            total_instr = conn.execute(
                "SELECT COUNT(*) FROM instruments"
            ).fetchone()[0]

            with_data = conn.execute(
                "SELECT COUNT(*) FROM dividend_data"
            ).fetchone()[0]

            with_yield = conn.execute(
                """
                SELECT COUNT(*)
                FROM dividend_data
                WHERE yield_bps > 0
                """
            ).fetchone()[0]

            high_yield = conn.execute(
                """
                SELECT COUNT(*)
                FROM dividend_data
                WHERE yield_bps >= 1000
                  AND yield_bps <= 5000
                """
            ).fetchone()[0]

            source_rows = conn.execute(
                """
                SELECT
                    data_source,
                    COUNT(*) AS n
                FROM dividend_data
                GROUP BY data_source
                ORDER BY n DESC
                """
            ).fetchall()

    except sqlite3.Error:
        logger.exception(
            "Datenbankfehler beim Laden der Analyse-Daten."
        )
        return AnalyseData(
            rating_counts={},
            top20=[],
            growth_top10=[],
            crossings=[],
            totals={},
            sources=[],
            total_scored=0,
            load_time_ms=0,
        )

    for row in rows:
        try:
            last_ex = (
                date.fromisoformat(row["last_ex_date"])
                if row["last_ex_date"]
                else None
            )

            snapshot = DividendSnapshot(
                isin=row["isin"],
                yield_bps=row["yield_bps"],
                frequency=row["frequency"],
                last_amount_micro=row["last_amount_micro"],
                last_ex_date=last_ex,
                currency=row["currency"] or "USD",
                payout_ratio_bps=row["payout_ratio_bps"],
                data_source=row["data_source"] or "yfinance",
            )

            metrics = growth_map.get(row["isin"])

            score = score_dividend_snapshot(
                snapshot,
                growth_metrics=metrics,
            )

            rating_counts[score.rating] += 1

            yoy_str = "—"

            if (
                metrics is not None
                and metrics.yoy_growth is not None
            ):
                pct = float(metrics.yoy_growth) * 100
                sign = "+" if pct >= 0 else ""
                yoy_str = f"{sign}{pct:.1f} %"

            yield_str = (
                f"{row['yield_bps'] / 100:.2f} %"
                if row["yield_bps"]
                else "—"
            )

            all_entries.append(
                TopEntry(
                    name=row["display_name"],
                    isin=row["isin"],
                    score=score.total,
                    rating=score.rating,
                    yield_pct=yield_str,
                    frequency=_freq_display(
                        row["frequency"]
                    ),
                    yoy_pct=yoy_str,
                )
            )

        except Exception:
            logger.debug(
                "Scoring fehlgeschlagen für %s",
                row["isin"],
            )
            continue

    top20 = sorted(
        all_entries,
        key=lambda e: e.score,
        reverse=True,
    )[:20]

    growth_candidates = [
        e
        for e in all_entries
        if (
            growth_map.get(e.isin) is not None
            and growth_map[e.isin].yoy_growth is not None
            and growth_map[e.isin].yoy_growth >= Decimal("0.05")
            and not growth_map[e.isin].has_cut
            and growth_map[e.isin].years_of_data >= 2
        )
    ]

    growth_top10 = sorted(
        growth_candidates,
        key=lambda e: (
            growth_map[e.isin].yoy_growth
            or Decimal("0")
        ),
        reverse=True,
    )[:10]

    crossings: list[CrossingEntry] = []

    for cr in crossing_rows:
        old = (
            f"{cr['yield_bps_old'] / 100:.1f}%"
            if cr["yield_bps_old"]
            else "—"
        )

        new = f"{cr['yield_bps_new'] / 100:.1f}%"

        crossings.append(
            CrossingEntry(
                direction=cr["direction"],
                name=cr["name"],
                isin=cr["isin"],
                yield_old=old,
                yield_new=new,
                detected_at=str(
                    cr["detected_at"]
                )[:10],
            )
        )

    elapsed_ms = int(
        (_time.monotonic() - t0) * 1000
    )

    logger.info(
        (
            "Analyse: %d Instrumente bewertet "
            "in %d ms."
        ),
        len(all_entries),
        elapsed_ms,
    )

    return AnalyseData(
        rating_counts=rating_counts,
        top20=top20,
        growth_top10=growth_top10,
        crossings=crossings,
        totals={
            "instruments": total_instr,
            "with_data": with_data,
            "with_yield": with_yield,
            "high_yield": high_yield,
        },
        sources=[dict(r) for r in source_rows],
        total_scored=len(all_entries),
        load_time_ms=elapsed_ms,
    )