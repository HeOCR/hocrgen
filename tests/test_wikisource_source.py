from __future__ import annotations

import copy
import hashlib
import json
import shutil
import unicodedata
from pathlib import Path

import pytest
import yaml

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.wikisource import (
    WikisourceProofreadImporter,
    index_exclusion_reason,
    index_exclusion_reasons,
    load_wikisource_snapshot,
    page_attestation,
    page_exclusion_reason,
    page_plain_text,
    scan_source_origin,
    write_wikisource_reference_pool,
)
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord, ItemRecord
from hocrgen.parsers.wikitext import UnsupportedWikitextError, wikitext_to_plain_text
from hocrgen.source_ops import _inspect_source

SOURCE_ID = "wikisource_he_proofread"
SNAPSHOT_ROOT = package_root() / "data" / "wikisource" / "snapshot"
SELIHOT = "selihot_baer_1885__p0034"
BOSTENAY = "bostenay_lehmann_1872__p0047"
HYMAN = "hyman_toldoth_1910_vol1__p0041"


def _bundle_and_source():
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    return bundle, source


def _snapshot():
    _, indexes, pages = load_wikisource_snapshot(SNAPSHOT_ROOT)
    return indexes, {page["source_item_id"]: page for page in pages}


def _copy_snapshot_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(SNAPSHOT_ROOT, config_root / "wikisource_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == SOURCE_ID:
            source["settings"]["extra"]["wikisource_snapshot_root"] = "wikisource_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return config_root


# --- source policy -----------------------------------------------------------------------------------------


def test_wikisource_source_is_review_only_sharealike_and_outside_the_public_profile() -> None:
    bundle, source = _bundle_and_source()
    assert source.fetcher == "wikisource_proofread"
    assert source.status.value == "review_only"
    assert source.default_public_release is False
    assert source.allowed_content_types == ["printed_historical"]
    assert source.normalized_license == "CC-BY-SA-4.0"
    assert source.rights_classification.value == "sharealike"
    assert source.rights_strategy.values == ["CC-BY-SA-4.0"]
    assert SOURCE_ID not in bundle.profiles["profile_open_v1"].include_sources
    assert SOURCE_ID in bundle.profiles["profile_review_v1"].include_sources
    # Public-domain historical print: no privacy-review gate (maintainer decision 2026-11-06).
    assert bundle.privacy_rules.source_defaults[SOURCE_ID].value == "clear"
    assert not [rule.id for rule in bundle.privacy_rules.rules if SOURCE_ID in rule.applies_to_sources]


# --- Index admission ---------------------------------------------------------------------------------------


def test_index_gate_admits_only_files_with_work_and_scan_evidence() -> None:
    indexes, _ = _snapshot()
    admitted = sorted(key for key, index in indexes.items() if not index_exclusion_reasons(index))
    assert admitted == ["bostenay_lehmann_1872", "hyman_toldoth_1910_vol1", "selihot_baer_1885"]
    assert index_exclusion_reason(indexes["birnbaum_siddur_1949"]) == "excluded_birnbaum_work"
    assert index_exclusion_reason(indexes["birnbaum_haggadah_1953"]) == "excluded_birnbaum_work"
    assert "creator_died_after_1955" in index_exclusion_reasons(indexes["birnbaum_siddur_1949"])
    assert index_exclusion_reasons(indexes["siddur_torah_ohr_1940"]) == ["pd_us_only_licence", "google_digitization_unchecked"]
    assert index_exclusion_reasons(indexes["korfu_siddur_1885"]) == [
        "creator_death_year_missing",
        "scan_provenance_unrecorded",
        "google_digitization_unchecked",
    ]


def test_birnbaum_exclusion_holds_even_with_otherwise_clean_evidence() -> None:
    indexes, _ = _snapshot()
    birnbaum = copy.deepcopy(indexes["birnbaum_siddur_1949"])
    birnbaum["commons_file"]["licence_templates"] = ["PD-scan|PD-old-70"]
    birnbaum["work"]["creators"][0]["death_year"] = 1900
    birnbaum["scan_rights"]["digitized_by_google"] = False
    assert index_exclusion_reasons(birnbaum) == ["excluded_birnbaum_work"]


def test_google_digitized_scans_are_held_pending_a_maintainer_decision() -> None:
    indexes, _ = _snapshot()
    stamped = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    stamped["scan_rights"]["digitized_by_google"] = True
    assert index_exclusion_reasons(stamped) == ["google_digitized_scan_pending"]
    google_source = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    google_source["commons_file"]["provenance_text"] = "Missing pages added from Google Books."
    assert index_exclusion_reasons(google_source) == ["google_digitized_scan_pending"]
    unchecked = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    del unchecked["scan_rights"]["digitized_by_google"]
    assert index_exclusion_reasons(unchecked) == ["google_digitization_unchecked"]
    for key in ("selihot_baer_1885", "bostenay_lehmann_1872", "hyman_toldoth_1910_vol1"):
        assert indexes[key]["scan_rights"]["digitized_by_google"] is False


def test_hebrewbooks_scans_are_admitted_on_the_same_rights_check() -> None:
    # Maintainer decision 3 (accepted 2026-11-06): HebrewBooks origin is provenance, not an exclusion.
    indexes, _ = _snapshot()
    hyman = indexes["hyman_toldoth_1910_vol1"]
    assert scan_source_origin(hyman) == "hebrewbooks"
    assert index_exclusion_reasons(hyman) == []
    assert scan_source_origin(indexes["selihot_baer_1885"]) == "open_siddur_project"
    assert scan_source_origin(indexes["bostenay_lehmann_1872"]) == "national_library_of_israel"
    assert scan_source_origin(indexes["korfu_siddur_1885"]) == "unrecorded"


def test_a_commons_template_alone_is_not_enough() -> None:
    indexes, _ = _snapshot()
    template_only = copy.deepcopy(indexes["selihot_baer_1885"])
    template_only["work_rights"] = {}
    template_only["scan_rights"] = {}
    assert index_exclusion_reasons(template_only) == ["work_rights_basis_unsupported", "scan_rights_basis_unsupported"]
    no_template = copy.deepcopy(indexes["selihot_baer_1885"])
    no_template["commons_file"]["licence_templates"] = []
    assert index_exclusion_reasons(no_template) == ["no_licence_template"]
    mixed_us = copy.deepcopy(indexes["selihot_baer_1885"])
    mixed_us["commons_file"]["licence_templates"] = ["PD-US", "PD-100"]
    assert index_exclusion_reasons(mixed_us) == []
    unpinned = copy.deepcopy(indexes["selihot_baer_1885"])
    unpinned["commons_file"]["sha1"] = None
    assert index_exclusion_reasons(unpinned) == ["commons_file_unpinned"]


@pytest.mark.parametrize(
    ("work", "work_rights", "expected"),
    [
        ({"creators": [{"name": "A", "role": "author", "death_year": 1955, "death_year_evidence_url": "u"}]}, "author_died_by_1955", []),
        ({"creators": [{"name": "A", "role": "author", "death_year": 1956, "death_year_evidence_url": "u"}]}, "author_died_by_1955", ["creator_died_after_1955"]),
        ({"creators": [{"name": "A", "role": "author", "death_year": 1900, "death_year_evidence_url": None}]}, "author_died_by_1955", ["creator_death_year_missing"]),
        ({"creators": []}, "author_died_by_1955", ["creators_missing"]),
        ({"created_year": 1975, "state_body": "Knesset", "creators": []}, "state_work_by_1975", []),
        ({"created_year": 1976, "state_body": "Knesset", "creators": []}, "state_work_by_1975", ["state_work_after_1975"]),
        ({"created_year": 1960, "creators": []}, "state_work_by_1975", ["state_work_evidence_missing"]),
        ({"published_year": 1955, "creators": [{"name": "?", "role": "anonymous"}]}, "anonymous_published_by_1955", []),
        ({"published_year": 1956, "creators": []}, "anonymous_published_by_1955", ["anonymous_work_after_1955"]),
        ({"published_year": 1900, "creators": [{"name": "A", "role": "author"}]}, "anonymous_published_by_1955", ["named_creator_on_anonymous_basis"]),
    ],
)
def test_work_rights_follow_israeli_terms(work: dict, work_rights: str, expected: list[str]) -> None:
    indexes, _ = _snapshot()
    index = copy.deepcopy(indexes["selihot_baer_1885"])
    index["work"] = {"title": "t", **work}
    index["work_rights"] = {"basis": work_rights, "evidence": "recorded"}
    assert index_exclusion_reasons(index) == expected


def test_scan_rights_need_open_licence_or_recorded_reproduction_provenance() -> None:
    indexes, _ = _snapshot()
    nc_scan = copy.deepcopy(indexes["selihot_baer_1885"])
    nc_scan["scan_rights"]["licence"] = "CC-BY-NC-4.0"
    assert index_exclusion_reasons(nc_scan) == ["scan_licence_not_open"]
    unsourced = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    unsourced["scan_rights"]["scan_source"] = None
    assert index_exclusion_reasons(unsourced) == ["scan_provenance_unrecorded"]
    unevidenced = copy.deepcopy(indexes["selihot_baer_1885"])
    unevidenced["scan_rights"]["scan_source"] = {"name": "Open Siddur Project", "evidence": ""}
    assert index_exclusion_reasons(unevidenced) == ["scan_provenance_unrecorded"]
    # A bibliographic Commons source field is not scan provenance: Korfu's names the book, not a scanner.
    korfu = copy.deepcopy(indexes["korfu_siddur_1885"])
    assert korfu["commons_file"]["source_field"]
    korfu["work"]["creators"][0].update({"death_year": 1900, "death_year_evidence_url": "u"})
    korfu["scan_rights"]["digitized_by_google"] = False
    assert index_exclusion_reasons(korfu) == ["scan_provenance_unrecorded"]
    no_evidence = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    no_evidence["scan_rights"]["evidence"] = " "
    assert index_exclusion_reasons(no_evidence) == ["scan_rights_evidence_missing"]


# --- page admission and attestation ------------------------------------------------------------------------


def test_page_gate_skips_low_quality_and_unattributed_quality() -> None:
    indexes, pages = _snapshot()
    low = copy.deepcopy(pages[HYMAN])
    low["quality"] = 1
    assert page_exclusion_reason(low, indexes, SNAPSHOT_ROOT) == "quality_not_proofread"
    bot = copy.deepcopy(pages[SELIHOT])
    bot["quality_history"][-1]["user_groups"] = ["bot"]
    assert page_exclusion_reason(bot, indexes, SNAPSHOT_ROOT) == "quality_editor_not_named_human"
    named_bot = copy.deepcopy(pages[HYMAN])
    named_bot["quality_history"][-1].update({"user": "Wikisource-bot", "pagequality_user_attribute": "Wikisource-bot"})
    assert page_exclusion_reason(named_bot, indexes, SNAPSHOT_ROOT) == "quality_editor_not_named_human"
    anonymous = copy.deepcopy(pages[HYMAN])
    anonymous["quality_history"][-1]["user_id"] = 0
    assert page_exclusion_reason(anonymous, indexes, SNAPSHOT_ROOT) == "quality_editor_not_named_human"
    mismatch = copy.deepcopy(pages[SELIHOT])
    mismatch["quality_history"][-1]["pagequality_user_attribute"] = "Someone"
    assert page_exclusion_reason(mismatch, indexes, SNAPSHOT_ROOT) == "quality_attribute_mismatch"
    self_validated = copy.deepcopy(pages[SELIHOT])
    proofreader = next(entry for entry in self_validated["quality_history"] if entry["level"] == 3)
    proofreader.update({"user": "Nahum", "user_id": 68, "pagequality_user_attribute": "Nahum"})
    assert page_exclusion_reason(self_validated, indexes, SNAPSHOT_ROOT) == "validator_is_proofreader"
    same_account = copy.deepcopy(pages[SELIHOT])
    proofreader = next(entry for entry in same_account["quality_history"] if entry["level"] == 3)
    proofreader["user_id"] = same_account["quality_history"][-1]["user_id"]
    assert page_exclusion_reason(same_account, indexes, SNAPSHOT_ROOT) == "validator_is_proofreader"
    no_proofreader = copy.deepcopy(pages[SELIHOT])
    no_proofreader["quality_history"] = [no_proofreader["quality_history"][-1]]
    assert page_exclusion_reason(no_proofreader, indexes, SNAPSHOT_ROOT) == "proofreader_missing"
    partial = copy.deepcopy(pages[HYMAN])
    partial["transcription_coverage"] = "commentary_only"
    assert page_exclusion_reason(partial, indexes, SNAPSHOT_ROOT) == "partial_page_transcription"
    unrecorded = copy.deepcopy(pages[HYMAN])
    del unrecorded["transcription_coverage"]
    assert page_exclusion_reason(unrecorded, indexes, SNAPSHOT_ROOT) == "transcription_coverage_unrecorded"
    orphan = copy.deepcopy(pages[SELIHOT])
    orphan["index_key"] = "korfu_siddur_1885"
    assert page_exclusion_reason(orphan, indexes, SNAPSHOT_ROOT) == "index_not_admitted"


def test_page_gate_rejects_drifted_or_unsupported_wikitext(tmp_path: Path) -> None:
    indexes, pages = _snapshot()
    root = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_ROOT, root)
    page = pages[SELIHOT]
    wikitext_path = root / page["wikitext_path"]
    original = wikitext_path.read_text(encoding="utf-8")
    wikitext_path.write_text(original + "x", encoding="utf-8")
    assert page_exclusion_reason(page, indexes, root) == "wikitext_checksum_mismatch"
    unsupported = original.replace("{{סוף}}", "{{תבנית לא מוכרת}}")
    wikitext_path.write_text(unsupported, encoding="utf-8")
    drifted = {**page, "wikitext_sha256": hashlib.sha256(unsupported.encode("utf-8")).hexdigest()}
    assert page_exclusion_reason(drifted, indexes, root) == "wikitext_unsupported_markup"
    wikitext_path.write_text(original, encoding="utf-8")
    text_path = root / page["text_path"]
    pinned_text = text_path.read_text(encoding="utf-8")
    text_path.write_text(pinned_text.rstrip("\n"), encoding="utf-8")
    assert page_exclusion_reason(page, indexes, root) == "page_text_file_mismatch"
    text_path.unlink()
    assert page_exclusion_reason(page, indexes, root) == "page_text_file_missing"
    text_path.write_text(pinned_text, encoding="utf-8")
    assert page_exclusion_reason(page, indexes, root) is None
    downgraded = original.replace('level="4"', 'level="3"')
    wikitext_path.write_text(downgraded, encoding="utf-8")
    tagged = {**page, "wikitext_sha256": hashlib.sha256(downgraded.encode("utf-8")).hexdigest()}
    assert page_exclusion_reason(tagged, indexes, root) == "quality_tag_mismatch"


