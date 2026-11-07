"""E2d2: operator-only real printed evaluation references from a pinned Hebrew Wikisource snapshot.

Converts the pages of a Wikisource snapshot root (the F8b page-record shape) that pass every source gate into
evaluation inputs for ``hocrgen evaluate-references``:

- **Quality 4, two distinct named editors, text unchanged since validation** (maintainer decision 2, 2026-11-06):
  ``benchmark_transcription_reference.v1`` records with ``review.status: adjudicated``, listed in a
  ``benchmark_reference_manifest.v1`` with ``modality: printed`` and the page's ``reference_normalization`` facts.
  Each page also gets an adjudication record that names the two Wikisource editors from the page history as the
  attesting humans. The adjudicating act is the validator's quality-4 edit; no agent attests, and nothing is edited
  on Wikisource.
- **Quality 3** (one named proofreader, ``single_reviewer``): not adjudicated, so never scored. They are written as an
  ``--unreviewed-texts`` JSONL with ``reference_origin: wikisource_single_reviewer``, a clearly labelled diagnostic
  stratum.
- An ``--asset-index`` maps every item to the sha256 of the image it pairs with: the page render, or for a
  ``partial_page`` page its decision-12 crop (F8b4).
- **Text the scan does not show** (F8b7 ``excluded_spans``, ``illegible_on_scan``) is honoured on both strata: an
  adjudicated reference carries each span as ``illegible`` / ``exclude_primary``, which scoring excludes, and a
  single-reviewer text has the span's characters removed. The span's page boxes are listed with the item's image, so
  an operator can mask them on the scored image.

The text is the post-F8b7 pair text (``page_plain_text``: unprinted footnotes dropped, stand-ins mapped).

Pages can be held out by item id (for example after a training-text leakage check); each is listed with its reason.

With a release ``split_manifest.json`` (F8g: whole source and work groups are assigned to one split), every item records
the release split its page belongs to (``train``, ``validation``, ``test`` or ``not_in_release``) and its split group;
adjudicated manifest items carry it as ``benchmark_split``. A page in the release ``train`` split ships as training
data, so it must never be presented as held-out evaluation.

**Validated-revision text (E2d3b).** With ``--validated-revisions`` (a ``wikisource_validated_revisions`` output) and
``--validated-text-checks``, a quality-4 page rejected only because its text changed after validation is scored on its
text *as of the validating revision*: exactly what the two editors attested; later, unvalidated edits are not used.
The page's F8b7 steps are re-applied to that text (stand-ins; unprinted notes and excluded spans as the check re-pins
them), and the item records ``reference_text_revision: validating`` and its difference from the latest text. A page
is used only when an agent or human check of the scan found the validated text agrees with it; a page whose later
edits fixed a real transcription error is ``validated_text_disagrees_with_scan`` and is left out, as is a page with no
check. A page whose validated and latest texts differ only in line or paragraph whitespace is used whatever its
check's verdict (E2d3c): a paragraph break is layout, not text. Every other adjudicated item records
``reference_text_revision: latest``.

Which pages are scored, and on which text, is ``hocrgen.fetchers.wikisource.scored_page_reference`` (E2d3e): the release
split's reference weight uses the same function, so the two count the same pages. A snapshot whose pages carry
``validated_revision`` and ``validated_text_check`` (tranche v5) needs neither flag.

``bootstrap_clusters.json`` (``hocrgen_bootstrap_clusters.v1``, E2d3) maps every written item to its Wikisource Index,
the book-level unit (and the release split group), for ``evaluate-references --bootstrap-clusters``.
Everything this writes holds CC BY-SA 4.0 Wikisource text and stays operator-only. ``benchmark_v1`` is untouched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.wikisource import (
    _FROM_PAGE,
    TEXT_LICENSE,
    scored_page_reference,
    load_validated_text_checks,
    reference_record_from_text,
    validated_revision_attestation,
    load_wikisource_snapshot,
    page_attestation,
    page_conversion,
    page_exclusion_reasons,
    page_needs_crop,
    page_permalink,
    page_plain_text,
    page_reference_record,
    reference_normalization,
)
from hocrgen.manifests.models import BenchmarkReferenceManifestRecord, BenchmarkTranscriptionReferenceRecord
from hocrgen.parsers.wikitext import WIKITEXT_NORMALIZATION_VERSION
from hocrgen.reference_runs import BOOTSTRAP_CLUSTERS_SCHEMA
from hocrgen.tools.wikisource_validated_revisions import load_validated_revisions

SOURCE_ID = "wikisource_he_proofread"
ADJUDICATION_RECORD_SCHEMA = "wikisource_adjudication_record.v1"
EVAL_SET_SCHEMA = "wikisource_eval_reference_set.v1"
SINGLE_REVIEWER_ORIGIN = "wikisource_single_reviewer"
MODALITY = "printed"
DOCUMENT_TYPE = "printed_book_page"
RELEASE_SPLITS = ("train", "validation", "test")
CLUSTER_KEY = "wikisource_index"
NOT_IN_RELEASE = "not_in_release"
ADJUDICATION_RULE = (
    "maintainer decision 2 (2026-11-06): a Wikisource quality-4 page, validated by a second named human editor "
    "with its text unchanged since validation, counts as human-attested and adjudication-eligible; the validator's "
    "quality-4 edit is the adjudicating act"
)


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def scored_image(page: Mapping[str, Any]) -> dict[str, Any]:
    """The image a page's text pairs with: its decision-12 crop for a partial page, else the page image."""

    image = page["image"]
    hidden = [region for span in ((page.get("excluded_spans") or {}).get("spans") or [])
              for region in span.get("regions_normalized") or []]
    extra = {"excluded_regions_normalized_page_frame": hidden} if hidden else {}
    if page_needs_crop(page):
        crop = page["crop"]
        return {"kind": "crop", "path": crop["asset"]["path"], "sha256": crop["asset"]["sha256"],
                "width": crop["asset"]["width"], "height": crop["asset"]["height"],
                "crop_of_page": image["sha256"], "box_normalized": crop["box_normalized"],
                **({"regions_normalized": crop["regions_normalized"]} if crop.get("regions_normalized") else {}),
                "crop_method": crop.get("method"), **extra}
    return {"kind": "page", "path": image["path"], "sha256": image["sha256"], "width": image["width"],
            "height": image["height"], **extra}


