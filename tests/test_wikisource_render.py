"""wikisource_plain_text.v2 against MediaWiki's own rendering of pinned pages (F8b3), offline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from hocrgen.config.loader import package_root
from hocrgen.parsers.wikitext import convert_wikitext
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


def _html(entry: dict) -> str:
    html = (FIXTURES / f"{entry['slug']}.html").read_text(encoding="utf-8")
    assert hashlib.sha256(html.encode("utf-8")).hexdigest() == entry["html_sha256"]
    return html


@pytest.mark.parametrize("entry", MANIFEST["pages"], ids=lambda entry: entry["slug"])
def test_converter_matches_mediawiki_rendering(entry: dict) -> None:
    result = compare(_wikitext(entry), _html(entry))
    assert result["converted"], result.get("error")
    assert result["tokens_equal"], (result["ours"], result["theirs"])
    assert result["lines_equal"] == entry["lines_equal"]


def test_fixtures_cover_the_new_constructs() -> None:
    features: set[str] = set()
    sizes: set[str] = set()
    for entry in MANIFEST["pages"]:
        conversion = convert_wikitext(_wikitext(entry))
        features.update(conversion.features)
        sizes.update(conversion.size_spans)
    assert {"footnotes", "footnote_continuations", "editor_notes_dropped", "citations", "quotation_marks", "tables"} <= features
    assert sizes == {"small", "large"}


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
