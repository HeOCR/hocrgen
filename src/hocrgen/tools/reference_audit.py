"""E2d4: validate the reference audit files and summarise where the human review stands.

``python -m hocrgen.tools.reference_audit [--proposals P] [--decisions D] [--snapshot-root ROOT]`` validates
``reference_audit_proposals.v1`` and ``reference_audit_decisions.v1`` (by default the committed
``docs/reference_audit_proposals.json`` and ``docs/reference_audit_decisions.json``) and prints counts only: proposals
by category and confidence, decisions by value, and pages pending. With an operator ``--snapshot-root`` (a Wikisource
snapshot holding the audited pages) it also checks every proposal's span and context against the page's current
scored text, so a stale proposal is caught before a reviewer sees it. It never prints reference text.

``--export-dir OUT --page-images DIR`` (operator-only) writes an import bundle for a review app: ``OUT/proposals.json``
(the proposals, byte for byte), ``OUT/crops/<proposal_id>.jpg`` (each proposal's region with a margin, enlarged and
outlined, cut from ``DIR/<source_item_id>.jpg|png``: any render of the page in the page frame, for example a 1920 px
render of the pinned scan) and ``OUT/crops.json`` (``reference_audit_crops.v1``: per proposal the crop file, its
SHA-256 and size, the source image's SHA-256 and the crop box in source pixels). Crops are scan images: keep the
bundle out of git. Proposals already decided, by a human or by a rule, are left out of the bundle (``OUT/proposals.json``
is then the still-undecided subset, a valid ``reference_audit_proposals.v1``; ``crops.json`` counts what was skipped).

E2d4b:

- ``--add-decisions EXPORT`` merges the human decisions of a review-app export (``reference_audit_decisions.v1``) into
  ``--decisions`` (default: the committed file), validated, sorted by id, written as ``reference_audit_decisions.v2``.
- ``--rule-coverage --snapshot-root ROOT`` lists the still-undecided proposals that a reference rule
  (``hocrgen.reference_rules``) makes exactly on the page's scored text: proposal ids and counts, never text. With
  ``--write-rule-decisions`` it records them in ``--decisions`` as rule decisions (``checked_by: rule``, id
  ``rule:<rule>:<proposal_id>``, dated ``--decided-at``).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from hocrgen.core.errors import StageExecutionError
from hocrgen.reference_audit import (
    DECISIONS_SCHEMA,
    ReferenceAudit,
    load_reference_audit_decisions,
    load_reference_audit_proposals,
    merge_decisions,
    proposal_text_problems,
    rule_coverage,
    rule_decisions_for,
    text_sha256,
)

DOCS = Path(__file__).resolve().parents[3] / "docs"
DEFAULT_PROPOSALS = DOCS / "reference_audit_proposals.json"
DEFAULT_DECISIONS = DOCS / "reference_audit_decisions.json"
CROPS_SCHEMA = "reference_audit_crops.v1"


def _page_image(directory: Path, item_id: str) -> Path:
    slug = item_id.split(":", 1)[1]
    for suffix in (".jpg", ".jpeg", ".png"):
        if (directory / f"{slug}{suffix}").is_file():
            return directory / f"{slug}{suffix}"
    raise StageExecutionError(f"no page image for {item_id} in {directory.name}")


def undecided_proposals(proposals: dict[str, Any], decisions: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, int]]:
    """``proposals`` without the ones a human or a rule decided (a valid ``reference_audit_proposals.v1``: pages
    left with no proposal are dropped, ``proposal_count`` follows), and how many were skipped by whom."""

    by_whom: dict[str, str] = {}
    for decision in (decisions or {}).get("decisions") or []:
        by_whom.setdefault(decision["proposal_id"], decision["checked_by"])
    skipped = dict(sorted(Counter(by_whom[p["proposal_id"]] for p in proposals["proposals"]
                                  if p["proposal_id"] in by_whom).items()))
    if not skipped:
        return proposals, {}
    kept = [p for p in proposals["proposals"] if p["proposal_id"] not in by_whom]
    counts = Counter(p["item_id"] for p in kept)
    pages = [{**page, "proposal_count": counts[page["item_id"]]} for page in proposals["pages"] if counts[page["item_id"]]]
    if not pages:
        raise StageExecutionError("every proposal is decided; nothing to export")
    return {**proposals, "pages": pages, "proposals": kept}, skipped


def export_crops(proposals_path: Path, page_images: Path, out: Path, *, decisions: dict[str, Any] | None = None,
                 max_width: int = 760, max_scale: float = 2.2, quality: int = 80) -> dict[str, Any]:
    """Write ``proposals.json``, one enlarged, outlined crop per proposal and ``crops.json`` to ``out`` (new or empty).

    Proposals with a human or rule decision in ``decisions`` are left out; with none decided, ``proposals.json`` is
    the input byte for byte."""

    from PIL import Image, ImageDraw

    proposals, skipped = undecided_proposals(load_reference_audit_proposals(proposals_path), decisions)
    if out.exists() and any(out.iterdir()):
        raise StageExecutionError(f"{out.name} must be new or empty")
    (out / "crops").mkdir(parents=True, exist_ok=True)
    if skipped:
        (out / "proposals.json").write_text(json.dumps(proposals, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    else:
        (out / "proposals.json").write_bytes(Path(proposals_path).read_bytes())
    entries, opened = [], {}
    for proposal in proposals["proposals"]:
        item_id = proposal["item_id"]
        if item_id not in opened:
            path = _page_image(page_images, item_id)
            opened[item_id] = (Image.open(path).convert("RGB"), hashlib.sha256(path.read_bytes()).hexdigest())
        image, image_sha = opened[item_id]
        width, height = image.size
        box = proposal["region"]["box_normalized"]
        x0, y0, x1, y1 = box[0] * width, box[1] * height, box[2] * width, box[3] * height
        mx, my = max(0.03 * width, (x1 - x0) * 0.35), max(0.016 * height, (y1 - y0) * 0.6)
        crop_box = [int(max(0, x0 - mx)), int(max(0, y0 - my)), int(min(width, x1 + mx)), int(min(height, y1 + my))]
        crop = image.crop(tuple(crop_box))
        scale = min(max_scale, max_width / max(1, crop.width))
        crop = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale))), Image.LANCZOS)
        ImageDraw.Draw(crop).rectangle([(x0 - crop_box[0]) * scale, (y0 - crop_box[1]) * scale,
                                        (x1 - crop_box[0]) * scale, (y1 - crop_box[1]) * scale], outline=(220, 30, 30), width=2)
        name = f"crops/{proposal['proposal_id']}.jpg"
        crop.save(out / name, format="JPEG", quality=quality)
        entries.append({"proposal_id": proposal["proposal_id"], "item_id": item_id, "path": name,
                        "sha256": hashlib.sha256((out / name).read_bytes()).hexdigest(),
                        "width": crop.width, "height": crop.height, "source_image_sha256": image_sha,
                        "source_image_size": [width, height], "crop_box_px": crop_box,
                        "region_box_normalized": box, "coordinate_frame": "page"})
    index = {"schema_version": CROPS_SCHEMA, "audit_id": proposals["audit_id"], "proposals_file": "proposals.json",
             "proposals_sha256": hashlib.sha256((out / "proposals.json").read_bytes()).hexdigest(),
             "note": "scan crops for human review; operator-only, never committed", "crops": entries}
    if skipped:
        index["skipped_decided"] = skipped
        index["source_proposals_sha256"] = hashlib.sha256(Path(proposals_path).read_bytes()).hexdigest()
    (out / "crops.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"crops": len(entries), "pages": len(opened), **({"skipped_decided": skipped} if skipped else {})}


def audit_summary(proposals: dict[str, Any], decisions: dict[str, Any] | None) -> dict[str, Any]:
    """Counts only: proposals by category and confidence, decisions by value, pages with undecided proposals."""

    all_decisions = (decisions or {}).get("decisions") or []
    decided = {d["proposal_id"] for d in all_decisions}
    pending_pages = {p["item_id"] for p in proposals["proposals"] if p["proposal_id"] not in decided}
    human = [d for d in all_decisions if d["checked_by"] == "human"]
    per_proposal = Counter(d["proposal_id"] for d in human)
    return {
        "audit_id": proposals["audit_id"],
        "pages": len(proposals["pages"]),
        "pages_audited_no_findings": sum(1 for p in proposals["pages"] if p["audit_status"] == "audited_no_findings"),
        "text_not_on_page_candidates": sum(1 for p in proposals["pages"] if p.get("text_not_on_page_candidate")),
        "proposals": len(proposals["proposals"]),
        "by_category": dict(sorted(Counter(p["category"] for p in proposals["proposals"]).items())),
        "by_confidence": dict(sorted(Counter(p["confidence"] for p in proposals["proposals"]).items())),
        "decisions": dict(sorted(Counter(d["decision"] for d in human).items())),
        "rule_decisions": dict(sorted(Counter(d["rule"] for d in all_decisions if d["checked_by"] == "rule").items())),
        "reviewers": len({d["reviewer"] for d in human}),
        "proposals_by_reviewer_count": dict(sorted(Counter(per_proposal.values()).items())),
        "human_decided_proposals": len(per_proposal),
        "undecided_proposals": len(proposals["proposals"]) - len(decided),
        "pages_audit_pending": len(pending_pages),
    }


def scored_texts(audit: ReferenceAudit, root: Path) -> tuple[dict[str, str], list[str]]:
    """Item id -> the current scored (unaudited) text of every audited page in an operator snapshot, and problems."""

    from hocrgen.fetchers.wikisource import load_wikisource_snapshot, scored_page_reference

    _, _, pages = load_wikisource_snapshot(root)
    by_item = {f"wikisource_he_proofread:{page['source_item_id']}": page for page in pages}
    texts, problems = {}, []
    for item_id in sorted(audit.pages):
        page = by_item.get(item_id)
        if page is None:
            problems.append(f"{item_id}: not in the snapshot")
            continue
        scored = scored_page_reference(page, root)
        if not scored["scored"]:
            problems.append(f"{item_id}: no longer scored ({scored['reason']})")
            continue
        texts[item_id] = scored["text"]
    return texts, problems


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
    parser.add_argument("--min-reviewers", type=int, default=1,
                        help="agreeing reviewers a proposal needs before it applies (default 1)")
    parser.add_argument("--export-dir", type=Path, default=None,
                        help="operator: write proposals.json, crops/ and crops.json for a review app (needs --page-images)")
    parser.add_argument("--page-images", type=Path, default=None,
                        help="directory of page renders named <source_item_id>.jpg|png, in the page frame")
    parser.add_argument("--add-decisions", type=Path, default=None,
                        help="E2d4b: merge this review-app export's decisions into --decisions (written in place)")
    parser.add_argument("--rule-coverage", action="store_true",
                        help="E2d4b: list undecided proposals a reference rule makes exactly (needs --snapshot-root)")
    parser.add_argument("--write-rule-decisions", action="store_true",
                        help="E2d4b: with --rule-coverage, record them in --decisions as rule decisions (in place)")
    parser.add_argument("--decided-at", default=_dt.date.today().isoformat(),
                        help="the date rule decisions record (default today)")
    args = parser.parse_args(argv)
    if (args.export_dir is None) != (args.page_images is None):
        raise StageExecutionError("--export-dir and --page-images go together")
    if args.rule_coverage and args.snapshot_root is None:
        raise StageExecutionError("--rule-coverage needs --snapshot-root (the pages' scored text)")
    if args.write_rule_decisions and not args.rule_coverage:
        raise StageExecutionError("--write-rule-decisions needs --rule-coverage")
    default_pair = args.proposals == DEFAULT_PROPOSALS and DEFAULT_DECISIONS.exists()
    decisions_path = args.decisions or (DEFAULT_DECISIONS if default_pair else None)
    if (args.add_decisions is not None or args.write_rule_decisions) and decisions_path is None:
        raise StageExecutionError("writing decisions needs --decisions")
    proposals = load_reference_audit_proposals(args.proposals)
    decisions = load_reference_audit_decisions(decisions_path, proposals) if decisions_path is not None else None
    if args.add_decisions is not None:
        incoming = json.loads(args.add_decisions.read_text(encoding="utf-8"))
        before = len(decisions["decisions"])
        decisions = merge_decisions(decisions, incoming, proposals)
        _write_decisions(decisions_path, decisions)
        added = len(decisions["decisions"]) - before
    summary = audit_summary(proposals, decisions)
    if args.add_decisions is not None:
        summary["decisions_added"] = added
    if args.snapshot_root is not None:
        problems = check_against_snapshot(ReferenceAudit(proposals, decisions, min_reviewers=args.min_reviewers),
                                          args.snapshot_root)
        if problems:
            raise StageExecutionError("; ".join(problems[:10]))
        summary["spans_checked_against_snapshot"] = True
    if args.rule_coverage:
        audit = ReferenceAudit(proposals, decisions, min_reviewers=args.min_reviewers)
        texts, problems = scored_texts(audit, args.snapshot_root)
        if problems:
            raise StageExecutionError("; ".join(problems[:10]))
        covered = rule_coverage(audit, texts)
        summary["rule_coverage"] = {rule: {"proposals": len(found), "proposal_ids": [p["proposal_id"] for p in found],
                                           "by_category": dict(sorted(Counter(p["category"] for p in found).items()))}
                                    for rule, found in covered.items()}
        if args.write_rule_decisions:
            new = [d for rule, found in covered.items() for d in rule_decisions_for(found, rule, args.decided_at)]
            decisions = merge_decisions(decisions, {**decisions, "schema_version": DECISIONS_SCHEMA, "decisions": new},
                                        proposals)
            _write_decisions(decisions_path, decisions)
            summary["rule_decisions_written"] = len(new)
            summary.update({k: v for k, v in audit_summary(proposals, decisions).items()
                            if k in ("rule_decisions", "undecided_proposals", "pages_audit_pending")})
    if args.export_dir is not None:
        summary["export"] = export_crops(args.proposals, args.page_images, args.export_dir, decisions=decisions)
    print(json.dumps(summary, indent=2))
    return 0


def _write_decisions(path: Path, decisions: dict[str, Any]) -> None:
    path.write_text(json.dumps(decisions, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
