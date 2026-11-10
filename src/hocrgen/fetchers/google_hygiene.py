"""Google scan hygiene for Route B (2026-11-10 legal strategy, rule 5): front matter and watermark detection.

Google-digitized scans open with a usage-guidelines page ("This is a digital copy of a book that was preserved for
generations on library shelves…") and carry a "Digitized by Google" watermark at the foot of each page. Before any
crop, glyph or benchmark page, HeOCR drops the front page and crops the watermark, so nothing suggests a trademark
endorsement; the fact that Google digitized the scan stays in the metadata.

The functions here are pure. They read Tesseract TSV from an ``eng`` pass that the operator path of
``benyehuda_nli_alignment align`` runs on the first canvases (front matter) and on each page's foot band (watermark):

- ``detect_google_front_matter``: whether a page's eng OCR carries Google's usage-guidelines boilerplate.
- ``detect_google_watermark``: the box (canvas pixels) of the "Digitized by Google" line in a foot band's eng OCR.
- ``hygiene_record``: the ``scan.google_hygiene`` record that also fills ``rights_justification.hygiene``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from difflib import SequenceMatcher
from typing import Any

EXCLUDED_GOOGLE_FRONT_MATTER = "excluded_google_front_matter"
FRONT_MATTER_MAX_CANVASES = 3  # Google's front page is among the first 1-3 canvases
# The watermark sits at the very foot of the page. Bands are tried in this order until one finds it: a band that
# reaches into the body text makes the eng pass misread the whole band (a real Google page: 6-12% read the line,
# 15% did not).
FOOT_BAND_FRACTIONS = (0.10, 0.06, 0.15)
WATERMARK_PAD_FRACTION = 0.25  # of the watermark line's height, on every side
HYGIENE_FORMAT = "hocrgen.google_hygiene.v1"
FRONT_MATTER_METHOD = "tesseract -l eng --psm 3 on the first canvases; Google usage-guidelines boilerplate phrases"
WATERMARK_METHOD = (
    "tesseract -l eng --psm 6 on the bottom band of each page (" + ", then ".join(f"{f:.0%}" for f in FOOT_BAND_FRACTIONS)
    + " until found); 'Digitized by Google' line"
)

# Boilerplate phrases of Google's front page (English, with the German and French versions some library copies carry).
OPENING_PHRASES = (
    "This is a digital copy of a book that was preserved for generations on library shelves",
    "Dies ist ein digitales Exemplar eines Buches, das seit Generationen in den Regalen der Bibliotheken aufbewahrt wurde",
    "Ceci est une copie numérique d'un ouvrage conservé depuis des générations dans les rayonnages d'une bibliothèque",
)
SUPPORTING_PHRASES = (
    "before it was carefully scanned by Google as part of a project",
    "Usage guidelines",
    "Google is proud to partner with libraries to digitize public domain materials",
    "We also ask that you",
    "Make non-commercial use of the files",
    "Refrain from automated querying",
    "Maintain attribution",
    "About Google Book Search",
    "Nutzungsrichtlinien",
    "Google ist stolz, mit Bibliotheken in partnerschaftlicher Zusammenarbeit",
    "Consignes d'utilisation",
)
MIN_SUPPORTING_PHRASES = 2


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", text.lower().replace("é", "e").replace("è", "e"))


def tsv_words(tsv: str) -> list[dict[str, Any]]:
    """Word rows (level 5) of a Tesseract TSV: text, confidence, box (image pixels) and line key."""

    words = []
    for row in tsv.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        words.append({
            "text": cols[11].strip(),
            "conf": float(cols[10]),
            "box": (int(cols[6]), int(cols[7]), int(cols[8]), int(cols[9])),
            "line": (int(cols[2]), int(cols[3]), int(cols[4])),
        })
    return words


def front_matter_phrases(tsv: str) -> list[str]:
    """The boilerplate phrases found in a page's eng OCR (compared letters only, so word splits do not matter)."""

    page = _letters(" ".join(word["text"] for word in tsv_words(tsv)))
    return [phrase for phrase in (*OPENING_PHRASES, *SUPPORTING_PHRASES) if _letters(phrase) in page]


