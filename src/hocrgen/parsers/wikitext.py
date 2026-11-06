"""Deterministic ProofreadPage wikitext to plain page text (F8b, extended in F8b3).

The conversion keeps the text a reader sees in the page body and drops everything else. It is a closed-world
converter, not a MediaWiki renderer: any markup it does not know raises ``UnsupportedWikitextError``, so an
unknown construct can never silently drop or invent visible text. Each known template has a rendering written
from its he.wikisource source; ``hocrgen.tools.wikisource_render_check`` compares the result with MediaWiki's own
``action=parse`` rendering of the pinned pages.

Rules, applied in this order (see ``docs/wikisource_proofread_source.md``):

1. Drop ``<noinclude>`` blocks. On a ProofreadPage page they hold the ``<pagequality>`` tag, the running
   header and footer, and ``<references/>``; none of that is page-body text.
2. Drop HTML comments and ``<pagequality>``, ``<section>`` and ``<קטע>`` tags.
3. Reject markup whose semantics are not implemented (``<nowiki>``, ``<pre>``, math, galleries, parser
   functions, unknown templates, ...).
4. Expand templates from the closed table ``TEMPLATE_RENDERERS``: wrappers keep their visible text, notices,
   anchors and layout markers are dropped, tooltips keep only the visible word, and citation templates keep the
   citation as MediaWiki shows it. Size templates and ``<small>`` / ``<big>`` keep their text and are counted in
   ``WikitextConversion.size_spans``.
5. Footnotes (``<ref>`` and ``{{הערה}}``): the mark becomes ``[n]`` in the body, numbered in order of first use as
   MediaWiki numbers them, and each note becomes a line ``[n] text`` where ``<references/>`` (or
   ``{{הערות שוליים}}``) stands, else after the body. That matches the print's layout (mark in the body, note at
   the foot of the page), but not the print's own mark (``*)``, ``1)``, ...), which editors do not type. A note
   signed by a Wikisource editor ("ויקיעורך") is not printed: it and its mark are dropped and counted.
6. Tables (``{| ... |}``) and block HTML (``div``, ``center``, ``p``, ``table`` cells, list items, ``poem``) end
   paragraphs, so each cell or block is its own line, in source (logical) order.
7. Links keep their label; file and category links are dropped. Bold and italic quotes are dropped.
8. Paragraphs follow MediaWiki rendering: a single newline inside a paragraph is a space, a blank line
   separates paragraphs, and headings, rules and block templates stand alone.
9. HTML tags are dropped (``<br>`` becomes a line break) and entities are decoded.
10. Bidirectional control characters are removed (the wikitext is already in logical order); Unicode space
    separators become plain spaces.
11. Unicode NFC; spaces collapsed per line; at most one blank line between paragraphs.

Line breaks therefore follow the rendered paragraphs, not the printed lines. There is no line geometry.

``wikisource_plain_text.v2`` (F8b3) extends v1's closed set; every page v1 converts gives the same text under v2.
"""

from __future__ import annotations

import html
import json
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

WIKITEXT_NORMALIZATION_VERSION = "wikisource_plain_text.v2"

BIDI_CONTROL_CHARACTERS = frozenset("\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff")

PAGE_ONLY_TAGS = ("pagequality", "section", "קטע")
UNSUPPORTED_TAGS = (
    "pre", "math", "gallery", "timeline", "score", "chem", "graph", "templatestyles", "onlyinclude",
    "syntaxhighlight", "source", "hiero", "imagemap", "inputbox", "categorytree", "mapframe",
)
DROPPED_LINK_NAMESPACES = ("file", "image", "קובץ", "תמונה", "category", "קטגוריה")
UNSUPPORTED_LINK_NAMESPACES = ("media",)
BLOCK_HTML_TAGS = ("div", "center", "p", "table", "tr", "td", "th", "caption", "blockquote", "ul", "ol", "li", "dl", "dd", "dt", "h1", "h2", "h3", "h4", "h5", "h6")
# F8b7: an editor's heading that labels MediaWiki's footnote list ("==הערות==", "==הערות שוליים==" right before
# {{הערות שוליים}} or <references/>) is not printed: the print's footnotes stand at the foot of the page unlabelled.
NOTE_LIST_HEADINGS = ("הערות", "הערות שוליים")
_NOTE_LIST_HEADING = re.compile(
    r"^[ \t]*(={1,6})[ \t]*(?:" + "|".join(NOTE_LIST_HEADINGS) + r")[ \t]*\1[ \t]*\n(?=\s*(?:\{\{\s*הערות שוליים\s*[|}]|\ue002))",
    re.MULTILINE,
)
# A footnote signed by a Wikisource editor ("ויקיעורך", "ויקי עורך", "הערת ויקיעורך") is not printed on the page.
EDITOR_NOTE_SIGNATURE = re.compile(r"ויקי\s?עור(?:ך|כת)")

_NOTE_MARK = "\ue000{}\ue001"
_NOTE_MARK_PATTERN = re.compile("\ue000(\\d+)\ue001")
_REFERENCES = "\ue002"
_REF_TEMPLATE = "\ue003ref"
_NOWIKI = "\ue004{}\ue005"
_NOWIKI_PATTERN = re.compile("\ue004(\\d+)\ue005")


class UnsupportedWikitextError(ValueError):
    """Raised when page wikitext contains markup outside the closed conversion set."""

    def __init__(self, kind: str, detail: str) -> None:
        super().__init__(f"unsupported wikitext {kind}: {detail}")
        self.kind = kind
        self.detail = detail


def pagequality_level(wikitext: str) -> int | None:
    match = re.search(r"<pagequality\b[^>]*\blevel\s*=\s*\"?(\d)", wikitext)
    return int(match.group(1)) if match else None


@dataclass(frozen=True)
class WikitextConversion:
    """The plain page text, counts of typographic size spans (``small`` / ``large``), and other features.

    ``features`` counts constructs that matter for provenance: ``footnotes`` (notes kept), ``editor_notes_dropped``,
    ``citations`` (editor citation templates such as ``{{ממ}}``), ``quotation_marks`` (templates that add quotation
    marks, such as ``{{צ}}``), ``tables`` and ``columns``.
    """

    text: str
    size_spans: dict[str, int] = field(default_factory=dict)
    features: dict[str, int] = field(default_factory=dict)


# --- Template arguments ----------------------------------------------------------------------------------------


class Args:
    """Template arguments with MediaWiki semantics: positional values keep whitespace, named values are trimmed,
    and an explicit ``n=`` names positional parameter ``n``."""

    def __init__(self, name: str, parts: list[str]) -> None:
        self.name = name
        self.values: dict[str, str] = {}
        self.hidden: list[str] = []
        position = 0
        for part in parts:
            named = re.match(r"^\s*([^=\[\]{}|<>]*[^\s=\[\]{}|<>][^=\[\]{}|<>]*?)\s*=(.*)$", part, flags=re.DOTALL)
            if named and "\n" in named.group(1).strip():
                named = None  # an "=" of a heading line, not a name/value separator (MediaWiki's preprocessor)
            if named:
                self.values[named.group(1)] = named.group(2).strip()
            else:
                position += 1
                self.values[str(position)] = part

    def check(self, *allowed: str) -> Args:
        """Reject a named parameter the template does not know; positional ones it does not use are hidden.

        A blank unused parameter has no visible effect. A non-blank positional parameter beyond those the template
        uses is not shown by MediaWiki either (an editor's stray ``|``); it is hidden here too and counted in
        ``hidden_arguments``.
        """

        used = {key for key in allowed if key.isdigit()}
        top = max((int(key) for key in used), default=0)
        unknown = sorted(key for key, value in self.values.items() if key not in allowed and value.strip())
        for key in unknown:
            if key.isdigit() and int(key) > top:
                self.hidden.append(key)
                continue
            raise UnsupportedWikitextError("template argument", f"{self.name}|{key}")
        return self

    def raw(self, key: str, default: str | None = None) -> str | None:
        return self.values.get(key, default)

    def filled(self, key: str) -> bool:
        """``{{#תנאי:{{{key|}}}|...}}``: the parameter is given and not blank."""

        return bool((self.values.get(key) or "").strip())

    def need(self, key: str) -> str:
        """``{{{key}}}`` with no default: a missing parameter would render literally, so it is rejected."""

        if key not in self.values:
            raise UnsupportedWikitextError("template argument", f"{self.name} without {key}")
        return self.values[key]


