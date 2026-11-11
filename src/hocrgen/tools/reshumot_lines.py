"""Printed-modern training lines from born-digital Reshumot booklets (decision 0018, operator tool).

Subcommands:

- ``build`` cuts one image per verified line from the 150 dpi renders of a tranche's Reshumot snapshot
  (``sources/reshumot_born_digital/snapshot``) and labels it with the **publisher's glyph-layer text** of that line
  (``pdf_glyph_geometry_logical.v1``, F8e2 / F8e3). The output has the shape of ``bynli_lines_v2``
  (``{train,dev}/<booklet>/<id>.png`` with a ``.gt.txt`` each, ``manifest.jsonl`` and ``summary.json``), so the
  Tesseract tooling that reads that set reads this one unchanged. It also writes ``tagger_units.json``.
- ``verify`` checks a built set: no row from an eval or unassigned unit (the decision 0017 guard, run again on the
  manifest), every row's provenance and licence fields, labels without niqqud or private-use code points, dev and
  train disjoint by booklet, and image and label files matching the manifest.

The glyph layer is a **silver training label, never an evaluation reference** (``label_source:
publisher_glyph_layer``, ``reference_eligible: false``), and only for truly born-digital PDFs. The guards, all fail
closed:

1. **Eval reserve (decision 0017).** Booklets are read only when the unit registry
   (``config/eval_reserved_units.yaml``) lists them ``non_eval``. Eval and unassigned booklets are counted from
   ``entries.jsonl`` metadata and never opened. ``refuse_eval_reserved_training_input`` then runs on the selected
   pages before anything is read, and on the line rows before anything is written.
2. **Born digital (per booklet).** The booklet's cached PDF must match the sha256 every entry pins, and
   ``born_digital_check`` must pass on its metadata (``pdfinfo``, XMP, ``pdffonts``, ``pdfimages -list``) and on the
   glyph layer of **every** PDF page. A booklet is refused when a Creator, Producer, XMP tool or history agent names
   OCR or scanning software (``OCR_SOFTWARE``); when a page has text in an invisible render mode (3 or 7) over a page
   image covering ``SCAN_IMAGE_SHARE`` of the page; when a page has invisible text and no visible text (an image-only
   page under an OCR layer); when a page image covers ``FULL_PAGE_IMAGE_SHARE`` of a page; when it has no embedded
   fonts; or when any page's glyph layer is missing. The result is recorded per booklet.
3. **Page gate.** Each page must pass the unchanged tranche gate (``reshumot_entry_exclusion_reasons``: section-6
   series, born-digital fields, checksums, the glyph-layer re-derivation and its crop). Its text is re-derived here
   (``convert_glyph_layer`` and ``page_verdict``) and must equal the committed text line for line.
4. **Glyphs.** A line with a private-use, replacement, unassigned or ``(cid:N)`` code point, or with a segment issue
   naming an unmapped, private-use or unverified glyph, is dropped (``unmapped_or_private_glyph``).
5. **Niqqud.** A line carrying any niqqud or cantillation mark is a pointed line and is dropped (``pointed``); the
   laws are unpointed, and the count checks it. Labels have niqqud stripped (a no-op on kept lines). Geresh,
   gershayim, maqaf and dashes are kept as printed; no other folds.
6. **Bidi and digit order.** heocr-eval's tier-A rules (vendored below from
   ``tasks/eval-domains/scripts/reshumot_candidates.py``) flag each line. A line flagged ``compound_number``,
   ``latin`` or ``bracket_order_or_balance`` is kept only when its order is verified **within the line**
   (``line_order_verified``): the entry records ``reading_order_verified: within_line``, every segment's logical text
   reproduces the glyphs' visual order under the forward bidi algorithm with no segment issue and no ambiguous
   Latin-number join, and, for a line of several segments (a label joined to its line), the whole line's logical text
   reproduces the segments' visual order too. Otherwise it is dropped (``bidi_or_digit_order_unverified``). The
   tier-A flags of every kept line are recorded on its row.

Lines: the kept units of the page verdict, in the committed text's order. The crop is the line's ink box (its text
and mark glyphs' outline boxes) padded by ``CROP_PAD_PT``; every pixel outside the line's own glyph boxes (padded by
``INK_GLYPH_PAD_PX``) is set to white (``crop_method: unit_glyph_ink_mask.v1``), so the image shows only the
labelled glyphs. A line whose glyph boxes touch another line's glyphs, a page image, a rule or a coloured fill is
dropped (``ink_overlaps_other_ink``). A line without a letter or digit is dropped (``no_letters_or_digits``).

Split: whole booklets. Dev is one booklet per (series, decade) stratum of the non-eval booklets: the first by
``sha256(unit_id)`` that passes the born-digital check and gives at least one line. Train is every other passing
booklet. ``--max-lines-per-booklet`` caps each booklet by sha256 of the line id. Every row carries
``proposed_node_hint: new_printed`` (a hint only; the maintainer's tagger decides the node) and
``tagger_units.json`` lists each booklet with two rendered page images.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from hocrgen.config.models import EvalReservedUnitsRegistry, EvalUnitStatus, SourceConfig
from hocrgen.fetchers.government_print import (
    RESHUMOT_READING_ORDER_VERIFIED,
    read_glyph_layer_bytes,
    reshumot_entry_exclusion_reasons,
    reshumot_page_render,
)
from hocrgen.parsers.pdf_geometry import (
    GLYPH_FLAG_INVISIBLE,
    Unit,
    convert_glyph_layer,
    page_verdict,
    unicode_bidi_display,
)
from hocrgen.split.eval_reserved import (
    RESHUMOT_SOURCE_ID,
    EvalReservedUnitError,
    packaged_registry,
    refuse_eval_reserved_training_input,
    registry_provenance,
    reshumot_unit_id,
    unit_status,
)

SCHEMA = "s16c_reshumot_lines.v1"
BUILDER = "reshumot_lines build"
LABEL_SOURCE = "publisher_glyph_layer"
CAPTURE = "rendered"
NODE_HINT = "new_printed"
NODE_HINT_NOTE = "a hint only (modern typography); the maintainer's tagger decides each booklet's node"
LICENSE = "PD-IL"
LICENSE_BASIS = "Copyright Act 2007 section 6: no copyright in laws and regulations (ספר החוקים, קובץ התקנות)"
ATTRIBUTION = "Reshumot (רשומות), the official gazette of the State of Israel"
CROP_METHOD = "unit_glyph_ink_mask.v1"
CROP_PAD_PT = 3.0
INK_GLYPH_PAD_PX = 1.5
DEFAULT_MAX_LINES = 6100
FULL_PAGE_IMAGE_SHARE = 0.8
SCAN_IMAGE_SHARE = 0.5
RELEASE_NOTICE = (
    "Line images rendered by HeOCR (pdftoppm, 150 dpi gray) from born-digital PDF booklets of ספר החוקים and "
    "קובץ התקנות published by Reshumot (רשומות), the official gazette of the State of Israel; the publisher URL of each "
    "booklet is in summary.json and on every row. Laws and regulations carry no copyright in Israel (Copyright Act "
    "2007 section 6, PD-IL); status outside Israel (including the US) is not separately asserted here. Labels are the "
    "publisher's PDF glyph-layer text, verified within each line against the render: silver training labels, never "
    "evaluation references. No line comes from a P-mod evaluation or unassigned booklet (decision 0017)."
)

# OCR and scanning software in a PDF's Creator / Producer / XMP tool fields: any match refuses the booklet.
OCR_SOFTWARE = re.compile(
    r"abbyy|fine\s*reader|tesseract|omni\s*page|paper\s*capture|clear\s*scan|ocrmypdf|\bocr|readiris|\biris\b|nuance|"
    r"scansoft|kofax|capture|luratech|pdf\s*compressor|scan|recogni[sz]", re.I)
XMP_TOOL = re.compile(r"(?:CreatorTool|Producer|softwareAgent)\s*(?:=\s*['\"]([^'\"]*)['\"]|>([^<]*)<)", re.I)

# --- heocr-eval tier-A rules (vendored) ---------------------------------------------------------------------------
# Vendored unchanged from heocr-eval's tasks/eval-domains/scripts/reshumot_candidates.py (TIER_A, bracket_problem;
# sha256 a0d42e9ed696100d6d4a9150447e9f9605292514e397c08a579648371f3d951b, 2026-11-11), so that train and eval flag the
# glyph-layer lines alike. Owner: eval[claude/claude-code#shay-macbook-m4]@heocr/opensource.
TIER_A_ORIGIN = {
    "path": "tasks/eval-domains/scripts/reshumot_candidates.py",
    "sha256": "a0d42e9ed696100d6d4a9150447e9f9605292514e397c08a579648371f3d951b",
    "owner": "heocr-eval",
}
TIER_A = {
    "pua_or_replacement": re.compile(r"[\ue000-\uf8ff\ufffd]"),
    "compound_number": re.compile(r"\d[.,/:\-]\d|\d+\s*\(|\)\s*\d"),   # dates, section refs: bidi order risk
    "latin": re.compile(r"[A-Za-z]"),
    "niqqud": re.compile(r"[\u0591-\u05c7]"),
    "dot_leader": re.compile(r"(?:\. ){3,}|\.{4,}"),
}


def bracket_problem(line: str) -> bool:
    depth = 0
    for ch in line:
        depth += ch == "("; depth -= ch == ")"  # noqa: E702 - vendored verbatim
        if depth < 0:
            return True
    return depth != 0


def tier_a_flags(line: str) -> list[str]:
    """The tier-A flags of heocr-eval's ``flags_for`` (its tier-B flags are spot checks and are not used here)."""

    flags = [name for name, rx in TIER_A.items() if rx.search(line)]
    if bracket_problem(line):
        flags.append("bracket_order_or_balance")
    return flags


