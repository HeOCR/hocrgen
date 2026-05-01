from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from hocrgen.benchmark import BENCHMARK_ID, _project_root_for
from hocrgen.config.loader import default_config_root, load_json_file
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    AnnotationPilotConfigRecord,
    AnnotationPilotItemRecord,
    AnnotationPilotManifestRecord,
    AnnotationPilotSelectionAuditRecord,
    BenchmarkItemRecord,
    PrivacyScannedItemRecord,
)


ANNOTATION_PILOT_ID = "e3a_annotation_pilot"


@dataclass(frozen=True)
class AnnotationPilotSelectionOutputs:
    config: AnnotationPilotConfigRecord
    manifest: AnnotationPilotManifestRecord
    audit: list[AnnotationPilotSelectionAuditRecord]


def _annotation_data_root_candidates(config_root: Path) -> list[Path]:
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
        candidate = parent / "annotation_data"
        if candidate not in candidates:
            candidates.append(candidate)
    default_candidate = default_config_root().resolve().parents[2] / "annotation_data"
    if default_candidate not in candidates:
        candidates.append(default_candidate)
    return candidates


def resolve_annotation_data_root(config_root: Path) -> Path:
    for candidate in _annotation_data_root_candidates(config_root):
        if candidate.exists():
            return candidate
    return config_root.resolve().parent / "annotation_data"


def load_annotation_pilot_config(
    config_root: Path,
    pilot_id: str = ANNOTATION_PILOT_ID,
) -> AnnotationPilotConfigRecord:
    root = resolve_annotation_data_root(config_root)
    config_path = root / "pilots" / pilot_id / "config.json"
    try:
        config = AnnotationPilotConfigRecord.model_validate(load_json_file(config_path))
    except ValidationError as exc:
        raise ConfigValidationError(f"annotation pilot config validation failed for {config_path}", details=exc.errors()) from exc
    if config.pilot_id != pilot_id:
        raise ConfigValidationError(
            f"annotation pilot config id mismatch for {config_path}",
            details=[{"expected": pilot_id, "actual": config.pilot_id}],
        )
    return config


def select_annotation_pilot_items(
    *,
    config: AnnotationPilotConfigRecord,
    release_ready_items: list[PrivacyScannedItemRecord],
    benchmark_items: list[BenchmarkItemRecord],
) -> AnnotationPilotSelectionOutputs:
    release_ready_by_id = {item.item_id: item for item in release_ready_items}
    benchmark_by_id = {item.item_id: item for item in benchmark_items}

    selected: list[AnnotationPilotItemRecord] = []
    audit: list[AnnotationPilotSelectionAuditRecord] = []
    for approved in config.approved_items:
        item = release_ready_by_id.get(approved.item_id)
        if item is None:
            raise StageExecutionError(
                f"annotation pilot {config.pilot_id} approved item {approved.item_id} is not release-ready"
            )
        if item.split is None:
            raise StageExecutionError(
                f"annotation pilot {config.pilot_id} approved item {approved.item_id} is missing a split assignment"
            )
        benchmark_item = benchmark_by_id.get(approved.item_id)
        if approved.target_subset == BENCHMARK_ID and benchmark_item is None:
            raise StageExecutionError(
                f"annotation pilot {config.pilot_id} approved benchmark item {approved.item_id} is not in {BENCHMARK_ID}"
            )
        selected.append(
            AnnotationPilotItemRecord(
                pilot_id=config.pilot_id,
                item_id=item.item_id,
                source_id=item.source_id,
                source_item_id=item.source_item_id,
                source_url=item.source_url,
                title=item.title,
                target_subset=approved.target_subset,
                release_split=item.split,
                benchmark_id=benchmark_item.benchmark_id if benchmark_item else None,
                benchmark_split=benchmark_item.benchmark_split if benchmark_item else None,
                tasks=list(approved.tasks),
                planned_transcription=approved.planned_transcription,
                planned_layout_labels=approved.planned_layout_labels,
                rationale=approved.rationale,
            )
        )
        audit.append(
            AnnotationPilotSelectionAuditRecord(
                pilot_id=config.pilot_id,
                item_id=item.item_id,
                outcome="selected",
                reason="explicitly_approved_release_ready_annotation_pilot_item",
                target_subset=approved.target_subset,
            )
        )

    selected.sort(key=lambda item: (item.target_subset, item.release_split, item.source_id, item.item_id))
    audit.sort(key=lambda item: item.item_id)
    manifest = AnnotationPilotManifestRecord(
        pilot_id=config.pilot_id,
        version=config.version,
        description=config.description,
        selection_policy=config.selection_policy,
        annotation_guidance=config.annotation_guidance,
        transcription_required_for_release=config.transcription_required_for_release,
        layout_labels_required_for_release=config.layout_labels_required_for_release,
        pilot_item_count=len(selected),
        transcription_task_count=sum(1 for item in selected if "transcription" in item.tasks),
        layout_label_task_count=sum(1 for item in selected if "layout_labels" in item.tasks),
        items=selected,
    )
    return AnnotationPilotSelectionOutputs(config=config, manifest=manifest, audit=audit)
