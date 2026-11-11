"""Rights justifications for the Commons scans behind the Wikisource pipeline (Route C): evidence pass and back-fill.

Subcommands:

- ``evidence`` (operator-only; the only path that may touch the network): gathers, for every Index the committed
  inventory admits, the evidence ``hocrgen.fetchers.wikisource_justification`` needs and writes it to
  ``docs/wikisource_rights_evidence.json`` (``wikisource_rights_evidence.v1``; ids, URLs, hashes and boxes, no page
  text and no images):

  - the exact file URL, file-page URL and MIME type, from the pinned Commons/Wikisource ``imageinfo`` responses in the
    inventory's API cache (``--api-cache``); a file page that redirects is followed to its target's licence templates;
  - the publication place the full inventory recorded (``--full-inventory``);
  - for a Commons file taken from the Internet Archive (``{{IA|…}}`` or an ``archive.org/details/…`` source), the IA
    item's identifier, contributor, sponsor, scanner and scanning centre (cached metadata first, ``--ia-metadata``);
  - the **Google hygiene pass** (strategy rule 5) for every file where Google is not ruled out: an ``eng`` Tesseract
    pass on each checked page render (Google's usage-guidelines boilerplate, ``detect_google_front_matter``) and on its
    foot band, upscaled 3x (the "Digitized by Google" line, ``detect_google_watermark``). The checked pages are scan
    pages 1-3 (where Google's front page sits) and every page of the file in the tranche snapshot (``--snapshot``).
    Page renders come from the snapshot, then the render caches (``--render-cache``), then Commons (``--fetch``).

  Downloads go to their own folders under ``--work-dir``, at most one request per second, with the User-Agent
  ``HeOCR-research/0.1 (+https://github.com/HeOCR)``. ``--skip-index`` keeps an Index out of the image pass (the E2d3d
  evaluation pages are never opened).
- ``backfill`` (network-free): builds the ``rights_justification`` of every admitted Index from the committed
  inventory and evidence and writes ``docs/wikisource_rights_justifications.json``, then prints the counts by reason,
  digitizer and Google status. A test replays it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from hocrgen.fetchers.google_hygiene import (
    FOOT_BAND_FRACTIONS,
    FRONT_MATTER_MAX_CANVASES,
    detect_google_front_matter,
    detect_google_watermark,
    foot_band_box,
)
from hocrgen.fetchers.wikisource_justification import (
    EVIDENCE_PATH,
    EVIDENCE_SCHEMA,
    GENERATOR,
    REGISTRY_PATH,
    REGISTRY_SCHEMA,
    build_wikisource_rights_justification,
    justification_key,
    wikisource_hygiene_record,
)

USER_AGENT = "HeOCR-research/0.1 (+https://github.com/HeOCR)"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
IA_METADATA = "https://archive.org/metadata/{identifier}"
RENDER_WIDTH = 960
UPSCALE = 3
IA_FIELDS = ("identifier", "contributor", "sponsor", "scanner", "scanningcenter", "date", "possible-copyright-status")
IA_SOURCE = re.compile(r"\{\{\s*IA\s*\|\s*([A-Za-z0-9._-]+)|archive\.org/details/([A-Za-z0-9._-]+)")
REDIRECT = re.compile(r"#REDIRECT\s*\[\[\s*(?:File|קובץ)\s*:\s*([^\]|]+)", re.I)
FILE_NAMESPACES = ("File:", "קובץ:", "Image:", "תמונה:")
ROOT = Path(__file__).resolve().parents[3]


def _bare(title: str) -> str:
    for prefix in FILE_NAMESPACES:
        if title.startswith(prefix):
            title = title[len(prefix):]
    return title.replace("_", " ").strip()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


# --- cached evidence -------------------------------------------------------------------------------------------------


def cached_imageinfo(api_cache: Path) -> dict[str, dict[str, Any]]:
    """``imageinfo`` (with ``url``) and file-page wikitext of every file in the inventory's raw API cache, by bare title."""

    found: dict[str, dict[str, Any]] = {}
    for path in sorted(api_cache.glob("*.json")):
        text = path.read_text(encoding="utf-8")
        if '"imageinfo"' not in text:
            continue
        payload = json.loads(text)
        for page in (payload.get("query") or {}).get("pages") or []:
            info = (page.get("imageinfo") or [{}])[0]
            if not info.get("url"):
                continue
            entry = found.setdefault(_bare(page.get("title", "")), {})
            entry.update({key: info.get(key) for key in ("url", "descriptionurl", "sha1", "mime", "size", "pagecount")})
            revision = (page.get("revisions") or [{}])[0]
            content = ((revision.get("slots") or {}).get("main") or {}).get("content")
            if content is not None:
                entry["wikitext"] = content
            entry["cache_file"] = path.name
    return found


