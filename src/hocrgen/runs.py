from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel
from hocrgen.core.context import normalize_stage_dir_name
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import (
    AcquiredItemRecord,
    CandidateRecord,
    ClassifiedItemRecord,
    CuratedItemRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    EnrichedCandidateRecord,
    ItemRecord,
    NormalizedItemRecord,
    PrivacyScannedItemRecord,
    ReviewDecisionAuditRecord,
    ReviewQueueRecord,
    SplitAssignmentRecord,
)
from hocrgen.pipeline import PIPELINE_STAGES, PipelineState, empty_pipeline_state


EXTRA_RUN_STAGES = ("export-alpha",)
RUN_STAGE_ORDER = PIPELINE_STAGES + EXTRA_RUN_STAGES
RUN_STAGE_INDEX = {stage: index for index, stage in enumerate(RUN_STAGE_ORDER)}
RunRecordModel = TypeVar("RunRecordModel", bound=BaseModel)


def summarize_run(run_dir: Path) -> dict[str, Any]:
    resolved_run_dir = run_dir.resolve()
    run_metadata = _load_json_object(resolved_run_dir / "run.json", "run metadata")
    top_level_summary = _load_json_object(resolved_run_dir / "summary.json", "run summary")
    latest_stage = str(top_level_summary.get("latest_stage", "")).strip()
    if latest_stage not in RUN_STAGE_INDEX:
        raise StageExecutionError(f"run summary has unknown latest_stage: {latest_stage!r}")

    stage_summaries: dict[str, dict[str, Any]] = {}
    for stage in RUN_STAGE_ORDER:
        summary_path = resolved_run_dir / normalize_stage_dir_name(stage) / "summary.json"
        if summary_path.exists():
            stage_summaries[stage] = _load_json_object(summary_path, f"{stage} summary")

    counts = _collect_run_counts(resolved_run_dir, stage_summaries)
    warnings = _collect_run_warnings(resolved_run_dir, stage_summaries, counts)
    return {
        "artifacts": top_level_summary.get("artifacts", []),
        "artifact_count": len(top_level_summary.get("artifacts", [])),
        "counts": counts,
        "created_at": run_metadata.get("created_at"),
        "dry_run": run_metadata.get("dry_run"),
        "latest_stage": latest_stage,
        "profile_id": run_metadata.get("profile_id"),
        "run_dir": str(resolved_run_dir),
        "run_id": run_metadata.get("run_id"),
        "stage_summaries": stage_summaries,
        "warnings": warnings,
        "work_root": run_metadata.get("work_root"),
    }


def render_run_summary_markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    warnings = summary["warnings"]
    lines = [
        f"# hocrgen run summary: `{summary['run_id']}`",
        "",
        f"- Profile: `{summary['profile_id']}`",
        f"- Latest stage: `{summary['latest_stage']}`",
        f"- Dry run: `{summary['dry_run']}`",
        f"- Artifact count: `{summary['artifact_count']}`",
        "",
        "## Key counts",
        "",
    ]

    key_count_lines = [
        ("Candidates discovered", counts.get("candidate_count")),
        ("Accepted after policy", counts.get("accepted_count")),
        ("Rejected by policy", counts.get("rejected_count")),
        ("Acquired items", counts.get("acquired_count")),
        ("QA failures", counts.get("qa_failed_count")),
        ("Retained after dedupe", counts.get("retained_count")),
        ("Review-routed items", counts.get("review_required_count")),
        ("Blocked items", counts.get("blocked_count")),
        ("Release-ready items", counts.get("release_ready_count")),
        ("Synthetic items", counts.get("synthetic_items")),
        ("Real items", counts.get("real_items")),
    ]
    for label, value in key_count_lines:
        if value in (None, {}, []):
            continue
        lines.append(f"- {label}: `{value}`")
    if counts.get("rejection_reasons"):
        lines.append(f"- Rights rejection reasons: `{_format_counter(counts['rejection_reasons'])}`")

    if warnings:
        lines.extend(["", "## Warnings", ""])
        for warning in warnings:
            lines.append(f"- {warning}")

    artifact_paths = summary.get("artifacts", [])
    if artifact_paths:
        lines.extend(["", "## Artifacts", ""])
        for artifact_path in artifact_paths:
            lines.append(f"- `{artifact_path}`")

    return "\n".join(lines) + "\n"


