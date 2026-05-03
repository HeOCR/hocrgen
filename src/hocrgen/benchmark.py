from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from hocrgen.config.loader import package_root, load_json_file
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    BenchmarkConfigRecord,
    BenchmarkItemRecord,
    BenchmarkLeakagePolicyRecord,
    BenchmarkLeakageResolutionRecord,
    BenchmarkSelectionAuditRecord,
    CuratedItemRecord,
    PrivacyScannedItemRecord,
)


BENCHMARK_ID = "benchmark_v1"


@dataclass(frozen=True)
class BenchmarkSelectionOutputs:
    config: BenchmarkConfigRecord
    items: list[BenchmarkItemRecord]
    audit: list[BenchmarkSelectionAuditRecord]
    stability_policy: dict[str, object]
    card_markdown: str


def _benchmark_data_root_candidates(config_root: Path) -> list[Path]:
    config_root = config_root.resolve()
    candidates: list[Path] = []
    project_root = _project_root_for(config_root)
    if project_root is None:
        search_roots = (config_root, config_root.parent)
    else:
        search_roots = [config_root]
        for parent in config_root.parents:
            search_roots.append(parent)
            if parent == project_root:
                break
    for parent in search_roots:
        candidate = parent / "benchmark_data"
        if candidate not in candidates:
            candidates.append(candidate)
    package_candidate = packaged_benchmark_data_root()
    if package_candidate not in candidates:
        candidates.append(package_candidate)
    return candidates


def packaged_benchmark_data_root() -> Path:
    return (package_root() / "data" / "benchmark").resolve()


def _project_root_for(path: Path) -> Path | None:
    for parent in (path, *path.parents):
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists():
            return parent
    return None


def resolve_benchmark_data_root(config_root: Path, benchmark_id: str = BENCHMARK_ID) -> Path:
    for candidate in _benchmark_data_root_candidates(config_root):
        if (candidate / benchmark_id / "config.json").exists():
            return candidate
    return config_root.resolve().parent / "benchmark_data"


def load_benchmark_config(config_root: Path, benchmark_id: str = BENCHMARK_ID) -> BenchmarkConfigRecord:
    root = resolve_benchmark_data_root(config_root, benchmark_id)
    config_path = root / benchmark_id / "config.json"
    try:
        config = BenchmarkConfigRecord.model_validate(load_json_file(config_path))
    except ValidationError as exc:
        raise ConfigValidationError(f"benchmark config validation failed for {config_path}", details=exc.errors()) from exc
    if config.benchmark_id != benchmark_id:
        raise ConfigValidationError(
            f"benchmark config id mismatch for {config_path}",
            details=[{"expected": benchmark_id, "actual": config.benchmark_id}],
        )
    return config