class _Context:
    def __init__(self, unprinted_notes: frozenset[int] = frozenset()) -> None:
        # F8b7: footnote numbers (as the faithful conversion numbers them) a reviewed check found not printed.
        self.unprinted_notes = unprinted_notes
        self.sizes: Counter[str] = Counter()
        self.features: Counter[str] = Counter()
        self.ref_bodies: list[tuple[str | None, str | None, bool]] = []
        self.notes: list[str] = []
        self.note_names: dict[str, int] = {}
        self.follow: list[str] = []
        self.nowiki: list[str] = []
        self.depth = 0

    def expand(self, text: str) -> str:
        self.depth += 1
        if self.depth > 40:
            raise UnsupportedWikitextError("markup", "template recursion")
        try:
            return _expand_templates(text, self)
        finally:
            self.depth -= 1

    def note(self, body: str | None, name: str | None) -> str:
        """Register a footnote and return its body mark, reusing the number of an earlier note of the same name."""

        if name and name in self.note_names:
            index = self.note_names[name]
            if body and body.strip() and not self.notes[index].strip():
                self.notes[index] = body
            return _NOTE_MARK.format(index)
        if body is None or not body.strip():
            if name:
                raise UnsupportedWikitextError("footnote", f"reference to note {name!r} defined elsewhere")
            raise UnsupportedWikitextError("footnote", "empty note")
        self.notes.append(body)
        if name:
            self.note_names[name] = len(self.notes) - 1
        return _NOTE_MARK.format(len(self.notes) - 1)


Renderer = Callable[[Args, _Context], str]


def _v(args: Args, ctx: _Context, key: str, default: str = "") -> str:
    """``{{{key|default}}}`` expanded."""

    return ctx.expand(args.raw(key, default) or "")


def _block(text: str) -> str:
    return f"\n\n{text}\n\n"


def _literal(value: str) -> Renderer:
    def render(args: Args, ctx: _Context) -> str:
        args.check()
        return value

    return render


def _drop(*allowed: str) -> Renderer:
    def render(args: Args, ctx: _Context) -> str:
        args.check(*allowed)
        return ""

    return render


def _keep_first(*, block: bool = False, size: str | None = None) -> Renderer:
    """The v1 rule: render the first positional parameter (or ``1=``); other parameters are not shown.

    Used for templates whose further parameters are invisible (a tooltip, a font or size option).
    """

    def render(args: Args, ctx: _Context) -> str:
        if size:
            ctx.sizes[size] += 1
        if "1" not in args.values:
            return ""
        text = ctx.expand(args.values["1"])
        return _block(text) if block else text

    return render


def _params(*keys: str, required: bool = False, size: str | None = None, block: bool = False, wrap: str = "{}") -> Renderer:
    """Render the listed parameters in order (``{{{1|}}}{{{name|}}}``); any other argument is rejected."""

    def render(args: Args, ctx: _Context) -> str:
        args.check(*keys)
        if required and any(key not in args.values for key in keys):
            raise UnsupportedWikitextError("template argument", f"{args.name} without its text")
        if size:
            ctx.sizes[size] += 1
        text = wrap.format("".join(ctx.expand(args.values[key]) for key in keys if key in args.values))
        return _block(text) if block else text

    return render


def _space(args: Args, ctx: _Context) -> str:
    return " "


def _quoted(content: str, args: Args, ctx: _Context) -> str:
    """``{{צ}}``-style quotation: the content between quotation marks unless ``מרכאות=לא``."""

    ctx.features["quotation_marks"] += 1
    mark = "" if (args.raw("מרכאות") or "").strip() == "לא" else '"'
    return f"{mark}{content}{mark}"


def _citation_label(book: str, chapter: str, verse: str | None, see: str | None, *, two_part: bool) -> str:
    """Visible label of ``{{מ"מ}}``: ``(book chapter, verse)``; ``.`` / ``:`` verses attach without a comma."""

    if verse is None:
        label = f"({book}, {chapter}" if two_part else f"({book} {chapter}"
    else:
        shown = verse if verse in {".", ":"} else f", {verse}"
        label = f"({book} {chapter}{shown}"
    if see:
        label += f" {see}"
    return f"<small>{label})</small>"


def _mm(args: Args, ctx: _Context) -> str:
    """``{{מ"מ}}`` / ``{{ממ}}``: an editor's source citation, shown small in parentheses.

    With three parameters the label is ``(1 2, 3)`` (``.``/``:`` attach directly). With two it is ``(1, 2)``:
    the template's other branch (``(1 2, )``) applies only when a page named ``1/2`` exists, which no pinned
    citation names.
    """

    args.check("1", "2", "3", "הק", "ק", "עיין שם", "קטגוריה")
    ctx.features["citations"] += 1
    book, chapter = _v(args, ctx, "1"), _v(args, ctx, "2")
    verse = _v(args, ctx, "3").strip() if args.filled("3") else None
    see = _v(args, ctx, "עיין שם") if args.filled("עיין שם") else None
    return _citation_label(book, chapter, verse, see, two_part=verse is None)


def _source(args: Args, ctx: _Context) -> str:
    """``{{מקור}}``: ``(label)`` small, the label being ``מקור=``, else parameter 2, else parameter 1."""

    args.check("1", "2", "מקור")
    ctx.features["citations"] += 1
    if args.filled("מקור"):
        label = _v(args, ctx, "מקור")
    else:
        label = _v(args, ctx, "2") if "2" in args.values else ctx.expand(args.need("1"))
    return f"<small>({label})</small>"


def _tsitut(args: Args, ctx: _Context) -> str:
    """``{{צ}}``: the quoted content (``תוכן`` or 1) between quotation marks."""

    args.check("1", "תוכן", "סוג", "גודל", "מרכאות")
    content = _v(args, ctx, "תוכן") if "תוכן" in args.values else ctx.expand(args.need("1"))
    return _quoted(content, args, ctx)


def _tsitutun(args: Args, ctx: _Context) -> str:
    """``{{ציטוטון}}``: ``"1"`` then ``(2)`` small when 2 is given."""

    args.check("1", "2", "מרכאות")
    text = _quoted(ctx.expand(args.need("1")), args, ctx)
    if args.filled("2"):
        text += f"<small> ({_v(args, ctx, '2')})</small>"
    return text


def _mets(args: Args, ctx: _Context) -> str:
    """``{{מצ}}``: a verse citation then the quoted verse: ``(1 2, 3): "4"``, or ``(1, 2): "3"``."""

    args.check("1", "2", "3", "4", "ק", "קטגוריה")
    ctx.features["citations"] += 1
    book, chapter = _v(args, ctx, "1"), _v(args, ctx, "2")
    if args.filled("4"):
        label = _citation_label(book, chapter, _v(args, ctx, "3").strip(), None, two_part=False)
        quote = _v(args, ctx, "4")
    else:
        label = _citation_label(book, chapter, None, None, two_part=True)
        quote = _v(args, ctx, "3")
    return f"{label}: {_quoted(quote, Args('צ', []), ctx)}"


