# Amendment suggestion: spin out synthetic Hebrew OCR/HTR document generation into a separate project

> Note: This document is preserved as external review input, not as the authoritative hocrgen roadmap. Where it uses `heocrsynth` or `HeOCR-Synth` as a working title for the generator repository, read that as the generator package now named `hocrsyngen`. The synthetic-only dataset repository is `HeOCRsynth`; hocrgen remains the orchestration, governance, and export pipeline.

**Prepared for:** HeOCR / hocrgen planning

**Date:** 2026-05-02

**Working title for the new repository:** `heocrsynth` / `HeOCR-Synth`

**Decision class:** roadmap amendment before implementation of the next synthetic-quality and beta-readiness work

---

## 1. Executive recommendation

Create a separate repository, provisionally named **`heocrsynth`**, for synthetic Hebrew OCR/HTR document generation. Keep **`hocrgen`** as the dataset operations and release-governance toolchain, and make it consume the new generator through a narrow, deterministic provider API.

The current roadmap already says that modern handwritten Hebrew is the core dataset identity, that synthetic data should help without dominating, and that future beta readiness depends on rights-clean modern handwriting, benchmark ground truth, and Hebrew-specific RTL/niqqud/layout synthetic quality. The proposed amendment preserves those principles but changes the implementation boundary: the synthetic generator should no longer be treated as a growing subsystem inside `hocrgen`. It should become a dedicated research-and-generation project with its own API, tests, assets, model experiments, governance, and evaluation loop. [R1], [R2]

The new repository should provide one principal product:

> Given a reproducible request, generate one or more realistic-looking **synthetic Hebrew document sample units**: scanned-document image assets plus exact text, line/region references, metadata, provenance, and generation controls suitable for inclusion as a governed synthetic component of a Hebrew OCR/HTR dataset.

This is not merely a code-organization change. It changes the roadmap from “make `hocrgen` synthetic templates better” to “build an external, script-aware synthetic Hebrew document laboratory that `hocrgen` can safely use.”

---

## 2. Existing roadmap context

The existing plan establishes several constraints that should not be relaxed:

1. **Product split:** `HeOCR` is the public dataset; `hocrgen` is the toolchain that generates, curates, versions, and publishes it. [R1]
2. **Dataset identity:** the project’s stated long-term identity is modern handwritten Hebrew, not a generic historical-scan or synthetic-demo corpus. [R1]
3. **Synthetic boundary:** the roadmap says synthetic data should help, but should remain bounded and capped. [R1]
4. **Current implementation:** the repository already includes deterministic synthetic Hebrew sample generation, governed fonts, a curated text corpus, and release caps, but the implementation is still a small, fixture/sample-driven source among several sources, not a full handwriting synthesis platform. [R2], [R3]
5. **Future gates:** the current Phase F roadmap already includes modern handwritten acquisition (`F3`), RTL/niqqud/layout synthetic quality (`F4`), and public beta readiness (`F5`). [R1]

The amendment should therefore be framed as a change to **ownership and depth of synthetic generation**, not as a retreat from the existing safety gates.

---

## 3. Problem statement

The new thought identifies a real architectural mismatch:

- `hocrgen` is becoming a release pipeline, governance engine, acquisition orchestrator, and benchmark/annotation coordinator.
- High-quality synthetic handwriting generation is a separate research problem with different needs: rendering, script shaping, allograph modeling, writer-style modeling, degradation simulation, image synthesis, optional ML models, visual realism evaluation, and human review.
- Letting all of that grow inside `hocrgen` risks making the release pipeline heavy, experimental, hard to test, and difficult to keep legally and operationally conservative.

The specific user idea adds requirements that exceed the current `project_synthetic` source:

- generate believable scanned Hebrew document pages, not just sample text cards;
- provide exact text and metadata counterpart suitable for OCR/HTR datasets;
- model handwritten Hebrew, not only print-like or handwriting-font rendering;
- create synthetic writer “personas” with stable visual and textual tendencies;
- allow latent condition controls such as concentration, fatigue, haste, or affect-like state;
- use character-level and line-level transformations such as stretching, slant, baseline drift, pressure/noise, letter spacing, and per-character variation;
- stay sufficiently generalized to later support another right-to-left script such as Arabic.

This should be a dedicated project.

---

## 4. Amendment thesis

Add a new project boundary:

| Component | Responsibility after amendment | Non-responsibility after amendment |
| --- | --- | --- |
| `HeOCR` | Public dataset releases, manifests, dataset cards, benchmark/public artifacts | Generating synthetic samples directly |
| `hocrgen` | Source acquisition, rights policy, privacy review, dedupe, splits, benchmark selection, annotation references, release export, synthetic caps, and provider integration | Handwriting synthesis research, model training, allograph generation, low-level rendering/degradation experimentation |
| `heocrsynth` | Synthetic Hebrew OCR/HTR sample generation, generator API, Hebrew/script rendering correctness, persona/style/condition model, document realism, optional ML generator experiments, synthetic output manifests | Public release governance, real-source acquisition, dataset publication, deciding whether a synthetic item is release-ready |

The central contract should be: **`heocrsynth` generates candidate synthetic sample units; `hocrgen` decides whether and how they enter HeOCR outputs.**

