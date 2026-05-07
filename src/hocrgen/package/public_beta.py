from __future__ import annotations

import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hocrgen.annotations import build_annotation_manifest
from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import PublicBetaGovernanceConfig, ReleaseProfile
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.io import write_json
from hocrgen.manifests.models import (
    CuratedItemRecord,
    DuplicateClusterRecord,
    DuplicateRelationRecord,
    PrivacyScannedItemRecord,
    PublicBetaReleaseRecord,
    ReviewQueueRecord,
    SplitAssignmentRecord,
)
from hocrgen.package.common import (
    REPO_ROOT,
    ReleaseDocs,
    StandardReleaseArtifacts,
    audit_item_payload_for_export,
    benchmark_card_for_export,
    build_checksum_manifest,
    build_classification_stats,
    build_privacy_stats,
    build_release_diff,
    build_source_stats,
    changelog_doc,
    copy_benchmark_reference_files,
    copy_export_assets,
    current_commit_sha,
    filter_annotation_pilot_manifest,
    filter_benchmark_leakage_risk,
    filter_benchmark_reference_manifest,
    filter_benchmark_reference_status,
    load_annotation_pilot_export_inputs,
    load_benchmark_export_inputs,
    load_json,
    load_models,
    ordered_sources,
    source_snapshot_lines,
    split_sort_key,
    synthetic_composition_lines,
    validate_release_diff_baseline,
    verify_checksum_manifest,
    write_release_archive,
    write_standard_release_artifacts,
)
from hocrgen.source_ops import F1_SYNTHETIC_TARGET_COUNT
from hocrgen.synthetic.reporting import synthetic_composition_report


@dataclass(frozen=True)
class PublicBetaExportConfig:
    version: str
    output_dir: Path | None = None
    compare_to: Path | None = None
    overwrite: bool = False


@dataclass(frozen=True)
class PublicBetaExportResult:
    export_dir: Path
    summary_path: Path
    release_record_path: Path
    item_manifest_path: Path
    readiness_report_path: Path
    blocker_closure_plan_path: Path
    checksum_manifest_path: Path
    archive_manifest_path: Path
    artifact_paths: list[Path]
    readiness_status: str
    publication_allowed: bool


FINAL_ARCHIVE_EXCLUDED_PATHS = {
    "archives/",
    "manifests/archive_manifest.json",
    "manifests/checksum_manifest.json",
}

PUBLIC_BETA_REQUIRED_DOCS = {
    "docs/DATASET_CARD.md": ["## Scope", "## Synthetic Composition", "## Known Blockers", "## Takedown and Corrections"],
    "docs/PROVENANCE.md": ["## Source Snapshot", "Publication targets: none"],
    "docs/CHANGELOG.md": ["# Changelog"],
    "docs/RELEASE_NOTES.md": ["## Publication Status", "## Takedown and Corrections"],
    "docs/BENCHMARK_CARD.md": ["# Benchmark"],
    "docs/HANDOFF.md": ["## Stop Conditions", "Do not publish to HeOCR"],
}

BLOCKER_CLOSURE_ACTIONS = {
    "source_depth_composition": {
        "category": "external_input_dependent",
        "owner_scope": "external synthetic-provider input plus repo validation",
        "closure_state": "requires_external_input",
        "required_action": (
            "Rerun public beta packaging after the hocrsyngen target-scale batch is available; do not count "
            "operator-only source-depth fixtures as public payload evidence unless they are promoted through "
            "normal release-profile, review, privacy, split, benchmark, and portability gates."
        ),
        "closure_artifacts": [
            "manifests/source_depth_feasibility.json",
            "manifests/source_stats.json",
            "docs/DATASET_CARD.md",
        ],
    },
    "synthetic_target_scale": {
        "category": "external_input_dependent",
        "owner_scope": "external hocrsyngen batch production",
        "closure_state": "requires_external_input",
        "required_action": (
            "Produce, configure, and validate a larger hocrsyngen batch for the 80 synthetic-control target; "
            "keep the current 2 / 80 evidence blocked until that batch exists."
        ),
        "closure_artifacts": [
            "manifests/source_depth_feasibility.json",
            "manifests/source_health.json",
            "manifests/synthetic_composition.json",
        ],
    },
    "privacy_review": {
        "category": "repo_owned_immediately_actionable",
        "owner_scope": "hocrgen review/privacy configuration and operator decisions",
        "closure_state": "requires_repo_pr_or_review_update",
        "required_action": (
            "Resolve or explicitly exclude review-required, blocked, unresolved privacy, consent, and takedown "
            "states through repo-tracked review/config/source-status changes before claiming public beta readiness."
        ),
        "closure_artifacts": [
            "manifests/privacy_stats.json",
            "manifests/review_required_items.json",
            "manifests/blocked_items.json",
            "manifests/review_queue.json",
        ],
    },
    "benchmark_references": {
        "category": "repo_owned_immediately_actionable",
        "owner_scope": "hocrgen benchmark-reference data and disclosure docs",
        "closure_state": "requires_repo_pr_or_reference_update",
        "required_action": (
            "Finalize benchmark-reference status/versioning artifacts or keep the limitation disclosed; public beta "
            "readiness stays blocked while references are draft, unavailable, blocked, or versioning-incoherent."
        ),
        "closure_artifacts": [
            "manifests/benchmark_reference_manifest.json",
            "manifests/benchmark_reference_status.json",
            "manifests/benchmark_reference_versioning.json",
            "docs/BENCHMARK_CARD.md",
        ],
    },
}


