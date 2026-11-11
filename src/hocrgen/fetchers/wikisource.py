"""Fixture-backed review-only adapter for Hebrew Wikisource ProofreadPage pages (F8b).

Each item is one ``עמוד:`` (Page) page at quality 3 (proofread) or 4 (validated), paired with that page of
its Index's Commons PDF/DjVu file. The adapter reads a pinned snapshot only; it never calls the network and
never edits Wikisource or Commons.

Admission is per Index, on evidence that the work is public domain in Israel (maintainer decisions, 2026-11-06).
Decision 10 (F8b3): missing Commons or Wikidata evidence is a data gap to resolve, not a rights problem. A
faithful reproduction of a PD work needs no recorded scan source or licence template, the Commons tag
(``PD-US-*``, missing or other) never decides the work's status, and a work published on or before 1855 is
presumed PD even when no creator death year is found. Real protection still excludes: a creator who died
after 1955, and the Birnbaum Siddur (1949) and Haggadah (1953). Decision 9: Google-digitized scans are
admitted; ``digitized_by_google`` is provenance only. The Index must record its language as Hebrew (``he``).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import urllib.parse
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from PIL import Image

from hocrgen.config.loader import ConfigBundle, load_yaml_file, package_root
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import (
    AcquiredAsset,
    AcquiredItemRecord,
    AssetReference,
    BenchmarkTranscriptionReferenceRecord,
    CandidateRecord,
    EnrichedCandidateRecord,
)
from hocrgen.parsers.wikitext import (
    WIKITEXT_NORMALIZATION_VERSION,
    UnsupportedWikitextError,
    WikitextConversion,
    convert_wikitext,
    pagequality_level,
)
from hocrgen.reference_audit import apply_reference_audit
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file

WIKISOURCE_SNAPSHOT_SETTING = "wikisource_snapshot_root"
WIKISOURCE_SITE_URL = "https://he.wikisource.org"
TEXT_LICENSE = "CC-BY-SA-4.0"

ADMITTED_QUALITY_LEVELS = {3: "proofread", 4: "validated"}
PD_ISRAEL_DEATH_CUTOFF_YEAR = 1955
PD_ISRAEL_ANONYMOUS_PUBLICATION_CUTOFF_YEAR = 1955
PD_ISRAEL_STATE_WORK_CUTOFF_YEAR = 1975
# Decision 10: a work published on or before 1855 is presumed PD in Israel even without a creator death year.
PD_ISRAEL_PRESUMPTION_PUBLICATION_CUTOFF_YEAR = 1855
WORK_RIGHTS_BASES = {
    "author_died_by_1955",
    "state_work_by_1975",
    "anonymous_published_by_1955",
    "presumed_pd_by_publication_age",
}
SCAN_RIGHTS_BASES = {"faithful_reproduction_of_pd_work", "explicit_open_licence"}
OPEN_SCAN_LICENCES = {"CC0-1.0", "PDM-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"}
ANONYMOUS_CREATOR_ROLES = {"anonymous", "pseudonymous"}
# Team lead, hocrgen#171 review (2026-11-11): a cited floruit counts as an *author's* basis. A person active at the
# latest in year F died by F + FLORUIT_LIFESPAN_MARGIN; every other contributor still needs a cited death year
# (or a printing on or before 1855).
FLORUIT_LIFESPAN_MARGIN = 100
# Team lead, hocrgen#171 review: every commentary printed on the edition's pages must be named, with a cited death
# year (decision 10's 1855 presumption covers the death year only), and an edition that may be a later reprint with
# added material is not admitted until evidence clears it. Both fail closed.
PRINTED_COMMENTARY_REASONS = ("printed_commentary_unnamed", "printed_commentary_unattributed",
                              "printed_commentary_death_year_missing")
REPRINT_REASON = "possible_later_reprint"
# Team-lead decision (F8b3, 2026-11-06): the source is Hebrew. The Index's recorded language must be ``he``.
INDEX_LANGUAGE = "he"
# Page reasons that mean the pinned snapshot itself is broken; source health reports them as errors.
WIKISOURCE_INTEGRITY_REASONS = {
    "wikitext_missing",
    "wikitext_checksum_mismatch",
    "page_text_checksum_mismatch",
    "page_text_file_missing",
    "page_text_file_mismatch",
    "transclusion_missing",
    "transclusion_checksum_mismatch",
    "text_adjustment_invalid",
    "text_adjustment_mismatch",
    "excluded_span_invalid",
}

# Maintainer decision (F8a decision 2, accepted 2026-11-06): not PD in Israel (Birnbaum died 1988).
EXCLUDED_INDEX_FILES = {
    "File:Philip Birnbaum - ha-Siddur ha-Shalem (The Daily Prayer Book,1949).pdf": "excluded_birnbaum_work",
    "File:Birnbaum Haggadah.pdf": "excluded_birnbaum_work",
}

# Decision 9 (2026-11-06): Google-digitized scans are admitted; the markers only inform the recorded provenance.
GOOGLE_DIGITIZATION_MARKERS = ("digitized by google", "google books", "books.google")
TRANSCRIPTION_COVERAGE_FULL = "full_page"
TRANSCRIPTION_COVERAGE_PARTIAL = "partial_page"
TRANSCRIPTION_COVERAGE_VALUES = {TRANSCRIPTION_COVERAGE_FULL, TRANSCRIPTION_COVERAGE_PARTIAL}
CROP_RESOLVED = "resolved"
# A multi-region crop's box is the union of its regions, to the rounding of the recorded boxes (F8b5).
CROP_REGION_UNION_TOLERANCE = 0.002
# Footnote marks: the printed mark (``*)``, ``1)``, ``(א``) is not typed by editors, so the converter writes the
# MediaWiki number as ``[n]``. Recorded per page so evaluation can mask the marks (F8b4).
FOOTNOTE_MARKER_STYLE = "bracketed_index"
# F8b7: reviewed per-file mappings from an editor's stand-in to the printed character, applied after conversion.
EDITOR_STANDINS_SCHEMA_VERSION = "wikisource_editor_standins.v1"
EDITOR_STANDIN_CONTEXTS = {
    # the stand-in between two Hebrew words (a Hebrew letter or point before it, a Hebrew letter after it, each at
    # most one space away): a printed mark between words, never part of a word, a number or markup
    "between_hebrew_words": re.compile(r"(?<=[\u0591-\u05c7\u05d0-\u05ea])( ?){stand_in}(?=( ?)[\u05d0-\u05ea])"),
}
# F8b7: text an agent or human check found not visible on the scan (an ink blot, a tear): kept in the reference,
# located on the page, and excluded from primary scoring (``illegible`` / ``exclude_primary`` reference spans).
EXCLUDED_SPAN_KINDS = {"illegible_on_scan"}

_LICENCE_TOKEN = re.compile(r"^(PD|CC|Cc-|GFDL|FAL|OGL|Copyrighted|Attribution)", re.IGNORECASE)
_BOT_NAME = re.compile(r"bot$", re.IGNORECASE)


def wikisource_snapshot_root(source: SourceConfig, bundle: ConfigBundle) -> Path:
    reference = source.settings.extra.get(WIKISOURCE_SNAPSHOT_SETTING)
    if not isinstance(reference, str) or not reference:
        raise StageExecutionError(f"{source.id} requires settings.extra.{WIKISOURCE_SNAPSHOT_SETTING}")
    return bundle.resolve_path(reference)


def load_wikisource_snapshot(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load the snapshot descriptor, Index evidence records (by ``index_key``) and page records."""

    snapshot = load_yaml_file(root / "snapshot.yaml")
    payload = json.loads((root / str(snapshot.get("indexes_path", "indexes.json"))).read_text(encoding="utf-8"))
    indexes = {record["index_key"]: record for record in payload["indexes"]}
    pages_path = root / str(snapshot.get("pages_path", "pages.jsonl"))
    pages = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return snapshot, indexes, pages


# --- Index (Commons file) admission ------------------------------------------------------------------------


def licence_tokens(index: dict[str, Any]) -> list[str]:
    """Licence template names on the Commons file page, including those nested as PD-scan arguments."""

    tokens: list[str] = []
    for template in (index.get("commons_file") or {}).get("licence_templates") or []:
        for part in str(template).split("|"):
            name = part.strip()
            if name and "=" not in name and _LICENCE_TOKEN.match(name):
                tokens.append(name)
    return tokens


def scan_source_origin(index: dict[str, Any]) -> str:
    """Provenance label for where the Commons scan came from. Informational only; it gates nothing."""

    commons = index.get("commons_file") or {}
    haystack = " ".join(
        str(value)
        for value in (
            commons.get("title"),
            commons.get("source_field"),
            commons.get("institution_field"),
            commons.get("provenance_text"),
            *(commons.get("categories") or []),
        )
        if value
    ).casefold()
    if "hebrewbooks" in haystack:
        return "hebrewbooks"
    if "opensiddur" in haystack or "open siddur" in haystack:
        return "open_siddur_project"
    if "national library of israel" in haystack:
        return "national_library_of_israel"
    if "archive.org" in haystack:
        return "internet_archive"
    return "unrecorded"


