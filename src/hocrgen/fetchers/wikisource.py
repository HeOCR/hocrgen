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
from pathlib import Path
from typing import Any

from PIL import Image

from hocrgen.config.loader import ConfigBundle, load_yaml_file
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
    wikitext_to_plain_text,
)
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
    reasons.extend(_scan_rights_reasons(index))
    reasons.extend(_language_reasons(index))
    return reasons


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
        text = wikitext_to_plain_text(wikitext, transclusions)
    except UnsupportedWikitextError:
        return ["wikitext_unsupported_markup"]
    if not text.strip():
        return ["page_text_empty"]  # a proofread page whose body was left empty: no text to pair
    if _sha256(text) != page.get("text_sha256"):
        return ["page_text_checksum_mismatch"]
    text_path = root / str(page.get("text_path", ""))
    if not page.get("text_path") or not text_path.is_file():
        return ["page_text_file_missing"]
    if text_path.read_text(encoding="utf-8") != text + "\n":
        return ["page_text_file_mismatch"]
    return []


def page_attestation(page: dict[str, Any]) -> dict[str, Any]:
    """Human-attestation facts for a page (maintainer decision 2, 2026-11-06).

    Quality 4 is human-attested and adjudication-eligible, but only while the pinned text is the text the
    validator saw: any later edit that changes the plain text removes adjudication eligibility.
    """

    proofreader, validator = _quality_editors(page)
    post_edits = [edit for edit in page.get("edits_after_quality_set") or [] if edit.get("text_changed")]
    if page.get("quality") == 4:
        unchanged = not post_edits and page.get("quality_set_text_sha256") == page.get("text_sha256")
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


def _editor_record(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "user": entry["user"],
        "user_id": entry["user_id"],
        "revision_id": entry["revision_id"],
        "timestamp": entry["timestamp"],
    }


def reference_normalization(conversion: WikitextConversion) -> dict[str, Any]:
    """Per-page facts about how the reference text differs from the print by convention, for evaluation masking.

    ``footnote_marker_style`` is ``bracketed_index`` when the page has footnotes: each printed mark (``*)``,
    ``1)``, ``(א``) is written ``[n]``, numbered in order of first use, because editors do not type the printed
    mark. It is ``None`` on a page without footnotes.
    """

    footnotes = conversion.features.get("footnotes", 0)
    return {"footnote_marker_style": FOOTNOTE_MARKER_STYLE if footnotes else None, "footnote_count": footnotes}


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


def page_conversion(page: dict[str, Any], root: Path) -> WikitextConversion:
    """Convert the page's pinned wikitext and check the text against the pinned checksum."""

    wikitext = (root / page["wikitext_path"]).read_text(encoding="utf-8")
    conversion = convert_wikitext(wikitext, page_transclusions(page, root))
    if _sha256(conversion.text) != page["text_sha256"]:
        raise StageExecutionError(f"Wikisource page text checksum mismatch for {page['source_item_id']}")
    return conversion


def page_plain_text(page: dict[str, Any], root: Path) -> str:
    """Derive the page's plain text from its pinned wikitext and check it against the pinned checksum."""

    return page_conversion(page, root).text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WikisourceProofreadImporter:
    """Packaged-static-records adapter over a pinned Hebrew Wikisource ProofreadPage snapshot."""

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = wikisource_snapshot_root(source, bundle)
        snapshot, indexes, pages = load_wikisource_snapshot(root)
        candidates: list[CandidateRecord] = []
        for page in sorted(pages, key=lambda record: record["source_item_id"]):
            if page_exclusion_reasons(page, indexes, root):
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
            conversion = page_conversion(page, root)
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
                        "reference_normalization": reference_normalization(conversion),
                        "page_text_ref": page["text_path"],
                        "page_text_sha256": page["text_sha256"],
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
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[
                        AcquiredAsset(item_id=item.item_id, path=str(destination), sha256=digest, media_type=asset.media_type)
                    ],
                )
            )
        return acquired_items


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
    text = page_plain_text(page, root)
    paragraphs = [paragraph for paragraph in text.split("\n") if paragraph.strip()]
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
        spans=[],
        review={
            "status": "reviewed",
            "reviewers": reviewers,
            "adjudicator": None,
            "adjudicated_at": None,
            "correction_of": None,
            "superseded_by": None,
            "change_reason": (
                f"Wikisource quality 4 at revision {page['revision_id']}: proofread by {reviewers[0]}, "
                f"validated by {reviewers[1]}; {WIKITEXT_NORMALIZATION_VERSION}; lines are rendered paragraphs"
            ),
        },
    )


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
                "reference_normalization": reference_normalization(page_conversion(page, root)),
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
