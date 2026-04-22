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

## Planning source of truth
- Treat merged code on `main` plus merged GitHub PR history as the canonical source of truth for roadmap status.
- Treat `.agent-plan.md` as the repo-tracked current-state summary for merged `main`, not as branch-local scratch notes.
- Before starting a roadmap item, verify whether it is already merged on `main` and reflected in recent PR history.
- If planning docs disagree with merged `main`, update the planning docs before starting the next roadmap item.
- Do not treat a branch-local "active branch", "current blocker", or "current implementation PR" note as authoritative unless it matches merged `main`.

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
- The PR must be ready for review, not draft.
- If the PR implements a roadmap-tracked item or any other planned milestone item with notation such as `B5b4`, the PR title must use `<notation>: <sentence-case summary>`.
- Planned PR descriptions must include a top-level `## Planning notation` section that names the notation, the parent milestone, and the plan source document.
- If work belongs to a planned milestone but no notation exists yet, define that notation in the planning docs before opening the PR.
- Planned PR notation applies to PR metadata, not branch names. Keep branch naming on the existing `codex/<topic>` rule.
- The PR must describe what changed, why it changed, the user/developer impact, and the validation performed.
- Ensure the PR is labeled appropriately and assigned to a GitHub milestone before handing off.
- A roadmap item is not fully complete until `main` reflects the merged code, the merged PR metadata is correct, and the planning docs on `main` reflect the new status and next critical path.
- Run `coverage run -m pytest`
- Run `hocrgen config validate`
- Run `hocrgen build-release --profile profile_open_v1 --dry-run`
- If touching alpha packaging or release exports, also run `hocrgen export-alpha --profile profile_open_v1 --dry-run`
