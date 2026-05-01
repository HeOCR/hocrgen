from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.dedupe.exact import deduplicate_items
from hocrgen.manifests.models import AcquiredAsset, NormalizedAssetRecord, NormalizedItemRecord
from hocrgen.pipeline import _run_build_release, PipelineState
from hocrgen.split import assign as split_assign_module
from hocrgen.split.assign import _validate_leakage, assign_splits


def _normalized_item(
    *,
    item_id: str,
    source_id: str,
    source_item_id: str,
    asset_hashes: list[str],
    is_synthetic: bool = False,
) -> NormalizedItemRecord:
    acquired_assets = [
        AcquiredAsset(item_id=item_id, path=f"/tmp/{item_id}_{index}.svg", sha256=asset_hash)
        for index, asset_hash in enumerate(asset_hashes, start=1)
    ]
    normalized_assets = [
        NormalizedAssetRecord(
            item_id=item_id,
            source_asset_path=f"/tmp/{item_id}_{index}.svg",
            normalized_asset_path=f"/tmp/normalized/{item_id}_{index}.svg",
            asset_format="svg",
            media_type="image/svg+xml",
            width=100,
            height=50,
            file_size_bytes=128,
            sha256=asset_hash,
            is_vector=True,
            normalization_action="copied",
            preview_generated=True,
            preview_path=f"/tmp/preview/{item_id}_{index}.svg",
            preview_action="copied_from_normalized_asset",
        )
        for index, asset_hash in enumerate(asset_hashes, start=1)
    ]
    return NormalizedItemRecord(
        candidate_id=f"candidate-{item_id}",
        source_id=source_id,
        source_item_id=source_item_id,
        source_url=f"https://example.org/{item_id}",
        discovery_method="fixture",
        item_id=item_id,
        normalized_license="PD-IL",
        rights_classification="open",
        eligibility="accepted",
        eligibility_reason="eligible",
        is_synthetic=is_synthetic,
        provenance={"source_name": source_id},
        acquired_assets=acquired_assets,
        normalized_assets=normalized_assets,
        qa_status="passed",
        qa_fail_reasons=[],
    )


def test_exact_dedupe_detects_item_level_duplicates() -> None:
    profile = load_and_validate_bundle().profiles["profile_open_v1"]
    retained_and_duplicate = [
        _normalized_item(item_id="pinkas_open:item-a", source_id="pinkas_open", source_item_id="folio-1", asset_hashes=["a1", "a2"]),
        _normalized_item(item_id="biblia_open:item-b", source_id="biblia_open", source_item_id="fragment-1", asset_hashes=["a1", "a2"]),
    ]

    outputs = deduplicate_items(retained_and_duplicate, profile)

    assert len(outputs.retained_items) == 1
    assert len(outputs.duplicate_items) == 1
    assert outputs.retained_items[0].canonical_item_id == "pinkas_open:item-a"
    assert outputs.duplicate_relations[0].reason == "exact_asset_sequence_match"
    assert outputs.duplicate_clusters[0].member_item_ids == ["pinkas_open:item-a", "biblia_open:item-b"]


