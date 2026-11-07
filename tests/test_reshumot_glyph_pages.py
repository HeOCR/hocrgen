"""F8e2: Reshumot pages rebuilt from their glyph layers, on real pinned pages.

The fixture ``tests/fixtures/reshumot_glyph_pages/snapshot`` holds ten pages of the F8g2 capture, each exercising one
rule (see each entry's ``fixture_note``); two are rejected. Every test re-derives from the committed glyph layer and
render; nothing needs pdfminer or poppler.
"""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.government_print import (
    ReshumotImporter,
    load_government_print_snapshot,
    read_glyph_layer_bytes,
    reshumot_crop_file,
    reshumot_entry_exclusion_reasons,
    reshumot_page_render,
)
from hocrgen.fetchers.wikisource import crop_image
from hocrgen.parsers.pdf_bidi import phrase_key
from hocrgen.parsers.pdf_geometry import (
    GEOMETRY_NORMALIZATION_VERSION,
    dash_between_numbers_ambiguous,
    Glyph,
    Line,
    quote_between_ltr_runs,
    unicode_bidi_display,
    unicode_bidi_visual,
    verify_glyph_page,
    visual_to_logical,
    line_segments,
)
from hocrgen.parsers.pdf_glyphs import glyph_bounds
from hocrgen.tools import government_print_tranche as gpt
from hocrgen.tools.real_tranche import _government_print_items
from hocrgen.utils.hashing import sha256_file

ROOT = Path(__file__).parent / "fixtures" / "reshumot_glyph_pages" / "snapshot"
TABLE_PATH = package_root() / "data" / "reshumot" / "glyph_outlines.json"
RESHUMOT_ID = "reshumot_born_digital"

H3085 = "sefer_hachukim_3085__p0003"
COVER = "sefer_hachukim_2574__p0001"
P2574 = "sefer_hachukim_2574__p0003"
P2006 = "kovetz_hatakanot_6517__p0006"
SIGNED = "sefer_hachukim_3579__p0008"
TWICE = "sefer_hachukim_2663__p0009"
CLIPPED = "sefer_hachukim_2745__p0002"
LATIN = "kovetz_hatakanot_10333__p0002"
STAMP = "kovetz_hatakanot_8764__p0003"
DATE = "kovetz_hatakanot_7070__p0003"
ADMITTED = [H3085, COVER, P2574, P2006, SIGNED, TWICE, CLIPPED, LATIN]


def _source():
    bundle = load_and_validate_bundle()
    return next(source for source in bundle.source_registry.sources if source.id == RESHUMOT_ID)


@pytest.fixture(scope="module")
def entries() -> dict[str, dict]:
    _, rows = load_government_print_snapshot(ROOT)
    return {entry["entry_id"]: entry for entry in rows}


