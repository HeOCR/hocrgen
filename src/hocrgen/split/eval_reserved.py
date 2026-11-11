"""Evaluation-reserved P-mod units (heocr-engine decision 0017): unit ids, status and the training-input guard.

heocr-eval owns the printed-modern (P-mod) evaluation set. Its split file lists, per source, the **units** (one
Reshumot booklet, one Knesset protocol) that are ``eval`` and those that are ``non_eval``; a unit of a listed source
that is in neither list is ``unassigned``. Its usage rule: eval units are never used for training, tuning, selection,
glyph harvesting or synthetic style/layout sources; unassigned units are used for neither training nor eval.

hocrgen records the file in ``eval_reserved_units.v1`` (``src/hocrgen/config/eval_reserved_units.yaml``) and enforces
it in two places:

- the release split pins every component holding an ``eval`` or ``unassigned`` unit to the ``eval_reserved``
  holdout (``split_constraint: eval_reserved_unit``), and the split and export stages refuse any such item in another
  split (``hocrgen.split.assign``, ``hocrgen.package.common.copy_export_assets``);
- every training-input builder passes its input rows through ``refuse_eval_reserved_training_input`` before it
  writes anything, and the guard raises ``EvalReservedUnitError`` on any row from a reserved unit.

The guard fails closed: a row of a listed source whose unit cannot be derived is ``unassigned``, and a row that only
*looks* like a Reshumot or Knesset page (by its ids) is checked even when it names another source.

Governed sources (decisions 0017/0018): ``reshumot_born_digital`` (``reshumot:<series>_<n>``),
``knesset_committee_protocols_pre1976`` (``knesset_protocol:<id>``), ``reshumot_scanned``
(``reshumot_scanned:<series>_<n>``, its own prefix with the same series strings) and ``knesset_plenary_k1_12``
(``plenary:K<knesset>_<sitting>``). Every unit id names one source, and the registry refuses a booklet listed in both
Reshumot sources. A governed source the registry does not list yet (scanned Reshumot and plenary under
``pmod_unit_split_v1``) has every unit ``unassigned``: its rows are refused until a split version lists them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from functools import lru_cache
from typing import Any

from hocrgen.config.models import EVAL_RESERVED_STATUSES, EvalReservedUnitsRegistry, EvalUnitStatus
from hocrgen.split.balance import EVAL_RESERVED_SPLIT

RESHUMOT_SOURCE_ID = "reshumot_born_digital"
KNESSET_SOURCE_ID = "knesset_committee_protocols_pre1976"
RESHUMOT_SCANNED_SOURCE_ID = "reshumot_scanned"
PLENARY_SOURCE_ID = "knesset_plenary_k1_12"
GOVERNED_SOURCE_IDS = (RESHUMOT_SOURCE_ID, KNESSET_SOURCE_ID, RESHUMOT_SCANNED_SOURCE_ID, PLENARY_SOURCE_ID)
__all__ = ["EVAL_RESERVED_SPLIT", "EvalReservedUnitError", "refuse_eval_reserved_training_input", "unit_status"]
PIN_EVAL_RESERVED_UNIT = "eval_reserved_unit"
DECISION = "heocr-engine decision 0017"

_SERIES = r"(?P<series>kovetz_hatakanot|sefer_hachukim)"
_PAGE = r"(?:__p\d+)?"
# Each pattern matches a whole identifier. Reshumot: the unit id (reshumot:<series>_<n>), the source group
# (reshumot:<series>:<n>), and the page / entry / item id (<series>_<n>__p0001, optionally prefixed by the source id
# and ":" or by "reshumot_", as the R4f files write it). Knesset: the unit id (knesset_protocol:<id>), the source group
# (knesset_committee:<id>), and the page / entry / item id (knesset_committee_<id>__p0001, optionally source-prefixed).
_RESHUMOT_PATTERNS = (
    re.compile(rf"^reshumot:{_SERIES}[:_](?P<number>\d+)$"),
    re.compile(rf"^(?:{RESHUMOT_SOURCE_ID}:)?(?:reshumot_)?{_SERIES}_(?P<number>\d+){_PAGE}$"),
)
_KNESSET_PATTERNS = (
    re.compile(r"^knesset_(?:protocol|committee):(?P<document>\d+)$"),
    re.compile(rf"^(?:{KNESSET_SOURCE_ID}:)?knesset_committee_(?P<document>\d+){_PAGE}$"),
)
# Scanned Reshumot (its own prefix, the same series strings): the unit id (reshumot_scanned:<series>_<n>), the source
# group (reshumot_scanned:<series>:<n>) and the page / item id (reshumot_scanned_<series>_<n>__p0001, optionally
# prefixed by the source id and ":"). Knesset plenary: the unit id (plenary:K<knesset>_<sitting>) and the page / item id
# (plenary_K<knesset>_<sitting>__p0001, optionally source-prefixed). Neither shape matches a born-digital or committee
# pattern, so every id names one source.
_RESHUMOT_SCANNED_PATTERNS = (
    re.compile(rf"^{RESHUMOT_SCANNED_SOURCE_ID}:{_SERIES}[:_](?P<number>\d+)$"),
    re.compile(rf"^(?:{RESHUMOT_SCANNED_SOURCE_ID}:)?reshumot_scanned_{_SERIES}_(?P<number>\d+){_PAGE}$"),
)
_PLENARY_PATTERNS = (
    re.compile(r"^plenary:K(?P<knesset>\d+)_(?P<sitting>\d+)$"),
    re.compile(rf"^(?:{PLENARY_SOURCE_ID}:)?plenary_K(?P<knesset>\d+)_(?P<sitting>\d+){_PAGE}$"),
)
# Fail closed: an id that starts like a scanned-Reshumot or plenary id but matches no pattern above is governed by
# that source with no derivable unit (unassigned, so refused). The born-digital and committee shapes keep their
# exact patterns, unchanged.
_LOOKALIKE = (
    (re.compile(rf"^(?:{RESHUMOT_SCANNED_SOURCE_ID}[:_])", re.IGNORECASE), RESHUMOT_SCANNED_SOURCE_ID),
    (re.compile(rf"^(?:{PLENARY_SOURCE_ID}:)?plenary[:_]", re.IGNORECASE), PLENARY_SOURCE_ID),
)
# Row fields the guard reads identifiers from (a mapping's keys or an object's attributes).
IDENTIFIER_FIELDS = (
    "unit_id", "item_id", "source_item_id", "entry_id", "source_group_id", "source_group",
    "page_id", "record_id", "work_id", "match_key", "id",
)


class EvalReservedUnitError(ValueError):
    """An input from an evaluation-reserved unit reached a training-input builder or the release train split."""


@dataclass(frozen=True)
class GovernedUnit:
    """A row's governed source and unit (``unit_id`` is ``None`` when it cannot be derived: unassigned)."""

    source_id: str
    unit_id: str | None
    evidence: str


