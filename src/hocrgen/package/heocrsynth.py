from __future__ import annotations

import shutil
from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hocrgen.annotations import build_annotation_manifest
from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import ReleaseProfile, SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import (
    AlphaExportedItemRecord,
    CuratedItemRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    ExportedAssetRecord,
    PrivacyScannedItemRecord,
    ReleaseDiffRecord,
    ReviewQueueRecord,
    SplitAssignmentRecord,
    SyntheticReleaseRecord,
)
from hocrgen.package.alpha import (
    REPO_ROOT,
    _benchmark_card_for_export,
    _build_classification_stats,
    _build_privacy_stats,
    _build_release_diff,
    _build_source_stats,
    _changelog_doc,
    _copy_benchmark_reference_files,
    _filter_annotation_pilot_manifest,
    _filter_benchmark_leakage_risk,
    _filter_benchmark_reference_manifest,
    _filter_benchmark_reference_status,
    _load_annotation_pilot_export_inputs,
    _load_benchmark_export_inputs,
    _load_json,
    _load_models,
    _natural_sort_key,
    _ordered_sources,
    _parse_exported_at,
    _public_item_payload,
    _review_queue_payloads,
    _synthetic_composition_lines,
    _validate_release_diff_baseline,
    _write_markdown,
    _current_commit_sha,
)
from hocrgen.synthetic.reporting import synthetic_composition_report


@dataclass(frozen=True)
class SyntheticExportConfig:
    version: str
    output_dir: Path | None = None
    heocrsynth_repo: Path | None = None
    compare_to: Path | None = None
    max_synthetic_items: int = 20
    overwrite: bool = False


@dataclass(frozen=True)
class SyntheticExportResult:
    export_dir: Path
    summary_path: Path
    release_record_path: Path
    item_manifest_path: Path
    artifact_paths: list[Path]


