"""Operator-only F8g2 capture and materialization of Reshumot and Knesset committee pages for the real tranche.

The F8e fixtures hold 2 Reshumot and 3 Knesset pages. This module grows both sources in the operator tranche with
the F8e method, unchanged:

- **Reshumot** (``reshumot_born_digital``): ספר החוקים and קובץ התקנות booklets published on or after 2006-01-01,
  found through the gazette search API (one query per series and Hebrew year), sampled by a seeded hash. Each page is
  rendered with ``pdftoppm`` at 150 dpi, 8-bit gray (``is_scan: false``), and carries the ``pdftotext`` text in
  logical order (``hocrgen.parsers.pdf_bidi``). The unchanged F8e gate decides each page: a page whose text fails the
  logical-order check, or whose PDF has an image on that page, is left out and counted by reason.
- **Knesset** (``knesset_committee_protocols_pre1976``): committee protocols (group type 23) of open sessions on or
  before 1975-12-31, from the Knesset OData service, sampled by a seeded hash per Knesset term. Each page is the
  PDF's embedded scan, extracted losslessly with ``pdfimages``: a 1-bit CCITT scan re-encoded as PNG, or a colour
  rescan's JPEG stream kept byte for byte. Images only; the OCR layer is never carried.

``capture`` is network (throttled, descriptive User-Agent, never in CI). Everything else is offline: the entry
builders are pure, and the poppler calls are confined to ``_poppler_*`` helpers.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image
from PIL import __version__ as PIL_VERSION

from hocrgen.parsers.pdf_bidi import PDF_BIDI_NORMALIZATION_VERSION, layout_notes, logical_order_issues, poppler_text_to_logical

USER_AGENT = "hocrgen-real-tranche/0.2 (https://github.com/HeOCR/hocrgen; operator capture, throttled)"
RESHUMOT_SEARCH_URL = "https://pub-justice.openapi.gov.il/pub/moj/portal/rest/searchpredefinedapi/v1/SearchPredefinedApi/Reshumot/Search"
# The public client id embedded in the gov.il gazette collector page (verification note, Source 3).
RESHUMOT_CLIENT_ID = "149a5bad-edde-49a6-9fb9-188bd17d4788"
RESHUMOT_SERIES = {"1": ("sefer_hachukim", "ספר החוקים"), "3": ("kovetz_hatakanot", "קובץ התקנות")}
RESHUMOT_BORN_DIGITAL_FROM = "2006-01-01"
RESHUMOT_HEBREW_YEAR_OFFSET = 5692  # BookletYear = Hebrew year - 5692 (verification note: 17 = 1949, 94 = 2026)
RESHUMOT_LIMITATIONS = [
    "block order follows poppler's physical layout analysis: side headings and section numbers come out as separate blocks before the body text",
    "superscript footnote markers are plain digits; an RLM between a marker and a preceding number becomes one space",
    "punctuation code points follow the PDF ToUnicode maps (for example ASCII quote and hyphen where the glyphs look like gershayim and an en dash)",
    "no line, word or block geometry is kept",
]
RESHUMOT_GLYPH_LIMITATIONS = [
    "reading order is rebuilt from glyph geometry: body lines top to bottom; a narrower block (a side heading, a signature, a table column) is read whole where it starts, side headings before the body line beside them, blocks on one row right to left",
    "a label set off by a tab or hanging indent (3., 2ג., (א), a footnote number) is joined to the line it labels with one space",
    "superscript digits next to digits are set off by one space (התשנ\"ה-1995 1); other superscripts are joined to their neighbour",
    "word spaces come from space glyphs or from gaps of at least 0.1 em; letter-spaced print is read as words",
    "punctuation code points follow the ToUnicode maps except where the glyph outline table names the character; brackets follow their drawn shape and run direction",
    "lines whose order or characters cannot be verified are left out and the page image is cropped to the verified regions (decision 12)",
    "the text keeps no geometry; the committed glyph layer holds every glyph's box",
]
RESHUMOT_GLYPH_EXTRACTION_COMMAND = "hocrgen.parsers.pdf_glyphs.extract_glyph_layer(<pdf>, {page})"
RESHUMOT_OUTLINE_TABLE = "glyph_outlines.json"
RESHUMOT_RIGHTS_BASIS = "Copyright Act 2007 section 6: no copyright in laws, regulations, Knesset proceedings and judicial decisions"

KNESSET_ODATA = "https://knesset.gov.il/OdataV4/ParliamentInfo/"
KNESSET_CUTOFF = "1975-12-31T23:59:59Z"
KNESSET_RIGHTS_BASIS = (
    "Copyright Act 2007 sections 36 and 42: a State work is public domain 50 years after creation (created on or before 1975-12-31)"
)
KNESSET_RIGHTS_EVIDENCE = (
    "Knesset committee protocol: a State work, not a section-6 Knesset proceeding; PD when the session is on or before "
    "1975-12-31 (verification note track_a_legislative_judicial.md, Source 1; F8 decision 5)"
)


def seeded_key(seed: str, value: str) -> str:
    return hashlib.sha256(f"{seed}\0{value}".encode("utf-8")).hexdigest()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# --- selection (pure) ----------------------------------------------------------------------------------------------


def reshumot_booklet_year_index(hebrew_year: int) -> str:
    return str(hebrew_year - RESHUMOT_HEBREW_YEAR_OFFSET)


def select_reshumot_booklets(results: Iterable[dict[str, Any]], *, seed: str, per_query: int, max_pages: int) -> list[dict[str, Any]]:
    """The ``per_query`` §6 booklets of one search answer to capture: born-digital era, at most ``max_pages`` pages.

    The order is a seeded hash of series and booklet number, so the choice of one booklet never depends on another.
    """

    eligible = []
    for result in results:
        data = result.get("Data") or {}
        if str(data.get("FolderType")) not in RESHUMOT_SERIES:
            continue
        if str(data.get("PublishDate") or "")[:10] < RESHUMOT_BORN_DIGITAL_FROM:
            continue
        if not data.get("Document") or not isinstance(data.get("Pages"), int) or not 0 < data["Pages"] <= max_pages:
            continue
        eligible.append(data)
    eligible.sort(key=lambda data: seeded_key(seed, f"{data['FolderType']}:{data['BookletNum']}"))
    return eligible[:per_query]


def knesset_document_is_candidate(document: dict[str, Any]) -> bool:
    """Metadata pre-filter before a PDF is fetched; the F8e gate still decides every page."""

    session = document.get("KNS_CommitteeSession") or {}
    return (
        document.get("GroupTypeID") == 23
        and document.get("ApplicationDesc") == "PDF"
        and str(session.get("StartDate") or "")[:10] <= KNESSET_CUTOFF[:10]
        and session.get("TypeDesc") == "פתוחה"
        and bool((session.get("KNS_Committee") or {}).get("Name"))
    )


def select_knesset_documents(documents: Iterable[dict[str, Any]], *, seed: str, count: int, per_committee: int = 1) -> list[dict[str, Any]]:
    """``count`` protocols from one Knesset term's documents, at most ``per_committee`` per committee, by seeded hash."""

    chosen: list[dict[str, Any]] = []
    per: dict[Any, int] = {}
    for document in sorted((doc for doc in documents if knesset_document_is_candidate(doc)), key=lambda doc: seeded_key(seed, str(doc["Id"]))):
        committee = document["KNS_CommitteeSession"].get("CommitteeID")
        if per.get(committee, 0) >= per_committee:
            continue
        per[committee] = per.get(committee, 0) + 1
        chosen.append(document)
        if len(chosen) >= count:
            break
    return chosen


