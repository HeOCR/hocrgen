from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.hash import HashImporter, hash_entry_exclusion_reason, load_hash_snapshot
from hocrgen.manifests.models import ItemRecord
from hocrgen.source_ops import _inspect_source

HASH_SOURCE_IDS = ("hash_nli_any_use", "hash_public_domain")
SNAPSHOT_ROOT = package_root() / "data" / "hash" / "snapshot"
CC_BY_SA_ENTRY = "commons__auerbach_letter_shtenzel_1961__p0001"
PARTIAL_HEBREW_ENTRY = "nli__nnl_archive_al997009912248705171__p0056"


def _sources() -> dict:
    bundle = load_and_validate_bundle()
    return bundle, {source.id: source for source in bundle.source_registry.sources}


def _entries() -> dict[str, dict]:
    _, entries = load_hash_snapshot(SNAPSHOT_ROOT)
    return {entry["entry_id"]: entry for entry in entries}


def _copy_snapshot_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(SNAPSHOT_ROOT, config_root / "hash_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] in HASH_SOURCE_IDS:
            source["settings"]["extra"]["hash_snapshot_root"] = "hash_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return config_root


def test_hash_sources_are_review_only_and_outside_the_public_profile() -> None:
    bundle, sources = _sources()
    for source_id in HASH_SOURCE_IDS:
        source = sources[source_id]
        assert source.fetcher == "hash"
        assert source.status.value == "review_only"
        assert source.default_public_release is False
        assert source.requires_manual_review is True
        assert bundle.privacy_rules.source_defaults[source_id].value == "needs_review"
        assert source_id not in bundle.profiles["profile_open_v1"].include_sources
        assert source_id in bundle.profiles["profile_review_v1"].include_sources
    assert sources["hash_nli_any_use"].normalized_license == "PD-IL"
    assert sources["hash_public_domain"].normalized_license == "PDM-1.0"


def test_no_source_accepts_hash_cc_by_sa_or_out_of_scope_entries() -> None:
    _, sources = _sources()
    entries = _entries()
    assert all("CC-BY-SA-3.0" not in source.rights_strategy.values for source in sources.values())
    for source_id in HASH_SOURCE_IDS:
        assert hash_entry_exclusion_reason(entries[CC_BY_SA_ENTRY], sources[source_id]) == "license_not_in_source_lane"
    assert hash_entry_exclusion_reason(entries[PARTIAL_HEBREW_ENTRY], sources["hash_nli_any_use"]) == "out_of_scope_language"
    partial_hebrew_only = {**entries[PARTIAL_HEBREW_ENTRY], "languages": ["he"]}
    assert hash_entry_exclusion_reason(partial_hebrew_only, sources["hash_nli_any_use"]) == "partial_hebrew_extent"
    unverified = json.loads(json.dumps(entries["loc__2018757701__p0005"]))
    unverified["rights"]["verification_status"] = "unverified"
    assert hash_entry_exclusion_reason(unverified, sources["hash_public_domain"]) == "rights_not_primary_page_checked"


def test_hash_discovery_emits_stable_ids_and_governance_metadata() -> None:
    bundle, sources = _sources()
    importer = HashImporter()
    options = StageOptions()
    discovered = {
        source_id: importer.discover_candidates(sources[source_id], bundle, options) for source_id in HASH_SOURCE_IDS
    }
    assert [candidate.candidate_id for candidate in discovered["hash_nli_any_use"]] == [
        "hash_nli_any_use:nli__nnl_archive_al997009912248505171__p0003"
    ]
    assert [candidate.candidate_id for candidate in discovered["hash_public_domain"]] == [
        "hash_public_domain:commons__blazer_letter_grayevsky_1905__p0001",
        "hash_public_domain:loc__2018757701__p0005",
    ]
    enriched = importer.fetch_candidate_metadata(sources["hash_public_domain"], bundle, discovered["hash_public_domain"], options)
    letter = enriched[0]
    assert letter.raw_rights_text == "PDM-1.0"
    assert letter.source_url.startswith("https://")
    assert letter.asset_references[0].reference == "assets/commons__blazer_letter_grayevsky_1905__p0001.jpg"
    assert letter.metadata["period"] == "historical"
    assert letter.metadata["source_group_id"] == "hash:commons__blazer_letter_grayevsky_1905"
    assert letter.metadata["writer_group_id"] == "Yitzchak Blazer"
    assert letter.metadata["upstream_commit"] == "3cb163a97bb1d1c75be938de282b1092929a684c"
    assert enriched[1].metadata["writer_group_id"] == "unknown:loc__2018757701"
    assert all("transcription" not in candidate.raw_metadata["entry"] for candidate in discovered["hash_public_domain"])


def test_hash_acquire_rejects_checksum_mismatch(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "hash_public_domain")
    importer = HashImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    Path(enriched[0].asset_references[0].resolved_path or "").write_bytes(b"tampered")
    items = [
        ItemRecord(
            **record.model_dump(),
            item_id=record.candidate_id,
            normalized_license="PDM-1.0",
            rights_classification="open",
            eligibility="review_required",
            eligibility_reason="hash fixture",
        )
        for record in enriched[:1]
    ]
    with pytest.raises(StageExecutionError, match="checksum mismatch"):
        importer.acquire_items(source, bundle, items, tmp_path / "acquire", options)


def test_hash_source_health_reports_missing_asset_and_exclusions(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    (config_root / "hash_snapshot" / "assets" / "loc__2018757701__p0005.jpg").unlink()
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "hash_public_domain")
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert candidate_count == 2
    assert asset_count == 1
    assert any(check["name"] == "hash_entry_asset" and check["status"] == "error" for check in checks)
    exclusions = next(check for check in checks if check["name"] == "hash_entry_exclusions")
    assert exclusions["actual"] == {"license_not_in_source_lane": 3}
    assert all(not str(check.get("path", "")).startswith("/") for check in checks)
