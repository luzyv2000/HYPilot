from typing import Dict, List


class Feature:
    name = "base"

    def required_fields(self) -> List[str]:
        return []

    def compute(self, data: Dict) -> Dict:
        raise NotImplementedError
