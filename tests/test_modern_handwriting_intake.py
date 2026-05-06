from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from PIL import Image, ImageDraw

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.modern_handwriting import ModernHandwritingIntakeFetcher, validate_modern_intake_manifest
from hocrgen.manifests.models import ItemRecord
from hocrgen.utils.hashing import sha256_file


MODERN_SOURCE_ID = "modern_contributor_open"


def _write_fixture_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 320), "white")
    draw = ImageDraw.Draw(image)
    draw.line((40, 90, 280, 120), fill="black", width=3)
    draw.line((40, 150, 260, 170), fill="black", width=3)
    draw.line((40, 215, 290, 235), fill="black", width=3)
    image.save(path)


def _record(asset_path: Path, *, source_item_id: str = "sample-001") -> dict[str, Any]:
    return {
        "source_item_id": source_item_id,
        "title": "Synthetic modern handwriting intake fixture",
        "asset_path": asset_path.name,
        "sha256": sha256_file(asset_path),
        "media_type": "image/png",
        "contributor_eligibility": "adult_contributor",
        "consent_artifact_id": "consent-0001",
        "consent_effective_date": "2026-05-06",
        "consent_scope": "image_prompt_metadata_public_reuse",
        "release_terms_version": "f3a-modern-consent-v1",
        "normalized_license": "HEOCR-CONSENT-OPEN",
        "contributor_wrote_sample": True,
        "approved_prompt_text": True,
        "private_evidence_locator": "private-consent-0001",
        "privacy_screening_status": "clear",
        "privacy_reviewer_id": "operator-a",
        "privacy_review_timestamp": "2026-05-06T10:00:00Z",
        "unresolved_privacy_flags": [],
        "operator_review_status": "intake_ready",
        "operator_reviewer_id": "operator-a",
        "operator_review_timestamp": "2026-05-06T10:05:00Z",
        "takedown_status": "none",
        "public_inclusion_state": "candidate",
        "scan": {
            "capture_resolution_dpi": 300,
            "capture_device": "test fixture renderer",
            "color_mode": "color",
            "orientation": "right_side_up",
            "page_visible": True,
            "hands_or_background_visible": False,
            "aggressive_filtering": False,
        },
        "composition": {
            "prompt_id": "prompt-neutral-001",
            "page_type": "prompted_lines",
            "script_style": "block_print",
            "language_mix": "hebrew_only",
            "page_condition": "clean_scan",
        },
        "text_metadata": {"prompt": "שלום עולם"},
    }


def _manifest(asset_path: Path) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "batch_id": "modern-batch-0001",
        "source_id": MODERN_SOURCE_ID,
        "operator_id": "operator-a",
        "collection_date": "2026-05-06",
        "collection_method": "operator_manifest",
        "consent_terms_version": "f3a-modern-consent-v1",
        "records": [_record(asset_path)],
    }


def _write_manifest(root: Path, payload: dict[str, Any]) -> Path:
    manifest_path = root / "modern_intake_manifest.json"
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest_path


def _config_root(tmp_path: Path, manifest_path: Path, *, include_modern_profile: bool = False) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    sources_path = config_root / "sources.yaml"
    data = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    data["sources"].append(
        {
            "id": MODERN_SOURCE_ID,
            "name": "Modern contributor handwriting operator intake",
            "fetcher": "modern_handwriting_intake",
            "status": "review_only",
            "default_public_release": False,
            "allowed_content_types": ["handwritten_modern"],
            "rights_strategy": {"type": "exact_match", "values": ["HEOCR-CONSENT-OPEN"]},
            "normalized_license": "HEOCR-CONSENT-OPEN",
            "rights_classification": "open",
            "requires_manual_review": True,
            "source_operations": {
                "operational_status": "active",
                "health_expectations": {"min_candidates": 1, "min_assets": 1},
            },
            "settings": {"modern_intake_manifest": str(manifest_path)},
        }
    )
    sources_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    if include_modern_profile:
        profile = yaml.safe_load((config_root / "profiles" / "profile_open_v1.yaml").read_text(encoding="utf-8"))
        profile["id"] = "profile_modern_operator"
        profile["description"] = "Operator-only modern handwriting intake validation profile."
        profile["include_sources"] = [*profile["include_sources"], MODERN_SOURCE_ID]
        (config_root / "profiles" / "profile_modern_operator.yaml").write_text(
            yaml.safe_dump(profile, sort_keys=False),
            encoding="utf-8",
        )
    return config_root


