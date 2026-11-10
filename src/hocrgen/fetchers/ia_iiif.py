"""Internet Archive (IA) scans as a second F8f scan source (Route B): rights gate and IIIF v3 canvas adapter.

The maintainer allowed non-Google library scans on IA for the PBY alignment on 2026-11-09
(``planning/decisions/2026-11-09-internet-archive-library-scans.md``). The 2026-11-10 legal strategy
(``planning/decisions/2026-11-10-legal-strategy.md``) superseded that decision's condition 2 (no Google scans) and,
by the maintainer's ruling on NLI-origin files, its condition 4 (no files from NLI) for files fetched from IA.
``decide_ia_rights`` applies the remaining conditions 1, 3 and 5 to an item's IA metadata
(``https://archive.org/metadata/<identifier>``), accepts Google-digitized and NLI-origin items with their own
``source_class``, and records the digitizer and NLI evidence it found. The NLI gate
(``hocrgen.fetchers.nli_iiif.decide_nli_rights``) is unchanged and is never applied to IA items. Every accepted item
also needs a per-item rights justification (``hocrgen.fetchers.ia_justification``).

``ia_v3_canvases`` turns an IA IIIF Presentation v3 manifest (``iiif.archive.org/iiif/3/<identifier>/manifest.json``;
IA serves v3 only) into the v2-shaped canvas dicts the F8f aligner reads (``@id``, ``label``, ``width``,
``height`` and ``images[0].resource.service.@id``), so the aligner's page records are built the same way for both
sources.

Both functions are pure: the operator fetches and saves the metadata and manifest; nothing here touches the network.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from typing import Any

IA_SOURCE = "internet_archive"
IA_GATE = "hocrgen.fetchers.ia_iiif.decide_ia_rights"
IA_DECISION_RECORD = "planning/decisions/2026-11-09-internet-archive-library-scans.md"
LEGAL_STRATEGY_DECISION_RECORD = "planning/decisions/2026-11-10-legal-strategy.md"
IA_METADATA_URL = "https://archive.org/metadata/{identifier}"
IA_MANIFEST_URL = "https://iiif.archive.org/iiif/3/{identifier}/manifest.json"

# Source classes recorded in ``scan.source_class``.
SOURCE_CLASS_NO_LICENCE = "ia_library_scan_no_licence_field"
SOURCE_CLASS_PD_MARK = "ia_library_scan_public_domain_mark"
SOURCE_CLASS_CC0 = "ia_library_scan_cc0"
SOURCE_CLASS_RIGHTS_PD = "ia_library_scan_rights_statement_public_domain"
SOURCE_CLASS_GOOGLE = "ia_google_digitized_scan"
SOURCE_CLASS_NLI_ORIGIN = "ia_nli_origin_scan"

DIGITIZER_GOOGLE = "Google"
DIGITIZER_NLI = "National Library of Israel"

PUBLIC_DOMAIN_LICENCES = {
    "creativecommons.org/publicdomain/mark/1.0": SOURCE_CLASS_PD_MARK,
    "creativecommons.org/publicdomain/zero/1.0": SOURCE_CLASS_CC0,
}
# ``possible-copyright-status`` values that say the book is out of copyright (compared case-insensitively).
PUBLIC_DOMAIN_STATUSES = frozenset(
    {
        "not_in_copyright",
        "not in copyright",
        "public domain",
        "public_domain",
        "the internet archive is unaware of any copyright restrictions on this item.",
    }
)
GOOGLE = re.compile(r"google", re.I)
GOOGLE_DESCRIPTION = re.compile(r"google\s*books|digiti[sz]ed\s+by\s+google|from\s+google", re.I)
# IA's Google Books imports: ``bub_gb_<id>`` and the older ``<title><nn><author>goog`` identifiers.
GOOGLE_IDENTIFIER = re.compile(r"^bub_gb_|goog$", re.I)
NLI = re.compile(
    r"national\s+library\s+of\s+israel|jewish\s+national\s+(and|&)\s+university\s+library|nli\.org\.il|"
    r"\bJNUL\b|הספרייה\s+הלאומית|הספריה\s+הלאומית",
    re.I,
)
ANONYMOUS = frozenset({"", "anonymous", "unknown", "n/a", "none", "-"})
RESTRICTIVE = re.compile(
    r"non[\s-]?commercial|\bby-nc\b|-nc\b|not\s+for\s+commercial|all\s+rights\s+reserved|permission|"
    r"personal\s+use|educational\s+use\s+only|research\s+use\s+only",
    re.I,
)
PUBLIC_DOMAIN_RIGHTS = re.compile(r"public\s+domain|no\s+known\s+copyright\s+restrictions|not\s+in\s+copyright", re.I)

GOOGLE_FIELDS = ("scanner", "contributor", "sponsor", "collection")
NLI_FIELDS = ("contributor", "sponsor", "collection", "source", "description", "notes", "provenance")
# An NLI record id (``99…5171``), as cited in an IA item's source, notes or description.
NLI_RECORD_ID = re.compile(r"(?<!\d)(99\d{10,16}5171)(?!\d)")


def _values(metadata: Mapping[str, Any], key: str) -> list[str]:
    value = metadata.get(key)
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    return [str(item).strip() for item in items if item is not None and str(item).strip()]


def _one(metadata: Mapping[str, Any], key: str) -> str | None:
    values = _values(metadata, key)
    return "; ".join(values) if values else None


def _licence_key(url: str) -> str:
    return re.sub(r"^https?://", "", url.strip().lower()).rstrip("/")


@dataclasses.dataclass(frozen=True)
class IaRightsDecision:
    """The gate's verdict on one IA item and the metadata it rests on."""

    accepted: bool
    reason: str
    source_class: str | None
    identifier: str | None
    record: dict[str, Any]

    def evidence(self) -> dict[str, Any]:
        return dict(self.record)


