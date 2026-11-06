from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from hocrgen.classify.heuristics import classify_items
from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.government_print import (
    KnessetCommitteeImporter,
    ReshumotImporter,
    knesset_entry_exclusion_reasons,
    load_government_print_snapshot,
    reshumot_entry_exclusion_reasons,
)
from hocrgen.manifests.models import CuratedItemRecord, ItemRecord
from hocrgen.parsers.pdf_bidi import (
    BIDI_CONTROL_CHARACTERS,
    layout_notes,
    logical_order_issues,
    poppler_line_to_logical,
    poppler_text_to_logical,
    strip_bidi_controls,
)
from hocrgen.source_ops import _inspect_source
from hocrgen.utils.hashing import sha256_file

RESHUMOT_ID = "reshumot_born_digital"
KNESSET_ID = "knesset_committee_protocols_pre1976"
RESHUMOT_ROOT = package_root() / "data" / "reshumot" / "snapshot"
KNESSET_ROOT = package_root() / "data" / "knesset_committees" / "snapshot"
SH_P2 = "sefer_hachukim_2580__p0002"
SH_P4 = "sefer_hachukim_2580__p0004"
KT_P2 = "kovetz_hatakanot_7712__p0002"
K1952_P2 = "knesset_committee_399388__p0002"
K1952_P3 = "knesset_committee_399388__p0003"
K1975_P2 = "knesset_committee_430997__p0002"
K1976 = "knesset_committee_430999__p0001"
K_BACKGROUND = "knesset_committee_304940__p0001"

LRE, RLE, POP, RLM = "‪", "‫", "‬", "‏"


def _bundle_and_source(source_id: str, config_root: Path | None = None):
    bundle = load_and_validate_bundle(config_root) if config_root else load_and_validate_bundle()
    return bundle, next(source for source in bundle.source_registry.sources if source.id == source_id)


def _entries(root: Path) -> dict[str, dict]:
    _, entries = load_government_print_snapshot(root)
    return {entry["entry_id"]: entry for entry in entries}


def _copy(entry: dict) -> dict:
    return json.loads(json.dumps(entry))


def _copy_snapshot_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(RESHUMOT_ROOT, config_root / "reshumot_snapshot")
    shutil.copytree(KNESSET_ROOT, config_root / "knesset_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == RESHUMOT_ID:
            source["settings"]["extra"]["government_print_snapshot_root"] = "reshumot_snapshot"
        if source["id"] == KNESSET_ID:
            source["settings"]["extra"]["government_print_snapshot_root"] = "knesset_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return config_root


def _items(enriched) -> list[ItemRecord]:
    return [
        ItemRecord(
            **record.model_dump(),
            item_id=record.candidate_id,
            normalized_license="PD-IL",
            rights_classification="open",
            eligibility="review_required",
            eligibility_reason="f8e fixture",
        )
        for record in enriched
    ]


# --- config ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source_id", "fetcher", "content_type"),
    [(RESHUMOT_ID, "reshumot", "printed_modern"), (KNESSET_ID, "knesset_committee", "typewritten_historical")],
)
def test_f8e_sources_are_review_only_and_outside_the_public_profile(source_id: str, fetcher: str, content_type: str) -> None:
    bundle, source = _bundle_and_source(source_id)
    assert source.fetcher == fetcher
    assert source.status.value == "review_only"
    assert source.default_public_release is False
    assert source.allowed_content_types == [content_type]
    assert source.rights_strategy.values == ["PD-IL"]
    assert source.normalized_license == "PD-IL"
    assert source.rights_classification.value == "open"
    # No privacy-review gate for public-domain official publications (maintainer decision 2026-11-06).
    assert source.requires_manual_review is False
    assert bundle.privacy_rules.source_defaults[source_id].value == "clear"
    assert source_id not in bundle.profiles["profile_open_v1"].include_sources
    assert source_id in bundle.profiles["profile_review_v1"].include_sources


