"""F8b4: transcription coverage and crops located by aligning the human text to OCR boxes (network- and engine-free)."""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

from hocrgen.tools import wikisource_coverage as wc
from hocrgen.tools import wikisource_inventory as inv

LINES = [
    "אמר רבי יוחנן כל המתפלל צריך שיכוין את לבו",
    "ולמה כתב מבראשית להודיע כח גבורתו לעמו",
    "שנאמר כח מעשיו הגיד לעמו לתת להם נחלת גוים",
    "אמר ריש לקיש כביכול דבר היה מפי הקדוש ברוך הוא",
    "ואלא ליפרע מן הרשעים שמאבדין את העולם שנברא בעמל",
    "וליתן שכר טוב לצדיקים שמקיימין את העולם שנברא",
]
NOTES = [
    "הערות ותקונים מסורת הש״ס כתב יד אוקספורד",
    "בכתב יד רומי נוסף כאן מאמר אחר שאינו בדפוס",
    "ועיין בילקוט שמעוני רמז ב׳ שמביא גרסא אחרת",
    "וכן הוא בלקח טוב ובשכל טוב על התורה",
]


def _misread(text: str, rate: float, seed: int) -> str:
    """OCR-like noise: substitute a share of the letters."""

    rng = random.Random(seed)
    return "".join(rng.choice("אבגדהוזחטיכלמנסעפצקרשת") if ch != " " and rng.random() < rate else ch for ch in text)


def _line(text: str, row: int, *, x0: int = 100, x1: int = 860, height: int = 24) -> wc.OcrLine:
    top = 120 + row * 36
    return wc.OcrLine(key=(1, 1, row), box=(x0, top, x1, top + height), words=len(text.split()), confidence=80.0, chars=wc.alignment_string(text))


def _page(lines: list[str], extra: list[str] | None = None, *, rate: float = 0.08) -> list[wc.OcrLine]:
    ocr = [_line(_misread(text, rate, row), row) for row, text in enumerate(lines)]
    start = len(lines) + 1
    ocr += [_line(_misread(text, rate, 100 + row), start + row) for row, text in enumerate(extra or [])]
    return ocr


def test_alignment_normalisation_drops_marks_finals_and_footnote_numbers() -> None:
    assert wc.alignment_tokens("בְּרֵאשִׁית בָּרָא[1] אֱלֹהִים, ﬠולם!") == ["בראשית", "ברא", "אלהימ", "עולמ"]
    assert wc.alignment_string("Cap. V.") == "capv"


def test_tesseract_tsv_lines_group_words_and_keep_reading_order() -> None:
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    rows = [
        "5\t1\t1\t1\t1\t1\t500\t10\t40\t20\t90\tבראשית",
        "5\t1\t1\t1\t1\t2\t440\t12\t50\t20\t70\tברא",
        "5\t1\t1\t1\t2\t1\t480\t40\t60\t20\t80\tאלהים",
        "5\t1\t2\t1\t1\t1\t480\t90\t60\t20\t95\t ",
        "4\t1\t1\t1\t1\t0\t440\t10\t100\t22\t-1\t",
    ]
    lines = wc.parse_tesseract_tsv("\n".join([header, *rows]) + "\n")
    assert [line.key for line in lines] == [(1, 1, 1), (1, 1, 2)]
    assert lines[0].box == (440, 10, 540, 32) and lines[0].words == 2 and lines[0].chars == "בראשיתברא"
    assert lines[0].confidence == 80.0


def test_full_page_when_every_text_line_aligns() -> None:
    reference = "\n".join(LINES)
    alignments, normalised = wc.align_page(_page(LINES), reference)
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400)
    assert assessment["outcome"] == "decided" and assessment["transcription_coverage"] == "full_page"
    assert assessment["missing"] is None
    assert assessment["alignment"]["reference_located_share"] > 0.8


