# Dateiname:     analysis/scorer.py
# Version:       2026-04-29
# Abhängigkeiten (intern): core.dividend_source, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
analysis/scorer.py

Dividenden-basiertes Scoring-System — Kernlogik von HYPilot.

Scoring-Dimensionen (Gewichtung spiegelt HYPilot-Ziel wider):
  1. Dividendenrendite    40 Punkte  (Kernziel: >10%)
  2. Ausschüttungsfrequenz 20 Punkte (monatlich bevorzugt)
  3. Dividendenstabilität  25 Punkte (Historie vorhanden)
  4. Payout-Qualität       15 Punkte (Ausschüttungsquote)

Gesamt: 100 Punkte möglich.

Alle Finanzwerte werden als int (bps/micro) empfangen —
keine float-Berechnungen in diesem Modul.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from core.dividend_source import DividendSnapshot, bps_to_decimal

logger = logging.getLogger(__name__)

# ── Schwellwerte ──────────────────────────────────────────────────────────────

_YIELD_TIER_1 = Decimal("0.10")   # >= 10%  → Kernziel erreicht
_YIELD_TIER_2 = Decimal("0.07")   # >= 7%   → gut
_YIELD_TIER_3 = Decimal("0.04")   # >= 4%   → akzeptabel

_PAYOUT_MAX   = Decimal("0.90")   # > 90%   → Risiko (nicht nachhaltig)
_PAYOUT_IDEAL = Decimal("0.70")   # <= 70%  → nachhaltig


# ── Ergebnistyp ───────────────────────────────────────────────────────────────

@dataclass
class DividendScore:
    isin:              str
    total:             int          # 0–100
    yield_points:      int          # max 40
    frequency_points:  int          # max 20
    stability_points:  int          # max 25
    payout_points:     int          # max 15
    rating:            str          # "STRONG_BUY" | "BUY" | "WATCH" | "REJECT"
    notes:             list[str]    # Begründungen


def _rating_from_score(score: int) -> str:
    if score >= 75:
        return "STRONG_BUY"
    if score >= 55:
        return "BUY"
    if score >= 35:
        return "WATCH"
    return "REJECT"


# ── Scoring-Dimensionen ───────────────────────────────────────────────────────

def _score_yield(
    yield_bps: int | None,
) -> tuple[int, list[str]]:
    """Max 40 Punkte. Kernziel: >= 10%."""
    notes: list[str] = []

    if yield_bps is None:
        notes.append("Rendite unbekannt")
        return 0, notes

    y = bps_to_decimal(yield_bps)
    assert y is not None

    if y >= _YIELD_TIER_1:
        notes.append(f"Rendite {float(y) * 100:.1f}% — Kernziel erreicht (≥10%)")
        return 40, notes
    if y >= _YIELD_TIER_2:
        points = int(40 * float(y / _YIELD_TIER_1))
        notes.append(f"Rendite {float(y) * 100:.1f}% — gut (≥7%)")
        return points, notes
    if y >= _YIELD_TIER_3:
        points = int(40 * float(y / _YIELD_TIER_1))
        notes.append(f"Rendite {float(y) * 100:.1f}% — akzeptabel (≥4%)")
        return points, notes

    notes.append(f"Rendite {float(y) * 100:.1f}% — zu niedrig (<4%)")
    return 0, notes


def _score_frequency(
    frequency: str | None,
) -> tuple[int, list[str]]:
    """Max 20 Punkte. Monatliche Ausschüttung bevorzugt."""
    mapping = {
        "monthly":     (20, "Monatliche Ausschüttung"),
        "quarterly":   (14, "Quartalsweise Ausschüttung"),
        "semi_annual": ( 8, "Halbjährliche Ausschüttung"),
        "annual":      ( 4, "Jährliche Ausschüttung"),
        "irregular":   ( 2, "Unregelmäßige Ausschüttung"),
    }
    if frequency is None:
        return 0, ["Ausschüttungsfrequenz unbekannt"]

    points, note = mapping.get(frequency, (0, f"Unbekannte Frequenz: {frequency}"))
    return points, [note]


