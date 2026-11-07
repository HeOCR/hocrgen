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
bundle out of git.
"""
from __future__ import annotations

import argparse
import hashlib
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
CROPS_SCHEMA = "reference_audit_crops.v1"


def _page_image(directory: Path, item_id: str) -> Path:
    slug = item_id.split(":", 1)[1]
    for suffix in (".jpg", ".jpeg", ".png"):
        if (directory / f"{slug}{suffix}").is_file():
            return directory / f"{slug}{suffix}"
    raise StageExecutionError(f"no page image for {item_id} in {directory.name}")


def export_crops(proposals_path: Path, page_images: Path, out: Path, *, max_width: int = 760, max_scale: float = 2.2,
                 quality: int = 80) -> dict[str, Any]:
    """Write ``proposals.json``, one enlarged, outlined crop per proposal and ``crops.json`` to ``out`` (new or empty)."""

    from PIL import Image, ImageDraw

    proposals = load_reference_audit_proposals(proposals_path)
    if out.exists() and any(out.iterdir()):
        raise StageExecutionError(f"{out.name} must be new or empty")
    (out / "crops").mkdir(parents=True, exist_ok=True)
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
    (out / "crops.json").write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"crops": len(entries), "pages": len(opened)}


def audit_summary(proposals: dict[str, Any], decisions: dict[str, Any] | None) -> dict[str, Any]:
    """Counts only: proposals by category and confidence, decisions by value, pages with undecided proposals."""

    all_decisions = (decisions or {}).get("decisions") or []
    decided = {d["proposal_id"] for d in all_decisions}
    pending_pages = {p["item_id"] for p in proposals["proposals"] if p["proposal_id"] not in decided}
    per_proposal = Counter(d["proposal_id"] for d in all_decisions)
    return {
        "audit_id": proposals["audit_id"],
        "pages": len(proposals["pages"]),
        "pages_audited_no_findings": sum(1 for p in proposals["pages"] if p["audit_status"] == "audited_no_findings"),
        "text_not_on_page_candidates": sum(1 for p in proposals["pages"] if p.get("text_not_on_page_candidate")),
        "proposals": len(proposals["proposals"]),
        "by_category": dict(sorted(Counter(p["category"] for p in proposals["proposals"]).items())),
        "by_confidence": dict(sorted(Counter(p["confidence"] for p in proposals["proposals"]).items())),
        "decisions": dict(sorted(Counter(d["decision"] for d in all_decisions).items())),
        "reviewers": len({d["reviewer"] for d in all_decisions}),
        "proposals_by_reviewer_count": dict(sorted(Counter(per_proposal.values()).items())),
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
    parser.add_argument("--min-reviewers", type=int, default=1,
                        help="agreeing reviewers a proposal needs before it applies (default 1)")
    parser.add_argument("--export-dir", type=Path, default=None,
                        help="operator: write proposals.json, crops/ and crops.json for a review app (needs --page-images)")
    parser.add_argument("--page-images", type=Path, default=None,
                        help="directory of page renders named <source_item_id>.jpg|png, in the page frame")
    args = parser.parse_args(argv)
    if (args.export_dir is None) != (args.page_images is None):
        raise StageExecutionError("--export-dir and --page-images go together")
    default_pair = args.proposals == DEFAULT_PROPOSALS and DEFAULT_DECISIONS.exists()
    decisions_path = args.decisions or (DEFAULT_DECISIONS if default_pair else None)
    proposals = load_reference_audit_proposals(args.proposals)
    decisions = load_reference_audit_decisions(decisions_path, proposals) if decisions_path is not None else None
    summary = audit_summary(proposals, decisions)
    if args.snapshot_root is not None:
        problems = check_against_snapshot(ReferenceAudit(proposals, decisions, min_reviewers=args.min_reviewers),
                                          args.snapshot_root)
        if problems:
            raise StageExecutionError("; ".join(problems[:10]))
        summary["spans_checked_against_snapshot"] = True
    if args.export_dir is not None:
        summary["export"] = export_crops(args.proposals, args.page_images, args.export_dir)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