def _shem(args: Args, ctx: _Context) -> str:
    """``{{שם}}`` ("ibid."): ``(שם 2, 3) "4"``, or with ``שם=``: ``(שם) "1"``."""

    args.check("1", "2", "3", "4", "שם", "ק", "קטגוריה")
    ctx.features["citations"] += 1
    if args.filled("שם"):
        text = "<small>(שם)</small>"
        if args.filled("2"):
            text += " " + _quoted(_v(args, ctx, "1"), Args("צ", []), ctx)
        return text
    second = f" {_v(args, ctx, '2')}" if args.filled("2") else ""
    text = f"<small>(שם{second}, {ctx.expand(args.need('3'))})</small> "
    if args.filled("4"):
        text += _quoted(_v(args, ctx, "4"), Args("צ", []), ctx)
    return text


def _tsitut_mefaresh(args: Args, ctx: _Context) -> str:
    """``{{צפ}}``: ``(source):`` small when a source is given, then the quoted text."""

    args.check("1", "2", "תוכן", "מקור")
    source = _v(args, ctx, "מקור") if "מקור" in args.values else _v(args, ctx, "2")
    prefix = f"<small>([[{source}]]):</small> " if source.strip() else ""
    content = _v(args, ctx, "תוכן") if "תוכן" in args.values else ctx.expand(args.need("1"))
    return prefix + _quoted(content, Args("צ", []), ctx)


def _tsitut_ad(args: Args, ctx: _Context) -> str:
    """``{{צא}}``: the quoted text then ``(2)`` small."""

    args.check("1", "2")
    ctx.features["citations"] += 1
    return f"{_quoted(ctx.expand(args.need('1')), Args('צ', []), ctx)} <small>([[{ctx.expand(args.need('2'))}]])</small>"


def _tsitut_mal(args: Args, ctx: _Context) -> str:
    """``{{צמל}}``: the text, then ``(2)`` small when given."""

    args.check("1", "2", "סוג", "גודל")
    text = ctx.expand(args.need("1"))
    if args.filled("2"):
        ctx.features["citations"] += 1
        text += f"<small> ([[{_v(args, ctx, '2')}]])</small>"
    return text


def _mm_zohar(args: Args, ctx: _Context) -> str:
    args.check("1", "2", "3")
    ctx.features["citations"] += 1
    return f'<small>(ח"{ctx.expand(args.need("1"))} {ctx.expand(args.need("2"))}, {ctx.expand(args.need("3"))})</small>'


def _mm_mishna(args: Args, ctx: _Context) -> str:
    """``{{ממ משנה}}``: ``(משנה, 1 2, 3)``; ``מסכת=ללא`` drops ``משנה, 1``; ``ביאור`` names the annotated edition."""

    args.check("1", "2", "3", "ביאור", "מסכת")
    ctx.features["citations"] += 1
    tractate, chapter = ctx.expand(args.need("1")), ctx.expand(args.need("2"))
    mishna = f", {_v(args, ctx, '3')}" if args.filled("3") else ""
    if args.filled("ביאור"):
        label = f"משנה מבוארת, {tractate} {chapter}{mishna}"
    else:
        label = (chapter if (args.raw("מסכת") or "").strip() == "ללא" else f"משנה, {tractate} {chapter}") + mishna
    return f"<small>({label})</small>"


def _verse_number(args: Args, ctx: _Context) -> str:
    """``{{מ:פסוק}}``: the verse marker as shown: ``סדר`` and ``עלייה``, the chapter (``פרק``, or 2 at verse א), the verse."""

    args.check("1", "2", "3", "סדר", "עלייה", "פרק")
    chapter = ""
    if args.filled("פרק"):
        chapter = f"{_v(args, ctx, 'פרק')} "
    elif (args.need("3") or "").strip() == "א":
        chapter = f"{ctx.expand(args.need('2'))} "
    return f"{_v(args, ctx, 'סדר')} {_v(args, ctx, 'עלייה')}{chapter}{ctx.expand(args.need('3'))} "


def _title_page(args: Args, ctx: _Context) -> str:
    """``{{דף שער}}`` (``{{כו}}``): the book label, title (1), subtitle (2) and imprint (``מקור``), one block each."""

    args.check("1", "2", "ספר", "מקור", "דפוס", "תמונה", "גודל", "רוחב", "כיתוב")
    book = (args.raw("ספר") or "").strip()
    parts = ["ספר" if book == "1" else _v(args, ctx, "ספר"), ctx.expand(args.need("1"))]
    if args.filled("2"):
        parts.append(_v(args, ctx, "2"))
    if args.filled("מקור"):
        ctx.sizes["small"] += 1
        parts.append(_v(args, ctx, "מקור"))
    return "".join(_block(part) for part in parts)


def _running_head(args: Args, ctx: _Context) -> str:
    """``{{כותרת רצה}}``: right and left parts on one line, then the centre (MediaWiki's source order)."""

    args.check("1", "2", "3", "ימין", "מרכז", "שמאל")
    right = _v(args, ctx, "1") if "1" in args.values else _v(args, ctx, "ימין")
    centre = _v(args, ctx, "2") if "2" in args.values else _v(args, ctx, "מרכז")
    left = _v(args, ctx, "3") if "3" in args.values else _v(args, ctx, "שמאל")
    return _block(f"{right} {left}") + _block(centre)


def _font_size(args: Args, ctx: _Context) -> str:
    args.check("1", "2")
    size = (args.need("1") or "").strip()
    if size.isdigit() and int(size) != 3:
        ctx.sizes["small" if int(size) < 3 else "large"] += 1
    return ctx.expand(args.need("2"))


def _columns(args: Args, ctx: _Context) -> str:
    """``{{עמודות}}``: a multi-column ``div`` of parameter 2 (parameter 1 is the column count)."""

    args.check("1", "2", "class", "style")
    ctx.features["columns"] += 1
    return _block(ctx.expand(args.need("2")))


def _tooltip_word(args: Args, ctx: _Context) -> str:
    """``{{ב}}``: the word (1) is shown; its explanation (2, 3) is a hover tooltip, not page text."""

    args.check("1", "2", "3", "ללא קו")
    return ctx.expand(args.need("1"))


def _glossary(args: Args, ctx: _Context) -> str:
    """``{{מונחון}}``: with three parameters the shown word is 2 (a link titled 3); otherwise 1 (titled 2)."""

    args.check("1", "2", "3")
    return ctx.expand(args.need("2")) if args.filled("3") else ctx.expand(args.need("1"))


def _link_label(prefix: str) -> Renderer:
    def render(args: Args, ctx: _Context) -> str:
        args.check("1", "2")
        target = ctx.expand(args.need("1"))
        return _v(args, ctx, "2") if "2" in args.values else target

    return render


def _note_template(args: Args, ctx: _Context) -> str:
    """``{{הערה}}`` (Module:הערה): a ``<ref>`` with parameter 1 as its text and ``שם``/``name`` as its name."""

    args.check("1", "שם", "name", "כיוון", "קבוצה", "group")
    if args.filled("קבוצה") or args.filled("group"):
        raise UnsupportedWikitextError("footnote", "note group")
    name = (args.raw("שם") or args.raw("name") or "").strip() or None
    return ctx.note(args.raw("1"), name)


def _ref_placeholder(args: Args, ctx: _Context) -> str:
    name, body, _ = ctx.ref_bodies[int(args.need("1"))]
    return ctx.note(body, name)


def _references(args: Args, ctx: _Context) -> str:
    args.check("יישור", "טורים", "group", "קבוצה", "הערות")
    if args.filled("הערות") or args.filled("group") or args.filled("קבוצה"):
        raise UnsupportedWikitextError("footnote", "note group or list-defined notes")
    return _REFERENCES


