from __future__ import annotations

import json
from pathlib import Path

from hocrgen.cli import main


def test_build_release_writes_release_summary(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])

    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    release_summary = run_dir / "build_release" / "release_summary.json"
    stage_summary = json.loads((run_dir / "build_release" / "summary.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert release_summary.exists()
    assert stage_summary["status"] == "scaffolded"
    assert stage_summary["release_summary"] == "build_release/release_summary.json"