def test_partial_page_crops_to_the_transcribed_lines() -> None:
    reference = "\n".join(LINES)
    alignments, normalised = wc.align_page(_page(LINES, NOTES), reference)
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400)
    assert assessment["transcription_coverage"] == "partial_page"
    assert "below the transcribed region" in assessment["missing"]
    crop = assessment["crop"]
    assert crop["status"] == "resolved" and crop["method"] == wc.CROP_METHOD
    x0, y0, x1, y1 = crop["box_render_px"]
    transcribed_bottom = 120 + (len(LINES) - 1) * 36 + 24
    notes_top = 120 + (len(LINES) + 1) * 36
    assert y0 <= 120 and transcribed_bottom <= y1 < notes_top  # all transcribed lines in, the notes out
    assert crop["untranscribed_inside"] == [] and 0 < crop["box_normalized"][3] < 1


def test_misread_lines_between_aligned_lines_are_interpolated() -> None:
    ocr = _page(LINES)
    ocr[2] = _line(_misread(LINES[2], 0.7, 7), 2)  # OCR garbles one line in the middle
    alignments, normalised = wc.align_page(ocr, "\n".join(LINES))
    assert alignments[2].status == "interpolated"
    assert wc.assess_page(alignments, len(normalised), 960, 1400)["transcription_coverage"] == "full_page"


def test_running_heads_and_page_numbers_are_furniture() -> None:
    ocr = [wc.OcrLine((0, 0, 0), (400, 60, 560, 84), 2, 85.0, wc.alignment_string("מדרש תנחומא"))]
    ocr += _page(LINES)
    ocr.append(wc.OcrLine((9, 9, 9), (460, 1300, 500, 1324), 1, 85.0, wc.alignment_string("קכג")))
    alignments, normalised = wc.align_page(ocr, "\n".join(LINES))
    assert alignments[0].status == "furniture" and alignments[-1].status in {"furniture", "short"}
    assert wc.assess_page(alignments, len(normalised), 960, 1400)["transcription_coverage"] == "full_page"


def test_untranscribed_text_inside_the_crop_is_listed_or_unresolves_the_crop() -> None:
    lines = LINES[:3] + LINES[3:]
    ocr = _page(lines[:3]) + [_line(_misread(NOTES[0], 0.05, 1), 3)] + [_line(_misread(t, 0.08, 9 + i), 4 + i) for i, t in enumerate(lines[3:])]
    alignments, normalised = wc.align_page(ocr, "\n".join(lines))
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400)
    crop = assessment["crop"]
    assert assessment["transcription_coverage"] == "partial_page"
    assert len(crop["untranscribed_inside"]) == 1 and crop["status"] == "resolved"  # one line in seven, masked
    # with a tighter tolerance one rectangle is not enough: two regions, the interleaved line masked out (F8b5)
    tight = {**wc.THRESHOLDS, "crop_untranscribed_inside_max": 0.05}
    regions = wc.assess_page(alignments, len(normalised), 960, 1400, tight)["crop"]
    assert regions["status"] == "resolved" and regions["method"] == wc.CROP_REGIONS_METHOD
    assert len(regions["regions_render_px"]) == 2 and regions["untranscribed_inside"] == [] and regions["masked_untranscribed"] == 1
    upper, lower = regions["regions_render_px"]
    note = ocr[3].box
    assert upper[3] <= note[1] and lower[1] >= note[3]  # neither region reaches into the untranscribed line
    assert regions["box_render_px"] == [min(upper[0], lower[0]), upper[1], max(upper[2], lower[2]), lower[3]]
    # when regions are not allowed either, the crop stays unresolved, with its reason
    single = {**tight, "region_max_count": 1}
    assert wc.assess_page(alignments, len(normalised), 960, 1400, single)["crop"] == {
        **{k: v for k, v in crop.items() if k not in {"status", "reason"}},
        "status": "unresolved",
        "reason": "untranscribed_text_inside_crop",
    }