---

## 5. Proposed new repository: `heocrsynth`

### 5.1 Mission

`heocrsynth` should generate synthetic document images and exact ground truth for Hebrew OCR/HTR research, with a strong emphasis on modern handwritten Hebrew and eventual script generalization.

A possible README mission statement:

> `heocrsynth` is a synthetic document generator for Hebrew OCR/HTR datasets. It creates reproducible synthetic scanned-document samples with exact text, layout metadata, provenance, and controllable handwriting-style variation. Its first target is modern handwritten Hebrew; its architecture is script-aware so that related right-to-left scripts can be added later without changing the dataset pipeline that consumes it.

### 5.2 Non-goals

The new project should not initially attempt to:

- publish a public dataset by itself;
- bypass `hocrgen` rights/review/release caps;
- replace rights-clean real modern handwriting acquisition;
- impersonate identifiable real writers without explicit consent and a clear license;
- train production OCR/HTR models as its main deliverable;
- support Arabic before the Hebrew contract and evaluation gates are stable;
- make synthetic benchmark claims before real benchmark references exist.

---

## 6. API contract

The new project should expose both a Python API and a CLI. `hocrgen` should be able to use either, but the Python API should be the primary integration path for local operator runs.

### 6.1 Minimal Python API

```python
from heocrsynth import GenerateRequest, generate_document

request = GenerateRequest(
    sample_id="synthetic-hebrew-000001",
    seed=1729,
    script="hebrew",
    profile="hebrew_handwritten_document_v1",
    page_count=1,
    document_type="administrative_note",
    text_policy={"source": "project-authored", "topic": "community_admin"},
    persona_policy={"mode": "sample", "family": "modern_hebrew_cursive"},
    condition_policy={"pace": "hurried", "concentration": "low"},
    output={"image_format": "jpeg", "include_line_boxes": True},
)

document = generate_document(request)
```

### 6.2 CLI contract

```bash
heocrsynth generate \
  --profile hebrew_handwritten_document_v1 \
  --count 80 \
  --seed 1729 \
  --out .work/heocrsynth/run-1729
```

The CLI should emit a `generation_manifest.json` that `hocrgen` can ingest without needing to understand all low-level synthesis internals.

### 6.3 Generated sample unit

A generated sample unit should be multi-page capable from the start, even if the MVP emits only one page:

```json
{
  "schema_version": 1,
  "sample_id": "synthetic-hebrew-000001",
  "script": "hebrew",
  "language": "he",
  "text_direction": "rtl",
  "document_type": "administrative_note",
  "pages": [
    {
      "page_id": "page-0001",
      "image_path": "images/synthetic-hebrew-000001/page-0001.jpg",
      "width": 1200,
      "height": 1600,
      "dpi": 300,
      "text": "... logical-order Hebrew text ...",
      "regions": [],
      "lines": []
    }
  ],
  "ground_truth": {
    "document_text": "... logical-order full text ...",
    "normalization": "NFC",
    "line_order": "reading_order_rtl",
    "contains_niqqud": false,
    "contains_mixed_direction_text": true
  },
  "persona": {
    "persona_id": "persona-6cc731",
    "persona_family": "modern_hebrew_cursive",
    "style_seed": 983221,
    "public_description": "synthetic persona; not a real writer"
  },
  "condition": {
    "pace": "hurried",
    "concentration": "low",
    "affect_label": "neutral_or_unspecified",
    "label_semantics": "generator_control_not_psychological_ground_truth"
  },
  "provenance": {
    "generator": "heocrsynth",
    "generator_version": "0.1.0",
    "recipe_id": "hebrew_admin_note_handwritten_v1",
    "assets": [],
    "corpus_refs": [],
    "license": "PROJECT-SYNTHETIC"
  }
}
```

### 6.4 Contract invariants

The API should guarantee:

1. **Determinism:** same version, same request, same seed, same assets produce byte-stable images or at least stable semantic outputs under a declared determinism mode.
2. **Logical text order:** ground truth is stored in Unicode logical order, not visual reversal.
3. **Explicit rendering settings:** text shaper, font, bidi settings, normalization form, rasterization settings, and degradation recipe are recorded.
4. **No local path leakage:** exported manifests are release-relative.
5. **Synthetic provenance:** every sample is clearly labeled synthetic and never implies real-source provenance.
6. **Asset governance:** fonts, corpora, style samples, models, and image assets are manifest-tracked with license/provenance/checksum.
7. **Script conformance:** Hebrew samples pass right-to-left, bidi, niqqud, final-letter, numeral, and mixed-direction rendering tests before release use.
8. **Downstream compatibility:** outputs can be mapped into existing `hocrgen` item/acquisition/normalization manifests without weakening review, privacy, synthetic-cap, split, benchmark, or export-portability gates.

---

## 7. Integration with `hocrgen`

### 7.1 Keep `hocrgen` as orchestrator, not generator lab

`hocrgen` should gain a new adapter, for example:

- `src/hocrgen/fetchers/synthetic_provider.py`
- source id: `project_synthetic_external`
- source settings:

