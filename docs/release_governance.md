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

Unknown rights, restricted review-only rights, blocked sources, unresolved privacy flags, and unresolved review decisions must not be promoted into `profile_open_v1`.

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

Takedown, privacy, rights, and source-owner concerns must be routed through an issue or maintainer-private report before release changes are made. Non-sensitive corrections should use a public GitHub issue with the appropriate dataset label. Sensitive rights, privacy, or source-owner concerns should use GitHub private vulnerability reporting or a private security advisory when that repository feature is enabled. If no private repository channel is configured, maintainers must arrange an out-of-band private contact path before publishing broader public releases and must avoid asking reporters to disclose sensitive details in a public issue.

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

Feature and PR work is incomplete until a non-draft PR is open with appropriate labels, a detailed body, and a relevant milestone assignment when one exists.