@pytest.fixture(scope="module")
def table() -> dict:
    return json.loads(TABLE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def results(entries, table) -> dict:
    """Each page re-derived from its committed glyph layer and render, as the gate does."""

    out = {}
    for entry_id, entry in entries.items():
        text = entry["text"]
        layer = json.loads(read_glyph_layer_bytes(ROOT / text["extraction"]["raw_local_path"]))
        render = reshumot_page_render(entry)
        expected = [item["text"] for item in text["order_verification"]["expected_phrases"]]
        with Image.open(ROOT / render["local_path"]) as image:
            image.load()
            out[entry_id] = verify_glyph_page(layer, table, image, render["rendering"]["dpi"], expected)
    return out


def _text(entry_id: str) -> str:
    return (ROOT / "text" / f"{entry_id}.txt").read_text(encoding="utf-8")


# --- the outline identity table ---------------------------------------------------------------------------------


def test_outline_table_is_closed_and_every_conflict_is_checked(table) -> None:
    assert table["schema"] == gpt.GLYPH_OUTLINE_SCHEMA and table["unresolved"] == 0
    assert (ROOT / "glyph_outlines.json").read_bytes() == TABLE_PATH.read_bytes()
    for outline, entry in table["outlines"].items():
        texts = {text for text in entry["tounicode"] if text.strip() and text not in "﻿‏‎"}
        if entry.get("shape"):
            assert entry["shape"] in "()[]" and entry["check"]["checked_by"] == "tool"
        elif len(texts) > 1 and not any(texts <= set(group) for group in table["variant_sets"]):
            # Conflicting ToUnicode readings are settled only by a recorded check.
            assert entry["check"]["checked_by"] == "agent" and entry["char"], outline
    # The full stop InDesign maps to a space, U+FFFD, פ, ר, ו or ב in some subsets.
    stop = table["outlines"]["bc3cb841df11b80a"]
    assert stop["char"] == "." and {" ", "פ", "ר"} <= set(stop["tounicode"])
    assert gpt.glyph_outline_table_bytes(table) == TABLE_PATH.read_bytes()


def test_outline_table_builder_needs_a_check_to_settle_a_conflict() -> None:
    fonts = [{"name": "X+Hadasa", "outlines": {"15": "aa", "20": "bb", "11": "cc"}}]
    layer = {"fonts": fonts, "glyphs": [[0, " ", 0, 0, 1, 1, 0, 1, 10, 0, 0, 15], [1, ".", 0, 0, 1, 1, 0, 1, 10, 0, 0, 15],
                                         [2, "3", 0, 0, 1, 1, 0, 1, 10, 0, 0, 20], [3, ")", 0, 0, 1, 1, 0, 1, 10, 0, 0, 11],
                                         [4, "(", 0, 0, 1, 1, 0, 1, 10, 0, 0, 11]]}
    layer["glyphs"].append([5, "ר", 0, 0, 1, 1, 0, 1, 10, 0, 0, 15])
    unchecked = gpt.build_glyph_outline_table([layer], {}, built_from="t")
    assert unchecked["unresolved"] == 1 and unchecked["outlines"]["aa"]["accept"] == [] and unchecked["outlines"]["aa"]["char"] is None
    assert unchecked["outlines"]["bb"] == {**unchecked["outlines"]["bb"], "char": "3", "accept": ["3"]}
    assert unchecked["outlines"]["cc"]["accept"] == ["(", ")"]  # a variant set: either bracket
    checked = gpt.build_glyph_outline_table([layer], {"aa": {"char": ".", "checked_by": "agent", "finding": "a full stop"}, "cc": {"shape": "(", "checked_by": "tool"}}, built_from="t")
    assert checked["unresolved"] == 0 and checked["outlines"]["aa"]["char"] == "." and checked["outlines"]["cc"]["shape"] == "("


def test_glyph_bounds_read_the_glyf_header() -> None:
    header = (1).to_bytes(2, "big", signed=True) + b"".join(value.to_bytes(2, "big", signed=True) for value in (10, -20, 500, 700))
    assert glyph_bounds(header, 2000) == [5, -10, 250, 350]
    assert glyph_bounds(b"", 1000) is None


# --- bidi --------------------------------------------------------------------------------------------------------


def test_forward_bidi_and_its_inverse_round_trip() -> None:
    logical = list('התשע"ו-2016')
    assert "".join(unicode_bidi_visual(logical)) == '2016-ו"עשתה'
    back, facts = visual_to_logical(unicode_bidi_visual(logical))
    assert "".join(back) == "".join(logical) and facts["round_trip"]
    # Numbers separated by a comma and a space stay separate runs: "192, 245" shows as "245 ,192".
    assert "".join(unicode_bidi_visual(list("לפי 192, 245"))) == "245 ,192 יפל"
    back, facts = visual_to_logical(list("245 ,192 יפל"))
    assert "".join(back) == "לפי 192, 245"
    # A Latin word next to a number across a space reads the same printed either way: kept as one run, counted.
    back, facts = visual_to_logical(list("ABC 123 בא"))
    assert "".join(back) == "אב ABC 123" and facts["ambiguous_joins"] == 1


def test_brackets_follow_their_drawn_shape_and_run_direction() -> None:
    # Logical "(א)" in a right-to-left run: the opening bracket stands right, drawn mirrored, so the shapes read
    # "(" "א" ")" left to right. Subsets whose ToUnicode names the logical character give ")" "א" "(" instead.
    shapes = list("(א)")
    logical, facts = visual_to_logical(shapes, [True, False, True])
    assert "".join(logical) == "(א)" and facts["round_trip"]
    assert unicode_bidi_display(logical, [True, False, True]) == shapes
    logical, _ = visual_to_logical(list(")א("))
    assert "".join(logical) == "(א)"
    # In a left-to-right run the shape is the character.
    logical, _ = visual_to_logical(list("(PV)"), [True, False, False, True])
    assert "".join(logical) == "(PV)"


def test_dash_between_numbers_is_unverifiable() -> None:
    # One glyph draws the hyphen (a number separator: "3-6325" stays one run) and the en dash (a neutral: logical
    # "383–385" shows as "385–383"); the page cannot tell which was set.
    assert dash_between_numbers_ambiguous(list("385-383 תוקלח"))
    assert dash_between_numbers_ambiguous(list("(3-6325 ןח)"))
    assert not dash_between_numbers_ambiguous(list('2016-ו"עשתה'))
    assert not dash_between_numbers_ambiguous(list("2016 - 2015"))


def test_quote_between_left_to_right_runs_is_unverifiable() -> None:
    assert quote_between_ltr_runs(list("29º 32' 26.33\" ןופצ"))
    assert not quote_between_ltr_runs(list('אובי "2016" םוקמב'))
    assert not quote_between_ltr_runs(list('ו"עשתה'))


def _glyph(paint, text, x0, size=10.0, baseline=100.0, width=5.0):
    return Glyph(paint, text, x0, baseline - 8, x0 + width, baseline + 2, x0, baseline, size, 0, 0, paint)


def test_word_gaps_tabs_and_letter_spacing() -> None:
    # Open gaps: 0 inside a word, 0.3 em between words (a booklet without space glyphs).
    glyphs = [_glyph(0, "ב", 0), _glyph(1, "א", 5), _glyph(2, "ד", 13), _glyph(3, "ג", 18)]
    (segment,) = line_segments(Line(glyphs=glyphs))
    assert segment.clusters == ["ב", "א", " ", "ד", "ג"] and segment.inferred_spaces == 1
    # Letter-spaced: every letter 0.12 em apart, the word space a space glyph.
    spaced = [_glyph(i, letter, i * 6.2) for i, letter in enumerate("והינתנ")]
    spaced += [_glyph(9, " ", 37.5, width=2.5)] + [_glyph(10 + i, letter, 41.2 + i * 6.2) for i, letter in enumerate("ןימינב")]
    (segment,) = line_segments(Line(glyphs=spaced))
    assert "".join(visual_to_logical(segment.clusters)[0]) == "בנימין נתניהו" and segment.letter_spaced
    # A gap of 0.4 em between frames painted apart (the right one first) cuts the line; within one frame it is a space.
    frames = [_glyph(10, "א", 0), _glyph(11, "ב", 5), _glyph(0, "ג", 14), _glyph(1, "ד", 19)]
    assert len(line_segments(Line(glyphs=frames))) == 2
    together = [_glyph(0, "א", 0), _glyph(1, "ב", 5), _glyph(2, "ג", 14), _glyph(3, "ד", 19)]
    assert len(line_segments(Line(glyphs=together))) == 1
    # Any open gap over 1.5 em is a gutter.
    assert len(line_segments(Line(glyphs=[_glyph(0, "א", 0), _glyph(1, "ב", 25)]))) == 2


# --- real pages ---------------------------------------------------------------------------------------------------


def test_fixture_pages_pass_or_fail_the_gate_as_recorded(entries) -> None:
    source = _source()
    outcomes = {entry_id: reshumot_entry_exclusion_reasons(entry, source, ROOT) for entry_id, entry in entries.items()}
    assert {entry_id for entry_id, reasons in outcomes.items() if not reasons} == set(ADMITTED)
    assert outcomes[STAMP] == outcomes[DATE] == ["extraction_order_not_verified", "missing_expected_phrase"]
    for entry in entries.values():
        extraction = entry["text"]["extraction"]
        assert extraction["normalization"] == GEOMETRY_NORMALIZATION_VERSION and extraction["raw_local_path"].endswith(".glyphs.json.gz")
        assert sha256_file(ROOT / extraction["outline_table_path"]) == extraction["outline_table_sha256"]
        render = reshumot_page_render(entry)
        assert render["rendering"]["is_scan"] is False and render["rendering"]["dpi"] == 150


def test_texts_are_reproduced_from_the_glyph_layers(entries, results) -> None:
    for entry_id, result in results.items():
        assert result.text == _text(entry_id), entry_id
        assert result.issues == entries[entry_id]["text"]["order_verification"]["issues"], entry_id


def test_hidden_tagged_copy_is_dropped_and_wrong_tounicode_entries_are_repaired(results) -> None:
    facts = results[H3085].facts()
    assert facts["glyphs_hidden_by_fill"]["white"] > 1000  # the old copy under the white rectangle
    assert facts["format_characters_removed"]["U+FEFF"] > 100  # space glyphs mapped to U+FEFF
    text = _text(H3085)
    assert '"מברר" - סוהר שמונה לפי סעיף 3ג(ג);' in text.splitlines()[0]
    assert 'חדש], התשל"ב-1971 3;' in text  # the footnote marker set off from the year, after it
    assert "ספר החוקים 3085, י\"ט באב התשפ\"ג, 6.8.2023" in text and text.count("ספר החוקים 3085") == 1
    assert "﻿" not in text and "‏" not in text
    # 2016: the full stops of this font subset are mapped to a space; the outline names them.
    assert results[P2574].facts()["glyph_identity"]["repaired"] > 30
    assert "בעניינו." in _text(P2574) and "ספר החוקים 2574, ז' באב התשע\"ו, 11.8.2016" in _text(P2574)


def test_reading_order_side_headings_labels_and_footnotes(results) -> None:
    lines = _text(P2574).splitlines()
    heading = lines.index("מועד בחירת")
    assert lines[heading + 1] == "הנציב" and lines[heading + 2].startswith("3. מינוי נציב ייעשה")
    assert "7 ס\"ח התשי\"ט, עמ' 86." in lines


def test_space_glyphless_booklets_letter_spacing_and_double_strikes(results) -> None:
    assert results[P2006].facts()["layout"]["inferred_spaces"] > 100
    assert "כ\"ט באב התשס\"ו (23 באוגוסט 2006)" in _text(P2006)
    assert "בנימין נתניהו" in _text(SIGNED) and results[SIGNED].facts()["layout"]["letter_spaced_segments"] >= 1
    assert results[TWICE].facts()["glyphs_painted_twice"] > 30
    assert _text(TWICE).splitlines()[-2] == "ספר החוקים 2663, י\"ז באב התשע\"ז, 9.8.2017"
    # A label set in white has no ink: it is not on the image, so it is not in the text, and nothing is cropped.
    assert results[CLIPPED].verdict.dropped == {"no_ink": 1} and results[CLIPPED].verdict.regions is None
    assert "הערות" in results[CLIPPED].conversion.text and "הערות" not in _text(CLIPPED)


def test_unverified_lines_and_page_images_are_cropped_out(entries, results) -> None:
    cover = entries[COVER]
    assert cover["pdf"]["page_image_count"] == 1 and cover["crop"]["method"] == "pdf_glyph_regions.v1"
    assert reshumot_crop_file(cover)["local_path"] == f"assets/{COVER}__crop.png"
    assert [item["source"] for item in cover["text"]["order_verification"]["expected_phrases"][:2]] == [
        "gazette API FolderType (cover)", "gazette API BookletNum (cover)"]
    latin = entries[LATIN]
    assert len(latin["crop"]["regions_normalized"]) == 2 and latin["crop"]["units_left_out"] == {"unverified": 1}
    dropped = [unit for unit in results[LATIN].conversion.units if unit not in results[LATIN].verdict.kept]
    assert dropped and dropped[0].issues and dropped[0].text not in _text(LATIN)
    for entry_id in (COVER, LATIN):
        entry = entries[entry_id]
        with Image.open(ROOT / reshumot_page_render(entry)["local_path"]) as page, Image.open(ROOT / reshumot_crop_file(entry)["local_path"]) as cropped:
            assert cropped.convert("RGB").tobytes() == crop_image(page, entry["crop"]).tobytes()


def test_rejections_keep_their_reasons(results) -> None:
    # The added stamp overlaps the running footer, so the footer cannot be cut apart and the anchors are missing.
    assert results[STAMP].verdict.dropped.get("unverified", 0) >= 1
    assert phrase_key("קובץ התקנות 8764,") in phrase_key(results[STAMP].conversion.text)
    assert phrase_key("קובץ התקנות 8764,") not in phrase_key(results[STAMP].text)
    # The print says 1.1.2012 (ו' בטבת התשע"ב); the gazette API says 2012-11-01.
    assert "1.1.2012" in _text(DATE) and results[DATE].issues == ["missing_expected_phrase"]


def test_ink_checks_catch_ink_no_glyph_explains(entries, table) -> None:
    entry = entries[H3085]
    layer = json.loads(read_glyph_layer_bytes(ROOT / entry["text"]["extraction"]["raw_local_path"]))
    expected = [item["text"] for item in entry["text"]["order_verification"]["expected_phrases"]]
    with Image.open(ROOT / reshumot_page_render(entry)["local_path"]) as image:
        tampered = image.convert("L")
    ImageDraw.Draw(tampered).rectangle((20, 700, 40, 712), fill=0)  # a mark in the margin, no glyph under it
    result = verify_glyph_page(layer, table, tampered, 150, expected)
    assert result.verdict.regions is not None and result.verdict.ink.blobs and result.text == _text(H3085)
    blank = Image.new("L", tampered.size, 255)  # no ink anywhere: every line is off the image
    assert verify_glyph_page(layer, table, blank, 150, expected).issues == ["no_verified_text"]


# --- the gate and the fetcher ---------------------------------------------------------------------------------------


def _tmp_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "snapshot"
    shutil.copytree(ROOT, root)
    return root


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda root, e: (root / e["text"]["local_path"]).write_text("x", encoding="utf-8"), "text_checksum_mismatch"),
        (lambda root, e: (root / e["text"]["extraction"]["raw_local_path"]).write_bytes(gzip.compress(b"{}")), "extraction_checksum_mismatch"),
        (lambda root, e: (root / "glyph_outlines.json").write_text("{}", encoding="utf-8"), "glyph_outline_table_checksum_mismatch"),
        (lambda root, e: (root / reshumot_page_render(e)["local_path"]).unlink(), "page_render_missing"),
        (lambda root, e: (root / reshumot_crop_file(e)["local_path"]).write_bytes(b"x"), "crop_asset_checksum_mismatch"),
    ],
)
def test_gate_reports_broken_pins(tmp_path: Path, entries, change, reason) -> None:
    root = _tmp_snapshot(tmp_path)
    entry = json.loads(json.dumps(entries[COVER]))
    change(root, entry)
    assert reshumot_entry_exclusion_reasons(entry, _source(), root) == [reason]


