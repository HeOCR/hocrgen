import pytest

from hocrgen.privacy.committee_names import (
    GATE_ID,
    UngatedCommitteeLinesError,
    attendance_block,
    gate_committee_lines,
    refuse_ungated_committee_lines,
    session_denylist,
    unproven_heading_names,
)
from hocrgen.privacy.plenary_names import Roster, stream_text

ROSTER = Roster.from_people(
    [{"first": "יואב", "last": "בן צור", "knessets": [24]}, {"first": "משה", "last": "כהן", "knessets": [24]}]
)


def _lines(*texts, **extra):
    return [{"line_id": f"l{i}", "unit_id": "committee:K24_1", "knesset": 24, "text": t, **extra}
            for i, t in enumerate(texts)]


def test_attendance_block_runs_to_agenda():
    paras = ["פרוטוקול מס' 5", "חברי הוועדה:", "יואב בן צור – היו\"ר", "מוזמנים:", "אורי כהן – עמותה",
             "סדר היום", "הצעת חוק"]
    assert attendance_block(paras) == (1, 5)
    assert attendance_block(["אין רשימה"]) is None


def test_denylist_skips_mks_and_titles():
    deny = session_denylist(["אורי כהן – עמותת דוגמה", "עו\"ד דנה לוינשטיין, לשכת עורכי הדין",
                             "יואב בן צור", "ד\"ר רמי בן חיים"], ROSTER, 24)
    assert {"כהן", "לוינשטין"} <= deny  # normalised (doubled yod collapsed)
    assert "צור" not in deny  # the MK himself
    assert "חים" in deny and "בן" not in deny


def test_guest_heading_with_marker_is_not_proof():
    head = _lines("אורי מזרחי:", is_speaker_heading=True)
    stream, _ = stream_text(head)
    spans = [{"start": 0, "end": 9, "text": stream[:9]}]
    res = gate_committee_lines(head, spans, ROSTER)
    assert not res.kept
    assert unproven_heading_names(head, ROSTER) == ["אורי מזרחי"]


def test_chair_heading_is_kept_and_guest_surname_overrides_mk():
    lines = _lines("היו\"ר יואב בן צור:", "תודה למר כהן על הנתונים", "נעבור לסעיף הבא")
    stream, offs = stream_text(lines)
    s = stream.index("כהן")
    spans = [{"start": s, "end": s + 3, "text": "כהן"}]
    res = gate_committee_lines(lines, spans, ROSTER, denylist=["אורי כהן"], use_heuristic=False)
    assert [r["line_id"] for r in res.kept] == ["l0", "l2"]
    assert res.dropped[0]["privacy_drop"] == ["session_denylist"]
    assert all(r["privacy_gate"] == GATE_ID for r in res.kept)


def test_attendance_lines_drop_whole():
    lines = _lines("מוזמנים:", "אורי כהן – עמותה", in_attendance_block=True) + _lines("טקסט")
    res = gate_committee_lines(lines, [], ROSTER)
    assert res.reasons["attendance_block"] == 2


def test_refuse_ungated_committee_lines():
    ok = {"line_id": "a", "unit_id": "committee:K24_1", "privacy_gate": GATE_ID}
    plenary_stamp = {"line_id": "b", "unit_id": "committee:K24_1", "privacy_gate": "plenary_private_names_v1"}
    assert refuse_ungated_committee_lines([ok, {"line_id": "x"}]) == 1
    with pytest.raises(UngatedCommitteeLinesError):
        refuse_ungated_committee_lines([plenary_stamp])


def test_lead_probe_witness_sharing_mk_surname_same_term():
    # The invited witness "אורי כהן" shares the surname of MK משה כהן (K24). "מר כהן" in the body
    # must drop, though the plenary rule alone would keep a bare K24 MK surname.
    deny = session_denylist(["אורי כהן – עמותת דוגמה"], ROSTER, 24)
    lines = _lines("אני מבקש להודות למר כהן על עבודתו", "נעבור לסעיף הבא")
    stream, _ = stream_text(lines)
    s = stream.index("כהן")
    spans = [{"start": s, "end": s + 3, "text": "כהן"}]
    assert gate_committee_lines(lines, spans, ROSTER).kept[0]["line_id"] == "l0"  # without the denylist it leaks
    res = gate_committee_lines(lines, spans, ROSTER, denylist=deny)
    assert [r["line_id"] for r in res.dropped] == ["l0"]
    assert res.dropped[0]["privacy_drop"] == ["session_denylist"]


def test_lead_probe_name_broken_across_two_physical_lines():
    # "רונית" ends the first physical line, "כהן" (a K24 MK surname) starts the second.
    lines = _lines("הגיעה אלינו פנייה של רונית", "כהן מחיפה בעניין הדיור", "אין כאן שמות")
    stream, _ = stream_text(lines)
    s = stream.index("רונית")
    spans = [{"start": s, "end": s + len("רונית כהן"), "text": "רונית כהן"}]
    res = gate_committee_lines(lines, spans, ROSTER)
    assert [r["line_id"] for r in res.dropped] == ["l0", "l1"]
    assert [r["line_id"] for r in res.kept] == ["l2"]


def test_attendance_block_ends_at_unmarked_chair_heading():
    paras = ["מוזמנים:", "אורי כהן – עמותה", 'היו"ר יואב בן צור:', "בוקר טוב"]
    assert attendance_block(paras) == (0, 2)


def test_denylist_entry_sharing_the_list_heading_line():
    deny = session_denylist(["מוזמנים:\tאורי מזרחי – עמותה"], ROSTER, 24)
    assert deny == frozenset({"מזרחי"})
