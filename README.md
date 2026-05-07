# hocrgen

`hocrgen` is the open-source dataset operations toolchain for the HeOCR project.

This repository now implements a conservative review-readiness, source-operations, benchmark-subset, evaluation-utility, community-contribution, annotation-pilot, multi-release governance, benchmark ground-truth reference, modern handwritten acquisition policy, synthetic-provider validation, synthetic-only export, and public beta packaging/readiness layer on top of the earlier acquisition, normalization, technical-QA, and exact-curation milestones. The current implementation remains intentionally fixture/sample-driven, but it now performs real source ingestion, source health checks, rights filtering, asset materialization, technical normalization, exact item-level deduplication, lightweight heuristic classification, metadata-based privacy screening, review-queue export, deterministic split assignment over release-ready items, benchmark v1 selection, optional benchmark-reference ingestion and adjudication/status reporting, lightweight text evaluation over benchmark manifests, carefully bounded annotation pilot selection, curated dry-run release assembly, documented contribution safety rails, release/version governance for repeated public exports, mixed HeOCR alpha handoff, synthetic-only HeOCRsynth handoff, and blocked public beta publication handoff packaging with checksums, archives, a machine-readable blocker-closure plan, and a repo-owned blocker report.

## What `hocrgen` can do today

- validate typed source, profile, and license config
- validate source-operations settings and fixture-backed source health expectations
- ingest a seed-driven NLI source for items explicitly marked `Any Use Permitted`
- ingest bounded static sample packages for Pinkas and BiblIA
- ingest deterministic hocrsyngen manifest-backed synthetic Hebrew candidate inputs as degraded JPEG assets
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
- ingest optional `benchmark_reference_manifest.v1` reference sets with typed transcription/layout validation, adjudication status artifacts, and versioning gates
- carry optional transcription and layout-label reference slots without requiring annotations for release-ready items
- select a small repo-approved annotation pilot subset without requiring transcriptions or layout labels for current public outputs
- load benchmark examples and score deterministic text predictions with simple evaluation metrics
- emit curated release manifests with duplicate-cluster, review-queue, split, and leakage-report artifacts
- document safe community contribution paths for source proposals, source adapters, synthetic assets, dataset issues, and release governance
- document multi-release governance for version semantics, removals/takedowns, additive schema migration, source deprecation, benchmark stability, and compatibility statements
- document and validate benchmark ground-truth guidance for Hebrew transcription, layout labels, and `benchmark_reference_manifest.v1` reference manifests
- document the `F3a` rights-clean modern handwritten Hebrew acquisition policy for consent, public-use release terms, provenance, privacy screening, takedown/removal handling, scanning standards, operator review, composition targets, and source-family boundaries
- document the four-repository synthetic spinout boundary: `hocrsyngen` for generation, `hocrgen` for gates/orchestration/export, `HeOCR` for mixed releases, and `HeOCRsynth` for synthetic-only releases
- package blocked public beta handoff trees with explicit readiness gates, checksums, archives, and beta docs
- emit a public beta blocker-closure plan that separates repo-owned blockers from external/input-dependent blockers without relaxing any gate
- emit a repo-owned public beta blocker report with item/status-level privacy-review, benchmark-reference, and takedown/private-reporting closure evidence
- export synthetic-only HeOCRsynth release handoff trees from governed release-ready pipeline state

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
  - hocrsyngen `generation_manifest.v1` fixture-backed synthetic candidate input source
  - consumes a configured manifest batch and keeps legacy in-repo generator fixtures out of the active source path

This is not a broad crawler yet. The NLI support is intentionally narrow and reliable rather than site-wide.

The NLI seed data is split on purpose:

- runnable fixture-backed seeds live in [`src/hocrgen/data/nli/seeds.yaml`](./src/hocrgen/data/nli/seeds.yaml)
- broader exploratory/manual candidate URLs live in [`src/hocrgen/data/nli/seed_catalog.yaml`](./src/hocrgen/data/nli/seed_catalog.yaml)

Near-term release-scale acquisition preserves that seed boundary while removing one-by-one manual promotion as the bottleneck. The operator path:

1. Accepts vetted seed URLs from the catalog, the runnable seed manifest, or both.
2. Reuses local fixture-backed seeds without network access when a fixture already exists.
3. Fetches and parses missing item metadata/assets into the same local fixture shape used by the current deterministic pipeline when explicitly run.
4. Persists a promotion/acquisition report with rights text, fixture path, asset paths, promoted seeds, skipped seeds, and failed seeds.
5. Keeps CI and release builds fixture-backed and network-free after the live acquisition step.
6. Leaves the normal rights, privacy, review, dedupe, split, benchmark, and export-portability gates in charge before any larger public release.

