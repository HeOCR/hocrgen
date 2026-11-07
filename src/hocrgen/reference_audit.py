"""E2d4: reference audit proposals (an agent proposes) and decisions (a human decides), and applying the decisions.

The scored Wikisource reference pages are audited against their scans. An agent reads every page and records each
place where the reference text disagrees with the print as a **proposal** (``reference_audit_proposals.v1``,
``docs/reference_audit_proposals.json``). A proposal is never attestation and never changes a reference by itself
(maintainer decision, 2026-11-07): ``status`` is always ``agent_proposed`` and ``checked_by`` always ``agent``.

Human reviewers then record **decisions** (``reference_audit_decisions.v1``, ``docs/reference_audit_decisions.json``):
``accepted`` (the proposed text), ``rejected`` (no change) or ``edited`` (the reviewer's own text for the same span).
Each decision names its reviewer by a pseudonymous id, ``rv_`` and 8 lower-case letters or digits (``rv_3f9a01bc``),
so no real name is ever recorded, and the date. Several reviewers may decide one proposal (one decision each), so a
stricter rule can come later: a proposal's outcome takes effect when at least ``min_reviewers`` reviewers decided it
and all of them agree (the same decision, and for ``edited`` the same text). Reviewers who disagree leave it
``conflict``. The default is ``min_reviewers=1``: one human accept suffices while there is a single reviewer. Every
outcome records its ``reviewer_count``.

``apply_reference_audit`` is the only place a correction takes effect. It applies the agreed accepted and edited
outcomes of a page, and nothing else, to the exact text the proposals were made on (pinned by ``base_text_sha256``),
and returns the corrected text with its provenance: the base revision, the applied decision ids in text order, and
the new ``text_sha256``. Proposals without an agreed outcome (undecided, short of ``min_reviewers``, or in conflict)
are reported as pending (``audit_pending``) and leave the text as it is. A stale or inconsistent proposal fails
closed.

**Rule decisions (E2d4b, ``reference_audit_decisions.v2``).** A proposal that a maintainer-approved reference rule
(``hocrgen.reference_rules``, e.g. ``space_before_punctuation.v1``) makes exactly may be resolved by that rule: a
decision with ``checked_by: rule``, the ``rule`` name, its ``decision_record`` and the deterministic id
``rule:<rule>:<proposal_id>``, and no reviewer. It counts as decided for the page state, but it is never human review:
it adds no reviewer, never makes a reference ``human_corrected`` on its own (``rule_corrected``, or
``human_and_rule_corrected`` beside human corrections), and is listed apart (``rule_decisions``,
``applied_rule_decisions``). ``apply_reference_audit`` re-checks on the page text that the rule really makes the
proposed change and fails closed otherwise. A proposal decided by a human takes no rule decision. ``v1`` files
(human decisions only, as the review app exports them) stay valid.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_rules import REFERENCE_RULES, RULE_DECISION_RECORDS, rule_covers

PROPOSALS_SCHEMA = "reference_audit_proposals.v1"
DECISIONS_SCHEMA_V1 = "reference_audit_decisions.v1"  # human decisions only (the review app's export)
DECISIONS_SCHEMA = "reference_audit_decisions.v2"  # v1 plus rule decisions (checked_by: rule)
DECISIONS_SCHEMAS = (DECISIONS_SCHEMA_V1, DECISIONS_SCHEMA)
CATEGORIES = ("letter_confusion", "word_join_split", "punctuation", "spacing", "missing_text", "extra_text",
              "unprinted_editors_text")
CONFIDENCES = ("high", "medium", "low")
PAGE_AUDIT_STATUSES = ("audited_with_findings", "audited_no_findings")
DECISION_VALUES = ("accepted", "rejected", "edited")
PROPOSAL_STATUS = "agent_proposed"
# The attestation of a reference that carries at least one applied human correction (``page_attestation`` names
# the uncorrected state ``two_editor_validated``).
HUMAN_CORRECTED_ATTESTATION = "two_editor_validated_human_corrected"
AUDIT_PENDING = "audit_pending"
REFERENCE_AUDIT_STATES = ("not_audited", "audited_no_findings", AUDIT_PENDING, "human_corrected", "human_reviewed_unchanged",
                          "rule_corrected", "human_and_rule_corrected")
REVIEWER_ID = re.compile(r"^rv_[0-9a-z]{8}$")
DEFAULT_MIN_REVIEWERS = 1
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_FOOTNOTE_MARK = re.compile(r"\[(\d+)\]")


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _box_problems(region: Any) -> list[str]:
    if not isinstance(region, Mapping) or region.get("coordinate_frame") != "page":
        return ["region must be {coordinate_frame: page, box_normalized}"]
    box = region.get("box_normalized")
    if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in box)):
        return ["region.box_normalized must be [x0, y0, x1, y1]"]
    if not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1):
        return ["region.box_normalized must be fractions of the page with x0 < x1 and y0 < y1"]
    return []


def proposal_problems(proposal: Mapping[str, Any]) -> list[str]:
    """Problems with one proposal on its own (the text check is ``proposal_text_problems``)."""

    problems = []
    for key in ("proposal_id", "item_id", "note"):
        if not (isinstance(proposal.get(key), str) and proposal[key].strip()):
            problems.append(f"{key} must be a non-empty string")
    for key in ("current", "proposed", "context_before", "context_after"):
        if not isinstance(proposal.get(key), str):
            problems.append(f"{key} must be a string")
    start, end = proposal.get("start"), proposal.get("end")
    if not (_is_int(start) and _is_int(end) and 0 <= start <= end):
        problems.append("start and end must be character offsets with 0 <= start <= end")
    elif isinstance(proposal.get("current"), str) and end - start != len(proposal["current"]):
        problems.append("end - start must equal the length of current")
    if isinstance(proposal.get("current"), str) and proposal.get("current") == proposal.get("proposed"):
        problems.append("proposed must differ from current")
    if proposal.get("current") == "" and not (proposal.get("context_before") and proposal.get("context_after")):
        problems.append("an insertion (empty current) needs both context_before and context_after")
    if proposal.get("category") not in CATEGORIES:
        problems.append(f"category must be one of {', '.join(CATEGORIES)}")
    if proposal.get("confidence") not in CONFIDENCES:
        problems.append(f"confidence must be one of {', '.join(CONFIDENCES)}")
    if proposal.get("status") != PROPOSAL_STATUS:
        problems.append(f"status must be {PROPOSAL_STATUS}: a proposal is never attestation")
    if proposal.get("checked_by") != "agent":
        problems.append("checked_by must be agent: proposals come from the agent audit; humans write decisions")
    problems.extend(_box_problems(proposal.get("region")))
    return problems


def proposal_text_problems(proposal: Mapping[str, Any], text: str) -> list[str]:
    """Whether a proposal's span, current text and both contexts are exactly where it says in ``text``."""

    start, end = proposal["start"], proposal["end"]
    before, after = proposal.get("context_before", ""), proposal.get("context_after", "")
    if end > len(text) or text[start:end] != proposal["current"]:
        return [f"{proposal['proposal_id']}: current is not the text at [{start}:{end}]"]
    if text[max(0, start - len(before)):start] != before or text[end:end + len(after)] != after:
        return [f"{proposal['proposal_id']}: context does not match the text around [{start}:{end}]"]
    return []


