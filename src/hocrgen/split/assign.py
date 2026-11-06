from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from hocrgen.config.models import SplitPolicy
from hocrgen.manifests.models import CuratedItemRecord, SplitAssignmentRecord
from hocrgen.split.work_groups import item_work_group_keys

SYNTHETIC_TRAINING_SPLIT = "train"


@dataclass(frozen=True)
class SplitOutputs:
    retained_items: list[CuratedItemRecord]
    duplicate_items: list[CuratedItemRecord]
    assignments: list[SplitAssignmentRecord]
    leakage_report: dict[str, object]


@dataclass
class _UnionFind:
    parent: dict[str, str] = field(default_factory=dict)

    def find(self, node: str) -> str:
        self.parent.setdefault(node, node)
        root = node
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[node] != root:
            self.parent[node], node = root, self.parent[node]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            # Deterministic: the smaller id is the root.
            low, high = sorted((left_root, right_root))
            self.parent[high] = low


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
    """The item's own (F1d) split group: its exact-duplicate cluster, else its source group, else the item."""

    if item.dedupe_cluster_id:
        return item.dedupe_cluster_id
    if item.source_group_id:
        return item.source_group_id
    return f"{item.source_id}:{item.source_item_id}"


def _item_group_keys(item: CuratedItemRecord) -> list[str]:
    """Every grouping an item belongs to; items sharing any one key are kept in one split (F1d, F8g)."""

    keys = [f"item:{item.item_id}", f"split_group:{_split_group_id(item)}"]
    if item.dedupe_cluster_id:
        keys.append(f"dedupe:{item.dedupe_cluster_id}")
    if item.near_duplicate_cluster_id:
        keys.append(f"near_duplicate:{item.near_duplicate_cluster_id}")
    if item.source_group_id:
        keys.append(f"source_group:{item.source_group_id}")
    keys.extend(f"work:{key}" for key in item_work_group_keys(item))
    return keys


def split_components(items: list[CuratedItemRecord]) -> dict[str, str]:
    """Map each item id to its component's split group id.

    Items are connected through exact-duplicate clusters, near-duplicate clusters, source groups and work groups
    (F8g), so a whole connected component lands in one split. The component's split group id is the smallest F1d
    split group id among its members, so an item that shares nothing keeps the split it had before F8g.
    """

    union_find = _UnionFind()
    for item in items:
        keys = _item_group_keys(item)
        for key in keys[1:]:
            union_find.union(keys[0], key)
    members: dict[str, list[CuratedItemRecord]] = {}
    for item in items:
        members.setdefault(union_find.find(f"item:{item.item_id}"), []).append(item)
    component_ids: dict[str, str] = {}
    for component in members.values():
        group_id = min(_split_group_id(item) for item in component)
        for item in component:
            component_ids[item.item_id] = group_id
    return component_ids


