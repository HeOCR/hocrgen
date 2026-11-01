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


def test_normalization_profiles_are_versioned_and_applied_to_both_sides():
    from hocrgen.reference_evaluation import NORMALIZATION_PROFILES, evaluate_reference_profiles

    assert set(NORMALIZATION_PROFILES) == {"raw.v1", "nfc.v1", "primary.v1", "consonantal.v1", "punct_folded.v1"}
    primary = NORMALIZATION_PROFILES["primary.v1"]
    assert primary.apply("\u200fשלום\u2067  עולם \u061c\r\n\n") == "שלום עולם"
    assert NORMALIZATION_PROFILES["consonantal.v1"].apply("ש\u05b8\u05c1לו\u05b9ם\u0591") == "שלום"
    assert NORMALIZATION_PROFILES["punct_folded.v1"].apply("ת״א, בית־ספר.") == "תא בית ספר"
    result = evaluate_reference_profiles(
        ["x"], predictions={"x": "\u200fשלום   עולם\n"}, references={"x": record("ש\u05b8\u05c1לו\u05b9ם עולם ")},
    )
    assert result["primary_profile"] == "primary.v1"
    assert result["report_only_profiles"] == ["punct_folded.v1"]
    assert [p["profile_id"] for p in result["normalization_profiles"]][:2] == ["raw.v1", "nfc.v1"]
    assert result["profiles"]["raw.v1"]["cer"] > 0
    assert result["profiles"]["primary.v1"]["cer"] > 0  # niqqud differs and is preserved by primary
    assert result["profiles"]["consonantal.v1"]["cer"] == 0
    assert result["items"][0]["profiles"]["nfc.v1"]["reference_characters"] == len("ש\u05b8\u05c1לו\u05b9ם עולם ")


def test_profile_selection_fails_closed():
    from hocrgen.reference_evaluation import evaluate_reference_profiles

    with pytest.raises(ValueError, match="unknown normalization profile"):
        evaluate_reference_profiles(["x"], predictions={}, references={}, profiles=["primary.v1", "nfkc"])
    with pytest.raises(ValueError, match="must be evaluated"):
        evaluate_reference_profiles(["x"], predictions={}, references={}, profiles=["raw.v1"])


def test_strata_aggregate_by_dimension_with_reference_defaults():
    from hocrgen.reference_evaluation import evaluate_reference_profiles

    second = record("ב")
    second.item_id, second.source_id = "y", "other"
    result = evaluate_reference_profiles(
        ["x", "y"], predictions={"x": "שלום עולם", "y": "ג"}, references={"x": record(), "y": second},
        item_strata={"x": {"modality": "synthetic", "reference_origin": "synthetic_gold", "document_type": "letter"}},
    )
    strata = result["strata"]
    assert set(strata) == {"language_script", "modality", "source_id", "document_type", "reference_origin"}
    assert strata["language_script"]["he-Hebr"]["primary.v1"]["item_count"] == 2
    assert strata["modality"]["synthetic"]["primary.v1"]["cer"] == 0
    assert strata["modality"]["unknown"]["primary.v1"]["cer"] == 1
    assert set(strata["source_id"]) == {"s", "other"}
    with pytest.raises(ValueError, match="unsupported modality"):
        evaluate_reference_profiles(["x"], predictions={"x": ""}, references={"x": record()},
                                    item_strata={"x": {"modality": "mixed"}})
    with pytest.raises(ValueError, match="unknown stratum"):
        evaluate_reference_profiles(["x"], predictions={"x": ""}, references={"x": record()},
                                    item_strata={"x": {"writer": "a"}})


def test_alignment_masked_is_diagnostic_only_and_never_changes_profile_scores():
    from hocrgen.reference_evaluation import alignment_masked_prediction, evaluate_reference_profiles

    span = {"span_id": "s", "line_id": "l", "start": 4, "end": 7, "status": "illegible", "scoring": "exclude_primary"}
    ref = record("אבג דהו זחט", [span])
    masked, stats = alignment_masked_prediction(ref, "אבג XX זחט")
    assert masked == "אבג  זחט"
    assert stats == {"excluded_reference_characters": 3, "removed_prediction_characters": 2}
    plain = evaluate_reference_profiles(["x"], predictions={"x": "אבג דהו זחט"}, references={"x": ref})
    with_diag = evaluate_reference_profiles(["x"], predictions={"x": "אבג דהו זחט"}, references={"x": ref},
                                            alignment_masked=True)
    assert with_diag["profiles"] == plain["profiles"]
    assert "diagnostics" not in plain
    diagnostic = with_diag["diagnostics"]["alignment_masked"]
    assert diagnostic["diagnostic_only"] is True and diagnostic["primary_eligible"] is False
    assert diagnostic["aggregate"]["cer"] == 0
    assert plain["profiles"]["primary.v1"]["cer"] > 0  # unscoped prediction stays penalised in primary


def test_alignment_masked_skips_oversized_alignment_and_passes_through_without_exclusions():
    from hocrgen.reference_evaluation import alignment_masked_prediction, evaluate_alignment_masked

    assert alignment_masked_prediction(record(), "anything") == ("anything", {
        "excluded_reference_characters": 0, "removed_prediction_characters": 0})
    span = {"span_id": "s", "line_id": "l", "start": 0, "end": 1, "status": "deleted", "scoring": "exclude_primary"}
    result = evaluate_alignment_masked(["x"], predictions={"x": "abc"}, references={"x": record("xyz", [span])},
                                       max_cells=4)
    assert result["items"] == [] and result["skipped"][0]["reason"] == "alignment exceeds max_cells"


def test_bidi_and_hebrew_mark_sets_round_trip_through_their_escapes():
    from hocrgen.reference_evaluation import _BIDI_CONTROLS, _HEBREW_MARKS

    bidi = {0x200E, 0x200F, 0x061C, *range(0x202A, 0x202F), *range(0x2066, 0x206A)}
    marks = {*range(0x0591, 0x05BE), 0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7}
    assert {ord(char) for char in _BIDI_CONTROLS} == bidi
    assert {ord(char) for char in _HEBREW_MARKS} == marks
    for char in (*_BIDI_CONTROLS, *_HEBREW_MARKS):
        assert char.encode("unicode_escape").decode("ascii").encode("ascii").decode("unicode_escape") == char
    assert "־" not in _HEBREW_MARKS and "׃" not in _HEBREW_MARKS  # maqaf and sof pasuq stay punctuation


def test_strata_are_validated_for_requested_items_without_scored_inputs():
    from hocrgen.reference_evaluation import evaluate_reference_profiles

    with pytest.raises(ValueError, match="unsupported modality"):
        evaluate_reference_profiles(["x", "missing"], predictions={"x": ""}, references={"x": record()},
                                    item_strata={"missing": {"modality": "mixed"}})
    with pytest.raises(ValueError, match="unknown stratum"):
        evaluate_reference_profiles(["x", "missing"], predictions={}, references={"x": record()},
                                    item_strata={"missing": {"writer": "a"}})


def test_alignment_masked_rejects_duplicate_ids_mismatches_and_missing_inputs():
    from hocrgen.reference_evaluation import evaluate_alignment_masked

    with pytest.raises(ValueError, match="duplicate"):
        evaluate_alignment_masked(["x", "x"], predictions={"x": ""}, references={"x": record()})
    with pytest.raises(ValueError, match="mismatch"):
        evaluate_alignment_masked(["y"], predictions={"y": ""}, references={"y": record()})
    with pytest.raises(ValueError, match="needs both"):
        evaluate_alignment_masked(["x"], predictions={}, references={"x": record()})