def index_exclusion_reasons(index: dict[str, Any]) -> list[str]:
    """Every reason an Index cannot be admitted; empty when (a) the work and (b) the scan are both evidenced."""

    reasons: list[str] = []
    commons = index.get("commons_file") or {}
    excluded = EXCLUDED_INDEX_FILES.get(str(commons.get("title")))
    if excluded:
        reasons.append(excluded)
    if not commons.get("sha1") or not commons.get("file_page_revision_id"):
        reasons.append("commons_file_unpinned")
    # Decision 10: the Commons licence template (PD-US-only, missing or other) never decides the work's status.
    reasons.extend(_work_rights_reasons(index))
    reasons.extend(_printed_commentary_reasons(index))
    reasons.extend(_reprint_reasons(index))
    reasons.extend(_scan_rights_reasons(index))
    reasons.extend(_language_reasons(index))
    return reasons


def floruit_basis(creator: dict[str, Any]) -> bool:
    """An author with no death year but a cited floruit early enough that they died by 1955 (hocrgen#171)."""

    floruit = creator.get("floruit") or {}
    latest = floruit.get("latest_year")
    return (
        creator.get("role") == "author"
        and isinstance(latest, int)
        and bool(floruit.get("evidence_url"))
        and latest + FLORUIT_LIFESPAN_MARGIN <= PD_ISRAEL_DEATH_CUTOFF_YEAR
    )


def _cited_death(creator: dict[str, Any]) -> bool:
    return isinstance(creator.get("death_year"), int) and bool(creator.get("death_year_evidence_url"))


def _printed_commentary_reasons(index: dict[str, Any]) -> list[str]:
    """Every commentary printed on the edition's pages is named and attributed to a contributor with a cited death
    year (``work.printed_commentaries``, recorded by the inventory). A printing on or before 1855 needs the name only."""

    work = index.get("work") or {}
    record = work.get("printed_commentaries") or {}
    detected = record.get("detected") or []
    if not detected:
        return []
    reasons: list[str] = []
    if any(signal.get("kind") == "unnamed" for signal in detected) and not record.get("complete"):
        reasons.append("printed_commentary_unnamed")
    year = work.get("published_year")
    early = isinstance(year, int) and year <= PD_ISRAEL_PRESUMPTION_PUBLICATION_CUTOFF_YEAR
    creators = {str(c.get("name")): c for c in work.get("creators") or []}
    attributions = record.get("attributed") or []
    for title in sorted({str(s["title"]) for s in detected if s.get("kind") == "named" and s.get("title")}):
        attribution = next((a for a in attributions if title in (a.get("titles") or [])), None)
        named = [creators.get(name) for name in (attribution or {}).get("creators") or []]
        if attribution is None or not named or any(c is None for c in named):
            reasons.append("printed_commentary_unattributed")
        elif not early and not all(_cited_death(c) or floruit_basis(c) for c in named if c is not None):
            reasons.append("printed_commentary_death_year_missing")
    return sorted(set(reasons), key=reasons.index)


def _reprint_reasons(index: dict[str, Any]) -> list[str]:
    check = (index.get("work") or {}).get("reprint_check") or {}
    return [REPRINT_REASON] if check.get("suspected") and not check.get("cleared") else []


def _language_reasons(index: dict[str, Any]) -> list[str]:
    """The Index must record Hebrew (``he``); another language or none recorded is rejected (F8b3).

    The language is the Index page's own field (``שפה``), else the Commons file's ``language`` field. An English
    Index such as *She* carries a Hebrew translation typed over an English scan, which is not a transcription.
    """

    language = (index.get("work") or {}).get("language")
    if not isinstance(language, str) or not language.strip():
        return ["index_language_unrecorded"]
    if language.strip() != INDEX_LANGUAGE:
        return ["index_language_not_hebrew"]
    return []


def index_exclusion_reason(index: dict[str, Any]) -> str | None:
    reasons = index_exclusion_reasons(index)
    return reasons[0] if reasons else None


def _work_rights_reasons(index: dict[str, Any]) -> list[str]:
    work = index.get("work") or {}
    rights = index.get("work_rights") or {}
    basis = rights.get("basis")
    if basis not in WORK_RIGHTS_BASES:
        return ["work_rights_basis_unsupported"]
    reasons: list[str] = []
    if not str(rights.get("evidence") or "").strip():
        reasons.append("work_rights_evidence_missing")
    creators = work.get("creators") or []
    if basis == "author_died_by_1955":
        if not creators:
            reasons.append("creators_missing")
        for creator in creators:
            death_year = creator.get("death_year")
            if not isinstance(death_year, int) or not creator.get("death_year_evidence_url"):
                if not floruit_basis(creator):
                    reasons.append("creator_death_year_missing")
            elif death_year > PD_ISRAEL_DEATH_CUTOFF_YEAR:
                reasons.append("creator_died_after_1955")
    elif basis == "presumed_pd_by_publication_age":
        published = work.get("published_year")
        if not isinstance(published, int) or not str(work.get("published_year_evidence") or "").strip():
            reasons.append("publication_year_missing")
        elif published > PD_ISRAEL_PRESUMPTION_PUBLICATION_CUTOFF_YEAR:
            reasons.append("published_after_1855")
        # A creator shown to have died after 1955 is real protection; the presumption never overrides it.
        if any(isinstance(c.get("death_year"), int) and c["death_year"] > PD_ISRAEL_DEATH_CUTOFF_YEAR for c in creators):
            reasons.append("creator_died_after_1955")
    elif basis == "state_work_by_1975":
        created = work.get("created_year")
        if not isinstance(created, int) or not work.get("state_body"):
            reasons.append("state_work_evidence_missing")
        elif created > PD_ISRAEL_STATE_WORK_CUTOFF_YEAR:
            reasons.append("state_work_after_1975")
    else:
        published = work.get("published_year")
        if any(creator.get("role") not in ANONYMOUS_CREATOR_ROLES for creator in creators):
            reasons.append("named_creator_on_anonymous_basis")
        if not isinstance(published, int):
            reasons.append("publication_year_missing")
        elif published > PD_ISRAEL_ANONYMOUS_PUBLICATION_CUTOFF_YEAR:
            reasons.append("anonymous_work_after_1955")
    return sorted(set(reasons), key=reasons.index)


def _scan_rights_reasons(index: dict[str, Any]) -> list[str]:
    rights = index.get("scan_rights") or {}
    basis = rights.get("basis")
    if basis not in SCAN_RIGHTS_BASES:
        return ["scan_rights_basis_unsupported"]
    reasons: list[str] = []
    if not str(rights.get("evidence") or "").strip():
        reasons.append("scan_rights_evidence_missing")
    if basis == "explicit_open_licence" and rights.get("licence") not in OPEN_SCAN_LICENCES:
        reasons.append("scan_licence_not_open")
    # Decision 10: a faithful reproduction of a PD work needs no recorded scan source; record it where known.
    # Decision 9: a Google-digitized scan is admitted; ``digitized_by_google`` stays provenance only.
    return reasons


def scan_source_recorded(scan_source: Any) -> bool:
    """A scan source counts as recorded only as a named scanning body plus the evidence naming it (provenance).

    A non-empty Commons ``source`` field is not enough: it often repeats the book's title or imprint.
    """

    if not isinstance(scan_source, dict):
        return False
    return bool(str(scan_source.get("name") or "").strip()) and bool(str(scan_source.get("evidence") or "").strip())


def digitized_by_google(index: dict[str, Any]) -> bool | None:
    """Provenance only (decision 9): True when recorded or when the Commons record names Google; else the record."""

    commons = index.get("commons_file") or {}
    rights = index.get("scan_rights") or {}
    haystack = " ".join(
        str(value)
        for value in (
            commons.get("source_field"),
            commons.get("institution_field"),
            commons.get("provenance_text"),
            rights.get("evidence"),
            *(commons.get("categories") or []),
        )
        if value
    ).casefold()
    if rights.get("digitized_by_google") is True or any(marker in haystack for marker in GOOGLE_DIGITIZATION_MARKERS):
        return True
    return rights.get("digitized_by_google")


# --- Page admission and attestation ------------------------------------------------------------------------


