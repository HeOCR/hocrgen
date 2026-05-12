# HeOCR ecosystem overview

`F4f` records the wider HeOCR ecosystem layout that surrounds `hocrgen` without
changing any runtime behavior, readiness gate, or release path. It supersedes
the narrower "four-repository synthetic spinout boundary" framing introduced by
`F4a` and extends it upstream to the real-handwriting scan and per-letter-glyph
repositories that feed `hocrsyngen`. The downstream `HeOCR` and `HeOCRsynth`
release targets are unchanged.

## 1. Why this exists

`F4a` originally framed synthetic generation as a four-repository boundary:
`hocrsyngen` for generation, `hocrgen` for orchestration/governance/export,
`HeOCR` for mixed real+synthetic releases, and `HeOCRsynth` for synthetic-only
releases. Since then, three additional HeOCR repositories have come online
upstream of `hocrsyngen`:

- `HeOCR/public-domain-hand-written-hebrew-scans`
- `HeOCR/hletterscriptgen`
- `HeOCR/hletterscript`

These three repositories are not currently consumed directly by `hocrgen`, but
they are real upstream sources of the synthetic candidate inputs that `hocrgen`
already gates through hocrsyngen `generation_manifest.v1` batches. The wider
chain matters for provenance disclosure, rights inheritance, public dataset
documentation, and contributor guidance, even when `hocrgen` itself has no new
direct dependency on those repositories.

`F4f` is documentation-only. It does not change `project_synthetic`,
`build-release`, `export-alpha`, `export-synthetic`, `export-public-beta`,
`hocrgen hocrsyngen-preflight`, the `hocrgen_hocrsyngen_import_metadata_packet.v1`
contract, or any synthetic cap, profile, or release gate. The hard `2 / 80`
synthetic target-scale blocker, benchmark-reference blocker, privacy/review
blocker, and source-depth/composition blocker are unaffected by `F4f`.

## 2. The seven-repository chain

The HeOCR ecosystem is now a chain of seven repositories from rights-clean
real-handwriting scans through hocrgen-orchestrated public dataset releases.
Each repository owns a narrow contract and the next repository downstream
consumes only that contract:

```
public-domain-hand-written-hebrew-scans   real-handwriting page-level scan corpus
                │
                ▼
        hletterscriptgen                  framework: crop scans into per-letter glyph variants
                │
                ▼
            hletterscript                 dataset: per-writer Hebrew letter-glyph image sets
                │
                ▼
              hocrsyngen                  composes glyphs into synthetic Hebrew pages and manifests
                │  (candidate generation_manifest.v1 batches)
                ▼
               hocrgen                    orchestration, governance, review, dedupe, split, benchmark,
                │                         synthetic caps, release-relative export packaging
        ┌───────┴────────┐
        ▼                ▼
      HeOCR          HeOCRsynth           public dataset releases (mixed vs synthetic-only)
```

Real-source acquisition for the mixed `HeOCR` release stream
(`nli_any_use_permitted`, `pinkas_open`, `biblia_open`, modern
handwriting intake) is independent of this chain and continues to flow into
`hocrgen` directly through the existing source adapters. The wider chain is
specifically the synthetic provenance chain that ultimately produces the
`PROJECT-SYNTHETIC` items inside `HeOCR` and `HeOCRsynth` releases.

## 3. Per-repository scope

The contract boundaries are deliberately narrow and stay narrow. `hocrgen` does
not absorb the responsibilities of any upstream repository, and upstream
repositories must not assume hocrgen-specific release/import metadata.

### 3.1 `public-domain-hand-written-hebrew-scans`

- Canonical rights-clean dataset of modern handwritten Hebrew scans (notes,
  letters, notebook pages, drafts, forms, and similar documents).
- Newline-delimited JSON indexes are the source of truth:
  `data/index/sources.jsonl` for institution/collection/lead records and
  `data/index/entries.jsonl` for per-scan records.
- Rights evidence is recorded at both source and scan level so a single
  collection-level label cannot silently apply to every page.
- Compound licensing: repository-authored metadata is dedicated to the public
  domain under CC0 1.0, while per-scan rights are recorded individually
  per entry (typical entries are `PDM-1.0`, `LicenseRef-Public-Domain-Israel`,
  `LicenseRef-Public-Domain-Ukraine`, or `CC-BY-SA-4.0`).

### 3.2 `hletterscriptgen`

- Python package and CLI (`hletterscriptgen`) plus the `letter_set.v1`
  JSON Schema for per-writer letter sets.
- Reads scan-level records from `public-domain-hand-written-hebrew-scans`
  and is responsible for producing per-letter glyph crops for each writer.
- Hosts code, schemas, contracts, and validation tooling, but does not host
  per-letter image data; that lives in `hletterscript`.
- Code is licensed MIT; generated glyph artifacts inherit per-variant
  upstream rights from the source scan rather than being relicensed.

### 3.3 `hletterscript`

- Dataset of per-writer Hebrew letter-glyph image sets covering the 27 forms
  (22 base letters plus the 5 finals).
- JSONL-first indexes: `data/index/writers.jsonl` at writer level and
  `data/index/entries.jsonl` at per-image level, with bounding boxes,
  extraction provenance, and inherited per-variant rights.
- Image bytes live under `data/letters/<writer_id>/<letter_name>/`, tracked
  through Git LFS.
- Validation enforces upstream-scan provenance, Hebrew-letter
  codepoint/name/form consistency, re-verified file checksums and sizes, and
  pinned upstream repository identity.
- Compound licensing mirrors the upstream scans repo: repository metadata is
  CC0, per-image rights inherit from the upstream crop source.

### 3.4 `hocrsyngen`

