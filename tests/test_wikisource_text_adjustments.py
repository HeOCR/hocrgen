"""F8b7: unprinted footnotes, editors' stand-ins and text not visible on the scan (network- and engine-free)."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.wikisource import (
    WikisourceProofreadImporter,
    apply_editor_standins,
    derive_page_text,
    editor_standin_problems,
    editor_standins_for,
    excluded_span_problems,
    load_wikisource_snapshot,
    page_attestation,
    page_exclusion_reasons,
    page_reference_record,
    page_text,
    page_transclusions,
    reference_normalization,
)
from hocrgen.parsers.wikitext import convert_wikitext, footnote_spans
from hocrgen.reference_evaluation import NORMALIZATION_PROFILES, reference_text
from hocrgen.tools import wikisource_coverage as wc
from hocrgen.tools import wikisource_inventory as inv
from hocrgen.tools.wikisource_render_check import drop_note_list_headings

SNAPSHOT_ROOT = package_root() / "data" / "wikisource" / "snapshot"
SELIHOT = "selihot_baer_1885__p0034"
PASEQ = "׀"
HEADER = '<noinclude><pagequality level="3" user="X" /></noinclude>'


def _snapshot(root: Path = SNAPSHOT_ROOT):
    _, indexes, pages = load_wikisource_snapshot(root)
    return indexes, {page["source_item_id"]: page for page in pages}


def _copy(tmp_path: Path) -> Path:
    root = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT_ROOT, root)
    return root


def _rewrite(root: Path, page: dict) -> None:
    path = root / "pages.jsonl"
    pages = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    path.write_text("".join(json.dumps(page if one["source_item_id"] == page["source_item_id"] else one, ensure_ascii=False) + "\n" for one in pages), encoding="utf-8")


# --- unprinted footnotes (HeOCR/hocrgen#130.1) ------------------------------------------------------------------


def test_an_unprinted_note_is_dropped_with_its_mark_and_the_rest_renumbered() -> None:
    wikitext = HEADER + "גוף{{הערה|הערה מודפסת}} ועוד<ref>הערת עורך שאינה חתומה</ref> וסוף{{הערה|עוד הערה מודפסת}}."
    faithful = convert_wikitext(wikitext)
    assert faithful.text == "גוף[1] ועוד[2] וסוף[3].\n\n[1] הערה מודפסת\n[2] הערת עורך שאינה חתומה\n[3] עוד הערה מודפסת"
    spans = footnote_spans(faithful.text)
    assert [number for number, _, _ in spans] == [1, 2, 3] and spans[-1][2] == len(faithful.text)
    assert [faithful.text[start:end].strip() for _, start, end in spans] == ["[1] הערה מודפסת", "[2] הערת עורך שאינה חתומה", "[3] עוד הערה מודפסת"]
    dropped = convert_wikitext(wikitext, unprinted_notes=[2])
    assert dropped.text == "גוף[1] ועוד וסוף[2].\n\n[1] הערה מודפסת\n[2] עוד הערה מודפסת"
    assert dropped.features == {"footnotes": 2, "unprinted_notes_dropped": 1}
    assert convert_wikitext(wikitext, unprinted_notes=[1, 2, 3]).text == "גוף ועוד וסוף."
    with pytest.raises(ValueError, match="not a footnote"):
        convert_wikitext(wikitext, unprinted_notes=[4])
    with pytest.raises(ValueError, match="no notes"):
        convert_wikitext(HEADER + "גוף בלי הערות", unprinted_notes=[1])
    # a note the editor signed is dropped first, so numbers are those of the faithful conversion
    signed = HEADER + "א{{הערה|הערה מודפסת}} ב{{הערה|ויקיעורך: הערה}} ג{{הערה|הערת עורך}}"
    assert convert_wikitext(signed).text.endswith("[1] הערה מודפסת\n[2] הערת עורך")
    assert convert_wikitext(signed, unprinted_notes=[2]).text == "א[1] ב ג\n\n[1] הערה מודפסת"


def test_footnote_spans_find_the_last_numbered_block() -> None:
    assert footnote_spans("גוף בלי הערות") == []
    text = "[1] שורה שנראית כהערה\n\nגוף[1]\n\n[1] הערה\n[2] שנייה\n\nזנב"
    spans = footnote_spans(text)
    assert [number for number, _, _ in spans] == [1, 2]
    assert text[spans[0][1]:spans[0][2]] == "[1] הערה\n" and text[spans[1][1]:spans[1][2]] == "[2] שנייה"


def test_an_editors_heading_over_the_footnote_list_is_dropped() -> None:
    wikitext = HEADER + "גוף<ref>הערה</ref>\n==הערות שוליים==\n{{הערות שוליים}}"
    conversion = convert_wikitext(wikitext)
    assert conversion.text == "גוף[1]\n\n[1] הערה"
    assert conversion.features["editor_headings_dropped"] == 1
    assert convert_wikitext(HEADER + "גוף<ref>הערה</ref>\n==הערות==\n<references/>").text == "גוף[1]\n\n[1] הערה"
    # a heading with other text after it, or another heading, is the page's own and stays
    kept = convert_wikitext(HEADER + "גוף<ref>הערה</ref>\n==הערות==\nמשפט של העורכים.\n{{הערות שוליים}}")
    assert "הערות" in kept.text.split("\n") and "editor_headings_dropped" not in kept.features
    assert drop_note_list_headings(["גוף[1]", "הערות שוליים", "[1] הערה"]) == ["גוף[1]", "[1] הערה"]
    assert drop_note_list_headings(["הערות", "גוף"]) == ["הערות", "גוף"]


def _lines(texts: list[str], *, start_row: int = 0, x0: int = 100) -> list[wc.OcrLine]:
    return [
        wc.OcrLine(key=(1, 1, row), box=(x0, 100 + row * 40, 860, 124 + row * 40), words=len(text.split()), confidence=85.0,
                   chars=wc.alignment_string(text))
        for row, text in enumerate(texts, start=start_row)
    ]


BODY = [
    "אמר רבי יוחנן כל המתפלל צריך שיכוין את לבו",
    "ולמה כתב מבראשית להודיע כח גבורתו לעמו",
    "שנאמר כח מעשיו הגיד לעמו לתת להם נחלת גוים",
    "אמר ריש לקיש כביכול דבר היה מפי הקדוש ברוך הוא",
]
PRINTED_NOTE = "בכתב יד רומי נוסף כאן מאמר אחר שאינו בדפוס"
EDITOR_NOTE = "ועיין בילקוט שמעוני רמז שמביא גרסא אחרת"


def test_footnote_presence_locates_printed_notes_and_flags_the_others() -> None:
    text = "\n".join(BODY) + f"[1] [2]\n\n[1] {PRINTED_NOTE}\n[2] {EDITOR_NOTE}"
    notes = footnote_spans(text)
    ocr = _lines([*BODY, PRINTED_NOTE])
    alignments, _ = wc.align_page(ocr, text)
    result = wc.footnote_presence(alignments, text, notes)
    assert result["status"] == "flagged" and result["flagged"] == [2]
    assert [note["status"] for note in result["notes"]] == ["located", "unlocated"]
    assert result["band_text_lines"] == 1 and result["method"] == wc.FOOTNOTE_METHOD
    # no note on the page and nothing printed below the body: every note is flagged, short ones too
    short = "\n".join(BODY) + "[1]\n\n[1] צ\"ל כן"
    alignments, _ = wc.align_page(_lines(BODY), short)
    banded = wc.footnote_presence(alignments, short, footnote_spans(short))
    assert banded["status"] == "flagged" and banded["notes"][0]["status"] == "no_footnote_band"
    # a short note with text-bearing lines below the body cannot be checked
    alignments, _ = wc.align_page(_lines([*BODY, "שורה אחרת שאינה בטקסט כלל ועיקר"]), short)
    assert wc.footnote_presence(alignments, short, footnote_spans(short))["status"] == "unchecked"
    assert wc.footnote_presence(alignments, "\n".join(BODY), []) is None
    # no OCR or page text in the result
    assert PRINTED_NOTE not in json.dumps(result, ensure_ascii=False)


def test_a_flagged_footnote_holds_the_page_until_an_agent_reviews_it() -> None:
    indexes, pages = _snapshot()
    page = copy.deepcopy(pages[SELIHOT])
    page["footnote_check"] = {"status": "flagged", "flagged": [1]}
    assert "footnote_not_located" in page_exclusion_reasons(page, indexes, SNAPSHOT_ROOT)
    page["footnotes_reviewed"] = True
    assert "footnote_not_located" not in page_exclusion_reasons(page, indexes, SNAPSHOT_ROOT)


def test_an_unprinted_note_changes_the_pair_text_but_not_the_raw_checksum(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    indexes, pages = _snapshot(root)
    page = pages["bostenay_lehmann_1872__p0047"]
    wikitext_path = root / page["wikitext_path"]
    wikitext = wikitext_path.read_text(encoding="utf-8")
    body_end = wikitext.rindex("<noinclude>")
    wikitext = wikitext[:body_end] + "<ref>הערת עורך</ref>" + wikitext[body_end:]
    wikitext_path.write_text(wikitext, encoding="utf-8")
    page["wikitext_sha256"] = hashlib.sha256(wikitext.encode()).hexdigest()
    faithful = convert_wikitext(wikitext).text
    page["text_sha256"] = hashlib.sha256(faithful.encode()).hexdigest()
    page["unprinted_notes"] = [{"note": 1, "detail": "an editor's note"}]
    derived = derive_page_text(wikitext, page_transclusions(page, root), page)
    assert derived.faithful.text == faithful and "[1]" not in derived.text
    assert derived.adjustments == {"converted_text_sha256": page["text_sha256"], "unprinted_notes": [1], "editor_standins": []}
    # the page must record the adjustment it derives
    assert "text_adjustment_mismatch" in page_exclusion_reasons(page, indexes, root)
    page["text_adjustments"] = derived.adjustments
    page["text_sha256"] = hashlib.sha256(derived.text.encode()).hexdigest()
    (root / page["text_path"]).write_text(derived.text + "\n", encoding="utf-8")
    assert not page_exclusion_reasons(page, indexes, root)
    page["unprinted_notes"] = [{"note": 2, "detail": "no such note"}]
    assert page_exclusion_reasons(page, indexes, root) == ["text_adjustment_invalid"]


# --- editors' stand-ins (HeOCR/hocrgen#111) ---------------------------------------------------------------------


def test_the_packaged_stand_in_mapping_is_reviewed_and_applies_between_words_only() -> None:
    mappings = json.loads((package_root() / "data" / "wikisource" / "editor_standins.json").read_text(encoding="utf-8"))["mappings"]
    assert [mapping["mapping_id"] for mapping in mappings] == ["typed_pipe_as_paseq.v1"]
    assert all(not editor_standin_problems(mapping) for mapping in mappings)
    assert mappings[0]["printed"] == PASEQ and mappings[0]["checked_by"] == "agent" and mappings[0]["verified"]
    assert editor_standin_problems({"mapping_id": "x", "stand_in": "ab", "printed": "c", "context": "anywhere"}) == [
        "missing files", "missing checked_by", "missing checker", "missing checked_at", "missing method",
        "context must be one of between_hebrew_words", "stand_in and printed must be single characters",
        "a mapping must list the occurrences verified on page images",
    ]
    text = "עָרוּ | עָרוּ עַד הַיְסוֹד קוּמָה| יְהֹוָה 1|2 a | b |אֶחָד"
    mapped, applied = apply_editor_standins(text, mappings)
    assert mapped == f"עָרוּ {PASEQ} עָרוּ עַד הַיְסוֹד קוּמָה{PASEQ} יְהֹוָה 1|2 a | b |אֶחָד"
    assert applied == [{"mapping_id": "typed_pipe_as_paseq.v1", "stand_in": "|", "printed": PASEQ, "count": 2}]
    assert editor_standins_for({"page_title": "עמוד:Bostenay - Meir Leheman.pdf/47"}) == []
    assert editor_standins_for({"page_title": "עמוד:The Seliḥot for the Entire Year.pdf/34"}) == mappings


def test_selihot_paseq_is_the_printed_character_and_the_raw_checksum_is_kept() -> None:
    """Psalms 137:7 is typed with {{!}}; the page prints a paseq (U+05C0)."""

    indexes, pages = _snapshot()
    page = pages[SELIHOT]
    wikitext = (SNAPSHOT_ROOT / page["wikitext_path"]).read_text(encoding="utf-8")
    assert "עָרוּ {{!}} עָרוּ" in wikitext
    faithful = convert_wikitext(wikitext).text
    assert "עָרוּ | עָרוּ" in faithful
    derived = page_text(page, SNAPSHOT_ROOT)
    assert f"עָרוּ {PASEQ} עָרוּ" in derived.text and "|" not in derived.text
    assert page["text_adjustments"] == {
        "converted_text_sha256": hashlib.sha256(faithful.encode()).hexdigest(),
        "unprinted_notes": [],
        "editor_standins": [{"mapping_id": "typed_pipe_as_paseq.v1", "stand_in": "|", "printed": PASEQ, "count": 1}],
    }
    assert page["text_sha256"] == hashlib.sha256(derived.text.encode()).hexdigest()
    assert (SNAPSHOT_ROOT / page["text_path"]).read_text(encoding="utf-8") == derived.text + "\n"
    # the validator saw the faithful rendering: the mapping keeps the page adjudication-eligible
    assert page_attestation(page)["adjudication_eligible"] is True
    assert not page_exclusion_reasons(page, indexes, SNAPSHOT_ROOT)
    # a page that does not record the mapping its Index has is caught
    stale = {key: value for key, value in page.items() if key != "text_adjustments"}
    assert page_exclusion_reasons(stale, indexes, SNAPSHOT_ROOT) == ["text_adjustment_mismatch"]
    # primary.v1 keeps | and the paseq apart: they are not silently conflated
    primary = NORMALIZATION_PROFILES["primary.v1"]
    assert primary.apply("עָרוּ | עָרוּ") != primary.apply(f"עָרוּ {PASEQ} עָרוּ")


def test_discovery_records_the_adjustment_provenance() -> None:
    from hocrgen.config.loader import load_and_validate_bundle

    bundle = load_and_validate_bundle()
    source = next(one for one in bundle.source_registry.sources if one.id == "wikisource_he_proofread")
    importer = WikisourceProofreadImporter()
    options = StageOptions()
    enriched = {item.source_item_id: item for item in importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)}
    metadata = enriched[SELIHOT].metadata
    assert metadata["text_adjustments"]["editor_standins"][0]["printed"] == PASEQ
    assert metadata["converted_text_sha256"] == metadata["text_adjustments"]["converted_text_sha256"] != metadata["page_text_sha256"]
    assert enriched["bostenay_lehmann_1872__p0047"].metadata["text_adjustments"] is None
    assert enriched["bostenay_lehmann_1872__p0047"].metadata["converted_text_sha256"] == enriched["bostenay_lehmann_1872__p0047"].metadata["page_text_sha256"]


# --- text not visible on the scan (HeOCR/hocrgen#130.3) ------------------------------------------------------------


def _with_spans(root: Path) -> tuple[dict, dict, str]:
    indexes, pages = _snapshot(root)
    page = pages[SELIHOT]
    text = page_text(page, root).text
    start = text.index("עָרוּ")
    page["excluded_spans"] = {
        "text_sha256": page["text_sha256"],
        "spans": [{"kind": "illegible_on_scan", "start": start, "end": start + len("עָרוּ"), "regions_normalized": [[0.2, 0.3, 0.6, 0.35]],
                   "detail": "an ink blot covers the word", "checked_by": "agent", "checker": "a", "checked_at": "2026-11-06"}],
    }
    return indexes, page, text


def test_an_illegible_span_is_kept_in_the_reference_and_excluded_from_primary_scoring(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    indexes, page, text = _with_spans(root)
    assert not page_exclusion_reasons(page, indexes, root)
    facts = reference_normalization(page_text(page, root).conversion, page)
    assert facts["excluded_spans"] == [{"kind": "illegible_on_scan", "start": page["excluded_spans"]["spans"][0]["start"],
                                        "end": page["excluded_spans"]["spans"][0]["end"], "regions_normalized": [[0.2, 0.3, 0.6, 0.35]],
                                        "coordinate_frame": "page", "detail": "an ink blot covers the word"}]
    record = page_reference_record("wikisource_he_proofread", page, root)
    assert record.pages[0].text == text
    [span] = record.spans
    assert (span.status, span.scoring) == ("illegible", "exclude_primary")
    line = next(one for one in record.lines if one.line_id == span.line_id)
    assert line.text[span.start:span.end] == "עָרוּ"
    scoped = reference_text(record)
    assert scoped.count("עָרוּ") == text.count("עָרוּ") - 1


def test_excluded_spans_must_be_pinned_to_the_pair_text_and_located(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    indexes, page, text = _with_spans(root)
    assert excluded_span_problems(page, text) == []
    moved = copy.deepcopy(page)
    moved["excluded_spans"]["text_sha256"] = "0" * 64
    assert page_exclusion_reasons(moved, indexes, root) == ["excluded_span_invalid"]
    bad = copy.deepcopy(page)
    span = bad["excluded_spans"]["spans"][0]
    span.update({"end": len(text) + 5, "regions_normalized": [], "detail": " ", "kind": "stain"})
    assert excluded_span_problems(bad, text) == [
        "span kind must be one of illegible_on_scan", "span offsets must lie in the text",
        "a span must be located on the page by one or more boxes", "a span must say why the text is not visible",
    ]
    across = copy.deepcopy(page)
    across["excluded_spans"]["spans"][0].update({"start": 0, "end": text.index("\n") + 2})
    assert excluded_span_problems(across, text) == ["a span must be non-blank text within one line"]


# --- page checks: text reviews --------------------------------------------------------------------------------


BASE = {"page_title": "עמוד:X.pdf/1", "revision_id": 5, "commons_file_sha1": "abc", "scan_page": 1, "checked_at": "2026-11-06"}
TOOL = {**BASE, "checked_by": "tool", "checker": "t", "method": "m", "transcription_coverage": "full_page", "outcome": "decided",
        "crop": {"status": "unresolved", "reason": "transcription_not_located"}, "footnotes": {"status": "flagged", "flagged": [1, 2]}}
REVIEW = {**BASE, "checked_by": "agent", "checker": "a", "method": "agent_text_review_960px", "footnotes_reviewed": True,
          "unprinted_notes": [{"note": 2, "detail": "an editor's remark"}],
          "excluded_spans_text_sha256": "f" * 64,
          "excluded_spans": [{"kind": "illegible_on_scan", "start": 3, "end": 9, "regions_normalized": [[0.1, 0.2, 0.3, 0.25]], "detail": "a blot"}]}


def test_a_text_review_travels_with_the_deciding_check() -> None:
    payload = {"schema_version": inv.PAGE_CHECKS_SCHEMA_VERSION, "checks": [TOOL, REVIEW]}
    assert inv.is_text_review(REVIEW) and not inv.is_text_review(TOOL)
    selected = inv.select_page_checks(payload)["עמוד:X.pdf/1"]
    assert selected["checked_by"] == "tool" and selected["text_review"]["checker"] == "a"
    page = {"revision_id": 5}
    provenance = inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, selected)
    assert provenance["applied"] and page["transcription_coverage"] == "full_page"
    assert page["footnote_check"] == TOOL["footnotes"] and page["footnotes_reviewed"] is True
    assert page["unprinted_notes"] == [{"note": 2, "detail": "an editor's remark"}]
    assert page["excluded_spans"]["text_sha256"] == "f" * 64 and page["excluded_spans"]["spans"][0]["checked_by"] == "agent"
    assert page["transcription_coverage_check"]["text_review"]["method"] == "agent_text_review_960px"
    # a text review alone decides nothing; a stale one is not applied
    assert inv.select_page_checks({"schema_version": inv.PAGE_CHECKS_SCHEMA_VERSION, "checks": [REVIEW]}) == {}
    stale = {**selected, "text_review": {**REVIEW, "revision_id": 4}}
    page = {"revision_id": 5}
    inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, stale)
    assert "footnotes_reviewed" not in page and "unprinted_notes" not in page
    # a text review may also find words the page does not show
    flagged = {**selected, "text_review": {**REVIEW, "text_not_on_page": "an editor's emendation"}}
    page = {"revision_id": 5}
    inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, flagged)
    assert page["text_not_on_page"] == "an editor's emendation"


def test_text_review_fields_are_validated() -> None:
    assert inv.page_check_problems(REVIEW) == []
    assert inv.page_check_problems({**TOOL, "unprinted_notes": [{"note": 1, "detail": "x"}]}) == ["only an agent or human check records unprinted_notes"]
    assert inv.page_check_problems({**TOOL, "footnotes": {"status": "flagged", "flagged": []}}) == [
        "a flagged footnote check lists its flagged notes, and only a flagged one does"]
    assert inv.page_check_problems({**TOOL, "footnotes": {"status": "maybe"}}) == ["footnote check status must be one of flagged, located, unchecked"]
    bad = {**REVIEW, "footnotes_reviewed": False, "unprinted_notes": [{"note": 0}], "excluded_spans_text_sha256": "x",
           "excluded_spans": [{"kind": "illegible_on_scan", "start": 5, "end": 5, "regions_normalized": [[0.5, 0.5, 0.4, 0.6]], "detail": ""}]}
    assert inv.page_check_problems(bad) == [
        "unprinted_notes needs footnotes_reviewed",
        "an unprinted note needs its number",
        "excluded_spans needs excluded_spans_text_sha256, the pair text they are offsets into",
        "an excluded span needs character offsets start < end",
        "an excluded span needs one or more boxes inside the page",
        "an excluded span must say, in words, why the text is not visible",
    ]
    assert inv.page_check_problems({**REVIEW, "unprinted_notes": [{"note": 1, "detail": " "}], "excluded_spans": [{"kind": "x"}]}) == [
        "an unprinted note must say, in words, what it is", "an excluded span's kind must be one of illegible_on_scan"]


def test_the_inventory_pins_the_adjusted_pair_text(tmp_path: Path) -> None:
    root = _copy(tmp_path)
    _, pages = _snapshot(root)
    page = copy.deepcopy(pages[SELIHOT])
    page.pop("text_adjustments")
    faithful = convert_wikitext((root / page["wikitext_path"]).read_text(encoding="utf-8")).text
    page["text_sha256"] = hashlib.sha256(faithful.encode()).hexdigest()
    (root / page["text_path"]).write_text(faithful + "\n", encoding="utf-8")
    adjustments = inv.apply_text_adjustments(page, root)
    assert adjustments["editor_standins"][0]["count"] == 1
    assert PASEQ in (root / page["text_path"]).read_text(encoding="utf-8")
    assert page["text_sha256"] == pages[SELIHOT]["text_sha256"]
    other = copy.deepcopy(pages["bostenay_lehmann_1872__p0047"])
    other["text_adjustments"] = {"stale": True}
    assert inv.apply_text_adjustments(other, root) is None and "text_adjustments" not in other
    broken = {**other, "unprinted_notes": [{"note": 9, "detail": "x"}]}
    assert inv.apply_text_adjustments(broken, root) is None


def test_committed_f8b7_checks_cover_every_flagged_footnote_and_hold_no_page_text() -> None:
    checks = json.loads(Path("docs/wikisource_page_checks.json").read_text(encoding="utf-8"))
    tool = json.loads(Path("docs/wikisource_page_tool_checks.json").read_text(encoding="utf-8"))
    selected = inv.load_page_checks([Path("docs/wikisource_page_checks.json"), Path("docs/wikisource_page_tool_checks.json")])
    flagged = {check["page_title"] for check in tool["checks"] if (check.get("footnotes") or {}).get("status") == "flagged"}
    assert flagged
    for title in flagged:
        chosen = selected[title]
        facts = chosen.get("text_review") or chosen
        assert facts.get("footnotes_reviewed"), title
    korfu = [c for c in checks["checks"] if c["method"] == "agent_tool_verdict_spot_check_960px"]
    assert len(korfu) >= 30 and all(c["transcription_coverage"] == "full_page" for c in korfu)
    for check in checks["checks"]:
        for note in check.get("unprinted_notes") or []:
            assert set(note) == {"note", "detail"}