def export_synthetic_release(
    bundle: ConfigBundle,
    run_dir: Path,
    profile_id: str,
    config: SyntheticExportConfig,
) -> SyntheticExportResult:
    _validate_synthetic_export_config(config)
    profile = bundle.profiles[profile_id]
    build_dir = run_dir / "build_release"
    handoff_repo_root = None
    export_dir = (run_dir.parent.parent / "exports" / config.version).resolve()
    if config.output_dir and config.heocrsynth_repo:
        raise StageExecutionError("--output-dir and --heocrsynth-repo cannot be used together")
    if config.heocrsynth_repo:
        handoff_repo_root = _validate_heocrsynth_repo_root(config.heocrsynth_repo)
        export_dir = (handoff_repo_root / "releases" / config.version).resolve()
    elif config.output_dir:
        export_dir = config.output_dir.resolve()
    if export_dir.exists():
        if not config.overwrite:
            raise StageExecutionError(f"synthetic export directory already exists: {export_dir}")
        _validate_synthetic_overwrite_target(export_dir, config.version)

    release_items = _load_models(build_dir / "item_manifest.json", PrivacyScannedItemRecord)
    review_required_items = _load_models(build_dir / "review_required_items.json", PrivacyScannedItemRecord)
    blocked_items = _load_models(build_dir / "blocked_items.json", PrivacyScannedItemRecord)
    split_manifest = _load_models(build_dir / "split_manifest.json", SplitAssignmentRecord)
    duplicate_relations = _load_models(build_dir / "duplicate_relations.json", DuplicateRelationRecord)
    duplicate_clusters = _load_models(build_dir / "duplicate_clusters.json", DuplicateClusterRecord)
    removed_duplicate_items = _load_models(build_dir / "removed_duplicate_items.json", CuratedItemRecord)
    review_queue = _load_models(build_dir / "review_queue.json", ReviewQueueRecord)
    benchmark_inputs = _load_benchmark_export_inputs(build_dir)
    annotation_pilot_inputs = _load_annotation_pilot_export_inputs(build_dir)
    build_release_summary = _load_json(build_dir / "release_summary.json")
    if build_release_summary.get("near_duplicate_review_status") == "blocked":
        cluster_count = build_release_summary.get("near_duplicate_cluster_count", 0)
        raise StageExecutionError(
            f"synthetic export is blocked: {cluster_count} near-duplicate cluster(s) require manual review"
        )
    if build_release_summary.get("benchmark_holdout_leakage_status") == "blocked":
        unresolved_count = (benchmark_inputs.leakage_risk or {}).get("unresolved_count", 0)
        raise StageExecutionError(
            "synthetic export is blocked: "
            f"{unresolved_count} unresolved benchmark/holdout leakage group(s)"
        )

    selected_items = _select_synthetic_items(release_items, config)
    if not selected_items:
        raise StageExecutionError("synthetic export selection is empty")

    selected_ids = {item.item_id for item in selected_items}
    selected_benchmark_items = [item for item in benchmark_inputs.items if item.item_id in selected_ids]
    selected_benchmark_ids = {item.item_id for item in selected_benchmark_items}
    selected_benchmark_audit = [
        item for item in benchmark_inputs.selection_audit if item.item_id in selected_benchmark_ids
    ]
    synthetic_benchmark_policy = _synthetic_benchmark_stability_policy(benchmark_inputs.stability_policy)
    synthetic_benchmark_inputs = replace(benchmark_inputs, stability_policy=synthetic_benchmark_policy)
    benchmark_card = _synthetic_benchmark_card(_benchmark_card_for_export(synthetic_benchmark_inputs, selected_benchmark_items))
    selected_benchmark_reference_manifest = _filter_benchmark_reference_manifest(
        benchmark_inputs.reference_manifest,
        selected_ids,
    )
    selected_benchmark_reference_status = _filter_benchmark_reference_status(
        benchmark_inputs.reference_status,
        selected_ids,
    )
    selected_benchmark_leakage_risk = _filter_synthetic_benchmark_leakage_risk(
        benchmark_inputs.leakage_risk,
        selected_ids,
    )
    included_sources = _ordered_sources(profile, {item.source_id for item in selected_items})
    selected_split_manifest = [assignment for assignment in split_manifest if assignment.item_id in selected_ids]
    synthetic_review_required_items = [item for item in review_required_items if item.is_synthetic]
    synthetic_blocked_items = [item for item in blocked_items if item.is_synthetic]
    synthetic_review_required_ids = {item.item_id for item in synthetic_review_required_items}
    selected_review_queue = [entry for entry in review_queue if entry.item_id in synthetic_review_required_ids]
    selected_duplicate_relations = [
        relation
        for relation in duplicate_relations
        if relation.canonical_item_id in selected_ids and relation.duplicate_item_id in selected_ids
    ]
    selected_duplicate_cluster_ids = {relation.cluster_id for relation in selected_duplicate_relations}
    selected_duplicate_clusters = [
        cluster
        for cluster in duplicate_clusters
        if cluster.cluster_id in selected_duplicate_cluster_ids
    ]
    synthetic_removed_duplicate_items = [item for item in removed_duplicate_items if item.is_synthetic]

    if export_dir.exists():
        shutil.rmtree(export_dir)
    exported_items = _copy_synthetic_export_assets(selected_items, export_dir / "data" / "synthetic")
    exported_benchmark_reference_files = _copy_benchmark_reference_files(
        selected_benchmark_reference_manifest,
        build_dir,
        export_dir,
    )
    source_stats = _build_source_stats(exported_items, selected_duplicate_relations)
    classification_stats = _build_classification_stats(exported_items)
    privacy_stats = _build_privacy_stats(exported_items)
    synthetic_composition = synthetic_composition_report(exported_items)
    annotation_manifest = build_annotation_manifest(exported_items, subset_id="heocrsynth_export")
    exported_annotation_pilot_manifest = _filter_annotation_pilot_manifest(annotation_pilot_inputs.manifest, selected_ids)
    selected_annotation_pilot_ids = {item.item_id for item in exported_annotation_pilot_manifest.items}
    selected_annotation_pilot_audit = [
        item for item in annotation_pilot_inputs.selection_audit if item.item_id in selected_annotation_pilot_ids
    ]
    split_counts = dict(Counter(item.split for item in exported_items if item.split))
    exported_at = datetime.now(UTC).isoformat()
    commit_sha = _current_commit_sha()
    release_record = SyntheticReleaseRecord(
        version=config.version,
        profile_id=profile_id,
        included_sources=included_sources,
        split_counts=split_counts,
        synthetic_items=len(exported_items),
        review_required_count=len(synthetic_review_required_items),
        blocked_count=len(synthetic_blocked_items),
        hocrgen_commit=commit_sha,
        exported_at=exported_at,
    )
    release_summary = {
        "accepted_count": build_release_summary["accepted_count"],
        "blocked_count": len(synthetic_blocked_items),
        "dataset_id": "HeOCRsynth",
        "exported_item_count": len(exported_items),
        "exported_real_items": 0,
        "exported_synthetic_items": len(exported_items),
        "is_dry_run": build_release_summary["is_dry_run"],
        "max_synthetic_items": config.max_synthetic_items,
        "normalized_count": build_release_summary["normalized_count"],
        "profile_id": profile_id,
        "real_items": 0,
        "release_kind": "synthetic_only",
        "release_ready_count": build_release_summary["release_ready_count"],
        "retained_count": build_release_summary["retained_count"],
        "review_required_count": len(synthetic_review_required_items),
        "split_counts": split_counts,
        "synthetic_items": len(exported_items),
        "synthetic_only": True,
        "synthetic_composition": synthetic_composition,
        "annotation_manifest": {
            "annotated_item_count": annotation_manifest.annotated_item_count,
            "transcription_item_count": annotation_manifest.transcription_item_count,
            "layout_label_item_count": annotation_manifest.layout_label_item_count,
            "transcription_required": annotation_manifest.transcription_required,
            "layout_labels_required": annotation_manifest.layout_labels_required,
        },
        "annotation_pilot": {
            "pilot_id": exported_annotation_pilot_manifest.pilot_id,
            "pilot_item_count": exported_annotation_pilot_manifest.pilot_item_count,
            "transcription_task_count": exported_annotation_pilot_manifest.transcription_task_count,
            "layout_label_task_count": exported_annotation_pilot_manifest.layout_label_task_count,
            "transcription_required_for_release": exported_annotation_pilot_manifest.transcription_required_for_release,
            "layout_labels_required_for_release": exported_annotation_pilot_manifest.layout_labels_required_for_release,
        },
        "benchmark_references": {
            "reference_manifest_id": (
                selected_benchmark_reference_manifest.reference_manifest_id
                if selected_benchmark_reference_manifest is not None
                else None
            ),
            "reference_ready_count": (
                selected_benchmark_reference_status.counts.get("reference_ready", 0)
                if selected_benchmark_reference_status is not None
                else 0
            ),
            "draft_or_blocked_count": (
                selected_benchmark_reference_status.counts.get("blocked_or_draft", 0)
                if selected_benchmark_reference_status is not None
                else 0
            ),
            "versioning_status": (
                benchmark_inputs.reference_versioning or {}
            ).get("status", "not_available"),
        },
        "version": config.version,
    }
    baseline_dir = _resolve_synthetic_comparison_release(export_dir, config)
    release_diff = _build_release_diff(
        version=config.version,
        generated_at=exported_at,
        current_items=exported_items,
        baseline_dir=baseline_dir,
        review_required_items=synthetic_review_required_items,
        blocked_items=synthetic_blocked_items,
        removed_duplicate_items=synthetic_removed_duplicate_items,
        build_release_items=[item for item in release_items if item.is_synthetic],
    )

    manifests_dir = export_dir / "manifests"
    docs_dir = export_dir / "docs"
    write_json(manifests_dir / "item_manifest.json", {"items": [_public_item_payload(item) for item in exported_items]})
    write_json(manifests_dir / "split_manifest.json", {"items": [item.model_dump(mode="json") for item in selected_split_manifest]})
    write_json(manifests_dir / "source_stats.json", source_stats)
    write_json(manifests_dir / "synthetic_composition.json", synthetic_composition)
    write_json(manifests_dir / "annotation_manifest.json", annotation_manifest.model_dump(mode="json"))
    write_json(manifests_dir / "annotation_pilot_manifest.json", exported_annotation_pilot_manifest.model_dump(mode="json"))
    write_json(
        manifests_dir / "annotation_pilot_selection_audit.json",
        {"items": [item.model_dump(mode="json") for item in selected_annotation_pilot_audit]},
    )
    write_json(manifests_dir / "classification_stats.json", classification_stats)
    write_json(manifests_dir / "privacy_stats.json", privacy_stats)
    write_json(manifests_dir / "release_summary.json", release_summary)
    write_json(manifests_dir / "duplicate_relations.json", {"items": [item.model_dump(mode="json") for item in selected_duplicate_relations]})
    write_json(manifests_dir / "duplicate_clusters.json", {"items": [item.model_dump(mode="json") for item in selected_duplicate_clusters]})
    write_json(manifests_dir / "review_required_items.json", {"items": [_synthetic_audit_item_payload(item) for item in synthetic_review_required_items]})
    write_json(manifests_dir / "blocked_items.json", {"items": [_synthetic_audit_item_payload(item) for item in synthetic_blocked_items]})
    write_json(
        manifests_dir / "review_queue.json",
        {"items": _review_queue_payloads(selected_review_queue, export_dir)},
    )
    write_json(manifests_dir / "release_record.json", release_record.model_dump(mode="json"))
    write_json(manifests_dir / "release_diff.json", release_diff.model_dump(mode="json"))
    write_json(manifests_dir / "benchmark_manifest.json", {"items": [item.model_dump(mode="json") for item in selected_benchmark_items]})
    if selected_benchmark_leakage_risk is not None:
        write_json(manifests_dir / "benchmark_leakage_risk.json", selected_benchmark_leakage_risk)
    write_json(
        manifests_dir / "benchmark_selection_audit.json",
        {"items": [item.model_dump(mode="json") for item in selected_benchmark_audit]},
    )
    write_json(manifests_dir / "benchmark_stability_policy.json", synthetic_benchmark_policy)
    if selected_benchmark_reference_manifest is not None:
        write_json(
            manifests_dir / "benchmark_reference_manifest.json",
            selected_benchmark_reference_manifest.model_dump(mode="json"),
        )
    if selected_benchmark_reference_status is not None:
        write_json(
            manifests_dir / "benchmark_reference_status.json",
            selected_benchmark_reference_status.model_dump(mode="json"),
        )
    if benchmark_inputs.reference_versioning is not None:
        write_json(manifests_dir / "benchmark_reference_versioning.json", benchmark_inputs.reference_versioning)

    _write_markdown(
        docs_dir / "DATASET_CARD.md",
        _dataset_card(config.version, profile, exported_items, synthetic_review_required_items, synthetic_blocked_items, included_sources),
    )
    _write_markdown(
        docs_dir / "RELEASE_NOTES.md",
        _release_notes(config.version, release_summary, source_stats, included_sources, release_diff),
    )
    _write_markdown(docs_dir / "CHANGELOG.md", _changelog_doc(config.version, release_diff))
    _write_markdown(
        docs_dir / "PROVENANCE.md",
        _provenance_doc(bundle, profile, included_sources, exported_at, commit_sha),
    )
    _write_markdown(
        docs_dir / "HANDOFF.md",
        _handoff_doc(
            config.version,
            export_dir,
            profile,
            release_summary,
            included_sources,
            commit_sha,
            handoff_repo_root,
        ),
    )
    _write_markdown(docs_dir / "BENCHMARK_CARD.md", benchmark_card)

    summary_path = run_dir / "export_synthetic" / "summary.json"
    write_json(
        summary_path,
        {
            "dataset_id": "HeOCRsynth",
            "export_dir": str(export_dir),
            "handoff_repo": str(handoff_repo_root) if handoff_repo_root else None,
            "item_manifest": "manifests/item_manifest.json",
            "release_diff": "manifests/release_diff.json",
            "release_record": "manifests/release_record.json",
            "release_summary": "manifests/release_summary.json",
            "annotation_manifest": "manifests/annotation_manifest.json",
            "annotation_pilot_manifest": "manifests/annotation_pilot_manifest.json",
            "annotation_pilot_selection_audit": "manifests/annotation_pilot_selection_audit.json",
            "benchmark_reference_manifest": (
                "manifests/benchmark_reference_manifest.json"
                if selected_benchmark_reference_manifest is not None
                else None
            ),
            "benchmark_leakage_risk": (
                "manifests/benchmark_leakage_risk.json"
                if selected_benchmark_leakage_risk is not None
                else None
            ),
            "benchmark_reference_status": (
                "manifests/benchmark_reference_status.json"
                if selected_benchmark_reference_status is not None
                else None
            ),
            "benchmark_reference_versioning": (
                "manifests/benchmark_reference_versioning.json"
                if benchmark_inputs.reference_versioning is not None
                else None
            ),
            "stage": "export-synthetic",
            "synthetic_composition": "manifests/synthetic_composition.json",
            "synthetic_only": True,
            "version": config.version,
        },
    )
    artifact_paths = [
        manifests_dir / "item_manifest.json",
        manifests_dir / "split_manifest.json",
        manifests_dir / "source_stats.json",
        manifests_dir / "synthetic_composition.json",
        manifests_dir / "annotation_manifest.json",
        manifests_dir / "annotation_pilot_manifest.json",
        manifests_dir / "annotation_pilot_selection_audit.json",
        manifests_dir / "classification_stats.json",
        manifests_dir / "privacy_stats.json",
        manifests_dir / "release_summary.json",
        manifests_dir / "duplicate_relations.json",
        manifests_dir / "duplicate_clusters.json",
        manifests_dir / "review_required_items.json",
        manifests_dir / "blocked_items.json",
        manifests_dir / "review_queue.json",
        manifests_dir / "release_record.json",
        manifests_dir / "release_diff.json",
        manifests_dir / "benchmark_manifest.json",
        *(
            [manifests_dir / "benchmark_leakage_risk.json"]
            if selected_benchmark_leakage_risk is not None
            else []
        ),
        manifests_dir / "benchmark_selection_audit.json",
        manifests_dir / "benchmark_stability_policy.json",
        *(
            [manifests_dir / "benchmark_reference_manifest.json"]
            if selected_benchmark_reference_manifest is not None
            else []
        ),
        *(
            [manifests_dir / "benchmark_reference_status.json"]
            if selected_benchmark_reference_status is not None
            else []
        ),
        *(
            [manifests_dir / "benchmark_reference_versioning.json"]
            if benchmark_inputs.reference_versioning is not None
            else []
        ),
        *exported_benchmark_reference_files,
        docs_dir / "DATASET_CARD.md",
        docs_dir / "CHANGELOG.md",
        docs_dir / "RELEASE_NOTES.md",
        docs_dir / "PROVENANCE.md",
        docs_dir / "HANDOFF.md",
        docs_dir / "BENCHMARK_CARD.md",
        summary_path,
    ]
    return SyntheticExportResult(
        export_dir=export_dir,
        summary_path=summary_path,
        release_record_path=manifests_dir / "release_record.json",
        item_manifest_path=manifests_dir / "item_manifest.json",
        artifact_paths=artifact_paths,
    )


