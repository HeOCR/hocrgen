from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Iterable, Literal

from pydantic import ValidationError

from hocrgen.config.loader import load_json_file
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import AlphaExportedItemRecord, AnnotationManifestRecord, BenchmarkItemRecord


@dataclass(frozen=True)
class BenchmarkExample:
    benchmark_id: str
    item_id: str
    source_id: str
    benchmark_split: Literal["train", "validation", "test"]
    title: str | None
    is_synthetic: bool
    content_class: Literal["handwritten", "printed", "mixed"]
    quality_tier: Literal["low", "medium", "high"]
    asset_paths: tuple[str, ...] = ()
    transcription_path: str | None = None

    @property
    def has_reference(self) -> bool:
        return self.transcription_path is not None


@dataclass(frozen=True)
class TextMetricResult:
    item_id: str
    prediction: str
    reference: str
    edit_distance: int
    reference_char_count: int
    char_error_rate: float | None
    exact_match: bool


def load_benchmark_examples(
    benchmark_manifest_path: Path,
    *,
    item_manifest_path: Path | None = None,
    annotation_manifest_path: Path | None = None,
) -> list[BenchmarkExample]:
    benchmark_items = _load_benchmark_manifest(benchmark_manifest_path)
    exported_items = _load_exported_items(item_manifest_path) if item_manifest_path is not None else {}
    annotation_items = _load_annotation_items(annotation_manifest_path) if annotation_manifest_path is not None else {}

    examples: list[BenchmarkExample] = []
    for item in benchmark_items:
        exported = exported_items.get(item.item_id)
        annotation = annotation_items.get(item.item_id)
        asset_paths = (
            tuple(validate_release_relative_path(asset.release_asset_path) for asset in exported.exported_assets)
            if exported
            else ()
        )
        transcription_path = (
            validate_release_relative_path(annotation.transcription.path)
            if annotation and annotation.transcription
            else None
        )
        examples.append(
            BenchmarkExample(
                benchmark_id=item.benchmark_id,
                item_id=item.item_id,
                source_id=item.source_id,
                benchmark_split=item.benchmark_split,
                title=item.title,
                is_synthetic=item.is_synthetic,
                content_class=item.content_class,
                quality_tier=item.quality_tier,
                asset_paths=asset_paths,
                transcription_path=transcription_path,
            )
        )
    return examples


def summarize_benchmark_examples(examples: Iterable[BenchmarkExample]) -> dict[str, Any]:
    example_list = list(examples)
    split_counts = _count_by(example.benchmark_split for example in example_list)
    content_class_counts = _count_by(example.content_class for example in example_list)
    quality_tier_counts = _count_by(example.quality_tier for example in example_list)
    return {
        "item_count": len(example_list),
        "reference_item_count": sum(1 for example in example_list if example.has_reference),
        "synthetic_item_count": sum(1 for example in example_list if example.is_synthetic),
        "real_item_count": sum(1 for example in example_list if not example.is_synthetic),
        "split_counts": split_counts,
        "content_class_counts": content_class_counts,
        "quality_tier_counts": quality_tier_counts,
    }


def evaluate_text_predictions(
    examples: Iterable[BenchmarkExample],
    *,
    predictions: dict[str, str],
    references: dict[str, str],
) -> dict[str, Any]:
    example_list = list(examples)
    example_ids = {example.item_id for example in example_list}
    results: list[TextMetricResult] = []
    missing_predictions: list[str] = []
    missing_references: list[str] = []

    for example in example_list:
        prediction = predictions.get(example.item_id)
        reference = references.get(example.item_id)
        if prediction is None:
            missing_predictions.append(example.item_id)
            continue
        if reference is None:
            missing_references.append(example.item_id)
            continue
        results.append(score_text_pair(example.item_id, prediction=prediction, reference=reference))

    unexpected_predictions = sorted(set(predictions) - example_ids)
    unexpected_references = sorted(set(references) - example_ids)
    total_edit_distance = sum(result.edit_distance for result in results)
    total_reference_chars = sum(result.reference_char_count for result in results)
    exact_matches = sum(1 for result in results if result.exact_match)
    char_error_rate = _ratio(total_edit_distance, total_reference_chars)
    return {
        "benchmark_item_count": len(example_list),
        "prediction_count": len(predictions),
        "reference_count": len(references),
        "evaluated_item_count": len(results),
        "prediction_coverage": _ratio(len(example_list) - len(missing_predictions), len(example_list)),
        "reference_coverage": _ratio(len(example_list) - len(missing_references), len(example_list)),
        "char_error_rate": char_error_rate,
        "exact_match_rate": _ratio(exact_matches, len(results)),
        "missing_predictions": sorted(missing_predictions),
        "missing_references": sorted(missing_references),
        "unexpected_predictions": unexpected_predictions,
        "unexpected_references": unexpected_references,
        "items": [_dump_metric_result(result) for result in sorted(results, key=lambda result: result.item_id)],
        "leaderboard_ready": {
            "schema_version": 1,
            "primary_metric": "char_error_rate",
            "lower_is_better": True,
            "requires_full_prediction_coverage": True,
            "requires_full_reference_coverage": True,
            "ready": bool(example_list)
            and len(results) == len(example_list)
            and char_error_rate is not None
            and not unexpected_predictions
            and not unexpected_references,
        },
    }


