from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_yaml_file
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file

YIDTAKNL_SNAPSHOT_SETTING = "yidtaknl_snapshot_root"
YIDTAKNL_RASTER_MEDIA_TYPES = {"image/jpeg", "image/png"}

# Maintainer decision 2026-11-06 (F8 decision 6): printed Yiddish in Hebrew script is in scope only for
# training and character-level evaluation, never for word-level or language-level Hebrew evaluation.
YIDTAKNL_LANGUAGES = ["yi"]
YIDTAKNL_EVALUATION_SCOPE = "character_level_only"
YIDTAKNL_ALLOWED_USES = frozenset({"training", "character_level_evaluation"})
YIDTAKNL_REQUIRED_EXCLUDED_EVALUATIONS = frozenset({"word_level", "language_level_hebrew"})

# Scan rights are checked separately from the dataset licence: the CC BY 4.0 grant covers the creators'
# transcriptions, not a third party's photographs. Only scans whose holding library states an open licence
# are admitted. NLI's `public-domain-free-use` slug is the only accepted value today.
YIDTAKNL_OPEN_SCAN_LICENSE_SLUGS = frozenset({"public-domain-free-use"})


def yidtaknl_snapshot_root(source: SourceConfig, bundle: ConfigBundle) -> Path:
    reference = source.settings.extra.get(YIDTAKNL_SNAPSHOT_SETTING)
    if not isinstance(reference, str) or not reference:
        raise StageExecutionError(f"{source.id} requires settings.extra.{YIDTAKNL_SNAPSHOT_SETTING}")
    return bundle.resolve_path(reference)


