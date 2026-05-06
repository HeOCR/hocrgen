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
            "provider_version": metadata_value(item, "synthetic_provider_version"),
            "layout_family": metadata_value(item, "synthetic_layout_family"),
            "hebrew_coverage": item.metadata.get("synthetic_hebrew_coverage") or {},
            "split": item.split or "unknown",
        }
        for item in synthetic_items
    ]
    coverage_counts: dict[str, int] = {}
    for item in synthetic_metadata:
        coverage = item["hebrew_coverage"]
        if not isinstance(coverage, dict):
            missing_metadata["synthetic_hebrew_coverage"] += 1
            continue
        for key, value in coverage.items():
            if value is True:
                coverage_counts[key] = coverage_counts.get(key, 0) + 1

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
        "by_provider_version": dict(Counter(item["provider_version"] for item in synthetic_metadata)),
        "by_layout_family": dict(Counter(item["layout_family"] for item in synthetic_metadata)),
        "hebrew_coverage_counts": coverage_counts,
        "by_split": {
            split: {
                "items": sum(counter.values()),
                "recipes": dict(counter),
            }
            for split, counter in sorted(split_counts.items())
        },
        "missing_metadata": dict(missing_metadata),
    }
