# Dateiname:     core/data_quality.py
# Version:       2026-05-15
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
core/data_quality.py

Datenqualitäts-Analyse für HYPilot.

Wird nach jedem Auto-Lauf von ingestion/auto_dividend_update.py aufgerufen.
Ergebnis wird als JSON in metadata (key='last_quality_report') gespeichert.
GUI liest den Bericht beim nächsten Start / Tab-Wechsel.

Geprüfte Dimensionen:
  1. Abdeckung       — ISINs mit/ohne Dividendendaten
  2. Ausreißer       — yield_bps > _MAX_PLAUSIBLE_YIELD_BPS (sollte 0 sein)
  3. Staleness       — Einträge nicht aktualisiert seit > _STALE_DAYS Tagen
  4. Skip-Until      — aktiv pausierte ISINs (18-Monats-Regel)
  5. Ticker-Mapping  — unresolvable / fehlende Mappings
  6. Nullrenditen    — Einträge mit yield_bps = 0 (kein Dividendenertrag)
  7. Quellen         — Verteilung der data_source-Werte
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# Schwellwert für "veraltet": Einträge älter als N Tage
_STALE_DAYS: int = 7

# Plausibilitäts-Cap — muss identisch mit dividend_service._MAX_PLAUSIBLE_YIELD_BPS
_MAX_PLAUSIBLE_YIELD_BPS: int = 5_000


# ── Ergebnistyp ───────────────────────────────────────────────────────────────

@dataclass
class QualityReport:
    """
    Vollständiger Datenqualitäts-Bericht.

    Alle Zählwerte beziehen sich auf den Zeitpunkt der Analyse.
    generated_at: ISO-Timestamp der Berichterstellung.
    """
    generated_at:        str

    # Abdeckung
    total_instruments:   int
    with_div_data:       int
    without_div_data:    int
    coverage_pct:        float          # with_div_data / total * 100

    # Ausreißer (kritisch — sollte 0 sein nach Plausibilitäts-Cap)
    outliers_above_cap:  int            # yield_bps > _MAX_PLAUSIBLE_YIELD_BPS
    outlier_isins:       list[str]      # max. 10 zur Anzeige

    # Staleness
    stale_entries:       int            # updated_at > _STALE_DAYS Tage alt
    stale_threshold_days: int

    # Skip-Until (18-Monats-Regel aktiv)
    skip_until_active:   int

    # Nullrenditen
    zero_yield:          int            # yield_bps = 0

    # Ticker-Mapping
    unresolvable_tickers: int
    missing_ticker:       int           # kein Eintrag in ticker_mapping

    # Quellen-Verteilung
    sources:             dict[str, int]  # {data_source: count}

    # Gesamtbewertung
    warnings:            list[str]       # Menschlesbare Warnungen


