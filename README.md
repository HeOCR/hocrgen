# hocrgen

`hocrgen` is the open-source dataset operations toolchain for the HeOCR project.

This repository now implements a conservative review-readiness, source-operations, and benchmark-subset pipeline on top of the earlier acquisition, normalization, technical-QA, and exact-curation milestones. The current implementation remains intentionally fixture/sample-driven, but it now performs real source ingestion, source health checks, rights filtering, asset materialization, technical normalization, exact item-level deduplication, lightweight heuristic classification, metadata-based privacy screening, review-queue export, deterministic split assignment over release-ready items, benchmark v1 selection, and curated dry-run release assembly.

## What `hocrgen` can do today

- validate typed source, profile, and license config
- validate source-operations settings and fixture-backed source health expectations
- ingest a seed-driven NLI source for items explicitly marked `Any Use Permitted`
- ingest bounded static sample packages for Pinkas and BiblIA
- generate deterministic synthetic Hebrew sample documents as degraded JPEG assets
- normalize rights into controlled license values and policy classifications
- apply release-profile eligibility rules
- report source health and skip frozen/degraded sources with explicit reasons
- materialize acquired/generated sample assets into a run workdir
- normalize acquired assets into a stable run layout with technical metadata
- compute checksums, dimensions, file sizes, and format metadata
- generate preview copies for supported SVG/raster assets
- emit QA pass/fail reports and normalized-item manifests
- perform exact item-level deduplication using ordered normalized-asset checksums
- classify retained items with heuristic content/period/language/quality labels
- apply conservative metadata-based privacy rules before release assembly
- export review-ready, blocked, and release-ready subsets as machine-readable manifests
- merge repo-tracked review decisions and allow/block overrides back into release gating
- assign deterministic `train` / `validation` / `test` splits over the release-ready deduped set
- select an explicit, repo-approved `benchmark_v1` subset from release-ready items
- carry optional transcription and layout-label reference slots without requiring annotations for release-ready items
- emit curated release manifests with duplicate-cluster, review-queue, split, and leakage-report artifacts

## Supported sources in the current MVP

- `nli_any_use_permitted`
  - implemented as a conservative seed-manifest flow
  - parses committed sample HTML item pages
  - extracts title, description, rights text, and page-image references
- `pinkas_open`
  - static importer over a packaged sample record set
  - current committed sample asset is a packaged real historical page normalized as `PD-IL`
- `biblia_open`
  - static importer over a packaged sample record set
  - current committed sample asset is a packaged real historical page normalized as `PD-IL`
- `project_synthetic`
  - deterministic JPEG-based synthetic generator
  - includes governed packaged Hebrew fonts and a curated Hebrew text corpus

This is not a broad crawler yet. The NLI support is intentionally narrow and reliable rather than site-wide.

The NLI seed data is split on purpose:

- runnable fixture-backed seeds live in [`src/hocrgen/data/nli/seeds.yaml`](./src/hocrgen/data/nli/seeds.yaml)
- broader exploratory/manual candidate URLs live in [`src/hocrgen/data/nli/seed_catalog.yaml`](./src/hocrgen/data/nli/seed_catalog.yaml)

To promote exploratory entries into runnable local fixtures, use the local operator script:

```bash
python scripts/promote_nli_seeds.py \
  --seed-id nli-ms-seed-001 \
  --browser-state-dir .cache/nli-playwright
```

The script opens a persistent browser, lets you solve any Cloudflare challenge once, captures the current item into a normalized local fixture HTML plus local asset files, appends the promoted entry to `seeds.yaml`, removes it from `seed_catalog.yaml`, and writes a machine-readable promotion report.

If Cloudflare resists Playwright-launched Chromium, the script can instead attach to a normal Chrome instance that you launch yourself with remote debugging enabled:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/hocrgen-chrome
```

Then open the target NLI item page in that browser, solve any challenge there, and run:

```bash
python scripts/promote_nli_seeds.py \
  --seed-id nli-ms-seed-001 \
  --connect-cdp http://127.0.0.1:9222 \
  --manual-wait-timeout 90 \
  --pause-on-every-challenge
