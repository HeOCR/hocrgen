"""Operator-only inventory of Hebrew Wikisource ProofreadPage Indexes through the F8b gates (F8b2, F8b3).

The tool enumerates every ``מפתח:`` (Index) page on he.wikisource.org and its quality-3/4 ``עמוד:`` pages,
gathers per-Index rights evidence, and runs each Index through the unchanged F8b gate
(``hocrgen.fetchers.wikisource.index_exclusion_reasons``). Pages of admitted Indexes are then pinned
(revision history, wikitext, derived text) into an operator snapshot root outside the repo and run through
``page_exclusion_reasons`` and ``page_attestation``.

Evidence is gathered, never guessed:

- **Creators** come from the Index page fields (author, translator, editor, illustrator) and the Commons
  ``{{Book}}`` / ``{{Information}}`` fields. Death years come from Wikidata ``P570`` (an upper bound at the
  statement's precision; the latest of several statements) or from the Wikisource author page's Gregorian
  death year, then from cited facts in the recorded evidence file (``--index-evidence``; F8b3) for creators
  the wikis name only as plain text. A creator without any keeps ``death_year: null``.
- **Work rights** (decision 10, F8b3): every creator dead by 1955 gives ``author_died_by_1955``; failing that,
  a work published on or before 1855 gives ``presumed_pd_by_publication_age``, with the year's evidence.
  Anonymous works take ``anonymous_published_by_1955`` only when every creator field carries an explicit
  anonymous or unknown-author marker. State works are never assigned automatically.
- **Scan rights** (decisions 9 and 10): an open licence template gives ``explicit_open_licence``; any other
  flat scan of a PD work is a ``faithful_reproduction_of_pd_work``, whatever the Commons tag. The scan source
  (a Commons ``source`` / ``institution`` field naming a scanning body, a URL host or the uploader's own work)
  and Google digitization (from the Commons record, categories and the file's metadata / text layer) are
  recorded as provenance and decide nothing.
- **Language** is the Index page's ``שפה`` field, else the Commons file's ``language`` field, else a recorded
  fact; the gate admits only ``he`` (F8b3).
- **Transcription coverage** is not assessed automatically. Render checks recorded per page in a reviewable
  file (``--page-checks``, committed as ``docs/wikisource_page_checks.json``; F8b3) set a page's
  ``transcription_coverage`` and per-page Google-stamp fact. Each check names who made it (``checked_by``:
  ``agent`` or ``human``), the method and the date, and is pinned to the page revision and the Commons file
  SHA-1; a human check overrides an agent check of the same page. Pages without a current check stay
  ``transcription_coverage_unrecorded``, and the report counts pages that pass every other gate.

Nothing is edited on Wikisource, Commons or Wikidata. The raw cache, the operator snapshot and the full
inventory JSON live outside the repo; only the compact per-Index JSON (ids, rights evidence and gate
results; no page text, no images) and the rendered markdown summary are committed. CI never runs the
network path: ``render_summary`` and the gate replay are network-free.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from hocrgen.config.loader import package_root
from hocrgen.fetchers.wikisource import (
    ADMITTED_QUALITY_LEVELS,
    PD_ISRAEL_DEATH_CUTOFF_YEAR,
    PD_ISRAEL_PRESUMPTION_PUBLICATION_CUTOFF_YEAR,
    GOOGLE_DIGITIZATION_MARKERS,
    OPEN_SCAN_LICENCES,
    TRANSCRIPTION_COVERAGE_PARTIAL,
    TRANSCRIPTION_COVERAGE_VALUES,
    index_exclusion_reasons,
    licence_tokens,
    load_wikisource_snapshot,
    page_attestation,
    page_exclusion_reasons,
    page_needs_crop,
    scan_source_origin,
)
from hocrgen.parsers.wikitext import UnsupportedWikitextError, convert_wikitext, pagequality_level, wikitext_to_plain_text

INVENTORY_SCHEMA_VERSION = "wikisource_index_inventory.v1"
PAGE_CHECKS_SCHEMA_VERSION = "wikisource_page_render_checks.v1"
PAGE_CHECKERS = ("agent", "human")
USER_AGENT = "hocrgen-wikisource-inventory/0.1 (https://github.com/HeOCR/hocrgen; operator inventory)"
WS_API = "https://he.wikisource.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WS_SITE = "https://he.wikisource.org"
INDEX_NAMESPACE = 112
PAGE_NAMESPACE = 104
COVERAGE_PENDING_REASON = "transcription_coverage_unrecorded"

INDEX_CREATOR_FIELDS = {"מחבר": "author", "מתרגם": "translator", "עורך": "editor", "מאייר": "illustrator"}
COMMONS_CREATOR_FIELDS = {"author": "author", "translator": "translator", "editor": "editor", "illustrator": "illustrator"}
WIKIDATA_CREATOR_PROPERTIES = {"P50": "author", "P655": "translator", "P98": "editor", "P110": "illustrator"}
ANONYMOUS_MARKERS = ("אנונימי", "אלמוני", "לא ידוע", "anonymous", "unknown")
OTHERS_MARKERS = ("ועוד", "ואחרים", "et al")

# Commons licence token (casefolded) -> licence id in OPEN_SCAN_LICENCES.
OPEN_LICENCE_TOKENS = {
    "cc-zero": "CC0-1.0",
    "cc0": "CC0-1.0",
    "cc-0": "CC0-1.0",
    "cc-pd-mark": "PDM-1.0",
    "cc-by-4.0": "CC-BY-4.0",
    "cc-by-sa-4.0": "CC-BY-SA-4.0",
}

# Ordered (needle, scanning body name). Matched against the casefolded source/institution fields.
SCAN_SOURCE_NAMES = (
    ("books.google", "Google Books"),
    ("google", "Google Books"),
    ("hebrewbooks", "HebrewBooks"),
    ("opensiddur", "Open Siddur Project"),
    ("open siddur", "Open Siddur Project"),
    ("national library of israel", "National Library of Israel"),
    ("nli.org.il", "National Library of Israel"),
    ("{{nnl", "National Library of Israel"),
    ("הספריה הלאומית", "National Library of Israel"),
    ("הספרייה הלאומית", "National Library of Israel"),
    ("archive.org", "Internet Archive"),
    ("{{ia|", "Internet Archive"),
    ("hebrew national library", "National Library of Israel"),
    ("internet archive", "Internet Archive"),
    ("hathitrust", "HathiTrust"),
    ("chabadlibrary", "Chabad-Lubavitch Library"),
    ("daat.ac.il", "Daat"),
    ("wdl.org", "World Digital Library"),
    ("loc.gov", "Library of Congress"),
    ("sammlungen.ub.uni-frankfurt", "Frankfurt University Library"),
    ("digi.ub.uni-heidelberg", "Heidelberg University Library"),
    ("mdz-nbn-resolving", "Bavarian State Library"),
    ("digitale-sammlungen", "Bavarian State Library"),
    ("e-rara", "e-rara"),
)
OWN_WORK_MARKERS = ("{{own}}", "{{own work}}", "own work", "{{self-photographed}}", "עבודה עצמית")

_WIKIDATA_ID = re.compile(r"(?<![\w])Q[1-9]\d*(?![\w])")
_AUTHOR_LINK = re.compile(r"\[\[\s*:?\s*מחבר\s*:\s*([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_WIKIPEDIA_TEMPLATE = re.compile(r"\{\{\s*דף ויקיפדיה\s*\|\s*([^}|]+)(?:\|[^}]*)?\}\}")
_WIKIPEDIA_LINK = re.compile(r"\[\[\s*:?\s*(?:w|wikipedia|ויקיפדיה)\s*:\s*(?:(he|en)\s*:\s*)?([^\]|]+)(?:\|[^\]]*)?\]\]", re.IGNORECASE)
_LANG_WIKI_LINK = re.compile(r"\[\[\s*:\s*(he|en)\s*:\s*([^\]|]+)(?:\|[^\]]*)?\]\]", re.IGNORECASE)
# Role markers inside free-text Index fields (title, notes), e.g. "הערות=מתרגם: שמואל יוסף פין".
_ROLE_IN_TEXT = re.compile(
    r"(?P<marker>מתרגם|מתורגם|תרגום|תרגם|בתרגום|עורך|ערך|בעריכת|מאייר|translat(?:or|ed by)|edit(?:or|ed by))\s*:?\s*"
    r"(?P<name>\[\[[^\]]+\]\]|\{\{[^}]+\}\}|[^()\n,.;\[\]{}]+)",
    re.IGNORECASE,
)
INDEX_TEXT_FIELDS = ("כותרת", "הערות", "Remarks")
_CREATOR_TEMPLATE = re.compile(r"\{\{\s*[Cc]reator\s*:\s*([^}|]+)(?:\|[^}]*)?\}\}")
_YEAR = re.compile(r"^\s*(1[0-9]{3}|20[0-9]{2})\b")

FetchJson = Callable[[str, dict[str, Any]], dict[str, Any]]


# --- Network client (operator path) ----------------------------------------------------------------------


class MediaWikiClient:  # pragma: no cover - live network path, exercised by the operator run only
    """Cached, rate-limited MediaWiki API client with a Wikimedia-etiquette User-Agent and ``maxlag``."""

    def __init__(self, cache_dir: Path, *, delay: float = 0.5, user_agent: str = USER_AGENT) -> None:
        self.cache_dir = cache_dir
        self.delay = delay
        self.user_agent = user_agent
        self.requests = 0
        cache_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, api: str, params: dict[str, Any]) -> dict[str, Any]:
        body = {**{key: str(value) for key, value in params.items()}, "format": "json", "formatversion": "2"}
        encoded = urllib.parse.urlencode(sorted(body.items()))
        cached = self.cache_dir / f"{hashlib.sha256((api + '?' + encoded).encode()).hexdigest()[:32]}.json"
        if cached.exists():
            return json.loads(cached.read_text(encoding="utf-8"))
        # maxlag on Wikidata also counts query-service lag, which concerns edits, not reads like these.
        payload = self._request(api, body if api == WIKIDATA_API else {**body, "maxlag": "5"})
        cached.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return payload

    def _request(self, api: str, body: dict[str, str]) -> dict[str, Any]:
        data = urllib.parse.urlencode(body).encode()
        for attempt in range(6):
            time.sleep(self.delay)
            request = urllib.request.Request(
                api, data=data, headers={"User-Agent": self.user_agent, "Content-Type": "application/x-www-form-urlencoded"}
            )
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504}:
                    time.sleep(min(60, 5 * 2**attempt))
                    continue
                raise
            self.requests += 1
            error = payload.get("error") if isinstance(payload, dict) else None
            if error and error.get("code") == "maxlag":
                time.sleep(min(60, 5 * 2**attempt))
                continue
            if error:
                raise RuntimeError(f"MediaWiki API error from {api}: {error}")
            return payload
        raise RuntimeError(f"MediaWiki API kept failing: {api}")


def _query_all(fetch: FetchJson, api: str, params: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """Yield each ``query`` block of a continued MediaWiki query."""

    cont: dict[str, Any] = {}
    while True:
        payload = fetch(api, {"action": "query", **params, **cont})
        yield payload.get("query") or {}
        if "continue" not in payload:
            return
        cont = payload["continue"]


def _chunks(items: list[str], size: int = 50) -> Iterable[list[str]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


# --- Wikitext field helpers --------------------------------------------------------------------------------


def template_field(wikitext: str, *names: str) -> str | None:
    """Value of the first ``|name = value`` line (case-insensitive), joined with its continuation lines."""

    wanted = {name.casefold() for name in names}
    lines = wikitext.split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"^\s*\|\s*([^=|{}\[\]]+?)\s*=(.*)$", line)
        if not match or match.group(1).casefold() not in wanted:
            continue
        value = [match.group(2)]
        for follow in lines[index + 1 :]:
            joined = "\n".join(value)
            open_templates = joined.count("{{") - joined.count("}}")
            if open_templates <= 0 and re.match(r"^\s*(\||\}\})", follow):
                break
            value.append(follow)
        return _lang_switch("\n".join(value)).strip() or None
    return None


def _lang_switch(value: str) -> str:
    """Keep one language of a Commons ``{{LangSwitch|en=...|he=...}}`` (English, else the first)."""

    match = re.search(r"\{\{\s*LangSwitch\s*\|", value, re.IGNORECASE)
    if not match:
        return value
    depth, index = 0, match.start()
    while index < len(value):
        if value.startswith("{{", index):
            depth += 1
            index += 2
        elif value.startswith("}}", index):
            depth -= 1
            index += 2
            if depth == 0:
                break
        else:
            index += 1
    body = value[match.end() : index - 2]
    options: dict[str, str] = {}
    for part in re.split(r"\|\s*(?=[a-z-]+\s*=)", body):
        key, _, text = part.partition("=")
        if text:
            options[key.strip().casefold()] = text.strip()
    chosen = options.get("en") or next(iter(options.values()), "")
    return value[: match.start()] + chosen + _lang_switch(value[index:])


def licence_templates(wikitext: str) -> list[str]:
    """Templates under the Commons licence header (the F8b capture's rule)."""

    _, header, tail = wikitext.partition("{{int:license-header}}")
    if not header:
        match = re.search(r"==\s*\{\{\s*int:license\s*\}\}\s*==|==\s*(?:Licen[cs]ing|רישיון)\s*:?\s*==", wikitext, re.IGNORECASE)
        tail = wikitext[match.end() :] if match else ""
    tail = re.split(r"\n\[\[Category:", tail, maxsplit=1)[0]
    return [match.strip() for match in re.findall(r"\{\{([^{}]+)\}\}", tail)]


def provenance_text(wikitext: str) -> str | None:
    """Free text before the licence header, outside templates and headings (the F8b capture's rule)."""

    head, _, _ = wikitext.partition("{{int:license-header}}")
    depth = 0
    out: list[str] = []
    index = 0
    while index < len(head):
        if head.startswith("{{", index):
            depth += 1
            index += 2
            continue
        if head.startswith("}}", index):
            depth = max(0, depth - 1)
            index += 2
            continue
        if depth == 0:
            out.append(head[index])
        index += 1
    text = re.sub(r"=+[^=\n]*=+", "", "".join(out))
    text = re.sub(r"\[\[Category:[^\]]*\]\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def wikitext_categories(wikitext: str) -> list[str]:
    return sorted({match.strip() for match in re.findall(r"\[\[Category:([^\]|]+)", wikitext)})


def _plain_name(text: str) -> str:
    text = re.sub(r"\[https?://[^\s\]]+\s*([^\]]*)\]", r"\1", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub("[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]", "", text)
    return re.sub(r"\s+", " ", text).strip(" .,;:-–־")


def _has_letters(text: str) -> bool:
    return sum(character.isalpha() for character in text) >= 2


def _is_marker(text: str, markers: Iterable[str]) -> bool:
    folded = text.casefold()
    return any(marker in folded for marker in markers)


def _names_match(name: str, names: set[str]) -> bool:
    """Exact normalised match, or a close spelling variant (e.g. אהרנזון / אהרנסון) of a full name."""

    if not name:
        return False
    if name in names:
        return True
    return len(name) >= 8 and any(len(other) >= 8 and difflib.SequenceMatcher(None, name, other).ratio() >= 0.85 for other in names)


def _normalise_name(name: str) -> str:
    name = re.sub(r"[\"'״׳.,\-־–()]", " ", name.casefold())
    return re.sub(r"\s+", " ", name).strip()


# --- Creator mentions ----------------------------------------------------------------------------------------


def index_creator_mentions(index_wikitext: str) -> list[dict[str, Any]]:
    """Creator mentions on an Index page: author-page links, Wikipedia names, plain names and markers."""

    mentions: list[dict[str, Any]] = []
    for field, role in INDEX_CREATOR_FIELDS.items():
        value = template_field(index_wikitext, field)
        if not value:
            continue
        mentions.extend(_linked_and_plain_mentions(value, role, f"index:{field}", default_wiki="hewiki"))
    for field in INDEX_TEXT_FIELDS:
        value = template_field(index_wikitext, field)
        for match in _ROLE_IN_TEXT.finditer(value or ""):
            marker = match.group("marker").casefold()
            role = "translator" if marker.startswith(("מתר", "תרג", "בתר", "transl")) else "illustrator" if marker == "מאייר" else "editor"
            for mention in _linked_and_plain_mentions(match.group("name"), role, f"index:{field}", default_wiki="hewiki"):
                mention["from_free_text"] = True
                mentions.append(mention)
    return mentions


def _linked_and_plain_mentions(value: str, role: str, origin: str, *, default_wiki: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    for match in _AUTHOR_LINK.finditer(value):
        mentions.append({"role": role, "author_page": match.group(1).strip(), "origin": origin})
    for match in _WIKIPEDIA_TEMPLATE.finditer(value):
        mentions.append({"role": role, "wiki_title": f"hewiki:{match.group(1).strip()}", "origin": origin})
    for match in _WIKIPEDIA_LINK.finditer(value):
        site = f"{match.group(1).lower()}wiki" if match.group(1) else default_wiki
        mentions.append({"role": role, "wiki_title": f"{site}:{match.group(2).strip()}", "origin": origin})
    for match in _LANG_WIKI_LINK.finditer(value):
        mentions.append({"role": role, "wiki_title": f"{match.group(1).lower()}wiki:{match.group(2).strip()}", "origin": origin})
    residual = _AUTHOR_LINK.sub(",", _LANG_WIKI_LINK.sub(",", _WIKIPEDIA_LINK.sub(",", _WIKIPEDIA_TEMPLATE.sub(",", value))))
    mentions.extend(_plain_mentions(residual, role, origin))
    return mentions


def commons_creator_mentions(file_wikitext: str) -> list[dict[str, Any]]:
    """Creator mentions in the Commons ``{{Book}}`` / ``{{Information}}`` fields."""

    mentions: list[dict[str, Any]] = []
    for field, role in COMMONS_CREATOR_FIELDS.items():
        value = template_field(file_wikitext, field)
        if not value:
            continue
        for match in _CREATOR_TEMPLATE.finditer(value):
            mentions.append({"role": role, "commons_creator": match.group(1).strip(), "origin": f"commons:{field}"})
        for qid in _WIKIDATA_ID.findall(value):
            mentions.append({"role": role, "wikidata": qid, "origin": f"commons:{field}"})
        residual = _CREATOR_TEMPLATE.sub(",", value)
        if _is_marker(residual, ANONYMOUS_MARKERS):
            mentions.append({"role": role, "anonymous": True, "name": _plain_name(residual) or "anonymous", "origin": f"commons:{field}"})
            continue
        residual = re.sub(r"\{\{[^{}]*\}\}", ",", re.sub(r"\{\{[^{}]*\}\}", ",", residual))
        if _WIKIDATA_ID.search(value):
            continue  # a {{Label|Q..}}-style value: the QID is the evidence; its display text is not a second creator
        mentions.extend(_linked_and_plain_mentions(residual, role, f"commons:{field}", default_wiki="enwiki"))
    return mentions


_ROLE_PREFIX = re.compile(
    r"^(?P<marker>מתרגם|תרגום|תרגם|בתרגום|עורך|ערך|בעריכת|translated(?: into [\w-]+)?(?: from [\w\s-]+?)? by|edited by|compiled by|written by|by)\s*:?\s*",
    re.IGNORECASE,
)
NAME_NOISE = {"ed", "eds", "editor", "editors", "hrsg", "et al", "ua", "u a"}


def _plain_mentions(residual: str, role: str, origin: str) -> list[dict[str, Any]]:
    mentions: list[dict[str, Any]] = []
    residual = re.sub(r"<[^>]+>", ",", residual)
    residual = re.sub(r"\[https?://[^\s\]]+\s*([^\]]*)\]", r"\1", residual)
    residual = re.sub(r"\([^()]*\)", " ", residual)
    for chunk in re.split(r"[,;\n/]| - | – | ו-| וְ| and | & ", residual):
        chunk_role = role
        name = _plain_name(chunk)
        prefix = _ROLE_PREFIX.match(name)
        if prefix:
            marker = prefix.group("marker").casefold()
            if marker.startswith(("מתר", "תרג", "בתר", "transl")):
                chunk_role = "translator"
            elif marker.startswith(("עור", "ערך", "בער", "edit", "compil")):
                chunk_role = "editor"
            name = _plain_name(name[prefix.end() :])
        if sum(character.isalpha() for character in name) < 3 or _normalise_name(name) in NAME_NOISE:
            continue
        if _is_marker(name, ANONYMOUS_MARKERS):
            mentions.append({"role": chunk_role, "anonymous": True, "name": name, "origin": origin})
        elif _is_marker(name, OTHERS_MARKERS) or "multiple authors" in name.casefold():
            mentions.append({"role": chunk_role, "name": f"unnamed further creators ({name})", "origin": origin})
        else:
            mentions.append({"role": chunk_role, "name": name, "origin": origin})
    return mentions


# --- Wikidata death years ------------------------------------------------------------------------------------


def death_year_upper_bound(time_value: str, precision: int) -> int | None:
    """Latest Gregorian year a Wikidata time value allows at its precision (9 year, 8 decade, 7 century, 6 millennium)."""

    match = re.match(r"^([+-])0*(\d+)-", time_value)
    if not match or match.group(1) == "-":
        return None
    year = int(match.group(2))
    if precision >= 9:
        return year
    if precision == 8:
        return year // 10 * 10 + 9
    if precision == 7:
        return year // 100 * 100 + 100
    if precision == 6:
        return year // 1000 * 1000 + 1000
    return None


def wikidata_death(entity: dict[str, Any]) -> dict[str, Any] | None:
    """The latest P570 upper bound over non-deprecated statements, or None when no dated statement exists."""

    best: dict[str, Any] | None = None
    for statement in (entity.get("claims") or {}).get("P570") or []:
        if statement.get("rank") == "deprecated":
            continue
        snak = statement.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        value = (snak.get("datavalue") or {}).get("value") or {}
        bound = death_year_upper_bound(str(value.get("time", "")), int(value.get("precision", 0)))
        if bound is None:
            continue
        if best is None or bound > best["death_year"]:
            best = {"death_year": bound, "precision": int(value.get("precision", 0)), "time": value.get("time")}
    return best


def entity_names(entity: dict[str, Any]) -> set[str]:
    names = {str(label.get("value")) for label in (entity.get("labels") or {}).values()}
    for aliases in (entity.get("aliases") or {}).values():
        names.update(str(alias.get("value")) for alias in aliases)
    return {_normalise_name(name) for name in names if name}


def entity_claim_ids(entity: dict[str, Any], prop: str) -> list[str]:
    ids: list[str] = []
    for statement in (entity.get("claims") or {}).get(prop) or []:
        value = ((statement.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if isinstance(value, dict) and value.get("id"):
            ids.append(str(value["id"]))
    return ids


# --- Building one Index record --------------------------------------------------------------------------------


def resolve_creators(
    mentions: list[dict[str, Any]],
    *,
    author_pages: dict[str, dict[str, Any]],
    wiki_ids: dict[str, str],
    commons_creators: dict[str, str],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge creator mentions into gate creators, keyed by Wikidata id where one is evidenced."""

    creators: list[dict[str, Any]] = []
    by_qid: dict[str, dict[str, Any]] = {}

    def add(role: str, name: str | None, qid: str | None, origin: str, author_page: dict[str, Any] | None = None) -> None:
        if qid and qid in by_qid:
            creator = by_qid[qid]
            creator["origins"] = sorted({*creator["origins"], origin})
            if author_page and not creator.get("author_page"):
                creator["author_page"] = author_page
            return
        if not qid:
            same = next((c for c in creators if not c["wikidata"] and c["role"] == role and _normalise_name(c["name"] or "") == _normalise_name(name or "")), None)
            if same is not None:
                same["origins"] = sorted({*same["origins"], origin})
                return
        creator = {"name": name, "role": role, "wikidata": qid, "origins": [origin], "author_page": author_page}
        creators.append(creator)
        if qid:
            by_qid[qid] = creator

    plain: list[dict[str, Any]] = []
    for mention in mentions:
        role, origin = mention["role"], mention["origin"]
        if mention.get("author_page"):
            page = author_pages.get(mention["author_page"]) or {"title": f"מחבר:{mention['author_page']}", "missing": True}
            add(role, mention["author_page"], page.get("wikidata"), origin, page)
        elif mention.get("wiki_title"):
            add(role, mention["wiki_title"].split(":", 1)[1], wiki_ids.get(mention["wiki_title"]), origin)
        elif mention.get("commons_creator"):
            qid = commons_creators.get(mention["commons_creator"])
            add(role, mention["commons_creator"], qid, origin)
        elif mention.get("wikidata"):
            entity = entities.get(mention["wikidata"]) or {}
            label = ((entity.get("labels") or {}).get("en") or (entity.get("labels") or {}).get("he") or {}).get("value")
            add(role, label or mention["wikidata"], mention["wikidata"], origin)
        else:
            plain.append(mention)

    known = [(creator, entity_names(entities.get(creator["wikidata"] or "", {})) | {_normalise_name(creator["name"] or "")}) for creator in creators]
    for mention in plain:
        normalised = _normalise_name(mention.get("name") or "")
        match = next((creator for creator, names in known if _names_match(normalised, names)), None)
        if match is not None:
            match["origins"] = sorted({*match["origins"], mention["origin"]})
            continue
        creator = {
            "name": mention.get("name"),
            "role": "anonymous" if mention.get("anonymous") else mention["role"],
            "wikidata": None,
            "origins": [mention["origin"]],
            "author_page": None,
        }
        creators.append(creator)
        known.append((creator, {normalised}))

    for creator in creators:
        _attach_death_year(creator, entities)
    return creators


def _attach_death_year(creator: dict[str, Any], entities: dict[str, dict[str, Any]]) -> None:
    sources: list[dict[str, Any]] = []
    qid = creator.get("wikidata")
    if qid and qid in entities:
        death = wikidata_death(entities[qid])
        if death:
            sources.append({"death_year": death["death_year"], "precision": death["precision"], "url": f"https://www.wikidata.org/wiki/{qid}", "kind": "wikidata_P570"})
    page = creator.get("author_page") or {}
    if isinstance(page.get("death_year"), int):
        sources.append({"death_year": page["death_year"], "precision": 9, "url": page.get("permalink"), "kind": "wikisource_author_page"})
    best = max(sources, key=lambda source: source["death_year"]) if sources else None
    creator["death_year"] = best["death_year"] if best else None
    creator["death_year_evidence_url"] = best["url"] if best else None
    creator["death_year_sources"] = sources
    if page:
        creator["author_page"] = {key: page.get(key) for key in ("title", "permalink", "wikidata", "death_year", "missing") if page.get(key) is not None}
    else:
        creator.pop("author_page", None)


def work_rights_from_creators(
    creators: list[dict[str, Any]], published_year: int | None, published_year_evidence: str | None = None
) -> dict[str, Any]:
    """The work-rights basis the evidence supports.

    Every creator dead by 1955 gives ``author_died_by_1955``. When a death year is missing (or no creator is
    recorded) and the work was published on or before 1855, decision 10's presumption gives
    ``presumed_pd_by_publication_age``. A creator who died after 1955 always stays on the death-year basis, so the
    gate rejects it as protected.
    """

    if creators and all(creator["role"] == "anonymous" for creator in creators):
        return {
            "basis": "anonymous_published_by_1955",
            "evidence": f"Every creator field carries an anonymous or unknown-author marker; published {published_year or 'year not recorded'}.",
        }
    parts = []
    for creator in creators:
        died = f"died {creator['death_year']}" if creator.get("death_year") is not None else "death year not evidenced"
        parts.append(f"{creator['name']} ({creator['role']}, {died})")
    listed = ("Creators: " + "; ".join(parts) + ".") if creators else "No creator is recorded on the Index page or the Commons file page."
    late = any(isinstance(c.get("death_year"), int) and c["death_year"] > PD_ISRAEL_DEATH_CUTOFF_YEAR for c in creators)
    complete = bool(creators) and all(isinstance(c.get("death_year"), int) for c in creators)
    if not late and not complete and isinstance(published_year, int) and published_year <= PD_ISRAEL_PRESUMPTION_PUBLICATION_CUTOFF_YEAR and published_year_evidence:
        return {
            "basis": "presumed_pd_by_publication_age",
            "evidence": f"Published {published_year} ({published_year_evidence}), on or before 1855: presumed PD in Israel (decision 10). {listed}",
        }
    return {"basis": "author_died_by_1955", "evidence": listed}


def scan_rights_from_commons(record: dict[str, Any], *, file_wikitext: str, uploader: str | None) -> dict[str, Any]:
    tokens = licence_tokens(record)
    open_licences = sorted({OPEN_LICENCE_TOKENS[token.casefold()] for token in tokens if token.casefold() in OPEN_LICENCE_TOKENS})
    pd_tokens = [token for token in tokens if token.upper().startswith("PD") and token.casefold() != "pd-us" and not token.upper().startswith("PD-US")]
    if open_licences:
        licence = open_licences[0]
        basis: str | None = "explicit_open_licence"
        evidence = f"Commons licence templates {tokens}: explicit open licence {licence}."
    else:
        # Decision 10: a flat scan of a printed PD work is a faithful reproduction; the Commons tag does not decide.
        licence = None
        basis = "faithful_reproduction_of_pd_work"
        kind = "a public-domain tag" if pd_tokens else "no non-US public-domain tag" if tokens else "no licence template"
        evidence = f"Commons licence templates {tokens} ({kind}): a flat scan of a printed work, a faithful reproduction (decision 10)."
    assert licence is None or licence in OPEN_SCAN_LICENCES
    return {"basis": basis, "licence": licence, "scan_source": scan_source_evidence(record, file_wikitext, uploader), "evidence": evidence}


def scan_source_evidence(record: dict[str, Any], file_wikitext: str, uploader: str | None) -> dict[str, Any] | None:
    """A named scanning body from the Commons source/institution fields, or None (provenance only)."""

    commons = record.get("commons_file") or {}
    fields = [("source", commons.get("source_field")), ("institution", commons.get("institution_field"))]
    for field, value in fields:
        if not value:
            continue
        folded = value.casefold()
        for needle, name in SCAN_SOURCE_NAMES:
            if needle in folded:
                return {"name": name, "url": _first_url(value), "evidence": f"Commons {field} field: {_snippet(value)}"}
    for field, value in fields:
        if value and _is_marker(value, OWN_WORK_MARKERS):
            name = f"Commons uploader {uploader} (own work)" if uploader else "Commons uploader (own work)"
            return {"name": name, "url": None, "evidence": f"Commons {field} field: {_snippet(value)}"}
    for field, value in fields:
        url = _first_url(value or "")
        if url:
            host = urllib.parse.urlparse(url).hostname or ""
            if host and not host.endswith(("wikisource.org", "wikipedia.org", "wikimedia.org")):
                return {"name": host.removeprefix("www."), "url": url, "evidence": f"Commons {field} field: {_snippet(value or '')}"}
    return None


def _first_url(text: str) -> str | None:
    match = re.search(r"https?://[^\s\]|}<]+", text)
    return match.group(0) if match else None


def _snippet(text: str, limit: int = 200) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def google_check(record: dict[str, Any], scan_source: dict[str, Any] | None, file_metadata: list[dict[str, Any]] | None, extmetadata_categories: list[str]) -> tuple[bool | None, str]:
    """Automated Google-digitization evidence (no render inspection)."""

    if scan_source and scan_source.get("name") == "Google Books":
        return True, f"Commons source names Google Books ({scan_source['evidence']})."
    commons = record.get("commons_file") or {}
    recorded = " ".join(str(v) for v in (commons.get("source_field"), commons.get("institution_field"), commons.get("provenance_text"), *(commons.get("categories") or [])) if v).casefold()
    if any(marker in recorded for marker in GOOGLE_DIGITIZATION_MARKERS):
        return True, "The Commons file record mentions Google Books or 'Digitized by Google'."
    hidden = " ".join(extmetadata_categories).casefold()
    if any(marker in hidden for marker in (*GOOGLE_DIGITIZATION_MARKERS, "google")):
        return True, "A Commons category on the file names Google."
    if file_metadata is None:
        return None, "Not checked: the file's metadata could not be read."
    blob = json.dumps(file_metadata, ensure_ascii=False).casefold()
    if "google" in blob:
        return True, "The file's embedded metadata or text layer contains 'Google'."
    text_chars = _text_layer_chars(file_metadata)
    if text_chars >= 500:
        return False, (
            f"Automated (F8b2 inventory): the file's embedded metadata and text layer ({text_chars} characters) "
            "contain no 'Google'; page renders were not inspected."
        )
    return None, "Not decided: the file has no usable text layer and its metadata does not name the digitizer; page renders were not inspected."


def _text_layer_chars(metadata: Any, *, inside_text: bool = False) -> int:
    if isinstance(metadata, str):
        return len(metadata) if inside_text else 0
    if isinstance(metadata, list):
        return sum(_text_layer_chars(item, inside_text=inside_text) for item in metadata)
    if isinstance(metadata, dict):
        name = str(metadata.get("name", "")).casefold()
        inside = inside_text or name in {"text", "xml", "data"}
        return sum(_text_layer_chars(value, inside_text=inside) for key, value in metadata.items() if key != "name")
    return 0


def with_render_check(
    digitized: bool | None, check: str, packaged: dict[str, Any] | None, *, label: str = "F8b packaged snapshot render check"
) -> tuple[bool | None, str]:
    """Combine the automated check with an operator render check recorded in the packaged F8b snapshot.

    Any evidence of Google wins; otherwise the render check, then the automated check.
    """

    rendered = (packaged or {}).get("digitized_by_google")
    if rendered is None or digitized is True:
        return digitized, check
    note = f"{label} ({(packaged or {}).get('evidence_checked_at')}): {(packaged or {}).get('digitization_check')}"
    return (True, note) if rendered is True else (False, note if digitized is None else f"{note} {check}")


def packaged_render_checks(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Google render checks recorded by hand in the packaged F8b snapshot, keyed by Commons file SHA-1."""

    root = root or package_root() / "data" / "wikisource" / "snapshot"
    _, indexes, _ = load_wikisource_snapshot(root)
    checks: dict[str, dict[str, Any]] = {}
    for record in indexes.values():
        sha1 = (record.get("commons_file") or {}).get("sha1")
        rights = record.get("scan_rights") or {}
        if sha1 and rights.get("digitized_by_google") is not None:
            checks[sha1] = {
                "digitized_by_google": rights["digitized_by_google"],
                "digitization_check": rights.get("digitization_check"),
                "evidence_checked_at": record.get("evidence_checked_at"),
            }
    return checks


# --- Recorded Index evidence (F8b3) ---------------------------------------------------------------------------

INDEX_EVIDENCE_SCHEMA_VERSION = "wikisource_index_evidence.v1"
RECORDERS = ("agent", "human")


def _recorded_problems(entry: dict[str, Any], *fields: str) -> list[str]:
    problems = [f"missing {field}" for field in ("recorded_by", "recorder", "checked_at", *fields) if entry.get(field) in (None, "", [])]
    if entry.get("recorded_by") not in RECORDERS:
        problems.append("recorded_by must be agent or human")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(entry.get("checked_at") or "")):
        problems.append("checked_at must be an ISO date")
    return problems


def index_evidence_problems(record: dict[str, Any]) -> list[str]:
    """Schema problems of one recorded-evidence record; empty when it is well formed."""

    problems = [f"missing {field}" for field in ("index_title", "commons_file_sha1") if not record.get(field)]
    for creator in record.get("creators") or []:
        problems += _recorded_problems(creator, "names", "role", "death_year", "evidence_url", "evidence_kind")
        if not isinstance(creator.get("death_year"), int):
            problems.append("death_year must be an integer year")
    if record.get("scan_source"):
        problems += _recorded_problems(record["scan_source"], "name", "evidence")
    if record.get("language"):
        problems += _recorded_problems(record["language"], "value", "evidence")
    return problems


def load_index_evidence(path: Path | None) -> dict[str, dict[str, Any]]:
    """Recorded per-Index evidence (cited creator death years, scan source, Google render check), keyed by Commons SHA-1."""

    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != INDEX_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(f"index evidence must be {INDEX_EVIDENCE_SCHEMA_VERSION}")
    evidence: dict[str, dict[str, Any]] = {}
    for record in payload.get("records") or []:
        problems = index_evidence_problems(record)
        if problems:
            raise ValueError(f"bad index evidence for {record.get('index_title')}: {', '.join(problems)}")
        evidence[record["commons_file_sha1"]] = record
    return evidence


def apply_creator_evidence(creators: list[dict[str, Any]], evidence: dict[str, Any] | None) -> None:
    """Fill a missing death year from a recorded, cited fact whose names match the creator exactly (normalised).

    A recorded fact never replaces a death year the tool found itself, and it never matches on a partial name.
    """

    for recorded in (evidence or {}).get("creators") or []:
        names = {_normalise_name(name) for name in recorded["names"]}
        for creator in creators:
            if creator.get("death_year") is not None or _normalise_name(creator.get("name") or "") not in names:
                continue
            source = {
                "death_year": recorded["death_year"],
                "precision": 9,
                "url": recorded["evidence_url"],
                "kind": f"recorded_{recorded['evidence_kind']}",
                "recorded_by": recorded["recorded_by"],
                "recorder": recorded["recorder"],
                "checked_at": recorded["checked_at"],
            }
            creator["death_year"] = recorded["death_year"]
            creator["death_year_evidence_url"] = recorded["evidence_url"]
            creator["death_year_sources"] = [*(creator.get("death_year_sources") or []), source]
            creator["death_year_recorded_by"] = recorded["recorded_by"]
            if recorded.get("wikidata") and not creator.get("wikidata"):
                creator["wikidata"] = recorded["wikidata"]


def recorded_scan_source(recorded: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": recorded["name"],
        "url": recorded.get("url"),
        "evidence": f"{recorded['evidence']} (recorded by {recorded['recorded_by']}, {recorded['checked_at']})",
    }


def apply_language_evidence(record: dict[str, Any], evidence: dict[str, Any] | None) -> None:
    """Fill an unrecorded Index language from a recorded fact; a language the wikis record is never replaced."""

    recorded = (evidence or {}).get("language")
    if not recorded or record["work"].get("language"):
        return
    record["work"]["language"] = recorded["value"]
    record["work"]["language_evidence"] = f"{recorded['evidence']} (recorded by {recorded['recorded_by']}, {recorded['checked_at']})"


def packaged_creator_mentions(root: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Creator Wikidata ids hand-recorded in the packaged F8b snapshot, keyed by Commons file SHA-1.

    They are mentions like any other: each still needs its own Wikidata death date in this run.
    """

    root = root or package_root() / "data" / "wikisource" / "snapshot"
    _, indexes, _ = load_wikisource_snapshot(root)
    mentions: dict[str, list[dict[str, Any]]] = {}
    for record in indexes.values():
        sha1 = (record.get("commons_file") or {}).get("sha1")
        for creator in (record.get("work") or {}).get("creators") or []:
            match = _WIKIDATA_ID.search(str(creator.get("death_year_evidence_url") or ""))
            if sha1 and match and "wikidata.org" in str(creator.get("death_year_evidence_url")):
                mentions.setdefault(sha1, []).append({"role": creator.get("role") or "author", "wikidata": match.group(0), "origin": "f8b_snapshot"})
    return mentions


def work_language(file_wikitext: str, index_wikitext: str) -> str | None:
    return work_language_evidence(file_wikitext, index_wikitext)[0]


def work_language_evidence(file_wikitext: str, index_wikitext: str) -> tuple[str | None, str]:
    """The recorded language (Index ``שפה`` field, else the Commons ``language`` field) and where it was read."""

    raw = template_field(index_wikitext, "שפה") or ""
    origin = "Index page field שפה"
    value = raw
    if not raw:
        raw = template_field(file_wikitext, "language") or ""
        origin = "Commons file page Language field"
        match = re.search(r"\{\{\s*language\s*\|\s*([a-z-]+)", raw, re.IGNORECASE)
        value = match.group(1) if match else raw
    value = _plain_name(value).casefold()
    language = {"עברית": "he", "hebrew": "he", "יידיש": "yi", "אנגלית": "en", "english": "en"}.get(value, value or None)
    if not raw.strip():
        return None, "Neither the Index page nor the Commons file page records a language."
    return language, f"{origin}: {_snippet(raw, 80)}"


HEBREW_LETTER_VALUES = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9, "י": 10, "כ": 20, "ך": 20, "ל": 30,
    "מ": 40, "ם": 40, "נ": 50, "ן": 50, "ס": 60, "ע": 70, "פ": 80, "ף": 80, "צ": 90, "ץ": 90, "ק": 100, "ר": 200,
    "ש": 300, "ת": 400,
}
_HEBREW_YEAR = re.compile(r"(?<![א-ת])(ה['׳]?)?([א-ת]{1,4}[\"״][א-ת])(?![א-ת])")


def hebrew_year_upper_bound(text: str) -> int | None:
    """Latest Gregorian year of a Hebrew-calendar year written in letters (``תרנ"ג``, ``ה'תקס"ח``), or None.

    Years in the minor era (without thousands) are read in the sixth millennium. A Hebrew year starts in the
    autumn, so AM year Y ends in Gregorian year Y - 3760: the upper bound used for the 1855 presumption.
    """

    match = _HEBREW_YEAR.search(_plain_name(text))
    if not match:
        return None
    letters = re.sub(r"[\"״]", "", match.group(2))
    value = sum(HEBREW_LETTER_VALUES[letter] for letter in letters)
    if value >= 1000:
        return None
    year = 5000 + value - 3760
    return year if 1450 <= year <= 2100 else None


def published_year(file_wikitext: str, index_wikitext: str) -> int | None:
    return published_year_evidence(file_wikitext, index_wikitext)[0]


def published_year_evidence(file_wikitext: str, index_wikitext: str) -> tuple[int | None, str | None]:
    """Publication year and where it was read: the latest of the Commons date and the Index ``שנה`` (an upper bound).

    The Index year may be Hebrew-calendar letters; it is converted to its latest Gregorian year.
    """

    found: list[tuple[int, str]] = []
    commons = template_field(file_wikitext, "date", "publication date")
    match = _YEAR.match(_plain_name(commons or ""))
    if match:
        found.append((int(match.group(1)), f"Commons date field: {_snippet(commons or '', 60)}"))
    index_year = template_field(index_wikitext, "שנה")
    if index_year:
        match = _YEAR.match(_plain_name(index_year))
        hebrew = None if match else hebrew_year_upper_bound(index_year)
        if match:
            found.append((int(match.group(1)), f"Index page field שנה: {_snippet(index_year, 60)}"))
        elif hebrew:
            found.append((hebrew, f"Index page field שנה: {_snippet(index_year, 60)} (Hebrew year, Gregorian upper bound {hebrew})"))
    if not found:
        return None, None
    year = max(value for value, _ in found)
    return year, "; ".join(note for _, note in found)


# --- Inventory run (operator path) --------------------------------------------------------------------------


def index_key_for(page_id: int) -> str:
    return f"ws_index_{page_id}"


def run_inventory(
    fetch: FetchJson,
    *,
    checked_at: str,
    snapshot_root: Path,
    with_pages: bool = True,
    page_checks: dict[str, dict[str, Any]] | None = None,
    index_evidence: dict[str, dict[str, Any]] | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Enumerate, gather evidence, gate. Returns the full operator inventory (no page text inside)."""

    indexes = [page for block in _query_all(fetch, WS_API, {"list": "allpages", "apnamespace": INDEX_NAMESPACE, "aplimit": "max"}) for page in block.get("allpages", [])]
    log(f"{len(indexes)} Index pages")
    quality: dict[str, int] = {}
    page_ids: dict[str, int] = {}
    for block in _query_all(fetch, WS_API, {"generator": "allpages", "gapnamespace": PAGE_NAMESPACE, "gaplimit": "max", "prop": "proofread"}):
        for page in block.get("pages", []):
            if "proofread" in page:
                quality[page["title"]] = int(page["proofread"]["quality"])
                page_ids[page["title"]] = int(page["pageid"])
    log(f"{len(quality)} Page pages with a quality level")

    index_pages: dict[str, dict[str, Any]] = {}
    for chunk in _chunks([index["title"] for index in indexes]):
        payload = fetch(WS_API, {"action": "query", "titles": "|".join(chunk), "prop": "revisions", "rvprop": "ids|content", "rvslots": "main"})
        for page in payload["query"]["pages"]:
            index_pages[page["title"]] = page

    members: dict[str, list[str]] = {}
    for index in indexes:
        titles: list[str] = []
        for block in _query_all(fetch, WS_API, {"list": "proofreadpagesinindex", "prppiititle": index["title"], "prppiiprop": "ids|title"}):
            titles.extend(entry["title"] for entry in block.get("proofreadpagesinindex", []))
        members[index["title"]] = list(dict.fromkeys(titles))

    file_titles = {index["title"]: index["title"].split(":", 1)[1] for index in indexes}
    file_pages = _file_pages(fetch, sorted(set(file_titles.values())))
    index_wikitexts = {title: _content(page) for title, page in index_pages.items()}

    packaged = packaged_creator_mentions()
    mentions_by_index: dict[str, list[dict[str, Any]]] = {}
    for index in indexes:
        file_page = file_pages.get(file_titles[index["title"]]) or {}
        mentions_by_index[index["title"]] = (
            index_creator_mentions(index_wikitexts.get(index["title"], ""))
            + commons_creator_mentions(file_page.get("wikitext", ""))
            + packaged.get(str((file_page.get("imageinfo") or {}).get("sha1")), [])
        )
    all_mentions = [mention for mentions in mentions_by_index.values() for mention in mentions]
    author_pages = _author_pages(fetch, sorted({m["author_page"] for m in all_mentions if m.get("author_page")}))
    wiki_ids = _wiki_ids(fetch, sorted({m["wiki_title"] for m in all_mentions if m.get("wiki_title")}))
    commons_creators = _commons_creators(fetch, sorted({m["commons_creator"] for m in all_mentions if m.get("commons_creator")}))
    work_items = {title: qid for title, page in file_pages.items() if (qid := page.get("work_wikidata"))}
    qids = {page.get("wikidata") for page in author_pages.values()} | set(wiki_ids.values()) | set(commons_creators.values())
    qids |= {m["wikidata"] for m in all_mentions if m.get("wikidata")} | set(work_items.values())
    entities = _entities(fetch, sorted(q for q in qids if q))
    extra = {q for qid in work_items.values() for prop in WIKIDATA_CREATOR_PROPERTIES for q in entity_claim_ids(entities.get(qid, {}), prop)}
    entities.update(_entities(fetch, sorted(extra - set(entities))))

    render_checks = packaged_render_checks()
    records: list[dict[str, Any]] = []
    for index in sorted(indexes, key=lambda entry: entry["title"]):
        title = index["title"]
        file_title = file_titles[title]
        file_page = file_pages.get(file_title) or {}
        mentions = list(mentions_by_index[title])
        work_qid = work_items.get(file_title)
        for prop, role in WIKIDATA_CREATOR_PROPERTIES.items():
            for qid in entity_claim_ids(entities.get(work_qid or "", {}), prop):
                mentions.append({"role": role, "wikidata": qid, "origin": f"wikidata:{work_qid}:{prop}"})
        record = build_index_record(
            index_title=title,
            index_page=index_pages.get(title) or {},
            file_page=file_page,
            mentions=mentions,
            author_pages=author_pages,
            wiki_ids=wiki_ids,
            commons_creators=commons_creators,
            entities=entities,
            checked_at=checked_at,
            render_checks=render_checks,
            index_evidence=index_evidence,
        )
        member_titles = members.get(title) or []
        record["pages"] = {
            "in_index": len(member_titles),
            "quality_counts": dict(sorted(Counter(str(quality[t]) for t in member_titles if t in quality).items())),
        }
        record["gate"] = {"reasons": index_exclusion_reasons(record)}
        record["gate"]["admitted"] = not record["gate"]["reasons"]
        record["_member_titles"] = [t for t in member_titles if quality.get(t) in ADMITTED_QUALITY_LEVELS]
        records.append(record)
    log(f"Index gate: {sum(r['gate']['admitted'] for r in records)} admitted of {len(records)}")

    page_results: list[dict[str, Any]] = []
    if with_pages:
        by_key = {record["index_key"]: record for record in records}
        for record in records:
            if not record["gate"]["admitted"]:
                continue
            for page_title in record["_member_titles"]:
                page = capture_page_record(fetch, page_title, record, snapshot_root)
                check = apply_page_check(page, record, (page_checks or {}).get(page_title))
                reasons = page_exclusion_reasons(page, by_key, snapshot_root)
                attestation = page_attestation(page)
                page_results.append(
                    {
                        "index_key": record["index_key"],
                        "page_title": page_title,
                        "page_id": page["page_id"],
                        "revision_id": page["revision_id"],
                        "quality": page["quality"],
                        "reasons": reasons,
                        "adjudication_eligible": attestation["adjudication_eligible"],
                        "adjudication_ineligible_reason": attestation["adjudication_ineligible_reason"],
                        "unsupported_markup": unsupported_markup(page, snapshot_root) if "wikitext_unsupported_markup" in reasons else None,
                        **page_text_provenance(page, snapshot_root),
                        "proofreader": (attestation["proofreader"] or {}).get("user"),
                        "validator": (attestation["validator"] or {}).get("user"),
                        "transcription_coverage": page.get("transcription_coverage"),
                        "needs_crop": page_needs_crop(page),
                        "render_check": check,
                    }
                )
        log(f"{len(page_results)} pages of admitted Indexes checked")
    for record in records:
        record.pop("_member_titles", None)
    return {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "checked_at": checked_at,
        "user_agent": USER_AGENT,
        "site": WS_SITE,
        "indexes": records,
        "pages": page_results,
    }


def page_text_provenance(page: dict[str, Any], root: Path) -> dict[str, Any]:
    """Size spans and converter features of the page body (provenance only); None when it does not convert."""

    try:
        conversion = convert_wikitext((root / page["wikitext_path"]).read_text(encoding="utf-8"))
    except UnsupportedWikitextError:
        return {"size_spans": None, "text_features": None}
    return {"size_spans": conversion.size_spans, "text_features": conversion.features}


# --- Page render checks (F8b3) --------------------------------------------------------------------------------


def page_check_problems(check: dict[str, Any]) -> list[str]:
    """Schema problems of one render-check record; empty when the record is well formed."""

    problems: list[str] = []
    for key in ("page_title", "revision_id", "commons_file_sha1", "scan_page", "checked_by", "checker", "checked_at", "method"):
        if check.get(key) in (None, ""):
            problems.append(f"missing {key}")
    if check.get("checked_by") not in PAGE_CHECKERS:
        problems.append("checked_by must be agent or human")
    coverage = check.get("transcription_coverage")
    if coverage not in TRANSCRIPTION_COVERAGE_VALUES:
        problems.append("transcription_coverage must be full_page or partial_page")
    if coverage == TRANSCRIPTION_COVERAGE_PARTIAL and not str(check.get("missing") or "").strip():
        problems.append("a partial_page check must say what is missing")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(check.get("checked_at") or "")):
        problems.append("checked_at must be an ISO date")
    return problems


def select_page_checks(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The check that applies to each page title: a human check overrides an agent check; otherwise the latest."""

    if payload.get("schema_version") != PAGE_CHECKS_SCHEMA_VERSION:
        raise ValueError(f"page checks must be {PAGE_CHECKS_SCHEMA_VERSION}")
    selected: dict[str, dict[str, Any]] = {}
    methods = payload.get("methods") or {}
    for check in payload.get("checks") or []:
        check = {**check, "method": methods.get(check.get("method"), check.get("method"))}  # a method id names shared text
        problems = page_check_problems(check)
        if problems:
            raise ValueError(f"bad page check for {check.get('page_title')}: {', '.join(problems)}")
        current = selected.get(check["page_title"])
        rank = (check["checked_by"] == "human", check["checked_at"])
        if current is None or rank >= (current["checked_by"] == "human", current["checked_at"]):
            selected[check["page_title"]] = check
    return selected


def load_page_checks(path: Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    return select_page_checks(json.loads(path.read_text(encoding="utf-8")))


def apply_page_check(page: dict[str, Any], index: dict[str, Any], check: dict[str, Any] | None) -> dict[str, Any] | None:
    """Set the page's transcription coverage from a render check pinned to this revision and scan.

    A check made on another page revision or another Commons file is stale and is not applied, so the page
    stays ``transcription_coverage_unrecorded``. Returns the applied check's provenance, or None.
    """

    if check is None:
        return None
    sha1 = (index.get("commons_file") or {}).get("sha1")
    if check["revision_id"] != page.get("revision_id") or check["commons_file_sha1"] != sha1:
        return {"applied": False, "reason": "stale_render_check", "checked_by": check["checked_by"], "checked_at": check["checked_at"]}
    provenance = {
        "applied": True,
        "checked_by": check["checked_by"],
        "checker": check["checker"],
        "checked_at": check["checked_at"],
        "method": check["method"],
        "missing": check.get("missing"),
    }
    page["transcription_coverage"] = check["transcription_coverage"]
    page["transcription_coverage_check"] = provenance
    return provenance


def unsupported_markup(page: dict[str, Any], root: Path) -> str | None:
    """The converter's message for a page rejected with ``wikitext_unsupported_markup``."""

    try:
        wikitext_to_plain_text((root / page["wikitext_path"]).read_text(encoding="utf-8"))
    except UnsupportedWikitextError as exc:
        return str(exc)
    return None


def build_index_record(
    *,
    index_title: str,
    index_page: dict[str, Any],
    file_page: dict[str, Any],
    mentions: list[dict[str, Any]],
    author_pages: dict[str, dict[str, Any]],
    wiki_ids: dict[str, str],
    commons_creators: dict[str, str],
    entities: dict[str, dict[str, Any]],
    checked_at: str,
    render_checks: dict[str, dict[str, Any]] | None = None,
    index_evidence: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One F8b-shaped Index record (fields ``index_exclusion_reasons`` reads), plus inventory extras."""

    index_wikitext = _content(index_page)
    file_wikitext = file_page.get("wikitext", "")
    info = file_page.get("imageinfo") or {}
    revision = file_page.get("revision") or {}
    year, year_evidence = published_year_evidence(file_wikitext, index_wikitext)
    language, language_evidence = work_language_evidence(file_wikitext, index_wikitext)
    creators = resolve_creators(mentions, author_pages=author_pages, wiki_ids=wiki_ids, commons_creators=commons_creators, entities=entities)
    title_field = template_field(index_wikitext, "כותרת")
    record: dict[str, Any] = {
        "index_key": index_key_for(int(index_page.get("pageid") or 0)),
        "index_title": index_title,
        "index_page_id": index_page.get("pageid"),
        "index_revision_id": ((index_page.get("revisions") or [{}])[0]).get("revid"),
        "commons_file": {
            "title": f"File:{file_page.get('file_title') or index_title.split(':', 1)[1]}",
            "repository": file_page.get("repository"),
            "description_url": info.get("descriptionurl"),
            "file_page_revision_id": revision.get("revid"),
            "file_page_revision_sha1": revision.get("sha1"),
            "sha1": info.get("sha1"),
            "size": info.get("size"),
            "mime": info.get("mime"),
            "page_count": info.get("pagecount"),
            "uploaded_at": info.get("timestamp"),
            "uploader": info.get("user"),
            "source_field": template_field(file_wikitext, "source"),
            "institution_field": template_field(file_wikitext, "institution"),
            "provenance_text": provenance_text(file_wikitext) if file_wikitext else None,
            "licence_templates": licence_templates(file_wikitext) if file_wikitext else [],
            "categories": wikitext_categories(file_wikitext),
            "missing": bool(file_page.get("missing")) or not file_wikitext,
        },
        "work": {
            "title": _plain_name(title_field or "") or index_title.split(":", 1)[1],
            "published_year": year,
            "published_year_evidence": year_evidence,
            "place": _plain_name(template_field(file_wikitext, "city") or template_field(index_wikitext, "Address") or "") or None,
            "creators": creators,
            "work_wikidata": file_page.get("work_wikidata"),
            "language": language,
            "language_evidence": language_evidence,
        },
        "evidence_checked_at": checked_at,
    }
    evidence = (index_evidence or {}).get(str(info.get("sha1")))
    apply_creator_evidence(creators, evidence)
    apply_language_evidence(record, evidence)
    record["work_rights"] = work_rights_from_creators(creators, year, year_evidence)
    scan = scan_rights_from_commons(record, file_wikitext=file_wikitext, uploader=info.get("user"))
    if scan["scan_source"] is None and evidence and evidence.get("scan_source"):
        scan["scan_source"] = recorded_scan_source(evidence["scan_source"])
    digitized, check = google_check(record, scan["scan_source"], file_page.get("metadata"), file_page.get("extmetadata_categories") or [])
    digitized, check = with_render_check(digitized, check, (render_checks or {}).get(str(info.get("sha1"))))
    scan["digitized_by_google"] = digitized
    scan["digitization_check"] = check
    record["scan_rights"] = scan
    record["scan_source_origin"] = scan_source_origin(record)
    return record


def _content(page: dict[str, Any]) -> str:
    revisions = page.get("revisions") or []
    return str(((revisions[0].get("slots") or {}).get("main") or {}).get("content", "")) if revisions else ""


def _file_pages(fetch: FetchJson, file_titles: list[str]) -> dict[str, dict[str, Any]]:  # pragma: no cover - network
    """File description pages (Commons or local) with imageinfo, wikitext, hidden categories and metadata."""

    result: dict[str, dict[str, Any]] = {}
    local_repo: dict[str, str] = {}
    for chunk in _chunks([f"File:{title}" for title in file_titles]):
        payload = fetch(WS_API, {"action": "query", "titles": "|".join(chunk), "prop": "imageinfo", "iiprop": "sha1"})
        normalized = {entry["to"]: entry["from"] for entry in payload["query"].get("normalized", [])}
        for page in payload["query"]["pages"]:
            original = normalized.get(page["title"], page["title"])
            local_repo[original.split(":", 1)[1]] = page.get("imagerepository") or ("local" if not page.get("missing") else "")
    for repository, api in (("shared", COMMONS_API), ("local", WS_API)):
        titles = [title for title in file_titles if local_repo.get(title) == repository]
        for chunk in _chunks([f"File:{title}" for title in titles]):
            payload = fetch(api, {
                "action": "query", "titles": "|".join(chunk), "prop": "imageinfo|revisions",
                "iiprop": "sha1|size|mime|url|timestamp|user|extmetadata", "iiextmetadatafilter": "Categories",
                "rvprop": "ids|sha1|content", "rvslots": "main",
            })
            normalized = {entry["to"]: entry["from"] for entry in payload["query"].get("normalized", [])}
            for page in payload["query"]["pages"]:
                original = normalized.get(page["title"], page["title"]).split(":", 1)[1]
                info = (page.get("imageinfo") or [{}])[0]
                revision = (page.get("revisions") or [{}])[0]
                wikitext = str(((revision.get("slots") or {}).get("main") or {}).get("content", ""))
                categories = str(((info.get("extmetadata") or {}).get("Categories") or {}).get("value", ""))
                work_qid = template_field(wikitext, "wikidata")
                result[original] = {
                    "file_title": original,
                    "repository": "commons" if repository == "shared" else "he.wikisource",
                    "imageinfo": {key: value for key, value in info.items() if key != "extmetadata"},
                    "revision": {"revid": revision.get("revid"), "sha1": revision.get("sha1")},
                    "wikitext": wikitext,
                    "extmetadata_categories": [c for c in categories.split("|") if c],
                    "work_wikidata": (_WIKIDATA_ID.search(work_qid).group(0) if work_qid and _WIKIDATA_ID.search(work_qid) else None),
                    "missing": bool(page.get("missing")),
                }
        for title in titles:
            entry = result.get(title)
            if not entry or entry["missing"]:
                continue
            payload = fetch(api, {"action": "query", "titles": f"File:{title}", "prop": "imageinfo", "iiprop": "metadata"})
            info = (payload["query"]["pages"][0].get("imageinfo") or [{}])[0]
            entry["metadata"] = info.get("metadata")
    for title in file_titles:
        result.setdefault(title, {"file_title": title, "missing": True})
    return result


def _author_pages(fetch: FetchJson, names: list[str]) -> dict[str, dict[str, Any]]:  # pragma: no cover - network
    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(names):
        payload = fetch(WS_API, {
            "action": "query", "titles": "|".join(f"מחבר:{name}" for name in chunk), "redirects": "1",
            "prop": "pageprops|revisions", "ppprop": "wikibase_item", "rvprop": "ids|content", "rvslots": "main",
        })
        query = payload["query"]
        forward: dict[str, str] = {}
        for entry in query.get("normalized", []) + query.get("redirects", []):
            forward[entry["from"]] = entry["to"]
        pages = {page["title"]: page for page in query["pages"]}
        for name in chunk:
            title = f"מחבר:{name}"
            while title in forward:
                title = forward[title]
            page = pages.get(title) or {}
            content = _content(page)
            year_field = template_field(content, "שנת פטירה לועזית") or ""
            match = re.match(r"^\s*(\d{3,4})\s*$", re.sub(r"<!--.*?-->", "", year_field))
            revid = ((page.get("revisions") or [{}])[0]).get("revid")
            result[name] = {
                "title": title,
                "missing": bool(page.get("missing")) or not page,
                "wikidata": (page.get("pageprops") or {}).get("wikibase_item"),
                "death_year": int(match.group(1)) if match else None,
                "permalink": f"{WS_SITE}/w/index.php?oldid={revid}" if revid else None,
            }
    return result


def _wiki_ids(fetch: FetchJson, keys: list[str]) -> dict[str, str]:  # pragma: no cover - network
    """Wikidata ids for ``site:title`` Wikipedia links, read from the article's ``wikibase_item`` (redirects followed)."""

    result: dict[str, str] = {}
    by_site: dict[str, list[str]] = {}
    for key in keys:
        site, title = key.split(":", 1)
        by_site.setdefault(site, []).append(title)
    for site, titles in by_site.items():
        api = f"https://{site.removesuffix('wiki')}.wikipedia.org/w/api.php"
        for chunk in _chunks(titles):
            payload = fetch(api, {"action": "query", "titles": "|".join(chunk), "redirects": "1", "prop": "pageprops", "ppprop": "wikibase_item"})
            query = payload.get("query") or {}
            forward = {entry["from"]: entry["to"] for entry in query.get("normalized", []) + query.get("redirects", [])}
            pages = {page["title"]: page for page in query.get("pages", [])}
            for title in chunk:
                target, seen = title, set()
                while target in forward and target not in seen:
                    seen.add(target)
                    target = forward[target]
                qid = ((pages.get(target) or {}).get("pageprops") or {}).get("wikibase_item")
                if qid:
                    result[f"{site}:{title}"] = qid
    return result


def _commons_creators(fetch: FetchJson, names: list[str]) -> dict[str, str]:  # pragma: no cover - network
    result: dict[str, str] = {}
    for chunk in _chunks(names):
        payload = fetch(COMMONS_API, {"action": "query", "titles": "|".join(f"Creator:{name}" for name in chunk), "redirects": "1", "prop": "revisions", "rvprop": "content", "rvslots": "main"})
        query = payload["query"]
        forward = {entry["from"]: entry["to"] for entry in query.get("normalized", []) + query.get("redirects", [])}
        pages = {page["title"]: page for page in query["pages"]}
        for name in chunk:
            title = f"Creator:{name}"
            while title in forward:
                title = forward[title]
            value = template_field(_content(pages.get(title) or {}), "wikidata") or ""
            match = _WIKIDATA_ID.search(value)
            if match:
                result[name] = match.group(0)
    return result


def _entities(fetch: FetchJson, qids: list[str]) -> dict[str, dict[str, Any]]:  # pragma: no cover - network
    result: dict[str, dict[str, Any]] = {}
    for chunk in _chunks(qids):
        payload = fetch(WIKIDATA_API, {"action": "wbgetentities", "ids": "|".join(chunk), "props": "claims|labels|aliases", "languages": "en|he"})
        for qid, entity in (payload.get("entities") or {}).items():
            claims = entity.get("claims") or {}
            result[qid] = {
                "labels": entity.get("labels") or {},
                "aliases": entity.get("aliases") or {},
                "claims": {prop: claims[prop] for prop in ("P570", "P31", *WIKIDATA_CREATOR_PROPERTIES) if prop in claims},
            }
    return result


def capture_page_record(fetch: FetchJson, title: str, index: dict[str, Any], root: Path) -> dict[str, Any]:  # pragma: no cover - network
    """Pin one Page into the operator snapshot root in the F8b page-record shape (no image)."""

    revisions: list[dict[str, Any]] = []
    page_meta: dict[str, Any] = {}
    for block in _query_all(fetch, WS_API, {"titles": title, "prop": "revisions|info", "rvprop": "ids|user|userid|timestamp|content|sha1", "rvslots": "main", "rvlimit": "50", "rvdir": "newer"}):
        page = block["pages"][0]
        page_meta = page
        revisions.extend(page.get("revisions") or [])
    users = sorted({revision.get("user", "") for revision in revisions if revision.get("user")})
    groups: dict[str, list[str]] = {}
    for chunk in _chunks(users):
        payload = fetch(WS_API, {"action": "query", "list": "users", "ususers": "|".join(chunk), "usprop": "groups"})
        groups.update({user["name"]: user.get("groups", []) for user in payload["query"]["users"]})
    pinned = revisions[-1]
    wikitext = str(pinned["slots"]["main"].get("content", ""))
    history: list[dict[str, Any]] = []
    previous = None
    for revision in revisions:
        content = str(revision["slots"]["main"].get("content", ""))
        level = pagequality_level(content)
        attribute = re.search(r"<pagequality\b[^>]*\buser\s*=\s*\"([^\"]*)\"", content)
        if level != previous:
            history.append({
                "level": level,
                "revision_id": revision["revid"],
                "timestamp": revision["timestamp"],
                "user": revision.get("user", ""),
                "user_id": revision.get("userid", 0),
                "user_groups": sorted(g for g in groups.get(revision.get("user", ""), []) if g not in {"*", "user", "autoconfirmed"}),
                "pagequality_user_attribute": attribute.group(1) if attribute else None,
            })
            previous = level
    quality_set = history[-1] if history else {"revision_id": pinned["revid"]}
    texts: dict[int, str | None] = {}
    for revision in revisions:
        try:
            texts[revision["revid"]] = wikitext_to_plain_text(str(revision["slots"]["main"].get("content", "")))
        except UnsupportedWikitextError:
            texts[revision["revid"]] = None
    later = []
    previous_text = texts.get(quality_set["revision_id"])
    for revision in revisions:
        if revision["revid"] <= quality_set["revision_id"]:
            continue
        later.append({
            "revision_id": revision["revid"],
            "timestamp": revision["timestamp"],
            "user": revision.get("user", ""),
            "user_id": revision.get("userid", 0),
            "text_changed": texts[revision["revid"]] != previous_text,
        })
        previous_text = texts[revision["revid"]]
    number = title.rsplit("/", 1)[1] if "/" in title else "0"
    slug = f"{index['index_key']}__p{int(number):04d}" if number.isdigit() else f"{index['index_key']}__{hashlib.sha256(title.encode()).hexdigest()[:10]}"
    text = texts[pinned["revid"]]
    (root / "wikitext").mkdir(parents=True, exist_ok=True)
    (root / "text").mkdir(parents=True, exist_ok=True)
    (root / "wikitext" / f"{slug}.wikitext.txt").write_text(wikitext, encoding="utf-8")
    if text is not None:
        (root / "text" / f"{slug}.txt").write_text(text + "\n", encoding="utf-8")
    quality_set_text = texts.get(quality_set["revision_id"])
    return {
        "source_item_id": slug,
        "transcription_coverage": None,
        "index_key": index["index_key"],
        "page_title": title,
        "page_number": int(number) if number.isdigit() else None,
        "page_id": page_meta.get("pageid"),
        "revision_id": pinned["revid"],
        "revision_timestamp": pinned["timestamp"],
        "revision_sha1": pinned.get("sha1"),
        "quality": pagequality_level(wikitext),
        "quality_history": history,
        "edits_after_quality_set": later,
        "quality_set_text_sha256": hashlib.sha256(quality_set_text.encode()).hexdigest() if quality_set_text is not None else None,
        "wikitext_path": f"wikitext/{slug}.wikitext.txt",
        "wikitext_sha256": hashlib.sha256(wikitext.encode()).hexdigest(),
        "text_path": f"text/{slug}.txt",
        "text_sha256": hashlib.sha256(text.encode()).hexdigest() if text is not None else None,
    }


# --- Committed compact record and summary (network-free) ----------------------------------------------------


COMPACT_COMMONS_FIELDS = (
    "title", "repository", "file_page_revision_id", "sha1", "page_count", "source_field", "institution_field",
    "provenance_text", "licence_templates", "categories",
)


def compact_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    """The committed per-Index view: ids, rights evidence, gate results and page counts. No page text."""

    pages_by_index: dict[str, list[dict[str, Any]]] = {}
    for page in inventory.get("pages") or []:
        pages_by_index.setdefault(page["index_key"], []).append(page)
    records = []
    for record in sorted(inventory["indexes"], key=lambda entry: entry["index_title"]):
        commons = record["commons_file"]
        page_entries = pages_by_index.get(record["index_key"], [])
        records.append(
            {
                "index_key": record["index_key"],
                "index_title": record["index_title"],
                "index_page_id": record["index_page_id"],
                "index_revision_id": record["index_revision_id"],
                "commons_file": {key: commons.get(key) for key in COMPACT_COMMONS_FIELDS},
                "work": {
                    "title": record["work"]["title"],
                    "published_year": record["work"]["published_year"],
                    "published_year_evidence": record["work"].get("published_year_evidence"),
                    "language": record["work"].get("language"),
                    "language_evidence": record["work"].get("language_evidence"),
                    "creators": [
                        {key: creator.get(key) for key in ("name", "role", "wikidata", "death_year", "death_year_evidence_url")}
                        for creator in record["work"]["creators"]
                    ],
                },
                "work_rights": record["work_rights"],
                "scan_rights": record["scan_rights"],
                "scan_source_origin": record["scan_source_origin"],
                "pages": record["pages"],
                "gate": {"admitted": record["gate"]["admitted"], "reasons": record["gate"]["reasons"]},
                "page_gate": _page_gate_counts(page_entries) if record["gate"]["admitted"] else None,
            }
        )
    return {
        "schema_version": "wikisource_index_inventory_summary.v1",
        "checked_at": inventory["checked_at"],
        "site": inventory["site"],
        "gate": "hocrgen.fetchers.wikisource.index_exclusion_reasons / page_exclusion_reasons (F8b; F8b3: decisions 9-12 and the language gate)",
        "indexes": records,
    }


def _page_gate_counts(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Page-gate counts for one admitted Index.

    ``eligible`` pages pass every gate with coverage recorded: ``full_page`` pages pair as they are, ``needs_crop``
    (``partial_page``) pages pair after the F8b4 crop (decision 12). ``pending_coverage_only`` pages fail only
    because no render check records their coverage. ``reference_eligible_q4`` counts adjudication-eligible
    quality-4 pages passing every gate but coverage; ``reference_eligible_now_q4`` those eligible as full pages.
    """

    reasons: Counter[str] = Counter()
    markup: Counter[str] = Counter()
    pending = {"3": 0, "4": 0}
    eligible = {"3": 0, "4": 0}
    needs_crop = {"3": 0, "4": 0}
    converts = {"3": 0, "4": 0}
    reference = reference_now = 0
    checks = {"checked": 0, "full_page": 0, "partial_page": 0, "stale": 0}
    for page in pages:
        check = page.get("render_check")
        if check and check.get("applied"):
            checks["checked"] += 1
            checks[str(page.get("transcription_coverage"))] += 1
        elif check:
            checks["stale"] += 1
        if "wikitext_unsupported_markup" not in page["reasons"]:
            converts[str(page["quality"])] += 1
        remaining = [reason for reason in page["reasons"] if reason != COVERAGE_PENDING_REASON]
        if remaining:
            reasons[remaining[0]] += 1
            if page.get("unsupported_markup"):
                markup[str(page["unsupported_markup"])] += 1
            continue
        crop = bool(page.get("needs_crop"))
        group = pending if page["reasons"] else needs_crop if crop else eligible
        group[str(page["quality"])] += 1
        if page["quality"] == 4 and page["adjudication_eligible"]:
            reference += 1
            reference_now += int(not page["reasons"] and not crop)
    return {
        "checked": len(pages),
        "converts": converts,
        "eligible": eligible,
        "needs_crop": needs_crop,
        "pending_coverage_only": pending,
        "reference_eligible_q4": reference,
        "reference_eligible_now_q4": reference_now,
        "render_checks": checks,
        "rejected_by_first_reason": dict(sorted(reasons.items())),
        "unsupported_markup": dict(sorted(markup.items())),
    }


def _q(record: dict[str, Any], level: str) -> int:
    return int((record["pages"].get("quality_counts") or {}).get(level, 0))


def _missing_evidence(record: dict[str, Any]) -> str:
    parts = []
    reasons = set(record["gate"]["reasons"])
    if "creators_missing" in reasons:
        parts.append("no creator recorded")
    missing = [c["name"] for c in record["work"]["creators"] if c.get("death_year") is None]
    if missing and {"creator_death_year_missing", "creators_missing"} & reasons:
        year = record["work"].get("published_year")
        parts.append("death year for " + ", ".join(str(name) for name in missing) + (f" (published {year}, after 1855)" if year else " (no publication year)"))
    if "index_language_unrecorded" in reasons:
        parts.append("the Index language")
    for reason in ("commons_file_unpinned", "publication_year_missing", "work_rights_basis_unsupported", "scan_rights_basis_unsupported"):
        if reason in reasons:
            parts.append(reason)
    return "; ".join(parts)


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


# The F8b2 run's funnel (2026-11-06), before the F8b3 converter and decisions 9-12; shown for comparison.
F8B2_BASELINE = {
    "indexes_admitted": 29,
    "pages_admitted": {"3": 624, "4": 27},
    "pages_converting": {"3": 231, "4": 12},
    "pages_passing_but_coverage": {"3": 231, "4": 12},
    "reference_eligible_q4": 4,
    "pages_full_page": {"3": 0, "4": 0},
    "pages_needs_crop": {"3": 0, "4": 0},
}


def render_summary(compact: dict[str, Any], *, top: int = 15, resolve_top: int = 15) -> str:
    """Deterministic markdown summary of the compact inventory."""

    records = compact["indexes"]
    q3 = sum(_q(r, "3") for r in records)
    q4 = sum(_q(r, "4") for r in records)
    admitted = [r for r in records if r["gate"]["admitted"]]
    first_reason: Counter[str] = Counter()
    any_reason: Counter[str] = Counter()
    pages_first: Counter[str] = Counter()
    pages_any: Counter[str] = Counter()
    for record in records:
        if record["gate"]["reasons"]:
            first_reason[record["gate"]["reasons"][0]] += 1
            pages_first[record["gate"]["reasons"][0]] += _q(record, "3") + _q(record, "4")
        for reason in record["gate"]["reasons"]:
            any_reason[reason] += 1
            pages_any[reason] += _q(record, "3") + _q(record, "4")
    page_reasons: Counter[str] = Counter()
    markup: Counter[str] = Counter()
    totals: Counter[str] = Counter()
    for record in admitted:
        gate = record.get("page_gate") or {}
        totals["checked"] += int(gate.get("checked", 0))
        for level in ("3", "4"):
            for key in ("converts", "pending_coverage_only", "eligible", "needs_crop"):
                totals[f"{key}{level}"] += int((gate.get(key) or {}).get(level, 0))
        totals["reference"] += int(gate.get("reference_eligible_q4", 0))
        totals["reference_now"] += int(gate.get("reference_eligible_now_q4", 0))
        for key, value in (gate.get("render_checks") or {}).items():
            totals[f"render_{key}"] += int(value)
        page_reasons.update(gate.get("rejected_by_first_reason") or {})
        markup.update(gate.get("unsupported_markup") or {})
    passing3 = totals["pending_coverage_only3"] + totals["eligible3"] + totals["needs_crop3"]
    passing4 = totals["pending_coverage_only4"] + totals["eligible4"] + totals["needs_crop4"]
    base = F8B2_BASELINE

    def _pair(values: dict[str, int]) -> str:
        return f"{values['3']} / {values['4']}"

    def _both(record: dict[str, Any], key: str) -> str:
        values = (record.get("page_gate") or {}).get(key) or {}
        return f"{values.get('3', 0)} / {values.get('4', 0)}"

    lines = [
        "# Hebrew Wikisource Index inventory (F8b2, F8b3)",
        "",
        f"Generated by `hocrgen.tools.wikisource_inventory` from evidence checked on {compact['checked_at']}; do not edit by hand.",
        "The per-Index data is in [`wikisource_index_inventory.json`](./wikisource_index_inventory.json). The evidence the run adds to",
        "what the wikis record is in [`wikisource_index_evidence.json`](./wikisource_index_evidence.json), and the per-page render",
        "checks in [`wikisource_page_checks.json`](./wikisource_page_checks.json). Every Index went through `index_exclusion_reasons`",
        "(maintainer decisions 9 and 10 and the F8b3 language gate); pages of admitted Indexes went through `page_exclusion_reasons`",
        "and `page_attestation`. The full pool, its page text and its raw API responses stay operator-only.",
        "",
        "## Funnel",
        "",
        "Quality-3 / quality-4 pages at each stage. The F8b2 column is the run before F8b3 (same date, old gates and converter).",
        "",
        "| Stage | F8b2 | F8b3 |",
        "| --- | ---: | ---: |",
        f"| Indexes; their quality-3 / quality-4 pages | {len(records)}; {q3} / {q4} | {len(records)}; {q3} / {q4} |",
        f"| Indexes admitted by the Index gate | {base['indexes_admitted']} | {len(admitted)} |",
        f"| Pages in admitted Indexes | {_pair(base['pages_admitted'])} | {sum(_q(r, '3') for r in admitted)} / {sum(_q(r, '4') for r in admitted)} |",
        f"| Pages the converter renders (`wikisource_plain_text`) | {_pair(base['pages_converting'])} | {totals['converts3']} / {totals['converts4']} |",
        f"| Pages passing every other gate (attestation, checksums) | {_pair(base['pages_passing_but_coverage'])} | {passing3} / {passing4} |",
        f"| Coverage checked `full_page`: eligible as they are | {_pair(base['pages_full_page'])} | {totals['eligible3']} / {totals['eligible4']} |",
        f"| Coverage checked `partial_page`: `needs_crop` (F8b4) | {_pair(base['pages_needs_crop'])} | {totals['needs_crop3']} / {totals['needs_crop4']} |",
        f"| Coverage not yet checked | {_pair(base['pages_passing_but_coverage'])} | {totals['pending_coverage_only3']} / {totals['pending_coverage_only4']} |",
        f"| Reference-eligible quality-4 pages (adjudication-eligible), every gate but coverage | {base['reference_eligible_q4']} | {totals['reference']} |",
        f"| Of those, coverage checked `full_page` | 0 | {totals['reference_now']} |",
        "",
        "In F8b2 the converter column counts pages that also passed the other page gates; the F8b2 run did not count them apart.",
        "",
        "Transcription coverage comes from render checks: a look at the page render against its text, recorded with who",
        "checked (`agent` or `human`), the method and the date, and pinned to the page revision and Commons file. A human check",
        "overrides an agent check. A `partial_page` page is kept and marked `needs_crop` (decision 12): F8b4 crops its image to",
        "the transcribed region. The checks record scope facts only; they never change a quality level or an attestation.",
        "",
        "## Index gate results",
        "",
        "Counts by the first reason the gate returns, and by every reason an Index carries (an Index can carry several).",
        "Pages are quality-3 plus quality-4 pages.",
        "",
        "| Reason code | Indexes (first reason) | Pages (first reason) | Indexes (any reason) | Pages (any reason) |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| admitted | {len(admitted)} | {sum(_q(r, '3') + _q(r, '4') for r in admitted)} | {len(admitted)} | {sum(_q(r, '3') + _q(r, '4') for r in admitted)} |",
    ]
    for reason in sorted(any_reason, key=lambda code: (-pages_any[code], code)):
        lines.append(f"| `{reason}` | {first_reason.get(reason, 0)} | {pages_first.get(reason, 0)} | {any_reason[reason]} | {pages_any[reason]} |")
    lines += [
        "",
        "## Page gate results in admitted Indexes",
        "",
        "| Result | Quality 3 / quality 4 |",
        "| --- | ---: |",
        f"| eligible now (`full_page`) | {totals['eligible3']} / {totals['eligible4']} |",
        f"| eligible after the F8b4 crop (`needs_crop`) | {totals['needs_crop3']} / {totals['needs_crop4']} |",
        f"| passes every gate but awaits a coverage check | {totals['pending_coverage_only3']} / {totals['pending_coverage_only4']} |",
    ]
    for reason, count in sorted(page_reasons.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| rejected: `{reason}` | {count} |")
    if markup:
        lines += [
            "",
            "Markup outside the closed-world `wikisource_plain_text.v2` converter, by the first construct it rejects on a page:",
            "",
            "| Unsupported construct | Pages |",
            "| --- | ---: |",
        ]
        for message, count in sorted(markup.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"| {_cell(message.removeprefix('unsupported wikitext '))} | {count} |")
    checked = [r for r in admitted if ((r.get("page_gate") or {}).get("render_checks") or {}).get("checked")]
    lines += [
        "",
        "## Page render checks",
        "",
        f"{totals['render_checked']} pages checked: {totals['render_full_page']} `full_page`, {totals['render_partial_page']} `partial_page` (`needs_crop`).",
        "",
        "| Index | Pages checked | `full_page` | `partial_page` | Eligible now (Q3 / Q4) | Needs crop (Q3 / Q4) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for record in sorted(checked, key=lambda r: r["index_title"]):
        render = (record.get("page_gate") or {}).get("render_checks") or {}
        lines.append(
            f"| {_cell(record['index_title'])} | {render.get('checked', 0)} | {render.get('full_page', 0)} | {render.get('partial_page', 0)} "
            f"| {_both(record, 'eligible')} | {_both(record, 'needs_crop')} |"
        )
    if not checked:
        lines.append("| (none) | | | | | |")
    if totals["render_stale"]:
        lines += ["", f"{totals['render_stale']} recorded checks are stale (another page revision or Commons file) and were not applied."]
    lines += [
        "",
        f"## Top {top} admitted Indexes by pages passing every gate but coverage",
        "",
        "| Index | Scan source | Q3 / Q4 pages | Eligible now (Q3 / Q4) | Needs crop (Q3 / Q4) | Awaiting a coverage check (Q3 / Q4) | Reference-eligible Q4 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]

    def _passing(record: dict[str, Any]) -> int:
        gate = record.get("page_gate") or {}
        return sum(int((gate.get(key) or {}).get(level, 0)) for key in ("eligible", "needs_crop", "pending_coverage_only") for level in ("3", "4"))

    ranked = sorted(admitted, key=lambda r: (-_passing(r), -(_q(r, "3") + _q(r, "4")), r["index_title"]))
    for record in ranked[:top]:
        gate = record.get("page_gate") or {}
        lines.append(
            f"| {_cell(record['index_title'])} | {_cell((record['scan_rights'].get('scan_source') or {}).get('name') or '—')} "
            f"| {_q(record, '3')} / {_q(record, '4')} | {_both(record, 'eligible')} | {_both(record, 'needs_crop')} "
            f"| {_both(record, 'pending_coverage_only')} | {gate.get('reference_eligible_q4', 0)} |"
        )
    if not ranked:
        lines.append("| (none) | | | | | | |")
    unresolved = sorted(
        (r for r in records if not r["gate"]["admitted"] and not {"excluded_birnbaum_work", "creator_died_after_1955", "index_language_not_hebrew"} & set(r["gate"]["reasons"])),
        key=lambda r: (-(_q(r, "3") + _q(r, "4")), r["index_title"]),
    )
    unresolved = [r for r in unresolved if _q(r, "3") + _q(r, "4")]
    protected = [r for r in records if {"excluded_birnbaum_work", "creator_died_after_1955"} & set(r["gate"]["reasons"])]
    not_hebrew = [r for r in records if "index_language_not_hebrew" in r["gate"]["reasons"]]
    lines += [
        "",
        "## Rejected Indexes",
        "",
        f"- Shown to be protected in Israel (a creator died after 1955, or the Birnbaum works): {len(protected)} Indexes,"
        f" {sum(_q(r, '3') + _q(r, '4') for r in protected)} quality-3/4 pages.",
        f"- Not Hebrew (`index_language_not_hebrew`): {len(not_hebrew)} Indexes, {sum(_q(r, '3') + _q(r, '4') for r in not_hebrew)} pages.",
        f"- Unresolved data gaps (decision 10's residual): {len(unresolved)} Indexes with quality-3/4 pages,"
        f" {sum(_q(r, '3') + _q(r, '4') for r in unresolved)} pages. The highest-yield ones, with what is missing:",
        "",
        "| Index | Q3 / Q4 pages | Gate reasons | What is missing |",
        "| --- | ---: | --- | --- |",
    ]
    for record in unresolved[:resolve_top]:
        lines.append(
            f"| {_cell(record['index_title'])} | {_q(record, '3')} / {_q(record, '4')} | "
            f"{', '.join(f'`{reason}`' for reason in record['gate']['reasons'])} | {_cell(_missing_evidence(record))} |"
        )
    lines += [
        "",
        "## Method",
        "",
        "- Creators: Index fields `מחבר`, `מתרגם`, `עורך`, `מאייר` and the Commons `Author`, `Translator`, `Editor`, `Illustrator`",
        "  fields (plus the work's Wikidata `P50`/`P655`/`P98`/`P110` when the Commons file names a work item). Death years come from",
        "  Wikidata `P570` (the latest non-deprecated statement, as an upper bound at its precision) or the Wikisource author page's",
        "  Gregorian death year, taking the later of the two; then from cited facts recorded in the evidence file for creators the",
        "  wikis name only as plain text. A creator without any keeps no death year.",
        "- Work rights (decision 10): every creator dead by 1955 gives `author_died_by_1955`; failing that, a work published on or",
        "  before 1855 (the latest of the Commons date and the Index `שנה`, a Hebrew year read as its latest Gregorian year) gives",
        "  `presumed_pd_by_publication_age`. A creator who died after 1955 always rejects. Anonymous basis only from explicit markers.",
        "- Scans (decisions 9 and 10): a flat scan of a PD work is a faithful reproduction. The Commons licence tag, the scan source",
        "  and Google digitization are recorded as provenance and decide nothing.",
        "- Language: the Index `שפה` field, else the Commons `language` field, else a fact recorded in the evidence file. Only `he` is",
        "  admitted; another language gives `index_language_not_hebrew`, none recorded gives `index_language_unrecorded`.",
        "- Page text: `wikisource_plain_text.v2`, checked against MediaWiki's own rendering (`hocrgen.tools.wikisource_render_check`).",
        "",
    ]
    return "\n".join(lines)


# --- CLI ------------------------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator-only Hebrew Wikisource Index inventory through the F8b gates (network).")
    parser.add_argument("--work-dir", type=Path, required=True, help="Operator folder outside the repo: raw cache, snapshot and full inventory.")
    parser.add_argument("--checked-at", required=True, help="Evidence date recorded on every Index, e.g. 2026-11-06.")
    parser.add_argument("--summary-json", type=Path, help="Write the compact per-Index JSON here (the committed artifact).")
    parser.add_argument("--summary-md", type=Path, help="Write the markdown summary here (the committed artifact).")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between uncached API requests.")
    parser.add_argument("--skip-pages", action="store_true", help="Run the Index gate only.")
    parser.add_argument(
        "--page-checks",
        type=Path,
        help="Reviewable per-page render checks (wikisource_page_render_checks.v1), e.g. docs/wikisource_page_checks.json.",
    )
    parser.add_argument(
        "--index-evidence",
        type=Path,
        help="Recorded per-Index evidence (wikisource_index_evidence.v1), e.g. docs/wikisource_index_evidence.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - live network path
    args = parse_args(argv)
    client = MediaWikiClient(args.work_dir / "raw", delay=args.delay)
    inventory = run_inventory(
        client,
        checked_at=args.checked_at,
        snapshot_root=args.work_dir / "snapshot",
        with_pages=not args.skip_pages,
        page_checks=load_page_checks(args.page_checks),
        index_evidence=load_index_evidence(args.index_evidence),
    )
    args.work_dir.mkdir(parents=True, exist_ok=True)
    (args.work_dir / "wikisource_inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = compact_inventory(inventory)
    if args.summary_json:
        args.summary_json.write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.summary_md:
        args.summary_md.write_text(render_summary(compact), encoding="utf-8")
    sys.stdout.write(f"{len(inventory['indexes'])} Indexes, {len(inventory['pages'])} pages checked; {client.requests} API requests\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
