"""Deterministic unit checks for the training-candidate screen."""
from PIL import Image

from hocrgen.tools.phist_eh_screen import Word, screen


def test_exact_word_evidence_catches_unmarked_abbreviation():
    image = Image.new("L", (100, 30), 255)
    page = (Word("ר", 40, 5, 10, 15), Word("אחד", 65, 5, 20, 15))
    reasons = screen("אחד מאתים", [0, 0, 100, 30], [0, 0, 100, 30], page, image)
    assert "ocr_label_disagreement" in reasons
    assert not screen("אחד ר", [0, 0, 100, 30], [0, 0, 100, 30], page, image)


def test_border_ink_rejects_cut_words_and_neighbour_lines():
    page = (Word("שלום", 35, 5, 25, 15),)
    image = Image.new("L", (100, 30), 255)
    image.putpixel((99, 10), 0)
    for x in range(20):
        image.putpixel((x + 10, 0), 0)
    reasons = screen("שלום", [0, 0, 100, 30], [0, 0, 100, 30], page, image)
    assert "side_border_ink" in reasons
    assert "vertical_border_ink" in reasons


def test_missing_ocr_fails_closed():
    assert "missing_ocr_evidence" in screen("שלום", [0, 0, 100, 30], [0, 0, 100, 30], (), Image.new("L", (100, 30), 255))
