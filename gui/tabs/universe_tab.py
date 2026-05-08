# Dateiname:     gui/tabs/universe_tab.py
# Version:       2026-05-08
# Abhängigkeiten (intern): gui.widgets.instrument_table,
#                          gui.widgets.score_detail_panel,
#                          core.dividend_service,
#                          db.dividend_repository,
#                          analysis.scorer
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/universe_tab.py

TR-Universum-Tab mit Batch-Dividenden-Update, manueller Namensänderung,
Score-Spalte und Score-Detail-Panel.

Grid-Layout:
  Row 0: Toolbar
  Row 1: Fortschrittsbalken (bedingt)
  Row 2: InstrumentTable (weight=1, füllt restlichen Platz)
  Row 3: ScoreDetailPanel (feste Höhe ~160px)

Row-Format (6 Elemente):
  (flag, name, isin_wkn, div_display, score_display, isin_raw)
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

from gui.widgets.instrument_table import InstrumentTable, Row
from gui.widgets.score_detail_panel import ScoreDetailPanel

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

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
    LEFT JOIN dividend_data d ON i.isin = d.isin
    ORDER BY display_name ASC
"""

_RATING_SHORT = {
    "STRONG_BUY": "SB",
    "BUY":        "B",
    "WATCH":      "W",
    "REJECT":     "R",
}


def _format_div(yield_bps: int | None) -> str:
    if yield_bps is None:
        return "—"
    return f"{yield_bps / 100.0:.2f} %"


def _format_isin_wkn(isin: str, wkn: str) -> str:
    return f"{isin}\n{wkn}" if wkn else isin


def _format_score(score_total: int, rating: str) -> str:
    short = _RATING_SHORT.get(rating, rating[:1])
    return f"{score_total} {short}"


def _load_instruments() -> list[Row]:
    """
    Lädt alle Instrumente aus der DB und berechnet Scores.
    Läuft im Hintergrund-Thread — kein Netzwerk-Zugriff.
    """
    from analysis.scorer import score_dividend_snapshot
    from core.dividend_source import DividendSnapshot

    rows: list[Row] = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for db_row in conn.execute(_QUERY):
                name = db_row["display_name"]
                if db_row["has_override"]:
                    name = "✎ " + name

                score_display = "—"
                if db_row["yield_bps"] is not None or db_row["frequency"] is not None:
                    try:
                        last_ex = (
                            date.fromisoformat(db_row["last_ex_date"])
                            if db_row["last_ex_date"]
                            else None
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
                        score = score_dividend_snapshot(snapshot)
                        score_display = _format_score(score.total, score.rating)
                    except Exception:
                        logger.debug(
                            "Score-Berechnung fehlgeschlagen für %s.",
                            db_row["isin"],
                        )

                rows.append((
                    "",
                    name,
                    _format_isin_wkn(db_row["isin"], db_row["wkn"]),
                    _format_div(db_row["yield_bps"]),
                    score_display,
                    db_row["isin"],
                ))

    except sqlite3.Error:
        logger.exception("Datenbankfehler beim Laden des Universums.")

    logger.info("Universe geladen: %d Instrumente.", len(rows))
    return rows


class UniverseTab(ctk.CTkFrame):
    """TR-Universum-Tab."""

    _BATCH_LIMIT = 100

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._batch_running = False
        self._stop_event    = threading.Event()
        self._progress_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self._build_toolbar()
        self._build_progress_bar()
        self._build_table()
        self._build_detail_panel()

        self._table.load_data(_load_instruments)
        self._refresh_pending_badge()

        self.after(200, self._process_progress_queue)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ctk.CTkButton(
            bar, text="↻  Aktualisieren", width=140,
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        self._category_var = ctk.StringVar(value="Alle")
        ctk.CTkOptionMenu(
            bar,
            values=["Alle", "ETF", "STOCK", "BOND", "DERIVATIVE"],
            variable=self._category_var,
            width=140,
            command=self._on_category_change,
        ).pack(side="left", padx=(0, 8))

        self._div_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            bar, text="Nur mit Dividende",
            variable=self._div_only_var,
            command=self._on_filter_change,
        ).pack(side="left", padx=(0, 8))

        self._scored_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            bar, text="Nur mit Score",
            variable=self._scored_only_var,
            command=self._on_filter_change,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkFrame(bar, width=2, height=24,
                     fg_color=("gray70", "gray40")).pack(side="left", padx=12)

        self._batch_btn = ctk.CTkButton(
            bar,
            text="⬇  Dividenden laden",
            width=175,
            fg_color=("green4", "#2d6a2d"),
            hover_color=("green3", "#3a8a3a"),
            command=self._toggle_batch,
        )
        self._batch_btn.pack(side="left", padx=(0, 8))

        ctk.CTkFrame(bar, width=2, height=24,
                     fg_color=("gray70", "gray40")).pack(side="left", padx=12)

        self._pending_btn = ctk.CTkButton(
            bar, text="", width=180,
            fg_color=("orange3", "#b35c00"),
            hover_color=("orange4", "#8a4500"),
            command=self._open_pending_dialog,
        )
        self._pending_btn.pack(side="left", padx=(0, 8))
        self._pending_btn.pack_forget()

    def _build_progress_bar(self) -> None:
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._progress_frame.grid(
            row=1, column=0, sticky="ew", padx=8, pady=(4, 0)
        )
        self._progress_frame.grid_columnconfigure(1, weight=1)

        self._progress_label = ctk.CTkLabel(
            self._progress_frame, text="", anchor="w", width=200,
        )
        self._progress_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self._progress_bar = ctk.CTkProgressBar(
            self._progress_frame, mode="determinate"
        )
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=1, sticky="ew")

        self._progress_detail = ctk.CTkLabel(
            self._progress_frame, text="",
            text_color=("gray50", "gray60"),
            anchor="e", width=220,
        )
        self._progress_detail.grid(row=0, column=2, padx=(8, 0), sticky="e")

        self._progress_frame.grid_remove()

    def _build_table(self) -> None:
        self._table = InstrumentTable(self)
        self._table.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        self._table.set_double_click_callback(self._on_row_double_click)
        self._table.set_select_callback(self._on_instrument_selected)

    def _build_detail_panel(self) -> None:
        """Score-Detail-Panel unterhalb der Tabelle."""
        # Trennlinie
        ctk.CTkFrame(
            self, height=1, fg_color=("gray75", "gray30")
        ).grid(row=3, column=0, sticky="ew", padx=0)

        self._detail_panel = ScoreDetailPanel(self, height=160)
        self._detail_panel.grid(
            row=4, column=0, sticky="ew", padx=0, pady=0
        )
        self._detail_panel.grid_propagate(False)

    # ── Selektion → Detail-Panel ──────────────────────────────────────────────

    def _on_instrument_selected(self, isin: str) -> None:
        """Callback von InstrumentTable bei Selektion."""
        self._detail_panel.update(isin)

    # ── Namensänderung ────────────────────────────────────────────────────────

    def _on_row_double_click(self, isin: str) -> None:
        from gui.widgets.name_edit_dialog import NameEditDialog
        NameEditDialog(self, isin=isin, on_saved=self._on_name_saved)

    def _on_name_saved(self) -> None:
        self._table.load_data(_load_instruments)

    def _open_pending_dialog(self) -> None:
        from gui.widgets.pending_names_dialog import PendingNamesDialog
        PendingNamesDialog(self, on_closed=self._on_pending_dialog_closed)

    def _on_pending_dialog_closed(self) -> None:
        self._refresh_pending_badge()
        self._table.load_data(_load_instruments)

    def _refresh_pending_badge(self) -> None:
        from db.instrument_repository import count_pending_name_changes
        count = count_pending_name_changes()
        if count > 0:
            self._pending_btn.configure(text=f"⚠  {count} Namensänderung(en)")
            self._pending_btn.pack(side="left", padx=(0, 8))
        else:
            self._pending_btn.pack_forget()

    # ── Batch-Update ──────────────────────────────────────────────────────────

    def _toggle_batch(self) -> None:
        if self._batch_running:
            self._stop_batch()
        else:
            self._start_batch()

    def _start_batch(self) -> None:
        self._batch_running = True
        self._stop_event.clear()
        self._batch_btn.configure(
            text="⏹  Abbrechen",
            fg_color=("firebrick3", "#8b0000"),
            hover_color=("firebrick4", "#6b0000"),
        )
        self._progress_frame.grid()
        self._progress_bar.set(0)
        self._progress_label.configure(text="Starte …")
        self._progress_detail.configure(text="")
        threading.Thread(target=self._batch_worker, daemon=True).start()

    def _stop_batch(self) -> None:
        self._stop_event.set()
        self._progress_label.configure(text="Wird abgebrochen …")
        self._batch_btn.configure(state="disabled")

    def _batch_worker(self) -> None:
        from core.dividend_service import update_batch

        def on_progress(processed: int, total: int,
                        isin: str, status: str) -> None:
            self._progress_queue.put((
                "progress",
                {"processed": processed, "total": total,
                 "isin": isin, "status": status},
            ))

        try:
            stats = update_batch(
                limit=self._BATCH_LIMIT,
                progress_callback=on_progress,
                stop_flag=lambda: self._stop_event.is_set(),
            )
            self._progress_queue.put(("done", stats))
        except Exception as exc:
            logger.exception("Fehler im Batch-Worker.")
            self._progress_queue.put(("error", str(exc)))

    def _process_progress_queue(self) -> None:
        try:
            while True:
                kind, payload = self._progress_queue.get_nowait()
                if kind == "progress":
                    self._update_progress(**payload)
                elif kind == "done":
                    self._on_batch_done(payload)
                elif kind == "error":
                    self._on_batch_error(payload)
        except queue.Empty:
            pass
        self.after(150, self._process_progress_queue)

    def _update_progress(self, processed: int, total: int,
                         isin: str, status: str) -> None:
        if total > 0:
            self._progress_bar.set(processed / total)
        self._progress_label.configure(text=f"{processed} / {total} ISINs")
        short = isin[:12] + "…" if len(isin) > 12 else isin
        self._progress_detail.configure(text=f"{short}  {status}")

    def _on_batch_done(self, stats: dict[str, int]) -> None:
        self._batch_running = False
        self._progress_bar.set(1.0)
        self._progress_label.configure(
            text=f"✓ Fertig — {stats['updated']} aktualisiert, "
                 f"{stats['skipped']} übersprungen"
        )
        self._progress_detail.configure(text="")
        self._reset_batch_button()
        self._table.load_data(_load_instruments)

    def _on_batch_error(self, message: str) -> None:
        self._batch_running = False
        self._progress_label.configure(text=f"⚠ Fehler: {message}")
        self._reset_batch_button()

    def _reset_batch_button(self) -> None:
        self._batch_btn.configure(
            text="⬇  Dividenden laden",
            fg_color=("green4", "#2d6a2d"),
            hover_color=("green3", "#3a8a3a"),
            state="normal",
        )

    # ── Filter ────────────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._detail_panel.clear()
        self._table.load_data(_load_instruments)

    def _on_category_change(self, _: str) -> None:
        self._on_filter_change()

    def _on_filter_change(self) -> None:
        category    = self._category_var.get()
        div_only    = self._div_only_var.get()
        scored_only = self._scored_only_var.get()

        from analysis.rules import classify_instrument

        def filtered_loader() -> list[Row]:
            base   = _load_instruments()
            result = []
            for row in base:
                if category != "Alle":
                    clean_name = row[1].lstrip("✎ ")
                    if classify_instrument(clean_name, row[5]) != category:
                        continue
                if div_only and row[3] == "—":
                    continue
                if scored_only and row[4] == "—":
                    continue
                result.append(row)
            return result

        self._detail_panel.clear()
        self._table.load_data(filtered_loader)