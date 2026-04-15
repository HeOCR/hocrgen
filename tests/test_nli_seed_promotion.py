from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from hocrgen.core.errors import StageExecutionError
from hocrgen.tools.nli_seed_promotion import (
    ExtractedSeedPage,
    PromotionFailure,
    _escape_html,
    _extract_failure_reason,
    _extract_rights_hint,
    _fallback_find_rights,
    _first_non_empty,
    _get_seed_page,
    _open_browser_session,
    _page_has_item_markers,
    _page_matches_seed_url,
    _save_failure_screenshot,
    _text_or_none,
    _wait_for_item_page_ready,
    apply_promotions,
    build_fixture_reference,
    build_promotion,
    build_report,
    infer_asset_extension,
    load_yaml_manifest,
    looks_like_challenge_page,
    main,
    parse_args,
    render_fixture_html,
    seed_id_to_slug,
    select_catalog_items,
    write_json,
    write_promotion_outputs,
    write_yaml_manifest,
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
    assert not _page_matches_seed_url("", "https://www.nli.org.il/en/manuscripts/NNL_ALEPH990027114740205171/NLI")


def test_infer_asset_extension_maps_jpe_to_jpg() -> None:
    import hocrgen.tools.nli_seed_promotion as mod

    original = mod.mimetypes.guess_extension
    mod.mimetypes.guess_extension = lambda _content_type: ".jpe"
    try:
        assert infer_asset_extension("https://example.com/file", "image/jpeg") == ".jpg"
    finally:
        mod.mimetypes.guess_extension = original


def test_build_promotion_rejects_asset_count_mismatch() -> None:
    with pytest.raises(StageExecutionError, match="download_failed: expected 2 assets, got 1"):
        build_promotion(
            seed={"id": "mismatch", "url": "https://example.com"},
            extracted=ExtractedSeedPage(
                title="Title",
                description="Description",
                rights="Any Use Permitted",
                asset_urls=["https://example.com/1.svg", "https://example.com/2.svg"],
            ),
            downloaded_assets=[("https://example.com/1.svg", "image/svg+xml", b"<svg />")],
            require_rights="Any Use Permitted",
        )


def test_load_and_write_yaml_manifest_round_trip(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.yaml"
    data = {"items": [{"id": "one", "notes": "hello"}]}

    write_yaml_manifest(manifest_path, data)
    loaded = load_yaml_manifest(manifest_path)

    assert loaded == data


def test_load_yaml_manifest_requires_items_list(tmp_path: Path) -> None:
    manifest_path = tmp_path / "bad.yaml"
    manifest_path.write_text("version: 1\n", encoding="utf-8")

    with pytest.raises(StageExecutionError, match="must contain an items list"):
        load_yaml_manifest(manifest_path)


def test_write_json_writes_pretty_json(tmp_path: Path) -> None:
    json_path = tmp_path / "out" / "report.json"
    write_json(json_path, {"value": "שלום"})

    assert json.loads(json_path.read_text(encoding="utf-8")) == {"value": "שלום"}


def test_write_promotion_outputs_writes_fixture_assets_manifests_and_report(tmp_path: Path) -> None:
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
    output_dir = tmp_path / "nli"
    runnable_path = tmp_path / "seeds.yaml"
    catalog_path = tmp_path / "seed_catalog.yaml"
    report_path = tmp_path / "promotion_report.json"
    runnable_manifest = {"items": [promotion.promoted_seed_entry]}
    catalog_manifest = {"items": []}
    report = {"attempted_seeds": ["promote-me"], "promoted_seeds": [{"seed_id": "promote-me"}], "failed_seeds": []}

    write_promotion_outputs(
        promotions=[promotion],
        output_dir=output_dir,
        runnable_seeds_path=runnable_path,
        seed_catalog_path=catalog_path,
        runnable_manifest=runnable_manifest,
        catalog_manifest=catalog_manifest,
        report_path=report_path,
        report=report,
        overwrite=False,
    )

    fixture_path = output_dir / promotion.fixture_file_name
    asset_path = output_dir / "assets" / promotion.asset_downloads[0].file_name
    assert fixture_path.exists()
    assert asset_path.read_bytes() == b"<svg />"
    assert load_yaml_manifest(runnable_path) == runnable_manifest
    assert load_yaml_manifest(catalog_path) == catalog_manifest
    assert json.loads(report_path.read_text(encoding="utf-8")) == report


def test_build_fixture_reference_supports_package_and_relative_paths(tmp_path: Path) -> None:
    package_reference = build_fixture_reference(
        fixture_file_name="item_seed.html",
        output_dir=Path("src/hocrgen/data/nli"),
        runnable_seeds_path=Path("src/hocrgen/data/nli/seeds.yaml"),
    )
    assert package_reference == "package://data/nli/item_seed.html"

    custom_output_dir = tmp_path / "fixtures"
    runnable_seeds_path = tmp_path / "manifests" / "seeds.yaml"
    relative_reference = build_fixture_reference(
        fixture_file_name="item_seed.html",
        output_dir=custom_output_dir,
        runnable_seeds_path=runnable_seeds_path,
    )
    assert relative_reference == "../fixtures/item_seed.html"


def test_build_promotion_uses_relative_fixture_reference_for_custom_output_dir(tmp_path: Path) -> None:
    promotion = build_promotion(
        seed={"id": "custom-seed", "url": "https://example.com/custom"},
        extracted=ExtractedSeedPage(
            title="Custom",
            description="Description",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
        downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        require_rights="Any Use Permitted",
        output_dir=tmp_path / "fixtures",
        runnable_seeds_path=tmp_path / "manifests" / "seeds.yaml",
    )

    assert promotion.fixture_reference == "../fixtures/item_custom_seed.html"
    assert promotion.promoted_seed_entry["fixture_html"] == "../fixtures/item_custom_seed.html"


def test_write_promotion_outputs_respects_overwrite_flag(tmp_path: Path) -> None:
    promotion = build_promotion(
        seed={"id": "promote-me", "url": "https://example.com/promote", "title": "Promote"},
        extracted=ExtractedSeedPage(
            title="Promote",
            description="Description",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
        downloaded_assets=[("https://example.com/a.svg", "image/svg+xml", b"new-data")],
        require_rights="Any Use Permitted",
    )
    output_dir = tmp_path / "nli"
    fixture_path = output_dir / promotion.fixture_file_name
    asset_path = output_dir / "assets" / promotion.asset_downloads[0].file_name
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text("existing fixture", encoding="utf-8")
    asset_path.write_bytes(b"old-data")

    write_promotion_outputs(
        promotions=[promotion],
        output_dir=output_dir,
        runnable_seeds_path=tmp_path / "seeds.yaml",
        seed_catalog_path=tmp_path / "seed_catalog.yaml",
        runnable_manifest={"items": []},
        catalog_manifest={"items": []},
        report_path=tmp_path / "report.json",
        report={"attempted_seeds": [], "promoted_seeds": [], "failed_seeds": []},
        overwrite=False,
    )
    assert fixture_path.read_text(encoding="utf-8") == "existing fixture"
    assert asset_path.read_bytes() == b"old-data"

    write_promotion_outputs(
        promotions=[promotion],
        output_dir=output_dir,
        runnable_seeds_path=tmp_path / "seeds2.yaml",
        seed_catalog_path=tmp_path / "seed_catalog2.yaml",
        runnable_manifest={"items": []},
        catalog_manifest={"items": []},
        report_path=tmp_path / "report2.json",
        report={"attempted_seeds": [], "promoted_seeds": [], "failed_seeds": []},
        overwrite=True,
    )
    assert "item-title" in fixture_path.read_text(encoding="utf-8")
    assert asset_path.read_bytes() == b"new-data"


def test_main_dry_run_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runnable = tmp_path / "seeds.yaml"
    catalog = tmp_path / "seed_catalog.yaml"
    write_yaml_manifest(runnable, {"items": []})
    write_yaml_manifest(
        catalog,
        {"items": [{"id": "seed-1", "url": "https://example.com/seed-1", "title": "Seed 1", "notes": "note"}]},
    )

    def fake_capture_seed_via_browser(**kwargs):
        return (
            ExtractedSeedPage(
                title="Seed 1",
                description="Desc",
                rights="Any Use Permitted",
                asset_urls=["https://example.com/a.svg"],
            ),
            [("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        )

    monkeypatch.setattr("hocrgen.tools.nli_seed_promotion.capture_seed_via_browser", fake_capture_seed_via_browser)

    exit_code = main(
        [
            "--dry-run",
            "--runnable-seeds",
            str(runnable),
            "--seed-catalog",
            str(catalog),
            "--output-dir",
            str(tmp_path / "nli"),
            "--report-path",
            str(tmp_path / "report.json"),
        ]
    )

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["promoted_seeds"][0]["seed_id"] == "seed-1"
    assert not (tmp_path / "report.json").exists()


def test_main_writes_outputs_when_not_dry_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runnable = tmp_path / "seeds.yaml"
    catalog = tmp_path / "seed_catalog.yaml"
    output_dir = tmp_path / "nli"
    report_path = tmp_path / "report.json"
    write_yaml_manifest(runnable, {"items": []})
    write_yaml_manifest(
        catalog,
        {"items": [{"id": "seed-1", "url": "https://example.com/seed-1", "title": "Seed 1", "notes": "note"}]},
    )

    monkeypatch.setattr(
        "hocrgen.tools.nli_seed_promotion.capture_seed_via_browser",
        lambda **kwargs: (
            ExtractedSeedPage(
                title="Seed 1",
                description="Desc",
                rights="Any Use Permitted",
                asset_urls=["https://example.com/a.svg"],
            ),
            [("https://example.com/a.svg", "image/svg+xml", b"<svg />")],
        ),
    )

    exit_code = main(
        [
            "--runnable-seeds",
            str(runnable),
            "--seed-catalog",
            str(catalog),
            "--output-dir",
            str(output_dir),
            "--report-path",
            str(report_path),
        ]
    )

    assert exit_code == 0
    assert report_path.exists()
    assert load_yaml_manifest(runnable)["items"][0]["id"] == "seed-1"
    assert load_yaml_manifest(catalog)["items"] == []


def test_main_records_stage_execution_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    runnable = tmp_path / "seeds.yaml"
    catalog = tmp_path / "seed_catalog.yaml"
    write_yaml_manifest(runnable, {"items": []})
    write_yaml_manifest(catalog, {"items": [{"id": "seed-1", "url": "https://example.com/seed-1", "title": "Seed 1"}]})

    monkeypatch.setattr(
        "hocrgen.tools.nli_seed_promotion.capture_seed_via_browser",
        lambda **kwargs: (_ for _ in ()).throw(StageExecutionError("rights_not_allowed:Restricted")),
    )

    exit_code = main(["--dry-run", "--runnable-seeds", str(runnable), "--seed-catalog", str(catalog)])

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert report["failed_seeds"][0]["reason"] == "rights_not_allowed"
    assert report["failed_seeds"][0]["rights"] == "Restricted"


class _FakeLocator:
    def __init__(self, *, count: int = 1, text: str | None = None, attr: str | None = None, should_raise: bool = False):
        self._count = count
        self._text = text
        self._attr = attr
        self._should_raise = should_raise
        self.first = self

    def count(self) -> int:
        if self._should_raise:
            raise RuntimeError("count failed")
        return self._count

    def text_content(self) -> str | None:
        if self._should_raise:
            raise RuntimeError("text failed")
        return self._text

    def get_attribute(self, _name: str) -> str | None:
        if self._should_raise:
            raise RuntimeError("attr failed")
        return self._attr

    def evaluate_all(self, _script: str):
        if self._should_raise:
            raise RuntimeError("eval failed")
        return []


class _FakePage:
    def __init__(
        self,
        *,
        url: str = "",
        markers: list[bool] | None = None,
        html: str = "",
        screenshot_raises: bool = False,
        goto_response=None,
    ):
        self.url = url
        self._markers = list(markers or [])
        self._html = html
        self._screenshot_raises = screenshot_raises
        self._goto_response = goto_response or _FakeRequestResponse(ok=True, body=b"svg", content_type="image/svg+xml")
        self.goto_calls: list[tuple[str, str]] = []
        self.reload_calls: list[str] = []
        self.brought_to_front = False
        self.closed = False

    def locator(self, selector: str):
        marker_state = self._markers[0] if self._markers else False
        if selector == ".item-title":
            return _FakeLocator(count=1 if marker_state else 0, text="Title")
        if selector == ".rights-label":
            return _FakeLocator(count=1 if marker_state else 0, text="Any Use Permitted")
        if selector == "img.page-image":
            return _FakeLocator(count=1 if marker_state else 0)
        if selector == "meta[property='og:title']":
            return _FakeLocator(count=1, attr="Meta Title" if marker_state else None)
        if selector == "meta[name='description']":
            return _FakeLocator(count=1, attr="Meta Description")
        if selector == ".item-description":
            return _FakeLocator(count=1, text="Description")
        return _FakeLocator(count=0)

    def title(self) -> str:
        return "Page Title"

    def content(self) -> str:
        return self._html

    def wait_for_timeout(self, _ms: int) -> None:
        if len(self._markers) > 1:
            self._markers.pop(0)

    def goto(self, url: str, wait_until: str = "domcontentloaded", timeout: int | None = None):
        self.goto_calls.append((url, wait_until))
        self.url = url
        return self._goto_response

    def reload(self, wait_until: str = "domcontentloaded") -> None:
        self.reload_calls.append(wait_until)

    def screenshot(self, *, path: str, full_page: bool) -> None:
        if self._screenshot_raises:
            raise RuntimeError("screenshot failed")
        Path(path).write_bytes(b"png")

    def bring_to_front(self) -> None:
        self.brought_to_front = True

    def evaluate(self, _script: str, *_args):
        return None

    def close(self) -> None:
        self.closed = True


class _FakeContext:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.closed = False
        self.new_page_created = None

    def new_page(self):
        self.new_page_created = _FakePage()
        self.pages.append(self.new_page_created)
        return self.new_page_created

    def new_context(self):
        return self

    def storage_state(self):
        return {"cookies": []}

    def close(self):
        self.closed = True


class _FakeBrowser:
    def __init__(self, contexts=None):
        self.contexts = list(contexts or [])
        self.closed = False

    def close(self):
        self.closed = True


class _FakeRequestResponse:
    def __init__(self, *, ok: bool = True, status: int = 200, body: bytes = b"body", content_type: str | None = "image/svg+xml"):
        self.ok = ok
        self.status = status
        self._body = body
        self.headers = {"content-type": content_type} if content_type else {}

    def body(self) -> bytes:
        return self._body


class _FakeRequestContext:
    def __init__(self, responses: list[_FakeRequestResponse]):
        self.responses = list(responses)
        self.disposed = False

    def get(self, _url: str):
        return self.responses.pop(0)

    def dispose(self):
        self.disposed = True


class _FakeRequestFactory:
    def __init__(self, request_context: _FakeRequestContext):
        self.request_context = request_context
        self.storage_state_arg = None

    def new_context(self, *, storage_state):
        self.storage_state_arg = storage_state
        return self.request_context


class _FakePlaywright:
    def __init__(self, *, browser=None, context=None, request_context=None):
        self.browser = browser
        self.context = context
        self.request = _FakeRequestFactory(request_context or _FakeRequestContext([_FakeRequestResponse()]))
        self.chromium = types.SimpleNamespace(
            connect_over_cdp=lambda _url: browser,
            launch_persistent_context=lambda _path, headless=False: context,
        )


class _FakeSyncPlaywright:
    def __init__(self, playwright):
        self.playwright = playwright

    def __enter__(self):
        return self.playwright

    def __exit__(self, exc_type, exc, tb):
        return False


def test_extract_failure_reason_and_rights_hint() -> None:
    assert _extract_failure_reason("challenge_not_resolved: foo") == "challenge_not_resolved"
    assert _extract_failure_reason("rights_missing") == "rights_missing"
    assert _extract_failure_reason("some_other_failure") == "page_load_failed"
    assert _extract_rights_hint("rights_not_allowed:Restricted") == "Restricted"
    assert _extract_rights_hint("page_load_failed: no") is None


def test_escape_html_first_non_empty_text_or_none_and_rights_fallback() -> None:
    assert _escape_html('a&<>"b') == "a&amp;&lt;&gt;&quot;b"
    assert _first_non_empty(None, "  ", "value ") == "value"
    assert _first_non_empty(None, " ", "\t") is None
    assert _text_or_none(_FakeLocator(count=0)) is None
    assert _text_or_none(_FakeLocator(count=1, text="Text")) == "Text"
    assert _text_or_none(_FakeLocator(should_raise=True)) is None
    assert _fallback_find_rights("<html>No Known Copyright Restrictions</html>") == "No Known Copyright Restrictions"
    assert _fallback_find_rights("<html>nothing here</html>") is None


def test_fake_helpers_cover_raise_and_misc_branches() -> None:
    with pytest.raises(RuntimeError, match="text failed"):
        _FakeLocator(should_raise=True).text_content()
    with pytest.raises(RuntimeError, match="attr failed"):
        _FakeLocator(should_raise=True).get_attribute("content")
    with pytest.raises(RuntimeError, match="eval failed"):
        _FakeLocator(should_raise=True).evaluate_all("els => els")

    page = _FakePage()
    assert page.locator("meta[name='description']").get_attribute("content") == "Meta Description"
    assert page.locator(".item-description").text_content() == "Description"
    assert page.locator("unknown").count() == 0
    page.goto("https://example.com/other")
    assert page.url == "https://example.com/other"

    context = _FakeContext()
    assert context.new_context() is context
    browser = _FakeBrowser()
    browser.close()
    assert browser.closed


def test_page_has_item_markers_and_wait_for_ready() -> None:
    ready_page = _FakePage(markers=[True])
    not_ready_page = _FakePage(markers=[False, False])

    assert _page_has_item_markers(ready_page)
    assert not _page_has_item_markers(not_ready_page)
    assert _wait_for_item_page_ready(_FakePage(markers=[False, True]), timeout_seconds=2)
    assert not _wait_for_item_page_ready(_FakePage(markers=[False]), timeout_seconds=0)


def test_page_has_item_markers_handles_locator_errors() -> None:
    class BrokenPage:
        def locator(self, _selector):
            raise RuntimeError("boom")

    assert not _page_has_item_markers(BrokenPage())


def test_save_failure_screenshot_writes_file_or_fallback(tmp_path: Path) -> None:
    ok_path = _save_failure_screenshot(_FakePage(), "seed-id", tmp_path)
    assert ok_path.exists()

    bad_path = _save_failure_screenshot(_FakePage(screenshot_raises=True), "seed-id-2", tmp_path)
    assert bad_path.read_text(encoding="utf-8") == "Screenshot capture failed.\n"


def test_open_browser_session_and_get_seed_page() -> None:
    existing_page = _FakePage(url="https://example.com/seed")
    browser = _FakeBrowser(contexts=[_FakeContext([existing_page])])
    fake_pw = _FakePlaywright(browser=browser)
    connected_browser, connected_context = _open_browser_session(
        playwright=fake_pw,
        browser_state_dir=Path("/tmp/unused"),
        connect_cdp="http://127.0.0.1:9222",
    )
    assert connected_browser is browser
    assert connected_context is browser.contexts[0]

    local_context = _FakeContext()
    fake_pw = _FakePlaywright(context=local_context)
    connected_browser, connected_context = _open_browser_session(
        playwright=fake_pw,
        browser_state_dir=Path("/tmp/browser-state"),
        connect_cdp=None,
    )
    assert connected_browser is None
    assert connected_context is local_context

    selected = _get_seed_page(context=browser.contexts[0], seed_url="https://example.com/seed")
    assert selected is existing_page
    assert existing_page.brought_to_front

    new_context = _FakeContext([])
    new_page = _get_seed_page(context=new_context, seed_url="https://example.com/missing")
    assert new_page is new_context.new_page_created


def test_download_assets_success_and_http_failure() -> None:
    request_context = _FakeRequestContext(
        [
            _FakeRequestResponse(ok=True, body=b"a", content_type="image/svg+xml"),
            _FakeRequestResponse(ok=True, body=b"b", content_type="image/png"),
        ]
    )
    fake_pw = _FakePlaywright(request_context=request_context)
    downloads = __import__("hocrgen.tools.nli_seed_promotion", fromlist=["download_assets"]).download_assets(
        fake_pw,
        {"cookies": ["x"]},
        ["https://example.com/a.svg", "https://example.com/b.png"],
    )
    assert downloads == [
        ("https://example.com/a.svg", "image/svg+xml", b"a"),
        ("https://example.com/b.png", "image/png", b"b"),
    ]
    assert request_context.disposed

    bad_request_context = _FakeRequestContext([_FakeRequestResponse(ok=False, status=403)])
    bad_pw = _FakePlaywright(request_context=bad_request_context)
    with pytest.raises(StageExecutionError, match="download_failed: https://example.com/a.svg: HTTP 403"):
        __import__("hocrgen.tools.nli_seed_promotion", fromlist=["download_assets"]).download_assets(
            bad_pw,
            {"cookies": []},
            ["https://example.com/a.svg"],
        )
    assert bad_request_context.disposed


def test_extract_page_data_uses_title_description_rights_and_asset_urls() -> None:
    class PageForExtract(_FakePage):
        def __init__(self):
            super().__init__(url="https://example.com/item")

        def locator(self, selector: str):
            if selector == "meta[property='og:title']":
                loc = _FakeLocator(count=1, attr="Meta Title")
                loc.first = loc
                return loc
            if selector == "meta[name='description']":
                loc = _FakeLocator(count=1, attr="Meta Description")
                loc.first = loc
                return loc
            if selector == ".item-title":
                loc = _FakeLocator(count=1, text="Title")
                loc.first = loc
                return loc
            if selector == ".item-description":
                loc = _FakeLocator(count=1, text="Description")
                loc.first = loc
                return loc
            if selector == ".rights-label":
                loc = _FakeLocator(count=1, text="Any Use Permitted")
                loc.first = loc
                return loc
            if selector == "img.page-image":
                class AssetLocator(_FakeLocator):
                    def evaluate_all(self, _script: str):
                        return ["/a.svg", "/b.png"]

                loc = AssetLocator(count=2)
                loc.first = loc
                return loc
            return super().locator(selector)

    extract_page_data = __import__("hocrgen.tools.nli_seed_promotion", fromlist=["extract_page_data"]).extract_page_data
    extracted = extract_page_data(PageForExtract())
    assert extracted.title == "Meta Title"
    assert extracted.description == "Meta Description"
    assert extracted.rights == "Any Use Permitted"
    assert extracted.asset_urls == ["https://example.com/a.svg", "https://example.com/b.png"]
    assert PageForExtract().locator("unknown").count() == 0


def test_capture_seed_via_browser_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    capture_seed_via_browser = __import__(
        "hocrgen.tools.nli_seed_promotion", fromlist=["capture_seed_via_browser"]
    ).capture_seed_via_browser
    with pytest.raises(StageExecutionError, match="playwright is required for seed promotion"):
        capture_seed_via_browser(
            seed={"id": "seed", "url": "https://example.com/seed"},
            browser_state_dir=Path("/tmp/browser-state"),
            connect_cdp=None,
            pause_on_first_page=False,
            pause_on_every_challenge=False,
            manual_wait_timeout_seconds=1,
        )


def test_capture_seed_via_browser_happy_path_and_context_close(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import hocrgen.tools.nli_seed_promotion as mod

    page = _FakePage(url="https://example.com/seed", markers=[True], html="<html></html>")
    context = _FakeContext([page])
    request_context = _FakeRequestContext([_FakeRequestResponse(ok=True, body=b"svg", content_type="image/svg+xml")])
    fake_playwright = _FakePlaywright(context=context, request_context=request_context)
    sync_module = types.SimpleNamespace(sync_playwright=lambda: _FakeSyncPlaywright(fake_playwright))
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)
    monkeypatch.setattr(
        mod,
        "extract_page_data",
        lambda _page: ExtractedSeedPage(
            title="Title",
            description="Desc",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
    )

    extracted, downloads = mod.capture_seed_via_browser(
        seed={"id": "seed", "url": "https://example.com/seed"},
        browser_state_dir=tmp_path,
        connect_cdp=None,
        pause_on_first_page=False,
        pause_on_every_challenge=False,
        manual_wait_timeout_seconds=1,
    )

    assert extracted.title == "Title"
    assert downloads == [("https://example.com/a.svg", "image/svg+xml", b"svg")]
    assert context.closed


def test_capture_seed_via_browser_navigates_to_seed_url_when_existing_page_does_not_match(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import hocrgen.tools.nli_seed_promotion as mod

    class ContextWithMismatchedExistingPage(_FakeContext):
        def __init__(self):
            super().__init__([_FakePage(url="https://example.com/other", markers=[True], html="<html></html>")])
            self.created_pages: list[_FakePage] = []

        def new_page(self):
            page = _FakePage(markers=[True], html="<html></html>")
            self.new_page_created = page
            self.created_pages.append(page)
            self.pages.append(page)
            return page

    context = ContextWithMismatchedExistingPage()
    browser = _FakeBrowser(contexts=[context])
    request_context = _FakeRequestContext([_FakeRequestResponse(ok=True, body=b"svg", content_type="image/svg+xml")])
    fake_playwright = _FakePlaywright(browser=browser, context=context, request_context=request_context)
    sync_module = types.SimpleNamespace(sync_playwright=lambda: _FakeSyncPlaywright(fake_playwright))
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)
    monkeypatch.setattr(
        mod,
        "extract_page_data",
        lambda _page: ExtractedSeedPage(
            title="Title",
            description="Desc",
            rights="Any Use Permitted",
            asset_urls=["https://example.com/a.svg"],
        ),
    )

    mod.capture_seed_via_browser(
        seed={"id": "seed", "url": "https://example.com/seed"},
        browser_state_dir=tmp_path,
        connect_cdp="http://127.0.0.1:9222",
        pause_on_first_page=False,
        pause_on_every_challenge=False,
        manual_wait_timeout_seconds=1,
    )

    assert context.created_pages
    assert context.created_pages[0].goto_calls == [("https://example.com/seed", "domcontentloaded")]
    assert not context.closed


def test_capture_seed_via_browser_manual_prompt_and_reload_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import hocrgen.tools.nli_seed_promotion as mod

    page = _FakePage(url="https://example.com/seed", markers=[False, False, False], html="<html>Just a moment...</html>")
    context = _FakeContext([page])
    fake_playwright = _FakePlaywright(context=context)
    sync_module = types.SimpleNamespace(sync_playwright=lambda: _FakeSyncPlaywright(fake_playwright))
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)
    monkeypatch.setattr("builtins.input", lambda: "")

    with pytest.raises(StageExecutionError, match="challenge_not_resolved"):
        mod.capture_seed_via_browser(
            seed={"id": "seed", "url": "https://example.com/seed"},
            browser_state_dir=tmp_path,
            connect_cdp=None,
            pause_on_first_page=True,
            pause_on_every_challenge=False,
            manual_wait_timeout_seconds=1,
        )
    assert page.reload_calls == ["domcontentloaded"]
    assert (tmp_path / "failures" / "seed_failure.png").exists()


def test_capture_seed_via_browser_page_load_failure_without_challenge(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import hocrgen.tools.nli_seed_promotion as mod

    page = _FakePage(url="https://example.com/seed", markers=[False, False], html="<html>plain page</html>")
    context = _FakeContext([page])
    fake_playwright = _FakePlaywright(context=context)
    sync_module = types.SimpleNamespace(sync_playwright=lambda: _FakeSyncPlaywright(fake_playwright))
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)

    with pytest.raises(StageExecutionError, match="page_load_failed: seed: item page markers not found within 1s"):
        mod.capture_seed_via_browser(
            seed={"id": "seed", "url": "https://example.com/seed"},
            browser_state_dir=tmp_path,
            connect_cdp=None,
            pause_on_first_page=False,
            pause_on_every_challenge=False,
            manual_wait_timeout_seconds=1,
        )


def test_capture_seed_via_browser_wraps_unexpected_exceptions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import hocrgen.tools.nli_seed_promotion as mod

    page = _FakePage(url="https://example.com/seed", markers=[True], html="<html></html>")
    context = _FakeContext([page])
    fake_playwright = _FakePlaywright(context=context)
    sync_module = types.SimpleNamespace(sync_playwright=lambda: _FakeSyncPlaywright(fake_playwright))
    monkeypatch.setitem(sys.modules, "playwright", types.SimpleNamespace())
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_module)
    monkeypatch.setattr(mod, "extract_page_data", lambda _page: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(StageExecutionError, match="page_load_failed: seed: boom"):
        mod.capture_seed_via_browser(
            seed={"id": "seed", "url": "https://example.com/seed"},
            browser_state_dir=tmp_path,
            connect_cdp=None,
            pause_on_first_page=False,
            pause_on_every_challenge=False,
            manual_wait_timeout_seconds=1,
        )
