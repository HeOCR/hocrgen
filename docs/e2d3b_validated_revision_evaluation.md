# E2d3b: quality-4 pages scored on their validating-revision text

Date: 2026-11-07, on the F8g2 tranche v2. Plan: [`planning/tasks/e2d-real-scan-evaluation.md`](../planning/tasks/e2d-real-scan-evaluation.md).

This document **supersedes the all-pages results of [E2d3](./e2d3_real_printed_evaluation.md)**. E2d3's validation + test results are unchanged, because no new page falls in those splits. Everything else in E2d3 still holds: the method, the book (cluster) bootstrap, the release splits and the quality-3 stratum.

> **[E2d3c](#e2d3c-two-pool-corrections) corrects the pool to 40 pages** (one paragraph-break page admitted; Hebrewbooks 19784 p. 24 is `text_not_on_page`). Its numbers supersede the all-pages headline below; validation + test is unchanged.

All numbers are aggregates. No page text appears here. The references, the pinned validating-revision wikitext and the predictions stay operator-only.

## The rule

The team-lead decision of 2026-11-07 covers a Wikisource quality-4 page whose text changed after validation. Under maintainer decision 2, such a page is not adjudication-eligible as it stands.

- **Which text is used.** It is scored on the text **as of its validating revision**, the one at which the second editor set quality 4. That text is exactly what the two named editors attested. Later edits were never validated and are not used. The image is unchanged.
- **When a page is left out.** If a later edit fixed a real transcription error, the validated text disagrees with the page image. Such a page is flagged `validated_text_disagrees_with_scan` and left out after a visual check (`checked_by: agent`). Neither version is used.

## What was done

- **Pinning (`hocrgen.tools.wikisource_validated_revisions`, new).**
  - The tool covers the 26 tranche pages that pass every page gate and fail adjudication only as `text_changed_after_validation`.
  - For each, it reads the revision history from the inventory's API cache, with 0 requests (`--cache-only`).
  - It pins the validating revision's wikitext by revision id and SHA-256.
  - It checks that the wikitext converts (`wikisource_plain_text.v3`) to the text checksum the inventory recorded for that revision. All 26 match.
- **Visual check (`docs/wikisource_validated_text_checks.json`, new, `wikisource_validated_text_checks.v1`).**
  - Every word-level difference between the validated and the latest text was located on the pinned 960 px render, or its crop, using Tesseract word boxes. Each was read on an enlarged crop.
  - Each of the 26 pages has a recorded verdict, method and detail.
- **Conversion (`wikisource_eval_references --validated-revisions DIR --validated-text-checks FILE`).** A page with a `validated_text_matches_scan` check becomes an adjudicated reference from its validated text.
  - The F8b7 steps are re-applied. Stand-in mappings apply as they are.
  - Unprinted notes and excluded spans must be re-pinned to the validated text by the check; they are not reused from the latest text. None of the 4 pages used has either.
  - The crop is unchanged; none of the 4 pages is a crop.
  - The item and its adjudication record carry `reference_text_revision: validating`, the validating and latest revision ids, and `diff_vs_latest` (character edits, both lengths, and the number of later text-changing edits).
  - Every other adjudicated item records `reference_text_revision: latest`.
  - A page is left out when its check is missing or stale (`validated_text_not_checked`), when it disagrees with the scan, or when the pinned wikitext does not reproduce its checksum.

## Outcome: 4 of the 26 pages agree with the scan

| Verdict | Pages | What the later edits did |
| --- | ---: | --- |
| `validated_text_matches_scan` | 4 | Only encodings and normalizations, with the validated text matching the print. Two pages write gershayim/geresh differently; one page has the print's defective spelling (later made plene); one page has the print's letter-spaced words (later closed up). |
| `validated_text_disagrees_with_scan` | 22 | They fixed real misreadings in the validated text: OCR-type letter errors such as ג/נ, ב/כ, ס/ש, ם/ט and a Latin `n` for מ; words run together; misplaced commas and full stops; a dropped printed abbreviation; and one missing paragraph break. |

- **All 4 pages are in the release `train` split.** They come from Indexes already in the pool: *Masa ba-Arav* (2), Hyman I and *Dorot ha-Rishonim* I. The validation + test set is unchanged.
- **One verdict is strict.** On one page the only difference is a paragraph break that the page prints and the validated text runs on (1 edit under `primary.v1`). It is counted as disagreeing; a reviewer may overrule it.
- **The 22 pages were never scored.** Their predictions were run and stay in the operator folder, so a later decision can use them.

## Headline (`primary.v1` CER, 95% intervals, 2,000 resamples, seed 20261106)

The **page** interval resamples pages. The **book** interval resamples whole Wikisource Indexes.

| Engine | All 39 pages (14 books) | Page | Book | Val + test, 10 pages (5 books) | Page | Book |
| --- | ---: | --- | --- | ---: | --- | --- |
| Tesseract 5.5.3 `heb`, psm 3 | **0.216** | [0.163, 0.279] | [0.149, 0.329] | **0.212** | [0.124, 0.420] | [0.178, 0.325] |
| R3d + R4d + A1 | 0.887 | [0.855, 0.926] | [0.829, 0.952] | 0.777 | [0.715, 0.828] | [0.758, 0.873] |
| R3g + R4d + A1 | 0.881 | [0.849, 0.921] | [0.821, 0.952] | 0.761 | [0.695, 0.809] | [0.697, 0.855] |
| R3h + R4d + A1 | 0.884 | [0.851, 0.923] | [0.823, 0.954] | 0.759 | [0.697, 0.802] | [0.721, 0.852] |
| R3h + blla (diagnostic) | 0.570 | [0.496, 0.632] | [0.403, 0.658] | 0.637 | [0.521, 0.700] | [0.477, 0.664] |

- **The set.** All pages total 49,923 reference characters (42,806 before). Hyman I still holds 35% of the characters.
- **The 4 new pages.** On them Tesseract scores 0.179, R3h + R4d + A1 0.866 and R3h + blla 0.475; on the 35 latest-text pages the scores are 0.222, 0.887 and 0.586.
- **No conclusion changes.**
  - R3h − Tesseract on all 39 pages is +0.668: page interval [+0.614, +0.722], book interval [+0.558, +0.749]. R3h is worse on 39 of 39 pages.
  - R3h − R3d is −0.003: page [−0.008, +0.001], book [−0.008, +0.002].
  - R3g − R3d is −0.006. Its page interval [−0.010, −0.001] now excludes zero, but its book interval [−0.011, +0.000] does not.
  - R3h + blla − R3h + R4d + A1 is −0.314: page [−0.386, −0.253], book [−0.481, −0.204].
- **Segmentation is unchanged in kind.** R4d finds a median of 171 lines per page, where Tesseract finds 24. R4d finds more lines on 38 of the 39 pages.

## Findings for review

These fall outside this PR's scope. They are recorded here and not acted on.

1. **Quality-4 validation often left OCR errors.** In 22 of the 26 pages edited after validation, the validator had accepted text with misreadings that a later edit fixed. The 35 pages never edited after validation may carry the same kind of error, simply never fixed.
   - A count of one OCR signature over the 35 references finds it on 6 pages: a space before a comma or full stop that is attached to the next word.
   - Three *Masa ba-Arav* pages (pp. 18–20) hold 21–27 such errors each.
   - A visual audit of the 35 scored pages, like the one done here, would bound the reference error. Until then, part of every engine's CER on those pages is reference error.
2. **One latest pair text holds editors' text the page does not print.** On Hebrewbooks 19784 p. 24 (a crop), both versions carry an editors' Rashi citation that the crop does not show. This is a `text_not_on_page` case for the F8 page checks. The page is not scored here. E2d3c records it, and finds more editors' text on the page.
3. **Some later edits move the text away from the print.** They modernize spelling to plene forms, expand abbreviations, and close up letter-spaced words. The validated text was faithful at those points. A latest-text policy alone would score some pages against non-printed text.

## Reproduction

The operator scripts are in `tasks/real-source-mapping/intermediates/e2d3b/scripts/`:
- `e2d3b_lanes.sh` (engine runs on the 26 images);
- `e2d3b_diffs.py` and `e2d3b_sheets.py` (review aids);
- `e2d3b_leakage.sh`;
- `e2d3b_subsets.py`;
- `e2d3b_score.sh`;
- `e2d3b_summarize.py`.

The hocrgen steps are:

```bash
python -m hocrgen.tools.wikisource_validated_revisions SNAPSHOT validated --raw-cache INVENTORY/raw --cache-only
python -m hocrgen.tools.wikisource_eval_references SNAPSHOT refs --items items.json --hold-out hold_out.json \
  --split-manifest split_manifest.json --reference-manifest-id e2d3b_wikisource_printed_v3 \
  --validated-revisions validated --validated-text-checks docs/wikisource_validated_text_checks.json
```

- **Manifest.** `e2d3b_wikisource_printed_v3`: sha256 `5103d2d9…`, children `7ecfbffc…`. The 35 earlier child references are byte-identical to E2d3's.
- **Predictions.** The 35 earlier pages use the E2d3 cache. The 4 new pages were run with the same engines and settings (heocr-engine `55b0f7d`, Kraken 7.0.2, Tesseract 5.5.3). The prediction sets are Tesseract `b78e435d…`, R3d `2646e47e…`, R3g `ec8e01ec…`, R3h `3c8355d8…` and R3h + blla `7a5506e9…`.
- **Leakage.** It was re-run over the 182 texts: 0 pages excluded and 0 flagged; the largest 3-gram share is 0.9%.

## E2d3c: two pool corrections

Date: 2026-11-07, team-lead decisions of the same day. Same snapshot, inputs, engines, predictions and commands as E2d3b.

### 1. A paragraph break is layout, not text

- **The rule.** A page whose validated text differs from its latest text only in whitespace is used, whatever its check's verdict. The difference may be line or paragraph breaks, or the length of a whitespace run. A paragraph break is layout, so it does not make the validated text disagree with the scan.
- **Where it lives.**
  - `fetchers.wikisource.layout_only_difference` decides it: the same words in the same order, and the texts not identical.
  - `wikisource_eval_references` applies it after the freshness and checksum checks, so it is not a one-page override.
- **What stays a text difference.** Two words run together, a space inside a word, and any changed character still disqualify the page. A page whose F8b7 steps cannot be re-applied to the validated text stays out too.
- **What each item records.** `diff_vs_latest.layout_only` is recorded on every validating-revision item. `validated_text_accepted_by` (`check_verdict` or `layout_only_difference`) is recorded on the item and on its adjudication record.
- **The page.** *Hut ha-Meshulash* p. 12 was E2d3b's strict verdict. Its check now reads `validated_text_matches_scan`, with the rule cited, and it joins the pool.
  - It is in the release `train` split.
  - It is scored on its validated text: 3,454 characters, 2 character edits from the latest text.
  - Its leakage check is clear.

### 2. Hebrewbooks 19784 p. 24 is `text_not_on_page`

- **The assumption.** E2d3b found one editors' Rashi citation on this crop that the page does not print. The plan was to exclude that span from primary scoring.
- **The finding.** The E2d3c check read the pinned 960 px crop, enlarged, against both texts. The Rashi citation is not the only such text. Both versions also hold:
  - more bracketed source citations, in sections ב and ג;
  - the expansion אמר רבי יצחק, where the page prints the abbreviation אר"י;
  - quotation marks the page does not print;
  - vocalised verse words.

  An excluded span cannot cover an expansion, and masking every addition would leave a reference the editors did not write. So the existing **page-level** mechanism applies. This follows the #130.1 decision: a page with other words the page does not show stays `text_not_on_page`.
- **What changed in the checks.**
  - The page's agent check in `docs/wikisource_page_checks.json` now records `text_not_on_page`.
  - The page's validated-text check stays `validated_text_disagrees_with_scan`, with the detail extended.
  - `docs/wikisource_index_inventory.md` is re-rendered from the cache. Quality-4 `text_not_on_page` goes from 1 to 2, and quality-4 cropped pages from 5 to 4.
- **In the tranche.** The committed tranche v3 still lists the page, because it was built before this check. Applying the committed checks to the v3 Wikisource page records rejects exactly this page (`text_not_on_page`) and no other. The next tranche build drops it. The committed manifest and the tranche are not rebuilt here.
- **The pool.** The page was never scored, so the pool and the validation + test set do not change on its account.

### Results (`primary.v1` CER, 95% intervals, 2,000 resamples, seed 20261106)

| Engine | E2d3b, 39 pages | **E2d3c, 40 pages (14 books)** | Page | Book | Val + test, 10 pages (unchanged) |
| --- | ---: | ---: | --- | --- | ---: |
| Tesseract 5.5.3 `heb`, psm 3 | 0.216 | **0.231** | [0.171, 0.297] | [0.149, 0.349] | 0.212 |
| R3d + R4d + A1 | 0.887 | **0.891** | [0.861, 0.928] | [0.836, 0.953] | 0.777 |
| R3g + R4d + A1 | 0.881 | **0.886** | [0.854, 0.923] | [0.826, 0.952] | 0.761 |
| R3h + R4d + A1 | 0.884 | **0.889** | [0.856, 0.925] | [0.828, 0.954] | 0.759 |
| R3h + blla (diagnostic) | 0.570 | **0.583** | [0.508, 0.647] | [0.414, 0.671] | 0.637 |

- **The set.** It has 53,371 reference characters (49,923 before). Hyman I now holds 32%. The splits are 30 `train` / 5 `validation` / 5 `test` pages.
- **The added page is hard for every engine.** On *Hut ha-Meshulash* p. 12, Tesseract scores 0.449, R3h + R4d + A1 0.961 and R3h + blla 0.778. That is in line with its book (Tesseract 0.455 over its 4 pages).
  - The page adds 3,448 scored characters, which moves Tesseract up by 0.015.
  - On the 5 validating-revision pages, Tesseract scores 0.267, R3h + R4d + A1 0.897 and R3h + blla 0.573.
- **No conclusion changes.**
  - R3h − Tesseract is +0.658: page interval [+0.602, +0.713], book interval [+0.553, +0.745]. R3h is worse on 40 of 40 pages.
  - R3h − R3d is −0.003: page [−0.007, +0.002], book [−0.008, +0.003].
  - R3g − R3d is −0.005: page [−0.010, −0.000], which still excludes zero; book [−0.010, +0.001], which does not.
  - R3h + blla − R3h + R4d + A1 is −0.306: page [−0.375, −0.247], book [−0.471, −0.203].
- **Segmentation.** R4d finds a median of 165 lines per page, where Tesseract finds 27. R4d finds more lines on 38 of the 40 pages.

### Finding for review: the Hebrewbooks 19784 references

The same kind of editors' text appears on a **scored** page of this book. A spot view of p. 25 (release `test`) was made while checking p. 24; it was not an audit. Its reference holds:
- bracketed citations the page does not print, such as (מגילה כד, ב) and (במדבר לא, יז);
- the expansions מה שכתוב and פירוש of the printed מ"ש and פי';
- quotation marks the page does not print;
- a section letter other than the printed one.

Hebrewbooks 19784 holds 81% of the validation + test characters. Part of every engine's validation + test CER may therefore be reference text that is not on the page. Auditing the reference text awaits maintainer approval, so nothing here acts on it. A check of the 5 scored pages of this book, like the one done for p. 24, would settle it.

### Reproduction

- **Operator scripts.** They are in `tasks/real-source-mapping/intermediates/e2d3c/scripts/`:
  - `e2d3c_leakage.sh`, `e2d3c_subsets.py`, `e2d3c_score.sh` and `e2d3c_summarize.py` are E2d3b's, with paths and counts updated;
  - `e2d3c_tranche_check.py` applies the committed page checks to the tranche v3 page records;
  - `e2d3c_peek.py` is a diff aid.
- **References.** The command is E2d3b's, with the new manifest id:

  ```bash
  python -m hocrgen.tools.wikisource_eval_references SNAPSHOT refs --items items.json --hold-out hold_out.json \
    --split-manifest split_manifest.json --reference-manifest-id e2d3c_wikisource_printed_v4 \
    --validated-revisions validated --validated-text-checks docs/wikisource_validated_text_checks.json
  ```

  It reuses E2d3b's pinned validated revisions, `items.json` and the E2d3 release split manifest.
- **Manifest.** `e2d3c_wikisource_printed_v4`: sha256 `1e2344a0…`, children `7de3dfa5…`. The 39 E2d3b child references are byte-identical.
- **Predictions.** They are E2d3b's, plus E2d3b's runs on p. 12 from `predictions_new/`. Nothing was re-run. The prediction sets are Tesseract `617d3d2c…`, R3d `4e683a01…`, R3g `e6808361…`, R3h `9314cbcb…` and R3h + blla `6677a6bf…`.
- **Leakage.** It was re-run over the 183 texts: 0 pages excluded and 0 flagged; the largest 3-gram share is 0.9%.
