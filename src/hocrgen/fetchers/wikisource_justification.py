"""Per-item rights justification for the Commons scans behind the Wikisource pipeline (Route C), from evidence.

The 2026-11-10 legal strategy (``planning/decisions/2026-11-10-legal-strategy.md``, "Per-item rights justification")
requires every scan accepted through Route B (Internet Archive) or Route C (Wikimedia Commons) to carry a
``rights_justification`` record built by the gate from evidence, and every line, glyph or page derived from it to point
to it. It names "the Wikisource and Commons scans behind the Wikisource pipeline and its eval sets" explicitly. This is
the Route C counterpart of ``hocrgen.fetchers.ia_justification`` (Route B): same record format
(``hocrgen.rights_justification.v1``), same id scheme (``rj:<index_key>:<sha12>``), same fail-closed rule (a required
field that cannot be filled rejects the Index with a ``justification_…`` reason).

Inputs, all committed and network-free:

- **The Index record** of the committed inventory (``docs/wikisource_index_inventory.json``), already run through the
  unchanged F8b gate (``hocrgen.fetchers.wikisource.index_exclusion_reasons``, replayed here): the Commons file (title,
  SHA-1, file-page revision, licence templates, source fields), the work (creators with death years and their cited
  evidence URLs, publication year and its evidence) and the scan record (``digitized_by_google`` and its check).
- **The rights evidence** of the Index (``docs/wikisource_rights_evidence.json``, written by the operator command
  ``python -m hocrgen.tools.wikisource_rights_justification evidence``): the exact file URL and file-page URL from the
  pinned Commons ``imageinfo`` response, the file's MIME type, the publication place, the Internet Archive item fields
  of a Commons file taken from IA, and the Google hygiene pass (front matter and watermark, per scan page).

Rules (see ``docs/wikisource_proofread_source.md``, "Rights justification (Route C)"):

- **Route C** is a Wikimedia file repository: Wikimedia Commons, or Hebrew Wikisource's local file repository for the
  few Indexes whose file lives there (``route.file_repository``). The strategy's analysis is the same for both
  (section 6: "Routes B (Internet Archive) and C (Wikimedia Commons / Wikisource)").
- **Israeli status** follows the Index's admitted basis: every contributor (author, translator, editor, annotator,
  illustrator) died more than 70 years before ``as_of``'s year, each death year with its cited source (Copyright Act
  2007, s. 38); or decision 10's presumption for a work printed on or before 1855, recorded as such; or an anonymous
  work published more than 70 years ago (s. 40). Anything else is rejected.
- **US status** is recorded, never required: ``pd_us`` when published before ``as_of.year - 95``, else
  ``not_established``.
- **Digitizer** is named from evidence: Google (the Commons record or categories, ``bub_gb_`` / ``…goog`` IA items, the
  file's text layer, or a "Digitized by Google" mark the hygiene pass found), the National Library of Israel,
  HebrewBooks, the Open Siddur Project, the Internet Archive and its contributing library, another named source, or
  ``unrecorded`` (decision 10: a faithful reproduction needs no recorded scan source).
- **Hygiene** (strategy rule 5) applies whenever Google is not ruled out: a Google-digitized file, or one whose Google
  status the inventory could not decide. Its record lists Google's usage-guidelines pages (excluded) and the
  ``google_watermark_bbox`` of each checked page, as fractions of the page render. Until the pass has run it is
  ``"pending"`` and ``wikisource_derivation_blocker`` blocks every derivation from the file.

``wikisource_derivation_blocker`` is the counterpart of ``ia_derivation_blocker``: every exporter of Wikisource-derived
artefacts (pairs, references, lines, glyphs) must call it and skip what it blocks.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

from PIL import Image

from hocrgen.fetchers.google_hygiene import (
    EXCLUDED_GOOGLE_FRONT_MATTER,
    FRONT_MATTER_METHOD,
    HYGIENE_FORMAT,
    WATERMARK_METHOD,
)
from hocrgen.fetchers.ia_iiif import (
    DIGITIZER_GOOGLE,
    DIGITIZER_NLI,
    LEGAL_STRATEGY_DECISION_RECORD,
)
from hocrgen.fetchers.ia_justification import (
    DECISION_10_RECORD,
    FAITHFUL_REPRODUCTION_TEXT,
    GOOGLE_USAGE_GUIDELINES,
    ISRAEL_TERM_YEARS,
    JUSTIFICATION_FORMAT,
    LEGAL_STRATEGY_DOC,
    PRESUMPTION_CUTOFF_YEAR,
    REASON_GOOGLE_HYGIENE_PENDING,
    US_TERM_YEARS,
    WHY_NOT_BINDING_TEMPLATE,
    JustificationResult,
)
from hocrgen.fetchers.wikisource import (
    FLORUIT_LIFESPAN_MARGIN,
    PRINTED_COMMENTARY_REASONS,
    REPRINT_REASON,
    crop_mask_fill,
    floruit_basis,
    index_exclusion_reasons,
    scan_source_origin,
)

GENERATOR = "hocrgen.fetchers.wikisource_justification.build_wikisource_rights_justification"
ROUTE_COMMONS = "wikimedia_commons"
REGISTRY_SCHEMA = "wikisource_rights_justifications.v1"
EVIDENCE_SCHEMA = "wikisource_rights_evidence.v1"
REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = REPO_ROOT / "docs" / "wikisource_rights_justifications.json"
EVIDENCE_PATH = REPO_ROOT / "docs" / "wikisource_rights_evidence.json"
F8_DECISIONS_RECORD = "planning/decisions/2026-11-06-f8-real-source-decisions.md"
WIKIMEDIA_TERMS_URL = "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"
ROUTE_TERMS_TEXT = (
    "Wikimedia Terms of Use, and the file's licence or public-domain template on its file page (recorded as found;"
    " decision 10: a missing or PD-US-only template never decides the work's status). Strategy section 2(a): Commons"
    " offers public-domain files free of all restrictions."
)
HEBREWBOOKS_TERMS = (
    "HebrewBooks' site terms: a personal-use, non-commercial licence that bans automated access (maintainer decision 3,"
    " 2026-11-06)"
)
# Commons tags that would restrict reuse (none occurs in the admitted Indexes; a hit rejects the Index).
RESTRICTIVE_TEMPLATE = re.compile(
    r"non-?free|fair[ _-]?use|(?:^|[-_ ])n[cd](?:$|[-_ ])|noncommercial|non-commercial|no[-_ ]?deriv|all rights reserved"
    r"|copyrighted(?![ _-]?free)|שימוש הוגן",
    re.I,
)
SCAN_MIME_TYPES = {"application/pdf", "image/vnd.djvu", "image/x.djvu", "image/png", "image/jpeg", "image/tiff"}
GOOGLE_IA_IDENTIFIER = re.compile(r"^bub_gb_|goog$", re.I)

GOOGLE_STATUS_GOOGLE = "google"  # Google digitized the file (or some of its pages)
GOOGLE_STATUS_RULED_OUT = "not_google"  # the inventory's check ruled Google out
GOOGLE_STATUS_NOT_DETECTED = "not_detected"  # undecided by the inventory; the hygiene pass found no Google mark
GOOGLE_STATUS_UNDECIDED = "undecided"  # undecided, and no hygiene pass yet

REASON_JUSTIFICATION_MISSING = "wikisource_rights_justification_missing"
REASON_GOOGLE_FRONT_MATTER = EXCLUDED_GOOGLE_FRONT_MATTER
HYGIENE_SCOPE = "wikisource_commons_pages"
BOX_UNITS = "fraction of the page render: [x, y, width, height]"

# hocrgen#171: what the gate read for printed commentaries and later reprints (none found is recorded too).
PRINTED_COMMENTARY_SOURCES = ["Commons file description and author fields", "Index title and author fields",
                              "headings of the pinned page wikitext (quality 3/4 pages)"]
REPRINT_SOURCES = ["Commons file description, date, source and author fields", "Index title, year and publisher fields",
                   "recorded facts (docs/wikisource_index_evidence.json)"]
# Index gate reasons of the rights rules: an Index they reject is listed in the registry as not justified.
RIGHTS_RULE_REASONS = (*PRINTED_COMMENTARY_REASONS, REPRINT_REASON)

ROLES_COUNTED = ["author", "translator", "editor", "annotator", "illustrator", "anonymous", "pseudonymous"]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def justification_key(index: Mapping[str, Any]) -> str:
    """The id key of an Index: its inventory ``index_key`` (``ws_index_<page id>``), else its Commons file title."""

    key = str(index.get("index_key") or "")
    if key.startswith("ws_index_"):
        return key
    return str((index.get("commons_file") or {}).get("title") or key)


# --- Google hygiene (strategy rule 5) on page renders ------------------------------------------------------------


def wikisource_hygiene_record(pages: Sequence[Mapping[str, Any]], *, render_source: str) -> dict[str, Any]:
    """The hygiene record of one Commons file from its per-page checks (``scan_page``, render, front matter, box).

    Each page entry is one render the operator pass checked: ``front_matter`` (Google's usage-guidelines boilerplate in
    the page's eng OCR, with the phrases found) and ``google_watermark_bbox`` (the "Digitized by Google" line in the
    page foot, as fractions of the render, or None). Front-matter pages are excluded; the rest carry their box.
    """

    ordered = sorted((dict(page) for page in pages), key=lambda page: int(page["scan_page"]))
    return {
        "format": HYGIENE_FORMAT,
        "scope": HYGIENE_SCOPE,
        "box_units": BOX_UNITS,
        "render_source": render_source,
        "excluded_front_matter": [
            {"scan_page": p["scan_page"], "reason": EXCLUDED_GOOGLE_FRONT_MATTER, "phrases": list(p.get("phrases") or [])}
            for p in ordered if p.get("front_matter")
        ],
        "watermark_boxes": [
            {"scan_page": p["scan_page"], "google_watermark_bbox": list(p["google_watermark_bbox"])}
            for p in ordered if p.get("google_watermark_bbox") is not None and not p.get("front_matter")
        ],
        "pages_without_watermark": [
            p["scan_page"] for p in ordered if p.get("google_watermark_bbox") is None and not p.get("front_matter")
        ],
        "pages": [
            {key: p.get(key) for key in ("scan_page", "render_sha256", "render_width", "render_height", "front_matter",
                                         "google_watermark_bbox", "watermark_band")}
            for p in ordered
        ],
        "method": {"front_matter": FRONT_MATTER_METHOD, "watermark": WATERMARK_METHOD + " (band upscaled 3x)"},
    }


def hygiene_page(hygiene: Any, scan_page: int) -> dict[str, Any] | None:
    """The hygiene entry of one scan page, or None when the pass did not check that page."""

    if not isinstance(hygiene, Mapping):
        return None
    for page in hygiene.get("pages") or []:
        if int(page.get("scan_page", -1)) == int(scan_page):
            return dict(page)
    return None


def mask_google_watermark(image: Image.Image, box: Sequence[float]) -> Image.Image:
    """The page image with its Google watermark box (fractions of the image) filled with the page background."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    x, y, w, h = box
    pixels = (max(0, int(x * width)), max(0, int(y * height)), min(width, -int(-(x + w) * width)), min(height, -int(-(y + h) * height)))
    if pixels[2] <= pixels[0] or pixels[3] <= pixels[1]:
        return rgb
    # The background is read around the box too (the box itself may be mostly watermark ink).
    margin = max(4, pixels[3] - pixels[1])
    around = (max(0, pixels[0] - margin), max(0, pixels[1] - margin), min(width, pixels[2] + margin), min(height, pixels[3] + margin))
    fill = tuple(crop_mask_fill(rgb, around))
    masked = rgb.copy()
    masked.paste(Image.new("RGB", (pixels[2] - pixels[0], pixels[3] - pixels[1]), fill), pixels[:2])
    return masked