def test_canonical_selection_prefers_source_order_then_non_synthetic_then_item_id() -> None:
    profile = load_and_validate_bundle().profiles["profile_open_v1"]
    same_fingerprint = ["same"]

    source_priority_outputs = deduplicate_items(
        [
            _normalized_item(item_id="biblia_open:z-item", source_id="biblia_open", source_item_id="fragment-z", asset_hashes=same_fingerprint),
            _normalized_item(item_id="pinkas_open:a-item", source_id="pinkas_open", source_item_id="folio-a", asset_hashes=same_fingerprint),
        ],
        profile,
    )
    assert source_priority_outputs.retained_items[0].item_id == "pinkas_open:a-item"

    synthetic_tiebreak_outputs = deduplicate_items(
        [
            _normalized_item(item_id="nli_any_use_permitted:real", source_id="nli_any_use_permitted", source_item_id="real", asset_hashes=same_fingerprint, is_synthetic=False),
            _normalized_item(item_id="nli_any_use_permitted:synthetic", source_id="nli_any_use_permitted", source_item_id="synthetic", asset_hashes=same_fingerprint, is_synthetic=True),
        ],
        profile,
    )
    assert synthetic_tiebreak_outputs.retained_items[0].item_id == "nli_any_use_permitted:real"

    item_id_tiebreak_outputs = deduplicate_items(
        [
            _normalized_item(item_id="nli_any_use_permitted:z-item", source_id="nli_any_use_permitted", source_item_id="z-item", asset_hashes=same_fingerprint),
            _normalized_item(item_id="nli_any_use_permitted:a-item", source_id="nli_any_use_permitted", source_item_id="a-item", asset_hashes=same_fingerprint),
        ],
        profile,
    )
    assert item_id_tiebreak_outputs.retained_items[0].item_id == "nli_any_use_permitted:a-item"


def test_split_assignment_is_deterministic_and_cluster_safe() -> None:
    profile = load_and_validate_bundle().profiles["profile_open_v1"]
    dedupe_outputs = deduplicate_items(
        [
            _normalized_item(item_id="pinkas_open:item-a", source_id="pinkas_open", source_item_id="folio-1", asset_hashes=["dup"]),
            _normalized_item(item_id="biblia_open:item-b", source_id="biblia_open", source_item_id="fragment-1", asset_hashes=["dup"]),
            _normalized_item(item_id="project_synthetic:item-c", source_id="project_synthetic", source_item_id="synthetic-1", asset_hashes=["unique"]),
        ],
        profile,
    )

    first = assign_splits(dedupe_outputs.retained_items, dedupe_outputs.duplicate_items, profile.split_policy)
    second = assign_splits(dedupe_outputs.retained_items, dedupe_outputs.duplicate_items, profile.split_policy)

    assert [record.model_dump() for record in first.assignments] == [record.model_dump() for record in second.assignments]
    assert first.leakage_report["status"] == "ok"
    duplicate = first.duplicate_items[0]
    canonical = next(item for item in first.retained_items if item.item_id == duplicate.canonical_item_id)
    assert duplicate.split_group_id == canonical.split_group_id
    assert duplicate.split == canonical.split


def test_pick_split_can_reach_test_bucket(monkeypatch) -> None:
    profile = load_and_validate_bundle().profiles["profile_open_v1"]
    monkeypatch.setattr(split_assign_module, "_stable_bucket", lambda _: 0.95)

    dedupe_outputs = deduplicate_items(
        [
            _normalized_item(
                item_id="nli_any_use_permitted:item-test",
                source_id="nli_any_use_permitted",
                source_item_id="item-test",
                asset_hashes=["test-bucket"],
            )
        ],
        profile,
    )
    outputs = assign_splits(dedupe_outputs.retained_items, dedupe_outputs.duplicate_items, profile.split_policy)

    assert outputs.retained_items[0].split == "test"


def test_validate_leakage_skips_items_without_split_metadata() -> None:
    item = deduplicate_items(
        [
            _normalized_item(
                item_id="nli_any_use_permitted:item-nosplit",
                source_id="nli_any_use_permitted",
                source_item_id="item-nosplit",
                asset_hashes=["nosplit"],
            )
        ],
        load_and_validate_bundle().profiles["profile_open_v1"],
    ).retained_items[0]

    report = _validate_leakage([item])

    assert report["status"] == "ok"
    assert report["group_count"] == 0


