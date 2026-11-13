"""Private-person name gate for Knesset committee protocol lines (``committee_private_names_v1``).

The plenary gate (:mod:`hocrgen.privacy.plenary_names`, decision 2026-11-13) with three
changes, because committee protocols name invited private witnesses:

1. **No structural heading proof.** The protocols mark guests (``<< אורח >>``) and
   officials (``<< דובר >>``) as speakers in the same way as members, so a marker is no
   proof that the speaker is public. Only the roster shape proofs count, and an unproven
   heading is judged as an ordinary line, so a guest's heading drops.
2. **A per-session denylist.** Surnames from the session's attendance lists (invitees,
   registered attendees) and from unproven speaker headings are private for that
   session: a mention containing one drops, even when an MK of that term shares it.
3. **The attendance block is dropped whole** (names and affiliations), officials too.

Rows are stamped ``privacy_gate: committee_private_names_v1``, and committee intake and
the release export refuse any committee row without that stamp. Committee protocols from
1976 on are also training-only (:mod:`hocrgen.privacy.training_only`).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from hocrgen.privacy.plenary_names import (
    Allowlist,
    GateResult,
    Roster,
    _norm,
    _title_before,
    _tokens,
    gate_stream_lines,
    proven_speaker_heading,
)
from hocrgen.privacy.training_only import _get, is_committee_row

GATE_ID = "committee_private_names_v1"
DECISION_PATH = "planning/decisions/2026-11-13-plenary-private-names.md"

# Headings that open the attendance block, and those that close it (the agenda or the first speaker).
ATTENDANCE_OPEN = re.compile(r"^\s*(נכחו|חברי הוועדה|חברי הכנסת|מוזמנים|מוזמנות|רישום פרלמנטרי|ייעוץ משפטי|"
                             r"מנהל[ת]? הוועדה|מנהלת הוועדה|רשמ[הת] פרלמנטרי[ת]?|קצרנית|נרשם על ידי)\b")
ATTENDANCE_CLOSE = re.compile(r"^\s*(סדר היום|סדר-היום|<<\s*נושא\s*>>|<<\s*יור\s*>>|<<\s*דובר\s*>>|<<\s*אורח\s*>>)")


def attendance_block(paragraphs: Sequence[str]) -> tuple[int, int] | None:
    """The paragraph range [start, end) of the attendance block, or ``None`` if there is none.

    The block ends at the agenda, a speaker marker, or the first speaker heading by shape
    (``היו"ר ...:``), since unmarked protocols (K16–20) carry no marker. It never runs to the
    end of the protocol.
    """

    start = next((i for i, p in enumerate(paragraphs) if ATTENDANCE_OPEN.match(p)), None)
    if start is None:
        return None
    end = next((i for i in range(start + 1, len(paragraphs))
                if ATTENDANCE_CLOSE.match(paragraphs[i]) or _CHAIR_HEADING.match(paragraphs[i])), len(paragraphs))
    return start, end


_CHAIR_HEADING = re.compile(r'^\s*(?:<<[^>]*>>\s*)?(?:היו"ר|היו״ר|היושב[- ]ראש)\s[^:]{1,60}:')
_LIST_HEAD = re.compile(r"^\s*<?([^:<>\t]{2,40}):\s*>?\s*")


def _name_part(entry: str) -> str:
    """The person part of an attendance entry ("ישראל ישראלי – משרד הבריאות" → "ישראל ישראלי").

    A list heading sharing the entry's line ("מוזמנים:<tab>ישראל ישראלי – ...") is cut off first.
    """

    head = _LIST_HEAD.match(entry)
    if head and ATTENDANCE_OPEN.match(head.group(1)):
        entry = entry[head.end():]
    return re.split(r"\s[–—-]\s|,|\s{2,}|\t", entry, maxsplit=1)[0].strip()


_PARTICLES = frozenset({"בן", "בר", "אבו", "אבן", "בת", "אל", "דה", "ון", "פון"})


def session_denylist(names: Iterable[str], roster: Roster, knesset: int | None) -> frozenset[str]:
    """Surname tokens of the session's private persons.

    ``names`` are attendance entries and unproven-heading names. A name that is wholly an
    MK of that term ("<full name>" in the roster) is left out; titles are stripped, and
    the last remaining token is taken as the surname. Particles of compound surnames
    (בן, אבו …) are never denylisted alone, since they would match every MK named with them.
    """

    full = roster.full_names
    out: set[str] = set()
    for raw in names:
        toks = _tokens(_name_part(raw))
        for i in range(len(toks) - 1, 0, -1):
            if _title_before(toks[:i]):
                toks = toks[i:]
                break
        toks = [t for t in toks if len(t) > 1 and not t.endswith(("'", "׳"))]
        if not toks or tuple(_norm(t) for t in toks) in full or tuple(toks) in full:
            continue
        if toks[-1] in _PARTICLES:
            continue
        out.add(_norm(toks[-1]))
    return frozenset(out)


def unproven_heading_names(lines: Sequence[Mapping[str, Any]], roster: Roster) -> list[str]:
    """The name part of every heading-shaped line that the roster does not prove."""

    out = []
    for line in lines:
        text = str(line.get("text", ""))
        if ":" not in text or len(text.split(":")[0]) > 60:
            continue
        flagless = {k: v for k, v in line.items() if k != "is_speaker_heading"}
        if line.get("is_speaker_heading") and proven_speaker_heading(flagless, roster) is None:
            out.append(re.sub(r"\([^)]*\)", " ", text.split(":")[0]))
    return out


def gate_committee_lines(
    lines: Sequence[Mapping[str, Any]],
    stream_spans: Iterable[Mapping[str, Any]] | None,
    roster: Roster,
    allowlist: Allowlist = Allowlist(),
    *,
    denylist: Iterable[str] = (),
    use_heuristic: bool = True,
) -> GateResult:
    """Gate one session's physical lines. Lines with ``in_attendance_block: True`` drop whole."""

    lines = list(lines)
    block = [dict(line) for line in lines if line.get("in_attendance_block")]
    body = [line for line in lines if not line.get("in_attendance_block")]
    result = gate_stream_lines(
        body, stream_spans, roster, allowlist, denylist=denylist, structural_headings=False,
        use_heuristic=use_heuristic, gate_id=GATE_ID,
    ) if body else GateResult()
    for line in block:
        result.dropped.append({**line, "privacy_drop": ["attendance_block"]})
        result.reasons["attendance_block"] += 1
    return result


def summary(result: GateResult, roster: Roster, tagger: str) -> dict[str, Any]:
    out = result.summary(roster, tagger)
    out.update({"gate": GATE_ID, "base_gate": "plenary_private_names_v1", "decision": DECISION_PATH})
    return out


class UngatedCommitteeLinesError(ValueError):
    """Raised when committee lines reach intake without passing this gate."""


def refuse_ungated_committee_lines(rows: Iterable[Any], *, builder: str = "committee intake") -> int:
    """Every committee row (see :func:`is_committee_row`) must carry ``privacy_gate == GATE_ID``."""

    checked, refused = 0, []
    for row in rows:
        if not is_committee_row(row):
            continue
        checked += 1
        if _get(row, "privacy_gate") != GATE_ID:
            refused.append(str(_get(row, "line_id") or _get(row, "item_id") or _get(row, "unit_id") or "?"))
    if refused:
        shown = ", ".join(refused[:10]) + (f" and {len(refused) - 10} more" if len(refused) > 10 else "")
        raise UngatedCommitteeLinesError(
            f"{builder}: {len(refused)} committee row(s) did not pass {GATE_ID}: {shown}"
        )
    return checked
