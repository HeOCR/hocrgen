"""Training-line text from born-digital Knesset protocols (DOC / DOCX), for rendering by hocrsyngen (operator tool).

Two series share one builder and differ only in their ``Series`` record:

- ``plenary``: the plenary record K13-25 (``knessetplenarylines_v1``), gate ``plenary_private_names_v1``, publishable;
- ``committee``: committee protocols K16-25 (``knessetcommitteelines_v1``), gate ``committee_private_names_v1``,
  training only (``committee_release_scope``), unit ids ``committee:K<k>_<session id>``.

Subcommands:

- ``plan`` ranks each term's units of an enumeration by ``sha256("heocr-knessetlines-v1:" + unit_id)`` and takes the
  first ``--per-term`` (default 8) that are not eval-reserved and have one protocol document. Eval and unassigned
  units are counted, never fetched.
- ``capture`` fetches the plan's documents: https knesset.gov.il hosts only, at most one request per
  ``CAPTURE_GAP_S`` s, the HeOCR user agent, stop at the first 403 / 429 / 473, challenge page or other failure; every
  request logged (``capture_log.jsonl``), every file pinned by sha256 (``capture_pins.json``).
- ``build`` turns each document into gated training-line text (below). ``render`` runs ``hocrsyngen render-lines`` on
  ``render_input.jsonl`` and joins its per-line manifest. ``verify`` checks a set at either stage.

Build, per unit (all guards fail closed):

1. **Eval reserve (decision 0017).** ``refuse_eval_reserved_training_input`` on the selected units and on the rows.
2. **Input.** The cache is untrusted: a document must match the sha256 its plan entry or capture pin gives and carry
   a Word signature (OLE or ZIP; K23+ serves OOXML under .doc names), and is copied into a per-run temp dir before ``soffice --convert-to txt``
   (UTF-8, a fresh profile) reads it. One paragraph per text line.
3. **Paragraphs.** The ``<< דובר >>``-style markers (hidden text in the document) are removed, a paragraph wrapped
   whole in ``<...>`` is unwrapped, format characters go, whitespace runs become one space. A paragraph that carried
   a speaker marker (``Series.speaker_markers``) is a structural speaker heading when it is one line ending in ":".
   Front matter (masthead, table of contents, agenda) is dropped: the body starts at the first speaker heading
   (``היו"ר ...:`` or a speaker marker); in a committee protocol the attendance block (``attendance_block``, cut at
   that first heading) is kept as lines flagged ``in_attendance_block`` and the gate drops them whole.
4. **Lines.** Each paragraph is wrapped at word boundaries into lines of at most ``W`` characters, ``W`` drawn per
   unit from ``WRAP_WIDTH`` by seed; joining a paragraph's lines with one space gives the paragraph back exactly.
   A line is dropped for a private-use / unmapped code point, niqqud (``pointed``), no letter or digit, a leftover
   marker, or any tier-A bidi or digit flag (``bidi_or_digit_flagged``: a wrapped line has no layout to verify).
5. **Privacy.** The NER tagger (``ner_stream.py`` in the heocr-ner venv) runs over ``stream_text`` of each unit's lines
   (committee: the lines outside the attendance block, the stream ``gate_committee_lines`` judges). Plenary:
   ``gate_stream_lines``. Committee: ``gate_committee_lines`` with ``session_denylist`` of the attendance entries and
   ``unproven_heading_names``. Dropped lines go only to ``--private-dir`` (default ``OUT/private``, never committed).
   ``refuse_ungated_plenary_lines`` / ``refuse_ungated_committee_lines`` run before anything is written.
6. **Dedup and caps.** At most ``MAX_LABEL_COPIES`` lines per identical text in the set, then
   ``--max-lines-per-unit``, both kept by sha256 of the line id.

Rows are synthetic (real text, rendered by HeOCR): ``capture: synthetic_render``, ``label_source:
born_digital_protocol_text``, ``reference_eligible: false``, ``eval_use: never``. Output: ``lines_text.jsonl``,
``render_input.jsonl`` (``{id, text, group}``), ``summary.json``; after ``render``, ``train/<unit>/<id>.png`` with a
logical-order ``.gt.txt`` each and ``manifest.jsonl`` (``face`` = the renderer's ``font_id``), the shape make_lstmf reads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hocrgen.config.models import EvalReservedUnitsRegistry
from hocrgen.privacy import committee_names, plenary_names
from hocrgen.privacy.plenary_names import GateResult, Roster, packaged_roster, stream_text
from hocrgen.privacy.training_only import PUBLISHABLE, committee_release_scope
from hocrgen.split.eval_reserved import (
    EvalReservedUnitError,
    packaged_registry,
    plenary_unit_id,
    refuse_eval_reserved_training_input,
    registry_provenance,
    unit_status,
)
from hocrgen.tools.reshumot_lines import ALNUM, BIDI_FLAGS, POINTS, TIER_A_ORIGIN, bad_code_points, cap_lines, sha256_bytes, tier_a_flags

SCHEMA = "knesset_lines.v1"
BUILDER = "knesset_lines build"
SEED_PREFIX = "heocr-knessetlines-v1:"
LABEL_SOURCE = "born_digital_protocol_text"
CAPTURE = "synthetic_render"
NODE_HINT = "new_printed"
DEFAULT_PER_TERM = 8
DEFAULT_MAX_LINES_PER_UNIT = 800
MAX_LABEL_COPIES = 3
WRAP_WIDTH = (40, 90)
CAPTURE_GAP_S = 3.0
CAPTURE_UA = "HeOCR-research/0.1 (+https://github.com/HeOCR)"
CAPTURE_MAX_BYTES = 64 * 1024 * 1024
BLOCK_STATUSES = frozenset({403, 429, 473})
KNESSET_HOST = re.compile(r"^(?:[a-z0-9-]+\.)*knesset\.gov\.il$")
MAGIC = {"doc": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "docx": b"PK\x03\x04"}
# The Knesset serves OOXML under a .doc name too (K23+): either Word signature is accepted for either extension.
WORD_SIGNATURES = tuple(MAGIC.values())
DEFAULT_SOFFICE = "/opt/homebrew/bin/soffice"
DEFAULT_NER_PYTHON = str(Path.home() / ".venvs" / "heocr-ner" / "bin" / "python")
NER_SCRIPT = Path(__file__).resolve().parent.parent / "privacy" / "ner_stream.py"
NER_TAGGER = "dicta-il/dictabert-ner over each unit's line stream (ner_stream.py) + cue heuristic"
HOCRSYNGEN_PIN = "32af108112afc51354e398239e7e6376b329b60a"  # HeOCR/hocrsyngen#100 (render-lines #99 + the 9 OFL faces)
DEFAULT_RENDER_CMD = "hocrsyngen render-lines"  # + --input/--output/--seed/--band-range/--preset/--font, set per band
RENDER_SEED = 20261113
RENDER_PRESET = "modern_print_scan_v1"
# lead 2026-11-13: half the units at the IA-like ink band (27-34 px, the R9 face-stats range), half at 35-48 px.
RENDER_BANDS: tuple[tuple[int, int], ...] = ((27, 34), (35, 48))
# The governed OFL faces of hocrsyngen 32af108 (maintainer approved the 6 google/fonts additions, 2026-11-13);
# more faces later are a re-render, not a rebuild (--font).
RENDER_FONTS: tuple[str, ...] = (
    "alef-regular", "assistant", "david-libre-regular", "frank-ruhl-libre", "heebo", "miriam-libre", "noto-sans-hebrew",
    "noto-serif-hebrew", "rubik",
)
# Weight drawn per unit and clipped to each variable face's axis (static faces keep their own weight).
RENDER_WEIGHTS: tuple[int, int] = (350, 600)
RENDER_LICENSES = frozenset({"OFL-1.1"})  # decision 0018 as amended 2026-11-13: open-licensed rendering fonts only

MARKER = re.compile(r"\s*<<\s*([^<>]*?)\s*>>\s*")
REMNANT = re.compile(r"<<|>>|[<>]")
CHAIR = re.compile(r'^(?:היו"ר|היו״ר|היושב[- ]ראש)\s')
HEADING_SHAPE = re.compile(r"^[^:\t]{2,80}:$")


# --- series ------------------------------------------------------------------------------------------------------


def committee_unit_id(knesset: int | str, session_id: int | str) -> str:
    """``committee:K<k>_<session id>``; never ``knesset_committee:<id>`` (the governed pre-1976 pattern)."""

    return f"committee:K{int(str(knesset))}_{int(str(session_id))}"


def _plenary_units(enumeration: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [{**u, "unit_id": plenary_unit_id(u["knesset"], u["sitting"])} for u in enumeration.get("units") or []
            if u.get("knesset") is not None and u.get("sitting") is not None]


def _committee_units(enumeration: Mapping[str, Any]) -> list[dict[str, Any]]:
    by_session: dict[Any, dict[str, Any]] = {}
    for doc in enumeration.get("documents") or []:
        sid, k = doc.get("committee_session_id"), doc.get("knesset")
        if sid is None or k is None:
            continue
        unit = by_session.setdefault(sid, {"unit_id": committee_unit_id(k, sid), "knesset": int(k), "sitting": int(sid),
                                           "date": doc.get("session_date"), "committee_id": doc.get("committee_id"),
                                           "committee_name": doc.get("committee_name"), "documents": []})
        unit["documents"].append(doc)
    return list(by_session.values())


def _plenary_protocol(doc: Mapping[str, Any]) -> bool:
    if "protocol_proper" in doc:
        return bool(doc["protocol_proper"])
    return doc.get("group_type") == "דברי הכנסת"


def _committee_protocol(doc: Mapping[str, Any]) -> bool:
    return "פרוטוקול" in str(doc.get("group_type") or "")


@dataclass(frozen=True)
class Series:
    """One protocol series. Everything that differs between plenary and committee lines is here."""

    key: str
    set_name: str
    source_id: str
    terms: tuple[int, ...]
    units: Callable[[Mapping[str, Any]], list[dict[str, Any]]]
    is_protocol: Callable[[Mapping[str, Any]], bool]
    speaker_markers: frozenset[str]
    gate: str  # "plenary" | "committee"
    gate_id: str
    license: str
    license_basis: str
    attribution: str
    training_only: bool

    def release_scope(self, unit: Mapping[str, Any]) -> str:
        return committee_release_scope(unit.get("date")) if self.gate == "committee" else PUBLISHABLE


PLENARY = Series(
    key="plenary", set_name="knessetplenarylines_v1", source_id="knesset_plenary_k13_25", terms=tuple(range(13, 26)),
    units=_plenary_units, is_protocol=_plenary_protocol,
    speaker_markers=frozenset({"דובר", "דובר_המשך", "יור", "קריאה"}), gate="plenary", gate_id=plenary_names.GATE_ID,
    license="PD-IL", license_basis="Copyright Act 2007 section 6: no copyright in Knesset proceedings (Divrei ha-Knesset)",
    attribution="Divrei ha-Knesset (דברי הכנסת), the plenary record of the Knesset", training_only=False,
)
COMMITTEE = Series(
    key="committee", set_name="knessetcommitteelines_v1", source_id="knesset_committee_protocols_k16plus",
    terms=tuple(range(16, 26)), units=_committee_units, is_protocol=_committee_protocol,
    speaker_markers=frozenset({"דובר", "דובר_המשך", "יור", "קריאה", "אורח"}), gate="committee",
    gate_id=committee_names.GATE_ID, license="training only (state copyright, 50 years from creation)",
    license_basis="planning/decisions/2026-11-11-knesset-protocols-training-vs-release.md: committee protocols from "
                  "1976 on are training input only, never released",
    attribution="Knesset committee protocols (פרוטוקולים של ועדות הכנסת)", training_only=True,
)
SERIES = {PLENARY.key: PLENARY, COMMITTEE.key: COMMITTEE}


def unit_slug(unit_id: str) -> str:
    return unit_id.split(":", 1)[1]


def rank_key(unit_id: str) -> str:
    return hashlib.sha256((SEED_PREFIX + unit_id).encode()).hexdigest()


def document_name(document: Mapping[str, Any]) -> str:
    """The cache file name: the URL's basename (``13_ptm_532022.docx``), checked to be a plain name."""

    name = Path(urllib.parse.urlparse(str(document["url"])).path).name
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", name) or name.startswith("."):
        raise ValueError(f"unsafe document name {name!r}")
    return name