def test_assign_splits_uses_canonical_split_when_duplicate_group_assignment_missing(monkeypatch) -> None:
    profile = load_and_validate_bundle().profiles["profile_open_v1"]
    dedupe_outputs = deduplicate_items(
        [
            _normalized_item(item_id="pinkas_open:item-a", source_id="pinkas_open", source_item_id="folio-1", asset_hashes=["dup-fallback"]),
            _normalized_item(item_id="biblia_open:item-b", source_id="biblia_open", source_item_id="fragment-1", asset_hashes=["dup-fallback"]),
        ],
        profile,
    )

    original_split_group_id = split_assign_module._split_group_id

    def fake_split_group_id(item):
        if item.dedupe_status == "duplicate":
            return f"{item.item_id}:fallback"
        return original_split_group_id(item)

    monkeypatch.setattr(split_assign_module, "_split_group_id", fake_split_group_id)
    outputs = assign_splits(dedupe_outputs.retained_items, dedupe_outputs.duplicate_items, profile.split_policy)

    canonical = outputs.retained_items[0]
    duplicate = outputs.duplicate_items[0]
    assert duplicate.split == canonical.split
    assert duplicate.split_group_id != canonical.split_group_id


def test_assign_splits_raises_when_leakage_report_is_error(monkeypatch) -> None:
    profile = load_and_validate_bundle().profiles["profile_open_v1"]
    dedupe_outputs = deduplicate_items(
        [
            _normalized_item(
                item_id="nli_any_use_permitted:item-error",
                source_id="nli_any_use_permitted",
                source_item_id="item-error",
                asset_hashes=["error"],
            )
        ],
        profile,
    )
    monkeypatch.setattr(
        split_assign_module,
        "_validate_leakage",
        lambda items: {
            "duplicate_cluster_leaks": [],
            "group_count": 1,
            "split_group_leaks": [{"split_group_id": "forced", "splits": ["train", "test"]}],
            "status": "error",
        },
    )

    try:
        assign_splits(dedupe_outputs.retained_items, dedupe_outputs.duplicate_items, profile.split_policy)
    except ValueError as exc:
        assert str(exc) == "split leakage detected"
    else:
        raise AssertionError("expected split leakage error")


def test_build_release_ignores_retained_items_without_split_in_source_split_stats(tmp_path: Path, monkeypatch) -> None:
    bundle = load_and_validate_bundle()
    context = create_run_context(profile_id="profile_open_v1", dry_run=True, workdir=tmp_path)
    retained = deduplicate_items(
        [
            _normalized_item(
                item_id="nli_any_use_permitted:item-unsplit",
                source_id="nli_any_use_permitted",
                source_item_id="item-unsplit",
                asset_hashes=["unsplit"],
            )
        ],
        bundle.profiles["profile_open_v1"],
    ).retained_items
    state = PipelineState(
        retained_items=retained,
        release_ready_items=retained,
        leakage_report={"status": "ok", "duplicate_cluster_leaks": [], "split_group_leaks": [], "group_count": 0},
    )
    monkeypatch.setattr(
        "hocrgen.pipeline.select_benchmark_items",
        lambda **kwargs: SimpleNamespace(
            audit=[],
            card_markdown="",
            config=SimpleNamespace(benchmark_id="benchmark_v1"),
            items=[],
            stability_policy={},
        ),
    )
    monkeypatch.setattr(
        "hocrgen.pipeline.select_annotation_pilot_items",
        lambda **kwargs: SimpleNamespace(
            audit=[],
            config=SimpleNamespace(pilot_id="e3a_annotation_pilot"),
            manifest=SimpleNamespace(
                layout_label_task_count=0,
                layout_labels_required_for_release=False,
                model_dump=lambda mode: {
                    "pilot_id": "e3a_annotation_pilot",
                    "items": [],
                    "pilot_item_count": 0,
                    "schema_version": 1,
                },
                pilot_item_count=0,
                transcription_required_for_release=False,
                transcription_task_count=0,
            ),
        ),
    )

    _run_build_release(bundle, context, options=None, state=state)  # type: ignore[arg-type]
    source_stats_path = context.stage_dir("build_release") / "source_stats.json"
    source_stats = __import__("json").loads(source_stats_path.read_text(encoding="utf-8"))

    assert source_stats["sources_by_split"] == {}
