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
    crop_asset_problems,
    crop_geometry_valid,
    crop_image,
    crop_mask_fill,
    crop_pixel_box,
    index_exclusion_reason,
    index_exclusion_reasons,
    load_wikisource_snapshot,
    page_attestation,
    digitized_by_google,
    page_exclusion_reason,
    page_exclusion_reasons,
    page_needs_crop,
    page_plain_text,
    pagequality_attribute_names_editor,
    scan_source_origin,
    write_wikisource_reference_pool,
)
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord, ItemRecord
from hocrgen.parsers.wikitext import UnsupportedWikitextError, convert_wikitext, section_text, transcluded_titles, wikitext_to_plain_text
from hocrgen.source_ops import _inspect_source

SOURCE_ID = "wikisource_he_proofread"
SNAPSHOT_ROOT = package_root() / "data" / "wikisource" / "snapshot"
SELIHOT = "selihot_baer_1885__p0034"
BOSTENAY = "bostenay_lehmann_1872__p0047"
HYMAN = "hyman_toldoth_1910_vol1__p0041"
# F8b4: partial pages paired with their crops (the notes section, and the Yiddish columns, are not transcribed)
BUBER = "buber_tanhuma_1885__p0233"
SIPPUREI = "sippurei_maasiyot_1902__p0011"


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
    assert admitted == ["bostenay_lehmann_1872", "buber_tanhuma_1885", "hyman_toldoth_1910_vol1", "selihot_baer_1885", "sippurei_maasiyot_1902"]
    assert index_exclusion_reason(indexes["birnbaum_siddur_1949"]) == "excluded_birnbaum_work"
    assert index_exclusion_reason(indexes["birnbaum_haggadah_1953"]) == "excluded_birnbaum_work"
    assert "creator_died_after_1955" in index_exclusion_reasons(indexes["birnbaum_siddur_1949"])
    # Decision 10: the PD-US-only tag, an unrecorded scan source and an unchecked Google stamp no longer reject.
    assert index_exclusion_reasons(indexes["siddur_torah_ohr_1940"]) == ["index_language_unrecorded"]
    assert index_exclusion_reasons(indexes["korfu_siddur_1885"]) == ["creator_death_year_missing", "index_language_unrecorded"]


def test_index_language_must_be_recorded_as_hebrew() -> None:
    # Team-lead decision (F8b3): the source is Hebrew. An English Index such as "She" (a Hebrew translation typed
    # over an English scan) and an Index with no recorded language are both rejected.
    indexes, _ = _snapshot()
    for key in ("selihot_baer_1885", "bostenay_lehmann_1872", "hyman_toldoth_1910_vol1"):
        assert indexes[key]["work"]["language"] == "he"
        assert indexes[key]["work"]["language_evidence"]
    english = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    english["work"]["language"] = "en"
    assert index_exclusion_reasons(english) == ["index_language_not_hebrew"]
    for missing in (None, "", "  "):
        unrecorded = copy.deepcopy(indexes["bostenay_lehmann_1872"])
        unrecorded["work"]["language"] = missing
        assert index_exclusion_reasons(unrecorded) == ["index_language_unrecorded"]
    del unrecorded["work"]["language"]
    assert index_exclusion_reasons(unrecorded) == ["index_language_unrecorded"]


def test_birnbaum_exclusion_holds_even_with_otherwise_clean_evidence() -> None:
    indexes, _ = _snapshot()
    birnbaum = copy.deepcopy(indexes["birnbaum_siddur_1949"])
    birnbaum["commons_file"]["licence_templates"] = ["PD-scan|PD-old-70"]
    birnbaum["work"]["creators"][0]["death_year"] = 1900
    birnbaum["scan_rights"]["digitized_by_google"] = False
    assert index_exclusion_reasons(birnbaum) == ["excluded_birnbaum_work"]


def test_google_digitized_scans_are_admitted_and_recorded_as_provenance() -> None:
    # Maintainer decision 9 (2026-11-06): Google-digitized scans pass the same per-file check.
    indexes, _ = _snapshot()
    stamped = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    stamped["scan_rights"]["digitized_by_google"] = True
    assert index_exclusion_reasons(stamped) == []
    assert digitized_by_google(stamped) is True
    google_source = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    google_source["commons_file"]["provenance_text"] = "Missing pages added from Google Books."
    assert index_exclusion_reasons(google_source) == []
    assert digitized_by_google(google_source) is True
    unchecked = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    del unchecked["scan_rights"]["digitized_by_google"]
    assert index_exclusion_reasons(unchecked) == []
    assert digitized_by_google(unchecked) is None
    for key in ("selihot_baer_1885", "bostenay_lehmann_1872", "hyman_toldoth_1910_vol1"):
        assert digitized_by_google(indexes[key]) is False