def _footnote_mark(args: Args, ctx: _Context) -> str:
    """``{{שוליים}}``: a hand-numbered footnote mark; the editor typed the printed mark (1), shown as is."""

    args.check("1", "2")
    return f"<sup>{ctx.expand(args.need('1'))}</sup>"


def _footnote_start(word: str) -> Renderer:
    """``{{שוליים למטה}}`` (``הערה 1:``) and ``{{שוליים למטה עם מספור חופשי}}`` (``1``): a hand-numbered note's start."""

    def render(args: Args, ctx: _Context) -> str:
        args.check("1", "2")
        mark = ctx.expand(args.need("1"))
        return f"<cite>{word}{mark}: </cite>" if word else f"<cite>{mark} </cite>"

    return render


def _poem(args: Args, ctx: _Context) -> str:
    args.check("1")
    return _poem_text(ctx.expand(args.need("1")))


def _mishnah_list_item(args: Args, ctx: _Context) -> str:
    args.check("1")
    return _block(ctx.expand(args.need("1")))


def _yerushalayim(points: str) -> Renderer:
    """``{{מ:ירושלם}}`` / ``{{מ:ירושלמה}}``: 1 and 2, then a combining grapheme joiner and the vowel the spelling lacks."""

    def render(args: Args, ctx: _Context) -> str:
        args.check("1", "2")
        return f"{ctx.expand(args.need('1'))}{_v(args, ctx, '2')}͏{points}"

    return render


def _hard_space(args: Args, ctx: _Context) -> str:
    args.check("1")
    return " "


def _version(args: Args, ctx: _Context) -> str:
    """``{{נוסח}}``: outside a ``הערות נוסח`` page it shows parameter 1; the variant readings are not shown."""

    return ctx.expand(args.need("1"))


def _kamats(args: Args, ctx: _Context) -> str:
    """``{{מ:קמץ}}``: ``ד``, ``אחר`` and 1 concatenated; ``ס`` (another reading) is not shown."""

    args.check("1", "ד", "אחר", "ס")
    return _v(args, ctx, "ד") + _v(args, ctx, "אחר") + _v(args, ctx, "1")


def _legarmeih(spaced: bool) -> Renderer:
    def render(args: Args, ctx: _Context) -> str:
        args.check("רווח") if spaced else args.check()
        tail = "" if not spaced or (args.raw("רווח") or "").strip() == "לא" else " "
        return f" ׀{tail}"

    return render


@cache
def _book_names() -> dict[str, str]:
    payload = json.loads((Path(__file__).resolve().parents[1] / "data" / "wikisource" / "book_names.json").read_text(encoding="utf-8"))
    return payload["names"]


def book_name(name: str, *, geresh: bool = False) -> str:
    """``{{מ"מ/ספר}}``: the full book name for an abbreviation (a ``#בחר`` switch, trimmed); otherwise the name."""

    value = _book_names().get(name.strip(), name.strip())
    return value.replace("{geresh}", "'" if geresh else "")


def gershayim(value: str) -> str:
    """Module:גרשיים: an apostrophe after a one-letter last word, else ``"`` before the last letter."""

    value = value.strip()
    words = value.split()
    if not words:
        return value
    if len(words[-1]) == 1:
        return value + "'"
    return value[:-1] + '"' + value[-1]


def _verse_reference(args: Args, ctx: _Context) -> str:
    """``{{הפניה לפסוקים}}``: ``(book chapter, verse-verse, suffix)`` small, numerals with gershayim.

    The template's first part is a Lua call that shows nothing on the page.
    """

    args.check("1", "2", "3", "4", "תחילית", "סיומת", "ט", "קט")
    ctx.features["citations"] += 1
    label = (f"{_v(args, ctx, 'תחילית')}\u00a0" if args.filled("תחילית") else "")
    label += f"{book_name(ctx.expand(args.need('1')), geresh=True)} {gershayim(ctx.expand(args.need('2')))}"
    if args.filled("3"):
        label += f", {gershayim(_v(args, ctx, '3'))}"
    if args.filled("4"):
        label += f"-{gershayim(_v(args, ctx, '4'))}"
    suffix_key = "סיומת" if "סיומת" in args.values else "ט"
    label += f", {_v(args, ctx, suffix_key)})" if args.filled(suffix_key) else ")"
    return f"<small>({label}</small>"


def _verse_quote(args: Args, ctx: _Context) -> str:
    """``{{פסוק}}``: the quoted verse (1) then its citation ``(2 3, 4)``; ``פסוק=`` adds a second quotation."""

    args.check("1", "2", "3", "4", "פסוק", "מרכאות", "בציטוט", "ק", "קטגוריה")
    if (args.raw("בציטוט") or "").strip() == "כן":
        raise UnsupportedWikitextError("template argument", "פסוק|בציטוט")
    text = _quoted(_v(args, ctx, "1"), args, ctx) if args.filled("1") else ""
    if args.filled("2"):
        ctx.features["citations"] += 1
        verse = _v(args, ctx, "4").strip() if args.filled("4") else None
        text += "\u00a0" + _citation_label(_v(args, ctx, "2"), _v(args, ctx, "3"), verse, None, two_part=verse is None)
    if args.filled("פסוק"):
        text += ":\u00a0" + _quoted(_v(args, ctx, "פסוק"), args, ctx)
    return text


def _gemara_reference(args: Args, ctx: _Context) -> str:
    """``{{הפניה-גמ1}}``: ``(tractate folio.)`` small (``.`` for side א, ``:`` for ב); the Lua part shows nothing."""

    args.check("1", "2", "3")
    ctx.features["citations"] += 1
    side = {"א": ".", "ב": ":"}.get(_v(args, ctx, "3").strip(), "")
    ctx.sizes["small"] += 1
    return f"({ctx.expand(args.need('1'))} {ctx.expand(args.need('2'))}{side})"


def _sdl_lemma(args: Args, ctx: _Context) -> str:
    """``{{שדל:דה}}`` (Luzzatto's lemma): ``(verse)`` when a chapter is given, then the lemma.

    The lemma is 4 when 3 is given, else 1; parameter 2 (often the lemma's trailing punctuation) is shown only as the
    chapter when ``פרק`` is absent and 3 is given, as in the template's source.
    """

    args.check("1", "2", "3", "4", "ספר", "פרק", "פסוק")  # a 5th parameter (trailing punctuation) is not shown
    chapter = _v(args, ctx, "3") if "3" in args.values else _v(args, ctx, "פרק")
    out = " "
    if chapter.strip():
        verse = _v(args, ctx, "פסוק") if "פסוק" in args.values else ctx.expand(args.need("3"))
        out += f"({verse}) "
    lemma = args.need("4") if args.filled("3") else args.need("1")
    return out + " " + ctx.expand(lemma)


def _bmets(args: Args, ctx: _Context) -> str:
    """``{{במצ}}``: ``(1 פרק, 2-3)`` small, then the quoted verse (4, else 3)."""

    args.check("1", "2", "3", "4", "פרק", "ק")
    ctx.features["citations"] += 1
    # The source tests {{{פרק}}} without a default: when פרק is absent the literal is non-empty, so a space shows.
    chapter = f"\u00a0{_v(args, ctx, 'פרק')}" if args.filled("פרק") or "פרק" not in args.values else ""
    span = f"-{ctx.expand(args.need('3'))}" if args.filled("4") else ""
    label = f"<small>({ctx.expand(args.need('1'))}{chapter}, {ctx.expand(args.need('2'))}{span})</small>"
    quote = _v(args, ctx, "4") if args.filled("4") else ctx.expand(args.need("3"))
    return f"{label}: {_quoted(quote, Args('צ', []), ctx)}"


