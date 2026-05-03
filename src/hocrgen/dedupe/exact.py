from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from hocrgen.config.models import ReleaseProfile
from hocrgen.manifests.models import (
    CuratedItemRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    NearDuplicateClusterRecord,
    NormalizedItemRecord,
    SourceGroupRecord,
)


@dataclass(frozen=True)
class DedupeOutputs:
    retained_items: list[CuratedItemRecord]
    duplicate_items: list[CuratedItemRecord]
    duplicate_relations: list[DuplicateRelationRecord]
    duplicate_clusters: list[DuplicateClusterRecord]
    near_duplicate_clusters: list[NearDuplicateClusterRecord]
    source_groups: list[SourceGroupRecord]
    report: dict[str, object]


def compute_content_fingerprint(item: NormalizedItemRecord) -> str:
    payload = {
        "asset_count": len(item.normalized_assets),
        "asset_sha256s": [asset.sha256 for asset in item.normalized_assets],
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def _asset_metadata_signature(item: NormalizedItemRecord) -> str:
    payload = {
        "asset_count": len(item.normalized_assets),
        "assets": [
            {
                "asset_format": asset.asset_format,
                "file_size_bytes": asset.file_size_bytes,
                "height": asset.height,
                "is_vector": asset.is_vector,
                "media_type": asset.media_type,
                "width": asset.width,
            }
            for asset in item.normalized_assets
        ],
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_group_key(item: NormalizedItemRecord) -> str:
    explicit = item.metadata.get("source_group_id") or item.raw_metadata.get("source_group_id")
    if explicit:
        return f"{item.source_id}:{explicit}"

    parsed = urlparse(item.source_url)
    if parsed.scheme and parsed.netloc:
        path = unquote(parsed.path).casefold()
        path = re.sub(r"\.(jpg|jpeg|png|tif|tiff|pdf|html?)$", "", path)
        path = re.sub(r"[\s_/-]*(page|folio|fol|p)[\s_-]*\d+$", "", path)
        path = re.sub(r"\(\d+\)$", "", path)
        path = re.sub(r"[_-]\d+$", "", path)
        path = re.sub(r"\s+", " ", path).strip("/")
        if path:
            return f"{item.source_id}:{parsed.netloc.casefold()}:{path}"

    source_item = re.sub(r"[\s_-]*(page|folio|fol|p)[\s_-]*\d+$", "", item.source_item_id.casefold())
    source_item = re.sub(r"[_-]\d+$", "", source_item)
    return f"{item.source_id}:{source_item or item.source_item_id.casefold()}"


def _cluster_ids_by_signature(
    grouped_items: dict[str, list[NormalizedItemRecord]],
    *,
    prefix: str,
) -> dict[str, str]:
    cluster_ids: dict[str, str] = {}
    for signature, items in sorted(grouped_items.items()):
        distinct_fingerprints = {compute_content_fingerprint(item) for item in items}
        if len(items) > 1 and (prefix == "source-group" or len(distinct_fingerprints) > 1):
            cluster_ids[signature] = _stable_id(prefix, signature)
    return cluster_ids


def _source_priority_map(profile: ReleaseProfile) -> dict[str, int]:
    return {source_id: index for index, source_id in enumerate(profile.include_sources)}


def _canonical_sort_key(item: NormalizedItemRecord, source_priority: dict[str, int]) -> tuple[int, int, str]:
    return (
        source_priority.get(item.source_id, len(source_priority)),
        1 if item.is_synthetic else 0,
        item.item_id,
    )


def deduplicate_items(items: list[NormalizedItemRecord], profile: ReleaseProfile) -> DedupeOutputs:
    source_priority = _source_priority_map(profile)
    fingerprint_groups: dict[str, list[NormalizedItemRecord]] = {}
    near_duplicate_groups: dict[str, list[NormalizedItemRecord]] = {}
    source_group_candidates: dict[str, list[NormalizedItemRecord]] = {}
    for item in items:
        fingerprint_groups.setdefault(compute_content_fingerprint(item), []).append(item)
        near_duplicate_groups.setdefault(_asset_metadata_signature(item), []).append(item)
        source_group_candidates.setdefault(_source_group_key(item), []).append(item)

    near_duplicate_cluster_ids = _cluster_ids_by_signature(near_duplicate_groups, prefix="near-duplicate")
    source_group_ids = _cluster_ids_by_signature(source_group_candidates, prefix="source-group")
    item_near_duplicate_cluster_ids = {
        item.item_id: near_duplicate_cluster_ids[signature]
        for signature, grouped_items in near_duplicate_groups.items()
        if signature in near_duplicate_cluster_ids
        for item in grouped_items
    }
    item_source_group_ids = {
        item.item_id: source_group_ids[signature]
        for signature, grouped_items in source_group_candidates.items()
        if signature in source_group_ids
        for item in grouped_items
    }

    retained_items: list[CuratedItemRecord] = []
    duplicate_items: list[CuratedItemRecord] = []
    duplicate_relations: list[DuplicateRelationRecord] = []
    duplicate_clusters: list[DuplicateClusterRecord] = []

    for fingerprint, grouped_items in sorted(fingerprint_groups.items()):
        members = sorted(grouped_items, key=lambda item: _canonical_sort_key(item, source_priority))
        canonical = members[0]
        has_duplicates = len(members) > 1
        cluster_id = fingerprint if has_duplicates else None
        retained_items.append(
            CuratedItemRecord(
                **canonical.model_dump(),
                content_fingerprint=fingerprint,
                dedupe_cluster_id=cluster_id,
                near_duplicate_cluster_id=item_near_duplicate_cluster_ids.get(canonical.item_id),
                source_group_id=item_source_group_ids.get(canonical.item_id),
                dedupe_status="retained",
                canonical_item_id=canonical.item_id,
            )
        )

        if not has_duplicates:
            continue

        duplicate_clusters.append(
            DuplicateClusterRecord(
                cluster_id=fingerprint,
                canonical_item_id=canonical.item_id,
                member_item_ids=[member.item_id for member in members],
            )
        )
        for duplicate in members[1:]:
            duplicate_items.append(
                CuratedItemRecord(
                    **duplicate.model_dump(),
                    content_fingerprint=fingerprint,
                    dedupe_cluster_id=fingerprint,
                    near_duplicate_cluster_id=item_near_duplicate_cluster_ids.get(duplicate.item_id),
                    source_group_id=item_source_group_ids.get(duplicate.item_id),
                    dedupe_status="duplicate",
                    canonical_item_id=canonical.item_id,
                )
            )
            duplicate_relations.append(
                DuplicateRelationRecord(
                    cluster_id=fingerprint,
                    canonical_item_id=canonical.item_id,
                    duplicate_item_id=duplicate.item_id,
                    reason="exact_asset_sequence_match",
                    content_fingerprint=fingerprint,
                )
            )

    near_duplicate_clusters = [
        NearDuplicateClusterRecord(
            cluster_id=cluster_id,
            member_item_ids=sorted(item.item_id for item in near_duplicate_groups[signature]),
            rationale="Items share deterministic normalized asset metadata but are not exact asset-sequence duplicates; surfaced for manual review and split grouping.",
        )
        for signature, cluster_id in sorted(near_duplicate_cluster_ids.items(), key=lambda row: row[1])
    ]
    source_groups = [
        SourceGroupRecord(
            group_id=group_id,
            member_item_ids=sorted(item.item_id for item in source_group_candidates[signature]),
            source_ids=sorted({item.source_id for item in source_group_candidates[signature]}),
            rationale="Items resolve to the same deterministic source-work key and are kept together for split safety.",
        )
        for signature, group_id in sorted(source_group_ids.items(), key=lambda row: row[1])
    ]

    return DedupeOutputs(
        retained_items=sorted(retained_items, key=lambda item: item.item_id),
        duplicate_items=sorted(duplicate_items, key=lambda item: item.item_id),
        duplicate_relations=sorted(duplicate_relations, key=lambda relation: (relation.cluster_id, relation.duplicate_item_id)),
        duplicate_clusters=sorted(duplicate_clusters, key=lambda cluster: cluster.cluster_id),
        near_duplicate_clusters=near_duplicate_clusters,
        source_groups=source_groups,
        report={
            "duplicate_cluster_count": len(duplicate_clusters),
            "duplicate_item_count": len(duplicate_items),
            "near_duplicate_evaluation": {
                "cluster_count": len(near_duplicate_clusters),
                "decision": "surface_and_split_group_not_auto_remove",
                "status": "implemented",
            },
            "retained_count": len(retained_items),
            "source_group_count": len(source_groups),
            "unique_fingerprint_count": len(fingerprint_groups),
        },
    )