def export_public_beta_release(
    bundle: ConfigBundle,
    run_dir: Path,
    profile_id: str,
    config: PublicBetaExportConfig,
) -> PublicBetaExportResult:
    profile = bundle.profiles[profile_id]
    build_dir = run_dir / "build_release"
    discover_dir = run_dir / "discover"
    export_dir = (run_dir.parent.parent / "exports" / config.version).resolve()
    if config.output_dir:
        export_dir = config.output_dir.resolve()
    if export_dir.name != config.version:
        raise StageExecutionError(
            f"public beta export output directory must be named {config.version} to match the archive root: {export_dir}"
        )
    if export_dir.exists():
        if not config.overwrite:
            raise StageExecutionError(f"public beta export directory already exists: {export_dir}")
        _validate_public_beta_overwrite_target(export_dir, config.version)

    release_items = load_models(build_dir / "item_manifest.json", PrivacyScannedItemRecord)
    review_required_items = load_models(build_dir / "review_required_items.json", PrivacyScannedItemRecord)
    blocked_items = load_models(build_dir / "blocked_items.json", PrivacyScannedItemRecord)
    split_manifest = load_models(build_dir / "split_manifest.json", SplitAssignmentRecord)
    duplicate_relations = load_models(build_dir / "duplicate_relations.json", DuplicateRelationRecord)
    duplicate_clusters = load_models(build_dir / "duplicate_clusters.json", DuplicateClusterRecord)
    removed_duplicate_items = load_models(build_dir / "removed_duplicate_items.json", CuratedItemRecord)
    review_queue = load_models(build_dir / "review_queue.json", ReviewQueueRecord)
    benchmark_inputs = load_benchmark_export_inputs(build_dir)
    annotation_pilot_inputs = load_annotation_pilot_export_inputs(build_dir)
    build_release_summary = load_json(build_dir / "release_summary.json")
    leakage_report = load_json(build_dir / "leakage_report.json")
    source_depth_feasibility = load_json(discover_dir / "source_depth_feasibility.json")
    source_health = load_json(discover_dir / "source_health.json")

    if not release_items:
        raise StageExecutionError("public beta packaging selection is empty")

    if export_dir.exists():
        shutil.rmtree(export_dir)
    exported_items = copy_export_assets(release_items, export_dir / "data")
    selected_ids = {item.item_id for item in exported_items}
    selected_benchmark_items = [item for item in benchmark_inputs.items if item.item_id in selected_ids]
    selected_benchmark_ids = {item.item_id for item in selected_benchmark_items}
    selected_benchmark_audit = [
        item for item in benchmark_inputs.selection_audit if item.item_id in selected_benchmark_ids
    ]
    selected_benchmark_reference_manifest = filter_benchmark_reference_manifest(
        benchmark_inputs.reference_manifest,
        selected_ids,
    )
    selected_benchmark_reference_status = filter_benchmark_reference_status(
        benchmark_inputs.reference_status,
        selected_ids,
    )
    selected_benchmark_leakage_risk = filter_benchmark_leakage_risk(
        benchmark_inputs.leakage_risk,
        selected_ids,
    )
    exported_benchmark_reference_files = copy_benchmark_reference_files(
        selected_benchmark_reference_manifest,
        build_dir,
        export_dir,
    )

    included_sources = ordered_sources(profile, {item.source_id for item in exported_items})
    selected_split_manifest = [assignment for assignment in split_manifest if assignment.item_id in selected_ids]
    review_required_ids = {item.item_id for item in review_required_items}
    selected_review_queue = [entry for entry in review_queue if entry.item_id in review_required_ids]
    selected_duplicate_relations = [
        relation
        for relation in duplicate_relations
        if relation.canonical_item_id in selected_ids and relation.duplicate_item_id in selected_ids
    ]
    selected_duplicate_cluster_ids = {relation.cluster_id for relation in selected_duplicate_relations}
    selected_duplicate_clusters = [
        cluster for cluster in duplicate_clusters if cluster.cluster_id in selected_duplicate_cluster_ids
    ]
    source_stats = build_source_stats(exported_items, selected_duplicate_relations)
    classification_stats = build_classification_stats(exported_items)
    privacy_stats = build_privacy_stats(exported_items)
    synthetic_composition = synthetic_composition_report(exported_items)
    annotation_manifest = build_annotation_manifest(exported_items, subset_id="public_beta")
    exported_annotation_pilot_manifest = filter_annotation_pilot_manifest(annotation_pilot_inputs.manifest, selected_ids)
    selected_annotation_pilot_ids = {item.item_id for item in exported_annotation_pilot_manifest.items}
    selected_annotation_pilot_audit = [
        item for item in annotation_pilot_inputs.selection_audit if item.item_id in selected_annotation_pilot_ids
    ]
    split_counts = dict(Counter(item.split for item in exported_items if item.split))
    exported_real_items = sum(1 for item in exported_items if not item.is_synthetic)
    exported_synthetic_items = sum(1 for item in exported_items if item.is_synthetic)
    exported_at = datetime.now(UTC).isoformat()
    commit_sha = current_commit_sha()
    initial_release_record = PublicBetaReleaseRecord(
        version=config.version,
        profile_id=profile_id,
        included_sources=included_sources,
        split_counts=split_counts,
        real_items=exported_real_items,
        synthetic_items=exported_synthetic_items,
        review_required_count=len(review_required_items),
        blocked_count=len(blocked_items),
        readiness_status="blocked",
        publication_allowed=False,
        hocrgen_commit=commit_sha,
        exported_at=exported_at,
    )
    release_summary = {
        "blocked_count": len(blocked_items),
        "dataset_id": "HeOCR",
        "exported_item_count": len(exported_items),
        "exported_real_items": exported_real_items,
        "exported_synthetic_items": exported_synthetic_items,
        "is_dry_run": build_release_summary["is_dry_run"],
        "profile_id": profile_id,
        "real_items": exported_real_items,
        "release_kind": "public_beta",
        "release_ready_count": build_release_summary["release_ready_count"],
        "review_required_count": len(review_required_items),
        "split_counts": split_counts,
        "synthetic_items": exported_synthetic_items,
        "synthetic_composition": synthetic_composition,
        "annotation_manifest": {
            "annotated_item_count": annotation_manifest.annotated_item_count,
            "transcription_item_count": annotation_manifest.transcription_item_count,
            "layout_label_item_count": annotation_manifest.layout_label_item_count,
            "transcription_required": annotation_manifest.transcription_required,
            "layout_labels_required": annotation_manifest.layout_labels_required,
        },
        "annotation_pilot": {
            "pilot_id": exported_annotation_pilot_manifest.pilot_id,
            "pilot_item_count": exported_annotation_pilot_manifest.pilot_item_count,
            "transcription_task_count": exported_annotation_pilot_manifest.transcription_task_count,
            "layout_label_task_count": exported_annotation_pilot_manifest.layout_label_task_count,
            "transcription_required_for_release": exported_annotation_pilot_manifest.transcription_required_for_release,
            "layout_labels_required_for_release": exported_annotation_pilot_manifest.layout_labels_required_for_release,
        },
        "benchmark_references": {
            "reference_manifest_id": (
                selected_benchmark_reference_manifest.reference_manifest_id
                if selected_benchmark_reference_manifest is not None
                else None
            ),
            "reference_ready_count": (
                selected_benchmark_reference_status.counts.get("reference_ready", 0)
                if selected_benchmark_reference_status is not None
                else 0
            ),
            "draft_or_blocked_count": (
                selected_benchmark_reference_status.counts.get("blocked_or_draft", 0)
                if selected_benchmark_reference_status is not None
                else 0
            ),
            "versioning_status": (
                benchmark_inputs.reference_versioning or {}
            ).get("status", "not_available"),
        },
        "version": config.version,
    }
    baseline_dir = _resolve_comparison_release(export_dir, config)
    release_diff = build_release_diff(
        version=config.version,
        generated_at=exported_at,
        current_items=exported_items,
        baseline_dir=baseline_dir,
        review_required_items=review_required_items,
        blocked_items=blocked_items,
        removed_duplicate_items=removed_duplicate_items,
        build_release_items=release_items,
    )
    benchmark_card = benchmark_card_for_export(benchmark_inputs, selected_benchmark_items)
    summary_path, artifact_paths = write_standard_release_artifacts(
        StandardReleaseArtifacts(
            export_dir=export_dir,
            run_dir=run_dir,
            summary_subdir="export_public_beta",
            summary_payload={
                "archive_manifest": "manifests/archive_manifest.json",
                "blocker_closure_plan": "manifests/public_beta_blocker_closure_plan.json",
                "checksum_manifest": "manifests/checksum_manifest.json",
                "dataset_id": "HeOCR",
                "export_dir": str(export_dir),
                "item_manifest": "manifests/item_manifest.json",
                "publication_report": None,
                "readiness_report": "manifests/public_beta_readiness_report.json",
                "release_diff": "manifests/release_diff.json",
                "release_record": "manifests/release_record.json",
                "release_summary": "manifests/release_summary.json",
                "stage": "export-public-beta",
                "version": config.version,
            },
            exported_items=exported_items,
            selected_split_manifest=selected_split_manifest,
            source_stats=source_stats,
            synthetic_composition=synthetic_composition,
            annotation_manifest=annotation_manifest,
            exported_annotation_pilot_manifest=exported_annotation_pilot_manifest,
            selected_annotation_pilot_audit=selected_annotation_pilot_audit,
            classification_stats=classification_stats,
            privacy_stats=privacy_stats,
            release_summary=release_summary,
            selected_duplicate_relations=selected_duplicate_relations,
            selected_duplicate_clusters=selected_duplicate_clusters,
            review_required_items=review_required_items,
            blocked_items=blocked_items,
            selected_review_queue=selected_review_queue,
            release_record=initial_release_record,
            release_diff=release_diff,
            selected_benchmark_items=selected_benchmark_items,
            selected_benchmark_leakage_risk=selected_benchmark_leakage_risk,
            selected_benchmark_audit=selected_benchmark_audit,
            benchmark_stability_policy=benchmark_inputs.stability_policy,
            selected_benchmark_reference_manifest=selected_benchmark_reference_manifest,
            selected_benchmark_reference_status=selected_benchmark_reference_status,
            benchmark_reference_versioning=benchmark_inputs.reference_versioning,
            exported_benchmark_reference_files=exported_benchmark_reference_files,
            docs=ReleaseDocs(
                dataset_card=_dataset_card(
                    config.version,
                    profile,
                    exported_items,
                    review_required_items,
                    blocked_items,
                    included_sources,
                    bundle.public_beta_governance,
                ),
                release_notes=_release_notes(
                    config.version,
                    release_summary,
                    source_stats,
                    included_sources,
                    release_diff,
                    bundle.public_beta_governance,
                ),
                changelog=changelog_doc(config.version, release_diff),
                provenance=_provenance_doc(bundle, profile, included_sources, exported_at, commit_sha),
                handoff=_handoff_doc(
                    config.version,
                    profile,
                    release_summary,
                    included_sources,
                    commit_sha,
                    bundle.public_beta_governance,
                ),
                benchmark_card=benchmark_card,
            ),
            audit_item_payload=audit_item_payload_for_export,
        )
    )

    manifests_dir = export_dir / "manifests"
    write_json(manifests_dir / "source_depth_feasibility.json", source_depth_feasibility)
    write_json(manifests_dir / "source_health.json", source_health)
    docs_validation = _validate_public_beta_docs(export_dir)
    takedown_validation = _validate_takedown_workflow(export_dir, bundle.public_beta_governance)

    bootstrap_archive_manifest = {
        "schema_version": 1,
        "archives": [],
        "excluded_paths": sorted(FINAL_ARCHIVE_EXCLUDED_PATHS),
    }
    bootstrap_verification = {
        "checked_count": 0,
        "failure_count": 1,
        "failures": [{"path": "archives", "reason": "archive_not_finalized"}],
        "status": "blocked",
    }
    readiness_report = _readiness_report(
        version=config.version,
        profile_id=profile_id,
        release_summary=release_summary,
        build_release_summary=build_release_summary,
        source_depth_feasibility=source_depth_feasibility,
        leakage_report=leakage_report,
        selected_benchmark_reference_status=selected_benchmark_reference_status,
        benchmark_reference_versioning=benchmark_inputs.reference_versioning,
        checksum_verification=bootstrap_verification,
        archive_manifest=bootstrap_archive_manifest,
        docs_validation=docs_validation,
        takedown_validation=takedown_validation,
    )
    _write_readiness_outputs(
        manifests_dir=manifests_dir,
        release_record=initial_release_record,
        release_summary=release_summary,
        readiness_report=readiness_report,
    )
    archive_record = write_release_archive(
        release_root=export_dir,
        version=config.version,
        exclude_paths=FINAL_ARCHIVE_EXCLUDED_PATHS,
    )
    archive_manifest = {
        "schema_version": 1,
        "archives": [archive_record],
        "excluded_paths": sorted(FINAL_ARCHIVE_EXCLUDED_PATHS),
    }
    write_json(manifests_dir / "archive_manifest.json", archive_manifest)
    checksum_manifest = build_checksum_manifest(release_root=export_dir, archive_records=[archive_record])
    verification = verify_checksum_manifest(export_dir, checksum_manifest)
    checksum_manifest["verification"] = verification
    write_json(manifests_dir / "checksum_manifest.json", checksum_manifest)
    readiness_report = _readiness_report(
        version=config.version,
        profile_id=profile_id,
        release_summary=release_summary,
        build_release_summary=build_release_summary,
        source_depth_feasibility=source_depth_feasibility,
        leakage_report=leakage_report,
        selected_benchmark_reference_status=selected_benchmark_reference_status,
        benchmark_reference_versioning=benchmark_inputs.reference_versioning,
        checksum_verification=verification,
        archive_manifest=archive_manifest,
        docs_validation=docs_validation,
        takedown_validation=takedown_validation,
    )
    _write_readiness_outputs(
        manifests_dir=manifests_dir,
        release_record=initial_release_record,
        release_summary=release_summary,
        readiness_report=readiness_report,
    )
    blocker_closure_plan = _blocker_closure_plan(
        readiness_report=readiness_report,
        takedown_validation=takedown_validation,
    )
    write_json(manifests_dir / "public_beta_blocker_closure_plan.json", blocker_closure_plan)
    archive_record = write_release_archive(
        release_root=export_dir,
        version=config.version,
        exclude_paths=FINAL_ARCHIVE_EXCLUDED_PATHS,
    )
    archive_manifest = {
        "schema_version": 1,
        "archives": [archive_record],
        "excluded_paths": sorted(FINAL_ARCHIVE_EXCLUDED_PATHS),
    }
    write_json(manifests_dir / "archive_manifest.json", archive_manifest)
    checksum_manifest = build_checksum_manifest(release_root=export_dir, archive_records=[archive_record])
    verification = verify_checksum_manifest(export_dir, checksum_manifest)
    checksum_manifest["verification"] = verification
    write_json(manifests_dir / "checksum_manifest.json", checksum_manifest)
    readiness_status = readiness_report["readiness_status"]
    publication_allowed = readiness_status == "pass"

    extra_paths = [
        manifests_dir / "source_depth_feasibility.json",
        manifests_dir / "source_health.json",
        manifests_dir / "archive_manifest.json",
        manifests_dir / "checksum_manifest.json",
        manifests_dir / "public_beta_readiness_report.json",
        manifests_dir / "public_beta_blocker_closure_plan.json",
        export_dir / archive_record["archive_path"],
    ]
    return PublicBetaExportResult(
        export_dir=export_dir,
        summary_path=summary_path,
        release_record_path=manifests_dir / "release_record.json",
        item_manifest_path=manifests_dir / "item_manifest.json",
        readiness_report_path=manifests_dir / "public_beta_readiness_report.json",
        blocker_closure_plan_path=manifests_dir / "public_beta_blocker_closure_plan.json",
        checksum_manifest_path=manifests_dir / "checksum_manifest.json",
        archive_manifest_path=manifests_dir / "archive_manifest.json",
        artifact_paths=[*artifact_paths, *extra_paths],
        readiness_status=readiness_status,
        publication_allowed=publication_allowed,
    )


