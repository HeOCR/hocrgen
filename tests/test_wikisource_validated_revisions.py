"""E2d3b / E2d3c: score a quality-4 page changed after validation on its validating-revision text (network-free)."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.wikisource import (
    derive_validated_page_text,
    layout_only_difference,
    load_validated_text_checks,
    page_plain_text,
    validated_revision_attestation,
    validated_text_check_problems,
)
from hocrgen.parsers.wikitext import convert_wikitext
from hocrgen.reference_runs import load_adjudicated_references
from hocrgen.tools import wikisource_inventory as inv
from hocrgen.tools import wikisource_validated_revisions as wvr
from hocrgen.tools.wikisource_eval_references import main as eval_refs_main
from hocrgen.tools.wikisource_eval_references import write_eval_reference_set

SNAPSHOT = package_root() / "data" / "wikisource" / "snapshot"
SOURCE = "wikisource_he_proofread"
BOSTENAY = "bostenay_lehmann_1872__p0047"
SELIHOT = "selihot_baer_1885__p0034"
COMMITTED_CHECKS = Path(__file__).resolve().parents[1] / "docs" / "wikisource_validated_text_checks.json"
COMMITTED_PAGE_CHECKS = Path(__file__).resolve().parents[1] / "docs" / "wikisource_page_checks.json"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _snapshot(tmp_path: Path, edit: str = "letter") -> tuple[Path, dict, str]:
    """A copy of the packaged snapshot whose Bostenay page records a validating-revision text apart from the latest.

    ``edit`` is ``letter`` (one word one letter longer), ``paragraph`` (a space between two words is a paragraph
    break) or ``joined`` (that space dropped, two words run together). Returns the root, the page and the validating
    revision's wikitext.
    """
    root = tmp_path / "snapshot"
    shutil.copytree(SNAPSHOT, root)
    pages = [json.loads(line) for line in (root / "pages.jsonl").read_text(encoding="utf-8").splitlines()]
    page = next(p for p in pages if p["source_item_id"] == BOSTENAY)
    wikitext = (root / page["wikitext_path"]).read_text(encoding="utf-8")
    words = page_plain_text(page, root).split()
    if edit == "letter":
        word = next(w for w in words if len(w) > 3 and wikitext.count(w) == 1)
        validated = wikitext.replace(word, word + "א")
    else:
        pair = next(f"{a} {b}" for a, b in zip(words, words[1:]) if len(a) > 3 and len(b) > 3 and wikitext.count(f"{a} {b}") == 1)
        validated = wikitext.replace(pair, pair.replace(" ", "\n\n" if edit == "paragraph" else ""))
    page["quality_set_text_sha256"] = _sha(convert_wikitext(validated, {}).text)
    (root / "pages.jsonl").write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in pages), encoding="utf-8")
    return root, page, validated


def _revisions(page: dict, wikitext: str):
    def revisions_of(title: str) -> list[dict]:
        assert title == page["page_title"]
        return [{"revid": page["quality_history"][-1]["revision_id"], "slots": {"main": {"content": wikitext}}},
                {"revid": page["revision_id"], "slots": {"main": {"content": "later"}}}]
    return revisions_of


def _checks(path: Path, page: dict, record: dict, verdict: str, **extra: object) -> Path:
    check = {"page_title": page["page_title"], "source_item_id": page["source_item_id"],
             "validating_revision_id": record["validating_revision_id"], "latest_revision_id": page["revision_id"],
             "validated_wikitext_sha256": record["wikitext_sha256"], "verdict": verdict, "checked_by": "agent",
             "checker": "test", "checked_at": "2026-11-07", "method": "agent_validated_text_visual.v1",
             "detail": "every difference read on the scan", **extra}
    path.write_text(json.dumps({"schema_version": "wikisource_validated_text_checks.v1", "checks": [check]},
                               ensure_ascii=False), encoding="utf-8")
    return path


def test_validating_revision_attestation_keeps_the_two_editors() -> None:
    pages = {json.loads(line)["source_item_id"]: json.loads(line)
             for line in (SNAPSHOT / "pages.jsonl").read_text(encoding="utf-8").splitlines()}
    changed = validated_revision_attestation(pages[BOSTENAY])
    assert changed["adjudication_eligible"] and changed["reference_text_revision"] == "validating"
    assert changed["validating_revision_id"] == pages[BOSTENAY]["quality_history"][-1]["revision_id"]
    assert changed["proofreader"]["user"] != changed["validator"]["user"]
    assert not validated_revision_attestation(pages[SELIHOT])["adjudication_eligible"]  # unchanged: use it as is
    assert not validated_revision_attestation(pages["buber_tanhuma_1885__p0233"])["adjudication_eligible"]  # quality 3


def test_the_tool_pins_the_validating_wikitext_and_checks_its_checksum(tmp_path: Path) -> None:
    root, page, validated = _snapshot(tmp_path)
    summary = wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))
    [record] = summary["items"]
    assert record["item_id"] == f"{SOURCE}:{BOSTENAY}" and record["latest_revision_id"] == page["revision_id"]
    assert record["wikitext_sha256"] == _sha(validated) and record["converted_text_sha256"] == page["quality_set_text_sha256"]
    loaded = wvr.load_validated_revisions(tmp_path / "out")
    assert loaded[record["item_id"]]["wikitext"] == validated
    with pytest.raises(StageExecutionError, match="new or empty"):
        wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))
    with pytest.raises(StageExecutionError, match="does not match the checksum"):
        wvr.write_validated_revisions(root, tmp_path / "bad", _revisions(page, validated + "\nעוד"))
    with pytest.raises(StageExecutionError, match="not in its history"):
        wvr.write_validated_revisions(root, tmp_path / "gone", lambda title: [])
    (tmp_path / "out" / record["wikitext_path"]).write_text("altered", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="checksum mismatch"):
        wvr.load_validated_revisions(tmp_path / "out")


def test_a_checked_page_is_scored_on_its_validating_revision_text(tmp_path: Path) -> None:
    root, page, validated = _snapshot(tmp_path)
    summary = wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))
    [record] = summary["items"]
    checks = _checks(tmp_path / "checks.json", page, record, "validated_text_matches_scan")
    item_id = f"{SOURCE}:{BOSTENAY}"
    result = write_eval_reference_set(root, tmp_path / "set", reference_manifest_id="e2d3b_test",
                                      validated_revisions=tmp_path / "out", validated_text_checks=checks)
    assert result["counts"]["adjudicated"] == 2 and result["counts"]["adjudicated_validating_revision"] == 1
    assert result["counts"]["skipped"] == {} and result["validated_text_excluded"] == []
    entry = next(item for item in result["items"] if item["item_id"] == item_id)
    assert entry["reference_text_revision"] == "validating"
    assert entry["reference_text_revision_id"] == record["validating_revision_id"]
    assert entry["diff_vs_latest"]["character_edits"] == 1 and entry["diff_vs_latest"]["text_changing_edits_after_validation"] == 1
    assert next(item for item in result["items"] if item["item_id"] == f"{SOURCE}:{SELIHOT}")["reference_text_revision"] == "latest"
    loaded = load_adjudicated_references(tmp_path / "set" / "reference_manifest.json", modality="printed")
    record_text = loaded["references"][item_id].pages[0].text
    assert record_text == derive_validated_page_text(validated, {}, page, {}).text != page_plain_text(page, root)
    assert _sha(convert_wikitext(validated, {}).text) == record["converted_text_sha256"]
    adjudication = json.loads((tmp_path / "set" / entry["adjudication_record"]).read_text(encoding="utf-8"))
    assert adjudication["reference_text_revision"] == "validating"
    assert adjudication["page_revision_id"] == record["validating_revision_id"]
    assert adjudication["latest_revision_id"] == page["revision_id"]
    assert f"oldid={record['validating_revision_id']}" in adjudication["page_permalink"]
    assert adjudication["validated_text_check"]["checked_by"] == "agent" and adjudication["agent_attestation"] is None
    assert eval_refs_main([str(root), str(tmp_path / "cli"), "--validated-revisions", str(tmp_path / "out"),
                           "--validated-text-checks", str(checks)]) == 0


def test_validated_text_is_excluded_when_it_disagrees_with_the_scan_or_is_unchecked(tmp_path: Path) -> None:
    root, page, validated = _snapshot(tmp_path)
    [record] = wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))["items"]
    item_id = f"{SOURCE}:{BOSTENAY}"
    cases = {
        "validated_text_disagrees_with_scan": _checks(tmp_path / "d.json", page, record, "validated_text_disagrees_with_scan"),
        "validated_text_not_checked": _checks(tmp_path / "n.json", page, {**record, "validating_revision_id": 1},
                                              "validated_text_matches_scan"),
    }
    for reason, checks in cases.items():
        result = write_eval_reference_set(root, tmp_path / reason, reference_manifest_id="x",
                                          validated_revisions=tmp_path / "out", validated_text_checks=checks)
        assert result["counts"]["adjudicated"] == 1 and result["counts"]["skipped"] == {reason: 1}
        assert result["validated_text_excluded"] == [{"item_id": item_id, "reason": reason}]
    plain = write_eval_reference_set(root, tmp_path / "plain", reference_manifest_id="x")
    assert plain["counts"]["skipped"] == {"text_changed_after_validation": 1} and "validated_text_excluded" not in plain
    with pytest.raises(StageExecutionError, match="go together"):
        write_eval_reference_set(root, tmp_path / "half", reference_manifest_id="x", validated_revisions=tmp_path / "out")


def test_text_steps_are_re_pinned_not_reused_from_the_latest_text(tmp_path: Path) -> None:
    root, page, validated = _snapshot(tmp_path)
    with pytest.raises(ValueError, match="unprinted_notes_unchecked"):
        derive_validated_page_text(validated, {}, {**page, "unprinted_notes": [{"note": 1}]}, {})
    with pytest.raises(ValueError, match="excluded_spans_unmapped"):
        derive_validated_page_text(validated, {}, {**page, "excluded_spans": {"spans": [{}]}}, {})
    assert derive_validated_page_text(validated, {}, {**page, "unprinted_notes": [{"note": 1}]},
                                      {"unprinted_notes": []}).text == convert_wikitext(validated, {}).text
    assert validated_text_check_problems({"verdict": "maybe", "checked_by": "bot", "unprinted_notes": [0]})
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema_version": "wikisource_validated_text_checks.v1", "checks": [{"page_title": "x"}]}))
    with pytest.raises(StageExecutionError, match="bad validated-text check"):
        load_validated_text_checks(bad)
    bad.write_text(json.dumps({"schema_version": "other"}))
    with pytest.raises(StageExecutionError, match="must be"):
        load_validated_text_checks(bad)


def test_the_committed_checks_are_well_formed_and_record_an_agent_check_per_page() -> None:
    checks = load_validated_text_checks(COMMITTED_CHECKS)
    assert len(checks) == 26
    assert {check["checked_by"] for check in checks.values()} == {"agent"}
    verdicts = [check["verdict"] for check in checks.values()]
    assert verdicts.count("validated_text_matches_scan") == 5  # E2d3c: the paragraph-break page agrees
    assert verdicts.count("validated_text_disagrees_with_scan") == 21


def test_a_difference_limited_to_line_and_paragraph_whitespace_is_layout_not_text() -> None:
    assert layout_only_difference("אבג דהו.\n\nזחט", "אבג דהו. זחט")
    assert layout_only_difference("אבג  דהו\nזחט", "אבג דהו זחט")
    assert not layout_only_difference("אבג דהו", "אבג דהו")  # no difference at all
    assert not layout_only_difference("אבגדהו", "אבג דהו")  # words run together
    assert not layout_only_difference("אב ג דהו", "אבג דהו")  # a space inside a word
    assert not layout_only_difference("אבג\nדהו", "אבג דהז")  # a letter changed too


@pytest.mark.parametrize("verdict", ["validated_text_disagrees_with_scan", "validated_text_matches_scan"])
def test_a_paragraph_break_alone_never_disqualifies_the_validated_text(tmp_path: Path, verdict: str) -> None:
    root, page, validated = _snapshot(tmp_path, "paragraph")
    [record] = wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))["items"]
    checks = _checks(tmp_path / "checks.json", page, record, verdict)
    result = write_eval_reference_set(root, tmp_path / "set", reference_manifest_id="e2d3c_test",
                                      validated_revisions=tmp_path / "out", validated_text_checks=checks)
    assert result["counts"]["adjudicated_validating_revision"] == 1 and result["validated_text_excluded"] == []
    entry = next(item for item in result["items"] if item["item_id"] == f"{SOURCE}:{BOSTENAY}")
    assert entry["diff_vs_latest"]["layout_only"] is True and entry["diff_vs_latest"]["character_edits"] >= 1
    basis = "layout_only_difference" if verdict == "validated_text_disagrees_with_scan" else "check_verdict"
    assert entry["validated_text_accepted_by"] == basis
    adjudication = json.loads((tmp_path / "set" / entry["adjudication_record"]).read_text(encoding="utf-8"))
    assert adjudication["validated_text_accepted_by"] == basis
    assert adjudication["validated_text_check"]["verdict"] == verdict
    loaded = load_adjudicated_references(tmp_path / "set" / "reference_manifest.json", modality="printed")
    assert loaded["references"][entry["item_id"]].pages[0].text.split() == page_plain_text(page, root).split()


def test_words_run_together_are_a_text_difference_and_stay_disqualifying(tmp_path: Path) -> None:
    root, page, validated = _snapshot(tmp_path, "joined")
    [record] = wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))["items"]
    checks = _checks(tmp_path / "checks.json", page, record, "validated_text_disagrees_with_scan")
    result = write_eval_reference_set(root, tmp_path / "set", reference_manifest_id="x",
                                      validated_revisions=tmp_path / "out", validated_text_checks=checks)
    assert result["validated_text_excluded"] == [{"item_id": f"{SOURCE}:{BOSTENAY}", "reason": "validated_text_disagrees_with_scan"}]


def test_a_disagreeing_page_whose_text_steps_cannot_be_re_applied_stays_disagreeing(tmp_path: Path) -> None:
    root, page, validated = _snapshot(tmp_path, "paragraph")
    [record] = wvr.write_validated_revisions(root, tmp_path / "out", _revisions(page, validated))["items"]
    stale = {"text_sha256": "0" * 64, "spans": []}  # excluded spans pinned to another text
    for verdict, reason in (("validated_text_disagrees_with_scan", "validated_text_disagrees_with_scan"),
                            ("validated_text_matches_scan", "validated_text_excluded_spans_invalid")):
        checks = _checks(tmp_path / f"{verdict}.json", page, record, verdict, excluded_spans=stale)
        result = write_eval_reference_set(root, tmp_path / verdict, reference_manifest_id="x",
                                          validated_revisions=tmp_path / "out", validated_text_checks=checks)
        assert result["validated_text_excluded"] == [{"item_id": f"{SOURCE}:{BOSTENAY}", "reason": reason}]


def test_hebrewbooks_19784_p24_is_text_not_on_page_in_the_committed_checks() -> None:
    title = "עמוד:Hebrewbooks org 19784.pdf/24"
    check = inv.load_page_checks(COMMITTED_PAGE_CHECKS)[title]
    assert check["checked_by"] == "agent" and "Rashi" in check["text_not_on_page"]
    assert load_validated_text_checks(COMMITTED_CHECKS)[title]["verdict"] == "validated_text_disagrees_with_scan"


def test_e2d3d_hebrewbooks_19784_scored_pages_with_editors_text_are_text_not_on_page() -> None:
    checks = inv.load_page_checks(COMMITTED_PAGE_CHECKS)
    flagged = {n for n in (1, 2, 8, 18, 24, 25) if checks[f"עמוד:Hebrewbooks org 19784.pdf/{n}"].get("text_not_on_page")}
    assert flagged == {8, 24, 25}
    assert "E2d3d agent check" in checks["עמוד:Hebrewbooks org 19784.pdf/25"]["text_not_on_page"]
