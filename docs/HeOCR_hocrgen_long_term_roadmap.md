# HeOCR / hocrgen Long-Term Roadmap and Milestone Plan

## 1. Purpose

This document provides a long-term planning framework for the **HeOCR** dataset and the **hocrgen** tool.

It is intended to guide:

- implementation sequencing
- public release strategy
- operational hardening
- governance
- quality expansion
- community adoption
- future annotation and benchmark work

The roadmap assumes the following product split:

- **HeOCR**: the public dataset
- **hocrgen**: the open-source toolchain that generates, curates, versions, and publishes HeOCR

The roadmap is deliberately staged. The early goal is not maximal scale. The early goal is to establish a **clean, defensible, reproducible public pipeline** that can expand safely over time.

---

## 2. Strategic objectives

Over the long term, the project should aim to achieve the following:

1. Build the best openly usable, practically valuable Hebrew document OCR/HTR dataset possible under conservative rights constraints.
2. Establish **modern handwritten Hebrew** as the core identity of the dataset.
3. Keep the dataset legally and operationally trustworthy through per-item provenance and explicit release policies.
4. Make expansion sustainable through policy-driven automation and GitHub-first operations.
5. Publish stable, versioned releases that researchers and developers can rely on.
6. Evolve from a raw document-image dataset into a richer evaluation and benchmarking resource.
7. Build enough process maturity that new sources, new policies, and new annotations can be added without destabilizing the project.

---

## 3. Guiding roadmap principles

### 3.1 Start narrow, then expand
The first public release should be intentionally modest and high-confidence.

### 3.2 Public release quality matters more than candidate-pool size
A smaller, cleaner release is strategically better than a large, ambiguous one.

### 3.3 Rights and provenance are infrastructure, not paperwork
These are core system capabilities and must mature early.

### 3.4 Synthetic data should help, not dominate
Synthetic should remain useful and bounded.

### 3.5 Tooling maturity should grow in lockstep with dataset scale
Do not scale sources or release size faster than review, QA, and publication processes.

### 3.6 Public trust is a product feature
Clear policies, changelogs, schema docs, and release behavior are part of the product.

---

## 4. Roadmap structure

This roadmap is organized into phases and milestones.

### Phases
- **Phase A**: Foundation
- **Phase B**: First public release capability
- **Phase C**: Curation and operational hardening
- **Phase D**: Expansion and benchmark formation
- **Phase E**: Ecosystem maturity

### Milestone types
Each milestone includes:
- objective
- scope
- key deliverables
- exit criteria
- risks / dependencies

### Implementation state legend
- `completed`: implemented and merged
- `partial`: implemented in part, but a planned follow-up PR is still required
- `next`: the most likely next implementation PR
- `planned`: not yet started

Roadmap notation is interpreted by repository location. A notation such as `D2a` means the work is
implemented on the current ref where the documentation is being read. On an implementation branch it
means the branch carries the work; after merge, the same current-ref wording means `main` carries the
work. Durable planning docs should therefore avoid branch-local status notes that become stale after
merge.

### State interpretation
The implementation state in the tables below tracks overall delivery status for a milestone or PR, but it does not by itself imply that the resulting content is already representative enough for public alpha use. In practice, the roadmap now distinguishes three separate ideas:

- **pipeline-complete**: the code path exists and works end to end
- **content-complete**: representative source/synthetic content exists for that path
- **release-ready**: the resulting outputs are good enough to ship in a public alpha or later release

Several milestones that are marked `partial` are code-complete enough to exercise the pipeline but still not content-complete enough to serve as credible alpha examples.

## 4.1 Milestone summary

| Milestone | Phase | Planned PRs | Concise scope | Implementation state |
| --- | --- | --- | --- | --- |
| A1 | Foundation | A1a | Repository/bootstrap and governance baseline | completed |
| A2 | Foundation | A2a | Config, schema, and manifest foundations | completed |
| A3 | Foundation | A3a | Core CLI and stage-oriented pipeline skeleton | completed |
| B1 | First public release capability | B1a, B1b | NLI acquisition MVP, then broader seed promotion and fixture capture | completed |
| B2 | First public release capability | B2a, B2b | Static open-source importers, then real historical sample replacement | completed |
| B3 | First public release capability | B3a, B3b | Synthetic MVP plumbing, then alpha-quality synthetic realism | completed |
| B4 | First public release capability | B4a | Rights normalization and release eligibility | completed |
| B5 | First public release capability | B5a, B5b1, B5b2, B5b3, B5b4 | First review-ready pilot release, then alpha-freeze unblock, content refresh, and handoff | completed |
| C1 | Curation and operational hardening | C1a | Normalization and technical QA | completed |
| C2 | Curation and operational hardening | C2a | Exact dedupe and split-safe curated build outputs | completed |
| C3 | Curation and operational hardening | C3a | Basic classification and quality scoring | completed |
| C4 | Curation and operational hardening | C4a | Privacy and sensitivity screening MVP | completed |
| C5 | Curation and operational hardening | C5a, C5b | Review queue export, then review decision merge/operational review loop | completed |
| C6 | Curation and operational hardening | C6a | Release diffs and changelog automation | completed |
| D1 | Expansion and benchmark formation | D1a | Scheduled GitHub-first dry-run maintenance and reporting workflows | completed |
| D2 | Expansion and benchmark formation | D2a | Stable source-operations maturity | completed |
| D3 | Expansion and benchmark formation | D3a | Benchmark subset v1 | completed |
| D4 | Expansion and benchmark formation | D4a, D4b | Richer synthetic generation, then synthetic diversity/reporting hardening | completed |
| D5 | Expansion and benchmark formation | D5a | Optional transcription-ready architecture | completed |
| E1 | Ecosystem maturity | E1a | Community contribution model | completed |
| E2 | Ecosystem maturity | E2a, E2b | Baselines/evaluation utilities, then live/cached NLI seed acquisition | completed |
| E3 | Ecosystem maturity | E3a | Annotation subset pilots | completed |
| E4 | Ecosystem maturity | E4a | Multi-release governance maturity | completed |

