"""Edition texts beyond Project Ben-Yehuda for the F8f alignment: Sefaria and Project Gutenberg.

The F8f aligner (``hocrgen.tools.benyehuda_nli_alignment align``) places a human-typed edition text on a public-domain
scan of the same printed edition. Until now that text always came from Project Ben-Yehuda (PBY). This module adds two
more text sources, under ``planning/decisions/2026-11-11-text-sources-sefaria-gutenberg.md``:

- **Sefaria** (``sefaria``): a Hebrew version saved from ``/download/version/<title> - he - <versionTitle>.json``.
- **Project Gutenberg** (``gutenberg``): a plain-text ebook, for an ebook proofread from a known scan only.

Everything here is pure and network-free. The operator saves the raw API/download bytes (the snapshots); this module
gates them, normalises the text and writes a **text record** (``hocrgen.text_source_record.v1``) beside the text file.
The aligner reads the text record in place of a PBY catalogue row, re-checks the licence gate (fail-closed), and
copies the record's provenance onto every page report; the line builder copies it onto every line.

**Licence gate (fail-closed).** ``decide_sefaria_licence`` accepts a version only when its ``license`` string is exactly
Sefaria's public-domain label (``"Public Domain"``) or ``"CC0"`` (a public-domain dedication; heocr-lead, 2026-11-11)
**and** its ``versionSource`` is the catalogue record of a printed
edition (an NLI record, an Internet Archive item or a Project Gutenberg ebook) **and** its version title names the
printing's year. Everything else is rejected with a reason: CC BY-NC (``sefaria_licence_non_commercial``), ``unknown``
(``sefaria_licence_unknown``), CC BY and CC BY-SA (``sefaria_licence_attribution_needs_decision``: they need their own
decision), any other label, and a public-domain or CC0 label tied to no printing (``sefaria_no_printing``).
``decide_gutenberg_licence`` accepts an ebook only when it is listed in ``GUTENBERG_EDITIONS`` with the scan it was
proofread from, its RDF record says ``Public domain in the USA.``, its credits name that scan's source, and the scan
being aligned is that scan.

**Normaliser.** Sefaria segments carry markup: commentator anchors (``<i data-commentator=… data-order=…></i>``),
footnote markers and bodies (``<sup class="footnote-marker">…</sup><i class="footnote">…</i>``), ``<b>``, ``<small>``,
``<big>``, ``<strong>``, ``<br>`` and HTML entities, and a dash after a comment's bold opening quote (``<b>…</b> -``).
Anchors, footnotes and the dash are removed, other tags unwrapped, entities decoded, niqqud and cantillation removed,
and the punctuation of the print kept: ``׳ ״ — ־`` and the ASCII quotes Sefaria types for them. Project Gutenberg
text is cut to the body between the ``*** START`` and ``*** END`` lines, its transcriber's note is removed, its
``*bold*``, ``/italic/`` and ``_spaced_`` markup unwrapped, and the typo corrections the note lists are reverted to the
printed reading (the print is the label's reference), each only where the corrected reading occurs exactly once.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html
import json
import re
import sys
import unicodedata
import urllib.parse
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

TEXT_SOURCE_PBY = "pby"
TEXT_SOURCE_SEFARIA = "sefaria"
TEXT_SOURCE_GUTENBERG = "gutenberg"
TEXT_SOURCES = (TEXT_SOURCE_PBY, TEXT_SOURCE_SEFARIA, TEXT_SOURCE_GUTENBERG)

RECORD_FORMAT = "hocrgen.text_source_record.v1"
DECISION_RECORD = "planning/decisions/2026-11-11-text-sources-sefaria-gutenberg.md"
SEFARIA_NORMALISER = "sefaria_markup.v1"
GUTENBERG_NORMALISER = "gutenberg_plain_text.v1"

SEFARIA_PUBLIC_DOMAIN = "Public Domain"
# heocr-lead, 2026-11-11 (hocrgen#183): CC0, a public-domain dedication at least as open, is accepted like the label.
SEFARIA_CC0 = "CC0"
SEFARIA_ACCEPTED_LICENCES = (SEFARIA_PUBLIC_DOMAIN, SEFARIA_CC0)
SEFARIA_DOWNLOAD_URL = "https://www.sefaria.org/download/version/{name}.json"
SEFARIA_VERSIONS_URL = "https://www.sefaria.org/api/texts/versions/{title}"
SEFARIA_DIGITIZER = "Sefaria"

GUTENBERG_PUBLIC_DOMAIN = "Public domain in the USA."
GUTENBERG_EBOOK_URL = "https://www.gutenberg.org/ebooks/{ebook}"
GUTENBERG_TEXT_URL = "https://www.gutenberg.org/ebooks/{ebook}.txt.utf-8"
GUTENBERG_RDF_URL = "https://www.gutenberg.org/ebooks/{ebook}.rdf"
# Ebooks proofread from a known scan, and that scan: a Gutenberg text is accepted only for that edition.
GUTENBERG_EDITIONS: dict[str, dict[str, str]] = {
    "43740": {
        "ia_identifier": "betnekhothahalak01horouoft",
        "edition": "Bet Nekhot ha-Halakhot o Toratan shel Rishonim, part I, ed. Chaim Meir Horowitz, Frankfurt am Main 1881",
        "credit": "Internet Archive/Canadian Libraries",
    },
}

SCRIPTS = ("square", "rashi", "mixed")

# Reasons.
ACCEPTED = "text_licence_accepted"
REASON_NOT_HEBREW = "sefaria_version_not_hebrew"
REASON_NON_COMMERCIAL = "sefaria_licence_non_commercial"
REASON_UNKNOWN = "sefaria_licence_unknown"
REASON_ATTRIBUTION = "sefaria_licence_attribution_needs_decision"
REASON_OTHER_LICENCE = "sefaria_licence_not_public_domain"
REASON_NO_PRINTING = "sefaria_no_printing"
REASON_GUTENBERG_NOT_LISTED = "gutenberg_ebook_not_listed"
REASON_GUTENBERG_RIGHTS = "gutenberg_rights_not_public_domain"
REASON_GUTENBERG_CREDITS = "gutenberg_credits_do_not_name_the_scan"
REASON_GUTENBERG_OTHER_SCAN = "gutenberg_text_not_for_this_scan"

# A catalogue record of a printed edition: an NLI record, an Internet Archive item or a Project Gutenberg ebook.
PRINTING_RECORDS = (
    ("nli_record", re.compile(r"nli\.org\.il/.*?(NNL_ALEPH\d{6,}|99\d{10,16}5171)", re.I)),
    ("internet_archive_item", re.compile(r"archive\.org/details/([\w.-]+)", re.I)),
    ("gutenberg_ebook", re.compile(r"gutenberg\.org/ebooks/(\d+)", re.I)),
)
PRINTING_YEAR = re.compile(r"(?<!\d)(1[4-9]\d\d)(?!\d)")

# --- the licence gate ---------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class TextLicenceDecision:
    """The text-source gate's verdict on one text, and the evidence it rests on."""

    accepted: bool
    reason: str
    text_source: str
    licence: str | None
    printing: dict[str, Any] | None
    evidence: dict[str, Any]

    def record(self) -> dict[str, Any]:
        return {
            "gate": f"hocrgen.fetchers.text_sources.decide_{self.text_source}_licence",
            "decision_record": DECISION_RECORD,
            "decision": "accepted" if self.accepted else "rejected",
            "reason": self.reason,
            "text_source": self.text_source,
            "licence": self.licence,
            "printing": self.printing,
            "evidence": dict(self.evidence),
        }


