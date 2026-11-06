"""Network-free tests for the operator-only NLI printed-book inventory (F8c2)."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from hocrgen.tools import nli_printed_inventory as inv
from hocrgen.tools.nli_search_discovery import DC, NLI_SEARCH_ENDPOINT

SECRET = "inventory-test-key-987"
LICENSE_BASE = "https://www.nli.org.il/contenteditors/pages-for-terms-of-use/"
FREE = f"{LICENSE_BASE}public-domain-free-use"
GOOGLE = f"{LICENSE_BASE}public-domain-non-commercial-use"
FAIR = f"{LICENSE_BASE}fair-use"
COPYING_PROHIBITED = "http://web.nli.org.il/sites/NLI/Hebrew/library/items-terms-of-use/Pages/nli-copying-prohibited.aspx"


def _record(record_id: str, *, kind: str = "book", access: str = "online_and_api_access", language: str = "heb", date: str = 'תקצ"ט', manifest: bool = True) -> dict:
    record = {
        "@id": f"https://www.nli.org.il/en/books/NNL_ALEPH{record_id}",
        f"{DC}recordid": [{"@value": record_id}],
        f"{DC}title": [{"@value": f"Book {record_id}"}],
        f"{DC}type": [{"@value": kind}],
        f"{DC}accessRights": [{"@value": access}],
        f"{DC}language": [{"@value": language}],
        f"{DC}non_standard_date": [{"@value": date}],
        f"{DC}publisher": [{"@value": "ליוורנו : דפוס"}],
    }
    if manifest:
        record[f"{DC}relation"] = [{"@id": f"https://iiif.nli.org.il/IIIFv21/{record_id}/manifest"}]
    return record


def _canvas(index: int) -> dict:
    return {"@id": f"https://iiif.nli.org.il/IIIFv21/FL{index}", "images": [{"resource": {"service": {"@id": f"https://iiif.nli.org.il/IIIFv21/FL{index}"}}}]}


def _manifest(licence: str | None, canvases: int = 0, *, volumes: list[str] | None = None) -> dict:
    sequences: list[dict] = [{"@id": url, "@type": "sc:Sequence"} for url in volumes or []]
    if not volumes:
        sequences = [{"@id": "seq", "canvases": [_canvas(i) for i in range(canvases)]}]
    manifest: dict = {"@id": "m", "sequences": sequences}
    if licence:
        manifest["license"] = [licence]
    return manifest


# --- dates ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("18740101", (1874, "year")),
        ('תרע"ב 1911', (1911, "year")),
        ("[תקצ\"ט]", (1839, "year")),
        ("א'ש'ר'י'ך' ישראל [תקל\"א] 1770", (1770, "year")),
        ('כא\'ש\'ר\' יברכך ה" אלהיך [תק"א]', (1741, "year")),
        ('ש"ח-ש"ט', (1548, "year")),
        ('[תרפ"-]', (1920, "year")),
        ("[תרס-?]", (1900, "decade")),
        ('מאה י"ט', (1850, "century")),
        ("[18--]", (1850, "century")),
        ("תאריך לא ידוע", (None, "unparsed")),
        (None, (None, "none")),
    ],
)
def test_publication_year_parsing(text, expected) -> None:
    assert inv.parse_publication_year(text) == expected


def test_century_labels() -> None:
    assert [inv.century_label(y) for y in (None, 1475, 1500, 1839, 1911)] == ["unknown", "before 1500", "1500s", "1800s", "1900s"]


# --- search pages --------------------------------------------------------------------------------


def test_search_urls_vary_order_but_not_meaning() -> None:
    urls = [inv.search_url(api_key=SECRET, page=7, order_index=i) for i in range(len(inv.PARAMETER_ORDERS))]
    assert len(set(urls)) == len(urls)
    parsed = [parse_qs(urlparse(url).query) for url in urls]
    assert all(p == parsed[0] for p in parsed)
    assert parsed[0]["query"] == ["language,exact,heb"] and parsed[0]["result_page"] == ["7"]
    assert all(url.endswith(f"api_key={SECRET}") for url in urls)
    assert "count_mode=true" in inv.count_url(api_key=SECRET)


def test_page_classification_detects_dropped_filters_and_fallbacks() -> None:
    good = [_record("1"), _record("2", kind="ebook", language="heb;yid")]
    assert inv.classify_search_page(good, page=3, page_one_ids=["9"]) == "ok"
    assert inv.classify_search_page(good, page=3, page_one_ids=["1", "2"]) == "fallback_page_one"
    assert inv.classify_search_page(good, page=1, page_one_ids=["1", "2"]) == "ok"
    assert inv.classify_search_page([_record("1", kind="manuscript")], page=1, page_one_ids=None) == "filter_dropped"
    assert inv.classify_search_page([_record("1", access="online_in_library_only")], page=1, page_one_ids=None) == "filter_dropped"
    assert inv.classify_search_page([_record("1", language="ger")], page=1, page_one_ids=None) == "filter_dropped"
    assert inv.classify_search_page({}, page=1, page_one_ids=None) == "not_a_list"
    assert inv.classify_search_page(["x"], page=1, page_one_ids=None) == "empty"


def test_failed_pages_retry_with_a_new_url_and_blocks_stop() -> None:
    seen: list[str] = []
    responses = [(502, b""), (200, b"<html>"), (200, json.dumps([_record("1", kind="journal")]).encode()), (200, json.dumps([_record("5")]).encode())]

    def fetch(url: str):
        seen.append(url)
        return responses[len(seen) - 1]

    page = inv.fetch_search_page(api_key=SECRET, page=4, fetch=fetch, page_one_ids=None)
    assert page["status"] == "ok" and page["attempts"] == ["http_502", "not_json", "filter_dropped", "ok"]
    assert len(set(seen)) == 4
    fallback = inv.fetch_search_page(api_key=SECRET, page=9, fetch=lambda _u: (200, json.dumps([_record("1")]).encode()), page_one_ids=["1"])
    assert fallback["status"] == "fallback_page_one" and fallback["attempts"] == ["fallback_page_one"]
    exhausted = inv.fetch_search_page(api_key=SECRET, page=9, fetch=lambda _u: (502, b""), page_one_ids=None, max_attempts=2)
    assert exhausted["status"] == "http_502" and exhausted["records"] == []
    with pytest.raises(inv.InventoryBlocked):
        inv.fetch_search_page(api_key=SECRET, page=2, fetch=lambda _u: (429, b""), page_one_ids=None)


def test_throttle_spaces_requests() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    throttle = inv.Throttle(lambda _u: (200, b""), 1.0, sleep, lambda: now[0])
    for _ in range(3):
        throttle("u")
    assert sleeps == [1.0, 1.0] and throttle.requests == 3


# --- manifests -----------------------------------------------------------------------------------


def _serve(manifests: dict[str, dict | int]):
    def fetch(url: str):
        value = manifests.get(url, 404)
        if isinstance(value, int):
            return value, b""
        return 200, json.dumps(value).encode("utf-8")

    return fetch


def test_manifest_classes_and_multi_volume_resolution() -> None:
    vol = "https://iiif.nli.org.il/IIIFv21/X/sequence/IE"
    fetch = _serve(
        {
            "free": _manifest(FREE, 3),
            "google": _manifest(GOOGLE, 9),
            "fair": _manifest(FAIR, 2),
            "none": _manifest(None, 2),
            "zero": _manifest(FREE, 0),
            "multi": _manifest(FREE, volumes=[f"{vol}1", f"{vol}2", f"{vol}3"]),
            f"{vol}1": {"@id": "v1", "canvases": [_canvas(1), _canvas(2)]},
            f"{vol}2": {"@id": "v2"},
            f"{vol}3": 500,
            "empty_multi": _manifest(FREE, volumes=[f"{vol}2"]),
            "nc_multi": _manifest(GOOGLE, volumes=[f"{vol}1"]),
            "forbidden": 403,
        }
    )
    checks = {name: inv.inspect_manifest(name, fetch) for name in ["free", "google", "fair", "none", "zero", "multi", "empty_multi", "nc_multi", "forbidden"]}
    assert {name: inv.outcome_class(check) for name, check in checks.items()} == {
        "free": "free_use",
        "google": "non_commercial_google",
        "fair": "other_slug",
        "none": "licence_missing_or_unrecognized",
        "zero": "free_use_zero_canvases",
        "multi": "free_use_multi_volume",
        "empty_multi": "free_use_empty_volume_sequences",
        "nc_multi": "non_commercial_google",
        "forbidden": "manifest_http_error",
    }
    assert inv.outcome_class(None) == "no_manifest_link"
    assert checks["free"]["image_service"] == "https://iiif.nli.org.il/IIIFv21/FL0"
    multi = checks["multi"]
    # The top-level gate rejects the zero-canvas manifest; each volume is gated on its own canvas count (F8d2).
    assert multi["reason"] == "nli_iiif_manifest_zero_canvases"
    assert [(v["canvas_count"], v["decision"]) for v in multi["volumes"]] == [(2, "accepted"), (0, "rejected"), (None, "rejected")]
    assert inv.effective_canvas_count(multi) == 2 and multi["image_service"] == "https://iiif.nli.org.il/IIIFv21/FL1"
    assert "volumes" not in checks["nc_multi"] and checks["nc_multi"]["volume_sequence_count"] == 1
    capped = inv.inspect_manifest("multi", fetch, max_volumes=1)
    assert len(capped["volumes"]) == 1 and capped["volumes_unresolved"] == 2
    assert inv.licence_class("nli-non-commercial", "x") == "non_commercial_other"
    assert inv.licence_class("non-commercial-use-license", "x") == "non_commercial_other"


def test_image_rights_are_recorded_not_decided() -> None:
    fetch = _serve({"svc/info.json": {"rights": COPYING_PROHIBITED}, "lic/info.json": {"license": "L"}})
    assert inv.check_image_rights("svc/", fetch)["rights"] == COPYING_PROHIBITED
    assert inv.check_image_rights("lic", fetch)["rights"] == "L"
    assert inv.check_image_rights("gone", fetch) == {"http_status": 404, "image_service": "gone", "rights": None}


# --- the run and the summary ---------------------------------------------------------------------


def _fake_upstream(pages: dict[int, list[dict]], manifests: dict[str, dict | int], *, count: int | None = 120):
    served = _serve(manifests)
    requested: list[str] = []

    def fetch(url: str):
        requested.append(url)
        if url.startswith(NLI_SEARCH_ENDPOINT):
            assert url.endswith(f"api_key={SECRET}")
            query = parse_qs(urlparse(url).query)
            if "count_mode" in query:
                return (200, json.dumps({"countInfos": {"total": count}}).encode()) if count is not None else (502, b"")
            return 200, json.dumps(pages.get(int(query["result_page"][0]), pages[1])).encode("utf-8")
        return served(url)

    return fetch, requested


def _upstream_fixture():
    m = lambda rid: f"https://iiif.nli.org.il/IIIFv21/{rid}/manifest"  # noqa: E731
    pages = {
        1: [_record("11", date="1601"), _record("12", date='תקצ"ט'), _record("13", kind="ebook")],
        2: [_record("21", date="18740101"), _record("22", date="1910"), _record("23", manifest=False)],
        3: [_record("31", date="[18--]"), _record("32", date="לא ידוע")],
    }
    vol = "https://iiif.nli.org.il/IIIFv21/S/sequence/IE9"
    manifests = {
        m("11"): _manifest(FREE, 4),
        m("12"): _manifest(GOOGLE, 100),
        m("21"): _manifest(FREE, 0),
        m("22"): _manifest(FREE, volumes=[vol]),
        vol: {"@id": vol, "canvases": [_canvas(5), _canvas(6), _canvas(7)]},
        m("31"): 403,
        m("32"): _manifest(FREE, 10),
        "https://iiif.nli.org.il/IIIFv21/FL0/info.json": {"rights": COPYING_PROHIBITED},
        "https://iiif.nli.org.il/IIIFv21/FL5/info.json": {"rights": COPYING_PROHIBITED},
    }
    return pages, manifests


def test_run_and_summary_are_deterministic_and_key_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    pages, manifests = _upstream_fixture()
    fetch, requested = _fake_upstream(pages, manifests)
    report = inv.run_inventory(
        api_key=SECRET, sample_size=3, window_pages=3, seed=1, info_json_checks=5, request_delay=0, captured_on="2026-11-06", fetch=fetch, sleep=lambda _s: None
    )
    assert report["status"] == "ok" and report["population_total"] == 120 and report["requests"] == len(requested)
    assert SECRET not in json.dumps(report)
    assert [p["page"] for p in report["pages"]] == [1, 2, 3]
    summary = inv.summarize_inventory(report)
    assert summary["sample"]["books"] == 7 and summary["sample"]["other_types"] == {"ebook": 1}
    assert summary["sample"]["outcomes"] == {
        "free_use": 2,
        "free_use_multi_volume": 1,
        "free_use_zero_canvases": 1,
        "non_commercial_google": 1,
        "manifest_http_error": 1,
        "no_manifest_link": 1,
    }
    assert summary["sample"]["licence_slugs"]["public-domain-free-use"] == 4
    assert summary["sample"]["free_use_pages"] == 4 + 3 + 10
    assert summary["sample"]["manifest_http_status"] == {"200": 5, "403": 1, "no_link": 1}
    assert summary["sample"]["book_share_ci95"][1] <= 1.0
    assert summary["by_century"]["1600s"]["free_use_pages"] == 4
    assert summary["by_century"]["1900s"]["free_use_with_pages"] == 1
    assert summary["by_century"]["unknown"]["books"] == 1
    assert summary["image_rights_sample"] == {"nli-copying-prohibited": 3}
    assert summary["estimates"]["by_outcome"]["free_use_with_pages"]["per_book"] == round(3 / 7, 4)
    assert summary["estimates"]["books"] is not None
    assert summary == inv.summarize_inventory(json.loads(json.dumps(report)))
    rows = inv.compact_records(report)
    assert rows == sorted(rows) and ["22", "public-domain-free-use", 3] in rows and ["23", "(no_manifest_link)", 0] in rows
    markdown = inv.render_markdown(summary)
    assert "nli-copying-prohibited" in markdown and "free_use_multi_volume" in markdown and SECRET not in markdown

    report_path = tmp_path / "full.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    md_path, compact_path = tmp_path / "out" / "summary.md", tmp_path / "out" / "summary.json"
    args = ["summarize", "--report-path", str(report_path), "--markdown-path", str(md_path), "--compact-json-path", str(compact_path), "--population-total", "500"]
    assert inv.main(args) == 0
    capsys.readouterr()
    compact = json.loads(compact_path.read_text(encoding="utf-8"))
    assert compact["books"] == rows
    assert compact["summary"]["method"]["population_total"] == 500 and compact["summary"]["method"]["population_total_source"] == "operator"
    first = md_path.read_text(encoding="utf-8")
    assert inv.main(args) == 0 and md_path.read_text(encoding="utf-8") == first

    monkeypatch.setenv("NLI_API_KEY", SECRET)
    monkeypatch.setattr(inv, "fetch_url", fetch)
    monkeypatch.setattr(inv.time, "sleep", lambda _s: None)
    run_path = tmp_path / "run.json"
    assert inv.main(["run", "--report-path", str(run_path), "--sample-pages", "2", "--window-pages", "3", "--request-delay", "0", "--population-total", "90"]) == 0
    assert SECRET not in run_path.read_text(encoding="utf-8") and SECRET not in capsys.readouterr().out


def test_run_without_key_makes_no_request_and_blocks_stop_cleanly(monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path) -> None:
    def no_network(_url):
        raise AssertionError("no request without a key")

    assert inv.run_inventory(api_key=None, fetch=no_network)["status"] == "no_api_key"
    monkeypatch.delenv("NLI_API_KEY", raising=False)
    assert inv.main(["run", "--report-path", str(tmp_path / "r.json")]) == 0
    capsys.readouterr()

    pages, manifests = _upstream_fixture()
    blocked_search, _ = _fake_upstream(pages, manifests)
    stopped = inv.run_inventory(api_key=SECRET, fetch=lambda u: (403, b"") if "count_mode" in u else blocked_search(u), sleep=lambda _s: None, request_delay=0)
    assert stopped["status"] == "stopped_blocked" and SECRET not in json.dumps(stopped)

    failing = {key: 500 for key in manifests}
    fetch, _ = _fake_upstream(pages, failing, count=None)
    report = inv.run_inventory(api_key=SECRET, sample_size=3, window_pages=3, fetch=fetch, sleep=lambda _s: None, request_delay=0, max_consecutive_manifest_failures=2)
    assert report["status"] == "stopped_blocked" and report["population_total_source"] == "unavailable"
    summary = inv.summarize_inventory(report)
    assert summary["estimates"]["books"] is None and summary["method"]["status"] == "stopped_blocked"
    assert "n/a" in inv.render_markdown(summary)

    rate_limited = {**manifests, "https://iiif.nli.org.il/IIIFv21/11/manifest": 429}
    fetch, _ = _fake_upstream(pages, rate_limited)
    assert inv.run_inventory(api_key=SECRET, sample_size=1, window_pages=1, fetch=fetch, sleep=lambda _s: None, request_delay=0)["status"] == "stopped_blocked"


def test_ratio_estimate_edges() -> None:
    assert inv._ratio_estimate([], 10) == (0.0, 0.0)
    assert inv._ratio_estimate([(1, 2)], 10) == (0.5, 0.0)
    ratio, se = inv._ratio_estimate([(1, 2), (2, 2), (0, 2)], 3)
    assert ratio == 0.5 and se == 0.0
    assert inv.parse_count(b"[]") is None and inv.parse_count(b"x") is None and inv.parse_count(b'{"countInfos": {"total": 5}}') == 5
    assert inv.sample_pages(window_pages=3, sample_size=10, seed=1) == [1, 2, 3]