## 4.2 PR summary

| PR | Milestone | Concise scope | Blocking for alpha? | Implementation state | Reference |
| --- | --- | --- | --- | --- | --- |
| A1a | A1 | Initial repository, governance, and architecture bootstrap | no | completed | historical / bootstrap work |
| A2a | A2 | Typed config, schemas, manifests, validation foundations | no | completed | merged as PR #1 |
| A3a | A3 | CLI, run context, stage skeleton, logging, workdir structure | no | completed | merged as PR #1 |
| B1a | B1 | Seed-driven NLI acquisition MVP | yes | completed | merged as PR #2 |
| B1b | B1 | NLI exploratory-seed promotion and CDP-assisted fixture capture | yes | completed | merged as PR #8 |
| B2a | B2 | Pinkas/BiblIA importer scaffolding over packaged sample records | yes | completed | merged as PR #2 |
| B2b | B2 | Replace scaffold-grade Pinkas/BiblIA assets with real packaged/open historical sample pages | yes | completed | historical-source sample realism work |
| B3a | B3 | Deterministic synthetic MVP with tracked inputs and metadata | yes | completed | merged as PR #2 |
| B3b | B3 | Synthetic alpha-quality upgrade: real fonts, curated text, raster output, degradation, better layouts | yes | completed | merged as PR #14 |
| B4a | B4 | Rights normalization and release eligibility engine | yes | completed | merged as PR #2 |
| B5a | B5 | Review-ready build and alpha export packaging in `hocrgen` | yes | completed | merged as PR #10 |
| B5b1 | B5 | Alpha export portability cleanup for public manifests and audit artifacts | yes | completed | pre-alpha freeze PR 1 |
| B5b2 | B5 | Real-scan exemplar refresh: higher-resolution NLI export and text-bearing historical sample replacement | yes | completed | pre-alpha freeze PR 2 |
| B5b3 | B5 | Synthetic alpha unblock: Hebrew ordering fix, `2x real` synthetic cap, and low-risk realism polish | yes | completed | pre-alpha freeze PR 3 |
| B5b4 | B5 | Final alpha freeze validation and handoff into the separate `HeOCR` repo | yes | completed | pre-alpha freeze PR 4 |
| C1a | C1 | Normalization, metadata extraction, checksums, previews, QA | yes | completed | merged as PR #3 |
| C2a | C2 | Exact dedupe, deterministic split assignment, curated build outputs | yes | completed | merged as PR #5 |
| C3a | C3 | Heuristic classification | yes | completed | merged as PR #6 |
| C4a | C4 | Metadata-first privacy scanning | yes | completed | merged as PR #6 |
| C5a | C5 | Review queue export and review-side artifacts | yes | completed | merged as PR #6 |
| C5b | C5 | Review decision schema merge, operational review loop, and post-review release gating | no | completed | merged as PR #22 |
| C6a | C6 | Release diffs and changelog generation | no | completed | merged as PR #23 |
| D1a | D1 | Scheduled GitHub-first dry-run maintenance and reporting workflows | no | completed | merged as PR #27 |
| D2a | D2 | Source refresh/reliability maturity and source freeze controls | no | completed | merged as PR #28; current ref source-health path follow-up |
| D3a | D3 | Benchmark subset v1 and benchmark-facing manifests | no | completed | merged as PR #30 and PR #41 |
| D4a | D4 | Richer synthetic generation for realism and document likeness | no | completed | merged as PR #32 |
| D4b | D4 | Synthetic diversity controls and reporting hardening | no | completed | merged as PR #33 |
| D5a | D5 | Optional transcription-ready architecture foundations | no | completed | merged as PR #34 |
| E1a | E1 | Community contribution model and contribution safety rails | no | completed | merged as PR #35 |
| E2a | E2 | Baselines and evaluation utilities | no | completed | merged as PR #36 |
| E2b | E2 | Live-but-cached batch acquisition for vetted NLI seed URLs | no | completed | merged as PR #38 |
| E3a | E3 | Annotation subset pilots | no | completed | merged as PR #39 |
| E4a | E4 | Multi-release governance and maturity controls | no | completed | current ref governance PR |

## 4.3 Current critical path

The immediate implementation critical path after `E4a` is:

1. Land the queued `D2a` source-operations follow-up from issue #29 by making source-health check paths portable in operator artifacts where stable package or config-root references are available.

