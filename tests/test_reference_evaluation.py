from copy import deepcopy

import pytest

from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord
from hocrgen.reference_evaluation import evaluate_reference_predictions, reference_text


def record(text="שלום עולם", spans=None):
    return BenchmarkTranscriptionReferenceRecord.model_validate({
        "schema_version": "benchmark_transcription_reference.v1", "item_id": "x", "source_id": "s", "source_item_id": "i",
        "normalization": {"unicode": "NFC", "text_order": "logical"},
        "language_scripts": [{"language": "he", "script": "Hebr", "direction": "rtl"}],
        "scoring_policy": {"uncertain": "include_primary_and_report", "illegible": "exclude_primary", "damaged": "include_readable_and_report", "deleted": "exclude_primary", "marginal": "include_when_ordered_else_separate"},
        "pages": [{"page_id": "p", "reading_order": 1}],
        "lines": [{"page_id": "p", "line_id": "l", "reading_order": 1, "text": text}],
        "spans": spans or [], "review": {"status": "reviewed"},
    })


def test_scoring_coverage_and_order():
    result = evaluate_reference_predictions(["x", "missing"], predictions={"x": "עולם שלום", "extra": ""}, references={"x": record()})
    assert result["prediction_coverage"] == result["reference_coverage"] == .5
    assert result["missing_predictions"] == result["missing_references"] == ["missing"]
    assert result["unexpected_predictions"] == ["extra"]
    assert result["items"][0]["raw"]["diagnostics"]["same_word_multiset_different_order"]
    assert result["raw"]["wer"] == 1


def test_nfc_is_optional_and_raw_preserved():
    result = evaluate_reference_predictions(["x"], predictions={"x": "e\u0301"}, references={"x": record("é")}, normalize_nfc=True)
    assert result["raw"]["cer"] == 2
    assert result["nfc"]["cer"] == 0


def test_exclusion_offsets_and_fail_closed():
    span = {"span_id": "s", "line_id": "l", "start": 2, "end": 4, "status": "deleted", "scoring": "exclude_primary"}
    assert reference_text(record("abcdef", [span])) == "abef"
    conflict = deepcopy(span)
    conflict.update(span_id="t", status="uncertain", scoring="include_primary_and_report")
    with pytest.raises(ValueError, match="overlapping"):
        reference_text(record("abcdef", [span, conflict]))
    bad = record()
    bad.scoring_policy["deleted"] = "unknown"
    with pytest.raises(ValueError, match="unsupported"):
        reference_text(bad)
    bad.review.status = "draft"
    with pytest.raises(ValueError, match="reviewed"):
        reference_text(bad)


def test_empty_reference_and_literal_diagnostics():
    result = evaluate_reference_predictions(["x"], predictions={"x": "לא 12"}, references={"x": record("")})
    assert result["raw"]["cer"] is None and result["raw"]["wer"] is None
    diagnostics = result["items"][0]["raw"]["diagnostics"]
    assert not diagnostics["number_tokens_match"] and not diagnostics["negation_tokens_match"]


def test_page_assembly_requires_explicit_complete_mapping():
    from hocrgen.reference_evaluation import assemble_page_predictions

    assert assemble_page_predictions({"a": "ראשון", "b": "שני"}, item_pages={"x": ["b", "a"]}) == {"x": "שני\nראשון"}
    with pytest.raises(ValueError, match="mapped more than once"):
        assemble_page_predictions({"a": "x"}, item_pages={"x": ["a"], "y": ["a"]})
    with pytest.raises(ValueError, match="unmapped"):
        assemble_page_predictions({"a": "x"}, item_pages={})


def test_unreviewed_reference_is_rejected_even_without_prediction():
    ref = record()
    ref.review.status = "draft"
    with pytest.raises(ValueError, match="reviewed"):
        evaluate_reference_predictions(["x"], predictions={}, references={"x": ref})
