# hocrgen

`hocrgen` is the open-source dataset operations toolchain for the HeOCR project.

This repository now implements Milestone 5: a conservative review-readiness pipeline on top of the earlier acquisition, normalization, technical-QA, and exact-curation milestones. The current implementation remains intentionally fixture/sample-driven, but it now performs real source ingestion, rights filtering, asset materialization, technical normalization, exact item-level deduplication, lightweight heuristic classification, metadata-based privacy screening, review-queue export, deterministic split assignment over release-ready items, and curated dry-run release assembly.

## What `hocrgen` can do today

- validate typed source, profile, and license config
- ingest a seed-driven NLI source for items explicitly marked `Any Use Permitted`
- ingest bounded static sample packages for Pinkas and BiblIA
- generate deterministic synthetic Hebrew sample documents as SVG assets
- normalize rights into controlled license values and policy classifications
- apply release-profile eligibility rules
- materialize acquired/generated sample assets into a run workdir
- normalize acquired assets into a stable run layout with technical metadata
- compute checksums, dimensions, file sizes, and format metadata
- generate preview copies for supported SVG/raster assets
- emit QA pass/fail reports and normalized-item manifests
- perform exact item-level deduplication using ordered normalized-asset checksums
- classify retained items with heuristic content/period/language/quality labels
- apply conservative metadata-based privacy rules before release assembly
- export review-ready, blocked, and release-ready subsets as machine-readable manifests
- assign deterministic `train` / `validation` / `test` splits over the release-ready deduped set
- emit curated release manifests with duplicate-cluster, review-queue, split, and leakage-report artifacts

## Supported sources in the current MVP

- `nli_any_use_permitted`
  - implemented as a conservative seed-manifest flow
  - parses committed sample HTML item pages
  - extracts title, description, rights text, and page-image references
- `pinkas_open`
  - static importer over a packaged sample record set
- `biblia_open`
  - static importer over a packaged sample record set
- `project_synthetic`
  - deterministic SVG-based synthetic generator
  - includes tracked font manifest and text corpus inputs

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
- review-decision merge and human-in-the-loop approval
- OCR-aware privacy screening
- advanced classification and benchmark subset logic
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
      split/split_manifest.json
      split/leakage_report.json
      build_release/item_manifest.json
      build_release/removed_duplicate_items.json
      build_release/duplicate_relations.json
      build_release/duplicate_clusters.json
      build_release/review_queue.json
      build_release/review_required_items.json
      build_release/blocked_items.json
      build_release/split_manifest.json
      build_release/leakage_report.json
      build_release/release_summary.json
      build_release/source_stats.json
      build_release/classification_stats.json
      build_release/privacy_stats.json
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
  --output-dir /path/to/HeOCR/releases/alpha-v0
```

The alpha exporter:

- copies only the public `release_ready` subset into `data/<split>/<item_id>/`
- keeps `review_required` and `blocked` items as audit manifests only
- caps synthetic inclusion separately from real inclusion
- writes repo-ready manifests under `manifests/`
- writes `DATASET_CARD.md`, `RELEASE_NOTES.md`, and `PROVENANCE.md` under `docs/`

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

## Classification, privacy, and review export

Milestone 5 adds a conservative review-readiness layer after exact dedupe.

What it does today:

- classifies retained deduped items as `handwritten`, `printed`, or `mixed`
- assigns heuristic `historical` / `modern` period labels and Hebrew-only vs mixed-language labels
- emits a lightweight quality score and tier for downstream review/export logic
- applies metadata-first privacy rules from [`src/hocrgen/config/privacy_rules.yaml`](./src/hocrgen/config/privacy_rules.yaml)
- routes items into `release_ready`, `review_required`, or `blocked` outcomes
- exports a stable review queue with preview paths and suggested decision types

The default public profile is conservative:

- `privacy_flag=clear` items can proceed to split and release assembly
- `possible_personal_data` and `needs_review` items are routed to the review queue
- `blocked_sensitive` items are excluded from both the review queue and the release-ready split set

What it still does not do:

- merge human review decisions back into the pipeline
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

## Synthetic generation

The synthetic subsystem is modest but real:

- deterministic from seed
- outputs SVG page assets plus metadata
- uses tracked inputs from [`src/hocrgen/data/synthetic/fonts/manifest.yaml`](./src/hocrgen/data/synthetic/fonts/manifest.yaml)
- uses a packaged Hebrew text corpus from [`src/hocrgen/data/synthetic/texts/hebrew_lines.txt`](./src/hocrgen/data/synthetic/texts/hebrew_lines.txt)
- supports a printed-style and handwritten-look template family
- may include short English fragments in otherwise Hebrew pages

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

## PR agent context

This repository publishes `pr-agent-context` comments for pull requests and later refresh events.

- [`.github/workflows/validate.yml`](./.github/workflows/validate.yml) runs the test and smoke-check
  suite, exports a combined `coverage.xml`, uploads it as the `coverage-xml` artifact, and invokes
  `pr-agent-context` on pull requests.
- [`.github/workflows/pr-agent-context-refresh.yml`](./.github/workflows/pr-agent-context-refresh.yml)
  handles later review/check signals and re-runs `pr-agent-context` in refresh mode.

Both workflows use XML-based patch coverage inputs:

- `patch_coverage_source_mode: coverage_xml_artifact`
- `coverage_report_artifact_name: coverage-xml`
- `coverage_report_filename: coverage.xml`

Both workflows also use `publish_mode: append`, so refresh runs append new managed comments rather
than updating earlier ones.

## Repository reference

- Product/design spec: [`docs/hocrgen_design_and_spec.md`](./docs/hocrgen_design_and_spec.md)
- Long-term roadmap: [`docs/HeOCR_hocrgen_long_term_roadmap.md`](./docs/HeOCR_hocrgen_long_term_roadmap.md)
- Normalization and QA notes: [`docs/hocrgen_normalization_and_qa.md`](./docs/hocrgen_normalization_and_qa.md)
