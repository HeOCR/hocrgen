"""E2d6: single-line verification of real printed lines (operator-only).

A human looks at one printed line on a real scan next to a **candidate** transcription of that line, typed by a
different human, and either confirms it (``exact``) or corrects it (``edited``). The line can also be flagged
``unreadable`` or ``misaligned``. Verified lines become line-level evaluation references. The app side is
``HeOCR/heocr-review``; the two formats are fixed by the line verification contract (v1, 2026-11-07):
``line_verify_items.v1`` (the bundle this tool exports) and ``line_verify_decisions.v1`` (what the app exports and
this tool ingests).

Subcommands:

- ``export`` builds a bundle (``items.json`` and ``pages/<sha256>.<ext>``) from two sources:

  - **Hebrew Wikisource quality-3 pages** of a tranche snapshot (one named proofreader each; CC BY-SA 4.0). Every
    page is re-gated by the unchanged ``page_exclusion_reasons`` (so its Index is rights-admitted), must be quality
    3, and must not be a page of an ``--exclude-reference-manifest`` (the scored quality-4 pages).
  - **Project Ben-Yehuda texts aligned to NLI free-use scans** (F8f). Every scan is re-gated by the unchanged
    ``decide_nli_rights`` and only ``public-domain-free-use`` is accepted.

  Lines are localized with the F8f aligner (``benyehuda_nli_alignment.align_pages``) on cached Tesseract line boxes.
  **OCR is used only for geometry, the difficulty score and the attention spans: no OCR text is written anywhere.**
  Weakly aligned lines are dropped (``ELIGIBILITY``). Each line gets a difficulty (``difficulty``) and the batch is
  selected by ``select_items``: about 80% ``hard`` lines (highest difficulty) and 20% ``random`` lines (a seeded
  uniform sample of the eligible lines), with per-book and per-page caps, ranked so that a random line comes about
  every fifth line.
- ``ingest`` validates a decisions file against its bundle and writes the line references with full provenance
  (``line_verify_references.v1``, committed under ``docs/``) and, optionally, the operator line reference set.
- ``validate`` checks bundles, decisions and reference files; ``stats`` prints counts and histograms.

The attestation of a verified line is set in one place, ``ATTESTATION_POLICY`` (maintainer decision 2026-11-07,
"Yes, like quality 4": a line typed by one human and verified by a second counts as adjudicated).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import random
import re
import shutil
import statistics
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_audit import DEFAULT_MIN_REVIEWERS, REVIEWER_ID
from hocrgen.reference_rules import fix_space_before_punctuation
from hocrgen.tools import benyehuda_nli_alignment as aligner

ITEMS_SCHEMA = "line_verify_items.v1"
DECISIONS_SCHEMA = "line_verify_decisions.v1"
REFERENCES_SCHEMA = "line_verify_references.v1"
LINE_SET_SCHEMA = "line_verify_line_references.v1"
REPORT_SCHEMA = "line_verify_export_report.v1"
TOOL = "hocrgen.tools.line_verify"
DEFAULT_BATCH_ID = "line_verify_v1"

WIKISOURCE = "wikisource_he_proofread"
NLI_ALIGNED = "benyehuda_nli_aligned"
SOURCES = (WIKISOURCE, NLI_ALIGNED)
CANDIDATE_PROVENANCE = {WIKISOURCE: "wikisource_quality3_single_proofreader", NLI_ALIGNED: "pby_human_typed_aligned"}
TEXT_LICENSE = {WIKISOURCE: "CC BY-SA 4.0", NLI_ALIGNED: "public domain"}
NLI_ACCEPTED_SLUG = "public-domain-free-use"
RELEASE_SPLITS = ("train", "validation", "test")
STRATA = ("hard", "random")
DECISION_VALUES = ("exact", "edited", "unreadable", "misaligned")
VERIFIED_DECISIONS = ("exact", "edited")

# --- Attestation policy (maintainer decision 2026-11-07) ------------------------------------------------------
# "Yes, like quality 4" (Shay Palachy Affek): a line whose candidate was typed by one human (a Wikisource quality-3
# proofreader, or the PBY typist) and then verified by a different human in the app (``exact`` or ``edited``) is
# adjudicated, the same standard as Wikisource quality 4 (F8 decision 2). The one-line switch back to the
# conservative policy is ``ATTESTATION_POLICY = "single_human_verified"``.
ATTESTATION_POLICIES: dict[str, dict[str, Any]] = {
    "adjudicated": {
        "attestation_status": "typist_and_verifier_adjudicated",
        "adjudication_status": "adjudicated",
        "reference_eligible": True,
        "decision": "maintainer decision 2026-11-07 (planning/decisions/2026-11-07-line-verification-attestation.md)",
    },
    "single_human_verified": {
        "attestation_status": "single_human_verified",
        "adjudication_status": "not_adjudicated",
        "reference_eligible": False,
        "decision": "conservative fallback: one verifier is not adjudication",
    },
}
ATTESTATION_POLICY = "adjudicated"

# --- Line eligibility (documented in docs/e2d6_line_verification.md) -------------------------------------------
ELIGIBILITY: dict[str, float] = {
    # the aligner's per-line similarity on the loose letter skeleton (matched lines start at 0.70)
    "min_line_score": 0.80,
    # letter-weighted mean of the page's matched lines: a page that aligns badly is skipped whole
    "min_page_score": 0.85,
    # long, full lines: letters, and the box width against the page's median matched-line width
    "min_letters": 15,
    "min_width_ratio": 0.60,
    "max_width_ratio": 1.35,
    # a box much taller than the page's median line usually holds two lines
    "max_height_ratio": 1.60,
    # another OCR line box covering this share of the box's area means merged or duplicate geometry
    "max_box_overlap": 0.30,
}
# Footnote marks: Wikisource writes a printed mark as ``[n]``; PBY moves notes to the end and leaves ``[^n]`` or a
# number glued to the next word. Lines that carry one are left out of v1 (a convention the verifier cannot settle).
FOOTNOTE_MARK = re.compile(r"\[\^?\d+\]|(?<![\d\w])\d{1,3}(?=[א-ת])")

# --- Difficulty -----------------------------------------------------------------------------------------------
DIFFICULTY_WEIGHTS = {"ocr_disagreement": 0.60, "ocr_low_confidence": 0.20, "niqqud": 0.10, "small_type": 0.10}
# Tesseract (cached for every page) is the base reading. Other engines with cached line readings (R3h + R4d + A1,
# for the E2d diagnostic pages only) enter page-centred: their disagreement minus its median over the page's
# eligible lines, times this weight. They sit near CER 0.9 on real print and cover few pages, so an absolute term
# would lift every line of those pages up the hard ranking; the centred term only reorders lines within a page.
SECONDARY_ENGINE_WEIGHT = 0.2
SMALL_TYPE_HEIGHT_RATIO = 0.75

# --- Selection ------------------------------------------------------------------------------------------------
SELECTION: dict[str, float] = {
    "size": 1500,
    "random_share": 0.20,
    "book_cap_share": 0.10,  # no book above 10% of the batch, and of the random stratum
    "hard_page_cap": 8,  # hard lines per page, so one bad page does not fill the queue
    "random_every": 5,  # rank: one random line, then four hard ones
}
BOX_PAD_LINE_FRACTION = 0.12
CONTEXT_LINE_FRACTION = 1.2
CONTEXT_X_FRACTION = 0.02
NIQQUD_AND_MARKS = frozenset(chr(code) for code in range(0x0591, 0x05C8) if chr(code) not in "־׀׃׆")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ITEM_ID = re.compile(r"^(?P<page>.+)#L(?P<line>\d{3,})$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


# --- Candidate text, disagreement and attention spans ----------------------------------------------------------


def candidate_text(raw: str) -> str:
    """The human text of a line as the bundle carries it: NFC, one space between words, then the hocrgen reference
    rule ``fix_space_before_punctuation``."""

    text = " ".join(unicodedata.normalize("NFC", raw).split())
    return fix_space_before_punctuation(text)[0]


def _comparable(text: str) -> tuple[str, list[int]]:
    """The text without niqqud and cantillation (OCR does not read them), with each kept character's offset."""

    chars, offsets = [], []
    for offset, char in enumerate(unicodedata.normalize("NFC", text)):
        if char in NIQQUD_AND_MARKS:
            continue
        chars.append(char)
        offsets.append(offset)
    return "".join(chars), offsets