def licence_class(label: str | None) -> str:
    """The gate's reading of a Sefaria licence string: the reason it is rejected, or ``ACCEPTED`` (``"Public Domain"`` or
    ``"CC0"``). Exact match only."""

    if label in SEFARIA_ACCEPTED_LICENCES:
        return ACCEPTED
    text = (label or "").strip()
    if not text or text.lower() == "unknown":
        return REASON_UNKNOWN
    if re.search(r"\bNC\b|non[\s-]?commercial", text, re.I):
        return REASON_NON_COMMERCIAL
    if re.search(r"\bCC[\s-]?BY\b", text, re.I):
        return REASON_ATTRIBUTION
    return REASON_OTHER_LICENCE


def printing_evidence(version_source: str | None, version_title: str | None, version_title_he: str | None = None) -> dict[str, Any] | None:
    """The printing a version names: its catalogue record (kind and id) and the year in its title, or None."""

    source = (version_source or "").strip()
    record = None
    for kind, pattern in PRINTING_RECORDS:
        match = pattern.search(source)
        if match:
            record = {"kind": kind, "id": match.group(1), "url": source}
            break
    years = PRINTING_YEAR.findall(version_title or "")
    if record is None or not years:
        return None
    return {**record, "version_title": version_title, "version_title_he": version_title_he or None,
            "year_in_title": [int(y) for y in years]}


