# Dateiname:     analysis/engine.py
# Version:       2026-05-09-growth
# Abhängigkeiten (intern): analysis.filter, analysis.rules, analysis.scorer,
#                           core.universe_service, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
analysis/engine.py

Einheitlicher Analyse-Orchestrator für HYPilot.

Neu 2026-05-09: score_instrument() lädt GrowthMetrics und gibt sie
an score_dividend_snapshot() weiter — Stabilitätsdimension nutzt
jetzt echte Historienanalyse.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from analysis.filter import is_investable
from analysis.rules import classify_instrument, score_instrument as name_score
from analysis.scorer import DividendScore, score_dividend_snapshot
from core.universe_service import DB_PATH, get_all_instruments
from db.dividend_repository import get_growth_metrics, get_snapshot

logger = logging.getLogger(__name__)


@dataclass
class UniverseEntry:
    name:       str
    isin:       str
    wkn:        str | None
    category:   str
    name_score: int


def universe_screen(
    limit:           int        = 500,
    category_filter: str | None = None,
    db_path:         Path       = DB_PATH,
) -> list[UniverseEntry]:
    instruments = get_all_instruments(limit=limit, db_path=db_path)
    results: list[UniverseEntry] = []

    for inst in instruments:
        if not is_investable(inst):
            continue

        isin     = inst["isin"]
        name     = inst["name"]
        category = classify_instrument(name, isin)

        if category_filter and category != category_filter:
            continue

        score = name_score(name, isin)
        if score < 0:
            continue

        results.append(UniverseEntry(
            name=name,
            isin=isin,
            wkn=inst.get("wkn"),
            category=category,
            name_score=score,
        ))

    results.sort(key=lambda x: x.name_score, reverse=True)
    logger.info(
        "Universe-Screening: %d Instrumente nach Filter (%d geladen)",
        len(results), len(instruments),
    )
    return results


def score_instrument(
    isin:    str,
    db_path: Path = DB_PATH,
) -> DividendScore | None:
    """
    Bewertet ein einzelnes Instrument anhand gecachter Dividendendaten.
    Lädt GrowthMetrics für historienbasierte Stabilitätsbewertung.
    """
    snapshot = get_snapshot(isin, db_path=db_path)
    if snapshot is None:
        logger.warning(
            "Keine Dividendendaten für %s — "
            "zuerst dividend_service.update_dividend_data() aufrufen.", isin,
        )
        return None

    metrics = get_growth_metrics(isin, db_path=db_path)
    result  = score_dividend_snapshot(snapshot, growth_metrics=metrics)

    logger.info(
        "Score %s: %d/100 → %s [Stabilität via %s]",
        isin, result.total, result.rating,
        "Historie" if metrics else "Proxy",
    )
    return result