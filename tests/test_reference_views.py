"""E2c7: the per-cell reference view derived from hocrsyngen line annotations (``logical_join``)."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_runs import load_per_cell_view, load_synthetic_gold, run_reference_evaluation

BATCH = package_root() / "data" / "hocrsyngen" / "contracts" / "generation_manifest_v1" / "fixture-batch"
LEDGER_ITEM = "project_synthetic:synthetic-1"
# (text, logical_line_index, logical_join): a ledger row of five cells whose details cell wraps, then a note whose
# text holds a literal " | " that is not a cell join and must stay scored.
LEDGER_SEGMENTS = [
    ("פנקס חשבונות", 0, None),
    ("01", 1, None), ("19/05", 1, "cell"), ("563", 1, "cell"), ("סעיף", 1, "cell"), ("ראשון", 1, "space"),
    ("1200", 1, "cell"),
    ("הערה | ללא שינוי", 2, None),
]
LEDGER_GOLD = "פנקס חשבונות\n01 | 19/05 | 563 | סעיף ראשון | 1200\nהערה | ללא שינוי"
LEDGER_PER_CELL = "פנקס חשבונות\n01\n19/05\n563\nסעיף ראשון\n1200\nהערה | ללא שינוי"


def _batch(tmp_path: Path, *, annotate: bool = True) -> Path:
    """A raw public copy of the fixture batch whose second sample is a ledger page, plus its line sidecar."""
    batch = tmp_path / ("annotated" if annotate else "plain")
    shutil.copytree(BATCH, batch)
    manifest_path = batch / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("provider_metadata")
    manifest["samples"][1]["text"]["logical_order"] = LEDGER_GOLD
    manifest["samples"][1]["provenance"]["template_id"] = "ledger"
    raw = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
    manifest_path.write_bytes(raw)
    if annotate:
        first = manifest["samples"][0]["text"]["logical_order"].split("\n")
        segments = [[(text, index, None) for index, text in enumerate(first)], LEDGER_SEGMENTS]
        pages = [{"page_id": sample["pages"][0]["page_id"], "page_sha256": sample["pages"][0]["sha256"],
                  "sample_id": sample["sample_id"],
                  "lines": [{"line_index": i, "logical_line_index": index, "logical_join": join, "text": text}
                            for i, (text, index, join) in enumerate(page_segments)]}
                 for sample, page_segments in zip(manifest["samples"], segments)]
        sidecar = {"schema": "hocrsyngen_line_annotations.v1", "coordinate_space": "final_page_pixels",
                   "generation_manifest_sha256": hashlib.sha256(raw).hexdigest(), "pages": pages}
        (batch / "line_annotations.json").write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    return batch


def _predictions(directory: Path, batch: Path, texts: dict[str, str]) -> Path:
    directory.mkdir(parents=True)
    gold = load_synthetic_gold(batch)
    for index, entry in enumerate(gold["asset_index"]):
        sha = entry["page_sha256"][0]
        payload = {"schema_version": "1.0", "page_id": f"sha256:{sha}", "input": {"sha256": sha, "width": 1, "height": 1},
                   "engine": {"name": "kraken", "version": "5.3.0"}, "words": [],
                   "text": texts.get(entry["item_id"], gold["texts"][entry["item_id"]])}
        (directory / f"page-{index}.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return directory


def _without_views(report: dict) -> dict:
    report = {key: value for key, value in report.items() if key != "reference_views"}
    report["run_record"] = {key: value for key, value in report["run_record"].items() if key != "reference_views"}
    if "comparison" in report:
        report["comparison"] = {k: v for k, v in report["comparison"].items() if k != "reference_view_deltas"}
    return report


def _dump(report: dict) -> bytes:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")  # as the CLI writes it


def test_view_turns_only_cell_joins_into_line_breaks(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    view = load_per_cell_view(batch, load_synthetic_gold(batch))
    # Only the ledger item has cell joins; the wrapped details cell keeps its space and the note keeps its " | ".
    assert view["texts"] == {LEDGER_ITEM: LEDGER_PER_CELL}
    assert view["view_id"] == "per_cell.v1"
    assert view["source"]["sha256"] == hashlib.sha256((batch / "line_annotations.json").read_bytes()).hexdigest()
    assert load_per_cell_view(_batch(tmp_path, annotate=False), load_synthetic_gold(batch)) is None


def test_cell_items_are_scored_against_both_views(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    per_cell = _predictions(tmp_path / "per-cell", batch, {LEDGER_ITEM: LEDGER_PER_CELL})
    report = run_reference_evaluation(predictions_dir=per_cell, synthetic_batch=batch)
    block = report["reference_views"]["synthetic_gold"]["per_cell.v1"]
    assert block["item_count"] == 1
    as_is, view = block["views"]["logical_order"], block["views"]["per_cell.v1"]
    assert [item["item_id"] for item in view["items"]] == [LEDGER_ITEM]
    assert view["strata"]["document_type"].keys() == {"ledger"}
    # Line-per-cell output pays 3 edits per cell boundary (" | " -> "\n") against logical_order, none per cell.
    assert as_is["profiles"]["primary.v1"]["character_edits"] == 12
    assert view["profiles"]["primary.v1"]["character_edits"] == 0
    # The logical_order view is the scored item's own result.
    scored = {item["item_id"]: item for item in report["scored"]["synthetic_gold"]["items"]}
    assert as_is["items"][0]["profiles"] == scored[LEDGER_ITEM]["profiles"]
    assert report["run_record"]["reference_views"] == [{"origin": "synthetic_gold", "view_id": "per_cell.v1",
                                                         "item_count": 1, "source": load_per_cell_view(
        batch, load_synthetic_gold(batch))["source"]}]
    # A literal "|" in page text is not a cell join, so splitting it is still an error in the per-cell view.
    split_note = _predictions(tmp_path / "split-note", batch,
                              {LEDGER_ITEM: LEDGER_PER_CELL.replace("הערה | ללא", "הערה\nללא")})
    report = run_reference_evaluation(predictions_dir=split_note, synthetic_batch=batch)
    view = report["reference_views"]["synthetic_gold"]["per_cell.v1"]["views"]["per_cell.v1"]
    assert view["profiles"]["primary.v1"]["character_edits"] == 3


def test_comparison_reports_paired_deltas_for_both_views(tmp_path: Path) -> None:
    batch = _batch(tmp_path)
    rows = _predictions(tmp_path / "rows", batch, {})
    cells = _predictions(tmp_path / "cells", batch, {LEDGER_ITEM: LEDGER_PER_CELL})
    report = run_reference_evaluation(predictions_dir=cells, baseline_predictions_dir=rows, synthetic_batch=batch)
    deltas = report["comparison"]["reference_view_deltas"]["synthetic_gold"]["per_cell.v1"]
    as_is = deltas["logical_order"]["profiles"]["primary.v1"]["paired_edit_accounting"]["characters"]
    view = deltas["per_cell.v1"]["profiles"]["primary.v1"]["paired_edit_accounting"]["characters"]
    assert (as_is["baseline_edits"], as_is["candidate_edits"], as_is["items_worsened"]) == (0, 12, 1)
    assert (view["baseline_edits"], view["candidate_edits"], view["items_improved"]) == (12, 0, 1)


def test_existing_report_fields_are_byte_identical_with_and_without_line_annotations(tmp_path: Path) -> None:
    """Pin: the view is additive. Every existing field, primary.v1 included, is unchanged byte for byte."""
    annotated, plain = _batch(tmp_path), _batch(tmp_path, annotate=False)
    texts = {LEDGER_ITEM: LEDGER_PER_CELL}
    for name, kwargs in (("single", {}), ("compare", {"baseline": {}})):
        runs = {}
        for batch in (annotated, plain):
            candidate = _predictions(tmp_path / f"{name}-{batch.name}-cand", batch, texts)
            extra = {}
            if "baseline" in kwargs:
                extra["baseline_predictions_dir"] = _predictions(tmp_path / f"{name}-{batch.name}-base", batch, {})
            runs[batch.name] = run_reference_evaluation(predictions_dir=candidate, synthetic_batch=batch,
                                                        profiles=["primary.v1", "raw.v1", "punct_folded.v1"], **extra)
        with_views, without = runs["annotated"], runs["plain"]
        assert "reference_views" not in without and "reference_views" not in without["run_record"]
        assert "reference_view_deltas" not in without.get("comparison", {})
        assert "reference_views" in with_views
        assert _dump(_without_views(with_views)) == _dump(without)


@pytest.mark.parametrize("tamper, message", [
    (lambda sidecar: sidecar.update(generation_manifest_sha256="0" * 64), "does not belong"),
    (lambda sidecar: sidecar["pages"][1]["lines"][2].update(text="20/05"), "do not rebuild logical_order"),
    (lambda sidecar: sidecar["pages"][1]["lines"][2].update(logical_join="tab"), "invalid logical_line_index"),
    (lambda sidecar: sidecar["pages"].pop(0), "does not annotate every item"),
    (lambda sidecar: sidecar["pages"][0].update(page_sha256="ab" * 32), "not in the generation manifest"),
    (lambda sidecar: sidecar.update(schema="hocrsyngen_line_annotations.v0"), "is not a"),
])
def test_present_but_inconsistent_sidecar_fails_closed(tmp_path: Path, tamper, message) -> None:
    batch = _batch(tmp_path)
    path = batch / "line_annotations.json"
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    tamper(sidecar)
    path.write_text(json.dumps(sidecar, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(StageExecutionError, match=message):
        load_per_cell_view(batch, load_synthetic_gold(batch))
