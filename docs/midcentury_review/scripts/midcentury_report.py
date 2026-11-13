"""Mid-century report from a midcentury_score.sh run directory (heocr-eval): report.md + report.json in RUN_DIR.

Headline numbers are evaluate-references' line_matched.v1 view (order-independent: every reference is
reading_order_verified within_line), node printed/new_printed, slice ALL / excluding_pointed, profile primary.v1,
with the cluster-bootstrap interval over units. Run from tasks/:  python3 eval-domains/scripts/midcentury_report.py RUN_DIR
"""
import json, sys
from pathlib import Path

NODE = "printed/new_printed"
CAVEATS = [
    "R8b (frozen main-fold, traineddata sha256 8cb22dbe...): rechecked 2026-11-13 with the widened mid-century target. "
    "116 of its 196,275 train_main lines share word 6-grams with the mid-century pages. 33 of 298 pages hold any "
    "training 6-gram, all under 30% of their lines; per-page shares are in outputs/r8b_overlap_exposure_v1.json. Which "
    "pages leave R8b's scored set (labels exposed: R8b) is decided with lead before scoring.",
    "Claude is a multimodal LLM, not an engine. Its readings are a yardstick for Claude-made training labels; they are "
    "never references, never hints on pass 2, and never published as a model score.",
    "A pre-fill line a reading skipped is charged, never filled from the pre-fill (claude_coverage.json: "
    "unread_prefill_lines).",
    "The 15 readings seeded from the pre-fill are replaced by their image-only re-reads; pages without either are left out.",
    "Pass-1 Claude scores are optimistic (the human checked where Claude flagged); the primary yardstick is pass 2.",
    "Internal scoring set: plenary lines are not private-name gated here. A published reference export must run "
    "plenary_private_names_v1 first; gated-out lines leave the published figure, which then reports the drop count.",
]


def headline(report, slice_key=("ALL", "excluding_pointed")):
    view = report["reference_views"]["adjudicated_reference"]["line_matched.v1"]["views"]["line_matched.v1"]
    sl = view["eval_slices"]["slices"][NODE]
    out = {}
    for name, s in [("ALL", sl["ALL"])] + [(k, v) for k, v in sl.items() if k.startswith("genre=")]:
        x = s.get(slice_key[1])
        if not x:
            continue
        p = x["profiles"]["primary.v1"]; c = x["profiles"].get("consonantal.v1", {})
        la = p.get("line_aligned", {})
        out[name] = {"items": x["items"], "clusters": x["clusters"], "flags": x.get("flags", []),
                     "cer_pct": round(100 * p["cer"], 3), "cer_ci_pct": [round(100 * v, 3) for v in p["cer_ci"]] if p.get("cer_ci") else None,
                     "wer_pct": round(100 * p["wer"], 3), "consonantal_cer_pct": round(100 * c["cer"], 3) if c else None,
                     "exact_line_rate": la.get("exact_line_rate"), "missed_line_rate": la.get("missed_line_rate"),
                     "page_cer_median_pct": round(100 * p["page_cer_distribution"]["median"], 3),
                     "page_cer_p90_pct": round(100 * p["page_cer_distribution"]["p90"], 3)}
    return out


def delta(report):
    d = report.get("comparison", {}).get("reference_view_deltas", {}).get("adjudicated_reference", {})
    try:
        x = d["line_matched.v1"]["line_matched.v1"]["eval_slices"]["slices"][NODE]["ALL"]["excluding_pointed"]["profiles"]["primary.v1"]
    except KeyError:
        return None
    return {k: x.get(k) for k in ("delta_cer", "delta_cer_ci", "cer_separated") if k in x}


def main(run):
    run = Path(run); summary = json.load(open(run / "sets/summary.json"))
    res = {"synthetic": summary["synthetic"], "counts": summary["counts"], "quota_short": {k: v for k, v in summary["quota"].items() if v["short"]},
           "excluded": summary["excluded"], "reference_error_page_order": summary["reference_error"], "caveats": CAVEATS, "runs": {}}
    for f in sorted(run.glob("eval_*.json")):
        r = json.load(open(f)); res["runs"][f.stem[5:]] = {"headline": headline(r), "vs_stock": delta(r)}
    res["exposure"] = {}
    for s in ("pass1", "pass2"):
        f = run / "sets" / s / "exposure.json"
        if f.exists():
            e = json.load(open(f))
            res["exposure"][s] = {"rule": e["rule"], "items": e["items"], "zero_exposure": e["zero_exposure"],
                                  "exposed_pages": sorted(e["exposed"]), "n_per_stratum": e["n_per_stratum"]}
    co = json.load(open(run / "coincidence.json")) if (run / "coincidence.json").exists() else None
    res["coincidence"] = co
    cov = json.load(open(run / "claude/claude_coverage.json"))
    res["claude_coverage"] = {k: cov[k] for k in ("pages_with_reading", "image_only_rereads", "unread_prefill_lines", "seeded_dropped")}
    json.dump(res, open(run / "report.json", "w"), ensure_ascii=False, indent=1)
    L = [f"# Mid-century scores{' (SYNTHETIC FIXTURE)' if res['synthetic'] else ''}", "",
         f"Node {NODE}, line_matched.v1, primary.v1, 95% unit-cluster bootstrap (2,000, seed 0). Counts: {res['counts']}.", ""]
    for name, x in res["runs"].items():
        L.append(f"## {name}")
        for sl, h in x["headline"].items():
            L.append(f"- {sl}: CER {h['cer_pct']}% {h['cer_ci_pct']}, WER {h['wer_pct']}%, consonantal {h['consonantal_cer_pct']}%, "
                     f"exact lines {h['exact_line_rate']}, missed lines {h['missed_line_rate']}, page median/p90 "
                     f"{h['page_cer_median_pct']}/{h['page_cer_p90_pct']}%; {h['items']} pages, {h['clusters']} units {h['flags'] or ''}")
        if x["vs_stock"]:
            L.append(f"- vs stock Tesseract: {x['vs_stock']}")
        L.append("")
    e = res["reference_error_page_order"]
    L += ["## Blind-pass reference error (page order, primary.v1; threshold 0.3%)",
          *(f"- {k}: {e[k]}" for k in ("all", "hints_shown", "no_hints")), "",
          f"Quota shortfalls: {res['quota_short'] or 'none'}", f"Excluded: {len(res['excluded'])}", "",
          "## Zero-exposure rule (primary = zero-exposure pages; secondary = full set)",
          *(f"- {s}: {x['zero_exposure']} of {x['items']} pages zero-exposure; exposed: {', '.join(x['exposed_pages']) or 'none'}"
            for s, x in res["exposure"].items()),
          *(f"  - {st}: full {v['full']}, zero-exposure {v['zero_exposure']}"
            for s, x in res["exposure"].items() if s == "pass1" for st, v in x["n_per_stratum"].items()), "",
          "## Error coincidence (per reader batch)", json.dumps(co["batches"] if co else None, ensure_ascii=False), "",
          "## Caveats", *(f"- {c}" for c in CAVEATS), ""]
    (run / "report.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L[:40]))


if __name__ == "__main__":
    main(sys.argv[1])
