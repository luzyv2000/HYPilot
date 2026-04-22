# Dateiname:     gui/widgets/instrument_table.py
# Version:       2026-04-22
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/instrument_table.py

Scrollbare, sortierbare Treeview-Tabelle für Finanzinstrumente.

Spalten:
  flag     — Multifunktionsspalte (leer, Infrastruktur für spätere Features)
  name     — Wertpapiername
  isin_wkn — ISIN und WKN (zwei Zeilen via \\n, rowheight=40)
  div      — Dividendenrendite in %

Threading:
  Datenladen läuft in threading.Thread.
  GUI-Updates ausschließlich via self.after() + queue.Queue.
  Niemals direkte Widget-Manipulation aus Hintergrund-Threads.
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable

import customtkinter as ctk

logger = logging.getLogger(__name__)

# Typ für eine Tabellenzeile: (flag, name, isin_wkn, div_display, isin_raw)
# isin_raw wird nicht angezeigt, aber für spätere Aktionen benötigt
Row = tuple[str, str, str, str, str]


class InstrumentTable(ctk.CTkFrame):
    """
    Wiederverwendbare Tabellenkomponente mit Suche, Sortierung
    und Hintergrund-Datenladen.
    """

    _COL_FLAG = "flag"
    _COL_NAME = "name"
    _COL_ISIN = "isin_wkn"
    _COL_DIV  = "div"
    _COLUMNS  = (_COL_FLAG, _COL_NAME, _COL_ISIN, _COL_DIV)

    _COL_CONFIG: dict[str, dict[str, Any]] = {
        _COL_FLAG: {
            "heading": "", "width": 44, "minwidth": 44,
            "stretch": False, "anchor": "center",
        },
        _COL_NAME: {
            "heading": "Wertpapier", "width": 420, "minwidth": 160,
            "stretch": True, "anchor": "w",
        },
        _COL_ISIN: {
            "heading": "ISIN / WKN", "width": 190, "minwidth": 130,
            "stretch": False, "anchor": "w",
        },
        _COL_DIV: {
            "heading": "Div %", "width": 80, "minwidth": 60,
            "stretch": False, "anchor": "e",
        },
    }

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, **kwargs)

        self._all_rows: list[Row] = []
        self._filtered_rows: list[Row] = []
        self._sort_col: str = self._COL_NAME
        self._sort_asc: bool = True
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_change)
        self._search_after_id: str | None = None
        self._data_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self._build()
        self.after(100, self._process_queue)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_search_bar()
        self._build_tree()
        self._apply_treeview_style()

    def _build_search_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(bar, text="🔍  Suche:").grid(
            row=0, column=0, padx=(0, 6), sticky="w"
        )
        ctk.CTkEntry(
            bar,
            textvariable=self._search_var,
            placeholder_text="Name, ISIN oder WKN …",
        ).grid(row=0, column=1, sticky="ew")

        self._status_label = ctk.CTkLabel(
            bar,
            text="",
            text_color=("gray50", "gray60"),
            width=140,
            anchor="e",
        )
        self._status_label.grid(row=0, column=2, padx=(10, 0), sticky="e")

    def _build_tree(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            outer,
            columns=self._COLUMNS,
            show="headings",
            selectmode="browse",
        )

        vsb = ttk.Scrollbar(outer, orient="vertical",   command=self._tree.yview)
        hsb = ttk.Scrollbar(outer, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        for col, cfg in self._COL_CONFIG.items():
            self._tree.column(
                col,
                width=cfg["width"],
                minwidth=cfg["minwidth"],
                stretch=cfg["stretch"],
                anchor=cfg["anchor"],
            )
            self._tree.heading(
                col,
                text=cfg["heading"],
                command=lambda c=col: self._sort_by(c),
            )

    def _apply_treeview_style(self) -> None:
        """
        Passt Treeview-Farben an CTk-Erscheinungsbild an.
        Wird beim Start einmalig aufgerufen.
        """
        mode = ctk.get_appearance_mode()
        dark = mode == "Dark"

        bg      = "#2b2b2b" if dark else "#f9f9f9"
        fg      = "#e0e0e0" if dark else "#1a1a1a"
        sel_bg  = "#1f6aa5"
        head_bg = "#1c1c1c" if dark else "#dcdcdc"
        head_fg = "#c8c8c8" if dark else "#333333"
        odd_bg  = "#323232" if dark else "#ffffff"
        even_bg = "#2b2b2b" if dark else "#f0f0f0"
        div_fg  = "#66bb6a" if dark else "#2e7d32"

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "HYPilot.Treeview",
            background=bg,
            foreground=fg,
            fieldbackground=bg,
            borderwidth=0,
            rowheight=40,
        )
        style.configure(
            "HYPilot.Treeview.Heading",
            background=head_bg,
            foreground=head_fg,
            relief="flat",
            borderwidth=1,
            padding=(4, 4),
        )
        style.map(
            "HYPilot.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", "#ffffff")],
        )

        self._tree.configure(style="HYPilot.Treeview")
        self._tree.tag_configure("odd",     background=odd_bg,  foreground=fg)
        self._tree.tag_configure("even",    background=even_bg, foreground=fg)
        self._tree.tag_configure("has_div", foreground=div_fg)

    # ── Datenladen (threadsicher) ─────────────────────────────────────────────

    def load_data(self, loader_fn: Callable[[], list[Row]]) -> None:
        """
        Startet Datenladen in Hintergrund-Thread.

        Args:
            loader_fn: Callable ohne Argumente → list[Row]
        """
        self._set_status("Lade …")
        threading.Thread(
            target=self._worker,
            args=(loader_fn,),
            daemon=True,
        ).start()

    def _worker(self, loader_fn: Callable[[], list[Row]]) -> None:
        try:
            rows = loader_fn()
            self._data_queue.put(("data", rows))
        except Exception as exc:
            logger.exception("Fehler beim Laden der Tabellendaten.")
            self._data_queue.put(("error", str(exc)))

    def _process_queue(self) -> None:
        """
        Verarbeitet Nachrichten aus dem Worker-Thread.
        Läuft ausschließlich im Hauptthread via self.after().
        """
        try:
            while True:
                kind, payload = self._data_queue.get_nowait()
                if kind == "data":
                    self._all_rows = payload
                    self._apply_filter(self._search_var.get())
                elif kind == "error":
                    self._set_status(f"⚠ Fehler: {payload}")
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    # ── Anzeige ───────────────────────────────────────────────────────────────

    def _populate(self, rows: list[Row]) -> None:
        """Füllt Treeview. Darf nur im Hauptthread aufgerufen werden."""
        self._tree.delete(*self._tree.get_children())

        for idx, row in enumerate(rows):
            tags: list[str] = ["even" if idx % 2 == 0 else "odd"]
            # Grüne Hervorhebung wenn Dividendenwert vorhanden
            if row[3] and row[3] != "—":
                tags.append("has_div")
            # row[4] (isin_raw) ist interner Wert, nicht anzeigen
            self._tree.insert("", "end", values=row[:4], tags=tags,
                               iid=row[4])  # ISIN als Item-ID

        self._set_status(f"{len(rows):,} Einträge")

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    # ── Suche ─────────────────────────────────────────────────────────────────

    def _on_search_change(self, *_: Any) -> None:
        if self._search_after_id:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(
            300, lambda: self._apply_filter(self._search_var.get())
        )

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if not q:
            self._filtered_rows = list(self._all_rows)
        else:
            self._filtered_rows = [
                row for row in self._all_rows
                if q in row[1].lower() or q in row[2].lower()
            ]
        self._sort_rows()
        self._populate(self._filtered_rows)

    # ── Sortierung ────────────────────────────────────────────────────────────

    def _sort_by(self, col: str) -> None:
        if col == self._COL_FLAG:
            return  # Multifunktionsspalte ist nicht sortierbar
        self._sort_asc = not self._sort_asc if self._sort_col == col else True
        self._sort_col = col
        self._sort_rows()
        self._populate(self._filtered_rows)
        self._update_headings()

    def _sort_rows(self) -> None:
        idx = self._COLUMNS.index(self._sort_col)

        def key(row: Row) -> Any:
            val = row[idx]
            if self._sort_col == self._COL_DIV:
                try:
                    return float(val.replace("%", "").strip())
                except (ValueError, AttributeError):
                    return -9999.0
            return val.lower() if isinstance(val, str) else val

        self._filtered_rows.sort(key=key, reverse=not self._sort_asc)

    def _update_headings(self) -> None:
        for col, cfg in self._COL_CONFIG.items():
            if col == self._COL_FLAG:
                continue
            suffix = ""
            if col == self._sort_col:
                suffix = "  ▲" if self._sort_asc else "  ▼"
            self._tree.heading(col, text=cfg["heading"] + suffix)

    # ── Öffentliche Hilfsmethode ──────────────────────────────────────────────

    def get_selected_isin(self) -> str | None:
        """Gibt die ISIN des aktuell selektierten Eintrags zurück."""
        selection = self._tree.selection()
        return selection[0] if selection else None
