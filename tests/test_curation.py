from __future__ import annotations

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.dedupe.exact import deduplicate_items
from hocrgen.manifests.models import AcquiredAsset, NormalizedAssetRecord, NormalizedItemRecord
from hocrgen.split.assign import assign_splits


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
