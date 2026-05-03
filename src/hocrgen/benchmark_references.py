from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from hocrgen.benchmark import BENCHMARK_ID, packaged_benchmark_data_root, resolve_benchmark_data_root
from hocrgen.config.loader import load_json_file
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    BenchmarkItemRecord,
    BenchmarkLayoutReferenceRecord,
    BenchmarkReferenceManifestItemRecord,
    BenchmarkReferenceManifestRecord,
    BenchmarkReferenceStatusArtifactRecord,
    BenchmarkReferenceStatusItemRecord,
    BenchmarkTranscriptionReferenceRecord,
    PrivacyScannedItemRecord,
)


REFERENCE_MANIFEST_NAME = "reference_manifest.json"


@dataclass(frozen=True)
class BenchmarkReferenceOutputs:
    manifest: BenchmarkReferenceManifestRecord | None
    status_artifact: BenchmarkReferenceStatusArtifactRecord
    transcription_references: list[BenchmarkTranscriptionReferenceRecord]
    layout_references: list[BenchmarkLayoutReferenceRecord]
    versioning_report: dict[str, Any]


def resolve_benchmark_reference_manifest_path(
    config_root: Path,
    benchmark_id: str = BENCHMARK_ID,
) -> Path | None:
    root = resolve_benchmark_data_root(config_root, benchmark_id) / benchmark_id
    candidates = [
        root / "references" / REFERENCE_MANIFEST_NAME,
        root / REFERENCE_MANIFEST_NAME,
    ]
    packaged_root = packaged_benchmark_data_root() / benchmark_id
    for candidate in [
        *candidates,
        packaged_root / "references" / REFERENCE_MANIFEST_NAME,
        packaged_root / REFERENCE_MANIFEST_NAME,
    ]:
        if candidate.exists():
            return candidate
    return None


def load_benchmark_reference_manifest(
    config_root: Path,
    benchmark_id: str = BENCHMARK_ID,
) -> tuple[BenchmarkReferenceManifestRecord | None, Path | None]:
    manifest_path = resolve_benchmark_reference_manifest_path(config_root, benchmark_id)
    if manifest_path is None:
        return None, None
    try:
        manifest = BenchmarkReferenceManifestRecord.model_validate(load_json_file(manifest_path))
    except ValidationError as exc:
        raise ConfigValidationError(
            f"benchmark reference manifest validation failed for {manifest_path}",
            details=exc.errors(),
        ) from exc
    if manifest.benchmark_id != benchmark_id:
        raise ConfigValidationError(
            f"benchmark reference manifest id mismatch for {manifest_path}",
            details=[{"expected": benchmark_id, "actual": manifest.benchmark_id}],
        )
    return manifest, manifest_path


def ingest_benchmark_references(
    *,
    config_root: Path,
    benchmark_items: list[BenchmarkItemRecord],
    release_ready_items: list[PrivacyScannedItemRecord],
    benchmark_id: str = BENCHMARK_ID,
) -> BenchmarkReferenceOutputs:
    manifest, manifest_path = load_benchmark_reference_manifest(config_root, benchmark_id)
    if manifest is None or manifest_path is None or not benchmark_items:
        return _empty_outputs(benchmark_id, benchmark_items)

    benchmark_by_id = {item.item_id: item for item in benchmark_items}
    release_ready_by_id = {item.item_id: item for item in release_ready_items}
    for item in manifest.items:
        benchmark_item = benchmark_by_id.get(item.item_id)
        if benchmark_item is None:
            raise StageExecutionError(
                f"benchmark reference manifest item {item.item_id} is not selected in {benchmark_id}"
            )
        _validate_manifest_item_linkage(item, benchmark_item)

    manifest_root = manifest_path.parent
    transcription_references: list[BenchmarkTranscriptionReferenceRecord] = []
    layout_references: list[BenchmarkLayoutReferenceRecord] = []
    for item in manifest.items:
        release_item = release_ready_by_id.get(item.item_id)
        if release_item is None:
            raise StageExecutionError(f"benchmark reference manifest item {item.item_id} is not release-ready")
        if item.transcription_reference is not None:
            transcription = _load_transcription_reference(manifest_root, item)
            _validate_child_linkage(transcription, item)
            transcription_references.append(transcription)
        for layout_ref in item.layout_label_references:
            layout = _load_layout_reference(manifest_root, item, layout_ref.path)
            _validate_child_linkage(layout, item)
            _validate_layout_assets(layout, release_item)
            if layout_ref.page_ids:
                actual_page_ids = {asset.page_id for asset in layout.assets}
                missing = set(layout_ref.page_ids) - actual_page_ids
                if missing:
                    raise StageExecutionError(
                        f"benchmark layout reference {layout_ref.path} missing declared page ids: {', '.join(sorted(missing))}"
                    )
            layout_references.append(layout)

    versioning_report = _validate_versioning(manifest)
    status_artifact = build_benchmark_reference_status_artifact(
        benchmark_id=benchmark_id,
        reference_manifest=manifest,
        benchmark_items=benchmark_items,
    )
    return BenchmarkReferenceOutputs(
        manifest=manifest,
        status_artifact=status_artifact,
        transcription_references=transcription_references,
        layout_references=layout_references,
        versioning_report=versioning_report,
    )


