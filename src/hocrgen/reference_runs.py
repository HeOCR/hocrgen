"""E2c4: offline reference-aware evaluation runs over engine prediction files, with a run record.

Scored set: synthetic gold derived from a validated hocrsyngen batch, plus reviewed/adjudicated
``benchmark_transcription_reference.v1`` records. HASH, tender, or any other unreviewed text is scored only as
``unreviewed`` diagnostics and never enters scored aggregates.
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
from hocrgen.manifests.models import BenchmarkReferenceManifestItemRecord, BenchmarkTranscriptionReferenceRecord
from hocrgen.reference_evaluation import (
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
    input_sha = (payload.get("input") or {}).get("sha256")
    engine = payload.get("engine") or {}
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
    seen_items: set[str] = set()
    seen_pages: set[str] = set()
    for item in payload.get("items", []):
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


def load_adjudicated_references(manifest_path: Path) -> dict[str, Any]:
    """Load reviewed+adjudicated transcription references; anything else is excluded with a reason."""
    payload, manifest_sha = _read_json(manifest_path, "reference manifest")
    if not isinstance(payload, dict) or payload.get("schema_version") != "benchmark_reference_manifest.v1":
        raise StageExecutionError("reference manifest must use benchmark_reference_manifest.v1")
    references, strata, excluded = {}, {}, []
    for raw_item in payload.get("items", []):
        item = BenchmarkReferenceManifestItemRecord.model_validate(raw_item)
        if item.public_reference_status not in {"reviewed", "adjudicated"} or item.adjudication_status != "adjudicated":
            excluded.append({"item_id": item.item_id, "reason": "reference is not reviewed and adjudicated"})
            continue
        if item.transcription_reference is None:
            excluded.append({"item_id": item.item_id, "reason": "no transcription reference"})
            continue
        child_path = (manifest_path.parent / item.transcription_reference.path).resolve()
        if manifest_path.parent.resolve() not in child_path.parents:
            raise StageExecutionError(f"reference path escapes manifest directory for {item.item_id}")
        child, _ = _read_json(child_path, "transcription reference")
        record = BenchmarkTranscriptionReferenceRecord.model_validate(child)
        if record.item_id != item.item_id:
            raise StageExecutionError(f"reference item id mismatch for {item.item_id}")
        references[item.item_id] = record
        strata[item.item_id] = {"reference_origin": "adjudicated_reference"}
    return {"references": references, "strata": strata, "excluded": excluded,
            "identity": {"kind": "benchmark_reference_manifest", "sha256": manifest_sha,
                         "reference_manifest_id": payload.get("reference_manifest_id")}}


def load_unreviewed_texts(path: Path) -> dict[str, Any]:
    """JSONL of ``{item_id, text, ...strata}`` for unreviewed candidate texts (HASH, tenders, etc.)."""
    try:
        raw = path.read_bytes()
        lines = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StageExecutionError(f"could not read unreviewed texts {path.name}: {exc}") from exc
    texts, strata = {}, {}
    for line in lines:
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
           alignment_masked: bool) -> dict[str, Any]:
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
    if unreviewed and unreviewed["texts"]:
        diagnostic = evaluate_text_profiles(
            sorted(unreviewed["texts"]),
            predictions={k: v for k, v in predictions.items() if k in unreviewed["texts"]},
            references=unreviewed["texts"], profiles=profiles, item_strata=unreviewed["strata"])
        result["unreviewed_diagnostics"] = {"reference_status": "unreviewed", "benchmark_ready": False,
                                            "scored": False, "track": track, **diagnostic}
    return result


def _stage_key(stage: Mapping[str, Any]) -> str:
    return json.dumps(stage, sort_keys=True)


def _comparison(baseline: dict[str, Any], candidate: dict[str, Any], base_set: dict, cand_set: dict) -> dict[str, Any]:
    if base_set["track"] != cand_set["track"]:
        raise StageExecutionError(
            f"refusing to compare a {base_set['track']}-track baseline with a {cand_set['track']}-track candidate"
        )
    deltas: dict[str, Any] = {}
    for origin, report in candidate["scored"].items():
        base_report = baseline["scored"].get(origin)
        if base_report is None:
            continue
        common = sorted({i["item_id"] for i in report["items"]} & {i["item_id"] for i in base_report["items"]})
        deltas[origin] = {
            "common_item_count": len(common),
            "profiles": {
                profile_id: {
                    "baseline_cer": base_report["profiles"][profile_id]["cer"],
                    "candidate_cer": report["profiles"][profile_id]["cer"],
                    "delta_cer": (None if None in (base_report["profiles"][profile_id]["cer"],
                                                   report["profiles"][profile_id]["cer"])
                                  else report["profiles"][profile_id]["cer"] - base_report["profiles"][profile_id]["cer"]),
                    "delta_wer": (None if None in (base_report["profiles"][profile_id]["wer"],
                                                   report["profiles"][profile_id]["wer"])
                                  else report["profiles"][profile_id]["wer"] - base_report["profiles"][profile_id]["wer"]),
                }
                for profile_id in report["profiles"]
            },
        }
    base_stages = {_stage_key(s) for p in base_set["pipelines"] for s in json.loads(p)}
    cand_stages = {_stage_key(s) for p in cand_set["pipelines"] for s in json.loads(p)}
    added = sorted(cand_stages - base_stages)
    removed = sorted(base_stages - cand_stages)
    single = len(added) + len(removed) == 1 and len(base_set["pipelines"]) == len(cand_set["pipelines"]) == 1
    return {
        "track": cand_set["track"],
        "deltas": deltas,
        "stage_changes": {"added": [json.loads(s) for s in added], "removed": [json.loads(s) for s in removed]},
        "single_stage_attribution": (json.loads((added or removed)[0]) if single else None),
        "attribution_note": "delta is attributed to a stage only when exactly one recorded pipeline stage differs "
                            "and each set used one pipeline; otherwise it is a set-level delta",
    }


def run_reference_evaluation(
    *, predictions_dir: Path, synthetic_batch: Path | None = None, reference_manifest: Path | None = None,
    unreviewed_texts: Path | None = None, mapping_path: Path | None = None, asset_index_path: Path | None = None,
    baseline_predictions_dir: Path | None = None, profiles: Iterable[str] = DEFAULT_PROFILE_IDS,
    alignment_masked: bool = False,
) -> dict[str, Any]:
    if synthetic_batch is None and reference_manifest is None:
        raise StageExecutionError("a scored set is required: --synthetic-batch and/or --reference-manifest")
    profile_ids = list(profiles)
    if PRIMARY_PROFILE_ID not in profile_ids or set(profile_ids) - NORMALIZATION_PROFILES.keys():
        raise StageExecutionError(f"profiles must be known and include {PRIMARY_PROFILE_ID}")
    gold = load_synthetic_gold(synthetic_batch) if synthetic_batch else None
    adjudicated = load_adjudicated_references(reference_manifest) if reference_manifest else None
    unreviewed = load_unreviewed_texts(unreviewed_texts) if unreviewed_texts else None
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
                        profiles=profile_ids, alignment_masked=alignment_masked)
        comparison = None
        baseline_set = None
        if baseline_predictions_dir is not None:
            baseline_set = load_prediction_set(baseline_predictions_dir)
            baseline_predictions, _ = _assemble(mapping, baseline_set)
            baseline = _score(baseline_predictions, track=baseline_set["track"], gold=gold, adjudicated=adjudicated,
                              unreviewed=None,
                              profiles=profile_ids, alignment_masked=False)
            comparison = _comparison(baseline, result, baseline_set, candidate_set)
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
    }
    return {"status": "ok", "run_record": run_record, "mapping": mapping, **result,
            **({"comparison": comparison} if comparison else {})}


__all__ = [
    "build_mapping_from_asset_sha256", "load_adjudicated_references",
    "load_engine_prediction", "load_prediction_set", "load_synthetic_gold", "load_unreviewed_texts",
    "run_reference_evaluation", "validate_mapping",
]
