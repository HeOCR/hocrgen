"""Wikimedia Commons scan files as an F8f scan source for text-source alignment (Route C, outside Wikisource).

The Wikisource pipeline already takes Commons scans through its Indexes (``hocrgen.fetchers.wikisource_justification``).
This module takes a Commons scan file that backs no Wikisource Index, and pairs it with a text-source edition
(Sefaria or Project Gutenberg; ``hocrgen.fetchers.text_sources``). The first users are Sefaria's own scans, which are on
Commons with "Scan by Sefaria of NNL_ALEPH…" in their source fields (heocr-lead, 2026-11-18, on the P-hist plan:
``docs/phist_round_inputs_plan.md``, Tier B).

Rules, from the existing decisions (no new rights rule):

- **Route C** (2026-11-10 legal strategy): public-domain files fetched from Commons are in. Every accepted file gets its
  own ``rights_justification`` (``hocrgen.rights_justification.v1``), and every line derived from it points to it.
- **The gate** (``decide_commons_rights``), fail-closed:
  1. a scan file: PDF, DjVu or an image MIME type;
  2. a public-domain template on the file page (``PD-…``), and no restrictive template (non-free, fair use, NC, ND);
  3. not Google-digitized: Google scans on Commons go through the Wikisource pipeline's hygiene pass, which this
     path does not run, so they are rejected here (``commons_google_scan_needs_wikisource_hygiene``).
  A recorded scan source is not required: under decision 10 (2026-11-06) a faithful reproduction needs none. The
  digitizer statements found ("Scan by Sefaria of …", "Scanned by …") and the NLI records cited are recorded as evidence,
  with the same checks as the IA gate (``hocrgen.fetchers.ia_iiif.known_source_from_description``).
- **Edition evidence for a Sefaria text** (recorded, never gating): when the file says Sefaria scanned it,
  ``edition_evidence`` records whether the Sefaria version is ``digitizedBySefaria`` and cites an NLI record the file
  cites, i.e. whether text and scan are the same physical copy. Whether the text matches the print is decided by the
  alignment and the per-book label audit, as for every other source.
- **The work's status** is computed as for Route B (``hocrgen.fetchers.ia_justification.work_public_domain``), from the
  text record's contributors and their saved Wikidata death years.

Page images come from Commons' per-page thumbnails of the file (``page<N>-<W>px-…jpg``). Everything here is pure: the
operator saves the Commons API response; nothing here touches the network.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from hocrgen.fetchers import ia_iiif as ia
from hocrgen.fetchers.ia_justification import (
    FAITHFUL_REPRODUCTION_TEXT,
    JUSTIFICATION_FORMAT,
    LEGAL_STRATEGY_DOC,
    DECISION_10_RECORD,
    JustificationResult,
    WikidataSnapshot,
    work_public_domain,
)

COMMONS_SOURCE = "wikimedia_commons"
COMMONS_GATE = "hocrgen.fetchers.commons_scan.decide_commons_rights"
GENERATOR = "hocrgen.fetchers.commons_scan.build_commons_rights_justification"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
COMMONS_TERMS_URL = "https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use"
SCAN_MIME_TYPES = {"application/pdf", "image/vnd.djvu", "image/x.djvu", "image/png", "image/jpeg", "image/tiff"}
RESTRICTIVE_TEMPLATE = re.compile(
    r"non-?free|fair[ _-]?use|(?:^|[-_ ])n[cd](?:$|[-_ ])|noncommercial|non-commercial|no[-_ ]?deriv|all rights reserved"
    r"|copyrighted(?![ _-]?free)",
    re.I,
)
PD_TEMPLATE = re.compile(r"^(?:PD|Public[ _]domain)\b", re.I)
GOOGLE = re.compile(r"google", re.I)
TEMPLATE_NAME = re.compile(r"\{\{\s*([^|{}\n]+?)\s*(?:\||\}\})")
INFO_FIELD = re.compile(r"^\s*\|\s*(description|source|author|date|permission|other[ _]versions)\s*=\s*(.*)$", re.I | re.M)
# A Commons per-page thumbnail: …/thumb/<a>/<ab>/<name>/page<N>-<W>px-<name>.jpg
THUMB_PAGE = re.compile(r"/page(\d+)-(\d+)px-")
THUMB_WIDTH = 1920  # a standard Commons thumbnail step; the aligner downsizes to its --image-width
SOURCE_CLASS_COMMONS = "commons_pd_scan"
SOURCE_CLASS_COMMONS_SEFARIA = "commons_sefaria_scan"
SOURCE_CLASS_COMMONS_NLI = "commons_nli_origin_scan"
ROUTE_TERMS_TEXT = (
    "Wikimedia Terms of Use, and the file's public-domain template on its file page (recorded as found). Strategy"
    " section 2(a): Commons offers public-domain files free of all restrictions."
)


def _plain(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", text)  # [[link|label]] -> label
    text = re.sub(r"\[(https?://\S+)\s+([^\]]*)\]", r"\2 (\1)", text)  # [url label] -> label (url)
    return " ".join(text.replace("&nbsp;", " ").replace("\xa0", " ").split())


def commons_file_record(api_response: Mapping[str, Any]) -> dict[str, Any]:
    """A Commons file's facts from one saved API response (``formatversion=2``; ``prop=imageinfo|revisions`` with
    ``iiprop=url|sha1|size|mime|extmetadata``, ``iiurlwidth``/``iiurlparam=page1-<W>px``, ``rvprop=ids|content``)."""

    pages = (api_response.get("query") or {}).get("pages") or []
    if len(pages) != 1 or pages[0].get("missing"):
        raise ValueError("the Commons API response must hold exactly one existing file page")
    page = pages[0]
    info = (page.get("imageinfo") or [{}])[0]
    rev = (page.get("revisions") or [{}])[0]
    wikitext = (((rev.get("slots") or {}).get("main") or {}).get("content")) or rev.get("content") or ""
    ext = info.get("extmetadata") or {}
    fields = {m.group(1).lower().replace(" ", "_"): m.group(2).strip() for m in INFO_FIELD.finditer(wikitext)}
    templates = sorted({m.group(1).strip() for m in TEMPLATE_NAME.finditer(wikitext)})
    licence_short = (ext.get("LicenseShortName") or {}).get("value")
    return {
        "title": page.get("title"),
        "pageid": page.get("pageid"),
        "file_page_revision_id": rev.get("revid"),
        "url": info.get("url"),
        "descriptionurl": info.get("descriptionurl"),
        "thumburl": info.get("thumburl"),
        "sha1": info.get("sha1"),
        "mime": info.get("mime"),
        "size": info.get("size"),
        "width": info.get("width"),
        "height": info.get("height"),
        "page_count": info.get("pagecount"),
        "templates": templates,
        "licence_templates": [t for t in templates if PD_TEMPLATE.search(t) or RESTRICTIVE_TEMPLATE.search(t)],
        "licence_short_name": licence_short,
        "description": _plain(fields.get("description") or (ext.get("ImageDescription") or {}).get("value") or ""),
        "source": _plain(fields.get("source") or (ext.get("Credit") or {}).get("value") or ""),
        "author": _plain(fields.get("author") or (ext.get("Artist") or {}).get("value") or ""),
        "date": _plain(fields.get("date") or (ext.get("DateTimeOriginal") or {}).get("value") or ""),
        "categories": [c for c in ((ext.get("Categories") or {}).get("value") or "").split("|") if c],
    }


@dataclasses.dataclass(frozen=True)
class CommonsRightsDecision:
    """The Commons gate's verdict on one file, with the evidence it rests on (``record``)."""

    accepted: bool
    reason: str
    source_class: str | None
    title: str | None
    record: dict[str, Any]

    def evidence(self) -> dict[str, Any]:
        return dict(self.record)