def _select_synthetic_items(
    items: list[PrivacyScannedItemRecord],
    config: SyntheticExportConfig,
) -> list[PrivacyScannedItemRecord]:
    _validate_synthetic_export_config(config)
    synthetic_items = [item for item in items if item.is_synthetic]
    for item in synthetic_items:
        _validate_synthetic_item_for_export(item)
    return sorted(
        synthetic_items,
        key=lambda item: (_split_sort_key(item.split), item.source_id, item.item_id),
    )[: config.max_synthetic_items]


def _validate_synthetic_item_for_export(item: PrivacyScannedItemRecord) -> None:
    if item.normalized_license != "PROJECT-SYNTHETIC":
        raise StageExecutionError(
            f"synthetic export item {item.item_id} must use PROJECT-SYNTHETIC license"
        )
    metadata = item.metadata
    required_metadata = [
        "synthetic_disclosure",
        "synthetic_license",
        "hocrsyngen_provider_metadata",
        "hocrsyngen_rendering_metadata",
        "hocrsyngen_hebrew_coverage",
        "synthetic_hebrew_coverage",
        "synthetic_provider_name",
        "synthetic_provider_version",
    ]
    missing = [key for key in required_metadata if not metadata.get(key)]
    if missing:
        raise StageExecutionError(
            f"synthetic export item {item.item_id} is missing required metadata: {', '.join(missing)}"
        )
    if metadata.get("synthetic_license") != "PROJECT-SYNTHETIC":
        raise StageExecutionError(
            f"synthetic export item {item.item_id} must disclose PROJECT-SYNTHETIC in metadata"
        )
    provider_metadata = metadata.get("hocrsyngen_provider_metadata")
    if not isinstance(provider_metadata, dict) or provider_metadata.get("provider_name") != "hocrsyngen":
        raise StageExecutionError(
            f"synthetic export item {item.item_id} must preserve hocrsyngen provider metadata"
        )
    if any(
        provider_metadata.get(flag) is not False
        for flag in ("used_network", "used_rest_service", "used_gpu", "used_llm", "used_diffusion")
    ):
        raise StageExecutionError(
            f"synthetic export item {item.item_id} has disallowed hocrsyngen dependency flags"
        )
    rendering_metadata = metadata.get("hocrsyngen_rendering_metadata")
    if not isinstance(rendering_metadata, dict) or rendering_metadata.get("text_order") != "logical":
        raise StageExecutionError(
            f"synthetic export item {item.item_id} must preserve logical hocrsyngen rendering metadata"
        )
    coverage = metadata.get("hocrsyngen_hebrew_coverage")
    if not isinstance(coverage, dict) or coverage.get("has_hebrew_letters") is not True:
        raise StageExecutionError(
            f"synthetic export item {item.item_id} must preserve Hebrew coverage metadata"
        )


