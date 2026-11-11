"""F8g2: the Reshumot / Knesset tranche builders, the Pinkas canvas match checks and the tranche manifest."""

from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest

from hocrgen.config.loader import load_and_validate_bundle, package_root
from hocrgen.fetchers.government_print import knesset_entry_exclusion_reasons, reshumot_entry_exclusion_reasons
from hocrgen.tools import government_print_tranche as gp
from hocrgen.tools import real_tranche as tranche_tool

DATA = package_root() / "data"
CHECKS = Path(__file__).resolve().parents[1] / "docs" / "pinkas_canvas_match_checks.json"


def _entries(relative: str) -> list[dict]:
    return [json.loads(line) for line in (DATA / relative / "entries.jsonl").read_text(encoding="utf-8").splitlines()]


def _source(source_id: str):
    return next(source for source in load_and_validate_bundle().source_registry.sources if source.id == source_id)


# --- selection --------------------------------------------------------------------------------------------------


def _result(folder_type: str, booklet: str, publish: str, pages: int = 8) -> dict:
    return {"Data": {"FolderType": folder_type, "BookletNum": booklet, "PublishDate": publish, "Pages": pages, "Document": [{"FileName": "u"}]}}


def test_reshumot_selection_keeps_section_6_born_digital_short_booklets_by_seeded_hash() -> None:
    results = [
        _result("1", "2580", "2016-08-16T00:00:00"),
        _result("1", "2581", "2016-08-17T00:00:00"),
        _result("2", "9000", "2016-08-17T00:00:00"),  # ילקוט הפרסומים: not section 6
        _result("1", "1969", "2004-07-01T00:00:00"),  # before the era floor (from 2005 the PDF decides)
        _result("3", "7712", "2016-09-13T00:00:00", pages=300),  # too long
    ]
    chosen = gp.select_reshumot_booklets(results, seed="s", per_query=5, max_pages=24)
    assert {data["BookletNum"] for data in chosen} == {"2580", "2581"}
    assert gp.select_reshumot_booklets(results, seed="s", per_query=1, max_pages=24) == chosen[:1]
    assert gp.select_reshumot_booklets(list(reversed(results)), seed="s", per_query=5, max_pages=24) == chosen
    assert gp.reshumot_booklet_year_index(5776) == "84"
    assert gp.hebrew_years_since(date(2006, 1, 1), date(2026, 11, 7))[0] == 5766


def _document(doc_id: int, committee: int, start: str = "1952-11-25T10:00:00+02:00", *, kind: str = "PDF", open_session: bool = True) -> dict:
    return {
        "Id": doc_id,
        "GroupTypeID": 23,
        "ApplicationDesc": kind,
        "KNS_CommitteeSession": {"StartDate": start, "TypeDesc": "פתוחה" if open_session else "חסויה", "CommitteeID": committee, "KNS_Committee": {"Name": "ועדה"}},
    }


def test_knesset_selection_prefilters_and_spreads_over_committees() -> None:
    documents = [
        _document(1, 10),
        _document(2, 10),
        _document(3, 11),
        _document(4, 12, start="1976-01-06T10:00:00+02:00"),
        _document(5, 13, kind="DOC"),
        _document(6, 14, open_session=False),
    ]
    chosen = gp.select_knesset_documents(documents, seed="s", count=5)
    assert {doc["Id"] for doc in chosen} <= {1, 2, 3}
    assert len(chosen) == 2 and len({doc["KNS_CommitteeSession"]["CommitteeID"] for doc in chosen}) == 2
    assert len(gp.select_knesset_documents(documents, seed="s", count=1)) == 1


# --- the entry builders reproduce the F8e fixture entries ------------------------------------------------------


