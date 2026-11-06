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
    load_yidtaknl_snapshot,
    yidtaknl_entry_exclusion_reason,
    yidtaknl_usage_scope_is_valid,
)
from hocrgen.manifests.models import ItemRecord
from hocrgen.source_ops import _inspect_source
from hocrgen.utils.hashing import sha256_file

SOURCE_ID = "yidtaknl_vaybertaytsh_gt"
SNAPSHOT_ROOT = package_root() / "data" / "yidtaknl" / "snapshot"
NLI_PAGE_7 = "nli_990021163940205171__p0007"
NLI_PAGE_8 = "nli_990021163940205171__p0008"
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


def test_yidtaknl_source_is_review_only_and_outside_the_public_profile() -> None:
    bundle, source = _bundle_and_source()
    assert source.fetcher == "yidtaknl"
    assert source.status.value == "review_only"
    assert source.default_public_release is False
    assert source.allowed_content_types == ["printed_historical"]
    assert source.rights_strategy.values == ["CC-BY-4.0"]
    assert source.normalized_license == "CC-BY-4.0"
    assert source.rights_classification.value == "open_with_attribution"
    # No privacy-review gate for public-domain historical sources (maintainer decision 2026-11-06).
    assert source.requires_manual_review is False
    assert bundle.privacy_rules.source_defaults[SOURCE_ID].value == "clear"
    assert SOURCE_ID not in bundle.profiles["profile_open_v1"].include_sources
    assert SOURCE_ID in bundle.profiles["profile_review_v1"].include_sources
    # The BGU Pinkas dataset is not admitted in F8d: its scan provenance is unverified.
    assert "pinkas_dataset_bgu" not in {candidate.id for candidate in bundle.source_registry.sources}


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
    assert yidtaknl_entry_exclusion_reason(entry, source) == "missing_character_level_scope"


def test_rights_language_and_reference_status_gates() -> None:
    _, source = _bundle_and_source()
    entries = _entries()
    # The HUC copy's photographs carry no open licence, whatever the dataset licence says.
    assert yidtaknl_entry_exclusion_reason(entries[HUC_ENTRY], source) == "scan_rights_not_open"
    for entry_id in (NLI_PAGE_7, NLI_PAGE_8):
        assert yidtaknl_entry_exclusion_reason(entries[entry_id], source) is None

    def variant(mutate) -> dict:
        entry = json.loads(json.dumps(entries[NLI_PAGE_7]))
        mutate(entry)
        return entry

    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["rights"].update(license_expression="CC-BY-NC-4.0")), source) == "license_not_in_source_lane"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["rights"].update(verification_status="unverified")), source) == "rights_not_primary_page_checked"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["scan"].update(license_slug="public-domain-non-commercial-use")), source) == "scan_rights_not_open"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["scan"].update(scan_redistribution_allowed=False)), source) == "scan_rights_not_open"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e.update(languages=["he"])), source) == "out_of_scope_language"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e.update(languages=["yi", "he"])), source) == "out_of_scope_language"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["text"].pop("sha256")), source) == "no_pinned_text"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["text"].update(adjudication_status="adjudicated")), source) == "unsupported_reference_status"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e["text"].update(reference_eligible=True)), source) == "unsupported_reference_status"
    assert yidtaknl_entry_exclusion_reason(variant(lambda e: e.update(files=[])), source) == "no_raster_asset"


def test_fixture_assets_and_text_match_their_pins() -> None:
    snapshot, _ = load_yidtaknl_snapshot(SNAPSHOT_ROOT)
    assert snapshot["dataset_doi"] == "10.6084/m9.figshare.25422844.v1"
    assert snapshot["dataset_license"] == "CC-BY-4.0"
    entries = _entries()
    for entry_id in (NLI_PAGE_7, NLI_PAGE_8):
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


def test_yidtaknl_discovery_emits_stable_ids_and_scope_metadata() -> None:
    bundle, source = _bundle_and_source()
    importer = YidTakNLImporter()
    options = StageOptions()
    discovered = importer.discover_candidates(source, bundle, options)
    assert [candidate.candidate_id for candidate in discovered] == [
        f"{SOURCE_ID}:{NLI_PAGE_7}",
        f"{SOURCE_ID}:{NLI_PAGE_8}",
    ]
    assert [candidate.candidate_id for candidate in importer.discover_candidates(source, bundle, StageOptions(max_items=1))] == [
        f"{SOURCE_ID}:{NLI_PAGE_7}"
    ]
    enriched = importer.fetch_candidate_metadata(source, bundle, discovered, options)
    page = enriched[0]
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

    (config_root / "yidtaknl_snapshot" / "text" / "nli_990021163940205171__0007_p007.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="text checksum mismatch"):
        importer.acquire_items(source, bundle, _items(enriched[:1]), tmp_path / "acquire-text", options)

    Path(enriched[1].asset_references[0].resolved_path or "").write_bytes(b"tampered")
    with pytest.raises(StageExecutionError, match="asset checksum mismatch"):
        importer.acquire_items(source, bundle, _items(enriched[1:]), tmp_path / "acquire-asset", options)


def test_yidtaknl_source_health_reports_missing_text_and_exclusions(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (2, 2)
    assert all(check["status"] == "ok" for check in checks)

    config_root = _copy_snapshot_config(tmp_path)
    (config_root / "yidtaknl_snapshot" / "text" / "nli_990021163940205171__0008_p008.txt").unlink()
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert candidate_count == 2
    assert asset_count == 1
    assert any(check["name"] == "yidtaknl_entry_text" and check["status"] == "error" for check in checks)
    exclusions = next(check for check in checks if check["name"] == "yidtaknl_entry_exclusions")
    assert exclusions["actual"] == {"scan_rights_not_open": 1}
    assert all(not str(check.get("path", "")).startswith("/") for check in checks)
