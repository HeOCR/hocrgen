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
2. **Public or private.** A mention is public only when it is in a proven speaker
   heading (:func:`proven_speaker_heading`), a public title ends immediately before it
   (:func:`_title_before`: exact titles and whole title phrases, no proclitic
   stripping), it is on the allowlist, or it matches the roster: by full name or part
   of one against everyone, by bare surname only against that Knesset term. Lone
   given names and namesakes are private. The decision record has the full rules.
3. **Drop.** A line with any private mention, or with a mention that could not be
   judged, is dropped. Lines that have not been tagged at all are refused by
   :func:`refuse_ungated_plenary_lines`.

The gate prefers dropping: a public figure missing from the roster costs a line,
never a leak. The known leak is a private person referred to by a bare surname that
someone in that Knesset term shares; private persons in the record are normally named
in full, and the full-name check catches those.
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

# Cues that the next words name a private person (used by the heuristic tagger).
PRIVATE_CUES: frozenset[str] = frozenset(
    {
        "מר", "גב'", "גב׳", "גברת", "הגברת", "האזרח", "האזרחית", "התושב", "התושבת",
        "ששמו", "ששמה", "משפחת",
    }
)


def _strip_niqqud(text: str) -> str:
    return _NIQQUD.sub("", text)


def _norm(token: str) -> str:
    """Spelling-normalise one token: doubled vav and yod are single ("נווה" = "נוה")."""

    return token.replace("וו", "ו").replace("יי", "י")


def _tokens(text: str) -> list[str]:
    # Hyphen and maqaf split compound names ("אבנר-חי", "פולישוק-בלוך") into tokens, so a
    # roster entry and a mention match whichever way the compound was written.
    text = re.sub(r"[-\u05be]", " ", _strip_niqqud(text))
    return [_norm(t.strip(_EDGE_PUNCT)) for t in _HEB_WORD.findall(text) if t.strip(_EDGE_PUNCT)]


def _is_initial(token: str) -> bool:
    """A one-letter initial such as "י'" (the apostrophe is already stripped)."""

    return len(token) == 1 and "\u05d0" <= token <= "\u05ea"


def _variants(token: str) -> set[str]:
    """The token and its forms with up to two proclitic letters removed."""

    out = {token}
    if len(token) > 2 and token[0] in _PREFIXES:
        out.add(token[1:])
        if len(token) > 3 and token[1] in _PREFIXES:
            out.add(token[2:])
    return out


# Public titles. A title counts only when it ends *immediately* before the name, is
# matched exactly (no proclitic stripping, except a leading "ו" on a title of four or
# more letters: "והשר"), and is never an ordinary word in another sense: "ראש", "סגן",
# "חבר", "מנהל", "מזכיר" and military ranks are out as single words. Multi-word titles
# are matched as whole phrases. Hyphens split tokens, so "יושב-ראש" is "יושב ראש".
SINGLE_TITLES: frozenset[str] = frozenset(_norm(t) for t in
    {
        "השר", "השרה", "הנשיא", "הנשיאה", "השופט", "השופטת", "השגריר", "השגרירה",
        'ח"כ', "ח״כ", 'חה"כ', "חה״כ", 'היו"ר', "היו״ר", 'יו"ר', "יו״ר",
        'הרמטכ"ל', "הרמטכ״ל", 'המפכ"ל', "המפכ״ל", "המלך", "המלכה", "הקנצלר", "הקנצלרית",
    }
)

TITLE_PHRASES: frozenset[tuple[str, ...]] = frozenset(
    tuple(_tokens(p))
    for p in (
        "חבר הכנסת", "חברת הכנסת", "חברי הכנסת", "חברות הכנסת", "ראש הממשלה", "ראשת הממשלה",
        "ממלא מקום ראש הממשלה", "מבקר המדינה", "מבקרת המדינה", "היועץ המשפטי לממשלה",
        "היועצת המשפטית לממשלה", "היועץ המשפטי לכנסת", "היועצת המשפטית לכנסת",
        "נציב תלונות הציבור", "נציבת תלונות הציבור", "נשיא המדינה", "נשיאת המדינה",
        "נשיא בית המשפט העליון", "נשיאת בית המשפט העליון", "שופט בית המשפט העליון",
        "שופטת בית המשפט העליון", "יושב ראש הכנסת", "יושבת ראש הכנסת", "היושב ראש",
        "היושבת ראש", "יושב ראש הוועדה", "יושבת ראש הוועדה", 'סגן יו"ר הכנסת',
        'סגנית יו"ר הכנסת', "סגן יו״ר הכנסת", "סגנית יו״ר הכנסת", "סגן השר", "סגנית השר",
        "סגן ראש הממשלה", "סגנית ראש הממשלה", "מזכיר הכנסת", "מזכירת הכנסת",
        "מזכיר הממשלה", "מזכירת הממשלה", "ראש העיר", "ראשת העיר", "ראש הממשלה לשעבר",
        "הרב הראשי", "שר החוץ של ארצות הברית", "נשיא ארצות הברית",
    )
)

