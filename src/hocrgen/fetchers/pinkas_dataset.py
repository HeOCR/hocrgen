from __future__ import annotations

import gzip
import hashlib
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import Field

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.nli_scan_evidence import nli_scan_evidence
from hocrgen.fetchers.pinkas_line_language import (
    LineEvaluationScope,
    LineLanguageTagFile,
    derive_line_scopes,
    load_line_language_tags,
    page_scope_summary,
)
from hocrgen.fetchers.snapshot_records import load_snapshot, snapshot_root_setting
from hocrgen.manifests.models import (
    AcquiredAsset,
    AcquiredItemRecord,
    AssetReference,
    BenchmarkBBoxRecord,
    BenchmarkGeometryRecord,
    BenchmarkPointRecord,
    CandidateRecord,
    EnrichedCandidateRecord,
    ManifestModel,
)
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file

PINKAS_DATASET_SNAPSHOT_SETTING = "pinkas_dataset_snapshot_root"
PINKAS_DATASET_RASTER_MEDIA_TYPES = {"image/jpeg", "image/png"}
PINKAS_DATASET_LANGUAGES = frozenset({"he", "yi"})
PINKAS_DATASET_EVALUATION_SCOPE = "character_level_only"
PINKAS_DATASET_ALLOWED_USES = frozenset({"training", "character_level_evaluation"})
PINKAS_DATASET_REQUIRED_EXCLUDED_EVALUATIONS = frozenset({"word_level", "language_level_hebrew"})
# The dataset's CC BY 4.0 covers the annotations; the photographs are NLI's. Scan rights come from the F8c
# licence-slug gate over a pinned NLI manifest capture that lists the matched canvas.
PAGE_XML_NAMESPACES = frozenset(
    {
        "http://schema.primaresearch.org/PAGE/gts/pagecontent/2017-07-15",
        "http://schema.primaresearch.org/PAGE/gts/pagecontent/2018-07-15",
        "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15",
    }
)


class PageXmlLineRecord(ManifestModel):
    """One PAGE XML text line, with geometry in the pixel space of the image it is projected onto."""

    line_id: str
    region_id: str
    region_type: str | None = None
    reading_order: int = Field(ge=1)
    text: str
    geometry: BenchmarkGeometryRecord


class PageXmlPageRecord(ManifestModel):
    image_filename: str
    source_width: int = Field(gt=0)
    source_height: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    scale_x: float = Field(gt=0)
    scale_y: float = Field(gt=0)
    reading_order_source: str = "document_order"
    lines: list[PageXmlLineRecord] = Field(default_factory=list)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_points(raw: str | None) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for pair in (raw or "").split():
        x, _, y = pair.partition(",")
        points.append((float(x), float(y)))
    return points