def test_gate_re_derives_text_and_crop(tmp_path: Path, entries) -> None:
    root = _tmp_snapshot(tmp_path / "text")
    source = _source()
    entry = json.loads(json.dumps(entries[P2574]))
    edited = _text(P2574).replace("בעניינו.", "בעניינו")
    (root / entry["text"]["local_path"]).write_text(edited, encoding="utf-8")
    entry["text"]["sha256"] = sha256_file(root / entry["text"]["local_path"])
    assert reshumot_entry_exclusion_reasons(entry, source, root) == ["text_not_reproducible_from_extraction"]
    root = _tmp_snapshot(tmp_path / "crop")
    cover = json.loads(json.dumps(entries[COVER]))
    cover["crop"]["box_normalized"] = [0.0, 0.0, 1.0, 1.0]
    assert reshumot_entry_exclusion_reasons(cover, source, root) == ["crop_geometry_mismatch"]
    uncropped = json.loads(json.dumps(entries[COVER]))
    uncropped.pop("crop")
    uncropped["files"] = [reshumot_page_render(uncropped)]
    assert reshumot_entry_exclusion_reasons(uncropped, source, root) == ["pdf_not_born_digital"]  # the image stays in
    full = json.loads(json.dumps(entries[P2574]))
    full["crop"] = entries[COVER]["crop"]
    assert reshumot_entry_exclusion_reasons(full, source, root) == ["crop_not_expected"]
    # Cropped pixels that differ from the render cut at the recorded regions are refused.
    cover = json.loads(json.dumps(entries[COVER]))
    asset = root / reshumot_crop_file(cover)["local_path"]
    with Image.open(asset) as image:
        image = image.convert("RGB")
    image.putpixel((0, 0), (0, 0, 0))
    image.save(asset)
    reshumot_crop_file(cover)["sha256"] = sha256_file(asset)
    assert reshumot_entry_exclusion_reasons(cover, source, root) == ["crop_pixels_mismatch"]


