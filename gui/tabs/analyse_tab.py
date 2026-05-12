# Dateiname:     gui/tabs/analyse_tab.py
# Version:       2026-05-09
# Abhängigkeiten (intern): db.dividend_repository, analysis.scorer,
#                          analysis.rules
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/analyse_tab.py

Analyse-Tab mit drei Bereichen:

  1. Scoring-Verteilung  — Balkendiagramm STRONG_BUY/BUY/WATCH/REJECT
                           aufgeteilt nach Kategorie (ETF/STOCK/BOND/alle)
  2. Top-20 Score        — Instrumente mit höchstem Gesamtscore
  3. Wachstums-Highlights — stärkstes YoY-Dividendenwachstum (≥5%,
                           keine Kürzung in der Historie)

Alle Daten werden einmalig im Hintergrund-Thread geladen.
Kein Netzwerk-Call, kein yfinance — ausschließlich DB-Lesen + Scoring.

Architektur-Entscheidungen:
  - Balkendiagramm via tkinter Canvas (kein matplotlib/plotly nötig)
  - Daten-Lade-Thread gibt AnalyseData-Dataclass via Queue zurück
  - Drei Sektionen in einem CTkScrollableFrame — kein Tab-in-Tab
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

# ── Farbpalette ───────────────────────────────────────────────────────────────

_RATING_COLORS_DARK = {
    "STRONG_BUY": "#66bb6a",
    "BUY":        "#aed581",
    "WATCH":      "#ffb74d",
    "REJECT":     "#ef5350",
}
_RATING_COLORS_LIGHT = {
    "STRONG_BUY": "#1b5e20",
    "BUY":        "#558b2f",
    "WATCH":      "#e65100",
    "REJECT":     "#b71c1c",
}

_RATING_ORDER = ["STRONG_BUY", "BUY", "WATCH", "REJECT"]
_RATING_LABEL = {
    "STRONG_BUY": "STRONG BUY",
    "BUY":        "BUY",
    "WATCH":      "WATCH",
    "REJECT":     "REJECT",
}


# ── Datenmodell ───────────────────────────────────────────────────────────────

@dataclass
class TopEntry:
    """Ein Eintrag in der Top-20 oder Wachstums-Liste."""
    name:      str
    isin:      str
    score:     int
    rating:    str
    yield_pct: str   # z.B. "12.34 %"
    frequency: str   # z.B. "monthly"
    yoy_pct:   str   # z.B. "+7.2 %" oder "—"


@dataclass
class AnalyseData:
    """Alle Daten für den Analyse-Tab, einmal berechnet."""
    rating_counts: dict[str, int]             # {"STRONG_BUY": 42, ...}
    top20:         list[TopEntry]
    growth_top10:  list[TopEntry]
    total_scored:  int
    load_time_ms:  int


# ── Datenladen ────────────────────────────────────────────────────────────────

_QUERY_ALL = """
    SELECT
        COALESCE(i.name_override, i.name) AS display_name,
        i.isin,
        d.yield_bps,
        d.frequency,
        d.last_amount_micro,
        d.last_ex_date,
        d.currency,
        d.payout_ratio_bps,
        d.data_source
    FROM instruments i
    JOIN dividend_data d ON i.isin = d.isin
    WHERE d.yield_bps IS NOT NULL
"""


def _freq_display(freq: str | None) -> str:
    mapping = {
        "monthly":     "monatlich",
        "quarterly":   "quartalsw.",
        "semi_annual": "halbjährl.",
        "annual":      "jährlich",
        "irregular":   "unregel.",
    }
    return mapping.get(freq or "", "—")