def load_yidtaknl_snapshot(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load the pinned YidTakNL snapshot descriptor and its entries.jsonl records."""

    snapshot = load_yaml_file(root / "snapshot.yaml")
    entries_path = root / str(snapshot.get("entries_path", "entries.jsonl"))
    entries = [
        json.loads(line)
        for line in entries_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return snapshot, entries


def yidtaknl_usage_scope_is_valid(usage_scope: Any) -> bool:
    """True only when the entry carries the decision-6 scope marker: character-level evaluation and training only."""

    if not isinstance(usage_scope, dict):
        return False
    allowed = usage_scope.get("allowed_uses")
    excluded = usage_scope.get("excluded_evaluations")
    return (
        usage_scope.get("evaluation_scope") == YIDTAKNL_EVALUATION_SCOPE
        and isinstance(allowed, list)
        and bool(allowed)
        and set(allowed) <= YIDTAKNL_ALLOWED_USES
        and isinstance(excluded, list)
        and YIDTAKNL_REQUIRED_EXCLUDED_EVALUATIONS <= set(excluded)
    )


def yidtaknl_entry_asset(entry: dict[str, Any]) -> dict[str, Any] | None:
    for file in entry.get("files", []):
        if file.get("mime_type") in YIDTAKNL_RASTER_MEDIA_TYPES and file.get("local_path"):
            return file
    return None


def yidtaknl_entry_source_url(entry: dict[str, Any]) -> str | None:
    """Prefer the holding library's item page, then the dataset DOI."""

    for url in ((entry.get("scan") or {}).get("landing_url"), (entry.get("rights") or {}).get("attribution_url")):
        if url:
            return str(url)
    return None


def yidtaknl_entry_exclusion_reason(entry: dict[str, Any], source: SourceConfig) -> str | None:
    """Return why a YidTakNL entry cannot become a candidate for this source, or None when eligible."""

    rights = entry.get("rights") or {}
    if rights.get("license_expression") not in source.rights_strategy.values:
        return "license_not_in_source_lane"
    if rights.get("verification_status") != "primary_page_checked":
        return "rights_not_primary_page_checked"
    scan = entry.get("scan") or {}
    if scan.get("license_slug") not in YIDTAKNL_OPEN_SCAN_LICENSE_SLUGS or scan.get("scan_redistribution_allowed") is not True:
        return "scan_rights_not_open"
    if entry.get("languages") != YIDTAKNL_LANGUAGES:
        return "out_of_scope_language"
    if not yidtaknl_usage_scope_is_valid(entry.get("usage_scope")):
        return "missing_character_level_scope"
    text = entry.get("text") or {}
    if not text.get("local_path") or not text.get("sha256"):
        return "no_pinned_text"
    if text.get("adjudication_status") != "not_adjudicated" or text.get("reference_eligible") is not False:
        # Adjudication and reference eligibility come only from the F2 path, never from an upstream dataset.
        return "unsupported_reference_status"
    if yidtaknl_entry_asset(entry) is None:
        return "no_raster_asset"
    if yidtaknl_entry_source_url(entry) is None:
        return "missing_source_url"
    return None


class YidTakNLImporter:
    """Packaged-static-records adapter over a pinned YidTakNL Vaybertaytsh ground-truth snapshot.

    Each candidate is one printed Yiddish page with its page-level Transkribus text (human-corrected HTR, not
    yet attested or adjudicated under F2). The text is carried by reference and checksum only; it becomes a
    scored reference only through the F2 attestation and adjudication path, and then only for character-level
    evaluation.
    """

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = yidtaknl_snapshot_root(source, bundle)
        snapshot, entries = load_yidtaknl_snapshot(root)
        candidates: list[CandidateRecord] = []
        for entry in sorted(entries, key=lambda record: record["entry_id"]):
            if yidtaknl_entry_exclusion_reason(entry, source) is not None:
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{entry['entry_id']}",
                    source_id=source.id,
                    source_item_id=entry["entry_id"],
                    source_url=yidtaknl_entry_source_url(entry) or "",
                    discovery_method="yidtaknl_snapshot_importer",
                    title=entry["title"],
                    raw_metadata={
                        "snapshot_root": str(root),
                        "dataset_doi": snapshot.get("dataset_doi"),
                        "captured_at": str(snapshot.get("captured_at")),
                        "entry": entry,
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            entry = candidate.raw_metadata["entry"]
            root = Path(candidate.raw_metadata["snapshot_root"])
            asset = yidtaknl_entry_asset(entry) or {}
            rights = entry["rights"]
            scan = entry["scan"]
            text = entry["text"]
            usage_scope = entry["usage_scope"]
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=rights["license_expression"],
                    asset_references=[
                        AssetReference(
                            reference=asset["local_path"],
                            resolved_path=str((root / asset["local_path"]).resolve()),
                            media_type=asset["mime_type"],
                        )
                    ],
                    metadata={
                        "collection": scan.get("holding_institution") or "",
                        "period": "historical",
                        "content_type": entry.get("content_type"),
                        "typeface": entry.get("typeface"),
                        "created": (entry.get("work") or {}).get("created"),
                        "languages": entry["languages"],
                        "script": entry.get("script"),
                        "upstream_identifier": entry["entry_id"],
                        "upstream_dataset_doi": candidate.raw_metadata.get("dataset_doi"),
                        "upstream_captured_at": candidate.raw_metadata.get("captured_at"),
                        "source_group_id": f"yidtaknl:{entry['work_id']}",
                        "usage_scope": dict(usage_scope),
                        "evaluation_scope": usage_scope["evaluation_scope"],
                        "text_reference": text["local_path"],
                        "expected_text_sha256": text["sha256"],
                        "text_granularity": text.get("granularity"),
                        "text_provenance": text.get("text_provenance"),
                        "text_annotators": list(text.get("annotators") or []),
                        "heocr_attestation": text.get("heocr_attestation"),
                        "adjudication_status": text["adjudication_status"],
                        "reference_eligible": text["reference_eligible"],
                        "rights_evidence": rights.get("evidence_text"),
                        "rights_verified_at": rights.get("verified_at"),
                        "attribution_text": rights.get("attribution_text"),
                        "scan_holding_institution": scan.get("holding_institution"),
                        "scan_record_id": scan.get("record_id"),
                        "scan_license_url": scan.get("license_url"),
                        "scan_iiif_canvas": scan.get("iiif_canvas"),
                        "scan_verified_at": scan.get("verified_at"),
                        "expected_asset_sha256": asset.get("sha256"),
                    },
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            asset = item.asset_references[0]
            resolved = Path(asset.resolved_path or "")
            # The asset reference is snapshot-relative, so the snapshot root is that many levels above the asset.
            snapshot_root = resolved.parents[len(PurePosixPath(asset.reference).parts) - 1]
            text_path = snapshot_root / str(item.metadata.get("text_reference", ""))
            expected_text = item.metadata.get("expected_text_sha256")
            if not text_path.is_file() or sha256_file(text_path) != expected_text:
                raise StageExecutionError(f"YidTakNL text checksum mismatch or missing text for {item.item_id}")
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            digest = sha256_file(destination)
            expected = item.metadata.get("expected_asset_sha256")
            if expected and digest != expected:
                raise StageExecutionError(
                    f"YidTakNL asset checksum mismatch for {item.item_id}: expected {expected}, got {digest}"
                )
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[
                        AcquiredAsset(
                            item_id=item.item_id,
                            path=str(destination),
                            sha256=digest,
                            media_type=asset.media_type,
                        )
                    ],
                )
            )
        return acquired_items
