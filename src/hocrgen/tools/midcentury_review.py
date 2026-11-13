"""Mid-century page review: heocr-review decisions -> scored reference sets for ``evaluate-references`` (heocr-eval).

The maintainer reviews whole pages of the mid-century new-printed batch in heocr-review (page_review task). The app
exports ``page_review_decisions.v0``. This tool validates that export against the batch manifest the app was loaded
from (``heocr_midcentury_batch.v0``, manifest_version v1) and its blind pre-fill sidecar. It then writes reference
sets in hocrgen's own formats, so scoring is the unchanged ``evaluate-references``: per-node eval_slices, cluster
bootstrap, line_matched.v1 pairing and page distributions (decisions 0017, 0018).

Subcommands:

- ``check`` validates an export. Nothing is written.
- ``build`` validates, then writes into ``--out``:

  - ``pass1/`` holds every confirmed first-pass page, test or opened reserve. A rejected page, or a page listed in
    ``KNOWN_BAD``, is excluded with its reason. The app opens the replacement reserve on a reject.
  - ``pass2/`` holds the blind second-pass references.
  - ``pass1_on_pass2/`` holds the blind pages' first-pass references, written as predictions. Scored against
    ``pass2/``, they give the set's measured reference error.

  Each set directory holds ``reference_manifest.json``, ``references/``, ``eval_labels.json``, ``clusters.json``,
  ``asset_index.json`` and ``items.txt``. Every reference is ``reading_order_verified: within_line``: its lines are
  printed lines, typed one per printed line, margin notes included, so pages are scored order-independently.
  ``summary.json`` holds counts, exclusions, the stratum quota check and the reference error split by hints shown.
- ``claude-predictions`` writes Claude's saved page readings (``ai_readings/``) as ``heocr_engine_prediction.v1``
  files, labelled "Claude (multimodal LLM), not an engine", track proprietary. They feed the yardstick only; they are
  never references and never shown. The 15 readings seeded from the pre-fill are replaced by their image-only re-reads
  (``pages_v1r/``) or dropped. Readings cover only pre-fill lines with 4+ Hebrew letters, so two variants are written:

  - ``claude_only`` charges the lines Claude did not read;
  - ``with_prefill_short`` fills those lines from the pre-fill the reading was made on.

  The command also writes ``items.txt``, the pages that have a reading.
- ``subset`` copies a set directory restricted to ``items.txt`` (for prediction sets that cover only some pages).
- ``coincidence`` is the error-coincidence test per reader batch, on first-pass references. Among pre-fill lines the
  reviewer edited (pre-fill wrong), it reports the share where Claude's reading equals the wrong pre-fill
  (primary.v1). An independent reader rarely repeats a pre-fill error exactly; a seeded reader does.

Reference text is as typed: NFC, bidi controls stripped. All other folding happens at scoring. The tool refuses to
write a real-looking set from an export holding the synthetic pseudonym ``rv_00000000`` unless ``--synthetic-fixture``
is given, which stamps every output ``synthetic: true``. Agents are never reviewers: ``checked_by`` must be
``human``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from hocrgen.evaluation import levenshtein_distance
from hocrgen.reference_evaluation import NORMALIZATION_PROFILES

DECISIONS_SCHEMA = "page_review_decisions.v0"
BATCH_ID = "newprinted_midcentury_v0"
SYNTHETIC_REVIEWER = "rv_00000000"
BIDI = re.compile("[\u200e\u200f\u061c\u202a-\u202e\u2066-\u2069]")
LINE_ACTIONS = {"correct", "edit", "print_has_niqqud", "not_on_page", "unreadable", "merge", "split", "added"}
EXCLUDED_ACTIONS = {"not_on_page", "unreadable"}
REQUIRED = ["decision_id", "batch_id", "unit_id", "page", "image_sha256", "prefill_source", "prefill_sha256", "reviewer",
            "pass", "blind_second_pass", "page_action", "reading_order_verified", "lines", "decided_at",
            "first_decided_at", "checked_by"]
GENRE = {"plenary": "parliamentary", "sefer_hachukim": "laws_government", "kovetz_hatakanot": "laws_government"}
# Batch v1 pages whose pre-fill or image is defective (REVIEW_BATCH_SPEC.md, "known bad pages"). Never scored, whatever
# the decision; the maintainer rejects them in the app, which opens their reserve.
KNOWN_BAD = {
    ("reshumot_scanned:kovetz_hatakanot_11", 11): "stamp sheet (no instrument text); reserve 311#p9",
    ("reshumot_scanned:sefer_hachukim_1057", 20): "pre-fill holds the same layer twice (PDF p12 = p20); reserve 1142#p7",
}
# Readings whose reader seeded lines from the pre-fill (lead, 2026-11-12): yardstick uses their image-only re-reads only.
SEEDED = frozenset({
    "plenary:K6_188#p11", "plenary:K12_329#p9", "plenary:K12_250#p23", "plenary:K4_221#p2", "plenary:K6_356#p34",
    "plenary:K8_386#p22", "plenary:K9_361#p36", "plenary:K5_502#p30", "plenary:K12_176#p50", "plenary:K12_225#p19",
    "plenary:K2_610#p10", "plenary:K12_118#p2", "plenary:K2_610#p2", "plenary:K8_386#p13",
    "reshumot_scanned:sefer_hachukim_1461#p5",
})
CLAUDE_ENGINE = "claude (multimodal LLM), not an engine"
SCORING_POLICY = {"uncertain": "include_primary_and_report", "illegible": "exclude_primary",
                  "damaged": "include_readable_and_report", "deleted": "exclude_primary",
                  "marginal": "include_when_ordered_else_separate"}
PRIMARY = NORMALIZATION_PROFILES["primary.v1"]


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


def clean(text: str | None) -> str | None:
    return None if text is None else BIDI.sub("", unicodedata.normalize("NFC", text))


def page_key(unit_id: str, page: int) -> str:
    return f"{unit_id}#p{page}"


def item_id(unit_id: str, page: int) -> str:
    return f"midcentury:{page_key(unit_id, page)}"


def safe(key: str) -> str:
    return key.replace(":", "_").replace("#", "_")


def _load(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


# --- validation ---------------------------------------------------------------------------------------------------

def check(records: list[Mapping[str, Any]], manifest: Mapping[str, Any], blind: Mapping[str, Any]) -> tuple[list[str], list[str]]:
    """Every problem in an export (empty: valid), and flags that do not fail it."""
    pages = {(p["unit_id"], p["page"]): p for p in manifest["pages"]}
    blinds = {(p["unit_id"], p["page"]): p for p in blind["pages"]}
    errors: list[str] = []
    flags: list[str] = []
    if blind.get("manifest_sha256") is None:
        errors.append("blind pre-fill does not name the manifest it was built on")
    first = {(r["unit_id"], r["page"], r["reviewer"]): r for r in records if r.get("pass") == 1 and "reviewer" in r}
    seen: Counter = Counter()
    for r in records:
        did = r.get("decision_id", "?")

        def err(message: str, did: str = did) -> None:
            errors.append(f"{did}: {message}")

        missing = [k for k in REQUIRED if k not in r]
        if missing:
            err(f"missing fields {missing}")
            continue
        seen[did] += 1
        key = (r["unit_id"], r["page"])
        m = pages.get(key)
        if r["batch_id"] != BATCH_ID:
            err("batch_id")
        if r["checked_by"] != "human":
            err("checked_by must be human")
        expected = f"decision:{page_key(*key)}{'@pass2' if r['pass'] == 2 else ''}:{r['reviewer']}"
        if did != expected:
            err(f"decision_id should be {expected}")
        if not m:
            err("unit/page not in manifest")
            continue
        if r["image_sha256"] != m["image_sha256"]:
            err("image_sha256 mismatch")
        if r["pass"] == 1:
            shown, source = m["prefill"], m["prefill_source"]
        elif r["pass"] == 2:
            if not (m.get("blind_second_pass") and r["blind_second_pass"]) or key not in blinds:
                err("pass 2 on a non-blind page")
                continue
            b = blinds[key]
            shown, source = b["blind_prefill"], b["blind_prefill_source"]
            q = first.get((*key, r["reviewer"]))
            if not q:
                err("pass 2 without the same reviewer's pass 1")
            elif _ts(r["decided_at"]) < _ts(q["first_decided_at"]) + timedelta(hours=24):
                err("pass 2 < 24 h after pass 1")
            if q and q.get("revised_after_pass2"):
                if "pass1_at_pass2" not in q:
                    err("revised_after_pass2 without pass1_at_pass2")
                flags.append(f"{did}: pass 1 revised after pass 2; compared with pass1_at_pass2")
        else:
            err("pass must be 1 or 2")
            continue
        if r["prefill_sha256"] != sha_text(shown):
            err("prefill_sha256 does not match the pre-fill shown")
        if r["prefill_source"] != source:
            err("prefill_source mismatch")
        n_lines = len(shown.splitlines())
        for k in ("ai_flagged_i", "ai_missing_near_i"):
            v = r.get(k)
            if v is None:
                continue
            if r["pass"] == 2:
                err(f"{k} must be null on pass 2")
            if not (isinstance(v, list) and all(isinstance(i, int) and 0 <= i < n_lines for i in v) and len(set(v)) == len(v)):
                err(f"{k} must be null or distinct pre-fill line indices")
        if r["page_action"] == "reject":
            if r["lines"] or not r.get("reject_reason"):
                err("reject needs lines [] and reject_reason")
            continue
        if r["page_action"] != "confirm":
            err("page_action")
            continue
        if m.get("reading_order_check") and r["reading_order_verified"] is None:
            err("reading_order_verified required")
        errors.extend(f"{did}: {e}" for e in _line_problems(r["lines"], shown))
    errors.extend(f"{d}: decision_id appears {n} times" for d, n in seen.items() if n > 1)
    return errors, flags


def _line_problems(lines: list[Mapping[str, Any]], shown: str) -> list[str]:
    out: list[str] = []
    cover: dict[int, list[int]] = {}
    for j, ln in enumerate(lines):
        a = ln.get("action")
        if a not in LINE_ACTIONS:
            out.append(f"line {j}: action {a}")
            continue
        src = ln.get("i_src", [])
        if a == "added" and src:
            out.append(f"line {j}: added with i_src")
        if a != "added" and not src:
            out.append(f"line {j}: no i_src")
        if a == "merge" and src and src != list(range(src[0], src[0] + len(src))):
            out.append(f"line {j}: merge not consecutive")
        if a in EXCLUDED_ACTIONS and ln.get("text") is not None:
            out.append(f"line {j}: text must be null")
        if a not in EXCLUDED_ACTIONS and not (ln.get("text") or "").strip():
            out.append(f"line {j}: empty text")
        views = ["consonantal"] if a == "print_has_niqqud" else ["primary", "consonantal"]
        if ln.get("reference_views") != views:
            out.append(f"line {j}: reference_views should be {views}")
        for i in src:
            cover.setdefault(i, []).append(j)
    want = {i for i, t in enumerate(shown.splitlines()) if t.strip()}
    if set(cover) != want:
        out.append(f"i_src coverage: missing {sorted(want - set(cover))[:8]}, unknown {sorted(set(cover) - want)[:8]}")
    for i, js in cover.items():
        if len(js) > 1 and not (all(lines[j]["action"] == "split" for j in js) and js == list(range(js[0], js[0] + len(js)))):
            out.append(f"pre-fill line {i} covered by several records that are not one consecutive split")
    return out


def _validated(decisions: Mapping[str, Any], manifest: Mapping[str, Any], blind: Mapping[str, Any]) -> list[dict]:
    if decisions.get("schema_version") != DECISIONS_SCHEMA:
        raise SystemExit(f"schema_version must be {DECISIONS_SCHEMA}")
    if manifest.get("manifest_version") != "v1":
        raise SystemExit("batch manifest must be manifest_version v1")
    records = list(decisions["decisions"])
    errors, flags = check(records, manifest, blind)
    for f in flags:
        print("FLAG", f)
    if errors:
        for e in errors[:50]:
            print("ERROR", e)
        raise SystemExit(f"{len(errors)} problems; nothing written")
    return records


# --- reference sets -----------------------------------------------------------------------------------------------

def _niqqud(lines: list[Mapping[str, Any]]) -> str:
    pointed = sum(ln["action"] == "print_has_niqqud" for ln in lines)
    return "pointed" if pointed and pointed * 2 >= len(lines) else "light" if pointed else "unpointed"


def _reference_lines(record: Mapping[str, Any]) -> list[dict]:
    return [ln for ln in record["lines"] if ln["action"] not in EXCLUDED_ACTIONS]


def _page_text(lines: Iterable[Mapping[str, Any]]) -> str:
    return "\n".join(clean(ln["text"]) for ln in lines)


class _Set:
    """One reference set directory in evaluate-references' formats."""

    def __init__(self, name: str, *, synthetic: bool):
        self.name, self.synthetic = name, synthetic
        self.items: list[dict] = []
        self.refs: dict[str, dict] = {}
        self.labels: dict[str, dict] = {}
        self.clusters: dict[str, str] = {}
        self.assets: list[dict] = []

    def add(self, page: Mapping[str, Any], record: Mapping[str, Any]) -> None:
        unit, number = page["unit_id"], page["page"]
        iid, sid = item_id(unit, number), unit.split(":")[0]
        lines = _reference_lines(record)
        path = f"references/{safe(page_key(unit, number))}/transcription.json"
        self.refs[path] = {
            "schema_version": "benchmark_transcription_reference.v1", "item_id": iid, "source_id": sid,
            "source_item_id": page_key(unit, number), "normalization": {"unicode": "NFC", "text_order": "logical"},
            "language_scripts": [{"language": "he", "script": "Hebr", "direction": "rtl"}],
            "scoring_policy": SCORING_POLICY, "pages": [{"page_id": "page-1", "reading_order": 1, "text": _page_text(lines)}],
            "lines": [{"line_id": f"line-{k}", "page_id": "page-1", "reading_order": k, "text": clean(ln["text"]),
                       "layout_line_id": None} for k, ln in enumerate(lines, start=1)],
            "spans": [], "review": {"status": "adjudicated", "reviewers": [record["reviewer"]],
                                    "adjudicator": record["reviewer"], "adjudicated_at": record["decided_at"]}}
        self.items.append({
            "reference_id": f"{self.name}:{iid}", "item_id": iid, "source_id": sid, "source_item_id": page_key(unit, number),
            "visibility": "hidden_reference", "public_reference_status": "adjudicated",
            "adjudication_status": "adjudicated", "modality": "printed", "reviewers": [record["reviewer"]],
            "transcription_reference": {"path": path, "schema_version": "benchmark_transcription_reference.v1"},
            "reference_normalization": {"reading_order_verified": "within_line"}})
        self.labels[iid] = {"node": page.get("node", "printed/new_printed"),
                            "facets": {"genre": GENRE[page["series"]], "font": None}, "niqqud": _niqqud(lines)}
        self.clusters[iid] = unit
        self.assets.append({"item_id": iid, "page_sha256": [page["image_sha256"]]})

    def write(self, root: Path, provenance: Mapping[str, Any]) -> None:
        d = root / self.name
        if d.exists():
            shutil.rmtree(d)
        for path, ref in self.refs.items():
            text = json.dumps(ref, ensure_ascii=False, indent=1) + "\n"
            (d / path).parent.mkdir(parents=True, exist_ok=True)
            (d / path).write_text(text, encoding="utf-8")
            item = next(i for i in self.items if i["transcription_reference"]["path"] == path)
            item["transcription_reference"]["sha256"] = sha_text(text)
        _dump(d / "reference_manifest.json", {
            "schema_version": "benchmark_reference_manifest.v1",
            "benchmark_id": f"heocr_midcentury_{self.name}" + ("_synthetic" if self.synthetic else ""),
            "reference_manifest_id": f"midcentury_review_{self.name}",
            "reference_contracts": {"transcription": "benchmark_transcription_reference.v1",
                                    "layout": "benchmark_layout_reference.v1"},
            "items": sorted(self.items, key=lambda i: i["item_id"])})
        _dump(d / "eval_labels.json", {
            "schema_version": "hocrgen_eval_labels.v1",
            "rule": "node from the batch manifest (decision 0018: printed/new_printed); genre by series; niqqud from the "
                    "reviewer's print_has_niqqud lines (pointed when at least half the lines, light when any)",
            "provenance": {**provenance, "synthetic": self.synthetic}, "labels": dict(sorted(self.labels.items()))})
        _dump(d / "clusters.json", {"schema_version": "hocrgen_bootstrap_clusters.v1", "cluster_key": "unit_id",
                                    "clusters": dict(sorted(self.clusters.items()))})
        _dump(d / "asset_index.json", {"items": sorted(self.assets, key=lambda a: a["item_id"])})
        (d / "items.txt").write_text("".join(f"{i}\n" for i in sorted(self.labels)), encoding="utf-8")


