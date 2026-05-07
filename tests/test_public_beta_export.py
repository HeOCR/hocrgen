from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

import hocrgen.package.public_beta as public_beta
from hocrgen.cli import main
from hocrgen.config.loader import default_config_root
from hocrgen.config.models import PrivateReportingPathConfig, ReportingPathConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.package.common import verify_checksum_manifest, write_release_archive
from hocrgen.package.public_beta import (
    _benchmark_reference_closure_entry,
    _benchmark_reference_gate,
    _benchmark_reference_item_required_action,
    _blocked_gate_ids_by_closure_category,
    _blocker_closure_plan,
    _stabilize_public_beta_readiness_artifacts,
    _takedown_blocker_action,
    _takedown_gate,
    _validate_takedown_workflow,
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


def _load_public_beta_config(config_root: Path) -> dict:
    return yaml.safe_load((config_root / "public_beta.yaml").read_text(encoding="utf-8"))


def _write_public_beta_config(config_root: Path, payload: dict) -> None:
    (config_root / "public_beta.yaml").write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_export_public_beta_creates_blocked_readiness_handoff(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "exports" / "public-beta-v0"

    exit_code = main(
        [
            "export-public-beta",
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
    assert payload["stage"] == "export-public-beta"
    assert payload["readiness_status"] == "blocked"
    assert payload["publication_allowed"] is False
    assert (output_dir / "data").exists()
    assert (output_dir / "docs" / "DATASET_CARD.md").exists()
    assert not (output_dir / "manifests" / "publication_report.json").exists()

    report = json.loads((output_dir / "manifests" / "public_beta_readiness_report.json").read_text(encoding="utf-8"))
    closure_plan = json.loads(
        (output_dir / "manifests" / "public_beta_blocker_closure_plan.json").read_text(encoding="utf-8")
    )
    repo_owned_report = json.loads(
        (output_dir / "manifests" / "public_beta_repo_owned_blocker_report.json").read_text(encoding="utf-8")
    )
    assert report["planning_notation"] == "F5b"
    assert report["current_planning_notation"] == "F6c"
    assert report["readiness_contract_notation"] == "F5a"
    assert report["valid_statuses"] == ["pass", "blocked"]
    assert report["readiness_status"] == "blocked"
    assert report["publication_allowed"] is False
    assert report["blocked_gate_ids"] == [
        "source_depth_composition",
        "synthetic_target_scale",
        "privacy_review",
        "benchmark_references",
    ]
    assert {gate["status"] for gate in report["gates"]} <= {"pass", "blocked"}
    synthetic_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "synthetic_target_scale")
    assert "larger validated batch" in synthetic_gate["rationale"]
    takedown_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "takedown_removal")
    assert takedown_gate["status"] == "pass"
    assert "configured public and private" in takedown_gate["rationale"]
    assert closure_plan["planning_notation"] == "F6c"
    assert closure_plan["source_readiness_report"] == "manifests/public_beta_readiness_report.json"
    assert closure_plan["readiness_status"] == "blocked"
    assert closure_plan["summary"]["external_input_dependent"] == 2
    assert closure_plan["summary"]["repo_owned_immediately_actionable"] == 2
    blockers_by_gate = {blocker["gate_id"]: blocker for blocker in closure_plan["blockers"]}
    assert blockers_by_gate["source_depth_composition"]["category"] == "external_input_dependent"
    assert blockers_by_gate["synthetic_target_scale"]["category"] == "external_input_dependent"
    assert blockers_by_gate["synthetic_target_scale"]["closure_state"] == "requires_external_input"
    assert blockers_by_gate["synthetic_target_scale"]["blocks_publication"] is True
    assert blockers_by_gate["privacy_review"]["category"] == "repo_owned_immediately_actionable"
    assert blockers_by_gate["benchmark_references"]["category"] == "repo_owned_immediately_actionable"
    assert "takedown_removal" not in blockers_by_gate
    assert closure_plan["known_hard_blockers"][0]["gate_id"] == "synthetic_target_scale"
    assert closure_plan["known_hard_blockers"][0]["do_not_relax"] is True
    assert repo_owned_report["planning_notation"] == "F6c"
    assert repo_owned_report["repo_owned_status"] == "blocked"
    assert repo_owned_report["repo_owned_blocked_gate_ids"] == [
        "privacy_review",
        "benchmark_references",
    ]
    assert repo_owned_report["external_input_dependent_blocked_gate_ids"] == [
        "source_depth_composition",
        "synthetic_target_scale",
    ]
    repo_entries = {entry["gate_id"]: entry for entry in repo_owned_report["entries"]}
    assert repo_entries["privacy_review"]["counts"]["review_required"] == 1
    assert repo_entries["privacy_review"]["counts"]["blocked"] == 0
    assert repo_entries["privacy_review"]["counts"]["suggested_decision"] == {
        "needs_classification_review": 1,
    }
    assert repo_entries["benchmark_references"]["counts"]["reference_ready"] == 1
    assert repo_entries["benchmark_references"]["counts"]["blocked_or_draft"] == 2
    assert repo_entries["benchmark_references"]["f6c_assessment"] == {
        "planning_notation": "F6c",
        "assessment_status": "blocked_partial_or_unavailable_reference_evidence",
        "closure_state": "requires_reviewed_or_adjudicated_reference_evidence",
        "readiness_contract": (
            "Every selected benchmark item must have reviewed/adjudicated reference evidence and coherent "
            "versioning before benchmark-reference readiness can pass."
        ),
        "selected_benchmark_item_count": 3,
        "reviewed_adjudicated_item_count": 1,
        "unresolved_item_count": 2,
        "versioning_status": "ok",
        "limitation_disclosure": (
            "1 / 3 selected benchmark item(s) have reviewed/adjudicated references; "
            "2 item(s) remain draft, unavailable, blocked, or unadjudicated"
        ),
        "blocked_gate_preserved": True,
    }
    assert [item["item_id"] for item in repo_entries["benchmark_references"]["ready_items"]] == [
        "nli_any_use_permitted:nli-ms-seed-006",
    ]
    unresolved_by_id = {item["item_id"]: item for item in repo_entries["benchmark_references"]["unresolved_items"]}
    assert unresolved_by_id["pinkas_open:pinkas-ledger-001"]["public_reference_status"] == "draft"
    assert unresolved_by_id["project_synthetic:synthetic-0"]["public_reference_status"] == "not_available"
    assert repo_entries["takedown_removal"]["status"] == "pass"
    assert repo_entries["takedown_removal"]["required_action"] == (
        "No takedown/private reporting action remains for current public beta governance config."
    )
    assert repo_entries["takedown_removal"]["configured_private_reporting_path"] is True
    assert repo_entries["takedown_removal"]["repository_check"] == {
        "checked_at": "2026-05-07",
        "method": "gh_api_private_vulnerability_reporting",
        "result": "enabled",
    }
    assert repo_entries["takedown_removal"]["verification"]["verified_at"] == "2026-05-07"
    assert repo_entries["takedown_removal"]["verification"]["method"] == "github_repository_security_settings"
    assert repo_entries["takedown_removal"]["verification"]["verified_by"] == (
        "authenticated_gh_api_repo_settings_check"
    )
    assert repo_entries["takedown_removal"]["verification"]["valid_until"] == "2026-06-06"
    assert repo_entries["takedown_removal"]["verification"]["freshness_status"] == "pass"
    assert str(output_dir.resolve()) not in json.dumps(repo_owned_report)
    for gate in report["gates"]:
        assert set(gate) == {"gate_id", "status", "evidence_paths", "rationale"}
        assert gate["evidence_paths"]

    release_record = json.loads((output_dir / "manifests" / "release_record.json").read_text(encoding="utf-8"))
    release_summary = json.loads((output_dir / "manifests" / "release_summary.json").read_text(encoding="utf-8"))
    handoff = (output_dir / "docs" / "HANDOFF.md").read_text(encoding="utf-8")
    assert release_record["release_kind"] == "public_beta"
    assert release_record["readiness_status"] == "blocked"
    assert release_record["publication_allowed"] is False
    assert release_summary["publication_report_emitted"] is False
    assert "repository sync, upload, release tagging, or publication report emission" in handoff
    assert "GitHub private vulnerability reporting for HeOCR/hocrgen" in handoff
    assert "Private reporting repository check: enabled" in handoff
    assert (
        "Private reporting verification: github_repository_security_settings by "
        "authenticated_gh_api_repo_settings_check at 2026-05-07"
    ) in handoff
    assert "Private reporting verification valid until: 2026-06-06" in handoff
    assert str(output_dir.resolve()) not in handoff

    summarize_exit = main(["summarize-run", "--run-dir", payload["run_dir"]])
    summary_payload = json.loads(capsys.readouterr().out)
    assert summarize_exit == 0
    assert summary_payload["latest_stage"] == "export-public-beta"


def test_export_public_beta_checksum_manifest_covers_public_payloads_and_archive(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "exports" / "public-beta-v0"

    assert main(
        [
            "export-public-beta",
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
    ) == 0
    capsys.readouterr()

    checksum_manifest = json.loads((output_dir / "manifests" / "checksum_manifest.json").read_text(encoding="utf-8"))
    archive_manifest = json.loads((output_dir / "manifests" / "archive_manifest.json").read_text(encoding="utf-8"))
    report = json.loads((output_dir / "manifests" / "public_beta_readiness_report.json").read_text(encoding="utf-8"))
    categories = {entry["category"] for entry in checksum_manifest["entries"]}
    assert {"payload_asset", "public_manifest", "public_doc", "benchmark_reference_child_file", "archive"} <= categories
    assert checksum_manifest["verification"]["status"] == "pass"
    assert checksum_manifest["entry_count"] == len(checksum_manifest["entries"])
    portability_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "portability_checksums_archives")
    assert portability_gate["status"] == checksum_manifest["verification"]["status"]

    entries_by_path = {entry["path"]: entry for entry in checksum_manifest["entries"]}
    for required_path in [
        "manifests/public_beta_readiness_report.json",
        "manifests/public_beta_blocker_closure_plan.json",
        "manifests/public_beta_repo_owned_blocker_report.json",
        "manifests/archive_manifest.json",
        "manifests/release_record.json",
        "manifests/release_summary.json",
        "docs/DATASET_CARD.md",
        "docs/PROVENANCE.md",
    ]:
        assert required_path in entries_by_path
        assert entries_by_path[required_path]["sha256"] == _sha256(output_dir / required_path)
    assert entries_by_path["manifests/public_beta_repo_owned_blocker_report.json"]["sha256"] == _sha256(
        output_dir / "manifests" / "public_beta_repo_owned_blocker_report.json"
    )

    archive_record = archive_manifest["archives"][0]
    archive_path = output_dir / archive_record["archive_path"]
    assert archive_record["sha256"] == _sha256(archive_path)
    assert entries_by_path[archive_record["archive_path"]]["sha256"] == archive_record["sha256"]


def test_export_public_beta_archive_is_rooted_at_versioned_release_dir(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "exports" / "public-beta-v0"

    assert main(
        [
            "export-public-beta",
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
    ) == 0
    capsys.readouterr()

    archive_manifest = json.loads((output_dir / "manifests" / "archive_manifest.json").read_text(encoding="utf-8"))
    archive_record = archive_manifest["archives"][0]
    assert archive_record["release_root"] == "public-beta-v0"
    assert archive_record["included_top_level_paths"] == ["data", "docs", "manifests", "references"]
    assert set(archive_record["excluded_paths"]) >= {
        "archives/",
        "manifests/archive_manifest.json",
        "manifests/checksum_manifest.json",
    }
    assert set(archive_manifest["excluded_paths"]) == {
        "archives/",
        "manifests/archive_manifest.json",
        "manifests/checksum_manifest.json",
    }

    with tarfile.open(output_dir / archive_record["archive_path"], "r:gz") as archive:
        names = archive.getnames()
    assert names
    assert all(name == "public-beta-v0" or name.startswith("public-beta-v0/") for name in names)
    assert not any("/../" in f"/{name}/" or name.startswith("/") for name in names)
    assert any(name.startswith("public-beta-v0/data/") for name in names)
    assert any(name.startswith("public-beta-v0/docs/") for name in names)
    assert any(name.startswith("public-beta-v0/manifests/") for name in names)
    assert "public-beta-v0/manifests/public_beta_readiness_report.json" in names
    assert "public-beta-v0/manifests/public_beta_blocker_closure_plan.json" in names
    assert "public-beta-v0/manifests/public_beta_repo_owned_blocker_report.json" in names
    assert "public-beta-v0/manifests/release_record.json" in names
    assert "public-beta-v0/manifests/release_summary.json" in names
    assert "public-beta-v0/manifests/source_depth_feasibility.json" in names
    assert "public-beta-v0/manifests/archive_manifest.json" not in names
    assert "public-beta-v0/manifests/checksum_manifest.json" not in names
    assert not any(name.startswith("public-beta-v0/archives/") for name in names)


def test_export_public_beta_rejects_output_dir_that_does_not_match_version(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "exports" / "not-public-beta-v0"

    exit_code = main(
        [
            "export-public-beta",
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
    assert payload["status"] == "error"
    assert "output directory must be named public-beta-v0" in payload["error"]
    assert not output_dir.exists()


def test_write_release_archive_records_the_tar_root_name(tmp_path: Path) -> None:
    release_root = tmp_path / "custom-output-name"
    (release_root / "docs").mkdir(parents=True)
    (release_root / "docs" / "README.md").write_text("# release\n", encoding="utf-8")

    archive_record = write_release_archive(release_root=release_root, version="public-beta-v0")

    assert archive_record["release_root"] == "public-beta-v0"
    with tarfile.open(release_root / archive_record["archive_path"], "r:gz") as archive:
        names = archive.getnames()
    assert "public-beta-v0/docs/README.md" in names
    assert not any(name.startswith("custom-output-name/") for name in names)


def test_verify_checksum_manifest_rejects_paths_that_escape_release_root(tmp_path: Path) -> None:
    release_root = tmp_path / "release"
    release_root.mkdir()
    inside = release_root / "inside.txt"
    inside.write_text("inside\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    checksum_manifest = {
        "entries": [
            {"path": "inside.txt", "sha256": _sha256(inside)},
            {"path": "../outside.txt", "sha256": _sha256(outside)},
            {"path": str(outside.resolve()), "sha256": _sha256(outside)},
        ]
    }

    verification = verify_checksum_manifest(release_root, checksum_manifest)

    assert verification["status"] == "blocked"
    assert verification["checked_count"] == 3
    assert verification["failure_count"] == 2
    assert verification["failures"] == [
        {"path": "../outside.txt", "reason": "unsafe_path"},
        {"path": str(outside.resolve()), "reason": "unsafe_path"},
    ]


def test_public_beta_command_does_not_change_alpha_or_synthetic_export_cli(tmp_path: Path, capsys) -> None:
    config_root = _fixture_config_root(tmp_path)

    alpha_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "alpha-work"),
            "--output-dir",
            str(tmp_path / "exports" / "alpha-v0"),
        ]
    )
    alpha_payload = json.loads(capsys.readouterr().out)
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
            str(tmp_path / "exports" / "synth-alpha-v0"),
        ]
    )
    synthetic_payload = json.loads(capsys.readouterr().out)

    assert alpha_exit == 0
    assert alpha_payload["stage"] == "export-alpha"
    assert (Path(alpha_payload["export_dir"]) / "docs" / "HANDOFF.md").exists()
    assert synthetic_exit == 0
    assert synthetic_payload["stage"] == "export-synthetic"
    assert synthetic_payload["synthetic_only"] is True


def test_export_public_beta_takedown_gate_blocks_when_private_reporting_path_is_unconfigured(
    tmp_path: Path,
    capsys,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    public_beta_payload = _load_public_beta_config(config_root)
    public_beta_payload["private_reporting_path"].update(
        {
            "configured": False,
            "repository_check_result": "disabled",
            "required_operator_action": (
                "Enable GitHub private vulnerability reporting for HeOCR/hocrgen or replace this with a "
                "configured maintainer-private reporting channel before public beta publication."
            ),
        }
    )
    for key in ("verified_at", "verification_method", "verified_by", "verification_valid_until"):
        public_beta_payload["private_reporting_path"].pop(key, None)
    _write_public_beta_config(config_root, public_beta_payload)
    assert _load_public_beta_config(config_root)["private_reporting_path"]["configured"] is False
    output_dir = tmp_path / "exports" / "public-beta-v0"

    assert main(
        [
            "export-public-beta",
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
    ) == 0
    capsys.readouterr()

    report = json.loads((output_dir / "manifests" / "public_beta_readiness_report.json").read_text(encoding="utf-8"))
    closure_plan = json.loads(
        (output_dir / "manifests" / "public_beta_blocker_closure_plan.json").read_text(encoding="utf-8")
    )
    takedown_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "takedown_removal")
    synthetic_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "synthetic_target_scale")

    assert takedown_gate["status"] == "blocked"
    assert "no repo-configured private reporting path" in takedown_gate["rationale"]
    assert "private reporting is disabled" in takedown_gate["rationale"]
    assert "takedown_removal" in {blocker["gate_id"] for blocker in closure_plan["blockers"]}
    assert synthetic_gate["status"] == "blocked"
    assert "2 / 80" in synthetic_gate["rationale"]
    assert report["readiness_status"] == "blocked"


def test_export_public_beta_rejects_unverified_private_reporting_path(
    tmp_path: Path,
    capsys,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    public_beta_config = config_root / "public_beta.yaml"
    public_beta_config.write_text(
        public_beta_config.read_text(encoding="utf-8")
        .replace("verified_at: '2026-05-07'\n", "")
        .replace("  verification_method: github_repository_security_settings\n", "")
        .replace("  verified_by: authenticated_gh_api_repo_settings_check\n", "")
        .replace("  verification_valid_until: '2026-06-06'\n", "")
        .replace(
            "  required_operator_action: Enable GitHub private vulnerability reporting for HeOCR/hocrgen or replace this with a configured maintainer-private reporting channel before public beta publication.\n",
            "",
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "export-public-beta",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(tmp_path / "exports" / "public-beta-v0"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert "configured private reporting paths require verification metadata" in payload["error"]


def test_export_public_beta_takedown_gate_blocks_when_verification_is_stale(
    tmp_path: Path,
    capsys,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    public_beta_config = config_root / "public_beta.yaml"
    public_beta_config.write_text(
        public_beta_config.read_text(encoding="utf-8").replace(
            "verification_valid_until: '2026-06-06'",
            "verification_valid_until: '2000-01-01'",
        ),
        encoding="utf-8",
    )
    output_dir = tmp_path / "exports" / "public-beta-v0"

    assert main(
        [
            "export-public-beta",
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
    ) == 0
    capsys.readouterr()

    report = json.loads((output_dir / "manifests" / "public_beta_readiness_report.json").read_text(encoding="utf-8"))
    closure_plan = json.loads(
        (output_dir / "manifests" / "public_beta_blocker_closure_plan.json").read_text(encoding="utf-8")
    )
    repo_owned_report = json.loads(
        (output_dir / "manifests" / "public_beta_repo_owned_blocker_report.json").read_text(encoding="utf-8")
    )
    takedown_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "takedown_removal")
    takedown_blocker = next(blocker for blocker in closure_plan["blockers"] if blocker["gate_id"] == "takedown_removal")
    takedown_entry = next(entry for entry in repo_owned_report["entries"] if entry["gate_id"] == "takedown_removal")

    assert takedown_gate["status"] == "blocked"
    assert takedown_blocker["closure_state"] == "requires_repository_settings_reverification"
    assert "Refresh private reporting repository settings verification" in takedown_blocker["required_action"]
    assert takedown_entry["verification"]["freshness_status"] == "blocked"
    assert takedown_entry["verification"]["valid_until"] == "2000-01-01"


def test_takedown_validation_requires_configured_verification_docs(tmp_path: Path) -> None:
    for relative_path, text in {
        "docs/RELEASE_NOTES.md": (
            "Rights, privacy, source-owner, correction\n"
            "review/config/source-status changes\n"
            "GitHub private vulnerability reporting for HeOCR/hocrgen\n"
        ),
        "docs/DATASET_CARD.md": (
            "Takedown and Corrections\n"
            "GitHub public dataset issue\n"
            "GitHub private vulnerability reporting for HeOCR/hocrgen\n"
        ),
        "docs/HANDOFF.md": (
            "Stop Conditions\n"
            "Do not publish to HeOCR\n"
            "GitHub private vulnerability reporting for HeOCR/hocrgen\n"
        ),
        "manifests/release_diff.json": "{}\n",
    }.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    governance = SimpleNamespace(
        public_reporting_path=SimpleNamespace(
            id="github_public_dataset_issue",
            label="GitHub public dataset issue",
        ),
        private_reporting_path=SimpleNamespace(
            id="github_private_vulnerability_reporting",
            label="GitHub private vulnerability reporting for HeOCR/hocrgen",
            channel="github_private_vulnerability_reporting",
            configured=True,
            repository_check_at="2026-05-07",
            repository_check_method="gh_api_private_vulnerability_reporting",
            repository_check_result="enabled",
            verified_at="2026-05-07",
            verification_method="github_repository_security_settings",
            verified_by="authenticated_gh_api_repo_settings_check",
            verification_valid_until="2026-06-06",
            required_operator_action="",
        ),
    )

    validation = _validate_takedown_workflow(tmp_path, governance)

    assert validation["status"] == "blocked"
    incomplete_paths = {entry["path"]: entry["missing_fragments"] for entry in validation["incomplete"]}
    assert "Private reporting repository check: enabled" in "\n".join(incomplete_paths["docs/HANDOFF.md"])
    assert "Private reporting verification: github_repository_security_settings" in "\n".join(
        incomplete_paths["docs/HANDOFF.md"]
    )
    assert "Private reporting verification valid until: 2026-06-06." in incomplete_paths["docs/HANDOFF.md"]


def test_public_beta_blocker_closure_plan_fails_closed_for_unmapped_blocked_gate() -> None:
    readiness_report = {
        "readiness_status": "blocked",
        "publication_allowed": False,
        "gates": [
            {
                "gate_id": "new_external_gate",
                "status": "blocked",
                "evidence_paths": ["manifests/new_external_gate.json"],
                "rationale": "A future gate must declare closure metadata.",
            }
        ],
    }

    with pytest.raises(StageExecutionError, match="has no F5d closure metadata"):
        _blocker_closure_plan(readiness_report=readiness_report, takedown_validation={})


def test_external_input_dependent_blocked_gates_are_category_derived(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        public_beta.BLOCKER_CLOSURE_ACTIONS,
        "future_repo_owned_gate",
        {
            "category": "repo_owned_immediately_actionable",
            "owner_scope": "hocrgen future repo-owned work",
            "closure_state": "requires_repo_pr_or_review_update",
            "required_action": "Close the future repo-owned blocker in hocrgen.",
            "closure_artifacts": ["manifests/public_beta_repo_owned_blocker_report.json"],
        },
    )
    readiness_report = {
        "gates": [
            {"gate_id": "source_depth_composition", "status": "blocked"},
            {"gate_id": "future_repo_owned_gate", "status": "blocked"},
            {"gate_id": "synthetic_target_scale", "status": "pass"},
        ]
    }

    assert _blocked_gate_ids_by_closure_category(
        readiness_report=readiness_report,
        takedown_validation={},
        category="external_input_dependent",
    ) == ["source_depth_composition"]


def test_public_beta_readiness_artifacts_rewrite_until_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    updated_report = {"readiness_status": "blocked", "iteration": 1, "gates": []}
    recomputed_reports = iter([updated_report, updated_report])
    written_reports: list[dict[str, object]] = []

    monkeypatch.setattr(public_beta, "_write_public_beta_blocker_outputs", lambda **_: None)
    monkeypatch.setattr(public_beta, "write_release_archive", lambda **_: {"archive_path": "archives/test.tar.gz"})
    monkeypatch.setattr(public_beta, "build_checksum_manifest", lambda **_: {"entries": []})
    monkeypatch.setattr(
        public_beta,
        "verify_checksum_manifest",
        lambda *_: {"status": "pass", "checked_count": 0, "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(public_beta, "_readiness_report", lambda **_: next(recomputed_reports))
    monkeypatch.setattr(
        public_beta,
        "_write_readiness_outputs",
        lambda **kwargs: written_reports.append(kwargs["readiness_report"]),
    )

    readiness_report, archive_record = _stabilize_public_beta_readiness_artifacts(
        export_dir=tmp_path,
        manifests_dir=manifests_dir,
        version="public-beta-v0",
        profile_id="profile_open_v1",
        release_record=SimpleNamespace(),
        release_summary={},
        build_release_summary={},
        source_depth_feasibility={},
        leakage_report={},
        selected_benchmark_reference_status=None,
        benchmark_reference_versioning=None,
        docs_validation={},
        takedown_validation={},
        review_required_items=[],
        blocked_items=[],
        selected_review_queue=[],
        readiness_report={"readiness_status": "blocked", "iteration": 0, "gates": []},
    )

    assert readiness_report == updated_report
    assert archive_record == {"archive_path": "archives/test.tar.gz"}
    assert written_reports == [updated_report]


def test_public_beta_readiness_artifacts_fail_when_not_stable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    reports = iter(
        [
            {"readiness_status": "blocked", "iteration": 1, "gates": []},
            {"readiness_status": "blocked", "iteration": 2, "gates": []},
            {"readiness_status": "blocked", "iteration": 3, "gates": []},
        ]
    )

    monkeypatch.setattr(public_beta, "_write_public_beta_blocker_outputs", lambda **_: None)
    monkeypatch.setattr(public_beta, "write_release_archive", lambda **_: {"archive_path": "archives/test.tar.gz"})
    monkeypatch.setattr(public_beta, "build_checksum_manifest", lambda **_: {"entries": []})
    monkeypatch.setattr(
        public_beta,
        "verify_checksum_manifest",
        lambda *_: {"status": "pass", "checked_count": 0, "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(public_beta, "_readiness_report", lambda **_: next(reports))
    monkeypatch.setattr(public_beta, "_write_readiness_outputs", lambda **_: None)

    with pytest.raises(StageExecutionError, match="did not stabilize"):
        _stabilize_public_beta_readiness_artifacts(
            export_dir=tmp_path,
            manifests_dir=manifests_dir,
            version="public-beta-v0",
            profile_id="profile_open_v1",
            release_record=SimpleNamespace(),
            release_summary={},
            build_release_summary={},
            source_depth_feasibility={},
            leakage_report={},
            selected_benchmark_reference_status=None,
            benchmark_reference_versioning=None,
            docs_validation={},
            takedown_validation={},
            review_required_items=[],
            blocked_items=[],
            selected_review_queue=[],
            readiness_report={"readiness_status": "blocked", "iteration": 0, "gates": []},
        )


def test_public_beta_readiness_artifacts_fail_when_archive_does_not_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()
    stable_report = {"readiness_status": "blocked", "iteration": 0, "gates": []}

    monkeypatch.setattr(public_beta, "_write_public_beta_blocker_outputs", lambda **_: None)
    monkeypatch.setattr(public_beta, "write_release_archive", lambda **_: None)
    monkeypatch.setattr(public_beta, "build_checksum_manifest", lambda **_: {"entries": []})
    monkeypatch.setattr(
        public_beta,
        "verify_checksum_manifest",
        lambda *_: {"status": "pass", "checked_count": 0, "failure_count": 0, "failures": []},
    )
    monkeypatch.setattr(public_beta, "_readiness_report", lambda **_: stable_report)

    with pytest.raises(StageExecutionError, match="archive generation did not run"):
        _stabilize_public_beta_readiness_artifacts(
            export_dir=tmp_path,
            manifests_dir=manifests_dir,
            version="public-beta-v0",
            profile_id="profile_open_v1",
            release_record=SimpleNamespace(),
            release_summary={},
            build_release_summary={},
            source_depth_feasibility={},
            leakage_report={},
            selected_benchmark_reference_status=None,
            benchmark_reference_versioning=None,
            docs_validation={},
            takedown_validation={},
            review_required_items=[],
            blocked_items=[],
            selected_review_queue=[],
            readiness_report=stable_report,
        )


def test_public_beta_takedown_action_describes_configured_doc_failures() -> None:
    takedown_validation = {
        "configured_private_reporting_path": True,
        "missing": ["docs/HANDOFF.md"],
        "incomplete": [
            {
                "path": "docs/DATASET_CARD.md",
                "missing_fragments": ["GitHub private vulnerability reporting for HeOCR/hocrgen"],
            }
        ],
        "verification": {"freshness_status": "pass"},
        "required_operator_action": "",
        "status": "blocked",
    }

    action = _takedown_blocker_action(takedown_validation)
    gate = _takedown_gate(takedown_validation)

    assert action["closure_state"] == "requires_repo_pr_or_doc_update"
    assert "Repair takedown workflow documentation" in action["required_action"]
    assert "missing evidence docs: docs/HANDOFF.md" in action["required_action"]
    assert "docs/DATASET_CARD.md missing GitHub private vulnerability reporting" in action["required_action"]
    assert "configured private reporting path" in gate["rationale"]
    assert "no repo-configured private reporting path" not in gate["rationale"]
    assert "required operator action: ." not in gate["rationale"]


def test_reporting_path_requires_operator_action_when_unconfigured() -> None:
    with pytest.raises(ValidationError, match="required_operator_action is required"):
        ReportingPathConfig.model_validate(
            {
                "id": "private_contact",
                "label": "Private contact",
                "configured": False,
            }
        )


def test_private_reporting_path_requires_repository_check_timestamp_when_result_recorded() -> None:
    with pytest.raises(ValidationError, match="repository_check_at is required"):
        PrivateReportingPathConfig.model_validate(
            {
                "id": "github_private_vulnerability_reporting",
                "label": "GitHub private vulnerability reporting",
                "channel": "github_private_vulnerability_reporting",
                "configured": False,
                "required_operator_action": "Enable GitHub private vulnerability reporting.",
                "repository_check_method": "gh_api_private_vulnerability_reporting",
                "repository_check_result": "disabled",
            }
        )


def test_private_reporting_path_requires_repository_check_method_when_result_recorded() -> None:
    with pytest.raises(ValidationError, match="repository_check_method is required"):
        PrivateReportingPathConfig.model_validate(
            {
                "id": "github_private_vulnerability_reporting",
                "label": "GitHub private vulnerability reporting",
                "channel": "github_private_vulnerability_reporting",
                "configured": False,
                "required_operator_action": "Enable GitHub private vulnerability reporting.",
                "repository_check_at": "2026-05-07",
                "repository_check_result": "disabled",
            }
        )


@pytest.mark.parametrize("field_name", ["verified_at", "verification_valid_until", "repository_check_at"])
def test_private_reporting_path_requires_iso_date_metadata(field_name: str) -> None:
    payload = {
        "id": "github_private_vulnerability_reporting",
        "label": "GitHub private vulnerability reporting",
        "channel": "github_private_vulnerability_reporting",
        "configured": False,
        "required_operator_action": "Enable GitHub private vulnerability reporting.",
        field_name: "2026/05/07",
    }

    with pytest.raises(ValidationError, match=f"{field_name} must use YYYY-MM-DD format"):
        PrivateReportingPathConfig.model_validate(payload)


@pytest.mark.parametrize("repository_check_result", ["", "unknown", "disabled"])
def test_private_reporting_path_requires_enabled_repository_check_when_configured(
    repository_check_result: str,
) -> None:
    with pytest.raises(ValidationError, match="require an enabled repository check"):
        PrivateReportingPathConfig.model_validate(
            {
                "id": "github_private_vulnerability_reporting",
                "label": "GitHub private vulnerability reporting",
                "channel": "github_private_vulnerability_reporting",
                "url": "https://github.com/HeOCR/hocrgen/security/advisories/new",
                "configured": True,
                "verified_at": "2026-05-07",
                "verification_method": "github_repository_security_settings",
                "verified_by": "test-maintainer",
                "verification_valid_until": "2026-06-06",
                "repository_check_at": "2026-05-07",
                "repository_check_method": "gh_api_private_vulnerability_reporting",
                "repository_check_result": repository_check_result,
            }
        )


@pytest.mark.parametrize(
    ("item", "expected_fragment"),
    [
        (
            SimpleNamespace(public_reference_status="reviewed", adjudication_status="pending"),
            "Complete adjudication",
        ),
        (
            SimpleNamespace(public_reference_status="adjudicated", adjudication_status="needs_repair"),
            "Complete adjudication",
        ),
        (
            SimpleNamespace(public_reference_status="blocked", adjudication_status="adjudicated"),
            "Repair reference status semantics",
        ),
    ],
)
def test_benchmark_reference_required_action_covers_unready_status_semantics(
    item: SimpleNamespace,
    expected_fragment: str,
) -> None:
    assert expected_fragment in _benchmark_reference_item_required_action(item)


def test_benchmark_reference_gate_requires_all_selected_items_ready() -> None:
    partial_status = SimpleNamespace(
        counts={"reference_ready": 2, "blocked_or_draft": 0},
        items=[
            SimpleNamespace(
                item_id="item-reviewed",
                public_reference_status="reviewed",
                adjudication_status="adjudicated",
            ),
            SimpleNamespace(
                item_id="item-draft",
                public_reference_status="draft",
                adjudication_status="in_review",
            ),
        ],
    )

    gate = _benchmark_reference_gate(partial_status, {"status": "ok"})

    assert gate["status"] == "blocked"
    assert "1 / 2 selected benchmark item(s) are reviewed/adjudicated" in gate["rationale"]
    assert "1 item(s) remain draft, unavailable, blocked, or unadjudicated" in gate["rationale"]


def test_benchmark_reference_gate_passes_only_with_complete_reviewed_adjudicated_evidence() -> None:
    complete_status = SimpleNamespace(
        counts={"reference_ready": 2, "blocked_or_draft": 0},
        items=[
            SimpleNamespace(
                item_id="item-reviewed",
                public_reference_status="reviewed",
                adjudication_status="adjudicated",
            ),
            SimpleNamespace(
                item_id="item-adjudicated",
                public_reference_status="adjudicated",
                adjudication_status="adjudicated",
            ),
        ],
    )

    gate = _benchmark_reference_gate(complete_status, {"status": "ok"})

    assert gate["status"] == "pass"
    assert "all 2 selected benchmark item(s)" in gate["rationale"]


def test_benchmark_reference_closure_entry_reports_versioning_only_blocker() -> None:
    complete_status = SimpleNamespace(
        counts={"reference_ready": 2, "blocked_or_draft": 0},
        items=[
            SimpleNamespace(
                item_id="item-a",
                source_id="source-a",
                benchmark_split="train",
                public_reference_status="reviewed",
                adjudication_status="adjudicated",
                has_transcription_reference=True,
                layout_reference_count=1,
                reviewer_count=1,
            ),
            SimpleNamespace(
                item_id="item-b",
                source_id="source-b",
                benchmark_split="train",
                public_reference_status="adjudicated",
                adjudication_status="adjudicated",
                has_transcription_reference=True,
                layout_reference_count=0,
                reviewer_count=2,
            ),
        ],
    )
    gate = _benchmark_reference_gate(complete_status, {"status": "not_available"})

    entry = _benchmark_reference_closure_entry(gate, complete_status, {"status": "not_available"})

    assert gate["status"] == "blocked"
    assert entry["closure_state"] == "requires_coherent_reference_versioning"
    assert entry["unresolved_items"] == []
    assert [item["item_id"] for item in entry["ready_items"]] == ["item-a", "item-b"]
    assert entry["f6c_assessment"] == {
        "planning_notation": "F6c",
        "assessment_status": "blocked_versioning_incoherent",
        "closure_state": "requires_coherent_reference_versioning",
        "readiness_contract": (
            "Every selected benchmark item must have reviewed/adjudicated reference evidence and coherent "
            "versioning before benchmark-reference readiness can pass."
        ),
        "selected_benchmark_item_count": 2,
        "reviewed_adjudicated_item_count": 2,
        "unresolved_item_count": 0,
        "versioning_status": "not_available",
        "limitation_disclosure": (
            "All 2 selected benchmark item(s) have reviewed/adjudicated references, "
            "but benchmark-reference versioning status is not_available"
        ),
        "blocked_gate_preserved": True,
    }


def test_alpha_and_synthetic_exports_accept_config_root_without_public_beta_config(
    tmp_path: Path,
    capsys,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    (config_root / "public_beta.yaml").unlink()

    alpha_exit = main(
        [
            "export-alpha",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "alpha-work"),
            "--output-dir",
            str(tmp_path / "exports" / "alpha-v0"),
        ]
    )
    alpha_payload = json.loads(capsys.readouterr().out)
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
            str(tmp_path / "exports" / "synth-alpha-v0"),
        ]
    )
    synthetic_payload = json.loads(capsys.readouterr().out)

    assert alpha_exit == 0
    assert alpha_payload["stage"] == "export-alpha"
    assert synthetic_exit == 0
    assert synthetic_payload["stage"] == "export-synthetic"


@pytest.mark.parametrize(
    ("flag_args", "expected_flag"),
    [
        (["--source", "nli_any_use_permitted"], "--source"),
        (["--max-items", "1"], "--max-items"),
        (["--seed", "123"], "--seed"),
        (["--synthetic-template", "book_page"], "--synthetic-template"),
        (["--synthetic-recipe", "default"], "--synthetic-recipe"),
        (["--synthetic-degradation-preset", "clean"], "--synthetic-degradation-preset"),
    ],
)
def test_export_public_beta_rejects_partial_pipeline_flags(
    tmp_path: Path,
    capsys,
    flag_args: list[str],
    expected_flag: str,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    output_dir = tmp_path / "exports" / "public-beta-v0"

    exit_code = main(
        [
            "export-public-beta",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--config-root",
            str(config_root),
            "--workdir",
            str(tmp_path / "work"),
            "--output-dir",
            str(output_dir),
            *flag_args,
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"
    assert "full governed public beta candidate set" in payload["error"]
    assert expected_flag in payload["error"]
    assert not output_dir.exists()