def single_reviewer_text(page: Mapping[str, Any], root: Path) -> tuple[str, int]:
    """A quality-3 page's pair text with every excluded span (F8b7) removed; returns the text and the span count."""

    text = page_plain_text(dict(page), root)
    spans = sorted(((page.get("excluded_spans") or {}).get("spans") or []), key=lambda span: span["start"], reverse=True)
    for span in spans:
        text = text[:span["start"]] + text[span["end"]:]
    return text, len(spans)


def _manifest_facts(facts: Mapping[str, Any]) -> dict[str, Any]:
    """The footnote facts a manifest item carries; excluded spans travel in the reference record's spans instead."""

    return {"footnote_marker_style": facts["footnote_marker_style"], "footnote_count": facts["footnote_count"]}


def adjudicated_reference(page: Mapping[str, Any], root: Path, *, source_id: str = SOURCE_ID,
                          validated: Mapping[str, Any] | None = None,
                          ) -> tuple[BenchmarkTranscriptionReferenceRecord, dict[str, Any]]:
    """One quality-4 page as an adjudicated reference plus its adjudication record (two named Wikisource editors).

    With ``validated`` (``{"text", "record", "check", "diff"}``, E2d3b) the reference is the page's text as of its
    validating revision instead of the latest one.
    """

    if validated is None:
        record = page_reference_record(source_id, dict(page), root)  # raises unless adjudication-eligible
        attestation = page_attestation(dict(page))
        revision_id, text_sha256 = page["revision_id"], page["text_sha256"]
        basis = f"Wikisource quality 4 at revision {revision_id}"
    else:
        attestation = validated_revision_attestation(dict(page))
        if not attestation["adjudication_eligible"]:
            raise StageExecutionError(f"{page['source_item_id']} has no attested validating-revision text")
        revision_id = validated["record"]["validating_revision_id"]
        spans = (validated["check"].get("excluded_spans") or None)
        record = reference_record_from_text(source_id, {**page, "excluded_spans": spans}, validated["text"], attestation, revision_id)
        text_sha256 = _sha256(validated["text"])
        basis = (f"Wikisource quality 4, text as of the validating revision {revision_id} (latest {page['revision_id']}; "
                 f"{validated['diff']['text_changing_edits_after_validation']} later text-changing edits not used)")
    proofreader, validator = attestation["proofreader"], attestation["validator"]
    reviewers = [f"wikisource:{proofreader['user']}", f"wikisource:{validator['user']}"]
    reason = (f"{basis}: proofread by {reviewers[0]} "
              f"(revision {proofreader['revision_id']}), validated by {reviewers[1]} (revision {validator['revision_id']}); "
              f"adjudicated under maintainer decision 2; {WIKITEXT_NORMALIZATION_VERSION}; lines are rendered paragraphs")
    adjudicated = record.model_copy(update={"review": record.review.model_copy(update={
        "status": "adjudicated", "reviewers": reviewers, "adjudicator": reviewers[1],
        "adjudicated_at": validator["timestamp"], "change_reason": reason})})
    BenchmarkTranscriptionReferenceRecord.model_validate(adjudicated.model_dump(mode="json"))
    adjudication = {
        "schema_version": ADJUDICATION_RECORD_SCHEMA,
        "item_id": record.item_id,
        "page_title": page["page_title"],
        "page_permalink": page_permalink({**page, "revision_id": revision_id}),
        "page_revision_id": revision_id,
        "text_sha256": text_sha256,
        "quality": 4,
        "rule": ADJUDICATION_RULE,
        "attesting_humans": [
            {"role": "proofreader", "wiki": "he.wikisource.org", **proofreader},
            {"role": "validator", "wiki": "he.wikisource.org", **validator},
        ],
        "adjudicator": {"role": "validator", "user": validator["user"], "user_id": validator["user_id"]},
        "agent_attestation": None,
        "conversion": {"by": "hocrgen.tools.wikisource_eval_references", "text_normalization": WIKITEXT_NORMALIZATION_VERSION,
                       "note": "a mechanical conversion of the pinned revision; the converter attests nothing"},
        "text_license": TEXT_LICENSE,
    }
    if validated is not None:
        check = validated["check"]
        adjudication["reference_text_revision"] = "validating"
        adjudication["latest_revision_id"] = page["revision_id"]
        adjudication["validated_wikitext_sha256"] = validated["record"]["wikitext_sha256"]
        adjudication["diff_vs_latest"] = dict(validated["diff"])
        adjudication["validated_text_check"] = {key: check[key] for key in ("verdict", "checked_by", "checker", "checked_at", "method")}
        adjudication["validated_text_accepted_by"] = validated.get("accepted_by", "check_verdict")
    return adjudicated, adjudication