def reshumot_unit_id(series: str, number: str | int) -> str:
    return f"reshumot:{series}_{int(str(number))}"


def knesset_unit_id(document_id: str | int) -> str:
    return f"knesset_protocol:{int(str(document_id))}"


def reshumot_scanned_unit_id(series: str, number: str | int) -> str:
    return f"{RESHUMOT_SCANNED_SOURCE_ID}:{series}_{int(str(number))}"


def plenary_unit_id(knesset: str | int, sitting: str | int) -> str:
    return f"plenary:K{int(str(knesset))}_{int(str(sitting))}"


def unit_from_identifier(value: Any) -> tuple[str, str] | None:
    """``(source_id, unit_id)`` when ``value`` is a governed unit, group, page or item id; else ``None``."""

    if not isinstance(value, str):
        return None
    for pattern in _RESHUMOT_SCANNED_PATTERNS:
        match = pattern.match(value)
        if match:
            return RESHUMOT_SCANNED_SOURCE_ID, reshumot_scanned_unit_id(match["series"], match["number"])
    for pattern in _PLENARY_PATTERNS:
        match = pattern.match(value)
        if match:
            return PLENARY_SOURCE_ID, plenary_unit_id(match["knesset"], match["sitting"])
    for pattern in _RESHUMOT_PATTERNS:
        match = pattern.match(value)
        if match:
            return RESHUMOT_SOURCE_ID, reshumot_unit_id(match["series"], match["number"])
    for pattern in _KNESSET_PATTERNS:
        match = pattern.match(value)
        if match:
            return KNESSET_SOURCE_ID, knesset_unit_id(match["document"])
    return None


def lookalike_source(value: Any) -> str | None:
    """The new governed source an id only *looks* like (a scanned-Reshumot or plenary prefix), when no pattern matched."""

    if not isinstance(value, str) or unit_from_identifier(value) is not None:
        return None
    return next((source for pattern, source in _LOOKALIKE if pattern.match(value)), None)


def _metadata_unit(source_id: str | None, metadata: Mapping[str, Any]) -> str | None:
    """The unit from the fetchers' structured metadata (``hocrgen.fetchers.government_print``)."""

    if source_id in (RESHUMOT_SOURCE_ID, RESHUMOT_SCANNED_SOURCE_ID):
        series, number = metadata.get("reshumot_series"), metadata.get("reshumot_booklet_number")
        if series and number not in (None, ""):
            make = reshumot_unit_id if source_id == RESHUMOT_SOURCE_ID else reshumot_scanned_unit_id
            return make(str(series), str(number))
    if source_id == KNESSET_SOURCE_ID:
        document = metadata.get("knesset_document_id")
        if document not in (None, ""):
            return knesset_unit_id(document)
    return None


