"""S16: harvest printed Hebrew glyph images from real scans into a ``printed_glyph_bank.v1`` directory.

hocrsyngen composes synthetic book pages from the bank (``docs/printed_glyph_bank_v1.md`` there), so recognizer
training sees real letterpress instead of font renders. This tool reads hocrgen's own real-source snapshots and is
the only place that knows their layouts, splits and rights records.

How a glyph is labelled:

1. A *unit* is a run of reference text plus the Tesseract words located on the same scan: a whole page
   (Wikisource proofread text) or one aligned line (Ben-Yehuda). Tesseract only locates words; its text is never
   a label.
2. Reference and OCR characters are aligned with difflib. A reference word is paired with the one OCR word that
   holds most of its aligned characters, and only when that OCR word belongs to no other reference word.
3. The word box is binarized (Sauvola) and split into connected components; components that overlap
   horizontally are merged (the leg of ה and ק, the dot of ! ? ; :). A word is kept only when the number of
   merged groups equals the number of characters it should show.
4. Per style (one book), every glyph is checked by a nearest-centroid classifier built from that style's own
   glyphs. A glyph is kept only when its own label wins, so a word paired with the wrong box drops out.

Words with niqqud, cantillation or Latin letters are skipped in v1. Digit runs are handled in visual order.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import statistics
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from PIL import Image

from hocrgen.core.errors import StageExecutionError

BANK_SCHEMA = "printed_glyph_bank.v1"
TOOL_NAME = "hocrgen.tools.glyph_harvest"
TOOL_VERSION = "s16-glyph-harvest-v3"

HEBREW_LETTERS = frozenset(chr(code) for code in range(0x05D0, 0x05EB))
DIGITS = frozenset("0123456789")
PUNCTUATION = frozenset(".,:;!?()[]-\"'״׳–—־/")
HARVESTABLE = HEBREW_LETTERS | DIGITS | PUNCTUATION
# Letters with neither ascender nor descender; their median height is the style's x-height.
X_HEIGHT_LETTERS = frozenset("אבגדהחטכמסעפצשתם")
DESCENDERS = frozenset("ךןףץק")
DOUBLE_MARKS = frozenset("\"״")
SINGLE_MARKS = frozenset("'׳")
# Characters whose bottom is not on the baseline, so they do not vote for it.
OFF_BASELINE = DESCENDERS | frozenset("'\"״׳-–—־()[]י")

_MARK_RE = re.compile(r"[֑-ׇ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_SPLIT_RE = re.compile(r"\s+")


def _require_numeric():
    try:
        import numpy
        from scipy import ndimage
    except ImportError as exc:  # pragma: no cover - environment guard
        raise StageExecutionError("glyph harvesting needs numpy and scipy: pip install -e '.[glyphs]'") from exc
    return numpy, ndimage


# --------------------------------------------------------------------------------------------------------------
# Inputs


@dataclass(frozen=True)
class OcrWord:
    text: str
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 in page-image pixels
    line_key: tuple[int, int, int]


@dataclass
class Unit:
    """Reference text and the OCR words located on the same page image."""

    style_id: str
    page_id: str
    image_path: Path
    reference_text: str
    ocr_words: list[OcrWord]
    page_words: list[OcrWord] | None = None  # every word on the page, for page statistics; default ``ocr_words``


@dataclass(frozen=True)
class StyleSource:
    style_id: str
    source_id: str
    work_id: str
    licence: str
    attribution: str | None = None
    born_digital: bool = False
    match_key: str | None = None  # work-group key (hocrgen.split.work_groups) for the synthetic-training registry


def read_tesseract_tsv(path: Path, *, target_width: int | None = None) -> list[OcrWord]:
    """Word rows of a Tesseract TSV, scaled to ``target_width`` when the TSV frame differs."""
    rows = [line.rstrip("\n").split("\t") for line in path.read_text(encoding="utf-8").splitlines()]
    frame_width = None
    words: list[OcrWord] = []
    for row in rows[1:]:
        if len(row) < 12:
            continue
        level = row[0]
        if level == "1":
            frame_width = int(row[8])
        if level != "5" or not row[11].strip():
            continue
        left, top, width, height = (int(value) for value in row[6:10])
        scale = (target_width / frame_width) if (target_width and frame_width) else 1.0
        box = (round(left * scale), round(top * scale), round((left + width) * scale), round((top + height) * scale))
        words.append(OcrWord(text=row[11].strip(), box=box, line_key=(int(row[2]), int(row[3]), int(row[4]))))
    return words


# --------------------------------------------------------------------------------------------------------------
# Text


def reference_words(text: str) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\[\d+\]", " ", text)  # footnote marks
    return [word for word in _SPLIT_RE.split(text) if word]


def harvestable_word(word: str) -> bool:
    return bool(word) and not _MARK_RE.search(word) and not _LATIN_RE.search(word) and all(
        char in HARVESTABLE for char in word
    )


def visual_order(word: str) -> list[str]:
    """Characters of ``word`` from right to left on the page: Hebrew runs keep logical order, digit runs flip."""
    out: list[str] = []
    run: list[str] = []
    for index, char in enumerate(word):
        in_number = char in DIGITS or (
            char in ".,/" and run and index + 1 < len(word) and word[index + 1] in DIGITS
        )
        if in_number:
            run.append(char)
            continue
        if run:
            out.extend(reversed(run))
            run = []
        out.append(char)
    out.extend(reversed(run))
    return out


def pair_words(reference: Sequence[str], ocr: Sequence[str]) -> list[tuple[int, int]]:
    """Pairs ``(reference_index, ocr_index)`` from a character-level alignment of the two word sequences."""
    ref_chars, ref_owner = _flatten(reference)
    ocr_chars, ocr_owner = _flatten(ocr)
    matcher = difflib.SequenceMatcher(None, ref_chars, ocr_chars, autojunk=False)
    votes: dict[int, dict[int, int]] = {}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            weight = 2 if tag == "equal" else 1
            for offset in range(i2 - i1):
                ref_word, ocr_word = ref_owner[i1 + offset], ocr_owner[j1 + offset]
                if ref_word < 0 or ocr_word < 0:
                    continue
                votes.setdefault(ref_word, {}).setdefault(ocr_word, 0)
                votes[ref_word][ocr_word] += weight
    best: dict[int, int] = {}
    claimed: dict[int, list[int]] = {}
    for ref_word, counts in votes.items():
        ocr_word, score = max(counts.items(), key=lambda item: (item[1], -item[0]))
        if score < max(2, len(reference[ref_word])):  # at least half the word, counting equal chars double
            continue
        best[ref_word] = ocr_word
        claimed.setdefault(ocr_word, []).append(ref_word)
    return sorted((ref, ocr_word) for ref, ocr_word in best.items() if len(claimed[ocr_word]) == 1)


def _flatten(words: Sequence[str]) -> tuple[str, list[int]]:
    chars: list[str] = []
    owner: list[int] = []
    for index, word in enumerate(words):
        if index:
            chars.append(" ")
            owner.append(-1)
        for char in word:
            chars.append(char)
            owner.append(index)
    return "".join(chars), owner


# --------------------------------------------------------------------------------------------------------------
# Images


def load_gray(path: Path):
    numpy, _ = _require_numeric()
    with Image.open(path) as image:
        return numpy.asarray(image.convert("L"), dtype=numpy.uint8)


def sauvola(gray, *, window: int = 41, k: float = 0.2, r: float = 128.0):
    """Ink mask (``True`` = ink) by Sauvola's local threshold."""
    numpy, ndimage = _require_numeric()
    values = gray.astype(numpy.float64)
    mean = ndimage.uniform_filter(values, size=window)
    sq_mean = ndimage.uniform_filter(values * values, size=window)
    std = numpy.sqrt(numpy.maximum(sq_mean - mean * mean, 0.0))
    threshold = mean * (1.0 + k * (std / r - 1.0))
    return values < threshold