def _modern_fixture(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "modern_fixture"
    asset_path = root / "sample_001.png"
    _write_fixture_image(asset_path)
    manifest_path = _write_manifest(root, _manifest(asset_path))
    return root, manifest_path


def _assert_config_validate_error(config_root: Path, capsys, message: str) -> None:
    exit_code = main(["config", "validate", "--config-root", str(config_root)])
    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "error"
    assert message in payload["error"]


def test_modern_intake_manifest_validates(tmp_path: Path) -> None:
    _, manifest_path = _modern_fixture(tmp_path)
    bundle = load_and_validate_bundle(_config_root(tmp_path, manifest_path))
    source = next(source for source in bundle.source_registry.sources if source.id == MODERN_SOURCE_ID)

    batch = validate_modern_intake_manifest(source, bundle)

    assert batch.candidate_count == 1
    assert batch.asset_count == 1
    assert batch.manifest.records[0].normalized_license == "HEOCR-CONSENT-OPEN"


def test_config_validate_checks_modern_intake_manifest(tmp_path: Path, capsys) -> None:
    _, manifest_path = _modern_fixture(tmp_path)
    config_root = _config_root(tmp_path, manifest_path)

    exit_code = main(["config", "validate", "--config-root", str(config_root)])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["source_count"] == 5


def test_config_validate_checks_modern_intake_manifest_failures(tmp_path: Path, capsys) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["sha256"] = "0" * 64
    _write_manifest(root, payload)

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, "sha256 mismatch")


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload["records"][0].pop("consent_artifact_id"), "consent_artifact_id or institutional_agreement_id"),
        (lambda payload: payload["records"][0].update({"contributor_eligibility": "minor_contributor"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"asset_path": "/tmp/page.png"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"asset_path": "C:sample.png"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"private_evidence_locator": "../private/consent.pdf"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"media_type": "image/gif"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"consent_effective_date": "not-a-date"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"privacy_review_timestamp": "2026-05-06T10:00:00"}), "timezone"),
        (lambda payload: payload["records"][0]["composition"].update({"demographic_band": "age:30-39"}), "validation failed"),
        (lambda payload: payload["records"][0].update({"unresolved_privacy_flags": ["name_visible"]}), "unresolved_privacy_flags"),
        (lambda payload: payload["records"][0].update({"takedown_request_date": "2026-05-06"}), "takedown"),
        (lambda payload: payload["records"][0].update({"normalized_license": "CC-BY-4.0"}), "validation failed"),
        (lambda payload: payload["records"][0]["text_metadata"].update({"prompt": "Cafe\u0301"}), "NFC"),
    ],
)
def test_modern_intake_manifest_rejects_policy_failures(tmp_path: Path, capsys, mutate, message: str) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(payload)
    _write_manifest(root, payload)

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, message)


def test_modern_intake_manifest_rejects_missing_asset(tmp_path: Path, capsys) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    (root / "sample_001.png").unlink()

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, "asset is missing")


def test_modern_intake_manifest_rejects_checksum_mismatch(tmp_path: Path, capsys) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["sha256"] = "0" * 64
    _write_manifest(root, payload)

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, "sha256 mismatch")


def test_modern_intake_manifest_rejects_symlink_asset_escape(tmp_path: Path, capsys) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    outside_asset = tmp_path / "outside.png"
    _write_fixture_image(outside_asset)
    linked_asset = root / "linked.png"
    linked_asset.symlink_to(outside_asset)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["asset_path"] = linked_asset.name
    payload["records"][0]["sha256"] = sha256_file(outside_asset)
    _write_manifest(root, payload)

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, "escapes manifest directory")


def test_modern_intake_manifest_rejects_media_type_mismatch(tmp_path: Path, capsys) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["media_type"] = "image/jpeg"
    _write_manifest(root, payload)

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, "media type mismatch")


def test_modern_intake_manifest_rejects_unreadable_asset_content(tmp_path: Path, capsys) -> None:
    root, manifest_path = _modern_fixture(tmp_path)
    asset_path = root / "sample_001.png"
    asset_path.write_text("not really an image", encoding="utf-8")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["records"][0]["sha256"] = sha256_file(asset_path)
    _write_manifest(root, payload)

    _assert_config_validate_error(_config_root(tmp_path, manifest_path), capsys, "not a readable JPEG/PNG")


def test_modern_intake_source_must_be_review_only(tmp_path: Path) -> None:
    _, manifest_path = _modern_fixture(tmp_path)
    config_root = _config_root(tmp_path, manifest_path)
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    payload["sources"][-1]["status"] = "allowed"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="status: review_only"):
        load_and_validate_bundle(config_root)


