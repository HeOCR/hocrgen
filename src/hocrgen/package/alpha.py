from __future__ import annotations

import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hocrgen.annotations import build_annotation_manifest
from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import ReleaseProfile
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import (
    AlphaExportedItemRecord,
    AlphaReleaseRecord,
    CuratedItemRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    PrivacyScannedItemRecord,
    ReleaseDiffRecord,
    ReviewQueueRecord,
    SplitAssignmentRecord,
)
from hocrgen.package.common import (
    AnnotationPilotExportInputs,
    BenchmarkExportInputs,
    ReleaseDocs,
    StandardReleaseArtifacts,
    audit_item_payload_for_export,
    benchmark_card_for_export,
    build_classification_stats,
    build_privacy_stats,
    build_release_diff,
    build_source_stats,
    changelog_doc,
    copy_benchmark_reference_files,
    copy_export_assets,
    current_commit_sha,
    filter_annotation_pilot_manifest,
    filter_benchmark_leakage_risk,
    filter_benchmark_reference_manifest,
    filter_benchmark_reference_status,
    is_release_diff_baseline,
    load_annotation_pilot_export_inputs,
    load_benchmark_export_inputs,
    load_json,
    load_models,
    natural_sort_key,
    ordered_sources,
    parse_exported_at,
    source_priority,
    source_snapshot_lines,
    split_sort_key,
    synthetic_composition_lines,
    validate_release_diff_baseline,
    write_markdown,
    write_standard_release_artifacts,
)
from hocrgen.synthetic.reporting import synthetic_composition_report


REPO_ROOT = Path(__file__).resolve().parents[3]
SPLIT_ORDER = {"train": 0, "validation": 1, "test": 2}
_OMIT = object()


@dataclass(frozen=True)
class AlphaExportConfig:
    version: str
    output_dir: Path | None = None
    heocr_repo: Path | None = None
    compare_to: Path | None = None
    max_real_items: int = 10
    max_synthetic_items: int = 20
    overwrite: bool = False


@dataclass(frozen=True)
class AlphaExportResult:
    export_dir: Path
    summary_path: Path
    release_record_path: Path
    item_manifest_path: Path
    artifact_paths: list[Path]


