# P-hist training round: inputs plan and pilot (2026-11-18)

Task from heocr-lead, 2026-11-18. The goal is to have the inputs of an old-Hebrew (P-hist) training round ready, so that
it can start on the HeOCR/heocr-compute pods as soon as Shay picks it. This document covers the source pool and its
licences, the line ground-truth method, the expected line counts, disk and upload sizes, and a pilot with measured label
error. It changes no code, no gate and no list.

**Status.** This is a plan only. Nothing here is a training list. The official CLEAN check stays with heocr-eval, and the
decisions in §8 are for the lead.

## 1. What already exists (trained on in R8b)

| Set | Train lines | Source | Text | Scans |
|---|---:|---|---|---|
| `wslines_v1` | 3,812 | Hebrew Wikisource proofread pages | CC BY-SA 4.0 (decision 0016) | Commons (Route C) |
| `bynli_lines_v3` | 81,182 (R8b used 62,808 after exclusions) | PBY texts on scans of the same edition | PBY public domain | NLI free-use IIIF, and IA library scans (Route B) |
| `rablines_v1` | 17,560 (+3,141 dev, Mekhilta; 5,034 reserved, Leket Yosher) | Sefaria PD versions and PG #43740 on IA scans | Public Domain / CC0, printing named | IA library and Google-via-IA (Route B) |

So the real P-hist pool is about 84k lines today. The Wikisource Page-namespace pool is nearly used up (1,400
eligible pages; F8b7 funnel). The PBY edition match on IA was scouted over 679 edition groups (f8f_ia, 55 IA groups).

**`bynli_lines_v3` includes NLI scans fetched through NLI's own IIIF service** (the `f8f_g` root, `public-domain-free-use`
only, never Google class). The lead's brief says "never the NLI API". Whether those lines stay in a P-hist round is
decision 2 in §8. They are counted separately below.

## 2. Source pool

Every input below has open inputs only: public-domain text, or CC0, or CC BY-SA from Wikisource under decision 0016. Scans
come only from IA (Route B) or Commons (Route C), each with its per-item `rights_justification`. Nothing is NC, ND or of
unknown licence. Nothing comes through the NLI API.

### Tier A: existing gates and tooling, no new decision

1. **Lines removed by the per-book cap.** These are already aligned and gated, and were cut only by `--max-lines-per-book 6100`.
   - `rablines_v1`: Machzor Vitry (Google copy via IA) 12,106 and Lekach Tov 3,942, so 16,048 lines.
   - `bynli_lines_v3`, excluding dev units and the overlap exclusions: *Sifrut ha-Historiya* 1,550, *Yotsrei ha-Sifrut* 1,934 and *Zikhronot le-Beit David* 1,891, so 5,375 lines. Kevar and Yedi'ot are R8b dev units; Zerubavel (638) stays out because of its overlap with audit2 and the ws dev set.
   - Their page images were trashed in the 2026-11-12 cleanup. The refetch manifests exist (`docs/refetch/`), so they must be refetched: about 3,000 pages. Once the cap is lifted, the round needs a mix weight per book instead.
2. **Lines dropped for print markers in `rablines_v1`.** `print_marker_missing_from_label` (11,130) and `parenthetical_differs_from_print` (3,786). A rule that restores the print's note markers from the edition's anchors could recover part of them. Estimate +5–8k. That needs code and an audit.
3. **Pointed PBY prints** (`bynli_lines_v3` `pointed_print`, 7,513): a niqqud stratum, only if the round wants one (decision 4).
4. **Robarts Rashi-script responsa with Sefaria PD texts.** Both pass the IA gate: *Teshuvot ha-Rashba ha-Meyuchasot la-Ramban* (Warsaw 1883, 142 canvases; Sefaria "Warsaw 1883", PD, NLI record cited) and *She'elot u-Teshuvot Chiddushei ha-Rim* (356 canvases; its Sefaria title is still to be found). **Blocked by localization:** see the pilot in §6.

### Tier B: needs one gate decision (decision 1)