```yaml
- id: project_synthetic_external
  name: HeOCR external synthetic provider
  fetcher: synthetic_provider
  status: allowed
  default_public_release: true
  allowed_content_types:
    - synthetic_handwritten_hebrew
    - synthetic_printed_hebrew
    - synthetic_mixed_hebrew
  rights_strategy:
    type: exact_match
    values:
      - PROJECT-SYNTHETIC
  normalized_license: PROJECT-SYNTHETIC
  rights_classification: open
  requires_manual_review: false
  settings:
    provider: heocrsynth
    provider_mode: python_api
    provider_profile: hebrew_handwritten_document_v1
    synthetic_batch_size: 80
    synthetic_seed: 17
    output_contract: generation_manifest_v1
```

The adapter should convert `heocrsynth` generated sample units into existing `hocrgen` item records and acquired assets. It should not duplicate low-level rendering logic.

### 7.2 Freeze the current internal generator as a legacy smoke source

The existing internal `project_synthetic` generator is useful for smoke tests and should not be deleted immediately. Recommended transition:

1. Mark it as `project_synthetic_legacy` in docs once external provider support exists.
2. Keep it in CI as a network-free, dependency-light fixture generator.
3. Do not keep expanding it into advanced handwriting synthesis.
4. Public profile should eventually prefer `project_synthetic_external` once the external provider passes release-quality gates.

### 7.3 Avoid heavy dependency leakage

`hocrgen` should not inherit GPU, diffusion, training, or large model dependencies. The provider contract should allow:

- `heocrsynth[minimal]`: deterministic renderer, no GPU;
- `heocrsynth[research]`: optional ML handwriting synthesis experiments;
- `heocrsynth[eval]`: optional OCR/HTR evaluation utilities;
- `hocrgen`: depends only on the minimal provider interface or reads a generated manifest.

---

## 8. Proposed generator architecture

`heocrsynth` should be built as layers. Each layer can produce useful outputs before the next is complete.

### 8.1 Layer 1 — deterministic typed/font renderer

Purpose: produce a reliable baseline and exercise the API.

Capabilities:

- project-owned or permissively licensed Hebrew text corpora;
- governed Hebrew fonts;
- layout recipes for notes, forms, ledgers, letters, margins, stamps, signatures, and annotations;
- scan degradation: skew, blur, grain, uneven illumination, paper texture, compression, bleed-through, edge wear, crop, shadow;
- exact text and line metadata.

This layer is not sufficient for realistic handwriting, but it establishes a stable baseline and CI target.

### 8.2 Layer 2 — font-plus-perturbation handwritten baseline

Purpose: improve over static handwriting fonts without introducing ML.

Capabilities:

- per-character and per-word affine perturbation;
- baseline jitter and line curvature;
- stroke-thickness variation;
- ink discontinuity and pen pressure simulation;
- letter spacing and word spacing variation;
- occasional corrections, overwritten letters, insertions, marginal notes, and crossed-out words;
- style-stable parameters per persona.

This layer should be the MVP route to visually plausible handwritten-like pages.

### 8.3 Layer 3 — allograph / character-bank synthesis

Purpose: move from fonts to handwriting components.

Capabilities:

- collect or import rights-clean isolated Hebrew letter/allograph components;
- model final forms separately: ך, ם, ן, ף, ץ;
- model common handwritten variants, loops, simplifications, stroke joins, and letter ambiguity;
- assemble words and lines from component variants while preserving persona consistency;
- apply local deformation per allograph and global deformation per word/line.

For Hebrew this is attractive because modern handwritten Hebrew is typically not cursive in the connected-letter sense. Unicode notes that handwritten Hebrew is called cursive but that its rounded letters are generally unconnected, which supports a component/allograph approach as a plausible intermediate before full generative models. [R13]

### 8.4 Layer 4 — persona model

Purpose: generate stable synthetic writers rather than independent random pages.

A persona should be a reproducible synthetic parameter object, not a claim about a real person:

```json
{
  "persona_id": "persona-6cc731",
  "script_family": "modern_hebrew_cursive",
  "handwriting_features": {
    "slant": -0.08,
    "baseline_wander": 0.22,
    "letter_width_variance": 0.18,
    "stroke_width": 2.7,
    "pressure_variability": 0.31,
    "spacing_tightness": 0.64,
    "final_letter_extension": 0.42
  },
  "layout_preferences": {
    "margin_left": 0.12,
    "margin_right": 0.09,
    "line_spacing": 1.18,
    "uses_marginal_notes": true
  },
  "text_preferences": {
    "topics": ["community_admin", "personal_note"],
    "register": "semi_formal",
    "mixed_language_frequency": 0.04
  }
}
```

The important property is intra-persona consistency: multiple documents from the same synthetic persona should look related, while documents from different personas should differ in controlled ways.

### 8.5 Layer 5 — condition model

Purpose: represent temporary state such as haste, fatigue, concentration, stress-like perturbation, or affect-like condition without overstating psychological validity.

The plan should **not** claim that generated handwriting reveals a true emotion or personality. It should treat `condition` as a generator-control vector that perturbs writing dynamics. Research on emotion recognition from handwriting exists, but published examples often frame it as proof-of-concept and show limited user-independent accuracy; the plan should therefore use condition labels cautiously. [R18]

Suggested condition parameters:

