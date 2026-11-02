from __future__ import annotations

import json
from pathlib import Path

import pytest

from hocrgen.cli import main
from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_runs import (
    build_mapping_from_asset_sha256,
    load_engine_prediction,
    load_synthetic_gold,
    run_reference_evaluation,
    validate_mapping,
)

BATCH = package_root() / "data" / "hocrsyngen" / "contracts" / "generation_manifest_v1" / "fixture-batch"
REFERENCE_MANIFEST = package_root() / "data" / "benchmark" / "benchmark_v1" / "reference_manifest.json"
NLI_ITEM = "nli_any_use_permitted:nli-ms-seed-006"
NLI_PAGE_SHA = "ab" * 32


def _prediction(sha: str, text: str, *, schema: str = "1.0", pipeline: list | None = None,
                track: str | None = None) -> dict:
    payload = {"schema_version": schema, "page_id": f"sha256:{sha}", "input": {"sha256": sha, "width": 1, "height": 1},
               "engine": {"name": "tesseract", "version": "tesseract 5.3.0"}, "text": text, "words": []}
    if pipeline is not None:
        payload["pipeline"] = pipeline
    if track is not None:
        payload["track"] = track
    return payload


def _stage(kind: str, name: str, version: str, *, track: str = "open", requires_network: bool = False) -> dict:
    return {"kind": kind, "name": name, "version": version, "track": track, "deterministic": True,
            "requires_network": requires_network}


def _write_predictions(directory: Path, texts: dict[str, str], **kwargs) -> Path:
    directory.mkdir(parents=True)
    for index, (sha, text) in enumerate(sorted(texts.items())):
        (directory / f"page-{index}.json").write_text(json.dumps(_prediction(sha, text, **kwargs), ensure_ascii=False),
                                                       encoding="utf-8")
    return directory


def _gold_pages() -> dict[str, str]:
    gold = load_synthetic_gold(BATCH)
    return {entry["page_sha256"][0]: gold["texts"][entry["item_id"]] for entry in gold["asset_index"]}


def test_synthetic_gold_run_derives_mapping_from_sha256_and_records_the_run(tmp_path: Path) -> None:
    pages = _gold_pages()
    predictions = _write_predictions(tmp_path / "pred", {sha: text + "  \n" for sha, text in pages.items()})
    report = run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH)

    gold = report["scored"]["synthetic_gold"]
    assert gold["evaluated_item_count"] == 2
    assert gold["profiles"]["primary.v1"]["cer"] == 0
    assert gold["profiles"]["raw.v1"]["cer"] > 0
    assert set(gold["strata"]["modality"]) == {"synthetic"}
    assert set(gold["strata"]["reference_origin"]) == {"synthetic_gold"}
    record = report["run_record"]
    assert record["schema_version"] == "hocrgen_reference_evaluation_run.v1"
    assert record["mapping"]["mapping_source"] == "asset_sha256"
    assert record["references"][0]["reference_manifest_id"].startswith("synthetic_gold:")
    assert len(record["predictions"]["files"]) == 2 and len(record["predictions"]["set_sha256"]) == 64
    assert record["hocrgen_version"] and record["primary_profile"] == "primary.v1"
    assert record["scored_origins"] == ["synthetic_gold"]
    assert str(tmp_path) not in json.dumps(report)


def test_prediction_loader_accepts_both_schema_ids_and_fails_closed(tmp_path: Path) -> None:
    sha = "cd" * 32
    path = tmp_path / "p.json"
    for schema in ("1.0", "heocr_engine_prediction.v1"):
        path.write_text(json.dumps(_prediction(sha, "x", schema=schema, pipeline=[_stage("recognize", "t", "5")],
                                               track="open")))
        assert load_engine_prediction(path)["schema_version"] == schema
    path.write_text(json.dumps(_prediction(sha, "x", schema="2.0")))
    with pytest.raises(StageExecutionError, match="unsupported schema_version"):
        load_engine_prediction(path)
    bad = _prediction(sha, "x")
    bad["page_id"] = "sha256:" + "ef" * 32
    path.write_text(json.dumps(bad))
    with pytest.raises(StageExecutionError, match="does not match"):
        load_engine_prediction(path)