def _prediction(image_sha: str, text: str, *, name: str, version: str, track: str, network: bool) -> dict:
    return {"schema_version": "heocr_engine_prediction.v1", "page_id": f"sha256:{image_sha}", "track": track,
            "input": {"sha256": image_sha}, "engine": {"name": name, "version": version},
            "pipeline": [{"kind": "recognize", "name": name, "version": version, "track": track,
                          "deterministic": not network, "requires_network": network}],
            "text": text, "words": []}


def _cer(prediction: str, reference: str) -> tuple[int, int]:
    p, r = PRIMARY.apply(prediction), PRIMARY.apply(reference)
    return levenshtein_distance(p, r), len(r)


def build(decisions: Mapping[str, Any], manifest: Mapping[str, Any], blind: Mapping[str, Any], out: Path, *,
          synthetic_fixture: bool = False, known_bad: Mapping[tuple[str, int], str] = KNOWN_BAD,
          provenance: Mapping[str, Any] | None = None) -> dict[str, Any]:
    records = _validated(decisions, manifest, blind)
    synthetic = bool(decisions.get("synthetic")) or any(r["reviewer"] == SYNTHETIC_REVIEWER for r in records)
    if synthetic and not synthetic_fixture:
        raise SystemExit(f"refusing to write references: the export holds the synthetic pseudonym {SYNTHETIC_REVIEWER}")
    if synthetic_fixture and not synthetic:
        raise SystemExit("--synthetic-fixture on a real export")
    pages = {(p["unit_id"], p["page"]): p for p in manifest["pages"]}
    reviewers = sorted({r["reviewer"] for r in records})
    by_pass: dict[int, dict[tuple, list[dict]]] = {1: defaultdict(list), 2: defaultdict(list)}
    for r in records:
        by_pass[r["pass"]][(r["unit_id"], r["page"])].append(r)
    if any(len(v) > 1 for p in by_pass.values() for v in p.values()):
        raise SystemExit("more than one reviewer on a page: this tool builds single-reviewer sets only")
    prov = {"decisions_sha256": sha_text(json.dumps(decisions, sort_keys=True, ensure_ascii=False)),
            "manifest_version": manifest.get("manifest_version"), "reviewers": reviewers, **(provenance or {})}
    pass1, pass2, cross = _Set("pass1", synthetic=synthetic), _Set("pass2", synthetic=synthetic), {}
    excluded = []
    for key, (r,) in sorted(by_pass[1].items()):
        page = pages[key]
        if key in known_bad:
            excluded.append({"page": page_key(*key), "role": page["role"], "reason": f"known bad: {known_bad[key]}",
                             "decision": r["page_action"]})
        elif r["page_action"] == "reject":
            excluded.append({"page": page_key(*key), "role": page["role"], "reason": f"rejected: {r['reject_reason']}",
                             "decision": "reject"})
        elif not _reference_lines(r):
            excluded.append({"page": page_key(*key), "role": page["role"], "reason": "confirmed with no reference lines",
                             "decision": "confirm"})
        else:
            pass1.add(page, r)
    error_rows = []
    for key, (r,) in sorted(by_pass[2].items()):
        if r["page_action"] != "confirm" or key in known_bad:
            excluded.append({"page": page_key(*key) + "@pass2", "role": "blind", "decision": r["page_action"],
                             "reason": "known bad" if key in known_bad else f"rejected: {r.get('reject_reason')}"})
            continue
        if not _reference_lines(r):
            excluded.append({"page": page_key(*key) + "@pass2", "role": "blind", "decision": "confirm",
                             "reason": "confirmed with no reference lines"})
            continue
        q = by_pass[1].get(key, [None])[0]
        first = q["pass1_at_pass2"] if q and q.get("revised_after_pass2") else q
        pass2.add(pages[key], r)
        if first and first["page_action"] == "confirm" and _reference_lines(first):
            text = _page_text(_reference_lines(first))
            cross[pages[key]["image_sha256"]] = text
            e, n = _cer(text, _page_text(_reference_lines(r)))
            error_rows.append({"page": page_key(*key), "edits": e, "chars": n, "hints_shown": q.get("ai_flagged_i") is not None,
                               "pass1_revised_after_pass2": bool(q.get("revised_after_pass2"))})
    out.mkdir(parents=True, exist_ok=True)
    pass1.write(out, prov)
    pass2.write(out, prov)
    cd = out / "pass1_on_pass2"
    if cd.exists():
        shutil.rmtree(cd)
    for image_sha, text in cross.items():
        _dump(cd / f"{image_sha}.json", _prediction(image_sha, text, name="pass1-reference", version="maintainer pass 1",
                                                    track="open", network=False))
    summary = {"synthetic": synthetic, "provenance": prov, "counts": {
        "records": len(records), "pass1_scored": len(pass1.items), "pass2_scored": len(pass2.items),
        "pass1_on_pass2_predictions": len(cross), "excluded": len(excluded)},
        "excluded": excluded, "quota": _quota(manifest, pass1), "reference_error": _reference_error(error_rows)}
    _dump(out / "summary.json", summary)
    return summary


