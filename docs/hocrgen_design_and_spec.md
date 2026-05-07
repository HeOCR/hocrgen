# hocrgen Design and Specification

## 1. Overview

**hocrgen** is the open-source generation, acquisition, curation, packaging, and publishing toolchain for the **HeOCR** dataset.

Its purpose is to make HeOCR:

- reproducible
- policy-driven
- incrementally expandable
- legally conservative
- automatable primarily via GitHub Actions

`hocrgen` is not just a scraper. It is a **dataset operations system** for a public Hebrew OCR/HTR dataset.

It should support the full lifecycle of the dataset:

1. source definition
2. candidate discovery
3. rights filtering
4. download/acquisition
5. normalization
6. deduplication
7. classification
8. privacy/sensitivity checks
9. manual review where needed
10. split assignment
11. packaging
12. publication
13. changelog and provenance generation

---

## 2. Product goals

### 2.1 Primary goals

`hocrgen` should:

1. generate and expand HeOCR from approved upstream sources
2. enforce source-level and item-level policy constraints
3. support both real scans and synthetic generation
4. preserve per-item provenance and rights metadata
5. produce versioned releases
6. publish releases to:
   - Hugging Face
   - the separate `HeOCR` GitHub repo
7. run most recurring maintenance and release work on GitHub Actions
8. keep all decisions auditable through manifests and logs

### 2.2 Non-goals

At least initially, `hocrgen` is not intended to:

- be a generic web crawler for arbitrary archives
- perform full transcription of all data
- solve annotation at scale
- silently ingest rights-ambiguous content
- replace legal review where needed
- act as a monolithic data lake for unrestricted raw scraping

---

## 3. Design principles

### 3.1 Policy first
Every acquisition path must be governed by explicit source and release policy.

### 3.2 Reproducibility over convenience
Every dataset release should be reconstructible or at least auditable from configs, source manifests, and tool versions.

### 3.3 Conservative rights posture
Anything unclear should be blocked or routed to review, not silently included.

Modern contributor-supplied handwriting is always high-risk until consent, release terms, provenance, privacy screening, and takedown handling are explicit.

### 3.4 Metadata is first-class
The system should treat metadata and provenance as core outputs, not byproducts.

### 3.5 GitHub-first operations
Most recurring workflows should run from GitHub Actions, with local execution as a compatible fallback.

### 3.6 Bounded automation
Automate aggressively where safe, but always preserve policy boundaries and review hooks.

### 3.7 Modularity
New sources, new checks, new release profiles, and new publishers should be addable without rewriting the system.

---

## 4. System responsibilities

`hocrgen` should be responsible for:

- reading source registry and release profiles
- discovering candidate items from approved sources
- extracting source and rights metadata
- filtering items by policy
- downloading image assets and related metadata
- normalizing files and computing checksums
- deduplicating exact and near-duplicate items
- classifying items by type and period
- flagging privacy/sensitivity risks
- routing items to review queues where needed
- constructing train/validation/test splits
- generating dataset manifests and QA reports
- packaging release bundles
- publishing to external targets
- emitting release changelogs and statistics

It should not be responsible for training OCR models, though it may later emit benchmark helpers or baseline-evaluation artifacts.

---

## 5. High-level architecture

`hocrgen` should be implemented as a Python package and CLI with a pipeline-oriented architecture.

### 5.1 Main layers

1. **Configuration layer**
   - source registry
   - release profiles
   - thresholds
   - policy files

2. **Acquisition layer**
   - source adapters/fetchers
   - rights parsing
   - metadata extraction
   - file download
   - operator-provided modern handwriting intake manifests governed by the F3a/F3b policy

3. **Processing layer**
   - normalization
   - dedupe
   - classification
   - privacy flagging
   - quality scoring

4. **Curation layer**
   - review queues
   - allowlists/blocklists
   - release eligibility
   - split assignment

5. **Packaging layer**
   - release manifests
   - dataset structure
   - dataset cards
   - reports

6. **Publishing layer**
   - Hugging Face publish
   - GitHub dataset repo sync
   - release notes/changelog output

7. **Operations layer**
   - CLI
   - logging
   - state tracking
   - GitHub Actions workflows

---

## 6. Core concepts

### 6.1 Source
A source is an upstream origin of candidate content.

Examples:

- NLI `Any Use Permitted`
- Pinkas
- BiblIA
- project synthetic generator
- JPress
- Israel State Archives

Each source must have:

- identity
- status
- fetcher type
- allowed content types
- rights interpretation strategy
- release eligibility

### 6.2 Release profile
A release profile defines what kinds of sources and items are allowed into a release.

Examples:

- `profile_open_v1`
- `profile_review_v1`

Release profiles are the primary mechanism by which public vs review-only releases are separated.

### 6.3 Candidate
A candidate is a discovered item not yet accepted into a release.

### 6.4 Item
An item is a normalized dataset unit with assigned metadata and eligibility state.

### 6.5 Review decision
A review decision is a persisted human or policy-driven judgment about a candidate or item.

