"""E2d4: reference audit proposals (an agent proposes) and decisions (a human decides), and applying the decisions.

The scored Wikisource reference pages are audited against their scans. An agent reads every page and records each
place where the reference text disagrees with the print as a **proposal** (``reference_audit_proposals.v1``,
``docs/reference_audit_proposals.json``). A proposal is never attestation and never changes a reference by itself
(maintainer decision, 2026-11-07): ``status`` is always ``agent_proposed`` and ``checked_by`` always ``agent``.

A human reviewer then records one **decision** per proposal (``reference_audit_decisions.v1``,
``docs/reference_audit_decisions.json``): ``accepted`` (the proposed text), ``rejected`` (no change) or ``edited``
(the reviewer's own text for the same span). A decision names the reviewer by a pseudonymous handle (lower-case
letters, digits and hyphens, as ``qa-1`` or ``reviewer-2``; never a real name unless the reviewer consents to it as
the handle, and never an agent) and the date.

``apply_reference_audit`` is the only place a correction takes effect. It applies the accepted and edited decisions
of a page, and nothing else, to the exact text the proposals were made on (pinned by ``base_text_sha256``), and
returns the corrected text with its provenance: the base revision, the applied decision ids in text order, and the
new ``text_sha256``. Proposals without a decision are reported as pending (``audit_pending``) and leave the text as
it is. A stale or inconsistent proposal fails closed.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from hocrgen.core.errors import StageExecutionError

PROPOSALS_SCHEMA = "reference_audit_proposals.v1"
DECISIONS_SCHEMA = "reference_audit_decisions.v1"
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
REFERENCE_AUDIT_STATES = ("not_audited", "audited_no_findings", AUDIT_PENDING, "human_corrected", "human_reviewed_unchanged")
REVIEWER_HANDLE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
_AGENT_HANDLE = re.compile(r"(?:^|-)(?:agent|claude|bot|tool|llm|gpt|model|auto|automatic|system)(?:-|$)")
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


def reviewer_handle_problems(handle: Any) -> list[str]:
    """A decision's reviewer must be a pseudonymous human handle (``qa-1``, ``reviewer-2``), never an agent."""

    if not (isinstance(handle, str) and REVIEWER_HANDLE.match(handle) and len(handle) <= 40):
        return ["reviewer must be a pseudonymous handle: lower-case letters, digits and single hyphens (e.g. reviewer-1)"]
    if _AGENT_HANDLE.search(handle):
        return ["reviewer must be a human; an agent never decides"]
    return []


def reference_audit_decisions_problems(payload: Mapping[str, Any], proposals: Mapping[str, Any]) -> list[str]:
    """Every problem with a ``reference_audit_decisions.v1`` payload, checked against its (valid) proposals."""

    if payload.get("schema_version") != DECISIONS_SCHEMA:
        return [f"schema_version must be {DECISIONS_SCHEMA}"]
    problems = []
    if payload.get("audit_id") != proposals.get("audit_id"):
        problems.append("audit_id must match the proposals' audit_id")
    known = {proposal["proposal_id"]: proposal for proposal in proposals.get("proposals") or []}
    decided: set[str] = set()
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
        if pid not in known:
            problems.append(f"{label}: proposal_id {pid!r} is not a proposal of {proposals.get('audit_id')}")
        elif pid in decided:
            problems.append(f"{label}: a second decision for {pid}; record one decision per proposal")
        else:
            decided.add(pid)
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
        if decision.get("checked_by") != "human":
            problems.append(f"{label}: checked_by must be human; an agent proposal is never a decision")
        problems.extend(f"{label}: {problem}" for problem in reviewer_handle_problems(decision.get("reviewer")))
        if not (isinstance(decision.get("decided_at"), str) and _valid_date(decision["decided_at"])):
            problems.append(f"{label}: decided_at must be a YYYY-MM-DD date")
        note = decision.get("note")
        if note is not None and not isinstance(note, str):
            problems.append(f"{label}: note must be a string")
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

    def __init__(self, proposals: Mapping[str, Any], decisions: Mapping[str, Any] | None = None) -> None:
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
        self.decisions = {d["proposal_id"]: d for d in (decisions or {}).get("decisions") or []}

    @classmethod
    def from_files(cls, proposals_path: Path, decisions_path: Path | None = None) -> "ReferenceAudit":
        proposals = load_reference_audit_proposals(proposals_path)
        decisions = load_reference_audit_decisions(decisions_path, proposals) if decisions_path is not None else None
        return cls(proposals, decisions)

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
    """Apply a page's human-accepted and human-edited corrections, and only those, to its reference ``text``.

    Returns ``{"text", "state", "audit_pending", "pending_proposals", "applied_decisions", "rejected_decisions",
    "provenance"}``. ``state`` is one of ``REFERENCE_AUDIT_STATES``. ``provenance`` is ``None`` unless a correction
    was applied; then it records the base revision and text checksum, the applied decision ids in text order and
    the corrected text's ``text_sha256``. Agent proposals alone never change the text. A page whose text is not
    the one the proposals were made on fails closed, as does a proposal whose span no longer matches.
    """

    unchanged = {"text": text, "audit_pending": False, "pending_proposals": [], "applied_decisions": [],
                 "rejected_decisions": [], "provenance": None}
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
    corrections, applied, rejected, pending = [], [], [], []
    for proposal in found:
        problems = proposal_text_problems(proposal, text)
        if problems:
            raise StageExecutionError("; ".join(problems))
        decision = audit.decisions.get(proposal["proposal_id"])
        if decision is None:
            pending.append(proposal["proposal_id"])
        elif decision["decision"] == "rejected":
            rejected.append(decision["decision_id"])
        else:
            replacement = proposal["proposed"] if decision["decision"] == "accepted" else decision["text"]
            corrections.append((proposal["start"], proposal["end"], replacement))
            applied.append({"decision_id": decision["decision_id"], "proposal_id": proposal["proposal_id"],
                            "decision": decision["decision"], "reviewer": decision["reviewer"],
                            "decided_at": decision["decided_at"], "start": proposal["start"], "end": proposal["end"],
                            "replacement": replacement})
    corrected = apply_text_corrections(text, corrections)
    provenance = None
    if applied:
        provenance = {"audit_id": audit.audit_id, "base_revision_id": page["base_revision_id"],
                      "base_text_sha256": page["base_text_sha256"],
                      "applied_decisions": [entry["decision_id"] for entry in applied],
                      "text_sha256": text_sha256(corrected)}
    if pending:
        state = AUDIT_PENDING
    elif applied:
        state = "human_corrected"
    else:
        state = "human_reviewed_unchanged"
    return {"text": corrected, "state": state, "audit_pending": bool(pending), "pending_proposals": pending,
            "applied_decisions": applied, "rejected_decisions": rejected, "provenance": provenance}


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
