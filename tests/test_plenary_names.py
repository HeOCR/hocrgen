import pytest

from hocrgen.privacy.plenary_names import (
    GATE_ID,
    Allowlist,
    Roster,
    UngatedPlenaryLinesError,
    classify_person,
    gate_lines,
    heuristic_person_spans,
    refuse_ungated_plenary_lines,
)

ROSTER = Roster.from_people(
    [
        {"first": "יואב", "last": "בן צור"},
        {"first": "אחמד", "last": "טיבי"},
        {"first": "יאיר", "last": "לפיד"},
        {"first": "משה", "last": "כהן"},
    ]
)


def _line(text, *names):
    spans = []
    for name in names:
        start = text.index(name)
        spans.append({"start": start, "end": start + len(name), "text": name})
    return {"line_id": "l1", "unit_id": "plenary:K25_267", "text": text, "person_spans": spans}


@pytest.mark.parametrize(
    "mention,left,expected",
    [
        ("יואב בן צור", "", ("public", "roster_full_name")),
        ("בן צור", "", ("public", "roster_surname")),
        ("לטיבי", "", ("public", "roster_surname")),  # proclitic stripped
        ("ולפיד", "", ("public", "roster_surname")),
        ("השר יואב בן צור", "", ("public", "title")),
        ("דוד לוי", "מבקר המדינה", ("public", "title")),
        ("רונית אברהמי", "קיבלתי מכתב מ", ("private", "not_public")),
        ("שרה כהן", "", ("private", "surname_namesake")),  # an MK's surname, a different first name
        ("משה כהן", "", ("public", "roster_full_name")),
    ],
)
def test_classify_person(mention, left, expected):
    assert classify_person(mention, left, ROSTER) == expected


def test_allowlist_makes_public():
    allow = Allowlist.from_names(["הארי טרומן"])
    assert classify_person("הארי טרומן", "", ROSTER, allow) == ("public", "allowlist")
    assert classify_person("הארי טרומן", "", ROSTER)[0] == "private"


def test_heuristic_finds_cued_names():
    spans = heuristic_person_spans("פנה אליי האזרח יוסי מזרחי, תושב באר שבע")
    assert [s["text"] for s in spans] == ["יוסי מזרחי"]
    assert heuristic_person_spans("אני מבקש לומר לחברי הכנסת") == []


def test_gate_drops_whole_line_with_private_name():
    lines = [
        _line("שר העבודה יואב בן צור: אדוני היושב-ראש", "יואב בן צור"),
        _line("קיבלתי מכתב מרונית אברהמי מחיפה", "רונית אברהמי"),
        _line("אין כאן שמות כלל"),
        {"line_id": "l4", "unit_id": "plenary:K25_267", "text": "לא תויג", "person_spans": None},
    ]
    res = gate_lines(lines, ROSTER)
    assert [line["text"] for line in res.kept] == ["שר העבודה יואב בן צור: אדוני היושב-ראש", "אין כאן שמות כלל"]
    assert all(line["privacy_gate"] == GATE_ID for line in res.kept)
    assert len(res.dropped) == 2
    assert res.dropped[0]["text"] == "קיבלתי מכתב מרונית אברהמי מחיפה"  # dropped, not masked
    assert res.reasons == {"not_public": 1, "untagged": 1}
    summary = res.summary(ROSTER, "test")
    assert (summary["lines_in"], summary["lines_kept"], summary["lines_dropped"]) == (4, 2, 2)


def test_gate_uses_heuristic_when_tagger_missed():
    res = gate_lines([_line("פנה אליי האזרח יוסי מזרחי מבאר שבע")], ROSTER)
    assert len(res.dropped) == 1


def test_refuse_ungated_plenary_lines():
    ok = [
        {"unit_id": "plenary:K1_1", "privacy_gate": GATE_ID},
        {"source_id": "knesset_plenary_k13_rendered", "metadata": {"privacy_gate": GATE_ID}},
        {"unit_id": "reshumot:x"},
    ]
    assert refuse_ungated_plenary_lines(ok) == 2
    with pytest.raises(UngatedPlenaryLinesError, match="refused 1"):
        refuse_ungated_plenary_lines([{"unit_id": "plenary:K1_1", "line_id": "a"}])
    with pytest.raises(UngatedPlenaryLinesError):
        refuse_ungated_plenary_lines([{"item_id": "x", "source_id": "knesset_plenary_k1_12"}])


