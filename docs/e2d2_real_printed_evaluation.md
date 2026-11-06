# E2d2: first evaluation on real printed Hebrew scans

Date: 2026-11-07. Plan: [`planning/tasks/e2d-real-scan-evaluation.md`](../planning/tasks/e2d-real-scan-evaluation.md). This is the printed modality track (E2d1). It is reported **beside** the synthetic scored set and does not replace it: the synthetic headline, `benchmark_v1` and every synthetic report are unchanged.

The numbers below are aggregates. No page text appears here. The Wikisource references and predictions stay operator-only. The tender set is private, so only its aggregate metrics are given.

## Headline

`primary.v1` CER on the 35 adjudicated quality-4 pages, with a 95% item-bootstrap interval, next to the same engine on synthetic gold:

| Engine | Real printed (35 pages) | Synthetic seed-101 (S10c) | Synthetic held-out s6101 | Synthetic printed templates (seed-101 / held-out) |
| --- | ---: | ---: | ---: | ---: |
| Tesseract 5.5.3 `heb`, psm 3 | **0.223** [0.163, 0.294] | 0.338 | 0.353 | 0.116 / 0.120 |
| R3d + R4d + A1 | **0.890** [0.854, 0.934] | 0.019 | 0.009 | — |
| R3g + R4d + A1 | **0.885** [0.847, 0.930] | 0.023 | 0.013 | — |
| R3h + R4d + A1 (the release pipeline) | **0.887** [0.849, 0.931] | 0.020 | 0.010 | 0.027 / 0.010 |
| R3h + blla (diagnostic) | 0.586 [0.508, 0.654] | 0.168 | 0.238 | 0.184 / 0.262 |

- **HeOCR's own pipelines do not transfer to real printed books.** R3d, R3g and R3h with R4d + A1 score about 0.01–0.02 CER on synthetic gold and about 0.89 here. On every one of the 35 pages they are worse than Tesseract (ΔCER +0.66, interval [+0.60, +0.73]).
- **The failure is mostly segmentation.**
  - R4d splits real pages into fragments. It finds a median of 157 lines per page (up to 205), where Tesseract finds a median of 24 text lines; R4d finds more lines on 34 of the 35 pages.
  - Upscaling a page to 1440 px did not change this.
  - With Kraken's general-purpose blla segmenter, the same R3h recognizer drops to 0.586 (ΔCER −0.30 [−0.38, −0.23], 33 of 35 pages better). The recognizer reads real print in part, but it is still far behind Tesseract.
- **The three recognizers cannot be told apart here.** R3h − R3d is −0.003 [−0.009, +0.002]; R3h − R3g is +0.002 [−0.002, +0.005].
- **Tesseract is the strongest engine on real print.** It scores 0.223, against 0.116–0.120 on the synthetic printed templates.

## The scored set

| | |
| --- | --- |
| Source | Hebrew Wikisource ProofreadPage (`wikisource_he_proofread`), F8b–F8b6 gates, pinned revisions, 960 px Commons renders |
| Scored pages | 35 quality-4 pages in 14 Indexes: 31 full pages, and 4 partial pages scored on their decision-12 crop |
| Reference characters | 42,831 (`primary.v1`) |
| Attestation | Each page has a proofreader and a different validator, both named humans from the page history, and its text is unchanged since validation (maintainer decision 2). Each page's adjudication record names them; no agent attests. |
| Reference manifest | `e2d2_wikisource_printed_v1`, `benchmark_id: e2d_real_printed`, `modality: printed`, `visibility: hidden_reference`; manifest sha256 `395b2983…`, child references `a2e96533…` |
| Diagnostic stratum | 141 quality-3 pages (single reviewer), up to 3 per Index, in 58 Indexes; unreviewed diagnostics only |

### Release splits: these pages are not held out

`F8g` ships the Wikisource pages in `profile_open_v1` and assigns each whole Index group to one split. The split of each page comes from the tranche `build-release --real-tranche-root` dry run on this branch, and is identical to the `F8g` run. It is recorded per item (`release_split`) and as `benchmark_split` on the adjudicated manifest items.

| Release split | Scored pages | Indexes | Tesseract | R3d | R3g | R3h (R4d + A1) | R3h + blla |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `train` | 25 | 10 | 0.191 | 0.855 | 0.848 | 0.851 | 0.568 |
| `validation` | 5 | 3 | 0.530 | 0.983 | 0.995 | 0.994 | 0.721 |
| `test` | 4 | 1 | 0.181 | 1.190 | 1.198 | 1.184 | 0.598 |
| `not_in_release` (crop dropped by the normalize height threshold) | 1 | 1 | 0.060 | 1.293 | 1.060 | 1.207 | 0.897 |
| `validation` + `test` | 9 | 4 | 0.391 | 1.065 | 1.076 | 1.069 | 0.672 |