@dataclass
class Group:
    labels: list[int]
    box: tuple[int, int, int, int]  # x0, y0, x1, y1 (exclusive) in page pixels

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def _absorb(group: Group, other: Group) -> None:
    group.labels.extend(other.labels)
    group.box = (
        min(group.box[0], other.box[0]),
        min(group.box[1], other.box[1]),
        max(group.box[2], other.box[2]),
        max(group.box[3], other.box[3]),
    )


def word_groups(ink, box: tuple[int, int, int, int], *, min_area_frac: float = 0.004):
    """Merged connected components inside a word box, right to left. Returns ``(groups, labels, offset)``."""
    numpy, ndimage = _require_numeric()
    x0, y0, x1, y1 = box
    height = max(1, y1 - y0)
    pad_y, pad_x = int(height * 0.45), max(3, int(height * 0.15))
    cx0, cy0 = max(0, x0 - pad_x), max(0, y0 - pad_y)
    cx1, cy1 = min(ink.shape[1], x1 + pad_x), min(ink.shape[0], y1 + pad_y)
    crop = ink[cy0:cy1, cx0:cx1]
    labels, count = ndimage.label(crop, structure=numpy.ones((3, 3), dtype=bool))
    if count == 0:
        return [], labels, (cx0, cy0)
    slices = ndimage.find_objects(labels)
    areas = ndimage.sum_labels(numpy.ones_like(labels), labels, index=numpy.arange(1, count + 1))
    min_area = max(4.0, min_area_frac * height * height)
    groups: list[Group] = []
    minor: list[Group] = []  # specks and edge pieces: attached to a letter they overlap, never letters themselves
    for label, (sl, area) in enumerate(zip(slices, areas), start=1):
        if sl is None:
            continue
        gy0, gy1 = sl[0].start + cy0, sl[0].stop + cy0
        gx0, gx1 = sl[1].start + cx0, sl[1].stop + cx0
        if gy1 <= y0 or gy0 >= y1:  # entirely in a neighbouring line's band
            continue
        centre_x = (gx0 + gx1) / 2
        piece = Group([label], (gx0, gy0, gx1, gy1))
        if area < min_area or not (x0 <= centre_x <= x1):
            minor.append(piece)
        else:
            groups.append(piece)
    groups.sort(key=lambda group: group.box[0])
    merged: list[Group] = []
    for group in groups:
        if merged:
            last = merged[-1]
            overlap = min(last.box[2], group.box[2]) - max(last.box[0], group.box[0])
            if overlap > 0.5 * min(last.width, group.width):
                _absorb(last, group)
                continue
        merged.append(group)
    # A detached stroke (the left leg of ה, the foot of ג) that Sauvola broke into specks still belongs to its
    # letter: without it the mask would draw ה as ד.
    for piece in minor:
        best, best_overlap = None, 0
        for group in merged:
            overlap = min(group.box[2], piece.box[2]) - max(group.box[0], piece.box[0])
            if overlap > best_overlap:
                best, best_overlap = group, overlap
        if best is not None and best_overlap > 0.5 * piece.width and piece.box[1] < best.box[3] + 0.3 * height:
            _absorb(best, piece)
    merged.reverse()  # right to left
    return merged, labels, (cx0, cy0)


