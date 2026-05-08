# hocrsyngen Adapter Preflight Plan

## Planning Notation

- notation: `F6f1`
- parent milestone: `F6 - Public beta closure and external input integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`
- status on this ref: completed (planning-only; no runtime behavior)

## Purpose

`F6f1` defines the hocrgen-side preflight required before hocrgen can safely consume current hocrsyngen S6 outputs. It is a diagnostic adapter plan, not a release-path integration. It does not implement the preflight command on this ref, does not add a command, does not change `project_synthetic`, does not change `build-release`, `export-alpha`, `export-synthetic`, or `export-public-beta`, and does not relax current hocrgen synthetic release gates.

The key finding from the S6 handoff review is that hocrsyngen is ready to emit deterministic candidate Hebrew OCR/HTR batches through installed public CLI surfaces, but raw hocrsyngen `generation_manifest.v1` output is not yet in the hocrgen hardened release/import metadata form expected by the current default synthetic source path.

## Review Findings

The installed hocrsyngen CLI surfaces that hocrgen can use for a future preflight are:

- `hocrsyngen templates --format json`
- `hocrsyngen templates --format json --catalog-version v2`
- `hocrsyngen contracts --format json`
- `hocrsyngen contracts export --fixture-id generation_manifest_v1_fixture_batch --output PATH --format json`
- `hocrsyngen generate --count N --seed S --output PATH --format json`
- `hocrsyngen generate --count N --seed S --output PATH --rendering-coverage-report --format json`
- `hocrsyngen validate PATH --format json`

The live S6 review confirmed that these surfaces expose `template_catalog.v1`, `template_catalog.v2`, `contract_fixture_catalog.v1`, `contract_fixture_export.v1`, `generation_report.v1`, `validation_report.v1`, valid public `generation_manifest.v1` manifests, portable relative POSIX asset paths, canonical sample/page ids, SHA-256 page hashes, logical-order UTF-8 Hebrew text, NFC normalization, and `(template_id, recipe_id)` values that can join to `template_catalog.v2`.

The compatibility gap is hocrgen-side and comes from two deliberately separate shapes. The public hocrsyngen `generation_manifest.v1` shape is the upstream batch contract emitted by hocrsyngen. The hocrgen-hardened fixture/import form is the current hocrgen release-path adapter shape derived from that public batch plus hocrgen-owned release/import metadata. The existing hocrgen adapter expects the hardened fixture/import form and therefore validates additional metadata, including top-level `provider_metadata`, per-sample `rendering_metadata`, and per-sample `hebrew_coverage`. hocrsyngen public `generation_manifest.v1` intentionally does not include those fields, and hocrgen should not ask hocrsyngen to mutate manifest v1 to satisfy hocrgen's current hardened model.

## Observed S6 Handoff Evidence

The S6 handoff review exercised hocrsyngen from installed CLI surfaces on hocrsyngen `main` in an operator-local temporary directory. The temporary output path is not a hocrgen release artifact; the durable evidence is the command contract and observed JSON shape below.

| Command shape | Observed JSON contract/evidence |
| --- | --- |
| `hocrsyngen templates --format json` | `schema_version: template_catalog.v1`; `template_count: 7` |
| `hocrsyngen templates --format json --catalog-version v2` | `schema_version: template_catalog.v2`; `template_count: 7` |
| `hocrsyngen contracts --format json` | `schema_version: contract_fixture_catalog.v1`; fixture `generation_manifest_v1_fixture_batch`; `sample_count: 2`; `page_count: 2` |
| `hocrsyngen contracts export --fixture-id generation_manifest_v1_fixture_batch --output PATH --format json` | `schema_version: contract_fixture_export.v1`; exported `generation_manifest.json`; `sample_count: 2`; `page_count: 2` |
| `hocrsyngen validate PATH --format json` against the exported fixture | `schema_version: validation_report.v1`; `valid: true`; `sample_count: 2`; `page_count: 2` |
| `hocrsyngen generate --count 4 --seed 101 --output PATH --rendering-coverage-report --format json` | `schema_version: generation_report.v1`; `sample_count: 4`; `page_count: 4`; `rendering_coverage_report_path` present |
| `hocrsyngen validate PATH --format json` against the generated batch | `schema_version: validation_report.v1`; `valid: true`; `sample_count: 4`; `page_count: 4` |