class Fetcher:  # pragma: no cover - live network path, operator only
    """At most one request per second, with HeOCR's research User-Agent; every response saved under ``directory``."""

    def __init__(self, directory: Path, *, enabled: bool, delay: float = 1.0) -> None:
        self.directory = directory
        self.enabled = enabled
        self.delay = delay
        self.last = 0.0
        self.count = 0

    def get(self, url: str, name: str) -> bytes | None:
        target = self.directory / name
        if target.is_file():
            return target.read_bytes()
        if not self.enabled:
            return None
        wait = self.delay - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
        except Exception as error:  # noqa: BLE001 - recorded, never fatal
            sys.stderr.write(f"fetch failed {url}: {error}\n")
            data = None
        finally:
            self.last = time.monotonic()
            self.count += 1
        if data is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return data


def ia_identifier(index: Mapping[str, Any]) -> str | None:
    commons = index.get("commons_file") or {}
    for field in (commons.get("source_field"), commons.get("institution_field"), commons.get("provenance_text")):
        match = IA_SOURCE.search(str(field or ""))
        if match:
            return match.group(1) or match.group(2)
    return None


def ia_item_fields(metadata: Mapping[str, Any]) -> dict[str, Any]:
    md = metadata.get("metadata") if isinstance(metadata.get("metadata"), Mapping) else metadata
    out = {}
    for field in IA_FIELDS:
        value = md.get(field)
        if isinstance(value, list):
            value = "; ".join(str(v) for v in value)
        out[field] = value
    return out


def thumb_url(file_url: str, page: int | None, width: int = RENDER_WIDTH) -> str:
    """The Wikimedia thumbnail URL of one page of a PDF/DjVu file (or of an image file when ``page`` is None)."""

    url = file_url.split("?")[0]
    head, name = url.rsplit("/", 1)
    head = re.sub(r"^(https://upload\.wikimedia\.org/[^/]+/[^/]+)/", r"\1/thumb/", head + "/")
    if page is None:
        return f"{head}{name}/{width}px-{name}"
    return f"{head}{name}/page{page}-{width}px-{name}.jpg"


# --- the hygiene pass ---------------------------------------------------------------------------------------------


def _tesseract(image_path: Path, psm: int) -> str:  # pragma: no cover - needs tesseract
    result = subprocess.run(["tesseract", str(image_path), "-", "-l", "eng", "--psm", str(psm), "tsv"],
                            capture_output=True, text=True, timeout=300)
    return result.stdout


def check_page_render(job: tuple[str, str, str]) -> dict[str, Any]:  # pragma: no cover - needs tesseract
    """Front matter and watermark of one page render: (render path, its sha256, OCR cache folder)."""

    from PIL import Image

    render, digest, cache = Path(job[0]), job[1], Path(job[2])
    cache.mkdir(parents=True, exist_ok=True)
    front_tsv = cache / f"{digest}.front.tsv"
    if not front_tsv.is_file():
        front_tsv.write_text(_tesseract(render, 3), encoding="utf-8")
    is_front, phrases = detect_google_front_matter(front_tsv.read_text(encoding="utf-8"))
    box = None
    band_used = None
    with Image.open(render) as opened:
        image = opened.convert("L")
    width, height = image.size
    for fraction in FOOT_BAND_FRACTIONS:
        band = foot_band_box(image.size, fraction)
        name = f"{digest}.b{round(fraction * 100):02d}"
        tsv = cache / f"{name}.tsv"
        if not tsv.is_file():
            crop = image.crop(band)
            crop = crop.resize((crop.width * UPSCALE, crop.height * UPSCALE), Image.LANCZOS)
            png = cache / f"{name}.png"
            crop.save(png)
            tsv.write_text(_tesseract(png, 6), encoding="utf-8")
            png.unlink()
        found = detect_google_watermark(tsv.read_text(encoding="utf-8"), band_top=band[1] * UPSCALE, scale=1 / UPSCALE)
        if found is not None:
            x, y, w, h = found
            box = [round(x / width, 4), round(y / height, 4), round(w / width, 4), round(h / height, 4)]
            band_used = fraction
            break
    return {"render_width": width, "render_height": height, "front_matter": is_front, "phrases": phrases,
            "google_watermark_bbox": box, "watermark_band": band_used}


