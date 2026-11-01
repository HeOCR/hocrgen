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