### 6.6 Modern handwriting intake
Modern handwriting intake is an operator-provided contributor-supplied acquisition path governed by the F3a policy in [`modern_handwritten_acquisition_policy.md`](./modern_handwritten_acquisition_policy.md) and implemented by the F3b `modern_handwriting_intake` adapter. It stays separate from historical public sources and synthetic-provider inputs, requires consent/provenance/privacy records before review, uses typed source-relative manifests, and requires explicit review approval before any public-profile eligibility.

### 6.7 Release
A release is a versioned packaged dataset output, including assets, metadata, and changelog.

---

## 7. Repository layout

Recommended repository layout:

```text
hocrgen/
  README.md
  pyproject.toml
  src/hocrgen/
    __init__.py
    cli.py
    config/
      loader.py
      models.py
      profiles/
        profile_open_v1.yaml
        profile_review_v1.yaml
      sources.yaml
      licenses.yaml
      quality_thresholds.yaml
      privacy_rules.yaml
    core/
      context.py
      state.py
      errors.py
      logging.py
    fetchers/
      base.py
      nli.py
      pinkas.py
      biblia.py
      jpress.py
      state_archives.py
      synthetic.py
    parsers/
      rights.py
      metadata.py
      html.py
      image_links.py
    normalize/
      files.py
      images.py
      metadata.py
    dedupe/
      exact.py
      phash.py
      clustering.py
    classify/
      content_type.py
      period.py
      language.py
      quality.py
    privacy/
      rules.py
      detectors.py
    review/
      queue.py
      decisions.py
      sampling.py
    split/
      assignment.py
      leakage.py
    manifests/
      items.py
      sources.py
      release.py
      changelog.py
      stats.py
    package/
      layout.py
      dataset_card.py
      bundle.py
    publish/
      huggingface.py
      github_repo.py
    synthetic/
      generator.py
      recipes.py
      assets.py
      render.py
      degrade.py
    utils/
      hashing.py
      io.py
      imaging.py
      dates.py
      text.py
      concurrency.py
      ids.py
  schemas/
    item.schema.json
    source.schema.json
    review_decision.schema.json
    release.schema.json
  tests/
  docs/
    architecture.md
    source-policy.md
    release-profiles.md
    contributing.md
  synthetic_assets/
    fonts/
      manifest.yaml
    templates/
    backgrounds/
    overlays/
    text_corpora/
  review_data/
    allowlists/
    blocklists/
    manual_decisions/
  .github/
    workflows/
      source_discovery.yml
      synthetic_generate.yml
      build_open_release.yml
      build_review_release.yml
      publish_hf.yml
      publish_github_dataset.yml
      validate_configs.yml
```

---

## 8. Configuration model

Configuration should be YAML-based, version-controlled, and validated on load.

### 8.1 Main config families

1. `sources.yaml`
2. release profile YAML files
3. `licenses.yaml`
4. `quality_thresholds.yaml`
5. `privacy_rules.yaml`
6. synthetic asset manifests
7. optional secrets/environment variables

### 8.2 Source registry schema

Each source definition should include fields like:

```yaml
sources:
  - id: nli_any_use_permitted
    name: National Library of Israel - Any Use Permitted items
    fetcher: nli
    status: allowed
    default_public_release: true
    allowed_content_types:
      - handwritten_modern
      - printed_modern
      - handwritten_historical
    rights_strategy:
      type: exact_match
      values:
        - "Any Use Permitted"
    normalized_license: PD-IL
    rights_classification: open
    requires_manual_review: false
```

### 8.3 Release profile schema

A profile should define:

- release profile id
- included sources
- excluded sources
- allowed rights classes
- synthetic cap
- split rules
- quality thresholds
- privacy policy mode
- publication targets

Example:

```yaml
id: profile_open_v1
description: Default public HeOCR release
include_sources:
  - nli_any_use_permitted
  - pinkas_open
  - biblia_open
  - project_synthetic
exclude_sources:
  - jpress
  - state_archives_selected
allowed_rights_classifications:
  - open
  - open_with_attribution
  - sharealike
synthetic_fraction_max: 0.5
privacy_mode: conservative
publish_targets:
  - huggingface
  - github_dataset_repo
```

### 8.4 Secret/config boundary

Anything environment-specific or sensitive should come from env vars or GitHub secrets, not committed YAML.

Examples:

- Hugging Face token
- GitHub token for dataset repo sync
- optional authenticated source tokens if ever needed

---

## 9. Data model

`hocrgen` should use explicit typed models internally and stable serialized schemas externally.

### 9.1 Main entities

- `SourceConfig`
- `ReleaseProfile`
- `CandidateRecord`
- `ItemRecord`
- `ReviewDecision`
- `ReleaseManifest`
- `PublishResult`

### 9.2 Candidate record fields

A candidate record should include:

- candidate id
- source id
- source item identifier
- source URL
- discovery timestamp
- raw metadata
- raw rights text
- discovery status

### 9.3 Item record fields

An item record should include at minimum:

