from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from hocrgen.config.models import PrivacyFlag, RightsClassification


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AssetReference(ManifestModel):
    reference: str
    resolved_path: str | None = None
    media_type: str = "image/svg+xml"


class CandidateRecord(ManifestModel):
    candidate_id: str
    source_id: str
    source_item_id: str
    source_url: str
    discovery_method: str
    title: str | None = None
    fixture_path: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)


class EnrichedCandidateRecord(CandidateRecord):
    raw_rights_text: str | None = None
    asset_references: list[AssetReference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ItemRecord(EnrichedCandidateRecord):
    item_id: str
    normalized_license: str
    rights_classification: RightsClassification
    eligibility: str
    eligibility_reason: str
    is_synthetic: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)


class AcquiredAsset(ManifestModel):
    item_id: str
    path: str
    sha256: str
    media_type: str = "image/svg+xml"


class AcquiredItemRecord(ItemRecord):
    acquired_assets: list[AcquiredAsset] = Field(default_factory=list)


class NormalizedAssetRecord(ManifestModel):
    item_id: str
    source_asset_path: str
    normalized_asset_path: str
    asset_format: str
    media_type: str
    width: int | None = None
    height: int | None = None
    file_size_bytes: int
    sha256: str
    is_vector: bool = False
    normalization_action: str
    preview_generated: bool = False
    preview_path: str | None = None
    preview_action: str | None = None
    preview_reason: str | None = None


class NormalizedItemRecord(AcquiredItemRecord):
    normalized_assets: list[NormalizedAssetRecord] = Field(default_factory=list)
    qa_status: str
    qa_fail_reasons: list[str] = Field(default_factory=list)


class CuratedItemRecord(NormalizedItemRecord):
    content_fingerprint: str
    dedupe_cluster_id: str | None = None
    dedupe_status: Literal["retained", "duplicate"]
    canonical_item_id: str
    split: Literal["train", "validation", "test"] | None = None
    split_group_id: str | None = None


class DuplicateRelationRecord(ManifestModel):
    cluster_id: str
    canonical_item_id: str
    duplicate_item_id: str
    reason: Literal["exact_asset_sequence_match"]
    content_fingerprint: str


class DuplicateClusterRecord(ManifestModel):
    cluster_id: str
    canonical_item_id: str
    member_item_ids: list[str] = Field(min_length=2)
    method: Literal["exact"] = "exact"


class SplitAssignmentRecord(ManifestModel):
    item_id: str
    split: Literal["train", "validation", "test"]
    split_group_id: str
    dedupe_cluster_id: str | None = None


class ClassifiedItemRecord(CuratedItemRecord):
    content_class: Literal["handwritten", "printed", "mixed"]
    content_confidence: float = Field(ge=0, le=1)
    period_class: Literal["modern", "historical"]
    period_confidence: float = Field(ge=0, le=1)
    language_class: Literal["hebrew_only", "mixed_language"]
    language_confidence: float = Field(ge=0, le=1)
    quality_score: float = Field(ge=0, le=1)
    quality_tier: Literal["low", "medium", "high"]
    classification_review_reasons: list[str] = Field(default_factory=list)


class PrivacyScannedItemRecord(ClassifiedItemRecord):
    privacy_flag: PrivacyFlag
    privacy_reasons: list[str] = Field(default_factory=list)
    privacy_decision: Literal["release_ready", "review_required", "blocked"]


class ReviewQueueRecord(ManifestModel):
    review_item_id: str
    item_id: str
    source_id: str
    canonical_item_id: str
    split_group_id_pre_review: str
    review_reasons: list[str] = Field(default_factory=list)
    suggested_decision: Literal["needs_privacy_review", "needs_classification_review", "needs_policy_review"]
    privacy_flag: PrivacyFlag
    classification_summary: dict[str, Any] = Field(default_factory=dict)
    preview_paths: list[str] = Field(default_factory=list)
    source_url: str
    title: str | None = None


class ReviewDecisionRecord(ManifestModel):
    review_item_id: str
    item_id: str
    decision: Literal["approve", "reject", "needs_legal_review", "needs_privacy_review", "defer"]
    reviewer: str
    timestamp: str
    rationale: str
    notes: str | None = None


