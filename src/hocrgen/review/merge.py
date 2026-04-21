from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from hocrgen.config.loader import default_config_root, load_json_file
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    PrivacyScannedItemRecord,
    ReviewDecisionAuditRecord,
    ReviewDecisionRecord,
    ReviewOverrideRecord,
    ReviewQueueRecord,
)


@dataclass(frozen=True)
class ReviewData:
    root: Path
    manual_decisions: list[ReviewDecisionRecord]
    allowlist: list[ReviewOverrideRecord]
    blocklist: list[ReviewOverrideRecord]


@dataclass(frozen=True)
class ReviewMergeOutputs:
    release_ready_items: list[PrivacyScannedItemRecord]
    unresolved_items: list[PrivacyScannedItemRecord]
    rejected_items: list[PrivacyScannedItemRecord]
    decision_audit: list[ReviewDecisionAuditRecord]
    summary: dict[str, object]


def _review_data_root_candidates(config_root: Path) -> list[Path]:
    config_root = config_root.resolve()
    candidates: list[Path] = []

    for parent in (config_root, *config_root.parents):
        candidate = parent / "review_data"
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def resolve_review_data_root(config_root: Path, explicit_config_root: Path | None = None) -> Path:
    resolved_config_root = explicit_config_root.resolve() if explicit_config_root is not None else config_root.resolve()

    for candidate in _review_data_root_candidates(resolved_config_root):
        if candidate.exists():
            return candidate

    if resolved_config_root == default_config_root().resolve():
        return resolved_config_root.parents[2] / "review_data"
    return resolved_config_root.parent / "review_data"


def load_review_data(config_root: Path, explicit_config_root: Path | None = None) -> ReviewData:
    root = resolve_review_data_root(config_root, explicit_config_root)
    review_data = ReviewData(
        root=root,
        manual_decisions=_load_records(root / "manual_decisions", ReviewDecisionRecord),
        allowlist=_load_records(root / "allowlists", ReviewOverrideRecord),
        blocklist=_load_records(root / "blocklists", ReviewOverrideRecord),
    )
    _validate_review_data(review_data)
    return review_data


def validate_review_data(config_root: Path, explicit_config_root: Path | None = None) -> ReviewData:
    return load_review_data(config_root, explicit_config_root)