def _quota(manifest: Mapping[str, Any], pass1: _Set) -> dict[str, Any]:
    want = Counter(p["stratum"] for p in manifest["pages"] if p["role"] == "test")
    scored_keys = {i["source_item_id"] for i in pass1.items}
    got = Counter(p["stratum"] for p in manifest["pages"] if page_key(p["unit_id"], p["page"]) in scored_keys)
    return {s: {"quota": want[s], "scored": got[s], "short": max(0, want[s] - got[s])} for s in sorted(want)}


def _reference_error(rows: list[dict]) -> dict[str, Any]:
    def agg(rs: list[dict]) -> dict[str, Any]:
        e, n = sum(r["edits"] for r in rs), sum(r["chars"] for r in rs)
        return {"pages": len(rs), "edits": e, "chars": n, "cer_pct": round(100 * e / n, 4) if n else None,
                "meets_0.3pct": (100 * e / n <= 0.3) if n else None}
    return {"profile": "primary.v1", "order": "page order (the line_matched.v1 figure comes from evaluate-references)",
            "all": agg(rows), "hints_shown": agg([r for r in rows if r["hints_shown"]]),
            "no_hints": agg([r for r in rows if not r["hints_shown"]]), "pages": rows}


# --- Claude's readings --------------------------------------------------------------------------------------------

