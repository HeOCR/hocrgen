from __future__ import annotations

from pathlib import Path

from hocrgen.config.loader import ConfigBundle, load_json_file
from hocrgen.config.models import SourceConfig
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, AssetReference, CandidateRecord, EnrichedCandidateRecord, ItemRecord
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file


class BibliaImporter:
    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        records_path = bundle.resolve_path(source.settings.records_path or "")
        records = load_json_file(records_path)["records"]
        candidates: list[CandidateRecord] = []
        selected_count = 0
        for record in records:
            source_depth_only = record.get("f1_source_depth_only") is True
            if source_depth_only and not options.f1_target_scale_trial:
                continue
            if options.max_items is not None and selected_count >= options.max_items:
                break
            selected_count += 1
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{record['id']}",
                    source_id=source.id,
                    source_item_id=record["id"],
                    source_url=record["source_url"],
                    discovery_method="f1_target_scale_static_importer" if source_depth_only else "static_importer",
                    title=record["title"],
                    raw_metadata={
                        "f1_target_scale_trial": options.f1_target_scale_trial,
                        "f1_source_depth_only": source_depth_only,
                        "record_path": str(records_path),
                        "record": record,
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            record = candidate.raw_metadata["record"]
            record_path = Path(candidate.raw_metadata["record_path"])
            asset_ref = record["asset_path"]
            if isinstance(asset_ref, str) and asset_ref.startswith("package://"):
                asset_path = bundle.resolve_path(asset_ref)
            else:
                asset_path = Path(asset_ref).resolve() if Path(asset_ref).is_absolute() else (record_path.parent / asset_ref).resolve()
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=record["raw_rights"],
                    asset_references=[AssetReference(reference=record["asset_path"], resolved_path=str(asset_path))],
                    metadata={
                        "collection": record["collection"],
                        "period": record["period"],
                        "upstream_identifier": record["upstream_identifier"],
                    },
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            asset = item.asset_references[0]
            resolved = Path(asset.resolved_path or "")
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[
                        AcquiredAsset(
                            item_id=item.item_id,
                            path=str(destination),
                            sha256=sha256_file(destination),
                            media_type=asset.media_type,
                        )
                    ],
                )
            )
        return acquired_items
