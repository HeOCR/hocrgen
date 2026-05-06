from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from hocrgen.manifests.models import PrivacyScannedItemRecord, ReviewQueueRecord


@dataclass(frozen=True)
class ReviewExportOutputs:
    release_ready_items: list[PrivacyScannedItemRecord]
    review_required_items: list[PrivacyScannedItemRecord]
    blocked_items: list[PrivacyScannedItemRecord]
    review_queue: list[ReviewQueueRecord]
    summary: dict[str, object]


def _split_group_id_pre_review(item: PrivacyScannedItemRecord) -> str:
    if item.dedupe_cluster_id:
        return item.dedupe_cluster_id
    return f"{item.source_id}:{item.source_item_id}"


def _suggested_decision(reasons: list[str]) -> str:
    if any(reason.startswith("privacy:") for reason in reasons):
        return "needs_privacy_review"
    if any(reason.startswith("classification:") for reason in reasons):
        return "needs_classification_review"
    return "needs_policy_review"


def export_review_queue(items: list[PrivacyScannedItemRecord]) -> ReviewExportOutputs:
    release_ready_items: list[PrivacyScannedItemRecord] = []
    review_required_items: list[PrivacyScannedItemRecord] = []
    blocked_items: list[PrivacyScannedItemRecord] = []
    review_queue: list[ReviewQueueRecord] = []
    review_reason_counts: Counter[str] = Counter()

    for item in sorted(items, key=lambda record: record.item_id):
        review_reasons: list[str] = []
        if item.privacy_decision == "blocked":
            blocked_items.append(item)
            continue
        if item.privacy_decision == "review_required":
            review_reasons.extend(f"privacy:{reason}" for reason in (item.privacy_reasons or [item.privacy_flag.value]))
        if item.classification_review_reasons:
            review_reasons.extend(f"classification:{reason}" for reason in item.classification_review_reasons)
        if item.provenance.get("requires_manual_review") is True:
            review_reasons.append("policy:manual_review_required_source")
        if item.provenance.get("source_status") == "review_only":
            review_reasons.append("policy:review_only_source")
        if item.rights_classification.value == "restricted_review_only":
            review_reasons.append("policy:restricted_rights")

        if review_reasons:
            review_required_items.append(item)
            review_reason_counts.update(review_reasons)
            review_queue.append(
                ReviewQueueRecord(
                    review_item_id=f"review:{item.item_id}",
                    item_id=item.item_id,
                    source_id=item.source_id,
                    canonical_item_id=item.canonical_item_id,
                    split_group_id_pre_review=_split_group_id_pre_review(item),
                    review_reasons=sorted(set(review_reasons)),
                    suggested_decision=_suggested_decision(review_reasons),
                    privacy_flag=item.privacy_flag,
                    classification_summary={
                        "content_class": item.content_class,
                        "content_confidence": item.content_confidence,
                        "period_class": item.period_class,
                        "period_confidence": item.period_confidence,
                        "language_class": item.language_class,
                        "language_confidence": item.language_confidence,
                        "quality_score": item.quality_score,
                        "quality_tier": item.quality_tier,
                    },
                    preview_paths=[asset.preview_path for asset in item.normalized_assets if asset.preview_path],
                    source_url=item.source_url,
                    title=item.title,
                )
            )
        else:
            release_ready_items.append(item)

    return ReviewExportOutputs(
        release_ready_items=release_ready_items,
        review_required_items=review_required_items,
        blocked_items=blocked_items,
        review_queue=review_queue,
        summary={
            "blocked_count": len(blocked_items),
            "release_ready_count": len(release_ready_items),
            "review_reason_counts": dict(review_reason_counts),
            "review_required_count": len(review_required_items),
        },
    )
