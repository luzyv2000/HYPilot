# Dateiname:     gui/tabs/high_yield_tab.py
# Version:       2026-05-08
# Abhängigkeiten (intern): gui.widgets.instrument_table,
#                          gui.widgets.score_detail_panel,
#                          analysis.scorer
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/high_yield_tab.py

High-Yield-Tab: zeigt nur Instrumente mit Dividendenrendite >= 10 %.

Funktionen:
  - Vorgefilterter Datensatz (yield_bps >= 1000), sortiert nach
    Rendite absteigend
  - CSV-Export der aktuell angezeigten Zeilen
  - Score-Detail-Panel bei Selektion (identisch zu UniverseTab)
  - Suchfeld (Name / ISIN / WKN)

Architektur-Entscheidungen:
  - Eigener Tab statt Filter in UniverseTab: unabhängiger Sortierstatus,
    kein gegenseitiger Zustand, CSV-Export nur hier sinnvoll
  - _load_high_yield() läuft im Hintergrund-Thread (kein Netzwerk-Call)
  - CSV-Export läuft synchron im Hauptthread (< 50 ms für ~874 Zeilen)
"""

from __future__ import annotations

import csv
import logging
import queue
import sqlite3
import threading
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog
from typing import Any

import customtkinter as ctk

from gui.widgets.instrument_table import InstrumentTable, Row
from gui.widgets.score_detail_panel import ScoreDetailPanel

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# Schwellwert: 10 % = 1000 bps
_HIGH_YIELD_BPS: int = 1000

_QUERY = """
    SELECT
        COALESCE(i.name_override, i.name) AS display_name,
        i.isin,
        COALESCE(i.wkn, '')              AS wkn,
        d.yield_bps,
        d.frequency,
        d.last_amount_micro,
        d.last_ex_date,
        d.currency,
        d.payout_ratio_bps,
        d.data_source,
        CASE WHEN i.name_override IS NOT NULL THEN 1 ELSE 0 END AS has_override
    FROM instruments i
    JOIN dividend_data d ON i.isin = d.isin
    WHERE d.yield_bps >= ?
    ORDER BY d.yield_bps DESC