def _quality_editors(page: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (proofreader, validator): the history entries that set quality 3 and, for quality 4, 4."""

    history = page.get("quality_history") or []
    if not history:
        return None, None
    last = history[-1]
    if page.get("quality") == 4:
        validator = last if last.get("level") == 4 else None
        proofreader = next((entry for entry in reversed(history[:-1]) if entry.get("level") == 3), None)
        return proofreader, validator
    return (last if last.get("level") == 3 else None), None


def _is_named_human(entry: dict[str, Any]) -> bool:
    name = str(entry.get("user") or "")
    return bool(name) and int(entry.get("user_id") or 0) > 0 and "bot" not in (entry.get("user_groups") or []) and not _BOT_NAME.search(name)


def pagequality_attribute_names_editor(entry: dict[str, Any]) -> bool:
    """Whether the ``<pagequality user=...>`` attribute names the editor who set that quality (F8b5).

    The attribute keeps the username at the time of the edit, while the page history shows the account's current
    name. It names the editor when it equals that name, or when the account was renamed from it after the edit: a
    recorded rename (``user_renames``, from the global or local rename log, with its log id and timestamp) made after
    the quality edit, whose chain of renames ends at the current name. Nothing else matches.
    """

    attribute, user = entry.get("pagequality_user_attribute"), entry.get("user")
    if attribute == user:
        return True
    names = {user}
    edited = str(entry.get("timestamp") or "")
    renames = [
        rename
        for rename in entry.get("user_renames") or []
        if rename.get("log_id") and rename.get("old") and rename.get("new") and edited and str(rename.get("timestamp") or "") > edited
    ]
    changed = True
    while changed:
        changed = False
        for rename in renames:
            if rename["new"] in names and rename["old"] not in names:
                names.add(rename["old"])
                changed = True
    return attribute in names


def page_exclusion_reasons(page: dict[str, Any], indexes: dict[str, dict[str, Any]], root: Path) -> list[str]:
    reasons: list[str] = []
    index = indexes.get(str(page.get("index_key")))
    if index is None:
        reasons.append("index_not_in_snapshot")
    elif index_exclusion_reasons(index):
        reasons.append("index_not_admitted")
    quality = page.get("quality")
    if quality not in ADMITTED_QUALITY_LEVELS:
        reasons.append("quality_not_proofread")
        return reasons
    history = page.get("quality_history") or []
    if not history or history[-1].get("level") != quality:
        reasons.append("quality_history_mismatch")
    proofreader, validator = _quality_editors(page)
    editors = [proofreader] + ([validator] if quality == 4 else [])
    if proofreader is None:
        reasons.append("proofreader_missing")
    if quality == 4 and validator is None:
        reasons.append("validator_missing")
    present = [entry for entry in editors if entry is not None]
    if any(not _is_named_human(entry) for entry in present):
        reasons.append("quality_editor_not_named_human")
    if any(not pagequality_attribute_names_editor(entry) for entry in present):
        reasons.append("quality_attribute_mismatch")
    if proofreader and validator and (
        proofreader.get("user") == validator.get("user") or proofreader.get("user_id") == validator.get("user_id")
    ):
        reasons.append("validator_is_proofreader")
    coverage = page.get("transcription_coverage")
    if coverage is None:
        reasons.append("transcription_coverage_unrecorded")
    elif coverage not in TRANSCRIPTION_COVERAGE_VALUES:
        reasons.append("transcription_coverage_unknown")
    # F8b6: a check found words in the text that the scan page does not show; text and image do not match.
    if str(page.get("text_not_on_page") or "").strip():
        reasons.append("text_not_on_page")
    # F8b7: the tool could not find a footnote of the text on the page (an unsigned editor's note, or small type OCR
    # misread). The page waits for an agent or human to compare its footnotes with the page.
    if (page.get("footnote_check") or {}).get("status") == "flagged" and not page.get("footnotes_reviewed"):
        reasons.append("footnote_not_located")
    # Decision 12: a partial_page transcription is not rejected; it is paired with its crop (F8b4).
    reasons.extend(page_crop_reasons(page))
    reasons.extend(_page_text_reasons(page, root))
    return reasons


def page_needs_crop(page: dict[str, Any]) -> bool:
    """Decision 12: a partial-page transcription is paired with the transcribed region only, after a crop (F8b4)."""

    return page.get("transcription_coverage") == TRANSCRIPTION_COVERAGE_PARTIAL


def page_crop_reasons(page: dict[str, Any]) -> list[str]:
    """A partial page pairs only through a resolved crop inside the page (F8b4, decision 12).

    ``crop_unrecorded``: no tool crop for the pinned revision and scan. ``crop_unresolved``: the tool could not
    place one (too little of the transcription located, or too much untranscribed text inside); such pages are
    reported, never silently dropped. ``crop_geometry_invalid``: the recorded box is not inside the page.
    """

    if not page_needs_crop(page):
        return []
    crop = page.get("crop")
    if not isinstance(crop, dict):
        return ["crop_unrecorded"]
    if crop.get("status") != CROP_RESOLVED:
        return ["crop_unresolved"]
    if not crop_geometry_valid(crop):
        return ["crop_geometry_invalid"]
    return []


def crop_geometry_valid(crop: dict[str, Any]) -> bool:
    """A resolved crop's geometry: its box inside the page and, for a multi-region crop (F8b5), at least two regions,
    each inside the page, whose union is the box (to the rounding of the recorded boxes)."""

    if not crop_box_valid(crop.get("box_normalized")):
        return False
    regions = crop.get("regions_normalized")
    if regions is None:
        return True
    if not isinstance(regions, list) or len(regions) < 2 or not all(crop_box_valid(region) for region in regions):
        return False
    union = [min(r[0] for r in regions), min(r[1] for r in regions), max(r[2] for r in regions), max(r[3] for r in regions)]
    return all(abs(a - b) <= CROP_REGION_UNION_TOLERANCE for a, b in zip(union, crop["box_normalized"]))


def crop_box_valid(box: Any) -> bool:
    """A normalised box ``[x0, y0, x1, y1]`` inside the page, with positive width and height."""

    if not isinstance(box, list) or len(box) != 4 or not all(isinstance(value, (int, float)) for value in box):
        return False
    x0, y0, x1, y1 = box
    return 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1


def crop_pixel_box(box_normalized: list[float], width: int, height: int) -> tuple[int, int, int, int]:
    """The crop box in an image of this size: the normalised box scaled, rounded outward, clamped to the image."""

    x0, y0, x1, y1 = box_normalized
    return (
        max(0, math.floor(x0 * width)),
        max(0, math.floor(y0 * height)),
        min(width, math.ceil(x1 * width)),
        min(height, math.ceil(y1 * height)),
    )


def crop_region_boxes(crop: dict[str, Any], width: int, height: int) -> list[tuple[int, int, int, int]]:
    """The regions of a multi-region crop in an image of this size (each rounded outward); empty for a one-box crop."""

    return [crop_pixel_box(region, width, height) for region in crop.get("regions_normalized") or []]


def crop_mask_fill(page_image: Image.Image, box: tuple[int, int, int, int]) -> list[int]:
    """The page background under a crop box: the upper-quartile value of each RGB channel (print is darker)."""

    histograms = page_image.convert("RGB").crop(box).histogram()
    fill = []
    for channel in range(3):
        counts = histograms[channel * 256 : (channel + 1) * 256]
        target, seen = 0.75 * sum(counts), 0
        for value, count in enumerate(counts):
            seen += count
            if seen >= target:
                fill.append(value)
                break
    return fill


def crop_image(page_image: Image.Image, crop: dict[str, Any]) -> Image.Image:
    """The image a partial page pairs with: the page cut at the crop box (F8b4).

    For a multi-region crop (F8b5) every pixel of the box outside the regions is set to the recorded ``mask_fill``
    (the page background), and each region is pasted from the page unchanged, so the transcribed pixels are the
    page's own. Masking keeps the regions where they stand on the page.
    """

    rgb = page_image.convert("RGB")
    box = crop_pixel_box(crop["box_normalized"], *rgb.size)
    regions = crop_region_boxes(crop, *rgb.size)
    if not regions:
        return rgb.crop(box)
    canvas = Image.new("RGB", (box[2] - box[0], box[3] - box[1]), tuple(int(value) for value in crop["mask_fill"]))
    for region in regions:
        canvas.paste(rgb.crop(region), (region[0] - box[0], region[1] - box[1]))
    return canvas


def crop_asset_problems(page: dict[str, Any], root: Path) -> list[str]:
    """Integrity of a cropped page's assets (source health and acquisition).

    The crop asset must exist with its pinned SHA-256, and must be exactly the pinned page image cut at the
    recorded box: its size is the box's, the box lies inside the page image, and its pixels equal the page's.
    """

    crop = page.get("crop") or {}
    asset = crop.get("asset") or {}
    image = page.get("image") or {}
    if not asset.get("path"):
        return ["crop_asset_missing"]
    path = root / str(asset["path"])
    if not path.is_file():
        return ["crop_asset_missing"]
    if sha256_file(path) != asset.get("sha256"):
        return ["crop_asset_checksum_mismatch"]
    page_path = root / str(image.get("path", ""))
    if not page_path.is_file():
        return ["page_image_missing"]
    with Image.open(page_path) as page_image:
        page_image.load()
        box = crop_pixel_box(crop["box_normalized"], *page_image.size)
        if list(box) != list(crop.get("box_px") or []):
            return ["crop_geometry_mismatch"]
        if crop.get("regions_normalized") is not None:
            regions = crop_region_boxes(crop, *page_image.size)
            fill = crop.get("mask_fill")
            if [list(region) for region in regions] != [list(region) for region in crop.get("regions_px") or []]:
                return ["crop_geometry_mismatch"]
            if not (isinstance(fill, list) and len(fill) == 3 and all(isinstance(v, int) and 0 <= v <= 255 for v in fill)):
                return ["crop_mask_fill_invalid"]
        expected = crop_image(page_image, crop)
    with Image.open(path) as cropped:
        cropped = cropped.convert("RGB")
        if cropped.size != expected.size:
            return ["crop_geometry_mismatch"]
        if cropped.tobytes() != expected.tobytes():
            return ["crop_pixels_mismatch"]
    return []


def page_exclusion_reason(page: dict[str, Any], indexes: dict[str, dict[str, Any]], root: Path) -> str | None:
    reasons = page_exclusion_reasons(page, indexes, root)
    return reasons[0] if reasons else None


def page_transclusions(page: dict[str, Any], root: Path) -> dict[str, str]:
    """The pinned wikitext of every page this page transcludes by labelled section (F8b4), by title.

    Each is pinned by revision id and SHA-256 in ``page["transclusions"]``; a missing or altered file raises
    ``StageExecutionError`` (source health reports it as ``transclusion_missing`` / ``transclusion_checksum_mismatch``).
    """

    pinned: dict[str, str] = {}
    for entry in page.get("transclusions") or []:
        path = root / str(entry.get("wikitext_path", ""))
        if not entry.get("wikitext_path") or not path.is_file():
            raise StageExecutionError(f"transclusion_missing: {entry.get('title')}")
        wikitext = path.read_text(encoding="utf-8")
        if _sha256(wikitext) != entry.get("wikitext_sha256"):
            raise StageExecutionError(f"transclusion_checksum_mismatch: {entry.get('title')}")
        pinned[str(entry["title"])] = wikitext
    return pinned


@dataclass(frozen=True)
class PageText:
    """A page's text at each step (F8b7).

    ``faithful`` is the converter's MediaWiki rendering of the pinned wikitext; its SHA-256 is the raw-text checksum
    the page keeps (``text_adjustments.converted_text_sha256``). ``conversion`` drops the footnotes a reviewed check
    found not printed (``unprinted_notes``), and ``text`` then maps editors' stand-ins to the printed characters
    (``editor_standins``): it is the pair text. ``adjustments`` is the provenance of both steps, or ``None`` when the
    pair text is the faithful rendering.
    """

    faithful: WikitextConversion
    conversion: WikitextConversion
    text: str
    adjustments: dict[str, Any] | None


def page_file_name(page: dict[str, Any]) -> str:
    """The Index file a page belongs to, from its title (``עמוד:<file>/<n>``): the key of the stand-in mappings."""

    title = str(page.get("page_title") or "")
    return title.split(":", 1)[-1].rsplit("/", 1)[0]


@cache
def _packaged_editor_standins(path: str) -> tuple[dict[str, Any], ...]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema_version") != EDITOR_STANDINS_SCHEMA_VERSION:
        raise StageExecutionError(f"editor stand-in mappings must be {EDITOR_STANDINS_SCHEMA_VERSION}")
    mappings = tuple(payload.get("mappings") or [])
    for mapping in mappings:
        problems = editor_standin_problems(mapping)
        if problems:
            raise StageExecutionError(f"bad editor stand-in mapping {mapping.get('mapping_id')}: {', '.join(problems)}")
    return mappings


def editor_standins_path() -> Path:
    return package_root() / "data" / "wikisource" / "editor_standins.json"


def editor_standin_problems(mapping: dict[str, Any]) -> list[str]:
    """Schema problems of one reviewed stand-in mapping; empty when it is well formed."""

    problems = [f"missing {key}" for key in ("mapping_id", "stand_in", "printed", "context", "files", "checked_by", "checker", "checked_at", "method")
                if not mapping.get(key)]
    if mapping.get("context") and mapping["context"] not in EDITOR_STANDIN_CONTEXTS:
        problems.append(f"context must be one of {', '.join(sorted(EDITOR_STANDIN_CONTEXTS))}")
    if mapping.get("checked_by") and mapping["checked_by"] not in {"agent", "human"}:
        problems.append("checked_by must be agent or human")
    if len(str(mapping.get("stand_in") or "")) != 1 or len(str(mapping.get("printed") or "")) != 1:
        problems.append("stand_in and printed must be single characters")
    if not mapping.get("verified"):
        problems.append("a mapping must list the occurrences verified on page images")
    return problems


def editor_standins_for(page: dict[str, Any], mappings: tuple[dict[str, Any], ...] | None = None) -> list[dict[str, Any]]:
    """The reviewed stand-in mappings that apply to a page's Index file (F8b7)."""

    mappings = _packaged_editor_standins(str(editor_standins_path())) if mappings is None else mappings
    name = page_file_name(page)
    return [mapping for mapping in mappings if name in mapping["files"]]


def apply_editor_standins(text: str, mappings: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Replace each mapping's stand-in by the printed character where its context holds; returns the counts applied."""

    applied: list[dict[str, Any]] = []
    for mapping in mappings:
        pattern = re.compile(EDITOR_STANDIN_CONTEXTS[mapping["context"]].pattern.replace("{stand_in}", re.escape(mapping["stand_in"])))
        text, count = pattern.subn(lambda match: match.group(1) + mapping["printed"], text)
        if count:
            applied.append({"mapping_id": mapping["mapping_id"], "stand_in": mapping["stand_in"], "printed": mapping["printed"], "count": count})
    return text, applied


def unprinted_note_numbers(page: dict[str, Any]) -> list[int]:
    """Footnotes a reviewed check found not printed (F8b7), by the number the faithful conversion gives them."""

    return sorted({int(entry["note"]) for entry in page.get("unprinted_notes") or []})


def derive_page_text(
    wikitext: str, transclusions: dict[str, str], page: dict[str, Any], mappings: tuple[dict[str, Any], ...] | None = None
) -> PageText:
    """The page's pair text from its pinned wikitext: the faithful conversion, without the footnotes a reviewed check
    found not printed, with editors' stand-ins mapped to the printed characters (F8b7). Raises
    ``UnsupportedWikitextError`` on unknown markup and ``ValueError`` on an unprinted note the page does not have."""

    faithful = convert_wikitext(wikitext, transclusions)
    notes = unprinted_note_numbers(page)
    conversion = convert_wikitext(wikitext, transclusions, unprinted_notes=notes) if notes else faithful
    text, standins = apply_editor_standins(conversion.text, editor_standins_for(page, mappings))
    adjustments = None
    if notes or standins:
        adjustments = {"converted_text_sha256": _sha256(faithful.text), "unprinted_notes": notes, "editor_standins": standins}
    return PageText(faithful, conversion, text, adjustments)


# Converter features that change what the text holds relative to MediaWiki's literal rendering (v3, F8g2).
CONVERTER_TEXT_REPAIRS = (
    "editor_notes_dropped",
    "editor_headings_dropped",
    "broken_link_double_pipe",
    "broken_link_unclosed",
    "broken_link_unopened",
    "malformed_markup",
)


def text_derivation(derived: PageText) -> dict[str, Any]:
    """How a page's pair text was derived (F8g2, HeOCR/hocrgen#134), for provenance.

    ``converter`` is the ``wikisource_plain_text`` version; ``converter_repairs`` counts what it rendered as printed
    where MediaWiki shows editors' markup (signed editors' notes and note-list headings dropped, broken links reduced
    to their labels, stray brackets); ``unprinted_notes_dropped`` and ``editor_standins_applied`` are the F8b7 steps
    after conversion (reviewed footnotes found not printed, reviewed stand-in mappings).
    """

    adjustments = derived.adjustments or {}
    return {
        "converter": WIKITEXT_NORMALIZATION_VERSION,
        "converter_repairs": {name: derived.faithful.features[name] for name in CONVERTER_TEXT_REPAIRS if derived.faithful.features.get(name)},
        "unprinted_notes_dropped": list(adjustments.get("unprinted_notes") or []),
        "editor_standins_applied": [
            {"mapping_id": entry["mapping_id"], "count": entry["count"]} for entry in adjustments.get("editor_standins") or []
        ],
    }


def page_text_sha256_converted(page: dict[str, Any]) -> str | None:
    """The raw-text checksum: the SHA-256 of the faithful conversion (the pair text's, when nothing is adjusted)."""

    return (page.get("text_adjustments") or {}).get("converted_text_sha256") or page.get("text_sha256")


def excluded_span_problems(page: dict[str, Any], text: str) -> list[str]:
    """Problems of a page's recorded excluded spans (F8b7) against its pair text; empty when they are sound."""

    record = page.get("excluded_spans")
    if not record:
        return []
    if not isinstance(record, dict) or record.get("text_sha256") != _sha256(text):
        return ["excluded spans are pinned to another text"]
    problems: list[str] = []
    for span in record.get("spans") or []:
        start, end = span.get("start"), span.get("end")
        if span.get("kind") not in EXCLUDED_SPAN_KINDS:
            problems.append(f"span kind must be one of {', '.join(sorted(EXCLUDED_SPAN_KINDS))}")
        if not (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)):
            problems.append("span offsets must lie in the text")
        elif "\n" in text[start:end] or not text[start:end].strip():
            problems.append("a span must be non-blank text within one line")
        regions = span.get("regions_normalized")
        if not regions or not all(crop_box_valid(region) for region in regions):
            problems.append("a span must be located on the page by one or more boxes")
        if not str(span.get("detail") or "").strip():
            problems.append("a span must say why the text is not visible")
    return problems if record.get("spans") else ["excluded spans record no span"]


def _page_text_reasons(page: dict[str, Any], root: Path) -> list[str]:
    wikitext_path = root / str(page.get("wikitext_path", ""))
    if not page.get("wikitext_path") or not wikitext_path.is_file():
        return ["wikitext_missing"]
    wikitext = wikitext_path.read_text(encoding="utf-8")
    if _sha256(wikitext) != page.get("wikitext_sha256"):
        return ["wikitext_checksum_mismatch"]
    if pagequality_level(wikitext) != page.get("quality"):
        return ["quality_tag_mismatch"]
    try:
        transclusions = page_transclusions(page, root)
    except StageExecutionError as exc:
        return [str(exc).split(":", 1)[0]]
    try:
        derived = derive_page_text(wikitext, transclusions, page)
    except UnsupportedWikitextError:
        return ["wikitext_unsupported_markup"]
    except ValueError:
        return ["text_adjustment_invalid"]
    if not derived.text.strip():
        return ["page_text_empty"]  # a proofread page whose body was left empty: no text to pair
    if derived.adjustments != page.get("text_adjustments"):
        return ["text_adjustment_mismatch"]
    if _sha256(derived.text) != page.get("text_sha256"):
        return ["page_text_checksum_mismatch"]
    text_path = root / str(page.get("text_path", ""))
    if not page.get("text_path") or not text_path.is_file():
        return ["page_text_file_missing"]
    if text_path.read_text(encoding="utf-8") != derived.text + "\n":
        return ["page_text_file_mismatch"]
    if excluded_span_problems(page, derived.text):
        return ["excluded_span_invalid"]
    return []


def page_attestation(page: dict[str, Any]) -> dict[str, Any]:
    """Human-attestation facts for a page (maintainer decision 2, 2026-11-06).

    Quality 4 is human-attested and adjudication-eligible, but only while the pinned text is the text the
    validator saw: any later edit that changes the plain text removes adjudication eligibility.
    """

    proofreader, validator = _quality_editors(page)
    post_edits = [edit for edit in page.get("edits_after_quality_set") or [] if edit.get("text_changed")]
    if page.get("quality") == 4:
        # The validator saw the faithful rendering: F8b7's adjustments (unprinted notes, stand-ins) do not change it.
        unchanged = not post_edits and page.get("quality_set_text_sha256") == page_text_sha256_converted(page)
        eligible = validator is not None and unchanged
        reason = None if eligible else "text_changed_after_validation"
        attestation = "two_editor_validated"
    else:
        eligible = False
        reason = "quality_3_single_reviewer"
        attestation = "single_reviewer_proofread"
    return {
        "human_attestation": attestation,
        "proofreader": _editor_record(proofreader),
        "validator": _editor_record(validator),
        "adjudication_eligible": eligible,
        "adjudication_ineligible_reason": reason,
        "text_changing_edits_after_quality_set": [
            {"revision_id": edit["revision_id"], "user": edit["user"], "timestamp": edit["timestamp"]} for edit in post_edits
        ],
    }


# --- E2d3b: the text as of the validating revision ---------------------------------------------------------

VALIDATED_TEXT_CHECKS_SCHEMA = "wikisource_validated_text_checks.v1"
VALIDATED_TEXT_MATCHES_SCAN = "validated_text_matches_scan"
VALIDATED_TEXT_DISAGREES_WITH_SCAN = "validated_text_disagrees_with_scan"
VALIDATED_TEXT_VERDICTS = {VALIDATED_TEXT_MATCHES_SCAN, VALIDATED_TEXT_DISAGREES_WITH_SCAN}


def layout_only_difference(validated: str, latest: str) -> bool:
    """Whether two pair texts differ only in whitespace layout: line and paragraph breaks, or run lengths (E2d3c).

    A paragraph break the print shows and the validated text runs on (or the reverse) is layout, not text, so it does
    not make the validated text disagree with the scan (team-lead decision, 2026-11-07). The words and their order
    must be identical: a space added inside a word or dropped between two words is a text difference.
    """

    return validated != latest and validated.split() == latest.split()


def validating_revision(page: dict[str, Any]) -> dict[str, Any] | None:
    """The quality-history entry at which the second editor set quality 4 (the validating revision), or None."""

    history = page.get("quality_history") or []
    if page.get("quality") != 4 or not history or history[-1].get("level") != 4:
        return None
    return history[-1]


def validated_revision_attestation(page: dict[str, Any]) -> dict[str, Any]:
    """Attestation of a quality-4 page's text *as of its validating revision* (team-lead decision, E2d3b).

    A page that ``page_attestation`` rejects only because its text changed after validation still has a text that
    both named editors attested: the one at the validating revision. Later edits are unvalidated and are not used.
    The result is ``page_attestation``'s, with ``adjudication_eligible`` for that text and
    ``reference_text_revision: validating``; any other page is not eligible here.
    """

    attestation = page_attestation(page)
    validator = validating_revision(page)
    eligible = (attestation["adjudication_ineligible_reason"] == "text_changed_after_validation"
                and validator is not None and attestation["proofreader"] is not None
                and attestation["validator"] is not None)
    return {
        **attestation,
        "adjudication_eligible": eligible,
        "adjudication_ineligible_reason": None if eligible else (attestation["adjudication_ineligible_reason"] or "not_changed_after_validation"),
        "reference_text_revision": "validating",
        "validating_revision_id": validator["revision_id"] if validator else None,
    }


def validated_text_check_problems(check: dict[str, Any]) -> list[str]:
    """Schema problems of one ``wikisource_validated_text_checks.v1`` entry; empty when it is well formed."""

    problems = [f"missing {key}" for key in ("page_title", "validating_revision_id", "latest_revision_id", "verdict",
                                              "checked_by", "checker", "checked_at", "method", "detail")
                if check.get(key) in (None, "")]
    if check.get("verdict") and check["verdict"] not in VALIDATED_TEXT_VERDICTS:
        problems.append(f"verdict must be one of {', '.join(sorted(VALIDATED_TEXT_VERDICTS))}")
    if check.get("checked_by") and check["checked_by"] not in {"agent", "human"}:
        problems.append("checked_by must be agent or human")
    notes = check.get("unprinted_notes")
    if notes is not None and not (isinstance(notes, list) and all(isinstance(n, int) and n > 0 for n in notes)):
        problems.append("unprinted_notes must be a list of footnote numbers of the validated text")
    return problems


def load_validated_text_checks(path: Path) -> dict[str, dict[str, Any]]:
    """Page title -> check, from a ``wikisource_validated_text_checks.v1`` file; a malformed entry raises."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != VALIDATED_TEXT_CHECKS_SCHEMA:
        raise StageExecutionError(f"{path.name} must be {VALIDATED_TEXT_CHECKS_SCHEMA}")
    checks: dict[str, dict[str, Any]] = {}
    for check in payload.get("checks") or []:
        problems = validated_text_check_problems(check)
        if problems:
            raise StageExecutionError(f"bad validated-text check for {check.get('page_title')}: {', '.join(problems)}")
        if check["page_title"] in checks:
            raise StageExecutionError(f"two validated-text checks for {check['page_title']}")
        checks[check["page_title"]] = check
    return checks


def derive_validated_page_text(wikitext: str, transclusions: dict[str, str], page: dict[str, Any],
                               check: dict[str, Any]) -> PageText:
    """The pair text of the validating revision's wikitext, with the page's F8b7 steps re-applied (E2d3b).

    Stand-in mappings are keyed by the Index file and re-apply as they are. Unprinted footnotes are numbered by
    the conversion, so a page that has them needs the check to list the validated text's own (``unprinted_notes``,
    possibly empty). A page with excluded spans needs the check to re-pin them to the validated text
    (``excluded_spans``). Missing either raises ``ValueError`` rather than reusing the latest text's facts.
    """

    if page.get("unprinted_notes") and "unprinted_notes" not in check:
        raise ValueError("validated_text_unprinted_notes_unchecked")
    if page.get("excluded_spans") and "excluded_spans" not in check:
        raise ValueError("validated_text_excluded_spans_unmapped")
    notes = [{"note": number} for number in check.get("unprinted_notes") or []]
    derived = derive_page_text(wikitext, transclusions, {**page, "unprinted_notes": notes})
    spans = {"excluded_spans": check["excluded_spans"]} if check.get("excluded_spans") else {}
    if spans and excluded_span_problems(spans, derived.text):
        raise ValueError("validated_text_excluded_spans_invalid")
    return derived


# --- E2d3e: the page set the E2d3 printed evaluation scores, shared by the evaluation and the split stage -----

VALIDATED_REVISION_FIELD = "validated_revision"
VALIDATED_TEXT_CHECK_FIELD = "validated_text_check"


def _validated_wikitext(record: dict[str, Any], root: Path) -> str | None:
    """A pinned validating-revision wikitext: inline (``wikitext``) or a snapshot file (``wikitext_path``, checked)."""

    if "wikitext" in record:
        return str(record["wikitext"])
    path = root / str(record.get("wikitext_path", ""))
    if not record.get("wikitext_path") or not path.is_file():
        return None
    wikitext = path.read_text(encoding="utf-8")
    return wikitext if _sha256(wikitext) == record.get("wikitext_sha256") else None


def validated_page_reference(page: dict[str, Any], root: Path, record: dict[str, Any] | None,
                             check: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
    """A quality-4 page's text as of its validating revision (E2d3b/E2d3c), or the reason it is not used (fail closed).

    ``record`` pins the validating revision's wikitext (``wikisource_validated_revisions.v1``); ``check`` is the
    page's ``wikisource_validated_text_checks.v1`` entry. The text is used when the check is fresh and finds it agrees
    with the scan, or when it differs from the latest text only in line or paragraph whitespace (E2d3c), and when
    the pinned wikitext reproduces the checksum the inventory recorded for the validating revision.
    """

    if not validated_revision_attestation(page)["adjudication_eligible"]:
        return None, "text_changed_after_validation"
    if record is None:
        return None, "validated_revision_missing"
    if (check is None or check.get("validating_revision_id") != record["validating_revision_id"]
            or check.get("latest_revision_id") != page["revision_id"]
            or check.get("validated_wikitext_sha256") != record["wikitext_sha256"]):
        return None, "validated_text_not_checked"
    matches = check["verdict"] == VALIDATED_TEXT_MATCHES_SCAN
    wikitext = _validated_wikitext(record, root)
    transclusions = page_transclusions(page, root)
    if wikitext is None:
        return None, "validated_revision_text_mismatch"
    faithful = convert_wikitext(wikitext, transclusions).text
    if _sha256(faithful) != record["converted_text_sha256"] or record["converted_text_sha256"] != page.get("quality_set_text_sha256"):
        return None, "validated_revision_text_mismatch"
    try:
        derived = derive_validated_page_text(wikitext, transclusions, page, check)
    except ValueError as exc:
        return None, str(exc) if matches else VALIDATED_TEXT_DISAGREES_WITH_SCAN
    except UnsupportedWikitextError:
        return None, "wikitext_unsupported_markup" if matches else VALIDATED_TEXT_DISAGREES_WITH_SCAN
    from hocrgen.evaluation import levenshtein_distance

    latest = page_text(page, root).text
    diff = {"character_edits": levenshtein_distance(derived.text, latest), "latest_characters": len(latest),
            "reference_characters": len(derived.text),
            "text_changing_edits_after_validation": record["text_changing_edits_after_validation"],
            "layout_only": layout_only_difference(derived.text, latest)}
    validated = {"text": derived.text, "conversion": derived.conversion, "record": record, "check": check, "diff": diff}
    # E2d3c: a difference limited to line and paragraph whitespace is layout, not text; it never disqualifies.
    if matches:
        return {**validated, "accepted_by": "check_verdict"}, VALIDATED_TEXT_MATCHES_SCAN
    if diff["layout_only"]:
        return {**validated, "accepted_by": "layout_only_difference"}, VALIDATED_TEXT_MATCHES_SCAN
    return None, VALIDATED_TEXT_DISAGREES_WITH_SCAN


_FROM_PAGE = object()


def scored_page_reference(page: dict[str, Any], root: Path, *, validation: Any = _FROM_PAGE, audit: Any = None,
                          item_id: str | None = None) -> dict[str, Any]:
    """Whether the E2d3 printed evaluation scores a page, and on which text (E2d3e; one rule for every consumer).

    For a page that passed ``page_exclusion_reasons`` (so ``text_not_on_page`` and every other page gate already
    apply). A quality-4 page that is adjudication-eligible is scored on its latest pair text. One rejected only
    because its text changed after validation is scored on its validating-revision text when
    ``validated_page_reference`` accepts it. Quality-3 pages are never scored (a single-reviewer diagnostic).

    ``validation`` is ``(record, check)`` supplied by the caller (the evaluation's ``--validated-revisions`` and
    ``--validated-text-checks``); by default the page's own ``validated_revision`` and ``validated_text_check``
    fields are read (a tranche built with them, E2d3e). Returns ``{"scored", "reason", "reference_text_revision",
    "text", "validated", "validation_considered"}``.

    ``audit`` (E2d4, a ``hocrgen.reference_audit.ReferenceAudit``) applies the page's human-accepted and
    human-edited reference corrections, and only those, to the scored text; the result then also carries
    ``base_text`` (the uncorrected text) and ``reference_audit`` (``apply_reference_audit``'s state, pending
    proposals and provenance). ``item_id`` defaults to ``wikisource_he_proofread:<source_item_id>``. Without
    ``audit`` the result is unchanged, so the split stage's reference weight is unaffected.
    """

    if audit is not None:
        scored = scored_page_reference(page, root, validation=validation)
        if not scored["scored"]:
            return scored
        revision = (scored["validated"]["record"]["validating_revision_id"] if scored["validated"] is not None
                    else page["revision_id"])
        applied = apply_reference_audit(audit, item_id or f"wikisource_he_proofread:{page['source_item_id']}",
                                        scored["text"], base_revision_id=revision)
        return {**scored, "text": applied["text"], "base_text": scored["text"], "reference_audit": applied}
    base = {"scored": False, "reference_text_revision": None, "text": None, "validated": None, "validation_considered": False}
    if page.get("quality") != 4:
        return {**base, "reason": "quality_3_single_reviewer"}
    attestation = page_attestation(page)
    if attestation["adjudication_eligible"]:
        return {**base, "scored": True, "reason": None, "reference_text_revision": "latest", "text": page_text(page, root).text}
    reason = attestation["adjudication_ineligible_reason"]
    if validation is _FROM_PAGE:
        if VALIDATED_REVISION_FIELD not in page and VALIDATED_TEXT_CHECK_FIELD not in page:
            return {**base, "reason": reason}
        validation = (page.get(VALIDATED_REVISION_FIELD), page.get(VALIDATED_TEXT_CHECK_FIELD))
    if validation is None or reason != "text_changed_after_validation":
        return {**base, "reason": reason}
    validated, reason = validated_page_reference(page, root, *validation)
    if validated is None:
        return {**base, "reason": reason, "validation_considered": True}
    return {**base, "scored": True, "reason": None, "reference_text_revision": "validating", "text": validated["text"],
            "validated": validated, "validation_considered": True}


def _editor_record(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "user": entry["user"],
        "user_id": entry["user_id"],
        "revision_id": entry["revision_id"],
        "timestamp": entry["timestamp"],
    }


def reference_normalization(conversion: WikitextConversion, page: dict[str, Any] | None = None) -> dict[str, Any]:
    """Per-page facts about how the reference text differs from the print by convention, for evaluation masking.

    ``footnote_marker_style`` is ``bracketed_index`` when the page has footnotes: each printed mark (``*)``,
    ``1)``, ``(א``) is written ``[n]``, numbered in order of first use, because editors do not type the printed
    mark. It is ``None`` on a page without footnotes.

    ``excluded_spans`` (F8b7; only on a page that has them) lists text that is in the reference but not visible on the scan (``illegible_on_scan``:
    an ink blot, a tear), by character offsets in the pair text and by boxes on the page (fractions of the page
    image). Evaluation excludes the text from primary scoring and can mask the boxes on the image.
    """

    footnotes = conversion.features.get("footnotes", 0)
    facts: dict[str, Any] = {"footnote_marker_style": FOOTNOTE_MARKER_STYLE if footnotes else None, "footnote_count": footnotes}
    spans = ((page or {}).get("excluded_spans") or {}).get("spans") or []
    if not spans:
        return facts
    facts["excluded_spans"] = [
        {"kind": span["kind"], "start": span["start"], "end": span["end"], "regions_normalized": span["regions_normalized"],
         "coordinate_frame": "page", "detail": span["detail"]}
        for span in spans
    ]
    return facts


def crop_provenance(page: dict[str, Any]) -> dict[str, Any]:
    """The crop a partial page pairs with: source page image, box, method and how it was located (F8b4)."""

    crop = page["crop"]
    image = page["image"]
    return {
        "source_page_image": {"path": image["path"], "sha256": image["sha256"], "width": image["width"], "height": image["height"]},
        "box_px": crop["box_px"],
        "box_normalized": crop["box_normalized"],
        # F8b5: a multi-region crop keeps only these regions of the box; the rest is masked to ``mask_fill``.
        "regions_px": crop.get("regions_px"),
        "regions_normalized": crop.get("regions_normalized"),
        "mask_fill": crop.get("mask_fill"),
        "method": crop["method"],
        "untranscribed_inside": crop.get("untranscribed_inside") or [],
        "untranscribed_inside_area_share": crop.get("untranscribed_inside_area_share"),
        "located_by": crop.get("located_by"),
        "asset_sha256": crop["asset"]["sha256"],
    }


def page_permalink(page: dict[str, Any]) -> str:
    title = urllib.parse.quote(str(page["page_title"]).replace(" ", "_"), safe=":/")
    return f"{WIKISOURCE_SITE_URL}/w/index.php?title={title}&oldid={page['revision_id']}"


def page_text(page: dict[str, Any], root: Path) -> PageText:
    """Derive the page's pair text from its pinned wikitext and check it against the pinned checksums (F8b7)."""

    wikitext = (root / page["wikitext_path"]).read_text(encoding="utf-8")
    derived = derive_page_text(wikitext, page_transclusions(page, root), page)
    if derived.adjustments != page.get("text_adjustments") or _sha256(derived.text) != page["text_sha256"]:
        raise StageExecutionError(f"Wikisource page text checksum mismatch for {page['source_item_id']}")
    return derived


