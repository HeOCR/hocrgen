from __future__ import annotations

from pathlib import Path

import yaml


def _load_workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_expansion_maintenance_workflow_has_expected_triggers_and_jobs() -> None:
    workflow = _load_workflow(Path(".github/workflows/expansion-maintenance.yml"))

    assert set(workflow["on"]) == {"workflow_dispatch", "schedule"}
    assert workflow["on"]["schedule"][0]["cron"] == "0 4 * * 1"
    assert workflow["on"]["workflow_dispatch"]["inputs"]["run_scope"]["options"] == [
        "all",
        "discovery",
        "synthetic",
        "review_build",
        "open_build",
    ]
    assert set(workflow["jobs"]) == {"discovery_review", "review_build", "synthetic_build", "open_build"}


def test_hocrgen_dry_run_workflow_uploads_artifacts_and_writes_summary() -> None:
    workflow_path = Path(".github/workflows/hocrgen-dry-run.yml")
    workflow = _load_workflow(workflow_path)
    rendered = workflow_path.read_text(encoding="utf-8")

    assert "workflow_call" in workflow["on"]
    assert "run_dry_run" in workflow["jobs"]
    assert "actions/upload-artifact@v4" in rendered
    assert "$GITHUB_STEP_SUMMARY" in rendered


def test_pr_agent_context_workflows_use_floating_v4_reference() -> None:
    validate = _load_workflow(Path(".github/workflows/validate.yml"))
    refresh = _load_workflow(Path(".github/workflows/pr-agent-context-refresh.yml"))

    validate_job = validate["jobs"]["pr-agent-context"]
    refresh_job = refresh["jobs"]["pr-agent-context-refresh"]

    assert validate_job["uses"] == "shaypal5/pr-agent-context/.github/workflows/pr-agent-context.yml@v4"
    assert validate_job["with"]["tool_ref"] == "v4"
    assert refresh_job["uses"] == "shaypal5/pr-agent-context/.github/workflows/pr-agent-context.yml@v4"
    assert refresh_job["with"]["tool_ref"] == "v4"
