from __future__ import annotations

import json
import re
import shutil
import subprocess
import tarfile
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from hocrgen.config.models import ReleaseProfile, SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import (
    AnnotationPilotManifestRecord,
    AnnotationPilotSelectionAuditRecord,
    BenchmarkItemRecord,
    BenchmarkReferenceManifestRecord,
    BenchmarkReferenceStatusArtifactRecord,
    BenchmarkSelectionAuditRecord,
    CuratedItemRecord,
    DuplicateRelationRecord,
    ExportedAssetRecord,
    ExportedItemRecord,
    PrivacyScannedItemRecord,
    ReleaseChangedItemRecord,
    ReleaseDiffRecord,
    ReleaseRemovalRecord,
    ReviewQueueRecord,
)
from hocrgen.normalize.files import sanitize_item_id


REPO_ROOT = Path(__file__).resolve().parents[3]
SPLIT_ORDER = {"train": 0, "validation": 1, "test": 2}
_OMIT = object()


@dataclass(frozen=True)
class BenchmarkExportInputs:
    items: list[BenchmarkItemRecord]
    selection_audit: list[BenchmarkSelectionAuditRecord]
    stability_policy: dict[str, Any]
    card_markdown: str
    leakage_risk: dict[str, Any] | None = None
    reference_manifest: BenchmarkReferenceManifestRecord | None = None
    reference_status: BenchmarkReferenceStatusArtifactRecord | None = None
    reference_versioning: dict[str, Any] | None = None


@dataclass(frozen=True)
class AnnotationPilotExportInputs:
    manifest: AnnotationPilotManifestRecord
    selection_audit: list[AnnotationPilotSelectionAuditRecord]


@dataclass(frozen=True)
class ReleaseDocs:
    dataset_card: str
    release_notes: str
    changelog: str
    provenance: str
    handoff: str
    benchmark_card: str


@dataclass(frozen=True)
class StandardReleaseArtifacts:
    export_dir: Path
    run_dir: Path
    summary_subdir: str
    summary_payload: dict[str, Any]
    exported_items: list[ExportedItemRecord]
    selected_split_manifest: list[Any]
    source_stats: dict[str, Any]
    synthetic_composition: dict[str, Any]
    annotation_manifest: Any
    exported_annotation_pilot_manifest: Any
    selected_annotation_pilot_audit: list[Any]
    classification_stats: dict[str, Any]
    privacy_stats: dict[str, Any]
    release_summary: dict[str, Any]
    selected_duplicate_relations: list[Any]
    selected_duplicate_clusters: list[Any]
    review_required_items: list[PrivacyScannedItemRecord]
    blocked_items: list[PrivacyScannedItemRecord]
    selected_review_queue: list[ReviewQueueRecord]
    release_record: Any
    release_diff: ReleaseDiffRecord
    selected_benchmark_items: list[Any]
    selected_benchmark_leakage_risk: dict[str, Any] | None
    selected_benchmark_audit: list[Any]
    benchmark_stability_policy: dict[str, Any]
    selected_benchmark_reference_manifest: BenchmarkReferenceManifestRecord | None
    selected_benchmark_reference_status: BenchmarkReferenceStatusArtifactRecord | None
    benchmark_reference_versioning: dict[str, Any] | None
    exported_benchmark_reference_files: list[Path]
    docs: ReleaseDocs
    audit_item_payload: Any | None = None


def copy_export_assets(
    items: list[PrivacyScannedItemRecord],
    data_dir: Path,
    *,
    release_root: Path | None = None,
) -> list[ExportedItemRecord]:
    release_root = release_root or data_dir.parent
    exported_items: list[ExportedItemRecord] = []
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
                    release_preview_path = str(preview_target.relative_to(release_root))
            exported_assets.append(
                ExportedAssetRecord(
                    release_asset_path=str(target_path.relative_to(release_root)),
                    media_type=asset.media_type,
                    asset_format=asset.asset_format,
                    release_preview_path=release_preview_path,
                )
            )
        exported_items.append(ExportedItemRecord(**item.model_dump(mode="python"), exported_assets=exported_assets))
    return exported_items