def _validate_synthetic_export_config(config: SyntheticExportConfig) -> None:
    if config.max_synthetic_items < 0:
        raise StageExecutionError("max_synthetic_items must be non-negative")
    if config.compare_to is not None:
        _validate_synthetic_release_diff_baseline(config.compare_to.resolve())


def _copy_synthetic_export_assets(
    items: list[PrivacyScannedItemRecord],
    synthetic_data_dir: Path,
) -> list[AlphaExportedItemRecord]:
    exported_items: list[AlphaExportedItemRecord] = []
    for item in items:
        if item.split is None:
            raise StageExecutionError(f"release-ready item {item.item_id} is missing a split assignment")
        item_dir = synthetic_data_dir / item.split / item.item_id
        exported_assets: list[ExportedAssetRecord] = []
        for asset in item.normalized_assets:
            source_path = Path(asset.normalized_asset_path)
            target_path = item_dir / source_path.name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target_path)
            release_preview_path = None
            if asset.preview_generated and asset.preview_path:
                preview_source = Path(asset.preview_path)
                if preview_source.exists():
                    preview_target = item_dir / "previews" / preview_source.name
                    preview_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preview_source, preview_target)
                    release_preview_path = str(preview_target.relative_to(synthetic_data_dir.parent.parent))
            exported_assets.append(
                ExportedAssetRecord(
                    release_asset_path=str(target_path.relative_to(synthetic_data_dir.parent.parent)),
                    media_type=asset.media_type,
                    asset_format=asset.asset_format,
                    release_preview_path=release_preview_path,
                )
            )
        exported_items.append(AlphaExportedItemRecord(**item.model_dump(mode="python"), exported_assets=exported_assets))
    return exported_items


