"""Locate the transcribed region of a Wikisource page by aligning its human text to OCR boxes (F8b4, operator tool).

Decision 12 (2026-11-06): a partial transcription is paired with the transcribed region of the page, not dropped.
This tool finds that region. For each page render it runs a local OCR engine (Tesseract with the Hebrew model,
called as a subprocess) **only to get line and word boxes**, aligns the page's human transcription
(``wikisource_plain_text.v2``) to the OCR lines, and derives:

- ``transcription_coverage``: ``full_page`` when the aligned lines cover every text-bearing OCR line within a
  tolerance (running heads, page numbers, catchwords and signature marks are page furniture and ignored),
  else ``partial_page``. Recorded as a check with ``checked_by: tool``, the method, its version and thresholds;
- a **crop box**: the union of the aligned line boxes plus a margin, shrunk so it does not reach into
  untranscribed lines outside it. Untranscribed lines left inside the box are listed (``untranscribed_inside``)
  so evaluation can mask them; too many of them, or too little of the transcription located, leaves the crop
  ``unresolved`` with a reason, and the page is reported (``crop_unresolved``), never silently dropped;
- an alignment-quality score (the share of the transcription located, and the mean line match).

OCR text is never stored as, or merged into, the reference. It is used only to place boxes; the check records
no OCR text and no page text. A human or agent check of the same page overrides a tool check
(``hocrgen.tools.wikisource_inventory.select_page_checks``).

The alignment is order-preserving per line: each OCR line is matched to the transcription by character-trigram
votes on a diagonal band (a line's trigrams must hit the transcription in the same order, with bounded drift),
so a line matches only where the transcription has the same run of text. Lines OCR misreads are recovered when
they sit between two aligned lines and the transcription has unmatched text of a fitting length between those
lines' matches (``interpolated``). Untranscribed text interleaved with transcribed text has no such gap.

The OCR and capture paths are operator-only; ``parse_tesseract_tsv``, ``align_page`` and ``assess_page`` are
network-free and engine-free, and are what the tests exercise.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import io
import json
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TOOL_VERSION = "0.2.0"
METHOD_ID = "tool_ocr_alignment_v1"
METHOD_TEXT = (
    "hocrgen.tools.wikisource_coverage: Tesseract (Hebrew model) on the Commons render of the pinned file's page, "
    "used only for line and word boxes; the page's wikisource_plain_text.v2 text aligned to the OCR lines by "
    "order-preserving character-trigram votes; full_page when the aligned lines cover every text-bearing OCR line "
    "within the tolerance, ignoring running heads, page numbers, catchwords and signature marks; for a partial page "
    "the crop is the union of the aligned line boxes plus a margin, or, when untranscribed blocks are interleaved with the "
    "transcription, one region per block of transcribed lines with the rest of the box masked. No OCR text is stored or used as text."
)
CROP_METHOD = "ocr_alignment_union_box.v1"
# F8b5: when one rectangle cannot leave interleaved untranscribed blocks out, one region per block of transcribed
# lines; the pair image is the regions' union box with everything outside the regions masked to the background.
CROP_REGIONS_METHOD = "ocr_alignment_region_mask.v1"
USER_AGENT = "hocrgen-wikisource-coverage/0.1 (https://github.com/HeOCR/hocrgen; operator capture)"
RENDER_WIDTH = 960

# Thresholds (recorded on every check, so a check can be re-derived and reviewed).
THRESHOLDS: dict[str, float] = {
    # a line is aligned when this share of its trigrams hits the transcription on one diagonal band
    "line_match_min": 0.30,
    # band width: drift allowed along a line, as a share of its length plus a constant (characters)
    "band_share": 0.15,
    "band_min_chars": 6,
    # a line with fewer normalised characters is too short to align on its own
    "line_min_chars": 6,
    # second pass: a weaker match is enough when it falls in transcription text no aligned line has matched
    "gap_match_min": 0.18,
    # an unaligned run is interpolated when the transcription gap between its aligned neighbours is
    # between gap_min_share and gap_max_share of the run's length (plus gap_slack_chars)
    "gap_min_share": 0.45,
    "gap_max_share": 2.5,
    "gap_slack_chars": 24,
    # full_page when untranscribed text-bearing lines are at most this share of the text area
    "full_page_untranscribed_area_max": 0.04,
    # and at most this many untranscribed lines of line_min_chars or more
    "full_page_untranscribed_lines_max": 1,
    # below this located share a page counts as poorly read, with a looser untranscribed-area tolerance
    "well_read_located_min": 0.5,
    "poorly_read_untranscribed_area_max": 0.10,
    "poorly_read_block_lines_max": 3,
    # corner marks (stamps, page numbers): narrow, off-centre, above or below the region, in the page's top or
    # bottom band; they never make a page partial
    "margin_mark_max_width_share": 0.4,
    "margin_mark_min_offset_share": 0.15,
    "margin_band_share": 0.15,
    # page furniture: up to this many unaligned lines above all aligned lines (running head) ...
    "furniture_top_lines": 2,
    "furniture_top_max_chars": 45,
    # ... and below them (page number, catchword, signature mark)
    "furniture_bottom_lines": 2,
    "furniture_bottom_max_chars": 18,
    # a crop is resolved only when aligned and interpolated lines span this much of the transcription ...
    "crop_bracketed_min": 0.7,
    # ... and untranscribed lines inside it are at most this share of its text area
    "crop_untranscribed_inside_max": 0.15,
    # crop margin, in median line heights
    "crop_margin_line_heights": 0.6,
    # multi-region crops (F8b5): two blocks of transcribed lines stay apart when joining them would take in an
    # untranscribed region's centre or this share of its area; at most this many regions; blocks whose tops lie in
    # the same band of this many render pixels are one row (read right to left)
    "region_block_overlap_max": 0.25,
    "region_max_count": 8,
    "region_row_px": 40,
    # ink no readable OCR line covers: cells of this many render pixels, darker than the page by this much
    "ink_cell_px": 4,
    "ink_contrast": 60,
    # an unread ink band counts as untranscribed text when it is this tall (median line heights), wide and dense
    "ink_min_line_heights": 1.5,
    # a band taller than this with no blank row inside is an illustration or ornament, not lines of text
    "ink_max_line_heights": 5.0,
    "ink_min_width_share": 0.2,
    "ink_min_density": 0.08,
    # a page is decided when aligned and interpolated lines span this share of the transcription, the aligned
    # lines alone at least decide_aligned_located_min, and at least decide_aligned_lines_min lines align
    "decide_bracketed_min": 0.6,
    "decide_aligned_located_min": 0.2,
    "decide_aligned_lines_min": 3,
    # a short page (a title or half-title) with fewer aligned lines is decided when this much of it is located
    "decide_short_page_located_min": 0.8,
}

_FINAL_FORMS = str.maketrans({"ך": "כ", "ם": "מ", "ן": "נ", "ף": "פ", "ץ": "צ"})
_NOTE_MARKER = re.compile(r"\[\d+\]")


# --- Normalisation --------------------------------------------------------------------------------------------


def alignment_tokens(text: str) -> list[str]:
    """Letters and digits only, per word: NFKC, no niqqud or cantillation, Hebrew final forms folded, lower case."""

    text = _NOTE_MARKER.sub(" ", unicodedata.normalize("NFKC", text))
    tokens: list[str] = []
    for raw in text.split():
        kept = "".join(ch for ch in raw if unicodedata.category(ch)[0] in "LN")
        if kept:
            tokens.append(kept.translate(_FINAL_FORMS).casefold())
    return tokens


def alignment_string(text: str) -> str:
    return "".join(alignment_tokens(text))


# --- OCR geometry ---------------------------------------------------------------------------------------------


@dataclass
class OcrLine:
    """One OCR line: its box in render pixels, word count, mean confidence, and the normalised characters.

    The characters are used to align, then discarded: they are never written out.
    """

    key: tuple[int, int, int]
    box: tuple[int, int, int, int]  # x0, y0, x1, y1
    words: int
    confidence: float
    chars: str = field(repr=False)

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]

    @property
    def area(self) -> int:
        return max(0, self.box[2] - self.box[0]) * max(0, self.box[3] - self.box[1])


def parse_tesseract_tsv(tsv: str) -> list[OcrLine]:
    """Group Tesseract TSV words (level 5) into lines (block, paragraph, line), in Tesseract's reading order."""

    reader = csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE)
    lines: dict[tuple[int, int, int], dict[str, Any]] = {}
    for row in reader:
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        x, y, w, h = (int(row[name]) for name in ("left", "top", "width", "height"))
        entry = lines.setdefault(key, {"boxes": [], "texts": [], "confs": []})
        entry["boxes"].append((x, y, x + w, y + h))
        entry["texts"].append(row["text"])
        entry["confs"].append(float(row["conf"]))
    result: list[OcrLine] = []
    for key in sorted(lines):
        entry = lines[key]
        boxes = entry["boxes"]
        box = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        result.append(
            OcrLine(
                key=key,
                box=box,
                words=len(boxes),
                confidence=sum(entry["confs"]) / len(entry["confs"]),
                chars=alignment_string(" ".join(entry["texts"])),
            )
        )
    return result