def write_standard_release_artifacts(inputs: StandardReleaseArtifacts) -> tuple[Path, list[Path]]:
    manifests_dir = inputs.export_dir / "manifests"
    docs_dir = inputs.export_dir / "docs"
    write_release_manifests(inputs, manifests_dir)
    write_release_docs(inputs.docs, docs_dir)
    summary_path = inputs.run_dir / inputs.summary_subdir / "summary.json"
    write_json(summary_path, inputs.summary_payload)
    return summary_path, release_artifact_paths(inputs, manifests_dir, docs_dir, summary_path)


def write_release_manifests(inputs: StandardReleaseArtifacts, manifests_dir: Path) -> None:
    audit_item_payload = inputs.audit_item_payload or audit_item_payload_for_export
    write_core_release_manifests(inputs, manifests_dir, audit_item_payload)
    write_benchmark_release_manifests(inputs, manifests_dir)


def write_core_release_manifests(
    inputs: StandardReleaseArtifacts,
    manifests_dir: Path,
    audit_item_payload: Any,
) -> None:
    write_json(
        manifests_dir / "item_manifest.json",
        {"items": [public_item_payload(item) for item in inputs.exported_items]},
    )
    write_json(
        manifests_dir / "split_manifest.json",
        {"items": [item.model_dump(mode="json") for item in inputs.selected_split_manifest]},
    )
    write_json(manifests_dir / "source_stats.json", inputs.source_stats)
    write_json(manifests_dir / "synthetic_composition.json", inputs.synthetic_composition)
    write_json(manifests_dir / "annotation_manifest.json", inputs.annotation_manifest.model_dump(mode="json"))
    write_json(
        manifests_dir / "annotation_pilot_manifest.json",
        inputs.exported_annotation_pilot_manifest.model_dump(mode="json"),
    )
    write_json(
        manifests_dir / "annotation_pilot_selection_audit.json",
        {"items": [item.model_dump(mode="json") for item in inputs.selected_annotation_pilot_audit]},
    )
    write_json(manifests_dir / "classification_stats.json", inputs.classification_stats)
    write_json(manifests_dir / "privacy_stats.json", inputs.privacy_stats)
    write_json(manifests_dir / "release_summary.json", inputs.release_summary)
    write_json(
        manifests_dir / "duplicate_relations.json",
        {"items": [item.model_dump(mode="json") for item in inputs.selected_duplicate_relations]},
    )
    write_json(
        manifests_dir / "duplicate_clusters.json",
        {"items": [item.model_dump(mode="json") for item in inputs.selected_duplicate_clusters]},
    )
    write_json(
        manifests_dir / "review_required_items.json",
        {"items": [audit_item_payload(item) for item in inputs.review_required_items]},
    )
    write_json(
        manifests_dir / "blocked_items.json",
        {"items": [audit_item_payload(item) for item in inputs.blocked_items]},
    )
    write_json(
        manifests_dir / "review_queue.json",
        {"items": review_queue_payloads(inputs.selected_review_queue, inputs.export_dir)},
    )
    write_json(manifests_dir / "release_record.json", inputs.release_record.model_dump(mode="json"))
    write_json(manifests_dir / "release_diff.json", inputs.release_diff.model_dump(mode="json"))


