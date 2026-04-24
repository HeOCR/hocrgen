from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from hocrgen.cli import handle_stage, handle_summarize_run
from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.core.context import create_run_context
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.pipeline import PIPELINE_STAGES, execute_pipeline, write_run_metadata, write_run_summary
from hocrgen.runs import load_resumed_pipeline_state, render_run_summary_markdown, summarize_run


def _materialize_run(tmp_path: Path, latest_stage: str, profile_id: str = "profile_open_v1") -> Path:
    bundle = load_and_validate_bundle()
    context = create_run_context(profile_id, dry_run=True, workdir=tmp_path / latest_stage.replace("-", "_"))
    run_metadata = write_run_metadata(context)
    results = execute_pipeline(latest_stage, bundle, context, StageOptions())
    write_run_summary(
        context,
        latest_stage,
        [run_metadata, *(artifact for result in results for artifact in [result.summary_path, *result.extra_artifacts])],
    )
    return context.run_dir


def _write_run_files(
    run_dir: Path,
    *,
    latest_stage: str,
    profile_id: str = "profile_open_v1",
    artifacts: list[str] | None = None,
    stage_summaries: dict[str, dict[str, object]] | None = None,
) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "created_at": "2026-01-01T00:00:00Z",
                "dry_run": True,
                "profile_id": profile_id,
                "run_id": "run-1",
                "work_root": str(run_dir.parent),
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(
        json.dumps({"latest_stage": latest_stage, "artifacts": artifacts or []}),
        encoding="utf-8",
    )
    for stage, summary in (stage_summaries or {}).items():
        stage_dir = run_dir / stage.replace("-", "_")
        stage_dir.mkdir(parents=True, exist_ok=True)
        (stage_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return run_dir


def test_handle_stage_returns_error_when_pipeline_execution_fails(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def raise_stage_error(*args, **kwargs):
        raise StageExecutionError("boom")

    monkeypatch.setattr("hocrgen.cli.execute_pipeline", raise_stage_error)
    args = argparse.Namespace(
        profile="profile_open_v1",
        workdir=None,
        config_root=None,
        dry_run=True,
        source=None,
        max_items=None,
        seed=None,
        resume_run_dir=None,
        verbose=False,
        stage_name="build-release",
    )

    exit_code = handle_stage(args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["error"] == "boom"


def test_handle_stage_returns_error_when_resume_cannot_determine_next_stage(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    class DummyState:
        pass

    monkeypatch.setattr("hocrgen.cli.load_resumed_pipeline_state", lambda *_args: (DummyState(), "build-release"))
    args = argparse.Namespace(
        profile="profile_open_v1",
        workdir=None,
        config_root=None,
        dry_run=True,
        source=None,
        max_items=None,
        seed=None,
        resume_run_dir=Path("/tmp/run"),
        verbose=False,
        stage_name="export-alpha",
    )

    exit_code = handle_stage(args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "cannot determine the next stage" in payload["error"]


def test_handle_summarize_run_returns_error_when_summary_loading_fails(capsys) -> None:
    args = argparse.Namespace(run_dir=Path("/definitely/missing"), format="json")

    exit_code = handle_summarize_run(args)
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert "missing required run metadata" in payload["error"]


def test_execute_pipeline_rejects_unknown_start_stage(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    context = create_run_context("profile_open_v1", dry_run=True, workdir=tmp_path)

    with pytest.raises(StageExecutionError, match="unknown start stage: nope"):
        execute_pipeline("build-release", bundle, context, StageOptions(), start_stage="nope")


def test_summarize_run_rejects_unknown_latest_stage(tmp_path: Path) -> None:
    run_dir = _write_run_files(tmp_path / "run", latest_stage="mystery")

    with pytest.raises(StageExecutionError, match="unknown latest_stage"):
        summarize_run(run_dir)


def test_render_run_summary_markdown_includes_rejection_reasons_and_keeps_zero_counts(tmp_path: Path) -> None:
    markdown = render_run_summary_markdown(
        {
            "artifacts": [],
            "artifact_count": 0,
            "counts": {
                "accepted_count": 1,
                "qa_failed_count": 0,
                "rejection_reasons": {"unknown_rights": 2},
            },
            "created_at": "2026-01-01T00:00:00Z",
            "dry_run": True,
            "latest_stage": "policy-filter",
            "profile_id": "profile_open_v1",
            "run_dir": str(tmp_path / "run"),
            "run_id": "run-1",
            "stage_summaries": {},
            "warnings": [],
            "work_root": str(tmp_path),
        }
    )

    assert "Rights rejection reasons" in markdown
    assert "QA failures: `0`" in markdown
    assert "Retained after dedupe" not in markdown


def test_summarize_run_collects_review_warning_lines(tmp_path: Path) -> None:
    run_dir = _materialize_run(tmp_path, "build-release")
    summary = summarize_run(run_dir)

    assert any("require review" in warning for warning in summary["warnings"])


def test_summarize_run_collects_blocked_and_qa_failure_reason_warnings(tmp_path: Path) -> None:
    run_dir = _write_run_files(
        tmp_path / "run",
        latest_stage="build-release",
        artifacts=["build_release/source_stats.json", "build_release/release_summary.json"],
        stage_summaries={
            "build-release": {
                "source_stats": "build_release/source_stats.json",
                "release_summary": "build_release/release_summary.json",
            }
        },
    )
    build_release_dir = run_dir / "build_release"
    build_release_dir.mkdir(exist_ok=True)
    (build_release_dir / "source_stats.json").write_text(
        json.dumps({"qa_fail_reasons": {"too_small": 2}}),
        encoding="utf-8",
    )
    (build_release_dir / "release_summary.json").write_text(
        json.dumps(
            {
                "blocked_count": 1,
                "qa_failed_count": 2,
                "real_items": 0,
                "release_ready_count": 0,
                "review_required_count": 0,
                "synthetic_items": 0,
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run(run_dir)

    assert any("blocked from release" in warning for warning in summary["warnings"])
    assert any("QA failure reasons:" in warning for warning in summary["warnings"])


def test_summarize_run_prefers_build_release_counts_over_review_export_counts(tmp_path: Path) -> None:
    run_dir = _write_run_files(
        tmp_path / "run",
        latest_stage="build-release",
        stage_summaries={
            "review-export": {"review_required_count": 9, "blocked_count": 7},
            "build-release": {"release_summary": "build_release/release_summary.json"},
        },
    )
    build_release_dir = run_dir / "build_release"
    build_release_dir.mkdir(exist_ok=True)
    (build_release_dir / "release_summary.json").write_text(
        json.dumps(
            {
                "blocked_count": 1,
                "qa_failed_count": 0,
                "real_items": 2,
                "release_ready_count": 3,
                "review_required_count": 4,
                "synthetic_items": 1,
            }
        ),
        encoding="utf-8",
    )

    summary = summarize_run(run_dir)

    assert summary["counts"]["blocked_count"] == 1
    assert summary["counts"]["review_required_count"] == 4


def test_load_resumed_pipeline_state_rejects_unknown_latest_stage(tmp_path: Path) -> None:
    run_dir = _write_run_files(tmp_path / "run", latest_stage="mystery")

    with pytest.raises(StageExecutionError, match="unknown latest_stage"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "build-release")


def test_load_resumed_pipeline_state_rejects_unknown_target_stage(tmp_path: Path) -> None:
    run_dir = _materialize_run(tmp_path, "discover")

    with pytest.raises(StageExecutionError, match="cannot resume unknown pipeline stage: mystery"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "mystery")


@pytest.mark.parametrize("latest_stage", PIPELINE_STAGES[:-1])
def test_load_resumed_pipeline_state_supports_each_resumable_pipeline_stage(tmp_path: Path, latest_stage: str) -> None:
    run_dir = _materialize_run(tmp_path, latest_stage)
    target_stage = PIPELINE_STAGES[min(PIPELINE_STAGES.index(latest_stage) + 1, len(PIPELINE_STAGES) - 1)]

    state, resumed_stage = load_resumed_pipeline_state(run_dir, "profile_open_v1", target_stage)

    assert resumed_stage == latest_stage
    assert state is not None


def test_load_resumed_pipeline_state_rejects_missing_stage_dir(tmp_path: Path) -> None:
    run_dir = _write_run_files(tmp_path / "run", latest_stage="discover")

    with pytest.raises(StageExecutionError, match="missing stage directory"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "fetch-metadata")


def test_load_resumed_pipeline_state_rejects_unknown_resume_stage(tmp_path: Path) -> None:
    run_dir = _write_run_files(tmp_path / "run", latest_stage="discover")
    discover_dir = run_dir / "discover"
    discover_dir.mkdir(exist_ok=True)
    (discover_dir / "candidates.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (run_dir / "summary.json").write_text(json.dumps({"latest_stage": "unknown", "artifacts": []}), encoding="utf-8")

    with pytest.raises(StageExecutionError, match="unknown latest_stage"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "fetch-metadata")


def test_load_resumed_pipeline_state_rejects_missing_items_list(tmp_path: Path) -> None:
    run_dir = _write_run_files(tmp_path / "run", latest_stage="discover")
    discover_dir = run_dir / "discover"
    discover_dir.mkdir(exist_ok=True)
    (discover_dir / "candidates.json").write_text(json.dumps({"not_items": []}), encoding="utf-8")

    with pytest.raises(StageExecutionError, match="missing an items list"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "fetch-metadata")


def test_summarize_run_rejects_invalid_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("{", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="invalid JSON"):
        summarize_run(run_dir)


def test_summarize_run_rejects_non_object_payload(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text("[]", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="must serialize to an object"):
        summarize_run(run_dir)


def test_summarize_run_handles_missing_release_summary_path_by_omitting_counts(tmp_path: Path) -> None:
    run_dir = _write_run_files(
        tmp_path / "run",
        latest_stage="build-release",
        stage_summaries={"build-release": {}},
    )

    summary = summarize_run(run_dir)

    assert "blocked_count" not in summary["counts"]