def build_benchmark_reference_status_artifact(
    *,
    benchmark_id: str,
    reference_manifest: BenchmarkReferenceManifestRecord | None,
    benchmark_items: list[BenchmarkItemRecord],
) -> BenchmarkReferenceStatusArtifactRecord:
    manifest_by_id = {item.item_id: item for item in reference_manifest.items} if reference_manifest else {}
    status_items: list[BenchmarkReferenceStatusItemRecord] = []
    for benchmark_item in sorted(benchmark_items, key=lambda item: item.item_id):
        reference_item = manifest_by_id.get(benchmark_item.item_id)
        if reference_item is None:
            status_items.append(
                BenchmarkReferenceStatusItemRecord(
                    item_id=benchmark_item.item_id,
                    source_id=benchmark_item.source_id,
                    source_item_id=benchmark_item.source_item_id,
                    benchmark_split=benchmark_item.benchmark_split,
                    public_reference_status="not_available",
                    adjudication_status="not_started",
                    has_transcription_reference=False,
                    layout_reference_count=0,
                    reviewer_count=0,
                )
            )
            continue
        status_items.append(
            BenchmarkReferenceStatusItemRecord(
                item_id=benchmark_item.item_id,
                source_id=benchmark_item.source_id,
                source_item_id=benchmark_item.source_item_id,
                benchmark_split=benchmark_item.benchmark_split,
                visibility=reference_item.visibility,
                public_reference_status=reference_item.public_reference_status,
                adjudication_status=reference_item.adjudication_status,
                has_transcription_reference=reference_item.transcription_reference is not None,
                layout_reference_count=len(reference_item.layout_label_references),
                reviewer_count=len(reference_item.reviewers),
                correction_of=reference_item.correction_of,
                superseded_by=reference_item.superseded_by,
                change_reason=reference_item.change_reason,
            )
        )
    counts = Counter(item.public_reference_status for item in status_items)
    for item in status_items:
        counts[f"adjudication_{item.adjudication_status}"] += 1
    counts["reference_ready"] = sum(
        1
        for item in status_items
        if item.public_reference_status in {"reviewed", "adjudicated"} and item.adjudication_status == "adjudicated"
    )
    counts["blocked_or_draft"] = sum(
        1
        for item in status_items
        if item.public_reference_status in {"draft", "not_available"} or item.adjudication_status == "blocked"
    )
    return BenchmarkReferenceStatusArtifactRecord(
        benchmark_id=benchmark_id,
        reference_manifest_id=reference_manifest.reference_manifest_id if reference_manifest else None,
        counts=dict(counts),
        items=status_items,
    )


def _empty_outputs(
    benchmark_id: str,
    benchmark_items: list[BenchmarkItemRecord],
) -> BenchmarkReferenceOutputs:
    return BenchmarkReferenceOutputs(
        manifest=None,
        status_artifact=build_benchmark_reference_status_artifact(
            benchmark_id=benchmark_id,
            reference_manifest=None,
            benchmark_items=benchmark_items,
        ),
        transcription_references=[],
        layout_references=[],
        versioning_report={
            "benchmark_id": benchmark_id,
            "reference_manifest_id": None,
            "status": "not_available",
            "checked_count": 0,
            "events": [],
            "policy": "Benchmark references are optional for current public and alpha exports.",
        },
    )


def _resolve_reference_path(manifest_root: Path, reference_path: str) -> Path:
    candidate = manifest_root / reference_path
    if candidate.exists():
        return candidate
    fallback = manifest_root / Path(reference_path).name
    if fallback.exists():
        return fallback
    return candidate