def load_resumed_pipeline_state(run_dir: Path, profile_id: str, target_stage: str) -> tuple[PipelineState, str]:
    resolved_run_dir = run_dir.resolve()
    run_metadata = _load_json_object(resolved_run_dir / "run.json", "run metadata")
    top_level_summary = _load_json_object(resolved_run_dir / "summary.json", "run summary")

    stored_profile_id = str(run_metadata.get("profile_id", "")).strip()
    if stored_profile_id != profile_id:
        raise StageExecutionError(
            f"resume run profile mismatch: requested {profile_id}, found {stored_profile_id or '<missing>'}"
        )

    latest_stage = str(top_level_summary.get("latest_stage", "")).strip()
    if latest_stage not in PIPELINE_STAGES:
        raise StageExecutionError(f"resume run summary has unknown latest_stage: {latest_stage!r}")
    if target_stage not in PIPELINE_STAGES:
        raise StageExecutionError(f"cannot resume unknown pipeline stage: {target_stage}")
    if PIPELINE_STAGES.index(latest_stage) >= PIPELINE_STAGES.index(target_stage):
        raise StageExecutionError(
            f"resume run already reached or passed target stage {target_stage}: latest completed stage is {latest_stage}"
        )

    state = empty_pipeline_state()
    latest_index = PIPELINE_STAGES.index(latest_stage)
    for stage in PIPELINE_STAGES[: latest_index + 1]:
        _load_stage_state(stage, resolved_run_dir, state)
    return state, latest_stage


def _collect_run_counts(run_dir: Path, stage_summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, Any] = {}
    discover = stage_summaries.get("discover", {})
    policy_filter = stage_summaries.get("policy-filter", {})
    acquire = stage_summaries.get("acquire", {})
    normalize = stage_summaries.get("normalize", {})
    dedupe = stage_summaries.get("dedupe", {})
    review_export = stage_summaries.get("review-export", {})
    build_release = stage_summaries.get("build-release", {})

    if "candidate_count" in discover:
        counts["candidate_count"] = discover["candidate_count"]
        counts["included_sources"] = discover.get("included_sources", [])
        counts["source_health"] = discover.get("source_health", {})
    if "accepted_count" in policy_filter:
        counts["accepted_count"] = policy_filter["accepted_count"]
        counts["rejected_count"] = policy_filter.get("rejected_count", 0)
        counts["rejection_reasons"] = policy_filter.get("rejection_reasons", {})
    if "acquired_count" in acquire:
        counts["acquired_count"] = acquire["acquired_count"]
    if "failed_count" in normalize:
        counts["qa_failed_count"] = normalize["failed_count"]
    if "retained_count" in dedupe:
        counts["retained_count"] = dedupe["retained_count"]
        counts["duplicate_item_count"] = dedupe.get("duplicate_item_count", 0)
    if "review_required_count" in review_export and not build_release:
        counts["review_required_count"] = review_export.get("review_required_count", 0)
        counts["blocked_count"] = review_export.get("blocked_count", 0)
    release_summary = _load_release_summary(run_dir, build_release)
    if release_summary:
        counts.update(release_summary)
    return counts


