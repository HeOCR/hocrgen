from __future__ import annotations

import json
import shutil
import subprocess
from argparse import Namespace
from collections import Counter
from datetime import UTC
from pathlib import Path

import pytest

from hocrgen.cli import handle_export_alpha, main
from hocrgen.annotations import build_annotation_manifest
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.config.models import RightsClassification
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    AnnotationManifestItemRecord,
    AlphaExportedItemRecord,
    LayoutLabelReference,
    NormalizedAssetRecord,
    PrivacyScannedItemRecord,
    ReviewQueueRecord,
    TranscriptionReference,
)
from hocrgen.package.alpha import (
    AlphaExportConfig,
    BenchmarkExportInputs,
    REPO_ROOT,
    _benchmark_card_for_export,
    _build_release_diff,
    _changelog_doc,
    _audit_item_payload,
    _build_source_stats,
    _copy_export_assets,
    _current_commit_sha,
    _load_baseline_item_manifest,
    _public_item_payload,
    _parse_exported_at,
    _resolve_comparison_release,
    _review_queue_payload,
    _copy_review_previews,
    _handoff_doc,
    _sanitize_portable_value,
    _select_alpha_items,
    _synthetic_composition_lines,
    _source_priority,
    _split_sort_key,
    _validate_heocr_repo_root,
    _validate_overwrite_target,
    export_alpha_release,
)
from hocrgen.synthetic.reporting import synthetic_composition_report


def _fixture_config_root(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    fixture_seed = (Path(__file__).parent / "fixtures" / "nli" / "seeds_default.yaml").resolve()
    sources_path = config_root / "sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace(
            "package://data/nli/seeds.yaml", str(fixture_seed)
        ),
        encoding="utf-8",
    )
    return config_root


def test_synthetic_composition_helpers_cover_empty_and_missing_metadata() -> None:
    missing_metadata_item = Namespace(
        is_synthetic=True,
        metadata={},
        split=None,
    )
    real_item = Namespace(
        is_synthetic=False,
        metadata={},
        split="train",
    )

    empty_report = synthetic_composition_report([real_item])
    missing_report = synthetic_composition_report([real_item, missing_metadata_item])

    assert _synthetic_composition_lines(empty_report) == ["- Synthetic items: 0"]
    assert missing_report["by_template_id"] == {"unknown": 1}
    assert missing_report["by_recipe_id"] == {"unknown": 1}
    assert missing_report["by_degradation_preset"] == {"unknown": 1}
    assert missing_report["by_font_id"] == {"unknown": 1}
    assert missing_report["missing_metadata"] == {
        "synthetic_degradation_preset": 1,
        "synthetic_font_id": 1,
        "synthetic_hebrew_coverage": 1,
        "synthetic_layout_family": 1,
        "synthetic_provider_version": 1,
        "synthetic_recipe_id": 1,
        "synthetic_template_id": 1,
    }