- Owns synthetic Hebrew OCR/HTR sample generation.
- Composes glyph variants from `hletterscript` (and other governed inputs) into
  synthetic Hebrew pages and emits `generation_manifest.v1` batches with
  sample id, page assets, logical-order UTF-8 text, script/language/direction
  metadata, generator version, recipe id, seed/provenance, license
  `PROJECT-SYNTHETIC`, synthetic disclosure, and optional persona/condition
  controls (which are generator controls only and must not claim psychological
  truth, real-writer identity, or demographic authority).
- `hocrsyngen` outputs are *candidate synthetic inputs*. They are not
  release-ready data by themselves and do not satisfy public beta readiness
  on their own.

### 3.5 `hocrgen` (this repository)

- Orchestration, governance, rights/provenance disclosure, privacy, review,
  dedupe, split, benchmark, synthetic caps, release-relative export
  packaging, blocker-closure reporting, and blocked public beta packaging.
- Consumes `hocrsyngen` `generation_manifest.v1` batches as fixture-backed
  candidate inputs through `project_synthetic` and the hocrgen-hardened
  release/import fixture/import boundary; can read hocrsyngen evidence-run
  roots through the operator-only `hocrgen hocrsyngen-preflight` reader and
  emit `hocrgen_hocrsyngen_import_metadata_packet.v1` sidecars without making
  raw hocrsyngen batches release-eligible.
- Does not import hocrsyngen internals, call `hocrsyngen generate` or
  `hocrsyngen validate` from default release/export paths, contact services,
  or require network, GPU, LLM, diffusion, or other heavyweight generator
  dependencies in baseline tests or release builds.
- Does not own per-letter glyph extraction or maintain the
  `public-domain-hand-written-hebrew-scans` corpus; those responsibilities
  stay upstream.

### 3.6 `HeOCR`

- Mixed real+synthetic public dataset releases produced through
  `hocrgen export-alpha` and (when readiness gates pass) `hocrgen export-public-beta`.

### 3.7 `HeOCRsynth`

- Synthetic-only public dataset releases produced through
  `hocrgen export-synthetic` from governed release-ready synthetic items in
  hocrgen pipeline state, not by copying raw hocrsyngen generator directories.

## 4. Rights and provenance inheritance through the chain

Per-variant rights evidence must flow forward through the chain. Each layer
records rights at the smallest reasonable unit (per scan in
`public-domain-hand-written-hebrew-scans`, per glyph image in
`hletterscript`, per synthetic sample in `hocrsyngen` batches) and downstream
layers inherit and disclose those rights without relicensing.

For mixed `HeOCR` and synthetic-only `HeOCRsynth` releases, `hocrgen` is the
disclosure boundary:

- real-source items continue to carry `PD-IL`, `CC-BY-4.0`, `CC-BY-SA-4.0`,
  `HEOCR-CONSENT-OPEN`, or another release-compatible normalized rights value
- synthetic items carry `PROJECT-SYNTHETIC` plus synthetic disclosure and
  the hocrgen-hardened provider/rendering/Hebrew coverage metadata
- the synthetic provenance chain from
  `public-domain-hand-written-hebrew-scans` through `hletterscriptgen` and
  `hletterscript` to `hocrsyngen` is upstream context; `hocrgen` is not
  required to publish per-glyph upstream identifiers for synthetic items
  unless a future governance PR explicitly changes the public contract

The compound licensing model in the upstream scans and letter-glyph
repositories (CC0 metadata, per-record/per-image rights) does not contradict
hocrgen's normalized release-compatible rights values. ShareAlike caveats from
upstream `CC-BY-SA-4.0` material remain the upstream repositories'
responsibility to label, and `hocrgen` must not promote ShareAlike material
into release-ready bundles that imply public-domain-equivalent reuse.

## 5. Contract boundaries and non-goals

`F4f` does not change any contract. In particular:

- `hocrgen` continues to import zero code from
  `public-domain-hand-written-hebrew-scans`, `hletterscriptgen`,
  `hletterscript`, or `hocrsyngen`.
- `hocrgen` continues to read `hocrsyngen` output only as fixture-backed
  candidate input through its existing source adapter and the operator-only
  evidence-root preflight; it does not call upstream CLIs from default release
  or export commands.
- `hocrgen` does not validate `hletterscriptgen` `letter_set.v1` documents,
  re-verify `hletterscript` image checksums, or duplicate
  `public-domain-hand-written-hebrew-scans` rights validation. Those checks
  remain the upstream repositories' responsibility.
- Public release manifests, item manifests, benchmark manifests, benchmark
  references, annotation manifests, release diffs, and release records are
  unchanged.
- The public beta readiness report, blocker-closure plan, repo-owned blocker
  report, source-depth/composition report, takedown/private reporting
  evidence, and `hocrgen_hocrsyngen_import_metadata_packet.v1` are unchanged.

## 6. Where this framing lives

`F4f` is recorded in:

- this document
- the F4 section of [`HeOCR_hocrgen_long_term_roadmap.md`](./HeOCR_hocrgen_long_term_roadmap.md)
- the "External generator boundary" section of [`synthetic_asset_contribution_guide.md`](./synthetic_asset_contribution_guide.md)
- the HeOCR ecosystem section of [`../README.md`](../README.md)
- the upstream-chain reference in [`../.agent-plan.md`](../.agent-plan.md)
- the design/spec discussion of the synthetic provider boundary in
  [`hocrgen_design_and_spec.md`](./hocrgen_design_and_spec.md)

The original `F4a` planning amendments under
[`2026_05_02_heocrsyn_spinout/`](./2026_05_02_heocrsyn_spinout/) are
historical and remain unchanged.
