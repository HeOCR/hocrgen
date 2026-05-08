from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from hashlib import sha256
from json import JSONDecodeError
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.hocrsyngen_manifest import (
    HocrsyngenGenerationManifest,
    HocrsyngenHebrewCoverage,
    HocrsyngenRenderingMetadata,
    _hebrew_coverage as _compute_hocrsyngen_hebrew_coverage,
)
from hocrgen.utils.hashing import sha256_file


REPORT_SCHEMA_VERSION = "hocrgen_hocrsyngen_preflight_report.v1"
IMPORT_METADATA_PACKET_SCHEMA_VERSION = "hocrgen_hocrsyngen_import_metadata_packet.v1"
PROVIDER_RUNTIME_CONTRACT_SCHEMA_VERSION = "hocrgen_hocrsyngen_provider_runtime.v1"
PLANNING_NOTATION = "F6f2a"
IMPORT_METADATA_PLANNING_NOTATION = "F6f2"
MANIFEST_FILENAME = "generation_manifest.json"
SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES = {
    "printed_letter": "printed_letter_form",
    "handwritten_note": "handwritten_note_marginalia",
}

REQUIRED_REPORTS = {
    "template_catalog_v2": ("reports/template_catalog_v2.json", "template_catalog.v2"),
    "generation": ("reports/generation_report.json", "generation_report.v1"),
    "generated_validation": ("reports/generated_validation_report.json", "validation_report.v1"),
}

OPTIONAL_REPORTS = {
    "template_catalog_v1": ("reports/template_catalog_v1.json", "template_catalog.v1"),
    "contracts": ("reports/contracts.json", "contract_fixture_catalog.v1"),
    "fixture_export": ("reports/fixture_export_report.json", "contract_fixture_export.v1"),
    "fixture_validation": ("reports/fixture_validation_report.json", "validation_report.v1"),
}

class PublicHocrsyngenModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class PublicTextMetadata(PublicHocrsyngenModel):
    logical_order: str = Field(min_length=1)
    script: Literal["Hebr"]
    language: Literal["he"]
    direction: Literal["rtl"]
    unicode_normalization: Literal["NFC"]

    @model_validator(mode="after")
    def validate_logical_order(self) -> "PublicTextMetadata":
        if self.logical_order != unicodedata.normalize("NFC", self.logical_order):
            raise ValueError("logical_order must be NFC-normalized")
        if "\ufffd" in self.logical_order:
            raise ValueError("logical_order must not contain replacement characters")
        if not any("\u05d0" <= char <= "\u05ea" for char in self.logical_order):
            raise ValueError("logical_order must contain Hebrew letters")
        return self


class PublicPageAsset(PublicHocrsyngenModel):
    page_id: str = Field(min_length=1)
    asset_path: str = Field(min_length=1)
    media_type: Literal["image/jpeg"]
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    width: int = Field(ge=1)
    height: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_asset_path(self) -> "PublicPageAsset":
        _portable_relative_path(self.asset_path, "page.asset_path")
        return self


class PublicSampleProvenance(PublicHocrsyngenModel):
    seed: int
    sample_index: int = Field(ge=0)
    template_id: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    degradation_preset: str = Field(min_length=1)
    font_id: str = Field(min_length=1)
    source_corpus: str = Field(min_length=1)


class PublicSampleControls(PublicHocrsyngenModel):
    persona: str | None
    condition: str | None


class PublicGeneratedSample(PublicHocrsyngenModel):
    sample_id: str = Field(pattern=r"^hocrsyngen-s[0-9]{8}-[0-9]{6}$")
    pages: list[PublicPageAsset] = Field(min_length=1)
    text: PublicTextMetadata
    generator_version: str = Field(min_length=1)
    recipe_id: str = Field(min_length=1)
    provenance: PublicSampleProvenance
    license: Literal["PROJECT-SYNTHETIC"]
    synthetic_disclosure: str = Field(min_length=1)
    controls: PublicSampleControls

    @model_validator(mode="after")
    def validate_recipe_consistency(self) -> "PublicGeneratedSample":
        if self.recipe_id != self.provenance.recipe_id:
            raise ValueError("recipe_id must match provenance.recipe_id")
        return self


class PublicGenerationManifest(PublicHocrsyngenModel):
    manifest_version: Literal["1.0"]
    generator_name: Literal["hocrsyngen"]
    license: Literal["PROJECT-SYNTHETIC"]
    synthetic_disclosure: str | None = None
    samples: list[PublicGeneratedSample] = Field(min_length=1)


class ImportMetadataModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ImportMetadataSourceManifest(ImportMetadataModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    boundary_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    manifest_version: Literal["1.0"]
    generator_name: Literal["hocrsyngen"]
    does_not_extend_hocrsyngen_manifest_v1: Literal[True]

    @model_validator(mode="after")
    def validate_boundary_id(self) -> "ImportMetadataSourceManifest":
        if self.boundary_id != f"sha256:{self.sha256}":
            raise ValueError("boundary_id must match source manifest sha256")
        _portable_relative_path(self.path, "source_manifest.path")
        return self


class ImportMetadataBatchMetadata(ImportMetadataModel):
    synthetic_disclosure: str = Field(min_length=1)


class ImportProviderRuntimeContract(ImportMetadataModel):
    evidence_status: Literal["validated_from_candidate_evidence_report", "not_provided_by_candidate_evidence_report"]
    source: str | None
    used_network: bool | None
    used_rest_service: bool | None
    used_gpu: bool | None
    used_llm: bool | None
    used_diffusion: bool | None

    @model_validator(mode="after")
    def validate_runtime_evidence(self) -> "ImportProviderRuntimeContract":
        flags = (self.used_network, self.used_rest_service, self.used_gpu, self.used_llm, self.used_diffusion)
        if self.evidence_status == "validated_from_candidate_evidence_report":
            if self.source != "candidate_evidence_run_report.provider_runtime":
                raise ValueError("validated provider runtime contract must cite candidate_evidence_run_report.provider_runtime")
            if flags != (False, False, False, False, False):
                raise ValueError("validated provider runtime contract must declare all runtime flags false")
        else:
            if self.source is not None:
                raise ValueError("missing provider runtime contract must not cite a source")
            if any(flag is not None for flag in flags):
                raise ValueError("missing provider runtime contract must leave runtime flags null")
        return self


class ImportProviderMetadata(ImportMetadataModel):
    provider_name: Literal["hocrsyngen"]
    provider_version: str = Field(pattern=r".*\S.*")
    generation_mode: Literal["offline_manifest_batch"]
    runtime_contract: ImportProviderRuntimeContract


class ImportSampleMetadataSources(ImportMetadataModel):
    text_metadata: Literal["generation_manifest.v1.samples[].text"]
    line_count: Literal["generation_manifest.v1.samples[].text.logical_order.splitlines()"]
    layout_family: Literal["template_catalog.v2 joined by provenance.template_id and provenance.recipe_id"]
    hebrew_coverage: Literal["computed from NFC logical_order text"]
    rendering_coverage_report: str | None


class ImportSampleMetadata(ImportMetadataModel):
    sample_id: str = Field(pattern=r"^hocrsyngen-s[0-9]{8}-[0-9]{6}$")
    rendering_metadata: HocrsyngenRenderingMetadata
    hebrew_coverage: HocrsyngenHebrewCoverage
    metadata_sources: ImportSampleMetadataSources


class ImportMetadataValidation(ImportMetadataModel):
    sample_count: int = Field(ge=1)
    page_count: int = Field(ge=1)
    provider_version_source: Literal["candidate_evidence_run_report.generator_version matched samples[].generator_version"]
    generator_versions: list[str] = Field(min_length=1)
    covers_missing_manifest_metadata: list[str]
    metadata_valid: Literal[True]
    validated_against_hocrgen_release_import_model: bool
    release_import_model_validation_errors: list[str]
    layout_family_policy: "ImportLayoutFamilyPolicy"


class ImportLayoutFamilyPolicy(ImportMetadataModel):
    supported_base_families: list[str]
    supported_layout_families: list[str]
    unsupported_family_behavior: Literal["fail_closed_before_sidecar"]

    @model_validator(mode="after")
    def validate_layout_policy(self) -> "ImportLayoutFamilyPolicy":
        if self.supported_base_families != sorted(SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES):
            raise ValueError("supported_base_families must match hocrgen policy")
        if self.supported_layout_families != sorted(SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES.values()):
            raise ValueError("supported_layout_families must match hocrgen policy")
        return self


class HocrsyngenImportMetadataPacket(ImportMetadataModel):
    schema_version: Literal["hocrgen_hocrsyngen_import_metadata_packet.v1"]
    planning_notation: Literal["F6f2"]
    artifact_scope: Literal["operator_only"]
    release_eligible: Literal[False]
    release_eligibility_reason: str = Field(min_length=1)
    source_manifest: ImportMetadataSourceManifest
    batch_metadata: ImportMetadataBatchMetadata
    provider_metadata: ImportProviderMetadata
    samples: list[ImportSampleMetadata] = Field(min_length=1)
    validation: ImportMetadataValidation
    non_goals: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_packet_consistency(self) -> "HocrsyngenImportMetadataPacket":
        sample_ids = [sample.sample_id for sample in self.samples]
        if len(set(sample_ids)) != len(sample_ids):
            raise ValueError("samples must contain unique sample_id values")
        if self.validation.sample_count != len(self.samples):
            raise ValueError("validation.sample_count must match samples length")
        if self.validation.generator_versions != sorted(set(self.validation.generator_versions)):
            raise ValueError("validation.generator_versions must be sorted and unique")
        return self


@dataclass(frozen=True)
class HocrsyngenPreflightResult:
    report_path: Path
    report: dict[str, Any]


def run_hocrsyngen_preflight(
    evidence_root: Path,
    *,
    report_path: Path | None = None,
    metadata_sidecar_path: Path | None = None,
    overwrite: bool = False,
) -> HocrsyngenPreflightResult:
    root = evidence_root.resolve()
    if not root.exists():
        raise StageExecutionError(f"hocrsyngen evidence root does not exist: {evidence_root}")
    if not root.is_dir():
        raise StageExecutionError(f"hocrsyngen evidence root is not a directory: {evidence_root}")
    if evidence_root.is_symlink():
        raise StageExecutionError(f"hocrsyngen evidence root must not be a symlink: {evidence_root}")

    destination = (report_path or (root / "hocrgen_preflight_report.json")).resolve()
    if destination.exists() and not overwrite:
        raise StageExecutionError(f"hocrsyngen preflight report already exists: {destination}")
    metadata_destination = metadata_sidecar_path.resolve() if metadata_sidecar_path is not None else None
    if metadata_destination is not None and metadata_destination == destination:
        raise StageExecutionError("hocrsyngen import metadata sidecar path must differ from the preflight report path")
    if metadata_destination is not None and metadata_destination.exists() and not overwrite:
        raise StageExecutionError(f"hocrsyngen import metadata sidecar already exists: {metadata_destination}")

    evidence_report_path = root / "candidate_evidence_run_report.json"
    evidence_report = _read_json_object(root, evidence_report_path, "candidate evidence run report")
    _require_schema(evidence_report, "candidate_evidence_run_report.v1", "candidate evidence run report")
    if evidence_report.get("release_eligible") is not False:
        raise StageExecutionError("candidate evidence run report must declare release_eligible=false")

    _validate_reported_paths(root, evidence_report)

    reports = _load_reports(root, evidence_report)
    generation_report = reports["generation"]["payload"]
    validation_report = reports["generated_validation"]["payload"]
    if validation_report.get("valid") is not True:
        raise StageExecutionError("generated validation_report.v1 must declare valid=true")

    generated_batch = _resolve_evidence_path(root, evidence_report.get("generated_batch_path"), "generated_batch_path")
    if generated_batch != root / "generated_batch":
        raise StageExecutionError("candidate evidence generated_batch_path must resolve to generated_batch under the evidence root")
    manifest_path = _resolve_evidence_path(
        root,
        evidence_report.get("generated_manifest_path"),
        "generated_manifest_path",
    )
    if manifest_path != generated_batch / MANIFEST_FILENAME:
        raise StageExecutionError("candidate evidence generated_manifest_path must resolve to generated_batch/generation_manifest.json")
    rendering_coverage_path = _validate_generated_report_paths(
        root,
        generated_batch,
        manifest_path,
        evidence_report,
        generation_report,
        validation_report,
    )

    manifest_payload = _read_json_object(root, manifest_path, "generated generation_manifest.v1")
    try:
        manifest = PublicGenerationManifest.model_validate(manifest_payload)
    except ValidationError as exc:
        raise StageExecutionError(f"public hocrsyngen generation_manifest.v1 validation failed: {exc}") from exc

    _validate_manifest_uniqueness(manifest)
    manifest_page_count = sum(len(sample.pages) for sample in manifest.samples)
    _validate_count(generation_report, "generation_report.v1", "sample_count", len(manifest.samples))
    _validate_count(generation_report, "generation_report.v1", "page_count", manifest_page_count)
    _validate_count(validation_report, "validation_report.v1", "sample_count", len(manifest.samples))
    _validate_count(validation_report, "validation_report.v1", "page_count", manifest_page_count)
    _validate_evidence_run_identity(evidence_report, manifest)

    checksum_inventory = _verify_checksum_inventory(root)
    catalog_result = _validate_template_catalog_join(manifest, reports["template_catalog_v2"]["payload"])
    asset_checks = _validate_assets(generated_batch, manifest)
    missing_metadata = _missing_release_metadata(manifest_payload)
    rendering_coverage = _rendering_coverage_reference(root, rendering_coverage_path)
    import_metadata_packet = _build_import_metadata_packet(
        root,
        evidence_report,
        manifest,
        manifest_payload,
        manifest_path,
        catalog_result,
        rendering_coverage,
        missing_metadata,
    )
    _validate_import_metadata_packet(root, manifest_path, manifest, import_metadata_packet)

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "planning_notation": PLANNING_NOTATION,
        "status": "ok",
        "artifact_scope": "operator_only",
        "release_eligible": False,
        "release_eligibility_reason": (
            "diagnostic preflight only; hocrgen review, dedupe, split, benchmark, caps, export, "
            "publication, and release/import metadata gates have not admitted this batch"
        ),
        "evidence_root": str(root),
        "candidate_evidence_run": {
            "path": _relative_to_root(root, evidence_report_path),
            "sha256": _sha256_evidence_file(root, evidence_report_path, "candidate evidence run report"),
            "count": evidence_report.get("count"),
            "seed": evidence_report.get("seed"),
            "generator_version": evidence_report.get("generator_version"),
            "started_at_utc": evidence_report.get("started_at_utc"),
            "completed_at_utc": evidence_report.get("completed_at_utc"),
            "release_eligible": evidence_report.get("release_eligible"),
        },
        "source_batch": {
            "path": _relative_to_root(root, generated_batch),
            "boundary_id": f"sha256:{_sha256_evidence_file(root, manifest_path, 'generated generation_manifest.v1')}",
            "manifest_path": _relative_to_root(root, manifest_path),
            "manifest_sha256": _sha256_evidence_file(root, manifest_path, "generated generation_manifest.v1"),
        },
        "manifest": {
            "manifest_version": manifest.manifest_version,
            "generator_name": manifest.generator_name,
            "license": manifest.license,
            "sample_count": len(manifest.samples),
            "page_count": manifest_page_count,
            "generator_versions": sorted({sample.generator_version for sample in manifest.samples}),
            "missing_hocrgen_release_import_metadata": missing_metadata,
        },
        "reports": {key: value["summary"] for key, value in reports.items()},
        "checksum_inventory": checksum_inventory,
        "asset_policy": {
            "relative_posix_only": True,
            "rejects_absolute_paths": True,
            "rejects_backslashes": True,
            "rejects_url_like_paths": True,
            "rejects_dot_or_dotdot_parts": True,
            "requires_path_under_generated_batch": True,
            "recomputes_sha256": True,
            "verifies_jpeg_and_dimensions": True,
        },
        "assets": {
            "page_count": manifest_page_count,
            "checks": asset_checks,
        },
        "template_catalog": catalog_result,
        "rendering_coverage_report": rendering_coverage,
        "hocrgen_import_metadata_packet": import_metadata_packet,
        "hocrgen_import_metadata_sidecar": {
            "requested": metadata_destination is not None,
            "written": metadata_destination is not None,
            "path": str(metadata_destination) if metadata_destination is not None else None,
            "schema_version": IMPORT_METADATA_PACKET_SCHEMA_VERSION,
            "release_eligible": False,
        },
        "samples": [_sample_summary(sample) for sample in manifest.samples],
        "limitations": [
            "raw hocrsyngen output is candidate synthetic input only",
            "hocrgen release-path provider_metadata is absent from public generation_manifest.v1",
            "hocrgen release-path rendering_metadata is absent from public generation_manifest.v1 samples",
            "hocrgen release-path hebrew_coverage is absent from public generation_manifest.v1 samples",
            "downstream realism acceptance evidence has not been reviewed by hocrgen",
            "downstream utility measurement evidence has not been reviewed by hocrgen",
            "synthetic diversity/domain-shift evidence has not been reviewed by hocrgen",
            "release caps, review evidence sidecars, and candidate profile/mix records have not admitted this batch",
        ],
        "non_goals": [
            "does not import hocrsyngen private Python internals",
            "does not call hocrsyngen runtime commands from the hocrgen release path",
            "does not change project_synthetic, build-release, export-alpha, export-synthetic, or export-public-beta",
            "does not treat hocrsyngen generation or validation success as release eligibility",
        ],
    }

    _write_preflight_artifacts(destination, report, metadata_destination, import_metadata_packet)

    return HocrsyngenPreflightResult(report_path=destination, report=report)