# --- logical-order conversion and checks -------------------------------------------------------------


def test_poppler_bidi_markup_converts_to_logical_order() -> None:
    # Lines as pdftotext writes them: LTR runs (digits and their neutrals) in visual order inside LRE ... PDF.
    title = f"{RLE}חוק חובת המכרזים (תיקון מס' {LRE} ,)25{POP}התשע\"ו{LRE}*2016-{POP}{POP}"
    assert poppler_line_to_logical(title) == "חוק חובת המכרזים (תיקון מס' 25), התשע\"ו-2016*"
    assert poppler_line_to_logical(f"{RLE}{LRE}.1{POP}{POP}") == "1."
    assert poppler_line_to_logical(f"{RLE}תיקון סעיף {LRE}2{POP}א{POP}") == "תיקון סעיף 2א"
    footer = f"{RLE}ספר החוקים {LRE} ,2580{POP}י\"ב באב התשע\"ו{LRE}16.8.2016 ,{POP}{POP}"
    assert poppler_line_to_logical(footer) == "ספר החוקים 2580, י\"ב באב התשע\"ו, 16.8.2016"
    # A bidi mark between a number and a superscript footnote marker becomes one space.
    footnote = f"{RLE}בחוק{LRE} ,{POP}התשנ\"ב{LRE}1992-{POP}{RLM}{LRE}( 1{POP}להלן{POP}"
    assert poppler_line_to_logical(footnote) == "בחוק, התשנ\"ב-1992 1 (להלן"
    text, issues = poppler_text_to_logical(f"{title}\n\n{footer}\n\f")
    assert issues == []
    assert text.endswith("16.8.2016\n")
    assert not any(char in BIDI_CONTROL_CHARACTERS for char in text)


def test_conversion_reports_markup_it_cannot_invert() -> None:
    issues: set[str] = set()
    assert poppler_line_to_logical(f"{RLE}המחיר {LRE}ISSN 0334-3030{POP}{POP}", issues) == "המחיר ISSN 0334-3030"
    assert issues == {"latin_run_order_unverified"}
    for line, code in [
        (f"{RLE}טקסט{POP}{POP}", "unbalanced_embedding"),
        (f"{RLE}טקסט {LRE}12", "unbalanced_embedding"),
        (f"{RLE}טקסט {LRE}1{RLE}2{POP}{POP}{POP}", "nested_embedding"),
        (f"{RLE}טקסט {LRE}12 אב{POP}{POP}", "hebrew_inside_ltr_embedding"),
    ]:
        found: set[str] = set()
        poppler_line_to_logical(line, found)
        assert code in found, line


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("חוק‫", "bidi_controls_present"),
        ("2246\x08", "control_characters_present"),
        ("ןמוקמב רבד", "reversed_hebrew_word"),
        ('התשע"ו*2016-', "hebrew_year_gregorian_order"),
        ('התשנ"ב1992-', "hebrew_year_gregorian_order"),
        ('התשנ"ה-11995 (להלן', "footnote_marker_merged_into_year"),
        ("יבוא:אחריהוספת", "glued_punctuation"),
        (".1\nבסעיף", "section_number_order"),
        (") בסעיף (", "unbalanced_parentheses"),
    ],
)
def test_logical_order_checks_flag_each_failure(text: str, code: str) -> None:
    assert code in logical_order_issues(text)


def test_logical_order_checks_pass_clean_text_and_require_expected_phrases() -> None:
    clean = 'חוק חובת המכרזים (תיקון מס\' 25), התשע"ו-2016*\n1.\nספר החוקים 2580, 16.8.2016\n'
    assert logical_order_issues(clean) == []
    assert logical_order_issues(clean, ["ספר החוקים 2580,", "16.8.2016"]) == []
    assert logical_order_issues(clean, ["2016.8.16"]) == ["missing_expected_phrase"]
    assert layout_notes("ב ני מ י ן נ ת ני ה ו") == ["letter_spaced_run"]
    assert layout_notes('ס"ח התשנ"ב, עמ\' 114; (א) (ב) (ג)') == []


