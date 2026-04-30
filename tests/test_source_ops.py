from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.core.errors import ConfigValidationError
from hocrgen.fetchers.biblia import BibliaImporter
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.nli import NliFetcher
from hocrgen.fetchers.pinkas import PinkasImporter
from hocrgen.fetchers.synthetic import SyntheticFetcher
from hocrgen.manifests.models import EnrichedCandidateRecord, ItemRecord
from hocrgen.source_ops import (
    SourceHealthResult,
    _inspect_nli_source,
    _inspect_records_source,
    _inspect_source,
    _inspect_synthetic_source,
    source_health_summary,
)


def _copy_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    return config_root


def _update_source_operations(config_root: Path, source_id: str, *, status: str, reason: str = "") -> None:
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == source_id:
            source.setdefault("source_operations", {})
            source["source_operations"]["operational_status"] = status
            source["source_operations"]["operational_reason"] = reason
            break
    else:
        raise AssertionError(f"missing source {source_id}")
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _update_source_settings(config_root: Path, source_id: str, settings: dict[str, object]) -> None:
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == source_id:
            source["settings"].update(settings)
            break
    else:
        raise AssertionError(f"missing source {source_id}")
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _item_from_enriched(record: EnrichedCandidateRecord, *, synthetic: bool = False) -> ItemRecord:
    return ItemRecord(
        **record.model_dump(),
        item_id=f"{record.source_id}:{record.source_item_id}",
        normalized_license="PD-IL" if not synthetic else "PROJECT-SYNTHETIC",
        rights_classification="open",
        eligibility="accepted",
        eligibility_reason="allowed_by_profile",
        is_synthetic=synthetic,
        provenance={},
    )


