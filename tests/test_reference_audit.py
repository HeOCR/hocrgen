"""E2d4: reference audit proposals and human decisions; only human decisions change a reference (network-free)."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.wikisource import page_plain_text, scored_page_reference
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord
from hocrgen.reference_audit import (
    DECISIONS_SCHEMA,
    HUMAN_CORRECTED_ATTESTATION,
    ReferenceAudit,
    apply_reference_audit,
    apply_text_corrections,
    corrected_footnote_facts,
    load_reference_audit_decisions,
    load_reference_audit_proposals,
    merge_decisions,
    reference_audit_decisions_problems,
    reference_audit_proposals_problems,
    reviewer_id_problems,
    rule_coverage,
    rule_decisions_for,
    text_sha256,
)
from hocrgen.reference_rules import RULE_DECISION_RECORDS, SPACE_BEFORE_PUNCTUATION_RULE
from hocrgen.tools import reference_audit as audit_tool
from hocrgen.tools.wikisource_eval_references import main as eval_refs_main
from hocrgen.tools.wikisource_eval_references import write_eval_reference_set

DOCS = Path(__file__).resolve().parents[1] / "docs"
SNAPSHOT = package_root() / "data" / "wikisource" / "snapshot"
SOURCE = "wikisource_he_proofread"
SELIHOT = f"{SOURCE}:selihot_baer_1885__p0034"


def _selihot() -> dict:
    for line in (SNAPSHOT / "pages.jsonl").read_text(encoding="utf-8").splitlines():
        page = json.loads(line)
        if page["source_item_id"] == "selihot_baer_1885__p0034":
            return page
    raise AssertionError("fixture page missing")


def _proposal(text: str, pid: str, needle: str, proposed: str, *, nth: int = 0, category: str = "punctuation") -> dict:
    start = -1
    for _ in range(nth + 1):
        start = text.index(needle, start + 1)
    end = start + len(needle)
    return {"proposal_id": pid, "item_id": SELIHOT, "start": start, "end": end, "current": needle, "proposed": proposed,
            "context_before": text[max(0, start - 6):start], "context_after": text[end:end + 6],
            "category": category, "confidence": "high", "region": {"coordinate_frame": "page", "box_normalized": [0.1, 0.2, 0.5, 0.3]},
            "note": "the print shows the proposed reading", "status": "agent_proposed", "checked_by": "agent"}


@pytest.fixture()
def selihot_proposals() -> dict:
    text = page_plain_text(_selihot(), SNAPSHOT)
    proposals = [_proposal(text, "p-1", "מוּסָר", "מוּסָר,"), _proposal(text, "p-2", "סְלַח נָא.", "סְלַח נָא:"),
                 _proposal(text, "p-3", "תְּחִנָּה", "תְּחִנָּה[1]", category="missing_text")]
    return {"schema_version": "reference_audit_proposals.v1", "audit_id": "e2d4_test", "checked_by": "agent",
            "checker": "test agent", "proposed_at": "2026-11-07",
            "pages": [{"item_id": SELIHOT, "page_title": _selihot()["page_title"], "reference_text_revision": "latest",
                       "base_revision_id": _selihot()["revision_id"], "base_text_sha256": text_sha256(text),
                       "image_sha256": _selihot()["image"]["sha256"], "audit_status": "audited_with_findings",
                       "proposal_count": 3, "text_not_on_page_candidate": None}],
            "proposals": proposals}


RV1, RV2 = "rv_a1b2c3d4", "rv_0f0e0d0c"


def _decision(pid: str, value: str, reviewer: str = RV1, **extra) -> dict:
    return {"decision_id": f"decision:{pid}:{reviewer}", "proposal_id": pid, "item_id": SELIHOT, "decision": value,
            "reviewer": reviewer, "decided_at": "2026-11-08", "checked_by": "human", **extra}


def _decisions(*decisions: dict) -> dict:
    return {"schema_version": "reference_audit_decisions.v1", "audit_id": "e2d4_test", "decisions": list(decisions)}


def _write(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_committed_proposals_are_agent_proposals_over_the_38_scored_pages() -> None:
    proposals = load_reference_audit_proposals(DOCS / "reference_audit_proposals.json")
    assert proposals["audit_id"] == "e2d4_reference_audit_v1" and proposals["checked_by"] == "agent"
    assert len(proposals["pages"]) == 38
    assert {p["status"] for p in proposals["proposals"]} == {"agent_proposed"}
    assert {p["checked_by"] for p in proposals["proposals"]} == {"agent"}
    no_findings = [p for p in proposals["pages"] if p["audit_status"] == "audited_no_findings"]
    assert no_findings and all(p["proposal_count"] == 0 for p in no_findings)
    assert sum(p["proposal_count"] for p in proposals["pages"]) == len(proposals["proposals"])
    decisions = load_reference_audit_decisions(DOCS / "reference_audit_decisions.json", proposals)
    assert decisions["audit_id"] == proposals["audit_id"] and decisions["schema_version"] == DECISIONS_SCHEMA
    assert {d["checked_by"] for d in decisions["decisions"]} == {"human", "rule"}
    human = [d for d in decisions["decisions"] if d["checked_by"] == "human"]
    rule = [d for d in decisions["decisions"] if d["checked_by"] == "rule"]
    assert all(reviewer_id_problems(d["reviewer"]) == [] for d in human)
    # E2d4b + E2d4c: the maintainer decided 494 proposals (103 spacing, then the full queue), and the rule resolves 13
    # more; never a reviewer on a rule
    assert len(human) == 494 and {d["decision"] for d in human} == {"accepted", "edited", "rejected"}
    assert len(rule) == 13 and all("reviewer" not in d and d["rule"] == SPACE_BEFORE_PUNCTUATION_RULE for d in rule)
    assert {d["decision_record"] for d in rule} == {RULE_DECISION_RECORDS[SPACE_BEFORE_PUNCTUATION_RULE]}
    assert (DOCS.parent / RULE_DECISION_RECORDS[SPACE_BEFORE_PUNCTUATION_RULE]).is_file()
    assert [d["decision_id"] for d in decisions["decisions"]] == sorted(d["decision_id"] for d in decisions["decisions"])
    text = json.dumps(proposals, ensure_ascii=False)
    assert "/Users/" not in text and "intermediates" not in text  # no operator paths, no crops


def test_proposal_validator_rejects_anything_but_a_well_formed_agent_proposal(selihot_proposals: dict) -> None:
    assert reference_audit_proposals_problems(selihot_proposals) == []
    cases = {
        "status must be agent_proposed": ("status", "accepted"),
        "checked_by must be agent": ("checked_by", "human"),
        "category must be one of": ("category", "typo"),
        "confidence must be one of": ("confidence", "certain"),
        "region.box_normalized must be fractions": ("region", {"coordinate_frame": "page", "box_normalized": [0.5, 0.2, 0.1, 0.3]}),
        "proposed must differ": ("proposed", "מוּסָר"),
        "end - start must equal": ("current", "x"),
    }
    for message, (key, value) in cases.items():
        bad = copy.deepcopy(selihot_proposals)
        bad["proposals"][0][key] = value
        assert any(message in problem for problem in reference_audit_proposals_problems(bad)), message
    overlap = copy.deepcopy(selihot_proposals)
    overlap["proposals"][1].update(start=overlap["proposals"][0]["start"], end=overlap["proposals"][0]["end"],
                                   current=overlap["proposals"][0]["current"])
    assert any("overlap" in problem for problem in reference_audit_proposals_problems(overlap))
    count = copy.deepcopy(selihot_proposals)
    count["pages"][0]["proposal_count"] = 2
    assert any("proposal_count" in problem for problem in reference_audit_proposals_problems(count))
    empty = copy.deepcopy(selihot_proposals)
    empty["pages"][0]["audit_status"] = "audited_no_findings"
    assert any("audited_no_findings but has proposals" in problem for problem in reference_audit_proposals_problems(empty))
    assert reference_audit_proposals_problems({"schema_version": "x"}) == ["schema_version must be reference_audit_proposals.v1"]


def test_decision_validator_takes_only_pseudonymous_human_decisions(selihot_proposals: dict) -> None:
    good = _decisions(_decision("p-1", "accepted"), _decision("p-2", "rejected"), _decision("p-3", "edited", text="תְּחִנָּה"))
    assert reference_audit_decisions_problems(good, selihot_proposals)[0].startswith(f"decision decision:p-3:{RV1}: an edit equal")
    good["decisions"][2]["text"] = "תְּחִנָּה:"
    assert reference_audit_decisions_problems(good, selihot_proposals) == []
    for reviewer in ("Shay Palachy", "claude", "reviewer-1", "rv_ABCDEF12", "rv_1234567", "rv_123456789", "", None):
        assert reviewer_id_problems(reviewer), reviewer
    assert reviewer_id_problems(RV1) == [] and reviewer_id_problems(RV2) == []
    cases = [
        (_decision("p-1", "accepted", text="x"), "only an edited decision carries text"),
        (_decision("p-1", "edited"), "needs the reviewer's text"),
        (_decision("p-1", "accepted", checked_by="agent"), "checked_by must be human"),
        (_decision("p-1", "accepted", reviewer="agent"), "pseudonymous id"),
        (_decision("p-1", "accepted", decided_at="2026-13-01"), "decided_at must be"),
        (_decision("p-9", "accepted"), "is not a proposal"),
        (_decision("p-1", "maybe"), "decision must be one of"),
    ]
    for decision, message in cases:
        assert any(message in problem for problem in reference_audit_decisions_problems(_decisions(decision), selihot_proposals)), message
    twice = _decisions(_decision("p-1", "accepted"), {**_decision("p-1", "rejected"), "decision_id": "other"})
    assert any("one per reviewer" in problem for problem in reference_audit_decisions_problems(twice, selihot_proposals))
    two_reviewers = _decisions(_decision("p-1", "accepted"), _decision("p-1", "rejected", RV2))
    assert reference_audit_decisions_problems(two_reviewers, selihot_proposals) == []
    other = {**_decisions(), "audit_id": "another_audit"}
    assert any("audit_id must match" in problem for problem in reference_audit_decisions_problems(other, selihot_proposals))


def test_agent_proposals_alone_change_nothing(selihot_proposals: dict) -> None:
    text = page_plain_text(_selihot(), SNAPSHOT)
    for decisions in (None, _decisions()):
        applied = apply_reference_audit(ReferenceAudit(selihot_proposals, decisions), SELIHOT, text)
        assert applied["text"] == text and applied["provenance"] is None and applied["applied_decisions"] == []
        assert applied["state"] == "audit_pending" and applied["audit_pending"] and applied["pending_proposals"] == ["p-1", "p-2", "p-3"]
    assert apply_reference_audit(None, SELIHOT, text)["state"] == "not_audited"
    rejected = _decisions(*(_decision(pid, "rejected") for pid in ("p-1", "p-2", "p-3")))
    applied = apply_reference_audit(ReferenceAudit(selihot_proposals, rejected), SELIHOT, text)
    assert applied["text"] == text and applied["state"] == "human_reviewed_unchanged" and applied["provenance"] is None


def test_human_decisions_apply_with_provenance_and_stale_input_fails_closed(selihot_proposals: dict) -> None:
    text = page_plain_text(_selihot(), SNAPSHOT)
    decisions = _decisions(_decision("p-2", "edited", text="סְלַח נָא;"), _decision("p-1", "accepted"))
    applied = apply_reference_audit(ReferenceAudit(selihot_proposals, decisions), SELIHOT, text,
                                    base_revision_id=_selihot()["revision_id"])
    expected = text.replace("מוּסָר", "מוּסָר,", 1).replace("סְלַח נָא.", "סְלַח נָא;", 1)
    assert applied["text"] == expected
    assert applied["state"] == "audit_pending" and applied["pending_proposals"] == ["p-3"]  # p-3 undecided: still flagged
    assert applied["provenance"] == {"audit_id": "e2d4_test", "base_revision_id": _selihot()["revision_id"],
                                     "base_text_sha256": text_sha256(text), "min_reviewers": 1,
                                     "applied_decisions": [f"decision:p-1:{RV1}", f"decision:p-2:{RV1}"],  # text order
                                     "text_sha256": text_sha256(expected)}
    audit = ReferenceAudit(selihot_proposals, decisions)
    with pytest.raises(StageExecutionError, match="base_text_sha256 differs"):
        apply_reference_audit(audit, SELIHOT, text + " ")
    with pytest.raises(StageExecutionError, match="audited revision"):
        apply_reference_audit(audit, SELIHOT, text, base_revision_id=1)
    moved = copy.deepcopy(selihot_proposals)
    moved["proposals"][0]["context_before"] = "nope"
    with pytest.raises(StageExecutionError, match="context does not match"):
        apply_reference_audit(ReferenceAudit(moved, decisions), SELIHOT, text)
    assert [entry["reviewer_count"] for entry in applied["applied_decisions"]] == [1, 1]
    assert apply_text_corrections("abcdef", [(4, 4, "X"), (0, 1, "")]) == "bcdXef"
    with pytest.raises(StageExecutionError, match="overlapping"):
        apply_text_corrections("abcdef", [(0, 3, ""), (2, 4, "")])


def test_footnote_facts_follow_marks_a_human_added() -> None:
    facts = {"footnote_marker_style": None, "footnote_count": 0}
    assert corrected_footnote_facts(facts, "a b", "a, b") == facts
    assert corrected_footnote_facts(facts, "a b", "a[1] b[2] c[1]") == {"footnote_marker_style": "bracketed_index", "footnote_count": 2}


def test_eval_references_apply_only_human_decisions(tmp_path: Path, selihot_proposals: dict) -> None:
    base = write_eval_reference_set(SNAPSHOT, tmp_path / "base", reference_manifest_id="e2d4_test")
    proposals = _write(tmp_path, "proposals.json", selihot_proposals)
    pending = write_eval_reference_set(SNAPSHOT, tmp_path / "pending", reference_manifest_id="e2d4_test",
                                       audit_proposals=proposals, audit_decisions=_write(tmp_path, "none.json", _decisions()))
    # agent proposals alone: every reference file and the manifest are byte-identical to a run without the audit
    for name in ("reference_manifest.json", "references/selihot_baer_1885__p0034/transcription.json",
                 "asset_index.json", "single_reviewer_texts.jsonl", "bootstrap_clusters.json"):
        assert (tmp_path / "pending" / name).read_bytes() == (tmp_path / "base" / name).read_bytes(), name
    assert pending["counts"]["audit_pending"] == 1 and pending["counts"]["human_corrected"] == 0
    assert pending["reference_audit"]["states"] == {"audit_pending": 1}
    (entry,) = [item for item in pending["items"] if item["item_id"] == SELIHOT]
    assert entry["reference_audit_state"] == "audit_pending" and entry["audit_pending_proposals"] == 3
    assert entry["human_attestation"] == "two_editor_validated" and "reference_audit_provenance" not in entry
    assert "audit_pending" not in base["counts"] and "reference_audit_state" not in base["items"][0]

    decisions = _write(tmp_path, "decisions.json", _decisions(*(_decision(pid, "accepted") for pid in ("p-1", "p-2", "p-3"))))
    summary = write_eval_reference_set(SNAPSHOT, tmp_path / "fixed", reference_manifest_id="e2d4_test",
                                       audit_proposals=proposals, audit_decisions=decisions)
    assert summary["counts"]["audit_pending"] == 0 and summary["counts"]["human_corrected"] == 1
    (entry,) = [item for item in summary["items"] if item["item_id"] == SELIHOT]
    text = page_plain_text(_selihot(), SNAPSHOT)
    corrected = apply_text_corrections(text, [(p["start"], p["end"], p["proposed"]) for p in selihot_proposals["proposals"]])
    assert entry["human_attestation"] == HUMAN_CORRECTED_ATTESTATION and entry["reference_audit_state"] == "human_corrected"
    assert entry["reference_audit_provenance"]["text_sha256"] == hashlib.sha256(corrected.encode("utf-8")).hexdigest()
    assert entry["reference_normalization"]["footnote_marker_style"] == "bracketed_index"  # p-3 added a [1] mark
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(
        (tmp_path / "fixed/references/selihot_baer_1885__p0034/transcription.json").read_text(encoding="utf-8"))
    assert record.pages[0].text == corrected and record.review.status == "adjudicated"
    assert record.review.reviewers == ["wikisource:Neriah", "wikisource:Nahum", f"heocr:{RV1}"]
    assert f"decision:p-1:{RV1}, decision:p-2:{RV1}, decision:p-3:{RV1}" in record.review.change_reason
    adjudication = json.loads((tmp_path / "fixed/references/selihot_baer_1885__p0034/adjudication.json").read_text("utf-8"))
    assert adjudication["text_sha256"] == entry["reference_audit_provenance"]["text_sha256"]
    assert adjudication["human_attestation"] == HUMAN_CORRECTED_ATTESTATION and adjudication["agent_attestation"] is None
    assert [d["reviewers"] for d in adjudication["reference_audit"]["applied_decisions"]] == [[RV1]] * 3
    assert [d["reviewer_count"] for d in adjudication["reference_audit"]["applied_decisions"]] == [1] * 3
    manifest = json.loads((tmp_path / "fixed/reference_manifest.json").read_text(encoding="utf-8"))
    assert manifest["items"][0]["reference_normalization"] == {"footnote_marker_style": "bracketed_index", "footnote_count": 1}
    with pytest.raises(StageExecutionError, match="needs --audit-proposals"):
        write_eval_reference_set(SNAPSHOT, tmp_path / "x", reference_manifest_id="x", audit_decisions=decisions)
    assert eval_refs_main([str(SNAPSHOT), str(tmp_path / "cli"), "--audit-proposals", str(proposals),
                           "--audit-decisions", str(decisions)]) == 0


def test_scored_page_reference_applies_decisions_only_when_given_an_audit(selihot_proposals: dict) -> None:
    page = _selihot()
    plain = scored_page_reference(page, SNAPSHOT)
    assert "reference_audit" not in plain and "base_text" not in plain
    audit = ReferenceAudit(selihot_proposals, _decisions(_decision("p-1", "accepted")))
    audited = scored_page_reference(page, SNAPSHOT, audit=audit)
    assert audited["base_text"] == plain["text"] and audited["text"] != plain["text"]
    assert audited["reference_audit"]["provenance"]["applied_decisions"] == [f"decision:p-1:{RV1}"]


def test_audit_tool_validates_and_checks_spans_against_a_snapshot(tmp_path: Path, selihot_proposals: dict, capsys) -> None:
    assert audit_tool.main([]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["pages"] == 38 and summary["decisions"] == {"accepted": 416, "edited": 58, "rejected": 20} and summary["reviewers"] == 1
    assert summary["rule_decisions"] == {SPACE_BEFORE_PUNCTUATION_RULE: 13} and summary["human_decided_proposals"] == 494
    assert summary["undecided_proposals"] == summary["proposals"] - 494 - 13
    proposals = _write(tmp_path, "proposals.json", selihot_proposals)
    decisions = _write(tmp_path, "decisions.json", _decisions(_decision("p-1", "rejected")))
    assert audit_tool.main(["--proposals", str(proposals), "--decisions", str(decisions), "--snapshot-root", str(SNAPSHOT)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["decisions"] == {"rejected": 1} and summary["pages_audit_pending"] == 1
    assert summary["spans_checked_against_snapshot"] is True
    stale = copy.deepcopy(selihot_proposals)
    stale["pages"][0]["base_text_sha256"] = "0" * 64
    with pytest.raises(StageExecutionError, match="changed since the audit"):
        audit_tool.main(["--proposals", str(_write(tmp_path, "stale.json", stale)), "--snapshot-root", str(SNAPSHOT)])


def test_several_reviewers_must_agree_and_the_count_is_recorded(selihot_proposals: dict) -> None:
    text = page_plain_text(_selihot(), SNAPSHOT)
    decisions = _decisions(_decision("p-1", "accepted"), _decision("p-1", "accepted", RV2),   # agree
                           _decision("p-2", "accepted"), _decision("p-2", "rejected", RV2),   # disagree
                           _decision("p-3", "edited", text="תְּחִנָּה:"))                   # one reviewer
    one = apply_reference_audit(ReferenceAudit(selihot_proposals, decisions), SELIHOT, text)
    assert [(e["proposal_id"], e["reviewer_count"]) for e in one["applied_decisions"]] == [("p-1", 2), ("p-3", 1)]
    assert one["conflicting_proposals"] == ["p-2"] and one["pending_proposals"] == ["p-2"] and one["audit_pending"]
    assert one["provenance"]["applied_decisions"] == [f"decision:p-1:{RV2}", f"decision:p-1:{RV1}", f"decision:p-3:{RV1}"]
    two = apply_reference_audit(ReferenceAudit(selihot_proposals, decisions, min_reviewers=2), SELIHOT, text)
    assert [e["proposal_id"] for e in two["applied_decisions"]] == ["p-1"]  # p-3 awaits a second reviewer
    assert two["pending_proposals"] == ["p-2", "p-3"] and two["provenance"]["min_reviewers"] == 2
    with pytest.raises(StageExecutionError, match="min_reviewers"):
        ReferenceAudit(selihot_proposals, decisions, min_reviewers=0)


def test_crop_export_bundle_for_a_review_app(tmp_path: Path, selihot_proposals: dict) -> None:
    from PIL import Image

    page = _selihot()
    images = tmp_path / "images"
    images.mkdir()
    (images / f"{page['source_item_id']}.jpg").write_bytes((SNAPSHOT / page["image"]["path"]).read_bytes())
    proposals = _write(tmp_path, "proposals.json", selihot_proposals)
    out = tmp_path / "bundle"
    assert audit_tool.main(["--proposals", str(proposals), "--export-dir", str(out), "--page-images", str(images)]) == 0
    index = json.loads((out / "crops.json").read_text(encoding="utf-8"))
    assert index["schema_version"] == "reference_audit_crops.v1" and index["audit_id"] == "e2d4_test"
    assert (out / "proposals.json").read_bytes() == proposals.read_bytes()
    assert [c["proposal_id"] for c in index["crops"]] == ["p-1", "p-2", "p-3"]
    for crop in index["crops"]:
        data = (out / crop["path"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == crop["sha256"]
        assert Image.open(out / crop["path"]).size == (crop["width"], crop["height"])
        assert crop["source_image_sha256"] == page["image"]["sha256"]
    with pytest.raises(StageExecutionError, match="go together"):
        audit_tool.main(["--proposals", str(proposals), "--export-dir", str(tmp_path / "x")])
    with pytest.raises(StageExecutionError, match="new or empty"):
        audit_tool.main(["--proposals", str(proposals), "--export-dir", str(out), "--page-images", str(images)])
    with pytest.raises(StageExecutionError, match="no page image"):
        audit_tool.main(["--proposals", str(proposals), "--export-dir", str(tmp_path / "y"), "--page-images", str(tmp_path)])


# --- E2d4b: rule decisions and the always-on reference rule ---------------------------------------------------------

RULE = SPACE_BEFORE_PUNCTUATION_RULE
RULE_RECORD = RULE_DECISION_RECORDS[RULE]
RULE_TEXT = "ודונג ,אם בעיר .ובשנת ועוד מלה אחת"
RULE_ITEM = "wikisource_he_proofread:rule_test__p0001"


def _rule_proposals() -> dict:
    """r-1 (' ,' -> ', ') is what the rule does; r-2 (' .' -> ', ', the print has a comma) and r-3 are not."""

    def one(pid: str, needle: str, proposed: str, category: str = "spacing") -> dict:
        start = RULE_TEXT.index(needle)
        end = start + len(needle)
        return {"proposal_id": pid, "item_id": RULE_ITEM, "start": start, "end": end, "current": needle,
                "proposed": proposed, "context_before": RULE_TEXT[max(0, start - 4):start],
                "context_after": RULE_TEXT[end:end + 4], "category": category, "confidence": "high",
                "region": {"coordinate_frame": "page", "box_normalized": [0.1, 0.2, 0.5, 0.3]}, "note": "n",
                "status": "agent_proposed", "checked_by": "agent"}

    proposals = [one("r-1", " ,", ", "), one("r-2", " .", ", ", "punctuation"), one("r-3", "מלה", "מילה", "letter_confusion")]
    return {"schema_version": "reference_audit_proposals.v1", "audit_id": "e2d4_test", "checked_by": "agent",
            "checker": "test agent", "proposed_at": "2026-11-07",
            "pages": [{"item_id": RULE_ITEM, "page_title": "t", "reference_text_revision": "latest", "base_revision_id": 1,
                       "base_text_sha256": text_sha256(RULE_TEXT), "image_sha256": "0" * 64,
                       "audit_status": "audited_with_findings", "proposal_count": 3, "text_not_on_page_candidate": None}],
            "proposals": proposals}


def _rule_decision(pid: str, item_id: str = RULE_ITEM, **extra) -> dict:
    return {**rule_decisions_for([{"proposal_id": pid, "item_id": item_id}], RULE, "2026-11-07")[0], **extra}


def _v2(*decisions: dict) -> dict:
    return {**_decisions(*decisions), "schema_version": DECISIONS_SCHEMA}


def test_rule_decisions_are_v2_deterministic_and_never_human_review() -> None:
    proposals = _rule_proposals()
    good = _rule_decision("r-1")
    assert good == {"decision_id": f"rule:{RULE}:r-1", "proposal_id": "r-1", "item_id": RULE_ITEM, "decision": "accepted",
                    "checked_by": "rule", "rule": RULE, "decision_record": RULE_RECORD, "decided_at": "2026-11-07"}
    assert reference_audit_decisions_problems(_v2(good), proposals) == []
    assert reference_audit_decisions_problems(_v2(good, {**_decision("r-2", "rejected"), "item_id": RULE_ITEM}), proposals) == []
    assert any("rule decisions need reference_audit_decisions.v2" in problem
               for problem in reference_audit_decisions_problems(_decisions(good), proposals))  # v1 is human-only
    cases = [
        ({**good, "rule": "nope.v1"}, "rule must be one of"),
        ({**good, "decision_record": "planning/decisions/other.md"}, "decision_record must be"),
        ({**good, "decision_id": "rule:r-1"}, "rule:<rule>:<proposal_id>"),
        ({**good, "decision": "rejected"}, "can only be accepted"),
        ({**good, "reviewer": RV1}, "names no reviewer"),
        ({**good, "checked_by": "agent"}, "checked_by must be human or rule"),
    ]
    for decision, message in cases:
        assert any(message in problem for problem in reference_audit_decisions_problems(_v2(decision), proposals)), message
    both = _v2(good, {**_decision("r-1", "accepted"), "item_id": RULE_ITEM})
    assert any("decided by a human and by a rule" in problem for problem in reference_audit_decisions_problems(both, proposals))
    assert any("one per reviewer" in problem for problem in reference_audit_decisions_problems(
        _v2(good, {**good, "decision_id": "x"}), proposals))


def test_a_rule_decision_applies_counts_as_decided_and_stays_apart_from_human_review() -> None:
    proposals = _rule_proposals()
    human = lambda pid, value: {**_decision(pid, value), "item_id": RULE_ITEM}  # noqa: E731
    only_rule = apply_reference_audit(ReferenceAudit(proposals, _v2(_rule_decision("r-1"))), RULE_ITEM, RULE_TEXT)
    assert only_rule["text"] == RULE_TEXT.replace(" ,", ", ", 1)
    assert only_rule["state"] == "audit_pending" and only_rule["pending_proposals"] == ["r-2", "r-3"]
    assert only_rule["applied_decisions"] == [] and [e["proposal_id"] for e in only_rule["rule_decisions"]] == ["r-1"]
    assert only_rule["rule_decisions"][0]["reviewer_count"] == 0 and only_rule["rule_decisions"][0]["checked_by"] == "rule"
    assert only_rule["provenance"]["applied_decisions"] == []
    assert only_rule["provenance"]["applied_rule_decisions"] == [f"rule:{RULE}:r-1"]

    rule_and_rejections = _v2(_rule_decision("r-1"), human("r-2", "rejected"), human("r-3", "rejected"))
    applied = apply_reference_audit(ReferenceAudit(proposals, rule_and_rejections), RULE_ITEM, RULE_TEXT)
    assert applied["state"] == "rule_corrected" and not applied["audit_pending"]  # not human_corrected
    # human-decided spans, in the corrected text: the rule leaves them as the human left them
    assert [applied["text"][a:b] for a, b in applied["human_decided_spans"]] == [" .", "מלה"]

    both = _v2(_rule_decision("r-1"), human("r-2", "rejected"), human("r-3", "accepted"))
    applied = apply_reference_audit(ReferenceAudit(proposals, both, min_reviewers=2), RULE_ITEM, RULE_TEXT)
    assert applied["state"] == "audit_pending" and applied["pending_proposals"] == ["r-2", "r-3"]  # humans only
    assert [e["proposal_id"] for e in applied["rule_decisions"]] == ["r-1"]  # min_reviewers does not hold a rule back
    applied = apply_reference_audit(ReferenceAudit(proposals, both), RULE_ITEM, RULE_TEXT)
    assert applied["state"] == "human_and_rule_corrected"
    assert applied["text"] == "ודונג, אם בעיר .ובשנת ועוד מילה אחת"
    assert [a["reviewers"] for a in applied["applied_decisions"]] == [[RV1]]
    assert [applied["text"][a:b] for a, b in applied["human_decided_spans"]] == [" .", "מילה"]
    # a rule decision the rule does not make on this text fails closed
    with pytest.raises(StageExecutionError, match="does not make the proposed change"):
        apply_reference_audit(ReferenceAudit(proposals, _v2(_rule_decision("r-2"))), RULE_ITEM, RULE_TEXT)


def test_rule_coverage_lists_only_undecided_proposals_the_rule_makes() -> None:
    proposals = _rule_proposals()
    covered = rule_coverage(ReferenceAudit(proposals), {RULE_ITEM: RULE_TEXT})
    assert [p["proposal_id"] for p in covered[RULE]] == ["r-1"]
    decided = ReferenceAudit(proposals, _decisions({**_decision("r-1", "rejected"), "item_id": RULE_ITEM}))
    assert rule_coverage(decided, {RULE_ITEM: RULE_TEXT}) == {RULE: []}
    with pytest.raises(StageExecutionError, match="not the one"):
        rule_coverage(ReferenceAudit(proposals), {RULE_ITEM: RULE_TEXT + " "})


def test_merging_a_review_app_export_is_validated_and_idempotent() -> None:
    proposals = _rule_proposals()
    base = _v2(_rule_decision("r-1"))
    export = _decisions({**_decision("r-2", "rejected"), "item_id": RULE_ITEM})
    merged = merge_decisions(base, export, proposals)
    assert merged["schema_version"] == DECISIONS_SCHEMA
    assert [d["decision_id"] for d in merged["decisions"]] == [f"decision:r-2:{RV1}", f"rule:{RULE}:r-1"]
    assert merge_decisions(merged, export, proposals) == merged
    changed = _decisions({**_decision("r-2", "accepted"), "item_id": RULE_ITEM})
    with pytest.raises(StageExecutionError, match="different content"):
        merge_decisions(merged, changed, proposals)
    with pytest.raises(StageExecutionError, match="decided by a human and by a rule"):
        merge_decisions(base, _decisions({**_decision("r-1", "accepted"), "item_id": RULE_ITEM}), proposals)
    with pytest.raises(StageExecutionError, match="another audit_id"):
        merge_decisions(base, {**export, "audit_id": "other"}, proposals)


def test_audit_tool_merges_exports_and_writes_rule_decisions(tmp_path: Path, selihot_proposals: dict, capsys) -> None:
    proposals = _write(tmp_path, "proposals.json", selihot_proposals)
    decisions = _write(tmp_path, "decisions.json", _decisions())
    export = _write(tmp_path, "export.json", _decisions(_decision("p-1", "accepted")))
    assert audit_tool.main(["--proposals", str(proposals), "--decisions", str(decisions), "--add-decisions", str(export)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["decisions_added"] == 1 and summary["human_decided_proposals"] == 1 and summary["undecided_proposals"] == 2
    written = json.loads(decisions.read_text(encoding="utf-8"))
    assert written["schema_version"] == DECISIONS_SCHEMA and len(written["decisions"]) == 1
    assert audit_tool.main(["--proposals", str(proposals), "--decisions", str(decisions), "--rule-coverage",
                            "--write-rule-decisions", "--snapshot-root", str(SNAPSHOT)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["rule_coverage"] == {RULE: {"proposals": 0, "proposal_ids": [], "by_category": {}}}  # nothing to fix
    assert summary["rule_decisions_written"] == 0
    with pytest.raises(StageExecutionError, match="needs --snapshot-root"):
        audit_tool.main(["--proposals", str(proposals), "--rule-coverage"])
    with pytest.raises(StageExecutionError, match="needs --rule-coverage"):
        audit_tool.main(["--proposals", str(proposals), "--write-rule-decisions"])
    with pytest.raises(StageExecutionError, match="needs --decisions"):
        audit_tool.main(["--proposals", str(proposals), "--add-decisions", str(export)])


def test_the_app_bundle_skips_proposals_a_human_or_the_rule_decided(tmp_path: Path, selihot_proposals: dict) -> None:
    page = _selihot()
    images = tmp_path / "images"
    images.mkdir()
    (images / f"{page['source_item_id']}.jpg").write_bytes((SNAPSHOT / page["image"]["path"]).read_bytes())
    proposals = _write(tmp_path, "proposals.json", selihot_proposals)
    decisions = _write(tmp_path, "decisions.json", _v2(_decision("p-1", "rejected"), _rule_decision("p-2", SELIHOT)))
    out = tmp_path / "bundle"
    assert audit_tool.main(["--proposals", str(proposals), "--decisions", str(decisions), "--export-dir", str(out),
                            "--page-images", str(images)]) == 0
    index = json.loads((out / "crops.json").read_text(encoding="utf-8"))
    assert [c["proposal_id"] for c in index["crops"]] == ["p-3"] and index["skipped_decided"] == {"human": 1, "rule": 1}
    bundled = load_reference_audit_proposals(out / "proposals.json")
    assert [p["proposal_id"] for p in bundled["proposals"]] == ["p-3"] and bundled["pages"][0]["proposal_count"] == 1
    assert index["source_proposals_sha256"] == hashlib.sha256(proposals.read_bytes()).hexdigest()


def _snapshot_with_stray_spaces(tmp_path: Path) -> tuple[Path, dict[str, tuple[str, str]]]:
    """A copy of the packaged snapshot with a stray space before a mark on the Selihot page (quality 4) and on the
    Toldoth page (quality 3), every pin recomputed; returns the root and item -> (edited text, original text)."""
    import shutil

    from hocrgen.fetchers.wikisource import derive_page_text, page_transclusions

    root = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT, root)
    edits = {"selihot_baer_1885__p0034": ("לָמוֹ. וְעֵינֵיהֶם", "לָמוֹ .וְעֵינֵיהֶם"),
             "hyman_toldoth_1910_vol1__p0041": ("בשבת, אך", "בשבת ,אך")}
    pages = [json.loads(line) for line in (root / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    texts = {}
    for page in pages:
        if page["source_item_id"] not in edits:
            continue
        original = page_plain_text(page, root)
        old, new = edits[page["source_item_id"]]
        path = root / page["wikitext_path"]
        wikitext = path.read_text(encoding="utf-8")
        assert wikitext.count(old) == 1
        wikitext = wikitext.replace(old, new)
        path.write_text(wikitext, encoding="utf-8")
        derived = derive_page_text(wikitext, page_transclusions(page, root), page)
        page["wikitext_sha256"] = hashlib.sha256(wikitext.encode("utf-8")).hexdigest()
        page["text_sha256"] = text_sha256(derived.text)
        page["text_adjustments"] = derived.adjustments
        if page.get("quality_set_text_sha256"):
            page["quality_set_text_sha256"] = (derived.adjustments or {}).get("converted_text_sha256") or page["text_sha256"]
        (root / page["text_path"]).write_text(derived.text + "\n", encoding="utf-8")
        texts[f"{SOURCE}:{page['source_item_id']}"] = (derived.text, original)
    (root / "pages.jsonl").write_text("".join(json.dumps(page, ensure_ascii=False) + "\n" for page in pages), encoding="utf-8")
    return root, texts


def test_eval_references_apply_the_rule_on_both_strata_after_the_audit(tmp_path: Path) -> None:
    root, texts = _snapshot_with_stray_spaces(tmp_path)
    hyman = f"{SOURCE}:hyman_toldoth_1910_vol1__p0041"
    selihot_text, selihot_original = texts[SELIHOT]
    summary = write_eval_reference_set(root, tmp_path / "rules", reference_manifest_id="e2d4b_test")
    assert summary["counts"]["reference_rule_fixes"] == {"adjudicated": 1, "single_reviewer": 1}
    assert summary["reference_rules"]["rules"] == [RULE] and summary["reference_rules"]["items_changed"] == 2
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(
        (tmp_path / "rules/references/selihot_baer_1885__p0034/transcription.json").read_text(encoding="utf-8"))
    assert record.pages[0].text == selihot_original  # the rule restores what the print has
    assert record.review.reviewers == ["wikisource:Neriah", "wikisource:Nahum"]  # a rule adds no reviewer
    assert "mechanical reference rules" in record.review.change_reason
    adjudication = json.loads((tmp_path / "rules/references/selihot_baer_1885__p0034/adjudication.json").read_text("utf-8"))
    assert adjudication["reference_rules"]["applied"] == [{"rule": RULE, "fixes": 1}]
    assert adjudication["reference_rules"]["decision_records"] == [RULE_RECORD]
    assert adjudication["reference_rules"]["text_sha256_before"] == text_sha256(selihot_text)
    assert adjudication["text_sha256"] == text_sha256(selihot_original)
    (entry,) = [item for item in summary["items"] if item["item_id"] == SELIHOT]
    assert entry["reference_rules_applied"] == [{"rule": RULE, "fixes": 1}]
    lines = {json.loads(line)["item_id"]: json.loads(line)
             for line in (tmp_path / "rules/single_reviewer_texts.jsonl").read_text("utf-8").splitlines()}
    assert lines[hyman]["text"] == texts[hyman][1] and lines[hyman]["reference_rules_applied"] == [{"rule": RULE, "fixes": 1}]
    off = write_eval_reference_set(root, tmp_path / "off", reference_manifest_id="e2d4b_test", reference_rules=())
    assert "reference_rule_fixes" not in off["counts"] and "reference_rules" not in off
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(
        (tmp_path / "off/references/selihot_baer_1885__p0034/transcription.json").read_text(encoding="utf-8"))
    assert record.pages[0].text == selihot_text
    assert eval_refs_main([str(root), str(tmp_path / "cli"), "--no-reference-rules"]) == 0

    # The audit: proposal offsets are on the unnormalized text; the audit applies first, then the rule.
    page = next(json.loads(line) for line in (root / "pages.jsonl").read_text(encoding="utf-8").splitlines()
                if json.loads(line)["source_item_id"] == "selihot_baer_1885__p0034")
    payload = {"schema_version": "reference_audit_proposals.v1", "audit_id": "e2d4_test", "checked_by": "agent",
               "checker": "test agent", "proposed_at": "2026-11-07",
               "pages": [{"item_id": SELIHOT, "page_title": page["page_title"], "reference_text_revision": "latest",
                          "base_revision_id": page["revision_id"], "base_text_sha256": text_sha256(selihot_text),
                          "image_sha256": page["image"]["sha256"], "audit_status": "audited_with_findings",
                          "proposal_count": 2, "text_not_on_page_candidate": None}],
               "proposals": [_proposal(selihot_text, "s-1", " .", ". ", category="spacing"),
                             _proposal(selihot_text, "p-1", "מוּסָר", "מוּסָר,")]}
    proposals = _write(tmp_path, "rule_proposals.json", payload)

    def build(name: str, decisions: dict) -> tuple[dict, dict, str]:
        out = write_eval_reference_set(root, tmp_path / name, reference_manifest_id="e2d4b_test", audit_proposals=proposals,
                                       audit_decisions=_write(tmp_path, f"{name}.json", decisions), include={SELIHOT})
        (item,) = out["items"]
        text = BenchmarkTranscriptionReferenceRecord.model_validate_json(
            (tmp_path / name / "references/selihot_baer_1885__p0034/transcription.json").read_text("utf-8")).pages[0].text
        return out, item, text

    # a rule decision on s-1 and a human accept on p-1: both decided, but only p-1 is human review
    out, item, text = build("ruled", _v2(_rule_decision("s-1", SELIHOT), _decision("p-1", "accepted")))
    assert item["reference_audit_state"] == "human_and_rule_corrected" and not item["audit_pending"]
    assert item["audit_rule_decided_proposals"] == 1 and item["human_attestation"] == HUMAN_CORRECTED_ATTESTATION
    assert item["reference_rules_applied"] == [{"rule": RULE, "fixes": 0}]  # the rule decision already fixed it
    assert text == selihot_original.replace("מוּסָר", "מוּסָר,", 1)
    assert out["counts"]["human_corrected"] == 1 and out["counts"]["audit_rule_decided_proposals"] == 1
    # only the rule decision: decided, corrected, but not human-corrected and no heocr reviewer
    out, item, text = build("rule_only", _v2(_rule_decision("s-1", SELIHOT), _decision("p-1", "rejected")))
    assert item["reference_audit_state"] == "rule_corrected" and item["human_attestation"] == "two_editor_validated"
    assert out["counts"]["human_corrected"] == 0 and text == selihot_original
    assert item["reference_audit_provenance"]["applied_rule_decisions"] == [f"rule:{RULE}:s-1"]
    adjudication = json.loads((tmp_path / "rule_only/references/selihot_baer_1885__p0034/adjudication.json").read_text("utf-8"))
    assert adjudication["reference_audit"]["rule_decisions"][0]["rule"] == RULE
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(
        (tmp_path / "rule_only/references/selihot_baer_1885__p0034/transcription.json").read_text("utf-8"))
    assert record.review.reviewers == ["wikisource:Neriah", "wikisource:Nahum"]  # no heocr: reviewer for a rule
    assert "rule decisions (not human review)" in record.review.change_reason
    # a human rejection of the very fix: the always-on rule leaves the span as the human left it
    out, item, text = build("rejected", _decisions(_decision("s-1", "rejected"), _decision("p-1", "rejected")))
    assert item["reference_audit_state"] == "human_reviewed_unchanged" and text == selihot_text
    assert item["reference_rules_applied"] == [{"rule": RULE, "fixes": 0, "skipped_protected": 1}]
    # undecided: the rule still fixes it, and the proposal stays pending
    out, item, text = build("pending", _decisions())
    assert item["reference_audit_state"] == "audit_pending" and text == selihot_original
    assert item["reference_rules_applied"] == [{"rule": RULE, "fixes": 1}]


def test_the_rule_keeps_excluded_spans_on_their_words(tmp_path: Path) -> None:
    from hocrgen.reference_evaluation import reference_text

    root, texts = _snapshot_with_stray_spaces(tmp_path)
    text = texts[SELIHOT][0]
    lines = (root / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    pages = [json.loads(line) for line in lines]
    word = "תְּחִנָּה"
    for page in pages:
        if f"{SOURCE}:{page['source_item_id']}" == SELIHOT:
            start = text.index(word)
            page["excluded_spans"] = {"text_sha256": page["text_sha256"], "spans": [{
                "kind": "illegible_on_scan", "start": start, "end": start + len(word),
                "regions_normalized": [[0.2, 0.3, 0.6, 0.35]], "detail": "an ink blot covers the word",
                "checked_by": "agent", "checker": "a", "checked_at": "2026-11-06"}]}
    (root / "pages.jsonl").write_text("".join(json.dumps(page, ensure_ascii=False) + "\n" for page in pages), encoding="utf-8")
    summary = write_eval_reference_set(root, tmp_path / "set", reference_manifest_id="e2d4b_test", include={SELIHOT})
    assert summary["counts"]["reference_rule_fixes"]["adjudicated"] == 1
    record = BenchmarkTranscriptionReferenceRecord.model_validate_json(
        (tmp_path / "set/references/selihot_baer_1885__p0034/transcription.json").read_text(encoding="utf-8"))
    (span,) = record.spans
    line = next(line for line in record.lines if line.line_id == span.line_id)
    assert line.text[span.start:span.end] == word  # moved with the fix before it
    assert reference_text(record).count(word) == text.count(word) - 1  # and still excluded from scoring
