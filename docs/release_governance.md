# Release Governance Notes

hocrgen release governance is intentionally conservative. Public payloads are produced from typed config, explicit review artifacts, release-profile gates, and portable export manifests.

## Version governance and compatibility

Published releases are immutable public records. A release version should not be edited in place after publication except for repository-level administrative repair that does not change dataset semantics. Dataset corrections, item removals, source status changes, benchmark changes, and metadata fixes should land in the next release version.

Every public release should carry a compatibility anchor:

- `manifests/release_record.json` identifies the release version, profile, included sources, hocrgen commit, export time, and schema version.
- `manifests/release_summary.json` reports public payload counts and the active export caps.
- `manifests/item_manifest.json` is the public item contract for exported items.
- `manifests/release_diff.json` and `docs/CHANGELOG.md` explain additions, removals, and changes relative to the selected baseline.

Compatibility expectations:

- patch-level release corrections should preserve existing manifest fields and item identifiers whenever possible
- minor release growth may add items, additive manifest fields, sources, or docs, but must preserve release-relative paths and public-profile gates
- breaking serialized schema changes require a new schema version or schema id, migration notes, updated validation/tests, and explicit release notes
- release consumers should use `schema_version` and schema ids rather than inferring compatibility from filenames alone

## Public release rules

Public releases must:

- include only release-ready items selected by the target release profile
- exclude review-required and blocked items from dataset payloads
- keep review-required and blocked items as audit manifests only when exported
- preserve per-item provenance, rights, privacy, classification, split, and benchmark metadata
- keep release/export paths release-relative and portable
- keep synthetic data bounded by profile and alpha export caps
- emit release diffs, changelogs, provenance, dataset cards, and handoff notes

Synthetic-only `HeOCRsynth` releases are a separate release stream from mixed `HeOCR` releases. They must:

- be produced by `hocrgen export-synthetic`, not by copying raw hocrsyngen generator directories
- include only release-ready synthetic items from existing hocrgen pipeline state
- run the full configured hocrgen pipeline before filtering; source-limited synthetic exports are rejected because they can bypass mixed release gates such as benchmark membership validation
- keep payload assets under `data/synthetic/<split>/<item_id>/`
- preserve `PROJECT-SYNTHETIC`, synthetic disclosure, hocrsyngen provider metadata, rendering metadata, and Hebrew coverage metadata
- use release records with `dataset_id: HeOCRsynth`, `release_kind: synthetic_only`, `synthetic_only: true`, and `real_items: 0`
- exclude real-source NLI, Pinkas, BiblIA, modern handwriting, and other non-synthetic items from payload and audit manifests
- avoid public beta or mixed-dataset readiness claims

## Public beta readiness gates

Mixed `HeOCR` public beta publication is a stricter publishability decision than a successful operator trial. The F1c target-scale trial may provide evidence that candidate acquisition and gates can run, but its artifacts are operator-only until the F5a readiness contract is satisfied. In particular, the current F1c synthetic evidence remains blocked for public beta readiness because full synthetic target scale still requires a larger validated hocrsyngen batch.

Before mixed public beta publication, maintainers must verify the canonical F5a gate matrix in [`docs/HeOCR_hocrgen_long_term_roadmap.md`](./HeOCR_hocrgen_long_term_roadmap.md). F5b now emits a machine-readable `manifests/public_beta_readiness_report.json` through `hocrgen export-public-beta`, with one entry per gate, source evidence artifact paths, status, and rationale. Public beta publication is allowed only when every gate status is `pass`; a `blocked` gate must stop repository sync, upload, release tagging, and publication reports.

The governance summary of those gates is:

