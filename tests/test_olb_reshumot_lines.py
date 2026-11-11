"""olb_reshumot_lines: scanned Reshumot lines labelled with same-wording OLB (Hebrew Wikisource) text.

Everything here is pure: OLB wikitext parsing, the comparison normaliser, line location, the per-line acceptance gate,
the held-out registry, the plan and the dev choice. The poppler / Tesseract steps run only in operator builds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.split.eval_reserved import packaged_registry
from hocrgen.tools import olb_reshumot_lines as olb

FIXTURES = Path(__file__).parent / "fixtures" / "olb_reshumot"


def _page(name: str) -> olb.OlbPage:
    return olb.parse_olb_page(name, (FIXTURES / f"{name}.wiki").read_text(encoding="utf-8"), revision_id=1)


# --- Hebrew years and citations -------------------------------------------------------------------------------------


@pytest.mark.parametrize("text,year", [("תש״ט", 5709), ("התשס״ה", 5765), ("תשנ״ג", 5753), ("תש״ח", 5708),
                                       ("תשמ״א", 5741), ("1949", None), ("פרק", None)])
def test_hebrew_year(text: str, year: int | None) -> None:
    assert olb.hebrew_year(text) == year


def test_citations_carry_series_and_year_forward() -> None:
    page = _page("flag_law")
    assert [(c.series, c.hebrew_year, c.page, c.role) for c in page.citations] == [
        ("sefer_hachukim", 5709, 37, "principal"), ("sefer_hachukim", 5741, 272, "amendment"),
        ("sefer_hachukim", 5741, 300, "amendment")]
    assert not page.replaced_law


def test_replaced_law_cites_the_new_law_as_its_own() -> None:
    page = _page("continuity_new")
    assert page.replaced_law
    roles = [(c.hebrew_year, c.page, c.role) for c in page.citations]
    assert roles == [(5725, 2, "prior_law"), (5734, 96, "prior_law"), (5753, 60, "new_law"), (5756, 10, "amendment")]


# --- OLB parsing ---------------------------------------------------------------------------------------------------


def test_parse_strips_editorial_notes_and_markup() -> None:
    page = _page("flag_law")
    texts = [b.text for b in page.blocks]
    assert page.notes_stripped == 2
    assert not any("בוטל" in t or "[1]" in t for t in texts)
    assert "1. (א) ”דגל המדינה“ – פירושו הדגל שמועצת־המדינה הזמנית הכריזה עליו ביום כ״ה בתשרי תש״ט (28 באוקטובר 1948) כעל דגל מדינת ישראל." in texts
    assert "”סמל המדינה“ – פירושו הסמל שהכריזה עליו לפי סעיף 2." in texts
    assert "2. לא ישתמש אדם שימוש כל שהוא בדגל המדינה לשם מסחר, עסק או משלח־יד, אלא על פי רשיון מאת הממשלה." in texts
    kinds = {b.text: b.kind for b in page.blocks}
    assert kinds["פרק שני: שימוש"] == "heading"
    assert kinds["פירושים"] == "section_heading"
    assert kinds["דוד בן־גוריון"] == kinds["ראש הממשלה"] == "signature"


def test_tables_navigation_and_unknown_templates_give_no_paragraph() -> None:
    page = _page("flag_law")
    texts = " ".join(b.text for b in page.blocks)
    assert "תא" not in texts and "שורה עם תבנית" not in texts
    assert page.unknown_templates == ["תבנית מוזרה"]


# --- normaliser and label fold ---------------------------------------------------------------------------------------


def test_compare_key_folds_glyphs_spacing_and_digit_group_order() -> None:
    assert olb.compare_key("”דגל המדינה“ – פירושו") == olb.compare_key('"דגל  המדינה" - פירושו')
    assert olb.compare_key("מועצת־המדינה (א)") == olb.compare_key("מועצת-המדינה )א(")
    assert olb.compare_key("תש״ט–1949") == olb.compare_key('תש"ט-1949')
    assert olb.compare_key("ביום 12.3.1949") == olb.compare_key("ביום 1949.3.12")
    assert olb.compare_key("1949") != olb.compare_key("1994")
    assert olb.compare_key("רשיון, מאת") != olb.compare_key("רשיון; מאת")


def test_fold_label_keeps_words_and_punctuation() -> None:
    assert olb.fold_label("”דגל המדינה“ – פירושו, תש״ט–1949 ע׳") == '"דגל המדינה" - פירושו, תש"ט-1949 ע\''


def test_footnote_markers_are_found_only_where_the_label_lacks_them() -> None:
    assert olb.strip_footnote_markers("חוק הדגל, תש\"ט-1949 *", "חוק הדגל, תש\"ט-1949") == ("חוק הדגל, תש\"ט-1949", 1)
    assert olb.strip_footnote_markers("לחוק העונשין1 קובע", "לחוק העונשין קובע") == ("לחוק העונשין קובע", 1)
    assert olb.strip_footnote_markers("סעיף 2 קובע", "סעיף 2 קובע") == ("סעיף 2 קובע", 0)


# --- location and the acceptance gate --------------------------------------------------------------------------------


def _paragraphs() -> list[olb.Paragraph]:
    return [olb.make_paragraph("חוק הדגל והסמל", b) for b in _page("flag_law").blocks]


def test_locate_finds_the_word_span_of_a_noisy_reading() -> None:
    spot = olb.locate("לא ישתמש אדם שימוש כל שהוא בדגל המדינח לשם מםחר", _paragraphs())
    assert spot is not None
    assert spot.raw_text == "לא ישתמש אדם שימוש כל שהוא בדגל המדינה לשם מסחר,"
    assert olb.locate("טקסט שאינו מופיע כלל בשום מקום בחוק", _paragraphs()) is None


def test_accept_exact_readings() -> None:
    label = "לא ישתמש אדם שימוש כל שהוא בדגל המדינה"
    d = olb.accept_line(label, "לא ישתמש אדם שימוש כל שהוא בדגל המדינה", "לא ישתמש אדם שימש כל שהוא בדגל המדינה")
    assert d.accepted and d.tier == "layer_exact" and d.evidence["cer_layer"] == 0.0 and d.evidence["cer_tesseract"] > 0
    d = olb.accept_line(label, None, "לא ישתמש אדם שימוש כל שהוא בדגל המדינה")
    assert d.accepted and d.tier == "tesseract_exact"


def test_accept_char_consensus_and_reject_agreed_deviation() -> None:
    label = "לא ישתמש אדם שימוש כל שהוא בדגל המדינה"
    # each reading has a different error; every label character is read by one of them
    d = olb.accept_line(label, "לא ישתמש אדם שימוש כל שהוא בדגל המדינח", "לא ישתמש אדס שימוש כל שהוא בדגל המדינה")
    assert d.accepted and d.tier == "char_consensus"
    # both readings agree the print has ';' where OLB has ',': a real difference
    d = olb.accept_line("רשיון, מאת הממשלה", "רשיון; מאת הממשלה", "רשיון; מאת הממשלח")
    assert not d.accepted and d.reason == "ocr_disagrees_with_olb"
    # both readings miss the same character the label has: not confirmed
    d = olb.accept_line("דגל המדינה הזמנית", "דגל המדינה הזמנת", "דגל המדינה הזמנת")
    assert not d.accepted


def test_single_reading_must_be_exact() -> None:
    d = olb.accept_line("לא ישתמש אדם שימוש כל שהוא", None, "לא ישתמש אדם שימש כל שהוא")
    assert not d.accepted and d.reason == "single_reading_not_exact"


def test_footnote_marker_is_stripped_and_reported() -> None:
    d = olb.accept_line('חוק הדגל והסמל, תש"ט-1949', 'חוק הדגל והסמל, תש"ט-1949 *', 'חוק הדגל והסמל, תש"ט-1949 *')
    assert d.accepted and d.evidence["footnote_markers_stripped"] == 1


def test_label_ok() -> None:
    assert olb.label_ok("לא ישתמש אדם שימוש") is None
    assert olb.label_ok("סעיף") == "too_short"
    assert olb.label_ok("שָׁלוֹם לכם חברים יקרים") == "pointed"


# --- held-out units -----------------------------------------------------------------------------------------------


def _split_file(tmp_path: Path) -> tuple[Path, str]:
    doc = {"test": [{"unit_id": "reshumot_scanned:sefer_hachukim_8"}], "dev": [{"unit_id": "reshumot_scanned:sefer_hachukim_9"}],
           "non_eval": [{"unit_id": "reshumot_scanned:sefer_hachukim_10"}, {"unit_id": "plenary:K1_5"}]}
    path = tmp_path / "midcentury_unit_split_v0.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def test_training_registry_fails_closed_until_reshumot_scanned_is_synced() -> None:
    registry = packaged_registry()
    if registry.governs(olb.SOURCE_ID):  # after heocr-eval's pmod_unit_split_v2 sync
        assert olb.training_registry(registry) is registry
    else:
        with pytest.raises(SystemExit, match="does not govern reshumot_scanned"):
            olb.training_registry(registry)


def test_ids_never_take_the_born_digital_shape() -> None:
    from hocrgen.split.eval_reserved import unit_from_identifier

    assert olb.unit_id("sefer_hachukim", "0008") == "reshumot_scanned:sefer_hachukim_8"
    assert olb.booklet_slug("kovetz_hatakanot", 1485) == "reshumot_scanned_kovetz_hatakanot_1485"
    assert olb.page_id("sefer_hachukim", 8, 3) == "reshumot_scanned_sefer_hachukim_8__p0003"
    for value in (olb.booklet_slug("sefer_hachukim", 8), olb.page_id("sefer_hachukim", 8, 3),
                  olb.page_id("sefer_hachukim", 8, 3) + "_l012"):
        hit = unit_from_identifier(value)
        assert hit is None or hit[0] != "reshumot_born_digital"


def test_load_split_refuses_another_file(tmp_path: Path) -> None:
    path, _ = _split_file(tmp_path)
    with pytest.raises(SystemExit):
        olb.load_split(path, "0" * 64)


# --- plan -----------------------------------------------------------------------------------------------------------


def _units() -> list[dict]:
    rows = []
    for number, idx, pages in ((8, 17, 6), (9, 17, 40), (10, 17, 4), (435, 33, 8), (436, 33, 10)):
        summary = "חוק הדגל והסמל, תש״ט-1949<br/> חוק אחר, תש״ט-1949" if number == 10 else None
        rows.append({"doc_summary": summary, "series": "sefer_hachukim", "number": number, "booklet_label": str(number), "booklet_year_index": idx,
                     "hebrew_year": idx + 5692, "year": idx + 5692 - 3760, "pages": pages, "url": f"https://x/{number}",
                     "file_token": f"t{number}", "creation_date": "2013-01-01"})
    return rows


def test_booklet_page_ranges_follow_volume_pagination() -> None:
    ranges = olb.booklet_page_ranges(_units())  # one unnumbered cover page per booklet
    assert ranges["reshumot_scanned:sefer_hachukim_8"] == (1, 5, 0)
    assert ranges["reshumot_scanned:sefer_hachukim_9"] == (6, 44, 1)
    assert ranges["reshumot_scanned:sefer_hachukim_10"] == (45, 47, 2)
    assert ranges["reshumot_scanned:sefer_hachukim_435"] == (1, 7, 0)


def test_plan_uses_citations_and_the_split(tmp_path: Path) -> None:
    units = tmp_path / "units.json"
    units.write_text(json.dumps({"units": _units()}), encoding="utf-8")
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"test": [{"unit_id": "reshumot_scanned:sefer_hachukim_8"}], "dev": [],
                                 "non_eval": [{"unit_id": f"reshumot_scanned:sefer_hachukim_{n}"} for n in (9, 10, 435, 436)]}))
    olb_dir = tmp_path / "olb"
    olb_dir.mkdir()
    pages = [_page("flag_law"), _page("continuity_new")]
    index = {"pages": [{"title": p.title, "revision_id": 1, "citations": [c.__dict__ for c in p.citations]} for p in pages]}
    (olb_dir / "olb_index.json").write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    doc = olb.plan(units, split, hashlib.sha256(split.read_bytes()).hexdigest(), olb_dir, slack=0)
    b = doc["booklets"]
    assert b["reshumot_scanned:sefer_hachukim_8"]["split_status"] == "test" and "files" not in b["reshumot_scanned:sefer_hachukim_8"]
    assert [c["title"] for c in b["reshumot_scanned:sefer_hachukim_9"]["olb_candidates"]] == ["flag_law"]  # cited page 37
    # booklet 10 is outside the page window, but its DocSummary names the law
    (cand,) = b["reshumot_scanned:sefer_hachukim_10"]["olb_candidates"]
    assert cand["title"] == "flag_law" and cand["by_title"] and not cand["by_page"]
    # the 1993 law that replaced the 1965 one is never matched to the 1965 booklet (cites תשכ״ה only as "חוק קודם")
    assert b["reshumot_scanned:sefer_hachukim_435"]["olb_candidates"] == []
    assert doc["counts"] == {"skipped_test": 1, "non_eval_booklets": 4, "non_eval_with_candidates": 2}


def test_norm_title_drops_year_and_glyphs() -> None:
    assert olb.norm_title("חוק הדגל והסמל, תש״ט–1949") == olb.norm_title('חוק הדגל והסמל, התש"ט-1949') == "חוק הדגל והסמל"


# --- page geometry and dev ------------------------------------------------------------------------------------------


def test_page_scan_row_skips_jpx_overlays() -> None:
    rows = [{"page": 1, "type": "image", "enc": "jpx", "width": 300, "height": 400},
            {"page": 1, "type": "image", "enc": "jbig2", "width": 2480, "height": 3508},
            {"page": 1, "type": "smask", "enc": "jbig2", "width": 2480, "height": 3508}]
    assert olb.page_scan_row(rows, 1)["enc"] == "jbig2"
    assert olb.page_scan_row(rows, 2) is None


def test_layer_lines_read_right_to_left_and_scale() -> None:
    page = {"width": 100.0, "height": 200.0, "lines": [[(10, 10, 20, 15, "שלישי"), (60, 10, 90, 15, "ראשון"), (30, 10, 50, 15, "שני")]]}
    (line,) = olb.layer_lines(page, 4.0, 4.0)
    assert line.layer == "ראשון שני שלישי"
    assert line.box == [40, 40, 360, 60]


def test_crop_box_stops_at_neighbouring_lines() -> None:
    a = olb.PageLine(0, [100, 100, 900, 140], "a", "a")
    b = olb.PageLine(1, [100, 150, 900, 190], "b", "b")
    margin = olb.PageLine(2, [950, 100, 1100, 140], "c", "c")
    box = olb.crop_box(a, [a, b, margin], (1200, 1000))
    assert box[1] < 100 and box[3] <= 149 and box[2] <= 949


def test_choose_dev_one_per_series_decade() -> None:
    booklets = {f"reshumot_scanned:sefer_hachukim_{n}": {"series": "sefer_hachukim", "year": y, "lines_candidate": c}
                for n, y, c in ((1, 1949, 5), (2, 1951, 3), (3, 1965, 2), (4, 1966, 0))}
    dev = olb.choose_dev(booklets)
    assert sorted(dev["picks"].values()) == ["sefer_hachukim|1948-59", "sefer_hachukim|1960s"]
    assert "reshumot_scanned:sefer_hachukim_4" not in dev["picks"]


def test_word_ngrams() -> None:
    assert olb.word_ngrams("א ב ג ד ה ו ז") == {("א", "ב", "ג", "ד", "ה", "ו"), ("ב", "ג", "ד", "ה", "ו", "ז")}
    assert olb.word_ngrams("א ב ג") == set()


def test_cli_parses_build_arguments() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    olb.add_build_arguments(sub)
    args = parser.parse_args(["build", "out", "--plan", "p", "--split", "s", "--split-sha256", "x", "--pmod-split", "m",
                              "--tasks", "t", "--olb", "o", "--cache", "c", "--shuffle-seed", "seed"])
    assert args.shuffle_seed == "seed" and args.workers == 1 and not args.keep_footnote_lines


def test_merge_row_fragments_joins_a_split_row_but_not_a_margin_heading() -> None:
    right = olb.PageLine(0, [1500, 100, 2200, 150], "(א) דגל המדינה", "(א) דגל המדינה")
    left = olb.PageLine(1, [600, 102, 1480, 150], "הכריזה עליו", "הכריזה עליו")
    margin = olb.PageLine(2, [100, 100, 400, 150], "פירושים", "פירושים")
    below = olb.PageLine(3, [600, 200, 2200, 250], "שורה הבאה", "שורה הבאה")
    merged = olb.merge_row_fragments([left, margin, right, below])
    assert [(l.index, l.layer) for l in merged] == [(0, "(א) דגל המדינה הכריזה עליו"), (2, "פירושים"), (3, "שורה הבאה")]
    assert merged[0].box == [600, 100, 2200, 150]


def test_visual_layer_words_are_turned_to_logical_order() -> None:
    assert olb.layer_is_visual(["ןכותה", "הנידמה", "םויקל"]) and not olb.layer_is_visual(["התוכן", "לקיום", "שלום"])
    assert olb.visual_to_logical('*1949­ט"שת') == 'תש"ט­1949*'
    assert olb.visual_to_logical(")18.3.49(") == "(18.3.49)"


def test_consensus_never_outvotes_an_inserted_digit() -> None:
    label = "ביום כ\"ה בתשרי תש\"ט (28 באוקטובר 1948) כעל דגל"
    d = olb.accept_line(label, "ביום כ\"ה בתשרי תש\"ט (28 באוקטובר 1948) 1כעל דגל", "ביום כ\"ה בתשרי תש\"ט (28 באוקטובר 1948) כעל דנל")
    assert not d.accepted and d.evidence["inserted_digits_or_marks"] == 1


def test_inputs_under_the_eval_test_folder_are_refused(tmp_path: Path) -> None:
    forbidden = tmp_path / "midcentury_test"
    (forbidden / "pdf").mkdir(parents=True)
    with pytest.raises(olb.ForbiddenInputError):
        olb.refuse_forbidden_path(forbidden / "pdf" / "sefer_hachukim_8.pdf", [forbidden])
    with pytest.raises(olb.ForbiddenInputError):
        olb.refuse_forbidden_path(tmp_path / "other" / ".." / "midcentury_test", [forbidden])
    link = tmp_path / "cache"
    link.symlink_to(forbidden)
    with pytest.raises(olb.ForbiddenInputError):
        olb.refuse_forbidden_path(link / "pdf", [forbidden])
    assert olb.refuse_forbidden_path(tmp_path / "olb", [forbidden]) == (tmp_path / "olb").resolve()
    assert str(olb.FORBIDDEN_INPUT_DIRS[0]).endswith("tasks/modern-s6-scout/midcentury_test")
    assert olb.NODE_HINT == "new_printed"


def _registry_with_scanned(eval_units: list[str], non_eval_units: list[str]):
    from hocrgen.config.models import EvalReservedUnitsRegistry

    data = packaged_registry().model_dump(mode="json")
    data["sources"] = [s for s in data["sources"] if s["source_id"] != olb.SOURCE_ID] + [
        {"source_id": olb.SOURCE_ID, "unit": "one scanned Reshumot booklet", "eval_units": sorted(eval_units),
         "non_eval_units": sorted(non_eval_units)}]
    return EvalReservedUnitsRegistry.model_validate(data)


def test_rows_pass_the_guard_only_for_non_eval_scanned_units() -> None:
    from hocrgen.split.eval_reserved import EvalReservedUnitError, refuse_eval_reserved_training_input

    registry = _registry_with_scanned(["reshumot_scanned:sefer_hachukim_8"], ["reshumot_scanned:sefer_hachukim_10"])
    assert olb.training_registry(registry) is registry

    def row(number: int) -> dict:
        entry = olb.page_id("sefer_hachukim", number, 3)
        return {"id": f"{entry}_l012", "entry_id": entry, "book": olb.booklet_slug("sefer_hachukim", number),
                "record_id": olb.booklet_slug("sefer_hachukim", number), "unit_id": olb.unit_id("sefer_hachukim", number),
                "source_id": olb.SOURCE_ID}

    assert refuse_eval_reserved_training_input([row(10)], builder="t", registry=registry) == 1
    for number in (8, 11):  # eval, unassigned
        with pytest.raises(EvalReservedUnitError):
            refuse_eval_reserved_training_input([row(number)], builder="t", registry=registry)