def _reading_text(reading: Mapping[str, Any], prefill: str | None, fill_short: bool) -> str:
    """Claude's page text in pre-fill line order, with its missing-text lines after their near_i line."""
    if reading.get("mode") == "image_only":
        return "\n".join(clean(t) for t in reading["printed_lines"] if t.strip())
    slots: list[tuple[int, int, int, str]] = []
    read = {ln["i"]: ln["text"] for ln in reading["lines"]}
    for i, text in read.items():
        slots.append((i, 0, 0, text))
    if fill_short and prefill is not None:
        for i, text in enumerate(prefill.splitlines()):
            if i not in read and text.strip():
                slots.append((i, 0, 0, text))
    for k, m in enumerate(reading.get("missing", [])):
        slots.append((m["near_i"], 1, k, m["text"]))
    return "\n".join(clean(t) for *_, t in sorted(slots) if t.strip())


def select_readings(readings: Path, manifest: Mapping[str, Any], manifest_v0: Mapping[str, Any]) -> dict[str, dict]:
    """Per page key: the reading the yardstick uses, the pre-fill it was made on, and its reader batch."""
    v0 = {page_key(p["unit_id"], p["page"]): p["prefill"] for p in manifest_v0["pages"]}
    batch_of: dict[tuple[str, str], str] = {}
    for sub in ("batches", "batches_v1"):
        for f in sorted((readings / sub).glob("*.json")):
            for entry in _load(f):
                batch_of[(sub, entry["key"])] = f.stem
    out = {}
    for p in manifest["pages"]:
        key = page_key(p["unit_id"], p["page"])
        name = f"{safe(key)}.json"
        if key in SEEDED:
            f, prefill, batch = readings / "pages_v1r" / name, None, "v1r"
        elif (readings / "pages_v1" / name).exists():
            f, prefill, batch = readings / "pages_v1" / name, p["prefill"], batch_of.get(("batches_v1", key), "v1:?")
        elif v0.get(key) == p["prefill"]:
            f, prefill, batch = readings / "pages" / name, v0[key], batch_of.get(("batches", key), "v0:?")
        else:
            continue
        if f.exists():
            out[key] = {"file": f, "reading": _load(f), "prefill": prefill, "batch": batch, "page": p}
    return out