# "שר X" / "השר ל-X" is a title only when X is a ministry word.
_MINISTER_HEADS = frozenset({"שר", "שרת", "השר", "השרה", "סגן שר", "סגנית שר"})
MINISTRY_WORDS: frozenset[str] = frozenset(_norm(t) for t in
    {
        "האוצר", "החוץ", "הביטחון", "הפנים", "המשפטים", "החינוך", "הבריאות", "התחבורה",
        "העבודה", "הרווחה", "החקלאות", "התיירות", "המדע", "התקשורת", "הקליטה", "השיכון",
        "הבינוי", "התשתיות", "האנרגיה", "הכלכלה", "התעשייה", "המסחר", "הדתות", "התרבות",
        "הספורט", "הסביבה", "המודיעין", "ההסברה", "התפוצות", "המורשת", "החדשנות", "הנגב",
        "הגליל", "המשטרה", "הפיתוח", "ההתיישבות", "התכנון", "המים", "האנרגייה", "הפריפריה",
        "לביטחון", "להגנת", "לאיכות", "לשיתוף", "לענייני", "לפיתוח", "לשוויון",
        "להתיישבות", "לירושלים", "לקליטת", "לשירותי", "לנושאים", "לביטחון-פנים",
    }
)


# Words that may follow a ministry word inside a minister's title ("השר לביטחון פנים",
# "שר העבודה והרווחה"). Every token after the head must be a ministry word or one of these.
_MINISTRY_CONTINUATIONS: frozenset[str] = frozenset(_norm(t) for t in {
    "פנים", "הפנים", "והרווחה", "והשיכון", "והספורט", "והתרבות", "והתעסוקה", "והמסחר",
    "והתעשייה", "החברתי", "החברתית", "הלאומיות", "הלאומית", "האסטרטגיות", "האזורי",
    "האזורית", "הכלכלי", "הכלכלית", "השירותים", "החברתיים", "ירושלים", "מורשת",
    "הסביבה", "איכות", "התיירות", "המדע", "והטכנולוגיה", "הטכנולוגיה", "והחלל", "החלל",
})


def _title_before(before: Sequence[str]) -> bool:
    """Whether the tokens right before a name end with a public title."""

    if not before:
        return False
    last = before[-1]
    if last in SINGLE_TITLES or (len(last) >= 4 and last[0] == "ו" and last[1:] in SINGLE_TITLES):
        return True
    for n in range(2, 7):
        if len(before) < n:
            break
        tail = tuple(before[-n:])
        if tail in TITLE_PHRASES:
            return True
        if tail[0][0] == "ו" and len(tail[0]) >= 4 and (tail[0][1:],) + tail[1:] in TITLE_PHRASES:
            return True
    # A minister's title: "שר האוצר", "השר לביטחון פנים", "סגן שר החינוך".
    for head_len in (1, 2):
        for k in range(1, 4):
            if len(before) < head_len + k:
                continue
            head = " ".join(before[-(head_len + k):-k])
            if head[:1] == "ו" and head[1:] in _MINISTER_HEADS:
                head = head[1:]  # "ושר הביטחון": safe here, the ministry word must follow
            tail = before[-k:]
            if head in _MINISTER_HEADS and tail[0] in MINISTRY_WORDS and all(
                t in MINISTRY_WORDS or t in _MINISTRY_CONTINUATIONS for t in tail[1:]
            ):
                return True
    return False