def test_mapping_validation_rejects_reused_pages() -> None:
    with pytest.raises(StageExecutionError, match="mapped more than once"):
        validate_mapping({"schema_version": "hocrgen_reference_page_mapping.v1", "mapping_source": "explicit",
                          "items": [{"item_id": "a", "page_ids": ["p"]}, {"item_id": "b", "page_ids": ["p"]}]})
    with pytest.raises(StageExecutionError, match="invalid page sha256"):
        build_mapping_from_asset_sha256([{"item_id": "a", "page_sha256": ["nothex"]}])


def test_unreviewed_texts_are_diagnostic_only_and_cannot_claim_scored_origin(tmp_path: Path) -> None:
    pages = _gold_pages()
    hash_sha = "12" * 32
    predictions = _write_predictions(tmp_path / "pred", {**pages, hash_sha: "שלום"})
    unreviewed = tmp_path / "unreviewed.jsonl"
    unreviewed.write_text(json.dumps({"item_id": "hash_public_domain:loc__x", "text": "שלום עולם",
                                      "reference_origin": "hash_htr_candidate", "modality": "handwritten"},
                                     ensure_ascii=False) + "\n", encoding="utf-8")
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"items": [{"item_id": "hash_public_domain:loc__x", "page_sha256": [hash_sha]}]}))
    report = run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH,
                                      unreviewed_texts=unreviewed, asset_index_path=index)
    diagnostics = report["unreviewed_diagnostics"]
    assert diagnostics["scored"] is False and diagnostics["benchmark_ready"] is False
    assert diagnostics["evaluated_item_count"] == 1
    assert "hash_public_domain:loc__x" not in {i["item_id"] for i in report["scored"]["synthetic_gold"]["items"]}
    assert report["scored"]["synthetic_gold"]["profiles"]["primary.v1"]["cer"] == 0
    unreviewed.write_text(json.dumps({"item_id": "x", "text": "t", "reference_origin": "synthetic_gold"}) + "\n")
    with pytest.raises(StageExecutionError, match="cannot claim scored origin"):
        run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH, unreviewed_texts=unreviewed,
                                 asset_index_path=index)


def test_reference_manifest_scores_only_adjudicated_items(tmp_path: Path) -> None:
    predictions = _write_predictions(tmp_path / "pred", {NLI_PAGE_SHA: "שלום"})
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"items": [{"item_id": NLI_ITEM, "page_sha256": [NLI_PAGE_SHA]}]}))
    report = run_reference_evaluation(predictions_dir=predictions, reference_manifest=REFERENCE_MANIFEST,
                                      asset_index_path=index, alignment_masked=True)
    scored = report["scored"]["adjudicated_reference"]
    assert [item["item_id"] for item in scored["items"]] == [NLI_ITEM]
    assert scored["diagnostics"]["alignment_masked"]["primary_eligible"] is False
    excluded = {entry["item_id"] for entry in report["run_record"]["excluded_references"]}
    assert excluded == {"pinkas_open:pinkas-ledger-001", "project_synthetic:synthetic-0"}
    assert report["run_record"]["references"][0]["reference_manifest_id"] == "benchmark_v1_refs_0001"


def test_baseline_comparison_reports_delta_and_single_stage_attribution(tmp_path: Path) -> None:
    pages = _gold_pages()
    stage = _stage("recognize", "tesseract", "5.3.0")
    post = _stage("postcorrect", "lexicon", "0.1")
    baseline = _write_predictions(tmp_path / "base", {sha: text[:-3] for sha, text in pages.items()}, pipeline=[stage])
    candidate = _write_predictions(tmp_path / "cand", pages, pipeline=[stage, post])
    report = run_reference_evaluation(predictions_dir=candidate, synthetic_batch=BATCH, baseline_predictions_dir=baseline)
    delta = report["comparison"]["deltas"]["synthetic_gold"]["profiles"]["primary.v1"]
    assert delta["candidate_cer"] == 0 and delta["baseline_cer"] > 0 and delta["delta_cer"] < 0
    assert report["comparison"]["single_stage_attribution"] == {"change": "added", "position": 1, "stage": post}
    assert report["run_record"]["baseline_predictions"]["pipelines"] == [[stage]]