def claude_predictions(readings: Path, manifest: Mapping[str, Any], manifest_v0: Mapping[str, Any], out: Path) -> dict[str, Any]:
    chosen = select_readings(readings, manifest, manifest_v0)
    for variant in ("claude_only", "with_prefill_short"):
        d = out / variant
        if d.exists():
            shutil.rmtree(d)
        for key, c in chosen.items():
            text = _reading_text(c["reading"], c["prefill"], variant == "with_prefill_short")
            _dump(d / f"{safe(key)}.json", _prediction(c["page"]["image_sha256"], text, name=CLAUDE_ENGINE,
                                                       version=c["reading"].get("reader", "claude"), track="proprietary",
                                                       network=True))
    (out / "items.txt").write_text("".join(f"midcentury:{k}\n" for k in sorted(chosen)), encoding="utf-8")
    report = {"pages_with_reading": len(chosen), "image_only_rereads": sum(c["batch"] == "v1r" for c in chosen.values()),
              "seeded_dropped": sorted(SEEDED - set(chosen)),
              "no_reading": sorted(page_key(p["unit_id"], p["page"]) for p in manifest["pages"]
                                   if page_key(p["unit_id"], p["page"]) not in chosen)}
    _dump(out / "claude_coverage.json", report)
    return report


def subset(src: Path, items_file: Path, out: Path) -> int:
    keep = set(items_file.read_text(encoding="utf-8").split())
    if out.exists():
        shutil.rmtree(out)
    m = _load(src / "reference_manifest.json")
    m["items"] = [i for i in m["items"] if i["item_id"] in keep]
    for i in m["items"]:
        (out / i["transcription_reference"]["path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / i["transcription_reference"]["path"], out / i["transcription_reference"]["path"])
    ids = {i["item_id"] for i in m["items"]}
    m["reference_manifest_id"] = f"{m['reference_manifest_id']}__subset"
    _dump(out / "reference_manifest.json", m)
    labels = _load(src / "eval_labels.json")
    labels["labels"] = {k: v for k, v in labels["labels"].items() if k in ids}
    _dump(out / "eval_labels.json", labels)
    clusters = _load(src / "clusters.json")
    clusters["clusters"] = {k: v for k, v in clusters["clusters"].items() if k in ids}
    _dump(out / "clusters.json", clusters)
    _dump(out / "asset_index.json", {"items": [a for a in _load(src / "asset_index.json")["items"] if a["item_id"] in ids]})
    (out / "items.txt").write_text("".join(f"{i}\n" for i in sorted(ids)), encoding="utf-8")
    return len(ids)


def coincidence(decisions: Mapping[str, Any], manifest: Mapping[str, Any], blind: Mapping[str, Any], readings: Path,
                manifest_v0: Mapping[str, Any]) -> dict[str, Any]:
    """Per reader batch, on pass-1 edits of a single pre-fill line that the reading covers."""
    records = _validated(decisions, manifest, blind)
    chosen = select_readings(readings, manifest, manifest_v0)
    rows: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        key = page_key(r["unit_id"], r["page"])
        c = chosen.get(key)
        if r["pass"] != 1 or r["page_action"] != "confirm" or c is None or c["prefill"] is None \
                or (r["unit_id"], r["page"]) in KNOWN_BAD:
            continue
        if c["prefill"] != manifest_prefill(manifest, r):
            continue  # a v0 reading of a page whose pre-fill v1 changed: indices differ
        shown = c["prefill"].splitlines()
        read = {ln["i"]: ln["text"] for ln in c["reading"]["lines"]}
        for ln in r["lines"]:
            if ln["action"] != "edit" or len(ln["i_src"]) != 1 or ln["i_src"][0] not in read:
                continue
            i = ln["i_src"][0]
            pre, ref, ai = (PRIMARY.apply(clean(t)) for t in (shown[i], ln["text"], read[i]))
            if pre == ref:
                continue
            b = rows[c["batch"]]
            b["prefill_wrong_lines"] += 1
            b["reading_equals_wrong_prefill"] += ai == pre
            b["reading_equals_reference"] += ai == ref
    report = {}
    for batch, b in sorted(rows.items()):
        n = b["prefill_wrong_lines"]
        report[batch] = {**b, "share_equals_wrong_prefill": round(b["reading_equals_wrong_prefill"] / n, 4),
                         "share_equals_reference": round(b["reading_equals_reference"] / n, 4)}
    shares = [v["share_equals_wrong_prefill"] for v in report.values() if v["prefill_wrong_lines"] >= 20]
    if shares:
        med = sorted(shares)[len(shares) // 2]
        for v in report.values():
            v["far_above_others"] = v["prefill_wrong_lines"] >= 20 and v["share_equals_wrong_prefill"] > max(3 * med, med + 0.15)
    return {"profile": "primary.v1", "rule": "a batch far above the others (over 3x the median share, and 15 points "
            "above it, with 20+ lines) is excluded from the yardstick, as the 15 seeded readings were",
            "batches": report}


def manifest_prefill(manifest: Mapping[str, Any], record: Mapping[str, Any]) -> str:
    return next(p["prefill"] for p in manifest["pages"] if p["unit_id"] == record["unit_id"] and p["page"] == record["page"])


# --- CLI ----------------------------------------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m hocrgen.tools.midcentury_review", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "build", "coincidence"):
        p = sub.add_parser(name)
        p.add_argument("decisions", type=Path, help="page_review_decisions.v0 export")
        p.add_argument("--manifest", type=Path, required=True, help="batch_manifest_v1.json")
        p.add_argument("--blind", type=Path, required=True, help="blind_prefill_v1.json")
        if name == "build":
            p.add_argument("--out", type=Path, required=True)
            p.add_argument("--synthetic-fixture", action="store_true")
        if name == "coincidence":
            p.add_argument("--readings", type=Path, required=True)
            p.add_argument("--manifest-v0", type=Path, required=True)
            p.add_argument("--out", type=Path, default=None)
    p = sub.add_parser("claude-predictions")
    p.add_argument("--readings", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--manifest-v0", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p = sub.add_parser("subset")
    p.add_argument("set_dir", type=Path)
    p.add_argument("--items", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse_args(argv)
    if a.command == "check":
        _validated(_load(a.decisions), _load(a.manifest), _load(a.blind))
        print("VALID")
    elif a.command == "build":
        s = build(_load(a.decisions), _load(a.manifest), _load(a.blind), a.out, synthetic_fixture=a.synthetic_fixture)
        print(json.dumps({"counts": s["counts"], "reference_error": s["reference_error"]["all"]}, ensure_ascii=False))
    elif a.command == "claude-predictions":
        r = claude_predictions(a.readings, _load(a.manifest), _load(a.manifest_v0), a.out)
        print(json.dumps({k: r[k] for k in ("pages_with_reading", "image_only_rereads")}))
    elif a.command == "subset":
        print(subset(a.set_dir, a.items, a.out), "items")
    else:
        r = coincidence(_load(a.decisions), _load(a.manifest), _load(a.blind), a.readings, _load(a.manifest_v0))
        if a.out:
            _dump(a.out, r)
        print(json.dumps(r["batches"], ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
