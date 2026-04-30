# Pre-Alpha Freeze Plan

## Purpose

This document turns the remaining `B5` alpha-freeze work into a small execution sequence of concrete PRs.
The goal is not to finish the broader roadmap. The goal is to freeze a narrow, defensible first alpha for the separate `HeOCR` repository.

## Current Alpha Freeze Status

The pre-alpha blocker sequence is now complete:

1. exported public manifests and review artifacts are release-portable
2. the public NLI exemplar is OCR-credible in resolution
3. the Pinkas exemplar is a text-bearing historical page
4. synthetic alpha output preserves Hebrew ordering and uses the `2x real items` cap

The remaining work after this document is no longer alpha freeze. `C5b`, `C6a`, `D1a`, `D2a`, and `D3a` are now represented in the current-ref roadmap state: review decisions can merge back into the pipeline, release-to-release changes are explainable, scheduled dry-run maintenance exists, source-operations health/freeze reporting is available, and the first explicitly approved benchmark subset exists. The next planned milestone is `D4a`, richer synthetic generation for realism and document likeness.

## Pre-Alpha PR Sequence

### `B5b1` — Alpha export portability cleanup

**Why now**
The release tree cannot be frozen while public artifacts expose absolute local paths or `.work/`-specific runtime references.

**Scope**
- remove absolute local filesystem paths from exported public manifests
- remove or rewrite review-audit preview references so they stay release-portable
- keep public export payloads release-relative and repository-portable
- add or update tests that lock this behavior down

**Exit criteria**
- no exported artifact under `releases/<version>/` exposes machine-local absolute paths
- audit manifests remain useful after copy into the separate `HeOCR` repo

### `B5b2` — Real exemplar quality refresh

**Why now**
The first alpha should not ship with a tiny NLI sample and a historical exemplar that contains no readable text.

**Scope**
- export NLI public assets at materially higher resolution
- replace the Pinkas binding/cover selection with an actual text-bearing historical page
- if feasible within the same bounded change, expand the alpha real-scan set to four credible public exemplars
- re-check that the selected public real items remain rights-safe and release-ready

**Exit criteria**
- NLI public samples are OCR-credible in resolution
- all public historical samples are text-bearing and representative
- the real portion of the alpha set looks intentional rather than placeholder-like

**Status**
- completed on `main` by promoting a high-resolution `nli-ms-seed-006` fixture and replacing the Pinkas cover exemplar with a text-bearing interior page

### `B5b3` — Synthetic alpha unblock and sampling policy

**Why now**
Synthetic maturity beyond alpha can wait, but visibly broken Hebrew ordering cannot.

**Scope**
- fix Hebrew character ordering so synthetic Hebrew reads correctly
- change alpha synthetic inclusion from the current separate fixed cap to a `2x real items` policy
- land only low-risk realism improvements that materially improve alpha credibility
- update tests and docs to reflect the new alpha sampling policy

**Explicit non-goals for this PR**
- full handwritten-like synthetic generation
- major new layout families
- heavy realism modeling or complex artifact simulation

**Exit criteria**
- synthetic Hebrew output is ordered correctly
- alpha exports can include synthetic items up to twice the number of exported real items
- synthetic alpha pages are no longer blocked on a correctness bug

**Status**
- completed on `codex/b5b3-synthetic-alpha-unblock` by adding RTL display-order rendering for Pillow-based synthetic pages and changing alpha selection to a `2x real items` cap bounded by `--max-synthetic-items`

### `B5b4` — Final alpha freeze and `HeOCR` handoff

**Why now**
After the blockers above are closed, the remaining step is to freeze the actual release tree and land it in the dataset repository.

**Scope**
- re-run `export-alpha` from the validated `main`
- inspect the frozen `alpha-v0` tree one more time
- copy or export the versioned release tree into the separate `HeOCR` checkout
- prepare and open the handoff PR there with the release docs and manifests included

**Exit criteria**
- the frozen export tree is portable, coherent, and manually reviewed
- the separate `HeOCR` repo contains the release tree under `releases/<version>/`
- the alpha handoff PR is open with accurate notes on included sources and limitations

**Status**
- completed on `codex/b5b4-alpha-freeze-handoff` by re-exporting `alpha-v0` into the sibling `HeOCR` checkout, reviewing the resulting tree, and opening coordinated ready-for-review PRs in both repositories

## Post-Alpha Follow-Ups

These items remain important, but they should not block the first alpha unless a low-risk subset naturally lands during the blocker work above.

### `D4a` / `D4b` — richer synthetic maturity

- handwritten-like generation families that are visually distinct from print-like pages
- stronger degradation and post-processing families
- broader layout diversity, overlays, forms, marginalia, and realism controls
- diversity reporting and richer synthetic filtering/reporting

### `C5b` — review-decision merge and operational review loop

- structured review decision merge back into the pipeline
- review-side CLI workflow hardening
- auditable operational loop for borderline items

This milestone is now implemented in `hocrgen` via the dedicated `review-merge` stage plus repo-tracked `review_data/` inputs.

### `C6a`, `D1a`, `D2a`, `D3a`, and later milestones

- release diffs and changelog automation
- scheduled source-refresh workflows
- benchmark subset formation
- evaluation utilities
- community contribution maturity

`C6a`, `D1a`, `D2a`, and `D3a` are complete on the current ref. The next planned milestone after this document is `D4a`.

## Working Rules For The Pre-Alpha Sequence

- keep the alpha bar narrow: portability, exemplar quality, correctness, and final handoff
- do not broaden scope just because the roadmap already contains larger synthetic ambitions
- when a pre-alpha PR changes operator expectations or release criteria, update `.agent-plan.md`, `README.md`, and the roadmap doc in the same branch
- when a planned PR has notation such as `B5b4`, use that notation in both the PR title and a top-level `## Planning notation` section in the PR description