def test_interleaved_untranscribed_blocks_split_the_crop_into_regions() -> None:
    """Luzzatto's layout: commentary, then an untranscribed Italian block, then more commentary, then verse."""

    italian = ["Dio creo il cielo e la terra nel principio", "e la terra era deserta e vuota e tenebre", "sopra la faccia dell abisso e lo spirito"]
    ocr = _page(LINES[:3])
    ocr += [_line(text, 3 + row) for row, text in enumerate(italian)]
    ocr += [_line(_misread(text, 0.08, 20 + row), 6 + row) for row, text in enumerate(LINES[3:])]
    ocr += [_line(_misread(text, 0.05, 40 + row), 10 + row) for row, text in enumerate(NOTES[:2])]
    alignments, normalised = wc.align_page(ocr, "\n".join(LINES))
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400)
    crop = assessment["crop"]
    assert assessment["transcription_coverage"] == "partial_page"
    assert crop["status"] == "resolved" and crop["method"] == wc.CROP_REGIONS_METHOD
    first, second = crop["regions_render_px"]
    assert first[1] <= ocr[0].box[1] and first[3] <= ocr[3].box[1]  # the first passage, stopped before the Italian
    assert second[1] >= ocr[5].box[3] and second[3] <= ocr[10].box[1]  # the second passage, stopped before the notes
    assert crop["masked_untranscribed"] == 3 and crop["untranscribed_inside"] == []
    assert crop["review_recommended"] is True  # a tool region crop is a proposal for review
    assert crop["box_normalized"] == wc._normalised(tuple(crop["box_render_px"]), 960, 1400)
    blocks = wc.transcribed_blocks([line.box for line in ocr[:3] + ocr[6:10]], [wc._Region(line.box, "line") for line in ocr[3:6]])
    assert len(blocks) == 2 and blocks[0][1] < blocks[1][1]  # reading order


def test_unrelated_text_is_not_located_and_decides_nothing() -> None:
    alignments, normalised = wc.align_page(_page(NOTES), "\n".join(LINES))
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400)
    assert assessment["outcome"] == "alignment_too_poor" and assessment["transcription_coverage"] is None
    assert assessment["crop"]["status"] == "unresolved" and assessment["crop"]["reason"] == "transcription_not_located"


def test_unread_ink_counts_as_untranscribed_text() -> None:
    image = Image.new("L", (960, 1400), 235)
    draw = ImageDraw.Draw(image)
    ocr = _page(LINES)
    for line in ocr:
        draw.rectangle(line.box, fill=40)
    # a block of print below the transcription that OCR did not read: three lines of large type
    for row in range(3):
        draw.rectangle((120, 520 + row * 60, 840, 560 + row * 60), fill=30)
    ink = wc.unrecognised_ink(image, ocr)
    assert ink and all(box[1] >= 500 for box in ink)
    alignments, normalised = wc.align_page(ocr, "\n".join(LINES))
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400, ink=ink)
    assert assessment["transcription_coverage"] == "partial_page"
    assert assessment["crop"]["status"] == "resolved" and assessment["crop"]["box_render_px"][3] < 520
    # the same print, read by OCR, is covered: no unread ink
    covered = ocr + [wc.OcrLine((5, 1, r), (120, 520 + r * 60, 840, 560 + r * 60), 5, 60.0, "אבגדהוזחטי") for r in range(3)]
    assert wc.unrecognised_ink(image, covered) == []
    # an illustration (one tall unbroken band) is not text
    picture = Image.new("L", (960, 1400), 235)
    ImageDraw.Draw(picture).rectangle((200, 500, 760, 1100), fill=60)
    assert wc.unrecognised_ink(picture, ocr) == []


