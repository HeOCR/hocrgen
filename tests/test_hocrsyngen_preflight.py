from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.cli import main
from hocrgen.core.errors import StageExecutionError
from hocrgen.synthetic.hocrsyngen_preflight import run_hocrsyngen_preflight
from hocrgen.utils.hashing import sha256_file


def test_hocrsyngen_preflight_reads_evidence_root_and_writes_diagnostic_report(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    report_path = tmp_path / "hocrgen_preflight_report.json"

    result = run_hocrsyngen_preflight(evidence_root, report_path=report_path)

    report = result.report
    assert result.report_path == report_path
    assert report_path.is_file()
    assert report["schema_version"] == "hocrgen_hocrsyngen_preflight_report.v1"
    assert report["planning_notation"] == "F6f2a"
    assert report["artifact_scope"] == "operator_only"
    assert report["release_eligible"] is False
    assert report["manifest"]["sample_count"] == 1
    assert report["manifest"]["page_count"] == 1
    assert report["manifest"]["missing_hocrgen_release_import_metadata"] == [
        "provider_metadata",
        "samples[].rendering_metadata",
        "samples[].hebrew_coverage",
    ]
    assert report["assets"]["checks"][0]["asset_path"] == "assets/hocrsyngen-s00000101-000000/page_0001.jpg"
    assert report["template_catalog"]["joined_sample_count"] == 1
    assert report["template_catalog"]["missing_join_count"] == 0
    assert report["rendering_coverage_report"]["present"] is True

    written_report = json.loads(report_path.read_text(encoding="utf-8"))
    assert written_report["release_eligible"] is False
    assert any("does not change project_synthetic" in non_goal for non_goal in written_report["non_goals"])


def test_hocrsyngen_preflight_cli_reports_expected_candidate_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    report_path = tmp_path / "cli_report.json"

    exit_code = main(
        [
            "hocrsyngen-preflight",
            "--evidence-root",
            str(evidence_root),
            "--report",
            str(report_path),
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["release_eligible"] is False
    assert payload["sample_count"] == 1
    assert payload["page_count"] == 1
    assert payload["missing_hocrgen_release_import_metadata"] == [
        "provider_metadata",
        "samples[].rendering_metadata",
        "samples[].hebrew_coverage",
    ]
    assert report_path.is_file()


def test_hocrsyngen_preflight_rejects_unsafe_asset_paths(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, asset_path="../escape.jpg")

    with pytest.raises(StageExecutionError, match="relative portable POSIX path"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_rejects_asset_hash_mismatch(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, page_sha256="0" * 64)

    with pytest.raises(StageExecutionError, match="page asset sha256 mismatch"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_rejects_missing_template_catalog_join(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, catalog_recipe_id="different_recipe_v1")

    with pytest.raises(StageExecutionError, match="does not join to template_catalog.v2"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


@pytest.mark.parametrize(
    ("field", "replacement", "expected_error"),
    [
        ("output_path", "other_batch", "generation_report.v1 output_path must resolve"),
        ("manifest_path", "generated_batch/other_manifest.json", "generation_report.v1 manifest_path must resolve"),
        (
            "rendering_coverage_report_path",
            "generated_batch/other_rendering_coverage_report.json",
            "rendering_coverage_report_path must match",
        ),
    ],
)
def test_hocrsyngen_preflight_rejects_stale_generation_report_paths(
    tmp_path: Path,
    field: str,
    replacement: str,
    expected_error: str,
) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_embedded_report(evidence_root, "generation", lambda payload: payload.update({field: str(evidence_root / replacement)}))

    with pytest.raises(StageExecutionError, match=expected_error):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_rejects_stale_validation_report_path(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_embedded_report(
        evidence_root,
        "generated_validation",
        lambda payload: payload.update({"path": str(evidence_root / "other_batch")}),
    )

    with pytest.raises(StageExecutionError, match="validation_report.v1 path must resolve"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_rejects_evidence_count_mismatch(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_candidate_report(evidence_root, lambda payload: payload.update({"count": 2}))

    with pytest.raises(StageExecutionError, match="candidate evidence count must match manifest sample count"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_rejects_evidence_seed_mismatch(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_candidate_report(evidence_root, lambda payload: payload.update({"seed": 202}))

    with pytest.raises(StageExecutionError, match="candidate evidence seed must match every manifest sample"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_refuses_report_overwrite(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    report_path = tmp_path / "report.json"
    report_path.write_text("{}", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="already exists"):
        run_hocrsyngen_preflight(evidence_root, report_path=report_path)


def _write_evidence_root(
    tmp_path: Path,
    *,
    asset_path: str = "assets/hocrsyngen-s00000101-000000/page_0001.jpg",
    page_sha256: str | None = None,
    catalog_recipe_id: str = "printed_letter_form_v1",
) -> Path:
    root = tmp_path / "evidence"
    generated_batch = root / "generated_batch"
    reports_dir = root / "reports"
    fixture_batch = root / "fixture_batch"
    generated_batch.mkdir(parents=True)
    reports_dir.mkdir(parents=True)
    fixture_batch.mkdir(parents=True)

    if not asset_path.startswith("../"):
        image_path = generated_batch / Path(asset_path)
        image_path.parent.mkdir(parents=True, exist_ok=True)
        with Image.new("RGB", (12, 8), "white") as image:
            image.putpixel((2, 2), (0, 0, 0))
            image.save(image_path, format="JPEG")
        actual_page_sha256 = sha256_file(image_path)
    else:
        actual_page_sha256 = "1" * 64

    manifest = {
        "manifest_version": "1.0",
        "generator_name": "hocrsyngen",
        "license": "PROJECT-SYNTHETIC",
        "samples": [
            {
                "sample_id": "hocrsyngen-s00000101-000000",
                "pages": [
                    {
                        "page_id": "hocrsyngen-s00000101-000000-page-0001",
                        "asset_path": asset_path,
                        "media_type": "image/jpeg",
                        "sha256": page_sha256 or actual_page_sha256,
                        "width": 12,
                        "height": 8,
                    }
                ],
                "text": {
                    "logical_order": "שלום עולם\nמספר 101",
                    "script": "Hebr",
                    "language": "he",
                    "direction": "rtl",
                    "unicode_normalization": "NFC",
                },
                "generator_version": "d4a-realism-v2",
                "recipe_id": "printed_letter_form_v1",
                "provenance": {
                    "seed": 101,
                    "sample_index": 0,
                    "template_id": "printed_letter",
                    "recipe_id": "printed_letter_form_v1",
                    "degradation_preset": "office_scan_soft",
                    "font_id": "alef-regular",
                    "source_corpus": "packaged:synthetic/texts/hebrew_lines.txt",
                },
                "license": "PROJECT-SYNTHETIC",
                "synthetic_disclosure": "Generated synthetic Hebrew OCR/HTR sample.",
                "controls": {"persona": None, "condition": None},
            }
        ],
    }
    _write_json(generated_batch / "generation_manifest.json", manifest)

    template_catalog_v2 = {
        "schema_version": "template_catalog.v2",
        "templates": [
            {
                "template_id": "printed_letter",
                "recipe_id": catalog_recipe_id,
                "layout_style": "printed_form",
                "font_style": "printed",
                "font_id": "alef-regular",
                "degradation_preset": "office_scan_soft",
                "document_family": "letter",
                "base_family": "printed_letter",
                "layout_density": "moderate",
            }
        ],
    }
    generation_report = {
        "schema_version": "generation_report.v1",
        "sample_count": 1,
        "page_count": 1,
        "output_path": str(generated_batch),
        "manifest_path": str(generated_batch / "generation_manifest.json"),
        "rendering_coverage_report_path": str(generated_batch / "rendering_coverage_report.json"),
    }
    validation_report = {
        "schema_version": "validation_report.v1",
        "valid": True,
        "sample_count": 1,
        "page_count": 1,
        "path": str(generated_batch),
    }
    rendering_coverage = {
        "batch": {"manifest_path": "generation_manifest.json", "sample_count": 1, "page_count": 1},
        "coverage": {"asset_smoke": {"covered": ["readable_jpeg"], "missing": []}},
    }
    _write_json(reports_dir / "template_catalog_v2.json", template_catalog_v2)
    _write_json(reports_dir / "generation_report.json", generation_report)
    _write_json(reports_dir / "generated_validation_report.json", validation_report)
    _write_json(generated_batch / "rendering_coverage_report.json", rendering_coverage)
    (root / "RUN_NOTES.md").write_text("# hocrsyngen evidence run\n", encoding="utf-8")

    _write_sha256s(root)

    candidate_report = {
        "schema_version": "candidate_evidence_run_report.v1",
        "started_at_utc": "2026-05-08T16:20:16Z",
        "completed_at_utc": "2026-05-08T16:20:18Z",
        "release_eligible": False,
        "count": 1,
        "seed": 101,
        "generator_version": "d4a-realism-v2",
        "output_root": str(root),
        "reports_dir": str(reports_dir),
        "fixture_batch_path": str(fixture_batch),
        "generated_batch_path": str(generated_batch),
        "generated_manifest_path": str(generated_batch / "generation_manifest.json"),
        "checksums_path": str(root / "SHA256SUMS"),
        "rendering_coverage_report_path": str(generated_batch / "rendering_coverage_report.json"),
        "reports": {
            "template_catalog_v2": template_catalog_v2,
            "generation": generation_report,
            "generated_validation": validation_report,
        },
    }
    _write_json(root / "candidate_evidence_run_report.json", candidate_report)
    return root


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _update_embedded_report(evidence_root: Path, key: str, mutate: Callable[[dict], None]) -> None:
    report_paths = {
        "generation": evidence_root / "reports" / "generation_report.json",
        "generated_validation": evidence_root / "reports" / "generated_validation_report.json",
    }
    path = report_paths[key]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    mutate(payload)
    _write_json(path, payload)
    _update_candidate_report(evidence_root, lambda candidate: candidate["reports"].update({key: payload}))


def _update_candidate_report(evidence_root: Path, mutate: Callable[[dict], None]) -> None:
    path = evidence_root / "candidate_evidence_run_report.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    mutate(payload)
    _write_json(path, payload)


def _write_sha256s(root: Path) -> None:
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
