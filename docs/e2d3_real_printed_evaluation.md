# E2d3: real printed evaluation, refreshed on tranche v2

> **All-pages results superseded by [E2d3b](./e2d3b_validated_revision_evaluation.md).** E2d3b adds 4 quality-4 pages, scored on their validating-revision text, for 39 pages; Tesseract is 0.216 there. It also records why the other 22 pages edited after validation stay out. [E2d3c](./e2d3b_validated_revision_evaluation.md#e2d3c-two-pool-corrections) then corrects that pool to 40 pages (Tesseract 0.231), and [E2d3d](./e2d3b_validated_revision_evaluation.md#e2d3d-the-hebrewbooks-19784-pages) to 38 pages (Tesseract 0.237). E2d3d also supersedes the validation + test results below: two of the five Hebrewbooks 19784 `test` pages are `text_not_on_page`, leaving 8 pages.

Date: 2026-11-07, on the F8g2 tranche v2 (#135: `size_aware_group_split.v1`, tranche `f8g2_real_tranche_v2`, converter `wikisource_plain_text.v3`). Plan: [`planning/tasks/e2d-real-scan-evaluation.md`](../planning/tasks/e2d-real-scan-evaluation.md).

This document **supersedes the release-split and interval sections of [E2d2](./e2d2_real_printed_evaluation.md)**. E2d2's method, engine settings, synthetic comparison and private tender results still hold; they are not repeated here.

This is still the printed modality track (E2d1). It is reported beside the synthetic scored set and does not replace it: the synthetic headline, `benchmark_v1` and every synthetic report are unchanged.

All numbers are aggregates. No page text appears here, and the references and predictions stay operator-only.

## What changed since E2d2

| | E2d2 (F8g splits) | E2d3 (F8g2 tranche v2) |
| --- | --- | --- |
| Quality-4 pages passing every page gate | 61 | 61 |
| Of those, adjudication-eligible (two named editors, text unchanged since validation) | 35 | 35: 31 full pages and 4 crops |
| Adjudicated pages in the release | 34: 25 `train` / 5 `validation` / 4 `test`, and 1 crop not in the release | 35: 25 `train` / 5 `validation` / 5 `test` |
| Pages valid for a model trained on the release (`validation` + `test`) | 9 pages, 4 Indexes | 10 pages, 5 Indexes, 7,811 reference characters |
| Quality-3 diagnostic stratum | 143 pages, 58 Indexes: 117 / 13 / 12, and 1 not in the release | the same 143 pages: 71 `train` / 52 `validation` / 20 `test` |
| Intervals | page (item) bootstrap | page bootstrap **and** book (Wikisource Index) cluster bootstrap |

- **The pool is the same 178 pages.** The same selection rule picks them on tranche v2:
  - every adjudication-eligible quality-4 page;
  - up to 3 quality-3 pages per Index (lowest sha256 of the slug);
  - the 2 quality-3 pages with `illegible_on_scan` spans.
- **Not all 61 quality-4 pages are eligible.** The other 26 quality-4 pages have text edited after validation (`text_changed_after_validation`), so they are not adjudication-eligible under maintainer decision 2.
- **Nothing was re-predicted.** Every scored image (render or crop) is byte-identical to E2d2's, and every cached prediction's input sha256 matches its image. So the prediction sets are E2d2's (`1a3154b9…`, `e0b531fc…`, `68c610f7…`, `1a06b244…`, `8de8ec99…`).
- **Text is unchanged except one quality-3 page.**
  - `wikisource_plain_text.v3` changed no adjudicated text; only the version string in each reference's `change_reason` changed.
  - One quality-3 text changed: *Sefer Arakhim* p. 11, a broken-link repair.
  - Pri Megadim p. 244, now `text_not_on_page`, was never in the sample.
- **`illegible_on_scan` spans are honoured, as before.** 5 spans on the 2 Korfu quality-3 pages; no scored page has one.
- **Leakage was re-run over all 178 texts.**
  - The corpora are the same as in E2d2: the hocrsyngen packaged texts, the R3d corpus, the R3e/R3g/R3h corpus, and the local 83-text PBY sample.
  - 0 pages are excluded and 0 flagged; the largest 3-gram share against the training corpora is 0.9%.
- **Manifest.** `e2d3_wikisource_printed_v2` (sha256 `6a7b2a91…`, children `b3b54734…`), `modality: printed`, `visibility: hidden_reference`. The validation + test subset is `e2d3_wikisource_printed_v2_valtest` (`3ccd95d2…`, children `c99b8c99…`).

## Headline

Each CER has two 95% percentile intervals from 2,000 resamples (seed 20261106):
- the **page** interval resamples pages, as in E2d2;
- the **book** interval resamples whole Wikisource Indexes (a cluster bootstrap) and keeps every page of a drawn Index.

### (a) All 35 scored pages: valid only for engines that never trained on the release

The set has 14 Indexes and 42,806 reference characters. Hyman's *Toldoth Tannaim veAmoraim* I holds 35% of the characters.

| Engine | `primary.v1` CER | Page interval | Book interval |
| --- | ---: | --- | --- |
| Tesseract 5.5.3 `heb`, psm 3 | **0.222** | [0.162, 0.293] | [0.148, 0.346] |
| R3d + R4d + A1 | **0.890** | [0.854, 0.934] | [0.830, 0.966] |
| R3g + R4d + A1 | **0.885** | [0.847, 0.931] | [0.821, 0.965] |
| R3h + R4d + A1 (the release pipeline) | **0.887** | [0.849, 0.932] | [0.822, 0.965] |
| R3h + blla (diagnostic) | 0.586 | [0.508, 0.653] | [0.435, 0.660] |

The point estimates are E2d2's to the last digit, since the texts and predictions are the same. The current engines never trained on any release page: they were trained on synthetic text only, and the leakage check finds no overlap.

### (b) Release validation + test pages only: the only valid set for a model trained on the release

The set has 10 pages in 5 Indexes and 7,811 reference characters.
- **`test`.** Hebrewbooks 19784, 5 pages. It holds 81% of the characters.
- **`validation`.** Hebrewbooks 38168 (2 pages), and one page each from Seligman Baer's *Seder Avodat Yisrael*, *Sefer ha-Mispar* and *Vikuah al Hokhmat ha-Kabbalah*.

| Engine | `primary.v1` CER | Page interval | Book interval |
| --- | ---: | --- | --- |
| Tesseract 5.5.3 `heb`, psm 3 | **0.212** | [0.124, 0.420] | [0.178, 0.325] |
| R3d + R4d + A1 | **0.777** | [0.715, 0.828] | [0.758, 0.873] |
| R3g + R4d + A1 | **0.761** | [0.695, 0.809] | [0.697, 0.855] |
| R3h + R4d + A1 | **0.759** | [0.697, 0.802] | [0.721, 0.852] |
| R3h + blla (diagnostic) | 0.637 | [0.521, 0.700] | [0.477, 0.664] |

- **The book intervals are not trustworthy here.** With 5 books, one of them holding 81% of the characters, the book bootstrap has few distinct resamples. It can come out narrower than the page interval (Tesseract above).
- **No interval here is a headline.** Any model trained on `profile_open_v1` must report this table, and both its intervals, beside the point estimate.

## What the refresh changes and what it does not

- **Tesseract is still the strongest engine on real print**, on both sets.
- **The R4d + A1 pipelines still do not transfer to real books.**
  - On all 35 pages, R3h − Tesseract is +0.665, with a page interval of [+0.601, +0.726] and a book interval of [+0.551, +0.756]. R3h is worse on all 35 pages.
  - The cause is still segmentation. R4d finds a median of 157 lines per page, where Tesseract finds 24.
- **The book intervals are wider on all 35 pages.** This is the expected effect of one dominant book. On the R3h − Tesseract delta, the book interval is about 1.6 times as wide as the page interval. No conclusion changes: every interval that excluded zero in E2d2 still excludes zero.
- **The recognizers can now be told apart on the validation + test pages.**
  - R3h − R3d is −0.018 (page [−0.040, −0.008], book [−0.054, −0.012]), and R3g − R3d is −0.017.
  - R3h − R3g is not distinguishable.
  - This rests mostly on one book (Hebrewbooks 19784). On all 35 pages the three recognizers are still indistinguishable.

## Paired comparisons (`primary.v1`, candidate − baseline)

| Candidate − baseline | All 35: ΔCER | Page interval | Book interval | Better / same / worse | Val + test (10): ΔCER | Page interval | Book interval | Better / same / worse |
| --- | ---: | --- | --- | --- | ---: | --- | --- | --- |
| R3h + R4d + A1 − Tesseract | +0.665 | [+0.601, +0.726] | [+0.551, +0.756] | 0 / 0 / 35 | +0.547 | [+0.335, +0.645] | [+0.396, +0.662] | 0 / 0 / 10 |
| R3d + R4d + A1 − Tesseract | +0.668 | [+0.603, +0.729] | [+0.555, +0.757] | 0 / 0 / 35 | +0.565 | [+0.371, +0.659] | [+0.440, +0.685] | 0 / 0 / 10 |
| R3g + R4d + A1 − Tesseract | +0.663 | [+0.601, +0.724] | [+0.551, +0.754] | 0 / 0 / 35 | +0.549 | [+0.344, +0.645] | [+0.372, +0.674] | 0 / 0 / 10 |
| R3h − R3d (both R4d + A1) | −0.003 | [−0.009, +0.002] | [−0.009, +0.003] | 20 / 1 / 14 | −0.018 | [−0.040, −0.008] | [−0.054, −0.012] | 8 / 1 / 1 |
| R3h − R3g (both R4d + A1) | +0.002 | [−0.002, +0.005] | [−0.002, +0.005] | 13 / 1 / 21 | −0.002 | [−0.013, +0.006] | [−0.011, +0.029] | 3 / 1 / 6 |
| R3g − R3d (both R4d + A1) | −0.005 | [−0.010, +0.000] | [−0.010, +0.001] | 27 / 0 / 8 | −0.017 | [−0.037, −0.006] | [−0.083, −0.005] | 9 / 0 / 1 |
| R3h + blla − R3h + R4d + A1 | −0.301 | [−0.378, −0.235] | [−0.472, −0.204] | 34 / 1 / 0 | −0.122 | [−0.237, −0.064] | [−0.365, −0.085] | 9 / 1 / 0 |
| R3h + blla − Tesseract | +0.363 | [+0.278, +0.435] | [+0.217, +0.451] | 2 / 0 / 33 | +0.425 | [+0.161, +0.541] | [+0.240, +0.454] | 1 / 0 / 9 |

## Per Index and per release split (all 35 scored pages, `primary.v1` CER)

| Index | Release split | Pages | Ref. chars | Tesseract | R3d | R3g | R3h | R3h + blla |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aaron Hyman, *Toldoth Tannaim veAmoraim* I (1910) | `train` | 6 | 14,932 | 0.156 | 0.882 | 0.876 | 0.880 | 0.656 |
| Hebrewbooks 19784 | `test` | 5 | 6,344 | 0.207 | 0.765 | 0.752 | 0.749 | 0.666 |
| *Masa ba-Arav* | `train` | 4 | 4,329 | 0.079 | 0.865 | 0.865 | 0.869 | 0.180 |
| *Dorot ha-Rishonim* I | `train` | 4 | 2,728 | 0.181 | 1.190 | 1.198 | 1.184 | 0.598 |
| *Hut ha-Meshulash* | `train` | 3 | 4,516 | 0.459 | 0.940 | 0.942 | 0.948 | 0.702 |
| *Agadat ha-Melekh Artush* | `train` | 2 | 2,252 | 0.083 | 0.811 | 0.790 | 0.800 | 0.295 |
| Hebrewbooks 38168 | `validation` | 2 | 256 | 0.262 | 0.871 | 0.754 | 0.777 | 0.500 |
| *The Selihot for the Entire Year* | `train` | 2 | 3,413 | 0.567 | 0.948 | 0.960 | 0.958 | 0.716 |
| S. D. Luzzatto, Commentary on Genesis | `train` | 2 | 501 | 0.377 | 1.407 | 1.443 | 1.449 | 0.850 |
| Seligman Baer, *Seder Avodat Yisrael* (1901) | `validation` | 1 | 367 | 0.322 | 0.717 | 0.665 | 0.670 | 0.542 |
| *Sefer ha-Mispar* | `validation` | 1 | 700 | 0.143 | 0.884 | 0.897 | 0.877 | 0.460 |
| *Vikuah al Hokhmat ha-Kabbalah* | `validation` | 1 | 144 | 0.389 | 0.792 | 0.729 | 0.799 | 0.688 |
| Aaron Hyman, *Toldoth Tannaim veAmoraim* III (1910) | `train` | 1 | 2,139 | 0.125 | 0.812 | 0.803 | 0.811 | 0.516 |
| Korfu siddur (1885) | `train` | 1 | 185 | 0.195 | 0.519 | 0.497 | 0.470 | 0.427 |

| Release split | Pages | Indexes | Tesseract | R3d | R3g | R3h | R3h + blla |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `train` | 25 | 9 | 0.224 | 0.915 | 0.913 | 0.915 | 0.574 |
| `validation` | 5 | 4 | 0.232 | 0.831 | 0.798 | 0.800 | 0.510 |
| `test` | 5 | 1 | 0.207 | 0.765 | 0.752 | 0.749 | 0.666 |

- **Splits move whole Indexes.** F8g2 moved Hebrewbooks 19784 from `train` to `test`, and Hebrewbooks 38168 and three single-page Indexes from `train` to `validation`. *Dorot ha-Rishonim* I, the Selihot, Luzzatto and the Korfu siddur moved into `train`. The *Artush* crop, dropped under F8g by the old height threshold, now ships in `train`.
- **The book cluster is the Index.** It is the release split group too. The two Hyman volumes are separate Indexes, so they are separate clusters.

## Footnote view and other profiles

- **`footnote_masked.v1`.** It still covers 1 scored page (2 marks, 6 reference characters), which is in `train`. There Tesseract goes from 0.089 to 0.085, and R3h + blla from 0.182 to 0.180; the R4d pipelines do not move. No validation or test page declares footnote marks.
- **Other profiles (all 35 pages).** These are unchanged from E2d2:

  | Engine | WER | `consonantal.v1` | `raw.v1` | `punct_folded.v1` | Line breaks folded (operator diagnostic) |
  | --- | ---: | ---: | ---: | ---: | ---: |
  | Tesseract | 0.459 | 0.202 | 0.233 | 0.199 | 0.200 |
  | R3d + R4d + A1 | 1.051 | 0.887 | 0.895 | 0.887 | 0.827 |
  | R3g + R4d + A1 | 1.057 | 0.882 | 0.890 | 0.880 | 0.824 |
  | R3h + R4d + A1 | 1.067 | 0.884 | 0.893 | 0.881 | 0.826 |
  | R3h + blla | 0.942 | 0.574 | 0.598 | 0.571 | 0.564 |

## Quality-3 diagnostic stratum (single reviewer; unreviewed, not scored)

| Engine | All 143 pages (58 Indexes): CER | Page interval | Book interval | Val + test 72 pages (32 Indexes): CER | Page interval | Book interval |
| --- | ---: | --- | --- | ---: | --- | --- |
| Tesseract | 0.397 | [0.336, 0.452] | [0.310, 0.474] | 0.372 | [0.311, 0.434] | [0.277, 0.469] |
| R3d + R4d + A1 | 0.906 | [0.886, 0.923] | [0.877, 0.930] | 0.883 | [0.862, 0.903] | [0.855, 0.909] |
| R3g + R4d + A1 | 0.902 | [0.880, 0.920] | [0.871, 0.927] | 0.878 | [0.855, 0.899] | [0.847, 0.906] |
| R3h + R4d + A1 | 0.905 | [0.884, 0.923] | [0.875, 0.929] | 0.882 | [0.859, 0.902] | [0.852, 0.909] |

- **The ranking matches the scored pages.**
  - R3h − Tesseract is +0.508 on all 143 pages: page interval [+0.466, +0.552], book interval [+0.448, +0.571].
  - On the 72 validation + test pages it is +0.510: page [+0.457, +0.563], book [+0.434, +0.587].
- **Recognizer deltas are small but distinguishable here.**
  - R3h − R3g is +0.003 to +0.004 on both sets, and both interval types exclude zero.
  - R3g − R3d is −0.004 to −0.005.

## Method

- **The new hocrgen option.** `evaluate-references --bootstrap-clusters FILE`, with `--bootstrap-resamples`, adds `paired_cluster_bootstrap` beside `paired_bootstrap` on every comparison delta.
  - Each delta records `unit: cluster`, the `cluster_key` and the `cluster_count`; the run record lists the settings and the cluster file's sha256.
  - `FILE` is a `hocrgen_bootstrap_clusters.v1` map from item id to cluster. `wikisource_eval_references` now writes one, `bootstrap_clusters.json`, with `cluster_key: wikisource_index`.
  - A compared item without a cluster fails the run.
  - Without the flag, reports are unchanged: the E2d2 item intervals reproduce exactly.
- **Single-set intervals.** The CER intervals in the headline tables use hocrgen's `paired_bootstrap_interval` with a zero baseline, which gives an interval of the candidate's own rate.
- **The validation + test runs.** They score a subset manifest: the same reference files, with the adjudicated items whose `benchmark_split` is `validation` or `test`. The quality-3 runs use the matching subset of single-reviewer texts.
- **Reproduction.** The operator scripts are in `tasks/real-source-mapping/intermediates/e2d3/scripts/`:
  - `e2d3_select_items.py`;
  - `e2d3_leakage.sh`;
  - `e2d3_subsets.py`;
  - `e2d3_score.sh`;
  - `e2d3_summarize.py`;
  - `e2d3_inventory.py`, the cache-only inventory re-render.

  The release split manifest comes from `build-release --profile profile_open_v1 --dry-run --real-tranche-root .../f8g2_real_tranche_v2` on this branch. Its splits are identical to F8g2's export run on all 2,002 items. The hocrgen steps are:

  ```bash
  python -m hocrgen.tools.wikisource_eval_references SNAPSHOT refs --items items.json --hold-out hold_out.json \
    --split-manifest split_manifest.json --reference-manifest-id e2d3_wikisource_printed_v2
  hocrgen evaluate-references --predictions P/r3h_r4d_a1 --baseline-predictions P/tesseract \
    --reference-manifest refs/reference_manifest.json --asset-index refs/asset_index.json --modality printed \
    --bootstrap-resamples 2000 --bootstrap-seed 20261106 --bootstrap-clusters refs/bootstrap_clusters.json
  ```

## Limits

These are E2d2's limits, plus three:

- **The validation + test set is too small for a headline.** It has 10 pages, 5 Indexes, and one book with 81% of the characters.
- **Few clusters make the book interval unreliable.** With 5 to 14 books, the book bootstrap is coarse; it also understates uncertainty for an Index that has only one page.
- **The pool did not grow.** F8g2 added no eligible quality-4 page. Growing the printed track needs new validated pages, or another human-attested printed source.