# --- entries (pure) ------------------------------------------------------------------------------------------------


def docsummary_titles(html: str) -> list[tuple[str, str]]:
    """(title, printed page) pairs from the gazette API's table of contents."""

    titles = []
    for part in html.split("<br/>"):
        match = re.match(r"^\s*(.+?)\s+(\d{3,5})\s*$", part)
        if match:
            titles.append((match.group(1).strip(), match.group(2)))
    return titles


def printed_page_number(logical: str) -> str | None:
    for line in logical.splitlines():
        if re.fullmatch(r"\d{3,5}[\x00-\x1f]*", line.strip()):
            return re.sub(r"\D", "", line)
    return None


def reshumot_expected_phrases(data: dict[str, Any], page: int, logical: str) -> list[dict[str, str]]:
    """Phrases the page must contain, from the gazette API: independent anchors for the text's order.

    An inner page carries the running footer (series and booklet number, the Gregorian date) and the titles the API's
    table of contents places on its printed page. The cover (PDF page 1) has no footer; it carries the series name,
    the booklet number and the whole table of contents."""

    _, series_he = RESHUMOT_SERIES[str(data["FolderType"])]
    booklet = str(data["BookletNum"])
    year, month, day = (int(part) for part in str(data["PublishDate"])[:10].split("-"))
    titles = docsummary_titles(((data.get("DocSummary") or {}).get("DescriptionHtmlString")) or "")
    if page == 1:
        return [
            {"text": series_he, "source": "gazette API FolderType (cover)"},
            {"text": booklet, "source": "gazette API BookletNum (cover)"},
            *({"text": title, "source": "gazette API DocSummary (cover table of contents)"} for title, _ in titles),
        ]
    printed = printed_page_number(logical)
    return [
        {"text": f"{series_he} {booklet},", "source": "gazette API BookletNum and FolderType"},
        {"text": f"{day}.{month}.{year}", "source": "gazette API PublishDate"},
        *({"text": title, "source": "gazette API DocSummary"} for title, title_page in titles if printed and title_page == printed),
    ]


def reshumot_page_entry(
    *,
    data: dict[str, Any],
    pdf: dict[str, Any],
    page: int,
    page_image_count: int,
    raw_text: str,
    poppler_version: str,
    captured_at: str,
    image_file: dict[str, Any] | None,
) -> tuple[dict[str, Any], str, list[str]]:
    """One Reshumot page entry in the F8e snapshot format, its logical text and its order issues.

    ``pdf`` holds the PDF facts (``sha256``, ``bytes``, ``info`` from pdfinfo, ``fonts``); ``image_file`` is the page
    render's file record, or None when the page is not rendered.
    """

    series_key, series_he = RESHUMOT_SERIES[str(data["FolderType"])]
    booklet = str(data["BookletNum"])
    publish_date = str(data["PublishDate"])[:10]
    year, month, day = (int(part) for part in publish_date.split("-"))
    stem = f"{series_key}_{booklet}__p{page:04d}"
    logical, conversion_issues = poppler_text_to_logical(raw_text)
    printed = printed_page_number(logical)
    expected = [
        {"text": f"{series_he} {booklet},", "source": "gazette API BookletNum and FolderType"},
        {"text": f"{day}.{month}.{year}", "source": "gazette API PublishDate"},
    ]
    titles = docsummary_titles(((data.get("DocSummary") or {}).get("DescriptionHtmlString")) or "")
    expected += [{"text": title, "source": "gazette API DocSummary"} for title, title_page in titles if printed and title_page == printed]
    issues = sorted(set(conversion_issues) | set(logical_order_issues(logical, [item["text"] for item in expected])))
    info = pdf["info"]
    document = data["Document"][0]
    entry = {
        "booklet": {
            "booklet_number": booklet,
            "booklet_year_index": str(data.get("BookletYear")),
            "display_name": document.get("DisplayName"),
            "folder_type": str(data["FolderType"]),
            "foreign_year": str(data.get("ForeignYear")),
            "page_count": data.get("Pages"),
            "publish_date": publish_date,
            "series": series_key,
            "series_name_he": series_he,
        },
        "content_type": "printed_modern",
        "direction": "rtl",
        "entry_id": stem,
        "files": [image_file] if image_file else [],
        "languages": ["he"],
        "page": {"pdf_page_index": page, "printed_page_number": printed},
        "pdf": {
            "born_digital": "InDesign" in str(info.get("Creator", "")) and bool(pdf["fonts"]),
            "born_digital_evidence": (
                f"Creator {info.get('Creator')!r}, Producer {info.get('Producer')!r}; embedded fonts with Unicode maps; "
                f"{'no page image' if page_image_count == 0 else f'{page_image_count} page image(s)'} on this page (pdfimages)"
            ),
            "bytes": pdf["bytes"],
            "creation_date": info.get("CreationDate"),
            "creator": info.get("Creator"),
            "document_url": document["FileName"],
            "embedded_fonts": pdf["fonts"],
            "page_count": int(info.get("Pages", 0)),
            "page_image_count": page_image_count,
            "producer": info.get("Producer"),
            "sha256": pdf["sha256"],
        },
        "rights": {
            "basis": RESHUMOT_RIGHTS_BASIS,
            "evidence_text": f"{series_he} publishes laws and regulations (section 6); verification note track_a_legislative_judicial.md, Source 3",
            "license_expression": "PD-IL",
            "verification_status": "primary_page_checked",
            "verified_at": captured_at,
        },
        "script": "Hebr",
        "text": {
            "adjudication_status": "not_adjudicated",
            "extraction": {
                "command": f"pdftotext -f {page} -l {page} -enc UTF-8 <pdf> <out>",
                "extractor": "pdftotext (poppler)",
                "extractor_version": poppler_version,
                "normalization": PDF_BIDI_NORMALIZATION_VERSION,
                "raw_local_path": f"extraction/{stem}.pdftotext.txt",
                "raw_sha256": _sha256(raw_text.encode("utf-8")),
            },
            "geometry": "none",
            "granularity": "page",
            "heocr_attestation": "none",
            "known_limitations": RESHUMOT_LIMITATIONS,
            "layout_notes": layout_notes(logical),
            "local_path": f"text/{stem}.txt",
            "order_verification": {"expected_phrases": expected, "issues": issues},
            "reference_eligible": False,
            "sha256": _sha256(logical.encode("utf-8")),
            "text_provenance": "born_digital_pdf_text",
            "text_tier": 2,
            "unicode": "NFC",
        },
        "title": f"{series_he} {booklet} ({day}.{month}.{year}), page {printed or page}",
        "upstream": {
            "api_search_body": {"BookletYear": str(data.get("BookletYear")), "FolderType": str(data["FolderType"]), "skip": 0},
            "api_search_url": RESHUMOT_SEARCH_URL,
            "doc_summary_html": (data.get("DocSummary") or {}).get("DescriptionHtmlString"),
            "modify_date": data.get("ModifyDate"),
        },
    }
    return entry, logical, issues