- source depth and composition evidence for the planned real-source mix, with source-depth-only fixtures promoted through normal release-profile and review gates before they can count as public payload
- synthetic target-scale evidence from a validated hocrsyngen `generation_manifest.v1` batch, with synthetic inclusion kept within the active public-profile/export cap policy
- normalized release-compatible rights, provenance, attribution, consent/provider evidence where applicable, and no unresolved rights-review state for every public item
- no review-required, blocked, unresolved privacy, unresolved modern-handwriting consent, or unresolved takedown/removal states in the public payload
- exact duplicate, near-duplicate, source-group, split, synthetic-sibling, and benchmark/holdout leakage risks are clear or resolved by typed repo-tracked accepted resolutions
- stable benchmark membership plus benchmark-reference status/versioning artifacts, with reference coverage and limitations disclosed
- optional annotation, pilot, transcription, and layout references are release-relative, status-labeled, and not implied to be complete when they are not mandatory
- release records, item manifests, SHA-256 checksum manifests, archive manifests, benchmark/reference paths, release diffs, changelogs, and docs are release-relative and do not expose absolute local paths, `.work/` state, `file://` references, or network-dependent reproducibility assumptions
- `DATASET_CARD.md`, `PROVENANCE.md`, `CHANGELOG.md`, `RELEASE_NOTES.md`, benchmark docs, and handoff notes describe composition, source mix, synthetic fraction, rights posture, benchmark/reference status, annotation status, validation, limitations, and known blockers
- rights, privacy, source-owner, takedown, correction, and source-breakage reports have a public or private intake path before publication

F5b implements local publication packaging and handoff verification, not publication itself. The command writes `manifests/checksum_manifest.json`, `manifests/archive_manifest.json`, `manifests/public_beta_readiness_report.json`, beta-specific docs, and a portable version-rooted archive, then verifies asset and archive digests from the handoff tree. F5c adds `manifests/public_beta_blocker_closure_plan.json`, which derives the blocker sequence from the readiness report, separates `repo_owned_immediately_actionable` blockers from `external_input_dependent` blockers, and keeps the hocrsyngen `80` synthetic-control target blocked until a larger validated batch exists. F5d adds `manifests/public_beta_repo_owned_blocker_report.json`, which records unresolved review/privacy item ids and reasons, benchmark-reference draft/unavailable/adjudication status by item, and takedown/private-reporting settings-check evidence from `src/hocrgen/config/public_beta.yaml`. It must not sync a repository, upload to a host, tag a release, or emit a blocked publication report while any readiness gate is unresolved.

F6 is the post-F5 closure roadmap, not a readiness shortcut. `F6a` defines the sequence. `F6b` closes takedown/private reporting readiness only because `src/hocrgen/config/public_beta.yaml` records GitHub private vulnerability reporting for `HeOCR/hocrgen` as enabled and verified by an authenticated GitHub API repository-settings check. `F6c` evaluates benchmark-reference readiness and keeps it blocked because current coverage is only `1 / 3` selected benchmark items with reviewed/adjudicated references. Later F6 PRs may close remaining individual blockers only with real evidence: repo-tracked review/config/source-status changes for privacy/review closure, real public-profile source-depth/composition evidence, and a larger validated hocrsyngen `generation_manifest.v1` batch for synthetic target scale. Partial or unavailable benchmark coverage may be disclosed as a limitation, but it must not be renamed into a passing readiness gate unless a separate governance PR explicitly changes the public beta contract. The current `2 / 80` synthetic evidence, source-depth composition gaps, benchmark-reference limitations, and privacy/review blockers must remain blocked until their respective evidence exists.

Unknown rights, restricted review-only rights, blocked sources, unresolved privacy flags, and unresolved review decisions must not be promoted into `profile_open_v1`.

Modern handwritten contributor material must additionally satisfy the F3a/F3b policy before public-profile use: explicit contributor consent, compatible public-use release terms, rights provenance, contemporary privacy clearance, typed operator intake manifests, source-relative assets, operator review, and a documented takedown/removal path. F3b does not add a default modern handwriting source or collect/package real contributor samples; configured modern intake records remain review-only until explicitly approved.