def document_ext(document: Mapping[str, Any]) -> str:
    """``doc`` or ``docx``, from the URL (the enumeration's format says DOC for both)."""

    return str(document.get("file_ext") or Path(document_name(document)).suffix.lstrip(".")).lower()


# --- plan --------------------------------------------------------------------------------------------------------


def protocol_document(unit: Mapping[str, Any], series: Series) -> tuple[dict[str, Any] | None, str | None]:
    """The unit's protocol document (a DOC / DOCX the series calls a protocol; the lowest id), or why none."""

    docs = [d for d in unit.get("documents") or [] if series.is_protocol(d) and d.get("url")
            and str(d.get("format") or "").upper() in ("DOC", "DOCX") and document_ext(d) in MAGIC]
    if not docs:
        return None, "no_protocol_document"
    return dict(min(docs, key=lambda d: int(d["document_id"]))), None


def _status(unit_id: str, registry: EvalReservedUnitsRegistry) -> str:
    found = unit_status({"unit_id": unit_id}, registry)
    return found[1].value if found else "not_governed"


OPEN_STATUSES = ("non_eval", "not_governed")


def plan_units(enumeration: Mapping[str, Any], series: Series, *, per_term: int = DEFAULT_PER_TERM,
               registry: EvalReservedUnitsRegistry | None = None) -> dict[str, Any]:
    """Per term, the first ``per_term`` units by ``rank_key`` that are not eval-reserved and have a protocol document."""

    registry = registry or packaged_registry()
    by_term: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for unit in series.units(enumeration):
        if unit["knesset"] in series.terms:
            by_term[int(unit["knesset"])].append(unit)
    selected, skipped = [], {}
    for term in sorted(by_term):
        counts: Counter = Counter()
        taken = 0
        for unit in sorted(by_term[term], key=lambda u: rank_key(u["unit_id"])):
            if taken >= per_term:
                break
            status = _status(unit["unit_id"], registry)
            if status not in OPEN_STATUSES:
                counts[status] += 1
                continue
            doc, why = protocol_document(unit, series)
            if doc is None:
                counts[str(why)] += 1
                continue
            keys = ("unit_id", "knesset", "sitting", "date", "committee_id", "committee_name", "plenum_session_id")
            selected.append({k: unit[k] for k in keys if unit.get(k) is not None}
                            | {"rank_key": rank_key(unit["unit_id"]), "eval_status": status, "document": doc})
            taken += 1
        skipped[str(term)] = dict(counts)
    refuse_eval_reserved_training_input(selected, builder=f"knesset_lines plan ({series.key})", registry=registry)
    return {"schema": "knesset_lines_plan.v1", "series": series.key, "per_term": per_term,
            "method": f"per term, units ranked by sha256('{SEED_PREFIX}' + unit_id) ascending; the first {per_term} that "
                      "are not eval-reserved and have a protocol document", "registry": registry_provenance(registry),
            "skipped_before_selection": skipped, "units": selected}


