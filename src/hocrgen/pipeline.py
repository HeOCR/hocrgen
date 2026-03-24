from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import floor
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import LicenseEntry, SourceConfig
from hocrgen.core.context import RunContext
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.biblia import BibliaImporter
from hocrgen.fetchers.nli import NliFetcher
from hocrgen.fetchers.pinkas import PinkasImporter
from hocrgen.fetchers.synthetic import SyntheticFetcher
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import AcquiredItemRecord, CandidateRecord, EnrichedCandidateRecord, ItemRecord
from hocrgen.parsers.rights import classify_eligibility, normalize_rights


STAGE_ORDER = ("discover", "fetch-metadata", "policy-filter", "acquire", "build-release")


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
    candidates: list[CandidateRecord]
    enriched_candidates: list[EnrichedCandidateRecord]
    accepted_items: list[ItemRecord]
    rejected_items: list[ItemRecord]
    acquired_items: list[AcquiredItemRecord]


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
    sources = [source for source in bundle.source_registry.sources if source.id in profile.include_sources]
    if options.source_filter:
        sources = [source for source in sources if source.id in options.source_filter]
    return sources


def _licenses_by_id(bundle: ConfigBundle) -> dict[str, LicenseEntry]:
    return {license_entry.id: license_entry for license_entry in bundle.licenses.licenses}


def _dump_models(items) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def _apply_synthetic_cap(accepted_items: list[ItemRecord], rejected_items: list[ItemRecord], synthetic_fraction_max: float) -> tuple[list[ItemRecord], list[ItemRecord]]:
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
            "source_name": source.name,
            "fetcher": source.fetcher,
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
    candidates_by_source = {source.id: [candidate for candidate in state.candidates if candidate.source_id == source.id] for source in selected_sources}
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
            "stage": "fetch-metadata",
            "rights_samples": sorted({item.raw_rights_text for item in enriched if item.raw_rights_text}),
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

    accepted, rejected = _apply_synthetic_cap(accepted, rejected, bundle.profiles[context.profile_id].synthetic_fraction_max)
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


def _run_build_release(bundle: ConfigBundle, context: RunContext, options: StageOptions, state: PipelineState) -> StageResult:
    stage_dir = context.stage_dir("build_release")
    stage_dir.mkdir(parents=True, exist_ok=True)
    item_manifest_path = stage_dir / "item_manifest.json"
    release_summary_path = stage_dir / "release_summary.json"
    source_stats_path = stage_dir / "source_stats.json"
    summary_path = stage_dir / "summary.json"

    source_counts = dict(Counter(item.source_id for item in state.acquired_items))
    rights_counts = dict(Counter(item.rights_classification.value for item in state.acquired_items))
    write_json(item_manifest_path, {"items": _dump_models(state.acquired_items)})
    write_json(source_stats_path, {"sources": source_counts, "rights_classifications": rights_counts})
    write_json(
        release_summary_path,
        {
            "accepted_count": len(state.accepted_items),
            "acquired_count": len(state.acquired_items),
            "is_dry_run": context.dry_run,
            "profile_id": context.profile_id,
            "publish_targets": [target.value for target in bundle.profiles[context.profile_id].publish_targets],
            "real_items": sum(1 for item in state.acquired_items if not item.is_synthetic),
            "synthetic_items": sum(1 for item in state.acquired_items if item.is_synthetic),
        },
    )
    write_json(
        summary_path,
        {
            "item_manifest": str(item_manifest_path.relative_to(context.run_dir)),
            "release_summary": str(release_summary_path.relative_to(context.run_dir)),
            "source_stats": str(source_stats_path.relative_to(context.run_dir)),
            "stage": "build-release",
        },
    )
    return StageResult(stage="build-release", summary_path=summary_path, extra_artifacts=[item_manifest_path, release_summary_path, source_stats_path])


def execute_pipeline(target_stage: str, bundle: ConfigBundle, context: RunContext, options: StageOptions) -> list[StageResult]:
    state = PipelineState(candidates=[], enriched_candidates=[], accepted_items=[], rejected_items=[], acquired_items=[])
    results: list[StageResult] = []
    for stage in STAGE_ORDER:
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
        elif stage == "build-release":
            results.append(_run_build_release(bundle, context, options, state))
        if stage == target_stage:
            break
    return results


def load_json(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))
