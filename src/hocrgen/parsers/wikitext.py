"""Deterministic ProofreadPage wikitext to plain page text (F8b).

The conversion keeps the text a reader sees in the page body and drops everything else. It is a small,
closed-world converter, not a MediaWiki renderer: any markup it does not know raises
``UnsupportedWikitextError``, so an unknown template can never silently drop or invent visible text.

Rules, applied in this order (see ``docs/wikisource_proofread_source.md``):

1. Drop ``<noinclude>`` blocks. On a ProofreadPage page they hold the ``<pagequality>`` tag, the running
   header and footer, and ``<references/>``; none of that is page-body text.
2. Drop HTML comments and ``<pagequality>``, ``<section>`` and ``<קטע>`` tags.
3. Reject footnotes (``<ref>``), tables, math, galleries and other markup outside the closed set.
4. Expand templates from the closed table ``TEMPLATE_RULES``: wrappers keep their visible text, notices
   and layout markers are dropped, and an abbreviation keeps the printed form, not its expansion.
5. Links keep their label; file and category links are dropped. Bold and italic quotes are dropped.
6. Paragraphs follow MediaWiki rendering: a single newline inside a paragraph is a space, a blank line
   separates paragraphs, and headings, rules and block templates stand alone.
7. HTML tags are dropped (``<br>`` becomes a line break) and entities are decoded.
8. Bidirectional control characters are removed: the wikitext is already in logical order.
9. Unicode NFC; spaces collapsed per line; at most one blank line between paragraphs.

Line breaks therefore follow the rendered paragraphs, not the printed lines. There is no line geometry.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

WIKITEXT_NORMALIZATION_VERSION = "wikisource_plain_text.v1"

BIDI_CONTROL_CHARACTERS = frozenset(
    "‎‏‪‫‬‭‮⁦⁧⁨⁩﻿"
)

TemplateAction = Literal["keep_first", "drop", "literal"]


@dataclass(frozen=True)
class TemplateRule:
    action: TemplateAction
    literal: str = ""
    block: bool = False
    note: str = ""


# Closed table of he.wikisource templates. Each entry records what the template renders, checked with
# action=expandtemplates on 2026-11-06. Anything else is rejected.
TEMPLATE_RULES: dict[str, TemplateRule] = {
    "!": TemplateRule("literal", literal="|", note="renders a literal vertical bar"),
    "ש": TemplateRule("literal", literal="<br />", note="renders <br />"),
    "ק": TemplateRule("keep_first", note="small text (font-size 83%)"),
    "ג": TemplateRule("keep_first", note="<big> text"),
    "מרכז": TemplateRule("keep_first", block=True, note="centred <div> block"),
    "עם-ניקוד": TemplateRule("keep_first", block=True, note="vocalized-font <div> block"),
    "קיצור": TemplateRule("keep_first", note="abbreviation; the second argument is an editor's tooltip expansion"),
    "סוף": TemplateRule("drop", note="renders a closing </div>"),
    "טקסט מנוקד": TemplateRule("drop", note="opens a vocalized-font <div>"),
}

PAGE_ONLY_TAGS = ("pagequality", "section", "קטע")
UNSUPPORTED_TAGS = ("nowiki", "pre", "ref", "math", "gallery", "timeline", "score", "chem", "graph", "templatestyles", "includeonly", "onlyinclude")
DROPPED_LINK_NAMESPACES = ("file", "image", "קובץ", "תמונה", "category", "קטגוריה")
UNSUPPORTED_LINK_NAMESPACES = ("media",)


class UnsupportedWikitextError(ValueError):
    """Raised when page wikitext contains markup outside the closed conversion set."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"unsupported wikitext {kind}: {detail}")
        self.kind = kind
        self.detail = detail


def pagequality_level(wikitext: str) -> int | None:
    match = re.search(r"<pagequality\b[^>]*\blevel\s*=\s*\"?(\d)", wikitext)
    return int(match.group(1)) if match else None


