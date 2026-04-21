from __future__ import annotations

import json
import shutil
from pathlib import Path

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root


def test_end_to_end_open_build_has_expected_counts(tmp_path: Path, capsys) -> None:
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
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path),
            "--config-root",
            str(config_root),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    normalized_items = json.loads((run_dir / "normalize" / "normalized_items.json").read_text(encoding="utf-8"))
    qa_report = json.loads((run_dir / "normalize" / "qa_report.json").read_text(encoding="utf-8"))
    split_manifest = json.loads((run_dir / "split" / "split_manifest.json").read_text(encoding="utf-8"))
    release_summary = json.loads((run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))
    source_stats = json.loads((run_dir / "build_release" / "source_stats.json").read_text(encoding="utf-8"))
    item_manifest = json.loads((run_dir / "build_release" / "item_manifest.json").read_text(encoding="utf-8"))
    removed_duplicate_items = json.loads((run_dir / "build_release" / "removed_duplicate_items.json").read_text(encoding="utf-8"))
    review_required_items = json.loads((run_dir / "build_release" / "review_required_items.json").read_text(encoding="utf-8"))
    review_queue = json.loads((run_dir / "build_release" / "review_queue.json").read_text(encoding="utf-8"))
    classification_stats = json.loads((run_dir / "build_release" / "classification_stats.json").read_text(encoding="utf-8"))
    privacy_stats = json.loads((run_dir / "build_release" / "privacy_stats.json").read_text(encoding="utf-8"))

    assert len(normalized_items["items"]) == 4
    assert qa_report["failed_count"] == 0
    assert release_summary["accepted_count"] == 4
    assert release_summary["acquired_count"] == 4
    assert release_summary["normalized_count"] == 4
    assert release_summary["retained_count"] == 4
    assert release_summary["duplicate_removed_count"] == 0
    assert release_summary["qa_failed_count"] == 0
    assert release_summary["release_ready_count"] == 3
    assert release_summary["review_approved_count"] == 0
    assert release_summary["review_rejected_count"] == 0
    assert release_summary["review_required_count"] == 1
    assert release_summary["review_unresolved_count"] == 1
    assert release_summary["blocked_count"] == 0
    assert release_summary["real_items"] == 2
    assert release_summary["synthetic_items"] == 1
    assert sum(release_summary["split_counts"].values()) == 3
    assert source_stats["asset_formats"] == {"jpeg": 3}
    assert source_stats["sources"]["nli_any_use_permitted"] == 1
    assert source_stats["sources"]["pinkas_open"] == 1
    assert source_stats["sources"]["project_synthetic"] == 1
    assert "biblia_open" not in source_stats["sources"]
    assert len(split_manifest["items"]) == 3
    assert len(item_manifest["items"]) == 3
    assert removed_duplicate_items["items"] == []
    assert len(review_required_items["items"]) == 1
    assert {item["source_id"] for item in review_required_items["items"]} == {"biblia_open"}
    assert len(review_queue["items"]) == 1
    assert {item["review_item_id"] for item in review_queue["items"]} == {"review:biblia_open:biblia-doc-001"}
    decision_audit = json.loads((run_dir / "build_release" / "decision_audit.json").read_text(encoding="utf-8"))
    assert len(decision_audit["items"]) == 4
    assert {item["decision_source"] for item in decision_audit["items"]} == {
        "automatic_release_ready",
        "default_unresolved",
    }
    assert classification_stats["period_class"]["modern"] == 2
    by_source = {item["source_id"]: item for item in item_manifest["items"]}
    assert by_source["nli_any_use_permitted"]["quality_tier"] == "high"
    assert privacy_stats["privacy_flag"] == {"clear": 4}


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


def test_build_release_removes_exact_duplicates(tmp_path: Path, capsys) -> None:
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
                        "asset_path": "package://data/pinkas/assets/pinkas_001.jpg",
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    sources_path = config_root / "sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace(
            "package://data/biblia/records.json", str(duplicate_records_path)
        ).replace(
            "package://data/nli/seeds.yaml", str(fixture_seed)
        ),
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
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    release_summary = json.loads((run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))
    duplicate_relations = json.loads((run_dir / "build_release" / "duplicate_relations.json").read_text(encoding="utf-8"))
    duplicate_clusters = json.loads((run_dir / "build_release" / "duplicate_clusters.json").read_text(encoding="utf-8"))
    removed_duplicate_items = json.loads((run_dir / "build_release" / "removed_duplicate_items.json").read_text(encoding="utf-8"))
    split_manifest = json.loads((run_dir / "build_release" / "split_manifest.json").read_text(encoding="utf-8"))
    item_manifest = json.loads((run_dir / "build_release" / "item_manifest.json").read_text(encoding="utf-8"))

    review_required_items = json.loads((run_dir / "build_release" / "review_required_items.json").read_text(encoding="utf-8"))

    assert release_summary["normalized_count"] == 4
    assert release_summary["retained_count"] == 3
    assert release_summary["duplicate_removed_count"] == 1
    assert release_summary["release_ready_count"] == 3
    assert release_summary["review_approved_count"] == 0
    assert release_summary["review_required_count"] == 0
    assert release_summary["review_unresolved_count"] == 0
    assert len(duplicate_relations["items"]) == 1
    assert duplicate_relations["items"][0]["reason"] == "exact_asset_sequence_match"
    assert len(duplicate_clusters["items"]) == 1
    assert len(removed_duplicate_items["items"]) == 1
    assert len(split_manifest["items"]) == 3
    assert len(item_manifest["items"]) == 3
    assert review_required_items["items"] == []