# --- Alignment ------------------------------------------------------------------------------------------------


@dataclass
class LineAlignment:
    line: OcrLine
    score: float
    span: tuple[int, int] | None  # [start, end) in the normalised transcription
    status: str  # aligned | interpolated | unaligned | furniture | noise


def _trigram_index(reference: str) -> dict[str, list[int]]:
    index: dict[str, list[int]] = defaultdict(list)
    for position in range(len(reference) - 2):
        index[reference[position : position + 3]].append(position)
    return index


def match_line(chars: str, index: dict[str, list[int]], thresholds: dict[str, float]) -> tuple[float, tuple[int, int] | None]:
    """Best diagonal-band match of one line against the transcription: (share of trigrams hit, transcription span)."""

    grams = len(chars) - 2
    if grams <= 0:
        return 0.0, None
    hits: list[tuple[int, int]] = []  # (diagonal, line position)
    for position in range(grams):
        for ref_position in index.get(chars[position : position + 3], ()):
            hits.append((ref_position - position, position))
    if not hits:
        return 0.0, None
    hits.sort()
    band = max(thresholds["band_min_chars"], thresholds["band_share"] * len(chars))
    diagonals = [diagonal for diagonal, _ in hits]
    best = (0, 0, 0)  # (distinct positions, start, end) over hits[start:end]
    end = 0
    for start in range(len(hits)):
        end = max(end, start)
        limit = diagonals[start] + band
        end = bisect_left(diagonals, limit + 1e-9, lo=end)
        if end - start <= best[0]:
            continue
        distinct = len({position for _, position in hits[start:end]})
        if distinct > best[0]:
            best = (distinct, start, end)
    distinct, start, end = best
    window = hits[start:end]
    ref_positions = [diagonal + position for diagonal, position in window]
    return distinct / grams, (min(ref_positions), max(ref_positions) + 3)


def _is_noise(line: OcrLine, median_height: float) -> bool:
    if len(line.chars) < 3:
        return True
    if line.confidence < 20 and len(line.chars) < 8:
        return True
    return line.height > 3.5 * median_height and line.confidence < 50


def align_page(lines: list[OcrLine], reference_text: str, thresholds: dict[str, float] | None = None) -> tuple[list[LineAlignment], str]:
    """Align the transcription to the OCR lines. Returns per-line alignments and the normalised transcription."""

    thresholds = {**THRESHOLDS, **(thresholds or {})}
    reference = alignment_string(reference_text)
    index = _trigram_index(reference)
    heights = [line.height for line in lines if len(line.chars) >= 3] or [1]
    median_height = statistics.median(heights)
    alignments: list[LineAlignment] = []
    for line in lines:
        if _is_noise(line, median_height):
            alignments.append(LineAlignment(line, 0.0, None, "noise"))
            continue
        score, span = match_line(line.chars, index, thresholds)
        if len(line.chars) < thresholds["line_min_chars"]:
            alignments.append(LineAlignment(line, score, None, "short"))
            continue
        aligned = score >= thresholds["line_match_min"]
        alignments.append(LineAlignment(line, score, span if aligned else None, "aligned" if aligned else "unaligned"))
    _rematch_in_gaps(alignments, reference, thresholds)
    _interpolate(alignments, len(reference), thresholds)
    _interpolate_between_neighbours(alignments, thresholds)
    _mark_furniture(alignments, thresholds)
    return alignments, reference


def _rematch_in_gaps(alignments: list[LineAlignment], reference: str, thresholds: dict[str, float]) -> None:
    """Second pass: match each unaligned line against only the transcription text no aligned line has matched.

    A misread line keeps some trigrams of its own text, which the first pass may outvote with hits elsewhere;
    restricted to the unmatched text, its weaker match (``gap_match_min``) is enough.
    """

    covered = [False] * len(reference)
    for a in alignments:
        if a.status == "aligned" and a.span:
            for position in range(a.span[0], min(a.span[1], len(reference))):
                covered[position] = True
    if all(covered) or not any(covered):
        return
    masked = "".join("\x00" if flag else char for char, flag in zip(reference, covered))
    index = {gram: positions for gram, positions in _trigram_index(masked).items() if "\x00" not in gram}
    for a in alignments:
        if a.status != "unaligned":
            continue
        score, span = match_line(a.line.chars, index, thresholds)
        if score >= thresholds["gap_match_min"]:
            a.status, a.score, a.span = "aligned", score, span