def _readiness_report(
    *,
    version: str,
    profile_id: str,
    release_summary: dict[str, Any],
    build_release_summary: dict[str, Any],
    source_depth_feasibility: dict[str, Any],
    leakage_report: dict[str, Any],
    selected_benchmark_reference_status: Any,
    benchmark_reference_versioning: dict[str, Any] | None,
    checksum_verification: dict[str, Any],
    archive_manifest: dict[str, Any],
    docs_validation: dict[str, Any],
    takedown_validation: dict[str, Any],
) -> dict[str, Any]:
    gates = [
        _source_depth_gate(source_depth_feasibility),
        _synthetic_target_scale_gate(source_depth_feasibility),
        _rights_provenance_gate(release_summary),
        _privacy_review_gate(release_summary),
        _uniqueness_leakage_gate(build_release_summary, leakage_report),
        _benchmark_reference_gate(selected_benchmark_reference_status, benchmark_reference_versioning),
        _annotation_expectations_gate(release_summary),
        _portability_archive_gate(checksum_verification, archive_manifest),
        _public_docs_gate(docs_validation),
        _takedown_gate(takedown_validation),
    ]
    readiness_status = "pass" if all(gate["status"] == "pass" for gate in gates) else "blocked"
    return {
        "schema_version": 1,
        "planning_notation": "F5b",
        "current_planning_notation": "F5c",
        "readiness_contract_notation": "F5a",
        "profile_id": profile_id,
        "version": version,
        "valid_statuses": ["pass", "blocked"],
        "readiness_status": readiness_status,
        "publication_allowed": readiness_status == "pass",
        "blocked_gate_ids": [gate["gate_id"] for gate in gates if gate["status"] == "blocked"],
        "publication_stop": (
            "repo sync, upload, tagging, and publication report emission are blocked until every gate passes"
            if readiness_status == "blocked"
            else "all gates passed; publication still requires an explicit operator action outside this dry-run workflow"
        ),
        "gates": gates,
    }