**25 of the 35 pages ship as release training data.**
- The engines scored here never saw them: R3d, R3g and R3h were trained on synthetic text only, and the leakage check below finds no overlap with that text.
- These numbers are therefore an evaluation of the current engines. They are not held-out evaluation for any model trained on the release.
- A future recognizer trained on `profile_open_v1` must be scored on the `validation` + `test` pages only: 9 pages in 4 Indexes, too few for a headline.
- Of the quality-3 pages: 117 are in `train`, 11 in `validation`, 12 in `test`, and 1 is not in the release.

## Leakage

`hocrgen.tools.eval_text_leakage` runs the E2d1 policy over all 176 texts:
- a page that shares any word 8-gram with a corpus is excluded;
- a page with more than 20% of its word 3-grams shared is flagged.

| Corpus | Words | Pages excluded / flagged |
| --- | ---: | ---: |
| hocrsyngen `origin/main` packaged texts: `hebrew_lines*` (S10b), `hebrew_mixed_lines_*` (S13a), `hebrew_typographic_lines_*` (S13b), `hebrew_lines.txt` | 108,602 | 0 / 0 |
| R3d training corpus (`r3d_train_corpus.txt`) | 75,832 | 0 / 0 |
| R3e / R3g / R3h training corpus (`r3e_train_corpus.txt`, sha256 `7c2a62b8…`) | 99,511 | 0 / 0 |
| Project Ben-Yehuda: the 83 texts held locally from the F8f pilot (not a training corpus) | 107,311 | 0 / 0 |

- **Training corpora.** No page shares an 8-gram with them, and the largest 3-gram share against them is 0.9%. Nothing was excluded.
- **Project Ben-Yehuda (S15a).** No PBY training corpus exists yet: S15b has not started, and `config/synthetic_training_works.yaml` lists no works.
  - Two quality-3 works in the pool are in the PBY catalogue: *Bostenai* (Lehmann, Fuenn) and *Sefer ha-Mevakesh* (Falaquera).
  - No quality-4 work is.
  - When S15b builds a corpus, these two works must stay out of it, or this check and `F8g`'s `synthetic_training_overlap` will remove those pages.

## Per Index (scored pages, `primary.v1` CER)

| Index | Pages | Ref. chars | Tesseract | R3d | R3g | R3h | R3h + blla |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Aaron Hyman, *Toldoth Tannaim veAmoraim* I (1910) | 6 | 14,932 | 0.156 | 0.882 | 0.876 | 0.880 | 0.656 |
| Hebrewbooks 19784 | 5 | 6,344 | 0.207 | 0.765 | 0.752 | 0.749 | 0.666 |
| *Masa ba-Arav* | 4 | 4,329 | 0.079 | 0.865 | 0.865 | 0.869 | 0.180 |
| *Dorot ha-Rishonim* I | 4 | 2,728 | 0.181 | 1.190 | 1.198 | 1.184 | 0.598 |
| *Hut ha-Meshulash* | 3 | 4,516 | 0.459 | 0.940 | 0.942 | 0.948 | 0.702 |
| *Agadat ha-Melekh Artush* | 2 | 2,252 | 0.083 | 0.811 | 0.790 | 0.800 | 0.295 |
| Hebrewbooks 38168 | 2 | 256 | 0.262 | 0.871 | 0.754 | 0.777 | 0.500 |
| *The Selihot for the Entire Year* | 2 | 3,413 | 0.567 | 0.948 | 0.960 | 0.958 | 0.716 |
| S. D. Luzzatto, Commentary on Genesis | 2 | 501 | 0.377 | 1.407 | 1.443 | 1.449 | 0.850 |
| Seligman Baer, *Seder Avodat Yisrael* (1901) | 1 | 367 | 0.322 | 0.717 | 0.665 | 0.670 | 0.542 |
| *Sefer ha-Mispar* | 1 | 700 | 0.143 | 0.884 | 0.897 | 0.877 | 0.460 |
| *Vikuah al Hokhmat ha-Kabbalah* | 1 | 144 | 0.389 | 0.792 | 0.729 | 0.799 | 0.688 |
| Aaron Hyman, *Toldoth Tannaim veAmoraim* III (1910) | 1 | 2,139 | 0.125 | 0.812 | 0.803 | 0.811 | 0.516 |
| Korfu siddur (1885) | 1 | 210 | 0.286 | 0.524 | 0.505 | 0.486 | 0.495 |