| Parameter | Possible visual effects | Notes |
| --- | --- | --- |
| `pace` | looser spacing, stronger slant, less uniform baseline, more omissions/corrections | More defensible than “emotion” |
| `fatigue` | smaller letter size over time, wavering baseline, lighter strokes | Should be tunable per line/page |
| `concentration` | spacing regularity, correction frequency, local neatness | Use as synthetic control |
| `stress_like_arousal` | pressure variation, tremor/noise, angularity, baseline instability | Label as generator control, not diagnosis |
| `mood_style` | optional high-level style family | Avoid public claims unless validated |

### 8.6 Layer 6 — generative model experiments

Purpose: explore modern handwriting generation models only after deterministic and allograph baselines exist.

Possible families:

- GAN-style arbitrary-length generation, following ideas from ScrabbleGAN. [R6]
- content-conditioned style generation, following GANwriting-like objectives. [R7]
- few-shot diffusion style generation, following DiffusionPen-like approaches. [R8]
- autoregressive styled text image generation, following newer work such as Emuru. [R9]

These experiments should be isolated behind optional extras and should not become mandatory for `hocrgen` CI or public export. The project should treat them as candidates whose utility must be proven by OCR/HTR task metrics and human review, not by visual appeal alone.

---

## 9. Hebrew-specific rendering requirements

Synthetic Hebrew OCR data is only useful if the text semantics and raster rendering are correct. The amendment should add explicit Hebrew rendering gates.

### 9.1 RTL and bidi

The generator should use Unicode logical order internally and rely on a proper bidirectional layout path. Unicode UAX #9 describes how to position characters in text containing right-to-left scripts such as Hebrew and Arabic. [R11]

Required fixtures:

- Hebrew-only line;
- Hebrew with Latin acronym;
- Hebrew with Arabic numerals;
- Hebrew with date formats;
- Hebrew with punctuation at line boundaries;
- Hebrew with parentheses/quotes;
- Hebrew mixed with English words;
- Hebrew plus document identifiers such as `מספר תיק 17-A/2026`.

### 9.2 Niqqud and marks

The generator should support three modes:

1. **No niqqud** for most modern administrative handwritten samples.
2. **Sparse niqqud** for pedagogical, poetic, religious, or citation-like samples.
3. **Full niqqud/cantillation stress tests** for rendering validation, not necessarily public training volume.

Unicode Chapter 9 describes Hebrew points as combining marks and separates classes such as dagesh, shin/sin dot, vowels, and other pronunciation marks. [R12]

### 9.3 Shaping stack

The renderer should use a text layout stack that supports bidi and shaping. Pillow’s `libraqm` path provides bidirectional support using FriBiDi, shaping using HarfBuzz, and proper script itemization. [R14]

Recommended policy:

- Minimal renderer must detect whether complex text layout support is available.
- CI should include a deterministic rendering test that fails if Hebrew text silently falls back to naive left-to-right or reversed rendering.
- The generator should record the rendering backend in every sample manifest.

### 9.4 Hebrew handwriting specifics

The generator should explicitly model:

- modern cursive-style rounded but mostly unconnected letters;
- final letter forms;
- handwritten ambiguity between visually similar letters;
- baseline drift and page slant;
- right margin behavior for RTL writing;
- insertion/correction patterns common in handwritten notes;
- occasional Latin/English fragments and numerals as realistic identifiers, not template explanations.

---

## 10. Document realism requirements

The target output should resemble scanned documents that could belong in a Hebrew OCR/HTR dataset. Realism should be defined across several axes.

### 10.1 Visual realism

- page texture;
- scan/copy artifacts;
- uneven lighting;
- skew and crop;
- ink/pencil/pen simulation;
- stroke gaps and pressure variation;
- edge shadow and paper folds;
- correction marks, marginal notes, stamps, signatures, and form lines.

### 10.2 Layout realism

Document families should include:

- short note;
- administrative memo;
- ledger/register page;
- school-style form;
- personal letter;
- meeting note;
- archival index card;
- receipt-like note;
- printed form with handwritten fill;
- mixed printed/handwritten page.

Each family should have a recipe definition, a metadata schema, and a set of known limitations.

### 10.3 Text realism

Text should be generated from governed sources:

- project-authored Hebrew corpora;
- public-domain Hebrew snippets where legally safe;
- synthetic template grammars with no real personal data;
- optional LLM-generated text only if prompts, outputs, review policy, and reuse rights are documented.

The current `hocrgen` guide already warns against synthetic assets with unclear reuse rights or unaudited generated corpora. That safety rule should move into the new project and remain visible to `hocrgen` reviewers. [R3]

### 10.4 Dataset realism

A release candidate synthetic batch should report:

- synthetic persona count;
- documents per persona;
- document-type distribution;
- text-source distribution;
- font/allograph/model distribution;
- degradation distribution;
- RTL/niqqud/mixed-direction coverage;
- image-quality distribution;
- repeated-template rate;
- known failure modes.

---

## 11. Evaluation strategy

High visual quality is insufficient. The generator should be evaluated as a data source for OCR/HTR.

### 11.1 Static validation

Every generated item should pass:

- schema validation;
- exact text availability;
- UTF-8 and Unicode normalization checks;
- RTL/bidi fixtures;
- asset checksum and dimension checks;
- no absolute path leakage;
- no prohibited synthetic metadata omissions;
- no unknown asset/license references.