def decide_sefaria_licence(version: Mapping[str, Any]) -> TextLicenceDecision:
    """Gate a Sefaria version (a download JSON, or one entry of ``/api/texts/versions``). Fail-closed: the licence
    must be exactly ``"Public Domain"`` or ``"CC0"`` and the version must name a printing (``printing_evidence``)."""

    licence = version.get("license")
    language = version.get("actualLanguage") or version.get("language")
    evidence = {
        "title": version.get("title"),
        "versionTitle": version.get("versionTitle"),
        "versionTitleInHebrew": version.get("versionTitleInHebrew") or None,
        "versionSource": version.get("versionSource"),
        "license": licence,
        "digitizedBySefaria": bool(version.get("digitizedBySefaria")),
        "language": language,
    }
    printing = printing_evidence(version.get("versionSource"), version.get("versionTitle"), version.get("versionTitleInHebrew"))
    if language != "he":
        reason = REASON_NOT_HEBREW
    else:
        reason = licence_class(licence if isinstance(licence, str) else None)
        if reason == ACCEPTED and printing is None:
            reason = REASON_NO_PRINTING
    return TextLicenceDecision(reason == ACCEPTED, reason, TEXT_SOURCE_SEFARIA, licence, printing, evidence)


def gutenberg_rights(rdf: str) -> str | None:
    match = re.search(r"<dcterms:rights>([^<]*)</dcterms:rights>", rdf)
    return html.unescape(match.group(1)).strip() if match else None


def gutenberg_credits(raw: str) -> str | None:
    match = re.search(r"^Credits:(.*?)(?:\n\s*\n)", raw, re.S | re.M)
    return " ".join(match.group(1).split()) if match else None


def decide_gutenberg_licence(ebook: str, rdf: str, raw_text: str, *, ia_identifier: str | None) -> TextLicenceDecision:
    """Gate a Project Gutenberg ebook for one scan: listed in ``GUTENBERG_EDITIONS``, PD per its RDF record, credits
    naming the scan's source, and ``ia_identifier`` the scan it was proofread from."""

    listed = GUTENBERG_EDITIONS.get(str(ebook))
    rights = gutenberg_rights(rdf)
    credits = gutenberg_credits(raw_text)
    evidence = {"ebook": str(ebook), "rdf_rights": rights, "credits": credits, "listed_edition": listed,
                "scan_aligned": ia_identifier}
    printing = None
    if listed is None:
        reason = REASON_GUTENBERG_NOT_LISTED
    elif rights != GUTENBERG_PUBLIC_DOMAIN:
        reason = REASON_GUTENBERG_RIGHTS
    elif not credits or listed["credit"] not in credits:
        reason = REASON_GUTENBERG_CREDITS
    elif ia_identifier != listed["ia_identifier"]:
        reason = REASON_GUTENBERG_OTHER_SCAN
    else:
        reason = ACCEPTED
        printing = {"kind": "gutenberg_ebook", "id": str(ebook), "url": GUTENBERG_EBOOK_URL.format(ebook=ebook),
                    "edition": listed["edition"], "proofread_from": f"internet_archive:{listed['ia_identifier']}"}
    return TextLicenceDecision(reason == ACCEPTED, reason, TEXT_SOURCE_GUTENBERG, rights, printing, evidence)


# --- normalisers --------------------------------------------------------------------------------------------

# Niqqud and cantillation (U+0591-U+05C7) except maqaf U+05BE, paseq U+05C0, sof pasuq U+05C3, nun hafukha U+05C6.
POINTS = re.compile("[֑-ׇֽֿׁׂׅׄ]")
FOOTNOTE = re.compile(r"<sup[^>]*>.*?</sup>\s*<i[^>]*class=\"footnote\"[^>]*>.*?</i>", re.S)
FOOTNOTE_BODY = re.compile(r"<i[^>]*class=\"footnote\"[^>]*>.*?</i>", re.S)
SUP = re.compile(r"<sup[^>]*>.*?</sup>", re.S)
ANCHOR = re.compile(r"<i[^>]*data-commentator[^>]*>\s*</i>", re.S)
BOLD_DASH = re.compile(r"(</b>)\s*[-–]\s+")
BREAK = re.compile(r"<br\s*/?>", re.I)
TAG = re.compile(r"</?[a-zA-Z][^>]*>")
FORMAT_CHARS = re.compile("[​-‏‪-‮⁦-⁩﻿]")
SPACES = re.compile(r"[ \t ]+")


