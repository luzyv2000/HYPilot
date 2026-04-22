# Dateiname:     analysis/rules.py
# Version:       2026-04-22-fix2
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine
"""
analysis/rules.py

Klassifikation und heuristischer Name-Score für TR-Instrumente.

ETF-Erkennung (rein name-basiert — ISIN-Präfix zu unzuverlässig):
  1. Schlüsselwort "etf" / "ucits" im Namen
  2. Bekannte ETF-Anbieter (iShares, Vanguard, Xtrackers, ...)
  3. Struktursuffix (Acc) oder (Dist) am Namensende — typisch für
     UCITS-ETF-Anteilsklassen, selten bei Einzelaktien
"""

from __future__ import annotations

import re

# ── ETF-Erkennungsregeln ──────────────────────────────────────────────────────

_ETF_KEYWORDS: frozenset[str] = frozenset({
    "etf", "ucits", "index fund",
})

_ETF_PROVIDERS: frozenset[str] = frozenset({
    "ishares", "vanguard", "xtrackers", "amundi", "invesco",
    "lyxor", "spdr", "wisdomtree", "vaneck", "dws", "pimco",
    "dimensional", "hsbc etf", "legal & general", "l&g",
    "fidelity index", "jp morgan etf", "blackrock",
})

# (Acc) oder (Dist) am Ende — starkes ETF-Signal, kaum Fehlalarme
_ETF_SUFFIX_PATTERN: re.Pattern[str] = re.compile(
    r"\((acc|dist)\)\s*$", re.IGNORECASE
)


def _is_etf(name: str) -> bool:
    """
    Erkennt ETFs rein über den Namen.
    ISIN-Präfix wird bewusst nicht verwendet (IE = Irland,
    auch Domizil vieler Einzelaktien → zu viele Fehlalarme).
    """
    name_lower = name.lower()

    if any(kw in name_lower for kw in _ETF_KEYWORDS):
        return True

    if any(p in name_lower for p in _ETF_PROVIDERS):
        return True

    if _ETF_SUFFIX_PATTERN.search(name):
        return True

    return False


# ── Klassifikation ────────────────────────────────────────────────────────────

def classify_instrument(name: str, isin: str = "") -> str:
    """
    Klassifiziert ein Instrument anhand des Namens.

    Reihenfolge ist entscheidend: spezifischere Kategorien
    (DERIVATIVE, OPTION_STRATEGY) werden vor ETF geprüft,
    da ETF-Muster wie (Dist) sonst zu Fehlklassifikationen führen.

    Returns:
        "ETF" | "BOND" | "DERIVATIVE" | "OPTION_STRATEGY" | "STOCK"
    """
    name_lower = name.lower()

    # Spezifische Ausschlüsse zuerst — vor ETF-Erkennung
    if any(kw in name_lower for kw in ("lev", "3x", "2x", "turbo", "knock")):
        return "DERIVATIVE"

    if "covered call" in name_lower:
        return "OPTION_STRATEGY"

    # ETF-Erkennung (nach Ausschlüssen)
    if _is_etf(name):
        return "ETF"

    if any(kw in name_lower for kw in ("bond", "t-bil", "treasury", "gilts")):
        return "BOND"

    if "yield" in name_lower and "etf" not in name_lower:
        return "BOND"

    return "STOCK"

# ── Name-Score ────────────────────────────────────────────────────────────────

def score_instrument(name: str, isin: str = "") -> int:
    """
    Heuristischer Score für Universe-Vorfilterung.
    Kein Ersatz für Dividenden-Scoring.
    """
    score = 0
    name_lower = name.lower()

    if _is_etf(name):
        score += 5

    if "msci world" in name_lower:
        score += 4
    elif "msci" in name_lower:
        score += 2

    if "s&p 500" in name_lower or "s&p500" in name_lower:
        score += 3

    if "world" in name_lower:
        score += 1

    if any(kw in name_lower for kw in ("lev", "3x", "2x", "turbo")):
        score -= 6
    if "short" in name_lower:
        score -= 4
    if "covered call" in name_lower:
        score -= 2
    if "high yield" in name_lower:
        score -= 2

    if len(name) < 5:
        score -= 1

    return score