# Tier-A flags that mark a bidi or digit-order risk (guard 6). ``pua_or_replacement`` is the glyph guard and
# ``niqqud`` the pointed guard; ``dot_leader`` is a table-of-contents layout flag, kept and recorded.
BIDI_FLAGS = frozenset({"compound_number", "latin", "bracket_order_or_balance"})
# --- end of vendored rules -----------------------------------------------------------------------------------------

# --- heocr-eval's word 6-gram rule (vendored) ----------------------------------------------------------------------
# From tasks/eval-domains/scripts/ngram_overlap.py (N, WORD, grams; sha256 pinned in NGRAM_ORIGIN): Hebrew-letter
# words in logical order; a line overlaps when it shares any word 6-gram with the pool. The pool (``--exclude-6grams``)
# holds only sha256 digests of the 6-grams of eval text (v1 eval booklets and wave-1 pages), built by heocr-eval's
# script, so no eval text reaches this tool or its output. Owner: heocr-eval.
NGRAM_ORIGIN = {
    "path": "tasks/eval-domains/scripts/ngram_overlap.py",
    "sha256": "e87e0a9d5c9df7251cf743b4c6a0a1ee89bdb3278a23f170eca120603de58550",
    "owner": "heocr-eval",
}
NGRAM_N = 6
NGRAM_WORD = re.compile(r"[א-ת]+")


def word_grams(text: str) -> set[tuple[str, ...]]:
    words = NGRAM_WORD.findall(text)
    return {tuple(words[i:i + NGRAM_N]) for i in range(len(words) - NGRAM_N + 1)}


def gram_digest(gram: Sequence[str]) -> str:
    """The pool's form of a 6-gram: sha256 of its words joined by one space."""

    return hashlib.sha256(" ".join(gram).encode("utf-8")).hexdigest()


def load_gram_pool(path: Path) -> dict[str, Any]:
    pool = json.loads(path.read_text(encoding="utf-8"))
    if pool.get("schema") != GRAM_POOL_SCHEMA or pool.get("n") != NGRAM_N or pool.get("digest") != "sha256":
        raise SystemExit(f"{path}: not a {GRAM_POOL_SCHEMA} pool of sha256 word {NGRAM_N}-grams")
    return pool


GRAM_POOL_SCHEMA = "heocr_eval_word_ngram_pool.v1"
DEFAULT_SHUFFLE_SEED = "reshumotlines-v2"

POINTS = re.compile("[\u0591-\u05bd\u05bf\u05c1\u05c2\u05c4\u05c5\u05c7]")  # niqqud + cantillation; keeps maqaf, paseq, sof pasuq
GLYPH_ISSUES = frozenset({"unmapped_glyph", "private_use_glyph", "glyph_identity_unverified"})
BRACKETS = str.maketrans({char: "|" for char in "()[]{}<>"})
ALNUM = re.compile(r"[א-תA-Za-z0-9]")


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def unit_slug(unit_id: str) -> str:
    return unit_id.split(":", 1)[1]


def entry_unit(entry: Mapping[str, Any]) -> str:
    booklet = entry["booklet"]
    return reshumot_unit_id(booklet["series"], booklet["booklet_number"])


def decade(publish_date: str) -> str:
    return f"{publish_date[:3]}0s"


def label(raw: str) -> str:
    """NFC, niqqud and cantillation removed, whitespace collapsed; geresh, gershayim, maqaf and dashes kept."""

    text = unicodedata.normalize("NFC", POINTS.sub("", unicodedata.normalize("NFD", raw)))
    return re.sub(r"\s+", " ", text).strip()


def bad_code_points(text: str) -> bool:
    return "(cid:" in text or any(char == "\ufffd" or unicodedata.category(char) in {"Co", "Cn", "Cs"} for char in text)


# --- born-digital check ------------------------------------------------------------------------------------------


def _share(box: Sequence[float], width: float, height: float) -> float:
    x0, y0, x1, y1 = max(0.0, box[0]), max(0.0, box[1]), min(width, box[2]), min(height, box[3])
    return max(0.0, x1 - x0) * max(0.0, y1 - y0) / (width * height) if width > 0 and height > 0 else 0.0


