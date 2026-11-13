"""Page predictions on every mid-century batch v1 page, for R8b main-fold (frozen) and stock Tesseract (heocr-eval).

Runs heocr-engine's Tesseract engine (psm 3, heocr_engine_prediction.v1) on each page PNG of batch_manifest_v1.json,
test and reserve alike, so scoring can start as soon as the references land. A tessdata dir per model holds
heb.traineddata plus the stock configs/ (the engine asks Tesseract for txt and tsv, which need them).
Fails closed: the R8b file is not the frozen release model (r8b_release_figures_v1.json), or a page's image sha256 differs
from the manifest. Existing outputs whose input sha256 matches are kept.
Run from tasks/:  python3 eval-domains/scripts/midcentury_predict.py [--jobs 8]
"""
import hashlib, json, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

MC = Path("eval-domains/capture/midcentury")
OUT = Path("eval-domains/intermediates/midcentury_score/predictions")
ENGINE = Path.home() / "clones/heocr-engine"
TESS = "/opt/homebrew/bin/tesseract"
STOCK_CONFIGS = Path("/opt/homebrew/share/tessdata/configs")
FROZEN = json.load(open("eval-domains/outputs/r8b_release_figures_v1.json"))["model_traineddata_sha256"]
MODELS = {"r8b": Path("eval-domains/intermediates/score_lines/models/r8b-main-fold/heb.traineddata"),
          "stock": Path("/opt/homebrew/share/tessdata/heb.traineddata")}
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tessdata(name):
    d = OUT.parent / f"tessdata_{name}"; d.mkdir(parents=True, exist_ok=True)
    for link, target in ((d / "heb.traineddata", MODELS[name].resolve()), (d / "configs", STOCK_CONFIGS)):
        if not link.is_symlink():
            link.symlink_to(target)
    return d.resolve()


def one(job):
    name, td, png, want, out = job
    if out.exists() and json.load(open(out))["input"]["sha256"] == want:
        return None
    r = subprocess.run(["uv", "run", "--quiet", "--project", str(ENGINE), "python", "-m", "heocr_engine.cli", str(png.resolve()),
                        str(out.resolve()), "--executable", TESS, "--tessdata-dir", str(td), "--timeout", "300"],
                       capture_output=True, text=True)
    return None if r.returncode == 0 else f"{name} {png.name}: {r.stderr.strip()[-200:]}"


def main(jobs):
    if sha(MODELS["r8b"]) != FROZEN:
        raise SystemExit("r8b-main-fold heb.traineddata is not the frozen release model")
    pages = json.load(open(MC / "batch_manifest_v1.json"))["pages"]
    todo = []
    for p in pages:
        png = Path(p["image"])
        if sha(png) != p["image_sha256"]:
            raise SystemExit(f"{png}: image sha256 differs from the manifest")
    for name in MODELS:
        td = tessdata(name); (OUT / name).mkdir(parents=True, exist_ok=True)
        todo += [(name, td, Path(p["image"]), p["image_sha256"], OUT / name / f"{Path(p['image']).stem}.json") for p in pages]
    with ThreadPoolExecutor(jobs) as ex:
        errs = [e for e in ex.map(one, todo) if e]
    for e in errs:
        print("ERROR", e)
    print(f"{len(todo) - len(errs)}/{len(todo)} predictions present in {OUT}")
    if errs:
        raise SystemExit(1)


if __name__ == "__main__":
    a = sys.argv[1:]
    main(int(a[a.index("--jobs") + 1]) if "--jobs" in a else 8)