# --- capture -----------------------------------------------------------------------------------------------------


class CaptureStopped(RuntimeError):
    """A request was refused, challenged or failed: capture stops."""


def _is_challenge(body: bytes) -> bool:
    low = body[:4000].lower()
    return b"access denied" in low or (b"<html" in low and (b"challenge" in low or b"captcha" in low))


def capture(plan: Mapping[str, Any], cache: Path, *, opener: Callable[..., Any] = urllib.request.urlopen,
            sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic,
            gap: float = CAPTURE_GAP_S) -> dict[str, Any]:
    """Fetch every planned document not yet pinned; returns the pins. Raises ``CaptureStopped`` on any failure."""

    cache.mkdir(parents=True, exist_ok=True)
    pins_path, log_path = cache / "capture_pins.json", cache / "capture_log.jsonl"
    pins = json.loads(pins_path.read_text(encoding="utf-8")) if pins_path.is_file() else {}
    last: list[float | None] = [None]
    for unit in plan.get("units") or []:
        doc = unit["document"]
        name = document_name(doc)
        target = cache / name
        if name in pins and target.is_file() and sha256_bytes(target.read_bytes()) == pins[name]["sha256"]:
            continue
        url = str(doc["url"])
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or not KNESSET_HOST.match(parsed.hostname or ""):
            raise CaptureStopped(f"{unit['unit_id']}: refusing a URL outside https://*.knesset.gov.il: {url}")
        if last[0] is not None and clock() - last[0] < gap:
            sleep(gap - (clock() - last[0]))
        status, body, error = None, b"", None
        try:
            with opener(urllib.request.Request(url, headers={"User-Agent": CAPTURE_UA}), timeout=120) as response:
                status = response.status
                body = response.read(CAPTURE_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            status, body = exc.code, exc.read()[:4000]
        except Exception as exc:  # noqa: BLE001 - every failure stops capture
            status, error = -1, repr(exc)
        last[0] = clock()
        blocked = status in BLOCK_STATUSES or _is_challenge(body)
        bad_magic = status == 200 and not blocked and not (document_ext(doc) in MAGIC and body.startswith(WORD_SIGNATURES))
        entry = {"t": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "unit_id": unit["unit_id"], "url": url, "status": status,
                 "bytes": len(body), "blocked": blocked, "bad_magic": bad_magic, "error": error}
        with log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if blocked or status != 200 or bad_magic or len(body) > CAPTURE_MAX_BYTES:
            raise CaptureStopped(f"stopped at {url}: status {status}, blocked {blocked}, bad signature {bad_magic}")
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(body)
        tmp.replace(target)
        pins[name] = {"sha256": sha256_bytes(body), "bytes": len(body), "url": url, "unit_id": unit["unit_id"],
                      "document_id": doc.get("document_id"), "fetched_at": entry["t"]}
        pins_path.write_text(json.dumps(pins, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return pins


def check_document(unit: Mapping[str, Any], cache: Path, pins: Mapping[str, Any]) -> tuple[Path | None, str | None, str | None]:
    """The cached document if it matches its pin and its extension's signature: (path, sha256, refusal)."""

    doc = unit["document"]
    name = document_name(doc)
    path = cache / name
    expected = doc.get("sha256") or (pins.get(name) or {}).get("sha256")
    if not expected:
        return None, None, "unpinned"
    if path.is_symlink() or not path.is_file():
        return None, expected, "document_missing"
    data = path.read_bytes()
    if sha256_bytes(data) != expected:
        return None, expected, "sha256_mismatch"
    if document_ext(doc) not in MAGIC or not data.startswith(WORD_SIGNATURES):
        return None, expected, "bad_signature"
    return path, expected, None


# --- text --------------------------------------------------------------------------------------------------------


def soffice_version(soffice: str) -> str:  # pragma: no cover - soffice
    out = subprocess.run([soffice, "--version"], capture_output=True, text=True, timeout=120).stdout.split()
    return out[1] if len(out) > 1 else "unknown"


def soffice_text(soffice: str) -> Callable[[Path, Path], str]:  # pragma: no cover - soffice
    """``soffice --convert-to txt`` (UTF-8) of a copy of the document, in a fresh profile under ``workdir``."""

    def to_text(document: Path, workdir: Path) -> str:
        local = workdir / "in" / document.name
        local.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(document, local)
        profile = (workdir / "profile").resolve()
        subprocess.run([soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore", "--convert-to",
                        "txt:Text (encoded):UTF8", "--outdir", str(workdir / "txt"), str(local)],
                       check=True, capture_output=True, timeout=900)
        return (workdir / "txt" / (local.stem + ".txt")).read_text(encoding="utf-8")

    return to_text


def clean_paragraph(raw: str) -> tuple[str, set[str]]:
    """The paragraph's visible text and the markers it carried."""

    marks = {m.strip() for m in MARKER.findall(raw)}
    text = MARKER.sub(" ", raw)
    text = re.sub(r"<<[^<>]*$", "", re.sub(r"^[^<>]*>>", "", text))  # a marker cut at the paragraph edge
    text = "".join(ch for ch in unicodedata.normalize("NFC", text) if unicodedata.category(ch) != "Cf")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > 2 and text[0] == "<" and text[-1] == ">" and "<" not in text[1:-1] and ">" not in text[1:-1]:
        text = text[1:-1].strip()
    return text, marks


def parse_paragraphs(text: str, series: Series) -> list[dict[str, Any]]:
    """One record per non-empty paragraph: index, visible text, the raw text (tabs kept) and the heading flags."""

    out = []
    for index, raw in enumerate(text.lstrip("﻿").split("\n")):
        clean, marks = clean_paragraph(raw)
        if not clean:
            continue
        heading_shape = bool(HEADING_SHAPE.match(clean))
        out.append({"index": index, "text": clean, "raw": MARKER.sub(" ", raw).strip(),
                    "structural": heading_shape and bool(marks & series.speaker_markers),
                    "heading_shape": heading_shape, "chair": heading_shape and bool(CHAIR.match(clean))})
    return out


def body_start(paragraphs: Sequence[Mapping[str, Any]]) -> int | None:
    """The first speaker heading: a chair heading or a paragraph that carried a speaker marker."""

    return next((i for i, p in enumerate(paragraphs) if p["chair"] or p["structural"]), None)


def wrap_width(unit_id: str) -> int:
    return random.Random(SEED_PREFIX + "wrap:" + unit_id).randint(*WRAP_WIDTH)


def wrap(text: str, width: int) -> list[str]:
    """Greedy word wrap at single spaces; ``" ".join(wrap(text, w)) == text`` for a whitespace-collapsed text."""

    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        if current and len(current) + 1 + len(word) > width:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines


def text_drop_reason(text: str) -> tuple[str | None, list[str]]:
    flags = tier_a_flags(text)
    if bad_code_points(text) or "pua_or_replacement" in flags:
        return "unmapped_or_private_glyph", flags
    if POINTS.search(unicodedata.normalize("NFD", text)):
        return "pointed", flags
    if not ALNUM.search(text):
        return "no_letters_or_digits", flags
    if REMNANT.search(text):
        return "marker_remnant", flags
    if BIDI_FLAGS & set(flags):
        return "bidi_or_digit_flagged", flags
    return None, flags


_ATTENDANCE_HEAD = re.compile(r"^\s*<?([^:<>\t]{2,40}):\s*>?\s*(.*)$")


def attendance_entries(raws: Iterable[str]) -> list[str]:
    """Attendance entries for ``session_denylist``: a list heading on the entry's own line ("מוזמנים:<tab>name – org")
    is cut off, so the entry's name, not the heading, gives the surname; a heading alone gives no entry."""

    out = []
    for raw in raws:
        match = _ATTENDANCE_HEAD.match(raw)
        if match and committee_names.ATTENDANCE_OPEN.match(match.group(1)):
            raw = match.group(2)
        if raw.strip():
            out.append(raw.strip())
    return out


def unit_lines(unit: Mapping[str, Any], text: str, series: Series) -> dict[str, Any]:
    """The unit's physical lines in reading order (front matter dropped), with drops, flags and the attendance block."""

    paragraphs = parse_paragraphs(text, series)
    start = body_start(paragraphs)
    if start is None:
        return {"refused": "no_body_start", "lines": [], "paragraphs": len(paragraphs)}
    block: tuple[int, int] | None = None
    attendance_raw: list[str] = []
    if series.gate == "committee":
        found = committee_names.attendance_block([p["raw"] for p in paragraphs])
        if found is not None and found[0] < start:
            block = (found[0], min(found[1], start))  # the block never runs past the first speaker heading
            attendance_raw = attendance_entries(p["raw"] for p in paragraphs[block[0]:block[1]])
            start = block[0]
    width = wrap_width(unit["unit_id"])
    slug = unit_slug(unit["unit_id"])
    lines = []
    for pos, para in enumerate(paragraphs[start:], start=start):
        pieces = wrap(para["text"], width)
        for li, piece in enumerate(pieces):
            drop, flags = text_drop_reason(piece)
            line = {"id": f"{slug}_p{para['index']:05d}_l{li:02d}", "paragraph_index": para["index"], "line_index": li,
                    "text": piece, "drop": drop, "tier_a_flags": flags}
            if len(pieces) == 1 and (para["structural"] or (series.gate == "committee" and para["heading_shape"])):
                line["is_speaker_heading"] = True  # committee: only feeds unproven_heading_names (no proof there)
            if block is not None and block[0] <= pos < block[1]:
                line["in_attendance_block"] = True
            lines.append(line)
    return {"refused": None, "lines": lines, "paragraphs": len(paragraphs), "front_matter_paragraphs": start,
            "attendance_block_paragraphs": (block[1] - block[0]) if block else 0, "attendance_raw": attendance_raw,
            "wrap_width": width, "structural_headings": sum(1 for p in paragraphs if p["structural"])}


# --- NER and the gate --------------------------------------------------------------------------------------------


NerFn = Callable[[Sequence[Mapping[str, str]]], dict[str, list[dict[str, Any]]]]


def subprocess_ner(python: str = DEFAULT_NER_PYTHON, script: Path = NER_SCRIPT) -> NerFn:  # pragma: no cover - venv
    """``ner_stream.py`` in the NER venv over JSONL ``{id, text}``: spans per id, in stream coordinates."""

    def ner(streams: Sequence[Mapping[str, str]]) -> dict[str, list[dict[str, Any]]]:
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "in.jsonl", Path(tmp) / "out.jsonl"
            src.write_text("".join(json.dumps(dict(s), ensure_ascii=False) + "\n" for s in streams), encoding="utf-8")
            env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}  # the cached model only
            subprocess.run([python, "-I", str(script), str(src), str(dst)], check=True, capture_output=True, timeout=14400, env=env)
            return {row["id"]: row["person_spans"] for row in map(json.loads, dst.read_text(encoding="utf-8").splitlines())}

    return ner


def gate_input(unit: Mapping[str, Any], lines: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """The gate's line dicts and the exact text the tagger must see (committee: outside the attendance block)."""

    gl = []
    for line in lines:
        row = {"line_id": line["id"], "unit_id": unit["unit_id"], "knesset": unit["knesset"], "text": line["text"]}
        for key in ("is_speaker_heading", "in_attendance_block"):
            if line.get(key):
                row[key] = True
        gl.append(row)
    return gl, stream_text([row for row in gl if not row.get("in_attendance_block")])[0]


def gate_unit(series: Series, unit: Mapping[str, Any], gl: Sequence[Mapping[str, Any]], spans: Any, roster: Roster,
              attendance_raw: Sequence[str] = ()) -> tuple[GateResult, list[str]]:
    """One unit's gate verdict (and, for committee, its denylist)."""

    if series.gate == "plenary":
        return plenary_names.gate_stream_lines(gl, spans, roster), []
    names = list(attendance_raw) + committee_names.unproven_heading_names(gl, roster)
    deny = committee_names.session_denylist(names, roster, int(unit["knesset"]))
    return committee_names.gate_committee_lines(gl, spans, roster, denylist=deny), sorted(deny)


def gate_summary(series: Series, result: GateResult, roster: Roster) -> dict[str, Any]:
    if series.gate == "committee":
        return committee_names.summary(result, roster, NER_TAGGER)
    return result.summary(roster, NER_TAGGER)


def refuse_ungated(series: Series, rows: Sequence[Mapping[str, Any]], builder: str) -> None:
    plenary_names.refuse_ungated_plenary_lines(rows, builder=builder)
    committee_names.refuse_ungated_committee_lines(rows, builder=builder)
    wrong = [row["id"] for row in rows if row.get("privacy_gate") != series.gate_id]
    if wrong:
        raise ValueError(f"{builder}: {len(wrong)} row(s) without privacy_gate={series.gate_id!r}: {wrong[:5]}")


def dedup_rows(rows: Sequence[Mapping[str, Any]], max_copies: int = MAX_LABEL_COPIES) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """At most ``max_copies`` rows per identical text (kept by sha256 of the id), in their original order."""

    by_text: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        by_text[row["text"]].append(row["id"])
    keep: set[str] = set()
    for ids in by_text.values():
        keep.update(sorted(ids, key=lambda value: sha256_bytes(value.encode()))[:max_copies])
    kept = [dict(row) for row in rows if row["id"] in keep]
    return kept, {"max_copies": max_copies, "rows_in": len(rows), "rows_removed": len(rows) - len(kept),
                  "labels_over_cap": sum(1 for ids in by_text.values() if len(ids) > max_copies),
                  "distinct_labels": len(by_text)}


DROP_DEFINITIONS = {
    "unit_refused:<reason>": "units refused (pin, signature, text conversion, no body start), counted in units",
    "unmapped_or_private_glyph": "lines with a private-use, replacement, unassigned or (cid:N) code point",
    "pointed": "lines carrying any niqqud or cantillation mark",
    "no_letters_or_digits": "lines without a letter or digit",
    "marker_remnant": "lines still carrying a < or > after the document's markers were removed",
    "bidi_or_digit_flagged": "lines with a tier-A bidi or digit flag (compound_number, latin, bracket_order_or_balance)",
    "privacy_gate": "lines the private-name gate drops that no text rule dropped (all gate counts: privacy_gate)",
    "dedup": "lines over the identical-text cap", "unit_cap": "lines over the per-unit cap",
}


# --- build -------------------------------------------------------------------------------------------------------


def make_row(series: Series, unit: Mapping[str, Any], record: Mapping[str, Any], line: Mapping[str, Any],
             gate: Mapping[str, Any], width: int) -> dict[str, Any]:
    doc = unit["document"]
    row = {
        "id": line["id"], "split": "train", "book": unit_slug(unit["unit_id"]), "unit_id": unit["unit_id"],
        "source_id": series.source_id, "series": series.set_name, "knesset": unit["knesset"], "sitting": unit["sitting"],
        "date": unit.get("date"), "document_id": doc.get("document_id"), "document_url": doc.get("url"),
        "document_sha256": record.get("document_sha256"), "paragraph_index": line["paragraph_index"],
        "line_index": line["line_index"], "text": line["text"], "wrap_width": width, "stratum": "unpointed",
        "label_source": LABEL_SOURCE, "label_tier": "silver", "adjudication_status": "not_adjudicated",
        "reference_eligible": False, "eval_use": "never", "capture": CAPTURE, "proposed_node_hint": NODE_HINT,
        "tier_a_flags": line["tier_a_flags"], "is_speaker_heading": bool(line.get("is_speaker_heading")),
        "privacy_gate": gate["privacy_gate"], "privacy_note": gate.get("privacy_note"),
        "release_scope": series.release_scope(unit), "training_only": series.training_only,
        "license": series.license, "attribution": series.attribution,
    }
    if series.gate == "committee":
        row.update(session_date=unit.get("date"), committee_id=unit.get("committee_id"), committee_name=unit.get("committee_name"))
    return row


def build(args: argparse.Namespace, *, registry: EvalReservedUnitsRegistry | None = None,
          to_text: Callable[[Path, Path], str] | None = None, ner: NerFn | None = None,
          roster: Roster | None = None) -> dict[str, Any]:
    out = Path(args.out)
    if out.exists():
        raise SystemExit(f"{out} exists")
    series = SERIES[args.series]
    registry = registry or packaged_registry()
    roster = roster or packaged_roster()
    version = getattr(args, "soffice_version", None)
    if to_text is None:  # pragma: no cover - operator runs
        to_text = soffice_text(args.soffice)
        version = soffice_version(args.soffice)
    ner = ner or subprocess_ner(args.ner_python)  # pragma: no cover - default only on operator runs
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    if plan.get("series", series.key) != series.key:
        raise SystemExit(f"plan is for series {plan.get('series')}, not {series.key}")
    cache = Path(args.cache)
    pins_path = cache / "capture_pins.json"
    pins = json.loads(pins_path.read_text(encoding="utf-8")) if pins_path.is_file() else {}

    # Guard 1: units that are not eval-reserved, decided from the plan alone; others are counted and never opened.
    units, skipped = [], Counter()
    for unit in plan.get("units") or []:
        status = _status(unit["unit_id"], registry)
        if unit.get("knesset") not in series.terms:
            skipped["outside_series_terms"] += 1
        elif status in OPEN_STATUSES:
            units.append(unit)
        else:
            skipped[status] += 1
    refuse_eval_reserved_training_input([{"unit_id": u["unit_id"]} for u in units], builder=BUILDER, registry=registry)

    drops: Counter = Counter()
    drops_by_term: dict[str, Counter] = defaultdict(Counter)
    records: dict[str, dict[str, Any]] = {}
    prepared: list[tuple[dict[str, Any], dict[str, Any]]] = []
    tmp_root = Path(tempfile.mkdtemp(prefix="knesset_lines_"))
    try:
        for unit in sorted(units, key=lambda u: (u["knesset"], u["sitting"])):
            term = str(unit["knesset"])
            started = time.monotonic()
            document, sha, refused = check_document(unit, cache, pins)
            record: dict[str, Any] = {"knesset": unit["knesset"], "sitting": unit["sitting"], "date": unit.get("date"),
                                      "document": unit["document"], "document_sha256": sha}
            if refused is None and document is not None:
                try:
                    lines = unit_lines(unit, to_text(document, tmp_root / unit_slug(unit["unit_id"])), series)
                except (subprocess.SubprocessError, OSError, UnicodeDecodeError) as exc:
                    lines = {"refused": f"text_conversion_failed:{type(exc).__name__}", "lines": []}
                refused = lines["refused"]
                record.update({k: v for k, v in lines.items() if k not in ("lines", "attendance_raw", "refused")})
                if not refused:
                    prepared.append((unit, lines))
            record["seconds"] = round(time.monotonic() - started, 1)
            record["refused"] = refused
            if refused:
                drops[f"unit_refused:{refused}"] += 1
                drops_by_term[term][f"unit_refused:{refused}"] += 1
            records[unit["unit_id"]] = record
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    # Guard 5: the tagger over each unit's stream, then the series gate over every line.
    inputs = {unit["unit_id"]: gate_input(unit, lines["lines"]) for unit, lines in prepared}
    ner_started = time.monotonic()
    spans = ner([{"id": unit_id, "text": stream} for unit_id, (_, stream) in inputs.items()]) if inputs else {}
    ner_seconds = round(time.monotonic() - ner_started, 1)
    merged = GateResult()
    gate_by_term: dict[str, Counter] = defaultdict(Counter)
    candidates, private_rows = [], []
    for unit, lines in prepared:
        term = str(unit["knesset"])
        gl, _ = inputs[unit["unit_id"]]
        result, deny = gate_unit(series, unit, gl, spans.get(unit["unit_id"]), roster, lines.get("attendance_raw") or ())
        records[unit["unit_id"]]["session_denylist_size"] = len(deny) if series.gate == "committee" else None
        merged.kept += result.kept
        merged.dropped += result.dropped
        merged.reasons.update(result.reasons)
        verdict = {row["line_id"]: row for row in result.kept}
        dropped = {row["line_id"]: row["privacy_drop"] for row in result.dropped}
        for reason, n in result.reasons.items():
            gate_by_term[term][reason] += n
        gate_by_term[term]["lines_kept"] += len(result.kept)
        gate_by_term[term]["lines_dropped"] += len(result.dropped)
        for line in lines["lines"]:
            if line["id"] in dropped:
                private_rows.append({"id": line["id"], "unit_id": unit["unit_id"], "text": line["text"],
                                     "privacy_drop": dropped[line["id"]], "text_drop": line["drop"]})
            if line["drop"]:
                drops[line["drop"]] += 1
                drops_by_term[term][line["drop"]] += 1
            elif line["id"] in dropped or line["id"] not in verdict:
                drops["privacy_gate"] += 1
                drops_by_term[term]["privacy_gate"] += 1
            else:
                candidates.append(make_row(series, unit, records[unit["unit_id"]], line, verdict[line["id"]], lines["wrap_width"]))

    # Guard 6: exact dedup across the set, then the per-unit cap.
    # Training-only text (committee protocols from 1976 on): exact duplicates removed, one copy (decision
    # 2026-11-11, safeguard 3).
    copies = 1 if series.training_only else args.max_label_copies
    rows, dedup = dedup_rows(candidates, copies)
    drops["dedup"] += dedup["rows_removed"]
    by_unit: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_unit[row["unit_id"]].append(row)
    rows, capped = [], {}
    for unit_id in sorted(by_unit):
        keep = set(cap_lines([row["id"] for row in by_unit[unit_id]], args.max_lines_per_unit))
        if len(keep) < len(by_unit[unit_id]):
            capped[unit_id] = len(by_unit[unit_id]) - len(keep)
            drops["unit_cap"] += capped[unit_id]
        rows += [row for row in by_unit[unit_id] if row["id"] in keep]

    # Guards 1 and 5 again, on the rows, before anything is written.
    refuse_eval_reserved_training_input(rows, builder=BUILDER, registry=registry)
    refuse_ungated(series, rows, BUILDER)

    out.mkdir(parents=True)
    private_dir = Path(args.private_dir) if getattr(args, "private_dir", None) else out / "private"
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "gate_dropped.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in private_rows),
                                                    encoding="utf-8")
    lines_path = out / "lines_text.jsonl"
    lines_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    render_input = out / "render_input.jsonl"
    render_input.write_text("".join(json.dumps({"id": r["id"], "text": r["text"], "group": r["unit_id"]}, ensure_ascii=False) + "\n"
                                    for r in rows), encoding="utf-8")
    per_term, per_unit, scopes = Counter(), Counter(), Counter()
    for row in rows:
        per_term[str(row["knesset"])] += 1
        per_unit[row["unit_id"]] += 1
        scopes[row["release_scope"]] += 1
    for unit_id, record in records.items():
        record["lines"] = per_unit.get(unit_id, 0)
    status_counts = Counter(_status(row["unit_id"], registry) for row in rows)
    gate = gate_summary(series, merged, roster)
    gate["per_term"] = {t: dict(sorted(c.items())) for t, c in sorted(gate_by_term.items(), key=lambda kv: int(kv[0]))}
    gate["dropped_line_details"] = "private dir only; never commit or publish it"
    gate["ner_seconds"] = ner_seconds
    by_term = lambda c: {t: dict(sorted(v.items())) for t, v in sorted(c.items(), key=lambda kv: int(kv[0]))}  # noqa: E731
    summary: dict[str, Any] = {
        "schema": SCHEMA, "series": series.set_name, "series_key": series.key, "source_id": series.source_id,
        "stage": "text", "label_source": LABEL_SOURCE, "capture": CAPTURE, "reference_eligible": False, "eval_use": "never",
        "labels": "the protocol document's own text, wrapped into lines by HeOCR, to be rendered by hocrsyngen in "
                  "open-licensed fonts: synthetic (real text, rendered) training lines, never evaluation references",
        "proposed_node_hint": NODE_HINT, "license": series.license, "license_basis": series.license_basis,
        "attribution": series.attribution, "training_only": series.training_only, "release_scope": dict(scopes),
        "totals": {"lines": len(rows), "units": len(prepared)},
        "lines_per_term": dict(sorted(per_term.items(), key=lambda kv: int(kv[0]))),
        "lines_per_unit": dict(sorted(per_unit.items())), "dropped": dict(sorted(drops.items())),
        "dropped_per_term": by_term(drops_by_term), "dropped_definitions": DROP_DEFINITIONS, "dedup": dedup,
        "max_lines_per_unit": args.max_lines_per_unit, "capped_lines": capped, "privacy_gate": gate,
        "wrap": {"width_range": list(WRAP_WIDTH), "rule": "greedy at single spaces; width per unit from "
                 f"random.Random('{SEED_PREFIX}wrap:' + unit_id)"},
        "units": dict(sorted(records.items())), "soffice_version": version,
        "input_pins": {u: {"document": r["document"].get("url"), "sha256": r.get("document_sha256")} for u, r in sorted(records.items())},
        "plan": {"path": str(Path(args.plan).resolve()), "sha256": sha256_bytes(Path(args.plan).read_bytes()), "method": plan.get("method")},
        "eval_reserved_check": {
            "decision": "heocr-engine decision 0017", "registry": registry_provenance(registry),
            "input_units": {"open": len(units), **dict(skipped)},
            "guard": "refuse_eval_reserved_training_input on the selected units and on the rows; both passed",
            "output_rows_by_status": dict(status_counts), "eval_rows": status_counts.get("eval", 0),
            "unassigned_rows": status_counts.get("unassigned", 0),
        },
        "tier_a_rules": {**TIER_A_ORIGIN, "bidi_or_digit_flags": sorted(BIDI_FLAGS), "rule": "any flagged line is dropped"},
        "lines_text_sha256": sha256_bytes(lines_path.read_bytes()), "render_input_sha256": sha256_bytes(render_input.read_bytes()),
    }
    for key in ("created_at", "signature"):
        if getattr(args, key, None):
            summary[key] = getattr(args, key)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


# --- render (hocrsyngen render-lines) and join -------------------------------------------------------------------


def _field(row: Mapping[str, Any], *names: str) -> Any:
    return next((row[n] for n in names if row.get(n) not in (None, "")), None)


def join_render(out: Path, render_dir: Path, *, licenses: frozenset[str] = RENDER_LICENSES) -> dict[str, Any]:
    """Join ``render_dir/manifest.jsonl`` (one row per rendered line) onto ``lines_text.jsonl``.

    Writes ``train/<unit>/<id>.png`` and a logical-order ``.gt.txt`` (our text) per line and ``manifest.jsonl``
    (the text row plus ``face`` = ``font_id`` and the render provenance). A rendered row is refused when its id is not
    ours, its font licence is not open, its image is outside ``render_dir`` or missing, or its gt text differs.
    """

    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in map(json.loads, (out / "lines_text.jsonl").read_text(encoding="utf-8").splitlines())}
    root = render_dir.resolve()
    joined, problems = [], Counter()
    for rendered in map(json.loads, (render_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()):
        row = rows.get(str(rendered.get("id")))
        if row is None:
            problems["unknown_id"] += 1
            continue
        font = rendered.get("font") if isinstance(rendered.get("font"), Mapping) else {}
        license_ = _field(font, "license") or _field(rendered, "license", "licence", "font_license", "font_licence")
        if license_ not in licenses:
            problems["font_license_not_open"] += 1
            continue
        image = (render_dir / str(_field(rendered, "image", "png", "path") or "")).resolve()
        if root not in image.parents or not image.is_file() or image.suffix != ".png":
            problems["image_missing_or_outside"] += 1
            continue
        gt_text = _field(rendered, "text", "gt_text")
        gt_file = _field(rendered, "label", "gt", "gt_path")
        if gt_text is None and gt_file:
            gt_path = (render_dir / str(gt_file)).resolve()
            gt_text = gt_path.read_text(encoding="utf-8").rstrip("\n") if root in gt_path.parents and gt_path.is_file() else ""
        if gt_text is not None and unicodedata.normalize("NFC", str(gt_text)) != row["text"]:
            problems["gt_differs"] += 1
            continue
        target = out / "train" / row["book"] / f"{row['id']}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target)
        target.with_suffix(".gt.txt").write_text(row["text"] + "\n", encoding="utf-8")
        provenance = {k: rendered.get(k) for k in (
            "schema", "size_px", "size_mode", "target_band_px", "band_def", "weight", "preset", "preset_params",
            "ink_band_px_otsu2pct", "ink_band_frac_otsu2pct", "ink_band_px", "dark_density", "seed", "line_seed",
            "style_seed", "synthetic", "width", "height") if k in rendered}
        joined.append({**row, "face": _field(rendered, "font_id", "font"), "image": f"train/{row['book']}/{row['id']}.png",
                       "image_sha256": sha256_bytes(target.read_bytes()),
                       "render": {"renderer": "hocrsyngen render-lines", "font_id": rendered.get("font_id"),
                                  "font_sha256": _field(font, "sha256") or _field(rendered, "font_sha256", "font_file_sha256"),
                                  "font_file": font.get("file"), "font_license": license_,
                                  **provenance}})
    refuse_ungated(SERIES[summary["series_key"]], joined, "knesset_lines render")
    manifest = out / "manifest.jsonl"
    manifest.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in joined), encoding="utf-8")
    faces = Counter(row["face"] for row in joined)
    fonts = sorted({(r["render"]["font_id"] or "", r["render"]["font_sha256"] or "", r["render"]["font_license"] or "") for r in joined})
    summary.update(stage="rendered", render={
        "render_dir": str(root), "manifest_in_sha256": sha256_bytes((render_dir / "manifest.jsonl").read_bytes()),
        "rendered_rows": len(joined), "not_rendered": len(rows) - len(joined), "refused": dict(problems),
        "lines_per_face": dict(sorted(faces.items())), "allowed_font_licenses": sorted(licenses),
        "fonts": [{"font_id": f, "sha256": s, "license": lic} for f, s, lic in fonts],
        "manifest_sha256": sha256_bytes(manifest.read_bytes())})
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary["render"]


