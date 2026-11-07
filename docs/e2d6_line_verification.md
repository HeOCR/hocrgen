# E2d6: single-line verification of real printed lines

> **Status (2026-11-07).** The tool and the first batch (`line_verify_v1`, 1,500 lines) are built. No human has
> verified a line yet, so [`line_verify_references.json`](./line_verify_references.json) holds no lines, and no score
> has changed.

## Why

The real printed evaluation set is small: 38 adjudicated Wikisource quality-4 pages from 14 books. The release
`test` split holds 8 of those pages, from 4 books. Engines are far from good on real scans. On those 38 pages,
Tesseract scores CER 0.237 and R3h + R4d + A1 scores 0.898 ([E2d3e](./e2d3b_validated_revision_evaluation.md)).
Auditing the near-perfect quality-4 pages mostly finds trivia ([E2d4](./e2d4_reference_audit.md)).

This step spends human effort on **hard, informative lines that add evaluation data** instead:

- **One line at a time.** A human sees one printed line on a real scan, next to a candidate transcription that a
  *different* human typed.
- **Four outcomes.** The human confirms the candidate (`exact`), corrects it (`edited`), or flags the line as
  `unreadable` or `misaligned`.
- **Order.** The hardest lines come first, and an unbiased random stratum is mixed in.

The online app is `HeOCR/heocr-review`. Both formats are fixed by the line verification contract (v1, 2026-11-07):

- `line_verify_items.v1`, the bundle that hocrgen exports;
- `line_verify_decisions.v1`, the decisions file that the app exports and hocrgen ingests.

## Attestation (maintainer decision 2026-11-07)

> "Yes, like quality 4" (Shay Palachy Affek, 2026-11-07).

**What counts as adjudicated.** A line counts as **adjudicated** when both of these hold:

- one human typed its candidate (a Wikisource quality-3 proofreader, or the Project Ben-Yehuda typist);
- a second human then verified it in the app (`exact` or `edited`).

This is the same standard as Wikisource quality 4 (F8 decision 2). Such a line is `reference_eligible: true` for
evaluation. The record is
[`planning/decisions/2026-11-07-line-verification-attestation.md`](../planning/decisions/2026-11-07-line-verification-attestation.md).

**Where the policy lives.** It is set in one place, `hocrgen.tools.line_verify.ATTESTATION_POLICY`.

| Policy | `attestation_status` | `adjudication_status` | `reference_eligible` |
| --- | --- | --- | --- |
| `adjudicated` (**default**, the decision) | `typist_and_verifier_adjudicated` | `adjudicated` | `true` |
| `single_human_verified` (the conservative fallback) | `single_human_verified` | `not_adjudicated` | `false` |

Switching back is one line: set `ATTESTATION_POLICY = "single_human_verified"`.

**The usual rules still hold:**

- **Exclusions.** `unreadable` and `misaligned` lines are excluded. A `misaligned` line is also counted as feedback
  on alignment quality (`misaligned_share_by_source`).
- **Edited lines.** An `edited` line's reference is the reviewer's text. The candidate is kept beside it as
  provenance (`candidate_text`, `candidate_provenance`, `corrected: true`).
- **Two different people.** The verifier is a different person from the typist. This is always true for these
  sources: the typists are Wikisource editors and PBY volunteers, recorded upstream, and the verifiers are
  pseudonymous `rv_` reviewers in the app. The references file records `verifier_differs_from_typist: true`.
- **Release splits.** Each line keeps its book's release split. Lines from `train` books are not held-out
  evaluation, and validation + test stays a labelled diagnostic (E2d3e).

## Sources

The first batch draws on two sources.

**Hebrew Wikisource quality-3 pages** (`wikisource_he_proofread`). The text is CC BY-SA 4.0.

- **Which pages.** All 1,394 quality-3 pages of tranche `e2d3e_real_tranche_v5`.
  - Every page is re-gated by the unchanged `page_exclusion_reasons`, so its Index passes the F8b rights gates.
  - Every pinned image and text is checked against its sha256.
  - The 38 scored quality-4 pages are left out through `--exclude-reference-manifest`, along with every other
    quality-4 page.
- **Images.** They are the pinned 960 px Commons renders.
- **Localization.** It reuses the coverage tool's Tesseract cache (`<image sha256>.heb.psm3.x2.tsv`, from a 2× upscale
  of the render).
- **Labels.** `candidate_provenance: wikisource_quality3_single_proofreader`, and the `release_split` of the page's
  book.

**PBY texts aligned to NLI free-use scans** (`benyehuda_nli_aligned`, F8f). The text is public domain.

