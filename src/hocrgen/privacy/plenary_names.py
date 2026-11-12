"""Private-person name gate for Knesset plenary record lines (Divrei ha-Knesset).

Decision: ``planning/decisions/2026-11-13-plenary-private-names.md``.

A plenary line is dropped, whole, when it names a private person: someone who is not
a member of the Knesset, a minister, an official or another public figure acting in
their role. Names are never masked; the line goes.

How a line is judged:

1. **Person mentions.** Each line carries the person-name spans found in it
   (``person_spans``), produced upstream by a named-entity tagger run over the
   paragraph the line came from (see ``tasks/modern-s6-scout/scripts/plenary_ner.py``
   in the agents workspace). :func:`heuristic_person_spans` adds a pure-Python
   fallback: a name that follows a private-person cue such as "מר", "הגברת",
   "האזרח" or "התושבת".
2. **Public or private.** :func:`classify_person` calls a mention public when
   - it matches a person in the Knesset roster (``KNS_Person`` with at least one
     ``KNS_PersonToPosition`` row: MKs, ministers, deputy ministers), by full name
     or by a surname that ends the mention;
   - it is preceded by a public-role word ("השר", "נשיא", "מבקר המדינה", ...); or
   - it is on the curated public-figure allowlist.
   Anything else is private.
3. **Drop.** A line with any private mention, or with a mention that could not be
   judged, is dropped. Lines that have not been tagged at all are refused by
   :func:`refuse_ungated_plenary_lines`.

The gate prefers dropping: a public figure missing from the roster costs a line,
never a leak. The known leak is a private person referred to by a bare surname that
some MK shares; private persons in the record are normally named in full, and the
full-name check catches those.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

GATE_ID = "plenary_private_names_v1"
DECISION_PATH = "planning/decisions/2026-11-13-plenary-private-names.md"

# Hebrew one-letter proclitics (ו, ה, ב, ל, מ, ש, כ), up to two of them in a row.
_PREFIXES = "והבלמשכ"
_HEB_WORD = re.compile(r"[א-ת׳״'\"״׳-]+")
_NIQQUD = re.compile(r"[֑-ׇ]")
_EDGE_PUNCT = "'\"״׳-–—.,:;!?()[]{}"

# Words that, right before a name, mark someone acting in a public role.
PUBLIC_ROLE_WORDS: frozenset[str] = frozenset(
    {
        "השר", "השרה", "שר", "שרת", "סגן", "סגנית", "ראש", "יושב", "יושבת", "היו\"ר", "היו״ר",
        "יו\"ר", "יו״ר", "חבר", "חברת", "חה\"כ", "חה״כ", "ח\"כ", "ח״כ", "נשיא", "נשיאת",
        "הנשיא", "הנשיאה", "מבקר", "מבקרת", "היועץ", "היועצת", "המשפטי", "המשפטית", "נציב",
        "נציבת", "השופט", "השופטת", "שופט", "שופטת", "אלוף", "האלוף", "תת-אלוף", "רב-אלוף",
        "הרמטכ\"ל", "הרמטכ״ל", "רמטכ\"ל", "רמטכ״ל", "המפכ\"ל", "המפכ״ל", "מפכ\"ל", "מפכ״ל",
        "השגריר", "השגרירה", "שגריר", "שגרירת", "מזכיר", "מזכירת", "המזכיר", "המזכירה",
        "ראש-הממשלה", "ראש-העיר", "המנכ\"ל",
        "המנכ״ל", "מנכ\"ל", "מנכ״ל", "מנהל", "מנהלת", "הרב-הראשי", "המשפטי", "המשפטית", "לממשלה",
        "הקונגרס", "המלך", "המלכה", "הקיסר", "הנשיאים", "הגנרל", "גנרל", "מרשל", "קנצלר",
    }
)

# Cues that the next words name a private person (used by the heuristic tagger).
PRIVATE_CUES: frozenset[str] = frozenset(
    {
        "מר", "גב'", "גב׳", "גברת", "הגברת", "האזרח", "האזרחית", "התושב", "התושבת",
        "ששמו", "ששמה", "משפחת",
    }
)


def _strip_niqqud(text: str) -> str:
    return _NIQQUD.sub("", text)


def _tokens(text: str) -> list[str]:
    # Hyphen and maqaf split compound names ("אבנר-חי", "פולישוק-בלוך") into tokens, so a
    # roster entry and a mention match whichever way the compound was written.
    text = re.sub(r"[-\u05be]", " ", _strip_niqqud(text))
    return [t.strip(_EDGE_PUNCT) for t in _HEB_WORD.findall(text) if t.strip(_EDGE_PUNCT)]


def _variants(token: str) -> set[str]:
    """The token and its forms with up to two proclitic letters removed."""

    out = {token}
    if len(token) > 2 and token[0] in _PREFIXES:
        out.add(token[1:])
        if len(token) > 3 and token[1] in _PREFIXES:
            out.add(token[2:])
    return out


@dataclass(frozen=True)
class Roster:
    """Public persons by normalised name: full names and surnames as token tuples."""

    full_names: frozenset[tuple[str, ...]]
    surnames: frozenset[tuple[str, ...]]
    source: str = ""
    sha256: str = ""
    surname_tokens: frozenset[str] = frozenset()

    @classmethod
    def from_people(cls, people: Iterable[Mapping[str, str]], *, source: str = "", sha256: str = "") -> "Roster":
        full: set[tuple[str, ...]] = set()
        last: set[tuple[str, ...]] = set()
        toks: set[str] = set()
        for person in people:
            first_toks = tuple(_tokens(person.get("first", "") or ""))
            last_toks = tuple(_tokens(person.get("last", "") or ""))
            if not last_toks:
                continue
            last.add(last_toks)
            toks.update(last_toks)
            if first_toks:
                full.add(first_toks + last_toks)
                # Common usage drops middle names: "first-of-first + last".
                full.add(first_toks[:1] + last_toks)
        return cls(frozenset(full), frozenset(last), source, sha256, frozenset(toks))

    @classmethod
    def load(cls, path: Path | str) -> "Roster":
        import hashlib

        path = Path(path)
        raw = path.read_bytes()
        data = json.loads(raw)
        return cls.from_people(data["people"], source=str(path), sha256=hashlib.sha256(raw).hexdigest())


PACKAGED_ROSTER = Path(__file__).resolve().parent.parent / "data" / "knesset_plenary" / "public_roster_v1.json"


def packaged_roster() -> Roster:
    """The committed roster (``hocrgen/data/knesset_plenary/public_roster_v1.json``)."""

    return Roster.load(PACKAGED_ROSTER)


@dataclass(frozen=True)
class Allowlist:
    """Curated public figures outside the roster, as token tuples."""

    names: frozenset[tuple[str, ...]] = frozenset()

    @classmethod
    def from_names(cls, names: Iterable[str]) -> "Allowlist":
        return cls(frozenset(tuple(_tokens(n)) for n in names if _tokens(n)))


def _ends_with(seq: Sequence[set[str]], target: tuple[str, ...]) -> bool:
    if not target or len(target) > len(seq):
        return False
    tail = seq[len(seq) - len(target):]
    return all(t in options for t, options in zip(target, tail))


def _contains(seq: Sequence[set[str]], target: tuple[str, ...]) -> bool:
    """``seq`` (two or more tokens) appears contiguously inside ``target``."""

    n = len(seq)
    if n < 2 or n > len(target):
        return False
    return any(all(target[i + j] in seq[j] for j in range(n)) for i in range(len(target) - n + 1))


def _equals(seq: Sequence[set[str]], target: tuple[str, ...]) -> bool:
    return len(seq) == len(target) and _ends_with(seq, target)


def classify_person(
    mention: str,
    left_context: str,
    roster: Roster,
    allowlist: Allowlist = Allowlist(),
    speaker_tokens: frozenset[str] = frozenset(),
) -> tuple[str, str]:
    """Return ``("public" | "private", reason)`` for one person-name mention.

    ``speaker_tokens`` are the name words of the people who spoke in the same sitting
    (from its speaker headings); a lone word matching one of them is public.
    """

    toks = _tokens(mention)
    if not toks:
        return "private", "empty_mention"
    # Role words inside the mention itself ("השר יואב בן צור") count as left context.
    lead: list[str] = []
    while toks and (toks[0] in PUBLIC_ROLE_WORDS or (_variants(toks[0]) & PUBLIC_ROLE_WORDS)):
        lead.append(toks.pop(0))
    if lead:
        return "public", "role_word"
    if not toks:
        return "public", "role_word"
    left = _tokens(left_context)
    if left and (set().union(*(_variants(t) for t in left[-3:])) & PUBLIC_ROLE_WORDS):
        return "public", "role_word"
    seq = [_variants(t) for t in toks]
    if any(_equals(seq, name) for name in allowlist.names):
        return "public", "allowlist"
    if any(_ends_with(seq, name) for name in roster.full_names):
        return "public", "roster_full_name"
    if any(_equals(seq, s) for s in roster.surnames):
        return "public", "roster_surname"
    if any(_contains(seq, name) for name in roster.full_names):
        # Part of an MK's full name: "גלית דיסטל" for "גלית דיסטל אטבריאן".
        return "public", "roster_partial_name"
    if len(seq) == 1 and seq[0] & roster.surname_tokens:
        # One word of a multi-word MK surname ("אטבריאן" for "דיסטל אטבריאן").
        return "public", "roster_surname_part"
    if len(seq) == 1 and seq[0] & speaker_tokens:
        # A lone given name of someone who spoke in this sitting ("תודה, מיקי").
        return "public", "sitting_speaker"
    if len(toks) >= 2 and any(_ends_with(seq, s) for s in roster.surnames):
        # A first name plus an MK's surname, but not that MK's first name: a namesake.
        return "private", "surname_namesake"
    return "private", "not_public"


def expand_to_words(text: str, start: int, end: int) -> tuple[int, int]:
    """Widen ``[start, end)`` to whole whitespace-delimited words of ``text``.

    Sub-word taggers can cut a name mid-word ("נעמה לזי" for "נעמה לזימי"), which would
    turn an MK into an unknown; trailing punctuation is trimmed after widening.
    """

    start = max(0, min(start, len(text)))
    end = max(start, min(end, len(text)))
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    while end > start and text[end - 1] in ",.:;!?)]}":
        end -= 1
    while start < end and text[start] in "([{":
        start += 1
    return start, end


def heuristic_person_spans(text: str) -> list[dict[str, Any]]:
    """Mentions that follow a private-person cue: the next one or two Hebrew words."""

    spans: list[dict[str, Any]] = []
    words = list(re.finditer(r"\S+", text))
    for i, m in enumerate(words):
        cue = m.group().strip(",.:;!?()[]{}")
        # Exact cue, or one proclitic on a cue longer than two letters ("והאזרח"); never
        # "לומר" -> "מר".
        if cue not in PRIVATE_CUES and not (len(cue) > 3 and cue[1:] in PRIVATE_CUES and cue[0] in _PREFIXES):
            continue
        name_words = []
        for nxt in words[i + 1 : i + 3]:
            tok = nxt.group().strip(_EDGE_PUNCT)
            if not tok or not _HEB_WORD.fullmatch(tok) or tok in PRIVATE_CUES or tok in PUBLIC_ROLE_WORDS:
                break
            name_words.append(nxt)
            if nxt.group()[-1:] in ",.:;!?)":
                break
        if name_words:
            start = name_words[0].start()
            end = name_words[-1].start() + len(name_words[-1].group().rstrip(",.:;!?)"))
            spans.append({"start": start, "end": end, "text": text[start:end], "source": "cue:" + cue})
    return spans


# A speaker heading: "דני נווה (הליכוד):" or "שר העבודה יואב בן צור:". Plenary speakers
# are MKs, ministers and the chair, so names in a heading are public.
_SPEAKER_HEADING = re.compile(r"^\s*[^:()\n]{2,60}(?:\s*\([^()\n]{1,80}\))?\s*:\s*$")


def is_speaker_heading(text: str) -> bool:
    return bool(_SPEAKER_HEADING.match(text))


@dataclass
class GateResult:
    kept: list[dict[str, Any]] = field(default_factory=list)
    dropped: list[dict[str, Any]] = field(default_factory=list)
    reasons: Counter = field(default_factory=Counter)

    def summary(self, roster: Roster, tagger: str) -> dict[str, Any]:
        return {
            "gate": GATE_ID,
            "decision": DECISION_PATH,
            "tagger": tagger,
            "roster": {"source": roster.source, "sha256": roster.sha256},
            "lines_in": len(self.kept) + len(self.dropped),
            "lines_kept": len(self.kept),
            "lines_dropped": len(self.dropped),
            "drop_reasons": dict(sorted(self.reasons.items())),
        }


def _mentions(text: str, spans: Iterable[Mapping[str, Any]]) -> list[tuple[int, str]]:
    """Normalise spans to whole words and merge neighbours split by the tagger.

    A tagger can split one name into two spans (the given name and the surname); judged
    apart, each half may match some MK, so spans separated only by whitespace are joined
    into one mention. A span that is only partly on this line keeps its full text.
    """

    norm: list[list[Any]] = []
    for span in spans:
        start, end = int(span.get("start", 0)), int(span.get("end", 0))
        mention = str(span.get("text", ""))
        whole = bool(mention) and text[start:end] == mention
        if whole:
            start, end = expand_to_words(text, start, end)
            mention = text[start:end]
        norm.append([start, end, mention, whole])
    norm.sort(key=lambda x: (x[0], x[1]))
    merged: list[list[Any]] = []
    for item in norm:
        if merged:
            prev = merged[-1]
            gap = text[prev[1]:item[0]] if item[0] >= prev[1] else ""
            if item[0] < prev[1] or (prev[3] and item[3] and gap.strip() == ""):
                if prev[3] and item[3]:
                    prev[1] = max(prev[1], item[1])
                    prev[2] = text[prev[0]:prev[1]]
                elif item[2] not in prev[2]:
                    prev[2] = f"{prev[2]} {item[2]}"
                continue
        merged.append(item)
    return [(m[0], m[2]) for m in merged]


def gate_lines(
    lines: Iterable[Mapping[str, Any]],
    roster: Roster,
    allowlist: Allowlist = Allowlist(),
    *,
    use_heuristic: bool = True,
) -> GateResult:
    """Split plenary lines into kept and dropped.

    Each line needs ``text`` and ``person_spans`` (a list, possibly empty, of dicts with
    ``start``/``end``/``text`` in line coordinates). ``person_spans: None`` means the
    line was never tagged: it is dropped with reason ``untagged``.
    """

    lines = list(lines)
    speakers: dict[str, set[str]] = {}
    for line in lines:
        text = str(line.get("text", ""))
        if is_speaker_heading(text):
            name = re.sub(r"\([^)]*\)", " ", text.split(":")[0])
            speakers.setdefault(str(line.get("unit_id", "")), set()).update(
                t for t in _tokens(name) if t not in PUBLIC_ROLE_WORDS
            )
    result = GateResult()
    for line in lines:
        text = str(line.get("text", ""))
        spans = line.get("person_spans")
        if spans is None:
            result.dropped.append({**line, "privacy_drop": ["untagged"]})
            result.reasons["untagged"] += 1
            continue
        if is_speaker_heading(text):
            result.kept.append({**line, "privacy_gate": GATE_ID, "privacy_note": "speaker_heading"})
            continue
        spans = list(spans) + (heuristic_person_spans(text) if use_heuristic else [])
        verdicts = []
        for start, mention in _mentions(text, spans):
            kind, reason = classify_person(
                mention, text[:start], roster, allowlist,
                frozenset(speakers.get(str(line.get("unit_id", "")), ())),
            )
            if kind == "private":
                verdicts.append(reason)
        if verdicts:
            result.dropped.append({**line, "privacy_drop": sorted(set(verdicts))})
            for reason in set(verdicts):
                result.reasons[reason] += 1
        else:
            result.kept.append({**line, "privacy_gate": GATE_ID})
    return result


class UngatedPlenaryLinesError(ValueError):
    """Raised when plenary lines reach intake without passing this gate."""


def _is_plenary(row: Any) -> bool:
    from hocrgen.split.eval_reserved import PLENARY_SOURCE_ID, _get, governed_unit

    source = str(_get(row, "source_id") or "")
    if source.startswith("knesset_plenary"):
        return True
    unit = governed_unit(row)
    if unit is not None and unit.source_id == PLENARY_SOURCE_ID:
        return True
    return any(str(_get(row, name) or "").startswith("plenary:") for name in ("unit_id", "source_unit"))


def _gate_of(row: Any) -> Any:
    from hocrgen.split.eval_reserved import _get

    gate = _get(row, "privacy_gate")
    metadata = _get(row, "metadata")
    if gate is None and isinstance(metadata, Mapping):
        gate = metadata.get("privacy_gate")
    return gate


def refuse_ungated_plenary_lines(rows: Iterable[Any], *, builder: str = "plenary intake") -> int:
    """Intake guard: every plenary row must carry ``privacy_gate == GATE_ID``.

    A row is a plenary row when its ``source_id`` starts with ``knesset_plenary``, when
    the eval-reserved id patterns place it in a plenary sitting (``plenary:K<k>_<s>``,
    any identifier field), or when its ``unit_id``/``source_unit`` starts with
    ``plenary:``. The gate stamp is read from the row or from its ``metadata``. Every
    plenary line builder calls this on its line rows before writing a manifest, and the
    release export calls it on every item. Returns the number of plenary rows checked.
    """

    checked = 0
    refused: list[str] = []
    for row in rows:
        if not _is_plenary(row):
            continue
        checked += 1
        if _gate_of(row) != GATE_ID:
            from hocrgen.split.eval_reserved import _get

            refused.append(str(_get(row, "line_id") or _get(row, "item_id") or _get(row, "unit_id") or "?"))
    if refused:
        shown = ", ".join(refused[:10]) + (f" and {len(refused) - 10} more" if len(refused) > 10 else "")
        raise UngatedPlenaryLinesError(
            f"{builder}: refused {len(refused)} plenary row(s) without privacy_gate={GATE_ID!r}; run "
            f"hocrgen.privacy.plenary_names.gate_lines first ({DECISION_PATH}): {shown}"
        )
    return checked