The public exported manifest shape observed in that review had top-level keys `generator_name`, `license`, `manifest_version`, `samples`, and `synthetic_disclosure`; sample keys `controls`, `generator_version`, `license`, `pages`, `provenance`, `recipe_id`, `sample_id`, `synthetic_disclosure`, and `text`; and page keys `asset_path`, `height`, `media_type`, `page_id`, `sha256`, and `width`.

The hocrgen-side hardened validator failure that motivates `F6f1` was explicit and expected for public hocrsyngen output: `hocrsyngen generation_manifest.v1 validation failed`, with missing `provider_metadata`, missing `samples.0.rendering_metadata`, missing `samples.0.hebrew_coverage`, missing `samples.1.rendering_metadata`, and missing `samples.1.hebrew_coverage`. That failure is not a request for hocrsyngen to mutate public manifest v1; it is the evidence that hocrgen needs a downstream import metadata form or downstream metadata computation before `F6f2`.

## Boundary Decision

hocrgen must either compute/import the missing provider, rendering, and Hebrew coverage metadata downstream, or define a separate hocrgen-owned import packet or sidecar. That hocrgen-owned form can cite hocrsyngen public manifests, validation reports, generation reports, template catalogs, optional rendering coverage reports, and downstream review/cap/profile evidence. It must not become a hocrsyngen manifest v1 extension by accident.

`F6f1` therefore plans an operator-only preflight that reports this metadata gap explicitly. `F6f2` remains the later integration step that can wire a larger target-scale batch into hocrgen only after that downstream import metadata form is settled.

## Planned hocrgen CLI Contract

`F6f1` does not implement this command on this ref, but it names the future operator surface so `F6f2` does not fork into incompatible preflight interpretations.

- Command name: `hocrgen hocrsyngen-preflight`
- Required output argument: `--output-dir PATH`
- hocrsyngen executable selection: `--hocrsyngen-executable PATH_OR_NAME`, defaulting to `hocrsyngen` resolved from `PATH`; the future implementation should execute it as an argument vector, not through shell parsing
- Mode: `--mode fixture|generate`, defaulting to `fixture`
- Fixture mode: runs the packaged fixture export for `generation_manifest_v1_fixture_batch` into `${output_dir}/source_batch` and records the contracts catalog/export JSON under `${output_dir}/reports/`
- Generate mode: requires `--count N --seed S`, writes the generated batch into `${output_dir}/source_batch`, and may accept `--rendering-coverage-report` to retain advisory rendering coverage JSON
- Diagnostic report path: `--report PATH`, defaulting to `${output_dir}/hocrsyngen_preflight_report.json`
- Raw hocrsyngen JSON retention: write command JSON outputs under `${output_dir}/reports/` with checksums referenced from the diagnostic report
- Overwrite policy: refuse existing output directories, `source_batch`, retained raw reports, or diagnostic report paths unless `--overwrite` is supplied; overwrite should replace only command-owned output subtrees
- Timeout policy: `--timeout-seconds N`, defaulting to `120`
- Exit `0`: all installed-CLI calls, public JSON validations, manifest validation, asset path checks, asset hash recomputation, asset readability/dimension checks, and `template_catalog.v2` joins pass, and the diagnostic report is written with `release_eligible: false`
- Exit `1`: hocrsyngen command failure, malformed/missing JSON, invalid public manifest, failed asset/hash/catalog checks, missing required evidence, or missing hocrgen release/import metadata; write a diagnostic report when possible
- Exit `2`: local usage/setup failure before batch validation, including invalid arguments, unsafe output paths, missing executable, or overwrite refusal

