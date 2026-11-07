"""Logical-order page text from a PDF glyph layer, rebuilt from geometry and verified line by line (F8e2).

Input is a ``hocrgen.pdf_glyph_layer.v1`` document (``hocrgen.parsers.pdf_glyphs``): every painted glyph with its box,
baseline, size, font code and paint order, plus each font's ToUnicode map and outline hashes. Everything here is pure
Python (PIL for the render checks), so CI re-derives and re-verifies committed pages without pdfminer or poppler.

**Conversion** (``convert_glyph_layer``):

1. *Identity.* A glyph's character is its ToUnicode text, unless the glyph outline table (``resolve_glyph_texts``)
   names it: InDesign's Hebrew subsets map some codes wrongly (a full stop to a space or to ``פ``, ``8`` to ``ר``),
   and the outline is the shape actually painted. A bracket's character follows its drawn shape and the run
   direction (UBA L4), because the subsets disagree on which of a pair they name.
2. *Visibility.* Glyphs in an invisible render mode, outside the clipping path, in optional content that is off, or
   under a later opaque fill are dropped (Reshumot booklets carry a hidden tagged copy of many pages under a white
   rectangle, with the visible text repainted on top); so is a glyph painted twice on itself. Glyphs that map to
   whitespace, control or format characters (U+0020, U+0009, U+FEFF, U+200F, ...) only mark word gaps; their code
   points are counted.
3. *Lines.* Glyphs are grouped by baseline; a short run of markedly smaller glyphs touching a line, or raised on
   its baseline, is a script run (a footnote marker).
4. *Segments.* A line is cut at a gap of more than ``SEGMENT_GAP_EM`` ems, or of more than ``FRAME_GAP_EM`` between
   glyphs not painted together (separate text frames: side headings, table cells, signatures). Inside a segment a
   space glyph, or an open gap over ``INFERRED_WORD_GAP_EM``, is one word space, except in letter-spaced runs
   (signature names), where only a clearly wider gap is. Script digits next to digits are set off by a space.
5. *Bidi.* Each segment is a right-to-left paragraph in visual order. It is reversed, and every left-to-right run
   (Latin words, numbers with their separators) is restored to its own order.
6. *Reading order.* Labels (``3.``, ``2ג.``, ``(א)``, a footnote number) join the line they label. Segments stack
   into blocks (same column, same type size, line spacing). A block at least ``MAIN_BLOCK_SHARE`` of the text width is
   read line by line; a narrower one (a side heading, a signature, a table column) is read whole. Items are read top
   to bottom; on one row, side headings outside the body column come first, then right to left.

**Verification**, independent of the conversion (``segment_issues``, ``ink_report``, ``page_verdict``):

- each segment's logical text, run forward through the Unicode bidi algorithm (``unicode_bidi_display``: W1-W7,
  N1-N2, I2, L1, L2, L4), must reproduce the glyphs' visual order exactly (``bidi_round_trip_failed``); a quote, prime
  or degree sign between two left-to-right runs (``29º 32' 26.33"``) has no verifiable order
  (``quote_between_ltr_runs``); every glyph must have a known outline or an unambiguous ToUnicode entry
  (``glyph_identity_unverified``), no U+FFFD or ``(cid:N)`` (``unmapped_glyph``) and no private-use code
  (``private_use_glyph``);
- on the page render, every kept glyph must hold ink and every inked pixel must lie under a kept glyph, a stroke, a
  fill or an image;
- a line that fails is left out and the page is cropped to the verified regions (decision 12): the regions avoid
  every unverified line, page image and unexplained ink, and inside them all ink must be explained again.
"""

from __future__ import annotations

import functools
import math
import re
import statistics
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

GEOMETRY_NORMALIZATION_VERSION = "pdf_glyph_geometry_logical.v1"

WORD_GAP_EM = 0.6
INFERRED_WORD_GAP_EM = 0.1
LETTER_SPACED_MIN_GAPS = 3
LETTER_SPACED_MIN_EM = 0.06
LETTER_SPACED_EVENNESS = 2.5
LETTER_SPACED_WORD_GAP = 1.8
DUPLICATE_OVERLAP = 0.6
SEGMENT_GAP_EM = 1.5
FRAME_GAP_EM = 0.3
SCRIPT_SIZE_RATIO = 0.75
SCRIPT_MAX_GLYPHS = 6
SCRIPT_TAB_REACH_EM = 3.0
SCRIPT_RISE_EM = 0.05
BASELINE_TOLERANCE_EM = 0.12
MAIN_BLOCK_SHARE = 0.45
BLOCK_LINE_GAP_EM = 0.7
BLOCK_SIZE_RATIO = (0.9, 1.11)
LABEL_REACH_EM = 4.0
ROW_TOLERANCE_EM = 0.5
OCCLUSION_TOLERANCE_PT = 0.5

GLYPH_FLAG_INVISIBLE = 1
GLYPH_FLAG_NOT_UPRIGHT = 2
GLYPH_FLAG_CLIPPED = 16
GLYPH_FLAG_HIDDEN_LAYER = 32

SEGMENT_ISSUES = frozenset({"bidi_round_trip_failed", "quote_between_ltr_runs", "dash_between_numbers_ambiguous", "unmapped_glyph", "private_use_glyph", "glyph_identity_unverified"})


@dataclass(frozen=True)
class Glyph:
    paint: int
    text: str
    x0: float
    top: float
    x1: float
    bottom: float
    origin_x: float
    baseline: float
    size: float
    font: int
    flags: int
    cid: int = -1
    mirror: bool = False  # the text is a bracket's drawn shape, mirrored at right-to-left levels
    ink: tuple[float, float, float, float] | None = None  # the outline's ink box on the page, when the font has one

    @property
    def ink_box(self) -> list[float]:
        """Where the glyph's ink lies: its outline box when known, otherwise its advance box."""

        return list(self.ink) if self.ink is not None else [self.x0, self.top, self.x1, self.bottom]

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.top + self.bottom) / 2

    @property
    def kind(self) -> str:
        """``space`` (whitespace, control or format characters only), ``mark`` (a combining mark) or ``text``."""

        return _kind(self.text)


@functools.lru_cache(maxsize=4096)
def _kind(text: str) -> str:
    if _whitespace(text):
        return "space"
    if text and all(unicodedata.category(char) in {"Mn", "Me"} for char in text):
        return "mark"
    return "text"


def load_glyphs(layer: dict[str, Any]) -> list[Glyph]:
    fonts = layer.get("fonts") or []
    glyphs = []
    for row in layer.get("glyphs") or []:
        glyph = Glyph(*row)
        font = fonts[glyph.font] if 0 <= glyph.font < len(fonts) and isinstance(fonts[glyph.font], dict) else {}
        bounds = (font.get("bounds") or {}).get(str(glyph.cid))
        if bounds and not glyph.flags & GLYPH_FLAG_NOT_UPRIGHT:
            scale = glyph.size / 1000.0
            glyph = replace(glyph, ink=(
                glyph.origin_x + bounds[0] * scale, glyph.baseline - bounds[3] * scale,
                glyph.origin_x + bounds[2] * scale, glyph.baseline - bounds[1] * scale,
            ))
        glyphs.append(glyph)
    return glyphs


