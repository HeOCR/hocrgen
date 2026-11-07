"""F8g2 / E2d3e: size-aware assignment of whole groups to splits (``size_aware_group_split.v2``)."""

from __future__ import annotations

import random
from types import SimpleNamespace
from pathlib import Path

import pytest

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import CuratedItemRecord
from hocrgen.pipeline import _committed_benchmark_splits
from hocrgen.split.assign import assign_splits, item_reference_weight, item_split_stratum
from hocrgen.split.balance import (
    DEFAULT_REFERENCE_CONSTRAINTS,
    SPLIT_ASSIGNMENT_ALGORITHM,
    ReferenceHoldoutConstraint,
    SplitGroup,
    _order_key,
    assign_group_splits,
    assign_group_splits_with_moves,
    reference_constraint_problems,
    split_balance_report,
    split_ratios,
)

POLICY = {"train": 0.8, "validation": 0.1, "test": 0.1}


def _items(groups: list[SplitGroup], assignment: dict[str, str]) -> dict[str, int]:
    counts = {"train": 0, "validation": 0, "test": 0}
    for group in groups:
        counts[assignment[group.group_id]] += group.size
    return counts


def _lumpy_pool(seed: int = 7, count: int = 60) -> list[SplitGroup]:
    rng = random.Random(seed)
    sizes = [rng.choice([1, 1, 1, 2, 3, 5, 10, 11, 27, 55, 88]) for _ in range(count)] + [214, 188, 138]
    return [SplitGroup(group_id=f"index-{n:03d}", size=size, stratum="wikisource:printed") for n, size in enumerate(sizes)]


def test_many_small_groups_meet_the_policy_within_one_item_of_each_target() -> None:
    groups = _lumpy_pool()
    assignment = assign_group_splits(groups, POLICY)
    counts = _items(groups, assignment)
    total = sum(counts.values())
    for split, ratio in POLICY.items():
        if split != "train":
            assert abs(counts[split] - ratio * total) <= 1
    assert counts["train"] >= 0.8 * total - 2
    # Several works in each holdout, not one.
    assert sum(1 for split in assignment.values() if split == "test") >= 3


def test_each_stratum_is_balanced_on_its_own() -> None:
    groups = _lumpy_pool() + [SplitGroup(group_id=f"yid-{n}", size=size, stratum="yidtaknl:printed") for n, size in enumerate([111, 10, 2])]
    assignment = assign_group_splits(groups, POLICY)
    report = split_balance_report(groups, assignment, POLICY)
    yid = report["strata"]["yidtaknl:printed"]
    assert yid["items"]["train"] == 111
    assert yid["items"]["validation"] + yid["items"]["test"] == 12
    assert report["algorithm"] == SPLIT_ASSIGNMENT_ALGORITHM
    assert report["items"] == _items(groups, assignment)


def test_a_group_never_splits_and_a_one_group_stratum_stays_in_the_sink() -> None:
    groups = [SplitGroup(group_id="pinkas-ms", size=30, stratum="pinkas:handwritten")]
    assert assign_group_splits(groups, POLICY) == {"pinkas-ms": "train"}


def test_a_group_larger_than_a_holdout_target_never_enters_it() -> None:
    groups = [SplitGroup(group_id=f"g{n}", size=1, stratum="s") for n in range(18)] + [SplitGroup(group_id="big", size=3, stratum="s")]
    for seed in ("a", "b", "c", "d"):
        assert assign_group_splits(groups, POLICY, seed=seed)["big"] == "train"


def test_a_stratum_too_small_for_half_an_item_puts_nothing_in_a_holdout() -> None:
    groups = [SplitGroup(group_id=f"g{n}", size=1, stratum="s") for n in range(4)]
    assert set(assign_group_splits(groups, POLICY).values()) == {"train"}
    five = [SplitGroup(group_id=f"g{n}", size=1, stratum="s") for n in range(5)]
    assert sorted(assign_group_splits(five, POLICY).values()).count("train") == 3


def test_pinned_groups_keep_their_split_and_count_toward_its_target() -> None:
    groups = [SplitGroup(group_id=f"g{n}", size=1, stratum="s") for n in range(18)]
    groups.append(SplitGroup(group_id="bench", size=2, stratum="s", pinned_split="test", pin_reason="committed_split"))
    assignment = assign_group_splits(groups, POLICY)
    assert assignment["bench"] == "test"
    # The test target (2 items) is already met by the pinned group.
    assert _items(groups, assignment)["test"] == 2
    report = split_balance_report(groups, assignment, POLICY)
    assert report["strata"]["s"]["pinned_groups"] == 1


