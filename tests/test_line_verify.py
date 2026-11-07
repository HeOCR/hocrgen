"""Network-free tests for the E2d6 line verification tool (bundle export, selection, decisions and ingest)."""

from __future__ import annotations

import json
import shutil
import unicodedata
from collections import Counter
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.core.errors import StageExecutionError
from hocrgen.tools import benyehuda_nli_alignment as aligner
from hocrgen.tools import line_verify as lv

ROOT = Path(__file__).resolve().parents[1]
NLI_FIXTURE = ROOT / "tests" / "fixtures" / "benyehuda_nli"
WS_SNAPSHOT = ROOT / "src" / "hocrgen" / "data" / "wikisource" / "snapshot"
WORDS = ("שלום עולם ספר מלך ארץ שמים דבר איש בית עיר נהר הר שדה לחם מים אור חושך יום לילה שנה זמן עת אהבה "
         "שלוה רוח נפש לב יד רגל עין אוזן פה קול שיר מזמור תפלה ברכה נחמה גאולה ישועה צדקה משפט אמת חסד").split()


def _lines(count: int, per: int = 7) -> list[str]:
    out, cursor = [], 0
    for index in range(count):
        words = [WORDS[(cursor + slot * 3 + index) % len(WORDS)] + ("ים" if (index + slot) % 4 == 0 else "") for slot in range(per)]
        cursor += per
        out.append(" ".join(words))
    return out


LINES = _lines(8)


def _ocr(lines: list[str], *, tall: int | None = None) -> list[aligner.OcrLine]:
    return [aligner.OcrLine(index=i, bbox=(50, 40 + i * 30, 500, 60 if i == tall else 22), text=text, confidence=90.0)
            for i, text in enumerate(lines)]


def _page(lines: list[aligner.OcrLine], **extra: object) -> lv.PageInput:
    return lv.PageInput(page_id="wikisource_he_proofread:t__p0001", source=lv.WIKISOURCE, book_id="t", book_title="T",
                        page_label="1", image_path=Path("unused.jpg"), attribution="a", release_split="train",
                        size=(600, 400), ocr_lines=lines, **extra)  # type: ignore[arg-type]


def _candidates(text: str, lines: list[aligner.OcrLine], **extra: object) -> tuple[list[lv.LineCandidate], Counter[str]]:
    rejected: Counter[str] = Counter()
    page = _page(lines, **extra)
    return lv.aligned_candidates(text, [page], rejected, text_bounded=True)[page.page_id], rejected


# --- candidate text, disagreement, difficulty -------------------------------------------------------------------


def test_candidate_text_is_nfc_single_spaced_and_has_no_space_before_punctuation() -> None:
    raw = unicodedata.normalize("NFD", "  שָׁלוֹם ,  עוֹלָם .\n")
    text = lv.candidate_text(raw)
    assert text == unicodedata.normalize("NFC", "שָׁלוֹם, עוֹלָם.")
    assert lv.fix_space_before_punctuation("אב ,גד :")[1] == 2


def test_disagreement_ignores_niqqud_and_spacing_and_marks_whole_words() -> None:
    assert lv.disagreement("שָׁלוֹם עוֹלָם", "שלום  עולם") == (0.0, [])
    score, spans = lv.disagreement("שלום עולם גדול", "שלום עולט גדול")
    assert spans == [[5, 9]] and 0 < score < 0.2
    score, spans = lv.disagreement("אבג דהו זחט", "אבג זחט")
    assert spans == [[4, 7]]
    score, spans = lv.disagreement("אבג", "אבגד")  # an extra OCR letter at the end
    assert spans == [[0, 3]]
    assert lv.disagreement("", "x") == (0.0, [])
    assert lv.disagreement("אב", "תתתתתתתתתת")[0] == 1.0