@dataclass
class Visibility:
    visible: list[Glyph]
    invisible_render_mode: int = 0
    hidden_by_fill: dict[str, int] = field(default_factory=dict)
    rotated: list[Glyph] = field(default_factory=list)
    duplicates: int = 0
    clipped: int = 0
    hidden_layer: int = 0
    identity: dict[str, int] = field(default_factory=dict)
    unverified: set[int] = field(default_factory=set)  # paint ids of glyphs whose character is not established


def _whitespace(text: str) -> bool:
    return bool(text) and all(unicodedata.category(char) in {"Zs", "Cc", "Cf", "Zl", "Zp"} for char in text)


def _duplicate_targets(tounicode: dict[str, str], table: dict[str, Any]) -> set[str]:
    """Characters a font's ToUnicode map gives to more than one code (whitespace and accepted variant sets aside)."""

    codes: dict[str, int] = {}
    for text in tounicode.values():
        if not _whitespace(text):
            codes[text] = codes.get(text, 0) + 1
    variants = [set(group) for group in table.get("variant_sets") or []]
    duplicates = {text for text, count in codes.items() if count > 1}
    return {text for text in duplicates if not any(text in group for group in variants)}


def resolve_glyph_texts(layer: dict[str, Any], table: dict[str, Any] | None) -> tuple[list[Glyph], dict[str, int], set[int]]:
    """Each glyph's character, established by its outline.

    ``table`` is a ``hocrgen.glyph_outline_identities.v1`` document: for each known TrueType outline (the hash the
    glyph layer records per font and code), the characters its ToUnicode text may be (``accept``) and the character
    to use otherwise (``char``). InDesign's Hebrew font subsets map some codes wrongly (a full stop to a space or to
    ``פ``, ``8`` to ``ר``); the outline is the shape actually painted, so it decides. A glyph is *unverified* when its
    outline is not in the table (closed world) or, for a font without outlines, when its ToUnicode character is also
    given to another code of the same font. Whitespace glyphs with no outline are whitespace.
    """

    table = table or {}
    known = table.get("outlines") or {}
    stats = {"repaired": 0, "unknown_outline": 0, "ambiguous_tounicode": 0}
    unverified: set[int] = set()
    fonts = layer.get("fonts") or []
    duplicates = [_duplicate_targets(dict(font.get("tounicode") or {}), table) if isinstance(font, dict) else set() for font in fonts]
    resolved = []
    for glyph in load_glyphs(layer):
        font = fonts[glyph.font] if 0 <= glyph.font < len(fonts) and isinstance(fonts[glyph.font], dict) else {}
        outline = (font.get("outlines") or {}).get(str(glyph.cid))
        text = glyph.text
        mirror = False
        if outline:
            entry = known.get(outline)
            if entry is None:
                stats["unknown_outline"] += 1
                unverified.add(glyph.paint)
            elif entry.get("shape"):
                # A bracket: the outline is the drawn shape; its character depends on the run direction (UBA L4).
                text = entry["shape"]
                mirror = True
            elif text not in entry.get("accept", []):
                if entry.get("char"):
                    text = entry["char"]
                    stats["repaired"] += 1
                else:
                    unverified.add(glyph.paint)
        elif not _whitespace(text) and text in duplicates[glyph.font] if 0 <= glyph.font < len(duplicates) else False:
            stats["ambiguous_tounicode"] += 1
            unverified.add(glyph.paint)
        resolved.append(replace(glyph, text=text, mirror=mirror) if text != glyph.text or mirror else glyph)
    return resolved, stats, unverified


def _inside(glyph: Glyph, box: Sequence[float], tolerance: float = OCCLUSION_TOLERANCE_PT) -> bool:
    return box[0] - tolerance <= glyph.cx <= box[2] + tolerance and box[1] - tolerance <= glyph.cy <= box[3] + tolerance


def visible_glyphs(layer: dict[str, Any], table: dict[str, Any] | None = None) -> Visibility:
    """The glyphs a viewer sees: not in an invisible render mode, not painted over by a later opaque fill."""

    glyphs, stats, unverified = resolve_glyph_texts(layer, table)
    result = Visibility(visible=[], identity=stats, unverified=unverified)
    fills = [fill for fill in layer.get("fills") or [] if float(fill[6]) >= 0.999]
    seen: dict[tuple[int, int], list[Glyph]] = {}
    for glyph in glyphs:
        if glyph.flags & GLYPH_FLAG_INVISIBLE:
            result.invisible_render_mode += 1
            continue
        if glyph.flags & GLYPH_FLAG_CLIPPED:
            result.clipped += 1
            continue
        if glyph.flags & GLYPH_FLAG_HIDDEN_LAYER:
            result.hidden_layer += 1
            continue
        cover = next((fill for fill in fills if fill[0] > glyph.paint and _inside(glyph, fill[1:5])), None)
        if cover is not None:
            result.hidden_by_fill[cover[5]] = result.hidden_by_fill.get(cover[5], 0) + 1
            continue
        if glyph.flags & GLYPH_FLAG_NOT_UPRIGHT:
            result.rotated.append(glyph)
            continue
        if glyph.kind == "text":
            cell = (round(glyph.cx / 4), round(glyph.cy / 4))
            twins = [other for dx in (-1, 0, 1) for dy in (-1, 0, 1) for other in seen.get((cell[0] + dx, cell[1] + dy), [])]
            if any(_same_glyph(glyph, other) for other in twins):
                # The same glyph painted again on top of itself (a footer set twice for weight).
                result.duplicates += 1
                continue
            seen.setdefault(cell, []).append(glyph)
        result.visible.append(glyph)
    return result


def _same_glyph(a: Glyph, b: Glyph) -> bool:
    if a.text != b.text or abs(a.size - b.size) > 0.05:
        return False
    width = _overlap(a.x0, a.x1, b.x0, b.x1)
    height = _overlap(a.top, a.bottom, b.top, b.bottom)
    area = min((a.x1 - a.x0) * (a.bottom - a.top), (b.x1 - b.x0) * (b.bottom - b.top))
    return area > 0 and width * height >= DUPLICATE_OVERLAP * area


# --- lines -----------------------------------------------------------------------------------------------------------


@dataclass
class Line:
    glyphs: list[Glyph]
    script: set[int] = field(default_factory=set)  # paint ids of script (superscript / subscript) glyphs

    @property
    def text_glyphs(self) -> list[Glyph]:
        return [glyph for glyph in self.glyphs if glyph.kind != "space"]

    @property
    def size(self) -> float:
        sizes = [glyph.size for glyph in self.text_glyphs if glyph.paint not in self.script] or [glyph.size for glyph in self.glyphs]
        return statistics.median(sizes)

    @property
    def baseline(self) -> float:
        values = [glyph.baseline for glyph in self.text_glyphs if glyph.paint not in self.script] or [glyph.baseline for glyph in self.glyphs]
        return statistics.median(values)

    @property
    def top(self) -> float:
        return min(glyph.top for glyph in self.glyphs)

    @property
    def bottom(self) -> float:
        return max(glyph.bottom for glyph in self.glyphs)


def _baseline_clusters(glyphs: list[Glyph]) -> list[list[Glyph]]:
    clusters: list[list[Glyph]] = []
    for glyph in sorted(glyphs, key=lambda item: (item.baseline, item.cx)):
        if clusters:
            last = clusters[-1]
            reference = statistics.median(item.baseline for item in last)
            if abs(glyph.baseline - reference) <= max(0.6, BASELINE_TOLERANCE_EM * glyph.size):
                last.append(glyph)
                continue
        clusters.append([glyph])
    return clusters