def strip_points(text: str) -> str:
    return unicodedata.normalize("NFC", POINTS.sub("", unicodedata.normalize("NFD", text)))


def normalise_sefaria_segment(raw: str, counts: Counter | None = None) -> str:
    """One Sefaria segment as plain edition text (see the module docstring). ``counts`` tallies what was removed."""

    counts = counts if counts is not None else Counter()
    text = raw
    for name, pattern, repl in (("footnotes", FOOTNOTE, " "), ("footnote_bodies", FOOTNOTE_BODY, " "), ("sup_markers", SUP, ""),
                                ("commentator_anchors", ANCHOR, ""), ("bold_dashes", BOLD_DASH, r"\1 "), ("line_breaks", BREAK, "\n")):
        text, n = pattern.subn(repl, text)
        counts[name] += n
    text, n = TAG.subn("", text)
    counts["tags_unwrapped"] += n
    text = html.unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    text, n = FORMAT_CHARS.subn("", text)
    counts["format_chars"] += n
    before = len(text)
    text = strip_points(text)
    counts["points_removed"] += before - len(text)
    lines = [SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def _schema_keys(schema: Mapping[str, Any] | None) -> list[str]:
    nodes = (schema or {}).get("nodes") or []
    return [str(node.get("enTitle") or "") for node in nodes]


def flatten_sefaria(text: Any, schema: Mapping[str, Any] | None = None, path: str = "") -> list[tuple[str, str]]:
    """``(ref path, raw segment)`` in reading order: jagged arrays depth-first, complex texts by schema node order
    (keys the schema does not list follow in the JSON's order)."""

    out: list[tuple[str, str]] = []
    if isinstance(text, str):
        if text.strip():
            out.append((path, text))
    elif isinstance(text, list):
        for i, item in enumerate(text, 1):
            out.extend(flatten_sefaria(item, None, f"{path}.{i}" if path else str(i)))
    elif isinstance(text, Mapping):
        order = [k for k in _schema_keys(schema) if k in text] + [k for k in text if k not in _schema_keys(schema)]
        nodes = {str(n.get("enTitle") or ""): n for n in (schema or {}).get("nodes") or []}
        for key in order:
            out.extend(flatten_sefaria(text[key], nodes.get(key), f"{path}/{key}" if path else key or "_default"))
    return out


def sefaria_text(version: Mapping[str, Any], parts: Sequence[str] | None = None) -> tuple[str, dict[str, Any]]:
    """The normalised edition text of a Sefaria download JSON (one segment per line, blank line between top-level
    parts), and its statistics. ``parts`` keeps only those top-level parts (schema node ``enTitle``s), in order."""

    text = version.get("text")
    schema = version.get("schema")
    if parts is not None:
        if not isinstance(text, Mapping):
            raise ValueError("parts given for a text without top-level parts")
        missing = [p for p in parts if p not in text]
        if missing:
            raise ValueError(f"parts not in the text: {missing}")
        nodes = {str(n.get("enTitle") or ""): n for n in (schema or {}).get("nodes") or []}
        segments = [seg for p in parts for seg in flatten_sefaria(text[p], nodes.get(p), p or "_default")]
    else:
        segments = flatten_sefaria(text, schema)
    counts: Counter = Counter()
    lines: list[str] = []
    top = None
    for ref, raw in segments:
        head = ref.split("/")[0].split(".")[0]
        if top is not None and head != top:
            lines.append("")
        top = head
        clean = normalise_sefaria_segment(raw, counts)
        if clean:
            lines.append(clean)
    body = "\n".join(lines).strip() + "\n"
    stats = {"segments": len(segments), "parts": list(parts) if parts is not None else None, "removed": dict(sorted(counts.items())),
             **text_stats(body)}
    return body, stats


GUTENBERG_START = re.compile(r"^\*\*\* START OF TH[EI]S? PROJECT GUTENBERG EBOOK.*?\*\*\*\s*$", re.M)
GUTENBERG_END = re.compile(r"^\*\*\* END OF TH[EI]S? PROJECT GUTENBERG EBOOK.*?\*\*\*\s*$", re.M)
GUTENBERG_NOTE = re.compile(r"^\s*הערות על המהדורה אלקטרונית\s*$", re.M)
CORRECTION = re.compile(r"^\s*\*\s+(?P<where>[^:]+):\s*(?P<printed>.+?)\s+←\s+(?P<corrected>.+?)\s*$", re.M)
GUTENBERG_MARKUP = (re.compile(r"\*([^*\n]+)\*"), re.compile(r"(?<![\w/])/([^/\n]+)/(?![\w/])"), re.compile(r"_([^_\n]+)_"))
BIDI_MARKS = re.compile("[‪-‮⁦-⁩‎‏]")


def gutenberg_body(raw: str) -> tuple[str, dict[str, Any]]:
    """The printed text of a Project Gutenberg plain-text ebook (see the module docstring) and its statistics."""

    start, end = GUTENBERG_START.search(raw), GUTENBERG_END.search(raw)
    if start is None or end is None or end.start() <= start.end():
        raise ValueError("not a Project Gutenberg text: START/END lines not found")
    body = raw[start.end():end.start()].replace("\r\n", "\n").replace("\r", "\n")
    note = GUTENBERG_NOTE.search(body)
    corrections: list[dict[str, str]] = []
    if note is not None:
        corrections = [{k: BIDI_MARKS.sub("", m.group(k)).strip() for k in ("where", "printed", "corrected")}
                       for m in CORRECTION.finditer(body[note.end():])]
        body = body[:note.start()]
    reverted, kept = [], []
    for item in corrections:
        printed, corrected = item["printed"], item["corrected"]
        if body.count(corrected) == 1 and printed not in body:
            body = body.replace(corrected, printed)
            reverted.append(item)
        else:
            kept.append({**item, "why_kept": f"corrected reading occurs {body.count(corrected)} times"})
    counts = Counter()
    for pattern in GUTENBERG_MARKUP:
        body, n = pattern.subn(r"\1", body)
        counts["markup_unwrapped"] += n
    body, n = BIDI_MARKS.subn("", body)
    counts["bidi_marks"] += n
    before = len(body)
    body = strip_points(body)
    counts["points_removed"] += before - len(body)
    lines = [SPACES.sub(" ", line).strip() for line in body.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"
    stats = {"removed": dict(counts), "transcriber_corrections": len(corrections), "corrections_reverted_to_print": reverted,
             "corrections_kept": kept, **text_stats(text)}
    return text, stats


# --- text statistics (the eval-reserve choice) --------------------------------------------------------------

HEBREW_LETTER = re.compile("[א-ת]")
# An abbreviation mark: geresh or gershayim (Hebrew or the ASCII quote Sefaria types), inside or at the end of a word.
ABBREVIATION = re.compile("(?<=[א-ת])[׳״'\"](?=[א-ת]|\\s|$|[.,:;)\\]])")


def text_stats(text: str) -> dict[str, Any]:
    """Letters, words, abbreviation marks (׳ ״ ' " after a letter) and their rate per 1,000 letters, mean word length."""

    letters = len(HEBREW_LETTER.findall(text))
    words = [w for w in text.split() if HEBREW_LETTER.search(w)]
    marks = ABBREVIATION.findall(text)
    return {
        "chars": len(text),
        "hebrew_letters": letters,
        "hebrew_words": len(words),
        "abbreviation_marks": len(marks),
        "abbreviation_marks_per_1000_letters": round(1000 * len(marks) / letters, 2) if letters else None,
        "abbreviated_word_share": round(sum(1 for w in words if ABBREVIATION.search(w)) / len(words), 4) if words else None,
        "mean_word_letters": round(letters / len(words), 3) if words else None,
    }


# --- the text record ----------------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sefaria_download_url(title: str, version_title: str) -> str:
    return SEFARIA_DOWNLOAD_URL.format(name=urllib.parse.quote(f"{title} - he - {version_title}"))


def _people(people: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for person in people:
        role = person.get("role")
        if role not in ("author", "editor", "translator", "annotator"):
            raise ValueError(f"contributor role must be author, editor, translator or annotator: {person}")
        if not person.get("qid") or not re.fullmatch(r"Q\d+", str(person["qid"])):
            raise ValueError(f"every contributor needs a Wikidata QID: {person}")
        out.append({"name": person["name"], "role": role, "qid": person["qid"], **({"note": person["note"]} if person.get("note") else {})})
    return out


def build_text_record(
    *,
    work_id: str,
    decision: TextLicenceDecision,
    title: str,
    he_title: str | None,
    text: str,
    stats: Mapping[str, Any],
    api_url: str,
    snapshot_sha256: str,
    contributors: Sequence[Mapping[str, Any]],
    publication: Mapping[str, Any],
    script: str,
    normaliser: str,
    anonymous_work: Mapping[str, Any] | None = None,
    versions_api_url: str | None = None,
    versions_snapshot_sha256: str | None = None,
    digitizer: str | None = None,
) -> dict[str, Any]:
    """The text record the aligner reads (``hocrgen.text_source_record.v1``). Refuses a rejected text, a work id that
    is not ``<source>_<slug>``, an unknown script, or a contributor without a Wikidata QID."""

    if not decision.accepted:
        raise ValueError(f"text rejected by the licence gate: {decision.reason}")
    if not re.fullmatch(rf"{decision.text_source}_[a-z0-9_]+", work_id):
        raise ValueError(f"work id must be {decision.text_source}_<slug> (lower case): {work_id!r}")
    if script not in SCRIPTS:
        raise ValueError(f"script must be one of {SCRIPTS}: {script!r}")
    people = _people(contributors)
    if not any(p["role"] == "author" for p in people) and not anonymous_work:
        raise ValueError("no author listed and the work is not marked anonymous")
    if not publication.get("place") or not isinstance(publication.get("year"), int):
        raise ValueError("publication needs a place and a year")
    record = {
        "format": RECORD_FORMAT,
        "work_id": work_id,
        "text_source": decision.text_source,
        "title": title,
        "he_title": he_title,
        "text_version_title": decision.evidence.get("versionTitle") if decision.text_source == TEXT_SOURCE_SEFARIA else decision.printing.get("edition"),
        "text_version_source": (decision.printing or {}).get("url"),
        "text_licence": decision.licence,
        "text_licence_decision": decision.record(),
        "text_api_url": api_url,
        "text_snapshot_sha256": snapshot_sha256,
        **({"versions_api_url": versions_api_url, "versions_snapshot_sha256": versions_snapshot_sha256} if versions_api_url else {}),
        "text_digitizer": digitizer,
        "contributors": people,
        "anonymous_work": dict(anonymous_work) if anonymous_work else None,
        "publication": {"place": publication["place"], "year": publication["year"], **({"source": publication["source"]} if publication.get("source") else {})},
        "script": script,
        "normaliser": normaliser,
        "text_sha256": sha256_bytes(text.encode("utf-8")),
        "text_stats": dict(stats),
    }
    return record


def check_text_record(record: Mapping[str, Any], text: str, *, ia_identifier: str | None = None) -> str | None:
    """Why the aligner must refuse this text record and text, or None. Fails closed: the record's own licence gate is
    replayed from its evidence, and the text file must be the one the record describes."""

    if record.get("format") != RECORD_FORMAT:
        return f"text record format is not {RECORD_FORMAT}"
    if record.get("text_source") not in (TEXT_SOURCE_SEFARIA, TEXT_SOURCE_GUTENBERG):
        return f"text source not supported here: {record.get('text_source')!r}"
    if sha256_bytes(text.encode("utf-8")) != record.get("text_sha256"):
        return "text file sha256 differs from the text record"
    decision = record.get("text_licence_decision") or {}
    if decision.get("decision") != "accepted":
        return f"text record not accepted by the licence gate: {decision.get('reason')}"
    if record["text_source"] == TEXT_SOURCE_SEFARIA:
        replay = decide_sefaria_licence({**(decision.get("evidence") or {}),
                                         "actualLanguage": (decision.get("evidence") or {}).get("language"),
                                         "license": record.get("text_licence")})
        if not replay.accepted:
            return f"text rejected by the licence gate: {replay.reason}"
    else:
        listed = GUTENBERG_EDITIONS.get(str((decision.get("evidence") or {}).get("ebook")))
        if listed is None or record.get("text_licence") != GUTENBERG_PUBLIC_DOMAIN:
            return "text rejected by the licence gate: gutenberg ebook not listed or not public domain"
        if ia_identifier is not None and ia_identifier != listed["ia_identifier"]:
            return f"text rejected by the licence gate: {REASON_GUTENBERG_OTHER_SCAN} ({listed['ia_identifier']} only)"
    if record.get("script") not in SCRIPTS:
        return f"text record script not in {SCRIPTS}"
    return None


def justification_row(record: Mapping[str, Any]) -> dict[str, str]:
    """The record as the catalogue row ``hocrgen.fetchers.ia_justification`` reads (names and QIDs by role)."""

    row: dict[str, str] = {"ID": str(record["work_id"]),
                           "source_edition": f"{record['publication']['place']}, {record['publication']['year']}"}
    for role, names, uris in (("author", "authors", "author_uris"), ("translator", "translators", "translator_uris"),
                              ("editor", "editors", "editor_uris"), ("annotator", "annotators", "annotator_uris")):
        people = [p for p in record.get("contributors") or [] if p["role"] == role]
        row[names] = "; ".join(p["name"] for p in people)
        row[uris] = "; ".join(f"http://www.wikidata.org/entity/{p['qid']}" for p in people)
    if record.get("anonymous_work"):
        row["anonymous_work"] = json.dumps(record["anonymous_work"], ensure_ascii=False, sort_keys=True)
    return row


def work_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """The alignment report's ``work`` for a text-source text (the PBY fields' counterparts and the provenance)."""

    return {
        "work_id": record["work_id"],
        "pby_id": None,
        "title": record.get("he_title") or record.get("title"),
        "title_en": record.get("title"),
        "authors": "; ".join(p["name"] for p in record.get("contributors") or [] if p["role"] == "author") or None,
        "source_edition": f"{record['publication']['place']}, {record['publication']['year']}",
        "source_edition_year": record["publication"]["year"],
        **{key: record.get(key) for key in PROVENANCE_FIELDS},
        "text_digitizer": record.get("text_digitizer"),
        "script": record.get("script"),
        "normaliser": record.get("normaliser"),
        "text_record_sha256": sha256_bytes(json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8")),
    }


# Per-row provenance carried from the text record to every alignment page and line.
PROVENANCE_FIELDS = ("text_source", "text_version_title", "text_version_source", "text_licence", "text_api_url", "text_snapshot_sha256")


# --- operator CLI -------------------------------------------------------------------------------------------


def _load_people(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(out_dir: Path, work_id: str, text: str, record: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{work_id}.txt").write_text(text, encoding="utf-8")
    (out_dir / f"{work_id}.record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _cmd_sefaria(args: argparse.Namespace) -> int:
    data = args.snapshot.read_bytes()
    version = json.loads(data)
    decision = decide_sefaria_licence(version)
    if not decision.accepted:
        sys.stderr.write(f"rejected by the Sefaria licence gate: {decision.reason}\n")
        return 2
    spec = _load_people(args.spec)
    text, stats = sefaria_text(version, spec.get("parts"))
    versions_sha = sha256_bytes(args.versions_snapshot.read_bytes()) if args.versions_snapshot else None
    if args.versions_snapshot:
        listed = [v for v in json.loads(args.versions_snapshot.read_bytes()) if v.get("versionTitle") == version.get("versionTitle")
                  and (v.get("actualLanguage") or v.get("language")) == "he"]
        if len(listed) != 1 or listed[0].get("license") != version.get("license"):
            sys.stderr.write("the versions list does not confirm this version's licence\n")
            return 2
    record = build_text_record(
        work_id=args.work_id, decision=decision, title=str(version.get("title")), he_title=version.get("heTitle"), text=text,
        stats=stats, api_url=sefaria_download_url(str(version.get("title")), str(version.get("versionTitle"))),
        snapshot_sha256=sha256_bytes(data), contributors=spec["contributors"], publication=spec["publication"],
        script=spec["script"], normaliser=SEFARIA_NORMALISER, anonymous_work=spec.get("anonymous_work"),
        versions_api_url=SEFARIA_VERSIONS_URL.format(title=urllib.parse.quote(str(version.get("title")))) if versions_sha else None,
        versions_snapshot_sha256=versions_sha, digitizer=SEFARIA_DIGITIZER if version.get("digitizedBySefaria") else None,
    )
    _write(args.out_dir, args.work_id, text, record)
    sys.stdout.write(json.dumps({"work_id": args.work_id, **stats}, ensure_ascii=False) + "\n")
    return 0


def _cmd_gutenberg(args: argparse.Namespace) -> int:
    raw_bytes = args.snapshot.read_bytes()
    raw = raw_bytes.decode("utf-8")
    rdf = args.rdf.read_text(encoding="utf-8")
    decision = decide_gutenberg_licence(args.ebook, rdf, raw, ia_identifier=args.ia_identifier)
    if not decision.accepted:
        sys.stderr.write(f"rejected by the Gutenberg licence gate: {decision.reason}\n")
        return 2
    spec = _load_people(args.spec)
    text, stats = gutenberg_body(raw)
    record = build_text_record(
        work_id=args.work_id, decision=decision, title=spec.get("title") or f"Project Gutenberg #{args.ebook}", he_title=spec.get("he_title"),
        text=text, stats=stats, api_url=GUTENBERG_TEXT_URL.format(ebook=args.ebook), snapshot_sha256=sha256_bytes(raw_bytes),
        contributors=spec["contributors"], publication=spec["publication"], script=spec["script"], normaliser=GUTENBERG_NORMALISER,
        anonymous_work=spec.get("anonymous_work"), versions_api_url=GUTENBERG_RDF_URL.format(ebook=args.ebook),
        versions_snapshot_sha256=sha256_bytes(rdf.encode("utf-8")), digitizer="Project Gutenberg (Distributed Proofreaders Canada)",
    )
    _write(args.out_dir, args.work_id, text, record)
    sys.stdout.write(json.dumps({"work_id": args.work_id, **{k: v for k, v in stats.items() if not k.startswith("corrections_")},
                                 "corrections_reverted": len(stats["corrections_reverted_to_print"])}, ensure_ascii=False) + "\n")
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    """Gate every version in a saved ``/api/texts/versions/<title>`` list (a report; nothing is written)."""

    rows = []
    for path in args.versions:
        for version in json.loads(Path(path).read_bytes()):
            decision = decide_sefaria_licence(version)
            rows.append({"file": Path(path).name, "versionTitle": version.get("versionTitle"), "license": version.get("license"),
                         "language": version.get("actualLanguage") or version.get("language"), "decision": decision.reason})
    sys.stdout.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    return 0


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gate and normalise Sefaria and Project Gutenberg texts for the F8f aligner.")
    sub = parser.add_subparsers(dest="command", required=True)
    sef = sub.add_parser("sefaria", help="a saved Sefaria version download -> text/<work_id>.txt and .record.json")
    sef.add_argument("--snapshot", type=Path, required=True, help="the saved /download/version/<title> - he - <version>.json")
    sef.add_argument("--versions-snapshot", type=Path, help="the saved /api/texts/versions/<title> (cross-checks the licence)")
    sef.add_argument("--spec", type=Path, required=True, help="JSON: contributors (name, role, qid), publication, script, parts, anonymous_work")
    sef.add_argument("--work-id", required=True)
    sef.add_argument("--out-dir", type=Path, required=True)
    pg = sub.add_parser("gutenberg", help="a saved Project Gutenberg ebook -> text/<work_id>.txt and .record.json")
    pg.add_argument("--snapshot", type=Path, required=True, help="the saved <ebook>.txt.utf-8")
    pg.add_argument("--rdf", type=Path, required=True, help="the saved <ebook>.rdf")
    pg.add_argument("--ebook", required=True)
    pg.add_argument("--ia-identifier", required=True, help="the scan the text will be aligned to (must be the one it was proofread from)")
    pg.add_argument("--spec", type=Path, required=True)
    pg.add_argument("--work-id", required=True)
    pg.add_argument("--out-dir", type=Path, required=True)
    gate = sub.add_parser("gate", help="report the gate's decision on every version of saved versions lists")
    gate.add_argument("versions", nargs="+")
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Iterable[str] | None = None) -> int:  # pragma: no cover - operator path
    args = parse_args(argv)
    return {"sefaria": _cmd_sefaria, "gutenberg": _cmd_gutenberg, "gate": _cmd_gate}[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
