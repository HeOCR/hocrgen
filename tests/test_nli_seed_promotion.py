from __future__ import annotations

from pathlib import Path

import pytest

from hocrgen.core.errors import StageExecutionError
from hocrgen.tools.nli_seed_promotion import (
    ExtractedSeedPage,
    PromotionFailure,
    _page_matches_seed_url,
    apply_promotions,
    build_promotion,
    build_report,
    infer_asset_extension,
    looks_like_challenge_page,
    parse_args,
    render_fixture_html,
    seed_id_to_slug,
    select_catalog_items,
)


def test_seed_id_to_slug_replaces_hyphens() -> None:
    assert seed_id_to_slug("nli-ms-seed-001") == "nli_ms_seed_001"


def test_infer_asset_extension_prefers_url_suffix_and_content_type() -> None:
    assert infer_asset_extension("https://example.com/page.svg", None) == ".svg"
    assert infer_asset_extension("https://example.com/page", "image/png") == ".png"


def test_infer_asset_extension_rejects_unsupported_types() -> None:
    with pytest.raises(StageExecutionError):
        infer_asset_extension("https://example.com/page", "application/pdf")


def test_render_fixture_html_matches_current_parser_contract() -> None:
    html = render_fixture_html(
        title="כותרת",
        description="תיאור",
        rights="Any Use Permitted",
        asset_relative_paths=["assets/a.svg", "assets/b.png"],
    )

    assert 'meta property="og:title" content="כותרת"' in html
    assert 'meta name="description" content="תיאור"' in html
    assert '<h1 class="item-title">כותרת</h1>' in html
    assert '<div class="item-description">תיאור</div>' in html
    assert '<span class="rights-label">Any Use Permitted</span>' in html
    assert html.index('src="assets/a.svg"') < html.index('src="assets/b.png"')


def test_build_promotion_preserves_notes_and_asset_order() -> None:
    seed = {
        "id": "nli-ms-seed-002",
        "url": "https://example.com/item",
        "title": "ignored",
        "notes": "Keep this note.",
    }
    extracted = ExtractedSeedPage(
        title="Live Title",
        description="Live Description",
        rights="Any Use Permitted",
        asset_urls=["https://example.com/a.svg", "https://example.com/b.jpg"],
    )

    promotion = build_promotion(
        seed=seed,
        extracted=extracted,
        downloaded_assets=[
            ("https://example.com/a.svg", "image/svg+xml", b"<svg />"),
            ("https://example.com/b.jpg", "image/jpeg", b"jpg"),
        ],
        require_rights="Any Use Permitted",
    )

    assert promotion.promoted_seed_entry["notes"] == "Keep this note."
    assert promotion.promoted_seed_entry["title"] == "Live Title"
    assert promotion.asset_downloads[0].relative_path.endswith("_page1.svg")
    assert promotion.asset_downloads[1].relative_path.endswith("_page2.jpg")
    assert 'src="assets/nli_ms_seed_002_page1.svg"' in promotion.fixture_html
    assert promotion.fixture_html.index("page1.svg") < promotion.fixture_html.index("page2.jpg")


def test_build_promotion_rejects_missing_rights() -> None:
    seed = {"id": "x", "url": "https://example.com/x"}
    extracted = ExtractedSeedPage(title="t", description="d", rights="", asset_urls=["https://example.com/a.svg"])

    with pytest.raises(StageExecutionError) as excinfo:
        build_promotion(
            seed=seed,
            extracted=extracted,
            downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
            require_rights="Any Use Permitted",
        )

    assert str(excinfo.value) == "rights_missing"


def test_build_promotion_rejects_disallowed_rights() -> None:
    seed = {"id": "x", "url": "https://example.com/x"}
    extracted = ExtractedSeedPage(title="t", description="d", rights="Restricted", asset_urls=["https://example.com/a.svg"])

    with pytest.raises(StageExecutionError) as excinfo:
        build_promotion(
            seed=seed,
            extracted=extracted,
            downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
            require_rights="Any Use Permitted",
        )

    assert "rights_not_allowed:Restricted" == str(excinfo.value)


def test_build_promotion_rejects_missing_assets() -> None:
    seed = {"id": "x", "url": "https://example.com/x"}
    extracted = ExtractedSeedPage(title="t", description="d", rights="Any Use Permitted", asset_urls=[])

    with pytest.raises(StageExecutionError) as excinfo:
        build_promotion(seed=seed, extracted=extracted, downloaded_assets=[], require_rights="Any Use Permitted")

    assert str(excinfo.value) == "assets_missing"


