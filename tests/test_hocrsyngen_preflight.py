from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.cli import main
from hocrgen.core.errors import StageExecutionError
from hocrgen.synthetic.hocrsyngen_preflight import (
    HocrsyngenImportMetadataPacket,
    ImportLayoutFamilyPolicy,
    ImportProviderRuntimeContract,
    PublicGenerationManifest,
    _build_import_metadata_packet,
    _derive_batch_synthetic_disclosure,
    _release_import_model_validation_errors,
    _validate_import_metadata_packet,
    _write_json_temp,
    _write_preflight_artifacts,
    run_hocrsyngen_preflight,
)
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
    packet = report["hocrgen_import_metadata_packet"]
    assert packet["schema_version"] == "hocrgen_hocrsyngen_import_metadata_packet.v1"
    assert packet["planning_notation"] == "F6f2"
    assert packet["artifact_scope"] == "operator_only"
    assert packet["release_eligible"] is False
    assert packet["provider_metadata"] == {
        "provider_name": "hocrsyngen",
        "provider_version": "d4a-realism-v2",
        "generation_mode": "offline_manifest_batch",
        "runtime_contract": {
            "evidence_status": "not_provided_by_candidate_evidence_report",
            "source": None,
            "used_network": None,
            "used_rest_service": None,
            "used_gpu": None,
            "used_llm": None,
            "used_diffusion": None,
        },
    }
    assert packet["batch_metadata"]["synthetic_disclosure"] == "Generated synthetic Hebrew OCR/HTR sample."
    assert packet["samples"][0]["sample_id"] == "hocrsyngen-s00000101-000000"
    assert packet["samples"][0]["rendering_metadata"] == {
        "text_order": "logical",
        "page_direction": "rtl",
        "line_direction": "rtl",
        "bidi_handling": "logical_rtl_paragraphs",
        "font_shaping": "provider_shaped_hebrew_text",
        "layout_family": "printed_letter_form",
        "line_count": 2,
    }
    assert packet["samples"][0]["hebrew_coverage"] == {
        "has_arabic_numerals": True,
        "has_final_letters": True,
        "has_hebrew_letters": True,
        "has_mixed_ltr": False,
        "has_niqqud": False,
        "has_punctuation": True,
    }
    assert packet["validation"]["metadata_valid"] is True
    assert packet["validation"]["validated_against_hocrgen_release_import_model"] is False
    assert packet["validation"]["release_import_model_validation_errors"] == [
        "provider_runtime contract is not provided by candidate_evidence_run_report; "
        "used_network/used_rest_service/used_gpu/used_llm/used_diffusion remain unproven"
    ]

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
    assert payload["hocrgen_import_metadata_packet"]["metadata_valid"] is True
    assert payload["hocrgen_import_metadata_packet"]["release_import_model_valid"] is False
    assert payload["missing_hocrgen_release_import_metadata"] == [
        "provider_metadata",
        "samples[].rendering_metadata",
        "samples[].hebrew_coverage",
    ]
    assert report_path.is_file()


