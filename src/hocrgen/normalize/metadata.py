from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from hocrgen.config.models import PreviewGenerationMode, QualityThresholds
from hocrgen.manifests.models import AcquiredItemRecord, NormalizedAssetRecord, NormalizedItemRecord
from hocrgen.normalize.files import copy_asset, normalized_asset_destination, preview_destination
from hocrgen.normalize.images import AssetTechnicalMetadata, detect_asset_metadata


@dataclass(frozen=True)
class NormalizationOutputs:
    normalized_items: list[NormalizedItemRecord]
    failed_items: list[NormalizedItemRecord]
    qa_report: dict[str, object]


def _preview_is_required(metadata: AssetTechnicalMetadata, thresholds: QualityThresholds) -> bool:
    if metadata.is_vector:
        return thresholds.preview_policy.require_for_svg
    return thresholds.preview_policy.require_for_raster


def _evaluate_asset(
    metadata: AssetTechnicalMetadata,
    normalized_path: Path,
    thresholds: QualityThresholds,
) -> list[str]:
    reasons: list[str] = []
    if metadata.file_size_bytes < thresholds.minimum_bytes:
        reasons.append("file_too_small")
    if metadata.asset_format == "svg":
        if not thresholds.allow_svg:
            reasons.append("svg_not_allowed")
    elif metadata.asset_format not in {fmt.value for fmt in thresholds.allowed_raster_formats}:
        reasons.append(f"unsupported_raster_format:{metadata.asset_format}")
    if metadata.width is None or metadata.height is None:
        reasons.append("missing_dimensions")
    else:
        if metadata.width < thresholds.minimum_width:
            reasons.append("width_below_threshold")
        if metadata.height < thresholds.minimum_height:
            reasons.append("height_below_threshold")
    if not normalized_path.exists():
        reasons.append("normalized_asset_missing")
    return reasons


def _normalize_asset(
    item_id: str,
    asset_index: int,
    source_path: Path,
    assets_dir: Path,
    thumbnails_dir: Path,
    thresholds: QualityThresholds,
) -> tuple[NormalizedAssetRecord | None, list[str]]:
    if not source_path.exists():
        return None, ["asset_missing"]
    if source_path.stat().st_size == 0:
        return None, ["empty_file"]
    try:
        metadata = detect_asset_metadata(source_path)
    except Exception as exc:
        return None, [f"asset_unreadable:{type(exc).__name__}"]

    normalized_path = normalized_asset_destination(assets_dir, item_id, asset_index, metadata.asset_format)
    copy_asset(source_path, normalized_path)
    reasons = _evaluate_asset(metadata, normalized_path, thresholds)

    preview_generated = False
    preview_path: Path | None = None
    preview_action: str | None = None
    preview_reason: str | None = None
    if thresholds.preview_policy.mode == PreviewGenerationMode.copy_if_supported:
        if metadata.asset_format in {"svg", "png", "jpeg"}:
            preview_path = preview_destination(thumbnails_dir, item_id, asset_index, metadata.asset_format)
            copy_asset(normalized_path, preview_path)
            preview_generated = True
            preview_action = "copied_from_normalized_asset"
        else:
            preview_reason = f"unsupported_preview_format:{metadata.asset_format}"
    else:
        preview_reason = "preview_generation_disabled"

    if _preview_is_required(metadata, thresholds) and not preview_generated:
        reasons.append("preview_required_missing")

    return (
        NormalizedAssetRecord(
            item_id=item_id,
            source_asset_path=str(source_path),
            normalized_asset_path=str(normalized_path),
            asset_format=metadata.asset_format,
            media_type=metadata.media_type,
            width=metadata.width,
            height=metadata.height,
            file_size_bytes=metadata.file_size_bytes,
            sha256=metadata.sha256,
            is_vector=metadata.is_vector,
            normalization_action="copied",
            preview_generated=preview_generated,
            preview_path=str(preview_path) if preview_path else None,
            preview_action=preview_action,
            preview_reason=preview_reason,
        ),
        reasons,
    )


def normalize_items(
    items: list[AcquiredItemRecord],
    thresholds: QualityThresholds,
    assets_dir: Path,
    thumbnails_dir: Path,
) -> NormalizationOutputs:
    normalized_items: list[NormalizedItemRecord] = []
    failed_items: list[NormalizedItemRecord] = []
    fail_reason_counts: Counter[str] = Counter()
    format_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    failed_source_counts: Counter[str] = Counter()

    for item in items:
        source_counts[item.source_id] += 1
        normalized_assets: list[NormalizedAssetRecord] = []
        item_reasons: list[str] = []
        for asset_index, asset in enumerate(item.acquired_assets, start=1):
            normalized_asset, asset_reasons = _normalize_asset(
                item_id=item.item_id,
                asset_index=asset_index,
                source_path=Path(asset.path),
                assets_dir=assets_dir,
                thumbnails_dir=thumbnails_dir,
                thresholds=thresholds,
            )
            if normalized_asset is not None:
                normalized_assets.append(normalized_asset)
                format_counts[normalized_asset.asset_format] += 1
            item_reasons.extend(asset_reasons)

        qa_fail_reasons = sorted(set(item_reasons))
        normalized_item = NormalizedItemRecord(
            **item.model_dump(),
            normalized_assets=normalized_assets,
            qa_status="failed" if qa_fail_reasons else "passed",
            qa_fail_reasons=qa_fail_reasons,
        )
        if qa_fail_reasons:
            failed_items.append(normalized_item)
            fail_reason_counts.update(qa_fail_reasons)
            failed_source_counts[item.source_id] += 1
        else:
            normalized_items.append(normalized_item)

    return NormalizationOutputs(
        normalized_items=normalized_items,
        failed_items=failed_items,
        qa_report={
            "asset_format_counts": dict(format_counts),
            "failed_source_counts": dict(failed_source_counts),
            "failed_count": len(failed_items),
            "failure_reason_counts": dict(fail_reason_counts),
            "normalized_count": len(normalized_items),
            "source_counts": dict(source_counts),
        },
    )