```

## What is still future work

- broad live-source crawling
- near-duplicate / perceptual deduplication
- OCR-aware privacy screening
- advanced classification and later benchmark/evaluation utilities
- final publication to Hugging Face or the GitHub dataset repo
- full release packaging maturity

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Validate config

```bash
hocrgen config validate
```

This validates:

- committed sources under [`src/hocrgen/config/sources.yaml`](./src/hocrgen/config/sources.yaml)
- release profiles under [`src/hocrgen/config/profiles`](./src/hocrgen/config/profiles)
- normalized license mappings under [`src/hocrgen/config/licenses.yaml`](./src/hocrgen/config/licenses.yaml)
- technical QA thresholds under [`src/hocrgen/config/quality_thresholds.yaml`](./src/hocrgen/config/quality_thresholds.yaml)
- privacy rules under [`src/hocrgen/config/privacy_rules.yaml`](./src/hocrgen/config/privacy_rules.yaml)
- benchmark v1 approvals and stability policy under [`benchmark_data/benchmark_v1/config.json`](./benchmark_data/benchmark_v1/config.json)

## Run a real Milestone 5 dry-run

```bash
hocrgen build-release --profile profile_open_v1 --dry-run
```

This now runs a real sample-backed pipeline and emits populated artifacts such as:

```text
.work/hocrgen/
  runs/
    <run_id>/
      run.json
      summary.json
      logs/run.log
      discover/candidates.json
      discover/source_health.json
      fetch_metadata/enriched_candidates.json
      policy_filter/accepted_items.json
      policy_filter/rejected_items.json
      acquire/acquired_items.json
      acquire/assets/
      normalize/normalized_items.json
      normalize/failed_items.json
      normalize/qa_report.json
      normalize/assets/
      normalize/thumbnails/
      dedupe/retained_items.json
      dedupe/duplicate_items.json
      dedupe/duplicate_relations.json
      dedupe/duplicate_clusters.json
      dedupe/report.json
      classify/classified_items.json
      classify/summary.json
      privacy_scan/privacy_scanned_items.json
      privacy_scan/summary.json
      review/queue.json
      review/release_ready_items.json
      review/review_required_items.json
      review/blocked_items.json
      review_merge/release_ready_items.json
      review_merge/unresolved_items.json
      review_merge/rejected_items.json
      review_merge/decision_audit.json
      split/split_manifest.json
      split/leakage_report.json
      build_release/item_manifest.json
      build_release/removed_duplicate_items.json
      build_release/duplicate_relations.json
      build_release/duplicate_clusters.json
      build_release/review_queue.json
      build_release/review_required_items.json
      build_release/blocked_items.json
      build_release/decision_audit.json
      build_release/split_manifest.json
      build_release/leakage_report.json
      build_release/release_summary.json
      build_release/source_stats.json
      build_release/annotation_manifest.json
      build_release/classification_stats.json
      build_release/privacy_stats.json
      build_release/benchmark_manifest.json
      build_release/benchmark_selection_audit.json
      build_release/benchmark_stability_policy.json
      build_release/BENCHMARK_CARD.md
```

## Stage commands

Each stage command is now meaningfully functional:

```bash
hocrgen discover --profile profile_open_v1 --dry-run
hocrgen fetch-metadata --profile profile_open_v1 --dry-run
hocrgen policy-filter --profile profile_open_v1 --dry-run
hocrgen acquire --profile profile_open_v1 --dry-run
hocrgen normalize --profile profile_open_v1 --dry-run
hocrgen dedupe --profile profile_open_v1 --dry-run
hocrgen classify --profile profile_open_v1 --dry-run
hocrgen privacy-scan --profile profile_open_v1 --dry-run
hocrgen review-export --profile profile_open_v1 --dry-run
hocrgen review-merge --profile profile_open_v1 --dry-run
hocrgen split --profile profile_open_v1 --dry-run
hocrgen build-release --profile profile_open_v1 --dry-run
hocrgen export-alpha --profile profile_open_v1 --dry-run
```

Useful implemented flags:

```bash
hocrgen build-release --profile profile_open_v1 --dry-run --source nli_any_use_permitted
hocrgen build-release --profile profile_open_v1 --dry-run --max-items 1
hocrgen build-release --profile profile_open_v1 --dry-run --seed 23
```

## Alpha export

`export-alpha` builds on the existing `build-release` outputs and writes a versioned release tree that is shaped for the separate `HeOCR` repository.

Default usage:

```bash
hocrgen export-alpha --profile profile_open_v1 --dry-run
```

By default the export is written under:

```text
.work/hocrgen/exports/alpha-v0/
```

To write directly into a checkout of the separate `HeOCR` repo:

```bash
hocrgen export-alpha \
  --profile profile_open_v1 \
  --dry-run \
  --heocr-repo /path/to/HeOCR
