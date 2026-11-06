"""Check ``wikisource_plain_text`` against MediaWiki's own rendering of the same wikitext (F8b3, operator tool).

The converter is closed-world and offline. To keep it honest, this tool asks MediaWiki to render each pinned page
body (``action=parse`` on the pinned wikitext with its ``<noinclude>`` header and footer removed, plus the footer's
``<references/>``), reduces the HTML to its visible lines, and compares them with the converter's text.

The reduction keeps what a reader sees and drops what is display-only:

- the ProofreadPage status banner, the table of contents, edit links and error messages;
- hover tooltips (``TooltipSpan``, e.g. the expansion of ``{{קיצור}}`` or ``{{ב}}``) and ``title`` attributes;
- footnote backlinks (the ``^`` / ``↑`` before each note).

Footnote marks render as ``[n]`` in the body and each note as a line ``[n] text`` where the list stands, as the
converter writes them. Block elements (paragraphs, ``div``, table cells, list items, headings, line breaks) end a
line. The comparison is on whitespace-separated tokens and, separately, on lines.

The network path (capture) is operator-only; ``visible_lines`` and ``compare`` are network-free and used by tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from hocrgen.parsers.wikitext import (
    BIDI_CONTROL_CHARACTERS,
    EDITOR_NOTE_SIGNATURE,
    NOTE_LIST_HEADINGS,
    UnsupportedWikitextError,
    convert_wikitext,
    page_body,
)

WS_API = "https://he.wikisource.org/w/api.php"
USER_AGENT = "hocrgen-wikisource-render-check/0.1 (https://github.com/HeOCR/hocrgen; operator capture)"
BLOCK_TAGS = {
    "p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "dd", "dt", "hr", "center", "ul", "ol", "dl",
    "table", "tr", "td", "th", "blockquote", "pre", "caption",
}
VOID_TAGS = {"br", "hr", "img", "wbr", "link", "meta", "input", "area", "base", "col", "source"}
SKIP_TAGS = {"style", "script"}
SKIP_CLASSES = {"prp-page-qualityheader", "TooltipSpan", "mw-cite-backlink", "mw-editsection", "error", "toc", "mw-empty-elt"}


def body_wikitext(wikitext: str) -> str:
    """The page body MediaWiki is asked to render: the pinned wikitext without its ProofreadPage header and footer,
    plus the footer's ``<references/>``."""

    return page_body(wikitext) + "\n<references/>"


