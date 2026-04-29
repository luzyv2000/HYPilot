# Dateiname:     analysis/engine.py
# Version:       2026-04-29
# Abhängigkeiten (intern): analysis.filter, analysis.rules, analysis.scorer,
#                           core.universe_service, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
analysis/engine.py

Einheitlicher Analyse-Orchestrator für HYPilot.

Zwei Betriebsmodi:
  1. universe_screen()   — schnelles Vorfiltern des TR-Universums
                           (name-basiert, kein Netzwerk-Aufruf)
  2. score_instrument()  — vollständige Dividenden-Bewertung einer ISIN
                           (benötigt vorhandene dividend_data in DB)

Ablauf universe_screen:
  Alle Instrumente → is_investable() → classify() → name_score()
  → sortiert nach name_score

Ablauf score_instrument:
  ISIN → dividend_repository.get_snapshot() → score_dividend_snapshot()

Beide Funktionen akzeptieren db_path als Parameter für testbaren Betrieb
gegen temporäre Datenbanken.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from analysis.filter import is_investable
from analysis.rules import classify_instrument, score_instrument as name_score
from analysis.scorer import DividendScore, score_dividend_snapshot
from core.universe_service import DB_PATH, get_all_instruments
from db.dividend_repository import get_snapshot

logger = logging.getLogger(__name__)


# ── Ergebnistypen ─────────────────────────────────────────────────────────────

@dataclass
class UniverseEntry:
    """Ergebnis des schnellen Universe-Screenings (name-basiert)."""
    name:       str
    isin:       str
    wkn:        str | None
    category:   str          # ETF | STOCK | BOND | DERIVATIVE | OPTION_STRATEGY
    name_score: int          # heuristischer Namensscore


# ── Universe-Screening ────────────────────────────────────────────────────────

def universe_screen(
    limit:           int       = 500,
    category_filter: str | None = None,
    db_path:         Path      = DB_PATH,
) -> list[UniverseEntry]:
    """
    Schnelles Vorfiltern des TR-Universums ohne Netzwerk-Aufruf.

    Args:
        limit:           Maximale Anzahl Instrumente aus der DB.
        category_filter: Optional — nur diese Kategorie zurückgeben
                         (z. B. 'ETF', 'STOCK').
        db_path:         Pfad zur SQLite-DB (für Tests überschreibbar).

    Returns:
        Gefilterte, nach name_score absteigende Liste von UniverseEntry.
    """
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
        len(results),
        len(instruments),
    )
    return results


# ── Vollständige Dividenden-Bewertung ─────────────────────────────────────────

def score_instrument(
    isin:    str,
    db_path: Path = DB_PATH,
) -> DividendScore | None:
    """
    Bewertet ein einzelnes Instrument anhand gecachter Dividendendaten.

    Benötigt vorherigen Aufruf von
    dividend_service.update_dividend_data() für diese ISIN.
    Ruft selbst kein Netzwerk auf — arbeitet ausschließlich auf der DB.

    Args:
        isin:    ISIN des Instruments.
        db_path: Pfad zur SQLite-DB (für Tests überschreibbar).

    Returns:
        DividendScore oder None wenn keine Dividendendaten in der DB.
    """
    snapshot = get_snapshot(isin, db_path=db_path)

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
