"""Per-item rights justification for Internet Archive scans (Route B), generated from evidence.

The 2026-11-10 legal strategy (``planning/decisions/2026-11-10-legal-strategy.md``, "Per-item rights justification")
requires every scan accepted through Route B or C to carry a ``rights_justification`` record that the gate builds from
evidence; nobody writes it by hand. When a required field cannot be filled, the item is rejected with a specific
``justification_…`` reason. ``build_ia_rights_justification`` builds the record for an item the IA gate
(``hocrgen.fetchers.ia_iiif.decide_ia_rights``) accepted; ``justify_existing_alignment`` rebuilds it for an
alignment made before the record existed, without re-aligning.

Sources, all read from saved snapshots (this module never touches the network):

- **Contributors.** Every author and translator of the Project Ben-Yehuda (PBY) work (``pseudocatalogue.csv``
  ``authors``/``translators``, paired by position with ``author_uris``/``translator_uris``), or, for a Sefaria or
  Project Gutenberg text, every author, translator, editor and annotator its text record lists with a QID
  (``hocrgen.fetchers.text_sources.justification_row``, ``contributors_listed_in="text_record"``), plus every editor or
  annotator the IA metadata or the NLI record names by role (a ``creator`` entry marked editor, or "ed." /
  "Commentar von" / "עורך" / "מהדיר" in the title statement or description). Death years come first from a saved
  Wikidata entity snapshot (P570) for the contributor's QID, then from life dates in the IA ``creator`` field or the
  NLI authority string, cited as such.
- **Publication year and place.** IA ``date`` and ``publisher``, the NLI record, then the PBY ``source_edition``.
  Status decisions use the latest year found (the conservative one).
- **Israeli status (Copyright Act 2007, s. 38).** PD when every contributor died more than 70 years before
  ``as_of``'s year; for a work printed in or before 1855, a contributor with no death year found is covered by the
  presumption of decision 10 (2026-11-06), recorded as such. A text record may mark the underlying work anonymous
  (an ancient compilation with a traditional attribution only, such as Avot de-Rabbi Natan): it then needs no author,
  the edition must be published more than 70 years before ``as_of``'s year (s. 40), and every named contributor (the
  editor) must still meet s. 38. Otherwise the item is rejected.
- **US status** is recorded, not required (decision 2026-11-06: PD in Israel is enough): ``pd_us`` when published
  before ``as_of.year - 95``, else ``not_established``.

``as_of`` is a parameter: the operator passes the run date and tests pin it.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from hocrgen.fetchers.ia_iiif import (
    DIGITIZER_GOOGLE,
    DIGITIZER_NLI,
    IA_DECISION_RECORD,
    IA_METADATA_URL,
    IA_SOURCE,
    LEGAL_STRATEGY_DECISION_RECORD,
    SOURCE_CLASS_GOOGLE,
    IaRightsDecision,
    decide_ia_rights,
)
from hocrgen.fetchers.nli_iiif import NLI_CAPTURE_FORMAT, manifest_license_values, nli_license_slug
from hocrgen.tools.nli_printed_inventory import parse_publication_year

JUSTIFICATION_FORMAT = "hocrgen.rights_justification.v1"
GENERATOR = "hocrgen.fetchers.ia_justification.build_ia_rights_justification"
LEGAL_STRATEGY_DOC = "docs/legal/2026-11-10_legal_strategy.md"
DECISION_10_RECORD = "planning/decisions/2026-11-06-f8-real-source-decisions.md"
WIKIDATA_ENTITY_URL = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
IA_TERMS_URL = "https://archive.org/about/terms.php"

ISRAEL_TERM_YEARS = 70
US_TERM_YEARS = 95
PRESUMPTION_CUTOFF_YEAR = 1855  # decision 10 (2026-11-06)
# The IA imagecount counts a few images the IIIF manifest leaves out (colour cards, covers).
IMAGECOUNT_SLACK = 4

ROLE_AUTHOR = "author"
ROLE_TRANSLATOR = "translator"
ROLE_EDITOR = "editor"
ROLE_ANNOTATOR = "annotator"

FAITHFUL_REPRODUCTION_TEXT = (
    "A faithful photographic or mechanical scan of a two-dimensional printed page carries no new copyright: in the US"
    " a slavish copy lacks originality (Feist v. Rural, 499 U.S. 340 (1991); Bridgeman v. Corel, 36 F. Supp. 2d 191"
    " (S.D.N.Y. 1999)), and in Israel sweat of the brow is not enough (CA 513/89 Interlego v. Exin-Lines, Copyright"
    " Act 2007). Strategy section 1."
)
WHY_NOT_BINDING_TEMPLATE = (
    "HeOCR fetched this file from {route}, not from {holders}. It accepted no terms from {holders} for it and is not"
    " in privity with {holders}, so {label} binds neither HeOCR nor the users of its releases (strategy section 2(a)"
    " and 2(c)). With no copyright in the public-domain text or in the faithful scan, no right travels with the file."
)
ROUTE_TERMS_TEXT = (
    "Internet Archive terms of use; strategy section 2(a): IA's terms impose no restriction on public-domain items."
)
GOOGLE_USAGE_GUIDELINES = (
    "Google's front-page usage guidelines (requests to make non-commercial use of the files, refrain from automated"
    " querying and maintain attribution)"
)

# Editor and annotator roles: in a creator entry ("…, editor"), or in a title statement or description.
ROLE_IN_ENTRY = re.compile(
    r"[,(]\s*(?P<role>ed\.|editor|herausgeber|hrsg\.?|annotator|commentator|עורך|מהדיר|מפרש)\s*[,)]?\s*$", re.I
)
ROLE_IN_STATEMENT = re.compile(
    r"(?P<role>edited|ed\.|herausgegeben|hrsg\.|commentar|kommentar|commentary|annotations?|notes)\s+(?:by|von|v\.)\s+"
    r"(?P<name>[^,;:/()\[\]]+?)\s*(?=$|[,;:/()\[\]]|\.\s|\.$)"
    r"|(?P<hrole>בעריכת|ערך|עורך|מהדיר|בהדרת|עם\s+פירוש\s+מאת)\s*:?\s+(?P<hname>[^,;:/()\[\]]+?)\s*(?=$|[,;:/()\[\].])",
    re.I,
)
ANNOTATOR_ROLES = re.compile(r"commentar|kommentar|commentary|annotat|notes|מפרש|פירוש", re.I)
LIFE_DATES = re.compile(r"(?<!\d)(?P<born>\d{3,4})\??\s*[-–]\s*(?P<died>\d{3,4})\??(?!\d)|\bd\.\s*(?P<d>\d{3,4})(?!\d)")
YEAR = re.compile(r"(?<!\d)(1[4-9]\d\d|20\d\d)(?!\d)")
HEBREW_FINALS = str.maketrans("ךםןףץ", "כמנפצ")


@dataclasses.dataclass(frozen=True)
class WikidataSnapshot:
    """A saved ``Special:EntityData/<QID>.json`` response: its QID, source URL, sha256 and entity."""

    qid: str
    url: str
    sha256: str
    entity: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class NliSnapshot:
    """A saved NLI IIIF manifest (raw, or an ``hocrgen.nli_iiif_manifest_capture.v1`` capture)."""

    url: str | None
    sha256: str
    manifest: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class JustificationResult:
    accepted: bool
    reason: str
    failures: list[str]
    record: dict[str, Any] | None

    @property
    def id(self) -> str | None:
        return None if self.record is None else self.record["id"]


# --- snapshots ----------------------------------------------------------------------------------------------


def wikidata_snapshot_from_bytes(qid: str, data: bytes) -> WikidataSnapshot:
    payload = json.loads(data)
    entities = payload.get("entities") or {}
    entity = entities.get(qid) or (next(iter(entities.values())) if len(entities) == 1 else None)
    if not isinstance(entity, Mapping):
        raise ValueError(f"Wikidata snapshot for {qid} has no entity")
    return WikidataSnapshot(qid=qid, url=WIKIDATA_ENTITY_URL.format(qid=qid), sha256=hashlib.sha256(data).hexdigest(), entity=entity)


def load_wikidata_snapshots(directory: Path) -> dict[str, WikidataSnapshot]:
    """Every ``<QID>.json`` entity snapshot in ``directory`` (saved by the operator from Special:EntityData)."""

    snapshots: dict[str, WikidataSnapshot] = {}
    for path in sorted(Path(directory).glob("Q*.json")):
        snapshots[path.stem] = wikidata_snapshot_from_bytes(path.stem, path.read_bytes())
    return snapshots


def nli_snapshot_from_bytes(data: bytes) -> NliSnapshot:
    payload = json.loads(data)
    if isinstance(payload, Mapping) and payload.get("capture_format") == NLI_CAPTURE_FORMAT:
        return NliSnapshot(url=payload.get("manifest_url"), sha256=hashlib.sha256(data).hexdigest(), manifest=payload.get("manifest") or {})
    return NliSnapshot(url=payload.get("@id"), sha256=hashlib.sha256(data).hexdigest(), manifest=payload)


def load_nli_snapshot(path: Path) -> NliSnapshot:
    return nli_snapshot_from_bytes(Path(path).read_bytes())


# --- helpers ------------------------------------------------------------------------------------------------


def _md(metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    inner = metadata.get("metadata")
    return inner if isinstance(inner, Mapping) else metadata


def _values(md: Mapping[str, Any], key: str) -> list[str]:
    value = md.get(key)
    items = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in items if item is not None and str(item).strip()]


def _tokens(text: str) -> list[str]:
    """Name tokens for matching across sources: Latin folded to ASCII lower case; Hebrew without matres (ו, י),
    final forms folded."""

    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower().translate(HEBREW_FINALS)
    tokens = []
    for token in re.findall(r"[a-z]+|[א-ת]+", folded):
        if re.match(r"[א-ת]", token):
            token = token.replace("ו", "").replace("י", "")
        if len(token) > 1:
            tokens.append(token)
    return tokens


def _qids(uris: str | None) -> list[str | None]:
    out: list[str | None] = []
    for part in (uris or "").split(";"):
        part = part.strip()
        if not part:
            continue
        match = re.search(r"(Q\d+)\s*$", part)
        out.append(match.group(1) if match else None)
    return out


def _names(names: str | None) -> list[str]:
    return [part.strip() for part in (names or "").split(";") if part.strip()]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _year_from_wikidata_time(value: Mapping[str, Any]) -> tuple[int | None, str]:
    time = str(value.get("time") or "")
    precision = int(value.get("precision") or 0)
    match = re.match(r"([+-])(\d+)-", time)
    if not match:
        return None, "unparsed"
    year = int(match.group(2)) * (-1 if match.group(1) == "-" else 1)
    if precision >= 9:
        return year, "year"
    if precision == 8:  # a decade: the latest year in it
        return year - year % 10 + 9, "decade (latest year used)"
    return None, f"precision {precision} (coarser than a decade)"


def wikidata_death_year(snapshot: WikidataSnapshot) -> dict[str, Any] | None:
    """The P570 (date of death) evidence of a Wikidata entity, or None. Several values give the latest year."""

    claims = [c for c in (snapshot.entity.get("claims") or {}).get("P570") or [] if c.get("rank") != "deprecated"]
    preferred = [c for c in claims if c.get("rank") == "preferred"]
    values = []
    for claim in preferred or claims:
        snak = claim.get("mainsnak") or {}
        if snak.get("snaktype") != "value":
            continue
        value = (snak.get("datavalue") or {}).get("value") or {}
        year, precision = _year_from_wikidata_time(value)
        if year is not None:
            values.append((year, str(value.get("time")), precision))
    if not values:
        return None
    year, time, precision = max(values)
    return {
        "kind": "wikidata_p570",
        "qid": snapshot.qid,
        "url": snapshot.url,
        "sha256": snapshot.sha256,
        "value": time,
        "precision": precision,
        "death_year": year,
        **({"all_values": sorted(v[1] for v in values)} if len(values) > 1 else {}),
    }


def wikidata_names(snapshot: WikidataSnapshot | None) -> list[str]:
    if snapshot is None:
        return []
    names = [label.get("value", "") for label in (snapshot.entity.get("labels") or {}).values()]
    for aliases in (snapshot.entity.get("aliases") or {}).values():
        names.extend(alias.get("value", "") for alias in aliases)
    return [name for name in names if name]


def wikidata_label(snapshot: WikidataSnapshot | None) -> str | None:
    labels = (snapshot.entity.get("labels") or {}) if snapshot else {}
    for lang in ("en", "he"):
        if lang in labels:
            return labels[lang].get("value")
    return None


@dataclasses.dataclass(frozen=True)
class CreatorEntry:
    """A person entry in IA ``creator`` or an NLI creator field, with its life dates when it states them."""

    source: str  # "ia_metadata_creator" or "nli_authority"
    field: str
    value: str
    name: str
    death_year: int | None
    role: str | None


def _entry(source: str, field: str, value: str, as_of_year: int) -> CreatorEntry:
    clean = re.sub(r"^\d{2}\s+", "", value.split("$$Q")[0]).strip()  # Michigan's "01 " ordering prefix; NLI's $$Q copy
    death = None
    for match in LIFE_DATES.finditer(clean):
        died = int(match.group("died") or match.group("d"))
        born = int(match.group("born")) if match.group("born") else None
        if died <= as_of_year and (born is None or born < died):
            death = died
    role_match = ROLE_IN_ENTRY.search(clean)
    role = None
    if role_match:
        role = ROLE_ANNOTATOR if ANNOTATOR_ROLES.search(role_match.group("role")) else ROLE_EDITOR
    name = LIFE_DATES.split(clean)[0] if LIFE_DATES.search(clean) else clean
    name = ROLE_IN_ENTRY.sub("", name).strip(" ,.;")
    return CreatorEntry(source=source, field=field, value=value, name=name, death_year=death, role=role)


def creator_entries(md: Mapping[str, Any], nli: NliSnapshot | None, as_of_year: int) -> list[CreatorEntry]:
    entries = [_entry("ia_metadata_creator", "creator", value, as_of_year) for value in _values(md, "creator")]
    if nli is not None:
        for item in nli.manifest.get("metadata") or []:
            label = str((item or {}).get("label") or "")
            if not re.search(r"creator|contributor|author", label, re.I):
                continue
            raw = item.get("value")
            for value in raw if isinstance(raw, list) else [raw]:
                for part in str(value or "").split(";"):
                    if part.strip():
                        entries.append(_entry("nli_authority", label, part.strip(), as_of_year))
    return entries


def _matches(names: Sequence[str], entry: CreatorEntry) -> bool:
    """An entry matches when every token of its surname (the part before the first comma) is a token of a name."""

    surname = _tokens(entry.name.split(",")[0])
    if not surname:
        return False
    return any(set(surname) <= set(_tokens(name)) for name in names if name)


def statement_roles(md: Mapping[str, Any], nli: NliSnapshot | None) -> list[dict[str, str]]:
    """Editors and annotators named in a title statement or description ("ed. by X", "Commentar von X", "עורך X")."""

    statements = [("ia_metadata_title", v) for v in _values(md, "title")]
    statements += [("ia_metadata_description", v) for v in _values(md, "description")]
    if nli is not None:
        label = nli.manifest.get("label")
        if isinstance(label, str):
            statements.append(("nli_record_title", label))
    found = []
    for source, text in statements:
        for match in ROLE_IN_STATEMENT.finditer(text):
            role_text = match.group("role") or match.group("hrole")
            name = (match.group("name") or match.group("hname") or "").strip()
            if not _tokens(name):
                continue
            role = ROLE_ANNOTATOR if ANNOTATOR_ROLES.search(role_text) else ROLE_EDITOR
            found.append({"name": name, "role": role, "source": source, "statement": text})
    return found


def publication_years(md: Mapping[str, Any], nli: NliSnapshot | None, catalogue_row: Mapping[str, str],
                      listed_in: str = "pby_catalogue") -> list[dict[str, Any]]:
    found = []
    ia_years = sorted({int(y) for value in _values(md, "date") for y in YEAR.findall(value)})
    if ia_years:
        found.append({"year": max(ia_years), "source": "ia_metadata_date", "value": "; ".join(_values(md, "date"))})
    if nli is not None:
        for item in nli.manifest.get("metadata") or []:
            if re.search(r"date", str((item or {}).get("label") or ""), re.I):
                value = item.get("value")
                text = "; ".join(value) if isinstance(value, list) else str(value or "")
                year, basis = parse_publication_year(text)
                if year is not None and basis == "year":
                    found.append({"year": year, "source": "nli_record", "value": text})
                    break
    edition = (catalogue_row.get("source_edition") or "").strip()
    if edition:
        year, basis = parse_publication_year(edition)
        if year is not None and basis == "year":
            found.append({"year": year, "source": f"{listed_in}_source_edition", "value": edition})
    return found


def _place_from(text: str, separators: str) -> str | None:
    for sep in separators:
        if sep in text:
            head = text.split(sep)[0].strip(" []")
            if head and not re.search(r"\d", head) and len(head) <= 40 and not head.startswith("מתוך"):
                return head
    return None


def publication_place(md: Mapping[str, Any], nli: NliSnapshot | None, catalogue_row: Mapping[str, str],
                      listed_in: str = "pby_catalogue") -> dict[str, Any] | None:
    for value in _values(md, "publisher"):
        place = _place_from(value, ":")
        if place:
            return {"place": place, "source": "ia_metadata_publisher", "value": value}
    if nli is not None:
        for item in nli.manifest.get("metadata") or []:
            if str((item or {}).get("label") or "").lower() == "publisher":
                value = str(item.get("value") or "")
                place = _place_from(value, ":")
                if place:
                    return {"place": place, "source": "nli_record_publisher", "value": value}
    edition = (catalogue_row.get("source_edition") or "").strip()
    place = _place_from(edition, ":,") if edition else None
    if place:
        return {"place": place, "source": f"{listed_in}_source_edition", "value": edition}
    return None


def _image_count_check(md: Mapping[str, Any], canvas_count: int) -> dict[str, Any]:
    raw = md.get("imagecount")
    try:
        imagecount = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        imagecount = None
    consistent = None if imagecount is None else canvas_count <= imagecount <= canvas_count + IMAGECOUNT_SLACK
    return {"imagecount": imagecount, "manifest_canvases": canvas_count, "consistent": consistent,
            "rule": f"manifest canvases <= imagecount <= manifest canvases + {IMAGECOUNT_SLACK}"}


# --- the record ---------------------------------------------------------------------------------------------


def _contributors(
    catalogue_row: Mapping[str, str],
    md: Mapping[str, Any],
    wikidata: Mapping[str, WikidataSnapshot],
    nli: NliSnapshot | None,
    as_of_year: int,
    listed_in: str = "pby_catalogue",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    entries = creator_entries(md, nli, as_of_year)
    people: list[dict[str, Any]] = []
    roles = [(ROLE_AUTHOR, "authors", "author_uris"), (ROLE_TRANSLATOR, "translators", "translator_uris")]
    if listed_in != "pby_catalogue":  # a text record also lists editors and annotators (PBY rows have neither)
        roles += [(ROLE_EDITOR, "editors", "editor_uris"), (ROLE_ANNOTATOR, "annotators", "annotator_uris")]
    for role, names_key, uris_key in roles:
        names, qids = _names(catalogue_row.get(names_key)), _qids(catalogue_row.get(uris_key))
        paired = len(names) == len(qids)
        count = max(len(names), len(qids))
        for i in range(count):
            qid = qids[i] if paired or (not names and i < len(qids)) else None
            name = names[i] if i < len(names) else None
            people.append({"name": name, "role": role, "qid": qid, "listed_in": f"{listed_in}.{names_key}"})
    for statement in statement_roles(md, nli):
        people.append({"name": statement["name"], "role": statement["role"], "qid": None, "listed_in": statement["source"]})
    for entry in entries:
        if entry.role:
            people.append({"name": entry.name, "role": entry.role, "qid": None, "listed_in": f"{entry.source}.{entry.field}"})
    contributors: list[dict[str, Any]] = []
    used: set[int] = set()
    for person in people:
        snapshot = wikidata.get(person["qid"]) if person["qid"] else None
        match_names = [n for n in [person["name"], *wikidata_names(snapshot)] if n]
        # The same person listed twice (a PBY author also named as editor): keep the first listing.
        own = set(_tokens(person["name"] or ""))
        if not person["listed_in"].startswith(f"{listed_in}.") and own and any(
            own <= set(_tokens(name)) for c in contributors for name in c["_names"]
        ):
            continue
        source: dict[str, Any] | None = None
        notes: list[str] = []
        if person["qid"] and snapshot is None:
            notes.append(f"wikidata_snapshot_missing:{person['qid']}")
        if snapshot is not None:
            source = wikidata_death_year(snapshot)
            if source is None:
                notes.append(f"wikidata_no_p570:{person['qid']}")
        secondary = []
        for index, entry in enumerate(entries):
            if entry.death_year is not None and _matches(match_names, entry):
                secondary.append((index, entry))
        if source is None and secondary:
            index, entry = secondary[0]
            source = {"kind": entry.source, "field": entry.field, "value": entry.value, "death_year": entry.death_year,
                      "match": "surname"}
        for index, entry in secondary:
            used.add(index)
            if source is not None and source["kind"] == "wikidata_p570" and entry.death_year != source["death_year"]:
                notes.append(f"{entry.source} gives {entry.death_year} ({entry.value}); the later year is used")
        death_year = None if source is None else max([source["death_year"], *[e.death_year for _, e in secondary if e.death_year]])
        contributors.append({
            "name": person["name"] or wikidata_label(snapshot) or person["qid"],
            "role": person["role"],
            "listed_in": person["listed_in"],
            "wikidata": person["qid"],
            "death_year": death_year,
            "death_year_source": source,
            **({"notes": notes} if notes else {}),
            "_names": match_names,
        })
    for index, entry in enumerate(entries):
        if entry.role:
            used.add(index)
    unlisted = [{"value": e.value, "source": e.source, "death_year": e.death_year}
                for i, e in enumerate(entries) if i not in used]
    basis = {
        "checked": [
            "pby_catalogue: authors, translators (author_uris, translator_uris)" if listed_in == "pby_catalogue"
            else f"{listed_in}: authors, translators, editors, annotators (Wikidata QIDs)",
            "ia_metadata: creator (role markers), title and description (title statement)",
            *(["nli_snapshot: creator and contributor fields (role markers), title statement"] if nli is not None else []),
        ],
        "counted_roles": [ROLE_AUTHOR, ROLE_TRANSLATOR, ROLE_EDITOR, ROLE_ANNOTATOR],
        "death_year_sources": ["wikidata_p570 (primary)", "ia_metadata_creator life dates", "nli_authority life dates"],
        "other_named_creators_not_counted": unlisted,
    }
    for contributor in contributors:
        contributor.pop("_names")
    return contributors, basis


def _join_years(contributors: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for role in (ROLE_AUTHOR, ROLE_TRANSLATOR, ROLE_EDITOR, ROLE_ANNOTATOR):
        years = [c["death_year"] for c in contributors if c["role"] == role and c["death_year"] is not None]
        if not years:
            continue
        label = role if len(years) == 1 else role + "s"
        parts.append(f"{label} d. " + " and ".join(str(y) for y in sorted(years)))
    return ", ".join(parts)


def build_ia_rights_justification(
    metadata: Mapping[str, Any],
    *,
    catalogue_row: Mapping[str, str],
    wikidata: Mapping[str, WikidataSnapshot],
    as_of: dt.date,
    metadata_sha256: str,
    manifest_url: str,
    manifest_sha256: str,
    canvas_count: int,
    image_urls: Sequence[str],
    nli_snapshot: NliSnapshot | None = None,
    hygiene: Any = None,
    decision: IaRightsDecision | None = None,
    contributors_listed_in: str = "pby_catalogue",
) -> JustificationResult:
    """The ``rights_justification`` of an IA item, or the reason it cannot be justified (and so is rejected).

    ``image_urls`` are the image sources actually used (the IIIF image service of each aligned canvas). ``hygiene``
    is PR B's front-matter and watermark record for a Google item; until it is given it is ``"pending"`` for Google
    items and ``"none"`` for others. ``contributors_listed_in`` is ``"pby_catalogue"`` for a PBY catalogue row and
    ``"text_record"`` for a Sefaria or Project Gutenberg text record's row (``text_sources.justification_row``).
    """

    decision = decision or decide_ia_rights(metadata)
    if not decision.accepted:
        return JustificationResult(False, f"ia_gate_rejected:{decision.reason}", [decision.reason], None)
    md = _md(metadata)
    evidence = decision.evidence()
    identifier = decision.identifier or ""
    google = decision.source_class == SOURCE_CLASS_GOOGLE
    nli_origin = bool(evidence.get("nli_evidence"))
    failures: list[str] = []

    listed_in = contributors_listed_in
    contributors, contributors_basis = _contributors(catalogue_row, md, wikidata, nli_snapshot, as_of.year, listed_in)
    anonymous = json.loads(catalogue_row["anonymous_work"]) if listed_in != "pby_catalogue" and catalogue_row.get("anonymous_work") else None
    if not any(c["role"] == ROLE_AUTHOR for c in contributors) and anonymous is None:
        failures.append("justification_no_author_listed")
    years = publication_years(md, nli_snapshot, catalogue_row, listed_in)
    year = max(y["year"] for y in years) if years else None
    if year is None:
        failures.append("justification_publication_year_missing")
    if anonymous is not None and year is not None and year + ISRAEL_TERM_YEARS >= as_of.year:
        failures.append(f"justification_anonymous_work_not_expired:{year}")
    place = publication_place(md, nli_snapshot, catalogue_row, listed_in)
    if place is None:
        failures.append("justification_publication_place_missing")

    # Israel: Copyright Act 2007, s. 38 (life + 70), or decision 10's presumption for 1855 and earlier.
    presumed = []
    for c in contributors:
        if c["death_year"] is None:
            if year is not None and year <= PRESUMPTION_CUTOFF_YEAR:
                presumed.append(c["name"])
            else:
                failures.append(f"justification_missing_death_year:{c['name']}")
        elif c["death_year"] + ISRAEL_TERM_YEARS >= as_of.year:
            failures.append(f"justification_not_pd_in_israel:{c['name']}:{c['death_year']}")
    if presumed:
        israel_status = {
            "status": "pd_il",
            "basis": "presumption_decision_10",
            "reason": f"printed {year}, on or before {PRESUMPTION_CUTOFF_YEAR}; no death year found for "
            + ", ".join(presumed) + "; presumed PD in Israel (decision 10, 2026-11-06)",
            "presumed_for": presumed,
            "law": "Copyright Act 2007, s. 38",
            "decision": DECISION_10_RECORD,
        }
    else:
        latest = max((c["death_year"] for c in contributors if c["death_year"] is not None), default=None)
        israel_status = {
            "status": "pd_il",
            "basis": "author_died_over_70_years_ago",
            "reason": f"every contributor died by {latest}; {latest} + {ISRAEL_TERM_YEARS} < {as_of.year}",
            "law": "Copyright Act 2007, s. 38",
        }
    if anonymous is not None and not presumed:
        israel_status = {
            "status": "pd_il",
            "basis": "anonymous_work_and_named_contributors_died_over_70_years_ago",
            "reason": f"anonymous work ({anonymous.get('note') or 'no author'}), edition published {year}: {year} + {ISRAEL_TERM_YEARS} < {as_of.year}"
            + (f"; every named contributor died by {latest}; {latest} + {ISRAEL_TERM_YEARS} < {as_of.year}" if latest is not None else ""),
            "anonymous_work": anonymous,
            "law": "Copyright Act 2007, ss. 38 and 40",
        }
    cutoff = as_of.year - US_TERM_YEARS
    if year is not None and year < cutoff:
        us_status = {"status": "pd_us", "reason": f"published before {cutoff}", "publication_year": year}
    else:
        us_status = {
            "status": "not_established",
            "reason": f"published {year}, not before {cutoff}; other US grounds (e.g. URAA) not assessed"
            if year is not None else "publication year unknown",
            "publication_year": year,
        }

    image_check = _image_count_check(md, canvas_count)
    if (evidence.get("mediatype") or "").lower() != "texts":
        failures.append("justification_not_a_printed_text")
    if image_check["consistent"] is False:
        failures.append(f"justification_imagecount_inconsistent:{image_check['imagecount']}:{canvas_count}")

    digitizer = evidence.get("digitizer")
    if not digitizer:
        failures.append("justification_digitizer_unknown")
    if failures:
        return JustificationResult(False, failures[0], failures, None)

    digitizer = {"name": digitizer["name"], "evidence": list(digitizer["evidence"])}
    nli_record = evidence.get("nli_record_id")
    if nli_origin:
        digitizer["origin"] = {"name": DIGITIZER_NLI, "evidence": list(evidence["nli_evidence"]), "nli_record_id": nli_record}

    origin_label: dict[str, Any] | None = None
    holders: list[str] = []
    if google:
        holders.append(DIGITIZER_GOOGLE)
        origin_label = {"holder": DIGITIZER_GOOGLE, "label": "google_books_usage_guidelines",
                        "as_found": GOOGLE_USAGE_GUIDELINES, "evidence": "Google-digitized item (digitizer evidence)"}
    if nli_origin:
        holders.append(DIGITIZER_NLI)
        snapshot_record = None
        slug = None
        if nli_snapshot is not None:
            text = (nli_snapshot.url or "") + _canonical(nli_snapshot.manifest)
            ids = {m for m in re.findall(r"99\d{10,16}5171", text)}
            if nli_record is None and len(ids) == 1:
                snapshot_record = ids.pop()
            elif nli_record is not None and nli_record in ids:
                snapshot_record = nli_record
            if snapshot_record is not None:
                slugs = [s for s in (nli_license_slug(v) for v in manifest_license_values(dict(nli_snapshot.manifest))) if s]
                slug = slugs[0] if len(set(slugs)) == 1 else None
        nli_label = {
            "holder": DIGITIZER_NLI,
            "label": slug,
            "nli_record_id": snapshot_record or nli_record,
            "checked": snapshot_record is not None,
            **({"snapshot": {"url": nli_snapshot.url, "sha256": nli_snapshot.sha256}} if snapshot_record is not None and nli_snapshot else {}),
            **({} if snapshot_record is not None else {"note": "NLI's own label for this item was not checked (no saved NLI snapshot for its record)"}),
        }
        origin_label = nli_label if origin_label is None else {**origin_label, "also": nli_label}
    why_not_binding = None
    if origin_label is not None:
        labels = ([GOOGLE_USAGE_GUIDELINES] if google else []) + (
            [f"NLI's label for it ({nli_label['label'] or 'not checked'})"] if nli_origin else []
        )
        why_not_binding = WHY_NOT_BINDING_TEMPLATE.format(
            route=f"the Internet Archive ({identifier})", holders=" or ".join(holders), label=" and ".join(labels)
        )

    if hygiene is None:
        hygiene = "pending" if google else "none"
    route_urls = [IA_METADATA_URL.format(identifier=identifier), manifest_url, *image_urls]
    pd_reason = (f"printed {year}, presumed PD (decision 10)" if presumed else f"{_join_years(contributors)}, printed {year}")
    if anonymous is not None and not presumed:
        pd_reason = "anonymous work, " + pd_reason
    digitized = f"digitized by {digitizer['name']}" + (" from an NLI copy" if nli_origin and digitizer["name"] != DIGITIZER_NLI else "")
    not_from = " or ".join(holders)
    summary = (
        f"Public-domain book ({pd_reason}); faithful scan {digitized}; fetched from the Internet Archive ({identifier})"
        + (f", not from {not_from}" if not_from else "")
        + "; no new right in the scan and no contract binds its reuse"
        + ("." if us_status["status"] == "pd_us" else "; US status not established.")
    )
    decision_refs = [
        LEGAL_STRATEGY_DECISION_RECORD + (" (including the maintainer ruling on NLI-origin files)" if nli_origin else ""),
        LEGAL_STRATEGY_DOC,
        IA_DECISION_RECORD,
        *([DECISION_10_RECORD + " (decision 10: the 1855 presumption)"] if presumed else []),
    ]
    record: dict[str, Any] = {
        "format": JUSTIFICATION_FORMAT,
        "generator": GENERATOR,
        "as_of": as_of.isoformat(),
        "ia_identifier": identifier,
        "source_class": decision.source_class,
        "route": {
            "name": IA_SOURCE,
            "url": route_urls,
            "sha256": {"metadata_snapshot": metadata_sha256, "manifest": manifest_sha256},
        },
        "work_public_domain": {
            ("pby_id" if listed_in == "pby_catalogue" else "text_work_id"): catalogue_row.get("ID"),
            "contributors": contributors,
            "contributors_basis": contributors_basis,
            "publication_year": {"year": year, "sources": years},
            "place": place,
            "israel_status": israel_status,
            "us_status": us_status,
        },
        "faithful_reproduction": {
            "text": FAITHFUL_REPRODUCTION_TEXT,
            "evidence": {"mediatype": evidence.get("mediatype"), "scanner": evidence.get("scanner"), **image_check},
        },
        "digitizer": digitizer,
        "origin_label": origin_label,
        "why_not_binding": why_not_binding,
        "route_terms": {
            "reference": ROUTE_TERMS_TEXT,
            "url": IA_TERMS_URL,
            "licenseurl": evidence.get("licenseurl"),
            "rights": evidence.get("rights"),
            "possible-copyright-status": evidence.get("possible-copyright-status"),
        },
        "hygiene": hygiene,
        "decision_refs": decision_refs,
        "summary": summary,
    }
    digest = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()
    record = {"id": f"rj:{identifier}:{digest[:12]}", **record}
    return JustificationResult(True, "rights_justified", [], record)


REASON_JUSTIFICATION_MISSING = "ia_rights_justification_missing"
REASON_GOOGLE_HYGIENE_PENDING = "google_hygiene_pending"


def ia_derivation_blocker(scan: Mapping[str, Any]) -> str | None:
    """Why no line, glyph or benchmark page may be derived from this scan yet, or None when it may.

    Every exporter of scan-derived artefacts (the line builder ``benyehuda_nli_lines``, and any glyph or benchmark
    export that takes Internet Archive scans) must call this and skip the whole scan when it returns a reason. It
    fails closed:

    - ``ia_rights_justification_missing``: an IA scan without a ``rights_justification`` id (2026-11-10 legal
      strategy, "Per-item rights justification");
    - ``google_hygiene_pending``: a Google-digitized IA scan whose justification's ``hygiene`` is not a hygiene
      record (``"pending"``, as ``justify_existing_alignment`` or an alignment made without the hygiene pass leaves
      it): its front page and watermark were never looked for (rule 5).

    NLI and other non-IA scans return None; their own gates apply.
    """

    if scan.get("source") != IA_SOURCE:
        return None
    record = scan.get("rights_justification")
    if not isinstance(record, Mapping) or not isinstance(record.get("id"), str) or not record["id"]:
        return REASON_JUSTIFICATION_MISSING
    google = SOURCE_CLASS_GOOGLE in (scan.get("source_class"), record.get("source_class"))
    if google and not isinstance(record.get("hygiene"), Mapping):
        return REASON_GOOGLE_HYGIENE_PENDING
    return None


def justify_existing_alignment(
    alignment: Mapping[str, Any],
    metadata_bytes: bytes,
    wikidata: Mapping[str, WikidataSnapshot],
    as_of: dt.date,
    *,
    catalogue_row: Mapping[str, str],
    nli_snapshot: NliSnapshot | None = None,
) -> JustificationResult:
    """Back-fill: the justification of an existing IA alignment (``alignment.json``) without re-aligning.

    ``metadata_bytes`` must be the saved IA metadata snapshot the alignment recorded (its sha256 is checked). The
    image URLs are the aligned pages' image services; the hygiene record is the alignment's, when it has one.
    """

    scan = alignment.get("scan") or {}
    if scan.get("source") != IA_SOURCE:
        return JustificationResult(False, "justification_not_an_ia_alignment", ["justification_not_an_ia_alignment"], None)
    sha = hashlib.sha256(metadata_bytes).hexdigest()
    if scan.get("metadata_snapshot_sha256") and scan["metadata_snapshot_sha256"] != sha:
        reason = "justification_metadata_snapshot_mismatch"
        return JustificationResult(False, reason, [reason], None)
    metadata = json.loads(metadata_bytes)
    if (decide_ia_rights(metadata).identifier or "") != scan.get("ia_identifier"):
        reason = "justification_metadata_identifier_mismatch"
        return JustificationResult(False, reason, [reason], None)
    work = alignment.get("work") or {}
    if str(catalogue_row.get("ID")) != str(work.get("pby_id")):
        reason = "justification_catalogue_row_mismatch"
        return JustificationResult(False, reason, [reason], None)
    pages = sorted(alignment.get("pages") or [], key=lambda page: page.get("canvas_index", 0))
    image_urls = [page["image_service"] for page in pages if page.get("image_service")]
    return build_ia_rights_justification(
        metadata,
        catalogue_row=catalogue_row,
        wikidata=wikidata,
        as_of=as_of,
        metadata_sha256=sha,
        manifest_url=scan.get("manifest_url") or "",
        manifest_sha256=scan.get("manifest_upstream_sha256") or "",
        canvas_count=int(scan.get("canvas_count") or 0),
        image_urls=image_urls,
        nli_snapshot=nli_snapshot,
        hygiene=scan.get("google_hygiene"),
    )
