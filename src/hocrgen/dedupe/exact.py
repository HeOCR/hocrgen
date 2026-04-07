from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from hocrgen.config.models import ReleaseProfile
from hocrgen.manifests.models import CuratedItemRecord, DuplicateClusterRecord, DuplicateRelationRecord, NormalizedItemRecord


@dataclass(frozen=True)
class DedupeOutputs:
    retained_items: list[CuratedItemRecord]
    duplicate_items: list[CuratedItemRecord]
    duplicate_relations: list[DuplicateRelationRecord]
    duplicate_clusters: list[DuplicateClusterRecord]
    report: dict[str, object]


def compute_content_fingerprint(item: NormalizedItemRecord) -> str:
    payload = {
        "asset_count": len(item.normalized_assets),
        "asset_sha256s": [asset.sha256 for asset in item.normalized_assets],
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    for item in items:
        fingerprint_groups.setdefault(compute_content_fingerprint(item), []).append(item)

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

    return DedupeOutputs(
        retained_items=sorted(retained_items, key=lambda item: item.item_id),
        duplicate_items=sorted(duplicate_items, key=lambda item: item.item_id),
        duplicate_relations=sorted(duplicate_relations, key=lambda relation: (relation.cluster_id, relation.duplicate_item_id)),
        duplicate_clusters=sorted(duplicate_clusters, key=lambda cluster: cluster.cluster_id),
        report={
            "duplicate_cluster_count": len(duplicate_clusters),
            "duplicate_item_count": len(duplicate_items),
            "near_duplicate_evaluation": {"status": "not_implemented"},
            "retained_count": len(retained_items),
            "unique_fingerprint_count": len(fingerprint_groups),
        },
    )