def _blocker_closure_plan(
    *,
    readiness_report: dict[str, Any],
    takedown_validation: dict[str, Any],
) -> dict[str, Any]:
    blockers = [
        _blocker_plan_entry(gate, takedown_validation)
        for gate in readiness_report["gates"]
        if gate["status"] == "blocked"
    ]
    category_counts = dict(Counter(blocker["category"] for blocker in blockers))
    return {
        "schema_version": 1,
        "planning_notation": "F5c",
        "source_readiness_report": "manifests/public_beta_readiness_report.json",
        "readiness_status": readiness_report["readiness_status"],
        "publication_allowed": readiness_report["publication_allowed"],
        "valid_categories": ["repo_owned_immediately_actionable", "external_input_dependent"],
        "summary": {
            "blocked_gate_count": len(blockers),
            "repo_owned_immediately_actionable": category_counts.get("repo_owned_immediately_actionable", 0),
            "external_input_dependent": category_counts.get("external_input_dependent", 0),
        },
        "known_hard_blockers": [
            {
                "gate_id": "synthetic_target_scale",
                "required_action": (
                    "Configure and validate a larger hocrsyngen generation_manifest.v1 batch that covers "
                    f"{F1_SYNTHETIC_TARGET_COUNT} synthetic-control target items."
                ),
                "do_not_relax": True,
            }
        ],
        "blockers": blockers,
    }


