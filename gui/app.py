# Dateiname:     gui/app.py
# Version:       2026-05-12
# Abhängigkeiten (intern): gui.tabs.universe_tab, gui.tabs.high_yield_tab,
#                          gui.tabs.analyse_tab, gui.tabs.watchlist_tab
# Abhängigkeiten (extern): customtkinter

"""
gui/app.py — WatchlistTab integriert.
set_watchlist_tab() wird auf Universe- und HighYieldTab angewendet.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import customtkinter as ctk

from gui.tabs.universe_tab import UniverseTab
from gui.tabs.high_yield_tab import HighYieldTab
from gui.tabs.analyse_tab import AnalyseTab
from gui.tabs.watchlist_tab import WatchlistTab

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_DEFAULT_GEOMETRY = "1440x900"
_GEO_KEY = "gui_geometry"


class HYPilotApp(ctk.CTk):
    """Hauptfenster der HYPilot-Applikation."""

    def __init__(self) -> None:
        super().__init__()

        self.title("HYPilot")
        self.minsize(900, 600)

        self._restore_geometry()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu_bar()
        self._build_tab_view()
        self._build_status_bar()

        self.after(800, self._startup_checks)

    def _restore_geometry(self) -> None:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT value FROM metadata WHERE key = ?",
                    (_GEO_KEY,),
                ).fetchone()

            self.geometry(row[0] if row else _DEFAULT_GEOMETRY)

        except sqlite3.Error:
            self.geometry(_DEFAULT_GEOMETRY)

    def _save_geometry(self) -> None:
        try:
            geo = self.geometry()

            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO metadata (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key)
                    DO UPDATE SET value = excluded.value
                    """,
                    (_GEO_KEY, geo),
                )
                conn.commit()

        except sqlite3.Error:
            logger.warning(
                "Fenstergeometrie konnte nicht gespeichert werden."
            )

    def _build_menu_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=36, corner_radius=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        for label, command in {
            "Datei": self._menu_datei,
            "Ansicht": None,
            "Extras": None,
            "Hilfe": None,
        }.items():
            ctk.CTkButton(
                bar,
                text=label,
                width=72,
                height=30,
                fg_color="transparent",
                hover_color=("gray80", "gray30"),
                corner_radius=4,
                command=command,
            ).pack(side="left", padx=2, pady=3)

    def _menu_datei(self) -> None:
        pass

    def _build_tab_view(self) -> None:
        self._tab_view = ctk.CTkTabview(self, corner_radius=4)
        self._tab_view.pack(fill="both", expand=True, padx=6)

        # TR-Universum
        self._tab_view.add("TR-Universum")

        self._universe_tab = UniverseTab(
            self._tab_view.tab("TR-Universum")
        )
        self._universe_tab.pack(fill="both", expand=True)

        # High-Yield
        self._tab_view.add("High-Yield ≥10 %")

        self._high_yield_tab = HighYieldTab(
            self._tab_view.tab("High-Yield ≥10 %")
        )
        self._high_yield_tab.pack(fill="both", expand=True)

        # Analyse
        self._tab_view.add("Analyse")

        self._analyse_tab = AnalyseTab(
            self._tab_view.tab("Analyse")
        )
        self._analyse_tab.pack(fill="both", expand=True)

        # Watchlist
        self._tab_view.add("Watchlist")

        self._watchlist_tab = WatchlistTab(
            self._tab_view.tab("Watchlist")
        )
        self._watchlist_tab.pack(fill="both", expand=True)

        # Watchlist-Referenz weiterreichen
        self._universe_tab.set_watchlist_tab(self._watchlist_tab)
        self._high_yield_tab.set_watchlist_tab(self._watchlist_tab)

        # Portfolio
        self._tab_view.add("Portfolio")

        ctk.CTkLabel(
            self._tab_view.tab("Portfolio"),
            text="Portfolio — in Entwicklung",
            text_color=("gray50", "gray60"),
        ).pack(expand=True)

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=26, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            bar,
            text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._status_label.pack(side="left", padx=10)

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    def _load_last_run_summary(self) -> str:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT value FROM metadata WHERE key = 'last_auto_run'"
                ).fetchone()

            if not row:
                return ""

            data = json.loads(row[0])

            run_at = data.get("run_at", "")[:16].replace("T", " ")
            stats = data.get("stats", {})
            crossings = data.get("crossings", 0)

            return (
                f"Letzter Auto-Lauf: {run_at}  |  "
                f"{stats.get('updated', 0)} aktualisiert  |  "
                f"{crossings} Schwellwert-Änderung(en)"
            )

        except Exception:
            return ""

    def _startup_checks(self) -> None:
        summary = self._load_last_run_summary()

        if summary:
            self._set_status(summary)

        try:
            from db.dividend_repository import (
                get_unshown_threshold_crossings,
            )

            crossings = get_unshown_threshold_crossings()

        except Exception:
            logger.exception(
                "Fehler beim Laden der Threshold-Crossings."
            )
            return

        if crossings:
            self._open_threshold_popup()

    def _open_threshold_popup(self) -> None:
        from gui.widgets.threshold_crossing_popup import (
            ThresholdCrossingPopup,
        )

        ThresholdCrossingPopup(
            self,
            on_closed=self._on_threshold_popup_closed,
        )

    def _on_threshold_popup_closed(self) -> None:
        summary = self._load_last_run_summary()

        if summary:
            self._set_status(summary)

    def _on_close(self) -> None:
        self._save_geometry()
        self.destroy()