# E2d — Real-scan evaluation with separate printed and handwritten tracks

Status: **`E2d1`, `E2d2`, `E2d3`, `E2d3b` and `E2d3c` implemented on the current ref (2026-11-07); `E2d4` planned.** Synthetic gold stays the headline scored set: no synthetic score, profile, view or report changed. Parent milestone: E2, Baselines and evaluation utilities. Decision record: [`planning/decisions/2026-11-06-real-scan-evaluation-direction.md`](../decisions/2026-11-06-real-scan-evaluation-direction.md). Results: [`docs/e2d3b_validated_revision_evaluation.md`](../../docs/e2d3b_validated_revision_evaluation.md) for all pages, and [`docs/e2d3_real_printed_evaluation.md`](../../docs/e2d3_real_printed_evaluation.md) for the release validation + test pages; E2d3 supersedes the release-split and interval sections of [`docs/e2d2_real_printed_evaluation.md`](../../docs/e2d2_real_printed_evaluation.md).

## Direction

- **Real scans only, eventually.** The eval set will be real scanned Hebrew text, both printed and handwritten. It will contain no synthetic text.
- **Separate printed and handwritten tracks.** Printed and handwritten Hebrew are scored and reported separately. They may also need separate pipelines (segmentation and recognition); whether they do is decided later, on evidence.
- **A transition, not a cutover.** Synthetic evaluation (E2c4–E2c7: synthetic gold as the scored set, `primary.v1` as the headline) stays in use until there is enough real reference data. Until `E2d4` changes it, every current synthetic score, profile, view and report stays as it is.

**Naming.** These are *modality* tracks. They are distinct from the existing open/proprietary `track` field in `evaluate-references` (heocr-engine decision 0005). The field is named `modality`, the name the E2c3 strata already use.

## Notation

| Notation | Scope | State |
| --- | --- | --- |
| `E2d1` | The modality-track contract and the training-text leakage policy (below). Small, so folded into the `E2d2` PR. The cutover criteria are not part of it; they stay open for `E2d4`. | completed |
| `E2d2` | The first real printed reference set (Hebrew Wikisource quality 4), engine runs on it, and a results doc beside the synthetic scored set. | completed |
| `E2d3` | Refresh the real printed evaluation on the F8g2 tranche v2 splits: rebuild the pool, re-score (cached predictions), report all pages and the release `validation` + `test` pages separately, and add a book-level (cluster) bootstrap. | completed |
| `E2d3b` | Score quality-4 pages edited after validation on their text as of the validating revision (team-lead decision 2026-11-07), after a visual check of the scan; pages where a later edit fixed a real transcription error are excluded (`validated_text_disagrees_with_scan`). | completed |
| `E2d3c` | Two corrections to the `E2d3b` pool (team-lead decisions 2026-11-07): a validated text that differs from the latest text only in line or paragraph whitespace is never disqualified (a general rule); Hebrewbooks 19784 p. 24 is `text_not_on_page`. The pool is re-scored. | completed |
| `E2d4` | Retire synthetic text from the scored eval set once both tracks meet cutover criteria the maintainer sets. | planned |

## E2d1 — Modality-track contract

- **Where the modality lives.** `benchmark_reference_manifest.v1` items take an optional `modality`: `printed` or `handwritten`. They also take an optional `reference_normalization` object, `{footnote_marker_style: "bracketed_index" | null, footnote_count}`. Both are omitted from serialized output while unset, so existing manifests and release artifacts are byte-identical (`benchmark_v1` included).
- **A run is one modality track.** `evaluate-references --modality printed|handwritten` needs `--reference-manifest` and refuses `--diagnostic-only`.
  - Only adjudicated items that declare that modality are scored.
  - Items of another modality, or with none, go to `excluded_references` with a reason.
  - A track with no scored item fails closed.
  - Printed and handwritten references are therefore never aggregated together.
