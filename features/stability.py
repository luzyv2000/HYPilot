from typing import Dict
from features.base import Feature


class StabilityFeature(Feature):
    name = "stability"

    def required_fields(self):
        # nur reale, verfügbare Daten!
        return ["profit_margin"]

    def compute(self, data: Dict) -> Dict:
        score = 0
        details = {}

        margin = data.get("profit_margin")

        if margin is not None:
            if margin > 0.2:
                score += 20
                details["margin"] = "strong"
            elif margin > 0.1:
                score += 10
                details["margin"] = "ok"
            else:
                details["margin"] = "weak"
        else:
            details["margin"] = "missing"

        return {
            "score": score,
            "details": details
        }
