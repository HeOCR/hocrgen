from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hocrgen.benchmark import load_benchmark_config, resolve_benchmark_data_root, select_benchmark_items
from hocrgen.config.loader import default_config_root
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import BenchmarkConfigRecord, NormalizedAssetRecord, PrivacyScannedItemRecord


def _benchmark_config_root(tmp_path: Path, payload: dict) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    benchmark_root = tmp_path / "benchmark_data" / "benchmark_v1"
    benchmark_root.mkdir(parents=True)
    (benchmark_root / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return config_root


def _valid_payload() -> dict:
    return {
        "approved_items": [
            {
                "benchmark_split": "train",
                "item_id": "nli_any_use_permitted:nli-ms-seed-006",
                "rationale": "real exemplar",
            }
        ],
        "benchmark_id": "benchmark_v1",
        "description": "fixture benchmark",
        "review_bar": "explicit approval required",
        "selection_policy": "representative mixed",
        "stability_policy": {"splits": "stable"},
        "version": 1,
    }


def test_load_benchmark_config_accepts_valid_repo_tracked_config(tmp_path: Path) -> None:
    config = load_benchmark_config(_benchmark_config_root(tmp_path, _valid_payload()))

    assert config.benchmark_id == "benchmark_v1"
    assert len(config.approved_items) == 1


def test_load_benchmark_config_rejects_duplicate_approved_items(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["approved_items"].append(dict(payload["approved_items"][0]))

    with pytest.raises(ConfigValidationError, match="benchmark config validation failed"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))


def test_load_benchmark_config_rejects_invalid_split(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["approved_items"][0]["benchmark_split"] = "dev"

    with pytest.raises(ConfigValidationError, match="benchmark config validation failed"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))


def test_load_benchmark_config_rejects_empty_approved_items(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["approved_items"] = []

    with pytest.raises(ConfigValidationError, match="benchmark config validation failed"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))


def test_resolve_benchmark_data_root_falls_back_without_unbounded_parent_search(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    unrelated = tmp_path / "benchmark_data" / "benchmark_v1"
    unrelated.mkdir(parents=True)
    (unrelated / "config.json").write_text("{}", encoding="utf-8")
    config_root = tmp_path / "nested" / "project" / "config"
    config_root.mkdir(parents=True)
    missing_default = tmp_path / "missing" / "src" / "hocrgen" / "config"
    monkeypatch.setattr("hocrgen.benchmark.default_config_root", lambda: missing_default)

    assert resolve_benchmark_data_root(config_root) == config_root.parent / "benchmark_data"


def test_load_benchmark_config_rejects_id_mismatch(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["benchmark_id"] = "other_benchmark"

    with pytest.raises(ConfigValidationError, match="benchmark config id mismatch"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))


def test_select_benchmark_items_rejects_missing_split_assignment(tmp_path: Path) -> None:
    item = _benchmark_item(tmp_path, split="train").model_copy(update={"split_group_id": None})

    with pytest.raises(StageExecutionError, match="missing a split assignment"):
        select_benchmark_items(
            config=_benchmark_config(),
            release_ready_items=[item],
            review_required_items=[],
            blocked_items=[],
            removed_duplicate_items=[],
        )


def test_select_benchmark_items_rejects_changed_split(tmp_path: Path) -> None:
    with pytest.raises(StageExecutionError, match="split changed: expected train, got validation"):
        select_benchmark_items(
            config=_benchmark_config(),
            release_ready_items=[_benchmark_item(tmp_path, split="validation")],
            review_required_items=[],
            blocked_items=[],
            removed_duplicate_items=[],
        )


@pytest.mark.parametrize(
    ("bucket", "expected_reason"),
    [
        ("review_required_items", "review_required"),
        ("blocked_items", "blocked"),
        ("removed_duplicate_items", "duplicate_removed"),
    ],
)
def test_select_benchmark_items_reports_non_release_ready_reason(
    tmp_path: Path,
    bucket: str,
    expected_reason: str,
) -> None:
    item = _benchmark_item(tmp_path, split="train")
    kwargs = {
        "review_required_items": [],
        "blocked_items": [],
        "removed_duplicate_items": [],
    }
    kwargs[bucket] = [item]

    with pytest.raises(StageExecutionError, match=expected_reason):
        select_benchmark_items(
            config=_benchmark_config(),
            release_ready_items=[],
            **kwargs,
        )


def _benchmark_config() -> BenchmarkConfigRecord:
    return BenchmarkConfigRecord.model_validate(_valid_payload())


def _benchmark_item(tmp_path: Path, *, split: str | None) -> PrivacyScannedItemRecord:
    item_id = "nli_any_use_permitted:nli-ms-seed-006"
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    normalized_asset = NormalizedAssetRecord(
        item_id=item_id,
        source_asset_path=str(asset_path),
        normalized_asset_path=str(asset_path),
        asset_format="svg",
        media_type="image/svg+xml",
        width=100,
        height=100,
        file_size_bytes=6,
        sha256="abc123",
        is_vector=True,
        normalization_action="copied",
        preview_generated=False,
    )
    return PrivacyScannedItemRecord.model_validate(
        {
            "candidate_id": item_id,
            "source_id": "nli_any_use_permitted",
            "source_item_id": "nli-ms-seed-006",
            "source_url": "https://example.org/nli-ms-seed-006",
            "discovery_method": "test",
            "title": item_id,
            "fixture_path": None,
            "raw_metadata": {},
            "raw_rights_text": "Any Use Permitted",
            "asset_references": [],
            "metadata": {},
            "item_id": item_id,
            "normalized_license": "CC-BY-4.0",
            "rights_classification": "open",
            "eligibility": "accepted",
            "eligibility_reason": "allowed_by_profile",
            "is_synthetic": False,
            "provenance": {},
            "acquired_assets": [],
            "normalized_assets": [normalized_asset.model_dump(mode="python")],
            "qa_status": "passed",
            "qa_fail_reasons": [],
            "content_fingerprint": f"fingerprint-{item_id}",
            "dedupe_cluster_id": None,
            "dedupe_status": "retained",
            "canonical_item_id": item_id,
            "split": split,
            "split_group_id": f"group-{item_id}",
            "content_class": "printed",
            "content_confidence": 0.9,
            "period_class": "historical",
            "period_confidence": 0.9,
            "language_class": "hebrew_only",
            "language_confidence": 0.9,
            "quality_score": 0.9,
            "quality_tier": "high",
            "classification_review_reasons": [],
            "privacy_flag": "clear",
            "privacy_reasons": [],
            "privacy_decision": "release_ready",
        }
    )