def _filter_synthetic_benchmark_leakage_risk(
    leakage_risk: dict[str, Any] | None,
    selected_ids: set[str],
) -> dict[str, Any] | None:
    filtered = _filter_benchmark_leakage_risk(leakage_risk, selected_ids)
    if filtered is not None:
        filtered["export_scope"] = "selected_synthetic_items"
        policy = filtered.get("policy")
        if isinstance(policy, dict):
            filtered["policy"] = {
                **policy,
                "accepted_resolutions": _selected_resolution_records(
                    policy.get("accepted_resolutions", []),
                    selected_ids,
                ),
            }
        filtered["unused_resolutions"] = _selected_resolution_records(
            filtered.get("unused_resolutions", []),
            selected_ids,
        )
        filtered["rejected_resolutions"] = _selected_resolution_records(
            filtered.get("rejected_resolutions", []),
            selected_ids,
        )
    return filtered


def _selected_resolution_records(records: Any, selected_ids: set[str]) -> list[dict[str, Any]]:
    selected_records: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return selected_records
    for record in records:
        if not isinstance(record, dict):
            continue
        benchmark_item_ids = [
            item_id
            for item_id in record.get("benchmark_item_ids", [])
            if item_id in selected_ids
        ]
        non_benchmark_item_ids = [
            item_id
            for item_id in record.get("non_benchmark_item_ids", [])
            if item_id in selected_ids
        ]
        if not benchmark_item_ids and not non_benchmark_item_ids:
            continue
        selected_records.append(
            {
                **record,
                "benchmark_item_ids": benchmark_item_ids,
                "non_benchmark_item_ids": non_benchmark_item_ids,
            }
        )
    return selected_records