def test_hebrewbooks_scans_are_admitted_on_the_same_rights_check() -> None:
    # Maintainer decision 3 (accepted 2026-11-06): HebrewBooks origin is provenance, not an exclusion.
    indexes, _ = _snapshot()
    hyman = indexes["hyman_toldoth_1910_vol1"]
    assert scan_source_origin(hyman) == "hebrewbooks"
    assert index_exclusion_reasons(hyman) == []
    assert scan_source_origin(indexes["selihot_baer_1885"]) == "open_siddur_project"
    assert scan_source_origin(indexes["bostenay_lehmann_1872"]) == "national_library_of_israel"
    assert scan_source_origin(indexes["korfu_siddur_1885"]) == "unrecorded"


def test_the_commons_tag_never_decides_the_works_status() -> None:
    # Decision 10: a template alone admits nothing, and a missing or PD-US-only template rejects nothing.
    indexes, _ = _snapshot()
    template_only = copy.deepcopy(indexes["selihot_baer_1885"])
    template_only["work_rights"] = {}
    template_only["scan_rights"] = {}
    assert index_exclusion_reasons(template_only) == ["work_rights_basis_unsupported", "scan_rights_basis_unsupported"]
    for templates in ([], ["PD-US-not renewed"], ["PD-US", "PD-100"]):
        tagged = copy.deepcopy(indexes["selihot_baer_1885"])
        tagged["commons_file"]["licence_templates"] = templates
        assert index_exclusion_reasons(tagged) == []
    protected = copy.deepcopy(indexes["selihot_baer_1885"])
    protected["work"]["creators"][0]["death_year"] = 1988
    assert index_exclusion_reasons(protected) == ["creator_died_after_1955"]
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
        # Decision 10: published on or before 1855, presumed PD in Israel without a death year.
        ({"published_year": 1855, "published_year_evidence": "e", "creators": [{"name": "A", "role": "author", "death_year": None}]}, "presumed_pd_by_publication_age", []),
        ({"published_year": 1700, "published_year_evidence": "e", "creators": []}, "presumed_pd_by_publication_age", []),
        ({"published_year": 1856, "published_year_evidence": "e", "creators": []}, "presumed_pd_by_publication_age", ["published_after_1855"]),
        ({"published_year": 1850, "creators": []}, "presumed_pd_by_publication_age", ["publication_year_missing"]),
        ({"published_year": 1850, "published_year_evidence": "e", "creators": [{"name": "A", "role": "translator", "death_year": 1960}]}, "presumed_pd_by_publication_age", ["creator_died_after_1955"]),
    ],
)
def test_work_rights_follow_israeli_terms(work: dict, work_rights: str, expected: list[str]) -> None:
    indexes, _ = _snapshot()
    index = copy.deepcopy(indexes["selihot_baer_1885"])
    index["work"] = {"title": "t", "language": "he", **work}
    index["work_rights"] = {"basis": work_rights, "evidence": "recorded"}
    assert index_exclusion_reasons(index) == expected


