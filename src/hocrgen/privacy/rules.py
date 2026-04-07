from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import PrivacyFlag
from hocrgen.manifests.models import ClassifiedItemRecord, PrivacyScannedItemRecord


@dataclass(frozen=True)
class PrivacyOutputs:
    scanned_items: list[PrivacyScannedItemRecord]
    summary: dict[str, object]


_PRIVACY_PRIORITY = {
    PrivacyFlag.clear: 0,
    PrivacyFlag.possible_personal_data: 1,
    PrivacyFlag.needs_review: 2,
    PrivacyFlag.blocked_sensitive: 3,
}


def _field_text(item: ClassifiedItemRecord, field_name: str) -> str:
    if field_name == "title":
        return item.title or ""
    if field_name == "description":
        return str(item.metadata.get("description", ""))
    if field_name == "metadata":
        return " ".join(str(value) for value in item.metadata.values())
    if field_name == "source_url":
        return item.source_url
    return ""


def _apply_profile_mode(flag: PrivacyFlag, privacy_mode: str) -> tuple[PrivacyFlag, str]:
    if privacy_mode == "off":
        return PrivacyFlag.clear, "release_ready"
    if flag == PrivacyFlag.blocked_sensitive:
        return flag, "blocked"
    if flag in {PrivacyFlag.needs_review, PrivacyFlag.possible_personal_data}:
        return flag, "review_required"
    return flag, "release_ready"


def apply_privacy_rules(items: list[ClassifiedItemRecord], bundle: ConfigBundle, profile_id: str) -> PrivacyOutputs:
    privacy_mode = bundle.profiles[profile_id].privacy_mode
    flag_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    scanned_items: list[PrivacyScannedItemRecord] = []

    for item in items:
        matched_flag = bundle.privacy_rules.source_defaults.get(item.source_id, PrivacyFlag.clear)
        matched_reasons: list[str] = []
        for rule in bundle.privacy_rules.rules:
            if rule.applies_to_sources and item.source_id not in rule.applies_to_sources:
                continue
            if rule.applies_to_periods and item.period_class not in rule.applies_to_periods:
                continue
            flags = re.IGNORECASE if not rule.case_sensitive else 0
            haystack = " ".join(_field_text(item, field_name) for field_name in rule.fields)
            if any(re.search(pattern, haystack, flags) for pattern in rule.patterns):
                if _PRIVACY_PRIORITY[rule.flag] > _PRIVACY_PRIORITY[matched_flag]:
                    matched_flag = rule.flag
                matched_reasons.append(rule.id)

        privacy_flag, decision = _apply_profile_mode(matched_flag, privacy_mode)
        scanned = PrivacyScannedItemRecord(
            **item.model_dump(),
            privacy_flag=privacy_flag,
            privacy_reasons=sorted(set(matched_reasons)),
            privacy_decision=decision,
        )
        scanned_items.append(scanned)
        flag_counts[privacy_flag.value] += 1
        source_counts[item.source_id] += 1
        reason_counts.update(scanned.privacy_reasons)

    return PrivacyOutputs(
        scanned_items=sorted(scanned_items, key=lambda item: item.item_id),
        summary={
            "privacy_flags": dict(flag_counts),
            "privacy_reasons": dict(reason_counts),
            "sources": dict(source_counts),
        },
    )
