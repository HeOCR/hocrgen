"""Real scanned line sets from Hebrew Wikisource proofread pages (R8 data, operator tool).

Subcommands:

- ``build`` cuts line images from the pinned Commons renders of a tranche's Wikisource snapshot and labels each line
  with the **human Wikisource page text** that the coverage tool's alignment (``hocrgen.tools.wikisource_coverage``)
  places on it. OCR gives line boxes and chooses between candidate word boundaries at a line's edges; **its text is
  never a label and is never written out.** The output has the shape of ``bynli_lines_v2``
  (``{train,dev}/<index_key>/<id>.png`` with a ``.gt.txt`` each, ``manifest.jsonl`` and ``summary.json``), so the
  Tesseract tooling that reads that set reads this one unchanged.
- ``fetch-hires`` fetches the 1920 px Commons render of listed pages (the pinned renders are 960 px), at most one
  request per second. ``build`` checks each against the pinned 960 px render before cutting from it.
- ``verify`` checks a built set: no row from a held-out or reserved Index or a dropped page, no niqqud in any label,
  licence and attribution on every row, non-null image sha256 that match the files.

Pages: quality 3 or 4 pages of the snapshot that pass the unchanged ``page_exclusion_reasons`` gate, whose image and
pair text match their pinned sha256. The pair text is the snapshot's (``wikisource_plain_text.v3`` with the reviewed
adjustments), so unprinted notes are already gone. A partial page (``partial_page``) keeps only lines whose box centre
lies inside its crop (and inside one of its regions, for a multi-region crop). Lines that touch an ``excluded_spans``
range (text the scan does not show) are dropped. A page whose text carries niqqud on ``POINTED_PAGE_DENSITY`` marks per
letter or more is a pointed page and is dropped whole.

Lines: the coverage tool's ``align_page`` on the cached Tesseract boxes (``<render sha256>.heb.psm{3,4}.x2[.flattened]
.tsv``, the pass that aligns the most text). Only ``aligned`` lines (not interpolated ones) with a trigram share of at
least ``--min-score`` are used. Their span in the normalised text is mapped back to the page text and snapped to word
boundaries (within two words of each edge, keeping the span whose letters best match the line's OCR letters); then
the line gates of ``benyehuda_nli_lines``: a line that still matches its OCR below ``MIN_OCR_SIMILARITY``, is taller
than ``MAX_HEIGHT_RATIO`` times the page's median aligned line, carries a ``[n]`` footnote mark, crosses a paragraph,
carries pointing (``POINTED_LINE_DENSITY``) or cantillation, has characters outside the repertoire or overlaps the span
of another line is dropped. Labels: NFC, niqqud and cantillation removed (maqaf, geresh, gershayim and dashes kept),
the folds of ``bynli_lines_v2``, whitespace collapsed, logical order.

Rights: every page passes ``wikisource_justification.wikisource_page_blocker`` (an accepted Route C justification,
Google hygiene; drops counted by reason), each row carries its Index's ``rights_justification_id``, and lines under a
page's ``google_watermark_bbox`` are dropped (``google_watermark_overlap``).

Index holdouts follow a named exclusion policy (``EXCLUSION_POLICIES``, ``--policy``): whole Indexes (the audit2
Indexes, the release ``test`` split, other volumes of audit2 works, line_verify Indexes ...) and single pages (the
line_verify pages, the E2d3d evaluation pages). Every row is silver training data: ``adjudication_status:
not_adjudicated`` and ``reference_eligible: false``, quality 4 included.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hocrgen.tools import wikisource_coverage as cov
from hocrgen.tools.benyehuda_nli_lines import ALLOWED, CANTILLATION, FOLD, LETTER, MAX_HEIGHT_RATIO, MIN_OCR_SIMILARITY, label, niqqud_density

TOOL = "hocrgen.tools.wikisource_lines"
TOOL_VERSION = "0.1.0"
SCHEMA = "s16c_wikisource_lines.v1"
SOURCE_ID = "wikisource_he_proofread"
USER_AGENT = "HeOCR-research/0.1 (+https://github.com/HeOCR)"
MIN_SCORE = 0.5  # trigram share on one diagonal band; the coverage tool aligns from 0.30
POINTED_PAGE_DENSITY = 0.3  # niqqud marks per letter over a page's text: a pointed page, dropped whole
POINTED_LINE_DENSITY = 0.1  # niqqud marks per letter in a line's text: a pointed line (quoted verse), dropped
# line box height / median word height, against the page's median over its aligned lines: above this factor one OCR
# "line" spans two printed rows (small type, a marginal gloss)
MAX_ROWS_RATIO = 1.3
# letters in the OCR line / letters in the label: outside this band the box holds text the label lacks (a marginal
# gloss Tesseract joined to the line) or the label holds text the box lacks
LENGTH_RATIO_BAND = (0.8, 1.25)
MIN_LINE_CHARS = 8  # letters and digits; a shorter line (a running head, a lone word) can match the text anywhere
HIRES_WIDTH = 1920
MAX_HIRES_MEAN_DIFF = 12.0  # grey levels, the hi-res render downscaled to the pinned 960 px render (as line_verify)
OCR_PASSES = (("psm3", ""), ("psm4", ""), ("psm3", ".flattened"))
FOOTNOTE_MARK = re.compile(r"\[\d+\]")
TEXT_LICENCE = "CC BY-SA 4.0"
TEXT_LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
ATTRIBUTION = "Hebrew Wikisource contributors"
SCAN_SOURCE = "wikimedia_commons"
SOURCE_CLASS = "wikisource_proofread_commons_scan"
SCRIPTS = ("square", "rashi")

# --- Exclusion policy -----------------------------------------------------------------------------------------
# Whole-Index rules and page rules. Each rule is computed from its input file, so a policy re-derives.
INDEX_RULES = {
    "audit2": "the Index has an adjudicated (audit2) page in the E2d3d eval set (--eval-set, stratum adjudicated)",
    "release_test": "the Index is in the release test split (--split-manifest)",
    "related_work_of_audit2": "another volume or edition of an audit2 work (same title core, ``related_works``)",
    "line_verify_index": "the Index has a page in a line_verify batch (--line-verify)",
    "line_verify_index_in_heldout_split": "the Index has a page in a line_verify batch and is in the release "
                                          "validation or test split",
    "manual": "named with --hold-out",
}
PAGE_RULES = {
    "line_verify_page": "the page is in a line_verify batch (--line-verify): its lines are future line references",
    "eval_set_page": "the page is in the E2d3d eval set (--eval-set), adjudicated or single-reviewer",
}
EXCLUSION_POLICIES: dict[str, dict[str, Any]] = {
    "A": {"description": "as first briefed: audit2, release test, line_verify Indexes and other volumes of audit2 "
                         "works held out whole; E2d3d eval pages dropped",
          "index_rules": ["audit2", "release_test", "related_work_of_audit2", "line_verify_index"],
          "page_rules": ["eval_set_page"]},
    "B": {"description": "audit2, release test and other volumes of audit2 works held out whole; line_verify and "
                         "E2d3d eval pages dropped page by page",
          "index_rules": ["audit2", "release_test", "related_work_of_audit2"],
          "page_rules": ["line_verify_page", "eval_set_page"]},
    "C": {"description": "heocr-lead 2026-11-11: audit2, release test, other volumes of audit2 works and the "
                         "line_verify Indexes of the release validation split held out whole; line_verify and E2d3d "
                         "eval pages dropped page by page (in every other Index)",
          "index_rules": ["audit2", "release_test", "related_work_of_audit2", "line_verify_index_in_heldout_split"],
          "page_rules": ["line_verify_page", "eval_set_page"]},
}

RESERVE_V1 = {
    "waived": True,
    "decision": "heocr-lead 2026-11-11",
    "why": "The audit2 and release-test Indexes, held out whole, already hold most of Hebrew Wikisource's proofread "
           "rabbinic print as evaluation; reserving one more rabbinic Index from the small remainder would leave "
           "training almost no rabbinic lines.",
    "obligation": "The first 5(b) batch (rabbinic open texts aligned to public-domain scans) must reserve one dense, "
                  "abbreviation-heavy rabbinic edition, as a whole work in neither train nor dev, as the future "
                  "rabbinic eval or line_verify source.",
}

# --- Related works (other volumes or editions) ------------------------------------------------------------------
_TITLE_STOP = {"ספר", "חלק", "כרך", "מהדורת", "מהדורה", "pdf", "ראשון", "שני", "שלישי", "רביעי", "חמישי", "א", "ב", "ג",
               "ד", "ה", "ו"}
_TITLE_WORD = re.compile(r"[א-ת]+|[a-z]+")


def title_core(title: str) -> tuple[str, ...]:
    """The first two content words of a work title: volume words, ``ספר`` and Hebrew numerals out, a leading
    article ``ה`` dropped from each word, final forms kept as typed (``דורות הראשונים`` == ``דורות ראשונים``)."""

    words = []
    for word in _TITLE_WORD.findall(unicodedata.normalize("NFC", title).casefold()):
        if word in _TITLE_STOP or (len(word) <= 2 and re.fullmatch("[א-ת]+", word) and word not in {"אב", "אל"}):
            continue
        if word.startswith("ה") and len(word) > 3:
            word = word[1:]
        words.append(word)
    return tuple(words[:2])


def related_works(indexes: Mapping[str, Mapping[str, Any]], targets: Iterable[str]) -> dict[str, list[str]]:
    """Indexes (not in ``targets``) whose work title core equals a target's: other volumes or editions."""

    targets = set(targets)
    cores = {key: title_core(str((record.get("work") or {}).get("title") or record.get("index_title") or ""))
             for key, record in indexes.items()}
    out: dict[str, list[str]] = {}
    for key, core in sorted(cores.items()):
        if key in targets or not core:
            continue
        hits = sorted(t for t in targets if cores.get(t) == core)
        if hits:
            out[key] = hits
    return out