# --- Reshumot fixture --------------------------------------------------------------------------------


def test_reshumot_admitted_pages_are_reproducible_and_pass_the_order_check() -> None:
    entries = _entries(RESHUMOT_ROOT)
    assert set(entries) == {SH_P2, SH_P4, KT_P2}
    for entry_id in (SH_P2, SH_P4):
        entry = entries[entry_id]
        text = entry["text"]
        raw = (RESHUMOT_ROOT / text["extraction"]["raw_local_path"]).read_bytes().decode("utf-8")
        logical = (RESHUMOT_ROOT / text["local_path"]).read_bytes().decode("utf-8")
        assert sha256_file(RESHUMOT_ROOT / text["local_path"]) == text["sha256"]
        assert sha256_file(RESHUMOT_ROOT / text["extraction"]["raw_local_path"]) == text["extraction"]["raw_sha256"]
        assert poppler_text_to_logical(raw) == (logical, [])
        expected = [phrase["text"] for phrase in text["order_verification"]["expected_phrases"]]
        # Booklet number, date and the law's title come from the gazette API, independently of the PDF text.
        assert {phrase["source"] for phrase in text["order_verification"]["expected_phrases"]} == {
            "gazette API BookletNum and FolderType",
            "gazette API PublishDate",
            "gazette API DocSummary",
        }
        assert logical_order_issues(logical, expected) == [] == text["order_verification"]["issues"]
        # The naive extraction (control characters stripped, visual runs kept) is caught by the same checks.
        naive_issues = logical_order_issues(strip_bidi_controls(raw), expected)
        assert {"hebrew_year_gregorian_order", "section_number_order", "missing_expected_phrase"} <= set(naive_issues)
        assert text["text_provenance"] == "born_digital_pdf_text"
        assert text["text_tier"] == 2
        assert (text["adjudication_status"], text["reference_eligible"], text["heocr_attestation"]) == ("not_adjudicated", False, "none")
        assert entry["booklet"]["series"] == "sefer_hachukim"
        assert entry["pdf"]["born_digital"] is True and entry["pdf"]["page_image_count"] == 0
        assert len(entry["pdf"]["sha256"]) == 64
    assert entries[SH_P4]["text"]["layout_notes"] == ["letter_spaced_run"]


def test_reshumot_rendered_pages_record_rendering_provenance_and_pins() -> None:
    for entry_id in (SH_P2, SH_P4):
        entry = _entries(RESHUMOT_ROOT)[entry_id]
        asset = entry["files"][0]
        rendering = asset["rendering"]
        # Rendered from a born-digital PDF: never a scan.
        assert rendering["is_scan"] is False
        assert rendering["image_origin"] == "rendered_from_born_digital_pdf"
        assert rendering["renderer"] == "pdftoppm (poppler)" and rendering["renderer_version"]
        assert rendering["dpi"] == 150
        path = RESHUMOT_ROOT / asset["local_path"]
        assert sha256_file(path) == asset["sha256"]
        assert path.stat().st_size == asset["bytes"] < 150_000
        with Image.open(path) as image:
            assert image.mode == "L"
            assert image.size == (asset["width_px"], asset["height_px"]) == (1004, 1418)
            assert hashlib.sha256(image.tobytes()).hexdigest() == asset["pixel_sha256"]


def test_reshumot_page_with_wrong_extraction_order_is_rejected() -> None:
    _, source = _bundle_and_source(RESHUMOT_ID)
    entry = _entries(RESHUMOT_ROOT)[KT_P2]
    assert entry["files"] == []
    reasons = reshumot_entry_exclusion_reasons(entry, source, RESHUMOT_ROOT)
    assert reasons == ["extraction_order_not_verified", "control_characters_present", "footnote_marker_merged_into_year"]
    assert entry["text"]["order_verification"]["issues"] == reasons[1:]


