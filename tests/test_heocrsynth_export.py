from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.package.heocrsynth import SyntheticExportConfig, export_synthetic_release
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
    assert release_summary["synthetic_only"] is True
    assert synthetic_composition["real_items"] == 0
    assert synthetic_composition["synthetic_items"] == 2
    assert synthetic_composition["synthetic_fraction"] == 1.0
    assert synthetic_composition["by_provider_version"] == {"fixture-f4c-v1": 2}
    assert annotation_pilot["pilot_item_count"] == 0
    assert {item["item_id"] for item in benchmark_manifest["items"]} == {"project_synthetic:synthetic-0"}
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
    config_root = _fixture_config_root(tmp_path)
    bundle = load_and_validate_bundle(config_root)
    context = create_run_context(profile_id="profile_open_v1", dry_run=True, workdir=tmp_path / "work")
    execute_pipeline("build-release", bundle, context, options=StageOptions())
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