### 11.2 Human review

For public-profile synthetic samples, add a lightweight human review rubric:

| Criterion | Pass condition |
| --- | --- |
| Hebrew text correctness | no obvious reversed or malformed Hebrew |
| Document plausibility | resembles a possible scanned page rather than a demo card |
| Handwriting plausibility | handwritten samples are not merely typed text in a novelty font |
| Synthetic disclosure | metadata clearly says synthetic |
| OCR relevance | sample has enough text and degradation to be meaningful |
| No sensitive fake-real confusion | no real-looking private records unless intentionally synthetic and safe |

### 11.3 Task evaluation

Synthetic utility should be measured by at least one downstream OCR/HTR task once benchmark references are available.

Candidate metrics:

- CER/WER on real benchmark references before and after adding synthetic pretraining or augmentation;
- exact-match and coverage on synthetic holdout;
- error breakdown by niqqud, final letters, numerals, and mixed-direction fragments;
- synthetic-to-real gap diagnostics.

TrOCR is an example of a modern text recognition model that can be pre-trained with large-scale synthetic data and fine-tuned with labeled data, but newer HTR literature also shows that synthetic-only training can have a synthetic-to-real gap. The plan should therefore require task evidence rather than assuming more synthetic volume helps. [R5], [R19]

### 11.4 Diversity and leakage

If synthetic personas are used, split policy must prevent leakage:

- same persona should not cross train/validation/test unless explicitly intended and reported;
- style-source samples from a real contributor must not leak to test examples that claim independence;
- generated variants from the same base document should remain in one split;
- benchmark synthetic controls should be stable and versioned separately from exploratory generated batches.

---

## 12. Roadmap amendment

### 12.1 Recommended roadmap text change

Add this section after the current Phase F description:

> **Synthetic-generation ownership amendment.** Advanced synthetic Hebrew OCR/HTR generation will be spun out into a separate repository, provisionally `heocrsynth`. `hocrgen` will remain the dataset operations, policy, review, split, benchmark, and export toolchain. It may consume synthetic samples through a narrow provider contract but should not absorb handwriting synthesis research, ML generation dependencies, or low-level rendering experimentation. Synthetic samples remain capped, explicitly synthetic, and subordinate to rights-clean real acquisition and benchmark ground truth.

### 12.2 Amend Phase F4

Current `F4` should be reframed from “implement synthetic quality inside `hocrgen`” to “validate the external synthetic provider contract and release gates.”

Proposed replacement:

#### Milestone F4 — External synthetic provider integration and Hebrew rendering gates

**Objective:** Integrate a dedicated external synthetic generator with `hocrgen` while preserving release governance, synthetic caps, export portability, and Hebrew rendering correctness.

**Scope:**

- define provider manifest contract;
- add `hocrgen` adapter for generated synthetic sample units;
- keep legacy internal generator as smoke/fixture path;
- validate RTL, bidi, niqqud, Unicode normalization, font-shaping, and mixed-direction rendering metadata;
- add synthetic provider composition reporting;
- reject outputs with missing provenance, unknown assets, invalid rights, absolute paths, or untested rendering settings.

**Planned PRs:**

- `F4a`: Define external synthetic provider contract and update roadmap/docs.
- `F4b`: Implement `hocrgen` synthetic-provider adapter over fixture-backed `heocrsynth` manifests.
- `F4c`: Add Hebrew rendering and metadata gates for external synthetic samples.
- `F4d`: Switch public synthetic profile from legacy generator to external provider only after provider MVP gates pass.

**Exit criteria:**

- `hocrgen` can ingest external synthetic samples without owning the generator internals;
- CI remains network-free and no-GPU;
- public release profiles still enforce synthetic caps;
- generated samples expose exact text, generation metadata, script metadata, and asset provenance;
- Hebrew rendering tests catch naive reversal, bidi failures, missing niqqud metadata, and unsupported shaping fallback.

### 12.3 Add new Phase G

#### Phase G — Dedicated synthetic Hebrew OCR/HTR generation project

This phase belongs primarily to `heocrsynth`, not `hocrgen`.

| Milestone | Repository | Objective | State |
| --- | --- | --- | --- |
| G0 | `heocrsynth` | Repository bootstrap, governance, asset policy, schemas | planned |
| G1 | `heocrsynth` | Stable generation API and manifest contract | planned |
| G2 | `heocrsynth` | Deterministic Hebrew document renderer MVP | planned |
| G3 | `heocrsynth` | RTL/bidi/niqqud/font-shaping validation suite | planned |
| G4 | `heocrsynth` | Persona and condition model for synthetic writers | planned |
| G5 | `heocrsynth` | Hebrew allograph/character-level handwriting engine | planned |
| G6 | `heocrsynth` | Document-layout realism and scan degradation library | planned |
| G7 | `heocrsynth` | Evaluation harness: human review, OCR/HTR metrics, diversity reports | planned |
| G8 | both | `hocrgen` integration with external provider and release gates | planned |
| G9 | `heocrsynth` | Optional GAN/diffusion/autoregressive handwriting experiments | research |
| G10 | `heocrsynth` | Script abstraction for future Arabic support | planned-later |

---

