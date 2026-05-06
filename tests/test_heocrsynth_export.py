from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import PrivacyScannedItemRecord
from hocrgen.package import heocrsynth
from hocrgen.package.heocrsynth import (
    SyntheticExportConfig,
    _copy_synthetic_export_assets,
    _filter_synthetic_benchmark_reference_versioning,
    _handoff_doc,
    _is_synthetic_release_diff_baseline,
    _selected_resolution_records,
    _source_snapshot_lines,
    _split_sort_key,
    _synthetic_audit_item_payload,
    _synthetic_benchmark_card,
    _synthetic_benchmark_stability_policy,
    _validate_heocrsynth_repo_root,
    _validate_synthetic_export_config,
    _validate_synthetic_item_for_export,
    _validate_synthetic_overwrite_target,
    export_synthetic_release,
)
from hocrgen.pipeline import execute_pipeline


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


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fixture_release_state(tmp_path: Path):
    config_root = _fixture_config_root(tmp_path)
    bundle = load_and_validate_bundle(config_root)
    context = create_run_context(profile_id="profile_open_v1", dry_run=True, workdir=tmp_path / "work")
    execute_pipeline("build-release", bundle, context, options=StageOptions())
    return bundle, context


def _synthetic_release_item(context) -> PrivacyScannedItemRecord:
    manifest = _json(context.run_dir / "build_release" / "item_manifest.json")
    item = next(item for item in manifest["items"] if item["item_id"] == "project_synthetic:synthetic-0")
    return PrivacyScannedItemRecord(**item)


