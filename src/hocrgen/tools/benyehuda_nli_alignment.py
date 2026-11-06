"""Operator-only pilot: align Project Ben-Yehuda texts to NLI free-use scans of the same edition (F8f).

Project Ben-Yehuda (PBY) publishes a public-domain dump of human-typed Hebrew works
(``github.com/projectbenyehuda/public_domain_dump``). The dump has no scan links and no page or line breaks:
its ``pseudocatalogue.csv`` names the printed edition a work was typed from only as free text
(``source_edition``). This tool turns a matched work into silver page-text pairs on NLI scans in three steps:

1. ``match``: edition matching. For each operator-written candidate (PBY ids, NLI Search API queries, the
   expected year, and title and publisher terms), the tool searches NLI, keeps ``book`` hits whose date is
   within the tolerance and whose title and publisher contain the terms, and decides each kept hit's rights
   with the unchanged F8c gate (``decide_nli_rights``) on its IIIF manifest. A candidate is ``matched`` only
   when a hit carries ``public-domain-free-use`` with canvases. The catalogue fields, the NLI record and the
   reasons are recorded per candidate.
2. ``align``: page and line alignment. The scan pages are OCR'd with Tesseract (operator-only). **The OCR is
   used only to localize PBY text on the page, never as reference text**: no OCR text is written to any
   output, only line geometry, letter counts and scores. The PBY text is aligned to the OCR lines with an
   order-preserving method: unique letter n-grams shared by both sides are chained by a longest increasing
   subsequence, and each OCR line is then refined against its PBY window with ``difflib``. Each page gets a
   PBY text span (character offsets into the PBY file), an alignment score, per-line spans, the measured
   PBY/print differences, and a crop decision (maintainer decision 12): the pair image is the located
   region, so text PBY lacks (running headers, relocated footnotes, the end of another work) stays outside
   it; when such text sits inside the region the page is flagged ``needs_review``.
   ``align`` also writes a side-by-side HTML report (scan with line boxes and crop, PBY text per line) for a
   fast human verification pass. It stays in the operator's work directory.
3. ``fixture`` writes a small pinned fixture of a few aligned pages, and ``summarize`` the committed pilot
   summary (match rows, per-work page rows, pooled quality and difference statistics).

Every pair is **silver**: ``text_provenance: human_typed_edition_text_aligned``,
``adjudication_status: not_adjudicated``, ``reference_eligible: false`` and
``verification_status: needs_human_verification``. A human verification pass (a campaign is allowed by the
2026-11-06 decision) is required before any pair becomes a reference through F2.

The NLI key is read only from ``NLI_API_KEY`` and is never printed, logged or written. CI never runs the
network or OCR paths; tests use pinned fixtures and synthetic input.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import dataclasses
import hashlib
import html
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from PIL import Image

from hocrgen.fetchers.nli_iiif import (
    NLI_CAPTURE_FORMAT,
    NliManifestCapture,
    canvas_image_service,
    capture_from_payload,
    decide_nli_rights,
    manifest_canvases,
    trim_manifest,
)
from hocrgen.tools.nli_printed_inventory import parse_publication_year
from hocrgen.tools.nli_search_discovery import (
    NLI_API_KEY_ENV,
    NLI_SEARCH_ENDPOINT,
    redact,
    summarize_search_record,
)
from hocrgen.utils.hashing import sha256_file

MATCH_FORMAT = "hocrgen.benyehuda_nli_match.v1"
FIXTURE_FORMAT = "hocrgen.benyehuda_nli_fixture.v1"
ALIGNMENT_FORMAT = "hocrgen.benyehuda_nli_alignment.v1"
TOOL_VERSION = "1"
USER_AGENT = "hocrgen-benyehuda-nli-alignment (+https://github.com/HeOCR/hocrgen)"

PBY_REPOSITORY = "https://github.com/projectbenyehuda/public_domain_dump"
PBY_RAW_BASE = "https://raw.githubusercontent.com/projectbenyehuda/public_domain_dump"
PBY_DEFAULT_RELEASE = "2026-03"

# Silver status every emitted pair carries.
TEXT_PROVENANCE = "human_typed_edition_text_aligned"
ADJUDICATION_STATUS = "not_adjudicated"
VERIFICATION_STATUS = "needs_human_verification"
SILVER_STATUS = {
    "text_provenance": TEXT_PROVENANCE,
    "adjudication_status": ADJUDICATION_STATUS,
    "reference_eligible": False,
    "verification_status": VERIFICATION_STATUS,
}
OCR_ROLE = "localization_only"

# Alignment parameters (recorded in every report).
GRAM_SIZE = 8
LINE_MATCH_THRESHOLD = 0.70
MIN_LINE_LETTERS = 4
MIN_PAGE_MATCHED_LINES = 3
QUALITY_BINS = (("high", 0.90), ("medium", 0.80), ("low", 0.0))
CROP_PAD_LINE_FRACTION = 0.35
NOISE_CONFIDENCE = 55.0
INTERIOR_PAGE_MIN_LETTERS = 300
HEADER_MAX_LETTERS = 30
EXTRAPOLATION_LIMIT = 200
CATCHWORD_MAX_LETTERS = 15

LINE_MATCHED = "matched"
LINE_RELOCATED = "relocated_in_pby"
LINE_HEADER = "running_header"
LINE_PAGE_NUMBER = "page_number"
LINE_NON_TEXT = "non_text"
LINE_UNMATCHED = "unmatched_text"
LINE_NOISE = "low_confidence_noise"
LINE_CATCHWORD = "catchword"
UNTRANSCRIBED_CLASSES = frozenset({LINE_RELOCATED, LINE_HEADER, LINE_UNMATCHED, LINE_CATCHWORD})

PAGE_ALIGNED = "aligned"
PAGE_WEAK = "weak"
PAGE_OUTSIDE = "outside_work"

CROP_CROPPED = "cropped"
CROP_REVIEW = "needs_review"
CROP_NONE = "not_applicable"
CROP_METHOD = "ocr_line_localization"

FetchResult = tuple[int, bytes]
Fetch = Callable[[str], FetchResult]

# --- text normalization --------------------------------------------------------------------------------------

HEBREW_LETTERS = frozenset(chr(code) for code in range(0x05D0, 0x05EB))
FINAL_FORMS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
YIDDISH_LIGATURES = {"װ": "וו", "ױ": "וי", "ײ": "יי"}
# Letters Tesseract confuses on old Hebrew print, folded together for anchoring and localization only.
CONFUSION_FOLD = str.maketrans({"ר": "ד", "ח": "ה", "ת": "ה", "כ": "ב", "ז": "ו", "ס": "מ", "ט": "מ"})
# Matres lectionis, dropped in the loose skeleton so plene and defective spellings align.
MATRES = frozenset({"ו", "י"})
NIQQUD_POINTS = frozenset(
    [chr(code) for code in range(0x05B0, 0x05BD)] + ["ֿ", "ׁ", "ׂ", "ׇ"]
)
CANTILLATION = frozenset(chr(code) for code in range(0x0591, 0x05B0))
PBY_FOOTNOTE_MARKER = re.compile(r"\[\^\d+\]|(?<![\d\w])\d{1,3}(?=[א-ת])")
PRINT_LOW_QUOTE = re.compile(r",,|„")
WORD = re.compile(r"\S+")


def _letters(text: str) -> Iterable[tuple[int, str]]:
    """Yield (offset, normalized letter) for each Hebrew or Latin letter, dropping marks and punctuation."""

    for offset, char in enumerate(text):
        if char in YIDDISH_LIGATURES:
            for letter in YIDDISH_LIGATURES[char]:
                yield offset, letter
        elif char in HEBREW_LETTERS:
            yield offset, char.translate(FINAL_FORMS)
        elif "a" <= char.lower() <= "z":
            yield offset, char.lower()


@dataclasses.dataclass(frozen=True)
class Skeleton:
    """Letter skeletons of a text with offsets back into it.

    ``strict`` keeps every letter (final forms normalized). ``loose`` also drops matres lectionis and folds
    OCR-confusable letters; it is used for anchoring and localization. ``loose_to_strict`` maps each loose
    position to its strict position, and ``strict_offsets`` maps each strict position to the source offset.
    """

    strict: str
    strict_offsets: tuple[int, ...]
    loose: str
    loose_to_strict: tuple[int, ...]

    def loose_offset(self, index: int) -> int:
        return self.strict_offsets[self.loose_to_strict[index]]


def skeleton(text: str) -> Skeleton:
    strict: list[str] = []
    offsets: list[int] = []
    loose: list[str] = []
    loose_to_strict: list[int] = []
    for offset, letter in _letters(text):
        if letter not in MATRES:
            loose.append(letter.translate(CONFUSION_FOLD))
            loose_to_strict.append(len(strict))
        strict.append(letter)
        offsets.append(offset)
    return Skeleton("".join(strict), tuple(offsets), "".join(loose), tuple(loose_to_strict))


def loose_key(text: str) -> str:
    return skeleton(text).loose


def strict_key(text: str) -> str:
    return skeleton(text).strict


def strip_marks(text: str) -> str:
    return "".join(char for char in text if char not in NIQQUD_POINTS and char not in CANTILLATION)


def niqqud_profile(text: str) -> dict[str, Any]:
    words = WORD.findall(text)
    pointed = sum(1 for word in words if any(char in NIQQUD_POINTS for char in word))
    marks = sum(1 for char in text if char in NIQQUD_POINTS)
    return {
        "niqqud_marks": marks,
        "words": len(words),
        "pointed_words": pointed,
        "pointed_word_share": round(pointed / len(words), 4) if words else 0.0,
    }


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- PBY catalogue ------------------------------------------------------------------------------------------


def load_catalogue(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["ID"]: dict(row) for row in csv.DictReader(handle)}


def catalogue_fields(row: dict[str, str]) -> dict[str, Any]:
    edition = (row.get("source_edition") or "").strip()
    year, basis = parse_publication_year(edition) if edition else (None, "none")
    return {
        "pby_id": row.get("ID"),
        "path": row.get("path"),
        "title": row.get("title"),
        "authors": row.get("authors"),
        "translators": row.get("translators") or None,
        "original_language": row.get("original_language") or None,
        "source_edition": edition or None,
        "source_edition_year": year,
        "source_edition_year_basis": basis,
        "read_url": f"https://benyehuda.org/read/{row.get('ID')}",
    }


def pby_text_path(row: dict[str, str]) -> str:
    """Release-relative path of the work's plain-text file (with niqqud where PBY has it)."""

    return f"txt{row['path']}.txt"