def test_cli_writes_report_and_mapping(tmp_path: Path, capsys) -> None:
    predictions = _write_predictions(tmp_path / "pred", _gold_pages())
    output, mapping = tmp_path / "out" / "report.json", tmp_path / "out" / "mapping.json"
    exit_code = main(["evaluate-references", "--predictions", str(predictions), "--synthetic-batch", str(BATCH),
                      "--profile", "primary.v1", "--profile", "consonantal.v1",
                      "--output", str(output), "--write-mapping", str(mapping)])
    assert exit_code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["run_record"]["profiles"] == ["primary.v1", "consonantal.v1"]
    assert json.loads(mapping.read_text(encoding="utf-8"))["mapping_source"] == "asset_sha256"
    capsys.readouterr()
    assert main(["evaluate-references", "--predictions", str(predictions)]) == 1
    assert "scored set is required" in capsys.readouterr().out


def test_raw_public_batch_is_accepted_only_after_page_checksums_verify(tmp_path: Path) -> None:
    import shutil

    batch = tmp_path / "raw-batch"
    shutil.copytree(BATCH, batch)
    manifest_path = batch / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("provider_metadata")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    gold = load_synthetic_gold(batch)
    assert gold["identity"]["validation"] == "public_manifest_page_checksums"
    assert sorted(gold["texts"]) == ["project_synthetic:synthetic-0", "project_synthetic:synthetic-1"]
    assert load_synthetic_gold(BATCH)["identity"]["validation"] == "hocrgen_release_path_model"
    asset = batch / manifest["samples"][0]["pages"][0]["asset_path"]
    asset.write_bytes(b"tampered")
    with pytest.raises(StageExecutionError, match="checksum mismatch"):
        load_synthetic_gold(batch)


def test_prediction_track_rules_follow_engine_decision_0005(tmp_path: Path) -> None:
    sha = "cd" * 32
    path = tmp_path / "p.json"

    def load(**kwargs):
        path.write_text(json.dumps(_prediction(sha, "x", **kwargs)))
        return load_engine_prediction(path)

    assert load()["track"] == "open"  # legacy "1.0" without track
    assert load(schema="heocr_engine_prediction.v1", track="proprietary",
                pipeline=[_stage("recognize", "gpt", "4o", track="proprietary", requires_network=True)])["track"] == "proprietary"
    with pytest.raises(StageExecutionError, match="track must be one of"):
        load(schema="heocr_engine_prediction.v1")  # v1 requires track
    with pytest.raises(StageExecutionError, match="track must be one of"):
        load(track="closed")
    with pytest.raises(StageExecutionError, match="is track open but pipeline stage 1 is proprietary"):
        load(schema="heocr_engine_prediction.v1", track="open",
             pipeline=[_stage("recognize", "t", "5"), _stage("postcorrect", "llm", "1", track="proprietary")])
    with pytest.raises(StageExecutionError, match="invalid track"):
        load(schema="heocr_engine_prediction.v1", track="open", pipeline=[{"kind": "recognize", "name": "t", "version": "5"}])
    with pytest.raises(StageExecutionError, match="requires_network: false"):
        load(schema="heocr_engine_prediction.v1", track="open",
             pipeline=[_stage("recognize", "t", "5", requires_network=True)])


def test_prediction_sets_have_one_track_recorded_everywhere(tmp_path: Path) -> None:
    pages = _gold_pages()
    (first, first_text), (second, second_text) = sorted(pages.items())
    mixed = tmp_path / "mixed"
    mixed.mkdir()
    (mixed / "a.json").write_text(json.dumps(_prediction(first, first_text), ensure_ascii=False), encoding="utf-8")
    (mixed / "b.json").write_text(json.dumps(_prediction(second, second_text, schema="heocr_engine_prediction.v1",
                                                         track="proprietary"), ensure_ascii=False), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="mixes tracks"):
        run_reference_evaluation(predictions_dir=mixed, synthetic_batch=BATCH)
    proprietary = _write_predictions(tmp_path / "prop", pages, schema="heocr_engine_prediction.v1", track="proprietary")
    report = run_reference_evaluation(predictions_dir=proprietary, synthetic_batch=BATCH)
    assert report["track"] == "proprietary"
    assert report["run_record"]["predictions"]["track"] == "proprietary"
    assert report["scored"]["synthetic_gold"]["track"] == "proprietary"


