"""E2d2: Wikisource real printed evaluation references and the training-text leakage check (network-free)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.wikisource import page_plain_text
from hocrgen.manifests.models import BenchmarkReferenceManifestRecord, BenchmarkTranscriptionReferenceRecord
from hocrgen.reference_runs import load_adjudicated_references, run_reference_evaluation
from hocrgen.tools import eval_text_leakage as leakage
from hocrgen.tools.wikisource_eval_references import main as eval_refs_main
from hocrgen.tools.wikisource_eval_references import write_eval_reference_set

SNAPSHOT = package_root() / "data" / "wikisource" / "snapshot"
SOURCE = "wikisource_he_proofread"
SELIHOT = f"{SOURCE}:selihot_baer_1885__p0034"
BUBER = f"{SOURCE}:buber_tanhuma_1885__p0233"


def _pages() -> dict[str, dict]:
    lines = (SNAPSHOT / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    return {f"{SOURCE}:{page['source_item_id']}": page for page in map(json.loads, lines)}


def test_quality_4_pages_become_adjudicated_printed_references_named_for_two_editors(tmp_path: Path) -> None:
    benchmark = package_root() / "data" / "benchmark" / "benchmark_v1" / "reference_manifest.json"
    before = benchmark.read_bytes()
    summary = write_eval_reference_set(SNAPSHOT, tmp_path / "set", reference_manifest_id="e2d2_test")
    assert benchmark.read_bytes() == before
    assert summary["counts"] == {"adjudicated": 1, "single_reviewer": 3, "held_out": 0,
                                 "skipped": {"text_changed_after_validation": 1}}
    manifest = json.loads((tmp_path / "set" / "reference_manifest.json").read_text(encoding="utf-8"))
    BenchmarkReferenceManifestRecord.model_validate(manifest)
    assert manifest["benchmark_id"] != "benchmark_v1"
    (item,) = manifest["items"]
    assert item["item_id"] == SELIHOT and item["modality"] == "printed"
    assert item["adjudication_status"] == "adjudicated" and item["visibility"] == "hidden_reference"
    assert item["reviewers"] == ["wikisource:Neriah", "wikisource:Nahum"]
    payload = (tmp_path / "set" / item["transcription_reference"]["path"]).read_text(encoding="utf-8")
    assert hashlib.sha256(payload.encode("utf-8")).hexdigest() == item["transcription_reference"]["sha256"]
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(payload)
    assert record.review.status == "adjudicated" and record.review.adjudicator == "wikisource:Nahum"
    assert record.pages[0].text == page_plain_text(_pages()[SELIHOT], SNAPSHOT)
    adjudication = json.loads((tmp_path / "set" / "references/selihot_baer_1885__p0034/adjudication.json").read_text("utf-8"))
    assert [human["role"] for human in adjudication["attesting_humans"]] == ["proofreader", "validator"]
    assert [human["user"] for human in adjudication["attesting_humans"]] == ["Neriah", "Nahum"]
    assert adjudication["agent_attestation"] is None and "decision 2" in adjudication["rule"]
    loaded = load_adjudicated_references(tmp_path / "set" / "reference_manifest.json", modality="printed")
    assert list(loaded["references"]) == [SELIHOT]
    assert str(tmp_path) not in json.dumps(summary)


def test_single_reviewer_texts_asset_index_and_crops(tmp_path: Path) -> None:
    summary = write_eval_reference_set(SNAPSHOT, tmp_path / "set", reference_manifest_id="e2d2_test")
    texts = [json.loads(line) for line in (tmp_path / "set" / "single_reviewer_texts.jsonl").read_text("utf-8").splitlines()]
    assert {text["reference_origin"] for text in texts} == {"wikisource_single_reviewer"}
    assert {text["modality"] for text in texts} == {"printed"}
    index = {entry["item_id"]: entry["page_sha256"] for entry in
             json.loads((tmp_path / "set" / "asset_index.json").read_text("utf-8"))["items"]}
    pages = _pages()
    assert index[BUBER] == [pages[BUBER]["crop"]["asset"]["sha256"]]  # decision 12: the crop is scored
    assert index[SELIHOT] == [pages[SELIHOT]["image"]["sha256"]]
    buber = next(item for item in summary["items"] if item["item_id"] == BUBER)
    assert buber["image"]["kind"] == "crop" and buber["image"]["crop_of_page"] == pages[BUBER]["image"]["sha256"]
    assert buber["stratum"] == "single_reviewer" and "adjudication_record" not in buber


def test_held_out_pages_are_listed_and_never_written(tmp_path: Path) -> None:
    held = {SELIHOT: "training_text_overlap: 3 shared word 8-grams with the training corpora"}
    summary = write_eval_reference_set(SNAPSHOT, tmp_path / "set", reference_manifest_id="e2d2_test", held_out=held)
    assert summary["held_out"] == [{"item_id": SELIHOT, "stratum": "adjudicated", "reason": held[SELIHOT]}]
    assert json.loads((tmp_path / "set" / "reference_manifest.json").read_text("utf-8"))["items"] == []
    assert not (tmp_path / "set" / "references").exists()
    with pytest.raises(StageExecutionError, match="not in the snapshot"):
        write_eval_reference_set(SNAPSHOT, tmp_path / "other", reference_manifest_id="x", held_out={"nope:1": "r"})
    with pytest.raises(StageExecutionError, match="new or empty"):
        write_eval_reference_set(SNAPSHOT, tmp_path / "set", reference_manifest_id="e2d2_test")
    hold = tmp_path / "hold.json"
    hold.write_text(json.dumps(held), encoding="utf-8")
    assert eval_refs_main([str(SNAPSHOT), str(tmp_path / "cli"), "--hold-out", str(hold)]) == 0


def test_printed_track_run_scores_the_real_reference_end_to_end(tmp_path: Path) -> None:
    write_eval_reference_set(SNAPSHOT, tmp_path / "set", reference_manifest_id="e2d2_test")
    pages = _pages()
    sha = pages[SELIHOT]["image"]["sha256"]
    text = page_plain_text(pages[SELIHOT], SNAPSHOT)
    predictions = tmp_path / "pred"
    predictions.mkdir()
    payload = {"schema_version": "heocr_engine_prediction.v1", "page_id": f"sha256:{sha}", "track": "open",
               "input": {"sha256": sha, "width": 1, "height": 1}, "engine": {"name": "e", "version": "1"},
               "pipeline": [], "text": text, "words": []}
    (predictions / "p.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    report = run_reference_evaluation(predictions_dir=predictions, reference_manifest=tmp_path / "set" / "reference_manifest.json",
                                      asset_index_path=tmp_path / "set" / "asset_index.json", modality="printed")
    scored = report["scored"]["adjudicated_reference"]
    assert scored["evaluated_item_count"] == 1 and scored["profiles"]["primary.v1"]["cer"] == 0
    assert scored["modality"] == "printed" and "reference_views" not in report  # Selihot p. 34 has no footnotes


def test_leakage_tokens_fold_points_punctuation_and_footnote_marks() -> None:
    assert leakage.leakage_tokens("שָׁלוֹם, עוֹלָם[1] — טוֹב־מְאֹד.") == ["שלום", "עולם", "טוב", "מאד"]
    assert leakage.leakage_tokens("‏א‎ ב") == ["א", "ב"]


def test_leakage_check_excludes_on_a_shared_8gram_and_flags_a_high_3gram_share(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.txt"
    corpus.write_text("אחת שתיים שלוש ארבע חמש שש שבע שמונה תשע\nאלף בית גימל דלת\n", encoding="utf-8")
    index = leakage.CorpusIndex()
    index.add_file("toy", corpus)
    report = leakage.check_texts({
        "a": "פתיחה אחת שתיים שלוש ארבע חמש שש שבע שמונה סוף",  # an 8-gram from one corpus line
        "b": "אלף בית גימל דלת",                                 # all 3-grams shared, no 8-gram
        "c": "שמונה תשע אלף בית גימל דלת הא וו",                 # crosses a corpus line: no 8-gram
        "d": "טקסט אחר לגמרי בלי חפיפה כלל",
    }, index)
    verdicts = {item["item_id"]: item["verdict"] for item in report["items"]}
    assert verdicts == {"a": "exclude", "b": "flag", "c": "flag", "d": "clear"}
    a = next(item for item in report["items"] if item["item_id"] == "a")
    assert a["shared_word_8grams"] == 1 and a["word_8grams"] == 3
    assert report["counts"] == {"exclude": 1, "flag": 2, "clear": 1}
    assert report["corpora"][0]["sha256"] == hashlib.sha256(corpus.read_bytes()).hexdigest()
    assert "אחת" not in json.dumps(report, ensure_ascii=False)


def test_leakage_cli_writes_counts_and_hold_out_list(tmp_path: Path) -> None:
    write_eval_reference_set(SNAPSHOT, tmp_path / "set", reference_manifest_id="e2d2_test")
    selihot = page_plain_text(_pages()[SELIHOT], SNAPSHOT)
    corpus = tmp_path / "corpus.txt"
    corpus.write_text(" ".join(leakage.leakage_tokens(selihot)[:12]) + "\n", encoding="utf-8")
    out, hold = tmp_path / "leak.json", tmp_path / "hold.json"
    assert leakage.main(["--reference-manifest", str(tmp_path / "set" / "reference_manifest.json"),
                         "--texts", str(tmp_path / "set" / "single_reviewer_texts.jsonl"),
                         "--corpus", f"toy={corpus}", "--output", str(out), "--hold-out-output", str(hold)]) == 0
    held = json.loads(hold.read_text(encoding="utf-8"))
    assert list(held) == [SELIHOT] and held[SELIHOT].startswith("training_text_overlap: 5 shared word 8-grams")
    assert json.loads(out.read_text(encoding="utf-8"))["counts"]["exclude"] == 1
    with pytest.raises(StageExecutionError, match="NAME=PATH"):
        leakage.main(["--texts", str(tmp_path / "set" / "single_reviewer_texts.jsonl"), "--corpus", "bad",
                      "--output", str(out)])