def _resolve_synthetic_comparison_release(export_dir: Path, config: SyntheticExportConfig) -> Path | None:
    if config.compare_to is not None:
        candidate = config.compare_to.resolve()
        if export_dir.resolve() == candidate:
            raise StageExecutionError("--compare-to cannot point to the current export directory")
        _validate_synthetic_release_diff_baseline(candidate)
        return candidate

    sibling_root = export_dir.resolve().parent
    if not sibling_root.exists():
        return None

    candidates: list[tuple[Any, str, Path]] = []
    for child in sibling_root.iterdir():
        if not child.is_dir():
            continue
        if child.resolve() == export_dir.resolve():
            continue
        if child.name == config.version:
            continue
        if not _is_synthetic_release_diff_baseline(child):
            continue
        release_record = _load_json(child / "manifests" / "release_record.json")
        if release_record.get("version") == config.version:
            continue
        exported_at = _parse_exported_at(release_record.get("exported_at"))
        candidates.append((exported_at, child.name, child))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min.replace(tzinfo=UTC), _natural_sort_key(item[1])))
    return candidates[-1][2]


def _is_synthetic_release_diff_baseline(path: Path) -> bool:
    manifests_dir = path / "manifests"
    release_record_path = manifests_dir / "release_record.json"
    item_manifest_path = manifests_dir / "item_manifest.json"
    if not release_record_path.is_file() or not item_manifest_path.is_file():
        return False
    try:
        release_record = _load_json(release_record_path)
    except StageExecutionError:
        return False
    return (
        release_record.get("dataset_id") == "HeOCRsynth"
        and release_record.get("release_kind") == "synthetic_only"
        and release_record.get("synthetic_only") is True
    )


def _validate_synthetic_release_diff_baseline(path: Path) -> None:
    _validate_release_diff_baseline(path)
    if not _is_synthetic_release_diff_baseline(path):
        raise StageExecutionError(f"compare-to release path is not a HeOCRsynth synthetic-only release: {path}")


def _synthetic_audit_item_payload(item: PrivacyScannedItemRecord) -> dict[str, Any]:
    return {
        "item_id": item.item_id,
        "source_id": item.source_id,
        "source_item_id": item.source_item_id,
        "source_url": item.source_url,
        "title": item.title,
        "canonical_item_id": item.canonical_item_id,
        "split_group_id": item.split_group_id,
        "normalized_license": item.normalized_license,
        "rights_classification": item.rights_classification.value,
        "content_class": item.content_class,
        "content_confidence": item.content_confidence,
        "period_class": item.period_class,
        "period_confidence": item.period_confidence,
        "language_class": item.language_class,
        "language_confidence": item.language_confidence,
        "quality_score": item.quality_score,
        "quality_tier": item.quality_tier,
        "classification_review_reasons": list(item.classification_review_reasons),
        "privacy_flag": item.privacy_flag.value,
        "privacy_reasons": list(item.privacy_reasons),
        "privacy_decision": item.privacy_decision,
    }


