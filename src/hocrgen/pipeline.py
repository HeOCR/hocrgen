from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import floor
from pathlib import Path
from typing import Any

from hocrgen.annotation_pilots import load_annotation_pilot_config, select_annotation_pilot_items
from hocrgen.annotations import build_annotation_manifest
from hocrgen.benchmark import load_benchmark_config, select_benchmark_items
from hocrgen.classify.heuristics import classify_items
from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import LicenseEntry, SourceConfig
from hocrgen.core.context import RunContext
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.dedupe.exact import deduplicate_items
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.biblia import BibliaImporter
from hocrgen.fetchers.nli import NliFetcher
from hocrgen.fetchers.pinkas import PinkasImporter
from hocrgen.fetchers.synthetic import SyntheticFetcher
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import (
    AcquiredItemRecord,
    AnnotationPilotManifestRecord,
    AnnotationPilotSelectionAuditRecord,
    BenchmarkItemRecord,
    BenchmarkSelectionAuditRecord,
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
    ReviewOverrideRecord,
    ReviewDecisionRecord,
    SplitAssignmentRecord,
)
from hocrgen.review.merge import load_review_data, merge_review_decisions
from hocrgen.normalize.metadata import normalize_items
from hocrgen.parsers.rights import classify_eligibility, normalize_rights
from hocrgen.privacy.rules import apply_privacy_rules
from hocrgen.review.queue import export_review_queue
from hocrgen.source_ops import (
    F1_REAL_TARGET_COUNT,
    F1_SOURCE_TARGETS,
    F1_SYNTHETIC_TARGET_COUNT,
    evaluate_f1_source_depth_feasibility,
    evaluate_source_health,
    source_health_summary,
)
from hocrgen.split.assign import assign_splits
from hocrgen.synthetic.reporting import synthetic_composition_report


PIPELINE_STAGES = (
    "discover",
    "fetch-metadata",
    "policy-filter",
    "acquire",
    "normalize",
    "dedupe",
    "classify",
    "privacy-scan",
    "review-export",
    "review-merge",
    "split",
    "build-release",
)


FETCHERS = {
    "nli": NliFetcher(),
    "pinkas": PinkasImporter(),
    "biblia": BibliaImporter(),
    "synthetic": SyntheticFetcher(),
}


@dataclass(frozen=True)
class StageResult:
    stage: str
    summary_path: Path
    extra_artifacts: list[Path]


@dataclass
class PipelineState:
    candidates: list[CandidateRecord] = field(default_factory=list)
    enriched_candidates: list[EnrichedCandidateRecord] = field(default_factory=list)
    accepted_items: list[ItemRecord] = field(default_factory=list)
    rejected_items: list[ItemRecord] = field(default_factory=list)
    acquired_items: list[AcquiredItemRecord] = field(default_factory=list)
    normalized_items: list[NormalizedItemRecord] = field(default_factory=list)
    failed_normalized_items: list[NormalizedItemRecord] = field(default_factory=list)
    retained_items: list[CuratedItemRecord] = field(default_factory=list)
    duplicate_items: list[CuratedItemRecord] = field(default_factory=list)
    duplicate_relations: list[DuplicateRelationRecord] = field(default_factory=list)
    duplicate_clusters: list[DuplicateClusterRecord] = field(default_factory=list)
    classified_items: list[ClassifiedItemRecord] = field(default_factory=list)
    privacy_scanned_items: list[PrivacyScannedItemRecord] = field(default_factory=list)
    release_ready_items: list[PrivacyScannedItemRecord] = field(default_factory=list)
    review_required_items: list[PrivacyScannedItemRecord] = field(default_factory=list)
    blocked_items: list[PrivacyScannedItemRecord] = field(default_factory=list)
    review_queue: list[ReviewQueueRecord] = field(default_factory=list)
    rejected_review_items: list[PrivacyScannedItemRecord] = field(default_factory=list)
    decision_audit: list[ReviewDecisionAuditRecord] = field(default_factory=list)
    review_data_manual_decisions: list[ReviewDecisionRecord] = field(default_factory=list)
    review_data_allowlist: list[ReviewOverrideRecord] = field(default_factory=list)
    review_data_blocklist: list[ReviewOverrideRecord] = field(default_factory=list)
    split_assignments: list[SplitAssignmentRecord] = field(default_factory=list)
    leakage_report: dict[str, Any] = field(default_factory=dict)
    source_health: list[dict[str, Any]] = field(default_factory=list)
    benchmark_items: list[BenchmarkItemRecord] = field(default_factory=list)
    benchmark_selection_audit: list[BenchmarkSelectionAuditRecord] = field(default_factory=list)
    benchmark_stability_policy: dict[str, Any] = field(default_factory=dict)
    benchmark_card_markdown: str = ""
    annotation_pilot_manifest: AnnotationPilotManifestRecord | None = None
    annotation_pilot_selection_audit: list[AnnotationPilotSelectionAuditRecord] = field(default_factory=list)


def empty_pipeline_state() -> PipelineState:
    return PipelineState(
        candidates=[],
        enriched_candidates=[],
        accepted_items=[],
        rejected_items=[],
        acquired_items=[],
        normalized_items=[],
        failed_normalized_items=[],
        retained_items=[],
        duplicate_items=[],
        duplicate_relations=[],
        duplicate_clusters=[],
        classified_items=[],
        privacy_scanned_items=[],
        release_ready_items=[],
        review_required_items=[],
        blocked_items=[],
        review_queue=[],
        rejected_review_items=[],
        decision_audit=[],
        review_data_manual_decisions=[],
        review_data_allowlist=[],
        review_data_blocklist=[],
        split_assignments=[],
        leakage_report={},
        source_health=[],
        benchmark_items=[],
        benchmark_selection_audit=[],
        benchmark_stability_policy={},
        benchmark_card_markdown="",
        annotation_pilot_manifest=None,
        annotation_pilot_selection_audit=[],
    )


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