def test_a_faithful_reproduction_needs_no_recorded_scan_source() -> None:
    # Decision 10: the scan source is provenance, recorded where known; it no longer gates.
    indexes, _ = _snapshot()
    nc_scan = copy.deepcopy(indexes["selihot_baer_1885"])
    nc_scan["scan_rights"]["licence"] = "CC-BY-NC-4.0"
    assert index_exclusion_reasons(nc_scan) == ["scan_licence_not_open"]
    unsourced = copy.deepcopy(indexes["bostenay_lehmann_1872"])
    unsourced["scan_rights"]["scan_source"] = None
    assert index_exclusion_reasons(unsourced) == []
    korfu = copy.deepcopy(indexes["korfu_siddur_1885"])
    korfu["work"]["creators"][0].update({"death_year": 1900, "death_year_evidence_url": "u"})
    korfu["work"]["language"] = "he"
    assert index_exclusion_reasons(korfu) == []
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
    # F8b5: the attribute keeps the name at the time of the edit; a recorded rename of the account after the edit matches it.
    renamed = copy.deepcopy(mismatch)
    entry = renamed["quality_history"][-1]
    rename = {"old": "Someone", "new": entry["user"], "log_id": 59156686, "timestamp": "2099-01-01T00:00:00Z", "log_type": "gblrename", "wiki": "https://meta.wikimedia.org"}
    entry["user_renames"] = [rename]
    assert "quality_attribute_mismatch" not in page_exclusion_reasons(renamed, indexes, SNAPSHOT_ROOT)
    entry["user_renames"] = [{**rename, "timestamp": "2000-01-01T00:00:00Z"}]  # renamed before the edit: someone else's name
    assert page_exclusion_reason(renamed, indexes, SNAPSHOT_ROOT) == "quality_attribute_mismatch"
    entry["user_renames"] = [{**rename, "new": "Another"}]  # another account's rename
    assert page_exclusion_reason(renamed, indexes, SNAPSHOT_ROOT) == "quality_attribute_mismatch"
    entry["user_renames"] = [{**rename, "log_id": None}]  # no log entry recorded
    assert page_exclusion_reason(renamed, indexes, SNAPSHOT_ROOT) == "quality_attribute_mismatch"
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
    # Decision 12 (F8b4): a partial page pairs through a resolved crop; without one it is reported, not dropped silently.
    partial = copy.deepcopy(pages[HYMAN])
    partial["transcription_coverage"] = "partial_page"
    assert page_exclusion_reason(partial, indexes, SNAPSHOT_ROOT) == "crop_unrecorded"
    partial["crop"] = {"status": "unresolved", "reason": "transcription_not_located"}
    assert page_exclusion_reason(partial, indexes, SNAPSHOT_ROOT) == "crop_unresolved"
    partial["crop"] = {"status": "resolved", "box_normalized": [0.1, 0.2, 1.2, 0.9]}
    assert page_exclusion_reason(partial, indexes, SNAPSHOT_ROOT) == "crop_geometry_invalid"
    partial["crop"] = {"status": "resolved", "box_normalized": [0.1, 0.2, 0.9, 0.9]}
    assert page_exclusion_reason(partial, indexes, SNAPSHOT_ROOT) is None
    assert page_needs_crop(partial) and not page_needs_crop(pages[HYMAN])
    unknown = copy.deepcopy(pages[HYMAN])
    unknown["transcription_coverage"] = "commentary_only"
    assert page_exclusion_reason(unknown, indexes, SNAPSHOT_ROOT) == "transcription_coverage_unknown"
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


def test_size_templates_keep_their_text_and_are_counted() -> None:
    conversion = convert_wikitext(
        "א {{קטן|ב {{ג|ג}}}} {{גדול|1=ד}} {{קטן|קטן=ה = ו}}{{קטן|}} <small>ז</small> <big>ח</big>\n{{גדול|ט\nי}}"
    )
    assert conversion.text == "א ב ג ד ה = ו ז ח ט י"
    assert conversion.size_spans == {"large": 4, "small": 4}
    assert convert_wikitext("א").size_spans == {}
    assert wikitext_to_plain_text("{{קטן|1= א }}ב") == "אב"


def test_footnotes_render_as_marks_and_notes_at_the_foot() -> None:
    # Decision 11: {{הערה}} and <ref> become "[n]" marks and "[n] text" lines where <references/> stands
    # (else after the body); named notes reuse their number; editors' signed notes are dropped and counted.
    conversion = convert_wikitext(
        'א{{הערה|ראשונה}} ב<ref name=x>שנייה</ref> ג<ref name=x/> ד{{הערה|ט"ס - ויקיעורך}} ה'
        "<ref follow=p>המשך מהעמוד הקודם</ref>\n<references/>\nסוף"
    )
    assert conversion.text == "א[1] ב[2] ג[2] ד ה\n\nהמשך מהעמוד הקודם\n[1] ראשונה\n[2] שנייה\n\nסוף"
    assert conversion.features == {"editor_notes_dropped": 1, "footnote_continuations": 1, "footnotes": 2}
    assert wikitext_to_plain_text("א{{הערה|ב {{קטן|ג}}}}") == "א[1]\n\n[1] ב ג"