def glyph_layer_bytes(layer: dict[str, Any]) -> bytes:
    """The committed form of a glyph layer: compact JSON, gzip-compressed with no timestamp. The JSON is
    byte-reproducible; the deflate stream is for one zlib build, so the file is pinned by its own sha256."""

    import gzip

    return gzip.compress(json.dumps(layer, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), compresslevel=9, mtime=0)


def reshumot_glyph_page_entry(
    *,
    data: dict[str, Any],
    pdf: dict[str, Any],
    page: int,
    page_image_count: int,
    layer: dict[str, Any],
    layer_sha256: str,
    table: dict[str, Any],
    table_sha256: str,
    render_file: dict[str, Any],
    render_image: Any,
    captured_at: str,
) -> tuple[dict[str, Any], str, list[str], Any]:
    """One F8e2 Reshumot page entry from its glyph layer and render: the entry, its text, its order issues and the
    crop image (None when the whole page is verified).

    The text is re-derived and re-checked by the gate (``hocrgen.fetchers.government_print``), so nothing here is
    trusted downstream: the builder only records what the pure functions produce.
    """

    from hocrgen.fetchers.government_print import RESHUMOT_CROP_ROLE, reshumot_crop_record
    from hocrgen.fetchers.wikisource import crop_image, crop_mask_fill, crop_pixel_box, crop_region_boxes
    from hocrgen.parsers.pdf_geometry import GEOMETRY_NORMALIZATION_VERSION, verify_glyph_page

    dpi = float(render_file["rendering"]["dpi"])
    expected_for = {}

    def expected(text: str) -> list[str]:
        expected_for["phrases"] = reshumot_expected_phrases(data, page, text)
        return [item["text"] for item in expected_for["phrases"]]

    result = verify_glyph_page(layer, table, render_image, dpi, expected=expected)
    entry, _, _ = reshumot_page_entry(
        data=data, pdf=pdf, page=page, page_image_count=page_image_count, raw_text="", poppler_version=render_file["rendering"]["renderer_version"],
        captured_at=captured_at, image_file=None,
    )
    stem = entry["entry_id"]
    logical = result.text
    printed = printed_page_number(logical)
    entry["page"]["printed_page_number"] = printed
    entry["title"] = entry["title"].rsplit(", page ", 1)[0] + f", page {printed or page}"
    files = [render_file]
    cropped = None
    if result.verdict.regions is not None and result.verdict.regions:
        crop = reshumot_crop_record(result.verdict.regions, float(layer["page"]["width"]), float(layer["page"]["height"]))
        crop["box_px"] = list(crop_pixel_box(crop["box_normalized"], *render_image.size))
        if crop.get("regions_normalized"):
            crop["regions_px"] = [list(box) for box in crop_region_boxes(crop, *render_image.size)]
            crop["mask_fill"] = crop_mask_fill(render_image, tuple(crop["box_px"]))
        crop["units_left_out"] = dict(sorted(result.verdict.dropped.items()))
        crop["reason"] = "lines whose order, characters or ink could not be verified, page images, or ink no glyph explains"
        cropped = crop_image(render_image, crop)
        buffer = io.BytesIO()
        cropped.save(buffer, format="PNG", optimize=True)
        content = buffer.getvalue()
        crop_file = {
            "bytes": len(content),
            "height_px": cropped.size[1],
            "local_path": f"assets/{stem}__crop.png",
            "mime_type": "image/png",
            "pixel_sha256": _sha256(cropped.tobytes()),
            "rendering": {**render_file["rendering"], "crop_of": render_file["local_path"]},
            "role": RESHUMOT_CROP_ROLE,
            "sha256": _sha256(content),
            "width_px": cropped.size[0],
        }
        files = [crop_file, render_file]
        entry["crop"] = crop
        cropped = (cropped, content)
    elif result.verdict.dropped:
        entry["text_units_left_out"] = dict(sorted(result.verdict.dropped.items()))
    entry["files"] = files
    entry["pdf"]["page_image_count"] = page_image_count
    text = entry["text"]
    text["extraction"] = {
        "command": RESHUMOT_GLYPH_EXTRACTION_COMMAND.format(page=page),
        "extractor": "pdfminer.six (hocrgen.parsers.pdf_glyphs)",
        "extractor_version": layer.get("extractor_version"),
        "normalization": GEOMETRY_NORMALIZATION_VERSION,
        "outline_table_path": RESHUMOT_OUTLINE_TABLE,
        "outline_table_sha256": table_sha256,
        "raw_local_path": f"extraction/{stem}.glyphs.json.gz",
        "raw_sha256": layer_sha256,
    }
    text["geometry"] = "glyph_layer"
    text["known_limitations"] = RESHUMOT_GLYPH_LIMITATIONS
    text["layout_notes"] = (["letter_spaced_run"] if result.conversion.layout.get("letter_spaced_segments") else [])
    text["order_verification"] = {
        "expected_phrases": expected_for.get("phrases", []),
        "issues": result.issues,
        "method": (
            "per segment: forward Unicode bidi algorithm reproduces the glyphs' visual order; per glyph: character from "
            "the outline identity table, ink on the render; per page: no ink outside kept glyphs in the pair image, "
            "order heuristics and gazette API phrases on the kept text"
        ),
        "facts": result.facts(),
    }
    text["sha256"] = _sha256(logical.encode("utf-8"))
    return entry, logical, result.issues, cropped