def write_benchmark_release_manifests(
    inputs: StandardReleaseArtifacts,
    manifests_dir: Path,
) -> None:
    write_json(
        manifests_dir / "benchmark_manifest.json",
        {"items": [item.model_dump(mode="json") for item in inputs.selected_benchmark_items]},
    )
    if inputs.selected_benchmark_leakage_risk is not None:
        write_json(manifests_dir / "benchmark_leakage_risk.json", inputs.selected_benchmark_leakage_risk)
    write_json(
        manifests_dir / "benchmark_selection_audit.json",
        {"items": [item.model_dump(mode="json") for item in inputs.selected_benchmark_audit]},
    )
    write_json(manifests_dir / "benchmark_stability_policy.json", inputs.benchmark_stability_policy)
    if inputs.selected_benchmark_reference_manifest is not None:
        write_json(
            manifests_dir / "benchmark_reference_manifest.json",
            inputs.selected_benchmark_reference_manifest.model_dump(mode="json"),
        )
    if inputs.selected_benchmark_reference_status is not None:
        write_json(
            manifests_dir / "benchmark_reference_status.json",
            inputs.selected_benchmark_reference_status.model_dump(mode="json"),
        )
    if inputs.benchmark_reference_versioning is not None:
        write_json(manifests_dir / "benchmark_reference_versioning.json", inputs.benchmark_reference_versioning)


def write_release_docs(docs: ReleaseDocs, docs_dir: Path) -> None:
    write_markdown(docs_dir / "DATASET_CARD.md", docs.dataset_card)
    write_markdown(docs_dir / "RELEASE_NOTES.md", docs.release_notes)
    write_markdown(docs_dir / "CHANGELOG.md", docs.changelog)
    write_markdown(docs_dir / "PROVENANCE.md", docs.provenance)
    write_markdown(docs_dir / "HANDOFF.md", docs.handoff)
    write_markdown(docs_dir / "BENCHMARK_CARD.md", docs.benchmark_card)


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def release_relative_path(path: Path, release_root: Path) -> str:
    try:
        return path.resolve().relative_to(release_root.resolve()).as_posix()
    except ValueError as exc:
        raise StageExecutionError(f"release artifact escapes release root: {path}") from exc


def write_release_archive(
    *,
    release_root: Path,
    version: str,
    archive_dir: Path | None = None,
    exclude_paths: set[str] | None = None,
) -> dict[str, Any]:
    archive_dir = archive_dir or release_root / "archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{version}.tar.gz"
    release_root_resolved = release_root.resolve()
    included_top_level_paths: set[str] = set()
    excluded = {"archives/", *(exclude_paths or set())}

    def is_excluded(relative: str) -> bool:
        return any(relative == entry.rstrip("/") or relative.startswith(f"{entry.rstrip('/')}/") for entry in excluded)

    with tarfile.open(archive_path, "w:gz") as archive:
        for child in sorted(release_root_resolved.rglob("*"), key=lambda item: item.relative_to(release_root_resolved).as_posix()):
            if not child.is_file():
                continue
            relative = child.relative_to(release_root_resolved).as_posix()
            if is_excluded(relative):
                continue
            included_top_level_paths.add(relative.split("/", maxsplit=1)[0])
            archive.add(child, arcname=f"{version}/{relative}", recursive=False)
    return {
        "archive_name": archive_path.name,
        "archive_path": release_relative_path(archive_path, release_root_resolved),
        "byte_size": archive_path.stat().st_size,
        "excluded_paths": sorted(excluded),
        "format": "tar.gz",
        "included_top_level_paths": sorted(included_top_level_paths),
        "release_root": version,
        "sha256": sha256_file(archive_path),
    }