This prioritization is intentional. `B5a` made the alpha mechanically exportable, `B5b1` through `B5b3` closed the portability and content-quality blockers, and `B5b4` froze `alpha-v0` into the separate `HeOCR` repository with a ready-for-review handoff PR. `C5b` then closed the missing review-decision merge path by adding repo-tracked review inputs, a dedicated `review-merge` stage, deterministic post-review gating, and auditable decision artifacts. `C6a` made exported release trees explainable over time through baseline-aware diffs and changelog generation. `D1a` moved routine dry-run maintenance into GitHub Actions with persisted run summaries. `D2a` adds source health, fixture-backed adapter regression coverage, freeze/degrade reporting, and portable source-health check paths where package or config-root references are available so source instability is visible without tying operator artifacts to local install paths unnecessarily. `D3a` defines the first explicitly approved `benchmark_v1` subset with benchmark manifests, selection audit, a stability policy, and usage guidance; the current ref also packages the benchmark approval config so non-editable installs do not depend on a checkout-root `benchmark_data/` directory. `D4a` upgrades the synthetic generator's visual realism without new external assets by adding recipe-backed printed and handwritten-look rendering, richer document-like marks, deterministic degradation presets, and public metadata. `D4b` adds synthetic controls over that metadata and reports synthetic composition in build and alpha export outputs. `D5a` adds optional, portable annotation-reference slots and annotation manifests so future transcription work can attach to release items without making transcriptions mandatory for current alpha/public outputs. `E1a` defines source proposal, source-adapter, synthetic asset, dataset issue, external review, and release-governance contribution paths while preserving existing rights, privacy, review, and release gates. `E2a` adds benchmark example loading, JSON/JSONL text prediction evaluation, character error rate and exact-match helpers, coverage reporting, and lightweight leaderboard-ready conventions over the existing `benchmark_v1` artifacts without adding model training infrastructure.

`E2b` is a deliberately narrow bridge between the current fixture-backed NLI seed flow and release-size real-source growth. It does not add broad site crawling. The operator path accepts vetted NLI seed URLs from the exploratory catalog, runnable seed manifest, or both; reuses local fixture-backed seeds without network access; fetches/parses missing item metadata and assets when explicitly run; writes reusable local fixtures/assets; and emits a machine-readable report with promoted, skipped, and failed seeds. CI and routine release validation continue to run against committed or locally cached fixtures rather than live network access. A release target such as `80` real samples plus `80` governed synthetic controls should wait until this batch path has produced enough release-ready real items and all rights, privacy, review, split-leakage, benchmark-stability, synthetic-cap, and export-portability gates still pass.

`E3a` adds a deliberately small annotation pilot path on top of the D5a annotation slots. The pilot config names two real `benchmark_v1` items, validates that they remain release-ready and benchmark-selected, emits `annotation_pilot_manifest.json` plus a selection audit during `build-release`, and mirrors the exported subset during `export-alpha`. Pilot entries carry release-relative planned target paths for transcription and layout-label JSON, but they do not assert that labels already exist and do not make annotations mandatory for current public or alpha payloads.

`E4a` documents the multi-release governance contract around immutable published release versions, release compatibility anchors, additive schema migration, rights/privacy takedown handling, source deprecation, and benchmark stability. It deliberately does not change current public or alpha inclusion behavior; the existing rights, privacy, review, benchmark, split-leakage, synthetic-cap, and export-portability gates remain the enforcement boundary.

## 4.4 Alpha release readiness gates

An alpha release should not be treated as ready merely because the pipeline can export it. At minimum, the following gates should be met:

- the public export contains only release-ready items and excludes review-required/blocked items from the dataset payload
- exported public artifacts do not leak absolute local filesystem paths or depend on `.work/`-relative runtime state
- representative real samples are text-bearing and OCR-relevant, not bindings/covers or scaffold-grade placeholder fixtures
- NLI-derived public samples are exported at a materially credible resolution for OCR use
- synthetic public samples preserve correct Hebrew character ordering and remain within the configured `2x real items` alpha cap
- synthetic samples use governed fonts, curated text, plausible layouts, raster output, and at least a basic scan/degradation pass
- the exported release tree has been validated locally and inspected in the target `HeOCR` repository layout
- release summary, provenance, and dataset-card documents accurately describe source coverage and known limitations

## 4.5 Merged PR traceability

The table below is a compact mapping from roadmap PR notation to already merged implementation PRs.
Some completed bootstrap work predates PR-based tracking. In particular, `A1a` is intentionally recorded as completed in the PR summary but omitted here because it was not tracked as a merged GitHub PR.

| PR notation | Merged GitHub PR |
| --- | --- |
| A2a | #1 |
| A3a | #1 |
| B1a | #2 |
| B2a | #2 |
| B3a | #2 |
| B4a | #2 |
| C1a | #3 |
| C2a | #5 |
| C3a | #6 |
| C4a | #6 |
| C5a | #6 |
| B1b | #8 |
| B5a | #10 |
| B3b | #14 |
| C5b | #22 |
| C6a | #23 |
| D1a | #27 |
| D2a | #28 |
| D3a | #30, #41 |
| D4a | #32 |
| D4b | #33 |
| D5a | #34 |

## 4.6 Planned PR documentation rule

When a PR is opened to implement a roadmap-tracked milestone or sub-PR, the implementation ref should update the planning/state documents together with the code. The default expectation is:

- update [`.agent-plan.md`](../.agent-plan.md) with the current execution state and next immediate tasks
- update [`README.md`](../README.md) when user-visible capabilities, workflow guidance, or operator expectations changed
- update the relevant planning doc under [`docs/`](./) when milestone state, PR state, critical path, or release-readiness guidance changed
- use the roadmap or plan notation in the PR title as `<notation>: <sentence-case summary>`
- include a top-level `## Planning notation` section in the PR body that names the notation, parent milestone, and plan source

This is a workflow rule, not optional polish. The point is to keep static capabilities, immediate execution state, and human-facing roadmap documents synchronized with the implementation PR that changed them. In practice, a planned PR is not complete until its code changes and its plan/documentation updates land together on the implementation ref, with the notation reflected consistently in the PR metadata. Current-ref wording is preferred because it remains correct after merge.