def _creators(record: Mapping[str, Any]) -> set[str]:
    return {str(c.get("name")) for c in (record.get("work") or {}).get("creators") or [] if c.get("name")}


def same_creator_other_works(indexes: Mapping[str, Mapping[str, Any]], targets: Iterable[str],
                             related: Mapping[str, Any]) -> dict[str, list[str]]:
    """Informational: Indexes sharing a named creator with a target but not its title core (a different work)."""

    targets = set(targets)
    out: dict[str, list[str]] = {}
    for key, record in sorted(indexes.items()):
        if key in targets or key in related:
            continue
        hits = sorted(t for t in targets if _creators(record) & _creators(indexes[t]))
        if hits:
            out[key] = hits
    return out


@dataclass
class Exclusions:
    policy: str
    held_out: dict[str, list[str]] = field(default_factory=dict)  # index_key -> rules
    dropped_pages: dict[str, list[str]] = field(default_factory=dict)  # source_item_id -> rules
    related: dict[str, list[str]] = field(default_factory=dict)
    same_creator: dict[str, list[str]] = field(default_factory=dict)
    release_split: dict[str, str] = field(default_factory=dict)  # index_key -> split


def _item_key(item_id: str) -> str:
    return item_id.split(":", 1)[-1].split("#", 1)[0]


def exclusions(policy: str, indexes: Mapping[str, Mapping[str, Any]], pages: Sequence[Mapping[str, Any]], *,
               eval_set: Mapping[str, Any] | None, split_manifest: Mapping[str, Any] | None,
               line_verify: Sequence[Mapping[str, Any]], manual: Mapping[str, str] | None = None) -> Exclusions:
    """Apply a named policy to the snapshot: which Indexes are held out whole and which pages are dropped, and why."""

    rules = EXCLUSION_POLICIES[policy]
    page_split = {}
    for item in (split_manifest or {}).get("items", []):
        if str(item.get("item_id", "")).startswith(SOURCE_ID + ":"):
            page_split[_item_key(item["item_id"])] = item["split"]
    index_split: dict[str, str] = {}
    for page in pages:
        split = page_split.get(page["source_item_id"])
        if split:
            index_split.setdefault(page["index_key"], split)
    eval_items = (eval_set or {}).get("items", [])
    audit2 = {item["index_key"] for item in eval_items if item.get("stratum") == "adjudicated"}
    eval_pages = {_item_key(item["item_id"]) for item in eval_items}
    lv_pages = set()
    for batch in line_verify:
        for page in batch.get("pages", []):
            if str(page.get("page_id", "")).startswith(SOURCE_ID + ":"):
                lv_pages.add(_item_key(page["page_id"]))
    lv_indexes = {key.split("__", 1)[0] for key in lv_pages}
    test = {key for key, split in index_split.items() if split == "test"}
    related = related_works(indexes, audit2)
    found: dict[str, set[str]] = {
        "audit2": audit2, "release_test": test, "related_work_of_audit2": set(related),
        "line_verify_index": lv_indexes,
        "line_verify_index_in_heldout_split": {k for k in lv_indexes if index_split.get(k) in {"validation", "test"}},
        "manual": set(manual or {}),
    }
    out = Exclusions(policy=policy, related=related, release_split=index_split,
                     same_creator=same_creator_other_works(indexes, audit2, related))
    for rule in rules["index_rules"] + ["manual"]:
        for key in sorted(found[rule]):
            out.held_out.setdefault(key, []).append(rule)
    page_found = {"line_verify_page": lv_pages, "eval_set_page": eval_pages}
    for rule in rules["page_rules"]:
        for key in sorted(page_found[rule]):
            out.dropped_pages.setdefault(key, []).append(rule)
    return out


# --- Text and alignment ---------------------------------------------------------------------------------------


