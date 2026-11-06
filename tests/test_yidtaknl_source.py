from __future__ import annotations

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
from hocrgen.fetchers.yidtaknl import (
    YidTakNLImporter,
    load_yidtaknl_matched_pages,
    load_yidtaknl_snapshot,
    yidtaknl_entry_exclusion_reason,
    yidtaknl_matched_page_problem,
    yidtaknl_usage_scope_is_valid,
)
from hocrgen.fetchers.nli_iiif import decide_nli_rights, load_nli_manifest_capture
from hocrgen.fetchers.nli_scan_evidence import load_scan_capture, nli_scan_evidence
from hocrgen.manifests.models import ItemRecord
from hocrgen.source_ops import _inspect_source
from hocrgen.utils.hashing import sha256_file

SOURCE_ID = "yidtaknl_vaybertaytsh_gt"
SNAPSHOT_ROOT = package_root() / "data" / "yidtaknl" / "snapshot"
NLI_PAGE_7 = "nli_990021163940205171__p0007"
NLI_PAGE_8 = "nli_990021163940205171__p0008"
NLI_1747_PAGE_7 = "nli_001294844__p0007"
NLI_JB899_PAGE_10 = "nli_990012586850205171_ie143609452__p0010"
VENDORED_ENTRIES = (NLI_1747_PAGE_7, NLI_JB899_PAGE_10, NLI_PAGE_7, NLI_PAGE_8)
HUC_ENTRY = "huc_rbr_o_128__p0006"


def _bundle_and_source():
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    return bundle, source


def _entries() -> dict[str, dict]:
    _, entries = load_yidtaknl_snapshot(SNAPSHOT_ROOT)
    return {entry["entry_id"]: entry for entry in entries}


def _copy_snapshot_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(SNAPSHOT_ROOT, config_root / "yidtaknl_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == SOURCE_ID:
            source["settings"]["extra"]["yidtaknl_snapshot_root"] = "yidtaknl_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return config_root


def _items(enriched) -> list[ItemRecord]:
    return [
        ItemRecord(
            **record.model_dump(),
            item_id=record.candidate_id,
            normalized_license="CC-BY-4.0",
            rights_classification="open_with_attribution",
            eligibility="review_required",
            eligibility_reason="yidtaknl fixture",
        )
        for record in enriched
    ]


def test_yidtaknl_source_is_promoted_into_the_public_profile() -> None:
    bundle, source = _bundle_and_source()
    assert source.fetcher == "yidtaknl"
    assert source.status.value == "allowed"
    assert source.default_public_release is True
    assert source.allowed_content_types == ["printed_historical"]
    assert source.rights_strategy.values == ["CC-BY-4.0"]
    assert source.normalized_license == "CC-BY-4.0"
    assert source.rights_classification.value == "open_with_attribution"
    # No privacy-review gate for public-domain historical sources (maintainer decision 2026-11-06).
    assert source.requires_manual_review is False
    assert bundle.privacy_rules.source_defaults[SOURCE_ID].value == "clear"
    # F8g: promoted into the public path; the real-source contract governs its composition.
    assert SOURCE_ID in bundle.profiles["profile_open_v1"].include_sources
    assert bundle.real_source_contract.entry(SOURCE_ID).promotion.value == "promoted"
    assert SOURCE_ID in bundle.profiles["profile_review_v1"].include_sources


def test_every_fixture_entry_carries_the_character_level_scope_marker() -> None:
    for entry in _entries().values():
        assert entry["languages"] == ["yi"]
        assert entry["script"] == "Hebr"
        scope = entry["usage_scope"]
        assert scope["evaluation_scope"] == "character_level_only"
        assert set(scope["allowed_uses"]) == {"training", "character_level_evaluation"}
        assert {"word_level", "language_level_hebrew"} <= set(scope["excluded_evaluations"])
        assert entry["text"]["adjudication_status"] == "not_adjudicated"
        assert entry["text"]["reference_eligible"] is False
        assert entry["text"]["heocr_attestation"] == "none"


@pytest.mark.parametrize(
    "usage_scope",
    [
        None,
        {},
        {"allowed_uses": ["training", "character_level_evaluation"], "excluded_evaluations": ["word_level", "language_level_hebrew"]},
        {
            "evaluation_scope": "character_level_only",
            "allowed_uses": ["training", "word_level_evaluation"],
            "excluded_evaluations": ["word_level", "language_level_hebrew"],
        },
        {
            "evaluation_scope": "character_level_only",
            "allowed_uses": ["training", "character_level_evaluation"],
            "excluded_evaluations": ["word_level"],
        },
        {
            "evaluation_scope": "word_level",
            "allowed_uses": ["training"],
            "excluded_evaluations": ["word_level", "language_level_hebrew"],
        },
        {"evaluation_scope": "character_level_only", "allowed_uses": [], "excluded_evaluations": ["word_level", "language_level_hebrew"]},
    ],
)
def test_entries_without_the_character_level_scope_marker_are_rejected(usage_scope) -> None:
    _, source = _bundle_and_source()
    entry = json.loads(json.dumps(_entries()[NLI_PAGE_7]))
    entry["usage_scope"] = usage_scope
    assert yidtaknl_usage_scope_is_valid(usage_scope) is False
    assert yidtaknl_entry_exclusion_reason(entry, source, SNAPSHOT_ROOT) == "missing_character_level_scope"


def test_rights_language_and_reference_status_gates() -> None:
    _, source = _bundle_and_source()
    entries = _entries()
    # The HUC copy's photographs carry no open licence, whatever the dataset licence says.
    assert yidtaknl_entry_exclusion_reason(entries[HUC_ENTRY], source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    for entry_id in VENDORED_ENTRIES:
        assert yidtaknl_entry_exclusion_reason(entries[entry_id], source, SNAPSHOT_ROOT) is None

    def variant(mutate) -> dict:
        entry = json.loads(json.dumps(entries[NLI_PAGE_7]))
        mutate(entry)
        return entry

    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["rights"].update(license_expression="CC-BY-NC-4.0")), source, SNAPSHOT_ROOT) == "license_not_in_source_lane"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["rights"].update(verification_status="unverified")), source, SNAPSHOT_ROOT) == "rights_not_primary_page_checked"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["scan"].pop("manifest_capture")), source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["scan"].update(iiif_canvas="https://iiif.nli.org.il/IIIFv21/FL0")), source, SNAPSHOT_ROOT) == "scan_not_matched"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["scan"].update(license_url="https://www.nli.org.il/x")), source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["scan"].update(scan_redistribution_allowed=False)), source, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e.update(languages=["he"])), source, SNAPSHOT_ROOT) == "out_of_scope_language"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e.update(languages=["yi", "he"])), source, SNAPSHOT_ROOT) == "out_of_scope_language"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["text"].pop("sha256")), source, SNAPSHOT_ROOT) == "no_pinned_text"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["text"].update(adjudication_status="adjudicated")), source, SNAPSHOT_ROOT) == "unsupported_reference_status"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["text"].update(reference_eligible=True)), source, SNAPSHOT_ROOT) == "unsupported_reference_status"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e.update(files=[])), source, SNAPSHOT_ROOT) == "no_raster_asset"


