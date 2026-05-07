from __future__ import annotations

from pathlib import PurePosixPath
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    annotation_status: Literal["not_available", "partial", "available"] = "not_available"
    transcription: "TranscriptionReference | None" = None
    layout_labels: list["LayoutLabelReference"] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_annotation_status(self) -> "ItemRecord":
        _validate_annotation_status_consistency(
            self.annotation_status,
            self.transcription,
            self.layout_labels,
        )
        return self


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
    near_duplicate_cluster_id: str | None = None
    source_group_id: str | None = None
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


class NearDuplicateClusterRecord(ManifestModel):
    cluster_id: str
    member_item_ids: list[str] = Field(min_length=2)
    method: Literal["quantized_thumbnail_hash"] = "quantized_thumbnail_hash"
    status: Literal["manual_review_required"] = "manual_review_required"
    rationale: str


class SourceGroupRecord(ManifestModel):
    group_id: str
    member_item_ids: list[str] = Field(min_length=2)
    source_ids: list[str] = Field(min_length=1)
    status: Literal["split_grouped"] = "split_grouped"
    rationale: str


class SplitAssignmentRecord(ManifestModel):
    item_id: str
    split: Literal["train", "validation", "test"]
    split_group_id: str
    dedupe_cluster_id: str | None = None
    near_duplicate_cluster_id: str | None = None
    source_group_id: str | None = None


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


class ExportedItemRecord(PrivacyScannedItemRecord):
    exported_assets: list[ExportedAssetRecord] = Field(default_factory=list)


AlphaExportedItemRecord = ExportedItemRecord


def validate_release_relative_manifest_path(path: str, *, field_label: str) -> str:
    parsed = PurePosixPath(path)
    if (
        not path
        or path != path.strip()
        or "\\" in path
        or "://" in path
        or re.match(r"^[A-Za-z]:", path)
        or parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or ".work" in parsed.parts
    ):
        raise ValueError(f"{field_label} paths must be release-relative and portable")
    return path


class AnnotationFileReference(ManifestModel):
    path: str
    schema_id: Literal["hocrgen_transcription_v1", "hocrgen_layout_labels_v1"]
    media_type: str = "application/json"
    sha256: str | None = None

    @field_validator("path")
    @classmethod
    def validate_portable_path(cls, path: str) -> str:
        return validate_release_relative_manifest_path(path, field_label="annotation reference")


class TranscriptionReference(AnnotationFileReference):
    schema_id: Literal["hocrgen_transcription_v1"] = "hocrgen_transcription_v1"
    text_direction: Literal["rtl", "ltr", "mixed", "unknown"] = "unknown"
    language: str | None = None


class LayoutLabelReference(AnnotationFileReference):
    schema_id: Literal["hocrgen_layout_labels_v1"] = "hocrgen_layout_labels_v1"
    label_set: str | None = None


class AnnotationManifestItemRecord(ManifestModel):
    item_id: str
    source_id: str
    split: Literal["train", "validation", "test"] | None = None
    annotation_status: Literal["not_available", "partial", "available"]
    transcription: TranscriptionReference | None = None
    layout_labels: list[LayoutLabelReference] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_annotation_status(self) -> "AnnotationManifestItemRecord":
        _validate_annotation_status_consistency(
            self.annotation_status,
            self.transcription,
            self.layout_labels,
        )
        return self


def _validate_annotation_status_consistency(
    annotation_status: Literal["not_available", "partial", "available"],
    transcription: TranscriptionReference | None,
    layout_labels: list[LayoutLabelReference],
) -> None:
    has_references = transcription is not None or bool(layout_labels)
    if annotation_status == "not_available" and has_references:
        raise ValueError("annotation_status not_available cannot include annotation references")
    if annotation_status in {"partial", "available"} and not has_references:
        raise ValueError(f"annotation_status {annotation_status} requires at least one annotation reference")


class AnnotationManifestRecord(ManifestModel):
    subset_id: str
    transcription_required: bool = False
    layout_labels_required: bool = False
    annotated_item_count: int
    transcription_item_count: int
    layout_label_item_count: int
    items: list[AnnotationManifestItemRecord] = Field(default_factory=list)
    schema_version: Literal[1] = 1


