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
from hocrgen.synthetic.generator import (
    CANVAS_SIZE,
    _draw_rtl_text,
    _font_path,
    _load_font,
    _rtl_display_text,
    _rtl_textbbox,
    _select_font,
    _wrap_hebrew_text,
    generate_documents,
)


def _legacy_synthetic_source(bundle):
    source = next(source for source in bundle.source_registry.sources if source.id == "project_synthetic")
    return source.model_copy(
        update={
            "fetcher": "synthetic",
            "settings": source.settings.model_copy(
                update={
                    "extra": {"f1_source_depth_candidate_count": 80},
                    "font_manifest": "package://data/synthetic/fonts/manifest.yaml",
                    "synthetic_batch_size": 2,
                    "synthetic_seed": 17,
                    "template_ids": ["printed_letter", "handwritten_note"],
                    "text_corpus_path": "package://data/synthetic/texts/hebrew_lines.txt",
                }
            ),
        }
    )


def test_nli_fetcher_parses_fixture_metadata() -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")
    fetcher = NliFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions())
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())

    assert len(candidates) == 7
    assert candidates[0].source_item_id == "nli-ms-001"
    assert "nli-ms-seed-005" not in {candidate.source_item_id for candidate in candidates}
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
    source = _legacy_synthetic_source(bundle)
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
    assert acquired_once[0].metadata["synthetic_generator_version"] == "d4a-realism-v2"
    assert acquired_once[0].metadata["synthetic_recipe_id"] == "printed_letter_form_v1"
    assert acquired_once[0].metadata["synthetic_degradation_preset"] == "office_scan_soft"
    assert acquired_once[0].metadata["synthetic_font_id"] == "gveret-levin-regular"
    assert acquired_once[0].metadata["synthetic_font_id"] == acquired_twice[0].metadata["synthetic_font_id"]


def test_synthetic_generation_uses_packaged_fonts_and_curated_text(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)
    documents = generate_documents(
        count=2,
        seed=11,
        template_ids=source.settings.template_ids or ["printed_letter", "handwritten_note"],
        font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
        text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
        output_dir=tmp_path / "synthetic",
    )

    assert {document.path.suffix for document in documents} == {".jpg"}
    assert {document.generator_version for document in documents} == {"d4a-realism-v2"}
    assert {document.font_id for document in documents} == {"gveret-levin-regular"}
    assert {document.recipe_id for document in documents} == {
        "printed_letter_form_v1",
        "handwritten_note_marginalia_v1",
    }
    assert {document.degradation_preset for document in documents} == {
        "office_scan_soft",
        "notebook_scan_worn",
    }
    for document in documents:
        with Image.open(document.path) as image:
            assert image.size == CANVAS_SIZE
            assert image.mode == "RGB"
    forbidden_fragments = {"Ref.", "Batch", "Office Copy", "אנגלית", "אפשר להוסיף מזהה קצר"}
    for document in documents:
        for line in document.body.splitlines():
            assert not any(fragment in line for fragment in forbidden_fragments)


def test_synthetic_template_recipes_are_distinct_and_deterministic(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)

    first = generate_documents(
        count=2,
        seed=31,
        template_ids=["printed_letter", "handwritten_note"],
        font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
        text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
        output_dir=tmp_path / "first",
    )
    second = generate_documents(
        count=2,
        seed=31,
        template_ids=["printed_letter", "handwritten_note"],
        font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
        text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
        output_dir=tmp_path / "second",
    )

    assert [document.sha256 for document in first] == [document.sha256 for document in second]
    assert first[0].recipe_id != first[1].recipe_id
    assert first[0].degradation_preset != first[1].degradation_preset
    assert first[0].sha256 != first[1].sha256


def test_synthetic_controls_filter_by_recipe_and_degradation_preset(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)
    fetcher = SyntheticFetcher()
    options = StageOptions(
        synthetic_recipe_filter={"handwritten_note_marginalia_v1"},
        synthetic_degradation_filter={"notebook_scan_worn"},
    )

    candidates = fetcher.discover_candidates(source, bundle, options)
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, options)
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

    acquired = fetcher.acquire_items(source, bundle, items, tmp_path / "out", options)

    assert {candidate.raw_metadata["synthetic_template_id"] for candidate in candidates} == {"handwritten_note"}
    assert {item.metadata["synthetic_recipe_id"] for item in enriched} == {"handwritten_note_marginalia_v1"}
    assert all("synthetic_available_template_ids" not in item.metadata for item in enriched)
    assert {item.metadata["synthetic_template_id"] for item in acquired} == {"handwritten_note"}
    assert {item.metadata["synthetic_degradation_preset"] for item in acquired} == {"notebook_scan_worn"}


