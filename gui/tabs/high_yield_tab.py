# Dateiname:     gui/tabs/high_yield_tab.py
# Version:       2026-05-09-watchlist
# Abhängigkeiten (intern): gui.widgets.instrument_table,
#                          gui.widgets.score_detail_panel,
#                          db.watchlist_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/high_yield_tab.py — Neu: Watchlist-Button in der Toolbar.
"""

from __future__ import annotations

import csv
import logging
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

_RATING_SHORT = {"STRONG_BUY": "SB", "BUY": "B", "WATCH": "W", "REJECT": "R"}


def _format_div(yield_bps: int | None) -> str:
    return "—" if yield_bps is None else f"{yield_bps / 100.0:.2f} %"


def _format_isin_wkn(isin: str, wkn: str) -> str:
    return f"{isin}\n{wkn}" if wkn else isin


def _format_score(score_total: int, rating: str) -> str:
    return f"{score_total} {_RATING_SHORT.get(rating, rating[:1])}"


def _load_high_yield() -> list[Row]:
    from analysis.scorer import score_dividend_snapshot
    from core.dividend_source import DividendSnapshot
    from db.dividend_repository import get_growth_metrics_bulk

    growth_map = get_growth_metrics_bulk(db_path=DB_PATH)
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
                        if db_row["last_ex_date"] else None
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
                    metrics = growth_map.get(db_row["isin"])
                    score   = score_dividend_snapshot(snapshot, growth_metrics=metrics)
                    score_display = _format_score(score.total, score.rating)
                except Exception:
                    logger.debug("Score fehlgeschlagen für %s.", db_row["isin"])

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
        self._raw_rows:     list[Row] = []
        self._raw_lock      = threading.Lock()
        self._watchlist_tab = None
        self._build_toolbar()
        self._build_table()
        self._build_detail_panel()
        self._table.load_data(self._loader_with_cache)

    def set_watchlist_tab(self, tab: Any) -> None:
        self._watchlist_tab = tab

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
            bar, text="↻  Aktualisieren", width=140,
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar,
            text="📥  CSV exportieren", width=160,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            command=self._export_csv,
        ).pack(side="left", padx=(0, 8))

        # ── Watchlist-Button ──────────────────────────────────────────────────
        self._watchlist_btn = ctk.CTkButton(
            bar,
            text="⭐  Watchlist",
            width=140,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            state="disabled",
            command=self._add_to_watchlist,
        )
        self._watchlist_btn.pack(side="left", padx=(0, 8))

        self._count_label = ctk.CTkLabel(
            bar, text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11), anchor="e",
        )
        self._count_label.pack(side="right", padx=(0, 4))

    def _build_table(self) -> None:
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

    def _loader_with_cache(self) -> list[Row]:
        rows = _load_high_yield()
        with self._raw_lock:
            self._raw_rows = rows
        self.after(0, lambda: self._count_label.configure(
            text=f"{len(rows)} Instrumente"
        ))
        return rows

    def _on_instrument_selected(self, isin: str) -> None:
        self._detail_panel.update(isin)
        self._watchlist_btn.configure(state="normal")

    def _add_to_watchlist(self) -> None:
        isin = self._table.get_selected_isin()
        if not isin:
            return
        from db.watchlist_repository import add_to_watchlist
        added = add_to_watchlist(isin, db_path=DB_PATH)
        if added:
            self._watchlist_btn.configure(text="✅  Hinzugefügt")
            self.after(2000, lambda: self._watchlist_btn.configure(
                text="⭐  Watchlist"
            ))
            if self._watchlist_tab:
                self._watchlist_tab.reload()
        else:
            self._watchlist_btn.configure(text="⭐  Bereits vorhanden")
            self.after(2000, lambda: self._watchlist_btn.configure(
                text="⭐  Watchlist"
            ))

    def _refresh(self) -> None:
        self._detail_panel.clear()
        self._watchlist_btn.configure(state="disabled")
        self._table.load_data(self._loader_with_cache)

    def _export_csv(self) -> None:
        with self._raw_lock:
            rows = list(self._raw_rows)
        if not rows:
            return
        timestamp    = datetime.now().strftime("%Y%m%d_%H%M")
        default_name = f"hypilot_high_yield_{timestamp}.csv"
        filepath = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV-Datei", "*.csv"), ("Alle Dateien", "*.*")],
            initialfile=default_name,
            title="High-Yield-Liste exportieren",
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f, delimiter=";")
                writer.writerow(["Name", "ISIN", "WKN", "Rendite %", "Score"])
                for row in rows:
                    parts  = row[2].split("\n")
                    isin_p = parts[0]
                    wkn_p  = parts[1] if len(parts) > 1 else ""
                    writer.writerow([
                        row[1].lstrip("✎ "), isin_p, wkn_p, row[3], row[4],
                    ])
            logger.info("CSV-Export: %d Zeilen → %s", len(rows), filepath)
        except OSError as exc:
            logger.error("CSV-Export fehlgeschlagen: %s", exc)