def test_reshumot_glyph_page_entry_rebuilds_the_packaged_entry_and_passes_the_gate() -> None:
    # F8e3: the packaged fixture is built by the same glyph-layer builder as the tranche.
    from PIL import Image

    from hocrgen.fetchers.government_print import read_glyph_layer_bytes, reshumot_page_render

    root = DATA / "reshumot" / "snapshot"
    packaged = next(entry for entry in _entries("reshumot/snapshot") if entry["entry_id"] == "sefer_hachukim_2580__p0002")
    booklet, pdf = packaged["booklet"], packaged["pdf"]
    data = {
        "BookletNum": booklet["booklet_number"],
        "BookletYear": booklet["booklet_year_index"],
        "FolderType": booklet["folder_type"],
        "ForeignYear": booklet["foreign_year"],
        "Pages": booklet["page_count"],
        "PublishDate": booklet["publish_date"] + "T00:00:00+03:00",
        "ModifyDate": packaged["upstream"]["modify_date"],
        "Document": [{"FileName": pdf["document_url"], "DisplayName": booklet["display_name"]}],
        "DocSummary": {"DescriptionHtmlString": packaged["upstream"]["doc_summary_html"]},
    }
    facts = {
        "info": {"Creator": pdf["creator"], "Producer": pdf["producer"], "CreationDate": pdf["creation_date"], "Pages": str(pdf["page_count"])},
        "fonts": pdf["embedded_fonts"],
        "sha256": pdf["sha256"],
        "bytes": pdf["bytes"],
    }
    extraction = packaged["text"]["extraction"]
    layer = json.loads(read_glyph_layer_bytes(root / extraction["raw_local_path"]))
    table = json.loads((root / extraction["outline_table_path"]).read_text(encoding="utf-8"))
    render = reshumot_page_render(packaged)
    with Image.open(root / render["local_path"]) as image:
        image.load()
        entry, logical, issues, cropped = gp.reshumot_glyph_page_entry(
            data=data, pdf=facts, page=2, page_image_count=0, layer=layer, layer_sha256=extraction["raw_sha256"], table=table,
            table_sha256=extraction["outline_table_sha256"], render_file=render, render_image=image, captured_at=packaged["rights"]["verified_at"],
        )
    assert issues == [] and cropped is None
    assert logical == (root / packaged["text"]["local_path"]).read_text(encoding="utf-8")
    assert entry == packaged
    assert entry["text"]["reading_order_verified"] == "within_line"
    assert reshumot_entry_exclusion_reasons(entry, _source("reshumot_born_digital"), root) == []
    render = gp.reshumot_render_file("x__p0002", b"png", "pix", (10, 20), page=2, poppler_version="26.07.0")
    assert render["rendering"]["is_scan"] is False and render["width_px"] == 10 and render["local_path"] == "assets/x__p0002.png"


def test_reshumot_entry_skeleton_records_born_digital_evidence_and_anchors() -> None:
    data = {
        "BookletNum": "1",
        "BookletYear": "84",
        "FolderType": "3",
        "PublishDate": "2016-09-13",
        "Document": [{"FileName": "u", "DisplayName": "d"}],
        "DocSummary": {"DescriptionHtmlString": "תקנות כלשהן 2246<br/>"},
    }
    facts = {"info": {"Creator": "Scanner", "Pages": "1"}, "fonts": [], "sha256": "0" * 64, "bytes": 1}
    entry = gp.reshumot_entry_skeleton(data=data, pdf=facts, page=1, page_image_count=1, captured_at="2026-11-07")
    assert entry["page"]["printed_page_number"] is None and entry["pdf"]["born_digital"] is False
    assert "1 page image(s)" in entry["pdf"]["born_digital_evidence"]
    assert entry["entry_id"] == "kovetz_hatakanot_1__p0001" and entry["text"]["local_path"] == "text/kovetz_hatakanot_1__p0001.txt"
    assert reshumot_entry_exclusion_reasons(entry, _source("reshumot_born_digital"), DATA / "reshumot" / "snapshot") == ["pdf_not_born_digital"]
    # An inner page is anchored by the running footer and the titles printed on it; page 2246 carries one title.
    assert [item["text"] for item in gp.reshumot_expected_phrases(data, 2, "כותרת\n2246\n")] == ["קובץ התקנות 1,", "13.9.2016", "תקנות כלשהן"]
    assert [item["text"] for item in gp.reshumot_expected_phrases(data, 2, "שלום\n")] == ["קובץ התקנות 1,", "13.9.2016"]
    assert gp.docsummary_titles("חוק א 1254<br/>   תיקונים עקיפים:<br/>") == [("חוק א", "1254")]
    assert gp.printed_page_number("כותרת\n2246\nגוף") == "2246"


