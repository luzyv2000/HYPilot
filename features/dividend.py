from typing import Dict
from features.base import Feature


class DividendFeature(Feature):
    name = "dividend"

    def required_fields(self):
        return ["dividend_yield"]

    def compute(self, data: Dict) -> Dict:
        score = 0
        details = {}

        dy = data.get("dividend_yield")

        if dy:
            if dy > 0.10:
                score += 40
                details["yield"] = "very high"
            elif dy > 0.05:
                score += 20
                details["yield"] = "good"
            elif dy > 0.02:
                score += 10
                details["yield"] = "low"
            else:
                details["yield"] = "very low"
        else:
            details["yield"] = "missing"

        return {
            "score": score,
            "details": details
        }
