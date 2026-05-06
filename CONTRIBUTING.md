# Contributing to hocrgen

`hocrgen` accepts contributions that improve the HeOCR dataset toolchain while preserving the project's conservative rights, privacy, source-quality, review, and release safeguards.

This repository is not a general archive crawler. New data work must move through explicit policy, typed config, deterministic fixtures, review artifacts, and release eligibility checks before it can affect a public dataset payload.

The review policy for external changes is conservative: when rights, privacy, source quality, or release impact is unclear, keep the change review-only, blocked, frozen, or deferred until the evidence is explicit.

## Contribution paths

Use the path that matches the change:

| Contribution type | Start with | Required guardrails |
| --- | --- | --- |
| Code-only pipeline or CLI fix | an issue or pull request explaining the behavior change | deterministic tests, no weakening of config/profile/review validation |
| Source proposal | a dataset source proposal issue | no code or public-profile change until rights, provenance, privacy, source stability, and fixture strategy are accepted |
| Source adapter | source proposal approval plus a focused adapter PR | typed `sources.yaml` entry, fixture-backed tests, source-health expectations, release-profile review |
| Modern handwriting intake | F3a-compatible policy proposal before any sample collection | contributor consent, public-use release terms, contemporary privacy review, takedown path, composition metadata, and bounded operator workflow |
| Synthetic asset | synthetic asset proposal issue | license proof, manifest entry, deterministic output checks, synthetic cap compatibility |
| Review data update | focused review-decision or override PR | one-record-per-file JSON under `review_data/`, reviewer/rationale/timestamp, no broad allowlists |
| Documentation or policy fix | focused PR | keep README, roadmap, and planning tests aligned when workflow expectations change |

## Source proposal workflow

Open an issue before adding source code or changing release profiles. A source proposal should include:

- upstream collection name, URL, and operator/contact when known
- content type and why it improves HeOCR's Hebrew OCR/HTR scope
- exact rights statement, license page, or terms text used for the proposal
- whether the source is public-release eligible, review-only, or blocked until legal/privacy review
- expected privacy risk, especially for modern handwritten material or named people
- expected source stability and whether deterministic local fixtures can be committed
- proposed adapter type: packaged static records, seed-manifest flow, or future live adapter
- sample items that can pass current normalization, QA, dedupe, privacy, review, and release checks

Acceptance of a proposal does not approve broad ingestion. It only authorizes a bounded follow-up PR that keeps the existing pipeline safeguards in place.

Modern handwritten Hebrew proposals must also follow the `F3a` policy and F3b manifest workflow in [Modern Handwritten Acquisition Policy](./docs/modern_handwritten_acquisition_policy.md). Do not collect contributor samples, add upload forms, or place modern handwriting in `profile_open_v1` unless a review-only `modern_handwriting_intake` source records consent/provenance, privacy-screening status, source-relative assets, composition metadata, and review decisions in typed repo-tracked artifacts.

## Source adapter rules

A source adapter PR must be narrow and fixture-backed.

Required implementation shape:

- add or update a typed source entry in `src/hocrgen/config/sources.yaml`
- keep `status`, `default_public_release`, `rights_strategy`, `normalized_license`, `rights_classification`, and `requires_manual_review` explicit
- add `source_operations` expectations so fixture or packaged source breakage is visible in `discover/source_health.json`
- add deterministic fixtures under `src/hocrgen/data/` or `tests/fixtures/`
- extend a stage-specific fetcher in `src/hocrgen/fetchers/` instead of adding unrelated orchestration logic to `src/hocrgen/cli.py`
- prove unknown or non-public rights are rejected or routed to review under the relevant profile
- keep network-dependent discovery out of CI tests
- for modern handwritten Hebrew intake, use a review-only `modern_handwriting_intake` source with a typed operator manifest, `HEOCR-CONSENT-OPEN`, source-relative assets, and explicit review approval before release inclusion

Adapter PRs must not:

- add broad live crawling without an explicit roadmap item
- include items with ambiguous rights in `profile_open_v1`
- bypass `hocrgen config validate`, policy filtering, privacy screening, review merge, split leakage checks, or export packaging
- expose absolute local filesystem paths in release/export artifacts

See [Source Adapter Contribution Guide](./docs/source_adapter_contribution_guide.md) for the full checklist.

## Synthetic asset contribution rules

Synthetic contributions are welcome only when the asset license and generation behavior remain auditable.

Acceptable synthetic asset changes include:

- governed font additions with license text and manifest metadata
- curated Hebrew text corpus updates with provenance notes
- deterministic recipe or degradation changes with composition reporting coverage
- documentation that clarifies generated asset limits and known layout limitations

Synthetic asset PRs must not:

- add fonts, scans, templates, or text corpora without clear reuse rights
- make synthetic data dominate public release outputs
- remove synthetic fraction caps or alpha export real-item clamps
- introduce prompts, assets, or generated text that cannot be reviewed and reproduced

See [Synthetic Asset Contribution Guide](./docs/synthetic_asset_contribution_guide.md) for the required metadata and tests.

## Dataset issue taxonomy

Use issue titles and labels that make the risk clear:

| Issue kind | Use when | Expected outcome |
| --- | --- | --- |
| `source-proposal` | proposing a new upstream source or source-policy change | accepted, rejected, or deferred before adapter work starts |
| `rights-review` | rights text, normalized license, or release eligibility is unclear | public release remains blocked until resolved |
| `privacy-review` | metadata or content may identify living people or sensitive records | item remains review-required or blocked until resolved |
| `source-breakage` | an existing adapter, fixture, or source-health expectation fails | source may be frozen/degraded rather than silently included |
| `dataset-correction` | an existing manifest, provenance, asset, or metadata field is wrong | corrected through reviewable config/data changes |
| `synthetic-asset` | adding or changing fonts, corpora, recipes, templates, or degradation behavior | accepted only with license/provenance and deterministic tests |
| `release-governance` | release notes, removals, changelogs, benchmark stability, or export policy changes | release docs and planning state stay synchronized |
| `docs-policy` | contribution, review, or operating policy needs clarification | policy docs and drift tests are updated together |

## Pull request expectations

Before handoff, run the validation that matches the change. For roadmap and release-facing work, the baseline is:

```bash
coverage run -m pytest
hocrgen config validate
hocrgen build-release --profile profile_open_v1 --dry-run
hocrgen export-alpha --profile profile_open_v1 --dry-run --overwrite
```

If a PR changes alpha packaging or release exports, include the alpha export command in validation evidence. If it changes source config, synthetic assets, review policy, or release governance, update README and planning docs in the same PR.

Roadmap-tracked PRs must use the planned notation in the PR title and body. For example, `E1a: Community contribution model and contribution safety rails` with a top-level `## Planning notation` section naming the notation, parent milestone, and roadmap source document.
