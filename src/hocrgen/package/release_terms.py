"""Per-item release terms, paired-text export and the release NOTICE (F8g).

Every exported real item carries a typed ``release_terms`` block taken from its own metadata and checked against
its source's ``real_source_contract.yaml`` terms: the licence, attribution, share-alike, the evaluation scope
(YidTakNL ``character_level_only``; BGU Pinkas per line; full Hebrew elsewhere), and the rendered-not-scan flag
(Reshumot). An item whose metadata cannot carry its source's terms stops the export: a scope marker is never
dropped on the way out.

The human-made text paired with an item (Wikisource page text, YidTakNL page text, BGU Pinkas PAGE XML, Reshumot
embedded text) ships next to the image, verified against the checksum pinned by its source snapshot.
"""

from __future__ import annotations

import gzip
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from hocrgen.config.models import (
    RealSourceContract,
    RealSourceContractEntry,
    RealSourceEvaluationScope,
    RealSourcePromotion,
)
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import ExportedTextRecord, ItemReleaseTermsRecord

ATTRIBUTION_MANIFEST_SCHEMA = "hocrgen_attribution_manifest.v1"
CHARACTER_LEVEL_EXCLUSIONS = {"word_level", "language_level_hebrew"}


@dataclass(frozen=True)
class PairedText:
    path: Path
    content: bytes
    media_type: str
    role: str
    sha256: str
    release_name: str


def item_release_terms(item: Any, contract: RealSourceContract | None) -> ItemReleaseTermsRecord:
    """The release terms of one item, validated against its source's contract terms when the source has an entry."""

    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    entry = contract.entry(item.source_id) if contract is not None else None
    classification = getattr(item.rights_classification, "value", item.rights_classification)
    usage_scope = metadata.get("usage_scope") if isinstance(metadata.get("usage_scope"), dict) else {}
    attribution_text = metadata.get("attribution_text") or metadata.get("text_attribution")
    terms: dict[str, Any] = {
        "source_id": item.source_id,
        "licence": item.normalized_license,
        "rights_classification": classification,
        "attribution_required": classification in {"open_with_attribution", "sharealike"},
        "attribution_text": attribution_text,
        "share_alike": classification == "sharealike",
        "text_licence": metadata.get("text_license") or (item.normalized_license if metadata.get("text_reference") else None),
        "evaluation_scope": metadata.get("evaluation_scope") or usage_scope.get("evaluation_scope"),
        "allowed_uses": list(usage_scope.get("allowed_uses") or []),
        "excluded_evaluations": list(usage_scope.get("excluded_evaluations") or []),
        "line_scope_summary": metadata.get("line_scope_summary"),
        "rendered_not_scan": metadata.get("is_scan") is False,
        "scope_decision": usage_scope.get("decision"),
        "contract_id": contract.contract_id if entry is not None else None,
    }
    if entry is not None:
        terms = _apply_contract_terms(item, entry, terms)
    return ItemReleaseTermsRecord.model_validate(terms)


def _apply_contract_terms(item: Any, entry: RealSourceContractEntry, terms: dict[str, Any]) -> dict[str, Any]:
    expected = entry.release_terms
    problems: list[str] = []
    if entry.promotion == RealSourcePromotion.not_promoted:
        problems.append("source_not_promoted")
    if terms["licence"] != expected.licence:
        problems.append(f"licence {terms['licence']} != {expected.licence}")
    if expected.attribution_required and not terms["attribution_text"]:
        problems.append("attribution_text_missing")
    if expected.share_alike and not terms["share_alike"]:
        problems.append("share_alike_missing")
    scope = expected.evaluation_scope
    if scope == RealSourceEvaluationScope.character_level_only:
        if terms["evaluation_scope"] != "character_level_only":
            problems.append("character_level_only_scope_missing")
        if not CHARACTER_LEVEL_EXCLUSIONS <= set(terms["excluded_evaluations"]):
            problems.append("character_level_exclusions_missing")
    elif scope == RealSourceEvaluationScope.per_line:
        if not isinstance(terms["line_scope_summary"], dict) or terms["evaluation_scope"] is None:
            problems.append("per_line_scope_missing")
    elif scope == RealSourceEvaluationScope.full_hebrew:
        terms["evaluation_scope"] = terms["evaluation_scope"] or "full_hebrew"
    elif scope == RealSourceEvaluationScope.images_only:
        terms["evaluation_scope"] = terms["evaluation_scope"] or "images_only"
    if expected.rendered_not_scan and not terms["rendered_not_scan"]:
        problems.append("rendered_not_scan_flag_missing")
    if problems:
        raise StageExecutionError(
            f"release terms of {item.item_id} do not satisfy the {entry.source_id} contract terms: {', '.join(problems)}"
        )
    terms["attribution_required"] = expected.attribution_required
    terms["paired_text"] = expected.paired_text
    return terms