def test_difficulty_formula_and_page_centred_secondary_engines() -> None:
    score, parts = lv.difficulty(0.5, confidence=60.0, niqqud=0.5, small_type=True)
    assert parts == {"ocr_disagreement": 0.5, "ocr_low_confidence": 0.4, "niqqud": 0.5, "small_type": 1.0}
    assert score == round(0.6 * 0.5 + 0.2 * 0.4 + 0.1 * 0.5 + 0.1, 4)
    lifted, _ = lv.difficulty(0.5, secondary={"r3h_r4d_a1": 0.25}, confidence=None, niqqud=0, small_type=False)
    assert lifted == round(0.6 * (0.5 + lv.SECONDARY_ENGINE_WEIGHT * 0.25), 4)
    assert lv.difficulty(0.0, secondary={"r3h_r4d_a1": -1.0}, confidence=100, niqqud=0, small_type=False)[0] == 0.0
    assert lv.niqqud_share("שָׁלוֹם") == 0.5 and lv.niqqud_share("...") == 0.0


# --- localization and eligibility -------------------------------------------------------------------------------


def test_aligned_lines_carry_the_human_text_of_their_line() -> None:
    candidates, rejected = _candidates("\n".join(LINES), _ocr(LINES))
    assert [c.line_index for c in candidates] == list(range(8)) and not rejected
    for candidate in candidates:
        assert candidate.candidate_text == LINES[candidate.line_index]
        assert candidate.item_id == f"wikisource_he_proofread:t__p0001#L{candidate.line_index:03d}"
        assert candidate.alignment_score == 1.0 and candidate.engines == {"tesseract": 0.0}
        assert candidate.box[0] < 50 and candidate.context_box[1] < candidate.box[1]


def test_lines_that_do_not_tile_with_their_neighbours_are_dropped() -> None:
    text = " ".join(LINES[:3]) + " ובתוך הדברים האלה נכתבה הערה ארוכה של העורכים " + " ".join(LINES[3:])
    candidates, rejected = _candidates(text, _ocr(LINES))
    assert [c.line_index for c in candidates] == [0, 1, 4, 5, 6, 7]
    assert rejected == {"span_does_not_tile_with_neighbours": 2}


def test_geometry_and_text_rules_reject_risky_lines() -> None:
    candidates, rejected = _candidates(" ".join(LINES), _ocr(LINES, tall=5))
    assert 5 not in {c.line_index for c in candidates}
    assert rejected == {"box_taller_than_a_line": 1, "box_overlaps_another_line": 1}
    marked = LINES[:2] + [LINES[2] + "[1]"] + LINES[3:]
    _, rejected = _candidates(" ".join(marked), _ocr(LINES))
    assert rejected["footnote_mark"] == 1
    short = LINES[:7] + ["שלום עולם"]
    _, rejected = _candidates(" ".join(short), _ocr(short))
    assert rejected["short_line"] == 1
    start = len(" ".join(LINES[:4])) + 2
    _, rejected = _candidates(" ".join(LINES), _ocr(LINES), excluded_ranges=[(start, start + 3)])
    assert rejected["excluded_span_on_scan"] == 1
    weak = [aligner.OcrLine(index=i, bbox=(50, 40 + i * 30, 500, 22), text=" ".join(word[::-1] for word in LINES[i].split()[:4])
                            + " " + " ".join(LINES[i].split()[4:])) for i in range(8)]
    candidates, rejected = _candidates(" ".join(LINES), weak)
    assert not candidates and rejected and set(rejected) <= {"page_alignment_weak", "line_alignment_weak",
                                                            "span_does_not_tile_with_neighbours"}


def test_secondary_engine_reading_is_centred_on_the_page() -> None:
    readings = [((50.0, 40.0 + i * 30, 550.0, 62.0 + i * 30), LINES[i] if i != 3 else "תתתת תתתת") for i in range(8)]
    candidates, _ = _candidates(" ".join(LINES), _ocr(LINES), engine_lines={"r3h_r4d_a1": readings})
    by_line = {c.line_index: c for c in candidates}
    assert by_line[3].engines["r3h_r4d_a1"] > 0.5 and by_line[0].engines["r3h_r4d_a1"] == 0.0
    assert by_line[3].difficulty > by_line[0].difficulty  # the other lines share the page's median: no shift
    assert by_line[0].components["ocr_disagreement"] == 0.0
    assert lv._engine_reading((0, 0, 10, 10), []) is None


# --- selection --------------------------------------------------------------------------------------------------


