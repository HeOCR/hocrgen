"""The glyph layer of a born-digital PDF page: every painted glyph, fill, stroke and image, in paint order (F8e2).

``extract_glyph_layer`` is operator-only: it needs ``pdfminer.six`` (the optional ``pdf`` extra), which reads the
page's content stream and the fonts' ToUnicode maps. Nothing else in hocrgen imports pdfminer. The result is a plain
JSON document, ``hocrgen.pdf_glyph_layer.v1``, committed or packaged next to each page; everything downstream
(``hocrgen.parsers.pdf_geometry``) is pure Python over that document, so CI never needs pdfminer.

Why glyphs rather than ``pdftotext``: poppler's text flow merges table cells, signature blocks and superscript
markers out of order, and it cannot tell that text was painted over. Reshumot booklets from 2017 on carry a hidden
copy of every text line (the tagged copy, offset to the left), covered by an opaque white rectangle and repainted as
an artifact; ``pdftotext`` and a naive char dump both emit both copies. The glyph layer keeps paint order, so the
converter can drop what a later opaque fill hides.

Coordinates are PDF points with the origin at the page's top-left corner and y growing downwards, rounded to 0.01.

Document keys:

- ``page``: ``width``, ``height``, ``rotation``.
- ``fonts``: one record per font, indexed by the glyph rows: ``name``, ``tounicode`` (the font's whole ToUnicode map,
  code to text) and ``outlines`` (for each code used on the page, the first 16 hex digits of the SHA-256 of its
  TrueType ``glyf`` outline, or null) and ``bounds`` (that outline's ink box, ``xMin, yMin, xMax, yMax`` in
  thousandths of an em from the glyph origin, or null). Subsets of one typeface share outlines, so an outline names
  a glyph's shape independently of the ToUnicode map.
- ``glyphs``: ``[paint, text, x0, top, x1, bottom, origin_x, baseline, size, font, flags, cid]``. ``text`` is the
  ToUnicode mapping (``(cid:N)`` when the font has none), ``size`` the glyph's em height in points, ``baseline``
  the y of the glyph origin (text rise included), ``cid`` the character code in the font. ``flags`` bits: ``1`` invisible text render mode (3 or 7),
  ``2`` not upright (rotated or mirrored), ``4`` inside an ``/Artifact`` marked-content sequence, ``8`` painted
  with a fill alpha below 1, ``16`` its centre outside the current clipping path's bounding box, ``32`` inside
  optional content that is off in the document's default configuration. Fills, strokes and images that are
  clipped away entirely or sit in off optional content are not recorded.
- ``fills``: ``[paint, x0, top, x1, bottom, colour, alpha]`` for filled paths; ``colour`` is ``"white"`` or
  ``"other"``.
- ``strokes``: ``[paint, x0, top, x1, bottom]`` for stroked paths (rules, table borders, underlines).
- ``images``: ``[paint, x0, top, x1, bottom]``.
- ``actual_text``: ``[first_paint, last_paint, text]`` for each ``/ActualText`` span that covers glyphs. The
  converter uses a one-glyph span to name that glyph's character (InDesign wraps glyphs whose ToUnicode entry is
  wrong, for example a full stop mapped to a space); longer spans are recorded only.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any

GLYPH_LAYER_SCHEMA = "hocrgen.pdf_glyph_layer.v1"
GLYPH_FLAG_INVISIBLE = 1
GLYPH_FLAG_NOT_UPRIGHT = 2
GLYPH_FLAG_ARTIFACT = 4
GLYPH_FLAG_TRANSLUCENT = 8
GLYPH_FLAG_CLIPPED = 16
GLYPH_FLAG_HIDDEN_LAYER = 32


def _round(value: float) -> float:
    return round(float(value), 2)


def _is_white(colour: Any) -> bool:
    if isinstance(colour, (int, float)):
        return float(colour) >= 0.999
    values = [float(part) for part in colour] if isinstance(colour, (list, tuple)) else []
    if len(values) == 1:
        return values[0] >= 0.999
    if len(values) == 3:
        return all(part >= 0.999 for part in values)
    if len(values) == 4:
        return all(part <= 0.001 for part in values)
    return False


def truetype_glyph_outlines(data: bytes) -> list[bytes] | None:
    """The ``glyf`` bytes of every glyph id of a TrueType font program, or None when it has no ``glyf`` table."""

    count = struct.unpack(">H", data[4:6])[0]
    tables = {}
    for index in range(count):
        tag, _, offset, length = struct.unpack(">4sIII", data[12 + 16 * index : 28 + 16 * index])
        tables[tag.decode("latin-1")] = (offset, length)
    if not {"glyf", "loca", "head", "maxp"} <= set(tables):
        return None
    long_offsets = struct.unpack(">h", data[tables["head"][0] + 50 : tables["head"][0] + 52])[0]
    glyphs = struct.unpack(">H", data[tables["maxp"][0] + 4 : tables["maxp"][0] + 6])[0]
    loca_offset = tables["loca"][0]
    if long_offsets:
        loca = list(struct.unpack(f">{glyphs + 1}I", data[loca_offset : loca_offset + 4 * (glyphs + 1)]))
    else:
        loca = [2 * value for value in struct.unpack(f">{glyphs + 1}H", data[loca_offset : loca_offset + 2 * (glyphs + 1)])]
    glyf = tables["glyf"][0]
    return [data[glyf + loca[gid] : glyf + loca[gid + 1]] for gid in range(glyphs)]


def truetype_units_per_em(data: bytes) -> int:
    count = struct.unpack(">H", data[4:6])[0]
    for index in range(count):
        tag, _, offset, _ = struct.unpack(">4sIII", data[12 + 16 * index : 28 + 16 * index])
        if tag == b"head":
            return struct.unpack(">H", data[offset + 18 : offset + 20])[0] or 1000
    return 1000


def glyph_bounds(glyph: bytes, units_per_em: int) -> list[int] | None:
    """A TrueType glyph's ink box (``xMin, yMin, xMax, yMax`` of its ``glyf`` header) in thousandths of an em."""

    if len(glyph) < 10:
        return None
    x_min, y_min, x_max, y_max = struct.unpack(">4h", glyph[2:10])
    return [round(value * 1000 / units_per_em) for value in (x_min, y_min, x_max, y_max)]