def paired_text_for_item(item: Any) -> PairedText | None:
    """The human-made text that ships with an item, read from its pinned snapshot and checked against its checksum.

    Returns None for image-only items. A missing or altered text file raises: the text was pinned when the item
    was admitted, so a mismatch means the snapshot changed under the run.
    """

    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    raw = item.raw_metadata if isinstance(item.raw_metadata, dict) else {}
    root_value = raw.get("snapshot_root")
    if metadata.get("page_text_ref"):
        root = _snapshot_root(item, root_value)
        path = root / str(metadata["page_text_ref"])
        content = _read(item, path)
        # Wikisource text files end with one newline that is not part of the pinned hash.
        text = content.decode("utf-8")
        if hashlib.sha256(text.removesuffix("\n").encode("utf-8")).hexdigest() != metadata.get("page_text_sha256"):
            raise StageExecutionError(f"paired text checksum mismatch for {item.item_id}")
        return PairedText(path, content, "text/plain; charset=utf-8", "page_text", _sha256(content), "page_text.txt")
    if metadata.get("text_reference"):
        root = _snapshot_root(item, root_value)
        path = root / str(metadata["text_reference"])
        content = _read(item, path)
        if _sha256(content) != metadata.get("expected_text_sha256"):
            raise StageExecutionError(f"paired text checksum mismatch for {item.item_id}")
        return PairedText(path, content, "text/plain; charset=utf-8", "page_text", _sha256(content), "page_text.txt")
    if metadata.get("annotation_reference"):
        root = _snapshot_root(item, root_value)
        path = root / str(metadata["annotation_reference"])
        content = _read(item, path)
        if metadata.get("annotation_encoding") == "gzip":
            content = gzip.decompress(content)
        if _sha256(content) != metadata.get("expected_annotation_sha256"):
            raise StageExecutionError(f"paired annotation checksum mismatch for {item.item_id}")
        return PairedText(path, content, "application/vnd.prima.page+xml", "page_xml", _sha256(content), "page.xml")
    return None


def _snapshot_root(item: Any, value: Any) -> Path:
    if not value:
        raise StageExecutionError(f"{item.item_id} names a paired text but no snapshot root")
    return Path(str(value))


def _read(item: Any, path: Path) -> bytes:
    if not path.is_file():
        raise StageExecutionError(f"paired text missing for {item.item_id}")
    return path.read_bytes()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def write_paired_text(item: Any, item_dir: Path, release_root: Path, terms: ItemReleaseTermsRecord) -> list[ExportedTextRecord]:
    paired = paired_text_for_item(item)
    if paired is None:
        if terms.paired_text not in {None, "none"}:
            raise StageExecutionError(f"{item.item_id} must ship its {terms.paired_text} but has none")
        return []
    if terms.paired_text not in {None, paired.role}:
        raise StageExecutionError(f"{item.item_id} ships {paired.role}, but its contract names {terms.paired_text}")
    target = item_dir / paired.release_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(paired.content)
    return [
        ExportedTextRecord(
            release_text_path=str(target.relative_to(release_root)),
            media_type=paired.media_type,
            role=paired.role,
            sha256=paired.sha256,
            bytes=len(paired.content),
            licence=terms.text_licence or terms.licence,
        )
    ]


def attribution_manifest(exported_items: Iterable[Any], contract: RealSourceContract | None) -> dict[str, Any]:
    """Per-source attribution, licence and scope for the release, with every item that needs attribution."""

    by_source: dict[str, list[Any]] = defaultdict(list)
    for item in exported_items:
        by_source[item.source_id].append(item)
    sources: list[dict[str, Any]] = []
    for source_id in sorted(by_source):
        items = sorted(by_source[source_id], key=lambda item: item.item_id)
        entry = contract.entry(source_id) if contract is not None else None
        terms = [item.release_terms for item in items if getattr(item, "release_terms", None) is not None]
        attributed = [
            {"item_id": item.item_id, "attribution_text": item.release_terms.attribution_text, "source_url": item.source_url}
            for item in items
            if item.release_terms is not None and item.release_terms.attribution_required
        ]
        sources.append(
            {
                "source_id": source_id,
                "item_count": len(items),
                "licences": sorted({term.licence for term in terms}),
                "attribution_required": any(term.attribution_required for term in terms),
                "share_alike": any(term.share_alike for term in terms),
                "evaluation_scopes": sorted({term.evaluation_scope for term in terms if term.evaluation_scope}),
                "rendered_not_scan_count": sum(1 for term in terms if term.rendered_not_scan),
                "paired_text_count": sum(1 for item in items if getattr(item, "exported_texts", None)),
                "notice": entry.release_terms.notice if entry is not None else None,
                "attributed_items": attributed,
            }
        )
    return {"schema": ATTRIBUTION_MANIFEST_SCHEMA, "sources": sources}


def notice_doc(manifest: dict[str, Any], *, title: str) -> str:
    lines = [
        f"# NOTICE: {title}",
        "",
        "This release bundles material from the sources below under the terms stated for each. Item-level",
        "attribution is in `manifests/attribution_manifest.json` and in each item's `release_terms` in",
        "`manifests/item_manifest.json`.",
        "",
    ]
    for source in manifest["sources"]:
        lines.append(f"## `{source['source_id']}` ({source['item_count']} items)")
        lines.append("")
        lines.append(f"- Licence: {', '.join(source['licences']) or 'unrecorded'}")
        lines.append(f"- Attribution required: {'yes' if source['attribution_required'] else 'no'}")
        if source["share_alike"]:
            lines.append("- Share-alike: yes. Redistributed or adapted page text and derived references keep CC BY-SA 4.0.")
        if source["evaluation_scopes"]:
            lines.append(f"- Evaluation scope: {', '.join(source['evaluation_scopes'])}")
        if source["rendered_not_scan_count"]:
            lines.append(f"- Rendered, not scanned: {source['rendered_not_scan_count']} items (`release_terms.rendered_not_scan`).")
        if source["notice"]:
            lines.extend(["", source["notice"]])
        lines.append("")
    return "\n".join(lines)