def _block_quote(args: Args, ctx: _Context) -> str:
    """``{{ציטוט}}``: a table whose cells are the quotation (``תוכן``) and, when given, ``– מקור``."""

    args.check("תוכן", "מקור", "מרכאות", "אנגלית", "רווח-אופקי")
    parts = [_block(ctx.expand(args.need("תוכן")))]
    parts.append(_block(f"– {_v(args, ctx, 'מקור')}" if args.filled("מקור") else ""))
    return "".join(parts)


# Closed table of he.wikisource templates and their renderings, written from each template's source
# (revision ids in docs/wikisource_proofread_source.md) and checked against action=parse. Anything else is rejected.
TEMPLATE_RENDERERS: dict[str, Renderer] = {
    # v1 (F8b)
    "!": _literal("|"),
    "ש": _literal("<br />"),
    "ק": _params("1", "קטן", size="small"),  # a redirect to {{קטן}}
    "ג": _keep_first(size="large"),
    "קטן": _params("1", "קטן", size="small"),
    "גדול": _params("1", required=True, size="large"),
    "מרכז": _keep_first(block=True),
    "עם-ניקוד": lambda args, ctx: _block(
        _v(args.check("1", "טקסט", "גופן", "גודל"), ctx, "טקסט") if "טקסט" in args.values else ctx.expand(args.need("1"))
    ),
    "קיצור": _keep_first(),
    # {{סוף}} closes a <div> and {{טקסט מנוקד}} opens one: both end the paragraph.
    "סוף": lambda args, ctx: (args.check(), "\n\n")[1],
    "טקסט מנוקד": lambda args, ctx: (args.check("גודל"), "\n\n")[1],
    # F8b3: wrappers that only style their text
    "גדול-מודגש": _params("1", required=True, size="large"),
    "גג": _params("1", required=True, size="large"),
    "קק": _params("1", required=True, size="small"),
    "הוראה למתפללים": _params("1", required=True, size="small"),
    "מרווחות": lambda args, ctx: ctx.expand(args.check("1", "רוחב").need("1")),
    "גודל גופן": _font_size,
    "ה": lambda args, ctx: ctx.expand(args.check("1", "תוכן", "סוג").raw("תוכן") or "" if "תוכן" in args.values else args.need("1")),
    "צבע גופן": lambda args, ctx: ctx.expand(args.check("1", "2").need("2")),
    "ירח בן יומו-2": _params("1", required=True),
    "מ:קמץ": _kamats,
    "נוסח": _version,
    "שמאל": _params("1", required=True, block=True),
    "מר": lambda args, ctx: _block(_v(args.check("1"), ctx, "1")) if args.filled("1") else "",
    "ג/": _drop(),
    "עמודות": _columns,
    "עמודות-התחלה": lambda args, ctx: (args.check("1"), "\n\n")[1],
    "מיספור עברי": _drop(),
    "מיספור עברי-סוף": _drop(),
    "מ": _mishnah_list_item,
    "רן": _poem,
    "מ:טעמי המקרא": lambda args, ctx: (args.check("1"), "\n\n")[1],
    "מ:טעמי המקרא-סוף": lambda args, ctx: (args.check(), "\n\n")[1],  # closes the verse <div>: ends the paragraph
    # spacing
    "רווח קשיח": _hard_space,
    "רווח קשיח2": _hard_space,
    "רווח": _hard_space,
    "ררר": lambda args, ctx: (args.check(), " ")[1],
    "ססס": lambda args, ctx: (args.check(), " ")[1],
    "סס": lambda args, ctx: (args.check(), "<br /> ")[1],
    "פפ": lambda args, ctx: (args.check(), "<br /> <br />")[1],
    "ש-רווח": lambda args, ctx: (args.check("1"), " ")[1],
    "עוגן בשורה": _drop("1"),
    # F8b6: {{שיר מנוקד|...}} is {{עם-ניקוד|<poem>...</poem>|גודל=120}}: a poem block, one rendered line per source line.
    "שיר מנוקד": _poem,
    # F8b6: {{חיריק ללא אות}} writes ZWJ + hiriq (Module-free, as the template's source has it).
    "חיריק ללא אות": lambda args, ctx: (args.check(), "\u200d\u05b4")[1],
    # F8b6: {{רווח בין אותיות|text}} or {{רווח בין אותיות|spacing|text}}: letter-spaced type; the text, unspaced.
    "רווח בין אותיות": lambda args, ctx: _v(args.check("1", "2"), ctx, "2") if args.filled("2") else ctx.expand(args.check("1", "2").need("1")),
    # F8b5: {{כ}} writes a bidi mark (RLM, or LRM with ימינה=), which step 8 removes: nothing visible.
    "כ": lambda args, ctx: (args.check("ימינה"), "")[1],
    "סעיף": lambda args, ctx: f"({ctx.expand(args.check('1').need('1'))})",
    # cantillation marks drawn by templates
    "מ:לגרמיה": _legarmeih(True),
    "מ:לגרמיה-2": _legarmeih(False),
    "מ:פסק": lambda args, ctx: (args.check(), " ׀ ")[1],
    "מ:ירושלם": _yerushalayim("ִ"),
    "מ:ירושלמה": _yerushalayim("ְ"),
    "מ:פסוק": _verse_number,
    "HIRIK WITHOUT LETTER": lambda args, ctx: (args.check(), "\u034f\u05b4")[1],
    "עם-טעמים": lambda args, ctx: ctx.expand(args.check("1", "גודל").need("1")),
    "גמט": lambda args, ctx: _v(args.check("1", "קטנה"), ctx, "1"),
    # The Page view is in the עמוד namespace, so the template shows parameter 1 (2 is for transclusion).
    "רק במרחב עמוד": lambda args, ctx: _v(args.check("1", "2"), ctx, "1"),
    "שדל:דה": _sdl_lemma,
    "הפניה לפסוקים": _verse_reference,
    "פסוק": _verse_quote,
    "הפניה-גמ1": _gemara_reference,
    "ציטוט": _block_quote,
    "במצ": _bmets,
    'אח"כ': lambda args, ctx: (args.check(), 'אח"כ')[1],
    # tooltips and links: the visible word only
    "ב": _tooltip_word,
    "מונחון": _glossary,
    "דף ויקיפדיה": _link_label("w"),
    "וק": _link_label("w"),
    "מח": _link_label("מחבר"),
    # quotations and editors' citations, as MediaWiki shows them
    "צ": _tsitut,
    "ציטוטון": _tsitutun,
    "צפ": _tsitut_mefaresh,
    "צא": _tsitut_ad,
    "צמל": _tsitut_mal,
    'מ"מ': _mm,
    "ממ": _mm,
    "ממ זהר": _mm_zohar,
    "ממ משנה": _mm_mishna,
    "מקור": _source,
    "מצ": _mets,
    "שם": _shem,
    # title pages and running heads in the body
    "דף שער": _title_page,
    "כו": _title_page,
    "כותרת רצה": _running_head,
    "rh": _running_head,
    # footnotes
    "הערה": _note_template,
    # Module:פרמטרים "biur": a {{הערה}} in the "hebrew" group, an editor's explanation, not printed: dropped.
    "ביאור": lambda args, ctx: (args.check("1", "שם", "name"), ctx.features.update({"editor_notes_dropped": 1}), "")[2],
    "הערות שוליים": _references,
    "שוליים": _footnote_mark,
    "שוליים למטה": _footnote_start("הערה "),
    "שולייםלמטה": _footnote_start("הערה "),
    "שוליים למטה עם מספור חופשי": _footnote_start(""),
    # {{ד"מ}}: a hand-numbered note's start, "1 " in bold, then "[2]" small grey when 2 is given.
    'ד"מ': lambda args, ctx: f"<cite>{ctx.expand(args.check('1', '2').need('1'))} </cite> "
    + (f"<small>[{_v(args, ctx, '2')}]</small>" if args.filled("2") else ""),
    # F8b4: Bible text reached through labelled-section transclusion (Mikra al pi ha-Masora)
    "מ:דחי": lambda args, ctx: ctx.expand(args.check("1", "2").need("1")),  # shows 1; 2 is the other accent reading
    "מ:אות-ג": lambda args, ctx: (ctx.sizes.update({"large": 1}), ctx.expand(args.check("1").need("1")))[1],
    "ר0": lambda args, ctx: "" if (args.check("רווח").raw("רווח") or "").strip() == "לא" else " ",
    "ר1": lambda args, ctx: (args.check(), "<br />")[1],  # a line break, then an indent (display only)
    "ר2": lambda args, ctx: (args.check(), "<br />")[1],
    'כו"ק': lambda args, ctx: f"{ctx.expand(args.check('1', '2').need('1'))} {ctx.expand(args.need('2'))}",  # ketiv (grey), qere
    'קו"כ': lambda args, ctx: f"{ctx.expand(args.check('1', '2').need('2'))} {ctx.expand(args.need('1'))}",  # qere, ketiv (grey)
    "מ:מקף אפור": lambda args, ctx: (args.check(), "־")[1],
    _REF_TEMPLATE: _ref_placeholder,
    "\ue006dropped": lambda args, ctx: (ctx.features.update({"malformed_markup": 1}), "")[1],
}