def test_assignment_is_deterministic_order_independent_and_seeded() -> None:
    groups = _lumpy_pool()
    first = assign_group_splits(groups, POLICY)
    assert assign_group_splits(list(reversed(groups)), POLICY) == first
    assert assign_group_splits(groups, POLICY, seed="other-seed") != first


def test_adding_a_group_never_moves_groups_visited_before_it() -> None:
    groups = _lumpy_pool()
    base = assign_group_splits(groups, POLICY)
    extra = SplitGroup(group_id="index-new", size=5, stratum="wikisource:printed")
    grown = assign_group_splits([*groups, extra], POLICY)
    new_key = _order_key("hocrgen-split-v1", extra.group_id)
    earlier = [group for group in groups if _order_key("hocrgen-split-v1", group.group_id) < new_key]
    # Earlier groups are visited first, with targets that moved by at most half an item of tolerance.
    moved = [group.group_id for group in earlier if base[group.group_id] != grown[group.group_id]]
    assert len(moved) <= 1
    total_moved = sum(group.size for group in groups if base[group.group_id] != grown[group.group_id])
    assert total_moved <= 0.2 * sum(group.size for group in groups)


def test_invalid_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="sum to 1.0"):
        split_ratios({"train": 0.9, "test": 0.2})
    with pytest.raises(ValueError, match="duplicate"):
        assign_group_splits([SplitGroup("a", 1, "s"), SplitGroup("a", 1, "s")], POLICY)
    with pytest.raises(ValueError, match="negative"):
        assign_group_splits([SplitGroup("a", -1, "s")], POLICY)
    with pytest.raises(ValueError, match="unknown split"):
        assign_group_splits([SplitGroup("a", 1, "s", pinned_split="holdout")], POLICY)


def test_ratios_accept_a_split_policy_and_a_two_way_mapping() -> None:
    policy = load_and_validate_bundle().profiles["profile_open_v1"].split_policy
    assert split_ratios(policy) == POLICY
    groups = [SplitGroup(group_id=f"g{n}", size=1, stratum="s") for n in range(10)]
    assignment = assign_group_splits(groups, {"train": 0.7, "test": 0.3})
    assert sorted(assignment.values()).count("test") == 3


# --- the split stage ---------------------------------------------------------------------------------------------


def _curated(item_id: str, source_id: str, *, source_group_id: str | None = None, content_type: str = "printed_historical") -> CuratedItemRecord:
    return CuratedItemRecord.model_construct(
        item_id=item_id,
        source_id=source_id,
        source_item_id=item_id.split(":", 1)[1],
        source_url="",
        metadata={"content_type": content_type},
        raw_metadata={},
        dedupe_cluster_id=None,
        near_duplicate_cluster_id=None,
        source_group_id=source_group_id,
        split=None,
        split_group_id=None,
        is_synthetic=False,
    )


def test_split_stage_balances_by_item_count_per_source_and_modality() -> None:
    policy = load_and_validate_bundle().profiles["profile_open_v1"].split_policy
    items = [
        _curated(f"wikisource_he_proofread:i{group}__p{page}", "wikisource_he_proofread", source_group_id=f"wikisource:i{group}")
        for group in range(40)
        for page in range(1 + group % 4)
    ]
    items += [
        _curated(f"pinkas_dataset_bgu:p{page}", "pinkas_dataset_bgu", source_group_id="pinkas_dataset_bgu:ms", content_type="handwritten_historical")
        for page in range(30)
    ]
    outputs = assign_splits(items, [], policy)
    report = outputs.leakage_report["split_assignment"]
    wikisource = report["strata"]["wikisource_he_proofread:printed_historical"]
    assert abs(wikisource["items"]["test"] - 0.1 * wikisource["item_count"]) <= 1
    assert abs(wikisource["items"]["validation"] - 0.1 * wikisource["item_count"]) <= 1
    assert report["strata"]["pinkas_dataset_bgu:handwritten_historical"]["items"] == {"train": 30, "validation": 0, "test": 0}
    assert outputs.leakage_report["status"] == "ok"
    assert item_split_stratum(items[-1]) == "pinkas_dataset_bgu:handwritten_historical"


