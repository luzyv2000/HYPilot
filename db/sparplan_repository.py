# Dateiname:     db/sparplan_repository.py
# Version:       2026-05-17
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/sparplan_repository.py

Datenzugriffsschicht für das Sparplan-Bewertungs-Feature.

Zyklus-Logik:
  - Jede ISIN wird einmal pro Zyklus bewertet (sparplan = 'S' oder 'N').
  - Ein neuer Zyklus startet frühestens 6 Monate nach Zyklusstart UND
    wenn alle ISINs bewertet sind.
  - Neue ISINs (aus PDF-Import) haben sparplan = NULL und werden
    automatisch im laufenden Zyklus angeboten.

Prioritäts-Reihenfolge (innerhalb eines Zyklus):
  1. yield_bps >= 1000  (>= 10 %)
  2. yield_bps >= 500   (>=  5 %)
  3. yield_bps >  0     (>  0 %)
  4. Alle restlichen (kein Dividendeneintrag oder yield_bps = 0)

Pausierung:
  metadata.sparplan_paused_until : ISO-Timestamp bis wann Popup pausiert.
  Wird gesetzt wenn Nutzer "24h pausieren" klickt.

Zyklus-Tracking:
  metadata.sparplan_cycle_start : ISO-Timestamp letzter Zyklusstart.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_CYCLE_MONTHS: int = 6
_BATCH_SIZE:   int = 10

_META_CYCLE_START  = "sparplan_cycle_start"
_META_PAUSED_UNTIL = "sparplan_paused_until"


# ── Datenklasse ───────────────────────────────────────────────────────────────

@dataclass
class SparplanCandidate:
    """Ein zur Bewertung angebotenes Instrument."""
    isin:      str
    name:      str       # COALESCE(name_override, name)
    wkn:       str | None
    yield_bps: int | None
    priority:  int       # 1=high yield, 2=mid yield, 3=low yield, 4=rest


# ── Verbindung ────────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ── Metadata-Hilfsfunktionen ──────────────────────────────────────────────────

def _get_meta(key: str, db_path: Path = DB_PATH) -> str | None:
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None
    except sqlite3.Error:
        return None


def _set_meta(key: str, value: str, db_path: Path = DB_PATH) -> None:
    with _get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO metadata (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


# ── Pausierung ────────────────────────────────────────────────────────────────

def set_paused(hours: int = 24, db_path: Path = DB_PATH) -> None:
    """Pausiert das Sparplan-Popup für `hours` Stunden."""
    until = (datetime.now() + timedelta(hours=hours)).isoformat()
    _set_meta(_META_PAUSED_UNTIL, until, db_path)
    logger.info("Sparplan-Popup pausiert bis %s.", until[:16])


def is_paused(db_path: Path = DB_PATH) -> bool:
    """True wenn aktuell pausiert."""
    val = _get_meta(_META_PAUSED_UNTIL, db_path)
    if not val:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(val)
    except ValueError:
        return False


# ── Zyklus-Verwaltung ─────────────────────────────────────────────────────────

def _get_cycle_start(db_path: Path = DB_PATH) -> datetime | None:
    val = _get_meta(_META_CYCLE_START, db_path)
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except ValueError:
        return None


def _start_new_cycle(db_path: Path = DB_PATH) -> None:
    """Setzt alle sparplan-Felder zurück und startet neuen Zyklus."""
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            "UPDATE instruments SET sparplan = NULL, sparplan_reviewed_at = NULL"
        )
        conn.commit()
    _set_meta(_META_CYCLE_START, now, db_path)
    logger.info("Neuer Sparplan-Zyklus gestartet: %s", now[:16])


def _all_reviewed(db_path: Path = DB_PATH) -> bool:
    """True wenn alle ISINs im aktuellen Zyklus bewertet wurden."""
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM instruments WHERE sparplan IS NULL"
        ).fetchone()
    return (row["cnt"] if row else 1) == 0


def _cycle_lockout_expired(db_path: Path = DB_PATH) -> bool:
    """True wenn die 6-Monats-Sperrfrist abgelaufen ist."""
    cycle_start = _get_cycle_start(db_path)
    if cycle_start is None:
        return True
    months_elapsed = (datetime.now() - cycle_start).days / 30.44
    return months_elapsed >= _CYCLE_MONTHS


def maybe_reset_cycle(db_path: Path = DB_PATH) -> None:
    """
    Prüft ob ein neuer Zyklus gestartet werden soll.
    Wird beim App-Start und vor jedem Popup-Aufruf aufgerufen.

    Bedingungen:
      - Noch kein Zyklus gestartet, ODER
      - Alle ISINs bewertet UND Sperrfrist abgelaufen
    """
    cycle_start = _get_cycle_start(db_path)

    if cycle_start is None:
        # Erster Start: Zyklus initialisieren ohne Reset
        _set_meta(_META_CYCLE_START, datetime.now().isoformat(), db_path)
        logger.info("Sparplan-Zyklus erstmalig initialisiert.")
        return

    if _all_reviewed(db_path) and _cycle_lockout_expired(db_path):
        _start_new_cycle(db_path)