def merge_review_decisions(
    *,
    release_ready_items: list[PrivacyScannedItemRecord],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    review_queue: list[ReviewQueueRecord],
    review_data: ReviewData,
) -> ReviewMergeOutputs:
    del blocked_items

    _validate_review_data(review_data)

    queue_by_item_id = {item.item_id: item for item in review_queue}
    queue_by_review_item_id = {item.review_item_id: item for item in review_queue}
    review_required_by_item_id = {item.item_id: item for item in review_required_items}
    release_ready_by_item_id = {item.item_id: item for item in release_ready_items}

    for decision in review_data.manual_decisions:
        queue_item = queue_by_item_id.get(decision.item_id)
        if queue_item is None:
            raise StageExecutionError(f"manual review decision references unknown review item: {decision.item_id}")
        if decision.review_item_id not in queue_by_review_item_id:
            raise StageExecutionError(f"manual review decision references unknown review queue id: {decision.review_item_id}")
        if queue_item.review_item_id != decision.review_item_id:
            raise StageExecutionError(
                f"manual review decision review/item mismatch for {decision.item_id}: "
                f"expected {queue_item.review_item_id}, got {decision.review_item_id}"
            )

    for entry in review_data.allowlist:
        queue_item = _queue_entry_for_override(entry, queue_by_item_id, queue_by_review_item_id)
        if queue_item is None:
            raise StageExecutionError(f"allowlist entry must target a review-queued item: {entry.item_id}")
        if entry.review_item_id is not None and queue_item.review_item_id != entry.review_item_id:
            raise StageExecutionError(
                f"allowlist review/item mismatch for {entry.item_id}: expected {queue_item.review_item_id}, got {entry.review_item_id}"
            )

    for entry in review_data.blocklist:
        queue_item = _queue_entry_for_override(entry, queue_by_item_id, queue_by_review_item_id)
        if queue_item is None and entry.item_id not in release_ready_by_item_id:
            raise StageExecutionError(f"blocklist entry references unknown item: {entry.item_id}")
        if entry.review_item_id is not None:
            if queue_item is None:
                raise StageExecutionError(f"blocklist review item id must target a review-queued item: {entry.review_item_id}")
            if queue_item.review_item_id != entry.review_item_id:
                raise StageExecutionError(
                    f"blocklist review/item mismatch for {entry.item_id}: expected {queue_item.review_item_id}, got {entry.review_item_id}"
                )

    manual_by_item_id = {record.item_id: record for record in review_data.manual_decisions}
    allow_by_item_id = {record.item_id: record for record in review_data.allowlist}
    block_by_item_id = {record.item_id: record for record in review_data.blocklist}

    final_release_ready: dict[str, PrivacyScannedItemRecord] = {}
    unresolved_items: dict[str, PrivacyScannedItemRecord] = {}
    rejected_items: dict[str, PrivacyScannedItemRecord] = {}
    decision_audit: list[ReviewDecisionAuditRecord] = []
    review_approved_count = 0

    for item in sorted(release_ready_items, key=lambda record: record.item_id):
        block_entry = block_by_item_id.get(item.item_id)
        if block_entry is not None:
            rejected_items[item.item_id] = item
            decision_audit.append(_audit_from_override(item, block_entry, "blocklist", "rejected"))
            continue
        final_release_ready[item.item_id] = item
        decision_audit.append(
            ReviewDecisionAuditRecord(
                item_id=item.item_id,
                decision_source="automatic_release_ready",
                outcome="release_ready",
            )
        )

    for queue_item in sorted(review_queue, key=lambda record: record.item_id):
        item = review_required_by_item_id[queue_item.item_id]
        manual_decision = manual_by_item_id.get(item.item_id)
        allow_entry = allow_by_item_id.get(item.item_id)
        block_entry = block_by_item_id.get(item.item_id)
        if manual_decision is not None:
            if manual_decision.decision == "approve":
                final_release_ready[item.item_id] = item
                review_approved_count += 1
                decision_audit.append(_audit_from_manual(item, manual_decision, "release_ready"))
            elif manual_decision.decision == "reject":
                rejected_items[item.item_id] = item
                decision_audit.append(_audit_from_manual(item, manual_decision, "rejected"))
            else:
                unresolved_items[item.item_id] = item
                decision_audit.append(_audit_from_manual(item, manual_decision, "unresolved"))
            continue
        if allow_entry is not None:
            final_release_ready[item.item_id] = item
            review_approved_count += 1
            decision_audit.append(_audit_from_override(item, allow_entry, "allowlist", "release_ready"))
            continue
        if block_entry is not None:
            rejected_items[item.item_id] = item
            decision_audit.append(_audit_from_override(item, block_entry, "blocklist", "rejected"))
            continue
        unresolved_items[item.item_id] = item
        decision_audit.append(
            ReviewDecisionAuditRecord(
                item_id=item.item_id,
                review_item_id=queue_item.review_item_id,
                decision_source="default_unresolved",
                outcome="unresolved",
            )
        )

    return ReviewMergeOutputs(
        release_ready_items=sorted(final_release_ready.values(), key=lambda record: record.item_id),
        unresolved_items=sorted(unresolved_items.values(), key=lambda record: record.item_id),
        rejected_items=sorted(rejected_items.values(), key=lambda record: record.item_id),
        decision_audit=sorted(decision_audit, key=lambda record: record.item_id),
        summary={
            "blocklisted_release_ready_count": sum(
                1 for item_id in rejected_items if item_id in release_ready_by_item_id and item_id not in review_required_by_item_id
            ),
            "release_ready_count": len(final_release_ready),
            "review_approved_count": review_approved_count,
            "review_rejected_count": len(rejected_items),
            "review_unresolved_count": len(unresolved_items),
            "decision_source_counts": dict(Counter(record.decision_source for record in decision_audit)),
            "stage": "review-merge",
        },
    )