For status reconciliation, treat merged `main` and merged GitHub PR history as authoritative over branch-local execution notes. If a roadmap table, `.agent-plan.md`, or another planning surface disagrees with merged `main`, update the planning docs before treating the notation as still open.

---

# Phase A — Foundation

## Milestone A1 — Project scaffolding and governance baseline

### Objective
Create the structural foundation for both repositories and define the project’s basic operating model.

### Scope
- initialize `hocrgen`
- initialize `HeOCR`
- define project mission and scope
- define contribution and governance basics
- define initial repository conventions

### Deliverables
- `hocrgen` repository created
- `HeOCR` repository created
- top-level READMEs
- initial architecture document
- initial dataset design/spec
- initial acquisition plan
- contribution guidelines
- issue templates
- pull request template
- basic coding/tooling setup

### Exit criteria
- both repos exist and are publicly structured
- project documentation explains the split between tool and dataset
- there is a clear stated policy that public releases will be conservative and policy-driven

### Risks / dependencies
- over-scoping governance too early
- under-documenting release boundaries

---

## Milestone A2 — Configuration and schema foundations

### Objective
Define the typed and serialized foundations required for deterministic dataset operations.

### Scope
- source registry schema
- release profile schema
- item schema
- review decision schema
- release manifest schema
- config loading/validation

### Deliverables
- `sources.yaml`
- `licenses.yaml`
- release profile YAML(s)
- JSON schema files
- Python models for config and manifests
- config validation CLI command

### Exit criteria
- invalid source or release configs fail fast
- schemas are documented and versioned
- a dry-run config validation step works in CI

### Risks / dependencies
- schema churn from premature design detail
- underspecified rights metadata fields

---

## Milestone A3 — Core CLI and pipeline skeleton

### Objective
Create the base `hocrgen` CLI and stage-oriented execution model.

### Scope
- CLI entrypoint
- stage commands
- run context model
- workdir layout
- manifest/logging conventions

### Deliverables
- `hocrgen config validate`
- `hocrgen discover`
- `hocrgen fetch-metadata`
- `hocrgen policy-filter`
- `hocrgen acquire`
- `hocrgen build-release`
- structured logging
- run summary output

### Exit criteria
- stage commands execute end-to-end on fixtures
- each stage emits expected manifests/logs
- CLI contract is documented

### Risks / dependencies
- too much orchestration complexity too early
- fragile coupling between pipeline stages

---

# Phase B — First public release capability

## Milestone B1 — NLI acquisition MVP

### Objective
Implement the first real acquisition adapter for the main real-scan source.

### Scope
- NLI discovery logic
- item-page parsing
- rights parsing for `Any Use Permitted`
- image link extraction
- acquisition metadata capture

### Deliverables
- `nli` fetcher
- source parser fixtures
- normalized NLI metadata mapping
- initial NLI candidate manifest generation

### Exit criteria
- `hocrgen` can discover and parse NLI candidates
- `Any Use Permitted` items are reliably recognized
- parse failures are logged and test-covered

### Risks / dependencies
- NLI HTML/API changes
- overly loose rights matching

---

## Milestone B2 — Static open-source importers

### Objective
Support bounded historical sources with clear upstream open licenses.

### Scope
- Pinkas importer
- BiblIA importer
- provenance mapping
- license normalization for imported datasets

### Deliverables
- `pinkas` importer
- `biblia` importer
- source manifests for imported datasets
- import tests

### Current-state clarification
Importer readiness and sample realism are separate concerns.

Pinkas and BiblIA are now implemented as bounded static importers over packaged sample records backed by real open historical page assets. They are still intentionally small and bounded sample sources, but the committed packaged assets are no longer scaffold-grade mock fixtures.

### Current bounded-source requirement
Pinkas and BiblIA should remain conservative bounded-source imports. In practical terms, that means:

- keep the importer and provenance model unchanged
- use packaged real open sample page assets rather than mock SVG stand-ins
- preserve upstream identifiers and license metadata
- keep source scope explicitly bounded even when the sample assets are visually representative

### Exit criteria
- imported records preserve upstream provenance
- licenses normalize correctly
- imported data appears as distinct source families in manifests
- importer readiness is documented separately from source-sample realism

### Risks / dependencies
- mixed upstream packaging details
- accidental over-ingestion beyond explicitly packaged open files

---

## Milestone B3 — Synthetic generation MVP

### Objective
Add a first useful synthetic generation capability to HeOCR.

### Scope
- synthetic recipe model
- font manifest
- project-owned text sources
- simple layouts
- scan degradation basics
- synthetic metadata emission

### Deliverables
- synthetic generator module
- 2–4 initial layout families
- printed Hebrew pages
- handwritten-look Hebrew pages
- mixed Hebrew+English examples
- synthetic asset manifest validation

### Concrete near-term quality requirements
The current SVG-first generator is acceptable as an infrastructure milestone, but it is not sufficient as an alpha-quality sample source. Before synthetic items are treated as credible public-release content, the implementation plan should explicitly address the following:

- replace host CSS fallback stacks with tracked, project-approved font assets
- ensure the handwritten path uses genuinely handwriting-like Hebrew fonts rather than print-like fallbacks
- replace placeholder or instruction-like text with curated Hebrew document-style lines
- remove visibly decorative framing that does not resemble real source material
- move synthetic export from vector-first SVG output toward raster output suitable for OCR/scanned-document evaluation
- add a lightweight degradation pass so synthetic pages no longer look digitally pristine
- keep mixed Hebrew+English support, but make it document-like and sparing rather than template-explanatory