# Template names an editor mistyped on a pinned page, and the template meant. MediaWiki shows a red link instead.
TYPO_ALIASES = {
    "קטם": "קטן",  # one Hyman page: "{{קטם|(...)}}" in a run of {{קטן}} citations
    ":פסוק": "מ:פסוק",  # one Biblia Hebraica page: every other verse marker is {{מ:פסוק}}
    "שם מד": "\ue006dropped",  # one Tosefta page: a broken {{שם}} verse citation the edition does not print
}


def normalize_template_name(name: str) -> str:
    """MediaWiki title normalisation for a template name: no bidi marks, single spaces, no ``תבנית:`` prefix."""

    name = "".join(char for char in name if char not in BIDI_CONTROL_CHARACTERS)
    name = re.sub(r"[\s_]+", " ", name).strip()
    for prefix in ("תבנית:", "Template:", "template:"):
        if name.startswith(prefix):
            name = name[len(prefix) :].strip()
    return name


# --- Conversion ------------------------------------------------------------------------------------------------


def wikitext_to_plain_text(wikitext: str, transclusions: Mapping[str, str] | None = None) -> str:
    return convert_wikitext(wikitext, transclusions).text


_NOTE_LINE = re.compile(r"^\[(\d+)\] ", re.MULTILINE)


def footnote_spans(text: str) -> list[tuple[int, int, int]]:
    """Where each footnote stands in converted text (F8b7): ``(number, start, end)`` character offsets.

    The converter writes the notes as lines ``[n] text``, numbered 1, 2, ... in order, where the list stands (at the
    foot of the body when the page has no list). The last run of such lines numbered from 1 is the notes block; a
    note runs from its own line to the next note's line, the last one to the end of the text (or of the block, when
    body text follows the list). Text without notes gives an empty list.
    """

    starts = [(int(match.group(1)), match.start()) for match in _NOTE_LINE.finditer(text)]
    block: list[tuple[int, int]] = []
    for number, start in starts:
        if number == 1:
            block = [(number, start)]
        elif block and number == block[-1][0] + 1:
            block.append((number, start))
    if not block:
        return []
    ends = [start for _, start in block[1:]]
    tail = text.find("\n\n", block[-1][1])
    ends.append(len(text) if tail < 0 else tail)
    return [(number, start, end) for (number, start), end in zip(block, ends)]


# --- Labelled-section transclusion (F8b4) ----------------------------------------------------------------------

_SECTION_CALL = re.compile(r"\{\{\s*#(?:קטע|section|lst)\s*:([^{}|]*)\|([^{}|]*)\}\}", re.IGNORECASE)
_SECTION_OPENER = re.compile(r"\{\{\s*#(?:קטע|section|lst|lsth|lstx|קטע-בלי)\s*:", re.IGNORECASE)


def normalize_page_title(title: str) -> str:
    """MediaWiki title normalisation for a transcluded page: no bidi marks, single spaces for spaces and underscores."""

    title = "".join(char for char in title if char not in BIDI_CONTROL_CHARACTERS)
    return re.sub(r"[\s_]+", " ", title).strip()


def transcluded_titles(wikitext: str, *, body: bool = True) -> list[str]:
    """Titles transcluded by labelled section, in order of first use: in a Page's body, or (``body=False``) anywhere
    in a transcluded page's text. Not followed into the targets."""

    text = page_body(wikitext) if body else wikitext
    return list(dict.fromkeys(normalize_page_title(match.group(1)) for match in _SECTION_CALL.finditer(text)))


def section_text(target_wikitext: str, section: str) -> str:
    """The text of every section ``section`` of a page, as Labelled Section Transclusion takes it.

    A section runs from ``<section begin=name/>`` (``<קטע התחלה=name/>``) to the matching end tag; several sections
    of one name are joined. The target is transcluded, so its ``<noinclude>`` parts are left out and its
    ``<includeonly>`` parts kept. A section that is not on the page is rejected (MediaWiki would show nothing).
    """

    text = target_wikitext.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"<noinclude>.*?</noinclude>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?includeonly\s*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    name = section.strip()
    # Labelled Section Transclusion matches the section name literally, quoted or not, spaces included.
    begin = re.compile(rf"<(?:section\s+begin|קטע\s+התחלה)\s*=\s*([\"']?){re.escape(name)}\1\s*/?>", re.IGNORECASE)
    end = re.compile(rf"<(?:section\s+end|קטע\s+סוף)\s*=\s*([\"']?){re.escape(name)}\1\s*/?>", re.IGNORECASE)
    parts: list[str] = []
    position = 0
    while (opening := begin.search(text, position)) is not None:
        closing = end.search(text, opening.end())
        stop = closing.start() if closing else len(text)
        parts.append(text[opening.end() : stop])
        position = closing.end() if closing else len(text)
    if not parts:
        raise UnsupportedWikitextError("transclusion", f"section {name!r} not on the transcluded page")
    return "".join(parts)


def transclude_sections(text: str, transclusions: Mapping[str, str], depth: int = 0) -> str:
    """Replace each ``{{#קטע:title|section}}`` with that section of the pinned page, following nested calls."""

    if depth > 5:
        raise UnsupportedWikitextError("transclusion", "nested too deeply")
    pinned = {normalize_page_title(title): wikitext for title, wikitext in transclusions.items()}

    def replace(match: re.Match[str]) -> str:
        title = normalize_page_title(match.group(1))
        if title not in pinned:
            raise UnsupportedWikitextError("transclusion", f"page not pinned: {title}")
        return transclude_sections(section_text(pinned[title], match.group(2)), transclusions, depth + 1)

    text = _SECTION_CALL.sub(replace, text)
    if _SECTION_OPENER.search(text):
        raise UnsupportedWikitextError("transclusion", "labelled-section call with unsupported arguments")
    return text


def page_body(wikitext: str) -> str:
    """The ProofreadPage body as the Page view shows it: header and footer removed, in-body noinclude kept.

    ProofreadPage stores a page as ``<noinclude>header</noinclude>body<noinclude>footer</noinclude>``. An editor's
    own ``<noinclude>`` inside the body is shown on the Page view (its tags are dropped) and ``<includeonly>`` is not.
    """

    text = wikitext.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^\s*<noinclude>.*?</noinclude>", "", text, count=1, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<noinclude>(?:(?!<noinclude>).)*?</noinclude>\s*$", "", text, count=1, flags=re.DOTALL | re.IGNORECASE)
    return text


