"""F8g real-source composition under ``real_source_composition.v2``.

The contract (``config/real_source_contract.yaml``) gives every real source a floor, a cap and its modalities. This
module counts a public payload against it. It is pure: it reads the exported items and the contract, and never
selects, drops or reorders what ships. Every gated item ships; the cap only limits how many of a source's items
count toward the readiness totals, so that no single source can satisfy the real-item target on its own.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from hocrgen.config.models import RealSourceContract, RealSourceModality, RealSourcePromotion, ReleaseProfile

COMPOSITION_ARTIFACT_SCHEMA = "real_source_composition_counts.v1"


def item_modality(item: Any, contract: RealSourceContract) -> RealSourceModality | None:
    """The E2d modality of one real item: its declared content type first, else its classified content class.

    A ``mixed`` (or unclassified) item has no modality: it counts toward the real total, never toward a modality floor.
    """

    metadata = item.metadata if isinstance(getattr(item, "metadata", None), dict) else {}
    declared = contract.modality_for_content_type(str(metadata.get("content_type") or "") or None)
    if declared is not None:
        return declared
    content_class = getattr(item, "content_class", None)
    if content_class in {modality.value for modality in RealSourceModality}:
        return RealSourceModality(content_class)
    return None


def real_source_composition(
    *,
    contract: RealSourceContract,
    exported_items: Iterable[Any],
    profile: ReleaseProfile,
) -> dict[str, Any]:
    """Count real public-payload items against the contract: per source, per modality and in total.

    The counted items of a source are its first ``cap`` items by item id, so the count is deterministic and never
    depends on the export order. Sources with ``counts_toward_modality_floors: false`` (rendered, not scanned)
    count toward the real total only.
    """

    real_items = sorted((item for item in exported_items if not item.is_synthetic), key=lambda item: item.item_id)
    by_source: dict[str, list[Any]] = {}
    for item in real_items:
        by_source.setdefault(item.source_id, []).append(item)

    included = set(profile.include_sources) - set(profile.exclude_sources)
    source_entries: list[dict[str, Any]] = []
    counted_by_modality: Counter[str] = Counter()
    payload_by_modality: Counter[str] = Counter()
    unassigned_item_ids: list[str] = []
    gaps: list[dict[str, Any]] = []
    counted_total = 0
    for entry in contract.sources:
        items = by_source.get(entry.source_id, [])
        counted = items[: entry.cap]
        payload_modalities = Counter(_modality_key(item_modality(item, contract)) for item in items)
        counted_modalities = Counter(_modality_key(item_modality(item, contract)) for item in counted)
        for item in items:
            if item_modality(item, contract) is None:
                unassigned_item_ids.append(item.item_id)
        if entry.counts_toward_modality_floors:
            for modality in RealSourceModality:
                counted_by_modality[modality.value] += counted_modalities.get(modality.value, 0)
        for modality in RealSourceModality:
            payload_by_modality[modality.value] += payload_modalities.get(modality.value, 0)
        counted_total += len(counted)
        floor_gap = max(entry.floor - len(items), 0)
        if floor_gap:
            gaps.append({"kind": "source_floor", "id": entry.source_id, "actual": len(items), "required": entry.floor})
        source_entries.append(
            {
                "source_id": entry.source_id,
                "promotion": entry.promotion.value,
                "planning_notation": entry.planning_notation,
                "modalities": [modality.value for modality in entry.modalities],
                "floor": entry.floor,
                "cap": entry.cap,
                "counts_toward_modality_floors": entry.counts_toward_modality_floors,
                "profile_included": entry.source_id in included,
                "public_payload_count": len(items),
                "counted_count": len(counted),
                "uncounted_over_cap": max(len(items) - entry.cap, 0),
                "floor_gap": floor_gap,
                "payload_modality_counts": dict(sorted(payload_modalities.items())),
                "counted_modality_counts": dict(sorted(counted_modalities.items())),
                "status": "pass" if not floor_gap else "blocked",
            }
        )

    modality_entries: list[dict[str, Any]] = []
    for modality in RealSourceModality:
        floor = contract.modality_floors.get(modality, 0)
        counted = counted_by_modality.get(modality.value, 0)
        gap = max(floor - counted, 0)
        if gap:
            gaps.append({"kind": "modality_floor", "id": modality.value, "actual": counted, "required": floor})
        modality_entries.append(
            {
                "modality": modality.value,
                "floor": floor,
                "counted_count": counted,
                "public_payload_count": payload_by_modality.get(modality.value, 0),
                "gap": gap,
                "status": "pass" if not gap else "blocked",
            }
        )

    total_gap = max(contract.min_real_items - counted_total, 0)
    if total_gap:
        gaps.append({"kind": "real_total", "id": "min_real_items", "actual": counted_total, "required": contract.min_real_items})
    contracted = {entry.source_id for entry in contract.sources}
    uncontracted = sorted(source_id for source_id in by_source if source_id not in contracted)
    not_promoted_in_payload = sorted(
        entry.source_id
        for entry in contract.sources
        if entry.promotion == RealSourcePromotion.not_promoted and by_source.get(entry.source_id)
    )
    return {
        "schema": COMPOSITION_ARTIFACT_SCHEMA,
        "contract_id": contract.contract_id,
        "planning_notation": contract.planning_notation,
        "decision_record": contract.decision_record,
        "min_real_items": contract.min_real_items,
        "public_payload_real_item_count": len(real_items),
        "counted_real_item_count": counted_total,
        "real_total_gap": total_gap,
        "sources": source_entries,
        "modalities": modality_entries,
        "unassigned_modality_item_count": len(unassigned_item_ids),
        "unassigned_modality_item_ids": sorted(unassigned_item_ids),
        "uncontracted_payload_source_ids": uncontracted,
        "not_promoted_payload_source_ids": not_promoted_in_payload,
        "gaps": gaps,
    }


def composition_gap_summary(gaps: list[dict[str, Any]]) -> str:
    labels = {"source_floor": "source floor", "modality_floor": "modality floor", "real_total": "counted real total"}
    return "; ".join(f"{labels.get(gap['kind'], gap['kind'])} {gap['id']} {gap['actual']} / {gap['required']}" for gap in gaps)


def _modality_key(modality: RealSourceModality | None) -> str:
    return modality.value if modality is not None else "unassigned"
