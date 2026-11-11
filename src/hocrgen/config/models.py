from __future__ import annotations

from datetime import date
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
    hocrsyngen_batch_path: str | None = None
    modern_intake_manifest: str | None = None
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
    # F8g2: the height floor for a text-region crop of a page (Wikisource decision 12), whose source page itself
    # passes minimum_width and minimum_height. None applies minimum_height to crops too.
    text_region_crop_minimum_height: int | None = Field(default=None, ge=1)
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


class ReportingPathConfig(ConfigBaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str = Field(min_length=1)
    url: str | None = None
    configured: bool = True
    required_operator_action: str = ""

    @model_validator(mode="after")
    def validate_reporting_path(self) -> "ReportingPathConfig":
        if not self.configured and not self.required_operator_action:
            raise ValueError("required_operator_action is required when a reporting path is not configured")
        return self


class PrivateReportingPathConfig(ReportingPathConfig):
    channel: Literal[
        "github_private_vulnerability_reporting",
        "github_private_security_advisory",
        "maintainer_private_contact",
    ]
    verified_at: str = ""
    verification_method: Literal[
        "github_repository_security_settings",
        "maintainer_contact_test",
        "security_advisory_dry_run",
        "",
    ] = ""
    verified_by: str = ""
    verification_valid_until: str = ""
    repository_check_at: str = ""
    repository_check_method: Literal[
        "gh_api_private_vulnerability_reporting",
        "manual_repository_settings_review",
        "",
    ] = ""
    repository_check_result: Literal["enabled", "disabled", "unknown", ""] = ""

    @model_validator(mode="after")
    def validate_private_reporting_path(self) -> "PrivateReportingPathConfig":
        if self.repository_check_result and not self.repository_check_at:
            raise ValueError("repository_check_at is required when repository_check_result is recorded")
        if self.repository_check_result and not self.repository_check_method:
            raise ValueError("repository_check_method is required when repository_check_result is recorded")
        for field_name, value in [
            ("verified_at", self.verified_at),
            ("verification_valid_until", self.verification_valid_until),
            ("repository_check_at", self.repository_check_at),
        ]:
            if value:
                try:
                    date.fromisoformat(value)
                except ValueError as exc:
                    raise ValueError(f"{field_name} must use YYYY-MM-DD format") from exc
        if not self.configured:
            return self
        missing = [
            field
            for field, value in [
                ("url", self.url),
                ("verified_at", self.verified_at),
                ("verification_method", self.verification_method),
                ("verified_by", self.verified_by),
                ("verification_valid_until", self.verification_valid_until),
            ]
            if not value
        ]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(f"configured private reporting paths require verification metadata: {joined}")
        if self.channel in {"github_private_vulnerability_reporting", "github_private_security_advisory"}:
            expected_prefix = "https://github.com/"
            if self.url is None or not self.url.startswith(expected_prefix) or "/security/advisories" not in self.url:
                raise ValueError(
                    "configured GitHub private reporting paths must use a GitHub security advisory URL"
                )
            if self.repository_check_result != "enabled":
                raise ValueError("configured GitHub private reporting paths require an enabled repository check")
        return self


class PublicBetaGovernanceConfig(ConfigBaseModel):
    version: Literal[1] = 1
    public_reporting_path: ReportingPathConfig
    private_reporting_path: PrivateReportingPathConfig


# --- F8g: real-source composition contract ---------------------------------------------------------------


class RealSourceModality(str, Enum):
    """E2d modality tracks. Printed covers machine-set type (typewritten included); handwritten covers manuscripts."""

    printed = "printed"
    handwritten = "handwritten"


class RealSourcePromotion(str, Enum):
    promoted = "promoted"  # moved from review_only into the public path by a planned PR (F8g, later F7d)
    legacy = "legacy"  # an allowed source that predates the contract (B1/B2 NLI, Pinkas, BiblIA)
    not_promoted = "not_promoted"  # known real source still review_only; counts nothing until its promotion PR


class RealSourceEvaluationScope(str, Enum):
    full_hebrew = "full_hebrew"
    character_level_only = "character_level_only"
    per_line = "per_line"  # a page-level default plus per-line scope (BGU Pinkas, decision 8)
    images_only = "images_only"  # no text ships with the item


class RealSourceReleaseTerms(ConfigBaseModel):
    """What every exported item of a source must carry, and the NOTICE paragraph for the source."""

    licence: str = Field(min_length=1)
    attribution_required: bool
    share_alike: bool = False
    evaluation_scope: RealSourceEvaluationScope
    rendered_not_scan: bool = False
    paired_text: Literal["page_text", "page_xml", "none"] = "none"
    # F8e3: ``within_line`` when the paired text's line text is verified but its order of lines and blocks across the
    # page is not (Reshumot); every item must then carry it, and page-order evaluation is excluded.
    reading_order_verified: Literal["within_line", "page"] | None = None
    notice: str = Field(min_length=1)


class RealSourceContractEntry(ConfigBaseModel):
    source_id: str = Field(pattern=r"^[a-z0-9_]+$")
    promotion: RealSourcePromotion
    planning_notation: str = Field(min_length=1)
    modalities: list[RealSourceModality] = Field(min_length=1)
    floor: int = Field(ge=0)
    cap: int = Field(ge=1)
    counts_toward_modality_floors: bool = True
    leakage_group: str = Field(min_length=1)
    release_terms: RealSourceReleaseTerms
    notes: str = ""

    @model_validator(mode="after")
    def validate_floor_and_cap(self) -> "RealSourceContractEntry":
        if self.floor > self.cap:
            raise ValueError(f"{self.source_id}: floor {self.floor} exceeds cap {self.cap}")
        if self.promotion == RealSourcePromotion.not_promoted and self.floor:
            raise ValueError(f"{self.source_id}: a not_promoted source cannot carry a floor")
        if self.release_terms.share_alike and not self.release_terms.attribution_required:
            raise ValueError(f"{self.source_id}: share-alike terms always require attribution")
        return self


class RealSourceContract(ConfigBaseModel):
    """``real_source_composition.v2`` (F8g): per-source floors and caps by modality, replacing the fixed
    27 / 27 / 26 NLI / Pinkas / BiblIA allocation for public-beta readiness.

    A source's public payload items count toward ``min_real_items`` only up to its ``cap``; its ``floor`` must be met
    outright. Modality floors (E2d printed / handwritten tracks) are counted over the capped items of sources that
    ``counts_toward_modality_floors``. The F1 trial keeps its own historical allocation (``hocrgen.source_ops``).
    """

    version: Literal[1] = 1
    contract_id: Literal["real_source_composition.v2"] = "real_source_composition.v2"
    planning_notation: str = Field(min_length=1)
    decision_record: str = Field(min_length=1)
    min_real_items: int = Field(ge=1)
    modality_content_types: dict[RealSourceModality, list[str]]
    modality_floors: dict[RealSourceModality, int]
    sources: list[RealSourceContractEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self) -> "RealSourceContract":
        ids = [entry.source_id for entry in self.sources]
        duplicates = sorted({source_id for source_id in ids if ids.count(source_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate real-source contract entries: {', '.join(duplicates)}")
        if set(self.modality_content_types) != set(RealSourceModality):
            raise ValueError("modality_content_types must name every modality")
        seen: dict[str, RealSourceModality] = {}
        for modality, content_types in self.modality_content_types.items():
            for content_type in content_types:
                if content_type in seen:
                    raise ValueError(f"content type {content_type} maps to both {seen[content_type].value} and {modality.value}")
                seen[content_type] = modality
        if any(value < 0 for value in self.modality_floors.values()):
            raise ValueError("modality floors must be non-negative")
        if sum(self.modality_floors.values()) > self.min_real_items:
            raise ValueError("modality floors exceed min_real_items")
        if sum(entry.floor for entry in self.sources) > self.min_real_items:
            raise ValueError("per-source floors exceed min_real_items")
        for modality, floor in self.modality_floors.items():
            reachable = sum(
                entry.cap
                for entry in self.sources
                if entry.promotion != RealSourcePromotion.not_promoted
                and entry.counts_toward_modality_floors
                and modality in entry.modalities
            )
            if reachable < floor:
                raise ValueError(f"{modality.value} floor {floor} cannot be reached under the caps ({reachable})")
        reachable_total = sum(entry.cap for entry in self.sources if entry.promotion != RealSourcePromotion.not_promoted)
        if reachable_total < self.min_real_items:
            raise ValueError(f"min_real_items {self.min_real_items} cannot be reached under the caps ({reachable_total})")
        return self

    def entry(self, source_id: str) -> RealSourceContractEntry | None:
        return next((entry for entry in self.sources if entry.source_id == source_id), None)

    def modality_for_content_type(self, content_type: str | None) -> RealSourceModality | None:
        for modality, content_types in self.modality_content_types.items():
            if content_type in content_types:
                return modality
        return None


# --- Decision 0017: evaluation-reserved source units (P-mod), refused as training input --------------------------


class EvalUnitStatus(str, Enum):
    eval = "eval"
    non_eval = "non_eval"
    unassigned = "unassigned"


# A unit in either of these statuses never reaches train or any training input (decision 0017's usage rule).
EVAL_RESERVED_STATUSES = frozenset({EvalUnitStatus.eval, EvalUnitStatus.unassigned})

EVAL_RESERVED_UNIT_PREFIXES = {
    "reshumot_born_digital": "reshumot:",
    "knesset_committee_protocols_pre1976": "knesset_protocol:",
}


class EvalSplitFileRecord(ConfigBaseModel):
    """The eval-owned split file a registry was generated from. Its name and sha256 are what identify it."""

    name: str = Field(pattern=r"^pmod_unit_split_v\d+\.json$")
    split_version: str = Field(pattern=r"^v\d+$")
    schema_version: str = Field(min_length=1)  # as the file states it (v1 said ...v0; from v2 it names the file format)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    packaged_copy: str = Field(min_length=1)  # path of the committed copy, relative to the hocrgen package


class EvalReservedSource(ConfigBaseModel):
    source_id: Literal["reshumot_born_digital", "knesset_committee_protocols_pre1976"]
    unit: str = Field(min_length=1)  # what one unit is: a booklet, a protocol
    eval_units: list[str]
    non_eval_units: list[str]

    @model_validator(mode="after")
    def validate_units(self) -> "EvalReservedSource":
        prefix = EVAL_RESERVED_UNIT_PREFIXES[self.source_id]
        for name, units in (("eval_units", self.eval_units), ("non_eval_units", self.non_eval_units)):
            if units != sorted(set(units)):
                raise ValueError(f"{self.source_id} {name} must be sorted and unique")
            wrong = [unit for unit in units if not unit.startswith(prefix)]
            if wrong:
                raise ValueError(f"{self.source_id} {name} must start with {prefix!r}: {wrong[:3]}")
        both = sorted(set(self.eval_units) & set(self.non_eval_units))
        if both:
            raise ValueError(f"{self.source_id} units are both eval and non_eval: {both}")
        return self


class EvalReservedUnitsRegistry(ConfigBaseModel):
    """``eval_reserved_units.v1`` (heocr-engine decision 0017): the P-mod evaluation units of the sources hocrgen
    ships, generated from heocr-eval's split file by ``hocrgen.tools.eval_reserved_units sync``, never by hand.

    An ``eval`` unit and an ``unassigned`` unit (a unit of a listed source in neither list) are reserved: the release
    split pins them to ``eval_reserved``, and every training-input builder refuses them. A ``non_eval`` unit is open.
    """

    version: Literal[1] = 1
    registry_id: Literal["eval_reserved_units.v1"] = "eval_reserved_units.v1"
    generated_by: Literal["hocrgen.tools.eval_reserved_units sync"] = "hocrgen.tools.eval_reserved_units sync"
    split_file: EvalSplitFileRecord
    decision: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    usage: str = Field(min_length=1)  # the split file's usage rule, verbatim
    unassigned_rule: str = Field(min_length=1)  # the usage rule's sentence on unassigned units, verbatim
    reserved_split: Literal["eval_reserved"] = "eval_reserved"
    sources: list[EvalReservedSource] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_registry(self) -> "EvalReservedUnitsRegistry":
        ids = [source.source_id for source in self.sources]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate eval-reserved source ids")
        if self.unassigned_rule not in self.usage:
            raise ValueError("unassigned_rule must be quoted from usage")
        return self

    def source(self, source_id: str) -> EvalReservedSource | None:
        return next((source for source in self.sources if source.source_id == source_id), None)

    def governs(self, source_id: str | None) -> bool:
        return source_id is not None and self.source(source_id) is not None

    def status(self, source_id: str, unit_id: str | None) -> EvalUnitStatus | None:
        """``None`` for a source the split file does not cover; otherwise the unit's status (no unit: unassigned)."""

        source = self.source(source_id)
        if source is None:
            return None
        if unit_id in set(source.eval_units):
            return EvalUnitStatus.eval
        if unit_id in set(source.non_eval_units):
            return EvalUnitStatus.non_eval
        return EvalUnitStatus.unassigned


# --- F8g: works whose text or glyphs feed synthetic training (leakage cross-check) --------------------------


class SyntheticTrainingProducer(ConfigBaseModel):
    producer: str = Field(min_length=1)
    plan: str = Field(min_length=1)
    status: Literal["planned", "active", "retired"]
    exclusion_list: str | None = None  # where the producer publishes its work-level exclusion list, once built


class SyntheticTrainingWork(ConfigBaseModel):
    work_id: str = Field(min_length=1)  # the producer's own id, e.g. pby:1234 (Project Ben-Yehuda) or hash:writer:...
    producer: str = Field(min_length=1)
    title: str = ""
    match_keys: list[str] = Field(min_length=1)  # work-group keys of real items: nli_record:<id>, commons_file:<sha1>, ...
    corpus_build: str | None = None
    recorded_by: str = Field(min_length=1)
    recorded_at: date

    @field_validator("match_keys")
    @classmethod
    def validate_match_keys(cls, keys: list[str]) -> list[str]:
        for key in keys:
            kind, _, value = key.partition(":")
            if not kind or not value:
                raise ValueError(f"match key {key!r} must be <kind>:<value>")
        return keys


class SyntheticTrainingWorkRegistry(ConfigBaseModel):
    """``synthetic_training_works.v1`` (F8g): real works whose text or glyphs feed synthetic training.

    A real item whose work-group keys match a registered work is kept in ``train`` with its whole split group and is
    never benchmark or holdout material. Producers record works here from their corpus builds (hocrsyngen S15a's
    Project Ben-Yehuda work-level exclusion list; HASH writer groups through hletterscript, F7d).
    """

    version: Literal[1] = 1
    registry_id: Literal["synthetic_training_works.v1"] = "synthetic_training_works.v1"
    producers: list[SyntheticTrainingProducer] = Field(default_factory=list)
    works: list[SyntheticTrainingWork] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_registry(self) -> "SyntheticTrainingWorkRegistry":
        producers = {producer.producer for producer in self.producers}
        ids = [work.work_id for work in self.works]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate synthetic-training work ids")
        unknown = sorted({work.producer for work in self.works} - producers)
        if unknown:
            raise ValueError(f"synthetic-training works name unregistered producers: {', '.join(unknown)}")
        return self

    def match_keys(self) -> dict[str, list[str]]:
        """Each registered match key, with the work ids that carry it."""

        keys: dict[str, list[str]] = {}
        for work in self.works:
            for key in work.match_keys:
                keys.setdefault(key, []).append(work.work_id)
        return keys
