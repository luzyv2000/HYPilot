# Dateiname:     analysis/scorer.py
# Version:       2026-05-09-growth
# Abhängigkeiten (intern): core.dividend_source, db.dividend_repository
# Abhängigkeiten (extern): keine
"""
analysis/scorer.py

Dividenden-basiertes Scoring-System.

Neu 2026-05-09:
  _score_stability_from_history() — echte Stabilitätsmessung via
  GrowthMetrics (Wachstum, Konsistenz, Kürzungshistorie).

  score_dividend_snapshot() akzeptiert optionalen growth_metrics-Parameter.
  Ohne ihn: Fallback auf bisherigen Proxy (_score_stability).
  Mit ihm: echte Historien-basierte Stabilitätsbewertung.

Scoring-Dimensionen (Gewichtung unverändert):
  1. Dividendenrendite     40 Punkte  (Kernziel: >10%)
  2. Ausschüttungsfrequenz 20 Punkte
  3. Dividendenstabilität  25 Punkte  (jetzt historienbasiert wenn möglich)
  4. Payout-Qualität       15 Punkte
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from core.dividend_source import DividendSnapshot, bps_to_decimal
from db.dividend_repository import GrowthMetrics

logger = logging.getLogger(__name__)

# ── Schwellwerte ──────────────────────────────────────────────────────────────

_YIELD_TIER_1 = Decimal("0.10")
_YIELD_TIER_2 = Decimal("0.07")
_YIELD_TIER_3 = Decimal("0.04")

_PAYOUT_MAX   = Decimal("0.90")
_PAYOUT_IDEAL = Decimal("0.70")

_GROWTH_STRONG = Decimal("0.05")   # ≥5% YoY → stark
_GROWTH_POS    = Decimal("0.00")   # >0% YoY → positiv


# ── Ergebnistyp ───────────────────────────────────────────────────────────────

@dataclass
class DividendScore:
    isin:              str
    total:             int
    yield_points:      int
    frequency_points:  int
    stability_points:  int
    payout_points:     int
    rating:            str
    notes:             list[str]


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
    """Max 20 Punkte."""
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
    Max 25 Punkte — Proxy-basiert (kein Historienzugriff).
    Wird als Fallback genutzt wenn keine GrowthMetrics verfügbar sind.
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


def _score_stability_from_history(
    metrics: GrowthMetrics,
) -> tuple[int, list[str]]:
    """
    Max 25 Punkte — historienbasiert via GrowthMetrics.

    Punkteverteilung:
      Jahre mit Daten (max 10): ≥3 Jahre → 10, 2 → 6, 1 → 3
      YoY-Wachstum    (max 10): ≥5% → 10, >0% → 6, stabil → 3, negativ → 0
      Keine Kürzung   (max  5): nur wenn ≥2 Jahre Daten vorhanden
    """
    notes: list[str] = []
    points = 0

    # ── Jahre mit Daten ───────────────────────────────────────────────────────
    if metrics.years_of_data >= 3:
        points += 10
        notes.append(
            f"Dividendenhistorie: {metrics.years_of_data} vollständige Jahre"
        )
    elif metrics.years_of_data == 2:
        points += 6
        notes.append("Dividendenhistorie: 2 vollständige Jahre")
    elif metrics.years_of_data == 1:
        points += 3
        notes.append("Dividendenhistorie: 1 vollständiges Jahr")
    else:
        notes.append("Keine vollständige Dividendenhistorie verfügbar")

    # ── YoY-Wachstum ──────────────────────────────────────────────────────────
    if metrics.yoy_growth is not None:
        g = metrics.yoy_growth
        pct = float(g) * 100
        if g >= _GROWTH_STRONG:
            points += 10
            notes.append(f"Dividendenwachstum {pct:.1f}% YoY — stark (≥5%)")
        elif g > _GROWTH_POS:
            points += 6
            notes.append(f"Dividendenwachstum {pct:.1f}% YoY — positiv")
        elif g == _GROWTH_POS:
            points += 3
            notes.append("Dividende stabil — kein Wachstum")
        else:
            notes.append(f"⚠ Dividende gesunken {pct:.1f}% YoY")
    else:
        # Kein Vergleich möglich (nur 1 Datenpunkt oder kein Vorjahr)
        points += 3
        notes.append("Wachstumsvergleich: zu wenig Daten")

    # ── Keine Kürzung ─────────────────────────────────────────────────────────
    if metrics.years_of_data >= 2:
        if not metrics.has_cut:
            points += 5
            notes.append("Keine Dividendenkürzung in der Historie")
        else:
            notes.append("⚠ Dividendenkürzung in der Historie erkannt")

    return points, notes


def _score_payout(
    payout_ratio_bps: int | None,
) -> tuple[int, list[str]]:
    """Max 15 Punkte."""
    notes: list[str] = []

    if payout_ratio_bps is None:
        return 5, ["Ausschüttungsquote unbekannt (neutraler Wert)"]

    ratio = bps_to_decimal(payout_ratio_bps)
    assert ratio is not None

    if ratio > Decimal("1.0"):
        notes.append(
            f"Ausschüttungsquote {float(ratio) * 100:.0f}%"
            " — REIT/strukturell (neutral bewertet)"
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

    points = int(
        15 * float((_PAYOUT_MAX - ratio) / (_PAYOUT_MAX - _PAYOUT_IDEAL))
    )
    notes.append(
        f"Ausschüttungsquote {float(ratio) * 100:.0f}% — erhöht (70–90%)"
    )
    return points, notes


# ── Öffentliche API ───────────────────────────────────────────────────────────

def score_dividend_snapshot(
    snapshot: DividendSnapshot,
    growth_metrics: GrowthMetrics | None = None,
) -> DividendScore:
    """
    Berechnet einen DividendScore aus einem DividendSnapshot.

    Args:
        snapshot:       Aggregierte Dividenden-Kennzahlen.
        growth_metrics: Optionale Wachstumsmetriken aus dividend_history.
                        Wenn vorhanden: echte historienbasierte Stabilitätsmessung.
                        Wenn None:      Fallback auf Proxy-Scoring.

    Returns:
        DividendScore mit Gesamtpunktzahl, Teilscores und Rating.
    """
    all_notes: list[str] = []

    y_pts, y_notes = _score_yield(snapshot.yield_bps)
    f_pts, f_notes = _score_frequency(snapshot.frequency)

    if growth_metrics is not None:
        s_pts, s_notes = _score_stability_from_history(growth_metrics)
    else:
        s_pts, s_notes = _score_stability(snapshot)

    p_pts, p_notes = _score_payout(snapshot.payout_ratio_bps)

    all_notes.extend(y_notes)
    all_notes.extend(f_notes)
    all_notes.extend(s_notes)
    all_notes.extend(p_notes)

    total  = y_pts + f_pts + s_pts + p_pts
    rating = _rating_from_score(total)

    logger.debug(
        "Score %s: %d Pkt (%s) — Rendite:%d Freq:%d Stab:%d Payout:%d "
        "[growth_metrics=%s]",
        snapshot.isin, total, rating,
        y_pts, f_pts, s_pts, p_pts,
        "ja" if growth_metrics else "nein",
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