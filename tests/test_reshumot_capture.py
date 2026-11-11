"""The Reshumot fetcher fixes (modern-s6-scout report §7 item 1): a complete, order-free listing; transient empty
answers retried; capped years sliced; files keyed by (series, number, sha256); born digital decided from the PDF."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from hocrgen.tools import government_print_tranche as gp
from hocrgen.tools import reshumot_capture as rc

FIXTURES = Path(__file__).parent / "fixtures" / "reshumot_capture"
INDESIGN = {"Creator": "Adobe InDesign CS (3.0.1)", "Producer": "Adobe PDF Library 6.0", "Pages": "2"}
RESCAN = {"Creator": "", "Producer": "PDFsharp 1.32.2608-g (www.pdfsharp.net)", "Pages": "2"}
ABBYY = {"Creator": "ABBYY FineReader Engine 12", "Producer": "ABBYY FineReader Engine 12", "Pages": "2"}
FONT_ROW = ["BMBSOR+HadassahMF", "CID", "TrueType", "Identity-H", "yes", "yes", "yes", "35", "0"]
A4 = {1: (595.0, 842.0), 2: (595.0, 842.0)}


def _data(number: str, *, folder_type: str = "1", year: str = "73", publish: str | None = None, pages: int = 4,
          url: str | None = None) -> dict:
    return {"BookletNum": number, "BookletYear": year, "FolderType": folder_type, "PublishDate": publish, "Pages": pages,
            "Document": [{"FileName": url or f"https://example.invalid/doc/{folder_type}-{number}", "DisplayName": f"x-{number}"}]}


class FakeApi:
    """A search API with the scout's quirks: an arbitrary order per query (and, with ``reshuffle``, a fresh one on
    every call), ``skip`` pages of 10, a 200 cap, a ``BookletNum`` substring match, and the first ``warn`` calls
    answering ``Status: Warn`` with no results."""

    def __init__(self, listings: list[dict], *, warn: int = 0, seed: int = 0, reshuffle: bool = False) -> None:
        self.listings, self.warn, self.seed, self.reshuffle, self.calls = listings, warn, seed, reshuffle, []
        self.random = random.Random(seed)

    def __call__(self, body: dict) -> dict:
        self.calls.append(dict(body))
        if self.warn:
            self.warn -= 1
            return {"Status": "Warn", "message": "items not found", "Results": None, "TotalResults": 0}
        hits = [d for d in self.listings if d["FolderType"] == body["FolderType"] and d["BookletYear"] == body["BookletYear"]
                and body.get("BookletNum", "") in d["BookletNum"]]
        query = json.dumps({k: v for k, v in body.items() if k != "skip"}, sort_keys=True)
        (self.random if self.reshuffle else random.Random(f"{self.seed}{query}")).shuffle(hits)
        skip = int(body.get("skip") or 0)
        page = hits[:gp.RESHUMOT_RESULT_CAP][skip:skip + gp.RESHUMOT_PAGE_SIZE]
        return {"Status": "OK", "Results": [{"Data": d} for d in page], "TotalResults": min(len(hits), gp.RESHUMOT_RESULT_CAP)}


def test_enumeration_is_complete_whatever_the_order_and_keeps_duplicate_listings() -> None:
    listings = [_data(str(n)) for n in range(1960, 2032)]
    listings.append(_data("1976", pages=6, url="https://example.invalid/doc/1-1976-indesign"))  # rescan + original
    listings.append(_data("1976", year="72"))  # another year: never mixed in
    api = FakeApi(listings, seed=3)
    result = gp.reshumot_enumerate_year(api, "1", "73", sleep=lambda _: None)
    assert result["complete"] and len(result["listings"]) == 73
    assert result["numbers"] == [str(n) for n in range(1960, 2032)]
    keys = {gp.reshumot_listing_key(d) for d in result["listings"]}
    assert ("sefer_hachukim", "1976", "https://example.invalid/doc/1-1976-indesign") in keys
    assert ("sefer_hachukim", "1976", "https://example.invalid/doc/1-1976") in keys
    assert result["queries"][0]["passes"] >= 1
    # The same answer set in another random order gives the same rows.
    again = gp.reshumot_enumerate_year(FakeApi(listings, seed=99), "1", "73", sleep=lambda _: None)
    assert again["listings"] == result["listings"]
    # Even when every call answers in a fresh order, re-paging and number look-ups complete the set.
    shuffled = gp.reshumot_enumerate_year(FakeApi(listings, seed=5, reshuffle=True), "1", "73", sleep=lambda _: None)
    assert shuffled["complete"] and shuffled["listings"] == result["listings"]


def test_transient_warn_answers_are_retried_with_backoff() -> None:
    waits: list[float] = []
    api = FakeApi([_data(str(n)) for n in range(1, 6)], warn=2)
    result = gp.reshumot_enumerate_year(api, "1", "73", sleep=waits.append)
    assert waits == [30.0, 60.0] and result["complete"] and len(result["listings"]) == 5
    # An answer still empty after every retry is recorded, and the year is not complete.
    stuck = FakeApi([_data("1")], warn=10)
    waits.clear()
    result = gp.reshumot_enumerate_year(stuck, "1", "73", sleep=waits.append)
    assert waits == list(gp.RESHUMOT_WARN_BACKOFF) and not result["complete"] and result["queries"][0]["empty_after_retries"]


def test_a_year_at_the_cap_is_sliced_by_booklet_number() -> None:
    listings = [_data(str(n), folder_type="3", year="44") for n in range(3500, 3780)]  # 280 booklets > 200
    api = FakeApi(listings, seed=7)
    result = gp.reshumot_enumerate_year(api, "3", "44", sleep=lambda _: None)
    assert result["queries"][0]["capped"]
    assert result["numbers"] == [str(n) for n in range(3500, 3780)]
    assert result["complete"] and gp.reshumot_number_gaps(result["numbers"]) == []
    assert any(q["number_part"] for q in result["queries"])


def test_number_gaps() -> None:
    assert gp.reshumot_number_gaps(["6394", "6396", "6395", "6399"]) == [6397, 6398]
    assert gp.reshumot_number_gaps([]) == []


def test_selection_no_longer_filters_on_an_empty_publish_date() -> None:
    results = [{"Data": _data("1976", publish=None)}, {"Data": _data("1900", publish="2004-06-01T00:00:00")},
               {"Data": _data("2010", publish="2005-06-30T00:00:00")}]
    chosen = gp.select_reshumot_booklets(results, seed="s", per_query=5, max_pages=24)
    assert {d["BookletNum"] for d in chosen} == {"1976", "2010"}


def _pdf_facts(info: dict, *, image_rows: list | None = None, fonts: list | None = None) -> dict:
    return {"info": info, "xmp": "", "font_rows": [FONT_ROW] if fonts is None else fonts, "image_rows": image_rows or [],
            "page_sizes": A4}


def test_born_digital_is_decided_from_the_pdf() -> None:
    emblem = ["1", "0", "image", "237", "303", "gray", "1", "8", "jpeg", "no", "53", "0", "301", "300", "36K", "52%"]
    ok = gp.reshumot_pdf_born_digital(_pdf_facts(INDESIGN, image_rows=[emblem]))
    assert ok["passed"] and ok["scope"] == "pdf_metadata"
    scan = ["1", "0", "image", "2480", "3508", "gray", "1", "1", "ccitt", "no", "5", "0", "300", "300", "90K", "1%"]
    rescan = gp.reshumot_pdf_born_digital(_pdf_facts(RESCAN, image_rows=[scan], fonts=[]))
    assert not rescan["passed"] and set(rescan["reasons"]) == {"full_page_image", "no_embedded_fonts"}
    assert gp.reshumot_pdf_born_digital(_pdf_facts(ABBYY))["reasons"] == ["ocr_producer"]
    # With glyph layers it is the full check: a missing page layer refuses.
    layer = {"page": {"width": 595.0, "height": 842.0}, "glyphs": [], "images": []}
    assert gp.reshumot_pdf_born_digital(_pdf_facts(INDESIGN), {1: layer, 2: None})["reasons"] == ["page_layer_missing"]
    assert gp.reshumot_pdf_born_digital(_pdf_facts(INDESIGN), {1: layer, 2: layer})["scope"] == "pdf_and_glyph_layers"


def _file(number: str, sha: str, info: dict, *, publish: str | None = None, pages: int = 6, series: str = "sefer_hachukim") -> dict:
    data = _data(number, publish=publish, pages=pages, url=f"https://example.invalid/{sha}")
    verdict = gp.reshumot_pdf_born_digital(_pdf_facts(info, fonts=[] if info is RESCAN else None))
    return {"listing_key": list(gp.reshumot_listing_key(data)), "booklet_key": list(gp.reshumot_booklet_key(series, number, sha)),
            "series": series, "booklet_number": number, "pdf_sha256": sha, "pdf_bytes": 10, "pdf_pages": pages,
            "creator": info["Creator"], "producer": info["Producer"], "born_digital": verdict, "listing": data}


def test_duplicate_listings_are_keyed_by_sha256_and_the_born_digital_file_wins() -> None:
    rescan, original = _file("1976", "a" * 64, RESCAN, pages=1), _file("1976", "b" * 64, INDESIGN)
    assert gp.reshumot_pick_born_digital_file([rescan, original]) == (original, "born_digital")
    assert gp.reshumot_pick_born_digital_file([rescan]) == (None, "no_born_digital_file")
    twin = _file("1976", "c" * 64, INDESIGN)
    assert gp.reshumot_pick_born_digital_file([original, twin]) == (None, "ambiguous_born_digital_files")
    assert gp.reshumot_booklet_key("sefer_hachukim", "1976", "b" * 64) != gp.reshumot_booklet_key("sefer_hachukim", "1976", "a" * 64)


def test_knesset_dates_fill_an_empty_publish_date_and_conflicts_stay_unknown() -> None:
    laws = json.loads((FIXTURES / "kns_law_rows.json").read_text(encoding="utf-8"))
    dates = gp.knesset_booklet_dates(laws)
    assert dates["1976"]["date"] == "2005-01-25"
    assert dates["1999"]["date"] is None and dates["1999"]["dates_seen"] == ["2005-04-01", "2005-04-02"]
    assert "6400" not in dates  # another series
    files = [_file("1976", "a" * 64, RESCAN, pages=1), _file("1976", "b" * 64, INDESIGN),
             _file("1999", "d" * 64, INDESIGN), _file("2010", "e" * 64, INDESIGN, publish="2005-06-30T00:00:00+03:00"),
             _file("2100", "f" * 64, INDESIGN, publish="2006-01-02T00:00:00+02:00"), _file("1977", "9" * 64, RESCAN, pages=1)]
    selected, decisions = rc.select_booklets(files, dates, date_from="2005-01-01", date_to="2005-12-31")
    by = {d["booklet_number"]: d for d in decisions}
    assert by["1976"]["selected"] and by["1976"]["publish_date_source"] == rc.KNESSET_DATE_SOURCE
    assert by["1999"]["reason"] == "publish_date_unknown"
    assert by["2010"]["selected"] and by["2010"]["publish_date_source"] == "gazette API PublishDate"
    assert by["2100"]["reason"] == "outside_span" and by["1977"]["reason"] == "no_born_digital_file"
    assert [row["BookletNum"] for row in selected] == ["1976", "2010"]
    assert selected[0]["publish_date"] == "2005-01-25" and selected[0]["pdf_sha256"] == "b" * 64
    assert "publish_date" not in selected[1]  # the API date is kept as the API's
    assert gp.reshumot_publish_date(selected[0]) == "2005-01-25" and gp.reshumot_publish_date(selected[1]) == "2005-06-30"
    rows = rc.new_booklet_rows(decisions)
    assert [(r["number"], r["sha256"][:1], r["role"]) for r in rows] == [
        ("1976", "a", "rescan_or_other"), ("1976", "b", "born_digital_original"), ("2010", "e", "born_digital_original")]
    assert {"series", "number", "date", "pages", "sha256"} <= set(rows[0])


def test_expected_phrases_name_the_date_source() -> None:
    data = {**_data("1976", publish=None), "publish_date": "2005-01-25", "publish_date_source": rc.KNESSET_DATE_SOURCE,
            "DocSummary": {"DescriptionHtmlString": ""}}
    phrases = gp.reshumot_expected_phrases(data, 2, "ספר החוקים 1976, 25.1.2005\n")
    assert {"text": "25.1.2005", "source": rc.KNESSET_DATE_SOURCE} in phrases


def test_ranges_and_outline_table_merge() -> None:
    assert rc.parse_ranges(["sefer_hachukim:1973-2050"]) == {"sefer_hachukim": (1973, 2050)}
    with pytest.raises(SystemExit):
        rc.parse_ranges(["hatzaot_chok:1-2"])  # bills are not captured
    listings = [_data("1972"), _data("1973"), _data("6390", folder_type="3")]
    assert [d["BookletNum"] for d in rc.listings_in_ranges(listings, {"sefer_hachukim": (1973, 2050)})] == ["1973"]
    base = {"schema": gp.GLYPH_OUTLINE_SCHEMA, "built_from": "v1", "unresolved": 0,
            "outlines": {"aa": {"char": "א", "accept": ["א"], "tounicode": {"א": 3}}}}
    new = {"schema": gp.GLYPH_OUTLINE_SCHEMA, "built_from": "x", "unresolved": 1,
           "outlines": {"aa": {"char": "ב", "accept": ["ב"]}, "bb": {"char": None, "accept": [], "tounicode": {".": 1, " ": 1, "פ": 1}}}}
    merged = rc.merge_outline_tables(base, new, built_from="v1 + 2005")
    assert merged["outlines"]["aa"] == base["outlines"]["aa"]  # a known outline is never redefined
    assert merged["extends"] == {"base_outlines": 1, "added_outlines": 1, "added_unresolved": 1}
