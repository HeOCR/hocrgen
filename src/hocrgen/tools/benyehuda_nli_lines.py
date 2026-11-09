"""Real scanned line sets from the Ben-Yehuda x NLI alignment (F8f), and a line-level OCR-as-label measurement.

Subcommands:

- ``build`` cuts line images from the cached NLI scans of one or more F8f alignment roots and labels each line with
  the **Ben-Yehuda edition text** the alignment placed on it. Labels are never OCR output: OCR only localizes lines
  (in the aligner) and picks between candidate edition spans at a line's edges (here).
- ``ocr`` runs Tesseract on each line crop of a built set (``--psm 13`` reads a crop as one raw line, as lstmeval
  does; ``--psm 7`` returns nothing on crops that carry a sliver of the neighbouring line).
- ``score`` compares a labeler's crop OCR with the edition labels: exact lines, CER, and for each target precision the
  keep-rule (min word confidence, lexicon coverage) with the most kept characters.

An alignment root has the F8f layout: ``out/<pby_id>/alignment.json`` (``hocrgen.benyehuda_nli_alignment.v1``),
``pby/txt/m<pby_id>.txt``, ``work/<record>/img/c<idx:04d>.jpg`` and ``work/<record>/ocr/c<idx:04d>.tsv``. Line boxes
in ``alignment.json`` are IIIF canvas pixels; Tesseract boxes are image pixels (scale = canvas width / image width).

``build`` keeps lines of class ``matched`` with score >= ``--min-score`` on ``aligned`` pages of records whose rights
decision is ``accepted`` with license ``public-domain-free-use``. The alignment's line span is approximate at the
edges, so it is snapped to word (or after-hyphen) boundaries within two units of each edge, keeping the span whose
label best matches Tesseract's reading of that line. Dropped: lines taller than 1.6x the page's median line (two printed
lines), lines whose best label still matches the line OCR below 0.7, ``[n]`` footnote markers, characters outside
the printed repertoire, labels without letters. Labels: NFC, cantillation removed, ``…`` as ``...``, ``„`` as ``"``,
soft hyphens removed, whitespace collapsed; niqqud removed too, except on pointed prints with ``--keep-pointed``.

Pointed prints (``--pointed``) are dropped by default (schema v1). With ``--keep-pointed`` their labels keep the
edition niqqud and the lines form the ``pointed`` stratum, behind three gates: lines whose edition text carries
cantillation or too little niqqud are dropped; a book whose edition text is under-pointed against a fully pointed
print (more than 5% of shins undotted or 1% of words bare) is dropped whole; then any line with a bare word or an
undotted shin. ``--dev`` books are held out whole; ``--max-lines-per-book`` caps each other book (and dev books only
with ``--cap-dev``) by sha256 of the line id. Schema v2 fails closed on possibly pointed prints: ``build`` exits
non-zero, writing nothing, when a record's edition text is pointed (``CHECK_POINTED_DENSITY``) and the record is named
in neither ``--pointed`` nor ``--unpointed`` (an asserted unpointed print). Schema v2 adds per-line ``stratum`` and ``ocr_placer`` (which OCR
localized the line for the aligner: ``method.ocr_model`` if the alignment records one, else the ``--tessdata-dir`` of
``method.ocr_engine``, else ``stock``) and the matching summary breakdowns.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from multiprocessing import Pool
from pathlib import Path
from typing import Any

from PIL import Image

SCHEMA_PREFIX = "s16c_benyehuda_nli_lines"
POINTS = re.compile("[֑-ׇֽֿׁׂׅׄ]")  # niqqud + cantillation; keeps maqaf, paseq, sof pasuq
CANTILLATION = re.compile("[֑-֯]")
NIQQUD = re.compile("[ְ-ׇֽֿׁׂ]")  # sheva..meteg, rafe, shin/sin dots, qamats qatan
LETTER = re.compile("[א-ת]")
POINTED_WORD = re.compile("[א-תְ-ׇ]+")
ALLOWED = re.compile("^[א-ת0-9 .,:;!?'\"()\\-־׳״–—/]+$")
FOLD = {"…": "...", "„": '"', "­": ""}  # ellipsis as printed dots; low quote as Ben-Yehuda's "; soft hyphen
TOKEN = re.compile(r"\S+")
HYPHEN = re.compile("[-־]")
MIN_OCR_SIMILARITY = 0.7
MAX_HEIGHT_RATIO = 1.6
MIN_POINTED_DENSITY = 0.3
# A record whose edition text carries this much niqqud (marks per letter) may be a pointed print. Unpointed editions in
# the F8f2 set sit at 0.004-0.045; pointed ones at 0.65-0.89. Schema v2 refuses to build while such a record is in
# neither --pointed nor --unpointed: stripping its niqqud would teach a recognizer to drop marks the print shows.
CHECK_POINTED_DENSITY = 0.1
MAX_UNDOTTED_SHIN = 0.05
MAX_BARE_WORDS = 0.01
ACCEPTED_LICENSE = "public-domain-free-use"


def label(raw: str, *, keep_niqqud: bool = False) -> str:
    text = unicodedata.normalize("NFD", raw)
    text = CANTILLATION.sub("", text) if keep_niqqud else POINTS.sub("", text)
    text = unicodedata.normalize("NFC", text)
    for char, repl in FOLD.items():
        text = text.replace(char, repl)
    return re.sub(r"\s+", " ", text).strip()


def niqqud_density(text: str) -> float:
    letters = len(LETTER.findall(text))
    return len(NIQQUD.findall(unicodedata.normalize("NFD", text))) / letters if letters else 0.0


def pointing_gaps(text: str) -> tuple[int, int, int, int]:
    """(words of 2+ letters, of them without niqqud, shins, of them without shin/sin dot) in a pointed label."""
    t = unicodedata.normalize("NFD", text)
    words = [w for w in POINTED_WORD.findall(t) if len(LETTER.findall(w)) >= 2]
    shins = re.findall("ש[ְ-ׇ]*", t)
    return (len(words), sum(not NIQQUD.search(w) for w in words),
            len(shins), sum("ׁ" not in s and "ׂ" not in s for s in shins))


def ocr_placer(method: Mapping[str, Any]) -> str:
    if method.get("ocr_model"):
        return str(method["ocr_model"])
    engine = str(method.get("ocr_engine") or "")
    m = re.search(r"--tessdata-dir[ =](\S+)", engine)
    return f"tessdata:{Path(m.group(1)).name}" if m else "stock"


def read_tsv_boxes(path: Path) -> list[tuple[str, float, tuple[int, int, int, int]]]:
    """Tesseract TSV word rows as (text, confidence, (left, top, right, bottom))."""
    words = []
    for row in path.read_text(encoding="utf-8").splitlines()[1:]:
        f = row.split("\t")
        if len(f) >= 12 and f[0] == "5" and f[11].strip():
            left, top, w, h = (int(v) for v in f[6:10])
            words.append((f[11].strip(), float(f[10]), (left, top, left + w, top + h)))
    return words


def words_in_box(words, box, slack=2):
    x, y, w, h = box
    inside = [wd for wd in words if x - slack <= (wd[-1][0] + wd[-1][2]) / 2 <= x + w + slack
              and y - slack <= (wd[-1][1] + wd[-1][3]) / 2 <= y + h + slack]
    return sorted(inside, key=lambda wd: -wd[-1][2])  # right to left


def refine(text: str, s: int, e: int, ocr_text: str, reach: int = 2) -> tuple[int, int, float, float]:
    """Snap an approximate line span to whole words: among word boundaries within ``reach`` words of each edge, keep
    the span whose label best matches Tesseract's reading of the line. The label text stays the edition's."""
    lo, hi = max(0, s - 120), min(len(text), e + 120)
    toks = []  # words, also split after a hyphen: prints break compounds across lines
    for m in TOKEN.finditer(text, lo, hi):
        a = m.start()
        for h in HYPHEN.finditer(text, m.start(), m.end() - 1):
            toks.append((a, h.end()))
            a = h.end()
        toks.append((a, m.end()))
    if not toks:
        return s, e, 0.0, 0.0
    i0 = next((k for k, (a, b) in enumerate(toks) if b > s), len(toks) - 1)
    j0 = max((k for k, (a, b) in enumerate(toks) if a < e), default=i0)
    before = difflib.SequenceMatcher(None, label(text[s:e]), ocr_text, autojunk=False).ratio()
    best = None
    for i in range(max(0, i0 - reach), min(len(toks), i0 + reach + 1)):
        for j in range(max(i, j0 - reach), min(len(toks), j0 + reach + 1)):
            r = difflib.SequenceMatcher(None, label(text[toks[i][0]:toks[j][1]]), ocr_text, autojunk=False).ratio()
            key = (r, -(abs(i - i0) + abs(j - j0)))
            if best is None or key > best[0]:
                best = (key, toks[i][0], toks[j][1])
    return best[1], best[2], before, best[0][0]


def crop_box(image_size: tuple[int, int], bbox_canvas: Sequence[float], canvas_width: float):
    """Image-pixel line box and padded crop box for a canvas-pixel line box."""
    scale = canvas_width / image_size[0]
    x, y, w, h = (v / scale for v in bbox_canvas)
    px, py = 0.5 * h, 0.12 * h
    box = (max(0, round(x - px)), max(0, round(y - py)), min(image_size[0], round(x + w + px)), min(image_size[1], round(y + h + py)))
    return scale, (x, y, w, h), box


def line_id(record: str, canvas_index: int, line_index: int) -> str:
    return f"nli{record}_c{canvas_index:04d}_l{line_index:03d}"


def _named(pairs: Iterable[str] | None) -> dict[str, str]:
    out = {}
    for p in pairs or ():
        rec, _, name = p.partition("=")
        out[rec] = name or rec
    return out


def collect(roots: Sequence[Path], *, min_score: float, pointed: Mapping[str, str], keep_pointed: bool):
    """Candidate lines per (record, canvas, line) after the line gates, with drop counts and edition niqqud density."""
    best: dict[tuple[str, int, int], dict[str, Any]] = {}
    drops: Counter = Counter()
    seen: dict[str, Path] = {}
    density: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for root in roots:
        for ap_path in sorted((root / "out").glob("*/alignment.json")):
            pby = ap_path.parent.name
            if not pby.isdigit():
                continue
            al = json.loads(ap_path.read_text(encoding="utf-8"))
            scan = al["scan"]
            rec = scan["nli_record_id"]
            if scan.get("license_slug") != ACCEPTED_LICENSE or (scan.get("rights_decision") or {}).get("decision") != "accepted":
                continue
            if seen.setdefault(rec, root) != root:
                raise SystemExit(f"record {rec} under two roots: {seen[rec]} and {root}")
            placer = ocr_placer(al.get("method") or {})
            text = unicodedata.normalize("NFC", (root / "pby" / "txt" / f"m{pby}.txt").read_text(encoding="utf-8"))
            for page in al["pages"]:
                if page["status"] != "aligned":
                    continue
                idx = page["canvas_index"]
                with Image.open(root / "work" / rec / "img" / f"c{idx:04d}.jpg") as opened:
                    page_scale = page["canvas_size"][0] / opened.size[0]
                words = read_tsv_boxes(root / "work" / rec / "ocr" / f"c{idx:04d}.tsv")
                heights = sorted(ln["bbox"][3] for ln in page["lines"] if ln.get("class") == "matched")
                median_h = heights[len(heights) // 2] if heights else 0
                for line in page["lines"]:
                    if line.get("class") != "matched" or not line.get("pby_span"):
                        continue
                    if (line.get("score") or 0) < min_score:
                        drops["below_min_score"] += 1
                        continue
                    if median_h and line["bbox"][3] > MAX_HEIGHT_RATIO * median_h:
                        drops["taller_than_one_line"] += 1
                        continue
                    s0, e0 = line["pby_span"]
                    inside = words_in_box(words, [v / page_scale for v in line["bbox"]])
                    s, e, sim_before, sim = refine(text, s0, e0, label(" ".join(wd[0] for wd in inside)))
                    raw = text[s:e]
                    if sim < MIN_OCR_SIMILARITY:
                        drops["label_disagrees_with_line_ocr"] += 1
                        continue
                    plain = label(raw)
                    density[rec][0] += len(NIQQUD.findall(unicodedata.normalize("NFD", raw)))
                    density[rec][1] += len(LETTER.findall(raw))
                    stratum, gt = "unpointed", plain
                    if rec in pointed:
                        if not keep_pointed:
                            drops["pointed_print"] += 1
                            continue
                        if CANTILLATION.search(unicodedata.normalize("NFD", raw)):
                            drops["pointed_print_cantillation"] += 1
                            continue
                        if niqqud_density(raw) < MIN_POINTED_DENSITY:
                            drops["pointed_print_label_unpointed"] += 1
                            continue
                        stratum, gt = "pointed", label(raw, keep_niqqud=True)
                    if re.search(r"\[\d+\]", raw):
                        drops["footnote_marker"] += 1
                        continue
                    if not plain or not LETTER.search(plain) or not ALLOWED.match(plain):
                        drops["outside_repertoire"] += 1
                        continue
                    key = (rec, idx, line["line"])
                    cand = {"record_id": rec, "pby_id": pby, "canvas_index": idx, "canvas_id": page["canvas_id"],
                            "line_index": line["line"], "bbox_canvas": line["bbox"], "canvas_size": page["canvas_size"],
                            "text": gt, "pby_span": [s, e], "pby_span_alignment": [s0, e0], "span_adjusted": [s, e] != [s0, e0],
                            "ocr_similarity_before": round(sim_before, 4), "ocr_similarity": round(sim, 4),
                            "alignment_score": line["score"], "strict_char_similarity": line.get("strict_char_similarity"),
                            "page_quality": page.get("quality"), "_root": root, "_stratum": stratum, "_placer": placer}
                    if key in best:
                        drops["aligned_twice"] += 1
                        if cand["alignment_score"] <= best[key]["alignment_score"]:
                            continue
                    best[key] = cand
    return best, drops, density


def pointed_book_gate(best: dict, drops: Counter) -> dict[str, dict[str, Any]]:
    """Drop pointed books whose edition text is under-pointed, then under-pointed lines. Mutates ``best``."""
    report = {}
    for rec in sorted({k[0] for k, c in best.items() if c["_stratum"] == "pointed"}):
        keys = [k for k in best if k[0] == rec]
        gaps = [pointing_gaps(best[k]["text"]) for k in keys]
        words, bare, shins, undotted = (sum(g[i] for g in gaps) for i in range(4))
        ok = (undotted / shins if shins else 0.0) <= MAX_UNDOTTED_SHIN and (bare / words if words else 1.0) <= MAX_BARE_WORDS
        report[rec] = {"lines": len(keys), "bare_word_rate": round(bare / words, 4) if words else None,
                       "undotted_shin_rate": round(undotted / shins, 4) if shins else None, "edition_fully_pointed": ok}
        for k, g in zip(keys, gaps):
            if not ok:
                drops["pointed_edition_underpointed"] += 1
                del best[k]
            elif g[1] or g[3]:
                drops["pointed_line_underpointed"] += 1
                del best[k]
    return report


def cap_per_book(keys: list, cap: int, exempt: Iterable[str]) -> tuple[list, Counter]:
    exempt = set(exempt)
    by_rec = defaultdict(list)
    for k in keys:
        by_rec[k[0]].append(k)
    keep, capped = set(), Counter()
    for rec, ks in by_rec.items():
        if rec in exempt:
            keep |= set(ks)
            continue
        order = sorted(ks, key=lambda k: hashlib.sha256(line_id(*k).encode()).hexdigest())
        keep |= set(order[:cap])
        capped[rec] = max(0, len(ks) - cap)
    return [k for k in keys if k in keep], capped


def build(args: argparse.Namespace) -> dict[str, Any]:
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    roots = [Path(r) for r in args.root]
    pointed, dev = _named(args.pointed), _named(args.dev)
    editions: dict[str, Any] = {}
    for path in args.editions or ():
        editions.update(json.loads(Path(path).read_text(encoding="utf-8")))
    names = _named(args.name)
    unpointed = set(args.unpointed or ())
    if unpointed & set(pointed):
        raise SystemExit(f"records both --pointed and --unpointed: {sorted(unpointed & set(pointed))}")
    best, drops, density = collect(roots, min_score=args.min_score, pointed=pointed, keep_pointed=args.keep_pointed)
    dens = {rec: round(m / n, 3) if n else 0.0 for rec, (m, n) in sorted(density.items())}
    unresolved = sorted(rec for rec, d in dens.items() if d >= CHECK_POINTED_DENSITY and rec not in pointed and rec not in unpointed)
    if args.schema == "v2" and unresolved:
        raise SystemExit("edition text is pointed but the print is not classified; name each in --pointed or --unpointed: "
                         + ", ".join(f"{rec} (niqqud {dens[rec]}/letter)" for rec in unresolved))
    pointing = pointed_book_gate(best, drops) if args.keep_pointed else {}
    keys = sorted(best)
    capped: Counter = Counter()
    if args.max_lines_per_book:
        keys, capped = cap_per_book(keys, args.max_lines_per_book, () if args.cap_dev else dev)
    v2 = args.schema == "v2"
    rows = []
    counts: dict[str, Counter] = defaultdict(Counter)
    strata: dict[str, Counter] = defaultdict(Counter)
    by_book_stratum: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    by_book_placer: dict[str, Counter] = defaultdict(Counter)
    for key in keys:
        r = dict(best[key])
        root, stratum, placer = r.pop("_root"), r.pop("_stratum"), r.pop("_placer")
        rec = r["record_id"]
        split = "dev" if rec in dev else "train"
        lid = line_id(*key)
        rel = Path(split) / rec / f"{lid}.png"
        with Image.open(root / "work" / rec / "img" / f"c{r['canvas_index']:04d}.jpg") as im:
            scale, (x, y, w, h), box = crop_box(im.size, r["bbox_canvas"], r["canvas_size"][0])
            image_sha = None
            if not args.no_images:
                (out / rel).parent.mkdir(parents=True, exist_ok=True)
                im.convert("L").crop(box).save(out / rel)
                (out / rel.with_suffix(".gt.txt")).write_text(r["text"] + "\n", encoding="utf-8")
                image_sha = hashlib.sha256((out / rel).read_bytes()).hexdigest()
        book = dev.get(rec) or pointed.get(rec) or names.get(rec) or (editions.get(rec) or {}).get("candidate", rec)
        row = {"id": lid, "split": split, "book": book, **{k: v for k, v in r.items() if k != "canvas_size"},
               "image_scale": round(scale, 5), "bbox_image": [round(x), round(y), round(w), round(h)],
               "crop_box_image": list(box), "image": str(rel), "image_sha256": image_sha}
        if v2:
            row["stratum"], row["ocr_placer"] = stratum, placer
        rows.append(row)
        label_key = f"{rec} {book}"
        counts[split][label_key] += 1
        strata[split][stratum] += 1
        by_book_stratum[split][label_key][stratum] += 1
        by_book_placer[label_key][placer] += 1
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    summary: dict[str, Any] = {
        "schema": f"{SCHEMA_PREFIX}.{args.schema}", "min_score": args.min_score,
        "labels": "Ben-Yehuda edition text placed by F8f alignment; never OCR output", "label_folds": FOLD,
        "min_ocr_similarity": MIN_OCR_SIMILARITY, "max_height_ratio": MAX_HEIGHT_RATIO, "dev_records": dev,
        ("pointed_records" if args.keep_pointed else "excluded_pointed_records"): pointed,
        "lines": {s: dict(c) for s, c in counts.items()}, "totals": {s: sum(c.values()) for s, c in counts.items()},
        "dropped": dict(drops), "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest()}
    if v2:
        summary.update({
            "roots": [str(r) for r in roots], "strata": {s: dict(c) for s, c in strata.items()},
            "lines_by_book_and_stratum": {s: {b: dict(c) for b, c in sorted(d.items())} for s, d in by_book_stratum.items()},
            "lines_by_book_and_ocr_placer": {b: dict(c) for b, c in sorted(by_book_placer.items())},
            "max_lines_per_book": args.max_lines_per_book, "cap_dev": args.cap_dev,
            "capped_lines": {rec: n for rec, n in sorted(capped.items()) if n},
            "min_pointed_density": MIN_POINTED_DENSITY, "max_undotted_shin": MAX_UNDOTTED_SHIN,
            "max_bare_words": MAX_BARE_WORDS, "pointed_edition_check": pointing, "edition_niqqud_density": dens,
            "check_pointed_density": CHECK_POINTED_DENSITY, "unpointed_records": sorted(unpointed),
            # Asserted unpointed prints whose edition text is pointed (labels have niqqud stripped, as the print shows).
            "unpointed_with_pointed_edition": sorted(rec for rec in unpointed if dens.get(rec, 0.0) >= CHECK_POINTED_DENSITY),
            "images_written": not args.no_images})
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


# --- OCR-as-label measurement ---------------------------------------------------------------------------------

SCORE_FOLD = {"…": "...", "„": '"', "­": "", "״": '"', "׳": "'", "־": "-", "–": "-",
              "—": "-", "“": '"', "”": '"'}
BIDI = re.compile("[‎‏‪-‮⁦-⁩]")
HEB_WORD = re.compile("[א-ת]{2,}")
SHORT_CHARS = 25
TARGETS = (0.99, 0.95)
CONF_STEPS = (0, 50, 60, 70, 75, 80, 85, 88, 90, 92, 94, 96)
LEX_STEPS = (0.0, 0.8, 0.9, 1.0)


def norm(text: str) -> str:
    """Comparison form for labels and OCR: NFC, niqqud removed, quotes/dashes folded, bidi marks and lone bars removed,
    no space before closing punctuation, whitespace collapsed."""
    text = unicodedata.normalize("NFC", POINTS.sub("", unicodedata.normalize("NFD", text)))
    for a, b in SCORE_FOLD.items():
        text = text.replace(a, b)
    text = BIDI.sub("", text)
    text = re.sub(r"(^|\s)\|(?=\s|$)", " ", text)  # lone bars: crop-edge rules, never text
    text = re.sub(r"\s+([.,:;!?)])", r"\1", text)
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\s+", " ", text).strip()


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def load_manifest(lines_dir: Path, records: Iterable[str] | None = None) -> list[dict[str, Any]]:
    rows = [json.loads(ln) for ln in (lines_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    records = set(records or ())
    return [r for r in rows if not records or r["record_id"] in records]


def _ocr_one(job):  # pragma: no cover - runs tesseract
    img, out, lang, tessdata, psm = job
    if out.exists():
        return 0
    cmd = ["tesseract", str(img), "stdout", "-l", lang, "--psm", str(psm)]
    if tessdata:
        cmd += ["--tessdata-dir", tessdata]
    res = subprocess.run(cmd + ["tsv"], capture_output=True, text=True, check=False,
                         env={**os.environ, "OMP_THREAD_LIMIT": "1"})
    if res.returncode:
        raise RuntimeError(f"{img}: {res.stderr[-300:]}")
    out.write_text(res.stdout, encoding="utf-8")
    return 1


def run_ocr(args: argparse.Namespace) -> int:  # pragma: no cover - runs tesseract
    lines_dir, ocr_dir = Path(args.lines), Path(args.ocr_dir)
    jobs = []
    for r in load_manifest(lines_dir, args.records):
        out = ocr_dir / r["record_id"] / f"{r['id']}.tsv"
        out.parent.mkdir(parents=True, exist_ok=True)
        jobs.append((lines_dir / r["image"], out, args.lang, args.tessdata_dir, args.psm))
    done = 0
    with Pool(args.procs) as pool:
        for i, n in enumerate(pool.imap_unordered(_ocr_one, jobs, chunksize=16), 1):
            done += n
            if i % 2000 == 0:
                print(f"{i}/{len(jobs)} lines", flush=True)
    print(f"OCR done: {done} new, {len(jobs)} lines", flush=True)
    return 0


def summarise(sel: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    n, chars = len(sel), sum(ln["chars"] for ln in sel)
    exact = [ln for ln in sel if ln["exact"]]
    return {"lines": n, "chars": chars, "exact_lines": len(exact), "exact_rate": round(len(exact) / n, 4) if n else None,
            "cer": round(sum(ln["dist"] for ln in sel) / chars, 5) if chars else None,
            "short_lines": sum(ln["chars"] < SHORT_CHARS for ln in sel),
            "short_exact_lines": sum(ln["chars"] < SHORT_CHARS for ln in exact),
            "exact_chars_in_long_lines": sum(ln["chars"] for ln in exact if ln["chars"] >= SHORT_CHARS)}


def score_lines(rows: Sequence[Mapping[str, Any]], words_of, lexicon: Mapping[str, int] | None) -> list[dict[str, Any]]:
    """Per line: normalised labeler text vs label. ``words_of(row)`` gives the labeler's (text, conf, ...) words in
    reading order, or None when the line has no OCR."""
    lines = []
    for r in rows:
        words = words_of(r)
        if words is None:
            continue
        hyp, ref = norm(" ".join(w[0] for w in words)), norm(r["text"])
        heb = [m.group() for w in words for m in HEB_WORD.finditer(norm(w[0]))]
        dist = edit_distance(hyp, ref)
        lines.append({"id": r["id"], "rec": r["record_id"], "book": r["book"], "split": r["split"], "ref": ref, "hyp": hyp,
                      "chars": len(ref), "dist": dist, "exact": dist == 0,
                      "min_conf": min((w[1] for w in words), default=0.0),
                      "mean_conf": sum(w[1] for w in words) / len(words) if words else 0.0,
                      "lex_cov": (sum(lexicon.get(h, 0) >= 3 for h in heb) / len(heb) if heb else 0.0) if lexicon is not None else None})
    return lines


def best_rules(lines: Sequence[Mapping[str, Any]], *, use_lexicon: bool) -> dict[str, Any]:
    recs = sorted({ln["rec"] for ln in lines})
    rules: dict[str, Any] = {}
    for target in TARGETS:
        best = None
        for c in CONF_STEPS:
            for x in (LEX_STEPS if use_lexicon else (0.0,)):
                kept = [ln for ln in lines if ln["min_conf"] >= c and (not use_lexicon or ln["lex_cov"] >= x)]
                s = summarise(kept)
                if s["lines"] and s["exact_rate"] >= target and (best is None or s["chars"] > best[3]["chars"]):
                    best = (c, x, kept, s)
        if best is None:
            rules[str(target)] = None
            continue
        c, x, kept, s = best
        rules[str(target)] = {"min_word_conf": c, "min_lex_cov": x if use_lexicon else None, "kept": s,
                              "yield_lines": round(len(kept) / len(lines), 4),
                              "per_record": {rec: {**summarise([ln for ln in kept if ln["rec"] == rec]),
                                                   "of_lines": sum(ln["rec"] == rec for ln in lines)} for rec in recs}}
    return rules


def score(args: argparse.Namespace) -> dict[str, Any]:
    lines_dir = Path(args.lines)
    lexicon = json.loads(Path(args.lexicon).read_text(encoding="utf-8"))["counts"] if args.lexicon else None
    page_cache: dict[tuple[str, int], list] = {}

    def crop_words(r):
        path = Path(args.ocr_dir) / r["record_id"] / f"{r['id']}.tsv"
        if not path.exists():
            return None
        return sorted(read_tsv_boxes(path), key=lambda wd: -wd[2][0])  # right to left

    def page_words(r):  # the aligner's cached full-page OCR, words inside the line box
        key = (r["record_id"], r["canvas_index"])
        if key not in page_cache:
            page_cache.clear()
            page_cache[key] = read_tsv_boxes(Path(args.page_ocr_root) / "work" / key[0] / "ocr" / f"c{key[1]:04d}.tsv")
        return words_in_box(page_cache[key], r["bbox_image"])

    rows = load_manifest(lines_dir, args.records)
    lines = score_lines(rows, page_words if args.page_ocr_root else crop_words, lexicon)
    out = {"tag": args.tag, "ocr": args.page_ocr_root or args.ocr_dir, "short_line_chars": SHORT_CHARS,
           "all": summarise(lines),
           "per_record_all": {rec: summarise([ln for ln in lines if ln["rec"] == rec]) for rec in sorted({ln["rec"] for ln in lines})},
           "books": {ln["rec"]: ln["book"] for ln in lines}, "rules": best_rules(lines, use_lexicon=lexicon is not None)}
    out_path = Path(args.out)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    out_path.with_name(out_path.stem + "_lines.jsonl").write_text(
        "".join(json.dumps(ln, ensure_ascii=False) + "\n" for ln in lines), encoding="utf-8")
    return out


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="cut a labelled line set from F8f alignment roots")
    b.add_argument("out")
    b.add_argument("--root", action="append", required=True, help="F8f alignment root (repeatable)")
    b.add_argument("--editions", action="append", help="record -> {candidate, pby_ids} JSON, for book names")
    b.add_argument("--name", nargs="*", help="book names REC=name (override --editions)")
    b.add_argument("--min-score", type=float, default=0.9)
    b.add_argument("--schema", choices=("v1", "v2"), default="v2")
    b.add_argument("--pointed", nargs="*", help="pointed-print records REC[=name]")
    b.add_argument("--unpointed", nargs="*", help="records asserted to be unpointed prints although their edition text is pointed")
    b.add_argument("--keep-pointed", action="store_true", help="keep pointed prints with niqqud labels (stratum `pointed`)")
    b.add_argument("--dev", nargs="*", help="dev records REC[=name], held out whole")
    b.add_argument("--max-lines-per-book", type=int, default=0)
    b.add_argument("--cap-dev", action="store_true")
    b.add_argument("--no-images", action="store_true", help="manifest and summary only (image_sha256 null)")
    o = sub.add_parser("ocr", help="run a Tesseract model on every line crop of a built set")
    o.add_argument("lines")
    o.add_argument("ocr_dir")
    o.add_argument("--lang", default="heb")
    o.add_argument("--tessdata-dir")
    o.add_argument("--psm", type=int, default=13)
    o.add_argument("--records", nargs="*")
    o.add_argument("--procs", type=int, default=4)
    s = sub.add_parser("score", help="score a labeler's line OCR against the edition labels")
    s.add_argument("lines")
    s.add_argument("ocr_dir", nargs="?", help="crop OCR from `ocr` (or use --page-ocr-root)")
    s.add_argument("out")
    s.add_argument("--page-ocr-root", help="use the aligner's cached full-page OCR under this F8f root instead")
    s.add_argument("--lexicon", help='{"counts": {word: n}} JSON; enables lexicon-coverage rules')
    s.add_argument("--records", nargs="*")
    s.add_argument("--tag", default="")
    args = parser.parse_args(argv)
    if args.cmd == "build":
        print(json.dumps(build(args), ensure_ascii=False, indent=2))
    elif args.cmd == "ocr":  # pragma: no cover - runs tesseract
        return run_ocr(args)
    else:
        if not args.ocr_dir and not args.page_ocr_root:
            parser.error("score needs OCR_DIR or --page-ocr-root")
        res = score(args)
        print(json.dumps({k: res[k] for k in ("all", "rules")}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