## 13. Detailed milestone plan for `heocrsynth`

### G0 — Repository bootstrap and governance

**Objective:** Create the separate project without weakening the existing release pipeline.

**Deliverables:**

- repository README;
- license and contribution policy;
- synthetic asset contribution policy;
- `schemas/` for request/output/persona/asset manifests;
- no-GPU CI baseline;
- package skeleton;
- sample generated manifest fixture;
- compatibility note for `hocrgen`.

**Exit criteria:**

- a generated fixture can be consumed manually by a draft `hocrgen` adapter;
- all assets have license/provenance/checksum entries;
- README states that generated outputs are synthetic and not real-source documents.

### G1 — API and manifest contract

**Objective:** Stabilize the generated sample unit contract before realism work expands.

**Deliverables:**

- `GenerateRequest` model;
- `GeneratedDocument` model;
- `GenerationManifest` model;
- JSON schemas;
- Python API;
- CLI generator;
- deterministic seed policy;
- fixtures and golden manifests.

**Exit criteria:**

- `heocrsynth generate --count 2 --seed 17` emits reproducible images and manifest;
- `hocrgen` can validate the manifest shape using a fixture;
- no unsupported metadata fields are silently dropped.

### G2 — Deterministic Hebrew document renderer MVP

**Objective:** Produce useful baseline synthetic document pages.

**Deliverables:**

- project-authored Hebrew text corpus;
- governed font manifest;
- document recipes for note, form, and administrative page;
- raster image output;
- basic line boxes and text ground truth;
- scan degradation presets.

**Exit criteria:**

- generated samples are not pristine vector cards;
- every sample has exact document text;
- metadata includes renderer, font, corpus, recipe, and degradation fields.

### G3 — Hebrew rendering validation

**Objective:** Prevent wrong Hebrew rendering from entering synthetic outputs.

**Deliverables:**

- Unicode normalization fixtures;
- bidi/mixed-direction fixtures;
- niqqud fixtures;
- final-letter fixtures;
- rendering-backend detection;
- screenshot/golden-image tests where stable;
- metadata fields for rendering backend and text normalization.

**Exit criteria:**

- naive reversal cannot pass tests;
- samples record `text_direction`, `unicode_normalization`, and rendering backend;
- lack of complex text layout support is visible and blocks release-grade output.

### G4 — Synthetic writer persona model

**Objective:** Generate internally consistent synthetic writers.

**Deliverables:**

- persona schema;
- persona sampler;
- persona persistence and replay;
- style vector fields;
- visual feature controls;
- persona-level diversity report.

**Exit criteria:**

- multiple pages from one persona share visible traits;
- different personas differ by controlled parameters;
- persona IDs can be used by `hocrgen` split/leakage logic.

### G5 — Hebrew allograph / component handwriting engine

**Objective:** Move beyond handwriting fonts toward character-level synthetic handwriting.

**Deliverables:**

- component/allograph inventory schema;
- generated or collected rights-clean component assets;
- character variant sampler;
- word assembly engine;
- per-letter deformation and placement;
- final-form handling;
- line-level baseline and spacing model.

**Exit criteria:**

- generated words are not uniform font glyphs;
- per-persona allograph choice is stable;
- repeated letters show natural variation without losing legibility;
- generated text remains aligned to ground truth.

### G6 — Document layout and degradation realism

**Objective:** Make complete pages plausible as scanned documents.

**Deliverables:**

- document family recipes;
- printed + handwritten mixed layouts;
- stamps/signatures/marginalia/corrections;
- paper and scanner model;
- degradation parameter report;
- visual review samples.

**Exit criteria:**

- samples are document-like, not template-like;
- degradation is controlled and metadata-backed;
- review rubric can distinguish release-grade from experimental outputs.

### G7 — Evaluation harness

**Objective:** Measure whether synthetic samples help OCR/HTR tasks and where they fail.

**Deliverables:**

- synthetic holdout references;
- optional OCR/HTR evaluation scripts;
- CER/WER helpers;
- rendering/failure report;
- diversity report;
- human review rubric;
- integration with `hocrgen` benchmark conventions.

**Exit criteria:**

- generated batches can be compared across versions;
- synthetic-to-real impact can be measured when real references are available;
- public-release candidates must pass both static and human review gates.

### G8 — `hocrgen` integration

**Objective:** Make external synthetic generation operational in the HeOCR pipeline.

**Deliverables:**

- fixture-backed `hocrgen` adapter;
- source config updates;
- synthetic provider composition report;
- release profile tests;
- alpha/beta export portability tests;
- documentation updates.

**Exit criteria:**

- `hocrgen build-release --source project_synthetic_external` works against a fixture manifest;
- public release caps remain enforced;
- synthetic items include exact text and metadata in release manifests;
- no generator internals are required in `hocrgen` public exports.

### G9 — Optional ML handwriting synthesis experiments

**Objective:** Evaluate whether modern generative methods improve synthetic usefulness.

**Deliverables:**

- optional research package extras;
- experiment configs;
- model cards;
- training data license reports;
- generated sample comparison;
- HTR utility report.

**Exit criteria:**

- ML-generated samples outperform or complement the deterministic/allograph baseline under task metrics;
- model dependencies remain optional;
- public samples disclose model version and training-data provenance.