def test_fixture_assets_and_text_match_their_pins() -> None:
    snapshot, _ = load_yidtaknl_snapshot(SNAPSHOT_ROOT)
    assert snapshot["dataset_doi"] == "10.6084/m9.figshare.25422844.v1"
    assert snapshot["dataset_license"] == "CC-BY-4.0"
    entries = _entries()
    for entry_id in VENDORED_ENTRIES:
        entry = entries[entry_id]
        asset = entry["files"][0]
        asset_path = SNAPSHOT_ROOT / asset["local_path"]
        assert sha256_file(asset_path) == asset["sha256"]
        assert asset_path.stat().st_size == asset["bytes"] < 150_000
        with Image.open(asset_path) as image:
            assert image.size == (asset["width_px"], asset["height_px"])
        # Page-level text has no geometry, so downscaling keeps the upstream aspect ratio and nothing else.
        upstream = entry["upstream"]
        assert abs(asset["height_px"] / asset["width_px"] - upstream["image_height_px"] / upstream["image_width_px"]) < 0.01
        assert entry["text"]["geometry"] == "none"
        text_path = SNAPSHOT_ROOT / entry["text"]["local_path"]
        raw = text_path.read_bytes()
        # The committed text is the upstream bytes, unchanged.
        assert sha256_file(text_path) == entry["text"]["sha256"] == upstream["text_sha256"]
        assert len(raw) == upstream["text_bytes"]
        text = raw.decode("utf-8")
        assert unicodedata.is_normalized("NFC", text)
        assert len(text.splitlines()) == entry["text"]["line_count"]
        assert any("א" <= char <= "ת" for char in text)
        assert entry["scan"]["license_url"].endswith("/public-domain-free-use")
        evidence = nli_scan_evidence(SNAPSHOT_ROOT, entry["scan"])
        assert evidence.problem is None and evidence.decision.license_slug == "public-domain-free-use"