This is the preferred short-term path for growing from the current small alpha exemplar set toward a bounded beta-scale trial. The `F1a` trial plan targets `80` real items plus `80` synthetic controls, with the real-source mix fixed at `27` NLI, `27` Pinkas, and `26` BiblIA. It is an operator-only acquisition trial, not a public beta export, release-candidate export, broad live-source crawler, or publication workflow.

The NLI portion can build on the existing live-but-cached seed promotion path. Pinkas and BiblIA are bounded packaged exemplar sources with explicit source-depth expansion manifests under `src/hocrgen/data/pinkas/` and `src/hocrgen/data/biblia/`; added records only count when they are committed as packaged fixtures with stable provenance, PD-IL-compatible rights, source-health-visible assets, and reviewable operator notes. Rights, privacy, review, dedupe, split, benchmark, synthetic-cap, and export-portability gates remain mandatory before any larger public release. F1d adds deterministic near-duplicate/source-group leakage hardening before scale beyond the operator-only trial; near-duplicates are surfaced as manual-review risks and grouped for split safety, not automatically removed. F1e adds an explicit benchmark/holdout leakage policy: benchmark items cannot share exact duplicate, near-duplicate, or source-group membership with non-benchmark holdout/public-beta candidates unless a typed repo-tracked accepted resolution matches the detected group and member set. F3a/F3b now define the rights-clean modern handwritten Hebrew acquisition policy and bounded operator intake workflow; F4b-F4e define the external synthetic-provider boundary, HeOCRsynth handoff, and shared release export packaging primitives; separate F5 publication gates are still required before treating beta-scale acquisition as release or benchmark readiness.

Every `discover` run emits an operator-only `discover/source_depth_feasibility.json` artifact for the F1 target. The report records per-source target count, observed candidate count, health-eligible runnable/cached candidate count, target-scale candidate count, asset count, exploratory catalog count where applicable, static-source expansion-path status, runnable/cached gap, target-scale gap, feasibility status, report-scoped warnings, and operator notes. On the current fixture-backed data, NLI reports `27` runnable/cached real source-cached seeds against a target of `27`; the newly promoted F1b4 NLI fixtures are marked source-depth-only and do not automatically enter normal release/export discovery. Pinkas reports `1` normally discoverable record plus `27` packaged source-depth inventory records against `27`; BiblIA reports `1` normally discoverable record plus `26` packaged source-depth inventory records against `26`; and the hocrsyngen-backed synthetic source reports `2` validated manifest samples against the `80` synthetic-control target. Pinkas/BiblIA expansion records marked for F1 source depth remain operator-only and do not automatically enter normal release/export discovery, while synthetic target scale now requires a larger validated hocrsyngen batch rather than hocrgen-side generation.

To execute the bounded F1c target-scale trial, use the explicit operator command:

```bash
hocrgen f1-beta-trial --profile profile_open_v1 --dry-run
```

This command opts into source-depth-only NLI seeds and packaged Pinkas/BiblIA expansion records, then runs the currently configured hocrsyngen synthetic fixture samples through the existing build-release gate sequence without broad crawling, publication, public beta export, release-candidate export, or automatic public-profile promotion. It writes `build_release/f1_target_scale_trial_report.json` with acquisition counts, rights outcomes, review outcomes, exact duplicate outcomes, near-duplicate/source-group outcomes, split and benchmark eligibility, benchmark/holdout leakage resolution status, post-review synthetic-cap status, source allocation, source-health status, non-goals, and remaining blockers. Normal `discover`, `build-release`, and `export-alpha` behavior remains bounded unless the operator explicitly runs this trial command. On the current data, target-scale execution is blocked until a validated hocrsyngen batch covers the synthetic target; those blockers are evidence that the gates remain enforceable, not permission to publish. The current F1c artifacts remain operator-only and do not satisfy public beta readiness by themselves.

## Public beta readiness

`F5a` defines public beta readiness as a publishability contract. `F5b` implements the local dry-run packaging command for that contract, `F5c` adds machine-readable blocker sequencing for the remaining handoff gaps, and `F5d` adds repo-owned blocker closure evidence before external scale inputs:

```bash
hocrgen export-public-beta --profile profile_open_v1 --dry-run
```

The command runs the normal `build-release` pipeline and writes a versioned mixed `HeOCR` handoff tree. It materializes `manifests/public_beta_readiness_report.json` with one row per gate using `gate_id`, `status`, `evidence_paths`, and `rationale`; valid statuses are only `pass` and `blocked`. It also writes `manifests/public_beta_blocker_closure_plan.json`, which derives the current closure sequence from the readiness report and categorizes blocked gates as `repo_owned_immediately_actionable` or `external_input_dependent`. F5d also writes `manifests/public_beta_repo_owned_blocker_report.json`, which records unresolved privacy/review item ids and reasons, benchmark-reference draft/unavailable/adjudication status by item, and takedown/private-reporting configuration plus repository-check evidence from `src/hocrgen/config/public_beta.yaml`. It also writes release-level SHA-256 checksum coverage, an archive manifest, at least one `tar.gz` archive rooted at the versioned release directory, beta-specific dataset/provenance/changelog/release/benchmark/handoff docs, and digest verification from the handoff tree.