def test_export_alpha_creates_heocr_shaped_tree(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "HeOCR" / "releases" / "alpha-v0"

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["export_dir"] == str(output_dir)
    assert (output_dir / "data").exists()
    assert (output_dir / "manifests" / "item_manifest.json").exists()
    assert (output_dir / "manifests" / "annotation_manifest.json").exists()
    assert (output_dir / "manifests" / "annotation_pilot_manifest.json").exists()
    assert (output_dir / "manifests" / "annotation_pilot_selection_audit.json").exists()
    assert (output_dir / "manifests" / "benchmark_manifest.json").exists()
    assert (output_dir / "manifests" / "benchmark_leakage_risk.json").exists()
    assert (output_dir / "manifests" / "benchmark_selection_audit.json").exists()
    assert (output_dir / "manifests" / "benchmark_stability_policy.json").exists()
    assert (output_dir / "manifests" / "benchmark_reference_manifest.json").exists()
    assert (output_dir / "manifests" / "benchmark_reference_status.json").exists()
    assert (output_dir / "manifests" / "benchmark_reference_versioning.json").exists()
    assert (output_dir / "manifests" / "release_diff.json").exists()
    assert (output_dir / "docs" / "BENCHMARK_CARD.md").exists()
    assert (output_dir / "docs" / "CHANGELOG.md").exists()
    assert (output_dir / "docs" / "DATASET_CARD.md").exists()
    assert (output_dir / "docs" / "RELEASE_NOTES.md").exists()
    assert (output_dir / "docs" / "PROVENANCE.md").exists()
    assert (output_dir / "docs" / "HANDOFF.md").exists()
    handoff_doc = (output_dir / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert "- Target repo checkout: `<manual target checkout>`" in handoff_doc
    assert "- Target release dir: `releases/alpha-v0/`" in handoff_doc
    assert str(output_dir.resolve()) not in handoff_doc

    release_diff = json.loads((output_dir / "manifests" / "release_diff.json").read_text(encoding="utf-8"))
    benchmark_manifest = json.loads((output_dir / "manifests" / "benchmark_manifest.json").read_text(encoding="utf-8"))
    benchmark_leakage_risk = json.loads((output_dir / "manifests" / "benchmark_leakage_risk.json").read_text(encoding="utf-8"))
    benchmark_reference_manifest = json.loads(
        (output_dir / "manifests" / "benchmark_reference_manifest.json").read_text(encoding="utf-8")
    )
    benchmark_reference_status = json.loads(
        (output_dir / "manifests" / "benchmark_reference_status.json").read_text(encoding="utf-8")
    )
    annotation_pilot_manifest = json.loads(
        (output_dir / "manifests" / "annotation_pilot_manifest.json").read_text(encoding="utf-8")
    )
    benchmark_card = (output_dir / "docs" / "BENCHMARK_CARD.md").read_text(encoding="utf-8")
    changelog = (output_dir / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (output_dir / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert release_diff["previous_version"] is None
    assert release_diff["counts"] == {"added": 4, "removed": 0, "changed": 0, "unchanged": 0}
    assert {item["item_id"] for item in benchmark_manifest["items"]} == {
        "nli_any_use_permitted:nli-ms-seed-006",
        "pinkas_open:pinkas-ledger-001",
        "project_synthetic:synthetic-0",
    }
    assert str(output_dir.resolve()) not in json.dumps(benchmark_manifest)
    assert benchmark_leakage_risk["status"] == "ok"
    assert str(output_dir.resolve()) not in json.dumps(benchmark_leakage_risk)
    assert benchmark_reference_manifest["reference_manifest_id"] == "benchmark_v1_refs_0001"
    assert benchmark_reference_status["counts"]["reference_ready"] == 1
    reference_paths = [
        reference["path"]
        for item in benchmark_reference_manifest["items"]
        for reference in [item.get("transcription_reference"), *item.get("layout_label_references", [])]
        if reference is not None
    ]
    layout_asset_paths = [
        asset["path"]
        for path in reference_paths
        if "layout.json" in path
        for asset in json.loads((output_dir / path).read_text(encoding="utf-8"))["assets"]
    ]
    assert reference_paths
    assert all((output_dir / path).is_file() for path in reference_paths)
    assert all((output_dir / path).is_file() for path in layout_asset_paths)
    assert str(output_dir.resolve()) not in json.dumps(benchmark_reference_manifest)
    assert annotation_pilot_manifest["pilot_id"] == "e3a_annotation_pilot"
    assert annotation_pilot_manifest["pilot_item_count"] == 2
    assert str(output_dir.resolve()) not in json.dumps(annotation_pilot_manifest)
    assert "Selection Policy" in benchmark_card
    assert "Review Bar" in benchmark_card
    assert "Stability Policy" in benchmark_card
    assert changelog.startswith("# Changelog: alpha-v0")
    assert "Previous version: none" in changelog
    assert "initial-release addition summary" in release_notes


def test_export_alpha_can_target_heocr_repo_checkout(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    heocr_repo = tmp_path / "HeOCR"
    (heocr_repo / ".git").mkdir(parents=True)

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--heocr-repo",
            str(heocr_repo),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    expected_export_dir = heocr_repo / "releases" / "alpha-v0"
    assert exit_code == 0
    assert payload["export_dir"] == str(expected_export_dir.resolve())
    assert payload["handoff_repo"] == str(heocr_repo.resolve())
    assert (expected_export_dir / "docs" / "HANDOFF.md").exists()
    handoff_doc = (expected_export_dir / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert "- Target repo checkout: `HeOCR`" in handoff_doc
    assert "- Target release dir: `releases/alpha-v0/`" in handoff_doc
    assert str(heocr_repo.resolve()) not in handoff_doc
    assert str(expected_export_dir.resolve()) not in handoff_doc


def test_export_alpha_only_copies_release_ready_items(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    item_manifest = json.loads((export_dir / "manifests" / "item_manifest.json").read_text(encoding="utf-8"))
    review_required = json.loads((export_dir / "manifests" / "review_required_items.json").read_text(encoding="utf-8"))
    blocked = json.loads((export_dir / "manifests" / "blocked_items.json").read_text(encoding="utf-8"))
    review_queue = json.loads((export_dir / "manifests" / "review_queue.json").read_text(encoding="utf-8"))
    split_manifest = json.loads((export_dir / "manifests" / "split_manifest.json").read_text(encoding="utf-8"))

    exported_ids = {item["item_id"] for item in item_manifest["items"]}
    assert "nli_any_use_permitted:nli-ms-001" not in exported_ids
    assert "biblia_open:biblia-doc-001" not in exported_ids
    assert "nli_any_use_permitted:nli-ms-seed-006" in exported_ids
    assert len(item_manifest["items"]) == 4
    assert len(split_manifest["items"]) == 4
    assert len(review_required["items"]) == 1
    assert {item["source_id"] for item in review_required["items"]} == {"biblia_open"}
    for item in review_required["items"]:
        assert "raw_metadata" not in item
        assert "fixture_path" not in item
        assert "normalized_assets" not in item
    for item in review_queue["items"]:
        for preview_path in item["preview_paths"]:
            assert not Path(preview_path).is_absolute()
            assert (export_dir / preview_path).exists()
    assert blocked["items"] == []
    assert "normalized_assets" not in item_manifest["items"][0]
    assert "asset_references" not in item_manifest["items"][0]
    assert "acquired_assets" not in item_manifest["items"][0]

    for item in item_manifest["items"]:
        item_dir = export_dir / "data" / item["split"] / item["item_id"]
        assert item_dir.exists()
        for asset in item["exported_assets"]:
            assert (export_dir / asset["release_asset_path"]).exists()
            assert "source_normalized_asset_path" not in asset
            assert "source_preview_path" not in asset
    synthetic_items = [item for item in item_manifest["items"] if item["source_id"] == "project_synthetic"]
    assert {item["metadata"]["synthetic_template_id"] for item in synthetic_items} == {
        "printed_letter",
        "handwritten_note",
    }
    for synthetic_item in synthetic_items:
        assert {asset["asset_format"] for asset in synthetic_item["exported_assets"]} == {"jpeg"}
        assert all(asset["release_asset_path"].endswith(".jpg") for asset in synthetic_item["exported_assets"])


def test_export_alpha_enforces_real_and_synthetic_caps_deterministically(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    first_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work1"),
            "--max-real-items",
            "1",
            "--max-synthetic-items",
            "1",
        ]
    )
    assert first_exit == 0
    first_payload = json.loads(capsys.readouterr().out)
    first_export_dir = Path(first_payload["export_dir"])
    first_manifest = json.loads((first_export_dir / "manifests" / "item_manifest.json").read_text(encoding="utf-8"))
    first_summary = json.loads((first_export_dir / "manifests" / "release_summary.json").read_text(encoding="utf-8"))
    first_benchmark_manifest = json.loads(
        (first_export_dir / "manifests" / "benchmark_manifest.json").read_text(encoding="utf-8")
    )
    first_benchmark_card = (first_export_dir / "docs" / "BENCHMARK_CARD.md").read_text(encoding="utf-8")

    second_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work2"),
            "--max-real-items",
            "1",
            "--max-synthetic-items",
            "1",
        ]
    )
    assert second_exit == 0
    second_payload = json.loads(capsys.readouterr().out)
    second_export_dir = Path(second_payload["export_dir"])
    second_manifest = json.loads((second_export_dir / "manifests" / "item_manifest.json").read_text(encoding="utf-8"))

    first_ids = [item["item_id"] for item in first_manifest["items"]]
    second_ids = [item["item_id"] for item in second_manifest["items"]]
    assert first_ids == second_ids
    assert len(first_ids) == 2
    assert first_summary["exported_real_items"] == 1
    assert first_summary["exported_synthetic_items"] == 1
    first_benchmark_ids = [item["item_id"] for item in first_benchmark_manifest["items"]]
    omitted_benchmark_ids = {
        "nli_any_use_permitted:nli-ms-seed-006",
        "pinkas_open:pinkas-ledger-001",
        "project_synthetic:synthetic-0",
    } - set(first_benchmark_ids)
    assert set(first_benchmark_ids) == set(first_ids)
    assert f"- Items: {len(first_benchmark_ids)}" in first_benchmark_card
    assert all(item_id not in first_benchmark_card for item_id in omitted_benchmark_ids)


def test_select_alpha_items_caps_synthetic_to_twice_the_selected_real_items(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_fixture_config_root(tmp_path))
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    real_items = [
        _make_item(f"real:item-{index}", "train", str(asset_path)).model_copy(
            update={"source_id": "pinkas_open"}
        )
        for index in range(2)
    ]
    synthetic_items = [
        _make_item(f"synthetic:item-{index}", "train", str(asset_path)).model_copy(
            update={"source_id": "project_synthetic", "is_synthetic": True}
        )
        for index in range(5)
    ]

    selected = _select_alpha_items(
        real_items + synthetic_items,
        bundle.profiles["profile_open_v1"],
        AlphaExportConfig(version="alpha-v0", max_real_items=2, max_synthetic_items=10),
    )

    assert sum(1 for item in selected if not item.is_synthetic) == 2
    assert sum(1 for item in selected if item.is_synthetic) == 4


def test_select_alpha_items_rejects_negative_caps(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_fixture_config_root(tmp_path))
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    items = [_make_item("real:item-0", "train", str(asset_path))]

    with pytest.raises(StageExecutionError, match="max_real_items must be non-negative"):
        _select_alpha_items(
            items,
            bundle.profiles["profile_open_v1"],
            AlphaExportConfig(version="alpha-v0", max_real_items=-1, max_synthetic_items=1),
        )

    with pytest.raises(StageExecutionError, match="max_synthetic_items must be non-negative"):
        _select_alpha_items(
            items,
            bundle.profiles["profile_open_v1"],
            AlphaExportConfig(version="alpha-v0", max_real_items=1, max_synthetic_items=-1),
        )


def test_export_alpha_summary_marks_when_synthetic_cap_is_bound_by_real_items(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--max-real-items",
            "1",
            "--max-synthetic-items",
            "10",
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    release_summary = json.loads((export_dir / "manifests" / "release_summary.json").read_text(encoding="utf-8"))

    assert release_summary["exported_real_items"] == 1
    assert release_summary["exported_synthetic_items"] == 2
    assert release_summary["synthetic_clamped_to_real"] is True


@pytest.mark.parametrize("git_available", [True, False])
def test_export_alpha_docs_and_release_record_include_metadata(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch, git_available: bool
) -> None:
    config_root = _fixture_config_root(tmp_path)
    expected_commit = "deadbeef" * 5

    class FakeCompletedProcess:
        def __init__(self, returncode: int, stdout: str) -> None:
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(*args: object, **kwargs: object) -> FakeCompletedProcess:
        if git_available:
            return FakeCompletedProcess(0, f"{expected_commit}\n")
        return FakeCompletedProcess(1, "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    release_record = json.loads((export_dir / "manifests" / "release_record.json").read_text(encoding="utf-8"))
    release_summary = json.loads((export_dir / "manifests" / "release_summary.json").read_text(encoding="utf-8"))
    synthetic_composition = json.loads((export_dir / "manifests" / "synthetic_composition.json").read_text(encoding="utf-8"))
    annotation_manifest = json.loads((export_dir / "manifests" / "annotation_manifest.json").read_text(encoding="utf-8"))
    annotation_pilot_manifest = json.loads(
        (export_dir / "manifests" / "annotation_pilot_manifest.json").read_text(encoding="utf-8")
    )
    dataset_card = (export_dir / "docs" / "DATASET_CARD.md").read_text(encoding="utf-8")
    changelog = (export_dir / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = (export_dir / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    provenance = (export_dir / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")
    git_result = subprocess.run(["git", "rev-parse", "HEAD"])

    assert release_record["profile_id"] == "profile_open_v1"
    assert release_record["included_sources"] == ["nli_any_use_permitted", "pinkas_open", "project_synthetic"]
    assert release_summary["synthetic_composition"]["by_recipe_id"] == synthetic_composition["by_recipe_id"]
    assert release_summary["annotation_manifest"]["transcription_item_count"] == 0
    assert release_summary["annotation_pilot"]["pilot_item_count"] == 2
    assert release_summary["annotation_pilot"]["transcription_required_for_release"] is False
    assert annotation_pilot_manifest["layout_labels_required_for_release"] is False
    assert annotation_manifest["subset_id"] == "alpha_export"
    assert annotation_manifest["transcription_required"] is False
    assert annotation_manifest["layout_labels_required"] is False
    assert annotation_manifest["items"][0]["annotation_status"] == "not_available"
    assert synthetic_composition["by_template_id"] == {
        "handwritten_note": 1,
        "printed_letter": 1,
    }
    assert synthetic_composition["by_provider_version"] == {"fixture-f4c-v1": 2}
    assert synthetic_composition["by_layout_family"] == {
        "handwritten_note_marginalia": 1,
        "printed_letter_form": 1,
    }
    assert synthetic_composition["hebrew_coverage_counts"]["has_hebrew_letters"] == 2
    if git_result.returncode == 0:
        current_commit = git_result.stdout.strip()
        assert release_record["hocrgen_commit"] == current_commit
        assert f"`{current_commit}`" in provenance
    else:
        assert release_record["hocrgen_commit"] == "unknown"
    assert "# HeOCR alpha-v0" in dataset_card
    assert "# Changelog: alpha-v0" in changelog
    assert "Release Notes: alpha-v0" in release_notes
    assert "## Synthetic Composition" in dataset_card
    assert "## Annotation Readiness" in dataset_card
    assert "Items with transcription references: 0" in release_notes
    assert "Annotation pilot items: 2" in release_notes
    assert "`handwritten_note_marginalia_v1`=1" in release_notes
    exported_synthetic_items = [
        item
        for item in json.loads((export_dir / "manifests" / "item_manifest.json").read_text(encoding="utf-8"))["items"]
        if item["source_id"] == "project_synthetic"
    ]
    assert all("synthetic_available_template_ids" not in item["metadata"] for item in exported_synthetic_items)
    assert dataset_card.index("`nli_any_use_permitted`") < dataset_card.index("`pinkas_open`")
    assert dataset_card.index("`pinkas_open`") < dataset_card.index("`project_synthetic`")
    assert "`biblia_open`" not in dataset_card


def test_annotation_references_reject_nonportable_paths() -> None:
    rejected_paths = [
        "",
        "/tmp/transcription.json",
        "file:///tmp/transcription.json",
        "annotations/../../private.json",
        "../annotations/item-001/transcription.json",
        "../layouts/item-001/layout.json",
        "C:/Users/me/transcription.json",
        r"C:\Users\me\transcription.json",
        r"annotations\item-001\transcription.json",
        ".work/run/layout.json",
    ]
    for path in rejected_paths:
        with pytest.raises(ValueError, match="release-relative"):
            TranscriptionReference(path=path)

    assert TranscriptionReference(path="annotations/item-001/transcription.json").path == "annotations/item-001/transcription.json"


def test_annotation_manifest_items_reject_status_reference_contradictions() -> None:
    transcription = TranscriptionReference(path="annotations/item-001/transcription.json")

    with pytest.raises(ValueError, match="not_available"):
        AnnotationManifestItemRecord(
            item_id="item-001",
            source_id="fixture_source",
            annotation_status="not_available",
            transcription=transcription,
        )

    with pytest.raises(ValueError, match="requires at least one"):
        AnnotationManifestItemRecord(
            item_id="item-001",
            source_id="fixture_source",
            annotation_status="available",
        )

    item = AnnotationManifestItemRecord(
        item_id="item-001",
        source_id="fixture_source",
        annotation_status="available",
        transcription=transcription,
    )
    assert item.annotation_status == "available"


def test_annotation_manifest_builder_preserves_validated_status() -> None:
    transcription = TranscriptionReference(path="annotations/item-001/transcription.json")
    item = PrivacyScannedItemRecord.model_validate(
        {
            "annotation_status": "partial",
            "transcription": transcription.model_dump(mode="python"),
            "layout_labels": [],
            "item_id": "item-001",
            "candidate_id": "fixture_source:source-item-001",
            "source_id": "fixture_source",
            "source_item_id": "source-item-001",
            "source_url": "https://example.test/item-001",
            "discovery_method": "fixture",
            "raw_metadata": {},
            "asset_references": [],
            "metadata": {},
            "normalized_license": "PD-IL",
            "rights_classification": "open",
            "eligibility": "accepted",
            "eligibility_reason": "allowed_by_profile",
            "is_synthetic": False,
            "provenance": {},
            "acquired_assets": [],
            "normalized_assets": [],
            "qa_status": "passed",
            "qa_fail_reasons": [],
            "content_fingerprint": "fingerprint",
            "dedupe_status": "retained",
            "canonical_item_id": "item-001",
            "split": "train",
            "split_group_id": "group-001",
            "content_class": "printed",
            "content_confidence": 1.0,
            "period_class": "modern",
            "period_confidence": 1.0,
            "language_class": "hebrew_only",
            "language_confidence": 1.0,
            "quality_score": 1.0,
            "quality_tier": "high",
            "classification_review_reasons": [],
            "privacy_flag": "clear",
            "privacy_reasons": [],
            "privacy_decision": "release_ready",
        }
    )

    manifest = build_annotation_manifest([item], subset_id="fixture_subset")

    assert manifest.items[0].annotation_status == "partial"
    assert manifest.annotated_item_count == 1
    assert manifest.transcription_item_count == 1


def test_annotation_manifest_builder_derives_status_when_missing() -> None:
    transcription = TranscriptionReference(path="annotations/item-001/transcription.json")
    item = Namespace(
        item_id="item-001",
        source_id="fixture_source",
        split="train",
        transcription=transcription,
        layout_labels=[],
    )

    manifest = build_annotation_manifest([item], subset_id="fixture_subset")

    assert manifest.items[0].annotation_status == "available"
    assert manifest.annotated_item_count == 1
    assert manifest.transcription_item_count == 1


def test_export_alpha_auto_discovers_previous_sibling_release(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    releases_root = tmp_path / "HeOCR" / "releases"
    baseline_dir = releases_root / "alpha-v0"
    invalid_dir = releases_root / "notes"
    invalid_dir.mkdir(parents=True)

    first_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work1"),
            "--output-dir",
            str(baseline_dir),
        ]
    )
    assert first_exit == 0
    _ = capsys.readouterr().out

    second_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work2"),
            "--version",
            "alpha-v1",
            "--output-dir",
            str(releases_root / "alpha-v1"),
        ]
    )
    assert second_exit == 0
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    release_diff = json.loads((export_dir / "manifests" / "release_diff.json").read_text(encoding="utf-8"))
    release_notes = (export_dir / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert release_diff["previous_version"] == "alpha-v0"
    assert release_diff["counts"]["unchanged"] == 4
    assert "Compared to `alpha-v0`" in release_notes


def test_export_alpha_compare_to_override_reports_selection_limit_removed(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    releases_root = tmp_path / "HeOCR" / "releases"
    baseline_dir = releases_root / "alpha-v0"

    first_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work1"),
            "--output-dir",
            str(baseline_dir),
        ]
    )
    assert first_exit == 0
    _ = capsys.readouterr().out

    second_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work2"),
            "--version",
            "alpha-v1",
            "--output-dir",
            str(releases_root / "alpha-v1"),
            "--compare-to",
            str(baseline_dir),
            "--max-real-items",
            "1",
            "--max-synthetic-items",
            "1",
        ]
    )
    assert second_exit == 0
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    release_diff = json.loads((export_dir / "manifests" / "release_diff.json").read_text(encoding="utf-8"))
    changelog = (export_dir / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    assert release_diff["previous_version"] == "alpha-v0"
    assert release_diff["counts"]["removed"] == 2
    assert release_diff["counts"]["unchanged"] == 2
    assert release_diff["removed_items"] == [
        {
            "item_id": "pinkas_open:pinkas-ledger-001",
            "previous_split": "train",
            "reason": "selection_limit_excluded",
            "source_id": "pinkas_open",
        },
        {
            "item_id": "project_synthetic:synthetic-1",
            "previous_split": "train",
            "reason": "selection_limit_excluded",
            "source_id": "project_synthetic",
        },
    ]
    assert "`selection_limit_excluded`" in changelog


def test_resolve_comparison_release_rejects_current_export_dir_compare_to(tmp_path: Path) -> None:
    export_dir = tmp_path / "exports" / "alpha-v1"
    export_dir.mkdir(parents=True)

    with pytest.raises(StageExecutionError, match="--compare-to cannot point to the current export directory"):
        _resolve_comparison_release(
            export_dir,
            AlphaExportConfig(version="alpha-v1", output_dir=export_dir, compare_to=export_dir),
        )


def test_resolve_comparison_release_returns_none_when_sibling_root_missing(tmp_path: Path) -> None:
    export_dir = tmp_path / "missing-root" / "alpha-v1"
    result = _resolve_comparison_release(export_dir, AlphaExportConfig(version="alpha-v1", output_dir=export_dir))
    assert result is None


def test_resolve_comparison_release_ignores_non_directories_and_same_version(tmp_path: Path) -> None:
    sibling_root = tmp_path / "exports"
    export_dir = sibling_root / "alpha-v2"
    export_dir.mkdir(parents=True)
    (sibling_root / "random.txt").write_text("ignore", encoding="utf-8")
    same_version_dir = sibling_root / "alpha-v2-copy"
    same_version_dir.mkdir()
    _write_baseline_release(same_version_dir, "alpha-v1", [])

    selected = _resolve_comparison_release(export_dir, AlphaExportConfig(version="alpha-v2-copy", output_dir=export_dir))
    assert selected is None


def test_resolve_comparison_release_skips_candidates_with_matching_release_record_version(tmp_path: Path) -> None:
    sibling_root = tmp_path / "exports"
    export_dir = sibling_root / "alpha-v1"
    export_dir.mkdir(parents=True)
    same_version_dir = sibling_root / "renamed-baseline"
    _write_baseline_release(same_version_dir, "alpha-v1", [])

    selected = _resolve_comparison_release(export_dir, AlphaExportConfig(version="alpha-v1", output_dir=export_dir))
    assert selected is None


def test_validate_release_diff_baseline_rejects_non_file_manifests(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    manifests_dir = baseline_dir / "manifests"
    (manifests_dir / "release_record.json").mkdir(parents=True)
    (manifests_dir / "item_manifest.json").write_text("{}", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="missing required manifests"):
        _resolve_comparison_release(
            tmp_path / "exports" / "alpha-v1",
            AlphaExportConfig(version="alpha-v1", compare_to=baseline_dir),
        )


def test_validate_release_diff_baseline_rejects_missing_compare_to_path(tmp_path: Path) -> None:
    missing = tmp_path / "missing-baseline"
    with pytest.raises(StageExecutionError, match="does not exist"):
        _resolve_comparison_release(
            tmp_path / "exports" / "alpha-v1",
            AlphaExportConfig(version="alpha-v1", compare_to=missing),
        )


def test_validate_release_diff_baseline_rejects_non_directory_compare_to_path(tmp_path: Path) -> None:
    baseline_file = tmp_path / "baseline-file"
    baseline_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="is not a directory"):
        _resolve_comparison_release(
            tmp_path / "exports" / "alpha-v1",
            AlphaExportConfig(version="alpha-v1", compare_to=baseline_file),
        )


def test_validate_release_diff_baseline_rejects_invalid_json_manifest(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    manifests_dir = baseline_dir / "manifests"
    manifests_dir.mkdir(parents=True)
    (manifests_dir / "release_record.json").write_text("{not-json", encoding="utf-8")
    (manifests_dir / "item_manifest.json").write_text("{\"items\": []}", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="has invalid JSON"):
        _resolve_comparison_release(
            tmp_path / "exports" / "alpha-v1",
            AlphaExportConfig(version="alpha-v1", compare_to=baseline_dir),
        )


def test_parse_exported_at_normalizes_naive_and_zulu_timestamps() -> None:
    naive = _parse_exported_at("2026-04-21T10:00:00")
    zulu = _parse_exported_at("2026-04-21T10:00:00Z")

    assert naive is not None
    assert naive.tzinfo == UTC
    assert naive.isoformat() == "2026-04-21T10:00:00+00:00"
    assert zulu is not None
    assert zulu.tzinfo == UTC


def test_parse_exported_at_returns_none_for_non_string_and_invalid_values() -> None:
    assert _parse_exported_at(None) is None
    assert _parse_exported_at("not-a-timestamp") is None


@pytest.mark.parametrize(
    ("payload", "expected_error"),
    [
        (["not-an-object"], "must be a JSON object with a list 'items'"),
        ({"items": "not-a-list"}, "must contain a list 'items'"),
        ({"items": ["not-an-object"]}, "must contain only object entries with 'item_id'"),
        ({"items": [{}]}, "must contain only object entries with 'item_id'"),
    ],
)
def test_load_baseline_item_manifest_validates_manifest_shape(tmp_path: Path, payload: object, expected_error: str) -> None:
    manifest_path = tmp_path / "item_manifest.json"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(StageExecutionError, match=expected_error):
        _load_baseline_item_manifest(manifest_path)


def test_export_alpha_fails_when_output_dir_exists_without_overwrite(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "HeOCR" / "releases" / "alpha-v0"
    stale_file = output_dir / "stale.txt"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(output_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["error"] == f"alpha export directory already exists: {output_dir.resolve()}"
    assert stale_file.exists()


def test_export_alpha_overwrites_existing_output_dir_when_requested(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "HeOCR" / "releases" / "alpha-v0"
    stale_file = output_dir / "stale.txt"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(output_dir),
            "--overwrite",
        ]
    )
    assert exit_code == 0
    assert not stale_file.exists()


def test_export_alpha_succeeds_when_removed_duplicate_items_are_curated_records(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    fixture_seed = (Path(__file__).parent / "fixtures" / "nli" / "seeds_default.yaml").resolve()
    duplicate_records_path = tmp_path / "duplicate_biblia_records.json"
    duplicate_records_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "id": "biblia-duplicate-001",
                        "title": "BiblIA duplicate fixture",
                        "source_url": "https://example.org/biblia/duplicate-1",
                        "upstream_identifier": "duplicate-1",
                        "collection": "BiblIA Open Packaged Subset",
                        "period": "historical",
                        "raw_rights": "PD-IL",
                        "asset_path": "package://data/hocrsyngen/contracts/generation_manifest_v1/fixture-batch/assets/hocrsyngen-s00000017-000001/page_0001.jpg",
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    expansion_manifest_path = tmp_path / "duplicate_biblia_source_depth_expansion.yaml"
    expansion_manifest_path.write_text(
        f"""version: 1
source_id: biblia_open
planning_notation: F1b2
target_count: 26
expansion_mode: operator_packaged_records
records_path: {duplicate_records_path}
asset_root: package://data/hocrsyngen/contracts/generation_manifest_v1/fixture-batch/assets/hocrsyngen-s00000017-000001/
required_record_fields:
  - id
  - title
  - source_url
  - upstream_identifier
  - collection
  - period
  - raw_rights
  - asset_path
allowed_raw_rights:
  - PD-IL
allowed_normalized_licenses:
  - PD-IL
required_gates:
  - rights
  - privacy
  - review
  - dedupe
  - split
  - benchmark
  - synthetic-cap
  - export-portability
review_requirements:
  - Test duplicate records remain explicit operator fixtures.
  - Test duplicate records carry stable provenance and PD-IL rights.
  - Test duplicate assets remain under the declared fixture root.
non_goals:
  - broad live-source crawling
  - public beta export
  - release-candidate export
  - publication
  - network-dependent CI
""",
        encoding="utf-8",
    )
    sources_path = config_root / "sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace(
            "package://data/biblia/records.json", str(duplicate_records_path)
        ).replace(
            "package://data/biblia/source_depth_expansion.yaml", str(expansion_manifest_path)
        ).replace(
            "package://data/nli/seeds.yaml", str(fixture_seed)
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "HeOCR" / "releases" / "alpha-v0"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert (Path(payload["export_dir"]) / "manifests" / "release_diff.json").exists()


def test_export_alpha_skips_auto_discovered_siblings_with_invalid_release_record_json(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    releases_root = tmp_path / "HeOCR" / "releases"
    invalid_baseline = releases_root / "broken-release"
    invalid_manifests = invalid_baseline / "manifests"
    invalid_manifests.mkdir(parents=True)
    (invalid_manifests / "release_record.json").write_text("{not-json", encoding="utf-8")
    (invalid_manifests / "item_manifest.json").write_text("{\"items\": []}", encoding="utf-8")

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--version",
            "alpha-v1",
            "--output-dir",
            str(releases_root / "alpha-v1"),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    release_diff = json.loads((Path(payload["export_dir"]) / "manifests" / "release_diff.json").read_text(encoding="utf-8"))
    assert release_diff["previous_version"] is None


def test_export_alpha_rejects_conflicting_handoff_targets(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    heocr_repo = tmp_path / "HeOCR"
    (heocr_repo / ".git").mkdir(parents=True)
    output_dir = heocr_repo / "releases" / "alpha-v0"

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(output_dir),
            "--heocr-repo",
            str(heocr_repo),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["error"] == "--output-dir and --heocr-repo cannot be used together"


@pytest.mark.parametrize(
    ("target_factory", "expected_error"),
    [
        (lambda tmp_path: tmp_path, "alpha export overwrite target must end with alpha-v0"),
        (lambda tmp_path: REPO_ROOT, "refusing to overwrite unsafe export target"),
        (lambda tmp_path: tmp_path / "HeOCR" / "releases", "alpha export overwrite target must end with alpha-v0"),
    ],
)
def test_export_alpha_rejects_unsafe_overwrite_targets(tmp_path: Path, capsys, target_factory, expected_error: str) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = target_factory(tmp_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(output_dir),
            "--overwrite",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert expected_error in payload["error"]


def test_export_alpha_handles_cli_error_paths(monkeypatch, tmp_path: Path, capsys) -> None:
    args = Namespace(
        profile="profile_open_v1",
        workdir=tmp_path / "work",
        config_root=tmp_path / "missing-config",
        dry_run=True,
        source=None,
        max_items=None,
        seed=None,
        verbose=False,
        version="alpha-v0",
        output_dir=None,
        heocr_repo=None,
        overwrite=False,
        max_real_items=10,
        max_synthetic_items=2,
    )

    def raise_config(_: Path | None) -> None:
        raise ConfigValidationError("broken config")

    monkeypatch.setattr("hocrgen.cli._load_bundle", raise_config)
    exit_code = handle_export_alpha(args)
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["error"] == "broken config"


def test_export_alpha_rejects_negative_caps(capsys, tmp_path: Path) -> None:
    config_root = _fixture_config_root(tmp_path)

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--max-synthetic-items",
            "-1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "max_synthetic_items must be non-negative"

    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work2"),
            "--max-real-items",
            "-1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "max_real_items must be non-negative"


def test_export_alpha_handles_unknown_profile(capsys, tmp_path: Path) -> None:
    exit_code = main(["export-alpha", "--profile", "missing_profile", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert payload["error"] == "unknown profile: missing_profile"


def test_export_alpha_handles_stage_execution_error(monkeypatch, tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    def raise_stage(*args, **kwargs):
        raise StageExecutionError("empty export")

    monkeypatch.setattr("hocrgen.cli.export_alpha_release", raise_stage)
    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["error"] == "empty export"


def test_export_alpha_handles_upstream_pipeline_stage_error(monkeypatch, tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    def raise_stage(*args, **kwargs):
        raise StageExecutionError("build failed")

    monkeypatch.setattr("hocrgen.cli.execute_pipeline", raise_stage)
    exit_code = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["error"] == "build failed"


def test_select_alpha_items_can_return_empty_when_real_cap_is_zero(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    release_items = [
        PrivacyScannedItemRecord.model_validate(item)
        for item in json.loads((run_dir / "build_release" / "item_manifest.json").read_text(encoding="utf-8"))["items"]
    ]
    bundle_root = _fixture_config_root(tmp_path / "other")
    bundle = load_and_validate_bundle(bundle_root)
    selected = _select_alpha_items(release_items, bundle.profiles["profile_open_v1"], AlphaExportConfig(version="alpha-v0", max_real_items=0, max_synthetic_items=2))
    assert selected == []


def test_export_alpha_release_raises_on_empty_selection(monkeypatch, tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    bundle = load_and_validate_bundle(config_root)

    monkeypatch.setattr("hocrgen.package.alpha._select_alpha_items", lambda *args, **kwargs: [])
    with pytest.raises(StageExecutionError, match="alpha export selection is empty"):
        export_alpha_release(bundle, run_dir, "profile_open_v1", AlphaExportConfig(version="alpha-v0"))


def test_export_alpha_release_blocks_benchmark_holdout_leakage(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    build_dir = run_dir / "build_release"
    release_summary_path = build_dir / "release_summary.json"
    release_summary = json.loads(release_summary_path.read_text(encoding="utf-8"))
    release_summary["benchmark_holdout_leakage_status"] = "blocked"
    release_summary_path.write_text(json.dumps(release_summary), encoding="utf-8")
    (build_dir / "benchmark_leakage_risk.json").write_text(
        json.dumps(
            {
                "enforcement_context": "build_release",
                "risk_count": 1,
                "status": "blocked",
                "unresolved_count": 1,
                "unresolved_risks": [],
            }
        ),
        encoding="utf-8",
    )
    bundle = load_and_validate_bundle(config_root)

    with pytest.raises(StageExecutionError, match="alpha export is blocked"):
        export_alpha_release(bundle, run_dir, "profile_open_v1", AlphaExportConfig(version="alpha-v0"))


def test_export_alpha_scopes_benchmark_leakage_artifact_to_selected_items(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "HeOCR" / "releases" / "alpha-v0"
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    (run_dir / "build_release" / "benchmark_leakage_risk.json").write_text(
        json.dumps(
            {
                "accepted_resolution_count": 1,
                "enforcement_context": "build_release",
                "risk_count": 1,
                "risks": [
                    {
                        "benchmark_item_ids": ["fixture:benchmark"],
                        "group_id": "source-group:outside",
                        "group_kind": "source_group",
                        "holdout_item_ids": ["fixture:holdout"],
                        "non_benchmark_item_ids": ["fixture:holdout"],
                        "resolution_status": "accepted",
                    }
                ],
                "resolved_risks": [
                    {
                        "benchmark_item_ids": ["fixture:benchmark"],
                        "group_id": "source-group:outside",
                        "group_kind": "source_group",
                        "holdout_item_ids": ["fixture:holdout"],
                        "non_benchmark_item_ids": ["fixture:holdout"],
                        "resolution_status": "accepted",
                    }
                ],
                "stale_resolutions": [],
                "status": "ok",
                "unresolved_count": 0,
                "unresolved_risks": [],
                "unused_resolutions": [],
            }
        ),
        encoding="utf-8",
    )
    bundle = load_and_validate_bundle(config_root)

    export_alpha_release(
        bundle,
        run_dir,
        "profile_open_v1",
        AlphaExportConfig(version="alpha-v0", output_dir=output_dir),
    )
    leakage_risk = json.loads((output_dir / "manifests" / "benchmark_leakage_risk.json").read_text(encoding="utf-8"))

    assert leakage_risk["export_scope"] == "selected_alpha_items"
    assert leakage_risk["risk_count"] == 0
    assert leakage_risk["resolved_risks"] == []


def test_export_alpha_release_requires_benchmark_artifacts(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    (run_dir / "build_release" / "benchmark_manifest.json").unlink()
    bundle = load_and_validate_bundle(config_root)

    with pytest.raises(StageExecutionError, match="requires build-release benchmark artifacts"):
        export_alpha_release(bundle, run_dir, "profile_open_v1", AlphaExportConfig(version="alpha-v0"))


@pytest.mark.parametrize(
    "artifact_name",
    [
        "annotation_pilot_manifest.json",
        "annotation_pilot_selection_audit.json",
    ],
)
def test_export_alpha_release_requires_annotation_pilot_artifacts(
    tmp_path: Path,
    capsys,
    artifact_name: str,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    (run_dir / "build_release" / artifact_name).unlink()
    bundle = load_and_validate_bundle(config_root)

    with pytest.raises(StageExecutionError, match="requires build-release annotation pilot artifacts"):
        export_alpha_release(bundle, run_dir, "profile_open_v1", AlphaExportConfig(version="alpha-v0"))


def test_export_alpha_release_validates_benchmark_artifacts_before_overwrite(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    (run_dir / "build_release" / "benchmark_manifest.json").unlink()
    output_dir = tmp_path / "HeOCR" / "releases" / "alpha-v0"
    stale_file = output_dir / "stale.txt"
    stale_file.parent.mkdir(parents=True, exist_ok=True)
    stale_file.write_text("stale", encoding="utf-8")
    bundle = load_and_validate_bundle(config_root)

    with pytest.raises(StageExecutionError, match="requires build-release benchmark artifacts"):
        export_alpha_release(
            bundle,
            run_dir,
            "profile_open_v1",
            AlphaExportConfig(version="alpha-v0", output_dir=output_dir, overwrite=True),
        )
    assert stale_file.read_text(encoding="utf-8") == "stale"


def test_benchmark_card_for_export_rejects_invalid_policy() -> None:
    inputs = BenchmarkExportInputs(
        items=[],
        selection_audit=[],
        stability_policy={"benchmark_id": "benchmark_v1"},
        card_markdown="",
    )

    with pytest.raises(StageExecutionError, match="benchmark policy is invalid"):
        _benchmark_card_for_export(inputs, [])


def test_copy_export_assets_requires_split_and_copies_preview(tmp_path: Path) -> None:
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    preview_path = tmp_path / "preview.svg"
    preview_path.write_text("<svg/>", encoding="utf-8")
    item = _make_item(
        item_id="test:item-001",
        split="train",
        normalized_asset_path=str(asset_path),
        preview_path=str(preview_path),
        preview_generated=True,
    )
    exported = _copy_export_assets([item], tmp_path / "export-data")
    assert exported[0].exported_assets[0].release_preview_path is not None
    assert (tmp_path / "export-data" / "train" / "test:item-001" / "previews" / "preview.svg").exists()

    missing_split_item = _make_item(
        item_id="test:item-002",
        split=None,
        normalized_asset_path=str(asset_path),
    )
    with pytest.raises(StageExecutionError, match="release-ready item test:item-002 is missing a split assignment"):
        _copy_export_assets([missing_split_item], tmp_path / "other-export")


def test_build_source_stats_skips_unsplit_items(tmp_path: Path) -> None:
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    split_item = AlphaExportedItemRecord.model_validate(
        _make_item("split:item", "validation", str(asset_path)).model_dump(mode="python") | {"exported_assets": []}
    )
    unsplit_item = AlphaExportedItemRecord.model_validate(
        _make_item("unsplit:item", None, str(asset_path)).model_dump(mode="python") | {"exported_assets": []}
    )
    stats = _build_source_stats([split_item, unsplit_item], [])
    assert stats["sources"]["test_source"] == 2
    assert stats["sources_by_split"]["test_source"] == {"validation": 1}


def test_alpha_helper_fallbacks(monkeypatch) -> None:
    class DummyProfile:
        include_sources = ["known_source"]

    assert _source_priority(DummyProfile(), "missing_source") == 1
    assert _split_sort_key(None) == 3

    class DummyResult:
        returncode = 1
        stdout = ""

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: DummyResult())
    assert _current_commit_sha() == "unknown"

    def raise_oserror(*args, **kwargs):
        raise FileNotFoundError("git not found")

    monkeypatch.setattr("subprocess.run", raise_oserror)
    assert _current_commit_sha() == "unknown"


def test_validate_heocr_repo_root_requires_git_checkout(tmp_path: Path) -> None:
    missing_repo = tmp_path / "missing-HeOCR"
    with pytest.raises(StageExecutionError, match=f"HeOCR repo path does not exist: {missing_repo.resolve()}"):
        _validate_heocr_repo_root(missing_repo)

    file_path = tmp_path / "HeOCR.txt"
    file_path.write_text("not a repo", encoding="utf-8")
    with pytest.raises(StageExecutionError, match=f"HeOCR repo path is not a directory: {file_path.resolve()}"):
        _validate_heocr_repo_root(file_path)

    repo_root = tmp_path / "HeOCR"
    repo_root.mkdir()

    with pytest.raises(StageExecutionError, match="HeOCR repo path is not a git checkout"):
        _validate_heocr_repo_root(repo_root)

    (repo_root / ".git").mkdir()
    assert _validate_heocr_repo_root(repo_root) == repo_root.resolve()


def test_public_item_payload_excludes_local_paths(tmp_path: Path) -> None:
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    item = AlphaExportedItemRecord.model_validate(
        (
            _make_item("payload:item", "train", str(asset_path)).model_dump(mode="python")
            | {
                "metadata": {
                    "display_label": "keep me",
                    "seed_manifest": "/Users/example/project/src/hocrgen/data/nli/seeds.yaml",
                }
            }
        )
        | {
            "exported_assets": [
                {
                    "release_asset_path": "data/train/payload:item/asset.svg",
                    "media_type": "image/svg+xml",
                    "asset_format": "svg",
                    "release_preview_path": None,
                }
            ]
        }
    )
    payload = _public_item_payload(item)
    assert "normalized_assets" not in payload
    assert "asset_references" not in payload
    assert "acquired_assets" not in payload
    assert payload["metadata"] == {"display_label": "keep me"}
    assert payload["exported_assets"][0] == {
        "release_asset_path": "data/train/payload:item/asset.svg",
        "media_type": "image/svg+xml",
        "asset_format": "svg",
        "release_preview_path": None,
    }


def test_public_item_payload_raises_if_sanitizer_does_not_return_object(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    item = AlphaExportedItemRecord.model_validate(
        _make_item("payload:item", "train", str(asset_path)).model_dump(mode="python")
        | {"exported_assets": []}
    )
    monkeypatch.setattr("hocrgen.package.alpha._sanitize_portable_value", lambda value: "not-a-dict")
    with pytest.raises(StageExecutionError, match="public item payload must serialize to an object"):
        _public_item_payload(item)


def test_sanitize_portable_value_omits_local_paths_from_lists() -> None:
    assert _sanitize_portable_value(
        [
            "keep me",
            "/tmp/local-file",
            r"C:\Users\shay\artifact.json",
            r"\\server\share\artifact.json",
            r"relative\.work\cache",
            "file:///Users/shay/file.txt",
        ]
    ) == ["keep me"]


def test_audit_item_payload_excludes_local_paths_and_raw_metadata(tmp_path: Path) -> None:
    asset_path = tmp_path / "asset.svg"
    asset_path.write_text("<svg/>", encoding="utf-8")
    payload = _audit_item_payload(_make_item("audit:item", None, str(asset_path)))
    assert payload["item_id"] == "audit:item"
    assert payload["source_id"] == "test_source"
    assert "raw_metadata" not in payload
    assert "fixture_path" not in payload
    assert "normalized_assets" not in payload


def test_review_queue_payload_rewrites_preview_paths_into_export_tree(tmp_path: Path) -> None:
    preview_path = tmp_path / "preview.svg"
    preview_path.write_text("<svg/>", encoding="utf-8")
    payload = _review_queue_payload(
        ReviewQueueRecord.model_validate(
            {
            "review_item_id": "review:test:item/001",
            "item_id": "test:item/001",
            "source_id": "test_source",
            "canonical_item_id": "test:item/001",
            "split_group_id_pre_review": "group:test:item/001",
            "review_reasons": ["privacy:metadata_signal"],
            "suggested_decision": "needs_privacy_review",
            "privacy_flag": "needs_review",
            "classification_summary": {},
            "preview_paths": [str(preview_path)],
            "source_url": "https://example.org/test:item/001",
            "title": "test:item/001",
            }
        ),
        tmp_path / "export",
    )
    assert payload["preview_paths"] == ["manifests/review_previews/test__item_001/01_preview.svg"]
    assert (tmp_path / "export" / payload["preview_paths"][0]).exists()


def test_review_queue_payload_skips_missing_preview_paths(tmp_path: Path) -> None:
    payload = _review_queue_payload(
        ReviewQueueRecord.model_validate(
            {
            "review_item_id": "review:test:item-002",
            "item_id": "test:item-002",
            "source_id": "test_source",
            "canonical_item_id": "test:item-002",
            "split_group_id_pre_review": "group:test:item-002",
            "review_reasons": ["policy:review_only_source"],
            "suggested_decision": "needs_policy_review",
            "privacy_flag": "clear",
            "classification_summary": {},
            "preview_paths": [str(tmp_path / "missing.svg")],
            "source_url": "https://example.org/test:item-002",
            "title": "test:item-002",
            }
        ),
        tmp_path / "export",
    )
    assert payload["preview_paths"] == []


def test_copy_review_previews_rejects_targets_outside_export_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    preview_path_ok = tmp_path / "preview_ok.svg"
    preview_path_ok.write_text("<svg/>", encoding="utf-8")
    preview_path_escape = tmp_path / "preview.svg"
    preview_path_escape.write_text("<svg/>", encoding="utf-8")
    review_item = ReviewQueueRecord.model_validate(
        {
            "review_item_id": "review:test:item-003",
            "item_id": "test:item-003",
            "source_id": "test_source",
            "canonical_item_id": "test:item-003",
            "split_group_id_pre_review": "group:test:item-003",
            "review_reasons": ["privacy:metadata_signal"],
            "suggested_decision": "needs_privacy_review",
            "privacy_flag": "needs_review",
            "classification_summary": {},
            "preview_paths": [str(preview_path_ok), str(preview_path_escape)],
            "source_url": "https://example.org/test:item-003",
            "title": "test:item-003",
        }
    )

    original_relative_to = Path.relative_to

    def fake_relative_to(self: Path, *other: Path) -> Path:
        if self.name == "02_preview.svg":
            raise ValueError("escape")
        return original_relative_to(self, *other)

    monkeypatch.setattr(Path, "relative_to", fake_relative_to)

    with pytest.raises(StageExecutionError, match="review preview target escapes export dir"):
        _copy_review_previews(review_item, tmp_path / "export")


def test_validate_overwrite_target_rejects_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "alpha-v0"
    target.write_text("not a directory", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="overwrite target is not a directory"):
        _validate_overwrite_target(target, "alpha-v0")


def test_validate_overwrite_target_rejects_shallow_paths() -> None:
    with pytest.raises(StageExecutionError, match="refusing to overwrite unsafe export target"):
        _validate_overwrite_target(Path("/tmp"), "tmp")


def test_build_release_diff_classifies_changed_items_and_removed_reasons(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    item_dir = tmp_path / "assets"
    item_dir.mkdir()

    unchanged = _make_exported_item("same:item", "train", item_dir / "same.svg", source_id="same_source")
    metadata_before = _make_exported_item("meta:item", "train", item_dir / "meta.svg", source_id="meta_source", title="before")
    metadata_after = metadata_before.model_copy(update={"title": "after"})
    asset_before = _make_exported_item("asset:item", "train", item_dir / "asset_before.svg", source_id="asset_source")
    asset_after = AlphaExportedItemRecord.model_validate(
        asset_before.model_dump(mode="python")
        | {
            "exported_assets": [
                {
                    "release_asset_path": "data/train/asset:item/asset_after.svg",
                    "media_type": "image/svg+xml",
                    "asset_format": "svg",
                    "release_preview_path": None,
                }
            ]
        }
    )
    split_before = _make_exported_item("split:item", "train", item_dir / "split.svg", source_id="split_source")
    split_after = split_before.model_copy(update={"split": "validation"})
    removed_review = _make_exported_item("removed:review", "train", item_dir / "removed_review.svg", source_id="review_source")
    removed_blocked = _make_exported_item("removed:blocked", "train", item_dir / "removed_blocked.svg", source_id="blocked_source")
    removed_duplicate = _make_exported_item("removed:duplicate", "train", item_dir / "removed_duplicate.svg", source_id="duplicate_source")
    removed_missing = _make_exported_item("removed:missing", "train", item_dir / "removed_missing.svg", source_id="missing_source")

    _write_baseline_release(
        baseline_dir,
        "alpha-v0",
        [
            unchanged,
            metadata_before,
            asset_before,
            split_before,
            removed_review,
            removed_blocked,
            removed_duplicate,
            removed_missing,
        ],
    )

    release_ready_selection = _make_item("removed:selection", "train", str(item_dir / "selection.svg")).model_copy(
        update={"source_id": "selection_source"}
    )
    diff = _build_release_diff(
        version="alpha-v1",
        generated_at="2026-04-21T10:00:00+00:00",
        current_items=[unchanged, metadata_after, asset_after, split_after],
        baseline_dir=baseline_dir,
        review_required_items=[_make_item("removed:review", "train", str(item_dir / "removed_review.svg")).model_copy(update={"source_id": "review_source"})],
        blocked_items=[_make_item("removed:blocked", "train", str(item_dir / "removed_blocked.svg")).model_copy(update={"source_id": "blocked_source"})],
        removed_duplicate_items=[_make_item("removed:duplicate", "train", str(item_dir / "removed_duplicate.svg")).model_copy(update={"source_id": "duplicate_source"})],
        build_release_items=[metadata_after, asset_after, split_after, unchanged, release_ready_selection],
    )

    assert diff.previous_version == "alpha-v0"
    assert diff.counts == {"added": 0, "removed": 4, "changed": 3, "unchanged": 1}
    assert {item.item_id: item.change_types for item in diff.changed_items} == {
        "asset:item": ["assets"],
        "meta:item": ["metadata"],
        "split:item": ["split"],
    }
    assert {item.item_id: item.reason for item in diff.removed_items} == {
        "removed:blocked": "blocked",
        "removed:duplicate": "duplicate_removed",
        "removed:missing": "missing_from_current_run",
        "removed:review": "review_required",
    }


def test_changelog_groups_changed_items_and_renders_removal_reasons(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    item_dir = tmp_path / "assets"
    item_dir.mkdir()
    before = _make_exported_item("doc:item", "train", item_dir / "before.svg", source_id="test_source", title="before")
    after = AlphaExportedItemRecord.model_validate(
        before.model_dump(mode="python")
        | {
            "title": "after",
            "split": "validation",
            "exported_assets": [
                {
                    "release_asset_path": "data/validation/doc:item/after.svg",
                    "media_type": "image/svg+xml",
                    "asset_format": "svg",
                    "release_preview_path": None,
                }
            ],
        }
    )
    removed = _make_exported_item("gone:item", "test", item_dir / "gone.svg", source_id="test_source")
    _write_baseline_release(baseline_dir, "alpha-v0", [before, removed])

    diff = _build_release_diff(
        version="alpha-v1",
        generated_at="2026-04-21T10:00:00+00:00",
        current_items=[after],
        baseline_dir=baseline_dir,
        review_required_items=[],
        blocked_items=[],
        removed_duplicate_items=[],
        build_release_items=[after],
    )
    changelog = _changelog_doc("alpha-v1", diff)

    assert "### Metadata Changes" in changelog
    assert "### Asset Changes" in changelog
    assert "### Split Assignment Changes" in changelog
    assert "`missing_from_current_run`" in changelog


def test_changelog_renders_none_for_empty_sections_and_skips_unmatched_change_types() -> None:
    diff = _build_release_diff(
        version="alpha-v1",
        generated_at="2026-04-21T10:00:00+00:00",
        current_items=[],
        baseline_dir=None,
        review_required_items=[],
        blocked_items=[],
        removed_duplicate_items=[],
        build_release_items=[],
    )

    changelog = _changelog_doc("alpha-v1", diff)

    assert "## Source Deltas\n- None" in changelog
    assert "## Split Deltas\n- None" in changelog
    assert "## Added Items\n- None" in changelog
    assert "## Removed Items\n- None" in changelog
    assert "## Changed Items\n- None" in changelog
    assert "### Metadata Changes" not in changelog


def test_changelog_renders_unknown_for_null_added_item_split(tmp_path: Path) -> None:
    diff = _build_release_diff(
        version="alpha-v1",
        generated_at="2026-04-21T10:00:00+00:00",
        current_items=[_make_exported_item("doc:item", "train", tmp_path / "alpha_doc.svg").model_copy(update={"split": None})],
        baseline_dir=None,
        review_required_items=[],
        blocked_items=[],
        removed_duplicate_items=[],
        build_release_items=[],
    )

    changelog = _changelog_doc("alpha-v1", diff)

    assert "`unknown`" in changelog


def test_changelog_skips_unmatched_change_type_sections(tmp_path: Path) -> None:
    baseline_dir = tmp_path / "baseline"
    item_dir = tmp_path / "assets"
    item_dir.mkdir()
    before = _make_exported_item("doc:item", "train", item_dir / "before.svg", source_id="test_source", title="before")
    after = before.model_copy(update={"title": "after"})
    _write_baseline_release(baseline_dir, "alpha-v0", [before])

    diff = _build_release_diff(
        version="alpha-v1",
        generated_at="2026-04-21T10:00:00+00:00",
        current_items=[after],
        baseline_dir=baseline_dir,
        review_required_items=[],
        blocked_items=[],
        removed_duplicate_items=[],
        build_release_items=[after],
    )
    changelog = _changelog_doc("alpha-v1", diff)

    assert "### Metadata Changes" in changelog
    assert "### Asset Changes" not in changelog
    assert "### Split Assignment Changes" not in changelog


def test_handoff_doc_falls_back_to_default_release_dir_when_export_not_under_repo(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_fixture_config_root(tmp_path))
    handoff = _handoff_doc(
        "alpha-v1",
        tmp_path / "external" / "alpha-v1",
        bundle.profiles["profile_open_v1"],
        {
            "exported_item_count": 1,
            "exported_real_items": 1,
            "exported_synthetic_items": 0,
            "review_required_count": 0,
            "blocked_count": 0,
        },
        ["nli_any_use_permitted"],
        "deadbeef",
        tmp_path / "HeOCR",
    )

    assert "- Target release dir: `releases/alpha-v1/`" in handoff


def _make_exported_item(
    item_id: str,
    split: str,
    normalized_asset_path: Path,
    *,
    source_id: str = "test_source",
    title: str | None = None,
) -> AlphaExportedItemRecord:
    normalized_asset_path.write_text("<svg/>", encoding="utf-8")
    item = _make_item(item_id, split, str(normalized_asset_path)).model_copy(
        update={"source_id": source_id, "title": title or item_id}
    )
    return AlphaExportedItemRecord.model_validate(
        item.model_dump(mode="python")
        | {
            "exported_assets": [
                {
                    "release_asset_path": f"data/{split}/{item_id}/{normalized_asset_path.name}",
                    "media_type": "image/svg+xml",
                    "asset_format": "svg",
                    "release_preview_path": None,
                }
            ]
        }
    )


def _write_baseline_release(path: Path, version: str, items: list[AlphaExportedItemRecord]) -> None:
    manifests_dir = path / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    (path / "docs").mkdir(parents=True, exist_ok=True)
    (path / "docs" / "CHANGELOG.md").write_text("# Previous\n", encoding="utf-8")
    (manifests_dir / "item_manifest.json").write_text(
        json.dumps({"items": [_public_item_payload(item) for item in items]}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (manifests_dir / "release_record.json").write_text(
        json.dumps(
            {
                "version": version,
                "profile_id": "profile_open_v1",
                "included_sources": sorted({item.source_id for item in items}),
                "split_counts": dict(sorted((Counter(item.split for item in items if item.split)).items())),
                "real_items": len(items),
                "synthetic_items": 0,
                "review_required_count": 0,
                "blocked_count": 0,
                "hocrgen_commit": "deadbeef",
                "exported_at": "2026-04-20T10:00:00+00:00",
                "schema_version": 1,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _make_item(
    item_id: str,
    split: str | None,
    normalized_asset_path: str,
    preview_path: str | None = None,
    preview_generated: bool = False,
) -> PrivacyScannedItemRecord:
    normalized_asset = NormalizedAssetRecord(
        item_id=item_id,
        source_asset_path=normalized_asset_path,
        normalized_asset_path=normalized_asset_path,
        asset_format="svg",
        media_type="image/svg+xml",
        width=100,
        height=100,
        file_size_bytes=6,
        sha256="abc123",
        is_vector=True,
        normalization_action="copied",
        preview_generated=preview_generated,
        preview_path=preview_path,
    )
    return PrivacyScannedItemRecord.model_validate(
        {
            "candidate_id": item_id,
            "source_id": "test_source",
            "source_item_id": item_id.split(":", 1)[-1],
            "source_url": f"https://example.org/{item_id}",
            "discovery_method": "test",
            "title": item_id,
            "fixture_path": None,
            "raw_metadata": {},
            "raw_rights_text": "Any Use Permitted",
            "asset_references": [],
            "metadata": {},
            "item_id": item_id,
            "normalized_license": "CC-BY-4.0",
            "rights_classification": RightsClassification.open,
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
