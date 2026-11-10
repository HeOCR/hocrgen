"""Network-free tests for Google scan hygiene (hocrgen.fetchers.google_hygiene): front matter and watermark."""

from __future__ import annotations

import datetime as dt
import json

from hocrgen.fetchers import google_hygiene as gh
from hocrgen.fetchers import ia_justification as ij
from test_ia_justification import AS_OF, ROW, WIKIDATA, _metadata

HEADER = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"


def _tsv(lines: list[list[tuple[str, tuple[int, int, int, int]]]]) -> str:
    rows = [HEADER]
    for n, words in enumerate(lines):
        for j, (text, (x, y, w, h)) in enumerate(words):
            rows.append(f"5\t1\t1\t1\t{n}\t{j}\t{x}\t{y}\t{w}\t{h}\t91.0\t{text}")
    return "\n".join(rows) + "\n"


def _words(sentence: str, y: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    return [(word, (20 + 60 * i, y, 55, 20)) for i, word in enumerate(sentence.split())]


# A synthetic front page built from the boilerplate phrases the detector looks for (no scan image is committed).
FRONT = _tsv([
    _words("This is a digital copy of a book that was pre- served for generations on library shelves", 40),
    _words("Usage guidelines", 400),
    _words("Google is proud to partner with libraries to digitize public domain materials", 440),
    _words("We also ask that you:", 600),
    _words("+ Make non-commercial use of the files", 640),
])
BODY = _tsv([_words("Ann 4 aan Dew gw ma? mn rar dy xan", 40), _words("pony nix yp m3 59 sipna nw", 80)])


def test_google_front_page_is_detected_and_a_text_page_is_not() -> None:
    is_front, phrases = gh.detect_google_front_matter(FRONT)
    assert is_front
    # Word splits in the OCR ("pre- served") do not hide the opening sentence: phrases are compared letters only.
    assert phrases[0] == gh.OPENING_PHRASES[0]
    assert "Make non-commercial use of the files" in phrases
    assert gh.detect_google_front_matter(BODY) == (False, [])
    # One supporting phrase alone is not enough.
    assert gh.detect_google_front_matter(_tsv([_words("Usage guidelines", 40)]))[0] is False


def test_watermark_box_is_found_in_the_foot_band_and_scaled_to_the_canvas() -> None:
    # The logo often reads as noise ("VjOOQlC"); "Digitized" anchors the line.
    band = _tsv([[("~", (1260, 170, 10, 5)), ("Digitized", (1288, 169, 109, 29)), ("by", (1405, 170, 30, 29)), ("VjOOQlC", (1445, 162, 123, 43))]])
    box = gh.detect_google_watermark(band, band_top=1737, scale=2.0)
    # Union 1288..1568 x 162..205 in band pixels, padded by a quarter of its 43 px height, then scaled x2.
    assert box == [round((1288 - 10.75) * 2), round((162 - 10.75 + 1737) * 2), round((280 + 21.5) * 2), round((43 + 21.5) * 2)]
    google_only = _tsv([[("by", (1405, 170, 30, 29)), ("Gooqle", (1445, 162, 123, 43))]])
    assert gh.detect_google_watermark(google_only, band_top=0, scale=1.0) is not None
    assert gh.detect_google_watermark(_tsv([_words("23", 10)]), band_top=0, scale=1.0) is None


def test_foot_band_and_overlap_helpers() -> None:
    assert gh.foot_band_box((1600, 2000)) == (0, 1800, 1600, 2000)
    assert gh.foot_band_box((1600, 2000), 0.15) == (0, 1700, 1600, 2000)
    assert gh.boxes_overlap([0, 0, 10, 10], [5, 5, 10, 10]) and not gh.boxes_overlap([0, 0, 10, 10], [10, 0, 5, 5])


def test_hygiene_record_fills_the_google_justification() -> None:
    hygiene = gh.hygiene_record(
        [{"canvas_index": 0, "reason": gh.EXCLUDED_GOOGLE_FRONT_MATTER, "phrases": [gh.OPENING_PHRASES[0]]}],
        {1: [10, 2900, 400, 80], 2: None},
    )
    assert hygiene["watermark_boxes"] == [{"canvas_index": 1, "google_watermark_bbox": [10, 2900, 400, 80]}]
    assert hygiene["pages_without_watermark"] == [2]
    metadata = _metadata(identifier="bub_gb_AbCdEf123", contributor=None, sponsor="Google")
    result = ij.build_ia_rights_justification(
        metadata, catalogue_row=ROW, wikidata=WIKIDATA, as_of=AS_OF, metadata_sha256="d" * 64, manifest_url="u",
        manifest_sha256="m" * 64, canvas_count=3, image_urls=[], hygiene=hygiene,
    )
    assert result.accepted and result.record["hygiene"]["excluded_front_matter"][0]["reason"] == "excluded_google_front_matter"
    # The back-fill reads the alignment's scan.google_hygiene, so it rebuilds the same record.
    metadata_bytes = json.dumps(metadata).encode()
    alignment = {"work": {"pby_id": ROW["ID"]}, "pages": [],
                 "scan": {"source": "internet_archive", "ia_identifier": "bub_gb_AbCdEf123", "manifest_url": "u",
                          "manifest_upstream_sha256": "m" * 64, "canvas_count": 3, "google_hygiene": hygiene}}
    again = ij.justify_existing_alignment(alignment, metadata_bytes, WIKIDATA, dt.date(2026, 11, 10), catalogue_row=ROW)
    assert again.accepted and again.record["hygiene"] == hygiene