@dataclass(frozen=True)
class Roster:
    """Public persons by normalised name: full names and surnames as token tuples."""

    full_names: frozenset[tuple[str, ...]]
    surnames: frozenset[tuple[str, ...]]
    source: str = ""
    sha256: str = ""
    surname_tokens: frozenset[str] = frozenset()
    # Surnames of the people who held a position in each Knesset term.
    surnames_by_knesset: Mapping[int, frozenset[tuple[str, ...]]] = field(default_factory=dict)
    surname_tokens_by_knesset: Mapping[int, frozenset[str]] = field(default_factory=dict)
    # Faction names per Knesset term, as token tuples (``KNS_PersonToPosition.FactionName``).
    factions_by_knesset: Mapping[int, frozenset[tuple[str, ...]]] = field(default_factory=dict)

    def surnames_for(self, knesset: int | None) -> tuple[frozenset[tuple[str, ...]], frozenset[str]]:
        """All-time surnames, or those of one Knesset term when it is known and listed."""

        if knesset is not None and self.surnames_by_knesset:
            # A term the roster does not list matches no bare surname (fail closed).
            return (self.surnames_by_knesset.get(knesset, frozenset()),
                    self.surname_tokens_by_knesset.get(knesset, frozenset()))
        return self.surnames, self.surname_tokens

    @classmethod
    def from_people(cls, people: Iterable[Mapping[str, Any]], *, source: str = "", sha256: str = "",
                    factions: Mapping[Any, Iterable[str]] | None = None) -> "Roster":
        full: set[tuple[str, ...]] = set()
        last: set[tuple[str, ...]] = set()
        toks: set[str] = set()
        by_k: dict[int, set[tuple[str, ...]]] = {}
        for person in people:
            first_toks = tuple(_tokens(person.get("first", "") or ""))
            last_toks = tuple(_tokens(person.get("last", "") or ""))
            if not last_toks:
                continue
            last.add(last_toks)
            toks.update(last_toks)
            for k in person.get("knessets") or ():
                by_k.setdefault(int(k), set()).add(last_toks)
            if first_toks:
                full.add(first_toks + last_toks)
                # Common usage drops middle names: "first-of-first + last".
                full.add(first_toks[:1] + last_toks)
        return cls(
            frozenset(full), frozenset(last), source, sha256, frozenset(toks),
            {k: frozenset(v) for k, v in by_k.items()},
            {k: frozenset(t for name in v for t in name) for k, v in by_k.items()},
            {int(k): frozenset(tuple(_tokens(f)) for f in v if _tokens(f)) for k, v in (factions or {}).items()},
        )

    @classmethod
    def load(cls, path: Path | str) -> "Roster":
        import hashlib

        path = Path(path)
        raw = path.read_bytes()
        data = json.loads(raw)
        return cls.from_people(data["people"], source=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                               factions=data.get("factions_by_knesset"))


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
    knesset: int | None = None,
) -> tuple[str, str]:
    """Return ``("public" | "private", reason)`` for one person-name mention.

    A lone given name is always private: common names ("מוחמד", "יוסי") collide with
    speakers' names, so a sitting's speaker list cannot vouch for one. ``knesset`` restricts bare-surname matches to people who held a position in that
    term; full-name matches use the whole roster.
    """

    toks = _tokens(mention)
    if not toks:
        return "private", "empty_mention"
    before = _tokens(left_context)
    # Initials before the tagged name belong to it ("ש' כרם"): look past them for a title.
    while before and _is_initial(before[-1]):
        before = before[:-1]
    # A title inside the mention itself ("השר יואב בן צור") counts as coming before it.
    for i in range(len(toks) - 1, 0, -1):
        if _title_before(toks[:i]):
            before, toks = before + toks[:i], toks[i:]
            break
    toks = [t for t in toks if not _is_initial(t)] or toks
    if _title_before(before):
        return "public", "title"
    seq = [_variants(t) for t in toks]
    surnames, surname_tokens = roster.surnames_for(knesset)
    if any(_equals(seq, name) for name in allowlist.names):
        return "public", "allowlist"
    if any(_ends_with(seq, name) for name in roster.full_names):
        return "public", "roster_full_name"
    if any(_equals(seq, s) for s in surnames):
        return "public", "roster_surname"
    if any(_contains(seq, name) for name in roster.full_names):
        # Part of an MK's full name: "גלית דיסטל" for "גלית דיסטל אטבריאן".
        return "public", "roster_partial_name"
    if len(seq) == 1 and seq[0] & surname_tokens:
        # One word of a multi-word MK surname ("אטבריאן" for "דיסטל אטבריאן").
        return "public", "roster_surname_part"
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
            if not tok or not _HEB_WORD.fullmatch(tok) or tok in PRIVATE_CUES or tok in SINGLE_TITLES:
                break
            name_words.append(nxt)
            if nxt.group()[-1:] in ",.:;!?)":
                break
        if name_words:
            start = name_words[0].start()
            end = name_words[-1].start() + len(name_words[-1].group().rstrip(",.:;!?)"))
            spans.append({"start": start, "end": end, "text": text[start:end], "source": "cue:" + cue})
    return spans


