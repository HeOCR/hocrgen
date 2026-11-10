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


def _record(root: Path, rec: str, pby: str, lines: list[str], *, method: dict | None = None, rights: str = "accepted",
            out: str = "out") -> None:
    """One aligned page whose lines carry ``lines`` (edition text); the page OCR reads them without niqqud.

    The OCR TSV goes where the aligner caches it (``ocr/``, or ``ocr-<ocr_model>/``).
    """
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
    method = method or {"ocr_engine": "tesseract 5.5.3 -l heb --psm 3"}
    alignment = {"format": "hocrgen.benyehuda_nli_alignment.v1", "method": method,
                 "scan": {"nli_record_id": rec, "license_slug": "public-domain-free-use", "rights_decision": {"decision": rights}},
                 "pages": [{"canvas_index": 0, "canvas_id": f"{rec}/c0", "canvas_size": list(CANVAS), "status": "aligned",
                            "quality": "high", "lines": page_lines}]}
    (root / out / pby).mkdir(parents=True)
    (root / out / pby / "alignment.json").write_text(json.dumps(alignment, ensure_ascii=False), encoding="utf-8")
    (root / "pby" / "txt").mkdir(parents=True, exist_ok=True)
    (root / "pby" / "txt" / f"m{pby}.txt").write_text(text, encoding="utf-8")
    sub = bl.ocr_subdir(method)
    for d in ("img", sub):
        (root / "work" / rec / d).mkdir(parents=True, exist_ok=True)
    if not (root / "work" / rec / "img" / "c0000.jpg").exists():
        Image.new("RGB", IMAGE, "white").save(root / "work" / rec / "img" / "c0000.jpg")
    (root / "work" / rec / sub / "c0000.tsv").write_text(_tsv(ocr), encoding="utf-8")


POINTED_FULL = [f"{SHIN}{HOLAM}לוֹם עוֹלָם", "בַּיִת גָּדוֹל", f"{SHIN}{PATAH}בָּת טוֹבָה"]
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


def test_ocr_subdir_follows_the_aligner_cache():
    assert bl.ocr_subdir({"ocr_engine": "tesseract 5.5.3 -l heb --psm 3"}) == "ocr"
    assert bl.ocr_subdir({"ocr_engine": "tesseract -l heb", "ocr_model": "r6@73eb18e0"}) == "ocr-r6@73eb18e0"
    assert bl.ocr_subdir({"ocr_engine": "tesseract 5.5.3 -l yid --psm 3"}) == "ocr-yid"


def test_r6_placed_record_reads_its_own_page_ocr(tmp_path):
    """Refinement and the line-OCR gate must use the placer's TSVs, not stock ones (hocrgen#155 cache layout)."""
    r = tmp_path / "f8f"
    r6 = {"ocr_engine": "tesseract 5.5.3 -l heb --psm 3", "ocr_model": "r6@73eb18e0"}
    _record(r, "777", "7", ["ספר חדש ויפה", "עיר גדולה מאד"], method=r6)
    # a stock TSV that disagrees with every line: reading it would drop them all
    (r / "work" / "777" / "ocr").mkdir()
    (r / "work" / "777" / "ocr" / "c0000.tsv").write_text(
        _tsv([([10, 10 + 20 * i, 180, 15], ["קקקק", "רררר"]) for i in range(2)]), encoding="utf-8")
    out = tmp_path / "set"
    assert bl.main(["build", str(out), "--root", str(r), "--no-images"]) == 0
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2 and all(row["page_ocr"] == "ocr-r6@73eb18e0" and row["ocr_similarity"] == 1.0 for row in rows)
    (r / "work" / "777" / "ocr-r6@73eb18e0" / "c0000.tsv").unlink()
    with pytest.raises(SystemExit, match="page OCR missing"):  # never falls back to stock
        bl.main(["build", str(tmp_path / "set2"), "--root", str(r), "--no-images"])


