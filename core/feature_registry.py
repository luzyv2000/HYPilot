from features.valuation import ValuationFeature
from features.dividend import DividendFeature
from features.stability import StabilityFeature


# Zentrale Feature-Liste (Reihenfolge = Priorität / Gewicht implizit)
FEATURES = [
    DividendFeature(),   # CORE (höchste Priorität)
    StabilityFeature(),  # sekundär
    ValuationFeature(),  # optional
]


def get_features():
    """
    Gibt alle aktiven Features zurück.
    """
    return FEATURES