- item id
- release profile
- source metadata
- rights metadata
- provenance metadata
- classification metadata
- file paths
- checksums
- quality metrics
- review state
- split
- version-added / version-removed fields

### 9.4 Suggested serialized format

For release manifests and larger tables:

- **Parquet** for tabular metadata
- JSON for schema-level or summary metadata
- Markdown for human-readable reports and dataset cards

### 9.5 Schema evolution policy

Serialized release schemas should be additive within a schema version. Optional fields with safe defaults are acceptable when validation, tests, and docs are updated. Removing fields, changing path semantics, changing controlled-vocabulary meanings, or making optional annotation/benchmark fields mandatory is breaking and requires a new schema version or schema id plus migration notes.

Release consumers should use explicit `schema_version` and schema id fields to determine compatibility. Public release paths must remain release-relative and portable across schema revisions.

---

## 10. Pipeline stages

The system should be organized into explicit, resumable pipeline stages.

### 10.1 Stage 1 — discover

Input:
- source registry
- release profile or source selection
- optional allowlists/blocklists

Actions:
- query source adapters
- enumerate candidate items
- capture candidate URLs and raw metadata

Outputs:
- candidate manifest
- discovery logs
- source stats

### 10.2 Stage 2 — fetch-metadata

Actions:
- fetch detailed item pages or dataset records
- parse rights fields
- parse metadata fields
- identify downloadable image assets

Outputs:
- enriched candidate manifest
- fetch errors log
- raw metadata cache

### 10.3 Stage 3 — policy-filter

Actions:
- apply source status rules
- apply rights rules
- apply release profile filters
- apply allowlists/blocklists

Outputs:
- eligible candidates
- rejected candidates with reasons
- needs-review candidates

### 10.4 Stage 4 — acquire

Actions:
- download image assets
- preserve original filenames where useful
- capture acquisition metadata
- compute checksums

Outputs:
- raw asset store
- acquisition manifest

### 10.5 Stage 5 — normalize

Actions:
- validate decodability
- normalize images into standard formats if needed
- generate thumbnails
- extract dimensions and technical metadata

Outputs:
- normalized asset store
- technical metadata

### 10.6 Stage 6 — dedupe

Actions:
- exact duplicate detection
- deterministic near-duplicate candidate surfacing from content-derived quantized thumbnails
- source-work group derivation for split safety
- optional future perceptual-hash or embedding-based near-duplicate clustering

Outputs:
- dedupe manifest
- retained-item set
- duplicate clusters
- near-duplicate candidate clusters
- source groups

### 10.7 Stage 7 — classify

Actions:
- classify handwritten / printed / mixed
- classify modern / historical
- classify Hebrew-only / mixed-language
- compute quality score

Outputs:
- classified item table

### 10.8 Stage 8 — privacy / sensitivity scan

Actions:
- heuristic OCR if needed
- metadata-based rules
- optional pattern matching for personal data risk
- source-specific safety rules

Outputs:
- privacy flags
- review queue candidates

### 10.9 Stage 9 — review integration

Actions:
- merge manual review decisions
- sample borderline items for review
- apply allowlist/blocklist overrides

Outputs:
- approved item set
- rejected item set
- unresolved review set

### 10.10 Stage 10 — split

Actions:
- assign train / validation / test
- prevent leakage across related documents or duplicates
- respect benchmark subset rules

Outputs:
- split manifest
- leakage report

Benchmark/holdout leakage is enforced after benchmark selection during release assembly. The gate checks whether benchmark items share exact duplicate, near-duplicate, or source-group membership with non-benchmark holdout/public-beta candidates. Such overlap is blocked unless the benchmark config carries a typed accepted resolution that exactly matches the detected group kind, group id, benchmark item ids, and non-benchmark item ids. This keeps benchmark stability separate from public-beta readiness: accepted resolutions can preserve `benchmark_v1` membership while excluding related non-benchmark items from holdout/public-beta claims.

### 10.11 Stage 11 — package

Actions:
- construct release folder layout
- generate manifests
- generate stats
- generate benchmark leakage-risk and resolution artifacts
- generate changelog diff from prior release
- generate dataset card draft

Outputs:
- release bundle

### 10.12 Stage 12 — publish

Actions:
- publish to Hugging Face
- sync metadata and release files to `HeOCR` repo
- emit publication report

Outputs:
- publish artifacts
- final release record

F5a defines the readiness contract that must pass before this publishing stage is invoked for a mixed `HeOCR` public beta. F5b implements local blocked packaging and handoff verification, not final publication. F5c adds blocker-closure sequencing and repo-owned handoff gap reporting without changing publication side effects. Operator trial success is not enough: public publishability also requires source-depth/composition evidence, validated synthetic target scale and cap policy, rights/provenance closure, privacy/review closure, duplicate and leakage clearance, benchmark-reference status, annotation-status disclosure, release-relative manifest/checksum/archive portability, public dataset/provenance/changelog docs, and takedown/removal readiness.

---

## 11. Source adapter design

Source adapters should encapsulate source-specific discovery and parsing logic.

