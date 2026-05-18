# Dateiname:     gui/widgets/pending_names_dialog.py
# Version:       2026-04-22-A-fix1
# Abhängigkeiten (intern): db.instrument_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/pending_names_dialog.py  —  Modaler Dialog für Namensänderungen.
Fix 2026-05-16: noqa F401 für tkinter as tk (wird für tk.TclError benötigt).
"""

from __future__ import annotations

import logging
import tkinter as tk  # noqa: F401  (tk.TclError in style.theme_use)
from tkinter import ttk
from typing import Callable

import customtkinter as ctk

from db.instrument_repository import (
    PendingNameChange,
    approve_name_change,
    get_pending_name_changes,
    reject_name_change,
)

logger = logging.getLogger(__name__)


class PendingNamesDialog(ctk.CTkToplevel):
    """
    Zeigt ausstehende Namensänderungen aus PDF-Import.

    Args:
        master:    Eltern-Widget
        on_closed: Callback wenn Dialog geschlossen wird
    """

    def __init__(
        self,
        master: ctk.CTk | ctk.CTkFrame,
        on_closed: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)

        self._on_closed    = on_closed
        self._pending: list[PendingNameChange] = []

        self.title("Ausstehende Namensänderungen")
        self.geometry("820x520")
        self.minsize(640, 360)
        self.grab_set()
        self.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._close)

        self._build()
        self._load()

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._info_label = ctk.CTkLabel(self, text="", anchor="w")
        self._info_label.grid(
            row=0, column=0, padx=16, pady=(14, 6), sticky="w"
        )

        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        cols = ("isin", "current", "pdf")
        self._tree = ttk.Treeview(outer, columns=cols, show="headings",
                                  selectmode="browse")

        self._tree.column("isin",    width=140, minwidth=120, anchor="w")
        self._tree.column("current", width=280, minwidth=160, anchor="w",
                          stretch=True)
        self._tree.column("pdf",     width=280, minwidth=160, anchor="w",
                          stretch=True)

        self._tree.heading("isin",    text="ISIN")
        self._tree.heading("current", text="Aktueller Name")
        self._tree.heading("pdf",     text="Neuer Name (PDF)")

        vsb = ttk.Scrollbar(outer, orient="vertical",
                             command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=2, column=0, padx=12, pady=(0, 14), sticky="ew")
        btn_frame.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="✓  Alle übernehmen",
            width=160,
            fg_color=("green4", "#2d6a2d"),
            hover_color=("green3", "#3a8a3a"),
            command=self._approve_all,
        ).grid(row=0, column=0, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="✗  Alle ablehnen",
            width=160,
            fg_color=("firebrick3", "#7a1a1a"),
            hover_color=("firebrick4", "#5a1010"),
            command=self._reject_all,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="✓  Auswahl übernehmen",
            width=180,
            command=self._approve_selected,
        ).grid(row=0, column=3, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="✗  Auswahl ablehnen",
            width=180,
            fg_color="transparent",
            border_width=1,
            command=self._reject_selected,
        ).grid(row=0, column=4, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Schließen",
            width=110,
            fg_color="transparent",
            border_width=1,
            command=self._close,
        ).grid(row=0, column=5)

        self.bind("<Escape>", lambda _: self._close())

    def _load(self) -> None:
        self._pending = get_pending_name_changes()
        self._tree.delete(*self._tree.get_children())

        for p in self._pending:
            self._tree.insert(
                "", "end",
                iid=str(p.id),
                values=(p.isin, p.name_current, p.name_pdf),
            )

        count = len(self._pending)
        self._info_label.configure(
            text=f"{count} ausstehende Namensänderung(en) aus PDF-Import"
        )

    def _approve_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        for iid in sel:
            approve_name_change(int(iid))
        self._load()

    def _reject_selected(self) -> None:
        sel = self._tree.selection()
        if not sel:
            return
        for iid in sel:
            reject_name_change(int(iid))
        self._load()

    def _approve_all(self) -> None:
        for p in self._pending:
            approve_name_change(p.id)
        self._load()

    def _reject_all(self) -> None:
        for p in self._pending:
            reject_name_change(p.id)
        self._load()

    def _close(self) -> None:
        if self._on_closed:
            self._on_closed()
        self.destroy()
