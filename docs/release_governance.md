# Release Governance Notes

hocrgen release governance is intentionally conservative. Public payloads are produced from typed config, explicit review artifacts, release-profile gates, and portable export manifests.

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

## Planning and PR metadata

Roadmap-tracked PRs must update `.agent-plan.md`, `README.md`, and affected docs in the same branch. The PR title must use `<notation>: <sentence-case summary>`, and the PR body must include a top-level `## Planning notation` section naming:

- notation
- parent milestone
- roadmap source document

For E1a, the required planning notation is:

- notation: `E1a`
- parent milestone: `E1`
- source: `docs/HeOCR_hocrgen_long_term_roadmap.md`

Feature and PR work is incomplete until a non-draft PR is open with appropriate labels, a detailed body, and a relevant milestone assignment when one exists.
