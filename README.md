# hocrgen

`hocrgen` is the open-source dataset operations toolchain for the HeOCR project.

This repository currently implements Milestone 1 of the roadmap: the package, config, CLI, run/workdir, and CI foundations for a policy-driven Hebrew OCR dataset pipeline. It does not yet implement real crawling, metadata extraction, rights parsing, acquisition, packaging, or publishing.

## What exists today

- Python package with `src/` layout and installable `hocrgen` CLI
- Typed config loading and validation for source registries, release profiles, and license metadata
- Example committed configs under [`src/hocrgen/config`](./src/hocrgen/config)
- Stage-oriented dry-run pipeline commands:
  - `hocrgen config validate`
  - `hocrgen discover`
  - `hocrgen fetch-metadata`
  - `hocrgen policy-filter`
  - `hocrgen acquire`
  - `hocrgen build-release`
- Run/workdir artifact emission under `.work/hocrgen/runs/<run_id>/`
- Initial tests and GitHub Actions validation

## What does not exist yet

- Real source adapters or scraping logic
- Real metadata fetch/parsing
- Real policy engine beyond config validation and profile/source reference checks
- Real acquisition, packaging, or publication
- Later-milestone modules such as dedupe, privacy screening, review handling, and release diffing

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Validate configuration

```bash
hocrgen config validate
```

Expected behavior:

- loads the committed source registry, release profiles, and licenses
- validates them with typed models
- fails fast on malformed YAML or broken references

## Run a sample dry-run stage

```bash
hocrgen discover --profile profile_open_v1 --dry-run
```

This creates a run directory similar to:

```text
.work/hocrgen/
  runs/
    20260324T120000000000Z/
      run.json
      summary.json
      logs/
        run.log
      discover/
        summary.json
        candidates.json
```

Other scaffolded stage commands follow the same pattern:

```bash
hocrgen fetch-metadata --profile profile_open_v1 --dry-run
hocrgen policy-filter --profile profile_open_v1 --dry-run
hocrgen acquire --profile profile_open_v1 --dry-run
hocrgen build-release --profile profile_open_v1 --dry-run
```

The generated artifacts are intentionally small, machine-readable JSON files that document the run and show where later milestones will plug in.

## Repository reference

- Product/design spec: [`docs/hocrgen_design_and_spec.md`](./docs/hocrgen_design_and_spec.md)
- Long-term roadmap: [`docs/HeOCR_hocrgen_long_term_roadmap.md`](./docs/HeOCR_hocrgen_long_term_roadmap.md)

## Development checks

```bash
pytest
hocrgen config validate
hocrgen build-release --profile profile_open_v1 --dry-run
```