def _overlap_problems(proposals: list[Mapping[str, Any]]) -> list[str]:
    """Proposals of one page must not overlap; an insertion may not sit at the start of another proposal."""

    problems = []
    ordered = sorted(proposals, key=lambda p: (p["start"], p["end"]))
    for left, right in zip(ordered, ordered[1:]):
        if left["end"] > right["start"] or (left["start"] == left["end"] == right["start"]):
            problems.append(f"{left['proposal_id']} and {right['proposal_id']} overlap")
    return problems


def reference_audit_proposals_problems(payload: Mapping[str, Any]) -> list[str]:
    """Every problem with a ``reference_audit_proposals.v1`` payload (empty when valid)."""

    if payload.get("schema_version") != PROPOSALS_SCHEMA:
        return [f"schema_version must be {PROPOSALS_SCHEMA}"]
    problems = []
    if not (isinstance(payload.get("audit_id"), str) and payload["audit_id"].strip()):
        problems.append("audit_id must be a non-empty string")
    if payload.get("checked_by") != "agent":
        problems.append("checked_by must be agent")
    if not (isinstance(payload.get("checker"), str) and payload["checker"].strip()):
        problems.append("checker must name the agent")
    if not (isinstance(payload.get("proposed_at"), str) and _valid_date(payload["proposed_at"])):
        problems.append("proposed_at must be a YYYY-MM-DD date")
    pages: dict[str, Mapping[str, Any]] = {}
    for page in payload.get("pages") or []:
        item_id = page.get("item_id")
        if not isinstance(item_id, str) or item_id in pages:
            problems.append(f"page {item_id!r}: item_id missing or listed twice")
            continue
        pages[item_id] = page
        if not _is_int(page.get("base_revision_id")):
            problems.append(f"page {item_id}: base_revision_id must be the revision the text comes from")
        if not (isinstance(page.get("base_text_sha256"), str) and _SHA256.match(page["base_text_sha256"])):
            problems.append(f"page {item_id}: base_text_sha256 must be a SHA-256")
        if page.get("audit_status") not in PAGE_AUDIT_STATUSES:
            problems.append(f"page {item_id}: audit_status must be one of {', '.join(PAGE_AUDIT_STATUSES)}")
        candidate = page.get("text_not_on_page_candidate")
        if candidate is not None and not (isinstance(candidate, str) and candidate.strip()):
            problems.append(f"page {item_id}: text_not_on_page_candidate must be null or say what is not on the page")
    if not pages:
        problems.append("pages must list every audited page")
    by_page: dict[str, list[Mapping[str, Any]]] = {}
    ids = set()
    for proposal in payload.get("proposals") or []:
        pid = proposal.get("proposal_id")
        problems.extend(f"proposal {pid}: {problem}" for problem in proposal_problems(proposal))
        if pid in ids:
            problems.append(f"proposal {pid}: listed twice")
        ids.add(pid)
        if proposal.get("item_id") not in pages:
            problems.append(f"proposal {pid}: item_id is not an audited page")
            continue
        by_page.setdefault(proposal["item_id"], []).append(proposal)
    if problems:
        return problems
    for item_id, page in pages.items():
        found = by_page.get(item_id, [])
        if page.get("proposal_count") != len(found):
            problems.append(f"page {item_id}: proposal_count {page.get('proposal_count')} but {len(found)} proposals")
        if page["audit_status"] == "audited_no_findings" and found:
            problems.append(f"page {item_id}: audited_no_findings but has proposals")
        if page["audit_status"] == "audited_with_findings" and not found:
            problems.append(f"page {item_id}: audited_with_findings but has no proposals")
        problems.extend(_overlap_problems(found))
    return problems


