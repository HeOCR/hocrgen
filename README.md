# hocrgen

[![Validate](https://github.com/HeOCR/hocrgen/actions/workflows/validate.yml/badge.svg)](https://github.com/HeOCR/hocrgen/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

`hocrgen` is the dataset operations and release-governance toolchain for the
HeOCR Hebrew OCR/HTR ecosystem. It turns rights-reviewed source candidates into
auditable, dry-run release artifacts for the mixed `HeOCR` dataset and the
synthetic-only `HeOCRsynth` stream.

Use this repository to inspect or run acquisition, rights, privacy, review,
dedupe, split, benchmark, and export gates. Use the downstream dataset
repositories when you need published dataset payloads.

## Current Status

Public-beta packaging exists, but publication is deliberately blocked until the
remaining source-depth, synthetic-scale, benchmark-reference, privacy, and
review evidence gates pass. The default repo experience is deterministic,
fixture-backed, and network-free.

The shortest way to understand the posture:

| Question | Answer |
| --- | --- |
| Is this a crawler? | No. It is a governed release-prep pipeline with bounded source adapters and fixtures. |
| Does a dry run publish anything? | No. Dry runs write auditable local artifacts under `.work/hocrgen/`. |
| Is the public beta ready? | No. The blocker reports are intentional and must remain visible until closed by evidence. |
| Is the software open source? | Yes. The code is MIT-licensed; individual dataset items keep their own rights metadata. |

## First Commands

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
hocrgen config validate
hocrgen build-release --profile profile_open_v1 --dry-run
```

The `build-release` dry run exercises the release-prep pipeline without syncing
to `HeOCR`, uploading to Hugging Face or Kaggle, tagging a release, or publishing
`HeOCRsynth`.

## How It Fits

```
public-domain-hand-written-hebrew-scans
            |
            v
      hletterscriptgen
            |
            v
        hletterscript
            |
            v
        hocrsyngen
            |
            v
          hocrgen
        /        \
       v          v
    HeOCR    HeOCRsynth
```

`hocrgen` sits at the governance boundary. It consumes source candidates,
normalizes evidence, applies release policy, and emits portable handoff trees.
It does not replace the upstream glyph/synthetic tooling, and it does not make
raw upstream batches public-release eligible by itself.

For exact repository boundaries, see
[`docs/heocr_ecosystem_overview.md`](./docs/heocr_ecosystem_overview.md).

## What It Does

| Area | What `hocrgen` provides |
| --- | --- |
| Source intake | Typed source config, fixture-backed adapters, source-health reports, and explicit degraded/frozen states. |
| Rights and review | License normalization, profile eligibility rules, privacy gates, review queues, and repo-tracked allow/block decisions. |
| Dataset shaping | Normalization, checksums, technical QA, exact dedupe, near-duplicate/source-group leakage checks, splits, and benchmark selection. |
| Release packaging | Release manifests, checksums, archives, public-beta blocker reports, alpha exports, and synthetic-only handoff trees. |
| Contribution safety | Documented paths for source proposals, source adapters, synthetic assets, review data, and policy changes. |

## Where To Go Next

| Need | Start here |
| --- | --- |
| Detailed operator and agent reference | [`AGENT_README.md`](./AGENT_README.md) |
| Contribution rules | [`CONTRIBUTING.md`](./CONTRIBUTING.md) |
| Ecosystem boundaries | [`docs/heocr_ecosystem_overview.md`](./docs/heocr_ecosystem_overview.md) |
| Pipeline design and artifact contracts | [`docs/hocrgen_design_and_spec.md`](./docs/hocrgen_design_and_spec.md) |
| Normalization and technical QA | [`docs/hocrgen_normalization_and_qa.md`](./docs/hocrgen_normalization_and_qa.md) |
| Source-adapter work | [`docs/source_adapter_contribution_guide.md`](./docs/source_adapter_contribution_guide.md) |
| Synthetic asset work | [`docs/synthetic_asset_contribution_guide.md`](./docs/synthetic_asset_contribution_guide.md) |
| Release governance | [`docs/release_governance.md`](./docs/release_governance.md) |
| Modern handwriting policy | [`docs/modern_handwritten_acquisition_policy.md`](./docs/modern_handwritten_acquisition_policy.md) |
| Roadmap and public-beta closure | [`docs/HeOCR_hocrgen_long_term_roadmap.md`](./docs/HeOCR_hocrgen_long_term_roadmap.md) |
| LLM-oriented repository context | [`llms.txt`](./llms.txt) |

## Common Workflows

Validate local configuration:

```bash
hocrgen config validate
```

Run a governed release-prep dry run:

```bash
hocrgen build-release --profile profile_open_v1 --dry-run
```

Inspect public-beta readiness without publishing:

```bash
hocrgen export-public-beta --profile profile_open_v1 --dry-run
```

Run the baseline validation expected before handoff:

```bash
coverage run -m pytest
hocrgen config validate
hocrgen build-release --profile profile_open_v1 --dry-run
```

## Release Boundary

`hocrgen` is conservative by design. Items with unresolved rights, privacy,
review, takedown, benchmark, source-depth, or split-leakage evidence must stay
blocked, review-only, or out of the public payload. Public release docs and
exports should be portable, release-relative, and free of absolute local paths.

When a readiness gate is blocked, that is useful evidence: it tells maintainers
what must be closed before public publication can be claimed.

## License

`hocrgen` is distributed under the [MIT License](./LICENSE). Dataset items and
generated payloads carry their own normalized rights metadata and release
eligibility status; the software license does not override item-level rights,
privacy, review, takedown, benchmark, or publication gates.
