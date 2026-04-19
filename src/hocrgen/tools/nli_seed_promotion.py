from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml
from PIL import Image

from hocrgen.core.errors import StageExecutionError


DEFAULT_REQUIRED_RIGHTS = "Any Use Permitted"
ALLOWED_ASSET_EXTENSIONS = {".svg", ".jpg", ".jpeg", ".png"}
FAILURE_PAGE_LOAD = "page_load_failed"
FAILURE_RIGHTS_MISSING = "rights_missing"
FAILURE_RIGHTS_NOT_ALLOWED = "rights_not_allowed"
FAILURE_ASSETS_MISSING = "assets_missing"
FAILURE_DOWNLOAD = "download_failed"
FAILURE_SEED_ALREADY_RUNNABLE = "seed_already_runnable"
FAILURE_CHALLENGE_NOT_RESOLVED = "challenge_not_resolved"
CHALLENGE_MARKERS = (
    "just a moment",
    "verify you are human",
    "checking your browser",
    "cloudflare",
    "attention required",
    "cdn-cgi/challenge-platform",
)
NLI_PROMOTION_IMAGE_WIDTH = 1280
NLI_PROMOTION_MAX_ASSETS = 5
CP1252_REVERSE_MAP = {
    "€": 0x80,
    "‚": 0x82,
    "ƒ": 0x83,
    "„": 0x84,
    "…": 0x85,
    "†": 0x86,
    "‡": 0x87,
    "ˆ": 0x88,
    "‰": 0x89,
    "Š": 0x8A,
    "‹": 0x8B,
    "Œ": 0x8C,
    "Ž": 0x8E,
    "‘": 0x91,
    "’": 0x92,
    "“": 0x93,
    "”": 0x94,
    "•": 0x95,
    "–": 0x96,
    "—": 0x97,
    "˜": 0x98,
    "™": 0x99,
    "š": 0x9A,
    "›": 0x9B,
    "œ": 0x9C,
    "ž": 0x9E,
    "Ÿ": 0x9F,
}


@dataclass(frozen=True)
class ExtractedSeedPage:
    title: str
    description: str
    rights: str
    asset_urls: list[str]


@dataclass(frozen=True)
class AssetDownload:
    file_name: str
    relative_path: str
    source_url: str
    content_type: str | None
    data: bytes


@dataclass(frozen=True)
class PromotionSuccess:
    seed_id: str
    title: str
    rights: str
    fixture_file_name: str
    fixture_html: str
    fixture_reference: str
    asset_downloads: list[AssetDownload]
    promoted_seed_entry: dict[str, Any]


@dataclass(frozen=True)
class PromotionFailure:
    seed_id: str
    reason: str
    message: str
    rights: str | None = None


def seed_id_to_slug(seed_id: str) -> str:
    return seed_id.replace("-", "_")


def infer_asset_extension(asset_url: str, content_type: str | None = None) -> str:
    suffix = Path(urlparse(asset_url).path).suffix.lower()
    if suffix in ALLOWED_ASSET_EXTENSIONS:
        return suffix
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip().lower())
    if guessed in ALLOWED_ASSET_EXTENSIONS:
        return guessed
    if guessed == ".jpe":
        return ".jpg"
    raise StageExecutionError(
        f"Could not infer supported asset extension for {asset_url}"
        + (f" (content type: {content_type})" if content_type else "")
    )


def _asset_signature(data: bytes) -> str | None:
    if data.startswith(b"\xff\xd8"):
        return "jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "tiff"
    if b"<svg" in data[:512].lower():
        return "svg"
    return None


def _repair_utf8_mojibake(data: bytes) -> bytes | None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    repaired = bytearray()
    for char in text:
        codepoint = ord(char)
        if codepoint <= 0xFF:
            repaired.append(codepoint)
            continue
        if char in CP1252_REVERSE_MAP:
            repaired.append(CP1252_REVERSE_MAP[char])
            continue
        return None
    return bytes(repaired)


def _normalize_downloaded_bytes(body: bytes) -> bytes:
    repaired = _repair_utf8_mojibake(body)
    if repaired is None:
        return body
    if _asset_signature(body) is None and _asset_signature(repaired) is not None:
        return repaired
    return body


