# Dateiname:     analysis/engine.py
# Version:       2026-04-22
# Abhängigkeiten (intern): analysis.rules, analysis.filter, analysis.scorer,
#                          core.universe_service, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
analysis/engine.py

Einheitlicher Analyse-Orchestrator für HYPilot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from analysis.filter import is_investable
from analysis.rules import classify_instrument, score_instrument as name_score
from analysis.scorer import DividendScore, score_dividend_snapshot
from core.universe_service import get_all_instruments
from db.dividend_repository import get_snapshot

logger = logging.getLogger(__name__)


@dataclass
class UniverseEntry:
    name: str
    isin: str
    wkn: str | None
    category: str
    name_score: int


def universe_screen(
    limit: int = 500,
    category_filter: str | None = None,
) -> list[UniverseEntry]:
    """
    Schnelles Vorfiltern des TR-Universums ohne Netzwerk-Aufruf.
    """
    instruments = get_all_instruments(limit=limit)
    results: list[UniverseEntry] = []

    for inst in instruments:
        if not is_investable(inst):
            continue

        isin = inst["isin"]
        name = inst["name"]

        # ISIN an Klassifikation übergeben für ETF-Domizil-Erkennung
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


def score_instrument(isin: str) -> DividendScore | None:
    """
    Bewertet ein Instrument anhand gecachter Dividendendaten (nur DB).
    """
    snapshot = get_snapshot(isin)
    if snapshot is None:
        logger.warning(
            "Keine Dividendendaten für %s — "
            "zuerst dividend_service.update_dividend_data() aufrufen.",
            isin,
        )
        return None

    result = score_dividend_snapshot(snapshot)
    logger.info("Score %s: %d/100 → %s", isin, result.total, result.rating)
    return result