class AnnotationPilotTargetReference(ManifestModel):
    path: str
    schema_id: Literal["hocrgen_transcription_v1", "hocrgen_layout_labels_v1"]
    media_type: str = "application/json"

    @field_validator("path")
    @classmethod
    def validate_portable_path(cls, path: str) -> str:
        return validate_release_relative_manifest_path(path, field_label="annotation pilot target")


class AnnotationPilotApprovedItemRecord(ManifestModel):
    item_id: str
    target_subset: Literal["release_ready", "benchmark_v1"]
    tasks: list[Literal["transcription", "layout_labels"]] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    planned_transcription: AnnotationPilotTargetReference | None = None
    planned_layout_labels: AnnotationPilotTargetReference | None = None

    @model_validator(mode="after")
    def validate_tasks_and_targets(self) -> "AnnotationPilotApprovedItemRecord":
        if len(set(self.tasks)) != len(self.tasks):
            raise ValueError(f"duplicate annotation pilot tasks for item {self.item_id}")
        if "transcription" in self.tasks and self.planned_transcription is None:
            raise ValueError(f"annotation pilot item {self.item_id} requires planned_transcription")
        if "transcription" not in self.tasks and self.planned_transcription is not None:
            raise ValueError(f"annotation pilot item {self.item_id} has planned_transcription without transcription task")
        if "layout_labels" in self.tasks and self.planned_layout_labels is None:
            raise ValueError(f"annotation pilot item {self.item_id} requires planned_layout_labels")
        if "layout_labels" not in self.tasks and self.planned_layout_labels is not None:
            raise ValueError(f"annotation pilot item {self.item_id} has planned_layout_labels without layout_labels task")
        if self.planned_transcription is not None and self.planned_transcription.schema_id != "hocrgen_transcription_v1":
            raise ValueError("planned_transcription must use hocrgen_transcription_v1")
        if self.planned_layout_labels is not None and self.planned_layout_labels.schema_id != "hocrgen_layout_labels_v1":
            raise ValueError("planned_layout_labels must use hocrgen_layout_labels_v1")
        return self


