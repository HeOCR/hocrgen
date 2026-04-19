from __future__ import annotations

import json
import shutil
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from hocrgen.cli import handle_export_alpha, main
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.config.models import RightsClassification
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import AlphaExportedItemRecord, NormalizedAssetRecord, PrivacyScannedItemRecord, ReviewQueueRecord
from hocrgen.package.alpha import (
    AlphaExportConfig,
    REPO_ROOT,
    _audit_item_payload,
    _build_source_stats,
    _copy_export_assets,
    _current_commit_sha,
    _public_item_payload,
    _review_queue_payload,
    _sanitize_portable_value,
    _select_alpha_items,
    _source_priority,
    _split_sort_key,
    _validate_heocr_repo_root,
    _validate_overwrite_target,
    export_alpha_release,
)


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
    assert (output_dir / "docs" / "HANDOFF.md").exists()
    handoff_doc = (output_dir / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert "- Target repo checkout: `<manual target checkout>`" in handoff_doc
    assert "- Target release dir: `releases/alpha-v0/`" in handoff_doc
    assert str(output_dir.resolve()) not in handoff_doc


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
    assert len(item_manifest["items"]) == 3
    assert len(split_manifest["items"]) == 3
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
    synthetic_item = next(item for item in item_manifest["items"] if item["source_id"] == "project_synthetic")
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
    dataset_card = (export_dir / "docs" / "DATASET_CARD.md").read_text(encoding="utf-8")
    release_notes = (export_dir / "docs" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    provenance = (export_dir / "docs" / "PROVENANCE.md").read_text(encoding="utf-8")
    git_result = subprocess.run(["git", "rev-parse", "HEAD"])

    assert release_record["profile_id"] == "profile_open_v1"
    assert release_record["included_sources"] == ["nli_any_use_permitted", "pinkas_open", "project_synthetic"]
    if git_result.returncode == 0:
        current_commit = git_result.stdout.strip()
        assert release_record["hocrgen_commit"] == current_commit
        assert f"`{current_commit}`" in provenance
    else:
        assert release_record["hocrgen_commit"] == "unknown"
    assert "# HeOCR alpha-v0" in dataset_card
    assert "Release Notes: alpha-v0" in release_notes
    assert dataset_card.index("`nli_any_use_permitted`") < dataset_card.index("`pinkas_open`")
    assert dataset_card.index("`pinkas_open`") < dataset_card.index("`project_synthetic`")
    assert "`biblia_open`" not in dataset_card


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


def test_validate_overwrite_target_rejects_non_directory(tmp_path: Path) -> None:
    target = tmp_path / "alpha-v0"
    target.write_text("not a directory", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="overwrite target is not a directory"):
        _validate_overwrite_target(target, "alpha-v0")


def test_validate_overwrite_target_rejects_shallow_paths() -> None:
    with pytest.raises(StageExecutionError, match="refusing to overwrite unsafe export target"):
        _validate_overwrite_target(Path("/tmp"), "tmp")


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
