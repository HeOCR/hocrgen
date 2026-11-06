"""F8e: born-digital and typewritten Israeli government print, as fixture-backed review-only sources.

Two packaged-static-records adapters over pinned snapshots:

- ``reshumot``: pages of ספר החוקים and קובץ התקנות booklets from 2006 on (Copyright Act section 6). Each
  page is rendered from the born-digital PDF (``rendering.is_scan`` false, so evaluation never mistakes it
  for a scan) and carries the PDF's embedded text in logical order. The text is admitted only when the
  committed pdftotext output converts to it exactly and it passes the logical-order checks of
  ``hocrgen.parsers.pdf_bidi``.
- ``knesset_committee``: page scans of Knesset committee protocols from sessions on or before
  1975-12-31 (State works, sections 36 and 42). Images only; the upstream OCR is never carried.

Both start ``review_only``. Text is carried by reference and checksum; it becomes a scored reference only
through the F2 attestation and adjudication path.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_yaml_file
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord
from hocrgen.parsers.pdf_bidi import logical_order_issues, poppler_text_to_logical
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file

GOVERNMENT_PRINT_SNAPSHOT_SETTING = "government_print_snapshot_root"
RASTER_MEDIA_TYPES = {"image/png", "image/jpeg"}

# Reshumot. Only laws (ספר החוקים, FolderType 1) and regulations (קובץ התקנות, FolderType 3) are section-6
# material. ילקוט הפרסומים (2), bills (6, 8) and the other series are not.
RESHUMOT_SECTION_6_SERIES = {"1": "sefer_hachukim", "3": "kovetz_hatakanot"}
RESHUMOT_BORN_DIGITAL_FROM = date(2006, 1, 1)

# Knesset committees. Maintainer decision 5 (2026-11-06): protocols from 1976 on wait for a legal opinion.
KNESSET_SESSION_DATE_CUTOFF = date(1975, 12, 31)
KNESSET_PROTOCOL_GROUP_TYPE_ID = 23  # "פרוטוקול ועדה"
KNESSET_BACKGROUND_MATERIAL_GROUP_TYPE_ID = 87  # "חומר רקע"
KNESSET_OPEN_SESSION_TYPE = "פתוחה"
_DOCUMENT_NAME_DATE = re.compile(r"(\d{2})/(\d{2})/(\d{4})")

# Reasons that mean the packaged fixture itself is broken, not that an entry is out of scope.
GOVERNMENT_PRINT_INTEGRITY_REASONS = frozenset(
    {"text_checksum_mismatch", "extraction_checksum_mismatch", "text_not_reproducible_from_extraction", "missing_text_file"}
)


def government_print_snapshot_root(source: SourceConfig, bundle: ConfigBundle) -> Path:
    reference = source.settings.extra.get(GOVERNMENT_PRINT_SNAPSHOT_SETTING)
    if not isinstance(reference, str) or not reference:
        raise StageExecutionError(f"{source.id} requires settings.extra.{GOVERNMENT_PRINT_SNAPSHOT_SETTING}")
    return bundle.resolve_path(reference)


def load_government_print_snapshot(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshot = load_yaml_file(root / "snapshot.yaml")
    entries_path = root / str(snapshot.get("entries_path", "entries.jsonl"))
    entries = [json.loads(line) for line in entries_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return snapshot, entries


def government_print_entry_asset(entry: dict[str, Any]) -> dict[str, Any] | None:
    for file in entry.get("files") or []:
        if file.get("mime_type") in RASTER_MEDIA_TYPES and file.get("local_path") and file.get("sha256"):
            return file
    return None


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _common_exclusion_reasons(entry: dict[str, Any], source: SourceConfig) -> list[str]:
    rights = entry.get("rights") or {}
    if rights.get("license_expression") not in source.rights_strategy.values:
        return ["license_not_in_source_lane"]
    if rights.get("verification_status") != "primary_page_checked":
        return ["rights_not_primary_page_checked"]
    if entry.get("content_type") not in source.allowed_content_types:
        return ["content_type_not_allowed"]
    return []


def reshumot_text_issues(entry: dict[str, Any], root: Path) -> list[str]:
    """Re-derive the page text from the committed pdftotext output and check its logical order.

    Returns integrity reasons (a pinned file is missing or changed) or the order issue codes of
    ``hocrgen.parsers.pdf_bidi``. An empty list means the text is admitted.
    """

    text = entry.get("text") or {}
    extraction = text.get("extraction") or {}
    raw_path = root / str(extraction.get("raw_local_path", ""))
    text_path = root / str(text.get("local_path", ""))
    if not raw_path.is_file() or not text_path.is_file():
        return ["missing_text_file"]
    if sha256_file(raw_path) != extraction.get("raw_sha256"):
        return ["extraction_checksum_mismatch"]
    if sha256_file(text_path) != text.get("sha256"):
        return ["text_checksum_mismatch"]
    logical = text_path.read_bytes().decode("utf-8")
    converted, conversion_issues = poppler_text_to_logical(raw_path.read_bytes().decode("utf-8"))
    if converted != logical:
        return ["text_not_reproducible_from_extraction"]
    expected = [str(item.get("text", "")) for item in (text.get("order_verification") or {}).get("expected_phrases") or []]
    if not expected:
        return ["no_expected_phrases"]
    return sorted(set(conversion_issues) | set(logical_order_issues(logical, expected)))


def reshumot_entry_exclusion_reasons(entry: dict[str, Any], source: SourceConfig, root: Path) -> list[str]:
    """Return why a Reshumot page cannot become a candidate (first reason first), or [] when eligible."""

    common = _common_exclusion_reasons(entry, source)
    if common:
        return common
    booklet = entry.get("booklet") or {}
    if str(booklet.get("folder_type")) not in RESHUMOT_SECTION_6_SERIES:
        return ["series_not_section_6"]
    if RESHUMOT_SECTION_6_SERIES[str(booklet["folder_type"])] != booklet.get("series"):
        return ["series_folder_type_mismatch"]
    published = _parse_date(booklet.get("publish_date"))
    if published is None:
        return ["publish_date_unknown"]
    if published < RESHUMOT_BORN_DIGITAL_FROM:
        return ["before_born_digital_era"]
    pdf = entry.get("pdf") or {}
    if pdf.get("born_digital") is not True or pdf.get("page_image_count") != 0 or not pdf.get("embedded_fonts") or not pdf.get("sha256"):
        return ["pdf_not_born_digital"]
    if not booklet.get("booklet_number"):
        return ["missing_booklet_number"]
    text = entry.get("text") or {}
    if text.get("text_provenance") != "born_digital_pdf_text":
        return ["unsupported_text_provenance"]
    if text.get("adjudication_status") != "not_adjudicated" or text.get("reference_eligible") is not False:
        # Adjudication and reference eligibility come only from the F2 path.
        return ["unsupported_reference_status"]
    issues = reshumot_text_issues(entry, root)
    if issues:
        integrity = [issue for issue in issues if issue in GOVERNMENT_PRINT_INTEGRITY_REASONS]
        return integrity or ["extraction_order_not_verified", *issues]
    asset = government_print_entry_asset(entry)
    if asset is None:
        return ["no_raster_asset"]
    rendering = asset.get("rendering") or {}
    if rendering.get("is_scan") is not False or rendering.get("image_origin") != "rendered_from_born_digital_pdf":
        return ["rendering_provenance_unrecorded"]
    if not rendering.get("renderer") or not rendering.get("renderer_version") or not rendering.get("dpi"):
        return ["rendering_provenance_unrecorded"]
    return []


def knesset_entry_exclusion_reasons(entry: dict[str, Any], source: SourceConfig, root: Path | None = None) -> list[str]:
    """Return why a Knesset committee page cannot become a candidate, or [] when eligible."""

    common = _common_exclusion_reasons(entry, source)
    if common:
        return common
    document = entry.get("document") or {}
    if document.get("group_type_id") == KNESSET_BACKGROUND_MATERIAL_GROUP_TYPE_ID or document.get("group_type_desc") == "חומר רקע":
        return ["committee_background_material_not_knesset_work"]
    if document.get("group_type_id") != KNESSET_PROTOCOL_GROUP_TYPE_ID:
        return ["document_not_committee_protocol"]
    session = entry.get("session") or {}
    session_date = _parse_date(session.get("start_date"))
    if session_date is None:
        return ["session_date_unknown"]
    if session_date > KNESSET_SESSION_DATE_CUTOFF:
        return ["post_1975_committee_protocol_pending_legal_opinion"]
    name_date = _DOCUMENT_NAME_DATE.search(str(document.get("document_name", "")))
    if name_date is None or date(int(name_date.group(3)), int(name_date.group(2)), int(name_date.group(1))) != session_date:
        return ["session_date_mismatch"]
    if document.get("committee_session_id") != session.get("committee_session_id"):
        return ["session_id_mismatch"]
    if session.get("type_desc") != KNESSET_OPEN_SESSION_TYPE:
        return ["session_not_open"]
    if not (entry.get("committee") or {}).get("name"):
        return ["committee_unknown"]
    text = entry.get("text") or {}
    if text.get("local_path") or text.get("text_provenance") != "none":
        # The scanned-era DOC and PDF text layers are Imagestore OCR: never ground truth, never carried.
        return ["upstream_ocr_text_not_allowed"]
    asset = government_print_entry_asset(entry)
    if asset is None:
        return ["no_raster_asset"]
    scan = asset.get("scan") or {}
    if scan.get("is_scan") is not True or not scan.get("x_ppi") or not scan.get("extractor_version"):
        return ["scan_provenance_unrecorded"]
    if not (entry.get("pdf") or {}).get("sha256"):
        return ["missing_pdf_checksum"]
    return []


class _GovernmentPrintImporter:
    fetcher_key = ""
    discovery_method = ""

    def exclusion_reasons(self, entry: dict[str, Any], source: SourceConfig, root: Path) -> list[str]:
        raise NotImplementedError

    def source_url(self, entry: dict[str, Any]) -> str:
        raise NotImplementedError

    def entry_metadata(self, entry: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = government_print_snapshot_root(source, bundle)
        snapshot, entries = load_government_print_snapshot(root)
        candidates: list[CandidateRecord] = []
        for entry in sorted(entries, key=lambda record: record["entry_id"]):
            if self.exclusion_reasons(entry, source, root):
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{entry['entry_id']}",
                    source_id=source.id,
                    source_item_id=entry["entry_id"],
                    source_url=self.source_url(entry),
                    discovery_method=self.discovery_method,
                    title=entry["title"],
                    raw_metadata={"snapshot_root": str(root), "captured_at": str(snapshot.get("captured_at")), "entry": entry},
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            entry = candidate.raw_metadata["entry"]
            root = Path(candidate.raw_metadata["snapshot_root"])
            asset = government_print_entry_asset(entry) or {}
            rights = entry["rights"]
            metadata = {
                "content_type": entry["content_type"],
                "languages": entry["languages"],
                "script": entry.get("script"),
                "upstream_identifier": entry["entry_id"],
                "upstream_captured_at": candidate.raw_metadata.get("captured_at"),
                "rights_basis": rights.get("basis"),
                "rights_evidence": rights.get("evidence_text"),
                "rights_verified_at": rights.get("verified_at"),
                "expected_asset_sha256": asset.get("sha256"),
                "expected_pixel_sha256": asset.get("pixel_sha256"),
                "upstream_pdf_sha256": (entry.get("pdf") or {}).get("sha256"),
                **self.entry_metadata(entry),
            }
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=rights["license_expression"],
                    asset_references=[
                        AssetReference(
                            reference=asset["local_path"],
                            resolved_path=str((root / asset["local_path"]).resolve()),
                            media_type=asset["mime_type"],
                        )
                    ],
                    metadata=metadata,
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            asset = item.asset_references[0]
            resolved = Path(asset.resolved_path or "")
            snapshot_root = resolved.parents[len(PurePosixPath(asset.reference).parts) - 1]
            text_reference = item.metadata.get("text_reference")
            if text_reference:
                text_path = snapshot_root / str(text_reference)
                if not text_path.is_file() or sha256_file(text_path) != item.metadata.get("expected_text_sha256"):
                    raise StageExecutionError(f"{self.fetcher_key} text checksum mismatch or missing text for {item.item_id}")
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            digest = sha256_file(destination)
            expected = item.metadata.get("expected_asset_sha256")
            if expected and digest != expected:
                raise StageExecutionError(f"{self.fetcher_key} asset checksum mismatch for {item.item_id}: expected {expected}, got {digest}")
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[AcquiredAsset(item_id=item.item_id, path=str(destination), sha256=digest, media_type=asset.media_type)],
                )
            )
        return acquired_items


class ReshumotImporter(_GovernmentPrintImporter):
    """Born-digital Reshumot booklet pages: a rendered page image plus the PDF's embedded text."""

    fetcher_key = "reshumot"
    discovery_method = "reshumot_snapshot_importer"

    def exclusion_reasons(self, entry: dict[str, Any], source: SourceConfig, root: Path) -> list[str]:
        return reshumot_entry_exclusion_reasons(entry, source, root)

    def source_url(self, entry: dict[str, Any]) -> str:
        return str(entry["pdf"]["document_url"])

    def entry_metadata(self, entry: dict[str, Any]) -> dict[str, Any]:
        booklet = entry["booklet"]
        page = entry["page"]
        text = entry["text"]
        rendering = (government_print_entry_asset(entry) or {})["rendering"]
        return {
            "collection": f"Reshumot, {booklet['series_name_he']}",
            "period": "modern",
            "created": booklet["publish_date"],
            "source_group_id": f"reshumot:{booklet['series']}:{booklet['booklet_number']}",
            "reshumot_series": booklet["series"],
            "reshumot_booklet_number": booklet["booklet_number"],
            "reshumot_publish_date": booklet["publish_date"],
            "pdf_page_index": page["pdf_page_index"],
            "printed_page_number": page.get("printed_page_number"),
            # Rendering provenance: born-digital pages are rendered by HeOCR, never scanned.
            "image_origin": rendering["image_origin"],
            "is_scan": False,
            "renderer": rendering["renderer"],
            "renderer_version": rendering["renderer_version"],
            "render_dpi": rendering["dpi"],
            "text_reference": text["local_path"],
            "expected_text_sha256": text["sha256"],
            "text_provenance": text["text_provenance"],
            "text_tier": text["text_tier"],
            "text_granularity": text.get("granularity"),
            "text_normalization": (text.get("extraction") or {}).get("normalization"),
            "text_extractor": (text.get("extraction") or {}).get("extractor"),
            "text_extractor_version": (text.get("extraction") or {}).get("extractor_version"),
            "text_order_verified": True,
            "text_layout_notes": list(text.get("layout_notes") or []),
            "heocr_attestation": text.get("heocr_attestation"),
            "adjudication_status": text["adjudication_status"],
            "reference_eligible": text["reference_eligible"],
        }