def _word_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    while end < len(text) and not text[end].isspace():
        end += 1
    return start, end


def disagreement(candidate: str, ocr_text: str) -> tuple[float, list[list[int]]]:
    """How far an engine's reading of a line is from the candidate, and where.

    Both sides lose niqqud and cantillation and their spacing is collapsed. The score is the share of candidate
    characters the edit script touches (``difflib`` opcodes, capped at 1). The spans are the candidate's words that
    contain a disagreement, as ``[start, end)`` offsets into ``candidate``, merged. The OCR text is never returned.
    """

    cand, offsets = _comparable(candidate)
    ocr = " ".join(_comparable(ocr_text)[0].split())
    if not cand:
        return 0.0, []
    matcher = SequenceMatcher(None, cand, ocr, autojunk=False)
    edits = 0
    raw_spans: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if not cand[i1:i2].strip() and not ocr[j1:j2].strip():
            continue  # a space more or less is layout, not a reading
        edits += max(i2 - i1, j2 - j1)
        if cand[i1:i2].strip():
            start, end = offsets[i1], offsets[i2 - 1] + 1
            while candidate[start].isspace():  # the edit's own spaces do not reach into the neighbouring word
                start += 1
            while candidate[end - 1].isspace():
                end -= 1
        else:  # an insertion on the OCR side (or a space it replaced), at a position in the candidate
            position = offsets[i1] if i1 < len(offsets) else len(candidate)
            start, end = max(0, position - 1), min(len(candidate), position + 1)
        raw_spans.append(_word_bounds(candidate, start, end))
    spans: list[list[int]] = []
    for start, end in sorted(raw_spans):
        while start < end and candidate[start].isspace():
            start += 1
        while end > start and candidate[end - 1].isspace():
            end -= 1
        if start >= end:
            continue
        if spans and start <= spans[-1][1] + 1:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return round(min(1.0, edits / len(cand)), 4), spans


def niqqud_share(text: str) -> float:
    letters = [char for char in text if "א" <= char <= "ת"]
    if not letters:
        return 0.0
    pointed = sum(1 for index, char in enumerate(text) if "א" <= char <= "ת" and index + 1 < len(text)
                  and text[index + 1] in NIQQUD_AND_MARKS)
    return round(pointed / len(letters), 4)


def difficulty(tesseract: float, *, secondary: Mapping[str, float] | None = None, confidence: float | None,
               niqqud: float, small_type: bool) -> tuple[float, dict[str, float]]:
    """``difficulty`` in [0, 1] and its components (docs/e2d6_line_verification.md, "Difficulty").

    ``ocr_disagreement`` is Tesseract's disagreement with the candidate plus ``SECONDARY_ENGINE_WEIGHT`` times the mean
    of the other engines' page-centred disagreements (``secondary``), clipped to [0, 1]; ``ocr_low_confidence`` is
    1 - the line's mean Tesseract word confidence / 100; ``niqqud`` is the share of the candidate's letters that carry
    points; ``small_type`` is 1 when the box is under ``SMALL_TYPE_HEIGHT_RATIO`` of the page's median line height."""

    centred = statistics.mean(secondary.values()) if secondary else 0.0
    ocr = max(0.0, min(1.0, tesseract + SECONDARY_ENGINE_WEIGHT * centred))
    components = {
        "ocr_disagreement": round(ocr, 4),
        "ocr_low_confidence": round(max(0.0, min(1.0, 1 - (confidence if confidence is not None else 100.0) / 100)), 4),
        "niqqud": round(niqqud, 4),
        "small_type": 1.0 if small_type else 0.0,
    }
    score = sum(DIFFICULTY_WEIGHTS[name] * value for name, value in components.items())
    return round(max(0.0, min(1.0, score)), 4), components


# --- Page inputs and line candidates ---------------------------------------------------------------------------


@dataclass
class PageInput:
    """One page: its metadata as the bundle ships it, its image, and its localization inputs (kept in memory)."""

    page_id: str
    source: str
    book_id: str
    book_title: str
    page_label: str
    image_path: Path
    attribution: str
    release_split: str | None
    size: tuple[int, int]
    ocr_lines: list[aligner.OcrLine] = field(default_factory=list)
    # other engines' line readings in this page's pixels: engine -> [((x0, y0, x1, y1), text)]
    engine_lines: dict[str, list[tuple[tuple[float, float, float, float], str]]] = field(default_factory=dict)
    excluded_ranges: list[tuple[int, int]] = field(default_factory=list)  # text offsets the scan does not show


@dataclass
class LineCandidate:
    page_id: str
    source: str
    book_id: str
    line_index: int
    box: list[int]
    context_box: list[int]
    candidate_text: str
    alignment_score: float
    attention_spans: list[list[int]]
    difficulty: float
    components: dict[str, float]
    engines: dict[str, float]
    letters: int

    @property
    def item_id(self) -> str:
        return f"{self.page_id}#L{self.line_index:03d}"


def _box_overlap_share(box: tuple[int, int, int, int], other: tuple[int, int, int, int]) -> float:
    x0, y0 = max(box[0], other[0]), max(box[1], other[1])
    x1, y1 = min(box[0] + box[2], other[0] + other[2]), min(box[1] + box[3], other[1] + other[3])
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0) / max(1, box[2] * box[3])


def _engine_reading(box: tuple[int, int, int, int], lines: Sequence[tuple[tuple[float, float, float, float], str]]) -> str | None:
    """The engine lines that sit on this box (centre inside the box's rows, mostly inside its columns), right to left."""

    x0, y0, x1, y1 = box[0], box[1], box[0] + box[2], box[1] + box[3]
    picked = []
    for (lx0, ly0, lx1, ly1), text in lines:
        centre = (ly0 + ly1) / 2
        overlap = max(0.0, min(x1, lx1) - max(x0, lx0))
        if y0 <= centre <= y1 and overlap >= 0.5 * max(1.0, lx1 - lx0):
            picked.append((lx1, text))
    if not picked:
        return None
    return " ".join(text for _, text in sorted(picked, key=lambda item: -item[0]))


def _letters(text: str) -> int:
    return len(aligner.skeleton(text).strict)