def _load_analyse_data() -> AnalyseData:
    """
    Lädt und berechnet alle Analyse-Daten.
    Läuft im Hintergrund-Thread — kein GUI-Zugriff.
    """
    import time as _time
    t0 = _time.monotonic()

    from analysis.scorer import score_dividend_snapshot
    from core.dividend_source import DividendSnapshot
    from db.dividend_repository import get_growth_metrics_bulk

    growth_map = get_growth_metrics_bulk(db_path=DB_PATH)

    rating_counts: dict[str, int] = {r: 0 for r in _RATING_ORDER}
    all_entries:   list[TopEntry] = []

    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(_QUERY_ALL).fetchall()
    except sqlite3.Error:
        logger.exception("Datenbankfehler beim Laden der Analyse-Daten.")
        return AnalyseData({}, [], [], 0, 0)

    for row in rows:
        try:
            last_ex = (
                date.fromisoformat(row["last_ex_date"])
                if row["last_ex_date"] else None
            )
            snapshot = DividendSnapshot(
                isin=row["isin"],
                yield_bps=row["yield_bps"],
                frequency=row["frequency"],
                last_amount_micro=row["last_amount_micro"],
                last_ex_date=last_ex,
                currency=row["currency"] or "USD",
                payout_ratio_bps=row["payout_ratio_bps"],
                data_source=row["data_source"] or "yfinance",
            )
            metrics = growth_map.get(row["isin"])
            score   = score_dividend_snapshot(snapshot, growth_metrics=metrics)

            rating_counts[score.rating] = rating_counts.get(score.rating, 0) + 1

            # YoY-Wachstum formatieren
            yoy_str = "—"
            if metrics and metrics.yoy_growth is not None:
                pct = float(metrics.yoy_growth) * 100
                sign = "+" if pct >= 0 else ""
                yoy_str = f"{sign}{pct:.1f} %"

            yield_str = (
                f"{row['yield_bps'] / 100.0:.2f} %"
                if row["yield_bps"] else "—"
            )

            all_entries.append(TopEntry(
                name=row["display_name"],
                isin=row["isin"],
                score=score.total,
                rating=score.rating,
                yield_pct=yield_str,
                frequency=_freq_display(row["frequency"]),
                yoy_pct=yoy_str,
            ))

        except Exception:
            logger.debug("Scoring fehlgeschlagen für %s.", row["isin"])
            continue

    # Top-20 nach Gesamtscore
    top20 = sorted(all_entries, key=lambda e: e.score, reverse=True)[:20]

    # Wachstums-Top-10: ≥5% YoY, keine Kürzung, mind. 2 Jahre Daten
    growth_candidates = [
        e for e in all_entries
        if (
            growth_map.get(e.isin) is not None
            and growth_map[e.isin].yoy_growth is not None
            and growth_map[e.isin].yoy_growth >= Decimal("0.05")
            and not growth_map[e.isin].has_cut
            and growth_map[e.isin].years_of_data >= 2
        )
    ]
    growth_top10 = sorted(
        growth_candidates,
        key=lambda e: growth_map[e.isin].yoy_growth or Decimal("0"),
        reverse=True,
    )[:10]

    elapsed_ms = int((_time.monotonic() - t0) * 1000)

    logger.info(
        "Analyse: %d Instrumente bewertet in %d ms. "
        "Verteilung: SB=%d B=%d W=%d R=%d",
        len(all_entries), elapsed_ms,
        rating_counts.get("STRONG_BUY", 0),
        rating_counts.get("BUY", 0),
        rating_counts.get("WATCH", 0),
        rating_counts.get("REJECT", 0),
    )

    return AnalyseData(
        rating_counts=rating_counts,
        top20=top20,
        growth_top10=growth_top10,
        total_scored=len(all_entries),
        load_time_ms=elapsed_ms,
    )


# ── Balkendiagramm ────────────────────────────────────────────────────────────

class _RatingChart(ctk.CTkFrame):
    """
    Einfaches horizontales Balkendiagramm via tkinter Canvas.
    Keine externen Bibliotheken nötig.
    """

    _BAR_HEIGHT  = 32
    _BAR_GAP     = 12
    _LABEL_WIDTH = 120
    _COUNT_WIDTH = 60
    _PADDING     = 16

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color=("gray92", "gray16"), **kwargs)
        self._canvas = tk.Canvas(
            self,
            bg="#292929" if ctk.get_appearance_mode() == "Dark" else "#f0f0f0",
            highlightthickness=0,
        )
        self._canvas.pack(fill="both", expand=True, padx=8, pady=8)

    def render(self, rating_counts: dict[str, int], total: int) -> None:
        """Zeichnet die Balken für die gegebene Verteilung."""
        self._canvas.delete("all")
        if total == 0:
            self._canvas.create_text(
                100, 40, text="Keine Daten", fill="gray", font=("", 11)
            )
            return

        dark   = ctk.get_appearance_mode() == "Dark"
        colors = _RATING_COLORS_DARK if dark else _RATING_COLORS_LIGHT
        fg     = "#e0e0e0" if dark else "#1a1a1a"
        bg     = "#292929" if dark else "#f0f0f0"
        self._canvas.configure(bg=bg)

        max_count  = max(rating_counts.values()) or 1
        canvas_w   = self._canvas.winfo_width() or 600
        bar_max_w  = canvas_w - self._LABEL_WIDTH - self._COUNT_WIDTH - self._PADDING * 2

        y = self._PADDING
        for rating in _RATING_ORDER:
            count = rating_counts.get(rating, 0)
            bar_w = int(bar_max_w * count / max_count) if max_count > 0 else 0

            # Label
            self._canvas.create_text(
                self._PADDING,
                y + self._BAR_HEIGHT // 2,
                text=_RATING_LABEL[rating],
                anchor="w",
                fill=fg,
                font=("", 10, "bold"),
            )

            # Balken
            x0 = self._PADDING + self._LABEL_WIDTH
            x1 = x0 + max(bar_w, 4)
            self._canvas.create_rectangle(
                x0, y, x1, y + self._BAR_HEIGHT,
                fill=colors[rating],
                outline="",
            )

            # Anzahl + Prozent
            pct = count / total * 100 if total > 0 else 0
            self._canvas.create_text(
                x1 + 8,
                y + self._BAR_HEIGHT // 2,
                text=f"{count} ({pct:.0f}%)",
                anchor="w",
                fill=fg,
                font=("", 10),
            )

            y += self._BAR_HEIGHT + self._BAR_GAP

        # Canvas-Höhe anpassen
        needed_h = y + self._PADDING
        self._canvas.configure(height=needed_h)