def band_of(group: str, bands: Sequence[tuple[int, int]] = RENDER_BANDS) -> int:
    """The band index of a unit: sha256("heocr-knessetlines-band:" + unit id), so each band gets about an equal share."""

    return int(hashlib.sha256(f"heocr-knessetlines-band:{group}".encode()).hexdigest(), 16) % len(bands)


def render(out: Path, render_dir: Path, command: str = DEFAULT_RENDER_CMD, *, fonts: Sequence[str] = RENDER_FONTS,
           bands: Sequence[tuple[int, int]] = RENDER_BANDS, seed: int = RENDER_SEED,
           preset: str = RENDER_PRESET, weights: tuple[int, int] = RENDER_WEIGHTS) -> dict[str, Any]:  # pragma: no cover
    """Run ``hocrsyngen render-lines`` (pinned at ``HOCRSYNGEN_PIN``) once per ink band on that band's units, merge the
    manifests into ``render_dir/manifest.jsonl`` and join it."""

    inputs = [json.loads(line) for line in (out / "render_input.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    render_dir.mkdir(parents=True, exist_ok=True)
    merged = []
    for index, (low, high) in enumerate(bands):
        part = [row for row in inputs if band_of(str(row["group"]), bands) == index]
        if not part:
            continue
        sub_dir = render_dir / f"band{index}_{low}_{high}"
        part_input = render_dir / f"input_band{index}.jsonl"
        part_input.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in part), encoding="utf-8")
        args = shlex.split(command) + ["--input", str(part_input), "--output", str(sub_dir), "--seed", str(seed),
                                       "--band-range", str(low), str(high), "--preset", preset,
                                       "--weight-range", str(weights[0]), str(weights[1])]
        for font in fonts:
            args += ["--font", font]
        subprocess.run(args, check=True)
        for row in map(json.loads, (sub_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()):
            for key in ("image", "label"):
                if row.get(key):
                    row[key] = f"{sub_dir.name}/{row[key]}"
            merged.append(row)
    (render_dir / "manifest.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in merged), encoding="utf-8")
    result = join_render(out, render_dir)
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    summary["render"]["config"] = {"hocrsyngen_pin": HOCRSYNGEN_PIN, "command": command, "fonts": list(fonts),
                                   "bands": [list(b) for b in bands], "band_rule": "sha256('heocr-knessetlines-band:'+unit_id) mod bands",
                                   "seed": seed, "preset": preset, "weight_range": list(weights)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


# --- verify ------------------------------------------------------------------------------------------------------


def verify(out: Path, *, registry: EvalReservedUnitsRegistry | None = None) -> list[str]:
    """Problems in a built set, at the text stage or after ``render`` (empty when it passes)."""

    registry = registry or packaged_registry()
    summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    series = SERIES[summary["series_key"]]
    rows = [json.loads(line) for line in (out / "lines_text.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    problems = []
    if sha256_bytes((out / "lines_text.jsonl").read_bytes()) != summary["lines_text_sha256"]:
        problems.append("lines_text.jsonl sha256 differs from summary")
    inputs = [json.loads(line) for line in (out / "render_input.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if [(r["id"], r["text"], r["group"]) for r in inputs] != [(r["id"], r["text"], r["unit_id"]) for r in rows]:
        problems.append("render_input.jsonl does not match lines_text.jsonl")
    try:
        refuse_eval_reserved_training_input(rows, builder="knesset_lines verify", registry=registry)
    except EvalReservedUnitError as exc:
        problems.append(f"eval: {exc}")
    try:
        refuse_ungated(series, rows, "knesset_lines verify")
    except ValueError as exc:
        problems.append(f"gate: {exc}")
    problems += [f"duplicate id {i}" for i, n in Counter(r["id"] for r in rows).items() if n > 1]
    cap = 1 if series.training_only else MAX_LABEL_COPIES
    problems += [f"text repeated {n} times (cap {cap})" for n in Counter(r["text"] for r in rows).values() if n > cap]
    for row in rows:
        where = row["id"]
        if row.get("capture") != CAPTURE or row.get("label_source") != LABEL_SOURCE or row.get("reference_eligible") is not False \
                or row.get("eval_use") != "never":
            problems.append(f"{where}: provenance fields missing (synthetic_render, never eval)")
        reason = text_drop_reason(row["text"])[0]
        if reason is not None:
            problems.append(f"{where}: text fails a line rule ({reason})")
        if row.get("release_scope") != series.release_scope(row):
            problems.append(f"{where}: release_scope is not the series' scope")
    manifest = out / "manifest.jsonl"
    if manifest.is_file():
        rendered = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines() if line.strip()]
        if sha256_bytes(manifest.read_bytes()) != (summary.get("render") or {}).get("manifest_sha256"):
            problems.append("manifest.jsonl sha256 differs from summary")
        known = {row["id"]: row for row in rows}
        listed = set()
        for row in rendered:
            where = row["id"]
            if known.get(where, {}).get("text") != row.get("text"):
                problems.append(f"{where}: rendered row not in lines_text.jsonl or text differs")
            if not row.get("face") or (row.get("render") or {}).get("font_license") not in RENDER_LICENSES:
                problems.append(f"{where}: face or open font licence missing")
            path = out / row["image"]
            listed.add(path.resolve())
            if row["image"] != f"train/{row['book']}/{where}.png" or not path.is_file() or sha256_bytes(path.read_bytes()) != row.get("image_sha256"):
                problems.append(f"{where}: image path, file or sha256 wrong")
            gt = path.with_suffix(".gt.txt")
            if not gt.is_file() or gt.read_text(encoding="utf-8") != row["text"] + "\n":
                problems.append(f"{where}: gt.txt missing or differs from the text")
        for png in (out / "train").glob("*/*.png") if (out / "train").is_dir() else []:
            if png.resolve() not in listed:
                problems.append(f"{png.relative_to(out)}: image not in the manifest")
    if summary["eval_reserved_check"]["eval_rows"] or summary["eval_reserved_check"]["unassigned_rows"]:
        problems.append("summary counts eval or unassigned rows")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("plan", help="select units from an enumeration")
    p.add_argument("out")
    p.add_argument("--enumeration", required=True)
    p.add_argument("--series", default="plenary", choices=sorted(SERIES))
    p.add_argument("--per-term", type=int, default=DEFAULT_PER_TERM)
    c = sub.add_parser("capture", help="fetch a plan's protocol documents (rate-limited)")
    c.add_argument("plan")
    c.add_argument("--cache", required=True)
    b = sub.add_parser("build", help="gated training-line text for the planned units")
    b.add_argument("out")
    b.add_argument("--plan", required=True)
    b.add_argument("--cache", required=True)
    b.add_argument("--series", default="plenary", choices=sorted(SERIES))
    b.add_argument("--soffice", default=shutil.which("soffice") or DEFAULT_SOFFICE)
    b.add_argument("--ner-python", default=DEFAULT_NER_PYTHON)
    b.add_argument("--max-lines-per-unit", type=int, default=DEFAULT_MAX_LINES_PER_UNIT)
    b.add_argument("--max-label-copies", type=int, default=MAX_LABEL_COPIES)
    b.add_argument("--private-dir", help="dropped-line details (default OUT/private; never committed)")
    b.add_argument("--created-at")
    b.add_argument("--signature")
    r = sub.add_parser("render", help="run hocrsyngen render-lines on render_input.jsonl and join its manifest")
    r.add_argument("out")
    r.add_argument("--render-dir", required=True)
    r.add_argument("--render-command", default=DEFAULT_RENDER_CMD, help="the renderer command; per-band flags are appended")
    r.add_argument("--font", action="append", dest="fonts", help=f"render face (repeatable; default {', '.join(RENDER_FONTS)})")
    r.add_argument("--seed", type=int, default=RENDER_SEED)
    r.add_argument("--preset", default=RENDER_PRESET)
    r.add_argument("--join-only", action="store_true", help="join an existing render dir without running the renderer")
    v = sub.add_parser("verify", help="check a built set")
    v.add_argument("out")
    args = parser.parse_args(argv)
    if args.command == "plan":
        plan = plan_units(json.loads(Path(args.enumeration).read_text(encoding="utf-8")), SERIES[args.series], per_term=args.per_term)
        Path(args.out).write_text(json.dumps(plan, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(len(plan["units"]), "units", json.dumps(plan["skipped_before_selection"], ensure_ascii=False))
        return 0
    if args.command == "capture":
        print(len(capture(json.loads(Path(args.plan).read_text(encoding="utf-8")), Path(args.cache))), "pinned")
        return 0
    if args.command == "build":
        summary = build(args)
        print(json.dumps({key: summary[key] for key in ("totals", "dropped", "lines_text_sha256")}, ensure_ascii=False))
        return 0
    if args.command == "render":
        out, render_dir = Path(args.out), Path(args.render_dir)
        result = join_render(out, render_dir) if args.join_only else render(
            out, render_dir, args.render_command, fonts=args.fonts or RENDER_FONTS, seed=args.seed, preset=args.preset)
        print(json.dumps({k: result[k] for k in ("rendered_rows", "not_rendered", "refused")}, ensure_ascii=False))
        return 0
    problems = verify(Path(args.out))
    for problem in problems[:50]:
        print(problem)
    print(f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