def pby_raw_url(row: dict[str, str], release: str = PBY_DEFAULT_RELEASE) -> str:
    return f"{PBY_RAW_BASE}/{release}/{pby_text_path(row)}"


PBY_TRAILER = re.compile(r"\s*את הטקסט\[ים\] לעיל הפיקו מתנדבי פרויקט בן־יהודה.*\Z", re.S)


def pby_body(text: str) -> str:
    """The PBY work text without the dump's volunteer credit trailer (kept verbatim otherwise)."""

    return PBY_TRAILER.sub("\n", text)


# --- edition matching ---------------------------------------------------------------------------------------


def _norm_terms(text: str | None) -> str:
    return " ".join(strip_marks(text or "").replace("־", " ").replace("-", " ").split())


def terms_present(text: str | None, terms: Sequence[str]) -> bool:
    """True when every term occurs in the text, compared on loose letter skeletons (spelling-tolerant)."""

    haystack = loose_key(_norm_terms(text))
    return all(loose_key(term) in haystack for term in terms)


def _search_url(query: str, api_key: str) -> str:
    params = {
        "query": query,
        "output_format": "json",
        "material_type": "book",
        "availability_type": "online_and_api_access",
        "api_key": api_key,
    }
    return f"{NLI_SEARCH_ENDPOINT}?{urlencode(params)}"


def _manifest_capture(manifest_url: str, fetch: Fetch) -> tuple[NliManifestCapture, dict[str, Any] | None]:
    status, body = fetch(manifest_url)
    manifest: dict[str, Any] | None = None
    if status == 200:
        try:
            parsed = json.loads(body.decode("utf-8"))
            manifest = parsed if isinstance(parsed, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            manifest = None
    capture = NliManifestCapture(
        manifest_url=manifest_url,
        http_status=status,
        canvas_count=len(manifest_canvases(manifest)) if manifest is not None else None,
        manifest=manifest,
        upstream_sha256=hashlib.sha256(body).hexdigest() if status == 200 else None,
    )
    return capture, manifest


def _metadata_value(manifest: dict[str, Any] | None, label: str) -> str | None:
    for entry in (manifest or {}).get("metadata") or []:
        if isinstance(entry, dict) and entry.get("label") == label:
            value = entry.get("value")
            if isinstance(value, list):
                value = "; ".join(str(item) for item in value)
            return str(value) if value is not None else None
    return None


def match_candidate(
    candidate: dict[str, Any],
    catalogue: dict[str, dict[str, str]],
    *,
    api_key: str,
    fetch: Fetch,
    max_manifest_checks: int = 4,
) -> dict[str, Any]:
    """Search NLI for one candidate edition and gate the kept hits on their manifest licence slug."""

    pby_rows = [catalogue[pby_id] for pby_id in candidate.get("pby_ids", []) if pby_id in catalogue]
    expected_year = candidate.get("expected_year")
    tolerance = int(candidate.get("year_tolerance", 2))
    title_terms = list(candidate.get("title_terms") or [])
    publisher_terms = list(candidate.get("publisher_terms") or [])
    result: dict[str, Any] = {
        "candidate_id": candidate["candidate_id"],
        "label": candidate.get("label"),
        "pby_works": [catalogue_fields(row) for row in pby_rows],
        "pby_works_in_edition": candidate.get("pby_works_in_edition"),
        "expected_year": expected_year,
        "year_tolerance": tolerance,
        "title_terms": title_terms,
        "publisher_terms": publisher_terms,
        "edition_notes": candidate.get("edition_notes"),
        "queries": [],
        "kept_hits": [],
    }
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for query in candidate.get("queries", []):
        status, body = fetch(_search_url(query, api_key))
        records: list[Any] = []
        if status == 200:
            try:
                parsed = json.loads(body.decode("utf-8"))
                records = parsed if isinstance(parsed, list) else []
            except (UnicodeDecodeError, json.JSONDecodeError):
                status = -1
        result["queries"].append({"query": query, "http_status": status, "records": len(records)})
        for record in records:
            if not isinstance(record, dict):
                continue
            hit = summarize_search_record(record)
            if not hit["record_id"] or hit["record_id"] in seen:
                continue
            seen.add(hit["record_id"])
            if hit["type"] != "book" or not hit["manifest_url"]:
                continue
            year, _ = parse_publication_year(hit["date"])
            hit["year"] = year
            year_ok = expected_year is None or (year is not None and abs(year - int(expected_year)) <= tolerance)
            title_ok = terms_present(hit["title"], title_terms)
            publisher_ok = terms_present(hit["publisher"], publisher_terms)
            if year_ok and title_ok and publisher_ok:
                kept.append(hit)
    for hit in kept[:max_manifest_checks]:
        capture, manifest = _manifest_capture(str(hit["manifest_url"]), fetch)
        decision = decide_nli_rights(display_rights=None, capture=capture)
        hit["manifest"] = {
            "http_status": capture.http_status,
            "canvas_count": capture.canvas_count,
            "license_slug": decision.license_slug,
            "decision": "accepted" if decision.accepted else "rejected",
            "reason": decision.reason,
            "upstream_sha256": capture.upstream_sha256,
            "label": (manifest or {}).get("label"),
            "publisher": _metadata_value(manifest, "Publisher"),
            "creation_date": _metadata_value(manifest, "Creation Date"),
            "format": _metadata_value(manifest, "Format"),
        }
        result["kept_hits"].append(hit)
    accepted = [hit for hit in result["kept_hits"] if hit["manifest"]["decision"] == "accepted"]
    if accepted:
        result["status"] = "matched"
        result["match"] = {
            "nli_record_id": accepted[0]["record_id"],
            "manifest_url": accepted[0]["manifest_url"],
            "item_url": accepted[0]["item_url"],
            "title": accepted[0]["title"],
            "publisher": accepted[0]["publisher"],
            "date": accepted[0]["date"],
            "canvas_count": accepted[0]["manifest"]["canvas_count"],
            "license_slug": accepted[0]["manifest"]["license_slug"],
        }
    else:
        result["status"] = "unmatched"
        result["reason"] = unmatched_reason(result)
    return result


def unmatched_reason(result: dict[str, Any]) -> str:
    if not any(query["http_status"] == 200 for query in result["queries"]):
        return "search_failed"
    hits = result["kept_hits"]
    if not hits:
        return "no_edition_hit"
    reasons = [hit["manifest"]["reason"] for hit in hits]
    if any(reason.startswith("nli_license_non_commercial") for reason in reasons):
        return "edition_scan_non_commercial"
    if any(reason == "nli_iiif_manifest_zero_canvases" for reason in reasons):
        return "edition_scan_zero_canvases"
    return "edition_scan_not_free_use"


def run_match(
    candidates: list[dict[str, Any]],
    catalogue: dict[str, dict[str, str]],
    *,
    api_key: str,
    fetch: Fetch,
    captured_on: str,
) -> dict[str, Any]:
    results = [match_candidate(candidate, catalogue, api_key=api_key, fetch=fetch) for candidate in candidates]
    statuses = Counter(result["status"] for result in results)
    reasons = Counter(result.get("reason") for result in results if result["status"] != "matched")
    return {
        "format": MATCH_FORMAT,
        "captured_on": captured_on,
        "pby_release": PBY_DEFAULT_RELEASE,
        "rights_gate": "hocrgen.fetchers.nli_iiif.decide_nli_rights (F8c, unchanged); only public-domain-free-use with canvases",
        "candidates": results,
        "summary": {
            "candidates": len(results),
            "matched": statuses.get("matched", 0),
            "match_rate": round(statuses.get("matched", 0) / len(results), 4) if results else 0.0,
            "unmatched_reasons": dict(sorted(reasons.items())),
        },
    }


# --- OCR (localization only) --------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class OcrLine:
    """One OCR line: geometry in canvas coordinates and its text, kept in memory only."""

    index: int
    bbox: tuple[int, int, int, int]  # x, y, w, h in canvas pixels
    text: str
    confidence: float | None = None  # mean Tesseract word confidence (0-100)

    @property
    def letters(self) -> int:
        return len(skeleton(self.text).strict)


def parse_tesseract_tsv(tsv: str, *, scale: float = 1.0) -> list[OcrLine]:
    """Group Tesseract TSV word rows into lines (block, paragraph, line order) with canvas-scaled boxes."""

    lines: dict[tuple[int, int, int], list[tuple[int, int, int, int, str, float]]] = {}
    order: list[tuple[int, int, int]] = []
    rows = tsv.splitlines()
    for row in rows[1:]:
        parts = row.split("\t")
        if len(parts) < 12 or parts[0] != "5":
            continue
        text = parts[11].strip()
        if not text:
            continue
        key = (int(parts[2]), int(parts[3]), int(parts[4]))
        if key not in lines:
            lines[key] = []
            order.append(key)
        left, top, width, height = (int(parts[index]) for index in range(6, 10))
        lines[key].append((left, top, width, height, text, float(parts[10])))
    result: list[OcrLine] = []
    for key in order:
        words = lines[key]
        x0 = min(word[0] for word in words)
        y0 = min(word[1] for word in words)
        x1 = max(word[0] + word[2] for word in words)
        y1 = max(word[1] + word[3] for word in words)
        bbox = (round(x0 * scale), round(y0 * scale), round((x1 - x0) * scale), round((y1 - y0) * scale))
        confidence = round(sum(word[5] for word in words) / len(words), 1)
        result.append(OcrLine(index=len(result), bbox=bbox, text=" ".join(word[4] for word in words), confidence=confidence))
    return result


def tesseract_version() -> str:  # pragma: no cover - operator path
    output = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, check=False)
    first = (output.stdout or output.stderr).splitlines()
    return first[0].strip() if first else "tesseract (unknown version)"