def build_checksum_manifest(
    *,
    release_root: Path,
    archive_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    release_root_resolved = release_root.resolve()
    entries: list[dict[str, Any]] = []
    skip_manifest_paths = {
        "manifests/checksum_manifest.json",
    }
    archive_paths = {
        str(record.get("archive_path"))
        for record in archive_records or []
        if record.get("archive_path")
    }
    for path in sorted((item for item in release_root_resolved.rglob("*") if item.is_file()), key=lambda item: item.relative_to(release_root_resolved).as_posix()):
        relative = path.relative_to(release_root_resolved).as_posix()
        if relative in skip_manifest_paths:
            continue
        entries.append(
            {
                "path": relative,
                "category": _checksum_category(relative, archive_paths),
                "byte_size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema_version": 1,
        "algorithm": "sha256",
        "release_root": release_root_resolved.name,
        "entry_count": len(entries),
        "entries": entries,
    }


def verify_checksum_manifest(release_root: Path, checksum_manifest: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, str]] = []
    release_root_resolved = release_root.resolve()
    for entry in checksum_manifest.get("entries", []):
        relative_path = str(entry.get("path", ""))
        path = _resolve_checksum_entry_path(release_root_resolved, relative_path)
        if path is None:
            failures.append({"path": relative_path, "reason": "unsafe_path"})
            continue
        if not path.is_file():
            failures.append({"path": relative_path, "reason": "missing"})
            continue
        digest = sha256_file(path)
        if digest != entry.get("sha256"):
            failures.append({"path": relative_path, "reason": "sha256_mismatch"})
    return {
        "checked_count": len(checksum_manifest.get("entries", [])),
        "failure_count": len(failures),
        "failures": failures,
        "status": "pass" if not failures else "blocked",
    }


def _resolve_checksum_entry_path(release_root: Path, relative_path: str) -> Path | None:
    if not relative_path:
        return None
    parsed = PurePosixPath(relative_path)
    if parsed.is_absolute() or Path(relative_path).is_absolute() or ".." in parsed.parts:
        return None
    candidate = (release_root / Path(*parsed.parts)).resolve()
    try:
        candidate.relative_to(release_root)
    except ValueError:
        return None
    return candidate


def _checksum_category(path: str, archive_paths: set[str]) -> str:
    if path in archive_paths or path.startswith("archives/"):
        return "archive"
    if path.startswith("data/"):
        return "payload_asset"
    if path.startswith("docs/"):
        return "public_doc"
    if path.startswith("references/"):
        return "benchmark_reference_child_file"
    if path.startswith("manifests/"):
        return "public_manifest"
    return "release_file"


def release_artifact_paths(
    inputs: StandardReleaseArtifacts,
    manifests_dir: Path,
    docs_dir: Path,
    summary_path: Path,
) -> list[Path]:
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
            if inputs.selected_benchmark_leakage_risk is not None
            else []
        ),
        manifests_dir / "benchmark_selection_audit.json",
        manifests_dir / "benchmark_stability_policy.json",
        *(
            [manifests_dir / "benchmark_reference_manifest.json"]
            if inputs.selected_benchmark_reference_manifest is not None
            else []
        ),
        *(
            [manifests_dir / "benchmark_reference_status.json"]
            if inputs.selected_benchmark_reference_status is not None
            else []
        ),
        *(
            [manifests_dir / "benchmark_reference_versioning.json"]
            if inputs.benchmark_reference_versioning is not None
            else []
        ),
        *inputs.exported_benchmark_reference_files,
        docs_dir / "DATASET_CARD.md",
        docs_dir / "CHANGELOG.md",
        docs_dir / "RELEASE_NOTES.md",
        docs_dir / "PROVENANCE.md",
        docs_dir / "HANDOFF.md",
        docs_dir / "BENCHMARK_CARD.md",
        summary_path,
    ]
    return artifact_paths


def _build_source_stats(
    items: list[ExportedItemRecord],
    duplicate_relations: list[DuplicateRelationRecord],
) -> dict[str, Any]:
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


def _public_item_payload(item: ExportedItemRecord) -> dict[str, Any]:
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
    sanitized = sanitize_portable_value(payload)
    if not isinstance(sanitized, dict):
        raise StageExecutionError("public item payload must serialize to an object")
    return sanitized


def _build_release_diff(
    *,
    version: str,
    generated_at: str,
    current_items: list[ExportedItemRecord],
    baseline_dir: Path | None,
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    removed_duplicate_items: list[CuratedItemRecord],
    build_release_items: list[PrivacyScannedItemRecord],
) -> ReleaseDiffRecord:
    current_payloads = [public_item_payload(item) for item in current_items]
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


def _build_classification_stats(items: list[ExportedItemRecord]) -> dict[str, Any]:
    return {
        "content_class": dict(Counter(item.content_class for item in items)),
        "language_class": dict(Counter(item.language_class for item in items)),
        "low_confidence_reason": dict(Counter(reason for item in items for reason in item.classification_review_reasons)),
        "period_class": dict(Counter(item.period_class for item in items)),
        "quality_tier": dict(Counter(item.quality_tier for item in items)),
    }


