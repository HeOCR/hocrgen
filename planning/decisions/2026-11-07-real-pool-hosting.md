# Decision 2026-11-07: where the real-source pool will be published

- **Date:** 2026-11-07
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Status:** accepted
- **Applies to:** publishing the real-source pool (real scans with human-made text: Wikisource, Reshumot, Pinkas,
  PBY aligned to NLI) and the release exports built from it

**Context.** The real pool exists only on the operator machine. F8g (HeOCR/hocrgen#131) proposed hosting it on Zenodo
plus a Hugging Face dataset repo, and weighed GitHub release assets and Git LFS.

## Decision

> "Yes, that plan" (Shay Palachy Affek, 2026-11-07).

1. **Zenodo is the archive.** Each published version of the pool is deposited on Zenodo. Its DOI is recorded in the
   committed release manifest. Zenodo versions are immutable, so a correction is a new version, not an edit.
2. **Hugging Face is the distribution channel.** The release exports go to a Hugging Face dataset repo, which is
   already a listed publish target.
3. **No Git LFS** for pool data, because of quotas and heavy clones. GitHub release assets stay optional.

## Consequences

- This decides *where*, not *when*. Publication still needs every public-beta gate to pass
  (`export-public-beta` stops while any gate is blocked), and each upload still needs the maintainer's approval.
- Nothing from `heocr-restricted-eval` (including the tender pages) is ever part of the pool or its deposits.
- Each item keeps its own source licence and attribution in the deposit (CC BY-SA 4.0 for Wikisource text, public
  domain for PBY text and Reshumot, the NLI licence slug for each scan).
