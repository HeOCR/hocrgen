# Reference-aware evaluation

`hocrgen.reference_evaluation` scores explicit predictions against reviewed or adjudicated `benchmark_transcription_reference.v1` records. It does not acquire references or run an OCR engine. Existing `hocrgen.evaluation` and `evaluate-benchmark` retain their raw E2a behavior.

**Direction (2026-11-06).** Synthetic gold is the headline scored set for now. Evaluation is to move, over time, to real scans only, with separate printed and handwritten tracks. `E2d1`/`E2d2` add a printed modality track beside it ([modality tracks](#modality-tracks-and-real-printed-references-e2d1-e2d2)); the cutover is `E2d4`. See [`planning/tasks/e2d-real-scan-evaluation.md`](../planning/tasks/e2d-real-scan-evaluation.md).

```python
from hocrgen.manifests.models import BenchmarkTranscriptionReferenceRecord
from hocrgen.reference_evaluation import assemble_page_predictions, evaluate_reference_predictions

# Load and validate reference JSON under your own trusted benchmark workflow.
reference = BenchmarkTranscriptionReferenceRecord.model_validate(reference_json)
# Extract each engine output's raw `text` under an operator-selected page key.
predictions = assemble_page_predictions(page_texts, item_pages={reference.item_id: ["page-1"]})
report = evaluate_reference_predictions(
    [reference.item_id], predictions=predictions,
    references={reference.item_id: reference}, normalize_nfc=True,
)
```

The mapping is explicit and ordered; engine page IDs (including image hashes) are not benchmark item IDs. Preserve engine name/version, input identity and mapping alongside the report. After exclusions, all ordered lines across pages are joined with exactly one LF (`\n`), including empty or fully excluded lines. Page boundaries add no extra separator. Predictions must use the same boundary serialization for comparable scoring; preserve raw engine text separately. All text must already be in Unicode logical order. The evaluator never reverses bidi text.

Spans use half-open code-point offsets into each original line. The evaluator applies only supported, explicit span and policy decisions, rejecting ambiguous conflicts. Predictions must already cover the same included scope as the reference: reference offsets cannot identify corresponding prediction offsets. Thus a full-page prediction containing excluded text is not comparable without an independently justified scope alignment. Marginal text in an ordered line is considered ordered. The output is diagnostic and does not certify benchmark or leaderboard readiness.

Raw CER (Unicode code points) and WER (whitespace-separated words) use edit distance divided by reference length; aggregation sums numerators and denominators, and zero denominators yield null. Optional NFC scores are separate from raw scores; neither changes punctuation, numeral systems, case, niqqud, or logical order. Literal numeric sequence, selected Hebrew negation token, and word-multiset order comparisons flag differences only; they do not evaluate meaning, and the limited negation vocabulary and numeral pattern miss many expressions. Reference coverage and prediction coverage are reported independently. Missing inputs are not fabricated; unsupported or non-reviewed references fail closed. No model output or test fixture is treated as gold.

For private experiments with unreviewed plain-text references, call `score_unreviewed_text_pair(prediction=..., reference=..., normalize_nfc=True)`. The result is explicitly marked `unreviewed` and `benchmark_ready: false`. The caller must ensure both texts cover the same content and use logical order; no span exclusions are inferred. This local diagnostic path does not change reference status, release gates, or establish benchmark ground truth. Keep private texts and resulting reports within their authorized environment.

Per-item `reference_spans` reports counts and identifiers by status, including uncertain and damaged spans; report files may therefore need the same access controls as references. Page texts are joined with exactly one newline, preserving any existing leading or trailing whitespace in each engine output. A trailing newline or doubled inter-page newline contributes to raw CER. NFC changes Unicode composition only and does not strip whitespace. If a task defines a boundary or whitespace transformation, apply it explicitly to both prediction and reference before using the unreviewed-pair API, retain raw results separately, and record that policy; the reference-aware API does not silently apply one.

The negation-token diagnostic strips a fixed set of surrounding punctuation before token comparison; raw CER and WER retain it.

## Normalization profiles and strata (E2c3)

`evaluate_reference_profiles(item_ids, predictions=..., references=..., profiles=DEFAULT_PROFILE_IDS, item_strata=None, alignment_masked=False)` scores the same scoped inputs under each named profile in `NORMALIZATION_PROFILES`.

- The result lists every profile applied (`normalization_profiles`) and names `primary.v1` as `primary_profile`.
- `report_only_profiles` lists `punct_folded.v1`. Never quote it as a headline score.
- `raw.v1` and `nfc.v1` keep the raw and NFC-only results. `evaluate_reference_predictions` is unchanged.

`primary.v1` folds whitespace and drops empty lines. It therefore does not score page-joining or trailing-whitespace artefacts, while `raw.v1` still does. `consonantal.v1` removes niqqud and cantillation only after `primary.v1`. `primary.v1` keeps visible niqqud, following the ground-truth guidelines.

`item_strata` maps item ids to `language_script`, `modality`, `source_id`, `document_type` and `reference_origin`. Unspecified values default from the reference or to `unknown`. `strata[dimension][value][profile_id]` holds summed aggregates.

`alignment_masked=True` adds `diagnostics.alignment_masked` for engines that emit whole-page text, including excluded spans:

- prediction characters aligned by edit distance to excluded reference characters are removed;
- the masked text is scored under `primary.v1`;
- the output is labelled `diagnostic_only: true` and `primary_eligible: false`;
- the alignment is heuristic near span boundaries, so it never replaces scoped predictions and never feeds profile scores.

## Engine prediction runs (E2c4)

`hocrgen evaluate-references` (and `hocrgen.reference_runs.run_reference_evaluation`) scores a directory of heocr-engine page predictions offline.

**Predictions.** Each file must use `schema_version` `"1.0"` (the current Tesseract baseline) or `heocr_engine_prediction.v1`.
- Required fields: `page_id`, `input.sha256`, `engine.name`, `engine.version` and `text`.
- A `sha256:` page id must equal `input.sha256`.
- An optional `pipeline` list of stage objects is recorded and compared.
- Any other schema fails closed.

**Tracks (heocr-engine decision 0005).** Every prediction resolves to `track` `open` or `proprietary`.
- Legacy `"1.0"` files without `track` count as `open`. In v1, `track` is required.
- Any other value is rejected.
- Every `pipeline[]` stage must carry a valid `track`. An `open` stage must declare `requires_network: false`.
- A prediction whose top-level track is `open` but has a `proprietary` stage is rejected.
- A prediction directory must hold a single track. The track is recorded in the run record's prediction summary, at the top level of the report, on each scored report and on `unreviewed_diagnostics`.
- Baseline comparison refuses sets on different tracks. Proprietary results are therefore never mixed with, or compared against, open-track results.

**Mapping.** `hocrgen_reference_page_mapping.v1` maps each item id to its ordered engine page ids.
- When `--mapping` is omitted, the mapping is derived from asset sha256: hocrsyngen page `sha256` values for synthetic gold, plus any `--asset-index` entries.
- A page mapped twice is rejected.
- Items with only some of their pages predicted are listed rather than scored. Prediction pages that no mapping covers are listed too.
- Pages are joined with one LF, as in E2c2.

**Scored set.** These are the only references that produce scores:
- `synthetic_gold`: text from a hocrsyngen batch (`--synthetic-batch`). Item ids are `project_synthetic:<legacy id>`.
  - A batch that carries hocrgen-owned `provider_metadata` must pass `validate_hocrsyngen_batch`. If it fails, the run fails; there is no fallback.
  - Only a raw public `generation_manifest.v1` batch with no `provider_metadata` at all (F6f1) takes the evaluation-only path. That path recomputes and matches every page asset's sha256.
  - `identity.validation` records which path was used. Neither path admits a batch to release paths.
- `adjudicated_reference`: child references of a `benchmark_reference_manifest.v1` (`--reference-manifest`) whose items are `reviewed`/`adjudicated` with `adjudication_status: adjudicated`. Other items are listed in `excluded_references` with a reason.

**Unreviewed diagnostics.** `--unreviewed-texts` takes JSONL `{item_id, text, reference_origin, modality, ...}`, for example HASH HTR candidates. (Tender self-attested pages, issue #86, were closed on 2026-11-06 as unusable.)
- These are scored under the same profiles, but only under `unreviewed_diagnostics`, with `scored: false` and `benchmark_ready: false`.
- They cannot claim a scored origin.

**Diagnostic-only runs (E2c5).** Use `--diagnostic-only` to score unreviewed text with no scored set, for example a handful of real HASH pages against a synthetic-trained recognizer:

```bash
hocrgen evaluate-references --diagnostic-only --predictions PRED_DIR \
  --unreviewed-texts texts.jsonl --mapping mapping.json --output report.json
```

- It requires `--unreviewed-texts` with at least one text, and `--mapping` or `--asset-index`.
- It refuses `--synthetic-batch`, `--reference-manifest` and `--alignment-masked`, so a run is either diagnostic or scored, never both.
- The report has `scored: {}`. The report and the run record carry `diagnostic_only: true` and `benchmark_ready: false`.
- `--baseline-predictions` adds a `diagnostic_comparison` block, never `comparison`. It holds per-profile `unreviewed_deltas` over common items, the pipelines and the single-stage attribution, and it refuses cross-track sets.
- Without the flag, a run with no scored set still fails with "a scored set is required".

**Comparison.** `--baseline-predictions` scores a second set (same track) against the same scored set.
- It reports baseline, candidate and delta CER/WER per profile and origin, re-aggregated over the items both sets evaluated. Items only one set scored are listed. Omitting a hard item therefore cannot look like an improvement.
- `single_stage_attribution` names a stage only when each set used one ordered pipeline and the two differ by exactly one stage insertion, removal or replacement. Reorderings and multi-stage changes give `null`, and the delta is then set-level.

**Run record.** `hocrgen_reference_evaluation_run.v1` lists:
- prediction file names, sha256 values and the set hash;
- engines and pipelines;
- the mapping hash and source;
- reference identities (`reference_manifest_id`; for synthetic gold, `synthetic_gold:<manifest sha256 prefix>`). For adjudicated references these include each child transcription's actual sha256 and a combined hash. A declared `transcription_reference.sha256` must match, and the whole manifest is validated, including duplicate item and reference ids;
- excluded references and the unreviewed-text hash;
- profiles, the primary profile and the hocrgen version.

The record contains file names only, never local paths.

**Paired edit accounting (E2c6).** Each profile's common-item comparison also
reports baseline and candidate edit totals, shared reference units, counts of
items improved, unchanged, and worsened, and the sums of item-level net edits
removed or introduced. These are differences in edit distance per item; they do
not identify individual corrected or introduced errors, which would require a
separate alignment policy. Empty common sets have zero counts and null rates.
The headline remains `primary.v1`; punctuation-folded scores are secondary.
These fields also appear in diagnostic-only comparisons without changing their
unreviewed status or permitting cross-track comparisons.

**Per-cell reference view (E2c7).** hocrsyngen ledger gold joins each row's cells with ` | `, which is not drawn on
the page. An engine that emits one line per cell therefore pays at least 3 character edits per cell boundary
against `logical_order`, however well it reads the cells (issue #98). The per-cell view adds a second reference
text for those pages. Nothing existing changes.

- **Source.** The batch's `line_annotations.json` (`hocrsyngen_line_annotations.v1`). Each page's segments are
  rebuilt in `line_index` order. A segment with `logical_join: "cell"` starts a new line, `"space"` still joins with
  one space, and lines with `logical_line_index: null` are skipped. The view is driven by `logical_join` only, so a
  literal `|` inside a segment's text stays in the reference and is still scored.
- **When it appears.** Only for `--synthetic-batch` runs whose batch has the sidecar and at least one item with a
  cell join. Otherwise there is no `reference_views` key anywhere in the report (nor `run_record.reference_views`
  or `comparison.reference_view_deltas`), rather than an empty view with null rates, and nothing is guessed. A sidecar that is present must name this
  manifest's sha256, annotate every item on exactly one page, and rebuild every item's `logical_order` exactly with
  the hocrsyngen separators; otherwise the run fails closed.
- **Scope.** Items with at least one cell join (every ledger page). They are scored twice under the requested
  profiles: `reference_views.synthetic_gold."per_cell.v1".views.logical_order` (the same per-item results as
  `scored`) and `views."per_cell.v1"`, each a full profile report with strata, so `document_type` breaks out ledger.
- **Comparison.** With `--baseline-predictions`, `comparison.reference_view_deltas` holds the same paired edit
  accounting for both views over common items.
- **Run record.** `run_record.reference_views` lists the view id, origin, item count and the sidecar's schema and
  sha256.
- **Unchanged.** `scored`, every profile including headline `primary.v1`, `comparison.deltas` and every existing
  run-record field are byte-identical with and without the sidecar. The view is a reporting aid for line-per-cell
  engines; it is not a new headline and does not change scored eligibility.

On the mixed-script recipe's 25 ledger pages, R3d on gold baselines scores 3,112 `primary.v1` edits against
`logical_order` and 130 against the per-cell view (12,038 and 10,038 reference characters).

For a frozen, rights-clean mixed-script example, see the [synthetic evaluation recipe](evaluation-fixtures/bidi-synthetic-recipe.md).

## Modality tracks and real printed references (E2d1, E2d2)

`--modality printed|handwritten` (with `--reference-manifest`; refused with `--diagnostic-only`) makes a run one modality track. The modality track is distinct from the open/proprietary prediction `track`; both are reported.

- **Input.** `benchmark_reference_manifest.v1` items may declare `modality` (`printed` or `handwritten`) and `reference_normalization` (`footnote_marker_style`, `footnote_count`). Unset, both are omitted from serialized output, so existing manifests and release artifacts are unchanged.
- **Scope.** Only adjudicated items of the run's modality are scored. Others are listed in `excluded_references` with a reason; a track with no scored item fails closed.
- **Report.** `modality` at the top level, on `scored.adjudicated_reference`, in `strata.modality` and in the run record (`modality`, `modality_scope`). `scored.synthetic_gold` is identical with and without the flag; a run without it is byte-identical to one before E2d.

**Footnote view (`footnote_masked.v1`, issue #124).** Adjudicated items whose manifest entry declares `footnote_marker_style: bracketed_index` (Hebrew Wikisource writes every printed mark as `[n]`) are also scored under `reference_views.adjudicated_reference."footnote_masked.v1"`:

- `views.as_is`: the same per-item results as `scored`;
- `views."footnote_masked.v1"`: the reference with its `[n]` marks removed, and the prediction with the characters a Levenshtein alignment against the unmasked reference places on those marks removed (the E2c3 alignment rule);
- `masking`: mark, masked-reference-character and removed-prediction-character counts per item, and skipped items (alignments above 25 million cells).

The view is heuristic near the marks, appears only when a scored item declares the fact, and never changes `scored` or `primary.v1`. `comparison.reference_view_deltas` covers it.

**Intervals.** `--bootstrap-resamples N` (with `--baseline-predictions`; `--bootstrap-seed`, default 0) adds `paired_bootstrap` to every comparison delta: the 95% percentile interval of ΔCER and ΔWER over common items resampled with replacement, re-aggregated as sums. The run record lists the settings. The default, 0, adds nothing.

**Book-level intervals (`E2d3`).** `--bootstrap-clusters FILE` (with `--bootstrap-resamples`) also adds `paired_cluster_bootstrap` to every comparison delta.
- The method resamples whole clusters with replacement, and every item of a drawn cluster enters the resample.
- `FILE` is `{"schema_version": "hocrgen_bootstrap_clusters.v1", "cluster_key": ..., "clusters": {item_id: cluster_id}}`.
- Each delta records `cluster_key` and `cluster_count`; the run record lists the settings and the file's sha256.
- A compared item without a cluster fails the run.
- Use it when items are not independent, for example several pages of one book. With few clusters the interval is coarse.

**Real printed references.** `python -m hocrgen.tools.wikisource_eval_references SNAPSHOT OUT` (operator-only) writes, from a pinned Wikisource snapshot:

- adjudicated `benchmark_transcription_reference.v1` records for quality-4 pages, each with a `wikisource_adjudication_record.v1` that names the two Wikisource editors as the attesting humans (maintainer decision 2; no agent attests);
- a manifest with `modality: printed`;
- quality-3 pages as `--unreviewed-texts` (`reference_origin: wikisource_single_reviewer`);
- an `--asset-index` that maps each item to its page image, or to its decision-12 crop;
- `bootstrap_clusters.json`, which maps each item to its Wikisource Index (`cluster_key: wikisource_index`), for `--bootstrap-clusters`.

**Validating-revision text (`E2d3b`).** `--validated-revisions DIR --validated-text-checks FILE` admits quality-4 pages whose text changed after validation, scored on their text as of the validating revision.
- `DIR` comes from `python -m hocrgen.tools.wikisource_validated_revisions SNAPSHOT DIR --raw-cache CACHE --cache-only`. It pins that revision's wikitext and checks it against the inventory's checksum.
- `FILE` is `docs/wikisource_validated_text_checks.json`. Only a page whose check found the validated text agrees with the scan is used.
- Such an item records `reference_text_revision: validating` and `diff_vs_latest`. Every other adjudicated item records `reference_text_revision: latest`.
- A validated text that differs from the latest text only in line or paragraph whitespace is used whatever its check's verdict (`E2d3c`): a paragraph break is layout, not text. The item records `diff_vs_latest.layout_only` and `validated_text_accepted_by`.

The text is the post-F8b7 pair text. F8b7 `illegible_on_scan` spans are honoured: an adjudicated reference carries them as `illegible` / `exclude_primary` spans, which `reference_text` excludes, and a single-reviewer text has them removed. `--items` limits the conversion to listed pages, and `--split-manifest` records each page's release split (`benchmark_split` on adjudicated items).

`python -m hocrgen.tools.eval_text_leakage` checks reference texts against training corpora (word 8-gram exclusion, 3-gram share flag above 20%) and writes the `--hold-out` list. The first run is in [`e2d2_real_printed_evaluation.md`](./e2d2_real_printed_evaluation.md).
