from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections import Counter
from json import JSONDecodeError
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import ReleaseProfile, SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import (
    AlphaExportedItemRecord,
    AlphaReleaseRecord,
    BenchmarkItemRecord,
    BenchmarkSelectionAuditRecord,
    CuratedItemRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    ExportedAssetRecord,
    PrivacyScannedItemRecord,
    ReleaseChangedItemRecord,
    ReleaseDiffRecord,
    ReleaseRemovalRecord,
    ReviewQueueRecord,
    SplitAssignmentRecord,
)
from hocrgen.normalize.files import sanitize_item_id


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


@dataclass(frozen=True)
class BenchmarkExportInputs:
    items: list[BenchmarkItemRecord]
    selection_audit: list[BenchmarkSelectionAuditRecord]
    stability_policy: dict[str, Any]
    card_markdown: str


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
    release_items = _load_models(build_dir / "item_manifest.json", PrivacyScannedItemRecord)
    review_required_items = _load_models(build_dir / "review_required_items.json", PrivacyScannedItemRecord)
    blocked_items = _load_models(build_dir / "blocked_items.json", PrivacyScannedItemRecord)
    split_manifest = _load_models(build_dir / "split_manifest.json", SplitAssignmentRecord)
    duplicate_relations = _load_models(build_dir / "duplicate_relations.json", DuplicateRelationRecord)
    duplicate_clusters = _load_models(build_dir / "duplicate_clusters.json", DuplicateClusterRecord)
    removed_duplicate_items = _load_models(build_dir / "removed_duplicate_items.json", CuratedItemRecord)
    review_queue = _load_models(build_dir / "review_queue.json", ReviewQueueRecord)
    benchmark_inputs = _load_benchmark_export_inputs(build_dir)
    build_release_summary = _load_json(build_dir / "release_summary.json")

    selected_items = _select_alpha_items(release_items, profile, config)
    if not selected_items:
        raise StageExecutionError("alpha export selection is empty")

    selected_ids = {item.item_id for item in selected_items}
    selected_benchmark_items = [item for item in benchmark_inputs.items if item.item_id in selected_ids]
    selected_benchmark_ids = {item.item_id for item in selected_benchmark_items}
    selected_benchmark_audit = [
        item for item in benchmark_inputs.selection_audit if item.item_id in selected_benchmark_ids
    ]
    benchmark_card = _benchmark_card_for_export(benchmark_inputs, selected_benchmark_items)
    included_sources = _ordered_sources(profile, {item.source_id for item in selected_items})
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
    exported_items = _copy_export_assets(selected_items, export_dir / "data")
    source_stats = _build_source_stats(exported_items, selected_duplicate_relations)
    classification_stats = _build_classification_stats(exported_items)
    privacy_stats = _build_privacy_stats(exported_items)
    split_counts = dict(Counter(item.split for item in exported_items if item.split))
    exported_real_items = sum(1 for item in exported_items if not item.is_synthetic)
    exported_synthetic_items = sum(1 for item in exported_items if item.is_synthetic)
    exported_at = datetime.now(UTC).isoformat()
    commit_sha = _current_commit_sha()
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
        "version": config.version,
    }
    baseline_dir = _resolve_comparison_release(export_dir, config)
    release_diff = _build_release_diff(
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
    docs_dir = export_dir / "docs"
    write_json(manifests_dir / "item_manifest.json", {"items": [_public_item_payload(item) for item in exported_items]})
    write_json(manifests_dir / "split_manifest.json", {"items": [item.model_dump(mode="json") for item in selected_split_manifest]})
    write_json(manifests_dir / "source_stats.json", source_stats)
    write_json(manifests_dir / "classification_stats.json", classification_stats)
    write_json(manifests_dir / "privacy_stats.json", privacy_stats)
    write_json(manifests_dir / "release_summary.json", release_summary)
    write_json(manifests_dir / "duplicate_relations.json", {"items": [item.model_dump(mode="json") for item in selected_duplicate_relations]})
    write_json(manifests_dir / "duplicate_clusters.json", {"items": [item.model_dump(mode="json") for item in selected_duplicate_clusters]})
    write_json(manifests_dir / "review_required_items.json", {"items": [_audit_item_payload(item) for item in review_required_items]})
    write_json(manifests_dir / "blocked_items.json", {"items": [_audit_item_payload(item) for item in blocked_items]})
    write_json(
        manifests_dir / "review_queue.json",
        {"items": _review_queue_payloads(selected_review_queue, export_dir)},
    )
    write_json(manifests_dir / "release_record.json", release_record.model_dump(mode="json"))
    write_json(manifests_dir / "release_diff.json", release_diff.model_dump(mode="json"))
    write_json(manifests_dir / "benchmark_manifest.json", {"items": [item.model_dump(mode="json") for item in selected_benchmark_items]})
    write_json(
        manifests_dir / "benchmark_selection_audit.json",
        {"items": [item.model_dump(mode="json") for item in selected_benchmark_audit]},
    )
    write_json(manifests_dir / "benchmark_stability_policy.json", benchmark_inputs.stability_policy)

    _write_markdown(
        docs_dir / "DATASET_CARD.md",
        _dataset_card(config.version, profile, exported_items, review_required_items, blocked_items, included_sources),
    )
    _write_markdown(
        docs_dir / "RELEASE_NOTES.md",
        _release_notes(config.version, release_summary, source_stats, included_sources, release_diff),
    )
    _write_markdown(
        docs_dir / "CHANGELOG.md",
        _changelog_doc(config.version, release_diff),
    )
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

    summary_path = run_dir / "export_alpha" / "summary.json"
    write_json(
        summary_path,
        {
            "export_dir": str(export_dir),
            "handoff_repo": str(handoff_repo_root) if handoff_repo_root else None,
            "item_manifest": "manifests/item_manifest.json",
            "release_diff": "manifests/release_diff.json",
            "release_record": "manifests/release_record.json",
            "release_summary": "manifests/release_summary.json",
            "stage": "export-alpha",
            "version": config.version,
        },
    )
    artifact_paths = [
        manifests_dir / "item_manifest.json",
        manifests_dir / "split_manifest.json",
        manifests_dir / "source_stats.json",
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
        manifests_dir / "benchmark_selection_audit.json",
        manifests_dir / "benchmark_stability_policy.json",
        docs_dir / "DATASET_CARD.md",
        docs_dir / "CHANGELOG.md",
        docs_dir / "RELEASE_NOTES.md",
        docs_dir / "PROVENANCE.md",
        docs_dir / "HANDOFF.md",
        docs_dir / "BENCHMARK_CARD.md",
        summary_path,
    ]
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
    ordered = sorted(items, key=lambda item: (_split_sort_key(item.split), _source_priority(profile, item.source_id), item.item_id))
    real_items = [item for item in ordered if not item.is_synthetic]
    synthetic_items = [item for item in ordered if item.is_synthetic]
    selected_real = real_items[: config.max_real_items]
    synthetic_limit = _synthetic_item_limit(len(selected_real), config)
    selected_synthetic = synthetic_items[:synthetic_limit]
    return sorted(
        selected_real + selected_synthetic,
        key=lambda item: (_split_sort_key(item.split), _source_priority(profile, item.source_id), item.item_id),
    )


def _synthetic_item_limit(real_item_count: int, config: AlphaExportConfig) -> int:
    return max(0, min(config.max_synthetic_items, real_item_count * 2))


def _validate_alpha_export_config(config: AlphaExportConfig) -> None:
    if config.max_real_items < 0:
        raise StageExecutionError("max_real_items must be non-negative")
    if config.max_synthetic_items < 0:
        raise StageExecutionError("max_synthetic_items must be non-negative")


def _copy_export_assets(items: list[PrivacyScannedItemRecord], data_dir: Path) -> list[AlphaExportedItemRecord]:
    exported_items: list[AlphaExportedItemRecord] = []
    for item in items:
        if item.split is None:
            raise StageExecutionError(f"release-ready item {item.item_id} is missing a split assignment")
        item_dir = data_dir / item.split / item.item_id
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
                    release_preview_path = str(preview_target.relative_to(data_dir.parent))
            exported_assets.append(
                ExportedAssetRecord(
                    release_asset_path=str(target_path.relative_to(data_dir.parent)),
                    media_type=asset.media_type,
                    asset_format=asset.asset_format,
                    release_preview_path=release_preview_path,
                )
            )
        exported_items.append(AlphaExportedItemRecord(**item.model_dump(mode="python"), exported_assets=exported_assets))
    return exported_items


def _build_source_stats(items: list[AlphaExportedItemRecord], duplicate_relations: list[DuplicateRelationRecord]) -> dict[str, Any]:
    split_counts = dict(Counter(item.split for item in items if item.split))
    source_counts = dict(Counter(item.source_id for item in items))
    source_split_counts: dict[str, dict[str, int]] = {}
    for item in items:
        split = item.split
        if split is None:
            continue
        source_split_counts.setdefault(item.source_id, {})
        source_split_counts[item.source_id][split] = source_split_counts[item.source_id].get(split, 0) + 1
    rights_counts = dict(Counter(item.rights_classification.value for item in items))
    format_counts = dict(Counter(asset.asset_format for item in items for asset in item.normalized_assets))
    duplicate_source_counts = dict(Counter(relation.canonical_item_id.split(":", 1)[0] for relation in duplicate_relations))
    return {
        "asset_formats": format_counts,
        "duplicate_sources": duplicate_source_counts,
        "rights_classifications": rights_counts,
        "sources": source_counts,
        "sources_by_split": source_split_counts,
        "splits": split_counts,
    }


def _resolve_comparison_release(export_dir: Path, config: AlphaExportConfig) -> Path | None:
    if config.compare_to is not None:
        candidate = config.compare_to.resolve()
        if export_dir.resolve() == candidate:
            raise StageExecutionError("--compare-to cannot point to the current export directory")
        _validate_release_diff_baseline(candidate)
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
        if not _is_release_diff_baseline(child):
            continue
        try:
            release_record = _load_json(child / "manifests" / "release_record.json")
        except StageExecutionError:
            continue
        if release_record.get("version") == config.version:
            continue
        exported_at = _parse_exported_at(release_record.get("exported_at"))
        candidates.append((exported_at, child.name, child))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0] is not None, item[0] or datetime.min.replace(tzinfo=UTC), _natural_sort_key(item[1])))
    return candidates[-1][2]