def render_fixture_html(
    *,
    title: str,
    description: str,
    rights: str,
    asset_relative_paths: list[str],
) -> str:
    escaped_title = _escape_html(title)
    escaped_description = _escape_html(description)
    escaped_rights = _escape_html(rights)
    image_lines = "\n".join(
        f'        <img class="page-image" src="{_escape_html(path)}" alt="page {index}" />'
        for index, path in enumerate(asset_relative_paths, start=1)
    )
    return (
        "<!doctype html>\n"
        '<html lang="he">\n'
        "  <head>\n"
        '    <meta charset="utf-8" />\n'
        f'    <meta property="og:title" content="{escaped_title}" />\n'
        f'    <meta name="description" content="{escaped_description}" />\n'
        "  </head>\n"
        "  <body>\n"
        "    <article>\n"
        f"      <h1 class=\"item-title\">{escaped_title}</h1>\n"
        f"      <div class=\"item-description\">{escaped_description}</div>\n"
        f"      <span class=\"rights-label\">{escaped_rights}</span>\n"
        "      <section class=\"image-list\">\n"
        f"{image_lines}\n"
        "      </section>\n"
        "    </article>\n"
        "  </body>\n"
        "</html>\n"
    )


def build_fixture_reference(*, fixture_file_name: str, output_dir: Path, runnable_seeds_path: Path) -> str:
    package_data_dir = Path(__file__).resolve().parents[1] / "data" / "nli"
    if output_dir.resolve() == package_data_dir.resolve():
        return f"package://data/nli/{fixture_file_name}"
    fixture_path = output_dir / fixture_file_name
    return Path(os.path.relpath(fixture_path, runnable_seeds_path.parent)).as_posix()


def build_promotion(
    *,
    seed: dict[str, Any],
    extracted: ExtractedSeedPage,
    downloaded_assets: list[tuple[str, str | None, bytes]],
    require_rights: str,
    output_dir: Path | None = None,
    runnable_seeds_path: Path | None = None,
) -> PromotionSuccess:
    if not extracted.rights:
        raise StageExecutionError(FAILURE_RIGHTS_MISSING)
    if extracted.rights != require_rights:
        raise StageExecutionError(f"{FAILURE_RIGHTS_NOT_ALLOWED}:{extracted.rights}")
    if not extracted.asset_urls:
        raise StageExecutionError(FAILURE_ASSETS_MISSING)
    if len(extracted.asset_urls) != len(downloaded_assets):
        raise StageExecutionError(
            f"{FAILURE_DOWNLOAD}: expected {len(extracted.asset_urls)} assets, got {len(downloaded_assets)}"
        )

    slug = seed_id_to_slug(str(seed["id"]))
    fixture_file_name = f"item_{slug}.html"
    asset_download_records: list[AssetDownload] = []
    asset_relative_paths: list[str] = []
    for index, (asset_url, content_type, data) in enumerate(downloaded_assets, start=1):
        extension = infer_asset_extension(asset_url, content_type)
        file_name = f"{slug}_page{index}{extension}"
        relative_path = f"assets/{file_name}"
        asset_relative_paths.append(relative_path)
        asset_download_records.append(
            AssetDownload(
                file_name=file_name,
                relative_path=relative_path,
                source_url=asset_url,
                content_type=content_type,
                data=data,
            )
        )
    fixture_html = render_fixture_html(
        title=extracted.title,
        description=extracted.description,
        rights=extracted.rights,
        asset_relative_paths=asset_relative_paths,
    )
    fixture_reference = (
        build_fixture_reference(
            fixture_file_name=fixture_file_name,
            output_dir=output_dir,
            runnable_seeds_path=runnable_seeds_path,
        )
        if output_dir is not None and runnable_seeds_path is not None
        else f"package://data/nli/{fixture_file_name}"
    )
    promoted_seed_entry = {
        "id": seed["id"],
        "url": seed["url"],
        "title": extracted.title,
        "fixture_html": fixture_reference,
    }
    if seed.get("notes"):
        promoted_seed_entry["notes"] = seed["notes"]
    return PromotionSuccess(
        seed_id=str(seed["id"]),
        title=extracted.title,
        rights=extracted.rights,
        fixture_file_name=fixture_file_name,
        fixture_html=fixture_html,
        fixture_reference=fixture_reference,
        asset_downloads=asset_download_records,
        promoted_seed_entry=promoted_seed_entry,
    )