### G10 — Arabic-ready script abstraction

**Objective:** Prepare for a future Arabic component without implementing Arabic prematurely.

**Deliverables:**

- `ScriptProfile` interface;
- `TextShaper` interface;
- `AllographInventory` abstraction;
- `DocumentRecipe` abstraction;
- Hebrew implementation as first concrete script;
- one minimal Arabic placeholder fixture or conformance design note only after Hebrew is stable.

**Exit criteria:**

- adding Arabic later does not require changing the `hocrgen` provider contract;
- the architecture acknowledges script-specific shaping, joining, and allograph rules;
- Arabic work remains a later milestone, not hidden scope creep.

Arabic handwriting synthesis literature shows that component segmentation and naturalness constraints have long been explored for OCR data generation, but Arabic’s connected script and joining behavior are different from Hebrew and should be handled by a later script-specific module. [R16]

---

## 14. Changes to implementation order

The current critical path should be modified as follows:

1. Keep `F1` operator-only beta acquisition and `F2` benchmark ground-truth planning on track.
2. Before implementing current `F4`, add `F4a` as a planning PR that records the synthetic spinout decision.
3. Bootstrap `heocrsynth` as `G0` and define the API as `G1` before writing a substantial new generator.
4. Add `hocrgen` provider ingestion with fixtures (`F4b` / `G8`) before using external outputs in public profiles.
5. Do not let `heocrsynth` delay rights-clean real handwriting acquisition (`F3`); the two streams should reinforce each other but not substitute for each other.
6. Public beta (`F5`) should require external synthetic provider gates only if synthetic volume is included in the public beta profile.

Recommended near-term PR sequence:

| Order | Repo | PR notation | Summary |
| --- | --- | --- | --- |
| 1 | `hocrgen` | `F4a` | Record synthetic spinout and provider-contract amendment |
| 2 | `heocrsynth` | `G0a` | Bootstrap repository, governance, schemas, CI |
| 3 | `heocrsynth` | `G1a` | Implement API/CLI and generated-manifest contract |
| 4 | `hocrgen` | `F4b` | Add fixture-backed synthetic-provider adapter |
| 5 | `heocrsynth` | `G2a` | Deterministic Hebrew document renderer MVP |
| 6 | `heocrsynth` | `G3a` | RTL/bidi/niqqud/shaping validation suite |
| 7 | `heocrsynth` | `G4a` | Persona model and composition reporting |
| 8 | `heocrsynth` | `G5a` | Character/allograph handwriting engine MVP |
| 9 | both | `F4c/G8a` | Release gate integration and external provider smoke release |

---

## 15. Policy and ethics

### 15.1 Synthetic disclosure

Every generated item should state:

- `is_synthetic: true`;
- `source_id: project_synthetic_external` or equivalent;
- `synthetic_generator: heocrsynth`;
- `generator_version`;
- `recipe_id`;
- `persona_id` if used;
- `license: PROJECT-SYNTHETIC`;
- `not_real_document: true` or equivalent public field.

### 15.2 Consent and style samples

If real handwriting samples are used to seed styles:

- contributor consent must cover style extraction and synthetic generation;
- public release must not include raw private style samples unless separately permitted;
- generated style should not claim to reproduce a real person unless that is explicitly consented and intended;
- takedown/deprecation policies must cover generated items derived from withdrawn style samples.

### 15.3 Text safety

Synthetic text should avoid modern names, addresses, phone numbers, emails, ID numbers, and sensitive records in default public profiles. If privacy edge cases are needed for tests, keep them in private/test fixtures and route them through privacy-specific tests rather than public synthetic defaults.

### 15.4 Copyright and corpus governance

All corpora and prompts must be auditable. The existing `hocrgen` synthetic asset guide already rejects unclear reuse rights and unaudited generated corpora; `heocrsynth` should inherit that standard. [R3]

---

## 16. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Synthetic work overwhelms real acquisition | Keep synthetic caps in `hocrgen`; F3 remains first-class |
| Generator becomes too ML-heavy | Separate `minimal`, `eval`, and `research` extras; keep `hocrgen` no-GPU |
| Visually appealing samples do not improve HTR | Require task metrics and synthetic-to-real evaluation |
| Hebrew rendering errors silently enter data | Add mandatory bidi/niqqud/shaping fixtures and metadata gates |
| Persona model implies real psychological traits | Treat persona/condition labels as generator controls only |
| Style imitation creates ethical/legal issues | Require consent and model/source cards for style-sample use |
| Public users confuse synthetic with real documents | Strong synthetic disclosure in manifests and dataset cards |
| Arabic support bloats scope | Add script abstraction only; defer Arabic implementation |
| Generated text contains sensitive fake-real content | Governed corpora; privacy tests; no real PII in defaults |
| Benchmark contamination | Keep synthetic controls stable and separate; split by persona/source group |

---

## 17. Acceptance criteria for the first usable integration

A first integration should be considered acceptable only when all of the following are true:

