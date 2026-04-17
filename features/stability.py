from typing import Dict
from features.base import Feature


class StabilityFeature(Feature):
    name = "stability"

    def required_fields(self):
        return ["earnings_stability", "profit_margin"]

    def compute(self, data: Dict) -> Dict:
        score = 0
        details = {}

        margin = data.get("profit_margin")

        if margin:
            if margin > 0.2:
                score += 20
                details["margin"] = "strong"
            elif margin > 0.1:
                score += 10
                details["margin"] = "ok"
            else:
                details["margin"] = "weak"

        return {
            "score": score,
            "details": details
        }