def test_tables_blocks_and_editor_markup_errors() -> None:
    assert wikitext_to_plain_text('{|\n|-\n| א || ב\n|-\n| style="x" | ג\n|}\nד') == "א\n\nב\n\nג\n\nד"
    assert wikitext_to_plain_text("א<div>ב</div>ג<center>ד</center>") == "א\n\nב\n\nג\n\nד"
    assert wikitext_to_plain_text("<poem>שורה א\nשורה ב</poem>") == "שורה א\nשורה ב"
    # Broken markup that MediaWiki shows literally is rendered as printed and counted.
    broken = convert_wikitext("[[א|[[א|ב]]]] ג]] {{{קטן|ד}} {{מ:פסוק|מלכים ב|כה|7}ה {{גדול|{{גדול|:}} ו")
    assert broken.text == "ב ג ד 7 ה : ו"
    assert broken.features["malformed_markup"] == 4
    # The Page view: the ProofreadPage header and footer go; an editor's in-body noinclude stays; includeonly goes.
    page = "<noinclude>כותרת</noinclude>גוף<noinclude>\nפרק ב\n</noinclude>עוד<includeonly>הכללה</includeonly><noinclude>footer</noinclude>"
    assert wikitext_to_plain_text(page) == "גוף פרק ב עוד"
    assert wikitext_to_plain_text("א<nowiki>'''*)'''</nowiki>ב") == "א'''*)'''ב"
    assert wikitext_to_plain_text("'''מעשה א''''") == "מעשה א'"
    assert wikitext_to_plain_text("‫==כותרת==\nטקסט") == "כותרת\n\nטקסט"


@pytest.mark.parametrize(
    ("wikitext", "expected"),
    [
        ("{{ממ|חולין קלא|א}}", "(חולין קלא, א)"),
        ('{{מ"מ|אבות|ו|א|עיין שם=ושם}}', "(אבות ו, א ושם)"),
        ('{{מקור|נידה נו א|נ"ו.}}', '(נ"ו.)'),
        ("{{צ|ציטוט}} {{צ|מרכאות=לא|בלי}}", '"ציטוט" בלי'),
        ("{{מצ|דברים כד|יט|כי תקצר}}", '(דברים כד, יט): "כי תקצר"'),
        ("{{הפניה לפסוקים|תהלים|קכד|ב}}", "(תהלים קכ\"ד, ב')"),
        ("{{פסוק|והחוט המשולש|קהלת|ד|יב}}", '"והחוט המשולש" (קהלת ד, יב)'),
        ("{{הפניה-גמ1|שבת|נה|א}}", "(שבת נה.)"),
        ('{{ב|רחב"פ|רבי חנינא}} {{מונחון|א|ב}}', 'רחב"פ א'),
        ("{{מ:פסוק|מלכים א|כב|א}}טקסט", "כב א טקסט"),
        ("{{שדל:דה|ספר=בראשית|פרק=א|פסוק=א||}} {{שדל:דה|בראשית ברא|,}}", "(א) בראשית ברא"),
        ("{{כו|ספר|כותרת משנה|ספר=1}}", "ספר\n\nספר\n\nכותרת משנה"),
        ("א{{רווח קשיח|3}}ב{{ססס}}ג", "א ב ג"),
        ("{{גדול-מודגש|א}}{{גודל גופן|5|ב}}{{הוראה למתפללים|ג}}", "אבג"),
    ],
)
def test_template_renderings_follow_mediawiki(wikitext: str, expected: str) -> None:
    assert wikitext_to_plain_text(wikitext) == expected


@pytest.mark.parametrize(
    ("wikitext", "kind"),
    [
        ("{{גדול}}", "template argument"),
        ("{{קטן|גודל=90|א}}", "template argument"),
        ("{{הערה|א|קבוצה=ב}}", "footnote"),
        ("א<ref group=x>ב</ref>", "footnote"),
        ("א{{הערה|שם=x}}", "footnote"),
        ("{{#קטע:דף|קטע}}", "transclusion"),
        ("טקסט{{תבנית חדשה|א}}", "template"),
        ("{{#if:x|y}}", "template"),
        ("<pre>א</pre>", "tag"),
        ("<math>x</math>", "tag"),
        ("__NOTOC__", "markup"),
        ("[[Media:x.ogg]]", "link"),
    ],
)
def test_wikitext_outside_the_closed_set_is_rejected(wikitext: str, kind: str) -> None:
    with pytest.raises(UnsupportedWikitextError) as error:
        wikitext_to_plain_text(wikitext)
    assert error.value.kind == kind


