"""Operator capture of a complete span of born-digital Reshumot booklets (ספר החוקים, קובץ התקנות), e.g. 2005.

F8g2's ``real_tranche capture --source reshumot`` samples booklets per Hebrew year and filtered on ``PublishDate``,
which misses the born-digital booklets of 2005 (ספר החוקים from booklet 1976, January 2005; קובץ התקנות from 6395,
30 June 2005; modern-s6-scout report §2.2) because ``PublishDate`` is often empty for ספר החוקים. This tool takes
every listing of a span instead, with the fetcher fixes of the scout's report §7 item 1:

- ``enumerate``: every listing of each (FolderType, BookletYear), complete and order-free: re-paged until the set of
  listings holds ``TotalResults``, transient ``Status: Warn`` empty answers retried with backoff, and years at the
  200-result cap sliced by ``BookletNum`` (``government_print_tranche.reshumot_enumerate_year``).
- ``fetch``: every listed file of the chosen booklet numbers, into a downloads folder of its own (untrusted), keyed by
  (series, booklet number, sha256), so a booklet listed twice (the 2015 rescan and the InDesign original) keeps both.
  Each file's born-digital verdict comes from the PDF itself (``reshumot_pdf_born_digital``, which reuses
  ``reshumot_lines.born_digital_check``), never from ``PublishDate``.
- ``select``: per booklet, the one born-digital file, its publication date and the span filter; writes the capture
  cache's ``booklets.jsonl`` and ``pdf/<series>_<number>.pdf``, which the materializer reads. When the API's
  ``PublishDate`` is empty (most 2005 ספר החוקים listings), the date is the one the cover prints, accepted only when
  it fits the number order of the series' API-dated booklets; the gate then checks it against every inner page's
  running footer. (The Knesset's ``KNS_Law`` holds no primary laws, so it cannot fill the date.)
- ``materialize``: the F8e2 / F8e3 method and the unchanged page gate on every page of the selected booklets, into a
  snapshot of their own (``materialize_reshumot`` with no packaged fixture), plus every page's glyph layer.
- ``outline-table``: the glyph outline identity table for the snapshot: the packaged table unchanged, plus the
  outlines it lacks, from the new layers (``build_glyph_outline_table``; a conflicting new outline stays unresolved).
- ``new-booklets``: the list heocr-eval assigns (series, number, date, pages, sha256; one row per file).

The network subcommands are throttled (at least 1.2 s between requests) with the User-Agent
``HeOCR-research/0.1 (+https://github.com/HeOCR)``. Every command that reads a downloaded PDF runs poppler or
pdfminer.six on it; run this module under ``python -I`` through a runner that puts ``src/`` on ``sys.path``.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from hocrgen.tools import government_print_tranche as gp

COVER_DATE_SOURCE = ("the booklet's cover (gazette API PublishDate empty); within the number order of the series' "
                     "API-dated booklets")
ERA_START = "2004-09-16"  # 1 Tishrei 5765: BookletYear 73 starts here


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] if path.is_file() else []


def parse_ranges(values: Iterable[str]) -> dict[str, tuple[int, int]]:
    """``series:from-to`` arguments as {series: (from, to)}."""

    ranges = {}
    for value in values:
        series, _, span = value.partition(":")
        low, _, high = span.partition("-")
        if series not in {name for name, _ in gp.RESHUMOT_SERIES.values()} or not low.isdigit() or not high.isdigit():
            raise SystemExit(f"bad range {value!r} (series:from-to)")
        ranges[series] = (int(low), int(high))
    return ranges


def listings_in_ranges(listings: Iterable[dict[str, Any]], ranges: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    chosen = []
    for data in listings:
        series = gp.reshumot_series(data)
        number = str(data.get("BookletNum"))
        if series in ranges and number.isdigit() and ranges[series][0] <= int(number) <= ranges[series][1]:
            chosen.append(data)
    return chosen


def select_booklets(files: Sequence[dict[str, Any]], cover_dates: dict[str, str | None], api_dates_by_series: dict[str, dict[str, str]], *, date_from: str,
                    date_to: str, decisions_file: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Per booklet (series, number), the born-digital file, its publication date and whether it is in the span.

    Returns (selected booklets, every booklet with its decision). A booklet is selected when exactly one of its files
    passes the born-digital check and its date (an operator correction, else the API's ``PublishDate`` of that
    listing, else of another listing of the booklet, else the born-digital file's cover date, in number order) lies
    in ``date_from``..``date_to``. ``cover_dates``: sha256 to ``reshumot_cover_date``; ``api_dates_by_series``:
    series to {booklet number: API date} over the whole listing.

    ``decisions_file`` holds the operator's recorded decisions: ``excluded_files`` ({sha256: reason}: a file that is
    not the gazette's print, e.g. a later re-typeset, never counts as the booklet's born-digital file) and
    ``date_corrections`` ({"<series>_<number>": {"date", "evidence"}}: an API date that is a typo). A corrected date
    is still checked by the gate against the page's running footer."""

    decisions_file = decisions_file or {}
    excluded = decisions_file.get("excluded_files") or {}
    corrections = decisions_file.get("date_corrections") or {}
    by_booklet: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in files:
        if row["pdf_sha256"] in excluded:
            row = {**row, "born_digital": {**row["born_digital"], "passed": False,
                                           "reasons": sorted({*row["born_digital"]["reasons"], "operator_excluded"}),
                                           "operator_excluded": excluded[row["pdf_sha256"]]}}
        by_booklet.setdefault((row["series"], row["booklet_number"]), []).append(row)
    selected, decisions = [], []
    for (series, number), group in sorted(by_booklet.items(), key=lambda item: (item[0][0], gp._number_key(item[0][1]))):
        pick, why = gp.reshumot_pick_born_digital_file(group)
        api_dates = sorted({str(row["listing"].get("PublishDate") or "")[:10] for row in group} - {""})
        cover = cover_dates.get(pick["pdf_sha256"]) if pick else None
        cover_fits = bool(cover) and gp.reshumot_date_in_number_order(number, cover, api_dates_by_series.get(series, {}), floor=ERA_START)
        correction = corrections.get(f"{series}_{number}")
        date, source = None, None
        if correction:
            date, source = correction["date"], f"operator correction: {correction['evidence']}"
        elif pick is not None and str(pick["listing"].get("PublishDate") or "")[:10]:
            date, source = str(pick["listing"]["PublishDate"])[:10], "gazette API PublishDate"
        elif len(api_dates) == 1:
            date, source = api_dates[0], "gazette API PublishDate (another listing of the booklet)"
        elif cover_fits:
            date, source = cover, COVER_DATE_SOURCE
        decision = {"series": series, "booklet_number": number, "files": [
            {"pdf_sha256": row["pdf_sha256"], "pages": row["pdf_pages"], "creator": row["creator"], "producer": row["producer"],
             "born_digital": row["born_digital"]["passed"], "reasons": row["born_digital"]["reasons"],
             "listing_pages": row["listing"].get("Pages"), "listing_publish_date": row["listing"].get("PublishDate")}
            for row in group], "born_digital_file": pick["pdf_sha256"] if pick else None, "file_decision": why,
            "publish_date": date, "publish_date_source": source, "api_dates": api_dates,
            "cover_date": cover, "cover_date_in_number_order": cover_fits if cover else None, "operator_excluded_files": {row["pdf_sha256"]: excluded[row["pdf_sha256"]]
                                                            for row in group if row["pdf_sha256"] in excluded}}
        if pick is None:
            decision["selected"], decision["reason"] = False, why
        elif date is None:
            decision["selected"], decision["reason"] = False, "publish_date_unknown"
        elif not date_from <= date <= date_to:
            decision["selected"], decision["reason"] = False, "outside_span"
        else:
            decision["selected"], decision["reason"] = True, "selected"
            data = dict(pick["listing"])
            if not str(data.get("PublishDate") or "")[:10] or correction:
                data["publish_date"], data["publish_date_source"] = date, source
            selected.append({**data, "pdf_sha256": pick["pdf_sha256"], "pdf_bytes": pick["pdf_bytes"],
                             "pdf_file": f"{series}_{number}.pdf", "born_digital_metadata": pick["born_digital"],
                             "files_listed": len(group)})
        decisions.append(decision)
    return selected, decisions


