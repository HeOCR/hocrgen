from hocrgen.privacy.plenary_names import Roster, gate_stream_lines, stream_text

ROSTER = Roster.from_people(
    [
        {"first": "יואב", "last": "בן צור", "knessets": [25]},
        {"first": "משה", "last": "כהן", "knessets": [25]},
    ]
)


def _lines(*texts):
    return [{"line_id": f"l{i}", "unit_id": "plenary:K25_1", "knesset": 25, "text": t} for i, t in enumerate(texts)]


def _spans(lines, *names):
    stream, _ = stream_text(lines)
    out = []
    for name in names:
        start = stream.index(name)
        out.append({"start": start, "end": start + len(name), "text": name})
    return out


def test_name_split_across_line_end_drops_both_lines():
    # "רונית" ends line 0, "כהן" (an MK surname in K25) starts line 1.
    lines = _lines("קיבלתי פנייה מאת רונית", "כהן מחיפה בעניין הדיור", "אין כאן שמות")
    res = gate_stream_lines(lines, _spans(lines, "רונית כהן"), ROSTER)
    assert [r["line_id"] for r in res.dropped] == ["l0", "l1"]
    assert [r["line_id"] for r in res.kept] == ["l2"]


def test_cue_at_previous_line_end_is_seen():
    # "מר" ends line 0; the tagger missed the name, and the cue heuristic sees across the break.
    lines = _lines("ואז פנה אליי מר", "יוסי מזרחי ושאל")
    res = gate_stream_lines(lines, [], ROSTER)
    assert [r["line_id"] for r in res.dropped] == ["l1"]
    assert gate_stream_lines(lines[1:], [], ROSTER).kept  # alone, the second line has no cue


def test_title_on_previous_line_makes_public():
    lines = _lines("דברי חבר הכנסת יואב", "בן צור נשמעו היטב")
    res = gate_stream_lines(lines, _spans(lines, "יואב בן צור"), ROSTER)
    assert not res.dropped


def test_session_denylist_overrides_mk_surname():
    lines = _lines("תודה למר כהן על הנתונים", "אדוני היושב ראש")
    spans = _spans(lines, "כהן")
    assert gate_stream_lines(lines, spans, ROSTER, use_heuristic=False).kept[0]["line_id"] == "l0"
    res = gate_stream_lines(lines, spans, ROSTER, denylist=["אורי כהן"], use_heuristic=False)
    assert res.dropped[0]["privacy_drop"] == ["session_denylist"]


def test_structural_headings_can_be_disabled():
    head = {**_lines("אורי מזרחי:")[0], "is_speaker_heading": True}
    spans = _spans([head], "אורי מזרחי")
    assert gate_stream_lines([head], spans, ROSTER).kept
    res = gate_stream_lines([head], spans, ROSTER, structural_headings=False)
    assert res.dropped and not res.kept


def test_untagged_stream_drops_everything():
    res = gate_stream_lines(_lines("א", "ב"), None, ROSTER)
    assert res.reasons["untagged"] == 2 and not res.kept


def test_kept_rows_carry_gate_id():
    res = gate_stream_lines(_lines("אין שמות"), [], ROSTER, gate_id="committee_private_names_v1")
    assert res.kept[0]["privacy_gate"] == "committee_private_names_v1"
