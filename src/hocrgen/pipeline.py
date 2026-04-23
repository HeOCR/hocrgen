from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from math import floor
from pathlib import Path
from typing import Any

from hocrgen.classify.heuristics import classify_items
from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import LicenseEntry, SourceConfig
from hocrgen.core.context import RunContext
from hocrgen.core.errors import StageExecutionError
from hocrgen.dedupe.exact import deduplicate_items
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.biblia import BibliaImporter
from hocrgen.fetchers.nli import NliFetcher
from hocrgen.fetchers.pinkas import PinkasImporter
from hocrgen.fetchers.synthetic import SyntheticFetcher
from hocrgen.manifests.io import write_json
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
    ReviewOverrideRecord,
    ReviewDecisionRecord,
    SplitAssignmentRecord,
)
from hocrgen.review.merge import load_review_data, merge_review_decisions
from hocrgen.normalize.metadata import normalize_items
from hocrgen.parsers.rights import classify_eligibility, normalize_rights
from hocrgen.privacy.rules import apply_privacy_rules
from hocrgen.review.queue import export_review_queue
from hocrgen.split.assign import assign_splits


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


def _selected_sources(bundle: ConfigBundle, profile_id: str, options: StageOptions) -> list[SourceConfig]:
    profile = bundle.profiles[profile_id]
    exclude_ids = set(profile.exclude_sources)
    sources_by_id = {source.id: source for source in bundle.source_registry.sources}
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
                ItemRecord(
                    **item.model_dump(),
                    eligibility="rejected",
                    eligibility_reason="synthetic_fraction_exceeded",
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


def _run_discover(bundle: ConfigBundle, context: RunContext, options: StageOptions) -> StageResult:
    stage_dir = context.stage_dir("discover")
    stage_dir.mkdir(parents=True, exist_ok=True)
    selected_sources = _selected_sources(bundle, context.profile_id, options)
    candidates: list[CandidateRecord] = []
    for source in selected_sources:
        candidates.extend(FETCHERS[source.fetcher].discover_candidates(source, bundle, options))

    manifest_path = stage_dir / "candidates.json"
    summary_path = stage_dir / "summary.json"
    write_json(manifest_path, {"items": _dump_models(candidates)})
    write_json(
        summary_path,
        {
            "candidate_count": len(candidates),
            "included_sources": [source.id for source in selected_sources],
            "stage": "discover",
        },
    )
    return StageResult(stage="discover", summary_path=summary_path, extra_artifacts=[manifest_path])


def _run_fetch_metadata(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("fetch_metadata")
    stage_dir.mkdir(parents=True, exist_ok=True)
    selected_sources = _selected_sources(bundle, context.profile_id, options)
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
    selected_sources = {source.id: source for source in _selected_sources(bundle, context.profile_id, options)}
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
    selected_sources = {source.id: source for source in _selected_sources(bundle, context.profile_id, options)}
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


def _run_build_release(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    del options
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
    classification_stats_path = stage_dir / "classification_stats.json"
    privacy_stats_path = stage_dir / "privacy_stats.json"
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
    write_json(
        source_stats_path,
        {
            "asset_formats": format_counts,
            "duplicate_sources": duplicate_source_counts,
            "qa_fail_reasons": qa_fail_reasons,
            "rights_classifications": rights_counts,
            "sources": retained_source_counts,
            "sources_by_split": source_split_counts,
            "splits": split_counts,
        },
    )
    write_json(
        release_summary_path,
        {
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
        },
    )
    write_json(
        summary_path,
        {
            "blocked_items": str(blocked_items_path.relative_to(context.run_dir)),
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
            "stage": "build-release",
        },
    )
    return StageResult(
        stage="build-release",
        summary_path=summary_path,
        extra_artifacts=[
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
            classification_stats_path,
            privacy_stats_path,
        ],
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
            results.append(_run_discover(bundle, context, options))
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