def test_split_stage_pins_committed_splits_and_refuses_conflicting_pins() -> None:
    policy = load_and_validate_bundle().profiles["profile_open_v1"].split_policy
    items = [_curated(f"src:i{n}", "src", source_group_id=f"g{n}") for n in range(20)]
    outputs = assign_splits(items, [], policy, pinned_splits={"src:i3": "validation", "missing:item": "test"})
    by_id = {item.item_id: item.split for item in outputs.retained_items}
    assert by_id["src:i3"] == "validation"
    assert outputs.leakage_report["pinned_group_count"] == 1
    shared = [_curated("src:a", "src", source_group_id="shared"), _curated("src:b", "src", source_group_id="shared")]
    with pytest.raises(ValueError, match="pinned to both"):
        assign_splits(shared, [], policy, pinned_splits={"src:a": "test", "src:b": "validation"})


def test_split_stage_reads_the_committed_benchmark_splits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundle = load_and_validate_bundle()
    pins = _committed_benchmark_splits(bundle)
    assert pins == {
        "nli_any_use_permitted:nli-ms-seed-006": "train",
        "pinkas_open:pinkas-ledger-001": "train",
        "project_synthetic:synthetic-0": "train",
    }
    with monkeypatch.context() as patch:
        patch.setattr("hocrgen.pipeline.resolve_benchmark_data_root", lambda _root: tmp_path / "none")
        assert _committed_benchmark_splits(bundle) == {}
    broken = tmp_path / "broken" / "benchmark_data" / "benchmark_v1"
    broken.mkdir(parents=True)
    (broken / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="benchmark config validation failed"):
        _committed_benchmark_splits(SimpleNamespace(config_root=tmp_path / "broken" / "config"))


# --- E2d3e: reference constraints (size_aware_group_split.v2) ----------------------------------------------------


def _reference_pool() -> list[SplitGroup]:
    """Forty unweighted books, one heavily weighted book that lands in test, and four weighted books in train.

    The heavy book's place depends on the seeded order; the helper finds a seed that puts it in test alone.
    """
    groups = [SplitGroup(group_id=f"q3-{n:02d}", size=1 + n % 5, stratum="ws") for n in range(40)]
    groups += [
        SplitGroup(group_id="heavy", size=3, stratum="ws", reference_weight=2700),
        SplitGroup(group_id="small-light", size=7, stratum="ws", reference_weight=2250),
        SplitGroup(group_id="small-even", size=10, stratum="ws", reference_weight=2700),
        SplitGroup(group_id="mid-even", size=11, stratum="ws", reference_weight=4500),
        SplitGroup(group_id="huge", size=60, stratum="ws", reference_weight=15000),
    ]
    return groups


def _seed_with_heavy_alone_in_test(groups: list[SplitGroup]) -> str:
    for n in range(500):
        seed = f"s{n}"
        v1 = assign_group_splits(groups, POLICY, seed=seed, reference_constraints={})
        weighted_in_test = [g.group_id for g in groups if g.reference_weight and v1[g.group_id] == "test"]
        if weighted_in_test == ["heavy"]:
            return seed
    raise AssertionError("no seed puts the heavy book alone in test")


def test_without_reference_weight_v2_places_exactly_as_v1() -> None:
    groups = _lumpy_pool()
    assert assign_group_splits(groups, POLICY) == assign_group_splits(groups, POLICY, reference_constraints={})
    report = split_balance_report(groups, assign_group_splits(groups, POLICY), POLICY)
    assert "reference" not in report["strata"]["wikisource:printed"]
    assert report["reference_constraints"]["test"] == vars(DEFAULT_REFERENCE_CONSTRAINTS["test"])


