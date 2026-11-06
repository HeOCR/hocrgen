from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_json_file, load_yaml_file, package_root
from hocrgen.config.models import SourceConfig, SourceOperationalStatus
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.government_print import (
    GOVERNMENT_PRINT_INTEGRITY_REASONS,
    government_print_entry_asset,
    government_print_snapshot_root,
    knesset_entry_exclusion_reasons,
    load_government_print_snapshot,
    reshumot_entry_exclusion_reasons,
)
from hocrgen.fetchers.hash import hash_entry_asset, hash_entry_exclusion_reason, hash_snapshot_root, load_hash_snapshot
from hocrgen.fetchers.hocrsyngen_manifest import validate_hocrsyngen_batch
from hocrgen.fetchers.modern_handwriting import validate_modern_intake_manifest
from hocrgen.fetchers.nli import SEED_CAPTURE_FIELD, SEED_CAPTURE_SHA256_FIELD, parse_nli_fixture_html
from hocrgen.fetchers.nli_iiif import capture_asset_problems, decide_nli_rights, load_nli_manifest_capture
from hocrgen.fetchers.pinkas_dataset import (
    load_entry_line_scopes,
    load_entry_page_lines,
    load_pinkas_dataset_snapshot,
    pinkas_dataset_entry_asset,
    pinkas_dataset_entry_exclusion_reason,
    pinkas_dataset_snapshot_root,
)
from hocrgen.fetchers.pinkas_line_language import load_line_language_tags, page_scope_summary, tag_file_problems
from hocrgen.fetchers.yidtaknl import (
    load_yidtaknl_matched_pages,
    load_yidtaknl_snapshot,
    yidtaknl_entry_asset,
    yidtaknl_entry_exclusion_reason,
    yidtaknl_matched_page_problem,
    yidtaknl_snapshot_root,
)
from hocrgen.fetchers.wikisource import (
    WIKISOURCE_INTEGRITY_REASONS,
    index_exclusion_reasons,
    load_wikisource_snapshot,
    page_exclusion_reasons,
    wikisource_snapshot_root,
)
from hocrgen.utils.hashing import sha256_file