```

The alpha exporter:

- copies only the public `release_ready` subset into `data/<split>/<item_id>/`
- keeps `review_required` and `blocked` items as audit manifests only
- caps synthetic inclusion at `2x` the exported real-item count, still bounded by `--max-synthetic-items`
- writes repo-ready manifests under `manifests/`
- writes `release_diff.json` with added/removed/changed item reporting against the prior exported release when one is available
- writes `annotation_manifest.json` as an additive, optional map for future transcription and layout-label references
- mirrors `benchmark_v1` manifests and `BENCHMARK_CARD.md` for the exported release-ready benchmark items
- rewrites review preview references into release-local files under `manifests/review_previews/`
- writes `CHANGELOG.md`, `DATASET_CARD.md`, `RELEASE_NOTES.md`, `PROVENANCE.md`, `BENCHMARK_CARD.md`, and `HANDOFF.md` under `docs/`

By default `export-alpha` auto-discovers the previous sibling release under the same export root and compares against it. To override that baseline explicitly:

```bash
hocrgen export-alpha \
  --profile profile_open_v1 \
  --dry-run \
  --version alpha-v1 \
  --compare-to /path/to/HeOCR/releases/alpha-v0
```

If no previous release is found, `export-alpha` still emits `release_diff.json` and `CHANGELOG.md` as an initial-release summary with all current exported items listed as additions.

The current alpha exemplar path now includes a high-resolution NLI manuscript fixture and a text-bearing Pinkas interior page so the real-scan subset is no longer placeholder-grade.

When `--heocr-repo` is provided, `hocrgen` validates that the target is a git checkout and exports directly to `releases/<version>/` inside that repository.

The current pre-alpha freeze sequencing and blocker list lives in [`docs/pre_alpha_freeze_plan.md`](./docs/pre_alpha_freeze_plan.md).

Kaggle and Hugging Face publication remain out of scope for alpha releases.

## Rights normalization and policy behavior

The current milestone normalizes rights into these controlled values:

- `PD-IL`
- `CC-BY-4.0`
- `CC-BY-SA-4.0`
- `PROJECT-SYNTHETIC`
- `RESTRICTED-NONOPEN`
- `UNKNOWN`

And these policy classes:

- `open`
- `open_with_attribution`
- `sharealike`
- `restricted_review_only`
- `blocked`

The default public profile is conservative: unknown or non-public rights are rejected during `policy-filter`.

## Normalization and technical QA

Milestone 3 adds a real `normalize` stage that operates on acquired assets and writes a stable release-prep layout under the run workdir.

What normalization does today:

- verifies the acquired asset exists and is non-empty
- checks that the asset is decodable as a supported SVG, PNG, or JPEG image
- extracts technical metadata such as width, height, file size, media type, and `sha256`
- copies the asset into a normalized layout under `normalize/assets/`
- generates a preview copy under `normalize/thumbnails/` for supported SVG/raster formats
- evaluates threshold-based QA rules and writes pass/fail reasons

Current QA thresholds are configured in [`src/hocrgen/config/quality_thresholds.yaml`](./src/hocrgen/config/quality_thresholds.yaml). The current implementation is conservative and lightweight:

- SVG is supported and treated explicitly as vector input
- raster support covers PNG and JPEG
- preview generation currently uses a copied normalized asset for supported formats instead of raster re-rendering
- unsupported formats are rejected with structured QA reasons

See [`docs/hocrgen_normalization_and_qa.md`](./docs/hocrgen_normalization_and_qa.md) for the artifact layout and QA report shape.

## Classification, privacy, review export, and review merge

Milestone 5 adds a conservative review-readiness layer after exact dedupe.

What it does today:

- classifies retained deduped items as `handwritten`, `printed`, or `mixed`
- assigns heuristic `historical` / `modern` period labels and Hebrew-only vs mixed-language labels
- emits a lightweight quality score and tier for downstream review/export logic
- applies metadata-first privacy rules from [`src/hocrgen/config/privacy_rules.yaml`](./src/hocrgen/config/privacy_rules.yaml)
- routes items into `release_ready`, `review_required`, or `blocked` outcomes
- exports a stable review queue with preview paths and suggested decision types
- auto-applies repo-tracked manual review decisions plus allow/block overrides during `review-merge` and `build-release`

The default public profile is conservative:

- `privacy_flag=clear` items can proceed to split and release assembly
- `possible_personal_data` and `needs_review` items are routed to the review queue
- `blocked_sensitive` items are excluded from both the review queue and the release-ready split set

The review workflow is now:

1. run `hocrgen review-export --profile profile_open_v1 --dry-run`
2. add one-record-per-file JSON inputs under [`review_data/`](./review_data):
   `manual_decisions/`, `allowlists/`, and `blocklists/`
3. run `hocrgen review-merge --profile profile_open_v1 --dry-run` or `hocrgen build-release --profile profile_open_v1 --dry-run`
4. inspect `review_merge/unresolved_items.json` until the remaining set is acceptable for the target release

`hocrgen config validate` now also validates the committed `review_data/` tree and reports its item counts.

What it still does not do:

- inspect image text via OCR
- perform scholarly/semantic classification

## Deduplication and split assignment

Milestone 4 remains the curation base that Milestone 5 builds on.

What it does today:

- computes an item-level content fingerprint from the ordered list of normalized-asset `sha256` values
- detects exact duplicate items when those ordered asset sequences match exactly
- retains a deterministic canonical item using source priority, then non-synthetic preference, then `item_id`
- emits duplicate-cluster and duplicate-relation manifests
- assigns deterministic `train` / `validation` / `test` splits using the profile `split_policy`
- keeps duplicate clusters and source-item groups together by using stable split-group ids
- emits a leakage report confirming that release-ready items do not cross split boundaries incorrectly

What it does not do yet:

- perceptual or semantic near-duplicate detection
- OCR-aware grouping
- content-quality ranking beyond technical QA

## Benchmark subset

`benchmark_v1` is a small, explicitly approved benchmark-facing slice emitted by `build-release` and mirrored by `export-alpha`.

The initial benchmark contains two real release-ready exemplars plus one governed synthetic control item. Every benchmark item must be named in [`benchmark_data/benchmark_v1/config.json`](./benchmark_data/benchmark_v1/config.json), must remain release-ready after review merge, and must keep its committed benchmark split. If an approved item becomes unresolved, blocked, duplicate-removed, missing from the current run, or assigned to a different split, `build-release` fails with a structured stage error.

Benchmark artifacts:

- `build_release/benchmark_manifest.json`
- `build_release/benchmark_selection_audit.json`
- `build_release/benchmark_stability_policy.json`
- `build_release/BENCHMARK_CARD.md`
- exported release mirrors under `manifests/` and `docs/BENCHMARK_CARD.md`

## Annotation readiness

`hocrgen` reserves typed, optional annotation slots on item manifests so future annotated subsets can attach release-relative transcription and layout-label files without changing the core release flow.

Current alpha and release builds do not require transcriptions. Items default to `annotation_status: not_available`, `transcription: null`, and `layout_labels: []`. `build-release` emits `build_release/annotation_manifest.json`; `export-alpha` mirrors it to `manifests/annotation_manifest.json`. Annotation references must remain portable and release-relative, such as `annotations/<item_id>/transcription.json`, so public exports do not depend on local `.work/` paths.

## Synthetic generation

The synthetic subsystem is modest but real:

- deterministic from seed
- outputs degraded JPEG page assets plus reproducibility metadata
- uses tracked governed fonts from [`src/hocrgen/data/synthetic/fonts/manifest.yaml`](./src/hocrgen/data/synthetic/fonts/manifest.yaml)
- uses a curated packaged Hebrew text corpus from [`src/hocrgen/data/synthetic/texts/hebrew_lines.txt`](./src/hocrgen/data/synthetic/texts/hebrew_lines.txt)
- supports a printed-style and handwritten-look template family with stable recipe and degradation metadata
- applies a conservative Hebrew RTL display-order heuristic before Pillow rendering for environments without optional RTL layout libraries; this is not full bidi-aware layout and may be inaccurate for mixed-direction text
- renders printed pages with form-like guide lines, identifiers, stamps, ink variation, paper edges, stains, and scan-like degradation
- renders handwritten-look pages with looser line placement, marginal notes, underlines, creases, stronger paper wear, and worn notebook-style degradation
- can limit generation by existing synthetic metadata with `--synthetic-template`, `--synthetic-recipe`, and `--synthetic-degradation-preset`
- emits `synthetic_composition.json` during `build-release` and `export-alpha`, with template, recipe, degradation preset, font, split, and synthetic fraction counts
- keeps synthetic release inclusion bounded by profile and alpha export caps while allowing both default D4a recipes into the conservative public profile

## Fixtures and tests

All tests are network-free and run against committed fixtures/sample data.

Key fixture locations:

- [`src/hocrgen/data/nli`](./src/hocrgen/data/nli)
- [`src/hocrgen/data/pinkas`](./src/hocrgen/data/pinkas)
- [`src/hocrgen/data/biblia`](./src/hocrgen/data/biblia)
- [`tests/fixtures`](./tests/fixtures)

## Development checks

```bash
pytest
hocrgen config validate
hocrgen normalize --profile profile_open_v1 --dry-run
hocrgen dedupe --profile profile_open_v1 --dry-run
hocrgen classify --profile profile_open_v1 --dry-run
hocrgen privacy-scan --profile profile_open_v1 --dry-run
hocrgen review-export --profile profile_open_v1 --dry-run
hocrgen split --profile profile_open_v1 --dry-run
hocrgen build-release --profile profile_open_v1 --dry-run
```

## Planned PR workflow

When implementation work is being driven from the roadmap or another concrete plan, the PR itself should update the current-state and human-facing planning documents in the same branch. In practice, a planned PR should usually include:

- `.agent-plan.md` for the immediate execution state and next-step tracker
- `README.md` when current capabilities, workflow expectations, or operator guidance changed
- the relevant planning docs under [`docs/`](./docs/) when milestone state, critical path, or implementation sequencing changed

Planned PR metadata should also follow a stable notation rule:

- PR title: `<notation>: <sentence-case summary>` such as `B5b4: finalize alpha freeze handoff and planned PR naming`
- PR body: include a top-level `## Planning notation` section with the notation, parent milestone, and plan source
- If a PR belongs to a planned milestone but no notation exists yet, define the notation in the planning docs before opening the PR
- Retire generic `[codex] ...` titles for planned work; use a plain summary title for unplanned/ad hoc PRs unless another repo-specific rule overrides it