def decide_commons_rights(file: Mapping[str, Any], *, sefaria_version: Mapping[str, Any] | None = None) -> CommonsRightsDecision:
    """Apply the Route C conditions to a ``commons_file_record``; see the module docstring."""

    md = {"description": file.get("description") or "", "source": file.get("source") or "", "notes": file.get("author") or ""}
    statements = ia.known_source_from_description(md, sefaria_version)
    google = [f"{k}: {v}" for k in ("description", "source", "author") if GOOGLE.search(str(file.get(k) or "")) for v in [file.get(k)]]
    google += [f"category: {c}" for c in file.get("categories") or [] if GOOGLE.search(c)]
    templates = [str(t) for t in file.get("licence_templates") or []] + ([str(file["licence_short_name"])] if file.get("licence_short_name") else [])
    failures: list[str] = []
    if (file.get("mime") or "") not in SCAN_MIME_TYPES:
        failures.append(f"commons_not_a_scan_file:{file.get('mime')}")
    restrictive = [t for t in templates if RESTRICTIVE_TEMPLATE.search(t)]
    if restrictive:
        failures.append(f"commons_restrictive_template:{restrictive[0]}")
    if not any(PD_TEMPLATE.search(t) for t in templates):
        failures.append("commons_no_public_domain_template")
    if google:
        failures.append("commons_google_scan_needs_wikisource_hygiene")
    sefaria_statements = [s for s in statements["statements"] if s["kind"] == "sefaria"]
    # Edition evidence, not a rights condition (Route C needs no recorded scan source, decision 10): whether the file's
    # Sefaria statement and the Sefaria version cite the same NLI record. Alignment and the label audit decide the match.
    edition_evidence = None
    if sefaria_version is not None and sefaria_statements:
        ok = any(s["accepted"] for s in sefaria_statements)
        edition_evidence = {"same_copy_as_sefaria_version": ok,
                            "check": "sefaria_version_cites_same_nli_record" if ok else sefaria_statements[0]["check"].replace("ia_", "commons_", 1),
                            "sefaria_version": statements.get("sefaria_version")}
    accepted = not failures
    if statements["established"]:
        digitizer = {"name": statements["digitizer"],
                     "evidence": [f"{s['field']}: {s['quote']}" for s in statements["statements"] if s["accepted"]],
                     "source_established": statements}
    else:
        digitizer = {"name": "unrecorded", "evidence": [], "basis": "decision 10: a faithful reproduction needs no recorded scan source",
                     "source_established": statements}
    if not accepted:
        source_class = None
    elif digitizer["name"] == ia.DIGITIZER_SEFARIA:
        source_class = SOURCE_CLASS_COMMONS_SEFARIA
    elif digitizer["name"] == ia.DIGITIZER_NLI or statements["nli_record_ids"] and any(s["kind"] == "nli" for s in statements["statements"]):
        source_class = SOURCE_CLASS_COMMONS_NLI
    else:
        source_class = SOURCE_CLASS_COMMONS
    record = {
        "gate": COMMONS_GATE,
        "decision_record": ia.LEGAL_STRATEGY_DECISION_RECORD,
        "title": file.get("title"),
        "sha1": file.get("sha1"),
        "mime": file.get("mime"),
        "page_count": file.get("page_count"),
        "file_page_revision_id": file.get("file_page_revision_id"),
        "licence_templates": templates,
        "google_evidence": google,
        "nli_record_ids": statements["nli_record_ids"],
        "digitizer": digitizer,
        "edition_evidence": edition_evidence,
        "decision": "accepted" if accepted else "rejected",
        "reason": failures[0] if failures else "commons_pd_scan_accepted",
        "failed_conditions": failures,
        "source_class": source_class,
    }
    return CommonsRightsDecision(accepted, record["reason"], source_class, file.get("title"), record)