def test_attestation_records_named_editors_and_adjudication_eligibility() -> None:
    _, pages = _snapshot()
    selihot = page_attestation(pages[SELIHOT])
    assert selihot["human_attestation"] == "two_editor_validated"
    assert selihot["proofreader"]["user"] == "Neriah"
    assert selihot["validator"]["user"] == "Nahum"
    assert selihot["adjudication_eligible"] is True
    # The validator fixed a missing space 14 seconds after validating: the pinned text is not the validated one.
    bostenay = page_attestation(pages[BOSTENAY])
    assert bostenay["validator"]["user"] == "Nahum"
    assert bostenay["proofreader"]["user"] == "Roxette5"
    assert bostenay["adjudication_eligible"] is False
    assert bostenay["adjudication_ineligible_reason"] == "text_changed_after_validation"
    assert [edit["revision_id"] for edit in bostenay["text_changing_edits_after_quality_set"]] == [821196]
    hyman = page_attestation(pages[HYMAN])
    assert hyman["human_attestation"] == "single_reviewer_proofread"
    assert hyman["proofreader"]["user"] == "עמד"
    assert hyman["validator"] is None
    assert hyman["adjudication_eligible"] is False


# --- normalisation -----------------------------------------------------------------------------------------


def test_pinned_page_texts_are_reproduced_from_pinned_wikitext() -> None:
    _, pages = _snapshot()
    for page in pages.values():
        wikitext = (SNAPSHOT_ROOT / page["wikitext_path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(wikitext.encode("utf-8")).hexdigest() == page["wikitext_sha256"]
        text = page_plain_text(page, SNAPSHOT_ROOT)
        assert (SNAPSHOT_ROOT / page["text_path"]).read_text(encoding="utf-8") == text + "\n"
        assert unicodedata.is_normalized("NFC", text)
        assert "<" not in text and "{{" not in text and "[[" not in text
        assert not set(text) & set("‎‏‪‫‬‭‮")


def test_wikitext_normalisation_rules() -> None:
    wikitext = (
        '<noinclude><pagequality level="4" user="X" />{{טקסט מנוקד}}</noinclude>'
        '<section begin="a"/><קטע התחלה=ב/>== כותרת ==\n'
        "שורה ראשונה\nהמשך הפסקה '''מודגש''' [[ברכות לט ב|ברכות לט:]] [[דף]]"
        " {{קיצור|ר\"פ|רב פפא}} {{ק|קטן {{ק|וכו'}}}} א{{!}}ב [[קטגוריה:x]][[File:y.png|thumb]]\n\n"
        "‫פסקה‬ שנייה{{ש}}שורה&nbsp;חדשה <!-- הערה -->\n"
        "{{מרכז|ממורכז}}שאר\n"
        "שְִּׁ<section end=\"a\"/><noinclude>{{סוף}}<references/></noinclude>"
    )
    assert wikitext_to_plain_text(wikitext) == (
        "כותרת\n\n"
        "שורה ראשונה המשך הפסקה מודגש ברכות לט: דף ר\"פ קטן וכו' א|ב\n\n"
        "פסקה שנייה\nשורה חדשה\n\n"
        "ממורכז\n\n"
        "שאר " + unicodedata.normalize("NFC", "שְִּׁ")
    )


@pytest.mark.parametrize(
    "wikitext",
    [
        "טקסט{{תבנית חדשה|א}}",
        "טקסט<ref>הערה</ref>",
        "{|\n| תא\n|}",
        "{{#if:x|y}}",
        "טקסט {{ק|לא סגור",
        "<noinclude>חסר סוף",
        "<nowiki>'''א'''</nowiki>",
        "טקסט<nowiki/>המשך",
        "<pre>א</pre>",
        "{{ק|1=א}}",
        "{{מרכז| 2 =א|ב}}",
    ],
)
def test_wikitext_outside_the_closed_set_is_rejected(wikitext: str) -> None:
    with pytest.raises(UnsupportedWikitextError):
        wikitext_to_plain_text(wikitext)


# --- adapter -----------------------------------------------------------------------------------------------


def test_discovery_emits_stable_ids_and_provenance_metadata() -> None:
    bundle, source = _bundle_and_source()
    importer = WikisourceProofreadImporter()
    options = StageOptions()
    candidates = importer.discover_candidates(source, bundle, options)
    assert [candidate.candidate_id for candidate in candidates] == [
        f"{SOURCE_ID}:{BOSTENAY}",
        f"{SOURCE_ID}:{HYMAN}",
        f"{SOURCE_ID}:{SELIHOT}",
    ]
    assert [c.candidate_id for c in importer.discover_candidates(source, bundle, StageOptions(max_items=1))] == [f"{SOURCE_ID}:{BOSTENAY}"]
    enriched = {record.source_item_id: record for record in importer.fetch_candidate_metadata(source, bundle, candidates, options)}
    selihot = enriched[SELIHOT]
    assert selihot.raw_rights_text == "CC-BY-SA-4.0"
    assert selihot.source_url == (
        "https://he.wikisource.org/w/index.php?title=%D7%A2%D7%9E%D7%95%D7%93:The_Seli%E1%B8%A5ot_for_the_Entire_Year.pdf/34&oldid=2801799"
    )
    metadata = selihot.metadata
    assert metadata["wikisource_revision_id"] == 2801799
    assert metadata["wikisource_quality_level"] == 4
    assert metadata["wikisource_quality_label"] == "validated"
    assert metadata["validator"]["user"] == "Nahum"
    assert metadata["adjudication_eligible"] is True
    assert metadata["scan_commons_file_sha1"] == "962def078054dac4adb630f76fc78db982d82617"
    assert metadata["scan_rights_basis"] == "explicit_open_licence"
    assert metadata["scan_licence"] == "CC0-1.0"
    assert metadata["source_group_id"] == "wikisource:selihot_baer_1885"
    assert metadata["text_normalization"] == "wikisource_plain_text.v1"
    assert enriched[HYMAN].metadata["scan_source_origin"] == "hebrewbooks"
    assert enriched[HYMAN].metadata["wikisource_quality_label"] == "proofread"
    for record in enriched.values():
        assert record.asset_references[0].reference.startswith("assets/")
        for key, value in record.metadata.items():
            assert not (isinstance(value, str) and value.startswith("/")), key


def test_enrichment_accepts_anonymous_creators_without_death_year(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    indexes_path = config_root / "wikisource_snapshot" / "indexes.json"
    payload = json.loads(indexes_path.read_text(encoding="utf-8"))
    hyman = next(index for index in payload["indexes"] if index["index_key"] == "hyman_toldoth_1910_vol1")
    hyman["work"] = {"title": "t", "published_year": 1910, "creators": [{"name": "פלוני", "role": "pseudonymous"}]}
    hyman["work_rights"] = {"basis": "anonymous_published_by_1955", "evidence": "recorded"}
    indexes_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    importer = WikisourceProofreadImporter()
    candidates = [c for c in importer.discover_candidates(source, bundle, StageOptions()) if c.source_item_id == HYMAN]
    [record] = importer.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
    assert record.metadata["work_creators"] == [{"name": "פלוני", "role": "pseudonymous", "death_year": None}]


def test_acquire_rejects_asset_checksum_mismatch(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle(_copy_snapshot_config(tmp_path))
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    importer = WikisourceProofreadImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    items = [
        ItemRecord(
            **record.model_dump(),
            item_id=record.candidate_id,
            normalized_license="CC-BY-SA-4.0",
            rights_classification="sharealike",
            eligibility="review_required",
            eligibility_reason="wikisource fixture",
        )
        for record in enriched
    ]
    acquired = importer.acquire_items(source, bundle, items, tmp_path / "acquire", options)
    assert [asset.sha256 for item in acquired for asset in item.acquired_assets] == [
        item.metadata["expected_asset_sha256"] for item in items
    ]
    Path(enriched[0].asset_references[0].resolved_path or "").write_bytes(b"tampered")
    with pytest.raises(StageExecutionError, match="checksum mismatch"):
        importer.acquire_items(source, bundle, items[:1], tmp_path / "acquire2", options)


def test_source_health_reports_exclusions_missing_assets_and_text_drift(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (3, 3)
    assert all(check["status"] == "ok" for check in checks)
    index_exclusions = next(check for check in checks if check["name"] == "wikisource_index_exclusions")
    assert index_exclusions["actual"] == {
        "creator_death_year_missing": 1,
        "creator_died_after_1955": 2,
        "excluded_birnbaum_work": 2,
        "google_digitization_unchecked": 4,
        "pd_us_only_licence": 3,
        "scan_provenance_unrecorded": 1,
    }

    config_root = _copy_snapshot_config(tmp_path)
    snapshot = config_root / "wikisource_snapshot"
    (snapshot / "assets" / f"{HYMAN}.jpg").unlink()
    (snapshot / "wikitext" / f"{SELIHOT}.wikitext.txt").write_text("drift", encoding="utf-8")
    (snapshot / "text" / f"{BOSTENAY}.txt").unlink()
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (1, 0)
    assert any(check["name"] == "wikisource_page_asset" and check["status"] == "error" for check in checks)
    drift = {check["record_id"]: check["message"] for check in checks if check["name"] == "wikisource_page_text"}
    assert drift == {SELIHOT: "wikitext_checksum_mismatch", BOSTENAY: "page_text_file_missing"}
    assert next(check for check in checks if check["name"] == "wikisource_page_exclusions")["actual"] == {
        "page_text_file_missing": 1,
        "wikitext_checksum_mismatch": 1,
    }
    assert all(not str(check.get("path", "")).startswith("/") for check in checks)


def test_review_profile_routes_pages_to_review_and_open_profile_ignores_them(tmp_path: Path, capsys) -> None:
    assert main(["build-release", "--profile", "profile_review_v1", "--dry-run", "--workdir", str(tmp_path / "review")]) == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    queue = json.loads((run_dir / "review" / "queue.json").read_text(encoding="utf-8"))
    queued = {item["item_id"]: item for item in queue["items"] if item["source_id"] == SOURCE_ID}
    assert sorted(queued) == [f"{SOURCE_ID}:{BOSTENAY}", f"{SOURCE_ID}:{HYMAN}", f"{SOURCE_ID}:{SELIHOT}"]
    assert all("policy:review_only_source" in item["review_reasons"] for item in queued.values())
    classified = json.loads((run_dir / "classify" / "classified_items.json").read_text(encoding="utf-8"))
    assert {item["content_class"] for item in classified["items"] if item["source_id"] == SOURCE_ID} == {"printed"}

    assert main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "open")]) == 0
    open_run = Path(json.loads(capsys.readouterr().out)["run_dir"])
    assert SOURCE_ID not in (open_run / "discover" / "candidates.json").read_text(encoding="utf-8")


# --- operator-only F2 reference conversion -----------------------------------------------------------------


def test_reference_pool_writes_skip_counts_when_nothing_is_eligible(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    pages_path = config_root / "wikisource_snapshot" / "pages.jsonl"
    pages = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    kept = [page for page in pages if page["source_item_id"] != SELIHOT]
    pages_path.write_text("".join(json.dumps(page) + "\n" for page in kept), encoding="utf-8")
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    out_dir = tmp_path / "new" / "pool"
    manifest = write_wikisource_reference_pool(source, bundle, out_dir)
    assert manifest["items"] == []
    assert json.loads((out_dir / "reference_pool.json").read_text(encoding="utf-8"))["skipped"] == {
        "quality_3_single_reviewer": 1,
        "text_changed_after_validation": 1,
    }


def test_reference_pool_converts_only_adjudication_eligible_validated_pages(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    benchmark_manifest = package_root() / "data" / "benchmark" / "benchmark_v1" / "reference_manifest.json"
    before = benchmark_manifest.read_bytes()
    manifest = write_wikisource_reference_pool(source, bundle, tmp_path / "pool")
    assert benchmark_manifest.read_bytes() == before
    assert [entry["item_id"] for entry in manifest["items"]] == [f"{SOURCE_ID}:{SELIHOT}"]
    assert manifest["skipped"] == {"quality_3_single_reviewer": 1, "text_changed_after_validation": 1}
    assert manifest["text_license"] == "CC-BY-SA-4.0"
    entry = manifest["items"][0]
    payload = (tmp_path / "pool" / entry["path"]).read_text(encoding="utf-8")
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == entry["sha256"]
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(payload)
    assert record.review.status == "reviewed"
    assert record.review.adjudicator is None
    assert record.review.reviewers == ["wikisource:Neriah", "wikisource:Nahum"]
    _, pages = _snapshot()
    assert record.pages[0].text == page_plain_text(pages[SELIHOT], SNAPSHOT_ROOT)
    assert "\n".join(line.text for line in record.lines) == record.pages[0].text.replace("\n\n", "\n")
