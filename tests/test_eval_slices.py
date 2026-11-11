"""Decisions 0017 and 0018: per-node eval labels, cluster intervals, page, order and line measures (synthetic fixtures only)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hocrgen import eval_slices
from hocrgen.cli import main
from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_runs import run_reference_evaluation
from hocrgen.tools import line_verify as lv

from test_line_verify import _bundle, _decision
from test_reference_modality_tracks import BATCH, _manifest, _predictions

# Nine invented pages over three domains; ws:h-* and ws:hist-* are two-line pages, ws:mod-3 is pointed.
TEXTS = {
    "ws:h-1": "מכתב קצר\nשורה שניה", "ws:h-2": "יומן אישי\nעוד שורה", "ws:h-3": "פתק",
    "ws:hist-1": "ספר ישן\nדף ראשון", "ws:hist-2": "ספר אחר\nדף שני", "ws:hist-3": "ספר שלישי",
    "ws:mod-1": "עיתון חדש", "ws:mod-2": "רשומות היום", "ws:mod-3": "שָׁלוֹם עוֹלָם",
}
SHA = {item_id: f"{index:02d}" * 32 for index, item_id in enumerate(sorted(TEXTS), start=10)}
NODE = {"h": "handwritten/new", "hist": "printed/old_printed", "mod": "printed/new_printed"}
H, OLD, NEW = NODE["h"], NODE["hist"], NODE["mod"]


def _label(item_id: str) -> dict:
    kind, number = item_id.split(":")[1].split("-")
    facets = {"genre": "laws" if number == "3" else "books", **({"font": "modern_sans"} if number == "2" else {})}
    return {"node": NODE[kind], "facets": facets,
            "niqqud": "pointed" if item_id == "ws:mod-3" else ("light" if number == "2" else "unpointed")}


def _labels(path: Path, labels: dict | None = None, **overrides: object) -> Path:
    payload = {"schema_version": "hocrgen_eval_labels.v1", "rule": "fixture rule", "provenance": "test fixture",
               "labels": labels if labels is not None else {item_id: _label(item_id) for item_id in TEXTS}, **overrides}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _clusters(path: Path, clusters: dict[str, str]) -> Path:
    path.write_text(json.dumps({"schema_version": "hocrgen_bootstrap_clusters.v1", "cluster_key": "book",
                                "clusters": clusters}), encoding="utf-8")
    return path


@pytest.fixture()
def inputs(tmp_path: Path) -> dict:
    manifest = _manifest(tmp_path / "refs", [{"item_id": k, "text": v, "sha": SHA[k], "modality": "printed"}
                                            for k, v in TEXTS.items()])
    # Candidate: one typo on h-1 and h-2's lines swapped; baseline: drops a word everywhere it can.
    cand_texts = {**TEXTS, "ws:h-1": "מכתב קצד\nשורה שניה", "ws:h-2": "עוד שורה\nיומן אישי"}
    base_texts = {k: v.split(" ")[0] for k, v in TEXTS.items()}
    return {"manifest": manifest, "index": tmp_path / "refs" / "asset_index.json",
            "cand": _predictions(tmp_path / "cand", {SHA[k]: v for k, v in cand_texts.items()}),
            "base": _predictions(tmp_path / "base", {SHA[k]: v for k, v in base_texts.items()}),
            "labels": _labels(tmp_path / "labels.json"),
            "clusters": _clusters(tmp_path / "clusters.json", {k: f"book-{i}" for i, k in enumerate(sorted(TEXTS))}),
            "tmp": tmp_path}


def _run(inputs: dict, **kwargs) -> dict:
    return run_reference_evaluation(predictions_dir=inputs["cand"], reference_manifest=inputs["manifest"],
                                    asset_index_path=inputs["index"], **kwargs)


def test_labels_load_and_fail_closed(tmp_path: Path) -> None:
    loaded = eval_slices.load_eval_labels(_labels(tmp_path / "ok.json"))
    assert loaded["labels"]["ws:mod-3"] == {"node": NEW, "genre": "laws", "font": "unset", "niqqud": "pointed"}
    assert len(loaded["sha256"]) == 64 and eval_slices.VERTICAL == NEW
    bad = [
        ({"labels": {"x": {"node": "P-mod", "niqqud": "pointed"}}}, "node must be one of"),
        ({"labels": {"x": {"node": NEW, "niqqud": "full"}}}, "niqqud"),
        ({"labels": {"x": {"node": NEW, "niqqud": "light", "facets": {"font": "frank_ruehl"}}}}, "facets.font"),
        ({"labels": {"x": {"node": NEW, "niqqud": "light", "facets": {"genre": ""}}}}, "facets.genre"),
        ({"labels": {"x": {"node": NEW, "niqqud": "light", "facets": {"era": "x"}}}}, "facets must be"),
        ({"labels": {"x": {"node": NEW, "niqqud": "light", "eval_domain": "H"}}}, "optionally facets"),
        ({"labels": {"x": {"niqqud": "light"}}}, "must have node and niqqud"),
        ({"labels": {}}, "non-empty"),
        ({"rule": ""}, "rule"),
        ({"provenance": None}, "provenance"),
        ({"schema_version": "v0"}, "schema_version"),
    ]
    for index, (override, message) in enumerate(bad):
        labels = override.pop("labels", None)
        with pytest.raises(StageExecutionError, match=message):
            eval_slices.load_eval_labels(_labels(tmp_path / f"bad{index}.json", labels, **override))


def test_runs_without_the_new_flags_add_no_new_keys(inputs: dict) -> None:
    plain = _run(inputs)
    text = json.dumps(plain, ensure_ascii=False)
    assert "eval_slices" not in text and "eval_labels" not in text and "line_reference" not in text
    assert "single_engine_cluster_bootstrap" not in plain["run_record"]


def test_eval_labels_add_strata_and_node_slices(inputs: dict) -> None:
    report = _run(inputs, eval_labels=inputs["labels"])
    scored = report["scored"]["adjudicated_reference"]
    assert set(scored["strata"]["node"]) == {H, OLD, NEW} and set(scored["strata"]["font"]) == {"modern_sans", "unset"}
    assert scored["items"][0]["strata"]["node"] in eval_slices.NODES
    block = scored["eval_slices"]
    assert block["labels"]["rule"] == "fixture rule" and "cluster_bootstrap" not in block
    assert "overall" not in block  # decision 0018 §5: no blended number
    slices = block["slices"]
    # The vertical: the pointed item enters no number but its own pointed slice, on consonantal.v1 only.
    assert set(slices[NEW]["ALL"]) == {"excluding_pointed", "unpointed", "light", "pointed"}
    headline = slices[NEW]["ALL"]["excluding_pointed"]
    assert headline["headline"] and headline["items"] == 2
    pointed = slices[NEW]["ALL"]["pointed"]
    assert list(pointed["profiles"]) == ["consonantal.v1"] and pointed["profile_scope"] == "consonantal_only"
    assert pointed["profiles"]["consonantal.v1"]["cer"] == 0.0
    assert slices[NEW]["genre=laws"]["excluding_pointed"]["items"] == 0
    # Every other node also reports 'ALL' with pointed items, and facet slices for the values present.
    assert set(slices[H]) == {"ALL", "genre=books", "genre=laws", "font=modern_sans"} and "ALL" in slices[H]["ALL"]
    assert slices[H]["font=modern_sans"]["ALL"]["items"] == 1
    assert not slices[H]["genre=books"]["excluding_pointed"].get("headline")
    assert slices[OLD]["ALL"]["excluding_pointed"]["headline"]
    h = slices[H]["ALL"]["excluding_pointed"]["profiles"]["primary.v1"]
    assert h["item_count"] == 3 and h["character_edits"] > 0
    distribution = h["page_cer_distribution"]
    assert distribution["units"] == 3 and distribution["median"] == pytest.approx(1 / 18)
    assert distribution["share_cer_lt_0.02"] == pytest.approx(1 / 3) and distribution["p90"] > 0.1
    assert set(block["strata"]) >= {"node", "genre", "font", "niqqud", "source_id"}
    # order diagnostic: h-2's swapped lines cost page-order edits that line_matched.v1 does not count.
    order = slices[H]["ALL"]["excluding_pointed"]["order_diagnostic"]
    assert order["diagnostic_only"] and order["items"] == 2 and order["order_cost"] > 0 and order["line_matched_cer"] < order["page_order_cer"]
    assert "missed_line_rate" not in order  # page references: lines are not declared physical
    assert report["run_record"]["eval_labels"]["labelled_items"] == 9


def test_unclassified_items_are_not_a_set_and_have_no_headline(inputs: dict) -> None:
    labels = {k: (_label(k) if not k.startswith("ws:hist") else {"node": "unclassified", "niqqud": "unpointed"})
              for k in TEXTS}
    slices = _run(inputs, eval_labels=_labels(inputs["tmp"] / "unclassified.json", labels))[
        "scored"]["adjudicated_reference"]["eval_slices"]["slices"]
    node = slices["unclassified"]
    assert set(node) == {"ALL"} and set(node["ALL"]) == {"excluding_pointed", "ALL", "unpointed"}
    assert all("not_a_set" in record["flags"] and not record.get("headline") for record in node["ALL"].values())
    assert slices[NEW]["ALL"]["excluding_pointed"]["headline"] and "not_a_set" not in slices[NEW]["ALL"]["excluding_pointed"]["flags"]


def test_unlabelled_scored_item_fails_the_run(inputs: dict) -> None:
    labels = {k: _label(k) for k in TEXTS if k != "ws:hist-2"}
    with pytest.raises(StageExecutionError, match="no label for 1 scored adjudicated reference item"):
        _run(inputs, eval_labels=_labels(inputs["tmp"] / "partial.json", labels))
    with pytest.raises(StageExecutionError, match="needs --reference-manifest or --line-references"):
        run_reference_evaluation(predictions_dir=inputs["cand"], synthetic_batch=BATCH, eval_labels=inputs["labels"])


def test_single_engine_cluster_intervals_and_flags(inputs: dict) -> None:
    report = _run(inputs, eval_labels=inputs["labels"], bootstrap_resamples=200, bootstrap_seed=4,
                  bootstrap_clusters=inputs["clusters"])
    block = report["scored"]["adjudicated_reference"]["eval_slices"]
    assert block["cluster_bootstrap"]["resamples"] == 200 and block["cluster_bootstrap"]["seed"] == 4
    everything = block["strata"]["reference_origin"]["adjudicated_reference"]
    assert everything["clusters"] == 9 and everything["flags"] == []
    primary = everything["profiles"]["primary.v1"]
    low, high = primary["cer_ci"]
    assert low <= primary["cer"] <= high and primary["interval_flags"] == []
    h = block["slices"][H]["ALL"]["excluding_pointed"]
    assert h["clusters"] == 3 and h["flags"] == ["low_cluster_count"]
    assert h["profiles"]["primary.v1"]["cer_ci"] is not None
    tiny = block["slices"][H]["genre=laws"]["excluding_pointed"]
    assert tiny["flags"] == ["too_few_clusters"] and tiny["profiles"]["primary.v1"]["cer_ci"] is None
    assert report["run_record"]["single_engine_cluster_bootstrap"]["cluster_key"] == "book"
    assert "paired_bootstrap" not in report["run_record"] and "comparison" not in report
    # Deterministic for a seed; without labels the block still gives strata, but no slices.
    again = _run(inputs, eval_labels=inputs["labels"], bootstrap_resamples=200, bootstrap_seed=4,
                 bootstrap_clusters=inputs["clusters"])
    assert again["scored"]["adjudicated_reference"]["eval_slices"] == block
    unlabelled = _run(inputs, bootstrap_resamples=50, bootstrap_clusters=inputs["clusters"])
    assert "slices" not in unlabelled["scored"]["adjudicated_reference"]["eval_slices"]
    with pytest.raises(StageExecutionError, match="needs --baseline-predictions"):
        _run(inputs, bootstrap_resamples=10)
    with pytest.raises(StageExecutionError, match="no cluster for 8 scored"):
        _run(inputs, bootstrap_resamples=10, bootstrap_clusters=_clusters(inputs["tmp"] / "one.json", {"ws:h-1": "b"}))


def test_paired_slice_intervals(inputs: dict) -> None:
    report = _run(inputs, baseline_predictions_dir=inputs["base"], eval_labels=inputs["labels"],
                  bootstrap_resamples=200, bootstrap_clusters=inputs["clusters"])
    deltas = report["comparison"]["deltas"]["adjudicated_reference"]
    assert "paired_cluster_bootstrap" in deltas["profiles"]["primary.v1"]  # existing behaviour kept
    paired = deltas["eval_slices"]
    assert paired["paired"] and paired["common_item_count"] == 9
    assert "overall" not in paired
    overall = paired["strata"]["reference_origin"]["adjudicated_reference"]["profiles"]["primary.v1"]
    low, high = overall["delta_cer_ci"]
    assert overall["delta_cer"] < 0 and low <= overall["delta_cer"] <= high
    assert overall["cer_separated"] is (high < 0 or low > 0)
    tiny = paired["slices"][OLD]["genre=laws"]["excluding_pointed"]["profiles"]["primary.v1"]
    assert tiny["delta_cer_ci"] is None and tiny["cer_separated"] is None and tiny["interval_flags"] == ["too_few_clusters"]
    # The candidate still gets its own single-engine interval beside the paired ones.
    single = report["scored"]["adjudicated_reference"]["eval_slices"]["slices"][H]["ALL"]["excluding_pointed"]
    assert single["profiles"]["primary.v1"]["cer_ci"]
    no_labels = _run(inputs, baseline_predictions_dir=inputs["base"], bootstrap_resamples=20,
                     bootstrap_clusters=inputs["clusters"])
    assert "eval_slices" not in no_labels["comparison"]["deltas"]["adjudicated_reference"]


def test_within_line_items_get_slices_with_missed_line_rate(tmp_path: Path) -> None:
    entries = [{"item_id": "rs:p-1", "text": "כותרת\nגוף ראשון\nגוף שני", "sha": "e1" * 32, "reading_order": "within_line"},
               {"item_id": "rs:p-2", "text": "שורה אחת\nשורה שתיים", "sha": "e2" * 32}]
    manifest = _manifest(tmp_path / "refs", entries)
    cand = _predictions(tmp_path / "cand", {"e1" * 32: "גוף שני\nכותרת", "e2" * 32: "שורה אחת\nשורה שתיים"})
    labels = _labels(tmp_path / "labels.json", {e["item_id"]: {"node": NEW, "facets": {"genre": "laws"},
                                                                "niqqud": "unpointed"} for e in entries})
    report = run_reference_evaluation(predictions_dir=cand, reference_manifest=manifest,
                                      asset_index_path=tmp_path / "refs" / "asset_index.json", eval_labels=labels)
    view = report["reference_views"]["adjudicated_reference"]["line_matched.v1"]["views"]["line_matched.v1"]
    order = view["eval_slices"]["slices"][NEW]["ALL"]["excluding_pointed"]["order_diagnostic"]
    assert order["missed_line_rate"] == pytest.approx(1 / 3) and order["missed_line_items"] == 1
    assert order["order_cost"] > 0
    page = report["scored"]["adjudicated_reference"]["eval_slices"]["slices"][NEW]["ALL"]["excluding_pointed"]
    assert page["items"] == 1 and page["order_diagnostic"]["order_cost"] == 0
    with pytest.raises(StageExecutionError, match="no label for 1"):
        run_reference_evaluation(predictions_dir=cand, reference_manifest=manifest,
                                 asset_index_path=tmp_path / "refs" / "asset_index.json",
                                 eval_labels=_labels(tmp_path / "l2.json", {"rs:p-2": _label("ws:h-1")}))


def test_cer_distribution_and_cluster_flags() -> None:
    page = eval_slices.cer_distribution([0.0, 0.02, 0.05, 0.3, None])
    assert page == {"units": 4, "median": 0.035, "p90": 0.3, "share_cer_lt_0.02": 0.25, "share_cer_lt_0.05": 0.5,
                    "share_cer_lt_0.10": 0.75}
    line = eval_slices.cer_distribution([0.0, 0.02, 0.05, 0.3], line=True)
    assert line["share_cer_le_0.02"] == 0.5 and line["share_cer_le_0.05"] == 0.75
    assert eval_slices.cer_distribution([])["median"] is None
    assert [eval_slices.cluster_flags(n) for n in (2, 3, 7, 8)] == [["too_few_clusters"], ["low_cluster_count"],
                                                                     ["low_cluster_count"], []]


# --- line-reference mode ----------------------------------------------------------------------------------------

def _line(item_id: str, text: str, book: str, *, pointed: bool = False, eligible: bool = True) -> dict:
    return {"item_id": item_id, "text": text, "book_id": book, "source": "wikisource_he_proofread",
            "pointed_print": pointed, "reference_views": ["consonantal"] if pointed else ["primary", "consonantal"],
            "adjudication_status": "adjudicated" if eligible else "pending", "reference_eligible": eligible}


def _line_set(path: Path, lines: list[dict]) -> Path:
    path.write_text(json.dumps({"schema_version": "line_verify_line_references.v1", "batch_id": "fixture",
                                "modality": "printed", "pages": [], "lines": lines}, ensure_ascii=False),
                    encoding="utf-8")
    return path


LINE_TEXTS = [("l1", "שורה ראשונה", "b1"), ("l2", "שורה שניה", "b1"), ("l3", "שורה שלישית", "b2"),
              ("l4", "שורה רביעית", "b3"), ("l5", "שלום", "b4")]


def _line_inputs(tmp_path: Path, predictions: dict[str, str]) -> tuple[Path, Path, Path]:
    lines = [_line(i, t, b) for i, t, b in LINE_TEXTS[:4]] + [_line("l5", "שלום", "b4", pointed=True),
                                                             _line("l6", "לא נבדק", "b4", eligible=False)]
    line_set = _line_set(tmp_path / "line_set.json", lines)
    shas = {item_id: f"f{n}" * 32 for n, item_id in enumerate(["l1", "l2", "l3", "l4", "l5", "l6"], start=1)}
    index = tmp_path / "line_index.json"
    index.write_text(json.dumps({"items": [{"item_id": k, "page_sha256": [v]} for k, v in shas.items()]}))
    preds = _predictions(tmp_path / f"preds-{len(list(tmp_path.iterdir()))}",
                         {shas[k]: v for k, v in predictions.items()})
    return line_set, index, preds


CAND_LINES = {"l1": "שורה ראשונה", "l2": "שורה שניה", "l3": "שורה שלישיח", "l4": "שורה", "l5": "שָׁלוֹם", "l6": "x"}


def test_line_reference_mode_scores_lines_and_honours_reference_views(tmp_path: Path) -> None:
    line_set, index, preds = _line_inputs(tmp_path, CAND_LINES)
    report = run_reference_evaluation(predictions_dir=preds, line_references=line_set, asset_index_path=index,
                                      bootstrap_resamples=100, bootstrap_seed=1)
    lines = report["scored"]["line_reference"]
    assert lines["unit"] == "line" and lines["evaluated_line_count"] == 5
    assert lines["excluded_lines"] == [{"item_id": "l6", "reason": "line reference is not adjudicated and reference-eligible"}]
    assert "overall" not in lines["measures"]
    measures = lines["measures"]["strata"]["source"]["wikisource_he_proofread"]["profiles"]
    # The pointed_print line enters consonantal.v1 only: primary counts 4 lines, consonantal 5.
    assert measures["primary.v1"]["item_count"] == 4 and measures["consonantal.v1"]["item_count"] == 5
    assert measures["primary.v1"]["exact_line_rate"] == 0.5 and measures["consonantal.v1"]["exact_line_rate"] == 0.6
    assert measures["primary.v1"]["line_cer_distribution"]["share_cer_le_0.02"] == 0.5
    assert measures["primary.v1"]["line_cer"] == measures["primary.v1"]["cer"]
    assert measures["primary.v1"]["interval_clusters"] == 3 and measures["primary.v1"]["interval_flags"] == ["low_cluster_count"]
    assert measures["consonantal.v1"]["interval_clusters"] == 4 and measures["consonantal.v1"]["cer_ci"] is not None
    assert lines["measures"]["strata"]["source"]["wikisource_he_proofread"]["clusters"] == 4
    pointed = next(item for item in lines["items"] if item["item_id"] == "l5")
    assert list(pointed["profiles"]) == ["consonantal.v1"]
    assert report["run_record"]["line_references"]["scored_line_count"] == 5
    assert report["run_record"]["scored_origins"] == ["line_reference"]
    with pytest.raises(StageExecutionError, match="needs the consonantal.v1 profile"):
        run_reference_evaluation(predictions_dir=preds, line_references=line_set, asset_index_path=index,
                                 profiles=["primary.v1"])
    with pytest.raises(StageExecutionError, match="needs --mapping or --asset-index"):
        run_reference_evaluation(predictions_dir=preds, line_references=line_set)


def test_line_reference_mode_with_labels_and_baseline(tmp_path: Path) -> None:
    line_set, index, cand = _line_inputs(tmp_path, CAND_LINES)
    _, _, base = _line_inputs(tmp_path, {k: "שורה" for k in CAND_LINES})
    labels = _labels(tmp_path / "labels.json", {i: {"node": NEW, "facets": {"font": "modern_serif"},
                                                    "niqqud": "pointed" if i == "l5" else "unpointed"}
                                                for i in ["l1", "l2", "l3", "l4", "l5", "l6"]})
    report = run_reference_evaluation(predictions_dir=cand, baseline_predictions_dir=base, line_references=line_set,
                                      asset_index_path=index, eval_labels=labels, bootstrap_resamples=50)
    slices = report["scored"]["line_reference"]["measures"]["slices"][NEW]["ALL"]
    assert slices["excluding_pointed"]["headline"] and list(slices["pointed"]["profiles"]) == ["consonantal.v1"]
    assert "ALL" not in slices  # the vertical: pointed lines only in the pointed slice
    delta = report["comparison"]["deltas"]["line_reference"]
    overall = delta["strata"]["source"]["wikisource_he_proofread"]["profiles"]["primary.v1"]
    assert delta["unit"] == "line" and overall["delta_cer"] < 0 and overall["interval_clusters"] == 3
    with pytest.raises(StageExecutionError, match="no label for 1 scored line reference"):
        run_reference_evaluation(predictions_dir=cand, line_references=line_set, asset_index_path=index,
                                 eval_labels=_labels(tmp_path / "few.json", {i: _label("ws:h-1") for i in ["l1", "l2", "l3", "l4"]}))


def test_line_references_loader_fails_closed(tmp_path: Path) -> None:
    good = _line("a", "שורה", "b")
    cases = [
        ([{**good, "reference_views": ["primary"]}], "includes consonantal"),
        ([{**good, "pointed_print": True}], "consonantal views only"),
        ([good, good], "unique item_id"),
        ([{**good, "text": ""}], "non-empty text"),
        ([_line("a", "שורה", "b", eligible=False)], "no adjudicated"),
        ([], "non-empty lines"),
    ]
    for index, (lines, message) in enumerate(cases):
        with pytest.raises(StageExecutionError, match=message):
            eval_slices.load_line_references(_line_set(tmp_path / f"c{index}.json", lines))
    (tmp_path / "wrong.json").write_text(json.dumps({"schema_version": "line_verify_references.v1"}), encoding="utf-8")
    with pytest.raises(StageExecutionError, match="schema_version"):
        eval_slices.load_line_references(tmp_path / "wrong.json")


def test_line_set_written_by_line_verify_loads(tmp_path: Path) -> None:
    assert eval_slices.LINE_REFERENCES_SCHEMA == lv.LINE_SET_SCHEMA
    _, bundle = _bundle(tmp_path)
    ids = [item["item_id"] for item in bundle["items"]]
    decisions = {"schema_version": lv.DECISIONS_SCHEMA, "batch_id": bundle["batch_id"], "decisions": [
        _decision(ids[0], "rv_aaaaaaa1", "exact"), _decision(ids[1], "rv_aaaaaaa1", "pointed_print"),
        _decision(ids[2], "rv_aaaaaaa1", "unreadable")]}
    document = lv.line_set(bundle, lv.resolve_decisions(bundle, decisions))
    path = tmp_path / "line_set.json"
    path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    loaded = eval_slices.load_line_references(path)
    assert sorted(loaded["texts"]) == sorted(ids[:2]) and loaded["views"][ids[1]] == ("consonantal",)
    assert set(loaded["clusters"]["clusters"].values()) == {bundle["pages"][0]["book_id"]}


def test_cli_passes_eval_labels_and_line_references(inputs: dict, capsys: pytest.CaptureFixture[str]) -> None:
    out = inputs["tmp"] / "report.json"
    assert main(["evaluate-references", "--predictions", str(inputs["cand"]), "--reference-manifest",
                 str(inputs["manifest"]), "--asset-index", str(inputs["index"]), "--eval-labels", str(inputs["labels"]),
                 "--bootstrap-resamples", "20", "--bootstrap-clusters", str(inputs["clusters"]),
                 "--output", str(out)]) == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["scored"]["adjudicated_reference"]["eval_slices"]["slices"][H]["ALL"]["excluding_pointed"]["headline"]
    capsys.readouterr()
    lines_dir = inputs["tmp"] / "lines"
    lines_dir.mkdir()
    line_set, index, preds = _line_inputs(lines_dir, CAND_LINES)
    assert main(["evaluate-references", "--predictions", str(preds), "--line-references", str(line_set),
                 "--asset-index", str(index)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["scored"]["line_reference"]["evaluated_line_count"] == 5