def test_reshumot_series_era_and_provenance_gates() -> None:
    _, source = _bundle_and_source(RESHUMOT_ID)
    page = _entries(RESHUMOT_ROOT)[SH_P2]
    assert reshumot_entry_exclusion_reasons(page, source, RESHUMOT_ROOT) == []

    def reasons(mutate) -> list[str]:
        entry = _copy(page)
        mutate(entry)
        return reshumot_entry_exclusion_reasons(entry, source, RESHUMOT_ROOT)

    # ילקוט הפרסומים (2) and bills (6, 8) are not section-6 material.
    for folder_type in ("2", "6", "8", "4"):
        assert reasons(lambda e, ft=folder_type: e["booklet"].update(folder_type=ft)) == ["series_not_section_6"]
    assert reasons(lambda e: e["booklet"].update(series="kovetz_hatakanot")) == ["series_folder_type_mismatch"]
    assert reasons(lambda e: e["booklet"].update(publish_date="2005-12-31")) == ["before_born_digital_era"]
    assert reasons(lambda e: e["booklet"].update(publish_date=None)) == ["publish_date_unknown"]
    assert reasons(lambda e: e["pdf"].update(born_digital=False)) == ["pdf_not_born_digital"]
    assert reasons(lambda e: e["pdf"].update(page_image_count=1)) == ["pdf_not_born_digital"]
    assert reasons(lambda e: e["pdf"].update(embedded_fonts=[])) == ["pdf_not_born_digital"]
    assert reasons(lambda e: e["rights"].update(license_expression="UNKNOWN")) == ["license_not_in_source_lane"]
    assert reasons(lambda e: e["rights"].update(verification_status="unverified")) == ["rights_not_primary_page_checked"]
    assert reasons(lambda e: e.update(content_type="printed_historical")) == ["content_type_not_allowed"]
    assert reasons(lambda e: e["text"].update(text_provenance="ocr")) == ["unsupported_text_provenance"]
    assert reasons(lambda e: e["text"].update(reference_eligible=True)) == ["unsupported_reference_status"]
    assert reasons(lambda e: e["text"].update(adjudication_status="adjudicated")) == ["unsupported_reference_status"]
    assert reasons(lambda e: e["files"][0]["rendering"].update(is_scan=True)) == ["rendering_provenance_unrecorded"]
    assert reasons(lambda e: e["files"][0]["rendering"].pop("renderer_version")) == ["rendering_provenance_unrecorded"]
    assert reasons(lambda e: e.update(files=[])) == ["no_raster_asset"]
    assert reasons(lambda e: e["text"]["order_verification"].update(expected_phrases=[])) == [
        "extraction_order_not_verified",
        "no_expected_phrases",
    ]
    wrong_title = [{"text": "ספר החוקים 2581,", "source": "gazette API BookletNum and FolderType"}]
    assert reasons(lambda e: e["text"]["order_verification"].update(expected_phrases=wrong_title)) == [
        "extraction_order_not_verified",
        "missing_expected_phrase",
    ]
    assert reasons(lambda e: e["text"].update(sha256="0" * 64)) == ["text_checksum_mismatch"]
    assert reasons(lambda e: e["text"]["extraction"].update(raw_sha256="0" * 64)) == ["extraction_checksum_mismatch"]