The IA gate (`decide_ia_rights`, condition 3 of the 2026-11-09 decision: "the source is known") rejects every item below
as `ia_anonymous_upload_no_known_library`. Checked 2026-11-18:

- **Sefaria's own uploads:** `radbaz`, `ari_sefaria_201601` (Tur OC), `NodaBYehuda`, and `arbaah_turim_vilna_images` (a re-upload).
- **Mirrors of NLI's own scans:** `radaq-bereshit-pressburg-1842-images`, `haameq-davar-vilna-1879-images` and `Talmud_Bavli_Vilna_images`. Their digitizer is still to be confirmed per item.
- **Uploads that name no source:** `KafHaChayimVol.I`.

These hold most of the rabbinic supply the R8 scout found (`tasks/r8-rabbinic-scout/report.md`). The text and the scan are
the same physical copy, because Sefaria typed from the scans it published. The legal strategy's ruling on NLI-origin
files ("Yes, same logic", Shay Palachy Affek, 2026-11-10) covers their rights. What is missing is the "known source"
evidence, which these items give in their description, not in IA's contributor field. The Shulchan Arukh scans are on
Commons; the aligner's text-source path accepts IA scans only, so they also need a Commons fetch path.

**Script.** Square type covers the main column of Tur, Shulchan Arukh (without Orach Chaim, which prints Pri Megadim, an eval
work), Rif and Sefer ha-Mitzvot. Rashi script covers every commentary, Radbaz, Noda bi-Yehuda and the Shas commentaries.

### Tier C: method extension (decision 5)

**Canonical texts on other printings.** A PD Sefaria text of a fixed-text work (for example Mishnah, Midrash Rabbah or the
Vilna Shas layout) placed on another PD printing of the same work. This is where most of the ~5,500 Hebrew IA text items
dated before 1931 could come in. It breaks the "exact edition" rule of decision 2026-11-11, so it needs a decision and
its own measured error first. It is not estimated here.

### Excluded

- The NLI API (Route A).
- Sefaria versions that are CC BY-NC, "unknown", or labelled PD with no printing named.
- Sefaria's "Wikisource Talmud Bavli" (CC BY-SA), out of scope until confirmed.
- Shulchan Arukh Orach Chaim.
- Any Commons file behind a Wikisource Index in a dev, test, reserved or line_verify split.
- Leket Yosher (eval reserve) and the Mekhilta (dev), which stay where they are.

## 3. Line ground truth

**Method: unchanged F8f.**
- `benyehuda_nli_alignment align --source ia --text-source …` places the edition text on the scan, with OCR used for localization only. Its steps are letter skeletons, unique loose 8-gram anchors, the longest increasing chain, and per-line `difflib` refinement.
- `benyehuda_nli_lines build` cuts the lines and applies the gates: min score 0.9, OCR similarity 0.7, height, short line, order and overlap.
- **Labels are always the edition text, never OCR.** Every row stays silver: `not_adjudicated`, `reference_eligible: false`.

**Measured label error.** This is an agent visual check, not a human review. The samples were seeded with
`sha256("20261118:phist-audit:" + set + ":" + id)` and drawn before any image was seen. An error is a line whose label does not
match the printed line, after the set's own folds.

| Set | Lines checked | Word-level error (a word wrong, missing or extra) | Punctuation only | Exact |
|---|---:|---:|---:|---:|
| `rablines_v1` (Sefaria / PG, exact edition) | 32 | 0 (95% upper bound ~9%) | 0 (one letter uncertain) | 32 |
| `bynli_lines_v3` (PBY, edition matched by catalogue) | 48 | 5 (10%) | 4 (8%) | 38 (79%) |

The `bynli_lines_v3` errors:
- a line span shifted by two words;
- a PBY reading that differs from the print in one word;
- footnote digits that differ from the print;
- two crops that cut off the first or last word of the line.

Each is a known failure of catalogue-matched PBY text. The Sefaria-on-edition route does not show them.