The future command must remain operator-only. It must not call `project_synthetic`, `build-release`, `export-alpha`, `export-synthetic`, or `export-public-beta`; it must not mutate hocrgen config; and exit `0` must still mean diagnostic preflight success rather than release eligibility.

## Future Preflight Workflow

The future `hocrgen hocrsyngen-preflight` operator command should:

1. Call installed hocrsyngen CLI commands only.
2. Capture and validate `template_catalog.v2`.
3. Capture and validate `contracts` and fixture export reports when fixture mode is used.
4. Capture and validate `generation_report.v1` when generated-batch mode is used.
5. Run `hocrsyngen validate PATH --format json` and fail closed when validation JSON is missing, malformed, non-JSON, non-zero, or reports `valid == false`.
6. Validate the public `generation_manifest.v1` shape without requiring hocrgen-only release metadata inside that manifest.
7. Reject unsafe asset paths, including absolute paths, drive prefixes, backslashes, URL-like references, `.` parts, `..` parts, and paths that resolve outside the validated batch root.
8. Recompute SHA-256 for each page asset and fail closed on mismatches.
9. Verify every page asset exists, is readable, is JPEG, and matches declared dimensions.
10. Preserve manifest `sample_id`, `pages[].page_id`, and `pages[].asset_path` exactly in the diagnostic report.
11. Join each manifest `(provenance.template_id, provenance.recipe_id)` pair to `template_catalog.v2` and fail closed when the join is missing.
12. Retain optional `rendering_coverage_report.v1` as advisory coverage evidence outside manifest v1 when generated.
13. Emit an operator-only hocrgen audit report that is not release eligibility.

## Diagnostic Report Expectations

The future report should be explicitly diagnostic and should include at least:

- report schema/version, planning notation `F6f1`, status, and artifact scope `operator_only`
- exact hocrsyngen command strings and return codes
- paths and SHA-256 checksums for retained hocrsyngen JSON reports
- source batch root, source batch boundary id, manifest path, and manifest SHA-256
- hocrsyngen generator version values observed in the manifest, including a limitation if mixed or unavailable
- sample ids, page ids, and relative asset paths retained exactly as serialized
- asset path policy and asset hash recomputation policy
- template catalog version and `(template_id, recipe_id)` join results
- optional rendering coverage report reference and checksum when present
- controls retained from `controls.persona` and `controls.condition` without inferring real identity, authorship, medical, psychological, disability, demographic, sensitive-attribute, or real-source provenance meaning
- limitations for missing downstream realism evidence, utility evidence, diversity/domain-shift evidence, release cap records, review evidence sidecars, candidate profile/mix records, and hocrgen-owned release/import metadata
- explicit `release_eligible: false`

Missing hocrgen-side `provider_metadata`, `rendering_metadata`, and `hebrew_coverage` must be reported as missing release/import metadata for the current hocrgen release path. The diagnostic preflight can still validate public hocrsyngen manifest/assets/catalog behavior, but it must not silently promote raw hocrsyngen output into hocrgen release eligibility.

## Non-Goals

`F6f1` does not:

- implement the preflight command on this ref
- wire raw hocrsyngen output into `project_synthetic`
- change `build-release`, `export-alpha`, `export-synthetic`, or `export-public-beta`
- relax current hocrgen release-path gates
- import hocrsyngen private Python internals
- call hocrsyngen CLI commands from default release/export paths
- require REST, GPU, LLM, diffusion, or network services
- treat successful hocrsyngen generation or validation as release eligibility
- ask hocrsyngen to add hocrgen-owned release/import metadata fields to `generation_manifest.v1`

## F6f2 Entry Criteria

`F6f2` should not start until hocrgen has a settled downstream import metadata form. That form can be computed by hocrgen or represented as a hocrgen-owned sidecar/import packet, but it must preserve current public-boundary constraints and keep review, dedupe, split, benchmark, caps, export, publication, and governance in hocrgen.
