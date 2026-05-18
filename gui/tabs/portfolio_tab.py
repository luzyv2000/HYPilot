# Dateiname:     gui/tabs/portfolio_tab.py
# Version:       2026-05-15-fix1
# Abhängigkeiten (intern): db.portfolio_repository,
#                          gui.widgets.score_detail_panel,
#                          db.dividend_repository, analysis.scorer
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/portfolio_tab.py  —  Portfolio-Tab.
Fix 2026-05-16: Ungenutzte Imports sqlite3 + PortfolioEntry entfernt.
"""

from __future__ import annotations

import logging
import queue
import threading
from decimal import Decimal
from pathlib import Path
from typing import Any

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from gui.widgets.score_detail_panel import ScoreDetailPanel
from db.portfolio_repository import (
    add_position,
    get_portfolio,
    remove_position,
    update_position,
)

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_RATING_SHORT = {"STRONG_BUY": "SB", "BUY": "B", "WATCH": "W", "REJECT": "R"}
_RATING_COLOR_DARK  = {"STRONG_BUY": "#66bb6a", "BUY": "#aed581",
                        "WATCH": "#ffb74d",      "REJECT": "#ef5350"}
_RATING_COLOR_LIGHT = {"STRONG_BUY": "#1b5e20", "BUY": "#558b2f",
                        "WATCH": "#e65100",      "REJECT": "#b71c1c"}


def _micro_to_dec(micro: int | None) -> Decimal:
    if micro is None:
        return Decimal("0")
    return Decimal(micro) / Decimal("1000000")


def _fmt_shares(micro: int) -> str:
    d = _micro_to_dec(micro)
    return f"{d:,.4f}".rstrip("0").rstrip(".")


def _fmt_price(micro: int | None, currency: str) -> str:
    if micro is None:
        return "—"
    return f"{_micro_to_dec(micro):,.2f} {currency}"


def _fmt_yield(yield_bps: int | None) -> str:
    if yield_bps is None:
        return "—"
    return f"{yield_bps / 100:.2f} %"


def _fmt_annual(shares_micro: int, buy_price_micro: int | None,
                yield_bps: int | None, currency: str) -> str:
    if buy_price_micro is None or yield_bps is None:
        return "—"
    shares    = _micro_to_dec(shares_micro)
    price     = _micro_to_dec(buy_price_micro)
    yield_dec = Decimal(yield_bps) / Decimal("10000")
    annual    = shares * price * yield_dec
    return f"{annual:,.2f} {currency}"


# ── Lade-Funktion ─────────────────────────────────────────────────────────────

def _load_portfolio_rows() -> list[tuple]:
    from analysis.scorer import score_dividend_snapshot
    from db.dividend_repository import get_growth_metrics_bulk, get_snapshot

    entries    = get_portfolio(db_path=DB_PATH)
    growth_map = get_growth_metrics_bulk(db_path=DB_PATH) if entries else {}

    rows = []
    for entry in entries:
        yield_bps  = None
        score_str  = "—"
        rating     = ""
        annual_str = "—"

        try:
            snapshot = get_snapshot(entry.isin, db_path=DB_PATH)
            if snapshot is not None:
                yield_bps = snapshot.yield_bps
                metrics   = growth_map.get(entry.isin)
                score     = score_dividend_snapshot(snapshot, growth_metrics=metrics)
                short     = _RATING_SHORT.get(score.rating, "?")
                score_str = f"{score.total} {short}"
                rating    = score.rating
                annual_str = _fmt_annual(
                    entry.shares_micro, entry.buy_price_micro,
                    yield_bps, entry.currency,
                )
        except Exception:
            logger.debug("Scoring fehlgeschlagen für %s.", entry.isin)

        rows.append((
            entry.isin,
            entry.name,
            entry.wkn or "",
            _fmt_shares(entry.shares_micro),
            _fmt_price(entry.buy_price_micro, entry.currency),
            _fmt_yield(yield_bps),
            score_str,
            rating,
            annual_str,
            entry.added_at[:10] if entry.added_at else "—",
            entry.shares_micro,
            entry.buy_price_micro,
            entry.currency,
            entry.notes,
        ))
    return rows


# ── Positions-Dialog ──────────────────────────────────────────────────────────

class _PositionDialog(ctk.CTkToplevel):

    def __init__(
        self,
        master: Any,
        isin:      str        = "",
        edit_mode: bool       = False,
        initial:   dict | None = None,
        on_saved:  Any        = None,
    ) -> None:
        super().__init__(master)
        self._isin      = isin
        self._edit_mode = edit_mode
        self._initial   = initial or {}
        self._on_saved  = on_saved

        self.title("Position bearbeiten" if edit_mode else "Position hinzufügen")
        self.geometry("480x340")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self.after(20, self._build)
        self.after(50, lambda: (self.grab_set(), self.focus_set()))

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text="ISIN:", anchor="w").grid(
            row=0, column=0, padx=(20, 8), pady=(20, 6), sticky="w"
        )
        if self._edit_mode:
            ctk.CTkLabel(
                self, text=self._isin,
                text_color=("gray40", "gray70"), anchor="w",
            ).grid(row=0, column=1, padx=(0, 20), pady=(20, 6), sticky="w")
        else:
            self._isin_entry = ctk.CTkEntry(self, width=220)
            self._isin_entry.grid(
                row=0, column=1, padx=(0, 20), pady=(20, 6), sticky="ew"
            )
            if self._isin:
                self._isin_entry.insert(0, self._isin)

        ctk.CTkLabel(self, text="Stückzahl:", anchor="w").grid(
            row=1, column=0, padx=(20, 8), pady=(0, 6), sticky="w"
        )
        self._shares_entry = ctk.CTkEntry(
            self, width=220, placeholder_text="z. B. 100 oder 0.5"
        )
        self._shares_entry.grid(
            row=1, column=1, padx=(0, 20), pady=(0, 6), sticky="ew"
        )
        if self._initial.get("shares_micro"):
            self._shares_entry.insert(
                0, str(_micro_to_dec(self._initial["shares_micro"]))
            )

        ctk.CTkLabel(self, text="Kaufkurs:", anchor="w").grid(
            row=2, column=0, padx=(20, 8), pady=(0, 6), sticky="w"
        )
        self._price_entry = ctk.CTkEntry(
            self, width=220, placeholder_text="z. B. 54.32 (optional)"
        )
        self._price_entry.grid(
            row=2, column=1, padx=(0, 20), pady=(0, 6), sticky="ew"
        )
        if self._initial.get("buy_price_micro"):
            self._price_entry.insert(
                0, str(_micro_to_dec(self._initial["buy_price_micro"]))
            )

        ctk.CTkLabel(self, text="Währung:", anchor="w").grid(
            row=3, column=0, padx=(20, 8), pady=(0, 6), sticky="w"
        )
        self._currency_var = ctk.StringVar(
            value=self._initial.get("currency", "EUR")
        )
        ctk.CTkOptionMenu(
            self,
            values=["EUR", "USD", "GBP", "CHF", "SEK", "NOK", "DKK"],
            variable=self._currency_var,
            width=100,
        ).grid(row=3, column=1, padx=(0, 20), pady=(0, 6), sticky="w")

        ctk.CTkLabel(self, text="Notiz:", anchor="w").grid(
            row=4, column=0, padx=(20, 8), pady=(0, 6), sticky="w"
        )
        self._notes_entry = ctk.CTkEntry(
            self, width=220, placeholder_text="Optional"
        )
        self._notes_entry.grid(
            row=4, column=1, padx=(0, 20), pady=(0, 6), sticky="ew"
        )
        if self._initial.get("notes"):
            self._notes_entry.insert(0, self._initial["notes"])

        self._error_label = ctk.CTkLabel(
            self, text="",
            text_color=("firebrick3", "#ef5350"),
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self._error_label.grid(
            row=5, column=0, columnspan=2, padx=20, pady=(0, 4), sticky="w"
        )

        btn = ctk.CTkFrame(self, fg_color="transparent")
        btn.grid(row=6, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        btn.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn, text="Abbrechen", width=110,
            fg_color="transparent", border_width=1,
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            btn, text="Speichern", width=110,
            command=self._save,
        ).grid(row=0, column=2)

        self.bind("<Return>", lambda _: self._save())
        self.bind("<Escape>", lambda _: self.destroy())

    def _save(self) -> None:
        if self._edit_mode:
            isin = self._isin
        else:
            isin = self._isin_entry.get().strip().upper()
            if len(isin) != 12:
                self._error_label.configure(text="ISIN muss 12 Zeichen haben.")
                return

        shares_str = self._shares_entry.get().replace(",", ".").strip()
        if not shares_str:
            self._error_label.configure(text="Stückzahl ist erforderlich.")
            return
        try:
            shares_micro = int(Decimal(shares_str) * Decimal("1000000"))
            if shares_micro <= 0:
                raise ValueError
        except Exception:
            self._error_label.configure(
                text="Ungültige Stückzahl (z. B. 100 oder 0.5)."
            )
            return

        price_str = self._price_entry.get().replace(",", ".").strip()
        buy_price_micro: int | None = None
        if price_str:
            try:
                buy_price_micro = int(Decimal(price_str) * Decimal("1000000"))
                if buy_price_micro < 0:
                    raise ValueError
            except Exception:
                self._error_label.configure(
                    text="Ungültiger Kaufkurs (z. B. 54.32)."
                )
                return

        currency = self._currency_var.get()
        notes    = self._notes_entry.get().strip()

        if self._edit_mode:
            update_position(
                isin=isin, shares_micro=shares_micro,
                buy_price_micro=buy_price_micro,
                currency=currency, notes=notes, db_path=DB_PATH,
            )
        else:
            ok = add_position(
                isin=isin, shares_micro=shares_micro,
                buy_price_micro=buy_price_micro,
                currency=currency, notes=notes, db_path=DB_PATH,
            )
            if not ok:
                self._error_label.configure(
                    text=f"ISIN {isin} ist bereits im Portfolio oder nicht bekannt."
                )
                return

        if self._on_saved:
            self._on_saved()
        self.destroy()


# ── Haupt-Tab ─────────────────────────────────────────────────────────────────

class PortfolioTab(ctk.CTkFrame):

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._rows:  list[tuple] = []

        self._build_toolbar()
        self._build_table()
        self._build_summary_bar()
        self._build_detail_panel()

        self.after(100, self._process_queue)
        self._start_load()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ctk.CTkButton(bar, text="↻  Aktualisieren", width=140,
                       command=self._refresh).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            bar, text="＋  Position hinzufügen", width=180,
            fg_color=("green4", "#2d6a2d"),
            hover_color=("green3", "#3a8a3a"),
            command=self._open_add_dialog,
        ).pack(side="left", padx=(0, 8))

        self._edit_btn = ctk.CTkButton(
            bar, text="✎  Bearbeiten", width=130,
            state="disabled", command=self._open_edit_dialog,
        )
        self._edit_btn.pack(side="left", padx=(0, 8))

        self._remove_btn = ctk.CTkButton(
            bar, text="✕  Entfernen", width=130,
            fg_color=("firebrick3", "#8b0000"),
            hover_color=("firebrick4", "#6b0000"),
            state="disabled", command=self._remove_selected,
        )
        self._remove_btn.pack(side="left", padx=(0, 8))

        self._count_label = ctk.CTkLabel(
            bar, text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11), anchor="w",
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

        cols = ("name", "isin_wkn", "shares", "price",
                "yield", "score", "annual", "added")
        self._tree = ttk.Treeview(
            outer, columns=cols, show="headings", selectmode="browse",
        )
        self._tree.column("name",     width=260, anchor="w",      stretch=True)
        self._tree.column("isin_wkn", width=150, anchor="w",      stretch=False)
        self._tree.column("shares",   width=90,  anchor="e",      stretch=False)
        self._tree.column("price",    width=110, anchor="e",      stretch=False)
        self._tree.column("yield",    width=80,  anchor="e",      stretch=False)
        self._tree.column("score",    width=80,  anchor="center", stretch=False)
        self._tree.column("annual",   width=120, anchor="e",      stretch=False)
        self._tree.column("added",    width=100, anchor="center", stretch=False)

        self._tree.heading("name",     text="Wertpapier")
        self._tree.heading("isin_wkn", text="ISIN / WKN")
        self._tree.heading("shares",   text="Stück")
        self._tree.heading("price",    text="Kaufkurs")
        self._tree.heading("yield",    text="Rendite")
        self._tree.heading("score",    text="Score")
        self._tree.heading("annual",   text="Div/Jahr (est.)")
        self._tree.heading("added",    text="Seit")

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Portfolio.Treeview",
            background=bg, foreground=fg,
            fieldbackground=bg, borderwidth=0, rowheight=32,
        )
        style.configure(
            "Portfolio.Treeview.Heading",
            background=head_bg, foreground=head_fg,
            relief="flat", borderwidth=1, padding=(4, 4),
        )
        style.map(
            "Portfolio.Treeview",
            background=[("selected", "#1f6aa5")],
            foreground=[("selected", "#ffffff")],
        )
        self._tree.configure(style="Portfolio.Treeview")

        rc = _RATING_COLOR_DARK if dark else _RATING_COLOR_LIGHT
        for rating, color in rc.items():
            self._tree.tag_configure(rating, foreground=color)

        vsb = ttk.Scrollbar(outer, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>",          self._on_double_click)

    def _build_summary_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=("gray88", "gray18"))
        bar.grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 0))
        bar.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            bar, text="Gesamt:",
            font=ctk.CTkFont(size=11, weight="bold"), anchor="w",
        ).grid(row=0, column=0, padx=(12, 8), pady=6, sticky="w")

        self._summary_label = ctk.CTkLabel(
            bar, text="—",
            font=ctk.CTkFont(size=11),
            text_color=("gray40", "gray70"), anchor="w",
        )
        self._summary_label.grid(row=0, column=1, padx=(0, 12), pady=6, sticky="w")

    def _build_detail_panel(self) -> None:
        ctk.CTkFrame(
            self, height=1, fg_color=("gray75", "gray30")
        ).grid(row=4, column=0, sticky="ew", padx=0)
        self._detail_panel = ScoreDetailPanel(self, height=160)
        self._detail_panel.grid(row=5, column=0, sticky="ew", padx=0, pady=0)
        self._detail_panel.grid_propagate(False)

    def _start_load(self) -> None:
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self) -> None:
        try:
            rows = _load_portfolio_rows()
            self._queue.put(("data", rows))
        except Exception as exc:
            logger.exception("Fehler beim Laden des Portfolios.")
            self._queue.put(("error", str(exc)))

    def _process_queue(self) -> None:
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "data":
                    self._populate(payload)
                elif kind == "error":
                    self._count_label.configure(text=f"⚠ {payload[:60]}")
        except queue.Empty:
            pass
        self.after(100, self._process_queue)

    def _populate(self, rows: list[tuple]) -> None:
        self._rows = rows
        self._tree.delete(*self._tree.get_children())

        total_annual = Decimal("0")
        currency_set: set[str] = set()

        for row in rows:
            (isin, name, wkn, shares_str, price_str, yield_str,
             score_str, rating, annual_str, added_str,
             shares_micro, buy_price_micro, currency, notes) = row

            isin_wkn = f"{isin}\n{wkn}" if wkn else isin
            tags     = (rating,) if rating else ()
            label    = name[:40] + "…" if len(name) > 40 else name

            self._tree.insert(
                "", "end", iid=isin,
                values=(label, isin_wkn, shares_str, price_str,
                        yield_str, score_str, annual_str, added_str),
                tags=tags,
            )

            if buy_price_micro and annual_str != "—":
                try:
                    val = annual_str.split()[0].replace(",", "")
                    total_annual += Decimal(val)
                    currency_set.add(currency)
                except Exception:
                    pass

        n = len(rows)
        self._count_label.configure(
            text=f"{n} Position{'en' if n != 1 else ''}"
        )
        self._edit_btn.configure(state="disabled")
        self._remove_btn.configure(state="disabled")

        if n == 0:
            self._summary_label.configure(text="Noch keine Positionen eingetragen.")
        elif len(currency_set) == 1:
            cur = next(iter(currency_set))
            self._summary_label.configure(
                text=f"Geschätzter Jahresertrag (alle Positionen): "
                     f"{total_annual:,.2f} {cur}"
            )
        else:
            self._summary_label.configure(
                text="Jährlicher Ertrag: Mehrere Währungen — Einzelwerte in Tabelle."
            )

    def _get_selected_isin(self) -> str | None:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _on_select(self, _: tk.Event) -> None:
        isin = self._get_selected_isin()
        if not isin:
            return
        self._edit_btn.configure(state="normal")
        self._remove_btn.configure(state="normal")
        self._detail_panel.update(isin)

    def _on_double_click(self, event: tk.Event) -> None:
        if self._tree.identify_region(event.x, event.y) == "cell":
            self._open_edit_dialog()

    def _open_add_dialog(self) -> None:
        _PositionDialog(self, on_saved=self._refresh)

    def _open_edit_dialog(self) -> None:
        isin = self._get_selected_isin()
        if not isin:
            return
        row = next((r for r in self._rows if r[0] == isin), None)
        if not row:
            return
        _PositionDialog(
            self, isin=isin, edit_mode=True,
            initial={"shares_micro": row[10], "buy_price_micro": row[11],
                     "currency": row[12], "notes": row[13]},
            on_saved=self._refresh,
        )

    def _remove_selected(self) -> None:
        isin = self._get_selected_isin()
        if not isin:
            return
        remove_position(isin, db_path=DB_PATH)
        self._detail_panel.clear()
        self._refresh()

    def _refresh(self) -> None:
        self._detail_panel.clear()
        self._edit_btn.configure(state="disabled")
        self._remove_btn.configure(state="disabled")
        self._start_load()
