"""Checks that logical-order Hebrew text from a born-digital PDF is in the right order (F8e).

The text itself is rebuilt from the PDF's glyph layer by ``hocrgen.parsers.pdf_geometry`` (F8e2,
``pdf_glyph_geometry_logical.v1``); these checks run on its output as an independent second line. F8e's
``pdftotext`` conversion (``poppler_bidi_logical.v1``), which inverted poppler's bidi markup, was retired in F8e3 once
no entry used it.

``logical_order_issues`` checks the text independently of the conversion. A page with any issue must
not become a reference candidate. Reason codes:

- ``bidi_controls_present``: an embedding, override, isolate or mark character is left in the text.
- ``control_characters_present``: a C0/C1 control character other than newline or tab (a stray backspace,
  U+0008, in a PDF's text).
- ``reversed_hebrew_word``: a word starts with a final letter form (ך ם ן ף ץ), i.e. a reversed run.
- ``hebrew_year_gregorian_order``: a Hebrew year (``התשע"ו``) is directly followed by a digit or an
  asterisk instead of ``-<year>`` (``התשע"ו*2016-``).
- ``footnote_marker_merged_into_year``: a Hebrew year is followed by ``-`` and five or more digits
  (``התשנ"ה-11995``). A superscript footnote marker was set as a separate run and the extraction glued
  it to the year, on the wrong side.
- ``glued_punctuation``: a Hebrew letter, then ``,`` ``:`` ``;`` or ``.``, then a Hebrew letter with no
  space (``יבוא:אחריהוספת``). Hebrew typesetting never does this; it marks overlapping text runs, such
  as table cells or signature blocks, merged out of order.
- ``section_number_order``: a line that is only ``.1`` or ``.2א`` instead of ``1.`` or ``2א.``.
- ``unbalanced_parentheses``: a ``)`` closes before any ``(`` on the page.
- ``missing_expected_phrase``: a phrase known from independent metadata (the gazette API's table of
  contents, the booklet number and date) does not occur in the text, compared by ``phrase_key`` (whitespace,
  dash and quote variants folded).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

BIDI_MARKS = frozenset("‎‏؜")
BIDI_CONTROL_CHARACTERS = frozenset("‪‫‬‭‮⁦⁧⁨⁩﻿") | BIDI_MARKS

HEBREW_LETTER = "א-ת"
_REVERSED_HEBREW_WORD = re.compile(rf"(?<![{HEBREW_LETTER}'\"׳״])[ךםןףץ][{HEBREW_LETTER}]")
_HEBREW_YEAR = re.compile(rf"(?<![{HEBREW_LETTER}])ה?תש[{HEBREW_LETTER}]{{0,2}}[\"״][{HEBREW_LETTER}]")
_GLUED_PUNCTUATION = re.compile(rf"[{HEBREW_LETTER}][,:;.][{HEBREW_LETTER}]")
_REVERSED_SECTION_NUMBER = re.compile(rf"^\.\d+[{HEBREW_LETTER}]?$")

ORDER_ISSUES = frozenset(
    {
        "bidi_controls_present",
        "control_characters_present",
        "reversed_hebrew_word",
        "hebrew_year_gregorian_order",
        "footnote_marker_merged_into_year",
        "glued_punctuation",
        "section_number_order",
        "unbalanced_parentheses",
        "missing_expected_phrase",
    }
)


_PHRASE_FOLD = str.maketrans({"־": "-", "–": "-", "—": "-", "‑": "-", "―": "-", "״": '"', "“": '"', "”": '"', "„": '"', "׳": "'", "‘": "'", "’": "'"})


def phrase_key(text: str) -> str:
    """The form an expected phrase is matched in: no whitespace, one hyphen for every dash, ASCII quotes.

    The gazette API and the print differ in spacing after commas, in the dash and quote code points (the print
    sets a maqaf, an en dash or a horizontal bar with one glyph) and in stray format characters (the API's titles
    carry RLMs), never in the order of the characters, which is what the phrase check verifies."""

    folded = "".join(char for char in text.translate(_PHRASE_FOLD) if unicodedata.category(char) != "Cf")
    return re.sub(r"\s+", "", folded)


def logical_order_issues(text: str, expected_phrases: Iterable[str] = ()) -> list[str]:
    """Return the sorted reason codes for which ``text`` is not trustworthy logical-order Hebrew."""

    issues: set[str] = set()
    if any(char in BIDI_CONTROL_CHARACTERS for char in text):
        issues.add("bidi_controls_present")
    if any(unicodedata.category(char) == "Cc" and char not in "\n\t" for char in text):
        issues.add("control_characters_present")
    if _REVERSED_HEBREW_WORD.search(text):
        issues.add("reversed_hebrew_word")
    for match in _HEBREW_YEAR.finditer(text):
        following = text[match.end() : match.end() + 1]
        if following.isdigit() or following == "*":
            issues.add("hebrew_year_gregorian_order")
        if re.match(r"[-–]\d{5,}", text[match.end() :]):
            issues.add("footnote_marker_merged_into_year")
    if _GLUED_PUNCTUATION.search(text):
        issues.add("glued_punctuation")
    for line in text.splitlines():
        if _REVERSED_SECTION_NUMBER.match(line.strip()):
            issues.add("section_number_order")
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                issues.add("unbalanced_parentheses")
                break
    folded = phrase_key(text)
    if any(phrase_key(phrase) not in folded for phrase in expected_phrases):
        issues.add("missing_expected_phrase")
    return sorted(issues)