def test_comparison_refuses_sets_on_different_tracks(tmp_path: Path) -> None:
    pages = _gold_pages()
    open_set = _write_predictions(tmp_path / "open", pages)
    proprietary = _write_predictions(tmp_path / "prop", pages, schema="heocr_engine_prediction.v1", track="proprietary")
    with pytest.raises(StageExecutionError, match="refusing to compare"):
        run_reference_evaluation(predictions_dir=proprietary, synthetic_batch=BATCH, baseline_predictions_dir=open_set)
    same = run_reference_evaluation(predictions_dir=open_set, synthetic_batch=BATCH, baseline_predictions_dir=open_set)
    assert same["comparison"]["track"] == "open"
    assert same["comparison"]["deltas"]["synthetic_gold"]["profiles"]["primary.v1"]["delta_cer"] == 0


def test_hardened_batch_that_fails_validation_raises_instead_of_falling_back(tmp_path: Path) -> None:
    import shutil

    batch = tmp_path / "hardened"
    shutil.copytree(BATCH, batch)
    manifest_path = batch / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provider_metadata"]["used_network"] = "sometimes"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="validation failed"):
        load_synthetic_gold(batch)


def test_comparison_uses_common_items_and_ordered_single_stage_attribution(tmp_path: Path) -> None:
    pages = _gold_pages()
    a, b, c = _stage("preprocess", "deskew", "1"), _stage("recognize", "tesseract", "5"), _stage("postcorrect", "lex", "1")
    (first, first_text), (second, second_text) = sorted(pages.items())
    baseline = _write_predictions(tmp_path / "base", {first: first_text, second: "x"}, pipeline=[a, b])
    # The candidate omits the badly recognised item and reorders stages while adding one.
    candidate = _write_predictions(tmp_path / "cand", {first: first_text}, pipeline=[b, a, c])
    report = run_reference_evaluation(predictions_dir=candidate, synthetic_batch=BATCH, baseline_predictions_dir=baseline)
    gold = report["comparison"]["deltas"]["synthetic_gold"]
    assert gold["common_item_count"] == 1 and gold["baseline_only_items"]
    assert gold["profiles"]["primary.v1"]["delta_cer"] == 0  # no fake improvement from the omitted item
    assert report["comparison"]["single_stage_attribution"] is None  # reorder + add is not one stage change
    replaced = _write_predictions(tmp_path / "repl", pages, pipeline=[a, _stage("recognize", "tesseract", "6")])
    again = run_reference_evaluation(predictions_dir=replaced, synthetic_batch=BATCH,
                                     baseline_predictions_dir=_write_predictions(tmp_path / "b2", pages, pipeline=[a, b]))
    assert again["comparison"]["single_stage_attribution"]["change"] == "replaced"


def test_malformed_inputs_raise_structured_errors(tmp_path: Path, capsys) -> None:
    sha = "cd" * 32
    path = tmp_path / "p.json"
    for broken in ({"input": "bad"}, {"engine": ["x"]}):
        payload = _prediction(sha, "x")
        payload.update(broken)
        path.write_text(json.dumps(payload))
        with pytest.raises(StageExecutionError, match="input and engine objects"):
            load_engine_prediction(path)
    with pytest.raises(StageExecutionError, match="list of objects"):
        validate_mapping({"schema_version": "hocrgen_reference_page_mapping.v1", "mapping_source": "explicit"})
    with pytest.raises(StageExecutionError, match="list of objects"):
        validate_mapping({"schema_version": "hocrgen_reference_page_mapping.v1", "mapping_source": "explicit",
                          "items": ["x"]})
    predictions = _write_predictions(tmp_path / "pred", _gold_pages())
    unreviewed = tmp_path / "u.jsonl"
    unreviewed.write_text("[]\n")
    with pytest.raises(StageExecutionError, match="JSON object"):
        run_reference_evaluation(predictions_dir=predictions, synthetic_batch=BATCH, unreviewed_texts=unreviewed)
    manifest = tmp_path / "refs" / "manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"schema_version": "benchmark_reference_manifest.v1", "items": [{}]}))
    assert main(["evaluate-references", "--predictions", str(predictions), "--reference-manifest", str(manifest)]) == 1
    assert "invalid reference manifest" in capsys.readouterr().out


