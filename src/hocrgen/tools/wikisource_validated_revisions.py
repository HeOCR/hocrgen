"""E2d3b: pin each quality-4 page's wikitext *as of its validating revision* (operator-only).

A Wikisource quality-4 page whose text changed after validation is not adjudication-eligible as it stands
(maintainer decision 2): the later edits were never validated. Its text at the validating revision, the one at
which the second editor set quality 4, is exactly what the two named editors attested (team-lead decision, E2d3b).
This tool pins that text beside a snapshot, without touching the snapshot:

- for every page of the snapshot that passes the page gates and is rejected only as
  ``text_changed_after_validation``, it reads the page's revision history (the inventory's own query, so a
  cached inventory run answers it; ``--cache-only`` refuses anything else), takes the validating revision's
  wikitext and writes it to ``OUT/wikitext/<slug>.validated.wikitext.txt``;
- it checks that the faithful conversion of that wikitext has the checksum the inventory recorded for the
  validating revision (``quality_set_text_sha256``), so the pin is the attested text;
- it writes ``OUT/validated_revisions.json`` (``wikisource_validated_revisions.v1``): per page, the validating and
  latest revision ids, the wikitext path and SHA-256, and the converted text's SHA-256.

The text is CC BY-SA 4.0 Wikisource text: the output stays operator-only. Which of these texts may be scored is
decided per page by a visual check (``docs/wikisource_validated_text_checks.json``), read by
``wikisource_eval_references --validated-revisions``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.wikisource import (
    load_wikisource_snapshot,
    page_attestation,
    page_exclusion_reasons,
    page_transclusions,
    validated_revision_attestation,
    validating_revision,
)
from hocrgen.parsers.wikitext import WIKITEXT_NORMALIZATION_VERSION, convert_wikitext

SCHEMA = "wikisource_validated_revisions.v1"
SOURCE_ID = "wikisource_he_proofread"
RevisionFetch = Callable[[str], list[dict[str, Any]]]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def candidate_pages(root: Path) -> list[dict[str, Any]]:
    """Pages that pass every page gate and fail adjudication only because their text changed after validation."""

    _, indexes, pages = load_wikisource_snapshot(root)
    return [page for page in sorted(pages, key=lambda record: record["source_item_id"])
            if not page_exclusion_reasons(page, indexes, root)
            and page_attestation(page)["adjudication_ineligible_reason"] == "text_changed_after_validation"
            and validated_revision_attestation(page)["adjudication_eligible"]]


def validated_revision_record(page: dict[str, Any], revisions: list[dict[str, Any]], root: Path, out: Path) -> dict[str, Any]:
    """Pin one page's validating-revision wikitext under ``out`` and return its record; raises on a mismatch."""

    validator = validating_revision(page)
    if validator is None:
        raise StageExecutionError(f"{page['source_item_id']} has no validating revision")
    match = [revision for revision in revisions if revision.get("revid") == validator["revision_id"]]
    if not match:
        raise StageExecutionError(f"{page['source_item_id']}: validating revision {validator['revision_id']} not in its history")
    wikitext = str(match[0]["slots"]["main"].get("content", ""))
    converted = convert_wikitext(wikitext, page_transclusions(page, root)).text
    if _sha256(converted) != page.get("quality_set_text_sha256"):
        raise StageExecutionError(f"{page['source_item_id']}: the validating revision's text does not match the "
                                  "checksum the inventory recorded for it")
    path = f"wikitext/{page['source_item_id']}.validated.wikitext.txt"
    (out / path).parent.mkdir(parents=True, exist_ok=True)
    (out / path).write_text(wikitext, encoding="utf-8")
    return {
        "item_id": f"{SOURCE_ID}:{page['source_item_id']}",
        "source_item_id": page["source_item_id"],
        "page_title": page["page_title"],
        "latest_revision_id": page["revision_id"],
        "validating_revision_id": validator["revision_id"],
        "validating_revision_timestamp": validator["timestamp"],
        "wikitext_path": path,
        "wikitext_sha256": _sha256(wikitext),
        "converted_text_sha256": _sha256(converted),
        "text_changing_edits_after_validation": len(page_attestation(page)["text_changing_edits_after_quality_set"]),
    }


def write_validated_revisions(root: Path, out: Path, revisions_of: RevisionFetch) -> dict[str, Any]:
    """Pin the validating revision of every candidate page of ``root`` under ``out``; returns the summary."""

    if out.exists() and any(out.iterdir()):
        raise StageExecutionError(f"{out.name} must be new or empty")
    out.mkdir(parents=True, exist_ok=True)
    items = [validated_revision_record(page, revisions_of(page["page_title"]), root, out) for page in candidate_pages(root)]
    summary = {"schema_version": SCHEMA, "source_id": SOURCE_ID, "text_normalization": WIKITEXT_NORMALIZATION_VERSION,
               "operator_only": True, "items": items}
    (out / "validated_revisions.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def load_validated_revisions(out: Path) -> dict[str, dict[str, Any]]:
    """Item id -> record with its pinned ``wikitext``, checked against the recorded SHA-256."""

    payload = json.loads((out / "validated_revisions.json").read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA:
        raise StageExecutionError(f"validated_revisions.json must be {SCHEMA}")
    records = {}
    for item in payload.get("items") or []:
        wikitext = (out / item["wikitext_path"]).read_text(encoding="utf-8")
        if _sha256(wikitext) != item["wikitext_sha256"]:
            raise StageExecutionError(f"validated wikitext checksum mismatch for {item['item_id']}")
        records[item["item_id"]] = {**item, "wikitext": wikitext}
    return records


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("snapshot_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--raw-cache", type=Path, required=True, help="The inventory's raw API cache (wikisource_inventory --work-dir/raw)")
    parser.add_argument("--cache-only", action="store_true", help="Refuse any request the cache cannot answer")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between uncached API requests")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - operator path over the API cache
    from hocrgen.tools.wikisource_inventory import MediaWikiClient, fetch_page_revisions

    args = parse_args(argv)

    class _CacheOnly(MediaWikiClient):
        def _request(self, api: str, body: dict[str, str]) -> dict[str, Any]:
            raise StageExecutionError(f"uncached request refused (--cache-only): {api}")

    client = (_CacheOnly if args.cache_only else MediaWikiClient)(args.raw_cache, delay=args.delay)
    summary = write_validated_revisions(args.snapshot_root, args.output_dir, lambda title: fetch_page_revisions(client, title)[0])
    print(json.dumps({"pages": len(summary["items"]), "api_requests": client.requests}))  # counts only, never text
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