def test_hocrsyngen_preflight_writes_import_metadata_sidecar(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    report_path = tmp_path / "report.json"
    sidecar_path = tmp_path / "import_metadata_packet.json"

    result = run_hocrsyngen_preflight(
        evidence_root,
        report_path=report_path,
        metadata_sidecar_path=sidecar_path,
    )

    assert sidecar_path.is_file()
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar == result.report["hocrgen_import_metadata_packet"]
    assert result.report["hocrgen_import_metadata_sidecar"] == {
        "requested": True,
        "written": True,
        "path": str(sidecar_path.resolve()),
        "schema_version": "hocrgen_hocrsyngen_import_metadata_packet.v1",
        "release_eligible": False,
    }


def test_hocrsyngen_preflight_refuses_sidecar_report_path_collision(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    report_path = tmp_path / "same.json"

    with pytest.raises(StageExecutionError, match="sidecar path must differ"):
        run_hocrsyngen_preflight(evidence_root, report_path=report_path, metadata_sidecar_path=report_path)


def test_hocrsyngen_preflight_refuses_sidecar_overwrite(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    sidecar_path = tmp_path / "import_metadata_packet.json"
    sidecar_path.write_text("{}", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="import metadata sidecar already exists"):
        run_hocrsyngen_preflight(
            evidence_root,
            report_path=tmp_path / "report.json",
            metadata_sidecar_path=sidecar_path,
        )


def test_hocrsyngen_preflight_wraps_artifact_write_errors(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    sidecar_path = tmp_path / "sidecar.json"

    with pytest.raises(StageExecutionError, match="could not write hocrsyngen preflight report to"):
        run_hocrsyngen_preflight(
            evidence_root,
            report_path=tmp_path,
            metadata_sidecar_path=sidecar_path,
            overwrite=True,
        )
    assert not sidecar_path.exists()


def test_hocrsyngen_preflight_does_not_publish_report_when_sidecar_publish_fails(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    report_path = tmp_path / "report.json"

    with pytest.raises(StageExecutionError, match="could not write hocrsyngen import metadata sidecar to"):
        run_hocrsyngen_preflight(
            evidence_root,
            report_path=report_path,
            metadata_sidecar_path=tmp_path,
            overwrite=True,
        )
    assert not report_path.exists()


def test_hocrsyngen_write_json_temp_wraps_write_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_write_text(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    with pytest.raises(StageExecutionError, match="could not write test artifact to"):
        _write_json_temp(tmp_path / "artifact.json", {}, "test artifact")


def test_hocrsyngen_preflight_wraps_artifact_publish_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_replace = Path.replace

    def fail_report_replace(self: Path, target: Path) -> Path:
        if target == tmp_path / "report.json":
            raise OSError("rename failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_report_replace)

    with pytest.raises(StageExecutionError, match="could not publish hocrsyngen preflight artifacts"):
        _write_preflight_artifacts(tmp_path / "report.json", {}, tmp_path / "sidecar.json", {})


def test_hocrsyngen_preflight_sidecar_validation_ignores_public_manifest_extra_fields(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    manifest_path = evidence_root / "generated_batch" / "generation_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["public_future_field"] = "retained by public-boundary validation"
    payload["samples"][0]["public_future_sample_field"] = "retained by public-boundary validation"
    _write_json(manifest_path, payload)
    _write_sha256s(evidence_root)

    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")

    assert result.report["hocrgen_import_metadata_packet"]["validation"]["metadata_valid"] is True


def test_hocrsyngen_preflight_validates_runtime_contract_when_evidence_reports_it(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, include_provider_runtime=True)

    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")

    packet = result.report["hocrgen_import_metadata_packet"]
    assert packet["provider_metadata"]["runtime_contract"] == {
        "evidence_status": "validated_from_candidate_evidence_report",
        "source": "candidate_evidence_run_report.provider_runtime",
        "used_network": False,
        "used_rest_service": False,
        "used_gpu": False,
        "used_llm": False,
        "used_diffusion": False,
    }
    assert packet["validation"]["validated_against_hocrgen_release_import_model"] is True
    assert packet["validation"]["release_import_model_validation_errors"] == []


def test_hocrsyngen_preflight_rejects_invalid_runtime_contract(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, include_provider_runtime=True)
    _update_candidate_report(
        evidence_root,
        lambda payload: payload["provider_runtime"].update({"used_llm": True}),
    )

    with pytest.raises(StageExecutionError, match="provider_runtime must explicitly declare all runtime flags false"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


@pytest.mark.parametrize(
    "provider_runtime",
    [
        "not-an-object",
        {
            "schema_version": "wrong",
            "used_network": False,
            "used_rest_service": False,
            "used_gpu": False,
            "used_llm": False,
            "used_diffusion": False,
        },
    ],
)
def test_hocrsyngen_preflight_rejects_malformed_runtime_contract(
    tmp_path: Path,
    provider_runtime: object,
) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_candidate_report(evidence_root, lambda payload: payload.update({"provider_runtime": provider_runtime}))

    with pytest.raises(StageExecutionError, match="provider_runtime"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


@pytest.mark.parametrize(
    "payload",
    [
        {
            "evidence_status": "validated_from_candidate_evidence_report",
            "source": "wrong",
            "used_network": False,
            "used_rest_service": False,
            "used_gpu": False,
            "used_llm": False,
            "used_diffusion": False,
        },
        {
            "evidence_status": "validated_from_candidate_evidence_report",
            "source": "candidate_evidence_run_report.provider_runtime",
            "used_network": False,
            "used_rest_service": False,
            "used_gpu": False,
            "used_llm": True,
            "used_diffusion": False,
        },
        {
            "evidence_status": "not_provided_by_candidate_evidence_report",
            "source": "candidate_evidence_run_report.provider_runtime",
            "used_network": None,
            "used_rest_service": None,
            "used_gpu": None,
            "used_llm": None,
            "used_diffusion": None,
        },
        {
            "evidence_status": "not_provided_by_candidate_evidence_report",
            "source": None,
            "used_network": False,
            "used_rest_service": None,
            "used_gpu": None,
            "used_llm": None,
            "used_diffusion": None,
        },
    ],
)
def test_import_provider_runtime_contract_rejects_inconsistent_evidence(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ImportProviderRuntimeContract.model_validate(payload)


def test_hocrsyngen_preflight_prefers_top_level_synthetic_disclosure(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    manifest_path = evidence_root / "generated_batch" / "generation_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["synthetic_disclosure"] = "Top-level hocrsyngen batch disclosure."
    _write_json(manifest_path, payload)
    _write_sha256s(evidence_root)

    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")

    assert result.report["hocrgen_import_metadata_packet"]["batch_metadata"]["synthetic_disclosure"] == (
        "Top-level hocrsyngen batch disclosure."
    )


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


def test_hocrsyngen_preflight_rejects_provider_version_mismatch_before_sidecar(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_candidate_report(evidence_root, lambda payload: payload.update({"generator_version": "other-version"}))

    with pytest.raises(StageExecutionError, match="generator_version must match all manifest samples"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_rejects_missing_provider_version_before_sidecar(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    _update_candidate_report(evidence_root, lambda payload: payload.pop("generator_version"))

    with pytest.raises(StageExecutionError, match="generator_version is required"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_preflight_derives_handwritten_layout_family(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(
        tmp_path,
        catalog_template_id="handwritten_note",
        catalog_recipe_id="handwritten_note_marginalia_v1",
        catalog_base_family="handwritten_note",
        manifest_template_id="handwritten_note",
        manifest_recipe_id="handwritten_note_marginalia_v1",
    )

    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")

    packet = result.report["hocrgen_import_metadata_packet"]
    assert packet["samples"][0]["rendering_metadata"]["layout_family"] == "handwritten_note_marginalia"


def test_hocrsyngen_preflight_derives_layout_family_from_recipe_when_base_family_is_unknown(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, catalog_base_family="unknown")

    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")

    packet = result.report["hocrgen_import_metadata_packet"]
    assert packet["samples"][0]["rendering_metadata"]["layout_family"] == "printed_letter_form"


def test_hocrsyngen_preflight_rejects_unsupported_layout_family_for_sidecar(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(
        tmp_path,
        catalog_template_id="ledger",
        catalog_recipe_id="ledger_table_v1",
        catalog_base_family="ledger",
        manifest_template_id="ledger",
        manifest_recipe_id="ledger_table_v1",
    )

    with pytest.raises(StageExecutionError, match="unsupported hocrgen release-import layout family"):
        run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")


def test_hocrsyngen_import_packet_rejects_missing_catalog_join_defensively(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    context = _load_import_packet_context(evidence_root)

    with pytest.raises(StageExecutionError, match="missing template catalog join"):
        _build_import_metadata_packet(
            evidence_root.resolve(),
            context["evidence_report"],
            context["manifest"],
            context["manifest_payload"],
            context["manifest_path"],
            {"joins": []},
            {"present": False},
            ["provider_metadata"],
        )


def test_hocrsyngen_import_packet_rejects_ambiguous_batch_disclosure(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    manifest_payload = _load_manifest_payload(evidence_root)
    second = {
        **manifest_payload["samples"][0],
        "sample_id": "hocrsyngen-s00000101-000001",
        "synthetic_disclosure": "Different synthetic disclosure.",
        "provenance": {**manifest_payload["samples"][0]["provenance"], "sample_index": 1},
        "pages": [
            {
                **manifest_payload["samples"][0]["pages"][0],
                "page_id": "hocrsyngen-s00000101-000001-page-0001",
                "asset_path": "assets/hocrsyngen-s00000101-000001/page_0001.jpg",
            }
        ],
    }
    manifest_payload["samples"].append(second)
    manifest = PublicGenerationManifest.model_validate(manifest_payload)

    with pytest.raises(StageExecutionError, match="cannot derive a single batch synthetic_disclosure"):
        _derive_batch_synthetic_disclosure(manifest_payload, manifest)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "supported_base_families": ["ledger"],
            "supported_layout_families": ["handwritten_note_marginalia", "printed_letter_form"],
            "unsupported_family_behavior": "fail_closed_before_sidecar",
        },
        {
            "supported_base_families": ["handwritten_note", "printed_letter"],
            "supported_layout_families": ["ledger_table"],
            "unsupported_family_behavior": "fail_closed_before_sidecar",
        },
    ],
)
def test_import_layout_family_policy_rejects_policy_drift(payload: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        ImportLayoutFamilyPolicy.model_validate(payload)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda packet: packet.update({"schema_version": "wrong"}),
        lambda packet: packet.update({"samples": "not-a-list"}),
        lambda packet: packet.update({"samples": []}),
        lambda packet: packet.update({"release_eligible": True}),
        lambda packet: packet["source_manifest"].update({"boundary_id": "sha256:" + "0" * 64}),
        lambda packet: packet["source_manifest"].update({"sha256": "0" * 64, "boundary_id": "sha256:" + "0" * 64}),
        lambda packet: packet["source_manifest"].update({"path": "other/generation_manifest.json"}),
        lambda packet: packet["validation"].update({"sample_count": 99}),
        lambda packet: packet["validation"].update({"page_count": 99}),
        lambda packet: packet["validation"].update({"generator_versions": ["z-version", "a-version"]}),
        lambda packet: packet["validation"].update({"generator_versions": ["other-version"]}),
        lambda packet: packet["validation"].update({"release_import_model_validation_errors": ["wrong"]}),
        lambda packet: packet["validation"].update({"validated_against_hocrgen_release_import_model": True}),
        lambda packet: packet["samples"].__setitem__(
            0,
            {**packet["samples"][0], "sample_id": "hocrsyngen-s00000101-999999"},
        ),
        lambda packet: packet.update({"unexpected": True}),
    ],
)
def test_hocrsyngen_import_packet_validation_rejects_invalid_sidecar_shapes(
    tmp_path: Path,
    mutate: Callable[[dict], None],
) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")
    manifest = PublicGenerationManifest.model_validate(_load_manifest_payload(evidence_root))
    packet = json.loads(json.dumps(result.report["hocrgen_import_metadata_packet"]))
    mutate(packet)

    with pytest.raises(StageExecutionError, match="hocrgen import metadata packet"):
        _validate_import_metadata_packet(
            evidence_root.resolve(),
            evidence_root / "generated_batch" / "generation_manifest.json",
            manifest,
            packet,
        )


def test_hocrsyngen_import_packet_validation_rejects_duplicate_sample_ids(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")
    packet = json.loads(json.dumps(result.report["hocrgen_import_metadata_packet"]))
    packet["samples"].append(packet["samples"][0])
    packet["validation"]["sample_count"] = 2

    with pytest.raises(ValueError, match="unique sample_id"):
        HocrsyngenImportMetadataPacket.model_validate(packet)


def test_release_import_projection_reports_model_validation_errors(tmp_path: Path) -> None:
    evidence_root = _write_evidence_root(tmp_path, include_provider_runtime=True)
    result = run_hocrsyngen_preflight(evidence_root, report_path=tmp_path / "report.json")
    manifest = PublicGenerationManifest.model_validate(_load_manifest_payload(evidence_root))
    packet = json.loads(json.dumps(result.report["hocrgen_import_metadata_packet"]))
    packet["samples"][0]["rendering_metadata"]["line_count"] = 99

    errors = _release_import_model_validation_errors(
        manifest,
        packet["provider_metadata"],
        packet["samples"],
        packet["batch_metadata"]["synthetic_disclosure"],
    )

    assert errors
    assert errors[0].startswith("hocrgen release/import model validation failed")


@pytest.mark.parametrize(
    "relative_path",
    [
        "candidate_evidence_run_report.json",
        "reports/template_catalog_v2.json",
        "generated_batch/generation_manifest.json",
        "generated_batch/rendering_coverage_report.json",
        "SHA256SUMS",
        "generated_batch/assets/hocrsyngen-s00000101-000000/page_0001.jpg",
    ],
)
def test_hocrsyngen_preflight_rejects_symlinked_evidence_artifacts(
    tmp_path: Path,
    relative_path: str,
) -> None:
    evidence_root = _write_evidence_root(tmp_path)
    target = tmp_path / "outside_artifact"
    target.write_text("{}", encoding="utf-8")
    artifact = evidence_root / relative_path
    artifact.unlink()
    artifact.symlink_to(target)

    with pytest.raises(StageExecutionError, match="must not be a symlink"):
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
    catalog_template_id: str = "printed_letter",
    catalog_base_family: str = "printed_letter",
    manifest_recipe_id: str = "printed_letter_form_v1",
    manifest_template_id: str = "printed_letter",
    include_provider_runtime: bool = False,
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
                    "logical_order": "שלום עולם\nמספר 101.",
                    "script": "Hebr",
                    "language": "he",
                    "direction": "rtl",
                    "unicode_normalization": "NFC",
                },
                "generator_version": "d4a-realism-v2",
                "recipe_id": manifest_recipe_id,
                "provenance": {
                    "seed": 101,
                    "sample_index": 0,
                    "template_id": manifest_template_id,
                    "recipe_id": manifest_recipe_id,
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
                "template_id": catalog_template_id,
                "recipe_id": catalog_recipe_id,
                "layout_style": "printed_form",
                "font_style": "printed",
                "font_id": "alef-regular",
                "degradation_preset": "office_scan_soft",
                "document_family": "letter",
                "base_family": catalog_base_family,
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
    if include_provider_runtime:
        candidate_report["provider_runtime"] = {
            "schema_version": "hocrgen_hocrsyngen_provider_runtime.v1",
            "used_network": False,
            "used_rest_service": False,
            "used_gpu": False,
            "used_llm": False,
            "used_diffusion": False,
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


def _load_manifest_payload(evidence_root: Path) -> dict:
    payload = json.loads((evidence_root / "generated_batch" / "generation_manifest.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _load_import_packet_context(evidence_root: Path) -> dict[str, object]:
    manifest_payload = _load_manifest_payload(evidence_root)
    evidence_report = json.loads((evidence_root / "candidate_evidence_run_report.json").read_text(encoding="utf-8"))
    assert isinstance(evidence_report, dict)
    manifest = PublicGenerationManifest.model_validate(manifest_payload)
    return {
        "evidence_report": evidence_report,
        "manifest": manifest,
        "manifest_payload": manifest_payload,
        "manifest_path": evidence_root / "generated_batch" / "generation_manifest.json",
    }


def _write_sha256s(root: Path) -> None:
    paths = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    lines = [f"{sha256_file(path)}  {path.relative_to(root).as_posix()}" for path in paths]
    (root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