def page_conversion(page: dict[str, Any], root: Path) -> WikitextConversion:
    """The page's conversion (without the footnotes a reviewed check found not printed), checked against the pin."""

    return page_text(page, root).conversion


def page_plain_text(page: dict[str, Any], root: Path) -> str:
    """Derive the page's pair text from its pinned wikitext and check it against the pinned checksum."""

    return page_text(page, root).text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _scored_reference_metadata(page: dict[str, Any], root: Path) -> dict[str, Any]:
    scored = scored_page_reference(page, root)
    return {"scored_reference_characters": len(scored["text"]) if scored["scored"] else 0,
            "scored_reference_text_revision": scored["reference_text_revision"]}


class WikisourceProofreadImporter:
    """Packaged-static-records adapter over a pinned Hebrew Wikisource ProofreadPage snapshot."""

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = wikisource_snapshot_root(source, bundle)
        snapshot, indexes, pages = load_wikisource_snapshot(root)
        candidates: list[CandidateRecord] = []
        for page in sorted(pages, key=lambda record: record["source_item_id"]):
            if page_exclusion_reasons(page, indexes, root):
                continue
            # 2026-11-10 legal strategy: no pair without its Index's rights justification, nor from a page whose Google
            # hygiene is pending or that is Google's front page (fails closed; ``wikisource_derivation_blocker``).
            if wikisource_page_blocker(page, indexes[page["index_key"]]):
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{page['source_item_id']}",
                    source_id=source.id,
                    source_item_id=page["source_item_id"],
                    source_url=page_permalink(page),
                    discovery_method="wikisource_snapshot_importer",
                    title=page["page_title"],
                    raw_metadata={
                        "snapshot_root": str(root),
                        "captured_at": snapshot.get("captured_at"),
                        "page": page,
                        "index": indexes[page["index_key"]],
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            page = candidate.raw_metadata["page"]
            index = candidate.raw_metadata["index"]
            root = Path(candidate.raw_metadata["snapshot_root"])
            image = page["image"]
            commons = index["commons_file"]
            work = index["work"]
            derived = page_text(page, root)
            conversion = derived.conversion
            # Decision 12 (F8b4): a partial page pairs its text with the crop of the transcribed region.
            asset = (page.get("crop") or {}).get("asset") if page_needs_crop(page) else None
            pair_image = asset or image
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=TEXT_LICENSE,
                    asset_references=[
                        AssetReference(
                            reference=pair_image["path"],
                            resolved_path=str((root / pair_image["path"]).resolve()),
                            media_type=pair_image["media_type"],
                        )
                    ],
                    metadata={
                        "collection": "Hebrew Wikisource ProofreadPage",
                        "period": "historical",
                        "content_type": "printed_historical",
                        "languages": ["he"],
                        "upstream_identifier": page["page_title"],
                        "source_group_id": f"wikisource:{page['index_key']}",
                        "wikisource_index_title": index["index_title"],
                        "wikisource_index_revision_id": index["index_revision_id"],
                        "wikisource_page_number": page["page_number"],
                        "wikisource_page_id": page["page_id"],
                        "wikisource_revision_id": page["revision_id"],
                        "wikisource_revision_timestamp": page["revision_timestamp"],
                        "wikisource_quality_level": page["quality"],
                        "wikisource_quality_label": ADMITTED_QUALITY_LEVELS[page["quality"]],
                        **page_attestation(page),
                        "text_license": TEXT_LICENSE,
                        "text_attribution": f"Hebrew Wikisource contributors, {page_permalink(page)}",
                        "text_normalization": WIKITEXT_NORMALIZATION_VERSION,
                        # Typographic size spans (small / large text) in the page body; the text itself is unsized.
                        "text_size_spans": conversion.size_spans,
                        # Reference-normalisation facts evaluation can mask (F8b4): footnote marks are [n], not the print's.
                        "reference_normalization": reference_normalization(conversion, page),
                        "page_text_ref": page["text_path"],
                        "page_text_sha256": page["text_sha256"],
                        # E2d3e: the characters of the text the E2d3 evaluation scores for this page (0 when it scores
                        # none), the page's reference weight in the split's reference constraints.
                        **_scored_reference_metadata(page, root),
                        # F8b7: the faithful MediaWiki rendering's checksum, and what was changed to reach the pair text
                        # (footnotes found not printed, editors' stand-ins mapped to the printed character).
                        "converted_text_sha256": page_text_sha256_converted(page),
                        "text_adjustments": derived.adjustments,
                        # F8g2 (#134): every step from the pinned wikitext to the pair text, versioned.
                        "text_derivation": text_derivation(derived),
                        "raw_wikitext_sha256": page["wikitext_sha256"],
                        "raw_wikitext_revision_sha1": page["revision_sha1"],
                        "work_title": work["title"],
                        "work_language": work.get("language"),
                        "work_published_year": work.get("published_year"),
                        "work_creators": [
                            {"name": creator.get("name"), "role": creator.get("role"), "death_year": creator.get("death_year")}
                            for creator in work.get("creators", [])
                        ],
                        "work_rights_basis": index["work_rights"]["basis"],
                        "scan_rights_basis": index["scan_rights"]["basis"],
                        "scan_licence": index["scan_rights"].get("licence"),
                        "scan_source_origin": scan_source_origin(index),
                        "scan_commons_file": commons["title"],
                        "scan_commons_file_sha1": commons["sha1"],
                        "scan_commons_file_page_revision_id": commons["file_page_revision_id"],
                        "scan_commons_licence_templates": commons["licence_templates"],
                        "scan_page_number": image["rendered_from"]["page"],
                        "transcription_coverage": page["transcription_coverage"],
                        "transcription_coverage_check": page.get("transcription_coverage_check"),
                        "needs_crop": page_needs_crop(page),
                        "crop": crop_provenance(page) if asset else None,
                        "scan_digitized_by_google": digitized_by_google(index),
                        # Route C rights justification (2026-11-10 legal strategy) and, where Google is not ruled out,
                        # the page's Google hygiene: ``google_watermark_bbox`` as fractions of the page render.
                        **page_justification_fields(page, index),
                        "rights_evidence_checked_at": index["evidence_checked_at"],
                        "expected_asset_sha256": pair_image["sha256"],
                    },
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            if item.metadata.get("crop"):
                problems = crop_asset_problems(item.raw_metadata["page"], Path(item.raw_metadata["snapshot_root"]))
                if problems:
                    raise StageExecutionError(f"Wikisource crop of {item.item_id} failed its integrity check: {', '.join(problems)}")
            asset = item.asset_references[0]
            resolved = Path(asset.resolved_path or "")
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            digest = sha256_file(destination)
            expected = item.metadata.get("expected_asset_sha256")
            if expected and digest != expected:
                raise StageExecutionError(
                    f"Wikisource asset checksum mismatch for {item.item_id}: expected {expected}, got {digest}"
                )
            box = watermark_box_on_pair_image(item.metadata)
            if box is not None:
                # Legal strategy rule 5: the "Digitized by Google" watermark is masked out of the exported image.
                with Image.open(destination) as opened:
                    masked = mask_google_watermark(opened, box)
                masked.save(destination, format=opened.format or "PNG", **({"quality": 95} if opened.format == "JPEG" else {}))
                item.metadata["google_watermark_masked"] = {"box": box, "units": "fraction of the pair image", "source_sha256": digest}
                digest = sha256_file(destination)
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[
                        AcquiredAsset(item_id=item.item_id, path=str(destination), sha256=digest, media_type=asset.media_type)
                    ],
                )
            )
        return acquired_items


