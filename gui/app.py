# Dateiname:     gui/app.py
# Version:       2026-05-17-sparplan
# Abhängigkeiten (intern): gui.tabs.universe_tab, gui.tabs.high_yield_tab,
#                          gui.tabs.analyse_tab, gui.tabs.watchlist_tab,
#                          gui.tabs.portfolio_tab, gui.tabs.info_tab,
#                          db.sparplan_repository
# Abhängigkeiten (extern): customtkinter
"""
gui/app.py

Neu 2026-05-17: Sparplan-Scheduler.

Scheduler-Logik:
  - Prüft alle 60 Sekunden ob ein Sparplan-Popup geöffnet werden soll.
  - Bedingungen (alle müssen erfüllt sein):
      1. Aktuell kein Popup offen
      2. Nicht pausiert (24h-Sperre)
      3. Aktuell im Handelszeitfenster (Mo–Fr 08:00–13:00, 15:00–16:30)
      4. Mindestens 10 Minuten seit App-Start vergangen
      5. Mindestens 30 Minuten seit letztem Popup vergangen
      6. Noch unbewertete ISINs vorhanden
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import customtkinter as ctk

from gui.tabs.universe_tab   import UniverseTab
from gui.tabs.high_yield_tab import HighYieldTab
from gui.tabs.analyse_tab    import AnalyseTab
from gui.tabs.watchlist_tab  import WatchlistTab
from gui.tabs.portfolio_tab  import PortfolioTab
from gui.tabs.info_tab       import InfoTab

logger = logging.getLogger(__name__)

DB_PATH: Path = Path("/home/luzy/workspace/openclaw-min/db/hypilot.db")

_DEFAULT_GEOMETRY = "1440x900"
_GEO_KEY          = "gui_geometry"

# ── Scheduler-Konstanten ──────────────────────────────────────────────────────

_SCHEDULER_INTERVAL_MS  = 60_000   # 60 Sekunden zwischen Prüfungen
_STARTUP_DELAY_MIN      = 10       # Mindest-Wartezeit nach Start (Minuten)
_POPUP_INTERVAL_MIN     = 30       # Mindest-Abstand zwischen Popups (Minuten)

# Handelszeitfenster: (start_h, start_min, end_h, end_min)
_TRADING_WINDOWS = [
    (8,  0,  13, 0),
    (15, 0,  16, 30),
]


class HYPilotApp(ctk.CTk):
    """Hauptfenster der HYPilot-Applikation."""

    def __init__(self) -> None:
        super().__init__()

        self.title("HYPilot")
        self.minsize(900, 600)

        self._restore_geometry()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_menu_bar()
        self._build_tab_view()
        self._build_status_bar()

        # Sparplan-Scheduler
        self._sparplan_popup_open: bool      = False
        self._app_start_time:      datetime  = datetime.now()
        self._last_popup_time:     datetime | None = None

        self.after(800,                    self._startup_checks)
        self.after(_SCHEDULER_INTERVAL_MS, self._sparplan_tick)

    # ── Geometrie ─────────────────────────────────────────────────────────────

    def _restore_geometry(self) -> None:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT value FROM metadata WHERE key = ?", (_GEO_KEY,)
                ).fetchone()
            self.geometry(row[0] if row else _DEFAULT_GEOMETRY)
        except sqlite3.Error:
            self.geometry(_DEFAULT_GEOMETRY)

    def _save_geometry(self) -> None:
        try:
            geo = self.geometry()
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    """
                    INSERT INTO metadata (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (_GEO_KEY, geo),
                )
                conn.commit()
        except sqlite3.Error:
            logger.warning("Fenstergeometrie konnte nicht gespeichert werden.")

    # ── Menüleiste ────────────────────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=36, corner_radius=0)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        for label, command in {
            "Datei":   self._menu_datei,
            "Ansicht": None,
            "Extras":  None,
            "Hilfe":   None,
        }.items():
            ctk.CTkButton(
                bar,
                text=label,
                width=72, height=30,
                fg_color="transparent",
                hover_color=("gray80", "gray30"),
                corner_radius=4,
                command=command,
            ).pack(side="left", padx=2, pady=3)

    def _menu_datei(self) -> None:
        pass

    # ── Tab-View ──────────────────────────────────────────────────────────────

    def _build_tab_view(self) -> None:
        self._tab_view = ctk.CTkTabview(self, corner_radius=4)
        self._tab_view.pack(fill="both", expand=True, padx=6)

        self._tab_view.add("TR-Universum")
        self._universe_tab = UniverseTab(self._tab_view.tab("TR-Universum"))
        self._universe_tab.pack(fill="both", expand=True)

        self._tab_view.add("High-Yield ≥10 %")
        self._high_yield_tab = HighYieldTab(self._tab_view.tab("High-Yield ≥10 %"))
        self._high_yield_tab.pack(fill="both", expand=True)

        self._tab_view.add("Analyse")
        self._analyse_tab = AnalyseTab(self._tab_view.tab("Analyse"))
        self._analyse_tab.pack(fill="both", expand=True)

        self._tab_view.add("Watchlist")
        self._watchlist_tab = WatchlistTab(self._tab_view.tab("Watchlist"))
        self._watchlist_tab.pack(fill="both", expand=True)

        self._tab_view.add("Portfolio")
        self._portfolio_tab = PortfolioTab(self._tab_view.tab("Portfolio"))
        self._portfolio_tab.pack(fill="both", expand=True)

        self._tab_view.add("Info")
        self._info_tab = InfoTab(self._tab_view.tab("Info"))
        self._info_tab.pack(fill="both", expand=True)

        self._universe_tab.set_watchlist_tab(self._watchlist_tab)
        self._high_yield_tab.set_watchlist_tab(self._watchlist_tab)

    # ── Statusleiste ──────────────────────────────────────────────────────────

    def _build_status_bar(self) -> None:
        bar = ctk.CTkFrame(self, height=26, corner_radius=0)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._status_label = ctk.CTkLabel(
            bar, text="",
            text_color=("gray45", "gray65"),
            font=ctk.CTkFont(size=11),
            anchor="w",
        )
        self._status_label.pack(side="left", padx=10)

    def _set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    # ── Startup-Checks ────────────────────────────────────────────────────────

    def _load_last_run_summary(self) -> str:
        try:
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT value FROM metadata WHERE key = 'last_auto_run'"
                ).fetchone()
            if not row:
                return ""
            data      = json.loads(row[0])
            run_at    = data.get("run_at", "")[:16].replace("T", " ")
            stats     = data.get("stats", {})
            crossings = data.get("crossings", 0)
            return (
                f"Letzter Auto-Lauf: {run_at}  |  "
                f"{stats.get('updated', 0)} aktualisiert  |  "
                f"{crossings} Schwellwert-Änderung(en)"
            )
        except Exception:
            return ""

    def _startup_checks(self) -> None:
        summary = self._load_last_run_summary()
        if summary:
            self._set_status(summary)

        try:
            from db.dividend_repository import get_unshown_threshold_crossings
            crossings = get_unshown_threshold_crossings()
        except Exception:
            logger.exception("Fehler beim Laden der Threshold-Crossings.")
            return

        if crossings:
            self._open_threshold_popup()

    def _open_threshold_popup(self) -> None:
        from gui.widgets.threshold_crossing_popup import ThresholdCrossingPopup
        ThresholdCrossingPopup(self, on_closed=self._on_threshold_popup_closed)

    def _on_threshold_popup_closed(self) -> None:
        summary = self._load_last_run_summary()
        if summary:
            self._set_status(summary)

    # ── Sparplan-Scheduler ────────────────────────────────────────────────────

    def _sparplan_tick(self) -> None:
        """
        Wird alle 60 Sekunden aufgerufen.
        Prüft alle Bedingungen und öffnet ggf. das Sparplan-Popup.
        """
        try:
            if self._should_open_sparplan_popup():
                self._open_sparplan_popup()
        except Exception:
            logger.exception("Fehler im Sparplan-Scheduler.")
        finally:
            self.after(_SCHEDULER_INTERVAL_MS, self._sparplan_tick)

    def _should_open_sparplan_popup(self) -> bool:
        """Prüft alle Bedingungen für das Sparplan-Popup."""

        # 1. Kein Popup bereits offen
        if self._sparplan_popup_open:
            return False

        # 2. Nicht pausiert
        from db.sparplan_repository import is_paused, count_unreviewed
        if is_paused():
            return False

        # 3. Im Handelszeitfenster (Mo–Fr)
        if not self._in_trading_window():
            return False

        # 4. Mindestens 10 Minuten seit App-Start
        if not self._startup_delay_passed():
            return False

        # 5. Mindestens 30 Minuten seit letztem Popup
        if not self._popup_interval_elapsed():
            return False

        # 6. Noch unbewertete ISINs vorhanden
        if count_unreviewed() == 0:
            return False

        return True

    def _in_trading_window(self) -> bool:
        """True wenn aktuell Werktag und im Handelszeitfenster."""
        now = datetime.now()
        if now.weekday() >= 5:  # Sa=5, So=6
            return False
        for sh, sm, eh, em in _TRADING_WINDOWS:
            start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
            end   = now.replace(hour=eh, minute=em, second=0, microsecond=0)
            if start <= now < end:
                return True
        return False

    def _startup_delay_passed(self) -> bool:
        """True wenn mindestens _STARTUP_DELAY_MIN Minuten seit Start."""
        elapsed = (datetime.now() - self._app_start_time).total_seconds()
        return elapsed >= _STARTUP_DELAY_MIN * 60

    def _popup_interval_elapsed(self) -> bool:
        """True wenn mindestens _POPUP_INTERVAL_MIN Minuten seit letztem Popup."""
        if self._last_popup_time is None:
            return True
        elapsed = (datetime.now() - self._last_popup_time).total_seconds()
        return elapsed >= _POPUP_INTERVAL_MIN * 60

    def _open_sparplan_popup(self) -> None:
        """Öffnet das Sparplan-Popup und setzt Zeitstempel."""
        from gui.widgets.sparplan_popup import SparplanPopup

        self._sparplan_popup_open = True
        self._last_popup_time     = datetime.now()

        logger.info("Sparplan-Popup wird geöffnet.")

        SparplanPopup(
            self,
            on_closed=self._on_sparplan_popup_closed,
        )

    def _on_sparplan_popup_closed(self, reload_universe: bool) -> None:
        """Callback nach Schließen des Sparplan-Popups."""
        self._sparplan_popup_open = False
        logger.info(
            "Sparplan-Popup geschlossen (reload_universe=%s).", reload_universe
        )
        if reload_universe:
            self._universe_tab.reload_data()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        self._save_geometry()
        self.destroy()
