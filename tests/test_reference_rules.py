"""E2d4b: space_before_punctuation.v1, the maintainer's always-on reference rule (pure, network-free)."""
from __future__ import annotations

import unicodedata

import pytest

from hocrgen.reference_rules import (
    REFERENCE_RULES,
    RULE_DECISION_RECORDS,
    SPACE_BEFORE_PUNCTUATION_RULE,
    apply_reference_rules,
    fix_space_before_punctuation,
    rule_covers,
    shift_offset,
    space_before_punctuation_fixes,
)

R = SPACE_BEFORE_PUNCTUATION_RULE


def test_the_rule_name_record_and_signature_are_stable() -> None:
    # Other tools import exactly these names (e.g. a line-verification exporter); keep them.
    assert R == "space_before_punctuation.v1" and REFERENCE_RULES == (R,)
    assert RULE_DECISION_RECORDS[R] == "planning/decisions/2026-11-07-space-before-punctuation-rule.md"
    assert fix_space_before_punctuation("") == ("", 0)
    text, count = fix_space_before_punctuation("ודונג ,אם")
    assert isinstance(text, str) and isinstance(count, int)


@pytest.mark.parametrize("before, after, fixes", [
    ("ודונג ,אם", "ודונג, אם", 1),                          # the Masa ba-Arav pattern the maintainer accepted
    ("בעיר .ובשנת", "בעיר. ובשנת", 1),
    ("הגויים לאמר :הנה נלכה", "הגויים לאמר: הנה נלכה", 1),
    ("מה זאת ;ומדוע", "מה זאת; ומדוע", 1),
    ("האמנם ?כן", "האמנם? כן", 1),
    ("הוי !אחי", "הוי! אחי", 1),
    ("ודונג , אם", "ודונג, אם", 1),                         # a space already follows: just remove the one before
    ("ודונג  \t,אם", "ודונג, אם", 1),                       # any run of horizontal whitespace
    ("ודונג ,אם", "ודונג, אם", 1),                     # NBSP is horizontal whitespace
    ("סוף הפרק .", "סוף הפרק.", 1),                          # at the end of the text
    ("סוף הפרק .\nפרק חדש", "סוף הפרק.\nפרק חדש", 1),       # before a line break: no space added
    ("מלה ,)", "מלה,)", 1),                                  # followed by a non-letter: no space added
    ("אמר :\"שלום\"", "אמר:\"שלום\"", 1),
    ("סְלַח נָא :אוֹמְצֵי", "סְלַח נָא: אוֹמְצֵי", 1),        # niqqud on the letter before the space
    ("וַיֹּאמַ֖ר ,לֹא", "וַיֹּאמַ֖ר, לֹא", 1),                  # cantillation too
    ("כ\"ב .ושם", "כ\"ב. ושם", 1),                          # gershayim-abbreviated number: the letter before fires
    ("ר' ,ושם", "ר', ושם", 1),                               # a quote mark before
    ("ר׳ ,ושם", "ר׳, ושם", 1),                               # geresh
    ("רמב״ם ,ושם", "רמב״ם, ושם", 1),                         # gershayim
    ("(ראה שם) ,ועוד", "(ראה שם), ועוד", 1),                # closing bracket
    ("[1] ,ועוד", "[1], ועוד", 1),
    ("the word ,next", "the word, next", 1),                 # Latin letters
    ("Café ,oui", "Café, oui", 1),
    ("אחד ,שנים ,שלשה .ארבעה", "אחד, שנים, שלשה. ארבעה", 3),
])
def test_a_stray_space_before_a_mark_moves_after_it(before: str, after: str, fixes: int) -> None:
    assert fix_space_before_punctuation(before) == (after, fixes)


