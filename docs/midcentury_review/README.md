# Mid-century review: scoring rules and scripts (heocr-eval)

This is the record copy of how heocr-eval scores the mid-century new-printed review batch (`newprinted_midcentury_v0`,
batch manifest v1). The tool that builds the scored sets is `hocrgen.tools.midcentury_review` (E2g1). The scripts in
`scripts/` are verbatim copies of eval's working scripts, which run from the HeOCR task workspace (`tasks/`); they are
here so the code that produces the scores is on record. A change to the rules lands here as a new commit before it is
used.

**Pre-registration.** The zero-exposure rule below was decided by lead on 2026-11-13, before any review decision: a
read-only D1 export at 2026-11-13T13:01:54Z showed 0 decisions. A hashed copy of the spec and scripts is also in
heocr-restricted-eval (`preregistration/midcentury_2026-11-13/`). The rule is pre-registered only against the review
decisions; the R8b exposure table was already known when it was set.

The section below is copied from the batch spec (`REVIEW_BATCH_SPEC.md`).

## Scoring (planned)

- **Pipeline (2026-11-13, lead's ask):**
  - The pipeline is `eval-domains/scripts/midcentury_score.sh EXPORT.json`. It validates the export, builds the sets and scores them with hocrgen's `evaluate-references`.
  - The builder is `hocrgen.tools.midcentury_review` (hocrgen E2g1). It supersedes `ingest_page_reviews.py`, whose checks it carries over.
  - **Pages excluded:** rejected pages, and the two known-bad pages whatever their decision.
  - **References:** every reference is `within_line` and scored by `line_matched.v1`.
  - **Headline:** node printed/new_printed, ALL / excluding_pointed, on primary.v1.
  - **Intervals:** a unit-cluster bootstrap, 2,000 resamples, seed 0 (metric_spec §0).
  - **Runs:**
    - R8b (frozen, 8cb22dbe) paired against stock Tesseract, on pass 1 and on pass 2;
    - the blind-pass reference error;
    - Claude on pass 2 (primary) and on pass 1 (secondary), each in a `claude_only` and a `with_prefill_short` variant;
    - the error-coincidence test per reader batch.
  - **Report:** `report.md` and `report.json`, carrying the 0.04% overlap caveat and the "not an engine" label.
  - **Page predictions:** made in advance by `midcentury_predict.py` for all 298 pages.
  - **Zero-exposure rule.** Lead decided it 2026-11-13 and it is pre-registered here, before any review decision. Exposure itself was already known (r8b_overlap_exposure_v1.json).
    - **Primary score:** only pages with zero exposure. A page is exposed when any of its reference lines shares a word 6-gram, in logical order, with the train list of any compared model that has one: R8b main-fold or R7. Stock Tesseract has none. There is no threshold: one exposed line makes the page exposed.
    - **Same subset for everyone:** R8b, stock and the Claude yardstick are all scored on the zero-exposure subset, so the paired deltas stay paired.
    - **Secondary score:** the full set, with its exposure stated.
    - **Report:** n per stratum for both sets, to show whether the exclusion skews toward laws. On pre-fill text it does: plenary loses almost no pages.
    - **Computed on the reviewed reference text** by `midcentury_exposure.py`, which writes `items_zero_exposure.txt` and `exposure.json` into each set. Every exposed page is listed.
  - **Lead's decisions (2026-11-13, #197 approved):**
    - The blind pass keeps the app's per-page 24 h gate, with no extra hold.
    - A full run takes about 20 minutes. The rapidfuzz speed-up is deferred until after the first real scores, so the diagnostic counts don't move before then.
- **The page-level profile is not written yet.** It will strip bidi controls and collapse dot leaders to "...", on top of line_fold_v1's folds. Until then the pipeline scores with hocrgen's primary.v1 and consonantal.v1, and reports punct_folded.v1 as a diagnostic.
- **Lines are aligned independently of order.** Each reference line is matched to a model output line by a minimum-cost assignment on character edit distance. Unmatched reference lines are charged as deletions, and unmatched output lines as insertions.
  - So a margin note typed before its main line still matches the model's note wherever the model put it. A note the model merged into its main line costs about twice the note's length: the note's characters are inserted in the main line and missing from the note line.
- **Reading order is reported separately.** It is measured as the order agreement of matched lines, using the reviewed `reading_order_verified` pages, so it doesn't inflate CER.

## Publishing plenary references

- **The private-name gate applies.** Shay decided on 2026-11-13, relayed by lead: "Yes, filter them".
  - Any published eval or reference export that includes K1–12 plenary pages must first run `hocrgen.privacy.plenary_names` gate_lines (gate id `plenary_private_names_v1`, hocrgen#196) and carry its stamp.
  - The release export refuses ungated plenary rows.
- **Scoring and review are unchanged.** Gated-out lines stay in the internal scoring set.
- **Published scores give two figures:**
  - the internal figure, on all lines;
  - the published-reference figure, on gated lines only, with the number of lines dropped.
- **In effect since 2026-11-13.** hocrgen#196 merged as 045c03a.
