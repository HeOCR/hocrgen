#!/usr/bin/env bash
# Mid-century post-review pipeline (heocr-eval): heocr-review export -> references -> scores -> report.
# Run from tasks/:  bash eval-domains/scripts/midcentury_score.sh EXPORT.json [OUT_DIR] [--synthetic-fixture]
# Scoring is hocrgen's evaluate-references (hocrgen.tools.midcentury_review builds its inputs); predictions come from
# midcentury_predict.py (R8b frozen, stock) and the saved Claude readings (yardstick only).
# OUT_DIR defaults to intermediates/midcentury_score/run. Nothing here imports, deploys or writes to D1.
set -euo pipefail
EXPORT=$1; OUT=${2:-eval-domains/intermediates/midcentury_score/run}; FIXTURE=${3:-}
HOCRGEN=${HOCRGEN:-$HOME/clones/hocrgen}
MC=eval-domains/capture/midcentury
PRED=eval-domains/intermediates/midcentury_score/predictions
H() { uv run --quiet --project "$HOCRGEN" python -m "$@"; }
RES=2000; SEED=0
PROFILES=(--profile primary.v1 --profile consonantal.v1 --profile punct_folded.v1)

H hocrgen.tools.midcentury_review check "$EXPORT" --manifest $MC/batch_manifest_v1.json --blind $MC/blind_prefill_v1.json
mkdir -p "$OUT"
H hocrgen.tools.midcentury_review build "$EXPORT" --manifest $MC/batch_manifest_v1.json --blind $MC/blind_prefill_v1.json \
  --out "$OUT/sets" $FIXTURE
H hocrgen.tools.midcentury_review claude-predictions --readings $MC/ai_readings --manifest $MC/batch_manifest_v1.json \
  --manifest-v0 $MC/batch_manifest.json --out "$OUT/claude"
# Zero-exposure rule (lead, pre-registered 2026-11-13): the PRIMARY score covers pages with no reference line sharing a
# word 6-gram with the R8b main-fold or R7 train list; the full set is SECONDARY. Every model and the Claude yardstick
# use the same subset. midcentury_exposure.py writes items_zero_exposure.txt and exposure.json into each set.
python3 eval-domains/scripts/midcentury_exposure.py "$OUT/sets/pass1" "$OUT/sets/pass2"
for s in pass1 pass2; do
  H hocrgen.tools.midcentury_review subset "$OUT/sets/$s" --items "$OUT/claude/items.txt" --out "$OUT/sets/${s}_claude"
  H hocrgen.tools.midcentury_review subset "$OUT/sets/$s" --items "$OUT/sets/$s/items_zero_exposure.txt" --out "$OUT/sets/${s}_zero"
  comm -12 <(sort "$OUT/claude/items.txt") <(sort "$OUT/sets/$s/items_zero_exposure.txt") > "$OUT/sets/${s}_zero_claude.items"
  H hocrgen.tools.midcentury_review subset "$OUT/sets/$s" --items "$OUT/sets/${s}_zero_claude.items" --out "$OUT/sets/${s}_zero_claude"
done
H hocrgen.tools.midcentury_review coincidence "$EXPORT" --manifest $MC/batch_manifest_v1.json --blind $MC/blind_prefill_v1.json \
  --readings $MC/ai_readings --manifest-v0 $MC/batch_manifest.json --out "$OUT/coincidence.json" > /dev/null
python3 eval-domains/scripts/midcentury_predict.py --jobs 8

ev() {  # ev NAME SET PREDICTIONS [BASELINE]
  local set="$OUT/sets/$2" extra=()
  [ -n "${4:-}" ] && extra=(--baseline-predictions "$4")
  if [ ! -s "$set/items.txt" ]; then echo "skip $1: $2 has no items"; return; fi
  H hocrgen evaluate-references --predictions "$3" --reference-manifest "$set/reference_manifest.json" \
    --asset-index "$set/asset_index.json" --eval-labels "$set/eval_labels.json" --bootstrap-clusters "$set/clusters.json" \
    --bootstrap-resamples $RES --bootstrap-seed $SEED "${PROFILES[@]}" ${extra[@]+"${extra[@]}"} --output "$OUT/eval_$1.json" > /dev/null
  python3 -c "import json,sys; r=json.load(open(sys.argv[1])); sys.exit(r.get('status') == 'error' and f\"{sys.argv[2]}: {r.get('error')}\")" \
    "$OUT/eval_$1.json" "$1"
  echo "scored $1"
}
rm -f "$OUT"/eval_*.json
pids=()   # the runs are independent: score them in parallel, then fail if any failed
# primary (zero-exposure subset), then secondary (full set)
ev primary_r8b_pass1 pass1_zero $PRED/r8b $PRED/stock & pids+=($!)
ev primary_r8b_pass2 pass2_zero $PRED/r8b $PRED/stock & pids+=($!)
ev primary_claude_pass2 pass2_zero_claude "$OUT/claude/predictions" & pids+=($!)
ev primary_claude_pass1 pass1_zero_claude "$OUT/claude/predictions" & pids+=($!)
ev secondary_r8b_pass1 pass1 $PRED/r8b $PRED/stock & pids+=($!)
ev secondary_r8b_pass2 pass2 $PRED/r8b $PRED/stock & pids+=($!)
ev secondary_claude_pass2 pass2_claude "$OUT/claude/predictions" & pids+=($!)
ev secondary_claude_pass1 pass1_claude "$OUT/claude/predictions" & pids+=($!)
ev reference_error pass2 "$OUT/sets/pass1_on_pass2" & pids+=($!)
for p in "${pids[@]}"; do wait "$p"; done
python3 eval-domains/scripts/midcentury_report.py "$OUT"