def score_text_pair(item_id: str, *, prediction: str, reference: str) -> TextMetricResult:
    edit_distance = levenshtein_distance(prediction, reference)
    return TextMetricResult(
        item_id=item_id,
        prediction=prediction,
        reference=reference,
        edit_distance=edit_distance,
        reference_char_count=len(reference),
        char_error_rate=_ratio(edit_distance, len(reference)),
        exact_match=prediction == reference,
    )


def levenshtein_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[right_index] + 1,
                    current[right_index - 1] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def load_text_records(path: Path, *, value_field: str = "text") -> dict[str, str]:
    records = _load_records(path)
    loaded: dict[str, str] = {}
    for index, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            raise StageExecutionError(f"{path} record {index} must be an object")
        item_id = record.get("item_id")
        value = record.get(value_field)
        if not isinstance(item_id, str) or not item_id:
            raise StageExecutionError(f"{path} record {index} must include non-empty string 'item_id'")
        if not isinstance(value, str):
            raise StageExecutionError(f"{path} record {index} must include string '{value_field}'")
        if item_id in loaded:
            raise StageExecutionError(f"{path} contains duplicate item_id: {item_id}")
        loaded[item_id] = value
    return loaded


def _load_records(path: Path) -> list[Any]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        records: list[Any] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise StageExecutionError(f"evaluation records at {path} could not be read: {exc}") from exc
        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise StageExecutionError(f"{path} line {line_number} is not valid JSON") from exc
        return records

    payload = _load_evaluation_json(path, "evaluation records")
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return payload["items"]
    raise StageExecutionError(f"{path} must be JSONL, a JSON list, or a JSON object with list 'items'")


def _load_benchmark_manifest(path: Path) -> list[BenchmarkItemRecord]:
    try:
        payload = _load_evaluation_json(path, "benchmark manifest")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise StageExecutionError(f"benchmark manifest at {path} must contain a list 'items'")
        return [BenchmarkItemRecord.model_validate(item) for item in items]
    except ValidationError as exc:
        raise StageExecutionError(f"benchmark manifest at {path} is invalid") from exc


def _load_exported_items(path: Path) -> dict[str, AlphaExportedItemRecord]:
    try:
        payload = _load_evaluation_json(path, "item manifest")
        items = payload.get("items") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            raise StageExecutionError(f"item manifest at {path} must contain a list 'items'")
        records = [AlphaExportedItemRecord.model_validate(item) for item in items]
    except ValidationError as exc:
        raise StageExecutionError(f"item manifest at {path} is invalid") from exc
    return _unique_by_item_id(records, path)


def _load_annotation_items(path: Path) -> dict[str, Any]:
    try:
        manifest = AnnotationManifestRecord.model_validate(_load_evaluation_json(path, "annotation manifest"))
    except ValidationError as exc:
        raise StageExecutionError(f"annotation manifest at {path} is invalid") from exc
    return _unique_by_item_id(manifest.items, path)


def _load_evaluation_json(path: Path, label: str) -> Any:
    try:
        return load_json_file(path)
    except ConfigValidationError as exc:
        raise StageExecutionError(f"{label} at {path} could not be loaded: {exc}") from exc
    except OSError as exc:
        raise StageExecutionError(f"{label} at {path} could not be read: {exc}") from exc


def _unique_by_item_id(records: Iterable[Any], path: Path) -> dict[str, Any]:
    loaded: dict[str, Any] = {}
    for record in records:
        if record.item_id in loaded:
            raise StageExecutionError(f"{path} contains duplicate item_id: {record.item_id}")
        loaded[record.item_id] = record
    return loaded


def _count_by(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _dump_metric_result(result: TextMetricResult) -> dict[str, Any]:
    return {
        "item_id": result.item_id,
        "edit_distance": result.edit_distance,
        "reference_char_count": result.reference_char_count,
        "char_error_rate": result.char_error_rate,
        "exact_match": result.exact_match,
    }


def validate_release_relative_path(path: str) -> str:
    parsed = PurePosixPath(path)
    if (
        not path
        or path != path.strip()
        or "\\" in path
        or "://" in path
        or re.match(r"^[A-Za-z]:", path)
        or parsed.is_absolute()
        or ".work" in parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise StageExecutionError(f"benchmark example path is not release-relative and portable: {path}")
    return path
