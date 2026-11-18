"""Rashi-pipeline fixes (hocrgen#205 §6d): the Sefaria lemma-stop option, gloss-marker tokens, crop clipping."""

from __future__ import annotations

from hocrgen.fetchers import text_sources as ts
from hocrgen.tools.benyehuda_nli_lines import clip_to_column, unlabelled_print_marker


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
