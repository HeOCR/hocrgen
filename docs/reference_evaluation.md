# Reference-aware evaluation

`hocrgen.reference_evaluation` scores explicit predictions against reviewed or adjudicated `benchmark_transcription_reference.v1` records. It does not acquire references or run an OCR engine. Existing `hocrgen.evaluation` and `evaluate-benchmark` retain their raw E2a behavior.

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