def _read_json_object(root: Path, path: Path, label: str) -> dict[str, Any]:
    path = _require_evidence_file(root, path, label)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise StageExecutionError(f"{label} has invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise StageExecutionError(f"{label} could not be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise StageExecutionError(f"{label} must serialize to an object: {path}")
    return payload


def _sha256_evidence_file(root: Path, path: Path, label: str) -> str:
    return sha256_file(_require_evidence_file(root, path, label))


def _write_json_temp(path: Path, payload: dict[str, Any], label: str) -> Path:
    if path.exists() and path.is_dir():
        raise StageExecutionError(f"could not write {label} to {path}: path is a directory")
    temp_path = path.with_name(f".{path.name}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise StageExecutionError(f"could not write {label} to {path}: {exc}") from exc
    return temp_path


def _write_preflight_artifacts(
    report_path: Path,
    report: dict[str, Any],
    metadata_sidecar_path: Path | None,
    metadata_packet: dict[str, Any],
) -> None:
    report_temp: Path | None = None
    sidecar_temp: Path | None = None
    try:
        report_temp = _write_json_temp(report_path, report, "hocrsyngen preflight report")
        if metadata_sidecar_path is not None:
            sidecar_temp = _write_json_temp(
                metadata_sidecar_path,
                metadata_packet,
                "hocrsyngen import metadata sidecar",
            )
            sidecar_temp.replace(metadata_sidecar_path)
            sidecar_temp = None
        report_temp.replace(report_path)
        report_temp = None
    except OSError as exc:
        raise StageExecutionError(f"could not publish hocrsyngen preflight artifacts: {exc}") from exc
    finally:
        for temp_path in (report_temp, sidecar_temp):
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()


def _require_evidence_file(root: Path, path: Path, label: str) -> Path:
    original_path = path if path.is_absolute() else root / path
    _reject_symlink_components(root, original_path, label)
    resolved = original_path.resolve()
    if not resolved.is_relative_to(root):
        raise StageExecutionError(f"{label} must stay under evidence root: {path}")
    if not resolved.is_file():
        raise StageExecutionError(f"{label} is missing: {path}")
    return resolved


def _reject_symlink_components(root: Path, path: Path, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise StageExecutionError(f"{label} must not be a symlink: {current}")


def _require_schema(payload: dict[str, Any], expected: str, label: str) -> None:
    if payload.get("schema_version") != expected:
        raise StageExecutionError(f"{label} must declare schema_version={expected}")


def _validate_reported_paths(root: Path, evidence_report: dict[str, Any]) -> None:
    expected_paths = {
        "output_root": root,
        "reports_dir": root / "reports",
        "fixture_batch_path": root / "fixture_batch",
        "generated_batch_path": root / "generated_batch",
        "generated_manifest_path": root / "generated_batch" / MANIFEST_FILENAME,
        "checksums_path": root / "SHA256SUMS",
        "rendering_coverage_report_path": root / "generated_batch" / "rendering_coverage_report.json",
    }
    for key, expected in expected_paths.items():
        value = evidence_report.get(key)
        if value is None and key == "rendering_coverage_report_path":
            continue
        path = _resolve_evidence_path(root, value, key)
        if path != expected:
            raise StageExecutionError(f"candidate evidence {key} must resolve to {expected}, got {path}")


def _resolve_evidence_path(root: Path, value: object, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise StageExecutionError(f"candidate evidence {label} must be a non-empty path string")
    raw = Path(value)
    original_path = raw if raw.is_absolute() else root / raw
    _reject_symlink_components(root, original_path, label)
    path = original_path.resolve()
    if not path.is_relative_to(root):
        raise StageExecutionError(f"candidate evidence {label} must stay under evidence root: {value}")
    return path


def _load_reports(root: Path, evidence_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for key, (relative_path, schema_version) in {**REQUIRED_REPORTS, **OPTIONAL_REPORTS}.items():
        path = root / Path(relative_path)
        if key in REQUIRED_REPORTS or path.exists():
            payload = _read_json_object(root, path, key)
            _require_schema(payload, schema_version, key)
            embedded_reports = evidence_report.get("reports")
            if isinstance(embedded_reports, dict) and key in embedded_reports and embedded_reports[key] != payload:
                raise StageExecutionError(f"candidate evidence embedded report {key} does not match {relative_path}")
            summary: dict[str, Any] = {
                "path": relative_path,
                "sha256": _sha256_evidence_file(root, path, key),
                "schema_version": payload.get("schema_version"),
            }
            for optional_key in ("sample_count", "page_count", "valid", "fixture_id", "contract"):
                if optional_key in payload:
                    summary[optional_key] = payload[optional_key]
            if key == "template_catalog_v2":
                templates = payload.get("templates")
                summary["template_count"] = len(templates) if isinstance(templates, list) else None
            loaded[key] = {"payload": payload, "summary": summary}
    return loaded


def _validate_count(payload: dict[str, Any], label: str, field: str, expected: int) -> None:
    if payload.get(field) != expected:
        raise StageExecutionError(f"{label} {field} must be {expected}, got {payload.get(field)!r}")


def _validate_generated_report_paths(
    root: Path,
    generated_batch: Path,
    manifest_path: Path,
    evidence_report: dict[str, Any],
    generation_report: dict[str, Any],
    validation_report: dict[str, Any],
) -> Path | None:
    _validate_report_path(root, generation_report, "generation_report.v1", "output_path", generated_batch)
    _validate_report_path(root, generation_report, "generation_report.v1", "manifest_path", manifest_path)
    _validate_report_path(root, validation_report, "validation_report.v1", "path", generated_batch)

    evidence_value = evidence_report.get("rendering_coverage_report_path")
    generation_value = generation_report.get("rendering_coverage_report_path")
    if evidence_value is None and generation_value is None:
        return None
    if evidence_value is None or generation_value is None:
        raise StageExecutionError(
            "candidate evidence and generation_report.v1 must agree on rendering_coverage_report_path presence"
        )
    evidence_path = _resolve_evidence_path(root, evidence_value, "rendering_coverage_report_path")
    generation_path = _resolve_evidence_path(root, generation_value, "generation_report.v1.rendering_coverage_report_path")
    if evidence_path != generation_path:
        raise StageExecutionError(
            "generation_report.v1 rendering_coverage_report_path must match candidate evidence rendering_coverage_report_path"
        )
    expected = generated_batch / "rendering_coverage_report.json"
    if generation_path != expected:
        raise StageExecutionError(
            "generation_report.v1 rendering_coverage_report_path must resolve to generated_batch/rendering_coverage_report.json"
        )
    return generation_path


def _validate_report_path(
    root: Path,
    payload: dict[str, Any],
    label: str,
    field: str,
    expected: Path,
) -> None:
    path = _resolve_evidence_path(root, payload.get(field), f"{label}.{field}")
    if path != expected:
        raise StageExecutionError(f"{label} {field} must resolve to {expected}, got {path}")


def _validate_evidence_run_identity(
    evidence_report: dict[str, Any],
    manifest: PublicGenerationManifest,
) -> None:
    sample_count = len(manifest.samples)
    if evidence_report.get("count") != sample_count:
        raise StageExecutionError(
            f"candidate evidence count must match manifest sample count: expected {sample_count}, got {evidence_report.get('count')!r}"
        )
    seed = evidence_report.get("seed")
    if not isinstance(seed, int):
        raise StageExecutionError(f"candidate evidence seed must be an integer, got {seed!r}")
    manifest_seeds = sorted({sample.provenance.seed for sample in manifest.samples})
    if manifest_seeds != [seed]:
        raise StageExecutionError(
            f"candidate evidence seed must match every manifest sample provenance.seed: expected {seed}, got {manifest_seeds}"
        )


def _verify_checksum_inventory(root: Path) -> dict[str, Any]:
    path = _require_evidence_file(root, root / "SHA256SUMS", "SHA256SUMS")
    if not path.is_file():
        raise StageExecutionError(f"hocrsyngen evidence root is missing SHA256SUMS: {path}")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise StageExecutionError(f"SHA256SUMS could not be read: {exc}") from exc
    entries: list[dict[str, str]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            digest, relative_path = line.split("  ", 1)
        except ValueError as exc:
            raise StageExecutionError(f"SHA256SUMS line {line_number} must use '<sha256>  <relative-path>'") from exc
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise StageExecutionError(f"SHA256SUMS line {line_number} has invalid sha256 digest")
        rel = _portable_relative_path(relative_path, f"SHA256SUMS line {line_number}")
        file_path = _resolve_evidence_path(root, str(Path(*rel.parts)), f"SHA256SUMS line {line_number}")
        file_path = _require_evidence_file(root, file_path, f"SHA256SUMS line {line_number}")
        actual = sha256_file(file_path)
        if actual != digest:
            raise StageExecutionError(f"SHA256SUMS mismatch for {relative_path}: expected {digest}, got {actual}")
        entries.append({"path": relative_path, "sha256": digest})
    if not entries:
        raise StageExecutionError("SHA256SUMS must contain at least one file entry")
    return {
        "path": "SHA256SUMS",
        "sha256": _sha256_evidence_file(root, path, "SHA256SUMS"),
        "entry_count": len(entries),
        "verified_count": len(entries),
    }


def _validate_template_catalog_join(
    manifest: PublicGenerationManifest,
    template_catalog: dict[str, Any],
) -> dict[str, Any]:
    templates = template_catalog.get("templates")
    if not isinstance(templates, list) or not templates:
        raise StageExecutionError("template_catalog.v2 must include a non-empty templates list")
    catalog_pairs: dict[tuple[str, str], dict[str, Any]] = {}
    for index, template in enumerate(templates):
        if not isinstance(template, dict):
            raise StageExecutionError(f"template_catalog.v2 templates[{index}] must be an object")
        template_id = template.get("template_id")
        recipe_id = template.get("recipe_id")
        if not isinstance(template_id, str) or not template_id:
            raise StageExecutionError(f"template_catalog.v2 templates[{index}].template_id must be a non-empty string")
        if not isinstance(recipe_id, str) or not recipe_id:
            raise StageExecutionError(f"template_catalog.v2 templates[{index}].recipe_id must be a non-empty string")
        pair = (template_id, recipe_id)
        if pair in catalog_pairs:
            raise StageExecutionError(f"template_catalog.v2 contains duplicate template/recipe pair: {pair}")
        catalog_pairs[pair] = template

    joined: list[dict[str, Any]] = []
    for sample in manifest.samples:
        pair = (sample.provenance.template_id, sample.provenance.recipe_id)
        template = catalog_pairs.get(pair)
        if template is None:
            raise StageExecutionError(
                f"manifest sample {sample.sample_id} template/recipe pair does not join to template_catalog.v2: {pair}"
            )
        joined.append(
            {
                "sample_id": sample.sample_id,
                "template_id": pair[0],
                "recipe_id": pair[1],
                "document_family": template.get("document_family"),
                "base_family": template.get("base_family"),
                "layout_density": template.get("layout_density"),
            }
        )
    return {
        "schema_version": template_catalog.get("schema_version"),
        "template_count": len(catalog_pairs),
        "joined_sample_count": len(joined),
        "missing_join_count": 0,
        "joins": joined,
    }


def _validate_assets(batch_root: Path, manifest: PublicGenerationManifest) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for sample in manifest.samples:
        for page in sample.pages:
            rel = _portable_relative_path(page.asset_path, f"{sample.sample_id}.{page.page_id}.asset_path")
            path = _resolve_evidence_path(batch_root, str(Path(*rel.parts)), f"{sample.sample_id}.{page.page_id}.asset_path")
            path = _require_evidence_file(batch_root, path, f"{sample.sample_id}.{page.page_id}.asset_path")
            actual_sha256 = sha256_file(path)
            if actual_sha256 != page.sha256:
                raise StageExecutionError(
                    f"page asset sha256 mismatch for {page.asset_path}: expected {page.sha256}, got {actual_sha256}"
                )
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                    if image.format != "JPEG":
                        raise StageExecutionError(
                            f"page asset media_type mismatch for {page.asset_path}: expected image/jpeg, got {image.format}"
                        )
                    if image.size != (page.width, page.height):
                        raise StageExecutionError(
                            f"page asset dimensions mismatch for {page.asset_path}: "
                            f"expected {page.width}x{page.height}, got {image.size[0]}x{image.size[1]}"
                        )
            except UnidentifiedImageError as exc:
                raise StageExecutionError(f"page asset is not a readable image: {page.asset_path}") from exc
            except OSError as exc:
                raise StageExecutionError(f"page asset is not a valid image: {page.asset_path}") from exc
            checks.append(
                {
                    "sample_id": sample.sample_id,
                    "page_id": page.page_id,
                    "asset_path": page.asset_path,
                    "sha256": actual_sha256,
                    "width": page.width,
                    "height": page.height,
                    "media_type": page.media_type,
                    "status": "ok",
                }
            )
    return checks


def _missing_release_metadata(manifest_payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if "provider_metadata" not in manifest_payload:
        missing.append("provider_metadata")
    samples = manifest_payload.get("samples")
    if isinstance(samples, list):
        if any(isinstance(sample, dict) and "rendering_metadata" not in sample for sample in samples):
            missing.append("samples[].rendering_metadata")
        if any(isinstance(sample, dict) and "hebrew_coverage" not in sample for sample in samples):
            missing.append("samples[].hebrew_coverage")
    else:
        missing.extend(["samples[].rendering_metadata", "samples[].hebrew_coverage"])
    return missing


def _rendering_coverage_reference(root: Path, path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"present": False, "advisory": True}
    if not path.is_file():
        raise StageExecutionError(f"rendering coverage report is missing: {path}")
    payload = _read_json_object(root, path, "rendering coverage report")
    return {
        "present": True,
        "advisory": True,
        "path": _relative_to_root(root, path),
        "sha256": _sha256_evidence_file(root, path, "rendering coverage report"),
        "coverage_keys": sorted(payload.get("coverage", {}).keys()) if isinstance(payload.get("coverage"), dict) else [],
    }


def _build_import_metadata_packet(
    root: Path,
    evidence_report: dict[str, Any],
    manifest: PublicGenerationManifest,
    manifest_payload: dict[str, Any],
    manifest_path: Path,
    catalog_result: dict[str, Any],
    rendering_coverage: dict[str, Any],
    missing_metadata: list[str],
) -> dict[str, Any]:
    provider_metadata = _derive_provider_metadata(evidence_report, manifest)
    catalog_by_sample = {
        str(join["sample_id"]): join
        for join in catalog_result.get("joins", [])
        if isinstance(join, dict) and isinstance(join.get("sample_id"), str)
    }
    samples = []
    for sample in manifest.samples:
        catalog_join = catalog_by_sample.get(sample.sample_id)
        if catalog_join is None:
            raise StageExecutionError(f"missing template catalog join for import metadata sample: {sample.sample_id}")
        rendering_metadata = _derive_rendering_metadata(sample, catalog_join)
        hebrew_coverage = _derive_hebrew_coverage(sample)
        samples.append(
            {
                "sample_id": sample.sample_id,
                "rendering_metadata": rendering_metadata,
                "hebrew_coverage": hebrew_coverage,
                "metadata_sources": {
                    "text_metadata": "generation_manifest.v1.samples[].text",
                    "line_count": "generation_manifest.v1.samples[].text.logical_order.splitlines()",
                    "layout_family": "template_catalog.v2 joined by provenance.template_id and provenance.recipe_id",
                    "hebrew_coverage": "computed from NFC logical_order text",
                    "rendering_coverage_report": rendering_coverage.get("path") if rendering_coverage.get("present") else None,
                },
            }
        )

    sample_page_count = sum(len(sample.pages) for sample in manifest.samples)
    manifest_sha256 = _sha256_evidence_file(root, manifest_path, "generated generation_manifest.v1")
    synthetic_disclosure = _derive_batch_synthetic_disclosure(manifest_payload, manifest)
    release_import_validation_errors = _release_import_model_validation_errors(
        manifest,
        provider_metadata,
        samples,
        synthetic_disclosure,
    )
    packet = {
        "schema_version": IMPORT_METADATA_PACKET_SCHEMA_VERSION,
        "planning_notation": IMPORT_METADATA_PLANNING_NOTATION,
        "artifact_scope": "operator_only",
        "release_eligible": False,
        "release_eligibility_reason": (
            "hocrgen-owned import metadata packet only; it does not admit the batch past review, dedupe, "
            "split, benchmark, cap, export, publication, or public-beta gates"
        ),
        "source_manifest": {
            "path": _relative_to_root(root, manifest_path),
            "sha256": manifest_sha256,
            "boundary_id": f"sha256:{manifest_sha256}",
            "manifest_version": manifest.manifest_version,
            "generator_name": manifest.generator_name,
            "does_not_extend_hocrsyngen_manifest_v1": True,
        },
        "batch_metadata": {
            "synthetic_disclosure": synthetic_disclosure,
        },
        "provider_metadata": provider_metadata,
        "samples": samples,
        "validation": {
            "sample_count": len(samples),
            "page_count": sample_page_count,
            "provider_version_source": "candidate_evidence_run_report.generator_version matched samples[].generator_version",
            "generator_versions": sorted({sample.generator_version for sample in manifest.samples}),
            "covers_missing_manifest_metadata": missing_metadata,
            "metadata_valid": True,
            "validated_against_hocrgen_release_import_model": not release_import_validation_errors,
            "release_import_model_validation_errors": release_import_validation_errors,
            "layout_family_policy": {
                "supported_base_families": sorted(SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES),
                "supported_layout_families": sorted(SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES.values()),
                "unsupported_family_behavior": "fail_closed_before_sidecar",
            },
        },
        "non_goals": [
            "does not mutate hocrsyngen generation_manifest.v1",
            "does not import hocrsyngen private Python internals",
            "does not call hocrsyngen runtime commands",
            "does not wire this batch into build-release, export-alpha, export-synthetic, or export-public-beta",
            "does not relax review, dedupe, split, benchmark, cap, export, publication, or public-beta gates",
        ],
    }
    return HocrsyngenImportMetadataPacket.model_validate(packet).model_dump(mode="json")


def _derive_provider_metadata(
    evidence_report: dict[str, Any],
    manifest: PublicGenerationManifest,
) -> dict[str, Any]:
    evidence_version = evidence_report.get("generator_version")
    if not isinstance(evidence_version, str) or not evidence_version.strip():
        raise StageExecutionError("candidate evidence generator_version is required to derive provider metadata")
    manifest_versions = sorted({sample.generator_version for sample in manifest.samples})
    if manifest_versions != [evidence_version]:
        raise StageExecutionError(
            "candidate evidence generator_version must match all manifest samples before deriving provider metadata: "
            f"expected {evidence_version!r}, got {manifest_versions}"
        )
    return ImportProviderMetadata(
        provider_name="hocrsyngen",
        provider_version=evidence_version,
        generation_mode="offline_manifest_batch",
        runtime_contract=_derive_provider_runtime_contract(evidence_report),
    ).model_dump(mode="json")


def _derive_provider_runtime_contract(evidence_report: dict[str, Any]) -> dict[str, Any]:
    runtime = evidence_report.get("provider_runtime")
    if runtime is None:
        return ImportProviderRuntimeContract(
            evidence_status="not_provided_by_candidate_evidence_report",
            source=None,
            used_network=None,
            used_rest_service=None,
            used_gpu=None,
            used_llm=None,
            used_diffusion=None,
        ).model_dump(mode="json")
    if not isinstance(runtime, dict):
        raise StageExecutionError("candidate evidence provider_runtime must be an object when present")
    if runtime.get("schema_version") != PROVIDER_RUNTIME_CONTRACT_SCHEMA_VERSION:
        raise StageExecutionError(
            f"candidate evidence provider_runtime must declare schema_version={PROVIDER_RUNTIME_CONTRACT_SCHEMA_VERSION}"
        )
    flags = {
        flag: runtime.get(flag)
        for flag in ("used_network", "used_rest_service", "used_gpu", "used_llm", "used_diffusion")
    }
    if any(value is not False for value in flags.values()):
        raise StageExecutionError("candidate evidence provider_runtime must explicitly declare all runtime flags false")
    return ImportProviderRuntimeContract(
        evidence_status="validated_from_candidate_evidence_report",
        source="candidate_evidence_run_report.provider_runtime",
        **flags,
    ).model_dump(mode="json")


def _derive_rendering_metadata(
    sample: PublicGeneratedSample,
    catalog_join: dict[str, Any],
) -> dict[str, Any]:
    return HocrsyngenRenderingMetadata(
        text_order="logical",
        page_direction=sample.text.direction,
        line_direction=sample.text.direction,
        bidi_handling="logical_rtl_paragraphs",
        font_shaping="provider_shaped_hebrew_text",
        layout_family=_derive_layout_family(sample, catalog_join),
        line_count=len(sample.text.logical_order.splitlines()),
    ).model_dump(mode="json")


def _derive_layout_family(sample: PublicGeneratedSample, catalog_join: dict[str, Any]) -> str:
    recipe_id = sample.provenance.recipe_id
    template_id = sample.provenance.template_id
    base_family = catalog_join.get("base_family")
    if isinstance(base_family, str) and base_family in SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES:
        return SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES[base_family]
    for supported_base_family, layout_family in SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES.items():
        if recipe_id.startswith(layout_family):
            return layout_family
    raise StageExecutionError(
        "unsupported hocrgen release-import layout family for "
        f"sample {sample.sample_id}: template={template_id!r}, recipe={recipe_id!r}, base_family={base_family!r}; "
        f"supported base families are {sorted(SUPPORTED_RELEASE_IMPORT_LAYOUT_FAMILIES)}"
    )


def _derive_hebrew_coverage(sample: PublicGeneratedSample) -> dict[str, bool]:
    return HocrsyngenHebrewCoverage(**_compute_hocrsyngen_hebrew_coverage(sample.text.logical_order)).model_dump(
        mode="json"
    )


def _derive_batch_synthetic_disclosure(
    manifest_payload: dict[str, Any],
    manifest: PublicGenerationManifest,
) -> str:
    value = manifest_payload.get("synthetic_disclosure")
    if isinstance(value, str) and value.strip():
        return value
    sample_values = {sample.synthetic_disclosure for sample in manifest.samples if sample.synthetic_disclosure.strip()}
    if len(sample_values) == 1:
        return next(iter(sample_values))
    raise StageExecutionError("cannot derive a single batch synthetic_disclosure for hocrgen import metadata")


def _validate_import_metadata_packet(
    root: Path,
    manifest_path: Path,
    manifest: PublicGenerationManifest,
    packet: dict[str, Any],
) -> None:
    try:
        typed_packet = HocrsyngenImportMetadataPacket.model_validate(packet)
    except ValidationError as exc:
        raise StageExecutionError(f"hocrgen import metadata packet validation failed: {exc}") from exc
    manifest_sha256 = _sha256_evidence_file(root, manifest_path, "generated generation_manifest.v1")
    if typed_packet.source_manifest.sha256 != manifest_sha256:
        raise StageExecutionError("hocrgen import metadata packet source_manifest.sha256 does not match manifest")
    if typed_packet.source_manifest.path != _relative_to_root(root, manifest_path):
        raise StageExecutionError("hocrgen import metadata packet source_manifest.path does not match manifest")

    packet_sample_ids = [sample.sample_id for sample in typed_packet.samples]
    manifest_sample_ids = [sample.sample_id for sample in manifest.samples]
    if packet_sample_ids != manifest_sample_ids:
        raise StageExecutionError("hocrgen import metadata packet sample ids must match manifest order exactly")
    if typed_packet.validation.page_count != sum(len(sample.pages) for sample in manifest.samples):
        raise StageExecutionError("hocrgen import metadata packet validation.page_count does not match manifest")
    if typed_packet.validation.generator_versions != sorted({sample.generator_version for sample in manifest.samples}):
        raise StageExecutionError("hocrgen import metadata packet validation.generator_versions does not match manifest")
    actual_errors = _release_import_model_validation_errors(
        manifest,
        typed_packet.provider_metadata.model_dump(mode="json"),
        [sample.model_dump(mode="json") for sample in typed_packet.samples],
        typed_packet.batch_metadata.synthetic_disclosure,
    )
    if actual_errors != typed_packet.validation.release_import_model_validation_errors:
        raise StageExecutionError(
            "hocrgen import metadata packet release-import validation errors do not match computed validation"
        )
    if typed_packet.validation.validated_against_hocrgen_release_import_model != (not actual_errors):
        raise StageExecutionError(
            "hocrgen import metadata packet release-import validation flag does not match computed validation"
        )


def _release_import_model_validation_errors(
    manifest: PublicGenerationManifest,
    provider_metadata: dict[str, Any],
    packet_samples: list[dict[str, Any]],
    synthetic_disclosure: str,
) -> list[str]:
    runtime_contract = provider_metadata.get("runtime_contract") if isinstance(provider_metadata, dict) else None
    if not isinstance(runtime_contract, dict) or runtime_contract.get("evidence_status") != "validated_from_candidate_evidence_report":
        return [
            "provider_runtime contract is not provided by candidate_evidence_run_report; "
            "used_network/used_rest_service/used_gpu/used_llm/used_diffusion remain unproven"
        ]
    flat_provider_metadata = {
        "provider_name": provider_metadata.get("provider_name"),
        "provider_version": provider_metadata.get("provider_version"),
        "generation_mode": provider_metadata.get("generation_mode"),
        "used_network": runtime_contract.get("used_network"),
        "used_rest_service": runtime_contract.get("used_rest_service"),
        "used_gpu": runtime_contract.get("used_gpu"),
        "used_llm": runtime_contract.get("used_llm"),
        "used_diffusion": runtime_contract.get("used_diffusion"),
    }
    metadata_by_sample = {sample["sample_id"]: sample for sample in packet_samples}
    hardened_samples = []
    for sample in manifest.samples:
        metadata = metadata_by_sample[sample.sample_id]
        hardened_samples.append(
            {
                "sample_id": sample.sample_id,
                "pages": [page.model_dump(mode="json") for page in sample.pages],
                "text": sample.text.model_dump(mode="json"),
                "rendering_metadata": metadata["rendering_metadata"],
                "hebrew_coverage": metadata["hebrew_coverage"],
                "generator_version": sample.generator_version,
                "recipe_id": sample.recipe_id,
                "provenance": sample.provenance.model_dump(mode="json"),
                "license": sample.license,
                "synthetic_disclosure": sample.synthetic_disclosure,
                "controls": sample.controls.model_dump(mode="json"),
            }
        )
    hardened_payload: dict[str, Any] = {
        "manifest_version": manifest.manifest_version,
        "generator_name": manifest.generator_name,
        "provider_metadata": flat_provider_metadata,
        "license": manifest.license,
        "synthetic_disclosure": synthetic_disclosure,
        "samples": hardened_samples,
    }
    try:
        HocrsyngenGenerationManifest.model_validate(hardened_payload)
    except ValidationError as exc:
        return [f"hocrgen release/import model validation failed: {exc}"]
    return []


def _sample_summary(sample: PublicGeneratedSample) -> dict[str, Any]:
    return {
        "sample_id": sample.sample_id,
        "generator_version": sample.generator_version,
        "recipe_id": sample.recipe_id,
        "provenance": {
            "seed": sample.provenance.seed,
            "sample_index": sample.provenance.sample_index,
            "template_id": sample.provenance.template_id,
            "recipe_id": sample.provenance.recipe_id,
            "degradation_preset": sample.provenance.degradation_preset,
            "font_id": sample.provenance.font_id,
            "source_corpus": sample.provenance.source_corpus,
        },
        "controls": sample.controls.model_dump(mode="json"),
        "synthetic_disclosure": sample.synthetic_disclosure,
        "text": {
            "script": sample.text.script,
            "language": sample.text.language,
            "direction": sample.text.direction,
            "unicode_normalization": sample.text.unicode_normalization,
            "logical_order_sha256": sha256(sample.text.logical_order.encode("utf-8")).hexdigest(),
        },
        "pages": [
            {
                "page_id": page.page_id,
                "asset_path": page.asset_path,
                "media_type": page.media_type,
                "sha256": page.sha256,
                "width": page.width,
                "height": page.height,
            }
            for page in sample.pages
        ],
    }


def _validate_manifest_uniqueness(manifest: PublicGenerationManifest) -> None:
    sample_ids: set[str] = set()
    sample_indexes: set[int] = set()
    page_ids: set[str] = set()
    asset_paths: set[str] = set()
    for sample in manifest.samples:
        _require_unique("sample_id", sample.sample_id, sample_ids)
        _require_unique("provenance.sample_index", sample.provenance.sample_index, sample_indexes)
        for page in sample.pages:
            _require_unique("page_id", page.page_id, page_ids)
            _require_unique("asset_path", page.asset_path, asset_paths)


def _require_unique(label: str, value: object, seen: set[object]) -> None:
    if value in seen:
        raise StageExecutionError(f"public hocrsyngen manifest contains duplicate {label}: {value}")
    seen.add(value)


def _portable_relative_path(value: str, location: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or "\\" in value
        or "://" in value
        or (len(value) >= 2 and value[1] == ":")
    ):
        raise StageExecutionError(f"{location} must be a relative portable POSIX path: {value}")
    return path


def _relative_to_root(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root).as_posix()