## External contribution review policy

External PRs that touch source config, source adapters, review policy, synthetic assets, release profiles, benchmark approvals, or export packaging require maintainer review focused on:

- rights evidence and normalized license correctness
- privacy risk and review routing
- source operational reliability and fixture coverage
- release-profile impact
- synthetic fraction and benchmark stability impact
- portability of public artifacts
- deterministic validation evidence

Maintainers should prefer freezing, degrading, or keeping a source review-only over accepting ambiguous public-release risk.

## Dataset corrections and removals

Dataset issue reports should be handled as auditable changes:

- rights concerns become `rights-review` issues and block public promotion until resolved
- privacy concerns become `privacy-review` issues and keep affected items review-required or blocked
- metadata or asset corrections become `dataset-correction` issues with fixture-backed updates
- source instability becomes `source-breakage` and may set the source operational status to `frozen` or `degraded`
- release-affecting removals must appear in release diffs and changelogs

Release history should explain removals rather than hiding them. If a correction changes a public item, the next release should make the change visible through `release_diff.json` and `CHANGELOG.md`.

## Removal and takedown workflow

Takedown, privacy, rights, and source-owner concerns must be routed through an issue or maintainer-private report before release changes are made. Non-sensitive corrections should use a public GitHub issue with the appropriate dataset label. Sensitive rights, privacy, or source-owner concerns should use GitHub private vulnerability reporting or a private security advisory when that repository feature is enabled. If no private repository channel is configured, maintainers must arrange an out-of-band private contact path before publishing broader public releases and must avoid asking reporters to disclose sensitive details in a public issue. The repo-owned public beta governance config at `src/hocrgen/config/public_beta.yaml` records the public reporting path, private reporting path label/channel, whether that private path is configured with verification metadata, the latest repository settings check when available, and the required operator action when the path is not configured. The current GitHub private vulnerability reporting check is recorded as enabled and verified for `HeOCR/hocrgen`, so the takedown gate can pass from that evidence while unrelated readiness gates remain blocked until their own evidence exists.

For modern handwritten contributor material, takedown handling must also check contributor consent artifact ids, institutional batch agreement ids, and any affected aggregate composition metadata. Public release notes should avoid exposing private contributor evidence while still documenting the dataset-visible removal where disclosure is safe.

The minimum handling path is:

1. classify the concern as `rights-review`, `privacy-review`, `dataset-correction`, or `source-breakage`
2. identify the affected source ids, item ids, release versions, and benchmark membership
3. block public promotion through review/config/source-status changes before the next export
4. re-run the release validation commands for the affected profile
5. document the removal in `release_diff.json`, `CHANGELOG.md`, release notes, and the PR body

If an item must be removed from a future public payload, use the narrowest accurate machine-readable removal reason available: `review_required`, `blocked`, `duplicate_removed`, `selection_limit_excluded`, or `missing_from_current_run`. Because those current manifest reasons are intentionally coarse, every rights, privacy, takedown, or source-policy removal must also carry a human-readable audit rationale in the changelog, release notes, and PR body. When the public rationale must be limited for privacy or legal reasons, say that explicitly and keep the full evidence in the private maintainer record.

More granular removal taxonomy should be treated as future schema work if removals become frequent enough that coarse machine reasons no longer support clear release-to-release audits.

## Schema migration policy

Schema evolution should be additive by default:

- adding optional fields with safe defaults is acceptable when tests and docs are updated
- removing fields, changing item ids, changing path semantics, or changing controlled-vocabulary meanings is breaking
- annotation, benchmark, and release schemas should keep explicit `schema_version` or schema id fields
- new annotation or benchmark file formats should use new schema ids rather than silently redefining existing ids
- migrations that affect public consumers must be described in release notes and design/spec docs

Current public and alpha outputs keep annotation fields optional. Schema changes must not make transcriptions, layout labels, or annotation pilot targets mandatory for `profile_open_v1` unless a future roadmap item deliberately changes the public release contract.

