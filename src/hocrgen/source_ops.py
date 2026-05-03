from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_json_file, load_yaml_file, package_root
from hocrgen.config.models import SourceConfig, SourceOperationalStatus
from hocrgen.core.errors import ConfigValidationError
from hocrgen.fetchers.base import StageOptions

F1_SOURCE_TARGETS = {
    "nli_any_use_permitted": 27,
    "pinkas_open": 27,
    "biblia_open": 26,
    "project_synthetic": 80,
}

F1_REAL_TARGET_COUNT = 80
F1_SYNTHETIC_TARGET_COUNT = 80
NLI_EXPLORATORY_CATALOG = "package://data/nli/seed_catalog.yaml"
STATIC_EXPANSION_SOURCE_IDS = {"pinkas_open", "biblia_open"}
STATIC_EXPANSION_REQUIRED_RECORD_FIELDS = {
    "id",
    "title",
    "source_url",
    "upstream_identifier",
    "collection",
    "period",
    "raw_rights",
    "asset_path",
}
STATIC_EXPANSION_ALLOWED_RAW_RIGHTS = {"PD-IL"}
STATIC_EXPANSION_ALLOWED_LICENSES = {"PD-IL"}
STATIC_EXPANSION_REQUIRED_GATES = {
    "rights",
    "privacy",
    "review",
    "dedupe",
    "split",
    "benchmark",
    "synthetic-cap",
    "export-portability",
}
STATIC_EXPANSION_REQUIRED_NON_GOALS = {
    "broad live-source crawling",
    "public beta export",
    "release-candidate export",
    "publication",
    "network-dependent CI",
}


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


