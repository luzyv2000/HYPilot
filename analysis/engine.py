from core.universe_service import get_all_instruments
from analysis.rules import classify_instrument, score_instrument
from analysis.filter import is_investable


def analyze_universe(limit=500):
    instruments = get_all_instruments(limit=limit)

    results = []

    for inst in instruments:
        if not is_investable(inst):
            continue

        name = inst["name"]

        category = classify_instrument(name)
        score = score_instrument(name)

        # nur sinnvolle Kandidaten behalten
        if score < 0:
            continue

        results.append({
            "name": name,
            "isin": inst["isin"],
            "category": category,
            "score": score
        })

    # Sortierung
    results.sort(key=lambda x: x["score"], reverse=True)

    return results