def page_lines_candidates(
    page: PageInput,
    page_lines: Sequence[aligner.LineAlignment],
    text: str,
    neighbours: Mapping[int, tuple[int | None, int | None]],
    rejected: Counter[str],
) -> list[LineCandidate]:
    """The eligible lines of one aligned page (``ELIGIBILITY``), each with its candidate text, difficulty and spans.

    ``neighbours`` maps a line index to the text offsets that bound it in reading order: the previous located
    line's end and the next one's start (``None`` at the text's start or end, where the text boundary is used).
    A line is eligible only when its span tiles with them: no letters of the text are left between them, and the
    spans do not overlap. That catches a box whose candidate gained or lost a word at either end.
    """

    matched = [entry for entry in page_lines if entry.status == aligner.LINE_MATCHED]
    if not matched:
        return []
    letters_total = sum(entry.line.letters for entry in matched)
    page_score = sum(entry.score * entry.line.letters for entry in matched) / max(1, letters_total)
    if page_score < ELIGIBILITY["min_page_score"]:
        rejected["page_alignment_weak"] += len(matched)
        return []
    median_height = statistics.median(entry.line.bbox[3] for entry in matched)
    median_width = statistics.median(entry.line.bbox[2] for entry in matched)
    width, height = page.size
    out = []
    for entry in matched:
        line = entry.line
        start, end = entry.pby_start, entry.pby_end
        assert start is not None and end is not None
        raw = text[start:end]
        before, after = neighbours.get(line.index, (None, None))
        before_text = text[before:start] if before is not None and before <= start else ("" if before is not None else text[:start])
        after_text = text[end:after] if after is not None and end <= after else ("" if after is not None else text[end:])
        overlapping = (before is not None and before > start) or (after is not None and after < end)
        reason = None
        if entry.score < ELIGIBILITY["min_line_score"]:
            reason = "line_alignment_weak"
        elif entry.catchword:
            reason = "carries_catchword"
        elif overlapping or _letters(before_text) or _letters(after_text):
            reason = "span_does_not_tile_with_neighbours"
        elif "\n" in raw.strip():
            reason = "span_crosses_paragraph"
        elif FOOTNOTE_MARK.search(raw):
            reason = "footnote_mark"
        elif any(start < ex_end and ex_start < end for ex_start, ex_end in page.excluded_ranges):
            reason = "excluded_span_on_scan"
        elif line.letters < ELIGIBILITY["min_letters"]:
            reason = "short_line"
        elif not ELIGIBILITY["min_width_ratio"] <= line.bbox[2] / median_width <= ELIGIBILITY["max_width_ratio"]:
            reason = "not_a_full_line"
        elif line.bbox[3] / median_height > ELIGIBILITY["max_height_ratio"]:
            reason = "box_taller_than_a_line"
        elif any(other.line.index != line.index and _box_overlap_share(line.bbox, other.line.bbox) > ELIGIBILITY["max_box_overlap"]
                 for other in page_lines):
            reason = "box_overlaps_another_line"
        if reason:
            rejected[reason] += 1
            continue
        cand = candidate_text(raw)
        tesseract_score, spans = disagreement(cand, line.text)
        engines = {"tesseract": tesseract_score}
        for name, readings in sorted(page.engine_lines.items()):
            reading = _engine_reading(line.bbox, readings)
            if reading is not None:
                engines[name] = disagreement(cand, reading)[0]
        small = line.bbox[3] < SMALL_TYPE_HEIGHT_RATIO * median_height
        x, y, w, h = line.bbox
        pad = max(2, round(BOX_PAD_LINE_FRACTION * h))
        box = [max(0, x - pad), max(0, y - pad), min(width, x + w + pad), min(height, y + h + pad)]
        band = round(CONTEXT_LINE_FRACTION * median_height)
        margin = round(CONTEXT_X_FRACTION * width)
        context = [max(0, box[0] - margin), max(0, box[1] - band), min(width, box[2] + margin), min(height, box[3] + band)]
        out.append(LineCandidate(page.page_id, page.source, page.book_id, line.index, box, context, cand,
                                 round(entry.score, 4), spans, 0.0, {"_confidence": line.confidence or 0.0,
                                                                     "_niqqud": niqqud_share(cand), "_small": float(small)},
                                 engines, line.letters))
    medians = {name: statistics.median(item.engines[name] for item in out if name in item.engines)
               for name in {name for item in out for name in item.engines if name != "tesseract"}}
    for item in out:
        secondary = {name: item.engines[name] - medians[name] for name in item.engines if name != "tesseract"}
        hints = item.components
        item.difficulty, item.components = difficulty(item.engines["tesseract"], secondary=secondary,
                                                      confidence=hints["_confidence"], niqqud=hints["_niqqud"],
                                                      small_type=bool(hints["_small"]))
    return out


def neighbour_bounds(alignments: Iterable[Sequence[aligner.LineAlignment]]) -> dict[tuple[int, int], tuple[int | None, int | None]]:
    """For every located line, the end of the previous and the start of the next located line in text order."""

    located = sorted(
        ((entry.pby_start, entry.pby_end, page_index, entry.line.index)
         for page_index, page_lines in enumerate(alignments) for entry in page_lines
         if entry.status == aligner.LINE_MATCHED and entry.pby_start is not None),
    )
    bounds = {}
    for position, (_, _, page_index, line_index) in enumerate(located):
        previous_end = located[position - 1][1] if position > 0 else None
        next_start = located[position + 1][0] if position + 1 < len(located) else None
        bounds[(page_index, line_index)] = (previous_end, next_start)
    return bounds


def aligned_candidates(text: str, pages: Sequence[PageInput], rejected: Counter[str], *,
                       text_bounded: bool) -> dict[str, list[LineCandidate]]:
    """Align one human text to its pages' OCR lines and return each page's eligible lines.

    ``text_bounded``: the text is exactly the pages' content (a Wikisource page), so the first and last lines must
    also tile with the text's start and end. A PBY work starts and ends with text that is not on the scan (titles),
    so there the outermost lines are bounded by the text edges only when a neighbour exists.
    """

    alignments = aligner.align_pages(text, [page.ocr_lines for page in pages])
    bounds = neighbour_bounds(alignments)
    out = {}
    for page_index, (page, page_lines) in enumerate(zip(pages, alignments)):
        neighbours = {}
        for entry in page_lines:
            if (page_index, entry.line.index) not in bounds:
                continue
            before, after = bounds[(page_index, entry.line.index)]
            if not text_bounded:
                before = entry.pby_start if before is None else before
                after = entry.pby_end if after is None else after
            neighbours[entry.line.index] = (before, after)
        out[page.page_id] = page_lines_candidates(page, page_lines, text, neighbours, rejected)
    return out


# --- Selection ------------------------------------------------------------------------------------------------


def _tiebreak(seed: str, item_id: str) -> str:
    return sha256_text(f"{seed}:{item_id}")


def select_items(candidates: Sequence[LineCandidate], *, seed: str, size: int | None = None,
                 book_cap_share: float | None = None) -> list[tuple[LineCandidate, str]]:
    """Pick the batch and rank it; deterministic given the candidates and the seed.

    1. ``random``: ``random_share`` of the batch, a uniform sample (``random.Random(seed)`` over the eligible lines
       sorted by item id) with at most ``book_cap_share`` of the random stratum from one book.
    2. ``hard``: the rest, by difficulty (ties by a seeded hash), with at most ``hard_page_cap`` lines per page and
       at most ``book_cap_share`` of the whole batch per book (random lines included).
    3. Rank: hard lines in difficulty order, with one random line (in sample order) at every ``random_every``-th
       place, starting at rank 1 with a hard line; whichever runs out first leaves the rest of the other.
    """

    size = int(size if size is not None else SELECTION["size"])
    pool = sorted(candidates, key=lambda item: item.item_id)
    n_random = round(size * SELECTION["random_share"])
    share = SELECTION["book_cap_share"] if book_cap_share is None else book_cap_share
    book_cap = max(1, int(size * share))
    random_book_cap = max(1, int(n_random * share))
    rng = random.Random(seed)
    order = list(range(len(pool)))
    rng.shuffle(order)
    books: Counter[str] = Counter()
    random_books: Counter[str] = Counter()
    chosen: set[str] = set()
    random_items = []
    for index in order:
        if len(random_items) >= n_random:
            break
        item = pool[index]
        if random_books[item.book_id] >= random_book_cap:
            continue
        random_books[item.book_id] += 1
        books[item.book_id] += 1
        chosen.add(item.item_id)
        random_items.append(item)
    pages: Counter[str] = Counter()
    hard_items = []
    for item in sorted(pool, key=lambda item: (-item.difficulty, _tiebreak(seed, item.item_id))):
        if len(hard_items) + len(random_items) >= size:
            break
        if item.item_id in chosen or books[item.book_id] >= book_cap or pages[item.page_id] >= SELECTION["hard_page_cap"]:
            continue
        books[item.book_id] += 1
        pages[item.page_id] += 1
        chosen.add(item.item_id)
        hard_items.append(item)
    ranked: list[tuple[LineCandidate, str]] = []
    every = int(SELECTION["random_every"])
    hard_iter, random_iter = iter(hard_items), iter(random_items)
    while len(ranked) < len(hard_items) + len(random_items):
        want_random = (len(ranked) + 1) % every == 0
        stream = (random_iter, "random") if want_random else (hard_iter, "hard")
        other = (hard_iter, "hard") if want_random else (random_iter, "random")
        item = next(stream[0], None)
        if item is not None:
            ranked.append((item, stream[1]))
            continue
        item = next(other[0], None)
        if item is None:  # pragma: no cover - both exhausted is the loop condition
            break
        ranked.append((item, other[1]))
    return ranked


