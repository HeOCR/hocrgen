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
    assert (run_dir / "build_release" / "release_summary.json").exists()


def test_unknown_profile_fails(capsys) -> None:
    exit_code = main(["build-release", "--profile", "missing_profile", "--dry-run"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["status"] == "error"
