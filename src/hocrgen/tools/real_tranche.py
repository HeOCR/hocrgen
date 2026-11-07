"""Operator-only F8g tranche packaging: capture, materialize and manifest the promoted real tranche.

The promoted pool (Wikisource proofread pages, YidTakNL pages matched to NLI canvases, the BGU Pinkas pages) is far
too large for git. This tool builds it reproducibly outside the repository:

``capture``
    Fetch the upstream files that no operator cache holds yet, each pinned by the checksum the repo already records:
    YidTakNL matched pages from the dataset's public SURFdrive share (SHA-1 and byte count from
    ``matched_pages.jsonl``), and the BGU Pinkas zip from Zenodo (its MD5) with the NLI manifest (its pinned
    sha256). Network; courtesy delay between requests; never run in CI.
``materialize``
    Offline. Write ``<out>/sources/<source_id>/snapshot/`` in each fetcher's packaged snapshot format, plus
    ``tranche.json`` and ``SHA256SUMS``, from the caches. Wikisource pages are rebuilt by replaying the F8b6
    inventory's API cache (no request may miss it), with the committed agent and tool checks and the 960 px
    Commons renders. Every page and entry is checked by the unchanged fetcher gates before it is written.
``manifest``
    Write the committed manifest (``src/hocrgen/data/real_tranche/``): ids, checksums, sizes and provenance per
    item, and the checksums of each snapshot's descriptor files. No page text.
``verify``
    Check every file of a materialized tree against its ``SHA256SUMS``.
``refresh-reshumot`` / ``refresh-wikisource``
    A new tree from an earlier one with one source refreshed (F8e2, E2d3e); every other source is copied byte for byte.

Nothing here publishes or uploads anything; hosting the tree is the maintainer's decision.
"""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import hashlib
import io
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Callable

import yaml
from PIL import Image

from hocrgen.config.loader import load_and_validate_bundle, load_yaml_file, package_root
from hocrgen.fetchers.pinkas_dataset import pinkas_dataset_entry_exclusion_reason
from hocrgen.fetchers.wikisource import (
    CROP_RESOLVED,
    crop_asset_problems,
    crop_image,
    crop_mask_fill,
    crop_pixel_box,
    crop_region_boxes,
    load_wikisource_snapshot,
    page_exclusion_reasons,
    page_needs_crop,
)
from hocrgen.fetchers.government_print import knesset_entry_exclusion_reasons, reshumot_entry_exclusion_reasons
from hocrgen.fetchers.yidtaknl import yidtaknl_entry_exclusion_reason
from hocrgen.tools import government_print_tranche
from hocrgen.real_tranche import (
    TRANCHE_CHECKSUMS,
    TRANCHE_DESCRIPTOR,
    TRANCHE_MANIFEST_SCHEMA,
    TRANCHE_SCHEMA,
    sha256_path,
    verify_tranche_files,
)

TRANCHE_ID = "e2d3e_real_tranche_v5"
TRANCHE_NOTATION = "E2d3e"
CAPTURE_SEED = "f8g2-tranche-v2"
USER_AGENT = "hocrgen-real-tranche/0.1 (https://github.com/HeOCR/hocrgen; operator capture)"
SURFDRIVE_WEBDAV = "https://surfdrive.surf.nl/public.php/webdav/"
YIDTAKNL_SHARE_TOKEN = "mov7H4wDaog4zkF"
PINKAS_ZIP_URL = "https://zenodo.org/api/records/3569694/files/pinkas_dataset.zip/content"
PINKAS_ZIP_MD5 = "802f14fbdb400efab9cb0808c3620be8"
PINKAS_MANIFEST_URL = "https://iiif.nli.org.il/IIIFv21/990000445290205171/manifest"
PINKAS_RECORD = "nli_990000445290205171"
PINKAS_MEMBER_PREFIX = "pinkas_dataset/pinkas_dataset_images_and_xmls/"
PINKAS_PAGE_NAME = re.compile(r"^Page (\d+)_([12])\.(jpg|xml)$")
DEFAULT_PAGE_CHECKS = ("docs/wikisource_page_checks.json", "docs/wikisource_page_tool_checks.json")
DEFAULT_PINKAS_CHECKS = "docs/pinkas_canvas_match_checks.json"
PINKAS_LABEL_RULE = (
    "label rule from F8d2: dataset 'Page N_1' is the right half and 'Page N_2' the left half of the NLI canvas labelled 'Page N'"
)

SOURCE_WIKISOURCE = "wikisource_he_proofread"
SOURCE_YIDTAKNL = "yidtaknl_vaybertaytsh_gt"
SOURCE_PINKAS = "pinkas_dataset_bgu"
SOURCE_RESHUMOT = "reshumot_born_digital"
SOURCE_KNESSET = "knesset_committee_protocols_pre1976"


def _data(relative: str) -> Path:
    return package_root() / "data" / relative


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _json_lines(rows: list[dict[str, Any]]) -> bytes:
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode("utf-8")


def _image_size(content: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(content)) as image:
        return image.size


# --- capture (network) -------------------------------------------------------------------------------------------


def _get(url: str, headers: dict[str, str] | None = None) -> bytes:  # pragma: no cover - network
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code in {429, 500, 502, 503, 504, 520} and attempt < 4:
                time.sleep(5 * 2**attempt)
                continue
            raise
    raise RuntimeError(f"giving up on {url}")


