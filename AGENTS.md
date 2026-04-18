# Repository Agent Instructions

## Scope
- Keep this file static and procedural.
- Put evolving roadmap, release planning, and feature sequencing in the docs under `docs/`, not here.

## Setup and validation
- Install: `pip install -e '.[dev]'`
- Test: `coverage run -m pytest`
- Validate config: `hocrgen config validate`
- Normalize smoke test: `hocrgen normalize --profile profile_open_v1 --dry-run`
- End-to-end smoke test: `hocrgen build-release --profile profile_open_v1 --dry-run`
- Alpha export smoke test: `hocrgen export-alpha --profile profile_open_v1 --dry-run`

## Branching
- Start new work from the latest `main`.
- Branch naming rule: `codex/<topic>`
- Preferred sequence:
  - `git checkout main`
  - `git pull --ff-only origin main`
  - `git checkout -b codex/<topic>`

## Repository structure
- Core CLI entrypoints live in `src/hocrgen/cli.py` and `src/hocrgen/pipeline.py`.
- Typed config models live in `src/hocrgen/config/models.py`.
- Typed manifest and export models live in `src/hocrgen/manifests/models.py`.
- Source adapters live in `src/hocrgen/fetchers/`.
- Stage logic should stay in the stage-specific packages:
  - `normalize/`
  - `dedupe/`
  - `classify/`
  - `privacy/`
  - `review/`
  - `split/`
  - `package/`
  - `synthetic/`

## Hard boundaries
- Do not put dynamic project state or roadmap status in this file.
- Do not add new public-export fields that leak absolute local filesystem paths.
- Keep public release/export payloads release-relative and portable.
- Preserve typed models when extending config, manifests, review artifacts, or release exports.
- Keep packaged sample data under `src/hocrgen/data/`.
- Treat runnable NLI seeds and exploratory NLI seeds separately:
  - runnable: `src/hocrgen/data/nli/seeds.yaml`
  - exploratory: `src/hocrgen/data/nli/seed_catalog.yaml`

## Coding rules
- Use Python 3.11+ compatible code.
- Prefer fixture-backed, deterministic tests.
- Keep network-dependent workflows out of CI tests.
- Extend stage-specific modules instead of adding unrelated orchestration logic to `cli.py`.
- Use `StageExecutionError` for pipeline-stage failures that should surface as structured command errors.

## Current release posture
- `profile_open_v1` is the conservative public profile.
- Review-required and blocked items must not enter the public dataset payload.
- Alpha exports are shaped for the separate `HeOCR` repository under `releases/<version>/`.

## Before merging
- Treat feature or PR work as incomplete until a non-draft GitHub PR with a detailed description is open.
- Ensure the PR is labeled appropriately and assigned to a GitHub milestone before handing off.
- Run `coverage run -m pytest`
- Run `hocrgen config validate`
- Run `hocrgen build-release --profile profile_open_v1 --dry-run`
- If touching alpha packaging or release exports, also run `hocrgen export-alpha --profile profile_open_v1 --dry-run`