Roadmap notation is location-based. When a notation such as `D2a` appears in repo docs, it means the
work is implemented on the current ref being read. On an implementation branch that means the branch
contains the work; after merge, the same wording means `main` contains the work. Write durable
planning docs in current-ref language so they do not become stale after the merge.

This keeps the machine-readable state tracker and the human-facing planning documents aligned with the code that just landed, instead of leaving planning updates as a later cleanup task.

When checking "what is next" or whether a roadmap item is still open, use this order of precedence:

1. merged code on `main`
2. merged GitHub PR history for the notation
3. roadmap and planning tables under [`docs/`](./docs/)
4. [`.agent-plan.md`](./.agent-plan.md) as the current merged-main summary

If these disagree, treat `main` plus merged PR history as authoritative and reconcile the planning docs before starting the next roadmap item.

## Source operations

`D2a` adds a deterministic source-health layer around the fixture-backed source adapters. Each source
has typed source-operations config with an `active`, `frozen`, or `degraded` operational status,
an operator-facing reason for non-active states, and optional minimum health expectations.

During `discover`, `hocrgen` validates the configured fixture manifests, packaged record files,
synthetic font/text assets, and configured minimum counts. The run emits
`discover/source_health.json`, includes a source-health rollup in `discover/summary.json`, and carries
the same rollup into `build_release/source_stats.json`.

