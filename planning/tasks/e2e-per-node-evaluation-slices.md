# E2e — Per-node evaluation slices, cluster intervals, page and line measures (decisions 0017, 0018)

Status: **`E2e1` implemented on the current ref (2026-11-11, #175); `E2e2` in review (#177); `E2e3` planned.** Parent milestone: E2, Baselines and evaluation utilities. The direction comes from heocr-engine decisions 0017 (character, word, line and page measures, with intervals) and 0018 (a tree of Hebrew document sets; new printed is the vertical). The usage reference is the "Per-node slices" section of [`docs/reference_evaluation.md`](../../docs/reference_evaluation.md).

## Direction

- **One score per selectable set.** `evaluate-references --eval-labels` places every scored item on a node of the 0018 tree. Each node has its own headline (`[node]["ALL"]["excluding_pointed"]`, `primary.v1`), and genre and font facets are reported under it.
- **Pointed text is scored apart.** Pointed text gets its own slice, scored on `consonantal.v1` only. It never enters a number of the vertical, `printed/new_printed`, except that slice.
- **No blended numbers.** No `eval_slices` number pools items of two nodes. A later aggregate must state the weight of every subset it averages (0018 §5).
- **Intervals and flags everywhere.** Every number carries its cluster count and a cluster-bootstrap interval. A number from fewer than 3 clusters gets no interval, and one from fewer than 8 is flagged.
- **Unchanged without the flags.** A run without the new flags is byte-identical to one before E2e.

## Notation

| Notation | Scope | State |
| --- | --- | --- |
| `E2e1` | `--eval-labels` (`hocrgen_eval_labels.v1`: node, facets, niqqud; fails closed on an unlabelled scored item). `eval_slices` per node, facet and niqqud key. Single-engine and paired cluster intervals with `too_few_clusters` / `low_cluster_count` flags. The page-CER distribution, and the order cost and missed-line rate as diagnostics. `--line-references` scoring of line_verify line sets, honouring `reference_views`. | completed (#175) |
| `E2e2` | Exposure exclusion: an optional per-label `exposed: [model ids]` plus `exposure_reason`, and `--model-id` / `--baseline-model-id`. An item exposed to a scored model enters no `eval_slices` number and is listed under `excluded_exposed`. A paired comparison drops items either side saw. Missing model ids fail closed. (The coordinator's follow-up "E2e.1".) | in review (#177) |
| `E2e3` | The pending 0017 measures (the coordinator's follow-up "E2e.3"): exact-line rate and line CER on line-aligned (physical-line) pages via `line_matched.v1` pairing; letter-level substitution, deletion and insertion rates (א–ת, diagnostic); and missed-region cost (diagnostic). | planned |

This notation record is itself the coordinator's follow-up "E2e.2". It is a planning change only.

## Open items

1. The weighted cross-node aggregates of 0018 §5 (all printed, then all Hebrew), once the maintainer sets the weights.
2. The fuller definition of the 0018 node placement, after the commissioned typography and genre research.

Each step needs its own PR and review by heocr-lead.