def test_cut_spans_widen_to_whole_words():
    from hocrgen.privacy.plenary_names import expand_to_words

    text = "אחמד טיבי (חד\"ש-תע\"ל): תודה"
    assert expand_to_words(text, 0, 8) == (0, 9)
    res = gate_lines([{"text": text, "person_spans": [{"start": 0, "end": 8, "text": text[0:8]}]}], ROSTER)
    assert len(res.kept) == 1


def test_partial_and_compound_roster_names():
    roster = Roster.from_people(
        [{"first": "גלית", "last": "דיסטל אטבריאן"}, {"first": "אבנר-חי", "last": "שאקי"}]
    )
    assert classify_person("גלית דיסטל", "", roster) == ("public", "roster_partial_name")
    assert classify_person("אטבריאן", "", roster) == ("public", "roster_surname_part")
    assert classify_person("גלית", "", roster)[0] == "private"
    assert classify_person("אבנר חי שאקי", "", roster) == ("public", "roster_full_name")
    assert classify_person("רונית דיסטל", "", roster)[0] == "private"


def test_speaker_heading_shape_needs_proof():
    from hocrgen.privacy.plenary_names import is_speaker_heading

    assert is_speaker_heading("דני נווה (הליכוד):")
    assert is_speaker_heading("שר העבודה יואב בן צור:")
    assert not is_speaker_heading("קיבלתי מכתב מרונית אברהמי: היא כותבת")
    # The shape alone proves nothing: an unlisted name in a heading is judged as usual.
    res = gate_lines([_line("דני נווה (הליכוד):", "דני נווה")], ROSTER)
    assert len(res.dropped) == 1
    res = gate_lines([{**_line("דני נווה (הליכוד):", "דני נווה"), "is_speaker_heading": True}], ROSTER)
    assert len(res.kept) == 1


def test_split_name_spans_are_merged():
    # Fictional names: each half alone matches someone on the roster.
    roster = Roster.from_people([{"first": "אורנה", "last": "לוי"}, {"first": "דגן", "last": "פאר"}])
    text = "הפעם אני רוצה להקריא מכתב שקיבלתי מאורנה דגן, אימא של"
    i = text.index("מאורנ")
    j = text.index("דגן")
    spans = [{"start": i, "end": i + 4, "text": "מאור"}, {"start": j, "end": j + 3, "text": "דגן"}]
    res = gate_lines([{"text": text, "person_spans": spans}], roster)
    assert len(res.dropped) == 1


def test_lone_given_names_are_private_even_if_a_speaker_shares_them():
    lines = [
        {"unit_id": "plenary:K25_1", "text": "יאיר לפיד (יש עתיד):", "person_spans": []},
        _line("תודה, יאיר.", "יאיר"),
        _line("כך אמר עוזי לבנו בטקס.", "עוזי"),
    ]
    lines[1]["unit_id"] = lines[2]["unit_id"] = "plenary:K25_1"
    res = gate_lines(lines, ROSTER)
    assert [line["text"] for line in res.kept] == ["יאיר לפיד (יש עתיד):"]
    assert len(res.dropped) == 2


def test_packaged_roster_loads():
    from hocrgen.privacy.plenary_names import packaged_roster

    roster = packaged_roster()
    assert len(roster.surnames) > 900
    assert classify_person("אחמד טיבי", "", roster) == ("public", "roster_full_name")


# The lead's review probes (hocrgen#196): invented private names, ordinary sentences. Each
# line must be dropped.
LEAD_PROBES = [
    ("קבענו מראש עם רחל אברבנאל שתגיע", "רחל אברבנאל"),  # "מראש" is not "ראש"
    ("קנינו בשר אצל עמיחי גלבוע", "עמיחי גלבוע"),  # "בשר" is not "שר"
    ("השר אמר לי שרחל אברבנאל פנתה אליו", "שרחל אברבנאל"),  # a title not right before the name
    ("החבר שלי עמיחי גלבוע כתב לי", "עמיחי גלבוע"),  # "חבר" as a friend
    ('סגן עמיחי גלבוע ז"ל נפל בקרב', "עמיחי גלבוע"),  # a junior officer's rank
]