def _load_transcription_reference(
    manifest_root: Path,
    item: BenchmarkReferenceManifestItemRecord,
) -> BenchmarkTranscriptionReferenceRecord:
    assert item.transcription_reference is not None
    path = _resolve_reference_path(manifest_root, item.transcription_reference.path)
    try:
        return BenchmarkTranscriptionReferenceRecord.model_validate(load_json_file(path))
    except (ConfigValidationError, ValidationError) as exc:
        raise StageExecutionError(f"benchmark transcription reference validation failed for {path}: {exc}") from exc


def _load_layout_reference(
    manifest_root: Path,
    item: BenchmarkReferenceManifestItemRecord,
    reference_path: str,
) -> BenchmarkLayoutReferenceRecord:
    del item
    path = _resolve_reference_path(manifest_root, reference_path)
    try:
        return BenchmarkLayoutReferenceRecord.model_validate(load_json_file(path))
    except (ConfigValidationError, ValidationError) as exc:
        raise StageExecutionError(f"benchmark layout reference validation failed for {path}: {exc}") from exc


def _validate_manifest_item_linkage(
    reference_item: BenchmarkReferenceManifestItemRecord,
    benchmark_item: BenchmarkItemRecord,
) -> None:
    mismatches = []
    for field_name in ("source_id", "source_item_id", "benchmark_split"):
        expected = getattr(benchmark_item, field_name)
        actual = getattr(reference_item, field_name)
        if actual is not None and actual != expected:
            mismatches.append(f"{field_name}: expected {expected}, got {actual}")
    if mismatches:
        raise StageExecutionError(
            f"benchmark reference item {reference_item.item_id} linkage mismatch: {'; '.join(mismatches)}"
        )


def _validate_child_linkage(
    reference: BenchmarkTranscriptionReferenceRecord | BenchmarkLayoutReferenceRecord,
    manifest_item: BenchmarkReferenceManifestItemRecord,
) -> None:
    mismatches = []
    for field_name in ("item_id", "source_id", "source_item_id"):
        expected = getattr(manifest_item, field_name)
        actual = getattr(reference, field_name)
        if actual != expected:
            mismatches.append(f"{field_name}: expected {expected}, got {actual}")
    if mismatches:
        raise StageExecutionError(
            f"benchmark reference child for {manifest_item.item_id} linkage mismatch: {'; '.join(mismatches)}"
        )


def _validate_layout_assets(
    layout: BenchmarkLayoutReferenceRecord,
    release_item: PrivacyScannedItemRecord,
) -> None:
    normalized_assets = {
        (asset.sha256, asset.width, asset.height)
        for asset in release_item.normalized_assets
    }
    for asset in layout.assets:
        if (asset.sha256, asset.width, asset.height) not in normalized_assets:
            raise StageExecutionError(
                "benchmark layout reference asset mismatch for "
                f"{layout.item_id} page {asset.page_id}: sha256/dimensions do not match current normalized assets"
            )


def _validate_versioning(manifest: BenchmarkReferenceManifestRecord) -> dict[str, Any]:
    items_by_id = {item.item_id: item for item in manifest.items}
    events: list[dict[str, str]] = []
    errors: list[str] = []
    for item in manifest.items:
        if item.correction_of:
            prior = items_by_id.get(item.correction_of)
            if prior is None:
                errors.append(f"{item.item_id} correction_of points to missing {item.correction_of}")
            elif prior.superseded_by != item.item_id:
                errors.append(f"{item.item_id} correction_of does not match superseded_by on {item.correction_of}")
            events.append({"item_id": item.item_id, "event": "correction", "reason": item.change_reason or ""})
        if item.superseded_by:
            replacement = items_by_id.get(item.superseded_by)
            if replacement is None:
                errors.append(f"{item.item_id} superseded_by points to missing {item.superseded_by}")
            elif replacement.correction_of != item.item_id:
                errors.append(f"{item.item_id} superseded_by does not match correction_of on {item.superseded_by}")
            events.append({"item_id": item.item_id, "event": "superseded", "reason": item.change_reason or ""})
        if item.public_reference_status == "retired":
            events.append({"item_id": item.item_id, "event": "retirement", "reason": item.change_reason or ""})
    if errors:
        raise StageExecutionError(f"benchmark reference versioning validation failed: {'; '.join(errors)}")
    return {
        "benchmark_id": manifest.benchmark_id,
        "reference_manifest_id": manifest.reference_manifest_id,
        "status": "ok",
        "checked_count": len(manifest.items),
        "event_count": len(events),
        "events": events,
        "policy": (
            "Public benchmark references require explicit correction, supersession, retirement, "
            "or change reasons for versioning events."
        ),
    }