def _copy_reference_manifest(tmp_path: Path) -> tuple[Path, dict]:
    import shutil

    root = tmp_path / "benchmark"
    shutil.copytree(REFERENCE_MANIFEST.parent, root)
    manifest_path = root / "reference_manifest.json"
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def test_reference_manifest_rejects_duplicates_and_verifies_child_checksums(tmp_path: Path) -> None:
    import hashlib

    from hocrgen.reference_runs import load_adjudicated_references

    manifest_path, manifest = _copy_reference_manifest(tmp_path)
    loaded = load_adjudicated_references(manifest_path)
    child = loaded["identity"]["child_references"][0]
    child_path = manifest_path.parent / child["path"]
    assert child["sha256"] == hashlib.sha256(child_path.read_bytes()).hexdigest()
    before = loaded["identity"]["child_references_sha256"]
    child_path.write_text(child_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert load_adjudicated_references(manifest_path)["identity"]["child_references_sha256"] != before
    ready = next(item for item in manifest["items"] if item["item_id"] == NLI_ITEM)
    ready["transcription_reference"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="checksum mismatch"):
        load_adjudicated_references(manifest_path)
    ready["transcription_reference"]["sha256"] = None
    manifest["items"].append(dict(ready))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="(?s)invalid reference manifest.*duplicate"):
        load_adjudicated_references(manifest_path)


def _diagnostic_inputs(tmp_path: Path) -> tuple[Path, Path, str]:
    """One unreviewed handwritten page (generic synthetic strings) plus its sha256 asset index."""
    sha = "34" * 32
    unreviewed = tmp_path / "unreviewed.jsonl"
    unreviewed.write_text(json.dumps({"item_id": "hash:page-1", "text": "שלום עולם",
                                      "reference_origin": "unreviewed:test_edition", "modality": "handwritten"},
                                     ensure_ascii=False) + "\n", encoding="utf-8")
    index = tmp_path / "index.json"
    index.write_text(json.dumps({"items": [{"item_id": "hash:page-1", "page_sha256": [sha]}]}))
    return unreviewed, index, sha


def test_diagnostic_only_scores_unreviewed_text_without_a_scored_set(tmp_path: Path) -> None:
    unreviewed, index, sha = _diagnostic_inputs(tmp_path)
    predictions = _write_predictions(tmp_path / "pred", {sha: "שלום עולם"})
    report = run_reference_evaluation(predictions_dir=predictions, unreviewed_texts=unreviewed,
                                      asset_index_path=index, diagnostic_only=True)
    assert report["diagnostic_only"] is True and report["benchmark_ready"] is False
    assert report["scored"] == {} and "comparison" not in report and "diagnostic_comparison" not in report
    diagnostics = report["unreviewed_diagnostics"]
    assert diagnostics["benchmark_ready"] is False and diagnostics["scored"] is False
    assert diagnostics["profiles"]["primary.v1"]["cer"] == 0
    assert set(diagnostics["strata"]["reference_origin"]) == {"unreviewed:test_edition"}
    record = report["run_record"]
    assert record["diagnostic_only"] is True and record["benchmark_ready"] is False
    assert record["references"] == [] and record["scored_origins"] == []
    assert record["scored_set_policy"].startswith("diagnostic only")
    assert str(tmp_path) not in json.dumps(report)