# --- Bundle ---------------------------------------------------------------------------------------------------


def build_bundle(pages: Mapping[str, PageInput], ranked: Sequence[tuple[LineCandidate, str]], *, batch_id: str,
                 created_at: str, generator_ref: str, description: str) -> tuple[dict[str, Any], dict[str, Path]]:
    """``items.json`` and the page images to copy (bundle path -> source path); only pages with items are shipped."""

    used = sorted({item.page_id for item, _ in ranked})
    page_records, copies = [], {}
    for page_id in used:
        page = pages[page_id]
        data = page.image_path.read_bytes()
        digest = sha256_bytes(data)
        relative = f"pages/{digest}{page.image_path.suffix.lower()}"
        copies[relative] = page.image_path
        page_records.append({
            "page_id": page.page_id, "image": relative, "sha256": digest, "width": page.size[0], "height": page.size[1],
            "source": page.source, "book_id": page.book_id, "book_title": page.book_title, "page_label": page.page_label,
            "text_license": TEXT_LICENSE[page.source], "attribution": page.attribution, "release_split": page.release_split,
        })
    items = []
    for rank, (item, stratum) in enumerate(ranked, start=1):
        items.append({
            "item_id": item.item_id, "page_id": item.page_id, "line_index": item.line_index, "box": item.box,
            "context_box": item.context_box, "candidate_text": item.candidate_text,
            "candidate_provenance": CANDIDATE_PROVENANCE[item.source], "alignment_score": item.alignment_score,
            "attention_spans": item.attention_spans, "difficulty": item.difficulty, "stratum": stratum, "rank": rank,
        })
    bundle = {"schema_version": ITEMS_SCHEMA, "batch_id": batch_id, "description": description, "created_at": created_at,
              "generator": {"tool": TOOL, "ref": generator_ref}, "pages": page_records, "items": items}
    return bundle, copies


def write_bundle(out: Path, bundle: Mapping[str, Any], copies: Mapping[str, Path]) -> None:
    """Write ``items.json`` and ``pages/``; a re-export with the same batch id replaces the bundle in place."""

    if out.exists():
        existing = out / "items.json"
        if existing.exists() and json.loads(existing.read_text(encoding="utf-8")).get("batch_id") != bundle["batch_id"]:
            raise StageExecutionError(f"{out.name} holds another batch; use a new directory")
        if (out / "pages").exists():
            shutil.rmtree(out / "pages")
    (out / "pages").mkdir(parents=True, exist_ok=True)
    for relative, source in sorted(copies.items()):
        shutil.copyfile(source, out / relative)
    (out / "items.json").write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _histogram(values: Iterable[float], bins: int = 10) -> dict[str, int]:
    counts = Counter(min(bins - 1, int(value * bins)) for value in values)
    return {f"{index / bins:.1f}-{(index + 1) / bins:.1f}": counts.get(index, 0) for index in range(bins)}


def bundle_stats(bundle: Mapping[str, Any]) -> dict[str, Any]:
    pages = {page["page_id"]: page for page in bundle["pages"]}
    items = bundle["items"]

    def by(key: Any) -> dict[str, int]:
        return dict(sorted(Counter(str(key(item)) for item in items).items()))

    per_book = Counter(pages[item["page_id"]]["book_id"] for item in items)
    return {
        "batch_id": bundle["batch_id"],
        "items": len(items),
        "pages": len(pages),
        "books": len(per_book),
        "by_source": by(lambda item: pages[item["page_id"]]["source"]),
        "by_stratum": by(lambda item: item["stratum"]),
        "by_release_split": by(lambda item: pages[item["page_id"]]["release_split"]),
        "by_source_and_stratum": by(lambda item: f"{pages[item['page_id']]['source']}/{item['stratum']}"),
        "by_book": dict(sorted(per_book.items(), key=lambda pair: (-pair[1], pair[0]))),
        "max_book_share": round(max(per_book.values()) / len(items), 4) if items else 0.0,
        "difficulty_histogram": _histogram(item["difficulty"] for item in items),
        "difficulty_histogram_by_stratum": {stratum: _histogram(item["difficulty"] for item in items if item["stratum"] == stratum)
                                            for stratum in STRATA},
        "alignment_score_histogram": _histogram(item["alignment_score"] for item in items),
        "items_with_attention_spans": sum(1 for item in items if item["attention_spans"]),
        "candidate_characters": sum(len(item["candidate_text"]) for item in items),
    }


# --- Validation -----------------------------------------------------------------------------------------------


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_box(value: Any) -> bool:
    return isinstance(value, list) and len(value) == 4 and all(_is_int(v) for v in value) and value[0] < value[2] and value[1] < value[3]


def _is_date(value: Any) -> bool:
    if not (isinstance(value, str) and _DATE.match(value)):
        return False
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def bundle_problems(bundle: Mapping[str, Any], root: Path | None = None) -> list[str]:
    """Every problem with a ``line_verify_items.v1`` bundle; with ``root`` also each page image and its sha256."""

    problems = []
    if bundle.get("schema_version") != ITEMS_SCHEMA:
        return [f"schema_version must be {ITEMS_SCHEMA}"]
    for key in ("batch_id", "description"):
        if not (isinstance(bundle.get(key), str) and bundle[key].strip()):
            problems.append(f"{key} must be a non-empty string")
    if not _is_date(bundle.get("created_at")):
        problems.append("created_at must be a YYYY-MM-DD date")
    generator = bundle.get("generator")
    if not (isinstance(generator, Mapping) and generator.get("tool") == TOOL and isinstance(generator.get("ref"), str)):
        problems.append(f"generator must be {{tool: {TOOL}, ref}}")
    pages: dict[str, Mapping[str, Any]] = {}
    for page in bundle.get("pages") or []:
        page_id = page.get("page_id")
        where = f"page {page_id}"
        if not isinstance(page_id, str) or page_id in pages:
            problems.append(f"{where}: page_id must be a unique string")
            continue
        source = page.get("source")
        if source not in SOURCES:
            problems.append(f"{where}: source must be one of {SOURCES}")
            continue
        pages[page_id] = page
        if not page_id.startswith(f"{source}:"):
            problems.append(f"{where}: page_id must start with its source")
        if page.get("text_license") != TEXT_LICENSE[source]:
            problems.append(f"{where}: text_license must be {TEXT_LICENSE[source]!r}")
        if page.get("release_split") not in (*RELEASE_SPLITS, None):
            problems.append(f"{where}: release_split must be one of {RELEASE_SPLITS} or null")
        for key in ("book_id", "book_title", "page_label", "attribution"):
            if not (isinstance(page.get(key), str) and page[key].strip()):
                problems.append(f"{where}: {key} must be a non-empty string")
        if not (_is_int(page.get("width")) and _is_int(page.get("height")) and page["width"] > 0 and page["height"] > 0):
            problems.append(f"{where}: width and height must be positive integers")
        digest, image = page.get("sha256"), page.get("image")
        if not (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) and isinstance(image, str)
                and image.startswith(f"pages/{digest}.")):
            problems.append(f"{where}: image must be pages/<sha256>.<ext> with its sha256")
        elif root is not None:
            path = root / image
            if not path.is_file():
                problems.append(f"{where}: {image} is missing")
            elif sha256_bytes(path.read_bytes()) != digest:
                problems.append(f"{where}: {image} does not match its sha256")
            else:
                from PIL import Image

                with Image.open(path) as opened:
                    if opened.size != (page.get("width"), page.get("height")):
                        problems.append(f"{where}: image size differs from width and height")
    if not pages:
        problems.append("pages must not be empty")
    items = bundle.get("items") or []
    if not items:
        problems.append("items must not be empty")
    seen, ranks, used = set(), [], set()
    for item in items:
        item_id = item.get("item_id")
        where = f"item {item_id}"
        match = _ITEM_ID.match(item_id) if isinstance(item_id, str) else None
        if match is None or item_id in seen:
            problems.append(f"{where}: item_id must be a unique <page_id>#L<nnn>")
            continue
        seen.add(item_id)
        page = pages.get(item.get("page_id"))
        if page is None or match["page"] != item.get("page_id"):
            problems.append(f"{where}: page_id must name a bundle page and prefix the item_id")
            continue
        used.add(page["page_id"])
        if not (_is_int(item.get("line_index")) and int(match["line"]) == item["line_index"]):
            problems.append(f"{where}: line_index must match the item_id")
        box, context = item.get("box"), item.get("context_box")
        if not (_is_box(box) and _is_box(context)):
            problems.append(f"{where}: box and context_box must be [x0, y0, x1, y1] integers with x0 < x1 and y0 < y1")
        else:
            if not (0 <= context[0] <= box[0] and 0 <= context[1] <= box[1] and box[2] <= context[2] <= page.get("width", 0)
                    and box[3] <= context[3] <= page.get("height", 0)):
                problems.append(f"{where}: box must lie in context_box, inside the page")
        text = item.get("candidate_text")
        if not (isinstance(text, str) and text.strip()):
            problems.append(f"{where}: candidate_text must be a non-empty string")
            continue
        if unicodedata.normalize("NFC", text) != text or text != " ".join(text.split()) or "\n" in text:
            problems.append(f"{where}: candidate_text must be NFC, on one line, with single spaces")
        if fix_space_before_punctuation(text)[1]:
            problems.append(f"{where}: candidate_text has a space before punctuation (fix_space_before_punctuation)")
        if item.get("candidate_provenance") != CANDIDATE_PROVENANCE[page["source"]]:
            problems.append(f"{where}: candidate_provenance must be {CANDIDATE_PROVENANCE[page['source']]}")
        for key in ("alignment_score", "difficulty"):
            value = item.get(key)
            if not (isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1):
                problems.append(f"{where}: {key} must be in [0, 1]")
        spans = item.get("attention_spans")
        if not isinstance(spans, list):
            problems.append(f"{where}: attention_spans must be a list")
        else:
            previous = -1
            for span in spans:
                # code-point offsets (Python string indices); an empty span [i, i] marks an insertion point
                if not (isinstance(span, list) and len(span) == 2 and all(_is_int(v) for v in span)
                        and max(previous, 0) <= span[0] <= span[1] <= len(text)):
                    problems.append(f"{where}: attention_spans must be sorted, disjoint [start, end) code-point offsets into candidate_text")
                    break
                previous = span[1]
        if item.get("stratum") not in STRATA:
            problems.append(f"{where}: stratum must be one of {STRATA}")
        if not _is_int(item.get("rank")):
            problems.append(f"{where}: rank must be an integer")
        else:
            ranks.append(item["rank"])
        extra = set(item) - {"item_id", "page_id", "line_index", "box", "context_box", "candidate_text", "candidate_provenance",
                             "alignment_score", "attention_spans", "difficulty", "stratum", "rank"}
        if extra:
            problems.append(f"{where}: unknown fields {sorted(extra)} (no OCR text or other data may ship)")
    if sorted(ranks) != list(range(1, len(ranks) + 1)):
        problems.append("rank must number the items 1..N without gaps or repeats")
    unused = set(pages) - used
    if unused:
        problems.append(f"{len(unused)} pages carry no item")
    return problems


