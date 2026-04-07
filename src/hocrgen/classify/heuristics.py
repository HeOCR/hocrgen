from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from hocrgen.config.loader import ConfigBundle
from hocrgen.manifests.models import ClassifiedItemRecord, CuratedItemRecord


@dataclass(frozen=True)
class ClassificationOutputs:
    classified_items: list[ClassifiedItemRecord]
    summary: dict[str, object]


def _contains_hebrew(text: str) -> bool:
    return any("\u0590" <= char <= "\u05ff" for char in text)


def _contains_latin(text: str) -> bool:
    return any(("a" <= char.lower() <= "z") for char in text)


def _combined_text(item: CuratedItemRecord) -> str:
    metadata_values = " ".join(str(value) for value in item.metadata.values())
    title = item.title or ""
    description = str(item.metadata.get("description", ""))
    return " ".join([title, description, metadata_values]).strip()


def _source_allowed_types(bundle: ConfigBundle, source_id: str) -> list[str]:
    for source in bundle.source_registry.sources:
        if source.id == source_id:
            return source.allowed_content_types
    return []


def _content_class(item: CuratedItemRecord, bundle: ConfigBundle) -> tuple[str, float, list[str]]:
    reasons: list[str] = []
    text = _combined_text(item).lower()
    template_id = str(item.metadata.get("synthetic_template_id", ""))
    allowed_types = _source_allowed_types(bundle, item.source_id)

    if template_id == "handwritten_note":
        return "handwritten", 0.95, reasons
    if template_id == "printed_letter":
        return "printed", 0.95, reasons
    if "כתב יד" in text or "מכתב" in text or "פנקס" in text or "note" in text:
        return "handwritten", 0.85, reasons
    if 'דו"ח' in text or "אישור" in text or "report" in text or "office copy" in text:
        return "printed", 0.8, reasons

    has_handwritten = any("handwritten" in content_type or "manuscript" in content_type for content_type in allowed_types)
    has_printed = any("printed" in content_type for content_type in allowed_types)
    if has_handwritten and has_printed:
        reasons.append("content_conflicting_source_priors")
        return "mixed", 0.5, reasons
    if has_handwritten:
        return "handwritten", 0.7, reasons
    if has_printed:
        return "printed", 0.7, reasons
    reasons.append("content_unknown")
    return "mixed", 0.45, reasons


def _period_class(item: CuratedItemRecord) -> tuple[str, float, list[str]]:
    reasons: list[str] = []
    period = str(item.metadata.get("period", "")).lower()
    text = _combined_text(item).lower()
    if item.is_synthetic:
        return "modern", 0.95, reasons
    if period == "historical" or item.source_id in {"pinkas_open", "biblia_open"}:
        return "historical", 0.95, reasons
    if item.source_id == "nli_any_use_permitted":
        return "modern", 0.8, reasons
    if any(year in text for year in ("193", "194", "195", "196", "197", "198", "199", "200", "201", "202")):
        reasons.append("period_inferred_from_year")
        return "modern", 0.7, reasons
    reasons.append("period_source_prior_only")
    return "modern", 0.6, reasons


def _language_class(item: CuratedItemRecord) -> tuple[str, float, list[str]]:
    reasons: list[str] = []
    text = _combined_text(item)
    has_hebrew = _contains_hebrew(text)
    has_latin = _contains_latin(text)
    if item.is_synthetic:
        return "mixed_language", 0.85, reasons
    if has_hebrew and has_latin:
        return "mixed_language", 0.9, reasons
    if has_hebrew:
        return "hebrew_only", 0.9, reasons
    if has_latin:
        reasons.append("language_non_hebrew_title")
        return "mixed_language", 0.65, reasons
    reasons.append("language_unknown")
    return "hebrew_only", 0.55, reasons


def _quality(item: CuratedItemRecord) -> tuple[float, str]:
    asset_count = len(item.normalized_assets)
    average_width = sum(asset.width or 0 for asset in item.normalized_assets) / asset_count if asset_count else 0
    average_height = sum(asset.height or 0 for asset in item.normalized_assets) / asset_count if asset_count else 0
    score = 0.5
    if asset_count >= 1:
        score += 0.1
    if average_width >= 800:
        score += 0.15
    if average_height >= 1000:
        score += 0.15
    if item.is_synthetic:
        score += 0.1
    score = min(score, 1.0)
    if score >= 0.8:
        return score, "high"
    if score >= 0.6:
        return score, "medium"
    return score, "low"


def classify_items(items: list[CuratedItemRecord], bundle: ConfigBundle) -> ClassificationOutputs:
    classified_items: list[ClassifiedItemRecord] = []
    content_counts: Counter[str] = Counter()
    period_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    quality_counts: Counter[str] = Counter()
    low_confidence_reasons: Counter[str] = Counter()

    for item in items:
        content_class, content_confidence, content_reasons = _content_class(item, bundle)
        period_class, period_confidence, period_reasons = _period_class(item)
        language_class, language_confidence, language_reasons = _language_class(item)
        quality_score, quality_tier = _quality(item)

        review_reasons: list[str] = []
        for confidence, reason_code in (
            (content_confidence, "content_low_confidence"),
            (period_confidence, "period_low_confidence"),
            (language_confidence, "language_low_confidence"),
        ):
            if confidence < 0.65:
                review_reasons.append(reason_code)
                low_confidence_reasons[reason_code] += 1
        if quality_tier == "low":
            review_reasons.append("quality_low")
            low_confidence_reasons["quality_low"] += 1
        for reason in [*content_reasons, *period_reasons, *language_reasons]:
            if "conflicting" in reason:
                review_reasons.append(reason)
                low_confidence_reasons[reason] += 1

        classified = ClassifiedItemRecord(
            **item.model_dump(),
            content_class=content_class,
            content_confidence=content_confidence,
            period_class=period_class,
            period_confidence=period_confidence,
            language_class=language_class,
            language_confidence=language_confidence,
            quality_score=quality_score,
            quality_tier=quality_tier,
            classification_review_reasons=sorted(set(review_reasons)),
        )
        classified_items.append(classified)
        content_counts[content_class] += 1
        period_counts[period_class] += 1
        language_counts[language_class] += 1
        quality_counts[quality_tier] += 1

    return ClassificationOutputs(
        classified_items=sorted(classified_items, key=lambda item: item.item_id),
        summary={
            "content_classes": dict(content_counts),
            "language_classes": dict(language_counts),
            "low_confidence_reasons": dict(low_confidence_reasons),
            "period_classes": dict(period_counts),
            "quality_tiers": dict(quality_counts),
        },
    )