def test_prefer_placer_picks_the_r6_second_pass(tmp_path):
    r = tmp_path / "f8f"
    lines = ["ספר חדש ויפה", "עיר גדולה מאד", "נהר ארוך וצר"]
    _record(r, "888", "8", lines)  # stock pass in out/
    _record(r, "888", "8", lines, out="out_r6", method={"ocr_engine": "tesseract 5.5.3 -l heb --psm 3", "ocr_model": "r6@73eb18e0"})
    with pytest.raises(SystemExit, match="several alignment sources"):
        bl.main(["build", str(tmp_path / "a"), "--root", str(r), "--no-images"])
    out = tmp_path / "b"
    assert bl.main(["build", str(out), "--root", str(r), "--no-images", "--prefer-placer", "r6@73eb18e0"]) == 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = [json.loads(x) for x in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["alignment"] for row in rows} == {"out_r6/8/alignment.json"} and len(rows) == 3
    assert summary["lines_by_book_and_ocr_placer"] == {"888 888": {"r6@73eb18e0": 3}}
    choice = summary["ocr_placer_choice"]["888"]
    assert choice["chosen"] == {"root": str(r), "dir": "out_r6", "ocr_placer": ["r6@73eb18e0"], "pby_ids": ["8"]}
    assert choice["skipped"] == [{"root": str(r), "dir": "out", "ocr_placer": ["stock"], "pby_ids": ["8"]}]
    out = tmp_path / "c"  # the preference order decides; a placer no source has is skipped
    assert bl.main(["build", str(out), "--root", str(r), "--no-images", "--prefer-placer", "r7", "--prefer-placer", "stock"]) == 0
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    assert summary["lines_by_book_and_ocr_placer"] == {"888 888": {"stock": 3}}
    assert summary["prefer_placer"] == ["r7", "stock"]


def test_same_record_under_two_roots_still_fails(tmp_path, root):
    other = tmp_path / "other"
    _record(other, "222", "2", ["ספר חדש ויפה"])
    with pytest.raises(SystemExit, match="several alignment sources"):
        bl.main(["build", str(tmp_path / "set"), "--root", str(root), "--root", str(other), "--pointed", "333", "444"])


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
    assert summary["unpointed_with_pointed_edition"] == []
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


def test_build_v2_fails_closed_on_unclassified_pointed_edition(tmp_path, root):
    _record(root, "666", "6", POINTED_FULL)  # pointed edition text, print not classified
    with pytest.raises(SystemExit, match="666"):
        _build(tmp_path, root, "--keep-pointed")
    assert not (tmp_path / "set").exists()  # nothing written
    summary, rows = _build(tmp_path, root, "--keep-pointed", "--unpointed", "666")
    labels = [r["text"] for r in rows if r["record_id"] == "666"]
    assert labels and not any(bl.NIQQUD.search(t) for t in labels)  # asserted unpointed print: niqqud stripped
    assert summary["unpointed_with_pointed_edition"] == ["666"] and summary["unpointed_records"] == ["666"]
    with pytest.raises(SystemExit, match="both"):
        _build(tmp_path / "c", root, "--unpointed", "333")
    v1, _ = _build(tmp_path / "d", root, "--schema", "v1")  # v1 (frozen bynli_lines_v1) does not fail
    assert v1["schema"].endswith(".v1")


def _as_ia(root: Path, pby: str, identifier: str, *, gate: str = bl.IA_GATE, decision: str = "accepted") -> None:
    """Rewrite one fixture record's alignment as an Internet Archive scan (``scan.record_id`` = identifier)."""
    path = root / "out" / pby / "alignment.json"
    al = json.loads(path.read_text(encoding="utf-8"))
    old = al["scan"]["nli_record_id"]
    al["scan"] = {"source": "internet_archive", "record_id": identifier, "ia_identifier": identifier,
                  "source_class": "ia_library_scan_no_licence_field",
                  "rights_decision": {"gate": gate, "decision": decision}}
    path.write_text(json.dumps(al, ensure_ascii=False), encoding="utf-8")
    (root / "work" / old).rename(root / "work" / identifier)


