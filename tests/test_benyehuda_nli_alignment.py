"""Network-free tests for the operator-only PBY-to-NLI edition matching and alignment pilot (F8f)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from hocrgen.fetchers.nli_iiif import capture_from_payload, decide_nli_rights
from hocrgen.tools import benyehuda_nli_alignment as tool
from hocrgen.tools.nli_search_discovery import DC
from hocrgen.utils.hashing import sha256_file

FIXTURE = Path(__file__).parent / "fixtures" / "benyehuda_nli"
SECRET = "f8f-test-key-314"
LICENSE_BASE = "https://www.nli.org.il/contenteditors/pages-for-terms-of-use/"
FREE = f"{LICENSE_BASE}public-domain-free-use"
GOOGLE = f"{LICENSE_BASE}public-domain-non-commercial-use"


def _excerpt() -> str:
    return (FIXTURE / "pby_excerpt.txt").read_text(encoding="utf-8")


# --- normalization -----------------------------------------------------------------------------------------


def test_skeleton_strips_marks_and_maps_offsets() -> None:
    text = "שָׁלוֹם, עוֹלָם!"
    sk = tool.skeleton(text)
    assert sk.strict == "שלומעולמ"
    assert sk.loose == "שלמעלמ"
    # Every strict letter maps back to the same letter in the source.
    for index, offset in enumerate(sk.strict_offsets):
        assert text[offset].translate(tool.FINAL_FORMS) == sk.strict[index]
    assert sk.loose_offset(0) == 0
    assert text[sk.loose_offset(len(sk.loose) - 1)] == "ם"


def test_loose_key_folds_ocr_confusions_and_matres() -> None:
    assert tool.loose_key("דבר") == tool.loose_key("רכד")
    assert tool.loose_key("תורה") == tool.loose_key("חרה")
    assert tool.loose_key("שירים") == tool.loose_key("שרם")
    assert tool.strict_key("ײַ") == "יי"
    assert tool.loose_key("Mapu") == "mapu"


def test_niqqud_profile_and_strip_marks() -> None:
    profile = tool.niqqud_profile("שָׁלוֹם לכם עוֹלָם")
    assert profile == {"niqqud_marks": 5, "words": 3, "pointed_words": 2, "pointed_word_share": 0.6667}
    assert tool.strip_marks("שָׁלוֹם") == "שלום"
    assert tool.niqqud_profile("")["pointed_word_share"] == 0.0


def test_pby_body_drops_the_dump_trailer() -> None:
    body = "טקסט היצירה.\n\n\nאת הטקסט[ים] לעיל הפיקו מתנדבי פרויקט בן־יהודה באינטרנט.  הכל זמין תמיד בכתובת הבאה:https://benyehuda.org/read/1"
    assert tool.pby_body(body) == "טקסט היצירה.\n"
    assert tool.pby_body("ללא סיומת") == "ללא סיומת"


# --- catalogue and matching --------------------------------------------------------------------------------

CATALOGUE = (
    "ID,path,title,authors,translators,author_uris,translator_uris,original_language,genre,source_edition\n"
    '3149,/p12/m3149,אברהם מאפו: חייו וספריו,ראובן בריינין,"",u,"","",prose,"אברהם מאפו - חייו וספריו / ראובן בריינין ; וילנא: תושיה, 1928"\n'
    '162,/p40/m162,אגרות תנחומים,קלמן שולמן,"",u,"","",prose,"מתוך ""שפה ברורה"", מהדורה שנייה, וילנה 1864."\n'
    '10,/p23/m10,חצי-נחמה,אחד העם,"",u,"","",article,""\n'
)


@pytest.fixture()
def catalogue(tmp_path: Path) -> dict[str, dict[str, str]]:
    path = tmp_path / "pseudocatalogue.csv"
    path.write_text(CATALOGUE, encoding="utf-8")
    return tool.load_catalogue(path)


def test_catalogue_fields_and_text_paths(catalogue: dict[str, dict[str, str]]) -> None:
    fields = tool.catalogue_fields(catalogue["3149"])
    assert fields["source_edition_year"] == 1928
    assert fields["read_url"] == "https://benyehuda.org/read/3149"
    assert tool.catalogue_fields(catalogue["10"])["source_edition"] is None
    assert tool.pby_text_path(catalogue["3149"]) == "txt/p12/m3149.txt"
    assert tool.pby_raw_url(catalogue["162"]).endswith("/2026-03/txt/p40/m162.txt")


def test_terms_present_is_spelling_tolerant() -> None:
    assert tool.terms_present("אברהם מאפו : חייו וספריו / מאת ראובן בריינין.", ["מאפו", "חיו וספרו"])
    assert tool.terms_present("ווילנא ; ורשה : תושיה", ["תושיה"])
    assert not tool.terms_present("ורשה : אחיאסף", ["תושיה"])
    assert tool.terms_present(None, [])


def _record(record_id: str, title: str, date: str, publisher: str, *, kind: str = "book") -> dict:
    return {
        "@id": f"https://www.nli.org.il/en/books/NNL_ALEPH{record_id}",
        f"{DC}recordid": [{"@value": record_id}],
        f"{DC}title": [{"@value": title}],
        f"{DC}type": [{"@value": kind}],
        f"{DC}non_standard_date": [{"@value": date}],
        f"{DC}publisher": [{"@value": publisher}],
        f"{DC}relation": [{"@id": f"https://iiif.nli.org.il/IIIFv21/{record_id}/manifest"}],
    }


def _manifest(licence: str, canvases: int) -> dict:
    return {
        "license": [licence],
        "label": "x",
        "metadata": [{"label": "Publisher", "value": "ווילנא ; ורשה : תושיה"}, {"label": "Format", "value": ["150 עמודים"]}],
        "sequences": [{"canvases": [{"@id": f"c{index}"} for index in range(canvases)]}],
    }


def _fake_fetch(search: dict[str, list[dict]], manifests: dict[str, dict | int]):
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, bytes]:
        calls.append(url)
        parsed = urlparse(url)
        if parsed.netloc == "api2.nli.org.il":
            params = parse_qs(parsed.query)
            assert params["api_key"] == [SECRET]
            query = params["query"][0]
            if query not in search:
                return 502, b""
            return 200, json.dumps(search[query]).encode("utf-8")
        record_id = parsed.path.split("/")[2]
        value = manifests[record_id]
        if isinstance(value, int):
            return value, b""
        return 200, json.dumps(value).encode("utf-8")

    return fetch, calls


def test_match_candidate_keeps_edition_hits_and_gates_rights(catalogue: dict[str, dict[str, str]]) -> None:
    search = {
        "title,contains,מאפו": [
            _record("1", "אברהם מאפו : חייו וספריו / מאת ראובן בריינין.", 'תרפ"ח', "ווילנא ; ורשה : תושיה"),
            _record("2", "אברהם מאפו : חייו וספריו", "1958", "תל אביב : דביר"),  # wrong year
            _record("3", "אהבת ציון", 'תרפ"ח', "ורשה : תושיה"),  # wrong title
            _record("4", "אברהם מאפו", 'תרפ"ח', "ורשה : תושיה", kind="manuscript"),  # not a book
        ]
    }
    fetch, calls = _fake_fetch(search, {"1": _manifest(FREE, 162)})
    candidate = {
        "candidate_id": "brainin",
        "label": "Brainin 1928",
        "pby_ids": ["3149"],
        "expected_year": 1928,
        "queries": ["title,contains,מאפו"],
        "title_terms": ["מאפו"],
        "publisher_terms": ["תושיה"],
    }
    result = tool.match_candidate(candidate, catalogue, api_key=SECRET, fetch=fetch)
    assert result["status"] == "matched"
    assert [hit["record_id"] for hit in result["kept_hits"]] == ["1"]
    assert result["match"]["canvas_count"] == 162
    assert result["kept_hits"][0]["manifest"]["publisher"] == "ווילנא ; ורשה : תושיה"
    assert result["kept_hits"][0]["manifest"]["format"] == "150 עמודים"
    assert result["pby_works"][0]["source_edition_year"] == 1928
    assert SECRET not in json.dumps(result, ensure_ascii=False)
    assert len(calls) == 2


@pytest.mark.parametrize(
    ("manifests", "expected"),
    [
        ({"1": _manifest(GOOGLE, 94)}, "edition_scan_non_commercial"),
        ({"1": _manifest(FREE, 0)}, "edition_scan_zero_canvases"),
        ({"1": _manifest(f"{LICENSE_BASE}fair-use", 10)}, "edition_scan_not_free_use"),
    ],
)
def test_match_candidate_unmatched_reasons(catalogue: dict[str, dict[str, str]], manifests: dict, expected: str) -> None:
    search = {"title,contains,שפה ברורה": [_record("1", "שפה ברורה : קבצת מליצות", 'תרכ"ד', "ווילנא")]}
    fetch, _ = _fake_fetch(search, manifests)
    candidate = {"candidate_id": "c", "pby_ids": ["162"], "expected_year": 1864, "queries": ["title,contains,שפה ברורה"], "title_terms": ["שפה ברורה"]}
    result = tool.match_candidate(candidate, catalogue, api_key=SECRET, fetch=fetch)
    assert result["status"] == "unmatched"
    assert result["reason"] == expected


def test_run_match_summary_counts_search_failures_and_misses(catalogue: dict[str, dict[str, str]]) -> None:
    search = {"title,contains,כלום": [], "title,contains,מאפו": [_record("1", "אברהם מאפו", 'תרפ"ח', "תושיה")]}
    fetch, _ = _fake_fetch(search, {"1": _manifest(FREE, 5)})
    candidates = [
        {"candidate_id": "miss", "pby_ids": ["162"], "queries": ["title,contains,כלום"]},
        {"candidate_id": "fail", "pby_ids": ["162"], "queries": ["title,contains,502"]},
        {"candidate_id": "hit", "pby_ids": ["3149", "missing-id"], "expected_year": 1928, "queries": ["title,contains,מאפו"]},
    ]
    report = tool.run_match(candidates, catalogue, api_key=SECRET, fetch=fetch, captured_on="2026-11-06")
    assert report["format"] == tool.MATCH_FORMAT
    assert report["summary"] == {
        "candidates": 3,
        "matched": 1,
        "match_rate": 0.3333,
        "unmatched_reasons": {"no_edition_hit": 1, "search_failed": 1},
    }
    rows = tool.compact_match(report)
    assert [row["status"] for row in rows] == ["unmatched", "unmatched", "matched"]
    assert rows[2]["pby_ids"] == ["3149"]
    assert rows[2]["kept_hits"][0]["license_slug"] == "public-domain-free-use"


def test_match_candidate_bad_json_counts_as_failed_search(catalogue: dict[str, dict[str, str]]) -> None:
    def fetch(url: str) -> tuple[int, bytes]:
        return 200, b"not json"

    result = tool.match_candidate({"candidate_id": "x", "pby_ids": ["162"], "queries": ["q"]}, catalogue, api_key=SECRET, fetch=fetch)
    assert result["queries"][0]["http_status"] == -1
    assert result["reason"] == "search_failed"


# --- OCR parsing -------------------------------------------------------------------------------------------

TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
    "4\t1\t1\t1\t1\t0\t100\t50\t300\t20\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t300\t50\t100\t20\t90\tשלום\n"
    "5\t1\t1\t1\t1\t2\t100\t52\t150\t22\t70\tעולם\n"
    "5\t1\t1\t1\t2\t1\t100\t90\t50\t20\t95\t   \n"
    "5\t1\t2\t1\t1\t1\t10\t200\t40\t20\t30\t7\n"
    "bad row\n"
)


def test_parse_tesseract_tsv_groups_words_into_scaled_lines() -> None:
    lines = tool.parse_tesseract_tsv(TSV, scale=2.0)
    assert [line.text for line in lines] == ["שלום עולם", "7"]
    assert lines[0].bbox == (200, 100, 600, 48)
    assert lines[0].confidence == 80.0
    assert lines[0].letters == 8
    assert lines[1].index == 1


# --- alignment ---------------------------------------------------------------------------------------------


def test_longest_increasing_chain() -> None:
    pairs = [(0, 5), (1, 1), (2, 2), (3, 9), (4, 3), (5, 4)]
    assert tool.longest_increasing_chain(pairs) == [(1, 1), (2, 2), (4, 3), (5, 4)]
    assert tool.longest_increasing_chain([]) == []


def test_unique_grams_keeps_only_unique() -> None:
    assert tool.unique_grams("abcabcx", 3) == {"bca": 1, "cab": 2, "bcx": 4}


OCR_CONFUSIONS = str.maketrans({"ד": "ר", "ה": "ת", "ב": "כ"})


def _ocr_like(text: str, every: int = 9) -> str:
    """Simulate OCR on PBY text: no niqqud, low-high quotes, and a confusable letter every few letters."""

    plain = tool.strip_marks(text).replace('"', ",,")
    out = []
    letters = 0
    for char in plain:
        if char in tool.HEBREW_LETTERS:
            letters += 1
            if letters % every == 0:
                char = char.translate(OCR_CONFUSIONS)
        out.append(char)
    return "".join(out)


def _lines(text: str, width: int = 48) -> list[str]:
    lines: list[str] = []
    current = ""
    for word in text.split():
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def _page(texts: list[str], *, top: int = 100) -> list[tool.OcrLine]:
    return [tool.OcrLine(index, (50, top + 50 * index, 900, 40), text, 90.0) for index, text in enumerate(texts)]


def _work_pages() -> tuple[str, list[str], list[str]]:
    text = tool.pby_body(_excerpt())
    lines = _lines(_ocr_like(text))
    half = len(lines) // 2
    return text, lines[:half], lines[half:]


def test_align_pages_locates_pages_and_classifies_extra_lines() -> None:
    text, first, second = _work_pages()
    page_one = _page(["חיי אנשי השם", *first])  # a running header PBY lacks
    page_two = _page([*second[:5], "שורה זרה לגמרי שאינה מופיעה בטקסט כלל וכלל ועיקר", *second[5:]])
    outside = _page(["קטע מיצירה אחרת שאין לה קשר לטקסט הזה בכלל", "ועוד שורה אחרת לגמרי שאין בה דבר מן הטקסט"])
    alignments = tool.align_pages(text, [page_one, page_two, outside])
    classes = [[entry.status for entry in page] for page in alignments]
    assert classes[0][0] == tool.LINE_HEADER
    assert set(classes[0][1:]) == {tool.LINE_MATCHED}
    assert classes[1][5] == tool.LINE_UNMATCHED
    assert set(classes[2]) == {tool.LINE_UNMATCHED}
    starts = [entry.pby_start for page in alignments for entry in page if entry.status == tool.LINE_MATCHED]
    assert starts == sorted(starts)
    records = tool.build_page_records(alignments, text, [{"@id": f"c{i}", "width": 1000, "height": 1600} for i in range(3)], [0, 1, 2])
    first_record, second_record, outside_record = records
    assert first_record["status"] == tool.PAGE_ALIGNED
    assert first_record["quality"] == "high"
    assert first_record["crop"]["status"] == tool.CROP_CROPPED
    assert first_record["crop"]["bbox"][1] >= 140  # the header line ends at y=140
    assert "running_header_or_page_number_omitted" in first_record["difference_classes"]
    assert "quote_style_normalized" in first_record["difference_classes"]
    assert second_record["crop"]["status"] == tool.CROP_REVIEW
    assert second_record["crop"]["untranscribed_lines_inside"] == [5]
    assert outside_record["status"] == tool.PAGE_OUTSIDE
    assert outside_record["crop"]["status"] == tool.CROP_NONE
    # The two located page spans tile the work text with no letters left over between them.
    assert second_record["differences"]["pby_letters_not_located_before_page"] == 0
    assert first_record["pby_span"]["end"] <= second_record["pby_span"]["start"]
    assert first_record["text"] == text[first_record["pby_span"]["start"] : first_record["pby_span"]["end"]]
    for key, value in tool.SILVER_STATUS.items():
        assert first_record[key] == value
    assert first_record["reference_eligible"] is False


def test_align_pages_marks_relocated_footnotes() -> None:
    text, first, second = _work_pages()
    note = "הערה זו נדפסה בתחתית העמוד אך בטקסט היא עברה אל סוף היצירה כולה"
    # PBY moves the page's footnote to the end of the work, after the next page's text.
    work = f"{text}\n\n{note}"
    alignments = tool.align_pages(work, [_page([*first, note]), _page(second)])
    assert alignments[0][-1].status == tool.LINE_RELOCATED
    assert work[alignments[0][-1].pby_start : alignments[0][-1].pby_end] == note
    records = tool.build_page_records(alignments, work, [{"@id": f"c{i}", "width": 1000, "height": 9000} for i in range(2)], [0, 1])
    assert records[0]["differences"]["relocated_lines"] == 1
    assert "footnote_reformatted" in records[0]["difference_classes"]
    assert note not in records[0]["text"]


def test_fill_short_lines_locates_a_paragraph_tail() -> None:
    text, first, _ = _work_pages()
    lines = list(first[:6])
    last_words = lines[5].split()
    # Split the last line so a one-word tail remains, as at the end of a paragraph.
    lines[5] = " ".join(last_words[:-1])
    lines.insert(6, last_words[-1])
    short = tool.skeleton(last_words[-1]).loose
    page = _page(lines)
    alignments = tool.align_pages(text, [page])
    tail = alignments[0][6]
    assert short
    assert tail.status == tool.LINE_MATCHED
    assert tool.strip_marks(text[tail.pby_start : tail.pby_end]).endswith(tool.strip_marks(last_words[-1]).replace(",,", '"')[-2:])


def test_fill_short_lines_inside_a_page() -> None:
    text, first, second = _work_pages()
    work = " ".join(first) + " עוד.\n\n" + " ".join(second)
    alignments = tool.align_pages(work, [_page([*first, "עוד.", *second])])
    tail = alignments[0][len(first)]
    assert len(tail.loose) < tool.MIN_LINE_LETTERS
    assert tail.status == tool.LINE_MATCHED
    assert work[tail.pby_start : tail.pby_end] == "עוד."


def test_catchwords_are_marked_and_kept_out_of_the_page_text() -> None:
    text, first, second = _work_pages()
    catchword = second[0].split()[0]
    # A catchword on its own line at the foot of the first page.
    alignments = tool.align_pages(text, [_page([*first, catchword]), _page(second)])
    assert alignments[0][-1].status == tool.LINE_CATCHWORD
    records = tool.build_page_records(alignments, text, [{"@id": f"c{i}", "width": 1000, "height": 9000} for i in range(2)], [0, 1])
    assert "catchword_omitted" in records[0]["difference_classes"]
    assert records[1]["differences"]["pby_chars_overlapping_previous_page"] == 0
    assert records[0]["crop"]["status"] == tool.CROP_CROPPED
    # A catchword that OCR merged into the last text line: the span is trimmed and the crop flagged.
    merged = [*first[:-1], f"{first[-1]} {catchword}"]
    alignments = tool.align_pages(text, [_page(merged), _page(second)])
    last = alignments[0][-1]
    assert last.status == tool.LINE_MATCHED and last.catchword
    records = tool.build_page_records(alignments, text, [{"@id": f"c{i}", "width": 1000, "height": 9000} for i in range(2)], [0, 1])
    assert records[1]["differences"]["pby_chars_overlapping_previous_page"] == 0
    assert records[0]["differences"]["catchword_lines"] == 1
    assert records[0]["crop"]["status"] == tool.CROP_REVIEW
    assert records[0]["lines"][-1]["carries_catchword"] is True


def test_classify_unmatched_noise_page_numbers_and_narrow_lines() -> None:
    text, first, _ = _work_pages()
    page = [
        tool.OcrLine(0, (50, 50, 900, 40), "12", 90.0),
        *[tool.OcrLine(i + 1, (50, 100 + 50 * i, 900, 40), line, 90.0) for i, line in enumerate(first[:6])],
        tool.OcrLine(7, (50, 230, 900, 15), "זה גמגום של רעש בלי שום משמעות נראית", 20.0),
        tool.OcrLine(8, (1500, 600, 30, 40), "שורה צרה בשוליים", 90.0),
    ]
    alignments = tool.align_pages(text, [page])
    statuses = [entry.status for entry in alignments[0]]
    assert statuses[0] == tool.LINE_PAGE_NUMBER
    assert statuses[7] == tool.LINE_NOISE
    assert statuses[8] == tool.LINE_NON_TEXT
    record = tool.build_page_records(alignments, text, [{"@id": "c", "width": 1600, "height": 2000}], [0])[0]
    assert record["differences"]["low_confidence_noise_lines"] == 1
    assert record["crop"]["noise_lines_inside"] == [7]


def test_drop_out_of_order_demotes_backward_lines() -> None:
    text, first, second = _work_pages()
    # The second half printed before the first: order preservation keeps one run, the other is demoted.
    alignments = tool.align_pages(text, [_page(second[:8]), _page(first[:8])])
    kept = [entry.pby_start for page in alignments for entry in page if entry.status == tool.LINE_MATCHED]
    assert kept == sorted(kept)
    assert any(entry.status != tool.LINE_MATCHED for page in alignments for entry in page)


def test_span_overlap_and_gap_are_measured() -> None:
    text, first, second = _work_pages()
    repeated = first[-3:]
    skipped = second[6:]
    alignments = tool.align_pages(text, [_page(first), _page([*repeated, *skipped])])
    records = tool.build_page_records(alignments, text, [{"@id": f"c{i}", "width": 1000, "height": 4000} for i in range(2)], [0, 1])
    second_record = records[1]
    assert second_record["status"] == tool.PAGE_ALIGNED
    assert second_record["differences"]["pby_letters_not_located_before_page"] > 0 or second_record["differences"]["pby_chars_overlapping_previous_page"] > 0


def test_crop_decision_without_matches_and_padding_limits() -> None:
    assert tool.crop_decision([], (100, 100))["status"] == tool.CROP_NONE
    matched = tool.LineAlignment(0, tool.OcrLine(0, (10, 100, 80, 20), "א"), 0, 1, "א", status=tool.LINE_MATCHED)
    header = tool.LineAlignment(0, tool.OcrLine(1, (10, 70, 80, 25), "ב"), 1, 2, "ב", status=tool.LINE_HEADER)
    below = tool.LineAlignment(0, tool.OcrLine(2, (10, 125, 80, 20), "ג"), 2, 3, "ג", status=tool.LINE_UNMATCHED)
    side = tool.LineAlignment(0, tool.OcrLine(3, (92, 100, 5, 20), "ד"), 3, 4, "ד", status=tool.LINE_RELOCATED)
    left = tool.LineAlignment(0, tool.OcrLine(4, (0, 100, 8, 20), "ה"), 4, 5, "ה", status=tool.LINE_UNMATCHED)
    crop = tool.crop_decision([matched, header, below, side, left], (100, 200))
    assert crop["status"] == tool.CROP_CROPPED
    x, y, w, h = crop["bbox"]
    assert y >= 95 and y + h <= 125 and x >= 8 and x + w <= 92
    assert crop["reason"].startswith("page_carries_text_pby_lacks:")


def test_word_variants_count_plene_spelling() -> None:
    counts = tool._word_variants(["הוא קרא לתלמידיו בשמם"], "הוא קרא לתלמידו בשמם")
    assert counts == {"words_equal": 3, "plene_spelling_variants": 1}


def test_quality_bins_and_difference_classes() -> None:
    assert tool.quality_bin(0.95) == "high"
    assert tool.quality_bin(0.85) == "medium"
    assert tool.quality_bin(0.2) == "low"
    differences = {
        "pby_niqqud": {"pointed_word_share": 0.2},
        "plene_spelling_variants": 2,
        "pby_footnote_markers": 1,
        "relocated_lines": 0,
        "print_low_quotes": 0,
        "running_header_lines": 0,
        "page_number_lines": 1,
        "unmatched_text_lines": 1,
        "pby_letters_not_located_before_page": 25,
        "pby_letters_not_located_in_span": 0,
    }
    assert tool.difference_classes(differences) == [
        "pby_niqqud_present",
        "spelling_variant",
        "footnote_reformatted",
        "running_header_or_page_number_omitted",
        "print_text_not_in_pby_span",
        "pby_text_not_located_on_print",
    ]


def test_summary_lists_interior_pages_missing_from_pby() -> None:
    def page(index: int, status: str, letters: int = 0) -> dict:
        record = {"canvas_index": index, "status": status, "lines": [{"class": tool.LINE_UNMATCHED, "letters": letters}], "crop": {"status": tool.CROP_NONE}}
        if status == tool.PAGE_ALIGNED:
            record.update(
                {
                    "quality": "high",
                    "alignment_score": 0.99,
                    "pby_span": {"start": index * 10, "end": index * 10 + 12},
                    "text": "אבגדהוזחטיכל",
                    "difference_classes": [],
                    "differences": {"plene_spelling_variants": 1, "words_equal": 2},
                    "crop": {"status": tool.CROP_CROPPED},
                }
            )
        return record

    pages = [page(0, tool.PAGE_OUTSIDE, 900), page(1, tool.PAGE_ALIGNED), page(2, tool.PAGE_OUTSIDE, 900), page(3, tool.PAGE_OUTSIDE, 5), page(4, tool.PAGE_ALIGNED)]
    summary = tool.summarize_alignment(pages, "אבגדהוזחטיכל" * 6)
    assert summary["interior_text_pages_not_in_pby"] == [2]
    assert summary["aligned_pages"] == 2
    assert summary["plene_spelling_variants"] == 2
    assert summary["alignment_score"]["median"] == 0.99
    assert tool.summarize_alignment([], "")["alignment_score"]["min"] is None


# --- the committed fixture ---------------------------------------------------------------------------------


def _fixture() -> dict:
    return json.loads((FIXTURE / "fixture.json").read_text(encoding="utf-8"))


def test_fixture_files_are_pinned_by_checksum() -> None:
    fixture = _fixture()
    assert fixture["format"] == tool.FIXTURE_FORMAT
    assert tool.sha256_text(_excerpt()) == fixture["pby_excerpt"]["sha256"]
    assert sha256_file(FIXTURE / fixture["manifest_capture"]) == fixture["manifest_capture_sha256"]
    for page in fixture["pages"]:
        assert sha256_file(FIXTURE / page["image"]) == page["image_sha256"]
        assert sha256_file(FIXTURE / page["localization_ocr"]) == page["localization_ocr_sha256"]
    total = sum(path.stat().st_size for path in FIXTURE.rglob("*") if path.is_file())
    assert total < 400_000


def test_fixture_scan_passes_the_unchanged_nli_gate() -> None:
    fixture = _fixture()
    capture = capture_from_payload(json.loads((FIXTURE / fixture["manifest_capture"]).read_text(encoding="utf-8")))
    decision = decide_nli_rights(display_rights=None, capture=capture)
    assert decision.accepted
    assert decision.license_slug == "public-domain-free-use"
    assert fixture["scan"]["license_slug"] == "public-domain-free-use"
    selected = {entry["canvas_id"]: entry for entry in capture.selected_canvases}
    for page in fixture["pages"]:
        assert selected[page["canvas_id"]]["sha256"] == page["image_sha256"]


def test_fixture_alignment_is_reproducible_and_silver() -> None:
    expected = json.loads((FIXTURE / "expected_alignment.json").read_text(encoding="utf-8"))
    recomputed = tool.fixture_alignment(FIXTURE)
    assert recomputed == expected
    excerpt = _excerpt()
    assert expected["method"]["ocr_role"] == tool.OCR_ROLE
    assert expected["method"]["ocr_text_recorded"] is False
    for page in expected["pages"]:
        assert page["status"] == tool.PAGE_ALIGNED
        assert page["quality"] == "high"
        assert page["text"] == excerpt[page["pby_span"]["start"] : page["pby_span"]["end"]]
        assert page["text_sha256"] == tool.sha256_text(page["text"])
        assert page["text_provenance"] == "human_typed_edition_text_aligned"
        assert page["adjudication_status"] == "not_adjudicated"
        assert page["reference_eligible"] is False
        x, y, w, h = page["crop"]["bbox"]
        width, height = page["canvas_size"]
        assert 0 <= x and 0 <= y and x + w <= width and y + h <= height
        assert page["crop"]["method"] == tool.CROP_METHOD
        assert "running_header_or_page_number_omitted" in page["difference_classes"]
    # The excerpt's pages tile the PBY text in order.
    first, second = expected["pages"]
    assert first["pby_span"]["end"] < second["pby_span"]["start"]


def test_fixture_outputs_carry_no_ocr_text_or_local_paths() -> None:
    expected_text = (FIXTURE / "expected_alignment.json").read_text(encoding="utf-8")
    fixture_text = (FIXTURE / "fixture.json").read_text(encoding="utf-8")
    for text in (expected_text, fixture_text):
        assert "/Users/" not in text and "/home/" not in text and "\\\\" not in text
    expected = json.loads(expected_text)
    ocr_lines = tool.parse_tesseract_tsv((FIXTURE / _fixture()["pages"][0]["localization_ocr"]).read_text(encoding="utf-8"))
    long_ocr = [line.text for line in ocr_lines if len(line.text) > 30]
    serialized = json.dumps(expected["pages"], ensure_ascii=False)
    # Lines with OCR errors cannot appear verbatim; only PBY text and geometry are recorded.
    assert not any(line in serialized for line in long_ocr if line not in excerpt_text())
    for page in expected["pages"]:
        for line in page["lines"]:
            assert set(line) <= {"line", "bbox", "letters", "class", "pby_span", "score", "strict_char_similarity"}


def excerpt_text() -> str:
    return _excerpt()


def test_render_report_is_side_by_side_and_escaped() -> None:
    expected = json.loads((FIXTURE / "expected_alignment.json").read_text(encoding="utf-8"))
    html_text = tool.render_report(expected, image_src=lambda page: f"img/<{page['canvas_index']}>.jpg", pby_text=_excerpt())
    assert html_text.startswith("<!doctype html>")
    assert "img/&lt;15&gt;.jpg" in html_text
    assert "reference_eligible=false" in html_text
    first_line = next(line for line in expected["pages"][0]["lines"] if line["class"] == tool.LINE_MATCHED)
    start, end = first_line["pby_span"]
    assert tool.html.escape(_excerpt()[start:end]) in html_text
    assert "not in PBY span" in html_text


def test_compact_alignment_rows() -> None:
    expected = json.loads((FIXTURE / "expected_alignment.json").read_text(encoding="utf-8"))
    compact = tool.compact_alignment(expected)
    assert compact["pby_id"] == "3149"
    assert [row[0] for row in compact["pages"]] == [15, 16]
    assert len(compact["page_columns"]) == len(compact["pages"][0])


def test_parse_args_and_ranges() -> None:
    args = tool.parse_args(["match", "--candidates", "c.json", "--catalogue", "p.csv", "--out", "o.json", "--captured-on", "2026-11-06"])
    assert args.command == "match" and args.request_delay == 1.5
    args = tool.parse_args(
        [
            "align",
            "--catalogue", "p.csv", "--pby-id", "1", "--pby-text", "t.txt", "--manifest", "m.json",
            "--manifest-url", "u", "--nli-record-id", "r", "--work-dir", "w", "--out-dir", "o", "--generated-on", "d",
        ]
    )  # fmt: skip
    assert args.image_width == 1600
    assert args.tesseract_lang == "heb" and args.tessdata_dir is None
    assert tool._parse_range(None, 3) == [0, 1, 2]
    assert tool._parse_range("1:", 4) == [1, 2, 3]
    assert tool._parse_range(":2", 4) == [0, 1]


def test_pilot_summary_pools_pages_and_match_rows(catalogue: dict[str, dict[str, str]]) -> None:
    search = {"title,contains,מאפו": [_record("1", "אברהם מאפו", 'תרפ"ח', "תושיה")]}
    fetch, _ = _fake_fetch(search, {"1": _manifest(FREE, 5)})
    match_report = tool.run_match(
        [{"candidate_id": "hit", "pby_ids": ["3149"], "queries": ["title,contains,מאפו"]}], catalogue, api_key=SECRET, fetch=fetch, captured_on="2026-11-06"
    )
    expected = json.loads((FIXTURE / "expected_alignment.json").read_text(encoding="utf-8"))
    summary = tool.pilot_summary(match_report, [expected])
    assert summary["format"] == tool.SUMMARY_FORMAT
    assert summary["match"]["summary"]["matched"] == 1
    assert summary["alignment"]["aligned_pages"] == 2
    assert summary["alignment"]["quality"]["high"] == 2
    assert sum(summary["alignment"]["score_histogram_2pt"].values()) == 2
    assert summary["alignment"]["works_detail"][0]["pby_id"] == "3149"


def test_summary_json_keeps_scalar_lists_on_one_line() -> None:
    summary = {"rows": [[1, "aligned", 0.99, ["a", "b"]], [2, "weak", None, []]], "nested": {"x": [1, 2]}, "objects": [{"a": 1}]}
    text = tool.summary_json(summary)
    assert json.loads(text) == summary
    assert '[1, "aligned", 0.99, ["a", "b"]]' in text
    assert '"x": [1, 2]' in text
    assert '\n  [2, "weak", null, []]' in text


# --- OCR model and canvas size options ---------------------------------------------------------------------


def test_tesseract_command_default_and_custom_model() -> None:
    image = Path("c0001.jpg")
    assert tool.tesseract_command(image) == ["tesseract", "c0001.jpg", "-", "-l", "heb", "--psm", "3", "tsv"]
    assert tool.tesseract_command(image, lang="heb", tessdata_dir=Path("models/r6")) == [
        "tesseract", "c0001.jpg", "-", "-l", "heb", "--psm", "3", "--tessdata-dir", "models/r6", "tsv",
    ]  # fmt: skip


def test_ocr_model_id_names_the_dir_and_hashes_the_traineddata(tmp_path: Path) -> None:
    model_dir = tmp_path / "r6"
    model_dir.mkdir()
    (model_dir / "heb.traineddata").write_bytes(b"fine-tuned")
    digest = tool.sha256_text("fine-tuned")
    assert tool.ocr_model_id(model_dir, "heb") == f"r6@{digest[:8]}"


def test_alignment_report_records_ocr_model_only_when_set() -> None:
    kwargs = dict(
        work={}, scan={}, pby_text="", pages=[], canvases=[], canvas_indices=[],
        ocr_engine="tesseract 5 -l heb --psm 3", image_width=1600, generated_on="2026-11-09",
    )  # fmt: skip
    stock = tool.alignment_report(**kwargs)
    assert "ocr_model" not in stock["method"]
    assert list(stock["method"])[:2] == ["ocr_engine", "ocr_role"]
    tuned = tool.alignment_report(**kwargs, ocr_model="r6@73eb18e0")
    assert tuned["method"]["ocr_model"] == "r6@73eb18e0"
    assert {key: value for key, value in tuned["method"].items() if key != "ocr_model"} == stock["method"]


def test_resolve_canvas_size_replaces_only_placeholder_sizes() -> None:
    calls: list[int] = []

    def info(body: dict | None):
        def lookup():
            calls.append(1)
            return body

        return lookup

    real = {"@id": "c1", "width": 2400, "height": 3600}
    assert tool.resolve_canvas_size(real, info({"width": 1, "height": 1})) is real
    assert calls == []
    placeholder = {"@id": "c2", "width": 16, "height": 9}
    resolved = tool.resolve_canvas_size(placeholder, info({"width": 1800, "height": 2700}))
    assert resolved == {"@id": "c2", "width": 1800, "height": 2700, "hocrgen_size_source": "info.json"}
    assert placeholder["width"] == 16
    assert tool.resolve_canvas_size(placeholder, info({"width": 16, "height": 9})) is placeholder
    assert tool.resolve_canvas_size(placeholder, info(None)) is placeholder
    assert tool.resolve_canvas_size({"@id": "c3"}, info({"width": 900, "height": 1400}))["width"] == 900


def test_page_record_notes_a_size_taken_from_info_json() -> None:
    canvas = {"@id": "c2", "label": "2", "width": 1800, "height": 2700, "hocrgen_size_source": "info.json"}
    record = tool.page_record([], "", canvas=canvas, canvas_index=1, gap_before=None)
    assert record["canvas_size"] == [1800, 2700]
    assert record["canvas_size_source"] == "info.json"
    plain = tool.page_record([], "", canvas={"@id": "c1", "width": 10, "height": 10}, canvas_index=0, gap_before=None)
    assert "canvas_size_source" not in plain