# --------------------------------------------------------------------------------------------------------------
# Candidates


@dataclass
class Candidate:
    style_id: str
    char: str
    page_id: str
    word_index: int
    position: int
    box: tuple[int, int, int, int]
    baseline: int
    x_height: float
    crop_box: tuple[int, int, int, int]
    crop: object  # numpy uint8 gray
    mask: object  # numpy bool
    feature: object = None
    score: float = 0.0


@dataclass
class PageStats:
    letter_gaps: list[int] = field(default_factory=list)
    word_gaps: list[int] = field(default_factory=list)
    line_pitches: list[float] = field(default_factory=list)
    line_widths: list[int] = field(default_factory=list)
    ink_gray: list[int] = field(default_factory=list)
    paper_gray: list[int] = field(default_factory=list)
    page_sizes: list[tuple[int, int]] = field(default_factory=list)
    paper_patches: list[object] = field(default_factory=list)


_PAGE_CACHE: dict = {}  # line units of one page arrive together; binarize the page once


def harvest_unit(unit: Unit, stats: PageStats, *, patch_size: int = 192, max_patches: int = 2) -> list[Candidate]:
    numpy, ndimage = _require_numeric()
    if _PAGE_CACHE.get("path") != unit.image_path:
        gray = load_gray(unit.image_path)
        _PAGE_CACHE.update(path=unit.image_path, gray=gray, ink=sauvola(gray))
    gray, ink = _PAGE_CACHE["gray"], _PAGE_CACHE["ink"]
    _collect_page_stats(gray, ink, unit.page_words or unit.ocr_words, stats, patch_size=patch_size, max_patches=max_patches)
    ref = reference_words(unit.reference_text)
    pairs = pair_words(ref, [word.text for word in unit.ocr_words])
    out: list[Candidate] = []
    for ref_index, ocr_index in pairs:
        word = ref[ref_index]
        if not harvestable_word(word):
            continue
        chars = visual_order(word)
        groups, labels, (ox, oy) = word_groups(ink, unit.ocr_words[ocr_index].box)
        if len(groups) != len(chars):
            continue
        heights = [g.height for g, c in zip(groups, chars) if c in X_HEIGHT_LETTERS]
        bottoms = [g.box[3] for g, c in zip(groups, chars) if c not in OFF_BASELINE and c not in PUNCTUATION]
        if len(bottoms) < 2 or not heights:
            continue
        baseline = int(statistics.median(bottoms))
        x_height = statistics.median(heights)
        if not _plausible(groups, chars, baseline, x_height):
            continue
        if not _complete(ink, labels, (ox, oy), groups):
            continue
        for gap_left, gap_right in zip(groups[1:], groups[:-1]):
            stats.letter_gaps.append(gap_right.box[0] - gap_left.box[2])
        for position, (group, char) in enumerate(zip(groups, chars)):
            pad = max(2, int(x_height * 0.25))
            bx0, by0, bx1, by1 = group.box
            cx0, cy0 = max(0, bx0 - pad), max(0, min(by0, baseline - int(x_height)) - pad)
            cx1, cy1 = min(gray.shape[1], bx1 + pad), min(gray.shape[0], max(by1, baseline) + pad)
            crop = gray[cy0:cy1, cx0:cx1].copy()
            mask = numpy.zeros(crop.shape, dtype=bool)
            ly0, lx0 = cy0 - oy, cx0 - ox
            window = labels[max(0, ly0) : ly0 + crop.shape[0], max(0, lx0) : lx0 + crop.shape[1]]
            sub = numpy.isin(window, group.labels)
            mask[max(0, -ly0) : max(0, -ly0) + sub.shape[0], max(0, -lx0) : max(0, -lx0) + sub.shape[1]] = sub
            out.append(
                Candidate(
                    style_id=unit.style_id,
                    char=char,
                    page_id=unit.page_id,
                    word_index=ref_index,
                    position=position,
                    box=group.box,
                    baseline=baseline - cy0,
                    x_height=float(x_height),
                    crop_box=(cx0, cy0, cx1, cy1),
                    crop=crop,
                    mask=mask,
                )
            )
    return out


def _complete(ink, labels, offset: tuple[int, int], groups: Sequence[Group], *, max_stray: float = 0.06) -> bool:
    """False when ink inside a glyph's box belongs to no glyph of the word (a stroke the grouping lost)."""
    numpy, _ = _require_numeric()
    ox, oy = offset
    assigned = numpy.isin(labels, [label for group in groups for label in group.labels])
    for group in groups:
        x0, y0, x1, y1 = group.box
        own = numpy.isin(labels[y0 - oy : y1 - oy, x0 - ox : x1 - ox], group.labels).sum()
        window = ink[y0:y1, x0:x1] & ~assigned[y0 - oy : y1 - oy, x0 - ox : x1 - ox]
        if window.sum() > max_stray * max(1, own):
            return False
    return True


def _plausible(groups: Sequence[Group], chars: Sequence[str], baseline: int, x_height: float) -> bool:
    for group, char in zip(groups, chars):
        if char in HEBREW_LETTERS:
            if group.height < 0.45 * x_height or group.height > 2.3 * x_height:
                if char not in "יו'":
                    return False
            if char in DESCENDERS and group.box[3] < baseline + 0.15 * x_height:
                return False
            if char not in DESCENDERS and char != "ל" and group.box[3] > baseline + 0.35 * x_height:
                return False
            if group.width > 2.2 * x_height:
                return False
        elif char in ".,":
            if group.height > 0.7 * x_height or group.width > 0.8 * x_height:
                return False
        elif char in ":;!?":
            # Two stacked marks; a broken colon whose dot is lost would be a period labelled ':'.
            if group.height < 0.45 * x_height:
                return False
    return True


