from __future__ import annotations

from pathlib import Path

from hocrgen.core.context import RunContext


def test_stage_dir_maps_review_export_aliases() -> None:
    context = RunContext(
        run_id="run-id",
        profile_id="profile",
        dry_run=True,
        work_root=Path("/tmp/work"),
        run_dir=Path("/tmp/work/runs/run-id"),
        log_dir=Path("/tmp/work/runs/run-id/logs"),
        created_at="2026-04-07T00:00:00Z",
    )

    assert context.stage_dir("review-export") == Path("/tmp/work/runs/run-id/review")
    assert context.stage_dir("review_export") == Path("/tmp/work/runs/run-id/review")
    assert context.stage_dir("privacy-scan") == Path("/tmp/work/runs/run-id/privacy_scan")