# The shape of a speaker heading: "דני נווה (הליכוד):" or "שר העבודה יואב בן צור:". The
# shape alone proves nothing: "וכך כתבה לי <name>:" introduces a letter read aloud.
_SPEAKER_HEADING = re.compile(r"^\s*[^:()\n]{2,60}(?:\s*\([^()\n]{1,80}\))?\s*:\s*$")


def is_speaker_heading(text: str) -> bool:
    """Whether a line has the *shape* of a speaker heading (not proof that it is one)."""

    return bool(_SPEAKER_HEADING.match(text))


def _faction_matches(text: str, factions: frozenset[tuple[str, ...]]) -> bool:
    """The heading's parenthetical names a faction of that term (or a leading part of one)."""

    m = re.search(r"\(([^()]*)\)\s*:\s*$", text)
    if not m:
        return False
    toks = tuple(_tokens(m.group(1)))
    if not toks:
        return False
    return any(f == toks or f[: len(toks)] == toks or toks[: len(f)] == f for f in factions)


def proven_speaker_heading(line: Mapping[str, Any], roster: Roster) -> tuple[str, ...] | None:
    """The speaker's name tokens when ``line`` is a proven speaker heading, else ``None``.

    Proof is one of:

    - the source's own structure (``is_speaker_heading: True``, set by a builder that
      reads the document's speaker style);
    - a heading-shaped line whose name, after any leading title, is wholly a roster name:
      a full name or a contiguous part of one;
    - a title, then optional initials, then a surname of someone in that Knesset term
      ("ראש הממשלה ושר הביטחון י' רבין:");
    - a faction of that term in the parentheses, with the name ending in a surname (or
      the end of a multi-word surname) of someone in that term ("דני נווה (הליכוד):"
      for the roster's "דני נוה"). A letter's intro carries no faction.

    Anything else is judged as an ordinary line.
    """

    text = str(line.get("text", ""))
    name = re.sub(r"\([^)]*\)", " ", text.split(":")[0])
    toks = _tokens(name)
    if line.get("is_speaker_heading") is True:
        return tuple(toks)
    if not is_speaker_heading(text) or not toks:
        return None
    titled = False
    for i in range(len(toks) - 1, 0, -1):  # the longest title prefix ("ראש הממשלה ושר הביטחון")
        if _title_before(toks[:i]):
            toks, titled = toks[i:], True
            break
    seq = [{t} for t in toks]
    if len(seq) >= 2 and (
        any(_ends_with(seq, n) for n in roster.full_names) or any(_contains(seq, n) for n in roster.full_names)
    ):
        return tuple(toks)
    knesset = _knesset_of(line)
    surnames, surname_tokens = roster.surnames_for(knesset)
    bare = [{t} for t in toks if not _is_initial(t)]
    if titled and bare and any(_equals(bare, s) for s in surnames):
        return tuple(toks)
    factions = roster.factions_by_knesset.get(knesset, frozenset()) if knesset is not None else frozenset()
    if len(bare) >= 2 and _faction_matches(text, factions) and (
        any(_ends_with(bare, s) for s in surnames) or bare[-1] & surname_tokens
    ):
        return tuple(toks)
    return None


def _knesset_of(line: Mapping[str, Any]) -> int | None:
    k = line.get("knesset")
    if k not in (None, ""):
        return int(k)
    m = re.match(r"plenary:K(\d+)_", str(line.get("unit_id", "")))
    return int(m.group(1)) if m else None


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
    headings = {i for i, line in enumerate(lines) if proven_speaker_heading(line, roster) is not None}
    result = GateResult()
    for i, line in enumerate(lines):
        text = str(line.get("text", ""))
        spans = line.get("person_spans")
        if i in headings:
            result.kept.append({**line, "privacy_gate": GATE_ID, "privacy_note": "speaker_heading"})
            continue
        if spans is None:
            result.dropped.append({**line, "privacy_drop": ["untagged"]})
            result.reasons["untagged"] += 1
            continue
        spans = list(spans) + (heuristic_person_spans(text) if use_heuristic else [])
        verdicts = []
        for start, mention in _mentions(text, spans):
            kind, reason = classify_person(
                mention, text[:start], roster, allowlist, _knesset_of(line),
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