### 11.1 Base interface

Every fetcher should implement a common interface such as:

- `discover_candidates(...)`
- `fetch_candidate_metadata(...)`
- `resolve_downloads(...)`
- `download_assets(...)`
- `normalize_source_metadata(...)`

### 11.2 Required adapter behavior

Each adapter must:

- preserve source item identifiers
- return normalized rights metadata plus raw rights text
- emit structured parse errors
- support incremental or resumable operation
- avoid leaking source-specific quirks into the global pipeline

### 11.3 Expected initial adapters

- `nli`
- `pinkas`
- `biblia`
- `synthetic`

Adapters for `jpress` and `state_archives` can exist but should default to review-only paths.

### 11.4 Adapter testing

Each source adapter should have:

- fixture-based parsing tests
- schema tests
- regression tests for HTML/API changes where practical

---

## 12. Rights and licensing subsystem

This is one of the most important parts of `hocrgen`.

### 12.1 Responsibilities

The rights subsystem should:

- parse raw rights statements
- normalize them into controlled values
- assign release eligibility states
- attach attribution requirements
- prevent non-eligible items from entering public releases

### 12.2 Core outputs

For each item:

- `rights_label_raw`
- `license_raw`
- `license_normalized`
- `rights_classification`
- `redistribution_status`
- `attribution_text`

### 12.3 Controlled vocabulary

Recommended `license_normalized` values:

- `PD-IL`
- `CC-BY-4.0`
- `CC-BY-SA-4.0`
- `PROJECT-SYNTHETIC`
- `HEOCR-CONSENT-OPEN`
- `RESTRICTED-NONOPEN`
- `UNKNOWN`

Recommended `rights_classification` values:

- `open`
- `open_with_attribution`
- `sharealike`
- `restricted_review_only`
- `blocked`

### 12.4 Hard safety rule

A public release profile must fail validation if any included item has:

- `restricted_review_only`
- `blocked`
- `UNKNOWN`

unless the profile explicitly allows that, which `profile_open_v1` should not.

Modern handwritten contributor items add stricter requirements: public-profile eligibility also requires explicit contributor consent, compatible release terms, rights provenance, privacy clearance, operator review, and a takedown/removal path. Historical public-domain source evidence and synthetic-provider metadata are not substitutes for modern contributor consent.

---

## 13. Synthetic generation subsystem

Synthetic generation is a first-class module, not an external afterthought.

### 13.1 Goals

The synthetic subsystem should:

- generate realistic Hebrew document images
- add printed, handwritten-look, and mixed layouts
- optionally include English fragments
- produce reproducible samples with rich metadata
- stay within configured release proportions

For avoidance of doubt, "realistic" here means more than deterministic rendering. In concrete implementation terms, the synthetic subsystem should avoid:

- host-font fallback output that collapses handwritten samples into print-like typography
- prompt-like or self-referential text that reads like template instructions rather than document content
- decorative frames or card-like layouts that do not resemble plausible source documents
- pristine vector output with no scan-like imperfections when the target use case is document OCR

### 13.2 Subcomponents

- recipe loader
- text source selector
- template/layout engine
- font asset manager
- overlay/background/stamp engine
- scan degradation engine
- metadata emitter

### 13.3 Inputs

- approved text sources
- font manifest
- template definitions
- random seed
- profile settings

### 13.4 Outputs

For each synthetic item:

- generated image
- generation recipe id
- seed
- fonts used
- layout template id
- text-source references
- degradation recipe
- normalized license metadata
- provider metadata for fixture-backed hocrsyngen batches, including offline manifest-batch mode and explicit no-network/no-REST/no-GPU/no-LLM/no-diffusion flags
- Hebrew rendering metadata for logical RTL pages, bidi handling, font shaping, layout family, and line counts
- computed Hebrew coverage metadata for letters, final letters, niqqud, Arabic numerals, punctuation, and mixed LTR text

For near-term planning, the expected public-release path should assume a raster export mode for synthetic items, even if SVG remains acceptable as an intermediate development format. Synthetic outputs intended for release should therefore support:

- a release-grade raster asset path
- explicit record of rasterization settings
- explicit record of degradation settings
- the ability to distinguish "layout prototype" outputs from "release-ready synthetic sample" outputs

### 13.5 Asset governance

Synthetic assets must be tracked in a manifest:

- asset path
- asset type

Font assets should be treated as first-class governed inputs. In practice, this means:

- handwritten-like and print-like Hebrew fonts must be explicitly approved and tracked
- fallback host CSS stacks are acceptable only for early development scaffolding, not for release-quality synthetic samples
- each released synthetic sample should be attributable to a specific governed font asset, not an implicit system fallback
- source
- license
- checksum
- allowed usage scope

The build should fail if an asset lacks a manifest entry or uses a non-allowed license.

For hocrsyngen-backed inputs, hocrgen validates the provider manifest and assets but does not call the generator package. The hardened `generation_manifest.v1` boundary requires provider, rendering, and Hebrew coverage metadata to be internally consistent with the logical text before source health can pass. Niqqud and mixed-LTR absence remain reportable coverage limitations rather than release-readiness claims.