def _build_privacy_stats(items: list[ExportedItemRecord]) -> dict[str, Any]:
    source_reason_counts: dict[str, Counter[str]] = {}
    for item in items:
        source_reason_counts.setdefault(item.source_id, Counter())
        source_reason_counts[item.source_id].update(item.privacy_reasons)
    return {
        "privacy_flag": dict(Counter(item.privacy_flag.value for item in items)),
        "privacy_reason": dict(Counter(reason for item in items for reason in item.privacy_reasons)),
        "source_id": {source_id: dict(counter) for source_id, counter in source_reason_counts.items()},
    }


def _synthetic_composition_lines(report: dict[str, Any]) -> list[str]:
    if report["synthetic_items"] == 0:
        return ["- Synthetic items: 0"]
    return [
        f"- Synthetic items: {report['synthetic_items']} ({report['synthetic_fraction']:.2%} of exported items)",
        "- Recipes: " + ", ".join(f"`{recipe}`={count}" for recipe, count in sorted(report["by_recipe_id"].items())),
        "- Degradation presets: "
        + ", ".join(f"`{preset}`={count}" for preset, count in sorted(report["by_degradation_preset"].items())),
    ]


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


def _ordered_sources(profile: ReleaseProfile, source_ids: set[str]) -> list[str]:
    return [source_id for source_id in profile.include_sources if source_id in source_ids]


def source_snapshot_lines(source: SourceConfig) -> list[str]:
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
        leakage_risk_path = build_dir / "benchmark_leakage_risk.json"
        reference_manifest_path = build_dir / "benchmark_reference_manifest.json"
        reference_status_path = build_dir / "benchmark_reference_status.json"
        reference_versioning_path = build_dir / "benchmark_reference_versioning.json"
        return BenchmarkExportInputs(
            items=_load_models(build_dir / "benchmark_manifest.json", BenchmarkItemRecord),
            selection_audit=_load_models(
                build_dir / "benchmark_selection_audit.json",
                BenchmarkSelectionAuditRecord,
            ),
            stability_policy=_load_json(build_dir / "benchmark_stability_policy.json"),
            card_markdown=(build_dir / "BENCHMARK_CARD.md").read_text(encoding="utf-8"),
            leakage_risk=(
                _load_json(leakage_risk_path)
                if leakage_risk_path.exists()
                else None
            ),
            reference_manifest=(
                BenchmarkReferenceManifestRecord.model_validate(_load_json(reference_manifest_path))
                if reference_manifest_path.exists()
                else None
            ),
            reference_status=(
                BenchmarkReferenceStatusArtifactRecord.model_validate(_load_json(reference_status_path))
                if reference_status_path.exists()
                else None
            ),
            reference_versioning=(
                _load_json(reference_versioning_path)
                if reference_versioning_path.exists()
                else None
            ),
        )
    except (FileNotFoundError, KeyError, StageExecutionError, ValidationError) as exc:
        raise StageExecutionError(
            "release export requires build-release benchmark artifacts; "
            "rerun build-release with benchmark outputs before exporting"
        ) from exc


def _filter_benchmark_reference_manifest(
    manifest: BenchmarkReferenceManifestRecord | None,
    selected_ids: set[str],
) -> BenchmarkReferenceManifestRecord | None:
    if manifest is None:
        return None
    items = [item for item in manifest.items if item.item_id in selected_ids]
    return manifest.model_copy(update={"items": items})


def _filter_benchmark_reference_status(
    status: BenchmarkReferenceStatusArtifactRecord | None,
    selected_ids: set[str],
) -> BenchmarkReferenceStatusArtifactRecord | None:
    if status is None:
        return None
    items = [item for item in status.items if item.item_id in selected_ids]
    counts = Counter(item.public_reference_status for item in items)
    for item in items:
        counts[f"adjudication_{item.adjudication_status}"] += 1
    counts["reference_ready"] = sum(
        1
        for item in items
        if item.public_reference_status in {"reviewed", "adjudicated"} and item.adjudication_status == "adjudicated"
    )
    counts["blocked_or_draft"] = sum(
        1
        for item in items
        if item.public_reference_status in {"draft", "not_available"} or item.adjudication_status == "blocked"
    )
    return status.model_copy(update={"counts": dict(counts), "items": items})


