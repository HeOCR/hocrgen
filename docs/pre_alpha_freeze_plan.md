# Pre-Alpha Freeze Plan

## Purpose

This document turns the remaining `B5` alpha-freeze work into a small execution sequence of concrete PRs.
The goal is not to finish the broader roadmap. The goal is to freeze a narrow, defensible first alpha for the separate `HeOCR` repository.

## Current Alpha-Blocker Findings

The latest `export-alpha` inspection on `main` narrowed the remaining release blockers to four concrete issues:

1. exported public manifests still leak absolute local paths and `.work/` runtime references
2. the current NLI public sample is valid but too small to feel OCR-credible
3. the current Pinkas public sample is a binding/cover image rather than a text-bearing historical page
4. the current synthetic public sample still has broken Hebrew ordering, and the alpha synthetic cap should move to `2x real items`

These are alpha blockers because they make the release either non-portable or visibly weak to a first external user.

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

## Postpone Until After Alpha Freeze

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

### `C6a` and later milestones

- release diffs and changelog automation
- scheduled source-refresh workflows
- benchmark subset formation
- evaluation utilities
- community contribution maturity

## Working Rules For The Pre-Alpha Sequence

- keep the alpha bar narrow: portability, exemplar quality, correctness, and final handoff
- do not broaden scope just because the roadmap already contains larger synthetic ambitions
- when a pre-alpha PR changes operator expectations or release criteria, update `.agent-plan.md`, `README.md`, and the roadmap doc in the same branch
