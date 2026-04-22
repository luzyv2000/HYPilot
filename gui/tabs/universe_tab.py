# Dateiname:     gui/tabs/universe_tab.py
# Version:       2026-04-22
# Abhängigkeiten (intern): gui.widgets.instrument_table,
#                          db.dividend_repository, core.universe_service
# Abhängigkeiten (extern): keine
"""
gui/tabs/universe_tab.py

TR-Universum-Tab: zeigt alle ~13.000 Instrumente aus der SQLite-DB
mit Dividendenrendite (sofern vorhanden).

Datenladen läuft vollständig im Hintergrund-Thread.
Kein Netzwerk-Aufruf — ausschließlich lokale DB.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import customtkinter as ctk

from gui.widgets.instrument_table import InstrumentTable, Row

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# SQL: alle Instrumente + Dividendenrendite (LEFT JOIN)
_QUERY = """
    SELECT
        i.name,
        i.isin,
        COALESCE(i.wkn, '') AS wkn,
        d.yield_bps
    FROM instruments i
    LEFT JOIN dividend_data d ON i.isin = d.isin
    ORDER BY i.name ASC
"""


def _format_div(yield_bps: int | None) -> str:
    """Formatiert Dividendenrendite für Anzeige."""
    if yield_bps is None:
        return "—"
    percent = yield_bps / 100.0
    return f"{percent:.2f} %"


def _format_isin_wkn(isin: str, wkn: str) -> str:
    """
    Kombiniert ISIN und WKN für Anzeige in einer Zelle.
    Zwei Zeilen via \\n (rowheight=40 in Treeview-Style).
    """
    if wkn:
        return f"{isin}\n{wkn}"
    return isin


def _load_instruments() -> list[Row]:
    """
    Lädt alle Instrumente aus der DB.
    Wird im Hintergrund-Thread aufgerufen.

    Returns:
        Liste von Row-Tuples:
        (flag, name, isin_wkn, div_display, isin_raw)
    """
    rows: list[Row] = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for db_row in conn.execute(_QUERY):
                rows.append((
                    "",                                          # flag (leer)
                    db_row["name"],                             # Wertpapiername
                    _format_isin_wkn(db_row["isin"], db_row["wkn"]),  # ISIN/WKN
                    _format_div(db_row["yield_bps"]),           # Div %
                    db_row["isin"],                             # isin_raw (Item-ID)
                ))
    except sqlite3.Error:
        logger.exception("Datenbankfehler beim Laden des Universums.")
    logger.info("Universe geladen: %d Instrumente.", len(rows))
    return rows


class UniverseTab(ctk.CTkFrame):
    """
    Inhalt des TR-Universum-Tabs.
    Besteht aus Toolbar (Aktionsbuttons) + InstrumentTable.
    """

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_toolbar()
        self._build_table()
        self._table.load_data(_load_instruments)

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ctk.CTkButton(
            bar,
            text="↻  Aktualisieren",
            width=140,
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        # Kategorie-Filter
        self._category_var = ctk.StringVar(value="Alle")
        ctk.CTkOptionMenu(
            bar,
            values=["Alle", "ETF", "STOCK", "BOND", "DERIVATIVE"],
            variable=self._category_var,
            width=140,
            command=self._on_category_change,
        ).pack(side="left", padx=(0, 8))

        # Nur mit Dividende
        self._div_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            bar,
            text="Nur mit Dividende",
            variable=self._div_only_var,
            command=self._on_filter_change,
        ).pack(side="left", padx=(0, 8))

    def _build_table(self) -> None:
        self._table = InstrumentTable(self)
        self._table.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

    def _refresh(self) -> None:
        self._table.load_data(_load_instruments)

    def _on_category_change(self, _: str) -> None:
        self._on_filter_change()

    def _on_filter_change(self) -> None:
        """
        Wendet Kategorie- und Dividenden-Filter auf geladene Daten an.
        Läuft im Hauptthread (Button/Checkbox-Callback).
        """
        category = self._category_var.get()
        div_only = self._div_only_var.get()

        # Filter auf _all_rows anwenden (kein Netzwerk, kein Thread nötig)
        from analysis.rules import classify_instrument

        def filtered_loader() -> list[Row]:
            base = _load_instruments()
            result = []
            for row in base:
                # row[1] = name, row[4] = isin_raw
                if category != "Alle":
                    cat = classify_instrument(row[1], row[4])
                    if cat != category:
                        continue
                if div_only and row[3] == "—":
                    continue
                result.append(row)
            return result

        self._table.load_data(filtered_loader)