def _synthetic(count: int, books: int, pages_per_book: int = 30) -> list[lv.LineCandidate]:
    out = []
    for index in range(count):
        book = f"b{index % books}"
        page = f"wikisource_he_proofread:{book}__p{(index // books) % pages_per_book:04d}"
        out.append(lv.LineCandidate(page, lv.WIKISOURCE, book, index, [0, 0, 10, 10], [0, 0, 10, 10], "אבג", 0.9, [],
                                    round((index * 37 % 101) / 100, 4), {}, {"tesseract": 0.0}, 20))
    return out


def test_selection_strata_caps_ranks_and_determinism() -> None:
    pool = _synthetic(3000, books=12)
    ranked = lv.select_items(pool, seed="s", size=200)
    assert len(ranked) == 200
    strata = Counter(stratum for _, stratum in ranked)
    assert strata == {"hard": 160, "random": 40}
    books = Counter(item.book_id for item, _ in ranked)
    assert max(books.values()) <= 20
    random_books = Counter(item.book_id for item, stratum in ranked if stratum == "random")
    assert max(random_books.values()) <= 4
    hard_pages = Counter(item.page_id for item, stratum in ranked if stratum == "hard")
    assert max(hard_pages.values()) <= lv.SELECTION["hard_page_cap"]
    assert [stratum for _, stratum in ranked[:10]] == ["hard"] * 4 + ["random"] + ["hard"] * 4 + ["random"]
    hard = [item.difficulty for item, stratum in ranked if stratum == "hard"]
    assert hard == sorted(hard, reverse=True)
    assert [item.item_id for item, _ in ranked] == [item.item_id for item, _ in lv.select_items(list(reversed(pool)), seed="s", size=200)]
    assert [item.item_id for item, _ in ranked] != [item.item_id for item, _ in lv.select_items(pool, seed="t", size=200)]
    # a small pool: everything is taken and the leftovers of a stratum fill the queue
    small = lv.select_items(_synthetic(7, books=7), seed="s", size=200)
    assert len(small) == 7 and sorted(item.item_id for item, _ in small) == sorted(c.item_id for c in _synthetic(7, books=7))


# --- bundle -----------------------------------------------------------------------------------------------------


def _bundle(tmp_path: Path, count: int = 6) -> tuple[Path, dict]:
    image = tmp_path / "src" / "page.jpg"
    image.parent.mkdir(parents=True)
    Image.new("RGB", (600, 400), "white").save(image)
    candidates, _ = _candidates(" ".join(LINES), _ocr(LINES))
    page = _page([])
    page.image_path = image
    ranked = lv.select_items(candidates, seed="b", size=count, book_cap_share=1.0)
    bundle, copies = lv.build_bundle({page.page_id: page}, ranked, batch_id="line_verify_test", created_at="2026-11-07",
                                     generator_ref="abc", description="test batch")
    out = tmp_path / "bundle"
    lv.write_bundle(out, bundle, copies)
    return out, bundle


def test_bundle_matches_the_contract_and_validates(tmp_path: Path) -> None:
    out, bundle = _bundle(tmp_path)
    assert bundle["schema_version"] == "line_verify_items.v1"
    page = bundle["pages"][0]
    assert page["image"] == f"pages/{page['sha256']}.jpg" and (out / page["image"]).is_file()
    assert page["text_license"] == "CC BY-SA 4.0" and page["release_split"] == "train"
    item = bundle["items"][0]
    assert set(item) == {"item_id", "page_id", "line_index", "box", "context_box", "candidate_text", "candidate_provenance",
                         "alignment_score", "attention_spans", "difficulty", "stratum", "rank"}
    assert item["candidate_provenance"] == "wikisource_quality3_single_proofreader" and item["rank"] == 1
    assert lv.bundle_problems(bundle, out) == []
    loaded = lv.load_bundle(out)
    assert loaded == bundle
    stats = lv.bundle_stats(bundle)
    assert stats["items"] == 6 and stats["by_stratum"] == {"hard": 5, "random": 1} and stats["books"] == 1
    # a re-export with the same batch id replaces it; another batch id is refused
    lv.write_bundle(out, bundle, {page["image"]: tmp_path / "src" / "page.jpg"})
    with pytest.raises(StageExecutionError, match="another batch"):
        lv.write_bundle(out, {**bundle, "batch_id": "other"}, {})