def _truetype_outlines(spec: Any, resolve1: Any) -> tuple[list[bytes], int] | None:  # pragma: no cover - needs pdfminer.six
    """Outlines indexed by CID, and units per em, for a Type0 font over a TrueType CID font with an identity
    CID-to-GID map."""

    try:
        spec = resolve1(spec)
        if not isinstance(spec, dict) or "DescendantFonts" not in spec:
            return None
        descendant = resolve1(resolve1(spec["DescendantFonts"])[0])
        mapping = resolve1(descendant.get("CIDToGIDMap"))
        if mapping is not None and "Identity" not in str(mapping):
            return None
        stream = resolve1(resolve1(descendant["FontDescriptor"]).get("FontFile2"))
        if stream is None:
            return None
        data = stream.get_data()
        outlines = truetype_glyph_outlines(data)
        return (outlines, truetype_units_per_em(data)) if outlines is not None else None
    except Exception:  # noqa: BLE001 - an unreadable font program simply has no outline hashes
        return None


def extract_glyph_layer(pdf_path: Path, page_number: int) -> dict[str, Any]:  # pragma: no cover - needs pdfminer.six
    """The glyph layer of one 1-based page. Requires ``pdfminer.six`` (``pip install 'hocrgen[pdf]'``)."""

    from pdfminer import __version__ as pdfminer_version
    from pdfminer.converter import PDFLayoutAnalyzer
    from pdfminer.layout import LTChar, LTCurve, LTFigure, LTImage
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdftypes import PDFObjRef, resolve1
    from pdfminer.psparser import PSLiteral, literal_name
    from pdfminer.utils import apply_matrix_pt, translate_matrix

    state: dict[str, Any] = {"alpha": 1.0, "tags": [], "paint": 0, "clip": None, "clip_stack": [], "off": set()}

    def hidden_layer() -> bool:
        return any(entry.get("hidden") for _, entry in state["tags"])

    def outside_clip(x0: float, y0: float, x1: float, y1: float) -> bool:
        clip = state["clip"]
        return clip is not None and (x1 < clip[0] or x0 > clip[2] or y1 < clip[1] or y0 > clip[3])

    def optional_content_hidden(ref: Any) -> bool:
        target = resolve1(ref)
        if not isinstance(target, dict):
            return False
        if str(target.get("Type")) == "/'OCMD'":
            members = resolve1(target.get("OCGs"))
            members = members if isinstance(members, list) else [target.get("OCGs")]
            ids = [member.objid for member in members if isinstance(member, PDFObjRef)]
            policy = str(target.get("P", "/'AnyOn'"))
            if "AllOn" in policy:
                return any(objid in state["off"] for objid in ids)
            if "AnyOff" in policy:
                return not any(objid in state["off"] for objid in ids)
            if "AllOff" in policy:
                return not all(objid in state["off"] for objid in ids)
            return bool(ids) and all(objid in state["off"] for objid in ids)
        return isinstance(ref, PDFObjRef) and ref.objid in state["off"]
    records: dict[str, list[Any]] = {"glyphs": [], "fills": [], "strokes": [], "images": [], "actual_text": []}
    fonts: list[dict[str, Any]] = []
    font_ids: dict[int, int] = {}
    font_specs: dict[int, Any] = {}
    font_outlines: dict[int, tuple[list[bytes], int] | None] = {}
    origin: list[float] = [0.0, 0.0]  # the media box's left edge and top edge

    def font_index(font: Any, cid: int) -> int:
        key = id(font)
        if key not in font_ids:
            font_ids[key] = len(fonts)
            unicode_map = getattr(font, "unicode_map", None)
            tounicode = dict(getattr(unicode_map, "cid2unichr", {}) or {}) if unicode_map is not None else {}
            fonts.append({
                "name": str(getattr(font, "fontname", "")),
                "tounicode": {str(code): text for code, text in sorted(tounicode.items())},
                "outlines": {},
                "bounds": {},
            })
            font_outlines[key] = _truetype_outlines(font_specs.get(key), resolve1)
        record = fonts[font_ids[key]]
        program = font_outlines[key]
        if str(cid) not in record["outlines"]:
            glyph = program[0][cid] if program is not None and 0 <= cid < len(program[0]) else None
            record["outlines"][str(cid)] = hashlib.sha256(glyph).hexdigest()[:16] if glyph else None
            record["bounds"][str(cid)] = glyph_bounds(glyph, program[1]) if glyph and program is not None else None
        return font_ids[key]

    def top_down(x0: float, y0: float, x1: float, y1: float) -> list[float]:
        left, top = origin
        return [_round(x0 - left), _round(top - y1), _round(x1 - left), _round(top - y0)]

    class Device(PDFLayoutAnalyzer):
        def render_char(self, matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate):  # type: ignore[no-untyped-def]
            before = len(self.cur_item._objs)
            advance = super().render_char(matrix, font, fontsize, scaling, rise, cid, ncs, graphicstate)
            for item in self.cur_item._objs[before:]:
                if not isinstance(item, LTChar):
                    continue
                origin_x, baseline = apply_matrix_pt(matrix, (0, rise))
                flags = 0
                if state.get("render_mode") in (3, 7):
                    flags |= GLYPH_FLAG_INVISIBLE
                if not item.upright:
                    flags |= GLYPH_FLAG_NOT_UPRIGHT
                if any(tag == "Artifact" for tag, _ in state["tags"]):
                    flags |= GLYPH_FLAG_ARTIFACT
                if state["alpha"] < 0.999:
                    flags |= GLYPH_FLAG_TRANSLUCENT
                if outside_clip((item.x0 + item.x1) / 2, (item.y0 + item.y1) / 2, (item.x0 + item.x1) / 2, (item.y0 + item.y1) / 2):
                    flags |= GLYPH_FLAG_CLIPPED
                if hidden_layer():
                    flags |= GLYPH_FLAG_HIDDEN_LAYER
                paint = state["paint"]
                state["paint"] += 1
                for _, props in state["tags"]:
                    if isinstance(props, dict) and "actual" in props:
                        props.setdefault("first", paint)
                        props["last"] = paint
                records["glyphs"].append(
                    [paint, item.get_text(), *top_down(item.x0, item.y0, item.x1, item.y1), _round(origin_x - origin[0]),
                     _round(origin[1] - baseline), _round(item.size), font_index(font, int(cid)), flags, int(cid)]
                )
            return advance

        def render_string_horizontal(self, seq, matrix, pos, font, fontsize, scaling, charspace, wordspace, rise, dxscale, ncs, graphicstate):  # type: ignore[no-untyped-def]
            # PDF 32000-1 9.4.4: the character spacing Tc follows every glyph, the last of a string too. pdfminer.six
            # adds it only between the glyphs of one string, so letter-spaced lines set as many short strings drift.
            x, y = pos
            for obj in seq:
                if isinstance(obj, (int, float)):
                    x -= obj * dxscale
                elif isinstance(obj, bytes):
                    for cid in font.decode(obj):
                        x += self.render_char(translate_matrix(matrix, (x, y)), font, fontsize, scaling, rise, cid, ncs, graphicstate)
                        x += charspace
                        if cid == 32 and wordspace:
                            x += wordspace
            return (x, y)

        def paint_path(self, gstate, stroke, fill, evenodd, path):  # type: ignore[no-untyped-def]
            before = len(self.cur_item._objs)
            super().paint_path(gstate, stroke, fill, evenodd, path)
            for item in self.cur_item._objs[before:]:
                if not isinstance(item, LTCurve) or hidden_layer() or outside_clip(item.x0, item.y0, item.x1, item.y1):
                    continue
                paint = state["paint"]
                state["paint"] += 1
                box = top_down(item.x0, item.y0, item.x1, item.y1)
                if item.fill:
                    colour = "white" if _is_white(item.non_stroking_color) else "other"
                    records["fills"].append([paint, *box, colour, _round(state["alpha"])])
                if item.stroke:
                    records["strokes"].append([paint, *box])

        def render_image(self, name, stream):  # type: ignore[no-untyped-def]
            super().render_image(name, stream)
            figure = self.cur_item
            if hidden_layer() or outside_clip(figure.x0, figure.y0, figure.x1, figure.y1):
                return
            paint = state["paint"]
            state["paint"] += 1
            records["images"].append([paint, *top_down(figure.x0, figure.y0, figure.x1, figure.y1)])

        def begin_tag(self, tag, props=None):  # type: ignore[no-untyped-def]
            name = literal_name(tag) if isinstance(tag, PSLiteral) else str(tag)
            entry: dict[str, Any] = {"hidden": state.pop("oc_pending", False)}
            resolved = resolve1(props) if props is not None else None
            if isinstance(resolved, dict) and "ActualText" in resolved:
                raw = resolve1(resolved["ActualText"])
                if isinstance(raw, bytes):
                    entry["actual"] = raw[2:].decode("utf-16-be", "replace") if raw[:2] == b"\xfe\xff" else raw.decode("latin-1")
                else:
                    entry["actual"] = str(raw)
            state["tags"].append((name, entry))

        def end_tag(self):  # type: ignore[no-untyped-def]
            if not state["tags"]:
                return
            _, entry = state["tags"].pop()
            if "actual" in entry and "first" in entry:
                records["actual_text"].append([entry["first"], entry["last"], entry["actual"]])

        def receive_layout(self, ltpage):  # type: ignore[no-untyped-def]
            return None

    class Interpreter(PDFPageInterpreter):
        def do_BDC(self, tag, props):  # type: ignore[no-untyped-def]
            if isinstance(tag, PSLiteral) and literal_name(tag) == "OC":
                properties = resolve1((resolve1(self.resources.get("Properties")) or {}))
                reference = properties.get(literal_name(props)) if isinstance(props, PSLiteral) and isinstance(properties, dict) else props
                state["oc_pending"] = optional_content_hidden(reference)
            super().do_BDC(tag, props)

        def do_Do(self, xobjid_arg):  # type: ignore[no-untyped-def]
            xobject = resolve1(self.xobjmap.get(literal_name(xobjid_arg)))
            reference = getattr(xobject, "attrs", {}).get("OC") if xobject is not None else None
            if reference is not None and optional_content_hidden(reference):
                return
            super().do_Do(xobjid_arg)

        def do_W(self):  # type: ignore[no-untyped-def]
            self._clip_from_path()

        def do_W_a(self):  # type: ignore[no-untyped-def]
            self._clip_from_path()

        def _clip_from_path(self):  # type: ignore[no-untyped-def]
            points = []
            for segment in self.curpath:
                coordinates = segment[1:]
                points.extend(apply_matrix_pt(self.ctm, (coordinates[i], coordinates[i + 1])) for i in range(0, len(coordinates) - 1, 2))
            if not points:
                return
            box = [min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)]
            clip = state["clip"]
            if clip is not None:
                box = [max(box[0], clip[0]), max(box[1], clip[1]), min(box[2], clip[2]), min(box[3], clip[3])]
            state["clip"] = box

        def init_resources(self, resources):  # type: ignore[no-untyped-def]
            super().init_resources(resources)
            for fontid, font in self.fontmap.items():
                spec = resolve1((resolve1((resources or {}).get("Font")) or {}).get(fontid))
                font_specs.setdefault(id(font), spec)

        def do_gs(self, name):  # type: ignore[no-untyped-def]
            extgstate = resolve1((resolve1(self.resources.get("ExtGState")) or {}).get(literal_name(name)))
            if isinstance(extgstate, dict) and "ca" in extgstate:
                state["alpha"] = float(resolve1(extgstate["ca"]))

        def do_Tr(self, render):  # type: ignore[no-untyped-def]
            super().do_Tr(render)
            state["render_mode"] = int(render)

        def do_q(self):  # type: ignore[no-untyped-def]
            super().do_q()
            state.setdefault("alpha_stack", []).append(state["alpha"])
            state["clip_stack"].append(state["clip"])

        def do_Q(self):  # type: ignore[no-untyped-def]
            super().do_Q()
            if state.get("alpha_stack"):
                state["alpha"] = state["alpha_stack"].pop()
            if state["clip_stack"]:
                state["clip"] = state["clip_stack"].pop()

    manager = PDFResourceManager(caching=True)
    device = Device(manager, laparams=None)
    interpreter = Interpreter(manager, device)
    with pdf_path.open("rb") as handle:
        document = PDFDocument(PDFParser(handle))
        configuration = resolve1((resolve1(document.catalog.get("OCProperties")) or {}).get("D")) or {}
        state["off"] = {ref.objid for ref in resolve1(configuration.get("OFF")) or [] if isinstance(ref, PDFObjRef)}
        for index, page in enumerate(PDFPage.create_pages(document)):
            if index + 1 != page_number:
                continue
            x0, y0, x1, y1 = page.mediabox
            origin[0], origin[1] = float(x0), float(y1)
            state["clip"] = [float(x0), float(y0), float(x1), float(y1)]
            rotation = int(page.rotate or 0)
            interpreter.process_page(page)
            return {
                "schema": GLYPH_LAYER_SCHEMA,
                "extractor": "pdfminer.six",
                "extractor_version": str(pdfminer_version),
                "page": {"number": page_number, "width": _round(x1 - x0), "height": _round(y1 - y0), "rotation": rotation},
                "fonts": fonts,
                **records,
            }
    raise ValueError(f"{pdf_path} has no page {page_number}")