The current public beta packaging output remains blocked; operator trial success is necessary evidence, but public beta is not publishable until all of these gates are satisfied and documented:

- source depth and composition: the mixed `HeOCR` candidate set must meet the planned real-source allocation evidence, keep source-depth-only fixtures out of normal publication unless deliberately promoted through release gates, and describe real versus synthetic composition clearly
- synthetic scale and caps: the planned `80` synthetic-control target requires a larger validated hocrsyngen manifest batch; synthetic items remain bounded by the active public-profile/export cap policy and must never be used to hide real-source gaps
- rights and provenance: every public item must have normalized release-compatible rights, source/provider provenance, attribution where needed, stable ids, and no unresolved rights review
- privacy and review: review-required, blocked, unresolved privacy, unresolved modern-handwriting consent, and unresolved takedown states cannot enter the public payload
- uniqueness and leakage: exact duplicates, near-duplicate risks, source groups, split leakage, and benchmark/holdout overlap must be cleared or explicitly resolved by typed repo-tracked policy before any public beta claim
- benchmark readiness: benchmark membership must be stable, benchmark-reference status/versioning artifacts must be present for benchmark items, and benchmark-reference limitations must be disclosed
- annotation expectations: full transcription and layout labels are not mandatory for all public beta items unless a later PR changes the contract; any included annotation or pilot references must be portable, explicit, and status-labeled
- portability and archives: public manifests, release records, checksums, assets, archives, release diffs, and changelogs must be release-relative and free of absolute local paths, `.work/` dependencies, and network-dependent reproducibility assumptions
- public docs and takedown readiness: `DATASET_CARD.md`, `PROVENANCE.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, benchmark docs, and handoff notes must state composition, rights, limitations, removal/takedown contact path, configured and verified public/private reporting status from `src/hocrgen/config/public_beta.yaml`, and known blockers

When any gate is `blocked`, `export-public-beta` stops before repository sync, upload, release tagging, or publication-report emission. It does not publish to `HeOCR`, Hugging Face, Kaggle, or `HeOCRsynth`. The known hard blocker remains the larger validated hocrsyngen manifest batch required for the `80` synthetic-control target; current F1c artifacts remain operator-only and do not satisfy public beta readiness by themselves. The current blocker-closure plan keeps source depth and synthetic scale external/input-dependent while the repo-owned blocker report keeps privacy/review closure, benchmark-reference readiness disclosure, and takedown private-reporting setup precise and machine-readable. Current GitHub private vulnerability reporting for `HeOCR/hocrgen` is recorded as disabled in `src/hocrgen/config/public_beta.yaml`, so the takedown gate remains blocked until maintainers enable that path or configure and verify another maintainer-private channel.

To promote exploratory entries into runnable local fixtures, use the local operator script:

```bash
python scripts/promote_nli_seeds.py \
  --seed-id nli-ms-seed-001 \
  --max-items 10 \
  --browser-state-dir .cache/nli-playwright
