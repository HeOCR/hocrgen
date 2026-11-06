"""E2d1/E2d2: modality tracks, the footnote-masked reference view (issue #124) and paired bootstrap intervals."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hocrgen.cli import main
from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import BenchmarkReferenceManifestItemRecord, BenchmarkReferenceManifestRecord
from hocrgen.reference_evaluation import FOOTNOTE_MASKED_VIEW_ID, footnote_masked_pair
from hocrgen.reference_runs import (
    load_adjudicated_references,
    load_synthetic_gold,
    paired_bootstrap_interval,
    run_reference_evaluation,
)
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord

BATCH = package_root() / "data" / "hocrsyngen" / "contracts" / "generation_manifest_v1" / "fixture-batch"
BENCHMARK_V1_MANIFEST = package_root() / "data" / "benchmark" / "benchmark_v1" / "reference_manifest.json"

PRINTED_TEXT = "שלום עולם[1] וכל אשר בו\n[1] הערה קצרה"
PRINTED_PRINT = "שלום עולם*) וכל אשר בו\n*) הערה קצרה"


def _reference(item_id: str, text: str) -> dict:
    lines = [line for line in text.split("\n") if line.strip()]
    return {
        "schema_version": "benchmark_transcription_reference.v1", "item_id": item_id, "source_id": item_id.split(":")[0],
        "source_item_id": item_id.split(":")[1], "normalization": {"unicode": "NFC", "text_order": "logical"},
        "language_scripts": [{"language": "he", "script": "Hebr", "direction": "rtl"}],
        "scoring_policy": {"uncertain": "include_primary_and_report", "illegible": "exclude_primary",
                           "damaged": "include_readable_and_report", "deleted": "exclude_primary",
                           "marginal": "include_when_ordered_else_separate"},
        "pages": [{"page_id": "page-1", "reading_order": 1, "text": text}],
        "lines": [{"line_id": f"line-{n}", "page_id": "page-1", "reading_order": n, "text": line, "layout_line_id": None}
                  for n, line in enumerate(lines, start=1)],
        "spans": [],
        "review": {"status": "adjudicated", "reviewers": ["wikisource:A", "wikisource:B"], "adjudicator": "wikisource:B",
                   "adjudicated_at": "2026-01-01T00:00:00Z"},
    }


def _manifest(tmp_path: Path, entries: list[dict]) -> Path:
    """entries: {item_id, text, sha, modality?, footnotes?}; writes children and the manifest."""
    items = []
    for entry in entries:
        source_item_id = entry["item_id"].split(":")[1]
        path = f"references/{source_item_id}/transcription.json"
        (tmp_path / path).parent.mkdir(parents=True)
        (tmp_path / path).write_text(json.dumps(_reference(entry["item_id"], entry["text"]), ensure_ascii=False),
                                     encoding="utf-8")
        item = {"reference_id": f"m:{source_item_id}", "item_id": entry["item_id"],
                "source_id": entry["item_id"].split(":")[0], "source_item_id": source_item_id,
                "visibility": "hidden_reference", "public_reference_status": "adjudicated",
                "transcription_reference": {"path": path, "schema_version": "benchmark_transcription_reference.v1"},
                "adjudication_status": "adjudicated"}
        if entry.get("modality"):
            item["modality"] = entry["modality"]
        if entry.get("footnotes"):
            item["reference_normalization"] = {"footnote_marker_style": "bracketed_index", "footnote_count": entry["footnotes"]}
        items.append(item)
    manifest = {"schema_version": "benchmark_reference_manifest.v1", "benchmark_id": "e2d_real_printed",
                "reference_manifest_id": "m", "reference_contracts": {"transcription": "benchmark_transcription_reference.v1",
                                                                     "layout": "benchmark_layout_reference.v1"},
                "items": items}
    path = tmp_path / "reference_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    index = tmp_path / "asset_index.json"
    index.write_text(json.dumps({"items": [{"item_id": e["item_id"], "page_sha256": [e["sha"]]} for e in entries]}))
    return path


def _predictions(directory: Path, texts: dict[str, str]) -> Path:
    directory.mkdir(parents=True)
    for index, (sha, text) in enumerate(sorted(texts.items())):
        payload = {"schema_version": "heocr_engine_prediction.v1", "page_id": f"sha256:{sha}", "track": "open",
                   "input": {"sha256": sha, "width": 1, "height": 1}, "engine": {"name": "e", "version": "1"},
                   "pipeline": [{"kind": "recognize", "name": "e", "version": "1", "track": "open",
                                 "deterministic": True, "requires_network": False}],
                   "text": text, "words": []}
        (directory / f"p{index}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def _gold_pages() -> dict[str, str]:
    gold = load_synthetic_gold(BATCH)
    return {entry["page_sha256"][0]: gold["texts"][entry["item_id"]] for entry in gold["asset_index"]}


ENTRIES = [
    {"item_id": "ws:printed-1", "text": PRINTED_TEXT, "sha": "a1" * 32, "modality": "printed", "footnotes": 1},
    {"item_id": "ws:printed-2", "text": "ספר הזכרונות", "sha": "a2" * 32, "modality": "printed"},
    {"item_id": "hash:hand-1", "text": "מכתב קצר", "sha": "b1" * 32, "modality": "handwritten"},
    {"item_id": "x:none-1", "text": "בלי סוג", "sha": "c1" * 32},
]


def test_manifest_item_facts_are_optional_and_omitted_when_unset() -> None:
    base = {"reference_id": "r", "item_id": "i", "source_id": "s", "source_item_id": "x", "visibility": "public",
            "public_reference_status": "draft", "adjudication_status": "not_started"}
    plain = BenchmarkReferenceManifestItemRecord.model_validate(base)
    assert "modality" not in plain.model_dump(mode="json") and "reference_normalization" not in plain.model_dump_json()
    full = BenchmarkReferenceManifestItemRecord.model_validate(
        {**base, "modality": "printed", "reference_normalization": {"footnote_marker_style": "bracketed_index",
                                                                    "footnote_count": 2}})
    assert full.model_dump(mode="json")["modality"] == "printed"
    with pytest.raises(ValueError):
        BenchmarkReferenceManifestItemRecord.model_validate({**base, "modality": "synthetic"})
    # The packaged benchmark_v1 manifest serializes exactly as before (no new keys).
    payload = json.loads(BENCHMARK_V1_MANIFEST.read_text(encoding="utf-8"))
    dumped = BenchmarkReferenceManifestRecord.model_validate(payload).model_dump(mode="json")
    assert all("modality" not in item and "reference_normalization" not in item for item in dumped["items"])


def test_modality_track_scores_only_its_modality_and_lists_the_rest(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path, ENTRIES)
    printed = load_adjudicated_references(manifest, modality="printed")
    assert sorted(printed["references"]) == ["ws:printed-1", "ws:printed-2"]
    reasons = {entry["item_id"]: entry["reason"] for entry in printed["excluded"]}
    assert reasons["hash:hand-1"] == "modality handwritten is not this run's printed track"
    assert reasons["x:none-1"].startswith("no modality declared")
    assert printed["strata"]["ws:printed-1"] == {"reference_origin": "adjudicated_reference", "modality": "printed"}
    every = load_adjudicated_references(manifest)
    assert len(every["references"]) == 4 and every["strata"]["x:none-1"] == {"reference_origin": "adjudicated_reference"}
    with pytest.raises(StageExecutionError, match="modality must be one of"):
        load_adjudicated_references(manifest, modality="synthetic")
    only_none = _manifest(tmp_path / "none", [ENTRIES[3]])
    with pytest.raises(StageExecutionError, match="no adjudicated reference in the handwritten modality track"):
        load_adjudicated_references(only_none, modality="handwritten")


def test_modality_run_reports_modality_beside_an_unchanged_synthetic_block(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "refs", ENTRIES)
    pages = _gold_pages()
    texts = {**pages, "a1" * 32: PRINTED_PRINT, "a2" * 32: "ספר הזכרונות", "b1" * 32: "מכתב", "c1" * 32: "x"}
    predictions = _predictions(tmp_path / "pred", texts)
    synthetic_only = run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH)
    assert "modality" not in synthetic_only and "reference_views" not in synthetic_only
    assert "modality" not in synthetic_only["run_record"] and "paired_bootstrap" not in synthetic_only["run_record"]
    report = run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH, reference_manifest=manifest,
                                      asset_index_path=tmp_path / "refs" / "asset_index.json", modality="printed")
    assert report["modality"] == "printed" and report["track"] == "open"
    assert report["scored"]["synthetic_gold"] == synthetic_only["scored"]["synthetic_gold"]
    adjudicated = report["scored"]["adjudicated_reference"]
    assert adjudicated["modality"] == "printed" and adjudicated["evaluated_item_count"] == 2
    assert set(adjudicated["strata"]["modality"]) == {"printed"}
    assert report["run_record"]["modality"] == "printed"
    assert {e["item_id"] for e in report["run_record"]["excluded_references"]} == {"hash:hand-1", "x:none-1"}
    with pytest.raises(StageExecutionError, match="needs --reference-manifest"):
        run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH, modality="printed")


def test_footnote_masked_pair_masks_marks_on_both_sides() -> None:
    record = BenchmarkTranscriptionReferenceRecord.model_validate(_reference("ws:printed-1", PRINTED_TEXT))
    prediction, reference, stats = footnote_masked_pair(record, PRINTED_PRINT, marker_style="bracketed_index")
    assert "[" not in reference and "*" not in prediction
    assert stats == {"reference_marks": 2, "masked_reference_characters": 6, "removed_prediction_characters": 4}
    assert prediction.split() == reference.split()
    plain = BenchmarkTranscriptionReferenceRecord.model_validate(_reference("ws:p", "ללא הערות"))
    assert footnote_masked_pair(plain, "ללא הערות", marker_style="bracketed_index")[2]["reference_marks"] == 0
    with pytest.raises(ValueError, match="unsupported footnote marker style"):
        footnote_masked_pair(record, PRINTED_PRINT, marker_style="superscript")


def test_footnote_view_appears_only_for_declared_items_and_never_changes_scored(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "refs", ENTRIES[:2])
    index = tmp_path / "refs" / "asset_index.json"
    predictions = _predictions(tmp_path / "pred", {"a1" * 32: PRINTED_PRINT, "a2" * 32: "ספר הזכרונות"})
    report = run_reference_evaluation(predictions_dir=predictions, reference_manifest=manifest, asset_index_path=index,
                                      modality="printed")
    view = report["reference_views"]["adjudicated_reference"][FOOTNOTE_MASKED_VIEW_ID]
    assert view["item_count"] == 1 and view["masking"]["reference_marks"] == 2
    as_is, masked = view["views"]["as_is"], view["views"][FOOTNOTE_MASKED_VIEW_ID]
    assert as_is["items"][0]["profiles"] == next(
        item for item in report["scored"]["adjudicated_reference"]["items"] if item["item_id"] == "ws:printed-1")["profiles"]
    assert as_is["profiles"]["primary.v1"]["character_edits"] > 0
    assert masked["profiles"]["primary.v1"]["character_edits"] == 0
    assert report["run_record"]["reference_views"][0]["view_id"] == FOOTNOTE_MASKED_VIEW_ID
    plain = _manifest(tmp_path / "plain", ENTRIES[1:2])
    plain_report = run_reference_evaluation(predictions_dir=predictions, reference_manifest=plain,
                                            asset_index_path=tmp_path / "plain" / "asset_index.json")
    assert "reference_views" not in plain_report and "reference_views" not in plain_report["run_record"]
    same_item = [item for item in report["scored"]["adjudicated_reference"]["items"] if item["item_id"] == "ws:printed-2"]
    assert plain_report["scored"]["adjudicated_reference"]["items"][0]["profiles"] == same_item[0]["profiles"]


def test_paired_bootstrap_is_deterministic_and_brackets_the_delta(tmp_path: Path) -> None:
    baseline = [(10, 100), (0, 50), (5, 80), (20, 100)]
    candidate = [(5, 100), (0, 50), (5, 80), (10, 100)]
    first = paired_bootstrap_interval(baseline, candidate, resamples=500, seed=3)
    assert first == paired_bootstrap_interval(baseline, candidate, resamples=500, seed=3)
    delta = (20 - 35) / 330
    assert first[0] <= delta <= first[1] <= 0 < first[1] - first[0]
    assert paired_bootstrap_interval([], [], resamples=10, seed=0) is None
    with pytest.raises(ValueError):
        paired_bootstrap_interval(baseline, candidate[:2], resamples=10, seed=0)

    manifest = _manifest(tmp_path / "refs", ENTRIES[:2])
    index = tmp_path / "refs" / "asset_index.json"
    base = _predictions(tmp_path / "base", {"a1" * 32: "שלום", "a2" * 32: "ספר"})
    cand = _predictions(tmp_path / "cand", {"a1" * 32: PRINTED_PRINT, "a2" * 32: "ספר הזכרונות"})
    report = run_reference_evaluation(predictions_dir=cand, baseline_predictions_dir=base, reference_manifest=manifest,
                                      asset_index_path=index, modality="printed", bootstrap_resamples=200, bootstrap_seed=1)
    primary = report["comparison"]["deltas"]["adjudicated_reference"]["profiles"]["primary.v1"]
    low, high = primary["paired_bootstrap"]["delta_cer_interval"]
    assert low <= primary["delta_cer"] <= high and primary["paired_bootstrap"]["resamples"] == 200
    view = report["comparison"]["reference_view_deltas"]["adjudicated_reference"][FOOTNOTE_MASKED_VIEW_ID]
    assert "paired_bootstrap" in view[FOOTNOTE_MASKED_VIEW_ID]["profiles"]["primary.v1"]
    assert report["run_record"]["paired_bootstrap"] == {"resamples": 200, "seed": 1, "confidence": 0.95, "unit": "item"}
    plain = run_reference_evaluation(predictions_dir=cand, baseline_predictions_dir=base, reference_manifest=manifest,
                                     asset_index_path=index)
    assert "paired_bootstrap" not in plain["comparison"]["deltas"]["adjudicated_reference"]["profiles"]["primary.v1"]
    with pytest.raises(StageExecutionError, match="needs --baseline-predictions"):
        run_reference_evaluation(predictions_dir=cand, reference_manifest=manifest, asset_index_path=index,
                                 bootstrap_resamples=10)


def test_cli_passes_modality_and_bootstrap(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    manifest = _manifest(tmp_path / "refs", ENTRIES[:2])
    index = tmp_path / "refs" / "asset_index.json"
    base = _predictions(tmp_path / "base", {"a1" * 32: "שלום", "a2" * 32: "ספר"})
    cand = _predictions(tmp_path / "cand", {"a1" * 32: PRINTED_PRINT, "a2" * 32: "ספר הזכרונות"})
    out = tmp_path / "report.json"
    assert main(["evaluate-references", "--predictions", str(cand), "--baseline-predictions", str(base),
                 "--reference-manifest", str(manifest), "--asset-index", str(index), "--modality", "printed",
                 "--bootstrap-resamples", "50", "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["modality"] == "printed" and report["run_record"]["paired_bootstrap"]["resamples"] == 50
    capsys.readouterr()
    assert main(["evaluate-references", "--predictions", str(cand), "--synthetic-batch", str(BATCH),
                 "--modality", "handwritten"]) == 1
    assert "needs --reference-manifest" in capsys.readouterr().out


def test_bit_parallel_levenshtein_equals_the_dynamic_program() -> None:
    import random

    from hocrgen.evaluation import _levenshtein_dp, levenshtein_distance

    rng = random.Random(20261106)
    alphabet = "אבגדה ,.\n[]1"
    for _ in range(2000):
        left = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 70)))
        right = "".join(rng.choice(alphabet) for _ in range(rng.randrange(0, 70)))
        assert levenshtein_distance(left, right) == _levenshtein_dp(left, right)
    for _ in range(300):
        left = [rng.choice(["שלום", "עולם", "x", "y"]) for _ in range(rng.randrange(0, 40))]
        right = [rng.choice(["שלום", "עולם", "x", "z"]) for _ in range(rng.randrange(0, 40))]
        assert levenshtein_distance(left, right) == _levenshtein_dp(left, right)
    assert levenshtein_distance("kitten", "sitting") == 3 and levenshtein_distance("", "abc") == 3