def _get(row: Any, name: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def row_fields(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if is_dataclass(row):
        return {field.name: getattr(row, field.name) for field in fields(row)}
    if hasattr(row, "model_dump"):
        return row.model_dump()
    return {name: getattr(row, name) for name in ("source_id", "metadata", *IDENTIFIER_FIELDS) if hasattr(row, name)}


def governed_unit(row: Any, *, source_id: str | None = None) -> GovernedUnit | None:
    """The governed (Reshumot or Knesset) unit of a row, an item record or a dataclass; ``None`` if not governed.

    A row is governed when its ``source_id`` (or the ``source_id`` given) is a governed source (born-digital or scanned
    Reshumot, Knesset committee or plenary), or when any of its identifiers has a governed id shape. Its unit comes from
    the fetcher metadata, else the identifiers. Identifiers naming two different units or sources raise: an ambiguous
    row is never let through. An id that only looks like a scanned-Reshumot or plenary id governs the row with no unit.
    """

    declared = _get(row, "source_id") or source_id
    metadata = _get(row, "metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    found: dict[str, tuple[str, str]] = {}
    unit = _metadata_unit(declared, metadata)
    if unit is not None:
        found[unit] = (str(declared), "metadata")
    values = [(name, _get(row, name)) for name in IDENTIFIER_FIELDS]
    values += [(f"metadata.{name}", metadata.get(name)) for name in ("source_group_id", "upstream_identifier")]
    lookalikes: set[str] = set()
    for name, value in values:
        hit = unit_from_identifier(value)
        if hit is not None:
            found.setdefault(hit[1], (hit[0], f"{name}={value}"))
        elif (lookalike := lookalike_source(value)) is not None:
            lookalikes.add(lookalike)
    sources = {source for source, _ in found.values()} | lookalikes
    if declared in GOVERNED_SOURCE_IDS:
        sources.add(str(declared))
    if not sources:
        return None
    if len(found) > 1 or len(sources) > 1:
        raise EvalReservedUnitError(
            f"row names more than one governed unit or source ({sorted(found)}, {sorted(sources)}); refusing it")
    if not found:
        return GovernedUnit(source_id=sources.pop(), unit_id=None, evidence="no unit derivable")
    (unit_id, (unit_source, evidence)), = found.items()
    return GovernedUnit(source_id=unit_source, unit_id=unit_id, evidence=evidence)


@lru_cache(maxsize=1)
def packaged_registry() -> EvalReservedUnitsRegistry:
    from hocrgen.config.loader import load_eval_reserved_units

    return load_eval_reserved_units()


def unit_status(row: Any, registry: EvalReservedUnitsRegistry | None = None, *,
                source_id: str | None = None) -> tuple[GovernedUnit, EvalUnitStatus] | None:
    """The row's governed unit and its status, or ``None`` for a row the split file does not govern."""

    registry = registry or packaged_registry()
    unit = governed_unit(row, source_id=source_id)
    if unit is None:
        return None
    status = registry.status(unit.source_id, unit.unit_id)
    if status is None:  # a governed id shape whose source the registry does not list: fail closed
        status = EvalUnitStatus.unassigned
    return unit, status


def is_reserved(status: EvalUnitStatus | None) -> bool:
    return status in EVAL_RESERVED_STATUSES


def registry_provenance(registry: EvalReservedUnitsRegistry) -> str:
    return f"{registry.registry_id} from {registry.split_file.name} (sha256 {registry.split_file.sha256[:12]})"


def refuse_eval_reserved_training_input(rows: Iterable[Any], *, builder: str,
                                        registry: EvalReservedUnitsRegistry | None = None,
                                        source_id: str | None = None) -> int:
    """Raise ``EvalReservedUnitError`` if any row comes from an ``eval`` or ``unassigned`` P-mod unit.

    The shared input boundary of every training-input builder (the line sets, the glyph banks, the release train
    split). ``source_id`` is the builder's own source, for rows that do not carry one. Returns the number of rows
    checked; nothing is written by the guard.
    """

    registry = registry or packaged_registry()
    refused: list[str] = []
    checked = 0
    for row in rows:
        checked += 1
        found = unit_status(row, registry, source_id=source_id)
        if found is None:
            continue
        unit, status = found
        if is_reserved(status):
            label = _get(row, "item_id") or _get(row, "id") or _get(row, "page_id") or _get(row, "style_id") or unit.evidence
            refused.append(f"{label}: {unit.unit_id or unit.source_id + ' (unit not derivable)'} is {status.value}")
    if refused:
        shown = "; ".join(refused[:10]) + (f"; and {len(refused) - 10} more" if len(refused) > 10 else "")
        raise EvalReservedUnitError(
            f"{builder}: refused {len(refused)} input row(s) from evaluation-reserved P-mod units "
            f"({DECISION}; {registry_provenance(registry)}). Eval units are never training, tuning, selection, glyph "
            f"or synthetic style/layout input, and unassigned units are used for neither until a new split version "
            f"assigns them: {shown}")
    return checked
