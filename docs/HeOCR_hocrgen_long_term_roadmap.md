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

The roadmap assumes the following four-repository synthetic spinout boundary, introduced by `F4a`:

- **HeOCR**: the public mixed real+synthetic dataset
- **HeOCRsynth**: the synthetic-only dataset repository that receives versioned synthetic releases from `hocrgen`
- **hocrgen**: the open-source orchestration/governance/export toolchain that curates, versions, and publishes governed dataset releases
- **hocrsyngen**: the synthetic Hebrew OCR/HTR generation package that emits candidate generated sample units and manifests consumed by `hocrgen`

`F4f` records the three upstream repositories that feed `hocrsyngen` without changing any hocrgen runtime behavior, readiness gate, or release path. See [`heocr_ecosystem_overview.md`](./heocr_ecosystem_overview.md) for the full seven-repository chain and per-repository scope.

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

### 3.7 Evaluation moves to real scans (direction, 2026-11-06)
Evaluation should eventually run on real scanned Hebrew text only, printed and handwritten, with no synthetic text in the eval set. Printed and handwritten Hebrew get separate evaluation tracks, and possibly separate pipelines. Synthetic evaluation stays in use until enough real reference data exists; this is a transition, and current scoring is unchanged. See [E2d](#e2d--real-scan-evaluation-direction).

---

## 4. Roadmap structure

This roadmap is organized into phases and milestones.

### Phases
- **Phase A**: Foundation
- **Phase B**: First public release capability
- **Phase C**: Curation and operational hardening
- **Phase D**: Expansion and benchmark formation
- **Phase E**: Ecosystem maturity
- **Phase F**: Beta-scale trial preparation
- **Phase G**: Synthetic generation spinout and synthetic-only dataset stream

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
- `deferred`: intentionally paused until a named precondition changes; the reason is recorded with the item

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
| E1 | Ecosystem maturity | E1a, E1b, E1c, E1d, E1e | Community contribution model, the public contribution channels map, then planned channel follow-ups | partial |
| E2 | Ecosystem maturity | E2a, E2b | Baselines/evaluation utilities, then live/cached NLI seed acquisition | completed |
| E3 | Ecosystem maturity | E3a | Annotation subset pilots | completed |
| E4 | Ecosystem maturity | E4a | Multi-release governance maturity | completed |
| F1 | Beta-scale acquisition trial | F1a, F1b, F1b2, F1b3, F1b4, F1c, F1d, F1e | Operator-only beta-scale plan, source-depth feasibility/reporting, static-source expansion feasibility, source-depth count expansion, NLI runnable/cached promotion, bounded trial artifacts, near-duplicate/leakage hardening, and benchmark/holdout leakage resolution | completed |
| F2 | Benchmark ground-truth foundation | F2a, F2b | Transcription/layout guidelines, reference manifests, benchmark references, and adjudication workflow | completed |
| F3 | Modern handwritten acquisition program | F3a, F3b | Rights-clean modern Hebrew handwriting collection policy and operator acquisition workflow | completed |
| F4 | External synthetic provider integration | F4a, F4b, F4c, F4d, F4e, F4f | Synthetic spinout architecture, provider manifest contract, fixture-backed adapter, Hebrew rendering/provider gates, HeOCRsynth export handoff, shared release export packaging primitives, and wider HeOCR ecosystem upstream-chain documentation | completed |
| F5 | Public beta and publication readiness | F5a, F5b, F5c, F5d | Public beta gates, publication packaging, dataset-card, checksum/archive manifests, takedown-ready export handoff, blocker-closure sequencing, and repo-owned blocker reporting | completed-with-blockers |
| F6 | Public beta closure and external input integration | F6a, F6b, F6c, F6d, F6e, F6f1, F6f2a, F6f2, F6g | Post-F5 closure roadmap, takedown/private reporting closure, benchmark-reference evidence review, remaining repo-owned blocker closure, source-depth evidence, hocrsyngen installed-CLI adapter preflight planning, operator-only evidence-root reader, hocrgen-owned metadata sidecar definition, and final readiness rerun | partial |
| F7 | Governed HASH real-handwriting source integration | F7a, F7b, F7c, F7d, F7e | HASH source proposal and notation, fixture-backed review-only adapter, human-attested reference conversion, first promoted tranche with a real-handwriting-aware composition contract, and a benchmark_v2 proposal | partial |
| F8 | Real-source map and paired-text source intake | F8a, F8b, F8b2, F8b3, F8b4, F8b5, F8b6, F8b7, F8c, F8c2, F8d, F8d2, F8d3, F8d3b, F8e, F8e2, F8e3, F8f, F8g, F8g2 | Real (non-synthetic) Hebrew source map, then a review-only Wikisource proofread-page source, NLI licence-slug rights with free-use printed books, CC-BY-4.0 ground-truth dataset imports, born-digital and typewritten government print, and promotion of the real sources into the public path under a per-source composition contract | partial |

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
| E1b | E1 | Map every people- and organization-facing contribution channel with its gates, as planning only | no | completed | planning-only channel map in docs/contribution_channels_map.md |
| E1c | E1 | Contributor consent and waiver template for channel sections A, B and E | no | planned | needs Shay approval and legal review before any use; consent and privacy |
| E1d | E1 | Known-text kit for CC-B1 to CC-B5: rendered PDFs, templates, and an intake manifest schema | no | planned | not started; intake stays closed until E1c is approved |
| E1e | E1 | CC-C3 blank-paper intake pilot | no | planned | not started; bounded pilot under existing release gates |
| E2a | E2 | Baselines and evaluation utilities | no | completed | merged as PR #36 |
| E2b | E2 | Live-but-cached batch acquisition for vetted NLI seed URLs | no | completed | merged as PR #38 |
| E3a | E3 | Annotation subset pilots | no | completed | merged as PR #39 |
| E4a | E4 | Multi-release governance and maturity controls | no | completed | current ref governance PR |
| F1a | F1 | Define an operator-only beta-scale acquisition trial plan before implementation | no | completed | current ref beta trial planning PR |
| F1b | F1 | Implement operator-only beta-trial source-depth feasibility and reporting | no | completed | current ref source-depth feasibility PR |
| F1b2 | F1 | Define Pinkas/BiblIA source-depth expansion feasibility before F1c execution | no | completed | current ref source-depth expansion feasibility PR |
| F1b3 | F1 | Expand source-depth counts before F1c execution | no | completed | current ref source-depth count expansion PR |
| F1b4 | F1 | Expand NLI runnable/cached source depth before F1c execution | no | completed | current ref real NLI source-cached fixture promotion PR |
| F1c | F1 | Execute bounded beta-trial acquisition artifacts for `80` real items and `80` synthetic controls | no | completed | current ref operator-only target-scale trial artifacts |
| F1d | F1 | Add near-duplicate, source-group, and split-leakage hardening before scale beyond the trial | no | completed | current ref leakage hardening PR |
| F1e | F1 | Resolve benchmark/holdout leakage gate | no | completed | current ref typed benchmark/holdout leakage policy PR |
| F2a | F2 | Define transcription, layout-label, and reference-manifest guidelines for benchmark ground truth | no | completed | current ref benchmark ground-truth guideline PR |
| F2b | F2 | Implement benchmark-reference ingestion, adjudication artifacts, and benchmark versioning gates | no | completed | current ref benchmark-reference ingestion PR |
| F3a | F3 | Define rights-clean modern handwritten Hebrew collection policy, consent, privacy, and takedown workflow | no | completed | current ref acquisition policy PR |
| F3b | F3 | Implement operator workflow for bounded modern handwriting acquisition and review | no | completed | current ref operator-only modern intake workflow |
| F4a | F4 | Record the four-repository synthetic spinout architecture and provider-boundary plan | no | completed | current ref synthetic spinout planning PR |
| F4b | F4 | Define and ingest the external `hocrsyngen` generated-sample manifest contract with fixture validation | no | completed | current ref hocrsyngen manifest-backed source PR |
| F4c | F4 | Add deeper Hebrew rendering/provider metadata gates for `hocrsyngen` batches | no | completed | current ref hocrsyngen provider/rendering gates |
| F4d | F4 | Add synthetic-only export handoff for `HeOCRsynth` | no | completed | current ref synthetic-only export PR |
| F4e | F4 | Extract shared release export packaging primitives for alpha and HeOCRsynth releases | no | completed | current ref shared packaging cleanup PR |
| F4f | F4 | Document the wider HeOCR ecosystem upstream chain without changing runtime behavior or release gates | no | completed | current ref documentation-only HeOCR ecosystem overview PR; extends F4a four-repository spinout boundary upstream to `public-domain-hand-written-hebrew-scans`, `hletterscriptgen`, and `hletterscript` |
| F5a | F5 | Define public beta readiness gates over source depth, uniqueness, ground truth, review, and portability | no | completed | current ref public beta readiness gate contract |
| F5b | F5 | Implement public beta publication packaging and handoff workflow | no | completed | current ref public beta packaging and blocked handoff workflow |
| F5c | F5 | Close public beta readiness blocker sequencing and repo-owned handoff gaps | no | completed | current ref blocker-closure plan and takedown reporting config |
| F5d | F5 | Close repo-owned public beta readiness gates before external scale inputs | no | completed | current ref repo-owned blocker evidence and private-reporting settings check |
| F6a | F6 | Define post-F5 public beta closure roadmap | no | completed | current ref planning-only post-F5 closure roadmap |
| F6b | F6 | Close takedown/private reporting readiness with a verified private path | no | completed | current ref verified GitHub private vulnerability reporting path; closes only takedown/removal |
| F6c | F6 | Close benchmark-reference readiness with reviewed/adjudicated evidence | no | completed | current ref F6c evidence review keeps benchmark_references blocked because current coverage is 1 / 3 reviewed/adjudicated |
| F6d | F6 | Close privacy/review blockers through review/config/source-status changes | no | completed | current ref F6d evidence review keeps privacy_review blocked because current review evidence is default-unresolved |
| F6e | F6 | Close source-depth and composition readiness with real public-profile evidence | no | completed | current ref F6e evidence review keeps source_depth_composition blocked because current public-profile payload evidence is only 2 / 80 real candidates and F1c/operator-only inventory does not count |
| F6f1 | F6 | Plan hocrsyngen installed-CLI adapter preflight and diagnostic dry-run | no | completed | current ref planning-only hocrsyngen S6 handoff review and hocrgen-owned release/import metadata gap |
| F6f2a | F6 | Implement hocrsyngen evidence-root preflight/import-packet reader | no | completed | current ref operator-only hocrgen diagnostic over hocrsyngen evidence-run roots with release_eligible=false |
| F6f2 | F6 | Define hocrsyngen release/import metadata sidecar | no | completed | current ref hocrgen_hocrsyngen_import_metadata_packet.v1 derived from validated evidence roots; operator-only release_eligible=false |
| F6g | F6 | Re-run public beta readiness after privacy/review closure, source-depth, and synthetic-scale inputs exist | no | planned | final convergence only after privacy/review closure evidence plus F6e-F6f2 evidence exists |
| F7a | F7 | Define the governed HASH source integration plan and planned notation | no | completed | current ref planning-only HASH source proposal record; no runtime, profile, or gate change |
| F7b | F7 | Add a fixture-backed review-only HASH source adapter | no | completed | current ref review_only sources outside profile_open_v1; CC-BY-SA-3.0 entries rejected; candidate HTR text never read |
| F7c | F7 | Convert human-attested HASH transcripts into benchmark reference artifacts | no | planned | needs human-attested HASH transcripts, which a new human transcription campaign may supply; none of the 10 HASH reviewed transcripts meets the bar yet; HTR candidates are never ground truth |
| F7d | F7 | Promote a first HASH tranche and reconcile the real-source composition contract | no | planned | F8g's `real_source_composition.v2` already carries not-promoted HASH entries and `writer:` work-group keys, so F7d sets a promotion and floor and ships a tranche through `hocrgen.tools.real_tranche`; no per-item privacy review (maintainer decision 2026-11-06) |
| F7e | F7 | Propose benchmark_v2 with adjudicated HASH references | no | planned | benchmark_v1 membership stays frozen under its stability policy |
| F8a | F8 | Map real Hebrew document sources and define the F8 notation | no | completed | current ref planning-only source map in planning/tasks/f8-real-source-map.md; no source, profile, licence, or gate change |
| F8b | F8 | Add a fixture-backed review-only Wikisource proofread-page source | no | completed | current ref review-only `wikisource_he_proofread` source (docs/wikisource_proofread_source.md): 3 fixture pages from 3 admitted Indexes, per-Index work and scan rights gates, editor attestation, and an operator-only F2 reference conversion; not in profile_open_v1 |
| F8b2 | F8 | Inventory every Hebrew Wikisource Index through the F8b gates (operator-only) | no | completed | current ref operator-only `hocrgen.tools.wikisource_inventory` and committed summary docs/wikisource_index_inventory.md: 29 of 141 Indexes admitted; 231 quality-3 and 12 quality-4 pages pass every gate except transcription coverage; no fixture, source, profile or gate change |
| F8b3 | F8 | Resolve Wikisource evidence gaps, render every page construct, and record coverage | no | completed | current ref decisions 9-12 in the Index gate (cited death years, pre-1856 presumption, scan tags and Google provenance only), Hebrew language gate, wikisource_plain_text.v2 checked against MediaWiki action=parse, agent coverage checks with needs_crop; 68 of 141 Indexes admitted, 82 / 43 pages eligible now, 30 needs_crop (docs/wikisource_index_inventory.md) |
| F8b4 | F8 | Check Wikisource coverage with an OCR-alignment tool and crop partial pages | no | completed | current ref operator-only `hocrgen.tools.wikisource_coverage` (Tesseract boxes only, never text) with tool checks docs/wikisource_page_tool_checks.json; crops of partial pages in the pipeline with crop provenance and source-health geometry checks; labelled-section transclusion pinned by revision; footnote_marker_style recorded; 837 / 43 full-page and 196 / 4 cropped pages eligible, 61 crop_unresolved, 74 undecided (docs/wikisource_index_inventory.md); not in profile_open_v1 |
| F8b5 | F8 | Resolve the Wikisource coverage, crop and attestation residuals | no | completed | current ref multi-region crops (regions kept, the rest of the box masked; source health checks the pixels), agent crops in page checks (agent_visual_crop.v1), agent visual review of the 188 residual pages, rename-aware pagequality attribute check, cited death years for 4 Indexes; 946 / 43 full-page and 241 / 5 cropped pages eligible, 0 crop_unresolved, 1 undecided (docs/wikisource_index_inventory.md); not in profile_open_v1 |
| F8b6 | F8 | Resolve the Wikisource rights residual and exclude text-image mismatches | no | completed | current ref evidence-file creators, creator corrections, publication years and additional grounds read by the unchanged Index gate; Korfu 1885, Dorot ha-Rishonim I, Artush, Hebrewbooks 9418 and Kol Machzike Hadas admitted (77 of 141 Indexes); text_not_on_page page reason (13 pages); converter templates for the new pages; 1161 / 56 full-page and 235 / 5 cropped pages eligible (docs/wikisource_index_inventory.md); not in profile_open_v1 |
| F8b7 | F8 | Harden Wikisource pairs: unprinted footnotes, editor stand-ins and text the scan hides | no | completed | current ref tool footnote check (OCR boxes only) and agent text reviews of all 90 flagged or unchecked footnote pages; 37 unprinted notes dropped from 31 pairs (`unprinted_notes`, faithful checksum kept); reviewed stand-in mapping `typed_pipe_as_paseq.v1` (`|` → U+05C0, 44 occurrences on 21 pairs); `illegible_on_scan` spans excluded from primary scoring (Korfu p. 128); Korfu spot check 30 / 30 agree; 1159 / 56 full-page and 236 / 5 cropped pages eligible (docs/wikisource_index_inventory.md); F8g tranche manifest regenerated (1,609 pages) |
| F8c | F8 | Key NLI rights on the IIIF licence slug and admit free-use printed books | no | completed | current ref slug-keyed nli rights gate over pinned IIIF manifest captures; only public-domain-free-use maps to open; three printed_historical book seeds stay exploratory, so the 27 / 27 / 26 allocation is unchanged; images only |
| F8c2 | F8 | Inventory NLI digitized printed Hebrew books by IIIF licence slug | no | completed | current ref operator-only `hocrgen.tools.nli_printed_inventory` and committed summary docs/nli_printed_inventory.md: 36 sampled result pages, 1,766 books; 22.7% free-use with admissible pages (about 4,460 books and 0.53 million pages in the 20,000 reachable records); 60% Google-class non-commercial; no seed, source, composition or profile_open_v1 change |
| F8d | F8 | Import CC-BY-4.0 human ground-truth datasets as review-only sources | no | completed | merged as PR #108: review_only yidtaknl_vaybertaytsh_gt (NLI-scanned pages only, character-level evaluation and training only); pinkas_dataset_bgu moved to F8d2 |
| F8d2 | F8 | Admit NLI-matched ground truth: the BGU Pinkas dataset and more YidTakNL works | no | completed | current ref review_only pinkas_dataset_bgu (PAGE XML lines on NLI Ms. Heb. 4°662 free-use scans); YidTakNL 1747 and JB 899 matched page by page; 1737 and 1772 unmatched |
| F8d3 | F8 | Add per-line language tags to the BGU Pinkas lines | no | completed | current ref typed per-line he/yi/mixed/unknown tags for pinkas_dataset_bgu (docs/pinkas_dataset_source.md); only a human he tag unlocks Hebrew evaluation for its line; committed tags are agent_proposed and advisory, so every line stays character_level_only; no scoring or profile change |
| F8d3b | F8 | Make non-text BGU Pinkas lines scope-neutral and give human-tagged Hebrew lines full Hebrew scope | no | completed | current ref lines with no Hebrew-script letter (U+05D0-U+05EA) are classified from their pinned text as scope_neutral, never get Hebrew scope and are ignored by the page rule; human he lines get full_hebrew scope (word-level and language-level Hebrew evaluation, nothing excluded; decision 8 as clarified) (docs/pinkas_dataset_source.md); no scoring or profile change |
| F8e | F8 | Add born-digital and typewritten government print sources | no | completed | current ref review-only reshumot_born_digital (born-digital pages rendered, embedded text bidi-checked) and knesset_committee_protocols_pre1976 (typewritten_historical scans, sessions to 1975-12-31, images only); not in profile_open_v1; protocols from 1976 wait for a legal opinion |
| F8e2 | F8 | Rebuild Reshumot text from the PDF glyph layer and verify it line by line | no | completed | current ref `pdf_glyph_geometry_logical.v1` (glyph layers via pdfminer.six, operator-only; outline identity table; forward-bidi round trip, ink checks, decision-12 crops of unverifiable lines) raises Reshumot from 180 to 796 of 886 captured pages (2017 on: 0 to 243 of 272); tranche `f8e2_real_tranche_v3` |
| F8e3 | F8 | Record Reshumot reading order as verified within lines, score it line-matched, retire the pdftotext method | no | completed | current ref every Reshumot entry records `reading_order_verified: within_line` (line text verified, block order a convention), carried into item metadata, tranche manifest items and release terms (`page_reading_order` excluded); `evaluate-references` scores such text on the new `line_matched.v1` view, never in page order; packaged fixture migrated to the glyph layer and `poppler_bidi_logical.v1` removed; digit-dash-digit lines stay cut; tranche `f8e3_real_tranche_v4` |
| F8f | F8 | Pilot aligning Project Ben-Yehuda texts to NLI free-use scans of the same edition | no | completed | current ref operator-only `hocrgen.tools.benyehuda_nli_alignment` and summary docs/benyehuda_nli_alignment_pilot.md: 11 of 45 candidate editions matched to `public-domain-free-use` scans through the unchanged F8c gate; 277 pages of 10 works aligned (275 high), OCR for localization only, decision-12 crops; silver pairs only (`human_typed_edition_text_aligned`, `not_adjudicated`, `reference_eligible: false`); no source, profile or scoring change |
| F8g | F8 | Promote the real F8 sources into the public path under a per-source composition contract | no | completed | current ref `real_source_composition.v2` (per-source floors and caps, printed/handwritten floors) replaces the 27 / 27 / 26 allocation in `source_depth_composition`; work-group leakage keys and a synthetic-training registry; wikisource, yidtaknl, pinkas_dataset_bgu, reshumot and knesset sources `allowed` in profile_open_v1 with per-item release terms, paired text, NOTICE and attribution manifests; operator tranche tool and committed manifest (1,610 pages, 814 MB, not in git, not published); composition passes on the tranche (95 / 80), blocked on fixtures (docs/real_source_release_contract.md) |
| F8g2 | F8 | Harden the real tranche: size-aware group splits, Pinkas canvas checks, crop floor, Reshumot and Knesset growth, `wikisource_plain_text.v3` | no | completed | current ref `size_aware_group_split.v1` (`hocrgen.split.balance`, seeded, whole groups per source/modality, benchmark splits pinned) brings the tranche to 81 / 9 / 10 from 65 / 34 / 1.5; Pinkas canvas bindings 6 / 30 verified, 24 recorded not verified (NLI HTTP 520); text-region crop floor 32 px; 33 empty YidTakNL texts confirmed upstream; Reshumot 182 (180 / 886 captured pages pass F8e) and Knesset 205 (18 protocols, 1949-1974); `wikisource_plain_text.v3` broken-link labels and `text_derivation` (#134); tranche `f8g2_real_tranche_v2`, 1,995 pages, 910 MB; composition 105 / 80 (docs/real_source_release_contract.md) |

## 4.3 Current critical path

The immediate implementation critical path after `F6f2` is:

1. Keep the F1c operator-only target-scale trial as evidence only: `27` NLI / `27` Pinkas / `26` BiblIA real-source candidates plus currently configured hocrsyngen synthetic fixture samples can be exercised through gates, but the artifacts remain operator-only and not publishable public beta outputs.
2. Keep the known blocker visible: full synthetic target scale still requires a larger validated hocrsyngen batch, so current F1c artifacts do not satisfy the F5a synthetic target-scale gate.
3. Keep `F1d` near-duplicate, source-group, and split-leakage hardening in force before treating any candidate pool as public beta or release-candidate material.
4. Keep `F1e` benchmark/holdout leakage policy in force: exact duplicate, near-duplicate, or source-group overlap between benchmark items and non-benchmark holdout/public-beta candidates must have a typed repo-tracked accepted resolution, and stale or missing resolutions block readiness claims.
5. Keep F2b benchmark-reference ingestion in place as optional ground-truth infrastructure; public beta benchmark claims must disclose reference coverage and status rather than implying complete annotation coverage.
6. Keep `export-public-beta` blocked until every F5a/F5b gate passes; keep synthetic-only `HeOCRsynth` readiness separate from mixed `HeOCR` readiness.
7. Use `manifests/public_beta_blocker_closure_plan.json`, `manifests/public_beta_source_depth_composition_report.json`, and `manifests/public_beta_repo_owned_blocker_report.json` as the machine-readable sequencing artifacts for the current blocker set: source-depth/composition has a dedicated public-profile evidence report while remaining input-dependent until real candidates are promoted, privacy/review closure and benchmark-reference readiness/status disclosure have item/status-level repo-owned closure evidence, and takedown/private reporting now passes only from the verified GitHub private vulnerability reporting config evidence. F6c records that current benchmark-reference evidence is still partial (`1 / 3` selected benchmark items reviewed/adjudicated), so `benchmark_references` remains blocked. F6d records that current privacy/review evidence is still unresolved, so `privacy_review` remains blocked until repo-tracked review/config/source-status closure evidence exists. F6e records that current source-depth/composition evidence is only `2 / 80` real public-profile payload candidates (`1` NLI / `1` Pinkas / `0` BiblIA), so `source_depth_composition` remains blocked until real public-profile candidates pass normal gates. The larger validated hocrsyngen batch remains external/input-dependent and must not be faked or relaxed.
8. Execute the remaining F6 work in evidence order: `F6f2` has settled the downstream release/import metadata form as an operator-only hocrgen-owned packet, and `F6g` may rerun public beta readiness only after privacy/review closure, source-depth, and synthetic-scale release-path evidence exists.

This prioritization is intentional. `F4a` records the synthetic spinout architecture, and `F4b` makes hocrsyngen manifests the active synthetic input boundary without displacing hocrgen's source-depth and release gates. `B5a` made the alpha mechanically exportable, `B5b1` through `B5b3` closed the portability and content-quality blockers, and `B5b4` froze `alpha-v0` into the separate `HeOCR` repository with a ready-for-review handoff PR. `C5b` then closed the missing review-decision merge path by adding repo-tracked review inputs, a dedicated `review-merge` stage, deterministic post-review gating, and auditable decision artifacts. `C6a` made exported release trees explainable over time through baseline-aware diffs and changelog generation. `D1a` moved routine dry-run maintenance into GitHub Actions with persisted run summaries. `D2a` adds source health, fixture-backed adapter regression coverage, freeze/degrade reporting, and portable source-health check paths where package or config-root references are available so source instability is visible without tying operator artifacts to local install paths unnecessarily. `D3a` defines the first explicitly approved `benchmark_v1` subset with benchmark manifests, selection audit, a stability policy, and usage guidance; the current ref also packages the benchmark approval config so non-editable installs do not depend on a checkout-root `benchmark_data/` directory. `D4a` and `D4b` remain legacy in-repo synthetic generator milestones whose code stays as smoke coverage, but active `project_synthetic` ingestion now comes from hocrsyngen `generation_manifest.v1`. `D5a` adds optional, portable annotation-reference slots and annotation manifests so future transcription work can attach to release items without making transcriptions mandatory for current alpha/public outputs. `E1a` defines source proposal, source-adapter, synthetic asset, dataset issue, external review, and release-governance contribution paths while preserving existing rights, privacy, review, and release gates. `E2a` adds benchmark example loading, JSON/JSONL text prediction evaluation, character error rate and exact-match helpers, coverage reporting, and lightweight leaderboard-ready conventions over the existing `benchmark_v1` artifacts without adding model training infrastructure. `F1a` selects the next post-E4 path as an operator-only beta-scale acquisition trial rather than broad crawling, publication, or a release-candidate export. `F1b` adds an operator-only source-depth feasibility artifact at discovery time and shows that target-scale execution is not yet feasible from committed fixtures alone. `F1b2` defines the Pinkas/BiblIA expansion path as packaged records plus source-health-visible assets, rights/provenance requirements, review requirements, and non-goals before those static sources can count toward F1 scale. `F1b3` adds validated target-scale Pinkas and BiblIA inventory while keeping runnable/cached feasibility separate from inventory readiness. `F1b4` closes the NLI promotion gap with real source-cached fixtures. `F1c` adds the explicit `hocrgen f1-beta-trial --profile profile_open_v1 --dry-run` path, which opts into source-depth-only NLI seeds, packaged Pinkas/BiblIA expansion records, and the configured hocrsyngen synthetic fixture batch while preserving normal bounded public profile behavior. `F1e` turns the F1d benchmark/holdout warning into a typed gate and records the current Pinkas WDL11806 source-group resolution without changing `benchmark_v1` membership. `F2a` defines benchmark ground-truth transcription, layout-label, and reference-manifest guidelines, and `F2b` now implements optional reference ingestion, adjudication/status artifacts, release-relative path validation, item/source/split linkage checks, layout checksum/dimension checks, and correction/supersession versioning gates without making references mandatory for current public or alpha exports.

`F3a` defines the rights-clean modern handwritten Hebrew acquisition policy in [`modern_handwritten_acquisition_policy.md`](./modern_handwritten_acquisition_policy.md). The policy covers contributor consent and public-use release terms, rights provenance, conservative contemporary privacy screening, takedown/removal handling, scanning/upload standards, mandatory operator review, composition targets for demographic bands, script style, page type, and mixed-language coverage, and source-family boundaries between modern real handwriting, historical public sources, and synthetic data.

`F3b` implements the bounded operator workflow against that policy. Custom operator configs can define `modern_handwriting_intake` sources backed by typed JSON intake manifests and source-relative JPEG/PNG assets. Config validation and source health now enforce adult contributor eligibility, consent/provenance ids, `HEOCR-CONSENT-OPEN` rights, clear privacy screening, clean takedown state, scan/composition metadata, portable paths, checksums, and review-only source settings. Valid modern records flow through the normal acquisition, QA, dedupe, privacy, review, split, benchmark, and export gates, but they are not added to default profiles and require explicit review approval before public release inclusion.

`F4c` hardens the hocrgen-side hocrsyngen fixture/import boundary, not the upstream public hocrsyngen manifest v1 contract. Configured hocrgen release-path fixtures now require explicit provider metadata, offline manifest-batch generation mode, no-network/no-REST/no-GPU/no-LLM/no-diffusion flags, per-sample logical RTL rendering metadata, computed Hebrew coverage metadata, and batch-level Hebrew/final-letter/numeral/punctuation coverage as hocrgen-owned import/release metadata. Source health and synthetic composition reports surface provider version, layout families, coverage counts, and optional niqqud/mixed-LTR coverage gaps. hocrgen still does not import hocrsyngen internals, call hocrsyngen commands, contact services, or require heavyweight generator dependencies.

`F5a` is implemented on the current ref as the readiness-definition contract. It defines mixed `HeOCR` public beta publishability as a separate contract from operator trial success: source depth and composition evidence, synthetic target-scale and cap policy, rights/provenance proof, privacy/review closure, exact/near/source-group/split/benchmark leakage clearance, benchmark-reference readiness, annotation-status disclosure, release-relative manifest/checksum/archive portability, dataset-card/provenance/changelog completeness, and takedown/removal readiness all need to pass before public beta publication. `F5b` is now implemented as `hocrgen export-public-beta`, which runs `build-release`, packages a local mixed `HeOCR` handoff tree, writes `manifests/public_beta_readiness_report.json` with explicit `pass`/`blocked` gates, emits checksum and archive manifests, creates a version-rooted portable archive, generates beta-specific docs, and verifies asset/archive digests from the handoff tree. `F5c` adds `manifests/public_beta_blocker_closure_plan.json`, derives closure work from the readiness report, categorizes blockers as `repo_owned_immediately_actionable` or `external_input_dependent`, and makes the takedown private-reporting path status explicit through `src/hocrgen/config/public_beta.yaml`. `F5d` adds `manifests/public_beta_repo_owned_blocker_report.json`, so unresolved privacy/review items, benchmark-reference draft/unavailable/adjudication states, and the latest private-reporting repository-settings check are recorded separately from external source-depth and synthetic-scale blockers. It does not publish to `HeOCR`, Hugging Face, Kaggle, or `HeOCRsynth`, does not emit a publication report while blocked, and does not relax the existing alpha and synthetic export gates.

`F6a` is implemented on the current ref as a planning-only post-F5 closure roadmap. It adds no runtime behavior, does not edit readiness status semantics, does not publish any artifact, and does not make the current blocked public beta export publishable. `F6b` is implemented on the current ref by recording GitHub private vulnerability reporting for `HeOCR/hocrgen` as enabled and verified in `src/hocrgen/config/public_beta.yaml`, based on the authenticated GitHub API repository-settings check. That evidence closes only the takedown/private reporting gate and removes `takedown_removal` from the blocked readiness and blocker-plan outputs. `F6c` is implemented on the current ref as an evidence review/reporting hardening pass for benchmark-reference readiness. Current benchmark-reference evidence remains insufficient for public beta readiness: `nli_any_use_permitted:nli-ms-seed-006` is reviewed/adjudicated, `pinkas_open:pinkas-ledger-001` is still draft/in review, and `project_synthetic:synthetic-0` has no public reference. The public beta readiness report and repo-owned blocker report therefore keep `benchmark_references` blocked and disclose the `1 / 3` reviewed/adjudicated coverage rather than converting a limitation into readiness. `F6d` is implemented on the current ref as an evidence review/reporting hardening pass for privacy/review readiness. Current privacy/review evidence remains insufficient for public beta readiness: governed candidates are still review-required with default-unresolved review decisions, and no repo-tracked review decision, privacy config change, or source-status change currently closes that gate. The public beta readiness report and repo-owned blocker report therefore keep `privacy_review` blocked and disclose the unresolved review limitation rather than converting it into readiness. `F6e` is implemented on the current ref as an evidence review/reporting hardening pass for source-depth/composition readiness. Current source-depth/composition evidence remains insufficient for public beta readiness: the public-profile payload has only `1` NLI item, `1` Pinkas item, `0` BiblIA items, and `2` synthetic items, while F1c/operator-only/source-depth-only inventory is explicitly not counted as public payload readiness. The public beta readiness report, `public_beta_source_depth_composition_report.json`, and repo-owned blocker report therefore keep `source_depth_composition` blocked and disclose the `2 / 80` real public-profile candidate coverage rather than converting operator-only inventory into readiness. `F6f1` is implemented on the current ref as planning only: it records the hocrsyngen S6 handoff review, confirms that hocrgen should use installed hocrsyngen CLI JSON surfaces only in an explicit operator-only preflight, and identifies the current gap between public hocrsyngen `generation_manifest.v1` output and hocrgen's hardened release/import metadata expectations for provider, rendering, and Hebrew coverage metadata. `F6f2a` implements the first hocrgen-side reader for that boundary: `hocrgen hocrsyngen-preflight` consumes a hocrsyngen evidence-run root, validates `candidate_evidence_run_report.v1`, `generation_report.v1`, `validation_report.v1`, `template_catalog.v2`, public `generation_manifest.v1`, SHA-256 inventory, page assets, and manifest-to-catalog joins, then writes an operator-only hocrgen diagnostic report with `release_eligible: false`. It does not wire raw hocrsyngen output into default release paths, relax release gates, call hocrsyngen from release/export commands, or ask hocrsyngen to mutate `generation_manifest.v1`. `F6f2` defines the hocrgen-owned `hocrgen_hocrsyngen_import_metadata_packet.v1` sidecar/import packet, validates the packet with typed hocrgen-owned models, and keeps release/import projection false unless provider runtime flags are explicitly evidenced. `F6g` is for rerunning public beta readiness only after the required privacy/review closure, source-depth, and synthetic-scale release-path evidence exists. The `2 / 80` synthetic target-scale blocker, source-depth composition blocker, benchmark-reference blocker, and privacy/review blocker remain blocked until real inputs exist.

The outside reviews under `docs/2026_05_01_outside_review/` reinforce that the repo is pipeline-mature but not yet large-dataset or benchmark-mature. The spinout reviews under `docs/2026_05_02_heocrsyn_spinout/` reinforce a second boundary: advanced synthetic OCR/HTR generation should be its own package and dataset stream, while `hocrgen` remains dependency-light and gate-driven. The post-F1 roadmap therefore treats acquisition scale as only one gate. It also elevates uniqueness/leakage control, benchmark ground truth, modern handwritten acquisition implementation, external synthetic-provider contracts, Hebrew rendering gates, and publication readiness as separate follow-on milestones rather than hidden assumptions inside the `80` real / `80` synthetic trial target.

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

`E1b` adds [`docs/contribution_channels_map.md`](./contribution_channels_map.md), a planning-only map of contribution channels for non-developers: text, known-text physical transformations, images, ready-made pairs, labelling, rights research, evaluation, feedback from real use, resources, and reach. It ranks the channels and lists the gates that apply to every one of them. It does not add upload forms, collection flows, or sources; each channel selected for implementation needs its own roadmap notation and stays under `F3a`/`F3b` and the existing release gates.

`E1c`, `E1d`, and `E1e` are planned follow-ups from the map and are not started. `E1c` is the contributor consent and waiver template covering channel sections A, B, and E; because it concerns consent and privacy, it needs Shay's approval and legal review before any use. `E1d` is the known-text kit for `CC-B1` to `CC-B5` (rendered PDFs, templates, and an intake manifest schema). `E1e` is the `CC-C3` blank-paper intake pilot. No channel accepts contributions until its item lands and, where it collects from people, `E1c` is approved.

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

# Phase F — Beta readiness and benchmark foundation

Phase F turns the post-E4 pipeline into a credible beta-readiness program. Its purpose is not to chase volume by relaxing gates. It tests whether real-source growth, uniqueness controls, benchmark references, modern handwritten coverage, synthetic quality, and publication packaging can mature in the right order.

## Milestone F1 — Beta-scale acquisition trial

### Objective
Define and then execute a bounded operator-only trial that tests whether HeOCR can grow beyond the alpha exemplar set without weakening source policy, review, privacy, benchmark, split, synthetic, uniqueness, or export-portability gates.

### Scope
- beta-scale acquisition targets before public beta/release export
- per-source real-item allocation
- source-depth feasibility gates for bounded static sources
- operator-facing acquisition reports
- near-duplicate, source-group, and split-leakage hardening before scale beyond the trial
- GitHub issue template for beta-trial implementation work

### Planned PRs
- `F1a`: define the beta-scale trial plan, issue template, target counts, non-goals, and gates
- `F1b`: implement the first operator-only beta-trial source-depth feasibility and reporting path
- `F1b2`: define fixture-backed, rights-safe, reviewable Pinkas/BiblIA source-depth expansion before F1c execution
- `F1b3`: expand source-depth counts for Pinkas, BiblIA, and synthetic controls before F1c execution
- `F1b4`: promote NLI runnable/cached fixture-backed source depth before F1c execution
- `F1c`: execute bounded beta-trial acquisition artifacts for the `80` real / `80` synthetic target only after feasibility gates pass
- `F1d`: add near-duplicate, source-group, and split-leakage hardening before larger public-beta or release-candidate work
- `F1e`: resolve the benchmark/holdout leakage gate with typed accepted resolutions before public-beta or release-candidate claims

### Trial target
The default F1 trial target is `80` real items plus `80` synthetic controls. Real items are allocated as `27` NLI, `27` Pinkas, and `26` BiblIA. This target is intentionally source-balanced, but Pinkas and BiblIA may not proceed past feasibility until their source-depth expansion path is explicit, fixture-backed, rights-safe, and reviewable.

### Non-goals
- broad live-source crawling
- public beta export or release-candidate export
- publication to Hugging Face or the GitHub dataset repo
- automatic public-profile promotion
- network-dependent CI
- relaxing rights, privacy, review, dedupe, split, benchmark, synthetic-cap, or export-portability gates to hit volume

### Current-ref implementation
`F1a` is implemented on the current ref as planning and workflow scaffolding plus a repo-native Splendor knowledge workspace. It does not add acquisition code, export code, new source adapters, or publication behavior. The Splendor workspace adds generated source summaries, source manifests, topic scaffolds, queue/run state, and agent brief/query entrypoints for future coding-agent context without changing hocrgen runtime behavior or dataset outputs.

`F1b` is implemented on the current ref as an operator-only discovery artifact. Every `discover` run writes `source_depth_feasibility.json` with the F1 target counts, per-source allocation, observed candidate counts, health-eligible runnable/cached candidate counts, asset counts, exploratory catalog counts where applicable, gaps, feasibility status, report-scoped warnings, operator notes, required gates, and non-goals. After `F1b4`, the current fixture-backed NLI depth is `27 / 27` runnable/cached real source-cached NLI seeds. This artifact does not create broad crawling, public beta export, release-candidate export, publication, or network-dependent CI.

`F1b2` is implemented on the current ref as the static-source expansion feasibility unblock before F1c. Pinkas and BiblIA now declare packaged `source_depth_expansion.yaml` manifests that source health validates, and the F1 feasibility report includes expansion-path status/checks. New static records only count when they remain packaged, deterministic, PD-IL-compatible, provenance-bearing, asset-backed, and reviewable.

`F1b3` is implemented on the current ref as source-depth inventory expansion before F1c execution. Pinkas now has `27 / 27` packaged source-depth inventory records/assets from bounded public-domain Commons page fixtures, and BiblIA has `26 / 26` packaged source-depth inventory records/assets from bounded public-domain `Bible from 1300` page fixtures. After F4b, `project_synthetic` is hocrsyngen manifest-backed and currently validates `2 / 80` synthetic fixture samples; synthetic target scale now requires a larger validated hocrsyngen batch rather than hocrgen-side generation.

`F1b4` is implemented on the current ref as the NLI runnable/cached source-depth promotion before F1c execution. The 20 exploratory catalog entries were promoted through the bounded operator path into real committed NLI fixture HTML plus cached page assets, so NLI now reports `27 / 27` runnable/cached source-depth candidates and the exploratory catalog is empty. The newly promoted fixtures are marked source-depth-only, so they do not automatically enter normal release/export discovery before F1c target-scale gate execution. Generated or hand-authored stand-in assets did not close the F1 source-depth gate.

`F1c` is implemented on the current ref as an explicit operator-only target-scale trial path. `hocrgen f1-beta-trial --profile profile_open_v1 --dry-run` includes source-depth-only NLI seeds, packaged Pinkas/BiblIA expansion records, and the currently configured hocrsyngen synthetic fixture samples, then runs them through source-health, rights, privacy, review, dedupe, split, benchmark, synthetic-cap, and export-portability gates. The command writes `build_release/f1_target_scale_trial_report.json` with acquisition counts, rights outcomes, review outcomes, dedupe outcomes, split/benchmark eligibility, post-review synthetic-cap status, source allocation, non-goals, and remaining blockers. Normal public profile discovery, build-release, and alpha export behavior remains bounded unless this F1c command is selected. Full `80` synthetic target execution remains blocked until a larger validated hocrsyngen batch is configured.

`F1d` is implemented on the current ref as deterministic, dependency-light leakage hardening. Exact dedupe behavior remains unchanged: exact asset-sequence duplicates are removed with a deterministic canonical item. Near-duplicate candidates are surfaced from content-derived quantized thumbnail hashes and marked as release-readiness blockers until reviewed rather than auto-removal candidates. Source-work groups are derived from explicit metadata or source-specific stable URL keys and are kept in the same split. Split leakage reports now cover exact duplicate clusters, near-duplicate cluster split exposure, source groups, and benchmark/holdout group risk. Build-release and the F1 trial emit near-duplicate/source-group artifacts and explain the conservative policy. On the current F1 trial data, synthetic target-scale execution is blocked until a larger validated hocrsyngen batch is configured; the report still surfaces downstream review, synthetic-cap, and benchmark/holdout source-group blockers as evidence that the gates remain enforceable, not permission to publish.

`F1e` is implemented on the current ref as the explicit benchmark/holdout leakage resolution gate. `benchmark_v1` now carries a typed `benchmark_holdout_leakage_policy` with accepted resolutions. `build-release` and `f1-beta-trial` emit `benchmark_leakage_risk.json`, embed the same status in `leakage_report.json`, and treat exact duplicate, near-duplicate, or source-group overlap between benchmark members and non-benchmark holdout/public-beta candidates as blocked unless a resolution exactly matches the detected group kind, group id, benchmark members, and non-benchmark members. The current Pinkas WDL11806 source-group overlap is deliberately resolved by excluding the related non-benchmark Pinkas pages from holdout/public-beta readiness claims. This keeps `benchmark_v1` membership stable, keeps current public/alpha exports bounded, and does not claim public beta readiness.

### Exit criteria
- the next beta-trial implementation issue can be opened from a template with concrete counts, source allocation, gates, validation, and non-goals
- the roadmap distinguishes operator-only trial work from public beta/release export work
- Pinkas/BiblIA source-depth feasibility is explicit before implementation treats them as scalable sources
- NLI runnable/cached source depth and Pinkas/BiblIA/static synthetic target-scale inventory gaps are closed, and `F1c` target-scale gate execution artifacts now exercise that inventory
- beta-trial artifacts preserve enough reporting to explain rights, acquisition failures, missing assets, review outcomes, dedupe outcomes, and split/benchmark eligibility
- near-duplicate and source-group leakage risks are surfaced before scale beyond the operator-only trial
- exact duplicate clusters, near-duplicate clusters, source groups, and benchmark/holdout risks cannot silently cross split or holdout/public-beta boundaries
- unresolved or stale benchmark/holdout leakage resolutions block the F1 trial/report gate rather than remaining passive warnings

### Risks / dependencies
- NLI live acquisition may remain operationally brittle
- review capacity remains visible in F1c artifacts and must not be confused with public beta readiness
- acquisition volume could outpace review and privacy capacity if gates are not enforced

---

## Milestone F2 — Benchmark ground-truth foundation

### Objective
Turn the existing benchmark and annotation scaffolding into a credible benchmark path with explicit references, guidelines, and adjudication artifacts.

### Scope
- Hebrew transcription guidelines covering niqqud, punctuation, numerals, Latin fragments, abbreviations, and bidi edge cases
- layout-label guidelines for line, region, and page-level references
- reference-manifest contracts tied to release-relative annotation paths
- review/adjudication workflow for benchmark references
- benchmark versioning gates for adding, correcting, or removing referenced items

### Planned PRs
- `F2a`: define transcription, layout-label, and reference-manifest guidelines for benchmark ground truth
- `F2b`: implement benchmark-reference ingestion, adjudication artifacts, and benchmark versioning gates

### Current-ref implementation
`F2a` is implemented on the current ref as human-facing benchmark ground-truth guidance. [`docs/benchmark_ground_truth_guidelines.md`](./benchmark_ground_truth_guidelines.md) defines Hebrew transcription policy for logical text order, Unicode NFC normalization, right-to-left and bidi behavior, niqqud, punctuation, Hebrew/Arabic/Latin numerals, Latin fragments, abbreviations, uncertain or damaged text, marginal and deleted text, and line/page boundaries. It also defines layout-label conventions for page, region, line, and optional word/reference levels; pixel coordinates over normalized release assets; reading order; multi-page items; uncertainty/review flags; and portability constraints. The same document records minimum documentation-level child-reference shapes for `benchmark_transcription_reference.v1` and `benchmark_layout_reference.v1`, plus the parent `benchmark_reference_manifest.v1` contract with release-relative paths, item/source identity linkage, transcription and layout-label references, reviewer/adjudication status, correction/versioning fields, checksum/page linkage, and separate public, private adjudication, and future hidden reference classes.

`F2b` is implemented on the current ref as optional runtime ingestion and validation for those contracts. The packaged fixture under `src/hocrgen/data/benchmark/benchmark_v1/reference_manifest.json` exercises reviewed, draft, and unavailable reference states with stable `reference_id` values. `build-release` validates reference-manifest, transcription-reference, and layout-reference shapes; rejects non-portable absolute, `file://`, `.work`, backslash, and path-traversal paths; checks benchmark item/source/split linkage; copies validated child reference files into the build artifact tree; verifies layout asset path/checksum/dimension linkage against current normalized assets; emits `benchmark_reference_manifest.json`, `benchmark_reference_status.json`, and `benchmark_reference_versioning.json`; and mirrors those artifacts plus selected child reference files through `export-alpha` for exported benchmark items. This does not make transcriptions or layout labels mandatory for current public or alpha outputs and does not change `benchmark_v1` membership. The separate F1e benchmark/holdout leakage gate now handles accepted overlap resolutions; neither F1e nor F2b is public beta/export readiness completion.

### Exit criteria
- benchmark examples can be tied to stable references rather than only image/manifests
- annotation/reference corrections have an auditable process
- benchmark versioning distinguishes fixed public examples from corrected or retired examples

### Risks / dependencies
- annotation quality and adjudication capacity may become the main bottleneck
- benchmark scope may expand faster than the number of trustworthy references

---

## Milestone F3 — Modern handwritten acquisition program

### Objective
Address the largest content gap: rights-clean modern handwritten Hebrew that matches the intended dataset identity more directly than historical public-source exemplars.

### Scope
- consent and contributor-release workflow
- institutional or project-owned collection policy
- scanning/upload standards for handwritten pages
- contemporary privacy and takedown handling
- demographic, script-style, page-type, and mixed-language composition targets
- bounded operator acquisition and review workflow

### Planned PRs
- `F3a`: define rights-clean modern handwritten Hebrew collection policy, consent, privacy, and takedown workflow (completed on the current ref)
- `F3b`: implement operator workflow for bounded modern handwriting acquisition and review

### Current-ref implementation
`F3a` is the policy foundation. It establishes contributor consent, public-use release terms, rights provenance, contemporary privacy screening, takedown/removal handling, scanning/upload standards, mandatory operator review, composition targets, and the boundary between modern real handwriting, historical public sources, and synthetic data.

`F3b` is implemented on the current ref as an operator-only manifest-backed workflow. It adds the `HEOCR-CONSENT-OPEN` normalized license, validates typed modern intake manifests during config validation and source health, maps valid records through a `modern_handwriting_intake` source adapter, and makes `requires_manual_review` effective in review export. It does not add a default modern handwriting source to existing profiles, package real contributor samples, add a public upload portal, or claim public beta readiness.

### Exit criteria
- modern handwritten samples can be collected through the F3b operator workflow without weakening privacy or rights posture
- collection targets are explicit enough to avoid drifting into a mostly historical dataset
- public-profile promotion remains gated separately from acquisition

### Risks / dependencies
- consent, privacy, and takedown obligations are heavier for contemporary material
- source diversity may be hard to achieve without institutional partnerships

---

## Milestone F4 — External synthetic provider integration

### Objective
Record and then integrate the synthetic spinout boundary without turning `hocrgen` into a generation engine. `hocrsyngen` owns synthetic Hebrew OCR/HTR generation. `hocrgen` consumes governed generated-sample manifests as candidate synthetic inputs, applies existing release gates, and exports either mixed real+synthetic releases to `HeOCR` or synthetic-only releases to `HeOCRsynth`.

### Scope
- four-repository ownership boundary across `hocrsyngen`, `hocrgen`, `HeOCR`, and `HeOCRsynth`
- narrow `hocrsyngen` `generation_manifest.json` contract with relative page assets
- fixture-backed provider ingestion before any live service, GPU, LLM, diffusion, or heavyweight generator dependency is allowed in `hocrgen`
- Hebrew logical-order text, RTL/bidi, Unicode normalization, niqqud, final-letter, numeral, punctuation, font-shaping, and layout-coverage validation gates
- synthetic provider metadata for generator version, recipe id, seed/provenance, license `PROJECT-SYNTHETIC`, synthetic disclosure, and optional persona/condition controls
- synthetic-only export handoff conventions for `HeOCRsynth`
- continued support for the old internal synthetic generator as legacy deterministic smoke coverage until it can be retired safely

Persona and condition fields are generator controls only. They must not claim psychological truth, real-writer identity, or demographic authority.

### Planned PRs
- `F4a`: record the four-repository synthetic spinout architecture and provider-boundary plan
- `F4b`: define and ingest the external `hocrsyngen` generated-sample manifest contract with fixture validation
- `F4c`: add deeper Hebrew rendering/provider metadata gates for `hocrsyngen` batches
- `F4d`: add synthetic-only export handoff for `HeOCRsynth`
- `F4e`: extract shared release export packaging primitives for alpha and HeOCRsynth release writers
- `F4f`: document the wider HeOCR ecosystem upstream chain (`public-domain-hand-written-hebrew-scans`, `hletterscriptgen`, `hletterscript`) that feeds `hocrsyngen` without changing runtime behavior, readiness gates, or release paths

### Current-ref implementation
`F4a` is implemented on the current ref as planning and documentation only. `F4b` adds fixture-backed hocrsyngen manifest ingestion. `F4c` hardens the hocrgen-side fixture/import boundary with required provider metadata, dependency-boundary flags, RTL/logical rendering metadata, Hebrew coverage validation, source-health signals, config validation, and synthetic composition reporting without redefining public hocrsyngen `generation_manifest.v1`. `F4d` adds `hocrgen export-synthetic`, a synthetic-only HeOCRsynth handoff path that selects release-ready `PROJECT-SYNTHETIC` items from existing hocrgen pipeline state, preserves synthetic disclosure and hocrgen-side provider/rendering/Hebrew coverage metadata for hocrsyngen-backed items, writes payload assets under `data/synthetic/<split>/<item_id>/`, and keeps mixed `HeOCR` `export-alpha` releases distinct. `F4e` extracts shared release export packaging primitives into `hocrgen.package.common` so alpha and HeOCRsynth exporters share release-relative portable payload shaping, stats, review/audit payloads, benchmark/reference filtering, release diffs, changelog rendering, and standard manifest/doc writing while retaining separate mixed `HeOCR` and synthetic-only release policy. F4d/F4e do not add acquisition code, hocrsyngen runtime calls, new hocrgen generator dependencies, or changes to current mixed public/alpha selection behavior. `F4f` is implemented on the current ref as documentation only. It records the wider HeOCR ecosystem upstream chain that surrounds the original `F4a` four-repository spinout boundary: `public-domain-hand-written-hebrew-scans` is the upstream rights-clean modern-handwriting page-scan corpus (per-scan rights evidence in `data/index/entries.jsonl`), `hletterscriptgen` is the framework that crops those scans into per-letter glyph variants under the `letter_set.v1` contract, and `hletterscript` is the per-writer glyph-image dataset that ultimately feeds `hocrsyngen` synthetic page composition. `F4f` is recorded in [`heocr_ecosystem_overview.md`](./heocr_ecosystem_overview.md), the README, the synthetic asset contribution guide, the `.agent-plan.md` summary, and the design/spec discussion of the synthetic provider boundary. It does not change `project_synthetic`, `build-release`, `export-alpha`, `export-synthetic`, `export-public-beta`, `hocrgen hocrsyngen-preflight`, the `hocrgen_hocrsyngen_import_metadata_packet.v1` contract, any source-adapter contract, the public beta readiness report, the blocker-closure plan, the repo-owned blocker report, the source-depth/composition report, takedown/private reporting evidence, or any synthetic cap, profile, or release gate. hocrgen does not import code from `public-domain-hand-written-hebrew-scans`, `hletterscriptgen`, `hletterscript`, or `hocrsyngen`, does not call upstream CLIs from default release/export commands, and does not re-validate upstream rights, glyph extraction, or per-image checksums; those responsibilities stay upstream and are inherited as per-item rights/provenance disclosure through the existing hocrgen item manifests.

### Exit criteria
- `hocrsyngen` output is treated as candidate synthetic input, not release-ready data by itself
- `hocrgen` can validate generated-sample fixtures without importing heavy generator dependencies or calling a live service
- synthetic caps, rights/provenance disclosure, review gates, benchmark gates, split/dedupe behavior, and export portability still apply before any mixed or synthetic-only publication
- `HeOCR` and `HeOCRsynth` release streams are distinguishable and do not confuse synthetic-only data with real-source provenance

### Risks / dependencies
- hocrgen could inherit generator complexity unless the manifest boundary stays narrow and fixture-backed
- high-quality Hebrew rendering may require optional system libraries or carefully bounded fallbacks in `hocrsyngen`, but baseline hocrgen CI must stay no-GPU and network-free
- synthetic-only publication could be mistaken for mixed-dataset readiness unless `HeOCRsynth` release cards and hocrgen export gates keep provenance explicit
- layout realism can grow complex quickly if it tries to mimic full document understanding datasets too early

---

## Milestone F5 — Public beta and publication readiness

### Objective
Only after F1-F4 gates are credible, define and implement the public beta/export path for a larger real+synthetic dataset and benchmark handoff.

### Scope
- public beta readiness gates over source depth, uniqueness, ground truth, review, privacy, and portability
- dataset-card and license/rights summaries
- release-relative checksums, archives, and manifest packaging
- publication handoff to the separate `HeOCR` dataset repo or external dataset host
- rollback, takedown, and changelog workflow for public beta versions

### Planned PRs
- `F5a`: define public beta readiness gates over source depth, uniqueness, ground truth, review, and portability
- `F5b`: implement public beta publication packaging and handoff workflow
- `F5c`: close public beta readiness blocker sequencing and repo-owned handoff gaps
- `F5d`: close repo-owned public beta readiness gates before external scale inputs

### Current-ref implementation
`F5a` is implemented on the current ref as a documentation and governance contract. `F5b` is implemented on the current ref as `hocrgen export-public-beta`, a deliberate local mixed `HeOCR` public beta packaging workflow. It runs `build-release`, writes `manifests/public_beta_readiness_report.json` with explicit `gate_id`, `status`, `evidence_paths`, and `rationale` fields, emits `manifests/checksum_manifest.json` and `manifests/archive_manifest.json`, creates a portable `tar.gz` archive rooted at the versioned release directory, verifies asset/archive digests from the handoff tree, and generates beta-specific dataset card, provenance, changelog, release notes, benchmark card, and handoff notes. `F5c` adds `manifests/public_beta_blocker_closure_plan.json` and `src/hocrgen/config/public_beta.yaml`, so the blocked handoff now separates repo-owned blockers from external/input-dependent blockers and reports whether the private takedown/reporting path has been configured. `F5d` adds `manifests/public_beta_repo_owned_blocker_report.json`, which records unresolved review/privacy item ids and reasons, benchmark-reference readiness by item/status/adjudication state, and the latest private-reporting repository-settings check before external scale inputs are available. It does not publish to `HeOCR`, Hugging Face, Kaggle, or `HeOCRsynth`, does not emit a publication report while any gate is `blocked`, does not change current `export-alpha` or `export-synthetic` behavior, and does not relax rights, privacy, review, dedupe, split, benchmark, synthetic-cap, or export-portability gates. Source-depth gates also remain blocked until real input evidence exists.

### Operator trial success versus public publishability
A successful F1c operator trial is necessary evidence for scale, but it is not sufficient for public beta publication. Operator trial artifacts may prove that candidate acquisition can run through gates; public publishability additionally requires release-facing documentation, benchmark-reference status, portability evidence, archive/checksum behavior, removal/takedown process readiness, and no unresolved source, rights, privacy, review, duplicate, leakage, benchmark, or synthetic-scale blockers.

The current known blocker remains: full synthetic target scale still requires a larger validated hocrsyngen batch. The current F1c hocrsyngen artifacts are operator-only scale-trial inputs, not public beta readiness evidence for the planned synthetic-control target.

### Public beta readiness gates
The mixed `HeOCR` public beta candidate set must satisfy all gates in the matrix below before publication. F5b turns this matrix into a machine-readable `public_beta_readiness_report.json` with one row per gate, the source artifacts used for evidence, a `pass` or `blocked` status, and a short rationale. F5c derives `public_beta_blocker_closure_plan.json` from that report, categorizing blocked gates as `repo_owned_immediately_actionable` or `external_input_dependent` and naming required closure artifacts/actions. F5d adds `public_beta_repo_owned_blocker_report.json`, which gives the repo-owned blockers enough structured evidence to act on without treating unresolved gaps as solved. F6e adds `public_beta_source_depth_composition_report.json`, which records public-profile source-depth/composition evidence separately from F1c/operator-only/source-depth-only inventory. Public beta publication must not proceed with any `blocked` gate.

| Gate | Required evidence artifacts | Pass state | Blocker examples | F5b enforcement expectation |
| --- | --- | --- | --- | --- |
| Source depth and composition | `discover/source_depth_feasibility.json`, `build_release/f1_target_scale_trial_report.json`, `build_release/source_stats.json`, public candidate/item manifest | Real candidate depth is backed by committed or cached deterministic source evidence; the planned F1 allocation is met or deliberately superseded in the roadmap; source-depth-only fixtures appear in public payload only after normal profile/review promotion | Missing source-depth report, source-health-ineligible records counted as public depth, source-depth-only fixtures copied directly to payload, composition docs omit real/synthetic/source mix | Fail the readiness report when required counts, source-health eligibility, or source-family composition evidence is missing or inconsistent |
| Synthetic target scale and cap policy | hocrsyngen `generation_manifest.v1`, source-health hocrsyngen batch checks, synthetic composition report, release summary cap fields | Planned synthetic-control target is backed by a larger validated hocrsyngen batch plus a settled hocrgen-owned provider/rendering/Hebrew metadata form; selected synthetic items stay within active public-profile/export caps | Current `2 / 80` fixture batch used as readiness evidence, missing hocrgen-owned provider/rendering/Hebrew metadata, synthetic cap exceeded, synthetic volume used to mask real-source gaps | Fail until the larger validated hocrsyngen batch and hocrgen-owned import metadata form are configured and the selected synthetic payload passes cap checks |
| Rights and provenance | `policy_filter/accepted_items.json`, `review_merge/release_ready_items.json`, public `manifests/item_manifest.json`, `docs/PROVENANCE.md`, dataset card rights section | Every public item has normalized release-compatible rights, raw source/provider/consent evidence, stable source ids, required attribution, and no unresolved rights-review state | Unknown/restricted rights in payload, missing attribution, missing consent/provider provenance, unresolved rights-review item | Fail on any public payload item without release-compatible rights/provenance evidence |
| Privacy and review closure | `privacy_scan/summary.json`, `review/queue.json`, `review_merge/unresolved_items.json`, `review_merge/rejected_items.json`, `build_release/blocked_items.json`, `build_release/review_required_items.json` | Public payload excludes review-required, blocked, unresolved review, unresolved privacy, unresolved modern-handwriting consent, and unresolved takedown/removal states | Unresolved review item in payload, blocked item copied as data, modern handwriting without consent/privacy clearance, takedown item still selected | Fail if any non-release-ready review/privacy/takedown state reaches public payload |
| Duplicate, source-group, split, and benchmark/holdout leakage | `dedupe/duplicate_clusters.json`, `dedupe/duplicate_relations.json`, `split/split_manifest.json`, `split/leakage_report.json`, `build_release/benchmark_leakage_risk.json`, benchmark accepted resolutions | Exact duplicates are removed deterministically; near-duplicate, source-group, split, synthetic-sibling, and benchmark/holdout risks are clear or resolved by typed repo-tracked accepted resolutions matching current detected groups | Stale accepted resolution, unresolved benchmark/holdout overlap, source group split across train/validation/test, near-duplicate risk left as warning only | Fail on unresolved or stale leakage risk, including benchmark/holdout overlap |
| Benchmark and benchmark-reference readiness | `build_release/benchmark_manifest.json`, `build_release/benchmark_reference_manifest.json`, `build_release/benchmark_reference_status.json`, `build_release/benchmark_reference_versioning.json`, `docs/BENCHMARK_CARD.md` | `benchmark_v1` membership is stable, release-ready, split-compatible, and accompanied by reference status/versioning artifacts; unavailable or draft references are explicitly disclosed as limitations | Benchmark member missing from run, split mismatch, silent benchmark membership change, missing reference status, docs imply complete ground truth when coverage is partial | Fail on unstable benchmark membership or missing reference/status/versioning artifacts; require docs to disclose reference coverage |
| Annotation expectations | `build_release/annotation_manifest.json`, `build_release/annotation_pilot_manifest.json`, benchmark child references, dataset card annotation section | Full transcription/layout labels are not mandatory for every public beta item under F5a; any shipped annotation, pilot, transcription, or layout reference is release-relative, checksum-linked where applicable, and status-labeled | Annotation path is absolute, pilot target not release-ready, draft reference presented as reviewed, docs imply complete annotations | Fail on non-portable or mislabeled annotation/reference artifacts |
| Portability, checksums, and archive | `manifests/release_record.json`, `manifests/release_summary.json`, `manifests/item_manifest.json`, `manifests/release_diff.json`, F5b checksum manifest, F5b archive manifest, generated release archive | Public paths are release-relative; no absolute paths, `file://`, `.work/`, path traversal, or network-only assumptions exist; every payload asset and release archive has a SHA-256 digest recorded in a manifest | Local path leakage, missing asset digest, archive digest mismatch, archive contains files outside the release root, reproducibility depends on live network | Fail on portability scan errors, missing SHA-256 digests, or archive verification mismatch |
| Public documentation | `docs/DATASET_CARD.md`, `docs/PROVENANCE.md`, `docs/CHANGELOG.md`, `docs/RELEASE_NOTES.md`, `docs/BENCHMARK_CARD.md`, `docs/HANDOFF.md` | Docs describe composition, source mix, synthetic fraction, rights/attribution posture, benchmark/reference status, annotation status, validation performed, known limitations, and blockers | Dataset card omits synthetic fraction, provenance omits source/provider evidence, changelog omits removals, validation not recorded | Fail if required docs are missing or omit required public-beta sections |
| Takedown/removal readiness | `docs/RELEASE_NOTES.md`, `docs/CHANGELOG.md`, release diff/removal manifests, PR body, public/private reporting path documentation | A public and private intake path exists for rights, privacy, source-owner, takedown, correction, and source-breakage concerns; removals flow through review/config/source-status changes and are reflected in diffs, changelogs, notes, and PR metadata where disclosure is safe | No private reporting path, removal not reflected in release diff, takedown item remains public, sensitive rationale exposed publicly | Fail if reporting path or release-to-release removal audit is missing |

### Publication non-goals and blockers
F5a/F5b explicitly do not:

- perform repository sync, upload, release tagging, or blocked publication-report emission
- publish or copy a public beta tree to `HeOCR`, Hugging Face, Kaggle, or another public host
- publish synthetic-only data to `HeOCRsynth` beyond the existing dry-run/handoff behavior already covered by `export-synthetic`
- make F1c operator trial outputs public beta artifacts
- make transcriptions or layout labels mandatory for all current public-profile items
- relax alpha export caps, synthetic-only export gates, benchmark gates, review gates, or portability checks

F5c/F5d explicitly do not turn blocker-closure reports into readiness. The `2 / 80` hocrsyngen synthetic target-scale evidence remains blocked until a larger validated batch exists, source-depth composition remains blocked until real input evidence exists, and repo-owned privacy/review, benchmark-reference, and takedown actions must still produce passing evidence before publication.

The public beta must remain blocked if any readiness gate above is unresolved, if the synthetic target-scale hocrsyngen batch remains too small, if benchmark/holdout leakage resolutions are missing or stale, if public docs do not disclose composition and known limitations, or if takedown/removal contact and audit workflow are not ready.

### Exit criteria
- public beta export is a deliberate release decision, not an accidental side effect of operator acquisition
- publication artifacts include enough rights, provenance, checksum, benchmark, and takedown context for external users
- final publication does not introduce local-path leakage or network-dependent reproducibility assumptions
- F5b remains clearly scoped to local packaging and blocked handoff verification, not final repository sync, upload, tagging, or hosting publication
- F5d keeps repo-owned blocker closure evidence precise while preserving source-depth and synthetic target-scale blockers until real inputs exist

### Risks / dependencies
- publication pressure could arrive before benchmark references and uniqueness controls are credible
- storage, hosting, and takedown workflows may need decisions outside this repository

---

## Milestone F6 — Public beta closure and external input integration

### Objective
Turn the blocked F5 public beta handoff into a concrete closure sequence that separates repo-owned fixes from external/input-dependent scale evidence. F6 is a post-F5 closure milestone in the public-beta track, not a new publication phase and not part of the hocrsyngen generator spinout. It exists because `export-public-beta` now reports the blocker set precisely, but reporting a blocker is not the same as closing it.

### Scope
- planning-only roadmap definition for the post-F5 closure path
- verified takedown/private reporting readiness when maintainer action or an alternate private channel exists; blocked while that evidence is missing
- benchmark-reference readiness only through reviewed/adjudicated evidence, with partial or unavailable coverage disclosed as a blocker unless the readiness contract changes explicitly
- privacy/review closure only through repo-tracked review, config, or source-status changes
- source-depth/composition readiness only through real public-profile candidate evidence promoted through normal gates
- hocrsyngen installed-CLI adapter preflight planning through public JSON reports, public manifests, relative assets, asset hashes, and `template_catalog.v2`, before any release-path integration
- hocrgen-owned release/import metadata sidecar definition before any larger validated hocrsyngen batch is admitted to release paths, not through hocrsyngen private internals
- final public beta readiness rerun only after privacy/review closure, source-depth, and synthetic-scale inputs exist

### Planned PRs
- `F6a`: define post-F5 public beta closure roadmap
- `F6b`: close takedown/private reporting readiness with a verified private path
- `F6c`: close benchmark-reference readiness with reviewed/adjudicated evidence; otherwise preserve blocked limitation reporting
- `F6d`: close privacy/review blockers through review/config/source-status changes; otherwise preserve blocked limitation reporting
- `F6e`: close source-depth and composition readiness with real public-profile evidence
- `F6f1`: plan the hocrsyngen installed-CLI adapter preflight and diagnostic dry-run
- `F6f2a`: implement the hocrsyngen evidence-root preflight/import-packet reader
- `F6f2`: define the hocrgen-owned release/import metadata sidecar for validated hocrsyngen evidence roots
- `F6g`: re-run public beta readiness after privacy/review closure, source-depth, and synthetic-scale inputs exist

### Current-ref implementation
`F6a` is implemented on the current ref as a planning-only roadmap pass. It updates planning docs and planning consistency tests so the next work is no longer implicit after `F5d`. `F6b` is implemented on the current ref by recording verified GitHub private vulnerability reporting evidence for `HeOCR/hocrgen` in `src/hocrgen/config/public_beta.yaml`. It closes only the takedown/private reporting readiness gate; it does not publish or copy a public beta tree, does not change `export-alpha` or `export-synthetic`, and does not change benchmark-reference, privacy/review, source-depth/composition, or synthetic target-scale gate semantics. `F6c` is implemented on the current ref by evaluating the current benchmark-reference evidence and keeping `benchmark_references` blocked because only `1 / 3` selected benchmark items have reviewed/adjudicated references. It improves readiness and repo-owned blocker reporting so the limitation is precise and auditable rather than silently treated as readiness. `F6d` is implemented on the current ref by evaluating the current privacy/review evidence and keeping `privacy_review` blocked because review-required item evidence still has default-unresolved review decisions and no repo-tracked review/config/source-status closure evidence. It adds F6d limitation and source-status reporting to the repo-owned blocker report without changing alpha, synthetic, or public beta packaging side effects. `F6e` is implemented on the current ref by evaluating current source-depth/composition evidence and keeping `source_depth_composition` blocked because only `2 / 80` real public-profile payload candidates exist. It adds F6e limitation reporting to the readiness report, dedicated source-depth composition report, blocker plan, and blocker evidence report without changing alpha, synthetic, or public beta packaging side effects. `F6f1` is implemented on the current ref as planning only. It records that hocrsyngen S6 public CLI surfaces are suitable for an explicit operator-only adapter preflight, but raw public hocrsyngen `generation_manifest.v1` output is not yet the same as the current hocrgen hardened release-path manifest model because hocrgen still needs provider, rendering, and Hebrew coverage metadata in a hocrgen-owned import form. `F6f2a` implements the operator-only hocrgen reader for hocrsyngen evidence-run roots and writes a diagnostic report with `release_eligible: false`; it does not make the batch usable by public release paths. `F6f2` defines `hocrgen_hocrsyngen_import_metadata_packet.v1`, deriving provider identity/version, logical RTL rendering metadata, and Hebrew coverage metadata from validated evidence roots and validating the packet with a typed hocrgen-owned schema without mutating hocrsyngen `generation_manifest.v1`. Release/import model projection remains false unless the evidence root explicitly provides a validated provider-runtime contract for the no-network/no-REST/no-GPU/no-LLM/no-diffusion flags.

### Required sequencing
The F6 sequence is evidence-gated:

1. `F6b` can pass the takedown/private reporting gate only if GitHub private vulnerability reporting is enabled for the repository or another maintainer-private channel is configured with verification metadata. On the current ref, the GitHub private vulnerability reporting path is enabled and verified, so only `takedown_removal` closes.
2. `F6c` can close benchmark-reference readiness only when benchmark references have real reviewed/adjudicated artifacts and coherent status/versioning semantics. Partial, draft, or unavailable references may be disclosed as limitations, but those limitations do not pass the readiness gate unless a separate governance PR explicitly changes the public beta contract.
3. `F6d` can close privacy/review readiness only through repo-tracked review decisions, config changes, or source-status changes. On the current ref, the evidence is unresolved, so the privacy/review gate remains blocked. Review-required, blocked, unresolved privacy, modern-handwriting consent, and takedown states must not enter public payloads.
4. `F6e` can close source-depth/composition readiness only when real public-profile candidate evidence exists and source-depth-only records have passed normal profile, review, privacy, split, benchmark, and portability gates. On the current ref, the evidence is still insufficient, so the source-depth/composition gate remains blocked. Source-depth-only fixtures must not be copied directly into public payloads.
5. `F6f1` is planning-only and cannot close synthetic target scale. It can only define an operator-only preflight that calls installed hocrsyngen CLI JSON surfaces, validates public reports/manifests/assets/catalog joins, recomputes hashes, reports missing hocrgen-owned release/import metadata, and leaves raw hocrsyngen output out of the default release path.
6. `F6f2a` implements the evidence-root reader for that preflight evidence and cannot close synthetic target scale. It validates a hocrsyngen evidence-run root and emits an operator-only hocrgen diagnostic report with `release_eligible: false`.
7. `F6f2` settles the hocrgen-owned release/import metadata form for provider, rendering, and Hebrew coverage metadata as an operator-only sidecar/import packet. It cannot close synthetic target scale by itself, and the current `2 / 80` release-path evidence remains blocked until a larger validated batch is admitted through hocrgen gates.
8. `F6g` can run final public beta readiness convergence only after privacy/review closure, source-depth, and synthetic-scale release-path evidence exists. It must still leave the export blocked if any F5a/F5b gate fails.

### Non-goals
F6 does not:

- relax the public beta readiness gate matrix
- treat `public_beta_blocker_closure_plan.json` or `public_beta_repo_owned_blocker_report.json` as readiness evidence by themselves
- count source-depth-only fixtures as public payload without normal profile, review, privacy, split, benchmark, and portability gates
- replace the larger validated hocrsyngen batch with legacy in-repo synthetic generator output
- import hocrsyngen internals, call hocrsyngen commands from default release/export paths, use network services, or add GPU/LLM/diffusion dependencies to hocrgen
- require hocrsyngen to add hocrgen-owned release/import metadata fields to `generation_manifest.v1`
- publish to `HeOCR`, Hugging Face, Kaggle, or `HeOCRsynth` while any gate is blocked

### Exit criteria
- `F6a` leaves the roadmap with a concrete next PR sequence after `F5d`, including an explicit source-depth/composition PR before final readiness
- `F6b` closes the takedown/private reporting gate only with verified private reporting path evidence
- `F6c` keeps benchmark-reference readiness blocked when current reference evidence is partial, draft, unavailable, or unadjudicated, and records the item-level limitation in blocker reporting
- `F6d` keeps privacy/review readiness blocked when current review evidence is unresolved, and records the item-level limitation plus source-status evidence in blocker reporting
- `F6f1` records the hocrsyngen public CLI adapter-preflight design and the current release/import metadata gap without runtime behavior changes
- `F6f2a` reads hocrsyngen evidence-run roots into operator-only hocrgen diagnostics without changing release eligibility or default release/export paths
- `F6f2` defines and validates the hocrgen-owned import metadata sidecar without mutating hocrsyngen manifests or admitting the batch into release/export paths
- each remaining F6 PR has a narrow evidence requirement and a clear stop condition
- public beta remains blocked until all gates pass with real evidence
- external/input-dependent blockers remain visible rather than being hidden behind repo-owned documentation changes

### Risks / dependencies
- real public-profile source-depth/composition evidence must exist before `F6e`
- a larger hocrsyngen batch must be admitted through hocrgen release-path gates before synthetic target scale can pass
- `F6g` must not become a pressure valve for merging incomplete readiness

## Milestone F7 — Governed HASH real-handwriting source integration

### Objective
Admit `HeOCR/hash` (HASH, the Hebrew Archive of Scanned Handwriting; formerly `public-domain-hand-written-hebrew-scans`) as a governed real-handwriting source without weakening any rights, privacy, review, leakage, benchmark, or readiness gate. HASH is HeOCR-owned, rights-recorded per scan, and mostly 1900–1949 cursive handwriting, which the current NLI/Pinkas/BiblIA mix barely covers. F7 supplies evidence to `F6g`; it does not replace or relax it.

### Planned PRs
- `F7a`: define the HASH source proposal record, rights mapping, gate-impact analysis, and F7 notation (planning only)
- `F7b`: add a fixture-backed `hash` adapter with `review_only` sources outside `profile_open_v1`, a `PDM-1.0` license entry, source health, and rejection of `CC-BY-SA-3.0` and out-of-scope entries
- `F7c`: add an operator-only converter from human-attested HASH transcripts to `benchmark_transcription_reference.v1` and `benchmark_reference_manifest.v1`
- `F7d`: promote a first HASH tranche and reconcile the real-source composition contract
- `F7e`: propose `benchmark_v2` with adjudicated HASH references

### Current-ref implementation
`F7a` is implemented on the current ref as planning only. The proposal, rights mapping, privacy notes, fixture strategy, ground-truth boundary, and gate-impact numbers are recorded in [the F7 plan](../planning/tasks/f7-hash-source-integration.md) and source-proposal issue `HeOCR/hocrgen#89`. It does not change sources, profiles, licenses, review data, readiness semantics, or any export. `F7b` is implemented on the current ref as the `hash` fetcher over a pinned five-entry fixture snapshot of `HeOCR/hash` under `src/hocrgen/data/hash/snapshot/`, with two `review_only` sources (`hash_nli_any_use` normalized as `PD-IL`, `hash_public_domain` normalized as the new `PDM-1.0` license), privacy default `clear` (F7b shipped `needs_review`; cleared by the 2026-11-06 maintainer decision below), inclusion only in `profile_review_v1`, source-health snapshot/checksum/exclusion checks, `source_group_id`/`writer_group_id` metadata, and rejection of `CC-BY-SA-3.0`, non-Hebrew, partial-Hebrew, unverified-rights, and non-redistributable entries. It does not add HASH to `profile_open_v1`, read HASH transcripts or HTR candidates, or change any readiness gate.

**Maintainer decision, 2026-11-06: HASH needs no human privacy review.** In the maintainer's words: "no need for human to go over privacy; if that is a guideline or rule written somewhere, it is in error and you must remove it; these are all public domain, and everything there is about people who've been dead for decades." The per-page privacy review, the per-writer cap, the Senesh "written as a minor" review, and "review, then approve" for the Commons letters are removed. Both HASH privacy source defaults are `clear` and `requires_manual_review` is `false`. HASH stays `review_only` and outside `profile_open_v1` until `F7d` for non-privacy reasons only: the per-source composition contract, writer-group leakage governance, and vendoring the promoted tranche's assets. The rights facts (the `CC-BY-SA-3.0` rejection, the v1 scope filters) and the ground-truth boundary are unchanged.

### Required sequencing
1. `F7b` keeps HASH out of `profile_open_v1`, so it changes no readiness gate. Candidate HTR text under HASH `data/transcripts/candidates/` is never read.
2. `F7c` is planned. It needs human-attested HASH transcripts, and none exists yet: none of the 10 HASH `status: reviewed` transcripts meets the human-reviewed bar (4 began as GPT-4o output and 6 as Wikisource edition texts; all 10 were edited toward the page image in HASH `cf1d4d4` by an agent with no human reviewer recorded, so they remain unreviewed). A new human transcription campaign may supply them. **Maintainer decision, 2026-11-06:** the earlier "no new human transcription campaign" rule, taken from the agent-written "Maintainer decisions" text in the now-closed issue #86, is removed; in the maintainer's words: "I don't remember dictating that rule, and anyway if I did, I remove it; we will have many new human transcription campaigns in the future, if we're lucky." Until attested inputs exist, HASH text may appear only as `unreviewed` diagnostics in E2c evaluation. `F7c` accepts a transcript only with a HASH-side human attestation that names the reviewer, method, text checksum, and adjudication. HASH `status: reviewed` alone is insufficient, and HTR output is never ground truth.
3. `F7d` may add HASH items to `profile_open_v1` without per-item privacy review decisions (maintainer decision 2026-11-06). HASH items count toward `source_depth_composition` only after an explicit change to the per-source real target contract (`27` NLI / `27` Pinkas / `26` BiblIA). The tranche must also carry source-group and writer-group leakage metadata.
4. `F7e` must not change `benchmark_v1` membership. HASH references enter only through a versioned `benchmark_v2` proposal.

### Non-goals
F7 does not add live crawling or network-dependent CI. It does not admit `CC-BY-SA-3.0`, Yiddish, Aramaic, or partial-Hebrew HASH entries in v1, treat HTR or LLM output as ground truth, or count HASH inventory as public-profile evidence before `F7d` promotion. It also does not edit `hocrsyngen`, `hletterscriptgen`, or `hletterscript`.

### Exit criteria
- HASH is a typed, fixture-backed, source-health-visible source with explicit rights mapping
- every promoted HASH item has attribution/provenance
- HASH references are human-attested and adjudicated before any benchmark readiness claim
- `F6g` readiness reporting discloses HASH contribution per gate with real counts


## Milestone F8 — Real-source map and paired-text source intake

### Objective
Map real (non-synthetic) Hebrew document sources beyond HASH, ranked by what HeOCR lacks most: real page images paired with human-made text, printed and handwritten. F8 supplies the printed real-reference source that E2d leaves unselected. hocrgen currently holds zero human-transcribed real pages: the packaged `biblia_open` and `pinkas_open` sources are Commons images with no transcriptions.

### Planned PRs
- `F8a`: the real-source map, routine decisions, maintainer decision list, and F8 notation (planning only)
- `F8b`: a fixture-backed `review_only` Hebrew Wikisource proofread-page source paired with Commons scans, gated per Index on evidence that both the work (in Israel) and the scan are public domain
- `F8b2`: an operator-only inventory of every Wikisource Index and its quality-3/4 pages through the unchanged F8b gates, with a committed summary
- `F8b3`: resolve Wikisource evidence gaps (decisions 9-10, cited death years, a Hebrew language gate), extend the converter to every construct on admitted pages (decision 11), and record transcription coverage with `needs_crop` for partial pages (decision 12)
- `F8b4`: check Wikisource transcription coverage at scale with an operator OCR-alignment tool (OCR for localisation only, never as text), crop partial pages to the transcribed region in the pipeline (decision 12), pin labelled-section transclusions, and record the footnote marker style
- `F8b5`: resolve the Wikisource residuals after `F8b4`: an agent visual review of the `review_recommended` crops, the `crop_unresolved` pages and the undecided pages, with multi-region crops for interleaved untranscribed blocks; the `quality_attribute_mismatch` drops (editor renames); and cited evidence for the rights residual
- `F8b6`: resolve the Wikisource rights residual with cited evidence (team-lead decisions on the F8b5 questions, under decision 10): Korfu 1885 on two grounds, and the evidence file extended to creators, publication years and anonymous markers for four more Indexes; exclude pages whose text holds words the page does not show (`text_not_on_page`)
- `F8b7`: harden the Wikisource pairs (`HeOCR/hocrgen#130`, `#111`): find footnotes with no printed counterpart (tool footnote check by OCR boxes, agent review) and drop them from the pair text; map reviewed editor stand-ins to the printed character after conversion; keep text the scan hides in the reference but exclude it from primary scoring (`illegible_on_scan` spans); spot-check the Korfu `full_page` verdicts
- `F8c`: key the `nli` rights strategy on the IIIF manifest `license` slug and admit `public-domain-free-use` printed books
- `F8c2`: an operator-only inventory of NLI digitized printed Hebrew books by IIIF licence slug, to measure the free-use pool
- `F8d`: fixture-backed `review_only` imports of CC-BY-4.0 human ground-truth datasets (`pinkas_dataset_bgu`, then YidTakNL)
- `F8d2`: NLI-matched ground truth: admit `pinkas_dataset_bgu` once its scans match an NLI free-use record, and match more YidTakNL works page by page
- `F8d3`: per-line language tags for `pinkas_dataset_bgu` lines (maintainer decision 8), with advisory agent proposals for human review
- `F8d3b`: scope-neutral non-text Pinkas lines (digits, years, empty), classified from the pinned text, and full Hebrew scope for human-tagged Hebrew lines
- `F8e`: born-digital and typewritten government print (Reshumot, Knesset committee scans to 1975)
- `F8f`: an operator-only pilot that matches Project Ben-Yehuda public-domain texts to NLI `public-domain-free-use` scans of the same edition and aligns them page by page and line by line into silver pairs (OCR for localization only), with a side-by-side review report for a human verification pass
- `F8g`: promote the real F8 sources into the public path: a per-source composition contract with modality floors, work-group leakage governance with a synthetic-training cross-check, per-item release terms and NOTICE generation, and a reproducible out-of-git tranche with a committed manifest
- `F8g2`: harden the F8g tranche: size-aware, seeded whole-group split assignment per source and modality; per-page Pinkas canvas checks; a text-region crop height floor; confirmed empty YidTakNL texts; Reshumot and Knesset captures past the fixtures; `wikisource_plain_text.v3` and tranche v2

### Current-ref implementation
`F8a` is implemented on the current ref as planning only, in [the F8 plan](../planning/tasks/f8-real-source-map.md). The verification evidence is under [`2026_11_06_israeli_public_domain_documents_research/verification/`](./2026_11_06_israeli_public_domain_documents_research/verification/). It does not change sources, profiles, licences, review data, readiness semantics, scores, or any export. `F8d` is partly implemented on the current ref as the `yidtaknl` fetcher over a pinned three-entry fixture snapshot under `src/hocrgen/data/yidtaknl/snapshot/`: one `review_only` source, `yidtaknl_vaybertaytsh_gt` (`CC-BY-4.0`, `open_with_attribution`), privacy default `clear`, inclusion only in `profile_review_v1`, and source-health checks on asset and text checksums. Each page carries its page-level Transkribus text by reference and checksum, with language `yi`, evaluation scope `character_level_only`, and adjudication status `not_adjudicated`. Only pages whose scan carries the NLI `public-domain-free-use` licence are admitted; the HUC-scanned works are rejected. `pinkas_dataset_bgu` was not added in `F8d`: the dataset and its paper do not name the holding library or the photographer of the scans. `F8d2` is implemented on the current ref. The NLI Search API identified the scans as NLI Ms. Heb. 4°662 (record 990000445290205171, Ktiv project, IIIF licence `public-domain-free-use`), and dataset pages match halves of its canvases. It adds the `pinkas_dataset` fetcher and the `review_only` source `pinkas_dataset_bgu`: a two-page fixture with the upstream PAGE XML (gzipped), line polygons scaled to the thumbnail, languages `he` and `yi`, scope `character_level_only` and `not_adjudicated`. Scan rights for both datasets go through the F8c `decide_nli_rights` gate over pinned manifest captures. It also matches the YidTakNL 1747 and JB 899 works to NLI canvases page by page: 154 metadata-only pages pinned by upstream SHA-1, plus two more vendored pages. `F8d3` is implemented on the current ref ([the Pinkas source guide](./pinkas_dataset_source.md)). Each `pinkas_dataset_bgu` PAGE XML line can carry a typed language tag (`he`, `yi`, `mixed`, `unknown`; `human` or `agent_proposed`) in a reviewable sidecar. One function derives line scope: only a human `he` tag unlocks Hebrew evaluation for that line, and the page stays `character_level_only` while any line is not. The committed tags are all `agent_proposed` by a lexicon tool and are advisory, so every fixture line stays `character_level_only`. `F8d3b` makes lines with no Hebrew-script letter (page numbers, years, empty lines) scope-neutral, classified from the pinned text: they never get Hebrew scope and never keep a page from `full_hebrew`. It also gives human-tagged Hebrew lines full Hebrew scope, including language-level Hebrew evaluation (the maintainer's clarification of decision 8).

`F8b` is implemented on the current ref as the review-only `wikisource_he_proofread` source, documented in [the Wikisource source guide](./wikisource_proofread_source.md). It is included only in `profile_review_v1`, so `profile_open_v1` outputs are unchanged. `F8b2` adds the operator-only `hocrgen.tools.wikisource_inventory`, which runs all 141 Indexes through the same gates; the full pool stays outside the repo, and only [the summary](./wikisource_index_inventory.md) and its per-Index JSON are committed. `F8b3` applies maintainer decisions 9-12 to the same gates: missing Commons or Wikidata evidence is resolved (cited death years and Index languages in [the evidence file](./wikisource_index_evidence.json), a pre-1856 publication presumption), the Commons tag, scan source and Google digitization are provenance only, and an Index must be Hebrew. `wikisource_plain_text.v2` renders footnotes, tables, citations and the other constructs used on admitted pages, checked against MediaWiki's own `action=parse` rendering; only 13 labelled-section transclusion pages are left. Agent render checks record transcription coverage on 156 pages ([page checks](./wikisource_page_checks.json)); partial pages are marked `needs_crop` for `F8b4`. `F8b4` adds the operator-only `hocrgen.tools.wikisource_coverage`: Tesseract gives line boxes only (OCR text is never stored or used as text), the human text is aligned to them, and each page gets a tool check (`full_page` or `partial_page`, overridden by any agent or human check) and a crop of the transcribed region. A partial page now pairs its unchanged text with that crop, with the crop's geometry, method and provenance recorded and checked by source health; pages whose crop cannot be placed are `crop_unresolved` and listed. The 13 transclusion pages now convert, with the transcluded pages pinned by revision, and each page records `footnote_marker_style`. `profile_open_v1` and `benchmark_v1` are unchanged. `F8b5` resolves the residuals: a partial page whose transcribed text is interleaved with untranscribed blocks pairs with a multi-region crop, the regions' union box with everything outside the regions masked to the page background and the regions' own pixels unchanged (checked by source health); agent and human page checks may confirm, correct or place a crop themselves; an agent reviewed all 188 residual pages visually; a `<pagequality user=...>` attribute written before an editor's recorded rename now matches; and cited death years admit 4 more Indexes. `crop_unresolved` drops from 61 pages to 0 and undecided coverage from 74 to 1. `F8b6` resolves the rights residual: the evidence file can now add a creator the wikis do not name, correct creators parsed from free text (`not_a_creator`, `anonymous`), record a missing publication year and state additional grounds, all cited and read by the unchanged Index gate. Five more Indexes are admitted, led by the Korfu 1885 siddur (214 pages). Pages whose text holds words the scan page does not show, such as an editor's paraphrase, note or placeholder, are excluded as `text_not_on_page` and listed.

`F8c` is implemented on the current ref. The `nli` fetcher reads an optional pinned IIIF manifest capture per seed and keys rights on its `license` slug: only `public-domain-free-use` maps to `PD-IL` / `open`, and non-commercial slugs, other slugs, slug/display-string disagreements, zero-canvas manifests and HTTP 403/500 manifests are rejected with explicit reason codes and listed in source health. Three hand-vetted `printed_historical` book seeds are cached in the exploratory seed catalog, so the runnable seeds and the 27 / 27 / 26 real-source allocation are unchanged. The Search API key is used only by an operator discovery tool that reads it from the environment.

`F8c2` is implemented on the current ref as the operator-only `hocrgen.tools.nli_printed_inventory`. It samples Search API result pages for digitized printed Hebrew books and decides each manifest with the unchanged F8c gate; multi-volume manifests are gated per volume, as in `F8d2`. The committed summary is [`nli_printed_inventory.md`](./nli_printed_inventory.md), with per-book JSON. It changes no seed, source, profile, composition or gate.

`F8e` is implemented on the current ref as two `review_only` sources over pinned fixture snapshots, both `PD-IL` / `open`, privacy default `clear`, and included only in `profile_review_v1`. `reshumot_born_digital` (fetcher `reshumot`) admits ספר החוקים and קובץ התקנות pages from 2006 on: a page image rendered from the born-digital PDF (`is_scan: false`, with renderer, version and dpi), plus the embedded text converted to logical order and checked by `hocrgen.parsers.pdf_bidi`; pages that fail the check are rejected. `knesset_committee_protocols_pre1976` (fetcher `knesset_committee`) admits page scans of committee protocols from sessions on or before 1975-12-31 under the new `typewritten_historical` content type, images only; later sessions and committee background material are rejected.

`F8f` is implemented on the current ref as the operator-only `hocrgen.tools.benyehuda_nli_alignment`, summarized in [the alignment pilot](./benyehuda_nli_alignment_pilot.md). Edition matching searches NLI for 45 candidate editions named by the Project Ben-Yehuda catalogue and gates each hit with the unchanged F8c `decide_nli_rights`: 11 match a `public-domain-free-use` scan with canvases, and most nineteenth-century editions are Google class. Alignment chains unique letter n-grams between the PBY text and Tesseract lines (OCR for line boxes only, never as text) and crops each page to its located region (decision 12). 277 pages of 10 works on 2 scans are aligned, 275 at high quality. Every pair is silver: `human_typed_edition_text_aligned`, `not_adjudicated`, `reference_eligible: false`, pending a human verification pass. No source, profile, composition or scoring change.

`F8g` is implemented on the current ref, documented in [the real-source release contract](./real_source_release_contract.md). `real_source_composition.v2` (`config/real_source_contract.yaml`) replaces the 27 / 27 / 26 allocation in the public-beta `source_depth_composition` gate with per-source floors and caps and printed / handwritten floors; the five F8 source ids are `allowed` in `profile_open_v1`, and the three cached F8c printed books are runnable NLI seeds. Every export carries typed per-item `release_terms`, the paired human text, `docs/NOTICE.md` and `manifests/attribution_manifest.json`. Split assignment joins source groups, work groups (`nli_record`, `commons_file`, `writer`) and duplicate clusters into whole components, and the synthetic-training registry keeps matching works in train. The 1,610-page tranche is materialized outside git by `hocrgen.tools.real_tranche` and read with `--real-tranche-root`; on it the composition gate passes (95 counted / 80), while the synthetic-scale, privacy-review (4 legacy items), benchmark-reference and takedown gates stay blocked. Hosting is proposed, not decided. `F8g2` hardens it: splits are size-aware (`size_aware_group_split.v1`, 81 / 9 / 10 on the tranche), Pinkas canvas bindings are checked per page (6 / 30 verified while NLI's image server is down), short text-region crops ship, Reshumot and the Knesset protocols grow to 182 and 205 pages, and the Wikisource converter is `wikisource_plain_text.v3`; tranche v2 holds 1,995 pages (composition 105 / 80).

### Required sequencing
1. Every new F8 source id (`F8b`, `F8d`, `F8d2`, `F8e`) starts `review_only` and outside `profile_open_v1`; promotion is a later explicit PR (`F8g`). `F8c` instead extends the existing `allowed` `nli_any_use_permitted` source, so its new printed items reach `profile_open_v1` only through that source's seed vetting and normal gates, with only `public-domain-free-use` mapped to `open`.
2. Text becomes a reference only through F2 reference manifests after human attestation and adjudication. OCR and HTR output is never ground truth, and `benchmark_v1` membership stays frozen.
3. Maintainer decisions of 2026-11-06 ([decision record](../planning/decisions/2026-11-06-f8-real-source-decisions.md)) accept CC BY-SA Wikisource text and quality-4 proofreading as human attestation, allow automated access to government sites, and limit printed Yiddish to training and character-level evaluation. HebrewBooks-sourced Commons scans are accepted under the same per-file rights check.
4. `F8e` throttles hard. Knesset committee protocols from 1976 on stay excluded until a legal opinion arrives.

### Non-goals
F8 does not add live crawling or network-dependent CI, admit non-commercial or `PD-US`-only material to `profile_open_v1`, use mr.gov.il tender pages, add a privacy-review gate for public-domain historical sources, or edit HASH.

### Exit criteria
- at least one printed and one handwritten real source carries human-made page text through a typed, fixture-backed, source-health-visible source
- every F8 source has explicit rights mapping and per-item rights evidence
- E2d can name its printed real-reference source

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
- beta-readiness gates for larger real+synthetic acquisition
- synthetic generation package boundary and provider-contract planning

Likely milestones:
- E1, E2, E3, E4
- F1, F2
- early F3/F4 planning

Outcome:
- the project becomes a durable ecosystem asset rather than only an internal pipeline
- larger beta-scale work has source-depth, uniqueness, and benchmark-reference gates

---

## Version line 1.x+ — Public beta and broader publication posture
Focus:
- modern handwritten collection maturity
- external synthetic-provider integration and Hebrew rendering/layout quality
- public beta publication packaging
- durable dataset hosting and takedown readiness
- synthetic-only publication stream for `HeOCRsynth`

Likely milestones:
- F3, F4, F5, F6
- cross-repository `hocrsyngen` and `HeOCRsynth` milestones

Outcome:
- the project can publish a larger real+synthetic dataset and benchmark without confusing operator trial artifacts with public release payloads
- public benchmark claims are backed by references, leakage controls, and documented composition limits
- synthetic-only releases are published as synthetic-only artifacts from `hocrgen` export handoffs, not ad hoc generator dumps
- post-F5 closure work is sequenced by real evidence rather than by documentation wording or relaxed gates

---

## Cross-repository synthetic generation stream

`F4a` intentionally names work that will happen outside `hocrgen` so future implementation threads do not collapse all synthetic work back into this repository.

### `hocrsyngen` generator package
- `G0a`: bootstrap the Python package, CLI, typed models, JSON schema, deterministic seed policy, no-GPU CI, and tiny fixture batch
- `G1a`: define and validate the `generation_manifest.json` contract with relative assets and stable sample identifiers
- `G2a`: add deterministic Hebrew renderer fixtures for logical-order UTF-8 text, RTL/bidi behavior, final letters, numerals, punctuation, and sparse niqqud
- `G3a`: add document-layout families and generator metadata coverage without requiring a REST service
- `G4a`: add persona/condition controls as generator controls only, without claims about real writer identity or psychological truth
- `G5a`: add handwriting/allograph-style generation and evaluation fixtures
- later optional work: ML, diffusion, LLM-assisted text generation, Arabic support, or service deployment only after the baseline manifest/API contract is stable

### `hocrgen` provider integration
- `F4b`: codify and consume the expected generated-sample contract through a fixture-backed manifest adapter under the same gates as `project_synthetic`
- `F4c`: add deeper Hebrew rendering/provider metadata gates for validated hocrsyngen batches
- `F4d`: add synthetic-only export handoff behavior for `HeOCRsynth`

### `HeOCRsynth` dataset repository
- `S0a`: bootstrap release layout, dataset-card/provenance conventions, and publication non-goals for synthetic-only releases
- `S1a`: accept the first dry-run synthetic-only release tree from `hocrgen`

`HeOCRsynth` must accept hocrgen-exported release trees from `hocrgen export-synthetic`, not raw generator directories. Synthetic-only release payloads are visibly rooted under `data/synthetic/`, carry `dataset_id: HeOCRsynth` and `release_kind: synthetic_only`, preserve `PROJECT-SYNTHETIC` licensing and hocrsyngen metadata, and exclude real-source items from payload and audit manifests. `HeOCR` remains the mixed real+synthetic public dataset repository.

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
21. F1 — operator-only beta-scale acquisition trial and uniqueness gates
22. F2 — benchmark ground-truth foundation
23. F3 — rights-clean modern handwritten acquisition program
24. F4a — record synthetic spinout architecture and provider boundaries
25. hocrsyngen G0/G1 — bootstrap generator package and manifest contract fixtures
26. F4b/F4c — define and ingest fixture-backed synthetic provider manifests
27. HeOCRsynth S0/S1 and F4d — bootstrap synthetic-only release stream and hocrgen handoff
28. F5 — public beta/export publication readiness
29. F6 — public beta closure and external input integration

This order emphasizes public-release safety before scale and polish before aggressive expansion.

---

# Milestone dependency notes

## Hard dependencies
- B5 depends on B1, B2, B3, B4
- C5 depends on A2 and partial C4
- D1 depends on a stable enough B5/C1-C2 foundation
- D3 depends on C2, C3, C4, C5, C6
- E3 depends on D5
- F1 depends on E2b, D2, D3, D4b, D5, E3, and E4 remaining intact
- F2 depends on D5, E2a, E3, and F1 composition/eligibility evidence
- F3 depends on rights, privacy, review, and takedown governance from B4/C4/C5/E4
- F4b depends on F4a and a stable `hocrsyngen` manifest-contract decision
- F4c depends on F4b's fixture-backed `hocrsyngen` manifest ingestion without network, GPU, REST, LLM, diffusion, or heavyweight generator dependencies
- F4d depends on F4c and an initialized `HeOCRsynth` release-repository layout
- F5 depends on credible F1-F4 gates, not just successful item acquisition
- F6 depends on F5 blocker reporting remaining truthful; `F6e` depends on real public-profile source-depth/composition evidence, `F6f1` depends on hocrsyngen S6 public CLI handoff evidence and hocrgen-side adapter planning, `F6f2a` depends on hocrsyngen evidence-run roots remaining public-boundary evidence, and `F6f2` depends on hocrgen deriving and validating a hocrgen-owned release/import metadata sidecar without mutating hocrsyngen manifest v1 or changing release eligibility

## Soft dependencies
- C3 can start before C5, but review hooks become more valuable once C5 exists
- D4 can progress in parallel with D1/D2 once synthetic asset governance is stable
- E2 can begin once D3 exists, even before E1 is fully mature
- F4 planning and provider-contract work can begin in parallel with F1/F2 if it stays deterministic and does not weaken release/export gates
- hocrsyngen generator work can proceed independently, but hocrgen should not consume it until the manifest contract and fixtures are stable
- F6b now has verified private-reporting evidence, F6c has current benchmark-reference limitation reporting, F6d has current privacy/review limitation reporting, F6e has current source-depth/composition limitation reporting, F6f1 has hocrsyngen installed-CLI adapter preflight planning, F6f2a has an operator-only hocrsyngen evidence-root reader, and F6f2 has a hocrgen-owned import metadata sidecar; F6g should wait for privacy/review closure plus real source-depth and synthetic-scale release-path inputs

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

## Risk 6b — hocrgen absorbs generator complexity through the spinout
### Mitigation
Keep hocrgen dependency-light. The first integration reads fixture-backed `hocrsyngen` manifests and relative assets; it does not call a REST service or require GPU, LLM, diffusion, or heavyweight generator dependencies.

## Risk 7 — Beta-scale acquisition is mistaken for benchmark readiness
### Mitigation
Keep F1 operator-only and require F2 benchmark ground truth, F1d leakage controls, and F5 publication gates before public beta claims.

## Risk 8 — Historical/open sources crowd out modern handwritten identity
### Mitigation
Treat F3 modern handwritten acquisition as a separate milestone with consent, privacy, composition, and takedown requirements.

## Risk 9 — Synthetic-only releases are mistaken for real-source provenance
### Mitigation
Publish synthetic-only data through `HeOCRsynth` with explicit generator provenance, `PROJECT-SYNTHETIC` licensing, synthetic disclosure, and hocrgen export metadata. Mixed releases in `HeOCR` must continue to distinguish real items from synthetic controls.

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

## End of Phase F
- beta-scale acquisition has been tested as operator-only artifacts before public export
- near-duplicate and split-leakage risks are surfaced before scaling
- benchmark references have guidelines and an adjudication path
- modern handwritten acquisition has a rights-clean route
- external synthetic-provider work has a manifest contract, fixture-backed ingestion path, and Hebrew rendering/provider metadata gates
- synthetic-only publication through `HeOCRsynth` is separated from mixed real+synthetic `HeOCR` readiness
- public beta publication waits for source-depth, uniqueness, ground-truth, review, and portability gates
- post-F5 public beta closure has a sequenced F6 roadmap and does not treat blocker reports as gate passes

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
5. source-depth, uniqueness, and leakage controls before beta-scale claims
6. rights-clean modern handwritten Hebrew acquisition as a first-class content stream
7. Hebrew-specific synthetic rendering/layout quality before synthetic volume claims
8. governance and documentation as first-class project outputs

The project reaches maturity when it can repeatedly and transparently produce useful public Hebrew OCR dataset releases while maintaining a conservative legal posture, a clear dataset identity, and sustainable maintenance practices.

## E2c — Reference-aware evaluation

E2c extends the completed E2 utility foundation without changing benchmark readiness or release policy. `E2c1` defines the contract and `E2c2` implements reference-aware scoring and literal diagnostics on the current ref, including an explicitly unreviewed diagnostic path for plain-text pairs. `E2c3` adds versioned normalization profiles (`raw.v1`, `nfc.v1`, headline `primary.v1`, `consonantal.v1`, report-only `punct_folded.v1`), per-stratum aggregates, and a labelled `alignment_masked` diagnostic for unscoped full-page predictions on the current ref. `E2c4` adds an offline `evaluate-references` CLI over heocr-engine prediction files on the current ref. It derives sha256-based page mappings, scores only synthetic gold and reviewed+adjudicated references, keeps HASH text as `unreviewed` diagnostics (the issue #86 tender-page source was closed on 2026-11-06 as unusable), compares two prediction sets with per-stage ΔCER, and emits a `hocrgen_reference_evaluation_run.v1` run record. `E2c5` adds an explicit `--diagnostic-only` mode on the current ref that scores unreviewed text with no scored set, refuses scored-set inputs, marks the run `benchmark_ready: false`, and reports baseline deltas only under `diagnostic_comparison`. The contract, engine boundary, acceptance criteria and limitations are in [the E2c plan](../planning/tasks/e2c-reference-aware-evaluation.md). No benchmark evidence or release gate is changed.

## E2d — Real-scan evaluation direction

**Direction (maintainer decision 2026-11-06); `E2d1`, `E2d2`, `E2d3`, `E2d3b`, `E2d3c`, `E2d3d`, `E2d3e`, `E2d4` and `E2d6` implemented on the current ref, `E2d5` planned.** Evaluation should eventually run on real scanned text only, printed and handwritten, with no synthetic text in the eval set. Printed Hebrew and handwritten Hebrew get separate evaluation tracks, and possibly separate pipelines. These are modality tracks, distinct from the existing open/proprietary `track` field. Synthetic evaluation (synthetic gold as the E2c4–E2c7 scored set, `primary.v1` headline) stays in use until enough real reference data exists; no synthetic score, profile, report, or gate changes. Real references must be human-attested and adjudicated: handwritten ones through `F7c`/`F7e`, printed ones from Hebrew Wikisource quality-4 pages (`F8b`–`F8b7`, maintainer decision 2). `E2d1` defines the modality-track contract (an optional `modality` and `reference_normalization` on reference-manifest items, `evaluate-references --modality`, the `footnote_masked.v1` view for issue #124, paired bootstrap intervals, and the training-text leakage policy); it is folded into the `E2d2` PR. `E2d2` builds the first real printed scored set (35 adjudicated quality-4 pages from 14 Indexes, plus a 143-page quality-3 `single_reviewer` diagnostic stratum, on the post-`F8b7` pair text with its excluded spans honoured), checks it for training-text leakage (none found), records each page's `F8g` release split (25 of the 35 pages are in `train`, so the set is not held out for release-trained models), and reports Tesseract and R3d/R3g/R3h with R4d + A1 on it beside the synthetic numbers in [`docs/e2d2_real_printed_evaluation.md`](./e2d2_real_printed_evaluation.md). `E2d3` refreshes it on the `F8g2` tranche v2 in [`docs/e2d3_real_printed_evaluation.md`](./e2d3_real_printed_evaluation.md): the same 35 pages (no text or image changed, cached predictions reused) now split 25 / 5 / 5, results are reported for all pages and for the 10 release `validation` + `test` pages separately, and `evaluate-references --bootstrap-clusters` adds a book-level cluster bootstrap beside the page bootstrap (Tesseract 0.222, page [0.162, 0.293], book [0.148, 0.346]; R3h + R4d + A1 0.887 on all pages; on validation + test, Tesseract 0.212 and R3h 0.759). `E2d3b` scores the quality-4 pages edited after validation on their validating-revision text, which both editors attested, after an agent visual check of the scan ([`docs/e2d3b_validated_revision_evaluation.md`](./e2d3b_validated_revision_evaluation.md)): 4 of the 26 agree with the scan and join the pool (39 pages; Tesseract 0.216, page [0.163, 0.279], book [0.149, 0.329]); the other 22 are `validated_text_disagrees_with_scan`. `E2d3c` corrects that pool: a difference limited to line or paragraph whitespace never disqualifies a validated text, which admits one page, and Hebrewbooks 19784 p. 24 is `text_not_on_page` (40 pages; Tesseract 0.231, R3h + R4d + A1 0.889; validation + test unchanged). `E2d3d` checks every scored Hebrewbooks 19784 page against its scan: pp. 8 and 25 hold editors' text the page does not print and become `text_not_on_page` (38 pages; Tesseract 0.237, R3h + R4d + A1 0.898; validation + test 8 pages, `test` only 3). `E2d3e` adds a reference constraint to the group-whole split (`size_aware_group_split.v2`, weighted by exactly the pages the evaluation scores: `test` holds 2 or more such books, 10% or more of their characters, and no book above 50%), applied in tranche v5. It moves *The Selihot for the Entire Year* to `test`. Validation + test is 10 pages, a labelled diagnostic only until the splits change, and tuning stays on synthetic validation. `E2d4` audits the 38 scored reference pages against their scans (maintainer decision 2026-11-07): an agent proposes corrections (519 in `docs/reference_audit_proposals.json`), and the reference build applies only human-accepted or human-edited ones (`docs/reference_audit_decisions.json`, with provenance; undecided pages are flagged `audit_pending`). The maintainer accepted 103 spacing proposals, almost all a stray space before a punctuation mark. `E2d4b` then makes that fix an always-on rule (`space_before_punctuation.v1`, maintainer decision 2026-11-07), applied after the audit to every Wikisource evaluation reference with per-item provenance. Proposals the rule makes exactly are resolved by rule decisions (13; never counted as human review), and 403 stay undecided. Tesseract moves from 0.2365 to 0.2321 on the 38 pages, and R3h + R4d + A1 is unchanged; see [`docs/e2d4_reference_audit.md`](./e2d4_reference_audit.md). `E2d6` adds single-line verification (maintainer decision 2026-11-07, "Yes, like quality 4"). A human verifies one printed line against a candidate typed by a different human: a Wikisource quality-3 page, or PBY text aligned to an NLI free-use scan. The hardest lines come first, with an unbiased random stratum mixed in. `hocrgen.tools.line_verify` exports `line_verify_items.v1` bundles for `HeOCR/heocr-review` and ingests `line_verify_decisions.v1` into `docs/line_verify_references.json`. Lines are localized with the F8f aligner, and OCR is used for geometry and difficulty only. A line typed by one human and verified by a second counts as adjudicated and `reference_eligible` (`ATTESTATION_POLICY`), and it keeps its book's release split. The first batch, `line_verify_v1`, holds 1,500 lines from 39 books, 253 of them in `test`; its first ingest (2026-11-11) holds 198 verified lines from 25 books, 20 of them in `validation` + `test`; see [`docs/e2d6_line_verification.md`](./e2d6_line_verification.md). `E2d6b` adds the `pointed_print` outcome (`line_verify_decisions.v1.1`, additive; v1 still accepted): the letters match the print but the print carries niqqud the candidate lacks, so the line is an adjudicated reference for consonantal views only (`reference_views`), with per-book counts as feedback on the v1 batch split, which used the candidate's niqqud share. `E2d5` (planned) retires synthetic text from the scored set once both tracks meet cutover criteria the maintainer sets. The plan is in [`planning/tasks/e2d-real-scan-evaluation.md`](../planning/tasks/e2d-real-scan-evaluation.md) and the decision record in [`planning/decisions/2026-11-06-real-scan-evaluation-direction.md`](../planning/decisions/2026-11-06-real-scan-evaluation-direction.md).