# ── Tabellen-Widget ───────────────────────────────────────────────────────────

def _build_entry_table(
    master: Any,
    columns: list[tuple[str, str, int, str]],   # (col_id, heading, width, anchor)
) -> ttk.Treeview:
    """Erstellt ein einheitliches Treeview für Top-Listen."""
    dark    = ctk.get_appearance_mode() == "Dark"
    bg      = "#2b2b2b" if dark else "#f9f9f9"
    fg      = "#e0e0e0" if dark else "#1a1a1a"
    head_bg = "#1c1c1c" if dark else "#dcdcdc"
    head_fg = "#c8c8c8" if dark else "#333333"
    sel_bg  = "#1f6aa5"

    col_ids = [c[0] for c in columns]
    tree = ttk.Treeview(
        master, columns=col_ids, show="headings",
        selectmode="browse", height=10,
    )

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style_name = f"Analyse{id(tree)}.Treeview"
    style.configure(
        style_name,
        background=bg, foreground=fg, fieldbackground=bg,
        borderwidth=0, rowheight=26,
    )
    style.configure(
        f"{style_name}.Heading",
        background=head_bg, foreground=head_fg,
        relief="flat", borderwidth=1, padding=(4, 3),
    )
    style.map(
        style_name,
        background=[("selected", sel_bg)],
        foreground=[("selected", "#ffffff")],
    )
    tree.configure(style=style_name)

    for col_id, heading, width, anchor in columns:
        tree.column(col_id, width=width, anchor=anchor, stretch=False)
        tree.heading(col_id, text=heading)

    # Rating-Farben
    sb_fg  = "#66bb6a" if dark else "#1b5e20"
    buy_fg = "#aed581" if dark else "#558b2f"
    w_fg   = "#ffb74d" if dark else "#e65100"
    r_fg   = "#ef5350" if dark else "#b71c1c"
    tree.tag_configure("STRONG_BUY", foreground=sb_fg)
    tree.tag_configure("BUY",        foreground=buy_fg)
    tree.tag_configure("WATCH",      foreground=w_fg)
    tree.tag_configure("REJECT",     foreground=r_fg)

    return tree


# ── Hauptklasse ───────────────────────────────────────────────────────────────