def page_justification_fields(page: dict[str, Any], index: dict[str, Any]) -> dict[str, Any]:
    from hocrgen.fetchers.wikisource_justification import page_justification_fields as fields

    return fields(page, index)


def wikisource_page_blocker(page: dict[str, Any], index: dict[str, Any]) -> str | None:
    from hocrgen.fetchers.wikisource_justification import wikisource_page_blocker as blocker

    return blocker(page, index)


def mask_google_watermark(image: Image.Image, box: list[float]) -> Image.Image:
    from hocrgen.fetchers.wikisource_justification import mask_google_watermark as mask

    return mask(image, box)


def watermark_box_on_pair_image(metadata: dict[str, Any]) -> list[float] | None:
    """The page's Google watermark box in the coordinates of the image it pairs with (fractions), or None.

    The box is recorded on the page render; a cropped page (decision 12) pairs with its crop, so the box is moved into
    the crop and clipped to it, and is None when the two do not overlap.
    """

    box = metadata.get("google_watermark_bbox")
    if not box:
        return None
    crop = metadata.get("crop")
    if not crop:
        return list(box)
    x0, y0, x1, y1 = crop["box_normalized"]
    bx0, by0, bx1, by1 = max(box[0], x0), max(box[1], y0), min(box[0] + box[2], x1), min(box[1] + box[3], y1)
    if bx1 <= bx0 or by1 <= by0:
        return None
    width, height = x1 - x0, y1 - y0
    return [(bx0 - x0) / width, (by0 - y0) / height, (bx1 - bx0) / width, (by1 - by0) / height]


