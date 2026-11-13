"""Mid-century page review -> reference sets -> evaluate-references, end to end (invented fixture only)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.cli import main as hocrgen_main
from hocrgen.tools import midcentury_review as mr

REV = mr.SYNTHETIC_REVIEWER
U = "reshumot_scanned:kovetz_hatakanot_9"   # invented unit ids
P = "plenary:K1_1"


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _page(unit, page, prefill, *, role="test", stratum="kovetz_hatakanot|1948-59", series="kovetz_hatakanot", blind=False):
    return {"unit_id": unit, "page": page, "image_sha256": _h(f"img {unit} {page}"), "prefill": prefill,
            "prefill_source": "publisher text layer", "role": role, "stratum": stratum, "series": series,
            "node": "printed/new_printed", "blind_second_pass": blind, "reading_order_check": series == "plenary"}


PAGES = [
    _page(U, 1, "חוק הדוגמה\nסעיף אחד ושתיים\nסעיף שלש", blind=True),
    _page(U, 2, "עמוד פגום"),
    _page(U, 3, "עמוד מילואים\nשורה נוספת", role="reserve"),
    _page(U, 4, "שכבה כפולה\nשכבה כפולה"),
    _page(P, 2, "דברי הכנסת\nהיושב ראש", stratum="plenary|K1-3", series="plenary"),
]
BLIND_PREFILL = "חוק הדוגמא\nסעיף אחד ושתים\nסעיף שלש"


def _manifest():
    return {"schema": "heocr_midcentury_batch.v0", "manifest_version": "v1", "pages": PAGES}


def _blind(manifest):
    p = PAGES[0]
    return {"batch_id": mr.BATCH_ID, "manifest_sha256": _h(json.dumps(manifest)),
            "pages": [{"unit_id": p["unit_id"], "page": p["page"], "image_sha256": p["image_sha256"],
                       "blind_prefill": BLIND_PREFILL, "blind_prefill_source": "stock Tesseract heb"}]}


def _line(i_src, action, text):
    return {"i_src": i_src, "action": action, "text": text,
            "reference_views": ["consonantal"] if action == "print_has_niqqud" else ["primary", "consonantal"]}


def _rec(page, pass_no, action, lines, at, *, prefill=None, hints=True, reason=None):
    key = mr.page_key(page["unit_id"], page["page"])
    r = {"decision_id": f"decision:{key}{'@pass2' if pass_no == 2 else ''}:{REV}", "batch_id": mr.BATCH_ID,
         "unit_id": page["unit_id"], "page": page["page"], "image_sha256": page["image_sha256"],
         "prefill_source": page["prefill_source"] if pass_no == 1 else "stock Tesseract heb",
         "prefill_sha256": _h(prefill if prefill is not None else page["prefill"]), "reviewer": REV, "pass": pass_no,
         "blind_second_pass": page["blind_second_pass"] or pass_no == 2, "page_action": action,
         "reading_order_verified": True if action == "confirm" else None, "lines": lines,
         "ai_flagged_i": ([0] if hints else None) if pass_no == 1 else None, "ai_missing_near_i": None,
         "decided_at": at, "first_decided_at": at, "checked_by": "human"}
    if reason:
        r["reject_reason"] = reason
    return r


def _decisions():
    a, b, c, d, e = PAGES
    return {"schema_version": mr.DECISIONS_SCHEMA, "batch_id": mr.BATCH_ID, "synthetic": True, "decisions": [
        _rec(a, 1, "confirm", [_line([0], "correct", "חוק הדוגמה"), _line([1], "edit", "סעיף אחד ושנים"),
                                _line([2], "correct", "סעיף שלש"), _line([], "added", "הערת שוליים")],
             "2026-11-13T08:00:00Z"),
        _rec(b, 1, "reject", [], "2026-11-13T08:05:00Z", reason="misfetched"),
        _rec(c, 1, "confirm", [_line([0], "print_has_niqqud", "עמוד מילואים"), _line([1], "correct", "שורה נוספת")],
             "2026-11-13T08:10:00Z", hints=False),
        _rec(d, 1, "confirm", [_line([0], "correct", "שכבה כפולה"), _line([1], "not_on_page", None)],
             "2026-11-13T08:15:00Z"),
        _rec(e, 1, "confirm", [_line([0, 1], "merge", "דברי הכנסת היושב ראש")], "2026-11-13T08:20:00Z"),
        _rec(a, 2, "confirm", [_line([0], "edit", "חוק הדוגמה"), _line([1], "edit", "סעיף אחד ושנים"),
                                _line([2], "correct", "סעיף שלש"), _line([], "added", "הערת שוליים.")],
             "2026-11-14T09:00:00Z", prefill=BLIND_PREFILL),
    ]}


KNOWN = {(U, 4): "fixture: layer twice"}


def _build(tmp_path, decisions=None):
    m = _manifest()
    return mr.build(decisions or _decisions(), m, _blind(m), tmp_path / "sets", synthetic_fixture=True, known_bad=KNOWN)


def test_build_sets_and_summary(tmp_path):
    s = _build(tmp_path)
    assert s["counts"]["pass1_scored"] == 3 and s["counts"]["pass2_scored"] == 1
    reasons = {x["page"]: x["reason"] for x in s["excluded"]}
    assert reasons[f"{U}#p2"].startswith("rejected") and reasons[f"{U}#p4"].startswith("known bad")
    assert s["quota"]["kovetz_hatakanot|1948-59"] == {"quota": 3, "scored": 2, "short": 1}
    err = s["reference_error"]
    assert err["all"]["pages"] == 1 and err["all"]["edits"] == 1 and err["hints_shown"]["pages"] == 1
    labels = json.loads((tmp_path / "sets/pass1/eval_labels.json").read_text())["labels"]
    assert labels[f"midcentury:{U}#p3"]["niqqud"] == "pointed"
    assert labels[f"midcentury:{P}#p2"]["facets"]["genre"] == "parliamentary"
    ref = json.loads((tmp_path / f"sets/pass1/references/{mr.safe(U + '#p1')}/transcription.json").read_text())
    assert [ln["text"] for ln in ref["lines"]][-1] == "הערת שוליים"


def test_page_without_reference_lines_is_excluded(tmp_path):
    d = _decisions()
    d["decisions"][3]["lines"] = [_line([0], "not_on_page", None), _line([1], "not_on_page", None)]
    s = mr.build(d, _manifest(), _blind(_manifest()), tmp_path / "sets", synthetic_fixture=True, known_bad={})
    assert {x["page"]: x["reason"] for x in s["excluded"]}[f"{U}#p4"] == "confirmed with no reference lines"


def test_refuses_synthetic_without_flag_and_bad_exports(tmp_path):
    m = _manifest()
    with pytest.raises(SystemExit, match="synthetic"):
        mr.build(_decisions(), m, _blind(m), tmp_path / "x", known_bad=KNOWN)
    bad = _decisions()
    bad["decisions"][-1]["decided_at"] = "2026-11-13T09:00:00Z"
    errors, _ = mr.check(bad["decisions"], m, _blind(m))
    assert any("24 h" in e for e in errors)
    bad = _decisions()
    bad["decisions"][0]["checked_by"] = "agent"
    bad["decisions"][0]["lines"] = bad["decisions"][0]["lines"][1:]
    errors, _ = mr.check(bad["decisions"], m, _blind(m))
    assert any("checked_by" in e for e in errors) and any("coverage" in e for e in errors)


def _predictions(d: Path, texts: dict[str, str]):
    d.mkdir(parents=True)
    for sha, text in texts.items():
        (d / f"{sha}.json").write_text(json.dumps(mr._prediction(sha, text, name="fixture", version="1", track="open",
                                                                 network=False), ensure_ascii=False))


def _evaluate(set_dir: Path, preds: Path, out: Path, *extra: str):
    rc = hocrgen_main(["evaluate-references", "--predictions", str(preds), "--reference-manifest",
                       str(set_dir / "reference_manifest.json"), "--asset-index", str(set_dir / "asset_index.json"),
                       "--eval-labels", str(set_dir / "eval_labels.json"), "--bootstrap-clusters",
                       str(set_dir / "clusters.json"), "--bootstrap-resamples", "200", "--profile", "primary.v1",
                       "--profile", "consonantal.v1", "--output", str(out), *extra])
    assert rc == 0
    return json.loads(out.read_text())


def test_end_to_end_evaluate_references(tmp_path):
    _build(tmp_path)
    sets = tmp_path / "sets"
    a, _, c, _, e = PAGES
    _predictions(tmp_path / "engine", {a["image_sha256"]: "חוק הדוגמה\nסעיף אחד ושנים\nסעיף שלש",
                                       c["image_sha256"]: "עמוד מילואים\nשורה נוספת",
                                       e["image_sha256"]: "דברי הכנסת היושב ראש"})
    _predictions(tmp_path / "base", {a["image_sha256"]: "חוק\nסעיף", c["image_sha256"]: "עמוד", e["image_sha256"]: "דברי"})
    r = _evaluate(sets / "pass1", tmp_path / "engine", tmp_path / "r.json", "--baseline-predictions", str(tmp_path / "base"))
    head = _headline(r)
    assert head["items"] == 2 and head["clusters"] == 2   # the pointed reserve page is outside the vertical's headline
    prof = head["profiles"]["primary.v1"]
    assert prof["line_aligned"]["reference_lines"] == 5 and prof["line_aligned"]["missed_lines"] == 1
    assert "too_few_clusters" in prof["interval_flags"]
    deltas = r["comparison"]["reference_view_deltas"]["adjudicated_reference"]["line_matched.v1"]["line_matched.v1"]
    assert "delta_cer_ci" in deltas["eval_slices"]["slices"]["printed/new_printed"]["ALL"]["excluding_pointed"][
        "profiles"]["primary.v1"]
    # reference error: pass-1 references read as predictions against the blind pass-2 references
    r2 = _evaluate(sets / "pass2", sets / "pass1_on_pass2", tmp_path / "r2.json")
    assert _headline(r2)["profiles"]["primary.v1"]["character_edits"] == 1


def _headline(report):
    view = report["reference_views"]["adjudicated_reference"]["line_matched.v1"]["views"]["line_matched.v1"]
    return view["eval_slices"]["slices"]["printed/new_printed"]["ALL"]["excluding_pointed"]


def test_claude_predictions_subset_and_coincidence(tmp_path):
    _build(tmp_path)
    m = _manifest()
    rd = tmp_path / "ai_readings"
    key_a, key_c = mr.page_key(U, 1), mr.page_key(U, 3)
    (rd / "pages_v1").mkdir(parents=True)
    (rd / "pages").mkdir()
    (rd / "batches").mkdir()
    (rd / "batches_v1").mkdir()
    # page a: reads line 1 with the pre-fill's own error (seeding-like); short line 0 left unread; a missing note
    (rd / "pages_v1" / f"{mr.safe(key_a)}.json").write_text(json.dumps({"key": key_a, "reader": "fixture reader", "lines": [
        {"i": 1, "text": "סעיף אחד ושתיים"}, {"i": 2, "text": "סעיף שלש"}], "missing": [{"near_i": 2, "text": "הערת שוליים"}],
        "uncertain_i": []}, ensure_ascii=False))
    (rd / "pages" / f"{mr.safe(key_c)}.json").write_text(json.dumps({"key": key_c, "reader": "fixture reader", "lines": [
        {"i": 0, "text": "עמוד מילואים"}, {"i": 1, "text": "שורה נוספת"}], "missing": []}, ensure_ascii=False))
    (rd / "batches_v1" / "batch_v1_00.json").write_text(json.dumps([{"key": key_a}]))
    (rd / "batches" / "batch_00.json").write_text(json.dumps([{"key": key_c}]))
    rep = mr.claude_predictions(rd, m, m, tmp_path / "claude")
    assert rep["pages_with_reading"] == 2
    only = json.loads((tmp_path / "claude/claude_only" / f"{mr.safe(key_a)}.json").read_text())
    filled = json.loads((tmp_path / "claude/with_prefill_short" / f"{mr.safe(key_a)}.json").read_text())
    assert only["text"] == "סעיף אחד ושתיים\nסעיף שלש\nהערת שוליים"
    assert filled["text"].startswith("חוק הדוגמה\n") and only["track"] == "proprietary"
    n = mr.subset(tmp_path / "sets/pass1", tmp_path / "claude/items.txt", tmp_path / "sets/pass1_claude")
    assert n == 2
    r = _evaluate(tmp_path / "sets/pass1_claude", tmp_path / "claude/claude_only", tmp_path / "rc.json")
    assert _headline(r)["items"] == 1 and r["track"] == "proprietary"
    co = mr.coincidence(_decisions(), m, _blind(m), rd, m)
    assert co["batches"]["batch_v1_00"]["prefill_wrong_lines"] == 1
    assert co["batches"]["batch_v1_00"]["share_equals_wrong_prefill"] == 1.0