### Alpha release constraint
Synthetic items may appear in alpha exports only under strict caps, but they should not be considered visually acceptable alpha content until the following are true:

- text content is corpus-driven and document-like rather than prompt-like or self-referential
- handwritten samples use approved handwriting-like fonts
- layouts resemble plausible Hebrew archival or administrative documents
- output is rasterized and passes a basic scan-realism bar

### Exit criteria
- synthetic items can be generated reproducibly from a seed
- all assets used are tracked
- synthetic items include required metadata
- public release caps can be enforced

### Risks / dependencies
- asset-license drift
- unrealistic or low-utility synthetic outputs

---

## Milestone B4 — Rights normalization and release eligibility engine

### Objective
Make policy enforcement real rather than aspirational.

### Scope
- raw rights capture
- normalized license mapping
- rights classification mapping
- release profile enforcement
- hard-fail rules for public release

### Deliverables
- rights parsing module
- normalized license taxonomy
- release eligibility checks
- blocked/review-only item handling
- public-release validator

### Exit criteria
- public-release profile fails if unknown or restricted items appear
- rights metadata is present in manifests
- source policy rules are deterministic and test-covered

### Risks / dependencies
- rights edge cases becoming silent includes
- overcomplicated policy logic before it is needed

---

## Milestone B5 — First end-to-end pilot release

### Objective
Produce the first small public HeOCR release.

### Scope
- acquire bounded NLI subset
- import Pinkas
- import BiblIA open package subset
- generate synthetic pages
- package train/validation/test
- publish a pilot release
- freeze a small alpha subset only after exemplar quality and export portability checks pass

### Deliverables
- `HeOCR v0.1.0`
- release manifests
- dataset card
- changelog
- QA summary
- first Hugging Face publication
- first GitHub dataset repo release sync

### Exit criteria
- a public release exists and is reproducible/auditable
- the release contains only allowed/open items
- the release metadata is coherent
- alpha exemplars are text-bearing, portable, and not obviously broken to a first-time OCR user
- publication to both targets succeeds

### Risks / dependencies
- first-release packaging complexity
- mismatch between Hugging Face and GitHub output structures

---

# Phase C — Curation and operational hardening

## Milestone C1 — Normalization and technical QA

### Objective
Standardize file handling and establish baseline technical quality controls.

### Scope
- image normalization
- thumbnail generation
- checksum computation
- dimension capture
- decodability checks
- minimum quality thresholds

### Deliverables
- normalization module
- technical QA report
- failed-asset handling
- consistent normalized output structure

### Exit criteria
- corrupt/invalid assets are rejected cleanly
- normalized files have stable layout and metadata
- technical QA is part of release builds

### Risks / dependencies
- over-normalization losing fidelity
- source-specific format edge cases

---

## Milestone C2 — Deduplication pipeline

### Objective
Prevent the dataset from bloating or leaking duplicates across releases and splits.

### Scope
- exact duplicate detection
- perceptual hash duplicate detection
- duplicate clustering
- canonical-retention policy

### Deliverables
- exact hash pass
- pHash pass
- dedupe relation table
- duplicate cluster manifest
- release-time duplicate checks

### Exit criteria
- exact duplicates do not survive release packaging
- near-duplicates are at least surfaced and handled deterministically
- duplicate clusters do not leak across splits

### Risks / dependencies
- false positives on visually similar handwriting
- weak duplicate handling across sources

---

## Milestone C3 — Basic classification and quality scoring

### Objective
Add operational labels needed for filtering, balancing, and future analysis.

### Scope
- handwritten/printed/mixed classification
- modern/historical classification
- Hebrew-only/mixed-language classification
- heuristic quality score

### Deliverables
- classification modules
- confidence fields
- release composition stats by class
- low-confidence routing hooks

### Exit criteria
- all release items have classification labels
- composition reports can be generated automatically
- suspicious/low-confidence items can route to review

### Risks / dependencies
- noisy automatic classification
- classification logic drifting into pseudo-ground-truth claims

---

## Milestone C4 — Privacy and sensitivity screening MVP

### Objective
Reduce the chance of publishing inappropriate modern documents.

### Scope
- source-level privacy rules
- metadata-based risk rules
- optional OCR/text heuristics
- review triggers

### Deliverables
- privacy rules config
- privacy flag values
- review queue generation for flagged items
- public-release blocking rules

### Exit criteria
- flagged items are excluded or reviewed under public profiles
- privacy signals are recorded in metadata
- the public release can demonstrate a conservative privacy posture

### Risks / dependencies
- false negatives on sensitive material
- overblocking useful but harmless items

---

## Milestone C5 — Manual review system

### Objective
Create a controlled human-in-the-loop path for borderline cases.

### Scope
- review queue artifact generation
- structured decision files
- allowlists/blocklists
- decision merge into pipeline

### Deliverables
- review queue format
- review decision schema
- CLI commands for review export/merge
- support for manual overrides

### Exit criteria
- review decisions deterministically affect release outcomes
- reviewers can approve/reject items without ad hoc editing
- review state is versioned and auditable

### Risks / dependencies
- review UX being too cumbersome
- human decisions not being captured in stable structured form

---

## Milestone C6 — Release diffs and changelog automation

### Objective
Make every new dataset release explainable.

### Scope
- compare with prior release
- added/removed/changed item reporting
- source-wise delta reporting
- release notes automation

### Deliverables
- release diff engine
- changelog generator
- per-source addition/removal stats
- removal-reason support