def test_bundle_validation_catches_tampering(tmp_path: Path) -> None:
    out, bundle = _bundle(tmp_path)
    image = out / bundle["pages"][0]["image"]
    image.write_bytes(image.read_bytes() + b"x")
    assert any("does not match its sha256" in p for p in lv.bundle_problems(bundle, out))
    with pytest.raises(StageExecutionError):
        lv.load_bundle(out)
    item = bundle["items"][0]
    cases = [
        {**item, "ocr_text": "x"},
        {**item, "rank": 99},
        {**item, "attention_spans": [[3, 1]]},
        {**item, "candidate_text": "אב ,גד"},
        {**item, "stratum": "easy"},
        {**item, "box": [5, 5, 1, 1]},
        {**item, "candidate_provenance": "pby_human_typed_aligned"},
        {**item, "difficulty": 2},
        {**item, "item_id": item["item_id"] + "x"},
    ]
    for case in cases:
        assert lv.bundle_problems({**bundle, "items": [case, *bundle["items"][1:]]}), case
    bad_page = {**bundle["pages"][0], "source": "heocr_restricted_eval"}
    assert any("source must be one of" in p for p in lv.bundle_problems({**bundle, "pages": [bad_page]}))
    assert lv.bundle_problems({"schema_version": "x"}) == ["schema_version must be line_verify_items.v1"]
    empty = lv.bundle_problems({"schema_version": lv.ITEMS_SCHEMA, "pages": [], "items": []})
    assert "pages must not be empty" in empty and "items must not be empty" in empty


# --- decisions and ingest -----------------------------------------------------------------------------------------


def _decision(item_id: str, reviewer: str, decision: str, text: str | None = None) -> dict:
    record = {"decision_id": f"decision:{item_id}:{reviewer}", "item_id": item_id, "reviewer": reviewer, "decision": decision,
              "decided_at": "2026-11-08", "checked_by": "human"}
    if text is not None:
        record["text"] = text
    return record


def _decisions(bundle: dict) -> dict:
    ids = [item["item_id"] for item in bundle["items"]]
    return {"schema_version": lv.DECISIONS_SCHEMA, "batch_id": bundle["batch_id"], "decisions": [
        _decision(ids[0], "rv_aaaaaaa1", "exact"),
        _decision(ids[1], "rv_aaaaaaa1", "edited", "תיקון של השורה"),
        _decision(ids[2], "rv_aaaaaaa1", "unreadable"),
        _decision(ids[3], "rv_aaaaaaa1", "misaligned"),
        _decision(ids[4], "rv_aaaaaaa1", "exact"),
        _decision(ids[4], "rv_bbbbbbb2", "misaligned"),
    ]}


def test_decision_validation(tmp_path: Path) -> None:
    _, bundle = _bundle(tmp_path)
    good = _decisions(bundle)
    assert lv.decisions_problems(good, bundle) == []
    first = good["decisions"][0]
    candidate = bundle["items"][0]["candidate_text"]
    bad = [
        {**first, "reviewer": "Shay"},
        {**first, "decision_id": "decision:x"},
        {**first, "decision": "accepted"},
        {**first, "decision": "edited"},
        {**first, "decision": "edited", "text": candidate},
        {**first, "decision": "edited", "text": "\u05e9\u05c1\u05b8\u05dc\u05d5\u05b9\u05dd"},  # marks not in canonical order
        {**first, "text": "x"},
        {**first, "decided_at": "2026-13-40"},
        {**first, "checked_by": "agent"},
        {**first, "note": "x"},
        _decision("wikisource_he_proofread:t__p0001#L999", "rv_aaaaaaa1", "exact"),
    ]
    for record in bad:
        assert lv.decisions_problems({**good, "decisions": [record]}, bundle), record
    assert lv.decisions_problems({**good, "decisions": [{**first, "candidate_sha256": "abc"}]}, bundle)
    assert lv.decisions_problems({**good, "decisions": [first, first]}, bundle)
    assert lv.decisions_problems({**good, "batch_id": "other"}, bundle)
    assert lv.decisions_problems({"schema_version": "x"}) == ["schema_version must be line_verify_decisions.v1"]
    assert lv.decisions_problems({**good, "decisions": None}) == ["decisions must be a list"]


