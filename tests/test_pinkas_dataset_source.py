from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import unicodedata
from pathlib import Path

import pytest
import yaml
from PIL import Image

from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.pinkas_dataset import (
    PinkasDatasetImporter,
    load_entry_page_lines,
    load_pinkas_dataset_snapshot,
    parse_page_xml_lines,
    pinkas_dataset_entry_exclusion_reason,
    read_annotation_bytes,
)
from hocrgen.fetchers.nli_scan_evidence import nli_scan_evidence
from hocrgen.manifests.models import ItemRecord
from hocrgen.source_ops import _inspect_source
from hocrgen.utils.hashing import sha256_file

SOURCE_ID = "pinkas_dataset_bgu"
SNAPSHOT_ROOT = package_root() / "data" / "pinkas_dataset_bgu" / "snapshot"
PAGE_105 = "nli_990000445290205171__page105_right"
PAGE_112 = "nli_990000445290205171__page112_right"

MINIMAL_PAGE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2018-07-15">
  <Page imageFilename="x.jpg" imageWidth="1000" imageHeight="2000">
    <TextRegion id="r1" type="paragraph">
      <Coords points="0,0 1000,0 1000,2000 0,2000"/>
      <TextLine id="l1">
        <Coords points="100,200 500,200 500,300 100,300"/>
        <TextEquiv><Unicode>\xd7\xa9\xd7\x9c\xd7\x95\xd7\x9d</Unicode></TextEquiv>
      </TextLine>
      <TextLine id="l2">
        <Coords points="900,1900 1100,1900 1100,2100 900,2100"/>
        <TextEquiv><Unicode></Unicode></TextEquiv>
      </TextLine>
      <TextLine id="degenerate"><Coords points="1,1 2,2"/></TextLine>
    </TextRegion>
  </Page>
