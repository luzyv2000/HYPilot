# Dateiname:     gui/widgets/sparplan_popup.py
# Version:       2026-05-17
# Abhängigkeiten (intern): db.sparplan_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/sparplan_popup.py

Popup-Fenster für die Sparplan-Bewertung.

Zeigt 10 unbewertete ISINs mit Ja/Nein-Buttons.
Entscheidungen werden erst beim Schließen gespeichert (nicht sofort),
damit der Nutzer alle 10 auf einmal überblicken und entscheiden kann.

Buttons:
  Ja  (S) / Nein (N) pro Zeile — Toggle, wiederholtes Klicken wechselt
  ✱ Weiter              — lädt nächste 10 ISINs (speichert aktuelle zuerst)
  ✕ 24h pausieren       — schließt + pausiert Scheduler für 24h
  ✓ Schließen           — speichert + schließt (unbewertete bleiben NULL)

Callback on_closed(reload_universe: bool):
  True  → Universe-Tab neu laden (mindestens eine S-Markierung gesetzt)
  False → kein Reload nötig
"""

from __future__ import annotations

import logging
from typing import Callable

import customtkinter as ctk
import tkinter as tk
from tkinter import ttk

from db.sparplan_repository import (
    SparplanCandidate,
    get_candidates,
    get_cycle_info,
    mark_batch,
    set_paused,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 10

# Farben für Ja/Nein-Buttons
_BTN_YES_FG   = ("green4",     "#2d6a2d")
_BTN_YES_HOV  = ("green3",     "#3a8a3a")
_BTN_NO_FG    = ("firebrick3", "#8b0000")
_BTN_NO_HOV   = ("firebrick4", "#6b0000")
_BTN_NONE_FG  = ("gray70",     "gray30")


def _fmt_yield(yield_bps: int | None) -> str:
    if yield_bps is None:
        return "—"
    return f"{yield_bps / 100:.2f} %"


def _priority_label(priority: int) -> str:
    return {1: "≥10 %", 2: "≥5 %", 3: ">0 %", 4: "—"}.get(priority, "—")


class SparplanPopup(ctk.CTkToplevel):
    """
    Popup zur Sparplan-Bewertung von je 10 ISINs.

    Args:
        master:      Eltern-Widget (HYPilotApp)
        on_closed:   Callback(reload_universe: bool)
    """

    def __init__(
        self,
        master: ctk.CTk,
        on_closed: Callable[[bool], None] | None = None,
    ) -> None:
        super().__init__(master)

        self._on_closed   = on_closed
        self._candidates: list[SparplanCandidate] = []
        # {isin: 'S' | 'N' | None} — Entscheidungen dieser Sitzung
        self._decisions:  dict[str, str | None] = {}
        self._has_new_s   = False   # mind. eine S-Markierung in dieser Sitzung

        self.title("⭐  Sparplan-Eignung prüfen")
        self.geometry("860x560")
        self.minsize(700, 400)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_shell()
        self._load_candidates()

        logger.info("SparplanPopup geöffnet.")

    # ── Grundgerüst ───────────────────────────────────────────────────────────

    def _build_shell(self) -> None:
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Header
        self._header = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12), anchor="w",
            text_color=("gray40", "gray70"),
        )
        self._header.grid(row=0, column=0, padx=16, pady=(12, 4), sticky="w")

        # Scrollbarer Bereich für die Zeilen
        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self._scroll.grid_columnconfigure(0, weight=1)

        # Footer
        self._build_footer()

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, padx=12, pady=(0, 12), sticky="ew")
        footer.grid_columnconfigure(1, weight=1)

        # Status-Info
        self._status_label = ctk.CTkLabel(
            footer, text="",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60"),
            anchor="w",
        )
        self._status_label.grid(row=0, column=0, sticky="w")

        # Buttons rechts
        btn_frame = ctk.CTkFrame(footer, fg_color="transparent")
        btn_frame.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            btn_frame,
            text="✕  24h pausieren",
            width=140,
            fg_color=("gray65", "gray25"),
            hover_color=("gray55", "gray35"),
            command=self._pause_and_close,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="✱  Weiter (nächste 10)",
            width=170,
            fg_color=("gray70", "gray30"),
            hover_color=("gray60", "gray40"),
            command=self._next_batch,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="✓  Schließen",
            width=120,
            command=self._on_close,
        ).pack(side="left")

        self.bind("<Escape>", lambda _: self._on_close())

    # ── Kandidaten laden & anzeigen ───────────────────────────────────────────

    def _load_candidates(self) -> None:
        """Lädt nächste Batch unbewerteter ISINs und baut Zeilen auf."""
        self._candidates = get_candidates(limit=_BATCH_SIZE)

        # Entscheidungs-Dict mit None initialisieren
        for c in self._candidates:
            if c.isin not in self._decisions:
                self._decisions[c.isin] = None

        self._rebuild_rows()
        self._update_header()

    def _rebuild_rows(self) -> None:
        """Löscht und baut alle Zeilen neu auf."""
        for widget in self._scroll.winfo_children():
            widget.destroy()

        if not self._candidates:
            ctk.CTkLabel(
                self._scroll,
                text="✓  Alle ISINs in diesem Zyklus bewertet.",
                font=ctk.CTkFont(size=13),
                text_color=("gray45", "gray65"),
            ).grid(row=0, column=0, pady=40)
            return

        dark    = ctk.get_appearance_mode() == "Dark"
        fg_main = "#e0e0e0" if dark else "#1a1a1a"
        fg_sub  = "#888888" if dark else "#666666"
        yield_color_high = "#66bb6a" if dark else "#1b5e20"
        yield_color_mid  = "#aed581" if dark else "#558b2f"

        # Spaltenbreiten
        self._scroll.grid_columnconfigure(0, minsize=44)   # Nr
        self._scroll.grid_columnconfigure(1, weight=1)     # Name
        self._scroll.grid_columnconfigure(2, minsize=140)  # ISIN/WKN
        self._scroll.grid_columnconfigure(3, minsize=80)   # Rendite
        self._scroll.grid_columnconfigure(4, minsize=60)   # Prio
        self._scroll.grid_columnconfigure(5, minsize=80)   # Ja
        self._scroll.grid_columnconfigure(6, minsize=80)   # Nein

        # Header-Zeile
        for col, text in enumerate(
            ["#", "Wertpapier", "ISIN / WKN", "Rendite", "Tier", "Ja", "Nein"]
        ):
            ctk.CTkLabel(
                self._scroll, text=text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=("gray45", "gray65"), anchor="w",
            ).grid(row=0, column=col, padx=(4, 4), pady=(4, 6), sticky="w")

        self._yes_btns:  dict[str, ctk.CTkButton] = {}
        self._no_btns:   dict[str, ctk.CTkButton] = {}

        for idx, c in enumerate(self._candidates, start=1):
            row = idx  # Datenzeilen ab Zeile 1

            # Zeilenhintergrund (abwechselnd)
            row_bg = ("gray88", "gray20") if idx % 2 == 0 else ("gray92", "gray17")

            # Nr
            ctk.CTkLabel(
                self._scroll, text=str(idx), anchor="center",
                font=ctk.CTkFont(size=11),
                fg_color=row_bg, corner_radius=0,
            ).grid(row=row, column=0, padx=(4, 0), pady=2, sticky="nsew")

            # Name (ggf. gekürzt)
            name = c.name[:48] + "…" if len(c.name) > 48 else c.name
            ctk.CTkLabel(
                self._scroll, text=name, anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=fg_main,
                fg_color=row_bg, corner_radius=0,
            ).grid(row=row, column=1, padx=(6, 4), pady=2, sticky="nsew")

            # ISIN/WKN
            isin_wkn = f"{c.isin}\n{c.wkn}" if c.wkn else c.isin
            ctk.CTkLabel(
                self._scroll, text=isin_wkn, anchor="w",
                font=ctk.CTkFont(size=10),
                text_color=fg_sub,
                fg_color=row_bg, corner_radius=0,
            ).grid(row=row, column=2, padx=4, pady=2, sticky="nsew")

            # Rendite (farbig je nach Tier)
            y_color = (
                yield_color_high if c.priority == 1
                else yield_color_mid if c.priority == 2
                else fg_main
            )
            ctk.CTkLabel(
                self._scroll, text=_fmt_yield(c.yield_bps), anchor="e",
                font=ctk.CTkFont(size=11),
                text_color=y_color,
                fg_color=row_bg, corner_radius=0,
            ).grid(row=row, column=3, padx=4, pady=2, sticky="nsew")

            # Priorität-Tier
            ctk.CTkLabel(
                self._scroll, text=_priority_label(c.priority), anchor="center",
                font=ctk.CTkFont(size=10),
                text_color=fg_sub,
                fg_color=row_bg, corner_radius=0,
            ).grid(row=row, column=4, padx=4, pady=2, sticky="nsew")

            # Ja-Button
            yes_btn = ctk.CTkButton(
                self._scroll, text="Ja", width=72, height=28,
                fg_color=_BTN_NONE_FG,
                hover_color=_BTN_YES_HOV,
                command=lambda isin=c.isin: self._toggle(isin, "S"),
            )
            yes_btn.grid(row=row, column=5, padx=4, pady=2)
            self._yes_btns[c.isin] = yes_btn

            # Nein-Button
            no_btn = ctk.CTkButton(
                self._scroll, text="Nein", width=72, height=28,
                fg_color=_BTN_NONE_FG,
                hover_color=_BTN_NO_HOV,
                command=lambda isin=c.isin: self._toggle(isin, "N"),
            )
            no_btn.grid(row=row, column=6, padx=(4, 8), pady=2)
            self._no_btns[c.isin] = no_btn

            # Bereits getroffene Entscheidung wiederherstellen
            self._refresh_buttons(c.isin)

    def _update_header(self) -> None:
        info = get_cycle_info()
        total     = info["total"]
        unreviewed = info["unreviewed"]
        reviewed  = total - unreviewed
        pct       = info["pct_done"]
        cycle     = info["cycle_start"] or "—"

        self._header.configure(
            text=(
                f"Zyklus seit {cycle}  |  "
                f"{reviewed:,} / {total:,} bewertet ({pct:.1f} %)  |  "
                f"{unreviewed:,} noch offen"
            )
        )

        decided = sum(1 for v in self._decisions.values() if v is not None)
        self._status_label.configure(
            text=f"{decided} von {len(self._candidates)} in diesem Batch entschieden"
        )

    # ── Button-Logik ──────────────────────────────────────────────────────────

    def _toggle(self, isin: str, value: str) -> None:
        """
        Togglet Ja/Nein.
        Zweimaliges Klicken desselben Buttons → zurück auf None.
        """
        current = self._decisions.get(isin)
        self._decisions[isin] = None if current == value else value
        self._refresh_buttons(isin)
        self._update_header()

    def _refresh_buttons(self, isin: str) -> None:
        """Aktualisiert Farben der Ja/Nein-Buttons für eine ISIN."""
        val = self._decisions.get(isin)
        yes_btn = self._yes_btns.get(isin)
        no_btn  = self._no_btns.get(isin)

        if yes_btn:
            yes_btn.configure(
                fg_color=_BTN_YES_FG if val == "S" else _BTN_NONE_FG
            )
        if no_btn:
            no_btn.configure(
                fg_color=_BTN_NO_FG if val == "N" else _BTN_NONE_FG
            )

    # ── Aktionen ──────────────────────────────────────────────────────────────

    def _save_current(self) -> None:
        """Speichert alle getroffenen Entscheidungen der aktuellen Batch."""
        to_save = {
            isin: val
            for isin, val in self._decisions.items()
            if val is not None
        }
        if to_save:
            mark_batch(to_save)
            if "S" in to_save.values():
                self._has_new_s = True
            logger.info(
                "Sparplan-Batch gespeichert: %d Entscheidungen.", len(to_save)
            )

    def _next_batch(self) -> None:
        """Speichert aktuelle Batch und lädt nächste 10 ISINs."""
        self._save_current()
        # Entscheidungs-Dict leeren für neue Batch
        self._decisions = {}
        self._load_candidates()

    def _pause_and_close(self) -> None:
        """Pausiert Popup für 24h und schließt."""
        set_paused(hours=24)
        self._save_current()
        self._close_and_notify()

    def _on_close(self) -> None:
        """Speichert und schließt."""
        self._save_current()
        self._close_and_notify()

    def _close_and_notify(self) -> None:
        if self._on_closed:
            self._on_closed(self._has_new_s)
        self.destroy()
