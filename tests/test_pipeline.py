from __future__ import annotations

import json
import shutil
from pathlib import Path

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root


def test_end_to_end_open_build_has_expected_counts(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    normalized_items = json.loads((run_dir / "normalize" / "normalized_items.json").read_text(encoding="utf-8"))
    qa_report = json.loads((run_dir / "normalize" / "qa_report.json").read_text(encoding="utf-8"))
    release_summary = json.loads((run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))
    source_stats = json.loads((run_dir / "build_release" / "source_stats.json").read_text(encoding="utf-8"))

    assert len(normalized_items["items"]) == 4
    assert qa_report["failed_count"] == 0
    assert release_summary["accepted_count"] == 4
    assert release_summary["acquired_count"] == 4
    assert release_summary["normalized_count"] == 4
    assert release_summary["qa_failed_count"] == 0
    assert release_summary["real_items"] == 3
    assert release_summary["synthetic_items"] == 1
    assert source_stats["asset_formats"]["svg"] == 5
    assert source_stats["sources"]["nli_any_use_permitted"] == 1
    assert source_stats["sources"]["project_synthetic"] == 1


def test_unknown_rights_are_rejected_in_pipeline(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    sources_path = config_root / "sources.yaml"
    fixture_seed = (Path(__file__).parent / "fixtures" / "nli" / "seeds_unknown.yaml").resolve()
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace(
            "package://data/nli/seeds.yaml", str(fixture_seed)
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "policy-filter",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
            "--source",
            "nli_any_use_permitted",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    accepted = json.loads((run_dir / "policy_filter" / "accepted_items.json").read_text(encoding="utf-8"))
    rejected = json.loads((run_dir / "policy_filter" / "rejected_items.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert accepted["items"] == []
    assert rejected["items"][0]["eligibility_reason"] == "unknown_rights"


def test_excluded_sources_are_not_selected(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    profile_path = config_root / "profiles" / "profile_open_v1.yaml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8")
        .replace("  - project_synthetic\n", "")
        .replace("exclude_sources: []", "exclude_sources:\n  - project_synthetic"),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    release_summary = json.loads((run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))
    source_stats = json.loads((run_dir / "build_release" / "source_stats.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert release_summary["synthetic_items"] == 0
    assert "project_synthetic" not in source_stats["sources"]
