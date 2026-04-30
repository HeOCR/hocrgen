from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_json_file, load_yaml_file
from hocrgen.config.models import SourceConfig, SourceOperationalStatus
from hocrgen.core.errors import ConfigValidationError
from hocrgen.fetchers.base import StageOptions


@dataclass(frozen=True)
class SourceHealthResult:
    source_id: str
    fetcher: str
    operational_status: str
    operational_reason: str
    profile_included: bool
    selection_requested: bool
    selected: bool
    skipped: bool
    skip_reason: str | None
    health_status: str
    candidate_count: int
    asset_count: int
    checks: list[dict[str, Any]]

    def model_dump(self) -> dict[str, Any]:
        return {
            "asset_count": self.asset_count,
            "candidate_count": self.candidate_count,
            "checks": self.checks,
            "fetcher": self.fetcher,
            "health_status": self.health_status,
            "operational_reason": self.operational_reason,
            "operational_status": self.operational_status,
            "profile_included": self.profile_included,
            "selected": self.selected,
            "selection_requested": self.selection_requested,
            "skip_reason": self.skip_reason,
            "skipped": self.skipped,
            "source_id": self.source_id,
        }


def evaluate_source_health(bundle: ConfigBundle, profile_id: str, options: StageOptions) -> list[SourceHealthResult]:
    profile = bundle.profiles[profile_id]
    included_source_ids = set(profile.include_sources) - set(profile.exclude_sources)
    requested_source_ids = options.source_filter
    results: list[SourceHealthResult] = []
    for source in bundle.source_registry.sources:
        profile_included = source.id in included_source_ids
        selection_requested = profile_included and (requested_source_ids is None or source.id in requested_source_ids)
        checks, candidate_count, asset_count = _inspect_source(source, bundle)
        expectation_checks = _check_expectations(source, candidate_count, asset_count)
        all_checks = [*checks, *expectation_checks]
        health_status = "ok" if all(check["status"] == "ok" for check in all_checks) else "error"
        skip_reason = _skip_reason(source, selection_requested, health_status)
        results.append(
            SourceHealthResult(
                source_id=source.id,
                fetcher=source.fetcher,
                operational_status=source.source_operations.operational_status.value,
                operational_reason=source.source_operations.operational_reason,
                profile_included=profile_included,
                selection_requested=selection_requested,
                selected=selection_requested and skip_reason is None,
                skipped=selection_requested and skip_reason is not None,
                skip_reason=skip_reason,
                health_status=health_status,
                candidate_count=candidate_count,
                asset_count=asset_count,
                checks=all_checks,
            )
        )
    return results


def source_health_summary(source_health: Iterable[SourceHealthResult | dict[str, Any]]) -> dict[str, Any]:
    results = [_health_record(result) for result in source_health]
    skipped = [result for result in results if result["skipped"]]
    unhealthy = [result for result in results if result["health_status"] != "ok"]
    return {
        "active_source_count": sum(1 for result in results if result["operational_status"] == SourceOperationalStatus.active.value),
        "degraded_source_count": sum(1 for result in results if result["operational_status"] == SourceOperationalStatus.degraded.value),
        "frozen_source_count": sum(1 for result in results if result["operational_status"] == SourceOperationalStatus.frozen.value),
        "selected_source_count": sum(1 for result in results if result["selected"]),
        "skipped_source_count": len(skipped),
        "skipped_sources": [
            {
                "operational_reason": result["operational_reason"],
                "operational_status": result["operational_status"],
                "skip_reason": result["skip_reason"],
                "source_id": result["source_id"],
            }
            for result in skipped
        ],
        "unhealthy_source_count": len(unhealthy),
        "unhealthy_sources": [
            {
                "health_status": result["health_status"],
                "source_id": result["source_id"],
            }
            for result in unhealthy
        ],
    }


def _health_record(result: SourceHealthResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, SourceHealthResult):
        return result.model_dump()
    return result

def _skip_reason(source: SourceConfig, selection_requested: bool, health_status: str) -> str | None:
    if not selection_requested:
        return None
    operational_status = source.source_operations.operational_status
    if operational_status == SourceOperationalStatus.frozen:
        return "source_frozen"
    if operational_status == SourceOperationalStatus.degraded:
        return "source_degraded"
    if health_status != "ok":
        return "source_health_failed"
    return None


def _inspect_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    if source.fetcher == "nli":
        return _inspect_nli_source(source, bundle)
    if source.fetcher in {"pinkas", "biblia"}:
        return _inspect_records_source(source, bundle)
    if source.fetcher == "synthetic":
        return _inspect_synthetic_source(source, bundle)
    return ([{"name": "known_fetcher", "status": "error", "message": f"unknown fetcher: {source.fetcher}"}], 0, 0)