def _get_connection(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def run_quality_check(db_path: Path = DB_PATH) -> QualityReport:
    """
    Führt vollständige Datenqualitätsprüfung durch.

    Returns:
        QualityReport mit allen Metriken.
    """
    logger.info("Starte Datenqualitätsprüfung.")
    now = datetime.now().isoformat()

    try:
        with _get_connection(db_path) as conn:
            report = _analyse(conn, now)
    except sqlite3.Error:
        logger.exception("Datenbankfehler bei Datenqualitätsprüfung.")
        return QualityReport(
            generated_at=now,
            total_instruments=0, with_div_data=0, without_div_data=0,
            coverage_pct=0.0, outliers_above_cap=0, outlier_isins=[],
            stale_entries=0, stale_threshold_days=_STALE_DAYS,
            skip_until_active=0, zero_yield=0,
            unresolvable_tickers=0, missing_ticker=0,
            sources={}, warnings=["DB-Fehler bei Qualitätsprüfung."],
        )

    _log_report(report)
    return report


def _analyse(conn: sqlite3.Connection, now: str) -> QualityReport:
    warnings: list[str] = []

    # ── 1. Abdeckung ──────────────────────────────────────────────────────────
    total = conn.execute(
        "SELECT COUNT(*) FROM instruments"
    ).fetchone()[0]

    with_data = conn.execute(
        "SELECT COUNT(*) FROM dividend_data"
    ).fetchone()[0]

    without_data = total - with_data
    coverage_pct = round(with_data / total * 100, 1) if total > 0 else 0.0

    if coverage_pct < 80.0:
        warnings.append(
            f"Abdeckung niedrig: {coverage_pct:.1f} % "
            f"({with_data:,} / {total:,} Instrumente)."
        )

    # ── 2. Ausreißer ──────────────────────────────────────────────────────────
    outlier_rows = conn.execute(
        """
        SELECT isin, yield_bps FROM dividend_data
        WHERE yield_bps > ?
        ORDER BY yield_bps DESC
        LIMIT 10
        """,
        (_MAX_PLAUSIBLE_YIELD_BPS,),
    ).fetchall()

    outliers_count = conn.execute(
        "SELECT COUNT(*) FROM dividend_data WHERE yield_bps > ?",
        (_MAX_PLAUSIBLE_YIELD_BPS,),
    ).fetchone()[0]

    outlier_isins = [
        f"{r['isin']} ({r['yield_bps'] / 100:.1f} %)"
        for r in outlier_rows
    ]

    if outliers_count > 0:
        warnings.append(
            f"{outliers_count} Ausreißer über Cap "
            f"({_MAX_PLAUSIBLE_YIELD_BPS / 100:.0f} %) entdeckt — "
            "manuelle Prüfung empfohlen."
        )

    # ── 3. Staleness ─────────────────────────────────────────────────────────
    stale_cutoff = (
        datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
    )
    stale_count = conn.execute(
        """
        SELECT COUNT(*) FROM dividend_data
        WHERE updated_at < datetime('now', ?)
        AND (skip_until IS NULL OR skip_until <= date('now'))
        """,
        (f"-{_STALE_DAYS} days",),
    ).fetchone()[0]

    if stale_count > 1_000:
        warnings.append(
            f"{stale_count:,} Einträge seit > {_STALE_DAYS} Tagen "
            "nicht aktualisiert."
        )

    # ── 4. Skip-Until ─────────────────────────────────────────────────────────
    skip_active = conn.execute(
        "SELECT COUNT(*) FROM dividend_data "
        "WHERE skip_until > date('now')"
    ).fetchone()[0]

    # ── 5. Nullrenditen ───────────────────────────────────────────────────────
    zero_yield = conn.execute(
        "SELECT COUNT(*) FROM dividend_data WHERE yield_bps = 0"
    ).fetchone()[0]

    # ── 6. Ticker-Mapping ─────────────────────────────────────────────────────
    unresolvable = conn.execute(
        "SELECT COUNT(*) FROM ticker_mapping WHERE source = 'unresolvable'"
    ).fetchone()[0]

    missing_ticker = conn.execute(
        """
        SELECT COUNT(*) FROM instruments i
        LEFT JOIN ticker_mapping tm ON tm.isin = i.isin
        WHERE tm.isin IS NULL
        """
    ).fetchone()[0]

    # ── 7. Quellen ────────────────────────────────────────────────────────────
    source_rows = conn.execute(
        """
        SELECT data_source, COUNT(*) AS n
        FROM dividend_data
        GROUP BY data_source
        ORDER BY n DESC
        """
    ).fetchall()
    sources = {r["data_source"]: r["n"] for r in source_rows}

    return QualityReport(
        generated_at=now,
        total_instruments=total,
        with_div_data=with_data,
        without_div_data=without_data,
        coverage_pct=coverage_pct,
        outliers_above_cap=outliers_count,
        outlier_isins=outlier_isins,
        stale_entries=stale_count,
        stale_threshold_days=_STALE_DAYS,
        skip_until_active=skip_active,
        zero_yield=zero_yield,
        unresolvable_tickers=unresolvable,
        missing_ticker=missing_ticker,
        sources=sources,
        warnings=warnings,
    )


def _log_report(report: QualityReport) -> None:
    logger.info(
        "Datenqualität: %d/%d Instrumente (%.1f %%) | "
        "Ausreißer: %d | Stale: %d | Skip-Until: %d | "
        "Nullrenditen: %d | Unresolvable: %d",
        report.with_div_data, report.total_instruments,
        report.coverage_pct,
        report.outliers_above_cap,
        report.stale_entries,
        report.skip_until_active,
        report.zero_yield,
        report.unresolvable_tickers,
    )
    for w in report.warnings:
        logger.warning("Qualitätswarnung: %s", w)


def save_report(report: QualityReport, db_path: Path = DB_PATH) -> None:
    """Speichert den Bericht als JSON in metadata (key='last_quality_report')."""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO metadata (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                ("last_quality_report", json.dumps(asdict(report))),
            )
            conn.commit()
        logger.info("Qualitätsbericht in metadata gespeichert.")
    except sqlite3.Error:
        logger.exception("Konnte Qualitätsbericht nicht speichern.")


def load_report(db_path: Path = DB_PATH) -> QualityReport | None:
    """Lädt den letzten gespeicherten Bericht aus metadata."""
    try:
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'last_quality_report'"
            ).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        return QualityReport(**data)
    except Exception:
        logger.exception("Konnte Qualitätsbericht nicht laden.")
        return None
