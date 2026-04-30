from __future__ import annotations

import json
from pathlib import Path

import pytest

from hocrgen.cli import main
from hocrgen.core.errors import StageExecutionError
from hocrgen.evaluation import (
    evaluate_text_predictions,
    levenshtein_distance,
    load_benchmark_examples,
    load_text_records,
    score_text_pair,
    summarize_benchmark_examples,
)


def test_load_benchmark_examples_summarizes_manifest_with_annotation_availability(tmp_path: Path) -> None:
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    annotation_manifest = tmp_path / "annotation_manifest.json"
    _write_benchmark_manifest(benchmark_manifest)
    annotation_manifest.write_text(
        json.dumps(
            {
                "annotated_item_count": 1,
                "items": [
                    {
                        "annotation_status": "available",
                        "item_id": "pinkas_open:pinkas-ledger-001",
                        "source_id": "pinkas_open",
                        "split": "train",
                        "transcription": {
                            "path": "annotations/pinkas_open/pinkas-ledger-001/transcription.json",
                            "schema_id": "hocrgen_transcription_v1",
                        },
                    }
                ],
                "layout_label_item_count": 0,
                "subset_id": "benchmark_v1",
                "transcription_item_count": 1,
            }
        ),
        encoding="utf-8",
    )

    examples = load_benchmark_examples(benchmark_manifest, annotation_manifest_path=annotation_manifest)
    summary = summarize_benchmark_examples(examples)

    assert [example.item_id for example in examples] == [
        "pinkas_open:pinkas-ledger-001",
        "project_synthetic:synthetic-0",
    ]
    assert examples[0].has_reference is True
    assert examples[1].has_reference is False
    assert summary["item_count"] == 2
    assert summary["reference_item_count"] == 1
    assert summary["synthetic_item_count"] == 1
    assert summary["split_counts"] == {"train": 2}


def test_load_benchmark_examples_rejects_non_portable_annotation_paths(tmp_path: Path) -> None:
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    annotation_manifest = tmp_path / "annotation_manifest.json"
    _write_benchmark_manifest(benchmark_manifest)
    annotation_manifest.write_text(
        json.dumps(
            {
                "annotated_item_count": 1,
                "items": [
                    {
                        "annotation_status": "available",
                        "item_id": "pinkas_open:pinkas-ledger-001",
                        "source_id": "pinkas_open",
                        "split": "train",
                        "transcription": {
                            "path": "/tmp/transcription.json",
                            "schema_id": "hocrgen_transcription_v1",
                        },
                    }
                ],
                "layout_label_item_count": 0,
                "subset_id": "benchmark_v1",
                "transcription_item_count": 1,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(StageExecutionError, match="annotation manifest"):
        load_benchmark_examples(benchmark_manifest, annotation_manifest_path=annotation_manifest)


def test_text_metric_helpers_compute_cer_and_exact_match() -> None:
    assert levenshtein_distance("abc", "axc") == 1

    result = score_text_pair("item-1", prediction="שלום", reference="שלם")

    assert result.edit_distance == 1
    assert result.reference_char_count == 3
    assert result.char_error_rate == pytest.approx(1 / 3)
    assert result.exact_match is False


def test_evaluate_text_predictions_reports_coverage_and_leaderboard_status(tmp_path: Path) -> None:
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    _write_benchmark_manifest(benchmark_manifest)
    examples = load_benchmark_examples(benchmark_manifest)

    report = evaluate_text_predictions(
        examples,
        predictions={
            "pinkas_open:pinkas-ledger-001": "abc",
            "project_synthetic:synthetic-0": "xyz",
            "unexpected:item": "ignored",
        },
        references={
            "pinkas_open:pinkas-ledger-001": "abc",
        },
    )

    assert report["evaluated_item_count"] == 1
    assert report["char_error_rate"] == 0
    assert report["exact_match_rate"] == 1
    assert report["missing_references"] == ["project_synthetic:synthetic-0"]
    assert report["unexpected_predictions"] == ["unexpected:item"]
    assert report["leaderboard_ready"]["ready"] is False


def test_load_text_records_accepts_jsonl_and_rejects_duplicates(tmp_path: Path) -> None:
    records = tmp_path / "predictions.jsonl"
    records.write_text(
        "\n".join(
            [
                json.dumps({"item_id": "item-1", "text": "abc"}),
                json.dumps({"item_id": "item-2", "text": "def"}),
            ]
        ),
        encoding="utf-8",
    )

    assert load_text_records(records) == {"item-1": "abc", "item-2": "def"}

    records.write_text(
        "\n".join(
            [
                json.dumps({"item_id": "item-1", "text": "abc"}),
                json.dumps({"item_id": "item-1", "text": "def"}),
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(StageExecutionError, match="duplicate item_id"):
        load_text_records(records)


def test_evaluate_benchmark_cli_writes_report(tmp_path: Path, capsys) -> None:
    benchmark_manifest = tmp_path / "benchmark_manifest.json"
    predictions = tmp_path / "predictions.jsonl"
    references = tmp_path / "references.jsonl"
    output = tmp_path / "reports" / "evaluation.json"
    _write_benchmark_manifest(benchmark_manifest)
    predictions.write_text(
        "\n".join(
            [
                json.dumps({"item_id": "pinkas_open:pinkas-ledger-001", "text": "אבג"}),
                json.dumps({"item_id": "project_synthetic:synthetic-0", "text": "דהו"}),
            ]
        ),
        encoding="utf-8",
    )
    references.write_text(
        "\n".join(
            [
                json.dumps({"item_id": "pinkas_open:pinkas-ledger-001", "text": "אבג"}),
                json.dumps({"item_id": "project_synthetic:synthetic-0", "text": "דחו"}),
            ]
        ),
        encoding="utf-8",
    )

    exit_code = main(
        [
            "evaluate-benchmark",
            "--benchmark-manifest",
            str(benchmark_manifest),
            "--predictions",
            str(predictions),
            "--references",
            str(references),
            "--output",
            str(output),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    written = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["status"] == "ok"
    assert payload["metrics"]["evaluated_item_count"] == 2
    assert payload["metrics"]["char_error_rate"] == pytest.approx(1 / 6)
    assert written == payload


def _write_benchmark_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "benchmark_id": "benchmark_v1",
                        "benchmark_split": "train",
                        "content_class": "printed",
                        "is_synthetic": False,
                        "item_id": "pinkas_open:pinkas-ledger-001",
                        "normalized_license": "CC-BY-4.0",
                        "quality_tier": "high",
                        "rationale": "real exemplar",
                        "release_split": "train",
                        "rights_classification": "open",
                        "source_id": "pinkas_open",
                        "source_item_id": "pinkas-ledger-001",
                        "source_url": "https://example.org/pinkas",
                        "split_group_id": "source-item:pinkas_open:pinkas-ledger-001",
                        "title": "Pinkas page",
                    },
                    {
                        "benchmark_id": "benchmark_v1",
                        "benchmark_split": "train",
                        "content_class": "printed",
                        "is_synthetic": True,
                        "item_id": "project_synthetic:synthetic-0",
                        "normalized_license": "MIT",
                        "quality_tier": "high",
                        "rationale": "synthetic control",
                        "release_split": "train",
                        "rights_classification": "open",
                        "source_id": "project_synthetic",
                        "source_item_id": "synthetic-0",
                        "source_url": "https://example.org/synthetic",
                        "split_group_id": "source-item:project_synthetic:synthetic-0",
                        "title": "Synthetic page",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