"""

_RATING_SHORT = {
    "STRONG_BUY": "SB",
    "BUY":        "B",
    "WATCH":      "W",
    "REJECT":     "R",
}


def _format_div(yield_bps: int | None) -> str:
    if yield_bps is None:
        return "—"
    return f"{yield_bps / 100.0:.2f} %"


def _format_isin_wkn(isin: str, wkn: str) -> str:
    return f"{isin}\n{wkn}" if wkn else isin


def _format_score(score_total: int, rating: str) -> str:
    short = _RATING_SHORT.get(rating, rating[:1])
    return f"{score_total} {short}"


def _load_high_yield() -> list[Row]:
    """
    Lädt alle High-Yield-Instrumente (>= 10 %) aus der DB.
    Berechnet Score für jede Zeile. Läuft im Hintergrund-Thread.
    """
    from analysis.scorer import score_dividend_snapshot
    from core.dividend_source import DividendSnapshot

    rows: list[Row] = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for db_row in conn.execute(_QUERY, (_HIGH_YIELD_BPS,)):
                name = db_row["display_name"]
                if db_row["has_override"]:
                    name = "✎ " + name

                score_display = "—"
                try:
                    last_ex = (
                        date.fromisoformat(db_row["last_ex_date"])
                        if db_row["last_ex_date"]
                        else None
                    )
                    snapshot = DividendSnapshot(
                        isin=db_row["isin"],
                        yield_bps=db_row["yield_bps"],
                        frequency=db_row["frequency"],
                        last_amount_micro=db_row["last_amount_micro"],
                        last_ex_date=last_ex,
                        currency=db_row["currency"] or "USD",
                        payout_ratio_bps=db_row["payout_ratio_bps"],
                        data_source=db_row["data_source"] or "yfinance",
                    )
                    score = score_dividend_snapshot(snapshot)
                    score_display = _format_score(score.total, score.rating)
                except Exception:
                    logger.debug(
                        "Score-Berechnung fehlgeschlagen für %s.",
                        db_row["isin"],
                    )

                rows.append((
                    "",
                    name,
                    _format_isin_wkn(db_row["isin"], db_row["wkn"]),
                    _format_div(db_row["yield_bps"]),
                    score_display,
                    db_row["isin"],
                ))

    except sqlite3.Error:
        logger.exception("Datenbankfehler beim Laden der High-Yield-Instrumente.")

    logger.info("High-Yield geladen: %d Instrumente (>= 10 %%).", len(rows))
    return rows


class HighYieldTab(ctk.CTkFrame):
    """High-Yield-Tab (>= 10 % Dividendenrendite)."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Rohdaten für CSV-Export (werden beim Laden gespeichert)
        self._raw_rows: list[Row] = []
        self._raw_lock = threading.Lock()

        self._build_toolbar()
        self._build_table()
        self._build_detail_panel()

        self._table.load_data(self._loader_with_cache)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ctk.CTkLabel(
            bar,
            text="Instrumente mit Dividendenrendite ≥ 10 %",
            font=ctk.CTkFont(size=12),
            text_color=("gray30", "gray80"),
            anchor="w",
        ).pack(side="left", padx=(0, 16))

        ctk.CTkButton(
            bar,
            text="↻  Aktualisieren",
            width=140,
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar,
            text="📥  CSV exportieren",
            width=160,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            command=self._export_csv,
        ).pack(side="left", padx=(0, 8))

        self._count_label = ctk.CTkLabel(
            bar,
            text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
            anchor="e",
        )
        self._count_label.pack(side="right", padx=(0, 4))

    def _build_table(self) -> None:
        # Trennlinie unter Toolbar
        ctk.CTkFrame(
            self, height=1, fg_color=("gray75", "gray30")
        ).grid(row=1, column=0, sticky="ew", padx=0)

        self._table = InstrumentTable(self)
        self._table.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        self._table.set_select_callback(self._on_instrument_selected)

    def _build_detail_panel(self) -> None:
        ctk.CTkFrame(
            self, height=1, fg_color=("gray75", "gray30")
        ).grid(row=3, column=0, sticky="ew", padx=0)

        self._detail_panel = ScoreDetailPanel(self, height=160)
        self._detail_panel.grid(row=4, column=0, sticky="ew", padx=0, pady=0)
        self._detail_panel.grid_propagate(False)

    # ── Datenladen ────────────────────────────────────────────────────────────

    def _loader_with_cache(self) -> list[Row]:
        """Lädt Daten, speichert Kopie für CSV-Export."""
        rows = _load_high_yield()
        with self._raw_lock:
            self._raw_rows = rows
        # Anzahl-Label im Hauptthread aktualisieren
        self.after(0, lambda: self._count_label.configure(
            text=f"{len(rows)} Instrumente"
        ))
        return rows

    def _refresh(self) -> None:
        self._detail_panel.clear()
        self._table.load_data(self._loader_with_cache)

    def _on_instrument_selected(self, isin: str) -> None:
        self._detail_panel.update(isin)

    # ── CSV-Export ────────────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        """
        Exportiert die aktuell geladenen High-Yield-Instrumente als CSV.
        Synchron im Hauptthread — bei ~874 Zeilen < 50 ms.
        """
        with self._raw_lock:
            rows = list(self._raw_rows)

        if not rows:
            logger.info("CSV-Export: keine Daten vorhanden.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        default_name = f"hypilot_high_yield_{timestamp}.csv"

        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV-Datei", "*.csv"), ("Alle Dateien", "*.*")],
            initialfile=default_name,
            title="High-Yield-Liste exportieren",
        )

        if not filepath:
            return  # Nutzer hat abgebrochen

        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow([
                    "Name", "ISIN", "WKN", "Rendite %", "Score", "ISIN_raw"
                ])
                for row in rows:
                    # row = (flag, name, isin_wkn, div, score, isin_raw)
                    isin_wkn_parts = row[2].split("\n")
                    isin_part = isin_wkn_parts[0]
                    wkn_part  = isin_wkn_parts[1] if len(isin_wkn_parts) > 1 else ""
                    writer.writerow([
                        row[1].lstrip("✎ "),  # Name ohne Präfix
                        isin_part,
                        wkn_part,
                        row[3],               # Rendite z.B. "12.34 %"
                        row[4],               # Score z.B. "78 SB"
                        row[5],               # ISIN raw
                    ])

            logger.info(
                "CSV-Export: %d Zeilen → %s", len(rows), filepath
            )
        except OSError as exc:
            logger.error("CSV-Export fehlgeschlagen: %s", exc)