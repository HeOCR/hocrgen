from hocrgen.reference_evaluation import _pair
from hocrgen.reference_runs import _report_deltas


def test_paired_accounting_uses_only_common_items_and_counts_both_directions():
    def report(pairs):
        return {"profiles": {"primary.v1": {}}, "items": [
            {"item_id": key, "profiles": {"primary.v1": _pair(pred, ref)}}
            for key, pred, ref in pairs
        ]}

    baseline = report([("a", "abcx", "abcd"), ("b", "abc", "abc"), ("missing", "x", "y")])
    candidate = report([("a", "abcd", "abcd"), ("b", "axc", "abc"), ("extra", "z", "z")])
    result = _report_deltas(baseline, candidate)
    assert result["common_item_count"] == 2
    assert result["baseline_only_items"] == ["missing"]
    assert result["candidate_only_items"] == ["extra"]
    chars = result["profiles"]["primary.v1"]["paired_edit_accounting"]["characters"]
    assert chars == {"baseline_edits": 1, "candidate_edits": 1, "reference_units": 7,
                     "items_improved": 1, "items_unchanged": 0, "items_worsened": 1,
                     "net_edits_removed_on_improved_items": 1, "net_edits_introduced_on_worsened_items": 1}


def test_empty_common_set_has_zero_counts_and_null_rate():
    report = {"profiles": {"primary.v1": {}}, "items": []}
    result = _report_deltas(report, report)["profiles"]["primary.v1"]
    assert result["baseline_cer"] is None
    assert result["paired_edit_accounting"]["characters"]["reference_units"] == 0