@dataclass(frozen=True)
class SourceDepthFeasibilityResult:
    source_id: str
    fetcher: str
    target_count: int
    observed_candidate_count: int
    runnable_cached_candidate_count: int
    asset_count: int
    exploratory_catalog_count: int
    source_health_status: str
    source_skip_reason: str | None
    expansion_path_status: str
    expansion_path_checks: list[dict[str, Any]]
    gap: int
    feasibility_status: str
    operator_notes: list[str]

    def model_dump(self) -> dict[str, Any]:
        return {
            "asset_count": self.asset_count,
            "exploratory_catalog_count": self.exploratory_catalog_count,
            "expansion_path_checks": self.expansion_path_checks,
            "expansion_path_status": self.expansion_path_status,
            "feasibility_status": self.feasibility_status,
            "fetcher": self.fetcher,
            "gap": self.gap,
            "observed_candidate_count": self.observed_candidate_count,
            "operator_notes": self.operator_notes,
            "runnable_cached_candidate_count": self.runnable_cached_candidate_count,
            "source_health_status": self.source_health_status,
            "source_id": self.source_id,
            "source_skip_reason": self.source_skip_reason,
            "target_count": self.target_count,
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


def evaluate_f1_source_depth_feasibility(
    bundle: ConfigBundle,
    source_health: Iterable[SourceHealthResult | dict[str, Any]],
) -> dict[str, Any]:
    health_by_source: dict[str, dict[str, Any]] = {}
    for result in source_health:
        record = _health_record(result)
        health_by_source[record["source_id"]] = record
    sources_by_id = {source.id: source for source in bundle.source_registry.sources}
    source_results: list[SourceDepthFeasibilityResult] = []
    for source_id, target_count in F1_SOURCE_TARGETS.items():
        source = sources_by_id.get(source_id)
        health = health_by_source.get(source_id)
        if source is None or health is None:
            source_results.append(_missing_source_depth_result(source_id, target_count, source, health))
            continue
        exploratory_count = _exploratory_candidate_count(source, bundle)
        expansion_path_status, expansion_path_checks = _source_depth_expansion_path(source, bundle)
        observed_candidate_count = int(health["candidate_count"])
        asset_count = int(health["asset_count"])
        runnable_cached_count = _runnable_cached_candidate_count(source, health, observed_candidate_count, asset_count)
        gap = max(target_count - runnable_cached_count, 0)
        status, notes = _source_depth_status_and_notes(
            source_id=source_id,
            fetcher=source.fetcher,
            target_count=target_count,
            runnable_cached_count=runnable_cached_count,
            observed_candidate_count=observed_candidate_count,
            asset_count=asset_count,
            exploratory_count=exploratory_count,
            gap=gap,
            health_status=str(health["health_status"]),
            skip_reason=health.get("skip_reason"),
            expansion_path_status=expansion_path_status,
        )
        source_results.append(
            SourceDepthFeasibilityResult(
                source_id=source_id,
                fetcher=source.fetcher,
                target_count=target_count,
                observed_candidate_count=observed_candidate_count,
                runnable_cached_candidate_count=runnable_cached_count,
                asset_count=asset_count,
                exploratory_catalog_count=exploratory_count,
                source_health_status=str(health["health_status"]),
                source_skip_reason=health.get("skip_reason"),
                expansion_path_status=expansion_path_status,
                expansion_path_checks=expansion_path_checks,
                gap=gap,
                feasibility_status=status,
                operator_notes=notes,
            )
        )
    return source_depth_feasibility_report(source_results)


def source_depth_feasibility_report(
    results: Iterable[SourceDepthFeasibilityResult | dict[str, Any]],
) -> dict[str, Any]:
    sources = [_source_depth_record(result) for result in results]
    real_source_ids = {"nli_any_use_permitted", "pinkas_open", "biblia_open"}
    not_ready = [source for source in sources if source["feasibility_status"] != "feasible"]
    f1c_blocking = [source for source in sources if source["feasibility_status"] != "feasible"]
    not_feasible = [source for source in f1c_blocking if source["feasibility_status"] == "not_feasible"]
    warnings = (
        [f"F1 source-depth feasibility is not met for: {', '.join(source['source_id'] for source in not_ready)}."]
        if not_ready
        else []
    )
    return {
        "trial": "F1 beta-scale acquisition trial",
        "artifact_scope": "operator_only",
        "real_target_count": F1_REAL_TARGET_COUNT,
        "synthetic_target_count": F1_SYNTHETIC_TARGET_COUNT,
        "real_source_allocation": {
            "nli_any_use_permitted": F1_SOURCE_TARGETS["nli_any_use_permitted"],
            "pinkas_open": F1_SOURCE_TARGETS["pinkas_open"],
            "biblia_open": F1_SOURCE_TARGETS["biblia_open"],
        },
        "sources": sources,
        "summary": {
            "target_count": sum(source["target_count"] for source in sources),
            "real_target_count": sum(source["target_count"] for source in sources if source["source_id"] in real_source_ids),
            "observed_candidate_count": sum(source["observed_candidate_count"] for source in sources),
            "runnable_cached_candidate_count": sum(source["runnable_cached_candidate_count"] for source in sources),
            "asset_count": sum(source["asset_count"] for source in sources),
            "exploratory_catalog_count": sum(source["exploratory_catalog_count"] for source in sources),
            "gap": sum(source["gap"] for source in sources),
            "not_ready_source_count": len(not_ready),
            "not_ready_sources": [source["source_id"] for source in not_ready],
            "f1c_blocking_source_count": len(f1c_blocking),
            "f1c_blocking_sources": [source["source_id"] for source in f1c_blocking],
            "not_feasible_source_count": len(not_feasible),
            "not_feasible_sources": [source["source_id"] for source in not_feasible],
            "overall_feasibility_status": "not_feasible" if not_ready else "feasible",
            "warnings": warnings,
        },
        "required_gates": [
            "rights",
            "privacy",
            "review",
            "dedupe",
            "split",
            "benchmark",
            "synthetic-cap",
            "export-portability",
        ],
        "non_goals": [
            "broad live-source crawling",
            "public beta export",
            "release-candidate export",
            "publication",
            "network-dependent CI",
        ],
    }


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


def _source_depth_record(result: SourceDepthFeasibilityResult | dict[str, Any]) -> dict[str, Any]:
    if isinstance(result, SourceDepthFeasibilityResult):
        return result.model_dump()
    result.setdefault("expansion_path_status", "not_applicable")
    result.setdefault("expansion_path_checks", [])
    return result


def _exploratory_candidate_count(source: SourceConfig, bundle: ConfigBundle) -> int:
    if source.fetcher != "nli":
        return 0
    catalog_path = bundle.resolve_path(NLI_EXPLORATORY_CATALOG)
    data = load_yaml_file(catalog_path)
    items = data.get("items", []) if isinstance(data, dict) else []
    return len(items) if isinstance(items, list) else 0


def _missing_source_depth_result(
    source_id: str,
    target_count: int,
    source: SourceConfig | None,
    health: dict[str, Any] | None,
) -> SourceDepthFeasibilityResult:
    missing = []
    if source is None:
        missing.append("source configuration")
    if health is None:
        missing.append("source health")
    return SourceDepthFeasibilityResult(
        source_id=source_id,
        fetcher=source.fetcher if source is not None else "missing",
        target_count=target_count,
        observed_candidate_count=int(health.get("candidate_count", 0)) if health else 0,
        runnable_cached_candidate_count=0,
        asset_count=int(health.get("asset_count", 0)) if health else 0,
        exploratory_catalog_count=0,
        source_health_status=str(health.get("health_status", "missing")) if health else "missing",
        source_skip_reason=health.get("skip_reason") if health else None,
        expansion_path_status="missing",
        expansion_path_checks=[],
        gap=target_count,
        feasibility_status="not_feasible",
        operator_notes=[
            f"Missing required F1 {' and '.join(missing)} for {source_id}.",
            "Target scale is not feasible until the required source is configured and source health can be evaluated.",
        ],
    )


def _runnable_cached_candidate_count(
    source: SourceConfig,
    health: dict[str, Any],
    observed_candidate_count: int,
    asset_count: int,
) -> int:
    if health["health_status"] != "ok" or health.get("skip_reason") is not None:
        return 0
    if source.source_operations.operational_status != SourceOperationalStatus.active:
        return 0
    if source.fetcher in {"nli", "pinkas", "biblia"} and asset_count < observed_candidate_count:
        return 0
    if source.fetcher == "synthetic" and asset_count <= 0:
        return 0
    return observed_candidate_count


def _source_depth_status_and_notes(
    *,
    source_id: str,
    fetcher: str,
    target_count: int,
    runnable_cached_count: int,
    observed_candidate_count: int,
    asset_count: int,
    exploratory_count: int,
    gap: int,
    health_status: str,
    skip_reason: str | None,
    expansion_path_status: str = "not_applicable",
) -> tuple[str, list[str]]:
    health_notes = []
    if health_status != "ok":
        health_notes.append(f"Source health is {health_status}; observed candidates do not count as runnable/cached depth.")
    if skip_reason is not None:
        health_notes.append(f"Source is skipped for {skip_reason}; observed candidates do not count as runnable/cached depth.")
    if observed_candidate_count and runnable_cached_count == 0 and not health_notes:
        health_notes.append("Observed candidates do not have enough validated cached assets to count as runnable/cached depth.")
    if source_id in {"pinkas_open", "biblia_open"}:
        if expansion_path_status == "ok":
            notes = [
                f"Only {runnable_cached_count} runnable/cached record(s) qualify for a target of {target_count}.",
                *health_notes,
                "Source-depth expansion path is defined, fixture-backed, rights-safe, and reviewable.",
                "F1c remains blocked until enough packaged records and cached assets qualify for the target.",
            ]
            return ("needs_fixture_expansion" if gap else "feasible", notes)
        return (
            "not_feasible",
            [
                f"Only {runnable_cached_count} runnable/cached record(s) qualify for a target of {target_count}.",
                *health_notes,
                "Target scale is not feasible until source-depth expansion is defined, fixture-backed, rights-safe, and reviewable.",
            ],
        )
    if source_id == "nli_any_use_permitted":
        notes = [
            f"{runnable_cached_count} runnable/cached fixture-backed seed(s) qualify for the target.",
            f"{exploratory_count} exploratory catalog seed(s) can inform operator promotion, but they are not runnable/cached candidates.",
            *health_notes,
            "Seed promotion must remain operator-run and cached; CI must not depend on live NLI access.",
        ]
        return ("needs_promotion" if gap else "feasible", notes)
    if fetcher == "synthetic":
        notes = [
            f"{runnable_cached_count} configured synthetic candidate(s) qualify for a target of {target_count}.",
            *health_notes,
            "Synthetic scale remains bounded by the existing synthetic-cap and quality/reporting gates.",
        ]
        return ("needs_configuration" if gap else "feasible", notes)
    return (
        "not_feasible" if gap else "feasible",
        [
            f"{asset_count} asset(s) and {runnable_cached_count} runnable/cached candidate(s) qualify for target {target_count}.",
            *health_notes,
        ],
    )


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
    data = _load_yaml_checked(checks, "seed_manifest", manifest_path, bundle)
    items = data.get("items", []) if isinstance(data, dict) else []
    candidate_count = len(items) if isinstance(items, list) else 0
    asset_count = 0
    if not isinstance(items, list):
        checks.append(
            {
                "name": "seed_manifest_items",
                "path": _format_health_path(manifest_path, bundle),
                "status": "error",
                "message": "items must be a list",
            }
        )
        return checks, candidate_count, asset_count
    for item in items:
        if not isinstance(item, dict):
            checks.append(
                {
                    "name": "seed_manifest_item",
                    "path": _format_health_path(manifest_path, bundle),
                    "status": "error",
                    "message": "item must be an object",
                }
            )
            continue
        fixture_reference = item.get("fixture_html")
        if not fixture_reference:
            continue
        fixture_path = _resolve_source_local_reference(str(fixture_reference), manifest_path, bundle)
        asset_count += 1
        checks.append(_path_check("fixture_html", fixture_path, bundle))
    return checks, candidate_count, asset_count


def _inspect_records_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    records_path = bundle.resolve_path(source.settings.records_path or "")
    data = _load_json_checked(checks, "records_path", records_path, bundle)
    records = data.get("records", []) if isinstance(data, dict) else []
    candidate_count = len(records) if isinstance(records, list) else 0
    asset_count = 0
    if not isinstance(records, list):
        checks.append(
            {
                "name": "records",
                "path": _format_health_path(records_path, bundle),
                "status": "error",
                "message": "records must be a list",
            }
        )
        return checks, candidate_count, asset_count
    for record in records:
        if not isinstance(record, dict):
            checks.append(
                {
                    "name": "record",
                    "path": _format_health_path(records_path, bundle),
                    "status": "error",
                    "message": "record must be an object",
                }
            )
            continue
        asset_reference = record.get("asset_path")
        if not asset_reference:
            continue
        asset_path = _resolve_source_local_reference(str(asset_reference), records_path, bundle)
        asset_count += 1
        checks.append(_path_check("record_asset", asset_path, bundle))
    checks.extend(_expansion_manifest_checks(source, bundle, records_path=records_path, records=records))
    return checks, candidate_count, asset_count


def _source_depth_expansion_path(source: SourceConfig, bundle: ConfigBundle) -> tuple[str, list[dict[str, Any]]]:
    if source.id not in STATIC_EXPANSION_SOURCE_IDS:
        return "not_applicable", []
    records_path = bundle.resolve_path(source.settings.records_path or "")
    data = load_json_file(records_path)
    records = data.get("records", []) if isinstance(data, dict) else []
    checks = _expansion_manifest_checks(source, bundle, records_path=records_path, records=records)
    if not checks:
        return "missing", []
    status = "ok" if all(check["status"] == "ok" for check in checks) else "error"
    return status, checks


def _expansion_manifest_checks(
    source: SourceConfig,
    bundle: ConfigBundle,
    *,
    records_path: Path | None = None,
    records: list[Any] | None = None,
) -> list[dict[str, Any]]:
    manifest_reference = source.settings.extra.get("source_depth_expansion_manifest")
    if manifest_reference is None:
        if source.id in STATIC_EXPANSION_SOURCE_IDS:
            return [
                {
                    "message": "source_depth_expansion_manifest is required for static F1 expansion sources",
                    "name": "source_depth_expansion_manifest",
                    "status": "error",
                }
            ]
        return []
    manifest_path = bundle.resolve_path(str(manifest_reference))
    checks: list[dict[str, Any]] = [_path_check("source_depth_expansion_manifest", manifest_path, bundle)]
    manifest = _load_yaml_checked(checks, "source_depth_expansion_manifest_parse", manifest_path, bundle)
    if not isinstance(manifest, dict):
        checks.append(
            {
                "name": "source_depth_expansion_manifest_schema",
                "path": _format_health_path(manifest_path, bundle),
                "status": "error",
                "message": "manifest must be an object",
            }
        )
        return checks
    expected_target = F1_SOURCE_TARGETS.get(source.id)
    required_fields = {
        "version": 1,
        "source_id": source.id,
        "planning_notation": "F1b2",
        "target_count": expected_target,
        "expansion_mode": "operator_packaged_records",
        "records_path": source.settings.records_path,
    }
    for field, expected in required_fields.items():
        checks.append(
            {
                "actual": manifest.get(field),
                "expected": expected,
                "name": f"source_depth_expansion_{field}",
                "path": _format_health_path(manifest_path, bundle),
                "status": "ok" if manifest.get(field) == expected else "error",
            }
        )
    _append_list_exact_check(
        checks,
        name="source_depth_expansion_allowed_raw_rights",
        manifest_path=manifest_path,
        bundle=bundle,
        actual=manifest.get("allowed_raw_rights"),
        expected=STATIC_EXPANSION_ALLOWED_RAW_RIGHTS,
    )
    _append_list_exact_check(
        checks,
        name="source_depth_expansion_allowed_normalized_licenses",
        manifest_path=manifest_path,
        bundle=bundle,
        actual=manifest.get("allowed_normalized_licenses"),
        expected=STATIC_EXPANSION_ALLOWED_LICENSES,
    )
    _append_list_contains_check(
        checks,
        name="source_depth_expansion_required_record_fields",
        manifest_path=manifest_path,
        bundle=bundle,
        actual=manifest.get("required_record_fields"),
        required=STATIC_EXPANSION_REQUIRED_RECORD_FIELDS,
    )
    _append_list_contains_check(
        checks,
        name="source_depth_expansion_required_gates",
        manifest_path=manifest_path,
        bundle=bundle,
        actual=manifest.get("required_gates"),
        required=STATIC_EXPANSION_REQUIRED_GATES,
    )
    _append_list_contains_check(
        checks,
        name="source_depth_expansion_non_goals",
        manifest_path=manifest_path,
        bundle=bundle,
        actual=manifest.get("non_goals"),
        required=STATIC_EXPANSION_REQUIRED_NON_GOALS,
    )
    review_requirements = manifest.get("review_requirements")
    checks.append(
        {
            "name": "source_depth_expansion_review_requirements",
            "path": _format_health_path(manifest_path, bundle),
            "status": "ok"
            if isinstance(review_requirements, list)
            and len(review_requirements) >= 3
            and all(isinstance(requirement, str) and requirement for requirement in review_requirements)
            else "error",
        }
    )
    asset_root: Path | None = None
    if "asset_root" in manifest:
        asset_root = bundle.resolve_path(str(manifest["asset_root"]))
        checks.append(_path_check("source_depth_expansion_asset_root", asset_root, bundle))
    else:
        checks.append(
            {
                "name": "source_depth_expansion_asset_root",
                "path": _format_health_path(manifest_path, bundle),
                "status": "error",
                "message": "asset_root is required",
            }
        )

    if records_path is not None:
        manifest_records_path = bundle.resolve_path(str(manifest.get("records_path", "")))
        checks.append(
            {
                "actual": _format_health_path(manifest_records_path, bundle),
                "expected": _format_health_path(records_path, bundle),
                "name": "source_depth_expansion_active_records_path",
                "path": _format_health_path(manifest_path, bundle),
                "status": "ok" if manifest_records_path == records_path else "error",
            }
        )
    if asset_root is not None and isinstance(records, list):
        checks.extend(_record_asset_root_checks(source, bundle, records_path or manifest_path, records, asset_root))
    return checks


def _append_list_exact_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    manifest_path: Path,
    bundle: ConfigBundle,
    actual: Any,
    expected: set[str],
) -> None:
    actual_set = set(actual) if isinstance(actual, list) and all(isinstance(item, str) for item in actual) else None
    checks.append(
        {
            "actual": sorted(actual_set) if actual_set is not None else actual,
            "expected": sorted(expected),
            "name": name,
            "path": _format_health_path(manifest_path, bundle),
            "status": "ok" if actual_set == expected else "error",
        }
    )


