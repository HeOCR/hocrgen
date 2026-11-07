"""Size-aware assignment of whole groups to splits (F8g2; reference constraints E2d3e).

A leakage-safe split keeps every connected group (a work, an edition, a manuscript, a duplicate cluster) in one split.
Hashing each group to a split independently, as F1d did, ignores group size: with few, unequal groups the item
ratios drift far from the policy (the F8g tranche came out 65 / 34 / 1.5 against 80 / 10 / 10, with every Pinkas
and YidTakNL page in train).

``assign_group_splits`` is a pure function of its inputs, so other stages and tools (for example the E2d real
printed reference pool) can call it on their own groups. The item placement, unchanged since ``v1``:

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

**Reference constraints (``size_aware_group_split.v2``, E2d3e).** Item counts alone can leave a holdout with almost
no human-adjudicated reference text: on the F8g2 Wikisource pool the release ``test`` split held one book's adjudicated
pages, and after E2d3d only three of them. A group may therefore carry a ``reference_weight`` (the characters of its
adjudicated reference text; the split stage counts exactly the pages the real printed evaluation scores). In a stratum with any reference
weight, each holdout's ``ReferenceHoldoutConstraint`` must hold:

- ``min_groups``: at least this many groups with reference weight;
- ``min_share``: at least this share of the stratum's reference weight;
- ``max_group_share``: no single group above this share of the holdout's reference weight.

6. If, after the item placement, a holdout fails its constraint, every group with reference weight keeps the split
   it was placed in (it is pinned there): the repair moves only the groups it chooses, and the groups without
   reference weight refill around them.
7. The first failing holdout (fill order) then takes one more group from the sink: an unpinned group with reference
   weight that would not itself exceed the holdout's ``max_group_share``. Each eligible group is tried (pinned to the
   holdout, and the item placement run again). A group whose move alone makes the holdout
   meet its whole constraint is preferred; then the fewest items (least change to the item ratios), the smallest
   reference weight (least adjudicated text taken from the sink) and the seeded order.
8. This repeats until every constraint holds or no eligible group is left; an unmet constraint is reported, never
   forced. A stratum without reference weight is placed exactly as in ``v1``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

SPLIT_ASSIGNMENT_ALGORITHM = "size_aware_group_split.v2"
DEFAULT_SPLIT_SEED = "hocrgen-split-v1"
SPLIT_ORDER = ("train", "validation", "test")
HOLDOUT_FILL_ORDER = ("test", "validation")
FIT_TOLERANCE_ITEMS = 0.5
PIN_REFERENCE_CONSTRAINT = "reference_constraint"


@dataclass(frozen=True)
class ReferenceHoldoutConstraint:
    """What a holdout must hold of its stratum's adjudicated reference text (``v2``)."""

    min_groups: int = 0
    min_share: float = 0.0
    max_group_share: float = 1.0


# E2d3e (team-lead decision 2026-11-07); the values and their reasons are in docs/real_source_release_contract.md.
DEFAULT_REFERENCE_CONSTRAINTS: dict[str, ReferenceHoldoutConstraint] = {
    "test": ReferenceHoldoutConstraint(min_groups=2, min_share=0.10, max_group_share=0.50),
}


@dataclass(frozen=True)
class SplitGroup:
    """One whole group to place: its id, item count, stratum and an optional pinned split."""

    group_id: str
    size: int
    stratum: str
    pinned_split: str | None = None
    pin_reason: str | None = None
    reference_weight: int = 0


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


def _place(members: list[SplitGroup], pins: Mapping[str, str], ratios: Mapping[str, float], sink: str,
           holdouts: list[str], seed: str) -> dict[str, str]:
    """Steps 2-5: pinned groups first, then the free groups in seeded order, each to the holdout it fits best."""

    total = sum(group.size for group in members)
    targets = {name: ratios[name] * total for name in ratios}
    counts = {name: 0 for name in ratios}
    assignment: dict[str, str] = {}
    for group in members:
        if group.group_id in pins:
            assignment[group.group_id] = pins[group.group_id]
            counts[pins[group.group_id]] += group.size
    free = sorted((group for group in members if group.group_id not in pins), key=lambda group: _order_key(seed, group.group_id))
    for group in free:
        fits = [name for name in holdouts if targets[name] > 0 and counts[name] + group.size <= targets[name] + FIT_TOLERANCE_ITEMS]
        if fits:
            split = max(fits, key=lambda name: ((targets[name] - counts[name]) / targets[name], -holdouts.index(name)))
        else:
            split = sink
        assignment[group.group_id] = split
        counts[split] += group.size
    return assignment