def select_benchmark_items(
    *,
    config: BenchmarkConfigRecord,
    release_ready_items: list[PrivacyScannedItemRecord],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    removed_duplicate_items: list[CuratedItemRecord],
) -> BenchmarkSelectionOutputs:
    release_ready_by_id = {item.item_id: item for item in release_ready_items}
    review_required_ids = {item.item_id for item in review_required_items}
    blocked_ids = {item.item_id for item in blocked_items}
    duplicate_removed_ids = {item.item_id for item in removed_duplicate_items}

    selected: list[BenchmarkItemRecord] = []
    audit: list[BenchmarkSelectionAuditRecord] = []
    for approved in config.approved_items:
        item = release_ready_by_id.get(approved.item_id)
        if item is None:
            reason = _missing_benchmark_item_reason(
                approved.item_id,
                review_required_ids,
                blocked_ids,
                duplicate_removed_ids,
            )
            raise StageExecutionError(
                f"benchmark {config.benchmark_id} approved item {approved.item_id} is not release-ready: {reason}"
            )
        if item.split is None or item.split_group_id is None:
            raise StageExecutionError(
                f"benchmark {config.benchmark_id} approved item {approved.item_id} is missing a split assignment"
            )
        if item.split != approved.benchmark_split:
            raise StageExecutionError(
                f"benchmark {config.benchmark_id} approved item {approved.item_id} split changed: "
                f"expected {approved.benchmark_split}, got {item.split}"
            )

        selected.append(
            BenchmarkItemRecord(
                benchmark_id=config.benchmark_id,
                item_id=item.item_id,
                source_id=item.source_id,
                source_item_id=item.source_item_id,
                source_url=item.source_url,
                title=item.title,
                benchmark_split=approved.benchmark_split,
                release_split=item.split,
                split_group_id=item.split_group_id,
                is_synthetic=item.is_synthetic,
                content_class=item.content_class,
                quality_tier=item.quality_tier,
                normalized_license=item.normalized_license,
                rights_classification=item.rights_classification,
                rationale=approved.rationale,
            )
        )
        audit.append(
            BenchmarkSelectionAuditRecord(
                benchmark_id=config.benchmark_id,
                item_id=item.item_id,
                outcome="selected",
                reason="explicitly_approved_release_ready_item",
                review_bar=config.review_bar,
            )
        )

    selected.sort(key=lambda item: (item.benchmark_split, item.source_id, item.item_id))
    audit.sort(key=lambda item: item.item_id)
    stability_policy = {
        "benchmark_id": config.benchmark_id,
        "version": config.version,
        "description": config.description,
        "selection_policy": config.selection_policy,
        "review_bar": config.review_bar,
        "stability_policy": config.stability_policy,
        "schema_version": 1,
    }
    return BenchmarkSelectionOutputs(
        config=config,
        items=selected,
        audit=audit,
        stability_policy=stability_policy,
        card_markdown=render_benchmark_card(config, selected),
    )


def benchmark_holdout_leakage_artifact(
    *,
    benchmark_items: list[BenchmarkItemRecord],
    release_ready_items: list[PrivacyScannedItemRecord],
    removed_duplicate_items: list[CuratedItemRecord],
    policy: BenchmarkLeakagePolicyRecord,
) -> dict[str, object]:
    benchmark_ids = {item.item_id for item in benchmark_items}
    benchmark_splits = {
        item.item_id: item.split
        for item in release_ready_items
        if item.item_id in benchmark_ids and item.split is not None
    }
    candidate_items = sorted(
        [*release_ready_items, *removed_duplicate_items],
        key=lambda item: item.item_id,
    )

    groups: dict[tuple[str, str], set[str]] = {}
    for item in candidate_items:
        if item.dedupe_cluster_id:
            groups.setdefault(("exact_duplicate", item.dedupe_cluster_id), set()).add(item.item_id)
        if item.near_duplicate_cluster_id:
            groups.setdefault(("near_duplicate", item.near_duplicate_cluster_id), set()).add(item.item_id)
        if item.source_group_id:
            groups.setdefault(("source_group", item.source_group_id), set()).add(item.item_id)

    resolutions = {
        (resolution.group_kind, resolution.group_id): resolution
        for resolution in policy.accepted_resolutions
    }
    risks: list[dict[str, object]] = []
    resolved_risks: list[dict[str, object]] = []
    unresolved_risks: list[dict[str, object]] = []
    stale_resolutions: list[dict[str, object]] = []
    matched_resolution_ids: set[str] = set()
    for (group_kind, group_id), member_ids in sorted(groups.items()):
        benchmark_members = sorted(member_ids & benchmark_ids)
        non_benchmark_members = sorted(member_ids - benchmark_ids)
        if not benchmark_members or not non_benchmark_members:
            continue
        risk = {
            "benchmark_item_ids": benchmark_members,
            "group_id": group_id,
            "group_kind": group_kind,
            "non_benchmark_item_ids": non_benchmark_members,
            "holdout_item_ids": non_benchmark_members,
            "splits": sorted(
                {
                    split
                    for item_id, split in benchmark_splits.items()
                    if item_id in benchmark_members and split
                }
            ),
        }
        resolution = resolutions.get((group_kind, group_id))
        if resolution is not None and _resolution_matches_risk(resolution, risk):
            matched_resolution_ids.add(resolution.resolution_id)
            resolved = {
                **risk,
                "resolution": resolution.model_dump(mode="json"),
                "resolution_status": "accepted",
            }
            risks.append(resolved)
            resolved_risks.append(resolved)
            continue
        if resolution is not None:
            stale_resolutions.append(
                {
                    "benchmark_item_ids": benchmark_members,
                    "expected_benchmark_item_ids": resolution.benchmark_item_ids,
                    "expected_non_benchmark_item_ids": resolution.non_benchmark_item_ids,
                    "group_id": group_id,
                    "group_kind": group_kind,
                    "non_benchmark_item_ids": non_benchmark_members,
                    "resolution_id": resolution.resolution_id,
                    "status": "stale",
                }
            )
        unresolved = {**risk, "resolution_status": "unresolved"}
        risks.append(unresolved)
        unresolved_risks.append(unresolved)

    unused_resolutions = [
        resolution.model_dump(mode="json")
        for resolution in policy.accepted_resolutions
        if resolution.resolution_id not in matched_resolution_ids
        and (resolution.group_kind, resolution.group_id) not in {
            (stale["group_kind"], stale["group_id"]) for stale in stale_resolutions
        }
    ]
    status = "ok" if not unresolved_risks and not stale_resolutions else "blocked"
    return {
        "accepted_resolution_count": len(resolved_risks),
        "policy": policy.model_dump(mode="json"),
        "risk_count": len(risks),
        "risks": risks,
        "resolved_risks": resolved_risks,
        "stale_resolutions": stale_resolutions,
        "status": status,
        "unresolved_count": len(unresolved_risks),
        "unresolved_risks": unresolved_risks,
        "unused_resolutions": unused_resolutions,
    }


