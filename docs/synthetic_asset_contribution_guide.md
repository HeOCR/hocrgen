# Synthetic Asset Contribution Guide

Synthetic data helps hocrgen exercise the pipeline and provide bounded OCR-relevant examples. It must remain governed, reproducible, and visibly capped so it does not overpower real-source identity.

## Acceptable synthetic contributions

The project may accept:

- fonts with clear redistribution rights and committed license text
- curated Hebrew text corpus additions with provenance notes
- deterministic recipe, layout, or degradation improvements
- manifest metadata that improves reporting or filtering
- tests that make synthetic composition and release caps more reliable

The project should not accept:

- assets with unclear reuse rights
- prompts or generated corpora that cannot be audited
- synthetic changes that remove `profile_open_v1` caps or alpha export clamps
- visual treatments that imply real provenance for generated content
- broad new generation workflows without a roadmap item

## Font contributions

Font PRs must include:

- the font file under `src/hocrgen/data/synthetic/fonts/`
- the full license text next to the font
- a `manifest.yaml` entry with font id, family/name, license id, and file path
- a note explaining why the license allows redistribution and generated dataset use
- deterministic test or smoke output coverage if the font changes default generation

Do not rely on a website summary alone. Include the committed license artifact used for review.

## Text corpus contributions

Text corpus PRs must include:

- source/provenance notes for the text
- confirmation that the text is public-domain, project-authored, or otherwise reusable
- Hebrew text that is OCR-relevant and does not include personal or sensitive modern records
- deterministic updates to generation expectations when line counts or defaults change

Avoid adding modern names, addresses, phone numbers, emails, or sensitive records to synthetic corpora. If such content is necessary for a future privacy test, keep it in test fixtures and route it through privacy-specific tests, not public synthetic defaults.

## Recipe and degradation contributions

Recipe changes should preserve existing reporting metadata:

- `synthetic_template_id`
- `synthetic_recipe_id`
- `synthetic_degradation_preset`
- `synthetic_font_id`

If a new recipe is public-profile eligible, update tests and docs that describe `synthetic_composition.json`, alpha export selection, and release summary behavior.

## Release safeguards

Synthetic assets must remain subject to:

- typed source config validation
- source-health expectations for configured fonts and corpora
- release profile synthetic fraction caps
- alpha export real-item based synthetic clamps
- composition reporting in `build-release` and `export-alpha`
- review of license and provenance evidence before merge

Synthetic output is never a substitute for rights-safe real-source acquisition.