def reshumot_render_file(stem: str, png: bytes, pixel_sha256: str, size: tuple[int, int], *, page: int, poppler_version: str) -> dict[str, Any]:
    return {
        "bytes": len(png),
        "height_px": size[1],
        "local_path": f"assets/{stem}.png",
        "mime_type": "image/png",
        "pixel_sha256": pixel_sha256,
        "rendering": {
            "command": f"pdftoppm -f {page} -l {page} -r 150 -gray <pdf> <out>",
            "dpi": 150,
            "encoder": f"Pillow {PIL_VERSION} PNG (optimize=True) from the PGM; pixel_sha256 is over the decoded 8-bit pixels",
            "image_origin": "rendered_from_born_digital_pdf",
            "is_scan": False,
            "pixel_mode": "L",
            "renderer": "pdftoppm (poppler)",
            "renderer_version": poppler_version,
        },
        "role": "page_render",
        "sha256": _sha256(png),
        "width_px": size[0],
    }


def knesset_page_entry(
    *,
    document: dict[str, Any],
    pdf: dict[str, Any],
    page: int,
    image_row: list[str],
    png: bytes,
    pixel_sha256: str,
    size: tuple[int, int],
    poppler_version: str,
    captured_at: str,
) -> dict[str, Any]:
    """One Knesset committee page entry in the F8e snapshot format (images only)."""

    session = document["KNS_CommitteeSession"]
    committee = session.get("KNS_Committee") or {}
    info = pdf["info"]
    stem = f"knesset_committee_{document['Id']}__p{page:04d}"
    return {
        "committee": {"committee_id": committee.get("Id"), "name": committee.get("Name")},
        "content_type": "typewritten_historical",
        "direction": "rtl",
        "document": {
            "application_desc": document["ApplicationDesc"],
            "committee_session_id": document["CommitteeSessionID"],
            "document_id": document["Id"],
            "document_name": document["DocumentName"],
            "file_url": document["FilePath"],
            "group_type_desc": document["GroupTypeDesc"],
            "group_type_id": document["GroupTypeID"],
            "last_updated": document.get("LastUpdatedDate"),
        },
        "entry_id": stem,
        "files": [knesset_scan_file(stem, page, image_row, png, pixel_sha256, size, poppler_version=poppler_version)],
        "languages": ["he"],
        "page": {"pdf_page_index": page},
        "pdf": {
            "bytes": pdf["bytes"],
            "creation_date": info.get("CreationDate"),
            "creator": info.get("Creator"),
            "page_count": int(info.get("Pages", 0)),
            "producer": info.get("Producer"),
            "sha256": pdf["sha256"],
            "subject": info.get("Subject"),
        },
        "rights": {
            "basis": KNESSET_RIGHTS_BASIS,
            "evidence_text": KNESSET_RIGHTS_EVIDENCE,
            "license_expression": "PD-IL",
            "verification_status": "primary_page_checked",
            "verified_at": captured_at,
        },
        "script": "Hebr",
        "session": {
            "committee_session_id": session["Id"],
            "knesset_num": session.get("KnessetNum"),
            "note": session.get("Note"),
            "session_number": session.get("Number"),
            "session_url": session.get("SessionUrl"),
            "start_date": str(session["StartDate"])[:10],
            "type_desc": session.get("TypeDesc"),
        },
        "text": {
            "ocr_policy": "The PDF's hidden Imagestore OCR layer and the DOC OCR are machine OCR, never ground truth; not carried",
            "text_provenance": "none",
            "text_tier": 4,
        },
        "title": f"{committee.get('Name')}, ישיבה {session.get('Number')} ({str(session['StartDate'])[:10]}), page {page}",
        "upstream": {
            "odata_document_query": f"{KNESSET_ODATA}KNS_DocumentCommitteeSession?$filter=Id eq {document['Id']}",
            "odata_session_query": f"{KNESSET_ODATA}KNS_CommitteeSession?$filter=Id eq {document['CommitteeSessionID']}&$expand=KNS_Committee",
        },
    }


def single_scan_image_row(rows: list[list[str]], page: int) -> list[str] | None:
    """The one scan image of a page in ``pdfimages -list`` rows: a 1-bit image (CCITT, the 1949-2005 Imagestore scans)
    or an 8-bit JPEG (the colour rescans). None when the page is not exactly one such image."""

    # pdfimages -list columns: page num type width height color comp bpc enc interp object ID x-ppi y-ppi size ratio
    images = [row for row in rows if len(row) >= 14 and row[0] == str(page) and row[2] == "image"]
    if len(images) != 1:
        return None
    row = images[0]
    if row[7] == "1" or (row[7] == "8" and row[8] == "jpeg"):
        return row
    return None


def knesset_scan_file(
    stem: str, page: int, image_row: list[str], content: bytes, pixel_sha256: str, size: tuple[int, int], *, poppler_version: str
) -> dict[str, Any]:
    """The file record of one extracted page scan: a 1-bit PNG, or the embedded JPEG stream byte for byte."""

    bitonal = image_row[7] == "1"
    components = int(image_row[6]) if image_row[6].isdigit() else 1
    return {
        "bytes": len(content),
        "height_px": size[1],
        "local_path": f"assets/{stem}.{'png' if bitonal else 'jpg'}",
        "mime_type": "image/png" if bitonal else "image/jpeg",
        "pixel_sha256": pixel_sha256,
        "role": "page_scan",
        "scan": {
            "bits_per_pixel": 1 if bitonal else 8 * components,
            "command": f"pdfimages -f {page} -l {page} {'-png' if bitonal else '-j'} <pdf> <out>",
            "encoder": (
                f"Pillow {PIL_VERSION} PNG (optimize=True); pixel_sha256 is over the decoded 1-bit pixels"
                if bitonal
                else f"none: the PDF's embedded JPEG stream, unchanged (pdfimages -j); pixel_sha256 is over the decoded {image_row[5]} pixels"
            ),
            "extractor": "pdfimages (poppler)",
            "extractor_version": poppler_version,
            "image_origin": "embedded_scan_extracted_losslessly",
            "is_scan": True,
            "pdf_image_encoding": image_row[8],
            "pdf_image_object": int(image_row[10]),
            "x_ppi": int(image_row[12]),
            "y_ppi": int(image_row[13]),
        },
        "sha256": _sha256(content),
        "width_px": size[0],
    }


# --- poppler (operator machines only) ------------------------------------------------------------------------------


def _run(args: list[str]) -> str:  # pragma: no cover - poppler
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def poppler_version() -> str:  # pragma: no cover - poppler
    return subprocess.run(["pdftoppm", "-v"], capture_output=True, text=True).stderr.split("\n")[0].split()[-1]