# --- Operator-only F2 reference conversion -----------------------------------------------------------------


def page_reference_record(source_id: str, page: dict[str, Any], root: Path) -> BenchmarkTranscriptionReferenceRecord:
    """Convert one adjudication-eligible quality-4 page to a ``benchmark_transcription_reference.v1`` record.

    The record is a human-reviewed candidate reference (``review.status: reviewed``), not an adjudicated one:
    adjudication stays a separate human step. Lines are the rendered paragraphs, not printed lines.
    """

    attestation = page_attestation(page)
    if not attestation["adjudication_eligible"]:
        raise StageExecutionError(
            f"Wikisource page {page['source_item_id']} is not adjudication-eligible: {attestation['adjudication_ineligible_reason']}"
        )
    return reference_record_from_text(source_id, page, page_plain_text(page, root), attestation, page["revision_id"])


def reference_record_from_text(source_id: str, page: dict[str, Any], text: str, attestation: dict[str, Any],
                               revision_id: int) -> BenchmarkTranscriptionReferenceRecord:
    """A ``benchmark_transcription_reference.v1`` record (``review.status: reviewed``) of ``text``, the page's
    pair text at ``revision_id``; ``page["excluded_spans"]`` must be pinned to that text."""

    paragraphs = [paragraph for paragraph in text.split("\n") if paragraph.strip()]
    spans = reference_spans(page, text)
    reviewers = [f"wikisource:{attestation['proofreader']['user']}", f"wikisource:{attestation['validator']['user']}"]
    return BenchmarkTranscriptionReferenceRecord(
        schema_version="benchmark_transcription_reference.v1",
        item_id=f"{source_id}:{page['source_item_id']}",
        source_id=source_id,
        source_item_id=page["source_item_id"],
        normalization={"unicode": "NFC", "text_order": "logical"},
        language_scripts=[{"language": "he", "script": "Hebr", "direction": "rtl"}],
        scoring_policy={
            "uncertain": "include_primary_and_report",
            "illegible": "exclude_primary",
            "damaged": "include_readable_and_report",
            "deleted": "exclude_primary",
            "marginal": "include_when_ordered_else_separate",
        },
        pages=[{"page_id": "page-1", "reading_order": 1, "text": text}],
        lines=[
            {"line_id": f"line-{number}", "page_id": "page-1", "reading_order": number, "text": paragraph, "layout_line_id": None}
            for number, paragraph in enumerate(paragraphs, start=1)
        ],
        spans=spans,
        review={
            "status": "reviewed",
            "reviewers": reviewers,
            "adjudicator": None,
            "adjudicated_at": None,
            "correction_of": None,
            "superseded_by": None,
            "change_reason": (
                f"Wikisource quality 4 at revision {revision_id}: proofread by {reviewers[0]}, "
                f"validated by {reviewers[1]}; {WIKITEXT_NORMALIZATION_VERSION}; lines are rendered paragraphs"
            ),
        },
    )


