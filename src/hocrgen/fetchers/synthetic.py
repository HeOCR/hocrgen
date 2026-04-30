from __future__ import annotations

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import AcquiredAsset, AcquiredItemRecord, CandidateRecord, EnrichedCandidateRecord, ItemRecord
from hocrgen.synthetic.generator import generate_documents, recipe_catalog


def _template_ids_for_options(source: SourceConfig, options: StageOptions) -> list[str]:
    template_ids = source.settings.template_ids or ["printed_letter", "handwritten_note"]
    recipes = recipe_catalog(template_ids)
    selected: list[str] = []
    for template_id in template_ids:
        recipe = recipes[template_id]
        if options.synthetic_template_filter and template_id not in options.synthetic_template_filter:
            continue
        if options.synthetic_recipe_filter and recipe.recipe_id not in options.synthetic_recipe_filter:
            continue
        if options.synthetic_degradation_filter and recipe.degradation_preset not in options.synthetic_degradation_filter:
            continue
        selected.append(template_id)
    if not selected:
        controls = {
            "templates": sorted(options.synthetic_template_filter or []),
            "recipes": sorted(options.synthetic_recipe_filter or []),
            "degradation_presets": sorted(options.synthetic_degradation_filter or []),
        }
        raise StageExecutionError(f"synthetic controls selected no configured templates for source {source.id}: {controls}")
    return selected


class SyntheticFetcher:
    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        del bundle
        count = source.settings.synthetic_batch_size or 1
        template_ids = _template_ids_for_options(source, options)
        recipes = recipe_catalog(template_ids)
        candidates: list[CandidateRecord] = []
        for index in range(count):
            template_id = template_ids[index % len(template_ids)]
            recipe = recipes[template_id]
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:synthetic:{index}",
                    source_id=source.id,
                    source_item_id=f"synthetic-{index}",
                    source_url=f"synthetic://{source.id}/{index}",
                    discovery_method="synthetic_generator",
                    title=f"Synthetic sample {index + 1}",
                    raw_metadata={
                        "synthetic_index": index,
                        "synthetic_template_id": template_id,
                        "synthetic_recipe_id": recipe.recipe_id,
                        "synthetic_degradation_preset": recipe.degradation_preset,
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        del bundle
        selected_templates = _template_ids_for_options(source, options)
        recipes = recipe_catalog(selected_templates)
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            template_id = str(candidate.raw_metadata.get("synthetic_template_id") or selected_templates[0])
            recipe = recipes[template_id]
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text="PROJECT-SYNTHETIC",
                    metadata={
                        "synthetic_template_id": template_id,
                        "synthetic_recipe_id": recipe.recipe_id,
                        "synthetic_degradation_preset": recipe.degradation_preset,
                        "synthetic_available_template_ids": selected_templates,
                    },
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        items = list(items)
        seed = options.synthetic_seed if options.synthetic_seed is not None else (source.settings.synthetic_seed or 17)
        selected_templates = _template_ids_for_options(source, options)
        template_ids = [
            str(item.metadata.get("synthetic_template_id") or selected_templates[index % len(selected_templates)])
            for index, item in enumerate(items)
        ]
        documents = generate_documents(
            count=len(items),
            seed=seed,
            template_ids=template_ids,
            font_manifest_path=bundle.resolve_path(source.settings.font_manifest or ""),
            text_corpus_path=bundle.resolve_path(source.settings.text_corpus_path or ""),
            output_dir=output_dir / source.id,
        )
        acquired_items: list[AcquiredItemRecord] = []
        for item, document in zip(items, documents, strict=True):
            item_data = item.model_dump()
            existing_metadata = dict(item_data.pop("metadata"))
            item_data.pop("title", None)
            acquired_items.append(
                AcquiredItemRecord(
                    **item_data,
                    title=document.title,
                    metadata={
                        **existing_metadata,
                        "synthetic_template_id": document.template_id,
                        "synthetic_recipe_id": document.recipe_id,
                        "synthetic_degradation_preset": document.degradation_preset,
                        "synthetic_font_id": document.font_id,
                        "synthetic_footer": document.footer,
                        "synthetic_generator_version": document.generator_version,
                    },
                    acquired_assets=[
                        AcquiredAsset(
                            item_id=item.item_id,
                            path=str(document.path),
                            sha256=document.sha256,
                            media_type="image/jpeg",
                        )
                    ],
                )
            )
        return acquired_items
