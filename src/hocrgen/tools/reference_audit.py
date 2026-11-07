"""E2d4: validate the reference audit files and summarise where the human review stands.

``python -m hocrgen.tools.reference_audit [--proposals P] [--decisions D] [--snapshot-root ROOT]`` validates
``reference_audit_proposals.v1`` and ``reference_audit_decisions.v1`` (by default the committed
``docs/reference_audit_proposals.json`` and ``docs/reference_audit_decisions.json``) and prints counts only: proposals
by category and confidence, decisions by value, and pages pending. With an operator ``--snapshot-root`` (a Wikisource
snapshot holding the audited pages) it also checks every proposal's span and context against the page's current
scored text, so a stale proposal is caught before a reviewer sees it. It never prints reference text.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_audit import (
    ReferenceAudit,
    load_reference_audit_decisions,
    load_reference_audit_proposals,
    proposal_text_problems,
    text_sha256,
)

DOCS = Path(__file__).resolve().parents[3] / "docs"
DEFAULT_PROPOSALS = DOCS / "reference_audit_proposals.json"
DEFAULT_DECISIONS = DOCS / "reference_audit_decisions.json"


def audit_summary(proposals: dict[str, Any], decisions: dict[str, Any] | None) -> dict[str, Any]:
    """Counts only: proposals by category and confidence, decisions by value, pages with undecided proposals."""

    decided = {d["proposal_id"]: d["decision"] for d in (decisions or {}).get("decisions") or []}
    pending_pages = {p["item_id"] for p in proposals["proposals"] if p["proposal_id"] not in decided}
    return {
        "audit_id": proposals["audit_id"],
        "pages": len(proposals["pages"]),
        "pages_audited_no_findings": sum(1 for p in proposals["pages"] if p["audit_status"] == "audited_no_findings"),
        "text_not_on_page_candidates": sum(1 for p in proposals["pages"] if p.get("text_not_on_page_candidate")),
        "proposals": len(proposals["proposals"]),
        "by_category": dict(sorted(Counter(p["category"] for p in proposals["proposals"]).items())),
        "by_confidence": dict(sorted(Counter(p["confidence"] for p in proposals["proposals"]).items())),
        "decisions": dict(sorted(Counter(decided.values()).items())),
        "undecided_proposals": len(proposals["proposals"]) - len(decided),
        "pages_audit_pending": len(pending_pages),
    }


def check_against_snapshot(audit: ReferenceAudit, root: Path) -> list[str]:
    """Every proposal's span and context against the current scored text of its page in an operator snapshot."""

    from hocrgen.fetchers.wikisource import load_wikisource_snapshot, scored_page_reference

    _, _, pages = load_wikisource_snapshot(root)
    by_item = {f"wikisource_he_proofread:{page['source_item_id']}": page for page in pages}
    problems = []
    for item_id, page_entry in sorted(audit.pages.items()):
        page = by_item.get(item_id)
        if page is None:
            problems.append(f"{item_id}: not in the snapshot")
            continue
        scored = scored_page_reference(page, root)
        if not scored["scored"]:
            problems.append(f"{item_id}: no longer scored ({scored['reason']})")
            continue
        if text_sha256(scored["text"]) != page_entry["base_text_sha256"]:
            problems.append(f"{item_id}: the scored text changed since the audit")
            continue
        for proposal in audit.proposals.get(item_id, []):
            problems.extend(proposal_text_problems(proposal, scored["text"]))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--proposals", type=Path, default=DEFAULT_PROPOSALS)
    parser.add_argument("--decisions", type=Path, default=None,
                        help="reference_audit_decisions.v1 (default: the committed docs file, with the default proposals)")
    parser.add_argument("--snapshot-root", type=Path, default=None,
                        help="operator Wikisource snapshot: also check every span against the current scored text")
    args = parser.parse_args(argv)
    default_pair = args.proposals == DEFAULT_PROPOSALS and DEFAULT_DECISIONS.exists()
    decisions_path = args.decisions or (DEFAULT_DECISIONS if default_pair else None)
    proposals = load_reference_audit_proposals(args.proposals)
    decisions = load_reference_audit_decisions(decisions_path, proposals) if decisions_path is not None else None
    summary = audit_summary(proposals, decisions)
    if args.snapshot_root is not None:
        problems = check_against_snapshot(ReferenceAudit(proposals, decisions), args.snapshot_root)
        if problems:
            raise StageExecutionError("; ".join(problems[:10]))
        summary["spans_checked_against_snapshot"] = True
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