def yidtaknl_capture_plan() -> list[dict[str, Any]]:
    """Every matched YidTakNL page with text: the share paths and the pinned SHA-1 and byte counts."""

    snapshot = load_yaml_file(_data("yidtaknl/snapshot/snapshot.yaml"))
    folders = {work["work_id"]: work["upstream_folder"] for work in snapshot["works"]}
    plan = []
    for line in _data("yidtaknl/snapshot/matched_pages.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        folder = folders[row["work_id"]]
        plan.append(
            {
                **row,
                "image_share_path": f"{folder}/{row['upstream_image_name']}",
                "text_share_path": f"{folder}/txt/{row['upstream_text_name']}",
            }
        )
    return plan


def capture_yidtaknl(cache: Path, *, delay: float, fetch: Callable[[str, dict[str, str]], bytes] = _get) -> dict[str, int]:
    """Fetch matched pages with non-empty text into ``cache/yidtaknl/<work_id>/``, verified by SHA-1 and bytes."""

    auth = {"Authorization": "Basic " + base64.b64encode(f"{YIDTAKNL_SHARE_TOKEN}:".encode()).decode()}
    counts = {"fetched": 0, "cached": 0, "skipped_empty_text": 0}
    for row in yidtaknl_capture_plan():
        if not row["text_bytes"]:
            counts["skipped_empty_text"] += 1
            continue
        for kind, share_path, sha1, size in (
            ("image", row["image_share_path"], row["image_sha1"], row["image_bytes"]),
            ("text", row["text_share_path"], row["text_sha1"], row["text_bytes"]),
        ):
            target = cache / "yidtaknl" / row["work_id"] / Path(share_path).name
            if target.is_file() and hashlib.sha1(target.read_bytes()).hexdigest() == sha1:
                counts["cached"] += 1
                continue
            content = fetch(SURFDRIVE_WEBDAV + urllib.parse.quote(share_path), auth)
            if hashlib.sha1(content).hexdigest() != sha1 or len(content) != size:
                raise RuntimeError(f"YidTakNL {kind} {share_path} does not match its pinned SHA-1 / size")
            _write(target, content)
            counts["fetched"] += 1
            time.sleep(delay)
    return counts


def capture_pinkas(
    cache: Path,
    *,
    fetch: Callable[[str, dict[str, str]], bytes] = _get,
    manifest_copy: Path | None = None,
) -> dict[str, int]:
    """Fetch the BGU Pinkas zip (pinned MD5) and the NLI manifest (pinned upstream sha256) into ``cache/pinkas/``.

    ``manifest_copy`` is an operator copy of the NLI manifest from an earlier capture (F8d2); it is used only when its
    sha256 equals the pinned capture's, so the result is the same bytes as a fresh fetch.
    """

    counts = {"fetched": 0, "cached": 0}
    zip_path = cache / "pinkas" / "pinkas_dataset.zip"
    if zip_path.is_file() and hashlib.md5(zip_path.read_bytes()).hexdigest() == PINKAS_ZIP_MD5:
        counts["cached"] += 1
    else:
        content = fetch(PINKAS_ZIP_URL, {})
        if hashlib.md5(content).hexdigest() != PINKAS_ZIP_MD5:
            raise RuntimeError("Pinkas zip does not match its Zenodo MD5")
        _write(zip_path, content)
        counts["fetched"] += 1
    manifest_path = cache / "pinkas" / "nli_manifest.json"
    expected = _pinkas_capture()["upstream_sha256"]
    if manifest_path.is_file() and sha256_path(manifest_path) == expected:
        counts["cached"] += 1
    elif manifest_copy is not None and manifest_copy.is_file() and sha256_path(manifest_copy) == expected:
        _write(manifest_path, manifest_copy.read_bytes())
        counts["cached"] += 1
    else:
        content = fetch(PINKAS_MANIFEST_URL, {})
        if _sha256(content) != expected:
            raise RuntimeError("NLI manifest for Ms. Heb. 4°662 changed since its pinned capture")
        _write(manifest_path, content)
        counts["fetched"] += 1
    return counts


def _pinkas_capture() -> dict[str, Any]:
    return json.loads(_data("pinkas_dataset_bgu/snapshot/iiif/nli_990000445290205171_manifest_capture.json").read_text(encoding="utf-8"))


# --- materialize: Wikisource ---------------------------------------------------------------------------------------


class CacheOnlyClient:
    """Replays a ``MediaWikiClient`` cache. Any request the cache does not hold fails: materializing is offline."""

    def __init__(self, cache_dir: Path) -> None:
        from hocrgen.tools.wikisource_inventory import MediaWikiClient

        self._client = MediaWikiClient.__new__(MediaWikiClient)
        self._client.cache_dir = cache_dir
        self._client.requests = 0
        self._client._request = self._refuse  # type: ignore[method-assign]

    @staticmethod
    def _refuse(api: str, body: dict[str, str]) -> dict[str, Any]:
        raise RuntimeError(f"request not in the operator cache (offline materialize): {api} {sorted(body.items())[:4]}")

    def __call__(self, api: str, params: dict[str, Any]) -> dict[str, Any]:
        return self._client(api, params)


def load_renders(render_dirs: list[Path]) -> dict[tuple[str, str], dict[str, Any]]:
    """Commons page renders by (slug, Commons file SHA-1), from each operator folder's ``renders.jsonl``."""

    renders: dict[tuple[str, str], dict[str, Any]] = {}
    for folder in render_dirs:
        index = folder / "renders.jsonl"
        if not index.is_file():
            continue
        for line in index.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            path = folder / f"{row['slug']}.jpg"
            if path.is_file():
                renders.setdefault((row["slug"], row["pinned_commons_sha1"]), {**row, "path": path})
    return renders


def _wikisource_image(page: dict[str, Any], index: dict[str, Any], render: dict[str, Any], root: Path) -> None:
    content = render["path"].read_bytes()
    if _sha256(content) != render["sha256"]:
        raise RuntimeError(f"render of {page['source_item_id']} does not match its recorded sha256")
    width, height = _image_size(content)
    relative = f"assets/{page['source_item_id']}.jpg"
    _write(root / relative, content)
    page["image"] = {
        "path": relative,
        "media_type": "image/jpeg",
        "sha256": _sha256(content),
        "bytes": len(content),
        "width": width,
        "height": height,
        "rendered_from": {
            "commons_file_sha1": index["commons_file"]["sha1"],
            "page": int(render.get("page") or page["page_number"]),
            "render_url": render["render_url"],
            "render_sha256": render["sha256"],
            "render_width": int(render.get("requested_width") or width),
        },
    }


def _wikisource_crop(page: dict[str, Any], root: Path) -> None:
    crop = page["crop"]
    with Image.open(root / page["image"]["path"]) as page_image:
        page_image.load()
        size = page_image.size
        crop["box_px"] = list(crop_pixel_box(crop["box_normalized"], *size))
        if crop.get("regions_normalized"):
            crop["regions_px"] = [list(region) for region in crop_region_boxes(crop, *size)]
            crop["mask_fill"] = crop_mask_fill(page_image, tuple(crop["box_px"]))
        cropped = crop_image(page_image, crop)
    buffer = io.BytesIO()
    cropped.save(buffer, format="PNG", optimize=False)
    content = buffer.getvalue()
    relative = f"assets/{page['source_item_id']}__crop.png"
    _write(root / relative, content)
    crop["asset"] = {
        "path": relative,
        "media_type": "image/png",
        "sha256": _sha256(content),
        "bytes": len(content),
        "width": cropped.size[0],
        "height": cropped.size[1],
    }


def materialize_wikisource(
    *,
    work_dir: Path,
    render_dirs: list[Path],
    page_check_paths: list[Path],
    out_root: Path,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Rebuild every eligible page of the operator inventory into a packaged-format snapshot (offline)."""

    from hocrgen.tools.wikisource_inventory import apply_page_check, apply_text_adjustments, capture_page_record, load_page_checks

    inventory = json.loads((work_dir / "wikisource_inventory.json").read_text(encoding="utf-8"))
    indexes = {record["index_key"]: record for record in inventory["indexes"]}
    checks = load_page_checks(page_check_paths)
    renders = load_renders(render_dirs)
    fetch = CacheOnlyClient(work_dir / "raw")
    root = out_root / "sources" / SOURCE_WIKISOURCE / "snapshot"
    pages: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for result in sorted(inventory["pages"], key=lambda row: (row["index_key"], row["page_title"])):
        if result["reasons"]:
            continue
        index = indexes[result["index_key"]]
        page = capture_page_record(fetch, result["page_title"], index, root)
        apply_page_check(page, index, checks.get(result["page_title"]))
        # F8b7: drop footnotes found not printed and map reviewed stand-ins, so the pair text is the inventory's.
        apply_text_adjustments(page, root)
        render = renders.get((page["source_item_id"], index["commons_file"]["sha1"]))
        if render is None:
            skipped["render_missing"] = skipped.get("render_missing", 0) + 1
            continue
        _wikisource_image(page, index, render, root)
        if page_needs_crop(page) and (page.get("crop") or {}).get("status") == CROP_RESOLVED:
            _wikisource_crop(page, root)
            problems = crop_asset_problems(page, root)
            if problems:
                raise RuntimeError(f"crop of {page['source_item_id']} failed its own check: {problems}")
        reasons = page_exclusion_reasons(page, indexes, root)
        if reasons:
            for reason in reasons:
                skipped[reason] = skipped.get(reason, 0) + 1
            continue
        pages.append(page)
    used = sorted({page["index_key"] for page in pages})
    index_records = [{key: value for key, value in indexes[key].items() if key not in {"gate", "pages"}} for key in used]
    _write(root / "indexes.json", (json.dumps({"indexes": index_records}, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
    _write(root / "pages.jsonl", _json_lines(pages))
    packaged = load_yaml_file(_data("wikisource/snapshot/snapshot.yaml"))
    snapshot = {
        **{key: packaged[key] for key in ("version", "site", "api_url", "commons_api_url", "text_licence", "text_normalization")},
        "captured_at": str(inventory["checked_at"]),
        "capture_user_agent": inventory.get("user_agent"),
        "indexes_path": "indexes.json",
        "pages_path": "pages.jsonl",
        "scope": "tranche",
        "notes": (
            f"F8g tranche ({TRANCHE_ID}). Every page of the operator inventory that passes the F8b-F8b7 gates, "
            "rebuilt offline from the inventory's API cache, with the committed agent and tool page checks and the F8b7 text "
            "adjustments applied. Page "
            "images are the 960 px Commons renders of the pinned files, unchanged; partial pages pair with their crop."
        ),
    }
    _write(root / "snapshot.yaml", yaml.safe_dump(snapshot, allow_unicode=True, sort_keys=False).encode())
    log(f"wikisource: {len(pages)} pages from {len(used)} Indexes; skipped {skipped}")
    return {"item_count": len(pages), "index_count": len(used), "skipped": skipped}


# --- materialize: YidTakNL -----------------------------------------------------------------------------------------


def materialize_yidtaknl(*, cache: Path, out_root: Path, log: Callable[[str], None] = print) -> dict[str, Any]:
    packaged_root = _data("yidtaknl/snapshot")
    root = out_root / "sources" / SOURCE_YIDTAKNL / "snapshot"
    snapshot = load_yaml_file(packaged_root / "snapshot.yaml")
    works = {work["work_id"]: work for work in snapshot["works"]}
    fixture_entries = [json.loads(line) for line in (packaged_root / "entries.jsonl").read_text(encoding="utf-8").splitlines()]
    templates = {entry["work_id"]: entry for entry in fixture_entries if entry["work_id"] in works}
    bundle = load_and_validate_bundle()
    source = next(item for item in bundle.source_registry.sources if item.id == SOURCE_YIDTAKNL)
    shutil.copytree(packaged_root / "iiif", root / "iiif", dirs_exist_ok=True)
    entries: list[dict[str, Any]] = []
    matched_works: set[str] = set()
    skipped: dict[str, int] = {}
    for row in yidtaknl_capture_plan():
        if not row["text_bytes"]:
            skipped["upstream_text_empty"] = skipped.get("upstream_text_empty", 0) + 1
            continue
        matched_works.add(row["work_id"])
        folder = cache / "yidtaknl" / row["work_id"]
        image = (folder / Path(row["image_share_path"]).name).read_bytes()
        text = (folder / Path(row["text_share_path"]).name).read_bytes()
        if hashlib.sha1(image).hexdigest() != row["image_sha1"] or hashlib.sha1(text).hexdigest() != row["text_sha1"]:
            raise RuntimeError(f"YidTakNL cache for {row['page_id']} does not match its pinned SHA-1")
        entry = copy.deepcopy(templates[row["work_id"]])
        width, height = _image_size(image)
        page_number = int(row["page_index"])
        entry["entry_id"] = row["page_id"]
        entry["title"] = re.sub(r"page \d+$", f"page {page_number}", entry["title"])
        asset_path = f"assets/{row['page_id']}.jpg"
        text_path = f"text/{row['page_id']}.txt"
        _write(root / asset_path, image)
        _write(root / text_path, text)
        entry["files"] = [
            {
                "bytes": len(image),
                "derived_from": "upstream image bytes, unchanged",
                "height_px": height,
                "local_path": asset_path,
                "mime_type": "image/jpeg",
                "role": "upstream",
                "sha256": _sha256(image),
                "width_px": width,
            }
        ]
        entry["text"].update(
            {
                "local_path": text_path,
                "sha256": _sha256(text),
                "line_count": len(text.decode("utf-8").splitlines()),
            }
        )
        entry["upstream"] = {
            "folder": works[row["work_id"]]["upstream_folder"],
            "image_bytes": len(image),
            "image_height_px": height,
            "image_path": row["image_share_path"],
            "image_sha1": row["image_sha1"],
            "image_sha256": _sha256(image),
            "image_width_px": width,
            "text_bytes": len(text),
            "text_path": row["text_share_path"],
            "text_sha1": row["text_sha1"],
            "text_sha256": _sha256(text),
        }
        entry["work"]["page_index"] = page_number
        entry["scan"]["iiif_canvas"] = row["iiif_canvas"]
        entry["scan"]["canvas_label"] = row["canvas_label"]
        entry["scan"]["match_method"] = f"{works[row['work_id']]['match_method']} (score {row['match_score']})"
        reason = yidtaknl_entry_exclusion_reason(entry, source, root)
        if reason is not None:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        entries.append(entry)
    # Vendored fixture entries of works without a matched-page list (the 1781 work's pages 7 and 8) stay as packaged.
    for entry in fixture_entries:
        if entry["work_id"] in works and entry["work_id"] not in matched_works:
            for file in entry["files"]:
                _write(root / file["local_path"], (packaged_root / file["local_path"]).read_bytes())
            _write(root / entry["text"]["local_path"], (packaged_root / entry["text"]["local_path"]).read_bytes())
            entries.append(entry)
    entries.sort(key=lambda entry: entry["entry_id"])
    _write(root / "entries.jsonl", _json_lines(entries))
    tranche_snapshot = {key: value for key, value in snapshot.items() if key != "matched_pages_path"}
    tranche_snapshot.update(
        {
            "scope": "tranche",
            "notes": (
                f"F8g tranche ({TRANCHE_ID}). Every page of the 1747 and JB 899 works matched to its NLI free-use canvas "
                "in F8d2 that has upstream text, captured from the SURFdrive share and verified against the share's "
                "SHA-1; the images are the upstream JPEGs, unchanged. The 1781 work's two vendored pages are kept as "
                "packaged. Pages whose upstream text file is empty are not pairs and are left out."
            ),
        }
    )
    _write(root / "snapshot.yaml", yaml.safe_dump(tranche_snapshot, allow_unicode=True, sort_keys=False).encode())
    log(f"yidtaknl: {len(entries)} entries; skipped {skipped}")
    return {"item_count": len(entries), "skipped": skipped}


# --- materialize: BGU Pinkas ---------------------------------------------------------------------------------------


def load_pinkas_checks(path: Path) -> dict[str, dict[str, Any]]:
    """Per-page canvas match checks (F8g2), keyed by dataset page ('Page 105_1')."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "hocrgen.pinkas_canvas_match_checks.v1":
        raise RuntimeError(f"{path} is not a hocrgen.pinkas_canvas_match_checks.v1 file")
    return {check["dataset_page"]: check for check in payload["checks"]}


def pinkas_match_scan_fields(check: dict[str, Any], *, number: int, side: str) -> dict[str, Any]:
    """The scan's ``match_method`` and ``match_check`` for one page, from its recorded check (F8g2)."""

    record = {key: check[key] for key in ("status", "checked_by", "checked_at", "method") if key in check}
    if check.get("reason"):
        record["reason"] = check["reason"]
    if check["status"] == "verified":
        method = (
            f"{PINKAS_LABEL_RULE}; verified for this page by agent visual comparison with the {side} half of the NLI "
            f"canvas 'Page {number}' ({check['method']}, {check['checked_at']})"
        )
    else:
        method = f"{PINKAS_LABEL_RULE}; this page is not visually verified yet ({check.get('reason')}, {check['checked_at']})"
    return {"match_method": method, "match_check": record}


def materialize_pinkas(
    *,
    cache: Path,
    out_root: Path,
    checks_path: Path = Path(DEFAULT_PINKAS_CHECKS),
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    packaged_root = _data("pinkas_dataset_bgu/snapshot")
    root = out_root / "sources" / SOURCE_PINKAS / "snapshot"
    snapshot = load_yaml_file(packaged_root / "snapshot.yaml")
    template = json.loads((packaged_root / "entries.jsonl").read_text(encoding="utf-8").splitlines()[0])
    manifest_bytes = (cache / "pinkas" / "nli_manifest.json").read_bytes()
    capture = _pinkas_capture()
    if _sha256(manifest_bytes) != capture["upstream_sha256"]:
        raise RuntimeError("cached NLI manifest does not match the pinned capture")
    canvases = {
        str(canvas["label"]): (position, canvas["@id"])
        for position, canvas in enumerate(
            canvas for sequence in json.loads(manifest_bytes).get("sequences", []) for canvas in sequence.get("canvases", [])
        )
    }
    zip_path = cache / "pinkas" / "pinkas_dataset.zip"
    if hashlib.md5(zip_path.read_bytes()).hexdigest() != PINKAS_ZIP_MD5:
        raise RuntimeError("cached Pinkas zip does not match its Zenodo MD5")
    bundle = load_and_validate_bundle()
    source = next(item for item in bundle.source_registry.sources if item.id == SOURCE_PINKAS)
    checks = load_pinkas_checks(checks_path)
    with zipfile.ZipFile(zip_path) as archive:
        names = {info.filename: info for info in archive.infolist()}
        splits: dict[str, str] = {}
        for split, member in (("train", "train_set.txt"), ("test", "test_set.txt")):
            name = next(name for name in names if name.endswith(member))
            for line in archive.read(name).decode("utf-8").splitlines():
                if line.strip():
                    splits[Path(line.strip()).stem] = split
        pages = sorted(
            {
                (int(match.group(1)), int(match.group(2)))
                for name in names
                if name.startswith(PINKAS_MEMBER_PREFIX) and (match := PINKAS_PAGE_NAME.match(name.removeprefix(PINKAS_MEMBER_PREFIX)))
            }
        )
        selected: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = []
        for number, half in pages:
            stem = f"Page {number}_{half}"
            image = archive.read(PINKAS_MEMBER_PREFIX + stem + ".jpg")
            xml = archive.read(PINKAS_MEMBER_PREFIX + stem + ".xml")
            side = "right" if half == 1 else "left"
            entry_id = f"{PINKAS_RECORD}__page{number}_{side}"
            position, canvas_id = canvases[f"Page {number}"]
            region = f"{side}_half"
            width, height = _image_size(image)
            asset_path = f"assets/{entry_id}.jpg"
            xml_path = f"page_xml/{entry_id}.xml.gz"
            _write(root / asset_path, image)
            _write(root / xml_path, gzip.compress(xml, mtime=0))
            entry = copy.deepcopy(template)
            entry["entry_id"] = entry_id
            entry["title"] = (
                f"Pinkas of the Frankfurt am Main Jewish community (NLI Ms. Heb. 4°662), image {number}, {side}-hand page"
            )
            entry["files"] = [
                {
                    "bytes": len(image),
                    "derived_from": "upstream image bytes, unchanged",
                    "height_px": height,
                    "local_path": asset_path,
                    "mime_type": "image/jpeg",
                    "role": "upstream",
                    "sha256": _sha256(image),
                    "width_px": width,
                }
            ]
            entry["annotation"].update(
                {"local_path": xml_path, "sha256": _sha256(xml), "line_count": xml.count(b"<TextLine")}
            )
            entry["upstream"] = {
                **template["upstream"],
                "image_bytes": len(image),
                "image_crc32": f"{names[PINKAS_MEMBER_PREFIX + stem + '.jpg'].CRC:08x}",
                "image_height_px": height,
                "image_member": PINKAS_MEMBER_PREFIX + stem + ".jpg",
                "image_sha256": _sha256(image),
                "image_width_px": width,
                "page_xml_bytes": len(xml),
                "page_xml_crc32": f"{names[PINKAS_MEMBER_PREFIX + stem + '.xml'].CRC:08x}",
                "page_xml_member": PINKAS_MEMBER_PREFIX + stem + ".xml",
                "page_xml_sha256": _sha256(xml),
                "split": splits.get(stem),
            }
            entry["scan"].update(
                {
                    "canvas_label": f"Page {number}",
                    "canvas_region": region,
                    "iiif_canvas": canvas_id,
                }
            )
            check = checks.get(stem)
            if check is None or check.get("canvas_id") != canvas_id or check.get("dataset_image_sha256") != _sha256(image):
                raise RuntimeError(f"Pinkas {stem} has no canvas match check for {canvas_id} and its image")
            entry["scan"].update(pinkas_match_scan_fields(check, number=number, side=side))
            selected.append({"canvas_id": canvas_id, "dataset_page": stem, "index": position, "label": f"Page {number}", "region": region})
            entries.append(entry)
    capture = {**capture, "selected_canvases": selected}
    _write(root / "iiif" / "nli_990000445290205171_manifest_capture.json", (json.dumps(capture, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
    shutil.copyfile(packaged_root / "line_language_tags.yaml", root / "line_language_tags.yaml")
    kept = []
    skipped: dict[str, int] = {}
    for entry in entries:
        reason = pinkas_dataset_entry_exclusion_reason(entry, source, root)
        if reason is None:
            kept.append(entry)
        else:
            skipped[reason] = skipped.get(reason, 0) + 1
    _write(root / "entries.jsonl", _json_lines(kept))
    tranche_snapshot = {
        **snapshot,
        "scope": "tranche",
        "notes": (
            f"F8g tranche ({TRANCHE_ID}). All 30 dataset pages from the Zenodo zip (MD5 pinned), images and PAGE XML "
            "unchanged (the XML gzip-compressed with mtime 0), each bound to its NLI canvas by the F8d2 label rule. The "
            "line-language sidecar is the packaged one: lines of the other pages are untagged, so character_level_only. "
            "Each entry's scan.match_check records whether its canvas binding was visually verified (F8g2, "
            "docs/pinkas_canvas_match_checks.json)."
        ),
    }
    _write(root / "snapshot.yaml", yaml.safe_dump(tranche_snapshot, allow_unicode=True, sort_keys=False).encode())
    verified = sum(1 for entry in kept if entry["scan"]["match_check"]["status"] == "verified")
    log(f"pinkas: {len(kept)} entries ({verified} canvas matches visually verified); skipped {skipped}")
    return {"item_count": len(kept), "skipped": skipped, "canvas_match_verified": verified, "canvas_match_not_verified": len(kept) - verified}


# --- tree descriptor, checksums and the committed manifest -------------------------------------------------------


def write_descriptor(out_root: Path, *, created_at: str, results: dict[str, dict[str, Any]], inputs: dict[str, Any]) -> None:
    descriptor = {
        "schema": TRANCHE_SCHEMA,
        "tranche_id": TRANCHE_ID,
        "created_at": created_at,
        "inputs": inputs,
        "sources": {
            source_id: {"snapshot": f"sources/{source_id}/snapshot", **result}
            for source_id, result in sorted(results.items())
        },
    }
    _write(out_root / TRANCHE_DESCRIPTOR, (json.dumps(descriptor, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
    lines = [
        f"{sha256_path(path)}  {path.relative_to(out_root).as_posix()}"
        for path in sorted(out_root.rglob("*"))
        if path.is_file() and path.name != TRANCHE_CHECKSUMS
    ]
    _write(out_root / TRANCHE_CHECKSUMS, ("\n".join(lines) + "\n").encode())


SNAPSHOT_DESCRIPTOR_FILES = {
    SOURCE_WIKISOURCE: ["snapshot.yaml", "indexes.json", "pages.jsonl"],
    SOURCE_YIDTAKNL: ["snapshot.yaml", "entries.jsonl"],
    SOURCE_PINKAS: ["snapshot.yaml", "entries.jsonl", "line_language_tags.yaml", "iiif/nli_990000445290205171_manifest_capture.json"],
    SOURCE_RESHUMOT: ["snapshot.yaml", "entries.jsonl"],
    SOURCE_KNESSET: ["snapshot.yaml", "entries.jsonl"],
}


def _wikisource_items(root: Path) -> list[dict[str, Any]]:
    items = []
    for line in (root / "pages.jsonl").read_text(encoding="utf-8").splitlines():
        page = json.loads(line)
        crop = page.get("crop") if page_needs_crop(page) else None
        pair = (crop or {}).get("asset") or page["image"]
        items.append(
            {
                "source_item_id": page["source_item_id"],
                "source_group": f"wikisource:{page['index_key']}",
                "modality": "printed",
                "asset": {key: pair[key] for key in ("path", "sha256", "bytes", "width", "height")},
                "page_image": {key: page["image"][key] for key in ("path", "sha256", "bytes")} if crop else None,
                "text": {"path": page["text_path"], "sha256_without_final_newline": page["text_sha256"]},
                "cropped": crop is not None,
                "quality": page["quality"],
                "provenance": {
                    "page_title": page["page_title"],
                    "revision_id": page["revision_id"],
                    "commons_file_sha1": page["image"]["rendered_from"]["commons_file_sha1"],
                    "commons_page": page["image"]["rendered_from"]["page"],
                },
            }
        )
    return items


def _entry_items(root: Path, *, source_id: str, text_key: str, modality: str) -> list[dict[str, Any]]:
    items = []
    for line in (root / "entries.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        asset = entry["files"][0]
        text = entry[text_key]
        upstream = entry.get("upstream") or {}
        items.append(
            {
                "source_item_id": entry["entry_id"],
                "source_group": f"{'yidtaknl' if source_id == SOURCE_YIDTAKNL else source_id}:{entry['work_id']}",
                "modality": modality,
                "asset": {
                    "path": asset["local_path"],
                    "sha256": asset["sha256"],
                    "bytes": asset["bytes"],
                    "width": asset["width_px"],
                    "height": asset["height_px"],
                },
                "text": {"path": text["local_path"], "sha256": text["sha256"]},
                "cropped": False,
                "provenance": {
                    "iiif_canvas": entry["scan"].get("iiif_canvas"),
                    "nli_record": entry["scan"].get("record_id"),
                    "upstream_image": upstream.get("image_path") or upstream.get("image_member"),
                    "upstream_image_sha1": upstream.get("image_sha1"),
                    "upstream_image_sha256": upstream.get("image_sha256"),
                },
            }
        )
    return items


def _government_print_items(root: Path, *, source_id: str) -> list[dict[str, Any]]:
    items = []
    for line in (root / "entries.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        asset = entry["files"][0]
        text = entry.get("text") or {}
        if source_id == SOURCE_RESHUMOT:
            group = f"reshumot:{entry['booklet']['series']}:{entry['booklet']['booklet_number']}"
            provenance = {
                "booklet": f"{entry['booklet']['series_name_he']} {entry['booklet']['booklet_number']}",
                "publish_date": entry["booklet"]["publish_date"],
                "pdf_page_index": entry["page"]["pdf_page_index"],
                "pdf_sha256": entry["pdf"]["sha256"],
            }
        else:
            group = f"knesset_committee:{entry['document']['document_id']}"
            provenance = {
                "committee": entry["committee"]["name"],
                "session_date": entry["session"]["start_date"],
                "knesset_num": entry["session"].get("knesset_num"),
                "document_id": entry["document"]["document_id"],
                "pdf_page_index": entry["page"]["pdf_page_index"],
                "pdf_sha256": entry["pdf"]["sha256"],
            }
        items.append(
            {
                "source_item_id": entry["entry_id"],
                "source_group": group,
                "modality": "printed",
                "asset": {
                    "path": asset["local_path"],
                    "sha256": asset["sha256"],
                    "bytes": asset["bytes"],
                    "width": asset["width_px"],
                    "height": asset["height_px"],
                },
                "text": {"path": text["local_path"], "sha256": text["sha256"]} if text.get("local_path") else None,
                "cropped": bool(entry.get("crop")),
                "provenance": provenance,
                # F8e3: Reshumot line text is verified, its order across the page is not (``within_line``).
                **({"reading_order_verified": text["reading_order_verified"]} if text.get("reading_order_verified") else {}),
            }
        )
    return items


def build_manifest(tranche_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    descriptor = json.loads((tranche_root / TRANCHE_DESCRIPTOR).read_text(encoding="utf-8"))
    sources: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    for source_id, entry in sorted(descriptor["sources"].items()):
        root = tranche_root / entry["snapshot"]
        if source_id == SOURCE_WIKISOURCE:
            source_items = _wikisource_items(root)
        elif source_id == SOURCE_YIDTAKNL:
            source_items = _entry_items(root, source_id=source_id, text_key="text", modality="printed")
        elif source_id in (SOURCE_RESHUMOT, SOURCE_KNESSET):
            source_items = _government_print_items(root, source_id=source_id)
        else:
            source_items = _entry_items(root, source_id=source_id, text_key="annotation", modality="handwritten")
        snapshot_bytes = sum(path.stat().st_size for path in root.rglob("*") if path.is_file())
        sources[source_id] = {
            "snapshot": entry["snapshot"],
            "item_count": len(source_items),
            "snapshot_bytes": snapshot_bytes,
            "snapshot_file_count": sum(1 for path in root.rglob("*") if path.is_file()),
            "snapshot_files": {
                f"{entry['snapshot']}/{name}": sha256_path(root / name) for name in SNAPSHOT_DESCRIPTOR_FILES[source_id]
            },
            "skipped": entry.get("skipped", {}),
            **{key: entry[key] for key in ("pages_checked", "pages_passed", "canvas_match_verified", "canvas_match_not_verified") if key in entry},
        }
        items.extend({"source_id": source_id, **item} for item in source_items)
    checksums = tranche_root / TRANCHE_CHECKSUMS
    manifest = {
        "schema": TRANCHE_MANIFEST_SCHEMA,
        "tranche_id": descriptor["tranche_id"],
        "created_at": descriptor["created_at"],
        "planning_notation": TRANCHE_NOTATION,
        "inputs": descriptor["inputs"],
        "item_count": len(items),
        "total_bytes": sum(path.stat().st_size for path in tranche_root.rglob("*") if path.is_file()),
        "file_count": sum(1 for _ in checksums.read_text(encoding="utf-8").splitlines()),
        "sha256sums_sha256": sha256_path(checksums),
        "items_path": "tranche_items.jsonl",
        "sources": sources,
        "hosting": "not published; see docs/real_source_release_contract.md (hosting proposal, maintainer decision)",
    }
    return manifest, items


def refresh_reshumot(
    *,
    base: Path,
    out: Path,
    cache: Path,
    created_at: str,
    captured_at: str,
    layer_cache: Path | None = None,
    report: Path | None = None,
) -> dict[str, Any]:  # pragma: no cover - operator entry point (poppler, pdfminer.six)
    """A new tranche tree from ``base`` with only the Reshumot snapshot rebuilt (F8e2; F8e3 rebuilt it again).

    Every other source's snapshot is copied byte for byte, with its descriptor entry; the Reshumot snapshot is
    materialized again from the cache, and the descriptor and SHA256SUMS are rewritten under this tranche id.
    """

    import shutil

    problems = verify_tranche_files(base)
    if problems:
        raise SystemExit(f"{base} does not match its SHA256SUMS: {problems[:5]}")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    descriptor = json.loads((base / TRANCHE_DESCRIPTOR).read_text(encoding="utf-8"))
    for source_id, entry in descriptor["sources"].items():
        if source_id != SOURCE_RESHUMOT:
            shutil.copytree(base / entry["snapshot"], out / entry["snapshot"])
    bundle = load_and_validate_bundle()
    sources = {source.id: source for source in bundle.source_registry.sources}
    results = {source_id: {key: value for key, value in entry.items() if key != "snapshot"} for source_id, entry in descriptor["sources"].items()}
    results[SOURCE_RESHUMOT] = government_print_tranche.materialize_reshumot(
        cache=cache, out_root=out, packaged_root=_data("reshumot/snapshot"), source=sources[SOURCE_RESHUMOT], captured_at=captured_at,
        gate=reshumot_entry_exclusion_reasons, outline_table=_data("reshumot/snapshot/glyph_outlines.json"), layer_cache=layer_cache, report=report,
    )
    inputs = dict(descriptor["inputs"])
    listing = cache / "reshumot" / "booklets.jsonl"
    inputs["reshumot_capture"] = {"listing_sha256": sha256_path(listing), "captured_at": captured_at, "seed": CAPTURE_SEED}
    inputs["reshumot_method"] = {
        "normalization": results[SOURCE_RESHUMOT]["method"],
        "glyph_outline_table_sha256": sha256_path(_data("reshumot/snapshot/glyph_outlines.json")),
    }
    inputs["refreshed_from"] = {"tranche_id": descriptor["tranche_id"], "sha256sums_sha256": sha256_path(base / TRANCHE_CHECKSUMS)}
    write_descriptor(out, created_at=created_at, results=results, inputs=inputs)
    return results[SOURCE_RESHUMOT]


def _wikisource_page_files(page: dict[str, Any]) -> set[str]:
    """The snapshot files a Wikisource page record owns: its image, its crop asset, its wikitext and its pair text."""

    crop = page.get("crop") or {}
    validated = page.get("validated_revision") or {}
    paths = {page["image"]["path"], page.get("wikitext_path"), page.get("text_path"), (crop.get("asset") or {}).get("path"),
             validated.get("wikitext_path")}
    return {path for path in paths if path}


def refresh_wikisource(*, base: Path, out: Path, page_check_paths: list[Path], created_at: str,
                       validated_revisions: Path | None = None, validated_text_checks: Path | None = None) -> dict[str, Any]:
    """A new tranche tree from ``base`` with the committed page checks' page-level verdicts re-applied to Wikisource (E2d3e).

    Every other source's snapshot is copied byte for byte, with its descriptor entry. A Wikisource page whose current
    winning check (pinned to the page revision and the Commons file) records ``text_not_on_page`` takes it, and the
    unchanged fetcher gates decide: a page they now reject is dropped with the files only it owns. Every other page
    record (its ``pages.jsonl`` line) and file is copied unchanged.

    With ``validated_revisions`` (a ``wikisource_validated_revisions`` output, E2d3b) and ``validated_text_checks``
    (``docs/wikisource_validated_text_checks.json``), every kept page with a pinned validating revision carries it
    (``validated_revision``, its wikitext copied into the snapshot) and its committed check (``validated_text_check``),
    so the fetcher scores and weighs exactly the pages the evaluation scores (``scored_page_reference``). The
    descriptor and ``SHA256SUMS`` are rewritten under this tranche id.
    """

    import shutil

    from hocrgen.fetchers.wikisource import VALIDATED_REVISION_FIELD, VALIDATED_TEXT_CHECK_FIELD, load_validated_text_checks
    from hocrgen.tools.wikisource_inventory import load_page_checks
    from hocrgen.tools.wikisource_validated_revisions import load_validated_revisions

    if (validated_revisions is None) != (validated_text_checks is None):
        raise SystemExit("--validated-revisions and --validated-text-checks go together")
    problems = verify_tranche_files(base)
    if problems:
        raise SystemExit(f"{base} does not match its SHA256SUMS: {problems[:5]}")
    if out.exists() and any(out.iterdir()):
        raise SystemExit(f"{out} is not empty")
    revisions = load_validated_revisions(validated_revisions) if validated_revisions is not None else {}
    text_checks = load_validated_text_checks(validated_text_checks) if validated_text_checks is not None else {}
    descriptor = json.loads((base / TRANCHE_DESCRIPTOR).read_text(encoding="utf-8"))
    for source_id, entry in descriptor["sources"].items():
        shutil.copytree(base / entry["snapshot"], out / entry["snapshot"])
    root = out / descriptor["sources"][SOURCE_WIKISOURCE]["snapshot"]
    _, indexes, _ = load_wikisource_snapshot(root)
    checks = load_page_checks(page_check_paths)
    lines = (root / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    kept: list[str] = []
    dropped: list[dict[str, Any]] = []
    validated_count = 0
    for line in lines:
        page = json.loads(line)
        check = checks.get(page["page_title"]) or {}
        current = (check.get("revision_id") == page.get("revision_id")
                   and check.get("commons_file_sha1") == indexes[page["index_key"]]["commons_file"]["sha1"])
        flagged = {**page, "text_not_on_page": check["text_not_on_page"]} if current and check.get("text_not_on_page") else page
        reasons = page_exclusion_reasons(flagged, indexes, root)
        if reasons:
            dropped.append({"page": page, "reasons": reasons})
            continue
        record = revisions.get(f"{SOURCE_WIKISOURCE}:{page['source_item_id']}")
        if record is None:
            kept.append(line)
            continue
        target = f"wikitext/{page['source_item_id']}.validated.wikitext.txt"
        _write(root / target, record["wikitext"].encode("utf-8"))
        page[VALIDATED_REVISION_FIELD] = {
            "validating_revision_id": record["validating_revision_id"], "wikitext_path": target,
            "wikitext_sha256": record["wikitext_sha256"], "converted_text_sha256": record["converted_text_sha256"],
            "text_changing_edits_after_validation": record["text_changing_edits_after_validation"],
        }
        check = text_checks.get(page["page_title"])
        if check is not None:
            page[VALIDATED_TEXT_CHECK_FIELD] = check
        kept.append(json.dumps(page, ensure_ascii=False, sort_keys=True))
        validated_count += 1
    kept_files = set().union(*(_wikisource_page_files(json.loads(line)) for line in kept))
    for entry in dropped:
        for relative in sorted(_wikisource_page_files(entry["page"]) - kept_files):
            (root / relative).unlink()
    used = {json.loads(line)["index_key"] for line in kept}
    emptied = {json.loads(line)["index_key"] for line in lines} - used
    if emptied:
        # An Index that lost every page leaves the snapshot's Index list, written as materialize writes it.
        records = json.loads((root / "indexes.json").read_text(encoding="utf-8"))["indexes"]
        kept_records = [record for record in records if record["index_key"] not in emptied]
        _write(root / "indexes.json", (json.dumps({"indexes": kept_records}, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
    _write(root / "pages.jsonl", "".join(line + "\n" for line in kept).encode())
    results = {source_id: {key: value for key, value in entry.items() if key != "snapshot"} for source_id, entry in descriptor["sources"].items()}
    skipped = dict(results[SOURCE_WIKISOURCE].get("skipped") or {})
    for entry in dropped:
        skipped[entry["reasons"][0]] = skipped.get(entry["reasons"][0], 0) + 1
    results[SOURCE_WIKISOURCE] = {**results[SOURCE_WIKISOURCE], "item_count": len(kept), "skipped": dict(sorted(skipped.items()))}
    if "index_count" in results[SOURCE_WIKISOURCE]:
        results[SOURCE_WIKISOURCE]["index_count"] -= len(emptied)
    inputs = dict(descriptor["inputs"])
    inputs["wikisource_page_checks"] = {path.as_posix(): sha256_path(path) for path in page_check_paths}
    if validated_revisions is not None and validated_text_checks is not None:
        inputs["wikisource_validated_revisions"] = {"sha256": sha256_path(validated_revisions / "validated_revisions.json"),
                                                    "pages_carrying_them": validated_count}
        inputs["wikisource_validated_text_checks"] = {validated_text_checks.as_posix(): sha256_path(validated_text_checks)}
    inputs["refreshed_from"] = {"tranche_id": descriptor["tranche_id"], "sha256sums_sha256": sha256_path(base / TRANCHE_CHECKSUMS)}
    write_descriptor(out, created_at=created_at, results=results, inputs=inputs)
    return {"item_count": len(kept), "validated_revisions_carried": validated_count,
            "dropped": [{"source_item_id": entry["page"]["source_item_id"], "reasons": entry["reasons"]} for entry in dropped]}


def write_manifest(tranche_root: Path, out_dir: Path) -> dict[str, Any]:
    manifest, items = build_manifest(tranche_root)
    _write(out_dir / "tranche_manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=1, sort_keys=True) + "\n").encode())
    _write(out_dir / "tranche_items.jsonl", _json_lines(items))
    return manifest


# --- CLI -----------------------------------------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Operator-only F8g real tranche packaging (no publication).")
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture", help="Fetch pinned upstream files into the operator cache (network).")
    capture.add_argument("--cache", type=Path, required=True)
    capture.add_argument("--source", action="append", choices=("yidtaknl", "pinkas", "reshumot", "knesset"), default=None)
    capture.add_argument("--delay", type=float, default=1.0)
    capture.add_argument("--seed", default=CAPTURE_SEED, help="Seed of the Reshumot booklet and Knesset protocol samples.")
    capture.add_argument("--reshumot-per-query", type=int, default=1, help="Booklets per (series, Hebrew year) search.")
    capture.add_argument("--reshumot-max-pages", type=int, default=24, help="Skip booklets longer than this.")
    capture.add_argument("--reshumot-delay", type=float, default=4.0)
    capture.add_argument("--knesset-terms", default="1-8", help="Knesset terms to sample, e.g. 1-8.")
    capture.add_argument("--knesset-per-term", type=int, default=2)
    capture.add_argument("--knesset-delay", type=float, default=15.0)
    capture.add_argument("--pinkas-manifest-copy", type=Path, default=None, help="Operator copy of the NLI manifest (used only if its sha256 is the pinned one).")
    materialize = commands.add_parser("materialize", help="Write the tranche tree from the operator caches (offline).")
    materialize.add_argument("--out", type=Path, required=True, help="Empty folder outside the repo for the tranche tree.")
    materialize.add_argument("--cache", type=Path, required=True, help="The capture cache (YidTakNL, Pinkas).")
    materialize.add_argument("--wikisource-work-dir", type=Path, required=True, help="F8b6 inventory work dir (raw/, wikisource_inventory.json).")
    materialize.add_argument("--wikisource-renders", type=Path, action="append", required=True, help="Folder of 960 px Commons renders with renders.jsonl; repeat.")
    materialize.add_argument("--page-checks", type=Path, action="append", default=None)
    materialize.add_argument("--created-at", required=True, help="Tranche date recorded in the descriptor, e.g. 2026-11-06.")
    materialize.add_argument("--manifest-out", type=Path, default=None, help="Also write the committed manifest here.")
    materialize.add_argument("--pinkas-checks", type=Path, default=Path(DEFAULT_PINKAS_CHECKS))
    materialize.add_argument("--government-print-captured-at", default=None, help="Capture date of the Reshumot / Knesset caches.")
    materialize.add_argument("--reshumot-glyph-layers", type=Path, default=None, help="Folder of glyph layers extracted before (<entry id>.json), reused when the pdfminer.six version matches.")
    materialize.add_argument("--reshumot-report", type=Path, default=None, help="Write one JSON line per captured Reshumot page (admitted, reasons, cropped) here.")
    refresh = commands.add_parser("refresh-reshumot", help="Copy a tranche tree with only its Reshumot snapshot rebuilt (offline; poppler, pdfminer.six).")
    refresh.add_argument("--base", type=Path, required=True, help="The materialized tranche tree to start from.")
    refresh.add_argument("--out", type=Path, required=True, help="Empty folder outside the repo for the new tree.")
    refresh.add_argument("--cache", type=Path, required=True)
    refresh.add_argument("--created-at", required=True)
    refresh.add_argument("--government-print-captured-at", required=True)
    refresh.add_argument("--reshumot-glyph-layers", type=Path, default=None)
    refresh.add_argument("--reshumot-report", type=Path, default=None)
    refresh.add_argument("--manifest-out", type=Path, default=None)
    refresh_ws = commands.add_parser("refresh-wikisource", help="Copy a tranche tree with the committed Wikisource page checks re-applied (offline).")
    refresh_ws.add_argument("--base", type=Path, required=True, help="The materialized tranche tree to start from.")
    refresh_ws.add_argument("--out", type=Path, required=True, help="Empty folder outside the repo for the new tree.")
    refresh_ws.add_argument("--page-checks", type=Path, action="append", default=None)
    refresh_ws.add_argument("--validated-revisions", type=Path, default=None, help="A wikisource_validated_revisions output (E2d3b) to carry on the pages.")
    refresh_ws.add_argument("--validated-text-checks", type=Path, default=None, help="docs/wikisource_validated_text_checks.json")
    refresh_ws.add_argument("--created-at", required=True)
    refresh_ws.add_argument("--manifest-out", type=Path, default=None)
    manifest = commands.add_parser("manifest", help="Write the committed manifest for a materialized tree.")
    manifest.add_argument("--tranche", type=Path, required=True)
    manifest.add_argument("--out", type=Path, default=Path("src/hocrgen/data/real_tranche"))
    verify = commands.add_parser("verify", help="Check every file of a materialized tree against SHA256SUMS.")
    verify.add_argument("--tranche", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - operator entry point
    args = parse_args(argv)
    if args.command == "capture":
        sources = args.source or ["yidtaknl", "pinkas"]
        if "yidtaknl" in sources:
            print("yidtaknl", capture_yidtaknl(args.cache, delay=args.delay))
        if "pinkas" in sources:
            print("pinkas", capture_pinkas(args.cache, manifest_copy=args.pinkas_manifest_copy))
        if "reshumot" in sources:
            years = government_print_tranche.hebrew_years_since(date(2006, 1, 1), date.today())
            print("reshumot", government_print_tranche.capture_reshumot(
                args.cache, hebrew_years=years, seed=args.seed, per_query=args.reshumot_per_query,
                max_pages=args.reshumot_max_pages, delay=args.reshumot_delay,
            ))
        if "knesset" in sources:
            first, _, last = args.knesset_terms.partition("-")
            print("knesset", government_print_tranche.capture_knesset(
                args.cache, knesset_nums=range(int(first), int(last or first) + 1), seed=args.seed,
                per_knesset=args.knesset_per_term, delay=args.knesset_delay,
            ))
        return 0
    if args.command == "materialize":
        if args.out.exists() and any(args.out.iterdir()):
            raise SystemExit(f"{args.out} is not empty")
        page_checks = args.page_checks or [Path(path) for path in DEFAULT_PAGE_CHECKS]
        results = {
            SOURCE_WIKISOURCE: materialize_wikisource(
                work_dir=args.wikisource_work_dir, render_dirs=args.wikisource_renders, page_check_paths=page_checks, out_root=args.out
            ),
            SOURCE_YIDTAKNL: materialize_yidtaknl(cache=args.cache, out_root=args.out),
            SOURCE_PINKAS: materialize_pinkas(cache=args.cache, out_root=args.out, checks_path=args.pinkas_checks),
        }
        bundle = load_and_validate_bundle()
        sources = {source.id: source for source in bundle.source_registry.sources}
        captured_at = args.government_print_captured_at or args.created_at
        if (args.cache / "reshumot" / "booklets.jsonl").is_file():
            results[SOURCE_RESHUMOT] = government_print_tranche.materialize_reshumot(
                cache=args.cache, out_root=args.out, packaged_root=_data("reshumot/snapshot"), source=sources[SOURCE_RESHUMOT],
                captured_at=captured_at, gate=reshumot_entry_exclusion_reasons, outline_table=_data("reshumot/snapshot/glyph_outlines.json"),
                layer_cache=args.reshumot_glyph_layers, report=args.reshumot_report,
            )
        if (args.cache / "knesset" / "documents.jsonl").is_file():
            results[SOURCE_KNESSET] = government_print_tranche.materialize_knesset(
                cache=args.cache, out_root=args.out, packaged_root=_data("knesset_committees/snapshot"), source=sources[SOURCE_KNESSET],
                captured_at=captured_at, gate=knesset_entry_exclusion_reasons,
            )
        inputs = {
            "wikisource_inventory_checked_at": json.loads((args.wikisource_work_dir / "wikisource_inventory.json").read_text(encoding="utf-8"))["checked_at"],
            "wikisource_page_checks": {path.as_posix(): sha256_path(path) for path in page_checks},
            "wikisource_renders": "960 px Commons renders of the pinned files (wikisource_coverage --capture), unchanged",
            "yidtaknl_share": "https://surfdrive.surf.nl/files/index.php/s/" + YIDTAKNL_SHARE_TOKEN,
            "yidtaknl_matched_pages_sha256": sha256_path(_data("yidtaknl/snapshot/matched_pages.jsonl")),
            "pinkas_zip": PINKAS_ZIP_URL,
            "pinkas_zip_md5": PINKAS_ZIP_MD5,
            "pinkas_manifest_sha256": _pinkas_capture()["upstream_sha256"],
            "pinkas_canvas_match_checks": {args.pinkas_checks.as_posix(): sha256_path(args.pinkas_checks)},
        }
        for name, source_id in (("reshumot", SOURCE_RESHUMOT), ("knesset", SOURCE_KNESSET)):
            if source_id in results:
                listing = args.cache / name / ("booklets.jsonl" if name == "reshumot" else "documents.jsonl")
                inputs[f"{name}_capture"] = {"listing_sha256": sha256_path(listing), "captured_at": captured_at, "seed": CAPTURE_SEED}
        if SOURCE_RESHUMOT in results:
            inputs["reshumot_method"] = {
                "normalization": results[SOURCE_RESHUMOT].get("method"),
                "glyph_outline_table_sha256": sha256_path(_data("reshumot/snapshot/glyph_outlines.json")),
            }
        write_descriptor(args.out, created_at=args.created_at, results=results, inputs=inputs)
        if args.manifest_out:
            manifest = write_manifest(args.out, args.manifest_out)
            print(json.dumps({key: manifest[key] for key in ("tranche_id", "item_count", "total_bytes", "file_count")}))
        return 0
    if args.command == "refresh-reshumot":
        print(json.dumps({key: value for key, value in refresh_reshumot(
            base=args.base, out=args.out, cache=args.cache, created_at=args.created_at, captured_at=args.government_print_captured_at,
            layer_cache=args.reshumot_glyph_layers, report=args.reshumot_report,
        ).items() if key != "booklets"}, ensure_ascii=False))
        if args.manifest_out:
            manifest = write_manifest(args.out, args.manifest_out)
            print(json.dumps({key: manifest[key] for key in ("tranche_id", "item_count", "total_bytes", "file_count")}))
        return 0
    if args.command == "refresh-wikisource":
        page_checks = args.page_checks or [Path(path) for path in DEFAULT_PAGE_CHECKS]
        print(json.dumps(refresh_wikisource(base=args.base, out=args.out, page_check_paths=page_checks, created_at=args.created_at,
                                            validated_revisions=args.validated_revisions,
                                            validated_text_checks=args.validated_text_checks), ensure_ascii=False))
        if args.manifest_out:
            manifest = write_manifest(args.out, args.manifest_out)
            print(json.dumps({key: manifest[key] for key in ("tranche_id", "item_count", "total_bytes", "file_count")}))
        return 0
    if args.command == "manifest":
        manifest = write_manifest(args.tranche, args.out)
        print(json.dumps({key: manifest[key] for key in ("tranche_id", "item_count", "total_bytes", "file_count")}))
        return 0
    problems = verify_tranche_files(args.tranche)
    print(json.dumps({"status": "ok" if not problems else "error", "problems": problems[:50], "problem_count": len(problems)}))
    return 0 if not problems else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
