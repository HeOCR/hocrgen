"""Network- and engine-free tests for hocrgen.tools.wikisource_lines (R8 line sets from Wikisource proofread pages)."""

from __future__ import annotations

import argparse
import hashlib
from collections import Counter
import json
import unicodedata
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.tools import wikisource_coverage as cov
from hocrgen.tools import wikisource_lines as wl

WIDTH, HEIGHT = 960, 700
LINES = [
    "אמר רבי יוחנן כל המתפלל צריך שיכוין את לבו",
    "ולמה כתב מבראשית להודיע כח גבורתו לעמו",
    "שנאמר כח מעשיו הגיד לעמו לתת להם נחלת גוים",
    "אמר ריש לקיש כביכול דבר היה מפי הקב״ה ז״ל",
    "ואלא ליפרע מן הרשעים שמאבדין את העולם שנברא",
    "וליתן שכר טוב לצדיקים שמקיימין את העולם שנברא",
]


def _misread(text: str) -> str:
    """OCR-like noise on every eighth letter: the label must stay the page text."""

    out, n = [], 0
    for ch in text:
        if "א" <= ch <= "ת":
            n += 1
            if n % 8 == 0:
                ch = "ט" if ch != "ט" else "ס"
        out.append(ch)
    return "".join(out)


def _tsv(lines: list[tuple[int, str]]) -> str:
    """Tesseract TSV of a 2x upscale: one line per (row, text), right to left, boxes in upscaled pixels."""

    rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
    for n, (row, text) in enumerate(lines):
        top = 2 * (60 + 40 * row)
        right = 2 * 900
        for j, word in enumerate(text.split()):
            left = right - (j + 1) * 2 * 60
            rows.append(f"5\t1\t1\t1\t{n}\t{j}\t{left + 4}\t{top}\t{2 * 56}\t{2 * 24}\t90.0\t{word}")
    return "\n".join(rows) + "\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot(root: Path, pages: dict[str, dict], indexes: dict[str, dict]) -> tuple[Path, Path]:
    """A tranche-like snapshot (indexes.json, pages.jsonl, text/, assets/) and the coverage OCR cache."""

    snap, cache = root / "snapshot", root / "ocr_cache"
    for d in (snap / "text", snap / "assets", cache):
        d.mkdir(parents=True, exist_ok=True)
    records = []
    for n, (item, spec) in enumerate(sorted(pages.items())):
        key, number = item.split("__p")
        text = spec["text"]
        (snap / "text" / f"{item}.txt").write_text(text + "\n", encoding="utf-8")
        img = snap / "assets" / f"{item}.jpg"
        Image.new("L", (WIDTH, HEIGHT), 255 - n).save(img, quality=95)
        sha = _sha(img.read_bytes())
        (cache / f"{sha}.heb.psm3.x2.tsv").write_text(_tsv(spec["ocr"]), encoding="utf-8")
        record = {"index_key": key, "source_item_id": item, "page_number": int(number), "quality": spec.get("quality", 3),
                  "page_title": f"עמוד:{key}.pdf/{int(number)}", "revision_id": 1000 + n,
                  "text_path": f"text/{item}.txt", "text_sha256": _sha(text.encode("utf-8")),
                  "transcription_coverage": "partial_page" if spec.get("crop") else "full_page",
                  "image": {"path": f"assets/{item}.jpg", "sha256": sha, "width": WIDTH, "height": HEIGHT,
                            "rendered_from": {"render_url": f"https://upload.example/page{int(number)}-960px-x.jpg"}}}
        if spec.get("crop"):
            record["crop"] = spec["crop"]
        if spec.get("excluded"):
            record["excluded_spans"] = {"spans": spec["excluded"]}
        records.append(record)
    (snap / "pages.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")
    full = {k: {"index_key": k, "index_title": f"מפתח:{k}.pdf", "scan_source_origin": "hebrewbooks",
                "scan_rights": {"digitized_by_google": False},
                "commons_file": {"title": f"File:{k}.pdf", "sha1": "ab" * 20, "description_url": f"https://commons.example/{k}"},
                **v} for k, v in indexes.items()}
    (snap / "indexes.json").write_text(json.dumps({"indexes": list(full.values())}, ensure_ascii=False), encoding="utf-8")
    return snap, cache