## Source deprecation policy

Source deprecation is preferred over sudden removal when rights and privacy posture allow it. Maintainers should choose the least disruptive state that preserves public safety:

- `active` sources may contribute to public profiles when all gates pass
- `degraded` sources may remain usable with explicit health warnings and fixture-backed validation
- `frozen` sources should stop new acquisitions while preserving already reviewed fixtures where policy allows
- review-only treatment is appropriate when public rights or privacy evidence is ambiguous
- blocked or removed treatment is appropriate when public release risk cannot be resolved

Deprecating a source must preserve deterministic release behavior: no benchmark item may disappear silently, no split leakage may be introduced, and public exports must remain release-relative and portable.

## Benchmark stability guarantees

`benchmark_v1` is intentionally small and stable. Approved benchmark items must remain explicitly named in the packaged approval config at `package://data/benchmark/benchmark_v1/config.json` (repository source path: `src/hocrgen/data/benchmark/benchmark_v1/config.json`), release-ready after review merge, present in the current run, and assigned to their committed benchmark split. Config-root-relative `benchmark_data/` trees may override this for deliberate local validation, but default and non-editable installs must not depend on a checkout-root `benchmark_data/` directory. If any of those invariants fail, `build-release` should fail instead of silently changing the benchmark.

Benchmark members also must not share exact duplicate, near-duplicate, or source-group membership with non-benchmark holdout/public-beta candidates unless the benchmark config contains a typed accepted resolution that matches the current detected group and member set. Missing or stale benchmark/holdout leakage resolutions should block F1 trial/report readiness. Accepted resolutions may exclude related non-benchmark items from holdout/public-beta claims without changing benchmark membership, but they must be explicit, reviewed, and auditable.

Benchmark removals or replacements require a deliberate PR that updates the benchmark config, benchmark card, release notes, and planning docs. The PR must explain why the change is necessary and how consumers should compare results across the affected release versions.

## Planning and PR metadata

Roadmap-tracked PRs must update `.agent-plan.md`, `README.md`, and affected docs in the same branch. The PR title must use `<notation>: <sentence-case summary>`, and the PR body must include a top-level `## Planning notation` section naming:

- notation
- parent milestone
- roadmap source document

For the original E1a contribution-safety pass, the required planning notation was:

- notation: `E1a`
- parent milestone: `E1`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For E4a, the required planning notation is:

- notation: `E4a`
- parent milestone: `E4`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F3a, the required planning notation is:

- notation: `F3a`
- parent milestone: `F3`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F4c, the required planning notation is:

- notation: `F4c`
- parent milestone: `F4 - External synthetic provider integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F4d, the required planning notation is:

- notation: `F4d`
- parent milestone: `F4 - External synthetic provider integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F4e, the required planning notation is:

- notation: `F4e`
- parent milestone: `F4 - External synthetic provider integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F5a, the required planning notation is:

- notation: `F5a`
- parent milestone: `F5 - Public beta and publication readiness`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F5b, the required planning notation is:

- notation: `F5b`
- parent milestone: `F5 - Public beta and publication readiness`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F5c, the required planning notation is:

- notation: `F5c`
- parent milestone: `F5 - Public beta and publication readiness`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F5d, the required planning notation is:

- notation: `F5d`
- parent milestone: `F5 - Public beta and publication readiness`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F6a, the required planning notation is:

- notation: `F6a`
- parent milestone: `F6 - Public beta closure and external input integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F6b, the required planning notation is:

- notation: `F6b`
- parent milestone: `F6 - Public beta closure and external input integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

For F6c, the required planning notation is:

- notation: `F6c`
- parent milestone: `F6 - Public beta closure and external input integration`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

Feature and PR work is incomplete until a non-draft PR is open with appropriate labels, a detailed body, and a relevant milestone assignment when one exists.
