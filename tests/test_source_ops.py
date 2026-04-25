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
    _update_source_operations(config_root, "pinkas_open", status="frozen", reason="upstream refresh paused")

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
    pinkas_health = next(source for source in source_health["sources"] if source["source_id"] == "pinkas_open")
    assert pinkas_health["selected"] is False
    assert pinkas_health["skipped"] is True
    assert pinkas_health["skip_reason"] == "source_frozen"
    assert "pinkas_open" not in source_stats["sources"]
    assert source_stats["source_health"]["skipped_sources"] == [
        {
            "operational_reason": "upstream refresh paused",
            "operational_status": "frozen",
            "skip_reason": "source_frozen",
            "source_id": "pinkas_open",
        }
    ]


def test_degraded_source_is_skipped_and_reported(tmp_path: Path, capsys) -> None:
    config_root = _copy_config(tmp_path)
    _update_source_operations(config_root, "project_synthetic", status="degraded", reason="synthetic asset audit in progress")

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
    assert "project_synthetic" not in source_stats["sources"]
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
    _update_source_operations(config_root, "pinkas_open", status="frozen", reason="fixture maintenance")
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
    assert "pinkas_open skipped: source_frozen" in markdown


def test_invalid_source_operations_config_requires_reason(tmp_path: Path) -> None:
    config_root = _copy_config(tmp_path)
    _update_source_operations(config_root, "pinkas_open", status="frozen", reason="")

    with pytest.raises(ConfigValidationError, match="source registry validation failed"):
        load_and_validate_bundle(config_root)


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
