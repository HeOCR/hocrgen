from __future__ import annotations

from pathlib import Path

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.biblia import BibliaImporter
from hocrgen.fetchers.nli import NliFetcher
from hocrgen.fetchers.pinkas import PinkasImporter
from hocrgen.fetchers.synthetic import SyntheticFetcher
from hocrgen.manifests.models import ItemRecord
from hocrgen.parsers.rights import normalize_rights


def test_nli_fetcher_parses_fixture_metadata() -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")
    fetcher = NliFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions())
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())

    assert candidates[0].source_item_id == "nli-ms-001"
    assert enriched[0].raw_rights_text == "Any Use Permitted"
    assert len(enriched[0].asset_references) == 2
    assert enriched[0].title == "מכתב קהילתי, ירושלים 1936"


def test_static_importers_map_fixture_records() -> None:
    bundle = load_and_validate_bundle()
    pinkas_source = next(source for source in bundle.source_registry.sources if source.id == "pinkas_open")
    biblia_source = next(source for source in bundle.source_registry.sources if source.id == "biblia_open")

    pinkas_candidates = PinkasImporter().discover_candidates(pinkas_source, bundle, StageOptions())
    biblia_candidates = BibliaImporter().discover_candidates(biblia_source, bundle, StageOptions())

    assert pinkas_candidates[0].source_item_id == "pinkas-ledger-001"
    assert biblia_candidates[0].source_item_id == "biblia-doc-001"


def test_rights_normalization_maps_known_and_unknown_values() -> None:
    bundle = load_and_validate_bundle()
    licenses = {entry.id: entry for entry in bundle.licenses.licenses}
    nli_source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")

    open_result = normalize_rights("Any Use Permitted", nli_source, licenses)
    unknown_result = normalize_rights("Unmapped value", nli_source, licenses)

    assert open_result.normalized_license == "PD-IL"
    assert unknown_result.normalized_license == "UNKNOWN"
    assert unknown_result.rights_classification.value == "blocked"


def test_synthetic_generation_is_deterministic(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    fetcher = SyntheticFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions(synthetic_seed=23))
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions(synthetic_seed=23))
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
    acquired_once = fetcher.acquire_items(
        source,
        bundle,
        items,
        tmp_path / "out1",
        StageOptions(synthetic_seed=23),
    )
    acquired_twice = fetcher.acquire_items(
        source,
        bundle,
        items,
        tmp_path / "out2",
        StageOptions(synthetic_seed=23),
    )

    assert acquired_once[0].acquired_assets[0].sha256 == acquired_twice[0].acquired_assets[0].sha256