def _runs(glyphs: list[Glyph], gap_em: float) -> list[list[Glyph]]:
    runs: list[list[Glyph]] = []
    for glyph in sorted(glyphs, key=lambda item: item.cx):
        if runs and glyph.x0 - runs[-1][-1].x1 <= gap_em * max(glyph.size, runs[-1][-1].size):
            runs[-1].append(glyph)
        else:
            runs.append([glyph])
    return runs


def build_lines(glyphs: Iterable[Glyph]) -> list[Line]:
    """Group visible glyphs into lines by baseline, attaching smaller raised or lowered runs to the line they touch."""

    clusters = _baseline_clusters(list(glyphs))
    lines = [Line(glyphs=cluster) for cluster in clusters]
    hosts = sorted(lines, key=lambda line: -line.size)
    detached: list[Line] = []
    for line in sorted(lines, key=lambda line: line.size):
        if not line.text_glyphs:
            continue
        moved = False
        for run in _runs(line.glyphs, 0.5):
            run_text = [glyph for glyph in run if glyph.kind != "space"]
            if not run_text or len(run_text) > SCRIPT_MAX_GLYPHS:
                continue
            size = statistics.median(glyph.size for glyph in run_text)
            center = statistics.median(glyph.cy for glyph in run_text)
            for host in hosts:
                if host is line or host in detached or not host.text_glyphs or size > SCRIPT_SIZE_RATIO * host.size:
                    continue
                if not host.top <= center <= host.bottom:
                    continue
                reach = 0.6 * host.size
                near = any(other.x0 - reach <= run[-1].x1 and run[0].x0 <= other.x1 + reach for other in host.text_glyphs)
                if not near:
                    # A marker set off by a tab (a footnote number before its note) joins the line it is painted with.
                    paints = {glyph.paint for glyph in host.glyphs}
                    wide = SCRIPT_TAB_REACH_EM * host.size
                    near = any(other.x0 - wide <= run[-1].x1 and run[0].x0 <= other.x1 + wide for other in host.text_glyphs) and any(
                        glyph.paint + step in paints for glyph in run for step in (-2, -1, 1, 2)
                    )
                if not near:
                    continue
                host.glyphs.extend(run)
                host.script.update(glyph.paint for glyph in run)
                for glyph in run:
                    line.glyphs.remove(glyph)
                moved = True
                break
        if moved and not line.text_glyphs:
            detached.append(line)
    kept = [line for line in lines if line.text_glyphs]
    for line in kept:
        # A superscript set on (nearly) the line's own baseline: a markedly smaller glyph raised above it.
        size = line.size
        baseline = line.baseline
        for glyph in line.text_glyphs:
            if glyph.size <= SCRIPT_SIZE_RATIO * size and baseline - glyph.baseline >= SCRIPT_RISE_EM * size:
                line.script.add(glyph.paint)
    return sorted(kept, key=lambda line: (line.baseline, -line.glyphs[0].cx))


# --- segments --------------------------------------------------------------------------------------------------------


@dataclass
class Segment:
    """A piece of one line between column gutters: its visual clusters (each a logical string) and its glyphs."""

    clusters: list[str]
    glyphs: list[Glyph]
    size: float
    mirror: list[bool] = field(default_factory=list)
    tabs: int = 0
    script_spaces: int = 0
    inferred_spaces: int = 0
    letter_spaced: bool = False

    @property
    def x0(self) -> float:
        return min(glyph.x0 for glyph in self.glyphs)

    @property
    def x1(self) -> float:
        return max(glyph.x1 for glyph in self.glyphs)

    @property
    def top(self) -> float:
        return min(glyph.top for glyph in self.glyphs)

    @property
    def bottom(self) -> float:
        return max(glyph.bottom for glyph in self.glyphs)

    @property
    def box(self) -> list[float]:
        return [self.x0, self.top, self.x1, self.bottom]

    @property
    def visual(self) -> str:
        return "".join(self.clusters)

    def add_space(self) -> None:
        self.clusters.append(" ")
        self.mirror.append(False)


_LATIN_LIGATURES = {chr(code): unicodedata.normalize("NFKC", chr(code)) for code in range(0xFB00, 0xFB07)}


def _strip_format(text: str) -> str:
    """A glyph's text without format characters, with Latin presentation ligatures (U+FB00-FB06: ﬁ, ﬂ, ...) spelled
    out: the ligature is one glyph, the text is its letters."""

    return "".join(_LATIN_LIGATURES.get(char, char) for char in text if unicodedata.category(char) != "Cf")


def _mostly_over(space: Glyph, neighbours: Sequence[Glyph]) -> bool:
    """A zero-advance space glyph placed on top of a text glyph (a tab stop's placeholder) is not a word gap."""

    width = max(space.x1 - space.x0, 0.01)
    return any(min(space.x1, other.x1) - max(space.x0, other.x0) >= 0.5 * width for other in neighbours)


def _letterlike(text: str) -> bool:
    """Letters, the geresh and gershayim set inside names (סמוטריץ', כ"ץ) and the maqaf or dash joining them (בר־און)."""

    return text.isalpha() or text in {"'", '"', "׳", "״", "־", "-", "–"}


def _is_digit_glyph(glyph: Glyph) -> bool:
    return bool(glyph.text) and all(char.isdigit() for char in glyph.text)


