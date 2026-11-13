"""Mid-century zero-exposure subset (heocr-eval; lead's rule, pre-registered 2026-11-13 before any review decision).

Rule: the primary mid-century score covers only pages with zero exposure. A page is exposed when any of its reference
lines shares a word 6-gram (logical order) with the train list of any model in the comparison that has one:
- R8b main-fold: r8b-tesseract/data/train_main.list
- R7: r7-tesseract-real/data/bynli/train.list
Stock Tesseract has no list and adds nothing.
There is no threshold: one exposed line makes the page exposed. Every model, the Claude yardstick and stock are scored
on the same subset. The full set is the secondary score, with exposure stated.
Input: a set directory written by `hocrgen.tools.midcentury_review build` (its references, i.e. the reviewed text).
Output into SET_DIR:
- items_zero_exposure.txt
- exposure.json: every page with any exposure, with its exposed lines (counts only, no text), and n per stratum for
  both sets.
The training pool is cached at intermediates/midcentury_score/train_pool_r8bmain_r7.pkl, keyed by the lists' sha256.
Run from tasks/:  python3 eval-domains/scripts/midcentury_exposure.py SET_DIR [SET_DIR...]
"""
import hashlib, json, pickle, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, "eval-domains/scripts")
import ngram_overlap as N  # noqa: E402

LISTS = {"r8b-main-fold": Path("r8b-tesseract/data/train_main.list"), "r7": Path("r7-tesseract-real/data/bynli/train.list")}
CACHE = Path("eval-domains/intermediates/midcentury_score/train_pool_r8bmain_r7.pkl")
MANIFEST = Path("eval-domains/capture/midcentury/batch_manifest_v1.json")


def pool():
    key = {k: hashlib.sha256(v.read_bytes()).hexdigest() for k, v in LISTS.items()}
    if CACHE.exists():
        c = pickle.loads(CACHE.read_bytes())
        if c["key"] == key:
            return c["grams"], key
    g = set()
    for f in LISTS.values():
        stores = defaultdict(list)
        for p in f.read_text().split():
            stores[str(Path(p).parent.parent)].append(Path(p[: -len(".lstmf")] + ".gt.txt").read_text(encoding="utf-8").strip())
        for texts in stores.values():
            for t in N.logical(texts):
                g |= N.grams(t)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps({"key": key, "grams": g}))
    return g, key


def main(dirs):
    g, key = pool()
    stratum = {f"midcentury:{p['unit_id']}#p{p['page']}": p["stratum"] for p in json.load(open(MANIFEST))["pages"]}
    for d in map(Path, dirs):
        man = json.load(open(d / "reference_manifest.json"))
        exposed, zero = {}, []
        for it in man["items"]:
            ref = json.load(open(d / it["transcription_reference"]["path"]))
            hits = [ln["line_id"] for ln in ref["lines"] if N.grams(ln["text"]) & g]
            if hits:
                exposed[it["item_id"]] = {"exposed_lines": len(hits), "lines": len(ref["lines"]), "line_ids": hits}
            else:
                zero.append(it["item_id"])
        (d / "items_zero_exposure.txt").write_text("".join(f"{i}\n" for i in sorted(zero)), encoding="utf-8")
        n_all = Counter(stratum[i["item_id"]] for i in man["items"]); n_zero = Counter(stratum[i] for i in zero)
        doc = {"rule": "zero exposure: no reference line shares a word 6-gram with the R8b main-fold or R7 train list; no "
                       "threshold (lead, pre-registered 2026-11-13)", "train_lists_sha256": key,
               "items": len(man["items"]), "zero_exposure": len(zero), "exposed": exposed,
               "n_per_stratum": {s: {"full": n_all[s], "zero_exposure": n_zero[s]} for s in sorted(n_all)}}
        (d / "exposure.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1))
        print(f"{d}: {len(zero)}/{len(man['items'])} zero-exposure pages; {len(exposed)} exposed")


if __name__ == "__main__":
    main(sys.argv[1:])