def test_tool_check_records_geometry_and_scores_but_no_ocr_text() -> None:
    reference = "\n".join(LINES)
    ocr = _page(LINES, NOTES)
    alignments, normalised = wc.align_page(ocr, reference)
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400)
    page = {"page_title": "עמוד:X.pdf/7", "page_id": 1, "revision_id": 5, "index_key": "ws_index_1", "quality": 3, "page_number": 7}
    check = wc.tool_check(page, "abc", assessment, render={"render_url": "u", "sha256": "s"}, engine={"name": "tesseract"}, checked_at="2026-11-06")
    assert check["checked_by"] == "tool" and check["method"] == wc.METHOD_ID and check["transcription_coverage"] == "partial_page"
    assert inv.page_check_problems(check) == []
    dumped = json.dumps(check, ensure_ascii=False)
    for line in ocr:
        assert line.chars not in dumped  # OCR text is never recorded
    for text in LINES + NOTES:
        assert text not in dumped and wc.alignment_string(text) not in dumped


def test_human_and_agent_checks_override_tool_checks_and_the_tool_crop_serves_them() -> None:
    base = {"page_title": "עמוד:X.pdf/1", "revision_id": 5, "commons_file_sha1": "abc", "scan_page": 1, "checker": "c", "method": "m"}
    crop = {"status": "resolved", "reason": None, "method": wc.CROP_METHOD, "box_normalized": [0.1, 0.5, 0.9, 0.95], "untranscribed_inside": []}
    tool = {**base, "checked_by": "tool", "checked_at": "2026-11-07", "transcription_coverage": "full_page", "outcome": "decided", "crop": crop}
    agent = {**base, "checked_by": "agent", "checked_at": "2026-11-06", "transcription_coverage": "partial_page", "missing": "the verse"}
    payload = {"schema_version": inv.PAGE_CHECKS_SCHEMA_VERSION}
    selected = inv.select_page_checks([{**payload, "checks": [agent]}, {**payload, "checks": [tool]}])["עמוד:X.pdf/1"]
    assert selected["checked_by"] == "agent" and selected["tool_check"]["checked_by"] == "tool"
    page = {"revision_id": 5}
    provenance = inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, selected)
    assert provenance["applied"] and page["transcription_coverage"] == "partial_page"
    assert page["crop"]["status"] == "resolved" and page["crop"]["box_normalized"] == crop["box_normalized"]
    assert page["crop"]["located_by"]["checker"] == "c" and provenance["tool"]["transcription_coverage"] == "full_page"
    # alone, the tool decides
    alone = inv.select_page_checks({**payload, "checks": [tool]})["עמוד:X.pdf/1"]
    page = {"revision_id": 5}
    inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, alone)
    assert page["transcription_coverage"] == "full_page" and "crop" not in page
    # an undecided tool check sets no coverage
    undecided = {**tool, "transcription_coverage": None, "outcome": "alignment_too_poor", "crop": {"status": "unresolved", "reason": "transcription_not_located"}}
    page = {"revision_id": 5}
    provenance = inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, inv.select_page_checks({**payload, "checks": [undecided]})["עמוד:X.pdf/1"])
    assert provenance["applied"] is False and provenance["reason"] == "tool_alignment_too_poor" and "transcription_coverage" not in page
    # a tool check must record a valid crop
    assert inv.page_check_problems({**tool, "crop": {**crop, "box_normalized": [0.5, 0.5, 0.4, 0.9]}}) == ["a resolved crop needs a box inside the page"]
    assert inv.page_check_problems({**tool, "crop": None}) == ["a tool check must record its crop"]


def test_a_block_of_unaligned_lines_on_a_poorly_read_page_is_untranscribed() -> None:
    boxes = [(100, 100 + row * 30, 800, 124 + row * 30) for row in range(4)]
    assert wc._longest_block(boxes) == 4
    assert wc._longest_block([boxes[0], (100, 400, 800, 424)]) == 1
    assert wc._longest_block([boxes[0], (900, 130, 1000, 154)]) == 1  # another column