def parse_page_xml_lines(xml_bytes: bytes, target_size: tuple[int, int] | None = None) -> PageXmlPageRecord:
    """Parse PAGE XML text lines with their polygons, scaled onto an image of `target_size` (width, height).

    Geometry is scaled by target/source per axis, so a downscaled thumbnail gets consistent coordinates. Points are
    clamped to the target image. Lines are numbered in document order (the format's ReadingOrder is not used when
    absent). Line text is NFC-normalized; empty lines are kept with empty text.
    """

    root = ET.fromstring(xml_bytes)
    namespace = root.tag[1:].split("}", 1)[0] if root.tag.startswith("{") else ""
    if _local_name(root.tag) != "PcGts" or namespace not in PAGE_XML_NAMESPACES:
        raise StageExecutionError(f"not a supported PAGE XML document: {root.tag}")
    ns = {"p": namespace}
    page = root.find("p:Page", ns)
    if page is None:
        raise StageExecutionError("PAGE XML has no Page element")
    source_width, source_height = int(page.get("imageWidth", "0")), int(page.get("imageHeight", "0"))
    if source_width <= 0 or source_height <= 0:
        raise StageExecutionError("PAGE XML Page lacks imageWidth/imageHeight")
    width, height = target_size or (source_width, source_height)
    scale_x, scale_y = width / source_width, height / source_height
    has_reading_order = page.find("p:ReadingOrder", ns) is not None
    lines: list[PageXmlLineRecord] = []
    for region in page.iter(f"{{{namespace}}}TextRegion"):
        for line in region.findall("p:TextLine", ns):
            coords = line.find("p:Coords", ns)
            points = [
                BenchmarkPointRecord(
                    x=round(min(max(x * scale_x, 0.0), float(width)), 2),
                    y=round(min(max(y * scale_y, 0.0), float(height)), 2),
                )
                for x, y in _parse_points(coords.get("points") if coords is not None else None)
            ]
            if len(points) < 3:
                continue
            xs = [point.x for point in points]
            ys = [point.y for point in points]
            if max(xs) <= min(xs) or max(ys) <= min(ys):
                continue
            unicode_node = line.find("p:TextEquiv/p:Unicode", ns)
            text = unicodedata.normalize("NFC", (unicode_node.text or "") if unicode_node is not None else "").strip()
            lines.append(
                PageXmlLineRecord(
                    line_id=str(line.get("id")),
                    region_id=str(region.get("id")),
                    region_type=region.get("type"),
                    reading_order=len(lines) + 1,
                    text=text,
                    geometry=BenchmarkGeometryRecord(
                        type="bbox_polygon",
                        bbox=BenchmarkBBoxRecord(x=min(xs), y=min(ys), width=round(max(xs) - min(xs), 2), height=round(max(ys) - min(ys), 2)),
                        polygon=points,
                    ),
                )
            )
    return PageXmlPageRecord(
        image_filename=str(page.get("imageFilename", "")),
        source_width=source_width,
        source_height=source_height,
        width=width,
        height=height,
        scale_x=scale_x,
        scale_y=scale_y,
        reading_order_source="page_xml_reading_order_ignored" if has_reading_order else "document_order",
        lines=lines,
    )


def read_annotation_bytes(path: Path, encoding: str | None) -> bytes:
    raw = path.read_bytes()
    return gzip.decompress(raw) if encoding == "gzip" else raw


def pinkas_dataset_snapshot_root(source: SourceConfig, bundle: ConfigBundle) -> Path:
    return snapshot_root_setting(source, bundle, PINKAS_DATASET_SNAPSHOT_SETTING)