def _blocker_plan_entry(gate: dict[str, Any], takedown_validation: dict[str, Any]) -> dict[str, Any]:
    gate_id = gate["gate_id"]
    action = _blocker_action(gate_id, takedown_validation)
    return {
        "gate_id": gate_id,
        "status": gate["status"],
        "category": action["category"],
        "owner_scope": action["owner_scope"],
        "closure_state": action["closure_state"],
        "required_action": action["required_action"],
        "closure_artifacts": action["closure_artifacts"],
        "evidence_paths": gate["evidence_paths"],
        "rationale": gate["rationale"],
        "blocks_publication": True,
    }


def _blocker_action(gate_id: str, takedown_validation: dict[str, Any]) -> dict[str, Any]:
    if gate_id == "takedown_removal":
        return _takedown_blocker_action(takedown_validation)
    if gate_id not in BLOCKER_CLOSURE_ACTIONS:
        raise StageExecutionError(f"blocked public beta gate has no F5c closure metadata: {gate_id}")
    return BLOCKER_CLOSURE_ACTIONS[gate_id]


def _takedown_blocker_action(takedown_validation: dict[str, Any]) -> dict[str, Any]:
    operator_action = takedown_validation.get("required_operator_action") or (
        "Configure a maintainer-private reporting path before public beta publication."
    )
    return {
        "category": "repo_owned_immediately_actionable",
        "owner_scope": "hocrgen governance config plus repository maintainer settings",
        "closure_state": (
            "requires_operator_action"
            if takedown_validation.get("configured_private_reporting_path") is not True
            else "requires_repo_pr_or_doc_update"
        ),
        "required_action": operator_action,
        "closure_artifacts": [
            "src/hocrgen/config/public_beta.yaml",
            "docs/RELEASE_NOTES.md",
            "docs/HANDOFF.md",
            "docs/DATASET_CARD.md",
            "manifests/release_diff.json",
        ],
    }


def _write_readiness_outputs(
    *,
    manifests_dir: Path,
    release_record: PublicBetaReleaseRecord,
    release_summary: dict[str, Any],
    readiness_report: dict[str, Any],
) -> None:
    readiness_status = readiness_report["readiness_status"]
    publication_allowed = readiness_status == "pass"
    final_release_record = release_record.model_copy(
        update={
            "readiness_status": readiness_status,
            "publication_allowed": publication_allowed,
        }
    )
    write_json(manifests_dir / "public_beta_readiness_report.json", readiness_report)
    write_json(manifests_dir / "release_record.json", final_release_record.model_dump(mode="json"))
    release_summary["readiness_status"] = readiness_status
    release_summary["publication_allowed"] = publication_allowed
    release_summary["publication_report_emitted"] = False
    release_summary["publication_blockers"] = [
        gate["gate_id"] for gate in readiness_report["gates"] if gate["status"] == "blocked"
    ]
    write_json(manifests_dir / "release_summary.json", release_summary)


def _gate(gate_id: str, status: bool, evidence_paths: list[str], rationale: str) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "status": "pass" if status else "blocked",
        "evidence_paths": evidence_paths,
        "rationale": rationale,
    }


def _source_depth_gate(source_depth_feasibility: dict[str, Any]) -> dict[str, Any]:
    summary = source_depth_feasibility.get("summary", {})
    status = summary.get("overall_feasibility_status") == "feasible" and summary.get("target_scale_gap", 1) == 0
    return _gate(
        "source_depth_composition",
        status,
        ["manifests/source_depth_feasibility.json", "manifests/source_stats.json", "docs/DATASET_CARD.md"],
        (
            "Source-depth allocation reaches the planned public beta composition."
            if status
            else "Source-depth allocation is not yet feasible for the planned public beta composition."
        ),
    )


