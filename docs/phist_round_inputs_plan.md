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
only, never Google class). They stay (§8, decision 2).

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
3. **Pointed PBY prints** (`bynli_lines_v3` `pointed_print`, 7,513): ordinary training lines if they pass the audit bar; no niqqud stratum this round (decision 4).
4. **Robarts Rashi-script responsa with Sefaria PD texts.** Both pass the IA gate: *Teshuvot ha-Rashba ha-Meyuchasot la-Ramban* (Warsaw 1883, 142 canvases; Sefaria "Warsaw 1883", PD, NLI record cited) and *She'elot u-Teshuvot Chiddushei ha-Rim* (356 canvases; its Sefaria title is still to be found). **Blocked by localization:** see the pilot in §6.

### Tier B: opened by decision 1 (Shay, 2026-11-18)

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

### Tier C: method extension (not this round, decision 5)

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

### 3c. Dev units and R7's `bynli_lines_v2` (2026-11-18)

Same method, asked for by heocr-eval and synth-gen:

- **R8b's dev units** (their lines serve as dev references):
  - Kevar: 0 word errors in 32;
  - Brainin IA: 1 in 32;
  - Yedi'ot ha-Teva: 3 in 32. Each is one letter that differs from the print, so it fails, and eval labels its dev numbers accordingly.
- **R7's training set `bynli_lines_v2`, its 6 largest books:**
  - `kolsifreperetsbe03smoluoft`: 0;
  - `kolsifreperetsbe01smoluoft`: 1;
  - `berashadsky-sipurim-1910`: 1;
  - `990017640460205171`: 2, which calls for a second sample;
  - `sifrehazikhronot00mont`: 3 (fail);
  - `citron-ahorei-hapargod-1923`: 5 (fail; words hyphenated across a line break, where the label carries the whole word).
  - In all, 13 of 192 lines (about 7%), so v2 is much cleaner than v3.
  - **Another rule for the v4 rebuild:** a line that ends in a printed hyphen gets a label ending at the hyphen.

### 3b. Per-book audit of `rablines_v1` (2026-11-18)

The same method and bar as 3a, an agent check of 32 seeded lines per book:

