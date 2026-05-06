from __future__ import annotations

import json
from hashlib import sha256
import unicodedata
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file


MANIFEST_FILENAME = "generation_manifest.json"
GENERATION_MANIFEST_VERSION = "1.0"
PROJECT_SYNTHETIC_LICENSE = "PROJECT-SYNTHETIC"
LEGACY_SOURCE_ITEM_ID_PREFIX = "synthetic-"


class HocrsyngenManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HocrsyngenTextMetadata(HocrsyngenManifestModel):
    logical_order: str = Field(min_length=1)
    script: Literal["Hebr"]
    language: Literal["he"]
    direction: Literal["rtl"]
    unicode_normalization: Literal["NFC"]

    @model_validator(mode="after")
    def validate_logical_order_nfc(self) -> "HocrsyngenTextMetadata":
        if self.logical_order != unicodedata.normalize("NFC", self.logical_order):
            raise ValueError("logical_order must be NFC-normalized")
        if "\ufffd" in self.logical_order:
            raise ValueError("logical_order must not contain replacement characters")
        if not _has_hebrew_letters(self.logical_order):
            raise ValueError("logical_order must contain Hebrew letters")
        return self


class HocrsyngenProviderMetadata(HocrsyngenManifestModel):
    provider_name: Literal["hocrsyngen"]
    provider_version: str = Field(min_length=1)
    generation_mode: Literal["offline_manifest_batch"]
    used_network: Literal[False]
    used_rest_service: Literal[False]
    used_gpu: Literal[False]
    used_llm: Literal[False]
    used_diffusion: Literal[False]


class HocrsyngenRenderingMetadata(HocrsyngenManifestModel):
    text_order: Literal["logical"]
    page_direction: Literal["rtl"]
    line_direction: Literal["rtl"]
    bidi_handling: str = Field(min_length=1)
    font_shaping: str = Field(min_length=1)
    layout_family: str = Field(min_length=1)
    line_count: int = Field(ge=1)


class HocrsyngenHebrewCoverage(HocrsyngenManifestModel):
    has_hebrew_letters: bool
    has_final_letters: bool
    has_niqqud: bool
    has_arabic_numerals: bool
    has_punctuation: bool
    has_mixed_ltr: bool


