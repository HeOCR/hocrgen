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
from hocrgen.runs import (
    _format_counter,
    _load_json_object,
    _load_release_summary,
    _load_stage_state,
    _collect_run_warnings,
    summarize_run,
)


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
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"created_at": "2026-01-01T00:00:00Z", "dry_run": True, "profile_id": "profile_open_v1", "run_id": "run-1", "work_root": "/tmp"}),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(json.dumps({"latest_stage": "mystery", "artifacts": []}), encoding="utf-8")

    with pytest.raises(StageExecutionError, match="unknown latest_stage"):
        summarize_run(run_dir)


def test_summarize_run_markdown_includes_rejection_reasons_and_skips_empty_counts(tmp_path: Path, capsys) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    summary_payload = {
        "artifacts": [],
        "artifact_count": 0,
        "counts": {"accepted_count": 1, "rejection_reasons": {"unknown_rights": 2}},
        "created_at": "2026-01-01T00:00:00Z",
        "dry_run": True,
        "latest_stage": "policy-filter",
        "profile_id": "profile_open_v1",
        "run_dir": str(run_dir),
        "run_id": "run-1",
        "stage_summaries": {},
        "warnings": [],
        "work_root": str(tmp_path),
    }

    from hocrgen.runs import render_run_summary_markdown

    markdown = render_run_summary_markdown(summary_payload)

    assert "Rights rejection reasons" in markdown
    assert "Retained after dedupe" not in markdown


def test_summarize_run_collects_review_warning_lines(tmp_path: Path) -> None:
    run_dir = _materialize_run(tmp_path, "build-release")
    summary = summarize_run(run_dir)

    assert any("require review" in warning for warning in summary["warnings"])


def test_collect_run_warnings_includes_blocked_and_qa_failure_reasons(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    build_release_dir = run_dir / "build_release"
    build_release_dir.mkdir()
    source_stats_path = build_release_dir / "source_stats.json"
    source_stats_path.write_text(json.dumps({"qa_fail_reasons": {"too_small": 2}}), encoding="utf-8")

    warnings = _collect_run_warnings(
        run_dir,
        {"build-release": {"source_stats": "build_release/source_stats.json"}},
        {"blocked_count": 1, "rejection_reasons": {"unknown_rights": 2}},
    )

    assert any("blocked from release" in warning for warning in warnings)
    assert any("QA failure reasons:" in warning for warning in warnings)


def test_load_resumed_pipeline_state_rejects_unknown_latest_stage(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.json").write_text(
        json.dumps({"created_at": "2026-01-01T00:00:00Z", "dry_run": True, "profile_id": "profile_open_v1", "run_id": "run-1", "work_root": "/tmp"}),
        encoding="utf-8",
    )
    (run_dir / "summary.json").write_text(json.dumps({"latest_stage": "mystery", "artifacts": []}), encoding="utf-8")

    from hocrgen.runs import load_resumed_pipeline_state

    with pytest.raises(StageExecutionError, match="unknown latest_stage"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "build-release")


def test_load_resumed_pipeline_state_rejects_unknown_target_stage(tmp_path: Path) -> None:
    run_dir = _materialize_run(tmp_path, "discover")

    from hocrgen.runs import load_resumed_pipeline_state

    with pytest.raises(StageExecutionError, match="cannot resume unknown pipeline stage: mystery"):
        load_resumed_pipeline_state(run_dir, "profile_open_v1", "mystery")


@pytest.mark.parametrize("stage", PIPELINE_STAGES)
def test_load_stage_state_supports_each_pipeline_stage(tmp_path: Path, stage: str) -> None:
    run_dir = _materialize_run(tmp_path, stage)
    from hocrgen.pipeline import empty_pipeline_state

    state = empty_pipeline_state()
    _load_stage_state(stage, run_dir, state)

    assert state is not None


def test_load_stage_state_rejects_missing_stage_dir(tmp_path: Path) -> None:
    from hocrgen.pipeline import empty_pipeline_state

    with pytest.raises(StageExecutionError, match="missing stage directory"):
        _load_stage_state("discover", tmp_path / "missing", empty_pipeline_state())


def test_load_stage_state_rejects_unknown_stage(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "unknown").mkdir(parents=True)
    from hocrgen.pipeline import empty_pipeline_state

    with pytest.raises(StageExecutionError, match="resume loading for stage unknown is not supported"):
        _load_stage_state("unknown", run_dir, empty_pipeline_state())


def test_load_items_rejects_missing_items_list(tmp_path: Path) -> None:
    payload_path = tmp_path / "discover" / "candidates.json"
    payload_path.parent.mkdir(parents=True)
    payload_path.write_text(json.dumps({"not_items": []}), encoding="utf-8")

    from hocrgen.manifests.models import CandidateRecord
    from hocrgen.runs import _load_items

    with pytest.raises(StageExecutionError, match="missing an items list"):
        _load_items(payload_path, CandidateRecord)


def test_load_json_object_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="invalid JSON"):
        _load_json_object(path, "broken")


def test_load_json_object_rejects_non_object_payload(tmp_path: Path) -> None:
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="must serialize to an object"):
        _load_json_object(path, "list")


def test_load_release_summary_returns_empty_dict_when_path_missing() -> None:
    assert _load_release_summary(Path("/tmp"), {}) == {}


def test_format_counter_returns_none_for_empty_mapping() -> None:
    assert _format_counter({}) == "none"