def test_apply_promotions_appends_runnable_and_removes_catalog() -> None:
    runnable = {"items": [{"id": "existing", "url": "https://example.com/existing", "fixture_html": "package://existing.html"}]}
    catalog = {
        "items": [
            {"id": "promote-me", "url": "https://example.com/promote", "title": "Promote", "notes": "Important note"},
            {"id": "keep-me", "url": "https://example.com/keep", "title": "Keep"},
        ]
    }
    promotion = build_promotion(
        seed=catalog["items"][0],
        extracted=ExtractedSeedPage(
            title="Promote",
            description="Description",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
        downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        require_rights="Any Use Permitted",
    )

    updated_runnable, updated_catalog, failures = apply_promotions(
        runnable_manifest=runnable,
        catalog_manifest=catalog,
        promotions=[promotion],
        overwrite=False,
    )

    assert not failures
    assert [item["id"] for item in updated_runnable["items"]] == ["existing", "promote-me"]
    assert updated_runnable["items"][-1]["notes"] == "Important note"
    assert [item["id"] for item in updated_catalog["items"]] == ["keep-me"]


def test_apply_promotions_rejects_duplicate_without_overwrite() -> None:
    promotion = build_promotion(
        seed={"id": "existing", "url": "https://example.com/promote", "title": "Promote"},
        extracted=ExtractedSeedPage(
            title="Promote",
            description="Description",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
        downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        require_rights="Any Use Permitted",
    )

    updated_runnable, updated_catalog, failures = apply_promotions(
        runnable_manifest={"items": [{"id": "existing", "url": "https://example.com/existing", "fixture_html": "package://existing.html"}]},
        catalog_manifest={"items": [{"id": "existing", "url": "https://example.com/promote", "title": "Promote"}]},
        promotions=[promotion],
        overwrite=False,
    )

    assert updated_runnable["items"][0]["url"] == "https://example.com/existing"
    assert updated_catalog["items"][0]["id"] == "existing"
    assert failures == [
        PromotionFailure(
            seed_id="existing",
            reason="seed_already_runnable",
            message="Seed existing already exists in runnable seeds.",
            rights="Any Use Permitted",
        )
    ]


def test_apply_promotions_overwrites_duplicate_when_requested() -> None:
    promotion = build_promotion(
        seed={"id": "existing", "url": "https://example.com/promote", "title": "Promote"},
        extracted=ExtractedSeedPage(
            title="Promoted Title",
            description="Description",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
        downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        require_rights="Any Use Permitted",
    )

    updated_runnable, updated_catalog, failures = apply_promotions(
        runnable_manifest={"items": [{"id": "existing", "url": "https://example.com/existing", "fixture_html": "package://existing.html"}]},
        catalog_manifest={"items": [{"id": "existing", "url": "https://example.com/promote", "title": "Promote"}]},
        promotions=[promotion],
        overwrite=True,
    )

    assert not failures
    assert updated_runnable["items"][0]["title"] == "Promoted Title"
    assert updated_catalog["items"] == []


def test_select_catalog_items_filters_ids_and_max_items() -> None:
    catalog = {"items": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}

    assert [item["id"] for item in select_catalog_items(catalog_manifest=catalog, seed_ids=["b", "c"], max_items=1)] == ["b"]


def test_build_report_includes_success_and_failure_details() -> None:
    promotion = build_promotion(
        seed={"id": "promote-me", "url": "https://example.com/promote", "title": "Promote", "notes": "Keep"},
        extracted=ExtractedSeedPage(
            title="Promote",
            description="Description",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
        downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        require_rights="Any Use Permitted",
    )

    report = build_report(
        attempted_seed_ids=["promote-me", "bad-seed"],
        promotions=[promotion],
        failures=[PromotionFailure(seed_id="bad-seed", reason="rights_missing", message="rights_missing", rights=None)],
    )

    assert report["attempted_seeds"] == ["promote-me", "bad-seed"]
    assert report["promoted_seeds"][0]["seed_id"] == "promote-me"
    assert report["promoted_seeds"][0]["rights"] == "Any Use Permitted"
    assert report["failed_seeds"][0]["reason"] == "rights_missing"


def test_looks_like_challenge_page_detects_cloudflare_markers() -> None:
    assert looks_like_challenge_page(
        url="https://www.nli.org.il/cdn-cgi/challenge-platform/h/g/check",
        html="<html><title>Just a moment...</title><body>Verify you are human</body></html>",
    )
    assert not looks_like_challenge_page(
        url="https://www.nli.org.il/en/manuscripts/example",
        html="<html><h1 class='item-title'>Real page</h1><span class='rights-label'>Any Use Permitted</span></html>",
    )


def test_parse_args_supports_manual_wait_timeout_and_challenge_pause() -> None:
    args = parse_args(["--manual-wait-timeout", "75", "--pause-on-every-challenge", "--connect-cdp", "http://127.0.0.1:9222"])

    assert args.manual_wait_timeout == 75
    assert args.pause_on_every_challenge is True
    assert args.connect_cdp == "http://127.0.0.1:9222"


def test_page_matches_seed_url_accepts_exact_and_query_urls() -> None:
    assert _page_matches_seed_url(
        "https://www.nli.org.il/en/manuscripts/NNL_ALEPH990027114740205171/NLI",
        "https://www.nli.org.il/en/manuscripts/NNL_ALEPH990027114740205171/NLI",
    )
    assert _page_matches_seed_url(
        "https://www.nli.org.il/en/manuscripts/NNL_ALEPH990027114740205171/NLI?foo=1",
        "https://www.nli.org.il/en/manuscripts/NNL_ALEPH990027114740205171/NLI",
    )
    assert not _page_matches_seed_url(
        "https://www.nli.org.il/en/manuscripts/OTHER/NLI",
        "https://www.nli.org.il/en/manuscripts/NNL_ALEPH990027114740205171/NLI",
    )