---

## 14. Deduplication subsystem

The dedupe subsystem should prevent duplication both within and across sources.

### 14.1 Required capabilities

- exact duplicate detection by hash
- deterministic near-duplicate candidate surfacing for fixture-backed CI
- source-group clustering for related source-work records
- future perceptual duplicate detection for resized/recompressed images
- future clustering of semantic near-duplicates
- lineage-aware handling of crops vs full pages

### 14.2 Preferred approach

1. exact hash pass
2. deterministic asset-metadata signature pass for conservative near-duplicate candidate surfacing
3. source-work grouping from explicit metadata or stable source URL/item keys
4. optional future perceptual hash, embedding, or OCR-text similarity for edge cases

### 14.3 Dedupe outputs

- retained canonical item
- duplicate relation table
- cluster ids
- duplicate reason code
- near-duplicate candidate cluster table
- source-group table

### 14.4 Public release rule

Do not include near-identical duplicates across splits.

---

## 15. Classification subsystem

The classification subsystem should attach operational metadata, not authoritative scholarly labels.

### 15.1 Initial classification targets

- handwritten / printed / mixed
- modern / historical
- Hebrew-only / mixed-language
- quality tier

### 15.2 Implementation options

Initial versions may use:

- metadata heuristics
- source-level priors
- lightweight image classifiers
- OCR-language heuristics

Confidence should be tracked where applicable.

### 15.3 Misclassification handling

Low-confidence or suspicious cases should route to review rather than be silently accepted.

---

## 16. Privacy and sensitivity subsystem

This subsystem is especially important for modern documents.

### 16.1 Goals

- reduce inclusion of clearly sensitive personal material
- provide consistent privacy flags
- support conservative release policies

### 16.2 Initial approach

Use a layered approach:

1. source-level restrictions
2. metadata rules
3. OCR/text heuristics where practical
4. manual review for flagged items

### 16.3 Suggested flags

- `clear`
- `possible_personal_data`
- `needs_review`
- `blocked_sensitive`

### 16.4 Policy integration

The release profile should define how these flags are handled.

Example for `profile_open_v1`:

- allow `clear`
- allow `possible_personal_data` only if source policy explicitly permits and review passes
- block `needs_review` and `blocked_sensitive`

---

## 17. Review subsystem

The review subsystem provides a controlled human-in-the-loop path.

### 17.1 Review triggers

Items should route to review if they:

- have ambiguous rights
- have privacy flags
- have low classification confidence
- are borderline duplicates
- come from review-only sources
- match manual sampling policy

### 17.2 Review artifacts

Review decisions should be stored as structured records with:

- review item id
- decision
- reviewer
- timestamp
- rationale
- optional notes

### 17.3 Decision types

- `approve`
- `reject`
- `needs_legal_review`
- `needs_privacy_review`
- `defer`

### 17.4 Integration rule

Review decisions must override automated defaults in a deterministic way.

---

## 18. Split subsystem

### 18.1 Goals

- create train / validation / test splits
- minimize leakage
- preserve dataset usefulness
- optionally create benchmark subsets

### 18.2 Leakage prevention

Split by document family or source item identifier where possible.

Avoid placing:

- pages from the same document bundle across different splits
- duplicate clusters across different splits
- deterministic near-duplicate candidate clusters across different splits
- source groups across different splits
- synthetic siblings across different splits if they are too similar

Benchmark or holdout members that share an exact duplicate cluster, near-duplicate cluster, or source group must be resolved through a typed benchmark policy before public beta/release-candidate export. Missing or stale accepted resolutions keep the risk blocked.

### 18.3 Benchmark subset

A later milestone may support a stable benchmark subset with stronger review and lower churn.

---

## 19. Packaging subsystem

### 19.1 Responsibilities

The packaging layer should build the release structure expected by Hugging Face, the mixed `HeOCR` repo, and the synthetic-only `HeOCRsynth` repo.

### 19.2 Required outputs

- item manifest
- split manifest
- sources manifest
- removals manifest
- stats report
- QA report
- changelog
- dataset card
- release metadata JSON

### 19.3 Output structure

Example logical output:

```text
release/
  heocr-open/
    v0.1.0/
      train/
        images/
      validation/
        images/
      test/
        images/
      metadata/
        items.parquet
        splits.parquet
        sources.parquet
        qa_report.json
        stats.json
      DATASET_CARD.md
      CHANGELOG.md
```

### 19.4 Diff generation

Packaging should compare against the previous release and produce:

- added items
- removed items
- changed metadata
- source-wise deltas
- split-wise deltas

### 19.5 Release compatibility contract

Each release should include a small compatibility set that lets users understand version semantics without reading the pipeline code:

- `release_record.json` for version, profile, included sources, commit, export time, and schema version
- `release_summary.json` for public payload counts and active export caps
- `item_manifest.json` for exported item metadata and release-relative asset paths
- `release_diff.json` and `CHANGELOG.md` for additions, removals, changes, and removal reasons
- benchmark and annotation manifests with explicit schema versions or schema ids

