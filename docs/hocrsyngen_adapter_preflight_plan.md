# hocrsyngen Adapter Preflight Plan

## Planning Notation

- notation: `F6f1`
- parent milestone: `F6 - Public beta closure and external input integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`
- status on this ref: planning-only

## Purpose

`F6f1` defines the hocrgen-side preflight required before hocrgen can safely consume current hocrsyngen S6 outputs. It is a diagnostic adapter plan, not a release-path integration. It does not add a command, does not change `project_synthetic`, does not change `build-release`, `export-alpha`, `export-synthetic`, or `export-public-beta`, and does not relax current hocrgen synthetic release gates.

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

The compatibility gap is hocrgen-side: current hocrgen release-path validation expects additional hardened release/import metadata, including top-level `provider_metadata`, per-sample `rendering_metadata`, and per-sample `hebrew_coverage`. hocrsyngen public `generation_manifest.v1` intentionally does not include those fields, and hocrgen should not ask hocrsyngen to mutate manifest v1 to satisfy hocrgen's current hardened model.

## Boundary Decision

hocrgen must either compute/import the missing provider, rendering, and Hebrew coverage metadata downstream, or define a separate hocrgen-owned import packet or sidecar. That hocrgen-owned form can cite hocrsyngen public manifests, validation reports, generation reports, template catalogs, optional rendering coverage reports, and downstream review/cap/profile evidence. It must not become a hocrsyngen manifest v1 extension by accident.

`F6f1` therefore plans an operator-only preflight that reports this metadata gap explicitly. `F6f2` remains the later integration step that can wire a larger target-scale batch into hocrgen only after that downstream import metadata form is settled.

## Future Preflight Workflow

A future hocrgen operator command or workflow should:

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