def pdf_facts(path: Path) -> dict[str, Any]:  # pragma: no cover - poppler
    info = {}
    for line in _run(["pdfinfo", str(path)]).splitlines():
        key, _, value = line.partition(":")
        info[key.strip()] = value.strip()
    fonts = sorted({line.split()[0].split("+", 1)[-1] for line in _run(["pdffonts", str(path)]).splitlines()[2:] if line.strip()})
    rows = [line.split() for line in _run(["pdfimages", "-list", str(path)]).splitlines()[2:]]
    content = path.read_bytes()
    return {"info": info, "fonts": fonts, "image_rows": rows, "sha256": _sha256(content), "bytes": len(content)}


def pdf_page_text(path: Path, page: int) -> str:  # pragma: no cover - poppler
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "page.txt"
        subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-enc", "UTF-8", str(path), str(out)], check=True)
        return out.read_text(encoding="utf-8")


def render_gray_page(path: Path, page: int) -> tuple[bytes, str, tuple[int, int]]:  # pragma: no cover - poppler
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-r", "150", "-gray", str(path), f"{tmp}/r"], check=True)
        image = Image.open(next(Path(tmp).glob("r-*.pgm")))
        image.load()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), _sha256(image.tobytes()), image.size


def extract_scan_page(path: Path, page: int, image_row: list[str]) -> tuple[bytes, str, tuple[int, int]] | None:  # pragma: no cover - poppler
    bitonal = image_row[7] == "1"
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["pdfimages", "-f", str(page), "-l", str(page), "-png" if bitonal else "-j", str(path), f"{tmp}/i"], check=True)
        files = sorted(Path(tmp).glob("i-*.png" if bitonal else "i-*.jpg"))
        if len(files) != 1:
            return None
        content = files[0].read_bytes()
        image = Image.open(io.BytesIO(content))
        image.load()
    if bitonal:
        if image.mode != "1":
            return None
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        content = buffer.getvalue()
    return content, _sha256(image.tobytes()), image.size


# --- capture (network) ---------------------------------------------------------------------------------------------


def _request(url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> bytes:  # pragma: no cover - network
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT, **(headers or {})}, method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def _log(cache: Path, record: dict[str, Any]) -> None:  # pragma: no cover - network
    path = cache / "capture_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **record}, ensure_ascii=False, sort_keys=True) + "\n")


def capture_reshumot(
    cache: Path,
    *,
    hebrew_years: Iterable[int],
    seed: str,
    per_query: int,
    max_pages: int,
    delay: float,
    log: Callable[[str], None] = print,
) -> dict[str, int]:  # pragma: no cover - network
    """Search each (series, Hebrew year) once and fetch the sampled booklets' PDFs into ``cache/reshumot/``."""

    root = cache / "reshumot"
    counts = {"searches": 0, "search_failures": 0, "pdfs_fetched": 0, "pdfs_cached": 0, "pdf_failures": 0}
    booklets_path = root / "booklets.jsonl"
    known = {}
    if booklets_path.is_file():
        for line in booklets_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            known[(row["FolderType"], row["BookletNum"])] = row
    headers = {
        "Content-Type": "application/json",
        "x-client-id": RESHUMOT_CLIENT_ID,
        "Origin": "https://www.gov.il",
        "Referer": "https://www.gov.il/",
    }
    for hebrew_year in hebrew_years:
        for folder_type in RESHUMOT_SERIES:
            year_index = reshumot_booklet_year_index(hebrew_year)
            search_path = root / "search" / f"ft{folder_type}_y{year_index}_s0.json"
            if search_path.is_file():
                answer = json.loads(search_path.read_text(encoding="utf-8"))
            else:
                body = json.dumps({"FolderType": folder_type, "BookletYear": year_index, "skip": 0}).encode()
                try:
                    raw = _request(RESHUMOT_SEARCH_URL, data=body, headers=headers)
                    answer = json.loads(raw)
                    _write(search_path, raw)
                    counts["searches"] += 1
                    _log(root, {"kind": "search", "folder_type": folder_type, "booklet_year": year_index, "results": len(answer.get("Results") or [])})
                except Exception as exc:  # noqa: BLE001 - recorded and counted
                    counts["search_failures"] += 1
                    _log(root, {"kind": "search_failed", "folder_type": folder_type, "booklet_year": year_index, "error": repr(exc)})
                    time.sleep(delay)
                    continue
                time.sleep(delay)
            for data in select_reshumot_booklets(answer.get("Results") or [], seed=seed, per_query=per_query, max_pages=max_pages):
                key = (str(data["FolderType"]), str(data["BookletNum"]))
                pdf_path = root / "pdf" / f"{RESHUMOT_SERIES[key[0]][0]}_{key[1]}.pdf"
                if key in known and pdf_path.is_file() and _sha256(pdf_path.read_bytes()) == known[key]["pdf_sha256"]:
                    counts["pdfs_cached"] += 1
                    continue
                url = data["Document"][0]["FileName"]
                token = url.rsplit("/", 1)
                quoted = token[0] + "/" + urllib.parse.quote(token[1], safe="~")
                try:
                    content = _request(quoted, headers={"Referer": "https://www.gov.il/"})
                except Exception as exc:  # noqa: BLE001
                    counts["pdf_failures"] += 1
                    _log(root, {"kind": "pdf_failed", "booklet": key[1], "error": repr(exc)})
                    time.sleep(delay)
                    continue
                if not content.startswith(b"%PDF"):
                    counts["pdf_failures"] += 1
                    _log(root, {"kind": "pdf_not_pdf", "booklet": key[1], "bytes": len(content)})
                    time.sleep(delay)
                    continue
                _write(pdf_path, content)
                row = {**data, "pdf_sha256": _sha256(content), "pdf_bytes": len(content), "pdf_file": pdf_path.name}
                known[key] = row
                counts["pdfs_fetched"] += 1
                _log(root, {"kind": "pdf", "booklet": key[1], "folder_type": key[0], "bytes": len(content)})
                log(f"reshumot {key[0]}:{key[1]} ({data['PublishDate'][:10]}, {data['Pages']} pages)")
                time.sleep(delay)
    _write(booklets_path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for _, row in sorted(known.items())).encode())
    return counts


def _odata(query: str) -> dict[str, Any]:  # pragma: no cover - network
    return json.loads(_request(KNESSET_ODATA + query))