class HocrsyngenPageAsset(HocrsyngenManifestModel):
    page_id: str = Field(min_length=1)
    asset_path: str = Field(min_length=1)
    media_type: Literal["image/jpeg"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_asset_path(self) -> "HocrsyngenPageAsset":
        _portable_asset_path(self.asset_path, "page.asset_path")
        return self


class HocrsyngenSampleProvenance(HocrsyngenManifestModel):
    seed: int
    sample_index: int = Field(ge=0)
    template_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    degradation_preset: str = Field(min_length=1)
    font_id: str = Field(min_length=1)
    source_corpus: str = Field(min_length=1)


class HocrsyngenSampleControls(HocrsyngenManifestModel):
    persona: str | None
    condition: str | None


class HocrsyngenGeneratedSample(HocrsyngenManifestModel):
    sample_id: str = Field(pattern=r"^hocrsyngen-s[0-9]{8}-[0-9]{6}$")
    pages: list[HocrsyngenPageAsset] = Field(min_length=1)
    text: HocrsyngenTextMetadata
    rendering_metadata: HocrsyngenRenderingMetadata
    hebrew_coverage: HocrsyngenHebrewCoverage
    generator_version: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    provenance: HocrsyngenSampleProvenance
    license: Literal["PROJECT-SYNTHETIC"]
    synthetic_disclosure: str = Field(min_length=1)
    controls: HocrsyngenSampleControls

    @model_validator(mode="after")
    def validate_sample_consistency(self) -> "HocrsyngenGeneratedSample":
        if self.recipe_id != self.provenance.recipe_id:
            raise ValueError("recipe_id must match provenance.recipe_id")
        if self.rendering_metadata.line_count != len(self.text.logical_order.splitlines()):
            raise ValueError("rendering_metadata.line_count must match logical_order line count")
        coverage = _hebrew_coverage(self.text.logical_order)
        if self.hebrew_coverage.model_dump() != coverage:
            raise ValueError("hebrew_coverage must match logical_order text")
        return self


class HocrsyngenGenerationManifest(HocrsyngenManifestModel):
    manifest_version: Literal["1.0"]
    generator_name: Literal["hocrsyngen"]
    provider_metadata: HocrsyngenProviderMetadata
    license: Literal["PROJECT-SYNTHETIC"]
    synthetic_disclosure: str = Field(min_length=1)
    samples: list[HocrsyngenGeneratedSample] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_batch_coverage(self) -> "HocrsyngenGenerationManifest":
        required = {
            "has_arabic_numerals": "Arabic numeral",
            "has_final_letters": "Hebrew final-letter",
            "has_hebrew_letters": "Hebrew letter",
            "has_punctuation": "punctuation",
        }
        for field_name, label in required.items():
            if not any(getattr(sample.hebrew_coverage, field_name) for sample in self.samples):
                raise ValueError(f"hocrsyngen batch must include at least one sample with {label} coverage")
        return self


@dataclass(frozen=True)
class HocrsyngenBatch:
    batch_dir: Path
    manifest: HocrsyngenGenerationManifest
    sample_count: int
    page_count: int


def validate_hocrsyngen_batch(batch_dir: Path) -> HocrsyngenBatch:
    root = batch_dir.resolve()
    manifest_path = root / MANIFEST_FILENAME
    if not root.exists():
        raise StageExecutionError(f"hocrsyngen batch path does not exist: {batch_dir}")
    if not root.is_dir():
        raise StageExecutionError(f"hocrsyngen batch path is not a directory: {batch_dir}")
    if not manifest_path.is_file():
        raise StageExecutionError(f"hocrsyngen batch is missing {MANIFEST_FILENAME}: {manifest_path}")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise StageExecutionError(
            f"hocrsyngen manifest has invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise StageExecutionError(f"hocrsyngen manifest could not be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise StageExecutionError("hocrsyngen manifest must serialize to an object")

    try:
        manifest = HocrsyngenGenerationManifest.model_validate(payload)
    except ValidationError as exc:
        raise StageExecutionError(f"hocrsyngen generation_manifest.v1 validation failed: {exc}") from exc

    _validate_manifest_uniqueness(manifest)

    page_count = 0
    for sample_index, sample in enumerate(manifest.samples):
        for page_index, page in enumerate(sample.pages):
            _validate_page(root, page, sample_index, page_index)
            page_count += 1

    return HocrsyngenBatch(
        batch_dir=root,
        manifest=manifest,
        sample_count=len(manifest.samples),
        page_count=page_count,
    )


class HocrsyngenManifestFetcher:
    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        batch = _load_configured_batch(source, bundle)
        selected_samples = _filtered_samples(batch.manifest.samples, options)
        if options.max_items is not None:
            selected_samples = selected_samples[: options.max_items]

        candidates: list[CandidateRecord] = []
        for sample in selected_samples:
            source_item_id = _source_item_id(sample)
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{source_item_id}",
                    source_id=source.id,
                    source_item_id=source_item_id,
                    source_url=f"synthetic://hocrsyngen/{sample.sample_id}",
                    discovery_method="hocrsyngen_generation_manifest_v1",
                    title=_sample_title(sample),
                    raw_metadata={
                        "hocrsyngen_manifest_version": batch.manifest.manifest_version,
                        "hocrsyngen_sample_id": sample.sample_id,
                        "hocrsyngen_sample_index": sample.provenance.sample_index,
                        "synthetic_degradation_preset": sample.provenance.degradation_preset,
                        "synthetic_recipe_id": sample.provenance.recipe_id,
                        "synthetic_template_id": sample.provenance.template_id,
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        batch = _load_configured_batch(source, bundle)
        samples = {sample.sample_id: sample for sample in _filtered_samples(batch.manifest.samples, options)}
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            sample_id = str(candidate.raw_metadata.get("hocrsyngen_sample_id", ""))
            sample = samples.get(sample_id)
            if sample is None:
                raise StageExecutionError(
                    f"hocrsyngen sample {sample_id!r} for candidate {candidate.candidate_id} is not allowed by current synthetic controls"
                )
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=PROJECT_SYNTHETIC_LICENSE,
                    asset_references=[
                        AssetReference(
                            reference=page.asset_path,
                            resolved_path=str(_asset_path(batch.batch_dir, page.asset_path)),
                            media_type=page.media_type,
                        )
                        for page in sample.pages
                    ],
                    metadata=_sample_metadata(batch.manifest, sample),
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
                destination = output_dir / item.item_id / f"page_{asset_index:04d}{source_path.suffix.lower() or '.jpg'}"
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


def _load_configured_batch(source: SourceConfig, bundle: ConfigBundle) -> HocrsyngenBatch:
    reference = source.settings.hocrsyngen_batch_path
    if not reference:
        raise StageExecutionError(f"source {source.id} settings.hocrsyngen_batch_path is required")
    return validate_hocrsyngen_batch(bundle.resolve_path(reference))


def _filtered_samples(
    samples: list[HocrsyngenGeneratedSample],
    options: StageOptions,
) -> list[HocrsyngenGeneratedSample]:
    selected: list[HocrsyngenGeneratedSample] = []
    for sample in samples:
        provenance = sample.provenance
        if options.synthetic_template_filter and provenance.template_id not in options.synthetic_template_filter:
            continue
        if options.synthetic_recipe_filter and provenance.recipe_id not in options.synthetic_recipe_filter:
            continue
        if options.synthetic_degradation_filter and provenance.degradation_preset not in options.synthetic_degradation_filter:
            continue
        selected.append(sample)
    if not selected:
        controls = {
            "degradation_presets": sorted(options.synthetic_degradation_filter or []),
            "recipes": sorted(options.synthetic_recipe_filter or []),
            "templates": sorted(options.synthetic_template_filter or []),
        }
        raise StageExecutionError(f"hocrsyngen synthetic controls selected no manifest samples: {controls}")
    return selected


def _source_item_id(sample: HocrsyngenGeneratedSample) -> str:
    return f"{LEGACY_SOURCE_ITEM_ID_PREFIX}{sample.provenance.sample_index}"


def _sample_title(sample: HocrsyngenGeneratedSample) -> str:
    first_line = sample.text.logical_order.splitlines()[0].strip()
    return first_line or sample.sample_id


def _sample_metadata(
    manifest: HocrsyngenGenerationManifest,
    sample: HocrsyngenGeneratedSample,
) -> dict[str, Any]:
    return {
        "hocrsyngen_controls": sample.controls.model_dump(mode="json"),
        "hocrsyngen_hebrew_coverage": sample.hebrew_coverage.model_dump(mode="json"),
        "hocrsyngen_generator_name": manifest.generator_name,
        "hocrsyngen_identity_mapping": "legacy_sample_index_v1",
        "hocrsyngen_manifest_version": manifest.manifest_version,
        "hocrsyngen_provider_metadata": manifest.provider_metadata.model_dump(mode="json"),
        "hocrsyngen_rendering_metadata": sample.rendering_metadata.model_dump(mode="json"),
        "hocrsyngen_sample_id": sample.sample_id,
        "hocrsyngen_synthetic_disclosure": sample.synthetic_disclosure,
        "hocrsyngen_text_logical_order_sha256": sha256(sample.text.logical_order.encode("utf-8")).hexdigest(),
        "hocrsyngen_text_metadata": _text_metadata(sample.text),
        "synthetic_degradation_preset": sample.provenance.degradation_preset,
        "synthetic_disclosure": sample.synthetic_disclosure,
        "synthetic_font_id": sample.provenance.font_id,
        "synthetic_generator_name": manifest.generator_name,
        "synthetic_generator_version": sample.generator_version,
        "synthetic_hebrew_coverage": sample.hebrew_coverage.model_dump(mode="json"),
        "synthetic_layout_family": sample.rendering_metadata.layout_family,
        "synthetic_license": sample.license,
        "synthetic_provider_name": manifest.provider_metadata.provider_name,
        "synthetic_provider_version": manifest.provider_metadata.provider_version,
        "synthetic_recipe_id": sample.provenance.recipe_id,
        "synthetic_sample_index": sample.provenance.sample_index,
        "synthetic_seed": sample.provenance.seed,
        "synthetic_source_corpus": sample.provenance.source_corpus,
        "synthetic_template_id": sample.provenance.template_id,
    }


def _text_metadata(text: HocrsyngenTextMetadata) -> dict[str, str]:
    return {
        "direction": text.direction,
        "language": text.language,
        "script": text.script,
        "unicode_normalization": text.unicode_normalization,
    }


def _hebrew_coverage(text: str) -> dict[str, bool]:
    return {
        "has_arabic_numerals": any("0" <= char <= "9" for char in text),
        "has_final_letters": any(char in "ךםןףץ" for char in text),
        "has_hebrew_letters": _has_hebrew_letters(text),
        "has_mixed_ltr": any(("A" <= char <= "Z") or ("a" <= char <= "z") for char in text),
        "has_niqqud": any("\u0591" <= char <= "\u05c7" and unicodedata.category(char).startswith("M") for char in text),
        "has_punctuation": any(unicodedata.category(char).startswith("P") for char in text),
    }


def _has_hebrew_letters(text: str) -> bool:
    return any("\u05d0" <= char <= "\u05ea" for char in text)


def _validate_manifest_uniqueness(manifest: HocrsyngenGenerationManifest) -> None:
    sample_ids: set[str] = set()
    sample_indexes: set[int] = set()
    source_item_ids: set[str] = set()
    page_ids: set[str] = set()
    asset_paths: set[str] = set()
    for sample in manifest.samples:
        _require_unique("sample_id", sample.sample_id, sample_ids)
        _require_unique("provenance.sample_index", sample.provenance.sample_index, sample_indexes)
        _require_unique("derived source_item_id", _source_item_id(sample), source_item_ids)
        for page in sample.pages:
            _require_unique("page_id", page.page_id, page_ids)
            _require_unique("asset_path", page.asset_path, asset_paths)


def _require_unique(label: str, value: object, seen: set) -> None:
    if value in seen:
        raise StageExecutionError(f"hocrsyngen manifest contains duplicate {label}: {value}")
    seen.add(value)


def _portable_asset_path(value: str, location: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
        or "://" in value
        or (len(value) >= 2 and value[1] == ":")
    ):
        raise ValueError(f"{location} must be a relative portable path: {value}")
    return path


def _asset_path(batch_dir: Path, asset_reference: str) -> Path:
    asset_path = _portable_asset_path(asset_reference, "page.asset_path")
    return (batch_dir / Path(*asset_path.parts)).resolve()


def _validate_page(batch_dir: Path, page: HocrsyngenPageAsset, sample_index: int, page_index: int) -> None:
    location = f"samples[{sample_index}].pages[{page_index}]"
    path = _asset_path(batch_dir, page.asset_path)
    if not path.is_relative_to(batch_dir):
        raise StageExecutionError(f"hocrsyngen {location}.asset_path must stay under the batch directory: {page.asset_path}")
    if not path.is_file():
        raise StageExecutionError(f"hocrsyngen {location}.asset_path is missing: {page.asset_path}")
    actual_sha256 = sha256_file(path)
    if actual_sha256 != page.sha256:
        raise StageExecutionError(
            f"hocrsyngen {location}.sha256 mismatch for {page.asset_path}: expected {page.sha256}, got {actual_sha256}"
        )
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
            if image.format != "JPEG":
                raise StageExecutionError(
                    f"hocrsyngen {location}.media_type mismatch for {page.asset_path}: expected image/jpeg, got {image.format}"
                )
            if image.size != (page.width, page.height):
                raise StageExecutionError(
                    f"hocrsyngen {location} dimensions mismatch for {page.asset_path}: "
                    f"expected {page.width}x{page.height}, got {image.size[0]}x{image.size[1]}"
                )
    except UnidentifiedImageError as exc:
        raise StageExecutionError(f"hocrsyngen {location}.asset_path is not a readable image: {page.asset_path}") from exc
    except OSError as exc:
        raise StageExecutionError(f"hocrsyngen {location}.asset_path is not a valid image: {page.asset_path}") from exc