def test_reshumot_text_must_be_reproducible_from_the_committed_extraction(tmp_path: Path) -> None:
    root = tmp_path / "snapshot"
    shutil.copytree(RESHUMOT_ROOT, root)
    _, source = _bundle_and_source(RESHUMOT_ID)
    entry = _entries(root)[SH_P2]
    text_path = root / entry["text"]["local_path"]
    # An edited text with an updated pin still fails: it no longer follows from the pdftotext output.
    text_path.write_bytes(text_path.read_bytes().replace("חובת".encode(), "חובות".encode(), 1))
    entry["text"]["sha256"] = sha256_file(text_path)
    assert reshumot_entry_exclusion_reasons(entry, source, root) == ["text_not_reproducible_from_extraction"]
    text_path.unlink()
    assert reshumot_entry_exclusion_reasons(entry, source, root) == ["missing_text_file"]


# --- Knesset committee fixture -----------------------------------------------------------------------


def test_knesset_session_date_gate_and_background_material_exclusion() -> None:
    _, source = _bundle_and_source(KNESSET_ID)
    entries = _entries(KNESSET_ROOT)
    for entry_id in (K1952_P2, K1952_P3, K1975_P2):
        assert knesset_entry_exclusion_reasons(entries[entry_id], source) == []
    # 1975-12-31 is the last admissible day; the next session (1976-01-06) waits for the legal opinion.
    assert entries[K1975_P2]["session"]["start_date"] == "1975-12-31"
    assert entries[K1976]["session"]["start_date"] == "1976-01-06"
    assert knesset_entry_exclusion_reasons(entries[K1976], source) == ["post_1975_committee_protocol_pending_legal_opinion"]
    assert entries[K_BACKGROUND]["document"]["group_type_desc"] == "חומר רקע"
    assert knesset_entry_exclusion_reasons(entries[K_BACKGROUND], source) == ["committee_background_material_not_knesset_work"]

    def reasons(mutate) -> list[str]:
        entry = _copy(entries[K1975_P2])
        mutate(entry)
        return knesset_entry_exclusion_reasons(entry, source)

    assert reasons(lambda e: e["session"].update(start_date="1976-01-01")) == ["post_1975_committee_protocol_pending_legal_opinion"]
    assert reasons(lambda e: e["session"].update(start_date="1990-05-01")) == ["post_1975_committee_protocol_pending_legal_opinion"]
    assert reasons(lambda e: e["session"].update(start_date=None)) == ["session_date_unknown"]
    assert reasons(lambda e: e["session"].update(start_date="1975-12-30")) == ["session_date_mismatch"]
    assert reasons(lambda e: e["document"].update(group_type_id=87, group_type_desc="חומר רקע")) == ["committee_background_material_not_knesset_work"]
    assert reasons(lambda e: e["document"].update(group_type_desc="חומר רקע")) == ["committee_background_material_not_knesset_work"]
    assert reasons(lambda e: e["document"].update(group_type_id=99)) == ["document_not_committee_protocol"]
    assert reasons(lambda e: e["document"].update(committee_session_id=1)) == ["session_id_mismatch"]
    assert reasons(lambda e: e["session"].update(type_desc="חסויה")) == ["session_not_open"]
    assert reasons(lambda e: e["committee"].update(name=None)) == ["committee_unknown"]
    assert reasons(lambda e: e.update(content_type="printed_historical")) == ["content_type_not_allowed"]
    assert reasons(lambda e: e["rights"].update(license_expression="UNKNOWN")) == ["license_not_in_source_lane"]


def test_knesset_pages_are_images_only_and_never_carry_upstream_ocr() -> None:
    _, source = _bundle_and_source(KNESSET_ID)
    entry = _entries(KNESSET_ROOT)[K1952_P2]
    assert entry["text"]["text_provenance"] == "none" and "local_path" not in entry["text"]
    assert "Imagestore" in entry["pdf"]["subject"]
    with_ocr = _copy(entry)
    with_ocr["text"].update(local_path="text/ocr.txt", text_provenance="ocr")
    assert knesset_entry_exclusion_reasons(with_ocr, source) == ["upstream_ocr_text_not_allowed"]
    unrecorded = _copy(entry)
    unrecorded["files"][0]["scan"]["is_scan"] = False
    assert knesset_entry_exclusion_reasons(unrecorded, source) == ["scan_provenance_unrecorded"]
    no_image = _copy(entry)
    no_image["files"] = []
    assert knesset_entry_exclusion_reasons(no_image, source) == ["no_raster_asset"]