def reference_constraint_problems(members: Iterable[SplitGroup], assignment: Mapping[str, str],
                                  constraints: Mapping[str, ReferenceHoldoutConstraint]) -> dict[str, list[str]]:
    """Holdout -> the reference constraints it fails in one stratum (empty when the stratum has no reference weight)."""

    members = list(members)
    total = sum(group.reference_weight for group in members)
    if total <= 0:
        return {}
    problems: dict[str, list[str]] = {}
    for split, constraint in constraints.items():
        weights = [group.reference_weight for group in members if assignment[group.group_id] == split and group.reference_weight > 0]
        held = sum(weights)
        failed = []
        if len(weights) < constraint.min_groups:
            failed.append("min_groups")
        if held < constraint.min_share * total:
            failed.append("min_share")
        if held and max(weights) > constraint.max_group_share * held:
            failed.append("max_group_share")
        if failed:
            problems[split] = failed
    return problems


def _assign_stratum(members: list[SplitGroup], ratios: Mapping[str, float], sink: str, holdouts: list[str], seed: str,
                    constraints: Mapping[str, ReferenceHoldoutConstraint]) -> tuple[dict[str, str], list[dict[str, Any]]]:
    pins = {group.group_id: group.pinned_split for group in members if group.pinned_split is not None}
    assignment = _place(members, pins, ratios, sink, holdouts, seed)
    moves: list[dict[str, Any]] = []
    active = {name: constraints[name] for name in holdouts if name in constraints}
    while True:
        problems = reference_constraint_problems(members, assignment, active)
        if not problems:
            return assignment, moves
        frozen = {group.group_id: assignment[group.group_id] for group in members
                  if group.reference_weight > 0 and group.group_id not in pins}
        split = next(name for name in holdouts if name in problems)
        held = sum(group.reference_weight for group in members if assignment[group.group_id] == split)
        cap = active[split].max_group_share
        eligible = [
            group for group in members
            if frozen.get(group.group_id) == sink and group.reference_weight <= cap * (held + group.reference_weight)
        ]
        if not eligible:
            return assignment, moves
        trials = {group.group_id: _place(members, {**frozen, **pins, group.group_id: split}, ratios, sink, holdouts, seed)
                  for group in eligible}
        clears = {group_id: split not in reference_constraint_problems(members, trial, {split: active[split]})
                  for group_id, trial in trials.items()}
        chosen = min(eligible, key=lambda group: (not clears[group.group_id], group.size, group.reference_weight,
                                                  _order_key(seed, group.group_id)))
        pins[chosen.group_id] = split
        moves.append({"group_id": chosen.group_id, "split": split, "failed": problems[split], "size": chosen.size,
                      "reference_weight": chosen.reference_weight, "clears": clears[chosen.group_id]})
        assignment = trials[chosen.group_id]


def _assign(groups: Iterable[SplitGroup], policy: Any, seed: str,
            constraints: Mapping[str, ReferenceHoldoutConstraint] | None) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    ratios = split_ratios(policy)
    sink, holdouts = _sink_and_holdouts(ratios)
    by_stratum: dict[str, list[SplitGroup]] = {}
    seen: set[str] = set()
    for group in groups:
        if group.group_id in seen:
            raise ValueError(f"duplicate split group id: {group.group_id}")
        if group.size < 0 or group.reference_weight < 0:
            raise ValueError(f"split group {group.group_id} has a negative size or reference weight")
        if group.pinned_split is not None and group.pinned_split not in ratios:
            raise ValueError(f"split group {group.group_id} is pinned to unknown split {group.pinned_split}")
        seen.add(group.group_id)
        by_stratum.setdefault(group.stratum, []).append(group)
    assignment: dict[str, str] = {}
    moves: dict[str, list[dict[str, Any]]] = {}
    for stratum, members in sorted(by_stratum.items()):
        placed, moved = _assign_stratum(members, ratios, sink, holdouts, seed, constraints or {})
        assignment.update(placed)
        if moved:
            moves[stratum] = moved
    return assignment, moves


