# Dateiname:     gui/widgets/threshold_crossing_popup.py
# Version:       2026-05-04
# Abhängigkeiten (intern): db.dividend_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/threshold_crossing_popup.py

Popup-Fenster für 10%-Schwellwert-Überschreitungen.

Öffnet sich beim GUI-Start wenn ungesehene Crossings vorhanden sind.
Zwei Gruppen: "Neu über 10% ▲" (grün) und "Neu unter 10% ▼" (rot).
mark_crossings_shown() wird erst beim Schließen aufgerufen.
"""

from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from db.dividend_repository import get_unshown_threshold_crossings, mark_crossings_shown

logger = logging.getLogger(__name__)


class ThresholdCrossingPopup(ctk.CTkToplevel):
    """
    Zeigt Schwellwert-Überschreitungen seit dem letzten GUI-Start.

    Args:
        master:    Eltern-Widget (HYPilotApp)
        on_closed: Optionaler Callback nach dem Schließen
    """

    def __init__(
        self,
        master: ctk.CTk,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)

        self._on_closed = on_closed
        self._crossings = get_unshown_threshold_crossings()
        self._ids_to_mark = [c["id"] for c in self._crossings]

        self.title("⚠  Dividenden-Schwellwert-Überschreitungen")
        self.geometry("900x520")
        self.minsize(640, 360)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()

        logger.info(
            "ThresholdCrossingPopup: %d ungesehene Überschreitungen angezeigt.",
            len(self._crossings),
        )

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_treeview()
        self._build_footer()

    def _build_header(self) -> None:
        up_count   = sum(1 for c in self._crossings if c["direction"] == "up")
        down_count = sum(1 for c in self._crossings if c["direction"] == "down")

        text = (
            f"Seit dem letzten Start:  "
            f"{up_count} Instrument(e) neu über 10 % ▲  |  "
            f"{down_count} Instrument(e) neu unter 10 % ▼"
        )
        ctk.CTkLabel(
            self,
            text=text,
            font=ctk.CTkFont(size=13),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

    def _build_treeview(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 6))
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        cols = ("direction", "name", "isin", "yield_old", "yield_new", "detected")
        self._tree = ttk.Treeview(
            outer, columns=cols, show="headings", selectmode="browse"
        )

        # Spaltenbreiten
        self._tree.column("direction", width=110, anchor="center", stretch=False)
        self._tree.column("name",      width=260, anchor="w",      stretch=True)
        self._tree.column("isin",      width=130, anchor="w",      stretch=False)
        self._tree.column("yield_old", width=90,  anchor="e",      stretch=False)
        self._tree.column("yield_new", width=90,  anchor="e",      stretch=False)
        self._tree.column("detected",  width=150, anchor="center", stretch=False)

        # Spaltenüberschriften
        self._tree.heading("direction", text="Richtung")
        self._tree.heading("name",      text="Wertpapier")
        self._tree.heading("isin",      text="ISIN")
        self._tree.heading("yield_old", text="Rendite alt")
        self._tree.heading("yield_new", text="Rendite neu")
        self._tree.heading("detected",  text="Erkannt am")

        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Styling
        mode = ctk.get_appearance_mode()
        dark = mode == "Dark"
        bg      = "#2b2b2b" if dark else "#f9f9f9"
        fg      = "#e0e0e0" if dark else "#1a1a1a"
        head_bg = "#1c1c1c" if dark else "#dcdcdc"
        head_fg = "#c8c8c8" if dark else "#333333"

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Crossing.Treeview",
            background=bg, foreground=fg,
            fieldbackground=bg, borderwidth=0, rowheight=28,
        )
        style.configure(
            "Crossing.Treeview.Heading",
            background=head_bg, foreground=head_fg,
            relief="flat", borderwidth=1, padding=(4, 4),
        )
        style.map(
            "Crossing.Treeview",
            background=[("selected", "#1f6aa5")],
            foreground=[("selected", "#ffffff")],
        )
        self._tree.configure(style="Crossing.Treeview")

        # Farb-Tags: up = grün, down = rot
        up_fg   = "#66bb6a" if dark else "#1b5e20"
        down_fg = "#ef5350" if dark else "#b71c1c"
        self._tree.tag_configure("up",   foreground=up_fg)
        self._tree.tag_configure("down", foreground=down_fg)

        self._populate()

    def _build_footer(self) -> None:
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=2, column=0, padx=12, pady=(0, 14), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Alle Einträge werden beim Schließen als gesehen markiert.",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            frame,
            text="Schließen",
            width=120,
            command=self._close,
        ).grid(row=0, column=1)

        self.bind("<Escape>", lambda _: self._close())

    # ── Befüllen ──────────────────────────────────────────────────────────────

    def _populate(self) -> None:
        # Sortierung: erst 'up' (aufsteigend nach Rendite), dann 'down'
        sorted_crossings = sorted(
            self._crossings,
            key=lambda c: (
                0 if c["direction"] == "up" else 1,
                -(c["yield_bps_new"] or 0),
            ),
        )

        for crossing in sorted_crossings:
            direction = crossing["direction"]
            arrow     = "▲  Neu über 10 %" if direction == "up" else "▼  Neu unter 10 %"

            old_bps = crossing["yield_bps_old"]
            new_bps = crossing["yield_bps_new"]
            old_str = f"{old_bps / 100:.2f} %" if old_bps is not None else "—"
            new_str = f"{new_bps / 100:.2f} %"

            # Datum kürzen: nur YYYY-MM-DD HH:MM
            detected_raw = crossing.get("detected_at", "")
            detected_str = detected_raw[:16].replace("T", "  ") if detected_raw else "—"

            self._tree.insert(
                "", "end",
                values=(
                    arrow,
                    crossing.get("display_name", crossing["isin"]),
                    crossing["isin"],
                    old_str,
                    new_str,
                    detected_str,
                ),
                tags=(direction,),
            )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _close(self) -> None:
        """Markiert alle gezeigten Einträge als gesehen und schließt."""
        mark_crossings_shown(self._ids_to_mark)
        logger.info(
            "ThresholdCrossingPopup: %d Einträge als gesehen markiert.",
            len(self._ids_to_mark),
        )
        if self._on_closed:
            self._on_closed()
        self.destroy()