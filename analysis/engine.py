# Dateiname:     analysis/engine.py
# Version:       2026-04-22
# Abhängigkeiten (intern): analysis.rules, analysis.filter, analysis.scorer,
#                          core.universe_service, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
analysis/engine.py

Einheitlicher Analyse-Orchestrator für HYPilot.

Zwei Betriebsmodi:
  1. universe_screen()  — schnelles Vorfiltern des TR-Universums
                          (name-basiert, kein Netzwerk-Aufruf)
  2. score_instrument() — vollständige Dividenden-Bewertung einer ISIN
                          (benötigt Netzwerk via dividend_service)

Ablauf universe_screen:
  Alle Instrumente → is_investable() → classify() → name_score()
  → sortiert nach name_score

Ablauf score_instrument:
  ISIN → dividend_repository (DB-Cache) → score_dividend_snapshot()
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


# ── Ergebnistypen ─────────────────────────────────────────────────────────────

@dataclass
class UniverseEntry:
    """Ergebnis des schnellen Universe-Screenings (name-basiert)."""
    name: str
    isin: str
    wkn: str | None
    category: str       # ETF | STOCK | BOND | DERIVATIVE | OPTION_STRATEGY
    name_score: int     # heuristischer Namensscore


# ── Universe-Screening ────────────────────────────────────────────────────────

def universe_screen(
    limit: int = 500,
    category_filter: str | None = None,
) -> list[UniverseEntry]:
    """
    Schnelles Vorfiltern des TR-Universums ohne Netzwerk-Aufruf.

    Args:
        limit:           Maximale Anzahl Instrumente aus der DB.
        category_filter: Optional — nur diese Kategorie zurückgeben
                         (z.B. 'ETF', 'STOCK').

    Returns:
        Gefilterte, sortierte Liste von UniverseEntry.
    """
    instruments = get_all_instruments(limit=limit)
    results: list[UniverseEntry] = []

    for inst in instruments:
        if not is_investable(inst):
            continue

        category = classify_instrument(inst["name"])

        if category_filter and category != category_filter:
            continue

        score = name_score(inst["name"])
        if score < 0:
            continue

        results.append(UniverseEntry(
            name=inst["name"],
            isin=inst["isin"],
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


# ── Vollständige Dividenden-Bewertung ─────────────────────────────────────────

def score_instrument(isin: str) -> DividendScore | None:
    """
    Bewertet ein einzelnes Instrument anhand der gecachten Dividendendaten.

    Benötigt vorherigen Aufruf von dividend_service.update_dividend_data().
    Ruft selbst kein Netzwerk auf — arbeitet ausschließlich auf der DB.

    Args:
        isin: ISIN des Instruments.

    Returns:
        DividendScore oder None wenn keine Dividendendaten in der DB.
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
    logger.info(
        "Score %s: %d/100 → %s",
        isin, result.total, result.rating,
    )
    return result