# --- evidence helpers ------------------------------------------------------------------------------------------


def _ia_identifier(index: Mapping[str, Any], evidence: Mapping[str, Any]) -> str | None:
    item = evidence.get("ia_item") or {}
    return item.get("identifier")


def google_status(index: Mapping[str, Any], evidence: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Whether Google digitized the file: a status (``google`` / ``not_google`` / ``not_detected`` / ``undecided``) and
    the evidence for it."""

    scan = index.get("scan_rights") or {}
    found: list[str] = []
    if scan.get("digitized_by_google") is True:
        found.append(f"inventory Google check: {scan.get('digitization_check')}")
    identifier = _ia_identifier(index, evidence)
    if identifier and GOOGLE_IA_IDENTIFIER.search(identifier):
        found.append(f"Internet Archive identifier pattern (bub_gb_ / …goog): {identifier}")
    item = evidence.get("ia_item") or {}
    for field in ("scanner", "sponsor", "contributor"):
        if "google" in str(item.get(field) or "").casefold():
            found.append(f"Internet Archive item {identifier} {field}: {item[field]}")
    hygiene = evidence.get("google_hygiene")
    if isinstance(hygiene, Mapping):
        marks = [p["scan_page"] for p in hygiene.get("pages") or [] if p.get("google_watermark_bbox") is not None]
        fronts = [p["scan_page"] for p in hygiene.get("pages") or [] if p.get("front_matter")]
        if marks:
            found.append(f"hygiene pass: 'Digitized by Google' watermark on scan pages {marks}")
        if fronts:
            found.append(f"hygiene pass: Google usage-guidelines page at scan pages {fronts}")
    if found:
        return GOOGLE_STATUS_GOOGLE, found
    if scan.get("digitized_by_google") is False:
        return GOOGLE_STATUS_RULED_OUT, [f"inventory Google check: {scan.get('digitization_check')}"]
    if isinstance(hygiene, Mapping):
        checked = len(hygiene.get("pages") or [])
        return GOOGLE_STATUS_NOT_DETECTED, [
            f"inventory Google check: {scan.get('digitization_check')}",
            f"hygiene pass: no Google usage-guidelines page and no 'Digitized by Google' watermark on {checked} checked page renders",
        ]
    return GOOGLE_STATUS_UNDECIDED, [f"inventory Google check: {scan.get('digitization_check')}"]


def _commons_text(index: Mapping[str, Any]) -> str:
    commons = index.get("commons_file") or {}
    return " ".join(str(v) for v in (commons.get("source_field"), commons.get("institution_field"),
                                      commons.get("provenance_text")) if v)


def digitizer_record(index: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Who scanned the file, with the evidence: Google, NLI, HebrewBooks, a named library or source, or unrecorded."""

    origin = scan_source_origin(dict(index))
    scan = index.get("scan_rights") or {}
    source = scan.get("scan_source") or {}
    commons = index.get("commons_file") or {}
    status, google_evidence = google_status(index, evidence)
    item = evidence.get("ia_item") or {}
    source_evidence = [str(source["evidence"])] if source.get("evidence") else []
    named = None
    kind = "unrecorded"
    if origin == "national_library_of_israel":
        named, kind = DIGITIZER_NLI, "national_library_of_israel"
    elif origin == "hebrewbooks":
        named, kind = "HebrewBooks", "hebrewbooks"
    elif origin == "open_siddur_project" or "open siddur" in str(source.get("name") or "").casefold():
        named, kind = str(source.get("name") or "Open Siddur Project"), "open_siddur_project"
    elif item.get("identifier"):
        library = item.get("contributor") or item.get("sponsor")
        if item.get("metadata") == "not_fetched":
            source_evidence.append(f"Internet Archive item {item['identifier']}: its metadata was not fetched")
        elif library:
            named = f"Internet Archive, from a copy at {library}"
            kind = "internet_archive_library_scan"
            source_evidence.append(
                f"Internet Archive item {item['identifier']}: contributor {item.get('contributor')!r}, sponsor "
                f"{item.get('sponsor')!r}, scanning centre {item.get('scanningcenter')!r}"
            )
        else:
            named = None
            how = f"uploaded with {item['scanner']}" if item.get("scanner") else "no scanner, contributor or sponsor recorded"
            source_evidence.append(f"Internet Archive item {item['identifier']}: {how}; the digitizer is not named")
    elif source.get("name") and source.get("name") != "Google Books":
        # A website the file came from (e.g. folkmasa.org) is where it was found, not who scanned it.
        kind = "named_source"
    if status == GOOGLE_STATUS_GOOGLE:
        name = DIGITIZER_GOOGLE
    elif named:
        name = named
    else:
        name = "unrecorded"
    record: dict[str, Any] = {
        "name": name,
        "kind": "google" if status == GOOGLE_STATUS_GOOGLE else kind,
        "evidence": [*google_evidence, *source_evidence] if status == GOOGLE_STATUS_GOOGLE else [*source_evidence, *google_evidence],
        "google": {"status": status, "evidence": google_evidence},
        "scan_source_origin": origin,
    }
    if status == GOOGLE_STATUS_GOOGLE and named:
        record["also_named"] = named
    if kind == "named_source" and source.get("name"):
        record["file_source_named"] = str(source["name"])
    if name == "unrecorded":
        record["note"] = ("No scanning body is recorded for this file (decision 10: a faithful reproduction of a"
                          " public-domain work needs no recorded scan source)"
                          + (f"; the Commons record names the site it came from, {source['name']}" if kind == "named_source" else "")
                          + ".")
    if commons.get("institution_field"):
        record["institution_field"] = commons["institution_field"]
    return record


def _contributors(index: Mapping[str, Any]) -> list[dict[str, Any]]:
    out = []
    for creator in (index.get("work") or {}).get("creators") or []:
        url = creator.get("death_year_evidence_url")
        floruit = creator.get("floruit") if not url else None
        source = None
        if url:
            source = {"url": url, "kind": "wikidata_p570" if "wikidata.org" in str(url) else "cited_source"}
        elif floruit and floruit_basis(dict(creator)):
            # hocrgen#171: a cited floruit is the author's basis (kind ``floruit``).
            source = {"url": floruit["evidence_url"], "kind": "floruit", "source": floruit.get("source"),
                      "value": floruit.get("value"), "label": floruit.get("label"), "latest_year": floruit["latest_year"],
                      "rule": f"active by {floruit['latest_year']} at the latest, so died by "
                              f"{floruit['latest_year'] + FLORUIT_LIFESPAN_MARGIN}"}
        out.append({
            "name": creator.get("name"),
            "role": creator.get("role"),
            "wikidata": creator.get("wikidata"),
            "death_year": creator.get("death_year"),
            "death_year_source": source,
        })
    return out


def _join_years(contributors: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for role in ROLES_COUNTED:
        years = sorted({c["death_year"] for c in contributors if c["role"] == role and isinstance(c.get("death_year"), int)})
        if years:
            parts.append(f"{role if len(years) == 1 else role + 's'} d. " + " and ".join(str(y) for y in sorted(years)))
        floruits = sorted({str((c.get("death_year_source") or {}).get("label") or (c.get("death_year_source") or {}).get("value"))
                           for c in contributors if c["role"] == role and c.get("death_year") is None
                           and (c.get("death_year_source") or {}).get("kind") == "floruit"})
        if floruits:
            parts.append(f"{role} fl. " + " and ".join(floruits))
    return ", ".join(parts)


def _israel_status(index: Mapping[str, Any], contributors: list[dict[str, Any]], year: int | None,
                   as_of: dt.date) -> tuple[dict[str, Any] | None, list[str]]:
    basis = (index.get("work_rights") or {}).get("basis")
    failures: list[str] = []
    last = as_of.year - ISRAEL_TERM_YEARS - 1  # died in or before this year: life + 70 has run out
    if basis == "anonymous_published_by_1955":
        if year is None or year > last:
            return None, [f"justification_anonymous_work_not_expired:{year}"]
        return {"status": "pd_il", "basis": "anonymous_published_over_70_years_ago",
                "reason": f"anonymous work published {year}; {year} + {ISRAEL_TERM_YEARS} < {as_of.year}",
                "law": "Copyright Act 2007, s. 40"}, []
    if basis not in {"author_died_by_1955", "presumed_pd_by_publication_age"}:
        return None, [f"justification_work_basis_unsupported:{basis}"]
    if not contributors:
        failures.append("justification_no_contributor_listed")
    presumed = []
    floruit_for = []
    for c in contributors:
        death = c.get("death_year")
        source = c.get("death_year_source") or {}
        if death is None and source.get("kind") == "floruit":
            floruit_for.append(f"{c['name']} (floruit {source.get('label') or source.get('value')})")
            continue
        if isinstance(death, int):
            if c.get("death_year_source") is None:
                failures.append(f"justification_death_year_uncited:{c['name']}")
            elif death > last:
                failures.append(f"justification_not_pd_in_israel:{c['name']}:{death}")
        elif year is not None and year <= PRESUMPTION_CUTOFF_YEAR:
            presumed.append(c["name"])
        else:
            failures.append(f"justification_missing_death_year:{c['name']}")
    if failures:
        return None, failures
    if presumed:
        return {
            "status": "pd_il",
            "basis": "presumption_decision_10",
            "reason": f"printed {year}, on or before {PRESUMPTION_CUTOFF_YEAR}; no death year found for "
            + ", ".join(presumed) + "; presumed PD in Israel (decision 10, 2026-11-06)",
            "presumed_for": presumed,
            "law": "Copyright Act 2007, s. 38",
            "decision": DECISION_10_RECORD,
        }, []
    deaths = [c["death_year"] for c in contributors if isinstance(c.get("death_year"), int)]
    deaths += [c["death_year_source"]["latest_year"] + FLORUIT_LIFESPAN_MARGIN for c in contributors
               if c.get("death_year") is None and (c.get("death_year_source") or {}).get("kind") == "floruit"]
    latest = max(deaths)
    status = {"status": "pd_il", "basis": "author_died_over_70_years_ago",
              "reason": f"every contributor died by {latest}; {latest} + {ISRAEL_TERM_YEARS} < {as_of.year}",
              "law": "Copyright Act 2007, s. 38"}
    if floruit_for:
        status["floruit_for"] = floruit_for
        status["reason"] += ("; the author's death year is bounded by a cited floruit (hocrgen#171: active by year F,"
                             f" so died by F + {FLORUIT_LIFESPAN_MARGIN}); every other contributor has a cited death year")
    return status, []


def _route_text(repository: str, title: str) -> str:
    if repository == "he.wikisource":
        return f"Hebrew Wikisource's file repository ({title})"
    return f"Wikimedia Commons ({title})"


def build_wikisource_rights_justification(
    index: Mapping[str, Any], evidence: Mapping[str, Any] | None, *, as_of: dt.date
) -> JustificationResult:
    """The ``rights_justification`` of the Commons file behind a Wikisource Index, or why it cannot be justified.

    ``index`` is the Index's committed inventory record; ``evidence`` its entry in the rights evidence file (None when
    the evidence pass never reached it, which rejects the Index).
    """

    reasons = index_exclusion_reasons(dict(index))
    if reasons:
        failures = [f"justification_index_not_admitted:{reason}" for reason in reasons]
        return JustificationResult(False, failures[0], failures, None)
    if evidence is None:
        reason = "justification_rights_evidence_missing"
        return JustificationResult(False, reason, [reason], None)
    commons = index.get("commons_file") or {}
    work = index.get("work") or {}
    scan = index.get("scan_rights") or {}
    file = evidence.get("file") or {}
    title = str(commons.get("title") or "")
    failures: list[str] = []

    if not file.get("url"):
        failures.append("justification_file_url_missing")
    if file.get("sha1") != commons.get("sha1"):
        failures.append("justification_file_sha1_mismatch")
    mime = file.get("mime")
    if mime is None:
        failures.append("justification_file_type_unknown")
    elif mime not in SCAN_MIME_TYPES:
        failures.append(f"justification_not_a_scan_file:{mime}")

    contributors = _contributors(index)
    year = work.get("published_year") if isinstance(work.get("published_year"), int) else None
    israel_status, israel_failures = _israel_status(index, contributors, year, as_of)
    failures.extend(israel_failures)

    templates = [str(t) for t in commons.get("licence_templates") or []]
    templates += [str(t) for t in (file.get("redirect_target") or {}).get("licence_templates") or []]
    for template in templates:
        if RESTRICTIVE_TEMPLATE.search(template):
            failures.append(f"justification_route_terms_restrictive:{template}")
    if failures:
        return JustificationResult(False, failures[0], failures, None)

    cutoff = as_of.year - US_TERM_YEARS
    if year is not None and year < cutoff:
        us_status = {"status": "pd_us", "reason": f"published before {cutoff}", "publication_year": year}
    else:
        us_status = {
            "status": "not_established",
            "reason": f"recorded publication year {year}, not before {cutoff}; other US grounds (e.g. URAA) not assessed"
            if year is not None else "publication year not recorded",
            "publication_year": year,
        }

    digitizer = digitizer_record(index, evidence)
    status = digitizer["google"]["status"]
    google = status == GOOGLE_STATUS_GOOGLE
    origin = digitizer["scan_source_origin"]
    nli_origin = origin == "national_library_of_israel"
    hebrewbooks = origin == "hebrewbooks"
    repository = str(file.get("repository") or commons.get("repository") or "commons")
    route_text = _route_text(repository, title)

    labels: list[dict[str, Any]] = []
    holders: list[str] = []
    label_texts: list[str] = []
    if google:
        holders.append(DIGITIZER_GOOGLE)
        label_texts.append(GOOGLE_USAGE_GUIDELINES)
        labels.append({"holder": DIGITIZER_GOOGLE, "label": "google_books_usage_guidelines",
                       "as_found": GOOGLE_USAGE_GUIDELINES, "evidence": "Google-digitized file (digitizer evidence)"})
    if nli_origin:
        holders.append(DIGITIZER_NLI)
        label_texts.append("NLI's label for it (not checked)")
        labels.append({"holder": DIGITIZER_NLI, "label": None, "checked": False,
                       "note": "NLI's own label for this item was not checked (no saved NLI record for it); the"
                       " maintainer ruling on NLI-origin files applies whatever it is"})
    if hebrewbooks:
        holders.append("HebrewBooks")
        label_texts.append(HEBREWBOOKS_TERMS)
        labels.append({"holder": "HebrewBooks", "label": "hebrewbooks_site_terms", "as_found": HEBREWBOOKS_TERMS,
                       "evidence": "the Commons file record names HebrewBooks as its source"})
    origin_label: dict[str, Any] | None = None
    if labels:
        origin_label = {**labels[0], **({"also": labels[1:]} if len(labels) > 1 else {})}
    why_not_binding = None
    if origin_label is not None:
        why_not_binding = WHY_NOT_BINDING_TEMPLATE.format(
            route=route_text, holders=" or ".join(holders), label=" and ".join(label_texts)
        )

    hygiene: Any = evidence.get("google_hygiene")
    if not isinstance(hygiene, Mapping):
        hygiene = "none" if status == GOOGLE_STATUS_RULED_OUT else "pending"

    basis = israel_status["basis"]
    if basis == "presumption_decision_10":
        pd_reason = f"printed {year}, presumed PD (decision 10)"
    elif basis == "anonymous_published_over_70_years_ago":
        pd_reason = f"anonymous, published {year}"
    else:
        pd_reason = _join_years(contributors) + (f", recorded publication year {year}" if year is not None else "")
    digitized = ("digitizer unrecorded" if digitizer["name"] == "unrecorded"
                 else f"digitized by {digitizer['name']}")
    if digitizer.get("file_source_named"):
        digitized += f" (file from {digitizer['file_source_named']})"
    summary = (
        f"Public-domain work ({pd_reason}); faithful scan, {digitized}; fetched from {route_text}"
        + (f", not from {' or '.join(holders)}" if holders else "")
        + "; no new right in the scan and no contract binds its reuse"
        + ("." if us_status["status"] == "pd_us" else "; US status not established.")
    )
    decision_refs = [
        LEGAL_STRATEGY_DECISION_RECORD + (" (including the maintainer ruling on NLI-origin files)" if nli_origin else ""),
        LEGAL_STRATEGY_DOC,
        F8_DECISIONS_RECORD + " (" + "; ".join(
            part for part in (
                "decision 3: HebrewBooks-sourced Commons files" if hebrewbooks else None,
                "decision 9: Google-digitized Commons files" if google else None,
                "decision 10: the 1855 presumption" if basis == "presumption_decision_10" else None,
                "decision 10: data gaps are not rights problems",
            ) if part
        ) + ")",
    ]
    route_urls = [file["url"], *([file["description_url"]] if file.get("description_url") else [])]
    record: dict[str, Any] = {
        "format": JUSTIFICATION_FORMAT,
        "generator": GENERATOR,
        "as_of": as_of.isoformat(),
        "index_key": justification_key(index),
        "index_title": index.get("index_title"),
        "commons_file": title,
        "route": {
            "name": ROUTE_COMMONS,
            "file_repository": repository,
            "url": route_urls,
            "sha1": {"file": commons.get("sha1")},
            "sha256": None,
            "sha256_note": "The whole file was never downloaded. The file is pinned by its SHA-1 (Commons imageinfo)"
            " and its file-page revision; every page render used is pinned by sha256 in its page record"
            " (image.rendered_from.render_sha256).",
            "file_page_revision_id": commons.get("file_page_revision_id"),
            **({"redirect_target": file["redirect_target"]["title"]} if file.get("redirect_target") else {}),
            **({"note": "Route C (Wikimedia): the file is in Hebrew Wikisource's local file repository, not on"
                        " Commons; the same Wikimedia Terms of Use and the same no-privity analysis apply"
                        " (strategy section 6: 'Routes B (Internet Archive) and C (Wikimedia Commons / Wikisource)')."}
               if repository == "he.wikisource" else {}),
        },
        "work_public_domain": {
            "title": work.get("title"),
            "contributors": contributors,
            "contributors_basis": {
                "checked": [
                    "Wikisource Index fields (author, translator, editor, illustrator, and role markers in the title"
                    " and notes)",
                    "Commons file page fields (Author, Translator, Editor, Illustrator)",
                    "cited facts in docs/wikisource_index_evidence.json",
                ],
                "counted_roles": ROLES_COUNTED,
                "death_year_sources": ["wikidata_p570", "Wikisource author page", "cited source (index evidence file)"],
            },
            "publication_year": {"year": year, "evidence": work.get("published_year_evidence")},
            "place": evidence.get("place"),
            "language": work.get("language"),
            # hocrgen#171: the commentaries printed on the pages and the reprint check, as the gate read them.
            "printed_commentaries": work.get("printed_commentaries") or {"detected": [], "checked": PRINTED_COMMENTARY_SOURCES},
            "reprint_check": work.get("reprint_check") or {"suspected": False, "checked": REPRINT_SOURCES},
            "inventory_gate": {"work_rights": dict(index.get("work_rights") or {}),
                               **({"additional_grounds": work["additional_grounds"]} if work.get("additional_grounds") else {})},
            "israel_status": israel_status,
            "us_status": us_status,
        },
        "faithful_reproduction": {
            "text": FAITHFUL_REPRODUCTION_TEXT,
            "evidence": {
                "mime": mime,
                "page_count": commons.get("page_count"),
                "scan_rights_basis": scan.get("basis"),
                "scan_rights_evidence": scan.get("evidence"),
                "explicit_open_licence": scan.get("licence"),
            },
        },
        "digitizer": digitizer,
        "origin_label": origin_label,
        "why_not_binding": why_not_binding,
        "route_terms": {
            "reference": ROUTE_TERMS_TEXT,
            "url": WIKIMEDIA_TERMS_URL,
            "licence_templates": [str(t) for t in commons.get("licence_templates") or []],
            **({"redirect_target_licence_templates": list(file["redirect_target"].get("licence_templates") or [])}
               if file.get("redirect_target") else {}),
            "file_page": file.get("description_url"),
            "file_page_revision_id": commons.get("file_page_revision_id"),
        },
        "hygiene": hygiene,
        "decision_refs": decision_refs,
        "summary": summary,
    }
    record = {"id": f"rj:{justification_key(index)}:{_sha256(record)[:12]}", **record}
    return JustificationResult(True, "rights_justified", [], record)


# --- the committed registry, lookups and the blocker ---------------------------------------------------------------


@cache
def _load_registry(path: str) -> dict[str, Any]:
    file = Path(path)
    if not file.is_file():
        return {"by_id": {}, "by_key": {}, "by_file": {}, "entries": {}}
    payload = json.loads(file.read_text(encoding="utf-8"))
    by_id: dict[str, dict[str, Any]] = {}
    by_key: dict[str, dict[str, Any]] = {}
    by_file: dict[str, dict[str, Any]] = {}
    entries: dict[str, dict[str, Any]] = {}
    for entry in payload.get("items") or []:
        entries[entry["index_key"]] = entry
        record = entry.get("rights_justification")
        if entry.get("accepted") and isinstance(record, dict):
            by_id[record["id"]] = record
            by_key[entry["index_key"]] = record
            by_file[record["commons_file"]] = record
    return {"by_id": by_id, "by_key": by_key, "by_file": by_file, "entries": entries}


def load_registry(path: Path | None = None) -> dict[str, Any]:
    """The committed justifications (``docs/wikisource_rights_justifications.json``), indexed by id, key and file."""

    return _load_registry(str(path or REGISTRY_PATH))


def wikisource_rights_justification(
    *, index_key: str | None = None, commons_file: str | None = None, sha1: str | None = None, path: Path | None = None
) -> dict[str, Any] | None:
    """The accepted ``rights_justification`` of an Index, by ``index_key`` (``ws_index_<id>``) or Commons file title.

    With ``sha1`` the record must pin that Commons SHA-1 (a re-uploaded file is a different scan). None when the Index
    has no accepted justification: it was rejected, or never justified.
    """

    registry = load_registry(path)
    record = None
    if index_key:
        record = registry["by_key"].get(index_key)
    if record is None and commons_file:
        name = commons_file if commons_file.startswith("File:") else f"File:{commons_file}"
        record = registry["by_file"].get(name)
    if record is None or (sha1 and record["route"]["sha1"]["file"] != sha1):
        return None
    return record


def wikisource_rights_justification_id(
    *, index_key: str | None = None, commons_file: str | None = None, sha1: str | None = None, path: Path | None = None
) -> str | None:
    """The ``rights_justification_id`` a Wikisource-derived row must carry (None: the Index is not justified)."""

    record = wikisource_rights_justification(index_key=index_key, commons_file=commons_file, sha1=sha1, path=path)
    return None if record is None else record["id"]


def wikisource_justification_entry(index_key: str, path: Path | None = None) -> dict[str, Any] | None:
    """The registry entry of an Index (accepted or rejected, with its reason), for reports."""

    return load_registry(path)["entries"].get(index_key)


def hygiene_required(record: Mapping[str, Any]) -> bool:
    """Hygiene applies unless the inventory's check ruled Google out."""

    status = ((record.get("digitizer") or {}).get("google") or {}).get("status")
    return status != GOOGLE_STATUS_RULED_OUT


def _scan_page(item: Mapping[str, Any]) -> int | None:
    for key in ("scan_page", "scan_page_number", "commons_page"):
        value = item.get(key)
        if isinstance(value, int):
            return value
    rendered = ((item.get("image") or {}).get("rendered_from") or {}).get("page")
    return rendered if isinstance(rendered, int) else None


def _item_sha1(item: Mapping[str, Any]) -> str | None:
    for key in ("commons_file_sha1", "scan_commons_file_sha1"):
        if item.get(key):
            return str(item[key])
    return ((item.get("image") or {}).get("rendered_from") or {}).get("commons_file_sha1")


def wikisource_derivation_blocker(item: Mapping[str, Any], *, path: Path | None = None) -> str | None:
    """Why nothing may be derived from this Wikisource item yet, or None when it may. Fails closed.

    ``item`` is anything that points to a Commons scan: a pair item's metadata, a page record, a line row. It must
    carry the ``rights_justification_id`` of its Index (or the record itself as ``rights_justification``); fill it
    with ``wikisource_rights_justification_id``. When it names its Commons SHA-1 (``commons_file_sha1`` /
    ``scan_commons_file_sha1``) and scan page (``scan_page`` / ``scan_page_number``, or ``image.rendered_from``), both
    are checked too.

    - ``wikisource_rights_justification_missing``: no id, an id the committed registry does not hold (the Index was
      rejected or never justified), or a record pinned to another file SHA-1;
    - ``google_hygiene_pending``: Google is not ruled out for the file and its hygiene pass has not run, or did not
      check this scan page;
    - ``excluded_google_front_matter``: the page is Google's usage-guidelines page.
    """

    record = item.get("rights_justification")
    if not isinstance(record, Mapping) or not isinstance(record.get("id"), str):
        identifier = item.get("rights_justification_id")
        record = load_registry(path)["by_id"].get(identifier) if isinstance(identifier, str) and identifier else None
    if record is None:
        return REASON_JUSTIFICATION_MISSING
    sha1 = _item_sha1(item)
    if sha1 and ((record.get("route") or {}).get("sha1") or {}).get("file") != sha1:
        return REASON_JUSTIFICATION_MISSING
    if not hygiene_required(record):
        return None
    hygiene = record.get("hygiene")
    if not isinstance(hygiene, Mapping):
        return REASON_GOOGLE_HYGIENE_PENDING
    page = _scan_page(item)
    if page is None:
        return None
    entry = hygiene_page(hygiene, page)
    if entry is None:
        return REASON_GOOGLE_HYGIENE_PENDING
    if entry.get("front_matter"):
        return REASON_GOOGLE_FRONT_MATTER
    return None


def page_justification_fields(page: Mapping[str, Any], index: Mapping[str, Any], *, path: Path | None = None) -> dict[str, Any]:
    """The rights fields a Wikisource page carries: its Index's ``rights_justification_id`` and, for a file where
    Google is not ruled out, the page's ``google_watermark_bbox`` (fractions of the page render; None when none was
    found) and hygiene entry."""

    commons = index.get("commons_file") or {}
    record = wikisource_rights_justification(index_key=str(index.get("index_key") or ""), commons_file=commons.get("title"),
                                             sha1=commons.get("sha1"), path=path)
    fields: dict[str, Any] = {"rights_justification_id": None if record is None else record["id"]}
    if record is not None and hygiene_required(record) and isinstance(record.get("hygiene"), Mapping):
        entry = hygiene_page(record["hygiene"], int(_scan_page(page) or -1))
        if entry is not None:
            fields["google_watermark_bbox"] = entry.get("google_watermark_bbox")
            fields["google_hygiene"] = {"box_units": BOX_UNITS, **entry}
    return fields


def wikisource_page_blocker(page: Mapping[str, Any], index: Mapping[str, Any], *, path: Path | None = None) -> str | None:
    """``wikisource_derivation_blocker`` for a snapshot page record and its Index record (the snapshot shape)."""

    commons = index.get("commons_file") or {}
    fields = page_justification_fields(page, index, path=path)
    return wikisource_derivation_blocker(
        {"rights_justification_id": fields["rights_justification_id"], "commons_file_sha1": commons.get("sha1"),
         "scan_page": _scan_page(page)},
        path=path,
    )