def load_bundle(path: Path, *, check_images: bool = True) -> dict[str, Any]:
    """Load and validate a bundle directory (or its ``items.json``)."""

    root = path if path.is_dir() else path.parent
    bundle = json.loads((root / "items.json").read_text(encoding="utf-8"))
    problems = bundle_problems(bundle, root if check_images else None)
    if problems:
        raise StageExecutionError("invalid line_verify_items.v1: " + "; ".join(problems[:10]))
    return bundle


def decisions_problems(decisions: Mapping[str, Any], bundle: Mapping[str, Any] | None = None) -> list[str]:
    """Every problem with a ``line_verify_decisions.v1`` file, against its bundle when given."""

    if decisions.get("schema_version") != DECISIONS_SCHEMA:
        return [f"schema_version must be {DECISIONS_SCHEMA}"]
    problems = []
    if not (isinstance(decisions.get("batch_id"), str) and decisions["batch_id"]):
        problems.append("batch_id must be a non-empty string")
    items = {item["item_id"]: item for item in (bundle or {}).get("items", [])}
    if bundle is not None and decisions.get("batch_id") != bundle.get("batch_id"):
        problems.append(f"batch_id {decisions.get('batch_id')!r} is not the bundle's {bundle.get('batch_id')!r}")
    records = decisions.get("decisions")
    if not isinstance(records, list):
        return problems + ["decisions must be a list"]
    seen = set()
    for record in records:
        item_id, reviewer = record.get("item_id"), record.get("reviewer")
        where = f"decision {record.get('decision_id')}"
        if not isinstance(item_id, str) or not isinstance(reviewer, str) or not REVIEWER_ID.match(reviewer):
            problems.append(f"{where}: item_id and an rv_ reviewer id (rv_ and 8 lower-case letters or digits) are required")
            continue
        if record.get("decision_id") != f"decision:{item_id}:{reviewer}":
            problems.append(f"{where}: decision_id must be decision:<item_id>:<reviewer>")
        if (item_id, reviewer) in seen:
            problems.append(f"{where}: one reviewer decided this item twice")
        seen.add((item_id, reviewer))
        if bundle is not None and item_id not in items:
            problems.append(f"{where}: item {item_id} is not in the bundle")
        decision = record.get("decision")
        if decision not in DECISION_VALUES:
            problems.append(f"{where}: decision must be one of {DECISION_VALUES}")
        text = record.get("text")
        if decision == "edited":
            if not (isinstance(text, str) and text.strip()):
                problems.append(f"{where}: an edited decision needs the corrected line as text")
            elif unicodedata.normalize("NFC", text) != text or "\n" in text or text != text.strip():
                problems.append(f"{where}: text must be NFC, on one line, without outer spaces")
            elif item_id in items and text == items[item_id]["candidate_text"] and not is_stale(record, items[item_id]):
                problems.append(f"{where}: the edited text equals the candidate (use exact)")
        elif "text" in record:
            problems.append(f"{where}: text is only allowed on an edited decision")
        if not _is_date(record.get("decided_at")):
            problems.append(f"{where}: decided_at must be a YYYY-MM-DD date")
        if record.get("checked_by") != "human":
            problems.append(f"{where}: checked_by must be human")
        digest = record.get("candidate_sha256")
        if digest is not None and not (isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)):
            problems.append(f"{where}: candidate_sha256 must be the SHA-256 hex of the judged candidate_text")
        extra = set(record) - {"decision_id", "item_id", "reviewer", "decision", "text", "decided_at", "checked_by",
                               "candidate_sha256"}
        if extra:
            problems.append(f"{where}: unknown fields {sorted(extra)}")
    return problems


def is_stale(record: Mapping[str, Any], item: Mapping[str, Any]) -> bool:
    """A decision is stale when the candidate its reviewer judged (``candidate_sha256``, the SHA-256 hex of the UTF-8
    ``candidate_text``) is not the item's current candidate, e.g. after a re-export changed it. A decision without
    the field (written before the contract added it) is taken as made on the current candidate."""

    digest = record.get("candidate_sha256")
    return digest is not None and digest != sha256_text(item["candidate_text"])


def load_decisions(path: Path, bundle: Mapping[str, Any] | None = None) -> dict[str, Any]:
    decisions = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = decisions_problems(decisions, bundle)
    if problems:
        raise StageExecutionError("invalid line_verify_decisions.v1: " + "; ".join(problems[:10]))
    return decisions


# --- Ingest ---------------------------------------------------------------------------------------------------


