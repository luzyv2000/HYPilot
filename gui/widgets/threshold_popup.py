# Dateiname:     gui/widgets/threshold_popup.py
# Version:       2026-04-23-P3pp
# Abhängigkeiten (intern): db.dividend_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/threshold_popup.py

Popup-Fenster für 10%-Schwellwert-Überschreitungen.

Öffnet sich automatisch beim GUI-Start wenn neue Überschreitungen
vorhanden sind. Zwei Gruppen: "Neu über 10%" und "Neu unter 10%".
Nach dem Schließen werden alle gezeigten Einträge markiert.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from db.dividend_repository import (
    get_unshown_threshold_crossings,
    mark_crossings_shown,
)

logger = logging.getLogger(__name__)


class ThresholdPopup(ctk.CTkToplevel):
    """
    Zeigt Schwellwert-Überschreitungen seit dem letzten Start.

    Args:
        master:    Eltern-Widget
        on_closed: Callback nach Schließen
    """

    def __init__(
        self,
        master: ctk.CTk,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)

        self._on_closed  = on_closed
        self._crossings  = get_unshown_threshold_crossings()
        self._shown_ids  = [c["id"] for c in self._crossings]

        self.title("⚠  Dividenden-Änderungen — 10%-Schwellwert")
        self.geometry("860x540")
        self.minsize(640, 360)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        up_count   = sum(1 for c in self._crossings if c["direction"] == "up")
        down_count = sum(1 for c in self._crossings if c["direction"] == "down")

        ctk.CTkLabel(
            self,
            text=(
                f"Seit dem letzten Start: "
                f"{up_count} Instrument(e) neu über 10% ▲  |  "
                f"{down_count} Instrument(e) neu unter 10% ▼"
            ),
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

        # Treeview
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        cols = ("direction", "isin", "name", "old", "new")
        self._tree = ttk.Treeview(
            outer, columns=cols, show="headings", selectmode="browse"
        )

        self._tree.column("direction", width=60,  anchor="center")
        self._tree.column("isin",      width=140, anchor="w")
        self._tree.column("name",      width=300, anchor="w", stretch=True)
        self._tree.column("old",       width=90,  anchor="e")
        self._tree.column("new",       width=90,  anchor="e")

        self._tree.heading("direction", text="")
        self._tree.heading("isin",      text="ISIN")
        self._tree.heading("name",      text="Wertpapier")
        self._tree.heading("old",       text="Alt")
        self._tree.heading("new",       text="Neu")

        vsb = ttk.Scrollbar(outer, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Tags für Farben
        self._tree.tag_configure("up",   foreground="#2e7d32")
        self._tree.tag_configure("down", foreground="#c62828")

        self._populate()

        # Button-Leiste
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(
            row=2, column=0, padx=12, pady=(0, 14), sticky="ew"
        )
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            btn_frame,
            text="Schließen markiert alle Einträge als gesehen.",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=11),
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            btn_frame,
            text="Schließen",
            width=120,
            command=self._close,
        ).grid(row=0, column=1)

        self.bind("<Escape>", lambda _: self._close())

    def _populate(self) -> None:
        # Erst "up" (aufsteigend nach Rendite), dann "down"
        sorted_crossings = sorted(
            self._crossings,
            key=lambda c: (
                0 if c["direction"] == "up" else 1,
                -(c["yield_bps_new"] or 0),
            ),
        )
        for c in sorted_crossings:
            arrow   = "▲ über 10%" if c["direction"] == "up" else "▼ unter 10%"
            old_pct = (
                f"{c['yield_bps_old']/100:.2f} %"
                if c["yield_bps_old"] is not None else "—"
            )
            new_pct = f"{c['yield_bps_new']/100:.2f} %"

            self._tree.insert(
                "", "end",
                values=(arrow, c["isin"], c["display_name"], old_pct, new_pct),
                tags=(c["direction"],),
            )

    def _close(self) -> None:
        mark_crossings_shown(self._shown_ids)
        if self._on_closed:
            self._on_closed()
        self.destroy()
