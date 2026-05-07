from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root
from hocrgen.config.models import ReportingPathConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.package.common import verify_checksum_manifest, write_release_archive
from hocrgen.package.public_beta import _blocker_closure_plan, _takedown_blocker_action, _takedown_gate


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
    assert report["planning_notation"] == "F5b"
    assert report["current_planning_notation"] == "F5c"
    assert report["readiness_contract_notation"] == "F5a"
    assert report["valid_statuses"] == ["pass", "blocked"]
    assert report["readiness_status"] == "blocked"
    assert report["publication_allowed"] is False
    assert set(report["blocked_gate_ids"]) >= {"synthetic_target_scale", "benchmark_references", "takedown_removal"}
    assert {gate["status"] for gate in report["gates"]} <= {"pass", "blocked"}
    synthetic_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "synthetic_target_scale")
    assert "larger validated batch" in synthetic_gate["rationale"]
    takedown_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "takedown_removal")
    assert takedown_gate["status"] == "blocked"
    assert "no repo-configured private reporting path" in takedown_gate["rationale"]
    assert "Enable GitHub private vulnerability reporting" in takedown_gate["rationale"]
    assert closure_plan["planning_notation"] == "F5c"
    assert closure_plan["source_readiness_report"] == "manifests/public_beta_readiness_report.json"
    assert closure_plan["readiness_status"] == "blocked"
    assert closure_plan["summary"]["external_input_dependent"] >= 1
    assert closure_plan["summary"]["repo_owned_immediately_actionable"] >= 1
    blockers_by_gate = {blocker["gate_id"]: blocker for blocker in closure_plan["blockers"]}
    assert blockers_by_gate["synthetic_target_scale"]["category"] == "external_input_dependent"
    assert blockers_by_gate["synthetic_target_scale"]["closure_state"] == "requires_external_input"
    assert blockers_by_gate["synthetic_target_scale"]["blocks_publication"] is True
    assert blockers_by_gate["takedown_removal"]["category"] == "repo_owned_immediately_actionable"
    assert blockers_by_gate["takedown_removal"]["closure_state"] == "requires_operator_action"
    assert "Enable GitHub private vulnerability reporting" in blockers_by_gate["takedown_removal"]["required_action"]
    assert closure_plan["known_hard_blockers"][0]["gate_id"] == "synthetic_target_scale"
    assert closure_plan["known_hard_blockers"][0]["do_not_relax"] is True
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
        "manifests/archive_manifest.json",
        "manifests/release_record.json",
        "manifests/release_summary.json",
        "docs/DATASET_CARD.md",
        "docs/PROVENANCE.md",
    ]:
        assert required_path in entries_by_path
        assert entries_by_path[required_path]["sha256"] == _sha256(output_dir / required_path)

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


def test_export_public_beta_takedown_gate_passes_when_private_reporting_path_is_configured(
    tmp_path: Path,
    capsys,
) -> None:
    config_root = _fixture_config_root(tmp_path)
    public_beta_config = config_root / "public_beta.yaml"
    public_beta_config.write_text(
        public_beta_config.read_text(encoding="utf-8").replace(
            "configured: false\n"
            "  required_operator_action: Enable GitHub private vulnerability reporting for HeOCR/hocrgen or replace this with a configured maintainer-private reporting channel before public beta publication.\n",
            "configured: true\n"
            "  verified_at: '2026-05-07'\n"
            "  verification_method: github_repository_security_settings\n"
            "  verified_by: test-maintainer\n",
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
    takedown_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "takedown_removal")
    synthetic_gate = next(gate for gate in report["gates"] if gate["gate_id"] == "synthetic_target_scale")

    assert takedown_gate["status"] == "pass"
    assert "configured public and private" in takedown_gate["rationale"]
    assert "takedown_removal" not in {blocker["gate_id"] for blocker in closure_plan["blockers"]}
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
        public_beta_config.read_text(encoding="utf-8").replace("configured: false", "configured: true"),
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

    with pytest.raises(StageExecutionError, match="has no F5c closure metadata"):
        _blocker_closure_plan(readiness_report=readiness_report, takedown_validation={})


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
