# E2c — Reference-aware evaluation expansion

Status: E2c1–E2c7 implemented on the current ref. Parent milestone: E2, Baselines and evaluation utilities. This is independent of F6 public-beta readiness and does not create reference evidence.

- **E2c1**: this planning contract.
- **E2c2**: deterministic reference-aware scoring and diagnostics, building on E2a's existing API without changing its results.
- **E2c3**: versioned normalization profiles applied to both sides and recorded in results, per-stratum aggregates, and a labelled `alignment_masked` diagnostic for unscoped full-page predictions.
- **E2c4**: an `evaluate-references` CLI over `heocr_engine_prediction.v1` / schema `"1.0"` prediction files with an explicit or sha256-derived page mapping, a run record, and per-stage ΔCER between two prediction sets. Synthetic gold is the scored set; HASH and tender pages are `unreviewed` diagnostics only.
- **E2c5**: an explicit `--diagnostic-only` mode for `evaluate-references` that scores `--unreviewed-texts` with no scored set, so real-page sanity checks need no placeholder scored set. See [E2c5 diagnostic-only runs](#e2c5-diagnostic-only-runs).
- **E2c6**: paired common-item error accounting. See [E2c6](#e2c6--paired-error-accounting-planned).
- **E2c7**: a per-cell reference view for synthetic gold, derived from hocrsyngen line annotations, reported beside the unchanged scores. See [E2c7](#e2c7--per-cell-reference-view).

## Contract and sequence

The evaluator accepts explicit predictions keyed by benchmark item id and validated `benchmark_transcription_reference.v1` records. A separately developed OCR engine remains outside hocrgen. An operator supplies an explicit mapping from each engine page prediction to a benchmark item and assembles pages in reference order; identifiers are not interchangeable. Prediction files contain raw Unicode text and engine identity/version; their provenance and page mapping must be retained by the operator. Never treat synthetic test strings as benchmark gold.

Reference pages and lines are ordered by their declared reading-order indexes. After applying exclusions to each line, serialize all lines across all ordered pages by joining them with exactly one LF (`\n`); page boundaries use the same single LF, with no additional separator. Empty or fully excluded lines remain empty entries and still contribute their separators. Predictions must use the same boundary serialization for comparable scoring; preserve raw engine output separately. Reject ambiguous indexes, missing lines, unsupported span decisions and overlapping spans with conflicting decisions. Span offsets are Python Unicode code-point offsets into the original line, half-open `[start, end)`, before any normalization. Resolve exclusions exactly at these offsets. Because a free-form prediction cannot be reliably masked from a reference offset, primary scoring requires predictions already scoped to the same included content; this assumption is explicit in the result and excluded content must not be guessed away. Missing, draft or unadjudicated references are not represented as gold. Logical order is an input requirement, not an automatic bidi reversal.

Report raw and optionally NFC-normalized metrics separately; never apply NFKC, digit conversion, punctuation rewriting or inferred niqqud. CER is code-point Levenshtein distance divided by reference length; WER uses whitespace-delimited tokens and word-level Levenshtein distance. Empty denominators yield null. Aggregate by summed edits and reference lengths, with coverage and missing/unexpected ids. Numeral-token and Hebrew negation-token differences are literal diagnostics, not claims of semantic correctness; token-order diagnostics expose reorderings without asserting visual reading order. No diagnostic changes primary scoring.

Implementation and tests must remain offline and deterministic, use only generic synthetic examples, and preserve E2a entrypoints and output behavior. Do not acquire or transfer data, create human labels, change release gates, or add engine runtime dependencies. Acceptance requires targeted adversarial cases plus all repository-required checks and a hostile self-review; report limitations explicitly.

## Delivered behavior

E2c2 supplies the reference-aware API, explicit page mapping, span reports, raw and optional NFC CER/WER, literal diagnostics, and a separately labeled unreviewed plain-text diagnostic API. It preserves the existing E2a API and release gates. Full-page predictions must be independently scoped to match exclusions; these results do not establish benchmark readiness.

## E2c3 profiles and strata

Each profile is a named, versioned transform chain, applied identically to the prediction and the scoped reference. Every result records which profiles were used.

| Profile | Role | Transforms |
| --- | --- | --- |
| `raw.v1` | baseline | none |
| `nfc.v1` | baseline | NFC |
| `primary.v1` | headline | NFC; strip LRM, RLM, ALM, embeddings, overrides and isolates; fold horizontal whitespace, trim lines, unify CR/CRLF, drop empty lines |
| `consonantal.v1` | reported alongside primary | `primary.v1`, then remove niqqud and cantillation |
| `punct_folded.v1` | report-only | `primary.v1`, then replace dashes with spaces and delete other punctuation |

A changed transform requires a new profile version. Existing versions are never edited. No profile converts numeral systems or reorders text, and `primary.v1` keeps visible niqqud.

Strata are reported along five dimensions:

- `language_script`, defaulting to the reference's `language_scripts`;
- `modality` (`printed`, `handwritten`, `synthetic` or `unknown`);
- `source_id`, defaulting to the reference;
- `document_type`;
- `reference_origin`.

Unknown dimensions or modalities fail closed.

`alignment_masked` handles unscoped full-page predictions. It aligns the prediction to the full reference by edit distance, then drops prediction characters aligned to excluded spans. The result is reported under `diagnostics`, with `diagnostic_only: true` and `primary_eligible: false`. It never changes profile or primary scores. Alignments larger than `max_cells` are skipped with a recorded reason.

## E2c5 diagnostic-only runs

**Why.** Before E2c5, `evaluate-references` produced unreviewed diagnostics only alongside a scored set. A real-page check (for example, 10 HASH pages against a synthetic-trained recognizer) therefore needed a placeholder: either a reference manifest whose items were all excluded, or an unrelated synthetic batch. Either one passed the scored-set check without scoring anything.

**Contract.** `--diagnostic-only` makes that intent explicit.
- **Inputs.** It requires `--unreviewed-texts` with at least one text, and `--mapping` or `--asset-index`.
- **Refusals.** It refuses `--synthetic-batch` and `--reference-manifest`, so a run is either diagnostic or scored, never both. It refuses `--alignment-masked`, which applies only to adjudicated references.
- **Report.** `scored` is `{}`. The report and the run record carry `diagnostic_only: true` and `benchmark_ready: false`. The run record's `scored_set_policy` says the run is diagnostic only.
- **Comparison.** `--baseline-predictions` gives a `diagnostic_comparison` block (`reference_status: unreviewed`, `scored: false`, `benchmark_ready: false`, `unreviewed_deltas`), never `comparison`. Deltas cover common items only, and the existing track rule still refuses cross-track comparison.
- **Without the flag.** A run with no scored set still fails with "a scored set is required". Scored runs keep their shape and record `diagnostic_only: false`.

No reference status, readiness gate or benchmark evidence changes. Unreviewed text stays outside every scored aggregate.


## E2c6 — Paired error accounting (planned)

Parent milestone E2. Extend the existing same-track, common-item comparison with
paired error accounting for each requested profile. Report baseline and candidate
character and word edit counts and shared reference denominators, plus the number
of items improved, unchanged, and worsened under each metric. Report net edits
removed and introduced as **net item-level changes**, not aligned individual
error corrections: edit distance alone cannot identify the same error across
predictions. Preserve primary.v1 as headline; optional punctuation-folded output
is secondary and never replaces the primary result. Keep diagnostic-only and
scored comparisons distinct, refuse cross-track comparisons, and retain common
item coverage and exclusions. Empty sets and zero denominators remain explicit.
Use offline adversarial fixtures and preserve existing output fields.

## E2c7 — Per-cell reference view

Parent milestone E2; source issue #98 (option 1, chosen by the maintainer). hocrsyngen ledger gold joins a row's
cells with ` | ` that is not on the page, so line-per-cell engines pay about 3 edits per cell boundary. Add a second
synthetic-gold reference view, `per_cell.v1`, in which every `logical_join: "cell"` segment of the batch's
`hocrsyngen_line_annotations.v1` sidecar starts a new line. Report the items with cell joins against both
`logical_order` and the view, under every requested profile and stratum, with paired deltas when a baseline is
given, and record the sidecar's sha256 in the run record.

Constraints: drive the view from `logical_join`, never from a blanket `|` replacement, so a literal `|` in page
text stays scored. If the batch has no sidecar the view is absent; a present sidecar that does not rebuild every
item's `logical_order` exactly, or does not match the manifest, fails closed. The change is additive: `scored`,
`primary.v1`, `comparison.deltas` and the existing run-record fields stay byte-identical, pinned by a test that
scores the same batch with and without the sidecar. The view is not a headline and does not change scored
eligibility or track isolation.
