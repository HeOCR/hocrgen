from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceStatus(str, Enum):
    allowed = "allowed"
    review_only = "review_only"
    blocked = "blocked"


class RightsClassification(str, Enum):
    open = "open"
    open_with_attribution = "open_with_attribution"
    sharealike = "sharealike"
    review_required = "review_required"
    restricted = "restricted"


class PublishTarget(str, Enum):
    huggingface = "huggingface"
    github_dataset_repo = "github_dataset_repo"


class RightsStrategy(ConfigBaseModel):
    type: Literal["exact_match", "contains", "manual_review"]
    values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_values(self) -> "RightsStrategy":
        if self.type != "manual_review" and not self.values:
            raise ValueError("rights_strategy.values must not be empty unless type is manual_review")
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
    requires_manual_review: bool = False


class SourceRegistry(ConfigBaseModel):
    version: int = 1
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
    exclude_sources: list[str] = Field(default_factory=list)
    allowed_rights_classifications: list[RightsClassification] = Field(min_length=1)
    synthetic_fraction_max: float = Field(ge=0, le=1)
    privacy_mode: Literal["conservative", "review", "off"]
    publish_targets: list[PublishTarget] = Field(default_factory=list)
    split_policy: SplitPolicy

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
    notes: str = ""


class LicenseRegistry(ConfigBaseModel):
    version: int = 1
    licenses: list[LicenseEntry] = Field(min_length=1)