**Acceptance bar (proposed):**
- **Per book, before it enters a list:** a 32-line seeded agent sample with at most 1 word-level error. That rejects a book whose true error is around 10% about 85% of the time, and accepts a 3% book about 75% of the time. With 2 word-level errors, a second sample of 32 is drawn; with more, the book is out.
- **Per round:** under 3% of lines with a word-level error, and under 1% character error. Tesseract fine-tuning tolerates that. These lines are never references.
- **Code fixes the audit points to** (each needs its own PR):
  1. a line-edge check: drop a line when its first or last label word has no OCR letters at that edge of the box, so truncated crops go;
  2. digits in a label must match the line's OCR digits;
  3. for PBY, prefer a Sefaria or PG text of the same edition where one exists.

**Rashi script needs its own localizer** (§6). The proposal:
1. render Sefaria PD Rashi-script texts in an open Rashi font, synthetically;
2. fine-tune a Tesseract model on those lines for localization only, on a pod;
3. align with it, under a page-density gate: keep lines only from pages whose chain has at least 10 matched lines.

synth-gen has to confirm the font licence (Noto Rashi Hebrew is said to be OFL; to verify). The localizer never labels
anything.

## 4. Expected line counts

**Yield model.** Batch 1 kept about 23 lines per aligned page, about 17 per canvas. That is 0.35 of the scout's per-book
estimates (36.6k actual against 105k estimated over the five built books). The Tier B estimates below use the same 0.35.

| Tier | Square type | Rashi script | Notes |
|---|---:|---:|---|
| Existing (§1) | ~84k (of which NLI-IIIF scans: part of bynli_lines_v3; decision 2) | 0 | trained on in R8b |
| A1, cap lifted | 21.4k | 0 | ~3,000 pages to refetch |
| A2, print markers | +5–8k (estimate) | 0 | needs code and an audit |
| A3, pointed PBY | 7.5k (niqqud stratum) | 0 | optional |
| A4, Robarts responsa | 0 | 0 now; ~20k with a Rashi localizer | Rashba, Chiddushei ha-Rim |
| B, after decision 1 | ~70k (Tur, SA without OC, Rif, Sefer ha-Mitzvot main text) | ~150–450k once a Rashi localizer exists | the square main text needs no new model |

- **Without new decisions:** about 110–120k real P-hist lines (existing plus Tier A).
- **With decision 1:** about 190k square-type lines.
- The Rashi stratum is the large reserve, but it depends on the localizer working. The range is wide because the pilot measured
  only failure modes.

## 5. Disk and upload

**Measured unit sizes:**
- a line PNG is about 45 KB (`rablines_v1`: 931 MB for 20.7k lines);
- a `.lstmf` file is about 27 KB (R8b: 5.4 GB for about 200k lines);
- a 1600-px page with its OCR TSV is about 1.3 MB (the pilot: 184 MB for 142 pages).

**Keeping the Mac lean** (86 GB free):
- Fetch, OCR, align and cut one book at a time.
- Move each book's page images to the Trash once its lines are cut and verified. The refetch manifest stays, so the book can be rebuilt. Peak page storage stays under 5 GB.
- No full-page intermediates are kept.

| Pool | Lines | PNG + gt on the Mac | Upload to pods (`.lstmf` tarball) |
|---|---:|---:|---:|
| Existing + Tier A | ~115k | ~5.2 GB | ~3.1 GB |
| + Tier B square | ~185k | ~8.3 GB | ~5.0 GB |
| + Tier B Rashi (mid estimate 300k) | ~485k | ~22 GB | ~13 GB |

A pod can build the `.lstmf` files itself from PNG + gt, so the upload could be the PNG set instead (about 1.7× larger).
Only `.lstmf` is needed for training.

## 6. Pilot (2026-11-18): Rashi-script responsa, 142 canvases

- **Text:** Sefaria *Teshuvot haRashba Meyuchas LehaRamban*, "Warsaw 1883", Public Domain, NLI record NNL_ALEPH002563852. It passes `decide_sefaria_licence`. Contributor: Shlomo ben Aderet (Q982170, d. 1310).
- **Scan:** IA `teshuvotharashba00adreuoft` (Robarts, University of Toronto). It passes `decide_ia_rights` (`ia_library_scan_accepted`).
- **Fetching:** all 142 pages, at 1 request per second with the generic UA.
- **Work root:** `tasks/phist-round/` (operator-only).