def line_segments(line: Line) -> list[Segment]:
    """Cut a line into segments at column gutters and spell each one as visual clusters with word spaces."""

    ordered = sorted(line.glyphs, key=lambda glyph: (glyph.cx, glyph.paint))
    text = [glyph for glyph in ordered if glyph.kind == "text"]
    marks = [glyph for glyph in ordered if glyph.kind == "mark"]
    spaces = [glyph for glyph in ordered if glyph.kind == "space"]
    attached: dict[int, list[Glyph]] = {}
    for mark in marks:
        base = max(text, key=lambda glyph: min(glyph.x1, mark.x1) - max(glyph.x0, mark.x0), default=None)
        if base is not None:
            attached.setdefault(base.paint, []).append(mark)
    paint_order = sorted(line.glyphs, key=lambda glyph: glyph.paint)
    rank = {glyph.paint: index for index, glyph in enumerate(paint_order)}

    def paint_adjacent(a: Glyph, b: Glyph) -> bool:
        low, high = sorted((rank[a.paint], rank[b.paint]))
        return all(glyph.kind != "text" for glyph in paint_order[low + 1 : high])

    def uncovered(a: Glyph, b: Glyph) -> float:
        start, end = a.x1, b.x0
        if end <= start:
            return 0.0
        covered = 0.0
        cursor = start
        for space in sorted((space for space in spaces if space.x1 > start and space.x0 < end), key=lambda space: space.x0):
            low, high = max(space.x0, cursor), min(space.x1, end)
            if high > low:
                covered += high - low
                cursor = high
        return end - start - covered

    # Many booklets (most before 2011) set word spaces as glyph positioning, not as space glyphs, so an open gap
    # wider than INFERRED_WORD_GAP_EM is a word space. Letter-spaced print (signature names) is the exception: a run
    # of at least LETTER_SPACED_MIN_GAPS consecutive, even open gaps between letters (each LETTER_SPACED_MIN_EM to
    # 0.7 em, the widest at most LETTER_SPACED_EVENNESS times the narrowest); inside such a run a word space is a
    # space glyph or a gap LETTER_SPACED_WORD_GAP times the run's median gap.
    gaps: list[float | None] = []
    for a, b in zip(text, text[1:]):
        open_letter_gap = not any(a.cx < space.cx < b.cx for space in spaces) and _letterlike(a.text) and _letterlike(b.text)
        gaps.append((b.x0 - a.x1) / max(a.size, b.size) if open_letter_gap else None)

    def spaced_out(gap: float | None) -> bool:
        return gap is not None and LETTER_SPACED_MIN_EM < gap <= WORD_GAP_EM + 0.1

    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(gaps):
        if not spaced_out(gaps[index]):
            index += 1
            continue
        end = index
        while end < len(gaps) and spaced_out(gaps[end]):
            end += 1
        runs.append((index, end))
        index = end
    word_gap_after: dict[int, float] = {}
    spacings: list[float] = []
    short_runs: list[tuple[int, int]] = []
    for start, end in runs:
        run = sorted(gap for gap in gaps[start:end] if gap is not None)
        # The run's letter spacing: its lower half (a wider gap inside it may be a word space).
        letters = run[: max(1, (len(run) + 1) // 2)]
        if len(run) >= LETTER_SPACED_MIN_GAPS and letters[-1] <= LETTER_SPACED_EVENNESS * letters[0]:
            spacing = statistics.median(letters)
            spacings.append(spacing)
            for position in range(start, end):
                word_gap_after[text[position].paint] = LETTER_SPACED_WORD_GAP * spacing
        else:
            short_runs.append((start, end))
    # A short word in the same letter-spaced line (כ"ץ after ישראל) has the same spacing.
    for start, end in short_runs:
        run = [gap for gap in gaps[start:end] if gap is not None]
        match = next((spacing for spacing in spacings if all(0.6 * spacing <= gap <= 1.6 * spacing for gap in run)), None)
        if match is not None:
            for position in range(start, end):
                word_gap_after[text[position].paint] = LETTER_SPACED_WORD_GAP * match
    letter_spaced = bool(spacings)
    segments: list[Segment] = []
    current: Segment | None = None
    previous: Glyph | None = None
    for glyph in text:
        cluster = _strip_format(glyph.text) + "".join(_strip_format(mark.text) for mark in attached.get(glyph.paint, []))
        if previous is not None and current is not None:
            gap = glyph.x0 - previous.x1
            em = max(glyph.size, previous.size)
            open_gap = uncovered(previous, glyph)
            spaced = any(previous.cx < space.cx < glyph.cx and not _mostly_over(space, (previous, glyph)) for space in spaces)
            if open_gap > SEGMENT_GAP_EM * em or (open_gap > FRAME_GAP_EM * em and not paint_adjacent(previous, glyph)):
                segments.append(current)
                current = None
            elif spaced:
                current.add_space()
            elif gap > word_gap_after.get(previous.paint, INFERRED_WORD_GAP_EM) * em:
                current.add_space()
                if gap > WORD_GAP_EM * em:
                    current.tabs += 1
                else:
                    current.inferred_spaces += 1
            elif (glyph.paint in line.script) != (previous.paint in line.script) and _is_digit_glyph(glyph) and _is_digit_glyph(previous):
                current.add_space()
                current.script_spaces += 1
        if current is None:
            current = Segment(clusters=[], glyphs=[], size=line.size, letter_spaced=letter_spaced)
        current.clusters.append(cluster)
        current.mirror.append(glyph.mirror)
        current.glyphs.append(glyph)
        current.glyphs.extend(attached.get(glyph.paint, []))
        previous = glyph
    if current is not None:
        segments.append(current)
    for segment in segments:
        # A segment's own type size: a side heading set smaller shares its baseline with a body line.
        sizes = [glyph.size for glyph in segment.glyphs if glyph.kind == "text" and glyph.paint not in line.script]
        segment.size = statistics.median(sizes) if sizes else segment.size
    return segments


# --- bidi ------------------------------------------------------------------------------------------------------------

_STRONG_R = {"R", "AL"}
_NEUTRAL = {"WS", "ON", "S", "B"}


def bidi_class(cluster: str) -> str:
    """The bidi class of a cluster (its first character; a combining mark alone is NSM)."""

    if not cluster:
        return "ON"
    return unicodedata.bidirectional(cluster[0]) or "ON"


def unicode_bidi_levels(classes: Sequence[str]) -> list[int]:
    """Embedding levels for one right-to-left paragraph with no explicit embeddings (UBA W1-W7, N1-N2, I2, L1)."""

    types = list(classes)
    n = len(types)
    for i in range(n):  # W1
        if types[i] == "NSM":
            types[i] = types[i - 1] if i else "R"
    for i in range(n):  # W2/W3: Arabic letters do not occur; AL behaves as R
        if types[i] == "AL":
            types[i] = "R"
    for i in range(1, n - 1):  # W4
        if types[i] == "ES" and types[i - 1] == "EN" and types[i + 1] == "EN":
            types[i] = "EN"
        elif types[i] == "CS" and types[i - 1] == types[i + 1] and types[i - 1] in {"EN", "AN"}:
            types[i] = types[i - 1]
    i = 0
    while i < n:  # W5
        if types[i] == "ET":
            j = i
            while j < n and types[j] == "ET":
                j += 1
            if (i > 0 and types[i - 1] == "EN") or (j < n and types[j] == "EN"):
                for k in range(i, j):
                    types[k] = "EN"
            i = j
        else:
            i += 1
    for i in range(n):  # W6
        if types[i] in {"ES", "ET", "CS"}:
            types[i] = "ON"
    strong = "R"
    for i in range(n):  # W7
        if types[i] in {"L", "R"}:
            strong = types[i]
        elif types[i] == "EN" and strong == "L":
            types[i] = "L"
    i = 0
    while i < n:  # N1/N2
        if types[i] in _NEUTRAL or types[i] in {"LRE", "RLE", "PDF", "BN"}:
            j = i
            while j < n and (types[j] in _NEUTRAL or types[j] in {"BN"}):
                j += 1
            before = "R" if i == 0 else ("R" if types[i - 1] in {"EN", "AN", "R"} else types[i - 1])
            after = "R" if j >= n else ("R" if types[j] in {"EN", "AN", "R"} else types[j])
            resolved = before if before == after else "R"
            for k in range(i, j):
                types[k] = resolved
            i = max(j, i + 1)
        else:
            i += 1
    levels = [2 if kind in {"L", "EN", "AN"} else 1 for kind in types]  # I2
    for i in range(n - 1, -1, -1):  # L1: trailing whitespace takes the paragraph level
        if classes[i] in {"WS", "S"}:
            levels[i] = 1
        else:
            break
    return levels


def unicode_bidi_visual(clusters: Sequence[str]) -> list[str]:
    """The visual (left-to-right display) order of logical-order clusters in a right-to-left paragraph (UBA L2)."""

    return unicode_bidi_display(clusters)


def _ltr_marks(classes: list[str], merge_latin_numbers: bool) -> tuple[list[bool], int]:
    """Which positions of a reversed visual sequence belong to left-to-right runs, and how many Latin-number joins."""

    n = len(classes)
    number = [kind == "EN" for kind in classes]
    for i in range(1, n - 1):
        if classes[i] in {"ES", "CS"} and number[i - 1] and classes[i + 1] == "EN":
            number[i] = True
    for i in range(n):
        if classes[i] == "ET" and ((i > 0 and number[i - 1]) or (i + 1 < n and number[i + 1])):
            number[i] = True
    ltr = [classes[i] == "L" or number[i] for i in range(n)]
    joins = 0
    i = 0
    while i < n:
        if ltr[i]:
            i += 1
            continue
        j = i
        while j < n and not ltr[j] and classes[j] not in _STRONG_R and classes[j] != "NSM":
            j += 1
        if 0 < i and j < n and ltr[j] and j > i:
            left = "L" if classes[i - 1] == "L" else "N"
            right = "L" if classes[j] == "L" else "N"
            if left == right == "L" or (merge_latin_numbers and left != right):
                for k in range(i, j):
                    ltr[k] = True
                if left != right:
                    joins += 1
        i = max(j, i + 1)
    return ltr, joins


MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "{": "}", "}": "{", "<": ">", ">": "<"}


def _mirrored(clusters: Sequence[str], levels: Sequence[int], mirror: Sequence[bool]) -> list[str]:
    return [MIRROR.get(cluster, cluster) if flag and level % 2 else cluster for cluster, level, flag in zip(clusters, levels, mirror)]


def unicode_bidi_display(clusters: Sequence[str], mirror: Sequence[bool] | None = None) -> list[str]:
    """What a renderer shows, left to right, for logical clusters: UBA order (L2) and, for clusters flagged in
    ``mirror``, the mirrored glyph at right-to-left levels (L4)."""

    flags = list(mirror) if mirror is not None else [False] * len(clusters)
    levels = unicode_bidi_levels([bidi_class(cluster) for cluster in clusters])
    shown = _mirrored(clusters, levels, flags)
    order = list(range(len(clusters)))
    for level in (2, 1):
        i = 0
        while i < len(order):
            if levels[order[i]] >= level:
                j = i
                while j < len(order) and levels[order[j]] >= level:
                    j += 1
                order[i:j] = reversed(order[i:j])
                i = j
            else:
                i += 1
    return [shown[index] for index in order]


def visual_to_logical(visual: Sequence[str], mirror: Sequence[bool] | None = None) -> tuple[list[str], dict[str, Any]]:
    """Invert the bidi reordering of one right-to-left segment given in visual order.

    ``visual`` holds the clusters left to right; ``mirror`` flags clusters that are a bracket's drawn shape (the
    glyph outline), whose character is its mirror image where the run is right to left. Returns the logical clusters
    and facts: ``round_trip`` (the forward algorithm reproduces ``visual``) and ``ambiguous_joins`` (Latin-number
    joins whose other reading round-trips too).
    """

    flags = list(mirror) if mirror is not None else [False] * len(visual)
    reversed_index = list(range(len(visual)))[::-1]
    classes = [bidi_class(visual[index]) for index in reversed_index]
    results = []
    for merge in (True, False):
        ltr, joins = _ltr_marks(classes, merge)
        order: list[int] = []
        i = 0
        while i < len(reversed_index):
            if ltr[i]:
                j = i
                while j < len(reversed_index) and ltr[j]:
                    j += 1
                order.extend(reversed(reversed_index[i:j]))
                i = j
            else:
                order.append(reversed_index[i])
                i += 1
        shapes = [visual[index] for index in order]
        order_flags = [flags[index] for index in order]
        levels = unicode_bidi_levels([bidi_class(cluster) for cluster in shapes])
        logical = _mirrored(shapes, levels, order_flags)
        results.append((logical, joins, unicode_bidi_display(logical, order_flags) == list(visual)))
    (merged, joins, merged_ok), (split, _, split_ok) = results
    if merged_ok:
        return merged, {"round_trip": True, "ambiguous_joins": joins if split_ok and split != merged else 0}
    if split_ok:
        return split, {"round_trip": True, "ambiguous_joins": 0}
    return merged, {"round_trip": False, "ambiguous_joins": 0}


# --- reading order ---------------------------------------------------------------------------------------------------


@dataclass
class Unit:
    """One output line: one or more segments (a label and the line it numbers), its logical text and its facts."""

    segment: Segment
    text: str
    round_trip: bool
    ambiguous_joins: int
    issues: list[str]
    block: int = -1
    parts: list[Segment] = field(default_factory=list)

    @property
    def segments(self) -> list[Segment]:
        return [self.segment, *self.parts]

    @property
    def box(self) -> list[float]:
        boxes = [segment.box for segment in self.segments]
        return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]

    @property
    def glyphs(self) -> list[Glyph]:
        return [glyph for segment in self.segments for glyph in segment.glyphs]


