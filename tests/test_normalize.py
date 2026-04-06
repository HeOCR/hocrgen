from __future__ import annotations

import base64
from pathlib import Path

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord
from hocrgen.normalize.images import detect_asset_metadata
from hocrgen.normalize.metadata import normalize_items


SMALL_PNG_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO9Wl7wAAAAASUVORK5CYII="
)


def _write_png(path: Path) -> Path:
    path.write_bytes(base64.b64decode(SMALL_PNG_BASE64))
    return path


def _make_item(asset_path: Path, *, item_id: str = "test_source:item-001", is_synthetic: bool = False) -> AcquiredItemRecord:
    return AcquiredItemRecord(
        candidate_id=f"{item_id}:candidate",
        source_id="test_source",
        source_item_id="item-001",
        source_url="https://example.test/item-001",
        discovery_method="fixture",
        title="Fixture item",
        fixture_path=None,
        raw_metadata={},
        raw_rights_text="PROJECT-SYNTHETIC",
        asset_references=[],
        metadata={},
        item_id=item_id,
        normalized_license="PROJECT-SYNTHETIC",
        rights_classification="open",
        eligibility="accepted",
        eligibility_reason="allowed_by_profile",
        is_synthetic=is_synthetic,
        provenance={"source_name": "Fixture source", "fetcher": "fixture", "upstream_identifier": "item-001"},
        acquired_assets=[AcquiredAsset(item_id=item_id, path=str(asset_path), sha256="placeholder")],
    )


def test_detect_asset_metadata_reads_png_dimensions(tmp_path: Path) -> None:
    path = _write_png(tmp_path / "tiny.png")

    metadata = detect_asset_metadata(path)

    assert metadata.asset_format == "png"
    assert metadata.width == 1
    assert metadata.height == 1
    assert metadata.media_type == "image/png"
    assert metadata.file_size_bytes > 0


def test_normalize_items_handles_svg_and_generates_preview(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    svg_path = bundle.resolve_path("package://data/pinkas/assets/pinkas_001.svg")
    thresholds = bundle.quality_thresholds.model_copy(update={"minimum_width": 1, "minimum_height": 1})

    outputs = normalize_items(
        items=[_make_item(svg_path, item_id="project_synthetic:item-001", is_synthetic=True)],
        thresholds=thresholds,
        assets_dir=tmp_path / "assets",
        thumbnails_dir=tmp_path / "thumbnails",
    )

    assert len(outputs.normalized_items) == 1
    normalized_item = outputs.normalized_items[0]
    assert normalized_item.qa_status == "passed"
    assert normalized_item.normalized_assets[0].asset_format == "svg"
    assert normalized_item.normalized_assets[0].preview_generated is True
    assert Path(normalized_item.normalized_assets[0].normalized_asset_path).exists()
    assert Path(normalized_item.normalized_assets[0].preview_path or "").exists()


def test_normalize_items_fails_thresholds_for_small_png(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    png_path = _write_png(tmp_path / "small.png")
    thresholds = bundle.quality_thresholds.model_copy(update={"minimum_width": 2, "minimum_height": 2, "minimum_bytes": 1})

    outputs = normalize_items(
        items=[_make_item(png_path)],
        thresholds=thresholds,
        assets_dir=tmp_path / "assets",
        thumbnails_dir=tmp_path / "thumbnails",
    )

    assert outputs.normalized_items == []
    assert len(outputs.failed_items) == 1
    assert outputs.failed_items[0].qa_status == "failed"
    assert "width_below_threshold" in outputs.failed_items[0].qa_fail_reasons
    assert "height_below_threshold" in outputs.failed_items[0].qa_fail_reasons


def test_detect_asset_metadata_rejects_truncated_jpeg(tmp_path: Path) -> None:
    path = tmp_path / "truncated.jpg"
    path.write_bytes(b"\xff\xd8\xff")

    try:
        detect_asset_metadata(path)
    except ValueError as exc:
        assert "truncated jpeg" in str(exc) or "jpeg dimensions not found" in str(exc)
    else:
        raise AssertionError("Expected truncated JPEG to fail metadata detection")