def test_committed_tool_checks_load_and_hold_only_geometry_and_scores() -> None:
    path = Path("docs/wikisource_page_tool_checks.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == inv.PAGE_CHECKS_SCHEMA_VERSION and payload["check_defaults"]["checked_by"] == "tool"
    assert set(payload["methods"]) == {wc.METHOD_ID, wc.FOOTNOTE_METHOD} and payload["thresholds"] == wc.THRESHOLDS
    selected = inv.load_page_checks([Path("docs/wikisource_page_checks.json"), path])
    assert len(selected) >= 1000
    allowed = {"page_title", "revision_id", "commons_file_sha1", "scan_page", "transcription_coverage", "outcome", "ocr_pass",
               "render_sha256", "render_size", "alignment", "crop", "missing", "ocr_engine", "checked_by", "checker", "checked_at", "method",
               "footnotes"}
    note_keys = {"note", "chars", "aligned_share", "bracketed_share", "status"}
    for check in payload["checks"]:
        assert set(check) <= allowed, set(check) - allowed
        # F8b7: the footnote check holds counts, shares and statuses only (no OCR or page text)
        for note in (check.get("footnotes") or {}).get("notes", []):
            assert set(note) == note_keys
        if check["transcription_coverage"] == "partial_page":
            assert check["missing"].startswith("untranscribed text located by OCR boxes")
        if check["crop"]["status"] == "resolved":
            assert inv.crop_box_valid(check["crop"]["box_normalized"])
    text = path.read_text(encoding="utf-8")
    assert "/Users/" not in text and "/home/" not in text and "render_url" not in text


def test_an_agent_crop_is_validated_and_wins_over_the_tool_crop() -> None:
    """F8b5: an agent or human may confirm, correct or place the crop itself (a geometry fact, not an attestation)."""

    base = {"page_title": "עמוד:X.pdf/1", "revision_id": 5, "commons_file_sha1": "abc", "scan_page": 1, "checker": "c", "method": "m"}
    tool_crop = {"status": "unresolved", "reason": "untranscribed_text_inside_crop", "method": wc.CROP_METHOD, "box_normalized": [0.1, 0.1, 0.9, 0.9]}
    tool = {**base, "checked_by": "tool", "checked_at": "2026-11-06", "transcription_coverage": "partial_page", "missing": "m", "outcome": "decided",
            "crop": tool_crop, "render_sha256": "r"}
    regions = [[0.1, 0.1, 0.9, 0.4], [0.1, 0.6, 0.9, 0.9]]
    agent_crop = {"status": "resolved", "method": "agent_visual_crop.v1", "basis": "tool_crop_corrected", "box_normalized": [0.1, 0.1, 0.9, 0.9], "regions_normalized": regions}
    agent = {**base, "checked_by": "agent", "checked_at": "2026-11-06", "transcription_coverage": "partial_page", "missing": "the Italian block",
             "crop": agent_crop, "render_sha256": "r"}
    assert inv.page_check_problems(agent) == []
    payload = {"schema_version": inv.PAGE_CHECKS_SCHEMA_VERSION}
    selected = inv.select_page_checks([{**payload, "checks": [tool]}, {**payload, "checks": [agent]}])["עמוד:X.pdf/1"]
    page = {"revision_id": 5}
    provenance = inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, selected)
    assert provenance["crop_by"] == "agent" and page["transcription_coverage_check"]["crop_by"] == "agent"
    assert page["crop"]["status"] == "resolved" and page["crop"]["regions_normalized"] == regions
    assert page["crop"]["located_by"] == {"checked_by": "agent", "checker": "c", "checked_at": "2026-11-06", "method": "m", "render_url": None,
                                          "render_sha256": "r", "render_size": None, "basis": "tool_crop_corrected"}
    assert page["crop"]["review_recommended"] is False
    # an agent check without its own crop still takes the tool's
    plain = {key: value for key, value in agent.items() if key != "crop"}
    page = {"revision_id": 5}
    inv.apply_page_check(page, {"commons_file": {"sha1": "abc"}}, inv.select_page_checks([{**payload, "checks": [tool, plain]}])["עמוד:X.pdf/1"])
    assert page["crop"]["status"] == "unresolved" and page["crop"]["located_by"]["checked_by"] == "tool"
    # schema: a resolved crop, on a partial page, with a known method and basis, and regions whose union is the box
    assert inv.page_check_problems({**agent, "crop": {**agent_crop, "status": "unresolved"}}) == ["an agent or human crop must be a resolved crop"]
    assert inv.page_check_problems({**agent, "transcription_coverage": "full_page", "missing": None}) == ["only a partial_page check records a crop"]
    assert "basis" in inv.page_check_problems({**agent, "crop": {**agent_crop, "basis": "guessed"}})[0]
    assert "method" in inv.page_check_problems({**agent, "crop": {**agent_crop, "method": wc.CROP_METHOD}})[0]
    assert inv.page_check_problems({**agent, "crop": {**agent_crop, "box_normalized": [0.1, 0.1, 0.9, 0.95]}}) == [
        "crop regions must be two or more boxes inside the page whose union is the box"
    ]
    # a tool region crop is checked the same way
    tool_regions = {**tool_crop, "status": "resolved", "reason": None, "method": wc.CROP_REGIONS_METHOD, "regions_normalized": regions}
    assert inv.page_check_problems({**tool, "crop": tool_regions}) == []
    assert inv.page_check_problems({**tool, "crop": {**tool_regions, "regions_normalized": [[0.1, 0.1, 0.9, 1.2], regions[1]]}}) == [
        "crop regions must be two or more boxes inside the page whose union is the box"
    ]