def test_diagnostic_only_baseline_delta_is_a_diagnostic_comparison(tmp_path: Path) -> None:
    unreviewed, index, sha = _diagnostic_inputs(tmp_path)
    stage = _stage("recognize", "kraken", "7")
    baseline = _write_predictions(tmp_path / "base", {sha: "שלום"}, pipeline=[stage])
    candidate = _write_predictions(tmp_path / "cand", {sha: "שלום עולם"},
                                   pipeline=[_stage("recognize", "kraken", "8")])
    report = run_reference_evaluation(predictions_dir=candidate, unreviewed_texts=unreviewed, asset_index_path=index,
                                      baseline_predictions_dir=baseline, diagnostic_only=True)
    assert "comparison" not in report
    comparison = report["diagnostic_comparison"]
    assert comparison["benchmark_ready"] is False and comparison["scored"] is False
    assert comparison["reference_status"] == "unreviewed" and comparison["track"] == "open"
    delta = comparison["unreviewed_deltas"]["profiles"]["primary.v1"]
    assert delta["candidate_cer"] == 0 and delta["baseline_cer"] > 0 and delta["delta_cer"] < 0
    assert comparison["unreviewed_deltas"]["common_item_count"] == 1
    assert comparison["single_stage_attribution"]["change"] == "replaced"
    proprietary = _write_predictions(tmp_path / "prop", {sha: "שלום"}, schema="heocr_engine_prediction.v1",
                                     track="proprietary")
    with pytest.raises(StageExecutionError, match="refusing to compare"):
        run_reference_evaluation(predictions_dir=proprietary, unreviewed_texts=unreviewed, asset_index_path=index,
                                 baseline_predictions_dir=baseline, diagnostic_only=True)


def test_diagnostic_only_refuses_scored_inputs_and_incomplete_runs(tmp_path: Path, capsys) -> None:
    unreviewed, index, sha = _diagnostic_inputs(tmp_path)
    predictions = _write_predictions(tmp_path / "pred", {sha: "שלום"})
    base = {"predictions_dir": predictions, "unreviewed_texts": unreviewed, "asset_index_path": index,
            "diagnostic_only": True}
    refused = [
        ({"synthetic_batch": BATCH}, "either diagnostic or scored"),
        ({"reference_manifest": REFERENCE_MANIFEST}, "either diagnostic or scored"),
        ({"unreviewed_texts": None}, "requires --unreviewed-texts"),
        ({"asset_index_path": None}, "requires --mapping or --asset-index"),
        ({"alignment_masked": True}, "only to adjudicated references"),
    ]
    for override, message in refused:
        with pytest.raises(StageExecutionError, match=message):
            run_reference_evaluation(**{**base, **override})
    empty = tmp_path / "empty.jsonl"
    empty.write_text("\n")
    with pytest.raises(StageExecutionError, match="at least one unreviewed text"):
        run_reference_evaluation(**{**base, "unreviewed_texts": empty})
    common = ["evaluate-references", "--predictions", str(predictions), "--unreviewed-texts", str(unreviewed),
              "--asset-index", str(index)]
    assert main([*common, "--diagnostic-only", "--synthetic-batch", str(BATCH)]) == 1
    assert "either diagnostic or scored" in capsys.readouterr().out
    assert main([*common, "--diagnostic-only"]) == 0
    assert json.loads(capsys.readouterr().out)["diagnostic_only"] is True


def test_unreviewed_texts_without_a_scored_set_still_need_the_flag(tmp_path: Path, capsys) -> None:
    unreviewed, index, sha = _diagnostic_inputs(tmp_path)
    predictions = _write_predictions(tmp_path / "pred", {sha: "שלום"})
    with pytest.raises(StageExecutionError, match="a scored set is required"):
        run_reference_evaluation(predictions_dir=predictions, unreviewed_texts=unreviewed, asset_index_path=index)
    assert main(["evaluate-references", "--predictions", str(predictions), "--unreviewed-texts", str(unreviewed),
                 "--asset-index", str(index)]) == 1
    assert "a scored set is required" in capsys.readouterr().out
    # A scored run keeps its shape and states that it is not diagnostic-only.
    gold = run_reference_evaluation(predictions_dir=_write_predictions(tmp_path / "gold", _gold_pages()),
                                    synthetic_batch=BATCH)
    assert gold["run_record"]["diagnostic_only"] is False and "diagnostic_only" not in gold
