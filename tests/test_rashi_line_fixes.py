"""Rashi-pipeline fixes (hocrgen#205 §6d): the Sefaria lemma-stop option, gloss-marker tokens, crop clipping."""

from __future__ import annotations

from PIL import Image, ImageDraw

from hocrgen.fetchers import text_sources as ts
from hocrgen.tools.benyehuda_nli_lines import (
    clip_to_column,
    matched_crop_region,
    unboxed_marker_ink,
    unlabelled_print_marker,
)


def test_lemma_stop_turns_the_lemma_dash_into_a_stop_and_keeps_markers_pinned() -> None:
    version = {"title": "Rashi on X", "versionTitle": "Vilna 1886", "schema": None,
               "text": [["תנן התם - במסכת מדות", 'ועגלה ערופה - <i data-commentator="Y" data-order="1"></i>שאסור בהנאה']]}
    plain, _ = ts.sefaria_text(version)
    stop, stats = ts.sefaria_text(version, lemma_stop=True)
    assert " - " in plain and stop == "תנן התם. במסכת מדות\nועגלה ערופה. שאסור בהנאה\n"
    assert stats["removed"]["lemma_dashes"] == 2
    m = ts.sefaria_marker_offsets(version, lemma_stop=True)
    assert m["text_sha256"] == ts.sha256_bytes(stop.encode("utf-8"))
    assert [stop[i:i + 2] for i in m["anchor_offsets"]] == ["שא"]


def test_a_gloss_marker_token_the_label_lacks_is_found() -> None:
    assert (unlabelled_print_marker("פליג ר׳ יהושע דטעמא", "פליג ר׳ יהושע יח] דטעמא") or "").strip() == "יח]"
    assert unlabelled_print_marker("העוף למטה ליתא זה", "העוף למטה ליתא * זה") is not None
    assert unlabelled_print_marker("שלום עולם", "שלום עולם") is None


def test_clip_to_column_stops_padding_before_a_neighbour_on_the_row() -> None:
    line = (100, 10, 300, 30)  # x, y, w, h
    words = [("n", 90.0, (40, 12, 70, 38)), ("m", 90.0, (430, 14, 470, 36)), ("own", 90.0, (150, 12, 200, 38)),
             ("above", 90.0, (0, -40, 90, -10))]
    assert clip_to_column((60, 10, 460, 40), line, words) == (85, 10, 415, 40)


def test_selects_matching_region_in_a_merged_ocr_line() -> None:
    text = "שלום עולם גדול"
    main = [("שלום", 95, (160, 10, 190, 30)), ("עולם", 95, (120, 10, 151, 30)),
            ("גדול", 95, (80, 10, 111, 30))]
    margin = [("הערה", 95, (5, 16, 28, 27))]
    result = matched_crop_region(text, 0, len(text), main + margin, 20)
    assert result is not None
    (start, end, _, _), words = result
    assert (text[start:end], words) == (text, main)


def test_rejects_two_regions_matching_the_same_edition_span() -> None:
    text = "שלום עולם"
    words = [("שלום", 95, (160, 10, 190, 30)), ("עולם", 95, (120, 10, 151, 30)),
             ("שלום", 95, (50, 10, 80, 30)), ("עולם", 95, (12, 10, 43, 30))]
    assert matched_crop_region(text, 0, len(text), words, 20) is None


def test_isolated_marker_missing_from_ocr_is_screened_in_crop_coordinates() -> None:
    image = Image.new("L", (110, 50), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 19, 40, 33), fill=0)
    draw.rectangle((60, 19, 85, 33), fill=0)
    words = [("עולם", 95, (60, 19, 86, 34)), ("שלום", 95, (20, 19, 41, 34))]
    box = (14, 14, 92, 38)
    assert not unboxed_marker_ink(image, box, words, 15)
    draw.line((46, 22, 52, 28), fill=0)
    draw.line((46, 28, 52, 22), fill=0)
    assert unboxed_marker_ink(image, box, words, 15)
