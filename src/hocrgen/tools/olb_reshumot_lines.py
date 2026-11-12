"""Silver training lines from the scanned Reshumot booklets (1948 to mid-2005), labelled with same-wording text from
Hebrew Wikisource's ספר החוקים הפתוח (OLB) (operator tool).

Subcommands:

- ``olb-fetch`` fetches the current revision of every OLB page (category בוט חוקים) from the Wikisource API, 50 titles
  per request and at most one request per second, and pins each page's revision id and content sha256.
- ``olb-index`` parses the fetched pages (``parse_olb_page``): the law's citations (series, Hebrew year, printed page;
  principal, amendment, or "חוק קודם" / "חוק חדש"), and its text as printed paragraphs, with the OLB editorial notes
  (``ח:הערה``: "(בוטל)", "(נמחקה)", ...) and the markup stripped.
- ``plan`` lists, for every ``non_eval`` booklet of heocr-eval's ``midcentury_unit_split_v0``, the OLB pages whose
  citations point into it (same series, same Hebrew year, printed page inside the booklet), ranked for capture.
- ``capture`` fetches the planned booklets' PDFs from the gov.il Reshumot API (one request per 1.2 s, the HeOCR
  research User-Agent). Downloads are untrusted: nothing here executes them, and ``build`` runs under ``python -I``.
- ``build`` cuts one image per accepted line and writes a ``bynli_lines_v2``-shaped set (``{train,dev}/<booklet>/
  <id>.png`` with a ``.gt.txt`` each, ``manifest.jsonl``, ``summary.json``); ``verify`` checks a built set.

**The label is OLB text, kept only where it equals the print.** The publisher's OCR layer (Imagestore for ספר החוקים,
ABBYY for קובץ התקנות) and stock Tesseract only *locate* lines and give evidence; their text is never a label and is
never written out. A located line is kept only when an OLB word span, normalised by ``compare_key`` (quote, dash,
maqaf and bracket glyphs folded, spacing removed, the order of digit groups ignored), is confirmed by the OCR
evidence (``accept_line``):

- ``layer_exact`` / ``tesseract_exact``: one reading equals the span;
- ``char_consensus`` (only where both readings exist): every character of the span is read by at least one of them,
  and no character the two readings agree on differs from it.

Everything else is dropped with a counted reason. Footnote markers that the print adds to a line are stripped from the
comparison (they are not in OLB), and the line is then dropped (``footnote_marker_in_print``) unless
``--keep-footnote-lines`` is given, because its label would lack a printed glyph. Each row records its
``match_evidence`` and the CER of each OCR reading against the accepted label, so the bias towards lines the OCR reads
well is measurable.

**The law's version.** An OLB page is a candidate for a booklet only through one of its citations (``ס״ח`` or
``ק״ת``, Hebrew year, printed page) that falls inside the booklet. A page that replaced an older law of the same name
cites the new law's year ("חוק חדש"), so it is never matched to the old booklet. Amendment marks are not trusted
either way: the per-line match decides.

Held-out units (source ``reshumot_scanned``, unit ids ``reshumot_scanned:<series>_<number>``, page ids
``reshumot_scanned_<series>_<number>__p0001``): whole booklets that heocr-eval's midcentury split marks test or dev
are never planned, fetched or read, and ``refuse_eval_reserved_training_input`` runs against the packaged registry,
which must govern ``reshumot_scanned`` (synced from ``pmod_unit_split_v2``; ``training_registry`` fails closed
before that). No input path may lie under the lead's eval test-unit folder (``refuse_forbidden_path``). Lines sharing a word 6-gram with a P-mod v1 eval
booklet's text or a wave-1 page are dropped (``eval_ngram_overlap``). Pointed lines are dropped. Every list output
is shuffled with ``--shuffle-seed``.

Licences: line images are PD-IL (Copyright Act 2007 section 6). Labels are OLB text, CC BY-SA 4.0 with attribution to
the Hebrew Wikisource contributors (heocr-engine decision 0016); every row carries the page title and pinned revision.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import html
import json
import random
import re
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from PIL import Image

TOOL = "hocrgen.tools.olb_reshumot_lines"
TOOL_VERSION = "0.1.0"
SCHEMA = "s16c_olb_reshumot_lines.v1"
BUILDER = "olb_reshumot_lines build"
SOURCE_ID = "reshumot_scanned"  # agreed with heocr-eval: unit ids reshumot_scanned:<series>_<number>
LABEL_SOURCE = "wikisource_olb_same_wording"
CAPTURE = "scan"
NODE_HINT = "new_printed"
NODE_HINT_NOTE = "the maintainer placed all 17 mid-century strata (decade x series) as new printed (2026-11-11)"
# heocr-eval's test-unit PDFs, fetched by the lead: never read, listed or used by this tool (any path under it)
FORBIDDEN_INPUT_DIRS = (Path.home() / "agents/environments/opensource/projects/heocr/tasks/modern-s6-scout/midcentury_test",)
NORMALIZER = "olb_print_compare.v1"
DEV_RULE = "layer_exact_only.v1"  # dev lines: kept iff the publisher text layer equals OLB, whatever Tesseract reads
LABEL_FOLD = "olb_label_fold.v1"
USER_AGENT = "HeOCR-research/0.1 (+https://github.com/HeOCR)"
WS_API = "https://he.wikisource.org/w/api.php"
OLB_CATEGORY = "קטגוריה:בוט חוקים"
RESHUMOT_SEARCH_URL = "https://pub-justice.openapi.gov.il/pub/moj/portal/rest/searchpredefinedapi/v1/SearchPredefinedApi/Reshumot/Search"
RESHUMOT_CLIENT_ID = "149a5bad-edde-49a6-9fb9-188bd17d4788"  # the public id embedded in the gov.il collector page
GOV_GAP_S = 1.2
WS_GAP_S = 1.0
TEXT_LICENCE = "CC BY-SA 4.0"
TEXT_LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/"
TEXT_ATTRIBUTION = "Hebrew Wikisource contributors, ספר החוקים הפתוח"
IMAGE_LICENSE = "PD-IL"
IMAGE_LICENSE_BASIS = "Copyright Act 2007 section 6: no copyright in laws and regulations (ספר החוקים, קובץ התקנות)"
IMAGE_ATTRIBUTION = "Reshumot (רשומות), the official gazette of the State of Israel"
SERIES = {"1": "sefer_hachukim", "3": "kovetz_hatakanot"}
SERIES_ABBREV = {"ס״ח": "sefer_hachukim", "ק״ת": "kovetz_hatakanot"}
SCAN_DPI = {"sefer_hachukim": 400, "kovetz_hatakanot": 300}
MIN_LINE_CHARS = 8          # letters and digits in the label; shorter lines can match anywhere
MIN_LINE_WORDS = 2
MAX_LOCATE_CER = 0.35       # layer (or Tesseract) reading against the located span: above this the line is not located
MAX_CONSENSUS_CER = 0.25    # each reading against the span, for the char_consensus tier
CROP_PAD_FRAC = 0.22        # of the line height, clipped at the neighbouring lines
MAX_LINES_PER_BOOKLET = 6100
RELEASE_NOTICE = (
    "Line images are cut by HeOCR from scans of ספר החוקים and קובץ התקנות published by Reshumot (רשומות), the official "
    "gazette of the State of Israel (Copyright Act 2007 section 6, PD-IL; status outside Israel, including the US, is not "
    "separately asserted). Line labels are text of Hebrew Wikisource's ספר החוקים הפתוח, by the Hebrew Wikisource "
    "contributors, under CC BY-SA 4.0 (share-alike): each row names its page and pinned revision (attribution_url). Any "
    "adaptation of the label text must carry this attribution and be shared under CC BY-SA 4.0 or a compatible licence. "
    "Labels are kept only where OCR evidence confirms that the consolidated OLB text equals the print: silver training "
    "labels, never evaluation references. No line comes from a midcentury test or dev booklet or a P-mod eval unit."
)

# --- Hebrew numerals and citations --------------------------------------------------------------------------------

HEB_VALUES = {"א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9, "י": 10, "כ": 20, "ך": 20,
              "ל": 30, "מ": 40, "ם": 40, "נ": 50, "ן": 50, "ס": 60, "ע": 70, "פ": 80, "ף": 80, "צ": 90, "ץ": 90,
              "ק": 100, "ר": 200, "ש": 300, "ת": 400}
HEB_YEAR = re.compile(r"^ה?ת[א-ת״׳\"']{1,5}$")


def hebrew_year(text: str) -> int | None:
    """``תש״ט`` -> 5709 (a leading ה, as in התש״ט, is the thousands and is dropped); ``None`` if not a year."""

    word = text.strip().replace("־", "").split("־")[0]
    if not HEB_YEAR.match(word):
        return None
    if word.startswith("ה") and len(word) > 1:
        word = word[1:]
    value = sum(HEB_VALUES.get(char, 0) for char in word)
    return 5000 + value if 700 <= value < 800 else None


@dataclass(frozen=True)
class Citation:
    series: str            # sefer_hachukim | kovetz_hatakanot | other:<abbrev>
    hebrew_year: int | None
    page: int | None
    name: str
    role: str              # principal | amendment | prior_law | new_law
    url: str | None = None


def _split_args(body: str) -> list[str]:
    """Split a template body at top-level ``|`` (nested templates and links are kept whole)."""

    args, depth, link, current = [], 0, 0, []
    i = 0
    while i < len(body):
        two = body[i:i + 2]
        if two == "{{":
            depth += 1; current.append(two); i += 2; continue  # noqa: E702
        if two == "}}":
            depth -= 1; current.append(two); i += 2; continue  # noqa: E702
        if two == "[[":
            link += 1; current.append(two); i += 2; continue  # noqa: E702
        if two == "]]":
            link -= 1; current.append(two); i += 2; continue  # noqa: E702
        if body[i] == "|" and depth == 0 and link == 0:
            args.append("".join(current)); current = []; i += 1; continue  # noqa: E702
        current.append(body[i]); i += 1  # noqa: E702
    args.append("".join(current))
    return args


TEMPLATE = re.compile(r"\{\{((?:[^{}]|\{(?!\{)|\}(?!\}))*)\}\}")


def citations_from_header(header: str) -> list[Citation]:
    """The ``ח:תיבה`` citations of an OLB header, in order, with series and year carried forward as OLB writes them."""

    out: list[Citation] = []
    series = year = None
    role_base = "principal"
    pos = 0
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"'''(חוק קודם|חוק חדש|תקנות קודמות|תקנות חדשות|צו קודם|צו חדש):'''", header)]
    for match in re.finditer(r"\{\{ח:תיבה\|([^{}]*)\}\}", header):
        for start, mark in marks:
            if pos <= start < match.start():
                role_base = "prior_law" if "קוד" in mark else "new_law"
        pos = match.start()
        args = _split_args(match.group(1))
        where = args[0].strip()
        name = args[1].strip() if len(args) > 1 else ""
        url = args[2].strip() if len(args) > 2 else None
        abbrev = re.match(r"^([א-ת]{1,3}״[א-ת](?:-[א-ת״׳]+)?)\s+", where)
        if abbrev:
            series = SERIES_ABBREV.get(abbrev.group(1), f"other:{abbrev.group(1)}")
            where = where[abbrev.end():]
        parts = [p.strip() for p in where.split(",")]
        page = None
        if len(parts) >= 2:
            year = hebrew_year(parts[0]) or year
            page = int(parts[1]) if parts[1].isdigit() else None
        elif parts and parts[0].isdigit():
            page = int(parts[0])
        elif parts:
            year = hebrew_year(parts[0]) or year
        first_of_role = not any(c.role in ("principal", "new_law") for c in out) if role_base != "prior_law" else False
        if role_base == "prior_law":
            role = "prior_law"
        elif role_base == "new_law":
            role = "new_law" if first_of_role else "amendment"
        else:
            role = "principal" if not out else "amendment"
        out.append(Citation(series=series or "unknown", hebrew_year=year, page=page, name=name, role=role, url=url))
    return out


# --- OLB wikitext -> printed paragraphs ---------------------------------------------------------------------------

STRUCT = "\u0001"   # structural markers emitted by the template renderer: \x01KIND\x02arg\x02arg\x03
SEP = "\u0002"
END = "\u0003"


@dataclass
class Block:
    kind: str           # title | heading | section_heading | paragraph | preamble | signature | schedule
    text: str           # printed text (markup and editorial notes stripped), with its section/sub labels
    section: str = ""
    label: str = ""
    amended: str = ""   # the section's OLB amendment mark ("תיקון: ..."), informative only
    index: int = 0


@dataclass
class OlbPage:
    title: str
    revision_id: int | None
    timestamp: str | None
    content_sha256: str
    kind: str                       # law | regulations | order | other
    citations: list[Citation]
    blocks: list[Block]
    replaced_law: bool              # the header has "חוק קודם" / "חוק חדש"
    notes_stripped: int
    unknown_templates: list[str] = field(default_factory=list)


STRUCTURAL = {"ח:התחלה", "ח:סוף", "ח:סוגר", "ח:מפריד", "ח:פתיח-התחלה", "ח:מאגר", "ח:מאגר2"}
SUB_TEMPLATES = {"ח:ת": 1, "ח:תת": 1, "ח:תתת": 2, "ח:תתתת": 3, "ח:תתתתת": 4, "ח:תתתתתת": 5, "ח:תתתתתתת": 6}


def _render_template(body: str, counter: Counter, unknown: list[str]) -> str:
    args = _split_args(body)
    name = args[0].strip()
    pos = [a for a in args[1:] if "=" not in a.split("|")[0] or a.strip().startswith("(")]
    named = dict(a.split("=", 1) for a in args[1:] if "=" in a and not a.strip().startswith("("))
    if name in ("ח:חיצוני", "ח:פנימי"):
        if len(pos) >= 2:
            return pos[1]
        return pos[0].split("#")[0] if pos else ""
    if name == "ח:הערה":
        counter["editorial_note"] += 1
        return ""
    if name in ("ח:סעיף", "ח:סעיף*"):
        number = pos[0].strip() if pos else ""
        heading = pos[1].strip() if len(pos) > 1 else ""
        amended = pos[2].strip() if len(pos) > 2 else ""
        return f"{STRUCT}SEC{SEP}{number}{SEP}{heading}{SEP}{amended}{SEP}{'*' if name.endswith('*') else ''}{END}"
    if name in SUB_TEMPLATES:
        label = pos[0].strip() if pos else ""
        return f"{STRUCT}SUB{SEP}{label}{SEP}{named.get('סוג', '').strip()}{END}"
    if re.fullmatch(r"ח:קטע\d", name):
        heading = pos[1].strip() if len(pos) > 1 else (pos[0].strip() if pos else "")
        return f"{STRUCT}HEAD{SEP}{heading}{END}"
    if name == "ח:כותרת":
        return f"{STRUCT}TITLE{SEP}{pos[0] if pos else ''}{END}"
    if name == "ח:מבוא":
        return f"{STRUCT}PREAMBLE{END}"
    if name == "ח:חתימות":
        return f"{STRUCT}SIG{SEP}{pos[0] if pos else ''}{END}"
    if name == "ח:תיבה":
        return "{{" + body + "}}"  # kept for the header parser
    if name in STRUCTURAL:
        return f"{STRUCT}{name[2:]}{END}"
    if name == "ש":
        return " "
    if name == "=":
        return "="
    if name in ("מוקטן", "מוגדל", "ממורכז", "גופן", "קטן", "גדול"):
        return pos[-1] if pos else ""
    if name in ("ריק", "ויקיפדיה", "מיזמים", "מאגר חקיקה"):
        return ""  # an empty cell or a box linking a sister project, not law text
    if name.startswith("חוקי ") or name.startswith("ניווט"):
        return ""  # a navigation box, not law text
    unknown.append(name)
    return f"{STRUCT}UNKNOWN{SEP}{name}{END}"


def render_inline(text: str, counter: Counter, unknown: list[str]) -> str:
    """Expand templates innermost first (``ח:תיבה`` is kept for the header parser)."""

    kept: list[str] = []

    def keep(match: re.Match[str]) -> str:
        kept.append(match.group(0))
        return f"\u0004{len(kept) - 1}\u0004"

    for _ in range(20):
        new = TEMPLATE.sub(lambda m: _render_template(m.group(1), counter, unknown), text)
        new = re.sub(r"\{\{ח:תיבה\|[^{}]*\}\}", keep, new)
        if new == text:
            break
        text = new
    return re.sub("\u0004(\\d+)\u0004", lambda m: kept[int(m.group(1))], text)


def strip_markup(text: str) -> str:
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"<br\s*/?>", " ", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"</?(?:sup|sub|small|big|span|b|i|u|s|center|div|p|nowiki)[^>]*>", "", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def page_kind(title: str) -> str:
    if title.startswith("חוק") or title.startswith("פקודת"):
        return "law"
    if title.startswith("תקנות") or title.startswith("תקנון"):
        return "regulations"
    if title.startswith("צו"):
        return "order"
    return "other"


def parse_olb_page(title: str, wikitext: str, *, revision_id: int | None = None, timestamp: str | None = None) -> OlbPage:
    counter: Counter = Counter()
    unknown: list[str] = []
    rendered = render_inline(wikitext, counter, unknown)
    header_end = rendered.find(f"{STRUCT}סוגר{END}")
    header = rendered[:header_end] if header_end >= 0 else ""
    citations = citations_from_header(header)
    body = rendered[header_end:] if header_end >= 0 else rendered
    title_match = re.search(f"{STRUCT}TITLE{SEP}(.*?){END}", rendered)
    blocks: list[Block] = []
    if title_match:
        blocks.append(Block(kind="title", text=strip_markup(title_match.group(1))))
    section = section_heading = amended = ""
    pending_number = ""
    preamble = False
    in_table = False
    for raw_line in body.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("{|") or line.startswith("<table"):
            in_table = True
        if in_table:
            if line.startswith("|}") or line.startswith("</table"):
                in_table = False
            continue
        if line.startswith("*") and blocks and blocks[-1].kind == "signature":
            for part in re.split(r"<br\s*/?>", line.lstrip("* ")):
                text = strip_markup(part)
                if text:
                    blocks.append(Block(kind="signature", text=text))
            continue
        items = re.split(f"({STRUCT}[^{END}]*{END})", line)
        text_parts: list[str] = []
        label = ""
        kind = "paragraph"
        for item in items:
            if not item.startswith(STRUCT):
                text_parts.append(item)
                continue
            fields_ = item[1:-1].split(SEP)
            tag = fields_[0]
            if tag == "SEC":
                section, section_heading, amended = fields_[1], strip_markup(fields_[2]), fields_[3]
                pending_number = section
                kind = "schedule" if fields_[4] == "*" else "paragraph"
                if section_heading:
                    blocks.append(Block(kind="section_heading", text=section_heading, section=section, amended=amended))
            elif tag == "SUB":
                label = fields_[1]
            elif tag == "HEAD":
                heading = strip_markup(fields_[1])
                if heading:
                    blocks.append(Block(kind="heading", text=heading))
            elif tag == "PREAMBLE":
                preamble = True
            elif tag == "SIG":
                text = strip_markup(fields_[1])
                if text:
                    blocks.append(Block(kind="signature", text=text))
            elif tag == "UNKNOWN":
                kind = "unknown"
        text = strip_markup("".join(text_parts))
        if not text or kind == "unknown":
            continue
        prefix = []
        if pending_number and kind == "paragraph" and not section.startswith("("):
            prefix.append(f"{pending_number}.")
        elif pending_number and kind == "schedule" and section:
            prefix.append(section)
        pending_number = ""
        if label:
            prefix.append(label)
        blocks.append(Block(kind="preamble" if preamble else kind, text=" ".join(prefix + [text]), section=section,
                            label=label, amended=amended))
        preamble = False
    for i, block in enumerate(blocks):
        block.index = i
    return OlbPage(title=title, revision_id=revision_id, timestamp=timestamp,
                   content_sha256=hashlib.sha256(wikitext.encode("utf-8")).hexdigest(), kind=page_kind(title),
                   citations=citations, blocks=blocks,
                   replaced_law=bool(re.search(r"'''(?:חוק|תקנות|צו) (?:קודם|קודמות|חדש|חדשות):'''", header)),
                   notes_stripped=counter["editorial_note"], unknown_templates=sorted(set(unknown)))


# --- normaliser (comparison only) and label fold ------------------------------------------------------------------

POINTS = re.compile("[֑-ׇֽֿׁׂׅׄ]")
DOUBLE_QUOTES = "\"”“„״‟″«»"
SINGLE_QUOTES = "'׳’‘‚`´′"
DASHES = "–—‒−־‐‑-\u00ad"
BRACKETS = "()[]{}"
DIGIT_RUN = re.compile(r"\d+(?:[.,/:\-]\d+)*")
LETTER_OR_DIGIT = re.compile(r"[א-תA-Za-z0-9]")
FOOTNOTE_TOKEN = re.compile(r"^(?:\*{1,3}|\d{1,2}\)?|\(\d{1,2}\))$")
GLUED_FOOTNOTE = re.compile(r"(?<=[א-ת),.;:\"'])(\d{1,2}|\*{1,3})$")
LABEL_FOLD_TABLE = str.maketrans({**{q: '"' for q in "”“„״‟″"}, **{q: "'" for q in "׳’‘‚`´′"},
                                  **{d: "-" for d in "–—‒−־‐‑"}, " ": " ", "‏": "", "‎": ""})


def strip_points(text: str) -> str:
    return unicodedata.normalize("NFC", POINTS.sub("", unicodedata.normalize("NFD", text)))


def is_pointed(text: str) -> bool:
    return bool(POINTS.search(unicodedata.normalize("NFD", text)))


def fold_label(text: str) -> str:
    """The written label: OLB text with quote, geresh and dash glyphs folded to ``"`` ``'`` ``-`` (the print's glyph
    shape varies by era, so the label does not claim one), whitespace collapsed. Words and punctuation stay OLB's."""

    text = unicodedata.normalize("NFC", text).translate(LABEL_FOLD_TABLE)
    text = text.replace("''", '"')
    return re.sub(r"\s+", " ", text).strip()