def page_thumb_url(file: Mapping[str, Any], page: int, width: int = THUMB_WIDTH) -> str:
    """The URL of page ``page`` (1-based) of a multi-page file, from the saved page-1 thumbnail URL."""

    thumb = str(file.get("thumburl") or "").split("?", 1)[0]  # Commons appends tracking parameters
    if not THUMB_PAGE.search(thumb):
        raise ValueError("the saved response has no per-page thumbnail URL (request iiurlparam=page1-<W>px)")
    return THUMB_PAGE.sub(f"/page{page}-{width}px-", thumb, count=1)


def commons_canvases(file: Mapping[str, Any], width: int = THUMB_WIDTH) -> list[dict[str, Any]]:
    """One v2-shaped canvas per page of the file, as the F8f aligner reads them (no IIIF service: ``image_url``)."""

    count = int(file.get("page_count") or 0)
    if count < 1:
        raise ValueError("the file has no page count")
    base = str(file.get("descriptionurl") or "")
    return [{"@id": f"{base}?page={n}", "label": str(n), "width": width, "height": None,
             "image_url": page_thumb_url(file, n, width)} for n in range(1, count + 1)]


def build_commons_rights_justification(
    file: Mapping[str, Any],
    decision: CommonsRightsDecision,
    *,
    catalogue_row: Mapping[str, str],
    wikidata: Mapping[str, WikidataSnapshot],
    as_of: dt.date,
    api_snapshot_sha256: str,
    image_urls: Sequence[str],
) -> JustificationResult:
    """The ``rights_justification`` of a Commons file paired with a text record, or why it cannot be justified."""

    if not decision.accepted:
        return JustificationResult(False, f"commons_gate_rejected:{decision.reason}", [decision.reason], None)
    wpd = work_public_domain({}, catalogue_row=catalogue_row, wikidata=wikidata, as_of=as_of, contributors_listed_in="text_record")
    failures = list(wpd["failures"])
    if not file.get("url") or not file.get("sha1"):
        failures.append("justification_file_url_or_sha1_missing")
    if failures:
        return JustificationResult(False, failures[0], failures, None)
    evidence = decision.evidence()
    digitizer = evidence["digitizer"]
    year, presumed, anonymous = wpd["year"], wpd["presumed"], wpd["anonymous"]
    from hocrgen.fetchers.ia_justification import _join_years  # noqa: PLC0415 - shared summary helper

    pd_reason = f"printed {year}, presumed PD (decision 10)" if presumed else f"{_join_years(wpd['contributors'])}, printed {year}"
    if anonymous is not None and not presumed:
        pd_reason = "anonymous work, " + pd_reason
    title = str(file.get("title") or "")
    summary = (
        f"Public-domain book ({pd_reason}); faithful scan, digitized by {digitizer['name']}; fetched from Wikimedia"
        f" Commons ({title}); no new right in the scan and no contract binds its reuse"
        + ("." if wpd["us_status"]["status"] == "pd_us" else "; US status not established.")
    )
    record: dict[str, Any] = {
        "format": JUSTIFICATION_FORMAT,
        "generator": GENERATOR,
        "as_of": as_of.isoformat(),
        "commons_file": title,
        "source_class": decision.source_class,
        "route": {"name": COMMONS_SOURCE, "url": [file.get("descriptionurl"), file.get("url"), *image_urls],
                  "sha1": file.get("sha1"), "file_page_revision_id": file.get("file_page_revision_id"),
                  "sha256": {"api_snapshot": api_snapshot_sha256}},
        "work_public_domain": {
            "text_work_id": catalogue_row.get("ID"),
            "contributors": wpd["contributors"],
            "contributors_basis": wpd["contributors_basis"],
            "publication_year": {"year": year, "sources": wpd["years"]},
            "place": wpd["place"],
            "israel_status": wpd["israel_status"],
            "us_status": wpd["us_status"],
        },
        "faithful_reproduction": {"text": FAITHFUL_REPRODUCTION_TEXT,
                                  "evidence": {"mime": file.get("mime"), "page_count": file.get("page_count"),
                                               "licence_templates": evidence["licence_templates"]}},
        "digitizer": digitizer,
        "origin_label": None,
        "why_not_binding": None,
        "route_terms": {"reference": ROUTE_TERMS_TEXT, "url": COMMONS_TERMS_URL, "licence_templates": evidence["licence_templates"]},
        "hygiene": "none",
        "decision_refs": [ia.LEGAL_STRATEGY_DECISION_RECORD, LEGAL_STRATEGY_DOC,
                          *([DECISION_10_RECORD + " (decision 10: no recorded scan source needed)"] if digitizer["name"] == "unrecorded" else []),
                          *([DECISION_10_RECORD + " (decision 10: the 1855 presumption)"] if presumed else [])],
        "summary": summary,
    }
    digest = hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    key = re.sub(r"[^\w.-]+", "_", title.removeprefix("File:"))[:80]
    record = {"id": f"rj:commons:{key}:{digest[:12]}", **record}
    return JustificationResult(True, "rights_justified", [], record)


def commons_derivation_blocker(scan: Mapping[str, Any]) -> str | None:
    """Why no line may be derived from a Commons scan yet (no ``rights_justification`` id), or None. Fails closed."""

    if scan.get("source") != COMMONS_SOURCE:
        return None
    record = scan.get("rights_justification") or {}
    return None if isinstance(record, Mapping) and str(record.get("id") or "").startswith("rj:") else "commons_rights_justification_missing"