def test_resolution_policy_and_provenance(tmp_path: Path) -> None:
    _, bundle = _bundle(tmp_path)
    resolved = lv.resolve_decisions(bundle, _decisions(bundle))
    counts = resolved["counts"]
    assert counts["line_references"] == 2 and counts["reference_eligible"] == 2
    assert counts["by_decision"] == {"edited": 1, "exact": 1, "misaligned": 1, "unreadable": 1}
    assert counts["conflicts"] == 1 and counts["undecided_items"] == 1
    exact, edited = resolved["lines"]
    assert exact["text"] == exact["candidate_text"] and not exact["corrected"]
    assert edited["text"] == "תיקון של השורה" and edited["corrected"] and edited["candidate_text"] == bundle["items"][1]["candidate_text"]
    for line in (exact, edited):
        assert line["attestation_policy"] == "adjudicated" == lv.ATTESTATION_POLICY
        assert line["attestation_status"] == "typist_and_verifier_adjudicated" and line["adjudication_status"] == "adjudicated"
        assert line["reviewers"] == ["rv_aaaaaaa1"] and line["release_split"] == "train"
    assert {entry["reason"] for entry in resolved["excluded"]} == {"unreadable_on_scan", "box_and_text_misaligned"}
    conservative = lv.resolve_decisions(bundle, _decisions(bundle), policy="single_human_verified")
    assert conservative["counts"]["reference_eligible"] == 0
    assert {line["attestation_status"] for line in conservative["lines"]} == {"single_human_verified"}
    two = lv.resolve_decisions(bundle, _decisions(bundle), min_reviewers=2)
    assert two["counts"]["line_references"] == 0 and two["counts"]["pending_min_reviewers"] == 4
    with pytest.raises(StageExecutionError):
        lv.resolve_decisions(bundle, _decisions(bundle), policy="whatever")


def test_stale_decisions_are_counted_and_never_applied(tmp_path: Path) -> None:
    _, bundle = _bundle(tmp_path)
    decisions = _decisions(bundle)
    current = lv.sha256_text(bundle["items"][0]["candidate_text"])
    decisions["decisions"][0]["candidate_sha256"] = current
    decisions["decisions"][1]["candidate_sha256"] = "0" * 64  # judged on another candidate text
    stale_equal = _decision(bundle["items"][5]["item_id"], "rv_aaaaaaa1", "edited", bundle["items"][5]["candidate_text"])
    stale_equal["candidate_sha256"] = "1" * 64  # equal to today's candidate, but judged on another one: not an error
    decisions["decisions"].append(stale_equal)
    assert lv.decisions_problems(decisions, bundle) == []
    resolved = lv.resolve_decisions(bundle, decisions)
    assert resolved["counts"]["stale_decisions"] == 2 and resolved["counts"]["line_references"] == 1
    assert [entry["item_id"] for entry in resolved["stale"]] == sorted([bundle["items"][1]["item_id"], bundle["items"][5]["item_id"]])
    assert {entry["reason"] for entry in resolved["stale"]} == {"candidate_changed_since_decision"}
    assert resolved["lines"][0]["item_id"] == bundle["items"][0]["item_id"]
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps(decisions, ensure_ascii=False), encoding="utf-8")
    out = tmp_path / "refs.json"
    lv.ingest(tmp_path / "bundle", path, out)
    document = json.loads(out.read_text(encoding="utf-8"))
    assert len(document["stale"]) == 2 and lv.references_problems(document, bundle) == []


def test_empty_attention_spans_mark_insertion_points(tmp_path: Path) -> None:
    _, bundle = _bundle(tmp_path)
    item = bundle["items"][0]
    end = len(item["candidate_text"])
    ok = {**item, "attention_spans": [[0, 0], [0, 3], [end, end]]}
    assert lv.bundle_problems({**bundle, "items": [ok, *bundle["items"][1:]]}) == []
    overlapping = {**item, "attention_spans": [[0, 3], [2, 4]]}
    assert lv.bundle_problems({**bundle, "items": [overlapping, *bundle["items"][1:]]})


