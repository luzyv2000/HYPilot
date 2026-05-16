# Dateiname:     gui/tabs/info_tab.py
# Version:       2026-05-16
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): customtkinter
"""
gui/tabs/info_tab.py

Info-Tab für HYPilot.

Inhalt:
  1. Version & System      — HYPilot-Version, Python, DB-Pfad, DB-Größe
  2. Datenquellen-Status   — API-Keys konfiguriert (ja/nein), letzter Lauf
  3. Drittanbieter         — verwendete Bibliotheken + Lizenzen
  4. Copyright & Lizenz    — Urheberrecht, MIT-Lizenz
  5. Haftungsausschluss    — Disclaimer (keine Anlageberatung)
  6. Datenschutz           — lokale Verarbeitung, keine Drittübermittlung
  7. Datentransfer         — zukünftige Synchronisation zwischen Geräten
  8. Bekannte Einschränkungen

Alle Informationen sind statisch oder werden beim Tab-Öffnen
einmalig aus DB/Umgebung gelesen (kein Netzwerk, kein Threading).
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import sys
from pathlib import Path
from typing import Any

import customtkinter as ctk

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_VERSION     = "2026-05-16"
_GITHUB_URL  = "https://github.com/luzyv2000/HYPilot"
_AUTHOR      = "Luzy"
_YEAR        = "2026"


# ── Drittanbieter-Bibliotheken ────────────────────────────────────────────────

_THIRD_PARTY: list[tuple[str, str, str]] = [
    ("customtkinter",   "MIT",     "https://github.com/TomSchimansky/CustomTkinter"),
    ("yfinance",        "Apache 2.0", "https://github.com/ranaroussi/yfinance"),
    ("requests",        "Apache 2.0", "https://github.com/psf/requests"),
    ("python-dotenv",   "BSD-3",   "https://github.com/theskumar/python-dotenv"),
    ("hypothesis",      "MPL 2.0", "https://github.com/HypothesisWorks/hypothesis"),
    ("pytest",          "MIT",     "https://github.com/pytest-dev/pytest"),
    ("python-dateutil", "Apache 2.0", "https://github.com/dateutil/dateutil"),
    ("pdfplumber",      "MIT",     "https://github.com/jsvine/pdfplumber"),
    ("responses",       "Apache 2.0", "https://github.com/getsentry/responses"),
]


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _db_size_str(db_path: Path) -> str:
    try:
        size = db_path.stat().st_size
        if size >= 1_048_576:
            return f"{size / 1_048_576:.1f} MB"
        return f"{size / 1_024:.0f} KB"
    except OSError:
        return "—"


def _last_auto_run() -> str:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT value FROM metadata WHERE key = 'last_auto_run'"
            ).fetchone()
        if not row:
            return "Noch kein Lauf aufgezeichnet"
        data   = json.loads(row[0])
        run_at = data.get("run_at", "")[:16].replace("T", "  ")
        stats  = data.get("stats", {})
        return (
            f"{run_at}  |  "
            f"{stats.get('updated', 0)} aktualisiert, "
            f"{stats.get('skipped', 0)} übersprungen"
        )
    except Exception:
        return "—"


def _api_status() -> list[tuple[str, str, str]]:
    """Gibt Liste von (Name, Status-Text, Farbe) zurück."""
    results = []

    divvy_key = os.getenv("DIVVYDIARY_API_KEY", "").strip()
    if divvy_key:
        results.append(("DivvyDiary API", "✓  API-Key konfiguriert", "ok"))
    else:
        results.append(("DivvyDiary API", "✗  Kein API-Key — Fallback auf yfinance", "warn"))

    openfigi_key = os.getenv("OPENFIGI_API_KEY", "").strip()
    if openfigi_key:
        results.append(("OpenFIGI API", "✓  API-Key konfiguriert", "ok"))
    else:
        results.append(("OpenFIGI API", "○  Kein API-Key — anonymer Zugang (Rate-Limit)", "neutral"))

    results.append(("yfinance", "✓  Kein API-Key erforderlich", "ok"))

    smtp_host = os.getenv("SMTP_HOST", "").strip()
    if smtp_host:
        results.append(("SMTP (E-Mail)", f"✓  Konfiguriert ({smtp_host})", "ok"))
    else:
        results.append(("SMTP (E-Mail)", "✗  Nicht konfiguriert — kein E-Mail-Versand", "warn"))

    return results


# ── Hauptklasse ───────────────────────────────────────────────────────────────

class InfoTab(ctk.CTkFrame):
    """Info-Tab mit rechtlichen Hinweisen, Systemstatus und Drittanbieter-Info."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._build()

    def _build(self) -> None:
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        row = 0

        # ── 1. Version & System ───────────────────────────────────────────────
        row = self._section(scroll, row, "⚙️  Version & System")
        row = self._kv_grid(scroll, row, [
            ("HYPilot Version",  _VERSION),
            ("GitHub",           _GITHUB_URL),
            ("Python",           f"{sys.version.split()[0]}  ({platform.python_implementation()})"),
            ("Plattform",        f"{platform.system()} {platform.release()}"),
            ("Datenbank",        str(DB_PATH)),
            ("DB-Größe",         _db_size_str(DB_PATH)),
            ("Letzter Auto-Lauf", _last_auto_run()),
        ])

        # ── 2. Datenquellen-Status ────────────────────────────────────────────
        row = self._section(scroll, row, "🔌  Datenquellen-Status")
        row = self._api_status_block(scroll, row)

        # ── 3. Drittanbieter-Bibliotheken ─────────────────────────────────────
        row = self._section(scroll, row, "📦  Verwendete Bibliotheken")
        row = self._library_table(scroll, row)

        # ── 4. Copyright & Lizenz ─────────────────────────────────────────────
        row = self._section(scroll, row, "©  Copyright & Lizenz")
        row = self._text_block(scroll, row,
            f"Copyright © {_YEAR} {_AUTHOR}. Alle Rechte vorbehalten.\n\n"
            "HYPilot wird unter der MIT-Lizenz veröffentlicht.\n\n"
            "MIT License\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy "
            "of this software and associated documentation files (the \"Software\"), to deal "
            "in the Software without restriction, including without limitation the rights "
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell "
            "copies of the Software, and to permit persons to whom the Software is "
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all "
            "copies or substantial portions of the Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR "
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, "
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT."
        )

        # ── 5. Haftungsausschluss ─────────────────────────────────────────────
        row = self._section(scroll, row, "⚠️  Haftungsausschluss")
        row = self._disclaimer_block(scroll, row)

        # ── 6. Datenschutz ────────────────────────────────────────────────────
        row = self._section(scroll, row, "🔒  Datenschutzhinweise")
        row = self._text_block(scroll, row,
            "HYPilot erhebt, verarbeitet und speichert ausschließlich Finanzdaten "
            "(Kurse, Dividendeninformationen, Depotdaten) zu privaten Analysezwecken.\n\n"
            "• Es werden keine personenbezogenen Daten gesammelt.\n"
            "• Es findet keine Übermittlung von Daten an Dritte statt.\n"
            "• Alle Daten (Depotdaten, historische Kurse, generierte Empfehlungen und "
            "Scores) werden ausschließlich lokal auf diesem Gerät gespeichert und "
            "verarbeitet.\n"
            "• API-Anfragen an externe Dienste (yfinance, DivvyDiary, OpenFIGI) enthalten "
            "ausschließlich ISIN- und Ticker-Symbole — keine personenbezogenen Daten.\n"
            "• Zugangsdaten (API-Keys, SMTP-Credentials) werden ausschließlich in der "
            "lokalen .env-Datei gespeichert und niemals protokolliert oder übertragen."
        )

        # ── 7. Datentransfer / Synchronisation ────────────────────────────────
        row = self._section(scroll, row, "🔄  Datentransfer & Synchronisation")
        row = self._text_block(scroll, row,
            "Aktuell (Version " + _VERSION + "):\n"
            "HYPilot ist als Single-Device-Anwendung konzipiert. Alle Daten werden "
            "lokal gespeichert. Es findet keine automatische Synchronisation statt.\n\n"
            "Geplant (zukünftige Version):\n"
            "Um die Funktionalität über mehrere Geräte hinweg zu gewährleisten, ist "
            "ein optionaler Datenaustausch zwischen installierten HYPilot-Instanzen "
            "vorgesehen. Dabei sollen ausschließlich Finanzdaten (Kurse, Scores, "
            "Portfolio-Positionen) synchronisiert werden — keine personenbezogenen Daten. "
            "Der Nutzer behält die vollständige Kontrolle darüber, ob und mit welchen "
            "Geräten eine Synchronisation stattfindet. Details werden vor Einführung "
            "dieser Funktion transparent kommuniziert."
        )

        # ── 8. Bekannte Einschränkungen ───────────────────────────────────────
        row = self._section(scroll, row, "ℹ️  Bekannte Einschränkungen")
        row = self._text_block(scroll, row,
            "• yfinance: Kein offizieller API-Vertrag mit Yahoo Finance. "
            "Datenverfügbarkeit und -qualität nicht garantiert. Gelegentliche "
            "HTTP-500-Fehler werden automatisch mit Exponential Backoff wiederholt.\n\n"
            "• DivvyDiary Free Tier: ~100 Anfragen/Tag. Bei Überschreitung "
            "fällt HYPilot automatisch auf yfinance zurück.\n\n"
            "• Rendite-Plausibilitäts-Cap: Dividendenrenditen über 50 % werden "
            "als Datenfehler gewertet und verworfen (Sonderausschüttungen, "
            "Kapitalrückzahlungen).\n\n"
            "• Keine Echtzeit-Kurse: Alle Daten sind verzögert und dienen "
            "ausschließlich der historischen Analyse.\n\n"
            "• SQLite: Die Datenbank ist nicht für gleichzeitigen Schreibzugriff "
            "von mehreren Prozessen optimiert. GUI-Batch und systemd-Timer "
            "sollten nicht gleichzeitig laufen."
        )

        # Abstand am Ende
        ctk.CTkFrame(scroll, height=24, fg_color="transparent").grid(
            row=row, column=0
        )

    # ── Layout-Helfer ─────────────────────────────────────────────────────────

    def _section(self, parent: Any, row: int, title: str) -> int:
        """Sektion-Header mit Trennlinie. Gibt nächste Zeile zurück."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(16, 4))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text=title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkFrame(
            frame, height=1, fg_color=("gray70", "gray40")
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

        return row + 1

    def _kv_grid(
        self, parent: Any, row: int, pairs: list[tuple[str, str]]
    ) -> int:
        """Key-Value-Tabelle."""
        frame = ctk.CTkFrame(parent, fg_color=("gray92", "gray17"),
                              corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        frame.grid_columnconfigure(1, weight=1)

        dark = ctk.get_appearance_mode() == "Dark"
        key_color = ("gray45", "gray65")
        val_color = ("gray10", "gray90")

        for i, (key, val) in enumerate(pairs):
            ctk.CTkLabel(
                frame, text=f"{key}:", anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=key_color, width=180,
            ).grid(row=i, column=0, padx=(12, 8), pady=3, sticky="w")
            ctk.CTkLabel(
                frame, text=val, anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=val_color,
            ).grid(row=i, column=1, padx=(0, 12), pady=3, sticky="w")

        return row + 1

    def _api_status_block(self, parent: Any, row: int) -> int:
        """API-Status-Block mit farbigen Indikatoren."""
        frame = ctk.CTkFrame(parent, fg_color=("gray92", "gray17"),
                              corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        frame.grid_columnconfigure(1, weight=1)

        dark = ctk.get_appearance_mode() == "Dark"
        colors = {
            "ok":      "#66bb6a" if dark else "#1b5e20",
            "warn":    "#ef5350" if dark else "#b71c1c",
            "neutral": "#ffb74d" if dark else "#e65100",
        }

        for i, (name, status, kind) in enumerate(_api_status()):
            ctk.CTkLabel(
                frame, text=name, anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=("gray45", "gray65"), width=180,
            ).grid(row=i, column=0, padx=(12, 8), pady=3, sticky="w")
            ctk.CTkLabel(
                frame, text=status, anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=colors.get(kind, ("gray10", "gray90")),
            ).grid(row=i, column=1, padx=(0, 12), pady=3, sticky="w")

        return row + 1

    def _library_table(self, parent: Any, row: int) -> int:
        """Tabelle der Drittanbieter-Bibliotheken."""
        frame = ctk.CTkFrame(parent, fg_color=("gray92", "gray17"),
                              corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        frame.grid_columnconfigure(2, weight=1)

        dark = ctk.get_appearance_mode() == "Dark"
        key_color = ("gray45", "gray65")
        lic_color = ("gray35", "gray70")

        # Header
        for col, text in enumerate(["Bibliothek", "Lizenz", "Quelle"]):
            ctk.CTkLabel(
                frame, text=text, anchor="w",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=key_color,
            ).grid(row=0, column=col, padx=(12 if col == 0 else 8, 8),
                   pady=(8, 2), sticky="w")

        for i, (lib, lic, url) in enumerate(_THIRD_PARTY, start=1):
            ctk.CTkLabel(
                frame, text=lib, anchor="w",
                font=ctk.CTkFont(size=11),
            ).grid(row=i, column=0, padx=(12, 8), pady=2, sticky="w")
            ctk.CTkLabel(
                frame, text=lic, anchor="w",
                font=ctk.CTkFont(size=11),
                text_color=lic_color,
            ).grid(row=i, column=1, padx=(0, 8), pady=2, sticky="w")
            ctk.CTkLabel(
                frame, text=url, anchor="w",
                font=ctk.CTkFont(size=10),
                text_color=("gray50", "gray60"),
            ).grid(row=i, column=2, padx=(0, 12), pady=2, sticky="w")

        # Abstand unten
        ctk.CTkFrame(frame, height=6, fg_color="transparent").grid(
            row=len(_THIRD_PARTY) + 1, column=0
        )

        return row + 1

    def _text_block(self, parent: Any, row: int, text: str) -> int:
        """Fließtext-Block."""
        frame = ctk.CTkFrame(parent, fg_color=("gray92", "gray17"),
                              corner_radius=6)
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text=text,
            font=ctk.CTkFont(size=11),
            anchor="w", justify="left",
            wraplength=860,
        ).grid(row=0, column=0, padx=14, pady=10, sticky="w")

        return row + 1

    def _disclaimer_block(self, parent: Any, row: int) -> int:
        """Hervorgehobener Disclaimer-Block."""
        dark = ctk.get_appearance_mode() == "Dark"

        frame = ctk.CTkFrame(
            parent,
            fg_color=("#fff3cd", "#3d2e00") if not dark else ("#3d2e00", "#3d2e00"),
            corner_radius=6,
            border_width=1,
            border_color=("#e6a817", "#a07000"),
        )
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 4))
        frame.grid_columnconfigure(0, weight=1)

        disclaimer = (
            "HYPilot ist ein privates Analyse-Werkzeug und stellt KEINE "
            "Anlageberatung, Finanzberatung oder Handelsempfehlung dar.\n\n"
            "Alle von HYPilot generierten Scores, Ratings und Renditeangaben "
            "basieren auf automatisiert abgerufenen Daten Dritter (Yahoo Finance, "
            "DivvyDiary, OpenFIGI) und können fehlerhaft, veraltet oder "
            "unvollständig sein.\n\n"
            "Investitionsentscheidungen auf Basis dieser Daten erfolgen "
            "ausschließlich auf eigenes Risiko. Der Entwickler übernimmt "
            "keinerlei Haftung für finanzielle Verluste, die aus der Nutzung "
            "von HYPilot entstehen.\n\n"
            "Vergangene Dividendenrenditen sind kein verlässlicher Indikator "
            "für zukünftige Erträge. Kapitalverluste sind möglich."
        )

        warn_color = "#856404" if not dark else "#ffb74d"

        ctk.CTkLabel(
            frame, text="⚠  WICHTIGER HINWEIS",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=warn_color, anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        ctk.CTkLabel(
            frame, text=disclaimer,
            font=ctk.CTkFont(size=11),
            text_color=("gray15", "gray85"),
            anchor="w", justify="left",
            wraplength=860,
        ).grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")

        return row + 1