def test_knesset_page_entry_rebuilds_the_packaged_f8e_entry_and_passes_the_gate() -> None:
    packaged = next(entry for entry in _entries("knesset_committees/snapshot") if entry["entry_id"] == "knesset_committee_399388__p0002")
    document, session, committee, scan = packaged["document"], packaged["session"], packaged["committee"], packaged["files"][0]["scan"]
    odata_document = {
        "Id": document["document_id"],
        "CommitteeSessionID": document["committee_session_id"],
        "GroupTypeID": document["group_type_id"],
        "GroupTypeDesc": document["group_type_desc"],
        "DocumentName": document["document_name"],
        "ApplicationDesc": document["application_desc"],
        "FilePath": document["file_url"],
        "LastUpdatedDate": document["last_updated"],
        "KNS_CommitteeSession": {
            "Id": session["committee_session_id"],
            "KnessetNum": session["knesset_num"],
            "Note": session["note"],
            "Number": session["session_number"],
            "SessionUrl": session["session_url"],
            "StartDate": session["start_date"] + "T10:00:00+02:00",
            "TypeDesc": session["type_desc"],
            "KNS_Committee": {"Id": committee["committee_id"], "Name": committee["name"]},
        },
    }
    pdf = packaged["pdf"]
    facts = {
        "info": {"CreationDate": pdf["creation_date"], "Creator": pdf["creator"], "Pages": str(pdf["page_count"]), "Producer": pdf["producer"], "Subject": pdf["subject"]},
        "sha256": pdf["sha256"],
        "bytes": pdf["bytes"],
    }
    row = ["2", "1", "image", "w", "h", "gray", "1", "1", scan["pdf_image_encoding"], "no", str(scan["pdf_image_object"]), "0", str(scan["x_ppi"]), str(scan["y_ppi"])]
    asset = DATA / "knesset_committees" / "snapshot" / packaged["files"][0]["local_path"]
    entry = gp.knesset_page_entry(
        document=odata_document, pdf=facts, page=2, image_row=row, png=asset.read_bytes(), pixel_sha256=packaged["files"][0]["pixel_sha256"],
        size=(packaged["files"][0]["width_px"], packaged["files"][0]["height_px"]), poppler_version=scan["extractor_version"],
        captured_at=packaged["rights"]["verified_at"],
    )
    entry["files"][0]["scan"]["encoder"] = scan["encoder"]  # the Pillow version of the capture machine
    assert entry == packaged
    assert knesset_entry_exclusion_reasons(entry, _source("knesset_committee_protocols_pre1976")) == []
    colour = ["3", "2", "image", "2126", "3507", "rgb", "3", "8", "jpeg", "no", "9", "0", "300", "300"]
    flate = ["6", "5", "image", "w", "h", "gray", "1", "8", "image", "no", "9", "0", "300", "300"]
    rows = [row, colour, ["4", "3", "image"] + ["x"] * 11, ["4", "4", "image"] + ["x"] * 11, flate]
    assert gp.single_scan_image_row(rows, 2) == row
    assert gp.single_scan_image_row(rows, 3) == colour  # a colour rescan's JPEG stream
    assert gp.single_scan_image_row(rows, 4) is None  # two images
    assert gp.single_scan_image_row(rows, 5) is None  # none
    assert gp.single_scan_image_row(rows, 6) is None  # an 8-bit image that is not a JPEG stream
    record = gp.knesset_scan_file("k__p0003", 3, colour, b"jpeg", "pix", (2126, 3507), poppler_version="26.07.0")
    assert record["mime_type"] == "image/jpeg" and record["local_path"] == "assets/k__p0003.jpg"
    assert record["scan"]["bits_per_pixel"] == 24 and record["scan"]["command"].endswith("-j <pdf> <out>")
    colour_entry = {**entry, "files": [record]}
    assert knesset_entry_exclusion_reasons(colour_entry, _source("knesset_committee_protocols_pre1976")) == []


# --- the committed manifest builder covers the government-print snapshots --------------------------------------