class AnnotationPilotConfigRecord(ManifestModel):
    pilot_id: str
    version: Literal[1] = 1
    description: str = Field(min_length=1)
    selection_policy: str = Field(min_length=1)
    annotation_guidance: str = Field(min_length=1)
    transcription_required_for_release: bool = False
    layout_labels_required_for_release: bool = False
    approved_items: list[AnnotationPilotApprovedItemRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_approved_item_ids(self) -> "AnnotationPilotConfigRecord":
        seen: set[str] = set()
        duplicates: set[str] = set()
        for item in self.approved_items:
            if item.item_id in seen:
                duplicates.add(item.item_id)
            seen.add(item.item_id)
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate annotation pilot item ids: {joined}")
        if self.transcription_required_for_release or self.layout_labels_required_for_release:
            raise ValueError("annotation pilots must not require annotations for release")
        return self


class AnnotationPilotItemRecord(ManifestModel):
    pilot_id: str
    item_id: str
    source_id: str
    source_item_id: str
    source_url: str
    title: str | None = None
    target_subset: Literal["release_ready", "benchmark_v1"]
    release_split: Literal["train", "validation", "test"]
    benchmark_id: str | None = None
    benchmark_split: Literal["train", "validation", "test"] | None = None
    tasks: list[Literal["transcription", "layout_labels"]]
    planned_transcription: AnnotationPilotTargetReference | None = None
    planned_layout_labels: AnnotationPilotTargetReference | None = None
    rationale: str


class AnnotationPilotSelectionAuditRecord(ManifestModel):
    pilot_id: str
    item_id: str
    outcome: Literal["selected"]
    reason: str
    target_subset: Literal["release_ready", "benchmark_v1"]


class AnnotationPilotManifestRecord(ManifestModel):
    pilot_id: str
    version: Literal[1] = 1
    description: str
    selection_policy: str
    annotation_guidance: str
    transcription_required_for_release: bool = False
    layout_labels_required_for_release: bool = False
    pilot_item_count: int
    transcription_task_count: int
    layout_label_task_count: int
    items: list[AnnotationPilotItemRecord] = Field(default_factory=list)
    schema_version: Literal[1] = 1


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


class SyntheticReleaseRecord(ManifestModel):
    dataset_id: Literal["HeOCRsynth"] = "HeOCRsynth"
    release_kind: Literal["synthetic_only"] = "synthetic_only"
    synthetic_only: Literal[True] = True
    version: str
    profile_id: str
    included_sources: list[str] = Field(default_factory=list)
    split_counts: dict[str, int] = Field(default_factory=dict)
    real_items: Literal[0] = 0
    synthetic_items: int
    review_required_count: int
    blocked_count: int
    hocrgen_commit: str
    exported_at: str
    schema_version: Literal[1] = 1


class PublicBetaReleaseRecord(ManifestModel):
    dataset_id: Literal["HeOCR"] = "HeOCR"
    release_kind: Literal["public_beta"] = "public_beta"
    version: str
    profile_id: str
    included_sources: list[str] = Field(default_factory=list)
    split_counts: dict[str, int] = Field(default_factory=dict)
    real_items: int
    synthetic_items: int
    review_required_count: int
    blocked_count: int
    readiness_status: Literal["pass", "blocked"]
    publication_allowed: bool
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


BenchmarkLeakageGroupKind = Literal["exact_duplicate", "near_duplicate", "source_group"]
BenchmarkLeakageEnforcementContext = Literal["build_release", "f1_trial", "alpha_export"]
BenchmarkLeakageResolutionAction = Literal[
    "exclude_related_group_from_holdout_public_beta_claims",
    "benchmark_membership_changed_with_reason",
    "accepted_for_operator_only_trial",
]


class BenchmarkLeakageResolutionRecord(ManifestModel):
    resolution_id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    group_kind: BenchmarkLeakageGroupKind
    benchmark_item_ids: list[str] = Field(min_length=1)
    non_benchmark_item_ids: list[str] = Field(min_length=1)
    action: BenchmarkLeakageResolutionAction
    rationale: str = Field(min_length=1)
    accepted_by: str = Field(min_length=1)
    accepted_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_members(self) -> "BenchmarkLeakageResolutionRecord":
        if len(set(self.benchmark_item_ids)) != len(self.benchmark_item_ids):
            raise ValueError(f"duplicate benchmark item ids in leakage resolution {self.resolution_id}")
        if len(set(self.non_benchmark_item_ids)) != len(self.non_benchmark_item_ids):
            raise ValueError(f"duplicate non-benchmark item ids in leakage resolution {self.resolution_id}")
        if set(self.benchmark_item_ids) & set(self.non_benchmark_item_ids):
            raise ValueError(f"leakage resolution {self.resolution_id} overlaps benchmark and non-benchmark item ids")
        return self


class BenchmarkLeakagePolicyRecord(ManifestModel):
    schema_version: Literal[1] = 1
    default_action: Literal["block_unresolved"] = "block_unresolved"
    policy: str = Field(min_length=1)
    accepted_resolutions: list[BenchmarkLeakageResolutionRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_resolutions(self) -> "BenchmarkLeakagePolicyRecord":
        seen: set[tuple[str, str]] = set()
        duplicates: set[str] = set()
        for resolution in self.accepted_resolutions:
            key = (resolution.group_kind, resolution.group_id)
            if key in seen:
                duplicates.add(f"{resolution.group_kind}:{resolution.group_id}")
            seen.add(key)
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise ValueError(f"duplicate benchmark leakage resolutions: {joined}")
        return self


class BenchmarkConfigRecord(ManifestModel):
    benchmark_id: str
    version: Literal[1] = 1
    description: str = Field(min_length=1)
    selection_policy: str = Field(min_length=1)
    review_bar: str = Field(min_length=1)
    stability_policy: dict[str, str] = Field(default_factory=dict)
    benchmark_holdout_leakage_policy: BenchmarkLeakagePolicyRecord = Field(
        default_factory=lambda: BenchmarkLeakagePolicyRecord(
            policy=(
                "Benchmark members must not share exact duplicate, near-duplicate, or source-group membership "
                "with non-benchmark holdout/public-beta candidates unless a repo-tracked accepted resolution "
                "matches the detected group and member sets."
            )
        )
    )
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


ReferenceStatus = Literal["not_available", "draft", "reviewed", "adjudicated", "corrected", "retired"]
ReferenceVisibility = Literal["public", "private_adjudication", "hidden_reference"]
ReferenceAdjudicationStatus = Literal["not_started", "in_review", "needs_adjudication", "adjudicated", "blocked"]
ReferenceReviewStatus = Literal["draft", "in_review", "reviewed", "adjudicated", "blocked", "corrected", "retired"]
ReferenceFlag = Literal[
    "uncertain",
    "illegible",
    "damaged",
    "deleted",
    "marginal",
    "partial",
    "estimated",
    "overlap",
    "needs_adjudication",
]


class BenchmarkReferenceFileReference(ManifestModel):
    path: str
    schema_version: Literal["benchmark_transcription_reference.v1", "benchmark_layout_reference.v1"]
    sha256: str | None = None

    @field_validator("path")
    @classmethod
    def validate_portable_path(cls, path: str) -> str:
        return validate_release_relative_manifest_path(path, field_label="benchmark reference")


class BenchmarkLayoutReferenceFileReference(BenchmarkReferenceFileReference):
    schema_version: Literal["benchmark_layout_reference.v1"] = "benchmark_layout_reference.v1"
    page_ids: list[str] = Field(default_factory=list)


class BenchmarkReferenceManifestItemRecord(ManifestModel):
    reference_id: str
    item_id: str
    source_id: str
    source_item_id: str
    benchmark_split: Literal["train", "validation", "test"] | None = None
    visibility: ReferenceVisibility
    public_reference_status: ReferenceStatus
    transcription_reference: BenchmarkReferenceFileReference | None = None
    layout_label_references: list[BenchmarkLayoutReferenceFileReference] = Field(default_factory=list)
    reviewers: list[str] = Field(default_factory=list)
    adjudication_status: ReferenceAdjudicationStatus
    correction_of: str | None = None
    superseded_by: str | None = None
    change_reason: str | None = None

    @model_validator(mode="after")
    def validate_reference_status(self) -> "BenchmarkReferenceManifestItemRecord":
        has_reference = self.transcription_reference is not None or bool(self.layout_label_references)
        if self.public_reference_status == "not_available" and has_reference:
            raise ValueError(f"benchmark reference item {self.item_id} is not_available but includes reference files")
        if self.public_reference_status in {"reviewed", "adjudicated", "corrected"} and not has_reference:
            raise ValueError(f"benchmark reference item {self.item_id} status requires at least one reference file")
        if self.public_reference_status in {"corrected", "retired"} and not self.change_reason:
            raise ValueError(f"benchmark reference item {self.item_id} {self.public_reference_status} requires change_reason")
        if self.public_reference_status == "corrected" and not self.correction_of:
            raise ValueError(f"benchmark reference item {self.item_id} corrected requires correction_of")
        if self.correction_of and self.superseded_by:
            raise ValueError(f"benchmark reference item {self.item_id} cannot set both correction_of and superseded_by")
        return self


class BenchmarkReferenceContractsRecord(ManifestModel):
    transcription: Literal["benchmark_transcription_reference.v1"]
    layout: Literal["benchmark_layout_reference.v1"]


class BenchmarkReferenceManifestRecord(ManifestModel):
    schema_version: Literal["benchmark_reference_manifest.v1"]
    benchmark_id: str
    reference_manifest_id: str | None
    release_id: str | None = None
    reference_contracts: BenchmarkReferenceContractsRecord
    items: list[BenchmarkReferenceManifestItemRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_item_ids(self) -> "BenchmarkReferenceManifestRecord":
        seen_item_ids: set[str] = set()
        duplicate_item_ids: set[str] = set()
        seen_reference_ids: set[str] = set()
        duplicate_reference_ids: set[str] = set()
        for item in self.items:
            if item.item_id in seen_item_ids:
                duplicate_item_ids.add(item.item_id)
            seen_item_ids.add(item.item_id)
            if item.reference_id in seen_reference_ids:
                duplicate_reference_ids.add(item.reference_id)
            seen_reference_ids.add(item.reference_id)
        if duplicate_item_ids:
            joined = ", ".join(sorted(duplicate_item_ids))
            raise ValueError(f"duplicate benchmark reference item ids: {joined}")
        if duplicate_reference_ids:
            joined = ", ".join(sorted(duplicate_reference_ids))
            raise ValueError(f"duplicate benchmark reference ids: {joined}")
        return self


class ReferenceNormalizationRecord(ManifestModel):
    unicode: Literal["NFC"]
    text_order: Literal["logical"]


class ReferenceLanguageScriptRecord(ManifestModel):
    language: str
    script: str
    direction: Literal["rtl", "ltr", "mixed"]


class BenchmarkTranscriptionPageRecord(ManifestModel):
    page_id: str
    reading_order: int = Field(ge=1)
    text: str | None = None


class BenchmarkTranscriptionLineRecord(ManifestModel):
    line_id: str
    page_id: str
    reading_order: int = Field(ge=1)
    text: str
    layout_line_id: str | None = None


class BenchmarkTranscriptionSpanRecord(ManifestModel):
    span_id: str
    line_id: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    status: ReferenceFlag
    scoring: str
    note: str | None = None

    @model_validator(mode="after")
    def validate_offsets(self) -> "BenchmarkTranscriptionSpanRecord":
        if self.end < self.start:
            raise ValueError(f"span {self.span_id} end must be greater than or equal to start")
        return self


class BenchmarkReferenceReviewRecord(ManifestModel):
    status: ReferenceReviewStatus
    reviewers: list[str] = Field(default_factory=list)
    adjudicator: str | None = None
    adjudicated_at: str | None = None
    correction_of: str | None = None
    superseded_by: str | None = None
    change_reason: str | None = None


class BenchmarkTranscriptionReferenceRecord(ManifestModel):
    schema_version: Literal["benchmark_transcription_reference.v1"]
    item_id: str
    source_id: str
    source_item_id: str
    normalization: ReferenceNormalizationRecord
    language_scripts: list[ReferenceLanguageScriptRecord] = Field(min_length=1)
    scoring_policy: dict[Literal["uncertain", "illegible", "damaged", "deleted", "marginal"], str]
    pages: list[BenchmarkTranscriptionPageRecord] = Field(min_length=1)
    lines: list[BenchmarkTranscriptionLineRecord] = Field(default_factory=list)
    spans: list[BenchmarkTranscriptionSpanRecord] = Field(default_factory=list)
    review: BenchmarkReferenceReviewRecord

    @model_validator(mode="after")
    def validate_links_and_offsets(self) -> "BenchmarkTranscriptionReferenceRecord":
        page_ids = {page.page_id for page in self.pages}
        line_ids: set[str] = set()
        line_text_by_id: dict[str, str] = {}
        for line in self.lines:
            if line.page_id not in page_ids:
                raise ValueError(f"transcription line {line.line_id} references unknown page_id {line.page_id}")
            if line.line_id in line_ids:
                raise ValueError(f"duplicate transcription line id: {line.line_id}")
            line_ids.add(line.line_id)
            line_text_by_id[line.line_id] = line.text
        for span in self.spans:
            if span.line_id not in line_ids:
                raise ValueError(f"span {span.span_id} references unknown line_id {span.line_id}")
            if span.end > len(line_text_by_id[span.line_id]):
                raise ValueError(f"span {span.span_id} offsets exceed line text length")
        return self


class BenchmarkCoordinateSystemRecord(ManifestModel):
    units: Literal["px"]
    origin: Literal["top_left"]
    x_axis: Literal["right"]
    y_axis: Literal["down"]


class BenchmarkLayoutAssetRecord(ManifestModel):
    asset_id: str
    page_id: str
    path: str
    sha256: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)

    @field_validator("path")
    @classmethod
    def validate_portable_path(cls, path: str) -> str:
        return validate_release_relative_manifest_path(path, field_label="benchmark layout asset")


class BenchmarkBBoxRecord(ManifestModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class BenchmarkPointRecord(ManifestModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)


class BenchmarkGeometryRecord(ManifestModel):
    type: Literal["bbox", "polygon", "baseline", "bbox_polygon", "bbox_baseline", "polygon_baseline"]
    bbox: BenchmarkBBoxRecord | None = None
    polygon: list[BenchmarkPointRecord] = Field(default_factory=list)
    baseline: list[BenchmarkPointRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_declared_geometry(self) -> "BenchmarkGeometryRecord":
        if "bbox" in self.type and self.bbox is None:
            raise ValueError(f"geometry type {self.type} requires bbox")
        if "polygon" in self.type and len(self.polygon) < 3:
            raise ValueError(f"geometry type {self.type} requires at least three polygon points")
        if "baseline" in self.type and len(self.baseline) < 2:
            raise ValueError(f"geometry type {self.type} requires at least two baseline points")
        return self


class BenchmarkLayoutRegionRecord(ManifestModel):
    region_id: str
    page_id: str
    label: str
    reading_order: int = Field(ge=1)
    geometry: BenchmarkGeometryRecord
    flags: list[ReferenceFlag] = Field(default_factory=list)


class BenchmarkLayoutLineRecord(ManifestModel):
    line_id: str
    page_id: str
    region_id: str | None = None
    reading_order: int = Field(ge=1)
    geometry: BenchmarkGeometryRecord
    transcription_line_id: str | None = None
    flags: list[ReferenceFlag] = Field(default_factory=list)


class BenchmarkLayoutReferenceRecord(ManifestModel):
    schema_version: Literal["benchmark_layout_reference.v1"]
    item_id: str
    source_id: str
    source_item_id: str
    coordinate_system: BenchmarkCoordinateSystemRecord
    assets: list[BenchmarkLayoutAssetRecord] = Field(min_length=1)
    regions: list[BenchmarkLayoutRegionRecord] = Field(default_factory=list)
    lines: list[BenchmarkLayoutLineRecord] = Field(default_factory=list)
    words: list[dict[str, Any]] = Field(default_factory=list)
    references: list[dict[str, Any]] = Field(default_factory=list)
    review: BenchmarkReferenceReviewRecord

    @model_validator(mode="after")
    def validate_links(self) -> "BenchmarkLayoutReferenceRecord":
        page_ids = {asset.page_id for asset in self.assets}
        region_ids: set[str] = set()
        for region in self.regions:
            if region.page_id not in page_ids:
                raise ValueError(f"layout region {region.region_id} references unknown page_id {region.page_id}")
            if region.region_id in region_ids:
                raise ValueError(f"duplicate layout region id: {region.region_id}")
            region_ids.add(region.region_id)
        line_ids: set[str] = set()
        for line in self.lines:
            if line.page_id not in page_ids:
                raise ValueError(f"layout line {line.line_id} references unknown page_id {line.page_id}")
            if line.region_id is not None and line.region_id not in region_ids:
                raise ValueError(f"layout line {line.line_id} references unknown region_id {line.region_id}")
            if line.line_id in line_ids:
                raise ValueError(f"duplicate layout line id: {line.line_id}")
            line_ids.add(line.line_id)
        return self


class BenchmarkReferenceStatusItemRecord(ManifestModel):
    reference_id: str | None = None
    item_id: str
    source_id: str
    source_item_id: str
    benchmark_split: Literal["train", "validation", "test"]
    visibility: ReferenceVisibility | None = None
    public_reference_status: ReferenceStatus
    adjudication_status: ReferenceAdjudicationStatus
    has_transcription_reference: bool
    layout_reference_count: int
    reviewer_count: int
    correction_of: str | None = None
    superseded_by: str | None = None
    change_reason: str | None = None


class BenchmarkReferenceStatusArtifactRecord(ManifestModel):
    benchmark_id: str
    reference_manifest_id: str | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    items: list[BenchmarkReferenceStatusItemRecord] = Field(default_factory=list)
    schema_version: Literal[1] = 1
