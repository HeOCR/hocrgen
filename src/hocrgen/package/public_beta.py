from __future__ import annotations

import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
    ReviewDecisionAuditRecord,
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

PUBLIC_BETA_CURRENT_PLANNING_NOTATION = "F6d"


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
    repo_owned_blocker_report_path: Path
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

REPO_OWNED_PUBLIC_BETA_GATES = {"privacy_review", "benchmark_references", "takedown_removal"}

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
            "manifests/public_beta_repo_owned_blocker_report.json",
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
            "Finalize every selected benchmark item's benchmark-reference status/versioning evidence through real "
            "review/adjudication artifacts, or keep the limitation disclosed; public beta readiness stays blocked "
            "while references are draft, unavailable, blocked, unadjudicated, or versioning-incoherent."
        ),
        "closure_artifacts": [
            "manifests/public_beta_repo_owned_blocker_report.json",
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
    decision_audit = load_models(build_dir / "decision_audit.json", ReviewDecisionAuditRecord)
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
                "repo_owned_blocker_report": "manifests/public_beta_repo_owned_blocker_report.json",
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
    readiness_report, archive_record = _stabilize_public_beta_readiness_artifacts(
        export_dir=export_dir,
        manifests_dir=manifests_dir,
        version=config.version,
        profile_id=profile_id,
        release_record=initial_release_record,
        release_summary=release_summary,
        build_release_summary=build_release_summary,
        source_depth_feasibility=source_depth_feasibility,
        leakage_report=leakage_report,
        selected_benchmark_reference_status=selected_benchmark_reference_status,
        benchmark_reference_versioning=benchmark_inputs.reference_versioning,
        docs_validation=docs_validation,
        takedown_validation=takedown_validation,
        review_required_items=review_required_items,
        blocked_items=blocked_items,
        selected_review_queue=selected_review_queue,
        decision_audit=decision_audit,
        source_registry=bundle.source_registry,
        profile=profile,
        readiness_report=readiness_report,
    )
    readiness_status = readiness_report["readiness_status"]
    publication_allowed = readiness_status == "pass"

    extra_paths = [
        manifests_dir / "source_depth_feasibility.json",
        manifests_dir / "source_health.json",
        manifests_dir / "archive_manifest.json",
        manifests_dir / "checksum_manifest.json",
        manifests_dir / "public_beta_readiness_report.json",
        manifests_dir / "public_beta_blocker_closure_plan.json",
        manifests_dir / "public_beta_repo_owned_blocker_report.json",
        export_dir / archive_record["archive_path"],
    ]
    return PublicBetaExportResult(
        export_dir=export_dir,
        summary_path=summary_path,
        release_record_path=manifests_dir / "release_record.json",
        item_manifest_path=manifests_dir / "item_manifest.json",
        readiness_report_path=manifests_dir / "public_beta_readiness_report.json",
        blocker_closure_plan_path=manifests_dir / "public_beta_blocker_closure_plan.json",
        repo_owned_blocker_report_path=manifests_dir / "public_beta_repo_owned_blocker_report.json",
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
        "current_planning_notation": PUBLIC_BETA_CURRENT_PLANNING_NOTATION,
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
        "planning_notation": PUBLIC_BETA_CURRENT_PLANNING_NOTATION,
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
        raise StageExecutionError(f"blocked public beta gate has no F5d closure metadata: {gate_id}")
    return BLOCKER_CLOSURE_ACTIONS[gate_id]


def _write_public_beta_blocker_outputs(
    *,
    manifests_dir: Path,
    readiness_report: dict[str, Any],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    selected_review_queue: list[ReviewQueueRecord],
    decision_audit: list[ReviewDecisionAuditRecord],
    source_registry: Any,
    profile: ReleaseProfile,
    selected_benchmark_reference_status: Any,
    benchmark_reference_versioning: dict[str, Any] | None,
    takedown_validation: dict[str, Any],
) -> None:
    blocker_closure_plan = _blocker_closure_plan(
        readiness_report=readiness_report,
        takedown_validation=takedown_validation,
    )
    write_json(manifests_dir / "public_beta_blocker_closure_plan.json", blocker_closure_plan)
    repo_owned_blocker_report = _repo_owned_blocker_report(
        readiness_report=readiness_report,
        review_required_items=review_required_items,
        blocked_items=blocked_items,
        selected_review_queue=selected_review_queue,
        decision_audit=decision_audit,
        source_registry=source_registry,
        profile=profile,
        selected_benchmark_reference_status=selected_benchmark_reference_status,
        benchmark_reference_versioning=benchmark_reference_versioning,
        takedown_validation=takedown_validation,
    )
    write_json(manifests_dir / "public_beta_repo_owned_blocker_report.json", repo_owned_blocker_report)


def _stabilize_public_beta_readiness_artifacts(
    *,
    export_dir: Path,
    manifests_dir: Path,
    version: str,
    profile_id: str,
    release_record: PublicBetaReleaseRecord,
    release_summary: dict[str, Any],
    build_release_summary: dict[str, Any],
    source_depth_feasibility: dict[str, Any],
    leakage_report: dict[str, Any],
    selected_benchmark_reference_status: Any,
    benchmark_reference_versioning: dict[str, Any] | None,
    docs_validation: dict[str, Any],
    takedown_validation: dict[str, Any],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    selected_review_queue: list[ReviewQueueRecord],
    decision_audit: list[ReviewDecisionAuditRecord],
    source_registry: Any,
    profile: ReleaseProfile,
    readiness_report: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    archive_record = None
    for _ in range(3):
        _write_public_beta_blocker_outputs(
            manifests_dir=manifests_dir,
            readiness_report=readiness_report,
            review_required_items=review_required_items,
            blocked_items=blocked_items,
            selected_review_queue=selected_review_queue,
            decision_audit=decision_audit,
            source_registry=source_registry,
            profile=profile,
            selected_benchmark_reference_status=selected_benchmark_reference_status,
            benchmark_reference_versioning=benchmark_reference_versioning,
            takedown_validation=takedown_validation,
        )
        archive_record = write_release_archive(
            release_root=export_dir,
            version=version,
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
        next_readiness_report = _readiness_report(
            version=version,
            profile_id=profile_id,
            release_summary=release_summary,
            build_release_summary=build_release_summary,
            source_depth_feasibility=source_depth_feasibility,
            leakage_report=leakage_report,
            selected_benchmark_reference_status=selected_benchmark_reference_status,
            benchmark_reference_versioning=benchmark_reference_versioning,
            checksum_verification=verification,
            archive_manifest=archive_manifest,
            docs_validation=docs_validation,
            takedown_validation=takedown_validation,
        )
        if next_readiness_report == readiness_report:
            break
        readiness_report = next_readiness_report
        _write_readiness_outputs(
            manifests_dir=manifests_dir,
            release_record=release_record,
            release_summary=release_summary,
            readiness_report=readiness_report,
        )
    else:
        raise StageExecutionError("public beta readiness artifacts did not stabilize after final checksum generation")
    if archive_record is None:
        raise StageExecutionError("public beta archive generation did not run")
    return readiness_report, archive_record


def _repo_owned_blocker_report(
    *,
    readiness_report: dict[str, Any],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    selected_review_queue: list[ReviewQueueRecord],
    decision_audit: list[ReviewDecisionAuditRecord],
    source_registry: Any,
    profile: ReleaseProfile,
    selected_benchmark_reference_status: Any,
    benchmark_reference_versioning: dict[str, Any] | None,
    takedown_validation: dict[str, Any],
) -> dict[str, Any]:
    gates_by_id = {gate["gate_id"]: gate for gate in readiness_report["gates"]}
    repo_owned_entries = [
        _privacy_review_closure_entry(
            gates_by_id["privacy_review"],
            review_required_items,
            blocked_items,
            selected_review_queue,
            decision_audit,
            source_registry,
            profile,
        ),
        _benchmark_reference_closure_entry(
            gates_by_id["benchmark_references"],
            selected_benchmark_reference_status,
            benchmark_reference_versioning,
        ),
        _takedown_closure_entry(gates_by_id["takedown_removal"], takedown_validation),
    ]
    blocked_entries = [entry for entry in repo_owned_entries if entry["status"] == "blocked"]
    external_blocked_gate_ids = _blocked_gate_ids_by_closure_category(
        readiness_report=readiness_report,
        takedown_validation=takedown_validation,
        category="external_input_dependent",
    )
    return {
        "schema_version": 1,
        "planning_notation": PUBLIC_BETA_CURRENT_PLANNING_NOTATION,
        "source_readiness_report": "manifests/public_beta_readiness_report.json",
        "readiness_status": readiness_report["readiness_status"],
        "publication_allowed": readiness_report["publication_allowed"],
        "repo_owned_gate_ids": sorted(REPO_OWNED_PUBLIC_BETA_GATES),
        "repo_owned_status": "pass" if not blocked_entries else "blocked",
        "repo_owned_blocked_gate_ids": [entry["gate_id"] for entry in blocked_entries],
        "external_input_dependent_blocked_gate_ids": external_blocked_gate_ids,
        "external_input_dependent_treatment": (
            "kept blocked until real source-depth and hocrsyngen target-scale inputs exist"
        ),
        "entries": repo_owned_entries,
    }


def _blocked_gate_ids_by_closure_category(
    *,
    readiness_report: dict[str, Any],
    takedown_validation: dict[str, Any],
    category: str,
) -> list[str]:
    return [
        gate["gate_id"]
        for gate in readiness_report["gates"]
        if gate["status"] == "blocked" and _blocker_action(gate["gate_id"], takedown_validation)["category"] == category
    ]


def _privacy_review_closure_entry(
    gate: dict[str, Any],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    selected_review_queue: list[ReviewQueueRecord],
    decision_audit: list[ReviewDecisionAuditRecord],
    source_registry: Any,
    profile: ReleaseProfile,
) -> dict[str, Any]:
    queue_by_item_id = {entry.item_id: entry for entry in selected_review_queue}
    relevant_item_ids = {item.item_id for item in review_required_items + blocked_items}
    relevant_decision_audit = [entry for entry in decision_audit if entry.item_id in relevant_item_ids]
    decision_audit_by_item_id = {entry.item_id: entry for entry in relevant_decision_audit}
    audited_item_ids = {entry.item_id for entry in relevant_decision_audit}
    missing_decision_audit_item_ids = sorted(relevant_item_ids - audited_item_ids)
    review_required_item_entries = [
        _privacy_review_item_entry(
            item=item,
            queue_by_item_id=queue_by_item_id,
            decision_audit_by_item_id=decision_audit_by_item_id,
        )
        for item in sorted(review_required_items, key=lambda record: record.item_id)
    ]
    blocked_item_entries = [
        _privacy_review_item_entry(
            item=item,
            queue_by_item_id=queue_by_item_id,
            decision_audit_by_item_id=decision_audit_by_item_id,
        )
        for item in sorted(blocked_items, key=lambda record: record.item_id)
    ]
    suggested_decision_counts = Counter(
        entry.suggested_decision for entry in selected_review_queue if entry.suggested_decision
    )
    privacy_flag_counts = Counter(item.privacy_flag.value for item in review_required_items + blocked_items)
    decision_source_counts = Counter(entry.decision_source for entry in relevant_decision_audit)
    decision_outcome_counts = Counter(entry.outcome for entry in relevant_decision_audit)
    f6d_assessment = _privacy_review_f6d_assessment(
        gate=gate,
        review_required_items=review_required_items,
        blocked_items=blocked_items,
        relevant_decision_audit=relevant_decision_audit,
        missing_decision_audit_item_ids=missing_decision_audit_item_ids,
    )
    privacy_review_closed = f6d_assessment["closure_state"] == "pass"
    return {
        "gate_id": "privacy_review",
        "status": gate["status"],
        "closure_state": f6d_assessment["closure_state"],
        "required_action": (
            "No repo-owned privacy/review action remains for currently exported public beta candidates."
            if privacy_review_closed
            else (
                "Resolve each listed item through repo-tracked review decisions, allow/block overrides, "
                "privacy config changes, or source-status changes; do not publish while unresolved items remain."
            )
        ),
        "counts": {
            "review_required": len(review_required_items),
            "blocked": len(blocked_items),
            "suggested_decision": dict(sorted(suggested_decision_counts.items())),
            "privacy_flag": dict(sorted(privacy_flag_counts.items())),
            "decision_source": dict(sorted(decision_source_counts.items())),
            "decision_outcome": dict(sorted(decision_outcome_counts.items())),
            "decision_audit_item_count": len(relevant_decision_audit),
            "missing_decision_audit": len(missing_decision_audit_item_ids),
        },
        "decision_audit_coverage": {
            "status": "blocked" if missing_decision_audit_item_ids else "pass",
            "covered_item_count": len(relevant_item_ids) - len(missing_decision_audit_item_ids),
            "missing_item_count": len(missing_decision_audit_item_ids),
            "missing_item_ids": missing_decision_audit_item_ids,
        },
        "f6d_assessment": f6d_assessment,
        "source_status_evidence": _source_status_evidence(
            source_registry=source_registry,
            profile=profile,
            relevant_source_ids={item.source_id for item in review_required_items + blocked_items},
        ),
        "review_required_items": review_required_item_entries,
        "blocked_items": blocked_item_entries,
        "blocked_item_ids": [item.item_id for item in sorted(blocked_items, key=lambda record: record.item_id)],
        "evidence_paths": gate["evidence_paths"],
        "rationale": gate["rationale"],
    }


def _privacy_review_item_entry(
    *,
    item: PrivacyScannedItemRecord,
    queue_by_item_id: dict[str, ReviewQueueRecord],
    decision_audit_by_item_id: dict[str, ReviewDecisionAuditRecord],
) -> dict[str, Any]:
    queue_entry = queue_by_item_id.get(item.item_id)
    audit_entry = decision_audit_by_item_id.get(item.item_id)
    return {
        "item_id": item.item_id,
        "source_id": item.source_id,
        "privacy_flag": item.privacy_flag.value,
        "privacy_reasons": item.privacy_reasons,
        "classification_review_reasons": item.classification_review_reasons,
        "suggested_decision": queue_entry.suggested_decision if queue_entry else None,
        "review_reasons": queue_entry.review_reasons if queue_entry else [],
        "decision_source": audit_entry.decision_source if audit_entry else None,
        "decision_outcome": audit_entry.outcome if audit_entry else None,
        "decision": audit_entry.decision if audit_entry else None,
    }


def _privacy_review_f6d_assessment(
    *,
    gate: dict[str, Any],
    review_required_items: list[PrivacyScannedItemRecord],
    blocked_items: list[PrivacyScannedItemRecord],
    relevant_decision_audit: list[ReviewDecisionAuditRecord],
    missing_decision_audit_item_ids: list[str],
) -> dict[str, Any]:
    review_required_count = len(review_required_items)
    blocked_count = len(blocked_items)
    unresolved_count = sum(1 for entry in relevant_decision_audit if entry.outcome == "unresolved")
    default_unresolved_count = sum(
        1
        for entry in relevant_decision_audit
        if entry.outcome == "unresolved" and entry.decision_source == "default_unresolved"
    )
    if gate["status"] == "pass" and not review_required_count and not blocked_count and not missing_decision_audit_item_ids:
        assessment_status = "closed_with_no_unresolved_privacy_or_review_items"
        closure_state = "pass"
        limitation = "none for currently governed public beta candidates"
    elif missing_decision_audit_item_ids:
        assessment_status = "blocked_missing_decision_audit_evidence"
        closure_state = "requires_decision_audit_reconciliation"
        limitation = (
            f"{len(missing_decision_audit_item_ids)} review/privacy item(s) lack decision-audit evidence; "
            "reconcile build_release/decision_audit.json before claiming F6d privacy/review closure"
        )
    elif blocked_count:
        assessment_status = "blocked_blocked_items_present"
        closure_state = "requires_repo_tracked_review_config_or_source_status_evidence"
        limitation = (
            f"{blocked_count} blocked item(s) and {review_required_count} review-required item(s) remain; "
            "blocked items must be resolved or excluded through repo-tracked review/config/source-status evidence"
        )
    elif review_required_count:
        assessment_status = "blocked_unresolved_review_required_items"
        closure_state = "requires_repo_tracked_review_config_or_source_status_evidence"
        limitation = (
            f"{review_required_count} review-required item(s) remain unresolved; "
            "no repo-tracked review decision, privacy config change, or source-status change currently closes the gate"
        )
    else:
        assessment_status = "blocked_inconsistent_privacy_review_evidence"
        closure_state = "requires_readiness_report_reconciliation"
        limitation = "privacy/review gate is blocked even though no review-required or blocked item evidence was provided"
    return {
        "planning_notation": "F6d",
        "assessment_status": assessment_status,
        "closure_state": closure_state,
        "readiness_contract": (
            "Privacy/review readiness can pass only when the governed candidate pool has no review-required, "
            "blocked, unresolved privacy, unresolved consent, or unresolved takedown states after repo-tracked "
            "review decisions, config changes, or source-status changes."
        ),
        "review_required_item_count": review_required_count,
        "blocked_item_count": blocked_count,
        "unresolved_decision_count": unresolved_count,
        "default_unresolved_decision_count": default_unresolved_count,
        "missing_decision_audit_count": len(missing_decision_audit_item_ids),
        "missing_decision_audit_item_ids": missing_decision_audit_item_ids,
        "decision_audit_coverage_status": "blocked" if missing_decision_audit_item_ids else "pass",
        "limitation_disclosure": limitation,
        "blocked_gate_preserved": gate["status"] == "blocked",
    }


def _source_status_evidence(
    *,
    source_registry: Any,
    profile: ReleaseProfile,
    relevant_source_ids: set[str],
) -> list[dict[str, Any]]:
    sources_by_id = {source.id: source for source in source_registry.sources}
    entries: list[dict[str, Any]] = []
    for source_id in sorted(relevant_source_ids):
        source = sources_by_id.get(source_id)
        if source is None:
            entries.append(
                {
                    "source_id": source_id,
                    "status": "unknown",
                    "default_public_release": None,
                    "requires_manual_review": None,
                    "operational_status": "unknown",
                    "included_in_profile": source_id in profile.include_sources,
                    "excluded_from_profile": source_id in profile.exclude_sources,
                }
            )
            continue
        entries.append(
            {
                "source_id": source_id,
                "status": source.status.value,
                "default_public_release": source.default_public_release,
                "requires_manual_review": source.requires_manual_review,
                "operational_status": source.source_operations.operational_status.value,
                "included_in_profile": source_id in profile.include_sources,
                "excluded_from_profile": source_id in profile.exclude_sources,
            }
        )
    return entries


def _benchmark_reference_closure_entry(
    gate: dict[str, Any],
    selected_benchmark_reference_status: Any,
    benchmark_reference_versioning: dict[str, Any] | None,
) -> dict[str, Any]:
    status_items = list(selected_benchmark_reference_status.items) if selected_benchmark_reference_status is not None else []
    ready_items = []
    unresolved_items = []
    for item in sorted(status_items, key=lambda record: record.item_id):
        if _benchmark_reference_item_ready(item):
            ready_items.append(
                {
                    "item_id": item.item_id,
                    "source_id": item.source_id,
                    "benchmark_split": item.benchmark_split,
                    "public_reference_status": item.public_reference_status,
                    "adjudication_status": item.adjudication_status,
                    "has_transcription_reference": item.has_transcription_reference,
                    "layout_reference_count": item.layout_reference_count,
                    "reviewer_count": item.reviewer_count,
                }
            )
            continue
        unresolved_items.append(
            {
                "item_id": item.item_id,
                "source_id": item.source_id,
                "benchmark_split": item.benchmark_split,
                "public_reference_status": item.public_reference_status,
                "adjudication_status": item.adjudication_status,
                "has_transcription_reference": item.has_transcription_reference,
                "layout_reference_count": item.layout_reference_count,
                "reviewer_count": item.reviewer_count,
                "required_action": _benchmark_reference_item_required_action(item),
            }
        )
    counts = selected_benchmark_reference_status.counts if selected_benchmark_reference_status is not None else {}
    f6c_assessment = _benchmark_reference_f6c_assessment(
        gate=gate,
        status_items=status_items,
        unresolved_items=unresolved_items,
        benchmark_reference_versioning=benchmark_reference_versioning,
    )
    return {
        "gate_id": "benchmark_references",
        "status": gate["status"],
        "closure_state": (
            "pass"
            if gate["status"] == "pass"
            else f6c_assessment["closure_state"]
        ),
        "required_action": (
            "No benchmark-reference action remains for currently selected benchmark items."
            if gate["status"] == "pass"
            else (
                "Keep draft, unavailable, blocked, or unadjudicated references blocked; only reviewed/adjudicated "
                "references with coherent versioning can satisfy public beta readiness."
            )
        ),
        "counts": dict(sorted(counts.items())),
        "versioning_status": (benchmark_reference_versioning or {}).get("status", "not_available"),
        "f6c_assessment": f6c_assessment,
        "ready_items": ready_items,
        "unresolved_items": unresolved_items,
        "evidence_paths": gate["evidence_paths"],
        "rationale": gate["rationale"],
    }


def _benchmark_reference_f6c_assessment(
    *,
    gate: dict[str, Any],
    status_items: list[Any],
    unresolved_items: list[dict[str, Any]],
    benchmark_reference_versioning: dict[str, Any] | None,
) -> dict[str, Any]:
    total_items = len(status_items)
    ready_count = total_items - len(unresolved_items)
    versioning_status = (benchmark_reference_versioning or {}).get("status", "not_available")
    if gate["status"] == "pass":
        assessment_status = "closed_with_reviewed_adjudicated_evidence"
        closure_state = "pass"
        limitation = "none for currently selected benchmark items"
    elif total_items == 0:
        assessment_status = "blocked_no_benchmark_reference_status"
        closure_state = "requires_benchmark_reference_status_artifact"
        limitation = "benchmark-reference status artifact is unavailable for selected benchmark items"
    elif unresolved_items:
        assessment_status = "blocked_partial_or_unavailable_reference_evidence"
        closure_state = "requires_reviewed_or_adjudicated_reference_evidence"
        limitation = (
            f"{ready_count} / {total_items} selected benchmark item(s) have reviewed/adjudicated references; "
            f"{len(unresolved_items)} item(s) remain draft, unavailable, blocked, or unadjudicated"
        )
    else:
        assessment_status = "blocked_versioning_incoherent"
        closure_state = "requires_coherent_reference_versioning"
        limitation = (
            f"All {total_items} selected benchmark item(s) have reviewed/adjudicated references, "
            f"but benchmark-reference versioning status is {versioning_status}"
        )
    return {
        "planning_notation": "F6c",
        "assessment_status": assessment_status,
        "closure_state": closure_state,
        "readiness_contract": (
            "Every selected benchmark item must have reviewed/adjudicated reference evidence and coherent "
            "versioning before benchmark-reference readiness can pass."
        ),
        "selected_benchmark_item_count": total_items,
        "reviewed_adjudicated_item_count": ready_count,
        "unresolved_item_count": len(unresolved_items),
        "versioning_status": versioning_status,
        "limitation_disclosure": limitation,
        "blocked_gate_preserved": gate["status"] == "blocked",
    }


def _benchmark_reference_item_ready(item: Any) -> bool:
    return item.public_reference_status in {"reviewed", "adjudicated"} and item.adjudication_status == "adjudicated"


def _benchmark_reference_item_required_action(item: Any) -> str:
    if item.public_reference_status == "draft":
        return "Complete review/adjudication and update public_reference_status only after the reference is no longer draft."
    if item.public_reference_status == "not_available":
        return "Add real transcription/layout reference evidence and review it, or keep the benchmark limitation disclosed."
    if item.adjudication_status != "adjudicated":
        return "Complete adjudication before using this reference as public beta-ready evidence."
    return "Repair reference status semantics before claiming public beta readiness."


def _takedown_closure_entry(gate: dict[str, Any], takedown_validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "gate_id": "takedown_removal",
        "status": gate["status"],
        "closure_state": (
            _takedown_blocker_action(takedown_validation)["closure_state"]
            if gate["status"] == "blocked"
            else "pass"
        ),
        "required_action": (
            "No takedown/private reporting action remains for current public beta governance config."
            if gate["status"] == "pass"
            else _takedown_required_action(takedown_validation)
        ),
        "configured_private_reporting_path": takedown_validation.get("configured_private_reporting_path"),
        "private_reporting_channel": takedown_validation.get("private_reporting_channel"),
        "private_reporting_path_id": takedown_validation.get("private_reporting_path_id"),
        "private_reporting_path_label": takedown_validation.get("private_reporting_path_label"),
        "repository_check": takedown_validation.get("repository_check", {}),
        "verification": takedown_validation.get("verification", {}),
        "missing": takedown_validation.get("missing", []),
        "incomplete": takedown_validation.get("incomplete", []),
        "evidence_paths": gate["evidence_paths"],
        "rationale": gate["rationale"],
    }


def _takedown_blocker_action(takedown_validation: dict[str, Any]) -> dict[str, Any]:
    return {
        "category": "repo_owned_immediately_actionable",
        "owner_scope": "hocrgen governance config plus repository maintainer settings",
        "closure_state": _takedown_closure_state(takedown_validation),
        "required_action": _takedown_required_action(takedown_validation),
        "closure_artifacts": [
            "manifests/public_beta_repo_owned_blocker_report.json",
            "src/hocrgen/config/public_beta.yaml",
            "docs/RELEASE_NOTES.md",
            "docs/HANDOFF.md",
            "docs/DATASET_CARD.md",
            "manifests/release_diff.json",
        ],
    }


def _takedown_closure_state(takedown_validation: dict[str, Any]) -> str:
    if takedown_validation.get("configured_private_reporting_path") is not True:
        return "requires_operator_action"
    verification = takedown_validation.get("verification") or {}
    if verification.get("freshness_status") != "pass":
        return "requires_repository_settings_reverification"
    return "requires_repo_pr_or_doc_update"


def _takedown_required_action(takedown_validation: dict[str, Any]) -> str:
    if takedown_validation.get("configured_private_reporting_path") is not True:
        required_action = str(
            takedown_validation.get("required_operator_action")
            or "Configure a maintainer-private reporting path before public beta publication."
        ).rstrip(".")
        repository_check = takedown_validation.get("repository_check") or {}
        if repository_check.get("result") == "disabled" and repository_check.get("checked_at"):
            required_action = (
                f"{required_action}; latest repository settings check "
                f"{repository_check['checked_at']}: private reporting is disabled"
            )
        return required_action
    verification = takedown_validation.get("verification") or {}
    if verification.get("freshness_status") != "pass":
        return (
            "Refresh private reporting repository settings verification and update "
            "src/hocrgen/config/public_beta.yaml before claiming takedown readiness."
        )
    problems = _takedown_doc_problems(takedown_validation)
    if problems:
        return f"Repair takedown workflow documentation: {'; '.join(problems)}"
    return "Repair takedown workflow documentation/configuration so configured private reporting evidence passes validation"


def _takedown_doc_problems(takedown_validation: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    missing = takedown_validation.get("missing") or []
    if missing:
        problems.append(f"missing evidence docs: {', '.join(missing)}")
    incomplete = takedown_validation.get("incomplete") or []
    if incomplete:
        fragments: list[str] = []
        for entry in incomplete:
            path = entry.get("path", "unknown")
            missing_fragments = entry.get("missing_fragments") or []
            fragments.append(f"{path} missing {', '.join(missing_fragments)}")
        problems.append(f"incomplete docs: {'; '.join(fragments)}")
    return problems


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
    status_items = list(status_artifact.items) if status_artifact is not None else []
    total = len(status_items)
    ready = sum(1 for item in status_items if _benchmark_reference_item_ready(item))
    unresolved = total - ready
    versioning_status = (versioning or {}).get("status", "not_available")
    status = total > 0 and ready == total and unresolved == 0 and versioning_status == "ok"
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
            f"Benchmark references are reviewed/adjudicated for all {total} selected benchmark item(s), and versioning is coherent."
            if status
            else (
                "Benchmark references cannot support public beta readiness: "
                f"{ready} / {total} selected benchmark item(s) are reviewed/adjudicated; "
                f"{unresolved} item(s) remain draft, unavailable, blocked, or unadjudicated; "
                f"versioning status is {versioning_status}."
            )
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
    if private_path.configured:
        configured_fragments = [
            "Private reporting status: configured in repo governance config.",
            (
                "Private reporting repository check: "
                f"{private_path.repository_check_result} via {private_path.repository_check_method} "
                f"at {private_path.repository_check_at}."
            ),
            (
                "Private reporting verification: "
                f"{private_path.verification_method} by {private_path.verified_by} "
                f"at {private_path.verified_at}."
            ),
            f"Private reporting verification valid until: {private_path.verification_valid_until}.",
        ]
        for fragments in required_fragments.values():
            fragments.extend(configured_fragments)
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
    verification = _private_reporting_verification(private_path)
    return {
        "configured_private_reporting_path": configured_private_reporting_path,
        "private_reporting_channel": private_path.channel,
        "private_reporting_path_id": private_path.id,
        "private_reporting_path_label": private_path.label,
        "public_reporting_path_id": public_path.id,
        "public_reporting_path_label": public_path.label,
        "repository_check": {
            "checked_at": private_path.repository_check_at,
            "method": private_path.repository_check_method,
            "result": private_path.repository_check_result,
        },
        "verification": verification,
        "required_operator_action": "" if configured_private_reporting_path else private_path.required_operator_action,
        "evidence_paths": evidence_paths,
        "incomplete": incomplete,
        "missing": missing,
        "status": (
            "pass"
            if configured_private_reporting_path
            and verification.get("freshness_status") == "pass"
            and not missing
            and not incomplete
            else "blocked"
        ),
    }


def _private_reporting_verification(private_path: Any) -> dict[str, Any]:
    status = "blocked"
    today = date.today()
    valid_until = private_path.verification_valid_until
    reason = "verification_valid_until is not configured"
    if valid_until:
        parsed_valid_until = date.fromisoformat(valid_until)
        if parsed_valid_until >= today:
            status = "pass"
            reason = "verification is within the configured validity window"
        else:
            reason = f"verification expired on {valid_until}"
    return {
        "verified_at": private_path.verified_at,
        "method": private_path.verification_method,
        "verified_by": private_path.verified_by,
        "valid_until": valid_until,
        "freshness_checked_at": today.isoformat(),
        "freshness_status": status,
        "freshness_reason": reason,
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
            else _takedown_blocked_rationale(takedown_validation)
        ),
    )


def _takedown_blocked_rationale(takedown_validation: dict[str, Any]) -> str:
    required_action = _takedown_required_action(takedown_validation)
    if takedown_validation.get("configured_private_reporting_path") is True:
        return (
            "Takedown workflow has a configured private reporting path, but documentation evidence is incomplete; "
            f"required action: {required_action}."
        )
    return (
        "Takedown workflow docs exist, but no repo-configured private reporting path is available; "
        f"required operator action: {required_action}."
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
        if private_path.repository_check_result:
            lines.append(
                "- Private reporting repository check: "
                f"{private_path.repository_check_result} via {private_path.repository_check_method} "
                f"at {private_path.repository_check_at}."
            )
        if private_path.verified_at:
            lines.append(
                "- Private reporting verification: "
                f"{private_path.verification_method} by {private_path.verified_by} "
                f"at {private_path.verified_at}."
            )
        if private_path.verification_valid_until:
            lines.append(f"- Private reporting verification valid until: {private_path.verification_valid_until}.")
    else:
        if private_path.repository_check_result:
            lines.append(
                "- Private reporting repository check: "
                f"{private_path.repository_check_result} via {private_path.repository_check_method} "
                f"at {private_path.repository_check_at}."
            )
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