def _valid_date(value: str) -> bool:
    if not _DATE.match(value):
        return False
    try:
        _dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def reviewer_id_problems(reviewer: Any) -> list[str]:
    """A decision's reviewer is a pseudonymous id: ``rv_`` and 8 lower-case letters or digits (never a real name)."""

    if not (isinstance(reviewer, str) and REVIEWER_ID.match(reviewer)):
        return ["reviewer must be a pseudonymous id: rv_ and 8 lower-case letters or digits (e.g. rv_3f9a01bc)"]
    return []


def rule_decision_id(rule: str, proposal_id: str) -> str:
    return f"rule:{rule}:{proposal_id}"


def _rule_decision_problems(label: str, decision: Mapping[str, Any], version: str) -> list[str]:
    if version != DECISIONS_SCHEMA:
        return [f"{label}: checked_by must be human; rule decisions need {DECISIONS_SCHEMA}"]
    problems = []
    rule = decision.get("rule")
    if rule not in REFERENCE_RULES:
        return [f"{label}: rule must be one of {', '.join(REFERENCE_RULES)}"]
    if decision.get("decision_record") != RULE_DECISION_RECORDS[rule]:
        problems.append(f"{label}: decision_record must be {RULE_DECISION_RECORDS[rule]}")
    if decision.get("decision_id") != rule_decision_id(rule, str(decision.get("proposal_id"))):
        problems.append(f"{label}: a rule decision's id must be rule:<rule>:<proposal_id>")
    if decision.get("decision") != "accepted":
        problems.append(f"{label}: a rule decision can only be accepted")
    if "reviewer" in decision:
        problems.append(f"{label}: a rule decision names no reviewer; it is not human review")
    return problems