def google_evidence(md: Mapping[str, Any]) -> list[str]:
    """Why an item is a Google-digitized scan: the fields, identifier pattern or description that name Google."""

    found: list[str] = []
    for field in GOOGLE_FIELDS:
        for value in _values(md, field):
            if GOOGLE.search(value):
                found.append(f"{field}: {value}")
    identifier = _one(md, "identifier")
    if identifier and GOOGLE_IDENTIFIER.search(identifier):
        pattern = "bub_gb_" if identifier.lower().startswith("bub_gb_") else "goog"
        found.append(f"identifier: {identifier} (Google Books import pattern {pattern})")
    for value in _values(md, "description"):
        if GOOGLE_DESCRIPTION.search(value):
            found.append(f"description: {value}")
    return found


def nli_evidence(md: Mapping[str, Any]) -> list[str]:
    """Why an item came from NLI: the fields that name it."""

    return [f"{field}: {value}" for field in NLI_FIELDS for value in _values(md, field) if NLI.search(value)]


def nli_record_id(md: Mapping[str, Any]) -> str | None:
    """The NLI record id an item cites, when exactly one is cited."""

    ids = {match for field in NLI_FIELDS for value in _values(md, field) for match in NLI_RECORD_ID.findall(value)}
    return ids.pop() if len(ids) == 1 else None