def _is_release_diff_baseline(path: Path) -> bool:
    manifests_dir = path / "manifests"
    release_record_path = manifests_dir / "release_record.json"
    item_manifest_path = manifests_dir / "item_manifest.json"
    return release_record_path.is_file() and item_manifest_path.is_file()


def _validate_release_diff_baseline(path: Path) -> None:
    if not path.exists():
        raise StageExecutionError(f"compare-to release path does not exist: {path}")
    if not path.is_dir():
        raise StageExecutionError(f"compare-to release path is not a directory: {path}")
    if not _is_release_diff_baseline(path):
        raise StageExecutionError(f"compare-to release path is missing required manifests: {path}")
    for manifest_name in ("release_record.json", "item_manifest.json"):
        manifest_path = path / "manifests" / manifest_name
        try:
            _load_json(manifest_path)
        except StageExecutionError as exc:
            raise StageExecutionError(f"compare-to release path has invalid JSON in {manifest_path}: {exc}") from exc


def _parse_exported_at(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _natural_sort_key(value: str) -> list[int | str]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", value)]


def _audit_item_payload(item: PrivacyScannedItemRecord) -> dict[str, Any]:
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


def _public_item_payload(item: AlphaExportedItemRecord) -> dict[str, Any]:
    payload = item.model_dump(
        mode="json",
        exclude={
            "acquired_assets",
            "asset_references",
            "fixture_path",
            "normalized_assets",
            "raw_metadata",
        },
    )
    payload["exported_assets"] = [asset.model_dump(mode="json") for asset in item.exported_assets]
    sanitized = _sanitize_portable_value(payload)
    if not isinstance(sanitized, dict):
        raise StageExecutionError("public item payload must serialize to an object")
    return sanitized


def _build_release_diff(
    *,
    version: str,
    generated_at: str,
    current_items: list[AlphaExportedItemRecord],
    baseline_dir: Path | None,
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    removed_duplicate_items: list[CuratedItemRecord],
    build_release_items: list[PrivacyScannedItemRecord],
) -> ReleaseDiffRecord:
    current_payloads = [_public_item_payload(item) for item in current_items]
    current_by_id = {item["item_id"]: item for item in current_payloads}
    baseline_by_id: dict[str, dict[str, Any]] = {}
    previous_version: str | None = None
    if baseline_dir is not None:
        baseline_record = _load_json(baseline_dir / "manifests" / "release_record.json")
        previous_version = baseline_record.get("version") or baseline_dir.name
        baseline_by_id = _load_baseline_item_manifest(baseline_dir / "manifests" / "item_manifest.json")

    added_ids = sorted(set(current_by_id) - set(baseline_by_id))
    removed_ids = sorted(set(baseline_by_id) - set(current_by_id))
    shared_ids = sorted(set(current_by_id) & set(baseline_by_id))
    changed_items: list[ReleaseChangedItemRecord] = []
    for item_id in shared_ids:
        change_types = _item_change_types(baseline_by_id[item_id], current_by_id[item_id])
        if not change_types:
            continue
        changed_items.append(
            ReleaseChangedItemRecord(
                item_id=item_id,
                source_id=str(current_by_id[item_id]["source_id"]),
                split=current_by_id[item_id].get("split"),
                change_types=change_types,
            )
        )

    review_required_ids = {item.item_id for item in review_required_items}
    blocked_ids = {item.item_id for item in blocked_items}
    duplicate_removed_ids = {item.item_id for item in removed_duplicate_items}
    build_release_ids = {item.item_id for item in build_release_items}
    removed_items = [
        ReleaseRemovalRecord(
            item_id=item_id,
            source_id=str(baseline_by_id[item_id]["source_id"]),
            previous_split=baseline_by_id[item_id].get("split"),
            reason=_removal_reason(item_id, review_required_ids, blocked_ids, duplicate_removed_ids, build_release_ids),
        )
        for item_id in removed_ids
    ]
    source_deltas = _count_deltas(current_by_id.values(), baseline_by_id.values(), "source_id")
    split_deltas = _count_deltas(current_by_id.values(), baseline_by_id.values(), "split")
    unchanged_count = len(shared_ids) - len(changed_items)
    return ReleaseDiffRecord(
        version=version,
        previous_version=previous_version,
        generated_at=generated_at,
        counts={
            "added": len(added_ids),
            "removed": len(removed_items),
            "changed": len(changed_items),
            "unchanged": unchanged_count,
        },
        added_items=[current_by_id[item_id] for item_id in added_ids],
        removed_items=removed_items,
        changed_items=changed_items,
        source_deltas=source_deltas,
        split_deltas=split_deltas,
    )


def _item_change_types(previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    change_types: list[str] = []
    if previous.get("split") != current.get("split"):
        change_types.append("split")
    if previous.get("exported_assets") != current.get("exported_assets"):
        change_types.append("assets")
    previous_metadata = {key: value for key, value in previous.items() if key not in {"exported_assets", "split"}}
    current_metadata = {key: value for key, value in current.items() if key not in {"exported_assets", "split"}}
    if previous_metadata != current_metadata:
        change_types.append("metadata")
    return change_types


def _removal_reason(
    item_id: str,
    review_required_ids: set[str],
    blocked_ids: set[str],
    duplicate_removed_ids: set[str],
    build_release_ids: set[str],
) -> str:
    if item_id in review_required_ids:
        return "review_required"
    if item_id in blocked_ids:
        return "blocked"
    if item_id in duplicate_removed_ids:
        return "duplicate_removed"
    if item_id in build_release_ids:
        return "selection_limit_excluded"
    return "missing_from_current_run"


def _count_deltas(
    current_items: Any,
    baseline_items: Any,
    field_name: str,
) -> dict[str, dict[str, int]]:
    current_counts = Counter(str(item.get(field_name)) for item in current_items if item.get(field_name) is not None)
    baseline_counts = Counter(str(item.get(field_name)) for item in baseline_items if item.get(field_name) is not None)
    keys = sorted(set(current_counts) | set(baseline_counts))
    return {
        key: {
            "current": current_counts.get(key, 0),
            "previous": baseline_counts.get(key, 0),
            "delta": current_counts.get(key, 0) - baseline_counts.get(key, 0),
        }
        for key in keys
    }


def _sanitize_portable_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized_dict: dict[str, Any] = {}
        for key, item in value.items():
            sanitized_item = _sanitize_portable_value(item)
            if sanitized_item is _OMIT:
                continue
            sanitized_dict[key] = sanitized_item
        return sanitized_dict
    if isinstance(value, list):
        sanitized_list: list[Any] = []
        for item in value:
            sanitized_item = _sanitize_portable_value(item)
            if sanitized_item is _OMIT:
                continue
            sanitized_list.append(sanitized_item)
        return sanitized_list
    if isinstance(value, str) and _looks_like_local_path(value):
        return _OMIT
    return value


def _looks_like_local_path(value: str) -> bool:
    if value.startswith(("http://", "https://", "package://")):
        return False
    return bool(
        value.startswith("/")
        or value.startswith(("file://", "\\\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or ".work/" in value
        or ".work\\" in value
    )


def _review_queue_payloads(items: list[ReviewQueueRecord], export_dir: Path) -> list[dict[str, Any]]:
    return [_review_queue_payload(item, export_dir) for item in items]


def _review_queue_payload(item: ReviewQueueRecord, export_dir: Path) -> dict[str, Any]:
    payload = item.model_dump(mode="json", exclude={"preview_paths"})
    payload["preview_paths"] = _copy_review_previews(item, export_dir)
    return payload


def _copy_review_previews(item: ReviewQueueRecord, export_dir: Path) -> list[str]:
    exported_preview_paths: list[str] = []
    export_root = export_dir.resolve()
    preview_dir = export_root / "manifests" / "review_previews" / sanitize_item_id(item.item_id)
    for index, preview_path in enumerate(item.preview_paths, start=1):
        source = Path(preview_path)
        if not source.exists():
            continue
        target = (preview_dir / f"{index:02d}_{source.name}").resolve()
        try:
            relative_target = target.relative_to(export_root)
        except ValueError as exc:
            raise StageExecutionError(f"review preview target escapes export dir for item {item.item_id}") from exc
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        exported_preview_paths.append(relative_target.as_posix())
    return exported_preview_paths


def _build_classification_stats(items: list[AlphaExportedItemRecord]) -> dict[str, Any]:
    return {
        "content_class": dict(Counter(item.content_class for item in items)),
        "language_class": dict(Counter(item.language_class for item in items)),
        "low_confidence_reason": dict(Counter(reason for item in items for reason in item.classification_review_reasons)),
        "period_class": dict(Counter(item.period_class for item in items)),
        "quality_tier": dict(Counter(item.quality_tier for item in items)),
    }


def _build_privacy_stats(items: list[AlphaExportedItemRecord]) -> dict[str, Any]:
    source_reason_counts: dict[str, Counter[str]] = {}
    for item in items:
        source_reason_counts.setdefault(item.source_id, Counter())
        source_reason_counts[item.source_id].update(item.privacy_reasons)
    return {
        "privacy_flag": dict(Counter(item.privacy_flag.value for item in items)),
        "privacy_reason": dict(Counter(reason for item in items for reason in item.privacy_reasons)),
        "source_id": {source_id: dict(counter) for source_id, counter in source_reason_counts.items()},
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
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: _split_sort_key(item[0]))],
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
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: _split_sort_key(item[0]))],
            "",
            "## Included Sources",
            *[f"- `{source_id}`: {source_stats['sources'][source_id]} items" for source_id in included_sources],
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


def _changelog_doc(version: str, release_diff: ReleaseDiffRecord) -> str:
    lines = [
        f"# Changelog: {version}",
        "",
        f"- Previous version: `{release_diff.previous_version}`" if release_diff.previous_version else "- Previous version: none",
        f"- Added: {release_diff.counts['added']}",
        f"- Removed: {release_diff.counts['removed']}",
        f"- Changed: {release_diff.counts['changed']}",
        f"- Unchanged: {release_diff.counts['unchanged']}",
        "",
        "## Source Deltas",
    ]
    if release_diff.source_deltas:
        lines.extend(
            f"- `{source_id}`: {delta['previous']} -> {delta['current']} ({delta['delta']:+d})"
            for source_id, delta in sorted(release_diff.source_deltas.items())
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Split Deltas"])
    if release_diff.split_deltas:
        lines.extend(
            f"- `{split}`: {delta['previous']} -> {delta['current']} ({delta['delta']:+d})"
            for split, delta in sorted(release_diff.split_deltas.items(), key=lambda item: _split_sort_key(item[0]))
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Added Items"])
    if release_diff.added_items:
        lines.extend(f"- `{item['item_id']}` ({item['source_id']}, `{item.get('split') or 'unknown'}`)" for item in release_diff.added_items)
    else:
        lines.append("- None")

    lines.extend(["", "## Removed Items"])
    if release_diff.removed_items:
        lines.extend(
            f"- `{item.item_id}` ({item.source_id}, `{item.previous_split or 'unknown'}`) - `{item.reason}`"
            for item in release_diff.removed_items
        )
    else:
        lines.append("- None")

    lines.extend(["", "## Changed Items"])
    if release_diff.changed_items:
        change_headings = {
            "metadata": "Metadata Changes",
            "assets": "Asset Changes",
            "split": "Split Assignment Changes",
        }
        for change_type in ("metadata", "assets", "split"):
            matching = [item for item in release_diff.changed_items if change_type in item.change_types]
            if not matching:
                continue
            lines.append(f"### {change_headings[change_type]}")
            lines.extend(f"- `{item.item_id}` ({item.source_id})" for item in matching)
            lines.append("")
        if lines[-1] == "":
            lines.pop()
    else:
        lines.append("- None")
    return "\n".join(lines + [""])


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


def _ordered_sources(profile: ReleaseProfile, source_ids: set[str]) -> list[str]:
    return [source_id for source_id in profile.include_sources if source_id in source_ids]


def _source_priority(profile: ReleaseProfile, source_id: str) -> int:
    try:
        return profile.include_sources.index(source_id)
    except ValueError:
        return len(profile.include_sources)


def _split_sort_key(split: str | None) -> int:
    if split is None:
        return len(SPLIT_ORDER)
    return SPLIT_ORDER.get(split, len(SPLIT_ORDER))


def _current_commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return "unknown"
    if result.returncode == 0:
        return result.stdout.strip()
    return "unknown"


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


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise StageExecutionError(f"invalid JSON at {path}: {exc.msg}") from exc


def _load_baseline_item_manifest(path: Path) -> dict[str, dict[str, Any]]:
    baseline_manifest = _load_json(path)
    if not isinstance(baseline_manifest, dict):
        raise StageExecutionError(f"baseline item manifest at {path} must be a JSON object with a list 'items'")
    baseline_items = baseline_manifest.get("items")
    if not isinstance(baseline_items, list):
        raise StageExecutionError(f"baseline item manifest at {path} must contain a list 'items'")
    invalid_item = next(
        (
            item
            for item in baseline_items
            if not isinstance(item, dict) or "item_id" not in item
        ),
        None,
    )
    if invalid_item is not None:
        raise StageExecutionError(
            f"baseline item manifest at {path} must contain only object entries with 'item_id'"
        )
    return {str(item["item_id"]): item for item in baseline_items}


def _load_models(path: Path, model_type: type[Any]) -> list[Any]:
    payload = _load_json(path)
    return [model_type.model_validate(item) for item in payload["items"]]


def _load_benchmark_export_inputs(build_dir: Path) -> BenchmarkExportInputs:
    try:
        return BenchmarkExportInputs(
            items=_load_models(build_dir / "benchmark_manifest.json", BenchmarkItemRecord),
            selection_audit=_load_models(
                build_dir / "benchmark_selection_audit.json",
                BenchmarkSelectionAuditRecord,
            ),
            stability_policy=_load_json(build_dir / "benchmark_stability_policy.json"),
            card_markdown=(build_dir / "BENCHMARK_CARD.md").read_text(encoding="utf-8"),
        )
    except (FileNotFoundError, KeyError, StageExecutionError, ValidationError) as exc:
        raise StageExecutionError(
            "alpha export requires build-release benchmark artifacts; "
            "rerun build-release with benchmark outputs before export-alpha"
        ) from exc


def _benchmark_card_for_export(inputs: BenchmarkExportInputs, items: list[BenchmarkItemRecord]) -> str:
    try:
        benchmark_id = str(inputs.stability_policy["benchmark_id"])
        description = str(inputs.stability_policy.get("description", "Exported benchmark subset."))
        selection_policy = str(inputs.stability_policy["selection_policy"])
        review_bar = str(inputs.stability_policy["review_bar"])
        stability_policy = dict(inputs.stability_policy["stability_policy"])
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise StageExecutionError("alpha export benchmark policy is invalid for card rendering") from exc
    real_count = sum(1 for item in items if not item.is_synthetic)
    synthetic_count = sum(1 for item in items if item.is_synthetic)
    split_counts: dict[str, int] = {}
    for item in items:
        split_counts[item.benchmark_split] = split_counts.get(item.benchmark_split, 0) + 1
    lines = [
        f"# Benchmark Card: {benchmark_id}",
        "",
        "## Summary",
        description,
        "",
        "## Selection Policy",
        selection_policy,
        "",
        "## Review Bar",
        review_bar,
        "",
        "## Stability Policy",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(stability_policy.items()))
    lines.extend(
        [
            "",
            "## Composition",
            f"- Items: {len(items)}",
            f"- Real items: {real_count}",
            f"- Synthetic control items: {synthetic_count}",
            "",
            "## Benchmark Splits",
        ]
    )
    lines.extend(f"- `{split}`: {count}" for split, count in sorted(split_counts.items()))
    lines.extend(["", "## Items"])
    lines.extend(
        f"- `{item.item_id}` ({item.source_id}, `{item.benchmark_split}`): {item.rationale}"
        for item in items
    )
    return "\n".join(lines + [""])


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