_HEBREW_LETTER = re.compile("[א-ת]")
_LABEL_PREFIX = re.compile(r"^(?:\d+[א-ת]?\d*\.|\([א-ת0-9]{1,3}\d?\))\s")
_LABEL = re.compile(r"^(?:\d+[א-ת]?\d*\.|\([א-ת0-9]{1,3}\d?\)|\*+|\d{1,3})$")


def merge_labels(units: list[Unit]) -> list[Unit]:
    """A label set off by a tab or a hanging indent (``3.``, ``2ג.``, ``(א)``, a footnote number) joins the line it
    labels: the nearest unit on its row to its left, at most ``LABEL_REACH_EM`` ems away. Each part keeps its own bidi
    check; the label is read first."""

    remaining = list(units)
    # Leftmost labels first, so that a run of labels (63. (א) (1) ...) chains onto the line one by one.
    for label in sorted((unit for unit in units if _LABEL.match(unit.text)), key=lambda unit: unit.box[2]):
        if label not in remaining:
            continue
        lx0, ltop, _, lbottom = label.box
        best = None
        for other in remaining:
            if other is label:
                continue
            x0, top, x1, bottom = other.box
            if x1 > lx0 + 0.5 or lx0 - x1 > LABEL_REACH_EM * label.segment.size:
                continue
            if _overlap(top, bottom, ltop, lbottom) < 0.5 * min(bottom - top, lbottom - ltop):
                continue
            if best is None or x1 > best.box[2]:
                best = other
        if best is None:
            continue
        best.parts.insert(0, best.segment)
        best.segment = label.segment
        best.text = f"{label.text} {best.text}"
        best.round_trip = best.round_trip and label.round_trip
        best.ambiguous_joins += label.ambiguous_joins
        best.issues = sorted(set(best.issues) | set(label.issues))
        remaining.remove(label)
    return remaining


QUOTE_LIKE = frozenset("'\"׳״′″‘’“”`´°º")


def quote_between_ltr_runs(visual: Sequence[str]) -> bool:
    """A quote, prime or degree sign set between two left-to-right runs (``29º 32' 26.33"``).

    The forward bidi algorithm makes such a neutral right to left, so the logical text that reproduces the print puts
    the marks where nobody types them; the producer's composer evidently did not apply the algorithm. Which logical
    order was meant cannot be verified from the page.
    """

    def ltr(cluster: str) -> bool:
        return bidi_class(cluster) in {"L", "EN"}

    for index, cluster in enumerate(visual):
        if cluster not in QUOTE_LIKE:
            continue
        left = next((visual[i] for i in range(index - 1, -1, -1) if visual[i] != " "), "")
        right = next((visual[i] for i in range(index + 1, len(visual)) if visual[i] != " "), "")
        touching = (index > 0 and ltr(visual[index - 1])) or (index + 1 < len(visual) and ltr(visual[index + 1]))
        if left and right and ltr(left) and ltr(right) and touching:
            return True
    return False