- **Which scans.** These two F8f scans: 342 pages in all.
  - Brainin, *Avraham Mapu*: 162 canvases.
  - Silman, *Sansinim*: 180 canvases, carrying 9 PBY works.
- **Rights.** Each scan is re-gated by the unchanged `decide_nli_rights`, and only `public-domain-free-use` passes.
- **Left out.** The 12 local Frank canvases have no aligned PBY text, so they are not used.
- **Images.** They are the F8f 1,600 px page images.
- **Labels.** `candidate_provenance: pby_human_typed_aligned`, and `release_split: null`, because the pages are not in
  a release.

**Never included:**

- anything from `heocr-restricted-eval`;
- tender pages;
- Google-class `public-domain-non-commercial-use` scans;
- any rights-unresolved item.

The bundle validator refuses any other `source`.

## Line localization

The tool reuses the F8f aligner (`benyehuda_nli_alignment.align_pages`). It aligns the human text to the OCR lines
in reading order. The anchors are unique loose-skeleton 8-grams, chained by a longest increasing subsequence, and
each line is then refined with `difflib`.

- **Wikisource.** Each page is aligned on its own text.
- **PBY.** Each work is aligned across all canvases of its scan. A line that two works both locate is dropped.

**The candidate text** is the human text of the line's span, built in three steps:

1. NFC, with one space between words;
2. the hocrgen reference rule `fix_space_before_punctuation`;
3. nothing else.

The rule is `hocrgen.reference_rules.fix_space_before_punctuation`, the always-on `space_before_punctuation.v1` rule
of `E2d4b`. It is the same rule that every Wikisource evaluation reference goes through, so a verified line and a
scored page follow one convention.

**OCR is used only for geometry, difficulty and attention spans.** No OCR text is written to the bundle, the report
or the references. The bundle validator refuses any item field outside the contract.

### Eligibility (weak alignment is dropped)

A located line (`matched`) is eligible only if it passes every check below (`line_verify.ELIGIBILITY`):