- **Where it is reported.** The modality appears at the top level of the report, on `scored.adjudicated_reference`, in `strata.modality`, and in the run record as `modality` and `modality_scope`.
- **Kept apart from `track`.** `modality` describes the references and `track` describes the predictions. Both are reported, and neither implies the other.
- **Synthetic gold is unchanged.** `--modality` never touches `scored.synthetic_gold`: its stratum stays `modality: synthetic`. A synthetic-only run has no new keys; reports from this branch and from `main` are byte-identical (checked on the seed-101 and mixed-fixture R3h reports).
- **Reference views for real pages.**
  - Adjudicated items that declare `footnote_marker_style: bracketed_index` are also scored under `reference_views.adjudicated_reference."footnote_masked.v1"`, with views `as_is` and `footnote_masked.v1` (issue #124).
  - The view removes the reference's `[n]` marks, and the prediction characters that a Levenshtein alignment places on them. It reports the mask counts.
  - It is heuristic near the marks, so it is reported beside `primary.v1` and never replaces it.
  - `comparison.reference_view_deltas` covers it, as it covers E2c7.
- **Intervals.** `--bootstrap-resamples N --bootstrap-seed S`, with `--baseline-predictions`, adds `paired_bootstrap` intervals (95% percentile, items resampled with replacement and re-aggregated) to every comparison delta. The default, 0, adds nothing.
- **Leakage policy (`hocrgen.tools.eval_text_leakage`).**
  - A real reference page that shares any word 8-gram with a training text corpus is excluded from the scored set.
  - A page whose word 3-grams are more than 20% shared with the corpora is listed for review.
  - Tokens are consonantal words: NFC, with bidi controls, `[n]` marks, points, cantillation and punctuation removed.
  - This is the check that hocrsyngen's S15a plan assigns to hocrgen for a future Project Ben-Yehuda corpus.

## E2d2 — First real printed scored set

- **References** (`hocrgen.tools.wikisource_eval_references`, operator-only):
  - **Selection.** Every Hebrew Wikisource quality-4 page that passes every F8b–F8b6 gate: 35 pages in 14 Indexes. They are full pages, or decision-12 crops scored on the crop image.
  - **Format.** Each page becomes a `benchmark_transcription_reference.v1` with `review.status: adjudicated`, under decision 2 of [the F8 decisions](../decisions/2026-11-06-f8-real-source-decisions.md).
  - **Adjudication record.** Each page also gets a `wikisource_adjudication_record.v1`. It names the proofreader and the validator from the page history as the attesting humans; the validator's quality-4 edit is the adjudicating act. No agent attests (`agent_attestation: null`).
  - **Manifest.** `modality: printed`, `visibility: hidden_reference`, `benchmark_id: e2d_real_printed`. It is not `benchmark_v1`.
- **Quality-3 stratum.** A deterministic sample of quality-3 pages is written as `--unreviewed-texts` with `reference_origin: wikisource_single_reviewer`: up to 3 per admitted Index, plus the 2 pages with F8b7 `illegible_on_scan` spans (143 pages, 58 Indexes). Those pages are reported only as unreviewed diagnostics.
- **Post-F8b7 text.** The set is built from the F8g real-tranche snapshot after F8b7, so unprinted editors' footnotes are dropped and stand-ins are mapped. F8b7 `excluded_spans` are honoured: adjudicated references carry them as `illegible` / `exclude_primary` spans, which `primary.v1` excludes, and single-reviewer texts have them removed. The span boxes are listed with the item's image; the images themselves are not masked.
- **Leakage.**
  - **Corpora checked.** The 178 texts were checked against hocrsyngen's packaged S10b/S13a/S13b and `hebrew_lines` corpora (`origin/main`), and against the R3d and R3e/R3g/R3h training corpora.
  - **Result.** No page shares an 8-gram; the largest 3-gram share is 0.9%. Nothing is excluded.
  - **Project Ben-Yehuda.** No PBY corpus exists yet (S15b is not started). Two quality-3 works in the pool, *Bostenai* and *Sefer ha-Mevakesh*, are in the PBY catalogue. S15b must exclude them, or this check will remove those pages.
- **Release splits (F8g).** `F8g` ships these pages in `profile_open_v1` and splits whole Index groups. With `--split-manifest`, each item records its release split (`release_split`, and `benchmark_split` on adjudicated manifest items).
  - 25 of the 35 scored pages are in the release `train` split, 5 in `validation`, 4 in `test`, and 1 crop is not in the release.
  - The current engines never trained on them, but a page in `train` is never presented as held-out evaluation. A model trained on the release may be scored only on the `validation` + `test` pages.
- **Engines.** Same settings as `score_r3h.sh`:
  - Tesseract (`heb`, psm 3);
  - R3d, R3g and R3h with R4d + A1;
  - R3h + blla as a diagnostic.

  All runs were scored with `--modality printed`. The private tender set was scored as aggregate unreviewed diagnostics only.

## E2d3 — Refresh on the F8g2 tranche v2

- **Why.** F8g2 (#135) changed the release splits (`size_aware_group_split.v1`, tranche `f8g2_real_tranche_v2`) and the converter (`wikisource_plain_text.v3`), so E2d2's split table went stale.
- **Pool.** The same selection on tranche v2 gives the same 178 pages:
  - 35 adjudicated quality-4 pages (31 full, 4 crops; 14 Indexes). The other 26 of the 61 quality-4 pages that pass the page gates have text edited after validation, so they are not adjudication-eligible;
  - 143 quality-3 pages.

  No adjudicated text changed and every scored image is byte-identical, so the cached E2d2 predictions were reused and nothing was re-predicted. Leakage was re-run: nothing excluded or flagged.
- **Release splits.** 25 `train` / 5 `validation` / 5 `test`. The crop F8g dropped now ships.
- **Two reported sets.**
  - **All 35 pages** are valid only for engines that never trained on the release.
  - **The 10 `validation` + `test` pages** (5 Indexes) are the only valid set for a model trained on the release. One book holds 81% of their characters.
- **Book-level intervals.**
  - `evaluate-references --bootstrap-clusters` (`hocrgen_bootstrap_clusters.v1`) adds a paired cluster bootstrap beside the item bootstrap. Without the flag, reports are unchanged.
  - `wikisource_eval_references` writes `bootstrap_clusters.json`, which maps each item to its Wikisource Index: the book unit.
- **Inventory.** `docs/wikisource_index_inventory.md` is re-rendered from the cache with F8g2's Pri Megadim p. 244 check (`text_not_on_page`).

## E2d3b — Validating-revision text

- **Decision (team lead, 2026-11-07).** A quality-4 page whose text changed after validation is scored on its text **as of the validating revision**: the revision at which the second editor set quality 4, the text both named editors attested. Later edits are unvalidated and not used. If a later edit fixed a real transcription error, the page is flagged `validated_text_disagrees_with_scan` and excluded after a visual check (`checked_by: agent`); neither version is used.
- **Pinning.** `hocrgen.tools.wikisource_validated_revisions` pins each page's validating-revision wikitext from the inventory's API cache (revision id, SHA-256), and checks that it converts (`wikisource_plain_text.v3`) to the text checksum the inventory recorded for that revision.
- **Checks.** `docs/wikisource_validated_text_checks.json` (`wikisource_validated_text_checks.v1`) records one agent visual check per page.
- **Conversion.** `wikisource_eval_references --validated-revisions --validated-text-checks` converts the checked pages.
  - Stand-ins are re-applied; unprinted notes and excluded spans must be re-pinned by the check.
  - Each item records `reference_text_revision: validating` and `diff_vs_latest`.
  - An unchecked or stale page fails closed.
- **Outcome.** 4 of the 26 pages agree with the scan. The pool is 39 pages: 29 `train` / 5 `validation` / 5 `test`, so validation + test is unchanged. The other 22 pages had later edits that fixed OCR-type misreadings.
- **Finding.** Validation often left OCR errors in place. The 35 pages never edited after validation may hold some too, and a visual audit of them is suggested.

## E2d3c — Pool corrections

- **Whitespace is layout (team-lead decision, 2026-11-07).**
  - A validated text that differs from the latest text only in line or paragraph whitespace, or in the length of a whitespace run, is used whatever its check's verdict (`layout_only_difference`).
  - Words run together, a space inside a word, or any changed character still disqualify the page.
  - Each item records `diff_vs_latest.layout_only` and `validated_text_accepted_by`.
  - *Hut ha-Meshulash* p. 12 (`train`) joins the pool.
- **Hebrewbooks 19784 p. 24.**
  - It holds editors' text throughout: citations, an expansion of a printed abbreviation, quotation marks and vocalisation. So it is recorded page-level `text_not_on_page` (decision #130.1), not as one excluded span.
  - The committed tranche v3 still lists the page; the next tranche build drops it.
- **Outcome.** The pool is 40 pages: 30 `train` / 5 `validation` / 5 `test`. Tesseract scores 0.231 and R3h + R4d + A1 0.889 on all pages; validation + test is unchanged. Results are in the E2d3c section of [`docs/e2d3b_validated_revision_evaluation.md`](../../docs/e2d3b_validated_revision_evaluation.md#e2d3c-two-pool-corrections).
- **Finding.** A scored page of Hebrewbooks 19784 (p. 25, `test`) shows the same kind of editors' text. That book holds 81% of the validation + test characters. An audit of its references awaits maintainer approval.

## What it depends on

- Human-attested real references in `benchmark_transcription_reference.v1` form (F2), adjudicated before they are scored.
- **Handwritten:** human-attested HASH transcripts through `F7c`, and later `F7e` / `benchmark_v2`. New human transcription campaigns are allowed (maintainer decision 2026-11-06), so they are a valid way to produce these.
- **Printed:** Hebrew Wikisource quality-4 pages (`E2d2`). The quality-3 pages are a single-reviewer diagnostic stratum. Other candidates remain NLI items (`printed_modern`) and later F8 sources.
- The existing rules still hold: HTR or OCR output is never ground truth, and `benchmark_v1` membership stays frozen.

## Open questions, for `E2d4`

1. What counts as "enough real data" per track: page count, writer and source diversity, and confidence-interval width (page and book level). The printed set is 35 pages from 14 Indexes; 6 pages come from one book, and after F8g2 only 10 pages (5 Indexes, one with 81% of their characters) are outside the release `train` split.
2. How a page is assigned to a track (for example from `content_class`), and how mixed printed/handwritten pages are handled.
3. Whether synthetic results stay available as a labelled diagnostic after the cutover. They are never part of the scored eval set.
4. How the switch is versioned, so that results before and after it are never compared as if they were alike.
5. Whether the quality-3 single-reviewer stratum may ever count toward a scored track, for example after a second human review.

Each step needs its own PR and maintainer review.