def _interpolate(alignments: list[LineAlignment], reference_length: int, thresholds: dict[str, float]) -> None:
    """Recover misread lines: a run of unaligned lines between two aligned lines (in Tesseract order) whose
    transcription gap fits the run's length is transcribed text OCR misread."""

    text_lines = [a for a in alignments if a.status in {"aligned", "unaligned"}]
    anchors = [i for i, a in enumerate(text_lines) if a.status == "aligned"]
    if not anchors:
        return
    bounds = [(-1, 0)] + [(i, 0) for i in anchors] + [(len(text_lines), 0)]
    for (left, _), (right, _) in zip(bounds, bounds[1:]):
        run = text_lines[left + 1 : right]
        if not run:
            continue
        gap_start = text_lines[left].span[1] if left >= 0 else 0
        gap_end = text_lines[right].span[0] if right < len(text_lines) else reference_length
        gap = gap_end - gap_start
        run_length = sum(len(a.line.chars) for a in run)
        if thresholds["gap_min_share"] * run_length <= gap <= thresholds["gap_max_share"] * run_length + thresholds["gap_slack_chars"]:
            for a in run:
                a.status = "interpolated"
                a.span = (gap_start, gap_end)


def isolate_running_head(alignments: list[LineAlignment], ink: list[tuple[int, int, int, int]], thresholds: dict[str, float] | None = None) -> None:
    """A short transcribed line alone at the top, with untranscribed text (an unaligned line or unread ink) between it
    and the next transcribed line, is a running head (typed in the body, or matching a citation), not the edge of
    the transcribed region. It becomes ``furniture``."""

    thresholds = {**THRESHOLDS, **(thresholds or {})}
    ordered = sorted((a for a in alignments if a.status in {"aligned", "interpolated"}), key=lambda a: a.line.box[1])
    if len(ordered) < 3 or len(ordered[0].line.chars) > thresholds["furniture_top_max_chars"]:
        return
    head, after = ordered[0], ordered[1]
    boxes = [u.line.box for u in alignments if u.status == "unaligned"] + list(ink)
    if any(head.line.box[3] <= box[1] and box[3] <= after.line.box[1] + 2 for box in boxes):
        head.status = "furniture"


def _x_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    overlap = min(a[2], b[2]) - max(a[0], b[0])
    return max(0.0, overlap) / max(1, min(a[2] - a[0], b[2] - b[0]))


def _interpolate_between_neighbours(alignments: list[LineAlignment], thresholds: dict[str, float]) -> None:
    """Recover a misread line by position: the transcribed lines directly above and below it in the same column
    leave unmatched transcription text between their matches that could hold it (Tesseract's own line order can
    differ from the page's, so the order-based pass misses some)."""

    transcribed = [a for a in alignments if a.status in {"aligned", "interpolated"} and a.span]
    for a in alignments:
        if a.status != "unaligned":
            continue
        box, reach = a.line.box, 1.6 * max(1, a.line.height)
        column = [t for t in transcribed if _x_overlap(t.line.box, box) >= 0.5]
        above = [t for t in column if t.line.box[3] <= box[1] + 0.5 * a.line.height and box[1] - t.line.box[3] <= reach]
        below = [t for t in column if t.line.box[1] >= box[3] - 0.5 * a.line.height and t.line.box[1] - box[3] <= reach]
        if not above or not below:
            continue
        upper = max(above, key=lambda t: t.line.box[3])
        lower = min(below, key=lambda t: t.line.box[1])
        gap = lower.span[0] - upper.span[1]
        if thresholds["gap_min_share"] * len(a.line.chars) <= gap <= thresholds["gap_max_share"] * len(a.line.chars) + thresholds["gap_slack_chars"]:
            a.status, a.span = "interpolated", (upper.span[1], lower.span[0])


def _mark_furniture(alignments: list[LineAlignment], thresholds: dict[str, float]) -> None:
    """Running heads above all transcribed lines, and page numbers, catchwords and signatures below them."""

    transcribed = [a for a in alignments if a.status in {"aligned", "interpolated"}]
    if not transcribed:
        return
    top = min(a.line.box[1] for a in transcribed)
    bottom = max(a.line.box[3] for a in transcribed)
    above = sorted((a for a in alignments if a.status == "unaligned" and a.line.box[3] <= top + 2), key=lambda a: a.line.box[1])
    below = sorted((a for a in alignments if a.status == "unaligned" and a.line.box[1] >= bottom - 2), key=lambda a: -a.line.box[3])
    if len(_rows(above)) <= thresholds["furniture_top_lines"]:
        for a in above:
            if len(a.line.chars) <= thresholds["furniture_top_max_chars"]:
                a.status = "furniture"
    if len(_rows(below)) <= thresholds["furniture_bottom_lines"]:
        for a in below:
            if len(a.line.chars) <= thresholds["furniture_bottom_max_chars"]:
                a.status = "furniture"


def _rows(alignments: list[LineAlignment]) -> list[list[LineAlignment]]:
    """Group lines that share a printed row (overlapping vertically), e.g. a running head split in two."""

    rows: list[list[LineAlignment]] = []
    for a in sorted(alignments, key=lambda a: a.line.box[1]):
        if rows and a.line.box[1] < max(r.line.box[3] for r in rows[-1]) - 0.3 * a.line.height:
            rows[-1].append(a)
        else:
            rows.append([a])
    return rows


# --- Ink the OCR did not read ---------------------------------------------------------------------------------


