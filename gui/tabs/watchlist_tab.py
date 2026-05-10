# Dateiname:     gui/tabs/watchlist_tab.py
# Version:       2026-05-10 
# Abhängigkeiten (intern): db.watchlist_repository,
#                          gui.widgets.instrument_table,
#                          gui.widgets.score_detail_panel,
#                          analysis.scorer, db.dividend_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/watchlist_tab.py

Watchlist-Tab — persönlich markierte Instrumente.

Funktionen:
  - Anzeige aller Watchlist-Einträge mit Score + Rendite
  - Entfernen via Toolbar-Button (selektiertes Instrument)
  - Notizfeld: Freitext pro ISIN (Inline-Bearbeitung)
  - Score-Detail-Panel bei Selektion
  - Instrument-Anzahl in der Toolbar
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Any

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from gui.widgets.score_detail_panel import ScoreDetailPanel
from db.watchlist_repository import (
    get_watchlist,
    remove_from_watchlist,
    update_notes,
    WatchlistEntry,
)

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_RATING_SHORT = {"STRONG_BUY": "SB", "BUY": "B", "WATCH": "W", "REJECT": "R"}


def _format_div(yield_bps: int | None) -> str:
    return "—" if yield_bps is None else f"{yield_bps / 100.0:.2f} %"


def _load_watchlist_rows() -> list[tuple]:
    """
    Lädt Watchlist-Einträge mit Scoring.
    Gibt Liste von (isin, name, wkn, yield, score, notes, added_at) zurück.
    Läuft im Hintergrund-Thread.
    """
    from analysis.scorer import score_dividend_snapshot
    from core.dividend_source import DividendSnapshot
    from db.dividend_repository import get_growth_metrics_bulk, get_snapshot

    entries    = get_watchlist()
    isins      = [e.isin for e in entries]
    growth_map = get_growth_metrics_bulk(db_path=DB_PATH) if isins else {}

    rows = []
    for entry in entries:
        yield_str    = "—"
        score_str    = "—"
        score_rating = None

        try:
            snapshot = get_snapshot(entry.isin, db_path=DB_PATH)
            if snapshot is not None:
                metrics   = growth_map.get(entry.isin)
                score     = score_dividend_snapshot(snapshot, growth_metrics=metrics)
                yield_str = _format_div(snapshot.yield_bps)
                short     = _RATING_SHORT.get(score.rating, "?")
                score_str = f"{score.total} {short}"
                score_rating = score.rating
        except Exception:
            logger.debug("Scoring fehlgeschlagen für %s.", entry.isin)

        # added_at: nur Datum anzeigen
        added_display = entry.added_at[:10] if entry.added_at else "—"

        rows.append((
            entry.isin,
            entry.name,
            entry.wkn or "",
            yield_str,
            score_str,
            score_rating or "",
            entry.notes,
            added_display,
        ))

    return rows