def _resolution_matches_risk(
    resolution: BenchmarkLeakageResolutionRecord,
    risk: dict[str, object],
) -> bool:
    return (
        resolution.benchmark_item_ids == risk["benchmark_item_ids"]
        and resolution.non_benchmark_item_ids == risk["non_benchmark_item_ids"]
    )


def _missing_benchmark_item_reason(
    item_id: str,
    review_required_ids: set[str],
    blocked_ids: set[str],
    duplicate_removed_ids: set[str],
) -> str:
    if item_id in review_required_ids:
        return "review_required"
    if item_id in blocked_ids:
        return "blocked"
    if item_id in duplicate_removed_ids:
        return "duplicate_removed"
    return "missing_from_current_run"


def render_benchmark_card(config: BenchmarkConfigRecord, items: list[BenchmarkItemRecord]) -> str:
    real_count = sum(1 for item in items if not item.is_synthetic)
    synthetic_count = sum(1 for item in items if item.is_synthetic)
    split_counts: dict[str, int] = {}
    for item in items:
        split_counts[item.benchmark_split] = split_counts.get(item.benchmark_split, 0) + 1

    lines = [
        f"# Benchmark Card: {config.benchmark_id}",
        "",
        "## Summary",
        config.description,
        "",
        "## Selection Policy",
        config.selection_policy,
        "",
        "## Review Bar",
        config.review_bar,
        "",
        "## Stability Policy",
    ]
    lines.extend(f"- {key}: {value}" for key, value in sorted(config.stability_policy.items()))
    lines.extend(
        [
            "",
            "## Composition",
            f"- Items: {len(items)}",
            f"- Real items: {real_count}",
            f"- Synthetic control items: {synthetic_count}",
            "",
            "## Benchmark Splits",
        ]
    )
    lines.extend(f"- `{split}`: {count}" for split, count in sorted(split_counts.items()))
    lines.extend(["", "## Items"])
    lines.extend(
        f"- `{item.item_id}` ({item.source_id}, `{item.benchmark_split}`): {item.rationale}"
        for item in items
    )
    return "\n".join(lines + [""])