def export_alpha_release(
    bundle: ConfigBundle,
    run_dir: Path,
    profile_id: str,
    config: AlphaExportConfig,
) -> AlphaExportResult:
    _validate_alpha_export_config(config)
    profile = bundle.profiles[profile_id]
    build_dir = run_dir / "build_release"
    handoff_repo_root = None
    export_dir = (run_dir.parent.parent / "exports" / config.version).resolve()
    if config.output_dir and config.heocr_repo:
        raise StageExecutionError("--output-dir and --heocr-repo cannot be used together")
    if config.heocr_repo:
        handoff_repo_root = _validate_heocr_repo_root(config.heocr_repo)
        export_dir = (handoff_repo_root / "releases" / config.version).resolve()
    elif config.output_dir:
        export_dir = config.output_dir.resolve()
    if export_dir.exists():
        if not config.overwrite:
            raise StageExecutionError(f"alpha export directory already exists: {export_dir}")
        _validate_overwrite_target(export_dir, config.version)
    release_items = load_models(build_dir / "item_manifest.json", PrivacyScannedItemRecord)
    review_required_items = load_models(build_dir / "review_required_items.json", PrivacyScannedItemRecord)
    blocked_items = load_models(build_dir / "blocked_items.json", PrivacyScannedItemRecord)
    split_manifest = load_models(build_dir / "split_manifest.json", SplitAssignmentRecord)
    duplicate_relations = load_models(build_dir / "duplicate_relations.json", DuplicateRelationRecord)
    duplicate_clusters = load_models(build_dir / "duplicate_clusters.json", DuplicateClusterRecord)
    removed_duplicate_items = load_models(build_dir / "removed_duplicate_items.json", CuratedItemRecord)
    review_queue = load_models(build_dir / "review_queue.json", ReviewQueueRecord)
    benchmark_inputs = load_benchmark_export_inputs(build_dir)
    annotation_pilot_inputs = load_annotation_pilot_export_inputs(build_dir)
    build_release_summary = load_json(build_dir / "release_summary.json")
    if build_release_summary.get("near_duplicate_review_status") == "blocked":
        cluster_count = build_release_summary.get("near_duplicate_cluster_count", 0)
        raise StageExecutionError(
            f"alpha export is blocked: {cluster_count} near-duplicate cluster(s) require manual review"
        )
    if build_release_summary.get("benchmark_holdout_leakage_status") == "blocked":
        unresolved_count = (benchmark_inputs.leakage_risk or {}).get("unresolved_count", 0)
        raise StageExecutionError(
            "alpha export is blocked: "
            f"{unresolved_count} unresolved benchmark/holdout leakage group(s)"
        )

    selected_items = _select_alpha_items(release_items, profile, config)
    if not selected_items:
        raise StageExecutionError("alpha export selection is empty")

    selected_ids = {item.item_id for item in selected_items}
    selected_benchmark_items = [item for item in benchmark_inputs.items if item.item_id in selected_ids]
    selected_benchmark_ids = {item.item_id for item in selected_benchmark_items}
    selected_benchmark_audit = [
        item for item in benchmark_inputs.selection_audit if item.item_id in selected_benchmark_ids
    ]
    benchmark_card = benchmark_card_for_export(benchmark_inputs, selected_benchmark_items)
    selected_benchmark_reference_manifest = filter_benchmark_reference_manifest(
        benchmark_inputs.reference_manifest,
        selected_ids,
    )
    selected_benchmark_reference_status = filter_benchmark_reference_status(
        benchmark_inputs.reference_status,
        selected_ids,
    )
    selected_benchmark_leakage_risk = filter_benchmark_leakage_risk(
        benchmark_inputs.leakage_risk,
        selected_ids,
    )
    included_sources = ordered_sources(profile, {item.source_id for item in selected_items})
    selected_split_manifest = [assignment for assignment in split_manifest if assignment.item_id in selected_ids]
    review_required_ids = {item.item_id for item in review_required_items}
    selected_review_queue = [entry for entry in review_queue if entry.item_id in review_required_ids]
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

    if export_dir.exists():
        shutil.rmtree(export_dir)
    exported_items = copy_export_assets(selected_items, export_dir / "data")
    exported_benchmark_reference_files = copy_benchmark_reference_files(
        selected_benchmark_reference_manifest,
        build_dir,
        export_dir,
    )
    source_stats = build_source_stats(exported_items, selected_duplicate_relations)
    classification_stats = build_classification_stats(exported_items)
    privacy_stats = build_privacy_stats(exported_items)
    synthetic_composition = synthetic_composition_report(exported_items)
    annotation_manifest = build_annotation_manifest(exported_items, subset_id="alpha_export")
    exported_annotation_pilot_manifest = filter_annotation_pilot_manifest(annotation_pilot_inputs.manifest, selected_ids)
    selected_annotation_pilot_ids = {item.item_id for item in exported_annotation_pilot_manifest.items}
    selected_annotation_pilot_audit = [
        item for item in annotation_pilot_inputs.selection_audit if item.item_id in selected_annotation_pilot_ids
    ]
    split_counts = dict(Counter(item.split for item in exported_items if item.split))
    exported_real_items = sum(1 for item in exported_items if not item.is_synthetic)
    exported_synthetic_items = sum(1 for item in exported_items if item.is_synthetic)
    exported_at = datetime.now(UTC).isoformat()
    commit_sha = current_commit_sha()
    release_record = AlphaReleaseRecord(
        version=config.version,
        profile_id=profile_id,
        included_sources=included_sources,
        split_counts=split_counts,
        real_items=exported_real_items,
        synthetic_items=exported_synthetic_items,
        review_required_count=len(review_required_items),
        blocked_count=len(blocked_items),
        hocrgen_commit=commit_sha,
        exported_at=exported_at,
    )
    synthetic_limit = _synthetic_item_limit(exported_real_items, config)
    release_summary = {
        "accepted_count": build_release_summary["accepted_count"],
        "blocked_count": len(blocked_items),
        "exported_item_count": len(exported_items),
        "exported_real_items": exported_real_items,
        "exported_synthetic_items": exported_synthetic_items,
        "is_dry_run": build_release_summary["is_dry_run"],
        "max_real_items": config.max_real_items,
        "max_synthetic_items": config.max_synthetic_items,
        "normalized_count": build_release_summary["normalized_count"],
        "profile_id": profile_id,
        "real_items": exported_real_items,
        "release_ready_count": build_release_summary["release_ready_count"],
        "retained_count": build_release_summary["retained_count"],
        "review_required_count": len(review_required_items),
        "split_counts": split_counts,
        "synthetic_items": exported_synthetic_items,
        "synthetic_clamped_to_real": synthetic_limit < config.max_synthetic_items,
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
    baseline_dir = _resolve_comparison_release(export_dir, config)
    release_diff = build_release_diff(
        version=config.version,
        generated_at=exported_at,
        current_items=exported_items,
        baseline_dir=baseline_dir,
        review_required_items=review_required_items,
        blocked_items=blocked_items,
        removed_duplicate_items=removed_duplicate_items,
        build_release_items=release_items,
    )

    manifests_dir = export_dir / "manifests"
    summary_path, artifact_paths = write_standard_release_artifacts(
        StandardReleaseArtifacts(
            export_dir=export_dir,
            run_dir=run_dir,
            summary_subdir="export_alpha",
            summary_payload={
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
            "stage": "export-alpha",
            "synthetic_composition": "manifests/synthetic_composition.json",
            "version": config.version,
            },
            exported_items=exported_items,
            selected_split_manifest=selected_split_manifest,
            source_stats=source_stats,
            synthetic_composition=synthetic_composition,
            annotation_manifest=annotation_manifest,
            exported_annotation_pilot_manifest=exported_annotation_pilot_manifest,
            selected_annotation_pilot_audit=selected_annotation_pilot_audit,
            classification_stats=classification_stats,
            privacy_stats=privacy_stats,
            release_summary=release_summary,
            selected_duplicate_relations=selected_duplicate_relations,
            selected_duplicate_clusters=selected_duplicate_clusters,
            review_required_items=review_required_items,
            blocked_items=blocked_items,
            selected_review_queue=selected_review_queue,
            release_record=release_record,
            release_diff=release_diff,
            selected_benchmark_items=selected_benchmark_items,
            selected_benchmark_leakage_risk=selected_benchmark_leakage_risk,
            selected_benchmark_audit=selected_benchmark_audit,
            benchmark_stability_policy=benchmark_inputs.stability_policy,
            selected_benchmark_reference_manifest=selected_benchmark_reference_manifest,
            selected_benchmark_reference_status=selected_benchmark_reference_status,
            benchmark_reference_versioning=benchmark_inputs.reference_versioning,
            exported_benchmark_reference_files=exported_benchmark_reference_files,
            docs=ReleaseDocs(
                dataset_card=_dataset_card(config.version, profile, exported_items, review_required_items, blocked_items, included_sources),
                release_notes=_release_notes(config.version, release_summary, source_stats, included_sources, release_diff),
                changelog=changelog_doc(config.version, release_diff),
                provenance=_provenance_doc(bundle, profile, included_sources, exported_at, commit_sha),
                handoff=_handoff_doc(
                    config.version,
                    export_dir,
                    profile,
                    release_summary,
                    included_sources,
                    commit_sha,
                    handoff_repo_root,
                ),
                benchmark_card=benchmark_card,
            ),
            audit_item_payload=audit_item_payload_for_export,
        )
    )
    return AlphaExportResult(
        export_dir=export_dir,
        summary_path=summary_path,
        release_record_path=manifests_dir / "release_record.json",
        item_manifest_path=manifests_dir / "item_manifest.json",
        artifact_paths=artifact_paths,
    )


def _select_alpha_items(
    items: list[PrivacyScannedItemRecord],
    profile: ReleaseProfile,
    config: AlphaExportConfig,
) -> list[PrivacyScannedItemRecord]:
    _validate_alpha_export_config(config)
    ordered = sorted(items, key=lambda item: (split_sort_key(item.split), source_priority(profile, item.source_id), item.item_id))
    real_items = [item for item in ordered if not item.is_synthetic]
    synthetic_items = [item for item in ordered if item.is_synthetic]
    selected_real = real_items[: config.max_real_items]
    synthetic_limit = _synthetic_item_limit(len(selected_real), config)
    selected_synthetic = synthetic_items[:synthetic_limit]
    return sorted(
        selected_real + selected_synthetic,
        key=lambda item: (split_sort_key(item.split), source_priority(profile, item.source_id), item.item_id),
    )


def _synthetic_item_limit(real_item_count: int, config: AlphaExportConfig) -> int:
    return max(0, min(config.max_synthetic_items, real_item_count * 2))


def _validate_alpha_export_config(config: AlphaExportConfig) -> None:
    if config.max_real_items < 0:
        raise StageExecutionError("max_real_items must be non-negative")
    if config.max_synthetic_items < 0:
        raise StageExecutionError("max_synthetic_items must be non-negative")


def _resolve_comparison_release(export_dir: Path, config: AlphaExportConfig) -> Path | None:
    if config.compare_to is not None:
        candidate = config.compare_to.resolve()
        if export_dir.resolve() == candidate:
            raise StageExecutionError("--compare-to cannot point to the current export directory")
        validate_release_diff_baseline(candidate)
        return candidate

    sibling_root = export_dir.resolve().parent
    if not sibling_root.exists():
        return None

    candidates: list[tuple[datetime | None, str, Path]] = []
    for child in sibling_root.iterdir():
        if not child.is_dir():
            continue
        if child.resolve() == export_dir.resolve():
            continue
        if child.name == config.version:
            continue
        if not is_release_diff_baseline(child):
            continue
        try:
            release_record = load_json(child / "manifests" / "release_record.json")
        except StageExecutionError:
            continue
        if release_record.get("version") == config.version:
            continue
        exported_at = parse_exported_at(release_record.get("exported_at"))
        candidates.append((exported_at, child.name, child))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min.replace(tzinfo=UTC), natural_sort_key(item[1])))
    return candidates[-1][2]


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
            f"# HeOCR {version}",
            "",
            "## Scope",
            f"This alpha release is a narrow public subset exported from `hocrgen` using `{profile.id}`.",
            f"It contains {len(items)} release-ready items across the configured public splits.",
            "",
            "## Included Sources",
            *[f"- `{source_id}`" for source_id in included_sources],
            "",
            "## Excluded From Public Payload",
            f"- Review-required items: {len(review_required_items)}",
            f"- Blocked items: {len(blocked_items)}",
            "",
            "## Rights Posture",
            "- Only release-ready items from the conservative public profile are included under `data/`.",
            "- Review-required and blocked items are exported only as audit manifests.",
            "",
            "## Split Counts",
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: split_sort_key(item[0]))],
            "",
            "## Synthetic Composition",
            *(synthetic_composition_lines(synthetic_composition)),
            "",
            "## Annotation Readiness",
            "- Transcriptions are optional and are not required for this alpha payload.",
            "- `manifests/annotation_manifest.json` defines the additive transcription and layout-label slots for future annotated subsets.",
            "- `manifests/annotation_pilot_manifest.json` lists explicitly scoped pilot work without making annotations mandatory.",
            "",
            "## Known Limitations",
            "- This is an alpha release, not a full corpus snapshot.",
            "- Kaggle and Hugging Face publication are intentionally deferred.",
            "- Audit manifests are included for transparency, but only the release-ready subset is packaged as dataset payload.",
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
        else "No prior release baseline was found. See `CHANGELOG.md` for the initial-release addition summary."
    )
    return "\n".join(
        [
            f"# Release Notes: {version}",
            "",
            "## Export Summary",
            f"- Exported items: {release_summary['exported_item_count']}",
            f"- Exported real items: {release_summary['exported_real_items']}",
            f"- Exported synthetic items: {release_summary['exported_synthetic_items']}",
            f"- Upstream release-ready items: {release_summary['release_ready_count']}",
            f"- Review-required items excluded from public export: {release_summary['review_required_count']}",
            f"- Blocked items excluded from public export: {release_summary['blocked_count']}",
            "",
            "## Split Counts",
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: split_sort_key(item[0]))],
            "",
            "## Included Sources",
            *[f"- `{source_id}`: {source_stats['sources'][source_id]} items" for source_id in included_sources],
            "",
            "## Synthetic Composition",
            *(synthetic_composition_lines(synthetic_composition)),
            "",
            "## Annotation Readiness",
            f"- Annotated items: {release_summary['annotation_manifest']['annotated_item_count']}",
            f"- Items with transcription references: {release_summary['annotation_manifest']['transcription_item_count']}",
            f"- Items with layout-label references: {release_summary['annotation_manifest']['layout_label_item_count']}",
            f"- Annotation pilot items: {release_summary['annotation_pilot']['pilot_item_count']}",
            f"- Planned pilot transcription tasks: {release_summary['annotation_pilot']['transcription_task_count']}",
            f"- Planned pilot layout-label tasks: {release_summary['annotation_pilot']['layout_label_task_count']}",
            "- Current alpha exports do not require transcriptions or layout labels.",
            "",
            "## Compared To Previous Release",
            f"- {comparison_summary}",
            "",
            "## Notes",
            f"- `max-real-items`: {release_summary['max_real_items']}",
            f"- `max-synthetic-items`: {release_summary['max_synthetic_items']} (effective export cap also bounded by `2x` exported real items)",
            "- Export is shaped for manual handoff into the separate `HeOCR` repository under `releases/<version>/`.",
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
        source_sections.extend(source_snapshot_lines(registry[source_id]))
    return "\n".join(
        [
            "# Provenance",
            "",
            f"- Profile: `{profile.id}`",
            f"- Exported at: `{exported_at}`",
            f"- hocrgen commit: `{commit_sha}`",
            f"- Included sources: {', '.join(f'`{source_id}`' for source_id in included_sources)}",
            "- Kaggle and Hugging Face publication are intentionally out of scope for alpha releases.",
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
            "# Alpha Handoff",
            "",
            f"- Version: `{version}`",
            f"- Target repo checkout: {target_label}",
            f"- Target release dir: {release_dir_label}",
            f"- Release profile: `{profile.id}`",
            f"- hocrgen commit: `{commit_sha}`",
            "",
            "## Export Summary",
            f"- Exported items: {release_summary['exported_item_count']}",
            f"- Exported real items: {release_summary['exported_real_items']}",
            f"- Exported synthetic items: {release_summary['exported_synthetic_items']}",
            f"- Review-required audit items: {release_summary['review_required_count']}",
            f"- Blocked audit items: {release_summary['blocked_count']}",
            "",
            "## Included Sources",
            *[f"- `{source_id}`" for source_id in included_sources],
            "",
            "## PR Checklist",
            "- Confirm only `release_ready` items are present under `data/`.",
            "- Confirm review-required and blocked items exist only as audit manifests under `manifests/`.",
            "- Inspect `docs/DATASET_CARD.md`, `docs/RELEASE_NOTES.md`, and `docs/PROVENANCE.md` in the target tree.",
            "- Open the HeOCR handoff PR against the target repository with this release tree under `releases/<version>/`.",
            "",
        ]
    )


def _validate_heocr_repo_root(repo_root: Path) -> Path:
    resolved = repo_root.resolve()
    if not resolved.exists():
        raise StageExecutionError(f"HeOCR repo path does not exist: {resolved}")
    if not resolved.is_dir():
        raise StageExecutionError(f"HeOCR repo path is not a directory: {resolved}")
    git_dir = resolved / ".git"
    if not git_dir.exists():
        raise StageExecutionError(f"HeOCR repo path is not a git checkout: {resolved}")
    return resolved


def _validate_overwrite_target(export_dir: Path, version: str) -> None:
    if not export_dir.is_dir():
        raise StageExecutionError(f"alpha export overwrite target is not a directory: {export_dir}")
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
        raise StageExecutionError(f"alpha export overwrite target must end with {version}: {export_dir}")
