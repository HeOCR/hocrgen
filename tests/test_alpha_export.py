from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root


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
    assert (output_dir / "docs" / "DATASET_CARD.md").exists()
    assert (output_dir / "docs" / "RELEASE_NOTES.md").exists()
    assert (output_dir / "docs" / "PROVENANCE.md").exists()


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
    split_manifest = json.loads((export_dir / "manifests" / "split_manifest.json").read_text(encoding="utf-8"))

    exported_ids = {item["item_id"] for item in item_manifest["items"]}
    assert "nli_any_use_permitted:nli-ms-001" not in exported_ids
    assert len(item_manifest["items"]) == 3
    assert len(split_manifest["items"]) == 3
    assert len(review_required["items"]) == 1
    assert review_required["items"][0]["source_id"] == "nli_any_use_permitted"
    assert blocked["items"] == []

    for item in item_manifest["items"]:
        item_dir = export_dir / "data" / item["split"] / item["item_id"]
        assert item_dir.exists()
        for asset in item["exported_assets"]:
            assert (export_dir / asset["release_asset_path"]).exists()


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


def test_export_alpha_docs_and_release_record_include_metadata(tmp_path: Path, capsys) -> None:
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
    release_record = json.loads((export_dir / "manifests" / "release_record.json").read_text(encoding="utf-8"))
    dataset_card = (export_dir / "docs" / "DATASET_CARD.md").read_text(encoding="utf-8")
    release_notes = (export_dir / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    provenance = (export_dir / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")
    current_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    assert release_record["profile_id"] == "profile_open_v1"
    assert release_record["included_sources"] == ["pinkas_open", "biblia_open", "project_synthetic"]
    assert release_record["hocrgen_commit"] == current_commit
    assert "# HeOCR alpha-v0" in dataset_card
    assert "Release Notes: alpha-v0" in release_notes
    assert f"`{current_commit}`" in provenance