class KnessetCommitteeImporter(_GovernmentPrintImporter):
    """Typewritten Knesset committee protocol page scans, sessions on or before 1975-12-31. Images only."""

    fetcher_key = "knesset_committee"
    discovery_method = "knesset_committee_snapshot_importer"

    def exclusion_reasons(self, entry: dict[str, Any], source: SourceConfig, root: Path) -> list[str]:
        return knesset_entry_exclusion_reasons(entry, source, root)

    def source_url(self, entry: dict[str, Any]) -> str:
        return str(entry["document"]["file_url"])

    def entry_metadata(self, entry: dict[str, Any]) -> dict[str, Any]:
        document = entry["document"]
        session = entry["session"]
        scan = (government_print_entry_asset(entry) or {})["scan"]
        return {
            "collection": f"Knesset committee protocols, {entry['committee']['name']}",
            "period": "historical",
            "created": session["start_date"],
            "source_group_id": f"knesset_committee:{document['document_id']}",
            "knesset_document_id": document["document_id"],
            "knesset_committee_session_id": session["committee_session_id"],
            "knesset_session_date": session["start_date"],
            "knesset_num": session.get("knesset_num"),
            "knesset_committee_id": entry["committee"].get("committee_id"),
            "knesset_committee_name": entry["committee"]["name"],
            "pdf_page_index": entry["page"]["pdf_page_index"],
            "image_origin": scan["image_origin"],
            "is_scan": True,
            "scan_ppi": scan["x_ppi"],
            "scan_bits_per_pixel": scan.get("bits_per_pixel"),
            "text_provenance": "none",
            "text_tier": 4,
            "reference_eligible": False,
        }