def _canon_word(word: str) -> str:
    word = strip_points(unicodedata.normalize("NFC", word))
    out = []
    for char in word:
        if char in DOUBLE_QUOTES:
            out.append('"')
        elif char in SINGLE_QUOTES:
            out.append("'")
        elif char in DASHES:
            out.append("-")
        elif char in BRACKETS:
            out.append("|")
        elif char.isspace() or char in "‎‏":
            continue
        else:
            out.append(char)
    word = "".join(out).replace("''", '"')
    # the order of digit groups is not compared: ABBYY writes multi-group numbers in bidi (visual) order
    return DIGIT_RUN.sub(lambda m: ".".join(sorted(re.split(r"[.,/:\-]", m.group(0)))), word)


def compare_key(text: str) -> str:
    """The comparison form (``olb_print_compare.v1``): NFC, niqqud removed, quotes, dashes, maqaf and brackets folded,
    all spacing removed, digit groups sorted. Used to compare, never written as a label."""

    return "".join(_canon_word(w) for w in text.split())


def word_keys(text: str) -> tuple[list[str], list[str], list[int]]:
    """Words, their comparison keys, and each word's start offset in the concatenated key."""

    words = text.split()
    keys = [_canon_word(w) for w in words]
    starts, pos = [], 0
    for key in keys:
        starts.append(pos)
        pos += len(key)
    return words, keys, starts


def strip_footnote_markers(ocr: str, label: str) -> tuple[str, int]:
    """The OCR reading without footnote markers the label lacks (``*``, a lone 1-2 digit number, digits glued to a
    word's end), and how many were removed."""

    label_tokens = set(label.split())
    kept, removed = [], 0
    for token in ocr.split():
        if FOOTNOTE_TOKEN.match(token) and token not in label_tokens:
            removed += 1
            continue
        glued = GLUED_FOOTNOTE.search(token)
        if glued and token not in label_tokens:
            token = token[:glued.start()]
            removed += 1
        kept.append(token)
    return " ".join(kept), removed


# --- alignment ----------------------------------------------------------------------------------------------------


def levenshtein(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def cer(reading: str, reference: str) -> float:
    return levenshtein(reading, reference) / max(1, len(reference))


def semi_global(query: str, target: str) -> tuple[int, int, int]:
    """Best substring of ``target`` for ``query`` (free start and end in the target): (distance, start, end)."""

    n = len(query)
    if not target:
        return n, 0, 0
    prev = list(range(n + 1))
    prev_start = [0] * (n + 1)
    best = (n + 1, 0, 0)
    for j, ct in enumerate(target, 1):
        cur = [0]
        cur_start = [j]
        for i in range(1, n + 1):
            sub = prev[i - 1] + (query[i - 1] != ct)
            dele = prev[i] + 1
            ins = cur[i - 1] + 1
            value = min(sub, dele, ins)
            cur.append(value)
            cur_start.append(prev_start[i - 1] if value == sub else prev_start[i] if value == dele else cur_start[i - 1])
        if cur[n] < best[0]:
            best = (cur[n], cur_start[n], j)
        prev, prev_start = cur, cur_start
    return best


def alignment_ops(reference: str, reading: str) -> list[tuple[str, int, str]]:
    """Edit operations turning ``reference`` into ``reading``: ('=', i, c), ('S', i, c), ('D', i, ''), ('I', i, c),
    with ``i`` the reference position (an insertion sits before reference position ``i``)."""

    n, m = len(reference), len(reading)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (reference[i - 1] != reading[j - 1]))
    ops: list[tuple[str, int, str]] = []
    i, j = n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (reference[i - 1] != reading[j - 1]):
            ops.append(("=" if reference[i - 1] == reading[j - 1] else "S", i - 1, reading[j - 1]))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            ops.append(("D", i - 1, ""))
            i -= 1
        else:
            ops.append(("I", i, reading[j - 1]))
            j -= 1
    return ops[::-1]


@dataclass
class Paragraph:
    """One OLB block as a word sequence with comparison keys (the matching unit)."""

    page_title: str
    block_index: int
    kind: str
    words: list[str]
    keys: list[str]
    starts: list[int]
    key: str
    trigrams: dict[str, list[int]]


def make_paragraph(page_title: str, block: Block) -> Paragraph:
    words, keys, starts = word_keys(block.text)
    key = "".join(keys)
    grams: dict[str, list[int]] = defaultdict(list)
    for i in range(len(key) - 2):
        grams[key[i:i + 3]].append(i)
    return Paragraph(page_title, block.index, block.kind, words, keys, starts, key, dict(grams))


@dataclass
class Located:
    paragraph: Paragraph
    first_word: int
    last_word: int          # exclusive
    distance: int

    @property
    def raw_text(self) -> str:
        return " ".join(self.paragraph.words[self.first_word:self.last_word])

    @property
    def key(self) -> str:
        return "".join(self.paragraph.keys[self.first_word:self.last_word])


class ParagraphIndex:
    """The candidate OLB paragraphs of one booklet with a shared trigram index (trigram -> (paragraph, offset))."""

    def __init__(self, paragraphs: Sequence[Paragraph]):
        self.paragraphs = list(paragraphs)
        self.grams: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for p_index, paragraph in enumerate(self.paragraphs):
            for gram, positions in paragraph.trigrams.items():
                self.grams[gram].extend((p_index, pos) for pos in positions)


