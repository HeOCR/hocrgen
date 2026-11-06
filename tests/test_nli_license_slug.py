"""F8c: NLI rights keyed on the IIIF manifest licence slug, and free-use printed books."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml

from hocrgen.classify.heuristics import classify_items
from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.nli import NliFetcher, read_seed_capture
from hocrgen.fetchers.nli_iiif import (
    NLI_CAPTURE_FORMAT,
    NLI_FREE_USE_LICENSE_URL,
    NliManifestCapture,
    capture_from_payload,
    decide_nli_rights,
    nli_license_slug,
    trim_manifest,
)
from hocrgen.manifests.models import CuratedItemRecord, EnrichedCandidateRecord
from hocrgen.pipeline import _item_from_enriched
from hocrgen.source_ops import evaluate_source_health, source_health_summary
from hocrgen.tools import nli_search_discovery
from hocrgen.tools.nli_seed_promotion import (
    ExtractedSeedPage,
    _extract_failure_reason,
    _extract_rights_hint,
    _normalize_nli_rights,
    build_cached_promotion,
    build_promotion,
    capture_seed_via_iiif,
    capture_conflicts,
    live_manifest_capture_payload,
    main,
    select_page_rights,
    write_promotion_outputs,
)

FIXTURES = Path(__file__).parent / "fixtures" / "nli" / "f8c"
PACKAGE_NLI = package_root() / "data" / "nli"
LICENSE_BASE = "https://www.nli.org.il/contenteditors/pages-for-terms-of-use/"
NC_URL = f"{LICENSE_BASE}public-domain-non-commercial-use"


def _manifest(license_values, canvases: int = 1) -> dict:
    return {
        "@id": "https://iiif.nli.org.il/IIIFv21/DOCID/NNL_ALEPH000/manifest",
        "label": "Test book",
        "license": license_values,
        "attribution": ["מאוסף הספרייה הלאומית"],
        "sequences": [
            {
                "@id": "seq",
                "canvases": [
                    {
                        "@id": f"https://iiif.nli.org.il/IIIFv21/FL{index}",
                        "label": f"jpg_{index}",
                        "images": [{"resource": {"service": {"@id": f"https://iiif.nli.org.il/IIIFv21/FL{index}"}}}],
                    }
                    for index in range(canvases)
                ],
            }
        ],
    }


def _capture(license_values=None, *, canvases: int = 3, status: int = 200) -> NliManifestCapture:
    manifest = None if status != 200 else _manifest([NLI_FREE_USE_LICENSE_URL] if license_values is None else license_values, canvases)
    return NliManifestCapture(
        manifest_url="https://iiif.nli.org.il/IIIFv21/000/manifest",
        http_status=status,
        canvas_count=canvases if status == 200 else None,
        manifest=manifest,
    )


# --- rights decision ---------------------------------------------------------------------------


def test_legacy_display_string_path_is_unchanged() -> None:
    decision = decide_nli_rights(display_rights="Any Use Permitted", capture=None)
    assert decision.accepted
    assert decision.gate_reason is None
    assert decision.raw_rights_text == "Any Use Permitted"
    assert decide_nli_rights(display_rights="Copyright", capture=None).raw_rights_text == "Copyright"


def test_free_use_slug_is_accepted_and_canonicalised() -> None:
    decision = decide_nli_rights(display_rights=None, capture=_capture())
    assert decision.accepted
    assert decision.reason == "nli_license_slug_free_use"
    assert decision.raw_rights_text == NLI_FREE_USE_LICENSE_URL
    http_variant = _capture([NLI_FREE_USE_LICENSE_URL.replace("https://www.", "http://")])
    assert decide_nli_rights(display_rights="Any Use Permitted", capture=http_variant).raw_rights_text == NLI_FREE_USE_LICENSE_URL


@pytest.mark.parametrize(
    ("slug", "reason", "hint"),
    [
        ("public-domain-non-commercial-use", "nli_license_non_commercial:public-domain-non-commercial-use", "RESTRICTED-NONOPEN"),
        ("nli-non-commercial", "nli_license_non_commercial:nli-non-commercial", "RESTRICTED-NONOPEN"),
        ("non-commercial-use-license", "nli_license_non_commercial:non-commercial-use-license", "RESTRICTED-NONOPEN"),
        ("fair-use", "nli_license_not_free_use:fair-use", "UNKNOWN"),
        ("no-license-subject-to-copyright", "nli_license_not_free_use:no-license-subject-to-copyright", "UNKNOWN"),
        ("nli-copying-prohibited", "nli_license_not_free_use:nli-copying-prohibited", "UNKNOWN"),
        ("free-use-license", "nli_license_not_free_use:free-use-license", "UNKNOWN"),
        ("public-domain-photographs-free-use", "nli_license_not_free_use:public-domain-photographs-free-use", "UNKNOWN"),
    ],
)
def test_every_other_slug_is_rejected_with_an_explicit_reason(slug: str, reason: str, hint: str) -> None:
    decision = decide_nli_rights(display_rights=None, capture=_capture([f"{LICENSE_BASE}{slug}"]))
    assert not decision.accepted
    assert decision.gate_reason == reason
    assert decision.normalized_license_hint == hint
    assert decision.license_slug == slug


@pytest.mark.parametrize(
    ("capture", "display", "reason"),
    [
        (_capture([NC_URL]), "Any Use Permitted", "nli_license_display_mismatch"),
        (_capture(), "Copyright", "nli_license_display_mismatch"),
        (_capture([]), None, "nli_license_missing"),
        (_capture([NLI_FREE_USE_LICENSE_URL, NC_URL]), None, "nli_license_ambiguous"),
        (_capture(["https://example.com/terms/public-domain-free-use"]), None, "nli_license_url_unrecognized"),
        (_capture([f"{LICENSE_BASE}a/b"]), None, "nli_license_url_unrecognized"),
        (_capture(canvases=0), None, "nli_iiif_manifest_zero_canvases"),
        (_capture(status=403), None, "nli_iiif_manifest_http_403"),
        (_capture(status=500), None, "nli_iiif_manifest_http_500"),
        (NliManifestCapture(manifest_url="u", http_status=200, canvas_count=1, manifest=None), None, "nli_iiif_manifest_missing"),
    ],
)
def test_unclear_rights_and_broken_manifests_are_rejected(capture, display, reason) -> None:
    decision = decide_nli_rights(display_rights=display, capture=capture)
    assert not decision.accepted
    assert decision.reason == reason


def test_license_slug_parser_accepts_only_nli_terms_urls() -> None:
    assert nli_license_slug(NLI_FREE_USE_LICENSE_URL) == "public-domain-free-use"
    assert nli_license_slug(f"https://nli.org.il/contenteditors/pages-for-terms-of-use/FAIR-USE/") == "fair-use"
    assert nli_license_slug("ftp://www.nli.org.il/contenteditors/pages-for-terms-of-use/x") is None
    assert nli_license_slug("https://www.nli.org.il/other/public-domain-free-use") is None
    assert nli_license_slug(LICENSE_BASE) is None


def test_capture_payload_validation() -> None:
    good = {"capture_format": NLI_CAPTURE_FORMAT, "manifest_url": "u", "http_status": 403, "manifest": None, "canvas_count": None}
    assert capture_from_payload(good).http_status == 403
    for bad, message in [
        ([], "JSON object"),
        ({**good, "capture_format": "other"}, "capture_format"),
        ({**good, "manifest_url": ""}, "manifest_url"),
        ({**good, "http_status": "403"}, "http_status"),
        ({**good, "manifest": []}, "manifest must"),
        ({**good, "http_status": 200}, "must include the manifest"),
        ({**good, "canvas_count": -1}, "canvas_count"),
        ({**good, "http_status": 200, "manifest": {}, "canvas_count": None}, "canvas_count"),
        ({**good, "selected_canvases": [1]}, "selected_canvases"),
    ]:
        with pytest.raises(ValueError, match=message):
            capture_from_payload(bad)
    capture = capture_from_payload({**good, "http_status": 200, "manifest": {"license": "x", "attribution": "NLI"}, "canvas_count": 2})
    assert capture.license_values == ["x"]
    assert capture.attribution == ["NLI"]
    assert NliManifestCapture(manifest_url="u", http_status=403, canvas_count=None, manifest=None).attribution == []
    assert NliManifestCapture(manifest_url="u", http_status=200, canvas_count=0, manifest={"attribution": 3}).attribution == []


def test_trim_manifest_keeps_rights_fields_and_selected_canvases_only() -> None:
    manifest = _manifest([NLI_FREE_USE_LICENSE_URL], canvases=4) | {"structures": ["dropped"]}
    manifest["sequences"].append("not-a-sequence")
    trimmed = trim_manifest(manifest, ["https://iiif.nli.org.il/IIIFv21/FL2"])
    assert "structures" not in trimmed
    assert trimmed["license"] == [NLI_FREE_USE_LICENSE_URL]
    assert [canvas["@id"] for canvas in trimmed["sequences"][0]["canvases"]] == ["https://iiif.nli.org.il/IIIFv21/FL2"]


def test_display_normalisation_never_maps_non_commercial_wording_to_free_use() -> None:
    assert _normalize_nli_rights("Public domain, non-commercial use only") == "Public domain, non-commercial use only"
    assert _normalize_nli_rights("Public domain") == "Any Use Permitted"


# --- packaged printed-book seeds -----------------------------------------------------------------


def _catalog_items() -> list[dict]:
    """Every packaged NLI seed: the runnable manifest (the F8c printed books since F8g) and the exploratory catalog."""

    return [
        *yaml.safe_load((PACKAGE_NLI / "seeds.yaml").read_text(encoding="utf-8"))["items"],
        *yaml.safe_load((PACKAGE_NLI / "seed_catalog.yaml").read_text(encoding="utf-8"))["items"],
    ]


def test_packaged_printed_seeds_are_runnable_pinned_and_free_use() -> None:
    """F8g promoted the three cached F8c printed books from the exploratory catalog to runnable seeds."""

    items = {item["id"]: item for item in _catalog_items()}
    runnable_ids = {item["id"] for item in yaml.safe_load((PACKAGE_NLI / "seeds.yaml").read_text(encoding="utf-8"))["items"]}
    catalog_ids = {item["id"] for item in yaml.safe_load((PACKAGE_NLI / "seed_catalog.yaml").read_text(encoding="utf-8"))["items"]}
    assert len(runnable_ids) == 30
    assert not runnable_ids & catalog_ids
    assert {"nli-pb-001", "nli-pb-002", "nli-pb-003"} <= runnable_ids
    captured = [item for item in items.values() if item.get("iiif_manifest_capture")]
    assert [item["id"] for item in captured] == ["nli-pb-001", "nli-pb-002", "nli-pb-003"]
    for item in captured:
        assert item["content_type"] == "printed_historical"
        assert item["period"] == "historical"
        capture_path = PACKAGE_NLI / item["iiif_manifest_capture"].removeprefix("package://data/nli/")
        assert hashlib.sha256(capture_path.read_bytes()).hexdigest() == item["iiif_manifest_capture_sha256"]
        result = read_seed_capture(capture_path, item["iiif_manifest_capture_sha256"])
        decision = decide_nli_rights(display_rights=None, capture=result.capture)
        assert decision.accepted, item["id"]
        assert result.capture.canvas_count > 0
        assert result.capture.attribution == ["מאוסף הספרייה הלאומית"]
        assert len(result.capture.selected_canvases) == 2
        for selected in result.capture.selected_canvases:
            asset_path = PACKAGE_NLI / selected["asset"]
            assert hashlib.sha256(asset_path.read_bytes()).hexdigest() == selected["sha256"]
            assert asset_path.stat().st_size < 300_000
        assert "/Users/" not in capture_path.read_text(encoding="utf-8")
    # The candidate whose images returned HTTP 500 stays listed, without a fixture, rather than dropped.
    assert items["nli-pb-004"].get("fixture_html") is None
    assert "HTTP 500" in items["nli-pb-004"]["notes"]


# --- fetcher, policy gate and source health -------------------------------------------------------


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_f8c_seed_manifest(tmp_path: Path, *, bad_pin: bool = False) -> Path:
    printed = [item for item in _catalog_items() if item.get("iiif_manifest_capture")]
    items = [
        *printed,
        {
            "id": "nli-nc-001",
            "url": "https://www.nli.org.il/en/books/NNL_ALEPH990012682310205171",
            "title": "Google-class non-commercial book",
            "iiif_manifest_capture": "non_commercial_capture.json",
            "iiif_manifest_capture_sha256": _sha(FIXTURES / "non_commercial_capture.json"),
        },
        {
            "id": "nli-nolicense-001",
            "url": "https://www.nli.org.il/en/books/NNL_ALEPH990012682300205171",
            "iiif_manifest_capture": "no_license_capture.json",
            "iiif_manifest_capture_sha256": _sha(FIXTURES / "no_license_capture.json"),
        },
        {
            "id": "nli-zero-001",
            "url": "https://www.nli.org.il/en/books/NNL_ALEPH990017258900205171",
            "iiif_manifest_capture": "zero_canvas_capture.json",
            "iiif_manifest_capture_sha256": _sha(FIXTURES / "zero_canvas_capture.json"),
        },
        {
            "id": "nli-403-001",
            "url": "https://www.nli.org.il/en/books/NNL_ALEPH990017916250205171",
            "iiif_manifest_capture": "http_403_capture.json",
            "iiif_manifest_capture_sha256": _sha(FIXTURES / "http_403_capture.json"),
        },
        {
            "id": "nli-mismatch-001",
            "url": "https://www.nli.org.il/en/books/mismatch",
            "fixture_html": "item_display_any_use.html",
            "iiif_manifest_capture": "non_commercial_capture.json",
            "iiif_manifest_capture_sha256": "0" * 64 if bad_pin else _sha(FIXTURES / "non_commercial_capture.json"),
        },
    ]
    seed_dir = tmp_path / "seeds"
    shutil.copytree(FIXTURES, seed_dir)
    shutil.copytree(FIXTURES.parent / "assets", tmp_path / "assets")
    seed_path = seed_dir / "seeds_f8c.yaml"
    seed_path.write_text(yaml.safe_dump({"items": items}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return seed_path


def _bundle_with_seed_manifest(tmp_path: Path, seed_path: Path):
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    sources_path = config_root / "sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace("package://data/nli/seeds.yaml", str(seed_path)),
        encoding="utf-8",
    )
    return load_and_validate_bundle(config_root)


def _items_by_id(tmp_path: Path, *, bad_pin: bool = False, profile: str = "profile_open_v1"):
    bundle = _bundle_with_seed_manifest(tmp_path, _write_f8c_seed_manifest(tmp_path, bad_pin=bad_pin))
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")
    fetcher = NliFetcher()
    candidates = fetcher.discover_candidates(source, bundle, StageOptions())
    enriched = fetcher.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
    return bundle, {record.source_item_id: _item_from_enriched(record, source, bundle, profile) for record in enriched}


def test_policy_gate_admits_free_use_printed_books_and_rejects_the_rest_with_reasons(tmp_path: Path) -> None:
    _bundle, items = _items_by_id(tmp_path)
    for seed_id in ("nli-pb-001", "nli-pb-002", "nli-pb-003"):
        item = items[seed_id]
        assert item.eligibility == "accepted", seed_id
        assert item.normalized_license == "PD-IL"
        assert item.rights_classification.value == "open"
        assert item.raw_rights_text == NLI_FREE_USE_LICENSE_URL
        assert item.metadata["content_type"] == "printed_historical"
        assert item.metadata["nli_rights"]["rights_basis"] == "iiif_manifest_license_slug"
        assert item.metadata["nli_rights"]["iiif_canvas_count"] > 0
        assert "iiif_manifest_capture" not in item.metadata
        assert "rights_gate" not in item.metadata
        assert len(item.asset_references) == 2
    expected = {
        "nli-nc-001": ("nli_license_non_commercial:public-domain-non-commercial-use", "RESTRICTED-NONOPEN"),
        "nli-nolicense-001": ("nli_license_not_free_use:no-license-subject-to-copyright", "UNKNOWN"),
        "nli-zero-001": ("nli_iiif_manifest_zero_canvases", "UNKNOWN"),
        "nli-403-001": ("nli_iiif_manifest_http_403", "UNKNOWN"),
        "nli-mismatch-001": ("nli_license_display_mismatch", "UNKNOWN"),
    }
    for seed_id, (reason, license_id) in expected.items():
        item = items[seed_id]
        assert item.eligibility == "rejected", seed_id
        assert item.eligibility_reason == reason
        assert item.normalized_license == license_id
        assert item.metadata["rights_gate"]["reason"] == reason
    assert items["nli-403-001"].asset_references == []


def test_policy_gate_rejects_in_the_review_profile_too(tmp_path: Path) -> None:
    _bundle, items = _items_by_id(tmp_path, profile="profile_review_v1")
    assert items["nli-nc-001"].eligibility == "rejected"
    assert items["nli-nc-001"].rights_classification.value == "restricted_review_only"


def test_checksum_pin_mismatch_is_rejected_not_trusted(tmp_path: Path) -> None:
    _bundle, items = _items_by_id(tmp_path, bad_pin=True)
    assert items["nli-mismatch-001"].eligibility_reason == "nli_iiif_capture_checksum_mismatch"


def test_rights_gate_can_never_admit_an_item(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")
    record = EnrichedCandidateRecord(
        candidate_id="nli_any_use_permitted:x",
        source_id=source.id,
        source_item_id="x",
        source_url="https://example.com",
        discovery_method="seed_manifest",
        raw_rights_text="Any Use Permitted",
        metadata={"rights_gate": {"decision": "rejected", "normalized_license": "PD-IL", "reason": "custom"}},
    )
    item = _item_from_enriched(record, source, bundle, "profile_open_v1")
    assert (item.eligibility, item.eligibility_reason, item.normalized_license) == ("rejected", "custom", "UNKNOWN")
    record.metadata["rights_gate"] = {"decision": "rejected"}
    assert _item_from_enriched(record, source, bundle, "profile_open_v1").eligibility_reason == "rights_gate_rejected"


def test_fetcher_handles_missing_and_malformed_captures(tmp_path: Path) -> None:
    with pytest.raises(StageExecutionError, match="capture is missing"):
        read_seed_capture(tmp_path / "missing.json", None)
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    result = read_seed_capture(bad, None)
    assert result.capture is None and result.failure_reason.startswith("nli_iiif_capture_invalid")


def test_source_health_surfaces_broken_and_non_free_manifests_without_failing(tmp_path: Path) -> None:
    bundle = _bundle_with_seed_manifest(tmp_path, _write_f8c_seed_manifest(tmp_path))
    health = next(result for result in evaluate_source_health(bundle, "profile_open_v1", StageOptions()) if result.source_id == "nli_any_use_permitted")
    assert health.health_status == "ok"
    assert health.extra["iiif_manifest_capture_count"] == 8
    assert health.extra["iiif_recorded_failure_count"] == 4
    issues = {issue["seed_id"]: issue for issue in health.extra["iiif_manifest_issues"]}
    assert set(issues) == {"nli-nc-001", "nli-nolicense-001", "nli-zero-001", "nli-403-001", "nli-mismatch-001"}
    assert issues["nli-403-001"]["http_status"] == 403
    assert issues["nli-zero-001"]["canvas_count"] == 0
    assert issues["nli-zero-001"]["reason"] == "nli_iiif_manifest_zero_canvases"
    names = [check["name"] for check in health.checks]
    assert {"iiif_manifest_capture", "iiif_manifest_capture_sha256"} <= set(names)
    # Binding is checked for the three admitted printed books only; rejected items are never acquired.
    assert names.count("iiif_capture_asset_binding") == 3
    summary = source_health_summary([health])
    assert summary["nli_iiif_manifest_issues"][0]["source_id"] == "nli_any_use_permitted"
    assert len(summary["nli_iiif_manifest_issues"][0]["issues"]) == 5


def test_source_health_fails_on_integrity_problems(tmp_path: Path) -> None:
    seed_path = _write_f8c_seed_manifest(tmp_path, bad_pin=True)
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    data["items"].append({"id": "nli-unpinned", "url": "u", "iiif_manifest_capture": "http_403_capture.json"})
    data["items"].append({"id": "nli-missing", "url": "u", "iiif_manifest_capture": "nope.json", "iiif_manifest_capture_sha256": "0" * 64})
    (seed_path.parent / "broken_capture.json").write_text("{}", encoding="utf-8")
    data["items"].append(
        {"id": "nli-broken", "url": "u", "iiif_manifest_capture": "broken_capture.json", "iiif_manifest_capture_sha256": _sha(seed_path.parent / "broken_capture.json")}
    )
    seed_path.write_text(yaml.safe_dump({"items": data["items"]}, allow_unicode=True), encoding="utf-8")
    bundle = _bundle_with_seed_manifest(tmp_path, seed_path)
    health = next(result for result in evaluate_source_health(bundle, "profile_open_v1", StageOptions()) if result.source_id == "nli_any_use_permitted")
    assert health.health_status == "error"
    failing = {check["name"] for check in health.checks if check["status"] == "error"}
    assert failing == {"iiif_manifest_capture", "iiif_manifest_capture_sha256", "iiif_manifest_capture_parse"}


def test_packaged_source_health_counts_the_promoted_printed_books() -> None:
    bundle = load_and_validate_bundle()
    health = next(result for result in evaluate_source_health(bundle, "profile_open_v1", StageOptions()) if result.source_id == "nli_any_use_permitted")
    # F8g: the three printed books are runnable seeds now, each with its pinned capture.
    assert health.extra == {
        "iiif_manifest_capture_count": 3,
        "iiif_manifest_issues": [],
        "iiif_recorded_failure_count": 0,
        "source_depth_asset_count": 30,
        "source_depth_candidate_count": 30,
    }
    assert source_health_summary([health])["nli_iiif_manifest_issues"] == []


def test_declared_printed_content_type_classifies_as_printed_historical(tmp_path: Path) -> None:
    bundle, items = _items_by_id(tmp_path)
    base = items["nli-pb-001"].model_dump()
    extra = {"qa_status": "pass", "content_fingerprint": "f", "dedupe_status": "retained"}
    curated = CuratedItemRecord(**base, **extra, canonical_item_id=base["item_id"])
    other = CuratedItemRecord(
        **{**base, "item_id": "nli_any_use_permitted:other", "metadata": {**base["metadata"], "content_type": "typewritten_historical"}},
        **extra,
        canonical_item_id="other",
    )
    hand = CuratedItemRecord(
        **{**base, "item_id": "nli_any_use_permitted:hand", "metadata": {**base["metadata"], "content_type": "manuscript_scan"}},
        **extra,
        canonical_item_id="hand",
    )
    classified = {item.item_id: item for item in classify_items([curated, other, hand], bundle).classified_items}
    printed = classified["nli_any_use_permitted:nli-pb-001"]
    assert (printed.content_class, printed.content_confidence) == ("printed", 0.9)
    assert printed.period_class == "historical"
    assert classified["nli_any_use_permitted:hand"].content_class == "handwritten"
    assert "content_declared_type_conflicting_source_types" in classified["nli_any_use_permitted:other"].classification_review_reasons


# --- promotion tool ----------------------------------------------------------------------------------


def test_cached_promotion_of_a_printed_seed_carries_f8c_fields(tmp_path: Path) -> None:
    seed = next(item for item in _catalog_items() if item["id"] == "nli-pb-003")
    promotion = build_cached_promotion(
        seed=seed,
        fixture_path=PACKAGE_NLI / "item_nli_pb_003.html",
        require_rights="Any Use Permitted",
        output_dir=PACKAGE_NLI,
        runnable_seeds_path=PACKAGE_NLI / "seeds.yaml",
        seed_manifest_path=PACKAGE_NLI / "seeds.yaml",
    )
    entry = promotion.promoted_seed_entry
    assert promotion.rights == NLI_FREE_USE_LICENSE_URL
    # Same names in the same directory: the re-emitted capture is byte-identical to the pinned one.
    assert entry["iiif_manifest_capture"] == seed["iiif_manifest_capture"]
    assert entry["iiif_manifest_capture_sha256"] == seed["iiif_manifest_capture_sha256"]
    assert entry["content_type"] == "printed_historical"
    assert entry["iiif_canvas_indices"] == seed["iiif_canvas_indices"]
    assert not capture_conflicts(promotion, output_dir=PACKAGE_NLI, overwrite=False)


def test_cached_promotion_rewrites_the_capture_for_renamed_images(tmp_path: Path) -> None:
    seed = dict(next(item for item in _catalog_items() if item["id"] == "nli-pb-003"))
    seed["id"] = "nli-renamed-003"
    out = tmp_path / "out"
    promotion = build_cached_promotion(
        seed=seed,
        fixture_path=PACKAGE_NLI / "item_nli_pb_003.html",
        require_rights="Any Use Permitted",
        output_dir=out,
        runnable_seeds_path=tmp_path / "seeds.yaml",
        seed_manifest_path=PACKAGE_NLI / "seeds.yaml",
    )
    entry = promotion.promoted_seed_entry
    assert entry["iiif_manifest_capture"] == "out/iiif/nli_renamed_003_manifest_capture.json"
    write_promotion_outputs(
        promotions=[promotion],
        output_dir=out,
        runnable_seeds_path=tmp_path / "seeds.yaml",
        seed_catalog_path=tmp_path / "catalog.yaml",
        runnable_manifest={"items": [entry]},
        catalog_manifest={"items": []},
        report_path=tmp_path / "report.json",
        report={},
        overwrite=False,
    )
    rewritten = read_seed_capture(out / "iiif" / "nli_renamed_003_manifest_capture.json", entry["iiif_manifest_capture_sha256"])
    assert [item["asset"] for item in rewritten.capture.selected_canvases] == [
        "assets/nli_renamed_003_page1.jpg",
        "assets/nli_renamed_003_page2.jpg",
    ]
    from hocrgen.fetchers.nli_iiif import capture_asset_problems

    assert capture_asset_problems(rewritten.capture, out, ["assets/nli_renamed_003_page1.jpg", "assets/nli_renamed_003_page2.jpg"]) == []
    # A retry that would produce a different capture is refused before anything is written.
    (out / "iiif" / "nli_renamed_003_manifest_capture.json").write_text("{}\n", encoding="utf-8")
    assert capture_conflicts(promotion, output_dir=out, overwrite=False)
    assert not capture_conflicts(promotion, output_dir=out, overwrite=True)
    with pytest.raises(StageExecutionError, match="nli_iiif_capture_conflict"):
        write_promotion_outputs(
            promotions=[promotion],
            output_dir=out,
            runnable_seeds_path=tmp_path / "seeds.yaml",
            seed_catalog_path=tmp_path / "catalog.yaml",
            runnable_manifest={"items": [entry]},
            catalog_manifest={"items": []},
            report_path=tmp_path / "report.json",
            report={},
            overwrite=False,
        )


def test_cached_promotion_rejects_images_not_bound_to_the_capture(tmp_path: Path) -> None:
    seed = next(item for item in _catalog_items() if item["id"] == "nli-pb-003")
    fixture = tmp_path / "item.html"
    fixture.write_text(
        (PACKAGE_NLI / "item_nli_pb_003.html").read_text(encoding="utf-8").replace("assets/nli_pb_003_page2.jpg", "assets/nli_pb_002_page1.jpg"),
        encoding="utf-8",
    )
    shutil.copytree(PACKAGE_NLI / "assets", tmp_path / "assets", ignore=shutil.ignore_patterns("nli_ms_*", "nli_item_*", "nli_pb_001*"))
    with pytest.raises(StageExecutionError, match="nli_iiif_capture_asset_mismatch.*unbound:assets/nli_pb_002_page1.jpg"):
        build_cached_promotion(
            seed=seed,
            fixture_path=fixture,
            require_rights="Any Use Permitted",
            output_dir=tmp_path / "out",
            runnable_seeds_path=tmp_path / "seeds.yaml",
            seed_manifest_path=PACKAGE_NLI / "seeds.yaml",
        )


def test_cached_promotion_rejects_bad_pins_and_non_free_slugs(tmp_path: Path) -> None:
    seed_dir = _write_f8c_seed_manifest(tmp_path).parent
    base = {"id": "x", "url": "u", "iiif_manifest_capture": "non_commercial_capture.json"}
    kwargs = dict(
        fixture_path=seed_dir / "item_display_any_use.html",
        require_rights="Any Use Permitted",
        output_dir=tmp_path / "out",
        runnable_seeds_path=tmp_path / "out" / "seeds.yaml",
        seed_manifest_path=seed_dir / "seeds_f8c.yaml",
    )
    with pytest.raises(StageExecutionError, match="nli_iiif_capture_checksum_mismatch"):
        build_cached_promotion(seed=base, **kwargs)
    pinned = {**base, "iiif_manifest_capture_sha256": _sha(seed_dir / "non_commercial_capture.json")}
    with pytest.raises(StageExecutionError) as excinfo:
        build_cached_promotion(seed=pinned, **kwargs)
    assert _extract_failure_reason(str(excinfo.value)) == "nli_license_display_mismatch"
    with pytest.raises(StageExecutionError, match="cached manifest capture missing"):
        build_cached_promotion(seed={**pinned, "iiif_manifest_capture": "nope.json"}, **kwargs)
    (seed_dir / "broken.json").write_text("{}", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="nli_iiif_capture_invalid"):
        build_cached_promotion(
            seed={**base, "iiif_manifest_capture": "broken.json", "iiif_manifest_capture_sha256": _sha(seed_dir / "broken.json")},
            **kwargs,
        )


def test_fetcher_rejects_a_fixture_image_swapped_away_from_the_capture(tmp_path: Path) -> None:
    seed = dict(next(item for item in _catalog_items() if item["id"] == "nli-pb-003"))
    data_dir = tmp_path / "nli"
    (data_dir / "assets").mkdir(parents=True)
    for name in ("nli_pb_003_page1.jpg", "nli_pb_002_page1.jpg"):
        shutil.copy(PACKAGE_NLI / "assets" / name, data_dir / "assets" / name)
    (data_dir / "item.html").write_text(
        (PACKAGE_NLI / "item_nli_pb_003.html").read_text(encoding="utf-8").replace("assets/nli_pb_003_page2.jpg", "assets/nli_pb_002_page1.jpg"),
        encoding="utf-8",
    )
    seed["fixture_html"] = "item.html"
    seed_path = data_dir / "seeds.yaml"
    seed_path.write_text(yaml.safe_dump({"items": [seed]}, allow_unicode=True), encoding="utf-8")
    bundle = _bundle_with_seed_manifest(tmp_path, seed_path)
    source = next(source for source in bundle.source_registry.sources if source.id == "nli_any_use_permitted")
    fetcher = NliFetcher()
    enriched = fetcher.fetch_candidate_metadata(source, bundle, fetcher.discover_candidates(source, bundle, StageOptions()), StageOptions())
    item = _item_from_enriched(enriched[0], source, bundle, "profile_open_v1")
    assert (item.eligibility, item.eligibility_reason) == ("rejected", "nli_iiif_capture_asset_mismatch")
    health = next(result for result in evaluate_source_health(bundle, "profile_open_v1", StageOptions()) if result.source_id == "nli_any_use_permitted")
    assert health.health_status == "error"


def test_failure_only_manifest_still_reaches_discovery(tmp_path: Path) -> None:
    seed_dir = _write_f8c_seed_manifest(tmp_path).parent
    items = [
        {"id": "nli-403-only", "url": "u", "iiif_manifest_capture": "http_403_capture.json", "iiif_manifest_capture_sha256": _sha(seed_dir / "http_403_capture.json")},
        {"id": "nli-zero-only", "url": "u", "iiif_manifest_capture": "zero_canvas_capture.json", "iiif_manifest_capture_sha256": _sha(seed_dir / "zero_canvas_capture.json")},
    ]
    seed_path = seed_dir / "failures_only.yaml"
    seed_path.write_text(yaml.safe_dump({"items": items}), encoding="utf-8")
    bundle = _bundle_with_seed_manifest(tmp_path, seed_path)
    health = next(result for result in evaluate_source_health(bundle, "profile_open_v1", StageOptions()) if result.source_id == "nli_any_use_permitted")
    assert health.health_status == "ok"
    assert health.asset_count == 0
    min_assets = next(check for check in health.checks if check["name"] == "min_assets")
    assert min_assets["recorded_upstream_failures"] == 2
    assert health.selected


def test_browser_rights_prefer_item_page_display_over_manifest_licence() -> None:
    assert select_page_rights(label=None, access_rights="Copyright", manifest_license=NLI_FREE_USE_LICENSE_URL, page_fallback=None) == "Copyright"
    assert select_page_rights(label=None, access_rights=None, manifest_license=NLI_FREE_USE_LICENSE_URL, page_fallback="Copyright") == NLI_FREE_USE_LICENSE_URL
    assert select_page_rights(label="Any Use Permitted", access_rights="x", manifest_license=None, page_fallback=None) == "Any Use Permitted"
    extracted = ExtractedSeedPage(
        title="t",
        description="",
        rights="Copyright",
        asset_urls=["https://example.com/a.jpg"],
        license_url=NLI_FREE_USE_LICENSE_URL,
        manifest=_manifest([NLI_FREE_USE_LICENSE_URL]),
    )
    with pytest.raises(StageExecutionError) as excinfo:
        build_promotion(seed={"id": "s", "url": "u"}, extracted=extracted, downloaded_assets=[], require_rights="Any Use Permitted")
    assert _extract_failure_reason(str(excinfo.value)) == "nli_license_display_mismatch"


def test_browser_promotion_persists_a_pinned_capture(tmp_path: Path) -> None:
    manifest = _manifest([NLI_FREE_USE_LICENSE_URL], canvases=2)
    extracted = ExtractedSeedPage(
        title="t",
        description="",
        rights=NLI_FREE_USE_LICENSE_URL,
        asset_urls=["https://example.com/a.jpg"],
        license_url=NLI_FREE_USE_LICENSE_URL,
        manifest=manifest,
    )
    promotion = build_promotion(
        seed={"id": "nli-browser-1", "url": "https://www.nli.org.il/x"},
        extracted=extracted,
        downloaded_assets=[("https://example.com/a.jpg", "image/jpeg", b"\xff\xd8x")],
        require_rights="Any Use Permitted",
        output_dir=tmp_path / "out",
        runnable_seeds_path=tmp_path / "seeds.yaml",
    )
    entry = promotion.promoted_seed_entry
    assert entry["iiif_manifest_capture"] == "out/iiif/nli_browser_1_manifest_capture.json"
    payload = json.loads(promotion.capture_json)
    assert payload["capture_source"] == "browser_viewer_manifest"
    assert payload["manifest_url"] == manifest["@id"]
    assert payload["selected_canvases"][0]["asset"] == "assets/nli_browser_1_page1.jpg"
    assert decide_nli_rights(display_rights=None, capture=capture_from_payload(payload)).accepted
    assert live_manifest_capture_payload({}, manifest_url="", asset_urls=[])["manifest_url"] == "unknown"


def test_browser_manifest_is_slug_checked(tmp_path: Path) -> None:
    extracted = ExtractedSeedPage(
        title="t",
        description="",
        rights=NC_URL,
        asset_urls=["https://example.com/a.jpg"],
        license_url=NC_URL,
        manifest=_manifest([NC_URL]),
    )
    with pytest.raises(StageExecutionError) as excinfo:
        build_promotion(seed={"id": "s", "url": "u"}, extracted=extracted, downloaded_assets=[], require_rights="Any Use Permitted")
    assert _extract_failure_reason(str(excinfo.value)) == "nli_license_non_commercial"
    assert _extract_rights_hint(str(excinfo.value)) == NC_URL


class _FakeIiif:
    def __init__(self, manifest: dict | None, *, status: int = 200, image_status: int = 200, info_status: int = 200):
        self.manifest = manifest
        self.status = status
        self.image_status = image_status
        self.info_status = info_status
        self.requests: list[str] = []

    def __call__(self, url: str):
        self.requests.append(url)
        if url.endswith("/manifest"):
            return self.status, "application/json", json.dumps(self.manifest or {}).encode("utf-8")
        if url.endswith("/info.json"):
            body = json.dumps({"rights": "http://web.nli.org.il/x/nli-copying-prohibited.aspx"}).encode("utf-8")
            return self.info_status, "application/json", body if self.info_status == 200 else b""
        return self.image_status, "image/jpeg", b"\xff\xd8fake-jpeg"


SEED = {
    "id": "nli-pb-test",
    "url": "https://www.nli.org.il/en/books/test",
    "iiif_manifest_url": "https://iiif.nli.org.il/IIIFv21/000/manifest",
    "content_type": "printed_historical",
    "period": "historical",
}


def _run_capture(fake: _FakeIiif, seed: dict | None = None):
    return capture_seed_via_iiif(seed=seed or SEED, fetch=fake, sleep=lambda _s: None)


def test_iiif_capture_builds_a_pinned_trimmed_capture(tmp_path: Path) -> None:
    manifest = _manifest([NLI_FREE_USE_LICENSE_URL], canvases=5)
    manifest["metadata"] = [{"label": "Publisher", "value": "ליוורנו$$Qx"}, {"label": "Type", "value": "book"}]
    fake = _FakeIiif(manifest)
    extracted, downloads, payload = _run_capture(fake, {**SEED, "iiif_canvas_indices": [3, 4]})
    assert extracted.license_url == NLI_FREE_USE_LICENSE_URL
    assert extracted.description == "ליוורנו | book"
    assert len(downloads) == 2
    assert payload["canvas_count"] == 5
    assert [item["index"] for item in payload["selected_canvases"]] == [3, 4]
    assert payload["selected_canvases"][0]["image_service_rights"].endswith("nli-copying-prohibited.aspx")
    assert len(payload["manifest"]["sequences"][0]["canvases"]) == 2
    promotion = build_promotion(
        seed={**SEED, "iiif_canvas_indices": [3, 4]},
        extracted=extracted,
        downloaded_assets=downloads,
        require_rights="Any Use Permitted",
        output_dir=tmp_path / "out",
        runnable_seeds_path=tmp_path / "seeds.yaml",
        capture_payload=payload,
    )
    assert promotion.rights == NLI_FREE_USE_LICENSE_URL
    entry = promotion.promoted_seed_entry
    assert entry["iiif_manifest_capture"] == "out/iiif/nli_pb_test_manifest_capture.json"
    assert entry["iiif_manifest_capture_sha256"] == hashlib.sha256(promotion.capture_json.encode("utf-8")).hexdigest()
    written = json.loads(promotion.capture_json)
    assert written["selected_canvases"][0]["asset"] == "assets/nli_pb_test_page1.jpg"
    write_promotion_outputs(
        promotions=[promotion],
        output_dir=tmp_path / "out",
        runnable_seeds_path=tmp_path / "seeds.yaml",
        seed_catalog_path=tmp_path / "catalog.yaml",
        runnable_manifest={"items": [entry]},
        catalog_manifest={"items": []},
        report_path=tmp_path / "report.json",
        report={},
        overwrite=False,
    )
    capture_path = tmp_path / "out" / "iiif" / "nli_pb_test_manifest_capture.json"
    assert _sha(capture_path) == entry["iiif_manifest_capture_sha256"]
    assert decide_nli_rights(display_rights=None, capture=read_seed_capture(capture_path, entry["iiif_manifest_capture_sha256"]).capture).accepted
    default_extracted, default_downloads, _payload = _run_capture(_FakeIiif(manifest, info_status=404))
    assert len(default_downloads) == 2
    assert build_promotion(
        seed=SEED, extracted=default_extracted, downloaded_assets=default_downloads, require_rights="x", capture_payload=_payload
    ).promoted_seed_entry["iiif_manifest_capture"].startswith("package://data/nli/iiif/")


@pytest.mark.parametrize(
    ("fake", "seed", "reason"),
    [
        (_FakeIiif(_manifest([NC_URL])), None, "nli_license_non_commercial"),
        (_FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL], canvases=0)), None, "nli_iiif_manifest_zero_canvases"),
        (_FakeIiif(None, status=403), None, "nli_iiif_manifest_http_403"),
        (_FakeIiif(None, status=500), None, "nli_iiif_manifest_http_500"),
        (_FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL])), {**SEED, "iiif_canvas_indices": [9]}, "nli_iiif_canvas_index_out_of_range"),
        (_FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL]), image_status=500), None, "download_failed"),
        (_FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL])), {"id": "x", "url": "u"}, "nli_iiif_manifest_url_missing"),
    ],
)
def test_iiif_capture_failures_have_explicit_reasons(fake: _FakeIiif, seed, reason: str) -> None:
    with pytest.raises(StageExecutionError) as excinfo:
        _run_capture(fake, seed)
    assert _extract_failure_reason(str(excinfo.value)) == reason
    if reason.startswith("nli_license_"):
        assert all(url.endswith("/manifest") for url in fake.requests), "no image may be requested for non-free items"


def test_iiif_capture_rejects_non_json_and_imageless_canvases() -> None:
    class Garbage(_FakeIiif):
        def __call__(self, url):
            return 200, "text/html", b"<html>"

    with pytest.raises(StageExecutionError, match="nli_iiif_capture_invalid"):
        _run_capture(Garbage(None))

    class ListManifest(_FakeIiif):
        def __call__(self, url):
            return 200, "application/json", b"[]"

    with pytest.raises(StageExecutionError, match="not an object"):
        _run_capture(ListManifest(None))
    manifest = _manifest([NLI_FREE_USE_LICENSE_URL])
    manifest["sequences"][0]["canvases"][0]["images"] = []
    with pytest.raises(StageExecutionError, match="no image service"):
        _run_capture(_FakeIiif(manifest))
    info_garbage = _FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL]))
    original = info_garbage.__call__

    def fetch(url):
        if url.endswith("/info.json"):
            return 200, "application/json", b"not-json"
        return original(url)

    _extracted, _downloads, payload = capture_seed_via_iiif(seed=SEED, fetch=fetch, sleep=lambda _s: None)
    assert payload["selected_canvases"][0]["image_service_rights"] is None


def test_main_iiif_mode_reports_failures_instead_of_dropping_them(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    catalog = tmp_path / "catalog.yaml"
    runnable = tmp_path / "seeds.yaml"
    catalog.write_text(yaml.safe_dump({"items": [SEED]}), encoding="utf-8")
    runnable.write_text("items: []\n", encoding="utf-8")

    def fake_capture(**_kwargs):
        raise StageExecutionError("nli_iiif_manifest_http_500: nli-pb-test")

    monkeypatch.setattr("hocrgen.tools.nli_seed_promotion.capture_seed_via_iiif", fake_capture)
    code = main(
        [
            "--seed-catalog",
            str(catalog),
            "--runnable-seeds",
            str(runnable),
            "--output-dir",
            str(tmp_path / "out"),
            "--report-path",
            str(tmp_path / "report.json"),
            "--capture-mode",
            "iiif",
            "--dry-run",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 1
    assert report["failed_seeds"] == [
        {"seed_id": "nli-pb-test", "reason": "nli_iiif_manifest_http_500", "message": "nli_iiif_manifest_http_500: nli-pb-test", "rights": None}
    ]


def test_main_iiif_mode_writes_capture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    catalog = tmp_path / "catalog.yaml"
    runnable = tmp_path / "seeds.yaml"
    catalog.write_text(yaml.safe_dump({"items": [SEED]}), encoding="utf-8")
    runnable.write_text("items: []\n", encoding="utf-8")
    fake = _FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL], canvases=3))
    monkeypatch.setattr(
        "hocrgen.tools.nli_seed_promotion.capture_seed_via_iiif",
        lambda **kwargs: capture_seed_via_iiif(seed=kwargs["seed"], fetch=fake, sleep=lambda _s: None),
    )
    code = main(
        [
            "--seed-catalog",
            str(catalog),
            "--runnable-seeds",
            str(runnable),
            "--output-dir",
            str(tmp_path / "out"),
            "--report-path",
            str(tmp_path / "report.json"),
            "--capture-mode",
            "iiif",
        ]
    )
    capsys.readouterr()
    assert code == 0
    assert (tmp_path / "out" / "iiif" / "nli_pb_test_manifest_capture.json").exists()
    promoted = yaml.safe_load(runnable.read_text(encoding="utf-8"))["items"][0]
    assert promoted["iiif_manifest_capture"] == "out/iiif/nli_pb_test_manifest_capture.json"


# --- Search API discovery (operator only) ----------------------------------------------------------

SECRET = "test-key-value-123"


def _search_record(record_id: str, manifest: str | None) -> dict:
    dc = nli_search_discovery.DC
    record = {
        "@id": f"https://www.nli.org.il/en/books/NNL_ALEPH{record_id}",
        f"{dc}recordid": [{"@value": record_id}],
        f"{dc}title": [{"@value": f"Book {record_id}"}],
        f"{dc}type": [{"@value": "book"}],
        f"{dc}accessRights": [{"@value": "online_and_api_access"}],
        f"{dc}non_standard_date": [{"@value": "[תקע\"ט]"}],
    }
    if manifest:
        record[f"{dc}relation"] = [{"@id": manifest}]
    return record


def test_discovery_without_key_degrades_to_hand_vetted_seeds(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("NLI_API_KEY", raising=False)

    def no_network(_url):
        raise AssertionError("no request may be made without a key")

    report = nli_search_discovery.discover(query="title,contains,הגדה", api_key=None, fetch=no_network)
    assert report["status"] == "no_api_key"
    assert report["candidates"] == []
    assert nli_search_discovery.main(["--query", "x"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "no_api_key"


def test_discovery_checks_each_manifest_slug_and_never_leaks_the_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    manifests = {
        "https://iiif.nli.org.il/IIIFv21/1/manifest": _manifest([NLI_FREE_USE_LICENSE_URL], canvases=4),
        "https://iiif.nli.org.il/IIIFv21/2/manifest": _manifest([NC_URL], canvases=4),
    }
    requested: list[str] = []

    def fetch(url: str):
        requested.append(url)
        if url.startswith(nli_search_discovery.NLI_SEARCH_ENDPOINT):
            assert f"api_key={SECRET}" in url
            records = [
                _search_record("1", "https://iiif.nli.org.il/IIIFv21/1/manifest"),
                _search_record("2", "https://iiif.nli.org.il/IIIFv21/2/manifest"),
                _search_record("3", "https://iiif.nli.org.il/IIIFv21/3/manifest"),
                _search_record("4", None),
                "not-a-record",
            ]
            return 200, json.dumps(records).encode("utf-8")
        if url in manifests:
            return 200, json.dumps(manifests[url]).encode("utf-8")
        return 403, b""

    monkeypatch.setattr(nli_search_discovery, "fetch_url", fetch)
    monkeypatch.setattr(nli_search_discovery.time, "sleep", lambda _s: None)
    monkeypatch.setenv("NLI_API_KEY", SECRET)
    report_path = tmp_path / "report.json"
    assert nli_search_discovery.main(["--query", "title,contains,הגדה", "--report-path", str(report_path), "--request-delay", "0"]) == 0
    out = capsys.readouterr().out
    text = report_path.read_text(encoding="utf-8")
    assert SECRET not in out and SECRET not in text
    report = json.loads(text)
    assert "api_key" not in report["query_parameters"]
    checks = {candidate["record_id"]: candidate.get("manifest_check") for candidate in report["candidates"]}
    assert checks["1"]["decision"] == "accepted"
    assert checks["2"]["reason"] == "nli_license_non_commercial:public-domain-non-commercial-use"
    assert checks["3"]["reason"] == "nli_iiif_manifest_http_403"
    assert checks["4"] is None
    assert [entry["iiif_manifest_url"] for entry in report["suggested_catalog_entries"]] == ["https://iiif.nli.org.il/IIIFv21/1/manifest"]


def test_discovery_reports_search_failures_and_caps_manifest_checks() -> None:
    assert nli_search_discovery.discover(query="q", api_key=SECRET, fetch=lambda _u: (502, b""))["status"] == "search_failed"
    bad = nli_search_discovery.discover(query="q", api_key=SECRET, fetch=lambda _u: (200, b"<html>"))
    assert bad["status"] == "search_failed" and SECRET not in json.dumps(bad)
    odd = nli_search_discovery.discover(query="q", api_key=SECRET, fetch=lambda _u: (200, b"{}"))
    assert odd["status"] == "ok" and odd["candidates"] == []

    def fetch(url: str):
        if url.startswith(nli_search_discovery.NLI_SEARCH_ENDPOINT):
            return 200, json.dumps([_search_record(str(i), f"https://iiif.nli.org.il/IIIFv21/{i}/manifest") for i in range(3)]).encode()
        return 200, b"not json"

    capped = nli_search_discovery.discover(query="q", api_key=SECRET, fetch=fetch, sleep=lambda _s: None, max_manifest_checks=1, material_type=None, availability_type=None)
    assert capped["manifest_checks"] == 1
    assert capped["candidates"][0]["manifest_check"]["reason"] == "nli_iiif_manifest_missing"
    assert "material_type" not in capped["query_parameters"]
    assert nli_search_discovery.redact("a test-key-value-123 b", SECRET) == "a [REDACTED] b"
    assert nli_search_discovery.redact("x", None) == "x"


def test_manifest_helpers_tolerate_malformed_upstream_shapes(tmp_path: Path) -> None:
    from hocrgen.fetchers.nli import resolve_seed_local_reference
    from hocrgen.fetchers.nli_iiif import canvas_image_service, manifest_canvases, manifest_license_values

    assert NliManifestCapture(manifest_url="u", http_status=403, canvas_count=None, manifest=None).license_values is None
    assert manifest_license_values({"license": " https://x "}) == ["https://x"]
    assert manifest_license_values({"license": 7}) == []
    assert manifest_canvases({"sequences": "x"}) == []
    assert manifest_canvases({"sequences": ["x", {"canvases": ["y", {"@id": "c"}]}]}) == [{"@id": "c"}]
    assert canvas_image_service({"images": ["x", {"resource": {"service": "bad"}}]}) is None
    absolute = tmp_path / "capture.json"
    bundle = load_and_validate_bundle()
    assert resolve_seed_local_reference(str(absolute), seed_manifest=tmp_path / "seeds.yaml", bundle=bundle) == absolute


def test_capture_asset_problems_reports_unpinned_and_changed_images(tmp_path: Path) -> None:
    from hocrgen.fetchers.nli_iiif import capture_asset_problems

    (tmp_path / "a.jpg").write_bytes(b"a")
    (tmp_path / "b.jpg").write_bytes(b"b")
    capture = NliManifestCapture(
        manifest_url="u",
        http_status=200,
        canvas_count=2,
        manifest={},
        selected_canvases=[{"asset": "a.jpg"}, {"asset": "b.jpg", "sha256": "0" * 64}, {"asset": "c.jpg", "sha256": "1"}],
    )
    assert capture_asset_problems(capture, tmp_path, ["a.jpg", "b.jpg", "c.jpg", "d.jpg"]) == [
        "unpinned:a.jpg",
        "checksum:b.jpg",
        "checksum:c.jpg",
        "unbound:d.jpg",
    ]


def test_main_reports_capture_conflicts_as_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    catalog = tmp_path / "catalog.yaml"
    runnable = tmp_path / "seeds.yaml"
    catalog.write_text(yaml.safe_dump({"items": [SEED]}), encoding="utf-8")
    runnable.write_text("items: []\n", encoding="utf-8")
    fake = _FakeIiif(_manifest([NLI_FREE_USE_LICENSE_URL], canvases=3))
    monkeypatch.setattr(
        "hocrgen.tools.nli_seed_promotion.capture_seed_via_iiif",
        lambda **kwargs: capture_seed_via_iiif(seed=kwargs["seed"], fetch=fake, sleep=lambda _s: None),
    )
    existing = tmp_path / "out" / "iiif" / "nli_pb_test_manifest_capture.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("{}\n", encoding="utf-8")
    args = ["--seed-catalog", str(catalog), "--runnable-seeds", str(runnable), "--output-dir", str(tmp_path / "out"),
            "--report-path", str(tmp_path / "report.json"), "--capture-mode", "iiif"]
    assert main(args) == 1
    report = json.loads(capsys.readouterr().out)
    assert [failure["reason"] for failure in report["failed_seeds"]] == ["nli_iiif_capture_conflict"]
    assert report["promoted_seeds"] == []
    assert existing.read_text(encoding="utf-8") == "{}\n"
    assert yaml.safe_load(runnable.read_text(encoding="utf-8"))["items"] == []