def resolve_decisions(bundle: Mapping[str, Any], decisions: Mapping[str, Any], *, min_reviewers: int = DEFAULT_MIN_REVIEWERS,
                      policy: str = ATTESTATION_POLICY) -> dict[str, Any]:
    """The line references and exclusions a decisions file gives.

    An item's outcome applies when at least ``min_reviewers`` reviewers decided it and all agree (the same decision,
    and for ``edited`` the same text); otherwise it is ``pending`` or ``conflict`` and nothing applies. ``exact`` and
    ``edited`` give a line reference whose status comes from ``ATTESTATION_POLICIES[policy]``; ``edited`` uses the
    reviewer's text and keeps the candidate as provenance. ``unreadable`` and ``misaligned`` exclude the line, and
    ``misaligned`` is counted as alignment-quality feedback. A stale decision (``is_stale``: made on another candidate
    text) is listed and counted, and never applied.
    """

    if policy not in ATTESTATION_POLICIES:
        raise StageExecutionError(f"unknown attestation policy {policy!r}")
    status = ATTESTATION_POLICIES[policy]
    pages = {page["page_id"]: page for page in bundle["pages"]}
    items = {item["item_id"]: item for item in bundle["items"]}
    by_item: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    stale = []
    for record in decisions["decisions"]:
        if is_stale(record, items[record["item_id"]]):
            stale.append({"decision_id": record["decision_id"], "item_id": record["item_id"], "reviewer": record["reviewer"],
                          "decision": record["decision"], "reason": "candidate_changed_since_decision"})
            continue
        by_item[record["item_id"]].append(record)
    lines, excluded, conflicts, pending = [], [], [], []
    for item_id in sorted(by_item, key=lambda key: items[key]["rank"]):
        records = sorted(by_item[item_id], key=lambda record: record["reviewer"])
        item, page = items[item_id], pages[items[item_id]["page_id"]]
        outcomes = {(record["decision"], record.get("text")) for record in records}
        common = {
            "item_id": item_id, "page_id": item["page_id"], "source": page["source"], "book_id": page["book_id"],
            "release_split": page["release_split"], "stratum": item["stratum"],
            "reviewers": [record["reviewer"] for record in records],
            "decision_ids": [record["decision_id"] for record in records], "reviewer_count": len(records),
        }
        if len(outcomes) > 1:
            conflicts.append({**common, "decisions": sorted(f"{d}" for d, _ in outcomes)})
            continue
        if len(records) < min_reviewers:
            pending.append(common)
            continue
        decision, text = next(iter(outcomes))
        decided_at = max(record["decided_at"] for record in records)
        if decision not in VERIFIED_DECISIONS:
            excluded.append({**common, "decision": decision, "decided_at": decided_at,
                             "reason": "unreadable_on_scan" if decision == "unreadable" else "box_and_text_misaligned"})
            continue
        final = item["candidate_text"] if decision == "exact" else text
        lines.append({
            **common, "line_index": item["line_index"], "box": item["box"], "page_sha256": page["sha256"],
            "decision": decision, "decided_at": decided_at, "checked_by": "human",
            "candidate_provenance": item["candidate_provenance"], "candidate_text": item["candidate_text"],
            "candidate_text_sha256": sha256_text(item["candidate_text"]), "text": final, "text_sha256": sha256_text(final),
            "corrected": decision == "edited", "text_license": page["text_license"], "attestation_policy": policy,
            "attestation_status": status["attestation_status"], "adjudication_status": status["adjudication_status"],
            "reference_eligible": status["reference_eligible"],
        })
    decided = set(by_item)
    misaligned = Counter(entry["source"] for entry in excluded if entry["decision"] == "misaligned")
    verified_or_excluded = Counter(entry["source"] for entry in [*lines, *excluded])
    counts = {
        "bundle_items": len(items), "decided_items": len(decided), "undecided_items": len(items) - len(decided),
        "decisions": len(decisions["decisions"]), "reviewers": len({record["reviewer"] for record in decisions["decisions"]}),
        "line_references": len(lines), "reference_eligible": sum(1 for line in lines if line["reference_eligible"]),
        "by_decision": dict(sorted(Counter(entry["decision"] for entry in [*lines, *excluded]).items())),
        "conflicts": len(conflicts), "pending_min_reviewers": len(pending), "stale_decisions": len(stale),
        "misaligned_share_by_source": {source: round(misaligned[source] / verified_or_excluded[source], 4)
                                       for source in sorted(verified_or_excluded)},
        "by_release_split": dict(sorted(Counter(str(line["release_split"]) for line in lines).items())),
    }
    return {"lines": lines, "excluded": excluded, "conflicts": conflicts, "pending": pending,
            "stale": sorted(stale, key=lambda entry: entry["decision_id"]), "counts": counts}


def references_document(bundle: Mapping[str, Any], decisions: Mapping[str, Any], resolved: Mapping[str, Any], *,
                        bundle_items_sha256: str, min_reviewers: int, policy: str = ATTESTATION_POLICY) -> dict[str, Any]:
    """``line_verify_references.v1``: the committed record (no images, no OCR, no local paths)."""

    return {
        "schema_version": REFERENCES_SCHEMA,
        "batch_id": bundle["batch_id"],
        "bundle_items_sha256": bundle_items_sha256,
        "generator": {"tool": TOOL, "bundle_generator_ref": bundle["generator"]["ref"]},
        "attestation_policy": {"name": policy, **ATTESTATION_POLICIES[policy], "min_reviewers": min_reviewers,
                               "verifier_differs_from_typist": True},
        "counts": resolved["counts"],
        "decisions": sorted(decisions["decisions"], key=lambda record: record["decision_id"]),
        "lines": resolved["lines"],
        "excluded": resolved["excluded"],
        "conflicts": resolved["conflicts"],
        "stale": resolved["stale"],
    }


def line_set(bundle: Mapping[str, Any], resolved: Mapping[str, Any]) -> dict[str, Any]:
    """The operator line reference set: the verified lines with their page images (bundle paths) and geometry."""

    pages = {page["page_id"]: page for page in bundle["pages"]}
    items = {item["item_id"]: item for item in bundle["items"]}
    used = sorted({line["page_id"] for line in resolved["lines"]})
    return {
        "schema_version": LINE_SET_SCHEMA, "batch_id": bundle["batch_id"], "modality": "printed",
        "visibility": "hidden_reference",
        "note": "line-level references for evaluation; each line keeps its book's release split (train lines are not held out)",
        "pages": [pages[page_id] for page_id in used],
        "lines": [{**line, "context_box": items[line["item_id"]]["context_box"]} for line in resolved["lines"]],
    }


def references_problems(document: Mapping[str, Any], bundle: Mapping[str, Any] | None = None) -> list[str]:
    """A committed references file is consistent: its decisions validate and re-resolve to the same lines."""

    if document.get("schema_version") != REFERENCES_SCHEMA:
        return [f"schema_version must be {REFERENCES_SCHEMA}"]
    policy = (document.get("attestation_policy") or {}).get("name")
    if policy not in ATTESTATION_POLICIES:
        return ["attestation_policy.name must be a known policy"]
    decisions = {"schema_version": DECISIONS_SCHEMA, "batch_id": document.get("batch_id"), "decisions": document.get("decisions")}
    problems = decisions_problems(decisions, bundle)
    if problems or bundle is None:
        return problems
    resolved = resolve_decisions(bundle, decisions, min_reviewers=document["attestation_policy"]["min_reviewers"], policy=policy)
    for key in ("lines", "excluded", "conflicts", "stale", "counts"):
        if resolved[key] != document.get(key):
            problems.append(f"{key} do not re-derive from the decisions and the bundle")
    return problems


