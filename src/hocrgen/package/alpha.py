from __future__ import annotations

import json
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import ReleaseProfile, SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import (
    AlphaExportedItemRecord,
    AlphaReleaseRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    ExportedAssetRecord,
    PrivacyScannedItemRecord,
    ReviewQueueRecord,
    SplitAssignmentRecord,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
SPLIT_ORDER = {"train": 0, "validation": 1, "test": 2}


@dataclass(frozen=True)
class AlphaExportConfig:
    version: str
    output_dir: Path | None = None
    max_real_items: int = 10
    max_synthetic_items: int = 2


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
    profile = bundle.profiles[profile_id]
    build_dir = run_dir / "build_release"
    export_dir = config.output_dir.resolve() if config.output_dir else (run_dir.parent.parent / "exports" / config.version).resolve()
    if export_dir.exists():
        shutil.rmtree(export_dir)
    release_items = _load_models(build_dir / "item_manifest.json", PrivacyScannedItemRecord)
    review_required_items = _load_models(build_dir / "review_required_items.json", PrivacyScannedItemRecord)
    blocked_items = _load_models(build_dir / "blocked_items.json", PrivacyScannedItemRecord)
    split_manifest = _load_models(build_dir / "split_manifest.json", SplitAssignmentRecord)
    duplicate_relations = _load_models(build_dir / "duplicate_relations.json", DuplicateRelationRecord)
    duplicate_clusters = _load_models(build_dir / "duplicate_clusters.json", DuplicateClusterRecord)
    review_queue = _load_models(build_dir / "review_queue.json", ReviewQueueRecord)
    build_release_summary = _load_json(build_dir / "release_summary.json")

    selected_items = _select_alpha_items(release_items, profile, config)
    if not selected_items:
        raise StageExecutionError("alpha export selection is empty")

    selected_ids = {item.item_id for item in selected_items}
    selected_split_manifest = [assignment for assignment in split_manifest if assignment.item_id in selected_ids]
    selected_review_queue = [entry for entry in review_queue if entry.item_id in {item.item_id for item in review_required_items}]

    exported_items = _copy_export_assets(selected_items, export_dir / "data")
    source_stats = _build_source_stats(exported_items, duplicate_relations)
    classification_stats = _build_classification_stats(exported_items)
    privacy_stats = _build_privacy_stats(exported_items)
    split_counts = dict(Counter(item.split for item in exported_items if item.split))
    included_sources = _ordered_sources(profile, {item.source_id for item in exported_items})
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
    available_synthetic = sum(1 for item in release_items if item.is_synthetic)
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
        "synthetic_clamped_to_real": exported_synthetic_items < min(config.max_synthetic_items, available_synthetic),
        "version": config.version,
    }

    manifests_dir = export_dir / "manifests"
    docs_dir = export_dir / "docs"
    write_json(manifests_dir / "item_manifest.json", {"items": [item.model_dump(mode="json") for item in exported_items]})
    write_json(manifests_dir / "split_manifest.json", {"items": [item.model_dump(mode="json") for item in selected_split_manifest]})
    write_json(manifests_dir / "source_stats.json", source_stats)
    write_json(manifests_dir / "classification_stats.json", classification_stats)
    write_json(manifests_dir / "privacy_stats.json", privacy_stats)
    write_json(manifests_dir / "release_summary.json", release_summary)
    write_json(manifests_dir / "duplicate_relations.json", {"items": [item.model_dump(mode="json") for item in duplicate_relations]})
    write_json(manifests_dir / "duplicate_clusters.json", {"items": [item.model_dump(mode="json") for item in duplicate_clusters]})
    write_json(manifests_dir / "review_required_items.json", {"items": [item.model_dump(mode="json") for item in review_required_items]})
    write_json(manifests_dir / "blocked_items.json", {"items": [item.model_dump(mode="json") for item in blocked_items]})
    write_json(manifests_dir / "review_queue.json", {"items": [item.model_dump(mode="json") for item in selected_review_queue]})
    write_json(manifests_dir / "release_record.json", release_record.model_dump(mode="json"))

    _write_markdown(docs_dir / "DATASET_CARD.md", _dataset_card(config.version, profile, exported_items, review_required_items, blocked_items))
    _write_markdown(
        docs_dir / "RELEASE_NOTES.md",
        _release_notes(config.version, release_summary, source_stats, included_sources),
    )
    _write_markdown(
        docs_dir / "PROVENANCE.md",
        _provenance_doc(bundle, profile, included_sources, exported_at, commit_sha),
    )

    summary_path = run_dir / "export_alpha" / "summary.json"
    write_json(
        summary_path,
        {
            "export_dir": str(export_dir),
            "item_manifest": "manifests/item_manifest.json",
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
        docs_dir / "DATASET_CARD.md",
        docs_dir / "RELEASE_NOTES.md",
        docs_dir / "PROVENANCE.md",
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
    ordered = sorted(items, key=lambda item: (_split_sort_key(item.split), _source_priority(profile, item.source_id), item.item_id))
    real_items = [item for item in ordered if not item.is_synthetic]
    synthetic_items = [item for item in ordered if item.is_synthetic]
    selected_real = real_items[: config.max_real_items]
    synthetic_limit = min(config.max_synthetic_items, len(selected_real))
    selected_synthetic = synthetic_items[:synthetic_limit]
    return sorted(
        selected_real + selected_synthetic,
        key=lambda item: (_split_sort_key(item.split), _source_priority(profile, item.source_id), item.item_id),
    )


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
            source_preview_path = None
            release_preview_path = None
            if asset.preview_generated and asset.preview_path:
                preview_source = Path(asset.preview_path)
                if preview_source.exists():
                    preview_target = item_dir / "previews" / preview_source.name
                    preview_target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(preview_source, preview_target)
                    source_preview_path = str(preview_source)
                    release_preview_path = str(preview_target.relative_to(data_dir.parent))
            exported_assets.append(
                ExportedAssetRecord(
                    source_normalized_asset_path=asset.normalized_asset_path,
                    release_asset_path=str(target_path.relative_to(data_dir.parent)),
                    media_type=asset.media_type,
                    asset_format=asset.asset_format,
                    source_preview_path=source_preview_path,
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
) -> str:
    included_sources = sorted({item.source_id for item in items})
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


def _release_notes(version: str, release_summary: dict[str, Any], source_stats: dict[str, Any], included_sources: list[str]) -> str:
    split_counts = release_summary["split_counts"]
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
            "## Notes",
            f"- `max-real-items`: {release_summary['max_real_items']}",
            f"- `max-synthetic-items`: {release_summary['max_synthetic_items']}",
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
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()
    return "unknown"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_models(path: Path, model_type: type[Any]) -> list[Any]:
    payload = _load_json(path)
    return [model_type.model_validate(item) for item in payload["items"]]


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
