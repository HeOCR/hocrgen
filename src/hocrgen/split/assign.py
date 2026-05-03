from __future__ import annotations

import hashlib
from dataclasses import dataclass

from hocrgen.config.models import SplitPolicy
from hocrgen.manifests.models import CuratedItemRecord, SplitAssignmentRecord


@dataclass(frozen=True)
class SplitOutputs:
    retained_items: list[CuratedItemRecord]
    duplicate_items: list[CuratedItemRecord]
    assignments: list[SplitAssignmentRecord]
    leakage_report: dict[str, object]


def _stable_bucket(value: str) -> float:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest, 16) / float(16**64)


def _pick_split(split_group_id: str, split_policy: SplitPolicy) -> str:
    bucket = _stable_bucket(split_group_id)
    if bucket < split_policy.train:
        return "train"
    if bucket < split_policy.train + split_policy.validation:
        return "validation"
    return "test"


def _split_group_id(item: CuratedItemRecord) -> str:
    if item.dedupe_cluster_id:
        return item.dedupe_cluster_id
    if item.source_group_id:
        return item.source_group_id
    return f"{item.source_id}:{item.source_item_id}"


def _validate_leakage(items: list[CuratedItemRecord]) -> dict[str, object]:
    split_group_splits: dict[str, set[str]] = {}
    duplicate_cluster_splits: dict[str, set[str]] = {}
    near_duplicate_cluster_splits: dict[str, set[str]] = {}
    source_group_splits: dict[str, set[str]] = {}
    for item in items:
        if item.split is None or item.split_group_id is None:
            continue
        split_group_splits.setdefault(item.split_group_id, set()).add(item.split)
        if item.dedupe_cluster_id:
            duplicate_cluster_splits.setdefault(item.dedupe_cluster_id, set()).add(item.split)
        if item.near_duplicate_cluster_id:
            near_duplicate_cluster_splits.setdefault(item.near_duplicate_cluster_id, set()).add(item.split)
        if item.source_group_id:
            source_group_splits.setdefault(item.source_group_id, set()).add(item.split)

    split_group_leaks = [
        {"split_group_id": split_group_id, "splits": sorted(splits)}
        for split_group_id, splits in sorted(split_group_splits.items())
        if len(splits) > 1
    ]
    duplicate_cluster_leaks = [
        {"cluster_id": cluster_id, "splits": sorted(splits)}
        for cluster_id, splits in sorted(duplicate_cluster_splits.items())
        if len(splits) > 1
    ]
    near_duplicate_cluster_leaks = [
        {"cluster_id": cluster_id, "splits": sorted(splits)}
        for cluster_id, splits in sorted(near_duplicate_cluster_splits.items())
        if len(splits) > 1
    ]
    source_group_leaks = [
        {"group_id": group_id, "splits": sorted(splits)}
        for group_id, splits in sorted(source_group_splits.items())
        if len(splits) > 1
    ]
    status = (
        "ok"
        if not split_group_leaks and not duplicate_cluster_leaks and not near_duplicate_cluster_leaks and not source_group_leaks
        else "error"
    )
    return {
        "duplicate_cluster_leaks": duplicate_cluster_leaks,
        "group_count": len(split_group_splits),
        "near_duplicate_cluster_leaks": near_duplicate_cluster_leaks,
        "near_duplicate_cluster_count": len(near_duplicate_cluster_splits),
        "source_group_count": len(source_group_splits),
        "source_group_leaks": source_group_leaks,
        "split_group_leaks": split_group_leaks,
        "status": status,
    }


def assign_splits(
    retained_items: list[CuratedItemRecord],
    duplicate_items: list[CuratedItemRecord],
    split_policy: SplitPolicy,
) -> SplitOutputs:
    group_assignments: dict[str, str] = {}
    updated_retained: list[CuratedItemRecord] = []
    assignments: list[SplitAssignmentRecord] = []

    for item in sorted(retained_items, key=lambda record: record.item_id):
        split_group_id = _split_group_id(item)
        split = group_assignments.setdefault(split_group_id, _pick_split(split_group_id, split_policy))
        updated = item.model_copy(update={"split": split, "split_group_id": split_group_id})
        updated_retained.append(updated)
        assignments.append(
            SplitAssignmentRecord(
                item_id=item.item_id,
                split=split,
                split_group_id=split_group_id,
                dedupe_cluster_id=item.dedupe_cluster_id,
                near_duplicate_cluster_id=item.near_duplicate_cluster_id,
                source_group_id=item.source_group_id,
            )
        )

    updated_duplicates: list[CuratedItemRecord] = []
    canonical_by_cluster = {
        item.dedupe_cluster_id: item for item in updated_retained if item.dedupe_cluster_id is not None
    }
    for item in sorted(duplicate_items, key=lambda record: record.item_id):
        split_group_id = _split_group_id(item)
        canonical = canonical_by_cluster.get(item.dedupe_cluster_id)
        split = group_assignments.get(split_group_id)
        if split is None and canonical is not None:
            split = canonical.split
        updated_duplicates.append(item.model_copy(update={"split": split, "split_group_id": split_group_id}))

    leakage_report = _validate_leakage(updated_retained + updated_duplicates)
    if leakage_report["status"] != "ok":
        raise ValueError("split leakage detected")

    return SplitOutputs(
        retained_items=updated_retained,
        duplicate_items=updated_duplicates,
        assignments=assignments,
        leakage_report=leakage_report,
    )
