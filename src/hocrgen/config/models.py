from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceStatus(str, Enum):
    allowed = "allowed"
    review_only = "review_only"
    blocked = "blocked"


class SourceOperationalStatus(str, Enum):
    active = "active"
    frozen = "frozen"
    degraded = "degraded"


class RightsClassification(str, Enum):
    open = "open"
    open_with_attribution = "open_with_attribution"
    sharealike = "sharealike"
    restricted_review_only = "restricted_review_only"
    blocked = "blocked"


class PublishTarget(str, Enum):
    huggingface = "huggingface"
    github_dataset_repo = "github_dataset_repo"


class RasterFormat(str, Enum):
    png = "png"
    jpeg = "jpeg"


class PreviewGenerationMode(str, Enum):
    copy_if_supported = "copy_if_supported"
    skip = "skip"


class PrivacyFlag(str, Enum):
    clear = "clear"
    possible_personal_data = "possible_personal_data"
    needs_review = "needs_review"
    blocked_sensitive = "blocked_sensitive"


class RightsStrategy(ConfigBaseModel):
    type: Literal["exact_match", "contains", "manual_review"]
    values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_values(self) -> "RightsStrategy":
        if self.type != "manual_review" and not self.values:
            raise ValueError("rights_strategy.values must not be empty unless type is manual_review")
        return self


class SourceSettings(ConfigBaseModel):
    seed_manifest: str | None = None
    records_path: str | None = None
    synthetic_batch_size: int | None = Field(default=None, ge=1)
    synthetic_seed: int | None = None
    template_ids: list[str] = Field(default_factory=list)
    font_manifest: str | None = None
    text_corpus_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SourceHealthExpectations(ConfigBaseModel):
    min_candidates: int | None = Field(default=None, ge=0)
    min_assets: int | None = Field(default=None, ge=0)


class SourceOperationsConfig(ConfigBaseModel):
    operational_status: SourceOperationalStatus = SourceOperationalStatus.active
    operational_reason: str = ""
    health_expectations: SourceHealthExpectations = Field(default_factory=SourceHealthExpectations)

    @model_validator(mode="after")
    def validate_operational_reason(self) -> "SourceOperationsConfig":
        if self.operational_status != SourceOperationalStatus.active and not self.operational_reason:
            raise ValueError("operational_reason is required when operational_status is frozen or degraded")
        return self


class SourceConfig(ConfigBaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    fetcher: str = Field(pattern=r"^[a-z0-9_]+$")
    status: SourceStatus
    default_public_release: bool
    allowed_content_types: list[str] = Field(min_length=1)
    rights_strategy: RightsStrategy
    normalized_license: str
    rights_classification: RightsClassification
    requires_manual_review: bool
    settings: SourceSettings = Field(default_factory=SourceSettings)
    source_operations: SourceOperationsConfig = Field(default_factory=SourceOperationsConfig)


class SourceRegistry(ConfigBaseModel):
    version: Literal[1] = 1
    sources: list[SourceConfig] = Field(min_length=1)

    @field_validator("sources")
    @classmethod
    def validate_unique_source_ids(cls, sources: list[SourceConfig]) -> list[SourceConfig]:
        seen: set[str] = set()
        for source in sources:
            if source.id in seen:
                raise ValueError(f"duplicate source id: {source.id}")
            seen.add(source.id)
        return sources


class SplitPolicy(ConfigBaseModel):
    train: float = Field(ge=0, le=1)
    validation: float = Field(ge=0, le=1)
    test: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> "SplitPolicy":
        total = round(self.train + self.validation + self.test, 6)
        if total != 1.0:
            raise ValueError("split_policy values must sum to 1.0")
        return self


class ReleaseProfile(ConfigBaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    description: str
    include_sources: list[str] = Field(min_length=1)
    exclude_sources: list[str]
    allowed_rights_classifications: list[RightsClassification] = Field(min_length=1)
    synthetic_fraction_max: float = Field(ge=0, le=1)
    privacy_mode: Literal["conservative", "review", "off"]
    publish_targets: list[PublishTarget]
    split_policy: SplitPolicy
    allow_unknown_rights: bool = False
    require_public_release_licenses: bool = True

    @model_validator(mode="after")
    def validate_sources(self) -> "ReleaseProfile":
        overlap = set(self.include_sources) & set(self.exclude_sources)
        if overlap:
            joined = ", ".join(sorted(overlap))
            raise ValueError(f"profile has source ids in both include_sources and exclude_sources: {joined}")
        return self


class LicenseEntry(ConfigBaseModel):
    id: str
    name: str
    rights_classification: RightsClassification
    public_release_allowed: bool
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""


class LicenseRegistry(ConfigBaseModel):
    version: Literal[1] = 1
    licenses: list[LicenseEntry] = Field(min_length=1)


class PreviewPolicy(ConfigBaseModel):
    mode: PreviewGenerationMode
    require_for_raster: bool = False
    require_for_svg: bool = False


class QualityThresholds(ConfigBaseModel):
    version: Literal[1] = 1
    minimum_width: int = Field(ge=1)
    minimum_height: int = Field(ge=1)
    minimum_bytes: int = Field(ge=1)
    allowed_raster_formats: list[RasterFormat] = Field(min_length=1)
    allow_svg: bool = True
    preview_policy: PreviewPolicy


class PrivacyRule(ConfigBaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    flag: PrivacyFlag
    patterns: list[str] = Field(min_length=1)
    fields: list[Literal["title", "description", "metadata", "source_url"]] = Field(min_length=1)
    applies_to_sources: list[str] = Field(default_factory=list)
    applies_to_periods: list[Literal["modern", "historical"]] = Field(default_factory=list)
    case_sensitive: bool = False


class PrivacyRules(ConfigBaseModel):
    version: Literal[1] = 1
    source_defaults: dict[str, PrivacyFlag] = Field(default_factory=dict)
    rules: list[PrivacyRule] = Field(default_factory=list)