def test_knesset_fixture_scans_match_their_pins() -> None:
    entries = _entries(KNESSET_ROOT)
    expected = {K1952_P2: (2026737, "1952-11-25", 2), K1952_P3: (2026737, "1952-11-25", 2), K1975_P2: (2037304, "1975-12-31", 8)}
    for entry_id, (session_id, session_date, knesset_num) in expected.items():
        entry = entries[entry_id]
        assert entry["content_type"] == "typewritten_historical"
        assert (entry["session"]["committee_session_id"], entry["session"]["start_date"], entry["session"]["knesset_num"]) == (
            session_id,
            session_date,
            knesset_num,
        )
        assert entry["committee"]["name"] == "ועדת הכלכלה"
        asset = entry["files"][0]
        assert asset["scan"]["is_scan"] is True and asset["scan"]["x_ppi"] == 300
        path = KNESSET_ROOT / asset["local_path"]
        assert sha256_file(path) == asset["sha256"]
        assert path.stat().st_size == asset["bytes"] < 150_000
        with Image.open(path) as image:
            assert image.mode == "1"
            assert image.size == (asset["width_px"], asset["height_px"])
            assert hashlib.sha256(image.tobytes()).hexdigest() == asset["pixel_sha256"]


# --- adapters ----------------------------------------------------------------------------------------


def test_discovery_emits_stable_ids_and_provenance_metadata() -> None:
    bundle, reshumot = _bundle_and_source(RESHUMOT_ID)
    options = StageOptions()
    importer = ReshumotImporter()
    discovered = importer.discover_candidates(reshumot, bundle, options)
    assert [candidate.candidate_id for candidate in discovered] == [f"{RESHUMOT_ID}:{SH_P2}", f"{RESHUMOT_ID}:{SH_P4}"]
    assert len(importer.discover_candidates(reshumot, bundle, StageOptions(max_items=1))) == 1
    page = importer.fetch_candidate_metadata(reshumot, bundle, discovered, options)[0]
    assert page.raw_rights_text == "PD-IL"
    assert page.source_url.startswith("https://free-justice.openapi.gov.il/")
    assert page.asset_references[0].reference == f"assets/{SH_P2}.png"
    metadata = page.metadata
    assert (metadata["content_type"], metadata["period"], metadata["created"]) == ("printed_modern", "modern", "2016-08-16")
    assert metadata["is_scan"] is False and metadata["image_origin"] == "rendered_from_born_digital_pdf"
    assert metadata["text_order_verified"] is True
    assert (metadata["text_provenance"], metadata["text_tier"], metadata["reference_eligible"]) == ("born_digital_pdf_text", 2, False)
    assert metadata["source_group_id"] == "reshumot:sefer_hachukim:2580"
    assert metadata["printed_page_number"] == "1226"

    bundle, knesset = _bundle_and_source(KNESSET_ID)
    importer = KnessetCommitteeImporter()
    discovered = importer.discover_candidates(knesset, bundle, options)
    assert [candidate.candidate_id for candidate in discovered] == [f"{KNESSET_ID}:{entry}" for entry in (K1952_P2, K1952_P3, K1975_P2)]
    page = importer.fetch_candidate_metadata(knesset, bundle, discovered, options)[0]
    assert page.source_url == "https://fs.knesset.gov.il//2/Committees/2_ptv_399388.PDF"
    metadata = page.metadata
    assert (metadata["content_type"], metadata["period"], metadata["is_scan"]) == ("typewritten_historical", "historical", True)
    assert (metadata["knesset_committee_session_id"], metadata["knesset_session_date"]) == (2026737, "1952-11-25")
    assert (metadata["text_provenance"], metadata["text_tier"]) == ("none", 4)
    assert "text_reference" not in metadata
    for record in [page]:
        assert not [value for value in record.metadata.values() if isinstance(value, str) and value.startswith("/")]


