# Dateiname:     hypilot.py
# Version:       2026-04-22
# Abhängigkeiten (intern): gui.tabs.app
# Abhängigkeiten (extern): customtkinter
"""
hypilot.py

Einstiegspunkt für HYPilot.
Startet die GUI-Applikation.

Verwendung:
  python hypilot.py
  python -m hypilot        (wenn als Paket gewünscht)
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import customtkinter as ctk

# Projektverzeichnis in sys.path (für Import ohne Installation)
_PROJECT_ROOT = Path(__file__).parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Erscheinungsbild: System-Default
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")

    from gui.tabs.app import HYPilotApp
    app = HYPilotApp()
    app.mainloop()


if __name__ == "__main__":
    main()
