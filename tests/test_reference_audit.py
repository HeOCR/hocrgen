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
    HUMAN_CORRECTED_ATTESTATION,
    ReferenceAudit,
    apply_reference_audit,
    apply_text_corrections,
    corrected_footnote_facts,
    load_reference_audit_decisions,
    load_reference_audit_proposals,
    reference_audit_decisions_problems,
    reference_audit_proposals_problems,
    reviewer_id_problems,
    text_sha256,
)
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
    assert decisions["audit_id"] == proposals["audit_id"]
    assert all(d["checked_by"] == "human" for d in decisions["decisions"])
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
    assert summary["pages"] == 38 and summary["undecided_proposals"] == summary["proposals"]
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
