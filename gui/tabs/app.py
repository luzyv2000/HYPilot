# Dateiname:     gui/app.py
# Version:       2026-04-22
# Abhängigkeiten (intern): gui.tabs.universe_tab
# Abhängigkeiten (extern): customtkinter
"""
gui/app.py

HYPilot Hauptfenster.

Fenstergröße wird in der SQLite-Tabelle metadata gespeichert
und beim nächsten Start wiederhergestellt.

Menüleiste: Windows-ähnliche Leiste via CTkFrame + CTkButton.
Tabs:       CTkTabview mit sortier-/aktivierbaren Reitern.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import customtkinter as ctk

from gui.tabs.universe_tab import UniverseTab

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")
_DEFAULT_GEOMETRY = "1400x900"
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

    # ── Geometrie ─────────────────────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT value FROM metadata WHERE key = ?", (_GEO_KEY,)
                ).fetchone()
            self.geometry(row[0] if row else _DEFAULT_GEOMETRY)
        except sqlite3.Error:
            self.geometry(_DEFAULT_GEOMETRY)

    def _save_geometry(self) -> None:
        try:
            geo = self.geometry()
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO metadata (key, value) VALUES (?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (_GEO_KEY, geo),
                )
                conn.commit()
        except sqlite3.Error:
            logger.warning("Fenstergeometrie konnte nicht gespeichert werden.")

    # ── Menüleiste ────────────────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        """Windows-ähnliche Menüleiste via CTkFrame."""
        bar = ctk.CTkFrame(self, height=36, corner_radius=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        menus = {
            "Datei":   self._menu_datei,
            "Ansicht": None,
            "Extras":  None,
            "Hilfe":   None,
        }

        for label, command in menus.items():
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
        """Datei-Menü — Platzhalter für spätere Implementierung."""
        pass

    # ── Tabs ──────────────────────────────────────────────────────────────────

    def _build_tab_view(self) -> None:
        tab_view = ctk.CTkTabview(self, corner_radius=4)
        tab_view.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Tab: TR-Universum
        tab_view.add("TR-Universum")
        UniverseTab(
            tab_view.tab("TR-Universum")
        ).pack(fill="both", expand=True)

        # Weitere Tabs (Platzhalter, werden später befüllt)
        for name in ("Analyse", "Watchlist", "Portfolio"):
            tab_view.add(name)
            ctk.CTkLabel(
                tab_view.tab(name),
                text=f"{name} — in Entwicklung",
                text_color=("gray50", "gray60"),
            ).pack(expand=True)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self._save_geometry()
        self.destroy()