def test_synthetic_discovery_honors_max_items() -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)

    candidates = SyntheticFetcher().discover_candidates(source, bundle, StageOptions(max_items=1))

    assert [candidate.source_item_id for candidate in candidates] == ["synthetic-0"]


def test_synthetic_acquire_handles_empty_item_batches(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)

    assert SyntheticFetcher().acquire_items(source, bundle, [], tmp_path, StageOptions()) == []


def test_synthetic_resume_rejects_candidate_metadata_outside_current_controls() -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)
    fetcher = SyntheticFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions())

    with pytest.raises(StageExecutionError, match="template_id 'printed_letter' is not allowed"):
        fetcher.fetch_candidate_metadata(
            source,
            bundle,
            candidates,
            StageOptions(synthetic_template_filter={"handwritten_note"}),
        )


def test_synthetic_controls_reject_empty_selection() -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)

    with pytest.raises(StageExecutionError, match="selected no configured templates"):
        SyntheticFetcher().discover_candidates(
            source,
            bundle,
            StageOptions(synthetic_recipe_filter={"unknown_recipe"}),
        )


def test_synthetic_controls_reject_unknown_degradation_preset() -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)

    with pytest.raises(StageExecutionError, match="selected no configured templates"):
        SyntheticFetcher().discover_candidates(
            source,
            bundle,
            StageOptions(synthetic_degradation_filter={"unknown_preset"}),
        )


def test_synthetic_metadata_validation_rejects_recipe_mismatch() -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)
    fetcher = SyntheticFetcher()
    candidate = fetcher.discover_candidates(source, bundle, StageOptions())[0].model_copy(
        update={
            "raw_metadata": {
                "synthetic_index": 0,
                "synthetic_template_id": "printed_letter",
                "synthetic_recipe_id": "handwritten_note_marginalia_v1",
                "synthetic_degradation_preset": "office_scan_soft",
            }
        }
    )

    with pytest.raises(StageExecutionError, match="synthetic_recipe_id"):
        fetcher.fetch_candidate_metadata(source, bundle, [candidate], StageOptions())


def test_synthetic_acquire_rejects_item_metadata_outside_current_controls() -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)
    fetcher = SyntheticFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions())
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
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

    with pytest.raises(StageExecutionError, match="template_id 'printed_letter' is not allowed"):
        fetcher.acquire_items(
            source,
            bundle,
            items,
            Path("."),
            StageOptions(synthetic_template_filter={"handwritten_note"}),
        )


def test_synthetic_visual_recipes_render_expected_page_features(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)
    documents = generate_documents(
        count=2,
        seed=31,
        template_ids=["printed_letter", "handwritten_note"],
        font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
        text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
        output_dir=tmp_path / "synthetic",
    )
    by_template = {document.template_id: document for document in documents}

    with Image.open(by_template["printed_letter"].path).convert("RGB") as printed:
        form_region = printed.crop((140, 330, 1060, 820))
        printed_pixels = list(form_region.getdata())
        red_stamp_pixels = sum(1 for r, g, b in printed_pixels if r > 90 and r > g * 1.45 and r > b * 1.45)
        dark_ink_pixels = sum(1 for r, g, b in printed_pixels if r < 115 and g < 105 and b < 95)
        faint_rule_pixels = sum(
            1
            for r, g, b in printed_pixels
            if 175 <= r <= 235 and 165 <= g <= 225 and 145 <= b <= 210 and max(r, g, b) - min(r, g, b) > 8
        )
        assert red_stamp_pixels > 450
        assert dark_ink_pixels > 5_000
        assert faint_rule_pixels > 50_000

    with Image.open(by_template["handwritten_note"].path).convert("RGB") as handwritten:
        marginalia_region = handwritten.crop((120, 430, 280, 760))
        guide_region = handwritten.crop((150, 300, 1050, 1150))
        marginalia_pixels = list(marginalia_region.getdata())
        guide_pixels = list(guide_region.getdata())
        marginalia_ink_pixels = sum(1 for r, g, b in marginalia_pixels if r < 115 and g < 105 and b < 95)
        guide_rule_pixels = sum(
            1
            for r, g, b in guide_pixels
            if 175 <= r <= 235 and 165 <= g <= 225 and 145 <= b <= 210 and max(r, g, b) - min(r, g, b) > 8
        )
        assert marginalia_ink_pixels > 150
        assert guide_rule_pixels > 500_000