def assign_group_splits_with_moves(
    groups: Iterable[SplitGroup], policy: Any, *, seed: str = DEFAULT_SPLIT_SEED,
    reference_constraints: Mapping[str, ReferenceHoldoutConstraint] | None = None,
) -> tuple[dict[str, str], dict[str, list[dict[str, Any]]]]:
    """``assign_group_splits`` plus, per stratum, the groups the reference constraints moved (step 7), in order."""

    constraints = DEFAULT_REFERENCE_CONSTRAINTS if reference_constraints is None else reference_constraints
    return _assign(groups, policy, seed, constraints)


def assign_group_splits(groups: Iterable[SplitGroup], policy: Any, *, seed: str = DEFAULT_SPLIT_SEED,
                        reference_constraints: Mapping[str, ReferenceHoldoutConstraint] | None = None) -> dict[str, str]:
    """Map each group id to its split under ``size_aware_group_split.v2`` (see the module docstring).

    Deterministic for a given set of groups, policy, seed and constraints; the input order does not matter. Group ids
    must be unique; a pinned split must be one of the policy's splits. ``reference_constraints`` defaults to
    ``DEFAULT_REFERENCE_CONSTRAINTS``; pass ``{}`` for the item placement alone (``v1``).
    """

    return assign_group_splits_with_moves(groups, policy, seed=seed, reference_constraints=reference_constraints)[0]


def split_balance_report(
    groups: Iterable[SplitGroup],
    assignment: Mapping[str, str],
    policy: Any,
    *,
    seed: str = DEFAULT_SPLIT_SEED,
    reference_constraints: Mapping[str, ReferenceHoldoutConstraint] | None = None,
) -> dict[str, Any]:
    """Per-stratum and overall item and group counts against the policy targets, and for a stratum with reference
    weight, each split's reference weight, its largest group's share, the constraint moves and any unmet constraint."""

    groups = list(groups)
    constraints = DEFAULT_REFERENCE_CONSTRAINTS if reference_constraints is None else reference_constraints
    _, moves = _assign(groups, policy, seed, constraints)
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

    by_stratum: dict[str, list[SplitGroup]] = {}
    for group in groups:
        by_stratum.setdefault(group.stratum, []).append(group)

    def reference(stratum: str) -> dict[str, Any]:
        members = by_stratum[stratum]
        total = sum(group.reference_weight for group in members)
        if total <= 0:
            return {}
        per_split = {}
        for name in ratios:
            held = [group for group in members if assignment[group.group_id] == name and group.reference_weight > 0]
            weight = sum(group.reference_weight for group in held)
            largest = max(held, key=lambda group: (group.reference_weight, group.group_id), default=None)
            per_split[name] = {
                "reference_weight": weight, "share": round(weight / total, 4), "groups": len(held),
                "largest_group": largest.group_id if largest else None,
                "largest_group_share": round(largest.reference_weight / weight, 4) if largest else None,
            }
        return {"reference": {
            "total_weight": total, "splits": per_split, "constraint_moves": moves.get(stratum, []),
            "unmet": reference_constraint_problems(members, assignment, constraints),
        }}

    return {
        "algorithm": SPLIT_ASSIGNMENT_ALGORITHM,
        "seed": seed,
        "policy": ratios,
        "reference_constraints": {name: vars(constraint) for name, constraint in sorted(constraints.items())},
        "items": overall_items,
        "groups": overall_groups,
        "item_shares": shares(overall_items),
        "strata": {
            stratum: {**record, "item_count": sum(record["items"].values()), "item_shares": shares(record["items"]),
                      **reference(stratum)}
            for stratum, record in sorted(strata.items())
        },
    }
