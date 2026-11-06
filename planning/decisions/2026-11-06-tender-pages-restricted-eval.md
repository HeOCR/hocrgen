# Decision 2026-11-06: tender pages are for private evaluation only

- **Date:** 2026-11-06
- **Decided by:** the maintainer
- **Status:** accepted

Context: [issue #86](https://github.com/HeOCR/hocrgen/issues/86) proposed about five Israeli government tender pages (mr.gov.il) with human transcriptions. It was closed on 2026-11-06 because the pages cannot enter the HeOCR dataset. They are State works under Copyright Act §§36 and 42, with no open licence. The gov.il terms forbid copying and making the pages available without written consent, and the tenders' own IP clause limits use to bid preparation. A copyright notice alone gives no permission.

## Decision

1. **Now.** The pages may be kept only in the private repository `HeOCR/heocr-restricted-eval`, as an evaluation-only set (`il-tender-pages-v0`):
   - never used for training or tuning;
   - only aggregate metrics are published;
   - never images, transcriptions or quoted text.
2. **In parallel.** A legal opinion is requested on whether a handful of such pages may sit in a public repository for test and evaluation only, under fair use (§19).
3. **If the opinion approves.** The pages move to a public repository with an explicit notice: "© State of Israel, all rights reserved; included for evaluation only; not covered by the repository licence". They must also have a takedown path and privacy screening.

## Consequences

- The pages stay out of every hocrgen source, profile and release, including `profile_review_v1`.
- **Import into `heocr-restricted-eval` needs two things first:**
  - the contributing institution's authorization for the transfer, since the transcriptions are its staff's work;
  - per-page privacy screening.
- The transcriptions are self-attested and not adjudicated, so they stay candidate references, not gold.