def test_ingest_writes_references_and_line_set_and_they_rederive(tmp_path: Path) -> None:
    out, bundle = _bundle(tmp_path)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(_decisions(bundle), ensure_ascii=False), encoding="utf-8")
    refs, line_set = tmp_path / "docs" / "refs.json", tmp_path / "op" / "line_refs.json"
    counts = lv.ingest(out, decisions_path, refs, line_set_out=line_set)
    assert counts["line_references"] == 2
    document = json.loads(refs.read_text(encoding="utf-8"))
    assert document["schema_version"] == "line_verify_references.v1"
    assert document["attestation_policy"]["name"] == "adjudicated" and document["attestation_policy"]["verifier_differs_from_typist"]
    assert lv.references_problems(document, bundle) == []
    assert lv.references_problems(document) == []
    tampered = {**document, "lines": [{**document["lines"][0], "text": "אחר"}, *document["lines"][1:]]}
    assert lv.references_problems(tampered, bundle) == ["lines do not re-derive from the decisions and the bundle"]
    assert lv.references_problems({"schema_version": "x"})
    assert lv.references_problems({"schema_version": lv.REFERENCES_SCHEMA, "attestation_policy": {"name": "x"}})
    payload = json.loads(line_set.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "line_verify_line_references.v1" and len(payload["lines"]) == 2
    assert payload["pages"][0]["image"].startswith("pages/") and "context_box" in payload["lines"][0]
    assert str(tmp_path) not in refs.read_text(encoding="utf-8")


def test_cli_validate_stats_and_ingest(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out, bundle = _bundle(tmp_path)
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(json.dumps(_decisions(bundle), ensure_ascii=False), encoding="utf-8")
    refs = tmp_path / "refs.json"
    assert lv.main(["ingest", "--bundle", str(out), "--decisions", str(decisions_path), "--out", str(refs)]) == 0
    assert lv.main(["validate", "--bundle", str(out), "--decisions", str(decisions_path), "--references", str(refs)]) == 0
    assert lv.main(["stats", "--bundle", str(out), "--decisions", str(decisions_path)]) == 0
    printed = capsys.readouterr().out
    assert '"line_references": 2' in printed and '"by_stratum"' in printed
    with pytest.raises(StageExecutionError):
        lv.main(["validate"])
    refs.write_text(json.dumps({**json.loads(refs.read_text(encoding="utf-8")), "counts": {}}), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="re-derive"):
        lv.main(["validate", "--bundle", str(out), "--references", str(refs)])
    decisions_path.write_text(json.dumps({**_decisions(bundle), "batch_id": "x"}), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="batch_id"):
        lv.main(["validate", "--bundle", str(out), "--no-images", "--decisions", str(decisions_path)])


def test_committed_references_file_is_valid_and_uses_the_decided_policy() -> None:
    document = json.loads((ROOT / "docs" / "line_verify_references.json").read_text(encoding="utf-8"))
    assert lv.references_problems(document) == []
    assert document["attestation_policy"]["name"] == lv.ATTESTATION_POLICY == "adjudicated"
    assert document["attestation_policy"]["reference_eligible"] is True
    assert document["batch_id"] == "line_verify_v1"
    decision = (ROOT / "planning" / "decisions" / "2026-11-07-line-verification-attestation.md").read_text(encoding="utf-8")
    assert '"Yes, like quality 4"' in decision


# --- the two sources on fixtures ------------------------------------------------------------------------------------


def _nli_config(tmp_path: Path, *, license_url: str | None = None) -> Path:
    fixture = json.loads((NLI_FIXTURE / "fixture.json").read_text(encoding="utf-8"))
    work = tmp_path / "work"
    (work / "img").mkdir(parents=True)
    (work / "ocr").mkdir()
    for index, page in enumerate(fixture["pages"]):
        shutil.copyfile(NLI_FIXTURE / page["image"], work / "img" / f"c{index:04d}.jpg")
        shutil.copyfile(NLI_FIXTURE / page["localization_ocr"], work / "ocr" / f"c{index:04d}.tsv")
    capture = json.loads((NLI_FIXTURE / "manifest_capture.json").read_text(encoding="utf-8"))
    if license_url:
        capture["manifest"]["license"] = [license_url]
    (tmp_path / "manifest.json").write_text(json.dumps(capture, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "pseudocatalogue.csv").write_text(
        "ID,path,title,authors,translators,original_language,source_edition\n"
        "3149,/p12/m3149,אברהם מאפו: חייו וספריו,ראובן בריינין,,,וילנא: תושיה 1928\n", encoding="utf-8")
    shutil.copyfile(NLI_FIXTURE / "pby_excerpt.txt", tmp_path / "m3149.txt")
    config = {"schema_version": "line_verify_nli_works.v1", "scans": [{
        "record_id": "990018546440205171", "manifest": "manifest.json", "ocr_image_width": 1600,
        "manifest_url": "https://iiif.nli.org.il/IIIFv21/990018546440205171/manifest", "work_dir": "work",
        "catalogue": "pseudocatalogue.csv", "works": [{"pby_id": "3149", "text": "m3149.txt"}]}]}
    path = tmp_path / "nli_works.json"
    path.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return path


def test_nli_fixture_pages_give_pby_lines_and_no_ocr_text(tmp_path: Path) -> None:
    rejected: Counter[str] = Counter()
    nli = lv.load_nli_works(_nli_config(tmp_path), rejected)
    assert len(nli) == 1 and len(nli[0][0]) == 2
    pages, candidates = lv.collect_candidates([], nli, rejected)
    assert len(candidates) >= 10
    pby = " ".join(unicodedata.normalize("NFC", (NLI_FIXTURE / "pby_excerpt.txt").read_text(encoding="utf-8")).split())
    ocr_texts = {line.text for page in pages.values() for line in page.ocr_lines}
    for candidate in candidates:
        assert candidate.source == lv.NLI_ALIGNED and candidate.page_id.startswith("benyehuda_nli_aligned:nli_990018546440205171__c")
        assert lv.fix_space_before_punctuation(candidate.candidate_text)[1] == 0
        assert candidate.candidate_text.replace(" ", "") in lv.fix_space_before_punctuation(pby)[0].replace(" ", "")
        assert candidate.candidate_text not in ocr_texts or candidate.engines["tesseract"] == 0.0
    used = {candidate.page_id for candidate in candidates}
    for page_id in used:
        assert pages[page_id].attribution.startswith("Text: אברהם מאפו") and "public-domain-free-use" in pages[page_id].attribution
        assert pages[page_id].release_split is None
    ranked = lv.select_items(candidates, seed="nli", size=8)
    bundle, _ = lv.build_bundle(pages, ranked, batch_id="b", created_at="2026-11-07", generator_ref="r", description="d")
    assert lv.bundle_problems(bundle) == []
    assert {item["candidate_provenance"] for item in bundle["items"]} == {"pby_human_typed_aligned"}
    assert {page["text_license"] for page in bundle["pages"]} == {"public domain"}


def test_nli_scans_that_are_not_free_use_are_refused(tmp_path: Path) -> None:
    rejected: Counter[str] = Counter()
    google = "https://www.nli.org.il/contenteditors/pages-for-terms-of-use/public-domain-non-commercial-use"
    assert lv.load_nli_works(_nli_config(tmp_path, license_url=google), rejected) == []
    assert rejected["nli_scan_rights_not_free_use"] == 2
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "x"}), encoding="utf-8")
    with pytest.raises(StageExecutionError):
        lv.load_nli_works(bad, rejected)