def _validate_leakage(
    items: list[CuratedItemRecord],
    synthetic_training_matches: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    split_group_splits: dict[str, set[str]] = {}
    duplicate_cluster_splits: dict[str, set[str]] = {}
    near_duplicate_cluster_splits: dict[str, set[str]] = {}
    source_group_splits: dict[str, set[str]] = {}
    work_group_splits: dict[str, set[str]] = {}
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
        for key in item_work_group_keys(item):
            work_group_splits.setdefault(key, set()).add(item.split)

    def leaks(groups: dict[str, set[str]], label: str) -> list[dict[str, object]]:
        return [{label: group_id, "splits": sorted(splits)} for group_id, splits in sorted(groups.items()) if len(splits) > 1]

    split_group_leaks = leaks(split_group_splits, "split_group_id")
    duplicate_cluster_leaks = leaks(duplicate_cluster_splits, "cluster_id")
    near_duplicate_cluster_leaks = leaks(near_duplicate_cluster_splits, "cluster_id")
    source_group_leaks = leaks(source_group_splits, "group_id")
    work_group_leaks = leaks(work_group_splits, "group_id")
    matches = synthetic_training_matches or {}
    items_by_id = {item.item_id: item for item in items}
    synthetic_training_holdout_leaks = sorted(
        item_id for item_id in matches if item_id in items_by_id and items_by_id[item_id].split != SYNTHETIC_TRAINING_SPLIT
    )
    status = (
        "ok"
        if not (
            split_group_leaks
            or duplicate_cluster_leaks
            or near_duplicate_cluster_leaks
            or source_group_leaks
            or work_group_leaks
            or synthetic_training_holdout_leaks
        )
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
        "work_group_count": len(work_group_splits),
        "work_group_leaks": work_group_leaks,
        "synthetic_training_overlap": {
            "matched_item_count": len(matches),
            "matched_items": [
                {"item_id": item_id, "work_ids": work_ids} for item_id, work_ids in sorted(matches.items())
            ],
            "holdout_leak_item_ids": synthetic_training_holdout_leaks,
            "rule": (
                "Items whose work-group keys match synthetic_training_works.v1 stay in train with their whole split "
                "group, and are never benchmark or holdout material."
            ),
        },
        "status": status,
    }


def synthetic_training_matches(
    items: list[CuratedItemRecord],
    registry_keys: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    """Item id -> registered synthetic-training work ids whose match keys the item's work-group keys hit."""

    if not registry_keys:
        return {}
    matches: dict[str, list[str]] = {}
    for item in items:
        work_ids = sorted({work_id for key in item_work_group_keys(item) for work_id in registry_keys.get(key, [])})
        if work_ids:
            matches[item.item_id] = work_ids
    return matches


def assign_splits(
    retained_items: list[CuratedItemRecord],
    duplicate_items: list[CuratedItemRecord],
    split_policy: SplitPolicy,
    synthetic_training_keys: dict[str, list[str]] | None = None,
) -> SplitOutputs:
    """Assign splits by connected group (F1d, F8g) and keep synthetic-training works in train (F8g).

    ``synthetic_training_keys`` maps a work-group key to the registered synthetic-training work ids that carry it
    (``SyntheticTrainingWorkRegistry.match_keys``). A component holding any matching item goes to train whole.
    """

    all_items = [*retained_items, *duplicate_items]
    component_ids = split_components(all_items)
    matches = synthetic_training_matches(all_items, synthetic_training_keys)
    forced_train_groups = {component_ids[item_id] for item_id in matches}
    group_assignments: dict[str, str] = {}

    def split_for(group_id: str) -> str:
        if group_id in forced_train_groups:
            return group_assignments.setdefault(group_id, SYNTHETIC_TRAINING_SPLIT)
        return group_assignments.setdefault(group_id, _pick_split(group_id, split_policy))

    updated_retained: list[CuratedItemRecord] = []
    assignments: list[SplitAssignmentRecord] = []
    for item in sorted(retained_items, key=lambda record: record.item_id):
        split_group_id = component_ids[item.item_id]
        split = split_for(split_group_id)
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
                work_group_ids=item_work_group_keys(item),
                split_constraint="synthetic_training_overlap" if split_group_id in forced_train_groups else None,
            )
        )

    updated_duplicates: list[CuratedItemRecord] = []
    canonical_by_cluster = {
        item.dedupe_cluster_id: item for item in updated_retained if item.dedupe_cluster_id is not None
    }
    for item in sorted(duplicate_items, key=lambda record: record.item_id):
        split_group_id = component_ids[item.item_id]
        canonical = canonical_by_cluster.get(item.dedupe_cluster_id)
        split = group_assignments.get(split_group_id)
        if split is None and canonical is not None:
            split = canonical.split
        updated_duplicates.append(item.model_copy(update={"split": split, "split_group_id": split_group_id}))

    leakage_report = _validate_leakage(updated_retained + updated_duplicates, matches)
    leakage_report["forced_train_group_count"] = len(forced_train_groups)
    if leakage_report["status"] != "ok":
        raise ValueError("split leakage detected")

    return SplitOutputs(
        retained_items=updated_retained,
        duplicate_items=updated_duplicates,
        assignments=assignments,
        leakage_report=leakage_report,
    )
