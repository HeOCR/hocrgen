"""Network-free tests for the Internet Archive scan source of the F8f alignment (hocrgen.fetchers.ia_iiif)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hocrgen.fetchers import ia_iiif as ia
from hocrgen.fetchers.nli_iiif import canvas_image_service
from hocrgen.tools import benyehuda_nli_alignment as tool

FIXTURE = Path(__file__).parent / "fixtures" / "ia"
IDENTIFIER = "hegyoneshpinozah00rubi"


def _metadata() -> dict:
    return json.loads((FIXTURE / f"metadata_{IDENTIFIER}.json").read_text(encoding="utf-8"))


def _manifest() -> dict:
    return json.loads((FIXTURE / f"manifest_v3_{IDENTIFIER}.json").read_text(encoding="utf-8"))


def _with(**fields: object) -> dict:
    md = dict(_metadata()["metadata"])
    for key, value in fields.items():
        key = key.replace("_", "-") if key == "possible_copyright_status" else key
        if value is None:
            md.pop(key, None)
        else:
            md[key] = value
    return {"metadata": md}


# --- rights gate -------------------------------------------------------------------------------------------


def test_library_scan_without_licence_field_is_accepted_with_evidence() -> None:
    decision = ia.decide_ia_rights(_metadata())
    assert decision.accepted
    assert decision.reason == "ia_library_scan_accepted"
    assert decision.source_class == "ia_library_scan_no_licence_field"
    evidence = decision.evidence()
    assert evidence["gate"] == ia.IA_GATE
    assert evidence["decision_record"] == "planning/decisions/2026-11-09-internet-archive-library-scans.md"
    assert evidence["identifier"] == IDENTIFIER
    assert evidence["contributor"] == "Robarts - University of Toronto"
    assert evidence["sponsor"] == "University of Toronto"
    assert evidence["scanner"] == "scribe10.toronto.archive.org"
    assert evidence["collections"] == ["robarts", "toronto", "university_of_toronto"]
    # Absent licence fields are recorded as null, not dropped.
    assert evidence["possible-copyright-status"] is None and evidence["licenseurl"] is None and evidence["rights"] is None
    assert evidence["decision"] == "accepted" and evidence["failed_conditions"] == []
    # The bare metadata object is read the same as the /metadata response.
    assert ia.decide_ia_rights(_metadata()["metadata"]).evidence() == evidence


@pytest.mark.parametrize(
    ("fields", "source_class"),
    [
        ({"licenseurl": "http://creativecommons.org/publicdomain/mark/1.0/", "possible_copyright_status": "NOT_IN_COPYRIGHT"}, "ia_library_scan_public_domain_mark"),
        ({"licenseurl": "https://creativecommons.org/publicdomain/zero/1.0"}, "ia_library_scan_cc0"),
        ({"rights": "Public domain in the United States."}, "ia_library_scan_rights_statement_public_domain"),
    ],
)
def test_public_domain_licence_fields_give_their_own_source_class(fields: dict, source_class: str) -> None:
    decision = ia.decide_ia_rights(_with(**fields))
    assert decision.accepted and decision.source_class == source_class


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"sponsor": "Google"}, "ia_google_scan:sponsor"),
        ({"contributor": "Google Books"}, "ia_google_scan:contributor"),
        ({"scanner": "Google"}, "ia_google_scan:scanner"),
        ({"collection": ["americana", "googlebooks"]}, "ia_google_scan:collection"),
        ({"identifier": "bub_gb_AbCdEf123"}, "ia_google_scan:identifier"),
        ({"identifier": "liuimshonimmiki00geiggoog"}, "ia_google_scan:identifier"),
        ({"description": "Book digitized by Google from the library of Oxford University."}, "ia_google_scan:description"),
    ],
)
def test_google_scans_are_rejected_even_with_a_public_domain_mark(fields: dict, reason: str) -> None:
    decision = ia.decide_ia_rights(_with(licenseurl="http://creativecommons.org/publicdomain/mark/1.0/", **fields))
    assert not decision.accepted
    assert decision.reason == reason
    assert decision.source_class is None
    assert decision.evidence()["decision"] == "rejected"


@pytest.mark.parametrize("contributor", [None, "", "Anonymous", "unknown"])
def test_anonymous_uploads_are_rejected(contributor: str | None) -> None:
    decision = ia.decide_ia_rights(_with(contributor=contributor, sponsor=None, scanner="Internet Archive HTML5 Uploader 1.7.0"))
    assert not decision.accepted
    assert decision.reason == "ia_anonymous_upload_no_known_library"


@pytest.mark.parametrize(
    "fields",
    [
        {"contributor": "National Library of Israel"},
        {"source": "https://commons.wikimedia.org/wiki/File:X.pdf (from www.nli.org.il)"},
        {"description": "סריקה של הספרייה הלאומית"},
    ],
)
def test_files_from_nli_are_rejected(fields: dict) -> None:
    decision = ia.decide_ia_rights(_with(**fields))
    assert not decision.accepted
    assert decision.reason.startswith("ia_files_from_nli:")


@pytest.mark.parametrize(
    ("fields", "reason"),
    [
        ({"licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"}, "ia_licence_non_commercial:https://creativecommons.org/licenses/by-nc/4.0/"),
        ({"licenseurl": "https://creativecommons.org/licenses/by/4.0/"}, "ia_licence_not_public_domain:https://creativecommons.org/licenses/by/4.0/"),
        ({"rights": "Public domain; non-commercial use only."}, "ia_rights_restrictive"),
        ({"rights": "Contact the library for reuse."}, "ia_rights_unclear"),
        ({"possible_copyright_status": "In copyright"}, "ia_copyright_status_not_public_domain:In copyright"),
        ({"mediatype": "movies"}, "ia_not_a_printed_text:movies"),
    ],
)
def test_restrictive_or_unclear_rights_are_rejected(fields: dict, reason: str) -> None:
    decision = ia.decide_ia_rights(_with(**fields))
    assert not decision.accepted
    assert decision.reason == reason


def test_every_failed_condition_is_recorded() -> None:
    decision = ia.decide_ia_rights(_with(sponsor="Google", contributor=None, rights="All rights reserved"))
    assert decision.evidence()["failed_conditions"] == [
        "ia_google_scan:sponsor",
        "ia_anonymous_upload_no_known_library",
        "ia_rights_restrictive",
    ]
    assert decision.reason == "ia_google_scan:sponsor"


# --- canvas adapter ----------------------------------------------------------------------------------------


def test_v3_manifest_becomes_v2_shaped_canvases() -> None:
    canvases = ia.ia_v3_canvases(_manifest())
    assert len(canvases) == 3
    first = canvases[0]
    assert first["@id"] == f"https://iiif.archive.org/iiif/{IDENTIFIER}$0/canvas"
    assert isinstance(first["label"], str)
    assert first["width"] == 2242 and isinstance(first["height"], int)
    service = canvas_image_service(first)
    assert service is not None and service.startswith(f"https://iiif.archive.org/image/iiif/3/{IDENTIFIER}%2F")
    assert service.endswith(".jp2")
    # Real sizes: the aligner never asks info.json for them.
    assert tool.resolve_canvas_size(first, lambda: pytest.fail("info.json requested")) is first
    assert ia.manifest_label(_manifest()).startswith("Hegyone Shpinozah")
    assert ia.manifest_provider(_manifest()) == "The Internet Archive"


def test_v3_adapter_skips_non_canvases_and_reads_a_bare_service() -> None:
    manifest = {
        "items": [
            {"type": "Range"},
            {"type": "Canvas", "id": "c1", "label": {"he": ["א"]}, "width": 900, "height": 1200,
             "items": [{"items": [{"body": {"id": "img", "service": {"@id": "svc"}}}]}]},
        ]
    }
    canvases = ia.ia_v3_canvases(manifest)
    assert [canvas["@id"] for canvas in canvases] == ["c1"]
    assert canvases[0]["label"] == "א"
    assert canvas_image_service(canvases[0]) == "svc"


# --- the aligner's IA scan record --------------------------------------------------------------------------


def _scan() -> dict:
    record = tool.ia_scan_record(
        _metadata(),
        _manifest(),
        identifier=IDENTIFIER,
        manifest_url=ia.IA_MANIFEST_URL.format(identifier=IDENTIFIER),
        manifest_sha256="m" * 64,
        metadata_sha256="d" * 64,
    )
    assert isinstance(record, dict)
    return record


def test_ia_scan_record_carries_source_rights_fields_and_gate_evidence() -> None:
    scan = _scan()
    assert scan["source"] == "internet_archive"
    assert scan["record_id"] == scan["ia_identifier"] == IDENTIFIER
    assert scan["contributing_library"] == "Robarts - University of Toronto"
    assert scan["source_class"] == "ia_library_scan_no_licence_field"
    assert {key: scan[key] for key in ("rights", "licenseurl", "possible-copyright-status")} == dict.fromkeys(
        ("rights", "licenseurl", "possible-copyright-status")
    )
    assert scan["rights_decision"]["gate"] == ia.IA_GATE and scan["rights_decision"]["decision"] == "accepted"
    assert scan["manifest_url"] == f"https://iiif.archive.org/iiif/3/{IDENTIFIER}/manifest.json"
    assert scan["metadata_url"] == f"https://archive.org/metadata/{IDENTIFIER}"
    assert scan["canvas_count"] == 3
    assert "nli_record_id" not in scan and "license_slug" not in scan
    assert tool.scan_record_id(scan) == IDENTIFIER


def test_ia_scan_record_refuses_rejected_items_and_mismatched_ids() -> None:
    rejected = tool.ia_scan_record(_with(sponsor="Google"), _manifest(), identifier=IDENTIFIER, manifest_url="u", manifest_sha256="", metadata_sha256="")
    assert rejected == "scan rejected by the IA gate: ia_google_scan:sponsor"
    other = tool.ia_scan_record(_metadata(), _manifest(), identifier="another00item", manifest_url="u", manifest_sha256="", metadata_sha256="")
    assert isinstance(other, str) and "not 'another00item'" in other


def test_ia_report_summaries_and_review_heading() -> None:
    pby_text = "שלום עולם " * 30
    report = tool.alignment_report(
        work={"pby_id": "31623", "title": "t", "authors": "a", "source_edition": "e"},
        scan=_scan(),
        pby_text=pby_text,
        pages=[[]],
        canvases=ia.ia_v3_canvases(_manifest())[:1],
        canvas_indices=[0],
        ocr_engine="tesseract -l heb --psm 3",
        image_width=1600,
        generated_on="2026-11-09",
    )
    assert report["scan"]["source"] == "internet_archive"
    page = report["pages"][0]
    assert page["image_service"].startswith("https://iiif.archive.org/image/iiif/3/")
    compact = tool.compact_alignment(report)
    assert compact["source"] == "internet_archive" and compact["record_id"] == IDENTIFIER and "nli_record_id" not in compact
    summary = tool.pilot_summary({"captured_on": "2026-11-09", "summary": {}, "candidates": []}, [report])
    assert summary["alignment"]["scans"] == 1
    html = tool.render_report(report, image_src=lambda _: "x.jpg", pby_text=pby_text)
    assert f"IA {IDENTIFIER} (Robarts - University of Toronto; ia_library_scan_no_licence_field)" in html


def test_nli_scan_keys_and_compact_rows_are_unchanged() -> None:
    scan = {"nli_record_id": "990018546440205171", "license_slug": "public-domain-free-use"}
    report = {"work": {"pby_id": "3149", "title": "t"}, "scan": scan, "summary": {}, "pages": []}
    assert list(tool.compact_alignment(report)) == ["pby_id", "title", "nli_record_id", "summary", "pages", "page_columns"]
    assert tool.scan_record_id(scan) == "990018546440205171"
    assert tool.scan_heading(scan) == "NLI 990018546440205171 (public-domain-free-use)"


def test_align_args_accept_an_ia_source() -> None:
    args = tool.parse_args(
        ["align", "--source", "ia", "--catalogue", "c.csv", "--pby-id", "1", "--pby-text", "t", "--manifest", "m.json",
         "--ia-identifier", IDENTIFIER, "--ia-metadata", "md.json", "--work-dir", "w", "--out-dir", "o", "--generated-on", "2026-11-09"]
    )
    assert args.source == "ia" and args.ia_identifier == IDENTIFIER and args.nli_record_id is None and args.manifest_url is None
    nli = tool.parse_args(
        ["align", "--catalogue", "c.csv", "--pby-id", "1", "--pby-text", "t", "--manifest", "m.json", "--manifest-url", "u",
         "--nli-record-id", "99", "--work-dir", "w", "--out-dir", "o", "--generated-on", "2026-11-09"]
    )
    assert nli.source == "nli" and nli.ia_identifier is None