def wikitext_to_plain_text(wikitext: str) -> str:
    text = wikitext.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"</?noinclude\b", text, flags=re.IGNORECASE):
        raise UnsupportedWikitextError("tag", "unbalanced noinclude")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    for tag in PAGE_ONLY_TAGS:
        text = re.sub(rf"<{tag}\b[^>]*/?>", "", text, flags=re.IGNORECASE)
    for tag in UNSUPPORTED_TAGS:
        if re.search(rf"<{tag}\b", text, flags=re.IGNORECASE):
            raise UnsupportedWikitextError("tag", tag)
    if re.search(r"^\s*\{\|", text, flags=re.MULTILINE):
        raise UnsupportedWikitextError("markup", "table")
    if "__" in text and re.search(r"__[A-Zא-ת]+__", text):
        raise UnsupportedWikitextError("markup", "behaviour switch")
    text = _expand_templates(text)
    text = _replace_links(text)
    text = re.sub(r"'{2,}", "", text)
    text = _join_paragraph_lines(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[A-Za-z][A-Za-z0-9]*\b[^>]*>", "", text)
    text = html.unescape(text)
    text = text.replace(" ", " ")
    text = "".join(char for char in text if char not in BIDI_CONTROL_CHARACTERS)
    text = unicodedata.normalize("NFC", text)
    return _normalize_whitespace(text)


def _join_paragraph_lines(text: str) -> str:
    """Render wikitext line structure: join soft-wrapped lines, keep paragraphs and block lines apart."""

    blocks: list[str] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append(" ".join(paragraph))
            paragraph.clear()

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            flush()
            blocks.append("")
            continue
        if re.fullmatch(r"-{4,}", line):
            flush()
            blocks.append("")
            continue
        heading = re.fullmatch(r"(={1,6})\s*(.*?)\s*\1", line)
        if heading:
            flush()
            blocks.extend(["", heading.group(2), ""])
            continue
        if re.match(r"^[:*#;]", line):
            flush()
            blocks.append(re.sub(r"^[:*#;]+\s*", "", line))
            continue
        paragraph.append(line)
    flush()
    return "\n".join(blocks)


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", raw_line).strip() for raw_line in text.split("\n")]
    collapsed = "\n".join(lines)
    collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
    return collapsed.strip("\n").strip()


def _expand_templates(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("{{", index)
        if start < 0:
            output.append(text[index:])
            break
        output.append(text[index:start])
        end = _matching_braces(text, start)
        output.append(_render_template(text[start + 2 : end - 2]))
        index = end
    rendered = "".join(output)
    if "{{" in rendered or "}}" in rendered:
        raise UnsupportedWikitextError("markup", "unbalanced template braces")
    return rendered


def _matching_braces(text: str, start: int) -> int:
    depth = 0
    index = start
    while index < len(text) - 1:
        pair = text[index : index + 2]
        if pair == "{{":
            depth += 1
            index += 2
            continue
        if pair == "}}":
            depth -= 1
            index += 2
            if depth == 0:
                return index
            continue
        index += 1
    raise UnsupportedWikitextError("markup", "unbalanced template braces")


def _split_arguments(body: str) -> list[str]:
    parts: list[str] = []
    depth_braces = 0
    depth_links = 0
    current: list[str] = []
    index = 0
    while index < len(body):
        pair = body[index : index + 2]
        if pair in ("{{", "}}", "[[", "]]"):
            if pair == "{{":
                depth_braces += 1
            elif pair == "}}":
                depth_braces -= 1
            elif pair == "[[":
                depth_links += 1
            else:
                depth_links -= 1
            current.append(pair)
            index += 2
            continue
        char = body[index]
        if char == "|" and depth_braces == 0 and depth_links == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return parts


def _render_template(body: str) -> str:
    parts = _split_arguments(body)
    name = parts[0].strip()
    if name.startswith("#") or name.startswith(":") or name.casefold().startswith(("subst:", "safesubst:", "msgnw:")):
        raise UnsupportedWikitextError("template", name)
    rule = TEMPLATE_RULES.get(name)
    if rule is None:
        raise UnsupportedWikitextError("template", name)
    for part in parts[1:]:
        numbered = re.match(r"^\s*(\d+)\s*=", part)
        if numbered:
            raise UnsupportedWikitextError("template argument", f"{name}|{numbered.group(1)}=")
    positional = [part for part in parts[1:] if not re.match(r"^\s*[^=\[\]{}|]+=", part)]
    if rule.action == "literal":
        return rule.literal
    if rule.action == "drop":
        return ""
    if not positional:
        return ""
    rendered = _expand_templates(positional[0])
    return f"\n\n{rendered}\n\n" if rule.block else rendered


def _replace_links(text: str) -> str:
    def internal(match: re.Match[str]) -> str:
        target, _, label = match.group(1).partition("|")
        namespace = target.strip().lstrip(":").split(":", 1)[0].strip().casefold() if ":" in target else ""
        if namespace in DROPPED_LINK_NAMESPACES and not target.strip().startswith(":"):
            return ""
        if namespace in UNSUPPORTED_LINK_NAMESPACES:
            raise UnsupportedWikitextError("link", namespace)
        return label if label else target.strip().lstrip(":")

    text = re.sub(r"\[\[([^\[\]]*)\]\]", internal, text)
    if "[[" in text or "]]" in text:
        raise UnsupportedWikitextError("markup", "unbalanced or nested link")
    text = re.sub(r"\[(?:https?:)?//[^\s\]]+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"\[(?:https?:)?//[^\s\]]+\]", "", text)
    return text