```

The script selects from `seed_catalog.yaml` by default, opens a persistent browser only for seeds without reusable local fixtures, lets you solve any Cloudflare challenge once, captures each live item into normalized local fixture HTML plus local asset files, appends promoted entries to `seeds.yaml`, removes them from `seed_catalog.yaml`, and writes a machine-readable promotion report. Use `--seed-source runnable` to audit/cache-check existing runnable seeds without live capture, or `--seed-source all` to select from both manifests. Use `--max-items` to keep every batch explicitly bounded.

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
- stronger perceptual/semantic duplicate review beyond the current deterministic near-duplicate/source-group split-safety gates
- OCR-aware privacy screening
- advanced classification and model-training infrastructure
- final public beta publication to Hugging Face or the GitHub dataset repo after F5a/F5b/F5c/F5d source-depth, uniqueness, ground-truth, review, portability, documentation, checksum/archive, blocker-sequencing, repo-owned closure reporting, and takedown gates pass
- publication automation beyond blocked local handoff packaging

## Splendor knowledge workspace

This repository includes a repo-native Splendor workspace for future coding-agent context. Splendor state lives in:

- [`splendor.yaml`](./splendor.yaml) for workspace layout and source policy
- [`wiki/`](./wiki/) for generated source summaries and maintained topic pages
- [`state/`](./state/) for source manifests, queue records, run records, and query snapshots
- [`planning/`](./planning/) for future Splendor task, milestone, decision, and question records
- [`reports/`](./reports/) for Splendor lint and health reports

The initial workspace registers and ingests high-signal hocrgen sources: `AGENTS.md`, `README.md`, `llms.txt`, `.agent-plan.md`, core docs under `docs/`, JSON schemas under `schemas/`, GitHub workflows, config files under `src/hocrgen/config/`, source operations, pipeline/CLI, benchmark/evaluation, annotation, review, release/export, fetcher, and NLI promotion modules. It intentionally does not register binary sample assets. The current local Splendor build used for this setup does not ingest TOML yet, so `pyproject.toml` remains part of normal repo context but is not included in the committed Splendor source set.

Treat `state/`, `wiki/sources/`, and `reports/` as generated Splendor artifacts. Do not hand-edit generated source summaries, manifests, queue/run records, or reports; update registered sources and regenerate the workspace through Splendor instead.

Future agents can start with:

```bash
splendor wiki status
splendor query "release export pipeline"
splendor brief --agent-context "continue hocrgen work" --json
```

If the installed `splendor` CLI is older than the repo workspace requires, run it from a local Splendor checkout. For the common sibling-checkout layout:

```bash
uv run --project ../splendor splendor --root . wiki status
```

After changing registered source files, refresh and check the workspace:

```bash
splendor source refresh <path-or-source-id>
splendor ingest --pending
splendor wiki rebuild-index
splendor lint
splendor health
```

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
- packaged benchmark v1 approvals and stability policy under `package://data/benchmark/benchmark_v1/config.json` (source-of-truth in this repository: [`src/hocrgen/data/benchmark/benchmark_v1/config.json`](./src/hocrgen/data/benchmark/benchmark_v1/config.json))
- packaged benchmark reference fixture under `package://data/benchmark/benchmark_v1/reference_manifest.json` (source-of-truth in this repository: [`src/hocrgen/data/benchmark/benchmark_v1/reference_manifest.json`](./src/hocrgen/data/benchmark/benchmark_v1/reference_manifest.json))

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
      build_release/annotation_pilot_manifest.json
      build_release/annotation_pilot_selection_audit.json
      build_release/classification_stats.json
      build_release/privacy_stats.json
      build_release/benchmark_manifest.json
      build_release/benchmark_selection_audit.json
      build_release/benchmark_stability_policy.json
      build_release/benchmark_reference_manifest.json
      build_release/benchmark_reference_status.json
      build_release/benchmark_reference_versioning.json
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
- writes `annotation_pilot_manifest.json` and `annotation_pilot_selection_audit.json` for explicitly scoped pilot annotation work
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

## Synthetic-only export

`export-synthetic` builds on the existing `build-release` outputs and writes a versioned synthetic-only release tree shaped for the separate `HeOCRsynth` repository. It selects only release-ready synthetic items from hocrgen pipeline state; raw hocrsyngen batches are not publishable by themselves.

Default usage:

```bash
hocrgen export-synthetic --profile profile_open_v1 --dry-run
```

By default the export is written under:

```text
.work/hocrgen/exports/synth-alpha-v0/
```

To write directly into a checkout of the separate `HeOCRsynth` repo:

```bash
hocrgen export-synthetic \
  --profile profile_open_v1 \
  --dry-run \
  --heocrsynth-repo /path/to/HeOCRsynth
```

The synthetic exporter:

- copies only release-ready synthetic items with `PROJECT-SYNTHETIC` licensing into `data/synthetic/<split>/<item_id>/`
- runs the full configured release pipeline before filtering; `--source` is intentionally unsupported because source-limited builds can invalidate benchmark and review gates
- rejects synthetic items that are missing synthetic disclosure or hocrsyngen provider, rendering, and Hebrew coverage metadata
- filters public manifests, benchmark artifacts, benchmark reference versioning, review/audit artifacts, annotation artifacts, release diffs, and docs to the selected synthetic scope
- writes `release_record.json` with `dataset_id: HeOCRsynth`, `release_kind: synthetic_only`, `synthetic_only: true`, and `real_items: 0`
- keeps real NLI, Pinkas, BiblIA, and modern handwriting items out of the synthetic-only payload and audit manifests
- writes HeOCRsynth-specific `CHANGELOG.md`, `DATASET_CARD.md`, `RELEASE_NOTES.md`, `PROVENANCE.md`, `BENCHMARK_CARD.md`, and `HANDOFF.md`
- keeps mixed real+synthetic `HeOCR` releases distinct; those remain handled by `export-alpha`

Both release exporters share portable packaging mechanics through `hocrgen.package.common`. Alpha and HeOCRsynth policy stays separate, but release-relative item payload shaping, stats, review/audit payloads, benchmark/reference filtering, release diffs, changelog rendering, and common manifest/doc writing use shared release export packaging primitives.

