"""Network-free tests for hocrgen.tools.benyehuda_nli_lines (real line sets from the Ben-Yehuda x NLI alignment)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.tools import benyehuda_nli_lines as bl

CANVAS = (400, 240)  # canvas px; the cached image is half that, so line boxes must be divided by 2
IMAGE = (200, 120)
SHIN, DAGESH, QAMATS, HOLAM, PATAH = "שׁ", "ּ", "ָ", "ֹ", "ַ"


def _tsv(lines_words: list[tuple[list[float], list[str]]]) -> str:
    rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
    for n, (box, words) in enumerate(lines_words):
        x, y, w, h = box
        right = x + w
        for j, word in enumerate(words):  # reading order is right to left
            left = right - (j + 1) * 40
            rows.append(f"5\t1\t1\t1\t{n}\t{j}\t{int(left) + 2}\t{int(y) + 2}\t36\t{int(h) - 4}\t95.0\t{word}")
    return "\n".join(rows) + "\n"


def _record(root: Path, rec: str, pby: str, lines: list[str], *, method: dict | None = None, rights: str = "accepted") -> None:
    """One aligned page whose lines carry ``lines`` (edition text); the page OCR reads them without niqqud."""
    text = " ".join(lines)
    spans, pos = [], 0
    for ln in lines:
        spans.append([pos, pos + len(ln)])
        pos += len(ln) + 1
    page_lines, ocr = [], []
    for i, ln in enumerate(lines):
        bbox = [20, 20 + 40 * i, 360, 30]
        page_lines.append({"line": i, "class": "matched", "score": 0.95, "bbox": bbox, "pby_span": spans[i]})
        ocr.append(([v / 2 for v in bbox], bl.label(ln).split()))
    alignment = {"format": "hocrgen.benyehuda_nli_alignment.v1", "method": method or {"ocr_engine": "tesseract 5.5.3 -l heb --psm 3"},
                 "scan": {"nli_record_id": rec, "license_slug": "public-domain-free-use", "rights_decision": {"decision": rights}},
                 "pages": [{"canvas_index": 0, "canvas_id": f"{rec}/c0", "canvas_size": list(CANVAS), "status": "aligned",
                            "quality": "high", "lines": page_lines}]}
    (root / "out" / pby).mkdir(parents=True)
    (root / "out" / pby / "alignment.json").write_text(json.dumps(alignment, ensure_ascii=False), encoding="utf-8")
    (root / "pby" / "txt").mkdir(parents=True, exist_ok=True)
    (root / "pby" / "txt" / f"m{pby}.txt").write_text(text, encoding="utf-8")
    for sub in ("img", "ocr"):
        (root / "work" / rec / sub).mkdir(parents=True)
    Image.new("RGB", IMAGE, "white").save(root / "work" / rec / "img" / "c0000.jpg")
    (root / "work" / rec / "ocr" / "c0000.tsv").write_text(_tsv(ocr), encoding="utf-8")


POINTED_FULL = [f"{SHIN}{HOLAM}לוֹם עוֹלָם", f"בַּיִת גָּדוֹל", f"{SHIN}{PATAH}בָּת טוֹבָה"]
POINTED_UNDER = ["שלוֹם עוֹלם", "בַּיִת גָּדוֹל", "שבָּת טוֹבָה"]  # shins undotted: edition under-pointed


@pytest.fixture
def root(tmp_path: Path) -> Path:
    r = tmp_path / "f8f"
    _record(r, "111", "1", ["שלום עולם טוב", "בית־ספר גדול…", "ילד קטן הלך"])
    _record(r, "222", "2", ["ספר חדש ויפה", "עיר גדולה מאד", "נהר ארוך וצר", "הר גבוה מאד"],
            method={"ocr_engine": "tesseract 5.5.3 -l heb --psm 3 --tessdata-dir /models/r6"})
    _record(r, "333", "3", POINTED_FULL, method={"ocr_engine": "x", "ocr_model": "r6@73eb18e0"})
    _record(r, "444", "4", POINTED_UNDER)
    _record(r, "555", "5", ["אסור לקחת"], rights="rejected")
    return r


def _build(tmp_path: Path, root: Path, *extra: str) -> tuple[dict, list[dict]]:
    out = tmp_path / "set"
    assert bl.main(["build", str(out), "--root", str(root), "--pointed", "333=full", "444=under",
                    "--dev", "111=devbook", *extra]) == 0
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    return json.loads((out / "summary.json").read_text(encoding="utf-8")), rows


def test_label_strips_niqqud_keeps_maqaf_and_folds():
    assert bl.label("בַּיִת־סֵפֶר…  „טוב­") == 'בית־ספר... "טוב'
    assert bl.label("בַּ֫יִת", keep_niqqud=True) == "בַּיִת"  # cantillation removed, niqqud kept


def test_pointing_gaps_and_density():
    assert bl.pointing_gaps(POINTED_FULL[0]) == (2, 0, 1, 0)
    assert bl.pointing_gaps(POINTED_UNDER[0]) == (2, 0, 1, 1)
    assert bl.pointing_gaps("שלום") == (1, 1, 1, 1)
    assert bl.niqqud_density("שלום") == 0.0 and bl.niqqud_density(POINTED_FULL[1]) > 0.3


def test_ocr_placer():
    assert bl.ocr_placer({"ocr_engine": "tesseract 5.5.3 -l heb --psm 3"}) == "stock"
    assert bl.ocr_placer({"ocr_engine": "tesseract -l heb --tessdata-dir /m/r6"}) == "tessdata:r6"
    assert bl.ocr_placer({"ocr_engine": "x", "ocr_model": "r6"}) == "r6"


def test_refine_snaps_span_to_words():
    text = "אחד שנים שלוש ארבע חמש"
    s, e, before, after = bl.refine(text, 6, 16, "שנים שלוש ארבע")
    assert text[s:e] == "שנים שלוש ארבע" and after == 1.0 and before < 1.0


def test_build_v1_drops_pointed_and_rejected(tmp_path, root):
    summary, rows = _build(tmp_path, root, "--schema", "v1")
    assert summary["schema"] == "s16c_benyehuda_nli_lines.v1"
    assert summary["dropped"]["pointed_print"] == 6
    assert {r["record_id"] for r in rows} == {"111", "222"}
    assert "stratum" not in rows[0] and summary["totals"] == {"dev": 3, "train": 4}
    first = next(r for r in rows if r["id"] == "nli111_c0000_l001")
    assert first["text"] == "בית־ספר גדול..." and first["split"] == "dev" and first["book"] == "devbook"
    assert first["bbox_image"] == [10, 30, 180, 15]  # canvas px / 2
    png = tmp_path / "set" / first["image"]
    assert png.exists() and png.with_suffix(".gt.txt").read_text(encoding="utf-8") == "בית־ספר גדול...\n"


def test_build_v2_pointed_gate_cap_and_breakdowns(tmp_path, root):
    summary, rows = _build(tmp_path, root, "--keep-pointed", "--max-lines-per-book", "2", "--no-images")
    by_rec = {}
    for r in rows:
        by_rec.setdefault(r["record_id"], []).append(r)
    assert set(by_rec) == {"111", "222", "333"}
    assert len(by_rec["111"]) == 3  # dev is uncapped
    assert len(by_rec["222"]) == 2 and summary["capped_lines"] == {"222": 2, "333": 1}
    assert all(r["stratum"] == "pointed" and r["ocr_placer"] == "r6@73eb18e0" for r in by_rec["333"])
    assert any(bl.NIQQUD.search(r["text"]) for r in by_rec["333"])
    assert summary["pointed_edition_check"]["444"]["edition_fully_pointed"] is False
    # one line of 444 is too sparsely pointed to pass the line gate; the book gate drops the other two
    assert summary["dropped"]["pointed_print_label_unpointed"] == 1
    assert summary["dropped"]["pointed_edition_underpointed"] == 2
    assert summary["lines_by_book_and_stratum"]["train"] == {"222 222": {"unpointed": 2}, "333 full": {"pointed": 2}}
    assert summary["lines_by_book_and_ocr_placer"]["222 222"] == {"tessdata:r6": 2}
    assert summary["lines_by_book_and_ocr_placer"]["111 devbook"] == {"stock": 3}
    assert rows[0]["image_sha256"] is None and summary["images_written"] is False
    _, again = _build(tmp_path / "b", root, "--keep-pointed", "--max-lines-per-book", "2", "--no-images")
    assert [r["id"] for r in again] == [r["id"] for r in rows]  # cap is deterministic


def test_build_refuses_existing_output(tmp_path, root):
    (tmp_path / "set").mkdir()
    with pytest.raises(SystemExit):
        _build(tmp_path, root)


def test_norm_folds_ocr_artifacts():
    assert bl.norm("‏שלום , עולם | ״טוב״ – ( כן )") == 'שלום, עולם "טוב" - (כן)'
    assert bl.edit_distance("שלום", "שלם") == 1


def test_score_crop_ocr_and_rules(tmp_path, root):
    _build(tmp_path, root, "--schema", "v1")
    lines_dir, ocr_dir = tmp_path / "set", tmp_path / "ocr"
    rows = bl.load_manifest(lines_dir)
    for i, r in enumerate(rows):
        words = bl.norm(r["text"]).split()
        if i == 0:
            words[0] = words[0][:-1] + "ב"  # one wrong letter
        path = ocr_dir / r["record_id"] / f"{r['id']}.tsv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_tsv([([0, 0, 40 * len(words), 20], words)]).replace("\t95.0\t", "\t80.0\t" if i == 0 else "\t95.0\t"), encoding="utf-8")
    lexicon = tmp_path / "lex.json"
    lexicon.write_text(json.dumps({"counts": {}}), encoding="utf-8")
    out = tmp_path / "score.json"
    assert bl.main(["score", str(lines_dir), str(ocr_dir), str(out), "--lexicon", str(lexicon), "--tag", "t"]) == 0
    res = json.loads(out.read_text(encoding="utf-8"))
    assert res["all"]["lines"] == 7 and res["all"]["exact_lines"] == 6
    assert res["rules"]["0.99"]["min_word_conf"] > 80 and res["rules"]["0.99"]["kept"]["lines"] == 6
    assert (tmp_path / "score_lines.jsonl").exists()
    page = tmp_path / "page.json"
    assert bl.main(["score", str(lines_dir), str(page), "--page-ocr-root", str(root)]) == 0
    assert json.loads(page.read_text(encoding="utf-8"))["all"]["exact_rate"] == 1.0