@pytest.mark.parametrize("text", [
    "ויאמר ... ויהי",            # a dot run
    "ויאמר ...",
    "ויאמר . . . ויהי",          # a spaced-dot ellipsis
    "ויאמר . . .",
    "ויאמר .. ויהי",
    "ויאמר ,, ויהי",             # a doubled mark
    "ויאמר ?! ויהי",             # marks in a run
    "ויאמר , . ויהי",
    "ויאמר .…",              # an ellipsis character after
    "שאלה? !",                   # preceded by another mark
    "מלה. ,",
    "מלה - ,",                   # a dash before
    "מלה־ ,",                    # a maqaf before
    "1 ,000",                    # numbers
    "3 .14",
    "בשנת ,1850",                 # a digit right after the mark
    "מחיר .5",
    "www.example .com",          # URLs and e-mail
    "http://example.org/a .b",
    "user@example .com",
    "ראה ,http://x.org",
    "מלה ,/",
    "מלה\n,ועוד",                 # a line break is never touched
    "מלה\n ,ועוד",                # whitespace after a line break: nothing before it on the line
    " ,ועוד",                    # at the start of the text
    "׃ ,ועוד",               # sof pasuq (a mark) before
    "מלה ׃",                     # not one of the six marks
    "מלה,ועוד",                   # no space before: nothing to do (no space is inserted either)
])
def test_excluded_cases_are_left_alone(text: str) -> None:
    assert fix_space_before_punctuation(text) == (text, 0)


def test_lines_are_kept_and_nfc_is_preserved() -> None:
    text = unicodedata.normalize("NFC", "שׁוּר ,אָח\nוְעֵינֵיהֶם .תּוֹלִים\n\nמוּסָר :לָמוֹ")
    fixed, count = fix_space_before_punctuation(text)
    assert count == 3 and fixed == "שׁוּר, אָח\nוְעֵינֵיהֶם. תּוֹלִים\n\nמוּסָר: לָמוֹ"
    assert fixed.count("\n") == text.count("\n")
    assert unicodedata.is_normalized("NFC", fixed)
    decomposed = unicodedata.normalize("NFD", text)
    assert unicodedata.normalize("NFC", fix_space_before_punctuation(decomposed)[0]) == fixed


def test_the_rule_is_idempotent() -> None:
    text = "ודונג ,אם בעיר .ובשנת סוף :ועוד ... ו . . . ז 1 ,000"
    once, count = fix_space_before_punctuation(text)
    assert count == 3 and fix_space_before_punctuation(once) == (once, 0)


def test_fixes_are_reported_as_spans_of_the_input() -> None:
    text = "ודונג ,אם ושם ."
    assert space_before_punctuation_fixes(text) == [(5, 7, ", "), (13, 15, ".")]


def test_protected_spans_are_left_alone_and_carried_through() -> None:
    text = "אחד ,שנים ,שלשה ,ארבעה"
    second = text.index(" ,שלשה")
    result = apply_reference_rules(text, protected=[(second, second + 2), (text.index("ארבעה"), len(text))])
    assert result["text"] == "אחד, שנים ,שלשה, ארבעה"
    assert result["applied"] == [{"rule": R, "fixes": 2, "skipped_protected": 1}]
    (kept, word) = result["protected"]
    assert result["text"][kept[0]:kept[1]] == " ," and result["text"][word[0]:word[1]] == "ארבעה"
    assert apply_reference_rules("אחד ,שנים")["applied"] == [{"rule": R, "fixes": 1}]
    assert apply_reference_rules("אחד ,שנים", ())["text"] == "אחד ,שנים"  # no rules: unchanged
    assert shift_offset(10, [(2, 4, ", "), (8, 10, ".")]) == 9
    with pytest.raises(ValueError, match="unknown reference rule"):
        apply_reference_rules("x", ("nope.v1",))


def test_rule_covers_only_a_proposal_the_rule_makes_exactly() -> None:
    text = "ודונג ,אם ושם .ועוד"
    assert rule_covers(R, text, 5, 7, ", ")                   # ' ,' -> ', '
    assert rule_covers(R, text, 5, 8, ", א")                  # a wider span, the same change
    assert not rule_covers(R, text, 5, 7, ",")                # the rule also adds the space after
    assert not rule_covers(R, text, 13, 15, ", ")             # a different mark
    assert not rule_covers(R, text, 0, 5, "ודונג")            # nothing the rule does there
    assert not rule_covers(R, "a ...", 1, 2, "")              # excluded by the rule