def capture_knesset(
    cache: Path,
    *,
    knesset_nums: Iterable[int],
    seed: str,
    per_knesset: int,
    delay: float,
    page_size: int = 100,
    log: Callable[[str], None] = print,
) -> dict[str, int]:  # pragma: no cover - network
    """Per Knesset term: one count query, one page of protocol PDFs at a seeded offset, then the sampled PDFs."""

    root = cache / "knesset"
    counts = {"queries": 0, "query_failures": 0, "pdfs_fetched": 0, "pdfs_cached": 0, "pdf_failures": 0}
    documents_path = root / "documents.jsonl"
    known = {}
    if documents_path.is_file():
        for line in documents_path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            known[row["Id"]] = row
    base_filter = (
        f"GroupTypeID eq 23 and ApplicationDesc eq 'PDF' and KNS_CommitteeSession/StartDate le {KNESSET_CUTOFF}"
        " and KNS_CommitteeSession/KnessetNum eq {k}"
    )
    expand = "KNS_CommitteeSession($expand=KNS_Committee($select=Id,Name,KnessetNum))"
    for knesset_num in knesset_nums:
        listing_path = root / "odata" / f"k{knesset_num}.json"
        if listing_path.is_file():
            listing = json.loads(listing_path.read_text(encoding="utf-8"))
        else:
            filter_text = urllib.parse.quote(base_filter.format(k=knesset_num))
            try:
                count = _odata(f"KNS_DocumentCommitteeSession?$filter={filter_text}&$count=true&$top=0")["@odata.count"]
                counts["queries"] += 1
                time.sleep(delay)
                offset = int(seeded_key(seed, f"knesset:{knesset_num}"), 16) % max(1, count - page_size + 1) if count > page_size else 0
                listing = _odata(f"KNS_DocumentCommitteeSession?$filter={filter_text}&$top={page_size}&$skip={offset}&$orderby=Id&$expand={expand}")
                listing = {"count": count, "offset": offset, **listing}
                counts["queries"] += 1
                _write(listing_path, json.dumps(listing, ensure_ascii=False).encode())
                _log(root, {"kind": "odata", "knesset_num": knesset_num, "count": count, "offset": offset, "rows": len(listing.get("value") or [])})
            except Exception as exc:  # noqa: BLE001
                counts["query_failures"] += 1
                _log(root, {"kind": "odata_failed", "knesset_num": knesset_num, "error": repr(exc)})
                log(f"knesset {knesset_num}: OData failed ({exc!r}); stopping the Knesset capture")
                break
            time.sleep(delay)
        for document in select_knesset_documents(listing.get("value") or [], seed=seed, count=per_knesset):
            pdf_path = root / "pdf" / f"{document['Id']}.pdf"
            if document["Id"] in known and pdf_path.is_file() and _sha256(pdf_path.read_bytes()) == known[document["Id"]]["pdf_sha256"]:
                counts["pdfs_cached"] += 1
                continue
            try:
                content = _request(document["FilePath"])
            except Exception as exc:  # noqa: BLE001
                counts["pdf_failures"] += 1
                _log(root, {"kind": "pdf_failed", "document_id": document["Id"], "error": repr(exc)})
                log(f"knesset document {document['Id']}: {exc!r}; stopping the Knesset capture")
                _write(documents_path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for _, row in sorted(known.items())).encode())
                return counts
            if not content.startswith(b"%PDF"):
                counts["pdf_failures"] += 1
                _log(root, {"kind": "pdf_not_pdf", "document_id": document["Id"], "bytes": len(content)})
                log(f"knesset document {document['Id']}: not a PDF ({len(content)} bytes); stopping the Knesset capture")
                break
            _write(pdf_path, content)
            known[document["Id"]] = {**document, "pdf_sha256": _sha256(content), "pdf_bytes": len(content), "pdf_file": pdf_path.name}
            counts["pdfs_fetched"] += 1
            _log(root, {"kind": "pdf", "document_id": document["Id"], "bytes": len(content)})
            log(f"knesset {knesset_num}: {document['DocumentName']} ({len(content)} bytes)")
            time.sleep(delay)
    _write(documents_path, "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for _, row in sorted(known.items())).encode())
    return counts


# --- materialize (offline, poppler) --------------------------------------------------------------------------------


def _json_lines(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")


def _count(counter: dict[str, int], reason: str) -> None:
    counter[reason] = counter.get(reason, 0) + 1


def materialize_reshumot(
    *,
    cache: Path,
    out_root: Path,
    packaged_root: Path,
    source: Any,
    captured_at: str,
    gate: Callable[[dict[str, Any], Any, Path], list[str]],
    outline_table: Path,
    layer_cache: Path | None = None,
    report: Path | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:  # pragma: no cover - poppler and pdfminer.six; exercised by the operator run
    """Every page of every cached booklet through the F8e2 method and the gate; only admitted pages are written.

    Each page's glyph layer is extracted with pdfminer.six (``hocrgen.parsers.pdf_glyphs``; ``layer_cache`` may hold
    layers extracted before, used only when their extractor version is the installed one), rendered with pdftoppm,
    converted, checked and, where needed, cropped to its verified regions (``reshumot_glyph_page_entry``). The gate
    then re-derives everything from the written files.
    """

    import yaml
    from PIL import Image

    from pdfminer import __version__ as pdfminer_version

    from hocrgen.parsers.pdf_glyphs import extract_glyph_layer

    root = out_root / "sources" / "reshumot_born_digital" / "snapshot"
    version = poppler_version()
    table_bytes = outline_table.read_bytes()
    table = json.loads(table_bytes)
    _write(root / RESHUMOT_OUTLINE_TABLE, table_bytes)
    table_sha = _sha256(table_bytes)
    entries: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    issues_seen: dict[str, int] = {}
    pages: list[dict[str, Any]] = []
    booklets_path = cache / "reshumot" / "booklets.jsonl"
    rows = [json.loads(line) for line in booklets_path.read_text(encoding="utf-8").splitlines()] if booklets_path.is_file() else []
    booklet_results = []
    for row in sorted(rows, key=lambda row: (row["FolderType"], row["BookletNum"])):
        pdf_path = cache / "reshumot" / "pdf" / row["pdf_file"]
        facts = pdf_facts(pdf_path)
        if facts["sha256"] != row["pdf_sha256"]:
            raise RuntimeError(f"cached Reshumot PDF {pdf_path.name} does not match its capture checksum")
        passed = 0
        for page in range(1, int(facts["info"].get("Pages", 0)) + 1):
            image_count = sum(1 for image_row in facts["image_rows"] if image_row and image_row[0] == str(page) and image_row[2] == "image")
            stem = f"{RESHUMOT_SERIES[str(row['FolderType'])][0]}_{row['BookletNum']}__p{page:04d}"
            cached = layer_cache / f"{stem}.json" if layer_cache else None
            layer = json.loads(cached.read_text(encoding="utf-8")) if cached and cached.is_file() else None
            if layer is None or layer.get("extractor_version") != pdfminer_version:
                layer = extract_glyph_layer(pdf_path, page)
            layer_bytes = glyph_layer_bytes(layer)
            png, pixel_sha, size = render_gray_page(pdf_path, page)
            render_file = reshumot_render_file(stem, png, pixel_sha, size, page=page, poppler_version=version)
            with Image.open(io.BytesIO(png)) as render_image:
                render_image.load()
                entry, logical, issues, cropped = reshumot_glyph_page_entry(
                    data=row, pdf=facts, page=page, page_image_count=image_count, layer=layer, layer_sha256=_sha256(layer_bytes),
                    table=table, table_sha256=table_sha, render_file=render_file, render_image=render_image, captured_at=captured_at,
                )
            for issue in issues:
                _count(issues_seen, issue)
            written = [entry["text"]["extraction"]["raw_local_path"], entry["text"]["local_path"], render_file["local_path"]]
            _write(root / written[0], layer_bytes)
            _write(root / written[1], logical.encode("utf-8"))
            _write(root / written[2], png)
            if cropped is not None:
                written.append(entry["files"][0]["local_path"])
                _write(root / written[-1], cropped[1])
            reasons = gate(entry, source, root)
            pages.append({
                "entry_id": stem, "year": str(row["PublishDate"])[:4], "series": RESHUMOT_SERIES[str(row["FolderType"])][0],
                "admitted": not reasons, "reasons": reasons, "cropped": "crop" in entry,
                "units_left_out": (entry.get("crop") or {}).get("units_left_out") or entry.get("text_units_left_out") or {},
            })
            if reasons:
                _count(skipped, reasons[0])
                for relative in written:
                    (root / relative).unlink(missing_ok=True)
                continue
            entries.append(entry)
            passed += 1
        booklet_results.append({"booklet": f"{row['FolderType']}:{row['BookletNum']}", "pages": int(facts["info"].get("Pages", 0)), "passed": passed})
    captured_ids = {entry["entry_id"] for entry in entries}
    packaged = [json.loads(line) for line in (packaged_root / "entries.jsonl").read_text(encoding="utf-8").splitlines()]
    for entry in packaged:
        if entry["entry_id"] in captured_ids or gate(entry, source, packaged_root):
            continue
        for relative in [file["local_path"] for file in entry["files"]] + [entry["text"]["local_path"], entry["text"]["extraction"]["raw_local_path"]]:
            _write(root / relative, (packaged_root / relative).read_bytes())
        entries.append(entry)
    entries.sort(key=lambda entry: entry["entry_id"])
    _write(root / "entries.jsonl", _json_lines(entries))
    snapshot = yaml.safe_load((packaged_root / "snapshot.yaml").read_text(encoding="utf-8"))
    snapshot.update(
        {
            "captured_at": captured_at,
            "capture": (
                "F8g2 operator capture through hocrgen.tools.real_tranche capture --source reshumot: one gazette search per "
                "series and Hebrew year, seeded booklet sample, throttled, descriptive User-Agent; raw PDFs stay in the "
                "operator cache and each entry pins the PDF sha256."
            ),
            "scope": "tranche",
            "notes": (
                "F8e2 tranche. Every page of every captured booklet was converted from its glyph layer (pdf_glyph_geometry_"
                "logical.v1), checked against its render and cropped to its verified regions where needed; the gate re-derives "
                "and re-checks each admitted page. The packaged F8e fixture's admitted pages (pdftotext, poppler_bidi_logical.v1) "
                "are kept as packaged."
            ),
        }
    )
    _write(root / "snapshot.yaml", yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False).encode())
    by_year: dict[str, dict[str, int]] = {}
    for record in pages:
        counts = by_year.setdefault(record["year"], {"pages": 0, "admitted": 0, "cropped": 0})
        counts["pages"] += 1
        counts["admitted"] += record["admitted"]
        counts["cropped"] += record["admitted"] and record["cropped"]
    result = {
        "item_count": len(entries),
        "booklet_count": len(rows),
        "pages_checked": len(pages),
        "pages_passed": len(captured_ids),
        "pages_cropped": sum(1 for record in pages if record["admitted"] and record["cropped"]),
        "method": "pdf_glyph_geometry_logical.v1",
        "skipped": skipped,
        "order_issue_counts": issues_seen,
        "by_year": dict(sorted(by_year.items())),
        "booklets": booklet_results,
    }
    if report is not None:
        _write(report, _json_lines(pages))
    log(
        f"reshumot: {len(entries)} entries from {len(rows)} booklets; {len(captured_ids)}/{len(pages)} captured pages pass "
        f"({result['pages_cropped']} cropped); skipped {skipped}"
    )
    return result


def materialize_knesset(
    *,
    cache: Path,
    out_root: Path,
    packaged_root: Path,
    source: Any,
    captured_at: str,
    gate: Callable[[dict[str, Any], Any, Path], list[str]],
    log: Callable[[str], None] = print,
) -> dict[str, Any]:  # pragma: no cover - poppler; exercised by the operator run
    """Every page of every cached protocol through the unchanged F8e gate; only pages that are one embedded scan are written."""

    import yaml

    root = out_root / "sources" / "knesset_committee_protocols_pre1976" / "snapshot"
    version = poppler_version()
    entries: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    pages_checked = 0
    documents_path = cache / "knesset" / "documents.jsonl"
    rows = [json.loads(line) for line in documents_path.read_text(encoding="utf-8").splitlines()] if documents_path.is_file() else []
    document_results = []
    for row in sorted(rows, key=lambda row: row["Id"]):
        pdf_path = cache / "knesset" / "pdf" / row["pdf_file"]
        facts = pdf_facts(pdf_path)
        if facts["sha256"] != row["pdf_sha256"]:
            raise RuntimeError(f"cached Knesset PDF {pdf_path.name} does not match its capture checksum")
        passed = 0
        for page in range(1, int(facts["info"].get("Pages", 0)) + 1):
            pages_checked += 1
            image_row = single_scan_image_row(facts["image_rows"], page)
            extracted = extract_scan_page(pdf_path, page, image_row) if image_row else None
            if image_row is None or extracted is None:
                _count(skipped, "page_not_one_scan_image")
                continue
            png, pixel_sha, size = extracted
            entry = knesset_page_entry(
                document=row, pdf=facts, page=page, image_row=image_row, png=png, pixel_sha256=pixel_sha, size=size,
                poppler_version=version, captured_at=captured_at,
            )
            reasons = gate(entry, source, root)
            if reasons:
                _count(skipped, reasons[0])
                continue
            _write(root / entry["files"][0]["local_path"], png)
            entries.append(entry)
            passed += 1
        session = row["KNS_CommitteeSession"]
        document_results.append(
            {
                "document_id": row["Id"],
                "committee": (session.get("KNS_Committee") or {}).get("Name"),
                "knesset_num": session.get("KnessetNum"),
                "session_date": str(session.get("StartDate"))[:10],
                "pages": int(facts["info"].get("Pages", 0)),
                "passed": passed,
            }
        )
    captured_ids = {entry["entry_id"] for entry in entries}
    packaged = [json.loads(line) for line in (packaged_root / "entries.jsonl").read_text(encoding="utf-8").splitlines()]
    for entry in packaged:
        if entry["entry_id"] in captured_ids or gate(entry, source, packaged_root):
            continue
        for file in entry["files"]:
            _write(root / file["local_path"], (packaged_root / file["local_path"]).read_bytes())
        entries.append(entry)
    entries.sort(key=lambda entry: entry["entry_id"])
    _write(root / "entries.jsonl", _json_lines(entries))
    snapshot = yaml.safe_load((packaged_root / "snapshot.yaml").read_text(encoding="utf-8"))
    snapshot.update(
        {
            "captured_at": captured_at,
            "capture": (
                "F8g2 operator capture through hocrgen.tools.real_tranche capture --source knesset: per Knesset term one "
                "count query and one page of protocol PDFs at a seeded offset, then the seeded sample of PDFs, 15 s or more "
                "apart, descriptive User-Agent; raw PDFs stay in the operator cache and each entry pins the PDF sha256."
            ),
            "scope": "tranche",
            "notes": (
                "F8g2 tranche. Every page of every captured protocol was run through the unchanged F8e gate; pages that are "
                "not one embedded scan are left out. Images only. The packaged fixture's admitted pages are kept."
            ),
        }
    )
    _write(root / "snapshot.yaml", yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False).encode())
    result = {
        "item_count": len(entries),
        "document_count": len(rows),
        "pages_checked": pages_checked,
        "pages_passed": len(captured_ids),
        "skipped": skipped,
        "documents": document_results,
    }
    log(f"knesset: {len(entries)} entries from {len(rows)} protocols; {len(captured_ids)}/{pages_checked} captured pages pass; skipped {skipped}")
    return result


def hebrew_years_since(start: date, end: date) -> list[int]:
    """Hebrew years whose span (about September to September) overlaps ``start``..``end``."""

    return list(range(start.year + 3760, end.year + 3761 + 1))


# --- glyph outline identities (F8e2) -------------------------------------------------------------------------------

GLYPH_OUTLINE_SCHEMA = "hocrgen.glyph_outline_identities.v1"
# Characters one outline may legitimately stand for: mirrored brackets (the ToUnicode text is the logical character,
# which depends on the run direction) and dashes (one shape set as hyphen, en dash, em dash or maqaf).
GLYPH_VARIANT_SETS = [["(", ")"], ["[", "]"], ["{", "}"], ["<", ">"], ["-", "‑", "–", "—", "―", "־"]]


def glyph_outline_table_bytes(table: dict[str, Any]) -> bytes:
    """The committed form of the outline table: its header fields, then one outline per line, sorted."""

    header = {key: value for key, value in table.items() if key != "outlines"}
    lines = ["{"]
    lines.extend(f" {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}," for key, value in header.items())
    lines.append(' "outlines": {')
    items = sorted(table["outlines"].items())
    lines.extend(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}{',' if index < len(items) - 1 else ''}" for index, (key, value) in enumerate(items))
    lines.extend([" }", "}"])
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_glyph_outline_table(layers: Iterable[dict[str, Any]], checks: dict[str, dict[str, Any]], *, built_from: str) -> dict[str, Any]:
    """The outline identity table from glyph layers: per outline hash, the ToUnicode characters seen and the
    character it stands for.

    An outline whose non-whitespace ToUnicode readings are one character, or all inside one variant set, takes them.
    An outline with conflicting readings (a full stop also read as a space or ``פ``) needs a recorded check in
    ``checks`` naming its character; without one it is left with no character, so every glyph that uses it is
    unverified.
    """

    from hocrgen.parsers.pdf_geometry import _whitespace

    readings: dict[str, dict[str, int]] = {}
    fonts: dict[str, set[str]] = {}
    for layer in layers:
        records = layer.get("fonts") or []
        for glyph in layer.get("glyphs") or []:
            font = records[glyph[9]] if glyph[9] < len(records) else {}
            outline = (font.get("outlines") or {}).get(str(glyph[11]))
            if not outline:
                continue
            counts = readings.setdefault(outline, {})
            counts[glyph[1]] = counts.get(glyph[1], 0) + 1
            fonts.setdefault(outline, set()).add(str(font.get("name", "")).split("+")[-1])
    outlines: dict[str, Any] = {}
    unresolved = 0
    for outline in sorted(readings):
        counts = readings[outline]
        texts = {text for text in counts if not _whitespace(text)}
        entry: dict[str, Any] = {"tounicode": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))), "typefaces": sorted(fonts[outline])}
        check = checks.get(outline)
        group = next((variants for variants in GLYPH_VARIANT_SETS if texts and texts <= set(variants)), None)
        if check and check.get("shape"):
            # A bracket: the character follows from the drawn shape and the run direction, not from ToUnicode.
            entry["char"] = None
            entry["accept"] = []
            entry["shape"] = check["shape"]
            entry["check"] = {key: check[key] for key in ("checked_by", "checked_at", "method", "finding") if key in check}
        elif check:
            entry["char"] = check["char"]
            entry["accept"] = sorted({check["char"], *check.get("accept_also", [])})
            entry["check"] = {key: check[key] for key in ("checked_by", "checked_at", "method", "finding") if key in check}
        elif not texts:
            entry["char"] = None
            entry["accept"] = sorted(counts)
        elif len(texts) == 1:
            (char,) = texts
            entry["char"] = char
            entry["accept"] = [char]
        elif group is not None:
            entry["char"] = None
            entry["accept"] = sorted(texts)
        else:
            entry["char"] = None
            entry["accept"] = []
            unresolved += 1
        outlines[outline] = entry
    return {
        "schema": GLYPH_OUTLINE_SCHEMA,
        "built_from": built_from,
        "method": (
            "Outline = first 16 hex digits of the SHA-256 of the glyph's TrueType glyf bytes (hocrgen.parsers.pdf_glyphs). "
            "An outline read as one character by every font's ToUnicode map takes it; conflicting readings are settled "
            "only by a recorded check of the rendered glyphs. A bracket outline records its drawn shape: its character is "
            "the shape in a left-to-right run and the mirror image in a right-to-left run (UBA L4), whatever ToUnicode says, "
            "because the subsets disagree on which of the pair they name."
        ),
        "variant_sets": GLYPH_VARIANT_SETS,
        "unresolved": unresolved,
        "outlines": outlines,
    }