Frozen and degraded sources are skipped conservatively with explicit reporting. Publication remains
manual, and D2a does not introduce live crawling, network health checks, retry/backoff automation, or
last-good snapshot reuse.

## PR agent context

This repository publishes `pr-agent-context` comments for pull requests and later refresh events.

- [`.github/workflows/validate.yml`](./.github/workflows/validate.yml) runs the test and smoke-check
  suite, exports a combined `coverage.xml`, uploads it as the `coverage-xml` artifact, and invokes
  `pr-agent-context` on pull requests.
- [`.github/workflows/pr-agent-context-refresh.yml`](./.github/workflows/pr-agent-context-refresh.yml)
  handles later review/check signals, re-runs `pr-agent-context` in refresh mode, and includes a
  repo-owned `schedule` to `workflow_dispatch` fallback for same-repo PRs when approval-gated bot
  events would otherwise leave refresh waiting.

Both workflows use XML-based patch coverage inputs:

- `patch_coverage_source_mode: coverage_xml_artifact`
- `coverage_report_artifact_name: coverage-xml`
- `coverage_report_filename: coverage.xml`

Both workflows also use `publish_mode: append`, so refresh runs append new managed comments rather
than updating earlier ones.

The refresh workflow follows the hardened `pr-agent-context` v4 pattern and intentionally uses the
floating `v4` major reference for both the reusable workflow ref and `tool_ref`:

