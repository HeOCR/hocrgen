from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import SourceConfig, SourceStatus
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord
from hocrgen.normalize.images import detect_asset_metadata
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file


MODERN_CONSENT_LICENSE = "HEOCR-CONSENT-OPEN"


class ModernIntakeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ModernScanMetadata(ModernIntakeModel):
    capture_resolution_dpi: int | None = Field(default=None, ge=1)
    capture_device: str | None = None
    color_mode: Literal["color", "grayscale"]
    orientation: Literal["right_side_up"]
    page_visible: bool
    hands_or_background_visible: bool = False
    aggressive_filtering: bool = False

    @model_validator(mode="after")
    def validate_scan_quality_flags(self) -> "ModernScanMetadata":
        if not self.page_visible:
            raise ValueError("page_visible must be true")
        if self.hands_or_background_visible:
            raise ValueError("hands_or_background_visible must be false")
        if self.aggressive_filtering:
            raise ValueError("aggressive_filtering must be false")
        return self


class ModernCompositionMetadata(ModernIntakeModel):
    prompt_id: str = Field(min_length=1)
    page_type: Literal["prompted_lines", "paragraph_prose", "list_or_table", "envelope_or_label", "mixed_printed_handwritten"]
    script_style: Literal["block_print", "cursive_like", "mixed_print_cursive", "natural_variation"]
    language_mix: Literal["hebrew_only", "hebrew_with_arabic_numerals", "hebrew_with_latin_fragments", "mixed_hebrew_english"]
    page_condition: Literal["clean_scan", "mild_skew", "varied_writing_instrument", "lined_paper", "plain_paper", "smartphone_capture"]


