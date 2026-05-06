from __future__ import annotations

import json
import shutil
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pytest

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.hocrsyngen_manifest import HocrsyngenManifestFetcher, validate_hocrsyngen_batch
from hocrgen.manifests.models import ItemRecord
from hocrgen.utils.hashing import sha256_file


def _fixture_batch_path() -> Path:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    return bundle.resolve_path(source.settings.hocrsyngen_batch_path or "")


def _copy_fixture(tmp_path: Path) -> Path:
    batch_dir = tmp_path / "fixture-batch"
    shutil.copytree(_fixture_batch_path(), batch_dir)
    return batch_dir


def _load_manifest(batch_dir: Path) -> dict:
    return json.loads((batch_dir / "generation_manifest.json").read_text(encoding="utf-8"))


def _write_manifest(batch_dir: Path, payload: dict) -> None:
    (batch_dir / "generation_manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _configured_source(source: SourceConfig, batch_dir: Path) -> SourceConfig:
    return source.model_copy(update={"settings": source.settings.model_copy(update={"hocrsyngen_batch_path": str(batch_dir)})})


def test_packaged_hocrsyngen_fixture_validates() -> None:
    batch = validate_hocrsyngen_batch(_fixture_batch_path())

    assert batch.manifest.manifest_version == "1.0"
    assert batch.manifest.generator_name == "hocrsyngen"
    assert batch.sample_count == 2
    assert batch.page_count == 2


def test_hocrsyngen_manifest_fetcher_maps_fixture_samples(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    base_source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    source = _configured_source(base_source, _copy_fixture(tmp_path))
    fetcher = HocrsyngenManifestFetcher()

    candidates = fetcher.discover_candidates(source, bundle, StageOptions())
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())

    assert [candidate.source_item_id for candidate in candidates] == ["synthetic-0", "synthetic-1"]
    assert {item.raw_rights_text for item in enriched} == {"PROJECT-SYNTHETIC"}
    assert {item.metadata["hocrsyngen_sample_id"] for item in enriched} == {
        "hocrsyngen-s00000017-000000",
        "hocrsyngen-s00000017-000001",
    }
    assert {item.metadata["hocrsyngen_identity_mapping"] for item in enriched} == {"legacy_sample_index_v1"}
    assert all("hocrsyngen_text" not in item.metadata for item in enriched)
    assert {item.metadata["hocrsyngen_text_metadata"]["direction"] for item in enriched} == {"rtl"}
    assert {item.metadata["hocrsyngen_provider_metadata"]["provider_version"] for item in enriched} == {"fixture-f4c-v1"}
    assert {item.metadata["synthetic_provider_version"] for item in enriched} == {"fixture-f4c-v1"}
    assert {item.metadata["hocrsyngen_rendering_metadata"]["text_order"] for item in enriched} == {"logical"}
    assert {item.metadata["hocrsyngen_rendering_metadata"]["line_direction"] for item in enriched} == {"rtl"}
    assert {item.metadata["synthetic_layout_family"] for item in enriched} == {
        "handwritten_note_marginalia",
        "printed_letter_form",
    }
    assert all(item.metadata["hocrsyngen_hebrew_coverage"]["has_hebrew_letters"] is True for item in enriched)
    assert all(item.metadata["synthetic_hebrew_coverage"]["has_punctuation"] is True for item in enriched)
    assert all("hocrsyngen_text_logical_order_sha256" in item.metadata for item in enriched)
    assert {item.metadata["synthetic_recipe_id"] for item in enriched} == {
        "printed_letter_form_v1",
        "handwritten_note_marginalia_v1",
    }
    assert all(str(tmp_path) not in json.dumps(item.metadata, ensure_ascii=False) for item in enriched)


def test_hocrsyngen_manifest_acquire_copies_multi_page_samples(tmp_path: Path) -> None:
    batch_dir = _copy_fixture(tmp_path)
    payload = _load_manifest(batch_dir)
    first_page = payload["samples"][0]["pages"][0]
    second_page_path = batch_dir / "assets" / "hocrsyngen-s00000017-000000" / "page_0002.jpg"
    shutil.copyfile(batch_dir / first_page["asset_path"], second_page_path)
    payload["samples"][0]["pages"].append(
        {
            **first_page,
            "asset_path": "assets/hocrsyngen-s00000017-000000/page_0002.jpg",
            "page_id": "hocrsyngen-s00000017-000000-page-0002",
            "sha256": sha256_file(second_page_path),
        }
    )
    _write_manifest(batch_dir, payload)
    bundle = load_and_validate_bundle()
    base_source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    source = _configured_source(base_source, batch_dir)
    fetcher = HocrsyngenManifestFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions(max_items=1))
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions(max_items=1))
    items = [
        ItemRecord(
            **record.model_dump(),
            item_id=f"{record.source_id}:{record.source_item_id}",
            normalized_license="PROJECT-SYNTHETIC",
            rights_classification="open",
            eligibility="accepted",
            eligibility_reason="allowed_by_profile",
            is_synthetic=True,
            provenance={"source_name": source.name, "fetcher": source.fetcher, "upstream_identifier": record.source_item_id},
        )
        for record in enriched
    ]

    acquired = fetcher.acquire_items(source, bundle, items, tmp_path / "acquire", StageOptions(max_items=1))

    assert len(acquired) == 1
    assert len(acquired[0].acquired_assets) == 2
    assert all(Path(asset.path).is_file() for asset in acquired[0].acquired_assets)
    assert [Path(asset.path).name for asset in acquired[0].acquired_assets] == ["page_0001.jpg", "page_0002.jpg"]