def new_booklet_rows(decisions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """heocr-eval's rows (``split_pmod_units_v2.py``): one per file of every selected booklet; a booklet listed twice
    (rescan and InDesign original) has two rows with the same series and number."""

    rows = []
    for decision in decisions:
        if not decision["selected"]:
            continue
        for file in decision["files"]:
            rows.append({"series": decision["series"], "number": decision["booklet_number"], "date": decision["publish_date"],
                         "date_source": decision["publish_date_source"], "pages": file["pages"], "sha256": file["pdf_sha256"],
                         "born_digital": file["born_digital"],
                         "role": "born_digital_original" if file["pdf_sha256"] == decision["born_digital_file"] else "rescan_or_other"})
    return rows


def merge_outline_tables(base: dict[str, Any], new: dict[str, Any], *, built_from: str) -> dict[str, Any]:
    """The base table with its outlines unchanged, plus the outlines only ``new`` has."""

    merged = {key: value for key, value in base.items() if key != "outlines"}
    outlines = dict(base["outlines"])
    added = {key: value for key, value in new["outlines"].items() if key not in outlines}
    outlines.update(added)
    merged["built_from"] = built_from
    merged["unresolved"] = sum(1 for value in outlines.values() if value.get("char") is None and not value.get("accept") and not value.get("shape"))
    merged["outlines"] = dict(sorted(outlines.items()))
    merged["extends"] = {"base_outlines": len(base["outlines"]), "added_outlines": len(added),
                         "added_unresolved": sum(1 for value in added.values() if value.get("char") is None and not value.get("accept")
                                                 and not value.get("shape")),
                         "added_shape_checked": sum(1 for value in added.values() if value.get("shape"))}
    return merged


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover - operator entry point
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    e = sub.add_parser("enumerate")
    e.add_argument("--cache", type=Path, required=True)
    e.add_argument("--target", action="append", required=True, help="FolderType:BookletYear, e.g. 1:73")
    f = sub.add_parser("fetch")
    f.add_argument("--cache", type=Path, required=True)
    f.add_argument("--downloads", type=Path, required=True, help="a folder of its own for the untrusted PDFs")
    f.add_argument("--range", action="append", required=True, help="series:from-to booklet numbers to fetch")
    s = sub.add_parser("select")
    s.add_argument("--cache", type=Path, required=True)
    s.add_argument("--downloads", type=Path, required=True)
    s.add_argument("--from", dest="date_from", required=True)
    s.add_argument("--to", dest="date_to", required=True)
    s.add_argument("--decisions", type=Path, help="operator decisions JSON (excluded_files, date_corrections)")
    o = sub.add_parser("outline-table")
    o.add_argument("--base", type=Path, required=True)
    o.add_argument("--layers", type=Path, required=True)
    o.add_argument("--out", type=Path, required=True)
    o.add_argument("--built-from", required=True)
    o.add_argument("--checks", type=Path, help="recorded checks of new outlines ({outline: {shape|char, checked_by, ...}})")
    m = sub.add_parser("materialize")
    m.add_argument("--cache", type=Path, required=True)
    m.add_argument("--out-root", type=Path, required=True)
    m.add_argument("--outline-table", type=Path, required=True)
    m.add_argument("--layer-out", type=Path, required=True, help="write every page's glyph layer here (<slug>__pNNNN.json.gz)")
    m.add_argument("--captured-at", required=True)
    m.add_argument("--report", type=Path)
    m.add_argument("--extract-only", action="store_true", help="only extract every page's glyph layer into --layer-out")
    n = sub.add_parser("new-booklets")
    n.add_argument("--cache", type=Path, required=True)
    n.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    root = args.cache / "reshumot" if getattr(args, "cache", None) else Path()
    if args.command == "enumerate":
        client = gp.ThrottledClient(root / "request_log.jsonl")
        targets = [tuple(value.split(":", 1)) for value in args.target]
        gp.enumerate_reshumot_listing(args.cache, client, targets)
        print(f"requests: {client.requests}")
        return 0
    if args.command == "fetch":
        listings = [data for path in sorted((root / "listing").glob("ft*_y*.json"))
                    for data in json.loads(path.read_text(encoding="utf-8"))["listings"]]
        chosen = listings_in_ranges(listings, parse_ranges(args.range))
        client = gp.ThrottledClient(root / "request_log.jsonl")
        rows = gp.fetch_reshumot_files(args.cache, args.downloads, client, chosen)
        print(f"{len(chosen)} listings chosen, {len(rows)} files recorded, requests: {client.requests}")
        return 0
    if args.command == "select":
        files = _rows(root / "files.jsonl")
        covers = {row["pdf_sha256"]: gp.reshumot_cover_date(gp._run(["pdftotext", "-f", "1", "-l", "1", "-layout",
                                                                       str(args.downloads / f"{row['pdf_sha256']}.pdf"), "-"]))
                  for row in files if row["born_digital"]["passed"]}
        api_dates: dict[str, dict[str, str]] = {}
        for path in sorted((root / "listing").glob("ft*_y*.json")):
            for data in json.loads(path.read_text(encoding="utf-8"))["listings"]:
                if str(data.get("PublishDate") or "")[:10]:
                    api_dates.setdefault(gp.reshumot_series(data) or "", {})[str(data["BookletNum"])] = str(data["PublishDate"])[:10]
        operator = json.loads(args.decisions.read_text(encoding="utf-8")) if args.decisions else None
        selected, decisions = select_booklets(files, covers, api_dates, date_from=args.date_from, date_to=args.date_to, decisions_file=operator)
        (root / "pdf").mkdir(parents=True, exist_ok=True)
        for row in selected:
            target = root / "pdf" / row["pdf_file"]
            shutil.copyfile(args.downloads / f"{row['pdf_sha256']}.pdf", target)
            if gp._sha256(target.read_bytes()) != row["pdf_sha256"]:
                raise SystemExit(f"{target}: sha256 differs from the pinned file")
        gp._write(root / "booklets.jsonl", gp._json_lines(selected))
        gp._write(root / "selection.json", json.dumps(decisions, ensure_ascii=False, indent=1).encode("utf-8"))
        reasons: dict[str, int] = {}
        for decision in decisions:
            reasons[decision["reason"]] = reasons.get(decision["reason"], 0) + 1
        print(json.dumps({"booklets": len(decisions), "by_reason": reasons}, ensure_ascii=False))
        return 0
    if args.command == "outline-table":
        layers = [json.loads(gp_read(path)) for path in sorted(args.layers.glob("*.json.gz"))]
        base = json.loads(args.base.read_text(encoding="utf-8"))
        checks = json.loads(args.checks.read_text(encoding="utf-8")) if args.checks else {}
        new = gp.build_glyph_outline_table(layers, checks, built_from=args.built_from)
        merged = merge_outline_tables(base, new, built_from=args.built_from)
        gp._write(args.out, gp.glyph_outline_table_bytes(merged))
        print(json.dumps(merged["extends"]))
        return 0
    if args.command == "materialize":
        from hocrgen.fetchers.government_print import reshumot_entry_exclusion_reasons
        from hocrgen.tools.reshumot_lines import _reshumot_source

        result = gp.materialize_reshumot(
            cache=args.cache, out_root=args.out_root, packaged_root=None, source=_reshumot_source(),
            captured_at=args.captured_at, gate=reshumot_entry_exclusion_reasons, outline_table=args.outline_table,
            layer_cache=None, report=args.report, layer_out=args.layer_out, extract_only=args.extract_only,
            born_digital_from_pdf=True)
        print(json.dumps({key: result[key] for key in result if key not in ("booklets", "by_year")}, ensure_ascii=False))
        return 0
    if args.command == "new-booklets":
        decisions = json.loads((root / "selection.json").read_text(encoding="utf-8"))
        rows = new_booklet_rows(decisions)
        args.out.write_text(json.dumps({"schema": "heocr_reshumot_new_booklets.v1", "booklets": rows}, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(f"{len(rows)} rows, {len({(r['series'], r['number']) for r in rows})} booklets")
        return 0
    return 2


def gp_read(path: Path) -> bytes:  # pragma: no cover - operator entry point
    from hocrgen.fetchers.government_print import read_glyph_layer_bytes

    return read_glyph_layer_bytes(path)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