### Exit criteria
- every release includes a machine-readable diff and human-readable changelog
- removals are documented explicitly
- release history becomes inspectable over time

### Risks / dependencies
- unstable item IDs
- poor handling of metadata-only changes vs asset changes

---

# Phase D — Expansion and benchmark formation

## Milestone D1 — Scheduled GitHub-first expansion workflows

### Objective
Move from one-off releases to sustainable scheduled maintenance.

### Scope
- scheduled review-profile candidate discovery through policy filtering
- scheduled synthetic-only dry-run builds
- scheduled review/open dry-run builds
- artifact handoff between workflows through persisted run directories
- machine-readable and Markdown run summaries for GitHub Actions operators
- keep publication gated and manual for now

### Deliverables
- GitHub Actions workflows for recurring dry-run/reporting runs
- resumable artifact-based flow
- scheduled reports in uploaded artifacts and Actions job summaries
- CLI support for resuming runs and summarizing persisted run directories

### Exit criteria
- most routine maintenance runs can occur on GitHub Actions
- dry-run builds happen without local intervention
- publication remains gated and deliberate outside `D1a`

### Risks / dependencies
- GitHub storage/runtime limits
- brittle workflow coupling

---

## Milestone D2 — Stable source-operations maturity

### Objective
Make supported sources operationally reliable.

### Scope
- parser regression fixtures
- source-health checks
- source-specific error dashboards/reports
- configurable retry/backoff logic

### Deliverables
- fixture suite for each adapter
- source health status report
- source health warnings in run summaries
- source freeze/degrade modes
- portable operator-facing path references for packaged and config-root source-health checks
- planning consistency guard for current-state docs

### Exit criteria
- adapter breakages are detected quickly
- source instability does not silently corrupt releases
- source-specific operational behavior is documented
- roadmap and planning surfaces agree on completed and next notation

### Risks / dependencies
- upstream source churn
- overengineering observability before enough sources exist

---

## Milestone D3 — Benchmark subset v1

### Objective
Create a smaller, more stable, more review-intensive subset suitable for consistent evaluation.

### Scope
- benchmark selection policy
- stronger review requirements
- lower-duplication tolerance
- stable split commitment

### Deliverables
- `benchmark v1`
- benchmark selection manifest
- benchmark card / usage guidance
- benchmark stability policy
- packaged benchmark approval config for non-editable installs

### Exit criteria
- a clearly defined evaluation subset exists
- benchmark churn is low across subsequent releases
- users can evaluate on HeOCR without depending on the entire changing corpus

### Risks / dependencies
- selecting benchmark content too early
- benchmark not matching the dataset’s core identity

---

## Milestone D4 — Richer synthetic generation

### Objective
Make the synthetic component more useful and document-like.

### Scope
- more document templates
- forms and marginalia
- mixed printed/handwritten overlays
- stamps/signatures/annotations
- harder degradation families
- bilingual fragments
- true handwritten-like Hebrew rendering families rather than only print-like approximations
- stronger post-generation distortion and artifact stacks beyond the alpha-minimum release pass

### Deliverables
- expanded recipe library
- richer asset manifests
- improved realism controls
- synthetic diversity reports (`D4b`)
- raster output mode suitable for release packaging
- curated handwriting-like and print-like Hebrew font sets with explicit governance
- document-style Hebrew corpora with no prompt/instruction leakage
- scan-like degradation presets for blur, noise, contrast loss, skew, and compression artifacts
- layout families that model plausible placement of headers, bodies, footers, notes, and identifiers
- handwritten-like generation families that read as handwritten rather than merely typed with a governed font
- heavier post-processing presets that can emulate more severe scanning, copying, and print-process defects

### Current-state clarification
`D4a` implements the visual realism pass while avoiding new external synthetic assets. The generator keeps the existing `printed_letter` and `handwritten_note` template IDs, backs them with stable recipe/degradation metadata and richer deterministic rendering, and emits both default recipes into the conservative public profile. `D4b` is implemented on the current ref by adding synthetic subset controls for template, recipe, and degradation preset metadata, plus synthetic composition reports in build-release and alpha export surfaces.

### Exit criteria
- synthetic data covers more realistic Hebrew document patterns
- users can selectively filter synthetic subsets by type
- synthetic still remains within configured release caps
- synthetic examples no longer look like clean SVG mockups or generic template cards
- handwritten-like synthetic pages are visually distinct from clean print-like pages
- mixed-language fragments appear as realistic identifiers or annotations rather than template instructions

### Risks / dependencies
- realism drift without measurement
- synthetic overpowering real-data identity

---

## Milestone D5 — Optional transcription-ready architecture

### Objective
Prepare the system for annotated subsets without making annotation a prerequisite for progress.

### Scope
- transcription field conventions
- annotation file paths/schema
- subset-level annotation support
- import hooks for external labels

### Deliverables
- additive annotation schema
- manifest support for transcriptions/layout labels
- doc describing annotation-ready subset structure

### Exit criteria
- a future annotated subset can be added without breaking the core dataset
- annotation storage and publication patterns are defined

### Current-state clarification
`D5a` is implemented on the current ref as an architecture foundation, not a broad annotation workflow. Item manifests carry optional `annotation_status`, `transcription`, and `layout_labels` fields, while `build-release` and `export-alpha` emit `annotation_manifest.json` with portable release-relative reference slots. Current alpha and public profile outputs keep transcriptions optional and do not require external annotation assets.

### Risks / dependencies
- scope creep into full annotation pipeline prematurely

---

# Phase E — Ecosystem maturity

## Milestone E1 — Community contribution model

