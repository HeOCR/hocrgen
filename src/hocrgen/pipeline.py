from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle
from hocrgen.core.context import RunContext
from hocrgen.manifests.io import write_json


@dataclass(frozen=True)
class StageResult:
    stage: str
    summary_path: Path
    extra_artifacts: list[Path]


def write_run_metadata(context: RunContext) -> Path:
    path = context.run_dir / "run.json"
    write_json(
        path,
        {
            "created_at": context.created_at,
            "dry_run": context.dry_run,
            "profile_id": context.profile_id,
            "run_id": context.run_id,
            "work_root": str(context.work_root),
        },
    )
    return path


def write_run_summary(context: RunContext, stage: str, artifacts: list[Path]) -> Path:
    path = context.run_dir / "summary.json"
    write_json(
        path,
        {
            "artifacts": [str(artifact.relative_to(context.run_dir)) for artifact in artifacts],
            "dry_run": context.dry_run,
            "latest_stage": stage,
            "profile_id": context.profile_id,
            "run_id": context.run_id,
        },
    )
    return path


def run_stage(stage: str, bundle: ConfigBundle, context: RunContext) -> StageResult:
    stage_dir = context.stage_dir(stage)
    stage_dir.mkdir(parents=True, exist_ok=True)

    summary_payload: dict[str, Any] = {
        "dry_run": context.dry_run,
        "included_sources": list(bundle.profiles[context.profile_id].include_sources),
        "profile_id": context.profile_id,
        "run_id": context.run_id,
        "stage": stage,
        "status": "scaffolded",
    }
    extra_artifacts: list[Path] = []

    if stage == "discover":
        candidates_path = stage_dir / "candidates.json"
        write_json(
            candidates_path,
            {
                "candidate_count": 0,
                "items": [],
                "note": "Milestone 1 placeholder manifest; no real discovery performed.",
                "stage": stage,
            },
        )
        summary_payload["candidate_manifest"] = str(candidates_path.relative_to(context.run_dir))
        extra_artifacts.append(candidates_path)
    elif stage == "build-release":
        release_path = stage_dir / "release_summary.json"
        write_json(
            release_path,
            {
                "note": "Milestone 1 dry-run scaffold. Packaging and publishing are not implemented yet.",
                "profile_id": context.profile_id,
                "publish_targets": [target.value for target in bundle.profiles[context.profile_id].publish_targets],
                "release_ready": False,
                "stage": stage,
            },
        )
        summary_payload["release_summary"] = str(release_path.relative_to(context.run_dir))
        extra_artifacts.append(release_path)
    else:
        manifest_path = stage_dir / "manifest.json"
        write_json(
            manifest_path,
            {
                "items": [],
                "note": f"Milestone 1 placeholder manifest for stage {stage}.",
                "stage": stage,
            },
        )
        summary_payload["manifest"] = str(manifest_path.relative_to(context.run_dir))
        extra_artifacts.append(manifest_path)

    summary_path = stage_dir / "summary.json"
    write_json(summary_path, summary_payload)
    return StageResult(stage=stage, summary_path=summary_path, extra_artifacts=extra_artifacts)