By default `export-synthetic` auto-discovers the previous sibling synthetic release under the same export root and compares against it. To override that baseline explicitly:

```bash
hocrgen export-synthetic \
  --profile profile_open_v1 \
  --dry-run \
  --version synth-alpha-v1 \
  --compare-to /path/to/HeOCRsynth/releases/synth-alpha-v0
```

## Multi-release governance

`E4a` defines the current release governance contract without changing alpha/public item inclusion behavior.

- Release versions are immutable public records once published; corrections and removals are represented in the next version through `release_diff.json`, `CHANGELOG.md`, `release_record.json`, and release notes.
- Public manifest paths remain release-relative and portable. Consumers should treat `manifests/release_record.json`, `manifests/release_summary.json`, `manifests/item_manifest.json`, `manifests/release_diff.json`, and explicit `schema_version` / schema id fields as the compatibility anchor for a release tree.
- Serialized schema changes should be additive within the current schema version. Breaking changes require a new schema version or schema id, migration notes, and updated tests/docs before publication.
- Rights, privacy, source breakage, or takedown concerns should enter the issue workflow or a private maintainer/security channel, then land as auditable config/review/source changes. Affected public items must be excluded from future dataset payloads until resolved, with the machine-readable removal reason plus human audit rationale visible in release diffs, changelogs, release notes, and PR metadata where disclosure is safe.
- Source deprecation should prefer `degraded`, `frozen`, or review-only treatment before removal. Deprecated sources must not silently corrupt benchmark membership, split leakage, export portability, or public-profile eligibility.
- `benchmark_v1` remains a stable, explicitly approved subset. Approved benchmark items cannot churn silently; if a benchmark item becomes blocked, unresolved, duplicate-removed, missing, split-incompatible, or tied to unresolved benchmark/holdout leakage, release validation fails or the F1 trial/report gate blocks until benchmark policy/docs are updated deliberately.

The detailed policy lives in [`docs/release_governance.md`](./docs/release_governance.md).

## Rights normalization and policy behavior

The current milestone normalizes rights into these controlled values:

- `PD-IL`
- `CC-BY-4.0`
- `CC-BY-SA-4.0`
- `PROJECT-SYNTHETIC`
- `HEOCR-CONSENT-OPEN`
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

`hocrgen config validate` now also validates the committed `review_data/` tree, benchmark config, and annotation pilot config, then reports their item counts.

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
- surfaces deterministic near-duplicate candidates from content-derived quantized thumbnail hashes as manual-review blockers without auto-removing them
- emits source-group manifests for related source-work records, including multi-page static source records, and keeps those groups split-safe
- assigns deterministic `train` / `validation` / `test` splits using the profile `split_policy`
- keeps exact duplicate clusters and source groups together by using stable split-group ids
- emits a leakage report confirming that release-ready items do not cross split boundaries incorrectly, records near-duplicate cluster split exposure, and adds build-release benchmark/holdout leakage resolution status

What it does not do yet:

- heavy perceptual hashing, embeddings, or OCR-semantic near-duplicate detection
- OCR-aware grouping
- content-quality ranking beyond technical QA

## Benchmark subset

`benchmark_v1` is a small, explicitly approved benchmark-facing slice emitted by `build-release` and mirrored by `export-alpha`.

The initial benchmark contains two real release-ready exemplars plus one governed synthetic control item. Every benchmark item must be named in the packaged approval config at `package://data/benchmark/benchmark_v1/config.json` (source-of-truth in this repository: [`src/hocrgen/data/benchmark/benchmark_v1/config.json`](./src/hocrgen/data/benchmark/benchmark_v1/config.json)), must remain release-ready after review merge, and must keep its committed benchmark split. If an approved item becomes unresolved, blocked, duplicate-removed, missing from the current run, or assigned to a different split, `build-release` fails with a structured stage error. Local checkout/config-root-relative `benchmark_data/` trees are still honored as explicit overrides, but non-editable installs use the packaged default.

The benchmark config also carries `benchmark_holdout_leakage_policy`. `build-release` and the F1 trial emit `build_release/benchmark_leakage_risk.json`, and `build_release/leakage_report.json` embeds the same status. The gate covers exact duplicate clusters, near-duplicate clusters, and source groups. Unresolved or stale overlap is reported as `blocked`; an accepted resolution is valid only when its group id, group kind, benchmark item ids, and non-benchmark item ids match the current detected risk. The current `benchmark_v1` config records the Pinkas WDL11806 source-group resolution as `exclude_related_group_from_holdout_public_beta_claims`, which keeps `benchmark_v1` membership stable and prevents the related non-benchmark Pinkas pages from being used as clean holdout/public-beta readiness evidence.