def test_manifest_items_for_reshumot_and_knesset_snapshots(tmp_path: Path) -> None:
    root = tmp_path / "tranche"
    for source_id, packaged in (("reshumot_born_digital", "reshumot"), ("knesset_committee_protocols_pre1976", "knesset_committees")):
        snapshot = root / "sources" / source_id / "snapshot"
        shutil.copytree(DATA / packaged / "snapshot", snapshot)
        gate = reshumot_entry_exclusion_reasons if packaged == "reshumot" else knesset_entry_exclusion_reasons
        kept = [entry for entry in _entries(f"{packaged}/snapshot") if not gate(entry, _source(source_id), snapshot)]
        (snapshot / "entries.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in kept), encoding="utf-8")
    tranche_tool.write_descriptor(
        root, created_at="2026-11-07",
        results={"reshumot_born_digital": {"item_count": 2, "pages_checked": 3, "pages_passed": 2}, "knesset_committee_protocols_pre1976": {"item_count": 3}},
        inputs={"fixture": True},
    )
    manifest, items = tranche_tool.build_manifest(root)
    assert manifest["sources"]["reshumot_born_digital"]["pages_passed"] == 2
    by_source = {}
    for item in items:
        by_source.setdefault(item["source_id"], []).append(item)
    assert len(by_source["reshumot_born_digital"]) == 2 and len(by_source["knesset_committee_protocols_pre1976"]) == 3
    assert all(item["text"]["path"].startswith("text/") for item in by_source["reshumot_born_digital"])
    assert all(item["text"] is None for item in by_source["knesset_committee_protocols_pre1976"])
    # F8e3: Reshumot items say their line text is verified and their page order is not; image-only items say nothing.
    assert {item["reading_order_verified"] for item in by_source["reshumot_born_digital"]} == {"within_line"}
    assert not any("reading_order_verified" in item for item in by_source["knesset_committee_protocols_pre1976"])
    assert {item["source_group"] for item in by_source["knesset_committee_protocols_pre1976"]} == {"knesset_committee:399388", "knesset_committee:430997"}
    assert by_source["reshumot_born_digital"][0]["source_group"] == "reshumot:sefer_hachukim:2580"


# --- Pinkas canvas match checks --------------------------------------------------------------------------------


def test_committed_pinkas_checks_cover_every_page_and_record_each_status() -> None:
    payload = json.loads(CHECKS.read_text(encoding="utf-8"))
    checks = tranche_tool.load_pinkas_checks(CHECKS)
    assert len(checks) == 30 == payload["summary"]["pages"]
    verified = sorted(page for page, check in checks.items() if check["status"] == "verified")
    assert verified == ["Page 105_1", "Page 105_2", "Page 112_1", "Page 112_2", "Page 134_1", "Page 134_2"]
    assert payload["summary"] == {"pages": 30, "verified": 6, "not_verified": 24, "mismatches": 0}
    for page, check in checks.items():
        number, half = page.removeprefix("Page ").split("_")
        assert check["canvas_label"] == f"Page {number}"
        assert check["canvas_region"] == ("right_half" if half == "1" else "left_half")
        assert check["checked_by"] == "agent" and check["method"] in payload["methods"] and check["checked_at"]
        assert (check["status"] == "verified") == ("nli_image_sha256" in check)
        assert check["status"] == "verified" or check["reason"] == "nli_image_not_cached_and_iiif_unavailable"
    fields = tranche_tool.pinkas_match_scan_fields(checks["Page 105_2"], number=105, side="left")
    assert fields["match_check"]["status"] == "verified" and "left half" in fields["match_method"]
    fields = tranche_tool.pinkas_match_scan_fields(checks["Page 107_1"], number=107, side="right")
    assert fields["match_check"]["reason"] == "nli_image_not_cached_and_iiif_unavailable"
    assert "not visually verified" in fields["match_method"]


def test_pinkas_checks_loader_refuses_another_schema(tmp_path: Path) -> None:
    path = tmp_path / "checks.json"
    path.write_text(json.dumps({"schema": "other", "checks": []}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="pinkas_canvas_match_checks"):
        tranche_tool.load_pinkas_checks(path)


# --- wikisource_plain_text.v3: broken-link fragments (#134) ----------------------------------------------------

from hocrgen.fetchers.wikisource import PageText, text_derivation  # noqa: E402
from hocrgen.parsers.wikitext import WIKITEXT_NORMALIZATION_VERSION, convert_wikitext, repair_broken_links  # noqa: E402
from hocrgen.tools.wikisource_render_check import compare  # noqa: E402

# Each case: the wikitext fragment an editor left (from the pinned page), MediaWiki's visible rendering of it (the
# captured action=parse HTML), and what the page prints (checked on the 960 px render, F8g2).
BROKEN_LINK_CASES = [
    (  # Hyman I p. 44: a doubled pipe
        'מחלוקתם מצינו [[מועד קטן כו ב||מו"ק כו:]], ע"ז',
        'מחלוקתם מצינו <a href="/wiki/x" title="מועד קטן כו ב">|מו"ק כו:</a>, ע"ז',
        'מחלוקתם מצינו מו"ק כו:, ע"ז',
        "broken_link_double_pipe",
    ),
    (  # Hyman I p. 414: an unopened link
        "וכו', וכן כתובות סא א|שם סא.]] הוו יתבי",
        "וכו', וכן כתובות סא א|שם סא.]] הוו יתבי",
        "וכו', וכן שם סא. הוו יתבי",
        "broken_link_unopened",
    ),
    (  # Hyman II p. 239: an unclosed link
        'ובירושלמי [[ירושלמי כתובות ט ב|כתובות פ"ט סה"ב]] ו[[ירושלמי קידושין א ד|קידושין פ"א ה"ד איתא בפירוש',
        'ובירושלמי <a href="/wiki/y">כתובות פ"ט סה"ב</a> ו[[ירושלמי קידושין א ד|קידושין פ"א ה"ד איתא בפירוש',
        'ובירושלמי כתובות פ"ט סה"ב וקידושין פ"א ה"ד איתא בפירוש',
        "broken_link_unclosed",
    ),
    (  # Sefer Arakhim p. 11: an unopened link inside brackets
        'בהם" <small>(יומא פה ב|יומא פ"ה, ע"ב]])</small>, שלא',
        'בהם" <small>(יומא פה ב|יומא פ"ה, ע"ב]])</small>, שלא',
        'בהם" (יומא פ"ה, ע"ב), שלא',
        "broken_link_unopened",
    ),
]


@pytest.mark.parametrize(("wikitext", "mediawiki_html", "printed", "feature"), BROKEN_LINK_CASES)
def test_v3_renders_the_label_of_a_broken_link_as_printed(wikitext: str, mediawiki_html: str, printed: str, feature: str) -> None:
    conversion = convert_wikitext(wikitext)
    assert WIKITEXT_NORMALIZATION_VERSION == "wikisource_plain_text.v3"
    assert conversion.text == printed
    assert conversion.features[feature] == 1
    # The render check tolerates exactly this departure from MediaWiki's literal rendering.
    result = compare(wikitext, f"<p>{mediawiki_html}</p>")
    assert result["tokens_equal"], (result["ours"], result["theirs"])


def test_v3_leaves_other_pipes_and_brackets_alone() -> None:
    # A stray pipe that is no link (the Pri Megadim p. 244 fragment) is not repaired: that page is text_not_on_page.
    assert convert_wikitext('וממילא "הלכות פסח| היינו').text == 'וממילא "הלכות פסח| היינו'
    # An unopened fragment whose target is not a reference shape keeps the label and target; the brackets go.
    conversion = convert_wikitext("ראה כאן|שם]] והלאה")
    assert conversion.text == "ראה כאן|שם והלאה" and conversion.features["malformed_markup"] == 1
    assert "broken_link_unopened" not in conversion.features
    assert repair_broken_links("טקסט רגיל") == "טקסט רגיל"
    # Well-formed links are unchanged from v2.
    assert convert_wikitext("[[ברכות ל א|ברכות ל.]] ו[[שבת]]").text == "ברכות ל. ושבת"


def test_text_derivation_records_every_step() -> None:
    conversion = convert_wikitext("וכן כתובות סא א|שם סא.]] הוו")
    derived = PageText(
        faithful=conversion,
        conversion=conversion,
        text=conversion.text,
        adjustments={"converted_text_sha256": "x", "unprinted_notes": [2], "editor_standins": [{"mapping_id": "typed_pipe_as_paseq.v1", "stand_in": "|", "printed": "׀", "count": 3}]},
    )
    assert text_derivation(derived) == {
        "converter": "wikisource_plain_text.v3",
        "converter_repairs": {"broken_link_unopened": 1},
        "unprinted_notes_dropped": [2],
        "editor_standins_applied": [{"mapping_id": "typed_pipe_as_paseq.v1", "count": 3}],
    }
    plain = PageText(faithful=convert_wikitext("שלום"), conversion=convert_wikitext("שלום"), text="שלום", adjustments=None)
    assert text_derivation(plain) == {"converter": "wikisource_plain_text.v3", "converter_repairs": {}, "unprinted_notes_dropped": [], "editor_standins_applied": []}
