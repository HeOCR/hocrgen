"""Operator-only NLI Search API seed discovery (F8c).

Lists candidate NLI items for hand vetting. Search results carry no rights field (only an
``accessRights`` availability value such as ``online_and_api_access``), so every hit's rights are
checked on its IIIF manifest ``license`` slug. Only ``public-domain-free-use`` hits with canvases are
suggested as exploratory catalog entries; nothing is written to the seed manifests.

The API key is read only from the ``NLI_API_KEY`` environment variable. It is never printed, logged,
or written to the report: reports record the query parameters without it, and error text is redacted.
Without a key the tool reports ``no_api_key`` and exits cleanly; the hand-vetted seed list stays the
only seed source. CI never runs this tool.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hocrgen.fetchers.nli_iiif import NliManifestCapture, decide_nli_rights, manifest_canvases

NLI_SEARCH_ENDPOINT = "https://api2.nli.org.il/openlibrary/search"
NLI_API_KEY_ENV = "NLI_API_KEY"
NLI_DISCOVERY_USER_AGENT = "hocrgen-nli-search-discovery (+https://github.com/HeOCR/hocrgen)"
DC = "http://purl.org/dc/elements/1.1/"

FetchResult = tuple[int, bytes]


def redact(text: str, secret: str | None) -> str:
    return text.replace(secret, "[REDACTED]") if secret else text


def fetch_url(url: str, *, timeout: float = 60.0) -> FetchResult:  # pragma: no cover - live network path
    request = Request(url, headers={"User-Agent": NLI_DISCOVERY_USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read()
    except HTTPError as exc:
        return int(exc.code), b""
    except URLError as exc:
        return 0, str(exc.reason).encode("utf-8")


def _dc_values(record: dict[str, Any], field: str) -> list[str]:
    values = record.get(f"{DC}{field}") or []
    result: list[str] = []
    for value in values if isinstance(values, list) else []:
        if isinstance(value, dict):
            item = value.get("@value", value.get("@id"))
            if isinstance(item, str):
                result.append(item)
    return result


def summarize_search_record(record: dict[str, Any]) -> dict[str, Any]:
    manifests = [value for value in _dc_values(record, "relation") if value.endswith("/manifest")]
    return {
        "access_rights": _dc_values(record, "accessRights"),
        "date": (_dc_values(record, "date") or _dc_values(record, "non_standard_date") or [None])[0],
        "item_url": record.get("@id"),
        "language": (_dc_values(record, "language") or [None])[0],
        "manifest_url": manifests[0] if manifests else None,
        "publisher": (_dc_values(record, "publisher") or [None])[0],
        "record_id": (_dc_values(record, "recordid") or [None])[0],
        "title": (_dc_values(record, "title") or [None])[0],
        "type": (_dc_values(record, "type") or [None])[0],
    }


def check_manifest(manifest_url: str, fetch: Callable[[str], FetchResult]) -> dict[str, Any]:
    status, body = fetch(manifest_url)
    manifest: dict[str, Any] | None = None
    if status == 200:
        try:
            parsed = json.loads(body.decode("utf-8"))
            manifest = parsed if isinstance(parsed, dict) else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            manifest = None
    capture = NliManifestCapture(
        manifest_url=manifest_url,
        http_status=status,
        canvas_count=len(manifest_canvases(manifest)) if manifest is not None else None,
        manifest=manifest,
    )
    decision = decide_nli_rights(display_rights=None, capture=capture)
    return {
        "canvas_count": capture.canvas_count,
        "decision": "accepted" if decision.accepted else "rejected",
        "http_status": status,
        "license_slug": decision.license_slug,
        "reason": decision.reason,
    }


def discover(
    *,
    query: str,
    api_key: str | None,
    material_type: str | None = "book",
    availability_type: str | None = "online_and_api_access",
    max_manifest_checks: int = 10,
    request_delay: float = 1.5,
    fetch: Callable[[str], FetchResult] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> dict[str, Any]:
    fetch = fetch or fetch_url
    sleep = sleep or time.sleep
    params: dict[str, str] = {"query": query, "output_format": "json"}
    if material_type:
        params["material_type"] = material_type
    if availability_type:
        params["availability_type"] = availability_type
    report: dict[str, Any] = {
        "candidates": [],
        "endpoint": NLI_SEARCH_ENDPOINT,
        "query_parameters": dict(params),
        "rights_prefilter": "none: search results carry accessRights (availability) only; rights come from each IIIF manifest licence slug",
        "suggested_catalog_entries": [],
    }
    if not api_key:
        report["status"] = "no_api_key"
        report["message"] = (
            f"{NLI_API_KEY_ENV} is not set; skipping Search API discovery. "
            "The hand-vetted seed list remains the only seed source."
        )
        return report
    status, body = fetch(f"{NLI_SEARCH_ENDPOINT}?{urlencode({**params, 'api_key': api_key})}")
    if status != 200:
        report["status"] = "search_failed"
        report["message"] = redact(f"Search API returned HTTP {status}", api_key)
        return report
    try:
        records = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report["status"] = "search_failed"
        report["message"] = redact(f"Search API response is not JSON: {exc}", api_key)
        return report
    if not isinstance(records, list):
        records = []
    checks = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        summary = summarize_search_record(record)
        if summary["manifest_url"] and checks < max_manifest_checks:
            sleep(request_delay)
            summary["manifest_check"] = check_manifest(str(summary["manifest_url"]), fetch)
            checks += 1
            check = summary["manifest_check"]
            if check["decision"] == "accepted":
                report["suggested_catalog_entries"].append(
                    {
                        "iiif_manifest_url": summary["manifest_url"],
                        "notes": "Search API candidate; IIIF licence slug public-domain-free-use. Hand-vet before promotion.",
                        "title": summary["title"],
                        "url": summary["item_url"],
                    }
                )
        report["candidates"].append(summary)
    report["status"] = "ok"
    report["manifest_checks"] = checks
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator-only NLI Search API discovery of candidate seeds.")
    parser.add_argument("--query", required=True, help="NLI query, for example 'title,contains,הגדה'.")
    parser.add_argument("--material-type", default="book")
    parser.add_argument("--availability-type", default="online_and_api_access")
    parser.add_argument("--max-manifest-checks", type=int, default=10)
    parser.add_argument("--request-delay", type=float, default=1.5)
    parser.add_argument("--report-path", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get(NLI_API_KEY_ENV) or None
    report = discover(
        query=args.query,
        api_key=api_key,
        material_type=args.material_type or None,
        availability_type=args.availability_type or None,
        max_manifest_checks=args.max_manifest_checks,
        request_delay=args.request_delay,
    )
    text = redact(json.dumps(report, ensure_ascii=False, indent=2), api_key) + "\n"
    if args.report_path is not None:
        args.report_path.parent.mkdir(parents=True, exist_ok=True)
        args.report_path.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if report["status"] in {"ok", "no_api_key"} else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