Benchmark artifacts:

- `build_release/benchmark_manifest.json`
- `build_release/benchmark_leakage_risk.json`
- `build_release/benchmark_selection_audit.json`
- `build_release/benchmark_stability_policy.json`
- `build_release/benchmark_reference_manifest.json`
- `build_release/benchmark_reference_status.json`
- `build_release/benchmark_reference_versioning.json`
- `build_release/BENCHMARK_CARD.md`
- exported release mirrors under `manifests/` and `docs/BENCHMARK_CARD.md`

`F2b` adds optional benchmark-reference ingestion on top of the `F2a` documented contracts. The packaged fixture at `src/hocrgen/data/benchmark/benchmark_v1/reference_manifest.json` carries one reviewed/adjudicated public transcription-plus-layout reference, one draft transcription reference, and one explicitly unavailable reference. Each entry has a stable `reference_id`; `correction_of` and `superseded_by` point to reference ids rather than item ids. `build-release` validates `benchmark_transcription_reference.v1`, `benchmark_layout_reference.v1`, and `benchmark_reference_manifest.v1` shapes, rejects absolute, `file://`, `.work`, backslash, and path-traversal reference paths, checks item/source/split linkage against the selected benchmark manifest, copies validated child reference files under their manifest paths, and verifies layout asset path/checksum/dimension linkage against current normalized assets so stale labels fail deterministically.

Reference ingestion is additive. Current public and alpha exports still do not require transcriptions or layout labels, and F2b does not change `benchmark_v1` membership. `export-alpha` mirrors both the reference artifacts and the selected child reference files so release-relative paths resolve inside the exported tree. `benchmark_reference_status.json` summarizes `not_available`, `draft`, `reviewed`, `adjudicated`, `corrected`, `retired`, reviewer/adjudication, correction/supersession, blocked/draft, and reference-ready counts. `benchmark_reference_versioning.json` enforces correction/supersession coherence, requires change reasons for corrected or retired references, and provides a previous-manifest comparison hook for detecting silent public reference removals or changes. F1e resolves the separate F1d benchmark/holdout leakage risk with a typed policy gate; F2b remains optional ground-truth ingestion and is not public beta or export-readiness completion.

## Benchmark evaluation utilities

`E2a` adds lightweight benchmark loading and text-evaluation utilities without introducing model training infrastructure.

Programmatic usage starts from the existing benchmark artifacts:

```python
from pathlib import Path

from hocrgen.evaluation import load_benchmark_examples, summarize_benchmark_examples

examples = load_benchmark_examples(
    Path("releases/alpha-v0/manifests/benchmark_manifest.json"),
    item_manifest_path=Path("releases/alpha-v0/manifests/item_manifest.json"),
    annotation_manifest_path=Path("releases/alpha-v0/manifests/annotation_manifest.json"),
)
summary = summarize_benchmark_examples(examples)
```

CLI evaluation accepts JSONL or JSON records keyed by `item_id` with a text field:

```bash
hocrgen evaluate-benchmark \
  --benchmark-manifest releases/alpha-v0/manifests/benchmark_manifest.json \
  --predictions predictions.jsonl \
  --references references.jsonl \
  --output reports/benchmark_v1_evaluation.json
```

The report includes item coverage, character error rate, exact-match rate, per-item edit distances, and a small `leaderboard_ready` block with the primary metric convention. Current public artifacts do not require transcriptions, so references are supplied explicitly until a future annotated subset lands. Evaluation helpers keep all joined asset and annotation paths release-relative and portable.

## Annotation readiness

`hocrgen` reserves typed, optional annotation slots on item manifests so future annotated subsets can attach release-relative transcription and layout-label files without changing the core release flow.

Current alpha and release builds do not require transcriptions. Items default to `annotation_status: not_available`, `transcription: null`, and `layout_labels: []`. `build-release` emits `build_release/annotation_manifest.json`; `export-alpha` mirrors it to `manifests/annotation_manifest.json`. Annotation references must remain portable and release-relative, such as `annotations/<item_id>/transcription.json`, so public exports do not depend on local `.work/` paths.

## Annotation pilot subset

`E3a` adds a narrow annotation pilot path driven by [`annotation_data/pilots/e3a_annotation_pilot/config.json`](./annotation_data/pilots/e3a_annotation_pilot/config.json).

The pilot currently names two real `benchmark_v1` items for planned transcription work, with one also carrying planned layout-label work. `build-release` validates that every pilot item is still release-ready and, for benchmark-targeted items, still selected in `benchmark_v1`. It emits:

- `build_release/annotation_pilot_manifest.json`
- `build_release/annotation_pilot_selection_audit.json`

