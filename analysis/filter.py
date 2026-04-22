# Dateiname:     analysis/filter.py
# Version:       2026-04-22
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine
"""
analysis/filter.py

Vorfilter für das TR-Instrument-Universum.
Entfernt Parser-Artefakte, Hochrisiko-Produkte und nicht
investierbare Instrumente bevor das Scoring läuft.
"""

from __future__ import annotations

import re

# Namen die mit diesen Mustern beginnen sind Parser-Artefakte
_ARTIFACT_PREFIX = re.compile(r"^\d")          # beginnt mit Ziffer

# Mindestlänge für sinnvolle Namen (nach Bereinigung)
_MIN_NAME_LENGTH = 6

# Harte Ausschlüsse
_EXCLUDE_KEYWORDS: tuple[str, ...] = (
    "short",
    "covered call",
    "swap",
    "turbo",
    "knock",
    "warrant",
    "certificate",
    "zertifikat",
)


def is_investable(inst: dict) -> bool:
    """
    Gibt True zurück wenn das Instrument für die Analyse in Frage kommt.

    Ausschlussgründe:
      - Name beginnt mit Ziffer (Parser-Artefakt)
      - Name zu kurz (< 6 Zeichen)
      - Enthält Hochrisiko-Schlüsselwörter
    """
    name: str = inst.get("name", "")
    name_lower = name.lower()

    # Parser-Artefakte (z.B. "100 (Acc)", "100 EUR (Acc)")
    if _ARTIFACT_PREFIX.match(name):
        return False

    # Zu kurze Namen
    if len(name) < _MIN_NAME_LENGTH:
        return False

    # Hochrisiko / nicht investierbar
    if any(kw in name_lower for kw in _EXCLUDE_KEYWORDS):
        return False

    return True
