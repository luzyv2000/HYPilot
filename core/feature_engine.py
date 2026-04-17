from typing import Dict

from core.feature_registry import get_features


def normalize_score(score: int) -> int:
    """
    Normiert Score auf 0–100 (einfacher Ansatz, später erweiterbar)
    """
    return max(0, min(score, 100))


def derive_rating(score: int) -> str:
    """
    Leitet eine Entscheidung aus dem Score ab
    """
    if score >= 70:
        return "BUY"
    elif score >= 50:
        return "HOLD"
    elif score >= 30:
        return "WATCH"
    else:
        return "REJECT"


def run_features(data: Dict) -> Dict:
    """
    Führt alle Features aus und aggregiert die Ergebnisse
    """
    total_score = 0
    results = {}

    for feature in get_features():
        result = feature.compute(data)

        feature_score = result.get("score", 0)

        results[feature.name] = result
        total_score += feature_score

    normalized = normalize_score(total_score)
    rating = derive_rating(normalized)

    return {
        "total_score": total_score,
        "normalized_score": normalized,
        "rating": rating,
        "features": results
    }
