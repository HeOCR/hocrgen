"""Network-free tests for the S16 printed glyph harvester (hocrgen.tools.glyph_harvest)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

pytest.importorskip("numpy")
pytest.importorskip("scipy")

from hocrgen.tools import glyph_harvest as gh  # noqa: E402

X_HEIGHT = 20
GAP = 3
WORD_GAP = 16
BASELINE = 80


def _draw_glyph(draw: ImageDraw.ImageDraw, char: str, right: int, baseline: int) -> int:
    """Draw a distinct toy shape for ``char`` ending at x=``right``; return its left edge."""
    h = X_HEIGHT
    if char == "א":  # filled square
        draw.rectangle([right - 18, baseline - h, right - 1, baseline - 1], fill=0)
        return right - 18
    if char == "ב":  # hollow square
        draw.rectangle([right - 16, baseline - h, right - 1, baseline - 1], outline=0, width=3)
        return right - 16
    if char == "ס":  # ring
        draw.ellipse([right - 18, baseline - h, right - 1, baseline - 1], outline=0, width=3)
        return right - 18
    if char == "ה":  # top bar with right leg, plus a separate left leg (two components)
        draw.rectangle([right - 16, baseline - h, right - 1, baseline - h + 3], fill=0)
        draw.rectangle([right - 4, baseline - h, right - 1, baseline - 1], fill=0)
        draw.rectangle([right - 16, baseline - h + 7, right - 13, baseline - 1], fill=0)
        return right - 16
    if char == "ש":  # three teeth on a bottom bar
        draw.rectangle([right - 18, baseline - 4, right - 1, baseline - 1], fill=0)
        for x in (right - 18, right - 10, right - 3):
            draw.rectangle([x, baseline - h, x + 2, baseline - 1], fill=0)
        return right - 18
    if char == ".":
        draw.rectangle([right - 3, baseline - 4, right - 1, baseline - 1], fill=0)
        return right - 3
    raise AssertionError(char)


def _page(tmp_path: Path, words: list[str]) -> tuple[Path, list[gh.OcrWord]]:
    image = Image.new("L", (900, 200), 255)
    draw = ImageDraw.Draw(image)
    x = 880
    boxes = []
    for word in words:
        right = x
        for char in gh.visual_order(word):
            x = _draw_glyph(draw, char, x, BASELINE) - GAP
        left = x + GAP
        boxes.append(gh.OcrWord(text=word, box=(left, BASELINE - X_HEIGHT, right, BASELINE), line_key=(1, 1, 1)))
        x = left - WORD_GAP
    path = tmp_path / "page.png"
    image.save(path)
    return path, boxes


def test_visual_order_flips_digit_runs_only():
    assert gh.visual_order("שלום") == list("שלום")
    assert gh.visual_order("1948,") == ["8", "4", "9", "1", ","]
    assert gh.visual_order("ב-1948") == ["ב", "-", "8", "4", "9", "1"]
    assert gh.visual_order("3.14") == ["4", "1", ".", "3"]


def test_harvestable_word_skips_marks_and_latin():
    assert gh.harvestable_word("שלום,")
    assert not gh.harvestable_word("שָׁלוֹם")
    assert not gh.harvestable_word("OCR")


def test_pair_words_tolerates_ocr_errors_and_extra_words():
    pairs = gh.pair_words(["שלום", "עולם", "ספר"], ["רסב", "שלוס", "עולס", "ספר"])
    assert pairs == [(0, 1), (1, 2), (2, 3)]


def test_word_groups_merge_two_component_letters(tmp_path):
    path, boxes = _page(tmp_path, ["אהב"])
    ink = gh.sauvola(gh.load_gray(path))
    groups, _, _ = gh.word_groups(ink, boxes[0].box)
    assert len(groups) == 3  # ה's separate left leg merged into its group
    assert groups[0].box[0] > groups[1].box[0] > groups[2].box[0]  # right to left


def test_harvest_unit_labels_each_glyph_with_reference_text(tmp_path):
    words = ["אבס", "שהא.", "בסש"]
    path, boxes = _page(tmp_path, words)
    # The OCR text is wrong in places; it only locates the words.
    ocr = [gh.OcrWord("אבם", boxes[0].box, boxes[0].line_key), gh.OcrWord("שהא.", boxes[1].box, boxes[1].line_key), gh.OcrWord("בסש", boxes[2].box, boxes[2].line_key)]
    unit = gh.Unit(style_id="toy", page_id="toy:p1", image_path=path, reference_text=" ".join(words), ocr_words=ocr)
    stats = gh.PageStats()
    found = gh.harvest_unit(unit, stats)
    assert [c.char for c in found] == [ch for word in words for ch in gh.visual_order(word)]
    for candidate in found:
        assert candidate.mask.any()
        assert abs(candidate.x_height - X_HEIGHT) <= 1
        bottom = int(candidate.mask.nonzero()[0].max()) + 1
        assert abs(bottom - candidate.baseline) <= 1  # every toy glyph sits on the baseline
    assert stats.word_gaps and min(stats.word_gaps) >= WORD_GAP - 1


def test_harvest_unit_rejects_word_whose_glyph_count_differs(tmp_path):
    path, boxes = _page(tmp_path, ["אבס"])
    unit = gh.Unit("toy", "toy:p1", path, "אבסא", [gh.OcrWord("אבסא", boxes[0].box, boxes[0].line_key)])
    assert gh.harvest_unit(unit, gh.PageStats()) == []


def _candidates(tmp_path: Path, repeats: int = 6) -> list[gh.Candidate]:
    words = ["אבס", "סבא", "בסש", "שאב"] * repeats
    path, boxes = _page(tmp_path, words[:8])
    out = []
    for round_ in range(repeats // 2):
        unit = gh.Unit("toy", f"toy:p{round_}", path, " ".join(words[:8]), boxes)
        out += gh.harvest_unit(unit, gh.PageStats())
    return out


def test_verify_style_drops_a_mislabelled_glyph(tmp_path):
    found = _candidates(tmp_path)
    wrong = next(c for c in found if c.char == "א")
    wrong.char = "ב"
    kept = gh.verify_style(found)
    assert wrong not in kept
    assert len(kept) == len(found) - 1
    assert all(0.0 < c.score <= 1.0 for c in kept)


def test_split_faces_keeps_a_single_face_style_whole(tmp_path):
    found = _candidates(tmp_path)
    assert gh.split_faces(found, min_char=5, min_face=1) == [found]


def test_write_bank_index_and_files(tmp_path):
    kept = gh.verify_style(_candidates(tmp_path))
    out = tmp_path / "bank"
    style = gh.StyleSource("toy", "toy_source", "work-1", "PD")
    stats = gh.PageStats(letter_gaps=[3, 3, 4], word_gaps=[16, 16], line_pitches=[40.0], line_widths=[800], page_sizes=[(900, 200)])
    index = gh.write_bank(out, bank_id="pgb-test", config={"a": 1}, sources=[{"source_id": "toy_source"}], exclusions=[], styles=[style], glyphs_by_style={"toy": kept}, stats_by_style={"toy": stats}, min_style_glyphs=1)
    assert index["schema"] == "printed_glyph_bank.v1"
    glyph_bytes = (out / "glyphs.jsonl").read_bytes()
    assert index["glyphs_sha256"] == hashlib.sha256(glyph_bytes).hexdigest()
    records = [json.loads(line) for line in glyph_bytes.decode().splitlines()]
    assert len(records) == index["glyph_count"] == len(kept)
    for record in records:
        assert len(record["char"]) == 1
        assert not record["asset_path"].startswith("/") and ".." not in record["asset_path"]
        with Image.open(out / record["asset_path"]) as crop, Image.open(out / record["mask_path"]) as mask:
            assert crop.size == mask.size == tuple(record["size"])
        x0, y0, x1, y1 = record["ink_box"]
        assert 0 <= x0 < x1 <= record["size"][0] and 0 <= y0 < y1 <= record["size"][1]
    metrics = index["styles"][0]["metrics"]
    assert metrics["word_gap_px"][1] == 16 and metrics["line_pitch_px"] == 40.0
    assert sum(index["styles"][0]["char_counts"].values()) == len(records)


def test_detached_specks_join_their_letter_mask(tmp_path):
    # ה whose left leg is broken into specks too small to be letters: they must stay in ה's mask.
    image = Image.new("L", (200, 120), 255)
    draw = ImageDraw.Draw(image)
    right = 150
    draw.rectangle([right - 16, BASELINE - X_HEIGHT, right - 1, BASELINE - X_HEIGHT + 3], fill=0)
    draw.rectangle([right - 4, BASELINE - X_HEIGHT, right - 1, BASELINE - 1], fill=0)
    for y in range(BASELINE - X_HEIGHT + 7, BASELINE - 1, 3):
        draw.rectangle([right - 16, y, right - 15, y], fill=0)  # 2-pixel specks
    left = _draw_glyph(draw, "א", right - 16 - GAP, BASELINE)
    path = tmp_path / "speck.png"
    image.save(path)
    box = (left, BASELINE - X_HEIGHT, right, BASELINE)
    unit = gh.Unit("toy", "toy:p1", path, "הא", [gh.OcrWord("הא", box, (1, 1, 1))])
    found = gh.harvest_unit(unit, gh.PageStats())
    assert [c.char for c in found] == ["ה", "א"]
    he = found[0]
    ys, xs = he.mask.nonzero()
    leg = xs <= xs.min() + 1  # the leftmost columns hold only the leg specks
    assert (ys[leg] > he.baseline - X_HEIGHT // 2).sum() >= 3  # specks below the bar are in ה's mask


def test_complete_rejects_unassigned_ink_inside_a_glyph_box():
    import numpy

    labels = numpy.zeros((10, 10), dtype=int)
    labels[2:8, 2:8] = 1
    ink = labels > 0
    group = gh.Group([1], (2, 2, 8, 8))
    assert gh._complete(ink, labels, (0, 0), [group])
    ink[4:7, 3] = True  # ink no glyph owns, e.g. a lost stroke
    labels[2:8, 3] = 0
    assert not gh._complete(ink, labels, (0, 0), [group])


def test_write_bank_drops_styles_without_evidence(tmp_path):
    kept = gh.verify_style(_candidates(tmp_path))
    style = gh.StyleSource("toy", "toy_source", "work-1", "PD")
    index = gh.write_bank(tmp_path / "bank", bank_id="pgb-test", config={}, sources=[], exclusions=[], styles=[style], glyphs_by_style={"toy": kept}, stats_by_style={"toy": gh.PageStats()}, min_style_glyphs=1)
    assert index["styles"] == [] and index["glyph_count"] == 0  # no line pitch measured


def test_single_tick_is_not_kept_as_double_mark():
    singles = [("'", 10.0, 32.0, 1)] * 6
    marks = [
        *singles,
        ('"', 10.0, 32.0, 1),  # one tick under a '"' label (single quotation marks in print)
        ('"', 18.0, 32.0, 1),  # two touching ticks
        ("״", 9.0, 32.0, 2),  # two separate ticks, close together
    ]
    assert gh.implausible_double_marks(marks) == {6}
    # Without enough singles, the floor is a third of the x-height.
    assert gh.implausible_double_marks([('"', 9.0, 32.0, 1), ('"', 12.0, 32.0, 1)]) == {0}


def test_broken_colon_is_not_labelled_colon():
    dot = gh.Group([1], (0, 15, 4, 19))
    assert not gh._plausible([dot], [":"], baseline=19, x_height=20.0)
    colon = gh.Group([1, 2], (0, 6, 4, 19))
    assert gh._plausible([colon], [":"], baseline=19, x_height=20.0)


def test_benyehuda_units_convert_canvas_line_boxes_to_image_pixels(tmp_path):
    # F8f stores line bboxes in IIIF canvas pixels; the cached image (and its TSV) is narrower, here half as wide.
    root = tmp_path / "f8f"
    record = "990000000000205171"
    (root / "work" / record / "img").mkdir(parents=True)
    (root / "work" / record / "ocr").mkdir(parents=True)
    (root / "pby" / "txt").mkdir(parents=True)
    (root / "out" / "7").mkdir(parents=True)
    Image.new("L", (900, 200), 255).save(root / "work" / record / "img" / "c0000.jpg")
    rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "1\t1\t0\t0\t0\t0\t0\t0\t900\t200\t-1\t"]
    for line_num, (top, words) in enumerate([(60, ["אבס", "בא"]), (140, ["סבא", "אב"])], start=1):
        for word_num, (left, word) in enumerate(zip((700, 600), words), start=1):
            rows.append(f"5\t1\t1\t1\t{line_num}\t{word_num}\t{left}\t{top}\t80\t20\t95\t{word}")
    (root / "work" / record / "ocr" / "c0000.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    text = "אבס בא\nסבא אב\n"
    (root / "pby" / "txt" / "m7.txt").write_text(text, encoding="utf-8")
    line = lambda index, top, span: {"line": index, "bbox": [1200, top * 2, 400, 40], "class": "matched", "score": 1.0, "pby_span": span}
    alignment = {
        "scan": {"nli_record_id": record, "license_slug": "public-domain-free-use", "rights_decision": {"decision": "accepted"}},
        "pages": [{"canvas_index": 0, "canvas_size": [1800, 400], "status": "aligned", "lines": [line(0, 60, [0, 6]), line(1, 140, [7, 13])]}],
    }
    (root / "out" / "7" / "alignment.json").write_text(json.dumps(alignment, ensure_ascii=False), encoding="utf-8")

    _, units = gh.benyehuda_units(root)
    units = list(units)

    assert [unit.reference_text for unit in units] == ["אבס בא", "סבא אב"]
    assert [[word.text for word in unit.ocr_words] for unit in units] == [["אבס", "בא"], ["סבא", "אב"]]