</PcGts>
"""


def _bundle_and_source():
    bundle = load_and_validate_bundle()
    return bundle, next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)


def _entries() -> dict[str, dict]:
    _, entries = load_pinkas_dataset_snapshot(SNAPSHOT_ROOT)
    return {entry["entry_id"]: entry for entry in entries}


def _copy_snapshot_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(SNAPSHOT_ROOT, config_root / "pinkas_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == SOURCE_ID:
            source["settings"]["extra"]["pinkas_dataset_snapshot_root"] = "pinkas_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return config_root


def test_pinkas_dataset_source_is_review_only_and_distinct_from_pinkas_open() -> None:
    bundle, source = _bundle_and_source()
    assert source.fetcher == "pinkas_dataset"
    assert source.status.value == "review_only"
    assert source.default_public_release is False
    assert source.requires_manual_review is False
    assert source.allowed_content_types == ["handwritten_historical"]
    assert source.rights_strategy.values == ["CC-BY-4.0"]
    assert source.rights_classification.value == "open_with_attribution"
    assert bundle.privacy_rules.source_defaults[SOURCE_ID].value == "clear"
    assert SOURCE_ID not in bundle.profiles["profile_open_v1"].include_sources
    assert SOURCE_ID in bundle.profiles["profile_review_v1"].include_sources
    pinkas_open = next(candidate for candidate in bundle.source_registry.sources if candidate.id == "pinkas_open")
    assert pinkas_open.fetcher == "pinkas" and pinkas_open.settings.extra.get("pinkas_dataset_snapshot_root") is None


def test_fixture_entries_carry_nli_scan_rights_and_dataset_annotation_rights() -> None:
    for entry in _entries().values():
        scan = entry["scan"]
        assert scan["holding_institution"] == "National Library of Israel"
        assert scan["record_id"] == "990000445290205171"
        assert scan["manifest_capture"] == "iiif/nli_990000445290205171_manifest_capture.json"
        evidence = nli_scan_evidence(SNAPSHOT_ROOT, scan)
        assert evidence.problem is None
        assert evidence.metadata()["license_slug"] == "public-domain-free-use"
        assert evidence.metadata()["iiif_canvas_count"] == 330
        selected = {item["canvas_id"]: item for item in evidence.capture.selected_canvases}
        assert selected[scan["iiif_canvas"]]["label"] == scan["canvas_label"]
        assert selected[scan["iiif_canvas"]]["region"] == "right_half"
        assert scan["license_url"].endswith("/public-domain-free-use")
        assert scan["canvas_region"] == "right_half"
        assert "4°662" in scan["shelfmark"]
        assert entry["rights"]["license_expression"] == "CC-BY-4.0"
        assert "Pinkas Dataset" in entry["rights"]["attribution_text"]
        assert "Scan: National Library of Israel, Ms. Heb. 4°662" in entry["rights"]["attribution_text"]
        assert entry["languages"] == ["he", "yi"]
        assert entry["usage_scope"]["evaluation_scope"] == "character_level_only"
        annotation = entry["annotation"]
        assert annotation["adjudication_status"] == "not_adjudicated"
        assert annotation["reference_eligible"] is False
        assert annotation["heocr_attestation"] == "none"


def test_exclusion_gates() -> None:
    _, source = _bundle_and_source()
    entries = _entries()
    for entry_id in (PAGE_105, PAGE_112):
        assert pinkas_dataset_entry_exclusion_reason(entries[entry_id], source, SNAPSHOT_ROOT) is None

    def variant(mutate) -> dict:
        entry = json.loads(json.dumps(entries[PAGE_105]))
        mutate(entry)
        return entry

    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["rights"].update(license_expression="CC-BY-NC-SA-4.0")), source, SNAPSHOT_ROOT) == "license_not_in_source_lane"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["rights"].update(verification_status="unverified")), source, SNAPSHOT_ROOT) == "rights_not_primary_page_checked"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["scan"].pop("manifest_capture")), source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["scan"].update(manifest_capture="iiif/missing.json")), source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["scan"].update(scan_redistribution_allowed=False)), source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["scan"].pop("iiif_canvas")), source, SNAPSHOT_ROOT) == "scan_not_matched"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e.update(languages=["he", "de"])), source, SNAPSHOT_ROOT) == "out_of_scope_language"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["usage_scope"].update(evaluation_scope="word_level")), source, SNAPSHOT_ROOT) == "missing_character_level_scope"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["annotation"].pop("sha256")), source, SNAPSHOT_ROOT) == "no_pinned_annotation"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e["annotation"].update(adjudication_status="adjudicated")), source, SNAPSHOT_ROOT) == "unsupported_reference_status"
    assert pinkas_dataset_entry_exclusion_reason(variant(lambda e: e.update(files=[])), source, SNAPSHOT_ROOT) == "no_raster_asset"


def test_committed_page_xml_is_the_upstream_bytes_and_assets_match_pins() -> None:
    for entry in _entries().values():
        upstream = entry["upstream"]
        annotation = entry["annotation"]
        xml_bytes = read_annotation_bytes(SNAPSHOT_ROOT / annotation["local_path"], annotation["encoding"])
        assert len(xml_bytes) == upstream["page_xml_bytes"]
        assert hashlib.sha256(xml_bytes).hexdigest() == annotation["sha256"] == upstream["page_xml_sha256"]
        assert gzip.decompress((SNAPSHOT_ROOT / annotation["local_path"]).read_bytes()) == xml_bytes
        asset = entry["files"][0]
        asset_path = SNAPSHOT_ROOT / asset["local_path"]
        assert sha256_file(asset_path) == asset["sha256"]
        assert asset_path.stat().st_size == asset["bytes"] < 150_000
        with Image.open(asset_path) as image:
            assert image.size == (asset["width_px"], asset["height_px"])
        assert upstream["split"] == "train"


def test_page_xml_lines_scale_consistently_onto_the_thumbnail() -> None:
    for entry in _entries().values():
        asset = entry["files"][0]
        upstream = entry["upstream"]
        page = load_entry_page_lines(SNAPSHOT_ROOT, entry)
        xml_bytes = read_annotation_bytes(SNAPSHOT_ROOT / entry["annotation"]["local_path"], "gzip")
        full = parse_page_xml_lines(xml_bytes)
        assert (page.source_width, page.source_height) == (upstream["image_width_px"], upstream["image_height_px"])
        assert (page.width, page.height) == (asset["width_px"], asset["height_px"])
        assert (full.width, full.height) == (upstream["image_width_px"], upstream["image_height_px"])
        assert page.scale_x == pytest.approx(asset["width_px"] / upstream["image_width_px"])
        assert page.scale_y == pytest.approx(asset["height_px"] / upstream["image_height_px"])
        # The thumbnail keeps the upstream aspect ratio, so both axes scale alike.
        assert page.scale_x == pytest.approx(page.scale_y, rel=0.002)
        assert len(page.lines) == len(full.lines) == entry["annotation"]["line_count"]
        assert page.reading_order_source == "document_order"
        for scaled, original in zip(page.lines, full.lines, strict=True):
            assert (scaled.line_id, scaled.region_id, scaled.text) == (original.line_id, original.region_id, original.text)
            assert unicodedata.is_normalized("NFC", scaled.text)
            assert scaled.geometry.type == "bbox_polygon"
            assert len(scaled.geometry.polygon) == len(original.geometry.polygon) >= 3
            for point, source_point in zip(scaled.geometry.polygon, original.geometry.polygon, strict=True):
                assert point.x == pytest.approx(source_point.x * page.scale_x, abs=0.01)
                assert point.y == pytest.approx(source_point.y * page.scale_y, abs=0.01)
                assert 0 <= point.x <= page.width and 0 <= point.y <= page.height
            bbox, source_bbox = scaled.geometry.bbox, original.geometry.bbox
            assert bbox.x == pytest.approx(source_bbox.x * page.scale_x, abs=0.02)
            assert bbox.width == pytest.approx(source_bbox.width * page.scale_x, abs=0.05)
            assert bbox.height == pytest.approx(source_bbox.height * page.scale_y, abs=0.05)
        assert [line.reading_order for line in page.lines] == list(range(1, len(page.lines) + 1))
        assert sum(1 for line in page.lines if line.text) >= len(page.lines) - 1
        assert any("א" <= char <= "ת" for line in page.lines for char in line.text)


def test_page_xml_parser_clamps_skips_degenerate_lines_and_rejects_other_xml() -> None:
    page = parse_page_xml_lines(MINIMAL_PAGE_XML, (100, 200))
    assert [line.line_id for line in page.lines] == ["l1", "l2"]
    first, second = page.lines
    assert first.text == "שלום"
    assert first.geometry.bbox.model_dump() == {"x": 10.0, "y": 20.0, "width": 40.0, "height": 10.0}
    assert second.text == ""
    assert max(point.x for point in second.geometry.polygon) == 100.0
    assert max(point.y for point in second.geometry.polygon) == 200.0
    with pytest.raises(StageExecutionError, match="not a supported PAGE XML"):
        parse_page_xml_lines(b"<alto xmlns='http://www.loc.gov/standards/alto/ns-v4#'/>")
    with pytest.raises(StageExecutionError, match="imageWidth"):
        parse_page_xml_lines(MINIMAL_PAGE_XML.replace(b'imageWidth="1000" ', b""))


def test_discovery_metadata_and_acquire_checksums(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    importer = PinkasDatasetImporter()
    options = StageOptions()
    discovered = importer.discover_candidates(source, bundle, options)
    assert [candidate.candidate_id for candidate in discovered] == [f"{SOURCE_ID}:{PAGE_105}", f"{SOURCE_ID}:{PAGE_112}"]
    enriched = importer.fetch_candidate_metadata(source, bundle, discovered, options)
    metadata = enriched[0].metadata
    assert enriched[0].source_url == "https://www.nli.org.il/he/manuscripts/NNL_ALEPH990000445290205171/NLI"
    assert enriched[0].raw_rights_text == "CC-BY-4.0"
    assert metadata["period"] == "historical"
    assert metadata["evaluation_scope"] == "character_level_only"
    assert metadata["languages"] == ["he", "yi"]
    assert metadata["adjudication_status"] == "not_adjudicated"
    assert metadata["annotation_reference"] == f"page_xml/{PAGE_105}.xml.gz"
    assert metadata["annotation_line_count"] == 45
    assert metadata["scan_canvas_region"] == "right_half"
    assert metadata["source_group_id"] == "pinkas_dataset_bgu:nli_990000445290205171"
    assert metadata["scan_rights"]["decision"] == "accepted"
    assert metadata["scan_rights"]["rights_basis"] == "iiif_manifest_license_slug"
    assert not [value for value in metadata.values() if isinstance(value, str) and value.startswith("/")]

    config_root = _copy_snapshot_config(tmp_path)
    bundle = load_and_validate_bundle(config_root)
    source = next(candidate for candidate in bundle.source_registry.sources if candidate.id == SOURCE_ID)
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    items = [
        ItemRecord(
            **record.model_dump(),
            item_id=record.candidate_id,
            normalized_license="CC-BY-4.0",
            rights_classification="open_with_attribution",
            eligibility="review_required",
            eligibility_reason="pinkas dataset fixture",
        )
        for record in enriched
    ]
    acquired = importer.acquire_items(source, bundle, items, tmp_path / "acquire", options)
    assert [item.acquired_assets[0].sha256 for item in acquired] == [record.metadata["expected_asset_sha256"] for record in enriched]
    xml_path = config_root / "pinkas_snapshot" / "page_xml" / f"{PAGE_105}.xml.gz"
    xml_path.write_bytes(gzip.compress(b"<PcGts/>"))
    with pytest.raises(StageExecutionError, match="PAGE XML checksum mismatch"):
        importer.acquire_items(source, bundle, items[:1], tmp_path / "acquire-xml", options)
    Path(enriched[1].asset_references[0].resolved_path or "").write_bytes(b"tampered")
    with pytest.raises(StageExecutionError, match="asset checksum mismatch"):
        importer.acquire_items(source, bundle, items[1:], tmp_path / "acquire-asset", options)


def test_source_health_reports_page_xml_lines_and_problems(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (2, 2)
    assert all(check["status"] == "ok" for check in checks)
    assert [check["actual"] for check in checks if check["name"] == "pinkas_dataset_entry_page_xml"] == [
        {"line_count": 45},
        {"line_count": 34},
    ]

    config_root = _copy_snapshot_config(tmp_path)
    (config_root / "pinkas_snapshot" / "page_xml" / f"{PAGE_112}.xml.gz").write_bytes(gzip.compress(b"tampered"))
    bundle = load_and_validate_bundle(config_root)
    source = next(candidate for candidate in bundle.source_registry.sources if candidate.id == SOURCE_ID)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (2, 1)
    failing = [check for check in checks if check["status"] == "error"]
    assert [check["name"] for check in failing] == ["pinkas_dataset_entry_page_xml"]
    assert "checksum mismatch" in failing[0]["message"]
    assert all(not str(check.get("path", "")).startswith("/") for check in checks)