def test_the_constraint_moves_the_fewest_item_group_that_clears_it_and_nothing_else_weighted() -> None:
    groups = _reference_pool()
    seed = _seed_with_heavy_alone_in_test(groups)
    v1 = assign_group_splits(groups, POLICY, seed=seed, reference_constraints={})
    v2, moves = assign_group_splits_with_moves(groups, POLICY, seed=seed)
    # small-light (7 items) does not clear the 50% cap beside heavy; small-even (10 items) does.
    assert [move["group_id"] for move in moves["ws"]] == ["small-even"]
    assert moves["ws"][0]["clears"] is True and "max_group_share" in moves["ws"][0]["failed"]
    assert v2["small-even"] == "test" and v2["heavy"] == "test"
    # Every other weighted group keeps its split; only unweighted groups refill around the move.
    for group in groups:
        if group.reference_weight and group.group_id != "small-even":
            assert v2[group.group_id] == v1[group.group_id]
    assert reference_constraint_problems(groups, v2, DEFAULT_REFERENCE_CONSTRAINTS) == {}
    counts = _items(groups, v2)
    total = sum(counts.values())
    assert counts["test"] <= 0.1 * total + 0.5 + 10  # the move may overshoot the item target by its own size
    report = split_balance_report(groups, v2, POLICY, seed=seed)["strata"]["ws"]["reference"]
    assert report["constraint_moves"][0]["group_id"] == "small-even" and report["unmet"] == {}
    assert report["splits"]["test"]["groups"] == 2 and report["splits"]["test"]["largest_group_share"] == 0.5


def test_each_reference_constraint_is_checked() -> None:
    groups = [SplitGroup("a", 1, "s", reference_weight=60), SplitGroup("b", 1, "s", reference_weight=40),
              SplitGroup("c", 1, "s", reference_weight=900)]
    in_test = {"a": "test", "b": "test", "c": "train"}
    assert reference_constraint_problems(groups, in_test, {"test": ReferenceHoldoutConstraint(min_groups=3)}) == {"test": ["min_groups"]}
    assert reference_constraint_problems(groups, in_test, {"test": ReferenceHoldoutConstraint(min_share=0.2)}) == {"test": ["min_share"]}
    assert reference_constraint_problems(groups, in_test, {"test": ReferenceHoldoutConstraint(max_group_share=0.5)}) == {"test": ["max_group_share"]}
    assert reference_constraint_problems(groups, in_test, {"test": ReferenceHoldoutConstraint(min_groups=2, max_group_share=0.6)}) == {}
    assert reference_constraint_problems([SplitGroup("z", 1, "s")], {"z": "test"}, DEFAULT_REFERENCE_CONSTRAINTS) == {}


def test_a_group_that_would_dominate_the_holdout_is_never_moved_and_an_unmet_constraint_is_reported() -> None:
    groups = [SplitGroup(f"u{n}", 1, "s") for n in range(18)] + [SplitGroup("huge", 2, "s", reference_weight=1000)]
    assignment, moves = assign_group_splits_with_moves(groups, POLICY)
    assert assignment["huge"] == "train" and moves == {}
    report = split_balance_report(groups, assignment, POLICY)["strata"]["s"]["reference"]
    assert report["unmet"] == {"test": ["min_groups", "min_share"]}


def test_v2_is_deterministic_and_order_independent() -> None:
    groups = _reference_pool()
    seed = _seed_with_heavy_alone_in_test(groups)
    first = assign_group_splits(groups, POLICY, seed=seed)
    assert assign_group_splits(list(reversed(groups)), POLICY, seed=seed) == first
    with pytest.raises(ValueError, match="negative"):
        assign_group_splits([SplitGroup("a", 1, "s", reference_weight=-1)], POLICY)


def test_split_stage_weights_adjudication_eligible_items_and_marks_constraint_moves() -> None:
    policy = load_and_validate_bundle().profiles["profile_open_v1"].split_policy
    pool = _reference_pool()
    seed = _seed_with_heavy_alone_in_test(pool)
    items = []
    for group in pool:
        for page in range(group.size):
            item = _curated(f"wikisource_he_proofread:{group.group_id}__p{page}", "wikisource_he_proofread", source_group_id=group.group_id)
            if group.reference_weight and page == 0:
                item.metadata.update({"scored_reference_characters": group.reference_weight})
            items.append(item)
    assert item_reference_weight(items[-60]) == 15000
    assert item_reference_weight(_curated("x:y", "x")) == 0
    outputs = assign_splits(items, [], policy, seed=seed)
    by_group = {item.split_group_id: item for item in outputs.assignments}
    moved = [record for record in outputs.assignments if record.split_constraint == "reference_constraint"]
    assert {record.split_group_id for record in moved} == {"small-even"} and all(record.split == "test" for record in moved)
    assert by_group["heavy"].split == "test" and by_group["heavy"].split_constraint is None
    stratum = outputs.leakage_report["split_assignment"]["strata"]["wikisource_he_proofread:printed_historical"]
    assert stratum["reference"]["unmet"] == {}