def _selected_sources(
    bundle: ConfigBundle,
    profile_id: str,
    options: StageOptions,
    source_health: list[dict[str, Any]] | None = None,
) -> list[SourceConfig]:
    profile = bundle.profiles[profile_id]
    exclude_ids = set(profile.exclude_sources)
    sources_by_id = {source.id: source for source in bundle.source_registry.sources}
    if source_health is not None:
        selected_ids = {record["source_id"] for record in source_health if record.get("selected")}
        return [sources_by_id[source_id] for source_id in profile.include_sources if source_id in selected_ids]
    sources = [
        sources_by_id[source_id]
        for source_id in profile.include_sources
        if source_id not in exclude_ids and source_id in sources_by_id
    ]
    if options.source_filter:
        sources = [source for source in sources if source.id in options.source_filter]
    return sources


def _licenses_by_id(bundle: ConfigBundle) -> dict[str, LicenseEntry]:
    return {license_entry.id: license_entry for license_entry in bundle.licenses.licenses}


def _dump_models(items) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def _apply_synthetic_cap(
    accepted_items: list[ItemRecord],
    rejected_items: list[ItemRecord],
    synthetic_fraction_max: float,
) -> tuple[list[ItemRecord], list[ItemRecord]]:
    synthetic = [item for item in accepted_items if item.is_synthetic]
    real = [item for item in accepted_items if not item.is_synthetic]
    if not synthetic or synthetic_fraction_max >= 1:
        return accepted_items, rejected_items

    allowed_synthetic = floor((synthetic_fraction_max * len(real)) / (1 - synthetic_fraction_max)) if real else 0
    allowed_ids = {item.item_id for item in sorted(synthetic, key=lambda item: item.item_id)[:allowed_synthetic]}
    remaining: list[ItemRecord] = []
    for item in accepted_items:
        if item.is_synthetic and item.item_id not in allowed_ids:
            rejected_items.append(
                item.model_copy(
                    update={
                        "eligibility": "rejected",
                        "eligibility_reason": "synthetic_fraction_exceeded",
                    }
                )
            )
        else:
            remaining.append(item)
    return remaining, rejected_items


def _item_from_enriched(record: EnrichedCandidateRecord, source: SourceConfig, bundle: ConfigBundle, profile_id: str) -> ItemRecord:
    licenses = _licenses_by_id(bundle)
    rights = normalize_rights(record.raw_rights_text, source, licenses)
    license_entry = licenses[rights.normalized_license]
    eligibility, reason = classify_eligibility(rights, bundle.profiles[profile_id], license_entry.public_release_allowed)
    return ItemRecord(
        **record.model_dump(),
        item_id=f"{record.source_id}:{record.source_item_id}",
        normalized_license=rights.normalized_license,
        rights_classification=rights.rights_classification,
        eligibility=eligibility,
        eligibility_reason=reason,
        is_synthetic=source.fetcher == "synthetic",
        provenance={
            "fetcher": source.fetcher,
            "source_name": source.name,
            "source_status": source.status.value,
            "upstream_identifier": record.source_item_id,
        },
    )