def _synthetic_target_scale_gate(source_depth_feasibility: dict[str, Any]) -> dict[str, Any]:
    synthetic_source = next(
        (source for source in source_depth_feasibility.get("sources", []) if source.get("source_id") == "project_synthetic"),
        {},
    )
    observed = int(synthetic_source.get("target_scale_candidate_count", 0) or 0)
    status = observed >= F1_SYNTHETIC_TARGET_COUNT
    return _gate(
        "synthetic_target_scale",
        status,
        ["manifests/source_depth_feasibility.json", "manifests/synthetic_composition.json"],
        (
            f"Validated synthetic target-scale evidence covers {observed} / {F1_SYNTHETIC_TARGET_COUNT} required items."
            if status
            else f"Validated hocrsyngen evidence covers only {observed} / {F1_SYNTHETIC_TARGET_COUNT} synthetic target items; a larger validated batch is still required."
        ),
    )


def _rights_provenance_gate(release_summary: dict[str, Any]) -> dict[str, Any]:
    status = release_summary["exported_item_count"] > 0
    return _gate(
        "rights_provenance",
        status,
        ["manifests/item_manifest.json", "manifests/source_stats.json", "docs/PROVENANCE.md"],
        "Public payload items carry portable rights and provenance metadata.",
    )


def _privacy_review_gate(release_summary: dict[str, Any]) -> dict[str, Any]:
    status = release_summary["blocked_count"] == 0 and release_summary["review_required_count"] == 0
    return _gate(
        "privacy_review",
        status,
        ["manifests/privacy_stats.json", "manifests/review_required_items.json", "manifests/blocked_items.json"],
        (
            "No blocked or review-required items remain in the governed candidate pool."
            if status
            else "Blocked or review-required items remain and prevent public beta publication."
        ),
    )


def _uniqueness_leakage_gate(build_release_summary: dict[str, Any], leakage_report: dict[str, Any]) -> dict[str, Any]:
    status = (
        build_release_summary.get("near_duplicate_review_status") == "ok"
        and build_release_summary.get("benchmark_holdout_leakage_status") == "ok"
        and leakage_report.get("status") == "ok"
    )
    return _gate(
        "uniqueness_leakage",
        status,
        [
            "manifests/duplicate_relations.json",
            "manifests/duplicate_clusters.json",
            "manifests/benchmark_leakage_risk.json",
        ],
        (
            "Exact duplicates, near duplicates, source groups, split leakage, and benchmark overlap are cleared or policy-resolved."
            if status
            else "Duplicate, source-group, split, or benchmark/holdout leakage evidence remains blocked."
        ),
    )


def _benchmark_reference_gate(status_artifact: Any, versioning: dict[str, Any] | None) -> dict[str, Any]:
    ready = 0
    blocked_or_draft = 1
    if status_artifact is not None:
        ready = status_artifact.counts.get("reference_ready", 0)
        blocked_or_draft = status_artifact.counts.get("blocked_or_draft", 0)
    status = ready > 0 and blocked_or_draft == 0 and (versioning or {}).get("status") == "ok"
    return _gate(
        "benchmark_references",
        status,
        [
            "manifests/benchmark_manifest.json",
            "manifests/benchmark_reference_manifest.json",
            "manifests/benchmark_reference_status.json",
            "manifests/benchmark_reference_versioning.json",
            "docs/BENCHMARK_CARD.md",
        ],
        (
            "Benchmark references are reviewed/adjudicated and versioning is coherent."
            if status
            else "Benchmark references include draft, unavailable, blocked, or non-coherent reference status and cannot support public beta readiness."
        ),
    )


def _annotation_expectations_gate(release_summary: dict[str, Any]) -> dict[str, Any]:
    annotation_manifest = release_summary["annotation_manifest"]
    annotation_pilot = release_summary["annotation_pilot"]
    status = (
        not annotation_manifest["transcription_required"]
        and not annotation_manifest["layout_labels_required"]
        and not annotation_pilot["transcription_required_for_release"]
        and not annotation_pilot["layout_labels_required_for_release"]
    )
    return _gate(
        "annotation_expectations",
        status,
        ["manifests/annotation_manifest.json", "manifests/annotation_pilot_manifest.json"],
        "Annotation and pilot references are additive, portable, and status-labeled without requiring complete labels for every beta item.",
    )


def _portability_archive_gate(checksum_verification: dict[str, Any], archive_manifest: dict[str, Any]) -> dict[str, Any]:
    status = checksum_verification.get("status") == "pass" and bool(archive_manifest.get("archives"))
    return _gate(
        "portability_checksums_archives",
        status,
        ["manifests/checksum_manifest.json", "manifests/archive_manifest.json", "archives"],
        (
            "Release assets, docs, manifests, benchmark references, and archive digests verify from the handoff tree."
            if status
            else "Checksum or archive verification failed from the handoff tree."
        ),
    )


def _validate_public_beta_docs(export_dir: Path) -> dict[str, Any]:
    missing: list[str] = []
    incomplete: list[dict[str, Any]] = []
    absolute_path_leaks: list[str] = []
    export_root = str(export_dir.resolve())
    for relative_path, required_fragments in PUBLIC_BETA_REQUIRED_DOCS.items():
        path = export_dir / relative_path
        if not path.is_file():
            missing.append(relative_path)
            continue
        text = path.read_text(encoding="utf-8")
        absent_fragments = [fragment for fragment in required_fragments if fragment not in text]
        if absent_fragments:
            incomplete.append({"path": relative_path, "missing_fragments": absent_fragments})
        if export_root in text:
            absolute_path_leaks.append(relative_path)
    return {
        "absolute_path_leaks": absolute_path_leaks,
        "incomplete": incomplete,
        "missing": missing,
        "required_paths": sorted(PUBLIC_BETA_REQUIRED_DOCS),
        "status": "pass" if not missing and not incomplete and not absolute_path_leaks else "blocked",
    }


