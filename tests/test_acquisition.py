from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.biblia import BibliaImporter
from hocrgen.fetchers.nli import NliFetcher
from hocrgen.fetchers.pinkas import PinkasImporter
from hocrgen.fetchers.synthetic import SyntheticFetcher
from hocrgen.manifests.models import ItemRecord
from hocrgen.parsers.rights import RightsResult, classify_eligibility, normalize_rights
from hocrgen.synthetic.generator import _font_path, _load_font, _select_font, _wrap_hebrew_text, generate_documents


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


def test_nli_fetcher_allows_fixtureless_seeds_but_fails_on_metadata_fetch(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    base_source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")
    package_data_dir = Path(__file__).resolve().parents[1] / "src" / "hocrgen" / "data" / "nli"
    (package_data_dir / "seeds_custom.yaml").write_text(
        """
items:
  - id: nli-manual-001
    url: https://example.com/manual
    title: Exploratory seed
    notes: no fixture yet
""".strip()
            + "\n",
            encoding="utf-8",
        )
    try:
        source = base_source.model_copy(
            update={
                "settings": base_source.settings.model_copy(
                    update={"seed_manifest": "package://data/nli/seeds_custom.yaml"}
                )
            }
        )
        fetcher = NliFetcher()
        candidates = fetcher.discover_candidates(source, bundle, StageOptions())

        assert candidates[0].fixture_path is None
        assert candidates[0].raw_metadata["notes"] == "no fixture yet"

        with pytest.raises(StageExecutionError, match="missing fixture_html"):
            fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
    finally:
        custom_seed_path = package_data_dir / "seeds_custom.yaml"
        if custom_seed_path.exists():
            custom_seed_path.unlink()


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


def test_review_profile_accepts_restricted_nonpublic_items() -> None:
    bundle = load_and_validate_bundle()
    review_profile = bundle.profiles["profile_review_v1"]

    eligibility, reason = classify_eligibility(
        RightsResult(
            raw_text="Restricted",
            normalized_license="RESTRICTED-NONOPEN",
            rights_classification="restricted_review_only",
        ),
        review_profile,
        public_release_allowed=False,
    )

    assert eligibility == "accepted"
    assert reason == "allowed_by_profile"


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
    assert acquired_once[0].acquired_assets[0].path.endswith(".jpg")
    assert acquired_once[0].acquired_assets[0].media_type == "image/jpeg"
    assert acquired_once[0].metadata["synthetic_generator_version"] == "b3b-jpeg-v1"
    assert acquired_once[0].metadata["synthetic_font_id"] in {
        "alef-regular",
        "gveret-levin-regular",
    }
    assert acquired_once[0].metadata["synthetic_font_id"] == acquired_twice[0].metadata["synthetic_font_id"]


def test_synthetic_generation_uses_packaged_fonts_and_curated_text(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    documents = generate_documents(
        count=2,
        seed=11,
        template_ids=source.settings.template_ids or ["printed_letter", "handwritten_note"],
        font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
        text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
        output_dir=tmp_path / "synthetic",
    )

    assert {document.path.suffix for document in documents} == {".jpg"}
    assert {document.generator_version for document in documents} == {"b3b-jpeg-v1"}
    assert {document.font_id for document in documents} == {
        "alef-regular",
        "gveret-levin-regular",
    }
    forbidden_fragments = {"Ref.", "Batch", "Office Copy", "אנגלית", "אפשר להוסיף מזהה קצר"}
    for document in documents:
        for line in document.body:
            assert not any(fragment in line for fragment in forbidden_fragments)


def test_synthetic_generation_fails_for_empty_inputs(tmp_path: Path) -> None:
    font_manifest_path = tmp_path / "fonts.yaml"
    text_corpus_path = tmp_path / "corpus.txt"
    font_manifest_path.write_text("fonts: []\n", encoding="utf-8")
    text_corpus_path.write_text("", encoding="utf-8")

    try:
        generate_documents(
            count=1,
            seed=7,
            template_ids=[],
            font_manifest_path=font_manifest_path,
            text_corpus_path=text_corpus_path,
            output_dir=tmp_path / "out",
        )
    except ValueError as exc:
        assert str(exc) == "Synthetic generation requires at least one template_id."
    else:
        raise AssertionError("Expected generate_documents to reject empty template_ids")


def test_synthetic_generator_font_path_rejects_missing_file_reference(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("fonts: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing a file reference"):
        _font_path(manifest_path, {"id": "broken-font"})


def test_synthetic_generator_font_path_rejects_missing_file(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("fonts: []\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Synthetic font file is missing"):
        _font_path(manifest_path, {"id": "broken-font", "file": "missing.ttf"})


def test_wrap_hebrew_text_handles_empty_and_wrapping_branches() -> None:
    image = Image.new("RGB", (600, 400), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    manifest_path = bundle.resolve_path(source.settings.font_manifest or "")
    printed_font_entry = {
        "id": "alef-regular",
        "file": "Alef-Regular.ttf",
        "style": "printed",
    }
    font = _load_font(_font_path(manifest_path, printed_font_entry), 42)

    assert _wrap_hebrew_text(draw, "", font, max_width=200) == [""]

    wrapped = _wrap_hebrew_text(draw, "מכתב מנהלי רישום ארכיוני הודעה פנימית", font, max_width=100)

    assert len(wrapped) > 1
    assert all(line for line in wrapped)


def test_select_font_rejects_missing_style() -> None:
    with pytest.raises(ValueError, match="No synthetic font registered for style: handwritten_like"):
        _select_font([{"id": "alef-regular", "style": "printed"}], "handwritten_note")
