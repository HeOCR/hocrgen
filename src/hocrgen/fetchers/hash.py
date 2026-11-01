from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_yaml_file
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file

HASH_SNAPSHOT_SETTING = "hash_snapshot_root"
HASH_RASTER_MEDIA_TYPES = {"image/jpeg", "image/png"}
HASH_ASSET_ROLE_PREFERENCE = ("original", "thumbnail")


def hash_snapshot_root(source: SourceConfig, bundle: ConfigBundle) -> Path:
    reference = source.settings.extra.get(HASH_SNAPSHOT_SETTING)
    if not isinstance(reference, str) or not reference:
        raise StageExecutionError(f"{source.id} requires settings.extra.{HASH_SNAPSHOT_SETTING}")
    return bundle.resolve_path(reference)


def load_hash_snapshot(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load a pinned HASH snapshot descriptor and its entries.jsonl records."""

    snapshot = load_yaml_file(root / "snapshot.yaml")
    entries_path = root / str(snapshot.get("entries_path", "entries.jsonl"))
    entries = [
        json.loads(line)
        for line in entries_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    return snapshot, entries


def hash_entry_exclusion_reason(entry: dict[str, Any], source: SourceConfig) -> str | None:
    """Return why a HASH entry cannot become a candidate for this source, or None when eligible.

    Rights are matched against the source's own exact-match values, so entries from another licence lane
    (including CC-BY-SA-3.0, which no HASH source accepts) are never emitted.
    """

    rights = entry.get("rights") or {}
    if rights.get("license_expression") not in source.rights_strategy.values:
        return "license_not_in_source_lane"
    if rights.get("verification_status") != "primary_page_checked":
        return "rights_not_primary_page_checked"
    if rights.get("scan_redistribution_allowed") is not True:
        return "scan_redistribution_not_allowed"
    if entry.get("languages") != ["he"]:
        return "out_of_scope_language"
    if (entry.get("handwriting") or {}).get("hebrew_extent") != "full_page":
        return "partial_hebrew_extent"
    if (entry.get("quality") or {}).get("usable_for_htr") is not True:
        return "not_usable_for_htr"
    if hash_entry_asset(entry) is None:
        return "no_raster_asset"
    if hash_entry_source_url(entry) is None:
        return "missing_source_url"
    return None


def hash_entry_asset(entry: dict[str, Any]) -> dict[str, Any] | None:
    files = [file for file in entry.get("files", []) if file.get("mime_type") in HASH_RASTER_MEDIA_TYPES]
    for role in HASH_ASSET_ROLE_PREFERENCE:
        for file in files:
            if file.get("role") == role:
                return file
    return None


def hash_entry_source_url(entry: dict[str, Any]) -> str | None:
    """Prefer the upstream landing page, then the attribution page, then the asset's own source URL."""

    asset = hash_entry_asset(entry) or {}
    for url in (
        (entry.get("provenance") or {}).get("source_landing_url"),
        (entry.get("rights") or {}).get("attribution_url"),
        asset.get("source_url"),
    ):
        if url:
            return str(url)
    return None


def _writer_group(entry: dict[str, Any]) -> str:
    names = sorted(
        str(creator.get("name"))
        for creator in entry.get("creators", [])
        if creator.get("name") and creator.get("name") != "unknown"
    )
    return "; ".join(names) if names else f"unknown:{entry['source_id']}"


class HashImporter:
    """Packaged-static-records adapter over a pinned HASH (HeOCR/hash) snapshot.

    Only scan-level metadata, rights evidence, and raster assets are read. HASH transcripts and HTR candidates
    are never read here; reference conversion is a separate, attestation-gated step.
    """

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = hash_snapshot_root(source, bundle)
        snapshot, entries = load_hash_snapshot(root)
        candidates: list[CandidateRecord] = []
        for entry in sorted(entries, key=lambda record: record["entry_id"]):
            if hash_entry_exclusion_reason(entry, source) is not None:
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{entry['entry_id']}",
                    source_id=source.id,
                    source_item_id=entry["entry_id"],
                    source_url=hash_entry_source_url(entry) or "",
                    discovery_method="hash_snapshot_importer",
                    title=entry["title"],
                    raw_metadata={
                        "snapshot_root": str(root),
                        "upstream_commit": snapshot.get("upstream_commit"),
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
            asset = hash_entry_asset(entry) or {}
            rights = entry["rights"]
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
                        "collection": entry.get("holding_institution") or "",
                        "period": "historical",
                        "upstream_identifier": entry["entry_id"],
                        "upstream_repository": "HeOCR/hash",
                        "upstream_commit": candidate.raw_metadata.get("upstream_commit"),
                        "source_group_id": f"hash:{entry['source_id']}",
                        "writer_group_id": _writer_group(entry),
                        "document_type": entry.get("document_type"),
                        "created": (entry.get("dates") or {}).get("created"),
                        "languages": entry.get("languages", []),
                        "rights_evidence": rights.get("evidence_text"),
                        "rights_verified_at": rights.get("verified_at"),
                        "attribution_text": rights.get("attribution_text"),
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
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            digest = sha256_file(destination)
            expected = item.metadata.get("expected_asset_sha256")
            if expected and digest != expected:
                raise StageExecutionError(
                    f"HASH asset checksum mismatch for {item.item_id}: expected {expected}, got {digest}"
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