def _args(out: Path, snap: Path, cache: Path, **kw) -> argparse.Namespace:
    base = dict(out=str(out), snapshot=str(snap), ocr_cache=[str(cache)], hires=None, policy="C", eval_set=None,
                split_manifest=None, line_verify=None, hold_out=None, dev=None, reserve=None, facts=None,
                rabbinic_dev_source=None, min_score=wl.MIN_SCORE, max_lines_per_book=0, cap_dev=False, no_images=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _no_gate(page, indexes, root):
    return []


def _rights(watermarks: dict | None = None):
    """Stand-in for the committed registry: ws_index_4 has no justification, the rest ``rj:<index_key>``."""

    def rights(page, index):
        if index["index_key"] == "ws_index_4":
            return "wikisource_rights_justification_missing", {"rights_justification_id": None}
        fields = {"rights_justification_id": f"rj:{index['index_key']}"}
        if (watermarks or {}).get(page["source_item_id"]):
            fields["google_watermark_bbox"] = watermarks[page["source_item_id"]]
        return None, fields

    return rights


def _work(title: str, *creators: str) -> dict:
    return {"work": {"title": title, "creators": [{"name": c} for c in creators]}}


# --- Units ------------------------------------------------------------------------------------------------------


def test_normalised_offsets_match_the_coverage_alignment_string() -> None:
    text = "בְּרֵאשִׁית בָּרָא[1] אֱלֹהִים, ﬠולם! ז״ל 12"
    norm, offsets = wl.normalised_with_offsets(text)
    assert norm == cov.alignment_string(text)
    assert len(offsets) == len(norm)
    assert text[offsets[0]] == "ב" and text[offsets[-1]] == "2"


def test_title_core_matches_other_volumes_and_editions() -> None:
    indexes = {
        "hyman1": _work("תולדות תנאים ואמוראים חלק ראשון", "אהרן הימן"),
        "hyman2": _work("תולדות תנאים ואמוראים חלק שני", "אהרן הימן"),
        "dorot1": _work("ספר דורות הראשונים א'.pdf", "יצחק אייזיק הלוי"),
        "dorot3": _work("דורות ראשונים, חלק ג' - מאחר החורבן עד חתימת המשנה", "יצחק אייזיק הלוי"),
        "other": _work("ספר הערכים", "אהרן הימן"),
    }
    related = wl.related_works(indexes, ["hyman1", "dorot1"])
    assert related == {"dorot3": ["dorot1"], "hyman2": ["hyman1"]}
    assert wl.same_creator_other_works(indexes, ["hyman1", "dorot1"], related) == {"other": ["hyman1"]}


def test_policy_c_holds_out_whole_indexes_and_drops_pages() -> None:
    indexes = {k: _work(k) for k in ("a2", "tst", "lvval", "lvtrain", "free")}
    pages = [{"index_key": k, "source_item_id": f"{k}__p{n:04d}"} for k in indexes for n in (1, 2)]
    split = {"items": [{"item_id": f"{wl.SOURCE_ID}:{p['source_item_id']}",
                        "split": {"tst": "test", "lvval": "validation"}.get(p["index_key"], "train")} for p in pages]}
    eval_set = {"items": [{"item_id": f"{wl.SOURCE_ID}:a2__p0001", "index_key": "a2", "stratum": "adjudicated"},
                          {"item_id": f"{wl.SOURCE_ID}:free__p0002", "index_key": "free", "stratum": "single_reviewer"}]}
    lv = {"pages": [{"page_id": f"{wl.SOURCE_ID}:lvval__p0001"}, {"page_id": f"{wl.SOURCE_ID}:lvtrain__p0001"},
                    {"page_id": "benyehuda_nli_aligned:x"}]}
    ex = wl.exclusions("C", indexes, pages, eval_set=eval_set, split_manifest=split, line_verify=[lv])
    assert ex.held_out == {"a2": ["audit2"], "tst": ["release_test"], "lvval": ["line_verify_index_in_heldout_split"]}
    assert ex.dropped_pages == {"lvtrain__p0001": ["line_verify_page"], "lvval__p0001": ["line_verify_page"],
                                "a2__p0001": ["eval_set_page"], "free__p0002": ["eval_set_page"]}
    strict = wl.exclusions("A", indexes, pages, eval_set=eval_set, split_manifest=split, line_verify=[lv])
    assert set(strict.held_out) == {"a2", "tst", "lvval", "lvtrain"}


def test_text_order_drops_a_running_head_matched_elsewhere() -> None:
    drops: Counter = Counter()
    cands = [{"line_index": 0, "span": [300, 310]}] + [{"line_index": i, "span": [i * 40, i * 40 + 35]} for i in range(1, 6)]
    kept = wl.in_text_order(cands, drops)
    assert [c["line_index"] for c in kept] == [1, 2, 3, 4, 5]
    assert drops["out_of_text_order"] == 1


def test_crop_gate_uses_box_and_regions() -> None:
    crop = {"box_px": [0, 0, 500, 500], "regions_px": [[0, 0, 500, 200]]}
    assert wl.in_crop((10, 10, 100, 40), crop)
    assert not wl.in_crop((10, 300, 100, 330), crop)
    assert not wl.in_crop((600, 10, 700, 40), {"box_px": [0, 0, 500, 500]})


# --- Build ------------------------------------------------------------------------------------------------------


def _pool(tmp_path: Path) -> tuple[Path, Path]:
    plain = "\n".join(LINES)
    pointed = "בְּרֵאשִׁית בָּרָא אֱלֹהִים אֵת הַשָּׁמַיִם וְאֵת הָאָרֶץ וְהָאָרֶץ הָיְתָה תֹהוּ וָבֹהוּ"
    pages = {
        # a clean page, its OCR misread; one line carries a footnote mark, one an excluded span
        "ws_index_1__p0001": {"text": plain.replace("לעמו\n", "לעמו[1]\n", 1) + "\n[1] הערה קצרה של המדפיס כאן",
                              "ocr": [(i, _misread(t)) for i, t in enumerate(LINES)]},
        # a partial page: only the first three lines are inside the crop
        "ws_index_1__p0002": {"text": plain, "ocr": [(i, _misread(t)) for i, t in enumerate(LINES)],
                              "crop": {"box_px": [0, 0, WIDTH, 60 + 40 * 3], "status": "resolved"}},
        "ws_index_2__p0001": {"text": plain, "ocr": [(i, _misread(t)) for i, t in enumerate(LINES)], "quality": 4},
        "ws_index_3__p0001": {"text": pointed, "ocr": [(0, cov.alignment_string(pointed))]},  # pointed page
        "ws_index_4__p0001": {"text": plain, "ocr": [(i, _misread(t)) for i, t in enumerate(LINES)]},  # NLI origin
        "ws_index_5__p0001": {"text": plain, "ocr": [(i, _misread(t)) for i, t in enumerate(LINES)]},  # held out
    }
    excl_start = plain.index("ואלא")
    pages["ws_index_2__p0001"]["excluded"] = [{"start": excl_start, "end": excl_start + 4}]
    indexes = {k: _work(f"ספר בדיקה {k}") for k in ("ws_index_1", "ws_index_2", "ws_index_3", "ws_index_4", "ws_index_5")}
    return _snapshot(tmp_path, pages, indexes)


def test_build_labels_with_page_text_and_verifies(tmp_path: Path) -> None:
    snap, cache = _pool(tmp_path)
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"indexes": {"ws_index_2": {"rabbinic": True, "genre": "halakha", "name": "two",
                                                            "script": "rashi"}}}), encoding="utf-8")
    out = tmp_path / "lines"
    summary = wl.build(_args(out, snap, cache, dev=["ws_index_2=dev-two"], hold_out=["ws_index_5=test"],
                             facts=str(facts)), gate=_no_gate, rights=_rights())
    rows = [json.loads(ln) for ln in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = {r["id"]: r["text"] for r in rows}
    # labels are the page text, never the misread OCR
    assert set(texts.values()) <= set(LINES)
    assert not any(_misread(t) in texts.values() for t in LINES if _misread(t) != t)
    # gershayim kept
    assert any("הקב״ה ז״ל" in t for t in texts.values())
    p1 = sorted(r["text"] for r in rows if r["source_item_id"] == "ws_index_1__p0001")
    assert LINES[1] not in p1 and len(p1) == 5  # the footnote-mark line goes; the note line has no box
    p2 = sorted(r["text"] for r in rows if r["source_item_id"] == "ws_index_1__p0002")
    assert p2 == sorted(LINES[:3])  # crop
    dev = [r for r in rows if r["split"] == "dev"]
    assert {r["index_key"] for r in dev} == {"ws_index_2"} and LINES[4] not in {r["text"] for r in dev}  # excluded span
    assert all(r["script"] == "rashi" and r["rabbinic"] and r["attestation"] == "wikisource_quality4_validated" for r in dev)
    assert not any(r["index_key"] in {"ws_index_3", "ws_index_4", "ws_index_5"} for r in rows)
    assert summary["dropped_pages"]["pointed_page"] == 1
    assert summary["dropped_pages"]["wikisource_rights_justification_missing"] == 1
    assert summary["dropped_pages"]["index_held_out"] == 1
    assert summary["dropped"]["footnote_marker"] == 1 and summary["dropped"]["excluded_span_on_scan"] == 1
    for r in rows:
        assert r["text_licence"] == "CC BY-SA 4.0" and "oldid=" in r["attribution"]
        assert r["reference_eligible"] is False and r["adjudication_status"] == "not_adjudicated"
        assert r["rights_justification_id"] == f"rj:{r['index_key']}" and r["scan_source"] == "wikimedia_commons"
        assert (out / r["image"]).is_file() and (out / r["image"]).with_suffix(".gt.txt").read_text(encoding="utf-8") == r["text"] + "\n"
    assert summary["rabbinic_dev"]["lines_in_this_set"] == len(dev) and summary["rabbinic_dev"]["note"] is None
    assert summary["reserve"]["waived"] is True and "5(b)" in summary["reserve"]["obligation"]
    assert summary["release_notice"]["share_alike"] is True
    assert summary["manifest_sha256"] == _sha((out / "manifest.jsonl").read_bytes())
    assert wl.verify(out) == []
    # verify catches a held-out row and niqqud in a label
    bad = dict(rows[0], index_key="ws_index_5", text="בְּרֵאשִׁית")
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [bad] + rows[1:]), encoding="utf-8")
    problems = wl.verify(out)
    assert any("held-out" in p for p in problems) and any("niqqud" in p for p in problems)