def _collect_page_stats(gray, ink, words: Sequence[OcrWord], stats: PageStats, *, patch_size: int, max_patches: int):
    numpy, ndimage = _require_numeric()
    stats.page_sizes.append((gray.shape[1], gray.shape[0]))
    if ink.any():
        stats.ink_gray.append(int(numpy.median(gray[ink])))
    stats.paper_gray.append(int(numpy.median(gray[~ink])) if (~ink).any() else 255)
    lines: dict[tuple[int, int, int], list[OcrWord]] = {}
    for word in words:
        lines.setdefault(word.line_key, []).append(word)
    bottoms: list[tuple[int, int, int]] = []
    for line_words in lines.values():
        line_words.sort(key=lambda word: -word.box[2])
        for right, left in zip(line_words, line_words[1:]):
            gap = right.box[0] - left.box[2]
            if gap > 0:
                stats.word_gaps.append(gap)
        x0 = min(word.box[0] for word in line_words)
        x1 = max(word.box[2] for word in line_words)
        bottoms.append((int(statistics.median(word.box[3] for word in line_words)), x0, x1))
        stats.line_widths.append(x1 - x0)
    bottoms.sort()
    for (upper, ux0, ux1), (lower, lx0, lx1) in zip(bottoms, bottoms[1:]):
        if min(ux1, lx1) - max(ux0, lx0) > 0.3 * (ux1 - ux0):  # same column
            stats.line_pitches.append(lower - upper)
    if len(stats.paper_patches) >= 40:
        return
    found = 0
    step = patch_size // 2
    dilated = ndimage.binary_dilation(ink, iterations=3)
    integral = dilated.astype(numpy.int32).cumsum(0).cumsum(1)
    height, width = ink.shape
    for y in range(step, height - patch_size - step, step):
        for x in range(step, width - patch_size - step, step):
            total = (
                integral[y + patch_size, x + patch_size]
                - integral[y, x + patch_size]
                - integral[y + patch_size, x]
                + integral[y, x]
            )
            if total == 0:
                stats.paper_patches.append(gray[y : y + patch_size, x : x + patch_size].copy())
                found += 1
                if found >= max_patches:
                    return


# --------------------------------------------------------------------------------------------------------------
# Verification