1. `heocrsynth` can generate at least 20 Hebrew synthetic sample units from a fixed seed.
2. Each sample has one or more raster page images and exact document text.
3. Each sample has generator, recipe, font/asset, corpus, persona, condition, and degradation metadata.
4. Hebrew-only, mixed Hebrew/Latin, numerals, punctuation, final letters, and at least sparse niqqud fixtures are tested.
5. `hocrgen` can ingest a fixture `generation_manifest.json` without importing heavy ML dependencies.
6. Synthetic caps in `profile_open_v1` still apply.
7. Alpha/beta export does not leak absolute paths from the provider run.
8. A human review of a small generated batch finds no obvious reversed Hebrew, template-card artifacts, or misleading real-document provenance.
9. The dataset card can explain the synthetic generator version, limitations, and proportion.
10. The legacy `project_synthetic` path remains available for smoke testing until external provider stability is proven.

---

## 18. Recommended final position

Adopt the spinout. It is strategically aligned with the roadmap because it strengthens the weakest future synthetic-quality area without diluting `hocrgen`’s core role as a conservative dataset operations tool. It also gives the handwriting-synthesis work enough room to become genuinely research-grade: persona modeling, character/allograph assembly, condition perturbations, Hebrew rendering validation, document realism, optional generative models, and future Arabic generalization all need their own repository and review cadence.

The amendment should be implemented before further major synthetic-generation work begins. The next planning PR should record the architectural decision, rewrite `F4` as an external-provider integration milestone, and add a new Phase G for `heocrsynth`.

---

## References

[R1] HeOCR / hocrgen Long-Term Roadmap and Milestone Plan, attached plan file, 2026-05-02 user upload.

[R2] HeOCR/hocrgen GitHub repository README and current repository package, accessed 2026-05-02. https://github.com/HeOCR/hocrgen

[R3] `docs/synthetic_asset_contribution_guide.md` and current source configuration in the attached repomix package, including synthetic asset governance, current `project_synthetic` source, and current synthetic caps.

[R4] Rabaev, I.; Kurar Barakat, B.; Churkin, A.; El-Sana, J. “The HHD Dataset.” ICFHR 2020. BGU research portal page: https://cris.bgu.ac.il/en/publications/the-hhd-dataset-2/

[R5] Li, M. et al. “TrOCR: Transformer-based Optical Character Recognition with Pre-trained Models.” arXiv:2109.10282. https://arxiv.org/abs/2109.10282

[R6] Fogel, S. et al. “ScrabbleGAN: Semi-Supervised Varying Length Handwritten Text Generation.” CVPR 2020 / arXiv:2003.10557. https://arxiv.org/abs/2003.10557

[R7] Kang, L. et al. “GANwriting: Content-Conditioned Generation of Styled Handwritten Word Images.” ECCV 2020 / arXiv:2003.02567. https://arxiv.org/abs/2003.02567

[R8] Nikolaidou, K. et al. “DiffusionPen: Towards Controlling the Style of Handwritten Text Generation.” arXiv:2409.06065. https://arxiv.org/html/2409.06065v1

[R9] Pippi, V. et al. “Zero-Shot Styled Text Image Generation, but Make It Autoregressive.” arXiv:2503.17074. https://arxiv.org/abs/2503.17074

[R10] Díaz, M. et al. “A survey of handwriting synthesis from 2019 to 2024: A comprehensive review.” Pattern Recognition, 2025. https://www.sciencedirect.com/science/article/pii/S0031320325000172

[R11] Unicode Consortium. “Unicode Standard Annex #9: Unicode Bidirectional Algorithm.” Version Unicode 17.0.0, 2025-08-13. https://www.unicode.org/reports/tr9/

[R12] Unicode Consortium. “The Unicode Standard, Version 17.0.0, Chapter 9: Middle Eastern Scripts — Hebrew.” https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-9/

[R13] Unicode Chapter 9, Hebrew script discussion noting that handwritten Hebrew is called cursive but generally has unconnected rounded letters. https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-9/

[R14] Pillow documentation, build/install section: `libraqm` provides bidirectional text support using FriBiDi, shaping using HarfBuzz, and proper script itemization. https://pillow.readthedocs.io/en/latest/installation/building-from-source.html

[R15] Clova AI. SynthTIGER documentation: synthetic text image generator for OCR models. https://clovaai.github.io/synthtiger/

[R16] Elarian, Y. S.; Al-Muhtaseb, H. A.; Ghouti, L. “Arabic Handwriting Synthesis.” https://d-nb.info/1106256131/34

[R17] Belval. TextRecognitionDataGenerator GitHub repository: synthetic data generator for OCR/text recognition, with non-Latin support. https://github.com/Belval/TextRecognitionDataGenerator

[R18] Han, J.; Wolf, K.; Kunze, K. “Sentiment Pen: Recognizing Emotional Context Based on Handwriting Features.” AH 2019. https://katrinwolf.info/wp-content/uploads/2021/04/AH2019_Empathy_Pen.pdf

[R19] Garrido-Muñoz, C. et al. “Zero-Shot Synthetic-to-Real Handwritten Text Recognition via Task Analogies.” arXiv:2604.09713, 2026. https://arxiv.org/html/2604.09713v1

[R20] Kim, G. et al. “OCR-free Document Understanding Transformer.” ECCV 2022, includes SynthDoG synthetic document generator use for pretraining. https://www.ecva.net/papers/eccv_2022/papers_ECCV/papers/136880493.pdf