Published releases should be treated as immutable records. Corrections, takedowns, source deprecations, and schema migrations should appear in later versions with release notes rather than rewriting prior release history.

Current removal manifests may use coarse machine-readable reasons, but release notes and changelogs should provide a human-readable audit rationale for rights, privacy, takedown, and source-policy removals whenever disclosure is safe.

### 19.6 Synthetic-only HeOCRsynth handoff

`hocrgen export-synthetic` is the dedicated synthetic-only export path for `HeOCRsynth`. It runs the normal pipeline through `build-release`, then filters existing release-ready pipeline state instead of treating raw hocrsyngen batches as publishable data.

The HeOCRsynth export must:

- select only release-ready synthetic items with `PROJECT-SYNTHETIC`
- preserve synthetic disclosure, hocrsyngen provider metadata, rendering metadata, and Hebrew coverage metadata
- reject selected synthetic items missing the metadata required to distinguish generated provenance from real-source provenance
- write payload assets under `data/synthetic/<split>/<item_id>/`
- run the full configured release pipeline before filtering, so source-limited invocation is not allowed for this handoff command
- filter item, split, benchmark, benchmark reference versioning, annotation, review, blocked, duplicate, source-stat, composition, diff, and handoff artifacts to the selected synthetic scope
- emit `release_record.json` with `dataset_id: HeOCRsynth`, `release_kind: synthetic_only`, `synthetic_only: true`, and `real_items: 0`
- keep mixed `HeOCR` release behavior in `export-alpha` unchanged

The synthetic-only exporter must not call hocrsyngen internals, a hocrsyngen CLI validator/generator, REST services, network services, GPU, LLM, diffusion, or heavyweight generator dependencies.

### 19.7 Public beta readiness contract

Public beta packaging for the mixed `HeOCR` dataset must be a deliberate F5b workflow, not a side effect of `build-release`, `export-alpha`, `export-synthetic`, or `f1-beta-trial`. F5a defines the contract that `hocrgen export-public-beta` enforces.

F5b materializes the F5a contract as `manifests/public_beta_readiness_report.json`. The report includes one entry per readiness gate with `gate_id`, `status`, `evidence_paths`, and `rationale`. Valid statuses are `pass` and `blocked`; publication must stop before repository sync, upload, tagging, or publication-report emission when any gate is `blocked`.

F5c materializes the current blocker sequencing as `manifests/public_beta_blocker_closure_plan.json`. The plan is derived from the readiness report, separates blocked gates into `repo_owned_immediately_actionable` and `external_input_dependent`, names closure artifacts/actions, and preserves the `2 / 80` hocrsyngen target-scale evidence as blocked until a larger validated batch exists. The takedown/private-reporting path is represented by `src/hocrgen/config/public_beta.yaml`; a private path can pass only when it is configured with channel-specific verification metadata, and that can pass only the takedown gate without affecting source-depth, synthetic-scale, benchmark, review, or portability gates.

The readiness gate inputs are:

- source depth and composition: deterministic evidence for the candidate pool, with source-depth-only records promoted through normal release gates before public payload inclusion
- synthetic target scale and caps: a larger validated hocrsyngen `generation_manifest.v1` batch for the planned synthetic-control target, plus continued enforcement of public-profile/export cap policy
- rights and provenance: normalized public-compatible rights, raw source/provider/consent evidence, attribution, stable ids, and no unresolved rights-review state
- privacy and review: exclusion of review-required, blocked, unresolved privacy, unresolved contributor-consent, and unresolved takedown states from payload
- uniqueness and leakage: exact duplicate, near-duplicate, source-group, split, synthetic-sibling, and benchmark/holdout leakage risks are clear or resolved with typed repo-tracked accepted resolutions
- benchmark readiness: stable benchmark membership, benchmark-reference manifest/status/versioning artifacts, and explicit disclosure of reference coverage limits
- annotation expectations: full transcription and layout labels are optional for non-benchmark public beta items unless a later contract changes that; any included references must be release-relative, checksum-linked where applicable, and status-labeled
- portability: manifests, asset paths, reference paths, checksums, release records, release diffs, changelogs, archives, and handoff docs do not expose absolute local paths, `file://`, `.work/`, path traversal, or network-only assumptions
- public docs and removal readiness: dataset card, provenance, changelog, release notes, benchmark docs, handoff notes, reporting paths, and takedown/removal workflow are complete before publication

F5b archive/checksum packaging must produce:

- a release-level SHA-256 checksum manifest that covers every public payload asset, public manifest, public doc, benchmark/reference child file, and generated archive
- an archive manifest naming each generated archive, archive format, byte size, SHA-256 digest, release root, and included top-level paths
- at least one portable release archive rooted at the versioned release directory, with no absolute paths, no path traversal entries, no `.work/` state, and no generated files outside the release root
- a verification step that recomputes asset and archive digests from the handoff tree before publication
- a blocker-closure plan that derives required repo-owned and external/input-dependent actions from the current readiness report