def locate(reading: str, paragraphs: Sequence[Paragraph] | ParagraphIndex, *, max_cer: float = MAX_LOCATE_CER) -> Located | None:
    """The OLB word span that best matches an OCR reading: trigram diagonal vote, semi-global alignment in a window,
    then the word boundaries (one word either way of the aligned ends) that minimise the distance."""

    index = paragraphs if isinstance(paragraphs, ParagraphIndex) else ParagraphIndex(paragraphs)
    query = compare_key(reading)
    if len(query) < 6:
        return None
    votes: Counter = Counter()
    for i in range(len(query) - 2):
        for p_index, pos in index.grams.get(query[i:i + 3], ()):
            votes[(p_index, (pos - i) // 4)] += 1
    if not votes:
        return None
    best: Located | None = None
    seen: set[tuple[int, int]] = set()
    for (p_index, diagonal), count in votes.most_common(4):
        if count < max(2, (len(query) - 2) // 8):
            break
        paragraph = index.paragraphs[p_index]
        lo = max(0, diagonal * 4 - 12)
        hi = min(len(paragraph.key), diagonal * 4 + len(query) + 16)
        if (p_index, lo) in seen:
            continue
        seen.add((p_index, lo))
        _, start, end = semi_global(query, paragraph.key[lo:hi])
        start, end = start + lo, end + lo
        w0 = _word_at(paragraph.starts, start)
        w1 = _word_at(paragraph.starts, max(start, end - 1)) + 1
        for s in range(max(0, w0 - 1), min(len(paragraph.words), w0 + 2)):
            for e in range(max(s + 1, w1 - 1), min(len(paragraph.words), w1 + 1) + 1):
                span = "".join(paragraph.keys[s:e])
                if abs(len(span) - len(query)) > max(4, len(query) // 3):
                    continue
                dist = levenshtein(query, span)
                if best is None or dist < best.distance or (dist == best.distance and e - s < best.last_word - best.first_word):
                    best = Located(paragraph, s, e, dist)
        if best is not None and best.distance == 0:
            break
    if best is None or best.distance > max_cer * max(1, len(best.key)):
        return None
    return best


def _word_at(starts: Sequence[int], offset: int) -> int:
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo


def consensus(label_key: str, readings: Sequence[str]) -> tuple[bool, dict[str, int]]:
    """Every label character read by at least one reading, and no deviation the readings agree on."""

    per_reading = []
    for reading in readings:
        confirmed = [False] * len(label_key)
        deviations: dict[tuple[str, int], str] = {}
        inserted: dict[int, str] = defaultdict(str)
        for op, i, char in alignment_ops(label_key, reading):
            if op == "=":
                confirmed[i] = True
            elif op == "S":
                deviations[("S", i)] = char
            elif op == "D":
                deviations[("D", i)] = ""
            else:
                inserted[i] += char
        for i, chars in inserted.items():
            deviations[("I", i)] = chars
        per_reading.append((confirmed, deviations))
    unconfirmed = sum(1 for i in range(len(label_key)) if not any(c[i] for c, _ in per_reading))
    agreed = 0
    if len(per_reading) >= 2:
        (_, d1), (_, d2) = per_reading[0], per_reading[1]
        agreed = sum(1 for k, v in d1.items() if k in d2 and d2[k] == v)
    # an inserted digit or mark may be printed (a footnote marker the other reading missed): never out-voted
    risky = sum(1 for _, d in per_reading for (op, _), chars in d.items() if op == "I" and re.search(r"[0-9*]", chars))
    # both readings insert something at the same place (whatever they read there): the print has text the label lacks
    places = [{i for (op, i) in d if op == "I"} for _, d in per_reading]
    agreed_insertions = len(set.intersection(*places)) if len(places) >= 2 else 0
    # a reading that sees anything beyond either end of the span (a word, a closing quote): the span may be short
    n = len(label_key)
    edge = sum(1 for _, d in per_reading for (op, i), chars in d.items() if op == "I" and i in (0, n))
    ok = unconfirmed == 0 and agreed == 0 and risky == 0 and agreed_insertions == 0 and edge == 0
    return ok, {"unconfirmed_chars": unconfirmed, "agreed_deviations": agreed, "inserted_digits_or_marks": risky,
                "agreed_insertion_places": agreed_insertions, "edge_insertions": edge}


def edge_insertion(label_key: str, reading: str) -> bool:
    """The reading has two or more characters, one of them a letter, before the span's start or after its end."""

    n = len(label_key)
    found: dict[int, str] = defaultdict(str)
    for op, i, char in alignment_ops(label_key, reading):
        if op == "I" and i in (0, n):
            found[i] += char
    return any(len(chars) >= 2 and re.search("[א-ת]", chars) for chars in found.values())


@dataclass
class Decision:
    accepted: bool
    reason: str
    tier: str | None
    evidence: dict[str, Any]


def accept_line(label_raw: str, layer: str | None, tesseract: str | None) -> Decision:
    """The per-line gate. ``label_raw`` is the located OLB span; ``layer`` the publisher OCR reading of the line (None
    where the PDF has no text layer); ``tesseract`` stock Tesseract's reading of the line crop."""

    label_key = compare_key(label_raw)
    evidence: dict[str, Any] = {"normalizer": NORMALIZER}
    readings: dict[str, str] = {}
    footnotes = 0
    for name, text in (("layer", layer), ("tesseract", tesseract)):
        if text is None:
            continue
        key = compare_key(text)
        if key != label_key:
            stripped, removed = strip_footnote_markers(text, label_raw)
            if removed and compare_key(stripped) != key:
                key_fn = compare_key(stripped)
                if levenshtein(key_fn, label_key) < levenshtein(key, label_key):
                    footnotes = max(footnotes, removed)
                    key = key_fn
        readings[name] = key
        evidence[f"cer_{name}"] = round(cer(key, label_key), 4)
        evidence[f"{name}_exact"] = key == label_key
    evidence["footnote_markers_stripped"] = footnotes
    if not readings:
        return Decision(False, "no_ocr_evidence", None, evidence)
    exact = [name for name, key in readings.items() if key == label_key]
    if exact == ["layer"] and "tesseract" in readings and evidence["cer_tesseract"] > MAX_LOCATE_CER:
        # the layer is text, not the image: a crop Tesseract cannot read near the label is not shown to hold it
        return Decision(False, "image_unconfirmed", None, evidence)
    if exact:
        tier = "both_exact" if len(exact) == 2 else f"{exact[0]}_exact"
        others = [key for name, key in readings.items() if name not in exact]
        if others and edge_insertion(label_key, others[0]):
            # the other reading sees letters beyond the span's ends: the crop holds print the label lacks
            evidence["edge_insertions"] = 1
            return Decision(False, "other_reading_sees_more", None, evidence)
        return Decision(True, "accepted", tier, evidence)
    if len(readings) == 2 and all(evidence[f"cer_{n}"] <= MAX_CONSENSUS_CER for n in readings):
        ok, detail = consensus(label_key, [readings["layer"], readings["tesseract"]])
        evidence.update(detail)
        if ok:
            return Decision(True, "accepted", "char_consensus", evidence)
        return Decision(False, "ocr_disagrees_with_olb", None, evidence)
    return Decision(False, "ocr_disagrees_with_olb" if len(readings) == 2 else "single_reading_not_exact", None, evidence)


# --- held-out units ---------------------------------------------------------------------------------------------


class ForbiddenInputError(SystemExit):
    pass


def refuse_forbidden_path(path: Path | str, forbidden: Sequence[Path] = FORBIDDEN_INPUT_DIRS) -> Path:
    """Refuse an input path under heocr-eval's test-unit folder (resolved, so symlinks and ``..`` do not escape)."""

    resolved = Path(path).expanduser().resolve()
    for root in forbidden:
        root = Path(root).expanduser().resolve()
        if resolved == root or root in resolved.parents:
            raise ForbiddenInputError(f"{path}: under {root}, which holds eval test units; refusing to read it")
    return resolved



def load_split(path: Path, expected_sha256: str | None) -> tuple[dict[str, str], str]:
    content = path.read_bytes()
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 and digest != expected_sha256:
        raise SystemExit(f"{path}: sha256 {digest} is not the pinned {expected_sha256}")
    data = json.loads(content)
    status = {}
    for part in ("test", "dev", "non_eval"):
        for unit in data.get(part) or []:
            uid = unit["unit_id"]
            if uid in status:
                raise SystemExit(f"{path}: {uid} is in two parts")
            status[uid] = part
    return status, digest


def training_registry(registry: Any = None) -> Any:
    """The packaged eval-reserved registry, which must govern ``reshumot_scanned`` (heocr-eval's pmod_unit_split_v2
    puts every enumerated scanned booklet in it: test and dev as eval, the rest non_eval). Fails closed before the
    sync: without it, no scanned booklet is known to be open."""

    from hocrgen.split.eval_reserved import packaged_registry

    registry = registry or packaged_registry()
    if not registry.governs(SOURCE_ID):
        raise SystemExit(f"the eval-reserved registry ({registry.split_file.name}) does not govern {SOURCE_ID}; "
                         "sync heocr-eval's pmod_unit_split_v2 first")
    return registry


UNIT_PREFIX = "reshumot_scanned:"   # unit ids agreed with heocr-eval: reshumot_scanned:<series>_<number>
PAGE_PREFIX = "reshumot_scanned_"   # page ids: reshumot_scanned_<series>_<number>__p0001


def unit_id(series: str, number: int | str) -> str:
    return f"{UNIT_PREFIX}{series}_{int(str(number))}"


def booklet_slug(series: str, number: int | str) -> str:
    """The booklet's directory and record id. Never the bare ``<series>_<n>``, which is a born-digital P-mod id."""

    return f"{PAGE_PREFIX}{series}_{int(str(number))}"


def page_id(series: str, number: int | str, page: int) -> str:
    return f"{booklet_slug(series, number)}__p{page:04d}"


# --- the eval 6-gram rule ----------------------------------------------------------------------------------------

NGRAM_N = 6
HEB_WORD = re.compile(r"[א-ת]+")


def word_ngrams(text: str, n: int = NGRAM_N) -> set[tuple[str, ...]]:
    words = HEB_WORD.findall(text)
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def eval_ngram_pool(tasks: Path, pmod_split: Path) -> tuple[set[tuple[str, ...]], dict[str, Any]]:
    """Word 6-grams of the P-mod v1 eval booklets' committed text and of the wave-1 pages (heocr-eval's
    ``ngram_overlap.py`` rule, logical order). Reads only the tranche snapshot's text files."""

    text_dir = tasks / "real-source-mapping/intermediates/e2d3e/tranche/e2d3e_real_tranche_v5/sources/reshumot_born_digital/snapshot/text"
    wave1 = json.loads((tasks / "eval-domains/capture/wave1/wave1_manifest.json").read_text(encoding="utf-8"))["pages"]
    split = json.loads(pmod_split.read_text(encoding="utf-8"))
    eval_units = set()
    for key, value in split.items():
        if isinstance(value, dict) and "eval" in value:
            eval_units |= {u for u in value["eval"] if isinstance(u, str)} | {u.get("unit_id") for u in value["eval"] if isinstance(u, dict)}
    pool: set[tuple[str, ...]] = set()
    counts = Counter()
    for page in wave1:
        path = text_dir / f"{page['entry_id']}.txt"
        if path.is_file():
            pool |= word_ngrams(path.read_text(encoding="utf-8"))
            counts["wave1_pages"] += 1
    for path in sorted(text_dir.glob("*.txt")):
        match = re.match(r"^(kovetz_hatakanot|sefer_hachukim)_(\d+)__p\d+$", path.stem)
        if match and unit_id(match.group(1), match.group(2)) in eval_units:
            pool |= word_ngrams(path.read_text(encoding="utf-8"))
            counts["pmod_eval_pages"] += 1
    return pool, {"rule": "drop a line sharing any word 6-gram (Hebrew-letter words, logical order) with the targets",
                  "targets": {"wave1": str(tasks / "eval-domains/capture/wave1/wave1_manifest.json"),
                              "pmod_v1_eval_booklets": str(pmod_split), "text_dir": str(text_dir)},
                  "pages_read": dict(counts), "ngrams": len(pool), "eval_units": len(eval_units)}


# --- network: Wikisource ------------------------------------------------------------------------------------------

_last_request: dict[str, float] = {}
THROTTLE_FILE: list[Path] = []  # set by capture: a gap file shared by every capture process on this cache


def _throttle(host: str, gap: float) -> None:  # pragma: no cover - network
    """At most one request per ``gap`` seconds to ``host``, across processes when a shared gap file is set."""

    if not THROTTLE_FILE:
        wait = _last_request.get(host, 0.0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        _last_request[host] = time.time()
        return
    import fcntl

    path = THROTTLE_FILE[0]
    with path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        state = json.loads(handle.read() or "{}")
        wait = state.get(host, 0.0) + gap - time.time()
        if wait > 0:
            time.sleep(wait)
        state[host] = time.time()
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(state))
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_UN)


def _request(url: str, *, data: bytes | None = None, headers: Mapping[str, str] | None = None, gap: float,
             tries: int = 4) -> bytes:  # pragma: no cover - network
    host = urllib.parse.urlsplit(url).hostname or ""
    for attempt in range(tries):
        _throttle(host, gap)
        req = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})},
                                     method="POST" if data else "GET")
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 401, 403, 404, 473):
                raise
            print(f"retry {attempt + 1}: HTTP {exc.code} {url[-40:]}", file=sys.stderr, flush=True)
            time.sleep(30 * 2 ** attempt)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            print(f"retry {attempt + 1}: {repr(exc)[:120]} {url[-40:]}", file=sys.stderr, flush=True)
            time.sleep(30 * 2 ** attempt)
    raise RuntimeError(f"gave up on {url[:120]}")


