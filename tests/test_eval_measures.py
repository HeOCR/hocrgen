"""E2e3: line-aligned page measures, letter-level edits and missed-region cost (invented fixtures only)."""
from __future__ import annotations

from pathlib import Path

import pytest

from hocrgen import eval_measures
from hocrgen.reference_evaluation import line_matched_prediction, pair_lines
from hocrgen.reference_runs import run_reference_evaluation

from test_eval_slices import NEW, _labels, _line_inputs, CAND_LINES
from test_reference_modality_tracks import _manifest, _predictions

LONG = "אבגדהוזחטיכלמנסעפצקרשת"  # 22 letters
RUN = "בגד" * 8  # 24 letters, none of them in the surrounding paragraph fixture


def test_hebrew_letters_ignore_marks_punctuation_and_latin() -> None:
    assert eval_measures.hebrew_letters("שָׁלוֹם, abc 12 ךםןףץ!") == "שלוםךםןףץ"


def test_letter_edits_count_substitutions_deletions_insertions() -> None:
    counts = eval_measures.letter_edits("שלוס עולםם", "שלום, עולם!")
    assert counts == {"reference_letters": 8, "substitutions": 1, "deletions": 0, "insertions": 1,
                      "deletion_run_letters": 0, "skipped": False}
    # Niqqud and punctuation never count, on either side.
    assert eval_measures.letter_edits("שָׁלוֹם", "שלום.")["substitutions"] == 0
    # A deletion run of at least 20 letters is a missed region; a shorter one is not.
    long_run = eval_measures.letter_edits("שלום", f"שלום {LONG}")
    assert long_run["deletions"] == 22 and long_run["deletion_run_letters"] == 22
    short_run = eval_measures.letter_edits("שלום", f"שלום {LONG[:19]}")
    assert short_run["deletions"] == 19 and short_run["deletion_run_letters"] == 0
    assert eval_measures.letter_edits("אב", "אב", max_cells=1)["skipped"] is True


def test_line_aligned_pairs_lines_and_counts_unpaired_lines_as_misses() -> None:
    reference = "כותרת\nגוף ראשון\nגוף שני"
    stats = eval_measures.line_aligned("גוף שני\nכותרת", reference, ["primary.v1"])["primary.v1"]
    assert stats == {"reference_lines": 3, "exact_lines": 2, "missed_lines": 1, "line_edits": 9,
                     "reference_characters": 21, "missed_characters": 9}
    # pair_lines is the line_matched.v1 pairing itself.
    ref_lines, pred_lines, pairs = pair_lines("גוף שני\nכותרת", reference)
    assert [pred_lines[pairs[i]] for i in sorted(pairs)] == ["כותרת", "גוף שני"]
    assert line_matched_prediction("גוף שני\nכותרת", reference)[0] == "כותרת\nגוף שני"


def _within_line_run(tmp_path: Path) -> dict:
    entries = [{"item_id": "rs:p-1", "text": "כותרת\nגוף ראשון\nגוף שני", "sha": "e1" * 32, "reading_order": "within_line"},
               {"item_id": "rs:p-2", "text": f"פסקה אחת {RUN} סוף", "sha": "e2" * 32}]
    manifest = _manifest(tmp_path / "refs", entries)
    cand = _predictions(tmp_path / "cand", {"e1" * 32: "גוף שני\nכותרת", "e2" * 32: "פסקה אחת סוף"})
    labels = _labels(tmp_path / "labels.json", {e["item_id"]: {"node": NEW, "niqqud": "unpointed"} for e in entries})
    return run_reference_evaluation(predictions_dir=cand, reference_manifest=manifest,
                                    asset_index_path=tmp_path / "refs" / "asset_index.json", eval_labels=labels)


def test_runs_report_line_aligned_letter_and_missed_region_measures(tmp_path: Path) -> None:
    report = _within_line_run(tmp_path)
    view = report["reference_views"]["adjudicated_reference"]["line_matched.v1"]["views"]["line_matched.v1"]
    headline = view["eval_slices"]["slices"][NEW]["ALL"]["excluding_pointed"]
    aligned = headline["profiles"]["primary.v1"]["line_aligned"]
    assert aligned["reference_lines"] == 3 and aligned["exact_line_rate"] == pytest.approx(2 / 3)
    assert aligned["line_cer"] == pytest.approx(9 / 21) and aligned["missed_line_rate"] == pytest.approx(1 / 3)
    region = headline["missed_region_diagnostic"]
    assert region["method"] == eval_measures.UNPAIRED_LINES and region["missed_region_cost"] == pytest.approx(9 / 21)
    letters = headline["letter_diagnostic"]
    # Letters are aligned on the line_matched.v1 prediction, so block order is not counted; the missing line is.
    assert letters["diagnostic_only"] and letters["deletions"] == 8 and letters["substitutions"] == 0
    page = report["scored"]["adjudicated_reference"]["eval_slices"]["slices"][NEW]["ALL"]["excluding_pointed"]
    assert "line_aligned" not in page["profiles"]["primary.v1"]  # paragraph references: no physical lines
    paragraph = page["missed_region_diagnostic"]
    assert paragraph["method"] == eval_measures.DELETION_RUNS and paragraph["missed_letters"] == 24
    assert page["letter_diagnostic"]["deletion_rate"] == pytest.approx(24 / page["letter_diagnostic"]["reference_letters"])