def unrecognised_ink(grey: Any, lines: list[OcrLine], thresholds: dict[str, float] | None = None) -> list[tuple[int, int, int, int]]:
    """Printed regions no OCR line covers: bands of ink outside every readable OCR line box (render pixels).

    Tesseract can miss whole blocks (large vocalised verse, ornate type). Such a block is text-bearing but has no
    line to align, so without this check a page could be judged ``full_page`` with an untranscribed block on it.
    ``grey`` is a Pillow greyscale image of the render. Thin bands (rules, niqqud rows, stray marks) and narrow ones
    (scan borders, stamps) are ignored, and so are tall unbroken bands (illustrations, ornaments): printed lines are
    separated by blank rows, so a text band is at most a few line heights tall.
    """

    from PIL import Image

    thresholds = {**THRESHOLDS, **(thresholds or {})}
    cell = int(thresholds["ink_cell_px"])
    width, height = grey.size
    columns, rows = max(1, width // cell), max(1, height // cell)
    small = grey.resize((columns, rows), Image.BOX)
    values = list(small.getdata())
    background = sorted(values)[int(len(values) * 0.75)]
    dark = background - thresholds["ink_contrast"]
    readable = [line for line in lines if len(line.chars) >= 3]
    heights = sorted(line.height for line in readable) or [cell * 4]
    line_height = heights[len(heights) // 2]
    covered = [[False] * columns for _ in range(rows)]
    for line in readable:
        x0, y0, x1, y1 = line.box
        for row in range(max(0, y0 // cell - 1), min(rows, y1 // cell + 2)):
            for column in range(max(0, x0 // cell - 1), min(columns, x1 // cell + 2)):
                covered[row][column] = True
    edge_x, edge_y = max(1, int(columns * 0.03)), max(1, int(rows * 0.02))
    ink_rows: list[list[int]] = []
    for row in range(rows):
        cells = [
            column
            for column in range(edge_x, columns - edge_x)
            if edge_y <= row < rows - edge_y and values[row * columns + column] < dark and not covered[row][column]
        ]
        ink_rows.append(cells)
    regions: list[tuple[int, int, int, int]] = []
    row = 0
    min_cells = max(3, int(columns * 0.03))
    while row < rows:
        if len(ink_rows[row]) < min_cells:
            row += 1
            continue
        start = row
        gap = 0
        while row < rows and gap <= 1:
            gap = 0 if len(ink_rows[row]) >= min_cells else gap + 1
            row += 1
        end = row - gap
        band = [column for r in range(start, end) for column in ink_rows[r]]
        x0, x1 = min(band), max(band) + 1
        box = (x0 * cell, start * cell, x1 * cell, end * cell)
        band_height = box[3] - box[1]
        tall = thresholds["ink_min_line_heights"] * line_height <= band_height <= thresholds["ink_max_line_heights"] * line_height
        wide = box[2] - box[0] >= thresholds["ink_min_width_share"] * width
        density = len(band) / max(1, (x1 - x0) * (end - start))
        if tall and wide and density >= thresholds["ink_min_density"]:
            regions.append(box)
    return regions


# --- Decision and crop ----------------------------------------------------------------------------------------


def _union(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _centre_inside(box: tuple[int, int, int, int], region: tuple[int, int, int, int]) -> bool:
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    return region[0] <= cx <= region[2] and region[1] <= cy <= region[3]


def _normalised(box: tuple[float, float, float, float], width: int, height: int) -> list[float]:
    return [round(box[0] / width, 5), round(box[1] / height, 5), round(box[2] / width, 5), round(box[3] / height, 5)]


def located_share(alignments: list[LineAlignment], reference_length: int, statuses: frozenset[str] = frozenset({"aligned"})) -> float:
    """Share of the normalised transcription covered by the spans of lines with these statuses."""

    if reference_length <= 0:
        return 0.0
    spans = sorted(a.span for a in alignments if a.status in statuses and a.span)
    covered = 0
    current_start, current_end = None, None
    for start, end in spans:
        if current_end is None or start > current_end:
            if current_end is not None:
                covered += current_end - current_start
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        covered += current_end - current_start
    return min(1.0, covered / reference_length)


def _describe(boxes: list[tuple[int, int, int, int]], region: tuple[int, int, int, int] | None, height: int) -> str:
    """Where untranscribed text is, in words (no text): relative to the transcribed region, else the page."""

    places: list[str] = []
    for box in boxes:
        if region is None:
            cy = (box[1] + box[3]) / 2
            places.append("top" if cy < height / 3 else "bottom" if cy > 2 * height / 3 else "middle")
        elif box[3] <= region[1]:
            places.append("above")
        elif box[1] >= region[3]:
            places.append("below")
        elif box[2] <= region[0] or box[0] >= region[2]:
            places.append("beside")
        else:
            places.append("inside")
    counts = {place: places.count(place) for place in dict.fromkeys(places)}
    parts = [f"{count} {place}" for place, count in counts.items()]
    anchor = "the transcribed region" if region is not None else "the page"
    return f"untranscribed text located by OCR boxes: {', '.join(parts)} {anchor}"


def _longest_block(boxes: list[tuple[int, int, int, int]]) -> int:
    """The most lines in one run of vertically adjacent boxes in the same column (gap under one line height)."""

    best = 0
    remaining = sorted(boxes, key=lambda box: box[1])
    for start in remaining:
        run, current = 1, start
        for box in remaining:
            if box[1] <= current[1]:
                continue
            gap = box[1] - current[3]
            if gap <= (current[3] - current[1]) and _x_overlap(current, box) >= 0.5:
                run, current = run + 1, box
            elif box[1] > current[3] + 2 * (current[3] - current[1]):
                break
        best = max(best, run)
    return best


def _margin_mark(box: tuple[int, int, int, int], region: tuple[int, int, int, int], width: int, height: int, thresholds: dict[str, float]) -> bool:
    narrow = box[2] - box[0] <= thresholds["margin_mark_max_width_share"] * width
    centre = (box[0] + box[2]) / 2
    off_centre = abs(centre - width / 2) >= thresholds["margin_mark_min_offset_share"] * width
    top = box[3] <= region[1] + 2 and box[1] <= thresholds["margin_band_share"] * height
    bottom = box[1] >= region[3] - 2 and box[3] >= (1 - thresholds["margin_band_share"]) * height
    return narrow and off_centre and (top or bottom)


@dataclass
class _Region:
    """An untranscribed text-bearing region: an unaligned OCR line, or a band of ink no OCR line read."""

    box: tuple[int, int, int, int]
    kind: str  # line | ink
    chars: int = 0

    @property
    def area(self) -> int:
        return max(0, self.box[2] - self.box[0]) * max(0, self.box[3] - self.box[1])


def _untranscribed(alignments: list[LineAlignment], ink: list[tuple[int, int, int, int]]) -> list[_Region]:
    regions = [_Region(a.line.box, "line", len(a.line.chars)) for a in alignments if a.status == "unaligned"]
    return regions + [_Region(box, "ink") for box in ink]


def assess_page(
    alignments: list[LineAlignment],
    reference_length: int,
    width: int,
    height: int,
    thresholds: dict[str, float] | None = None,
    *,
    ink: list[tuple[int, int, int, int]] | None = None,
) -> dict[str, Any]:
    """Coverage verdict, transcribed region and crop for one aligned page (render pixel geometry).

    ``ink`` lists bands of print no OCR line read (``unrecognised_ink``); they count as untranscribed text.
    """

    thresholds = {**THRESHOLDS, **(thresholds or {})}
    ink = ink or []
    isolate_running_head(alignments, ink, thresholds)
    transcribed = [a for a in alignments if a.status in {"aligned", "interpolated"}]
    untranscribed = _untranscribed(alignments, ink)
    text_area = (sum(a.line.area for a in transcribed) + sum(r.area for r in untranscribed)) or 1
    untranscribed_area = sum(r.area for r in untranscribed)
    located = located_share(alignments, reference_length)
    bracketed = located_share(alignments, reference_length, frozenset({"aligned", "interpolated"}))
    aligned_scores = [a.score for a in alignments if a.status == "aligned"]
    quality = {
        "reference_located_share": round(located, 4),
        "reference_bracketed_share": round(bracketed, 4),
        "mean_line_match": round(sum(aligned_scores) / len(aligned_scores), 4) if aligned_scores else 0.0,
        "ocr_lines": len(alignments),
        "aligned_lines": len(aligned_scores),
        "interpolated_lines": sum(a.status == "interpolated" for a in alignments),
        "untranscribed_lines": sum(r.kind == "line" for r in untranscribed),
        "unread_ink_regions": len(ink),
        "furniture_lines": sum(a.status == "furniture" for a in alignments),
        "short_lines": sum(a.status == "short" for a in alignments),
        "noise_lines": sum(a.status == "noise" for a in alignments),
        "untranscribed_area_share": round(untranscribed_area / text_area, 4),
    }
    quality["alignment_score"] = round(bracketed * (0.5 + 0.5 * located) * (quality["mean_line_match"] ** 0.5), 4)
    result: dict[str, Any] = {"alignment": quality, "render": {"width": width, "height": height}}
    region = _union([a.line.box for a in transcribed]) if transcribed else None
    result["transcribed_region"] = _normalised(region, width, height) if region else None

    decidable = (
        reference_length > 0
        and region is not None
        and bracketed >= thresholds["decide_bracketed_min"]
        and located >= thresholds["decide_aligned_located_min"]
        and (len(aligned_scores) >= thresholds["decide_aligned_lines_min"] or located >= thresholds["decide_short_page_located_min"])
    )
    if not decidable:
        result["transcription_coverage"] = None
        result["outcome"] = "alignment_too_poor"
        result["missing"] = None
        # A crop is still offered for a page another check finds partial; it keeps its own thresholds.
        result["crop"] = crop_from_alignment(alignments, bracketed, width, height, thresholds, ink=ink, located=located)
        return result
    # Marks in the page corners above or below the transcribed region (library and digitization stamps, page
    # numbers) are outside the page body: they do not make a page partial, though the crop still excludes them.
    body = [r for r in untranscribed if not _margin_mark(r.box, region, width, height, thresholds)]
    body_area = sum(r.area for r in body)
    quality["margin_marks"] = len(untranscribed) - len(body)
    quality["untranscribed_body_area_share"] = round(body_area / text_area, 4)
    long_lines = [r for r in body if r.kind == "line" and r.chars >= thresholds["line_min_chars"]]
    body_ink = [r for r in body if r.kind == "ink"]
    if located >= thresholds["well_read_located_min"]:
        full = (
            not body_ink
            and body_area / text_area <= thresholds["full_page_untranscribed_area_max"]
            and len(long_lines) <= thresholds["full_page_untranscribed_lines_max"]
        )
    else:
        # A poorly read page (ornate or Rashi type) leaves more misread lines unaligned: a looser area tolerance, but
        # a block of adjacent unaligned lines in one column is untranscribed text, not scattered misreads.
        full = (
            not body_ink
            and body_area / text_area <= thresholds["poorly_read_untranscribed_area_max"]
            and _longest_block([r.box for r in body if r.kind == "line"]) < thresholds["poorly_read_block_lines_max"]
        )
    result["transcription_coverage"] = "full_page" if full else "partial_page"
    result["outcome"] = "decided"
    result["missing"] = None if full else _describe([r.box for r in untranscribed], region, height)
    result["crop"] = crop_from_alignment(alignments, bracketed, width, height, thresholds, ink=ink, located=located)
    return result


def crop_from_alignment(
    alignments: list[LineAlignment],
    bracketed: float,
    width: int,
    height: int,
    thresholds: dict[str, float] | None = None,
    *,
    ink: list[tuple[int, int, int, int]] | None = None,
    located: float = 1.0,
) -> dict[str, Any]:
    """The crop for this page's transcription: always computed, applied only when the page is ``partial_page``.

    The box is the union of the aligned and interpolated line boxes plus a margin; the margin stops halfway to any
    untranscribed region outside the union. Untranscribed regions whose centre lies inside the union stay inside
    the crop and are listed (``untranscribed_inside``) so evaluation can mask them.
    """

    thresholds = {**THRESHOLDS, **(thresholds or {})}
    transcribed = [a for a in alignments if a.status in {"aligned", "interpolated"}]
    untranscribed = _untranscribed(alignments, ink or [])
    crop: dict[str, Any] = {"method": CROP_METHOD}
    if not transcribed:
        return {**crop, "status": "unresolved", "reason": "transcription_not_located"}
    tight = _union([a.line.box for a in transcribed])
    margin = thresholds["crop_margin_line_heights"] * statistics.median(a.line.height for a in transcribed)
    x0, y0, x1, y1 = tight[0] - margin, tight[1] - margin, tight[2] + margin, tight[3] + margin
    for r in untranscribed:
        box = r.box
        if _centre_inside(box, tight):
            continue
        if box[3] <= tight[1] + 1 and box[2] > x0 and box[0] < x1:
            y0 = max(y0, (box[3] + tight[1]) / 2)
        if box[1] >= tight[3] - 1 and box[2] > x0 and box[0] < x1:
            y1 = min(y1, (box[1] + tight[3]) / 2)
        if box[2] <= tight[0] + 1 and box[3] > y0 and box[1] < y1:
            x0 = max(x0, (box[2] + tight[0]) / 2)
        if box[0] >= tight[2] - 1 and box[3] > y0 and box[1] < y1:
            x1 = min(x1, (box[0] + tight[2]) / 2)
    box = (max(0, int(x0)), max(0, int(y0)), min(width, int(round(x1))), min(height, int(round(y1))))
    inside = [r for r in untranscribed if _centre_inside(r.box, tight)]
    inside_area = sum(a.line.area for a in transcribed) + sum(r.area for r in inside)
    inside_share = sum(r.area for r in inside) / (inside_area or 1)
    crop.update(
        {
            "box_normalized": _normalised(box, width, height),
            "box_render_px": list(box),
            "margin_px": round(margin, 1),
            "untranscribed_inside": [_normalised(r.box, width, height) for r in inside],
            "untranscribed_inside_area_share": round(inside_share, 4),
        }
    )
    # On a poorly read page interpolation can absorb an untranscribed block set between transcribed ones (an
    # Italian translation between Hebrew commentary, say): such a crop is flagged for review.
    crop["review_recommended"] = located < thresholds["well_read_located_min"]
    if bracketed < thresholds["crop_bracketed_min"] or located < thresholds["decide_aligned_located_min"]:
        return {**crop, "status": "unresolved", "reason": "transcription_not_located"}
    if inside_share > thresholds["crop_untranscribed_inside_max"]:
        # One rectangle cannot leave the untranscribed text out (blocks interleaved with the transcription): try
        # several regions, one per run of transcribed lines, with everything else in the box masked (F8b5).
        regions = region_crop(transcribed, untranscribed, width, height, thresholds, margin)
        if regions is not None:
            return {**crop, **regions, "review_recommended": crop["review_recommended"]}
        return {**crop, "status": "unresolved", "reason": "untranscribed_text_inside_crop"}
    return {**crop, "status": "resolved", "reason": None}


def _intersection(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    return max(0.0, min(a[2], b[2]) - max(a[0], b[0])) * max(0.0, min(a[3], b[3]) - max(a[1], b[1]))


def _blocks_merge(box: tuple[int, int, int, int], untranscribed: list[_Region], thresholds: dict[str, float]) -> bool:
    """An untranscribed region stops two runs of transcribed lines from joining when the joined box would take in
    its centre or a large part of it."""

    for r in untranscribed:
        if _centre_inside(r.box, box) or _intersection(r.box, box) > thresholds["region_block_overlap_max"] * max(1, r.area):
            return True
    return False


def transcribed_blocks(lines: list[tuple[int, int, int, int]], untranscribed: list[_Region], thresholds: dict[str, float] | None = None) -> list[tuple[int, int, int, int]]:
    """Group transcribed line boxes into blocks no untranscribed region lies inside (render pixels, reading order).

    Blocks are joined nearest first (by vertical gap, then horizontal), and two blocks join only when the joined box
    keeps every untranscribed region out. Interleaved untranscribed text (a verse or a translation between two
    passages of commentary) therefore splits the transcription into separate blocks.
    """

    thresholds = {**THRESHOLDS, **(thresholds or {})}
    blocks = [tuple(box) for box in lines]
    while len(blocks) > 1:
        candidates = []
        for i in range(len(blocks)):
            for j in range(i + 1, len(blocks)):
                a, b = blocks[i], blocks[j]
                gap_y = max(0, max(a[1], b[1]) - min(a[3], b[3]))
                gap_x = max(0, max(a[0], b[0]) - min(a[2], b[2]))
                candidates.append((gap_y, gap_x, i, j))
        candidates.sort()
        merged = False
        for _, _, i, j in candidates:
            union = _union([blocks[i], blocks[j]])
            if not _blocks_merge(union, untranscribed, thresholds):
                blocks = [box for k, box in enumerate(blocks) if k not in {i, j}] + [union]
                merged = True
                break
        if not merged:
            break
    # reading order: top to bottom; blocks side by side (columns) right to left
    return sorted(blocks, key=lambda box: (box[1] // max(1, thresholds["region_row_px"]), -box[2]))


def region_crop(
    transcribed: list[LineAlignment],
    untranscribed: list[_Region],
    width: int,
    height: int,
    thresholds: dict[str, float],
    margin: float,
) -> dict[str, Any] | None:
    """A multi-region crop (``ocr_alignment_region_mask.v1``): one box per block of transcribed lines, each with the
    crop margin stopped halfway to any untranscribed region outside it. The pair image is the union box with every
    pixel outside the regions masked to the page background, so the regions' own pixels are unchanged. Returns
    ``None`` when the blocks still take in too much untranscribed text, or there are too many of them."""

    blocks = transcribed_blocks([a.line.box for a in transcribed], untranscribed, thresholds)
    if len(blocks) < 2 or len(blocks) > thresholds["region_max_count"]:
        return None
    regions: list[tuple[int, int, int, int]] = []
    for tight in blocks:
        x0, y0, x1, y1 = tight[0] - margin, tight[1] - margin, tight[2] + margin, tight[3] + margin
        for r in untranscribed:
            box = r.box
            if _centre_inside(box, tight):
                continue
            if box[3] <= tight[1] + 1 and box[2] > x0 and box[0] < x1:
                y0 = max(y0, (box[3] + tight[1]) / 2)
            if box[1] >= tight[3] - 1 and box[2] > x0 and box[0] < x1:
                y1 = min(y1, (box[1] + tight[3]) / 2)
            if box[2] <= tight[0] + 1 and box[3] > y0 and box[1] < y1:
                x0 = max(x0, (box[2] + tight[0]) / 2)
            if box[0] >= tight[2] - 1 and box[3] > y0 and box[1] < y1:
                x1 = min(x1, (box[0] + tight[2]) / 2)
        regions.append((max(0, int(x0)), max(0, int(y0)), min(width, int(round(x1))), min(height, int(round(y1)))))
    inside = [r for r in untranscribed if any(_centre_inside(r.box, block) for block in blocks)]
    text_area = sum(a.line.area for a in transcribed) + sum(r.area for r in inside)
    inside_share = sum(r.area for r in inside) / (text_area or 1)
    if inside_share > thresholds["crop_untranscribed_inside_max"]:
        return None
    union = _union(regions)
    masked = [r for r in untranscribed if r not in inside and _intersection(r.box, union) > 0]
    return {
        "method": CROP_REGIONS_METHOD,
        "status": "resolved",
        "reason": None,
        "box_normalized": _normalised(union, width, height),
        "box_render_px": list(union),
        "regions_normalized": [_normalised(box, width, height) for box in regions],
        "regions_render_px": [list(box) for box in regions],
        "untranscribed_inside": [_normalised(r.box, width, height) for r in inside],
        "untranscribed_inside_area_share": round(inside_share, 4),
        "masked_untranscribed": len(masked),
    }


# --- Tool checks ----------------------------------------------------------------------------------------------


def tool_check(
    page: dict[str, Any],
    commons_sha1: str,
    assessment: dict[str, Any],
    *,
    render: dict[str, Any],
    engine: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    """A ``wikisource_page_render_checks.v1`` check made by this tool (``checked_by: tool``)."""

    return {
        "page_title": page["page_title"],
        "page_id": page.get("page_id"),
        "revision_id": page["revision_id"],
        "index_key": page["index_key"],
        "quality": page.get("quality"),
        "commons_file_sha1": commons_sha1,
        "scan_page": page.get("page_number") or int(str(page["page_title"]).rsplit("/", 1)[1]),
        "transcription_coverage": assessment["transcription_coverage"],
        "missing": assessment.get("missing"),
        "outcome": assessment["outcome"],
        "checked_by": "tool",
        "checker": f"hocrgen.tools.wikisource_coverage {TOOL_VERSION}",
        "checked_at": checked_at,
        "method": METHOD_ID,
        "render_url": render.get("render_url"),
        "render_sha256": render.get("sha256"),
        "render_size": [assessment["render"]["width"], assessment["render"]["height"]],
        "ocr_engine": engine,
        "alignment": assessment["alignment"],
        "transcribed_region": assessment["transcribed_region"],
        "crop": assessment["crop"],
    }


COMPACT_ALIGNMENT_KEYS = ("reference_located_share", "reference_bracketed_share", "alignment_score", "untranscribed_body_area_share")


def _round_boxes(value: Any) -> Any:
    """Boxes to three decimals (a thousandth of the page: about one render pixel)."""

    if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
        return [round(item, 3) for item in value]
    if isinstance(value, list):
        return [_round_boxes(item) for item in value]
    return value


def compact_tool_checks(payload: dict[str, Any]) -> dict[str, Any]:
    """The committed form of a tool-checks file: shared engine and method text in the header, rounded scores, and no
    render URL (the render is pinned by its SHA-256). Still ``wikisource_page_render_checks.v1``. No OCR or page text."""

    engines: dict[str, dict[str, Any]] = {}
    shared = ("checked_by", "checker", "checked_at", "method", "ocr_engine")
    rows = []
    for check in payload["checks"]:
        engine = {key: value for key, value in (check.get("ocr_engine") or {}).items() if key != "pass"}
        engine_id = f"tesseract_{hashlib.sha256(json.dumps(engine, sort_keys=True).encode()).hexdigest()[:8]}"
        engines[engine_id] = engine
        crop = check["crop"]
        keep_inside = crop.get("status") == "resolved"
        row = {
            **{key: check.get(key) for key in ("page_title", "revision_id", "commons_file_sha1", "scan_page")},
            "transcription_coverage": check["transcription_coverage"],
            "outcome": check["outcome"],
            **{key: check[key] for key in ("checked_by", "checker", "checked_at", "method")},
            "ocr_engine": engine_id,
            "ocr_pass": (check.get("ocr_engine") or {}).get("pass"),
            "render_sha256": check.get("render_sha256"),
            "render_size": check.get("render_size"),
            "alignment": {key: round(check["alignment"][key], 3) for key in COMPACT_ALIGNMENT_KEYS if key in check["alignment"]},
            "crop": {
                key: _round_boxes(crop.get(key))
                for key in ("status", "reason", "method", "box_normalized", "regions_normalized", "untranscribed_inside", "untranscribed_inside_area_share", "review_recommended")
                if crop.get(key) not in (None, [], False)
                and (keep_inside or key not in {"untranscribed_inside", "untranscribed_inside_area_share", "regions_normalized"})
                and not (key == "method" and crop.get(key) == CROP_METHOD)
            },
        }
        if check.get("missing"):
            row["missing"] = check["missing"]
        rows.append(row)
    # Values every check shares are stated once (``check_defaults``) and restored on load.
    defaults = {key: rows[0][key] for key in shared if rows and all(row[key] == rows[0][key] for row in rows)}
    checks = [{key: value for key, value in row.items() if key not in defaults} for row in rows]
    return {
        "schema_version": payload["schema_version"],
        "description": payload["description"] + f" Compact form: render URLs dropped (renders are pinned by SHA-256), boxes to three decimals, values every check shares in check_defaults; crop method {CROP_METHOD} unless a crop names {CROP_REGIONS_METHOD}.",
        "tool_version": payload["tool_version"],
        "thresholds": payload["thresholds"],
        "methods": payload["methods"],
        "ocr_engines": dict(sorted(engines.items())),
        "check_defaults": defaults,
        "checks": checks,
    }


def dump_checks(payload: dict[str, Any]) -> str:
    """JSON with one check per line, so a review diff shows the pages that changed."""

    head = {key: value for key, value in payload.items() if key != "checks"}
    body = ",\n".join("  " + json.dumps(check, ensure_ascii=False, sort_keys=True) for check in payload["checks"])
    text = json.dumps(head, ensure_ascii=False, indent=1)[:-2]
    return f'{text},\n "checks": [\n{body}\n ]\n}}\n'


# --- Operator paths: OCR and capture --------------------------------------------------------------------------


def tesseract_engine(executable: str, tessdata: Path | None, language: str = "heb") -> dict[str, Any]:  # pragma: no cover - operator
    version = subprocess.run([executable, "--version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    data_dir = tessdata or Path(subprocess.run([executable, "--list-langs"], capture_output=True, text=True).stdout.split('"')[1])
    model = data_dir / f"{language}.traineddata"
    return {
        "name": "tesseract",
        "version": version,
        "language": language,
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "passes": [f"psm{psm}-{preprocess}" for psm, preprocess in OCR_PASSES],
        "preprocess": f"greyscale, {OCR_SCALE}x Lanczos upscale (flattened: shading divided out); boxes mapped back to render pixels",
        "use": "line_and_word_boxes_only",
    }


OCR_SCALE = 2  # Commons renders at 960 px are about 125 dpi; Tesseract finds lines far better at twice that
# OCR passes, tried in order until one decides the page with a resolvable crop; the best-aligned pass is kept:
# automatic layout, single-column layout, then automatic layout on a background-flattened image (shaded scans)
OCR_PASSES: tuple[tuple[int, str], ...] = ((3, "plain"), (4, "plain"), (3, "flattened"))


def ocr_input(image: Path, scale: int, preprocess: str) -> Any:  # pragma: no cover - operator
    """The image Tesseract reads: greyscale, upscaled; ``flattened`` also divides out the page's shading."""

    from PIL import Image, ImageChops, ImageFilter, ImageOps

    with Image.open(image) as opened:
        grey = opened.convert("L")
    grey = grey.resize((grey.width * scale, grey.height * scale), Image.LANCZOS)
    if preprocess == "flattened":
        background = grey.filter(ImageFilter.MaxFilter(15)).filter(ImageFilter.GaussianBlur(20))
        grey = ImageOps.autocontrast(ImageChops.add(grey, ImageChops.invert(background)), cutoff=1)
    return grey


def run_tesseract(image: Path, executable: str, *, language: str = "heb", psm: int = 3, scale: int = OCR_SCALE, preprocess: str = "plain") -> str:  # pragma: no cover - operator
    with tempfile.TemporaryDirectory(prefix="hocrgen-coverage-") as temp:
        source = Path(temp) / "page.png"
        ocr_input(image, scale, preprocess).save(source)
        target = Path(temp) / "out"
        env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
        subprocess.run(
            [executable, str(source), str(target), "-l", language, "--psm", str(psm), "tsv"],
            capture_output=True, check=True, env=env, timeout=900,
        )
        return target.with_suffix(".tsv").read_text(encoding="utf-8")


def cached_ocr(image: Path, cache: Path, executable: str, *, language: str = "heb", psm: int = 3, scale: int = OCR_SCALE, preprocess: str = "plain") -> str:  # pragma: no cover - operator
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    suffix = "" if preprocess == "plain" else f".{preprocess}"
    path = cache / f"{digest}.{language}.psm{psm}.x{scale}{suffix}.tsv"
    if path.exists():
        return path.read_text(encoding="utf-8")
    tsv = run_tesseract(image, executable, language=language, psm=psm, scale=scale, preprocess=preprocess)
    cache.mkdir(parents=True, exist_ok=True)
    path.write_text(tsv, encoding="utf-8")
    return tsv


def scaled_lines(tsv: str, scale: int) -> list[OcrLine]:
    """Lines from an upscaled OCR run, with boxes mapped back to the render's own pixels."""

    lines = parse_tesseract_tsv(tsv)
    for line in lines:
        line.box = tuple(int(round(value / scale)) for value in line.box)  # type: ignore[assignment]
    return lines


def assess_render(image: Path, text: str, cache: Path, executable: str) -> tuple[dict[str, Any], str]:  # pragma: no cover - operator
    """OCR (``OCR_PASSES`` in order, stopping at the first that decides with a resolvable crop), align, assess.

    Returns the best-aligned pass's assessment and the pass's name (``psm3-plain``, ...)."""

    from PIL import Image

    with Image.open(image) as opened:
        grey = opened.convert("L")
    width, height = grey.size
    best: tuple[dict[str, Any], str] | None = None
    for psm, preprocess in OCR_PASSES:
        lines = scaled_lines(cached_ocr(image, cache, executable, psm=psm, preprocess=preprocess), OCR_SCALE)
        alignments, reference = align_page(lines, text)
        assessment = assess_page(alignments, len(reference), width, height, ink=unrecognised_ink(grey, lines))
        if best is None or assessment["alignment"]["alignment_score"] > best[0]["alignment"]["alignment_score"]:
            best = (assessment, f"psm{psm}-{preprocess}")
        if assessment["alignment"]["reference_bracketed_share"] >= THRESHOLDS["crop_bracketed_min"] and assessment["outcome"] == "decided":
            break
    assert best is not None
    return best


def render_slug(page: dict[str, Any]) -> str:
    return f"{page['index_key']}__p{int(page['page_title'].rsplit('/', 1)[1]):04d}"


def capture_renders(inventory: dict[str, Any], out_dir: Path, *, width: int = RENDER_WIDTH, delay: float = 1.0) -> None:  # pragma: no cover - network
    """Fetch the Commons render of every page in the inventory (operator capture; cached in ``renders.jsonl``)."""

    files = {record["index_key"]: record["commons_file"] for record in inventory["indexes"]}
    out_dir.mkdir(parents=True, exist_ok=True)
    log = out_dir / "renders.jsonl"
    done = {json.loads(line)["slug"] for line in log.read_text().splitlines()} if log.exists() else set()
    thumb_bases: dict[str, tuple[str, str]] = {}
    for page in inventory["pages"]:
        number = page["page_title"].rsplit("/", 1)[1]
        if not number.isdigit() or render_slug(page) in done:
            continue
        commons = files[page["index_key"]]
        if page["index_key"] not in thumb_bases:
            api = "https://commons.wikimedia.org/w/api.php" if commons.get("repository") == "commons" else "https://he.wikisource.org/w/api.php"
            query = urllib.parse.urlencode({"action": "query", "titles": commons["title"], "prop": "imageinfo", "iiprop": "url|sha1",
                                            "iiurlwidth": width, "iiurlparam": f"page1-{width}px", "format": "json", "formatversion": 2})
            info = _get(f"{api}?{query}")["query"]["pages"][0]["imageinfo"][0]
            thumb_bases[page["index_key"]] = (info["thumburl"].split("?", 1)[0], info["sha1"])
            time.sleep(delay)
        base, sha1 = thumb_bases[page["index_key"]]
        url = re.sub(r"/page1-\d+px-", f"/page{int(number)}-{width}px-", base, count=1)
        data = _get(url, binary=True)
        slug = render_slug(page)
        (out_dir / f"{slug}.jpg").write_bytes(data)
        record = {"slug": slug, "index_key": page["index_key"], "page": int(number), "page_title": page["page_title"],
                  "commons_file": commons["title"], "commons_file_sha1": sha1, "pinned_commons_sha1": commons.get("sha1"),
                  "render_url": url, "requested_width": width, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        with log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        time.sleep(delay)


def _get(url: str, *, binary: bool = False) -> Any:  # pragma: no cover - network
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as response:
                return response.read() if binary else json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504}:
                time.sleep(min(60, 5 * 2**attempt))
                continue
            raise
    raise RuntimeError(f"request kept failing: {url}")


def _check_one(job: tuple[dict[str, Any], str, Path, dict[str, Any], str, Path, str, dict[str, Any], str]) -> dict[str, Any]:  # pragma: no cover - operator
    page, text, image, render, sha1, cache, executable, engine, checked_at = job
    assessment, ocr_pass = assess_render(image, text, cache, executable)
    return tool_check(page, sha1, assessment, render=render, engine={**engine, "pass": ocr_pass}, checked_at=checked_at)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - operator path
    parser = argparse.ArgumentParser(description="Tool coverage checks and crops for Wikisource pages by OCR-box alignment (operator).")
    parser.add_argument("--inventory", type=Path, required=True, help="Full operator inventory JSON (wikisource_inventory.json).")
    parser.add_argument("--snapshot", type=Path, required=True, help="Operator snapshot root with text/.")
    parser.add_argument("--renders", type=Path, required=True, help="Folder with the Commons page renders and renders.jsonl.")
    parser.add_argument("--ocr-cache", type=Path, required=True, help="Folder caching Tesseract TSV output by render SHA-256.")
    parser.add_argument("--capture", action="store_true", help="Fetch missing renders from Commons first (network).")
    parser.add_argument("--checked-at", required=True)
    parser.add_argument("--out", type=Path, required=True, help="Write the full tool checks (wikisource_page_render_checks.v1) here.")
    parser.add_argument("--compact-out", type=Path, help="Also write the committed compact form, e.g. docs/wikisource_page_tool_checks.json.")
    parser.add_argument("--tesseract", default="tesseract")
    parser.add_argument("--tessdata", type=Path)
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    parser.add_argument("--only", type=Path, help="Check only the page titles listed in this file (one per line).")
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    if args.capture:
        capture_renders(inventory, args.renders)
    renders = {json.loads(line)["slug"]: json.loads(line) for line in (args.renders / "renders.jsonl").read_text().splitlines() if line.strip()}
    sha1s = {record["index_key"]: record["commons_file"]["sha1"] for record in inventory["indexes"]}
    only = set(args.only.read_text(encoding="utf-8").splitlines()) if args.only else None
    engine = tesseract_engine(args.tesseract, args.tessdata)
    jobs = []
    for page in inventory["pages"]:
        if only is not None and page["page_title"] not in only:
            continue
        if not page["page_title"].rsplit("/", 1)[1].isdigit():
            continue
        slug = render_slug(page)
        text_path = args.snapshot / "text" / f"{slug}.txt"
        render = renders.get(slug)
        if render is None or not text_path.is_file() or render.get("commons_file_sha1") != sha1s.get(page["index_key"]):
            continue
        jobs.append((page, text_path.read_text(encoding="utf-8"), args.renders / f"{slug}.jpg", render, sha1s[page["index_key"]],
                     args.ocr_cache, args.tesseract, engine, args.checked_at))
    with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
        checks = list(pool.map(_check_one, jobs, chunksize=4))
    payload = {
        "schema_version": "wikisource_page_render_checks.v1",
        "description": "Tool coverage checks and crops (F8b4): OCR used for localisation only, never as text.",
        "tool_version": TOOL_VERSION,
        "thresholds": THRESHOLDS,
        "methods": {METHOD_ID: METHOD_TEXT},
        "checks": sorted(checks, key=lambda check: (check["index_key"], check["scan_page"] or 0)),
    }
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.compact_out:
        args.compact_out.write_text(dump_checks(compact_tool_checks(payload)), encoding="utf-8")
    decided = sum(check["outcome"] == "decided" for check in checks)
    sys.stdout.write(f"{len(checks)} pages checked, {decided} decided\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
