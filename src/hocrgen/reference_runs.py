"""E2c4: offline reference-aware evaluation runs over engine prediction files, with a run record.

Scored set: synthetic gold derived from a validated hocrsyngen batch, plus reviewed/adjudicated
``benchmark_transcription_reference.v1`` records. HASH, tender, or any other unreviewed text is scored only as
``unreviewed`` diagnostics and never enters scored aggregates.

E2c5: ``diagnostic_only`` runs score unreviewed text alone, with no scored set. Such a run is never a benchmark:
it refuses scored-set inputs, is marked ``benchmark_ready: false`` and ``diagnostic_only: true``, and reports any
baseline delta under ``diagnostic_comparison`` rather than ``comparison``.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from hocrgen import __version__
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.hocrsyngen_manifest import LEGACY_SOURCE_ITEM_ID_PREFIX, _source_item_id, validate_hocrsyngen_batch
from pydantic import ValidationError

from hocrgen.manifests.models import BenchmarkReferenceManifestRecord, BenchmarkTranscriptionReferenceRecord
from hocrgen.reference_evaluation import (
    _aggregate,
    DEFAULT_PROFILE_IDS,
    NORMALIZATION_PROFILES,
    PRIMARY_PROFILE_ID,
    evaluate_reference_profiles,
    evaluate_text_profiles,
)

PREDICTION_SCHEMA_VERSIONS = frozenset({"1.0", "heocr_engine_prediction.v1"})
MAPPING_SCHEMA_VERSION = "hocrgen_reference_page_mapping.v1"
RUN_RECORD_SCHEMA_VERSION = "hocrgen_reference_evaluation_run.v1"
SCORED_ORIGINS = frozenset({"synthetic_gold", "adjudicated_reference"})
LEGACY_PREDICTION_SCHEMA_VERSIONS = frozenset({"1.0"})
TRACKS = frozenset({"open", "proprietary"})
LINE_ANNOTATIONS_SCHEMA_VERSION = "hocrsyngen_line_annotations.v1"
LOGICAL_JOINS = {"space": " ", "cell": " | "}  # hocrsyngen LOGICAL_JOIN_SEPARATORS
PER_CELL_VIEW_ID = "per_cell.v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_sha256(payload: Any) -> str:
    return _sha256_bytes(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _read_json(path: Path, label: str) -> tuple[Any, str]:
    try:
        raw = path.read_bytes()
        return json.loads(raw.decode("utf-8")), _sha256_bytes(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageExecutionError(f"could not read {label} {path.name}: {exc}") from exc


# --- predictions ----------------------------------------------------------------------------------------------

def load_engine_prediction(path: Path) -> dict[str, Any]:
    """Load one engine page prediction (heocr-engine schema ``"1.0"`` or ``heocr_engine_prediction.v1``)."""
    payload, file_sha256 = _read_json(path, "prediction")
    if not isinstance(payload, dict):
        raise StageExecutionError(f"prediction {path.name} must be a JSON object")
    schema = payload.get("schema_version")
    if schema not in PREDICTION_SCHEMA_VERSIONS:
        raise StageExecutionError(f"prediction {path.name} has unsupported schema_version {schema!r}")
    page_id, text = payload.get("page_id"), payload.get("text")
    if not isinstance(payload.get("input"), dict) or not isinstance(payload.get("engine"), dict):
        raise StageExecutionError(f"prediction {path.name} needs input and engine objects")
    input_sha = payload["input"].get("sha256")
    engine = payload["engine"]
    if not isinstance(page_id, str) or not page_id or not isinstance(text, str):
        raise StageExecutionError(f"prediction {path.name} needs string page_id and text")
    if not isinstance(input_sha, str) or not _SHA256.fullmatch(input_sha):
        raise StageExecutionError(f"prediction {path.name} needs input.sha256")
    if page_id.startswith("sha256:") and page_id != f"sha256:{input_sha}":
        raise StageExecutionError(f"prediction {path.name} page_id does not match input.sha256")
    if not isinstance(engine.get("name"), str) or not isinstance(engine.get("version"), str):
        raise StageExecutionError(f"prediction {path.name} needs engine name and version")
    pipeline = payload.get("pipeline", [])
    if not isinstance(pipeline, list) or not all(isinstance(stage, dict) for stage in pipeline):
        raise StageExecutionError(f"prediction {path.name} pipeline must be a list of objects")
    track = _prediction_track(path.name, schema, payload.get("track"), pipeline)
    return {
        "file_name": path.name, "file_sha256": file_sha256, "schema_version": schema, "page_id": page_id,
        "input_sha256": input_sha, "track": track, "engine": {"name": engine["name"], "version": engine["version"]},
        "pipeline": pipeline, "text": text,
    }


def _prediction_track(file_name: str, schema: str, track: Any, pipeline: list[dict[str, Any]]) -> str:
    """Apply heocr-engine decision 0005: proprietary output never passes as open-track."""
    if track is None and schema in LEGACY_PREDICTION_SCHEMA_VERSIONS:
        track = "open"  # PR #1 baseline files predate the field and are open-source, network-free Tesseract output
    if track not in TRACKS:
        raise StageExecutionError(f"prediction {file_name} track must be one of {sorted(TRACKS)}, got {track!r}")
    for index, stage in enumerate(pipeline):
        stage_track = stage.get("track")
        if stage_track not in TRACKS:
            raise StageExecutionError(f"prediction {file_name} pipeline stage {index} has invalid track {stage_track!r}")
        if stage_track == "proprietary" and track == "open":
            raise StageExecutionError(f"prediction {file_name} is track open but pipeline stage {index} is proprietary")
        if stage_track == "open" and stage.get("requires_network") is not False:
            raise StageExecutionError(f"prediction {file_name} open pipeline stage {index} must declare requires_network: false")
    return track


def load_prediction_set(directory: Path) -> dict[str, Any]:
    if not directory.is_dir():
        raise StageExecutionError(f"prediction directory not found: {directory.name}")
    records = [load_engine_prediction(path) for path in sorted(directory.glob("*.json"))]
    if not records:
        raise StageExecutionError(f"no prediction files in {directory.name}")
    pages: dict[str, dict[str, Any]] = {}
    for record in records:
        if record["page_id"] in pages:
            raise StageExecutionError(f"duplicate prediction for page {record['page_id']}")
        pages[record["page_id"]] = record
    tracks = sorted({record["track"] for record in records})
    if len(tracks) != 1:
        raise StageExecutionError(f"prediction set {directory.name} mixes tracks {tracks}; score each track separately")
    return {
        "pages": pages,
        "track": tracks[0],
        "set_sha256": _canonical_sha256(sorted(record["file_sha256"] for record in records)),
        "engines": sorted({(r["engine"]["name"], r["engine"]["version"]) for r in records}),
        "pipelines": sorted({json.dumps(r["pipeline"], sort_keys=True) for r in records}),
    }


# --- mapping ----------------------------------------------------------------------------------------------------

def build_mapping_from_asset_sha256(asset_index: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build an item -> ordered page-id mapping from asset sha256 values (engine page ids are ``sha256:<hex>``)."""
    items: dict[str, list[str]] = {}
    for entry in asset_index:
        item_id, pages = entry.get("item_id"), entry.get("page_sha256")
        if not isinstance(item_id, str) or not item_id or not isinstance(pages, list) or not pages:
            raise StageExecutionError("asset index entries need item_id and a non-empty page_sha256 list")
        if item_id in items:
            raise StageExecutionError(f"duplicate asset index item {item_id}")
        for sha in pages:
            if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
                raise StageExecutionError(f"invalid page sha256 for {item_id}")
        items[item_id] = [f"sha256:{sha}" for sha in pages]
    return validate_mapping({"schema_version": MAPPING_SCHEMA_VERSION, "mapping_source": "asset_sha256",
                             "items": [{"item_id": k, "page_ids": v} for k, v in sorted(items.items())]})


