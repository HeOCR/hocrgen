# Synthetic Asset Contribution Guide

Synthetic data helps hocrgen exercise the pipeline and provide bounded OCR-relevant examples. It must remain governed, reproducible, and visibly capped so it does not overpower real-source identity.

Advanced synthetic OCR/HTR generation is split into the separate `hocrsyngen` package. This repository keeps only governed legacy smoke assets, provider-contract fixtures, and hocrgen-side validation/export policy. Generated outputs from `hocrsyngen` are candidate synthetic inputs, not release-ready data by themselves.

## Acceptable synthetic contributions

The project may accept:

- fonts with clear redistribution rights and committed license text
- curated Hebrew text corpus additions with provenance notes
- deterministic recipe, layout, or degradation improvements
- fixture-backed `generation_manifest.json` examples for the external `hocrsyngen` provider contract
- provider metadata and validation rules that improve Hebrew rendering, provenance, or export portability checks
- manifest metadata that improves reporting or filtering
- tests that make synthetic composition and release caps more reliable

The project should not accept:

- assets with unclear reuse rights
- prompts or generated corpora that cannot be audited
- synthetic changes that remove `profile_open_v1` caps or alpha export clamps
- visual treatments that imply real provenance for generated content
- broad `hocrsyngen` implementation work inside `hocrgen`
- REST-service, GPU, LLM, diffusion, or heavyweight generator dependencies in baseline hocrgen tests or release builds
- persona, condition, or handwriting controls that claim psychological truth, real-writer identity, or demographic authority
- broad new generation workflows without a roadmap item

## External generator boundary

The four-repository boundary is:

- `hocrsyngen`: Python package and CLI for generating synthetic Hebrew OCR/HTR sample units and manifests.
- `hocrgen`: orchestration, governance, rights/provenance disclosure, privacy, review, dedupe, split, benchmark, synthetic caps, and export portability.
- `HeOCR`: mixed real+synthetic public dataset releases exported by `hocrgen`.
- `HeOCRsynth`: synthetic-only dataset releases exported by `hocrgen`.

The provider contract starts with `hocrsyngen` emitting `generation_manifest.json` plus relative image assets. Manifest v1 includes sample id, page assets, logical-order UTF-8 text, script/language/direction metadata, hocrsyngen provider metadata, offline manifest-batch generation mode, explicit no-network/no-REST/no-GPU/no-LLM/no-diffusion flags, rendering metadata for logical RTL Hebrew pages, computed Hebrew coverage metadata, generator version, recipe id, seed/provenance, license `PROJECT-SYNTHETIC`, synthetic disclosure, and optional persona/condition controls. hocrgen reads fixture-backed `generation_manifest.v1` batches and validates them on its side, including unique sample/page/asset identities and Hebrew rendering/provider metadata before mapping samples into hocrgen item ids. It should not call `hocrsyngen generate`, `hocrsyngen validate`, a live service, or require network, GPU, LLM, diffusion, or heavyweight generator dependencies in baseline tests or release builds. hocrsyngen CLI JSON reports are command reports only, not hocrgen release manifests.

The current `project_synthetic` source is hocrsyngen manifest-backed. It preserves legacy `project_synthetic:synthetic-*` item ids through a validated sample-index compatibility mapping, but exact logical text from the provider manifest is not published as generic item metadata. The old internal generator code remains legacy deterministic smoke coverage until it can be retired safely.

Synthetic-only dataset handoff uses `hocrgen export-synthetic`. The command runs the normal hocrgen gates through `build-release`, selects only release-ready synthetic `PROJECT-SYNTHETIC` items from pipeline state, preserves synthetic disclosure plus hocrsyngen provider/rendering/Hebrew coverage metadata, and writes payload assets under `data/synthetic/<split>/<item_id>/`. This keeps `HeOCRsynth` releases distinct from mixed `HeOCR` releases and prevents raw generator batches from being mistaken for governed public artifacts.

## Font contributions

Font PRs must include:

- the font file under `src/hocrgen/data/synthetic/fonts/`
- the full license text next to the font
- a `manifest.yaml` entry using the current packaged font manifest shape: `id`, `file`, `style`, and `notes`
- a note in `notes` or the PR description explaining why the committed license allows redistribution and generated dataset use
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
- `synthetic_provider_version`
- `synthetic_layout_family`
- `synthetic_hebrew_coverage`

If a new recipe is public-profile eligible, update tests and docs that describe `synthetic_composition.json`, alpha export selection, and release summary behavior.

## Release safeguards

Synthetic assets must remain subject to:

- typed source config validation
- source-health expectations for configured fonts and corpora
- release profile synthetic fraction caps
- alpha export real-item based synthetic clamps
- composition reporting in `build-release`, `export-alpha`, and `export-synthetic`
- review of license and provenance evidence before merge
- release-relative and portable export paths
- explicit synthetic disclosure in mixed `HeOCR` releases and synthetic-only `HeOCRsynth` releases

Synthetic output is never a substitute for rights-safe real-source acquisition. `HeOCRsynth` exports must come from `hocrgen` release handoffs, not raw generator dumps.