DASHES = frozenset("-‐‑‒–—―־−")


def dash_between_numbers_ambiguous(visual: Sequence[str]) -> bool:
    """A dash set directly between two digits whose reading depends on which dash it is.

    A hyphen-minus is a number separator in the bidi algorithm (``3-6325`` stays one left-to-right run); an en dash
    is a neutral (``383–385`` shows as ``385–383``). The Reshumot fonts draw both with one glyph and their ToUnicode
    maps name one character for it, so where the two readings give different logical text the order is not
    verifiable from the page.
    """

    positions = [
        index for index in range(1, len(visual) - 1)
        if visual[index] in DASHES and visual[index - 1][:1].isdigit() and visual[index + 1][:1].isdigit()
    ]
    if not positions:
        return False
    readings = []
    for dash in ("-", "–"):
        trial = list(visual)
        for index in positions:
            trial[index] = dash
        logical, _ = visual_to_logical(trial)
        readings.append("".join("-" if cluster in DASHES else cluster for cluster in logical))
    return readings[0] != readings[1]


def segment_issues(segment: Segment, logical: Sequence[str], facts: dict[str, Any], unverified: set[int] = frozenset()) -> list[str]:  # type: ignore[assignment]
    issues = set()
    if not facts["round_trip"]:
        issues.add("bidi_round_trip_failed")
    if quote_between_ltr_runs(segment.clusters):
        issues.add("quote_between_ltr_runs")
    if dash_between_numbers_ambiguous(segment.clusters):
        issues.add("dash_between_numbers_ambiguous")
    for glyph in segment.glyphs:
        if glyph.paint in unverified:
            issues.add("glyph_identity_unverified")
        if "�" in glyph.text or glyph.text.startswith("(cid:"):
            issues.add("unmapped_glyph")
        if any(unicodedata.category(char) == "Co" for char in glyph.text):
            issues.add("private_use_glyph")
    return sorted(issues)


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def build_blocks(units: list[Unit]) -> list[list[Unit]]:
    """Stack units into column blocks: each unit joins the block of the nearest unit above it in the same column."""

    ordered = sorted(units, key=lambda unit: (unit.box[1], -unit.box[2]))
    blocks: list[list[Unit]] = []
    for unit in ordered:
        x0, top, x1, _ = unit.box
        best = None
        for index, block in enumerate(blocks):
            last = block[-1]
            lx0, _, lx1, lbottom = last.box
            narrow = min(x1 - x0, lx1 - lx0)
            if narrow <= 0 or _overlap(x0, x1, lx0, lx1) < 0.3 * narrow:
                continue
            gap = top - lbottom
            size = max(unit.segment.size, last.segment.size)
            if gap < -0.3 * size or gap > BLOCK_LINE_GAP_EM * size:
                continue
            if not BLOCK_SIZE_RATIO[0] <= unit.segment.size / last.segment.size <= BLOCK_SIZE_RATIO[1]:
                continue
            if best is None or lbottom > blocks[best][-1].box[3]:
                best = index
        if best is None:
            blocks.append([unit])
        else:
            blocks[best].append(unit)
    for index, block in enumerate(blocks):
        for unit in block:
            unit.block = index
    return blocks


def reading_order(units: list[Unit]) -> list[Unit]:
    """Body blocks line by line, narrower blocks whole; top to bottom, right to left within a row."""

    if not units:
        return []
    blocks = build_blocks(units)
    left = min(unit.box[0] for unit in units)
    right = max(unit.box[2] for unit in units)
    width = max(right - left, 1.0)
    # (top, right edge, size, units, is body, left edge)
    items: list[tuple[float, float, float, list[Unit], bool, float]] = []
    for block in blocks:
        bx0 = min(unit.box[0] for unit in block)
        bx1 = max(unit.box[2] for unit in block)
        if (bx1 - bx0) >= MAIN_BLOCK_SHARE * width:
            items.extend((unit.box[1], unit.box[2], unit.segment.size, [unit], True, unit.box[0]) for unit in block)
        else:
            items.append((block[0].box[1], bx1, block[0].segment.size, block, False, bx0))
    items.sort(key=lambda item: (item[0], -item[1]))
    ordered: list[Unit] = []

    body_items = [item for item in items if item[4]]
    column = (min(item[5] for item in body_items), max(item[1] for item in body_items)) if body_items else None

    def flush(row: list[tuple[float, float, float, list[Unit], bool, float]]) -> None:
        anchored = any(entry[4] or _LABEL_PREFIX.match(entry[3][0].text) for entry in row)
        if column is not None and anchored:
            # Narrow blocks of words wholly outside the body column (side headings in either margin) are read before the
            # row when the row holds body text or a numbered line; a page number in the margin is not a heading, and a
            # row of separate pieces (the imprint line) is read right to left.
            margin = [
                entry for entry in row
                if not entry[4] and (entry[5] >= column[1] - 1 or entry[1] <= column[0] + 1) and _HEBREW_LETTER.search(entry[3][0].text)
            ]
            rest = [entry for entry in row if entry not in margin]
            row = sorted(margin, key=lambda entry: -entry[1]) + sorted(rest, key=lambda entry: -entry[1])
        else:
            row = sorted(row, key=lambda entry: -entry[1])
        for entry in row:
            ordered.extend(entry[3])

    def same_row(first: tuple[float, float, float, list[Unit], bool, float], item: tuple[float, float, float, list[Unit], bool, float]) -> bool:
        # Items share a row when their first lines overlap by half the shorter line, or their tops are close.
        a, b = first[3][0].box, item[3][0].box
        shorter = min(a[3] - a[1], b[3] - b[1])
        return item[0] - first[0] <= ROW_TOLERANCE_EM * min(first[2], item[2]) or (shorter > 0 and _overlap(a[1], a[3], b[1], b[3]) >= 0.5 * shorter)

    row: list[tuple[float, float, float, list[Unit], bool, float]] = []
    for item in items:
        if row and not same_row(row[0], item):
            flush(row)
            row = []
        row.append(item)
    if row:
        flush(row)
    return ordered


@dataclass
class PageConversion:
    units: list[Unit]
    visibility: Visibility
    format_characters: dict[str, int]
    layout: dict[str, int]

    @property
    def text(self) -> str:
        return units_text(self.units)


def units_text(units: Iterable[Unit]) -> str:
    lines = [unit.text for unit in units if unit.text]
    return unicodedata.normalize("NFC", "\n".join(lines) + "\n") if lines else ""