def snapshot_renders(snapshot: Path) -> dict[tuple[str, int], tuple[Path, str]]:
    """Page renders in a tranche snapshot by (Commons SHA-1, scan page): path and pinned sha256."""

    found = {}
    for line in (snapshot / "pages.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        page = json.loads(line)
        image = page.get("image") or {}
        rendered = image.get("rendered_from") or {}
        path = snapshot / str(image.get("path", ""))
        if rendered.get("commons_file_sha1") and isinstance(rendered.get("page"), int) and path.is_file():
            found[(rendered["commons_file_sha1"], rendered["page"])] = (path, image.get("sha256"))
    return found


def cached_renders(directories: Sequence[Path]) -> dict[tuple[str, int], Path]:
    found: dict[tuple[str, int], Path] = {}
    for directory in directories:
        index_file = directory / "renders.jsonl"
        if not index_file.is_file():
            continue
        for line in index_file.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            sha = record.get("pinned_commons_sha1") or record.get("commons_file_sha1")
            path = directory / f"{record['slug']}.jpg"
            if sha and isinstance(record.get("page"), int) and path.is_file():
                found.setdefault((sha, record["page"]), path)
    return found


# --- evidence -----------------------------------------------------------------------------------------------------


def gather_evidence(args: argparse.Namespace, log: Callable[[str], None] = print) -> dict[str, Any]:  # pragma: no cover - operator
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    full = {i["index_key"]: i for i in json.loads(args.full_inventory.read_text(encoding="utf-8"))["indexes"]}
    admitted = [i for i in inventory["indexes"] if (i.get("gate") or {}).get("admitted")]
    imageinfo = cached_imageinfo(args.api_cache)
    ia_cache = json.loads(args.ia_metadata.read_text(encoding="utf-8")) if args.ia_metadata else {}
    ia_by_identifier = {ia_item_fields(v).get("identifier"): v for v in ia_cache.values() if isinstance(v, Mapping)}
    downloads = args.work_dir / "downloads"
    fetch_api = Fetcher(downloads / "api", enabled=args.fetch)
    fetch_ia = Fetcher(downloads / "ia", enabled=args.fetch)
    fetch_render = Fetcher(downloads / "renders", enabled=args.fetch)
    snapshot = snapshot_renders(args.snapshot) if args.snapshot else {}
    caches = cached_renders(args.render_cache or [])
    skip = set(args.skip_index or [])
    entries: dict[str, dict[str, Any]] = {}
    jobs: dict[str, list[tuple[int, Path, str, str]]] = {}
    for index in sorted(admitted, key=lambda i: i["index_key"]):
        key = index["index_key"]
        commons = index["commons_file"]
        full_commons = (full.get(key) or {}).get("commons_file") or {}
        info = imageinfo.get(_bare(commons["title"])) or {}
        file: dict[str, Any] = {
            "repository": commons.get("repository"),
            "url": (info.get("url") or "").split("?")[0] or None,
            "description_url": full_commons.get("description_url") or info.get("descriptionurl"),
            "sha1": info.get("sha1"),
            "mime": info.get("mime") or full_commons.get("mime"),
            "size": info.get("size") or full_commons.get("size"),
            "imageinfo_source": f"inventory API cache {info['cache_file']}" if info.get("cache_file") else None,
        }
        redirect = REDIRECT.search(str(commons.get("provenance_text") or "")) or REDIRECT.search(str(info.get("wikitext") or ""))
        if redirect:
            target = redirect.group(1).strip()
            raw = fetch_api.get(
                COMMONS_API + "?" + urllib.parse.urlencode({
                    "action": "query", "format": "json", "formatversion": "2", "titles": f"File:{target}",
                    "prop": "revisions", "rvprop": "ids|content", "rvslots": "main"}),
                f"commons_filepage_{hashlib.sha256(target.encode()).hexdigest()[:16]}.json",
            )
            templates: list[str] | None = None
            revid = None
            if raw is not None:
                from hocrgen.tools.wikisource_inventory import licence_templates

                page = json.loads(raw)["query"]["pages"][0]
                revision = (page.get("revisions") or [{}])[0]
                revid = revision.get("revid")
                templates = licence_templates(str(((revision.get("slots") or {}).get("main") or {}).get("content", "")))
            file["redirect_target"] = {"title": f"File:{target}", "file_page_revision_id": revid, "licence_templates": templates}
        entry: dict[str, Any] = {"index_key": key, "commons_file": commons["title"], "commons_file_sha1": commons["sha1"], "file": file}
        place = ((full.get(key) or {}).get("work") or {}).get("place")
        entry["place"] = {"place": place, "source": "Commons {{Book}} city field, else the Index page Address field"
                          " (wikisource_inventory)"} if place else None
        identifier = ia_identifier(index)
        if identifier:
            metadata = ia_by_identifier.get(identifier)
            if metadata is None:
                raw = fetch_ia.get(IA_METADATA.format(identifier=identifier), f"{identifier}.json")
                metadata = json.loads(raw) if raw else None
            entry["ia_item"] = ia_item_fields(metadata) if metadata else {"identifier": identifier, "metadata": "not_fetched"}
        entries[key] = entry
        if index["scan_rights"].get("digitized_by_google") is False or key in skip:
            continue
        pages: dict[int, tuple[Path, str, str]] = {}
        # A single-image file (no page count) is checked as its one page, scan page 1.
        wanted = set(range(1, FRONT_MATTER_MAX_CANVASES + 1)) if commons.get("page_count") else {1}
        wanted |= {page for (sha, page) in snapshot if sha == commons["sha1"]}
        for page in sorted(wanted):
            if commons.get("page_count") and page > commons["page_count"]:
                continue
            if (commons["sha1"], page) in snapshot:
                path, digest = snapshot[(commons["sha1"], page)]
                pages[page] = (path, digest, "tranche snapshot")
            elif (commons["sha1"], page) in caches:
                path = caches[(commons["sha1"], page)]
                pages[page] = (path, _sha256_file(path), "operator render cache")
            elif file["url"]:
                url = thumb_url(file["url"], page if commons.get("page_count") else None)
                name = f"{key}__p{page:04d}.jpg"
                data = fetch_render.get(url, name)
                if data is not None and data[:3] in (b"\xff\xd8\xff", b"\x89PN"):
                    pages[page] = (downloads / "renders" / name, _sha256_bytes(data), "Commons thumbnail " + url)
        jobs[key] = [(page, path, digest, origin) for page, (path, digest, origin) in sorted(pages.items())]
    log(f"evidence: {len(entries)} admitted Indexes; network requests {fetch_api.count + fetch_ia.count + fetch_render.count}")
    flat = [(key, page, path, digest, origin) for key, items in jobs.items() for page, path, digest, origin in items]
    with Pool(args.workers) as pool:
        results = pool.map(check_page_render, [(str(path), digest, str(args.work_dir / "ocr")) for _, _, path, digest, _ in flat])
    by_key: dict[str, list[dict[str, Any]]] = {}
    origins: dict[str, Counter] = {}
    for (key, page, _, digest, origin), result in zip(flat, results):
        by_key.setdefault(key, []).append({"scan_page": page, "render_sha256": digest, **result})
        origins.setdefault(key, Counter())[origin.split(" http")[0]] += 1
    for key in jobs:
        if by_key.get(key):
            source = ", ".join(f"{n} from {o}" for o, n in sorted(origins[key].items()))
            entries[key]["google_hygiene"] = wikisource_hygiene_record(by_key[key], render_source=source)
    payload = {
        "schema_version": EVIDENCE_SCHEMA,
        "checked_at": args.checked_at,
        "user_agent": USER_AGENT,
        "inventory_checked_at": inventory.get("checked_at"),
        "hygiene_skipped_indexes": sorted(skip),
        "indexes": [entries[key] for key in sorted(entries)],
    }
    return payload


# --- back-fill ----------------------------------------------------------------------------------------------------


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.name


def backfill(inventory: Mapping[str, Any], evidence: Mapping[str, Any], *, as_of: dt.date,
             inputs: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Every admitted Index's justification (or rejection), with the counts."""

    by_key = {entry["index_key"]: entry for entry in evidence.get("indexes") or []}
    items = []
    for index in sorted(inventory.get("indexes") or [], key=lambda i: i["index_key"]):
        if not (index.get("gate") or {}).get("admitted"):
            continue
        result = build_wikisource_rights_justification(index, by_key.get(index["index_key"]), as_of=as_of)
        items.append({
            "index_key": justification_key(index),
            "commons_file": index["commons_file"]["title"],
            "commons_file_sha1": index["commons_file"]["sha1"],
            "accepted": result.accepted,
            "reason": result.reason,
            "failures": result.failures,
            "rights_justification": result.record,
        })
    return {
        "schema_version": REGISTRY_SCHEMA,
        "generator": GENERATOR,
        "as_of": as_of.isoformat(),
        "inputs": dict(inputs or {}),
        "counts": counts(items),
        "items": items,
    }


def counts(items: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    items = list(items)
    accepted = [i["rights_justification"] for i in items if i["accepted"]]
    hygiene = Counter(
        "record" if isinstance(r["hygiene"], Mapping) else str(r["hygiene"]) for r in accepted
    )
    return {
        "admitted_indexes": len(items),
        "accepted": len(accepted),
        "rejected": len(items) - len(accepted),
        "by_reason": dict(sorted(Counter(i["reason"] for i in items).items())),
        "by_digitizer": dict(sorted(Counter(r["digitizer"]["name"] for r in accepted).items())),
        "by_digitizer_kind": dict(sorted(Counter(r["digitizer"]["kind"] for r in accepted).items())),
        "by_google_status": dict(sorted(Counter(r["digitizer"]["google"]["status"] for r in accepted).items())),
        "by_israel_basis": dict(sorted(Counter(r["work_public_domain"]["israel_status"]["basis"] for r in accepted).items())),
        "by_us_status": dict(sorted(Counter(r["work_public_domain"]["us_status"]["status"] for r in accepted).items())),
        "by_file_repository": dict(sorted(Counter(r["route"]["file_repository"] for r in accepted).items())),
        "hygiene": dict(sorted(hygiene.items())),
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ev = sub.add_parser("evidence", help="Operator-only: gather the rights evidence and run the Google hygiene pass.")
    ev.add_argument("--inventory", type=Path, default=ROOT / "docs" / "wikisource_index_inventory.json")
    ev.add_argument("--full-inventory", type=Path, required=True, help="The operator wikisource_inventory.json.")
    ev.add_argument("--api-cache", type=Path, required=True, help="The inventory's raw MediaWiki API cache.")
    ev.add_argument("--ia-metadata", type=Path, help="Cached IA metadata, keyed by anything ({key: metadata}).")
    ev.add_argument("--snapshot", type=Path, help="A tranche Wikisource snapshot (pages.jsonl and assets/).")
    ev.add_argument("--render-cache", type=Path, action="append", help="Folders with renders.jsonl and <slug>.jpg.")
    ev.add_argument("--work-dir", type=Path, required=True, help="Operator folder for downloads and OCR, outside the repo.")
    ev.add_argument("--skip-index", action="append", help="Index kept out of the image pass (e.g. evaluation pages).")
    ev.add_argument("--fetch", action="store_true", help="Fetch what the caches lack (1 request/s).")
    ev.add_argument("--workers", type=int, default=6)
    ev.add_argument("--checked-at", required=True)
    ev.add_argument("--out", type=Path, default=EVIDENCE_PATH)
    bf = sub.add_parser("backfill", help="Write the justification of every admitted Index (network-free).")
    bf.add_argument("--inventory", type=Path, default=ROOT / "docs" / "wikisource_index_inventory.json")
    bf.add_argument("--evidence", type=Path, default=EVIDENCE_PATH)
    bf.add_argument("--as-of", type=dt.date.fromisoformat, required=True)
    bf.add_argument("--out", type=Path, default=REGISTRY_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "evidence":  # pragma: no cover - operator
        write_json(args.out, gather_evidence(args))
        return 0
    inventory_bytes = args.inventory.read_bytes()
    evidence_bytes = args.evidence.read_bytes()
    payload = backfill(
        json.loads(inventory_bytes), json.loads(evidence_bytes), as_of=args.as_of,
        inputs={"inventory": {"path": _relative(args.inventory), "sha256": _sha256_bytes(inventory_bytes)},
                "evidence": {"path": _relative(args.evidence), "sha256": _sha256_bytes(evidence_bytes)}},
    )
    write_json(args.out, payload)
    print(json.dumps(payload["counts"], ensure_ascii=False, indent=1))
    for item in payload["items"]:
        if not item["accepted"]:
            print(f"rejected {item['index_key']} ({item['commons_file']}): {', '.join(item['failures'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
