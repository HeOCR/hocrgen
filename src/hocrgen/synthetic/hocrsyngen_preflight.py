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
from hocrgen.utils.hashing import sha256_file


REPORT_SCHEMA_VERSION = "hocrgen_hocrsyngen_preflight_report.v1"
PLANNING_NOTATION = "F6f2a"
MANIFEST_FILENAME = "generation_manifest.json"

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


@dataclass(frozen=True)
class HocrsyngenPreflightResult:
    report_path: Path
    report: dict[str, Any]


def run_hocrsyngen_preflight(
    evidence_root: Path,
    *,
    report_path: Path | None = None,
    overwrite: bool = False,
) -> HocrsyngenPreflightResult:
    root = evidence_root.resolve()
    if not root.exists():
        raise StageExecutionError(f"hocrsyngen evidence root does not exist: {evidence_root}")
    if not root.is_dir():
        raise StageExecutionError(f"hocrsyngen evidence root is not a directory: {evidence_root}")

    destination = (report_path or (root / "hocrgen_preflight_report.json")).resolve()
    if destination.exists() and not overwrite:
        raise StageExecutionError(f"hocrsyngen preflight report already exists: {destination}")

    evidence_report_path = root / "candidate_evidence_run_report.json"
    evidence_report = _read_json_object(evidence_report_path, "candidate evidence run report")
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

    manifest_payload = _read_json_object(manifest_path, "generated generation_manifest.v1")
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

    checksum_inventory = _verify_checksum_inventory(root)
    catalog_result = _validate_template_catalog_join(manifest, reports["template_catalog_v2"]["payload"])
    asset_checks = _validate_assets(generated_batch, manifest)
    missing_metadata = _missing_release_metadata(manifest_payload)
    rendering_coverage = _rendering_coverage_reference(root, evidence_report)

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
            "sha256": sha256_file(evidence_report_path),
            "count": evidence_report.get("count"),
            "seed": evidence_report.get("seed"),
            "generator_version": evidence_report.get("generator_version"),
            "started_at_utc": evidence_report.get("started_at_utc"),
            "completed_at_utc": evidence_report.get("completed_at_utc"),
            "release_eligible": evidence_report.get("release_eligible"),
        },
        "source_batch": {
            "path": _relative_to_root(root, generated_batch),
            "boundary_id": f"sha256:{sha256_file(manifest_path)}",
            "manifest_path": _relative_to_root(root, manifest_path),
            "manifest_sha256": sha256_file(manifest_path),
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

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        raise StageExecutionError(f"could not write hocrsyngen preflight report to {destination}: {exc}") from exc

    return HocrsyngenPreflightResult(report_path=destination, report=report)


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise StageExecutionError(f"{label} is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError as exc:
        raise StageExecutionError(f"{label} has invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc
    except OSError as exc:
        raise StageExecutionError(f"{label} could not be read: {exc}") from exc
    if not isinstance(payload, dict):
        raise StageExecutionError(f"{label} must serialize to an object: {path}")
    return payload


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
    path = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if not path.is_relative_to(root):
        raise StageExecutionError(f"candidate evidence {label} must stay under evidence root: {value}")
    return path


def _load_reports(root: Path, evidence_report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for key, (relative_path, schema_version) in {**REQUIRED_REPORTS, **OPTIONAL_REPORTS}.items():
        path = root / Path(relative_path)
        if key in REQUIRED_REPORTS or path.exists():
            payload = _read_json_object(path, key)
            _require_schema(payload, schema_version, key)
            embedded_reports = evidence_report.get("reports")
            if isinstance(embedded_reports, dict) and key in embedded_reports and embedded_reports[key] != payload:
                raise StageExecutionError(f"candidate evidence embedded report {key} does not match {relative_path}")
            summary: dict[str, Any] = {
                "path": relative_path,
                "sha256": sha256_file(path),
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


def _verify_checksum_inventory(root: Path) -> dict[str, Any]:
    path = root / "SHA256SUMS"
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
        file_path = (root / Path(*rel.parts)).resolve()
        if not file_path.is_relative_to(root):
            raise StageExecutionError(f"SHA256SUMS line {line_number} escapes evidence root: {relative_path}")
        if not file_path.is_file():
            raise StageExecutionError(f"SHA256SUMS line {line_number} references missing file: {relative_path}")
        actual = sha256_file(file_path)
        if actual != digest:
            raise StageExecutionError(f"SHA256SUMS mismatch for {relative_path}: expected {digest}, got {actual}")
        entries.append({"path": relative_path, "sha256": digest})
    if not entries:
        raise StageExecutionError("SHA256SUMS must contain at least one file entry")
    return {
        "path": "SHA256SUMS",
        "sha256": sha256_file(path),
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
            path = (batch_root / Path(*rel.parts)).resolve()
            if not path.is_relative_to(batch_root):
                raise StageExecutionError(f"page asset escapes generated batch root: {page.asset_path}")
            if not path.is_file():
                raise StageExecutionError(f"page asset is missing: {page.asset_path}")
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


def _rendering_coverage_reference(root: Path, evidence_report: dict[str, Any]) -> dict[str, Any]:
    value = evidence_report.get("rendering_coverage_report_path")
    if value is None:
        return {"present": False, "advisory": True}
    path = _resolve_evidence_path(root, value, "rendering_coverage_report_path")
    if not path.is_file():
        raise StageExecutionError(f"rendering coverage report is missing: {path}")
    payload = _read_json_object(path, "rendering coverage report")
    return {
        "present": True,
        "advisory": True,
        "path": _relative_to_root(root, path),
        "sha256": sha256_file(path),
        "coverage_keys": sorted(payload.get("coverage", {}).keys()) if isinstance(payload.get("coverage"), dict) else [],
    }


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