def page_layer_facts(layer: Mapping[str, Any]) -> dict[str, Any]:
    """What a page's glyph layer says about a scan: invisible and visible text glyphs, page images and their share."""

    width, height = float(layer["page"]["width"]), float(layer["page"]["height"])
    images = [list(image[1:5]) for image in layer.get("images") or []]
    shares = [_share(box, width, height) for box in images]
    big = [box for box, share in zip(images, shares) if share >= SCAN_IMAGE_SHARE]
    invisible = visible = invisible_over_image = 0
    for glyph in layer.get("glyphs") or []:
        text, flags = glyph[1], int(glyph[10])
        if not text.strip():
            continue
        if flags & GLYPH_FLAG_INVISIBLE:
            invisible += 1
            cx, cy = (glyph[2] + glyph[4]) / 2, (glyph[3] + glyph[5]) / 2
            if any(box[0] <= cx <= box[2] and box[1] <= cy <= box[3] for box in big):
                invisible_over_image += 1
        else:
            visible += 1
    return {"invisible_text_glyphs": invisible, "visible_text_glyphs": visible, "images": len(images),
            "max_image_share": round(max(shares, default=0.0), 4), "invisible_glyphs_over_page_image": invisible_over_image}


def pdfimages_share(row: Sequence[str], page_size: tuple[float, float]) -> float:
    """A ``pdfimages -list`` image row's area at its stated resolution, as a share of its page."""

    try:
        width, height, xppi, yppi = int(row[3]), int(row[4]), float(row[12]), float(row[13])
    except (IndexError, ValueError):
        return 0.0
    if xppi <= 0 or yppi <= 0:
        return 0.0
    return (width / xppi * 72.0) * (height / yppi * 72.0) / (page_size[0] * page_size[1])


def born_digital_check(facts: Mapping[str, Any]) -> dict[str, Any]:
    """Whether a booklet PDF is truly born digital (passed, reasons, evidence); fails closed.

    ``facts``: ``info`` (``pdfinfo`` fields), ``xmp`` (``pdfinfo -meta`` text), ``fonts`` (``pdffonts`` rows: name,
    type, encoding, emb, sub, uni, ...), ``image_rows`` (``pdfimages -list`` rows), ``page_count`` and ``pages``
    (page number to ``page_layer_facts`` and ``size``, or ``None`` when the page's glyph layer is missing).
    """

    reasons: set[str] = set()
    info = facts.get("info") or {}
    tools = {f"info.{key}": str(info.get(key) or "") for key in ("Creator", "Producer")}
    for index, match in enumerate(XMP_TOOL.finditer(str(facts.get("xmp") or ""))):
        tools[f"xmp.{index}"] = (match.group(1) or match.group(2) or "").strip()
    ocr_tools = sorted({value for value in tools.values() if value and OCR_SOFTWARE.search(value)})
    if ocr_tools:
        reasons.add("ocr_producer")
    fonts = facts.get("fonts") or []
    embedded = [row for row in fonts if len(row) >= 7 and row[-5] == "yes"]  # ... emb sub uni <object> <generation>
    if not embedded:
        reasons.add("no_embedded_fonts")
    page_count = int(facts.get("page_count") or 0)
    pages = facts.get("pages") or {}
    if page_count <= 0:
        reasons.add("page_count_unknown")
    per_page: dict[str, Any] = {}
    for number in range(1, page_count + 1):
        page = pages.get(number) or pages.get(str(number))
        if page is None:
            reasons.add("page_layer_missing")
            per_page[str(number)] = None
            continue
        layer = dict(page["layer"])
        size = page.get("size") or (1.0, 1.0)
        rows = [row for row in facts.get("image_rows") or [] if row and row[0] == str(number) and row[2] == "image"]
        image_share = max([layer["max_image_share"], *(pdfimages_share(row, size) for row in rows)])
        layer.update(max_image_share=round(image_share, 4), pdfimages=len(rows))
        if layer["invisible_glyphs_over_page_image"]:
            reasons.add("invisible_text_over_page_image")
        if layer["invisible_text_glyphs"] and not layer["visible_text_glyphs"]:
            reasons.add("image_only_page_under_invisible_text")
        if image_share >= FULL_PAGE_IMAGE_SHARE:
            reasons.add("full_page_image")
        per_page[str(number)] = layer
    present = [page for page in per_page.values() if page]
    evidence = {
        "creator": info.get("Creator"), "producer": info.get("Producer"),
        "xmp_tools": sorted({value for key, value in tools.items() if key.startswith("xmp.") and value}),
        "ocr_tools": ocr_tools, "embedded_fonts": sorted({row[0].split("+", 1)[-1] for row in embedded}),
        "fonts_without_unicode_map": sorted({row[0].split("+", 1)[-1] for row in embedded if row[-3] != "yes"}),
        "pages_checked": len(present), "page_count": page_count,
        "invisible_text_glyphs": sum(page["invisible_text_glyphs"] for page in present),
        "pages_with_images": sum(1 for page in present if page["images"] or page["pdfimages"]),
        "max_image_share": max((page["max_image_share"] for page in present), default=0.0),
    }
    return {"passed": not reasons, "reasons": sorted(reasons), "evidence": evidence,
            "thresholds": {"full_page_image_share": FULL_PAGE_IMAGE_SHARE, "scan_image_share": SCAN_IMAGE_SHARE}}


def _run(args: list[str]) -> str:  # pragma: no cover - poppler
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def pdf_facts(pdf: Path, layers: Mapping[int, Mapping[str, Any] | None]) -> dict[str, Any]:  # pragma: no cover - poppler
    """The booklet facts ``born_digital_check`` reads: poppler's metadata, fonts and image list, and the layers."""

    info: dict[str, str] = {}
    for line in _run(["pdfinfo", str(pdf)]).splitlines():
        key, _, value = line.partition(":")
        info[key.strip()] = value.strip()
    xmp = subprocess.run(["pdfinfo", "-meta", str(pdf)], capture_output=True, text=True).stdout
    fonts = [line.split() for line in _run(["pdffonts", str(pdf)]).splitlines()[2:] if line.strip()]
    image_rows = [line.split() for line in _run(["pdfimages", "-list", str(pdf)]).splitlines()[2:] if line.strip()]
    pages = {}
    for number, layer in layers.items():
        if layer is not None:
            pages[number] = {"layer": page_layer_facts(layer), "size": (float(layer["page"]["width"]), float(layer["page"]["height"]))}
    return {"info": info, "xmp": xmp, "fonts": fonts, "image_rows": image_rows, "page_count": int(info.get("Pages") or 0), "pages": pages}