`export-alpha` mirrors the pilot manifest and audit for the exported subset under `manifests/`. Pilot entries use release-relative planned target paths such as `annotations/<source_id>/<source_item_id>/transcription.json`; they do not assert that annotation files already exist and do not change `annotation_manifest.json` counts. Current public and alpha outputs still do not require transcriptions or layout labels.

## Benchmark ground-truth references

`F2a` defines the human-facing benchmark ground-truth conventions in [`docs/benchmark_ground_truth_guidelines.md`](./docs/benchmark_ground_truth_guidelines.md). The guidelines cover Hebrew transcription policy for logical text order, Unicode NFC normalization, right-to-left and bidi behavior, niqqud, punctuation, Hebrew/Arabic/Latin numerals, Latin fragments, abbreviations, uncertain or damaged text, marginal and deleted text, and line/page boundaries.

The same document defines layout-label guidance for page, region, line, and optional word/reference levels; pixel-based coordinate systems over normalized release assets; reading-order indexes; multi-page item handling; uncertainty/review flags; and release-relative portability constraints. It also documents minimum future child-reference shapes for `benchmark_transcription_reference.v1` and `benchmark_layout_reference.v1`, plus the parent `benchmark_reference_manifest.v1` contract for linking benchmark item ids and source identity to transcription references, layout-label references, reviewer/adjudication status, correction/versioning fields, and explicit `public`, `private_adjudication`, and `hidden_reference` visibility classes.

`F2b` implements the first runtime layer for those contracts. It validates the packaged/reference-root override manifest and child reference files during config validation and `build-release`, emits benchmark reference manifests/status/versioning artifacts, and mirrors those artifacts plus selected child reference files through `export-alpha` for exported benchmark items. `F1e` is the separate benchmark/holdout leakage gate: it records accepted overlap resolutions in the benchmark config and blocks unresolved or stale exact duplicate, near-duplicate, or source-group overlap. Neither path adds OCR/HTR model training, broad annotation tooling, network workflows, or mandatory transcription/layout-label requirements for current public and alpha outputs.

## Modern handwritten acquisition policy

`F3a` defines the policy foundation for rights-clean modern handwritten Hebrew intake in [`docs/modern_handwritten_acquisition_policy.md`](./docs/modern_handwritten_acquisition_policy.md). The policy requires explicit contributor consent and public-use release terms, rights provenance before review, conservative contemporary privacy screening, a takedown/removal workflow, scan/upload quality standards, mandatory operator review, and composition targets for demographic bands, script style, page type, and mixed-language coverage.

`F3b` implements the bounded operator workflow for custom-config intake sources without adding a default modern handwriting source to `profile_open_v1` or `profile_review_v1`. A modern intake source uses the `modern_handwriting_intake` fetcher with `settings.modern_intake_manifest`, `status: review_only`, `requires_manual_review: true`, `default_public_release: false`, and the normalized license `HEOCR-CONSENT-OPEN`.

Modern intake manifests are operator-provided JSON files with source-relative JPEG/PNG assets. `hocrgen config validate --config-root ...` and source health validation check adult contributor eligibility, consent/provenance ids, public-use release terms, clear contemporary privacy screening, takedown/removal state, scan metadata, checksums, portable paths, and composition metadata before the source can run. Valid records flow through the normal pipeline as candidate real modern handwriting, but public release inclusion still requires explicit review approval or allowlist treatment through the existing review-merge path.

Modern real handwriting remains distinct from historical public sources and synthetic data. Historical public sources continue to use upstream rights/provenance evidence and source-adapter gates; synthetic data continues to use hocrsyngen/provider manifests, synthetic disclosure, and caps. F3b does not collect or package real contributor samples, implement a public upload portal, add broad acquisition automation, change default public/alpha exports, or claim public beta readiness.

## Synthetic generation

The active `project_synthetic` source now consumes fixture-backed hocrsyngen `generation_manifest.v1` batches. hocrsyngen owns deterministic candidate sample generation; hocrgen validates the manifest and assets, maps samples into its source adapter contract, and keeps the normal governance, release, review, split, benchmark, cap, and export gates in charge.

- reads a packaged hocrsyngen fixture batch from `package://data/hocrsyngen/contracts/generation_manifest_v1/fixture-batch`
- validates `generation_manifest.json` plus relative JPEG page assets, provider dependency-boundary metadata, Hebrew rendering metadata, and computed Hebrew coverage inside hocrgen before ingestion
- preserves stable hocrgen item ids such as `project_synthetic:synthetic-0` through an explicit legacy sample-index mapping so benchmark approvals do not churn in this transition PR
- carries hocrsyngen sample id, manifest version, provider/generator version, seed, template, recipe, degradation, font, source corpus, text metadata, rendering metadata, Hebrew coverage metadata, controls, and synthetic disclosure in item metadata without publishing exact logical text as generic item metadata
- can limit manifest-backed synthetic candidates by `--synthetic-template`, `--synthetic-recipe`, and `--synthetic-degradation-preset`
- emits `synthetic_composition.json` during `build-release`, `export-alpha`, and `export-synthetic`, with template, recipe, degradation preset, font, provider version, layout family, Hebrew coverage, split, and synthetic fraction counts
- keeps synthetic release inclusion bounded by profile and alpha export caps while allowing both default hocrsyngen fixture recipes into the conservative public profile

