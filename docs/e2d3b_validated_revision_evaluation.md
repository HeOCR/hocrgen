# E2d3b: quality-4 pages scored on their validating-revision text

Date: 2026-11-07, on the F8g2 tranche v2. Plan: [`planning/tasks/e2d-real-scan-evaluation.md`](../planning/tasks/e2d-real-scan-evaluation.md).

This document **supersedes the all-pages results of [E2d3](./e2d3_real_printed_evaluation.md)**. E2d3's validation + test results are unchanged, because no new page falls in those splits. Everything else in E2d3 still holds: the method, the book (cluster) bootstrap, the release splits and the quality-3 stratum.

> **[E2d3c](#e2d3c-two-pool-corrections) corrects the pool to 40 pages** (one paragraph-break page admitted; Hebrewbooks 19784 p. 24 is `text_not_on_page`). **[E2d3d](#e2d3d-the-hebrewbooks-19784-pages) then removes two more Hebrewbooks 19784 pages: 38 pages, validation + test 8.** The E2d3d numbers supersede both earlier headlines. **[E2d3e](#e2d3e-a-reference-constraint-on-the-test-split) re-splits the release (`size_aware_group_split.v2`): validation + test becomes 10 pages. Until the splits change again, validation + test is a labelled diagnostic, never a headline (team-lead decision, 2026-11-07).**

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

## E2d3d: the Hebrewbooks 19784 pages

Date: 2026-11-07, at the team lead's request. It follows up the E2d3c finding.

### The check

Each of the 5 scored pages of Hebrewbooks 19784 was checked. Every scored page of this book is in the release `test` split.

- **Method.** The pinned 960 px render was read in enlarged column crops against the page's reference text. This is the same check as for p. 24.
- **The question.** Does the text hold editors' text that the page does not print?
  - bracketed citations;
  - expanded abbreviations;
  - added quotation marks or vowel points;
  - a section letter or heading that differs from the print.
- **The rule.** Decision #130.1: such a page becomes `text_not_on_page` in `docs/wikisource_page_checks.json` and leaves the pool.
- **Not done.** No reference text was edited or corrected. Plain misreadings seen in passing are left to the reference audit, which awaits maintainer approval.

| Page | Content | Verdict | Reason |
| --- | --- | --- | --- |
| p. 1 | title page | stays | The text follows the print line by line. The publisher's logo and the digitization stamp are not transcribed, and both are outside the body. |
| p. 2 | contents and copyright | stays | The text follows the print. Its bracketed (מהוריי"צ) and the telephone numbers are printed. |
| p. 8 | end of the publishers' note, with two notes | **`text_not_on_page`** | The text adds a heading, הערות, above the notes. The page prints only a rule there. |
| p. 18 | the book's introduction | stays | The text follows the print. Abbreviations stay as printed (ע"י, מוהר"ר, ית', ח"ו), with no citations and no added quotation marks. |
| p. 25 | *Likutei Amarim*, sections ד–ו | **`text_not_on_page`** | See below. |

On p. 25 the editors' text runs through the whole page:
- bracketed citations the page does not print, such as (מגילה כד, ב) three times, (במדבר לא, יז), (שיר השירים ב, ט) and (ישעיה נא, ד);
- expansions of printed abbreviations: פירוש for פי', מה שכתוב for מ"ש, and נוקבא for נוק';
- added quotation marks;
- a running head the page does not print (מגיד דבריו ליעקב for the printed לקוטי אמרים);
- section letters ג–ו where the page prints ד–ו, with the editors opening a section that the page runs on.

### A systematic convention

The book's text follows one convention in the *Likutei Amarim* body and another in the front matter.

- **The body (pp. 24 and 25).** The editors produce a modern annotated text: source citations in brackets, expanded abbreviations, quotation marks around quoted passages, vocalised verses, and their own section numbering and running head. Every body page of this book is likely to carry it.
- **The front matter (pp. 1, 2, 8 and 18).** It follows the print, apart from p. 8's heading.
- **What was built for it.** Nothing.
- **What was not checked.** The book's three quality-3 pages in the diagnostic stratum (pp. 3, 16 and 20) are not scored, and they were not checked.

### In the tranche

The committed tranche is now v4 (F8e3), and its Wikisource snapshot is v3's byte for byte. Applying the committed checks to those page records rejects exactly pp. 8, 24 and 25 (`text_not_on_page`), and no other page. The tranche still lists them; the next build of its Wikisource snapshot drops them.

The eval snapshot predates the check. So the run holds out pp. 8 and 25 by item id, with the reason, through the existing `--hold-out`; leakage held out nothing.

### Results (`primary.v1` CER, 95% intervals, 2,000 resamples, seed 20261106)

| Engine | E2d3c, 40 pages | **E2d3d, 38 pages (14 books)** | Page | Book | E2d3c val + test, 10 pages | **E2d3d val + test, 8 pages** | Page | Book |
| --- | ---: | ---: | --- | --- | ---: | ---: | --- | --- |
| Tesseract 5.5.3 `heb`, psm 3 | 0.231 | **0.237** | [0.173, 0.300] | [0.149, 0.364] | 0.212 | **0.257** | [0.121, 0.508] | [0.178, 0.325] |
| R3d + R4d + A1 | 0.891 | **0.901** | [0.870, 0.938] | [0.855, 0.957] | 0.777 | **0.808** | [0.774, 0.869] | [0.764, 0.873] |
| R3g + R4d + A1 | 0.886 | **0.896** | [0.863, 0.933] | [0.846, 0.956] | 0.761 | **0.783** | [0.743, 0.837] | [0.697, 0.855] |
| R3h + R4d + A1 | 0.889 | **0.898** | [0.866, 0.935] | [0.847, 0.958] | 0.759 | **0.779** | [0.741, 0.829] | [0.721, 0.852] |
| R3h + blla (diagnostic) | 0.583 | **0.578** | [0.500, 0.642] | [0.401, 0.671] | 0.637 | **0.613** | [0.519, 0.671] | [0.477, 0.654] |

- **The pool.**
  - It is 38 pages with 50,399 reference characters. Hyman I holds 34%.
  - The splits are 30 `train` / 5 `validation` / **3 `test`**.
  - Validation + test is 8 pages from 5 books, with 4,839 characters. Hebrewbooks 19784 holds 70% of those characters.
- **Why CER rises.** The two removed pages were easy for Tesseract (p. 8 0.114, p. 25 0.145), even with the added text. The remaining three pages are harder: p. 1 0.492, p. 2 0.599 (with an English block) and p. 18 0.082.
- **No conclusion changes.**
  - R3h − Tesseract is +0.662: page [+0.605, +0.720], book [+0.548, +0.753]. R3h is worse on 38 of 38 pages.
  - R3h − R3d is −0.003: page [−0.008, +0.002].
  - R3g − R3d is −0.005: page [−0.010, −0.000], book [−0.011, +0.001].
  - R3h + blla − R3h + R4d + A1 is −0.321: page [−0.392, −0.261], book [−0.488, −0.222].

### The validation + test set is now too small

- **The `test` split.** It is 3 pages of one book: a title page, a contents and copyright page, and one introduction page (3,372 characters).
- **Validation + test.** It is 8 pages from 5 books. Its page interval for Tesseract spans [0.121, 0.508].
- **What it supports.** Neither split can carry a held-out result for a model trained on the release. They are reported here as a diagnostic.
- **The splits.** They were not rebalanced. Any change is a release-split decision, proposed to the team lead.

### Reproduction

- **Operator scripts.** They are in `tasks/real-source-mapping/intermediates/e2d3d/scripts/`. They are E2d3c's with paths and counts updated, plus `e2d3d_strips.py` (the review crops) and `e2d3d_tranche_check.py`.
- **References.** The command is E2d3c's, with `--hold-out hold_out.json` naming pp. 8 and 25 and `--reference-manifest-id e2d3d_wikisource_printed_v5`.
- **Manifest.** sha256 `c0682e82…`, children `5a13400f…`. The 38 child references are byte-identical to E2d3c's.
- **Predictions.** They are E2d3c's, unchanged; the prediction set checksums are the same.
- **Leakage.** It was re-run over the 181 texts: 0 excluded and 0 flagged.

## E2d3e: a reference constraint on the test split

Date: 2026-11-07, team-lead decisions of the same day on the E2d3d split proposal, and on the first draft of this PR.

> **Validation + test is a labelled diagnostic, never a headline,** until the release splits change. That covers every table below and the operator report. The headline is the all-pages result. Real-data validation is too small to tune on, so tuning stays on synthetic validation for now.

### The constraint (`size_aware_group_split.v2`)

The group-whole split (`src/hocrgen/split/balance.py`) keeps v1's item placement. It adds a constraint on human-adjudicated reference text. The full rule is in [the release contract](./real_source_release_contract.md).

- **What a book weighs.** A book's weight is the characters of every page the evaluation scores, on the text it scores: adjudication-eligible pages on their latest text, and pages scored on their validating-revision text (E2d3b/E2d3c), after every page gate.
- **One rule for both sides.** The fetcher (`scored_reference_characters`) and `wikisource_eval_references` call the same function, `fetchers.wikisource.scored_page_reference`, so they cannot drift.
  - Tranche v5 carries each page's pinned validating revision and committed check, so the release build sees what the evaluation sees.
  - A test checks that the split weight's page set equals the evaluation pool's page set. On tranche v5 both are the same 38 pages.

| Constraint on `test` | Value | Why |
| --- | ---: | --- |
| `min_groups`, the fewest books with scored pages | 2 | A result from one book is a one-book result, and the book bootstrap needs two clusters. |
| `min_share`, the smallest share of the stratum's scored characters | 10% | The test ratio of the split policy: test holds its share of the reference text, as it holds its share of the items. |
| `max_group_share`, the largest share one book may hold of test's scored characters | 50% | No book holds a majority of test's reference text. In E2d3d one book held 70% of validation + test. |

- **The repair.** When `test` fails the constraint, the weighted books keep their splits, and test takes one more weighted book from train.
  - The book must not itself exceed the cap.
  - A book whose move alone satisfies the constraint is preferred; then the fewest pages, then the least weight.
  - Unweighted books refill the item targets around it.
  - The process is deterministic. A constraint that cannot be met is reported, not forced.
- **Validation is not constrained** (team-lead decision). It stays a labelled diagnostic, reported together with test.
- **On this pool the constraint moves *The Selihot for the Entire Year* (59 pages), not *Dorot ha-Rishonim* I.** The values were not tuned to change that.
  - After the three `text_not_on_page` pages leave the tranche, v1 puts Hebrewbooks 19784, *Sefer ha-Mispar* and Hebrewbooks 38168 in test. They hold 8.6% of the scored characters, with Hebrewbooks 19784 at 78% of them, so test fails both `min_share` and the cap.
  - **Books that cannot move.** *Dorot ha-Rishonim* I is ineligible: counting its validating-revision page p. 9, it would hold 54.6% of test by itself. *Hut ha-Meshulash* (64.6%), *Masa ba-Arav* (59.9%) and Hyman I (79.9%) are ineligible for the same reason.
  - **Books that move but do not clear.** *Artush* (7 pages) and Hyman III (72) would leave Hebrewbooks 19784 above 50% (51.4% and 52.1%).
  - **The one that clears.** *Selihot* clears both rules: test share 15.4%, largest book 43.8%.
  - A first draft counted only latest-text pages and moved *Dorot ha-Rishonim* I. By the evaluation's count, that left Dorot at 54.8% of test.
- **Who could have seen the moved pages.** No model trained on release `train` data can have seen them.
  - R3d, R3g and R3h (recognition), R4d (segmentation) and A1 (reading order) were trained from scratch on hocrsyngen synthetic pages only: their run records give `init: from_scratch` and `hocrsyngen_line_annotations.v1`.
  - Their text corpora (`r3d_train_corpus`, `r3e_train_corpus`) are among the 11 corpora of the leakage check, which is clear.
  - Tesseract `heb` is an external model.

### Tranche v5 and the release splits

- **Tranche v5.** `e2d3e_real_tranche_v5` is v4 refreshed with `real_tranche refresh-wikisource --validated-revisions --validated-text-checks`.
  - Hebrewbooks 19784 pp. 8, 24 and 25 leave.
  - 25 pages carry their pinned validating revision and committed check.
  - Every other file is copied byte for byte. It has 2,608 items, `verify` is ok, and the manifest is regenerated.
- **The Wikisource stratum.** It splits 1,162 / 145 / 145 pages and 27 / 17 / 14 books (v1 on v4: 26 / 24 / 8).
  - By scored characters it is 83.6% / 1.1% / 15.4%.
  - No other source's split changes.
- **What moved apart from *Selihot*.**
  - Dropping the three pages alone (under v1) moves *Sefer ha-Mispar* and Hebrewbooks 38168 from validation to test.
  - Unweighted books refill around the move.
  - *Selihot*'s items record `split_constraint: reference_constraint`.

### The pool on the new splits

The pool still has 38 pages, and their references are byte-identical to E2d3d's. Shares below are of the evaluation's reference characters.

| Split | Pages | Books | Ref. characters | Each book's share of the split's characters |
| --- | ---: | ---: | ---: | --- |
| `train` | 28 | 8 | 42,147 | Hyman I 41.1%, *Hut ha-Meshulash* 18.9%, *Masa ba-Arav* 15.5%, *Dorot ha-Rishonim* I 12.5%, *Artush* 5.3%, Hyman III 5.1%, Luzzatto 1.2%, Korfu 0.4% |
| `validation` | 2 | 2 | 511 | *Seder Avodat Yisrael* 71.8%, *Vikuah* 28.2% |
| `test` | 8 | 4 | 7,741 | *Selihot* 44.1%, Hebrewbooks 19784 43.6%, *Sefer ha-Mispar* 9.0%, Hebrewbooks 38168 3.3% |

- **The cap holds by the evaluation's count too:** no test book is above 50%.
- **Validation has 2 pages (511 characters).** Its two adjudicated books moved to test when the pool changed, not by the constraint. It is a diagnostic.

### Results (`primary.v1` CER, 95% intervals, 2,000 resamples, seed 20261106)

| Engine | All 38 pages (headline, unchanged) | E2d3d val + test, 8 pages (diagnostic) | **E2d3e val + test, 10 pages (diagnostic)** | Page | Book |
| --- | ---: | ---: | ---: | --- | --- |
| Tesseract 5.5.3 `heb`, psm 3 | 0.237 | 0.257 | **0.385** | [0.188, 0.556] | [0.210, 0.539] |
| R3d + R4d + A1 | 0.901 | 0.808 | **0.866** | [0.799, 0.927] | [0.790, 0.937] |
| R3g + R4d + A1 | 0.896 | 0.783 | **0.856** | [0.772, 0.927] | [0.753, 0.942] |
| R3h + R4d + A1 | 0.898 | 0.779 | **0.853** | [0.768, 0.925] | [0.757, 0.942] |
| R3h + blla (diagnostic) | 0.578 | 0.613 | **0.656** | [0.576, 0.711] | [0.497, 0.700] |

- **All pages.** The headline is unchanged, because the 38 pages and their predictions are the same; only their split labels changed.
- **Validation + test.** It is 10 pages from 6 books with 8,252 characters; *Selihot* holds 41% of them.
  - Tesseract scores 0.567 on *Selihot*, which raises the diagnostic to 0.385.
  - R3h − Tesseract is +0.468: page [+0.318, +0.610], book [+0.390, +0.610]. R3h is worse on 10 of 10 pages.
- **By split** (Tesseract / R3h): `train` 0.207 / 0.907, `validation` 0.341 / 0.706, `test` 0.388 / 0.863.

### Reproduction

- **Operator scripts.** They are in `tasks/real-source-mapping/intermediates/e2d3e/scripts/`.
  - The E2d3d scripts are reused with paths updated. The summary labels validation + test as a diagnostic.
  - `e2d3e_weight_vs_pool.py` checks the weight's page set against the pool.
  - `e2d3e_groups.py`, `e2d3e_simulate.py` and `e2d3e_trials.py` were first-draft replay aids.
- **Release split.** It comes from `hocrgen build-release --profile profile_open_v1 --dry-run --real-tranche-root .../e2d3e_real_tranche_v5`.
- **References.** `wikisource_eval_references` runs on the v5 snapshot with that run's `split_manifest.json` and the E2d3b `items.json` without the three pages.
  - `--reference-manifest-id` is `e2d3e_wikisource_printed_v6`. No page is held out.
  - It reads the carried fields, and gives byte-identical output with `--validated-revisions --validated-text-checks`.
- **Manifest.** sha256 `9aac8171…`, children `a0a4b152…`.
- **Predictions.** They are E2d3c's, unchanged.
- **Leakage.** It is clear over the 181 texts.
