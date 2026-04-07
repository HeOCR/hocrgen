from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hocrgen.config.models import RightsClassification


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