def load_page_layers(layer_dir: Path | None, slug: str, page_count: int, pdf: Path) -> dict[int, dict[str, Any] | None]:
    """Every PDF page's glyph layer: ``<layer_dir>/<slug>__pNNNN.json[.gz]``, else extracted (needs pdfminer.six)."""

    layers: dict[int, dict[str, Any] | None] = {}
    for number in range(1, page_count + 1):
        layer = None
        for suffix in (".json", ".json.gz", ".glyphs.json.gz"):
            path = (layer_dir / f"{slug}__p{number:04d}{suffix}") if layer_dir else None
            if path is not None and path.is_file():
                layer = json.loads(read_glyph_layer_bytes(path) if path.suffix == ".gz" else path.read_bytes())
                break
        if layer is None:
            try:  # pragma: no cover - needs pdfminer.six
                from hocrgen.parsers.pdf_glyphs import extract_glyph_layer

                layer = extract_glyph_layer(pdf, number)
            except ImportError:
                layer = None
        layers[number] = layer
    return layers


# --- lines -------------------------------------------------------------------------------------------------------


def line_order_verified(unit: Unit, entry: Mapping[str, Any]) -> bool:
    """The line's order is verified within the line (guard 6): see the module docstring."""

    if (entry.get("text") or {}).get("reading_order_verified") != RESHUMOT_READING_ORDER_VERIFIED:
        return False
    if not unit.round_trip or unit.issues or unit.ambiguous_joins:
        return False
    if len(unit.segments) == 1:
        return True
    visual = " ".join(segment.visual.strip() for segment in sorted(unit.segments, key=lambda segment: segment.x0))
    shown = "".join(unicode_bidi_display(list(unit.text)))
    collapse = lambda text: re.sub(r"\s+", " ", text).strip().translate(BRACKETS)  # noqa: E731
    return collapse(shown) == collapse(visual)


def _ink_glyphs(unit: Unit) -> list[Any]:
    return [glyph for glyph in unit.glyphs if glyph.kind in ("text", "mark")]


