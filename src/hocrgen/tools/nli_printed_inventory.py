"""Operator-only inventory of NLI digitized printed Hebrew books by IIIF licence slug (F8c2).

The tool measures how many digitized printed Hebrew books at the National Library of Israel carry the manifest
licence ``public-domain-free-use``, and how many pages they hold. Search results carry no rights field, so every
sampled hit's rights come from its IIIF manifest ``license`` slug through the F8c gate (``decide_nli_rights``).

Method (a random cluster sample of result pages):

1. The Search API query is ``language,exact,heb`` with ``material_type=book`` and
   ``availability_type=online_and_api_access``, 50 records a page. ``count_mode`` gives the population total.
2. Observed API behaviour on 2026-11-06, which the tool guards against:
   - ``sort_field`` is ignored, and date clauses in the query (``start_date``/``end_date``) silently drop the
     material and availability filters, so the API cannot stratify by period. Periods come from each record's
     own date string instead (:func:`parse_publication_year`).
   - Pages past a depth cap (about page 400, offset 20,000) return page 1 instead.
   - Some responses silently drop the filters, and a bad response is cached per URL. Every page is therefore
     validated record by record, and a failed page is retried with a different parameter order (a new URL).
3. A seeded random sample of pages is drawn from the reachable window. Each ``book`` record's manifest is fetched
   and its licence slug, canvas count, date, place and title are recorded. A manifest whose top level lists
   volume sequences without inline canvases (a multi-volume record, as in F8d2) has its volume sequences fetched,
   and each volume's canvas count is what the gate sees, as ``load_scan_capture`` does for a pinned volume.
4. Estimates are ratio estimates with cluster-sample (per page) standard errors.

The image-service ``info.json`` ``rights`` value (``nli-copying-prohibited`` on every manifest F8c checked) is
recorded for a small sample as evidence only. Under maintainer decision 13 (2026-11-06) the per-item manifest
licence slug governs NLI rights, and the ``info.json`` value never changes a rights result.

The API key is read only from ``NLI_API_KEY``; it is never printed, logged or written. Requests are spaced by at
least ``request_delay`` seconds, and the run stops on HTTP 403 or 429 from the Search API, on 429 anywhere, or
after a run of consecutive manifest failures. CI never runs the network path; the full inventory JSON stays
outside the repository, and only the deterministic summary (markdown, compact JSON) is committed.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import random
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hocrgen.fetchers.nli_iiif import (
    NLI_FREE_USE_SLUG,
    NLI_NON_COMMERCIAL_SLUGS,
    NliManifestCapture,
    canvas_image_service,
    decide_nli_rights,
    manifest_canvases,
)
from hocrgen.tools.nli_search_discovery import NLI_API_KEY_ENV, NLI_SEARCH_ENDPOINT, redact, summarize_search_record

INVENTORY_FORMAT = "hocrgen.nli_printed_inventory.v1"
SUMMARY_FORMAT = "hocrgen.nli_printed_inventory_summary.v1"
NLI_INVENTORY_USER_AGENT = "hocrgen-nli-printed-inventory (+https://github.com/HeOCR/hocrgen)"

SEARCH_QUERY = "language,exact,heb"
SEARCH_FILTERS = {"material_type": "book", "availability_type": "online_and_api_access"}
PAGE_SIZE = 50
DEFAULT_WINDOW_PAGES = 400
PRINTED_TYPE = "book"
ACCEPTED_TYPES = frozenset({"book", "ebook"})
GOOGLE_CLASS_SLUG = "public-domain-non-commercial-use"
COPYING_PROHIBITED_MARKER = "nli-copying-prohibited"

# Parameter orders tried for one page. The API caches a bad (filter-dropped) response per URL, so a retry must
# change the URL; reordering the same parameters does that without changing the request's meaning.
PARAMETER_ORDERS: tuple[tuple[str, ...], ...] = (
    ("query", "output_format", "material_type", "availability_type", "result_page"),
    ("output_format", "query", "availability_type", "material_type", "result_page"),
    ("availability_type", "material_type", "query", "result_page", "output_format"),
    ("result_page", "query", "material_type", "availability_type", "output_format"),
    ("material_type", "result_page", "output_format", "availability_type", "query"),
)

FetchResult = tuple[int, bytes]
Fetch = Callable[[str], FetchResult]

CAVEATS = (
    "`non-commercial-use-license` was first seen in this inventory (3 books). It is now in `NLI_NON_COMMERCIAL_SLUGS`, so the "
    "gate rejects it as `nli_license_non_commercial:non-commercial-use-license` with hint `RESTRICTED-NONOPEN`, not `UNKNOWN`. "
    "Classes are recomputed from each recorded slug, so this summary follows the current slug sets.",
    "An image service answering `info.json` with HTTP 415 (\"Identifier ... not supported\") suggests that item may not serve "
    "images; promotion should probe images first.",
    "Periods come from the catalog date string. Hebrew years map to AM - 3760, exact to within a year.",
)

LICENCE_CLASS_ORDER = (
    "free_use",
    "non_commercial_google",
    "non_commercial_other",
    "other_slug",
    "licence_missing_or_unrecognized",
    "manifest_http_error",
    "no_manifest_link",
)


class InventoryBlocked(RuntimeError):
    """Raised when the upstream signals a block; the run stops and keeps what it has."""


def fetch_url(url: str, *, timeout: float = 90.0) -> FetchResult:  # pragma: no cover - live network path
    request = Request(url, headers={"User-Agent": NLI_INVENTORY_USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), b""
    except (URLError, TimeoutError, OSError):
        return 0, b""


class Throttle:
    """Space requests by at least ``delay`` seconds (the courtesy limit is one request a second)."""

    def __init__(self, fetch: Fetch, delay: float, sleep: Callable[[float], None], clock: Callable[[], float]):
        self._fetch = fetch
        self._delay = delay
        self._sleep = sleep
        self._clock = clock
        self._last: float | None = None
        self.requests = 0

    def __call__(self, url: str) -> FetchResult:
        if self._last is not None:
            wait = self._delay - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
        try:
            return self._fetch(url)
        finally:
            self._last = self._clock()
            self.requests += 1


# --- dates -------------------------------------------------------------------------------------------------

HEBREW_LETTER_VALUES = {
    "א": 1, "ב": 2, "ג": 3, "ד": 4, "ה": 5, "ו": 6, "ז": 7, "ח": 8, "ט": 9,
    "י": 10, "כ": 20, "ך": 20, "ל": 30, "מ": 40, "ם": 40, "נ": 50, "ן": 50, "ס": 60, "ע": 70,
    "פ": 80, "ף": 80, "צ": 90, "ץ": 90, "ק": 100, "ר": 200, "ש": 300, "ת": 400,
}  # fmt: skip
MIN_YEAR = 1450
MAX_YEAR = 2030
_GERSHAYIM = "\"״"
_HEBREW_YEAR = re.compile(rf"([א-ת]+)[{_GERSHAYIM}]([א-ת]?)")
_HEBREW_CENTURY = re.compile(rf"מאה\s+([א-ת]+)[{_GERSHAYIM}]?([א-ת]?)")
_GREGORIAN_COMPACT = re.compile(r"^\s*(\d{4})\d{4}\s*$")
_GREGORIAN_YEAR = re.compile(r"(?<!\d)(1[4-9]\d\d|20[0-2]\d)(?!\d)")
_GREGORIAN_CENTURY = re.compile(r"(?<!\d)(1[4-9]|20)(?:--|\?\?|xx)(?!\d)", re.IGNORECASE)
_BRACKETED = re.compile(r"\[([^\]]*)\]?")
_HEBREW_DECADE = re.compile(r"(?<![\u05d0-\u05ea])([\u05d0-\u05ea]{2,3})(?:-|\?)")


def hebrew_numeral_value(letters: str) -> int:
    return sum(HEBREW_LETTER_VALUES.get(letter, 0) for letter in letters)


def _hebrew_year(text: str) -> int | None:
    for match in _HEBREW_YEAR.finditer(text):
        letters = match.group(1) + match.group(2)
        value = hebrew_numeral_value(letters)
        if value >= 1000 or len(letters) < 2:
            continue
        year = value + 1240  # Anno Mundi 5000 + value, minus 3760
        if MIN_YEAR <= year <= MAX_YEAR:
            return year
    return None


def parse_publication_year(text: str | None) -> tuple[int | None, str]:
    """Return a Gregorian year and its precision (``year``, ``decade`` or ``century``) from an NLI date string.

    Search records carry dates such as ``18740101``, ``תרע"ב 1911``, ``[תקצ"ט]``, ``[18--]`` or ``מאה י"ט``.
    Gregorian years win; then a Hebrew year inside brackets; then any Hebrew year; then a stated century.
    Hebrew years map to the Gregorian year they mostly overlap (AM - 3760), which is exact to a year.
    """

    if not text:
        return None, "none"
    compact = _GREGORIAN_COMPACT.match(text)
    if compact and MIN_YEAR <= int(compact.group(1)) <= MAX_YEAR:
        return int(compact.group(1)), "year"
    gregorian = _GREGORIAN_YEAR.search(text)
    if gregorian:
        return int(gregorian.group(1)), "year"
    for bracketed in _BRACKETED.findall(text):
        year = _hebrew_year(bracketed)
        if year is not None:
            return year, "year"
    year = _hebrew_year(text)
    if year is not None:
        return year, "year"
    for bracketed in _BRACKETED.findall(text):
        for match in _HEBREW_DECADE.finditer(bracketed):
            value = hebrew_numeral_value(match.group(1))
            if value < 1000 and MIN_YEAR <= value + 1240 <= MAX_YEAR:
                return value + 1240, "decade"
    century = _HEBREW_CENTURY.search(text)
    if century:
        number = hebrew_numeral_value(century.group(1) + century.group(2))
        if MIN_YEAR <= (number - 1) * 100 + 50 <= MAX_YEAR:
            return (number - 1) * 100 + 50, "century"
    gregorian_century = _GREGORIAN_CENTURY.search(text)
    if gregorian_century:
        return int(gregorian_century.group(1)) * 100 + 50, "century"
    return None, "unparsed"


def century_label(year: int | None) -> str:
    if year is None:
        return "unknown"
    if year < 1500:
        return "before 1500"
    return f"{year // 100 * 100}s"


# --- search pages ------------------------------------------------------------------------------------------


def search_url(*, api_key: str, page: int, order_index: int) -> str:
    values = {"query": SEARCH_QUERY, "output_format": "json", "result_page": str(page), **SEARCH_FILTERS}
    order = PARAMETER_ORDERS[order_index % len(PARAMETER_ORDERS)]
    pairs = [(key, values[key]) for key in order] + [("api_key", api_key)]
    return f"{NLI_SEARCH_ENDPOINT}?{urlencode(pairs)}"


def count_url(*, api_key: str) -> str:
    pairs = [("query", SEARCH_QUERY), *SEARCH_FILTERS.items(), ("count_mode", "true"), ("api_key", api_key)]
    return f"{NLI_SEARCH_ENDPOINT}?{urlencode(pairs)}"


def _record_ids(records: Iterable[dict[str, Any]]) -> list[str]:
    return [str(summarize_search_record(record)["record_id"]) for record in records]


def classify_search_page(records: Any, *, page: int, page_one_ids: list[str] | None) -> str:
    """Return ``ok``, ``empty``, ``not_a_list``, ``filter_dropped`` or ``fallback_page_one``."""

    if not isinstance(records, list):
        return "not_a_list"
    records = [record for record in records if isinstance(record, dict)]
    if not records:
        return "empty"
    for record in records:
        summary = summarize_search_record(record)
        if summary["type"] not in ACCEPTED_TYPES or "online_and_api_access" not in summary["access_rights"]:
            return "filter_dropped"
        if "heb" not in str(summary["language"] or "").split(";"):
            return "filter_dropped"
    if page > 1 and page_one_ids is not None and _record_ids(records) == page_one_ids:
        return "fallback_page_one"
    return "ok"


def fetch_search_page(
    *,
    api_key: str,
    page: int,
    fetch: Fetch,
    page_one_ids: list[str] | None,
    max_attempts: int = len(PARAMETER_ORDERS),
) -> dict[str, Any]:
    attempts: list[str] = []
    for attempt in range(max_attempts):
        status, body = fetch(search_url(api_key=api_key, page=page, order_index=attempt))
        if status in {403, 429}:
            raise InventoryBlocked(f"Search API returned HTTP {status} on page {page}")
        if status != 200:
            attempts.append(f"http_{status}")
            continue
        try:
            records = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            attempts.append("not_json")
            continue
        outcome = classify_search_page(records, page=page, page_one_ids=page_one_ids)
        attempts.append(outcome)
        if outcome == "ok":
            return {"attempts": attempts, "page": page, "records": records, "status": "ok"}
        if outcome == "fallback_page_one":
            break
    return {"attempts": attempts, "page": page, "records": [], "status": attempts[-1] if attempts else "not_fetched"}


# --- manifests ---------------------------------------------------------------------------------------------


def licence_class(slug: str | None, reason: str) -> str:
    if slug == NLI_FREE_USE_SLUG:
        return "free_use"
    if slug == GOOGLE_CLASS_SLUG:
        return "non_commercial_google"
    if slug in NLI_NON_COMMERCIAL_SLUGS:
        return "non_commercial_other"
    if slug:
        return "other_slug"
    if reason.startswith("nli_iiif_manifest_http") or reason == "nli_iiif_manifest_missing":
        return "manifest_http_error"
    return "licence_missing_or_unrecognized"


def volume_sequence_urls(manifest: dict[str, Any]) -> list[str]:
    """Sequences listed by @id without inline canvases: the volumes of a multi-volume record (F8d2)."""

    urls: list[str] = []
    for sequence in manifest.get("sequences") or []:
        if isinstance(sequence, dict) and "canvases" not in sequence and isinstance(sequence.get("@id"), str):
            urls.append(sequence["@id"])
    return urls


def _json_object(status: int, body: bytes) -> dict[str, Any] | None:
    if status != 200:
        return None
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _first_image_service(canvases: list[dict[str, Any]]) -> str | None:
    for canvas in canvases[:1]:
        return canvas_image_service(canvas)
    return None


def inspect_manifest(manifest_url: str, fetch: Fetch, *, max_volumes: int = 12) -> dict[str, Any]:
    """Fetch one manifest and decide its rights with the F8c gate; resolve volume sequences for free-use items."""

    status, body = fetch(manifest_url)
    manifest = _json_object(status, body)
    canvases = manifest_canvases(manifest) if manifest is not None else []
    capture = NliManifestCapture(
        manifest_url=manifest_url,
        http_status=status,
        canvas_count=len(canvases) if manifest is not None else None,
        manifest=manifest,
    )
    decision = decide_nli_rights(display_rights=None, capture=capture)
    result: dict[str, Any] = {
        "canvas_count": capture.canvas_count,
        "decision": "accepted" if decision.accepted else "rejected",
        "http_status": status,
        "licence_class": licence_class(decision.license_slug, decision.reason),
        "license_slug": decision.license_slug,
        "reason": decision.reason,
        "image_service": _first_image_service(canvases),
    }
    volumes = volume_sequence_urls(manifest) if manifest is not None else []
    if volumes:
        result["volume_sequence_count"] = len(volumes)
    if volumes and not canvases and decision.license_slug == NLI_FREE_USE_SLUG:
        resolved: list[dict[str, Any]] = []
        for url in volumes[:max_volumes]:
            volume_status, volume_body = fetch(url)
            sequence = _json_object(volume_status, volume_body)
            volume_canvases = [c for c in (sequence or {}).get("canvases") or [] if isinstance(c, dict)]
            count = len(volume_canvases) if sequence is not None else None
            # The gate sees the volume's own canvas count, exactly as a pinned F8d2 volume capture does.
            volume_decision = decide_nli_rights(display_rights=None, capture=dataclasses.replace(capture, canvas_count=count))
            resolved.append(
                {
                    "canvas_count": count,
                    "decision": "accepted" if volume_decision.accepted else "rejected",
                    "http_status": volume_status,
                    "reason": volume_decision.reason,
                    "sequence_url": url,
                }
            )
            if result["image_service"] is None and volume_canvases:
                result["image_service"] = _first_image_service(volume_canvases)
        result["volumes"] = resolved
        result["volumes_unresolved"] = max(0, len(volumes) - max_volumes)
    return result


def effective_canvas_count(check: dict[str, Any]) -> int:
    """Pages the gate admits for one record: top-level canvases, or the sum over accepted volumes."""

    if check.get("decision") == "accepted":
        return int(check.get("canvas_count") or 0)
    return sum(int(volume["canvas_count"] or 0) for volume in check.get("volumes") or [] if volume["decision"] == "accepted")


def outcome_class(check: dict[str, Any] | None) -> str:
    """One of the inventory outcome classes; free-use is split by whether any pages are admissible."""

    if check is None:
        return "no_manifest_link"
    # Recomputed from the recorded slug, so a summary follows the current gate's slug sets, not the run-time ones.
    cls = licence_class(check.get("license_slug"), str(check.get("reason") or ""))
    if cls != "free_use":
        return cls
    if check["decision"] == "accepted":
        return "free_use"
    if effective_canvas_count(check) > 0:
        return "free_use_multi_volume"
    if check.get("volume_sequence_count"):
        return "free_use_empty_volume_sequences"
    return "free_use_zero_canvases"


def check_image_rights(image_service: str, fetch: Fetch) -> dict[str, Any]:
    status, body = fetch(f"{image_service.rstrip('/')}/info.json")
    info = _json_object(status, body)
    rights = (info or {}).get("rights") if info is not None else None
    if rights is None and info is not None:
        rights = info.get("license")
    return {"http_status": status, "image_service": image_service, "rights": rights if isinstance(rights, str) else None}


# --- the run -----------------------------------------------------------------------------------------------


def sample_pages(*, window_pages: int, sample_size: int, seed: int) -> list[int]:
    sample_size = max(0, min(sample_size, window_pages))
    return sorted(random.Random(seed).sample(range(1, window_pages + 1), sample_size))


def parse_count(body: bytes) -> int | None:
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    total = payload.get("countInfos", {}).get("total") if isinstance(payload, dict) else None
    return total if isinstance(total, int) and not isinstance(total, bool) else None


def record_entry(record: dict[str, Any]) -> dict[str, Any]:
    summary = summarize_search_record(record)
    year, precision = parse_publication_year(summary["date"])
    publisher = summary["publisher"] or ""
    place = publisher.split(":", 1)[0].strip() if ":" in publisher else None
    return {
        "century": century_label(year),
        "date": summary["date"],
        "item_url": summary["item_url"],
        "language": summary["language"],
        "manifest_url": summary["manifest_url"],
        "place": place or None,
        "publisher": summary["publisher"],
        "record_id": summary["record_id"],
        "title": summary["title"],
        "type": summary["type"],
        "year": year,
        "year_precision": precision,
    }


def run_inventory(
    *,
    api_key: str | None,
    sample_size: int = 40,
    window_pages: int = DEFAULT_WINDOW_PAGES,
    seed: int = 20261106,
    population_total: int | None = None,
    info_json_checks: int = 30,
    max_volumes: int = 12,
    request_delay: float = 1.1,
    max_consecutive_manifest_failures: int = 10,
    captured_on: str | None = None,
    fetch: Fetch | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
    progress: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    throttle = Throttle(fetch or fetch_url, request_delay, sleep or time.sleep, clock or time.monotonic)
    say = progress or (lambda _message: None)
    report: dict[str, Any] = {
        "captured_on": captured_on,
        "format": INVENTORY_FORMAT,
        "method": {
            "endpoint": NLI_SEARCH_ENDPOINT,
            "filters": dict(SEARCH_FILTERS),
            "info_json_checks": info_json_checks,
            "max_volumes_per_record": max_volumes,
            "page_size": PAGE_SIZE,
            "query": SEARCH_QUERY,
            "request_delay_seconds": request_delay,
            "sample_pages_requested": sample_size,
            "seed": seed,
            "window_pages": window_pages,
        },
        "pages": [],
        "records": [],
        "image_rights_sample": [],
    }
    if not api_key:
        report["status"] = "no_api_key"
        report["message"] = f"{NLI_API_KEY_ENV} is not set; no request was made."
        return report
    try:
        if population_total is None:
            status, body = throttle(count_url(api_key=api_key))
            if status in {403, 429}:
                raise InventoryBlocked(f"Search API returned HTTP {status} on the count request")
            population_total = parse_count(body) if status == 200 else None
            report["population_total_source"] = "count_mode" if population_total is not None else "unavailable"
        else:
            report["population_total_source"] = "operator"
        report["population_total"] = population_total
        page_one = fetch_search_page(api_key=api_key, page=1, fetch=throttle, page_one_ids=None)
        page_one_ids = _record_ids(page_one["records"]) if page_one["status"] == "ok" else None
        pages = sample_pages(window_pages=window_pages, sample_size=sample_size, seed=seed)
        failures = 0
        for page in pages:
            fetched = page_one if page == 1 else fetch_search_page(api_key=api_key, page=page, fetch=throttle, page_one_ids=page_one_ids)
            report["pages"].append({"attempts": fetched["attempts"], "page": page, "records": len(fetched["records"]), "status": fetched["status"]})
            say(f"page {page}: {fetched['status']} ({len(fetched['records'])} records)")
            for record in fetched["records"]:
                if not isinstance(record, dict):
                    continue
                entry = record_entry(record)
                entry["page"] = page
                if entry["type"] == PRINTED_TYPE and entry["manifest_url"]:
                    check = inspect_manifest(str(entry["manifest_url"]), throttle, max_volumes=max_volumes)
                    entry["manifest_check"] = check
                    if check["http_status"] == 429:
                        raise InventoryBlocked("IIIF returned HTTP 429")
                    failures = failures + 1 if check["http_status"] != 200 else 0
                    if failures >= max_consecutive_manifest_failures:
                        raise InventoryBlocked(f"{failures} consecutive manifest failures")
                report["records"].append(entry)
        free_use_services = [
            entry["manifest_check"]["image_service"]
            for entry in report["records"]
            if outcome_class(entry.get("manifest_check")) in {"free_use", "free_use_multi_volume"}
            and entry["manifest_check"].get("image_service")
        ]
        for service in random.Random(seed).sample(free_use_services, min(info_json_checks, len(free_use_services))):
            report["image_rights_sample"].append(check_image_rights(service, throttle))
        report["status"] = "ok"
    except InventoryBlocked as exc:
        report["status"] = "stopped_blocked"
        report["message"] = redact(str(exc), api_key)
    report["requests"] = throttle.requests
    return report


# --- summary -----------------------------------------------------------------------------------------------


def _ratio_estimate(pairs: list[tuple[float, float]], total_clusters: int | None) -> tuple[float, float]:
    """Ratio estimate sum(y)/sum(m) and its cluster-sample standard error, with a finite-population correction."""

    n = len(pairs)
    total_m = sum(m for _y, m in pairs)
    if n == 0 or total_m == 0:
        return 0.0, 0.0
    ratio = sum(y for y, _m in pairs) / total_m
    if n < 2:
        return ratio, 0.0
    mean_m = total_m / n
    residual = sum((y - ratio * m) ** 2 for y, m in pairs) / (n - 1)
    fpc = max(1 - n / total_clusters, 0.0) if total_clusters else 1.0
    return ratio, math.sqrt(max(fpc, 0.0) * residual / n) / mean_m


def _round(value: float, digits: int = 4) -> float:
    return round(value, digits)


def summarize_inventory(report: dict[str, Any]) -> dict[str, Any]:
    """Deterministic summary of a full inventory report: counts, shares, estimates. No titles, no URLs."""

    pages_ok = sorted(page["page"] for page in report["pages"] if page["status"] == "ok")
    by_page: dict[int, list[dict[str, Any]]] = {page: [] for page in pages_ok}
    for entry in report["records"]:
        if entry["page"] in by_page:
            by_page[entry["page"]].append(entry)
    books = [entry for entry in report["records"] if entry["type"] == PRINTED_TYPE and entry["page"] in by_page]
    records_seen = sum(len(entries) for entries in by_page.values())
    outcome_counts = Counter(outcome_class(entry.get("manifest_check")) for entry in books)
    slug_counts = Counter(
        (entry.get("manifest_check") or {}).get("license_slug") or f"({outcome_class(entry.get('manifest_check'))})" for entry in books
    )
    http_counts = Counter(str((entry.get("manifest_check") or {}).get("http_status", "no_link")) for entry in books)
    population = report.get("population_total")
    window_pages = report["method"]["window_pages"]
    total_pages = math.ceil(population / PAGE_SIZE) if population else None
    reachable_clusters = min(window_pages, total_pages) if total_pages else window_pages
    book_share, book_share_se = _ratio_estimate(
        [(sum(1 for e in by_page[p] if e["type"] == PRINTED_TYPE), len(by_page[p])) for p in pages_ok], reachable_clusters
    )
    estimated_books = population * book_share if population else None
    reachable = min(population, window_pages * PAGE_SIZE) if population else None

    def estimate(predicate: Callable[[dict[str, Any]], float], *, share: bool = True) -> dict[str, Any]:
        # Per book for display; the population estimate is the ratio over all sampled records times the
        # population total, so the uncertainty of the book share is carried by the same cluster error.
        totals = [(sum(predicate(e) for e in by_page[p] if e["type"] == PRINTED_TYPE), by_page[p]) for p in pages_ok]
        ratio, se = _ratio_estimate([(y, sum(1 for e in page if e["type"] == PRINTED_TYPE)) for y, page in totals], reachable_clusters)
        high = min(ratio + 1.96 * se, 1.0) if share else ratio + 1.96 * se
        result: dict[str, Any] = {"per_book": _round(ratio), "per_book_ci95": [_round(max(ratio - 1.96 * se, 0.0)), _round(high)]}
        if population and reachable:
            per_record, per_record_se = _ratio_estimate([(y, len(page)) for y, page in totals], reachable_clusters)
            low, high_record = max(per_record - 1.96 * per_record_se, 0.0), per_record + 1.96 * per_record_se
            window_ci = [int(round(low * reachable, -1)), int(round(high_record * reachable, -1))]
            result["window_estimate"] = int(round(per_record * reachable, -1))
            result["window_ci95"] = window_ci
            # Only the reachable window was sampled. Extrapolating assumes the rest looks like it; the bounds do not.
            result["extrapolated_estimate"] = int(round(per_record * population, -1))
            unreachable = population - reachable
            result["whole_set_bounds"] = [window_ci[0], window_ci[1] + unreachable] if share else [window_ci[0], None]
        return result

    free_use_outcomes = {"free_use", "free_use_multi_volume"}
    estimates = {
        cls: estimate(lambda e, cls=cls: 1.0 if outcome_class(e.get("manifest_check")) == cls else 0.0)
        for cls in sorted(set(outcome_counts) | {"free_use", "non_commercial_google"}, key=_outcome_sort_key)
    }
    estimates["free_use_with_pages"] = estimate(lambda e: 1.0 if outcome_class(e.get("manifest_check")) in free_use_outcomes else 0.0)
    free_use_pages = estimate(lambda e: float(effective_canvas_count(e["manifest_check"])) if outcome_class(e.get("manifest_check")) in free_use_outcomes else 0.0, share=False)
    free_use_books = [e for e in books if outcome_class(e.get("manifest_check")) in free_use_outcomes]
    canvas_counts = sorted(effective_canvas_count(e["manifest_check"]) for e in free_use_books)
    centuries = sorted({e["century"] for e in books}, key=_century_sort_key)
    by_century = {
        century: {
            "books": sum(1 for e in books if e["century"] == century),
            "free_use_with_pages": sum(1 for e in free_use_books if e["century"] == century),
            "free_use_pages": sum(effective_canvas_count(e["manifest_check"]) for e in free_use_books if e["century"] == century),
            "non_commercial_google": sum(1 for e in books if e["century"] == century and outcome_class(e.get("manifest_check")) == "non_commercial_google"),
        }
        for century in centuries
    }
    half = window_pages // 2
    halves = {}
    for label, pages in (("pages_1_to_%d" % half, [p for p in pages_ok if p <= half]), ("pages_%d_to_%d" % (half + 1, window_pages), [p for p in pages_ok if p > half])):
        part = [e for p in pages for e in by_page[p] if e["type"] == PRINTED_TYPE]
        halves[label] = {
            "books": len(part),
            "free_use_share": _round(sum(1 for e in part if outcome_class(e.get("manifest_check")) in free_use_outcomes) / len(part)) if part else None,
            "sampled_pages": len(pages),
        }
    image_rights = Counter(
        ("nli-copying-prohibited" if COPYING_PROHIBITED_MARKER in (sample.get("rights") or "") else (sample.get("rights") or f"(image service HTTP {sample['http_status']}, no info.json)"))
        for sample in report.get("image_rights_sample", [])
    )
    sequence_refs = [int((e.get("manifest_check") or {}).get("volume_sequence_count") or 0) for e in books]
    by_page_rows = [
        [
            p,
            sum(1 for e in by_page[p] if e["type"] == PRINTED_TYPE),
            sum(1 for e in by_page[p] if e["type"] == PRINTED_TYPE and outcome_class(e.get("manifest_check")).startswith("free_use")),
            sum(1 for e in by_page[p] if e["type"] == PRINTED_TYPE and outcome_class(e.get("manifest_check")) in free_use_outcomes),
            sum(1 for e in by_page[p] if e["type"] == PRINTED_TYPE and outcome_class(e.get("manifest_check")) == "non_commercial_google"),
        ]
        for p in pages_ok
    ]
    return {
        "captured_on": report.get("captured_on"),
        "format": SUMMARY_FORMAT,
        "method": {
            **report["method"],
            "population_total": population,
            "population_total_source": report.get("population_total_source"),
            "reachable_records": reachable,
            "sampled_pages_ok": len(pages_ok),
            "sampled_pages_failed": sorted(page["page"] for page in report["pages"] if page["status"] != "ok"),
            "search_retries": sum(len(page["attempts"]) - 1 for page in report["pages"] if page["attempts"]),
            "requests": report.get("requests"),
            "status": report.get("status"),
        },
        "sample": {
            "records_seen": records_seen,
            "books": len(books),
            "other_types": dict(sorted(Counter(e["type"] for e in report["records"] if e["type"] != PRINTED_TYPE and e["page"] in by_page).items())),
            "book_share": _round(book_share),
            "book_share_ci95": [_round(max(book_share - 1.96 * book_share_se, 0.0)), _round(min(book_share + 1.96 * book_share_se, 1.0))],
            "outcomes": {key: outcome_counts[key] for key in sorted(outcome_counts, key=_outcome_sort_key)},
            "licence_slugs": dict(sorted(slug_counts.items(), key=lambda item: (-item[1], item[0]))),
            "manifest_http_status": dict(sorted(http_counts.items())),
            "records_with_sequence_refs": sum(1 for n in sequence_refs if n),
            "records_with_two_or_more_sequence_refs": sum(1 for n in sequence_refs if n >= 2),
            "free_use_pages": sum(canvas_counts),
            "free_use_pages_median": canvas_counts[len(canvas_counts) // 2] if canvas_counts else None,
            "dates_unparsed": sum(1 for e in books if e["year"] is None),
        },
        "estimates": {"books": int(round(estimated_books, -1)) if estimated_books is not None else None, "by_outcome": estimates, "free_use_pages": free_use_pages},
        "by_century": by_century,
        "window_halves": halves,
        "by_page": by_page_rows,
        "image_rights_sample": dict(sorted(image_rights.items())),
    }


def _outcome_sort_key(name: str) -> tuple[int, str]:
    order = ("free_use", "free_use_multi_volume", "free_use_empty_volume_sequences", "free_use_zero_canvases", *LICENCE_CLASS_ORDER[1:])
    return (order.index(name) if name in order else len(order), name)


def _century_sort_key(label: str) -> tuple[int, str]:
    if label == "unknown":
        return (9999, label)
    if label == "before 1500":
        return (0, label)
    return (int(label[:4]), label)


def compact_records(report: dict[str, Any]) -> list[list[Any]]:
    """Sorted ``[record_id, licence slug or outcome, admissible canvas count]`` rows for the sampled books."""

    rows = []
    for entry in report["records"]:
        if entry["type"] != PRINTED_TYPE:
            continue
        check = entry.get("manifest_check")
        label = (check or {}).get("license_slug") or f"({outcome_class(check)})"
        rows.append([str(entry["record_id"]), label, effective_canvas_count(check) if check else 0])
    return sorted(rows)


def compact_json(summary: dict[str, Any], rows: list[list[Any]]) -> str:
    """The committed JSON: the summary, then one ``[record_id, slug, canvases]`` row a line."""

    head = json.dumps({"format": SUMMARY_FORMAT, "summary": summary}, ensure_ascii=False, indent=1, sort_keys=True)
    body = ",\n".join("  " + json.dumps(row, ensure_ascii=False) for row in rows)
    return head[:-2] + ',\n "books": [\n' + body + "\n ]\n}\n"


def _estimate_cells(est: dict[str, Any], sep: str = " | ") -> str:
    if "window_estimate" not in est:
        return sep.join(["n/a"] * 3)
    low, high = est["whole_set_bounds"]
    bounds = f"{low}-{high}" if high is not None else f"at least {low}"
    return sep.join([f"{est['window_estimate']} ({est['window_ci95'][0]}-{est['window_ci95'][1]})", str(est["extrapolated_estimate"]), bounds])


def _estimate_sentence(est: dict[str, Any]) -> str:
    if "window_estimate" not in est:
        return "no population total, so no estimate"
    low, high = est["whole_set_bounds"]
    bounds = f"bounds {low}-{high}" if high is not None else f"at least {low}"
    return (
        f"reachable window {est['window_estimate']} (95% CI {est['window_ci95'][0]}-{est['window_ci95'][1]}); "
        f"whole set if like the window {est['extrapolated_estimate']}; {bounds}"
    )


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def render_markdown(summary: dict[str, Any]) -> str:
    method, sample, estimates = summary["method"], summary["sample"], summary["estimates"]
    lines = [
        "# NLI digitized printed Hebrew books by IIIF licence slug (F8c2)",
        "",
        f"Generated by `python -m hocrgen.tools.nli_printed_inventory` from evidence captured on {summary['captured_on']}; do not edit by hand. "
        "The per-book rows (record id, licence slug, admissible canvas count) are in "
        "[`nli_printed_inventory.json`](./nli_printed_inventory.json); the full inventory JSON stays outside the repository. "
        "Rights come from each manifest's `license` slug through the unchanged F8c gate (`decide_nli_rights`). "
        "Nothing here is a seed, a source or a release item.",
        "",
        "## Method",
        "",
        f"- Search API query `{method['query']}` with `material_type={method['filters']['material_type']}` and "
        f"`availability_type={method['filters']['availability_type']}`, {method['page_size']} records a page.",
        f"- Population: {method['population_total']} records ({method['population_total_source']}). Pages past about page "
        f"{method['window_pages']} return page 1, so {method['reachable_records']} records are reachable in the API's default order.",
        f"- Random cluster sample: {method['sampled_pages_ok']} of {method['sample_pages_requested']} requested pages from pages "
        f"1-{method['window_pages']} (seed {method['seed']}); failed pages: {method['sampled_pages_failed'] or 'none'}; "
        f"{method['search_retries']} search retries; {method['requests']} requests at one per {method['request_delay_seconds']} s or slower; run status `{method['status']}`.",
        "- Every `book` record's manifest was fetched. Multi-volume records (volume sequences without inline canvases) had up to "
        f"{method['max_volumes_per_record']} volume sequences fetched; the gate sees each volume's own canvas count, as for F8d2's pinned volume.",
        "- Estimates are ratio estimates with per-page cluster standard errors (95% intervals). The window estimate covers the "
        "reachable records only. The extrapolation to the whole result set assumes the unreachable records look like the window; "
        "the bounds assume nothing (the unreachable records could all be in, or all out of, a class). The result order comes in "
        "large homogeneous blocks (see the per-page table), so the extrapolation is weak.",
        "",
        "## Sample",
        "",
        f"- Records seen: {sample['records_seen']}; `book`: {sample['books']}; other types: {sample['other_types'] or 'none'}.",
        f"- Manifests listing sequences by reference without inline canvases: {sample['records_with_sequence_refs']} "
        f"({sample['records_with_two_or_more_sequence_refs']} with two or more, i.e. multi-volume). Book dates that did not parse: {sample['dates_unparsed']}.",
        "",
        f"| Outcome | Books | Share of books (95% CI) | Window of {method['reachable_records']} records (95% CI) | Whole set if like the window | Whole-set bounds |",
        "| --- | ---: | --- | --- | ---: | --- |",
    ]
    for name, count in sample["outcomes"].items():
        est = estimates["by_outcome"].get(name, {})
        ci = est.get("per_book_ci95", [0, 0])
        lines.append(
            f"| `{name}` | {count} | {_pct(est.get('per_book'))} ({_pct(ci[0])}-{_pct(ci[1])}) | {_estimate_cells(est)} |"
        )
    fu = estimates["by_outcome"]["free_use_with_pages"]
    pages = estimates["free_use_pages"]
    lines += [
        "",
        f"- Estimated `book` records in the population: {estimates['books']}.",
        f"- **Free-use books with admissible pages:** {_pct(fu['per_book'])} of books ({_pct(fu['per_book_ci95'][0])}-{_pct(fu['per_book_ci95'][1])}); "
        f"{_estimate_sentence(fu)}.",
        f"- **Free-use pages (canvases):** {sample['free_use_pages']} in the sample (median {sample['free_use_pages_median']} a free-use book with pages); "
        f"{pages['per_book']:.1f} a book overall; {_estimate_sentence(pages)}.",
        "",
        "### Licence slugs in the sample",
        "",
        "| Slug or outcome | Books |",
        "| --- | ---: |",
        *[f"| `{slug}` | {count} |" for slug, count in sample["licence_slugs"].items()],
        "",
        "### Manifest HTTP status",
        "",
        "| Status | Books |",
        "| --- | ---: |",
        *[f"| {status} | {count} |" for status, count in sample["manifest_http_status"].items()],
        "",
        "## By century (sample)",
        "",
        "| Period | Books | Free-use with pages | Free-use pages | Google class (non-commercial) |",
        "| --- | ---: | ---: | ---: | ---: |",
        *[
            f"| {century} | {row['books']} | {row['free_use_with_pages']} | {row['free_use_pages']} | {row['non_commercial_google']} |"
            for century, row in summary["by_century"].items()
        ],
        "",
        "Periods come from each record's date string: a Gregorian year, else a Hebrew year (AM - 3760), else a stated century.",
        "",
        "## Result order",
        "",
        "Per sampled page: books, free-use books (any), free-use books with admissible pages, Google-class books.",
        "",
        "| Page | Books | Free-use (any) | Free-use with pages | Google class |",
        "| ---: | ---: | ---: | ---: | ---: |",
        *[f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |" for row in summary["by_page"]],
        "",
        "## Window check",
        "",
        "| Window part | Sampled pages | Books | Share free-use with pages |",
        "| --- | ---: | ---: | --- |",
        *[f"| {label} | {row['sampled_pages']} | {row['books']} | {_pct(row['free_use_share'])} |" for label, row in summary["window_halves"].items()],
        "",
        "## Image-service rights (evidence only)",
        "",
        "The IIIF Image API `info.json` `rights` value of sampled free-use items. Under maintainer decision 13 (2026-11-06) the "
        "per-item manifest `license` slug governs NLI rights; this value is recorded as evidence only and never changes a rights result.",
        "",
        "| `info.json` rights | Items |",
        "| --- | ---: |",
        *([f"| `{value}` | {count} |" for value, count in summary["image_rights_sample"].items()] or ["| (none sampled) | 0 |"]),
        "",
        "## Caveats",
        "",
        *[f"- {line}" for line in CAVEATS],
        "",
    ]
    return "\n".join(lines)


# --- CLI ---------------------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator-only NLI printed-book licence-slug inventory (F8c2).")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="Sample the Search API and the IIIF manifests (network).")
    run.add_argument("--report-path", type=Path, required=True, help="Full inventory JSON; keep it outside the repository.")
    run.add_argument("--sample-pages", type=int, default=40)
    run.add_argument("--window-pages", type=int, default=DEFAULT_WINDOW_PAGES)
    run.add_argument("--seed", type=int, default=20261106)
    run.add_argument("--population-total", type=int)
    run.add_argument("--info-json-checks", type=int, default=30)
    run.add_argument("--max-volumes", type=int, default=12)
    run.add_argument("--request-delay", type=float, default=1.1)
    run.add_argument("--captured-on", default=time.strftime("%Y-%m-%d"))
    summarize = sub.add_parser("summarize", help="Write the deterministic summary from a full report (no network).")
    summarize.add_argument("--report-path", type=Path, required=True)
    summarize.add_argument("--markdown-path", type=Path, required=True)
    summarize.add_argument("--compact-json-path", type=Path)
    summarize.add_argument("--population-total", type=int, help="Override the report's count, for example a re-checked count_mode total.")
    return parser.parse_args(argv)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "summarize":
        report = json.loads(args.report_path.read_text(encoding="utf-8"))
        if args.population_total is not None:
            report["population_total"] = args.population_total
            report["population_total_source"] = "operator"
        summary = summarize_inventory(report)
        _write(args.markdown_path, render_markdown(summary))
        if args.compact_json_path is not None:
            _write(args.compact_json_path, compact_json(summary, compact_records(report)))
        sys.stdout.write(json.dumps(summary["sample"]["outcomes"], indent=2) + "\n")
        return 0
    api_key = os.environ.get(NLI_API_KEY_ENV) or None
    report = run_inventory(
        api_key=api_key,
        sample_size=args.sample_pages,
        window_pages=args.window_pages,
        seed=args.seed,
        population_total=args.population_total,
        info_json_checks=args.info_json_checks,
        max_volumes=args.max_volumes,
        request_delay=args.request_delay,
        captured_on=args.captured_on,
        progress=lambda message: sys.stderr.write(redact(message, api_key) + "\n"),
    )
    _write(args.report_path, redact(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True), api_key) + "\n")
    sys.stdout.write(json.dumps({"status": report["status"], "records": len(report["records"]), "requests": report.get("requests")}) + "\n")
    return 0 if report["status"] in {"ok", "no_api_key"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
