from typing import List, Set
from core.feature_registry import get_features


def collect_required_fields() -> List[str]:
    """
    Aggregiert alle benötigten Datenfelder aus den aktiven Features.
    """
    fields: Set[str] = set()

    for feature in get_features():
        required = feature.required_fields()

        if not isinstance(required, list):
            raise ValueError(
                f"Feature {feature.name} returned invalid required_fields format"
            )

        for field in required:
            fields.add(field)

    return list(fields)