class ModernIntakeRecord(ModernIntakeModel):
    source_item_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9_.:-]+$")
    title: str = Field(min_length=1)
    asset_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: Literal["image/jpeg", "image/png"]
    contributor_eligibility: Literal["adult_contributor"]
    consent_artifact_id: str | None = None
    institutional_agreement_id: str | None = None
    consent_effective_date: date
    consent_scope: Literal["image_prompt_metadata_public_reuse"]
    release_terms_version: str = Field(min_length=1)
    normalized_license: Literal["HEOCR-CONSENT-OPEN"]
    contributor_wrote_sample: bool
    approved_prompt_text: bool
    private_evidence_locator: str = Field(min_length=1)
    privacy_screening_status: Literal["clear"]
    privacy_reviewer_id: str = Field(min_length=1)
    privacy_review_timestamp: datetime
    unresolved_privacy_flags: list[str] = Field(default_factory=list)
    operator_review_status: Literal["intake_ready"]
    operator_reviewer_id: str = Field(min_length=1)
    operator_review_timestamp: datetime
    takedown_status: Literal["none"]
    takedown_request_date: date | None = None
    affected_future_release_versions: list[str] = Field(default_factory=list)
    public_inclusion_state: Literal["candidate"]
    first_release_version: str | None = None
    last_release_version: str | None = None
    scan: ModernScanMetadata
    composition: ModernCompositionMetadata
    text_metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("asset_path")
    @classmethod
    def validate_asset_path(cls, path: str) -> str:
        _portable_relative_path(path, "asset_path")
        return path

    @field_validator("private_evidence_locator")
    @classmethod
    def validate_private_evidence_locator(cls, value: str) -> str:
        if "/" in value or "\\" in value or "://" in value or value.startswith("."):
            raise ValueError("private_evidence_locator must be an opaque private reference, not a path")
        return value

    @field_validator("privacy_review_timestamp", "operator_review_timestamp")
    @classmethod
    def validate_review_timestamp_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("review timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_policy_state(self) -> "ModernIntakeRecord":
        if not (self.consent_artifact_id or self.institutional_agreement_id):
            raise ValueError("consent_artifact_id or institutional_agreement_id is required")
        if not self.contributor_wrote_sample:
            raise ValueError("contributor_wrote_sample must be true")
        if not self.approved_prompt_text:
            raise ValueError("approved_prompt_text must be true")
        if self.unresolved_privacy_flags:
            raise ValueError("unresolved_privacy_flags must be empty")
        if self.takedown_request_date is not None or self.affected_future_release_versions:
            raise ValueError("unresolved takedown/removal state is not allowed for intake candidates")
        if self.first_release_version is not None or self.last_release_version is not None:
            raise ValueError("F3b intake records must not claim release inclusion")
        for key, value in self.text_metadata.items():
            if value != unicodedata.normalize("NFC", value):
                raise ValueError(f"text_metadata.{key} must be NFC-normalized")
        return self


class ModernIntakeManifest(ModernIntakeModel):
    schema_version: Literal[1]
    batch_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    operator_id: str = Field(min_length=1)
    collection_date: date
    collection_method: Literal["operator_manifest"]
    consent_terms_version: str = Field(min_length=1)
    records: list[ModernIntakeRecord] = Field(min_length=1)

    @field_validator("batch_id", "source_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if value != unicodedata.normalize("NFC", value):
            raise ValueError("identifier must be NFC-normalized")
        return value

    @model_validator(mode="after")
    def validate_unique_items(self) -> "ModernIntakeManifest":
        seen: set[str] = set()
        for record in self.records:
            if record.source_item_id in seen:
                raise ValueError(f"duplicate source_item_id: {record.source_item_id}")
            seen.add(record.source_item_id)
        return self


@dataclass(frozen=True)
class ModernIntakeBatch:
    manifest_path: Path
    manifest: ModernIntakeManifest
    candidate_count: int
    asset_count: int


def validate_modern_intake_source_config(source: SourceConfig) -> None:
    if source.fetcher != "modern_handwriting_intake":
        return
    if source.status != SourceStatus.review_only:
        raise StageExecutionError("modern_handwriting_intake sources must use status: review_only")
    if source.default_public_release:
        raise StageExecutionError("modern_handwriting_intake sources must set default_public_release: false")
    if not source.requires_manual_review:
        raise StageExecutionError("modern_handwriting_intake sources must set requires_manual_review: true")
    if not source.settings.modern_intake_manifest:
        raise StageExecutionError("modern_handwriting_intake sources require settings.modern_intake_manifest")
    if source.normalized_license != MODERN_CONSENT_LICENSE:
        raise StageExecutionError(f"modern_handwriting_intake sources must use normalized_license: {MODERN_CONSENT_LICENSE}")


def validate_modern_intake_manifest(source: SourceConfig, bundle: ConfigBundle) -> ModernIntakeBatch:
    validate_modern_intake_source_config(source)
    manifest_path = bundle.resolve_path(source.settings.modern_intake_manifest or "")
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StageExecutionError(f"modern intake manifest is missing: {manifest_path}") from exc
    except JSONDecodeError as exc:
        raise StageExecutionError(
            f"modern intake manifest has invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise StageExecutionError(f"modern intake manifest could not be read: {exc}") from exc
    try:
        manifest = ModernIntakeManifest.model_validate(payload)
    except ValidationError as exc:
        raise StageExecutionError(f"modern intake manifest validation failed: {exc}") from exc
    if manifest.source_id != source.id:
        raise StageExecutionError(f"modern intake manifest source_id {manifest.source_id!r} does not match source {source.id!r}")

    manifest_root = manifest_path.parent.resolve()
    for record in manifest.records:
        asset_path = _asset_path(manifest_path, record.asset_path)
        if not asset_path.is_relative_to(manifest_root):
            raise StageExecutionError(f"modern intake asset escapes manifest directory for {record.source_item_id}: {record.asset_path}")
        if not asset_path.is_file():
            raise StageExecutionError(f"modern intake asset is missing for {record.source_item_id}: {record.asset_path}")
        actual_sha = sha256_file(asset_path)
        if actual_sha != record.sha256:
            raise StageExecutionError(
                f"modern intake asset sha256 mismatch for {record.source_item_id}: expected {record.sha256}, got {actual_sha}"
            )
        try:
            technical_metadata = detect_asset_metadata(asset_path)
        except (OSError, ValueError) as exc:
            raise StageExecutionError(f"modern intake asset is not a readable JPEG/PNG for {record.source_item_id}: {exc}") from exc
        if technical_metadata.media_type != record.media_type:
            raise StageExecutionError(
                f"modern intake asset media type mismatch for {record.source_item_id}: "
                f"expected {record.media_type}, got {technical_metadata.media_type}"
            )
    return ModernIntakeBatch(
        manifest_path=manifest_path,
        manifest=manifest,
        candidate_count=len(manifest.records),
        asset_count=len(manifest.records),
    )


class ModernHandwritingIntakeFetcher:
    def __init__(self) -> None:
        self._validated_batches: dict[tuple[str, Path, int, int], ModernIntakeBatch] = {}

    def _validated_batch(self, source: SourceConfig, bundle: ConfigBundle) -> ModernIntakeBatch:
        manifest_path = bundle.resolve_path(source.settings.modern_intake_manifest or "")
        try:
            manifest_stat = manifest_path.stat()
        except FileNotFoundError:
            return validate_modern_intake_manifest(source, bundle)
        key = (source.id, manifest_path.resolve(), manifest_stat.st_mtime_ns, manifest_stat.st_size)
        batch = self._validated_batches.get(key)
        if batch is None:
            batch = validate_modern_intake_manifest(source, bundle)
            self._validated_batches[key] = batch
        return batch

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        batch = self._validated_batch(source, bundle)
        records = batch.manifest.records[: options.max_items] if options.max_items is not None else batch.manifest.records
        return [
            CandidateRecord(
                candidate_id=f"{source.id}:{record.source_item_id}",
                source_id=source.id,
                source_item_id=record.source_item_id,
                source_url=f"modern-intake://{batch.manifest.batch_id}/{record.source_item_id}",
                discovery_method="modern_handwriting_intake_manifest_v1",
                title=record.title,
                raw_metadata={
                    "batch_id": batch.manifest.batch_id,
                    "collection_method": batch.manifest.collection_method,
                    "modern_intake_manifest_schema_version": batch.manifest.schema_version,
                    "source_item_id": record.source_item_id,
                },
            )
            for record in records
        ]

    def fetch_candidate_metadata(
        self,
        source: SourceConfig,
        bundle: ConfigBundle,
        candidates,
        options: StageOptions,
    ) -> list[EnrichedCandidateRecord]:
        batch = self._validated_batch(source, bundle)
        records = {record.source_item_id: record for record in batch.manifest.records}
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            record = records.get(candidate.source_item_id)
            if record is None:
                raise StageExecutionError(f"modern intake candidate is missing from manifest: {candidate.source_item_id}")
            asset_path = _asset_path(batch.manifest_path, record.asset_path)
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=record.normalized_license,
                    asset_references=[
                        AssetReference(
                            reference=record.asset_path,
                            resolved_path=str(asset_path),
                            media_type=record.media_type,
                        )
                    ],
                    metadata=_record_metadata(batch.manifest, record),
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        del source, bundle, options
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            acquired_assets: list[AcquiredAsset] = []
            for asset_index, asset in enumerate(item.asset_references, start=1):
                source_path = Path(asset.resolved_path or "")
                destination = output_dir / item.item_id / f"page_{asset_index:04d}{source_path.suffix.lower()}"
                copy_file(source_path, destination)
                acquired_assets.append(
                    AcquiredAsset(
                        item_id=item.item_id,
                        path=str(destination),
                        sha256=sha256_file(destination),
                        media_type=asset.media_type,
                    )
                )
            acquired_items.append(AcquiredItemRecord(**item.model_dump(), acquired_assets=acquired_assets))
        return acquired_items


def _record_metadata(manifest: ModernIntakeManifest, record: ModernIntakeRecord) -> dict[str, object]:
    metadata = {
        "collection_date": manifest.collection_date.isoformat(),
        "collection_method": manifest.collection_method,
        "consent_artifact_id": record.consent_artifact_id,
        "consent_effective_date": record.consent_effective_date.isoformat(),
        "consent_terms_version": manifest.consent_terms_version,
        "institutional_agreement_id": record.institutional_agreement_id,
        "modern_intake_batch_id": manifest.batch_id,
        "modern_intake_operator_id": manifest.operator_id,
        "normalized_license": record.normalized_license,
        "operator_review_status": record.operator_review_status,
        "period": "modern",
        "privacy_screening_status": record.privacy_screening_status,
        "public_inclusion_state": record.public_inclusion_state,
        "scan": record.scan.model_dump(mode="json"),
        "composition": record.composition.model_dump(mode="json"),
        "takedown_status": record.takedown_status,
    }
    if record.text_metadata:
        metadata["text_metadata_sha256"] = {
            key: sha256(value.encode("utf-8")).hexdigest() for key, value in sorted(record.text_metadata.items())
        }
    return {key: value for key, value in metadata.items() if value is not None}


def _asset_path(manifest_path: Path, asset_reference: str) -> Path:
    return (manifest_path.parent / asset_reference).resolve()


def _portable_relative_path(path: str, field_label: str) -> None:
    parsed = PurePosixPath(path)
    if (
        not path
        or path != path.strip()
        or "\\" in path
        or "://" in path
        or (len(path) >= 2 and path[0].isalpha() and path[1] == ":")
        or parsed.is_absolute()
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or path.startswith("~")
    ):
        raise ValueError(f"{field_label} must be a source-relative portable path")