def reference_spans(page: dict[str, Any], text: str) -> list[dict[str, Any]]:
    """The page's excluded spans (F8b7) as reference spans on its paragraph lines: ``illegible``, ``exclude_primary``.

    Lines are the text's non-blank paragraphs, numbered as ``page_reference_record`` numbers them; a span lies inside
    one paragraph (``excluded_span_problems`` checks it), so its offsets are taken from that paragraph's start.
    """

    starts: list[tuple[int, int, int]] = []  # (line number, start, end) in the text
    position = 0
    number = 0
    for paragraph in text.split("\n"):
        if paragraph.strip():
            number += 1
            starts.append((number, position, position + len(paragraph)))
        position += len(paragraph) + 1
    records = []
    for index, span in enumerate(((page.get("excluded_spans") or {}).get("spans") or []), start=1):
        line, line_start, _ = next(entry for entry in starts if entry[1] <= span["start"] and span["end"] <= entry[2])
        records.append(
            {
                "span_id": f"span-{index}",
                "line_id": f"line-{line}",
                "start": span["start"] - line_start,
                "end": span["end"] - line_start,
                "status": "illegible",
                "scoring": "exclude_primary",
                "note": f"{span['kind']}: {span['detail']}",
            }
        )
    return records


def write_wikisource_reference_pool(source: SourceConfig, bundle: ConfigBundle, output_dir: Path) -> dict[str, Any]:
    """Operator-only: write F2 reference files for adjudication-eligible pages. Never touches ``benchmark_v1``."""

    root = wikisource_snapshot_root(source, bundle)
    _, indexes, pages = load_wikisource_snapshot(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for page in sorted(pages, key=lambda record: record["source_item_id"]):
        # A partial page passes the gate only with a resolved crop (F8b4); its reference pairs with that crop.
        reasons = page_exclusion_reasons(page, indexes, root)
        reason = reasons[0] if reasons else page_attestation(page)["adjudication_ineligible_reason"]
        # 2026-11-10 legal strategy: a reference is a Wikisource-derived artefact; it needs its Index's justification.
        reason = reason or wikisource_page_blocker(page, indexes[page["index_key"]])
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        record = page_reference_record(source.id, page, root)
        relative = f"references/{page['source_item_id']}/transcription.json"
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        path.write_text(payload, encoding="utf-8")
        entries.append(
            {
                "item_id": record.item_id,
                "path": relative,
                "sha256": _sha256(payload),
                "wikisource_revision_id": page["revision_id"],
                "adjudication_status": "needs_adjudication",
                "reference_normalization": reference_normalization(page_conversion(page, root), page),
                "image": {
                    "crop_of_page": page["image"]["sha256"],
                    "box_normalized": page["crop"]["box_normalized"],
                    **({"regions_normalized": page["crop"]["regions_normalized"]} if page["crop"].get("regions_normalized") else {}),
                }
                if page_needs_crop(page)
                else {"page": page["image"]["sha256"]},
            }
        )
    manifest = {
        "schema_version": "wikisource_reference_pool.v1",
        "source_id": source.id,
        "text_license": TEXT_LICENSE,
        "reference_contract": "benchmark_transcription_reference.v1",
        "items": entries,
        "skipped": dict(sorted(skipped.items())),
    }
    (output_dir / "reference_pool.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