def convert_wikitext(
    wikitext: str, transclusions: Mapping[str, str] | None = None, *, unprinted_notes: Collection[int] = ()
) -> WikitextConversion:
    """Convert a page's pinned wikitext. ``transclusions`` maps each page title the body transcludes by labelled
    section (``{{#קטע:title|section}}``, F8b4) to that page's pinned wikitext; a title not given is rejected.

    ``unprinted_notes`` (F8b7) lists footnotes, by the number the faithful conversion gives them, that a reviewed
    check found to have no printed counterpart (an unsigned editor's note). They are dropped with their marks, as
    signed editors' notes are, and the other notes are renumbered; a number that is not a footnote of the page
    raises ``ValueError``. Without it the conversion is the faithful MediaWiki rendering.
    """

    ctx = _Context(frozenset(int(number) for number in unprinted_notes))
    text = page_body(wikitext)
    text = re.sub(r"<includeonly>.*?</includeonly>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"</?noinclude\s*>", "", text, flags=re.IGNORECASE)
    if re.search(r"</?(?:noinclude|includeonly)\b", text, flags=re.IGNORECASE):
        raise UnsupportedWikitextError("tag", "unbalanced noinclude or includeonly")
    text = transclude_sections(text, transclusions or {})

    def keep_literal(match: re.Match[str]) -> str:
        ctx.nowiki.append(match.group(1) or "")
        return _NOWIKI.format(len(ctx.nowiki) - 1)

    text = re.sub(r"<nowiki\s*/>|<nowiki>(.*?)</nowiki>", keep_literal, text, flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"</?nowiki\b", text, flags=re.IGNORECASE):
        raise UnsupportedWikitextError("tag", "unbalanced nowiki")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    for tag in PAGE_ONLY_TAGS:
        text = re.sub(rf"<{tag}\b[^>]*/?>", "", text, flags=re.IGNORECASE)
    for tag in UNSUPPORTED_TAGS:
        if re.search(rf"<{tag}\b", text, flags=re.IGNORECASE):
            raise UnsupportedWikitextError("tag", tag)
    if "__" in text and re.search(r"__[A-Zא-ת]+__", text):
        raise UnsupportedWikitextError("markup", "behaviour switch")
    text = _extract_ref_tags(text, ctx)
    text = re.sub(r"<references\s*/>|<references\s*>\s*</references>", _REFERENCES, text, flags=re.IGNORECASE)
    text, headings = _NOTE_LIST_HEADING.subn("", text)
    if headings:
        ctx.features["editor_headings_dropped"] += headings
    text = ctx.expand(text)
    body = _render_blocks(text, ctx)
    if ctx.notes or ctx.follow:
        body = _place_notes(body, ctx)
    elif ctx.unprinted_notes:
        raise ValueError(f"unprinted note {min(ctx.unprinted_notes)} is not a footnote of the page (no notes)")
    body = body.replace(_REFERENCES, "")
    return WikitextConversion(
        body,
        {kind: count for kind, count in sorted(ctx.sizes.items()) if count},
        {kind: count for kind, count in sorted(ctx.features.items()) if count},
    )


def _render_blocks(text: str, ctx: _Context) -> str:
    """Everything after template expansion: tables, block HTML, poems, links, quotes, paragraphs, tags, spaces."""

    ctx.sizes["small"] += len(re.findall(r"<small\b", text, flags=re.IGNORECASE))
    ctx.sizes["large"] += len(re.findall(r"<big\b", text, flags=re.IGNORECASE))
    text = re.sub(r"<poem\b[^>]*>(.*?)</poem>", lambda m: _poem_text(m.group(1)), text, flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"</?poem\b", text, flags=re.IGNORECASE):
        raise UnsupportedWikitextError("tag", "unbalanced poem")
    text = _render_tables(text, ctx)
    text = re.sub(rf"</?(?:{'|'.join(BLOCK_HTML_TAGS)})\b[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    malformed = [0]
    text = _replace_links(text, malformed)
    if malformed[0]:
        ctx.features["malformed_markup"] += malformed[0]
    text = re.sub(r"'{2,}", _quote_run, text)
    text = _join_paragraph_lines(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[A-Za-z][A-Za-z0-9]*\b[^>]*>", "", text)
    text = _NOWIKI_PATTERN.sub(lambda m: ctx.nowiki[int(m.group(1))], text)
    text = html.unescape(text)
    text = "".join(" " if unicodedata.category(char) == "Zs" else char for char in text if char not in BIDI_CONTROL_CHARACTERS)
    text = unicodedata.normalize("NFC", text)
    return _normalize_whitespace(text)


def _quote_run(match: re.Match[str]) -> str:
    """Bold/italic quotes: 2, 3 and 5 are markup; 4 is an apostrophe then bold; more than 5 keep the excess."""

    run = len(match.group(0))
    return "'" if run == 4 else "'" * (run - 5) if run > 5 else ""


def _poem_text(text: str) -> str:
    """``<poem>``: each source line is a rendered line; blank lines separate stanzas."""

    lines = text.strip("\n").split("\n")
    return _block("\n".join("" if not line.strip() else f"{line}<br />" for line in lines))


def _extract_ref_tags(text: str, ctx: _Context) -> str:
    """Replace ``<ref>`` tags by an internal template call, so notes are numbered in document order."""

    def replace(match: re.Match[str]) -> str:
        attributes = match.group(1) or ""
        name = re.search(r"\bname\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s/>]+))", attributes)
        bad = re.search(r"\b(group|dir|extends)\s*=", attributes)
        if bad:
            raise UnsupportedWikitextError("footnote", "ref attribute " + bad.group(1))
        if re.search(r"\bfollow\s*=", attributes):
            # The continuation of a note begun on the previous page: printed unmarked at the foot of this page.
            ctx.follow.append(match.group(2) or "")
            return ""
        ctx.ref_bodies.append(((next((g for g in name.groups() if g), None) if name else None), match.group(2), True))
        return "{{" + _REF_TEMPLATE + f"|{len(ctx.ref_bodies) - 1}}}}}"

    text = re.sub(r"<ref\b([^>]*?)(?:/>|>(.*?)</ref\s*>)", replace, text, flags=re.DOTALL | re.IGNORECASE)
    if re.search(r"</?ref\b", text, flags=re.IGNORECASE):
        raise UnsupportedWikitextError("footnote", "unbalanced ref")
    return text


def _place_notes(body: str, ctx: _Context) -> str:
    """Number the notes in order of first mark, drop editors' notes, and write ``[n] text`` lines at the list."""

    order: list[int] = []
    for match in _NOTE_MARK_PATTERN.finditer(body):
        index = int(match.group(1))
        if index not in order:
            order.append(index)
    texts: dict[int, str] = {}
    for index in order:
        note_ctx = _Context()
        note_ctx.depth = 1
        note_ctx.nowiki = ctx.nowiki
        expanded = note_ctx.expand(ctx.notes[index])
        if note_ctx.notes or _REFERENCES in expanded:
            raise UnsupportedWikitextError("footnote", "nested note")
        rendered = _render_blocks(expanded, note_ctx)
        ctx.sizes.update(note_ctx.sizes)
        ctx.features.update(note_ctx.features)
        texts[index] = rendered
    kept = [index for index in order if not EDITOR_NOTE_SIGNATURE.search(texts[index])]
    dropped = len(order) - len(kept)
    if dropped:
        ctx.features["editor_notes_dropped"] += dropped
    if ctx.unprinted_notes:
        # F8b7: unsigned editors' notes a reviewed check found not printed, by their faithful number.
        unknown = sorted(ctx.unprinted_notes - set(range(1, len(kept) + 1)))
        if unknown:
            raise ValueError(f"unprinted note {unknown[0]} is not a footnote of the page ({len(kept)} notes)")
        kept = [index for number, index in enumerate(kept, start=1) if number not in ctx.unprinted_notes]
        ctx.features["unprinted_notes_dropped"] += len(ctx.unprinted_notes)
    if kept:
        ctx.features["footnotes"] += len(kept)
    numbers = {index: number for number, index in enumerate(kept, start=1)}
    follow = []
    for raw in ctx.follow:
        note_ctx = _Context()
        note_ctx.depth = 1
        note_ctx.nowiki = ctx.nowiki
        follow.append(_render_blocks(note_ctx.expand(raw), note_ctx))
        ctx.features["footnote_continuations"] += 1

    def mark(match: re.Match[str]) -> str:
        number = numbers.get(int(match.group(1)))
        return f"[{number}]" if number else ""

    body = _NOTE_MARK_PATTERN.sub(mark, body)
    body = re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", body))
    lines = "\n".join([*follow, *(f"[{numbers[index]}] {texts[index]}" for index in kept)])
    if not lines:
        return body
    if _REFERENCES in body:
        head, _, tail = body.partition(_REFERENCES)
        return _normalize_whitespace(f"{head}\n\n{lines}\n\n{tail.replace(_REFERENCES, '')}")
    return _normalize_whitespace(f"{body}\n\n{lines}")


def _render_tables(text: str, ctx: _Context) -> str:
    """Wikitext tables: every cell (and the caption) becomes its own block, in source order."""

    if not re.search(r"^\s*\{\|", text, flags=re.MULTILINE):
        return text
    out: list[str] = []
    depth = 0
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if line.startswith("{|"):
            depth += 1
            ctx.features["tables"] += 1
            out.append("\n\n")
            continue
        if depth and line.startswith("|}"):
            depth -= 1
            out.append("\n\n" + line[2:])
            continue
        if depth and line.startswith("|-"):
            out.append("\n\n")
            continue
        if depth and (line.startswith("|+") or line.startswith("|") or line.startswith("!")):
            body = line[2:] if line.startswith("|+") else line[1:]
            separator = "!!" if line.startswith("!") else "||"
            for cell in _split_cells(body, separator):
                out.append("\n\n" + _cell_content(cell) + "\n\n")
            continue
        out.append(raw_line + "\n")
    if depth:
        raise UnsupportedWikitextError("markup", "unclosed table")
    return "".join(out)


def _split_cells(body: str, separator: str) -> list[str]:
    cells: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    while index < len(body):
        if body.startswith("[[", index):
            depth += 1
        elif body.startswith("]]", index):
            depth -= 1
        if depth == 0 and (body.startswith(separator, index) or (separator == "!!" and body.startswith("||", index))):
            cells.append("".join(current))
            current = []
            index += 2
            continue
        current.append(body[index])
        index += 1
    cells.append("".join(current))
    return cells


def _cell_content(cell: str) -> str:
    """A cell ``attributes | content``: the attributes are dropped (a single ``|`` outside links)."""

    depth = 0
    for index, char in enumerate(cell):
        if cell.startswith("[[", index):
            depth += 1
        elif cell.startswith("]]", index):
            depth -= 1
        elif char == "|" and depth == 0 and not cell.startswith("||", index):
            if re.fullmatch(r"\s*(?:[\w-]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s|]+)\s*)*", cell[:index]):
                return cell[index + 1 :]
            return cell
    return cell


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
        # Bidi marks an editor left before a heading's "=" make MediaWiki show the "=" signs; the print shows a
        # heading, so the marks do not stop heading detection here.
        bare = "".join(char for char in line if char not in BIDI_CONTROL_CHARACTERS).strip()
        if bare != line and re.fullmatch(r"(={1,6})\s*(.*?)\s*\1", bare):
            line = bare
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


def _expand_templates(text: str, ctx: _Context) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        start = text.find("{{", index)
        if start < 0:
            output.append(text[index:])
            break
        output.append(text[index:start])
        if text.startswith("{{{", start) and "}}}" not in text[start:]:
            # A stray third brace an editor typed ("{{{קטן|...}}"): MediaWiki shows "{", the print does not.
            ctx.features["malformed_markup"] += 1
            index = start + 1
            continue
        try:
            end = _matching_braces(text, start)
        except UnsupportedWikitextError:
            index = _recover_unclosed_template(text, start, ctx, output)
            continue
        output.append(_render_template(text[start + 2 : end - 2], ctx))
        index = end
    rendered = "".join(output)
    if "{{" in rendered or "}}" in rendered:
        raise UnsupportedWikitextError("markup", "unbalanced template braces")
    return rendered


def _recover_unclosed_template(text: str, start: int, ctx: _Context, output: list[str]) -> int:
    """An editor's unclosed template call, which MediaWiki shows as literal text and the print does not show.

    ``{{name|a|b}`` (one closing brace) is rendered as the call it was meant to be; any other unclosed opener
    ``{{name|`` is dropped and the text after it kept. Both count as ``malformed_markup``. Returns where to go on.
    """

    ctx.features["malformed_markup"] += 1
    single = re.match(r"\{\{([^{}\n]*)\}(?!\})", text[start:])
    if single:
        output.append(_render_template(single.group(1), ctx))
        return start + single.end()
    opener = re.match(r"\{\{[^{}|\n]*\|?", text[start:])
    return start + (opener.end() if opener else 2)


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


def _render_template(body: str, ctx: _Context) -> str:
    parts = _split_arguments(body)
    raw_name = parts[0].strip()
    if raw_name.startswith("{"):
        raise UnsupportedWikitextError("markup", "unbalanced template braces")
    if normalize_template_name(raw_name) in TYPO_ALIASES:
        pass
    elif raw_name.startswith("#") or raw_name.startswith(":") or raw_name.casefold().startswith(("subst:", "safesubst:", "msgnw:")):
        raise UnsupportedWikitextError("template", raw_name)
    name = normalize_template_name(raw_name)
    name = TYPO_ALIASES.get(name, name)
    renderer = TEMPLATE_RENDERERS.get(name)
    if renderer is None:
        raise UnsupportedWikitextError("template", name)
    args = Args(name, parts[1:])
    rendered = renderer(args, ctx)
    if args.hidden:
        ctx.features["hidden_arguments"] += len(args.hidden)
    return rendered


def _replace_links(text: str, malformed: list[int] | None = None) -> str:
    malformed = malformed if malformed is not None else [0]

    def internal(match: re.Match[str]) -> str:
        target, _, label = match.group(1).partition("|")
        namespace = target.strip().lstrip(":").split(":", 1)[0].strip().casefold() if ":" in target else ""
        if namespace in DROPPED_LINK_NAMESPACES and not target.strip().startswith(":"):
            return ""
        if namespace in UNSUPPORTED_LINK_NAMESPACES:
            raise UnsupportedWikitextError("link", namespace)
        return label if label else target.strip().lstrip(":")

    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\[\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\]", internal, text)
    if "[[" in text or "]]" in text:
        # Broken link markup an editor left (a doubled or unclosed link): MediaWiki shows the brackets, the print
        # does not. The brackets are dropped and counted.
        malformed[0] += text.count("[[") + text.count("]]")
        text = text.replace("[[", "").replace("]]", "")
    text = re.sub(r"\[(?:https?:)?//[^\s\]]+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"\[(?:https?:)?//[^\s\]]+\]", "", text)
    return text