def _run_discover(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("discover")
    stage_dir.mkdir(parents=True, exist_ok=True)
    source_health = [result.model_dump() for result in evaluate_source_health(bundle, context.profile_id, options)]
    source_depth_feasibility = evaluate_f1_source_depth_feasibility(bundle, source_health)
    state.source_health = source_health
    selected_sources = _selected_sources(bundle, context.profile_id, options, source_health)
    candidates: list[CandidateRecord] = []
    for source in selected_sources:
        candidates.extend(FETCHERS[source.fetcher].discover_candidates(source, bundle, options))

    manifest_path = stage_dir / "candidates.json"
    source_depth_feasibility_path = stage_dir / "source_depth_feasibility.json"
    source_health_path = stage_dir / "source_health.json"
    summary_path = stage_dir / "summary.json"
    write_json(manifest_path, {"items": _dump_models(candidates)})
    write_json(source_depth_feasibility_path, source_depth_feasibility)
    write_json(source_health_path, {"sources": source_health, "summary": source_health_summary(source_health)})
    write_json(
        summary_path,
        {
            "candidate_count": len(candidates),
            "included_sources": [source.id for source in selected_sources],
            "source_depth_feasibility": source_depth_feasibility["summary"],
            "source_depth_feasibility_report": str(source_depth_feasibility_path.relative_to(context.run_dir)),
            "source_health": source_health_summary(source_health),
            "stage": "discover",
        },
    )
    return StageResult(
        stage="discover",
        summary_path=summary_path,
        extra_artifacts=[manifest_path, source_health_path, source_depth_feasibility_path],
    )


def _run_fetch_metadata(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("fetch_metadata")
    stage_dir.mkdir(parents=True, exist_ok=True)
    selected_sources = _selected_sources(bundle, context.profile_id, options, state.source_health or None)
    candidates_by_source = {
        source.id: [candidate for candidate in state.candidates if candidate.source_id == source.id]
        for source in selected_sources
    }
    enriched: list[EnrichedCandidateRecord] = []
    for source in selected_sources:
        enriched.extend(FETCHERS[source.fetcher].fetch_candidate_metadata(source, bundle, candidates_by_source[source.id], options))

    manifest_path = stage_dir / "enriched_candidates.json"
    summary_path = stage_dir / "summary.json"
    write_json(manifest_path, {"items": _dump_models(enriched)})
    write_json(
        summary_path,
        {
            "enriched_candidate_count": len(enriched),
            "rights_samples": sorted({item.raw_rights_text for item in enriched if item.raw_rights_text}),
            "stage": "fetch-metadata",
        },
    )
    state.enriched_candidates = enriched
    return StageResult(stage="fetch-metadata", summary_path=summary_path, extra_artifacts=[manifest_path])


def _run_policy_filter(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("policy_filter")
    stage_dir.mkdir(parents=True, exist_ok=True)
    selected_sources = {source.id: source for source in _selected_sources(bundle, context.profile_id, options, state.source_health or None)}
    accepted: list[ItemRecord] = []
    rejected: list[ItemRecord] = []
    for record in state.enriched_candidates:
        source = selected_sources[record.source_id]
        item = _item_from_enriched(record, source, bundle, context.profile_id)
        if item.eligibility == "accepted":
            accepted.append(item)
        else:
            rejected.append(item)

    accepted, rejected = _apply_synthetic_cap(
        accepted,
        rejected,
        bundle.profiles[context.profile_id].synthetic_fraction_max,
    )
    accepted_path = stage_dir / "accepted_items.json"
    rejected_path = stage_dir / "rejected_items.json"
    summary_path = stage_dir / "summary.json"
    write_json(accepted_path, {"items": _dump_models(accepted)})
    write_json(rejected_path, {"items": _dump_models(rejected)})
    write_json(
        summary_path,
        {
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "rejection_reasons": dict(Counter(item.eligibility_reason for item in rejected)),
            "stage": "policy-filter",
        },
    )
    state.accepted_items = accepted
    state.rejected_items = rejected
    return StageResult(stage="policy-filter", summary_path=summary_path, extra_artifacts=[accepted_path, rejected_path])


def _run_acquire(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("acquire")
    assets_dir = stage_dir / "assets"
    stage_dir.mkdir(parents=True, exist_ok=True)
    selected_sources = {source.id: source for source in _selected_sources(bundle, context.profile_id, options, state.source_health or None)}
    acquired: list[AcquiredItemRecord] = []
    for source_id, source in selected_sources.items():
        source_items = [item for item in state.accepted_items if item.source_id == source_id]
        acquired.extend(FETCHERS[source.fetcher].acquire_items(source, bundle, source_items, assets_dir, options))

    manifest_path = stage_dir / "acquired_items.json"
    summary_path = stage_dir / "summary.json"
    write_json(manifest_path, {"items": _dump_models(acquired)})
    write_json(
        summary_path,
        {
            "acquired_count": len(acquired),
            "asset_count": sum(len(item.acquired_assets) for item in acquired),
            "stage": "acquire",
        },
    )
    state.acquired_items = acquired
    return StageResult(stage="acquire", summary_path=summary_path, extra_artifacts=[manifest_path])


def _run_normalize(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("normalize")
    assets_dir = stage_dir / "assets"
    thumbnails_dir = stage_dir / "thumbnails"
    stage_dir.mkdir(parents=True, exist_ok=True)

    outputs = normalize_items(
        items=state.acquired_items,
        thresholds=bundle.quality_thresholds,
        assets_dir=assets_dir,
        thumbnails_dir=thumbnails_dir,
    )
    normalized_manifest_path = stage_dir / "normalized_items.json"
    failed_manifest_path = stage_dir / "failed_items.json"
    qa_report_path = stage_dir / "qa_report.json"
    summary_path = stage_dir / "summary.json"

    write_json(normalized_manifest_path, {"items": _dump_models(outputs.normalized_items)})
    write_json(failed_manifest_path, {"items": _dump_models(outputs.failed_items)})
    write_json(qa_report_path, outputs.qa_report)
    write_json(
        summary_path,
        {
            "failed_count": len(outputs.failed_items),
            "normalized_count": len(outputs.normalized_items),
            "qa_report": str(qa_report_path.relative_to(context.run_dir)),
            "stage": "normalize",
        },
    )
    state.normalized_items = outputs.normalized_items
    state.failed_normalized_items = outputs.failed_items
    return StageResult(
        stage="normalize",
        summary_path=summary_path,
        extra_artifacts=[normalized_manifest_path, failed_manifest_path, qa_report_path],
    )


def _run_dedupe(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del options
    stage_dir = context.stage_dir("dedupe")
    stage_dir.mkdir(parents=True, exist_ok=True)
    outputs = deduplicate_items(state.normalized_items, bundle.profiles[context.profile_id])

    retained_path = stage_dir / "retained_items.json"
    duplicate_path = stage_dir / "duplicate_items.json"
    relations_path = stage_dir / "duplicate_relations.json"
    clusters_path = stage_dir / "duplicate_clusters.json"
    report_path = stage_dir / "report.json"
    summary_path = stage_dir / "summary.json"

    write_json(retained_path, {"items": _dump_models(outputs.retained_items)})
    write_json(duplicate_path, {"items": _dump_models(outputs.duplicate_items)})
    write_json(relations_path, {"items": _dump_models(outputs.duplicate_relations)})
    write_json(clusters_path, {"items": _dump_models(outputs.duplicate_clusters)})
    write_json(report_path, outputs.report)
    write_json(
        summary_path,
        {
            "duplicate_cluster_count": len(outputs.duplicate_clusters),
            "duplicate_item_count": len(outputs.duplicate_items),
            "report": str(report_path.relative_to(context.run_dir)),
            "retained_count": len(outputs.retained_items),
            "stage": "dedupe",
        },
    )
    state.retained_items = outputs.retained_items
    state.duplicate_items = outputs.duplicate_items
    state.duplicate_relations = outputs.duplicate_relations
    state.duplicate_clusters = outputs.duplicate_clusters
    return StageResult(
        stage="dedupe",
        summary_path=summary_path,
        extra_artifacts=[retained_path, duplicate_path, relations_path, clusters_path, report_path],
    )


def _run_classify(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del options
    stage_dir = context.stage_dir("classify")
    stage_dir.mkdir(parents=True, exist_ok=True)
    outputs = classify_items(state.retained_items, bundle)
    manifest_path = stage_dir / "classified_items.json"
    summary_path = stage_dir / "summary.json"
    write_json(manifest_path, {"items": _dump_models(outputs.classified_items)})
    write_json(summary_path, {**outputs.summary, "classified_count": len(outputs.classified_items), "stage": "classify"})
    state.classified_items = outputs.classified_items
    return StageResult(stage="classify", summary_path=summary_path, extra_artifacts=[manifest_path])


def _run_privacy_scan(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del options
    stage_dir = context.stage_dir("privacy_scan")
    stage_dir.mkdir(parents=True, exist_ok=True)
    outputs = apply_privacy_rules(state.classified_items, bundle, context.profile_id)
    manifest_path = stage_dir / "privacy_scanned_items.json"
    summary_path = stage_dir / "summary.json"
    write_json(manifest_path, {"items": _dump_models(outputs.scanned_items)})
    write_json(summary_path, {**outputs.summary, "scanned_count": len(outputs.scanned_items), "stage": "privacy-scan"})
    state.privacy_scanned_items = outputs.scanned_items
    return StageResult(stage="privacy-scan", summary_path=summary_path, extra_artifacts=[manifest_path])


def _run_review_export(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del bundle, options
    stage_dir = context.stage_dir("review-export")
    stage_dir.mkdir(parents=True, exist_ok=True)
    outputs = export_review_queue(state.privacy_scanned_items)
    queue_path = stage_dir / "queue.json"
    release_ready_path = stage_dir / "release_ready_items.json"
    review_required_path = stage_dir / "review_required_items.json"
    blocked_path = stage_dir / "blocked_items.json"
    summary_path = stage_dir / "summary.json"
    write_json(queue_path, {"items": _dump_models(outputs.review_queue)})
    write_json(release_ready_path, {"items": _dump_models(outputs.release_ready_items)})
    write_json(review_required_path, {"items": _dump_models(outputs.review_required_items)})
    write_json(blocked_path, {"items": _dump_models(outputs.blocked_items)})
    write_json(summary_path, {**outputs.summary, "stage": "review-export"})
    state.release_ready_items = outputs.release_ready_items
    state.review_required_items = outputs.review_required_items
    state.blocked_items = outputs.blocked_items
    state.review_queue = outputs.review_queue
    return StageResult(
        stage="review-export",
        summary_path=summary_path,
        extra_artifacts=[queue_path, release_ready_path, review_required_path, blocked_path],
    )


def _run_review_merge(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del options
    stage_dir = context.stage_dir("review-merge")
    stage_dir.mkdir(parents=True, exist_ok=True)
    review_data = load_review_data(bundle.config_root)
    outputs = merge_review_decisions(
        release_ready_items=state.release_ready_items,
        review_required_items=state.review_required_items,
        review_queue=state.review_queue,
        review_data=review_data,
    )

    release_ready_path = stage_dir / "release_ready_items.json"
    unresolved_path = stage_dir / "unresolved_items.json"
    rejected_path = stage_dir / "rejected_items.json"
    decision_audit_path = stage_dir / "decision_audit.json"
    summary_path = stage_dir / "summary.json"

    write_json(release_ready_path, {"items": _dump_models(outputs.release_ready_items)})
    write_json(unresolved_path, {"items": _dump_models(outputs.unresolved_items)})
    write_json(rejected_path, {"items": _dump_models(outputs.rejected_items)})
    write_json(decision_audit_path, {"items": _dump_models(outputs.decision_audit)})
    write_json(summary_path, outputs.summary)

    state.release_ready_items = outputs.release_ready_items
    state.review_required_items = outputs.unresolved_items
    state.rejected_review_items = outputs.rejected_items
    state.decision_audit = outputs.decision_audit
    state.review_data_manual_decisions = review_data.manual_decisions
    state.review_data_allowlist = review_data.allowlist
    state.review_data_blocklist = review_data.blocklist
    return StageResult(
        stage="review-merge",
        summary_path=summary_path,
        extra_artifacts=[release_ready_path, unresolved_path, rejected_path, decision_audit_path],
    )


def _run_split(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del options
    stage_dir = context.stage_dir("split")
    stage_dir.mkdir(parents=True, exist_ok=True)
    outputs = assign_splits(
        retained_items=state.release_ready_items,
        duplicate_items=[],
        split_policy=bundle.profiles[context.profile_id].split_policy,
    )

    split_manifest_path = stage_dir / "split_manifest.json"
    leakage_report_path = stage_dir / "leakage_report.json"
    summary_path = stage_dir / "summary.json"

    write_json(split_manifest_path, {"items": _dump_models(outputs.assignments)})
    write_json(leakage_report_path, outputs.leakage_report)
    write_json(
        summary_path,
        {
            "leakage_report": str(leakage_report_path.relative_to(context.run_dir)),
            "retained_count": len(outputs.retained_items),
            "split_counts": dict(Counter(item.split for item in outputs.retained_items if item.split)),
            "stage": "split",
        },
    )
    state.release_ready_items = outputs.retained_items
    state.split_assignments = outputs.assignments
    state.leakage_report = outputs.leakage_report
    return StageResult(stage="split", summary_path=summary_path, extra_artifacts=[split_manifest_path, leakage_report_path])


def _count_by_source(items: list[Any]) -> dict[str, int]:
    return dict(Counter(item.source_id for item in items))


def _synthetic_cap_outcome(real_count: int, synthetic_count: int, synthetic_fraction_max: float) -> dict[str, Any]:
    if synthetic_fraction_max >= 1:
        allowed_synthetic_count = synthetic_count
    else:
        allowed_synthetic_count = floor((synthetic_fraction_max * real_count) / (1 - synthetic_fraction_max)) if real_count else 0
    return {
        "allowed_synthetic_count": allowed_synthetic_count,
        "real_release_ready_count": real_count,
        "status": "ok" if synthetic_count <= allowed_synthetic_count else "blocked",
        "synthetic_fraction_max": synthetic_fraction_max,
        "synthetic_release_ready_count": synthetic_count,
    }


def _build_f1_target_scale_trial_report(
    bundle: ConfigBundle,
    context: RunContext,
    state: PipelineState,
    source_health: dict[str, Any],
    release_summary: dict[str, Any],
    source_stats: dict[str, Any],
) -> dict[str, Any]:
    profile = bundle.profiles[context.profile_id]
    source_rows: list[dict[str, Any]] = []
    candidate_counts = _count_by_source(state.candidates)
    accepted_counts = _count_by_source(state.accepted_items)
    rejected_counts = _count_by_source(state.rejected_items)
    acquired_counts = _count_by_source(state.acquired_items)
    normalized_counts = _count_by_source(state.normalized_items)
    qa_failed_counts = _count_by_source(state.failed_normalized_items)
    retained_counts = _count_by_source(state.retained_items)
    duplicate_counts = _count_by_source(state.duplicate_items)
    release_ready_counts = _count_by_source(state.release_ready_items)
    review_required_counts = _count_by_source(state.review_required_items)
    blocked_counts = _count_by_source(state.blocked_items)
    rejected_review_counts = _count_by_source(state.rejected_review_items)
    benchmark_counts = _count_by_source(state.benchmark_items)
    split_counts_by_source = source_stats["sources_by_split"]
    source_health_by_id = {record["source_id"]: record for record in state.source_health}

    target_execution_blockers: list[str] = []
    for source_id, target_count in F1_SOURCE_TARGETS.items():
        source_release_ready_count = release_ready_counts.get(source_id, 0)
        source_row = {
            "source_id": source_id,
            "target_count": target_count,
            "candidate_count": candidate_counts.get(source_id, 0),
            "accepted_count": accepted_counts.get(source_id, 0),
            "rejected_count": rejected_counts.get(source_id, 0),
            "acquired_count": acquired_counts.get(source_id, 0),
            "normalized_count": normalized_counts.get(source_id, 0),
            "qa_failed_count": qa_failed_counts.get(source_id, 0),
            "retained_after_dedupe_count": retained_counts.get(source_id, 0),
            "duplicate_removed_count": duplicate_counts.get(source_id, 0),
            "release_ready_count": source_release_ready_count,
            "review_required_count": review_required_counts.get(source_id, 0),
            "review_rejected_count": rejected_review_counts.get(source_id, 0),
            "blocked_count": blocked_counts.get(source_id, 0),
            "split_counts": split_counts_by_source.get(source_id, {}),
            "benchmark_item_count": benchmark_counts.get(source_id, 0),
            "source_health_status": source_health_by_id.get(source_id, {}).get("health_status", "missing"),
            "source_skip_reason": source_health_by_id.get(source_id, {}).get("skip_reason"),
        }
        if source_row["candidate_count"] < target_count:
            target_execution_blockers.append(
                f"{source_id} discovered {source_row['candidate_count']} / {target_count} target candidates"
            )
        if source_row["acquired_count"] < target_count:
            target_execution_blockers.append(f"{source_id} acquired {source_row['acquired_count']} / {target_count} target items")
        if source_row["normalized_count"] + source_row["qa_failed_count"] < source_row["acquired_count"]:
            target_execution_blockers.append(f"{source_id} did not account for all acquired items during normalization")
        source_rows.append(source_row)

    real_release_ready_count = sum(row["release_ready_count"] for row in source_rows if row["source_id"] != "project_synthetic")
    synthetic_release_ready_count = release_ready_counts.get("project_synthetic", 0)
    discovered_target_count = sum(row["candidate_count"] for row in source_rows)
    acquired_target_count = sum(row["acquired_count"] for row in source_rows)
    normalized_target_count = sum(row["normalized_count"] for row in source_rows)
    target_candidate_count = F1_REAL_TARGET_COUNT + F1_SYNTHETIC_TARGET_COUNT
    synthetic_cap = _synthetic_cap_outcome(real_release_ready_count, synthetic_release_ready_count, profile.synthetic_fraction_max)
    gate_blockers: list[str] = []
    failed_source_health = [
        source_id
        for source_id in F1_SOURCE_TARGETS
        if source_health_by_id.get(source_id, {}).get("health_status") != "ok"
        or source_health_by_id.get(source_id, {}).get("skip_reason") is not None
    ]
    if failed_source_health:
        gate_blockers.append(f"source-health is not ok for: {', '.join(failed_source_health)}")
    if state.rejected_items:
        gate_blockers.append(f"rights rejected {len(state.rejected_items)} item(s)")
    if state.blocked_items:
        gate_blockers.append(f"privacy/review blocked {len(state.blocked_items)} item(s)")
    if synthetic_cap["status"] != "ok":
        gate_blockers.append(
            "synthetic-cap is blocked after review: "
            f"{synthetic_release_ready_count} synthetic release-ready item(s) exceed "
            f"{synthetic_cap['allowed_synthetic_count']} allowed for {real_release_ready_count} real item(s)"
        )

    near_duplicate_blocker = (
        "F1d remains the next planned hardening step for near-duplicate, source-group, and split-leakage controls "
        "before scale beyond this operator-only trial."
    )
    target_scale_execution_status = "complete" if not target_execution_blockers else "blocked"
    gate_status = "ok" if not gate_blockers else "blocked"
    remaining_blockers = [*target_execution_blockers, *gate_blockers]
    if target_scale_execution_status == "complete":
        remaining_blockers.append(near_duplicate_blocker)

    return {
        "artifact_scope": "operator_only",
        "planning_notation": "F1c",
        "profile_id": context.profile_id,
        "run_id": context.run_id,
        "dry_run": context.dry_run,
        "gate_status": gate_status,
        "status": (
            target_scale_execution_status
            if gate_status == "ok" or target_scale_execution_status == "blocked"
            else "complete_with_gate_blockers"
        ),
        "target_scale_execution_status": target_scale_execution_status,
        "target_counts": {
            "real": F1_REAL_TARGET_COUNT,
            "synthetic": F1_SYNTHETIC_TARGET_COUNT,
            "total": target_candidate_count,
        },
        "source_allocation": dict(F1_SOURCE_TARGETS),
        "target_scale_exercised": {
            "candidate_count": discovered_target_count,
            "acquired_count": acquired_target_count,
            "normalized_count": normalized_target_count,
            "candidate_target_met": discovered_target_count >= target_candidate_count,
            "acquisition_target_met": acquired_target_count >= target_candidate_count,
            "normalization_accounted_for_acquired": (
                normalized_target_count + sum(row["qa_failed_count"] for row in source_rows) >= acquired_target_count
            ),
        },
        "source_outcomes": source_rows,
        "rights_outcomes": {
            "accepted_count": release_summary["accepted_count"],
            "rejected_count": len(state.rejected_items),
            "accepted_rights_classifications": dict(Counter(item.rights_classification.value for item in state.accepted_items)),
            "rejection_reasons": dict(Counter(item.eligibility_reason for item in state.rejected_items)),
            "rights_classifications": source_stats["rights_classifications"],
        },
        "review_outcomes": {
            "release_ready_count": release_summary["release_ready_count"],
            "review_required_count": release_summary["review_required_count"],
            "review_rejected_count": release_summary["review_rejected_count"],
            "blocked_count": release_summary["blocked_count"],
        },
        "dedupe_outcomes": {
            "retained_count": release_summary["retained_count"],
            "duplicate_removed_count": release_summary["duplicate_removed_count"],
            "duplicate_sources": source_stats["duplicate_sources"],
        },
        "split_and_benchmark_eligibility": {
            "real_release_ready_count": real_release_ready_count,
            "synthetic_release_ready_count": synthetic_release_ready_count,
            "split_counts": release_summary["split_counts"],
            "benchmark_id": release_summary["benchmark_id"],
            "benchmark_item_count": release_summary["benchmark_item_count"],
            "benchmark_note": "F1c exercises benchmark selection eligibility; F2 remains responsible for benchmark ground-truth foundations.",
        },
        "gate_outcomes": {
            "benchmark": {
                "benchmark_id": release_summary["benchmark_id"],
                "benchmark_item_count": release_summary["benchmark_item_count"],
                "status": "ok",
            },
            "dedupe": {
                "duplicate_removed_count": release_summary["duplicate_removed_count"],
                "status": "ok",
            },
            "export_portability": {
                "status": "ok",
                "note": "F1c uses build-release artifacts only and does not publish or export a public beta payload.",
            },
            "privacy": {
                "blocked_count": release_summary["blocked_count"],
                "review_required_count": release_summary["review_required_count"],
                "status": "ok" if release_summary["blocked_count"] == 0 else "blocked",
            },
            "review": {
                "release_ready_count": release_summary["release_ready_count"],
                "review_required_count": release_summary["review_required_count"],
                "review_rejected_count": release_summary["review_rejected_count"],
                "status": "ok" if release_summary["blocked_count"] == 0 else "blocked",
            },
            "rights": {
                "accepted_count": release_summary["accepted_count"],
                "rejected_count": len(state.rejected_items),
                "status": "ok" if not state.rejected_items else "blocked",
            },
            "source_health": {
                "failed_sources": failed_source_health,
                "status": "ok" if not failed_source_health else "blocked",
            },
            "split": {
                "split_counts": release_summary["split_counts"],
                "status": "ok",
            },
            "synthetic_cap": synthetic_cap,
        },
        "source_health": source_health,
        "source_depth_feasibility": {
            "report": "discover/source_depth_feasibility.json",
            "operator_note": "F1c consumes source-depth-only inventory only through this explicit target-scale trial mode.",
        },
        "required_gates": [
            "source-health",
            "rights",
            "privacy",
            "review",
            "dedupe",
            "split",
            "benchmark",
            "synthetic-cap",
            "export-portability",
        ],
        "non_goals": [
            "broad live-source crawling",
            "public beta export",
            "release-candidate export",
            "delivery to the HeOCR dataset repo",
            "Hugging Face upload",
            "network-dependent CI",
            "automatic promotion of source-depth-only records into normal public release inputs",
        ],
        "remaining_blockers": remaining_blockers,
        "target_execution_blockers": target_execution_blockers,
        "gate_blockers": gate_blockers,
        "next_step": (
            "F1d near-duplicate/source-group/split-leakage hardening"
            if target_scale_execution_status == "complete"
            else "Resolve F1c target execution blockers before F1d"
        ),
    }


def _run_build_release(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("build_release")
    stage_dir.mkdir(parents=True, exist_ok=True)
    item_manifest_path = stage_dir / "item_manifest.json"
    removed_duplicate_items_path = stage_dir / "removed_duplicate_items.json"
    duplicate_relations_path = stage_dir / "duplicate_relations.json"
    duplicate_clusters_path = stage_dir / "duplicate_clusters.json"
    review_queue_path = stage_dir / "review_queue.json"
    review_required_items_path = stage_dir / "review_required_items.json"
    blocked_items_path = stage_dir / "blocked_items.json"
    decision_audit_path = stage_dir / "decision_audit.json"
    split_manifest_path = stage_dir / "split_manifest.json"
    leakage_report_path = stage_dir / "leakage_report.json"
    release_summary_path = stage_dir / "release_summary.json"
    source_stats_path = stage_dir / "source_stats.json"
    synthetic_composition_path = stage_dir / "synthetic_composition.json"
    annotation_manifest_path = stage_dir / "annotation_manifest.json"
    classification_stats_path = stage_dir / "classification_stats.json"
    privacy_stats_path = stage_dir / "privacy_stats.json"
    benchmark_manifest_path = stage_dir / "benchmark_manifest.json"
    benchmark_selection_audit_path = stage_dir / "benchmark_selection_audit.json"
    benchmark_stability_policy_path = stage_dir / "benchmark_stability_policy.json"
    benchmark_card_path = stage_dir / "BENCHMARK_CARD.md"
    annotation_pilot_manifest_path = stage_dir / "annotation_pilot_manifest.json"
    annotation_pilot_selection_audit_path = stage_dir / "annotation_pilot_selection_audit.json"
    f1_trial_report_path = stage_dir / "f1_target_scale_trial_report.json"
    summary_path = stage_dir / "summary.json"

    retained_source_counts = dict(Counter(item.source_id for item in state.release_ready_items))
    duplicate_source_counts = dict(Counter(item.source_id for item in state.duplicate_items))
    rights_counts = dict(Counter(item.rights_classification.value for item in state.release_ready_items))
    format_counts = dict(Counter(asset.asset_format for item in state.release_ready_items for asset in item.normalized_assets))
    split_counts = dict(Counter(item.split for item in state.release_ready_items if item.split))
    source_split_counts: dict[str, dict[str, int]] = {}
    for item in state.release_ready_items:
        if item.split is None:
            continue
        source_split_counts.setdefault(item.source_id, {})
        source_split_counts[item.source_id][item.split] = source_split_counts[item.source_id].get(item.split, 0) + 1
    qa_fail_reasons = dict(Counter(reason for item in state.failed_normalized_items for reason in item.qa_fail_reasons))
    classification_stats = {
        "content_class": dict(Counter(item.content_class for item in state.classified_items)),
        "period_class": dict(Counter(item.period_class for item in state.classified_items)),
        "language_class": dict(Counter(item.language_class for item in state.classified_items)),
        "quality_tier": dict(Counter(item.quality_tier for item in state.classified_items)),
        "low_confidence_reason": dict(Counter(reason for item in state.classified_items for reason in item.classification_review_reasons)),
    }
    privacy_stats = {
        "privacy_flag": dict(Counter(item.privacy_flag.value for item in state.privacy_scanned_items)),
        "privacy_reason": dict(Counter(reason for item in state.privacy_scanned_items for reason in item.privacy_reasons)),
        "source_id": dict(Counter(item.source_id for item in state.privacy_scanned_items)),
    }
    synthetic_composition = synthetic_composition_report(state.release_ready_items)
    annotation_manifest = build_annotation_manifest(state.release_ready_items, subset_id="release_ready")
    try:
        benchmark_config = load_benchmark_config(bundle.config_root)
    except ConfigValidationError as exc:
        raise StageExecutionError(f"benchmark config validation failed: {exc}") from exc
    benchmark_outputs = select_benchmark_items(
        config=benchmark_config,
        release_ready_items=state.release_ready_items,
        review_required_items=state.review_required_items,
        blocked_items=state.blocked_items,
        removed_duplicate_items=state.duplicate_items,
    )
    state.benchmark_items = benchmark_outputs.items
    state.benchmark_selection_audit = benchmark_outputs.audit
    state.benchmark_stability_policy = benchmark_outputs.stability_policy
    state.benchmark_card_markdown = benchmark_outputs.card_markdown
    try:
        annotation_pilot_config = load_annotation_pilot_config(bundle.config_root)
    except ConfigValidationError as exc:
        raise StageExecutionError(f"annotation pilot config validation failed: {exc}") from exc
    annotation_pilot_outputs = select_annotation_pilot_items(
        config=annotation_pilot_config,
        release_ready_items=state.release_ready_items,
        benchmark_items=state.benchmark_items,
    )
    state.annotation_pilot_manifest = annotation_pilot_outputs.manifest
    state.annotation_pilot_selection_audit = annotation_pilot_outputs.audit

    write_json(item_manifest_path, {"items": _dump_models(state.release_ready_items)})
    write_json(removed_duplicate_items_path, {"items": _dump_models(state.duplicate_items)})
    write_json(duplicate_relations_path, {"items": _dump_models(state.duplicate_relations)})
    write_json(duplicate_clusters_path, {"items": _dump_models(state.duplicate_clusters)})
    write_json(review_queue_path, {"items": _dump_models(state.review_queue)})
    write_json(review_required_items_path, {"items": _dump_models(state.review_required_items)})
    write_json(blocked_items_path, {"items": _dump_models(state.blocked_items)})
    write_json(decision_audit_path, {"items": _dump_models(state.decision_audit)})
    write_json(split_manifest_path, {"items": _dump_models(state.split_assignments)})
    write_json(leakage_report_path, state.leakage_report)
    write_json(classification_stats_path, classification_stats)
    write_json(privacy_stats_path, privacy_stats)
    write_json(synthetic_composition_path, synthetic_composition)
    write_json(annotation_manifest_path, annotation_manifest.model_dump(mode="json"))
    write_json(benchmark_manifest_path, {"items": _dump_models(state.benchmark_items)})
    write_json(benchmark_selection_audit_path, {"items": _dump_models(state.benchmark_selection_audit)})
    write_json(benchmark_stability_policy_path, state.benchmark_stability_policy)
    benchmark_card_path.write_text(state.benchmark_card_markdown, encoding="utf-8")
    write_json(annotation_pilot_manifest_path, state.annotation_pilot_manifest.model_dump(mode="json"))
    write_json(annotation_pilot_selection_audit_path, {"items": _dump_models(state.annotation_pilot_selection_audit)})
    source_stats = {
        "asset_formats": format_counts,
        "duplicate_sources": duplicate_source_counts,
        "qa_fail_reasons": qa_fail_reasons,
        "rights_classifications": rights_counts,
        "source_health": source_health_summary(state.source_health),
        "sources": retained_source_counts,
        "sources_by_split": source_split_counts,
        "splits": split_counts,
        "synthetic_composition": synthetic_composition,
    }
    release_summary = {
        "accepted_count": len(state.accepted_items),
        "acquired_count": len(state.acquired_items),
        "blocked_count": len(state.blocked_items),
        "duplicate_removed_count": len(state.duplicate_items),
        "is_dry_run": context.dry_run,
        "normalized_count": len(state.normalized_items),
        "profile_id": context.profile_id,
        "publish_targets": [target.value for target in bundle.profiles[context.profile_id].publish_targets],
        "qa_failed_count": len(state.failed_normalized_items),
        "real_items": sum(1 for item in state.release_ready_items if not item.is_synthetic),
        "release_ready_count": len(state.release_ready_items),
        "retained_count": len(state.retained_items),
        "review_approved_count": sum(
            1
            for record in state.decision_audit
            if record.outcome == "release_ready" and record.decision_source in {"manual_decision", "allowlist"}
        ),
        "review_rejected_count": len(state.rejected_review_items),
        "review_required_count": len(state.review_required_items),
        "review_unresolved_count": len(state.review_required_items),
        "split_counts": split_counts,
        "synthetic_items": sum(1 for item in state.release_ready_items if item.is_synthetic),
        "synthetic_composition": synthetic_composition,
        "annotation_manifest": {
            "annotated_item_count": annotation_manifest.annotated_item_count,
            "transcription_item_count": annotation_manifest.transcription_item_count,
            "layout_label_item_count": annotation_manifest.layout_label_item_count,
            "transcription_required": annotation_manifest.transcription_required,
            "layout_labels_required": annotation_manifest.layout_labels_required,
        },
        "benchmark_id": benchmark_outputs.config.benchmark_id,
        "benchmark_item_count": len(state.benchmark_items),
        "annotation_pilot": {
            "pilot_id": annotation_pilot_outputs.config.pilot_id,
            "pilot_item_count": annotation_pilot_outputs.manifest.pilot_item_count,
            "transcription_task_count": annotation_pilot_outputs.manifest.transcription_task_count,
            "layout_label_task_count": annotation_pilot_outputs.manifest.layout_label_task_count,
            "transcription_required_for_release": annotation_pilot_outputs.manifest.transcription_required_for_release,
            "layout_labels_required_for_release": annotation_pilot_outputs.manifest.layout_labels_required_for_release,
        },
    }
    write_json(source_stats_path, source_stats)
    write_json(release_summary_path, release_summary)
    extra_artifacts = [
        item_manifest_path,
        removed_duplicate_items_path,
        duplicate_relations_path,
        duplicate_clusters_path,
        review_queue_path,
        review_required_items_path,
        blocked_items_path,
        decision_audit_path,
        split_manifest_path,
        leakage_report_path,
        release_summary_path,
        source_stats_path,
        synthetic_composition_path,
        annotation_manifest_path,
        classification_stats_path,
        privacy_stats_path,
        benchmark_manifest_path,
        benchmark_selection_audit_path,
        benchmark_stability_policy_path,
        benchmark_card_path,
        annotation_pilot_manifest_path,
        annotation_pilot_selection_audit_path,
    ]
    summary_extra: dict[str, Any] = {}
    if options and options.f1_target_scale_trial:
        f1_trial_report = _build_f1_target_scale_trial_report(
            bundle,
            context,
            state,
            source_stats["source_health"],
            release_summary,
            source_stats,
        )
        write_json(f1_trial_report_path, f1_trial_report)
        extra_artifacts.append(f1_trial_report_path)
        summary_extra["f1_target_scale_trial_report"] = str(f1_trial_report_path.relative_to(context.run_dir))
    write_json(
        summary_path,
        {
            "blocked_items": str(blocked_items_path.relative_to(context.run_dir)),
            "benchmark_card": str(benchmark_card_path.relative_to(context.run_dir)),
            "benchmark_manifest": str(benchmark_manifest_path.relative_to(context.run_dir)),
            "benchmark_selection_audit": str(benchmark_selection_audit_path.relative_to(context.run_dir)),
            "benchmark_stability_policy": str(benchmark_stability_policy_path.relative_to(context.run_dir)),
            "annotation_pilot_manifest": str(annotation_pilot_manifest_path.relative_to(context.run_dir)),
            "annotation_pilot_selection_audit": str(annotation_pilot_selection_audit_path.relative_to(context.run_dir)),
            "classification_stats": str(classification_stats_path.relative_to(context.run_dir)),
            "decision_audit": str(decision_audit_path.relative_to(context.run_dir)),
            "duplicate_clusters": str(duplicate_clusters_path.relative_to(context.run_dir)),
            "duplicate_relations": str(duplicate_relations_path.relative_to(context.run_dir)),
            "item_manifest": str(item_manifest_path.relative_to(context.run_dir)),
            "leakage_report": str(leakage_report_path.relative_to(context.run_dir)),
            "privacy_stats": str(privacy_stats_path.relative_to(context.run_dir)),
            "removed_duplicate_items": str(removed_duplicate_items_path.relative_to(context.run_dir)),
            "release_summary": str(release_summary_path.relative_to(context.run_dir)),
            "review_queue": str(review_queue_path.relative_to(context.run_dir)),
            "review_required_items": str(review_required_items_path.relative_to(context.run_dir)),
            "split_manifest": str(split_manifest_path.relative_to(context.run_dir)),
            "source_stats": str(source_stats_path.relative_to(context.run_dir)),
            "synthetic_composition": str(synthetic_composition_path.relative_to(context.run_dir)),
            "annotation_manifest": str(annotation_manifest_path.relative_to(context.run_dir)),
            "stage": "build-release",
            **summary_extra,
        },
    )
    return StageResult(
        stage="build-release",
        summary_path=summary_path,
        extra_artifacts=extra_artifacts,
    )


def execute_pipeline(
    target_stage: str,
    bundle: ConfigBundle,
    context: RunContext,
    options: StageOptions,
    *,
    initial_state: PipelineState | None = None,
    start_stage: str | None = None,
) -> list[StageResult]:
    state = initial_state or empty_pipeline_state()
    results: list[StageResult] = []
    start_index = 0
    if start_stage is not None:
        if start_stage not in PIPELINE_STAGES:
            raise StageExecutionError(f"unknown start stage: {start_stage}")
        start_index = PIPELINE_STAGES.index(start_stage)
    for stage in PIPELINE_STAGES[start_index:]:
        if stage == "discover":
            results.append(_run_discover(bundle, context, options, state))
            candidates_path = context.stage_dir("discover") / "candidates.json"
            state.candidates = [CandidateRecord.model_validate(item) for item in load_json(candidates_path)["items"]]
        elif stage == "fetch-metadata":
            results.append(_run_fetch_metadata(bundle, context, options, state))
        elif stage == "policy-filter":
            results.append(_run_policy_filter(bundle, context, options, state))
        elif stage == "acquire":
            results.append(_run_acquire(bundle, context, options, state))
        elif stage == "normalize":
            results.append(_run_normalize(bundle, context, options, state))
        elif stage == "dedupe":
            results.append(_run_dedupe(bundle, context, options, state))
        elif stage == "classify":
            results.append(_run_classify(bundle, context, options, state))
        elif stage == "privacy-scan":
            results.append(_run_privacy_scan(bundle, context, options, state))
        elif stage == "review-export":
            results.append(_run_review_export(bundle, context, options, state))
        elif stage == "review-merge":
            results.append(_run_review_merge(bundle, context, options, state))
        elif stage == "split":
            results.append(_run_split(bundle, context, options, state))
        elif stage == "build-release":
            results.append(_run_build_release(bundle, context, options, state))
        if stage == target_stage:
            break
    return results


def load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