def reference_audit_decisions_problems(payload: Mapping[str, Any], proposals: Mapping[str, Any]) -> list[str]:
    """Every problem with a ``reference_audit_decisions.v1``/``v2`` payload, checked against its (valid) proposals."""

    version = payload.get("schema_version")
    if version not in DECISIONS_SCHEMAS:
        return [f"schema_version must be {' or '.join(DECISIONS_SCHEMAS)}"]
    problems = []
    if payload.get("audit_id") != proposals.get("audit_id"):
        problems.append("audit_id must match the proposals' audit_id")
    known = {proposal["proposal_id"]: proposal for proposal in proposals.get("proposals") or []}
    decided: set[tuple[str, Any]] = set()
    by_human: set[str] = set()
    by_rule: set[str] = set()
    ids: set[str] = set()
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        return problems + ["decisions must be a list"]
    for number, decision in enumerate(decisions, start=1):
        label = f"decision {decision.get('decision_id') or number}"
        did = decision.get("decision_id")
        if not (isinstance(did, str) and did.strip()):
            problems.append(f"{label}: decision_id must be a non-empty string")
        elif did in ids:
            problems.append(f"{label}: decision_id listed twice")
        ids.add(did)
        pid = decision.get("proposal_id")
        is_rule = decision.get("checked_by") == "rule"
        who = f"rule:{decision.get('rule')}" if is_rule else decision.get("reviewer")
        if pid not in known:
            problems.append(f"{label}: proposal_id {pid!r} is not a proposal of {proposals.get('audit_id')}")
        elif (pid, who) in decided:
            problems.append(f"{label}: a second decision by {who} for {pid}; one per reviewer")
        else:
            decided.add((pid, who))
            (by_rule if is_rule else by_human).add(pid)
            if decision.get("item_id") not in (None, known[pid]["item_id"]):
                problems.append(f"{label}: item_id does not match the proposal's")
        value = decision.get("decision")
        if value not in DECISION_VALUES:
            problems.append(f"{label}: decision must be one of {', '.join(DECISION_VALUES)}")
        if value == "edited":
            if not isinstance(decision.get("text"), str):
                problems.append(f"{label}: an edited decision needs the reviewer's text for the span")
            elif pid in known and decision["text"] == known[pid]["current"]:
                problems.append(f"{label}: an edit equal to the current text is a rejection; record rejected")
        elif "text" in decision:
            problems.append(f"{label}: only an edited decision carries text")
        if is_rule:
            problems.extend(_rule_decision_problems(label, decision, version))
        elif decision.get("checked_by") != "human":
            problems.append(f"{label}: checked_by must be human or rule; an agent proposal is never a decision")
        else:
            problems.extend(f"{label}: {problem}" for problem in reviewer_id_problems(decision.get("reviewer")))
        if not (isinstance(decision.get("decided_at"), str) and _valid_date(decision["decided_at"])):
            problems.append(f"{label}: decided_at must be a YYYY-MM-DD date")
        note = decision.get("note")
        if note is not None and not isinstance(note, str):
            problems.append(f"{label}: note must be a string")
    for pid in sorted(by_rule & by_human):
        problems.append(f"{pid}: decided by a human and by a rule; a human decision takes no rule decision")
    return problems


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageExecutionError(f"cannot read {Path(path).name}: {exc}") from exc