def _filter_benchmark_leakage_risk(
    leakage_risk: dict[str, Any] | None,
    selected_ids: set[str],
) -> dict[str, Any] | None:
    if leakage_risk is None:
        return None

    def selected_risk(risk: dict[str, Any]) -> dict[str, Any] | None:
        benchmark_item_ids = [
            item_id
            for item_id in risk.get("benchmark_item_ids", [])
            if item_id in selected_ids
        ]
        non_benchmark_item_ids = [
            item_id
            for item_id in risk.get("non_benchmark_item_ids", risk.get("holdout_item_ids", []))
            if item_id in selected_ids
        ]
        if not benchmark_item_ids or not non_benchmark_item_ids:
            return None
        filtered = {
            **risk,
            "benchmark_item_ids": benchmark_item_ids,
            "holdout_item_ids": non_benchmark_item_ids,
            "non_benchmark_item_ids": non_benchmark_item_ids,
        }
        resolution = filtered.get("resolution")
        if isinstance(resolution, dict):
            filtered["resolution"] = {
                **resolution,
                "benchmark_item_ids": [
                    item_id
                    for item_id in resolution.get("benchmark_item_ids", [])
                    if item_id in selected_ids
                ],
                "non_benchmark_item_ids": [
                    item_id
                    for item_id in resolution.get("non_benchmark_item_ids", [])
                    if item_id in selected_ids
                ],
            }
        return filtered

    resolved_risks = [
        filtered
        for risk in leakage_risk.get("resolved_risks", [])
        if isinstance(risk, dict)
        for filtered in [selected_risk(risk)]
        if filtered is not None
    ]
    unresolved_risks = [
        filtered
        for risk in leakage_risk.get("unresolved_risks", [])
        if isinstance(risk, dict)
        for filtered in [selected_risk(risk)]
        if filtered is not None
    ]
    risks = [
        filtered
        for risk in leakage_risk.get("risks", [])
        if isinstance(risk, dict)
        for filtered in [selected_risk(risk)]
        if filtered is not None
    ]
    stale_resolutions = [
        stale
        for stale in leakage_risk.get("stale_resolutions", [])
        if isinstance(stale, dict)
        and (
            any(item_id in selected_ids for item_id in stale.get("benchmark_item_ids", []))
            or any(item_id in selected_ids for item_id in stale.get("non_benchmark_item_ids", []))
        )
    ]
    status = "ok" if not unresolved_risks and not stale_resolutions else "blocked"
    return {
        **leakage_risk,
        "accepted_resolution_count": len(resolved_risks),
        "export_scope": "selected_alpha_items",
        "risk_count": len(risks),
        "risks": risks,
        "resolved_risks": resolved_risks,
        "stale_resolutions": stale_resolutions,
        "status": status,
        "unresolved_count": len(unresolved_risks),
        "unresolved_risks": unresolved_risks,
    }


def _copy_benchmark_reference_files(
    manifest: BenchmarkReferenceManifestRecord | None,
    build_dir: Path,
    export_dir: Path,
) -> list[Path]:
    if manifest is None:
        return []
    copied: list[Path] = []
    for item in manifest.items:
        paths = []
        if item.transcription_reference is not None:
            paths.append(item.transcription_reference.path)
        paths.extend(reference.path for reference in item.layout_label_references)
        for relative_path in paths:
            source = build_dir / relative_path
            if not source.is_file():
                raise StageExecutionError(f"release export benchmark reference file is missing: {source}")
            target = export_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def _load_annotation_pilot_export_inputs(build_dir: Path) -> AnnotationPilotExportInputs:
    try:
        return AnnotationPilotExportInputs(
            manifest=AnnotationPilotManifestRecord.model_validate(
                _load_json(build_dir / "annotation_pilot_manifest.json")
            ),
            selection_audit=_load_models(
                build_dir / "annotation_pilot_selection_audit.json",
                AnnotationPilotSelectionAuditRecord,
            ),
        )
    except (FileNotFoundError, KeyError, StageExecutionError, ValidationError) as exc:
        raise StageExecutionError(
            "release export requires build-release annotation pilot artifacts; "
            "rerun build-release with annotation pilot outputs before exporting"
        ) from exc