F1_TARGET_SCALE_COUNT_KEY = "f1_source_depth_candidate_count"
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
    extra: dict[str, Any] | None = None

    def model_dump(self) -> dict[str, Any]:
        record = {
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
        if self.extra:
            record["extra"] = self.extra
        return record


@dataclass(frozen=True)
class SourceDepthFeasibilityResult:
    source_id: str
    fetcher: str
    target_count: int
    observed_candidate_count: int
    runnable_cached_candidate_count: int
    target_scale_candidate_count: int
    asset_count: int
    exploratory_catalog_count: int
    source_health_status: str
    source_skip_reason: str | None
    expansion_path_status: str
    expansion_path_checks: list[dict[str, Any]]
    gap: int
    target_scale_gap: int
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
            "target_scale_candidate_count": self.target_scale_candidate_count,
            "target_scale_gap": self.target_scale_gap,
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
        source_inspection = _inspect_source(source, bundle)
        if len(source_inspection) == 4:
            checks, candidate_count, asset_count, extra = source_inspection
        else:
            checks, candidate_count, asset_count = source_inspection
            extra = {}
        recorded_failures = int(extra.get("iiif_recorded_failure_count", 0) or 0)
        expectation_checks = _check_expectations(source, candidate_count, asset_count + recorded_failures)
        if recorded_failures:
            for check in expectation_checks:
                if check["name"] == "min_assets":
                    check["recorded_upstream_failures"] = recorded_failures
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
                extra=extra,
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
        observed_candidate_count = _source_depth_observed_candidate_count(source, health)
        asset_count = _source_depth_asset_count(source, health)
        runnable_cached_count = _runnable_cached_candidate_count(source, health, observed_candidate_count, asset_count)
        target_scale_candidate_count = _target_scale_candidate_count(
            source=source,
            bundle=bundle,
            health=health,
            expansion_path_status=expansion_path_status,
            runnable_cached_count=runnable_cached_count,
        )
        gap = max(target_count - runnable_cached_count, 0)
        target_scale_gap = max(target_count - target_scale_candidate_count, 0)
        status, notes = _source_depth_status_and_notes(
            source_id=source_id,
            fetcher=source.fetcher,
            target_count=target_count,
            runnable_cached_count=runnable_cached_count,
            target_scale_candidate_count=target_scale_candidate_count,
            observed_candidate_count=observed_candidate_count,
            asset_count=asset_count,
            exploratory_count=exploratory_count,
            gap=gap,
            target_scale_gap=target_scale_gap,
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
                target_scale_candidate_count=target_scale_candidate_count,
                asset_count=asset_count,
                exploratory_catalog_count=exploratory_count,
                source_health_status=str(health["health_status"]),
                source_skip_reason=health.get("skip_reason"),
                expansion_path_status=expansion_path_status,
                expansion_path_checks=expansion_path_checks,
                gap=gap,
                target_scale_gap=target_scale_gap,
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
            "target_scale_candidate_count": sum(source["target_scale_candidate_count"] for source in sources),
            "asset_count": sum(source["asset_count"] for source in sources),
            "exploratory_catalog_count": sum(source["exploratory_catalog_count"] for source in sources),
            "gap": sum(source["gap"] for source in sources),
            "target_scale_gap": sum(source["target_scale_gap"] for source in sources),
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
    hocrsyngen_coverage_warnings = [
        {
            "source_id": result["source_id"],
            "warnings": warnings,
        }
        for result in results
        if isinstance(result.get("extra"), dict)
        and (warnings := result["extra"].get("hocrsyngen_coverage_warnings"))
    ]
    nli_iiif_manifest_issues = [
        {
            "issues": issues,
            "source_id": result["source_id"],
        }
        for result in results
        if isinstance(result.get("extra"), dict)
        and (issues := result["extra"].get("iiif_manifest_issues"))
    ]
    return {
        "active_source_count": sum(1 for result in results if result["operational_status"] == SourceOperationalStatus.active.value),
        "degraded_source_count": sum(1 for result in results if result["operational_status"] == SourceOperationalStatus.degraded.value),
        "frozen_source_count": sum(1 for result in results if result["operational_status"] == SourceOperationalStatus.frozen.value),
        "hocrsyngen_coverage_warnings": hocrsyngen_coverage_warnings,
        "nli_iiif_manifest_issues": nli_iiif_manifest_issues,
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
    result.setdefault("target_scale_candidate_count", result.get("runnable_cached_candidate_count", 0))
    result.setdefault("target_scale_gap", result.get("gap", 0))
    return result


def _exploratory_candidate_count(source: SourceConfig, bundle: ConfigBundle) -> int:
    if source.fetcher != "nli":
        return 0
    catalog_path = bundle.resolve_path(NLI_EXPLORATORY_CATALOG)
    data = load_yaml_file(catalog_path)
    items = data.get("items", []) if isinstance(data, dict) else []
    return len(items) if isinstance(items, list) else 0


def _source_depth_observed_candidate_count(source: SourceConfig, health: dict[str, Any]) -> int:
    if source.fetcher == "nli":
        extra = health.get("extra") if isinstance(health.get("extra"), dict) else {}
        source_depth_count = extra.get("source_depth_candidate_count")
        if isinstance(source_depth_count, int):
            return source_depth_count
    return int(health["candidate_count"])


def _source_depth_asset_count(source: SourceConfig, health: dict[str, Any]) -> int:
    if source.fetcher == "nli":
        extra = health.get("extra") if isinstance(health.get("extra"), dict) else {}
        source_depth_asset_count = extra.get("source_depth_asset_count")
        if isinstance(source_depth_asset_count, int):
            return source_depth_asset_count
    return int(health["asset_count"])


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
        target_scale_candidate_count=0,
        asset_count=int(health.get("asset_count", 0)) if health else 0,
        exploratory_catalog_count=0,
        source_health_status=str(health.get("health_status", "missing")) if health else "missing",
        source_skip_reason=health.get("skip_reason") if health else None,
        expansion_path_status="missing",
        expansion_path_checks=[],
        gap=target_count,
        target_scale_gap=target_count,
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
    if source.fetcher in {"nli", "pinkas", "biblia", "hash"} and asset_count < observed_candidate_count:
        return 0
    if source.fetcher in {"hocrsyngen_manifest", "synthetic"} and asset_count <= 0:
        return 0
    return observed_candidate_count


def _target_scale_candidate_count(
    *,
    source: SourceConfig,
    bundle: ConfigBundle,
    health: dict[str, Any],
    expansion_path_status: str,
    runnable_cached_count: int,
) -> int:
    if health["health_status"] != "ok" or health.get("skip_reason") is not None:
        return 0
    if source.source_operations.operational_status != SourceOperationalStatus.active:
        return 0
    if source.id in STATIC_EXPANSION_SOURCE_IDS:
        if expansion_path_status != "ok":
            return runnable_cached_count
        records_path = bundle.resolve_path(source.settings.records_path or "")
        data = load_json_file(records_path)
        records = data.get("records", []) if isinstance(data, dict) else []
        return len(records) if isinstance(records, list) else runnable_cached_count
    if source.fetcher == "synthetic":
        configured_count = source.settings.extra.get(F1_TARGET_SCALE_COUNT_KEY)
        if isinstance(configured_count, int) and configured_count > 0:
            return configured_count
    return runnable_cached_count


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
    target_scale_candidate_count: int | None = None,
    target_scale_gap: int | None = None,
) -> tuple[str, list[str]]:
    if target_scale_candidate_count is None:
        target_scale_candidate_count = runnable_cached_count
    if target_scale_gap is None:
        target_scale_gap = gap
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
                f"{target_scale_candidate_count} packaged source-depth inventory record(s) are validated by source health.",
                *health_notes,
                "Source-depth expansion path is defined, fixture-backed, rights-safe, and reviewable.",
                "F1c remains blocked until target-scale operator trial artifacts exercise the packaged inventory through the pipeline gates.",
            ]
            if gap == 0:
                return "feasible", notes
            return ("needs_target_scale_trial" if target_scale_gap == 0 else "needs_fixture_expansion", notes)
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
    if fetcher == "hocrsyngen_manifest":
        notes = [
            f"{runnable_cached_count} validated hocrsyngen manifest sample(s) qualify for a target of {target_count}.",
            f"{target_scale_candidate_count} manifest-backed synthetic candidate(s) are available from the configured batch.",
            *health_notes,
            "Synthetic target scale requires a larger validated hocrsyngen batch; hocrgen no longer expands this source through the legacy generator.",
            "Synthetic scale remains bounded by the existing synthetic-cap and quality/reporting gates.",
            "F1c remains blocked until target-scale operator trial artifacts exercise a target-sized hocrsyngen batch through the pipeline gates.",
        ]
        if gap == 0:
            return "feasible", notes
        return ("needs_target_scale_trial" if target_scale_gap == 0 else "needs_configuration", notes)
    if fetcher == "synthetic":
        notes = [
            f"{runnable_cached_count} runnable synthetic candidate(s) qualify for a target of {target_count}.",
            f"{target_scale_candidate_count} synthetic candidate(s) are configured for target-scale operator reporting.",
            *health_notes,
            "Synthetic scale remains bounded by the existing synthetic-cap and quality/reporting gates.",
            "F1c remains blocked until target-scale operator trial artifacts exercise the configured controls through the pipeline gates.",
        ]
        if gap == 0:
            return "feasible", notes
        return ("needs_target_scale_trial" if target_scale_gap == 0 else "needs_configuration", notes)
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


def _inspect_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int] | tuple[list[dict[str, Any]], int, int, dict[str, Any]]:
    if source.fetcher == "nli":
        return _inspect_nli_source_with_extra(source, bundle)
    if source.fetcher in {"pinkas", "biblia"}:
        return _inspect_records_source(source, bundle)
    if source.fetcher == "hash":
        return _inspect_hash_source(source, bundle)
    if source.fetcher == "yidtaknl":
        return _inspect_yidtaknl_source(source, bundle)
    if source.fetcher == "wikisource_proofread":
        return _inspect_wikisource_source(source, bundle)
    if source.fetcher in {"reshumot", "knesset_committee"}:
        return _inspect_government_print_source(source, bundle)
    if source.fetcher == "pinkas_dataset":
        return _inspect_pinkas_dataset_source(source, bundle)
    if source.fetcher == "hocrsyngen_manifest":
        return _inspect_hocrsyngen_manifest_source(source, bundle)
    if source.fetcher == "modern_handwriting_intake":
        return _inspect_modern_handwriting_source(source, bundle)
    if source.fetcher == "synthetic":
        return _inspect_synthetic_source(source, bundle)
    return ([{"name": "known_fetcher", "status": "error", "message": f"unknown fetcher: {source.fetcher}"}], 0, 0)


