"""knesset_lines: gated training-line text from born-digital Knesset protocols (plenary and committee series).

Nothing here needs LibreOffice, the NER venv, hocrsyngen or the network: the text conversion, the tagger, the renderer's
output and the HTTP opener are injected or faked. The plenary K13+ sittings are not in the packaged eval registry yet
(unassigned), so plenary builds run on a registry that lists the test sittings as non_eval.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.error
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.config.loader import load_and_validate_bundle
from hocrgen.privacy import ner_stream
from hocrgen.privacy.committee_names import GATE_ID as COMMITTEE_GATE
from hocrgen.privacy.plenary_names import GATE_ID as PLENARY_GATE
from hocrgen.privacy.plenary_names import Roster, UngatedPlenaryLinesError, stream_text
from hocrgen.split.eval_reserved import EvalReservedUnitError
from hocrgen.tools import knesset_lines as kl

ROSTER = Roster.from_people([{"first": "יואב", "last": "בן צור", "knessets": [13, 18, 25]},
                             {"first": "משה", "last": "כהן", "knessets": [18]}])
K13_ENUM = Path.home() / "agents/environments/opensource/projects/heocr/tasks/modern-s6-scout/knesset/plenary_units_k13plus.json"
CMT_ENUM = Path.home() / "agents/environments/opensource/projects/heocr/tasks/modern-s6-scout/knesset/committee_docs_k16plus.json"


MODERN_SOURCES = ("knesset_plenary_k13_25", "knesset_committee_protocols_k16plus")


def _registry(non_eval=(), eval_units=()):
    """The packaged registry made hermetic for these tests: the modern Knesset sources (E2f7: plenary K13-25, committee
    K16-25) hold only the test units given here, placed in the source their id routes to."""

    registry = load_and_validate_bundle().eval_reserved_units
    data = registry.model_dump(mode="json")
    k13 = next(s for s in data["sources"] if s["source_id"] == "knesset_plenary_k13_25")
    if not any(s["source_id"] == "knesset_committee_protocols_k16plus" for s in data["sources"]):
        data["sources"].append({**json.loads(json.dumps(k13)), "source_id": "knesset_committee_protocols_k16plus"})
    for src in data["sources"]:
        if src["source_id"] in MODERN_SOURCES:
            src["eval_units"], src["non_eval_units"] = [], []

    def source_of(unit):
        if unit.startswith("committee:"):
            return "knesset_committee_protocols_k16plus"
        k = int(unit.split(":K", 1)[1].split("_", 1)[0])
        return "knesset_plenary_k1_12" if k <= 12 else "knesset_plenary_k13_25"

    for units, key in ((non_eval, "non_eval_units"), (eval_units, "eval_units")):
        for unit in units:
            for src in data["sources"]:
                for field in ("non_eval_units", "eval_units"):
                    src[field] = [u for u in src.get(field, []) if u != unit]
            target = next(s for s in data["sources"] if s["source_id"] == source_of(unit))
            target[key] = sorted(set(target[key]) | {unit})
    return type(registry).model_validate(data)


def _unit(k, s, docs=None):
    if docs is None:
        docs = [{"document_id": 1000 * k + s, "format": "DOC", "url": f"https://fs.knesset.gov.il//{k}/Plenum/{k}_ptm_{1000 * k + s}.doc",
                 "group_type": "דברי הכנסת", "protocol_proper": True}]
    return {"knesset": k, "sitting": s, "date": "2000-01-01", "documents": docs}


# --- plan ---------------------------------------------------------------------------------------------------------


def test_plan_takes_the_first_non_eval_sittings_per_term_by_sha256() -> None:
    units = [_unit(13, s) for s in range(1, 21)] + [_unit(14, s) for s in range(1, 6)] + [_unit(12, 1)]
    ids13 = sorted((f"plenary:K13_{s}" for s in range(1, 21)), key=kl.rank_key)
    registry = _registry(non_eval=[f"plenary:K{u['knesset']}_{u['sitting']}" for u in units if u["knesset"] >= 13
                                   and f"plenary:K13_{u['sitting']}" != ids13[1]], eval_units=[ids13[1]])
    plan = kl.plan_units({"units": units}, kl.PLENARY, per_term=3, registry=registry)
    assert [u["unit_id"] for u in plan["units"] if u["knesset"] == 13] == [ids13[0], ids13[2], ids13[3]]
    assert plan["skipped_before_selection"]["13"] == {"eval": 1}  # the eval sitting is skipped, never selected
    assert len([u for u in plan["units"] if u["knesset"] == 14]) == 3
    assert not [u for u in plan["units"] if u["knesset"] == 12]  # outside the series' terms
    assert kl.rank_key("plenary:K13_1") == hashlib.sha256(b"heocr-knessetlines-v1:plenary:K13_1").hexdigest()


def test_plan_picks_the_protocol_document_and_skips_unassigned_sittings() -> None:
    docs = [{"document_id": 9, "format": "DOC", "url": "https://fs.knesset.gov.il/x/13_ptm_9.docx", "protocol_proper": True},
            {"document_id": 8, "format": "DOC", "url": "https://fs.knesset.gov.il/x/13_ptm_8.doc", "protocol_proper": False},
            {"document_id": 7, "format": "PDF", "url": "https://fs.knesset.gov.il/x/13_ptm_7.pdf", "protocol_proper": True}]
    units = [_unit(13, 1, docs), _unit(13, 2, docs[1:]), _unit(13, 3)]
    plan = kl.plan_units({"units": units}, kl.PLENARY, per_term=5, registry=_registry(non_eval=["plenary:K13_1", "plenary:K13_2"]))
    assert [u["unit_id"] for u in plan["units"]] == ["plenary:K13_1"]
    assert plan["units"][0]["document"]["document_id"] == 9 and kl.document_ext(plan["units"][0]["document"]) == "docx"
    assert plan["skipped_before_selection"]["13"] == {"no_protocol_document": 1, "unassigned": 1}
    # With only K13_3 assigned, the other sittings stay unassigned and are never planned.
    assert [u["unit_id"] for u in kl.plan_units({"units": units}, kl.PLENARY, registry=_registry(non_eval=["plenary:K13_3"]))["units"]] == ["plenary:K13_3"]


def test_committee_plan_groups_documents_by_session() -> None:
    docs = [{"knesset": 18, "committee_session_id": 471534, "session_date": "2012-06-19", "committee_id": 4, "document_id": d,
             "format": "DOC", "group_type": "פרוטוקול ועדה", "url": f"https://fs.knesset.gov.il//18/Committees/18_ptv_{d}.doc"}
            for d in (216179, 216180)]
    docs.append({**docs[0], "document_id": 1, "group_type": "חומר רקע"})
    docs.append({**docs[0], "committee_session_id": 5, "knesset": 15})  # before K16: outside the series
    assert kl.plan_units({"documents": docs}, kl.COMMITTEE, registry=_registry())["units"] == []  # unassigned: refused
    plan = kl.plan_units({"documents": docs}, kl.COMMITTEE, registry=_registry(non_eval=["committee:K18_471534"]))
    assert [(u["unit_id"], u["document"]["document_id"], u["eval_status"]) for u in plan["units"]] == [
        ("committee:K18_471534", 216179, "non_eval")]
    assert not kl.committee_unit_id(18, 471534).startswith("knesset_committee")


@pytest.mark.skipif(not K13_ENUM.is_file(), reason="the K13+ enumeration is not on this machine")
def test_plan_on_the_k13_plus_enumeration() -> None:
    enumeration = json.loads(K13_ENUM.read_text(encoding="utf-8"))
    ids = [kl.plenary_unit_id(u["knesset"], u["sitting"]) for u in enumeration["units"] if u.get("sitting") is not None]
    plan = kl.plan_units(enumeration, kl.PLENARY, registry=_registry(non_eval=ids))
    terms = {u["knesset"] for u in plan["units"]}
    assert terms == set(range(13, 26)) & {u["knesset"] for u in enumeration["units"]}
    assert all(u["document"].get("protocol_proper") for u in plan["units"])
    assert all(sum(1 for v in plan["units"] if v["knesset"] == k) <= 8 for k in terms)


@pytest.mark.skipif(not CMT_ENUM.is_file(), reason="the K16+ committee enumeration is not on this machine")
def test_plan_on_the_k16_plus_committee_enumeration() -> None:
    plan = kl.plan_units(json.loads(CMT_ENUM.read_text(encoding="utf-8")), kl.COMMITTEE)
    assert plan["units"] and all(u["unit_id"].startswith("committee:K") and 16 <= u["knesset"] <= 25 for u in plan["units"])


# --- paragraphs, wrap and line rules ------------------------------------------------------------------------------


PLENARY_TEXT = "\n".join([
    "﻿דברי הכנסת", "תוכן העניינים", "יואב בן צור (הליכוד):\t12", "",
    ' << יור >> היו"ר יואב בן צור: << יור >>   ',
    "אני פותח את הישיבה. " + "מילים רבות מאוד בפסקה ארוכה " * 6,
    " << דובר >> יואב בן צור (הליכוד): << דובר >> ",
    "\tקיבלתי מכתב מאת מר רונית לוינסון מחיפה.",
    "<הישיבה נעולה.>",
    "מיום 1.1.2012 ואילך",
])


def test_paragraphs_lose_markers_and_front_matter_and_wrap_exactly() -> None:
    unit = {"unit_id": "plenary:K25_7", "knesset": 25}
    result = kl.unit_lines(unit, PLENARY_TEXT, kl.PLENARY)
    lines = result["lines"]
    assert result["front_matter_paragraphs"] == 3 and lines[0]["text"] == 'היו"ר יואב בן צור:'
    assert lines[0].get("is_speaker_heading") and not any("<" in line["text"] for line in lines)
    long = [line["text"] for line in lines if line["paragraph_index"] == 5]
    assert len(long) > 1 and all(len(text) <= result["wrap_width"] for text in long)
    assert " ".join(long) == "אני פותח את הישיבה. " + ("מילים רבות מאוד בפסקה ארוכה " * 6).strip()
    assert [line["text"] for line in lines if line["paragraph_index"] == 8] == ["הישיבה נעולה."]  # <...> unwrapped
    assert [line["drop"] for line in lines if line["paragraph_index"] == 9] == ["bidi_or_digit_flagged"]
    assert 40 <= kl.wrap_width("plenary:K25_7") <= 90 and kl.wrap_width("plenary:K25_7") == kl.wrap_width("plenary:K25_7")
    assert kl.unit_lines(unit, "רק טקסט\nבלי דוברים", kl.PLENARY)["refused"] == "no_body_start"


def test_wrap_preserves_characters_and_line_rules() -> None:
    text = 'חבר הכנסת  א.ב., "ציטוט" — ומילה־מחוברת ארוכהארוכהארוכהארוכהארוכהארוכהארוכה וזהו'
    text = " ".join(text.split())
    for width in (10, 40, 90):
        assert " ".join(kl.wrap(text, width)) == text
    assert kl.text_drop_reason("שָׁלוֹם")[0] == "pointed"
    assert kl.text_drop_reason("— – .")[0] == "no_letters_or_digits"
    assert kl.text_drop_reason("ראה www.gov.il")[0] == "bidi_or_digit_flagged"
    assert kl.text_drop_reason("סעיף 3(ב) לחוק")[0] == "bidi_or_digit_flagged"
    assert kl.text_drop_reason("תג << שארית")[0] == "marker_remnant"
    assert kl.text_drop_reason('התשפ"ב-2022 נקבע')[0] is None


COMMITTEE_TEXT = "\n".join([
    "הכנסת העשרים-וארבע", "פרוטוקול מס' 4", "סדר היום:\tסוגיות", "נכחו:", "חברי הוועדה: \tיואב בן צור – היו\"ר",
    "מוזמנים:\tאורי כהן\t–\tעמותת דוגמה", "רחל זכאית\t–\tמשרד", "ייעוץ משפטי:\tנעה שקד",
    ' << יור >> היו"ר יואב בן צור: << יור >>   ', "אני מבקש להודות למר כהן על עבודתו.",
    " << אורח >> רחל זכאית: << אורח >> ", "תודה רבה לכם.",
])


def test_committee_lines_flag_the_attendance_block_and_guest_headings() -> None:
    unit = {"unit_id": "committee:K18_471534", "knesset": 18}
    result = kl.unit_lines(unit, COMMITTEE_TEXT, kl.COMMITTEE)
    block = [line["text"] for line in result["lines"] if line.get("in_attendance_block")]
    assert block[0] == "נכחו:" and "רחל זכאית – משרד" in block and len(block) == result["attendance_block_paragraphs"]
    assert result["front_matter_paragraphs"] == 3  # masthead and agenda before the block are dropped
    assert {line["text"] for line in result["lines"] if line.get("is_speaker_heading")} >= {"רחל זכאית:"}


# --- capture ------------------------------------------------------------------------------------------------------


class _Response(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _plan(*units, series="plenary"):
    return {"series": series, "units": [{"unit_id": u.get("unit_id") or kl.plenary_unit_id(u["knesset"], u["sitting"]),
                                         "knesset": u["knesset"], "sitting": u["sitting"], "date": u.get("date"),
                                         "document": dict(u["documents"][0])} for u in units]}


def test_capture_rate_limits_pins_and_stops_on_a_block(tmp_path: Path) -> None:
    calls, sleeps, now = [], [], [0.0]

    def opener(request, timeout):
        calls.append(request.full_url)
        assert request.get_header("User-agent") == kl.CAPTURE_UA
        if len(calls) == 3:
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {}, io.BytesIO(b""))
        return _Response(kl.MAGIC["doc"] + b"body%d" % len(calls))

    plan = _plan(_unit(13, 1), _unit(13, 2), _unit(13, 3))
    with pytest.raises(kl.CaptureStopped, match="status 429"):
        kl.capture(plan, tmp_path, opener=opener, sleep=lambda s: (sleeps.append(s), now.__setitem__(0, now[0] + s)),
                   clock=lambda: now[0])
    pins = json.loads((tmp_path / "capture_pins.json").read_text())
    assert sorted(pins) == ["13_ptm_13001.doc", "13_ptm_13002.doc"]
    assert pins["13_ptm_13001.doc"]["sha256"] == hashlib.sha256((tmp_path / "13_ptm_13001.doc").read_bytes()).hexdigest()
    assert sleeps == [3.0, 3.0]  # one request per 3 s
    log = [json.loads(line) for line in (tmp_path / "capture_log.jsonl").read_text().splitlines()]
    assert [entry["status"] for entry in log] == [200, 200, 429] and log[-1]["blocked"]
    calls.clear()
    bad = _unit(13, 4, [{"document_id": 4, "format": "DOC", "url": "https://example.com/13_ptm_4.doc", "protocol_proper": True}])
    with pytest.raises(kl.CaptureStopped, match="outside"):
        kl.capture(_plan(_unit(13, 1), bad), tmp_path, opener=opener, sleep=lambda s: None, clock=lambda: 0.0)
    assert calls == []  # the pinned file is skipped and the foreign URL refused before any request


# --- build: gate wiring, dedup, verify ----------------------------------------------------------------------------


def _fake_ner(calls, names=("רונית לוינסון", "יואב בן צור", "כהן", "רחל זכאית")):
    def ner(streams):
        calls.extend(streams)
        out = {}
        for stream in streams:
            spans, text = [], stream["text"]
            for name in names:
                start = text.find(name)
                while start >= 0:
                    spans.append({"start": start, "end": start + len(name), "text": name})
                    start = text.find(name, start + 1)
            out[stream["id"]] = spans
        return out
    return ner


def _setup(tmp_path: Path, series: str, units: list[dict], texts: dict[str, str]) -> dict:
    cache = tmp_path / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    plan = _plan(*units, series=series)
    for entry in plan["units"]:
        data = kl.MAGIC["doc"] + entry["unit_id"].encode()
        (cache / kl.document_name(entry["document"])).write_bytes(data)
        entry["document"]["sha256"] = hashlib.sha256(data).hexdigest()
    (tmp_path / "plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    by_name = {kl.document_name(e["document"]): texts[e["unit_id"]] for e in plan["units"]}
    args = argparse.Namespace(out=str(tmp_path / "out"), plan=str(tmp_path / "plan.json"), cache=str(cache), series=series,
                              max_lines_per_unit=800, max_label_copies=3, private_dir=None, soffice_version="test",
                              created_at="2026-11-13", signature="test")
    return {"args": args, "to_text": lambda document, workdir: by_name[document.name], "tmp": tmp_path}


REPEAT = "\n".join(["הישיבה נעולה."] * 3)


@pytest.fixture()
def plenary(tmp_path: Path) -> dict:
    units = [_unit(13, 5), _unit(25, 7)]
    texts = {"plenary:K13_5": PLENARY_TEXT + "\n" + REPEAT, "plenary:K25_7": PLENARY_TEXT + "\n" + REPEAT}
    env = _setup(tmp_path, "plenary", units, texts)
    env["registry"] = _registry(non_eval=["plenary:K13_5", "plenary:K25_7"])
    env["calls"] = []
    env["summary"] = kl.build(env["args"], registry=env["registry"], to_text=env["to_text"], ner=_fake_ner(env["calls"]), roster=ROSTER)
    env["out"] = Path(env["args"].out)
    return env


def _rows(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "lines_text.jsonl").read_text(encoding="utf-8").splitlines()]


def test_plenary_build_gates_each_unit_stream_and_writes_no_dropped_text(plenary: dict) -> None:
    out, summary = plenary["out"], plenary["summary"]
    # The tagger saw each sitting's lines joined by stream_text, every line included (also lines dropped by text rules).
    lines = kl.unit_lines({"unit_id": "plenary:K25_7", "knesset": 25}, PLENARY_TEXT + "\n" + REPEAT, kl.PLENARY)["lines"]
    call = next(c for c in plenary["calls"] if c["id"] == "plenary:K25_7")
    assert call["text"] == stream_text(lines)[0]
    rows = _rows(out)
    assert not any("לוינסון" in row["text"] for row in rows)
    assert all(row["privacy_gate"] == PLENARY_GATE and row["release_scope"] == "publishable" for row in rows)
    assert all(row["capture"] == "synthetic_render" and row["label_source"] == "born_digital_protocol_text"
               and row["reference_eligible"] is False and row["eval_use"] == "never" for row in rows)
    heading = [row for row in rows if row["is_speaker_heading"]]
    assert heading and all(row["privacy_note"] == "speaker_heading" for row in heading)
    committed = [p for p in out.rglob("*") if p.is_file() and "private" not in p.parts]
    assert not any("לוינסון" in p.read_text(encoding="utf-8") for p in committed)
    private = [json.loads(line) for line in (out / "private" / "gate_dropped.jsonl").read_text(encoding="utf-8").splitlines()]
    assert private and all("לוינסון" in row["text"] for row in private)
    gate = summary["privacy_gate"]
    assert gate["gate"] == PLENARY_GATE and gate["lines_dropped"] == len(private)
    assert set(gate["per_term"]) == {"13", "25"} and summary["dropped"]["privacy_gate"] == len(private)
    # Exact dedup: "הישיבה נעולה." appears 8 times in the set, 3 are kept.
    assert sum(row["text"] == "הישיבה נעולה." for row in rows) == 3 and summary["dedup"]["rows_removed"] == 5
    inputs = [json.loads(line) for line in (out / "render_input.jsonl").read_text(encoding="utf-8").splitlines()]
    assert inputs == [{"id": r["id"], "text": r["text"], "group": r["unit_id"]} for r in rows]
    assert summary["lines_per_term"] == {"13": sum(r["knesset"] == 13 for r in rows), "25": sum(r["knesset"] == 25 for r in rows)}
    assert kl.verify(out, registry=plenary["registry"]) == []


def test_untagged_streams_drop_every_line(plenary: dict) -> None:
    args = argparse.Namespace(**{**vars(plenary["args"]), "out": str(plenary["tmp"] / "out2")})
    summary = kl.build(args, registry=plenary["registry"], to_text=plenary["to_text"], ner=lambda streams: {}, roster=ROSTER)
    assert summary["totals"]["lines"] == 0 and summary["privacy_gate"]["drop_reasons"]["untagged"] > 0


def test_rows_the_gate_did_not_stamp_are_refused(plenary: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    real = kl.make_row
    monkeypatch.setattr(kl, "make_row", lambda *a, **k: {key: v for key, v in real(*a, **k).items() if key != "privacy_gate"})
    args = argparse.Namespace(**{**vars(plenary["args"]), "out": str(plenary["tmp"] / "out3")})
    with pytest.raises(UngatedPlenaryLinesError):
        kl.build(args, registry=plenary["registry"], to_text=plenary["to_text"], ner=_fake_ner([]), roster=ROSTER)
    assert not (plenary["tmp"] / "out3").exists()


def test_units_that_are_not_open_are_never_opened_and_eval_rows_are_refused(plenary: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    opened = []

    def spy(document, workdir):
        opened.append(document.name)
        return plenary["to_text"](document, workdir)

    args = argparse.Namespace(**{**vars(plenary["args"]), "out": str(plenary["tmp"] / "out4")})
    summary = kl.build(args, registry=_registry(non_eval=["plenary:K13_5"]), to_text=spy, ner=_fake_ner([]), roster=ROSTER)
    assert opened == ["13_ptm_13005.doc"] and summary["eval_reserved_check"]["input_units"] == {"open": 1, "unassigned": 1}
    monkeypatch.setattr(kl, "_status", lambda unit_id, registry: "non_eval")
    args = argparse.Namespace(**{**vars(plenary["args"]), "out": str(plenary["tmp"] / "out5")})
    with pytest.raises(EvalReservedUnitError):
        kl.build(args, registry=_registry(eval_units=["plenary:K13_5"], non_eval=["plenary:K25_7"]), to_text=plenary["to_text"],
                 ner=_fake_ner([]), roster=ROSTER)


def test_a_document_off_its_pin_refuses_the_unit(plenary: dict) -> None:
    plan = json.loads(Path(plenary["args"].plan).read_text(encoding="utf-8"))
    plan["units"][0]["document"]["sha256"] = "0" * 64
    Path(plenary["args"].plan).write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    args = argparse.Namespace(**{**vars(plenary["args"]), "out": str(plenary["tmp"] / "out6")})
    summary = kl.build(args, registry=plenary["registry"], to_text=plenary["to_text"], ner=_fake_ner([]), roster=ROSTER)
    assert summary["dropped"]["unit_refused:sha256_mismatch"] == 1
    assert {row["unit_id"] for row in _rows(plenary["tmp"] / "out6")} == {"plenary:K25_7"}


def test_document_signature_accepts_ooxml_under_a_doc_name(tmp_path: Path) -> None:
    doc = {"url": "https://fs.knesset.gov.il//24/Plenum/24_ptm_1.doc"}
    for data, refused in ((kl.MAGIC["docx"] + b"x", None), (kl.MAGIC["doc"] + b"x", None), (b"<html>no</html>", "bad_signature")):
        (tmp_path / "24_ptm_1.doc").write_bytes(data)
        unit = {"document": {**doc, "sha256": hashlib.sha256(data).hexdigest()}}
        assert kl.check_document(unit, tmp_path, {})[2] == refused
    assert kl.check_document({"document": doc}, tmp_path, {})[2] == "unpinned"


def test_dedup_keeps_at_most_three_copies_by_sha256_of_the_id() -> None:
    rows = [{"id": f"r{i}", "text": "הישיבה נעולה."} for i in range(6)] + [{"id": "x", "text": "אחר"}]
    kept, stats = kl.dedup_rows(rows)
    same = [r["id"] for r in kept if r["text"] == "הישיבה נעולה."]
    assert same == sorted(same)  # original order kept
    assert set(same) == set(sorted((f"r{i}" for i in range(6)), key=lambda v: hashlib.sha256(v.encode()).hexdigest())[:3])
    assert stats == {"max_copies": 3, "rows_in": 7, "rows_removed": 3, "labels_over_cap": 1, "distinct_labels": 2}


def test_committee_build_uses_the_committee_gate_denylist_and_scope(tmp_path: Path) -> None:
    unit = {"unit_id": "committee:K18_471534", "knesset": 18, "sitting": 471534, "date": "2012-06-19",
            "documents": [{"document_id": 216179, "format": "DOC", "url": "https://fs.knesset.gov.il//18/Committees/18_ptv_216179.doc"}]}
    env = _setup(tmp_path, "committee", [unit], {"committee:K18_471534": COMMITTEE_TEXT})
    calls: list = []
    committee_registry = _registry(non_eval=["committee:K18_471534"])
    summary = kl.build(env["args"], registry=committee_registry, to_text=env["to_text"], ner=_fake_ner(calls), roster=ROSTER)
    rows = _rows(tmp_path / "out")
    texts = {row["text"] for row in rows}
    # The attendance block drops whole; the guest's heading and the body mention of the guest's surname drop too.
    assert "נכחו:" not in texts and not any("זכאית" in t or "כהן" in t for t in texts)
    assert 'היו"ר יואב בן צור:' in texts and "תודה רבה לכם." in texts
    assert all(row["privacy_gate"] == COMMITTEE_GATE and row["release_scope"] == "training_only" and row["training_only"]
               and row["source_id"] == "knesset_committee_protocols_k16plus" for row in rows)
    gate = summary["privacy_gate"]
    assert gate["gate"] == COMMITTEE_GATE and gate["drop_reasons"]["attendance_block"] == 5
    assert gate["drop_reasons"].get("session_denylist", 0) >= 1
    # The tagger saw only the lines outside the attendance block (the stream gate_committee_lines judges).
    lines = kl.unit_lines(unit, COMMITTEE_TEXT, kl.COMMITTEE)["lines"]
    assert calls[0]["text"] == stream_text([line for line in lines if not line.get("in_attendance_block")])[0]
    assert kl.verify(tmp_path / "out", registry=committee_registry) == []
    # Training-only text keeps one copy of each exact label (2026-11-11, safeguard 3).
    assert summary["dedup"]["max_copies"] == 1 and len(texts) == len(rows)
    assert any("unassigned" in problem for problem in kl.verify(tmp_path / "out", registry=_registry()))


def test_verify_finds_tampering_and_the_packaged_registry_refuses_k13_plus(plenary: dict) -> None:
    out, registry = plenary["out"], plenary["registry"]
    assert any("unassigned" in problem for problem in kl.verify(out, registry=_registry()))  # sittings no split lists
    rows = _rows(out)
    rows[0].pop("privacy_gate")
    rows[1]["capture"] = "rendered"
    rows[2]["text"] = "שָׁלוֹם"
    (out / "lines_text.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    problems = kl.verify(out, registry=registry)
    for needle in ("sha256 differs", "render_input.jsonl does not match", "privacy_gate", "provenance", "pointed"):
        assert any(needle in p for p in problems), needle


# --- render join --------------------------------------------------------------------------------------------------


def _fake_render(render_dir: Path, rows: list[dict], *, bad_license_id=None, wrong_gt_id=None) -> None:
    render_dir.mkdir(parents=True)
    manifest = []
    for row in rows:
        png = render_dir / "lines" / f"{row['id']}.png"
        png.parent.mkdir(parents=True, exist_ok=True)
        Image.new("L", (60, 20), 255).save(png)
        gt = png.with_suffix(".gt.txt")
        gt.write_text(("אחר" if row["id"] == wrong_gt_id else row["text"]) + "\n", encoding="utf-8")
        # the hocrsyngen_line_render.v1 shape (hocrsyngen 90aa2bf, docs/line_render.md)
        manifest.append({"schema": "hocrsyngen_line_render.v1", "id": row["id"], "image": f"lines/{row['id']}.png",
                         "label": f"lines/{row['id']}.gt.txt", "font_id": "david-libre-regular",
                         "font": {"id": "david-libre-regular", "file": "DavidLibre-Regular.ttf", "sha256": "a" * 64,
                                  "license": "GPL-2.0" if row["id"] == bad_license_id else "OFL-1.1"},
                         "size_px": 28, "weight": None, "preset": "modern_print_scan_v1", "ink_band_px_otsu2pct": 31,
                         "synthetic": "rendered"})
    manifest.append({"id": "not-ours", "image": "lines/x.png", "font_id": "x", "license": "OFL-1.1"})
    (render_dir / "manifest.jsonl").write_text("".join(json.dumps(m, ensure_ascii=False) + "\n" for m in manifest), encoding="utf-8")


def test_join_render_writes_the_make_lstmf_shape_with_face_and_provenance(plenary: dict) -> None:
    out = plenary["out"]
    rows = _rows(out)
    render_dir = plenary["tmp"] / "render"
    _fake_render(render_dir, rows, bad_license_id=rows[0]["id"], wrong_gt_id=rows[1]["id"])
    result = kl.join_render(out, render_dir)
    assert result["rendered_rows"] == len(rows) - 2 and result["not_rendered"] == 2
    assert result["refused"] == {"unknown_id": 1, "font_license_not_open": 1, "gt_differs": 1}
    assert result["lines_per_face"] == {"david-libre-regular": len(rows) - 2}
    joined = [json.loads(line) for line in (out / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in joined:
        assert row["face"] == "david-libre-regular" and row["render"]["font_license"] == "OFL-1.1"
        assert row["render"]["preset"] == "modern_print_scan_v1" and row["render"]["ink_band_px_otsu2pct"] == 31
        assert row["render"]["font_sha256"] == "a" * 64 and row["render"]["synthetic"] == "rendered"
        assert row["image"] == f"train/{row['book']}/{row['id']}.png" and row["privacy_gate"] == PLENARY_GATE
        assert (out / row["image"]).with_suffix(".gt.txt").read_text(encoding="utf-8") == row["text"] + "\n"
    assert kl.verify(out, registry=plenary["registry"]) == []
    Image.new("L", (5, 5), 0).save(out / "train" / joined[0]["book"] / "stray.png")
    assert any("stray.png" in p for p in kl.verify(out, registry=plenary["registry"]))


def test_ner_windows_cover_the_text_with_overlap() -> None:
    text = " ".join(f"מילה{i}" for i in range(400))
    wins = list(ner_stream.windows(text, size=120, overlap=30))
    assert all(len(chunk) <= 120 and text[off:off + len(chunk)] == chunk for off, chunk in wins)
    assert wins[0][0] == 0 and wins[-1][0] + len(wins[-1][1]) == len(text)
    assert all(b[0] < a[0] + len(a[1]) for a, b in zip(wins, wins[1:]))  # consecutive windows overlap


def test_band_of_splits_units_about_evenly_and_is_stable() -> None:
    units = [f"plenary:K{k}_{s}" for k in range(13, 26) for s in range(1, 41)]
    counts = [sum(1 for u in units if kl.band_of(u) == i) for i in range(len(kl.RENDER_BANDS))]
    assert abs(counts[0] - counts[1]) < 0.15 * len(units) and kl.band_of(units[0]) == kl.band_of(units[0])
    assert kl.RENDER_BANDS[0] == (27, 34) and len(kl.RENDER_FONTS) == 9 and "david-libre-regular" in kl.RENDER_FONTS
