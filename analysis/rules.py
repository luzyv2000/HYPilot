import re


def classify_instrument(name: str):
    name_lower = name.lower()

    if "etf" in name_lower:
        return "ETF"

    if "bond" in name_lower or "yield" in name_lower or "t-bil" in name_lower:
        return "BOND"

    if "lev" in name_lower or "3x" in name_lower or "short" in name_lower:
        return "DERIVATIVE"

    if "covered call" in name_lower:
        return "OPTION_STRATEGY"

    return "STOCK"


def score_instrument(name: str):
    score = 0
    name_lower = name.lower()

    # === POSITIV ===

    if "etf" in name_lower:
        score += 5

    if "msci" in name_lower:
        score += 3

    if "world" in name_lower:
        score += 2

    if "s&p" in name_lower or "sp500" in name_lower:
        score += 3

    # === NEGATIV ===

    # Hochrisiko-Produkte
    if "lev" in name_lower or "3x" in name_lower:
        score -= 6

    if "short" in name_lower:
        score -= 4

    if "covered call" in name_lower:
        score -= 2

    if "high yield" in name_lower:
        score -= 3

    # === leichte Korrekturen ===

    if "t-bil" in name_lower:
        score += 1  # stabil, aber langweilig

    # === Bonus: einfache Pattern-Erkennung ===

    # sehr kurze Namen → oft Müll / spezielle Produkte
    if len(name) < 5:
        score -= 1

    return score