Current known blocker: the existing F1c synthetic artifacts are operator-only and do not meet the planned public beta synthetic target scale until a larger validated hocrsyngen batch is configured and passes the same gates.

The current implementation creates local handoff artifacts only. It does not publish to `HeOCR`, Hugging Face, Kaggle, or `HeOCRsynth`, and a blocked run must not emit `manifests/publication_report.json`.

---

## 20. Publishing subsystem

### 20.1 Hugging Face publishing

The Hugging Face publisher should support:

- repo creation if needed
- authenticated upload
- versioned folder sync
- dataset card upload/update
- retryable uploads
- publication report

### 20.2 GitHub dataset repo publishing

The GitHub publisher should support:

- clone or checkout of dataset repo
- copy/sync of release metadata and approved release assets
- commit generation
- push
- release tag or release note generation if configured

### 20.3 Atomicity expectation

A release should not be marked fully published unless both:

- Hugging Face publish succeeds
- GitHub dataset repo sync succeeds

If one fails, the system should record partial status clearly.

---

## 21. CLI design

The CLI should expose both full-pipeline and stage-specific commands.

### 21.1 Top-level structure

Suggested CLI:

```text
hocrgen config validate
hocrgen discover
hocrgen fetch-metadata
hocrgen policy-filter
hocrgen acquire
hocrgen normalize
hocrgen dedupe
hocrgen classify
hocrgen privacy-scan
hocrgen review-merge
hocrgen split
hocrgen package
hocrgen publish
hocrgen build-release
hocrgen report
```

### 21.2 Full-build command

A high-level command should orchestrate the end-to-end flow:

```text
hocrgen build-release --profile profile_open_v1 --version v0.1.0
```

### 21.3 Important flags

- `--profile`
- `--version`
- `--workdir`
- `--resume`
- `--dry-run`
- `--source`
- `--max-items`
- `--since`
- `--publish`
- `--skip-stage`
- `--only-stage`

### 21.4 Dry-run behavior

Dry runs should perform discovery, filtering, manifests, and QA without publishing final outputs.

---

## 22. State management

Because GitHub Actions is ephemeral, `hocrgen` needs deliberate state handling.

### 22.1 State types

- cached raw metadata
- downloaded raw assets
- stage manifests
- dedupe indexes
- review decisions
- release history

### 22.2 Recommended persistence approach

Use file-based manifests and artifacts as the primary persistence mechanism, with optional support for external object storage later if needed.

### 22.3 Minimum durable state

At minimum, persist:

- discovery outputs
- acquisition manifests
- checksums
- review decisions
- release manifests

---

## 23. Logging and observability

### 23.1 Logging requirements

The system should emit structured logs with:

- stage
- source
- item id
- severity
- error code
- message

### 23.2 Summary reports

Every run should produce a concise machine-readable and human-readable summary including:

- sources processed
- candidates discovered
- candidates rejected by rights
- candidates rejected by quality
- review-routed items
- items published
- failures and warnings

### 23.3 Metrics worth tracking

- discovery count per source
- acceptance rate per source
- duplicate rate
- privacy flag rate
- synthetic fraction
- average quality score
- release size delta

---

## 24. GitHub Actions design

### 24.1 Main workflows

Recommended initial workflows:

- `validate_configs.yml`
- `source_discovery.yml`
- `synthetic_generate.yml`
- `build_open_release.yml`
- `build_review_release.yml`
- `publish_hf.yml`
- `publish_github_dataset.yml`

### 24.2 PR checks

On pull requests:

- validate YAML configs
- validate schemas
- test source adapters
- dry-run release profile validation
- ensure blocked sources cannot enter `profile_open_v1`

### 24.3 Scheduled workflows

On schedule:

- discover new NLI candidates
- generate synthetic candidates
- build review reports
- optionally create candidate release bundles

### 24.4 Manual approval points

Public publish should likely require explicit manual dispatch or tag-based approval, not every schedule tick.

---

## 25. Testing strategy

### 25.1 Unit tests

Test:

- config validation
- rights parsing
- source parsing
- normalization helpers
- dedupe logic
- split logic

### 25.2 Integration tests

Test:

- end-to-end dry-run builds for tiny fixtures
- publication mocks
- synthetic generation pipeline
- source adapter fixture runs

### 25.3 Regression tests

Maintain fixture-based regression tests for HTML/API parsing of key sources.

### 25.4 Contract tests

Validate output manifests against JSON schemas and expected controlled vocabularies.

---

## 26. Failure handling

### 26.1 Error philosophy

The system should prefer explicit, actionable failures over silent partial corruption.

### 26.2 Failure classes

- config error
- source fetch error
- parse error
- rights normalization error
- download error
- decode/normalize error
- dedupe error
- packaging error
- publication error

### 26.3 Tolerance strategy

- recover and continue for per-item failures where safe
- fail fast for config/policy violations
- fail release build if public-release rules are violated
- clearly record skipped items and reasons