def _collapse(clusters: list[str]) -> str:
    text = "".join(clusters)
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def convert_glyph_layer(layer: dict[str, Any], table: dict[str, Any] | None = None) -> PageConversion:
    """The page's units in reading order, each with its logical text and segment-level issues.

    ``table`` is the glyph outline identity table (``resolve_glyph_texts``)."""

    visibility = visible_glyphs(layer, table)
    # Format characters are never text. A glyph mapped to one (U+FEFF, U+200F) with an advance is a space glyph;
    # inside a text glyph's mapping it is dropped. Both are counted by code point.
    format_characters: dict[str, int] = {}
    for glyph in visibility.visible:
        for char in glyph.text:
            if unicodedata.category(char) == "Cf":
                key = f"U+{ord(char):04X}"
                format_characters[key] = format_characters.get(key, 0) + 1
    units: list[Unit] = []
    layout = {"segments": 0, "letter_spaced_segments": 0, "tabs": 0, "inferred_spaces": 0, "script_spaces": 0, "script_glyphs": 0, "ambiguous_joins": 0}
    for line in build_lines(visibility.visible):
        layout["script_glyphs"] += len(line.script)
        for segment in line_segments(line):
            logical, facts = visual_to_logical(segment.clusters, segment.mirror)
            text = _collapse(logical)
            units.append(Unit(segment, text, facts["round_trip"], facts["ambiguous_joins"], segment_issues(segment, logical, facts, visibility.unverified)))
            layout["segments"] += 1
            layout["tabs"] += segment.tabs
            layout["script_spaces"] += segment.script_spaces
            layout["inferred_spaces"] += segment.inferred_spaces
            layout["letter_spaced_segments"] += segment.letter_spaced
            layout["ambiguous_joins"] += facts["ambiguous_joins"]
    return PageConversion(units=reading_order(merge_labels(units)), visibility=visibility, format_characters=format_characters, layout=layout)


# --- ink -------------------------------------------------------------------------------------------------------------

INK_THRESHOLD = 128
INK_GLYPH_PAD_PX = 1.5
INK_BLOB_MIN_PIXELS = 4


def _pixel_box(box: Sequence[float], scale: float, pad: float, width: int, height: int) -> tuple[int, int, int, int]:
    return (
        max(0, math.floor(box[0] * scale - pad)),
        max(0, math.floor(box[1] * scale - pad)),
        min(width, math.ceil(box[2] * scale + pad)),
        min(height, math.ceil(box[3] * scale + pad)),
    )


@dataclass
class InkReport:
    glyphs_without_ink: list[int]  # paint ids
    blobs: list[list[float]]  # boxes (points) of inked areas no glyph, stroke, fill or image explains


def ink_report(conversion: PageConversion, layer: dict[str, Any], image: Any, dpi: float, boxes: Iterable[Sequence[float]] | None = None) -> InkReport:
    """Check a conversion against the page render (a PIL image; any mode, read as 8-bit gray).

    - Every kept text glyph must hold at least one inked pixel (value below ``INK_THRESHOLD``) inside its box.
    - Every inked pixel must lie inside a kept glyph's box (padded by ``INK_GLYPH_PAD_PX``), a stroke, a non-white
      fill or an image. Uncovered inked pixels are grouped into 8-connected blobs; blobs of at least
      ``INK_BLOB_MIN_PIXELS`` pixels are reported with their boxes in points.

    ``boxes`` limits the second check to these regions (points), for a page cropped to its verified regions.
    """

    from PIL import Image, ImageChops, ImageDraw

    gray = image.convert("L")
    width, height = gray.size
    scale = dpi / 72.0
    without_ink = []
    for unit in conversion.units:
        for glyph in unit.glyphs:
            if glyph.kind != "text":
                continue
            box = _pixel_box(glyph.ink_box, scale, 0.5, width, height)
            if box[2] <= box[0] or box[3] <= box[1] or gray.crop(box).getextrema()[0] >= INK_THRESHOLD:
                without_ink.append(glyph.paint)
    covered = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(covered)

    def cover(box: Sequence[float], pad: float) -> None:
        x0, y0, x1, y1 = _pixel_box(box, scale, pad, width, height)
        if x1 > x0 and y1 > y0:
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)

    for unit in conversion.units:
        for glyph in unit.glyphs:
            cover(glyph.ink_box, INK_GLYPH_PAD_PX)
    for stroke in layer.get("strokes") or []:
        cover(stroke[1:5], 2.0)
    for fill in layer.get("fills") or []:
        if fill[5] != "white":
            cover(fill[1:5], 1.0)
    for image_box in layer.get("images") or []:
        cover(image_box[1:5], 1.0)
    ink = gray.point(lambda value: 255 if value < INK_THRESHOLD else 0)
    stray = ImageChops.subtract(ink, covered)
    if boxes is not None:
        keep = Image.new("L", (width, height), 0)
        keep_draw = ImageDraw.Draw(keep)
        for box in boxes:
            x0, y0, x1, y1 = _pixel_box(box, scale, 0.0, width, height)
            if x1 > x0 and y1 > y0:
                keep_draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
        stray = ImageChops.multiply(stray, keep)
    blobs = []
    if stray.getbbox() is not None:
        data = stray.tobytes()
        seen = bytearray(len(data))
        for start in (index for index, value in enumerate(data) if value):
            if seen[start]:
                continue
            stack = [start]
            seen[start] = 1
            xs, ys = [], []
            while stack:
                index = stack.pop()
                y, x = divmod(index, width)
                xs.append(x)
                ys.append(y)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            neighbour = ny * width + nx
                            if data[neighbour] and not seen[neighbour]:
                                seen[neighbour] = 1
                                stack.append(neighbour)
            if len(xs) >= INK_BLOB_MIN_PIXELS:
                blobs.append([round(min(xs) / scale, 2), round(min(ys) / scale, 2), round((max(xs) + 1) / scale, 2), round((max(ys) + 1) / scale, 2)])
    return InkReport(glyphs_without_ink=without_ink, blobs=blobs)


# --- page verdict: verified units, crop regions (decision 12) ------------------------------------------------------

REGION_PAD_PT = 1.5
EXCLUSION_PAD_PT = 1.0


@dataclass
class PageVerdict:
    """What of a page may be paired: the kept units' text and, when anything was left out, the crop regions."""

    kept: list[Unit]
    dropped: dict[str, int]  # reason -> units left out
    regions: list[list[float]] | None  # crop regions in points; None for the whole page
    excluded: list[list[float]]  # boxes (points) the regions avoid
    ink: InkReport
    region_ink_blobs: list[list[float]]

    @property
    def text(self) -> str:
        return units_text(self.kept)


def _pad(box: Sequence[float], pad: float) -> list[float]:
    return [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad]