def load_pinkas_dataset_snapshot(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return load_snapshot(root)


def pinkas_dataset_entry_asset(entry: dict[str, Any]) -> dict[str, Any] | None:
    for file in entry.get("files", []):
        if file.get("mime_type") in PINKAS_DATASET_RASTER_MEDIA_TYPES and file.get("local_path"):
            return file
    return None


def pinkas_dataset_usage_scope_is_valid(usage_scope: Any) -> bool:
    if not isinstance(usage_scope, dict):
        return False
    allowed = usage_scope.get("allowed_uses")
    excluded = usage_scope.get("excluded_evaluations")
    return (
        usage_scope.get("evaluation_scope") == PINKAS_DATASET_EVALUATION_SCOPE
        and isinstance(allowed, list)
        and bool(allowed)
        and set(allowed) <= PINKAS_DATASET_ALLOWED_USES
        and isinstance(excluded, list)
        and PINKAS_DATASET_REQUIRED_EXCLUDED_EVALUATIONS <= set(excluded)
    )


def pinkas_dataset_entry_exclusion_reason(entry: dict[str, Any], source: SourceConfig, root: Path) -> str | None:
    """Return why a Pinkas dataset entry cannot become a candidate for this source, or None when eligible."""

    rights = entry.get("rights") or {}
    if rights.get("license_expression") not in source.rights_strategy.values:
        return "license_not_in_source_lane"
    if rights.get("verification_status") != "primary_page_checked":
        return "rights_not_primary_page_checked"
    scan = entry.get("scan") or {}
    if scan.get("scan_redistribution_allowed") is not True:
        return "scan_rights_not_open"
    if not scan.get("match_method"):
        return "scan_not_matched"
    scan_problem = nli_scan_evidence(root, scan).problem
    if scan_problem is not None:
        return scan_problem
    languages = entry.get("languages")
    if not isinstance(languages, list) or not languages or not set(languages) <= PINKAS_DATASET_LANGUAGES:
        return "out_of_scope_language"
    if not pinkas_dataset_usage_scope_is_valid(entry.get("usage_scope")):
        return "missing_character_level_scope"
    annotation = entry.get("annotation") or {}
    if not annotation.get("local_path") or not annotation.get("sha256"):
        return "no_pinned_annotation"
    if annotation.get("adjudication_status") != "not_adjudicated" or annotation.get("reference_eligible") is not False:
        return "unsupported_reference_status"
    if pinkas_dataset_entry_asset(entry) is None:
        return "no_raster_asset"
    if not scan.get("landing_url"):
        return "missing_source_url"
    return None


def load_entry_page_lines(root: Path, entry: dict[str, Any]) -> PageXmlPageRecord:
    """Read an entry's pinned PAGE XML, verify it, and project its lines onto the entry's vendored thumbnail."""

    annotation = entry["annotation"]
    xml_bytes = read_annotation_bytes(root / annotation["local_path"], annotation.get("encoding"))
    if hashlib.sha256(xml_bytes).hexdigest() != annotation["sha256"]:
        raise StageExecutionError(f"Pinkas dataset PAGE XML checksum mismatch for {entry['entry_id']}")
    asset = pinkas_dataset_entry_asset(entry) or {}
    return parse_page_xml_lines(xml_bytes, (int(asset["width_px"]), int(asset["height_px"])))


def load_entry_line_scopes(
    root: Path, entry: dict[str, Any], tag_file: LineLanguageTagFile | None, page: PageXmlPageRecord | None = None
) -> list[LineEvaluationScope]:
    """Derive the per-line evaluation scope of one entry from the snapshot's language-tag sidecar.

    This is what an evaluator reads: a line may be scored at word level as Hebrew only when its scope is
    `word_level_hebrew` (a human `he` tag that still binds to the line). Geometry is in thumbnail pixels.
    """

    page = page or load_entry_page_lines(root, entry)
    page_tags = tag_file.page(entry["entry_id"]) if tag_file is not None else None
    return derive_line_scopes(entry["entry_id"], entry["annotation"]["sha256"], page.lines, page_tags)


class PinkasDatasetImporter:
    """Packaged-static-records adapter over a pinned excerpt of the BGU Pinkas Dataset (Zenodo 3569694).

    Each candidate is one handwritten page, an NLI scan, with its upstream PAGE XML (region, line and word geometry
    and text). The annotation is carried by reference and checksum; `load_entry_page_lines` turns it into typed line
    records scaled to the thumbnail. It becomes a scored reference only through F2 attestation and adjudication.
    Per-line evaluation scope comes from the snapshot's language-tag sidecar (F8d3, `pinkas_line_language`).
    """

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = pinkas_dataset_snapshot_root(source, bundle)
        snapshot, entries = load_pinkas_dataset_snapshot(root)
        candidates: list[CandidateRecord] = []
        for entry in sorted(entries, key=lambda record: record["entry_id"]):
            if pinkas_dataset_entry_exclusion_reason(entry, source, root) is not None:
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{entry['entry_id']}",
                    source_id=source.id,
                    source_item_id=entry["entry_id"],
                    source_url=entry["scan"]["landing_url"],
                    discovery_method="pinkas_dataset_snapshot_importer",
                    title=entry["title"],
                    raw_metadata={
                        "snapshot_root": str(root),
                        "dataset_landing_url": snapshot.get("dataset_landing_url"),
                        "captured_at": str(snapshot.get("captured_at")),
                        "entry": entry,
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        tag_files: dict[Path, LineLanguageTagFile | None] = {}
        for candidate in candidates:
            entry = candidate.raw_metadata["entry"]
            root = Path(candidate.raw_metadata["snapshot_root"])
            if root not in tag_files:
                tag_files[root] = load_line_language_tags(root, load_pinkas_dataset_snapshot(root)[0])
            line_scopes = load_entry_line_scopes(root, entry, tag_files[root])
            scope_summary = page_scope_summary(line_scopes)
            asset = pinkas_dataset_entry_asset(entry) or {}
            rights, scan, annotation, usage_scope = entry["rights"], entry["scan"], entry["annotation"], entry["usage_scope"]
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
                    metadata={
                        "collection": scan.get("holding_institution") or "",
                        "period": "historical",
                        "content_type": entry.get("content_type"),
                        "created": (entry.get("work") or {}).get("created"),
                        "languages": list(entry["languages"]),
                        "script": entry.get("script"),
                        "upstream_identifier": entry["entry_id"],
                        "upstream_dataset": candidate.raw_metadata.get("dataset_landing_url"),
                        "upstream_captured_at": candidate.raw_metadata.get("captured_at"),
                        "upstream_split": (entry.get("upstream") or {}).get("split"),
                        "source_group_id": f"pinkas_dataset_bgu:{entry['work_id']}",
                        "usage_scope": dict(usage_scope),
                        # The pinned page default is `character_level_only`; the derived page scope widens only when
                        # every line carries a binding human `he` tag. Per-line scope is in `line_scopes`.
                        "evaluation_scope": scope_summary["page_evaluation_scope"],
                        "line_scope_summary": scope_summary,
                        "line_scopes": [scope.model_dump(mode="json", exclude={"geometry", "entry_id"}) for scope in line_scopes],
                        "annotation_reference": annotation["local_path"],
                        "annotation_encoding": annotation.get("encoding"),
                        "annotation_format": annotation.get("format"),
                        "expected_annotation_sha256": annotation["sha256"],
                        "annotation_line_count": annotation.get("line_count"),
                        "text_provenance": annotation.get("text_provenance"),
                        "heocr_attestation": annotation.get("heocr_attestation"),
                        "adjudication_status": annotation["adjudication_status"],
                        "reference_eligible": annotation["reference_eligible"],
                        "rights_evidence": rights.get("evidence_text"),
                        "rights_verified_at": rights.get("verified_at"),
                        "attribution_text": rights.get("attribution_text"),
                        "scan_holding_institution": scan.get("holding_institution"),
                        "scan_record_id": scan.get("record_id"),
                        "scan_shelfmark": scan.get("shelfmark"),
                        "scan_license_url": scan.get("license_url"),
                        "scan_iiif_canvas": scan.get("iiif_canvas"),
                        "scan_canvas_region": scan.get("canvas_region"),
                        "scan_verified_at": scan.get("verified_at"),
                        "scan_rights": nli_scan_evidence(root, scan).metadata(),
                        "expected_asset_sha256": asset.get("sha256"),
                    },
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            asset = item.asset_references[0]
            resolved = Path(asset.resolved_path or "")
            snapshot_root = resolved.parents[len(PurePosixPath(asset.reference).parts) - 1]
            annotation_path = snapshot_root / str(item.metadata.get("annotation_reference", ""))
            if not annotation_path.is_file():
                raise StageExecutionError(f"Pinkas dataset PAGE XML missing for {item.item_id}")
            xml_bytes = read_annotation_bytes(annotation_path, item.metadata.get("annotation_encoding"))
            if hashlib.sha256(xml_bytes).hexdigest() != item.metadata.get("expected_annotation_sha256"):
                raise StageExecutionError(f"Pinkas dataset PAGE XML checksum mismatch for {item.item_id}")
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            digest = sha256_file(destination)
            expected = item.metadata.get("expected_asset_sha256")
            if expected and digest != expected:
                raise StageExecutionError(
                    f"Pinkas dataset asset checksum mismatch for {item.item_id}: expected {expected}, got {digest}"
                )
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[
                        AcquiredAsset(item_id=item.item_id, path=str(destination), sha256=digest, media_type=asset.media_type)
                    ],
                )
            )
        return acquired_items