def load_reference_audit_proposals(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    problems = reference_audit_proposals_problems(payload)
    if problems:
        raise StageExecutionError(f"{Path(path).name} is not a valid {PROPOSALS_SCHEMA}: " + "; ".join(problems[:10]))
    return payload


def load_reference_audit_decisions(path: Path, proposals: Mapping[str, Any]) -> dict[str, Any]:
    payload = _read_json(path)
    problems = reference_audit_decisions_problems(payload, proposals)
    if problems:
        raise StageExecutionError(f"{Path(path).name} is not a valid {DECISIONS_SCHEMA}: " + "; ".join(problems[:10]))
    return payload


class ReferenceAudit:
    """Validated proposals plus (optionally) validated human decisions, indexed by page."""

    def __init__(self, proposals: Mapping[str, Any], decisions: Mapping[str, Any] | None = None, *,
                 min_reviewers: int = DEFAULT_MIN_REVIEWERS) -> None:
        if not (_is_int(min_reviewers) and min_reviewers >= 1):
            raise StageExecutionError("min_reviewers must be 1 or more")
        self.min_reviewers = min_reviewers
        problems = reference_audit_proposals_problems(proposals)
        if problems:
            raise StageExecutionError(f"invalid {PROPOSALS_SCHEMA}: " + "; ".join(problems[:10]))
        if decisions is not None:
            problems = reference_audit_decisions_problems(decisions, proposals)
            if problems:
                raise StageExecutionError(f"invalid {DECISIONS_SCHEMA}: " + "; ".join(problems[:10]))
        self.audit_id: str = proposals["audit_id"]
        self.pages = {page["item_id"]: page for page in proposals["pages"]}
        self.proposals: dict[str, list[Mapping[str, Any]]] = {}
        for proposal in proposals["proposals"]:
            self.proposals.setdefault(proposal["item_id"], []).append(proposal)
        for found in self.proposals.values():
            found.sort(key=lambda p: (p["start"], p["end"]))
        self.decisions: dict[str, list[Mapping[str, Any]]] = {}
        for decision in (decisions or {}).get("decisions") or []:
            self.decisions.setdefault(decision["proposal_id"], []).append(decision)
        for found in self.decisions.values():
            found.sort(key=lambda d: (d.get("reviewer") or "", d["decision_id"]))

    @classmethod
    def from_files(cls, proposals_path: Path, decisions_path: Path | None = None, *,
                   min_reviewers: int = DEFAULT_MIN_REVIEWERS) -> "ReferenceAudit":
        proposals = load_reference_audit_proposals(proposals_path)
        decisions = load_reference_audit_decisions(decisions_path, proposals) if decisions_path is not None else None
        return cls(proposals, decisions, min_reviewers=min_reviewers)

    def outcome(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        """A proposal's outcome from its decisions: ``undecided``, ``awaiting_reviewers`` (agreeing but fewer than
        ``min_reviewers``), ``conflict`` (reviewers disagree), or the agreed ``accepted``/``rejected``/``edited``
        with its ``replacement``; always with ``checked_by`` (``human`` or ``rule``), ``reviewer_count``,
        ``reviewers`` and ``decision_ids``. A rule decision is ``accepted`` with no reviewer (``reviewer_count`` 0);
        ``min_reviewers`` counts human reviewers only and does not apply to it."""

        found = self.decisions.get(proposal["proposal_id"], [])
        rules = [d for d in found if d["checked_by"] == "rule"]
        if rules:
            (decision,) = rules  # the validator allows one rule decision per rule and none beside a human one
            return {"checked_by": "rule", "rule": decision["rule"], "reviewer_count": 0, "reviewers": [],
                    "decision_ids": [decision["decision_id"]], "outcome": "accepted", "replacement": proposal["proposed"]}
        base = {"checked_by": "human", "reviewer_count": len(found), "reviewers": [d["reviewer"] for d in found],
                "decision_ids": [d["decision_id"] for d in found], "replacement": None}
        if not found:
            return {**base, "outcome": "undecided"}
        keys = {(d["decision"], d.get("text")) for d in found}
        if len(keys) > 1:
            return {**base, "outcome": "conflict"}
        if len(found) < self.min_reviewers:
            return {**base, "outcome": "awaiting_reviewers"}
        value, text = keys.pop()
        replacement = proposal["proposed"] if value == "accepted" else text if value == "edited" else None
        return {**base, "outcome": value, "replacement": replacement}

    def item_ids(self) -> set[str]:
        return set(self.pages)


def apply_text_corrections(text: str, corrections: Iterable[tuple[int, int, str]]) -> str:
    """``text`` with each ``(start, end, replacement)`` applied; spans are base-text offsets and must not overlap."""

    out, position = [], 0
    for start, end, replacement in sorted(corrections, key=lambda c: (c[0], c[1])):
        if start < position:
            raise StageExecutionError("overlapping corrections")
        out.append(text[position:start])
        out.append(replacement)
        position = end
    out.append(text[position:])
    return "".join(out)


def apply_reference_audit(audit: ReferenceAudit | None, item_id: str, text: str,
                          base_revision_id: int | None = None) -> dict[str, Any]:
    """Apply a page's agreed human-accepted and human-edited corrections, and only those, to its reference ``text``.

    Returns ``{"text", "state", "audit_pending", "pending_proposals", "conflicting_proposals", "applied_decisions",
    "rule_decisions", "rejected_decisions", "human_decided_spans", "min_reviewers", "provenance"}``; each
    ``applied_decisions`` entry (human decisions only) records its ``reviewer_count``; ``rule_decisions`` lists the
    applied rule decisions apart. ``state`` is one of ``REFERENCE_AUDIT_STATES``. ``provenance`` is ``None`` unless a
    correction was applied; then it records the base revision and text checksum, the applied human decision ids in
    text order (``applied_decisions``), any applied rule decision ids (``applied_rule_decisions``) and the corrected
    text's ``text_sha256``. ``human_decided_spans`` are the ``[start, end)`` spans, in the corrected text, of every
    proposal any human decided (applied, rejected, in conflict or awaiting more reviewers), so a later reference rule
    leaves them as the human left them. Agent proposals alone never change the text. A page whose text is not the one the proposals
    were made on fails closed, as does a proposal whose span no longer matches, or a rule decision the rule does not
    make on this text.
    """

    unchanged = {"text": text, "audit_pending": False, "pending_proposals": [], "conflicting_proposals": [],
                 "applied_decisions": [], "rule_decisions": [], "rejected_decisions": [], "human_decided_spans": [],
                 "provenance": None,
                 "min_reviewers": audit.min_reviewers if audit is not None else DEFAULT_MIN_REVIEWERS}
    if audit is None or item_id not in audit.pages:
        return {**unchanged, "state": "not_audited"}
    page = audit.pages[item_id]
    if text_sha256(text) != page["base_text_sha256"]:
        raise StageExecutionError(f"{item_id}: the reference text is not the text {audit.audit_id} audited "
                                  "(base_text_sha256 differs); re-audit the page")
    if base_revision_id is not None and base_revision_id != page["base_revision_id"]:
        raise StageExecutionError(f"{item_id}: the reference comes from revision {base_revision_id}, "
                                  f"but {audit.audit_id} audited revision {page['base_revision_id']}")
    found = audit.proposals.get(item_id, [])
    if not found:
        return {**unchanged, "state": "audited_no_findings"}
    corrections, applied, by_rule, rejected, pending, conflicting = [], [], [], [], [], []
    human_spans, shift = [], 0  # spans a human decided, in corrected-text offsets
    for proposal in found:
        problems = proposal_text_problems(proposal, text)
        if problems:
            raise StageExecutionError("; ".join(problems))
        outcome = audit.outcome(proposal)
        start, end = proposal["start"] + shift, proposal["end"] + shift
        if outcome["outcome"] in ("undecided", "awaiting_reviewers", "conflict"):
            pending.append(proposal["proposal_id"])
            if outcome["outcome"] == "conflict":
                conflicting.append(proposal["proposal_id"])
            if outcome["reviewer_count"]:
                human_spans.append([start, end])
        elif outcome["outcome"] == "rejected":
            rejected.extend(outcome["decision_ids"])
            human_spans.append([start, end])
        else:
            replacement = outcome["replacement"]
            corrections.append((proposal["start"], proposal["end"], replacement))
            shift += len(replacement) - (proposal["end"] - proposal["start"])
            dates = [d["decided_at"] for d in audit.decisions[proposal["proposal_id"]]]
            entry = {"proposal_id": proposal["proposal_id"], "decision": outcome["outcome"],
                     "decision_ids": outcome["decision_ids"], "reviewers": outcome["reviewers"],
                     "reviewer_count": outcome["reviewer_count"], "decided_at": max(dates),
                     "start": proposal["start"], "end": proposal["end"], "replacement": replacement}
            if outcome["checked_by"] == "rule":
                if not rule_covers(outcome["rule"], text, proposal["start"], proposal["end"], proposal["proposed"]):
                    raise StageExecutionError(f"{proposal['proposal_id']}: decided by rule {outcome['rule']}, but the "
                                              "rule does not make the proposed change on this text")
                by_rule.append({**entry, "checked_by": "rule", "rule": outcome["rule"]})
            else:
                applied.append(entry)
                human_spans.append([start, start + len(replacement)])
    corrected = apply_text_corrections(text, corrections)
    provenance = None
    if applied or by_rule:
        provenance = {"audit_id": audit.audit_id, "base_revision_id": page["base_revision_id"],
                      "base_text_sha256": page["base_text_sha256"], "min_reviewers": audit.min_reviewers,
                      "applied_decisions": [did for entry in applied for did in entry["decision_ids"]],
                      **({"applied_rule_decisions": [did for entry in by_rule for did in entry["decision_ids"]]}
                         if by_rule else {}),
                      "text_sha256": text_sha256(corrected)}
    if pending:
        state = AUDIT_PENDING
    elif applied and by_rule:
        state = "human_and_rule_corrected"
    elif applied:
        state = "human_corrected"
    elif by_rule:
        state = "rule_corrected"
    else:
        state = "human_reviewed_unchanged"
    return {"text": corrected, "state": state, "audit_pending": bool(pending), "pending_proposals": pending,
            "conflicting_proposals": conflicting, "applied_decisions": applied, "rule_decisions": by_rule,
            "rejected_decisions": rejected, "human_decided_spans": human_spans,
            "min_reviewers": audit.min_reviewers, "provenance": provenance}


def rule_coverage(audit: ReferenceAudit, texts: Mapping[str, str], rules: Iterable[str] = REFERENCE_RULES,
                  ) -> dict[str, list[Mapping[str, Any]]]:
    """Per rule, the proposals still without any decision that the rule makes exactly on their page's text
    (``texts``: item id -> the audited base text). Proposals a human or a rule already decided are left out."""

    covered: dict[str, list[Mapping[str, Any]]] = {rule: [] for rule in rules}
    for item_id, found in sorted(audit.proposals.items()):
        if item_id not in texts:
            continue
        text = texts[item_id]
        if text_sha256(text) != audit.pages[item_id]["base_text_sha256"]:
            raise StageExecutionError(f"{item_id}: the text is not the one {audit.audit_id} audited")
        for proposal in found:
            if audit.decisions.get(proposal["proposal_id"]):
                continue
            for rule in covered:
                if rule_covers(rule, text, proposal["start"], proposal["end"], proposal["proposed"]):
                    covered[rule].append(proposal)
                    break
    return covered


def rule_decisions_for(proposals: Iterable[Mapping[str, Any]], rule: str, decided_at: str) -> list[dict[str, Any]]:
    """Deterministic rule decisions (``checked_by: rule``) for proposals a rule covers."""

    return [{"decision_id": rule_decision_id(rule, proposal["proposal_id"]), "proposal_id": proposal["proposal_id"],
             "item_id": proposal["item_id"], "decision": "accepted", "checked_by": "rule", "rule": rule,
             "decision_record": RULE_DECISION_RECORDS[rule], "decided_at": decided_at}
            for proposal in proposals]


def merge_decisions(base: Mapping[str, Any], incoming: Mapping[str, Any], proposals: Mapping[str, Any]) -> dict[str, Any]:
    """``base`` (v1 or v2) plus every decision of ``incoming`` (e.g. a review-app v1 export) it does not hold yet,
    as ``reference_audit_decisions.v2``, sorted by decision id and validated. A decision id held with a different
    content fails closed."""

    if incoming.get("audit_id") != base.get("audit_id"):
        raise StageExecutionError("the decisions to add are for another audit_id")
    for payload in (base, incoming):
        problems = reference_audit_decisions_problems(payload, proposals)
        if problems:
            raise StageExecutionError("invalid decisions: " + "; ".join(problems[:10]))
    held = {d["decision_id"]: d for d in base["decisions"]}
    for decision in incoming["decisions"]:
        if decision["decision_id"] in held and held[decision["decision_id"]] != decision:
            raise StageExecutionError(f"{decision['decision_id']}: already recorded with a different content")
        held.setdefault(decision["decision_id"], dict(decision))
    merged = {**base, "schema_version": DECISIONS_SCHEMA, "decisions": [held[key] for key in sorted(held)]}
    problems = reference_audit_decisions_problems(merged, proposals)
    if problems:
        raise StageExecutionError("merged decisions are invalid: " + "; ".join(problems[:10]))
    return merged


def footnote_marks(text: str) -> list[str]:
    """The ``[n]`` footnote marks of a reference text, in order."""

    return _FOOTNOTE_MARK.findall(text)


def corrected_footnote_facts(facts: Mapping[str, Any], base_text: str, corrected_text: str) -> dict[str, Any]:
    """A page's footnote facts after correction: unchanged unless the corrections added or removed ``[n]`` marks.

    Then the facts follow the corrected text's marks (``bracketed_index`` and the number of distinct marks), so the
    ``footnote_masked.v1`` view sees every mark a human added.
    """

    if footnote_marks(base_text) == footnote_marks(corrected_text):
        return dict(facts)
    marks = set(footnote_marks(corrected_text))
    return {**facts, "footnote_marker_style": "bracketed_index" if marks else None, "footnote_count": len(marks)}
