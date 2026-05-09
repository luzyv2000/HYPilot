# Dateiname:     gui/widgets/score_detail_panel.py
# Version:       2026-05-09-growth
# Abhängigkeiten (intern): db.dividend_repository, analysis.scorer
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/score_detail_panel.py
Neu 2026-05-09: update() lädt GrowthMetrics und gibt sie an scorer weiter.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import customtkinter as ctk

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_RATING_STYLE: dict[str, tuple[str, str, str]] = {
    "STRONG_BUY": ("STRONG BUY", "#1b5e20", "#66bb6a"),
    "BUY":        ("BUY",        "#558b2f", "#aed581"),
    "WATCH":      ("WATCH",      "#e65100", "#ffb74d"),
    "REJECT":     ("REJECT",     "#b71c1c", "#ef5350"),
}

_DIMENSIONS: list[tuple[str, int]] = [
    ("Rendite",    40),
    ("Frequenz",   20),
    ("Stabilität", 25),
    ("Payout",     15),
]


class ScoreDetailPanel(ctk.CTkFrame):

    def __init__(self, master: ctk.CTkFrame, **kwargs: dict) -> None:
        super().__init__(master, fg_color=("gray90", "gray17"), **kwargs)
        self._current_isin: str | None = None
        self._build()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=8)
        left.grid_columnconfigure(0, weight=1)

        self._name_label = ctk.CTkLabel(
            left,
            text="Kein Instrument ausgewählt",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self._name_label.grid(row=0, column=0, sticky="w")

        self._isin_label = ctk.CTkLabel(
            left, text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11), anchor="w",
        )
        self._isin_label.grid(row=1, column=0, sticky="w")

        self._notes_label = ctk.CTkLabel(
            left, text="",
            text_color=("gray40", "gray70"),
            font=ctk.CTkFont(size=11), anchor="w",
            wraplength=560, justify="left",
        )
        self._notes_label.grid(row=2, column=0, sticky="w", pady=(4, 0))

        self._rating_badge = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=120, height=32, corner_radius=6,
            fg_color="transparent",
        )
        self._rating_badge.grid(
            row=0, column=1, padx=(0, 12), pady=8, sticky="ne"
        )

        ctk.CTkFrame(
            self, height=1, fg_color=("gray75", "gray30")
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=8)

        bars_frame = ctk.CTkFrame(self, fg_color="transparent")
        bars_frame.grid(
            row=2, column=0, columnspan=2,
            sticky="ew", padx=12, pady=(6, 10)
        )
        bars_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self._bars: list[ctk.CTkProgressBar] = []
        self._bar_labels: list[ctk.CTkLabel]  = []

        for col_idx, (label, max_pts) in enumerate(_DIMENSIONS):
            pad = (0 if col_idx == 0 else 16, 0)
            ctk.CTkLabel(
                bars_frame, text=label,
                font=ctk.CTkFont(size=11), anchor="w",
            ).grid(row=0, column=col_idx, sticky="w", padx=pad)

            bar = ctk.CTkProgressBar(
                bars_frame, height=12, corner_radius=4,
                progress_color=("#1f6aa5", "#3a9ad9"),
            )
            bar.set(0)
            bar.grid(row=1, column=col_idx, sticky="ew",
                     padx=pad, pady=(2, 0))
            self._bars.append(bar)

            lbl = ctk.CTkLabel(
                bars_frame, text=f"0 / {max_pts}",
                font=ctk.CTkFont(size=10),
                text_color=("gray45", "gray65"), anchor="w",
            )
            lbl.grid(row=2, column=col_idx, sticky="w", padx=pad)
            self._bar_labels.append(lbl)

    def update(self, isin: str) -> None:
        if isin == self._current_isin:
            return
        self._current_isin = isin

        try:
            from db.dividend_repository import get_growth_metrics, get_snapshot
            snapshot = get_snapshot(isin)
            metrics  = get_growth_metrics(isin)
        except Exception:
            logger.exception("ScoreDetailPanel: Fehler beim Laden von %s", isin)
            self.clear()
            return

        if snapshot is None:
            self._show_no_data(isin)
            return

        from analysis.scorer import score_dividend_snapshot
        score = score_dividend_snapshot(snapshot, growth_metrics=metrics)
        dark  = ctk.get_appearance_mode() == "Dark"

        name = self._load_display_name(isin)
        self._name_label.configure(text=name or isin)
        self._isin_label.configure(text=isin)
        self._notes_label.configure(text="  •  ".join(score.notes[:4]))

        style       = _RATING_STYLE.get(score.rating, ("?", "#555", "#aaa"))
        badge_color = style[2] if dark else style[1]
        self._rating_badge.configure(
            text=f"{score.total} / 100\n{style[0]}",
            fg_color=badge_color, text_color="white",
        )

        subscores = [
            score.yield_points, score.frequency_points,
            score.stability_points, score.payout_points,
        ]
        for i, (pts, (_, max_pts)) in enumerate(zip(subscores, _DIMENSIONS)):
            self._bars[i].set(pts / max_pts if max_pts > 0 else 0)
            self._bar_labels[i].configure(text=f"{pts} / {max_pts}")

    def clear(self) -> None:
        self._current_isin = None
        self._name_label.configure(text="Kein Instrument ausgewählt")
        self._isin_label.configure(text="")
        self._notes_label.configure(text="")
        self._rating_badge.configure(
            text="", fg_color="transparent", text_color="white"
        )
        for i, (_, max_pts) in enumerate(_DIMENSIONS):
            self._bars[i].set(0)
            self._bar_labels[i].configure(text=f"0 / {max_pts}")

    def _load_snapshot(self, isin: str):
        from db.dividend_repository import get_snapshot
        return get_snapshot(isin)

    def _load_display_name(self, isin: str) -> str | None:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT COALESCE(name_override, name) AS n "
                    "FROM instruments WHERE isin = ?", (isin,),
                ).fetchone()
            return row[0] if row else None
        except sqlite3.Error:
            return None

    def _show_no_data(self, isin: str) -> None:
        name = self._load_display_name(isin)
        self._name_label.configure(text=name or isin)
        self._isin_label.configure(text=isin)
        self._notes_label.configure(text="Keine Dividendendaten vorhanden.")
        self._rating_badge.configure(
            text="—", fg_color=("gray70", "gray40"), text_color="white"
        )
        for i, (_, max_pts) in enumerate(_DIMENSIONS):
            self._bars[i].set(0)
            self._bar_labels[i].configure(text=f"— / {max_pts}")