def detect_google_front_matter(tsv: str) -> tuple[bool, list[str]]:
    """A page is Google's front matter when its OCR has an opening sentence or at least two supporting phrases."""

    found = front_matter_phrases(tsv)
    opening = any(phrase in OPENING_PHRASES for phrase in found)
    supporting = sum(phrase in SUPPORTING_PHRASES for phrase in found)
    return opening or supporting >= MIN_SUPPORTING_PHRASES, found


def _like(word: str, target: str, threshold: float) -> bool:
    clean = re.sub(r"[^a-z]", "", word.lower())
    return bool(clean) and SequenceMatcher(None, clean, target).ratio() >= threshold


def foot_band_box(image_size: tuple[int, int], fraction: float = FOOT_BAND_FRACTIONS[0]) -> tuple[int, int, int, int]:
    """The bottom ``fraction`` of an image, as a PIL crop box (left, top, right, bottom)."""

    width, height = image_size
    return 0, int(round(height * (1 - fraction))), width, height


def detect_google_watermark(tsv: str, *, band_top: int, scale: float) -> list[int] | None:
    """The canvas-pixel box ``[x, y, w, h]`` of the "Digitized by Google" line in a foot band's eng OCR, or None.

    ``band_top`` is the band's top in image pixels and ``scale`` is canvas width / image width. The line is found
    by a word like "Digitized" (the logo itself often reads as noise) or, failing that, a word like "Google"; the box
    covers that word to the end of its OCR line, padded by a quarter of its height.
    """

    words = tsv_words(tsv)
    lines: dict[tuple[int, int, int], list[dict[str, Any]]] = {}
    for word in words:
        lines.setdefault(word["line"], []).append(word)
    for target, threshold in (("digitized", 0.75), ("google", 0.8)):
        for line_words in lines.values():
            ordered = sorted(line_words, key=lambda w: w["box"][0])
            hits = [i for i, w in enumerate(ordered) if _like(w["text"], target, threshold)]
            if not hits:
                continue
            start = hits[0] if target == "digitized" else max(0, hits[0] - 2)
            boxes = [w["box"] for w in ordered[start:]]
            x0 = min(b[0] for b in boxes)
            y0 = min(b[1] for b in boxes)
            x1 = max(b[0] + b[2] for b in boxes)
            y1 = max(b[1] + b[3] for b in boxes)
            pad = (y1 - y0) * WATERMARK_PAD_FRACTION
            x0, y0, x1, y1 = x0 - pad, y0 - pad + band_top, x1 + pad, y1 + pad + band_top
            return [round(max(0.0, x0) * scale), round(max(0.0, y0) * scale), round((x1 - max(0.0, x0)) * scale),
                    round((y1 - max(0.0, y0)) * scale)]
    return None


def boxes_overlap(a: Sequence[float], b: Sequence[float]) -> bool:
    """Whether two ``[x, y, w, h]`` boxes intersect."""

    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def hygiene_record(
    excluded: Iterable[Mapping[str, Any]],
    watermarks: Mapping[int, Sequence[int] | None],
) -> dict[str, Any]:
    """``scan.google_hygiene``: the excluded front-matter canvases and the watermark box found on each page."""

    return {
        "format": HYGIENE_FORMAT,
        "excluded_front_matter": [dict(item) for item in excluded],
        "watermark_boxes": [{"canvas_index": index, "google_watermark_bbox": list(box)}
                            for index, box in sorted(watermarks.items()) if box is not None],
        "pages_without_watermark": sorted(index for index, box in watermarks.items() if box is None),
        "method": {"front_matter": FRONT_MATTER_METHOD, "watermark": WATERMARK_METHOD},
    }