def test_line_reference_mode_gets_letter_diagnostic_without_missed_region(tmp_path: Path) -> None:
    line_set, index, preds = _line_inputs(tmp_path, CAND_LINES)
    report = run_reference_evaluation(predictions_dir=preds, line_references=line_set, asset_index_path=index)
    record = report["scored"]["line_reference"]["measures"]["strata"]["source"]["wikisource_he_proofread"]
    assert record["letter_diagnostic"]["substitutions"] == 1 and record["letter_diagnostic"]["items"] == 5
    assert "missed_region_diagnostic" not in record


def test_runs_without_slices_have_no_new_measures(tmp_path: Path) -> None:
    entries = [{"item_id": "rs:p-1", "text": "כותרת\nגוף", "sha": "e1" * 32, "reading_order": "within_line"}]
    manifest = _manifest(tmp_path / "refs", entries)
    cand = _predictions(tmp_path / "cand", {"e1" * 32: "גוף\nכותרת"})
    text = str(run_reference_evaluation(predictions_dir=cand, reference_manifest=manifest,
                                        asset_index_path=tmp_path / "refs" / "asset_index.json"))
    assert "letter_diagnostic" not in text and "line_aligned" not in text and "missed_region" not in text


def test_exposed_items_enter_no_line_letter_or_missed_region_number(tmp_path: Path) -> None:
    entries = [{"item_id": "rs:p-1", "text": "כותרת\nגוף ראשון\nגוף שני", "sha": "e1" * 32, "reading_order": "within_line"},
               {"item_id": "rs:p-3", "text": "שורה אחת\nשורה שתיים", "sha": "e3" * 32, "reading_order": "within_line"},
               {"item_id": "rs:p-2", "text": f"פסקה אחת {RUN} סוף", "sha": "e2" * 32},
               {"item_id": "rs:p-4", "text": "פסקה שניה", "sha": "e4" * 32}]
    manifest = _manifest(tmp_path / "refs", entries)
    cand = _predictions(tmp_path / "cand", {"e1" * 32: "גוף שני\nכותרת", "e3" * 32: "שורה אחת\nשורה שתיים",
                                            "e2" * 32: "פסקה אחת סוף", "e4" * 32: "פסקה שניה"})
    labels = {e["item_id"]: {"node": NEW, "niqqud": "unpointed"} for e in entries}
    for item_id in ("rs:p-1", "rs:p-2"):
        labels[item_id] = {**labels[item_id], "exposed": ["R8"], "exposure_reason": "selection dev (fixture)"}
    path = _labels(tmp_path / "labels.json", labels)

    def run(model_id: str) -> dict:
        return run_reference_evaluation(predictions_dir=cand, reference_manifest=manifest, eval_labels=path,
                                        asset_index_path=tmp_path / "refs" / "asset_index.json", model_id=model_id)

    exposed, clean = run("R8"), run("R1")
    for report, (lines, missed_lines, deleted) in ((exposed, (2, 0, 0)), (clean, (5, 1, 24))):
        view = report["reference_views"]["adjudicated_reference"]["line_matched.v1"]["views"]["line_matched.v1"]
        headline = view["eval_slices"]["slices"][NEW]["ALL"]["excluding_pointed"]
        aligned = headline["profiles"]["primary.v1"]["line_aligned"]
        assert aligned["reference_lines"] == lines and aligned["missed_lines"] == missed_lines
        assert headline["letter_diagnostic"]["items"] == headline["items"]
        assert headline["missed_region_diagnostic"]["items"] == headline["items"]
        page = report["scored"]["adjudicated_reference"]["eval_slices"]["slices"][NEW]["ALL"]["excluding_pointed"]
        assert page["missed_region_diagnostic"]["missed_letters"] == deleted
        assert page["letter_diagnostic"]["deletions"] == deleted and page["letter_diagnostic"]["items"] == page["items"]
    assert exposed["scored"]["adjudicated_reference"]["eval_slices"]["excluded_exposed"]["item_ids"] == ["rs:p-2"]
    line_view = exposed["reference_views"]["adjudicated_reference"]["line_matched.v1"]["views"]["line_matched.v1"]
    assert line_view["eval_slices"]["excluded_exposed"]["item_ids"] == ["rs:p-1"]


def test_exposed_lines_enter_no_letter_number(tmp_path: Path) -> None:
    line_set, index, preds = _line_inputs(tmp_path, CAND_LINES)
    labels = {i: {"node": NEW, "niqqud": "unpointed"} for i in ["l1", "l2", "l3", "l4", "l5", "l6"]}
    labels["l3"] = {**labels["l3"], "exposed": ["R8"], "exposure_reason": "PBY selection dev (fixture)"}
    report = run_reference_evaluation(predictions_dir=preds, line_references=line_set, asset_index_path=index,
                                      eval_labels=_labels(tmp_path / "labels.json", labels), model_id="R8")
    headline = report["scored"]["line_reference"]["measures"]["slices"][NEW]["ALL"]["excluding_pointed"]
    # l3 holds the only substitution; with it excluded, no letter edit is left but l4's deletions.
    assert headline["letter_diagnostic"]["items"] == 4 and headline["letter_diagnostic"]["substitutions"] == 0