def _filter_annotation_pilot_manifest(
    manifest: AnnotationPilotManifestRecord,
    selected_ids: set[str],
) -> AnnotationPilotManifestRecord:
    items = [item for item in manifest.items if item.item_id in selected_ids]
    return AnnotationPilotManifestRecord(
        pilot_id=manifest.pilot_id,
        version=manifest.version,
        description=manifest.description,
        selection_policy=manifest.selection_policy,
        annotation_guidance=manifest.annotation_guidance,
        transcription_required_for_release=manifest.transcription_required_for_release,
        layout_labels_required_for_release=manifest.layout_labels_required_for_release,
        pilot_item_count=len(items),
        transcription_task_count=sum(1 for item in items if "transcription" in item.tasks),
        layout_label_task_count=sum(1 for item in items if "layout_labels" in item.tasks),
        items=items,
    )


def _benchmark_card_for_export(inputs: BenchmarkExportInputs, items: list[BenchmarkItemRecord]) -> str:
    try:
        benchmark_id = str(inputs.stability_policy["benchmark_id"])
        description = str(inputs.stability_policy.get("description", "Exported benchmark subset."))
        selection_policy = str(inputs.stability_policy["selection_policy"])
        review_bar = str(inputs.stability_policy["review_bar"])
        stability_policy = dict(inputs.stability_policy["stability_policy"])
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise StageExecutionError("release export benchmark policy is invalid for card rendering") from exc
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


build_source_stats = _build_source_stats
is_release_diff_baseline = _is_release_diff_baseline
validate_release_diff_baseline = _validate_release_diff_baseline
parse_exported_at = _parse_exported_at
natural_sort_key = _natural_sort_key
audit_item_payload_for_export = _audit_item_payload
public_item_payload = _public_item_payload
build_release_diff = _build_release_diff
item_change_types = _item_change_types
removal_reason = _removal_reason
count_deltas = _count_deltas
sanitize_portable_value = _sanitize_portable_value
looks_like_local_path = _looks_like_local_path
review_queue_payloads = _review_queue_payloads
review_queue_payload = _review_queue_payload
copy_review_previews = _copy_review_previews
build_classification_stats = _build_classification_stats
build_privacy_stats = _build_privacy_stats
synthetic_composition_lines = _synthetic_composition_lines
changelog_doc = _changelog_doc
ordered_sources = _ordered_sources
source_priority = _source_priority
split_sort_key = _split_sort_key
current_commit_sha = _current_commit_sha
load_json = _load_json
load_baseline_item_manifest = _load_baseline_item_manifest
load_models = _load_models
load_benchmark_export_inputs = _load_benchmark_export_inputs
filter_benchmark_reference_manifest = _filter_benchmark_reference_manifest
filter_benchmark_reference_status = _filter_benchmark_reference_status
filter_benchmark_leakage_risk = _filter_benchmark_leakage_risk
copy_benchmark_reference_files = _copy_benchmark_reference_files
load_annotation_pilot_export_inputs = _load_annotation_pilot_export_inputs
filter_annotation_pilot_manifest = _filter_annotation_pilot_manifest
benchmark_card_for_export = _benchmark_card_for_export
write_markdown = _write_markdown
checksum_category = _checksum_category

# Backward-compatible names for older tests and callers that reached into the
# original alpha-private helper surface before F4e.
_copy_export_assets = copy_export_assets
_write_standard_release_artifacts = write_standard_release_artifacts