def _dataset_card(
    version: str,
    profile: ReleaseProfile,
    items: list[AlphaExportedItemRecord],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    included_sources: list[str],
) -> str:
    split_counts = Counter(item.split for item in items if item.split)
    synthetic_composition = synthetic_composition_report(items)
    return "\n".join(
        [
            f"# HeOCRsynth {version}",
            "",
            "## Scope",
            f"This release is a synthetic-only HeOCRsynth handoff exported from `hocrgen` using `{profile.id}`.",
            "It is not a mixed real+synthetic HeOCR release and does not claim public beta readiness.",
            f"It contains {len(items)} release-ready synthetic items across the configured public splits.",
            "",
            "## Included Synthetic Sources",
            *[f"- `{source_id}`" for source_id in included_sources],
            "",
            "## Excluded From Dataset Payload",
            "- Real NLI, Pinkas, BiblIA, modern handwriting, and other non-synthetic items are excluded.",
            f"- Synthetic review-required items: {len(review_required_items)}",
            f"- Synthetic blocked items: {len(blocked_items)}",
            "",
            "## Rights And Disclosure",
            "- Every dataset payload item must use `PROJECT-SYNTHETIC`.",
            "- Synthetic disclosure and hocrsyngen provider/rendering metadata are preserved in `manifests/item_manifest.json`.",
            "- hocrsyngen outputs remain candidate inputs until hocrgen release, review, split, benchmark, and export gates pass.",
            "",
            "## Split Counts",
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: _split_sort_key(item[0]))],
            "",
            "## Synthetic Composition",
            *(_synthetic_composition_lines(synthetic_composition)),
            "",
            "## Known Limitations",
            "- This is a synthetic-only alpha handoff, not a full corpus snapshot.",
            "- It must not be interpreted as real-source handwriting provenance.",
            "- Kaggle and Hugging Face publication are intentionally deferred.",
            "",
        ]
    )


def _release_notes(
    version: str,
    release_summary: dict[str, Any],
    source_stats: dict[str, Any],
    included_sources: list[str],
    release_diff: ReleaseDiffRecord,
) -> str:
    split_counts = release_summary["split_counts"]
    synthetic_composition = release_summary["synthetic_composition"]
    comparison_summary = (
        f"Compared to `{release_diff.previous_version}`: +{release_diff.counts['added']} / "
        f"-{release_diff.counts['removed']} / ~{release_diff.counts['changed']}. "
        "See `CHANGELOG.md` for item-level details."
        if release_diff.previous_version
        else "No prior synthetic-only release baseline was found. See `CHANGELOG.md` for the initial-release addition summary."
    )
    return "\n".join(
        [
            f"# HeOCRsynth Release Notes: {version}",
            "",
            "## Export Summary",
            f"- Exported items: {release_summary['exported_item_count']}",
            "- Exported real items: 0",
            f"- Exported synthetic items: {release_summary['exported_synthetic_items']}",
            f"- Upstream release-ready items: {release_summary['release_ready_count']}",
            f"- Synthetic review-required items excluded from payload: {release_summary['review_required_count']}",
            f"- Synthetic blocked items excluded from payload: {release_summary['blocked_count']}",
            "- Release kind: `synthetic_only`",
            "",
            "## Split Counts",
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: _split_sort_key(item[0]))],
            "",
            "## Included Synthetic Sources",
            *[f"- `{source_id}`: {source_stats['sources'][source_id]} items" for source_id in included_sources],
            "",
            "## Synthetic Composition",
            *(_synthetic_composition_lines(synthetic_composition)),
            "",
            "## Compared To Previous Synthetic Release",
            f"- {comparison_summary}",
            "",
            "## Notes",
            f"- `max-synthetic-items`: {release_summary['max_synthetic_items']}",
            "- Export is shaped for manual handoff into the separate `HeOCRsynth` repository under `releases/<version>/`.",
            "- Mixed real+synthetic HeOCR releases remain handled by `export-alpha`.",
            "",
        ]
    )


def _provenance_doc(
    bundle: ConfigBundle,
    profile: ReleaseProfile,
    included_sources: list[str],
    exported_at: str,
    commit_sha: str,
) -> str:
    registry = {source.id: source for source in bundle.source_registry.sources}
    source_sections: list[str] = []
    for source_id in included_sources:
        source_sections.extend(_source_snapshot_lines(registry[source_id]))
    return "\n".join(
        [
            "# HeOCRsynth Provenance",
            "",
            f"- Dataset: `HeOCRsynth`",
            "- Release kind: `synthetic_only`",
            f"- Profile: `{profile.id}`",
            f"- Exported at: `{exported_at}`",
            f"- hocrgen commit: `{commit_sha}`",
            f"- Included synthetic sources: {', '.join(f'`{source_id}`' for source_id in included_sources)}",
            "- Real-source provenance is intentionally absent from the dataset payload.",
            "- hocrsyngen provider metadata and synthetic disclosure are preserved per item.",
            "",
            "## Source Snapshot",
            *source_sections,
            "",
        ]
    )