def _append_list_contains_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    manifest_path: Path,
    bundle: ConfigBundle,
    actual: Any,
    required: set[str],
) -> None:
    actual_set = set(actual) if isinstance(actual, list) and all(isinstance(item, str) for item in actual) else set()
    missing = sorted(required - actual_set)
    checks.append(
        {
            "missing": missing,
            "name": name,
            "path": _format_health_path(manifest_path, bundle),
            "status": "ok" if isinstance(actual, list) and not missing else "error",
        }
    )


def _record_asset_root_checks(
    source: SourceConfig,
    bundle: ConfigBundle,
    records_path: Path,
    records: list[Any],
    asset_root: Path,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    resolved_asset_root = asset_root.resolve()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            continue
        record_id = str(record.get("id", f"record-{index}"))
        missing_fields = sorted(field for field in STATIC_EXPANSION_REQUIRED_RECORD_FIELDS if not record.get(field))
        checks.append(
            {
                "missing": missing_fields,
                "name": "source_depth_expansion_record_fields",
                "record_id": record_id,
                "status": "ok" if not missing_fields else "error",
            }
        )
        rights = record.get("raw_rights")
        checks.append(
            {
                "actual": rights,
                "expected": sorted(STATIC_EXPANSION_ALLOWED_RAW_RIGHTS),
                "name": "source_depth_expansion_record_rights",
                "record_id": record_id,
                "status": "ok" if rights in STATIC_EXPANSION_ALLOWED_RAW_RIGHTS else "error",
            }
        )
        asset_reference = record.get("asset_path")
        if not asset_reference:
            continue
        asset_path = _resolve_source_local_reference(str(asset_reference), records_path, bundle)
        try:
            asset_path.resolve().relative_to(resolved_asset_root)
            under_root = True
        except ValueError:
            under_root = False
        checks.append(
            {
                "asset_path": _format_health_path(asset_path, bundle),
                "asset_root": _format_health_path(resolved_asset_root, bundle),
                "name": "source_depth_expansion_record_asset_root",
                "record_id": record_id,
                "source_id": source.id,
                "status": "ok" if under_root else "error",
            }
        )
    return checks


def _inspect_synthetic_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    font_manifest_path = bundle.resolve_path(source.settings.font_manifest or "")
    text_corpus_path = bundle.resolve_path(source.settings.text_corpus_path or "")
    font_manifest = _load_yaml_checked(checks, "font_manifest", font_manifest_path, bundle)
    checks.append(_path_check("text_corpus", text_corpus_path, bundle))
    fonts = font_manifest.get("fonts", []) if isinstance(font_manifest, dict) else []
    asset_count = 0
    if isinstance(fonts, list):
        for font in fonts:
            if not isinstance(font, dict) or not font.get("file"):
                continue
            asset_count += 1
            checks.append(_path_check("font_file", font_manifest_path.parent / str(font["file"]), bundle))
    else:
        checks.append(
            {
                "name": "fonts",
                "path": _format_health_path(font_manifest_path, bundle),
                "status": "error",
                "message": "fonts must be a list",
            }
        )
    source_depth_count = source.settings.extra.get("f1_source_depth_candidate_count")
    if source.settings.synthetic_batch_size is None:
        candidate_count = 0
    else:
        candidate_count = source_depth_count if isinstance(source_depth_count, int) else source.settings.synthetic_batch_size
    return checks, candidate_count, asset_count


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


def _path_check(name: str, path: Path, bundle: ConfigBundle) -> dict[str, Any]:
    return {"name": name, "path": _format_health_path(path, bundle), "status": "ok" if path.exists() else "error"}


def _format_health_path(path: Path, bundle: ConfigBundle) -> str:
    resolved = path.resolve()
    package_base = package_root().resolve()
    try:
        return f"package://{resolved.relative_to(package_base).as_posix()}"
    except ValueError:
        pass

    try:
        return resolved.relative_to(bundle.config_root.resolve()).as_posix()
    except ValueError:
        return str(resolved)


def _resolve_source_local_reference(reference: str, manifest_path: Path, bundle: ConfigBundle) -> Path:
    if reference.startswith("package://") or Path(reference).is_absolute():
        return bundle.resolve_path(reference)
    return (manifest_path.parent / reference).resolve()


def _load_yaml_checked(checks: list[dict[str, Any]], name: str, path: Path, bundle: ConfigBundle) -> Any:
    checks.append(_path_check(name, path, bundle))
    try:
        return load_yaml_file(path)
    except (ConfigValidationError, OSError) as exc:
        checks.append(
            {"name": f"{name}_parse", "path": _format_health_path(path, bundle), "status": "error", "message": str(exc)}
        )
        return {}


def _load_json_checked(checks: list[dict[str, Any]], name: str, path: Path, bundle: ConfigBundle) -> Any:
    checks.append(_path_check(name, path, bundle))
    try:
        return load_json_file(path)
    except (ConfigValidationError, OSError) as exc:
        checks.append(
            {"name": f"{name}_parse", "path": _format_health_path(path, bundle), "status": "error", "message": str(exc)}
        )
        return {}