Synthetic generation is now a conservative spinout. `hocrsyngen` owns synthetic Hebrew OCR/HTR sample generation; `hocrgen` remains the orchestration, governance, review, benchmark, split, cap, and export pipeline; `HeOCR` receives mixed real+synthetic releases; and `HeOCRsynth` receives synthetic-only releases. The old in-repo generator code and font/text fixtures remain temporarily as legacy smoke coverage, but they are no longer the default `project_synthetic` source path.

The external-provider integration is fixture-backed and dependency-light. hocrgen consumes a hardened `generation_manifest.v1`: `generation_manifest.json` plus relative page assets. Manifest v1 includes sample id, page assets, logical-order UTF-8 text, script/language/direction metadata, explicit hocrsyngen provider metadata, no-network/no-REST/no-GPU/no-LLM/no-diffusion flags, rendering metadata for logical RTL Hebrew pages, computed Hebrew coverage booleans, generator version, recipe id, seed/provenance, license `PROJECT-SYNTHETIC`, synthetic disclosure, and optional persona/condition controls. Persona and condition fields are generator controls only; they must not claim psychological truth, real-writer identity, or demographic authority.

`hocrsyngen` outputs are candidate synthetic inputs, not release-ready data by themselves. hocrgen does not call `hocrsyngen generate`, `hocrsyngen validate`, a live service, GPU model, LLM, diffusion model, or other heavyweight generator dependency in the default pipeline. hocrsyngen CLI JSON reports such as `generation_report.v1` are command output only; hocrgen consumes the batch manifest and assets. The normal rights/provenance disclosure, privacy, review, dedupe, split, benchmark, synthetic-cap, and export-portability gates decide whether generated samples appear in mixed `HeOCR` releases or synthetic-only `HeOCRsynth` releases. `export-synthetic` is the hocrgen-side HeOCRsynth handoff path and keeps its release tree visibly synthetic-only under `data/synthetic/`.

## Community contribution model

`E1a` defines contribution safety rails without adding broad new ingestion behavior. The contribution model is documentation-first and keeps source, review, synthetic, and release changes constrained by existing typed config, rights classification, privacy review, release eligibility, and export portability checks.

Start with the relevant guide:

- [CONTRIBUTING.md](./CONTRIBUTING.md) for code, data policy, source proposals, dataset issue taxonomy, and PR expectations
- [Source Adapter Contribution Guide](./docs/source_adapter_contribution_guide.md) for fixture-backed source adapter requirements
- [Synthetic Asset Contribution Guide](./docs/synthetic_asset_contribution_guide.md) for governed fonts, corpora, recipes, and synthetic reporting expectations
- [Release Governance Notes](./docs/release_governance.md) for public release rules, external review policy, dataset corrections, and planned PR metadata

Community source proposals must begin as issues, not public-profile config changes. A source adapter PR must preserve `hocrgen config validate`, policy filtering, privacy screening, review merge, split leakage checks, release eligibility, and export portability. Synthetic assets require committed license/provenance evidence and must remain subject to profile and alpha export caps.

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
hocrgen evaluate-benchmark --benchmark-manifest <benchmark_manifest.json> --predictions <predictions.jsonl> --references <references.jsonl>
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

Source-health check paths are operator-facing references, not public release payload fields. Packaged
resources are reported as `package://...`, files under the active config root are reported relative to
that root, and truly external local files remain absolute so operators can locate the configured input.

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
- `synthetic_seed`: optional legacy synthetic-generator seed override; the active hocrsyngen manifest-backed source is fixture-batch driven

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
- Contribution policy: [`CONTRIBUTING.md`](./CONTRIBUTING.md)
- Source adapter guide: [`docs/source_adapter_contribution_guide.md`](./docs/source_adapter_contribution_guide.md)
- Synthetic asset guide: [`docs/synthetic_asset_contribution_guide.md`](./docs/synthetic_asset_contribution_guide.md)
- Release governance: [`docs/release_governance.md`](./docs/release_governance.md)
- Pre-alpha freeze plan: [`docs/pre_alpha_freeze_plan.md`](./docs/pre_alpha_freeze_plan.md)
- Normalization and QA notes: [`docs/hocrgen_normalization_and_qa.md`](./docs/hocrgen_normalization_and_qa.md)