def test_acquire_copies_assets_and_verifies_checksums(tmp_path: Path) -> None:
    config_root = _copy_snapshot_config(tmp_path)
    options = StageOptions()
    bundle, source = _bundle_and_source(RESHUMOT_ID, config_root)
    importer = ReshumotImporter()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    acquired = importer.acquire_items(source, bundle, _items(enriched), tmp_path / "acquire", options)
    assert [item.acquired_assets[0].sha256 for item in acquired] == [record.metadata["expected_asset_sha256"] for record in enriched]
    (config_root / "reshumot_snapshot" / "text" / f"{SH_P2}.txt").write_text("tampered", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="text checksum mismatch"):
        importer.acquire_items(source, bundle, _items(enriched[:1]), tmp_path / "acquire-text", options)
    Path(enriched[1].asset_references[0].resolved_path or "").write_bytes(b"tampered")
    with pytest.raises(StageExecutionError, match="asset checksum mismatch"):
        importer.acquire_items(source, bundle, _items(enriched[1:]), tmp_path / "acquire-asset", options)

    bundle, source = _bundle_and_source(KNESSET_ID, config_root)
    importer = KnessetCommitteeImporter()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    acquired = importer.acquire_items(source, bundle, _items(enriched), tmp_path / "acquire-knesset", options)
    assert len(acquired) == 3


def test_source_health_counts_exclusions_and_reports_broken_pins(tmp_path: Path) -> None:
    for source_id, counts, exclusions in [
        (RESHUMOT_ID, (2, 2), {"extraction_order_not_verified": 1}),
        (KNESSET_ID, (3, 3), {"committee_background_material_not_knesset_work": 1, "post_1975_committee_protocol_pending_legal_opinion": 1}),
    ]:
        bundle, source = _bundle_and_source(source_id)
        checks, candidate_count, asset_count = _inspect_source(source, bundle)
        assert (candidate_count, asset_count) == counts
        assert all(check["status"] == "ok" for check in checks)
        assert next(check for check in checks if check["name"].endswith("_entry_exclusions"))["actual"] == exclusions
        assert all(not str(check.get("path", "")).startswith("/") for check in checks)

    config_root = _copy_snapshot_config(tmp_path)
    (config_root / "reshumot_snapshot" / "text" / f"{SH_P4}.txt").unlink()
    (config_root / "knesset_snapshot" / "assets" / f"{K1975_P2}.png").write_bytes(b"tampered")
    bundle, source = _bundle_and_source(RESHUMOT_ID, config_root)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (1, 1)
    assert any(check["name"] == "reshumot_entry_text" and check["status"] == "error" for check in checks)
    bundle, source = _bundle_and_source(KNESSET_ID, config_root)
    checks, candidate_count, asset_count = _inspect_source(source, bundle)
    assert (candidate_count, asset_count) == (3, 2)
    assert any(check["name"] == "knesset_committee_entry_asset" and check["status"] == "error" for check in checks)


def test_typewritten_content_type_classifies_as_printed() -> None:
    bundle, source = _bundle_and_source(KNESSET_ID)
    importer = KnessetCommitteeImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    item = _items(enriched[:1])[0]
    curated = CuratedItemRecord(
        **item.model_dump(), qa_status="pass", content_fingerprint="f", dedupe_status="retained", canonical_item_id=item.item_id
    )
    classified = classify_items([curated], bundle).classified_items[0]
    assert (classified.content_class, classified.content_confidence) == ("printed", 0.9)
    assert classified.period_class == "historical"
    # No content-class review reason (this bare record has no normalized assets, so quality is low).
    assert not [reason for reason in classified.classification_review_reasons if reason.startswith("content")]