def load_release_splits(path: Path) -> dict[str, dict[str, Any]]:
    """Item id -> ``{split, split_group_id, split_constraint}`` from a release ``split_manifest.json``."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    splits = {}
    for item in payload.get("items", []):
        if item.get("split") not in RELEASE_SPLITS:
            raise StageExecutionError(f"split manifest item {item.get('item_id')} has an unknown split")
        splits[item["item_id"]] = {"split": item["split"], "split_group_id": item.get("split_group_id"),
                                   "split_constraint": item.get("split_constraint")}
    return splits


def write_eval_reference_set(
    root: Path, output_dir: Path, *, source_id: str = SOURCE_ID, reference_manifest_id: str,
    held_out: Mapping[str, str] | None = None, release_splits: Mapping[str, Mapping[str, Any]] | None = None,
    include: set[str] | None = None, validated_revisions: Path | None = None, validated_text_checks: Path | None = None,
) -> dict[str, Any]:
    """Write the adjudicated printed reference manifest, the single-reviewer texts and the asset index.

    ``held_out`` maps item ids to a reason (for example a training-text overlap); those pages are listed, never
    written. Returns the ``wikisource_eval_reference_set.v1`` summary, also written as ``eval_set.json``.
    """

    if (validated_revisions is None) != (validated_text_checks is None):
        raise StageExecutionError("--validated-revisions and --validated-text-checks go together")
    revisions = load_validated_revisions(validated_revisions) if validated_revisions is not None else None
    checks = load_validated_text_checks(validated_text_checks) if validated_text_checks is not None else {}
    _, indexes, pages = load_wikisource_snapshot(root)
    held_out = dict(held_out or {})
    known = {f"{source_id}:{page['source_item_id']}" for page in pages}
    unknown = sorted((set(held_out) | set(include or ())) - known)
    if unknown:
        raise StageExecutionError(f"held-out items not in the snapshot: {unknown}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise StageExecutionError(f"{output_dir.name} must be new or empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_items, single_reviewer, asset_index, items, skipped, excluded = [], [], [], [], {}, []
    validated_excluded: list[dict[str, Any]] = []
    considered = revisions is not None
    masked_spans = 0
    for page in sorted(pages, key=lambda record: record["source_item_id"]):
        item_id = f"{source_id}:{page['source_item_id']}"
        if include is not None and item_id not in include:
            continue
        reasons = page_exclusion_reasons(page, indexes, root)
        if reasons:
            skipped[reasons[0]] = skipped.get(reasons[0], 0) + 1
            continue
        validated = None
        if page["quality"] == 4:
            # E2d3e: the same rule as the split stage's reference weight (``scored_page_reference``).
            supplied = (revisions.get(item_id), checks.get(page["page_title"])) if revisions is not None else _FROM_PAGE
            scored = scored_page_reference(page, root, validation=supplied)
            if scored["validation_considered"]:
                considered = True
            if not scored["scored"]:
                if scored["validation_considered"]:
                    validated_excluded.append({"item_id": item_id, "reason": scored["reason"]})
                skipped[scored["reason"]] = skipped.get(scored["reason"], 0) + 1
                continue
            validated = scored["validated"]
        stratum = "adjudicated" if page["quality"] == 4 else "single_reviewer"
        if item_id in held_out:
            excluded.append({"item_id": item_id, "stratum": stratum, "reason": held_out[item_id]})
            continue
        image = scored_image(page)
        if validated is None:
            facts = reference_normalization(page_conversion(page, root), page)
        else:
            spans = validated["check"].get("excluded_spans")
            facts = reference_normalization(validated["conversion"], {**page, "excluded_spans": spans})
        entry = {"item_id": item_id, "stratum": stratum, "index_key": page["index_key"], "quality": page["quality"],
                 "page_title": page["page_title"], "page_revision_id": page["revision_id"],
                 "transcription_coverage": page["transcription_coverage"], "image": image,
                 "reference_normalization": facts}
        split = None
        if release_splits is not None:
            assigned = release_splits.get(item_id)
            split = assigned["split"] if assigned else None
            entry["release_split"] = split or NOT_IN_RELEASE
            entry["release_split_group_id"] = assigned.get("split_group_id") if assigned else None
            entry["release_split_constraint"] = assigned.get("split_constraint") if assigned else None
        if stratum == "adjudicated":
            entry["reference_text_revision"] = "latest" if validated is None else "validating"
            if validated is not None:
                entry["reference_text_revision_id"] = validated["record"]["validating_revision_id"]
                entry["latest_revision_id"] = page["revision_id"]
                entry["diff_vs_latest"] = dict(validated["diff"])
                entry["validated_text_accepted_by"] = validated["accepted_by"]
            record, adjudication = adjudicated_reference(page, root, source_id=source_id, validated=validated)
            base = f"references/{page['source_item_id']}"
            payload = _dump(record.model_dump(mode="json"))
            (output_dir / base).mkdir(parents=True)
            (output_dir / base / "transcription.json").write_text(payload, encoding="utf-8")
            (output_dir / base / "adjudication.json").write_text(_dump(adjudication), encoding="utf-8")
            manifest_items.append({
                "reference_id": f"{reference_manifest_id}:{page['source_item_id']}",
                "item_id": item_id, "source_id": source_id, "source_item_id": page["source_item_id"],
                "benchmark_split": split, "visibility": "hidden_reference", "public_reference_status": "adjudicated",
                "transcription_reference": {"path": f"{base}/transcription.json",
                                            "schema_version": "benchmark_transcription_reference.v1",
                                            "sha256": _sha256(payload)},
                "layout_label_references": [], "reviewers": record.review.reviewers,
                "adjudication_status": "adjudicated", "correction_of": None, "superseded_by": None,
                "change_reason": f"E2d2 real printed reference: {record.review.change_reason}",
                "modality": MODALITY,
                "reference_normalization": _manifest_facts(facts),
            })
            masked_spans += len(record.spans)
            entry["adjudication_record"] = f"{base}/adjudication.json"
        else:
            text, count = single_reviewer_text(page, root)
            masked_spans += count
            single_reviewer.append({
                "item_id": item_id, "text": text, "reference_origin": SINGLE_REVIEWER_ORIGIN,
                "modality": MODALITY, "source_id": source_id, "document_type": DOCUMENT_TYPE,
                "language_script": "he-Hebr",
                **({"release_split": entry["release_split"]} if release_splits is not None else {}),
            })
        asset_index.append({"item_id": item_id, "page_sha256": [image["sha256"]]})
        items.append(entry)
    manifest = {
        "schema_version": "benchmark_reference_manifest.v1",
        "benchmark_id": "e2d_real_printed",
        "reference_manifest_id": reference_manifest_id,
        "release_id": None,
        "reference_contracts": {"transcription": "benchmark_transcription_reference.v1",
                                "layout": "benchmark_layout_reference.v1"},
        "items": manifest_items,
    }
    BenchmarkReferenceManifestRecord.model_validate(manifest)
    (output_dir / "reference_manifest.json").write_text(_dump(manifest), encoding="utf-8")
    with (output_dir / "single_reviewer_texts.jsonl").open("w", encoding="utf-8") as handle:
        for line in single_reviewer:
            handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    (output_dir / "asset_index.json").write_text(_dump({"items": asset_index}), encoding="utf-8")
    (output_dir / "bootstrap_clusters.json").write_text(_dump({
        "schema_version": BOOTSTRAP_CLUSTERS_SCHEMA, "cluster_key": CLUSTER_KEY,
        "clusters": {entry["item_id"]: entry["index_key"] for entry in items}}), encoding="utf-8")
    split_counts = None
    if release_splits is not None:
        split_counts = {}
        for entry in items:
            key = f"{entry['stratum']}:{entry['release_split']}"
            split_counts[key] = split_counts.get(key, 0) + 1
    summary = {
        "schema_version": EVAL_SET_SCHEMA,
        "source_id": source_id,
        "reference_manifest_id": reference_manifest_id,
        "modality": MODALITY,
        "text_license": TEXT_LICENSE,
        "operator_only": True,
        "counts": {"adjudicated": len(manifest_items), "single_reviewer": len(single_reviewer),
                   "held_out": len(excluded), "skipped": dict(sorted(skipped.items())),
                   "excluded_spans_honoured": masked_spans},
        "release_split_counts": dict(sorted(split_counts.items())) if split_counts is not None else None,
        "release_split_policy": ("a page in the release train split ships as training data and is never held-out "
                                 "evaluation; not_in_release pages were dropped before the split stage")
        if split_counts is not None else None,
        "held_out": excluded,
        "items": items,
    }
    if considered:
        summary["counts"]["adjudicated_validating_revision"] = sum(
            1 for entry in items if entry.get("reference_text_revision") == "validating")
        summary["validated_text_excluded"] = validated_excluded
    (output_dir / "eval_set.json").write_text(_dump(summary), encoding="utf-8")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("snapshot_root", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--reference-manifest-id", default="e2d2_wikisource_printed_v1")
    parser.add_argument("--hold-out", type=Path, default=None,
                        help="JSON {item_id: reason} of pages to leave out (for example training-text overlap)")
    parser.add_argument("--items", type=Path, default=None,
                        help="JSON list of item ids to convert (default: every page that passes the gates)")
    parser.add_argument("--validated-revisions", type=Path, default=None,
                        help="E2d3b: a wikisource_validated_revisions output; score quality-4 pages changed after "
                             "validation on their validating-revision text (needs --validated-text-checks)")
    parser.add_argument("--validated-text-checks", type=Path, default=None,
                        help="E2d3b: wikisource_validated_text_checks.v1 (docs/wikisource_validated_text_checks.json)")
    parser.add_argument("--split-manifest", type=Path, default=None,
                        help="A release split_manifest.json: record each page's release split (F8g group-whole splits)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    held_out = json.loads(args.hold_out.read_text(encoding="utf-8")) if args.hold_out else None
    splits = load_release_splits(args.split_manifest) if args.split_manifest else None
    include = set(json.loads(args.items.read_text(encoding="utf-8"))) if args.items else None
    summary = write_eval_reference_set(args.snapshot_root, args.output_dir, reference_manifest_id=args.reference_manifest_id,
                                       held_out=held_out, release_splits=splits, include=include,
                                       validated_revisions=args.validated_revisions,
                                       validated_text_checks=args.validated_text_checks)
    print(json.dumps({"counts": summary["counts"], "release_split_counts": summary["release_split_counts"]},
                     indent=2))  # counts only, never text
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