def test_watermark_lines_dropped_and_cap(tmp_path: Path) -> None:
    snap, cache = _pool(tmp_path)
    out = tmp_path / "lines"
    # the watermark box (fractions of the page) covers the first printed line of ws_index_2 p. 1
    box = [0.5, (60 - 2) / HEIGHT, 0.45, 10 / HEIGHT]
    summary = wl.build(_args(out, snap, cache, max_lines_per_book=2, no_images=True), gate=_no_gate,
                       rights=_rights({"ws_index_2__p0001": box}))
    rows = [json.loads(ln) for ln in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert summary["dropped"]["google_watermark_overlap"] == 1
    assert all(r["google_watermark_bbox"] == box for r in rows if r["index_key"] == "ws_index_2")
    assert all(n <= 2 for n in summary["lines"]["train"].values())
    assert all(r["image_sha256"] is None for r in rows)
    assert wl.watermark_box_px(box, WIDTH, HEIGHT) == (480, 58, 912, 68)


def test_dev_index_cannot_be_held_out(tmp_path: Path) -> None:
    snap, cache = _pool(tmp_path)
    with pytest.raises(SystemExit, match="held out"):
        wl.build(_args(tmp_path / "x", snap, cache, dev=["ws_index_5"], hold_out=["ws_index_5=test"]), gate=_no_gate,
                 rights=_rights())


def test_verify_accepts_maqaf_and_rejects_points() -> None:
    assert not wl.NIQQUD_ANY.search("המאד־נעלה ׀ סוף׃")
    assert wl.NIQQUD_ANY.search(unicodedata.normalize("NFD", "בְּ"))