def validate_mapping(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema_version") != MAPPING_SCHEMA_VERSION:
        raise StageExecutionError(f"mapping must use schema_version {MAPPING_SCHEMA_VERSION}")
    if payload.get("mapping_source") not in {"asset_sha256", "explicit"}:
        raise StageExecutionError("mapping_source must be asset_sha256 or explicit")
    items = payload.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise StageExecutionError("mapping items must be a list of objects")
    seen_items: set[str] = set()
    seen_pages: set[str] = set()
    for item in items:
        item_id, page_ids = item.get("item_id"), item.get("page_ids")
        if not isinstance(item_id, str) or not item_id or not isinstance(page_ids, list) or not page_ids:
            raise StageExecutionError("mapping items need item_id and a non-empty page_ids list")
        if item_id in seen_items:
            raise StageExecutionError(f"duplicate mapping item {item_id}")
        seen_items.add(item_id)
        for page_id in page_ids:
            if not isinstance(page_id, str) or page_id in seen_pages:
                raise StageExecutionError(f"page {page_id} mapped more than once")
            seen_pages.add(page_id)
    return payload


def _assemble(mapping: Mapping[str, Any], prediction_set: Mapping[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    pages = prediction_set["pages"]
    assembled: dict[str, str] = {}
    partial: list[str] = []
    mapped: set[str] = set()
    for item in mapping["items"]:
        mapped.update(item["page_ids"])
        present = [page_id for page_id in item["page_ids"] if page_id in pages]
        if len(present) == len(item["page_ids"]):
            assembled[item["item_id"]] = "\n".join(pages[page_id]["text"] for page_id in item["page_ids"])
        elif present:
            partial.append(item["item_id"])
    return assembled, {"items_with_partial_page_predictions": sorted(partial),
                       "unmapped_prediction_pages": sorted(set(pages) - mapped)}


# --- references -------------------------------------------------------------------------------------------------

def load_synthetic_gold(batch_dir: Path, *, source_id: str = "project_synthetic") -> dict[str, Any]:
    """Derive synthetic gold text and an asset index from a hocrsyngen batch (gold by construction).

    Batches that satisfy hocrgen's hardened release-path model are validated with it. Raw public
    ``generation_manifest.v1`` batches (without hocrgen-owned provider metadata, see F6f1) are accepted for
    evaluation only after every page asset's sha256 is recomputed; this does not admit them to release paths.
    """
    manifest_path = batch_dir / "generation_manifest.json"
    payload, manifest_sha = _read_json(manifest_path, "generation manifest")
    if isinstance(payload, dict) and "provider_metadata" not in payload:
        # Raw public output without hocrgen-owned provider metadata (F6f1): evaluation-only, checksum-verified.
        samples = _public_manifest_samples(batch_dir, payload)
        validation = "public_manifest_page_checksums"
    else:
        # A batch that carries hocrgen-owned metadata must pass the hardened model; failures raise, never fall back.
        batch = validate_hocrsyngen_batch(batch_dir)  # raises StageExecutionError on any hardened-model failure
        samples = [
            {"item": _source_item_id(sample), "text": sample.text.logical_order, "language": sample.text.language,
             "script": sample.text.script, "template": sample.provenance.template_id,
             "pages": [page.sha256 for page in sample.pages]}
            for sample in batch.manifest.samples
        ]
        validation = "hocrgen_release_path_model"
    texts, strata, asset_index = {}, {}, []
    for sample in samples:
        item_id = f"{source_id}:{sample['item']}"
        if item_id in texts:
            raise StageExecutionError(f"duplicate synthetic item {item_id}")
        texts[item_id] = sample["text"]
        strata[item_id] = {"language_script": f"{sample['language']}-{sample['script']}", "modality": "synthetic",
                           "source_id": source_id, "document_type": sample["template"],
                           "reference_origin": "synthetic_gold"}
        asset_index.append({"item_id": item_id, "page_sha256": sample["pages"]})
    return {"texts": texts, "strata": strata, "asset_index": asset_index,
            "identity": {"kind": "hocrsyngen_generation_manifest", "sha256": manifest_sha, "validation": validation,
                         "reference_manifest_id": f"synthetic_gold:{manifest_sha[:16]}"}}


def _public_manifest_samples(batch_dir: Path, payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("manifest_version") != "1.0" or not payload.get("samples"):
        raise StageExecutionError(f"{batch_dir.name} is not a hocrsyngen generation_manifest.v1 batch")
    root = batch_dir.resolve()
    samples = []
    for sample in payload["samples"]:
        try:
            text = sample["text"]
            if text["unicode_normalization"] != "NFC" or not isinstance(text["logical_order"], str):
                raise ValueError("text must be NFC logical-order")
            pages = []
            for page in sample["pages"]:
                asset = (root / page["asset_path"]).resolve()
                if root not in asset.parents:
                    raise ValueError("asset path escapes batch directory")
                if not _SHA256.fullmatch(page["sha256"]) or _sha256_bytes(asset.read_bytes()) != page["sha256"]:
                    raise ValueError(f"page checksum mismatch for {page['asset_path']}")
                pages.append(page["sha256"])
            samples.append({"item": f"{LEGACY_SOURCE_ITEM_ID_PREFIX}{int(sample['provenance']['sample_index'])}", "text": text["logical_order"],
                            "language": text["language"], "script": text["script"],
                            "template": sample["provenance"]["template_id"], "pages": pages})
        except (KeyError, TypeError, ValueError, OSError) as exc:
            raise StageExecutionError(f"invalid hocrsyngen sample in {batch_dir.name}: {exc}") from exc
    return samples


def _rebuild_logical_order(lines: Any, separators: Mapping[str, str], where: str) -> tuple[str, bool]:
    """Rebuild page gold from hocrsyngen line segments, joining continuations with ``separators[logical_join]``."""
    if not isinstance(lines, list):
        raise StageExecutionError(f"{where}: lines must be a list")
    rebuilt: dict[int, str] = {}
    has_cell = False
    for line in lines:  # hocrsyngen writes lines in line_index (logical) order
        if not isinstance(line, dict) or not isinstance(line.get("text"), str):
            raise StageExecutionError(f"{where}: each line needs string text")
        index, join = line.get("logical_line_index"), line.get("logical_join")
        if index is None:
            continue  # drawn but not in page gold
        if not isinstance(index, int) or join not in (None, *LOGICAL_JOINS):
            raise StageExecutionError(f"{where}: invalid logical_line_index or logical_join")
        if join is None:
            if index in rebuilt:
                raise StageExecutionError(f"{where}: logical line {index} starts twice")
            rebuilt[index] = line["text"]
        elif index not in rebuilt:
            raise StageExecutionError(f"{where}: logical line {index} continues before it starts")
        else:
            has_cell = has_cell or join == "cell"
            rebuilt[index] += separators[join] + line["text"]
    return "\n".join(rebuilt[index] for index in sorted(rebuilt)), has_cell


def load_per_cell_view(batch_dir: Path, gold: Mapping[str, Any]) -> dict[str, Any] | None:
    """Derive the per-cell reference view (E2c7) from a batch's hocrsyngen line annotations.

    Each ``logical_join: "cell"`` segment starts a new line instead of joining with ``" | "``; every other join, and
    any ``|`` inside a segment's text, is kept as is. Returns None when the batch has no ``line_annotations.json``
    or no item has a cell join. A sidecar that is present but does not rebuild every item's ``logical_order``
    exactly fails closed, with or without cell joins.
    """
    path = batch_dir / "line_annotations.json"
    if not path.is_file():
        return None
    payload, sidecar_sha = _read_json(path, "line annotations")
    if not isinstance(payload, dict) or payload.get("schema") != LINE_ANNOTATIONS_SCHEMA_VERSION \
            or not isinstance(payload.get("pages"), list):
        raise StageExecutionError(f"{path.name} is not a {LINE_ANNOTATIONS_SCHEMA_VERSION} sidecar")
    if payload.get("generation_manifest_sha256") != gold["identity"]["sha256"]:
        raise StageExecutionError(f"{path.name} does not belong to this batch's generation manifest")
    item_pages = {entry["item_id"]: entry["page_sha256"] for entry in gold["asset_index"]}
    page_items = {sha: item_id for item_id, shas in item_pages.items() for sha in shas}
    texts: dict[str, str] = {}
    seen: set[str] = set()
    for page in payload["pages"]:
        item_id = page_items.get(page.get("page_sha256")) if isinstance(page, dict) else None
        if item_id is None:
            raise StageExecutionError(f"{path.name} has a page that is not in the generation manifest")
        if item_id in seen or len(item_pages[item_id]) != 1:
            raise StageExecutionError(f"{path.name}: per-cell view needs exactly one annotated page per item ({item_id})")
        seen.add(item_id)
        where = f"{path.name} {item_id}"
        as_is, has_cell = _rebuild_logical_order(page.get("lines"), LOGICAL_JOINS, where)
        if as_is != gold["texts"][item_id]:
            raise StageExecutionError(f"{where}: lines do not rebuild logical_order")
        if has_cell:
            texts[item_id] = _rebuild_logical_order(page["lines"], {**LOGICAL_JOINS, "cell": "\n"}, where)[0]
    if seen != item_pages.keys():
        raise StageExecutionError(f"{path.name} does not annotate every item: {sorted(item_pages.keys() - seen)}")
    if not texts:
        return None  # no cell joins: an empty view would only report null rates
    return {"view_id": PER_CELL_VIEW_ID, "texts": texts,
            "source": {"kind": "hocrsyngen_line_annotations", "schema": LINE_ANNOTATIONS_SCHEMA_VERSION,
                       "sha256": sidecar_sha}}


def load_adjudicated_references(manifest_path: Path) -> dict[str, Any]:
    """Load reviewed+adjudicated transcription references; anything else is excluded with a reason.

    The whole manifest is validated (including duplicate item/reference ids). Declared child checksums are
    verified, and the actual child hashes are recorded so edited references change the recorded identity.
    """
    payload, manifest_sha = _read_json(manifest_path, "reference manifest")
    try:
        manifest = BenchmarkReferenceManifestRecord.model_validate(payload)
    except ValidationError as exc:
        raise StageExecutionError(f"invalid reference manifest {manifest_path.name}: {exc}") from exc
    root = manifest_path.parent.resolve()
    references, strata, excluded, children = {}, {}, [], []
    for item in manifest.items:
        if item.public_reference_status not in {"reviewed", "adjudicated"} or item.adjudication_status != "adjudicated":
            excluded.append({"item_id": item.item_id, "reason": "reference is not reviewed and adjudicated"})
            continue
        if item.transcription_reference is None:
            excluded.append({"item_id": item.item_id, "reason": "no transcription reference"})
            continue
        child_path = (root / item.transcription_reference.path).resolve()
        if root not in child_path.parents:
            raise StageExecutionError(f"reference path escapes manifest directory for {item.item_id}")
        child, child_sha = _read_json(child_path, "transcription reference")
        declared = item.transcription_reference.sha256
        if declared is not None and declared != child_sha:
            raise StageExecutionError(f"transcription reference checksum mismatch for {item.item_id}")
        try:
            record = BenchmarkTranscriptionReferenceRecord.model_validate(child)
        except ValidationError as exc:
            raise StageExecutionError(f"invalid transcription reference for {item.item_id}: {exc}") from exc
        if record.item_id != item.item_id:
            raise StageExecutionError(f"reference item id mismatch for {item.item_id}")
        references[item.item_id] = record
        strata[item.item_id] = {"reference_origin": "adjudicated_reference"}
        children.append({"item_id": item.item_id, "reference_id": item.reference_id,
                         "path": item.transcription_reference.path, "sha256": child_sha,
                         "declared_sha256": declared})
    return {"references": references, "strata": strata, "excluded": excluded,
            "identity": {"kind": "benchmark_reference_manifest", "sha256": manifest_sha,
                         "reference_manifest_id": manifest.reference_manifest_id,
                         "child_references": children,
                         "child_references_sha256": _canonical_sha256(children)}}


def load_unreviewed_texts(path: Path) -> dict[str, Any]:
    """JSONL of ``{item_id, text, ...strata}`` for unreviewed candidate texts (HASH, tenders, etc.)."""
    try:
        raw = path.read_bytes()
        lines = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageExecutionError(f"could not read unreviewed texts {path.name}: {exc}") from exc
    texts, strata = {}, {}
    for line in lines:
        if not isinstance(line, dict):
            raise StageExecutionError("each unreviewed text record must be a JSON object")
        item_id, text = line.get("item_id"), line.get("text")
        if not isinstance(item_id, str) or not isinstance(text, str) or item_id in texts:
            raise StageExecutionError("unreviewed texts need unique item_id and string text")
        origin = line.get("reference_origin") or "unreviewed_candidate"
        if origin in SCORED_ORIGINS:
            raise StageExecutionError(f"unreviewed text {item_id} cannot claim scored origin {origin}")
        texts[item_id] = text
        strata[item_id] = {key: line[key] for key in ("language_script", "modality", "source_id", "document_type")
                           if line.get(key)} | {"reference_origin": origin}
    return {"texts": texts, "strata": strata, "sha256": _sha256_bytes(raw)}


# --- runs -------------------------------------------------------------------------------------------------------

def _score(predictions: Mapping[str, str], *, track: str, gold: Mapping[str, Any] | None,
           adjudicated: Mapping[str, Any] | None, unreviewed: Mapping[str, Any] | None, profiles: list[str],
           alignment_masked: bool, cell_view: Mapping[str, Any] | None = None) -> dict[str, Any]:
    gold_texts = dict(gold["texts"]) if gold else {}
    references = dict(adjudicated["references"]) if adjudicated else {}
    overlap = sorted(gold_texts.keys() & references.keys())
    if overlap:
        raise StageExecutionError(f"items appear in both synthetic gold and adjudicated references: {overlap}")
    scored: dict[str, Any] = {}
    if gold_texts:
        scored["synthetic_gold"] = evaluate_text_profiles(
            sorted(gold_texts), predictions={k: v for k, v in predictions.items() if k in gold_texts},
            references=gold_texts, profiles=profiles, item_strata=gold["strata"])
    if references:
        scored["adjudicated_reference"] = evaluate_reference_profiles(
            sorted(references), predictions={k: v for k, v in predictions.items() if k in references},
            references=references, profiles=profiles, item_strata=adjudicated["strata"],
            alignment_masked=alignment_masked)
    for report in scored.values():
        report["track"] = track
    result: dict[str, Any] = {"track": track, "scored": scored}
    if gold_texts and cell_view is not None:
        result["reference_views"] = {"synthetic_gold": {cell_view["view_id"]: _cell_view_reports(
            predictions, track=track, gold=gold, cell_view=cell_view, profiles=profiles)}}
    if unreviewed and unreviewed["texts"]:
        diagnostic = evaluate_text_profiles(
            sorted(unreviewed["texts"]),
            predictions={k: v for k, v in predictions.items() if k in unreviewed["texts"]},
            references=unreviewed["texts"], profiles=profiles, item_strata=unreviewed["strata"])
        result["unreviewed_diagnostics"] = {"reference_status": "unreviewed", "benchmark_ready": False,
                                            "scored": False, "track": track, **diagnostic}
    return result


def _cell_view_reports(predictions: Mapping[str, str], *, track: str, gold: Mapping[str, Any],
                       cell_view: Mapping[str, Any], profiles: list[str]) -> dict[str, Any]:
    """Score the items that have cell joins against both their logical_order gold and the per-cell view (E2c7)."""
    ids = sorted(cell_view["texts"])
    subset = {k: v for k, v in predictions.items() if k in cell_view["texts"]}
    strata = {item_id: gold["strata"][item_id] for item_id in ids}
    views = {
        "logical_order": evaluate_text_profiles(ids, predictions=subset, profiles=profiles, item_strata=strata,
                                                references={item_id: gold["texts"][item_id] for item_id in ids}),
        cell_view["view_id"]: evaluate_text_profiles(ids, predictions=subset, profiles=profiles, item_strata=strata,
                                                     references=dict(cell_view["texts"])),
    }
    for report in views.values():
        report["track"] = track
    return {"view_id": cell_view["view_id"], "scope": "items with at least one logical_join cell segment",
            "item_count": len(ids), "views": views}


def _single_stage_change(base_set: dict, cand_set: dict) -> dict[str, Any] | None:
    """Return the one ordered stage difference between single-pipeline sets, or None if it is not exactly one."""
    if len(base_set["pipelines"]) != 1 or len(cand_set["pipelines"]) != 1:
        return None
    base, cand = json.loads(base_set["pipelines"][0]), json.loads(cand_set["pipelines"][0])
    if len(cand) == len(base) + 1:
        for index in range(len(cand)):
            if cand[:index] + cand[index + 1:] == base:
                return {"change": "added", "position": index, "stage": cand[index]}
    elif len(base) == len(cand) + 1:
        for index in range(len(base)):
            if base[:index] + base[index + 1:] == cand:
                return {"change": "removed", "position": index, "stage": base[index]}
    elif len(base) == len(cand):
        differing = [index for index, (left, right) in enumerate(zip(base, cand)) if left != right]
        if len(differing) == 1:
            index = differing[0]
            return {"change": "replaced", "position": index, "stage": cand[index], "replaced": base[index]}
    return None


def _report_deltas(base_report: dict[str, Any], cand_report: dict[str, Any]) -> dict[str, Any]:
    base_items = {item["item_id"]: item for item in base_report["items"]}
    cand_items = {item["item_id"]: item for item in cand_report["items"]}
    common = sorted(base_items.keys() & cand_items.keys())
    profiles: dict[str, Any] = {}
    for profile_id in cand_report["profiles"]:
        # Re-aggregate over common items only, so omitting a hard item cannot look like an improvement.
        base_agg = _aggregate([base_items[i]["profiles"][profile_id] for i in common])
        cand_agg = _aggregate([cand_items[i]["profiles"][profile_id] for i in common])
        accounting = {}
        for metric, edit_key, denominator_key in (
            ("characters", "character_edits", "reference_characters"),
            ("words", "word_edits", "reference_words"),
        ):
            differences = [cand_items[i]["profiles"][profile_id][edit_key]
                           - base_items[i]["profiles"][profile_id][edit_key] for i in common]
            accounting[metric] = {
                "baseline_edits": base_agg[edit_key], "candidate_edits": cand_agg[edit_key],
                "reference_units": base_agg[denominator_key],
                "items_improved": sum(d < 0 for d in differences),
                "items_unchanged": sum(d == 0 for d in differences),
                "items_worsened": sum(d > 0 for d in differences),
                "net_edits_removed_on_improved_items": sum(-d for d in differences if d < 0),
                "net_edits_introduced_on_worsened_items": sum(d for d in differences if d > 0),
            }
        profiles[profile_id] = {
            "paired_edit_accounting": accounting,
            "baseline_cer": base_agg["cer"], "candidate_cer": cand_agg["cer"],
            "delta_cer": None if None in (base_agg["cer"], cand_agg["cer"]) else cand_agg["cer"] - base_agg["cer"],
            "baseline_wer": base_agg["wer"], "candidate_wer": cand_agg["wer"],
            "delta_wer": None if None in (base_agg["wer"], cand_agg["wer"]) else cand_agg["wer"] - base_agg["wer"],
        }
    return {
        "common_item_count": len(common),
        "baseline_only_items": sorted(base_items.keys() - cand_items.keys()),
        "candidate_only_items": sorted(cand_items.keys() - base_items.keys()),
        "profiles": profiles,
    }


def _comparison_context(base_set: dict, cand_set: dict) -> dict[str, Any]:
    if base_set["track"] != cand_set["track"]:
        raise StageExecutionError(
            f"refusing to compare a {base_set['track']}-track baseline with a {cand_set['track']}-track candidate"
        )
    return {
        "track": cand_set["track"],
        "baseline_pipelines": [json.loads(p) for p in base_set["pipelines"]],
        "candidate_pipelines": [json.loads(p) for p in cand_set["pipelines"]],
        "single_stage_attribution": _single_stage_change(base_set, cand_set),
        "attribution_note": "deltas cover common items only; a stage is named only when each set used one ordered "
                            "pipeline and they differ by exactly one stage insertion, removal or replacement",
    }


def _comparison(baseline: dict[str, Any], candidate: dict[str, Any], base_set: dict, cand_set: dict) -> dict[str, Any]:
    context = _comparison_context(base_set, cand_set)
    deltas = {origin: _report_deltas(baseline["scored"][origin], report)
              for origin, report in candidate["scored"].items() if origin in baseline["scored"]}
    comparison = {"track": context.pop("track"), "deltas": deltas, **context}
    if "reference_views" in candidate:
        comparison["reference_view_deltas"] = {
            origin: {view_id: {name: _report_deltas(baseline["reference_views"][origin][view_id]["views"][name], report)
                               for name, report in block["views"].items()}
                     for view_id, block in by_view.items()}
            for origin, by_view in candidate["reference_views"].items()
        }
    return comparison


def _diagnostic_comparison(baseline: dict[str, Any], candidate: dict[str, Any], base_set: dict,
                           cand_set: dict) -> dict[str, Any]:
    """Delta between two sets on unreviewed text only; never a scored comparison (E2c5)."""
    context = _comparison_context(base_set, cand_set)
    return {"track": context.pop("track"), "reference_status": "unreviewed", "benchmark_ready": False,
            "scored": False, "unreviewed_deltas": _report_deltas(baseline["unreviewed_diagnostics"],
                                                                 candidate["unreviewed_diagnostics"]),
            **context}


def run_reference_evaluation(
    *, predictions_dir: Path, synthetic_batch: Path | None = None, reference_manifest: Path | None = None,
    unreviewed_texts: Path | None = None, mapping_path: Path | None = None, asset_index_path: Path | None = None,
    baseline_predictions_dir: Path | None = None, profiles: Iterable[str] = DEFAULT_PROFILE_IDS,
    alignment_masked: bool = False, diagnostic_only: bool = False,
) -> dict[str, Any]:
    if diagnostic_only:
        if synthetic_batch is not None or reference_manifest is not None:
            raise StageExecutionError("--diagnostic-only cannot be combined with --synthetic-batch or "
                                      "--reference-manifest: a run is either diagnostic or scored, never both")
        if unreviewed_texts is None:
            raise StageExecutionError("--diagnostic-only requires --unreviewed-texts")
        if mapping_path is None and asset_index_path is None:
            raise StageExecutionError("--diagnostic-only requires --mapping or --asset-index")
        if alignment_masked:
            raise StageExecutionError("--alignment-masked applies only to adjudicated references, "
                                      "not to --diagnostic-only runs")
    elif synthetic_batch is None and reference_manifest is None:
        raise StageExecutionError("a scored set is required: --synthetic-batch and/or --reference-manifest "
                                  "(or use --diagnostic-only with --unreviewed-texts)")
    profile_ids = list(profiles)
    if PRIMARY_PROFILE_ID not in profile_ids or set(profile_ids) - NORMALIZATION_PROFILES.keys():
        raise StageExecutionError(f"profiles must be known and include {PRIMARY_PROFILE_ID}")
    gold = load_synthetic_gold(synthetic_batch) if synthetic_batch else None
    cell_view = load_per_cell_view(synthetic_batch, gold) if synthetic_batch else None
    adjudicated = load_adjudicated_references(reference_manifest) if reference_manifest else None
    unreviewed = load_unreviewed_texts(unreviewed_texts) if unreviewed_texts else None
    if diagnostic_only and not unreviewed["texts"]:
        raise StageExecutionError("--diagnostic-only needs at least one unreviewed text")
    if mapping_path is not None:
        payload, _ = _read_json(mapping_path, "mapping")
        mapping = validate_mapping(payload)
    else:
        asset_index = list(gold["asset_index"]) if gold else []
        if asset_index_path is not None:
            extra, _ = _read_json(asset_index_path, "asset index")
            asset_index.extend(extra.get("items", []) if isinstance(extra, dict) else [])
        mapping = build_mapping_from_asset_sha256(asset_index)
    mapping_sha = _canonical_sha256(mapping)
    candidate_set = load_prediction_set(predictions_dir)
    predictions, assembly = _assemble(mapping, candidate_set)
    try:
        result = _score(predictions, track=candidate_set["track"], gold=gold, adjudicated=adjudicated, unreviewed=unreviewed,
                        profiles=profile_ids, alignment_masked=alignment_masked, cell_view=cell_view)
        comparison = None
        baseline_set = None
        if baseline_predictions_dir is not None:
            baseline_set = load_prediction_set(baseline_predictions_dir)
            baseline_predictions, _ = _assemble(mapping, baseline_set)
            baseline = _score(baseline_predictions, track=baseline_set["track"], gold=gold, adjudicated=adjudicated,
                              unreviewed=unreviewed if diagnostic_only else None,
                              profiles=profile_ids, alignment_masked=False, cell_view=cell_view)
            compare = _diagnostic_comparison if diagnostic_only else _comparison
            comparison = compare(baseline, result, baseline_set, candidate_set)
    except ValueError as exc:
        raise StageExecutionError(str(exc)) from exc
    references = [identity for identity in (gold and gold["identity"], adjudicated and adjudicated["identity"]) if identity]

    def prediction_summary(prediction_set: dict[str, Any]) -> dict[str, Any]:
        return {
            "set_sha256": prediction_set["set_sha256"],
            "track": prediction_set["track"],
            "files": [{"file_name": r["file_name"], "sha256": r["file_sha256"], "page_id": r["page_id"],
                       "schema_version": r["schema_version"]} for r in prediction_set["pages"].values()],
            "engines": [{"name": n, "version": v} for n, v in prediction_set["engines"]],
            "pipelines": [json.loads(p) for p in prediction_set["pipelines"]],
        }

    run_record = {
        "schema_version": RUN_RECORD_SCHEMA_VERSION,
        "hocrgen_version": __version__,
        "predictions": prediction_summary(candidate_set),
        "baseline_predictions": prediction_summary(baseline_set) if baseline_set else None,
        "mapping": {"sha256": mapping_sha, "schema_version": MAPPING_SCHEMA_VERSION,
                    "mapping_source": mapping["mapping_source"], **assembly},
        "references": references,
        "excluded_references": adjudicated["excluded"] if adjudicated else [],
        "unreviewed_texts_sha256": unreviewed["sha256"] if unreviewed else None,
        "profiles": profile_ids,
        "primary_profile": PRIMARY_PROFILE_ID,
        "scored_origins": sorted(result["scored"]),
        "scored_set_policy": "synthetic gold and reviewed+adjudicated references only; unreviewed text is diagnostic",
        "diagnostic_only": diagnostic_only,
    }
    if cell_view is not None:
        run_record["reference_views"] = [{"origin": "synthetic_gold", "view_id": cell_view["view_id"],
                                          "source": cell_view["source"], "item_count": len(cell_view["texts"])}]
    if diagnostic_only:
        run_record["benchmark_ready"] = False
        run_record["scored_set_policy"] = "diagnostic only: no scored set; unreviewed text under unreviewed_diagnostics"
        return {"status": "ok", "diagnostic_only": True, "benchmark_ready": False, "run_record": run_record,
                "mapping": mapping, **result, **({"diagnostic_comparison": comparison} if comparison else {})}
    return {"status": "ok", "run_record": run_record, "mapping": mapping, **result,
            **({"comparison": comparison} if comparison else {})}


__all__ = [
    "build_mapping_from_asset_sha256", "load_adjudicated_references",
    "load_engine_prediction", "load_per_cell_view", "load_prediction_set", "load_synthetic_gold",
    "load_unreviewed_texts",
    "run_reference_evaluation", "validate_mapping",
]
