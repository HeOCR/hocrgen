from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hocrgen.cli import main
from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.config.loader import default_config_root
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.pipeline import execute_pipeline, write_run_metadata, write_run_summary
from hocrgen.runs import load_resumed_pipeline_state


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
    benchmark_manifest = json.loads((run_dir / "build_release" / "benchmark_manifest.json").read_text(encoding="utf-8"))
    benchmark_audit = json.loads((run_dir / "build_release" / "benchmark_selection_audit.json").read_text(encoding="utf-8"))
    benchmark_policy = json.loads((run_dir / "build_release" / "benchmark_stability_policy.json").read_text(encoding="utf-8"))
    benchmark_card = (run_dir / "build_release" / "BENCHMARK_CARD.md").read_text(encoding="utf-8")

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
    assert release_summary["benchmark_id"] == "benchmark_v1"
    assert release_summary["benchmark_item_count"] == 3
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
    benchmark_ids = {item["item_id"] for item in benchmark_manifest["items"]}
    assert benchmark_ids == {
        "nli_any_use_permitted:nli-ms-seed-006",
        "pinkas_open:pinkas-ledger-001",
        "project_synthetic:synthetic-0",
    }
    assert {item["item_id"] for item in benchmark_manifest["items"] if item["is_synthetic"]} == {"project_synthetic:synthetic-0"}
    assert {item["benchmark_split"] for item in benchmark_manifest["items"]} == {"train"}
    assert {item["outcome"] for item in benchmark_audit["items"]} == {"selected"}
    assert benchmark_policy["benchmark_id"] == "benchmark_v1"
    assert "Review Bar" in benchmark_card
    assert "Stability Policy" in benchmark_card


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


def test_build_release_fails_when_benchmark_approved_item_is_missing(tmp_path: Path, capsys) -> None:
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--source",
            "nli_any_use_permitted",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "benchmark benchmark_v1 approved item pinkas_open:pinkas-ledger-001 is not release-ready" in payload["error"]


def test_build_release_fails_when_profile_excludes_benchmark_approved_source(tmp_path: Path, capsys) -> None:
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

    assert exit_code == 1
    assert "benchmark benchmark_v1 approved item project_synthetic:synthetic-0 is not release-ready" in payload["error"]


def test_build_release_reports_benchmark_config_validation_as_stage_error(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    benchmark_root = tmp_path / "benchmark_data" / "benchmark_v1"
    benchmark_root.mkdir(parents=True)
    (benchmark_root / "config.json").write_text(
        json.dumps(
            {
                "approved_items": [
                    {
                        "benchmark_split": "train",
                        "item_id": "nli_any_use_permitted:nli-ms-seed-006",
                        "rationale": "real exemplar",
                    }
                ],
                "benchmark_id": "other_benchmark",
                "description": "fixture benchmark",
                "review_bar": "explicit approval required",
                "selection_policy": "representative mixed",
                "stability_policy": {"splits": "stable"},
                "version": 1,
            }
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
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert "benchmark config validation failed" in payload["error"]


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


def test_execute_pipeline_can_resume_from_policy_filter_run(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    initial_context = create_run_context("profile_open_v1", dry_run=True, workdir=tmp_path / "initial")
    options = StageOptions()

    initial_run_metadata = write_run_metadata(initial_context)
    initial_results = execute_pipeline("policy-filter", bundle, initial_context, options)
    initial_run_summary = write_run_summary(
        initial_context,
        "policy-filter",
        [initial_run_metadata, *(artifact for result in initial_results for artifact in [result.summary_path, *result.extra_artifacts])],
    )
    initial_policy_summary = json.loads((initial_context.stage_dir("policy-filter") / "summary.json").read_text(encoding="utf-8"))
    assert initial_run_summary.exists()

    resumed_state, latest_stage = load_resumed_pipeline_state(initial_context.run_dir, "profile_open_v1", "build-release")
    resumed_context = create_run_context("profile_open_v1", dry_run=True, workdir=tmp_path / "resumed")
    resumed_run_metadata = write_run_metadata(resumed_context)
    resumed_results = execute_pipeline(
        "build-release",
        bundle,
        resumed_context,
        options,
        initial_state=resumed_state,
        start_stage="acquire" if latest_stage == "policy-filter" else None,
    )
    resumed_run_summary = write_run_summary(
        resumed_context,
        "build-release",
        [resumed_run_metadata, *(artifact for result in resumed_results for artifact in [result.summary_path, *result.extra_artifacts])],
    )
    release_summary = json.loads((resumed_context.stage_dir("build-release") / "release_summary.json").read_text(encoding="utf-8"))

    assert resumed_run_summary.exists()
    assert release_summary["accepted_count"] == initial_policy_summary["accepted_count"]
    assert release_summary["release_ready_count"] > 0


def test_load_resumed_pipeline_state_rejects_profile_mismatch(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    context = create_run_context("profile_open_v1", dry_run=True, workdir=tmp_path / "initial")
    options = StageOptions()

    run_metadata = write_run_metadata(context)
    results = execute_pipeline("policy-filter", bundle, context, options)
    write_run_summary(
        context,
        "policy-filter",
        [run_metadata, *(artifact for result in results for artifact in [result.summary_path, *result.extra_artifacts])],
    )

    with pytest.raises(StageExecutionError, match="profile mismatch"):
        load_resumed_pipeline_state(context.run_dir, "profile_review_v1", "build-release")


def test_load_resumed_pipeline_state_rejects_missing_required_manifests(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    context = create_run_context("profile_open_v1", dry_run=True, workdir=tmp_path / "initial")
    options = StageOptions()

    run_metadata = write_run_metadata(context)
    results = execute_pipeline("policy-filter", bundle, context, options)
    write_run_summary(
        context,
        "policy-filter",
        [run_metadata, *(artifact for result in results for artifact in [result.summary_path, *result.extra_artifacts])],
    )
    (context.stage_dir("policy-filter") / "accepted_items.json").unlink()

    with pytest.raises(StageExecutionError, match="missing required"):
        load_resumed_pipeline_state(context.run_dir, "profile_open_v1", "build-release")


def test_load_resumed_pipeline_state_rejects_target_stage_already_completed(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    context = create_run_context("profile_open_v1", dry_run=True, workdir=tmp_path / "initial")
    options = StageOptions()

    run_metadata = write_run_metadata(context)
    results = execute_pipeline("build-release", bundle, context, options)
    write_run_summary(
        context,
        "build-release",
        [run_metadata, *(artifact for result in results for artifact in [result.summary_path, *result.extra_artifacts])],
    )

    with pytest.raises(StageExecutionError, match="already reached or passed target stage"):
        load_resumed_pipeline_state(context.run_dir, "profile_open_v1", "build-release")
