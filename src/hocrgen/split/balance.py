"""Size-aware assignment of whole groups to splits (F8g2).

A leakage-safe split keeps every connected group (a work, an edition, a manuscript, a duplicate cluster) in one split.
Hashing each group to a split independently, as F1d did, ignores group size: with few, unequal groups the item
ratios drift far from the policy (the F8g tranche came out 65 / 34 / 1.5 against 80 / 10 / 10, with every Pinkas
and YidTakNL page in train).

``assign_group_splits`` is a pure function of its inputs, so other stages and tools (for example the E2d real
printed reference pool) can call it on their own groups. The algorithm, ``size_aware_group_split.v1``:

1. Groups are assigned per **stratum** (the caller's key; the split stage uses ``<source_id>:<modality>``), so each
   source and modality approaches the policy on its own.
2. In a stratum of ``N`` items, the target of split ``s`` is ``ratio_s * N`` items. The split with the largest
   ratio (``train``) is the **sink**; the others are **holdouts**, filled in the order ``test``, ``validation``.
3. **Pinned** groups (a committed benchmark split, a synthetic-training overlap) take their split first and count
   toward its total.
4. The other groups are visited in a seeded order: ascending ``sha256(seed + "\\0" + group_id)``. That order does
   not depend on the other groups, so adding or removing one group never reorders the rest.
5. A visited group of ``n`` items enters a holdout ``s`` only if it fits: ``count_s + n <= target_s + 0.5`` (the
   target rounded to the nearest item). Among the holdouts it fits, it takes the one with the largest share of its
   target still open (ties: the fill order). A group that fits no holdout goes to the sink.

Consequences, by design:

- A group larger than a holdout's target never goes to that holdout, so a stratum that is one group (the BGU Pinkas
  manuscript) stays whole in the sink. Group integrity always wins over the ratio.
- A stratum too small for a holdout's target to reach half an item puts nothing in that holdout.
- With many small groups the ratios are met to within one item of each target.
- Stability: a change to the pool moves only groups visited after the change whose fit changes; on the F8g2
  Wikisource pool (58 Indexes, 1,455 pages), dropping one Index moves 13 other pages at the median, 3% on average.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

SPLIT_ASSIGNMENT_ALGORITHM = "size_aware_group_split.v1"
DEFAULT_SPLIT_SEED = "hocrgen-split-v1"
SPLIT_ORDER = ("train", "validation", "test")
HOLDOUT_FILL_ORDER = ("test", "validation")
FIT_TOLERANCE_ITEMS = 0.5


@dataclass(frozen=True)
class SplitGroup:
    """One whole group to place: its id, item count, stratum and an optional pinned split."""

    group_id: str
    size: int
    stratum: str
    pinned_split: str | None = None
    pin_reason: str | None = None


def split_ratios(policy: Any) -> dict[str, float]:
    """Ratios from a ``SplitPolicy`` or a mapping of split name to ratio."""

    if isinstance(policy, Mapping):
        ratios = {str(name): float(value) for name, value in policy.items()}
    else:
        ratios = {name: float(getattr(policy, name)) for name in SPLIT_ORDER}
    if any(value < 0 for value in ratios.values()) or round(sum(ratios.values()), 6) != 1.0:
        raise ValueError("split ratios must be non-negative and sum to 1.0")
    return ratios


def _order_key(seed: str, group_id: str) -> str:
    return hashlib.sha256(f"{seed}\0{group_id}".encode("utf-8")).hexdigest()


def _sink_and_holdouts(ratios: Mapping[str, float]) -> tuple[str, list[str]]:
    names = sorted(ratios, key=lambda name: SPLIT_ORDER.index(name) if name in SPLIT_ORDER else len(SPLIT_ORDER))
    sink = max(names, key=lambda name: (ratios[name], -names.index(name)))
    fill_rank = {name: rank for rank, name in enumerate(HOLDOUT_FILL_ORDER)}
    holdouts = sorted((name for name in names if name != sink), key=lambda name: (fill_rank.get(name, len(fill_rank)), name))
    return sink, holdouts


def assign_group_splits(groups: Iterable[SplitGroup], policy: Any, *, seed: str = DEFAULT_SPLIT_SEED) -> dict[str, str]:
    """Map each group id to its split under ``size_aware_group_split.v1`` (see the module docstring).

    Deterministic for a given set of groups, policy and seed; the input order does not matter. Group ids must be
    unique; a pinned split must be one of the policy's splits.
    """

    ratios = split_ratios(policy)
    sink, holdouts = _sink_and_holdouts(ratios)
    by_stratum: dict[str, list[SplitGroup]] = {}
    seen: set[str] = set()
    for group in groups:
        if group.group_id in seen:
            raise ValueError(f"duplicate split group id: {group.group_id}")
        if group.size < 0:
            raise ValueError(f"split group {group.group_id} has a negative size")
        if group.pinned_split is not None and group.pinned_split not in ratios:
            raise ValueError(f"split group {group.group_id} is pinned to unknown split {group.pinned_split}")
        seen.add(group.group_id)
        by_stratum.setdefault(group.stratum, []).append(group)

    assignment: dict[str, str] = {}
    for members in by_stratum.values():
        total = sum(group.size for group in members)
        targets = {name: ratios[name] * total for name in ratios}
        counts = {name: 0 for name in ratios}
        for group in members:
            if group.pinned_split is not None:
                assignment[group.group_id] = group.pinned_split
                counts[group.pinned_split] += group.size
        free = sorted((group for group in members if group.pinned_split is None), key=lambda group: _order_key(seed, group.group_id))
        for group in free:
            fits = [name for name in holdouts if targets[name] > 0 and counts[name] + group.size <= targets[name] + FIT_TOLERANCE_ITEMS]
            if fits:
                split = max(fits, key=lambda name: ((targets[name] - counts[name]) / targets[name], -holdouts.index(name)))
            else:
                split = sink
            assignment[group.group_id] = split
            counts[split] += group.size
    return assignment


def split_balance_report(
    groups: Iterable[SplitGroup],
    assignment: Mapping[str, str],
    policy: Any,
    *,
    seed: str = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    """Per-stratum and overall item and group counts against the policy targets."""

    ratios = split_ratios(policy)
    strata: dict[str, dict[str, Any]] = {}
    overall_items = {name: 0 for name in ratios}
    overall_groups = {name: 0 for name in ratios}
    for group in groups:
        split = assignment[group.group_id]
        record = strata.setdefault(
            group.stratum,
            {"items": {name: 0 for name in ratios}, "groups": {name: 0 for name in ratios}, "pinned_groups": 0},
        )
        record["items"][split] += group.size
        record["groups"][split] += 1
        record["pinned_groups"] += 1 if group.pinned_split is not None else 0
        overall_items[split] += group.size
        overall_groups[split] += 1

    def shares(items: Mapping[str, int]) -> dict[str, float]:
        total = sum(items.values())
        return {name: round(items[name] / total, 4) if total else 0.0 for name in ratios}

    return {
        "algorithm": SPLIT_ASSIGNMENT_ALGORITHM,
        "seed": seed,
        "policy": ratios,
        "items": overall_items,
        "groups": overall_groups,
        "item_shares": shares(overall_items),
        "strata": {
            stratum: {**record, "item_count": sum(record["items"].values()), "item_shares": shares(record["items"])}
            for stratum, record in sorted(strata.items())
        },
    }