class ReviewOverrideRecord(ManifestModel):
    item_id: str
    review_item_id: str | None = None
    reviewer: str
    timestamp: str
    rationale: str
    notes: str | None = None


class ReviewDecisionAuditRecord(ManifestModel):
    item_id: str
    review_item_id: str | None = None
    decision_source: Literal["manual_decision", "allowlist", "blocklist", "automatic_release_ready", "default_unresolved"]
    outcome: Literal["release_ready", "rejected", "unresolved"]
    decision: str | None = None
    reviewer: str | None = None
    timestamp: str | None = None
    rationale: str | None = None
    notes: str | None = None


class ExportedAssetRecord(ManifestModel):
    release_asset_path: str
    media_type: str
    asset_format: str
    release_preview_path: str | None = None


class AlphaExportedItemRecord(PrivacyScannedItemRecord):
    exported_assets: list[ExportedAssetRecord] = Field(default_factory=list)


class AlphaReleaseRecord(ManifestModel):
    version: str
    profile_id: str
    included_sources: list[str] = Field(default_factory=list)
    split_counts: dict[str, int] = Field(default_factory=dict)
    real_items: int
    synthetic_items: int
    review_required_count: int
    blocked_count: int
    hocrgen_commit: str
    exported_at: str
    schema_version: Literal[1] = 1


class ReleaseRemovalRecord(ManifestModel):
    item_id: str
    source_id: str
    previous_split: Literal["train", "validation", "test"] | None = None
    reason: Literal["review_required", "blocked", "duplicate_removed", "selection_limit_excluded", "missing_from_current_run"]


class ReleaseChangedItemRecord(ManifestModel):
    item_id: str
    source_id: str
    split: Literal["train", "validation", "test"] | None = None
    change_types: list[Literal["metadata", "assets", "split"]] = Field(default_factory=list)


class ReleaseDiffRecord(ManifestModel):
    version: str
    previous_version: str | None = None
    generated_at: str
    counts: dict[str, int] = Field(default_factory=dict)
    added_items: list[dict[str, Any]] = Field(default_factory=list)
    removed_items: list[ReleaseRemovalRecord] = Field(default_factory=list)
    changed_items: list[ReleaseChangedItemRecord] = Field(default_factory=list)
    source_deltas: dict[str, dict[str, int]] = Field(default_factory=dict)
    split_deltas: dict[str, dict[str, int]] = Field(default_factory=dict)
    schema_version: Literal[1] = 1


class BenchmarkApprovedItemRecord(ManifestModel):
    item_id: str
    benchmark_split: Literal["train", "validation", "test"]
    rationale: str = Field(min_length=1)


class BenchmarkConfigRecord(ManifestModel):
    benchmark_id: str
    version: Literal[1] = 1
    description: str = Field(min_length=1)
    selection_policy: str = Field(min_length=1)
    review_bar: str = Field(min_length=1)
    stability_policy: dict[str, str] = Field(default_factory=dict)
    approved_items: list[BenchmarkApprovedItemRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_approved_item_ids(self) -> "BenchmarkConfigRecord":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in self.approved_items:
            if item.item_id in seen:
                duplicates.add(item.item_id)
            seen.add(item.item_id)
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate benchmark approved item ids: {joined}")
        return self


class BenchmarkItemRecord(ManifestModel):
    benchmark_id: str
    item_id: str
    source_id: str
    source_item_id: str
    source_url: str
    title: str | None = None
    benchmark_split: Literal["train", "validation", "test"]
    release_split: Literal["train", "validation", "test"]
    split_group_id: str
    is_synthetic: bool
    content_class: Literal["handwritten", "printed", "mixed"]
    quality_tier: Literal["low", "medium", "high"]
    normalized_license: str
    rights_classification: RightsClassification
    rationale: str


class BenchmarkSelectionAuditRecord(ManifestModel):
    benchmark_id: str
    item_id: str
    outcome: Literal["selected"]
    reason: str
    review_bar: str
