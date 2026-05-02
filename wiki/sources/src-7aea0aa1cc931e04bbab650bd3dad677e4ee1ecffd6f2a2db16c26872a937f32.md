---
schema_version: '1'
kind: source-summary
title: HeOCR hocrgen long term roadmap
page_id: src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32
status: active
review_state: machine-generated
source_refs:
- src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32
generated_by_run_ids:
- run-src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32-20260502T090920671975Z
last_generated_at: '2026-05-02T09:09:20+00:00'
last_reviewed_at: null
confidence: 1.0
related_pages: []
tags:
- source-summary
- md
provenance_links:
- source_id: src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32
  page_id: null
  run_id: null
  path_ref: state/manifests/sources/src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32.json
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: run-src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32-20260502T090920671975Z
  path_ref: null
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: null
  path_ref: docs/HeOCR_hocrgen_long_term_roadmap.md
  role: input
  note: null
contradictions: []
---

# HeOCR hocrgen long term roadmap

## Source

- Source ID: `src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32`
- Source type: `md`
- Registered path: `docs/HeOCR_hocrgen_long_term_roadmap.md`
- Source file: `docs/HeOCR_hocrgen_long_term_roadmap.md`

## Summary

HeOCR / hocrgen Long-Term Roadmap and Milestone Plan. This document provides a long-term planning framework for the HeOCR dataset and the hocrgen tool. registered from `docs/HeOCR_hocrgen_long_term_roadmap.md`.

## Key Facts

- Source ID: `src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32`
- Source type: `md`
- Checksum: `7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32`
- Source ref: `docs/HeOCR_hocrgen_long_term_roadmap.md`
- Added at: `2026-05-02T09:09:16+00:00`
- Ingested at: `2026-05-02T09:09:20+00:00`

## Extract

```text
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
- **hocrgen**: the open-source orchestration/governance/export toolchain that curates, versions, and publishes governed dataset releases
- **hocrsyngen**: the synthetic Hebrew OCR/HTR generation package that emits candidate generated sample units and manifests
- **HeOCRsynth**: the synthetic-only dataset repository that receives versioned synthetic releases from `hocrgen`

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
- **Phase F**: Beta-scale trial preparation
- **Phase G**: Synthetic generation spinout and synthetic-only dataset stream

### Milestone types
Each milestone includes:
- objective
- scope
```

## Provenance

- Manifest: `state/manifests/sources/src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32.json`
- Workspace source: `docs/HeOCR_hocrgen_long_term_roadmap.md`
- Run ID: `run-src-7aea0aa1cc931e04bbab650bd3dad677e4ee1ecffd6f2a2db16c26872a937f32-20260502T090920671975Z`
- Pipeline version: `0.1.0a0`