def test_labelled_section_transclusion_renders_the_pinned_sections() -> None:
    """F8b4: {{#קטע:title|section}} takes that section of the pinned page, as Labelled Section Transclusion does."""

    commentary = (
        "<noinclude>{{ניווט}}</noinclude><קטע התחלה=עמוד 6/>{{#קטע:משלי א/טעמים|א}}{{מ:טעמי המקרא-סוף}}\n"
        "'''משלי שלמה''' – פירוש.<קטע סוף=עמוד 6/><קטע התחלה=עמוד 7/>אחר<קטע סוף=עמוד 7/>"
    )
    verses = "<noinclude>{{מ:טעמי המקרא}}</noinclude><קטע התחלה=א/>{{מ:דחי|מִ֭שְׁלֵי|x}} שְׁלֹמֹ֣ה{{ר1}}מֶ֗לֶךְ<קטע סוף=א/>"
    page = '<noinclude><pagequality level="3" user="X" /></noinclude>{{#קטע:פירוש/א|עמוד 6}}<noinclude></noinclude>'
    pinned = {"פירוש/א": commentary, "משלי_א/טעמים": verses}
    assert transcluded_titles(page) == ["פירוש/א"] and transcluded_titles(commentary, body=False) == ["משלי א/טעמים"]
    assert convert_wikitext(page, pinned).text == "מִ֭שְׁלֵי שְׁלֹמֹ֣ה\nמֶ֗לֶךְ\n\nמשלי שלמה – פירוש."
    assert section_text('<section begin="a" />x<section end="a" />y<section begin=a/>z', "a") == "xz"
    with pytest.raises(UnsupportedWikitextError, match="page not pinned"):
        convert_wikitext(page, {"פירוש/א": commentary})
    with pytest.raises(UnsupportedWikitextError, match="not on the transcluded page"):
        convert_wikitext(page.replace("עמוד 6", "עמוד 9"), pinned)


def test_unused_positional_arguments_are_hidden_as_mediawiki_hides_them() -> None:
    conversion = convert_wikitext("{{קטן|א|ב}}{{גדול|ג|ד}}")
    assert conversion.text == "אג"
    assert conversion.features == {"hidden_arguments": 2}


# --- adapter -----------------------------------------------------------------------------------------------