def test_hocrsyngen_manifest_filters_use_provenance_metadata() -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    fetcher = HocrsyngenManifestFetcher()
    options = StageOptions(
        synthetic_recipe_filter={"handwritten_note_marginalia_v1"},
        synthetic_degradation_filter={"notebook_scan_worn"},
        synthetic_template_filter={"handwritten_note"},
    )

    candidates = fetcher.discover_candidates(source, bundle, options)
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, options)

    assert [candidate.source_item_id for candidate in candidates] == ["synthetic-1"]
    assert {item.metadata["synthetic_template_id"] for item in enriched} == {"handwritten_note"}


def test_hocrsyngen_manifest_filters_reject_empty_selection() -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")

    with pytest.raises(StageExecutionError, match="selected no manifest samples"):
        HocrsyngenManifestFetcher().discover_candidates(
            source,
            bundle,
            StageOptions(synthetic_recipe_filter={"missing_recipe"}),
        )


def test_hocrsyngen_manifest_fetch_rejects_candidate_outside_current_controls() -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    fetcher = HocrsyngenManifestFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions())

    with pytest.raises(StageExecutionError, match="not allowed by current synthetic controls"):
        fetcher.fetch_candidate_metadata(
            source,
            bundle,
            candidates,
            StageOptions(synthetic_template_filter={"handwritten_note"}),
        )


def test_hocrsyngen_manifest_validation_rejects_missing_manifest(tmp_path: Path) -> None:
    batch_dir = _copy_fixture(tmp_path)
    (batch_dir / "generation_manifest.json").unlink()

    with pytest.raises(StageExecutionError, match="missing generation_manifest.json"):
        validate_hocrsyngen_batch(batch_dir)


def test_hocrsyngen_manifest_validation_rejects_malformed_json(tmp_path: Path) -> None:
    batch_dir = _copy_fixture(tmp_path)
    (batch_dir / "generation_manifest.json").write_text("{", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="invalid JSON"):
        validate_hocrsyngen_batch(batch_dir)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda payload: payload.update({"generator_name": "other"}), "validation failed"),
        (lambda payload: payload.update({"extra": "nope"}), "validation failed"),
        (lambda payload: payload.pop("provider_metadata"), "validation failed"),
        (lambda payload: payload["provider_metadata"].update({"used_llm": True}), "validation failed"),
        (lambda payload: payload["samples"][0]["rendering_metadata"].update({"text_order": "visual"}), "validation failed"),
        (lambda payload: payload["samples"][0]["rendering_metadata"].update({"line_direction": "ltr"}), "validation failed"),
        (lambda payload: payload["samples"][0]["rendering_metadata"].update({"bidi_handling": "unknown"}), "validation failed"),
        (lambda payload: payload["samples"][0]["rendering_metadata"].update({"font_shaping": "none"}), "validation failed"),
        (lambda payload: payload["samples"][0]["rendering_metadata"].update({"layout_family": "generic"}), "validation failed"),
        (lambda payload: payload["samples"][0]["rendering_metadata"].update({"line_count": 999}), "validation failed"),
        (lambda payload: payload["samples"][0]["hebrew_coverage"].update({"has_niqqud": True}), "validation failed"),
        (lambda payload: payload["samples"][0]["text"].update({"logical_order": "abc 123."}), "validation failed"),
        (lambda payload: payload["samples"][0]["text"].update({"logical_order": "שלום \ufffd"}), "validation failed"),
        (lambda payload: payload["samples"][0]["pages"][0].update({"asset_path": "/tmp/page.jpg"}), "validation failed"),
        (lambda payload: payload["samples"][0]["pages"][0].update({"asset_path": "../page.jpg"}), "validation failed"),
        (lambda payload: payload["samples"][0]["pages"][0].update({"sha256": "0" * 64}), "sha256 mismatch"),
        (lambda payload: payload["samples"][0]["pages"][0].update({"width": 999}), "dimensions mismatch"),
        (
            lambda payload: payload["samples"][0]["text"].update(
                {"logical_order": unicodedata.normalize("NFD", "é")}
            ),
            "validation failed",
        ),
        (lambda payload: payload["samples"][0]["text"].update({"direction": "ltr"}), "validation failed"),
    ],
)
def test_hocrsyngen_manifest_validation_rejects_invalid_contract_fields(
    tmp_path: Path,
    mutate: Callable[[dict], object],
    message: str,
) -> None:
    batch_dir = _copy_fixture(tmp_path)
    payload = _load_manifest(batch_dir)
    mutate(payload)
    _write_manifest(batch_dir, payload)

    with pytest.raises(StageExecutionError, match=message):
        validate_hocrsyngen_batch(batch_dir)


