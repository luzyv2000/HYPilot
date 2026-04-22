# Dateiname:     analysis/rules.py
# Version:       2026-04-22
# Abhängigkeiten (intern): keine
# Abhängigkeiten (extern): keine
"""
analysis/rules.py

Klassifikation und heuristischer Name-Score für TR-Instrumente.

ETF-Erkennung (mehrschichtig, da TR-Namen selten "ETF" enthalten):
  1. Schlüsselwort "etf" im Namen
  2. Bekannte ETF-Anbieter (iShares, Vanguard, Xtrackers, ...)
  3. Struktursuffix (Acc), (Dist) → typisch für UCITS-ETFs
  4. ISIN-Prefix IE (Irland) oder LU (Luxemburg) → typische ETF-Domizile
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
    "flossbach", "dimensional", "hsbc etf",
})

_ETF_ISIN_PREFIXES: frozenset[str] = frozenset({
    "IE",   # Irland — häufigster ETF-Domizil
    "LU",   # Luxemburg
})

_ETF_SUFFIX_PATTERN: re.Pattern[str] = re.compile(
    r"\((acc|dist|hedged|swap)\)", re.IGNORECASE
)


def _is_etf(name: str, isin: str) -> bool:
    name_lower = name.lower()

    # Direktes Schlüsselwort
    if any(kw in name_lower for kw in _ETF_KEYWORDS):
        return True

    # Bekannter Anbieter
    if any(p in name_lower for p in _ETF_PROVIDERS):
        return True

    # Struktursuffix (Acc)/(Dist)
    if _ETF_SUFFIX_PATTERN.search(name):
        return True

    # ISIN-Domizil
    if any(isin.startswith(prefix) for prefix in _ETF_ISIN_PREFIXES):
        return True

    return False


# ── Klassifikation ────────────────────────────────────────────────────────────

def classify_instrument(name: str, isin: str = "") -> str:
    """
    Klassifiziert ein Instrument anhand Name und optionaler ISIN.

    Returns:
        "ETF" | "BOND" | "DERIVATIVE" | "OPTION_STRATEGY" | "STOCK"
    """
    name_lower = name.lower()

    if _is_etf(name, isin):
        return "ETF"

    if any(kw in name_lower for kw in ("bond", "t-bil", "treasury", "gilts")):
        return "BOND"

    # "yield" nur als BOND wenn kein ETF erkannt (High Yield ETFs existieren)
    if "yield" in name_lower and "etf" not in name_lower:
        return "BOND"

    if any(kw in name_lower for kw in ("lev", "3x", "2x", "turbo", "knock")):
        return "DERIVATIVE"

    if "covered call" in name_lower:
        return "OPTION_STRATEGY"

    return "STOCK"


# ── Name-Score ────────────────────────────────────────────────────────────────

def score_instrument(name: str, isin: str = "") -> int:
    """
    Heuristischer Score basierend auf Name/ISIN.
    Nur für Universe-Vorfilterung — kein Ersatz für Dividenden-Scoring.
    """
    score = 0
    name_lower = name.lower()

    # ETF-Bonus
    if _is_etf(name, isin):
        score += 5

    # Qualitätsindizes
    if "msci world" in name_lower:
        score += 4
    elif "msci" in name_lower:
        score += 2

    if "s&p 500" in name_lower or "s&p500" in name_lower:
        score += 3

    if "world" in name_lower:
        score += 1

    # Risikoabschläge
    if any(kw in name_lower for kw in ("lev", "3x", "2x", "turbo")):
        score -= 6
    if "short" in name_lower:
        score -= 4
    if "covered call" in name_lower:
        score -= 2
    if "high yield" in name_lower:
        score -= 2

    # Sehr kurze Namen → oft Sonderprodukte
    if len(name) < 5:
        score -= 1

    return score