def _inspect_nli_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    manifest_path = bundle.resolve_path(source.settings.seed_manifest or "")
    data = _load_yaml_checked(checks, "seed_manifest", manifest_path)
    items = data.get("items", []) if isinstance(data, dict) else []
    candidate_count = len(items) if isinstance(items, list) else 0
    asset_count = 0
    if not isinstance(items, list):
        checks.append({"name": "seed_manifest_items", "path": str(manifest_path), "status": "error", "message": "items must be a list"})
        return checks, candidate_count, asset_count
    for item in items:
        if not isinstance(item, dict):
            checks.append({"name": "seed_manifest_item", "path": str(manifest_path), "status": "error", "message": "item must be an object"})
            continue
        fixture_reference = item.get("fixture_html")
        if not fixture_reference:
            continue
        fixture_path = _resolve_source_local_reference(str(fixture_reference), manifest_path, bundle)
        asset_count += 1
        checks.append(_path_check("fixture_html", fixture_path))
    return checks, candidate_count, asset_count


def _inspect_records_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    records_path = bundle.resolve_path(source.settings.records_path or "")
    data = _load_json_checked(checks, "records_path", records_path)
    records = data.get("records", []) if isinstance(data, dict) else []
    candidate_count = len(records) if isinstance(records, list) else 0
    asset_count = 0
    if not isinstance(records, list):
        checks.append({"name": "records", "path": str(records_path), "status": "error", "message": "records must be a list"})
        return checks, candidate_count, asset_count
    for record in records:
        if not isinstance(record, dict):
            checks.append({"name": "record", "path": str(records_path), "status": "error", "message": "record must be an object"})
            continue
        asset_reference = record.get("asset_path")
        if not asset_reference:
            continue
        asset_path = _resolve_source_local_reference(str(asset_reference), records_path, bundle)
        asset_count += 1
        checks.append(_path_check("record_asset", asset_path))
    return checks, candidate_count, asset_count


def _inspect_synthetic_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    font_manifest_path = bundle.resolve_path(source.settings.font_manifest or "")
    text_corpus_path = bundle.resolve_path(source.settings.text_corpus_path or "")
    font_manifest = _load_yaml_checked(checks, "font_manifest", font_manifest_path)
    checks.append(_path_check("text_corpus", text_corpus_path))
    fonts = font_manifest.get("fonts", []) if isinstance(font_manifest, dict) else []
    asset_count = 0
    if isinstance(fonts, list):
        for font in fonts:
            if not isinstance(font, dict) or not font.get("file"):
                continue
            asset_count += 1
            checks.append(_path_check("font_file", font_manifest_path.parent / str(font["file"])))
    else:
        checks.append({"name": "fonts", "path": str(font_manifest_path), "status": "error", "message": "fonts must be a list"})
    return checks, source.settings.synthetic_batch_size or 0, asset_count


def _check_expectations(source: SourceConfig, candidate_count: int, asset_count: int) -> list[dict[str, Any]]:
    expectations = source.source_operations.health_expectations
    checks: list[dict[str, Any]] = []
    if expectations.min_candidates is not None:
        checks.append(_minimum_check("min_candidates", candidate_count, expectations.min_candidates))
    if expectations.min_assets is not None:
        checks.append(_minimum_check("min_assets", asset_count, expectations.min_assets))
    return checks


def _minimum_check(name: str, actual: int, expected: int) -> dict[str, Any]:
    status = "ok" if actual >= expected else "error"
    return {"actual": actual, "expected": expected, "name": name, "status": status}


def _path_check(name: str, path: Path) -> dict[str, Any]:
    return {"name": name, "path": str(path), "status": "ok" if path.exists() else "error"}


def _resolve_source_local_reference(reference: str, manifest_path: Path, bundle: ConfigBundle) -> Path:
    if reference.startswith("package://") or Path(reference).is_absolute():
        return bundle.resolve_path(reference)
    return (manifest_path.parent / reference).resolve()


def _load_yaml_checked(checks: list[dict[str, Any]], name: str, path: Path) -> Any:
    checks.append(_path_check(name, path))
    try:
        return load_yaml_file(path)
    except (ConfigValidationError, OSError) as exc:
        checks.append({"name": f"{name}_parse", "path": str(path), "status": "error", "message": str(exc)})
        return {}


def _load_json_checked(checks: list[dict[str, Any]], name: str, path: Path) -> Any:
    checks.append(_path_check(name, path))
    try:
        return load_json_file(path)
    except (ConfigValidationError, OSError) as exc:
        checks.append({"name": f"{name}_parse", "path": str(path), "status": "error", "message": str(exc)})
        return {}
