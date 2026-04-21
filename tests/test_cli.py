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
