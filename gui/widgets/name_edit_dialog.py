# Dateiname:     gui/widgets/name_edit_dialog.py
# Version:       2026-05-08-fix1
# Abhängigkeiten (intern): db.instrument_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/widgets/name_edit_dialog.py

Modaler Dialog zum manuellen Bearbeiten des Wertpapiernamens.

Öffnet sich via Doppelklick auf eine Tabellenzeile.
Zeigt Original-PDF-Name + aktuellen Override.
Leeres Feld = Override löschen (PDF-Name wird wieder angezeigt).

Fix 2026-05-08: CTkToplevel-Timing-Problem behoben.
  _build() + _load() werden via after(20) verzögert ausgeführt,
  grab_set() erst via after(50) — verhindert leeres graues Fenster
  in CustomTkinter >= 5.2.
"""

from __future__ import annotations

import logging
from typing import Callable

import customtkinter as ctk

from db.instrument_repository import get_instrument_names, set_name_override

logger = logging.getLogger(__name__)


class NameEditDialog(ctk.CTkToplevel):
    """
    Modaler Dialog für manuelle Namensänderung.

    Args:
        master:      Eltern-Widget
        isin:        ISIN des zu bearbeitenden Instruments
        on_saved:    Callback nach erfolgreichem Speichern (kein Argument)
    """

    def __init__(
        self,
        master: ctk.CTk | ctk.CTkFrame,
        isin: str,
        on_saved: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(master)

        self._isin     = isin
        self._on_saved = on_saved

        self.title("Name bearbeiten")
        self.geometry("520x280")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # Verzögerter Aufbau: Fenster muss vom Window-Manager
        # gemappt sein bevor Widgets erstellt und grab_set() aufgerufen wird.
        self.after(20, self._build)
        self.after(20, self._load)
        self.after(50, self._make_modal)

    def _make_modal(self) -> None:
        """Setzt Modal-Verhalten nach vollständigem Rendern."""
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        self.grid_columnconfigure(1, weight=1)

        # ISIN (readonly)
        ctk.CTkLabel(self, text="ISIN:", anchor="w").grid(
            row=0, column=0, padx=(20, 8), pady=(20, 4), sticky="w"
        )
        ctk.CTkLabel(
            self,
            text=self._isin,
            text_color=("gray40", "gray70"),
            anchor="w",
        ).grid(row=0, column=1, columnspan=2, padx=(0, 20), pady=(20, 4),
               sticky="w")

        # Original-Name (readonly)
        ctk.CTkLabel(self, text="PDF-Name:", anchor="w").grid(
            row=1, column=0, padx=(20, 8), pady=(0, 4), sticky="w"
        )
        self._original_label = ctk.CTkLabel(
            self,
            text="",
            text_color=("gray40", "gray70"),
            anchor="w",
        )
        self._original_label.grid(
            row=1, column=1, columnspan=2, padx=(0, 20), pady=(0, 4),
            sticky="w"
        )

        # Neuer Name
        ctk.CTkLabel(self, text="Mein Name:", anchor="w").grid(
            row=2, column=0, padx=(20, 8), pady=(8, 4), sticky="w"
        )
        self._name_entry = ctk.CTkEntry(
            self,
            width=300,
            placeholder_text="Leer lassen = PDF-Name verwenden",
        )
        self._name_entry.grid(
            row=2, column=1, columnspan=2, padx=(0, 20), pady=(8, 4),
            sticky="ew"
        )

        # Hinweis
        self._hint_label = ctk.CTkLabel(
            self,
            text="",
            text_color=("gray50", "gray60"),
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._hint_label.grid(
            row=3, column=1, columnspan=2, padx=(0, 20), pady=(0, 12),
            sticky="w"
        )

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(
            row=4, column=0, columnspan=3, padx=20, pady=(0, 20), sticky="ew"
        )
        btn_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            btn_frame,
            text="Abbrechen",
            width=110,
            fg_color="transparent",
            border_width=1,
            command=self.destroy,
        ).grid(row=0, column=1, padx=(0, 8))

        ctk.CTkButton(
            btn_frame,
            text="Speichern",
            width=110,
            command=self._save,
        ).grid(row=0, column=2)

        # Enter = Speichern, Escape = Abbrechen
        self.bind("<Return>",  lambda _: self._save())
        self.bind("<Escape>",  lambda _: self.destroy())

    def _load(self) -> None:
        """Lädt aktuelle Namen aus der DB."""
        data = get_instrument_names(self._isin)
        if not data:
            logger.warning("Instrument %s nicht gefunden.", self._isin)
            self.destroy()
            return

        self._original_label.configure(text=data["name"])

        if data["name_override"]:
            self._name_entry.insert(0, data["name_override"])
            self._hint_label.configure(
                text="✎ Manueller Name aktiv — leer lassen für Original"
            )
        else:
            self._hint_label.configure(
                text="Kein manueller Name gesetzt"
            )

    def _save(self) -> None:
        """Speichert den neuen Namen und schließt den Dialog."""
        new_name = self._name_entry.get().strip()
        set_name_override(self._isin, new_name)

        if new_name:
            logger.info("Name-Override gesetzt: %s → %r", self._isin, new_name)
        else:
            logger.info("Name-Override gelöscht: %s", self._isin)

        if self._on_saved:
            self._on_saved()
        self.destroy()