def _load_records(directory: Path, model_type):
    if not directory.exists():
        return []
    loaded = []
    for path in sorted(directory.glob("*.json")):
        try:
            loaded.append(model_type.model_validate(load_json_file(path)))
        except ValidationError as exc:
            raise ConfigValidationError(f"{model_type.__name__} validation failed for {path}", details=exc.errors()) from exc
    return loaded


def _validate_review_data(review_data: ReviewData) -> None:
    _validate_unique_targets(review_data.manual_decisions, "manual review decisions")
    _validate_unique_targets(review_data.allowlist, "allowlist entries")
    _validate_unique_targets(review_data.blocklist, "blocklist entries")

    allow_ids = {record.item_id for record in review_data.allowlist}
    block_ids = {record.item_id for record in review_data.blocklist}
    overlap = sorted(allow_ids & block_ids)
    if overlap:
        raise ConfigValidationError(
            "review data contains allowlist/blocklist conflicts",
            details=[{"conflicting_item_ids": overlap}],
        )

    manual_ids = {record.item_id for record in review_data.manual_decisions}
    override_overlap = sorted(manual_ids & (allow_ids | block_ids))
    if override_overlap:
        raise ConfigValidationError(
            "review data contains manual-decision/override conflicts",
            details=[{"conflicting_item_ids": override_overlap}],
        )


def _validate_unique_targets(records, label: str) -> None:
    by_item_id: dict[str, list[str | None]] = defaultdict(list)
    for record in records:
        by_item_id[record.item_id].append(getattr(record, "review_item_id", None))
    duplicates = sorted(item_id for item_id, values in by_item_id.items() if len(values) > 1)
    if duplicates:
        raise ConfigValidationError(
            f"review data contains duplicate {label}",
            details=[{"duplicate_item_ids": duplicates}],
        )


def _queue_entry_for_override(
    entry: ReviewOverrideRecord,
    queue_by_item_id: dict[str, ReviewQueueRecord],
    queue_by_review_item_id: dict[str, ReviewQueueRecord],
) -> ReviewQueueRecord | None:
    queue_item = queue_by_item_id.get(entry.item_id)
    if entry.review_item_id is not None:
        queue_from_review_id = queue_by_review_item_id.get(entry.review_item_id)
        if queue_item is None:
            if queue_from_review_id is not None and queue_from_review_id.item_id != entry.item_id:
                raise StageExecutionError(
                    f"override review/item mismatch for {entry.item_id}: expected {queue_from_review_id.item_id}, got {entry.review_item_id}"
                )
            return queue_from_review_id
        if queue_from_review_id is not None and queue_from_review_id.item_id != queue_item.item_id:
            raise StageExecutionError(
                f"override review/item mismatch for {entry.item_id}: expected {queue_item.review_item_id}, got {entry.review_item_id}"
            )
    return queue_item


def _audit_from_manual(
    item: PrivacyScannedItemRecord,
    record: ReviewDecisionRecord,
    outcome: str,
) -> ReviewDecisionAuditRecord:
    return ReviewDecisionAuditRecord(
        item_id=item.item_id,
        review_item_id=record.review_item_id,
        decision_source="manual_decision",
        outcome=outcome,
        decision=record.decision,
        reviewer=record.reviewer,
        timestamp=record.timestamp,
        rationale=record.rationale,
        notes=record.notes,
    )


def _audit_from_override(
    item: PrivacyScannedItemRecord,
    record: ReviewOverrideRecord,
    source: str,
    outcome: str,
) -> ReviewDecisionAuditRecord:
    return ReviewDecisionAuditRecord(
        item_id=item.item_id,
        review_item_id=record.review_item_id,
        decision_source=source,
        outcome=outcome,
        reviewer=record.reviewer,
        timestamp=record.timestamp,
        rationale=record.rationale,
        notes=record.notes,
    )