def test_fetcher_discovers_fixture_pages_with_crop_metadata(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(ROOT, config_root / "reshumot_glyph_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == RESHUMOT_ID:
            source["settings"]["extra"]["government_print_snapshot_root"] = "reshumot_glyph_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    bundle = load_and_validate_bundle(config_root)
    source = next(source for source in bundle.source_registry.sources if source.id == RESHUMOT_ID)
    importer = ReshumotImporter()
    options = StageOptions()
    discovered = importer.discover_candidates(source, bundle, options)
    assert sorted(candidate.source_item_id for candidate in discovered) == sorted(ADMITTED)
    enriched = {record.source_item_id: record for record in importer.fetch_candidate_metadata(source, bundle, discovered, options)}
    cover = enriched[COVER]
    assert cover.asset_references[0].reference == f"assets/{COVER}__crop.png"
    assert cover.metadata["cropped"] is True and cover.metadata["crop_method"] == "pdf_glyph_regions.v1"
    assert enriched[H3085].metadata["cropped"] is False and enriched[H3085].metadata["text_normalization"] == GEOMETRY_NORMALIZATION_VERSION
    acquired = importer.acquire_items(source, bundle, [_item(enriched[COVER])], tmp_path / "acquire", options)
    assert acquired[0].acquired_assets[0].sha256 == enriched[COVER].metadata["expected_asset_sha256"]


def _item(record):
    from hocrgen.manifests.models import ItemRecord

    return ItemRecord(
        **record.model_dump(), item_id=record.candidate_id, normalized_license="PD-IL", rights_classification="open",
        eligibility="review_required", eligibility_reason="f8e2 fixture",
    )


def test_tranche_manifest_items_mark_cropped_pages(tmp_path: Path, entries) -> None:
    root = _tmp_snapshot(tmp_path)
    admitted = [entries[entry_id] for entry_id in sorted(ADMITTED)]
    (root / "entries.jsonl").write_text("".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in admitted), encoding="utf-8")
    items = {item["source_item_id"]: item for item in _government_print_items(root, source_id=RESHUMOT_ID)}
    assert items[COVER]["cropped"] is True and items[COVER]["asset"]["path"] == f"assets/{COVER}__crop.png"
    assert items[H3085]["cropped"] is False and items[H3085]["asset"]["path"] == f"assets/{H3085}.png"


# --- builders --------------------------------------------------------------------------------------------------------


def _api_row_and_pdf_facts(entry: dict) -> tuple[dict, dict]:
    """The gazette API row and pdfinfo facts an entry was built from, read back from the entry."""

    booklet, pdf, upstream = entry["booklet"], entry["pdf"], entry["upstream"]
    row = {
        "BookletNum": booklet["booklet_number"], "BookletYear": booklet["booklet_year_index"], "FolderType": booklet["folder_type"],
        "ForeignYear": booklet["foreign_year"], "Pages": booklet["page_count"], "PublishDate": booklet["publish_date"] + "T00:00:00+02:00",
        "Document": [{"DisplayName": booklet["display_name"], "FileName": pdf["document_url"]}],
        "DocSummary": {"DescriptionHtmlString": upstream["doc_summary_html"]}, "ModifyDate": upstream["modify_date"],
    }
    facts = {
        "info": {"Creator": pdf["creator"], "Producer": pdf["producer"], "CreationDate": pdf["creation_date"], "Pages": str(pdf["page_count"])},
        "fonts": pdf["embedded_fonts"], "sha256": pdf["sha256"], "bytes": pdf["bytes"],
    }
    return row, facts


@pytest.mark.parametrize("entry_id", [COVER, H3085, LATIN, DATE])
def test_entry_builder_reproduces_the_committed_entries(entries, table, entry_id) -> None:
    entry = entries[entry_id]
    row, facts = _api_row_and_pdf_facts(entry)
    raw = ROOT / entry["text"]["extraction"]["raw_local_path"]
    layer = json.loads(read_glyph_layer_bytes(raw))
    assert gpt.glyph_layer_bytes(layer) == raw.read_bytes()  # the committed form is byte-reproducible
    render = reshumot_page_render(entry)
    with Image.open(ROOT / render["local_path"]) as image:
        image.load()
        rebuilt, logical, issues, cropped = gpt.reshumot_glyph_page_entry(
            data=row, pdf=facts, page=entry["page"]["pdf_page_index"], page_image_count=entry["pdf"]["page_image_count"], layer=layer,
            layer_sha256=sha256_file(raw), table=table, table_sha256=sha256_file(TABLE_PATH), render_file=render, render_image=image,
            captured_at=entry["rights"]["verified_at"],
        )
    expected = {key: value for key, value in entry.items() if key != "fixture_note"}
    assert json.loads(json.dumps(rebuilt, ensure_ascii=False)) == expected
    assert logical == _text(entry_id) and issues == entry["text"]["order_verification"]["issues"]
    assert (cropped is not None) == ("crop" in entry)
    if cropped is not None:
        assert cropped[1] == (ROOT / reshumot_crop_file(entry)["local_path"]).read_bytes()


def _truetype(glyphs: list[bytes], *, long_offsets: bool = False, units_per_em: int = 1000) -> bytes:
    import struct

    glyf = b"".join(glyphs)
    offsets, position = [], 0
    for glyph in glyphs:
        offsets.append(position)
        position += len(glyph)
    offsets.append(position)
    loca = struct.pack(f">{len(offsets)}I", *offsets) if long_offsets else struct.pack(f">{len(offsets)}H", *(value // 2 for value in offsets))
    head = bytearray(54)
    head[18:20] = struct.pack(">H", units_per_em)
    head[50:52] = struct.pack(">h", 1 if long_offsets else 0)
    maxp = struct.pack(">IH", 0x00005000, len(glyphs))
    tables = {b"glyf": glyf, b"head": bytes(head), b"loca": loca, b"maxp": maxp}
    directory = struct.pack(">IHHHH", 0x00010000, len(tables), 0, 0, 0)
    offset = 12 + 16 * len(tables)
    entries, body = b"", b""
    for tag, data in tables.items():
        entries += struct.pack(">4sIII", tag, 0, offset + len(body), len(data))
        body += data + b"\0" * (-len(data) % 4)
    return directory + entries + body


def test_truetype_outlines_and_units_are_read_from_the_font_program() -> None:
    from hocrgen.parsers.pdf_glyphs import truetype_glyph_outlines, truetype_units_per_em

    glyph = (1).to_bytes(2, "big") + b"".join(value.to_bytes(2, "big", signed=True) for value in (0, 0, 500, 700)) + b"\0\0"
    for long_offsets in (False, True):
        font = _truetype([b"", glyph, glyph + b"\0\0"], long_offsets=long_offsets, units_per_em=2048)
        outlines = truetype_glyph_outlines(font)
        assert outlines == [b"", glyph, glyph + b"\0\0"] and truetype_units_per_em(font) == 2048
    assert truetype_glyph_outlines((0x00010000).to_bytes(4, "big") + b"\0" * 8) is None  # no glyf table: no outlines
