"""Logical-order text from born-digital Hebrew PDFs, and checks that the order is right (F8e).

F8e2 supersedes the ``pdftotext`` conversion below for new captures with ``hocrgen.parsers.pdf_geometry``, which
rebuilds the text from the PDF's glyph layer; the order checks here (``logical_order_issues``) still run on its
output. This module stays for the F8e entries (``poppler_bidi_logical.v1``), which the gate still re-derives.

``pdftotext`` (poppler) writes right-to-left lines in a bidi-markup form: each RTL line opens with RLE
(U+202B) and closes with PDF (U+202C); Hebrew words are already in logical order, but every run of
digits, Latin letters and the neutral characters next to them is wrapped in LRE (U+202A) ... PDF and
written in *visual* (left-to-right display) order. Stripping the control characters is therefore not
enough: ``מס' (תיקון מס' 25), התשע"ו-2016`` comes out as ``מס' ,)25 התשע"ו*2016-``.

``poppler_text_to_logical`` inverts that markup. Inside each LRE run it splits the text into number
tokens (digits with single ``. , : / -`` separators between them), Latin tokens and single neutral
characters, and reverses the token order; tokens themselves keep their internal left-to-right order.
That is the inverse of the Unicode bidi algorithm for numbers and neutrals inside an RTL paragraph. It
is not exact for Latin text next to numbers (``123 ABC`` and ``ABC 123`` look the same once displayed),
so any LRE run with a Latin letter is reported as ``latin_run_order_unverified``.

``logical_order_issues`` checks the result independently of the conversion. A page with any issue must
not become a reference candidate. Reason codes:

- ``bidi_controls_present``: an embedding, override, isolate or mark character is left in the text.
- ``control_characters_present``: a C0/C1 control character other than newline or tab (poppler can
  emit a stray backspace, U+0008).
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
- conversion issues: ``unbalanced_embedding``, ``nested_embedding``, ``hebrew_inside_ltr_embedding``,
  ``latin_run_order_unverified``.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

PDF_BIDI_NORMALIZATION_VERSION = "poppler_bidi_logical.v1"

LRE = "‪"
RLE = "‫"
POP = "‬"
LRO = "‭"
RLO = "‮"
BIDI_MARKS = frozenset("‎‏؜")
BIDI_CONTROL_CHARACTERS = frozenset("‪‫‬‭‮⁦⁧⁨⁩﻿") | BIDI_MARKS

HEBREW_LETTER = "א-ת"
_LTR_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[ .,:/\-'&]+[A-Za-z0-9]+)*|\d+(?:[.,:/\-]\d+)*|.", re.DOTALL)
_MARK_BETWEEN_DIGITS = re.compile(r"(?<=\d)[‎‏؜]+(?=\d)")
_REVERSED_HEBREW_WORD = re.compile(rf"(?<![{HEBREW_LETTER}'\"׳״])[ךםןףץ][{HEBREW_LETTER}]")
_HEBREW_YEAR = re.compile(rf"(?<![{HEBREW_LETTER}])ה?תש[{HEBREW_LETTER}]{{0,2}}[\"״][{HEBREW_LETTER}]")
_GLUED_PUNCTUATION = re.compile(rf"[{HEBREW_LETTER}][,:;.][{HEBREW_LETTER}]")
_REVERSED_SECTION_NUMBER = re.compile(rf"^\.\d+[{HEBREW_LETTER}]?$")

CONVERSION_ISSUES = frozenset(
    {"unbalanced_embedding", "nested_embedding", "hebrew_inside_ltr_embedding", "latin_run_order_unverified"}
)
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


def _ltr_run_to_logical(run: str, issues: set[str]) -> str:
    if any("א" <= char <= "ת" for char in run):
        issues.add("hebrew_inside_ltr_embedding")
    if any(char.isascii() and char.isalpha() for char in run):
        issues.add("latin_run_order_unverified")
    return "".join(reversed(_LTR_TOKEN.findall(run)))


def poppler_line_to_logical(line: str, issues: set[str] | None = None) -> str:
    """Convert one ``pdftotext`` output line from bidi markup to logical order."""

    found = issues if issues is not None else set()
    output: list[str] = []
    stack: list[str] = []
    ltr_run: list[str] = []
    for char in line:
        if stack and stack[-1] == LRE:
            if char == POP:
                stack.pop()
                output.append(_ltr_run_to_logical("".join(ltr_run), found))
                ltr_run = []
            elif char in (LRE, RLE, LRO, RLO):
                found.add("nested_embedding")
                stack.append(char)
            else:
                ltr_run.append(char)
            continue
        if char in (LRE, RLE, LRO, RLO):
            if char in (LRO, RLO) or (char == RLE and stack):
                found.add("nested_embedding")
            stack.append(char)
            continue
        if char == POP:
            if not stack:
                found.add("unbalanced_embedding")
            else:
                stack.pop()
            continue
        output.append(char)
    if stack or ltr_run:
        found.add("unbalanced_embedding")
        output.append("".join(ltr_run))
    text = _MARK_BETWEEN_DIGITS.sub(" ", "".join(output))
    return "".join(char for char in text if char not in BIDI_MARKS)


def poppler_text_to_logical(text: str) -> tuple[str, list[str]]:
    """Convert a ``pdftotext`` page to logical-order plain text.

    Returns the text and the sorted conversion issues. Line structure is kept; trailing spaces, the form
    feed and leading or trailing blank lines are dropped, and the text is NFC-normalized.
    """

    issues: set[str] = set()
    lines = [poppler_line_to_logical(line, issues).rstrip() for line in text.replace("\f", "").split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return unicodedata.normalize("NFC", "\n".join(lines) + "\n"), sorted(issues)


def strip_bidi_controls(text: str) -> str:
    """The naive extraction: remove the control characters and keep the visual runs as they are."""

    return "".join(char for char in text.replace("\f", "") if char not in BIDI_CONTROL_CHARACTERS)


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


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


_LETTER_SPACED_RUN = re.compile(rf"(?<![{HEBREW_LETTER}])(?:[{HEBREW_LETTER}]{{1,2}} ){{3,}}[{HEBREW_LETTER}]{{1,2}}(?![{HEBREW_LETTER}])")


def layout_notes(text: str) -> list[str]:
    """Layout facts worth recording that do not make the order wrong.

    ``letter_spaced_run``: letter-spaced print (signature blocks) comes out as single letters separated by
    irregular spaces (``ב ני מ י ן``). The letters are in order; the spacing does not follow the print.
    """

    return ["letter_spaced_run"] if _LETTER_SPACED_RUN.search(text) else []
