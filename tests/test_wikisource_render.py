"""wikisource_plain_text.v2 against MediaWiki's own rendering of pinned pages (F8b3), offline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.parsers.wikitext import UnsupportedWikitextError, convert_wikitext
from hocrgen.tools.wikisource_render_check import compare, drop_editor_notes, tolerate_editor_markup, visible_lines

FIXTURES = Path("tests/fixtures/wikisource_render")
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def _wikitext(entry: dict) -> str:
    reference = entry.get("wikitext_path")
    if reference:
        path = package_root() / reference.removeprefix("package:")
    else:
        path = FIXTURES / f"{entry['slug']}.wikitext.txt"
    wikitext = path.read_text(encoding="utf-8")
    assert hashlib.sha256(wikitext.encode("utf-8")).hexdigest() == entry["wikitext_sha256"]
    return wikitext


def _transclusions(entry: dict) -> dict[str, str]:
    """F8b4: the pinned pages a fixture page transcludes by labelled section, checked by SHA-256."""

    pinned: dict[str, str] = {}
    for item in entry.get("transclusions") or []:
        wikitext = (FIXTURES / item["path"]).read_text(encoding="utf-8")
        assert hashlib.sha256(wikitext.encode("utf-8")).hexdigest() == item["wikitext_sha256"]
        pinned[item["title"]] = wikitext
    return pinned


def _html(entry: dict) -> str:
    html = (FIXTURES / f"{entry['slug']}.html").read_text(encoding="utf-8")
    assert hashlib.sha256(html.encode("utf-8")).hexdigest() == entry["html_sha256"]
    return html


@pytest.mark.parametrize("entry", MANIFEST["pages"], ids=lambda entry: entry["slug"])
def test_converter_matches_mediawiki_rendering(entry: dict) -> None:
    result = compare(_wikitext(entry), _html(entry), _transclusions(entry))
    assert result["converted"], result.get("error")
    assert result["tokens_equal"], (result["ours"], result["theirs"])
    assert result["lines_equal"] == entry["lines_equal"]


def test_fixtures_cover_the_new_constructs() -> None:
    features: set[str] = set()
    sizes: set[str] = set()
    for entry in MANIFEST["pages"]:
        conversion = convert_wikitext(_wikitext(entry), _transclusions(entry))
        features.update(conversion.features)
        sizes.update(conversion.size_spans)
    assert {"footnotes", "footnote_continuations", "editor_notes_dropped", "citations", "quotation_marks", "tables"} <= features
    assert sizes == {"small", "large"}
    assert any(entry.get("transclusions") for entry in MANIFEST["pages"])  # F8b4: labelled-section transclusion


def test_visible_lines_drop_display_only_parts() -> None:
    html = (
        '<div class="mw-parser-output"><div class="prp-page-qualityheader">banner</div><p>א'
        '<span class="TooltipPhrase">ב<span class="TooltipSpan"><small>הסבר<br /><br /> <a>להרחבה</a></small></span></span>'
        '<sup class="reference"><a>[1]</a></sup> ג<style>.x{}</style></p>'
        '<ol class="references"><li><span class="mw-cite-backlink">^</span> <span class="reference-text">הערה</span></li></ol></div>'
    )
    assert visible_lines(html) == ["אב[1] ג", "[1] הערה"]


def test_editor_notes_and_markup_errors_are_tolerated_as_the_converter_renders_them() -> None:
    assert drop_editor_notes(["א[1] ב[2]", "[1] ט\"ס - ויקיעורך", "[2] הערה"]) == ["א ב[1]", "[1] הערה"]
    assert tolerate_editor_markup("==כותרת==") == "כותרת"
    assert tolerate_editor_markup("[[קישור") == "קישור"


def test_bidi_mark_template_renders_nothing_visible() -> None:
    """F8b5: ``{{כ}}`` writes RLM (LRM with ``ימינה=``); MediaWiki renders ``א{{כ}}ב`` as ``א&#8207;ב``, and bidi marks
    are removed from the plain text, so it shows nothing (Hanokh-B p. 1)."""

    html = '<div class="mw-parser-output"><p>א&#8207;ב\n</p></div>'
    assert visible_lines(html) == ["אב"] or visible_lines(html) == ["א‏ב"]
    assert convert_wikitext("א{{כ}}ב").text == "אב"
    assert convert_wikitext("{{כ|ימינה=כן}}(jaz) gledam").text == "(jaz) gledam"
    with pytest.raises(UnsupportedWikitextError):
        convert_wikitext("{{כ|צבע=אדום}}")


def test_templates_added_for_the_f8b6_indexes() -> None:
    """F8b6: ``{{חיריק ללא אות}}`` (ZWJ + hiriq), ``{{רווח בין אותיות}}`` (letter-spaced text) and ``{{שיר מנוקד}}`` (a poem)."""

    assert convert_wikitext("ב{{חיריק ללא אות}}").text == "ב‍ִ"
    assert convert_wikitext("א {{רווח בין אותיות|שלום עולם }} ב").text == "א שלום עולם ב"
    assert convert_wikitext("{{רווח בין אותיות|.3em|שלום}}").text == "שלום"
    assert convert_wikitext("{{שיר מנוקד|\nשורה א\nשורה ב\n\nשורה ג\n}}").text == "שורה א\nשורה ב\n\nשורה ג"
    slugs = {entry["slug"] for entry in MANIFEST["pages"]}
    assert {"ws_index_336412__p0054", "ws_index_336412__p0156", "ws_index_398674__p0009"} <= slugs  # checked against MediaWiki
