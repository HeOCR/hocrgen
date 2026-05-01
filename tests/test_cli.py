from __future__ import annotations

import json
from pathlib import Path

from hocrgen.cli import main


def test_config_validate_command_succeeds(capsys) -> None:
    exit_code = main(["config", "validate"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["profile_count"] == 2
    assert payload["benchmark"] == {"approved_item_count": 3, "benchmark_id": "benchmark_v1", "version": 1}
    assert payload["annotation_pilot"] == {
        "approved_item_count": 2,
        "pilot_id": "e3a_annotation_pilot",
        "version": 1,
    }
    assert payload["privacy_rules_version"] == 1
    assert payload["quality_thresholds_version"] == 1
    assert payload["review_data_counts"] == {"allowlist": 0, "blocklist": 0, "manual_decisions": 0}
    assert payload["source_count"] == 4


def test_build_release_command_creates_real_manifests(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "discover" / "candidates.json").exists()
    assert (run_dir / "fetch_metadata" / "enriched_candidates.json").exists()
    assert (run_dir / "policy_filter" / "accepted_items.json").exists()
    assert (run_dir / "acquire" / "acquired_items.json").exists()
    assert (run_dir / "normalize" / "normalized_items.json").exists()
    assert (run_dir / "dedupe" / "retained_items.json").exists()
    assert (run_dir / "classify" / "classified_items.json").exists()
    assert (run_dir / "privacy_scan" / "privacy_scanned_items.json").exists()
    assert (run_dir / "review" / "queue.json").exists()
    assert (run_dir / "review_merge" / "decision_audit.json").exists()
    assert (run_dir / "split" / "split_manifest.json").exists()
    assert (run_dir / "build_release" / "benchmark_manifest.json").exists()
    assert (run_dir / "build_release" / "benchmark_selection_audit.json").exists()
    assert (run_dir / "build_release" / "benchmark_stability_policy.json").exists()
    assert (run_dir / "build_release" / "BENCHMARK_CARD.md").exists()
    assert (run_dir / "build_release" / "annotation_pilot_manifest.json").exists()
    assert (run_dir / "build_release" / "annotation_pilot_selection_audit.json").exists()
    assert (run_dir / "build_release" / "release_summary.json").exists()


def test_normalize_command_creates_qa_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["normalize", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "normalize" / "normalized_items.json").exists()
    assert (run_dir / "normalize" / "failed_items.json").exists()
    assert (run_dir / "normalize" / "qa_report.json").exists()


def test_dedupe_command_creates_duplicate_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["dedupe", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "dedupe" / "retained_items.json").exists()
    assert (run_dir / "dedupe" / "duplicate_items.json").exists()
    assert (run_dir / "dedupe" / "duplicate_relations.json").exists()
    assert (run_dir / "dedupe" / "duplicate_clusters.json").exists()
    assert (run_dir / "dedupe" / "report.json").exists()


def test_split_command_creates_split_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["split", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "split" / "split_manifest.json").exists()
    assert (run_dir / "split" / "leakage_report.json").exists()


def test_classify_command_creates_classification_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["classify", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "classify" / "classified_items.json").exists()
    assert (run_dir / "classify" / "summary.json").exists()


def test_privacy_scan_command_creates_privacy_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["privacy-scan", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "privacy_scan" / "privacy_scanned_items.json").exists()
    assert (run_dir / "privacy_scan" / "summary.json").exists()


def test_review_export_command_creates_review_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["review-export", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "review" / "queue.json").exists()
    assert (run_dir / "review" / "release_ready_items.json").exists()
    assert (run_dir / "review" / "review_required_items.json").exists()
    assert (run_dir / "review" / "blocked_items.json").exists()


def test_review_merge_command_creates_review_merge_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["review-merge", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])

    assert exit_code == 0
    assert (run_dir / "review_merge" / "release_ready_items.json").exists()
    assert (run_dir / "review_merge" / "unresolved_items.json").exists()
    assert (run_dir / "review_merge" / "rejected_items.json").exists()
    assert (run_dir / "review_merge" / "decision_audit.json").exists()


def test_unknown_profile_fails(capsys) -> None:
    exit_code = main(["build-release", "--profile", "missing_profile", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"


def test_summarize_run_command_outputs_json(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    release_summary = json.loads((Path(payload["run_dir"]) / "build_release" / "release_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0

    exit_code = main(["summarize-run", "--run-dir", payload["run_dir"], "--format", "json"])
    summary = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert summary["latest_stage"] == "build-release"
    assert summary["counts"]["release_ready_count"] == release_summary["release_ready_count"]
    assert summary["counts"]["review_required_count"] == release_summary["review_required_count"]


def test_summarize_run_command_outputs_markdown(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    release_summary = json.loads((Path(payload["run_dir"]) / "build_release" / "release_summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0

    exit_code = main(["summarize-run", "--run-dir", payload["run_dir"], "--format", "markdown"])
    markdown = capsys.readouterr().out

    assert exit_code == 0
    assert "# hocrgen run summary" in markdown
    assert "Release-ready items" in markdown
    assert f"`{release_summary['release_ready_count']}`" in markdown


def test_build_release_can_resume_from_prior_run_dir(tmp_path: Path, capsys) -> None:
    initial_workdir = tmp_path / "initial"
    resumed_workdir = tmp_path / "resumed"
    exit_code = main(["policy-filter", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(initial_workdir)])
    initial_payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(resumed_workdir),
            "--resume-run-dir",
            initial_payload["run_dir"],
        ]
    )
    resumed_payload = json.loads(capsys.readouterr().out)
    resumed_run_dir = Path(resumed_payload["run_dir"])
    release_summary = json.loads((resumed_run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))
    original_release_summary = json.loads((Path(initial_payload["run_dir"]) / "policy_filter" / "summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert release_summary["accepted_count"] == original_release_summary["accepted_count"]
    assert release_summary["release_ready_count"] > 0


def test_resume_run_dir_rejects_profile_mismatch(tmp_path: Path, capsys) -> None:
    exit_code = main(["policy-filter", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "initial")])
    initial_payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_review_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "resumed"),
            "--resume-run-dir",
            initial_payload["run_dir"],
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "profile mismatch" in payload["error"]


def test_resume_run_dir_rejects_missing_required_manifests(tmp_path: Path, capsys) -> None:
    exit_code = main(["policy-filter", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "initial")])
    initial_payload = json.loads(capsys.readouterr().out)
    initial_run_dir = Path(initial_payload["run_dir"])
    (initial_run_dir / "policy_filter" / "accepted_items.json").unlink()

    assert exit_code == 0

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "resumed"),
            "--resume-run-dir",
            str(initial_run_dir),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "missing required" in payload["error"]


def test_resume_run_dir_rejects_target_stage_already_completed(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "initial")])
    initial_payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "resumed"),
            "--resume-run-dir",
            initial_payload["run_dir"],
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "already reached or passed target stage" in payload["error"]