def _collect_run_warnings(run_dir: Path, stage_summaries: dict[str, dict[str, Any]], counts: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if counts.get("qa_failed_count", 0):
        warnings.append(f"QA rejected {counts['qa_failed_count']} item(s).")
    if counts.get("review_required_count", 0):
        warnings.append(f"{counts['review_required_count']} item(s) still require review.")
    if counts.get("blocked_count", 0):
        warnings.append(f"{counts['blocked_count']} item(s) are blocked from release.")
    rejection_reasons = counts.get("rejection_reasons", {})
    if rejection_reasons:
        warnings.append(f"Policy rejections: {_format_counter(rejection_reasons)}.")

    build_release = stage_summaries.get("build-release", {})
    if "source_stats" in build_release:
        source_stats = _load_json_object(run_dir / build_release["source_stats"], "source stats")
        if source_stats.get("qa_fail_reasons"):
            warnings.append(f"QA failure reasons: {_format_counter(source_stats['qa_fail_reasons'])}.")
        for skipped_source in source_stats.get("source_health", {}).get("skipped_sources", []):
            reason = skipped_source.get("operational_reason") or "no operational reason recorded"
            warnings.append(
                "Source "
                f"{skipped_source['source_id']} skipped: {skipped_source['skip_reason']} "
                f"({skipped_source['operational_status']}: {reason})."
            )
    elif counts.get("source_health"):
        for skipped_source in counts["source_health"].get("skipped_sources", []):
            reason = skipped_source.get("operational_reason") or "no operational reason recorded"
            warnings.append(
                "Source "
                f"{skipped_source['source_id']} skipped: {skipped_source['skip_reason']} "
                f"({skipped_source['operational_status']}: {reason})."
            )
    return warnings


def _load_release_summary(run_dir: Path, build_release_summary: dict[str, Any]) -> dict[str, Any]:
    if not build_release_summary or "release_summary" not in build_release_summary:
        return {}
    release_summary_path = run_dir / build_release_summary["release_summary"]
    release_summary = _load_json_object(release_summary_path, "build release summary")
    return {
        "blocked_count": release_summary.get("blocked_count"),
        "qa_failed_count": release_summary.get("qa_failed_count"),
        "real_items": release_summary.get("real_items"),
        "release_ready_count": release_summary.get("release_ready_count"),
        "review_required_count": release_summary.get("review_required_count"),
        "synthetic_items": release_summary.get("synthetic_items"),
    }


def _load_stage_state(stage: str, run_dir: Path, state: PipelineState) -> None:
    stage_dir = run_dir / normalize_stage_dir_name(stage)
    if not stage_dir.exists():
        raise StageExecutionError(f"resume run is missing stage directory for {stage}: {stage_dir}")

    if stage == "discover":
        state.candidates = _load_items(stage_dir / "candidates.json", CandidateRecord)
        source_health_path = stage_dir / "source_health.json"
        if source_health_path.exists():
            source_health = _load_json_object(source_health_path, "source health")
            sources = source_health.get("sources", [])
            if not isinstance(sources, list):
                raise StageExecutionError(
                    f"invalid source health artifact at {source_health_path}: 'sources' must be a list"
                )
            if any(not isinstance(source, dict) for source in sources):
                raise StageExecutionError(
                    f"invalid source health artifact at {source_health_path}: each entry in 'sources' must be an object"
                )
            state.source_health = list(sources)
        return
    if stage == "fetch-metadata":
        state.enriched_candidates = _load_items(stage_dir / "enriched_candidates.json", EnrichedCandidateRecord)
        return
    if stage == "policy-filter":
        state.accepted_items = _load_items(stage_dir / "accepted_items.json", ItemRecord)
        state.rejected_items = _load_items(stage_dir / "rejected_items.json", ItemRecord)
        return
    if stage == "acquire":
        state.acquired_items = _load_items(stage_dir / "acquired_items.json", AcquiredItemRecord)
        return
    if stage == "normalize":
        state.normalized_items = _load_items(stage_dir / "normalized_items.json", NormalizedItemRecord)
        state.failed_normalized_items = _load_items(stage_dir / "failed_items.json", NormalizedItemRecord)
        return
    if stage == "dedupe":
        state.retained_items = _load_items(stage_dir / "retained_items.json", CuratedItemRecord)
        state.duplicate_items = _load_items(stage_dir / "duplicate_items.json", CuratedItemRecord)
        state.duplicate_relations = _load_items(stage_dir / "duplicate_relations.json", DuplicateRelationRecord)
        state.duplicate_clusters = _load_items(stage_dir / "duplicate_clusters.json", DuplicateClusterRecord)
        return
    if stage == "classify":
        state.classified_items = _load_items(stage_dir / "classified_items.json", ClassifiedItemRecord)
        return
    if stage == "privacy-scan":
        state.privacy_scanned_items = _load_items(stage_dir / "privacy_scanned_items.json", PrivacyScannedItemRecord)
        return
    if stage == "review-export":
        state.review_queue = _load_items(stage_dir / "queue.json", ReviewQueueRecord)
        state.release_ready_items = _load_items(stage_dir / "release_ready_items.json", PrivacyScannedItemRecord)
        state.review_required_items = _load_items(stage_dir / "review_required_items.json", PrivacyScannedItemRecord)
        state.blocked_items = _load_items(stage_dir / "blocked_items.json", PrivacyScannedItemRecord)
        return
    if stage == "review-merge":
        state.release_ready_items = _load_items(stage_dir / "release_ready_items.json", PrivacyScannedItemRecord)
        state.review_required_items = _load_items(stage_dir / "unresolved_items.json", PrivacyScannedItemRecord)
        state.rejected_review_items = _load_items(stage_dir / "rejected_items.json", PrivacyScannedItemRecord)
        state.decision_audit = _load_items(stage_dir / "decision_audit.json", ReviewDecisionAuditRecord)
        return
    if stage == "split":
        state.split_assignments = _load_items(stage_dir / "split_manifest.json", SplitAssignmentRecord)
        state.leakage_report = _load_json_object(stage_dir / "leakage_report.json", "split leakage report")
        return
    if stage == "build-release":
        state.release_ready_items = _load_items(stage_dir / "item_manifest.json", PrivacyScannedItemRecord)
        state.duplicate_items = _load_items(stage_dir / "removed_duplicate_items.json", CuratedItemRecord)
        state.duplicate_relations = _load_items(stage_dir / "duplicate_relations.json", DuplicateRelationRecord)
        state.duplicate_clusters = _load_items(stage_dir / "duplicate_clusters.json", DuplicateClusterRecord)
        state.review_queue = _load_items(stage_dir / "review_queue.json", ReviewQueueRecord)
        state.review_required_items = _load_items(stage_dir / "review_required_items.json", PrivacyScannedItemRecord)
        state.blocked_items = _load_items(stage_dir / "blocked_items.json", PrivacyScannedItemRecord)
        state.decision_audit = _load_items(stage_dir / "decision_audit.json", ReviewDecisionAuditRecord)
        state.split_assignments = _load_items(stage_dir / "split_manifest.json", SplitAssignmentRecord)
        state.leakage_report = _load_json_object(stage_dir / "leakage_report.json", "build release leakage report")
        return
    raise StageExecutionError(f"resume loading for stage {stage} is not supported")


def _load_items(path: Path, model_type: type[RunRecordModel]) -> list[RunRecordModel]:
    data = _load_json_object(path, str(path.relative_to(path.parents[1])))
    items = data.get("items")
    if not isinstance(items, list):
        raise StageExecutionError(f"run artifact is missing an items list: {path}")
    return [model_type.model_validate(item) for item in items]


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise StageExecutionError(f"missing required {label}: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StageExecutionError(f"{label} has invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise StageExecutionError(f"{label} must serialize to an object: {path}")
    return payload


def _format_counter(values: dict[str, Any]) -> str:
    if not values:
        return "none"
    ordered = Counter({str(key): int(value) for key, value in values.items()})
    return ", ".join(f"{key}={ordered[key]}" for key in sorted(ordered))
