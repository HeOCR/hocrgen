# Source Adapter Contribution Guide

Source adapters are the highest-risk contribution path because they can change what enters the candidate pool. Treat every adapter change as policy work plus code.

## Pre-approval

Do not start with code. Open a `source-proposal` issue and document:

- source identity, upstream URL, and owner/operator when known
- exact rights text, license page, and any attribution/share-alike obligations
- content type, period, language, and expected OCR/HTR value
- privacy risk and whether modern personal records may appear
- sample items that are suitable for deterministic local fixtures
- proposed public status: `allowed`, `review_only`, or `blocked`
- proposed operational status and health expectations

A maintainer may ask for the source to start as `review_only` or `blocked`, or for public-profile inclusion to wait for a separate PR.

## Config checklist

Every source adapter PR must keep source policy visible in `src/hocrgen/config/sources.yaml`.

Required source fields:

- `id`: stable lowercase identifier
- `fetcher`: adapter key implemented under `src/hocrgen/fetchers/`
- `status`: `allowed`, `review_only`, or `blocked`
- `default_public_release`: whether the source is eligible by default for public profiles
- `allowed_content_types`: explicit expected content classes
- `rights_strategy`: exact or conservative parser strategy
- `normalized_license`: controlled license value from `src/hocrgen/config/licenses.yaml`
- `rights_classification`: `open`, `open_with_attribution`, `sharealike`, `restricted_review_only`, or `blocked`
- `requires_manual_review`: whether candidates must enter the review path
- `source_operations`: operational status, reason for non-active states, and minimum health expectations

Public profile changes must also be checked against `src/hocrgen/config/profiles/profile_open_v1.yaml`. Unknown rights, restricted review-only rights, and blocked sources must not enter `profile_open_v1`.

## Implementation checklist

Keep adapter code local to the acquisition layer:

- implement source-specific parsing in `src/hocrgen/fetchers/`
- use typed candidate and item records rather than ad hoc dictionaries where models exist
- keep path references portable and avoid absolute local paths in public output fields
- add fixture data under `src/hocrgen/data/<source>/` when it is packaged runtime data, or under `tests/fixtures/<source>/` for test-only inputs
- extend source-health checks when the adapter has fixture or asset expectations
- use `StageExecutionError` for stage failures that should surface as structured command errors

Source-health artifacts are operator-facing run artifacts rather than public release payloads, but
their check paths should still be stable where possible. Prefer `package://...` references for
packaged runtime data and config-root-relative references for files under the active config root.
Only use absolute paths for deliberately external local inputs that cannot be represented relative
to the package or config root.

Do not add broad live crawling, live network crawling, scheduled ingestion, automatic source promotion, or publication behavior unless the roadmap explicitly calls for it.

The NLI release-scale path is a narrow exception: live-but-cached acquisition of vetted seed URLs is allowed when the implementation keeps the seed boundary explicit, reuses existing local fixtures before live capture, writes reusable local fixtures/assets, emits an audit report, and leaves CI/release validation network-free. That path must still run through normal source policy, rights, privacy, review, dedupe, split, benchmark, and export-portability gates before any public release.

Modern handwritten Hebrew intake is a separate high-risk source family. Follow [Modern Handwritten Acquisition Policy](./modern_handwritten_acquisition_policy.md) and the F3b `modern_handwriting_intake` manifest contract before proposing an adapter or workflow: contributor consent, public-use release terms, rights provenance, contemporary privacy screening, takedown/removal handling, scan/upload standards, operator review, and composition metadata must exist before any sample collection. Historical public-source rights and synthetic-provider manifests do not satisfy modern contributor-consent requirements.

## Review and release gates

Before a source adapter can affect public outputs, the source must pass:

1. `hocrgen config validate`
2. policy filtering under the target release profile
3. normalization and QA checks for committed fixtures
4. exact dedupe and split leakage checks
5. privacy scanning
6. review export and review merge when the source or item requires review
7. `build-release` release eligibility checks
8. `export-alpha` portability checks when release exports are affected

If any gate is unresolved, keep the source out of the public profile or mark the source frozen/degraded with an explicit reason.

## Tests

Add deterministic tests that prove:

- valid source config loads through typed validation
- unknown or unsupported rights are rejected or routed to review
- fixture-backed discovery/acquisition produces stable candidate ids
- source-health output reports missing or insufficient fixtures
- public exports remain release-relative and portable when the source is included

Network-dependent workflows belong in operator scripts or manual docs, not CI tests.