Pages, Indexes and content are lumpy:
- The Hyman volume holds 35% of the reference characters.
- Several Indexes are a single short page.
- The full pages score 0.213 for Tesseract; the 4 crops score 0.383.
- The vocalised liturgy (Selihot) and the dense *Hut ha-Meshulash* are the hardest for every engine.

## Other profiles and views

| Engine | WER | `consonantal.v1` | `raw.v1` | `punct_folded.v1` (report-only) | Line breaks folded (operator diagnostic) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Tesseract | 0.459 | 0.202 | 0.234 | 0.200 | 0.201 |
| R3d + R4d + A1 | 1.051 | 0.886 | 0.895 | 0.887 | 0.827 |
| R3g + R4d + A1 | 1.057 | 0.881 | 0.890 | 0.879 | 0.823 |
| R3h + R4d + A1 | 1.066 | 0.884 | 0.893 | 0.881 | 0.826 |
| R3h + blla | 0.943 | 0.574 | 0.598 | 0.572 | 0.565 |

- **Line breaks.** Wikisource lines are rendered paragraphs, while engines emit printed lines. `primary.v1` therefore charges one edit for every printed line break inside a paragraph, about 0.02 CER for Tesseract. The "line breaks folded" column turns every line break into a space on both sides after `primary.v1`. It is computed by the operator script, not by a hocrgen profile.
- **Running heads and stamps.** References leave out running heads, page numbers, catchwords, signature marks and digitization stamps, following the F8b coverage convention. An engine that reads them is charged insertions.
- **`footnote_masked.v1` (issue #124).**
  - 2 scored pages declare `bracketed_index` footnote marks: 4 marks and 12 reference characters.
  - Masking lowers Tesseract on those pages from 0.114 to 0.107 (9 prediction characters removed), and R3h + blla from 0.223 to 0.217. The R4d pipelines barely move.
  - `primary.v1` is unchanged.

## Paired comparisons (`primary.v1`, 2,000 item resamples, seed 20261106)

| Candidate − baseline | Scored (35) ΔCER [95% CI] | Pages better / same / worse | Quality-3 diagnostic (141) ΔCER [95% CI] |
| --- | --- | --- | --- |
| R3h + R4d + A1 − Tesseract | +0.664 [+0.601, +0.725] | 0 / 0 / 35 | +0.510 [+0.467, +0.555] |
| R3d + R4d + A1 − Tesseract | +0.667 [+0.602, +0.728] | 0 / 0 / 35 | +0.511 [+0.468, +0.555] |
| R3g + R4d + A1 − Tesseract | +0.662 [+0.599, +0.723] | 0 / 0 / 35 | +0.507 [+0.464, +0.551] |
| R3h − R3d (both R4d + A1) | −0.003 [−0.009, +0.002] | 20 / 1 / 14 | −0.001 [−0.003, +0.001] |
| R3h − R3g (both R4d + A1) | +0.002 [−0.002, +0.005] | 13 / 1 / 21 | +0.003 [+0.002, +0.005] |
| R3g − R3d (both R4d + A1) | −0.005 [−0.010, +0.000] | 27 / 0 / 8 | −0.004 [−0.007, −0.002] |
| R3h + blla − R3h + R4d + A1 | −0.301 [−0.377, −0.234] | 33 / 1 / 1 | — (blla ran on the quality-4 pages only) |
| R3h + blla − Tesseract | +0.363 [+0.278, +0.434] | 2 / 0 / 33 | — |

**Quality-3 stratum** (141 single-reviewer pages; unreviewed diagnostics, not scored), `primary.v1` CER:

| Engine | CER |
| --- | --- |
| Tesseract | 0.395 [0.336, 0.451] |
| R3d + R4d + A1 | 0.906 [0.886, 0.923] |
| R3g + R4d + A1 | 0.902 [0.881, 0.920] |
| R3h + R4d + A1 | 0.905 [0.884, 0.923] |

The ranking is the same as on the scored pages.

## Private tender set (`heocr-restricted-eval`, `il-tender-pages-v0`)

**Aggregate metrics only.** The set is 5 first pages of government tenders, printed modern Hebrew at 160 DPI.
- **Reference status.** Its references are human, blank-start and self-attested, but not adjudicated. They are scored only as unreviewed diagnostics (`--diagnostic-only`), with the set's `[[...]]` editorial markers removed (3 markers).
- **Not held out.** Every page was already used in development, so these are not held-out results.

| Engine | `primary.v1` CER | WER |
| --- | ---: | ---: |
| Tesseract | 0.171 | 0.277 |
| R3d + R4d + A1 | 0.649 | 0.953 |
| R3g + R4d + A1 | 0.625 | 0.920 |
| R3h + R4d + A1 | 0.576 | 0.834 |
| R3h + blla | 0.255 | 0.620 |

Paired deltas, each with a 95% interval over 5 pages:

| Comparison | ΔCER [95% CI] |
| --- | --- |
| R3h − Tesseract | +0.404 [+0.303, +0.483] |
| R3h − R3d | −0.073 [−0.101, −0.049] |
| R3h − R3g | −0.049 [−0.063, −0.037] |
| R3h + blla − R3h + R4d + A1 | −0.321 [−0.431, −0.192] |

On modern print, too, the R4d pipelines are far behind Tesseract. Here R3h is clearly the best of the three recognizers.

## Method and run identities

- **Engines.** heocr-engine `55b0f7d` (inference code identical to `main`), Kraken 7.0.2, all on CPU. The settings are those of `tasks/r3h-crop-mix-75/score_r3h.sh`:
  - the `kraken-python` stage with R4d segmentation (sha256 `d32cd1a8…`) and A1 reading order (`69aa1946…`), `--reading-order-classes region`, base direction R;
  - recognizers R3d `374f9302…`, R3g `fe4f082d…` and R3h `f76affa8…`;
  - Tesseract 5.5.3 with `heb` (`11f9e43a…`), psm 3;
  - R3h + blla through the Kraken CLI, as in `score_r3h_blla.sh` (`77a638a8…`).
- **Inputs.** The pinned F8b6 960 px Commons render of each page, or its crop. The page id is the image's sha256, mapped through the reference set's `asset_index.json`.
- **Scoring.** hocrgen on this branch: `evaluate-references --modality printed` with profiles `primary.v1`, `raw.v1`, `consonantal.v1` and `punct_folded.v1`, plus `--bootstrap-resamples 2000 --bootstrap-seed 20261106` for comparisons. The run-record prediction-set sha256 prefixes are:

  | Engine | Prediction set |
  | --- | --- |
  | Tesseract | `ea158d7d…` |
  | R3d | `39ded083…` |
  | R3g | `a23f32ef…` |
  | R3h | `98819d49…` |
  | R3h + blla | `8de8ec99…` |
- **Synthetic numbers.** Read unchanged from the existing R3h, R3-training and R3h + blla reports (`tasks/r3h-crop-mix-75/reports`, `tasks/r3-training/reports`). Tesseract's synthetic number is the page-level psm 3 baseline.
- **Reproduction.** Operator scripts are in `tasks/real-source-mapping/intermediates/e2d2/scripts/`: `e2d2_build_snapshot.py` (cache-only), `e2d2_run_engines.py`, `e2d2_lanes.sh`, `e2d2_score.sh` and `e2d2_summarize.py`. The two hocrgen steps are:

  ```bash
  python -m hocrgen.tools.wikisource_eval_references SNAPSHOT refs --hold-out hold_out.json --split-manifest split_manifest.json
  python -m hocrgen.tools.eval_text_leakage --reference-manifest refs/reference_manifest.json \
    --texts refs/single_reviewer_texts.jsonl --corpus NAME=PATH ... --output leakage.json --hold-out-output hold_out.json
  ```

## Limits

- **Small and lumpy.** 35 pages from 14 Indexes, with one book holding a third of the characters. The intervals resample pages, not books, so they understate between-book variance.
- **Low resolution.** The images are 960 px Commons renders, smaller than the synthetic 1200 × 1600 pages. Tesseract copes with this; whether higher-resolution renders change the R4d result beyond the 1440 px spot check is untested.
- **Reference conventions cost every engine.** Paragraph lines, omitted running heads and stamps, and `[n]` footnote marks all add edits. The masked and line-break-folded numbers above bound these costs.
- **Wikisource attestation is two editors' proofreading.** No HeOCR reviewer checked these pages. The adjudicated status rests on maintainer decision 2.
- **Not a model ranking for release-trained models.** See [release splits](#release-splits-these-pages-are-not-held-out).