def olb_fetch(titles: Sequence[str], out: Path, *, batch: int = 20, log=print) -> dict[str, int]:  # pragma: no cover
    """Fetch each title's current revision (content, revision id, timestamp, sha1) into ``out/pages.jsonl.gz``."""

    out.mkdir(parents=True, exist_ok=True)
    path = out / "pages.jsonl.gz"
    have: dict[str, dict] = {}
    if path.is_file():
        for line in gzip.open(path, "rt", encoding="utf-8"):
            row = json.loads(line)
            have[row["title"]] = row
    todo = [t for t in titles if t not in have]
    counts = Counter()
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        params = {"action": "query", "prop": "revisions", "rvprop": "ids|timestamp|content|sha1", "rvslots": "main",
                  "titles": "|".join(chunk), "format": "json", "formatversion": "2", "maxlag": "5"}
        body = urllib.parse.urlencode(params).encode()  # POST: 50 Hebrew titles overflow a GET URL
        answer = json.loads(_request(WS_API, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, gap=WS_GAP_S))
        if "error" in answer:
            raise SystemExit(f"olb-fetch: API error {answer['error'].get('code')}")
        counts["requests"] += 1
        for page in answer.get("query", {}).get("pages", []):
            if page.get("missing") or not page.get("revisions"):
                counts["missing"] += 1
                continue
            rev = page["revisions"][0]
            content = rev["slots"]["main"]["content"]
            have[page["title"]] = {"title": page["title"], "pageid": page["pageid"], "revision_id": rev["revid"],
                                   "timestamp": rev["timestamp"], "sha1": rev.get("sha1"), "content": content,
                                   "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                                   "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            counts["pages"] += 1
        if counts["requests"] % 10 == 0:
            log(f"olb-fetch: {len(have)} pages", flush=True)
            _write_pages(path, have)
    _write_pages(path, have)
    return dict(counts)


def _write_pages(path: Path, pages: Mapping[str, dict]) -> None:  # pragma: no cover - network helper
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as handle:
        for title in sorted(pages):
            handle.write(json.dumps(pages[title], ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_olb_pages(olb_dir: Path) -> dict[str, dict]:
    return {row["title"]: row for row in (json.loads(line) for line in gzip.open(olb_dir / "pages.jsonl.gz", "rt", encoding="utf-8"))}


def olb_index(olb_dir: Path) -> dict[str, Any]:
    pages = load_olb_pages(olb_dir)
    index = []
    stats = Counter()
    for title, row in sorted(pages.items()):
        page = parse_olb_page(title, row["content"], revision_id=row["revision_id"], timestamp=row["timestamp"])
        if page.content_sha256 != row["content_sha256"]:
            raise SystemExit(f"{title}: content sha256 changed")
        stats[f"kind:{page.kind}"] += 1
        stats["blocks"] += len(page.blocks)
        stats["notes_stripped"] += page.notes_stripped
        stats["replaced_law"] += page.replaced_law
        stats["unknown_template_pages"] += bool(page.unknown_templates)
        index.append({"title": title, "revision_id": page.revision_id, "timestamp": page.timestamp,
                      "content_sha256": page.content_sha256, "kind": page.kind, "replaced_law": page.replaced_law,
                      "citations": [asdict(c) for c in page.citations], "blocks": len(page.blocks),
                      "unknown_templates": page.unknown_templates})
    doc = {"schema": "olb_index.v1", "pages": index, "stats": dict(stats)}
    (olb_dir / "olb_index.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return doc


# --- plan ---------------------------------------------------------------------------------------------------------


def norm_title(title: str) -> str:
    """A law title without its year suffix, quotes, punctuation and spacing differences (for DocSummary matching)."""

    t = re.sub(r"<[^>]+>", " ", html.unescape(title or ""))
    t = t.translate(LABEL_FOLD_TABLE)
    t = re.sub(r",?\s*ה?ת[שר][א-ת\"']{1,4}\s*-\s*\d{4}.*$", "", t)
    t = re.sub(r"[\"'.,]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def booklet_titles(doc_summary: str | None) -> list[str]:
    return [norm_title(x) for x in re.split(r"<br\s*/?>", doc_summary or "") if norm_title(x)]


def booklet_page_ranges(units: Sequence[Mapping[str, Any]], *, unnumbered: int = 1) -> dict[str, tuple[int, int, int]]:
    """Estimated printed page range per booklet, and how many booklets of its year precede it. Volumes are paginated
    per Hebrew year, so a booklet starts after the pages of the lower-numbered booklets of its year index (API
    ``Pages``, less ``unnumbered`` unnumbered cover pages each). The estimate drifts with the position in the year."""

    by_year: dict[tuple[str, int], dict[int, int]] = defaultdict(dict)
    for u in units:
        pages = u.get("pages") or u.get("pages_api") or 0
        key = (u["series"], int(u["booklet_year_index"]))
        by_year[key][int(u["number"])] = max(by_year[key].get(int(u["number"]), 0), int(pages))
    ranges = {}
    for (series, _), booklets in by_year.items():
        start = 1
        for position, number in enumerate(sorted(booklets)):
            pages = max(1, booklets[number] - unnumbered)
            ranges[unit_id(series, number)] = (start, start + pages - 1, position)
            start += pages
    return ranges


def plan(units_path: Path, split_path: Path, split_sha256: str | None, olb_dir: Path, *, slack: int = 12,
         drift_per_booklet: float = 1.5) -> dict[str, Any]:
    """OLB candidates per non_eval booklet. An OLB page is a candidate through a citation (not a "חוק קודם" one) in
    the booklet's series and Hebrew year that either names one of the booklet's DocSummary titles (ספר החוקים), or
    cites a page inside the booklet's estimated range, widened by ``slack + drift_per_booklet x position``."""

    for path in (units_path, split_path, olb_dir):
        refuse_forbidden_path(path)
    units_doc = json.loads(units_path.read_text(encoding="utf-8"))
    units = units_doc["units"]
    status, digest = load_split(split_path, split_sha256)
    index = json.loads((olb_dir / "olb_index.json").read_text(encoding="utf-8"))
    ranges = booklet_page_ranges(units)
    by_cite: dict[tuple[str, int], list[tuple[dict, dict]]] = defaultdict(list)
    for page in index["pages"]:
        principal = next((c["name"] for c in page["citations"] if c["role"] in ("principal", "new_law")), "")
        for c in page["citations"]:
            # a "חוק קודם" citation is the replaced law, whose text the page does not hold (the version check)
            if c["role"] != "prior_law" and c["series"] in SERIES.values() and c["hebrew_year"]:
                by_cite[(c["series"], c["hebrew_year"])].append((page, {**c, "principal_name": principal}))
    booklets: dict[str, dict[str, Any]] = {}
    for u in units:
        uid = unit_id(u["series"], u["number"])
        part = status.get(uid, "unassigned")
        b = booklets.setdefault(uid, {"unit_id": uid, "series": u["series"], "number": int(u["number"]),
                                      "hebrew_year": u["hebrew_year"], "year": u["year"], "split_status": part,
                                      "files": [], "titles": [], "estimated_pages": ranges.get(uid), "olb_candidates": []})
        b["files"].append({k: u.get(k) for k in ("booklet_label", "url", "file_token", "pages", "pages_api", "creation_date", "date")})
        b["titles"] = sorted(set(b["titles"]) | set(booklet_titles(u.get("doc_summary"))))
    counts = Counter()
    for uid, b in booklets.items():
        if b["split_status"] != "non_eval":
            counts[f"skipped_{b['split_status']}"] += 1
            b.pop("files")
            b.pop("titles")
            continue
        lo, hi, position = b["estimated_pages"] or (0, -1, 0)
        window = slack + drift_per_booklet * position
        titles = set(b["titles"])
        seen = set()
        for page, c in by_cite.get((b["series"], b["hebrew_year"]), []):
            if page["title"] in seen:
                continue
            name, principal = norm_title(c["name"]), norm_title(c["principal_name"])
            by_title = bool(titles) and (name in titles or (c["role"] == "amendment" and any(
                t.startswith(principal) and "תיקון" in t for t in titles if principal)))
            by_page = c["page"] is not None and lo - window <= c["page"] <= hi + window
            if by_title or by_page:
                seen.add(page["title"])
                b["olb_candidates"].append({"title": page["title"], "revision_id": page["revision_id"], "role": c["role"],
                                            "cited_page": c["page"], "by_title": by_title, "by_page": by_page,
                                            "inside_estimate": c["page"] is not None and lo <= c["page"] <= hi})
        # capture priority: instruments first published here (principal / new-law citations) that the tight window
        # (slack + 0.5 x position) or the DocSummary titles place in this booklet
        tight = slack + 0.5 * position
        b["priority"] = sum(1 for c in b["olb_candidates"] if c["role"] in ("principal", "new_law") and (
            c["by_title"] or (c["cited_page"] is not None and lo - tight <= c["cited_page"] <= hi + tight)))
        counts["non_eval_booklets"] += 1
        counts["non_eval_with_candidates"] += bool(b["olb_candidates"])
        counts["non_eval_with_priority"] += bool(b["priority"])
    return {"schema": "olb_reshumot_plan.v1", "units": str(units_path), "units_sha256": hashlib.sha256(units_path.read_bytes()).hexdigest(),
            "split": str(split_path), "split_sha256": digest, "olb_index_sha256": hashlib.sha256((olb_dir / "olb_index.json").read_bytes()).hexdigest(),
            "page_slack": slack, "drift_per_booklet": drift_per_booklet, "counts": dict(counts), "booklets": booklets}


# --- network: gov.il capture ----------------------------------------------------------------------------------------


def document_url(url: str) -> str:
    head, token = url.rsplit("/", 1)
    return head + "/" + urllib.parse.quote(urllib.parse.unquote(token), safe="~")


def capture(plan_doc: Mapping[str, Any], cache: Path, *, series: Sequence[str], only_candidates: bool, limit: int | None,
            min_priority: int = 0, shard: tuple[int, int] | None = None, log=print) -> dict[str, int]:  # pragma: no cover - network
    """Fetch the planned non_eval booklets' PDFs (earliest-listed file per booklet) into ``cache/pdf``."""

    refuse_forbidden_path(cache)
    THROTTLE_FILE[:] = [cache / "throttle.json"]
    pdf_dir = cache / "pdf"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    log_path = cache / "capture_log.jsonl"
    counts = Counter()
    todo = [b for b in plan_doc["booklets"].values() if b["split_status"] == "non_eval" and b["series"] in series
            and ((b.get("priority") if min_priority else b["olb_candidates"]) or not only_candidates)
            and b.get("priority", 0) >= min_priority]
    todo.sort(key=lambda b: (series.index(b["series"]), -b.get("priority", 0), -len(b["olb_candidates"]), b["number"]))
    if shard:  # (i, n): this process takes every n-th booklet of the ordered list; all shards share the throttle
        todo = todo[:limit][shard[0]::shard[1]]
        limit = None
    logged = {}
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "sha256" in r:
                logged[r["unit_id"]] = r["sha256"]
    registry = training_registry()
    for b in todo[:limit]:
        status = registry.status(SOURCE_ID, b["unit_id"])
        if b["split_status"] != "non_eval" or status is None or status.value != "non_eval":  # never fetch a held-out booklet
            raise SystemExit(f"{b['unit_id']} is {b['split_status']} / {status}; refusing to fetch it")
        target = pdf_dir / f"{booklet_slug(b['series'], b['number'])}.pdf"
        if target.is_file() and logged.get(b["unit_id"]) == hashlib.sha256(target.read_bytes()).hexdigest():
            counts["cached"] += 1
            continue
        files = sorted(b["files"], key=lambda f: (f.get("creation_date") or "", f.get("file_token") or ""))
        content = None
        for f in files:
            try:
                content = _request(document_url(f["url"]), headers={"Referer": "https://www.gov.il/"}, gap=GOV_GAP_S)
            except Exception as exc:  # noqa: BLE001 - recorded
                with log_path.open("a") as handle:
                    handle.write(json.dumps({"unit_id": b["unit_id"], "error": repr(exc)[:200]}) + "\n")
                counts["failed"] += 1
                continue
            if content.startswith(b"%PDF"):
                chosen = f
                break
            content = None
        if content is None:
            continue
        tmp = target.with_suffix(".part")
        tmp.write_bytes(content)
        tmp.replace(target)
        with log_path.open("a") as handle:
            handle.write(json.dumps({"unit_id": b["unit_id"], "file_token": chosen["file_token"], "url": chosen["url"],
                                     "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
                                     "at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, ensure_ascii=False) + "\n")
        counts["fetched"] += 1
        if counts["fetched"] % 25 == 0:
            log(f"capture: {counts['fetched']} fetched")
    return dict(counts)


# --- PDF pages: scan image, OCR-layer lines, Tesseract readings ---------------------------------------------------


@dataclass
class PageLine:
    """A located printed line: its box on the scan (pixels) and the readings that locate and check it."""

    index: int
    box: list[int]                  # x0, y0, x1, y1 in scan pixels
    layer: str | None               # publisher OCR text, words in right-to-left order (None: no text layer)
    locate_text: str                # the reading used to locate the line in OLB
    tesseract: str | None = None
    touching: bool = False          # set by ink_fit_vertical: no blank row between this line and a neighbour


def _run(args: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess:  # pragma: no cover - poppler/tesseract
    import os

    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}  # one thread per Tesseract: the build parallelises over booklets
    return subprocess.run(list(args), check=True, capture_output=True, env=env, **kwargs)


def pdf_info(path: Path) -> dict[str, str]:  # pragma: no cover - poppler
    out = _run(["pdfinfo", str(path)]).stdout.decode("utf-8", "replace")
    return {k.strip(): v.strip() for k, v in (line.split(":", 1) for line in out.splitlines() if ":" in line)}


def pdfimages_rows(path: Path) -> list[dict[str, Any]]:  # pragma: no cover - poppler
    out = _run(["pdfimages", "-list", str(path)]).stdout.decode("utf-8", "replace").splitlines()
    rows = []
    for line in out[2:]:
        f = line.split()
        if len(f) < 14:
            continue
        rows.append({"page": int(f[0]), "num": int(f[1]), "type": f[2], "width": int(f[3]), "height": int(f[4]),
                     "color": f[5], "bpc": f[7], "enc": f[8], "x_ppi": int(f[12]) if f[12].isdigit() else 0,
                     "y_ppi": int(f[13]) if f[13].isdigit() else 0})
    return rows


def page_scan_row(rows: Sequence[Mapping[str, Any]], page: int) -> Mapping[str, Any] | None:
    """The page's scan image: the largest ``image`` (not ``smask``) row, skipping low-resolution JPX overlays."""

    images = [r for r in rows if r["page"] == page and r["type"] == "image" and r["enc"] != "jpx"]
    return max(images, key=lambda r: r["width"] * r["height"]) if images else None


def scan_covers_page(row: Mapping[str, Any], page_w: float, page_h: float, *, min_share: float = 0.9) -> bool:
    """True when the image, at its stated resolution, covers the page (one full-page scan, not a strip of one)."""

    if not (row.get("x_ppi") and row.get("y_ppi") and page_w and page_h):
        return False
    placed_w, placed_h = row["width"] * 72.0 / row["x_ppi"], row["height"] * 72.0 / row["y_ppi"]
    return placed_w >= min_share * page_w and placed_h >= min_share * page_h


def render_page(path: Path, page: int, dpi: int, work: Path) -> Image.Image:  # pragma: no cover - poppler
    """The whole page rendered by pdftoppm (grey), for pages stored as several image strips."""

    prefix = work / f"r{page:04d}"
    _run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(int(dpi)), "-gray", "-png", str(path), str(prefix)])
    (file,) = sorted(work.glob(f"r{page:04d}*.png"))
    with Image.open(file) as im:
        image = im.convert("L")
    file.unlink()
    return image


def extract_scan(path: Path, page: int, row: Mapping[str, Any], work: Path) -> Image.Image:  # pragma: no cover - poppler
    prefix = work / f"p{page:04d}"
    _run(["pdfimages", "-f", str(page), "-l", str(page), "-png", str(path), str(prefix)])
    files = sorted(work.glob(f"p{page:04d}-*.png"))
    best = None
    for f in files:
        with Image.open(f) as im:
            if im.size == (row["width"], row["height"]):
                best = im.convert("L")
                break
    for f in files:
        f.unlink()
    if best is None:
        raise RuntimeError(f"page {page}: scan image not extracted")
    histogram = best.histogram()
    if sum(histogram[:128]) > sum(histogram[128:]):  # inverted (BlackIs1 / Decode) bitonal data
        best = Image.eval(best, lambda v: 255 - v)
    return best


def bbox_layout(path: Path) -> dict[int, dict[str, Any]]:  # pragma: no cover - poppler
    """``pdftotext -bbox-layout``: per page, its size and its OCR-layer lines (word boxes, in PDF points)."""

    from defusedxml import ElementTree

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "bbox.html"
        _run(["pdftotext", "-bbox-layout", "-enc", "UTF-8", str(path), str(out)])
        tree = ElementTree.fromstring(out.read_bytes())
    pages: dict[int, dict[str, Any]] = {}
    ns = "{http://www.w3.org/1999/xhtml}"
    for number, page in enumerate(tree.iter(f"{ns}page"), 1):
        lines = []
        for line in page.iter(f"{ns}line"):
            words = [(float(w.get("xMin")), float(w.get("yMin")), float(w.get("xMax")), float(w.get("yMax")), (w.text or "").strip())
                     for w in line.iter(f"{ns}word")]
            words = [w for w in words if w[4]]
            if words:
                lines.append(words)
        pages[number] = {"width": float(page.get("width")), "height": float(page.get("height")), "lines": lines}
    return pages


FINALS = set("םןץףך")
VISUAL_TOKEN = re.compile(r"\d+(?:[.,/:]\d+)*|.", re.S)


def layer_is_visual(words: Iterable[str]) -> bool:
    """True when a layer stores each word's characters in visual (left-to-right) order, as Imagestore does: Hebrew
    final letters then sit at word starts instead of word ends (heocr-eval's ``reversed_store`` test)."""

    start = end = 0
    for word in words:
        letters = re.sub(r"[^א-ת]", "", word)
        if len(letters) > 1:
            start += letters[0] in FINALS
            end += letters[-1] in FINALS
    return start > end


def visual_to_logical(word: str) -> str:
    """One visually stored word in logical order: characters reversed, numbers (with their separators) kept whole."""

    return "".join(reversed(VISUAL_TOKEN.findall(word)))


def layer_lines(layer_page: Mapping[str, Any], scale_x: float, scale_y: float) -> list[PageLine]:
    """OCR-layer lines as boxes in scan pixels. Words are put in right-to-left order by their boxes, and a layer that
    stores characters in visual order (``layer_is_visual``) is turned to logical order word by word."""

    visual = layer_is_visual(w[4] for words in layer_page["lines"] for w in words)
    out = []
    for i, words in enumerate(layer_page["lines"]):
        ordered = sorted(words, key=lambda w: -w[2])
        text = " ".join(visual_to_logical(w[4]) if visual else w[4] for w in ordered)
        box = [int(min(w[0] for w in words) * scale_x), int(min(w[1] for w in words) * scale_y),
               int(max(w[2] for w in words) * scale_x + 0.999), int(max(w[3] for w in words) * scale_y + 0.999)]
        out.append(PageLine(index=i, box=box, layer=text, locate_text=text))
    return merge_row_fragments(out)


def merge_row_fragments(lines: Sequence[PageLine], *, max_gap: float = 1.2, min_overlap: float = 0.6) -> list[PageLine]:
    """Join OCR lines that are fragments of one printed row (vertical overlap of at least ``min_overlap`` of the
    lower box, horizontal gap at most ``max_gap`` line heights), right fragment first. A margin heading, set off by
    the column gap, stays its own line. The merged line keeps the lowest index."""

    items = sorted(lines, key=lambda l: -l.box[2])
    merged: list[PageLine] = []
    for line in items:
        for group in merged:
            gx0, gy0, gx1, gy1 = group.box
            x0, y0, x1, y1 = line.box
            overlap = min(gy1, y1) - max(gy0, y0)
            height = max(gy1 - gy0, y1 - y0, 1)
            gap = gx0 - x1  # the new fragment lies left of the group (items run right to left)
            if overlap >= min_overlap * min(gy1 - gy0, y1 - y0) and -0.5 * height <= gap <= max_gap * height:
                group.box = [min(gx0, x0), min(gy0, y0), max(gx1, x1), max(gy1, y1)]
                group.layer = f"{group.layer} {line.layer}" if line.layer is not None else group.layer
                group.locate_text = f"{group.locate_text} {line.locate_text}"
                group.index = min(group.index, line.index)
                group.touching = group.touching or line.touching
                break
        else:
            merged.append(PageLine(index=line.index, box=list(line.box), layer=line.layer, locate_text=line.locate_text,
                                   touching=line.touching))
    return sorted(merged, key=lambda l: l.index)


def tesseract_page_lines(image: Image.Image, work: Path, *, psm: int = 4) -> list[PageLine]:  # pragma: no cover
    """Stock Tesseract (``heb``) line boxes and text, for pages without a text layer."""

    src = work / "page.png"
    image.save(src)
    out = _run(["tesseract", str(src), "stdout", "-l", "heb", "--psm", str(psm), "tsv"]).stdout.decode("utf-8", "replace")
    groups: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = defaultdict(list)
    for row in out.splitlines()[1:]:
        f = row.split("\t")
        if len(f) < 12 or f[0] != "5" or not f[11].strip():
            continue
        left, top, width, height = (int(v) for v in f[6:10])
        groups[(int(f[2]), int(f[3]), int(f[4]))].append((left, top, left + width, top + height, f[11].strip()))
    lines = []
    for i, key in enumerate(sorted(groups)):
        words = groups[key]
        text = " ".join(w[4] for w in words)  # Tesseract writes words in logical order
        box = [min(w[0] for w in words), min(w[1] for w in words), max(w[2] for w in words), max(w[3] for w in words)]
        lines.append(PageLine(index=i, box=box, layer=None, locate_text=text))
    return lines


def column_ink(image: Image.Image, x0: int, x1: int, y0: int, y1: int) -> list[bool]:
    """Per column of ``image[y0:y1, x0:x1]``: does it hold ink (a pixel darker than mid-grey)?"""

    if x1 <= x0 or y1 <= y0:
        return []
    strip = image.crop((x0, y0, x1, y1)).point(lambda v: 255 if v < 128 else 0)
    return [v > 0 for v in strip.resize((x1 - x0, 1), Image.Resampling.BOX).getdata()]


def row_ink(image: Image.Image, x0: int, x1: int, y0: int, y1: int) -> list[bool]:
    """Per row of ``image[y0:y1, x0:x1]``: does it hold ink?"""

    if x1 <= x0 or y1 <= y0:
        return []
    strip = image.crop((x0, y0, x1, y1)).point(lambda v: 255 if v < 128 else 0)
    return [v > 0 for v in strip.resize((1, y1 - y0), Image.Resampling.BOX).getdata()]


def ink_fit_vertical(image: Image.Image, line: PageLine, lines: Sequence[PageLine]) -> list[int]:
    """The line box moved to its ink band. OCR-layer boxes come from invisible text set in another font, so they sit
    lower than the print and stop short of it; the band is the run of inked rows through the box's centre (blank
    rows end it), searched from 0.7 line heights above the box to 0.3 below, never past a neighbour's centre."""

    x0, y0, x1, y1 = line.box
    h = max(1, y1 - y0)
    top, bottom = max(0, y0 - int(0.7 * h)), min(image.height, y1 + int(0.3 * h))
    top_by_neighbour = bottom_by_neighbour = False
    for other in lines:
        ox0, oy0, ox1, oy1 = other.box
        if other is line or ox1 <= x0 or ox0 >= x1:
            continue
        centre = (oy0 + oy1) // 2
        if centre < (y0 + y1) // 2:
            if centre > top:
                top, top_by_neighbour = centre, True
        elif centre < bottom:
            bottom, bottom_by_neighbour = centre, True
    line.touching = False
    ink = row_ink(image, x0, x1, top, bottom)
    if not ink:
        return list(line.box)
    mid = min(len(ink) - 1, max(0, (y0 + y1) // 2 - top))
    if not ink[mid]:  # the centre row is blank (between letters' strokes): start from the nearest inked row
        near = [i for i, v in enumerate(ink) if v and y0 - top <= i < y1 - top]
        if not near:
            return list(line.box)
        mid = min(near, key=lambda i: abs(i - mid))
    a = b = mid
    while a > 0 and ink[a - 1]:
        a -= 1
    while b < len(ink) - 1 and ink[b + 1]:
        b += 1
    if b - a + 1 < h * 0.4:  # a thin band (a rule, a speck): keep the layer's box
        return list(line.box)
    # the ink runs on into a neighbouring line (no blank row between them): the line cannot be cut cleanly
    line.touching = (a == 0 and top_by_neighbour) or (b == len(ink) - 1 and bottom_by_neighbour)
    return [x0, top + a, x1, top + b + 1]


def ink_extend(image: Image.Image, line: PageLine, lines: Sequence[PageLine], *, gap_frac: float = 0.4,
               limit_frac: float = 2.0) -> list[int]:
    """The line box widened to the ink that continues past its left and right edges (OCR-layer word boxes can stop
    short of a line's first or last letter), up to the first blank gap of ``gap_frac`` line heights, never into
    another line's box and at most ``limit_frac`` line heights."""

    x0, y0, x1, y1 = line.box
    h = max(1, y1 - y0)
    core_top, core_bottom = y0 + h // 4, y1 - h // 4  # the x-height band: no ascenders or descenders of neighbours
    gap, limit = max(2, int(gap_frac * h)), int(limit_frac * h)
    right_stop, left_stop = min(image.width, x1 + limit), max(0, x0 - limit)
    for other in lines:
        ox0, oy0, ox1, oy1 = other.box
        if other is line or oy1 <= core_top or oy0 >= core_bottom:
            continue
        if ox0 >= x1:
            right_stop = min(right_stop, ox0)
        elif ox1 <= x0:
            left_stop = max(left_stop, ox1)
    new_x1 = x1
    run = 0
    for i, ink in enumerate(column_ink(image, x1, right_stop, core_top, core_bottom)):
        run = 0 if ink else run + 1
        if ink:
            new_x1 = x1 + i + 1
        if run >= gap:
            break
    new_x0 = x0
    run = 0
    for i, ink in enumerate(reversed(column_ink(image, left_stop, x0, core_top, core_bottom))):
        run = 0 if ink else run + 1
        if ink:
            new_x0 = x0 - i - 1
        if run >= gap:
            break
    return [new_x0, y0, new_x1, y1]


def crop_box(line: PageLine, lines: Sequence[PageLine], size: tuple[int, int]) -> list[int]:
    """The line box padded by ``CROP_PAD_FRAC`` of its height, clipped so it does not reach into another line."""

    x0, y0, x1, y1 = line.box
    height = max(1, y1 - y0)
    pad_y, pad_x = int(height * CROP_PAD_FRAC), int(height * 0.4)
    top, bottom, left, right = max(0, y0 - pad_y), min(size[1], y1 + pad_y), max(0, x0 - pad_x), min(size[0], x1 + pad_x)
    for other in lines:
        if other is line:
            continue
        ox0, oy0, ox1, oy1 = other.box
        if ox1 > x0 and ox0 < x1:  # same column: clip vertically
            if oy1 <= y0 + height * 0.3:  # the line above: stop half way (its descenders, this line's ascenders)
                top = max(top, min(y0, (oy1 + y0) // 2))
            elif oy0 >= y1 - height * 0.3:
                bottom = min(bottom, max(y1, (y1 + oy0) // 2))
        if oy1 > y0 + height * 0.3 and oy0 < y1 - height * 0.3:  # same row: clip horizontally
            if ox1 <= x0:
                left = max(left, min(x0, ox1 + 1))
            elif ox0 >= x1:
                right = min(right, max(x1, ox0 - 1))
    return [left, top, right, bottom]


def tesseract_lines(crops: Sequence[Image.Image], work: Path) -> list[str]:  # pragma: no cover - tesseract
    """Stock Tesseract ``heb`` at ``--psm 7`` on each line crop (one process per page, a list of images)."""

    if not crops:
        return []
    paths = []
    for i, crop in enumerate(crops):
        padded = Image.new("L", (crop.width + 24, crop.height + 24), 255)
        padded.paste(crop, (12, 12))
        path = work / f"line_{i:04d}.png"
        padded.save(path)
        paths.append(str(path))
    listing = work / "lines.txt"
    listing.write_text("\n".join(paths) + "\n", encoding="utf-8")
    out = _run(["tesseract", str(listing), "stdout", "-l", "heb", "--psm", "7"]).stdout.decode("utf-8", "replace")
    texts = [re.sub(r"\s+", " ", t).strip() for t in out.split("\f")]
    for p in paths:
        Path(p).unlink()
    texts += [""] * (len(crops) - len(texts))
    return texts[:len(crops)]


def tesseract_version() -> str:  # pragma: no cover - tesseract
    return _run(["tesseract", "--version"]).stdout.decode("utf-8", "replace").splitlines()[0]


def poppler_version() -> str:  # pragma: no cover - poppler
    return _run(["pdftotext", "-v"]).stderr.decode("utf-8", "replace").splitlines()[0]


# --- one booklet ----------------------------------------------------------------------------------------------------


def label_ok(raw: str) -> str | None:
    """Why a located OLB span cannot be a label, or ``None``."""

    if is_pointed(raw):
        return "pointed"
    letters = len(LETTER_OR_DIGIT.findall(raw))
    if letters < MIN_LINE_CHARS or len(raw.split()) < MIN_LINE_WORDS:
        return "too_short"
    if any(unicodedata.category(c) in ("Co", "Cn", "Cs") or c == "�" for c in raw):
        return "bad_code_point"
    return None


def booklet_job(job: Mapping[str, Any]) -> dict[str, Any]:  # pragma: no cover - poppler/tesseract (fixture-free)
    """Locate, check and crop the lines of one non_eval booklet. Returns candidate rows and drop counts."""

    pdf = refuse_forbidden_path(job["pdf"])
    staging = Path(job["staging"])
    paragraphs = [make_paragraph(p["title"], Block(**b)) for p in job["olb_pages"] for b in p["blocks"]]
    paragraphs = ParagraphIndex([p for p in paragraphs if len(p.key) >= 6])
    drops: Counter = Counter()
    evidence_tiers: Counter = Counter()
    rows: list[dict[str, Any]] = []
    facts: dict[str, Any] = {"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest()}
    try:
        info = pdf_info(pdf)
        image_rows = pdfimages_rows(pdf)
        layout = bbox_layout(pdf)
    except Exception as exc:  # noqa: BLE001 - recorded
        return {"unit_id": job["unit_id"], "rows": [], "drops": {"pdf_unreadable": 1}, "facts": {**facts, "error": repr(exc)[:200]}}
    facts.update({"producer": info.get("Producer"), "creator": info.get("Creator"), "pages": int(info.get("Pages", "0") or 0)})
    if not image_rows:
        drops["booklet_not_scanned"] += facts["pages"]
        return {"unit_id": job["unit_id"], "rows": [], "drops": dict(drops), "facts": facts}
    staging.mkdir(parents=True, exist_ok=True)
    debug: list[dict[str, Any]] = []
    candidates = 0
    page_sources: Counter = Counter()
    pages_with_layer = 0
    ocr_kinds: Counter = Counter()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for page_no in range(1, facts["pages"] + 1):
            row = page_scan_row(image_rows, page_no)
            if row is None:
                drops["page_without_scan_image"] += 1
                continue
            lay = layout.get(page_no) or {"lines": [], "width": 0, "height": 0}
            if scan_covers_page(row, lay.get("width") or 0, lay.get("height") or 0):
                image = extract_scan(pdf, page_no, row, work)
                page_sources["pdfimages"] += 1
            else:  # the page is several image strips: render it whole at the strips' resolution
                image = render_page(pdf, page_no, row.get("x_ppi") or SCAN_DPI.get(job["series"], 300), work)
                page_sources["pdftoppm_composite"] += 1
            if lay["lines"] and lay["width"]:
                lines = layer_lines(lay, image.width / lay["width"], image.height / lay["height"])
                pages_with_layer += 1
                ocr_kinds["layer"] += 1
            else:
                lines = tesseract_page_lines(image, work)
                ocr_kinds["tesseract_page"] += 1
            # fit every box to the ink (layer boxes come from invisible text in another font: they sit low and stop
            # short of a line's ends), then join the row fragments the true gaps reveal
            fitted = [ink_fit_vertical(image, line, lines) for line in lines]
            for line, box in zip(lines, fitted):
                line.box = box
            extended = [ink_extend(image, line, lines) for line in lines]
            for line, box in zip(lines, extended):
                line.box = box
            lines = merge_row_fragments(lines, max_gap=0.9)
            heights = sorted(l.box[3] - l.box[1] for l in lines if l.box[3] > l.box[1])
            median_h = heights[len(heights) // 2] if heights else 0
            located = []
            for line in lines:
                h = line.box[3] - line.box[1]
                if median_h and h > 1.8 * median_h:
                    drops["merged_rows"] += 1
                    continue
                if line.touching:
                    drops["touches_neighbour_line"] += 1
                    continue
                spot = locate(line.locate_text, paragraphs)
                if spot is None:
                    drops["no_olb_span"] += 1
                    continue
                reason = label_ok(spot.raw_text)
                if reason:
                    drops[reason] += 1
                    continue
                located.append((line, spot))
            boxes = [crop_box(line, lines, image.size) for line, _ in located]
            min_h = max(10, int(0.5 * median_h)) if median_h else 10
            keep = [i for i, b in enumerate(boxes) if b[3] - b[1] >= min_h and b[2] - b[0] >= min_h]
            drops["degenerate_crop"] += len(boxes) - len(keep)
            located, boxes = [located[i] for i in keep], [boxes[i] for i in keep]
            crops = [image.crop(tuple(b)) for b in boxes]
            readings = tesseract_lines(crops, work)
            for (line, spot), box, crop, reading in zip(located, boxes, crops, readings):
                decision = accept_line(spot.raw_text, line.layer, reading)
                candidates += 1
                if job.get("dev_rule") == DEV_RULE:
                    # dev selection uses the publisher layer only: kept iff the layer equals OLB, whatever Tesseract
                    # reads (so dev is not filtered by the model family it will evaluate)
                    ev = decision.evidence
                    if ev.get("layer_exact"):
                        decision = Decision(True, "accepted", "both_exact" if ev.get("tesseract_exact") else "layer_exact", ev)
                    else:
                        decision = Decision(False, "dev_layer_not_exact", None, ev)
                if not decision.accepted:
                    drops[decision.reason] += 1
                    if job.get("debug"):  # operator debugging only; OCR text is never written to a set
                        debug.append({"page": page_no, "line": line.index, "reason": decision.reason, "olb": spot.raw_text,
                                      "layer": line.layer, "tesseract": reading, "evidence": decision.evidence})
                    continue
                if decision.evidence["footnote_markers_stripped"] and not job["keep_footnote_lines"]:
                    drops["footnote_marker_in_print"] += 1
                    continue
                evidence_tiers[decision.tier] += 1
                entry = page_id(job["series"], job["number"], page_no)
                lid = f"{entry}_l{line.index:03d}"
                path = staging / f"{lid}.png"
                crop.save(path)
                rows.append({
                    "id": lid, "entry_id": entry, "page": page_no, "line_index": line.index, "text": fold_label(strip_points(spot.raw_text)),
                    "olb_text": spot.raw_text, "olb_page_title": spot.paragraph.page_title,
                    "olb_block_index": spot.paragraph.block_index, "olb_block_kind": spot.paragraph.kind,
                    "olb_words": [spot.first_word, spot.last_word],
                    "tesseract_exact": bool(decision.evidence.get("tesseract_exact")),
                    "match_evidence": {"tier": decision.tier, **decision.evidence,
                                       "layer_source": job["layer_source"] if line.layer is not None else None,
                                       "locate_distance": spot.distance},
                    "bbox_image": line.box, "crop_box_image": box, "scan_size": list(image.size),
                    "scan_ppi": [row["x_ppi"], row["y_ppi"]], "scan_encoding": row["enc"],
                    "staged_image": str(path), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                })
    facts.update({"pages_with_text_layer": pages_with_layer, "line_sources": dict(ocr_kinds), "page_images": dict(page_sources)})
    facts["candidate_lines"] = candidates  # located lines with an OLB span that reached the per-line gate
    return {"unit_id": job["unit_id"], "rows": rows, "drops": dict(drops), "facts": facts, "tiers": dict(evidence_tiers),
            **({"debug": debug} if job.get("debug") else {})}


# --- build / verify -------------------------------------------------------------------------------------------------

DECADES = ("1948-59", "1960s", "1970s", "1980s", "1990s", "2000-mid2005")
DROP_DEFINITIONS = {
    "no_olb_span": "located line with no OLB word span within MAX_LOCATE_CER of its locating reading",
    "ocr_disagrees_with_olb": "both readings exist and neither equals the span nor do they confirm it character by character",
    "single_reading_not_exact": "only one reading exists (no text layer) and it does not equal the span",
    "image_unconfirmed": "only the layer equals the span and Tesseract's reading of the crop is beyond MAX_LOCATE_CER of it",
    "degenerate_crop": "the crop is under half the page's median line height (or 10 px) high or wide",
    "other_reading_sees_more": "one reading equals the span, but the other reads two or more characters (with a letter) beyond its ends",
    "footnote_marker_in_print": "the print adds a footnote marker the OLB text lacks (the label would miss a printed glyph)",
    "pointed": "the OLB span carries niqqud or cantillation",
    "too_short": f"fewer than {MIN_LINE_CHARS} letters or digits, or fewer than {MIN_LINE_WORDS} words",
    "merged_rows": "the located box is over 1.8 times the page's median line height (two printed rows)",
    "touches_neighbour_line": "no blank row separates the line's ink from a neighbouring line's, so no clean crop exists",
    "eval_ngram_overlap": "the label shares a word 6-gram with a P-mod v1 eval booklet or a wave-1 page",
    "capped": f"over --max-lines-per-booklet, by sha256 of the line id",
    "page_without_scan_image": "pages counted, not lines",
    "booklet_not_scanned": "pages of a PDF without a page image, counted in pages",
}


def midcentury_decade(year: int) -> str:
    return "1948-59" if year < 1960 else "2000-mid2005" if year >= 2000 else f"{year // 10 * 10}s"


def choose_dev(booklets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """One dev booklet per (series, decade) stratum of the non_eval booklets that give lines: the first by
    sha256(unit_id)."""

    strata: dict[str, list[str]] = defaultdict(list)
    for unit, b in booklets.items():
        if b.get("lines_candidate"):
            strata[f"{b['series']}|{midcentury_decade(int(b['year']))}"].append(unit)
    picks, ranking = {}, {}
    for stratum in sorted(strata):
        ranked = sorted(strata[stratum], key=lambda u: hashlib.sha256(u.encode()).hexdigest())
        ranking[stratum] = ranked
        picks[ranked[0]] = stratum
    return {"method": "per (series, midcentury decade) stratum of non_eval booklets giving at least one line, ranked by "
                      "sha256(unit_id) ascending: the first is dev; dev is never drawn from test, dev or unassigned units",
            "picks": picks, "ranking": ranking}


def build(args: argparse.Namespace, *, registry: Any = None) -> dict[str, Any]:  # pragma: no cover - operator run
    from hocrgen.split.eval_reserved import refuse_eval_reserved_training_input, registry_provenance, unit_status
    from hocrgen.tools.reshumot_lines import tier_a_flags

    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    for path in (args.out, args.plan, args.split, args.pmod_split, args.tasks, args.olb, args.cache):
        refuse_forbidden_path(path)
    plan_doc = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    split_status, split_digest = load_split(Path(args.split), args.split_sha256)
    if split_digest != plan_doc["split_sha256"]:
        raise SystemExit("the plan was made from another split file")
    registry = training_registry(registry)
    olb_dir = Path(args.olb)
    pages = load_olb_pages(olb_dir)
    booklets = {u: b for u, b in plan_doc["booklets"].items() if b["split_status"] == "non_eval" and b["olb_candidates"]
                and b["series"] in args.series}
    if args.only:
        booklets = {u: b for u, b in booklets.items() if u in set(args.only)}
    cache = Path(args.cache)
    logged = {}
    if (cache / "capture_log.jsonl").is_file():
        for line in (cache / "capture_log.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "sha256" in r:
                logged[r["unit_id"]] = r["sha256"]

    def captured(u: str, b: Mapping[str, Any]) -> bool:  # the file must be the one the capture log pins
        path = refuse_forbidden_path(cache / "pdf" / f"{booklet_slug(b['series'], b['number'])}.pdf")
        return path.is_file() and logged.get(u) == hashlib.sha256(path.read_bytes()).hexdigest()

    booklets = {u: b for u, b in booklets.items() if captured(u, b)}
    selected = [{"source_id": SOURCE_ID, "unit_id": u} for u in booklets]
    refuse_eval_reserved_training_input(selected, builder=BUILDER, registry=registry)
    staging = out / ".staging"
    jobs = []
    parsed_blocks: dict[str, list[dict[str, Any]]] = {}  # each OLB page is parsed once
    for unit, b in sorted(booklets.items()):
        olb_pages = []
        for cand in b["olb_candidates"]:
            row = pages[cand["title"]]
            if row["revision_id"] != cand["revision_id"]:
                raise SystemExit(f"{cand['title']}: revision {row['revision_id']} is not the planned {cand['revision_id']}")
            if cand["title"] not in parsed_blocks:
                parsed = parse_olb_page(cand["title"], row["content"], revision_id=row["revision_id"])
                parsed_blocks[cand["title"]] = [asdict(x) for x in parsed.blocks]
            olb_pages.append({"title": cand["title"], "blocks": parsed_blocks[cand["title"]]})
        slug = booklet_slug(b["series"], b["number"])
        jobs.append({"unit_id": unit, "slug": slug, "series": b["series"], "number": b["number"],
                     "pdf": str(cache / "pdf" / f"{slug}.pdf"), "staging": str(staging / slug),
                     "olb_pages": olb_pages, "keep_footnote_lines": args.keep_footnote_lines,
                     "layer_source": "imagestore" if b["series"] == "sefer_hachukim" else "abbyy"})
    print(f"build: {len(jobs)} booklets, {len(parsed_blocks)} OLB pages parsed", flush=True)
    results = []
    if args.workers > 1:
        with Pool(args.workers) as pool:
            for i, result in enumerate(pool.imap_unordered(booklet_job, jobs, chunksize=1), 1):
                results.append(result)
                if i % 20 == 0:
                    print(f"build: {i}/{len(jobs)} booklets", flush=True)
    else:
        results = [booklet_job(j) for j in jobs]
    pool_ngrams, ngram_info = eval_ngram_pool(Path(args.tasks), Path(args.pmod_split))
    capture_log = {}
    log_path = cache / "capture_log.jsonl"
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if "sha256" in r:
                capture_log[r["unit_id"]] = r
    drops: Counter = Counter()
    tiers: Counter = Counter()
    summary_booklets: dict[str, dict[str, Any]] = {}
    candidates: dict[str, list[dict[str, Any]]] = {}
    for result in results:
        unit = result["unit_id"]
        b = booklets[unit]
        kept = []
        local = Counter(result["drops"])
        for r in result["rows"]:
            if word_ngrams(r["text"]) & pool_ngrams:
                local["eval_ngram_overlap"] += 1
                continue
            kept.append(r)
        if args.max_lines_per_booklet and len(kept) > args.max_lines_per_booklet:
            ranked = sorted(kept, key=lambda r: hashlib.sha256(r["id"].encode()).hexdigest())
            keep_ids = {r["id"] for r in ranked[:args.max_lines_per_booklet]}
            local["capped"] += len(kept) - len(keep_ids)
            kept = [r for r in kept if r["id"] in keep_ids]
        drops.update(local)
        tiers.update(r["match_evidence"]["tier"] for r in kept)
        candidates[unit] = kept
        summary_booklets[unit] = {"series": b["series"], "number": b["number"], "year": b["year"], "hebrew_year": b["hebrew_year"],
                                  "lines_candidate": len(kept), "dropped": dict(sorted(local.items())), "facts": result["facts"],
                                  "olb_pages": [c["title"] for c in b["olb_candidates"]],
                                  "publisher_url": (capture_log.get(unit) or {}).get("url"),
                                  "file_token": (capture_log.get(unit) or {}).get("file_token")}
    dev = choose_dev(summary_booklets)
    rows: list[dict[str, Any]] = []
    for unit, kept in candidates.items():
        b = summary_booklets[unit]
        split = "dev" if unit in dev["picks"] else "train"
        b["split"] = split
        slug = booklet_slug(b["series"], b["number"])
        for r in kept:
            olb = pages[r["olb_page_title"]]
            permalink = f"https://he.wikisource.org/w/index.php?oldid={olb['revision_id']}"
            rows.append({
                "id": r["id"], "entry_id": r["entry_id"], "split": split, "book": slug, "record_id": slug, "unit_id": unit,
                "source_id": SOURCE_ID,
                "series": b["series"], "booklet_number": str(b["number"]), "hebrew_year": b["hebrew_year"], "year": b["year"],
                "decade": midcentury_decade(int(b["year"])), "page": r["page"], "line_index": r["line_index"],
                "text": r["text"], "olb_text": r["olb_text"], "label_fold": LABEL_FOLD, "stratum": "unpointed",
                "label_source": LABEL_SOURCE, "label_tier": "silver", "adjudication_status": "not_adjudicated",
                "reference_eligible": False, "capture": CAPTURE, "proposed_node_hint": NODE_HINT,
                "tesseract_exact": bool(r["match_evidence"].get("tesseract_exact")),
                "match_evidence": r["match_evidence"], "tier_a_flags": tier_a_flags(r["text"]),
                "olb_page_title": r["olb_page_title"], "olb_revision_id": olb["revision_id"],
                "olb_revision_timestamp": olb["timestamp"], "olb_block_index": r["olb_block_index"],
                "olb_block_kind": r["olb_block_kind"], "olb_words": r["olb_words"],
                "text_licence": TEXT_LICENCE, "text_licence_url": TEXT_LICENCE_URL,
                "attribution": f"{TEXT_ATTRIBUTION}, {r['olb_page_title']}, {permalink}", "attribution_url": permalink,
                "image_license": IMAGE_LICENSE, "image_license_basis": IMAGE_LICENSE_BASIS, "image_attribution": IMAGE_ATTRIBUTION,
                "publisher_url": b["publisher_url"], "pdf_sha256": b["facts"].get("pdf_sha256"),
                "bbox_image": r["bbox_image"], "crop_box_image": r["crop_box_image"], "scan_size": r["scan_size"],
                "scan_ppi": r["scan_ppi"], "scan_encoding": r["scan_encoding"],
                "image": f"{split}/{slug}/{r['id']}.png", "image_sha256": r["image_sha256"], "_staged": r["staged_image"],
            })
    refuse_eval_reserved_training_input(rows, builder=BUILDER, registry=registry)
    random.Random(args.shuffle_seed).shuffle(rows)
    for row in rows:
        target = out / row["image"]
        target.parent.mkdir(parents=True, exist_ok=True)
        Path(row.pop("_staged")).replace(target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != row["image_sha256"]:
            raise RuntimeError(f"{row['id']}: image changed")
        target.with_suffix(".gt.txt").write_text(row["text"] + "\n", encoding="utf-8")
    import shutil

    shutil.rmtree(staging, ignore_errors=True)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    for split in ("train", "dev"):
        (out / f"{split}_list.txt").write_text("".join(r["image"] + "\n" for r in rows if r["split"] == split), encoding="utf-8")
    per = defaultdict(lambda: defaultdict(Counter))
    for r in rows:
        per[r["series"]][r["decade"]][r["split"]] += 1
    output_status = Counter()
    for r in rows:
        found = unit_status(r, registry)
        output_status[found[1].value if found else "not_governed"] += 1
    olb_used = sorted({(r["olb_page_title"], r["olb_revision_id"]) for r in rows})
    summary = {
        "schema": SCHEMA, "tool": TOOL, "tool_version": TOOL_VERSION,
        "labels": "Hebrew Wikisource OLB text, kept per line only where OCR evidence confirms it equals the print; silver "
                  "training labels, never evaluation references",
        "label_source": LABEL_SOURCE, "capture": CAPTURE, "normalizer": NORMALIZER, "label_fold": LABEL_FOLD,
        "proposed_node_hint": NODE_HINT, "proposed_node_hint_note": NODE_HINT_NOTE,
        "forbidden_input_dirs": [str(p) for p in FORBIDDEN_INPUT_DIRS],
        "shuffle_seed": args.shuffle_seed, "release_notice": RELEASE_NOTICE,
        "text_licence": TEXT_LICENCE, "text_attribution": TEXT_ATTRIBUTION,
        "image_license": IMAGE_LICENSE, "image_license_basis": IMAGE_LICENSE_BASIS,
        "olb_page_permalinks": [{"title": t, "revision_id": rid, "permalink": f"https://he.wikisource.org/w/index.php?oldid={rid}"} for t, rid in olb_used],
        "totals": dict(Counter(r["split"] for r in rows)),
        "lines_by_series_decade": {s: {d: dict(c) for d, c in sorted(v.items())} for s, v in sorted(per.items())},
        "match_evidence_tiers": dict(tiers),
        "dropped": dict(sorted(drops.items())), "dropped_definitions": DROP_DEFINITIONS,
        "booklets": dict(sorted(summary_booklets.items())), "dev_selection": dev,
        "line_set_condition": {
            "condition": json.loads(Path(args.pmod_split).read_text(encoding="utf-8")).get("line_set_condition"),
            "pmod_split": str(Path(args.pmod_split).resolve()),
            "pmod_split_sha256": hashlib.sha256(Path(args.pmod_split).read_bytes()).hexdigest(),
            **ngram_info, "dropped_lines": drops.get("eval_ngram_overlap", 0)},
        "held_out": {"midcentury_split": str(Path(args.split).resolve()), "midcentury_split_sha256": split_digest,
                     "source_id": SOURCE_ID, "unit_id_pattern": UNIT_PREFIX + "<series>_<number>",
                     "registry": registry_provenance(registry),
                     "guard": "refuse_eval_reserved_training_input on the selected booklets and on the rows; both passed",
                     "output_rows_by_status": dict(output_status),
                     "plan_counts": plan_doc["counts"]},
        "tools": {"poppler": poppler_version(), "tesseract": tesseract_version(), "tesseract_model": "heb (stock tessdata)"},
        "thresholds": {"min_line_chars": MIN_LINE_CHARS, "min_line_words": MIN_LINE_WORDS, "max_locate_cer": MAX_LOCATE_CER,
                       "max_consensus_cer": MAX_CONSENSUS_CER, "crop_pad_frac": CROP_PAD_FRAC,
                       "keep_footnote_lines": args.keep_footnote_lines, "max_lines_per_booklet": args.max_lines_per_booklet},
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    }
    if args.signature:
        summary["signature"] = args.signature
    if args.created_at:
        summary["created_at"] = args.created_at
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return summary


EVIDENCE_DROPS = ("ocr_disagrees_with_olb", "single_reading_not_exact", "other_reading_sees_more", "image_unconfirmed",
                  "footnote_marker_in_print", "dev_layer_not_exact")
TIERS = ("both_exact", "layer_exact", "tesseract_exact", "char_consensus")
AUDIT_NAME = "agent audit (data-collection subagent)"


def booklet_candidates(b: Mapping[str, Any]) -> int:
    """Lines of a booklet that reached the per-line gate: recorded by the job, else kept + gate drops."""

    facts = b.get("facts") or {}
    if facts.get("candidate_lines") is not None:
        return int(facts["candidate_lines"])
    dropped = b.get("dropped") or {}
    kept_before = int(b.get("lines_candidate", 0)) + int(dropped.get("eval_ngram_overlap", 0)) + int(dropped.get("capped", 0))
    return kept_before + sum(int(dropped.get(r, 0)) for r in EVIDENCE_DROPS)


def yield_report(booklets: Mapping[str, Mapping[str, Any]], rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Kept lines and kept share of the gate's candidates per (series, decade), per evidence tier."""

    cells: dict[str, dict[str, Any]] = defaultdict(lambda: {"booklets": 0, "pages": 0, "candidate_lines": 0, "kept": 0,
                                                              "kept_by_tier": Counter()})
    for unit, b in booklets.items():
        c = cells[f"{b['series']}|{midcentury_decade(int(b['year']))}"]
        c["booklets"] += 1
        c["pages"] += int((b.get("facts") or {}).get("pages") or 0)
        c["candidate_lines"] += booklet_candidates(b)
    for r in rows:
        c = cells[f"{r['series']}|{r['decade']}"]
        c["kept"] += 1
        c["kept_by_tier"][r["match_evidence"]["tier"]] += 1
    out = {}
    for key, c in sorted(cells.items()):
        n = max(1, c["candidate_lines"])
        out[key] = {"booklets": c["booklets"], "pages": c["pages"], "candidate_lines": c["candidate_lines"], "kept": c["kept"],
                    "kept_share": round(c["kept"] / n, 4),
                    "by_tier": {t: {"kept": c["kept_by_tier"].get(t, 0), "kept_share": round(c["kept_by_tier"].get(t, 0) / n, 4)}
                                for t in TIERS}}
    return out


def _write_set(out: Path, rows: list[dict[str, Any]], seed: str) -> str:
    random.Random(seed).shuffle(rows)
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    for split in ("train", "dev"):
        (out / f"{split}_list.txt").write_text("".join(r["image"] + "\n" for r in rows if r["split"] == split), encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


DEV_README = """# olbreshumotlines_v1_dev

Real-scan dev lines from {units} whole non_eval booklets of ספר החוקים and קובץ התקנות (1948 to mid-2005), held out
from `olbreshumotlines_v1` (no line of these booklets is in train). Labels are same-wording text of Hebrew Wikisource's
ספר החוקים הפתוח (CC BY-SA 4.0, Hebrew Wikisource contributors; each row names its page and pinned revision); line images
are PD-IL (Copyright Act 2007 section 6).

## Selection: the publisher's text layer only

A located line is kept iff the PDF text layer (Imagestore or ABBYY OCR), normalised by `olb_print_compare.v1`, equals
the OLB span, whatever Tesseract reads (`dev_rule: layer_exact_only.v1`). Tesseract-exact-only and character-consensus
lines are not used. Each row says whether stock Tesseract also read it exactly (`tesseract_exact`, and
`match_evidence.tier`: `both_exact` or `layer_exact`), so it can be reported as a stratum; it was never used to select.

## Bias

Even layer-exact selection drops every line the publisher's OCR got wrong. Those lines skew harder: degraded or
broken print, unusual layout (tables, margin notes, letter-spaced signatures), quoted or pointed text, small type,
digits and brackets in bidi-sensitive order. The kept lines are therefore easier than the booklets' lines at large,
and a CER on this set understates the CER on the print as a whole. The per-booklet table below gives each unit's
candidate lines (located lines with an OLB span that reached the gate), kept lines and kept share by tier, and the
same for `olbreshumotlines_v1` train in aggregate.

## Per booklet

| Unit | Series | Decade | Candidate lines | Kept | Kept share | Kept both_exact | Kept layer_exact (Tesseract not exact) |
|---|---|---|---|---|---|---|---|
{table}
| **train (olbreshumotlines_v1, aggregate)** | | | {train_cand} | {train_kept} | {train_share} | {train_both} | {train_layer} (+ tesseract_exact {train_tess}, char_consensus {train_cons}) |

Rows are silver: `adjudication_status: not_adjudicated`, `reference_eligible: false`. Checking: {audit}.
"""


def finalize(args: argparse.Namespace, *, registry: Any = None) -> dict[str, Any]:  # pragma: no cover - operator run
    """Hold out the listed dev units: their lines leave the train set, and a separate dev set is cut from them with
    the layer-only rule (``DEV_RULE``). The train set's own per-stratum dev booklets return to train."""

    import shutil

    from hocrgen.split.eval_reserved import refuse_eval_reserved_training_input, registry_provenance

    out, dev_out = Path(args.out), Path(args.dev_out)
    for path in (args.out, args.dev_out, args.dev_units, args.plan, args.split, args.pmod_split, args.tasks, args.olb, args.cache):
        refuse_forbidden_path(path)
    if dev_out.exists():
        raise SystemExit(f"{dev_out} exists")
    split_status, split_digest = load_split(Path(args.split), args.split_sha256)
    registry = training_registry(registry)
    raw = Path(args.dev_units).read_text(encoding="utf-8")
    dev_units = sorted(set(json.loads(raw) if raw.lstrip().startswith("[") else [x.strip() for x in raw.splitlines() if x.strip()]))
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if summary.get("dev_holdout"):
        raise SystemExit(f"{out} already has a dev holdout")
    for unit in dev_units:
        status = registry.status(SOURCE_ID, unit)
        if split_status.get(unit) != "non_eval" or status is None or status.value != "non_eval":
            raise SystemExit(f"dev unit {unit} is not non_eval")
        if unit not in summary["booklets"]:
            raise SystemExit(f"dev unit {unit} was not captured and built")
    refuse_eval_reserved_training_input([{"source_id": SOURCE_ID, "unit_id": u} for u in dev_units], builder=BUILDER, registry=registry)

    # train: drop the dev units' lines, return the per-stratum dev booklets to train
    held = set(dev_units)
    train_rows = []
    for r in rows:
        path = out / r["image"]
        if r["unit_id"] in held:
            path.unlink()
            path.with_suffix(".gt.txt").unlink()
            continue
        if r["split"] != "train":
            new = Path("train") / Path(r["image"]).relative_to(r["split"])
            (out / new).parent.mkdir(parents=True, exist_ok=True)
            path.replace(out / new)
            path.with_suffix(".gt.txt").replace((out / new).with_suffix(".gt.txt"))
            r["image"], r["split"] = str(new), "train"
        r.setdefault("tesseract_exact", bool(r["match_evidence"].get("tesseract_exact")))
        train_rows.append(r)
    for d in (out / "dev").glob("*") if (out / "dev").is_dir() else []:
        shutil.rmtree(d, ignore_errors=True)
    if (out / "dev").is_dir():
        shutil.rmtree(out / "dev", ignore_errors=True)
    for unit in held:
        shutil.rmtree(out / "train" / unit_slug(unit), ignore_errors=True)
    refuse_eval_reserved_training_input(train_rows, builder=BUILDER, registry=registry)
    for unit, b in summary["booklets"].items():
        b["split"] = "dev_holdout" if unit in held else "train"
    per = defaultdict(lambda: defaultdict(Counter))
    for r in train_rows:
        per[r["series"]][r["decade"]]["train"] += 1
    holdout = {"units": dev_units, "units_sha256": hashlib.sha256("\n".join(dev_units).encode()).hexdigest(),
               "source": str(Path(args.dev_units).resolve()), "dev_set": str(dev_out.resolve()),
               "train_lines_removed": len(rows) - len(train_rows)}
    summary.update({
        "totals": dict(Counter(r["split"] for r in train_rows)),
        "lines_by_series_decade": {s: {d: dict(c) for d, c in sorted(v.items())} for s, v in sorted(per.items())},
        "match_evidence_tiers": dict(Counter(r["match_evidence"]["tier"] for r in train_rows)),
        "dev_selection": {"method": "external dev holdout (dev_holdout): whole units listed by the lead and heocr-eval; "
                                    "their lines are in the separate dev set, none in train", "picks": {}, "ranking": {}},
        "dev_holdout": holdout,
        "yield": yield_report({u: b for u, b in summary["booklets"].items() if u not in held}, train_rows),
    })
    summary["manifest_sha256"] = _write_set(out, train_rows, summary["shuffle_seed"])
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # dev: re-cut the held-out units with the layer-only rule
    plan_doc = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    pages = load_olb_pages(Path(args.olb))
    cache = Path(args.cache)
    staging = dev_out / ".staging"
    jobs, parsed_blocks = [], {}
    for unit in dev_units:
        b = plan_doc["booklets"][unit]
        olb_pages = []
        for cand in b["olb_candidates"]:
            if cand["title"] not in parsed_blocks:
                row = pages[cand["title"]]
                if row["revision_id"] != cand["revision_id"]:
                    raise SystemExit(f"{cand['title']}: revision changed")
                parsed_blocks[cand["title"]] = [asdict(x) for x in parse_olb_page(cand["title"], row["content"]).blocks]
            olb_pages.append({"title": cand["title"], "blocks": parsed_blocks[cand["title"]]})
        slug = booklet_slug(b["series"], b["number"])
        jobs.append({"unit_id": unit, "slug": slug, "series": b["series"], "number": b["number"],
                     "pdf": str(cache / "pdf" / f"{slug}.pdf"), "staging": str(staging / slug), "olb_pages": olb_pages,
                     "keep_footnote_lines": False, "dev_rule": DEV_RULE,
                     "layer_source": "imagestore" if b["series"] == "sefer_hachukim" else "abbyy"})
    with Pool(max(1, args.workers)) as pool:
        results = pool.map(booklet_job, jobs, chunksize=1)
    pool_ngrams, ngram_info = eval_ngram_pool(Path(args.tasks), Path(args.pmod_split))
    dev_rows, dev_booklets, drops = [], {}, Counter()
    for result in results:
        unit = result["unit_id"]
        b = plan_doc["booklets"][unit]
        tb = summary["booklets"][unit]
        local = Counter(result["drops"])
        slug = booklet_slug(b["series"], b["number"])
        kept = []
        for r in result["rows"]:
            if word_ngrams(r["text"]) & pool_ngrams:
                local["eval_ngram_overlap"] += 1
                continue
            kept.append(r)
        drops.update(local)
        for r in kept:
            olb = pages[r["olb_page_title"]]
            permalink = f"https://he.wikisource.org/w/index.php?oldid={olb['revision_id']}"
            target = dev_out / "dev" / slug / f"{r['id']}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            Path(r["staged_image"]).replace(target)
            target.with_suffix(".gt.txt").write_text(r["text"] + "\n", encoding="utf-8")
            from hocrgen.tools.reshumot_lines import tier_a_flags

            dev_rows.append({
                "id": r["id"], "entry_id": r["entry_id"], "split": "dev", "book": slug, "record_id": slug, "unit_id": unit,
                "source_id": SOURCE_ID, "series": b["series"], "booklet_number": str(b["number"]), "hebrew_year": b["hebrew_year"],
                "year": b["year"], "decade": midcentury_decade(int(b["year"])), "page": r["page"], "line_index": r["line_index"],
                "text": r["text"], "olb_text": r["olb_text"], "label_fold": LABEL_FOLD, "stratum": "unpointed",
                "label_source": LABEL_SOURCE, "label_tier": "silver", "adjudication_status": "not_adjudicated",
                "reference_eligible": False, "capture": CAPTURE, "proposed_node_hint": NODE_HINT, "dev_rule": DEV_RULE,
                "tesseract_exact": bool(r["match_evidence"].get("tesseract_exact")),
                "match_evidence": r["match_evidence"], "tier_a_flags": tier_a_flags(r["text"]),
                "olb_page_title": r["olb_page_title"], "olb_revision_id": olb["revision_id"],
                "olb_revision_timestamp": olb["timestamp"], "olb_block_index": r["olb_block_index"],
                "olb_block_kind": r["olb_block_kind"], "olb_words": r["olb_words"],
                "text_licence": TEXT_LICENCE, "text_licence_url": TEXT_LICENCE_URL,
                "attribution": f"{TEXT_ATTRIBUTION}, {r['olb_page_title']}, {permalink}", "attribution_url": permalink,
                "image_license": IMAGE_LICENSE, "image_license_basis": IMAGE_LICENSE_BASIS, "image_attribution": IMAGE_ATTRIBUTION,
                "publisher_url": tb.get("publisher_url"), "pdf_sha256": result["facts"].get("pdf_sha256"),
                "bbox_image": r["bbox_image"], "crop_box_image": r["crop_box_image"], "scan_size": r["scan_size"],
                "scan_ppi": r["scan_ppi"], "scan_encoding": r["scan_encoding"],
                "image": f"dev/{slug}/{r['id']}.png", "image_sha256": r["image_sha256"],
            })
            if hashlib.sha256(target.read_bytes()).hexdigest() != r["image_sha256"]:
                raise RuntimeError(f"{r['id']}: image changed")
        dev_booklets[unit] = {"series": b["series"], "number": b["number"], "year": b["year"], "hebrew_year": b["hebrew_year"],
                              "split": "dev", "lines_candidate": len(kept), "dropped": dict(sorted(local.items())),
                              "facts": result["facts"], "publisher_url": tb.get("publisher_url"),
                              "olb_pages": [c["title"] for c in b["olb_candidates"]]}
    shutil.rmtree(staging, ignore_errors=True)
    refuse_eval_reserved_training_input(dev_rows, builder=BUILDER + " (dev holdout)", registry=registry)
    dev_out.mkdir(parents=True, exist_ok=True)
    dev_summary = {k: summary[k] for k in ("tool", "tool_version", "label_source", "capture", "normalizer", "label_fold",
                                           "proposed_node_hint", "proposed_node_hint_note", "release_notice", "text_licence",
                                           "text_attribution", "image_license", "image_license_basis", "tools", "thresholds",
                                           "shuffle_seed", "held_out", "forbidden_input_dirs")}
    yields = yield_report(dev_booklets, dev_rows)
    per_booklet = {}
    for unit, b in sorted(dev_booklets.items()):
        n = booklet_candidates(b)
        tiers = Counter(r["match_evidence"]["tier"] for r in dev_rows if r["unit_id"] == unit)
        per_booklet[unit] = {"series": b["series"], "decade": midcentury_decade(int(b["year"])), "candidate_lines": n,
                             "kept": sum(tiers.values()), "kept_share": round(sum(tiers.values()) / max(1, n), 4),
                             "kept_by_tier": dict(tiers)}
    train_cand = sum(booklet_candidates(b) for u, b in summary["booklets"].items() if u not in held)
    train_tiers = Counter(r["match_evidence"]["tier"] for r in train_rows)
    dev_summary.update({
        "schema": SCHEMA + "+dev", "dev_rule": DEV_RULE,
        "dev_rule_text": "kept iff the publisher's PDF text layer equals the OLB span (olb_print_compare.v1), whatever "
                         "Tesseract reads; tesseract_exact is recorded per row as a stratum, never used to select",
        "labels": "Hebrew Wikisource OLB text, kept per line only where the publisher's OCR layer equals it; silver dev lines",
        "totals": {"dev": len(dev_rows)}, "match_evidence_tiers": dict(Counter(r["match_evidence"]["tier"] for r in dev_rows)),
        "dropped": dict(sorted(drops.items())), "dropped_definitions": {**DROP_DEFINITIONS,
            "dev_layer_not_exact": "dev rule: the publisher layer does not equal the OLB span"},
        "booklets": dev_booklets, "dev_selection": {"method": "external dev holdout", "picks": {u: f"{b['series']}|{midcentury_decade(int(b['year']))}" for u, b in dev_booklets.items()}},
        "dev_holdout": holdout, "per_booklet": per_booklet, "yield": yields,
        "train_aggregate": {"candidate_lines": train_cand, "kept": len(train_rows), "kept_share": round(len(train_rows) / max(1, train_cand), 4),
                            "kept_by_tier": dict(train_tiers)},
        "line_set_condition": {**summary["line_set_condition"], **ngram_info, "dropped_lines": drops.get("eval_ngram_overlap", 0)},
        "olb_page_permalinks": [{"title": t, "revision_id": rid, "permalink": f"https://he.wikisource.org/w/index.php?oldid={rid}"}
                                for t, rid in sorted({(r["olb_page_title"], r["olb_revision_id"]) for r in dev_rows})],
    })
    if args.signature:
        dev_summary["signature"] = args.signature
    if args.created_at:
        dev_summary["created_at"] = args.created_at
    dev_summary["manifest_sha256"] = _write_set(dev_out, dev_rows, summary["shuffle_seed"] + ":dev")
    dev_summary["shuffle_seed_dev"] = summary["shuffle_seed"] + ":dev"
    (dev_out / "summary.json").write_text(json.dumps(dev_summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    table = "\n".join(f"| {u} | {v['series']} | {v['decade']} | {v['candidate_lines']} | {v['kept']} | {v['kept_share']:.1%} | "
                      f"{v['kept_by_tier'].get('both_exact', 0)} | {v['kept_by_tier'].get('layer_exact', 0)} |" for u, v in per_booklet.items())
    (dev_out / "README.md").write_text(DEV_README.format(
        units=len(dev_units), table=table, train_cand=train_cand, train_kept=len(train_rows),
        train_share=f"{len(train_rows) / max(1, train_cand):.1%}", train_both=train_tiers.get("both_exact", 0),
        train_layer=train_tiers.get("layer_exact", 0), train_tess=train_tiers.get("tesseract_exact", 0),
        train_cons=train_tiers.get("char_consensus", 0), audit=AUDIT_NAME + " of the train set; see the PR"), encoding="utf-8")
    return {"train": summary, "dev": dev_summary}


def verify(out: Path, *, split_path: Path, split_sha256: str, registry: Any = None) -> list[str]:
    from hocrgen.split.eval_reserved import EvalReservedUnitError, refuse_eval_reserved_training_input

    refuse_forbidden_path(out)
    refuse_forbidden_path(split_path)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    status, digest = load_split(split_path, split_sha256)
    registry = training_registry(registry)
    problems = []
    if hashlib.sha256((out / "manifest.jsonl").read_bytes()).hexdigest() != summary["manifest_sha256"]:
        problems.append("manifest sha256 differs from summary")
    if digest != summary["held_out"]["midcentury_split_sha256"]:
        problems.append("built from another midcentury split")
    try:
        refuse_eval_reserved_training_input(rows, builder="olb_reshumot_lines verify", registry=registry)
    except EvalReservedUnitError as exc:
        problems.append(str(exc))
    dev = set(summary["dev_selection"]["picks"])
    ids = Counter(r["id"] for r in rows)
    problems += [f"duplicate id {i}" for i, n in ids.items() if n > 1]
    split_units = defaultdict(set)
    for r in rows:
        where = r["id"]
        split_units[r["split"]].add(r["unit_id"])
        if status.get(r["unit_id"]) != "non_eval":
            problems.append(f"{where}: unit {r['unit_id']} is {status.get(r['unit_id'], 'unassigned')}")
        if r["split"] not in ("train", "dev") or (r["split"] == "dev") != (r["unit_id"] in dev):
            problems.append(f"{where}: split disagrees with the dev booklets")
        if is_pointed(r["text"]) or r["text"] != fold_label(strip_points(r["olb_text"])):
            problems.append(f"{where}: label is not the folded OLB span or carries niqqud")
        if not r.get("match_evidence", {}).get("tier"):
            problems.append(f"{where}: no match evidence")
        if (r.get("label_source"), r.get("capture"), r.get("adjudication_status"), r.get("reference_eligible")) != (
                LABEL_SOURCE, CAPTURE, "not_adjudicated", False):
            problems.append(f"{where}: provenance fields wrong")
        if r.get("text_licence") != TEXT_LICENCE or "oldid=" not in r.get("attribution_url", "") or not r.get("olb_revision_id"):
            problems.append(f"{where}: OLB licence, attribution or revision missing")
        if r.get("image_license") != IMAGE_LICENSE or not r.get("publisher_url"):
            problems.append(f"{where}: image licence or publisher URL missing")
        path = out / r["image"]
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != r["image_sha256"]:
            problems.append(f"{where}: image missing or sha256 mismatch")
        gt = path.with_suffix(".gt.txt")
        if not gt.is_file() or gt.read_text(encoding="utf-8") != r["text"] + "\n":
            problems.append(f"{where}: gt.txt differs from the label")
    if split_units["train"] & split_units["dev"]:
        problems.append("a booklet is in both train and dev")
    for split in ("train", "dev"):
        listed = (out / f"{split}_list.txt").read_text(encoding="utf-8").split()
        if listed != [r["image"] for r in rows if r["split"] == split]:
            problems.append(f"{split}_list.txt differs from the manifest order")
    return problems


def add_build_arguments(sub: Any) -> None:
    b = sub.add_parser("build", help="cut the line set from captured non_eval booklets (run under python -I)")
    b.add_argument("out")
    b.add_argument("--plan", required=True)
    b.add_argument("--split", required=True, help="heocr-eval's midcentury_unit_split_v0.json")
    b.add_argument("--split-sha256", required=True)
    b.add_argument("--pmod-split", required=True, help="heocr-eval's current pmod_unit_split (its line_set_condition and eval booklets)")
    b.add_argument("--tasks", required=True, help="the HeOCR tasks directory (wave-1 manifest, tranche text)")
    b.add_argument("--olb", required=True)
    b.add_argument("--cache", required=True)
    b.add_argument("--series", nargs="+", default=["sefer_hachukim", "kovetz_hatakanot"])
    b.add_argument("--only", nargs="*", help="unit ids to build (a pilot)")
    b.add_argument("--shuffle-seed", required=True)
    b.add_argument("--workers", type=int, default=1)
    b.add_argument("--max-lines-per-booklet", type=int, default=MAX_LINES_PER_BOOKLET)
    b.add_argument("--keep-footnote-lines", action="store_true")
    b.add_argument("--created-at")
    b.add_argument("--signature")
    f = sub.add_parser("finalize", help="hold out listed dev units: remove them from train, cut the dev set (layer-only rule)")
    f.add_argument("out")
    f.add_argument("--dev-units", required=True, help="unit ids (JSON list or one per line)")
    f.add_argument("--dev-out", required=True)
    for name in ("--plan", "--split", "--split-sha256", "--pmod-split", "--tasks", "--olb", "--cache"):
        f.add_argument(name, required=True)
    f.add_argument("--workers", type=int, default=4)
    f.add_argument("--created-at")
    f.add_argument("--signature")
    v = sub.add_parser("verify", help="check a built set")
    v.add_argument("out")
    v.add_argument("--split", required=True)
    v.add_argument("--split-sha256", required=True)


def run_build_command(args: argparse.Namespace) -> int:  # pragma: no cover - operator run
    if args.command == "build":
        summary = build(args)
        print(json.dumps({k: summary[k] for k in ("totals", "match_evidence_tiers", "dropped", "manifest_sha256")}, ensure_ascii=False))
        return 0
    if args.command == "finalize":
        result = finalize(args)
        print(json.dumps({"train": {k: result["train"][k] for k in ("totals", "manifest_sha256")},
                          "dev": {k: result["dev"][k] for k in ("totals", "match_evidence_tiers", "manifest_sha256")}}, ensure_ascii=False))
        return 0
    problems = verify(Path(args.out), split_path=Path(args.split), split_sha256=args.split_sha256)
    for problem in problems[:50]:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


# --- CLI ----------------------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("olb-fetch", help="fetch the current revision of every OLB page (Wikisource API, 1 req/s)")
    f.add_argument("--titles", required=True, help="jsonl of category members ({'title': ...}), or a text file of titles")
    f.add_argument("--out", required=True)
    x = sub.add_parser("olb-index", help="parse the fetched OLB pages into olb_index.json")
    x.add_argument("olb_dir")
    p = sub.add_parser("plan", help="OLB candidates per non_eval booklet")
    p.add_argument("--units", required=True)
    p.add_argument("--split", required=True)
    p.add_argument("--split-sha256", required=True)
    p.add_argument("--olb", required=True)
    p.add_argument("--out", required=True)
    c = sub.add_parser("capture", help="fetch planned non_eval booklet PDFs (gov.il, 1 req / 1.2 s)")
    c.add_argument("--plan", required=True)
    c.add_argument("--cache", required=True)
    c.add_argument("--series", nargs="+", default=["sefer_hachukim", "kovetz_hatakanot"])
    c.add_argument("--all-booklets", action="store_true", help="also booklets without an OLB candidate")
    c.add_argument("--limit", type=int)
    c.add_argument("--shard", help="i/n: take every n-th planned booklet starting at i (parallel captures, one throttle)")
    c.add_argument("--min-priority", type=int, default=0, help="only booklets with at least this many first-published OLB instruments")
    add_build_arguments(sub)
    args = parser.parse_args(argv)
    if args.command == "olb-fetch":
        raw = Path(args.titles).read_text(encoding="utf-8").splitlines()
        titles = [json.loads(line)["title"] if line.startswith("{") else line.strip() for line in raw if line.strip()]
        print(json.dumps(olb_fetch(titles, Path(args.out)), ensure_ascii=False))
        return 0
    if args.command == "olb-index":
        print(json.dumps(olb_index(Path(args.olb_dir))["stats"], ensure_ascii=False))
        return 0
    if args.command == "plan":
        doc = plan(Path(args.units), Path(args.split), args.split_sha256, Path(args.olb))
        Path(args.out).write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(json.dumps(doc["counts"], ensure_ascii=False))
        return 0
    if args.command == "capture":
        doc = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        print(json.dumps(capture(doc, Path(args.cache), series=args.series, only_candidates=not args.all_booklets,
                                 limit=args.limit, min_priority=args.min_priority,
                                 shard=tuple(int(x) for x in args.shard.split("/")) if args.shard else None), ensure_ascii=False))
        return 0
    return run_build_command(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