@pytest.mark.parametrize("text,name", LEAD_PROBES)
def test_lead_probes_are_dropped(text, name):
    from hocrgen.privacy.plenary_names import packaged_roster

    res = gate_lines([_line(text, name)], packaged_roster())
    assert len(res.dropped) == 1, res.kept


def test_letter_intro_is_not_a_speaker_heading_and_seeds_no_speakers():
    from hocrgen.privacy.plenary_names import packaged_roster, proven_speaker_heading

    roster = packaged_roster()
    intro = _line("וכך כתבה לי רחל אברבנאל מבאר שבע:", "רחל אברבנאל")
    follow = _line("רחל ביקשה שאקריא את דבריה", "רחל")
    assert proven_speaker_heading(intro, roster) is None
    res = gate_lines([intro, follow], roster)
    assert len(res.dropped) == 2 and not res.kept


def test_proven_speaker_headings():
    from hocrgen.privacy.plenary_names import packaged_roster, proven_speaker_heading

    roster = packaged_roster()
    assert proven_speaker_heading({"text": "אחמד טיבי (חד\"ש-תע\"ל):"}, roster) == ("אחמד", "טיבי")
    assert proven_speaker_heading({"text": "שר העבודה יואב בן צור:"}, roster) == ("יואב", "בן", "צור")
    # Source structure is proof on its own.
    assert proven_speaker_heading({"text": "מזכיר הכנסת דן מרזוק:", "is_speaker_heading": True}, roster)


def test_titles_must_be_exact_and_adjacent():
    assert classify_person("רחל אברבנאל", "ראש הממשלה", ROSTER) == ("public", "title")
    assert classify_person("רחל אברבנאל", "שר האוצר", ROSTER) == ("public", "title")
    assert classify_person("רחל אברבנאל", "והשר", ROSTER) == ("public", "title")
    assert classify_person("רחל אברבנאל", "חבר הכנסת", ROSTER) == ("public", "title")
    for left in ("מראש", "בשר", "כשר", "משרת", "החבר שלי", "סגן", "ראש", "השר אמר לי", "השר הוא"):
        assert classify_person("רחל אברבנאל", left, ROSTER)[0] == "private", left


def test_bare_surname_is_matched_per_knesset_term():
    roster = Roster.from_people([{"first": "משה", "last": "גלבוע", "knessets": [3]}])
    assert classify_person("גלבוע", "", roster, knesset=3) == ("public", "roster_surname")
    assert classify_person("גלבוע", "", roster, knesset=20)[0] == "private"
    assert classify_person("משה גלבוע", "", roster, knesset=20) == ("public", "roster_full_name")


def test_heading_proof_by_faction_title_and_initials():
    from hocrgen.privacy.plenary_names import proven_speaker_heading

    roster = Roster.from_people(
        [{"first": "דני", "last": "נוה", "knessets": [15]}, {"first": "יצחק", "last": "רבין", "knessets": [13]}],
        factions={15: ["הליכוד"], 13: ["מפלגת העבודה הישראלית"]},
    )
    # A full roster name proves the heading in any term (plene spelling is normalised).
    assert proven_speaker_heading({"text": "דני נווה (הליכוד):", "knesset": 20}, roster)
    # A variant first name needs the faction of that term plus a surname of that term.
    assert proven_speaker_heading({"text": "דניאל נווה (הליכוד):", "knesset": 15}, roster)
    assert proven_speaker_heading({"text": "דניאל נווה (הליכוד):", "knesset": 20}, roster) is None
    # A title, an initial, and a surname of that term.
    assert proven_speaker_heading({"text": "ראש הממשלה ושר הביטחון י' רבין:", "knesset": 13}, roster)
    # A parenthetical that is no faction: no proof.
    assert proven_speaker_heading({"text": "וכך כתבה לי רחל נוה (מבאר שבע):", "knesset": 15}, roster) is None