class _Visible(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip_depth = 0
        self.stack: list[tuple[str, bool, bool]] = []
        self.references = 0
        self.note = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        style = (attributes.get("style") or "").replace(" ", "")
        if tag in VOID_TAGS:
            if not self.skip_depth and tag in BLOCK_TAGS:
                self.out.append("\n")
            return
        skip = tag in SKIP_TAGS or bool(classes & SKIP_CLASSES) or attributes.get("id") == "toc" or "display:none" in style
        references = tag == "ol" and "references" in classes
        self.stack.append((tag, skip, references))
        self.references += int(references)
        if skip:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS:
            self.out.append("\n")
        if tag == "li" and self.references:
            self.note += 1
            self.out.append(f"[{self.note}] ")
        if "inline-block" in style:
            self.out.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS:
            return
        while self.stack:
            open_tag, skip, references = self.stack.pop()
            self.references -= int(references)
            if skip:
                self.skip_depth -= 1
            elif not self.skip_depth and open_tag in BLOCK_TAGS:
                self.out.append("\n")
            if open_tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.out.append(data.replace("\n", " "))


def visible_lines(html: str) -> list[str]:
    """MediaWiki HTML reduced to its visible, non-empty lines (bidi controls removed, NFC, spaces collapsed)."""

    parser = _Visible()
    parser.feed(html)
    parser.close()
    text = "".join(parser.out).replace("\xa0", " ").replace("　", " ").replace(" ", " ").replace(" ", " ")
    text = "".join(character for character in text if character not in BIDI_CONTROL_CHARACTERS)
    text = unicodedata.normalize("NFC", text)
    return [line for line in (re.sub(r"\s+", " ", raw).strip() for raw in text.split("\n")) if line]


def tolerate_editor_markup(line: str) -> str:
    """Editor markup errors MediaWiki shows literally and the converter renders as printed (see wikitext.py):
    broken link brackets, and a heading's ``=`` signs left visible by a bidi mark before them."""

    line = line.replace("[[", "").replace("]]", "")
    heading = re.fullmatch(r"(={1,6})\s*(.*?)\s*\1", line)
    return re.sub(r"\s+", " ", heading.group(2) if heading else line).strip()


def drop_editor_notes(lines: list[str]) -> list[str]:
    """Drop notes signed by a Wikisource editor and their marks, and renumber the rest, as the converter does."""

    dropped = {match.group(1) for line in lines if (match := re.match(r"^\[(\d+)\] ", line)) and EDITOR_NOTE_SIGNATURE.search(line)}
    if not dropped:
        return lines
    kept = [line for line in lines if not ((match := re.match(r"^\[(\d+)\] ", line)) and match.group(1) in dropped)]
    numbers: dict[str, str] = {}
    for line in kept:
        for number in re.findall(r"\[(\d+)\]", line):
            if number not in dropped and number not in numbers:
                numbers[number] = str(len(numbers) + 1)

    def renumber(match: re.Match[str]) -> str:
        number = match.group(1)
        return "" if number in dropped else f"[{numbers.get(number, number)}]"

    return [re.sub(r"\s+", " ", re.sub(r"\[(\d+)\]", renumber, line)).strip() for line in kept]


def drop_note_list_headings(lines: list[str]) -> list[str]:
    """Drop an editor's heading that labels the footnote list (``הערות``, ``הערות שוליים``), as the converter does (F8b7)."""

    return [line for index, line in enumerate(lines)
            if not (line in NOTE_LIST_HEADINGS and index + 1 < len(lines) and re.match(r"^\[1\] ", lines[index + 1]))]


def compare(wikitext: str, html: str, transclusions: dict[str, str] | None = None) -> dict[str, Any]:
    """Compare the converter's text with MediaWiki's visible rendering of the same page body.

    ``transclusions`` are the pinned pages the body transcludes by labelled section (F8b4); MediaWiki renders the
    current revisions, so the comparison holds while those are the pinned ones.
    """

    try:
        ours = [line for line in convert_wikitext(wikitext, transclusions).text.split("\n") if line.strip()]
    except UnsupportedWikitextError as error:
        return {"converted": False, "error": str(error), "tokens_equal": False, "lines_equal": False}
    theirs = drop_note_list_headings(drop_editor_notes([tolerate_editor_markup(line) for line in visible_lines(html)]))
    return {
        "converted": True,
        "tokens_equal": " ".join(ours).split() == " ".join(theirs).split(),
        "lines_equal": ours == theirs,
        "ours": ours,
        "theirs": theirs,
    }


# --- Operator capture -----------------------------------------------------------------------------------------


def capture(pages: list[tuple[str, Path]], out_dir: Path, *, delay: float = 1.0) -> None:  # pragma: no cover - network
    """Render each (page title, pinned wikitext file) body with ``action=parse`` and cache the HTML by checksum."""

    out_dir.mkdir(parents=True, exist_ok=True)
    for title, path in pages:
        wikitext = path.read_text(encoding="utf-8")
        body = body_wikitext(wikitext)
        digest = hashlib.sha256(body.encode()).hexdigest()
        target = out_dir / f"{digest}.json"
        if target.exists():
            continue
        data = urllib.parse.urlencode(
            {
                "action": "parse", "title": title, "text": body, "contentmodel": "wikitext", "prop": "text",
                "disablelimitreport": 1, "disableeditsection": 1, "disabletoc": 1, "format": "json",
                "formatversion": 2, "maxlag": 5,
            }
        ).encode()
        for attempt in range(6):
            time.sleep(delay)
            request = urllib.request.Request(WS_API, data=data, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    payload = json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in {429, 500, 502, 503, 504}:
                    time.sleep(min(60, 5 * 2**attempt))
                    continue
                raise
            if (payload.get("error") or {}).get("code") == "maxlag":
                time.sleep(min(60, 5 * 2**attempt))
                continue
            break
        target.write_text(
            json.dumps({"page_title": title, "wikitext_file": path.name, "body_sha256": digest, "html": payload["parse"]["text"]}, ensure_ascii=False),
            encoding="utf-8",
        )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - operator path
    parser = argparse.ArgumentParser(description="Compare wikisource_plain_text with MediaWiki's rendering (operator).")
    parser.add_argument("--inventory", type=Path, required=True, help="Full operator inventory JSON (wikisource_inventory.json).")
    parser.add_argument("--snapshot", type=Path, required=True, help="Operator snapshot root with wikitext/.")
    parser.add_argument("--renders", type=Path, required=True, help="Folder caching the MediaWiki renderings.")
    parser.add_argument("--capture", action="store_true", help="Fetch missing renderings (network).")
    parser.add_argument("--report", type=Path, help="Write a per-page comparison report here.")
    parser.add_argument("--only", type=Path, help="Capture only the page titles listed in this file (one per line).")
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    pages = []
    transcluded: dict[str, dict[str, str]] = {}
    for page in inventory["pages"]:
        number = page["page_title"].rsplit("/", 1)[1]
        slug = f"{page['index_key']}__p{int(number):04d}" if number.isdigit() else None
        path = args.snapshot / "wikitext" / f"{slug}.wikitext.txt"
        if slug and path.exists():
            pages.append((page["page_title"], path))
            transcluded[page["page_title"]] = {
                entry["title"]: (args.snapshot / entry["wikitext_path"]).read_text(encoding="utf-8") for entry in page.get("transclusions") or []
            }
    if args.capture:
        wanted = set(args.only.read_text(encoding="utf-8").splitlines()) if args.only else None
        capture([page for page in pages if wanted is None or page[0] in wanted], args.renders)
    results = []
    for title, path in pages:
        wikitext = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(body_wikitext(wikitext).encode()).hexdigest()
        cached = args.renders / f"{digest}.json"
        if not cached.exists():
            results.append({"page_title": title, "rendered": False})
            continue
        result = compare(wikitext, json.loads(cached.read_text(encoding="utf-8"))["html"], transcluded.get(title))
        results.append({"page_title": title, "rendered": True, **{k: v for k, v in result.items() if k not in {"ours", "theirs"}}})
    summary = {
        "pages": len(results),
        "rendered": sum(r["rendered"] for r in results),
        "converted": sum(bool(r.get("converted")) for r in results),
        "tokens_equal": sum(bool(r.get("tokens_equal")) for r in results),
        "lines_equal": sum(bool(r.get("lines_equal")) for r in results),
    }
    if args.report:
        args.report.write_text(json.dumps({"summary": summary, "pages": results}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    sys.stdout.write(json.dumps(summary) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
