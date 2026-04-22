# Dateiname:     gui/tabs/universe_tab.py
# Version:       2026-04-22-C
# Abhängigkeiten (intern): gui.widgets.instrument_table,
#                          core.dividend_service,
#                          db.dividend_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/universe_tab.py

TR-Universum-Tab mit Batch-Dividenden-Update.

Threading-Regeln (verbindlich):
  - Batch-Update läuft in threading.Thread (Netzwerk-I/O)
  - GUI-Updates NUR via self.after() + queue.Queue
  - Niemals direkte Widget-Manipulation aus Hintergrund-Thread
  - stop_flag als threading.Event für sauberen Abbruch
"""

from __future__ import annotations

import logging
import queue
import sqlite3
import threading
from pathlib import Path
from typing import Any

import customtkinter as ctk

from gui.widgets.instrument_table import InstrumentTable, Row

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_QUERY = """
    SELECT
        i.name,
        i.isin,
        COALESCE(i.wkn, '') AS wkn,
        d.yield_bps
    FROM instruments i
    LEFT JOIN dividend_data d ON i.isin = d.isin
    ORDER BY i.name ASC
"""


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _format_div(yield_bps: int | None) -> str:
    if yield_bps is None:
        return "—"
    return f"{yield_bps / 100.0:.2f} %"


def _format_isin_wkn(isin: str, wkn: str) -> str:
    return f"{isin}\n{wkn}" if wkn else isin


def _load_instruments() -> list[Row]:
    rows: list[Row] = []
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            for db_row in conn.execute(_QUERY):
                rows.append((
                    "",
                    db_row["name"],
                    _format_isin_wkn(db_row["isin"], db_row["wkn"]),
                    _format_div(db_row["yield_bps"]),
                    db_row["isin"],
                ))
    except sqlite3.Error:
        logger.exception("Datenbankfehler beim Laden des Universums.")
    logger.info("Universe geladen: %d Instrumente.", len(rows))
    return rows


# ── Tab ───────────────────────────────────────────────────────────────────────

class UniverseTab(ctk.CTkFrame):
    """TR-Universum-Tab mit Batch-Dividenden-Update."""

    # Maximale ISINs pro Batch-Lauf (yfinance ist langsam)
    _BATCH_LIMIT = 100

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._batch_running   = False
        self._stop_event      = threading.Event()
        self._progress_queue: queue.Queue[tuple[str, Any]] = queue.Queue()

        self._build_toolbar()
        self._build_progress_bar()
        self._build_table()

        self._table.load_data(_load_instruments)
        self.after(200, self._process_progress_queue)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        # Aktualisieren
        ctk.CTkButton(
            bar,
            text="↻  Aktualisieren",
            width=140,
            command=self._refresh,
        ).pack(side="left", padx=(0, 8))

        # Kategorie-Filter
        self._category_var = ctk.StringVar(value="Alle")
        ctk.CTkOptionMenu(
            bar,
            values=["Alle", "ETF", "STOCK", "BOND", "DERIVATIVE"],
            variable=self._category_var,
            width=140,
            command=self._on_category_change,
        ).pack(side="left", padx=(0, 8))

        # Nur mit Dividende
        self._div_only_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            bar,
            text="Nur mit Dividende",
            variable=self._div_only_var,
            command=self._on_filter_change,
        ).pack(side="left", padx=(0, 8))

        # Trennlinie
        ctk.CTkFrame(bar, width=2, height=24,
                     fg_color=("gray70", "gray40")).pack(
            side="left", padx=12
        )

        # Batch-Update Button
        self._batch_btn = ctk.CTkButton(
            bar,
            text="⬇  Dividenden laden",
            width=175,
            fg_color=("green4", "#2d6a2d"),
            hover_color=("green3", "#3a8a3a"),
            command=self._toggle_batch,
        )
        self._batch_btn.pack(side="left", padx=(0, 8))

        # Limit-Anzeige
        self._limit_label = ctk.CTkLabel(
            bar,
            text=f"max. {self._BATCH_LIMIT} ISINs",
            text_color=("gray50", "gray60"),
        )
        self._limit_label.pack(side="left")

    def _build_progress_bar(self) -> None:
        """Fortschrittsbereich — initial versteckt."""
        self._progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._progress_frame.grid(
            row=1, column=0, sticky="ew", padx=8, pady=(4, 0)
        )
        self._progress_frame.grid_columnconfigure(1, weight=1)

        self._progress_label = ctk.CTkLabel(
            self._progress_frame,
            text="",
            anchor="w",
            width=200,
        )
        self._progress_label.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self._progress_bar = ctk.CTkProgressBar(
            self._progress_frame, mode="determinate"
        )
        self._progress_bar.set(0)
        self._progress_bar.grid(row=0, column=1, sticky="ew")

        self._progress_detail = ctk.CTkLabel(
            self._progress_frame,
            text="",
            text_color=("gray50", "gray60"),
            anchor="e",
            width=220,
        )
        self._progress_detail.grid(row=0, column=2, padx=(8, 0), sticky="e")

        # Initial verstecken
        self._progress_frame.grid_remove()

    def _build_table(self) -> None:
        self._table = InstrumentTable(self)
        self._table.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)

    # ── Batch-Update ──────────────────────────────────────────────────────────

    def _toggle_batch(self) -> None:
        """Start oder Abbruch des Batch-Updates."""
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
        self._progress_frame.grid()      # einblenden
        self._progress_bar.set(0)
        self._progress_label.configure(text="Starte …")
        self._progress_detail.configure(text="")

        threading.Thread(
            target=self._batch_worker,
            daemon=True,
        ).start()

    def _stop_batch(self) -> None:
        """Sendet Abbruch-Signal — Worker beendet sich beim nächsten ISIN."""
        self._stop_event.set()
        self._progress_label.configure(text="Wird abgebrochen …")
        self._batch_btn.configure(state="disabled")

    def _batch_worker(self) -> None:
        """
        Läuft im Hintergrund-Thread.
        Kommuniziert mit GUI ausschließlich via _progress_queue.
        """
        from core.dividend_service import update_batch

        def on_progress(
            processed: int, total: int, isin: str, status: str
        ) -> None:
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
            logger.exception("Unerwarteter Fehler im Batch-Worker.")
            self._progress_queue.put(("error", str(exc)))

    def _process_progress_queue(self) -> None:
        """
        Verarbeitet Nachrichten vom Batch-Worker.
        Läuft ausschließlich im Hauptthread via self.after().
        """
        try:
            while True:
                kind, payload = self._progress_queue.get_nowait()

                if kind == "progress":
                    self._update_progress(
                        payload["processed"],
                        payload["total"],
                        payload["isin"],
                        payload["status"],
                    )

                elif kind == "done":
                    self._on_batch_done(payload)

                elif kind == "error":
                    self._on_batch_error(payload)

        except queue.Empty:
            pass

        self.after(150, self._process_progress_queue)

    def _update_progress(
        self,
        processed: int,
        total: int,
        isin: str,
        status: str,
    ) -> None:
        """Aktualisiert Fortschrittsanzeige. Nur im Hauptthread."""
        if total > 0:
            self._progress_bar.set(processed / total)

        self._progress_label.configure(
            text=f"{processed} / {total} ISINs"
        )
        # Kurze ISIN + Status für Detail-Label
        short_isin = isin[:12] + "…" if len(isin) > 12 else isin
        self._progress_detail.configure(
            text=f"{short_isin}  {status}"
        )

    def _on_batch_done(self, stats: dict[str, int]) -> None:
        """Batch erfolgreich abgeschlossen."""
        self._batch_running = False
        self._progress_bar.set(1.0)
        self._progress_label.configure(
            text=f"✓ Fertig — {stats['updated']} aktualisiert, "
                 f"{stats['skipped']} übersprungen"
        )
        self._progress_detail.configure(text="")
        self._reset_batch_button()

        # Tabelle sofort neu laden damit neue Dividendenwerte sichtbar sind
        self._table.load_data(_load_instruments)

        logger.info(
            "Batch-UI abgeschlossen: %s", stats
        )

    def _on_batch_error(self, message: str) -> None:
        """Batch mit Fehler beendet."""
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

    # ── Filter / Aktualisieren ────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._table.load_data(_load_instruments)

    def _on_category_change(self, _: str) -> None:
        self._on_filter_change()

    def _on_filter_change(self) -> None:
        category = self._category_var.get()
        div_only = self._div_only_var.get()

        from analysis.rules import classify_instrument

        def filtered_loader() -> list[Row]:
            base = _load_instruments()
            result = []
            for row in base:
                if category != "Alle":
                    if classify_instrument(row[1], row[4]) != category:
                        continue
                if div_only and row[3] == "—":
                    continue
                result.append(row)
            return result

        self._table.load_data(filtered_loader)