def _handoff_doc(
    version: str,
    export_dir: Path,
    profile: ReleaseProfile,
    release_summary: dict[str, Any],
    included_sources: list[str],
    commit_sha: str,
    handoff_repo_root: Path | None,
) -> str:
    target_label = (
        f"`{handoff_repo_root.name}`"
        if handoff_repo_root and handoff_repo_root.name
        else "`<manual target checkout>`"
    )
    release_dir_path = Path("releases") / version
    if handoff_repo_root:
        try:
            release_dir_path = export_dir.relative_to(handoff_repo_root)
        except ValueError:
            pass
    release_dir_label = f"`{release_dir_path.as_posix().rstrip('/')}/`"
    return "\n".join(
        [
            "# HeOCRsynth Handoff",
            "",
            f"- Version: `{version}`",
            "- Dataset: `HeOCRsynth`",
            "- Release kind: `synthetic_only`",
            f"- Target repo checkout: {target_label}",
            f"- Target release dir: {release_dir_label}",
            f"- Release profile: `{profile.id}`",
            f"- hocrgen commit: `{commit_sha}`",
            "",
            "## Export Summary",
            f"- Exported items: {release_summary['exported_item_count']}",
            "- Exported real items: 0",
            f"- Exported synthetic items: {release_summary['exported_synthetic_items']}",
            f"- Synthetic review-required audit items: {release_summary['review_required_count']}",
            f"- Synthetic blocked audit items: {release_summary['blocked_count']}",
            "",
            "## Included Synthetic Sources",
            *[f"- `{source_id}`" for source_id in included_sources],
            "",
            "## PR Checklist",
            "- Confirm only synthetic `release_ready` items are present under `data/synthetic/`.",
            "- Confirm no real NLI, Pinkas, BiblIA, or modern handwriting items are present in payload or audit manifests.",
            "- Confirm every payload item preserves `PROJECT-SYNTHETIC`, synthetic disclosure, and hocrsyngen metadata.",
            "- Open the HeOCRsynth handoff PR against the target repository with this release tree under `releases/<version>/`.",
            "",
        ]
    )


def _synthetic_benchmark_card(card_markdown: str) -> str:
    return card_markdown.replace(
        "# Benchmark Card:",
        "# HeOCRsynth Synthetic Benchmark Card:",
        1,
    ) + "\nThis benchmark subset is filtered to synthetic-only HeOCRsynth payload items.\n"


def _synthetic_benchmark_stability_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return {
        **policy,
        "description": "Synthetic-only HeOCRsynth view of benchmark_v1 for exported synthetic payload items.",
        "selection_policy": (
            "Synthetic-only export view: select only release-ready, explicitly approved benchmark items "
            "that are present in the HeOCRsynth synthetic payload."
        ),
    }


def _source_snapshot_lines(source: SourceConfig) -> list[str]:
    return [
        f"### `{source.id}`",
        f"- Name: {source.name}",
        f"- Fetcher: `{source.fetcher}`",
        f"- Status: `{source.status.value}`",
        f"- Allowed content types: {', '.join(f'`{value}`' for value in source.allowed_content_types)}",
        f"- Normalized license: `{source.normalized_license}`",
        f"- Rights classification: `{source.rights_classification.value}`",
        "",
    ]


def _split_sort_key(split: str | None) -> int:
    split_order = {"train": 0, "validation": 1, "test": 2}
    if split is None:
        return len(split_order)
    return split_order.get(split, len(split_order))


def _validate_heocrsynth_repo_root(repo_root: Path) -> Path:
    resolved = repo_root.resolve()
    if not resolved.exists():
        raise StageExecutionError(f"HeOCRsynth repo path does not exist: {resolved}")
    if not resolved.is_dir():
        raise StageExecutionError(f"HeOCRsynth repo path is not a directory: {resolved}")
    git_dir = resolved / ".git"
    if not git_dir.exists():
        raise StageExecutionError(f"HeOCRsynth repo path is not a git checkout: {resolved}")
    return resolved


def _validate_synthetic_overwrite_target(export_dir: Path, version: str) -> None:
    if not export_dir.is_dir():
        raise StageExecutionError(f"synthetic export overwrite target is not a directory: {export_dir}")
    disallowed = {
        export_dir.anchor,
        str(Path.home()),
        str(REPO_ROOT),
    }
    if str(export_dir) in disallowed:
        raise StageExecutionError(f"refusing to overwrite unsafe export target: {export_dir}")
    if len(export_dir.parts) < 3:
        raise StageExecutionError(f"refusing to overwrite unsafe export target: {export_dir}")
    if export_dir.name != version:
        raise StageExecutionError(f"synthetic export overwrite target must end with {version}: {export_dir}")