| Check | Threshold |
| --- | --- |
| Line alignment score (loose-skeleton similarity) | ≥ 0.80 (the aligner's own floor is 0.70) |
| Page alignment score (letter-weighted mean of the page's located lines) | ≥ 0.85 |
| **The span tiles with its neighbours** | no letters of the human text between it and the previous and next located lines, and no overlap; on a Wikisource page the text's start and end count as neighbours |
| Letters (long lines) | ≥ 15 |
| Box width / median line width of the page (full lines) | 0.60–1.35 |
| Box height / median line height | ≤ 1.60 (taller boxes usually hold two lines) |
| Overlap with another OCR line box | ≤ 30% of the box |
| Not a catchword line, not across a paragraph break, no footnote mark (`[n]`, PBY `[^n]` or a number glued to a word), no Wikisource `illegible_on_scan` span | — |

**Why tiling.** On a calibration sample, lines with a score of 0.70–0.80 often had the wrong first or last word: the
human text ran on into the next line, or a word was missing at the start. Lines whose spans tile with their
neighbours had right boundaries at every score checked. Tiling is the main filter: it drops 8,319 lines.

**Counts in `line_verify_v1`.**

- **Located lines.**
  - 45,367 on Wikisource.
  - On PBY, each work is counted on its own pages.
- **Eligible lines.** 34,969: 30,505 from Wikisource and 4,464 from PBY, in 50 books.
- **Rejected lines:**
  - 8,319 do not tile with their neighbours;
  - 2,831 are short;
  - 1,887 are on weak pages;
  - 1,615 cross a paragraph break;
  - 1,355 have overlapping boxes;
  - 843 have a weak line score;
  - 656 are not full lines;
  - 227 have boxes that are too tall;
  - 48 carry a footnote mark;
  - 16 carry a catchword;
  - 1 holds an excluded span.

**Boxes.**

- `box` is the line's Tesseract ink box, padded by 0.12 of its height (at least 2 px) and clipped to the page.
- `context_box` adds 1.2 median line heights above and below, and 2% of the page width at each side.
- Both are in the shipped image's pixels.

## Difficulty

`difficulty` ∈ [0, 1] is a weighted sum (`line_verify.difficulty`):

```
difficulty = 0.60 · ocr_disagreement + 0.20 · ocr_low_confidence + 0.10 · niqqud + 0.10 · small_type
```

**`ocr_disagreement`.** This is how far the engines' reading of the line is from the candidate.

- **Tesseract** is cached for every page. Its score is the share of candidate characters that the `difflib` edit
  script touches, capped at 1.
  - Both sides drop niqqud and cantillation, since OCR does not read them.
  - A change in spacing alone is not counted.
- **R3h + R4d + A1** is added where a cached reading exists: the E2d diagnostic pages, 132 of the selected lines.
  - It enters **page-centred**: its disagreement minus the median over the page's eligible lines, times 0.2.
  - That engine sits near CER 0.9 on real print and covers few pages. An absolute term would lift every line on
    those pages up the hard ranking. The centred term only reorders lines within a page.

**The other components:**

- `ocr_low_confidence` is 1 − the line's mean Tesseract word confidence / 100;
- `niqqud` is the share of the candidate's letters that carry points;
- `small_type` is 1 when the box is under 0.75 of the page's median line height.

**Attention spans** are the candidate words where Tesseract's reading disagrees, merged. They are `[start, end)`
code-point offsets into `candidate_text` (Python string indices). They never contain the OCR text.

- The contract allows an empty span, `[i, i]`, to mark an insertion point, and the validator accepts it.
- This exporter always widens a disagreement to whole words, including an insertion on the OCR side, so it writes
  no empty spans.

## Selection

`line_verify.select_items` is deterministic given its inputs: the seed is the batch id, and ties are broken by a
seeded hash of the item id.

1. **`random`: 20% of the batch (300 lines).** This is a uniform sample of the eligible lines, drawn with
   `random.Random(seed)` over the lines sorted by id. No book holds more than 10% of the stratum. Within that cap,
   it is an unbiased estimate of how often a candidate is wrong.
2. **`hard`: the rest (1,200 lines).** These are taken by difficulty, under two caps:
   - at most 8 lines per page;
   - at most 10% of the whole batch per book, random lines included.
3. **Rank.** Hard lines come in difficulty order, with a random line at every 5th place. Rank 1 is a hard line.

## The first batch: `line_verify_v1`

The bundle is in the operator data at
`tasks/real-source-mapping/intermediates/line_verify_v1/bundle/`. It is not committed.

- **Size.** 1,500 items on 707 pages (222 MB of page images).
- **Integrity.** Every page sha256 matches.
- **Reproducibility.** A second export gave a byte-identical `items.json`.
- **Script.** `line_verify_v1/export.sh` reproduces it.

| | Lines |
| --- | ---: |
| Wikisource quality 3 | 1,394 (hard 1,146, random 248) |
| PBY ↔ NLI | 106 (hard 54, random 52) |
| Books | 39 (largest 10.0%) |
| Release split `train` / `validation` / `test` / none | 1,066 / 75 / 253 / 106 |
| Hard lines, difficulty 0.2–0.3 / 0.3–0.4 / ≥ 0.4 | 869 / 276 / 55 |
| Random lines, difficulty < 0.2 / ≥ 0.2 | 269 / 31 |
| Line alignment score 0.8–0.9 / ≥ 0.9 | 425 / 1,075 |

**Books.** Four books reach the 150-line cap: *The Selihot for the Entire Year* (`test`), Hyman's *Toldoth Tannaim
veAmoraim* I and II, and the Korfu siddur.

**Spans.** 1,456 lines carry attention spans. Even random lines usually have a Tesseract disagreement somewhere.

**Split.** 253 lines are in `test` and 75 in `validation`. Together that is more than the 8 + 2 test and validation
pages of the current scored set.

### Spot check of the alignment (agent, 2026-11-07)

An agent rendered 30 items from the bundle: each line's `context_box`, with its `box` outlined. They were read
against the candidate.

- the 10 top-ranked hard lines;
- 12 hard lines sampled at random;
- 4 hard PBY lines;
- 4 random PBY lines.

**Result: 30 of 30 boxes and candidates are the same printed line, with the right first and last words.**

The check ran on the export made just before the switch from the interim rule to the merged `E2d4b` rule. All 30
items are in the final bundle with the same boxes. That switch changed the candidate text of 23 of the 1,500 lines
(a space after a mark that runs into the next word).

What the check showed:

- **Boxes.** On pointed liturgical and Bible pages, about 5 of the 30 boxes reach into the niqqud or ascenders of
  the line above or below. The line is still unambiguous.
- **Candidate differences.** The differences a verifier will correct are the candidate's, not the alignment's:
  - Wikisource editors' verse numbers in Bible text;
  - abbreviations the editors expanded;
  - a printed footnote superscript the text omits;
  - PBY's normalized quotes (`"` for the print's `,,`);
  - printed dashes that PBY drops.

  These are exactly the cases that add evaluation data.
- **The hardest lines** are on worn or small type (Hyman's citation lists, the Selihot, the Korfu siddur). They are
  not misalignments.

Before the tiling rule, a sample at line scores 0.70–0.80 had boundary errors on 4 of 10 lines, and one box spanning
two lines. That sample is why the rule exists.

## Decisions and ingest

`line_verify_decisions.v1` is the app's export. A file is valid only if:

- `decision_id` is `decision:<item_id>:<reviewer>`;
- the reviewer is a pseudonymous `rv_` id with 8 lower-case letters or digits;
- `decision` is one of `exact`, `edited`, `unreadable` or `misaligned`;
- `text` is present only for `edited`, and is the full corrected line: NFC, on one line, and not equal to the
  candidate;
- `decided_at` is a date and `checked_by` is `human`;
- each reviewer decides an item at most once;
- every item is in the bundle, and the batch id matches.

`ingest` resolves the outcomes.

- **When an outcome applies.** At least `min_reviewers` reviewers decided the item (1 by default, as in E2d4), and all
  of them agree. For `edited`, they must also give the same text.
- **Disagreement** leaves the item in `conflict`, and nothing applies.
- **Stale decisions.** Each decision carries `candidate_sha256`, the SHA-256 hex of the UTF-8 `candidate_text` the
  reviewer judged. It is a contract addition from the app side. A decision whose hash differs from the item's
  current candidate is **stale**, for example after a re-export changed the candidate. A stale decision is listed
  under `stale`, counted in `counts.stale_decisions`, and never applied. A decision without the field is taken as
  made on the current candidate.

It writes two files:

- **[`docs/line_verify_references.json`](./line_verify_references.json)** (`line_verify_references.v1`, committed).
  It holds:
  - the attestation policy;
  - the counts;
  - every decision, verbatim;
  - one record per verified line: item, page, book, `release_split`, `box`, page sha256, `candidate_provenance`,
    `candidate_text`, the final `text` and its sha256, `corrected`, the reviewers, the decision ids, the date, the
    attestation fields and `text_license`;
  - the exclusions, the conflicts and the stale decisions.

  It holds no images, no OCR text and no local paths. `validate --references` re-derives it from the decisions and
  the bundle.
- **The operator line reference set** (`--line-set-out`, `line_verify_line_references.v1`). It holds the verified
  lines with their context boxes and their bundle page records (`modality: printed`, `visibility: hidden_reference`).

## Reproduce (operator)

```bash
D=tasks/real-source-mapping/intermediates
python -m hocrgen.tools.line_verify export \
  --wikisource-snapshot $D/e2d3e/tranche/e2d3e_real_tranche_v5/sources/wikisource_he_proofread/snapshot \
  --wikisource-ocr-cache $D/f8b7/ocr_cache --split-manifest $D/e2d3e/release_split_manifest.json \
  --exclude-reference-manifest $D/e2d3e/refs/reference_manifest.json \
  --engine-geometry r3h_r4d_a1=$D/e2d3e/predictions/r3h_r4d_a1_geometry \
  --nli-works $D/line_verify_v1/nli_works.json \
  --out $D/line_verify_v1/bundle --report $D/line_verify_v1/export_report.json \
  --batch-id line_verify_v1 --created-at 2026-11-07
python -m hocrgen.tools.line_verify validate --bundle $D/line_verify_v1/bundle
python -m hocrgen.tools.line_verify stats --bundle $D/line_verify_v1/bundle [--decisions D]
# after review: the app's export
python -m hocrgen.tools.line_verify ingest --bundle $D/line_verify_v1/bundle --decisions line_verify_decisions.json \
  --out docs/line_verify_references.json --line-set-out $D/line_verify_v1/line_reference_set.json
```

`nli_works.json` (`line_verify_nli_works.v1`) lists each F8f scan with these fields:

- its manifest and manifest URL;
- its work directory (`img/`, `ocr/`);
- the PBY catalogue;
- its works.

## Caveats and follow-ups

- **Image resolution.** The Wikisource images are the pinned 960 px renders. Small type and niqqud are hard to read
  at that size. A 1,920 px render of the same Commons pages, as E2d4 used, would help the verifier. It needs a
  fetch, and the box coordinates scale by 2.
- **R3h covers few pages.** R3h + R4d + A1 readings exist only for the E2d diagnostic pages. More engines' line
  readings would sharpen the difficulty score.
- **Where the eligible lines are.** Most come from a few large books: Hyman's three volumes hold 16,623 of the
  34,969, and Gersonides' *Milhamot Hashem* 5,634. By release split the eligible lines are 27,080 `train`, 1,995
  `validation`, 1,430 `test` and 4,464 PBY (no split). The caps keep the batch spread out, and later batches can
  lower them.
- **What is not in v1:**
  - footnote lines;
  - lines with footnote marks;
  - short lines (headings, line ends);
  - lines that cross a paragraph break.

  Each of these needs a convention for the verifier first.
- **Using the references.** Verified lines become line-level references for the printed track. How they are scored
  next to the page-level set is a separate step.