def _intersects(a: Sequence[float], b: Sequence[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _union(boxes: Iterable[Sequence[float]]) -> list[float]:
    boxes = list(boxes)
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def unit_ink_box(unit: Unit) -> list[float]:
    return _union(glyph.ink_box for glyph in unit.glyphs) if unit.glyphs else unit.box


def image_ink_boxes(conversion: PageConversion, layer: dict[str, Any], image: Any, dpi: float) -> list[list[float]]:
    """Where each page image actually shows: the box of the inked pixels inside the image's placement that no glyph
    explains. An image's placement box often has transparent margins (a stamp drawn under its soft mask); the
    margins hide nothing. An image with no such ink excludes nothing."""

    from PIL import ImageDraw

    gray = image.convert("L")
    width, height = gray.size
    scale = dpi / 72.0
    glyph_mask = gray.point(lambda value: 0)
    draw = ImageDraw.Draw(glyph_mask)
    for unit in conversion.units:
        for glyph in unit.glyphs:
            x0, y0, x1, y1 = _pixel_box(glyph.ink_box, scale, INK_GLYPH_PAD_PX, width, height)
            if x1 > x0 and y1 > y0:
                draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
    boxes = []
    for placement in layer.get("images") or []:
        x0, y0, x1, y1 = _pixel_box(placement[1:5], scale, 0.0, width, height)
        if x1 <= x0 or y1 <= y0:
            continue
        ink = gray.crop((x0, y0, x1, y1)).point(lambda value: 255 if value < INK_THRESHOLD else 0)
        from PIL import ImageChops

        own = ImageChops.subtract(ink, glyph_mask.crop((x0, y0, x1, y1))).getbbox()
        if own is not None:
            boxes.append([round((x0 + own[0]) / scale, 2), round((y0 + own[1]) / scale, 2), round((x0 + own[2]) / scale, 2), round((y0 + own[3]) / scale, 2)])
    return boxes


def page_verdict(conversion: PageConversion, layer: dict[str, Any], image: Any, dpi: float) -> PageVerdict:
    """Keep the units whose text is verified and visible; crop the page to them when anything else is printed.

    - A unit none of whose glyphs has ink on the render is not on the page image: it is left out (``no_ink``) and
      needs no crop, since the image shows nothing there.
    - A unit with a segment issue (``SEGMENT_ISSUES``), with some glyphs without ink, or overlapping a page image or
      rotated text is left out (``unverified``) and its ink box is excluded from the pair image.
    - Ink no glyph explains (``ink_report`` blobs), page images and rotated glyphs are excluded too.
    - A kept unit whose box touches an excluded box cannot be cut apart from it and is left out (``inseparable``).
    - With nothing excluded the pair is the whole page. Otherwise the regions are bands of kept units that stay clear
      of every excluded box; the pair image is their union with everything outside them masked (as F8b5 crops), and
      the ink inside the regions must again be fully explained by the kept glyphs (``region_ink_blobs``).
    """

    report = ink_report(conversion, layer, image, dpi)
    no_ink = set(report.glyphs_without_ink)
    images = image_ink_boxes(conversion, layer, image, dpi)
    rotated = [[glyph.x0, glyph.top, glyph.x1, glyph.bottom] for glyph in conversion.visibility.rotated]
    excluded = [_pad(box, EXCLUSION_PAD_PT) for box in report.blobs + images + rotated]
    dropped: dict[str, int] = {}
    candidates: list[Unit] = []
    for unit in conversion.units:
        text_glyphs = [glyph for glyph in unit.glyphs if glyph.kind == "text"]
        inkless = [glyph for glyph in text_glyphs if glyph.paint in no_ink]
        if text_glyphs and len(inkless) == len(text_glyphs):
            dropped["no_ink"] = dropped.get("no_ink", 0) + 1
            continue
        box = unit_ink_box(unit)
        if unit.issues or inkless or any(_intersects(box, other) for other in images + rotated):
            dropped["unverified"] = dropped.get("unverified", 0) + 1
            excluded.append(_pad(box, EXCLUSION_PAD_PT))
            continue
        candidates.append(unit)
    kept = []
    for unit in candidates:
        if any(_intersects(_pad(unit_ink_box(unit), REGION_PAD_PT), other) for other in excluded):
            dropped["inseparable"] = dropped.get("inseparable", 0) + 1
            excluded.append(_pad(unit_ink_box(unit), EXCLUSION_PAD_PT))
            continue
        kept.append(unit)
    # A unit dropped as inseparable can make an earlier kept unit inseparable in turn.
    while True:
        clash = [unit for unit in kept if any(_intersects(_pad(unit_ink_box(unit), REGION_PAD_PT), other) for other in excluded)]
        if not clash:
            break
        for unit in clash:
            kept.remove(unit)
            dropped["inseparable"] = dropped.get("inseparable", 0) + 1
            excluded.append(_pad(unit_ink_box(unit), EXCLUSION_PAD_PT))
    if not excluded:
        return PageVerdict(kept=kept, dropped=dropped, regions=None, excluded=[], ink=report, region_ink_blobs=[])
    regions: list[list[float]] = []
    for unit in sorted(kept, key=lambda unit: (unit_ink_box(unit)[1], -unit_ink_box(unit)[2])):
        box = _pad(unit_ink_box(unit), REGION_PAD_PT)
        for index, region in enumerate(regions):
            merged = _union([region, box])
            if not any(_intersects(merged, other) for other in excluded) and not any(
                _intersects(merged, other) for position, other in enumerate(regions) if position != index
            ):
                regions[index] = merged
                break
        else:
            regions.append(box)
    width, height = float(layer["page"]["width"]), float(layer["page"]["height"])
    regions = [[max(0.0, r[0]), max(0.0, r[1]), min(width, r[2]), min(height, r[3])] for r in regions]
    inside = ink_report(PageConversion(kept, conversion.visibility, {}, {}), layer, image, dpi, boxes=regions).blobs if regions else []
    return PageVerdict(kept=kept, dropped=dropped, regions=regions, excluded=excluded, ink=report, region_ink_blobs=inside)


@dataclass
class GlyphPageResult:
    conversion: PageConversion
    verdict: PageVerdict
    text: str
    issues: list[str]

    def facts(self) -> dict[str, Any]:
        """What the conversion and the checks did, for the entry's record."""

        visibility = self.conversion.visibility
        return {
            "units": len(self.conversion.units),
            "units_kept": len(self.verdict.kept),
            "units_dropped": dict(sorted(self.verdict.dropped.items())),
            "glyphs_hidden_by_fill": dict(sorted(visibility.hidden_by_fill.items())),
            "glyphs_clipped": visibility.clipped,
            "glyphs_in_hidden_layers": visibility.hidden_layer,
            "glyphs_invisible_render_mode": visibility.invisible_render_mode,
            "glyphs_painted_twice": visibility.duplicates,
            "glyphs_rotated": len(visibility.rotated),
            "glyph_identity": dict(sorted(visibility.identity.items())),
            "format_characters_removed": dict(sorted(self.conversion.format_characters.items())),
            "layout": dict(sorted(self.conversion.layout.items())),
        }


def verify_glyph_page(layer: dict[str, Any], table: dict[str, Any], image: Any, dpi: float, expected_phrases: Iterable[str] | None = None, *, expected: Any = None) -> GlyphPageResult:
    """Convert a glyph layer, check it against its render and keep what is verified.

    ``expected`` may be a callable from the kept text to the expected phrases (the printed page number, and so the
    titles, are read from the text). ``issues`` holds the page-level reasons the kept text cannot be admitted: the
    order checks of ``hocrgen.parsers.pdf_bidi.logical_order_issues`` on the kept text, ``ink_without_glyph`` when ink
    inside the crop regions is not explained by kept glyphs, and ``no_verified_text`` when nothing is kept.
    """

    from hocrgen.parsers.pdf_bidi import logical_order_issues

    conversion = convert_glyph_layer(layer, table)
    verdict = page_verdict(conversion, layer, image, dpi)
    text = verdict.text
    phrases = list(expected(text)) if callable(expected) else list(expected_phrases or [])
    if not text:
        issues = {"no_verified_text"}
    else:
        issues = set(logical_order_issues(text, phrases))
    if verdict.region_ink_blobs:
        issues.add("ink_without_glyph")
    return GlyphPageResult(conversion=conversion, verdict=verdict, text=text, issues=sorted(issues))
