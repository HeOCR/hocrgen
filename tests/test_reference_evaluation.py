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


def test_unreviewed_pair_is_explicitly_diagnostic():
    from hocrgen.reference_evaluation import score_unreviewed_text_pair

    result = score_unreviewed_text_pair(prediction="e\u0301 לא 12", reference="é אין 13", normalize_nfc=True)
    assert result["reference_status"] == "unreviewed"
    assert result["benchmark_ready"] is False
    assert result["raw"]["cer"] != result["nfc"]["cer"]
    assert not result["raw"]["diagnostics"]["number_tokens_match"]


def test_reported_spans_and_raw_page_boundaries():
    span = {"span_id": "uncertain-1", "line_id": "l", "start": 0, "end": 1,
            "status": "uncertain", "scoring": "include_primary_and_report"}
    ref = record("א", [span])
    result = evaluate_reference_predictions(["x"], predictions={"x": "א\n"}, references={"x": ref})
    assert result["items"][0]["reference_spans"] == {"uncertain": {"count": 1, "span_ids": ["uncertain-1"]}}
    assert result["raw"]["cer"] == 1  # Raw engine trailing newline is not silently stripped.
    from hocrgen.reference_evaluation import assemble_page_predictions
    assert assemble_page_predictions({"p1": "א\n", "p2": "ב\n"}, item_pages={"x": ["p1", "p2"]})["x"] == "א\n\nב\n"


def test_negation_comparison_strips_boundary_punctuation_only_for_diagnostic():
    from hocrgen.reference_evaluation import score_unreviewed_text_pair
    result = score_unreviewed_text_pair(prediction="לא,", reference="לא")
    assert result["raw"]["diagnostics"]["negation_tokens_match"]
    assert result["raw"]["cer"] > 0


def test_reference_serialization_retains_empty_and_fully_excluded_lines_across_pages():
    payload = record().model_dump()
    payload["pages"] = [{"page_id": "p2", "reading_order": 2}, {"page_id": "p1", "reading_order": 1}]
    payload["lines"] = [
        {"page_id": "p2", "line_id": "last", "reading_order": 1, "text": "ד"},
        {"page_id": "p1", "line_id": "first", "reading_order": 1, "text": "א"},
        {"page_id": "p1", "line_id": "empty", "reading_order": 2, "text": ""},
        {"page_id": "p1", "line_id": "excluded", "reading_order": 3, "text": "ב"},
    ]
    payload["spans"] = [{"span_id": "s", "line_id": "excluded", "start": 0, "end": 1,
                         "status": "deleted", "scoring": "exclude_primary"}]
    ref = BenchmarkTranscriptionReferenceRecord.model_validate(payload)
    assert reference_text(ref) == "א\n\n\nד"
    result = evaluate_reference_predictions(["x"], predictions={"x": "א\n\n\nד"}, references={"x": ref})
    assert result["raw"]["cer"] == 0
