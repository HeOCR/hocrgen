from __future__ import annotations

from collections import Counter
from typing import Any


def synthetic_composition_report(items: list[Any]) -> dict[str, Any]:
    synthetic_items = [item for item in items if item.is_synthetic]
    real_count = len(items) - len(synthetic_items)
    synthetic_count = len(synthetic_items)
    total_count = len(items)
    split_counts: dict[str, Counter[str]] = {}
    missing_metadata: Counter[str] = Counter()

    def metadata_value(item: Any, key: str) -> str:
        value = item.metadata.get(key)
        if not value:
            missing_metadata[key] += 1
            return "unknown"
        return str(value)

    synthetic_metadata = [
        {
            "template_id": metadata_value(item, "synthetic_template_id"),
            "recipe_id": metadata_value(item, "synthetic_recipe_id"),
            "degradation_preset": metadata_value(item, "synthetic_degradation_preset"),
            "font_id": metadata_value(item, "synthetic_font_id"),
            "split": item.split or "unknown",
        }
        for item in synthetic_items
    ]

    for item in synthetic_metadata:
        split = item["split"]
        split_counts.setdefault(split, Counter())
        split_counts[split].update([item["recipe_id"]])

    return {
        "total_items": total_count,
        "real_items": real_count,
        "synthetic_items": synthetic_count,
        "synthetic_fraction": round(synthetic_count / total_count, 6) if total_count else 0.0,
        "by_template_id": dict(Counter(item["template_id"] for item in synthetic_metadata)),
        "by_recipe_id": dict(Counter(item["recipe_id"] for item in synthetic_metadata)),
        "by_degradation_preset": dict(Counter(item["degradation_preset"] for item in synthetic_metadata)),
        "by_font_id": dict(Counter(item["font_id"] for item in synthetic_metadata)),
        "by_split": {
            split: {
                "items": sum(counter.values()),
                "recipes": dict(counter),
            }
            for split, counter in sorted(split_counts.items())
        },
        "missing_metadata": dict(missing_metadata),
    }