def _inspect_nli_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks, candidate_count, asset_count, _ = _inspect_nli_source_with_extra(source, bundle)
    return checks, candidate_count, asset_count


def _inspect_nli_source_with_extra(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int, dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    manifest_path = bundle.resolve_path(source.settings.seed_manifest or "")
    data = _load_yaml_checked(checks, "seed_manifest", manifest_path, bundle)
    items = data.get("items", []) if isinstance(data, dict) else []
    candidate_count = (
        sum(1 for item in items if not (isinstance(item, dict) and item.get("f1_source_depth_only") is True))
        if isinstance(items, list)
        else 0
    )
    asset_count = 0
    source_depth_candidate_count = len(items) if isinstance(items, list) else 0
    source_depth_asset_count = 0
    capture_count = 0
    manifest_issues: list[dict[str, Any]] = []
    manifest_issue_items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if not isinstance(items, list):
        checks.append(
            {
                "name": "seed_manifest_items",
                "path": _format_health_path(manifest_path, bundle),
                "status": "error",
                "message": "items must be a list",
            }
        )
        return checks, candidate_count, asset_count, {
            "source_depth_asset_count": source_depth_asset_count,
            "source_depth_candidate_count": source_depth_candidate_count,
        }
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
        display_rights: str | None = None
        fixture_path: Path | None = None
        if fixture_reference:
            fixture_path = _resolve_source_local_reference(str(fixture_reference), manifest_path, bundle)
            if item.get("f1_source_depth_only") is not True:
                asset_count += 1
            source_depth_asset_count += 1
            checks.append(_path_check("fixture_html", fixture_path, bundle))
            if fixture_path.exists():
                parsed_fixture = parse_nli_fixture_html(fixture_path)
                display_rights = parsed_fixture.rights
                for asset_reference in parsed_fixture.assets:
                    asset_path = (fixture_path.parent / asset_reference).resolve()
                    checks.append(_path_check("fixture_asset", asset_path, bundle))
        capture_reference = item.get(SEED_CAPTURE_FIELD)
        if capture_reference:
            capture_count += 1
            issue = _inspect_nli_manifest_capture(
                checks=checks,
                item=item,
                capture_reference=str(capture_reference),
                manifest_path=manifest_path,
                fixture_path=fixture_path,
                display_rights=display_rights,
                bundle=bundle,
            )
            if issue is not None:
                manifest_issues.append(issue)
                manifest_issue_items.append((issue, item))
    extra: dict[str, Any] = {
        "source_depth_asset_count": source_depth_asset_count,
        "source_depth_candidate_count": source_depth_candidate_count,
    }
    if capture_count:
        extra["iiif_manifest_capture_count"] = capture_count
        extra["iiif_manifest_issues"] = manifest_issues
        # Seeds whose pinned capture records an upstream failure (HTTP error, zero canvases, a non-free
        # slug) and that have no cached images still reach discovery, so they become rejected
        # candidates instead of failing min_assets and skipping the whole source.
        extra["iiif_recorded_failure_count"] = sum(
            1
            for issue, item in manifest_issue_items
            if not issue["has_fixture"] and item.get("f1_source_depth_only") is not True
        )
    return checks, candidate_count, asset_count, extra


def _inspect_nli_manifest_capture(
    *,
    checks: list[dict[str, Any]],
    item: dict[str, Any],
    capture_reference: str,
    manifest_path: Path,
    fixture_path: Path | None,
    display_rights: str | None,
    bundle: ConfigBundle,
) -> dict[str, Any] | None:
    """Check one pinned IIIF manifest capture.

    Integrity problems (a missing or unparseable capture, a checksum pin mismatch, a missing or
    changed cached page image) are failing checks. Item-level upstream problems (HTTP 403/500, zero
    canvases, a licence slug other than public-domain-free-use) do not fail the source; they are
    returned as an issue so source health surfaces them, and the fetcher rejects the item with the
    same reason code instead of dropping it.
    """

    seed_id = str(item.get("id", ""))
    capture_path = _resolve_source_local_reference(capture_reference, manifest_path, bundle)
    checks.append(_path_check("iiif_manifest_capture", capture_path, bundle))
    if not capture_path.exists():
        return None
    expected_sha256 = item.get(SEED_CAPTURE_SHA256_FIELD)
    if expected_sha256 is None:
        checks.append(
            {
                "name": "iiif_manifest_capture_sha256",
                "path": _format_health_path(capture_path, bundle),
                "status": "error",
                "message": f"seed {seed_id} must pin {SEED_CAPTURE_SHA256_FIELD}",
            }
        )
    else:
        actual_sha256 = sha256_file(capture_path)
        checks.append(
            {
                "name": "iiif_manifest_capture_sha256",
                "path": _format_health_path(capture_path, bundle),
                "status": "ok" if actual_sha256 == expected_sha256 else "error",
            }
        )
    try:
        capture = load_nli_manifest_capture(capture_path)
    except (ValueError, UnicodeDecodeError) as exc:
        checks.append(
            {
                "name": "iiif_manifest_capture_parse",
                "path": _format_health_path(capture_path, bundle),
                "status": "error",
                "message": str(exc),
            }
        )
        return None
    decision = decide_nli_rights(display_rights=display_rights, capture=capture)
    # Admitted items are acquired from the fixture HTML, so their images must be the pinned capture's.
    if decision.accepted and fixture_path is not None and fixture_path.exists():
        problems = capture_asset_problems(capture, fixture_path.parent, parse_nli_fixture_html(fixture_path).assets)
        binding_check: dict[str, Any] = {
            "name": "iiif_capture_asset_binding",
            "path": _format_health_path(fixture_path, bundle),
            "status": "error" if problems else "ok",
        }
        if problems:
            binding_check["message"] = f"fixture images not bound to pinned capture canvases: {', '.join(problems)}"
        checks.append(binding_check)
    if decision.accepted:
        return None
    return {
        "canvas_count": capture.canvas_count,
        "has_fixture": fixture_path is not None,
        "http_status": capture.http_status,
        "license_slug": decision.license_slug,
        "manifest_url": capture.manifest_url,
        "reason": decision.reason,
        "seed_id": seed_id,
    }


def _inspect_records_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    records_path = bundle.resolve_path(source.settings.records_path or "")
    data = _load_json_checked(checks, "records_path", records_path, bundle)
    records = data.get("records", []) if isinstance(data, dict) else []
    candidate_count = (
        sum(1 for record in records if not (isinstance(record, dict) and record.get("f1_source_depth_only") is True))
        if isinstance(records, list)
        else 0
    )
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
        record_id = str(record.get("id", "record"))
        if "f1_source_depth_only" in record:
            checks.append(
                {
                    "actual": record.get("f1_source_depth_only"),
                    "expected": "boolean",
                    "name": "source_depth_expansion_record_source_depth_only",
                    "record_id": record_id,
                    "status": "ok" if isinstance(record.get("f1_source_depth_only"), bool) else "error",
                }
            )
        asset_reference = record.get("asset_path")
        if not asset_reference:
            continue
        asset_path = _resolve_source_local_reference(str(asset_reference), records_path, bundle)
        if record.get("f1_source_depth_only") is not True:
            asset_count += 1
        checks.append(_path_check("record_asset", asset_path, bundle))
    checks.extend(_expansion_manifest_checks(source, bundle, records_path=records_path, records=records))
    return checks, candidate_count, asset_count


def _inspect_hash_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    try:
        root = hash_snapshot_root(source, bundle)
    except StageExecutionError as exc:
        return [{"name": "hash_snapshot_root", "status": "error", "message": str(exc)}], 0, 0
    snapshot_path = root / "snapshot.yaml"
    checks.append(_path_check("hash_snapshot", snapshot_path, bundle))
    if not snapshot_path.exists():
        return checks, 0, 0
    try:
        snapshot, entries = load_hash_snapshot(root)
    except (OSError, ValueError) as exc:
        checks.append({"name": "hash_entries", "path": _format_health_path(root, bundle), "status": "error", "message": str(exc)})
        return checks, 0, 0
    checks.append(
        {
            "name": "hash_upstream_commit",
            "actual": snapshot.get("upstream_commit"),
            "status": "ok" if snapshot.get("upstream_commit") else "error",
        }
    )
    candidate_count = 0
    asset_count = 0
    exclusions: dict[str, int] = {}
    for entry in entries:
        reason = hash_entry_exclusion_reason(entry, source)
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        candidate_count += 1
        asset = hash_entry_asset(entry) or {}
        asset_path = (root / str(asset.get("local_path", ""))).resolve()
        check = _path_check("hash_entry_asset", asset_path, bundle)
        if asset_path.exists() and asset.get("sha256") and sha256_file(asset_path) != asset["sha256"]:
            check["status"] = "error"
            check["message"] = f"checksum mismatch for {entry['entry_id']}"
        if check["status"] == "ok":
            asset_count += 1
        checks.append(check)
    checks.append({"name": "hash_entry_exclusions", "actual": dict(sorted(exclusions.items())), "status": "ok"})
    return checks, candidate_count, asset_count


def _inspect_yidtaknl_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    try:
        root = yidtaknl_snapshot_root(source, bundle)
    except StageExecutionError as exc:
        return [{"name": "yidtaknl_snapshot_root", "status": "error", "message": str(exc)}], 0, 0
    snapshot_path = root / "snapshot.yaml"
    checks.append(_path_check("yidtaknl_snapshot", snapshot_path, bundle))
    if not snapshot_path.exists():
        return checks, 0, 0
    try:
        snapshot, entries = load_yidtaknl_snapshot(root)
    except (OSError, ValueError) as exc:
        checks.append({"name": "yidtaknl_entries", "path": _format_health_path(root, bundle), "status": "error", "message": str(exc)})
        return checks, 0, 0
    checks.append(
        {
            "name": "yidtaknl_dataset_doi",
            "actual": snapshot.get("dataset_doi"),
            "status": "ok" if snapshot.get("dataset_doi") else "error",
        }
    )
    candidate_count = 0
    asset_count = 0
    exclusions: dict[str, int] = {}
    for entry in entries:
        reason = yidtaknl_entry_exclusion_reason(entry, source, root)
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        candidate_count += 1
        asset = yidtaknl_entry_asset(entry) or {}
        asset_path = (root / str(asset.get("local_path", ""))).resolve()
        asset_check = _path_check("yidtaknl_entry_asset", asset_path, bundle)
        if asset_path.exists() and asset.get("sha256") and sha256_file(asset_path) != asset["sha256"]:
            asset_check["status"] = "error"
            asset_check["message"] = f"checksum mismatch for {entry['entry_id']}"
        text = entry.get("text") or {}
        text_path = (root / str(text.get("local_path", ""))).resolve()
        text_check = _path_check("yidtaknl_entry_text", text_path, bundle)
        if text_path.exists() and sha256_file(text_path) != text.get("sha256"):
            text_check["status"] = "error"
            text_check["message"] = f"text checksum mismatch for {entry['entry_id']}"
        if asset_check["status"] == "ok" and text_check["status"] == "ok":
            asset_count += 1
        checks.extend([asset_check, text_check])
    checks.append({"name": "yidtaknl_entry_exclusions", "actual": dict(sorted(exclusions.items())), "status": "ok"})
    checks.append(_yidtaknl_matched_pages_check(root, snapshot))
    return checks, candidate_count, asset_count


def _inspect_wikisource_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    try:
        root = wikisource_snapshot_root(source, bundle)
    except StageExecutionError as exc:
        return [{"name": "wikisource_snapshot_root", "status": "error", "message": str(exc)}], 0, 0
    snapshot_path = root / "snapshot.yaml"
    checks.append(_path_check("wikisource_snapshot", snapshot_path, bundle))
    if not snapshot_path.exists():
        return checks, 0, 0
    try:
        _, indexes, pages = load_wikisource_snapshot(root)
    except (OSError, ValueError, KeyError, ConfigValidationError) as exc:
        checks.append({"name": "wikisource_records", "path": _format_health_path(root, bundle), "status": "error", "message": str(exc)})
        return checks, 0, 0
    index_exclusions: dict[str, int] = {}
    admitted_indexes = 0
    for index in indexes.values():
        reasons = index_exclusion_reasons(index)
        if not reasons:
            admitted_indexes += 1
        for reason in reasons:
            index_exclusions[reason] = index_exclusions.get(reason, 0) + 1
    checks.append({"name": "wikisource_admitted_indexes", "actual": admitted_indexes, "status": "ok"})
    checks.append({"name": "wikisource_index_exclusions", "actual": dict(sorted(index_exclusions.items())), "status": "ok"})
    candidate_count = 0
    asset_count = 0
    page_exclusions: dict[str, int] = {}
    for page in pages:
        reasons = page_exclusion_reasons(page, indexes, root)
        integrity = [reason for reason in reasons if reason in WIKISOURCE_INTEGRITY_REASONS]
        if integrity:
            checks.append(
                {"name": "wikisource_page_text", "record_id": page.get("source_item_id"), "status": "error", "message": ", ".join(integrity)}
            )
        if reasons:
            page_exclusions[reasons[0]] = page_exclusions.get(reasons[0], 0) + 1
            continue
        candidate_count += 1
        image = page.get("image") or {}
        asset_path = (root / str(image.get("path", ""))).resolve()
        check = _path_check("wikisource_page_asset", asset_path, bundle)
        if asset_path.is_file() and image.get("sha256") and sha256_file(asset_path) != image["sha256"]:
            check["status"] = "error"
            check["message"] = f"checksum mismatch for {page['source_item_id']}"
        if check["status"] == "ok":
            asset_count += 1
        checks.append(check)
    checks.append({"name": "wikisource_page_exclusions", "actual": dict(sorted(page_exclusions.items())), "status": "ok"})
    return checks, candidate_count, asset_count


def _inspect_pinkas_dataset_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    try:
        root = pinkas_dataset_snapshot_root(source, bundle)
    except StageExecutionError as exc:
        return [{"name": "pinkas_dataset_snapshot_root", "status": "error", "message": str(exc)}], 0, 0
    snapshot_path = root / "snapshot.yaml"
    checks.append(_path_check("pinkas_dataset_snapshot", snapshot_path, bundle))
    if not snapshot_path.exists():
        return checks, 0, 0
    try:
        snapshot, entries = load_pinkas_dataset_snapshot(root)
    except (OSError, ValueError) as exc:
        checks.append({"name": "pinkas_dataset_entries", "path": _format_health_path(root, bundle), "status": "error", "message": str(exc)})
        return checks, 0, 0
    tag_check: dict[str, Any] = {"name": "pinkas_dataset_line_language_tags", "status": "ok"}
    try:
        tag_file = load_line_language_tags(root, snapshot)
    except StageExecutionError as exc:
        tag_file = None
        tag_check.update(status="error", message=str(exc))
    tag_pages: dict[str, tuple[str, list[Any]]] = {}
    scope_counts: dict[str, int] = {}
    candidate_count = 0
    asset_count = 0
    exclusions: dict[str, int] = {}
    for entry in entries:
        reason = pinkas_dataset_entry_exclusion_reason(entry, source, root)
        if reason is not None:
            exclusions[reason] = exclusions.get(reason, 0) + 1
            continue
        candidate_count += 1
        asset = pinkas_dataset_entry_asset(entry) or {}
        asset_path = (root / str(asset.get("local_path", ""))).resolve()
        asset_check = _path_check("pinkas_dataset_entry_asset", asset_path, bundle)
        if asset_path.exists() and asset.get("sha256") and sha256_file(asset_path) != asset["sha256"]:
            asset_check["status"] = "error"
            asset_check["message"] = f"checksum mismatch for {entry['entry_id']}"
        annotation_path = (root / str(entry["annotation"]["local_path"])).resolve()
        annotation_check = _path_check("pinkas_dataset_entry_page_xml", annotation_path, bundle)
        if annotation_path.exists():
            try:
                page = load_entry_page_lines(root, entry)
                annotation_check["actual"] = {"line_count": len(page.lines)}
                if len(page.lines) != entry["annotation"].get("line_count"):
                    annotation_check["status"] = "error"
                    annotation_check["message"] = f"line count mismatch for {entry['entry_id']}"
                tag_pages[entry["entry_id"]] = (entry["annotation"]["sha256"], page.lines)
                summary = page_scope_summary(load_entry_line_scopes(root, entry, tag_file, page))
                for scope, count in (
                    ("full_hebrew", summary["full_hebrew_line_count"]),
                    ("character_level_only", summary["character_level_only_line_count"]),
                    ("scope_neutral", summary["scope_neutral_line_count"]),
                ):
                    scope_counts[scope] = scope_counts.get(scope, 0) + count
            except (OSError, ValueError, StageExecutionError) as exc:
                annotation_check["status"] = "error"
                annotation_check["message"] = str(exc)
        if asset_check["status"] == "ok" and annotation_check["status"] == "ok":
            asset_count += 1
        checks.extend([asset_check, annotation_check])
    checks.append({"name": "pinkas_dataset_entry_exclusions", "actual": dict(sorted(exclusions.items())), "status": "ok"})
    if tag_file is not None:
        tag_counts: dict[str, int] = {}
        for page_tags in tag_file.pages:
            for tag in page_tags.lines:
                key = f"{tag.tag_source}:{tag.language}"
                tag_counts[key] = tag_counts.get(key, 0) + 1
        tag_check["actual"] = {"tags": dict(sorted(tag_counts.items())), "line_scopes": dict(sorted(scope_counts.items()))}
        unparsed = {str(entry.get("entry_id")) for entry in entries} - set(tag_pages)
        problems = tag_file_problems(tag_file, tag_pages, unparsed)
        if problems:
            tag_check.update(status="error", message="stale line language tags: " + "; ".join(problems))
    elif tag_check["status"] == "ok":
        tag_check["actual"] = {"tags": {}, "line_scopes": dict(sorted(scope_counts.items()))}
    checks.append(tag_check)
    return checks, candidate_count, asset_count


def _yidtaknl_matched_pages_check(root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Summarize metadata-only matched pages: never candidates, but their rights and pins must stay well formed."""

    try:
        pages = load_yidtaknl_matched_pages(root, snapshot)
    except (OSError, ValueError) as exc:
        return {"name": "yidtaknl_matched_pages", "status": "error", "message": str(exc)}
    works = {str(work.get("work_id")): work for work in snapshot.get("works") or [] if isinstance(work, dict)}
    by_work: dict[str, int] = {}
    problems: dict[str, int] = {}
    for page in pages:
        problem = yidtaknl_matched_page_problem(page, works, root)
        if problem is not None:
            problems[problem] = problems.get(problem, 0) + 1
            continue
        by_work[str(page["work_id"])] = by_work.get(str(page["work_id"]), 0) + 1
    check: dict[str, Any] = {
        "name": "yidtaknl_matched_pages",
        "actual": {"by_work": dict(sorted(by_work.items())), "problems": dict(sorted(problems.items()))},
        "status": "error" if problems else "ok",
    }
    if problems:
        check["message"] = "malformed metadata-only matched pages"
    return check


def _inspect_government_print_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    """F8e: Reshumot and Knesset committee snapshots; checks pins and reports exclusions by first reason."""

    prefix = source.fetcher
    exclusion_reasons = reshumot_entry_exclusion_reasons if source.fetcher == "reshumot" else knesset_entry_exclusion_reasons
    try:
        root = government_print_snapshot_root(source, bundle)
    except StageExecutionError as exc:
        return [{"name": f"{prefix}_snapshot_root", "status": "error", "message": str(exc)}], 0, 0
    snapshot_path = root / "snapshot.yaml"
    checks = [_path_check(f"{prefix}_snapshot", snapshot_path, bundle)]
    if not snapshot_path.exists():
        return checks, 0, 0
    try:
        _, entries = load_government_print_snapshot(root)
    except (OSError, ValueError) as exc:
        checks.append({"name": f"{prefix}_entries", "path": _format_health_path(root, bundle), "status": "error", "message": str(exc)})
        return checks, 0, 0
    candidate_count = 0
    asset_count = 0
    exclusions: dict[str, int] = {}
    for entry in entries:
        reasons = exclusion_reasons(entry, source, root)
        integrity = [reason for reason in reasons if reason in GOVERNMENT_PRINT_INTEGRITY_REASONS]
        if integrity:
            checks.append({"name": f"{prefix}_entry_text", "record_id": entry.get("entry_id"), "status": "error", "message": ", ".join(integrity)})
        if reasons:
            exclusions[reasons[0]] = exclusions.get(reasons[0], 0) + 1
            continue
        candidate_count += 1
        asset = government_print_entry_asset(entry) or {}
        asset_path = (root / str(asset.get("local_path", ""))).resolve()
        check = _path_check(f"{prefix}_entry_asset", asset_path, bundle)
        if asset_path.is_file() and sha256_file(asset_path) != asset.get("sha256"):
            check["status"] = "error"
            check["message"] = f"checksum mismatch for {entry['entry_id']}"
        if check["status"] == "ok":
            asset_count += 1
        checks.append(check)
    checks.append({"name": f"{prefix}_entry_exclusions", "actual": dict(sorted(exclusions.items())), "status": "ok"})
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
    configured_count = source.settings.extra.get(F1_TARGET_SCALE_COUNT_KEY)
    checks.append(
        {
            "actual": configured_count,
            "expected": "positive integer",
            "name": F1_TARGET_SCALE_COUNT_KEY,
            "status": "ok" if isinstance(configured_count, int) and configured_count > 0 else "error",
        }
    )
    return checks, source.settings.synthetic_batch_size or 0, asset_count


def _inspect_hocrsyngen_manifest_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int, dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    batch_reference = source.settings.hocrsyngen_batch_path
    if not batch_reference:
        return (
            [
                {
                    "message": "settings.hocrsyngen_batch_path is required",
                    "name": "hocrsyngen_batch_path",
                    "status": "error",
                }
            ],
            0,
            0,
            {},
        )
    batch_dir = bundle.resolve_path(batch_reference)
    manifest_path = batch_dir / "generation_manifest.json"
    checks.append(_path_check("hocrsyngen_batch_path", batch_dir, bundle))
    checks.append(_path_check("hocrsyngen_generation_manifest", manifest_path, bundle))
    try:
        batch = validate_hocrsyngen_batch(batch_dir)
    except (ConfigValidationError, OSError, StageExecutionError) as exc:
        checks.append(
            {
                "message": str(exc),
                "name": "hocrsyngen_generation_manifest_v1",
                "path": _format_health_path(manifest_path, bundle),
                "status": "error",
            }
        )
        return checks, 0, 0, {}

    for sample in batch.manifest.samples:
        for page in sample.pages:
            checks.append(_path_check("hocrsyngen_page_asset", batch.batch_dir / page.asset_path, bundle))
    coverage_counts = _hocrsyngen_coverage_counts(batch)
    layout_families = sorted({sample.rendering_metadata.layout_family for sample in batch.manifest.samples})
    provider_version = batch.manifest.provider_metadata.provider_version
    coverage_warnings = [
        label
        for key, label in {
            "has_mixed_ltr": "no mixed LTR coverage in hocrsyngen batch",
            "has_niqqud": "no niqqud coverage in hocrsyngen batch",
        }.items()
        if coverage_counts.get(key, 0) == 0
    ]
    checks.append(
        {
            "actual": batch.sample_count,
            "expected": "validated hocrsyngen samples",
            "name": "hocrsyngen_sample_count",
            "status": "ok",
        }
    )
    checks.append(
        {
            "actual": provider_version,
            "expected": "non-empty hocrsyngen provider version",
            "name": "hocrsyngen_provider_version",
            "status": "ok",
        }
    )
    for key, label in {
        "has_arabic_numerals": "Arabic numeral",
        "has_final_letters": "Hebrew final-letter",
        "has_hebrew_letters": "Hebrew letter",
        "has_punctuation": "punctuation",
    }.items():
        checks.append(
            {
                "actual": coverage_counts.get(key, 0),
                "expected": f"at least one sample with {label} coverage",
                "name": f"hocrsyngen_coverage_{key}",
                "status": "ok" if coverage_counts.get(key, 0) > 0 else "error",
            }
        )
    checks.append(
        {
            "actual": batch.page_count,
            "expected": "validated hocrsyngen page assets",
            "name": "hocrsyngen_page_count",
            "status": "ok",
        }
    )
    return checks, batch.sample_count, batch.page_count, {
        "hocrsyngen_coverage_counts": coverage_counts,
        "hocrsyngen_coverage_warnings": coverage_warnings,
        "hocrsyngen_layout_families": layout_families,
        "hocrsyngen_provider_version": provider_version,
    }


def _hocrsyngen_coverage_counts(batch: Any) -> dict[str, int]:
    counts = {
        "has_arabic_numerals": 0,
        "has_final_letters": 0,
        "has_hebrew_letters": 0,
        "has_mixed_ltr": 0,
        "has_niqqud": 0,
        "has_punctuation": 0,
    }
    for sample in batch.manifest.samples:
        coverage = sample.hebrew_coverage.model_dump()
        for key in counts:
            if coverage[key]:
                counts[key] += 1
    return counts


def _inspect_modern_handwriting_source(source: SourceConfig, bundle: ConfigBundle) -> tuple[list[dict[str, Any]], int, int]:
    checks: list[dict[str, Any]] = []
    manifest_reference = source.settings.modern_intake_manifest
    if not manifest_reference:
        return (
            [
                {
                    "message": "settings.modern_intake_manifest is required",
                    "name": "modern_intake_manifest",
                    "status": "error",
                }
            ],
            0,
            0,
        )
    manifest_path = bundle.resolve_path(manifest_reference)
    checks.append(_path_check("modern_intake_manifest", manifest_path, bundle))
    try:
        batch = validate_modern_intake_manifest(source, bundle)
    except (ConfigValidationError, OSError, StageExecutionError) as exc:
        checks.append(
            {
                "message": str(exc),
                "name": "modern_intake_manifest_v1",
                "path": _format_health_path(manifest_path, bundle),
                "status": "error",
            }
        )
        return checks, 0, 0
    for record in batch.manifest.records:
        checks.append(_path_check("modern_intake_asset", batch.manifest_path.parent / record.asset_path, bundle))
    checks.append(
        {
            "actual": batch.candidate_count,
            "expected": "validated modern handwriting intake records",
            "name": "modern_intake_candidate_count",
            "status": "ok",
        }
    )
    checks.append(
        {
            "actual": batch.asset_count,
            "expected": "validated modern handwriting intake assets",
            "name": "modern_intake_asset_count",
            "status": "ok",
        }
    )
    return checks, batch.candidate_count, batch.asset_count


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