def test_record_id_and_rights_for_both_sources():
    nli = {"nli_record_id": "111", "license_slug": "public-domain-free-use", "rights_decision": {"decision": "accepted"}}
    assert bl.record_id(nli) == "111" and bl.rights_accepted(nli)
    assert not bl.rights_accepted({**nli, "license_slug": "public-domain-non-commercial-use"})
    ia = {"source": "internet_archive", "record_id": "abc00x", "rights_decision": {"gate": bl.IA_GATE, "decision": "accepted"}}
    assert bl.record_id(ia) == "abc00x" and bl.rights_accepted(ia)
    # An IA scan is never accepted on an NLI-style verdict, nor on a rejected IA one.
    assert not bl.rights_accepted({**ia, "rights_decision": {"decision": "accepted"}})
    assert not bl.rights_accepted({**ia, "rights_decision": {"gate": bl.IA_GATE, "decision": "rejected"}})
    assert bl.line_id("990012", 3, 7) == "nli990012_c0003_l007"
    assert bl.line_id("abc00x", 3, 7, source="internet_archive") == "ia_abc00x_c0003_l007"


def test_line_id_prefix_follows_the_scan_source_not_the_id_shape():
    # An all-digit IA identifier still gets the ia_ prefix; an NLI record keeps nli.
    assert bl.line_id("1234567", 0, 1, source=bl.IA_SOURCE) == "ia_1234567_c0000_l001"
    assert bl.line_id("1234567", 0, 1) == bl.line_id("1234567", 0, 1, source=None) == "nli1234567_c0000_l001"
    assert bl.line_id("abc00x", 0, 1) == "nliabc00x_c0000_l001"  # no source given: the NLI default


def test_cap_per_book_ranks_ia_lines_by_their_ia_line_ids():
    keys = [("12345", 0, n) for n in range(6)]
    as_ia, _ = bl.cap_per_book(keys, 3, (), {"12345": bl.IA_SOURCE})
    as_nli, _ = bl.cap_per_book(keys, 3, ())
    rank = lambda prefix: sorted(keys, key=lambda k: bl.hashlib.sha256(f"{prefix}12345_c0000_l{k[2]:03d}".encode()).hexdigest())[:3]  # noqa: E731
    assert set(as_ia) == set(rank("ia_")) and set(as_nli) == set(rank("nli"))


def test_build_names_an_all_digit_ia_identifier_by_its_source(tmp_path, root):
    _as_ia(root, "2", "20191010")
    _, rows = _build(tmp_path, root, "--keep-pointed", "--no-images")
    assert {r["id"][:12] for r in rows if r["record_id"] == "20191010"} == {"ia_20191010_"}


def test_build_reads_ia_alignments_and_skips_ia_items_the_gate_did_not_accept(tmp_path, root):
    _as_ia(root, "2", "sefer00test")
    _as_ia(root, "5", "google00goog", decision="rejected")
    summary, rows = _build(tmp_path, root, "--keep-pointed", "--no-images")
    ia_rows = [r for r in rows if r["record_id"] == "sefer00test"]
    assert len(ia_rows) == 4 and all(r["id"].startswith("ia_sefer00test_c0000_l") for r in ia_rows)
    assert all(r["split"] == "train" for r in ia_rows)
    assert all(r["scan_source"] == "internet_archive" and r["source_class"] == "ia_library_scan_no_licence_field" for r in ia_rows)
    assert not any("scan_source" in r or "source_class" in r for r in rows if r["record_id"] != "sefer00test")
    assert not any(r["record_id"] == "google00goog" for r in rows)
    assert summary["lines_by_book_and_ocr_placer"]["sefer00test sefer00test"] == {"tessdata:r6": 4}