def _ws_cache(tmp_path: Path) -> Path:
    """A localization cache for the packaged snapshot's pages: TSV word rows at 2x, one line per 7 words."""

    cache = tmp_path / "ocr_cache"
    cache.mkdir()
    for raw in (WS_SNAPSHOT / "pages.jsonl").read_text(encoding="utf-8").splitlines():
        page = json.loads(raw)
        text = (WS_SNAPSHOT / page["text_path"]).read_text(encoding="utf-8")
        words = text.split()
        rows = ["level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"]
        for index, word in enumerate(words):
            line, slot = divmod(index, 7)
            rows.append(f"5\t1\t1\t1\t{line + 1}\t{slot + 1}\t{1100 - slot * 140}\t{80 + line * 60}\t120\t40\t91\t{word}")
        (cache / f"{page['image']['sha256']}.heb.psm3.x2.tsv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return cache


def test_wikisource_loader_gates_pages_and_records_split_and_attribution(tmp_path: Path) -> None:
    cache = _ws_cache(tmp_path)
    splits = tmp_path / "splits.json"
    splits.write_text(json.dumps({"items": [{"item_id": "wikisource_he_proofread:hyman_toldoth_1910_vol1__p0041", "split": "test"}]}),
                      encoding="utf-8")
    excluded = tmp_path / "refs.json"
    excluded.write_text(json.dumps({"items": [{"item_id": "wikisource_he_proofread:sippurei_maasiyot_1902__p0011"}]}), encoding="utf-8")
    rejected: Counter[str] = Counter()
    loaded = lv.load_wikisource_pages(WS_SNAPSHOT, cache, split_manifest=splits, exclude_manifests=[excluded], engine_dirs={},
                                      rejected=rejected)
    ids = {page.page_id for page, _ in loaded}
    assert ids == {"wikisource_he_proofread:hyman_toldoth_1910_vol1__p0041", "wikisource_he_proofread:buber_tanhuma_1885__p0233"}
    assert rejected == {"page_not_quality_3": 2, "page_scored_reference": 1}
    hyman = next(page for page, _ in loaded if "hyman" in page.page_id)
    assert hyman.release_split == "test" and hyman.size == (600, hyman.size[1])
    assert hyman.attribution.startswith("Text: Hebrew Wikisource contributors, CC BY-SA 4.0, https://he.wikisource.org/w/index.php?oldid=")
    assert hyman.ocr_lines and hyman.ocr_lines[0].bbox[:2] == (130, 40)  # boxes mapped back from the 2x OCR
    pages, candidates = lv.collect_candidates(loaded, [], rejected)
    assert candidates and all(c.source == lv.WIKISOURCE for c in candidates)
    # a page whose image drifted from its pin fails closed
    snapshot = tmp_path / "snapshot"
    shutil.copytree(WS_SNAPSHOT, snapshot)
    asset = snapshot / "assets" / "hyman_toldoth_1910_vol1__p0041.jpg"
    asset.write_bytes(asset.read_bytes() + b"x")
    with pytest.raises(StageExecutionError, match="pinned sha256"):
        lv.load_wikisource_pages(snapshot, cache, split_manifest=None, exclude_manifests=[], engine_dirs={}, rejected=Counter())


def test_wikisource_loader_reads_cached_engine_geometry(tmp_path: Path) -> None:
    cache = _ws_cache(tmp_path)
    pages = {json.loads(raw)["source_item_id"]: json.loads(raw) for raw in (WS_SNAPSHOT / "pages.jsonl").read_text(encoding="utf-8").splitlines()}
    hyman = pages["hyman_toldoth_1910_vol1__p0041"]
    engine = tmp_path / "r3h"
    engine.mkdir()
    geometry = {"schema_version": "heocr_engine_kraken_geometry.v1", "input_sha256": hyman["image"]["sha256"],
                "lines": [{"bbox": [10, 40, 500, 20], "text": "אבג"}, {"bbox": [10, 70, 500, 20], "text": ""}]}
    (engine / "hyman_toldoth_1910_vol1__p0041.json").write_text(json.dumps(geometry, ensure_ascii=False), encoding="utf-8")
    other = {**geometry, "input_sha256": "0" * 64}
    (engine / "buber_tanhuma_1885__p0233.json").write_text(json.dumps(other), encoding="utf-8")
    loaded = dict((page.page_id, page) for page, _ in lv.load_wikisource_pages(
        WS_SNAPSHOT, cache, split_manifest=None, exclude_manifests=[], engine_dirs={"r3h_r4d_a1": engine}, rejected=Counter()))
    assert loaded["wikisource_he_proofread:hyman_toldoth_1910_vol1__p0041"].engine_lines == {"r3h_r4d_a1": [((10, 40, 510, 60), "אבג")]}
    assert loaded["wikisource_he_proofread:buber_tanhuma_1885__p0233"].engine_lines == {}