def test_modern_intake_fetcher_maps_records_without_private_paths(tmp_path: Path) -> None:
    _, manifest_path = _modern_fixture(tmp_path)
    bundle = load_and_validate_bundle(_config_root(tmp_path, manifest_path))
    source = next(source for source in bundle.source_registry.sources if source.id == MODERN_SOURCE_ID)
    fetcher = ModernHandwritingIntakeFetcher()

    candidates = fetcher.discover_candidates(source, bundle, StageOptions())
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
    items = [
        ItemRecord(
            **record.model_dump(),
            item_id=f"{record.source_id}:{record.source_item_id}",
            normalized_license="HEOCR-CONSENT-OPEN",
            rights_classification="open",
            eligibility="accepted",
            eligibility_reason="allowed_by_profile",
            is_synthetic=False,
            provenance={"source_name": source.name, "fetcher": source.fetcher, "upstream_identifier": record.source_item_id},
        )
        for record in enriched
    ]
    acquired = fetcher.acquire_items(source, bundle, items, tmp_path / "acquire", StageOptions())

    assert [candidate.source_item_id for candidate in candidates] == ["sample-001"]
    assert enriched[0].raw_rights_text == "HEOCR-CONSENT-OPEN"
    assert enriched[0].metadata["modern_intake_batch_id"] == "modern-batch-0001"
    assert "private-consent-0001" not in json.dumps(enriched[0].metadata, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(enriched[0].metadata, ensure_ascii=False)
    assert str(tmp_path) not in json.dumps(enriched[0].raw_metadata, ensure_ascii=False)
    assert "demographic" not in json.dumps(enriched[0].model_dump(mode="json"), ensure_ascii=False)
    assert acquired[0].acquired_assets[0].media_type == "image/png"
    assert Path(acquired[0].acquired_assets[0].path).is_file()


def test_modern_intake_pipeline_requires_review_then_allows_explicit_approval(tmp_path: Path, capsys) -> None:
    _, manifest_path = _modern_fixture(tmp_path)
    config_root = _config_root(tmp_path, manifest_path, include_modern_profile=True)
    workdir = tmp_path / "runs"

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_modern_operator",
            "--dry-run",
            "--workdir",
            str(workdir),
            "--config-root",
            str(config_root),
        ]
    )
    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    review_queue = json.loads((run_dir / "build_release" / "review_queue.json").read_text(encoding="utf-8"))
    review_merge_summary = json.loads((run_dir / "review_merge" / "summary.json").read_text(encoding="utf-8"))
    source_health = json.loads((run_dir / "discover" / "source_health.json").read_text(encoding="utf-8"))

    modern_review = next(item for item in review_queue["items"] if item["source_id"] == MODERN_SOURCE_ID)
    assert "policy:manual_review_required_source" in modern_review["review_reasons"]
    assert "policy:review_only_source" in modern_review["review_reasons"]
    assert review_merge_summary["review_unresolved_count"] >= 1
    modern_health = next(source for source in source_health["sources"] if source["source_id"] == MODERN_SOURCE_ID)
    assert modern_health["candidate_count"] == 1
    assert modern_health["asset_count"] == 1

    review_data = tmp_path / "review_data"
    (review_data / "allowlists").mkdir(parents=True)
    (review_data / "blocklists").mkdir(parents=True)
    (review_data / "manual_decisions").mkdir(parents=True)
    (review_data / "allowlists" / "modern-sample-001.json").write_text(
        json.dumps(
            {
                "item_id": f"{MODERN_SOURCE_ID}:sample-001",
                "review_item_id": f"review:{MODERN_SOURCE_ID}:sample-001",
                "reviewer": "operator-a",
                "timestamp": "2026-05-06T11:00:00Z",
                "rationale": "F3b fixture approval for operator workflow regression coverage.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_modern_operator",
            "--dry-run",
            "--workdir",
            str(workdir / "approved"),
            "--config-root",
            str(config_root),
        ]
    )
    assert exit_code == 0
    approved_payload = json.loads(capsys.readouterr().out)
    approved_run_dir = Path(approved_payload["run_dir"])
    release_items = json.loads((approved_run_dir / "build_release" / "item_manifest.json").read_text(encoding="utf-8"))
    release_summary = json.loads((approved_run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))

    assert any(item["item_id"] == f"{MODERN_SOURCE_ID}:sample-001" for item in release_items["items"])
    assert release_summary["review_approved_count"] >= 1
