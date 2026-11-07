"""E2d4b: deterministic reference-text rules, applied to every Wikisource-derived evaluation reference.

``space_before_punctuation.v1`` (maintainer decision 2026-11-07,
``planning/decisions/2026-11-07-space-before-punctuation-rule.md``): Hebrew puts no space before a punctuation mark,
so a stray space before one is fixed always and automatically, and rare wrong fixes are accepted.

The rule: horizontal whitespace (never a line break, so line structure is kept) immediately before a single ``.``
``,`` ``:`` ``;`` ``?`` or ``!`` is removed, and when the mark is then directly followed by a letter one space is
inserted after it (``ודונג ,אם`` -> ``ודונג, אם``). It fires only when the character before the whitespace (past any
niqqud or cantillation marks) is a Hebrew or Latin letter, a geresh, gershayim or quote mark, or a closing bracket.
It never fires on a dot run or spaced-dot ellipsis (``...``, ``. . .``) or any mark followed by another mark, before
a digit, a slash or a backslash, or inside a URL or e-mail address. It only removes and inserts ASCII spaces next to
ASCII marks, so an NFC text stays NFC.

``fix_space_before_punctuation`` is a pure function; other tools import it under this exact name and signature.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Sequence

SPACE_BEFORE_PUNCTUATION_RULE = "space_before_punctuation.v1"
REFERENCE_RULES = (SPACE_BEFORE_PUNCTUATION_RULE,)
RULE_DECISION_RECORDS = {
    SPACE_BEFORE_PUNCTUATION_RULE: "planning/decisions/2026-11-07-space-before-punctuation-rule.md",
}

_MARKS = ".,:;?!"
# Horizontal whitespace only: never \n, \r, \v, \f, U+2028 or U+2029.
_HSPACE = "[ \t   -   　]"
_CANDIDATE = re.compile(f"{_HSPACE}+([{re.escape(_MARKS)}])")
_HSPACE_RUN = re.compile(f"{_HSPACE}*")
_QUOTES = "'\"׳״’”"  # ' " geresh gershayim ’ ”
_CLOSING = ")]}"
_NOT_AFTER = _MARKS + "…/\\"  # another mark, an ellipsis character, a path or URL separator
_URLISH = re.compile(r"://|^www\.|@", re.IGNORECASE)
_TOKEN_END = re.compile(r"\s")


def _is_hebrew_or_latin_letter(char: str) -> bool:
    if not unicodedata.category(char).startswith("L"):
        return False
    code = ord(char)
    if 0x05D0 <= code <= 0x05F2 or 0xFB1D <= code <= 0xFB4F:
        return True
    return "LATIN" in unicodedata.name(char, "")


def _base_before(text: str, index: int) -> str | None:
    """The character before ``index``, skipping combining marks (niqqud, cantillation); None at the text start."""

    while index > 0 and unicodedata.category(text[index - 1]) in ("Mn", "Me"):
        index -= 1
    return text[index - 1] if index > 0 else None


def _token_before(text: str, index: int) -> str:
    start = index
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    return text[start:index]


def _token_after(text: str, index: int) -> str:
    match = _TOKEN_END.search(text, index)
    return text[index:match.start() if match else len(text)]


def space_before_punctuation_fixes(text: str) -> list[tuple[int, int, str]]:
    """The rule's edits on ``text`` as ``(start, end, replacement)``, in text order, non-overlapping.

    Each edit spans the whitespace run and the mark (``text[start:end]`` is e.g. ``" ,"``) and replaces it by the
    mark, or by the mark and one space when a letter follows the mark directly.
    """

    edits = []
    for match in _CANDIDATE.finditer(text):
        start, mark_at = match.start(), match.start(1)
        end = mark_at + 1
        before = _base_before(text, start)
        if before is None or not (_is_hebrew_or_latin_letter(before) or before in _QUOTES or before in _CLOSING):
            continue
        following = text[end:end + 1]
        after_space = text[_HSPACE_RUN.match(text, end).end():][:1]
        if (following and following in _NOT_AFTER) or (after_space and after_space in _MARKS + "…"):
            continue  # a dot run, a spaced-dot ellipsis, a doubled mark, a path
        if following.isdigit():
            continue  # a number (.5, ,000)
        if _URLISH.search(_token_before(text, start)) or _URLISH.search(_token_after(text, end)):
            continue
        replacement = text[mark_at] + (" " if following and following.isalpha() else "")
        edits.append((start, end, replacement))
    return edits


def apply_edits(text: str, edits: Iterable[tuple[int, int, str]]) -> str:
    out, position = [], 0
    for start, end, replacement in sorted(edits):
        out.append(text[position:start])
        out.append(replacement)
        position = end
    out.append(text[position:])
    return "".join(out)


def fix_space_before_punctuation(text: str) -> tuple[str, int]:
    """``text`` with ``space_before_punctuation.v1`` applied, and the number of fixes."""

    edits = space_before_punctuation_fixes(text)
    return apply_edits(text, edits), len(edits)


_RULE_FIXES = {SPACE_BEFORE_PUNCTUATION_RULE: space_before_punctuation_fixes}


def rule_fixes(rule: str, text: str) -> list[tuple[int, int, str]]:
    if rule not in _RULE_FIXES:
        raise ValueError(f"unknown reference rule {rule!r}")
    return _RULE_FIXES[rule](text)


def _overlaps(edit: tuple[int, int, str], span: tuple[int, int]) -> bool:
    (a, b, _), (c, d) = edit, span
    return (a < d and c < b) if c < d else a <= c <= b


def shift_offset(position: int, edits: Sequence[tuple[int, int, str]]) -> int:
    """``position`` in the text after ``edits``; no edit may strictly contain it."""

    return position + sum(len(replacement) - (end - start) for start, end, replacement in edits if end <= position)


def apply_reference_rules(text: str, rules: Sequence[str] = REFERENCE_RULES, *,
                          protected: Iterable[tuple[int, int]] = ()) -> dict:
    """Apply ``rules`` in order. A fix that overlaps a ``protected`` span (a human-decided audit span, an excluded
    span) is skipped; ``protected`` offsets are in ``text`` and are carried through each rule.

    Returns ``{"text", "applied": [{"rule", "fixes"[, "skipped_protected"]}], "edits": [per rule, the edits made]}``.
    """

    spans = [tuple(span) for span in protected]
    applied, all_edits = [], []
    for rule in rules:
        edits, skipped = [], 0
        for edit in rule_fixes(rule, text):
            if any(_overlaps(edit, span) for span in spans):
                skipped += 1
            else:
                edits.append(edit)
        text = apply_edits(text, edits)
        spans = [(shift_offset(start, edits), shift_offset(end, edits)) for start, end in spans]
        applied.append({"rule": rule, "fixes": len(edits), **({"skipped_protected": skipped} if skipped else {})})
        all_edits.append(edits)
    return {"text": text, "applied": applied, "edits": all_edits, "protected": spans}


def rule_covers(rule: str, text: str, start: int, end: int, proposed: str) -> bool:
    """Whether ``rule`` makes exactly the change ``text[start:end] -> proposed`` there: the rule's edits that touch
    ``[start, end]`` produce the same full text as the proposal alone, and there is at least one."""

    near = [edit for edit in rule_fixes(rule, text) if edit[0] <= end and start <= edit[1]]
    if not near:
        return False
    return apply_edits(text, near) == text[:start] + proposed + text[end:]
