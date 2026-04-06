# hocrgen

`hocrgen` is the open-source dataset operations toolchain for the HeOCR project.

This repository now implements Milestone 3: a conservative normalization and technical-QA layer on top of the earlier acquisition MVP. The current implementation remains intentionally fixture/sample-driven, but it now performs real source ingestion, rights filtering, asset materialization, technical normalization, checksum/integrity tracking, preview generation, and QA reporting.

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
- build a meaningful dry-run release manifest with per-source, per-format, and QA stats

## Supported sources in Milestone 2

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

## What is still future work

- broad live-source crawling
- deduplication
- advanced classification
- privacy/sensitivity screening
- manual review queues
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

## Run a real Milestone 2 dry-run

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
      build_release/item_manifest.json
      build_release/failed_item_manifest.json
      build_release/release_summary.json
      build_release/source_stats.json
```

## Stage commands

Each stage command is now meaningfully functional:

```bash
hocrgen discover --profile profile_open_v1 --dry-run
hocrgen fetch-metadata --profile profile_open_v1 --dry-run
hocrgen policy-filter --profile profile_open_v1 --dry-run
hocrgen acquire --profile profile_open_v1 --dry-run
hocrgen normalize --profile profile_open_v1 --dry-run
hocrgen build-release --profile profile_open_v1 --dry-run
```

Useful implemented flags:

```bash
hocrgen build-release --profile profile_open_v1 --dry-run --source nli_any_use_permitted
hocrgen build-release --profile profile_open_v1 --dry-run --max-items 1
hocrgen build-release --profile profile_open_v1 --dry-run --seed 23
```

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
hocrgen build-release --profile profile_open_v1 --dry-run
```

## Repository reference

- Product/design spec: [`docs/hocrgen_design_and_spec.md`](./docs/hocrgen_design_and_spec.md)
- Long-term roadmap: [`docs/HeOCR_hocrgen_long_term_roadmap.md`](./docs/HeOCR_hocrgen_long_term_roadmap.md)
- Normalization and QA notes: [`docs/hocrgen_normalization_and_qa.md`](./docs/hocrgen_normalization_and_qa.md)