---

## 27. Security considerations

### 27.1 Secret handling

Never commit tokens. Use environment variables and GitHub secrets.

### 27.2 Untrusted input handling

Treat remote HTML, metadata, and files as untrusted input.

### 27.3 Dependency posture

Keep dependencies minimal and pinned where appropriate, especially for image parsing and publication code.

---

## 28. Extensibility model

`hocrgen` should be designed for future extension.

### 28.1 New sources
Adding a source should primarily require:

- a new fetcher
- a source registry entry
- tests
- optional rights parser updates

### 28.2 New release profiles
Should be config-driven, not code-heavy.

### 28.3 New publishers
Should plug into the publishing interface.

### 28.4 New annotations
The item schema should be additive-friendly for future fields like:

- transcription
- line boxes
- region annotations
- OCR baseline outputs

Current annotation pilots are intentionally config-driven and additive. A pilot config may name a tiny set of release-ready or benchmark-selected items and planned release-relative target files such as `annotations/<source_id>/<source_item_id>/transcription.json`, but it must not make annotation files mandatory for current public releases. Build outputs should keep the broad `annotation_manifest.json` separate from any `annotation_pilot_manifest.json` so future label work can be scoped, audited, and exported without weakening release eligibility, benchmark stability, privacy, review, split, or portability gates.

### 28.5 Benchmark references
Benchmark ground-truth references are a benchmark-specific layer, not a general release eligibility requirement. A `benchmark_reference_manifest.v1` may link selected benchmark items to `benchmark_transcription_reference.v1` and `benchmark_layout_reference.v1` files, but current public and alpha exports must continue to work when references are missing or draft.

Runtime ingestion should validate only portable release-relative reference paths, reject absolute paths, `file://` paths, `.work` paths, backslashes, and traversal, copy selected child reference files into build/export artifacts, and check item/source/split linkage against the selected benchmark manifest. Layout references must also carry asset path, checksum, width, and height so stale labels are detected when normalized or exported assets change. Adjudication/status output should keep `not_available`, `draft`, `reviewed`, `adjudicated`, `corrected`, and `retired` states explicit, and versioning gates should use stable `reference_id` values for coherent `correction_of` / `superseded_by` relationships plus `change_reason` for corrected or retired references.

This benchmark-reference layer must not relax rights, privacy, review, dedupe, split, synthetic-cap, benchmark membership, or export-portability gates. Benchmark/holdout leakage is handled by the separate F1e policy gate, which records accepted overlap resolutions and blocks unresolved or stale risks.

---

## 29. Recommended initial milestones for implementation

### Milestone 1 — core scaffolding
- Python package and CLI
- config loading and validation
- source registry and release profiles
- base schemas
- logging and manifest helpers

### Milestone 2 — acquisition MVP
- NLI fetcher
- Pinkas importer
- BiblIA importer
- synthetic generator MVP
- rights normalization MVP

Implementation note:
- for bounded historical sources such as Pinkas and BiblIA, importer completeness does not automatically imply representative source assets
- the current packaged Pinkas/BiblIA samples use real open historical page assets, but broader source coverage and source-depth expansion remain future work

### Milestone 3 — processing and curation
- normalization
- dedupe
- basic classification
- privacy flagging
- review queue
- split assignment

### Milestone 4 — packaging and publish
- release bundle generation
- dataset card generation
- Hugging Face publishing
- GitHub dataset repo sync
- changelog diff generation

### Milestone 5 — operations hardening
- GitHub Actions workflows
- resumable runs
- richer QA reports
- regression fixtures
- review-decision integration

---

## 30. Recommended output contracts

A successful `build-release` run should produce at least:

1. release folder
2. `items.parquet`
3. `splits.parquet`
4. `sources.parquet`
5. `qa_report.json`
6. `stats.json`
7. `CHANGELOG.md`
8. `DATASET_CARD.md`
9. publication summary JSON

A failed run should still produce:

- run summary
- logs
- partial manifests where safe
- explicit failure reason

---

## 31. Success criteria

`hocrgen` is succeeding if it can reliably do the following:

- build a small public HeOCR release from approved sources
- keep review-only sources out of public releases
- preserve per-item provenance and rights metadata
- generate synthetic data reproducibly
- deduplicate and split items sensibly
- publish to Hugging Face and the `HeOCR` repo
- run the recurring maintenance workflow mostly from GitHub Actions
- produce clear manifests and changelogs for every release

---

## 32. Summary

`hocrgen` should be built as a **policy-driven dataset operations tool** for HeOCR.

Its core identity is not “scraper” and not merely “synthetic generator.” It is a system that combines:

- controlled source acquisition
- conservative rights enforcement
- synthetic augmentation
- reproducible packaging
- versioned public publishing

The central architectural principle should be:

**explicit policies + modular adapters + reproducible release builds**

The central operational principle should be:

**GitHub-first automation with auditable manifests**

The central product principle should be:

**make HeOCR useful and expandable without sacrificing provenance, legality, or maintainability**