def test_frozen_source_is_skipped_and_reported(tmp_path: Path, capsys) -> None:
    config_root = _copy_config(tmp_path)
    _update_source_operations(config_root, "biblia_open", status="frozen", reason="upstream refresh paused")

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    source_health = json.loads((run_dir / "discover" / "source_health.json").read_text(encoding="utf-8"))
    source_stats = json.loads((run_dir / "build_release" / "source_stats.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    biblia_health = next(source for source in source_health["sources"] if source["source_id"] == "biblia_open")
    assert biblia_health["selected"] is False
    assert biblia_health["skipped"] is True
    assert biblia_health["skip_reason"] == "source_frozen"
    assert "biblia_open" not in source_stats["sources"]
    assert source_stats["source_health"]["skipped_sources"] == [
        {
            "operational_reason": "upstream refresh paused",
            "operational_status": "frozen",
            "skip_reason": "source_frozen",
            "source_id": "biblia_open",
        }
    ]


def test_degraded_source_is_skipped_and_reported(tmp_path: Path, capsys) -> None:
    config_root = _copy_config(tmp_path)
    _update_source_operations(config_root, "biblia_open", status="degraded", reason="fixture audit in progress")

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    source_stats = json.loads((run_dir / "build_release" / "source_stats.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert "biblia_open" not in source_stats["sources"]
    assert source_stats["source_health"]["degraded_source_count"] == 1
    assert source_stats["source_health"]["skipped_sources"][0]["skip_reason"] == "source_degraded"


def test_active_source_health_is_emitted_in_discover_and_build_release(tmp_path: Path, capsys) -> None:
    exit_code = main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    discover_summary = json.loads((run_dir / "discover" / "summary.json").read_text(encoding="utf-8"))
    source_health = json.loads((run_dir / "discover" / "source_health.json").read_text(encoding="utf-8"))
    source_stats = json.loads((run_dir / "build_release" / "source_stats.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    assert discover_summary["source_health"]["selected_source_count"] == 4
    assert source_health["summary"]["active_source_count"] == 4
    assert source_stats["source_health"]["skipped_source_count"] == 0


def test_summarize_run_markdown_includes_source_health_warning(tmp_path: Path, capsys) -> None:
    config_root = _copy_config(tmp_path)
    _update_source_operations(config_root, "biblia_open", status="frozen", reason="fixture maintenance")
    build_exit = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
        ]
    )
    build_payload = json.loads(capsys.readouterr().out)

    summarize_exit = main(["summarize-run", "--run-dir", build_payload["run_dir"], "--format", "markdown"])
    markdown = capsys.readouterr().out

    assert build_exit == 0
    assert summarize_exit == 0
    assert "biblia_open skipped: source_frozen" in markdown


def test_invalid_source_operations_config_requires_reason(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    _update_source_operations(config_root, "pinkas_open", status="frozen", reason="")

    with pytest.raises(ConfigValidationError, match="source registry validation failed"):
        load_and_validate_bundle(config_root)


def test_update_source_operations_helper_rejects_unknown_source(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)

    with pytest.raises(AssertionError, match="missing source missing_source"):
        _update_source_operations(config_root, "missing_source", status="frozen", reason="missing")


def test_update_source_settings_helper_rejects_unknown_source(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)

    with pytest.raises(AssertionError, match="missing source missing_source"):
        _update_source_settings(config_root, "missing_source", {"records_path": "missing.json"})


def test_record_health_resolves_relative_assets_next_to_records_file(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    asset_path = records_dir / "relative.jpg"
    asset_path.write_bytes(b"fake")
    records_path = records_dir / "records.json"
    records_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "id": "relative-record",
                        "title": "Relative record",
                        "source_url": "https://example.org/relative",
                        "raw_rights": "PD-IL",
                        "asset_path": "relative.jpg",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _update_source_settings(config_root, "pinkas_open", {"records_path": str(records_path)})
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "pinkas_open")

    checks, candidate_count, asset_count = _inspect_records_source(source, bundle)

    assert candidate_count == 1
    assert asset_count == 1
    assert {"name": "record_asset", "path": str(asset_path), "status": "ok"} in checks


def test_active_source_with_failed_health_is_skipped_at_discover_time(tmp_path: Path, capsys) -> None:
    config_root = _copy_config(tmp_path)
    broken_seed = tmp_path / "broken_seed.yaml"
    broken_seed.write_text("items:\n  - id: broken\n    url: https://example.org/broken\n    fixture_html: missing.html\n", encoding="utf-8")
    _update_source_settings(config_root, "nli_any_use_permitted", {"seed_manifest": str(broken_seed)})

    exit_code = main(
        [
            "discover",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
            "--source",
            "nli_any_use_permitted",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    run_dir = Path(payload["run_dir"])
    source_health = json.loads((run_dir / "discover" / "source_health.json").read_text(encoding="utf-8"))

    assert exit_code == 0
    nli_health = next(source for source in source_health["sources"] if source["source_id"] == "nli_any_use_permitted")
    assert nli_health["selected"] is False
    assert nli_health["skipped"] is True
    assert nli_health["skip_reason"] == "source_health_failed"


def test_source_health_summary_accepts_result_models() -> None:
    summary = source_health_summary(
        [
            SourceHealthResult(
                source_id="model_source",
                fetcher="nli",
                operational_status="active",
                operational_reason="",
                profile_included=True,
                selection_requested=True,
                selected=True,
                skipped=False,
                skip_reason=None,
                health_status="ok",
                candidate_count=1,
                asset_count=1,
                checks=[],
            )
        ]
    )

    assert summary["selected_source_count"] == 1


def test_source_health_reports_unknown_fetcher_without_selection() -> None:
    bundle = load_and_validate_bundle()
    source = bundle.source_registry.sources[0].model_copy(update={"fetcher": "unknown"})

    checks, candidate_count, asset_count = _inspect_source(source, bundle)

    assert candidate_count == 0
    assert asset_count == 0
    assert checks == [{"name": "known_fetcher", "status": "error", "message": "unknown fetcher: unknown"}]


def test_nli_health_reports_malformed_seed_items(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    seed_path = tmp_path / "bad_items.yaml"
    seed_path.write_text("items: bad\n", encoding="utf-8")
    _update_source_settings(config_root, "nli_any_use_permitted", {"seed_manifest": str(seed_path)})
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")

    checks, candidate_count, asset_count = _inspect_nli_source(source, bundle)

    assert candidate_count == 0
    assert asset_count == 0
    assert any(check["name"] == "seed_manifest_items" and check["status"] == "error" for check in checks)


def test_nli_health_skips_malformed_items_and_missing_fixture_reference(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    seed_path = tmp_path / "mixed_items.yaml"
    seed_path.write_text("items:\n  - bad\n  - id: no-fixture\n    url: https://example.org/no-fixture\n", encoding="utf-8")
    _update_source_settings(config_root, "nli_any_use_permitted", {"seed_manifest": str(seed_path)})
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")

    checks, candidate_count, asset_count = _inspect_nli_source(source, bundle)

    assert candidate_count == 2
    assert asset_count == 0
    assert any(check["name"] == "seed_manifest_item" and check["status"] == "error" for check in checks)


def test_records_health_reports_malformed_records(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    records_path = tmp_path / "bad_records.json"
    records_path.write_text(json.dumps({"records": "bad"}), encoding="utf-8")
    _update_source_settings(config_root, "pinkas_open", {"records_path": str(records_path)})
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "pinkas_open")

    checks, candidate_count, asset_count = _inspect_records_source(source, bundle)

    assert candidate_count == 0
    assert asset_count == 0
    assert any(check["name"] == "records" and check["status"] == "error" for check in checks)


def test_records_health_skips_malformed_records_and_missing_asset_reference(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    records_path = tmp_path / "mixed_records.json"
    records_path.write_text(json.dumps({"records": ["bad", {"id": "no-asset"}]}), encoding="utf-8")
    _update_source_settings(config_root, "pinkas_open", {"records_path": str(records_path)})
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "pinkas_open")

    checks, candidate_count, asset_count = _inspect_records_source(source, bundle)

    assert candidate_count == 2
    assert asset_count == 0
    assert any(check["name"] == "record" and check["status"] == "error" for check in checks)


def test_synthetic_health_handles_malformed_fonts_and_default_batch_size(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    font_manifest = tmp_path / "fonts.yaml"
    text_corpus = tmp_path / "lines.txt"
    font_manifest.write_text("fonts:\n  - bad\n  - file: missing.ttf\n", encoding="utf-8")
    text_corpus.write_text("שלום\n", encoding="utf-8")
    _update_source_settings(
        config_root,
        "project_synthetic",
        {"font_manifest": str(font_manifest), "text_corpus_path": str(text_corpus), "synthetic_batch_size": None},
    )
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")

    checks, candidate_count, asset_count = _inspect_synthetic_source(source, bundle)

    assert candidate_count == 0
    assert asset_count == 1
    assert any(check["name"] == "font_file" and check["status"] == "error" for check in checks)


def test_synthetic_health_reports_non_list_fonts(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    font_manifest = tmp_path / "fonts.yaml"
    text_corpus = tmp_path / "lines.txt"
    font_manifest.write_text("fonts: bad\n", encoding="utf-8")
    text_corpus.write_text("שלום\n", encoding="utf-8")
    _update_source_settings(
        config_root,
        "project_synthetic",
        {"font_manifest": str(font_manifest), "text_corpus_path": str(text_corpus)},
    )
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")

    checks, _, _ = _inspect_synthetic_source(source, bundle)

    assert any(check["name"] == "fonts" and check["status"] == "error" for check in checks)


def test_source_health_records_yaml_and_json_parse_errors(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    bad_yaml = tmp_path / "bad.yaml"
    bad_json = tmp_path / "bad.json"
    bad_yaml.write_text("items: [", encoding="utf-8")
    bad_json.write_text("{", encoding="utf-8")
    _update_source_settings(config_root, "nli_any_use_permitted", {"seed_manifest": str(bad_yaml)})
    _update_source_settings(config_root, "pinkas_open", {"records_path": str(bad_json)})
    bundle = load_and_validate_bundle(config_root)
    sources = {source.id: source for source in bundle.source_registry.sources}

    yaml_checks, _, _ = _inspect_nli_source(sources["nli_any_use_permitted"], bundle)
    json_checks, _, _ = _inspect_records_source(sources["pinkas_open"], bundle)

    assert any(check["name"] == "seed_manifest_parse" for check in yaml_checks)
    assert any(check["name"] == "records_path_parse" for check in json_checks)


def test_fixture_backed_source_adapters_regressions(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    sources = {source.id: source for source in bundle.source_registry.sources}
    options = StageOptions()

    nli_candidates = NliFetcher().discover_candidates(sources["nli_any_use_permitted"], bundle, options)
    nli_enriched = NliFetcher().fetch_candidate_metadata(sources["nli_any_use_permitted"], bundle, nli_candidates[:1], options)
    assert nli_candidates
    assert nli_enriched[0].raw_rights_text == "Any Use Permitted"

    pinkas_candidates = PinkasImporter().discover_candidates(sources["pinkas_open"], bundle, options)
    pinkas_enriched = PinkasImporter().fetch_candidate_metadata(sources["pinkas_open"], bundle, pinkas_candidates, options)
    pinkas_acquired = PinkasImporter().acquire_items(
        sources["pinkas_open"],
        bundle,
        [_item_from_enriched(item) for item in pinkas_enriched],
        tmp_path / "pinkas",
        options,
    )
    assert pinkas_candidates
    assert pinkas_acquired[0].acquired_assets[0].path.endswith(".jpg")

    biblia_candidates = BibliaImporter().discover_candidates(sources["biblia_open"], bundle, options)
    biblia_enriched = BibliaImporter().fetch_candidate_metadata(sources["biblia_open"], bundle, biblia_candidates, options)
    biblia_acquired = BibliaImporter().acquire_items(
        sources["biblia_open"],
        bundle,
        [_item_from_enriched(item) for item in biblia_enriched],
        tmp_path / "biblia",
        options,
    )
    assert biblia_candidates
    assert biblia_acquired[0].acquired_assets[0].path.endswith(".jpg")

    synthetic_candidates = SyntheticFetcher().discover_candidates(sources["project_synthetic"], bundle, options)
    synthetic_enriched = SyntheticFetcher().fetch_candidate_metadata(sources["project_synthetic"], bundle, synthetic_candidates, options)
    synthetic_acquired = SyntheticFetcher().acquire_items(
        sources["project_synthetic"],
        bundle,
        [_item_from_enriched(item, synthetic=True) for item in synthetic_enriched],
        tmp_path / "synthetic",
        options,
    )
    assert synthetic_candidates
    assert synthetic_acquired[0].acquired_assets[0].media_type == "image/jpeg"