def feature(candidate: Candidate, size: int = 24):
    numpy, _ = _require_numeric()
    ys, xs = numpy.nonzero(candidate.mask)
    if len(xs) == 0:
        return numpy.zeros(size * size + 3)
    sub = candidate.mask[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
    h, w = sub.shape
    side = max(h, w)
    canvas = numpy.zeros((side, side), dtype=numpy.uint8)
    canvas[(side - h) // 2 : (side - h) // 2 + h, (side - w) // 2 : (side - w) // 2 + w] = sub * 255
    small = numpy.asarray(Image.fromarray(canvas).resize((size, size), Image.Resampling.BILINEAR), dtype=numpy.float64)
    small /= 255.0
    vector = small.ravel()
    vector = (vector - vector.mean()) / (vector.std() + 1e-6)
    # Shape alone confuses ו/ן and ' / , ; size and seat relative to the baseline separate them.
    bottom = (ys.max() + 1 - candidate.baseline) / max(1.0, h)
    return numpy.concatenate([vector / numpy.sqrt(vector.size), [h / (w + 1.0) * 0.5, bottom, h / 40.0]])


def _two_means(features, iterations: int = 25):
    numpy, _ = _require_numeric()
    mean = features.mean(axis=0)
    first = features[numpy.argmax(((features - mean) ** 2).sum(axis=1))]
    second = features[numpy.argmax(((features - first) ** 2).sum(axis=1))]
    centres = numpy.stack([first, second])
    assign = numpy.zeros(len(features), dtype=int)
    for _ in range(iterations):
        assign = numpy.argmin(((features[:, None, :] - centres[None]) ** 2).sum(axis=2), axis=1)
        if assign.min() == assign.max():
            break
        centres = numpy.stack([features[assign == k].mean(axis=0) for k in range(2)])
    within = numpy.sqrt(((features - centres[assign]) ** 2).sum(axis=1)).mean()
    separation = float(numpy.linalg.norm(centres[0] - centres[1]) / (within + 1e-6))
    return assign, separation


def split_faces(
    candidates: list[Candidate], *, min_char: int = 30, min_separation: float = 1.3, min_share: float = 0.12, min_face: int = 300,
    min_purity: float = 0.75,
) -> list[list[Candidate]]:
    """Split one style's glyphs into typefaces (for example square and Rashi script) that never share a line.

    Each letter with enough glyphs is split in two by shape. Glyphs from the same word share a face, so word
    co-occurrence tells which cluster of one letter goes with which cluster of another. Every glyph then takes
    its word's majority face. Returns one list per face; a single list when the style has one face.
    """
    numpy, _ = _require_numeric()
    for candidate in candidates:
        if candidate.feature is None:
            candidate.feature = feature(candidate)
    by_char: dict[str, list[int]] = {}
    for index, candidate in enumerate(candidates):
        by_char.setdefault(candidate.char, []).append(index)
    clusters: dict[str, tuple[object, float]] = {}
    for char, indices in by_char.items():
        if char not in HEBREW_LETTERS or len(indices) < min_char:
            continue
        assign, separation = _two_means(numpy.stack([candidates[i].feature[:-3] for i in indices]))
        share = min(assign.mean(), 1 - assign.mean())
        if separation >= min_separation and share >= min_share:
            clusters[char] = (assign, separation)
    if not clusters:
        return [candidates]
    glyph_cluster: dict[int, tuple[str, int]] = {}
    for char, (assign, _) in clusters.items():
        for index, k in zip(by_char[char], assign):
            glyph_cluster[index] = (char, int(k))
    words: dict[tuple[str, int], list[int]] = {}
    for index, candidate in enumerate(candidates):
        words.setdefault((candidate.page_id, candidate.word_index), []).append(index)
    seed = max(clusters, key=lambda char: clusters[char][1])
    face_of: dict[tuple[str, int], int] = {(seed, 0): 0, (seed, 1): 1}
    pending = set(clusters) - {seed}
    while pending:
        best = None
        for char in pending:
            votes = numpy.zeros((2, 2))
            for members in words.values():
                faces = [face_of[glyph_cluster[i]] for i in members if i in glyph_cluster and glyph_cluster[i] in face_of]
                if not faces:
                    continue
                for i in members:
                    if i in glyph_cluster and glyph_cluster[i][0] == char:
                        for face in faces:
                            votes[glyph_cluster[i][1], face] += 1
            if best is None or votes.sum() > best[1].sum():
                best = (char, votes)
        char, votes = best
        pending.discard(char)
        if votes.sum() == 0:
            continue
        mapping = votes.argmax(axis=1)
        if mapping[0] != mapping[1]:
            face_of[(char, 0)], face_of[(char, 1)] = int(mapping[0]), int(mapping[1])
    faces: list[list[Candidate]] = [[], []]
    consistent = judged = 0
    for members in words.values():
        votes = [face_of[glyph_cluster[i]] for i in members if i in glyph_cluster and glyph_cluster[i] in face_of]
        if not votes:
            continue  # a word with no face evidence cannot be placed in either face
        face = int(round(sum(votes) / len(votes)))
        if len(votes) >= 2:
            judged += 1
            consistent += votes.count(face) == len(votes)
        if votes.count(face) < 0.75 * len(votes):
            continue  # mixed evidence: drop the word rather than guess
        faces[face].extend(candidates[i] for i in members)
    # Within one face the two shape clusters are just variation, and a word's votes disagree at random.
    if judged == 0 or consistent / judged < min_purity:
        return [candidates]
    faces = [face for face in faces if len(face) >= min_face]
    return faces or [candidates]


def verify_style(candidates: list[Candidate], *, rounds: int = 2, min_per_char: int = 3, margin: float = 0.02) -> list[Candidate]:
    """Keep glyphs whose own label wins a nearest-centroid vote among the style's glyphs."""
    numpy, _ = _require_numeric()
    for candidate in candidates:
        candidate.feature = feature(candidate)
    kept = candidates
    for _ in range(rounds):
        by_char: dict[str, list[Candidate]] = {}
        for candidate in kept:
            by_char.setdefault(candidate.char, []).append(candidate)
        chars = sorted(char for char, items in by_char.items() if len(items) >= min_per_char)
        if not chars:
            return []
        centroids = numpy.stack([numpy.median(numpy.stack([c.feature for c in by_char[char]]), axis=0) for char in chars])
        index = {char: i for i, char in enumerate(chars)}
        survivors: list[Candidate] = []
        for candidate in kept:
            if candidate.char not in index:
                continue
            distances = numpy.linalg.norm(centroids - candidate.feature, axis=1)
            own = distances[index[candidate.char]]
            distances[index[candidate.char]] = numpy.inf
            other = distances.min() if len(chars) > 1 else own + 1.0
            if own + margin < other:
                candidate.score = float(min(1.0, (other - own) / (other + 1e-6)))
                survivors.append(candidate)
        kept = survivors
    return kept


# --------------------------------------------------------------------------------------------------------------
# Bank writer


def _percentiles(values: Sequence[float]) -> list[float]:
    if not values:
        return [0.0, 0.0, 0.0]
    ordered = sorted(values)

    def at(q: float) -> float:
        return float(ordered[min(len(ordered) - 1, int(q * (len(ordered) - 1)))])

    return [at(0.1), at(0.5), at(0.9)]


def _png_bytes(array, mode: str) -> bytes:
    import io

    buffer = io.BytesIO()
    Image.fromarray(array).convert(mode).save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def implausible_double_marks(
    marks: Sequence[tuple[str, float, float, int]],
    *,
    min_single_ratio: float = 1.2,
    min_x_height_ratio: float = 0.33,
    min_singles: int = 5,
) -> set[int]:
    """Indices of ``"``/``״`` glyphs too narrow to hold two ticks.

    ``marks`` are one style's ``(char, ink_width, x_height, major_parts)``. Books that print single
    quotation marks under a ``"`` transcription label one tick as a double mark; a double mark must
    have two major parts, or be at least ``min_single_ratio`` times the style's median single-tick
    width (``min_x_height_ratio`` of the x-height when the style has fewer than ``min_singles`` ticks).
    """

    singles = [width / x_height for char, width, x_height, _ in marks if char in SINGLE_MARKS and x_height > 0]
    floor = (
        min_single_ratio * statistics.median(singles) if len(singles) >= min_singles else min_x_height_ratio
    )
    return {
        index
        for index, (char, width, x_height, parts) in enumerate(marks)
        if char in DOUBLE_MARKS and parts < 2 and (x_height <= 0 or width / x_height < floor)
    }


def _major_parts(mask, ndimage) -> int:
    labels, count = ndimage.label(mask)
    if count < 2:
        return count
    sizes = ndimage.sum(mask, labels, range(1, count + 1))
    return int(sum(1 for size in sizes if size >= 0.25 * max(sizes)))


def write_bank(
    output: Path,
    *,
    bank_id: str,
    config: dict,
    sources: list[dict],
    exclusions: list[str],
    styles: Sequence[StyleSource],
    glyphs_by_style: dict[str, list[Candidate]],
    stats_by_style: dict[str, PageStats],
    max_per_char: int = 400,
    min_style_glyphs: int = 500,
) -> dict:
    numpy, ndimage = _require_numeric()
    output.mkdir(parents=True, exist_ok=True)
    style_entries = []
    glyph_lines: list[str] = []
    for style in styles:
        glyphs = glyphs_by_style.get(style.style_id, [])
        marks = [g for g in glyphs if g.char in DOUBLE_MARKS | SINGLE_MARKS]
        widths = [numpy.nonzero(g.mask.any(axis=0))[0] for g in marks]
        drop = implausible_double_marks(
            [
                (g.char, float(w.max() - w.min() + 1) if w.size else 0.0, g.x_height, _major_parts(g.mask, ndimage))
                for g, w in zip(marks, widths)
            ]
        )
        dropped = {id(marks[index]) for index in drop}
        glyphs = [g for g in glyphs if id(g) not in dropped]
        stats = stats_by_style.get(style.style_id, PageStats())
        heights = [g.x_height for g in glyphs if g.char in X_HEIGHT_LETTERS]
        if len(glyphs) < min_style_glyphs or not heights or not stats.line_pitches:
            continue  # too little evidence for a usable typeface or its page metrics
        root = output / "styles" / style.style_id
        (root / "glyphs").mkdir(parents=True, exist_ok=True)
        (root / "paper").mkdir(parents=True, exist_ok=True)
        by_char: dict[str, list[Candidate]] = {}
        for glyph in glyphs:
            by_char.setdefault(glyph.char, []).append(glyph)
        written = 0
        heights = []
        for char in sorted(by_char):
            items = sorted(by_char[char], key=lambda g: (-g.score, g.page_id, g.word_index, g.position))[:max_per_char]
            for glyph in items:
                glyph_id = f"{style.style_id}-{written:06d}"
                asset = f"styles/{style.style_id}/glyphs/{glyph_id}.png"
                mask = f"styles/{style.style_id}/glyphs/{glyph_id}.mask.png"
                (output / asset).write_bytes(_png_bytes(glyph.crop, "L"))
                (output / mask).write_bytes(_png_bytes(glyph.mask.astype(numpy.uint8) * 255, "L"))
                ys, xs = numpy.nonzero(glyph.mask)
                ink_box = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]
                if char in X_HEIGHT_LETTERS:
                    heights.append(ink_box[3] - ink_box[1])
                record = {
                    "glyph_id": glyph_id,
                    "style_id": style.style_id,
                    "char": char,
                    "asset_path": asset,
                    "mask_path": mask,
                    "size": [int(glyph.crop.shape[1]), int(glyph.crop.shape[0])],
                    "ink_box": ink_box,
                    "baseline_y": int(glyph.baseline),
                    "x_height_px": round(glyph.x_height, 1),
                    "source": {
                        "page_id": glyph.page_id,
                        "box_in_source": [int(v) for v in glyph.box],
                        "word_index": glyph.word_index,
                        "position_in_word": glyph.position,
                    },
                    "quality": {"method": "cc_word_alignment", "score": round(glyph.score, 4)},
                }
                glyph_lines.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
                written += 1
        patches = []
        for index, patch in enumerate(stats.paper_patches[:12]):
            path = f"styles/{style.style_id}/paper/p{index:03d}.png"
            (output / path).write_bytes(_png_bytes(patch, "L"))
            patches.append(path)
        widths = sorted(stats.line_widths)
        full_width = widths[int(0.75 * (len(widths) - 1))] if widths else 0
        sizes = stats.page_sizes or [(0, 0)]
        style_entries.append(
            {
                "style_id": style.style_id,
                "source_id": style.source_id,
                "work_id": style.work_id,
                "licence": style.licence,
                "attribution": style.attribution,
                "born_digital": style.born_digital,
                "work_match_key": style.match_key,
                "metrics": {
                    "x_height_px": float(statistics.median(heights)) if heights else 0.0,
                    "line_pitch_px": float(statistics.median(stats.line_pitches)) if stats.line_pitches else 0.0,
                    "letter_gap_px": _percentiles([g for g in stats.letter_gaps if g > -5]),
                    "word_gap_px": _percentiles(stats.word_gaps),
                    "text_block_width_px": int(full_width),
                    "page_size_px": [int(statistics.median(s[0] for s in sizes)), int(statistics.median(s[1] for s in sizes))],
                    "ink_gray": int(statistics.median(stats.ink_gray)) if stats.ink_gray else 40,
                    "paper_gray": int(statistics.median(stats.paper_gray)) if stats.paper_gray else 230,
                },
                "paper_patches": patches,
                "glyph_count": written,
                "char_counts": {char: min(len(items), max_per_char) for char, items in sorted(by_char.items())},
            }
        )
    glyph_bytes = ("\n".join(glyph_lines) + "\n").encode("utf-8") if glyph_lines else b""
    (output / "glyphs.jsonl").write_bytes(glyph_bytes)
    index = {
        "schema": BANK_SCHEMA,
        "bank_id": bank_id,
        "created_by": {
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        },
        "glyph_count": len(glyph_lines),
        "glyphs_sha256": hashlib.sha256(glyph_bytes).hexdigest(),
        "sources": sources,
        "exclusions": exclusions,
        "styles": style_entries,
    }
    (output / "printed_glyph_bank.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


# --------------------------------------------------------------------------------------------------------------
# Source adapters


ACCEPTED_SCAN_BASES = frozenset({"faithful_reproduction_of_pd_work"})
ACCEPTED_OPEN_LICENCES = {"CC0-1.0": "CC0-1.0", "CC-BY-4.0": "CC-BY-4.0"}


def wikisource_units(
    snapshot: Path,
    *,
    split_manifest: Path,
    ocr_cache: Path,
    renders: Path,
    excluded_items: set[str],
) -> tuple[list[StyleSource], Iterator[Unit]]:
    """Train-split Wikisource proofread pages with a 1920 px render and a cached Tesseract TSV."""
    splits = {item["item_id"]: item["split"] for item in json.loads(split_manifest.read_text(encoding="utf-8"))["items"]}
    indexes = {entry["index_key"]: entry for entry in json.loads((snapshot / "indexes.json").read_text(encoding="utf-8"))["indexes"]}
    styles: dict[str, StyleSource] = {}
    pages = [json.loads(line) for line in (snapshot / "pages.jsonl").read_text(encoding="utf-8").splitlines() if line]
    selected = []
    for page in pages:
        slug = page["source_item_id"]
        if splits.get(f"wikisource_he_proofread:{slug}") != "train" or slug in excluded_items:
            continue
        index = indexes.get(page["index_key"])
        if index is None:
            continue
        rights = index["scan_rights"]
        if rights.get("basis") in ACCEPTED_SCAN_BASES:
            licence = "PD"
        elif rights.get("licence") in ACCEPTED_OPEN_LICENCES:
            licence = ACCEPTED_OPEN_LICENCES[rights["licence"]]
        else:
            continue
        render = renders / f"{slug}.jpg"
        tsv = ocr_cache / f"{page['image']['sha256']}.heb.psm3.x2.tsv"
        if not render.exists() or not tsv.exists():
            continue
        style_id = f"ws-{index['index_page_id']}"
        styles.setdefault(
            style_id,
            StyleSource(
                style_id=style_id,
                source_id="wikisource_he_proofread",
                work_id=page["index_key"],
                licence=licence,
                attribution=None if licence == "PD" else f"Wikimedia Commons, {index['commons_file']['title']}",
                match_key=f"commons_file:{index['commons_file']['sha1']}",
            ),
        )
        selected.append((style_id, slug, render, tsv, snapshot / page["text_path"]))

    def generate() -> Iterator[Unit]:
        for style_id, slug, render, tsv, text_path in selected:
            with Image.open(render) as image:
                width = image.width
            yield Unit(
                style_id=style_id,
                page_id=f"wikisource_he_proofread:{slug}",
                image_path=render,
                reference_text=text_path.read_text(encoding="utf-8"),
                ocr_words=read_tesseract_tsv(tsv, target_width=width),
            )

    return list(styles.values()), generate()


def benyehuda_units(f8f_root: Path, *, min_line_score: float = 0.85) -> tuple[list[StyleSource], Iterator[Unit]]:
    """Ben-Yehuda lines aligned to NLI free-use scans (silver line text; boxes from the cached Tesseract TSVs)."""
    styles: dict[str, StyleSource] = {}
    selected = []
    for alignment_path in sorted((f8f_root / "out").glob("*/alignment.json")):
        alignment = json.loads(alignment_path.read_text(encoding="utf-8"))
        scan = alignment.get("scan") or {}
        if scan.get("license_slug") != "public-domain-free-use" or (scan.get("rights_decision") or {}).get("decision") != "accepted":
            continue
        record = scan["nli_record_id"]
        pby_id = alignment_path.parent.name
        text_path = f8f_root / "pby" / "txt" / f"m{pby_id}.txt"
        if not text_path.exists():
            continue
        style_id = f"nli-{record}"
        styles.setdefault(
            style_id,
            StyleSource(style_id=style_id, source_id="benyehuda_nli_free_use", work_id=record, licence="PD", match_key=f"nli_record:{record}"),
        )
        for page in alignment["pages"]:
            lines = [line for line in page.get("lines", []) if line.get("class") == "matched" and (line.get("score") or 0) >= min_line_score and line.get("pby_span")]
            if not lines:
                continue
            index = page["canvas_index"]
            image = f8f_root / "work" / record / "img" / f"c{index:04d}.jpg"
            tsv = f8f_root / "work" / record / "ocr" / f"c{index:04d}.tsv"
            if image.exists() and tsv.exists():
                # Line bboxes are canvas pixels (image px * canvas width / image width, as F8f scales its OCR);
                # the TSV word boxes are image pixels.
                with Image.open(image) as opened:
                    scale = page["canvas_size"][0] / opened.size[0]
                selected.append((style_id, record, index, image, tsv, text_path, lines, scale))

    def generate() -> Iterator[Unit]:
        cache: dict[Path, str] = {}
        for style_id, record, index, image, tsv, text_path, lines, scale in selected:
            text = cache.setdefault(text_path, unicodedata.normalize("NFC", text_path.read_text(encoding="utf-8")))
            words = read_tesseract_tsv(tsv)
            for line in lines:
                x, y, w, h = (value / scale for value in line["bbox"])
                inside = [word for word in words if x - 2 <= (word.box[0] + word.box[2]) / 2 <= x + w + 2 and y - 2 <= (word.box[1] + word.box[3]) / 2 <= y + h + 2]
                start, end = line["pby_span"]
                yield Unit(
                    style_id=style_id,
                    page_id=f"benyehuda_nli:{record}:c{index:04d}:l{line['line']}",
                    image_path=image,
                    reference_text=text[start:end],
                    ocr_words=sorted(inside, key=lambda word: -word.box[2]),
                    page_words=words,
                )

    return list(styles.values()), generate()


# --------------------------------------------------------------------------------------------------------------
# CLI


def harvest(units: Iterable[Unit], *, progress_every: int = 50) -> tuple[dict[str, list[Candidate]], dict[str, PageStats], dict]:
    candidates: dict[str, list[Candidate]] = {}
    stats: dict[str, PageStats] = {}
    counts = {"units": 0, "candidates": 0}
    images: dict[Path, bool] = {}
    for unit in units:
        style_stats = stats.setdefault(unit.style_id, PageStats())
        # Line units share a page image; count page statistics once per image.
        page_stats = style_stats if unit.image_path not in images else PageStats()
        images[unit.image_path] = True
        found = harvest_unit(unit, page_stats)
        candidates.setdefault(unit.style_id, []).extend(found)
        counts["units"] += 1
        counts["candidates"] += len(found)
        if progress_every and counts["units"] % progress_every == 0:
            print(json.dumps({"progress": counts}), flush=True)
    return candidates, stats, counts


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bank-id", required=True)
    parser.add_argument("--wikisource-snapshot", type=Path)
    parser.add_argument("--split-manifest", type=Path)
    parser.add_argument("--ocr-cache", type=Path)
    parser.add_argument("--renders", type=Path, help="1920 px page renders named <source_item_id>.jpg")
    parser.add_argument("--exclude-items-from", type=Path, action="append", default=[], help="file whose text holds source_item_id values to exclude (e.g. a reference manifest)")
    parser.add_argument("--benyehuda-root", type=Path)
    parser.add_argument("--limit-units", type=int)
    parser.add_argument("--max-per-char", type=int, default=400)
    args = parser.parse_args(argv)

    excluded: set[str] = set()
    for path in args.exclude_items_from:
        excluded |= set(re.findall(r'"source_item_id": "([^"]+)"', path.read_text(encoding="utf-8")))
    styles: list[StyleSource] = []
    unit_iters: list[Iterator[Unit]] = []
    sources: list[dict] = []
    if args.wikisource_snapshot:
        if not (args.split_manifest and args.ocr_cache and args.renders):
            raise StageExecutionError("--wikisource-snapshot needs --split-manifest, --ocr-cache and --renders")
        found, units = wikisource_units(args.wikisource_snapshot, split_manifest=args.split_manifest, ocr_cache=args.ocr_cache, renders=args.renders, excluded_items=excluded)
        styles += found
        unit_iters.append(units)
        sources.append({"source_id": "wikisource_he_proofread", "licence": "PD scans (Commons PD-old); labels from proofread text", "notes": "train split only"})
    if args.benyehuda_root:
        found, units = benyehuda_units(args.benyehuda_root)
        styles += found
        unit_iters.append(units)
        sources.append({"source_id": "benyehuda_nli_free_use", "licence": "PD (NLI public-domain-free-use scans; PBY public-domain text)", "notes": "silver line alignment"})

    def chained() -> Iterator[Unit]:
        produced = 0
        for units in unit_iters:
            for unit in units:
                if args.limit_units is not None and produced >= args.limit_units:
                    return
                produced += 1
                yield unit

    candidates, stats, counts = harvest(chained())
    verified: dict[str, list[Candidate]] = {}
    style_by_id = {style.style_id: style for style in styles}
    final_styles: list[StyleSource] = []
    for style_id, items in sorted(candidates.items()):
        faces = split_faces(items)
        for face_index, face in enumerate(faces):
            sub_id = style_id if len(faces) == 1 else f"{style_id}-f{face_index}"
            for candidate in face:
                candidate.style_id = sub_id
            verified[sub_id] = verify_style(face)
            base = style_by_id[style_id]
            final_styles.append(StyleSource(sub_id, base.source_id, base.work_id, base.licence, base.attribution, base.born_digital, base.match_key))
            stats[sub_id] = stats[style_id]
    styles = final_styles
    counts["faces_split"] = sum(1 for s in styles if "-f" in s.style_id)
    counts["verified"] = sum(len(items) for items in verified.values())
    config = {
        "tool_version": TOOL_VERSION,
        "excluded_items": sorted(excluded),
        "limit_units": args.limit_units,
        "max_per_char": args.max_per_char,
        "sources": [s["source_id"] for s in sources],
    }
    index = write_bank(
        args.output,
        bank_id=args.bank_id,
        config=config,
        sources=sources,
        exclusions=[
            "Wikisource pages outside the release train split (size_aware_group_split.v2)",
            "the scored reference pages listed in --exclude-items-from",
            "restricted evaluation sets (never read)",
        ],
        styles=styles,
        glyphs_by_style=verified,
        stats_by_style=stats,
        max_per_char=args.max_per_char,
    )
    counts["written"] = index["glyph_count"]
    counts["styles"] = len(index["styles"])
    print(json.dumps({"summary": counts}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