| Book | Train lines | Word errors | Verdict |
|---|---:|---:|---|
| Machzor Vitry, Google copy (§6b pilot; never-trained lines) | 6,100 (+12,106 capped) | 1 / 32 | pass |
| Lekach Tov, Buber, vols 3–5 | 6,100 (+3,942 capped) | 1 / 32 | pass |
| Toratan shel Rishonim (PG #43740) | 1,900 | 0 / 32 | pass |
| Avot de-Rabbi Natan, Schechter | 3,417 | 2 / 32, then a second sample: 4 / 32 (6 / 64) | **fail** |

ADRN stays out of the round. Its errors are a letter that differs from the print, printed footnote numbers missing from the label, and a word cut at a line end. The capped lines of Machzor Vitry and Lekach Tov enter once their pages are refetched (A1).

### 3a. Per-book audit of `bynli_lines_v3` (2026-11-18)

**Method.** An agent visual check (three subagents and data-collection; not a human review). Each book got 32 seeded lines (`sha256("20261118:phist-audit:bynli3book_<book>:" + id)`), judged under the §3 bar. Kevar and Yedi'ot (dev units) and Zerubavel (excluded) were not audited. Per-book counts are in `tasks/phist-round/audit/bynli3_books/summary.json` (operator-only).

| Book | Train lines | Exact | Punct only | Word errors | Verdict |
|---|---:|---:|---:|---:|---|
| `seferhademaotmeo0000bern` | 5,350 | 32 | 0 | 0 | pass |
| `kolkitveylkatsen018800` | 5,721 | 30 | 1 | 1 | pass |
| `afahleneemaniml00fngoog` | 5,751 | 28 | 3 | 1 | pass |
| `zikhronotlebetda01reck` | 6,100 | 31 | 0 | 1 | pass |
| `yotsrehasifrutha00zitr` | 6,100 | 28 | 0 | 4 | fail |
| `zikhronotlevetda01frie` | 4,150 | 28 | 0 | 4 | fail |
| `mikhtavimmiarsh00mezagoog` | 3,452 | 25 | 3 | 4 | fail |
| `sipurim00nombuoft` | 1,291 | 26 | 2 | 4 | fail |
| `divreyemeolam02schuuoft` | 4,668 | 24 | 3 | 5 | fail |
| `tsitsimuferaimm00geiggoog` | 633 | 26 | 0 | 6 | fail |
| `sifruthahisoriya11kaha` | 6,100 | 24 | 1 | 7 | fail |
| `990026910840205171` | 2,319 | 25 | 0 | 7 | fail |
| `tserorperaimvehu00kovn` | 3,617 | 12 | 5 | 15 | fail |
| `korothayehudimb00friegoog` | 2,968 | 14 | 1 | 17 | fail |
| `bioretletoldotha01gott` | 4,662 | 9 | 0 | 23 | fail |

- **4 of 15 books pass.** Together they hold 22,922 of the 62,882 audited train lines. Over all 480 audited lines, 99 have a word-level error (21%).
- **The errors have four causes:**
  - **Shifted spans** (`bioretletoldotha01gott`, `korothayehudimb00friegoog`, part of `divreyemeolam02schuuoft`): the label starts with words from the line above and ends short of the printed line.
  - **Tight crops** (`tserorperaimvehu00kovn`): the line box cuts off or clips a word at an edge.
  - **Footnote digits** that differ from the printed marker (`sifruthahisoriya11kaha`, `990026910840205171`, `tsitsimuferaimm00geiggoog`).
  - **Plene spelling.** The PBY text spells words fuller than the print does, which means it was typed from another printing (`sipurim00nombuoft`, `tsitsimuferaimm00geiggoog`).
- **For this round:** only the 4 passing books enter the P-hist pool.
- **Can line-level checks rescue the failing books? Measured on the 480 audited lines, no.**
  - **Edge check:** the first and last label words against the OCR's end words, by loose skeleton. At a threshold of 0.5 it flags 57 lines (48 bad, 9 good). That leaves the kept lines at 12% bad, against 21% before.
  - **OCR similarity below 0.9** flags 100 lines (56 bad, 44 good) and leaves 11% bad.
  - **Letter-count difference** does worse.
  - **Why:** most of what remains is inside the line (plene spelling, one letter, digits), and stock OCR on this print can't tell the edition's reading from the print's.
- **So the per-book audit is the gate:**
  - the failing books stay out, unless a book is re-aligned (the shifted-span books) and passes a fresh audit;
  - the edge check is worth adding later as an extra filter for passing books (about half their bad lines go, at about 2% of their good lines);
  - books whose PBY text was typed from another printing stay out.
- **For the record (heocr-lead, 2026-11-18): R8b and R9 trained on `bynli_lines_v3`,** whose books show an audited word-error rate of about 21% (99 of 480 seeded lines; 11 of 15 books fail the bar).
  - The 11 failing books hold 39,960 of the 62,882 audited train lines.
  - A P-hist start model trained without them could beat R8b, so this bears on the start-model choice in §8, and on how R8b and R9 results on old print are read.
- **A1 consequence:** of the capped bynli books, only `zikhronotlebetda01reck` passes, so the capped lines of `sifruthahisoriya11kaha` and `yotsrehasifrutha00zitr` are not added. Machzor Vitry passed (§6b). Lekach Tov gets its own 32-line audit before its capped lines are used.

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
| B, after decision 1 | ~70k (Tur, SA without OC, Rif, Sefer ha-Mitzvot main text): **needs marker reconstruction first (§6c); pilot 3 kept about 6 lines per page** | ~150–450k once a Rashi localizer exists | |

- **Without new decisions:** about 110–120k real P-hist lines (existing plus Tier A).
- **With decision 1:** about 190k square-type lines.
- The Rashi stratum is the large reserve, but it depends on the localizer working. The range is wide because the pilot measured
  only failure modes.

### 4a. This round is frozen at pool v1 (heocr-lead, 2026-11-18)

- **This round's lists** are pool v1 (`tasks/phist-round/phist_pool_v1.json`) plus about 40k clean Reshumot replay lines (synth-gen).
- **Pool v1** is 37,022 audited square-type lines: 22,922 from the 4 passing `bynli_lines_v3` books and 14,100 from the 3 passing `rablines_v1` books.
- **Everything newer goes into pool v2, for the next round:** the A1 capped lines, marker-free Tier B (option 1 of §6c, audited per book), and the Tur.
- **On size:** 37k is small next to R8b's ~200k lines. Labels audited under 3% word error, plus replay, make this round the honest test of whether clean labels beat volume. The start model is chosen zero-shot on P-hist dev from R7, the office-print winner, and stock `heb`.

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

## 6b. Pilot 2 (2026-11-18): square type, 20 new pages, measured label error

- **What it is.** Machzor Vitry (ed. Hurwitz, Berlin 1889–97), the Google copy on IA (`mahzor-vitri-abraham-berliner-1893`, Route B), with Sefaria's PD version "Machzor Vitry, Berlin, 1893-97". This is the A1 case: an aligned book whose lines were cut by the 6,100 cap.
- **Pages.** 20 canvases, drawn by `sha256("20261118:phist-pilot:" + canvas)` from the book's 793 high-quality aligned pages.
  - Their images were refetched (the 2026-11-12 cleanup had trashed them), at 1 request per second.
  - The full-size sha256 of all 20 matches the original fetch record.
- **Build.** The unchanged `benyehuda_nli_lines build` (main at 8bdf893) on a root holding only those 20 pages and their alignment, uncapped, at min score 0.9.
  - Result: **448 lines, 22.4 per page**, of which 150 are already in `rablines_v1` and **298 were never trained**.
  - Drops: `print_marker_missing_from_label` 62, `outside_repertoire` 32, `below_min_score` 15, `label_disagrees_with_line_ocr` 13, `parenthetical_differs_from_print` 12, `taller_than_one_line` 9.
- **Audit.** A seeded agent check of 32 of the 298 new lines, by `sha256("20261118:phist-audit:mvg_pilot:" + id)`:
  - **30 exact**;
  - **1 word-level error:** the last word of the line is missing from the label;
  - 1 punctuation only: the edition writes commas where the print has stops;
  - 1 letter uncertain (נ or ג), not counted.
- **Verdict.** 1 word error in 32 meets the approved bar (at most 1 in 32), so the book qualifies, and the A1 refetch for the capped books can go ahead. The square-type method on exact-edition text behaves as `rablines_v1` did in §3. The yield matches the batch-1 model: 22 lines per aligned page.

## 6c. Pilot 3 (2026-11-18): Shulchan Arukh main text on Sefaria's Commons scan (Tier B)

- **What it is:**
  - **Scan:** `File:שולחן ערוך יורה דעה חלק ראשון.pdf` (Commons, 295 pages, `PD-old-100-1996`). It says "Scan by Sefaria of NNL_ALEPH001157672", and the Route C gate of hocrgen#207 accepts it.
  - **Text:** Sefaria's PD "Ashlei Ravrevei: Shulchan Aruch Yoreh Deah, Lemberg, 1888". It cites another NLI record (002097765) and is not marked `digitizedBySefaria`, so it may not be the same copy; #207 records this as edition evidence.
  - **Pages:** 20 seeded consecutive pages (199–218).
- **Alignment:** 20 of 20 pages aligned, median 0.936.
- **Lines:** the builder kept 118 (5.9 per page; the main column is a small part of each page). It dropped 73 below min score, 63 for `print_marker_missing_from_label`, and 4 for disagreeing with the OCR.
- **Audit:** 16 of 32 sampled lines were read, enough for a verdict: about 10 of 16 labels miss what the print shows.
  - **Se'if numbers:** the letters ה, ח, יא, יג at the start of a se'if.
  - **Commentators' marker letters** in brackets, such as (ג), [כ], [א], which point to the Taz, the Shakh and the others.
  - One label starts with the previous line's word.
- **Why:** the Sefaria text has these as commentator anchors and segment numbers, and `sefaria_markup.v1` removes them (35,333 anchors in this text). The builder's print-marker gate catches only markers the OCR reads.
- **Verdict:** Tier B Shulchan Arukh and Tur are **not usable as they stand**. The next engineering step, and now the gate for Tier B, is to rebuild each printed marker from Sefaria's anchors (commentator → bracket style, numbered in order) and each se'if number from the segments. Then re-run this pilot and audit it.
  - The main-column yield is also low (about 6 lines per page). Most of each page is the Rashi-script commentaries, which wait for the Rashi localizer.

## 6a. Eval hold-out books (picked before the pool is filled)

**What eval needs.** heocr-eval's power analysis (`eval-domains/scripts/phist_power.py`) asks for at least 30 new
books, with 2–3 pages each, on top of audit2's 13. The unit is the whole book, so every edition and scan of a held-out
work leaves the training pool.

**What Wikisource can supply** (checked 2026-11-18):
- he.wikisource has 141 Index pages, the same set as the 2026-11-06 inventory, and 74 of them pass the Index gate.
- Already used: audit2 (14 Indexes), `wslines_v1` (9) and line_verify (37 Indexes, exposed). That leaves 33.
- After merging the volumes of one work, and dropping works with another volume already trained (Tanhuma Buber) or in line_verify (Tosefta Zuckermandel), **12 new books with at least one eligible proofread page remain**, about 32 pages. All 12 are E2d3d single-reviewer Indexes:

| Index | Work | Year | Eligible q3/q4 pages | Look |
|---|---|---:|---:|---|
| `ws_index_1720479` | Qav ve-Naqi on Proverbs | 1492 | 11 | rabbinic |
| `ws_index_1734711` | Liqqutei ha-Pardes | 1519 | 3 | rabbinic |
| `ws_index_1734721` | Sefer ha-Tapuach | 1799 | 3 | rabbinic (printed before 1800) |
| `ws_index_1720553` | Ibn Yahya on Ketuvim | 1538 | 2 | rabbinic |
| `ws_index_223203` | Emunot ve-De'ot | 1562 | 2 | rabbinic |
| `ws_index_336509` (+ `336537`, vol. I) | Horev | 1895 | 2 | rabbinic |
| `ws_index_468593` | Safa Ahat le-Kulanu | 1888 | 2 | standard square |
| `ws_index_359833` | Ohev Ger | (inventory says 2012; to check) | 4 | rabbinic |
| `ws_index_332868`, `332872` (+ `332869`–`332871`, `332873`) | Beit ha-Midrash (Jellinek) | 1853–77 | 2 | rabbinic |
| `ws_index_274837` | Or ha-Shem | 1905 | 1 | rabbinic |
| `ws_index_336554` | ha-Shabbat | 1926 | 1 | rabbinic |
| `ws_index_331268` | Shevet Shimon | 1884 | 1 | standard square |

**The gap.** That is 12 books, not 30, and they skew rabbinic. The proposal sent to eval and the lead (their decision):
- Fill the gap with edition-matched books from this pool, each held out whole.
- Their references come from human verification of the aligned edition text, line_verify style, with candidates from the edition text and never from OCR.
- The scout's medium-confidence editions fit best, because a human corrects any edition mismatch: Mishnah Romm, the Midrash Rabbah commentaries, Arukh ha-Shulchan, and ADRN with the minor tractates.
- The two Robarts Rashi-script responsa also fit, and they would give a Rashi stratum.
- None of these is trained yet, so the hold-out costs little supply.

**Decided (eval and lead, 2026-11-18):**
- **Take the 12 now.** With audit2's 13 they are the floor, about 25 books.
  - At most 3 seeded pages per book are scored; Qav ve-Naqi is held out whole but scores 3 pages.
  - Ohev Ger is held out, but is scored only if its print is really P-hist (its 2012 date needs checking).
- **Add 15–18 whole books through option 1.**
  - **Less common works only.** CLEAN bars every edition of a held-out work, so widely printed works such as Mishnah or Midrash Rabbah stay in training.
  - **About a third standard square.**
  - **Rashi-script books as their own stratum,** reported apart.
- **References:** Shay verifies them, line_verify style, in heocr-review, at 2–3 pages per book. The batch is hardest-first, with an agent pre-check flag on each line. A seeded 10% of the verified lines get a blind second human pass. The batch is prepared as an import, but not imported until the lead relays Shay's go.
- **Candidate list v1** (`docs/phist_eval_holdout_candidates_v1.json`, sent to eval for registration): **30 books**, with the work-level rule.
  - A. 13 Wikisource books with proofread pages: the 12 above, plus Ma'ayan Ganim on Job (`ws_index_1735193`, 3 proofread pages whose coverage check is pending).
  - B. 4 Wikisource books with unproofread (quality-1) text only, used as verification candidates: Sefer ha-Nezirim 1910, Ketav Sofer on the Torah 1889, Alim li-Trufa 1778, Mavo Kelali la-Sefarim ha-Hitsonim 1936.
  - C. 2 edition-text books: Leket Yosher (the `rablines_v1` reserve) and Arukh ha-Shulchan Choshen Mishpat (NLI scan mirror of Warsaw 1884; Sefaria text from the Vilna 1923–29 printing).
  - D. 8 PBY editions on IA library scans, standard square, none in any line set. Eretz Yisrael (Gur, 1903) was left out because it is pointed.
  - E. 3 Rashi-script books, a separate stratum: the Rashba responsa (Warsaw 1883), the Chiddushei ha-Rim responsa (Warsaw 1882), and Radak on Genesis (Pressburg 1842, an NLI scan; the Sefaria PD version cites the same NLI record).
  - So 27 new P-hist books plus audit2's 13 makes 40, and the Rashi stratum has 3. About 13 of the 27 are standard square.
  - eval's overlap check must also cover the synthetic training text: htext's PBY corpus feeds hocrsyngen, so group D's works may already appear in synthetic lines.
- **Registration first:** eval registers the final book ids and the work-level rule (which works and volumes are held out together) as a `check_train_overlap` target. **No pool fill starts before that registration.**

## 7. Decontamination

**The hold-out comes first.** The §6a books are picked and registered by eval before any line enters the pool; their works are dropped at work level, every edition and scan.

- **Per list:** `tasks/r9-new-printed/scripts/decontam.py LIST DROP_OUT`. It covers every target of heocr-eval's `check_train_overlap.py`, including the audit2 references and every dev and report set, and prints no text. `--extra` adds P-hist dev sets that are not yet targets.
- **Per work, before alignment:** no edition or Commons file behind an eval, dev, reserved or line_verify Index. These are the scout's exclusion flags, re-checked per batch.
- **The official CLEAN** on the final list is heocr-eval's (`check_train_overlap.py`), as for R8b and R9.

## 8. Decisions (2026-11-18)

Decision 1 is Shay's; decisions 2–6 are heocr-lead's.

1. **IA gate, condition 3: approved by Shay** ("Yes, allow it", Shay Palachy Affek, 2026-11-18, in the lead session).
   - An IA item counts as a known source when its description names the digitizer.
   - Sefaria's own scans count when the Sefaria version is `digitizedBySefaria` and cites the same NLI record.
   - Mirrors of NLI's own scans count when they name the NLI record.
   - Every item has its own `rights_justification`, recording how the source was established. The rest of the IA gate is unchanged.
   - The decision record and the gate change come in a follow-up PR. **Tier B is open once it merges.**
2. **NLI-IIIF free-use lines in `bynli_lines_v3` stay.** The "never the NLI API" rule bars Google-class scans fetched through NLI's API (Route A). NLI's own `public-domain-free-use` scans, fetched from its IIIF service, are what R8b trained on and what HeOCR's public statements describe.
3. **The Rashi localizer: approved.** synth-gen builds it, after confirming the font licence from the upstream notofonts repository. It trains on a pod inside the $150/month budget, and the cost estimate goes to the lead before the run. Its spec is §8a.
4. **Pointed prints** go in as ordinary training lines at their natural weight, if they pass the audit bar. There is no niqqud stratum and no niqqud eval claim this round, because niqqud is not powered.
5. **Tier C: not now.**
6. **No delivery cap.** data-collection delivers every good line. synth-gen applies a seeded per-book cap when it builds the list (lstmtraining has no weights), with 6,100 as the start value, set on P-hist dev. The lead's limit is that no book is above 8% of the round's lines.

**The label-error bar (§3) is approved.** `bynli_lines_v3` is audited per book before the round, and any book that fails is fixed or dropped.

**Training format (agreed with synth-gen):**
- Line sets in the `bynli_lines_v2` shape; labels in NFC, logical order, with niqqud removed. ׳ ״ ־ – — are kept in the labels.
- synth-gen builds the `.lstmf` files locally with the R8b `make_lstmf.py` and uploads them with their `.gt.txt` only, so eval's CLEAN runs on the exact files that train.
- The start model is R7 or the office-print winner, whichever scores better on P-hist dev before training. Stock tessdata_best is reported next to it.

**Order of work:**
1. The eval hold-out list (§6a), registered by eval before any pool fill.
2. The A1 refetch and the per-book audit of `bynli_lines_v3`.
3. A Tur main-column pilot, 20 pages, with the §3 audit.
4. Shulchan Arukh (without OC) and Rif.
5. The Rashi localizer.
6. The Rashi stratum, book by book, each with its 32-line audit.

## 8a. Rashi localizer: spec for synth-gen

- **Purpose:** localization only. Its output finds lines and anchors the edition text; it never becomes a label.
- **Output:** a Tesseract `traineddata` the aligner can load with `--tessdata-dir`. The aligner runs it as `tesseract IMG - -l <name> --psm 3 tsv`, the same call as today.
  - Page segmentation stays Tesseract's own.
  - The model only has to read Rashi letters well enough to anchor 8-grams.
- **Training text:** Sefaria versions whose own licence is PD or CC0, in Rashi-script works. They must be decontaminated against the official targets and the eval hold-out works (§6a). No Rashba or Chiddushei ha-Rim text, because they are pilot and hold-out books.
- **Acceptance test on the pilot book** (`teshuvotharashba00adreuoft`, 142 canvases, `tasks/phist-round/`), unfolded, compared with stock `heb`:
  - at least 60% of the text-bearing canvases `aligned` (stock: 1 of 142; the best fold: 25);
  - at least 15 builder-passing lines per aligned page;
  - a 32-line agent audit with at most 1 word-level error.
  - **The Rashba book is now an eval hold-out (§6a, group E), so the test moves.** It runs on a non-held-out Rashi text: the Rashi columns of one Vilna Shas tractate (IA `Talmud_Bavli_Vilna_images`, "Scanned by Duke University Libraries", which the amended gate accepts), with Sefaria's PD "Vilna Edition" Rashi. The thresholds are the same. The localizer's training text excludes all three group-E works.

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