def test_discovery_emits_stable_ids_and_provenance_metadata() -> None:
    bundle, source = _bundle_and_source()
    importer = WikisourceProofreadImporter()
    options = StageOptions()
    candidates = importer.discover_candidates(source, bundle, options)
    assert [candidate.candidate_id for candidate in candidates] == [
        f"{SOURCE_ID}:{BOSTENAY}",
        f"{SOURCE_ID}:{BUBER}",
        f"{SOURCE_ID}:{HYMAN}",
        f"{SOURCE_ID}:{SELIHOT}",
        f"{SOURCE_ID}:{SIPPUREI}",
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
    assert metadata["text_normalization"] == "wikisource_plain_text.v2"
    assert metadata["text_size_spans"] == {"large": 1, "small": 2}
    assert metadata["work_language"] == "he"
    assert metadata["transcription_coverage_check"].startswith("Page render compared by eye")
    assert enriched[BOSTENAY].metadata["text_size_spans"] == {}
    assert enriched[HYMAN].metadata["scan_source_origin"] == "hebrewbooks"
    assert enriched[HYMAN].metadata["wikisource_quality_label"] == "proofread"
    # Footnote marks are [n]: a reference-normalisation fact evaluation can mask (F8b4).
    assert selihot.metadata["reference_normalization"] == {"footnote_marker_style": None, "footnote_count": 0}
    # F8b4 (decision 12): a partial page pairs its unchanged text with the crop of the transcribed region.
    for slug in (BUBER, SIPPUREI):
        record = enriched[slug]
        crop = record.metadata["crop"]
        assert record.metadata["needs_crop"] and record.metadata["transcription_coverage"] == "partial_page"
        assert record.asset_references[0].reference == f"assets/{slug}__crop.png"
        assert record.metadata["expected_asset_sha256"] == crop["asset_sha256"]
        assert crop["source_page_image"]["path"] == f"assets/{slug}.jpg" and crop["method"] == "ocr_alignment_union_box.v1"
        x0, y0, x1, y1 = crop["box_px"]
        assert 0 <= x0 < x1 <= crop["source_page_image"]["width"] and 0 <= y0 < y1 <= crop["source_page_image"]["height"]
        assert crop["located_by"]["checker"].startswith("hocrgen.tools.wikisource_coverage")
        assert record.metadata["transcription_coverage_check"]["checked_by"] == "agent"  # the agent's verdict, the tool's crop
    assert enriched[BUBER].metadata["crop"]["box_normalized"][3] < 0.4  # the notes below are cut away
    for record in enriched.values():
        assert record.asset_references[0].reference.startswith("assets/")
        for key, value in record.metadata.items():
            assert not (isinstance(value, str) and value.startswith("/")), key


def test_enrichment_accepts_anonymous_creators_without_death_year(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    indexes_path = config_root / "wikisource_snapshot" / "indexes.json"
    payload = json.loads(indexes_path.read_text(encoding="utf-8"))
    hyman = next(index for index in payload["indexes"] if index["index_key"] == "hyman_toldoth_1910_vol1")
    hyman["work"] = {"title": "t", "published_year": 1910, "language": "he", "creators": [{"name": "פלוני", "role": "pseudonymous"}]}
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
    assert (candidate_count, asset_count) == (5, 5)
    assert all(check["status"] == "ok" for check in checks)
    crops = {check["record_id"]: check for check in checks if check["name"] == "wikisource_page_crop"}
    assert sorted(crops) == [BUBER, SIPPUREI] and all(check["status"] == "ok" for check in crops.values())
    index_exclusions = next(check for check in checks if check["name"] == "wikisource_index_exclusions")
    assert index_exclusions["actual"] == {
        "creator_death_year_missing": 1,
        "creator_died_after_1955": 2,
        "excluded_birnbaum_work": 2,
        "index_language_unrecorded": 2,
    }

    config_root = _copy_snapshot_config(tmp_path)
    snapshot = config_root / "wikisource_snapshot"
    (snapshot / "assets" / f"{HYMAN}.jpg").unlink()
    (snapshot / "wikitext" / f"{SELIHOT}.wikitext.txt").write_text("drift", encoding="utf-8")
    (snapshot / "text" / f"{BOSTENAY}.txt").unlink()
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (3, 2)
    assert any(check["name"] == "wikisource_page_asset" and check["status"] == "error" for check in checks)
    drift = {check["record_id"]: check["message"] for check in checks if check["name"] == "wikisource_page_text"}
    assert drift == {SELIHOT: "wikitext_checksum_mismatch", BOSTENAY: "page_text_file_missing"}
    assert next(check for check in checks if check["name"] == "wikisource_page_exclusions")["actual"] == {
        "page_text_file_missing": 1,
        "wikitext_checksum_mismatch": 1,
    }
    assert all(not str(check.get("path", "")).startswith("/") for check in checks)


def test_source_health_and_acquisition_verify_the_crop_against_its_page(tmp_path: Path) -> None:
    """F8b4: the crop asset is pinned, its box lies inside the page image, and it is that image cut at the box."""

    config_root = _copy_snapshot_config(tmp_path)
    snapshot = config_root / "wikisource_snapshot"
    pages_path = snapshot / "pages.jsonl"
    pages = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    by_id = {page["source_item_id"]: page for page in pages}
    assert crop_asset_problems(by_id[BUBER], snapshot) == []
    moved = copy.deepcopy(by_id[BUBER])
    moved["crop"]["box_px"] = [moved["crop"]["box_px"][0] + 1, *moved["crop"]["box_px"][1:]]
    assert crop_asset_problems(moved, snapshot) == ["crop_geometry_mismatch"]
    # Another crop asset with the right checksum but other pixels: re-pin it to look valid, then compare pixels.
    from PIL import Image

    other = snapshot / "assets" / f"{BUBER}__crop.png"
    with Image.open(other) as image:
        flipped = image.transpose(Image.FLIP_LEFT_RIGHT)
    flipped.save(other)
    by_id[BUBER]["crop"]["asset"]["sha256"] = hashlib.sha256(other.read_bytes()).hexdigest()
    assert crop_asset_problems(by_id[BUBER], snapshot) == ["crop_pixels_mismatch"]
    pages_path.write_text("".join(json.dumps(page, ensure_ascii=False) + "\n" for page in pages), encoding="utf-8")
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    checks, _, asset_count = _inspect_source(source, bundle)
    crop = next(check for check in checks if check["name"] == "wikisource_page_crop" and check["record_id"] == BUBER)
    assert crop["status"] == "error" and crop["message"] == "crop_pixels_mismatch" and asset_count == 4
    importer = WikisourceProofreadImporter()
    candidates = [c for c in importer.discover_candidates(source, bundle, StageOptions()) if c.source_item_id == BUBER]
    enriched = importer.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
    items = [
        ItemRecord(**record.model_dump(), item_id=record.candidate_id, normalized_license="CC-BY-SA-4.0", rights_classification="sharealike",
                   eligibility="review_required", eligibility_reason="wikisource fixture")
        for record in enriched
    ]
    with pytest.raises(StageExecutionError, match="crop_pixels_mismatch"):
        importer.acquire_items(source, bundle, items, tmp_path / "acquired", StageOptions())
    (snapshot / "assets" / f"{BUBER}__crop.png").unlink()
    assert crop_asset_problems(by_id[BUBER], snapshot) == ["crop_asset_missing"]


def test_review_profile_routes_pages_to_review_and_open_profile_ignores_them(tmp_path: Path, capsys) -> None:
    assert main(["build-release", "--profile", "profile_review_v1", "--dry-run", "--workdir", str(tmp_path / "review")]) == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    queue = json.loads((run_dir / "review" / "queue.json").read_text(encoding="utf-8"))
    queued = {item["item_id"]: item for item in queue["items"] if item["source_id"] == SOURCE_ID}
    assert sorted(queued) == [f"{SOURCE_ID}:{BOSTENAY}", f"{SOURCE_ID}:{BUBER}", f"{SOURCE_ID}:{HYMAN}", f"{SOURCE_ID}:{SELIHOT}", f"{SOURCE_ID}:{SIPPUREI}"]
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
        "quality_3_single_reviewer": 3,
        "text_changed_after_validation": 1,
    }


def test_reference_pool_converts_only_adjudication_eligible_validated_pages(tmp_path: Path) -> None:
    bundle, source = _bundle_and_source()
    benchmark_manifest = package_root() / "data" / "benchmark" / "benchmark_v1" / "reference_manifest.json"
    before = benchmark_manifest.read_bytes()
    manifest = write_wikisource_reference_pool(source, bundle, tmp_path / "pool")
    assert benchmark_manifest.read_bytes() == before
    assert [entry["item_id"] for entry in manifest["items"]] == [f"{SOURCE_ID}:{SELIHOT}"]
    assert manifest["skipped"] == {"quality_3_single_reviewer": 3, "text_changed_after_validation": 1}
    assert manifest["text_license"] == "CC-BY-SA-4.0"
    entry = manifest["items"][0]
    assert entry["reference_normalization"] == {"footnote_marker_style": None, "footnote_count": 0}
    assert set(entry["image"]) == {"page"}
    payload = (tmp_path / "pool" / entry["path"]).read_text(encoding="utf-8")
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == entry["sha256"]
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(payload)
    assert record.review.status == "reviewed"
    assert record.review.adjudicator is None
    assert record.review.reviewers == ["wikisource:Neriah", "wikisource:Nahum"]
    _, pages = _snapshot()
    assert record.pages[0].text == page_plain_text(pages[SELIHOT], SNAPSHOT_ROOT)
    assert "\n".join(line.text for line in record.lines) == record.pages[0].text.replace("\n\n", "\n")


def test_rename_chains_match_the_attribute_only_through_the_editors_own_account() -> None:
    """F8b5: Eitan96 was איתן96 until 2014-07-30 (Meta log 9259138); J. Nord was Elendil 03 until 2025-03-21."""

    entry = {"user": "J. Nord", "pagequality_user_attribute": "Elendil 03", "timestamp": "2024-04-05T16:01:05Z"}
    assert not pagequality_attribute_names_editor(entry)
    renames = [
        {"old": "Elendil 03", "new": "J. Nord", "log_id": 59156686, "timestamp": "2025-03-21T15:38:05Z"},
        {"old": "Elendil 03", "new": "J. Nord", "log_id": 1749979, "timestamp": "2025-03-21T15:38:36Z"},
    ]
    assert pagequality_attribute_names_editor({**entry, "user_renames": renames})
    chain = [{"old": "A", "new": "B", "log_id": 1, "timestamp": "2025-01-01"}, {"old": "B", "new": "J. Nord", "log_id": 2, "timestamp": "2025-06-01"}]
    assert pagequality_attribute_names_editor({**entry, "pagequality_user_attribute": "A", "user_renames": chain})
    assert not pagequality_attribute_names_editor({**entry, "pagequality_user_attribute": "C", "user_renames": chain})
    assert pagequality_attribute_names_editor({"user": "X", "pagequality_user_attribute": "X"})


def test_a_multi_region_crop_masks_the_rest_of_its_box_and_keeps_the_regions_pixels(tmp_path: Path) -> None:
    """F8b5: interleaved untranscribed blocks are masked to the page background; the transcribed pixels are the page's."""

    from PIL import Image

    config_root = _copy_snapshot_config(tmp_path)
    snapshot = config_root / "wikisource_snapshot"
    pages_path = snapshot / "pages.jsonl"
    pages = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines()]
    page = next(page for page in pages if page["source_item_id"] == BUBER)
    crop = page["crop"]
    x0, y0, x1, y1 = crop["box_normalized"]
    middle = round((y0 + y1) / 2, 3)
    crop["regions_normalized"] = [[x0, y0, x1, middle - 0.02], [round((x0 + x1) / 2, 3), middle + 0.02, x1, y1]]
    crop["method"] = "agent_visual_crop.v1"
    assert crop_geometry_valid(crop)
    with Image.open(snapshot / page["image"]["path"]) as opened:
        page_image = opened.convert("RGB")
    box = crop_pixel_box(crop["box_normalized"], *page_image.size)
    crop["mask_fill"] = crop_mask_fill(page_image, box)
    crop["regions_px"] = [list(crop_pixel_box(region, *page_image.size)) for region in crop["regions_normalized"]]
    masked = crop_image(page_image, crop)
    assert masked.size == (box[2] - box[0], box[3] - box[1])
    # every pixel of each region is the page's own; every pixel outside the regions is the fill
    for region in crop["regions_px"]:
        local = (region[0] - box[0], region[1] - box[1], region[2] - box[0], region[3] - box[1])
        assert masked.crop(local).tobytes() == page_image.crop(tuple(region)).tobytes()
    upper, lower = crop["regions_px"]
    gap_y = (upper[3] + lower[1]) // 2 - box[1]
    assert masked.getpixel((1, gap_y)) == tuple(crop["mask_fill"])
    assert masked.getpixel((1, lower[1] - box[1] + 2)) == tuple(crop["mask_fill"])  # beside the second region
    assert all(value > 150 for value in crop["mask_fill"])  # the paper, not the print
    asset = snapshot / crop["asset"]["path"]
    masked.save(asset)
    crop["asset"]["sha256"] = hashlib.sha256(asset.read_bytes()).hexdigest()
    assert crop_asset_problems(page, snapshot) == []
    # the verification compares against the page: a wrong region, a missing fill or altered pixels are found
    assert crop_asset_problems({**page, "crop": {**crop, "regions_px": [upper, [lower[0] + 1, *lower[1:]]]}}, snapshot) == ["crop_geometry_mismatch"]
    assert crop_asset_problems({**page, "crop": {**crop, "mask_fill": None}}, snapshot) == ["crop_mask_fill_invalid"]
    assert crop_asset_problems({**page, "crop": {**crop, "mask_fill": [255, 255, 255]}}, snapshot) == ["crop_pixels_mismatch"]
    assert not crop_geometry_valid({**crop, "box_normalized": [x0, y0, x1, y1 - 0.01]})  # the box must be the regions' union
    assert not crop_geometry_valid({**crop, "regions_normalized": crop["regions_normalized"][:1]})
    pages_path.write_text("".join(json.dumps(one, ensure_ascii=False) + "\n" for one in pages), encoding="utf-8")
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)
    checks, _, _ = _inspect_source(source, bundle)
    health = next(check for check in checks if check["name"] == "wikisource_page_crop" and check["record_id"] == BUBER)
    assert health["status"] == "ok", health
    importer = WikisourceProofreadImporter()
    candidates = [c for c in importer.discover_candidates(source, bundle, StageOptions()) if c.source_item_id == BUBER]
    record = importer.fetch_candidate_metadata(source, bundle, candidates, StageOptions())[0]
    assert record.metadata["crop"]["regions_px"] == crop["regions_px"] and record.metadata["crop"]["mask_fill"] == crop["mask_fill"]
    assert record.metadata["expected_asset_sha256"] == crop["asset"]["sha256"]
    manifest = write_wikisource_reference_pool(source, bundle, tmp_path / "pool")
    assert manifest["skipped"]  # quality 3: not adjudication-eligible, so no reference; the pool still builds