- normal review and external-check-triggered refresh behavior stays enabled
- scheduled fanout dispatches explicit refresh runs only for same-repo PRs
- dispatch inputs carry explicit PR number plus base/head SHA overrides into the reusable workflow
- scheduled dispatches dedupe on both current managed refresh comments and recent/in-flight
  SHA-specific `workflow_dispatch` runs
- refresh runs continue to reuse the `Validate` workflow's `coverage-xml` artifact via
  `coverage_xml_artifact` plus cross-run coverage lookup

## Scheduled Dry-Run Automation

`D1a` adds a GitHub-first dry-run maintenance backbone without enabling automatic publishing,
auto-generated PRs, or workflow-driven commits.

- [`.github/workflows/hocrgen-dry-run.yml`](./.github/workflows/hocrgen-dry-run.yml) is a reusable
  workflow that installs the repo, runs one dry-run stage command, uploads the resulting run
  directory as an artifact, and appends a Markdown summary to the Actions job summary via
  `hocrgen summarize-run --format markdown`.
- [`.github/workflows/expansion-maintenance.yml`](./.github/workflows/expansion-maintenance.yml)
  orchestrates recurring review-profile discovery, resumable review builds, synthetic-only dry-run
  builds, and open-profile dry-run builds on a weekly schedule or manual dispatch.

The orchestrator accepts these manual-dispatch inputs:

- `run_scope`: `all`, `discovery`, `synthetic`, `review_build`, or `open_build`
- `max_items`: optional override for discovery/import limits
- `synthetic_seed`: optional override for synthetic dry-run reproducibility

The CLI now exposes two D1a-oriented operator surfaces:

- `hocrgen build-release --profile profile_review_v1 --dry-run --resume-run-dir <prior-run-dir>`
  continues from a previously completed run directory when the stored profile matches and the target
  stage has not already completed.
- `hocrgen summarize-run --run-dir <run-dir> --format markdown`
  renders a concise operator report from the persisted run metadata and stage summaries.

Publication remains intentionally manual. `D1a` only automates dry-run maintenance, reporting, and
artifact handoff between GitHub Actions jobs.

## Repository reference

- Product/design spec: [`docs/hocrgen_design_and_spec.md`](./docs/hocrgen_design_and_spec.md)
- Long-term roadmap: [`docs/HeOCR_hocrgen_long_term_roadmap.md`](./docs/HeOCR_hocrgen_long_term_roadmap.md)
- Pre-alpha freeze plan: [`docs/pre_alpha_freeze_plan.md`](./docs/pre_alpha_freeze_plan.md)
- Normalization and QA notes: [`docs/hocrgen_normalization_and_qa.md`](./docs/hocrgen_normalization_and_qa.md)