def test_yidtaknl_discovery_emits_stable_ids_and_scope_metadata() -> None:
    bundle, source = _bundle_and_source()
    importer = YidTakNLImporter()
    options = StageOptions()
    discovered = importer.discover_candidates(source, bundle, options)
    assert [candidate.candidate_id for candidate in discovered] == [f"{SOURCE_ID}:{entry_id}" for entry_id in VENDORED_ENTRIES]
    assert [candidate.candidate_id for candidate in importer.discover_candidates(source, bundle, StageOptions(max_items=1))] == [
        f"{SOURCE_ID}:{NLI_1747_PAGE_7}"
    ]
    enriched = importer.fetch_candidate_metadata(source, bundle, discovered, options)
    page = next(record for record in enriched if record.source_item_id == NLI_PAGE_7)
    assert page.raw_rights_text == "CC-BY-4.0"
    assert page.source_url == "https://www.nli.org.il/he/books/NNL_ALEPH990021163940205171/NLI"
    assert page.asset_references[0].reference == "assets/nli_990021163940205171__0007_p007.jpg"
    assert page.asset_references[0].media_type == "image/jpeg"
    metadata = page.metadata
    assert metadata["period"] == "historical"
    assert metadata["content_type"] == "printed_historical"
    assert metadata["languages"] == ["yi"]
    assert metadata["evaluation_scope"] == "character_level_only"
    assert metadata["usage_scope"]["excluded_evaluations"] == ["word_level", "language_level_hebrew"]
    assert metadata["adjudication_status"] == "not_adjudicated"
    assert metadata["reference_eligible"] is False
    assert metadata["text_provenance"] == "htr_corrected_by_humans"
    assert metadata["text_reference"] == "text/nli_990021163940205171__0007_p007.txt"
    assert metadata["source_group_id"] == "yidtaknl:nli_990021163940205171"
    assert metadata["scan_holding_institution"] == "National Library of Israel"
    assert "Reshef" in metadata["attribution_text"] and "CC BY 4.0" in metadata["attribution_text"]
    # Metadata stays portable: no absolute local paths outside the asset resolution field.
    assert not [value for value in metadata.values() if isinstance(value, str) and value.startswith("/")]