def decide_ia_rights(metadata: Mapping[str, Any]) -> IaRightsDecision:
    """Apply the IA conditions still in force (2026-11-09 decision, as amended on 2026-11-10) to an item's metadata.

    ``metadata`` is the ``/metadata/<identifier>`` response or its ``metadata`` object. Conditions, in order; the
    first failure is the reason:

    1. a public-domain printed book: ``mediatype`` is ``texts`` and ``possible-copyright-status``, when present,
       says not in copyright. (That the scan is the edition a PBY text was typed from is shown by the alignment.)
    2. superseded by the 2026-11-10 legal strategy: a Google scan is accepted. It is detected when ``scanner``,
       ``contributor``, ``sponsor`` or ``collection`` names Google, the identifier is a Google Books import
       (``bub_gb_…``, ``…goog``), or the description says it came from Google Books; the evidence is recorded and
       the item gets ``source_class: ia_google_digitized_scan``.
    3. a known source: ``contributor`` names a library (no anonymous uploads), or the item is Google-digitized (a
       known digitizer). An item with neither is rejected.
    4. lifted for IA by the maintainer's 2026-11-10 ruling on NLI-origin files: an item whose contributor, sponsor,
       collection, source, description, notes or provenance names NLI is accepted with its NLI evidence (and the NLI
       record id it cites) and ``source_class: ia_nli_origin_scan``. An item that is both keeps the Google class.
    5. nothing restrictive: ``licenseurl``, when present, is a public-domain mark or CC0, and ``rights``, when
       present, states public domain and nothing restrictive (a rights statement that is neither is unclear and
       rejected).
    """

    inner = metadata.get("metadata")
    md: Mapping[str, Any] = inner if isinstance(inner, Mapping) else metadata
    identifier = _one(md, "identifier")
    licenseurl = _one(md, "licenseurl")
    rights = _one(md, "rights")
    status = _one(md, "possible-copyright-status")
    contributor = _one(md, "contributor")
    google = google_evidence(md)
    nli = nli_evidence(md)
    record: dict[str, Any] = {
        "gate": IA_GATE,
        "decision_record": IA_DECISION_RECORD,
        "amended_by": LEGAL_STRATEGY_DECISION_RECORD,
        "identifier": identifier,
        "mediatype": _one(md, "mediatype"),
        "date": _one(md, "date"),
        "scanner": _one(md, "scanner"),
        "contributor": contributor,
        "sponsor": _one(md, "sponsor"),
        "collections": _values(md, "collection"),
        "possible-copyright-status": status,
        "licenseurl": licenseurl,
        "rights": rights,
        "google_evidence": google,
        "nli_evidence": nli,
        "nli_record_id": nli_record_id(md) if nli else None,
    }

    def failures() -> list[str]:
        found: list[str] = []
        if not identifier:
            found.append("ia_identifier_missing")
        # 1. public-domain printed book
        if (record["mediatype"] or "").lower() != "texts":
            found.append(f"ia_not_a_printed_text:{record['mediatype']}")
        if status is not None and status.strip().lower() not in PUBLIC_DOMAIN_STATUSES:
            found.append(f"ia_copyright_status_not_public_domain:{status}")
        # 3. known source: a named library, or Google as a known digitizer
        if (not contributor or contributor.strip().lower() in ANONYMOUS) and not google:
            found.append("ia_anonymous_upload_no_known_library")
        # 5. nothing restrictive
        if licenseurl is not None and _licence_key(licenseurl) not in PUBLIC_DOMAIN_LICENCES:
            kind = "non_commercial" if RESTRICTIVE.search(licenseurl) else "not_public_domain"
            found.append(f"ia_licence_{kind}:{licenseurl}")
        if rights is not None:
            if RESTRICTIVE.search(rights):
                found.append("ia_rights_restrictive")
            elif not PUBLIC_DOMAIN_RIGHTS.search(rights):
                found.append("ia_rights_unclear")
        return found

    failed = failures()
    accepted = not failed
    if not accepted:
        source_class = None
    elif google:
        source_class = SOURCE_CLASS_GOOGLE
    elif nli:
        source_class = SOURCE_CLASS_NLI_ORIGIN
    elif licenseurl is not None:
        source_class = PUBLIC_DOMAIN_LICENCES[_licence_key(licenseurl)]
    elif rights is not None:
        source_class = SOURCE_CLASS_RIGHTS_PD
    else:
        source_class = SOURCE_CLASS_NO_LICENCE
    if not accepted:
        reason = failed[0]
    elif google:
        reason = "ia_google_digitized_scan_accepted"
    elif nli:
        reason = "ia_nli_origin_scan_accepted"
    else:
        reason = "ia_library_scan_accepted"
    if google:
        digitizer: dict[str, Any] | None = {"name": DIGITIZER_GOOGLE, "evidence": google}
    elif nli and contributor and NLI.search(contributor):
        digitizer = {"name": DIGITIZER_NLI, "evidence": [f"contributor: {contributor}"]}
    elif contributor and contributor.strip().lower() not in ANONYMOUS:
        digitizer = {"name": contributor, "evidence": [f"contributor: {contributor}"]}
    else:
        digitizer = None
    if digitizer is not None:
        for key in ("scanner", "sponsor"):
            line = f"{key}: {record[key]}"
            if record[key] and line not in digitizer["evidence"]:
                digitizer["evidence"].append(line)
    record.update(
        {
            "digitizer": digitizer,
            "decision": "accepted" if accepted else "rejected",
            "reason": reason,
            "failed_conditions": failed,
            "source_class": source_class,
        }
    )
    return IaRightsDecision(accepted=accepted, reason=reason, source_class=source_class, identifier=identifier, record=record)


# --- IIIF v3 canvases ---------------------------------------------------------------------------------------


def _label(value: Any) -> str | None:
    """A IIIF v3 language map (``{"none": ["4"]}``) as one string."""

    if isinstance(value, Mapping):
        for items in value.values():
            if isinstance(items, list) and items:
                return "; ".join(str(item) for item in items)
        return None
    return None if value is None else str(value)


def _image_service(canvas: Mapping[str, Any]) -> tuple[str | None, str | None]:
    for page in canvas.get("items") or []:
        for annotation in (page or {}).get("items") or []:
            body = (annotation or {}).get("body") or {}
            services = body.get("service") or []
            services = services if isinstance(services, list) else [services]
            for service in services:
                service_id = (service or {}).get("id") or (service or {}).get("@id")
                if isinstance(service_id, str) and service_id:
                    return service_id, body.get("id")
    return None, None


def ia_v3_canvases(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The canvases of an IA IIIF v3 manifest, shaped like v2 canvases for the aligner."""

    canvases: list[dict[str, Any]] = []
    for canvas in manifest.get("items") or []:
        if not isinstance(canvas, Mapping) or canvas.get("type") != "Canvas":
            continue
        service, image = _image_service(canvas)
        canvases.append(
            {
                "@id": canvas.get("id"),
                "@type": "sc:Canvas",
                "label": _label(canvas.get("label")),
                "width": canvas.get("width"),
                "height": canvas.get("height"),
                "images": [{"resource": {"@id": image, "service": {"@id": service}}}],
            }
        )
    return canvases


def manifest_label(manifest: Mapping[str, Any]) -> str | None:
    return _label(manifest.get("label"))


def manifest_provider(manifest: Mapping[str, Any]) -> str | None:
    providers = manifest.get("provider") or []
    labels = [_label((provider or {}).get("label")) for provider in providers if isinstance(provider, Mapping)]
    labels = [label for label in labels if label]
    return "; ".join(labels) if labels else None