class AnalyseTab(ctk.CTkFrame):
    """Analyse-Tab mit Scoring-Verteilung, Top-20 und Wachstums-Highlights."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._data: AnalyseData | None = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_toolbar()
        self._build_content()

        self.after(100, self._process_queue)
        self._start_load()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ctk.CTkButton(
            bar, text="↻  Aktualisieren", width=140,
            command=self._start_load,
        ).pack(side="left", padx=(0, 8))

        self._status_label = ctk.CTkLabel(
            bar, text="Lade …",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._status_label.pack(side="left", padx=(8, 0))

    def _build_content(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=0, pady=(8, 0))
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll

        # ── Sektion 1: Scoring-Verteilung ─────────────────────────────────────
        self._build_section_header(scroll, 0, "📊  Scoring-Verteilung")
        self._chart = _RatingChart(scroll, height=200)
        self._chart.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 16))

        # ── Sektion 2: Top-20 Score ────────────────────────────────────────────
        self._build_section_header(scroll, 2, "🏆  Top-20 nach Gesamtscore")

        top20_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        top20_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 16))
        top20_frame.grid_columnconfigure(0, weight=1)

        self._top20_tree = _build_entry_table(
            top20_frame,
            [
                ("rank",   "#",          36,  "center"),
                ("name",   "Wertpapier", 320, "w"),
                ("score",  "Score",       70, "center"),
                ("rating", "Rating",      90, "center"),
                ("yield",  "Rendite",     80, "e"),
                ("freq",   "Frequenz",    90, "center"),
            ],
        )
        vsb = ttk.Scrollbar(
            top20_frame, orient="vertical", command=self._top20_tree.yview
        )
        self._top20_tree.configure(yscrollcommand=vsb.set)
        self._top20_tree.grid(row=0, column=0, sticky="ew")
        vsb.grid(row=0, column=1, sticky="ns")

        # ── Sektion 3: Wachstums-Highlights ───────────────────────────────────
        self._build_section_header(
            scroll, 4,
            "🌱  Wachstums-Highlights  (≥5% YoY, keine Kürzung, ≥2 Jahre)",
        )

        growth_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        growth_frame.grid(row=5, column=0, sticky="ew", padx=8, pady=(0, 24))
        growth_frame.grid_columnconfigure(0, weight=1)

        self._growth_tree = _build_entry_table(
            growth_frame,
            [
                ("rank",   "#",          36,  "center"),
                ("name",   "Wertpapier", 300, "w"),
                ("yoy",    "YoY",         80, "e"),
                ("score",  "Score",        70, "center"),
                ("yield",  "Rendite",      80, "e"),
                ("freq",   "Frequenz",     90, "center"),
            ],
        )
        vsb2 = ttk.Scrollbar(
            growth_frame, orient="vertical", command=self._growth_tree.yview
        )
        self._growth_tree.configure(yscrollcommand=vsb2.set)
        self._growth_tree.grid(row=0, column=0, sticky="ew")
        vsb2.grid(row=0, column=1, sticky="ns")

    def _build_section_header(
        self, parent: Any, row: int, text: str
    ) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(8, 4))
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame, text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkFrame(
            frame, height=1, fg_color=("gray70", "gray40")
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))

    # ── Datenladen ────────────────────────────────────────────────────────────

    def _start_load(self) -> None:
        self._status_label.configure(text="Lade …")
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            data = _load_analyse_data()
            self._queue.put(("data", data))
        except Exception as exc:
            logger.exception("Fehler beim Laden der Analyse-Daten.")
            self._queue.put(("error", str(exc)))

    def _process_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "data":
                    self._render(payload)
                elif kind == "error":
                    self._status_label.configure(text=f"⚠ Fehler: {payload}")
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    # ── Rendern ───────────────────────────────────────────────────────────────

    def _render(self, data: AnalyseData) -> None:
        self._data = data

        # Status
        self._status_label.configure(
            text=(
                f"{data.total_scored:,} Instrumente bewertet  |  "
                f"geladen in {data.load_time_ms} ms"
            )
        )

        # Chart rendern (nach kurzem Delay damit Canvas-Breite bekannt ist)
        self.after(50, lambda: self._chart.render(
            data.rating_counts, data.total_scored
        ))

        # Top-20
        self._top20_tree.delete(*self._top20_tree.get_children())
        for rank, entry in enumerate(data.top20, 1):
            self._top20_tree.insert(
                "", "end",
                values=(
                    rank,
                    entry.name[:45] + "…" if len(entry.name) > 45 else entry.name,
                    entry.score,
                    _RATING_LABEL[entry.rating],
                    entry.yield_pct,
                    entry.frequency,
                ),
                tags=(entry.rating,),
            )

        # Wachstums-Highlights
        self._growth_tree.delete(*self._growth_tree.get_children())
        if not data.growth_top10:
            self._growth_tree.insert(
                "", "end",
                values=("—", "Keine Instrumente erfüllen die Kriterien",
                         "—", "—", "—", "—"),
            )
        else:
            for rank, entry in enumerate(data.growth_top10, 1):
                self._growth_tree.insert(
                    "", "end",
                    values=(
                        rank,
                        entry.name[:40] + "…" if len(entry.name) > 40 else entry.name,
                        entry.yoy_pct,
                        entry.score,
                        entry.yield_pct,
                        entry.frequency,
                    ),
                    tags=(entry.rating,),
                )