### Objective
Enable outside contributors to safely help expand or improve the project.

### Scope
- contribution docs for sources
- source proposal workflow
- review policy for external changes
- synthetic asset contribution rules
- dataset issue taxonomy

### Deliverables
- `CONTRIBUTING.md` for code and data policy
- source-adapter contribution guide
- synthetic asset contribution guide
- release governance notes

### Exit criteria
- a contributor can understand how to propose a new source or improvement
- external contributions are constrained by policy and schema validation
- contribution pathways do not bypass rights or privacy safeguards

### Current-state clarification
`E1a` is implemented on the current ref as policy and documentation rails, not as a new ingestion workflow. The contribution model now lives in [`CONTRIBUTING.md`](../CONTRIBUTING.md), [`docs/source_adapter_contribution_guide.md`](./source_adapter_contribution_guide.md), [`docs/synthetic_asset_contribution_guide.md`](./synthetic_asset_contribution_guide.md), and [`docs/release_governance.md`](./release_governance.md). It defines source proposal requirements, review expectations for external changes, synthetic asset licensing/provenance rules, a dataset issue taxonomy, source-adapter acceptance criteria, and release governance notes while leaving typed config validation, rights classification, privacy review, review merge, release eligibility, benchmark stability, and export portability as mandatory gates.

### Risks / dependencies
- community contributions increasing rights ambiguity
- underdocumented acceptance criteria

---

## Milestone E2 — Baselines and evaluation utilities

`E2a` is implemented on the current ref as lightweight utility foundations over the existing `benchmark_v1` artifacts. The implementation adds benchmark example loading from benchmark, item, and annotation manifests; JSON/JSONL prediction/reference loading keyed by `item_id`; deterministic edit-distance, character error rate, exact-match, coverage, and per-item metric reporting; a CLI `hocrgen evaluate-benchmark`; README examples; and a small leaderboard-ready convention block for downstream reports. It deliberately avoids training infrastructure, network-dependent tests, or weakening benchmark stability, release eligibility, review, privacy, rights, source-quality, split-leakage, and export-portability gates.

### Objective
Make HeOCR easier to use in practice.

### Scope
- example loading code
- baseline OCR/HTR evaluation scripts
- metric helpers
- benchmark evaluation examples

### Deliverables
- example notebooks/scripts
- benchmark usage examples
- evaluation utilities
- optional lightweight leaderboard-ready conventions

### Exit criteria
- users can quickly run baselines on HeOCR
- benchmark subset has documented evaluation pathways
- the project becomes more than a data dump

### Risks / dependencies
- baseline maintenance burden
- distracting from dataset core work

---

## Milestone E3 — Annotation subset pilots

### Objective
Introduce carefully bounded annotated subsets.

### Scope
- manually transcribed subset pilot
- line or region annotation pilot
- release and schema extension for annotations

### Deliverables
- one or more annotated micro-subsets
- annotation guidelines
- provenance link between images and labels

### Exit criteria
- an annotated subset exists without destabilizing the core dataset
- annotation format is documented and versioned
- labels can be consumed by users cleanly

### Current-state clarification
`E3a` is implemented on the current ref as a carefully bounded pilot-selection path, not a full annotation-production workflow. The repo-tracked pilot config selects two real `benchmark_v1` items, requires release-ready and benchmark membership before inclusion, emits a typed pilot manifest and audit, and keeps all planned annotation target paths release-relative. Current alpha and public outputs still do not require transcriptions or layout labels.

### Risks / dependencies
- annotation quality bottlenecks
- annotation tooling burden

---

## Milestone E4 — Multi-release governance maturity

### Objective
Handle growth in dataset history, removal events, and source-policy evolution gracefully.

### Scope
- stronger version governance
- removal/takedown workflow
- schema migration policy
- source deprecation policy
- benchmark stability guarantees

### Deliverables
- governance docs for versioning/removals
- deprecation rules
- schema evolution guidance
- release compatibility statements

### Current-ref implementation
`E4a` is implemented on the current ref as a governance maturity pass. The policy now defines release version semantics, compatibility anchors, removal/takedown handling, additive schema migration rules, source deprecation states, benchmark stability guarantees, and PR/release documentation expectations. Current alpha/public payload selection is unchanged.

### Exit criteria
- the project can evolve without chaotic breaking changes
- removals and corrections are part of the normal process
- users can understand compatibility and release semantics

### Risks / dependencies
- historical burden as versions accumulate
- governance becoming too heavy for project size

---

# Cross-cutting workstreams

## Workstream 1 — Documentation
This must continue across all phases.

### Ongoing outputs
- architecture docs
- schema docs
- source policy docs
- release profile docs
- privacy docs
- licensing docs
- changelogs
- benchmark docs

### Success condition
A technically strong outsider can understand what the system does and why items are or are not in the public release.

---

## Workstream 2 — Testing and reliability
This must grow with system complexity.

### Ongoing outputs
- parser fixtures
- schema validation tests
- pipeline integration tests
- regression tests
- publishing mocks
- CI dry-run builds

### Success condition
A source breakage or config mistake is caught before a public release is corrupted.

---

## Workstream 3 — Rights and policy maintenance
This is permanent.

### Ongoing outputs
- source registry updates
- license normalization updates
- review-only source support
- removal/takedown handling
- release-profile validation

### Success condition
The public release remains defensible as sources and project scope evolve.

---

## Workstream 4 — Dataset composition monitoring
The dataset should be intentionally shaped, not just accumulated.

### Ongoing outputs
- modern vs historical stats
- handwritten vs printed stats
- synthetic fraction stats
- source concentration stats
- quality distribution stats