def load_yaml_manifest(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    items = data.get("items")
    if not isinstance(items, list):
        raise StageExecutionError(f"Manifest at {path} must contain an items list.")
    return data


def write_yaml_manifest(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_promotions(
    *,
    runnable_manifest: dict[str, Any],
    catalog_manifest: dict[str, Any],
    promotions: list[PromotionSuccess],
    overwrite: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], list[PromotionFailure]]:
    runnable_items = list(runnable_manifest["items"])
    catalog_items = list(catalog_manifest["items"])
    failures: list[PromotionFailure] = []
    for promotion in promotions:
        existing_index = next((i for i, item in enumerate(runnable_items) if item["id"] == promotion.seed_id), None)
        if existing_index is not None and not overwrite:
            failures.append(
                PromotionFailure(
                    seed_id=promotion.seed_id,
                    reason=FAILURE_SEED_ALREADY_RUNNABLE,
                    message=f"Seed {promotion.seed_id} already exists in runnable seeds.",
                    rights=promotion.rights,
                )
            )
            continue
        if existing_index is not None:
            runnable_items[existing_index] = promotion.promoted_seed_entry
        else:
            runnable_items.append(promotion.promoted_seed_entry)
        catalog_items = [item for item in catalog_items if item["id"] != promotion.seed_id]
    return {"items": runnable_items}, {"items": catalog_items}, failures


def select_catalog_items(
    *,
    catalog_manifest: dict[str, Any],
    seed_ids: list[str] | None,
    max_items: int | None,
) -> list[dict[str, Any]]:
    selected = list(catalog_manifest["items"])
    if seed_ids:
        wanted = set(seed_ids)
        selected = [item for item in selected if item["id"] in wanted]
    if max_items is not None:
        selected = selected[:max_items]
    return selected


def build_report(
    *,
    attempted_seed_ids: list[str],
    promotions: list[PromotionSuccess],
    failures: list[PromotionFailure],
) -> dict[str, Any]:
    return {
        "attempted_seeds": attempted_seed_ids,
        "promoted_seeds": [
            {
                "seed_id": promotion.seed_id,
                "fixture_path": promotion.fixture_reference,
                "asset_paths": [download.relative_path for download in promotion.asset_downloads],
                "rights": promotion.rights,
            }
            for promotion in promotions
        ],
        "failed_seeds": [
            {
                "seed_id": failure.seed_id,
                "reason": failure.reason,
                "message": failure.message,
                "rights": failure.rights,
            }
            for failure in failures
        ],
    }


def write_promotion_outputs(
    *,
    promotions: list[PromotionSuccess],
    output_dir: Path,
    runnable_seeds_path: Path,
    seed_catalog_path: Path,
    runnable_manifest: dict[str, Any],
    catalog_manifest: dict[str, Any],
    report_path: Path,
    report: dict[str, Any],
    overwrite: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    for promotion in promotions:
        fixture_path = output_dir / promotion.fixture_file_name
        if overwrite or not fixture_path.exists():
            fixture_path.write_text(promotion.fixture_html, encoding="utf-8")
        for asset in promotion.asset_downloads:
            asset_path = assets_dir / asset.file_name
            if overwrite or not asset_path.exists():
                asset_path.parent.mkdir(parents=True, exist_ok=True)
                asset_path.write_bytes(asset.data)
    write_yaml_manifest(runnable_seeds_path, runnable_manifest)
    write_yaml_manifest(seed_catalog_path, catalog_manifest)
    write_json(report_path, report)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote exploratory NLI seeds to runnable fixture-backed seeds.")
    parser.add_argument("--seed-catalog", type=Path, default=Path("src/hocrgen/data/nli/seed_catalog.yaml"))
    parser.add_argument("--runnable-seeds", type=Path, default=Path("src/hocrgen/data/nli/seeds.yaml"))
    parser.add_argument("--output-dir", type=Path, default=Path("src/hocrgen/data/nli"))
    parser.add_argument("--browser-state-dir", type=Path, default=Path(".cache/nli-playwright"))
    parser.add_argument("--connect-cdp", help="Connect to an already running Chrome instance via CDP, e.g. http://127.0.0.1:9222")
    parser.add_argument("--seed-id", action="append", dest="seed_ids")
    parser.add_argument("--max-items", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--report-path", type=Path, default=Path("src/hocrgen/data/nli/promotion_report.json"))
    parser.add_argument("--pause-on-first-page", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--pause-on-every-challenge", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--manual-wait-timeout", type=int, default=60)
    parser.add_argument("--require-rights", default=DEFAULT_REQUIRED_RIGHTS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    runnable_manifest = load_yaml_manifest(args.runnable_seeds)
    catalog_manifest = load_yaml_manifest(args.seed_catalog)
    selected_seeds = select_catalog_items(
        catalog_manifest=catalog_manifest,
        seed_ids=args.seed_ids,
        max_items=args.max_items,
    )
    promotions: list[PromotionSuccess] = []
    failures: list[PromotionFailure] = []
    for index, seed in enumerate(selected_seeds):
        try:
            extracted, downloads = capture_seed_via_browser(
                seed=seed,
                browser_state_dir=args.browser_state_dir,
                connect_cdp=args.connect_cdp,
                pause_on_first_page=args.pause_on_first_page and index == 0,
                pause_on_every_challenge=args.pause_on_every_challenge,
                manual_wait_timeout_seconds=args.manual_wait_timeout,
            )
            promotions.append(
                build_promotion(
                    seed=seed,
                    extracted=extracted,
                    downloaded_assets=downloads,
                    require_rights=args.require_rights,
                    output_dir=args.output_dir,
                    runnable_seeds_path=args.runnable_seeds,
                )
            )
        except StageExecutionError as exc:
            failures.append(
                PromotionFailure(
                    seed_id=str(seed["id"]),
                    reason=_extract_failure_reason(str(exc)),
                    message=str(exc),
                    rights=_extract_rights_hint(str(exc)),
                )
            )
    updated_runnable, updated_catalog, manifest_failures = apply_promotions(
        runnable_manifest=runnable_manifest,
        catalog_manifest=catalog_manifest,
        promotions=promotions,
        overwrite=args.overwrite,
    )
    all_failures = [*failures, *manifest_failures]
    successful_promotions = [promotion for promotion in promotions if promotion.seed_id not in {f.seed_id for f in manifest_failures}]
    report = build_report(
        attempted_seed_ids=[str(seed["id"]) for seed in selected_seeds],
        promotions=successful_promotions,
        failures=all_failures,
    )
    if not args.dry_run:
        write_promotion_outputs(
            promotions=successful_promotions,
            output_dir=args.output_dir,
            runnable_seeds_path=args.runnable_seeds,
            seed_catalog_path=args.seed_catalog,
            runnable_manifest=updated_runnable,
            catalog_manifest=updated_catalog,
            report_path=args.report_path,
            report=report,
            overwrite=args.overwrite,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not all_failures else 1


def capture_seed_via_browser(
    *,
    seed: dict[str, Any],
    browser_state_dir: Path,
    connect_cdp: str | None,
    pause_on_first_page: bool,
    pause_on_every_challenge: bool,
    manual_wait_timeout_seconds: int,
) -> tuple[ExtractedSeedPage, list[tuple[str, str | None, bytes]]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise StageExecutionError(
            "playwright is required for seed promotion. Install it locally, for example with: "
            "uv pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as playwright:
        browser, context = _open_browser_session(
            playwright=playwright,
            browser_state_dir=browser_state_dir,
            connect_cdp=connect_cdp,
        )
        try:
            page = _get_seed_page(context=context, seed_url=str(seed["url"]))
            if not _page_matches_seed_url(page.url, str(seed["url"])):
                page.goto(str(seed["url"]), wait_until="domcontentloaded")
                page.wait_for_timeout(1500)
            print(f"[nli-promote] {seed['id']} initial URL: {page.url}", file=sys.stderr)
            if _wait_for_item_page_ready(page, timeout_seconds=3):
                print(f"[nli-promote] {seed['id']} item markers detected without manual intervention.", file=sys.stderr)
            else:
                challenge_detected = looks_like_challenge_page(url=page.url, html=page.content())
                if pause_on_first_page or challenge_detected or pause_on_every_challenge:
                    prompt = (
                        f"Opened {seed['id']} in the connected browser session.\n"
                        "If you see a challenge, solve it now. When the item page looks fully loaded, press Enter to continue.\n"
                        f"Current URL: {page.url}"
                    )
                    print(prompt, file=sys.stderr)
                    input()
                    print(f"[nli-promote] {seed['id']} URL after manual confirmation: {page.url}", file=sys.stderr)
                    if not _wait_for_item_page_ready(page, timeout_seconds=manual_wait_timeout_seconds):
                        print(
                            f"[nli-promote] {seed['id']} still not ready after manual confirmation; trying one reload.",
                            file=sys.stderr,
                        )
                        page.reload(wait_until="domcontentloaded")
                        page.wait_for_timeout(1000)
                        print(f"[nli-promote] {seed['id']} URL after reload: {page.url}", file=sys.stderr)
                        if not _wait_for_item_page_ready(page, timeout_seconds=manual_wait_timeout_seconds):
                            screenshot = _save_failure_screenshot(page, seed["id"], browser_state_dir)
                            raise StageExecutionError(
                                f"{FAILURE_CHALLENGE_NOT_RESOLVED}: {seed['id']}: item page markers not found after manual challenge resolution; screenshot={screenshot}"
                            )
                else:
                    if not _wait_for_item_page_ready(page, timeout_seconds=manual_wait_timeout_seconds):
                        screenshot = _save_failure_screenshot(page, seed["id"], browser_state_dir)
                        raise StageExecutionError(
                            f"{FAILURE_PAGE_LOAD}: {seed['id']}: item page markers not found within {manual_wait_timeout_seconds}s; screenshot={screenshot}"
                        )
            extracted = extract_page_data(page)
            downloads = download_assets(
                playwright,
                context.storage_state(),
                extracted.asset_urls,
                browser_context=context,
            )
            return extracted, downloads
        except Exception as exc:  # pragma: no cover - browser path is intentionally local/manual
            raise StageExecutionError(f"{FAILURE_PAGE_LOAD}: {seed['id']}: {exc}") from exc
        finally:
            if not connect_cdp:
                context.close()


def extract_page_data(page) -> ExtractedSeedPage:  # pragma: no cover - exercised through local browser only
    manifest = _fetch_nli_viewer_manifest(page)
    title = _first_non_empty(
        page.locator("meta[property='og:title']").first.get_attribute("content"),
        _text_or_none(page.locator(".item-title").first),
        _text_or_none(page.locator("h1.pageTitle--title").first),
        _manifest_value(manifest, "label"),
        _manifest_metadata_value(manifest, "Title"),
        page.title(),
    )
    description = _first_non_empty(
        page.locator("meta[name='description']").first.get_attribute("content"),
        _text_or_none(page.locator(".item-description").first),
        _manifest_value(manifest, "description"),
        "",
    )
    rights = _first_non_empty(
        _text_or_none(page.locator(".rights-label").first),
        _normalize_nli_rights(_manifest_first(manifest, "license")),
        _normalize_nli_rights(_text_or_none(page.locator("#accessRights-collapse").first)),
        _fallback_find_rights(page.content()),
    )
    asset_urls = [
        urljoin(page.url, value)
        for value in page.locator("img.page-image").evaluate_all("els => els.map(el => el.getAttribute('src'))")
        if value
    ]
    if not asset_urls:
        asset_urls = _manifest_asset_urls(manifest)
    if not asset_urls:
        asset_urls = _iframe_asset_urls(page)
    if not asset_urls:
        asset_urls = _delivery_manager_asset_urls(page)
    return ExtractedSeedPage(
        title=title or "Untitled NLI item",
        description=description or "",
        rights=rights or "",
        asset_urls=asset_urls,
    )


def download_assets(
    playwright,
    storage_state: dict[str, Any],
    asset_urls: list[str],
    *,
    browser_context=None,
) -> list[tuple[str, str | None, bytes]]:  # pragma: no cover
    request_context = playwright.request.new_context(storage_state=storage_state)
    try:
        downloads: list[tuple[str, str | None, bytes]] = []
        for asset_url in asset_urls:
            response = request_context.get(asset_url)
            if not response.ok:
                raise StageExecutionError(f"{FAILURE_DOWNLOAD}: {asset_url}: HTTP {response.status}")
            content_type, body = _normalize_downloaded_asset(
                content_type=response.headers.get("content-type"),
                body=_normalize_downloaded_bytes(response.body()),
            )
            downloads.append(
                (
                    asset_url,
                    content_type,
                    body,
                )
            )
        return downloads
    finally:
        request_context.dispose()


def _extract_failure_reason(message: str) -> str:
    if ":" in message:
        prefix = message.split(":", 1)[0]
        if prefix in {
            FAILURE_PAGE_LOAD,
            FAILURE_CHALLENGE_NOT_RESOLVED,
            FAILURE_RIGHTS_MISSING,
            FAILURE_RIGHTS_NOT_ALLOWED,
            FAILURE_ASSETS_MISSING,
            FAILURE_DOWNLOAD,
            FAILURE_SEED_ALREADY_RUNNABLE,
        }:
            return prefix
    if message in {
        FAILURE_RIGHTS_MISSING,
        FAILURE_ASSETS_MISSING,
    }:
        return message
    return FAILURE_PAGE_LOAD


def _extract_rights_hint(message: str) -> str | None:
    if not message.startswith(f"{FAILURE_RIGHTS_NOT_ALLOWED}:"):
        return None
    return message.split(":", 1)[1].strip() or None


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _text_or_none(locator) -> str | None:  # pragma: no cover - browser path only
    try:
        if locator.count() == 0:
            return None
        return locator.text_content()
    except Exception:
        return None


def _fallback_find_rights(page_html: str) -> str | None:
    match = re.search(r"Any Use Permitted|No Known Copyright Restrictions|Copyright", page_html, re.IGNORECASE)
    if not match:
        return None
    return match.group(0)


def looks_like_challenge_page(*, url: str, html: str) -> bool:
    lowered = f"{url}\n{html}".lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


def _open_browser_session(*, playwright, browser_state_dir: Path, connect_cdp: str | None):  # pragma: no cover - browser path only
    if connect_cdp:
        browser = playwright.chromium.connect_over_cdp(connect_cdp)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        return browser, context
    browser_state_dir.mkdir(parents=True, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        str(browser_state_dir),
        headless=False,
    )
    return None, context


def _get_seed_page(*, context, seed_url: str):  # pragma: no cover - browser path only
    for page in context.pages:
        if _page_matches_seed_url(page.url, seed_url):
            page.bring_to_front()
            return page
    page = context.new_page()
    return page


def _page_matches_seed_url(current_url: str, seed_url: str) -> bool:
    if not current_url:
        return False
    current = current_url.rstrip("/")
    seed = seed_url.rstrip("/")
    return current == seed or current.startswith(seed + "?")


def _wait_for_item_page_ready(page, *, timeout_seconds: int) -> bool:  # pragma: no cover - browser path only
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if _page_has_item_markers(page):
            return True
        page.wait_for_timeout(1000)
    return False


def _page_has_item_markers(page) -> bool:  # pragma: no cover - browser path only
    try:
        has_item_title = page.locator(".item-title").count() > 0
        has_page_title = page.locator("h1.pageTitle--title").count() > 0
        has_rights = page.locator(".rights-label").count() > 0
        has_assets = page.locator("img.page-image").count() > 0 or page.locator("img[src*='DeliveryManagerServlet']").count() > 0
        has_meta_title = bool(page.locator("meta[property='og:title']").first.get_attribute("content"))
        has_viewer = page.locator("#viewer[data-info]").count() > 0 or page.locator("#MainIframe").count() > 0
        return (has_assets or has_viewer) and (has_item_title or has_page_title or has_meta_title or has_rights)
    except Exception:
        return False


def _save_failure_screenshot(page, seed_id: str, browser_state_dir: Path) -> Path:  # pragma: no cover - browser path only
    failures_dir = browser_state_dir / "failures"
    failures_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = failures_dir / f"{seed_id_to_slug(seed_id)}_failure.png"
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception:
        screenshot_path.write_text("Screenshot capture failed.\n", encoding="utf-8")
    return screenshot_path


def _fetch_nli_viewer_manifest(page) -> dict[str, Any] | None:
    viewer_data = page.evaluate(
        """() => {
          const viewer = document.getElementById('viewer');
          if (!viewer) return null;
          return {
            docId: viewer.getAttribute('data-info'),
            mmsId: viewer.getAttribute('data-info-mmsid'),
          };
        }"""
    )
    if not viewer_data or not viewer_data.get("docId") or not viewer_data.get("mmsId"):
        return None
    response = page.evaluate(
        """async ({docId, mmsId}) => {
          const params = new URLSearchParams({
            docID: docId,
            MmsId: mmsId,
            isMmsId: 'true',
          });
          const resp = await fetch(`/umbraco/api/ViewerApi/GetManifestByDocID?${params.toString()}`, {
            credentials: 'include',
          });
          const text = await resp.text();
          return {status: resp.status, ok: resp.ok, text};
        }""",
        viewer_data,
    )
    if not response.get("ok"):
        return None
    payload = json.loads(response["text"])
    value = payload.get("Value")
    if not value:
        return None
    return json.loads(value)


def _manifest_value(manifest: dict[str, Any] | None, key: str) -> str | None:
    if not manifest:
        return None
    value = manifest.get(key)
    if isinstance(value, str):
        return value
    return None


def _manifest_first(manifest: dict[str, Any] | None, key: str) -> str | None:
    if not manifest:
        return None
    value = manifest.get(key)
    if isinstance(value, list) and value:
        first = value[0]
        return first if isinstance(first, str) else None
    return None


def _manifest_metadata_value(manifest: dict[str, Any] | None, label: str) -> str | None:
    if not manifest:
        return None
    for item in manifest.get("metadata", []):
        if item.get("label") == label:
            value = item.get("value")
            if isinstance(value, str):
                return value
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str):
                    return first
    return None


def _normalize_nli_rights(rights: str | None) -> str | None:
    if not rights:
        return None
    normalized = rights.strip()
    lowered = normalized.lower()
    if normalized == DEFAULT_REQUIRED_RIGHTS:
        return normalized
    if "ללא מגבלות" in normalized or "public domain" in lowered or "no known copyright restrictions" in lowered:
        return DEFAULT_REQUIRED_RIGHTS
    return normalized


def _manifest_asset_urls(manifest: dict[str, Any] | None) -> list[str]:
    if not manifest:
        return []
    asset_urls: list[str] = []
    for sequence in manifest.get("sequences", []):
        for canvas in sequence.get("canvases", []):
            for image in canvas.get("images", []):
                resource = image.get("resource") or {}
                service = resource.get("service") or {}
                service_id = service.get("@id")
                resource_id = resource.get("@id")
                if isinstance(service_id, str):
                    asset_urls.append(f"{service_id}/full/{NLI_PROMOTION_IMAGE_WIDTH},/0/default.jpg")
                elif isinstance(resource_id, str):
                    asset_urls.append(resource_id)
                if len(asset_urls) >= NLI_PROMOTION_MAX_ASSETS:
                    return asset_urls
    return asset_urls


def _iframe_asset_urls(page) -> list[str]:
    asset_urls: list[str] = []
    for frame in getattr(page, "frames", []):
        try:
            frame_asset_urls = frame.evaluate(
                """() => {
                  const results = [];
                  const collect = (value) => {
                    if (typeof value === 'string' && value.includes('DeliveryManagerServlet')) {
                      results.push(value);
                    }
                  };
                  for (const img of document.querySelectorAll('img')) {
                    collect(img.getAttribute('src'));
                    collect(img.getAttribute('data-src'));
                  }
                  const text = document.documentElement ? document.documentElement.innerHTML : '';
                  const matches = text.match(/https?:\\\\/\\\\/[^"'\\\\s]+DeliveryManagerServlet[^"'\\\\s<]+/g) || [];
                  for (const match of matches) {
                    results.push(match);
                  }
                  return [...new Set(results)];
                }"""
            )
        except Exception:
            continue
        for value in frame_asset_urls or []:
            if isinstance(value, str):
                asset_urls.append(urljoin(frame.url or page.url, value))
        if asset_urls:
            break
    return asset_urls[:NLI_PROMOTION_MAX_ASSETS]


def _delivery_manager_asset_urls(page) -> list[str]:
    urls = [
        urljoin(page.url, value)
        for value in page.locator("img[src*='DeliveryManagerServlet']").evaluate_all("els => els.map(el => el.getAttribute('src'))")
        if value
    ]
    normalized_urls: list[str] = []
    for value in urls:
        if "dps_func=thumbnail" in value:
            normalized_urls.append(value.replace("dps_func=thumbnail", "dps_func=stream"))
        else:
            normalized_urls.append(value)
    return normalized_urls[:NLI_PROMOTION_MAX_ASSETS]


def _normalize_downloaded_asset(*, content_type: str | None, body: bytes) -> tuple[str | None, bytes]:
    if _asset_signature(body) != "tiff":
        return content_type, body
    image = Image.open(BytesIO(body))
    if image.mode not in {"RGB", "L"}:
        image = image.convert("RGB")
    elif image.mode == "L":
        image = image.convert("RGB")
    output = BytesIO()
    image.save(output, format="JPEG", quality=92)
    return "image/jpeg", output.getvalue()