def test_hocrsyngen_manifest_validation_rejects_missing_asset(tmp_path: Path) -> None:
    batch_dir = _copy_fixture(tmp_path)
    payload = _load_manifest(batch_dir)
    (batch_dir / payload["samples"][0]["pages"][0]["asset_path"]).unlink()

    with pytest.raises(StageExecutionError, match="asset_path is missing"):
        validate_hocrsyngen_batch(batch_dir)


def test_hocrsyngen_manifest_validation_rejects_bad_jpeg(tmp_path: Path) -> None:
    batch_dir = _copy_fixture(tmp_path)
    payload = _load_manifest(batch_dir)
    page = payload["samples"][0]["pages"][0]
    asset_path = batch_dir / page["asset_path"]
    asset_path.write_bytes(b"not a jpeg")
    page["sha256"] = sha256_file(asset_path)
    _write_manifest(batch_dir, payload)

    with pytest.raises(StageExecutionError, match="not a readable image"):
        validate_hocrsyngen_batch(batch_dir)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["samples"].append(
                {
                    **payload["samples"][1],
                    "sample_id": payload["samples"][0]["sample_id"],
                    "provenance": {**payload["samples"][1]["provenance"], "sample_index": 2},
                    "pages": [
                        {
                            **payload["samples"][1]["pages"][0],
                            "page_id": "hocrsyngen-s00000017-000002-page-0001",
                            "asset_path": "assets/hocrsyngen-s00000017-000002/page_0001.jpg",
                        }
                    ],
                }
            ),
            "duplicate sample_id",
        ),
        (
            lambda payload: payload["samples"].append(
                {
                    **payload["samples"][1],
                    "sample_id": "hocrsyngen-s00000017-000002",
                    "provenance": {**payload["samples"][1]["provenance"], "sample_index": 0},
                    "pages": [
                        {
                            **payload["samples"][1]["pages"][0],
                            "page_id": "hocrsyngen-s00000017-000002-page-0001",
                            "asset_path": "assets/hocrsyngen-s00000017-000002/page_0001.jpg",
                        }
                    ],
                }
            ),
            "duplicate provenance.sample_index",
        ),
        (
            lambda payload: payload["samples"].append(
                {
                    **payload["samples"][1],
                    "sample_id": "hocrsyngen-s00000017-000002",
                    "provenance": {**payload["samples"][1]["provenance"], "sample_index": 2},
                    "pages": [
                        {
                            **payload["samples"][1]["pages"][0],
                            "page_id": payload["samples"][0]["pages"][0]["page_id"],
                            "asset_path": "assets/hocrsyngen-s00000017-000002/page_0001.jpg",
                        }
                    ],
                }
            ),
            "duplicate page_id",
        ),
        (
            lambda payload: payload["samples"].append(
                {
                    **payload["samples"][1],
                    "sample_id": "hocrsyngen-s00000017-000002",
                    "provenance": {**payload["samples"][1]["provenance"], "sample_index": 2},
                    "pages": [
                        {
                            **payload["samples"][1]["pages"][0],
                            "page_id": "hocrsyngen-s00000017-000002-page-0001",
                            "asset_path": payload["samples"][0]["pages"][0]["asset_path"],
                        }
                    ],
                }
            ),
            "duplicate asset_path",
        ),
    ],
)
def test_hocrsyngen_manifest_validation_rejects_duplicate_identities(
    tmp_path: Path,
    mutate: Callable[[dict], object],
    message: str,
) -> None:
    batch_dir = _copy_fixture(tmp_path)
    payload = _load_manifest(batch_dir)
    mutate(payload)
    duplicate_asset_reference = payload["samples"][-1]["pages"][0]["asset_path"]
    original_asset = batch_dir / payload["samples"][1]["pages"][0]["asset_path"]
    target_asset = batch_dir / duplicate_asset_reference
    if duplicate_asset_reference != payload["samples"][0]["pages"][0]["asset_path"]:
        target_asset.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original_asset, target_asset)
    _write_manifest(batch_dir, payload)

    with pytest.raises(StageExecutionError, match=message):
        validate_hocrsyngen_batch(batch_dir)
