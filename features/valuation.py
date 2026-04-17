from typing import Dict
from features.base import Feature


class ValuationFeature(Feature):
    name = "valuation"

    def required_fields(self):
        return ["pe_ratio", "forward_pe"]

    def compute(self, data: Dict) -> Dict:
        score = 0
        details = {}

        pe = data.get("pe_ratio")
        forward_pe = data.get("forward_pe")

        if pe:
            if 10 <= pe <= 25:
                score += 15
                details["pe"] = "fair"
            elif pe < 10:
                score += 10
                details["pe"] = "cheap"
            else:
                details["pe"] = "expensive"

        if forward_pe and pe:
            if forward_pe < pe:
                score += 10
                details["forward_pe"] = "improving"
            else:
                details["forward_pe"] = "worsening"

        return {
            "score": score,
            "details": details
        }
