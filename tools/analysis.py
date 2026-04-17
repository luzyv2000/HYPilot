from typing import Dict


def score_stock(data: Dict) -> Dict:
    score = 0
    details = {}

    pe = data.get("pe_ratio")
    growth = data.get("revenue_growth")
    margin = data.get("profit_margin")
    debt = data.get("debt_to_equity")

    # --- Bewertungssystem ---

    # PE Ratio (niedriger = besser, aber nicht zu niedrig)
    if pe:
        if 10 <= pe <= 25:
            score += 20
            details["pe"] = "gut"
        elif pe < 10:
            score += 10
            details["pe"] = "möglicherweise unterbewertet"
        else:
            details["pe"] = "teuer"

    # Wachstum
    if growth:
        if growth > 0.15:
            score += 25
            details["growth"] = "stark"
        elif growth > 0.05:
            score += 15
            details["growth"] = "moderat"
        else:
            details["growth"] = "schwach"

    # Marge
    if margin:
        if margin > 0.2:
            score += 20
            details["margin"] = "hoch"
        elif margin > 0.1:
            score += 10
            details["margin"] = "ok"
        else:
            details["margin"] = "niedrig"

    # Verschuldung
    if debt:
        if debt < 1:
            score += 15
            details["debt"] = "niedrig"
        elif debt < 2:
            score += 5
            details["debt"] = "mittel"
        else:
            details["debt"] = "hoch"

    # --- Finale Bewertung ---
    if score >= 70:
        rating = "BUY"
    elif score >= 50:
        rating = "HOLD"
    else:
        rating = "RISKY"

    return {
        "score": score,
        "rating": rating,
        "details": details
    }