| Localization | Pages aligned / weak / outside | Text covered | Matched lines at score ≥ 0.9 |
|---|---|---:|---:|
| Stock `heb` (the aligner unchanged) | 1 / 3 / 138 | 0.04% | — |
| + Rashi fold v1 (ש→מ, א→ל, OCR digits 5 6 → א) | 3 / 24 / 115 | 0.5% | — |
| + Rashi fold v2 (also ה ח ת → the ס/מ class, צ→פ, digits 9 0 → א) | 19 / 38 / 85 | 20% | 44 |
| + Rashi fold v3 (v2, and א dropped like a mater) | 25 / 53 / 64 | 6.5% | 51 |

- **Why it fails.** Stock `heb` misreads Rashi letters consistently. The fold was derived from the OCR's letter frequencies against the text's: OCR ס is 17.5% of the letters against 1.1% in the text, because ה, ש, ם and ח read as ס; ב reads as כ; and א reads as 6, 5, ל or ס. The folds are pilot-only monkeypatches (`scripts/rab_run_tool_rashi.py`). The repository's aligner is unchanged.
- **Line labels (agent check, all 44 lines at ≥ 0.9 under v2, labels widened to whole words):**
  - Short lines (under 8 letters, 13 of them) are all wrong. The builder's `short_line` gate already drops them.
  - Of the 31 longer lines, 6 are wrong (19%).
  - **The errors split by page density.** On the one page with a dense chain (25 lines) 1 line is wrong: one extra word. On isolated placements, 5 of 6 are wrong.
  - So the page-density gate in §3 is needed. With stock `heb` and the fold, it keeps almost nothing: 25 lines from 142 pages.
- **Conclusion.** The Rashi stratum needs a Rashi-script localizer before any line set (§3). The square-type method's error is the one measured in §3 on the existing sets.
- **Why the pilot is not on square type.** A square-type pilot on new pages would have needed the 538-page refetch of a capped book. That waits for the refetch in A1.

## 7. Decontamination

- **Per list:** `tasks/r9-new-printed/scripts/decontam.py LIST DROP_OUT`. It covers every target of heocr-eval's `check_train_overlap.py`, including the audit2 references and every dev and report set, and prints no text. `--extra` adds P-hist dev sets that are not yet targets.
- **Per work, before alignment:** no edition or Commons file behind an eval, dev, reserved or line_verify Index. These are the scout's exclusion flags, re-checked per batch.
- **The official CLEAN** on the final list is heocr-eval's (`check_train_overlap.py`), as for R8b and R9.

## 8. Decisions for the lead

1. **IA gate, condition 3.** Should an IA item count as a known source when its description names the digitizer?
   - The two cases are Sefaria's own scans, where the Sefaria version cites the same NLI record and is `digitizedBySefaria`, and mirrors of NLI's own scans that name the NLI record.
   - Each item would still need its own `rights_justification`.
   - This opens Tier B. If the lead reads it as a rights change, it goes to Shay.
2. **NLI-IIIF lines in `bynli_lines_v3`** (free-use scans fetched from NLI's IIIF service, never Google class): keep them in a P-hist round, or drop them under "never the NLI API"?
3. **The Rashi localizer** (§3): synthetic Rashi-script lines in an OFL font, trained on a pod for localization only. synth-gen confirms the font licence first.
4. **Pointed PBY prints** (7.5k) as a niqqud stratum in this round: yes or no?
5. **Tier C** (canonical texts on other printings): pilot it, or not now.
6. **Per-book cap and mix weights** once the cap is lifted (A1).

**Order of work, if decision 1 is yes:**
1. Refetch the A1 pages, as a light job outside the gate window.
2. Tur main column: a 20-page square-type pilot with the §3 audit.
3. Shulchan Arukh and Rif.
4. The Rashi localizer.
5. The Rashi stratum, book by book, each with its 32-line audit.

If decision 1 is no: A1, then A2, then the Rashi localizer for the two Robarts responsa.

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