class WatchlistTab(ctk.CTkFrame):
    """Watchlist-Tab."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._rows: list[tuple] = []

        self._build_toolbar()
        self._build_table()
        self._build_notes_bar()
        self._build_detail_panel()

        self.after(100, self._process_queue)
        self._start_load()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ctk.CTkButton(
            bar, text="↻  Aktualisieren", width=140,
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        self._remove_btn = ctk.CTkButton(
            bar,
            text="✕  Entfernen",
            width=130,
            fg_color=("firebrick3", "#8b0000"),
            hover_color=("firebrick4", "#6b0000"),
            state="disabled",
            command=self._remove_selected,
        )
        self._remove_btn.pack(side="left", padx=(0, 8))

        self._count_label = ctk.CTkLabel(
            bar, text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._count_label.pack(side="left", padx=(8, 0))

    def _build_table(self) -> None:
        outer = ctk.CTkFrame(self, fg_color="transparent")
        outer.grid(row=2, column=0, sticky="nsew", padx=8, pady=(8, 0))
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        dark    = ctk.get_appearance_mode() == "Dark"
        bg      = "#2b2b2b" if dark else "#f9f9f9"
        fg      = "#e0e0e0" if dark else "#1a1a1a"
        head_bg = "#1c1c1c" if dark else "#dcdcdc"
        head_fg = "#c8c8c8" if dark else "#333333"
        sel_bg  = "#1f6aa5"

        cols = ("name", "isin_wkn", "yield", "score", "notes", "added")
        self._tree = ttk.Treeview(
            outer, columns=cols, show="headings",
            selectmode="browse",
        )

        self._tree.column("name",    width=320, anchor="w",      stretch=True)
        self._tree.column("isin_wkn",width=160, anchor="w",      stretch=False)
        self._tree.column("yield",   width=80,  anchor="e",      stretch=False)
        self._tree.column("score",   width=80,  anchor="center", stretch=False)
        self._tree.column("notes",   width=200, anchor="w",      stretch=True)
        self._tree.column("added",   width=100, anchor="center", stretch=False)

        self._tree.heading("name",    text="Wertpapier")
        self._tree.heading("isin_wkn",text="ISIN / WKN")
        self._tree.heading("yield",   text="Rendite")
        self._tree.heading("score",   text="Score")
        self._tree.heading("notes",   text="Notiz")
        self._tree.heading("added",   text="Hinzugefügt")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Watchlist.Treeview",
            background=bg, foreground=fg,
            fieldbackground=bg, borderwidth=0, rowheight=32,
        )
        style.configure(
            "Watchlist.Treeview.Heading",
            background=head_bg, foreground=head_fg,
            relief="flat", borderwidth=1, padding=(4, 4),
        )
        style.map(
            "Watchlist.Treeview",
            background=[("selected", sel_bg)],
            foreground=[("selected", "#ffffff")],
        )
        self._tree.configure(style="Watchlist.Treeview")

        sb_fg  = "#66bb6a" if dark else "#1b5e20"
        buy_fg = "#aed581" if dark else "#558b2f"
        w_fg   = "#ffb74d" if dark else "#e65100"
        r_fg   = "#ef5350" if dark else "#b71c1c"
        self._tree.tag_configure("STRONG_BUY", foreground=sb_fg)
        self._tree.tag_configure("BUY",        foreground=buy_fg)
        self._tree.tag_configure("WATCH",      foreground=w_fg)
        self._tree.tag_configure("REJECT",     foreground=r_fg)

        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>",         self._on_double_click)

    def _build_notes_bar(self) -> None:
        """Inline-Notizbearbeitung unterhalb der Tabelle."""
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 0))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="Notiz:",
            font=ctk.CTkFont(size=11),
            anchor="w", width=50,
        ).grid(row=0, column=0, sticky="w", padx=(0, 6))

        self._notes_entry = ctk.CTkEntry(
            bar,
            placeholder_text="Notiz für ausgewähltes Instrument …",
            state="disabled",
        )
        self._notes_entry.grid(row=0, column=1, sticky="ew")

        self._notes_save_btn = ctk.CTkButton(
            bar, text="Speichern", width=100,
            state="disabled",
            command=self._save_notes,
        )
        self._notes_save_btn.grid(row=0, column=2, padx=(6, 0))

    def _build_detail_panel(self) -> None:
        ctk.CTkFrame(
            self, height=1, fg_color=("gray75", "gray30")
        ).grid(row=4, column=0, sticky="ew", padx=0)
        self._detail_panel = ScoreDetailPanel(self, height=160)
        self._detail_panel.grid(row=5, column=0, sticky="ew", padx=0, pady=0)
        self._detail_panel.grid_propagate(False)

    # ── Datenladen ────────────────────────────────────────────────────────────

    def _start_load(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            rows = _load_watchlist_rows()
            self._queue.put(("data", rows))
        except Exception as exc:
            logger.exception("Fehler beim Laden der Watchlist.")
            self._queue.put(("error", str(exc)))

    def _process_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "data":
                    self._populate(payload)
                elif kind == "error":
                    self._count_label.configure(text=f"⚠ {payload}")
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    # ── Tabelle befüllen ──────────────────────────────────────────────────────

    def _populate(self, rows: list[tuple]) -> None:
        self._rows = rows
        self._tree.delete(*self._tree.get_children())

        for row in rows:
            isin, name, wkn, yield_str, score_str, rating, notes, added = row
            isin_wkn = f"{isin}\n{wkn}" if wkn else isin
            tags = (rating,) if rating else ()
            self._tree.insert(
                "", "end",
                iid=isin,
                values=(
                    name[:50] + "…" if len(name) > 50 else name,
                    isin_wkn,
                    yield_str,
                    score_str,
                    notes[:60] + "…" if len(notes) > 60 else notes,
                    added,
                ),
                tags=tags,
            )

        count = len(rows)
        self._count_label.configure(
            text=f"{count} Instrument{'e' if count != 1 else ''} auf der Watchlist"
        )
        self._remove_btn.configure(state="disabled")
        self._notes_entry.configure(state="disabled")
        self._notes_save_btn.configure(state="disabled")

    # ── Selektion ─────────────────────────────────────────────────────────────

    def _get_selected_isin(self) -> str | None:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _on_select(self, _event: tk.Event) -> None:
        isin = self._get_selected_isin()
        if not isin:
            return

        self._remove_btn.configure(state="normal")
        self._detail_panel.update(isin)

        # Notizfeld befüllen
        row = next((r for r in self._rows if r[0] == isin), None)
        if row:
            self._notes_entry.configure(state="normal")
            self._notes_entry.delete(0, "end")
            self._notes_entry.insert(0, row[6])  # notes
            self._notes_save_btn.configure(state="normal")

    def _on_double_click(self, event: tk.Event) -> None:
        """Doppelklick fokussiert das Notizfeld."""
        if self._get_selected_isin():
            self._notes_entry.focus_set()

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _remove_selected(self) -> None:
        isin = self._get_selected_isin()
        if not isin:
            return
        remove_from_watchlist(isin, db_path=DB_PATH)
        self._detail_panel.clear()
        self._refresh()

    def _save_notes(self) -> None:
        isin = self._get_selected_isin()
        if not isin:
            return
        notes = self._notes_entry.get().strip()
        update_notes(isin, notes, db_path=DB_PATH)
        logger.info("Notiz gespeichert: %s", isin)
        self._refresh()

    def _refresh(self) -> None:
        self._detail_panel.clear()
        self._start_load()

    # ── Öffentliche API (für andere Tabs) ────────────────────────────────────

    def reload(self) -> None:
        """Wird von UniverseTab/HighYieldTab nach Watchlist-Änderung aufgerufen."""
        self._start_load()