def _validate_takedown_workflow(export_dir: Path, governance: PublicBetaGovernanceConfig) -> dict[str, Any]:
    evidence_paths = ["docs/RELEASE_NOTES.md", "docs/HANDOFF.md", "docs/DATASET_CARD.md", "manifests/release_diff.json"]
    missing = [relative_path for relative_path in evidence_paths if not (export_dir / relative_path).is_file()]
    private_path = governance.private_reporting_path
    public_path = governance.public_reporting_path
    required_fragments = {
        "docs/RELEASE_NOTES.md": ["Rights, privacy, source-owner, correction", "review/config/source-status changes"],
        "docs/DATASET_CARD.md": ["Takedown and Corrections", public_path.label, private_path.label],
        "docs/HANDOFF.md": ["Stop Conditions", "Do not publish to HeOCR", private_path.label],
    }
    incomplete: list[dict[str, Any]] = []
    for relative_path, fragments in required_fragments.items():
        path = export_dir / relative_path
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        absent_fragments = [fragment for fragment in fragments if fragment not in text]
        if absent_fragments:
            incomplete.append({"path": relative_path, "missing_fragments": absent_fragments})
    configured_private_reporting_path = private_path.configured
    return {
        "configured_private_reporting_path": configured_private_reporting_path,
        "private_reporting_channel": private_path.channel,
        "private_reporting_path_id": private_path.id,
        "private_reporting_path_label": private_path.label,
        "public_reporting_path_id": public_path.id,
        "public_reporting_path_label": public_path.label,
        "required_operator_action": "" if configured_private_reporting_path else private_path.required_operator_action,
        "evidence_paths": evidence_paths,
        "incomplete": incomplete,
        "missing": missing,
        "status": "pass" if configured_private_reporting_path and not missing and not incomplete else "blocked",
    }


def _public_docs_gate(docs_validation: dict[str, Any]) -> dict[str, Any]:
    status = docs_validation.get("status") == "pass"
    problems: list[str] = []
    if docs_validation.get("missing"):
        problems.append(f"missing docs: {', '.join(docs_validation['missing'])}")
    if docs_validation.get("incomplete"):
        problems.append("required beta doc sections are incomplete")
    if docs_validation.get("absolute_path_leaks"):
        problems.append(f"absolute export paths leaked in docs: {', '.join(docs_validation['absolute_path_leaks'])}")
    return _gate(
        "public_docs",
        status,
        [
            "docs/DATASET_CARD.md",
            "docs/PROVENANCE.md",
            "docs/CHANGELOG.md",
            "docs/RELEASE_NOTES.md",
            "docs/BENCHMARK_CARD.md",
            "docs/HANDOFF.md",
        ],
        (
            "Beta-specific public docs were generated with composition, limitations, known blocker, provenance, benchmark, and handoff context."
            if status
            else f"Beta-specific public docs are incomplete: {'; '.join(problems)}."
        ),
    )


def _takedown_gate(takedown_validation: dict[str, Any]) -> dict[str, Any]:
    status = (
        takedown_validation.get("status") == "pass"
        and takedown_validation.get("configured_private_reporting_path") is True
        and not takedown_validation.get("missing")
        and not takedown_validation.get("incomplete")
    )
    return _gate(
        "takedown_removal",
        status,
        [
            "src/hocrgen/config/public_beta.yaml",
            "docs/RELEASE_NOTES.md",
            "docs/HANDOFF.md",
            "docs/DATASET_CARD.md",
            "manifests/release_diff.json",
        ],
        (
            "Release notes and handoff notes document configured public and private rights/privacy/source-owner correction and takedown paths."
            if status
            else (
                "Takedown workflow docs exist, but no repo-configured private reporting path is available; "
                f"required operator action: "
                f"{str(takedown_validation.get('required_operator_action', 'configure a private reporting path')).rstrip('.')}."
            )
        ),
    )


def _reporting_path_lines(governance: PublicBetaGovernanceConfig) -> list[str]:
    public_path = governance.public_reporting_path
    private_path = governance.private_reporting_path
    lines = [
        f"- Public reporting path: {public_path.label}.",
        f"- Private reporting path: {private_path.label}.",
    ]
    if public_path.url:
        lines.append(f"- Public reporting URL: {public_path.url}.")
    if private_path.url:
        lines.append(f"- Private reporting URL: {private_path.url}.")
    if private_path.configured:
        lines.append("- Private reporting status: configured in repo governance config.")
    else:
        lines.append(f"- Required operator action: {private_path.required_operator_action}")
    return lines


def _dataset_card(
    version: str,
    profile: ReleaseProfile,
    items: list[Any],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    included_sources: list[str],
    governance: PublicBetaGovernanceConfig,
) -> str:
    split_counts = Counter(item.split for item in items if item.split)
    synthetic_composition = synthetic_composition_report(items)
    return "\n".join(
        [
            f"# HeOCR Public Beta {version}",
            "",
            "## Scope",
            f"This is a deliberate public beta packaging dry run from `hocrgen` using `{profile.id}`.",
            "It is not published until every readiness gate in `manifests/public_beta_readiness_report.json` is `pass`.",
            f"It currently packages {len(items)} release-ready candidate items across the configured public splits.",
            "",
            "## Included Sources",
            *[f"- `{source_id}`" for source_id in included_sources],
            "",
            "## Excluded From Public Payload",
            f"- Review-required items: {len(review_required_items)}",
            f"- Blocked items: {len(blocked_items)}",
            "",
            "## Split Counts",
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: split_sort_key(item[0]))],
            "",
            "## Synthetic Composition",
            *(synthetic_composition_lines(synthetic_composition)),
            "",
            "## Known Blockers",
            "- Public beta readiness remains blocked until a larger validated hocrsyngen batch satisfies the synthetic target-scale gate.",
            "- Operator-only F1c artifacts are not public beta readiness evidence by themselves.",
            "- Draft, unavailable, or blocked benchmark references must not be presented as public beta-ready references.",
            "",
            "## Takedown and Corrections",
            "- Public reports should use the project issue tracker when disclosure is safe.",
            "- Private rights, privacy, source-owner, or takedown reports must not require sensitive public issue disclosure.",
            *(_reporting_path_lines(governance)),
            "- Removals must flow through source status, review/config changes, release diffs, changelogs, and release notes.",
            "",
        ]
    )