class _NoRaqmDraw:
    def __init__(self) -> None:
        self.text_calls: list[dict[str, object]] = []
        self.textbbox_calls: list[dict[str, object]] = []

    def text(self, *args, **kwargs) -> None:
        self.text_calls.append(kwargs)
        if kwargs.get("direction") == "rtl":
            raise KeyError("setting text direction, language or font features is not supported without libraqm")

    def textbbox(self, *args, **kwargs) -> tuple[int, int, int, int]:
        self.textbbox_calls.append(kwargs)
        if kwargs.get("direction") == "rtl":
            raise KeyError("setting text direction, language or font features is not supported without libraqm")
        return (0, 0, 42, 10)


class _BrokenDraw(_NoRaqmDraw):
    def text(self, *args, **kwargs) -> None:
        raise KeyError("different drawing failure")

    def textbbox(self, *args, **kwargs) -> tuple[int, int, int, int]:
        raise KeyError("different bbox failure")


def test_rtl_text_helpers_fall_back_without_libraqm() -> None:
    draw = _NoRaqmDraw()

    _draw_rtl_text(draw, (10, 10), "שלום", font=object(), fill=(0, 0, 0))  # type: ignore[arg-type]
    bbox = _rtl_textbbox(draw, (0, 0), "שלום", font=object())  # type: ignore[arg-type]

    assert bbox == (0, 0, 42, 10)
    assert draw.text_calls[0]["direction"] == "rtl"
    assert "direction" not in draw.text_calls[1]
    assert draw.textbbox_calls[0]["direction"] == "rtl"
    assert "direction" not in draw.textbbox_calls[1]


def test_rtl_text_helpers_reraise_unexpected_key_errors() -> None:
    draw = _BrokenDraw()

    with pytest.raises(KeyError, match="different drawing failure"):
        _draw_rtl_text(draw, (10, 10), "שלום", font=object(), fill=(0, 0, 0))  # type: ignore[arg-type]
    with pytest.raises(KeyError, match="different bbox failure"):
        _rtl_textbbox(draw, (0, 0), "שלום", font=object())  # type: ignore[arg-type]


def test_synthetic_generation_rejects_unknown_template_ids(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = _legacy_synthetic_source(bundle)

    with pytest.raises(ValueError, match="Unsupported synthetic template_id: typo_template"):
        generate_documents(
            count=1,
            seed=7,
            template_ids=["typo_template"],
            font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
            text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
            output_dir=tmp_path / "synthetic",
        )


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


def test_synthetic_generation_rejects_malformed_font_manifest(tmp_path: Path) -> None:
    font_manifest_path = tmp_path / "fonts.yaml"
    text_corpus_path = tmp_path / "corpus.txt"
    font_manifest_path.write_text("not_fonts: []\n", encoding="utf-8")
    text_corpus_path.write_text("שורה ארכיונית תקינה\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing a valid 'fonts' list"):
        generate_documents(
            count=1,
            seed=7,
            template_ids=["printed_letter"],
            font_manifest_path=font_manifest_path,
            text_corpus_path=text_corpus_path,
            output_dir=tmp_path / "out",
        )


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
    source = _legacy_synthetic_source(bundle)
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


def test_rtl_display_text_preserves_logical_hebrew_for_raqm_rendering() -> None:
    assert _rtl_display_text("מכתב מנהלי") == "מכתב מנהלי"
    assert _rtl_display_text("סימן 12") == "סימן 12"
    assert _rtl_display_text("עמוד ABC") == "עמוד ABC"


def test_select_font_rejects_missing_style() -> None:
    with pytest.raises(ValueError, match="No synthetic font registered for style: handwritten_like"):
        _select_font([{"id": "alef-regular", "style": "printed"}], "printed_letter")