def test_rename_log_replies_become_recorded_renames() -> None:
    meta = {"query": {"logevents": [{"logid": 9259138, "type": "gblrename", "timestamp": "2014-07-30T08:23:07Z", "params": {"olduser": "איתן96", "newuser": "Eitan96"}}]}}
    local = {"query": {"logevents": [{"logid": 7, "type": "block", "params": {}}]}}
    assert inv.renames_from_log(meta, "https://meta.wikimedia.org") == [
        {"old": "איתן96", "new": "Eitan96", "log_id": 9259138, "timestamp": "2014-07-30T08:23:07Z", "log_type": "gblrename", "wiki": "https://meta.wikimedia.org"}
    ]
    assert inv.renames_from_log(local, inv.WS_SITE) == [] and inv.renames_from_log({}, inv.WS_SITE) == []


def test_compact_tool_checks_keep_region_crops() -> None:
    reference = "\n".join(LINES)
    ocr = _page(LINES[:3]) + [_line(_misread(NOTES[0], 0.05, 1), 3)] + [_line(_misread(t, 0.08, 9 + i), 4 + i) for i, t in enumerate(LINES[3:])]
    alignments, normalised = wc.align_page(ocr, reference)
    assessment = wc.assess_page(alignments, len(normalised), 960, 1400, {**wc.THRESHOLDS, "crop_untranscribed_inside_max": 0.05})
    page = {"page_title": "עמוד:X.pdf/7", "page_id": 1, "revision_id": 5, "index_key": "ws_index_1", "quality": 3, "page_number": 7}
    check = wc.tool_check(page, "abc", assessment, render={"render_url": "u", "sha256": "s"}, engine={"name": "tesseract"}, checked_at="2026-11-06")
    payload = {"schema_version": inv.PAGE_CHECKS_SCHEMA_VERSION, "description": "d", "tool_version": wc.TOOL_VERSION, "thresholds": wc.THRESHOLDS,
               "methods": {wc.METHOD_ID: wc.METHOD_TEXT}, "checks": [check]}
    compact = wc.compact_tool_checks(payload)
    crop = compact["checks"][0]["crop"]
    assert crop["method"] == wc.CROP_REGIONS_METHOD and len(crop["regions_normalized"]) == 2
    loaded = inv.select_page_checks(json.loads(wc.dump_checks(compact)))["עמוד:X.pdf/7"]
    assert loaded["crop"]["regions_normalized"] == crop["regions_normalized"]