def _release_notes(
    version: str,
    release_summary: dict[str, Any],
    source_stats: dict[str, Any],
    included_sources: list[str],
    release_diff: Any,
    governance: PublicBetaGovernanceConfig,
) -> str:
    split_counts = release_summary["split_counts"]
    synthetic_composition = release_summary["synthetic_composition"]
    return "\n".join(
        [
            f"# Public Beta Release Notes: {version}",
            "",
            "## Publication Status",
            "- Status: blocked until every public beta readiness gate passes.",
            "- No repository sync, upload, release tag, or publication report is emitted by blocked dry runs.",
            "",
            "## Export Summary",
            f"- Exported items: {release_summary['exported_item_count']}",
            f"- Exported real items: {release_summary['exported_real_items']}",
            f"- Exported synthetic items: {release_summary['exported_synthetic_items']}",
            f"- Upstream release-ready items: {release_summary['release_ready_count']}",
            "",
            "## Split Counts",
            *[f"- `{split}`: {count}" for split, count in sorted(split_counts.items(), key=lambda item: split_sort_key(item[0]))],
            "",
            "## Included Sources",
            *[f"- `{source_id}`: {source_stats['sources'][source_id]} items" for source_id in included_sources],
            "",
            "## Synthetic Composition",
            *(synthetic_composition_lines(synthetic_composition)),
            "",
            "## Takedown and Corrections",
            "- Rights, privacy, source-owner, correction, and source-breakage reports must be triaged through review/config/source-status changes before any refreshed publication.",
            "- Public removals are reflected in `docs/CHANGELOG.md`, `manifests/release_diff.json`, and this file where disclosure is safe.",
            *(_reporting_path_lines(governance)),
            "",
            "## Compared To Previous Release",
            f"- Added: {release_diff.counts['added']}; removed: {release_diff.counts['removed']}; changed: {release_diff.counts['changed']}.",
            "",
        ]
    )


def _provenance_doc(
    bundle: ConfigBundle,
    profile: ReleaseProfile,
    included_sources: list[str],
    exported_at: str,
    commit_sha: str,
) -> str:
    registry = {source.id: source for source in bundle.source_registry.sources}
    source_sections: list[str] = []
    for source_id in included_sources:
        source_sections.extend(source_snapshot_lines(registry[source_id]))
    return "\n".join(
        [
            "# Public Beta Provenance",
            "",
            f"- Profile: `{profile.id}`",
            f"- Exported at: `{exported_at}`",
            f"- hocrgen commit: `{commit_sha}`",
            "- Publication targets: none in this dry-run handoff.",
            "- HeOCR, Hugging Face, Kaggle, and HeOCRsynth publication remain out of scope for blocked F5b packaging.",
            "",
            "## Source Snapshot",
            *source_sections,
            "",
        ]
    )


def _handoff_doc(
    version: str,
    profile: ReleaseProfile,
    release_summary: dict[str, Any],
    included_sources: list[str],
    commit_sha: str,
    governance: PublicBetaGovernanceConfig,
) -> str:
    return "\n".join(
        [
            "# Public Beta Handoff Notes",
            "",
            f"- Version: `{version}`",
            "- Target dataset repo: `HeOCR` after all gates pass; no repo sync is performed by this blocked dry run.",
            f"- Release profile: `{profile.id}`",
            f"- hocrgen commit: `{commit_sha}`",
            "",
            "## Export Summary",
            f"- Exported items: {release_summary['exported_item_count']}",
            f"- Exported real items: {release_summary['exported_real_items']}",
            f"- Exported synthetic items: {release_summary['exported_synthetic_items']}",
            "",
            "## Included Sources",
            *[f"- `{source_id}`" for source_id in included_sources],
            "",
            "## Stop Conditions",
            "- If any gate in `manifests/public_beta_readiness_report.json` is `blocked`, stop before repository sync, upload, release tagging, or publication report emission.",
            "- Keep the larger validated hocrsyngen synthetic batch as an explicit blocker until the target-scale gate passes.",
            "- Do not publish to HeOCR, Hugging Face, Kaggle, or HeOCRsynth from this command.",
            "",
            "## Takedown and Corrections",
            *(_reporting_path_lines(governance)),
            "",
        ]
    )


def _validate_public_beta_overwrite_target(export_dir: Path, version: str) -> None:
    if not export_dir.is_dir():
        raise StageExecutionError(f"public beta export overwrite target is not a directory: {export_dir}")
    disallowed = {
        export_dir.anchor,
        str(Path.home()),
        str(REPO_ROOT),
    }
    if str(export_dir) in disallowed:
        raise StageExecutionError(f"refusing to overwrite unsafe public beta export target: {export_dir}")
    if len(export_dir.parts) < 3:
        raise StageExecutionError(f"refusing to overwrite unsafe public beta export target: {export_dir}")
    if export_dir.name != version:
        raise StageExecutionError(f"public beta export overwrite target must end with {version}: {export_dir}")


def _resolve_comparison_release(export_dir: Path, config: PublicBetaExportConfig) -> Path | None:
    if config.compare_to is None:
        return None
    candidate = config.compare_to.resolve()
    if export_dir.resolve() == candidate:
        raise StageExecutionError("--compare-to cannot point to the current public beta export directory")
    validate_release_diff_baseline(candidate)
    return candidate