def _hits(a: Sequence[float], b: Sequence[float]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _padded(box: Sequence[float], pad: float) -> list[float]:
    return [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad]


def foreign_ink(unit: Unit, others: Iterable[Unit], layer: Mapping[str, Any], scale: float, rotated: Iterable[Any] = ()) -> bool:
    """Whether another line's glyphs, a page image, a rule or a coloured fill touches this line's glyph boxes."""

    pad = INK_GLYPH_PAD_PX / scale
    own = [_padded(glyph.ink_box, pad) for glyph in _ink_glyphs(unit)]
    boxes = [glyph.ink_box for other in others if other is not unit for glyph in _ink_glyphs(other)]
    boxes += [list(row[1:5]) for row in layer.get("images") or []]
    boxes += [list(row[1:5]) for row in layer.get("strokes") or []]
    boxes += [list(row[1:5]) for row in layer.get("fills") or [] if row[5] != "white"]
    boxes += [[glyph.x0, glyph.top, glyph.x1, glyph.bottom] for glyph in rotated]
    return any(_hits(a, _padded(b, pad)) for a in own for b in boxes)


def crop_line(page: Image.Image, unit: Unit, scale: float) -> tuple[Image.Image, list[int], list[int]]:
    """The line image (white outside the line's own padded glyph boxes), its crop box and ink box in pixels."""

    glyphs = _ink_glyphs(unit)
    x0 = min(glyph.ink_box[0] for glyph in glyphs); y0 = min(glyph.ink_box[1] for glyph in glyphs)  # noqa: E702
    x1 = max(glyph.ink_box[2] for glyph in glyphs); y1 = max(glyph.ink_box[3] for glyph in glyphs)  # noqa: E702
    width, height = page.size
    box = [max(0, int((x0 - CROP_PAD_PT) * scale)), max(0, int((y0 - CROP_PAD_PT) * scale)),
           min(width, int((x1 + CROP_PAD_PT) * scale) + 1), min(height, int((y1 + CROP_PAD_PT) * scale) + 1)]
    crop = page.crop(tuple(box))
    mask = Image.new("L", crop.size, 0)
    draw = ImageDraw.Draw(mask)
    for glyph in glyphs:
        gx0, gy0, gx1, gy1 = glyph.ink_box
        draw.rectangle((gx0 * scale - INK_GLYPH_PAD_PX - box[0], gy0 * scale - INK_GLYPH_PAD_PX - box[1],
                        gx1 * scale + INK_GLYPH_PAD_PX - box[0], gy1 * scale + INK_GLYPH_PAD_PX - box[1]), fill=255)
    out = Image.composite(crop, Image.new("L", crop.size, 255), mask)
    ink = [round(x0 * scale), round(y0 * scale), round((x1 - x0) * scale), round((y1 - y0) * scale)]
    return out, box, ink


def page_lines(entry: Mapping[str, Any], root: Path, source: SourceConfig) -> tuple[list[dict[str, Any]], Counter, str | None]:
    """Candidate line rows of one admitted page, the drop counts, and the page's refusal reason (or None)."""

    drops: Counter = Counter()
    reasons = reshumot_entry_exclusion_reasons(dict(entry), source, root)
    if reasons:
        return [], drops, f"page_gate:{reasons[0]}"
    text = entry["text"]
    committed = [line for line in (root / text["local_path"]).read_text(encoding="utf-8").split("\n") if line]
    layer = json.loads(read_glyph_layer_bytes(root / text["extraction"]["raw_local_path"]))
    table = json.loads((root / text["extraction"]["outline_table_path"]).read_text(encoding="utf-8"))
    render = reshumot_page_render(entry) or {}
    rendering = render.get("rendering") or {}
    dpi = float(rendering.get("dpi") or 0)
    scale = dpi / 72.0
    with Image.open(root / render["local_path"]) as page:
        page.load()
        page = page.convert("L")
        conversion = convert_glyph_layer(layer, table)
        verdict = page_verdict(conversion, layer, page, dpi)
        kept = [unit for unit in verdict.kept if unit.text]
        if [unit.text for unit in kept] != committed:
            return [], drops, "text_not_reproducible"
        rows = []
        for index, unit in enumerate(kept):
            raw = unicodedata.normalize("NFC", unit.text)
            flags = tier_a_flags(raw)
            verified = line_order_verified(unit, entry)
            if bad_code_points(raw) or GLYPH_ISSUES & set(unit.issues) or "pua_or_replacement" in flags:
                drops["unmapped_or_private_glyph"] += 1
                continue
            if POINTS.search(unicodedata.normalize("NFD", raw)):
                drops["pointed"] += 1
                continue
            if BIDI_FLAGS & set(flags) and not verified:
                drops["bidi_or_digit_order_unverified"] += 1
                continue
            gt = label(raw)
            if not ALNUM.search(gt):
                drops["no_letters_or_digits"] += 1
                continue
            if foreign_ink(unit, conversion.units, layer, scale, conversion.visibility.rotated):
                drops["ink_overlaps_other_ink"] += 1
                continue
            _, crop_box, ink = crop_line(page, unit, scale)
            rows.append({
                "line_index": index, "text": gt, "tier_a_flags": flags, "line_order_verified": verified,
                "segments": len(unit.segments), "bbox_page_pt": [round(v, 2) for v in unit.box],
                "bbox_image": ink, "crop_box_image": crop_box, "image_scale": round(scale, 5),
            })
    return rows, drops, None


def _page_job(job: tuple[dict[str, Any], str, SourceConfig]) -> tuple[str, list[dict[str, Any]], Counter, str | None]:
    entry, root, source = job
    rows, drops, refused = page_lines(entry, Path(root), source)
    return entry["entry_id"], rows, drops, refused


def line_id(entry_id: str, index: int) -> str:
    return f"{entry_id}_l{index:03d}"


def cap_lines(ids: Sequence[str], cap: int) -> list[str]:
    """At most ``cap`` ids, chosen by sha256 of the id, in their original order."""

    if not cap or len(ids) <= cap:
        return list(ids)
    keep = set(sorted(ids, key=lambda value: sha256_bytes(value.encode()))[:cap])
    return [value for value in ids if value in keep]


def choose_dev(booklets: Mapping[str, Mapping[str, Any]], per_stratum: int = 1,
               pinned: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Dev booklets: per (series, decade), the first ``per_stratum`` by sha256(unit_id) that pass and give lines.

    ``pinned`` (an earlier build's picks, ``--keep-dev-from``) are kept first, when they still pass and give lines, so
    a later build that adds booklets keeps the earlier dev split; a stratum with fewer pinned picks is filled by the
    rule."""

    strata: dict[str, list[str]] = defaultdict(list)
    for unit, booklet in booklets.items():
        strata[f"{booklet['series']} {decade(booklet['publish_date'])}"].append(unit)
    picks, considered = {}, {}
    pinned = dict(pinned or {})
    for stratum in sorted(strata):
        ranked = sorted(strata[stratum], key=lambda unit: sha256_bytes(unit.encode()))
        considered[stratum] = ranked
        eligible = [unit for unit in ranked if booklets[unit]["born_digital"]["passed"] and booklets[unit]["candidate_lines"] > 0]
        kept = [unit for unit in eligible if pinned.get(unit) == stratum]
        for unit in (kept + [unit for unit in eligible if unit not in kept])[:per_stratum]:
            picks[unit] = stratum
    result = {"method": ("per (series, decade) stratum of the non_eval booklets, ranked by sha256(unit_id) hex digest "
                         f"ascending: the first {per_stratum} booklet(s) that pass the born-digital check and give at least "
                         "one line; dev is never drawn from eval or unassigned units"),
              "per_stratum": per_stratum, "picks": picks, "ranking": considered}
    if pinned:
        result["pinned"] = {"picks": pinned, "kept": sorted(unit for unit in picks if pinned.get(unit) == picks[unit]),
                            "dropped": sorted(unit for unit in pinned if unit not in picks),
                            "rule": "pinned picks kept first in their stratum while they pass and give lines; the rest by the rule"}
    return result


def shuffle_key(seed: str, row_id: str) -> str:
    """A row's place in the seeded order of every list output (lstmtraining does not shuffle)."""

    return sha256_bytes(f"{seed}\0{row_id}".encode("utf-8"))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    return [str(item) for item in value] if isinstance(value, (list, tuple)) else [str(value)]


def _first_with(dirs: Sequence[str], name_for: Callable[[Path], Path]) -> Path | None:
    for directory in dirs:
        if name_for(Path(directory)).exists():
            return Path(directory)
    return None


# --- build -------------------------------------------------------------------------------------------------------


def _load_entries(snapshot: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (snapshot / "entries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def _reshumot_source() -> SourceConfig:
    from hocrgen.config.loader import load_and_validate_bundle

    return next(source for source in load_and_validate_bundle().source_registry.sources if source.id == RESHUMOT_SOURCE_ID)


def _page_image_paths(snapshot: Path, entries: Sequence[Mapping[str, Any]], lines_per_entry: Mapping[str, int]) -> list[str]:
    """Two rendered page images of a booklet: the pages giving the most lines (ties by page), in page order."""

    ranked = sorted(entries, key=lambda e: (-lines_per_entry.get(e["entry_id"], 0), e["page"]["pdf_page_index"]))[:2]
    ranked.sort(key=lambda e: e["page"]["pdf_page_index"])
    return [str((snapshot / (reshumot_page_render(e) or {}).get("local_path", "")).resolve()) for e in ranked]


def build(args: argparse.Namespace, *, registry: EvalReservedUnitsRegistry | None = None, source: SourceConfig | None = None,
          facts_for: Callable[[Path, Mapping[int, Any]], dict[str, Any]] | None = None) -> dict[str, Any]:
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    snapshots = [Path(path).resolve() for path in _as_list(args.snapshot)]
    pdf_caches = _as_list(args.pdf_cache)
    layer_dirs = _as_list(getattr(args, "page_layers", None))
    registry = registry or packaged_registry()
    source = source or _reshumot_source()
    facts_for = facts_for or pdf_facts
    entries, root_of = [], {}
    units_in: dict[str, Path] = {}
    for snapshot in snapshots:
        for entry in _load_entries(snapshot):
            unit = entry_unit(entry)
            if units_in.setdefault(unit, snapshot) != snapshot or entry["entry_id"] in root_of:
                raise SystemExit(f"{unit}: booklet in more than one snapshot")
            root_of[entry["entry_id"]] = snapshot
            entries.append(entry)
    seed = getattr(args, "shuffle_seed", None) or DEFAULT_SHUFFLE_SEED
    pool_path = getattr(args, "exclude_6grams", None)
    pool = load_gram_pool(Path(pool_path)) if pool_path else None
    pool_digests = frozenset(pool["digests"]) if pool else frozenset()
    pinned = None
    if getattr(args, "keep_dev_from", None):
        pinned = json.loads(Path(args.keep_dev_from).read_text(encoding="utf-8"))["dev_selection"]["picks"]

    # Guard 1: select non_eval booklets from metadata alone; eval and unassigned booklets are counted, never opened.
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    skipped: dict[str, Counter] = defaultdict(Counter)
    for entry in entries:
        found = unit_status({"source_id": RESHUMOT_SOURCE_ID, "entry_id": entry["entry_id"], "unit_id": entry_unit(entry)}, registry)
        status = found[1] if found else EvalUnitStatus.unassigned
        if status is EvalUnitStatus.non_eval:
            by_unit[entry_unit(entry)].append(entry)
        else:
            skipped[status.value][entry_unit(entry)] += 1
    selected = [{"source_id": RESHUMOT_SOURCE_ID, "unit_id": unit, "entry_id": e["entry_id"]} for unit, es in by_unit.items() for e in es]
    refuse_eval_reserved_training_input(selected, builder=BUILDER, registry=registry)

    # Guard 2: the born-digital check per booklet, on the cached PDF and every page's glyph layer.
    booklets: dict[str, dict[str, Any]] = {}
    for unit in sorted(by_unit):
        es = sorted(by_unit[unit], key=lambda e: e["page"]["pdf_page_index"])
        first = es[0]
        slug = unit_slug(unit)
        snapshot = root_of[first["entry_id"]]
        pdf_path = (_first_with(pdf_caches, lambda d: d / f"{slug}.pdf") or Path(pdf_caches[0])) / f"{slug}.pdf"
        pins = {e["pdf"]["sha256"] for e in es}
        record = {"series": first["booklet"]["series"], "series_name_he": first["booklet"].get("series_name_he"),
                  "booklet_number": str(first["booklet"]["booklet_number"]), "publish_date": first["booklet"]["publish_date"],
                  "display_name": first["booklet"].get("display_name"), "publisher_url": first["pdf"].get("document_url"),
                  "pdf_sha256": first["pdf"]["sha256"], "pages_in_snapshot": len(es), "pdf_page_count": first["pdf"].get("page_count")}
        if not pdf_path.is_file():
            check = {"passed": False, "reasons": ["pdf_missing"], "evidence": {}}
        elif len(pins) != 1 or sha256_bytes(pdf_path.read_bytes()) not in pins:
            check = {"passed": False, "reasons": ["pdf_sha256_mismatch"], "evidence": {}}
        else:
            page_count = int(first["pdf"].get("page_count") or 0)
            layer_dir = _first_with(layer_dirs, lambda d: d / f"{slug}__p0001.json") or _first_with(
                layer_dirs, lambda d: d / f"{slug}__p0001.json.gz") or (Path(layer_dirs[0]) if layer_dirs else None)
            layers = load_page_layers(layer_dir, slug, page_count, pdf_path)
            check = born_digital_check(facts_for(pdf_path, layers))
            mismatched = []
            for e in es:  # the layers checked must be the tranche's own extraction of the same pages
                committed = json.loads(read_glyph_layer_bytes(snapshot / e["text"]["extraction"]["raw_local_path"]))
                if layers.get(e["page"]["pdf_page_index"]) != committed:
                    mismatched.append(e["entry_id"])
            if mismatched:
                check["passed"] = False
                check["reasons"] = sorted(set(check["reasons"]) | {"page_layer_differs_from_tranche"})
                check["evidence"]["layer_mismatch_pages"] = mismatched
        record["born_digital"] = check
        booklets[unit] = record

    # Pages and candidate lines (born-digital booklets only).
    jobs = [(e, str(root_of[e["entry_id"]]), source) for unit in sorted(by_unit) if booklets[unit]["born_digital"]["passed"]
            for e in sorted(by_unit[unit], key=lambda e: e["page"]["pdf_page_index"])]
    entry_of = {e["entry_id"]: e for es in by_unit.values() for e in es}
    drops: Counter = Counter()
    drops_by_booklet: dict[str, Counter] = defaultdict(Counter)
    refused_pages: dict[str, str] = {}
    candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    workers = int(getattr(args, "workers", 1) or 1)
    results: Iterable[Any]
    if workers > 1:  # pragma: no cover - exercised by operator runs
        with Pool(workers) as pool:
            results = pool.map(_page_job, jobs, chunksize=4)
    else:
        results = map(_page_job, jobs)
    for entry_id, rows, page_drops, refused in results:
        unit = entry_unit(entry_of[entry_id])
        drops.update(page_drops)
        drops_by_booklet[unit].update(page_drops)
        if refused:
            refused_pages[entry_id] = refused
            drops[f"page_refused:{refused}"] += 1
            drops_by_booklet[unit][f"page_refused:{refused}"] += 1
        for row in rows:
            if pool_digests and any(gram_digest(gram) in pool_digests for gram in word_grams(row["text"])):
                drops["shares_word_6gram_with_eval_text"] += 1
                drops_by_booklet[unit]["shares_word_6gram_with_eval_text"] += 1
                continue
            candidates[unit].append({**row, "entry_id": entry_id})
    for unit, booklet in booklets.items():
        booklet["candidate_lines"] = len(candidates.get(unit, []))
        if not booklet["born_digital"]["passed"]:
            drops["booklet_not_born_digital"] += booklet["pages_in_snapshot"]
            drops_by_booklet[unit]["booklet_not_born_digital"] += booklet["pages_in_snapshot"]

    dev = choose_dev(booklets, per_stratum=args.dev_per_stratum, pinned=pinned)
    cap = args.max_lines_per_booklet
    rows: list[dict[str, Any]] = []
    capped: dict[str, int] = {}
    for unit in sorted(booklets):
        booklet = booklets[unit]
        if not booklet["born_digital"]["passed"]:
            booklet["split"] = "refused"
            continue
        split = "dev" if unit in dev["picks"] else "train"
        booklet["split"] = split
        lines = {line_id(c["entry_id"], c["line_index"]): c for c in candidates.get(unit, [])}
        keep = cap_lines(list(lines), cap)
        if len(keep) < len(lines):
            capped[unit] = len(lines) - len(keep)
        for lid in keep:
            c = lines[lid]
            entry = entry_of[c["entry_id"]]
            render = reshumot_page_render(entry) or {}
            rendering = render.get("rendering") or {}
            slug = unit_slug(unit)
            rows.append({
                "id": lid, "split": split, "book": slug, "record_id": slug, "unit_id": unit, "source_id": RESHUMOT_SOURCE_ID,
                "entry_id": c["entry_id"], "series": booklet["series"], "series_name_he": booklet["series_name_he"],
                "booklet_number": booklet["booklet_number"], "publish_date": booklet["publish_date"],
                "page": entry["page"]["pdf_page_index"], "printed_page_number": entry["page"].get("printed_page_number"),
                "line_index": c["line_index"], "text": c["text"], "stratum": "unpointed",
                "label_source": LABEL_SOURCE, "label_tier": "silver", "adjudication_status": "not_adjudicated",
                "reference_eligible": False, "capture": CAPTURE, "proposed_node_hint": NODE_HINT,
                "reading_order_verified": entry["text"]["reading_order_verified"], "line_order_verified": c["line_order_verified"],
                "tier_a_flags": c["tier_a_flags"], "segments": c["segments"],
                "text_normalization": entry["text"]["extraction"]["normalization"],
                "bbox_page_pt": c["bbox_page_pt"], "image_scale": c["image_scale"], "bbox_image": c["bbox_image"],
                "crop_box_image": c["crop_box_image"], "crop_method": CROP_METHOD,
                "page_render": {"path": render.get("local_path"), "sha256": render.get("sha256"), "dpi": rendering.get("dpi"),
                                "renderer": rendering.get("renderer"), "renderer_version": rendering.get("renderer_version"),
                                "is_scan": rendering.get("is_scan")},
                "image": f"{split}/{slug}/{lid}.png", "image_sha256": None,
                "license": LICENSE, "license_basis": LICENSE_BASIS, "attribution": ATTRIBUTION,
                "publisher_url": booklet["publisher_url"], "pdf_sha256": booklet["pdf_sha256"], "born_digital_check": "passed",
            })

    # Guard 1 again, on the rows, before anything is written.
    refuse_eval_reserved_training_input(rows, builder=BUILDER, registry=registry)
    # Every list output in one seeded order: lstmtraining reads its list as given and does not shuffle.
    rows.sort(key=lambda row: shuffle_key(seed, row["id"]))

    out.mkdir(parents=True)
    by_entry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_entry[row["entry_id"]].append(row)
    for entry_id, entry_rows in by_entry.items():
        entry = entry_of[entry_id]
        root = root_of[entry_id]
        text = entry["text"]
        layer = json.loads(read_glyph_layer_bytes(root / text["extraction"]["raw_local_path"]))
        table = json.loads((root / text["extraction"]["outline_table_path"]).read_text(encoding="utf-8"))
        render = reshumot_page_render(entry) or {}
        dpi = float((render.get("rendering") or {}).get("dpi") or 0)
        with Image.open(root / render["local_path"]) as page:
            page.load()
            page = page.convert("L")
            verdict = page_verdict(convert_glyph_layer(layer, table), layer, page, dpi)
            kept = [unit for unit in verdict.kept if unit.text]
            for row in entry_rows:
                image, box, _ = crop_line(page, kept[row["line_index"]], dpi / 72.0)
                if box != row["crop_box_image"]:
                    raise RuntimeError(f"{row['id']}: crop box changed between passes")
                path = out / row["image"]
                path.parent.mkdir(parents=True, exist_ok=True)
                image.save(path)
                path.with_suffix(".gt.txt").write_text(row["text"] + "\n", encoding="utf-8")
                row["image_sha256"] = sha256_bytes(path.read_bytes())
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    for split in ("train", "dev"):
        (out / f"{split}.txt").write_text("".join(row["image"] + "\n" for row in rows if row["split"] == split), encoding="utf-8")

    lines: dict[str, Counter] = defaultdict(Counter)
    by_series: dict[str, Counter] = defaultdict(Counter)
    flags_kept: Counter = Counter()
    chars: Counter = Counter()
    lines_per_entry: Counter = Counter()
    for row in rows:
        lines[row["split"]][row["unit_id"]] += 1
        by_series[row["split"]][row["series"]] += 1
        flags_kept.update(row["tier_a_flags"])
        chars.update(row["text"])
        lines_per_entry[row["entry_id"]] += 1
    output_status = Counter()
    for row in rows:
        found = unit_status(row, registry)
        output_status[found[1].value if found else "not_governed"] += 1
    for unit, booklet in booklets.items():
        booklet["lines"] = {split: lines[split][unit] for split in ("train", "dev") if lines[split][unit]}
        booklet["dropped"] = dict(sorted(drops_by_booklet[unit].items()))
    tagger = [{"unit_id": unit, "series": b["series"], "series_name_he": b["series_name_he"], "booklet_number": b["booklet_number"],
               "publish_date": b["publish_date"], "split": b["split"], "proposed_node_hint": NODE_HINT,
               "lines": sum(b["lines"].values()), "publisher_url": b["publisher_url"],
               "page_images": _page_image_paths(units_in[unit], by_unit[unit], lines_per_entry)}
              for unit, b in sorted(booklets.items())]
    (out / "tagger_units.json").write_text(json.dumps({"schema": "s16c_reshumot_tagger_units.v1", "proposed_node_hint": NODE_HINT,
                                                       "note": NODE_HINT_NOTE, "units": tagger}, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    summary: dict[str, Any] = {
        "schema": SCHEMA, "labels": "publisher glyph-layer text of born-digital PDFs, verified within each line; silver "
                                    "training labels, never evaluation references", "label_source": LABEL_SOURCE,
        "capture": CAPTURE, "proposed_node_hint": NODE_HINT, "proposed_node_hint_note": NODE_HINT_NOTE,
        "license": LICENSE, "license_basis": LICENSE_BASIS, "attribution": ATTRIBUTION, "release_notice": RELEASE_NOTICE,
        "snapshot": str(snapshots[0]), "pdf_cache": str(Path(pdf_caches[0]).resolve()),
        "page_layers": str(Path(layer_dirs[0]).resolve()) if layer_dirs else None,
        "totals": {split: sum(c.values()) for split, c in lines.items()},
        "lines": {split: dict(sorted(c.items())) for split, c in lines.items()},
        "lines_by_series": {split: dict(sorted(c.items())) for split, c in by_series.items()},
        "dropped": dict(sorted(drops.items())), "dropped_definitions": DROP_DEFINITIONS,
        "booklets": dict(sorted(booklets.items())),
        "born_digital": {
            "passed": sorted(u for u, b in booklets.items() if b["born_digital"]["passed"]),
            "refused": {u: b["born_digital"]["reasons"] for u, b in sorted(booklets.items()) if not b["born_digital"]["passed"]},
            "ocr_software_pattern": OCR_SOFTWARE.pattern,
        },
        "refused_pages": dict(sorted(refused_pages.items())),
        "eval_reserved_check": {
            "decision": "heocr-engine decision 0017", "registry": registry_provenance(registry),
            "input_units": {"non_eval": len(by_unit), **{status: len(units) for status, units in skipped.items()}},
            "input_pages": {"non_eval": len(selected), **{status: sum(units.values()) for status, units in skipped.items()}},
            "skipped_units_never_opened": {status: len(units) for status, units in skipped.items()},
            "guard": "refuse_eval_reserved_training_input on the selected pages and on the line rows; both passed",
            "output_rows_by_status": dict(output_status),
            "eval_rows": output_status.get("eval", 0), "unassigned_rows": output_status.get("unassigned", 0),
            "dev_units_all_non_eval": all(registry.status(RESHUMOT_SOURCE_ID, unit) is EvalUnitStatus.non_eval for unit in dev["picks"]),
        },
        "dev_selection": dev, "max_lines_per_booklet": cap, "capped_lines": capped,
        "tier_a_rules": {**TIER_A_ORIGIN, "bidi_or_digit_flags": sorted(BIDI_FLAGS),
                         "rule": "a flagged line is kept only when line_order_verified"},
        "tier_a_flags_on_kept_lines": dict(sorted(flags_kept.items())),
        "kept_lines_order_verified": sum(1 for row in rows if row["line_order_verified"]),
        "characters": dict(sorted(chars.items(), key=lambda item: (-item[1], item[0]))),
        "crop": {"method": CROP_METHOD, "pad_pt": CROP_PAD_PT, "glyph_pad_px": INK_GLYPH_PAD_PX},
        "manifest_sha256": sha256_bytes(manifest.read_bytes()),
        "shuffle_seed": seed,
        "shuffle": {"seed": seed, "method": "rows ordered by sha256(seed + NUL + row id) hex digest ascending",
                    "applies_to": ["manifest.jsonl", "train.txt", "dev.txt"],
                    "why": "lstmtraining reads its list files in order and does not shuffle"},
        "list_files": {split: {"path": f"{split}.txt", "lines": sum(1 for row in rows if row["split"] == split),
                               "sha256": sha256_bytes((out / f"{split}.txt").read_bytes())} for split in ("train", "dev")},
    }
    if len(snapshots) > 1 or len(pdf_caches) > 1 or len(layer_dirs) > 1:
        summary["snapshots"] = [str(path) for path in snapshots]
        summary["pdf_caches"] = [str(Path(path).resolve()) for path in pdf_caches]
        summary["page_layer_dirs"] = [str(Path(path).resolve()) for path in layer_dirs]
    if pool is not None:
        summary["eval_text_overlap_filter"] = {
            "rule": ("a line sharing any word 6-gram (Hebrew-letter words, logical order) with the pool is dropped "
                     "(shares_word_6gram_with_eval_text): amendments quote the text they amend"),
            "pool": str(Path(pool_path).resolve()), "pool_sha256": sha256_bytes(Path(pool_path).read_bytes()),
            "pool_digests": len(pool_digests), "pool_targets": pool.get("targets"), "pool_built_by": pool.get("built_by"),
            "rule_origin": NGRAM_ORIGIN, "lines_dropped": drops.get("shares_word_6gram_with_eval_text", 0),
        }
    if getattr(args, "created_at", None):
        summary["created_at"] = args.created_at
    if getattr(args, "signature", None):
        summary["signature"] = args.signature
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


DROP_DEFINITIONS = {
    "booklet_not_born_digital": "pages of booklets refused by the born-digital check (counted in pages)",
    "page_refused:<reason>": "pages refused by the tranche gate or whose re-derived text differs (counted in pages)",
    "unmapped_or_private_glyph": "lines with a private-use, replacement, unassigned or (cid:N) code point or glyph issue",
    "pointed": "lines carrying any niqqud or cantillation mark",
    "bidi_or_digit_order_unverified": "lines tier-A flags for bidi or digit order whose order is not verified within the line",
    "no_letters_or_digits": "lines without a letter or digit",
    "ink_overlaps_other_ink": "lines whose glyph boxes touch another line, a page image, a rule or a coloured fill",
    "shares_word_6gram_with_eval_text": ("lines sharing a word 6-gram (logical order) with a v1 eval booklet or a wave-1 "
                                         "page (heocr-eval's ngram_overlap.py rule, --exclude-6grams)"),
}


def verify(out: Path, *, registry: EvalReservedUnitsRegistry | None = None) -> list[str]:
    """Problems in a built set (empty when it passes)."""

    registry = registry or packaged_registry()
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    problems = []
    if sha256_bytes((out / "manifest.jsonl").read_bytes()) != summary["manifest_sha256"]:
        problems.append("manifest sha256 differs from summary")
    try:
        refuse_eval_reserved_training_input(rows, builder="reshumot_lines verify", registry=registry)
    except EvalReservedUnitError as exc:
        problems.append(str(exc))
    dev = set(summary["dev_selection"]["picks"])
    ids = Counter(row["id"] for row in rows)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    for row in rows:
        where = row["id"]
        try:
            found = unit_status(row, registry)
        except EvalReservedUnitError as exc:
            problems.append(f"{where}: {exc}")
            found = None
        if found is None or found[1] is not EvalUnitStatus.non_eval:
            problems.append(f"{where}: unit {row.get('unit_id')} is not non_eval")
        if row["split"] not in ("train", "dev") or (row["split"] == "dev") != (row["unit_id"] in dev):
            problems.append(f"{where}: split {row['split']} disagrees with the dev booklets")
        if POINTS.search(unicodedata.normalize("NFD", row["text"])) or bad_code_points(row["text"]):
            problems.append(f"{where}: label has niqqud or a private-use / unmapped code point")
        if BIDI_FLAGS & set(tier_a_flags(row["text"])) and not row.get("line_order_verified"):
            problems.append(f"{where}: bidi or digit-order flagged line without verified order")
        if row.get("label_source") != LABEL_SOURCE or row.get("capture") != CAPTURE or row.get("reference_eligible") is not False:
            problems.append(f"{where}: provenance fields missing")
        if not all(row.get(key) not in (None, "") for key in ("unit_id", "series", "publish_date", "page", "entry_id")):
            problems.append(f"{where}: booklet unit, series, date or page missing")
        if row.get("license") != LICENSE or row.get("attribution") != ATTRIBUTION or not row.get("publisher_url"):
            problems.append(f"{where}: licence, attribution or publisher URL missing")
        if row.get("born_digital_check") != "passed" or not ((summary["booklets"].get(row["unit_id"]) or {}).get("born_digital") or {}).get("passed"):
            problems.append(f"{where}: booklet did not pass the born-digital check")
        path = out / row["image"]
        if not row.get("image_sha256") or not path.is_file() or sha256_bytes(path.read_bytes()) != row["image_sha256"]:
            problems.append(f"{where}: image missing or sha256 mismatch")
        gt = path.with_suffix(".gt.txt")
        if not gt.is_file() or gt.read_text(encoding="utf-8") != row["text"] + "\n":
            problems.append(f"{where}: gt.txt missing or differs from the label")
    if summary["eval_reserved_check"]["eval_rows"] or summary["eval_reserved_check"]["unassigned_rows"]:
        problems.append("summary counts eval or unassigned rows")
    seed = summary.get("shuffle_seed")
    if seed is not None:
        if [row["id"] for row in rows] != sorted((row["id"] for row in rows), key=lambda value: shuffle_key(seed, value)):
            problems.append("manifest is not in the seeded shuffle order")
        for split in ("train", "dev"):
            listed = (out / f"{split}.txt").read_text(encoding="utf-8").splitlines() if (out / f"{split}.txt").is_file() else None
            if listed != [row["image"] for row in rows if row["split"] == split]:
                problems.append(f"{split}.txt missing or not the manifest's {split} rows in order")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("build", help="cut a labelled line set from a tranche's Reshumot snapshot")
    b.add_argument("out")
    b.add_argument("--snapshot", required=True, action="append",
                   help="a sources/reshumot_born_digital/snapshot; repeat to read several (a booklet may be in only one)")
    b.add_argument("--pdf-cache", required=True, action="append",
                   help="a capture cache's reshumot/pdf directory (<series>_<n>.pdf); repeat, searched in order")
    b.add_argument("--page-layers", action="append",
                   help="glyph layers of every PDF page (<series>_<n>__pNNNN.json[.gz]); repeat; else extracted")
    b.add_argument("--keep-dev-from", help="an earlier build's summary.json: keep its dev booklets (dev_selection.picks)")
    b.add_argument("--exclude-6grams", help="a heocr_eval_word_ngram_pool.v1 file: drop lines sharing a word 6-gram with it")
    b.add_argument("--shuffle-seed", default=DEFAULT_SHUFFLE_SEED,
                   help="seed of the order of manifest.jsonl, train.txt and dev.txt (recorded in summary.json)")
    b.add_argument("--max-lines-per-booklet", type=int, default=DEFAULT_MAX_LINES)
    b.add_argument("--dev-per-stratum", type=int, default=1)
    b.add_argument("--workers", type=int, default=1)
    b.add_argument("--created-at")
    b.add_argument("--signature", help="the operator's signature line, recorded in summary.json")
    v = sub.add_parser("verify", help="check a built set")
    v.add_argument("out")
    args = parser.parse_args(argv)
    if args.command == "build":
        summary = build(args)
        print(json.dumps({key: summary[key] for key in ("totals", "dropped", "manifest_sha256")}, ensure_ascii=False))
        return 0
    problems = verify(Path(args.out))
    for problem in problems[:50]:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
