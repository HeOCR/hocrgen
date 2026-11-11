"""reshumot_lines: printed-modern training lines from born-digital Reshumot booklets (decision 0018).

The builds run on the F8e2 fixture (``tests/fixtures/reshumot_glyph_pages/snapshot``): ten real pinned pages, six of
non-eval booklets and four of eval booklets. Nothing needs poppler or pdfminer: the PDF facts and the other pages'
glyph layers are stubbed, and every line is re-derived from the committed glyph layer and render.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.split.eval_reserved import EvalReservedUnitError
from hocrgen.tools import reshumot_lines as rl

FIXTURE = Path(__file__).parent / "fixtures" / "reshumot_glyph_pages" / "snapshot"
EVAL_SCRIPT = Path.home() / "agents/environments/opensource/projects/heocr/tasks/eval-domains/scripts/reshumot_candidates.py"
NON_EVAL = {"reshumot:kovetz_hatakanot_10333", "reshumot:kovetz_hatakanot_6517", "reshumot:kovetz_hatakanot_7070",
            "reshumot:sefer_hachukim_2663", "reshumot:sefer_hachukim_2745", "reshumot:sefer_hachukim_3085"}
EVAL = {"reshumot:kovetz_hatakanot_8764", "reshumot:sefer_hachukim_2574", "reshumot:sefer_hachukim_3579"}
INDESIGN = {"Creator": "Adobe InDesign CS6 (Windows)", "Producer": "Adobe PDF Library 10.0.1"}
FONT_ROW = ["ABCDEF+HadasaMFOMedium", "CID", "TrueType", "Identity-H", "yes", "yes", "yes", "54", "0"]


def _blank_layer(width: float = 481.89, height: float = 680.32) -> dict:
    return {"schema": "hocrgen.pdf_glyph_layer.v1", "page": {"number": 1, "width": width, "height": height, "rotation": 0},
            "fonts": [], "glyphs": [], "fills": [], "strokes": [], "images": [], "actual_text": []}


def _glyph(text: str, x: float, flags: int = 0) -> list:
    return [0, text, x, 100.0, x + 5.0, 110.0, x, 108.0, 10.0, 0, flags, 1]


def _facts(pages: dict[int, dict], **info) -> dict:
    return {"info": {**INDESIGN, **info}, "xmp": "", "fonts": [FONT_ROW], "image_rows": [], "page_count": len(pages),
            "pages": {n: {"layer": rl.page_layer_facts(layer), "size": (481.89, 680.32)} for n, layer in pages.items()}}


# --- the vendored tier-A rules ------------------------------------------------------------------------------------


@pytest.mark.skipif(not EVAL_SCRIPT.is_file(), reason="heocr-eval's task scripts are not on this machine")
def test_vendored_tier_a_rules_are_heocr_evals() -> None:
    source = EVAL_SCRIPT.read_text(encoding="utf-8")
    assert hashlib.sha256(EVAL_SCRIPT.read_bytes()).hexdigest() == rl.TIER_A_ORIGIN["sha256"]
    namespace: dict = {}
    exec(compile(source.split("def main")[0].replace('split = json.load', '# split = json.load').replace(
        'EVAL = {u', '# EVAL = {u'), str(EVAL_SCRIPT), "exec"), namespace)  # rules only, no file reads
    assert {name: rx.pattern for name, rx in namespace["TIER_A"].items()} == {name: rx.pattern for name, rx in rl.TIER_A.items()}
    for line in ["סעיף 12(א) לחוק", "(ב) לפי 1.1.2012", "www.gov.il", "ש\u05b8\u05c1לו\u05b9ם", ". . . . 12", "(פתוח", "רגיל"]:
        assert namespace["flags_for"](line)[0] == rl.tier_a_flags(line)


def test_tier_a_flags_and_labels() -> None:
    assert rl.tier_a_flags("התשפ\"ב-2022") == []  # a year after a letter is no compound number
    assert rl.tier_a_flags("מיום 1.1.2012") == ["compound_number"]
    assert rl.tier_a_flags("סעיף 3(ב)") == ["compound_number"]
    assert rl.tier_a_flags("(פתוח") == ["bracket_order_or_balance"]
    assert rl.tier_a_flags("db(A)") == ["latin"]
    assert "pua_or_replacement" in rl.tier_a_flags("א\ue001")
    # Labels: niqqud stripped; geresh, gershayim, maqaf and dashes kept as printed.
    assert rl.label("המ\u05b4ינהל  ת״א ג׳ בין־משרדית — –") == "המינהל ת״א ג׳ בין־משרדית — –"
    assert rl.bad_code_points("א\ue000") and rl.bad_code_points("(cid:12)") and rl.bad_code_points("\ufffd")
    assert not rl.bad_code_points("רגיל ״ ׳ ־ — 12")


# --- the born-digital check ---------------------------------------------------------------------------------------


def test_born_digital_check_passes_an_indesign_booklet_and_records_its_evidence() -> None:
    layer = _blank_layer()
    layer["glyphs"] = [_glyph("א", 50), _glyph("ב", 60)]
    layer["images"] = [[0, 10.0, 10.0, 60.0, 60.0]]  # an emblem: small
    check = rl.born_digital_check(_facts({1: layer, 2: _blank_layer()}))
    assert check["passed"] and check["reasons"] == []
    assert check["evidence"]["creator"] == INDESIGN["Creator"] and check["evidence"]["embedded_fonts"] == ["HadasaMFOMedium"]
    assert check["evidence"]["pages_checked"] == 2 and check["evidence"]["pages_with_images"] == 1


@pytest.mark.parametrize("producer", ["ABBYY FineReader 12", "Adobe Acrobat 9.0 Paper Capture Plug-in", "Tesseract 4.1",
                                      "OmniPage CSDK 21", "OCRmyPDF 13.4", "Canon iR-ADV Scan"])
def test_born_digital_check_refuses_ocr_or_scan_producers(producer: str) -> None:
    check = rl.born_digital_check(_facts({1: _blank_layer()}, Producer=producer))
    assert not check["passed"] and "ocr_producer" in check["reasons"] and check["evidence"]["ocr_tools"] == [producer]


def test_born_digital_check_reads_the_xmp_tools() -> None:
    facts = _facts({1: _blank_layer()})
    facts["xmp"] = "<rdf:Description xmp:CreatorTool='ABBYY FineReader 15' pdf:Producer='x'/>"
    assert rl.born_digital_check(facts)["reasons"] == ["ocr_producer"]


def test_born_digital_check_refuses_a_scan_under_an_invisible_text_layer() -> None:
    scan = _blank_layer()
    scan["images"] = [[0, 0.0, 0.0, 481.89, 680.32]]
    scan["glyphs"] = [_glyph("א", 50, flags=1), _glyph("ב", 60, flags=1)]
    check = rl.born_digital_check(_facts({1: _blank_layer(), 2: scan}))
    assert check["reasons"] == ["full_page_image", "image_only_page_under_invisible_text", "invisible_text_over_page_image"]
    # Invisible text with no image at all and no visible text is refused too (an image-only page, strips or not).
    hidden = _blank_layer()
    hidden["glyphs"] = [_glyph("א", 50, flags=1)]
    assert rl.born_digital_check(_facts({1: hidden}))["reasons"] == ["image_only_page_under_invisible_text"]
    # Invisible glyphs beside visible born-digital text and no page image (a tagged copy) are not a scan.
    tagged = _blank_layer()
    tagged["glyphs"] = [_glyph("א", 50, flags=1), _glyph("ב", 60)]
    assert rl.born_digital_check(_facts({1: tagged}))["passed"]


def test_born_digital_check_fails_closed() -> None:
    facts = _facts({1: _blank_layer()})
    facts["page_count"] = 2
    assert rl.born_digital_check(facts)["reasons"] == ["page_layer_missing"]
    facts = _facts({1: _blank_layer()})
    facts["fonts"] = [FONT_ROW[:4] + ["no", "no", "no", "54", "0"]]
    assert rl.born_digital_check(facts)["reasons"] == ["no_embedded_fonts"]
    facts = _facts({1: _blank_layer()})
    facts["image_rows"] = [["1", "0", "image", "2480", "3508", "gray", "1", "8", "jpeg", "no", "5", "0", "300", "300", "1M", "9%"]]
    assert rl.born_digital_check(facts)["reasons"] == ["full_page_image"]  # pdfimages alone: an A4 page at 300 ppi


# --- build on the fixture -----------------------------------------------------------------------------------------


@pytest.fixture()
def tranche(tmp_path: Path) -> dict:
    """A copy of the fixture snapshot with a stub PDF per booklet (the entries pin its sha256) and a layer stub."""

    snapshot = tmp_path / "snapshot"
    shutil.copytree(FIXTURE, snapshot)
    cache = tmp_path / "pdf"
    cache.mkdir()
    entries = [json.loads(line) for line in (snapshot / "entries.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    for entry in entries:
        slug = rl.unit_slug(rl.entry_unit(entry))
        content = f"%PDF stub {slug}".encode()
        (cache / f"{slug}.pdf").write_bytes(content)
        entry["pdf"]["sha256"] = hashlib.sha256(content).hexdigest()
    (snapshot / "entries.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries), encoding="utf-8")
    return {"snapshot": snapshot, "cache": cache, "entries": entries, "out": tmp_path / "set"}


def _layers_stub(snapshot: Path):
    committed = {}
    for line in (snapshot / "entries.jsonl").read_text(encoding="utf-8").splitlines():
        entry = json.loads(line)
        layer = json.loads(rl.read_glyph_layer_bytes(snapshot / entry["text"]["extraction"]["raw_local_path"]))
        committed[(rl.unit_slug(rl.entry_unit(entry)), entry["page"]["pdf_page_index"])] = layer

    def load(layer_dir, slug, page_count, pdf):
        return {n: copy.deepcopy(committed.get((slug, n), _blank_layer())) for n in range(1, page_count + 1)}

    return load


def _args(tranche: dict, **overrides) -> argparse.Namespace:
    values = {"out": str(tranche["out"]), "snapshot": str(tranche["snapshot"]), "pdf_cache": str(tranche["cache"]),
              "page_layers": None, "max_lines_per_booklet": rl.DEFAULT_MAX_LINES, "dev_per_stratum": 1, "workers": 1,
              "created_at": "2026-11-11", "signature": "— test"}
    values.update(overrides)
    return argparse.Namespace(**values)


def _facts_for(producers: dict[str, str] | None = None):
    def facts_for(pdf: Path, layers):
        facts = _facts(dict(layers))
        facts["page_count"] = len(layers)
        if producers and pdf.stem in producers:
            facts["info"]["Producer"] = producers[pdf.stem]
        return facts

    return facts_for


def _build(tranche: dict, monkeypatch: pytest.MonkeyPatch, producers: dict[str, str] | None = None, **overrides) -> dict:
    monkeypatch.setattr(rl, "load_page_layers", _layers_stub(tranche["snapshot"]))
    return rl.build(_args(tranche, **overrides), facts_for=_facts_for(producers))


def _rows(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]


def test_build_writes_the_bynli_v2_shape_from_non_eval_booklets_only(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _build(tranche, monkeypatch)
    out = tranche["out"]
    rows = _rows(out)
    assert rows and {row["unit_id"] for row in rows} <= NON_EVAL
    # Eval booklets are counted from metadata and never opened.
    check = summary["eval_reserved_check"]
    assert check["input_units"] == {"non_eval": 6, "eval": 3} and check["input_pages"] == {"non_eval": 6, "eval": 4}
    assert check["eval_rows"] == 0 and check["unassigned_rows"] == 0 and check["output_rows_by_status"] == {"non_eval": len(rows)}
    assert set(summary["booklets"]) == NON_EVAL
    # The page the tranche gate rejects gives no line.
    assert summary["refused_pages"] == {"kovetz_hatakanot_7070__p0003": "page_gate:extraction_order_not_verified"}
    # bynli_lines_v2 layout: <split>/<booklet>/<id>.png + .gt.txt, one per manifest row (make_lstmf globs */*/*.png).
    assert sorted(p.relative_to(out).as_posix() for p in out.glob("*/*/*.png")) == sorted(row["image"] for row in rows)
    for row in rows:
        assert (out / row["image"]).with_suffix(".gt.txt").read_text(encoding="utf-8") == row["text"] + "\n"
        assert row["label_source"] == "publisher_glyph_layer" and row["capture"] == "rendered"
        assert row["reference_eligible"] is False and row["proposed_node_hint"] == "new_printed"
        assert row["license"] == "PD-IL" and row["attribution"].startswith("Reshumot") and row["publisher_url"].startswith("https://")
        assert row["series"] in {"sefer_hachukim", "kovetz_hatakanot"} and row["publish_date"] and row["page"] >= 1
        assert not re.search("[\u0591-\u05bd\u05bf\u05c1\u05c2\u05c4\u05c5\u05c7]", row["text"])
    # Every kept line is a line of the committed page text, in order.
    for entry_id in {row["entry_id"] for row in rows}:
        committed = [line for line in (FIXTURE / "text" / f"{entry_id}.txt").read_text(encoding="utf-8").split("\n") if line]
        for row in (r for r in rows if r["entry_id"] == entry_id):
            assert committed[row["line_index"]] == row["text"]
    assert summary["manifest_sha256"] == hashlib.sha256((out / "manifest.jsonl").read_bytes()).hexdigest()
    assert summary["signature"] == "— test" and "PD-IL" in summary["release_notice"]
    assert rl.verify(out) == []


def test_dev_is_whole_non_eval_booklets_by_sha256_per_series_and_decade(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _build(tranche, monkeypatch)
    picks = summary["dev_selection"]["picks"]
    # One per stratum that gives lines; 7070 (kovetz 2010s) gives none, so that stratum has no dev booklet.
    assert sorted(picks.values()) == ["kovetz_hatakanot 2000s", "kovetz_hatakanot 2020s", "sefer_hachukim 2010s", "sefer_hachukim 2020s"]
    two = ["reshumot:sefer_hachukim_2663", "reshumot:sefer_hachukim_2745"]
    first = min(two, key=lambda unit: hashlib.sha256(unit.encode()).hexdigest())
    assert first in picks and not set(two) - {first} & set(picks)
    rows = _rows(tranche["out"])
    assert {row["unit_id"] for row in rows if row["split"] == "dev"} <= set(picks)
    assert not {row["unit_id"] for row in rows if row["split"] == "train"} & set(picks)
    tagger = json.loads((tranche["out"] / "tagger_units.json").read_text(encoding="utf-8"))
    assert {unit["unit_id"] for unit in tagger["units"]} == NON_EVAL
    assert all(unit["page_images"] and all(Path(path).is_file() for path in unit["page_images"]) for unit in tagger["units"])
    assert {unit["unit_id"]: unit["split"] for unit in tagger["units"]}["reshumot:kovetz_hatakanot_10333"] in {"train", "dev"}


def test_a_booklet_failing_the_born_digital_check_gives_no_line(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _build(tranche, monkeypatch, producers={"sefer_hachukim_3085": "ABBYY FineReader 14"})
    assert summary["born_digital"]["refused"] == {"reshumot:sefer_hachukim_3085": ["ocr_producer"]}
    assert summary["booklets"]["reshumot:sefer_hachukim_3085"]["split"] == "refused"
    assert summary["dropped"]["booklet_not_born_digital"] == 1
    assert "reshumot:sefer_hachukim_3085" not in {row["unit_id"] for row in _rows(tranche["out"])}
    assert "reshumot:sefer_hachukim_3085" not in summary["dev_selection"]["picks"]


def test_a_pdf_that_is_not_the_pinned_one_refuses_its_booklet(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    (tranche["cache"] / "sefer_hachukim_2663.pdf").write_bytes(b"%PDF another")
    summary = _build(tranche, monkeypatch)
    assert summary["born_digital"]["refused"] == {"reshumot:sefer_hachukim_2663": ["pdf_sha256_mismatch"]}


def test_lines_with_unverified_order_are_dropped_only_when_tier_a_flags_them(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    kept = _rows_after(tranche, monkeypatch)
    monkeypatch.setattr(rl, "line_order_verified", lambda unit, entry: False)
    tranche["out"] = tranche["out"].with_name("set2")
    summary = _build(tranche, monkeypatch)
    rows = _rows(tranche["out"])
    flagged = [row for row in kept if rl.BIDI_FLAGS & set(row["tier_a_flags"])]
    assert flagged and summary["dropped"]["bidi_or_digit_order_unverified"] == len(flagged)
    assert {row["id"] for row in rows} == {row["id"] for row in kept} - {row["id"] for row in flagged}


def _rows_after(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    _build(tranche, monkeypatch)
    return _rows(tranche["out"])


def test_the_guard_refuses_an_eval_unit_that_slips_past_the_selection(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    from hocrgen.config.models import EvalUnitStatus

    monkeypatch.setattr(rl, "unit_status", lambda row, registry, **kwargs: (None, EvalUnitStatus.non_eval))
    with pytest.raises(EvalReservedUnitError, match="reshumot_lines build: refused 4 input row"):
        _build(tranche, monkeypatch)
    assert not tranche["out"].exists()


def test_a_registry_that_reserves_a_booklet_keeps_it_out(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    registry = load_and_validate_bundle().eval_reserved_units
    data = registry.model_dump(mode="json")
    reshumot = next(source for source in data["sources"] if source["source_id"] == rl.RESHUMOT_SOURCE_ID)
    reshumot["non_eval_units"].remove("reshumot:sefer_hachukim_3085")  # now unassigned
    narrowed = type(registry).model_validate(data)
    monkeypatch.setattr(rl, "load_page_layers", _layers_stub(tranche["snapshot"]))
    summary = rl.build(_args(tranche), registry=narrowed, facts_for=_facts_for())
    assert summary["eval_reserved_check"]["input_units"] == {"non_eval": 5, "eval": 3, "unassigned": 1}
    assert "reshumot:sefer_hachukim_3085" not in {row["unit_id"] for row in _rows(tranche["out"])}
    assert rl.verify(tranche["out"], registry=narrowed) == []


def test_verify_finds_tampering(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    _build(tranche, monkeypatch)
    out = tranche["out"]
    row = _rows(out)[0]
    (out / row["image"]).with_suffix(".gt.txt").write_text("אחר\n", encoding="utf-8")
    problems = rl.verify(out)
    assert any("gt.txt" in problem for problem in problems)
    rows = _rows(out)
    rows[0].update(unit_id="reshumot:sefer_hachukim_2574", entry_id="sefer_hachukim_2574__p0003", record_id="sefer_hachukim_2574")  # an eval booklet
    (out / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    problems = rl.verify(out)
    assert any("manifest sha256" in p for p in problems) and any("is eval" in p for p in problems)


def test_cap_keeps_lines_by_sha256_of_the_id() -> None:
    ids = [f"x_l{i:03d}" for i in range(10)]
    kept = rl.cap_lines(ids, 3)
    assert len(kept) == 3 and kept == [i for i in ids if i in set(sorted(ids, key=lambda v: hashlib.sha256(v.encode()).hexdigest())[:3])]
    assert rl.cap_lines(ids, 0) == ids


# --- v2: shuffle, pinned dev, several snapshots, the eval-text 6-gram filter ---------------------------------------

NGRAM_SCRIPT = Path.home() / "agents/environments/opensource/projects/heocr/tasks/eval-domains/scripts/ngram_overlap.py"


@pytest.mark.skipif(not NGRAM_SCRIPT.is_file(), reason="heocr-eval's task scripts are not on this machine")
def test_vendored_6gram_rule_is_heocr_evals() -> None:
    assert hashlib.sha256(NGRAM_SCRIPT.read_bytes()).hexdigest() == rl.NGRAM_ORIGIN["sha256"]
    namespace: dict = {}
    source = NGRAM_SCRIPT.read_text(encoding="utf-8")
    exec(compile(source.split("ORDER = {}")[0], str(NGRAM_SCRIPT), "exec"), namespace)  # N, WORD, grams only; no file reads
    assert namespace["N"] == rl.NGRAM_N and namespace["WORD"].pattern == rl.NGRAM_WORD.pattern
    for line in ["חוק לתיקון פקודת העיריות מס' 3 התשס\"ה-2005 בסעיף 12 לחוק", "א ב ג ד ה ו ז", "קצר"]:
        assert namespace["grams"](line) == rl.word_grams(line)


def test_every_list_output_is_in_the_seeded_order(tranche: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = _build(tranche, monkeypatch, shuffle_seed="s1")
    rows = _rows(tranche["out"])
    assert summary["shuffle_seed"] == "s1" and [r["id"] for r in rows] == sorted((r["id"] for r in rows), key=lambda i: rl.shuffle_key("s1", i))
    assert [r["id"] for r in rows] != sorted(r["id"] for r in rows)  # not the build order
    for split in ("train", "dev"):
        listed = (tranche["out"] / f"{split}.txt").read_text(encoding="utf-8").splitlines()
        assert listed == [r["image"] for r in rows if r["split"] == split] and summary["list_files"][split]["lines"] == len(listed)
    assert rl.verify(tranche["out"]) == []
    other = tranche["out"].with_name("set_s2")
    _build({**tranche, "out": other}, monkeypatch, shuffle_seed="s2")
    rows2 = _rows(other)
    assert sorted(map(json.dumps, rows)) == sorted(map(json.dumps, rows2))  # the same rows, byte for byte
    assert [r["id"] for r in rows2] != [r["id"] for r in rows]
    (tranche["out"] / "train.txt").write_text("", encoding="utf-8")
    assert any("train.txt" in p for p in rl.verify(tranche["out"]))


def test_keep_dev_from_pins_an_earlier_builds_dev_booklets(tranche: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    first = _build(tranche, monkeypatch)
    picks = first["dev_selection"]["picks"]
    # Pin a different booklet of the sefer_hachukim 2010s stratum than the rule would pick.
    other = next(u for u in ("reshumot:sefer_hachukim_2663", "reshumot:sefer_hachukim_2745") if u not in picks)
    pinned = {**{u: s for u, s in picks.items() if s != "sefer_hachukim 2010s"}, other: "sefer_hachukim 2010s"}
    prior = tmp_path / "prior_summary.json"
    prior.write_text(json.dumps({"dev_selection": {"picks": pinned}}), encoding="utf-8")
    summary = _build({**tranche, "out": tmp_path / "pinned"}, monkeypatch, keep_dev_from=str(prior))
    assert summary["dev_selection"]["picks"] == pinned and summary["dev_selection"]["pinned"]["dropped"] == []


def test_several_snapshots_are_read_as_one(tranche: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    whole = _build(tranche, monkeypatch)
    rows = _rows(tranche["out"])
    # Move one booklet's entries and files to a second snapshot and its PDF to a second cache.
    second, cache2 = tmp_path / "snapshot2", tmp_path / "pdf2"
    moved = "reshumot:sefer_hachukim_3085"
    entries = [json.loads(l) for l in (tranche["snapshot"] / "entries.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    stay = [e for e in entries if rl.entry_unit(e) != moved]
    move = [e for e in entries if rl.entry_unit(e) == moved]
    shutil.copytree(tranche["snapshot"], second)
    (tranche["snapshot"] / "entries.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in stay), encoding="utf-8")
    (second / "entries.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in move), encoding="utf-8")
    cache2.mkdir()
    shutil.move(str(tranche["cache"] / "sefer_hachukim_3085.pdf"), cache2 / "sefer_hachukim_3085.pdf")
    monkeypatch.setattr(rl, "load_page_layers", _multi_layers_stub([tranche["snapshot"], second]))
    out = tmp_path / "multi"
    summary = rl.build(_args({**tranche, "out": out}, snapshot=[str(tranche["snapshot"]), str(second)],
                             pdf_cache=[str(tranche["cache"]), str(cache2)]), facts_for=_facts_for())
    assert sorted(map(json.dumps, _rows(out))) == sorted(map(json.dumps, rows))
    assert summary["totals"] == whole["totals"] and summary["snapshots"] == [str(tranche["snapshot"].resolve()), str(second.resolve())]
    with pytest.raises(SystemExit, match="more than one snapshot"):
        rl.build(_args({**tranche, "out": tmp_path / "dup"}, snapshot=[str(second), str(second)]), facts_for=_facts_for())


def _multi_layers_stub(snapshots: list[Path]):
    loaders = [_layers_stub(s) for s in snapshots]

    def load(layer_dir, slug, page_count, pdf):
        merged: dict = {}
        for loader in loaders:
            for n, layer in loader(layer_dir, slug, page_count, pdf).items():
                if layer != _blank_layer() or n not in merged:
                    merged[n] = layer
        return merged

    return load


def test_lines_sharing_a_6gram_with_eval_text_are_dropped(tranche: dict, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _build(tranche, monkeypatch)
    rows = _rows(tranche["out"])
    long = [r for r in rows if rl.word_grams(r["text"])]
    assert len(long) > 2
    target = long[0]
    pool = tmp_path / "pool.json"
    pool.write_text(json.dumps({"schema": rl.GRAM_POOL_SCHEMA, "n": 6, "digest": "sha256", "targets": {"test": 1},
                                "digests": [rl.gram_digest(sorted(rl.word_grams(target["text"]))[0])]}), encoding="utf-8")
    summary = _build({**tranche, "out": tmp_path / "filtered"}, monkeypatch, exclude_6grams=str(pool))
    kept = _rows(tmp_path / "filtered")
    hit = {r["id"] for r in rows if rl.word_grams(r["text"]) & {tuple(sorted(rl.word_grams(target["text"]))[0])}}
    assert target["id"] in hit and {r["id"] for r in kept} == {r["id"] for r in rows} - hit
    assert summary["dropped"]["shares_word_6gram_with_eval_text"] == len(hit)
    assert summary["eval_text_overlap_filter"]["lines_dropped"] == len(hit)
    # The rows that stay are byte-identical to the unfiltered build's.
    same = {r["id"]: json.dumps(r) for r in rows}
    assert all(json.dumps(r) == same[r["id"]] for r in kept)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "x", "n": 5, "digest": "sha256", "digests": []}), encoding="utf-8")
    with pytest.raises(SystemExit):
        _build({**tranche, "out": tmp_path / "bad"}, monkeypatch, exclude_6grams=str(bad))
