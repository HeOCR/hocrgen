# Decision 2026-11-07: a verified line counts as adjudicated, like Wikisource quality 4

- **Date:** 2026-11-07
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Status:** accepted
- **Applies to:** `E2d6` single-line verification ([`docs/e2d6_line_verification.md`](../../docs/e2d6_line_verification.md))

**Context.** E2d6 shows a human one printed line on a real scan with a candidate transcription that a *different*
human typed. The candidate comes from one of two places:

- a Hebrew Wikisource quality-3 page, where one named proofreader typed and proofread it;
- a Project Ben-Yehuda text aligned to an NLI free-use scan, where a PBY volunteer typed it.

The verifier confirms the candidate (`exact`) or corrects it (`edited`) in the app. The question was whether typist
plus verifier counts as adjudicated, the same standard as Wikisource quality 4 (F8 decision 2: two named humans, a
proofreader and a validator).

## Decision

> "Yes, like quality 4" (Shay Palachy Affek, 2026-11-07).

1. **Adjudicated.** A line counts as adjudicated when one human typed its candidate and a second human then verified
   it in the app (`exact` or `edited`). This holds for both sources, Wikisource quality 3 and PBY. Such a line is
   `reference_eligible: true` for evaluation, with `attestation_status: typist_and_verifier_adjudicated` and
   `adjudication_status: adjudicated`.
2. **Excluded lines.** `unreadable` and `misaligned` lines are excluded. A `misaligned` line is also counted as
   feedback on alignment quality.
3. **Edited lines.** An `edited` line's reference is the reviewer's text. The provenance of both texts is kept: the
   candidate, its `candidate_provenance`, the reviewer's text and `corrected: true`.
4. **Two different people.** The verifier must be a different person from the typist. This is always true for these
   sources:
   - the typists are Wikisource editors and PBY volunteers, recorded upstream;
   - the verifiers are pseudonymous `rv_` reviewers in the app.

   The references file records `verifier_differs_from_typist: true`.
5. **Release splits.** Each line keeps its book's release split. Lines from `train` books are not held-out
   evaluation. Validation + test stays a labelled diagnostic until the splits change (E2d3e).

## Consequences

- **The policy lives in one place.** It is `hocrgen.tools.line_verify.ATTESTATION_POLICY = "adjudicated"`. The
  conservative alternative, `single_human_verified` (`reference_eligible: false`), stays defined. Switching to it is
  a one-line change.
- **Several reviewers.** `min_reviewers` stays at 1, as in E2d4. When several reviewers decide one line, all must
  agree; otherwise the line is a `conflict` and nothing applies.
- **What has not changed.** No score, scored set, split or `benchmark_v1` changes from this decision. Verified lines
  become line-level references only through `line_verify ingest` (`docs/line_verify_references.json`). How they are
  scored next to the page-level set is a separate step.