def test_yidtaknl_acquire_copies_asset_and_verifies_checksums(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    importer = YidTakNLImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    acquired = importer.acquire_items(source, bundle, _items(enriched), tmp_path / "acquire", options)
    assert [item.acquired_assets[0].sha256 for item in acquired] == [record.metadata["expected_asset_sha256"] for record in enriched]

    by_id = {record.source_item_id: record for record in enriched}
    (config_root / "yidtaknl_snapshot" / "text" / "nli_990021163940205171__0007_p007.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="text checksum mismatch"):
        importer.acquire_items(source, bundle, _items([by_id[NLI_PAGE_7]]), tmp_path / "acquire-text", options)

    Path(by_id[NLI_PAGE_8].asset_references[0].resolved_path or "").write_bytes(b"tampered")
    with pytest.raises(StageExecutionError, match="asset checksum mismatch"):
        importer.acquire_items(source, bundle, _items([by_id[NLI_PAGE_8]]), tmp_path / "acquire-asset", options)


def test_yidtaknl_source_health_reports_missing_text_and_exclusions(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (4, 4)
    assert all(check["status"] == "ok" for check in checks)
    matched = next(check for check in checks if check["name"] == "yidtaknl_matched_pages")
    assert matched["actual"] == {
        "by_work": {"nli_001294844": 16, "nli_990012586850205171_ie143609452": 138},
        "problems": {},
    }

    config_root = _copy_snapshot_config(tmp_path)
    (config_root / "yidtaknl_snapshot" / "text" / "nli_990021163940205171__0008_p008.txt").unlink()
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert candidate_count == 4
    assert asset_count == 3
    assert any(check["name"] == "yidtaknl_entry_text" and check["status"] == "error" for check in checks)
    exclusions = next(check for check in checks if check["name"] == "yidtaknl_entry_exclusions")
    assert exclusions["actual"] == {"scan_rights_not_open": 1}
    assert all(not str(check.get("path", "")).startswith("/") for check in checks)


def test_scan_credit_names_only_the_holder_of_an_admitted_scan() -> None:
    entries = _entries()
    # The HUC scan is rejected, so its entry credits no scan, and never NLI.
    assert "National Library of Israel" not in entries[HUC_ENTRY]["rights"]["attribution_text"]
    assert "Scan:" not in entries[HUC_ENTRY]["rights"]["attribution_text"]
    for entry_id in VENDORED_ENTRIES:
        assert entries[entry_id]["scan"]["holding_institution"] == "National Library of Israel"
        assert entries[entry_id]["rights"]["attribution_text"].endswith("Scan: National Library of Israel.")


def test_matched_pages_pin_upstream_checksums_and_are_never_candidates() -> None:
    snapshot, _ = load_yidtaknl_snapshot(SNAPSHOT_ROOT)
    works = {work["work_id"]: work for work in snapshot["works"]}
    pages = load_yidtaknl_matched_pages(SNAPSHOT_ROOT, snapshot)
    assert len(pages) == 154
    assert all(yidtaknl_matched_page_problem(page, works, SNAPSHOT_ROOT) is None for page in pages)
    for work_id in ("nli_001294844", "nli_990012586850205171_ie143609452"):
        work_pages = [page for page in pages if page["work_id"] == work_id]
        assert len(work_pages) == works[work_id]["page_count"] == works[work_id]["matched_page_count"]
        # In order with no gaps: upstream page n is canvas n-1 of the NLI sequence.
        assert [page["canvas_index"] for page in work_pages] == list(range(len(work_pages)))
        assert works[work_id]["match_in_order"] is True
        assert min(page["match_score"] for page in work_pages) >= 0.95
    # Unmatched or excluded works never appear among matched pages or entries.
    assert {work["upstream_folder"] for work in snapshot["unmatched_works"]}.isdisjoint(work["upstream_folder"] for work in works.values())
    vendored = {page["vendored_entry_id"]: page for page in pages if page.get("vendored_entry_id")}
    entries = _entries()
    assert set(vendored) == {NLI_1747_PAGE_7, NLI_JB899_PAGE_10}
    for entry_id, page in vendored.items():
        assert entries[entry_id]["upstream"]["image_sha1"] == page["image_sha1"]
        assert entries[entry_id]["upstream"]["text_sha1"] == page["text_sha1"]
        assert entries[entry_id]["scan"]["iiif_canvas"] == page["iiif_canvas"]

    bundle, source = _bundle_and_source()
    discovered = {candidate.source_item_id for candidate in YidTakNLImporter().discover_candidates(source, bundle, StageOptions())}
    assert discovered == set(VENDORED_ENTRIES)
    assert yidtaknl_matched_page_problem({**pages[0], "work_id": "unknown"}, works, SNAPSHOT_ROOT) == "unknown_work"
    assert yidtaknl_matched_page_problem({**pages[0], "image_sha1": None}, works, SNAPSHOT_ROOT) == "missing_upstream_checksum"
    uncaptured = {**works, "nli_001294844": {**works["nli_001294844"], "manifest_capture": None}}
    assert yidtaknl_matched_page_problem(pages[0], uncaptured, SNAPSHOT_ROOT) == "scan_rights_not_open"
    assert yidtaknl_matched_page_problem({**pages[0], "iiif_canvas": "https://iiif.nli.org.il/IIIFv21/FL0"}, works, SNAPSHOT_ROOT) == "scan_not_matched"


def test_scan_rights_reuse_the_nli_licence_slug_gate(tmp_path: Path) -> None:
    capture_path = SNAPSHOT_ROOT / "iiif" / "nli_990012586850205171_manifest_capture.json"
    # The JB 899 record's top-level manifest exposes no canvases, so the F8c gate alone rejects it...
    assert decide_nli_rights(display_rights=None, capture=load_nli_manifest_capture(capture_path)).reason == "nli_iiif_manifest_zero_canvases"
    # ...and the pinned volume sequence supplies the canvases the gate sees.
    capture = load_scan_capture(capture_path)
    assert capture.canvas_count == 138
    assert decide_nli_rights(display_rights=None, capture=capture).accepted
    payload = json.loads(capture_path.read_text(encoding="utf-8"))
    payload["volume_sequence"]["canvas_count"] = 0
    zero = tmp_path / "zero.json"
    zero.write_text(json.dumps(payload), encoding="utf-8")
    assert decide_nli_rights(display_rights=None, capture=load_scan_capture(zero)).reason == "nli_iiif_manifest_zero_canvases"
    payload["volume_sequence"] = {"canvas_count": 3}
    zero.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="volume_sequence"):
        load_scan_capture(zero)
    # A non-free-use slug in the pinned capture rejects the scan.
    payload = json.loads((SNAPSHOT_ROOT / "iiif" / "nli_001294844_manifest_capture.json").read_text(encoding="utf-8"))
    payload["manifest"]["license"] = ["https://www.nli.org.il/contenteditors/pages-for-terms-of-use/public-domain-non-commercial-use"]
    (tmp_path / "iiif").mkdir()
    (tmp_path / "iiif" / "c.json").write_text(json.dumps(payload), encoding="utf-8")
    evidence = nli_scan_evidence(tmp_path, {"manifest_capture": "iiif/c.json", "iiif_canvas": "https://iiif.nli.org.il/IIIFv21/FL42163794"})
    assert (evidence.problem, evidence.detail) == ("scan_rights_not_open", "nli_license_non_commercial:public-domain-non-commercial-use")
    assert evidence.metadata()["decision"] == "rejected"