def normalised_with_offsets(text: str) -> tuple[str, list[int]]:
    """The coverage tool's alignment string of ``text`` (``wikisource_coverage.alignment_string``) with the offset in
    ``text`` of each of its characters."""

    masked = set()
    for m in cov._NOTE_MARKER.finditer(text):
        masked.update(range(m.start(), m.end()))
    chars, offsets = [], []
    for i, char in enumerate(text):
        if i in masked:
            continue
        for ch in unicodedata.normalize("NFKC", char):
            if unicodedata.category(ch)[0] in "LN":
                for out in ch.translate(cov._FINAL_FORMS).casefold():
                    chars.append(out)
                    offsets.append(i)
    return "".join(chars), offsets


def _tokens(text: str, lo: int, hi: int) -> list[tuple[int, int]]:
    """Word spans in ``text[lo:hi]``, also split after a hyphen or maqaf (prints break compounds across lines)."""

    toks = []
    for m in re.finditer(r"\S+", text[lo:hi]):
        a, b = lo + m.start(), lo + m.end()
        for h in re.finditer("[-־]", text[a:b - 1]):
            toks.append((a, a + h.end()))
            a = a + h.end()
        toks.append((a, b))
    return toks


def _sim(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() if a and b else 0.0


def refine_span(text: str, start: int, end: int, ocr_chars: str, reach: int = 2) -> tuple[int, int, float, float]:
    """Snap an approximate span to whole words: among word boundaries within ``reach`` words of each edge (and never
    across a line break), keep the span whose letters best match the line's OCR letters (``ocr_chars``, normalised).
    Returns (start, end, similarity before, similarity after). The label is the page text, never the OCR."""

    lo = text.rfind("\n", 0, start) + 1
    hi = text.find("\n", end)
    hi = len(text) if hi < 0 else hi
    toks = _tokens(text, max(lo, start - 150), min(hi, end + 150))
    before = _sim(cov.alignment_string(text[start:end]), ocr_chars)
    if not toks:
        return start, end, before, before
    i0 = next((k for k, (a, b) in enumerate(toks) if b > start), len(toks) - 1)
    j0 = max((k for k, (a, b) in enumerate(toks) if a < end), default=i0)
    best = None
    for i in range(max(0, i0 - reach), min(len(toks), i0 + reach + 1)):
        for j in range(max(i, j0 - reach), min(len(toks), j0 + reach + 1)):
            r = _sim(cov.alignment_string(text[toks[i][0]:toks[j][1]]), ocr_chars)
            key = (r, -(abs(i - i0) + abs(j - j0)))
            if best is None or key > best[0]:
                best = (key, toks[i][0], toks[j][1])
    assert best is not None
    return best[1], best[2], before, best[0][0]


def lines_in_render_px(tsv: str, factor: float) -> list[cov.OcrLine]:
    """OCR lines with boxes mapped to the pinned render's pixels (``factor``: OCR image width / render width)."""

    lines = cov.parse_tesseract_tsv(tsv)
    for line in lines:
        line.box = tuple(int(round(v / factor)) for v in line.box)  # type: ignore[assignment]
    return lines


def row_ratios(tsv: str) -> dict[tuple[int, int, int], float]:
    """Per OCR line (block, paragraph, line): its box height over its median word height."""

    import csv
    import io
    import statistics

    words: dict[tuple[int, int, int], list[tuple[int, int]]] = defaultdict(list)
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        if row.get("level") != "5" or not (row.get("text") or "").strip():
            continue
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        top, height = int(row["top"]), int(row["height"])
        words[key].append((top, top + height))
    out = {}
    for key, spans in words.items():
        line_h = max(b for _, b in spans) - min(a for a, _ in spans)
        out[key] = line_h / max(1.0, statistics.median(b - a for a, b in spans))
    return out


def best_pass(text: str, tsvs: Mapping[str, tuple[str, float]]) -> tuple[str, list[cov.LineAlignment]] | None:
    """The OCR pass whose aligned lines cover the most of the page text, with its alignment. ``tsvs`` maps a pass
    name to its TSV and the factor from the pinned render's pixels to the OCR image's."""

    best = None
    for name, (tsv, factor) in sorted(tsvs.items()):
        lines = lines_in_render_px(tsv, factor)
        alignments, _ = cov.align_page(lines, text)
        covered = sum(a.span[1] - a.span[0] for a in alignments if a.status == "aligned" and a.span)
        if best is None or covered > best[0]:
            best = (covered, name, alignments)
    return None if best is None else (best[1], best[2])


def _inside(point: tuple[float, float], box: Sequence[float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def in_crop(box: tuple[int, int, int, int], crop: Mapping[str, Any] | None, scale: float = 1.0) -> bool:
    """A line box (render px) is transcribed when its centre lies in the crop box and, for a multi-region crop, in
    one of its regions. ``scale`` maps crop pixels to render pixels (1 for the pinned render)."""

    if not crop:
        return True
    centre = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    outer = crop.get("box_px")
    if not outer or not _inside(centre, [v * scale for v in outer]):
        return False
    regions = crop.get("regions_px")
    return not regions or any(_inside(centre, [v * scale for v in region]) for region in regions)


def in_text_order(cands: list[dict[str, Any]], drops: Counter) -> list[dict[str, Any]]:
    """Keep the longest run of lines whose text spans increase in OCR reading order; drop the rest
    (``out_of_text_order``). A running head or a stray short line that matched a word elsewhere in the text breaks
    the order and goes; a page whose lines all follow the text keeps them all."""

    order = sorted(cands, key=lambda c: c["line_index"])
    starts = [c["span"][0] for c in order]
    best_len, prev = [1] * len(order), [-1] * len(order)
    for i in range(len(order)):
        for j in range(i):
            if starts[j] < starts[i] and best_len[j] + 1 > best_len[i]:
                best_len[i], prev[i] = best_len[j] + 1, j
    if not order:
        return []
    i = max(range(len(order)), key=lambda k: (best_len[k], -k))
    keep = set()
    while i >= 0:
        keep.add(i)
        i = prev[i]
    drops["out_of_text_order"] += len(order) - len(keep)
    return [c for k, c in enumerate(order) if k in keep]


@dataclass
class PageLines:
    lines: list[dict[str, Any]]
    ocr_pass: str | None


def page_lines(text: str, tsvs: Mapping[str, tuple[str, float]], *, crop: Mapping[str, Any] | None,
               excluded: Sequence[tuple[int, int]], min_score: float, drops: Counter,
               watermark: tuple[int, int, int, int] | None = None) -> PageLines:
    """Candidate lines of one page, after the line gates. Each: box (render px), span, label and scores."""

    norm, offsets = normalised_with_offsets(text)
    if norm != cov.alignment_string(text):
        drops["page_normalisation_mismatch"] += 1
        return PageLines([], None)
    picked = best_pass(text, tsvs)
    if picked is None:
        return PageLines([], None)
    name, alignments = picked
    rows_ratio = row_ratios(tsvs[name][0])
    aligned = [a for a in alignments if a.status == "aligned" and a.span]
    page_ratios = sorted(rows_ratio.get(a.line.key, 1.0) for a in aligned)
    max_rows = MAX_ROWS_RATIO * (page_ratios[len(page_ratios) // 2] if page_ratios else 1.0)
    heights = sorted(a.line.height for a in aligned)
    median_h = heights[len(heights) // 2] if heights else 0
    out = []
    for n, a in enumerate(alignments):
        if a.status != "aligned" or not a.span:
            continue
        if a.score < min_score:
            drops["below_min_score"] += 1
            continue
        if median_h and a.line.height > MAX_HEIGHT_RATIO * median_h:
            drops["taller_than_one_line"] += 1
            continue
        if rows_ratio.get(a.line.key, 1.0) > max_rows:
            drops["box_spans_two_rows"] += 1
            continue
        if watermark and boxes_overlap(a.line.box, watermark):
            drops["google_watermark_overlap"] += 1
            continue
        if not in_crop(a.line.box, crop):
            drops["outside_transcribed_crop"] += 1
            continue
        s0 = offsets[min(a.span[0], len(offsets) - 1)]
        e0 = offsets[min(a.span[1], len(offsets)) - 1] + 1
        s, e, sim_before, sim = refine_span(text, s0, e0, a.line.chars)
        raw = text[s:e]
        letters = len(cov.alignment_string(raw))
        if letters < MIN_LINE_CHARS:
            drops["short_line"] += 1
            continue
        if not LENGTH_RATIO_BAND[0] <= len(a.line.chars) / letters <= LENGTH_RATIO_BAND[1]:
            drops["line_length_disagrees_with_ocr"] += 1
            continue
        if sim < MIN_OCR_SIMILARITY:
            drops["label_disagrees_with_line_ocr"] += 1
            continue
        if "\n" in raw:
            drops["span_crosses_paragraph"] += 1
            continue
        if FOOTNOTE_MARK.search(raw):
            drops["footnote_marker"] += 1
            continue
        if any(s < x1 and x0 < e for x0, x1 in excluded):
            drops["excluded_span_on_scan"] += 1
            continue
        if CANTILLATION.search(unicodedata.normalize("NFD", raw)) or niqqud_density(raw) >= POINTED_LINE_DENSITY:
            drops["pointed_line"] += 1
            continue
        gt = label(raw)
        if not gt or not LETTER.search(gt) or not ALLOWED.match(gt):
            drops["outside_repertoire"] += 1
            continue
        out.append({"line_index": n, "box": a.line.box, "span": [s, e], "span_alignment": [s0, e0],
                    "text": gt, "alignment_score": round(a.score, 4), "ocr_similarity_before": round(sim_before, 4),
                    "ocr_similarity": round(sim, 4)})
    out = in_text_order(out, drops)
    # two lines may not claim the same text: keep the better-scored one
    out.sort(key=lambda c: c["span"][0])
    keep: list[dict[str, Any]] = []
    for cand in out:
        if keep and cand["span"][0] < keep[-1]["span"][1]:
            drops["span_overlaps_another_line"] += 1
            if cand["alignment_score"] > keep[-1]["alignment_score"]:
                keep[-1] = cand
            continue
        keep.append(cand)
    return PageLines(sorted(keep, key=lambda c: c["line_index"]), name)


# --- Pages ----------------------------------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def line_id(index_key: str, page: int, line: int) -> str:
    return f"{index_key}_p{page:04d}_l{line:03d}"


def ocr_tsvs(caches: Sequence[Path], render_sha256: str, *, hires_sha256: str | None = None,
             hires_factor: float | None = None) -> dict[str, tuple[str, float]]:
    """Cached Tesseract passes of one page, by pass name, each with its factor to the pinned render's pixels:
    the coverage tool's passes on the 2x upscale of the 960 px render (``psm3-plain`` ...), and a pass on the
    native 1920 px render when there is one (``hires-psm3``, ``ocr-hires``)."""

    out = {}
    for psm, suffix in OCR_PASSES:
        name = f"{psm}-{'flattened' if suffix else 'plain'}"
        for cache in caches:
            path = cache / f"{render_sha256}.heb.{psm}.x2{suffix}.tsv"
            if path.is_file():
                out[name] = (path.read_text(encoding="utf-8"), float(cov.OCR_SCALE))
                break
    if hires_sha256 and hires_factor:
        for cache in caches:
            path = cache / f"{hires_sha256}.heb.psm3.x1.tsv"
            if path.is_file():
                out["hires-psm3"] = (path.read_text(encoding="utf-8"), hires_factor)
                break
    return out


def page_ocr_file(name: str, render_sha256: str, hires_sha256: str | None) -> str:
    if name == "hires-psm3":
        return f"{hires_sha256}.heb.psm3.x1.tsv"
    psm, _, kind = name.partition("-")
    return f"{render_sha256}.heb.{psm}.x2{'.flattened' if kind == 'flattened' else ''}.tsv"


Rights = Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[str | None, dict[str, Any]]]


def page_rights(page: Mapping[str, Any], index: Mapping[str, Any]) -> tuple[str | None, dict[str, Any]]:
    """The page's derivation blocker and rights fields, from the committed Wikisource/Commons rights justifications
    (2026-11-10 legal strategy; ``hocrgen.fetchers.wikisource_justification``). Fails closed: an Index without an
    accepted justification, a Google-class file whose hygiene pass has not checked the page, and Google's front
    matter give no lines. The fields carry ``rights_justification_id`` and, where Google is not ruled out, the
    page's ``google_watermark_bbox`` (fractions of the page render)."""

    from hocrgen.fetchers.wikisource_justification import page_justification_fields, wikisource_page_blocker

    return wikisource_page_blocker(page, index), page_justification_fields(page, index)


def watermark_box_px(bbox: Sequence[float] | None, width: int, height: int) -> tuple[int, int, int, int] | None:
    """A ``google_watermark_bbox`` (``[x, y, w, h]`` fractions of the page render) in render pixels (x0, y0, x1, y1)."""

    if not bbox:
        return None
    x, y, w, h = bbox
    return (round(x * width), round(y * height), round((x + w) * width), round((y + h) * height))


def boxes_overlap(a: Sequence[int], b: Sequence[int]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def permalink(revision_id: int) -> str:
    return f"https://he.wikisource.org/w/index.php?oldid={revision_id}"


def load_facts(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"indexes": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def index_fact(facts: Mapping[str, Any], key: str) -> dict[str, Any]:
    return dict((facts.get("indexes") or {}).get(key) or {})


def page_script(facts: Mapping[str, Any], key: str, item: str, lid: str | None = None) -> str:
    """The line's script: a line override (by line id), else a page override, else the Index's, else square."""

    fact = index_fact(facts, key)
    script = ((fact.get("line_scripts") or {}).get(lid or "") or (fact.get("page_scripts") or {}).get(item)
              or fact.get("script") or "square")
    if script not in SCRIPTS:
        raise SystemExit(f"{item}: unknown script {script!r}")
    return script


def hires_image(item: str, caches: Sequence[Path]) -> Path | None:
    for cache in caches:
        path = cache / f"{item}.{HIRES_WIDTH}.jpg"
        if path.is_file():
            return path
    return None


def check_hires(hires: Path, pinned: Path) -> tuple[bool, float, int]:
    """Is ``hires`` the same page as the pinned render? (mean absolute grey difference after downscaling, as the
    line_verify hi-res step). Returns (ok, difference, hi-res width)."""

    from PIL import Image, ImageChops, ImageStat

    with Image.open(pinned) as lo, Image.open(hires) as hi:
        small = hi.convert("L").resize(lo.size, Image.LANCZOS)
        diff = ImageStat.Stat(ImageChops.difference(small, lo.convert("L"))).mean[0]
        ok = diff <= MAX_HIRES_MEAN_DIFF and hi.size[0] > lo.size[0]
        width = hi.size[0]
    return ok, round(diff, 2), width


Gate = Callable[[dict[str, Any], dict[str, dict[str, Any]], Path], list[str]]


def _default_gate(page: dict[str, Any], indexes: dict[str, dict[str, Any]], root: Path) -> list[str]:
    from hocrgen.fetchers.wikisource import page_exclusion_reasons

    return page_exclusion_reasons(page, indexes, root)


def load_snapshot(root: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    indexes = json.loads((root / "indexes.json").read_text(encoding="utf-8"))["indexes"]
    if isinstance(indexes, list):
        indexes = {record["index_key"]: record for record in indexes}
    pages = [json.loads(line) for line in (root / "pages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    return indexes, pages


def _named(pairs: Iterable[str] | None) -> dict[str, str]:
    out = {}
    for p in pairs or ():
        key, _, name = p.partition("=")
        out[key] = name or key
    return out


def _json(path: Path | None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def cap_per_index(keys: list[tuple[str, int, int]], cap: int, exempt: Iterable[str]) -> tuple[list, Counter]:
    """At most ``cap`` lines per Index, chosen by sha256 of the line id (deterministic, spread over the Index)."""

    exempt = set(exempt)
    by = defaultdict(list)
    for k in keys:
        by[k[0]].append(k)
    keep, capped = set(), Counter()
    for key, ks in by.items():
        if key in exempt:
            keep |= set(ks)
            continue
        order = sorted(ks, key=lambda k: hashlib.sha256(line_id(*k).encode()).hexdigest())
        keep |= set(order[:cap])
        capped[key] = max(0, len(ks) - cap)
    return [k for k in keys if k in keep], capped


def release_notice(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    files: dict[str, dict[str, Any]] = {}
    for r in rows:
        f = files.setdefault(r["commons_file"], {"commons_file": r["commons_file"], "sha1": r["commons_file_sha1"],
                                                  "description_url": r["commons_description_url"],
                                                  "scan_basis": r["scan_basis"], "pages": set()})
        f["pages"].add(r["page"])
    pages = sorted({(r["index_key"], r["page"], r["attribution_url"]) for r in rows})
    return {
        "text_licence": TEXT_LICENCE, "text_licence_url": TEXT_LICENCE_URL,
        "text": "Line labels are text of Hebrew Wikisource proofread pages, by Hebrew Wikisource contributors, under "
                "CC BY-SA 4.0 (share-alike). Each row's `attribution_url` is the pinned revision of its page. Any "
                "adaptation of this text must carry this attribution and be shared under CC BY-SA 4.0 or a "
                "compatible licence.",
        "share_alike": True,
        "attribution": ATTRIBUTION,
        "page_permalinks": [{"index_key": k, "page": p, "permalink": u} for k, p, u in pages],
        "scan_credits": [{**{k: v for k, v in f.items() if k != "pages"}, "pages": sorted(f["pages"])}
                         for f in sorted(files.values(), key=lambda f: f["commons_file"])],
        "scan_terms": "Line images are cut from Wikimedia Commons renders of public-domain printed works (faithful "
                      "reproductions, no new rights; per-file licence templates on Commons). Credit: Wikimedia Commons "
                      "and the scan sources named per file.",
    }


def build(args: argparse.Namespace, *, gate: Gate = _default_gate, rights: Rights = page_rights) -> dict[str, Any]:
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    snap = Path(args.snapshot)
    indexes, pages = load_snapshot(snap)
    facts = load_facts(Path(args.facts) if args.facts else None)
    dev = _named(args.dev)
    reserve = _named(args.reserve)
    ex = exclusions(args.policy, indexes, pages, eval_set=_json(Path(args.eval_set) if args.eval_set else None),
                    split_manifest=_json(Path(args.split_manifest) if args.split_manifest else None),
                    line_verify=[_json(Path(p)) for p in args.line_verify or ()], manual=_named(args.hold_out))
    clash = (set(dev) | set(reserve)) & set(ex.held_out)
    if clash:
        raise SystemExit(f"dev or reserve Indexes are held out by the policy: {sorted(clash)}")
    if set(dev) & set(reserve):
        raise SystemExit(f"Indexes both dev and reserve: {sorted(set(dev) & set(reserve))}")
    caches = [Path(p) for p in args.ocr_cache]
    hires_dirs = [Path(p) for p in args.hires or ()]
    drops: Counter = Counter()
    page_drops: Counter = Counter()
    page_drops_by_index: dict[str, Counter] = defaultdict(Counter)
    pool_pages: Counter = Counter()
    after_pages: Counter = Counter()
    best: dict[tuple[str, int, int], dict[str, Any]] = {}
    page_meta: dict[str, dict[str, Any]] = {}
    hires_report: Counter = Counter()
    for record in pages:
        key, item = record["index_key"], record["source_item_id"]
        pool_pages[key] += 1

        def drop_page(reason: str) -> None:
            page_drops[reason] += 1
            page_drops_by_index[key][reason] += 1

        if key in ex.held_out:
            drop_page("index_held_out")
            continue
        if item in ex.dropped_pages:
            drop_page("page_" + ex.dropped_pages[item][0])
            continue
        if key in reserve:
            drop_page("index_reserved")
            continue
        after_pages[key] += 1
        if record.get("quality") not in (3, 4):
            drop_page("quality_not_3_or_4")
            continue
        if gate(record, indexes, snap):
            drop_page("page_gate_failed")
            continue
        blocked, rights_fields = rights(record, indexes[key])
        if blocked:
            drop_page(blocked)
            continue
        image = record["image"]
        image_path = snap / image["path"]
        if sha256_bytes(image_path.read_bytes()) != image["sha256"]:
            raise SystemExit(f"{item}: page image does not match its pinned sha256")
        text = (snap / record["text_path"]).read_text(encoding="utf-8")
        text = unicodedata.normalize("NFC", text[:-1] if text.endswith("\n") else text)
        if sha256_bytes(text.encode("utf-8")) != record["text_sha256"]:
            raise SystemExit(f"{item}: pair text does not match its pinned sha256")
        if niqqud_density(text) >= POINTED_PAGE_DENSITY:
            drop_page("pointed_page")
            continue
        hires, diff, hires_sha, factor = None, None, None, None
        candidate = hires_image(item, hires_dirs)
        if candidate is not None:
            ok, diff, width = check_hires(candidate, image_path)
            hires_report["hires_used" if ok else "hires_check_failed"] += 1
            if ok:
                hires, hires_sha, factor = candidate, sha256_bytes(candidate.read_bytes()), width / int(image["width"])
        else:
            hires_report["pinned_960_used"] += 1
        tsvs = ocr_tsvs(caches, image["sha256"], hires_sha256=hires_sha, hires_factor=factor)
        if not tsvs:
            drop_page("page_without_cached_ocr")
            continue
        crop = record.get("crop") if record.get("transcription_coverage") == "partial_page" else None
        excluded = [(s["start"], s["end"]) for s in (record.get("excluded_spans") or {}).get("spans", []) if "start" in s]
        watermark = watermark_box_px(rights_fields.get("google_watermark_bbox"), int(image["width"]), int(image["height"]))
        found = page_lines(text, tsvs, crop=crop, excluded=excluded, min_score=args.min_score, drops=drops,
                           watermark=watermark)
        if not found.lines:
            drop_page("page_without_lines")
            continue
        page_meta[item] = {"rights": rights_fields, "record": record, "ocr_pass": found.ocr_pass, "image_path": image_path, "hires": hires,
                           "hires_sha256": hires_sha, "hires_mean_diff": diff}
        for cand in found.lines:
            best[(key, int(record["page_number"]), cand["line_index"])] = {**cand, "_item": item}
    keys = sorted(best)
    capped: Counter = Counter()
    if args.max_lines_per_book:
        keys, capped = cap_per_index(keys, args.max_lines_per_book, () if args.cap_dev else dev)
    rows = []
    counts: dict[str, Counter] = defaultdict(Counter)
    strata: dict[str, Counter] = defaultdict(Counter)
    scripts: dict[str, Counter] = defaultdict(Counter)
    genres: dict[str, Counter] = defaultdict(Counter)
    by_book_stratum: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    by_book_script: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    for k in keys:
        c = best[k]
        key, page_no, n = k
        item = c["_item"]
        meta = page_meta[item]
        record, index = meta["record"], indexes[key]
        fact = index_fact(facts, key)
        split = "dev" if key in dev else "train"
        lid = line_id(key, page_no, n)
        rel = Path(split) / key / f"{lid}.png"
        hires, diff = meta["hires"], meta["hires_mean_diff"]
        source_image = hires or meta["image_path"]
        from PIL import Image

        with Image.open(source_image) as im:
            scale = im.size[0] / int(record["image"]["width"])
            x0, y0, x1, y1 = (v * scale for v in c["box"])
            h = y1 - y0
            box = (max(0, round(x0 - 0.5 * h)), max(0, round(y0 - 0.12 * h)),
                   min(im.size[0], round(x1 + 0.5 * h)), min(im.size[1], round(y1 + 0.12 * h)))
            image_sha = None
            if not args.no_images:
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                im.convert("L").crop(box).save(out / rel)
                (out / rel.with_suffix(".gt.txt")).write_text(c["text"] + "\n", encoding="utf-8")
                image_sha = sha256_bytes((out / rel).read_bytes())
        commons = index.get("commons_file") or {}
        script = page_script(facts, key, item, lid)
        genre = fact.get("genre")
        rabbinic = bool(fact.get("rabbinic"))
        quality = record["quality"]
        book = dev.get(key) or fact.get("name") or key
        row = {
            "id": lid, "split": split, "book": book, "record_id": key, "index_key": key, "page": page_no,
            "page_title": record["page_title"], "page_revision_id": record["revision_id"], "source_item_id": item,
            "line_index": n, "bbox_render": [c["box"][0], c["box"][1], c["box"][2] - c["box"][0], c["box"][3] - c["box"][1]],
            "render_width": int(record["image"]["width"]), "text": c["text"], "text_span": c["span"],
            "text_span_alignment": c["span_alignment"], "span_adjusted": c["span"] != c["span_alignment"],
            "ocr_similarity_before": c["ocr_similarity_before"], "ocr_similarity": c["ocr_similarity"],
            "alignment_score": c["alignment_score"], "page_quality": quality,
            "image_source": f"commons_render_{HIRES_WIDTH}" if hires else "commons_render_960_pinned",
            "image_source_sha256": meta["hires_sha256"] if hires else record["image"]["sha256"],
            "hires_mean_diff": diff, "image_scale": round(scale, 5),
            "bbox_image": [round(x0), round(y0), round(x1 - x0), round(y1 - y0)], "crop_box_image": list(box),
            "image": str(rel), "image_sha256": image_sha,
            "stratum": "unpointed", "script": script, "genre": genre, "rabbinic": rabbinic,
            "ocr_placer": "stock", "alignment": f"wikisource_coverage {cov.TOOL_VERSION} align_page, {meta['ocr_pass']}",
            "page_ocr": page_ocr_file(meta["ocr_pass"], record["image"]["sha256"], meta["hires_sha256"]),
            "scan_source": SCAN_SOURCE, "source_class": SOURCE_CLASS,
            "scan_basis": index.get("scan_source_origin"),
            "scan_digitized_by_google": (index.get("scan_rights") or {}).get("digitized_by_google"),
            "commons_file": commons.get("title"), "commons_file_sha1": commons.get("sha1"),
            "commons_description_url": commons.get("description_url"), "commons_page": page_no,
            "text_licence": TEXT_LICENCE, "text_licence_url": TEXT_LICENCE_URL,
            "attribution": f"{ATTRIBUTION}, {permalink(record['revision_id'])}",
            "attribution_url": permalink(record["revision_id"]),
            "rights_justification_id": meta["rights"]["rights_justification_id"],
            "google_watermark_bbox": meta["rights"].get("google_watermark_bbox"),
            "attestation": "wikisource_quality4_validated" if quality == 4 else "wikisource_quality3_single_proofreader",
            "adjudication_status": "not_adjudicated", "reference_eligible": False,
        }
        rows.append(row)
        label_key = f"{key} {book}"
        counts[split][label_key] += 1
        strata[split]["unpointed"] += 1
        scripts[split][script] += 1
        genres[split]["rabbinic" if rabbinic else (genre or "unclassified")] += 1
        by_book_stratum[split][label_key]["unpointed"] += 1
        by_book_script[split][label_key][script] += 1
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    def rabbinic_count(page_counter: Mapping[str, int]) -> dict[str, Any]:
        keys_r = sorted(k for k, v in page_counter.items() if v and index_fact(facts, k).get("rabbinic"))
        return {"indexes": len(keys_r), "pages": sum(page_counter[k] for k in keys_r), "index_keys": keys_r}

    used_pages: Counter = Counter()
    for item in {r["source_item_id"] for r in rows}:
        used_pages[item.split("__", 1)[0]] += 1
    summary: dict[str, Any] = {
        "schema": SCHEMA, "tool": TOOL, "tool_version": TOOL_VERSION, "row_shape": "s16c_benyehuda_nli_lines.v2",
        "snapshot": str(snap), "min_score": args.min_score,
        "labels": "Hebrew Wikisource proofread page text placed by the wikisource_coverage alignment; never OCR output",
        "label_folds": FOLD, "label_rules": "NFC; niqqud and cantillation removed; maqaf, geresh, gershayim and dashes "
                                             "kept; logical order; whitespace collapsed",
        "min_ocr_similarity": MIN_OCR_SIMILARITY, "max_height_ratio": MAX_HEIGHT_RATIO,
        "pointed_page_density": POINTED_PAGE_DENSITY, "pointed_line_density": POINTED_LINE_DENSITY,
        "dev_records": dev,
        "rabbinic_dev": {
            "lines_in_this_set": genres.get("dev", Counter()).get("rabbinic", 0),
            "indexes_with_lines": sorted({r["index_key"] for r in rows if r["split"] == "dev" and r["rabbinic"]}),
            "elsewhere": args.rabbinic_dev_source,
            "note": (f"This set has no rabbinic dev line; the rabbinic dev set comes from {args.rabbinic_dev_source}."
                     if args.rabbinic_dev_source and not genres.get("dev", Counter()).get("rabbinic", 0) else None)},
        "lines": {s: dict(c) for s, c in counts.items()},
        "totals": {s: sum(c.values()) for s, c in counts.items()},
        "dropped": dict(sorted(drops.items())), "dropped_pages": dict(sorted(page_drops.items())),
        "dropped_pages_by_index": {k: dict(v) for k, v in sorted(page_drops_by_index.items())},
        "manifest_sha256": sha256_bytes(manifest.read_bytes()),
        "strata": {s: dict(c) for s, c in strata.items()}, "scripts": {s: dict(c) for s, c in scripts.items()},
        "genres": {s: dict(c) for s, c in genres.items()},
        "lines_by_book_and_stratum": {s: {b: dict(c) for b, c in sorted(d.items())} for s, d in by_book_stratum.items()},
        "lines_by_book_and_script": {s: {b: dict(c) for b, c in sorted(d.items())} for s, d in by_book_script.items()},
        "max_lines_per_book": args.max_lines_per_book, "cap_dev": args.cap_dev,
        "capped_lines": {k: n for k, n in sorted(capped.items()) if n},
        "pages_used": {k: v for k, v in sorted(used_pages.items())},
        "indexes_used": len(used_pages), "pages_used_total": sum(used_pages.values()),
        "images": dict(hires_report), "images_written": not args.no_images,
        "exclusion_policy": {
            "id": args.policy, **EXCLUSION_POLICIES[args.policy],
            "rules": {r: INDEX_RULES[r] for r in EXCLUSION_POLICIES[args.policy]["index_rules"]}
                     | {r: PAGE_RULES[r] for r in EXCLUSION_POLICIES[args.policy]["page_rules"]},
            "inputs": {"eval_set": args.eval_set, "split_manifest": args.split_manifest, "line_verify": args.line_verify},
            "held_out_indexes": {k: {"rules": v, "title": (indexes.get(k, {}).get("work") or {}).get("title"),
                                     "release_split": ex.release_split.get(k), "pages": pool_pages.get(k, 0)}
                                 for k, v in sorted(ex.held_out.items())},
            "related_works_of_audit2": ex.related,
            "same_creator_other_works_not_held_out": ex.same_creator,
            "dropped_page_ids": sorted(ex.dropped_pages),
            "dropped_pages": {"count": len([p for p in ex.dropped_pages if p.split("__")[0] not in ex.held_out]),
                              "by_rule": dict(Counter(v[0] for p, v in ex.dropped_pages.items()
                                                      if p.split("__")[0] not in ex.held_out))},
            "counts": {"pool": {"indexes": len(pool_pages), "pages": sum(pool_pages.values())},
                       "after_exclusions": {"indexes": len([k for k, v in after_pages.items() if v]),
                                            "pages": sum(after_pages.values())}},
        },
        "reserve": {"indexes": reserve, **(RESERVE_V1 if not reserve else {"waived": False})},
        "rabbinic": {"pool": rabbinic_count(pool_pages), "after_exclusions": rabbinic_count(after_pages),
                     "in_output": rabbinic_count(used_pages),
                     "lines": {s: c.get("rabbinic", 0) for s, c in genres.items()},
                     "classification": (facts.get("classification") or "")},
        "release_notice": release_notice(rows),
        "rights_justification": "rights_justification_id is the Index's Route C (Wikimedia Commons) record in "
                                "docs/wikisource_rights_justifications.json (hocrgen#171); every page passes "
                                "wikisource_page_blocker (dropped_pages counts its reasons) and lines under a "
                                "google_watermark_bbox are dropped (google_watermark_overlap).",
        "silver": "every row is not_adjudicated and reference_eligible: false (training data), quality 4 included",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


# --- Verification ---------------------------------------------------------------------------------------------

NIQQUD_ANY = re.compile("[\u0591-\u05bd\u05bf\u05c1\u05c2\u05c4\u05c5\u05c7]")  # points and accents; not maqaf, paseq, sof pasuq


def verify(out: Path) -> list[str]:
    """Problems in a built set (empty when it passes)."""

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(ln) for ln in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    policy = summary["exclusion_policy"]
    held = set(policy["held_out_indexes"]) | set(summary["reserve"].get("indexes") or {})
    problems = []
    if sha256_bytes((out / "manifest.jsonl").read_bytes()) != summary["manifest_sha256"]:
        problems.append("manifest sha256 differs from summary")
    dropped = set()
    if policy.get("dropped_page_ids"):
        dropped = set(policy["dropped_page_ids"])
    ids = Counter(r["id"] for r in rows)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for r in rows:
        where = r["id"]
        if r["index_key"] in held:
            problems.append(f"{where}: held-out or reserved Index {r['index_key']}")
        if r["source_item_id"] in dropped:
            problems.append(f"{where}: dropped page {r['source_item_id']}")
        if NIQQUD_ANY.search(unicodedata.normalize("NFD", r["text"])):
            problems.append(f"{where}: label has niqqud or cantillation")
        if not ALLOWED.match(r["text"]):
            problems.append(f"{where}: label outside the repertoire")
        if r.get("text_licence") != TEXT_LICENCE or not r.get("attribution") or "oldid=" not in r.get("attribution_url", ""):
            problems.append(f"{where}: licence or attribution missing")
        if not r.get("commons_file") or not r.get("commons_file_sha1"):
            problems.append(f"{where}: Commons file or sha1 missing")
        if r.get("reference_eligible") is not False or r.get("adjudication_status") != "not_adjudicated":
            problems.append(f"{where}: row is not silver")
        if r["split"] == "dev" and r["index_key"] not in summary["dev_records"]:
            problems.append(f"{where}: dev row from a non-dev Index")
        if r["split"] == "train" and r["index_key"] in summary["dev_records"]:
            problems.append(f"{where}: train row from a dev Index")
        if summary.get("images_written"):
            if not r.get("image_sha256"):
                problems.append(f"{where}: image sha256 is null")
            else:
                path = out / r["image"]
                if not path.is_file() or sha256_bytes(path.read_bytes()) != r["image_sha256"]:
                    problems.append(f"{where}: image missing or sha256 mismatch")
                gt = path.with_suffix(".gt.txt")
                if not gt.is_file() or gt.read_text(encoding="utf-8") != r["text"] + "\n":
                    problems.append(f"{where}: gt.txt missing or differs from the label")
    return problems


# --- Hi-res renders (network) ---------------------------------------------------------------------------------


def fetch_hires(snapshot: Path, items: Sequence[str], out_dir: Path, *, delay: float = 1.0) -> Counter:  # pragma: no cover - network
    """Fetch the 1920 px Commons render of each listed page (``<source_item_id>.1920.jpg``), one request per
    ``delay`` seconds at most. Downloads are untrusted: they are only ever opened as images."""

    _, pages = load_snapshot(snapshot)
    by_item = {p["source_item_id"]: p for p in pages}
    out_dir.mkdir(parents=True, exist_ok=True)
    stats: Counter = Counter()
    for item in items:
        dest = out_dir / f"{item}.{HIRES_WIDTH}.jpg"
        if dest.exists():
            stats["cached"] += 1
            continue
        url = ((by_item[item].get("image") or {}).get("rendered_from") or {}).get("render_url", "")
        if "-960px-" not in url:
            stats["no_960_render_url"] += 1
            continue
        url = url.replace("-960px-", f"-{HIRES_WIDTH}px-")
        for attempt in range(5):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req, timeout=60) as response:
                    data = response.read()
                tmp = dest.with_suffix(".part")
                tmp.write_bytes(data)
                tmp.rename(dest)
                stats["fetched"] += 1
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504}:
                    stats[f"http_{exc.code}"] += 1
                    break
                time.sleep(min(60, 5 * 2 ** attempt))
            except (urllib.error.URLError, TimeoutError):
                time.sleep(min(60, 5 * 2 ** attempt))
        else:
            stats["failed"] += 1
        time.sleep(delay)
    return stats


def _ocr_hires_one(job: tuple[Path, Path, str]) -> int:  # pragma: no cover - runs tesseract
    import os
    import subprocess
    import tempfile

    from PIL import Image

    image, cache, executable = job
    path = cache / f"{sha256_bytes(image.read_bytes())}.heb.psm3.x1.tsv"
    if path.exists():
        return 0
    with tempfile.TemporaryDirectory(prefix="hocrgen-wslines-") as temp:
        source = Path(temp) / "page.png"
        with Image.open(image) as opened:
            opened.convert("L").save(source)
        target = Path(temp) / "out"
        subprocess.run([executable, str(source), str(target), "-l", "heb", "--psm", "3", "tsv"], capture_output=True,
                       check=True, env={**os.environ, "OMP_THREAD_LIMIT": "1"}, timeout=900)
        tmp = path.with_suffix(".part")
        tmp.write_text(target.with_suffix(".tsv").read_text(encoding="utf-8"), encoding="utf-8")
        tmp.rename(path)
    return 1


def ocr_hires(hires_dir: Path, cache: Path, *, executable: str = "tesseract", workers: int = 4) -> int:  # pragma: no cover - runs tesseract
    """Tesseract (stock ``heb``, psm 3) on each 1920 px render, for line boxes only, cached by the render's sha256
    as ``<sha256>.heb.psm3.x1.tsv`` next to the coverage tool's passes. The OCR text is never used as a label."""

    from concurrent.futures import ProcessPoolExecutor

    cache.mkdir(parents=True, exist_ok=True)
    jobs = [(p, cache, executable) for p in sorted(hires_dir.glob(f"*.{HIRES_WIDTH}.jpg"))]
    with ProcessPoolExecutor(workers) as pool:
        return sum(pool.map(_ocr_hires_one, jobs, chunksize=2))


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - CLI wiring
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="cut a labelled line set from a tranche's Wikisource snapshot")
    b.add_argument("out")
    b.add_argument("--snapshot", required=True, help="the tranche's sources/wikisource_he_proofread/snapshot")
    b.add_argument("--ocr-cache", action="append", required=True, help="coverage tool Tesseract cache (repeatable)")
    b.add_argument("--hires", action="append", help="folder of <source_item_id>.1920.jpg renders (repeatable)")
    b.add_argument("--policy", choices=sorted(EXCLUSION_POLICIES), required=True)
    b.add_argument("--eval-set", help="E2d3d eval_set.json (audit2 = its adjudicated stratum)")
    b.add_argument("--split-manifest", help="the tranche's release split manifest")
    b.add_argument("--line-verify", action="append", help="a line_verify bundle items.json (repeatable)")
    b.add_argument("--hold-out", nargs="*", help="extra Indexes held out whole, INDEX=reason")
    b.add_argument("--dev", nargs="*", help="dev Indexes INDEX[=name], held out whole from train")
    b.add_argument("--reserve", nargs="*", help="reserved Indexes INDEX[=reason], in neither train nor dev")
    b.add_argument("--facts", help="per-Index facts JSON (genre, rabbinic, script, names)")
    b.add_argument("--rabbinic-dev-source", help="where the rabbinic dev set comes from when this set has none (recorded)")
    b.add_argument("--min-score", type=float, default=MIN_SCORE)
    b.add_argument("--max-lines-per-book", type=int, default=0)
    b.add_argument("--cap-dev", action="store_true")
    b.add_argument("--no-images", action="store_true", help="manifest and summary only (image_sha256 null)")
    f = sub.add_parser("fetch-hires", help="fetch 1920 px Commons renders of listed pages (network)")
    f.add_argument("--snapshot", required=True)
    f.add_argument("--items", required=True, help="file with one source_item_id per line")
    f.add_argument("--out", required=True)
    f.add_argument("--delay", type=float, default=1.0)
    o = sub.add_parser("ocr-hires", help="Tesseract line boxes for the 1920 px renders (boxes only, cached)")
    o.add_argument("--hires", required=True)
    o.add_argument("--ocr-cache", required=True)
    o.add_argument("--tesseract", default="tesseract")
    o.add_argument("--workers", type=int, default=4)
    v = sub.add_parser("verify", help="verify a built set")
    v.add_argument("out")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        summary = build(args)
        print(json.dumps({k: summary[k] for k in ("totals", "scripts", "genres", "dropped", "dropped_pages", "manifest_sha256")},
                         ensure_ascii=False, indent=1))
    elif args.cmd == "fetch-hires":
        items = [ln.strip() for ln in Path(args.items).read_text(encoding="utf-8").splitlines() if ln.strip()]
        print(json.dumps(fetch_hires(Path(args.snapshot), items, Path(args.out), delay=max(1.0, args.delay))))
    elif args.cmd == "ocr-hires":
        print(json.dumps({"new": ocr_hires(Path(args.hires), Path(args.ocr_cache), executable=args.tesseract, workers=args.workers)}))
    else:
        problems = verify(Path(args.out))
        print(json.dumps({"problems": len(problems), "first": problems[:20]}, ensure_ascii=False, indent=1))
        return 1 if problems else 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