def run_tesseract(image_path: Path, *, lang: str = "heb", psm: int = 3) -> str:  # pragma: no cover - operator path
    completed = subprocess.run(
        ["tesseract", str(image_path), "-", "-l", lang, "--psm", str(psm), "tsv"],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout


# --- alignment ----------------------------------------------------------------------------------------------


def unique_grams(text: str, size: int) -> dict[str, int]:
    counts: Counter[str] = Counter(text[index : index + size] for index in range(len(text) - size + 1))
    return {
        text[index : index + size]: index
        for index in range(len(text) - size + 1)
        if counts[text[index : index + size]] == 1
    }


def longest_increasing_chain(pairs: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Longest chain of (ocr, pby) anchors increasing in both coordinates (pairs sorted by ocr position)."""

    tails: list[int] = []
    tail_index: list[int] = []
    previous: list[int] = [-1] * len(pairs)
    for index, (_, pby) in enumerate(pairs):
        position = bisect.bisect_left(tails, pby)
        if position == len(tails):
            tails.append(pby)
            tail_index.append(index)
        else:
            tails[position] = pby
            tail_index[position] = index
        previous[index] = tail_index[position - 1] if position > 0 else -1
    chain: list[tuple[int, int]] = []
    cursor = tail_index[-1] if tail_index else -1
    while cursor >= 0:
        chain.append(pairs[cursor])
        cursor = previous[cursor]
    chain.reverse()
    return chain


@dataclasses.dataclass
class LineAlignment:
    page: int
    line: OcrLine
    stream_start: int
    stream_end: int
    loose: str
    status: str = LINE_UNMATCHED
    score: float = 0.0
    strict_score: float = 0.0
    pby_start: int | None = None  # source offsets into the PBY text
    pby_end: int | None = None
    catchword: bool = False  # the line also carries the catchword (the next page's first word)


def _refine(line_loose: str, pby: Skeleton, start: int, end: int) -> tuple[float, int, int] | None:
    """Best local match of a line's loose skeleton inside pby.loose[start:end]; returns (score, start, end)."""

    start = max(0, start)
    end = min(len(pby.loose), end)
    if end - start < 2 or not line_loose:
        return None
    window = pby.loose[start:end]
    matcher = SequenceMatcher(None, line_loose, window, autojunk=False)
    blocks = [block for block in matcher.get_matching_blocks() if block.size > 0]
    if not blocks:
        return None
    core = [block for block in blocks if block.size >= 3] or blocks
    first, last = core[0], core[-1]
    span_start = start + first.b - first.a
    span_end = start + last.b + last.size + (len(line_loose) - last.a - last.size)
    span_start = max(start, span_start)
    span_end = min(end, max(span_end, span_start + 1))
    span = pby.loose[span_start:span_end]
    score = SequenceMatcher(None, line_loose, span, autojunk=False).ratio()
    return score, span_start, span_end


def _snap_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Extend a source span to whole words (and the punctuation attached to them)."""

    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def _span_from_loose(pby: Skeleton, text: str, start: int, end: int) -> tuple[int, int]:
    source_start = pby.loose_offset(start)
    source_end = pby.loose_offset(max(start, end - 1)) + 1
    return _snap_span(text, source_start, source_end)


def _strict_score(line: OcrLine, pby_text: str, start: int, end: int) -> float:
    return round(SequenceMatcher(None, strict_key(line.text), strict_key(pby_text[start:end]), autojunk=False).ratio(), 4)


def _estimate(stream_start: int, stream_end: int, chain: list[tuple[int, int]], chain_ocr: list[int]) -> tuple[int, int] | None:
    """Estimate a line's loose PBY window from the anchor chain (inside anchors, else interpolation)."""

    lo = bisect.bisect_left(chain_ocr, stream_start)
    hi = bisect.bisect_left(chain_ocr, stream_end)
    if hi > lo:
        first, last = chain[lo], chain[hi - 1]
        return first[1] - (first[0] - stream_start), last[1] + (stream_end - last[0])
    if not chain:
        return None
    if lo >= len(chain):
        # After the last anchor (the end of the aligned text): extrapolate one-to-one, only nearby.
        ocr0, pby0 = chain[-1]
        if stream_start - ocr0 > EXTRAPOLATION_LIMIT:
            return None
        return pby0 + (stream_start - ocr0), pby0 + (stream_end - ocr0)
    if lo == 0:
        ocr1, pby1 = chain[0]
        if ocr1 - stream_end > EXTRAPOLATION_LIMIT:
            return None
        return pby1 - (ocr1 - stream_start), pby1 - (ocr1 - stream_end)
    (ocr0, pby0), (ocr1, pby1) = chain[lo - 1], chain[lo]
    ocr_gap = ocr1 - ocr0
    pby_gap = pby1 - pby0
    if ocr_gap <= 0 or pby_gap < 0 or pby_gap > 2 * ocr_gap + 200:
        return None
    ratio = pby_gap / ocr_gap
    return pby0 + round((stream_start - ocr0) * ratio), pby0 + round((stream_end - ocr0) * ratio)


def align_pages(pby_text: str, pages: Sequence[Sequence[OcrLine]], *, gram_size: int = GRAM_SIZE) -> list[list[LineAlignment]]:
    """Order-preserving alignment of a PBY text to OCR lines of consecutive pages."""

    pby = skeleton(pby_text)
    stream_parts: list[str] = []
    alignments: list[list[LineAlignment]] = []
    cursor = 0
    for page_index, lines in enumerate(pages):
        page_lines: list[LineAlignment] = []
        for line in lines:
            loose = skeleton(line.text).loose
            page_lines.append(LineAlignment(page_index, line, cursor, cursor + len(loose), loose))
            stream_parts.append(loose)
            cursor += len(loose)
        alignments.append(page_lines)
    stream = "".join(stream_parts)
    pby_grams = unique_grams(pby.loose, gram_size)
    ocr_grams = unique_grams(stream, gram_size)
    pairs = sorted((ocr, pby_grams[gram]) for gram, ocr in ocr_grams.items() if gram in pby_grams)
    chain = longest_increasing_chain(pairs)
    chain_ocr = [ocr for ocr, _ in chain]
    chain_set = set(chain)
    off_chain = [(ocr, pby_pos) for ocr, pby_pos in pairs if (ocr, pby_pos) not in chain_set]
    off_ocr = [ocr for ocr, _ in off_chain]

    for page_lines in alignments:
        for entry in page_lines:
            if len(entry.loose) < MIN_LINE_LETTERS:
                continue
            estimate = _estimate(entry.stream_start, entry.stream_end, chain, chain_ocr)
            refined = None
            if estimate is not None:
                pad = max(20, len(entry.loose) // 3)
                refined = _refine(entry.loose, pby, estimate[0] - pad, estimate[1] + pad)
            if refined is not None and refined[0] >= LINE_MATCH_THRESHOLD:
                entry.status = LINE_MATCHED
            else:
                # Text that PBY carries elsewhere (footnotes moved to the end, headings): off-chain anchors.
                lo = bisect.bisect_left(off_ocr, entry.stream_start)
                hi = bisect.bisect_left(off_ocr, entry.stream_end)
                if hi - lo >= 2:
                    positions = sorted(pby_pos for _, pby_pos in off_chain[lo:hi])
                    middle = positions[len(positions) // 2]
                    relocated = _refine(entry.loose, pby, middle - 2 * len(entry.loose), middle + 2 * len(entry.loose))
                    if relocated is not None and relocated[0] >= LINE_MATCH_THRESHOLD:
                        refined = relocated
                        entry.status = LINE_RELOCATED
            if entry.status in (LINE_MATCHED, LINE_RELOCATED) and refined is not None:
                entry.score = round(refined[0], 4)
                entry.pby_start, entry.pby_end = _span_from_loose(pby, pby_text, refined[1], refined[2])
                entry.strict_score = _strict_score(entry.line, pby_text, entry.pby_start, entry.pby_end)
    _drop_out_of_order(alignments)
    _fill_short_lines(alignments, pby, pby_text)
    _mark_catchwords(alignments, pby_text)
    for page_lines in alignments:
        _classify_unmatched(page_lines)
    return alignments


def _drop_out_of_order(alignments: list[list[LineAlignment]]) -> None:
    """Demote matched lines whose PBY span runs backwards against their neighbours (order preservation)."""

    matched = [entry for page_lines in alignments for entry in page_lines if entry.status == LINE_MATCHED]
    if not matched:
        return
    starts = [(entry.pby_start or 0) for entry in matched]
    chain = longest_increasing_chain(sorted((index, start) for index, start in enumerate(starts)))
    keep = {index for index, _ in chain}
    for index, entry in enumerate(matched):
        if index not in keep:
            entry.status = LINE_UNMATCHED
            entry.score = 0.0
            entry.strict_score = 0.0
            entry.pby_start = entry.pby_end = None


def _classify_unmatched(page_lines: list[LineAlignment]) -> None:
    matched = [entry for entry in page_lines if entry.status == LINE_MATCHED]
    widths = [entry.line.bbox[2] for entry in matched] or [entry.line.bbox[2] for entry in page_lines] or [1]
    median_width = statistics.median(widths)
    first_matched_top = min((entry.line.bbox[1] for entry in matched), default=None)
    for entry in page_lines:
        if entry.status in (LINE_MATCHED, LINE_RELOCATED, LINE_CATCHWORD):
            continue
        text = "".join(entry.line.text.split())
        letters = len(skeleton(entry.line.text).strict)
        digits = sum(char.isdigit() for char in text)
        if letters < MIN_LINE_LETTERS or entry.line.bbox[2] < 0.1 * median_width:
            entry.status = LINE_PAGE_NUMBER if digits and letters <= 1 and len(text) <= 6 else LINE_NON_TEXT
        elif (
            first_matched_top is not None
            and entry.line.bbox[1] + entry.line.bbox[3] <= first_matched_top
            and (entry.line.bbox[2] < 0.8 * median_width or letters <= HEADER_MAX_LETTERS)
        ):
            entry.status = LINE_HEADER
        elif entry.line.confidence is not None and entry.line.confidence < NOISE_CONFIDENCE:
            entry.status = LINE_NOISE
        else:
            entry.status = LINE_UNMATCHED


def _mark_catchwords(alignments: list[list[LineAlignment]], pby_text: str) -> None:
    """Find the printed catchword: the next page's first word repeated at the foot of a page.

    A catchword OCR'd as its own short line is classed ``catchword``. One that Tesseract merged into the last
    text line makes that line's span run into the next page; the span is trimmed back and the line flagged.
    """

    for page_lines, next_lines in zip(alignments, alignments[1:]):
        next_starts = [entry.pby_start for entry in next_lines if entry.status == LINE_MATCHED and entry.pby_start is not None]
        if not next_starts:
            continue
        next_start = min(next_starts)
        for entry in reversed([entry for entry in page_lines if entry.status == LINE_MATCHED]):
            if entry.pby_start is None or entry.pby_end is None:
                break
            if entry.pby_start >= next_start - 1 and entry.line.letters <= CATCHWORD_MAX_LETTERS:
                entry.status = LINE_CATCHWORD
                continue
            if entry.pby_start < next_start < entry.pby_end:
                end = next_start
                while end > entry.pby_start and pby_text[end - 1].isspace():
                    end -= 1
                entry.pby_end = end
                entry.catchword = True
                entry.strict_score = _strict_score(entry.line, pby_text, entry.pby_start, entry.pby_end)
            break


def _fill_short_lines(alignments: list[list[LineAlignment]], pby: Skeleton, pby_text: str) -> None:
    """Locate short lines (a word or two ending a paragraph) in the PBY gap after the previous matched line."""

    for page_lines in alignments:
        for position, entry in enumerate(page_lines):
            if entry.status != LINE_UNMATCHED or not entry.loose or len(entry.loose) >= MIN_LINE_LETTERS:
                continue
            previous = next((item for item in reversed(page_lines[:position]) if item.status == LINE_MATCHED), None)
            following = next((item for item in page_lines[position + 1 :] if item.status == LINE_MATCHED), None)
            if previous is None or previous.pby_end is None:
                continue
            gap_start = bisect.bisect_left(pby.strict_offsets, previous.pby_end)
            loose_start = bisect.bisect_left(pby.loose_to_strict, gap_start)
            if following is not None and following.pby_start is not None:
                loose_end = bisect.bisect_left(pby.loose_to_strict, bisect.bisect_left(pby.strict_offsets, following.pby_start))
            else:
                loose_end = loose_start + 2 * len(entry.loose) + 2
            if loose_end <= loose_start or loose_end - loose_start > 3 * len(entry.loose) + 4:
                continue
            refined = _refine(entry.loose, pby, loose_start, loose_end)
            if refined is None or refined[0] < 0.66:
                continue
            entry.status = LINE_MATCHED
            entry.score = round(refined[0], 4)
            entry.pby_start, entry.pby_end = _span_from_loose(pby, pby_text, refined[1], refined[2])
            entry.strict_score = _strict_score(entry.line, pby_text, entry.pby_start, entry.pby_end)


# --- page records -------------------------------------------------------------------------------------------


def _union(boxes: Iterable[tuple[int, int, int, int]]) -> tuple[int, int, int, int] | None:
    boxes = list(boxes)
    if not boxes:
        return None
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[0] + box[2] for box in boxes)
    y1 = max(box[1] + box[3] for box in boxes)
    return x0, y0, x1 - x0, y1 - y0


def _intersects(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def crop_decision(page_lines: Sequence[LineAlignment], canvas_size: tuple[int, int]) -> dict[str, Any]:
    """Decision 12 crop: the located region, or a review flag when untranscribed text lies inside it.

    The crop box is the union of the located lines, padded by a fraction of the median line height and clipped
    to the canvas. Untranscribed lines (running headers, relocated footnotes, unmatched text) that intersect
    it make the page ``needs_review``; low-confidence OCR noise inside it is only listed.
    """

    matched = [entry for entry in page_lines if entry.status == LINE_MATCHED]
    if not matched:
        return {"status": CROP_NONE, "bbox": None, "method": CROP_METHOD, "reason": "no_located_text"}
    heights = [entry.line.bbox[3] for entry in matched]
    pad = round(CROP_PAD_LINE_FRACTION * statistics.median(heights))
    core = _union(entry.line.bbox for entry in matched)
    assert core is not None
    width, height = canvas_size
    x0 = max(0, core[0] - pad)
    y0 = max(0, core[1] - pad)
    x1 = min(width, core[0] + core[2] + pad)
    y1 = min(height, core[1] + core[3] + pad)
    untranscribed = [entry for entry in page_lines if entry.status in UNTRANSCRIBED_CLASSES]
    inside = [entry.line.index for entry in untranscribed if _intersects(entry.line.bbox, core)]
    inside += [entry.line.index for entry in matched if entry.catchword]
    # The padding never reaches into an untranscribed line outside the located core.
    for entry in untranscribed:
        lx, ly, lw, lh = entry.line.bbox
        if _intersects(entry.line.bbox, core):
            continue
        if ly + lh <= core[1]:
            y0 = max(y0, ly + lh)
        elif ly >= core[1] + core[3]:
            y1 = min(y1, ly)
        elif lx + lw <= core[0]:
            x0 = max(x0, lx + lw)
        elif lx >= core[0] + core[2]:
            x1 = min(x1, lx)
    bbox = (x0, y0, x1 - x0, y1 - y0)
    noise_inside = [entry.line.index for entry in page_lines if entry.status == LINE_NOISE and _intersects(entry.line.bbox, bbox)]
    if inside:
        return {
            "status": CROP_REVIEW,
            "bbox": list(bbox),
            "method": CROP_METHOD,
            "reason": "untranscribed_text_inside_located_region",
            "untranscribed_lines_inside": inside,
            "noise_lines_inside": noise_inside,
        }
    # Always crop to the located region: text Tesseract did not detect at all (a large title, an ornament
    # with letters) must not end up in the pair image when the PBY span does not cover it.
    classes = sorted({entry.status for entry in untranscribed})
    return {
        "status": CROP_CROPPED,
        "bbox": list(bbox),
        "method": CROP_METHOD,
        "reason": "page_carries_text_pby_lacks:" + ",".join(classes) if classes else "located_region",
        "noise_lines_inside": noise_inside,
    }


def _word_variants(ocr_texts: Sequence[str], pby_span: str) -> dict[str, int]:
    """Count aligned word pairs that differ only in matres lectionis (plene vs defective spelling)."""

    ocr_words = [strict_key(word) for text in ocr_texts for word in WORD.findall(text)]
    pby_words = [strict_key(word) for word in WORD.findall(pby_span)]
    ocr_words = [word for word in ocr_words if word]
    pby_words = [word for word in pby_words if word]
    matcher = SequenceMatcher(None, ocr_words, pby_words, autojunk=False)
    plene = 0
    equal = 0
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            equal += a1 - a0
        elif tag == "replace" and a1 - a0 == b1 - b0:
            for ocr_word, pby_word in zip(ocr_words[a0:a1], pby_words[b0:b1]):
                if ocr_word != pby_word and _drop_matres(ocr_word) == _drop_matres(pby_word):
                    plene += 1
    return {"words_equal": equal, "plene_spelling_variants": plene}


def _drop_matres(word: str) -> str:
    return "".join(char for char in word if char not in MATRES)


def page_record(
    page_lines: Sequence[LineAlignment],
    pby_text: str,
    *,
    canvas: dict[str, Any],
    canvas_index: int,
    gap_before: str | None,
) -> dict[str, Any]:
    matched = [entry for entry in page_lines if entry.status == LINE_MATCHED]
    textual = [entry for entry in page_lines if entry.status not in (LINE_NON_TEXT, LINE_PAGE_NUMBER, LINE_NOISE)]
    textual_letters = sum(entry.line.letters for entry in textual)
    matched_letters = sum(entry.line.letters for entry in matched)
    size = (int(canvas.get("width") or 0), int(canvas.get("height") or 0))
    if len(matched) >= MIN_PAGE_MATCHED_LINES:
        status = PAGE_ALIGNED
    elif matched:
        status = PAGE_WEAK
    else:
        status = PAGE_OUTSIDE
    record: dict[str, Any] = {
        "canvas_index": canvas_index,
        "canvas_id": canvas.get("@id"),
        "canvas_label": canvas.get("label"),
        "image_service": canvas_image_service(canvas),
        "canvas_size": list(size),
        "status": status,
    }
    if not matched:
        record.update({"alignment_score": None, "quality": None, "crop": crop_decision(page_lines, size), "lines": _line_records(page_lines)})
        return record
    start = min(entry.pby_start or 0 for entry in matched)
    end = max(entry.pby_end or 0 for entry in matched)
    span_text = pby_text[start:end]
    score = sum(entry.score * entry.line.letters for entry in matched) / max(1, matched_letters)
    strict = sum(entry.strict_score * entry.line.letters for entry in matched) / max(1, matched_letters)
    span_letters = len(skeleton(span_text).strict)
    located_letters = sum(len(skeleton(pby_text[entry.pby_start : entry.pby_end]).strict) for entry in matched if entry.pby_start is not None)
    classes = Counter(entry.status for entry in page_lines)
    differences = {
        "pby_niqqud": niqqud_profile(span_text),
        "print_niqqud": "not_measured_by_ocr",
        **_word_variants([entry.line.text for entry in matched], span_text),
        "pby_footnote_markers": len(PBY_FOOTNOTE_MARKER.findall(span_text)),
        "print_low_quotes": sum(len(PRINT_LOW_QUOTE.findall(entry.line.text)) for entry in matched),
        "pby_quote_marks": span_text.count('"') + span_text.count("״"),
        "running_header_lines": classes.get(LINE_HEADER, 0),
        "page_number_lines": classes.get(LINE_PAGE_NUMBER, 0),
        "relocated_lines": classes.get(LINE_RELOCATED, 0),
        "catchword_lines": classes.get(LINE_CATCHWORD, 0) + sum(1 for entry in matched if entry.catchword),
        "unmatched_text_lines": classes.get(LINE_UNMATCHED, 0),
        "low_confidence_noise_lines": classes.get(LINE_NOISE, 0),
        "pby_letters_in_span": span_letters,
        "pby_letters_not_located_in_span": max(0, span_letters - located_letters),
        "pby_letters_not_located_before_page": len(skeleton(gap_before or "").strict),
    }
    record.update(
        {
            "pby_span": {"start": start, "end": end},
            "text": span_text,
            "text_sha256": sha256_text(span_text),
            "alignment_score": round(score, 4),
            "strict_char_similarity": round(strict, 4),
            "line_coverage": round(matched_letters / textual_letters, 4) if textual_letters else 0.0,
            "quality": quality_bin(score) if status == PAGE_ALIGNED else "weak",
            "difference_classes": difference_classes(differences),
            "differences": differences,
            "crop": crop_decision(page_lines, size),
            "lines": _line_records(page_lines),
            **SILVER_STATUS,
        }
    )
    return record


def _line_records(page_lines: Sequence[LineAlignment]) -> list[dict[str, Any]]:
    records = []
    for entry in page_lines:
        item: dict[str, Any] = {
            "line": entry.line.index,
            "bbox": list(entry.line.bbox),
            "letters": entry.line.letters,
            "class": entry.status,
        }
        if entry.pby_start is not None:
            item.update({"pby_span": [entry.pby_start, entry.pby_end], "score": entry.score, "strict_char_similarity": entry.strict_score})
        if entry.catchword:
            item["carries_catchword"] = True
        records.append(item)
    return records


def quality_bin(score: float) -> str:
    for name, floor in QUALITY_BINS:
        if score >= floor:
            return name
    return QUALITY_BINS[-1][0]  # pragma: no cover - the last floor is 0


def difference_classes(differences: dict[str, Any]) -> list[str]:
    classes = []
    if differences["pby_niqqud"]["pointed_word_share"] >= 0.05:
        classes.append("pby_niqqud_present")
    if differences["plene_spelling_variants"]:
        classes.append("spelling_variant")
    if differences["pby_footnote_markers"] or differences["relocated_lines"]:
        classes.append("footnote_reformatted")
    if differences["print_low_quotes"]:
        classes.append("quote_style_normalized")
    if differences["running_header_lines"] or differences["page_number_lines"]:
        classes.append("running_header_or_page_number_omitted")
    if differences.get("catchword_lines"):
        classes.append("catchword_omitted")
    if differences["unmatched_text_lines"]:
        classes.append("print_text_not_in_pby_span")
    if differences["pby_letters_not_located_before_page"] >= 20 or differences["pby_letters_not_located_in_span"] >= 20:
        classes.append("pby_text_not_located_on_print")
    return classes


def build_page_records(
    alignments: Sequence[Sequence[LineAlignment]],
    pby_text: str,
    canvases: Sequence[dict[str, Any]],
    canvas_indices: Sequence[int],
) -> list[dict[str, Any]]:
    records = []
    previous_end: int | None = None
    for page_lines, canvas, canvas_index in zip(alignments, canvases, canvas_indices):
        matched = [entry for entry in page_lines if entry.status == LINE_MATCHED]
        gap = None
        overlap = 0
        if matched and previous_end is not None:
            start = min(entry.pby_start or 0 for entry in matched)
            gap = pby_text[previous_end:start] if start > previous_end else ""
            overlap = max(0, previous_end - start)
        record = page_record(page_lines, pby_text, canvas=canvas, canvas_index=canvas_index, gap_before=gap)
        if matched:
            record["differences"]["pby_chars_overlapping_previous_page"] = overlap
            if overlap:
                record["difference_classes"].append("span_overlaps_previous_page")
            previous_end = max(entry.pby_end or 0 for entry in matched)
        records.append(record)
    return records


def summarize_alignment(pages: Sequence[dict[str, Any]], pby_text: str) -> dict[str, Any]:
    aligned = [page for page in pages if page["status"] == PAGE_ALIGNED]
    statuses = Counter(page["status"] for page in pages)
    quality = Counter(page["quality"] for page in aligned)
    crops = Counter(page["crop"]["status"] for page in aligned)
    classes = Counter(name for page in aligned for name in page.get("difference_classes", []))
    scores = sorted(page["alignment_score"] for page in aligned)
    covered: list[tuple[int, int]] = []
    for start, end in sorted((page["pby_span"]["start"], page["pby_span"]["end"]) for page in aligned):
        if covered and start <= covered[-1][1]:
            covered[-1] = (covered[-1][0], max(covered[-1][1], end))
        else:
            covered.append((start, end))
    located = sum(len(skeleton(pby_text[start:end]).strict) for start, end in covered)
    total = len(skeleton(pby_text).strict)
    aligned_indices = [page["canvas_index"] for page in aligned]
    interior_missing = [
        page["canvas_index"]
        for page in pages
        if aligned_indices
        and page["status"] == PAGE_OUTSIDE
        and aligned_indices[0] < page["canvas_index"] < aligned_indices[-1]
        and sum(line["letters"] for line in page.get("lines", []) if line["class"] in UNTRANSCRIBED_CLASSES) >= INTERIOR_PAGE_MIN_LETTERS
    ]

    def percentile(fraction: float) -> float | None:
        if not scores:
            return None
        return scores[min(len(scores) - 1, int(fraction * (len(scores) - 1) + 0.5))]

    return {
        "pages": len(pages),
        "page_status": dict(sorted(statuses.items())),
        "aligned_pages": len(aligned),
        "quality": {name: quality.get(name, 0) for name, _ in QUALITY_BINS},
        "alignment_score": {"min": percentile(0.0), "p10": percentile(0.1), "median": percentile(0.5), "max": percentile(1.0)},
        "crop": dict(sorted(crops.items())),
        "difference_classes": dict(sorted(classes.items())),
        "pby_letters": total,
        "pby_letters_in_aligned_page_spans": located,
        "pby_text_coverage": round(located / total, 4) if total else 0.0,
        "interior_text_pages_not_in_pby": interior_missing,
        "plene_spelling_variants": sum(page["differences"]["plene_spelling_variants"] for page in aligned),
        "words_equal": sum(page["differences"]["words_equal"] for page in aligned),
    }


def alignment_report(
    *,
    work: dict[str, Any],
    scan: dict[str, Any],
    pby_text: str,
    pages: Sequence[Sequence[OcrLine]],
    canvases: Sequence[dict[str, Any]],
    canvas_indices: Sequence[int],
    ocr_engine: str,
    image_width: int | None,
    generated_on: str,
) -> dict[str, Any]:
    alignments = align_pages(pby_text, pages)
    records = build_page_records(alignments, pby_text, canvases, canvas_indices)
    return {
        "format": ALIGNMENT_FORMAT,
        "tool_version": TOOL_VERSION,
        "generated_on": generated_on,
        "work": {**work, "pby_text_sha256": sha256_text(pby_text), "pby_text_chars": len(pby_text), "pby_niqqud": niqqud_profile(pby_text)},
        "scan": scan,
        "method": {
            "ocr_engine": ocr_engine,
            "ocr_role": OCR_ROLE,
            "ocr_text_recorded": False,
            "image_width": image_width,
            "gram_size": GRAM_SIZE,
            "line_match_threshold": LINE_MATCH_THRESHOLD,
            "min_page_matched_lines": MIN_PAGE_MATCHED_LINES,
            "quality_bins": {name: floor for name, floor in QUALITY_BINS},
            "skeleton": "Hebrew and Latin letters only; final forms normalized; loose form drops matres lectionis (ו, י) and folds OCR-confusable letters",
            "coordinates": "canvas pixels (x, y, w, h)",
        },
        "status_defaults": dict(SILVER_STATUS),
        "pages": records,
        "summary": summarize_alignment(records, pby_text),
    }


# --- review report ------------------------------------------------------------------------------------------

LINE_COLOURS = {
    LINE_MATCHED: "#1a7f37",
    LINE_RELOCATED: "#8250df",
    LINE_HEADER: "#bf8700",
    LINE_PAGE_NUMBER: "#6e7781",
    LINE_NON_TEXT: "#6e7781",
    LINE_UNMATCHED: "#cf222e",
    LINE_NOISE: "#d4a72c",
    LINE_CATCHWORD: "#bf8700",
}


def render_report(report: dict[str, Any], *, image_src: Callable[[dict[str, Any]], str], pby_text: str) -> str:
    """Side-by-side HTML for a human verification pass: scan with line boxes and crop, PBY text per line."""

    work = report["work"]
    scan = report["scan"]
    summary = report["summary"]
    parts = [
        "<!doctype html><html lang='he'><head><meta charset='utf-8'>",
        f"<title>F8f review: {html.escape(str(work.get('title')))}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#fff;color:#1f2328}"
        ".page{display:flex;gap:16px;border-top:1px solid #d0d7de;padding:12px 0;flex-wrap:wrap}"
        ".scan{position:relative;flex:0 0 auto}.scan img{display:block;width:520px;height:auto}"
        ".scan svg{position:absolute;left:0;top:0;width:520px;height:100%}"
        ".text{flex:1 1 380px;direction:rtl;font-size:17px;line-height:1.55}"
        ".ln{display:flex;gap:8px}.ln b{direction:ltr;font-size:11px;color:#6e7781;min-width:2.5em}"
        ".meta{direction:ltr;font-size:12px;color:#57606a}.flag{color:#cf222e}"
        "table{border-collapse:collapse}td,th{border:1px solid #d0d7de;padding:2px 6px;font-size:12px}</style></head><body>",
        f"<h1>{html.escape(str(work.get('title')))} — {html.escape(str(work.get('authors')))}</h1>",
        "<p class='meta'>Operator-only review report (F8f). Silver pairs: "
        f"{html.escape(TEXT_PROVENANCE)}, {ADJUDICATION_STATUS}, reference_eligible=false. OCR was used for "
        "localization only; no OCR text is shown. Verify that the PBY text on the right is exactly the text in the "
        "crop box on the left.</p>",
        f"<p class='meta'>PBY {html.escape(str(work.get('pby_id')))}: {html.escape(str(work.get('source_edition')))} | "
        f"NLI {html.escape(str(scan.get('nli_record_id')))} ({html.escape(str(scan.get('license_slug')))})</p>",
        "<table><tr><th>aligned pages</th><th>quality</th><th>crop</th><th>difference classes</th></tr><tr>"
        f"<td>{summary['aligned_pages']} / {summary['pages']}</td><td>{html.escape(json.dumps(summary['quality']))}</td>"
        f"<td>{html.escape(json.dumps(summary['crop']))}</td><td>{html.escape(json.dumps(summary['difference_classes'], ensure_ascii=False))}</td></tr></table>",
    ]
    for page in report["pages"]:
        if page["status"] == PAGE_OUTSIDE:
            continue
        width, height = page["canvas_size"]
        boxes = []
        for line in page["lines"]:
            x, y, w, h = line["bbox"]
            colour = LINE_COLOURS.get(line["class"], "#6e7781")
            boxes.append(
                f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='none' stroke='{colour}' stroke-width='4'/>"
                f"<text x='{x + w + 6}' y='{y + h}' font-size='28' fill='{colour}'>{line['line']}</text>"
            )
        crop = page["crop"]
        if crop.get("bbox"):
            x, y, w, h = crop["bbox"]
            boxes.append(f"<rect x='{x}' y='{y}' width='{w}' height='{h}' fill='none' stroke='#0969da' stroke-width='6' stroke-dasharray='24 12'/>")
        rows = []
        for line in page["lines"]:
            if "pby_span" in line and line["class"] in (LINE_MATCHED, LINE_RELOCATED):
                start, end = line["pby_span"]
                rows.append(
                    f"<div class='ln'><b>{line['line']} · {line['score']:.2f}</b><span>{html.escape(pby_text[start:end])}</span></div>"
                )
            elif line["class"] in UNTRANSCRIBED_CLASSES:
                rows.append(f"<div class='ln'><b>{line['line']}</b><span class='flag'>[{html.escape(line['class'])}: not in PBY span]</span></div>")
        flags = ", ".join(page.get("difference_classes", []))
        parts.append(
            f"<section class='page' id='c{page['canvas_index']}'><div class='scan'><img loading='lazy' src='{html.escape(image_src(page))}' alt=''>"
            f"<svg viewBox='0 0 {width} {height}' preserveAspectRatio='none'>{''.join(boxes)}</svg></div>"
            f"<div class='text'><p class='meta'>canvas {page['canvas_index']} ({html.escape(str(page['canvas_label']))}) · "
            f"{page['status']} · score {page['alignment_score']} · {page['quality']} · crop {html.escape(crop['status'])} · {html.escape(flags)}</p>"
            f"{''.join(rows)}</div></section>"
        )
    parts.append("</body></html>")
    return "\n".join(parts)


# --- committed summary --------------------------------------------------------------------------------------


def compact_match(match_report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for candidate in match_report["candidates"]:
        hits = [
            {
                "nli_record_id": hit["record_id"],
                "date": hit["date"],
                "publisher": hit["publisher"],
                "license_slug": hit["manifest"]["license_slug"],
                "canvas_count": hit["manifest"]["canvas_count"],
                "decision": hit["manifest"]["decision"],
            }
            for hit in candidate["kept_hits"]
        ]
        rows.append(
            {
                "candidate_id": candidate["candidate_id"],
                "label": candidate["label"],
                "pby_ids": [work["pby_id"] for work in candidate["pby_works"]],
                "pby_source_edition": candidate["pby_works"][0]["source_edition"] if candidate["pby_works"] else None,
                "pby_works_in_edition": candidate.get("pby_works_in_edition"),
                "status": candidate["status"],
                "reason": candidate.get("reason"),
                "match": candidate.get("match"),
                "kept_hits": hits,
                "edition_notes": candidate.get("edition_notes"),
            }
        )
    return rows


def compact_alignment(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "pby_id": report["work"]["pby_id"],
        "title": report["work"]["title"],
        "nli_record_id": report["scan"]["nli_record_id"],
        "summary": report["summary"],
        "pages": [
            [
                page["canvas_index"],
                page["status"],
                page["alignment_score"],
                page["quality"],
                page["crop"]["status"],
                page.get("pby_span", {}).get("start"),
                page.get("pby_span", {}).get("end"),
                page.get("difference_classes", []),
            ]
            for page in report["pages"]
            if page["status"] != PAGE_OUTSIDE
        ],
        "page_columns": ["canvas_index", "status", "alignment_score", "quality", "crop", "pby_start", "pby_end", "difference_classes"],
    }


SUMMARY_FORMAT = "hocrgen.benyehuda_nli_pilot_summary.v1"


def pilot_summary(match_report: dict[str, Any], alignment_reports: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic committed summary: match rows, per-work alignment rows, and pooled page statistics."""

    works = [compact_alignment(report) for report in sorted(alignment_reports, key=lambda item: (item["scan"]["nli_record_id"], int(item["work"]["pby_id"])))]
    aligned = [page for report in alignment_reports for page in report["pages"] if page["status"] == PAGE_ALIGNED]
    quality = Counter(page["quality"] for page in aligned)
    crops = Counter(page["crop"]["status"] for page in aligned)
    classes = Counter(name for page in aligned for name in page.get("difference_classes", []))
    scores = sorted(page["alignment_score"] for page in aligned)
    histogram = Counter(min(99, int(score * 100)) // 2 * 2 for score in scores)
    return {
        "format": SUMMARY_FORMAT,
        "match": {"captured_on": match_report["captured_on"], "summary": match_report["summary"], "candidates": compact_match(match_report)},
        "alignment": {
            "works": len(alignment_reports),
            "scans": len({report["scan"]["nli_record_id"] for report in alignment_reports}),
            "aligned_pages": len(aligned),
            "quality": {name: quality.get(name, 0) for name, _ in QUALITY_BINS},
            "score_histogram_2pt": {f"{bucket / 100:.2f}": histogram[bucket] for bucket in sorted(histogram)},
            "crop": dict(sorted(crops.items())),
            "difference_classes": dict(sorted(classes.items())),
            "plene_spelling_variants": sum(page["differences"]["plene_spelling_variants"] for page in aligned),
            "words_equal": sum(page["differences"]["words_equal"] for page in aligned),
            "works_detail": works,
        },
    }


# --- fixture -------------------------------------------------------------------------------------------------

FIXTURE_IMAGE_WIDTH = 800
FIXTURE_CONTEXT_CHARS = 300


def fixture_alignment(fixture_dir: Path) -> dict[str, Any]:
    """Recompute a fixture's alignment from its pinned files (PBY excerpt, manifest capture, localization OCR)."""

    fixture = json.loads((fixture_dir / "fixture.json").read_text(encoding="utf-8"))
    capture = capture_from_payload(json.loads((fixture_dir / fixture["manifest_capture"]).read_text(encoding="utf-8")))
    canvases = {canvas["@id"]: canvas for canvas in manifest_canvases(capture.manifest or {})}
    pby_text = (fixture_dir / fixture["pby_excerpt"]["path"]).read_text(encoding="utf-8")
    pages: list[list[OcrLine]] = []
    page_canvases: list[dict[str, Any]] = []
    indices: list[int] = []
    for page in fixture["pages"]:
        canvas = canvases[page["canvas_id"]]
        tsv = (fixture_dir / page["localization_ocr"]).read_text(encoding="utf-8")
        pages.append(parse_tesseract_tsv(tsv, scale=int(canvas["width"]) / page["ocr_image_width"]))
        page_canvases.append(canvas)
        indices.append(page["canvas_index"])
    return alignment_report(
        work=fixture["work"],
        scan=fixture["scan"],
        pby_text=pby_text,
        pages=pages,
        canvases=page_canvases,
        canvas_indices=indices,
        ocr_engine=fixture["ocr_engine"],
        image_width=None,
        generated_on=fixture["generated_on"],
    )


def build_fixture(
    *,
    out_dir: Path,
    report: dict[str, Any],
    pby_text: str,
    manifest: dict[str, Any],
    manifest_sha256: str,
    work_dir: Path,
    canvas_indices: Sequence[int],
    captured_on: str,
) -> dict[str, Any]:  # pragma: no cover - operator path (reads the operator's image and OCR cache)
    """Write a small pinned fixture of a few aligned pages: images, PBY excerpt, capture and localization OCR."""

    by_index = {page["canvas_index"]: page for page in report["pages"]}
    chosen = [by_index[index] for index in canvas_indices]
    start = max(0, min(page["pby_span"]["start"] for page in chosen) - FIXTURE_CONTEXT_CHARS)
    end = min(len(pby_text), max(page["pby_span"]["end"] for page in chosen) + FIXTURE_CONTEXT_CHARS)
    start, end = _snap_span(pby_text, start, end)
    excerpt = pby_text[start:end]
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    (out_dir / "localization_ocr").mkdir(parents=True, exist_ok=True)
    (out_dir / "pby_excerpt.txt").write_text(excerpt, encoding="utf-8")
    canvases = manifest_canvases(manifest)
    selected = []
    pages = []
    for index in canvas_indices:
        canvas = canvases[index]
        asset = f"images/c{index:04d}.jpg"
        with Image.open(work_dir / "img" / f"c{index:04d}.jpg") as image:
            ocr_width = image.width
            height = round(image.height * FIXTURE_IMAGE_WIDTH / image.width)
            image.convert("L").resize((FIXTURE_IMAGE_WIDTH, height)).save(out_dir / asset, quality=75, optimize=True)
        shutil.copyfile(work_dir / "ocr" / f"c{index:04d}.tsv", out_dir / "localization_ocr" / f"c{index:04d}.tsv")
        selected.append({"asset": asset, "canvas_id": canvas["@id"], "index": index, "label": canvas.get("label"), "sha256": sha256_file(out_dir / asset)})
        pages.append(
            {
                "canvas_index": index,
                "canvas_id": canvas["@id"],
                "image": asset,
                "image_sha256": sha256_file(out_dir / asset),
                "localization_ocr": f"localization_ocr/c{index:04d}.tsv",
                "localization_ocr_sha256": sha256_file(out_dir / "localization_ocr" / f"c{index:04d}.tsv"),
                "ocr_image_width": ocr_width,
            }
        )
    capture = {
        "capture_format": NLI_CAPTURE_FORMAT,
        "captured_on": captured_on,
        "canvas_count": len(canvases),
        "http_status": 200,
        "manifest": trim_manifest(manifest, [page["canvas_id"] for page in pages]),
        "manifest_url": report["scan"]["manifest_url"],
        "selected_canvases": selected,
        "upstream_sha256": manifest_sha256,
    }
    (out_dir / "manifest_capture.json").write_text(json.dumps(capture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fixture = {
        "format": FIXTURE_FORMAT,
        "notes": (
            "Silver PBY-to-NLI page pairs (F8f). The localization_ocr TSV files are Tesseract output used only to "
            "locate PBY text on the page; they are never reference text. Images are grayscale, "
            f"{FIXTURE_IMAGE_WIDTH} px wide; boxes are in canvas pixels."
        ),
        "generated_on": report["generated_on"],
        "ocr_engine": report["method"]["ocr_engine"],
        "work": {key: value for key, value in report["work"].items() if key not in ("pby_text_sha256", "pby_text_chars", "pby_niqqud")},
        "scan": report["scan"],
        "pby_excerpt": {
            "path": "pby_excerpt.txt",
            "sha256": sha256_text(excerpt),
            "start_in_work_text": start,
            "end_in_work_text": end,
            "work_text_sha256": sha256_text(pby_text),
        },
        "manifest_capture": "manifest_capture.json",
        "manifest_capture_sha256": sha256_file(out_dir / "manifest_capture.json"),
        "pages": pages,
    }
    (out_dir / "fixture.json").write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    expected = fixture_alignment(out_dir)
    (out_dir / "expected_alignment.json").write_text(json.dumps(expected, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return expected


# --- operator CLI -------------------------------------------------------------------------------------------


def fetch_url(url: str, *, timeout: float = 90.0) -> FetchResult:  # pragma: no cover - live network path
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), b""
    except (URLError, TimeoutError, OSError):
        return 0, b""


def polite_fetch(delay: float, retries: int = 3) -> Fetch:  # pragma: no cover - live network path
    last: list[float] = [0.0]

    def fetch(url: str) -> FetchResult:
        status, body = 0, b""
        for attempt in range(retries + 1):
            wait = delay - (time.monotonic() - last[0])
            if wait > 0:
                time.sleep(wait)
            status, body = fetch_url(url)
            last[0] = time.monotonic()
            if status == 429:
                raise RuntimeError("upstream rate-limited the run (HTTP 429); stopping")
            if status not in (0, 500, 502, 503, 504, 520, 522, 524):
                break
            time.sleep(3 * (attempt + 1))
        return status, body

    return fetch


def _cmd_match(args: argparse.Namespace) -> int:  # pragma: no cover - operator path
    api_key = os.environ.get(NLI_API_KEY_ENV) or ""
    if not api_key:
        sys.stderr.write(f"{NLI_API_KEY_ENV} is not set; edition matching needs the NLI Search API.\n")
        return 2
    catalogue = load_catalogue(args.catalogue)
    candidates = json.loads(args.candidates.read_text(encoding="utf-8"))
    report = run_match(candidates, catalogue, api_key=api_key, fetch=polite_fetch(args.request_delay), captured_on=args.captured_on)
    text = redact(json.dumps(report, ensure_ascii=False, indent=1), api_key) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    summary = report["summary"]
    sys.stdout.write(f"{summary['matched']} / {summary['candidates']} candidates matched ({summary['match_rate']:.0%})\n")
    return 0


def _parse_range(text: str | None, count: int) -> list[int]:
    if not text:
        return list(range(count))
    start, _, end = text.partition(":")
    return list(range(int(start or 0), min(count, int(end) if end else count)))


def _cmd_align(args: argparse.Namespace) -> int:  # pragma: no cover - operator path
    catalogue = load_catalogue(args.catalogue)
    row = catalogue[args.pby_id]
    pby_text = pby_body(args.pby_text.read_text(encoding="utf-8"))
    manifest_bytes = args.manifest.read_bytes()
    manifest = json.loads(manifest_bytes)
    canvases = manifest_canvases(manifest)
    capture = NliManifestCapture(
        manifest_url=args.manifest_url,
        http_status=200,
        canvas_count=len(canvases),
        manifest=manifest,
        upstream_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    decision = decide_nli_rights(display_rights=None, capture=capture)
    if not decision.accepted:
        sys.stderr.write(f"scan rejected by the NLI gate: {decision.reason}\n")
        return 2
    indices = _parse_range(args.canvases, len(canvases))
    work_dir: Path = args.work_dir
    (work_dir / "img").mkdir(parents=True, exist_ok=True)
    (work_dir / "ocr").mkdir(parents=True, exist_ok=True)
    fetch = polite_fetch(args.request_delay)
    pages: list[list[OcrLine]] = []
    for index in indices:
        canvas = canvases[index]
        service = canvas_image_service(canvas)
        canvas_width = int(canvas.get("width") or args.image_width)
        image_path = work_dir / "img" / f"c{index:04d}.jpg"
        tsv_path = work_dir / "ocr" / f"c{index:04d}.tsv"
        if not image_path.exists():
            # The image server refuses upscaling (HTTP 403), and canvas sizes can differ from the image's.
            width = min(args.image_width, canvas_width)
            status, body = fetch(f"{service}/full/{width},/0/default.jpg")
            if status == 403:
                info_status, info_body = fetch(f"{service}/info.json")
                info_width = json.loads(info_body).get("width") if info_status == 200 else None
                if isinstance(info_width, int) and info_width < width:
                    status, body = fetch(f"{service}/full/{info_width},/0/default.jpg")
            if status != 200:
                sys.stderr.write(f"canvas {index}: image HTTP {status}; page left empty\n")
                pages.append([])
                continue
            image_path.write_bytes(body)
        if not tsv_path.exists():
            tsv_path.write_text(run_tesseract(image_path), encoding="utf-8")
        with Image.open(image_path) as image:
            scale = canvas_width / image.width
        pages.append(parse_tesseract_tsv(tsv_path.read_text(encoding="utf-8"), scale=scale))
        sys.stderr.write(f"\rOCR {index + 1}/{len(canvases)}")
    sys.stderr.write("\n")
    report = alignment_report(
        work={**catalogue_fields(row), "pby_release": args.pby_release, "pby_text_path": pby_text_path(row), "pby_text_url": pby_raw_url(row, args.pby_release)},
        scan={
            "nli_record_id": args.nli_record_id,
            "manifest_url": args.manifest_url,
            "manifest_upstream_sha256": capture.upstream_sha256,
            "canvas_count": len(canvases),
            "license_slug": decision.license_slug,
            "rights_decision": decision.evidence(),
            "label": manifest.get("label"),
            "attribution": capture.attribution,
        },
        pby_text=pby_text,
        pages=pages,
        canvases=[canvases[index] for index in indices],
        canvas_indices=indices,
        ocr_engine=f"{tesseract_version()} -l heb --psm 3",
        image_width=args.image_width,
        generated_on=args.generated_on,
    )
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "alignment.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    def image_src(page: dict[str, Any]) -> str:
        local = work_dir / "img" / f"c{page['canvas_index']:04d}.jpg"
        return os.path.relpath(local, out_dir) if local.exists() else f"{page['image_service']}/full/800,/0/default.jpg"

    (out_dir / "review.html").write_text(render_report(report, image_src=image_src, pby_text=pby_text), encoding="utf-8")
    summary = report["summary"]
    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=1) + "\n")
    return 0


def _cmd_fixture(args: argparse.Namespace) -> int:  # pragma: no cover - operator path
    report = json.loads(args.alignment.read_text(encoding="utf-8"))
    manifest_bytes = args.manifest.read_bytes()
    expected = build_fixture(
        out_dir=args.out_dir,
        report=report,
        pby_text=pby_body(args.pby_text.read_text(encoding="utf-8")),
        manifest=json.loads(manifest_bytes),
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        work_dir=args.work_dir,
        canvas_indices=[int(index) for index in args.canvases.split(",")],
        captured_on=args.captured_on,
    )
    sys.stdout.write(json.dumps(expected["summary"], ensure_ascii=False, indent=1) + "\n")
    return 0


def _flat(value: Any) -> bool:
    """A scalar, or a row: a list of scalars and lists of scalars (a page row, a span), written on one line.

    A list whose items are all lists (a table of rows) is not a row; each of its rows gets its own line.
    """

    if isinstance(value, dict):
        return False
    if not isinstance(value, list):
        return True
    if value and all(isinstance(item, list) for item in value):
        return False
    return all(not isinstance(item, (dict, list)) or (isinstance(item, list) and all(not isinstance(sub, (dict, list)) for sub in item)) for item in value)


def _dump(value: Any, depth: int) -> str:
    if _flat(value):
        return json.dumps(value, ensure_ascii=False)
    pad = " " * (depth + 1)
    if isinstance(value, dict):
        items = [f"{pad}{json.dumps(key, ensure_ascii=False)}: {_dump(item, depth + 1)}" for key, item in value.items()]
        return "{\n" + ",\n".join(items) + "\n" + " " * depth + "}" if items else "{}"
    items = [pad + _dump(item, depth + 1) for item in value]
    return "[\n" + ",\n".join(items) + "\n" + " " * depth + "]"


def summary_json(summary: dict[str, Any]) -> str:
    """Indented JSON with every list of scalars (a page row, a span) kept on one line."""

    return _dump(summary, 0) + "\n"


def _cmd_summarize(args: argparse.Namespace) -> int:  # pragma: no cover - operator path
    match_report = json.loads(args.match.read_text(encoding="utf-8"))
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.alignments]
    summary = pilot_summary(match_report, reports)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(summary_json(summary), encoding="utf-8")
    sys.stdout.write(json.dumps({key: value for key, value in summary["alignment"].items() if key != "works_detail"}, ensure_ascii=False, indent=1) + "\n")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator-only PBY-to-NLI edition matching and page alignment (F8f).")
    sub = parser.add_subparsers(dest="command", required=True)
    match = sub.add_parser("match", help="Match PBY candidate editions to NLI free-use scans.")
    match.add_argument("--candidates", type=Path, required=True)
    match.add_argument("--catalogue", type=Path, required=True)
    match.add_argument("--out", type=Path, required=True)
    match.add_argument("--captured-on", required=True)
    match.add_argument("--request-delay", type=float, default=1.5)
    align = sub.add_parser("align", help="OCR (localization only) and align one PBY work to its matched scan.")
    align.add_argument("--catalogue", type=Path, required=True)
    align.add_argument("--pby-id", required=True)
    align.add_argument("--pby-text", type=Path, required=True)
    align.add_argument("--pby-release", default=PBY_DEFAULT_RELEASE)
    align.add_argument("--manifest", type=Path, required=True, help="A saved copy of the IIIF manifest.")
    align.add_argument("--manifest-url", required=True)
    align.add_argument("--nli-record-id", required=True)
    align.add_argument("--canvases", help="Canvas index range start:end (default all).")
    align.add_argument("--image-width", type=int, default=1600)
    align.add_argument("--work-dir", type=Path, required=True)
    align.add_argument("--out-dir", type=Path, required=True)
    align.add_argument("--generated-on", required=True)
    align.add_argument("--request-delay", type=float, default=1.0)
    fixture = sub.add_parser("fixture", help="Write a small pinned fixture of aligned pages from an alignment run.")
    fixture.add_argument("--alignment", type=Path, required=True)
    fixture.add_argument("--pby-text", type=Path, required=True)
    fixture.add_argument("--manifest", type=Path, required=True)
    fixture.add_argument("--work-dir", type=Path, required=True)
    fixture.add_argument("--canvases", required=True, help="Comma-separated canvas indices.")
    fixture.add_argument("--out-dir", type=Path, required=True)
    fixture.add_argument("--captured-on", required=True)
    summarize = sub.add_parser("summarize", help="Write the committed pilot summary JSON from match and alignment reports.")
    summarize.add_argument("--match", type=Path, required=True)
    summarize.add_argument("--alignments", type=Path, nargs="+", required=True)
    summarize.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - operator path
    args = parse_args(argv)
    if shutil.which("tesseract") is None and args.command == "align":
        sys.stderr.write("tesseract is not installed; alignment needs it for localization.\n")
        return 2
    commands = {"match": _cmd_match, "align": _cmd_align, "fixture": _cmd_fixture, "summarize": _cmd_summarize}
    return commands[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
