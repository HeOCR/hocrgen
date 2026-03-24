from __future__ import annotations

import json
from pathlib import Path

from hocrgen.cli import main


def test_config_validate_command_succeeds(capsys) -> None:
    exit_code = main(["config", "validate"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["source_count"] >= 1


def test_stage_command_emits_run_artifacts(tmp_path: Path, capsys) -> None:
    exit_code = main(["discover", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    run_dir = Path(payload["run_dir"])
    summary_path = Path(payload["summary_path"])

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert run_dir.exists()
    assert (run_dir / "run.json").exists()
    assert (run_dir / "discover" / "summary.json").exists()
    assert (run_dir / "discover" / "candidates.json").exists()
    assert summary_path.exists()


def test_unknown_profile_fails(capsys) -> None:
    exit_code = main(["build-release", "--profile", "missing_profile", "--dry-run"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 1
    assert payload["status"] == "error"