### Success condition
The dataset continues to match its intended identity: mainly modern handwritten Hebrew, with bounded complements.

---

# Suggested version-aligned milestone map

## Version line 0.x — Prove the core concept
Focus:
- build the pipeline
- ship a first public release
- validate policy architecture
- prove publishability

Likely milestones:
- A1, A2, A3
- B1, B2, B3, B4, B5

Outcome:
- `HeOCR v0.1.x`
- `hocrgen v0.1.x`

---

## Version line 0.2–0.4 — Make the system trustworthy
Focus:
- normalization
- dedupe
- classification
- privacy review
- release diffs
- operational QA

Likely milestones:
- C1, C2, C3, C4, C5, C6

Outcome:
- public releases become cleaner, more auditable, and safer

---

## Version line 0.5–0.9 — Make the system sustainable
Focus:
- scheduled GitHub-first operations
- source reliability
- review process hardening
- richer synthetic coverage

Likely milestones:
- D1, D2, D4
- partial D5

Outcome:
- recurring releases become routine rather than bespoke

---

## Version line 1.0 — Stable public dataset and benchmark posture
Focus:
- benchmark subset
- stable schemas
- strong documentation
- reproducible release discipline

Likely milestones:
- D3
- finalization of D5 foundations
- parts of E1 and E4

Outcome:
- `HeOCR v1.0`
- public confidence in release discipline and benchmark usage

---

## Version line 1.x — Ecosystem and research utility
Focus:
- community adoption
- baselines
- annotated subsets
- mature governance

Likely milestones:
- E1, E2, E3, E4

Outcome:
- the project becomes a durable ecosystem asset rather than only an internal pipeline

---

# Recommended implementation order

If implementation resources are limited, the order should be:

1. A1 — scaffolding and governance baseline
2. A2 — schemas and config validation
3. A3 — CLI/pipeline skeleton
4. B1 — NLI acquisition MVP
5. B3 — synthetic generation MVP
6. B4 — rights normalization and release eligibility
7. B2 — open-source importers
8. B5 — first pilot release
9. C1 — normalization and technical QA
10. C2 — dedupe
11. C4 — privacy and sensitivity screening
12. C5 — manual review system
13. C6 — release diffs/changelog
14. C3 — classification/quality scoring
15. D1 — scheduled GitHub-first workflows
16. D2 — source operational maturity
17. D3 — benchmark subset v1
18. D4 — richer synthetic generation
19. D5 — annotation-ready architecture
20. E1 / E2 / E3 / E4 — ecosystem maturity work

This order emphasizes public-release safety before scale and polish before aggressive expansion.

---

# Milestone dependency notes

## Hard dependencies
- B5 depends on B1, B2, B3, B4
- C5 depends on A2 and partial C4
- D1 depends on a stable enough B5/C1-C2 foundation
- D3 depends on C2, C3, C4, C5, C6
- E3 depends on D5

## Soft dependencies
- C3 can start before C5, but review hooks become more valuable once C5 exists
- D4 can progress in parallel with D1/D2 once synthetic asset governance is stable
- E2 can begin once D3 exists, even before E1 is fully mature

---

# Risks across the roadmap

## Risk 1 — Rights complexity grows faster than tooling maturity
### Mitigation
Keep the public release narrow and formalize review-only profiles early.

## Risk 2 — GitHub Actions becomes a bottleneck
### Mitigation
Keep pipelines incremental and artifact-driven; use local/manual fallback for exceptional rebuilds.

## Risk 3 — Dataset identity drifts
### Mitigation
Track composition stats and enforce release-level caps/targets.

## Risk 4 — Too much manual review load
### Mitigation
Bias toward strong source policies and targeted review, not broad manual curation.

## Risk 5 — Source fragility
### Mitigation
Use modular adapters, parser fixtures, and source-health reporting.

## Risk 6 — Synthetic data becomes easier than real acquisition and starts dominating
### Mitigation
Enforce synthetic fraction caps and real-data minimum targets in public releases.

---

# Recommended success criteria by phase

## End of Phase A
- the project is structurally coherent
- schemas and configs exist
- CLI scaffolding works

## End of Phase B
- a public pilot release exists
- rights gating and publication work
- synthetic and real data coexist in one release pipeline

## End of Phase C
- releases are cleaner, safer, and explainable
- duplicates, privacy flags, and review decisions are operationalized

## End of Phase D
- recurring expansion is sustainable
- benchmark subset exists
- source operations are stable

## End of Phase E
- the project supports community use and contribution
- annotated subsets and baselines increase practical value
- governance can handle long-term maintenance

---

# Suggested management cadence

## Weekly / near-term
- issue triage
- source/parser breakage checks
- small implementation milestones
- config/review updates

## Per release
- release diff review
- QA report review
- composition check review
- publication verification

## Quarterly / phase review
- reassess source policies
- reassess composition targets
- decide whether to promote new sources into public profiles
- update roadmap priorities

---

# Summary

The long-term success of HeOCR and hocrgen depends less on raw scraping volume and more on disciplined sequencing.

The roadmap should prioritize:

1. a narrow, defensible public release pipeline
2. strong rights and provenance infrastructure
3. operational hardening before aggressive source expansion
4. benchmark and annotation value once the dataset core is stable
5. governance and documentation as first-class project outputs

The project reaches maturity when it can repeatedly and transparently produce useful public Hebrew OCR dataset releases while maintaining a conservative legal posture, a clear dataset identity, and sustainable maintenance practices.