# ── Kandidaten-Abfrage ────────────────────────────────────────────────────────

def get_candidates(
    limit: int = _BATCH_SIZE,
    db_path: Path = DB_PATH,
) -> list[SparplanCandidate]:
    """
    Gibt bis zu `limit` unbewertete ISINs nach Priorität zurück.

    Priorität:
      1 → yield_bps >= 1000  (>= 10 %)
      2 → yield_bps >= 500   (>=  5 %)
      3 → yield_bps >  0     (>   0 %)
      4 → kein Dividendeneintrag oder yield_bps = 0 / NULL

    Innerhalb einer Priorität: absteigend nach yield_bps,
    dann alphabetisch nach Name.
    """
    maybe_reset_cycle(db_path)

    query = """
        SELECT
            i.isin,
            COALESCE(i.name_override, i.name) AS name,
            COALESCE(i.wkn, '')               AS wkn,
            d.yield_bps,
            CASE
                WHEN d.yield_bps >= 1000 THEN 1
                WHEN d.yield_bps >= 500  THEN 2
                WHEN d.yield_bps >  0    THEN 3
                ELSE                          4
            END AS priority
        FROM instruments i
        LEFT JOIN dividend_data d ON i.isin = d.isin
        WHERE i.sparplan IS NULL
        ORDER BY
            priority ASC,
            d.yield_bps DESC NULLS LAST,
            name       ASC
        LIMIT ?
    """

    try:
        with _get_connection(db_path) as conn:
            rows = conn.execute(query, (limit,)).fetchall()
    except sqlite3.Error:
        logger.exception("Fehler beim Laden der Sparplan-Kandidaten.")
        return []

    return [
        SparplanCandidate(
            isin=row["isin"],
            name=row["name"],
            wkn=row["wkn"] or None,
            yield_bps=row["yield_bps"],
            priority=row["priority"],
        )
        for row in rows
    ]


def count_unreviewed(db_path: Path = DB_PATH) -> int:
    """Anzahl noch nicht bewerteter ISINs im aktuellen Zyklus."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM instruments WHERE sparplan IS NULL"
            ).fetchone()
        return row["cnt"] if row else 0
    except sqlite3.Error:
        return 0


def count_total(db_path: Path = DB_PATH) -> int:
    """Gesamtzahl der Instrumente."""
    try:
        with _get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM instruments"
            ).fetchone()
        return row["cnt"] if row else 0
    except sqlite3.Error:
        return 0


# ── Bewertung speichern ───────────────────────────────────────────────────────

def mark_sparplan(
    isin: str,
    value: str,
    db_path: Path = DB_PATH,
) -> None:
    """
    Setzt sparplan-Wert für eine ISIN.

    Args:
        isin:  ISIN des Instruments
        value: 'S' (Sparplan ja) oder 'N' (Sparplan nein)
    """
    assert value in ("S", "N"), f"Ungültiger sparplan-Wert: {value!r}"
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE instruments
               SET sparplan = ?, sparplan_reviewed_at = ?
             WHERE isin = ?
            """,
            (value, now, isin),
        )
        conn.commit()
    logger.debug("Sparplan-Markierung: %s → %s", isin, value)


def mark_batch(
    decisions: dict[str, str],
    db_path: Path = DB_PATH,
) -> None:
    """
    Setzt sparplan-Werte für mehrere ISINs auf einmal.

    Args:
        decisions: {isin: 'S' | 'N'}
    """
    now = datetime.now().isoformat()
    with _get_connection(db_path) as conn:
        conn.executemany(
            """
            UPDATE instruments
               SET sparplan = ?, sparplan_reviewed_at = ?
             WHERE isin = ?
            """,
            [(v, now, k) for k, v in decisions.items()],
        )
        conn.commit()
    logger.info("Sparplan-Batch: %d Entscheidungen gespeichert.", len(decisions))


# ── Zyklus-Info für Anzeige ───────────────────────────────────────────────────

def get_cycle_info(db_path: Path = DB_PATH) -> dict:
    """
    Gibt Zyklus-Statistik zurück (für Info-Tab oder Status-Anzeige).

    Returns:
        {
          'cycle_start': str | None,
          'unreviewed':  int,
          'total':       int,
          'pct_done':    float,
          'paused_until': str | None,
        }
    """
    cycle_start = _get_meta(_META_CYCLE_START, db_path)
    paused      = _get_meta(_META_PAUSED_UNTIL, db_path)
    total       = count_total(db_path)
    unreviewed  = count_unreviewed(db_path)
    reviewed    = total - unreviewed
    pct_done    = round(reviewed / total * 100, 1) if total > 0 else 0.0

    return {
        "cycle_start":  cycle_start[:16].replace("T", " ") if cycle_start else None,
        "unreviewed":   unreviewed,
        "total":        total,
        "pct_done":     pct_done,
        "paused_until": paused[:16].replace("T", " ") if paused else None,
    }
