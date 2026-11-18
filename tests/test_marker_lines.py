"""Marker offsets of Sefaria texts (text_sources.sefaria_marker_offsets) and the builder's --drop-marker-lines rule."""

from __future__ import annotations

from hocrgen.fetchers import text_sources as ts


def _version(segments):
    return {"title": "Example", "versionTitle": "Example, Lemberg, 1888", "text": segments, "schema": None}


def test_marker_offsets_reproduce_the_text_and_point_at_removed_anchors() -> None:
    seg1 = 'אם <i data-commentator="Turei Zahav" data-order="1"></i>נשברה השדרה <i data-commentator="Siftei Kohen" data-order="2"></i> כשרה'
    seg2 = '<i data-commentator="Be\'er HaGolah" data-order="1"></i>שני דברים'
    version = _version([[seg1, seg2]])
    body, _ = ts.sefaria_text(version)
    m = ts.sefaria_marker_offsets(version)
    assert m["text_sha256"] == ts.sha256_bytes(body.encode("utf-8"))
    assert body == "אם נשברה השדרה כשרה\nשני דברים\n"
    # anchors before "נשברה", before "כשרה" and at the start of the second segment
    assert [body[i:i + 2] for i in m["anchor_offsets"]] == ["נש", "כש", "שנ"]
    assert m["segment_starts"] == [0, body.index("שני")]


def test_a_text_without_anchors_has_none() -> None:
    m = ts.sefaria_marker_offsets(_version([["שורה ראשונה", "שורה שנייה"]]))
    assert m["anchor_offsets"] == [] and len(m["segment_starts"]) == 2