def test_export_synthetic_creates_heocrsynth_shaped_tree(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "HeOCRsynth" / "releases" / "synth-alpha-v0"

    exit_code = main(
        [
            "export-synthetic",
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
    assert payload["dataset_id"] == "HeOCRsynth"
    assert payload["stage"] == "export-synthetic"
    assert payload["synthetic_only"] is True
    assert payload["export_dir"] == str(output_dir)
    for relative_path in [
        "manifests/item_manifest.json",
        "manifests/release_record.json",
        "manifests/release_summary.json",
        "manifests/synthetic_composition.json",
        "manifests/benchmark_manifest.json",
        "manifests/benchmark_leakage_risk.json",
        "docs/DATASET_CARD.md",
        "docs/RELEASE_NOTES.md",
        "docs/PROVENANCE.md",
        "docs/HANDOFF.md",
        "docs/BENCHMARK_CARD.md",
    ]:
        assert (output_dir / relative_path).exists()

    release_record = _json(output_dir / "manifests" / "release_record.json")
    release_summary = _json(output_dir / "manifests" / "release_summary.json")
    benchmark_reference_versioning = _json(output_dir / "manifests" / "benchmark_reference_versioning.json")
    item_manifest = _json(output_dir / "manifests" / "item_manifest.json")
    synthetic_composition = _json(output_dir / "manifests" / "synthetic_composition.json")
    benchmark_manifest = _json(output_dir / "manifests" / "benchmark_manifest.json")
    annotation_pilot = _json(output_dir / "manifests" / "annotation_pilot_manifest.json")
    handoff = (output_dir / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    dataset_card = (output_dir / "docs" / "DATASET_CARD.md").read_text(encoding="utf-8")
    release_notes = (output_dir / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")

    assert release_record["dataset_id"] == "HeOCRsynth"
    assert release_record["release_kind"] == "synthetic_only"
    assert release_record["synthetic_only"] is True
    assert release_record["real_items"] == 0
    assert release_record["synthetic_items"] == 2
    assert release_record["included_sources"] == ["project_synthetic"]
    assert release_summary["exported_real_items"] == 0
    assert release_summary["exported_synthetic_items"] == 2
    assert release_summary["release_ready_count"] == 2
    assert release_summary["synthetic_only"] is True
    assert release_summary["upstream_build_counts"]["release_ready_count"] == 4
    assert "accepted_count" not in release_summary
    assert "normalized_count" not in release_summary
    assert "retained_count" not in release_summary
    assert synthetic_composition["real_items"] == 0
    assert synthetic_composition["synthetic_items"] == 2
    assert synthetic_composition["synthetic_fraction"] == 1.0
    assert synthetic_composition["by_provider_version"] == {"fixture-f4c-v1": 2}
    assert annotation_pilot["pilot_item_count"] == 0
    assert {item["item_id"] for item in benchmark_manifest["items"]} == {"project_synthetic:synthetic-0"}
    assert benchmark_reference_versioning["export_scope"] == "selected_synthetic_items"
    assert benchmark_reference_versioning["checked_count"] == 1
    assert "synthetic-only HeOCRsynth" in dataset_card
    assert "not a mixed real+synthetic HeOCR release" in dataset_card
    assert "Mixed real+synthetic HeOCR releases remain handled by `export-alpha`." in release_notes
    assert "- Target release dir: `releases/synth-alpha-v0/`" in handoff
    assert str(output_dir.resolve()) not in handoff


def test_export_synthetic_payload_is_synthetic_only_and_portable(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "HeOCRsynth" / "releases" / "synth-alpha-v0"

    exit_code = main(
        [
            "export-synthetic",
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
    assert exit_code == 0
    _ = capsys.readouterr().out

    item_manifest = _json(output_dir / "manifests" / "item_manifest.json")
    review_required = _json(output_dir / "manifests" / "review_required_items.json")
    blocked = _json(output_dir / "manifests" / "blocked_items.json")
    split_manifest = _json(output_dir / "manifests" / "split_manifest.json")
    benchmark_leakage_risk = _json(output_dir / "manifests" / "benchmark_leakage_risk.json")
    all_manifest_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (output_dir / "manifests").glob("*.json")
    )

    assert review_required["items"] == []
    assert blocked["items"] == []
    assert {item["item_id"] for item in split_manifest["items"]} == {
        "project_synthetic:synthetic-0",
        "project_synthetic:synthetic-1",
    }
    assert benchmark_leakage_risk["export_scope"] == "selected_synthetic_items"
    for forbidden in [
        "nli_any_use_permitted",
        "pinkas_open",
        "biblia_open",
        "nli-ms",
        "pinkas-ledger",
        "biblia-doc",
    ]:
        assert forbidden not in all_manifest_text

    for item in item_manifest["items"]:
        assert item["item_id"].startswith("project_synthetic:")
        assert item["source_id"] == "project_synthetic"
        assert item["is_synthetic"] is True
        assert item["normalized_license"] == "PROJECT-SYNTHETIC"
        assert item["metadata"]["synthetic_license"] == "PROJECT-SYNTHETIC"
        assert "candidate synthetic input" in item["metadata"]["synthetic_disclosure"]
        assert item["metadata"]["hocrsyngen_provider_metadata"]["provider_name"] == "hocrsyngen"
        assert item["metadata"]["hocrsyngen_provider_metadata"]["provider_version"] == "fixture-f4c-v1"
        assert item["metadata"]["hocrsyngen_provider_metadata"]["used_network"] is False
        assert item["metadata"]["hocrsyngen_rendering_metadata"]["text_order"] == "logical"
        assert item["metadata"]["hocrsyngen_hebrew_coverage"]["has_hebrew_letters"] is True
        assert item["metadata"]["synthetic_hebrew_coverage"]["has_punctuation"] is True
        assert "normalized_assets" not in item
        for asset in item["exported_assets"]:
            assert asset["release_asset_path"].startswith("data/synthetic/train/project_synthetic:")
            assert asset["release_preview_path"].startswith("data/synthetic/train/project_synthetic:")
            assert not Path(asset["release_asset_path"]).is_absolute()
            assert (output_dir / asset["release_asset_path"]).exists()
            assert (output_dir / asset["release_preview_path"]).exists()


def test_export_synthetic_rejects_source_filter_before_pipeline(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--source",
            "project_synthetic",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "--source is not supported for export-synthetic" in payload["error"]
    assert not (tmp_path / "work").exists()


def test_export_synthetic_cli_reports_config_load_error(tmp_path: Path, capsys, monkeypatch) -> None:
    def fail_load(_config_root):
        raise ConfigValidationError("bad config")

    monkeypatch.setattr("hocrgen.cli._load_bundle", fail_load)

    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(tmp_path / "missing"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload == {"status": "error", "error": "bad config"}


def test_export_synthetic_cli_reports_unknown_profile(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "missing_profile",
            "--dry-run",
            "--config-root",
            str(config_root),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload == {"status": "error", "error": "unknown profile: missing_profile"}


def test_export_synthetic_cli_reports_pipeline_and_export_errors(tmp_path: Path, capsys, monkeypatch) -> None:
    config_root = _fixture_config_root(tmp_path)

    def fail_pipeline(*_args, **_kwargs):
        raise StageExecutionError("build failed")

    monkeypatch.setattr("hocrgen.cli.execute_pipeline", fail_pipeline)
    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "pipeline-work"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload == {"status": "error", "error": "build failed"}

    monkeypatch.setattr("hocrgen.cli.execute_pipeline", lambda *_args, **_kwargs: [])

    def fail_export(*_args, **_kwargs):
        raise StageExecutionError("export failed")

    monkeypatch.setattr("hocrgen.cli.export_synthetic_release", fail_export)
    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "export-work"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload == {"status": "error", "error": "export failed"}


def test_export_synthetic_can_target_heocrsynth_repo_checkout(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    heocrsynth_repo = tmp_path / "HeOCRsynth"
    (heocrsynth_repo / ".git").mkdir(parents=True)

    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--heocrsynth-repo",
            str(heocrsynth_repo),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    expected_export_dir = heocrsynth_repo / "releases" / "synth-alpha-v0"
    assert exit_code == 0
    assert payload["export_dir"] == str(expected_export_dir.resolve())
    assert payload["handoff_repo"] == str(heocrsynth_repo.resolve())
    handoff = (expected_export_dir / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert "- Target repo checkout: `HeOCRsynth`" in handoff
    assert "- Target release dir: `releases/synth-alpha-v0/`" in handoff
    assert str(heocrsynth_repo.resolve()) not in handoff


def test_export_synthetic_release_diff_reports_selection_limit_removed(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    releases_root = tmp_path / "HeOCRsynth" / "releases"
    baseline_dir = releases_root / "synth-alpha-v0"

    first_exit = main(
        [
            "export-synthetic",
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
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work2"),
            "--version",
            "synth-alpha-v1",
            "--output-dir",
            str(releases_root / "synth-alpha-v1"),
            "--compare-to",
            str(baseline_dir),
            "--max-synthetic-items",
            "1",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    release_diff = _json(export_dir / "manifests" / "release_diff.json")
    changelog = (export_dir / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    assert second_exit == 0
    assert release_diff["previous_version"] == "synth-alpha-v0"
    assert release_diff["counts"]["removed"] == 1
    assert release_diff["removed_items"] == [
        {
            "item_id": "project_synthetic:synthetic-1",
            "previous_split": "train",
            "reason": "selection_limit_excluded",
            "source_id": "project_synthetic",
        }
    ]
    assert "`selection_limit_excluded`" in changelog


def test_export_synthetic_auto_baseline_ignores_mixed_heocr_releases(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    releases_root = tmp_path / "releases"
    mixed_dir = releases_root / "alpha-v0"

    mixed_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "mixed-work"),
            "--output-dir",
            str(mixed_dir),
        ]
    )
    assert mixed_exit == 0
    _ = capsys.readouterr().out

    synthetic_exit = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "synthetic-work"),
            "--output-dir",
            str(releases_root / "synth-alpha-v0"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    export_dir = Path(payload["export_dir"])
    release_diff = _json(export_dir / "manifests" / "release_diff.json")
    changelog = (export_dir / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    assert synthetic_exit == 0
    assert release_diff["previous_version"] is None
    for forbidden in ["nli_any_use_permitted", "pinkas_open", "biblia_open"]:
        assert forbidden not in json.dumps(release_diff)
        assert forbidden not in changelog


def test_export_synthetic_rejects_empty_selection(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    exit_code = main(
        [
            "export-synthetic",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--max-synthetic-items",
            "0",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "synthetic export selection is empty"


def test_export_synthetic_rejects_missing_required_metadata_before_overwrite(tmp_path: Path) -> None:
    bundle, context = _fixture_release_state(tmp_path)
    build_manifest_path = context.run_dir / "build_release" / "item_manifest.json"
    build_manifest = _json(build_manifest_path)
    for item in build_manifest["items"]:
        if item["item_id"] == "project_synthetic:synthetic-0":
            item["metadata"].pop("synthetic_disclosure")
    build_manifest_path.write_text(json.dumps(build_manifest), encoding="utf-8")
    output_dir = tmp_path / "HeOCRsynth" / "releases" / "synth-alpha-v0"
    output_dir.mkdir(parents=True)
    stale_file = output_dir / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="missing required metadata: synthetic_disclosure"):
        export_synthetic_release(
            bundle,
            context.run_dir,
            "profile_open_v1",
            SyntheticExportConfig(version="synth-alpha-v0", output_dir=output_dir, overwrite=True),
        )

    assert stale_file.exists()


def test_export_synthetic_rejects_conflicting_or_existing_export_dirs(tmp_path: Path) -> None:
    bundle, context = _fixture_release_state(tmp_path)
    output_dir = tmp_path / "HeOCRsynth" / "releases" / "synth-alpha-v0"
    heocrsynth_repo = tmp_path / "HeOCRsynth"
    (heocrsynth_repo / ".git").mkdir(parents=True)

    with pytest.raises(StageExecutionError, match="--output-dir and --heocrsynth-repo cannot be used together"):
        export_synthetic_release(
            bundle,
            context.run_dir,
            "profile_open_v1",
            SyntheticExportConfig(version="synth-alpha-v0", output_dir=output_dir, heocrsynth_repo=heocrsynth_repo),
        )

    output_dir.mkdir(parents=True)
    with pytest.raises(StageExecutionError, match="synthetic export directory already exists"):
        export_synthetic_release(
            bundle,
            context.run_dir,
            "profile_open_v1",
            SyntheticExportConfig(version="synth-alpha-v0", output_dir=output_dir),
        )


def test_export_synthetic_overwrite_replaces_existing_export_dir(tmp_path: Path) -> None:
    bundle, context = _fixture_release_state(tmp_path)
    output_dir = tmp_path / "HeOCRsynth" / "releases" / "synth-alpha-v0"
    output_dir.mkdir(parents=True)
    stale_file = output_dir / "stale.txt"
    stale_file.write_text("stale", encoding="utf-8")

    result = export_synthetic_release(
        bundle,
        context.run_dir,
        "profile_open_v1",
        SyntheticExportConfig(version="synth-alpha-v0", output_dir=output_dir, overwrite=True),
    )

    assert result.export_dir == output_dir.resolve()
    assert not stale_file.exists()
    assert (output_dir / "manifests" / "item_manifest.json").exists()


def test_export_synthetic_blocks_unresolved_release_gates(tmp_path: Path) -> None:
    bundle, context = _fixture_release_state(tmp_path)
    summary_path = context.run_dir / "build_release" / "release_summary.json"
    summary = _json(summary_path)
    summary["near_duplicate_review_status"] = "blocked"
    summary["near_duplicate_cluster_count"] = 7
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(StageExecutionError, match="7 near-duplicate cluster"):
        export_synthetic_release(
            bundle,
            context.run_dir,
            "profile_open_v1",
            SyntheticExportConfig(version="synth-alpha-v0", output_dir=tmp_path / "out"),
        )

    summary["near_duplicate_review_status"] = "ok"
    summary["benchmark_holdout_leakage_status"] = "blocked"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    leakage_path = context.run_dir / "build_release" / "benchmark_leakage_risk.json"
    leakage = _json(leakage_path)
    leakage["unresolved_count"] = 3
    leakage_path.write_text(json.dumps(leakage), encoding="utf-8")

    with pytest.raises(StageExecutionError, match="3 unresolved benchmark/holdout leakage"):
        export_synthetic_release(
            bundle,
            context.run_dir,
            "profile_open_v1",
            SyntheticExportConfig(version="synth-alpha-v0", output_dir=tmp_path / "out"),
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item.model_copy(update={"normalized_license": "MIT"}), "PROJECT-SYNTHETIC license"),
        (
            lambda item: item.model_copy(
                deep=True,
                update={"metadata": {**item.metadata, "synthetic_license": "MIT"}},
            ),
            "must disclose PROJECT-SYNTHETIC",
        ),
        (
            lambda item: item.model_copy(
                deep=True,
                update={"metadata": {**item.metadata, "hocrsyngen_provider_metadata": {"provider_name": "other"}}},
            ),
            "must preserve hocrsyngen provider metadata",
        ),
        (
            lambda item: item.model_copy(
                deep=True,
                update={
                    "metadata": {
                        **item.metadata,
                        "hocrsyngen_provider_metadata": {
                            **item.metadata["hocrsyngen_provider_metadata"],
                            "used_network": True,
                        },
                    }
                },
            ),
            "disallowed hocrsyngen dependency flags",
        ),
        (
            lambda item: item.model_copy(
                deep=True,
                update={"metadata": {**item.metadata, "hocrsyngen_rendering_metadata": {"text_order": "visual"}}},
            ),
            "logical hocrsyngen rendering metadata",
        ),
        (
            lambda item: item.model_copy(
                deep=True,
                update={"metadata": {**item.metadata, "hocrsyngen_hebrew_coverage": {"has_hebrew_letters": False}}},
            ),
            "Hebrew coverage metadata",
        ),
    ],
)
def test_validate_synthetic_item_rejects_invalid_metadata(tmp_path: Path, mutation, message: str) -> None:
    _bundle, context = _fixture_release_state(tmp_path)
    item = mutation(_synthetic_release_item(context))

    with pytest.raises(StageExecutionError, match=message):
        _validate_synthetic_item_for_export(item)


def test_validate_synthetic_export_config_and_asset_copy_guards(tmp_path: Path) -> None:
    _bundle, context = _fixture_release_state(tmp_path)
    item = _synthetic_release_item(context)

    with pytest.raises(StageExecutionError, match="max_synthetic_items must be non-negative"):
        _validate_synthetic_export_config(SyntheticExportConfig(version="synth-alpha-v0", max_synthetic_items=-1))

    with pytest.raises(StageExecutionError, match="missing a split assignment"):
        _copy_synthetic_export_assets([item.model_copy(update={"split": None})], tmp_path / "data" / "synthetic")


def test_synthetic_benchmark_filter_helpers_cover_edge_cases() -> None:
    assert _filter_synthetic_benchmark_reference_versioning(None, None) is None
    versioning = {
        "benchmark_id": "benchmark_v1",
        "reference_manifest_id": "refs",
        "status": "ok",
        "checked_count": 3,
        "event_count": 3,
        "events": [
            {"reference_id": "ref-keep", "item_id": "item-keep", "event": "changed"},
            {"reference_id": "ref-other", "item_id": "item-other", "event": "changed"},
            "not-a-dict",
        ],
    }
    manifest = type(
        "Manifest",
        (),
        {"items": [type("Reference", (), {"reference_id": "ref-keep", "item_id": "item-keep"})()]},
    )()

    filtered = _filter_synthetic_benchmark_reference_versioning(versioning, manifest)

    assert filtered["checked_count"] == 1
    assert filtered["event_count"] == 1
    assert filtered["events"] == [{"reference_id": "ref-keep", "item_id": "item-keep", "event": "changed"}]
    assert filtered["export_scope"] == "selected_synthetic_items"
    assert _selected_resolution_records("bad", {"a"}) == []
    assert _selected_resolution_records([{"benchmark_item_ids": ["x"]}, "bad"], {"a"}) == []
    assert _selected_resolution_records(
        [{"benchmark_item_ids": ["a", "x"], "non_benchmark_item_ids": ["b", "y"], "kind": "accepted"}],
        {"a", "b"},
    ) == [{"benchmark_item_ids": ["a"], "non_benchmark_item_ids": ["b"], "kind": "accepted"}]


def test_synthetic_comparison_baseline_helpers(tmp_path: Path) -> None:
    export_dir = tmp_path / "releases" / "synth-alpha-v1"

    assert heocrsynth._resolve_synthetic_comparison_release(export_dir, SyntheticExportConfig(version="synth-alpha-v1")) is None
    assert _is_synthetic_release_diff_baseline(tmp_path / "missing") is False

    bad_release = tmp_path / "releases" / "bad"
    (bad_release / "manifests").mkdir(parents=True)
    (bad_release / "manifests" / "item_manifest.json").write_text('{"items": []}', encoding="utf-8")
    (bad_release / "manifests" / "release_record.json").write_text("{not json", encoding="utf-8")
    assert _is_synthetic_release_diff_baseline(bad_release) is False
    mixed_release = tmp_path / "releases" / "mixed"
    (mixed_release / "manifests").mkdir(parents=True)
    (mixed_release / "manifests" / "item_manifest.json").write_text('{"items": []}', encoding="utf-8")
    (mixed_release / "manifests" / "release_record.json").write_text(
        json.dumps({"version": "alpha-v0", "dataset_id": "HeOCR"}),
        encoding="utf-8",
    )

    baseline = tmp_path / "releases" / "synth-alpha-v0"
    (baseline / "manifests").mkdir(parents=True)
    (baseline / "manifests" / "item_manifest.json").write_text('{"items": []}', encoding="utf-8")
    (baseline / "manifests" / "release_record.json").write_text(
        json.dumps(
            {
                "dataset_id": "HeOCRsynth",
                "release_kind": "synthetic_only",
                "synthetic_only": True,
                "version": "synth-alpha-v0",
                "exported_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    same_version = tmp_path / "releases" / "same-name"
    (same_version / "manifests").mkdir(parents=True)
    (same_version / "manifests" / "item_manifest.json").write_text('{"items": []}', encoding="utf-8")
    (same_version / "manifests" / "release_record.json").write_text(
        json.dumps(
            {
                "dataset_id": "HeOCRsynth",
                "release_kind": "synthetic_only",
                "synthetic_only": True,
                "version": "synth-alpha-v1",
                "exported_at": "2026-02-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    same_name_as_config = tmp_path / "releases" / "synth-alpha-v1"
    same_name_as_config.mkdir()
    ignored_file = tmp_path / "releases" / "not-a-dir"
    ignored_file.write_text("", encoding="utf-8")

    assert heocrsynth._resolve_synthetic_comparison_release(export_dir, SyntheticExportConfig(version="synth-alpha-v1")) == baseline
    assert (
        heocrsynth._resolve_synthetic_comparison_release(
            tmp_path / "releases" / "current",
            SyntheticExportConfig(version="synth-alpha-v1"),
        )
        == baseline
    )
    with pytest.raises(StageExecutionError, match="current export directory"):
        heocrsynth._resolve_synthetic_comparison_release(
            export_dir,
            SyntheticExportConfig(version="synth-alpha-v1", compare_to=export_dir),
        )
    with pytest.raises(StageExecutionError, match="not a HeOCRsynth synthetic-only release"):
        heocrsynth._resolve_synthetic_comparison_release(
            export_dir,
            SyntheticExportConfig(version="synth-alpha-v1", compare_to=mixed_release),
        )


def test_heocrsynth_docs_and_small_helpers(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_fixture_config_root(tmp_path))
    profile = bundle.profiles["profile_open_v1"]
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    summary = {
        "exported_item_count": 2,
        "exported_synthetic_items": 2,
        "review_required_count": 0,
        "blocked_count": 0,
    }

    outside_handoff = _handoff_doc(
        "synth-alpha-v0",
        tmp_path / "outside" / "synth-alpha-v0",
        profile,
        summary,
        ["project_synthetic"],
        "abc123",
        tmp_path / "repo",
    )

    assert "- Target release dir: `releases/synth-alpha-v0/`" in outside_handoff
    assert "HeOCRsynth Synthetic Benchmark Card" in _synthetic_benchmark_card("# Benchmark Card: benchmark_v1")
    assert _synthetic_benchmark_stability_policy({"policy_id": "p"})["policy_id"] == "p"
    assert "Synthetic-only export view" in _synthetic_benchmark_stability_policy({})["selection_policy"]
    assert "project_synthetic" in "\n".join(_source_snapshot_lines(source))
    assert _split_sort_key(None) > _split_sort_key("test")
    assert _split_sort_key("custom") == _split_sort_key(None)


def test_heocrsynth_repo_and_overwrite_validation(tmp_path: Path) -> None:
    with pytest.raises(StageExecutionError, match="does not exist"):
        _validate_heocrsynth_repo_root(tmp_path / "missing")

    file_path = tmp_path / "file"
    file_path.write_text("", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="not a directory"):
        _validate_heocrsynth_repo_root(file_path)

    repo_without_git = tmp_path / "repo"
    repo_without_git.mkdir()
    with pytest.raises(StageExecutionError, match="not a git checkout"):
        _validate_heocrsynth_repo_root(repo_without_git)

    (repo_without_git / ".git").mkdir()
    assert _validate_heocrsynth_repo_root(repo_without_git) == repo_without_git.resolve()

    with pytest.raises(StageExecutionError, match="not a directory"):
        _validate_synthetic_overwrite_target(file_path, "file")
    with pytest.raises(StageExecutionError, match="unsafe export target"):
        _validate_synthetic_overwrite_target(Path.home(), Path.home().name)
    shallow = Path(tmp_path.anchor) / "tmp"
    if shallow.is_dir():
        with pytest.raises(StageExecutionError, match="unsafe export target"):
            _validate_synthetic_overwrite_target(shallow, shallow.name)
    release_dir = tmp_path / "releases" / "wrong-name"
    release_dir.mkdir(parents=True)
    with pytest.raises(StageExecutionError, match="must end with synth-alpha-v0"):
        _validate_synthetic_overwrite_target(release_dir, "synth-alpha-v0")


def test_synthetic_audit_payload_covers_public_fields(tmp_path: Path) -> None:
    _bundle, context = _fixture_release_state(tmp_path)
    item = _synthetic_release_item(context)

    payload = _synthetic_audit_item_payload(item)

    assert payload["item_id"] == item.item_id
    assert payload["source_id"] == "project_synthetic"
    assert payload["normalized_license"] == "PROJECT-SYNTHETIC"
    assert payload["rights_classification"] == item.rights_classification.value
    assert payload["privacy_flag"] == item.privacy_flag.value