def ingest(bundle_dir: Path, decisions_path: Path, out: Path, *, line_set_out: Path | None = None,
           min_reviewers: int = DEFAULT_MIN_REVIEWERS) -> dict[str, Any]:
    bundle = load_bundle(bundle_dir)
    decisions = load_decisions(decisions_path, bundle)
    resolved = resolve_decisions(bundle, decisions, min_reviewers=min_reviewers)
    items_sha = sha256_bytes((bundle_dir / "items.json").read_bytes())
    document = references_document(bundle, decisions, resolved, bundle_items_sha256=items_sha, min_reviewers=min_reviewers)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if line_set_out is not None:
        line_set_out.parent.mkdir(parents=True, exist_ok=True)
        line_set_out.write_text(json.dumps(line_set(bundle, resolved), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return resolved["counts"]


# --- Operator export: loading the two sources ---------------------------------------------------------------------


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as opened:
        return opened.size


def _geometry_lines(path: Path, frame_sha: str, offset: tuple[int, int] | None) -> list[tuple[tuple[float, float, float, float], str]]:
    """An engine's cached line geometry (``heocr_engine_kraken_geometry.v1``) in page pixels; [] if it is not of
    this page (or of its crop, shifted by ``offset``)."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("input_sha256") != frame_sha:
        return []
    dx, dy = offset or (0, 0)
    out = []
    for line in payload.get("lines") or []:
        x, y, w, h = line["bbox"]
        if line.get("text"):
            out.append(((x + dx, y + dy, x + w + dx, y + h + dy), str(line["text"])))
    return out


def load_wikisource_pages(snapshot_root: Path, ocr_cache: Path, *, split_manifest: Path | None,
                          exclude_manifests: Sequence[Path], engine_dirs: Mapping[str, Path],
                          rejected: Counter[str]) -> list[tuple[PageInput, str]]:
    """Quality-3 pages of an operator Wikisource snapshot that pass every page gate, with their pair text."""

    from hocrgen.fetchers.wikisource import load_wikisource_snapshot, page_exclusion_reasons

    _, indexes, records = load_wikisource_snapshot(snapshot_root)
    splits = {}
    if split_manifest is not None:
        for entry in json.loads(split_manifest.read_text(encoding="utf-8"))["items"]:
            splits[entry["item_id"]] = entry["split"]
    excluded_ids = set()
    for manifest in exclude_manifests:
        excluded_ids.update(entry["item_id"] for entry in json.loads(manifest.read_text(encoding="utf-8"))["items"])
    out = []
    for record in records:
        page_id = f"{WIKISOURCE}:{record['source_item_id']}"
        if page_id in excluded_ids:
            rejected["page_scored_reference"] += 1
            continue
        if record.get("quality") != 3:
            rejected["page_not_quality_3"] += 1
            continue
        if page_exclusion_reasons(record, indexes, snapshot_root):
            rejected["page_gate_failed"] += 1
            continue
        image = record["image"]
        image_path = snapshot_root / image["path"]
        if sha256_bytes(image_path.read_bytes()) != image["sha256"]:
            raise StageExecutionError(f"{page_id}: page image does not match its pinned sha256")
        tsv = ocr_cache / f"{image['sha256']}.heb.psm3.x2.tsv"
        if not tsv.is_file():
            rejected["page_without_cached_ocr"] += 1
            continue
        index = indexes[record["index_key"]]
        text = (snapshot_root / record["text_path"]).read_text(encoding="utf-8")
        if text.endswith("\n"):
            text = text[:-1]
        if sha256_text(text) != record["text_sha256"]:
            raise StageExecutionError(f"{page_id}: pair text does not match its pinned sha256")
        excluded_ranges = [(span["start"], span["end"]) for span in (record.get("excluded_spans") or {}).get("spans", [])
                           if isinstance(span, Mapping) and "start" in span]
        crop = record.get("crop") or {}
        engines = {}
        for name, directory in engine_dirs.items():
            path = directory / f"{record['source_item_id']}.json"
            if not path.is_file():
                continue
            readings = _geometry_lines(path, image["sha256"], None)
            if not readings and crop.get("asset") and crop.get("box_px"):
                readings = _geometry_lines(path, crop["asset"]["sha256"], (crop["box_px"][0], crop["box_px"][1]))
            if readings:
                engines[name] = readings
        revision = record["revision_id"]
        work = index.get("work") or {}
        commons = (index.get("commons_file") or {}).get("title", "")
        page = PageInput(
            page_id=page_id, source=WIKISOURCE, book_id=record["index_key"],
            book_title=str(work.get("title") or index.get("index_title")), page_label=str(record["page_number"]),
            image_path=image_path,
            attribution=(f"Text: Hebrew Wikisource contributors, CC BY-SA 4.0, "
                         f"https://he.wikisource.org/w/index.php?oldid={revision}; scan: Wikimedia Commons, {commons}, page "
                         f"{record['page_number']}"),
            release_split=splits.get(page_id), size=(int(image["width"]), int(image["height"])),
            ocr_lines=aligner.parse_tesseract_tsv(tsv.read_text(encoding="utf-8"), scale=0.5),
            engine_lines=engines, excluded_ranges=excluded_ranges,
        )
        out.append((page, text))
    return out


def load_nli_works(config_path: Path, rejected: Counter[str]) -> list[tuple[list[PageInput], list[tuple[str, str]]]]:
    """F8f scans and their PBY works from an operator config (``line_verify_nli_works.v1``).

    Each scan: ``record_id``, ``manifest`` (the captured IIIF manifest, or an F8f manifest capture), ``manifest_url``,
    ``work_dir`` (``img/cNNNN.jpg`` and ``ocr/cNNNN.tsv`` as F8f wrote them; ``image_pattern``, ``ocr_pattern`` and
    ``ocr_image_width`` override), ``catalogue`` (the PBY ``pseudocatalogue.csv``) and ``works`` (``[{pby_id, text}]``).
    Paths are relative to the config. The scan is re-gated by ``decide_nli_rights``.
    """

    from hocrgen.fetchers.nli_iiif import NliManifestCapture, decide_nli_rights, manifest_canvases

    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("schema_version") != "line_verify_nli_works.v1":
        raise StageExecutionError("NLI works config must be line_verify_nli_works.v1")
    base = config_path.parent
    out = []
    for scan in config["scans"]:
        manifest_bytes = (base / scan["manifest"]).read_bytes()
        manifest = json.loads(manifest_bytes)
        if manifest.get("capture_format") and isinstance(manifest.get("manifest"), dict):
            manifest = manifest["manifest"]  # an F8f manifest capture
        canvases = manifest_canvases(manifest)
        capture = NliManifestCapture(manifest_url=scan["manifest_url"], http_status=200, canvas_count=len(canvases),
                                     manifest=manifest, upstream_sha256=sha256_bytes(manifest_bytes))
        decision = decide_nli_rights(display_rights=None, capture=capture)
        if not decision.accepted or decision.license_slug != NLI_ACCEPTED_SLUG:
            rejected["nli_scan_rights_not_free_use"] += len(canvases)
            continue
        catalogue = aligner.load_catalogue(base / scan["catalogue"])
        work_dir = base / scan["work_dir"]
        record = str(scan["record_id"])
        label = manifest.get("label")
        title = label if isinstance(label, str) else str(record)
        pages = []
        image_pattern = scan.get("image_pattern", "img/c{index:04d}.jpg")
        ocr_pattern = scan.get("ocr_pattern", "ocr/c{index:04d}.tsv")
        for index, _canvas in enumerate(canvases):
            image_path = work_dir / image_pattern.format(index=index)
            tsv = work_dir / ocr_pattern.format(index=index)
            if not (image_path.is_file() and tsv.is_file()):
                continue
            size = _image_size(image_path)
            # F8f ran Tesseract on the page image itself; a fixture may ship a smaller copy of the OCR'd image.
            scale = size[0] / int(scan.get("ocr_image_width") or size[0])
            pages.append(PageInput(
                page_id=f"{NLI_ALIGNED}:nli_{record}__c{index:04d}", source=NLI_ALIGNED, book_id=f"nli_{record}",
                book_title=title, page_label=f"canvas {index + 1}", image_path=image_path,
                attribution="",  # set per page below, from the works that align to it
                release_split=None, size=size,
                ocr_lines=aligner.parse_tesseract_tsv(tsv.read_text(encoding="utf-8"), scale=scale),
            ))
        works = []
        for work in scan["works"]:
            row = catalogue[str(work["pby_id"])]
            fields = aligner.catalogue_fields(row)
            text = aligner.pby_body((base / work["text"]).read_text(encoding="utf-8"))
            works.append((text, f"{fields.get('title')} ({fields.get('authors')}), Project Ben-Yehuda {fields.get('read_url')}"))
        attribution_scan = (f"scan: National Library of Israel ({'; '.join(capture.attribution or [])}), {scan['manifest_url']}, "
                            f"{decision.license_slug}")
        for page in pages:
            page.attribution = attribution_scan
        out.append((pages, works))
    return out


def collect_candidates(wikisource: Sequence[tuple[PageInput, str]], nli: Sequence[tuple[list[PageInput], list[tuple[str, str]]]],
                       rejected: Counter[str]) -> tuple[dict[str, PageInput], list[LineCandidate]]:
    """Align every source and pool the eligible lines (one PBY scan may carry several works: a line located by more
    than one work is ambiguous and dropped)."""

    pages: dict[str, PageInput] = {}
    candidates: list[LineCandidate] = []
    for page, text in wikisource:
        pages[page.page_id] = page
        candidates.extend(aligned_candidates(text, [page], rejected, text_bounded=True)[page.page_id])
    for scan_pages, works in nli:
        per_line: dict[str, list[tuple[LineCandidate, str]]] = defaultdict(list)
        for text, work_attribution in works:
            for page_id, lines in aligned_candidates(text, scan_pages, rejected, text_bounded=False).items():
                for line in lines:
                    per_line[line.item_id].append((line, work_attribution))
        by_page_work: dict[str, set[str]] = defaultdict(set)
        for item_id, found in per_line.items():
            if len(found) > 1:
                rejected["located_by_two_works"] += 1
                continue
            line, work_attribution = found[0]
            candidates.append(line)
            by_page_work[line.page_id].add(work_attribution)
        for page in scan_pages:
            pages[page.page_id] = page
            if by_page_work.get(page.page_id):
                page.attribution = "Text: " + "; ".join(sorted(by_page_work[page.page_id])) + ", public domain; " + page.attribution
    return pages, candidates


def export(args: argparse.Namespace) -> dict[str, Any]:  # pragma: no cover - operator path (real data)
    rejected: Counter[str] = Counter()
    engine_dirs = dict(spec.split("=", 1) for spec in args.engine_geometry or [])
    wikisource = []
    if args.wikisource_snapshot:
        wikisource = load_wikisource_pages(args.wikisource_snapshot, args.wikisource_ocr_cache, split_manifest=args.split_manifest,
                                           exclude_manifests=args.exclude_reference_manifest or [],
                                           engine_dirs={name: Path(path) for name, path in engine_dirs.items()}, rejected=rejected)
    nli = load_nli_works(args.nli_works, rejected) if args.nli_works else []
    pages, candidates = collect_candidates(wikisource, nli, rejected)
    ranked = select_items(candidates, seed=args.batch_id, size=args.size)
    for item, _ in ranked:
        if pages[item.page_id].attribution == "":
            raise StageExecutionError(f"{item.page_id}: no attribution")
    bundle, copies = build_bundle(pages, ranked, batch_id=args.batch_id, created_at=args.created_at,
                                  generator_ref=args.generator_ref or _git_ref(), description=args.description)
    problems = bundle_problems(bundle)
    if problems:
        raise StageExecutionError("; ".join(problems[:10]))
    write_bundle(args.out, bundle, copies)
    problems = bundle_problems(bundle, args.out)
    if problems:
        raise StageExecutionError("; ".join(problems[:10]))
    stats = bundle_stats(bundle)
    engines_used = Counter(name for item, _ in ranked for name in item.engines)
    eligible_books = Counter(item.book_id for item in candidates)
    report = {
        "schema_version": REPORT_SCHEMA, "batch_id": args.batch_id, "eligibility": ELIGIBILITY,
        "difficulty_weights": DIFFICULTY_WEIGHTS, "secondary_engine_weight": SECONDARY_ENGINE_WEIGHT, "selection": SELECTION,
        "source_pages": {"wikisource": len(wikisource), "nli": sum(len(scan_pages) for scan_pages, _ in nli)},
        "eligible_lines": len(candidates),
        "eligible_by_source": dict(Counter(item.source for item in candidates)),
        "eligible_books": len(eligible_books),
        "rejected_lines": dict(sorted(rejected.items())),
        "selected_engines": dict(engines_used),
        "stats": stats,
        "items": [{"item_id": item.item_id, "stratum": stratum, "difficulty": item.difficulty, "components": item.components,
                   "engines": item.engines} for item, stratum in ranked],
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {key: report[key] for key in ("eligible_lines", "eligible_by_source", "eligible_books", "rejected_lines", "selected_engines")} | {"stats": stats}


def _git_ref() -> str:  # pragma: no cover - operator path
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


# --- CLI ------------------------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m hocrgen.tools.line_verify", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="operator: build a line_verify_items.v1 bundle")
    ex.add_argument("--wikisource-snapshot", type=Path, help="tranche Wikisource snapshot root (pages.jsonl, assets/, text/)")
    ex.add_argument("--wikisource-ocr-cache", type=Path, help="Tesseract cache of the coverage tool (<sha256>.heb.psm3.x2.tsv)")
    ex.add_argument("--split-manifest", type=Path, help="the tranche's release split manifest")
    ex.add_argument("--exclude-reference-manifest", type=Path, action="append",
                    help="reference manifest whose pages are left out (the scored quality-4 pages); repeatable")
    ex.add_argument("--engine-geometry", action="append", metavar="NAME=DIR",
                    help="cached engine line geometry per page (<source_item_id>.json), e.g. r3h_r4d_a1=DIR; repeatable")
    ex.add_argument("--nli-works", type=Path, help="line_verify_nli_works.v1 config of F8f scans and PBY works")
    ex.add_argument("--out", type=Path, required=True, help="bundle directory (operator data, never committed)")
    ex.add_argument("--report", type=Path, help="selection report (components and counts, no text)")
    ex.add_argument("--batch-id", default=DEFAULT_BATCH_ID)
    ex.add_argument("--created-at", default=_dt.date.today().isoformat())
    ex.add_argument("--size", type=int, default=int(SELECTION["size"]))
    ex.add_argument("--generator-ref", default=None)
    ex.add_argument("--description", default="E2d6 line verification, first batch: hard lines first, with an unbiased random stratum")
    ing = sub.add_parser("ingest", help="validate decisions and write the line references")
    ing.add_argument("--bundle", type=Path, required=True)
    ing.add_argument("--decisions", type=Path, required=True)
    ing.add_argument("--out", type=Path, required=True, help="line_verify_references.v1 (docs/line_verify_references.json)")
    ing.add_argument("--line-set-out", type=Path, help="operator line reference set (with page images and geometry)")
    ing.add_argument("--min-reviewers", type=int, default=DEFAULT_MIN_REVIEWERS)
    val = sub.add_parser("validate", help="validate a bundle, a decisions file and/or a references file")
    val.add_argument("--bundle", type=Path)
    val.add_argument("--decisions", type=Path)
    val.add_argument("--references", type=Path)
    val.add_argument("--no-images", action="store_true", help="do not check page images (bundle items.json only)")
    st = sub.add_parser("stats", help="counts per source, book, split and stratum, and histograms")
    st.add_argument("--bundle", type=Path, required=True)
    st.add_argument("--decisions", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "export":  # pragma: no cover - operator path
        result = export(args)
    elif args.command == "ingest":
        result = ingest(args.bundle, args.decisions, args.out, line_set_out=args.line_set_out, min_reviewers=args.min_reviewers)
    elif args.command == "validate":
        if not (args.bundle or args.decisions or args.references):
            raise StageExecutionError("give --bundle, --decisions and/or --references")
        bundle = load_bundle(args.bundle, check_images=not args.no_images) if args.bundle else None
        result = {"valid": True}
        if bundle is not None:
            result["items"] = len(bundle["items"])
        if args.decisions:
            result["decisions"] = len(load_decisions(args.decisions, bundle)["decisions"])
        if args.references:
            document = json.loads(args.references.read_text(encoding="utf-8"))
            problems = references_problems(document, bundle)
            if problems:
                raise StageExecutionError("invalid line_verify_references.v1: " + "; ".join(problems[:10]))
            result["line_references"] = len(document["lines"])
    else:
        bundle = load_bundle(args.bundle, check_images=False)
        result = bundle_stats(bundle)
        if args.decisions:
            result["decisions"] = resolve_decisions(bundle, load_decisions(args.decisions, bundle))["counts"]
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
