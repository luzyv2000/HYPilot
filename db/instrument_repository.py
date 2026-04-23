# Dateiname:     db/instrument_repository.py
# Version:       2026-04-22-A
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine (sqlite3 ist stdlib)
"""
db/instrument_repository.py

CRUD-Operationen für Instrument-Stammdaten mit Fokus auf
manuelle Namensänderungen und PDF-Konfliktverwaltung.

Namenslogik:
  - name          : Original aus TR-PDF, wird bei neuem PDF aktualisiert
                    sofern kein name_override gesetzt ist
  - name_override : Manuell gesetzt, hat immer Vorrang
  - Anzeige:        COALESCE(name_override, name)

PDF-Konflikt-Logik:
  - PDF liefert neuen Namen für bekannte ISIN
  - name_override gesetzt → Konflikt still ignoriert (Nutzer hat bewusst
    einen eigenen Namen gewählt)
  - name_override nicht gesetzt → Eintrag in pending_name_changes
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")


# ── Datenklassen ──────────────────────────────────────────────────────────────

@dataclass
class PendingNameChange:
    """Ausstehende Namensänderung aus PDF-Import."""
    id: int
    isin: str
    name_current: str
    name_pdf: str
    detected_at: str


# ── Verbindung ────────────────────────────────────────────────────────────────

def _get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


# ── Name-Override ─────────────────────────────────────────────────────────────

def set_name_override(
    isin: str,
    new_name: str,
    db_path: Path = DB_PATH,
) -> None:
    """
    Setzt oder aktualisiert den manuellen Namen für eine ISIN.
    Leerer String löscht den Override (Original-PDF-Name wird wieder gezeigt).
    """
    override = new_name.strip() or None
    with _get_connection(db_path) as conn:
        conn.execute(
            "UPDATE instruments SET name_override = ? WHERE isin = ?",
            (override, isin),
        )
        conn.commit()
    logger.info(
        "name_override für %s gesetzt: %r",
        isin, override,
    )


def get_display_name(
    isin: str,
    db_path: Path = DB_PATH,
) -> str | None:
    """
    Gibt den aktuell angezeigten Namen zurück (override hat Vorrang).
    """
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(name_override, name) AS display_name "
            "FROM instruments WHERE isin = ?",
            (isin,),
        ).fetchone()
    return row["display_name"] if row else None


def get_instrument_names(
    isin: str,
    db_path: Path = DB_PATH,
) -> dict[str, str | None] | None:
    """
    Gibt name, name_override und display_name zurück.
    Nützlich für den Edit-Dialog.
    """
    with _get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                name,
                name_override,
                COALESCE(name_override, name) AS display_name
            FROM instruments WHERE isin = ?
            """,
            (isin,),
        ).fetchone()
    if not row:
        return None
    return {
        "name":         row["name"],
        "name_override": row["name_override"],
        "display_name": row["display_name"],
    }


# ── Pending Name Changes ──────────────────────────────────────────────────────

def add_pending_name_change(
    isin: str,
    name_current: str,
    name_pdf: str,
    db_path: Path = DB_PATH,
) -> None:
    """
    Speichert einen PDF-Namenskonflikt zur Nutzer-Entscheidung.
    Bereits vorhandener Eintrag für dieselbe ISIN wird aktualisiert.
    """
    with _get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO pending_name_changes
                (isin, name_current, name_pdf, detected_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(isin) DO UPDATE SET
                name_current = excluded.name_current,
                name_pdf     = excluded.name_pdf,
                detected_at  = excluded.detected_at
            """,
            (isin, name_current, name_pdf, datetime.now().isoformat()),
        )
        conn.commit()
    logger.debug("Pending name change: %s → %r", isin, name_pdf)


def get_pending_name_changes(
    db_path: Path = DB_PATH,
) -> list[PendingNameChange]:
    """Gibt alle ausstehenden Namensänderungen zurück."""
    with _get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM pending_name_changes ORDER BY detected_at ASC"
        ).fetchall()
    return [
        PendingNameChange(
            id=row["id"],
            isin=row["isin"],
            name_current=row["name_current"],
            name_pdf=row["name_pdf"],
            detected_at=row["detected_at"],
        )
        for row in rows
    ]


def count_pending_name_changes(db_path: Path = DB_PATH) -> int:
    """Anzahl ausstehender Namensänderungen (für Toolbar-Badge)."""
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM pending_name_changes"
        ).fetchone()
    return row["cnt"] if row else 0


def approve_name_change(
    pending_id: int,
    db_path: Path = DB_PATH,
) -> None:
    """
    Nutzer stimmt zu: PDF-Name wird als name_override übernommen.
    Pending-Eintrag wird gelöscht.
    """
    with _get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT isin, name_pdf FROM pending_name_changes WHERE id = ?",
            (pending_id,),
        ).fetchone()
        if not row:
            logger.warning("Pending ID %d nicht gefunden.", pending_id)
            return

        conn.execute(
            "UPDATE instruments SET name_override = ? WHERE isin = ?",
            (row["name_pdf"], row["isin"]),
        )
        conn.execute(
            "DELETE FROM pending_name_changes WHERE id = ?",
            (pending_id,),
        )
        conn.commit()
    logger.info("Name-Änderung genehmigt: ID %d", pending_id)


def reject_name_change(
    pending_id: int,
    db_path: Path = DB_PATH,
) -> None:
    """
    Nutzer lehnt ab: Pending-Eintrag wird gelöscht, Name bleibt.
    """
    with _get_connection(db_path) as conn:
        conn.execute(
            "DELETE FROM pending_name_changes WHERE id = ?",
            (pending_id,),
        )
        conn.commit()
    logger.info("Name-Änderung abgelehnt: ID %d", pending_id)