def _score_stability(
    snapshot: DividendSnapshot,
) -> tuple[int, list[str]]:
    """
    Max 25 Punkte.
    Proxy: Snapshot vorhanden + last_ex_date vorhanden + Rendite nicht None.
    Echte Stabilitätsmessung (Wachstum über Jahre) kommt mit erweiterter
    Historie.
    """
    notes: list[str] = []
    points = 0

    if snapshot.yield_bps is not None:
        points += 10
        notes.append("Aktuelle Rendite verfügbar")

    if snapshot.last_ex_date is not None:
        points += 10
        notes.append(f"Letzte Ex-Date: {snapshot.last_ex_date}")

    if snapshot.last_amount_micro is not None and snapshot.last_amount_micro > 0:
        points += 5
        amount_display = float(snapshot.last_amount or 0)
        notes.append(
            f"Letzter Betrag: {amount_display:.4f} {snapshot.currency}"
        )

    return points, notes


def _score_payout(
    payout_ratio_bps: int | None,
) -> tuple[int, list[str]]:
    """
    Max 15 Punkte.
    Normalisiert yfinance-Werte > 10000 bps (>100%) —
    bei REITs strukturell möglich, wird neutral bewertet.
    """
    notes: list[str] = []

    if payout_ratio_bps is None:
        return 5, ["Ausschüttungsquote unbekannt (neutraler Wert)"]

    ratio = bps_to_decimal(payout_ratio_bps)
    assert ratio is not None

    # REITs: Payout >100% ist strukturell normal (FFO-Basis)
    # → neutral 8 Punkte statt Risikoabzug
    if ratio > Decimal("1.0"):
        notes.append(
            f"Ausschüttungsquote {float(ratio) * 100:.0f}% "
            f"— REIT/strukturell (neutral bewertet)"
        )
        return 8, notes

    if ratio > _PAYOUT_MAX:
        notes.append(
            f"Ausschüttungsquote {float(ratio) * 100:.0f}% — Risiko (>90%)"
        )
        return 0, notes

    if ratio <= _PAYOUT_IDEAL:
        notes.append(
            f"Ausschüttungsquote {float(ratio) * 100:.0f}% — nachhaltig (≤70%)"
        )
        return 15, notes

    # 70–90%: linear interpolieren
    points = int(
        15 * float((_PAYOUT_MAX - ratio) / (_PAYOUT_MAX - _PAYOUT_IDEAL))
    )
    notes.append(
        f"Ausschüttungsquote {float(ratio) * 100:.0f}% — erhöht (70–90%)"
    )
    return points, notes


# ── Öffentliche API ───────────────────────────────────────────────────────────

def score_dividend_snapshot(snapshot: DividendSnapshot) -> DividendScore:
    """
    Berechnet einen DividendScore aus einem DividendSnapshot.

    Args:
        snapshot: Aggregierte Dividenden-Kennzahlen.

    Returns:
        DividendScore mit Gesamtpunktzahl, Teilscores und Rating.
    """
    all_notes: list[str] = []

    y_pts, y_notes = _score_yield(snapshot.yield_bps)
    f_pts, f_notes = _score_frequency(snapshot.frequency)
    s_pts, s_notes = _score_stability(snapshot)
    p_pts, p_notes = _score_payout(snapshot.payout_ratio_bps)

    all_notes.extend(y_notes)
    all_notes.extend(f_notes)
    all_notes.extend(s_notes)
    all_notes.extend(p_notes)

    total  = y_pts + f_pts + s_pts + p_pts
    rating = _rating_from_score(total)

    logger.debug(
        "Score %s: %d Pkt (%s) — Rendite:%d Freq:%d Stab:%d Payout:%d",
        snapshot.isin, total, rating, y_pts, f_pts, s_pts, p_pts,
    )

    return DividendScore(
        isin=snapshot.isin,
        total=total,
        yield_points=y_pts,
        frequency_points=f_pts,
        stability_points=s_pts,
        payout_points=p_pts,
        rating=rating,
        notes=all_notes,
    )