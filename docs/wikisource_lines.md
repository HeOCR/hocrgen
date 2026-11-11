# Real line sets from Hebrew Wikisource proofread pages (R8)

`hocrgen.tools.wikisource_lines` cuts line images from the pinned Commons renders of a tranche's Wikisource snapshot
and labels each line with the human page text. It builds the R8 training set `wslines_v1`: rabbinic and dense
small-type print, which the R8 diagnosis (heocr-lead, 2026-11-11) found missing from training.

**Labels are always the Wikisource page text that the coverage alignment placed on a line, never OCR output.** OCR
gives line boxes and picks between candidate word boundaries at a line's edges. Its text is not written anywhere.

Every row is silver training data: `adjudication_status: not_adjudicated`, `reference_eligible: false`, quality 4
included.

## Build

```bash
python -I wsl_runner.py fetch-hires --snapshot SNAP --items ITEMS.txt --out RENDERS_1920   # network, 1 request/s
python -I wsl_runner.py ocr-hires --hires RENDERS_1920 --ocr-cache OCR_HIRES                 # boxes only
python -I wsl_runner.py build OUT --snapshot SNAP \
  --ocr-cache F8B7/ocr_cache --ocr-cache OCR_HIRES --hires RENDERS_1920 \
  --policy C --eval-set E2D3D_AUDIT2/refs/eval_set.json --split-manifest E2D3E/release_split_manifest.json \
  --line-verify LINE_VERIFY_V1/bundle/items.json \
  --facts src/hocrgen/data/wikisource/wikisource_lines_index_facts.json \
  --dev INDEX=name ... --max-lines-per-book N
python -I wsl_runner.py verify OUT
```

The runner puts `src/` on `sys.path` and calls `hocrgen.tools.wikisource_lines.main`. `-I` ignores `PYTHONPATH`,
and the run reads downloaded files.

- `SNAP` is the tranche's `sources/wikisource_he_proofread/snapshot`.
- `fetch-hires` fetches the 1920 px render of each listed page: the pinned 960 px `render_url` with `-960px-`
  replaced by `-1920px-`. It uses the User-Agent `HeOCR-research/0.1 (+https://github.com/HeOCR)`.
- `build` uses a 1920 px render only when it matches the pinned 960 px render, downscaled: a mean absolute difference
  of at most 12 grey levels, the same check as line_verify's hi-res step. Otherwise it cuts from the pinned render.
- `ocr-hires` runs stock Tesseract `heb` (psm 3) on each 1920 px render. It is cached as `<sha256>.heb.psm3.x1.tsv`,
  next to the coverage tool's passes, and is used for boxes only.

The output has the shape of `bynli_lines_v2`, so make_lstmf and the R7 scripts read it unchanged:
- `{train,dev}/<index_key>/<id>.png`, each with a `.gt.txt`;
- `manifest.jsonl`;
- `summary.json`.

## Pages

- **Which pages.** Quality 3 and 4 pages of the snapshot that pass the unchanged `page_exclusion_reasons` gate.
- **Checksums.** The image and the pair text must match their pinned sha256.
- **Pair text.** The pair text is the snapshot's: `wikisource_plain_text.v3` with the reviewed adjustments, so
  unprinted notes are already gone.
- **Partial pages.** A `partial_page` keeps only lines whose box centre lies inside its crop. For a multi-region
  crop, the centre must also lie inside one of its regions.
- **Text the scan does not show.** Lines that touch an `excluded_spans` range are dropped.
- **Pointed pages.** A page whose text carries at least 0.3 niqqud marks per letter is dropped whole.
- **Rights (legal strategy, 2026-11-10; hocrgen#171).** Every page passes
  `hocrgen.fetchers.wikisource_justification.wikisource_page_blocker`, which fails closed:
  - an Index without an accepted Route C (Wikimedia Commons) justification gives no lines
    (`wikisource_rights_justification_missing`);
  - a file where Google is not ruled out and whose hygiene pass did not check the page gives none
    (`google_hygiene_pending`);
  - Google's usage-guidelines page gives none (`excluded_google_front_matter`).

  `dropped_pages` counts these reasons. Each row carries its Index's `rights_justification_id` (`rj:<index_key>:<sha12>`,
  in `docs/wikisource_rights_justifications.json`) and the page's `google_watermark_bbox` when it has one. A line whose
  box overlaps that box (`[x, y, w, h]` fractions of the page render) is dropped (`google_watermark_overlap`), as
  #165 does for Internet Archive scans.

## Lines

1. **Alignment.** The coverage tool's `align_page` runs on each cached Tesseract pass:
   - the coverage passes on the 2× upscale of the 960 px render (`psm3-plain`, `psm4-plain`, `psm3-flattened`);
   - `hires-psm3` on the 1920 px render.

   The pass whose aligned lines cover the most of the text is used. Only `aligned` lines count (interpolated lines
   do not), with a trigram share of at least `--min-score` (0.5; the coverage tool aligns from 0.30).
2. **Span.** The line's span in the normalised text is mapped back to the page text. It is snapped to word
   boundaries (or after a hyphen or maqaf), within two words of each edge and never across a line break. The span
   kept is the one whose letters best match the line's OCR letters.
3. **Gates** (the drop reason is in brackets). A line is dropped when it:
   - still matches its OCR below 0.7 (`label_disagrees_with_line_ocr`);
   - has under 8 letters and digits (`short_line`);
   - is taller than 1.6× the page's median aligned line (`taller_than_one_line`);
   - lies outside the crop (`outside_transcribed_crop`);
   - crosses a paragraph (`span_crosses_paragraph`);
   - carries a `[n]` footnote mark (`footnote_marker`);
   - touches an excluded span (`excluded_span_on_scan`);
   - carries cantillation or at least 0.1 niqqud marks per letter (`pointed_line`);
   - has characters outside the `bynli_lines_v2` repertoire (`outside_repertoire`).
4. **Order.** The lines kept on a page must follow the text in OCR reading order: the longest increasing run is kept
   (`out_of_text_order`). This drops a running head or stray short line that matched a word elsewhere in the text.
5. **Overlap.** Two lines may not claim the same text (`span_overlaps_another_line`).
6. **Labels.**
   - NFC, in logical order.
   - Niqqud and cantillation are removed. Maqaf ־, geresh ׳, gershayim ״ and the dashes – — are kept.
   - Editors' ASCII `"` and `'` stay as they typed them; the stand-in survey leaves them unmapped.
   - The `bynli_lines_v2` folds apply (`…` to `...`, `„` to `"`, soft hyphen removed), and whitespace is collapsed.
7. **Cap.** `--max-lines-per-book` keeps N lines per Index, chosen by the sha256 of the line id. Dev Indexes are
   uncapped unless `--cap-dev` is set.

## Row fields

These come on top of the `bynli_lines_v2` core (`id`, `split`, `book`, `record_id`, `text`, `alignment_score`,
`ocr_similarity`, `image_scale`, `bbox_image`, `crop_box_image`, `image`, `image_sha256`, `stratum`, `ocr_placer`,
`alignment`, `page_ocr`):

- **Location:** `index_key`, `page`, `page_title`, `page_revision_id`, `source_item_id`, `bbox_render` (pinned 960 px
  render pixels), `text_span`.
- **Strata:**
  - `stratum: unpointed` (pointed pages are dropped);
  - `script`: `square` or `rashi`;
  - `genre` and `rabbinic`, from `src/hocrgen/data/wikisource/wikisource_lines_index_facts.json`.
- **Scan:**
  - `scan_source: wikimedia_commons`;
  - `source_class: wikisource_proofread_commons_scan`;
  - `scan_basis`: the Commons file's `scan_source_origin` (`hebrewbooks`, `internet_archive`,
    `national_library_of_israel`, …);
  - `scan_digitized_by_google`;
  - `commons_file`, `commons_file_sha1`, `commons_description_url`, `commons_page`;
  - `image_source`, with its sha256 and the hi-res check difference.
- **Rights:**
  - `text_licence: CC BY-SA 4.0`, `text_licence_url`;
  - `attribution`: "Hebrew Wikisource contributors" plus the pinned page permalink (`attribution_url`);
  - `rights_justification_id` (the Index's Route C record) and `google_watermark_bbox` (null on these pages).
- **Attestation:** `attestation` (`wikisource_quality3_single_proofreader` or `wikisource_quality4_validated`),
  `adjudication_status: not_adjudicated`, `reference_eligible: false`.

`summary.json` adds:
- lines by Index and split, by stratum and by script;
- genres and drop reasons (for lines and for pages, by Index);
- the exclusion policy, with each held-out Index and its rules and the dropped page ids;
- the reserve;
- rabbinic counts (pool, after exclusions, in the output);
- the manifest sha256;
- a `release_notice`: CC BY-SA 4.0, share-alike, the page permalinks and the Commons file credits.

## Script

`script` is the dominant script of the line, `square` or `rashi`. It comes from the facts file, set per Index, with
page and line overrides from an agent check of the line crops and renders. That check never looks at an E2d3d or
audit2 page image. Unlisted lines are `square`.

Stock Tesseract reads Rashi script poorly, so the OCR-similarity gate drops most Rashi lines. The Rashi stratum is
therefore small.

## Exclusion policy

The policy is a tool input (`--policy`, `EXCLUSION_POLICIES`). Each rule is derived from its input file, so a policy
re-derives:

| Rule | Unit | From |
|---|---|---|
| `audit2` | Index | the E2d3d eval set's adjudicated stratum (the 38 audit2 pages, 14 Indexes) |
| `release_test` | Index | the release split manifest's `test` split |
| `related_work_of_audit2` | Index | another volume or edition of an audit2 work: the same title core (`title_core`: the first two content words, with volume words, `ספר`, numerals and a leading article dropped) |
| `line_verify_index` | Index | any page in a line_verify batch (policy A only) |
| `line_verify_index_in_heldout_split` | Index | a line_verify Index in the release `validation` or `test` split |
| `line_verify_page` | page | a page in a line_verify batch: its lines are future line references |
| `eval_set_page` | page | a page of the E2d3d eval set (adjudicated or single-reviewer) |
| `manual` | Index | `--hold-out INDEX=reason` |

**`wslines_v1` uses policy C** (heocr-lead, 2026-11-11):
- held out whole: `audit2`, `release_test`, `related_work_of_audit2` and `line_verify_index_in_heldout_split`;
- dropped page by page: `line_verify_page` and `eval_set_page`.

Policy A, which holds out every line_verify Index whole, leaves 29 pages in 11 Indexes. Only 10 pages in 2 Indexes
remain once the E2d3d pages are also dropped: line_verify_v1 drew on every quality-3 page of the tranche.

## Reserved Indexes

**The reserve is waived for `wslines_v1`** (heocr-lead, 2026-11-11). The audit2 and release-test Indexes, held out
whole, already hold most of Hebrew Wikisource's proofread rabbinic print as evaluation. Reserving one more rabbinic
Index from the small remainder would leave training almost no rabbinic lines.

**Obligation.** The first 5(b) batch (rabbinic open texts aligned to public-domain scans) must reserve one dense,
abbreviation-heavy rabbinic edition. It must be held out as a whole work, in neither train nor dev, as the future
rabbinic eval or line_verify source. Record it here when it is chosen. `--reserve INDEX=reason` keeps an Index out of
both splits, and `verify` fails on any row from it.

**Chosen (2026-11-11):** `rablines_v1` reserves *Leket Yosher* (Freimann, Berlin 1903–04; IA
`seferleetyosher00socgoog`). See "Reserved editions" in [`benyehuda_nli_lines.md`](./benyehuda_nli_lines.md).

## `wslines_v1` (2026-11-11)

Built on 2026-11-11 on top of hocrgen#171 at `31038fc` (the rights justifications, with the commentary, reprint and
floruit rules). The inputs are tranche `e2d3e_real_tranche_v5` (Wikisource snapshot: 58 Indexes, 1,452 pages), the
release split manifest, the E2d3d audit2 eval set and `line_verify_v1`, under policy C.

The output is in `tasks/s16c-glyph-scale/outputs/lines/wslines_v1/`, manifest sha256
`25ed7ff97d6cd1d05774de6377d4481483981ebcdc7460472d041118df988f99`.
- `--max-lines-per-book 3000` caps Milḥamot ha-Shem (964 lines over the cap); dev is uncapped.
- Every line is cut from a checked 1920 px render.

**Superseded build.** The earlier build (manifest `c745bb00…`, on #171's first commit) is kept as
`outputs/lines/superseded_wslines_v1_c745bb00/`, because heocr-lead's R8a run used it. Against it:
- its 3,812 train rows are the same rows, with identical text, boxes, images and `.gt.txt` files. Only
  `rights_justification_id` differs: each Index keeps its `rj:<index_key>:` prefix, and the hash suffix changed
  because #171 regenerated the records;
- its 142 Mishneh Torah dev lines are gone: #171's commentary rule rejects every Mishneh Torah volume (1711486).

**Exclusions.**
- **Held out whole: 33 Indexes, 928 pages.**
  - the 14 audit2 Indexes;
  - the release `test` Indexes;
  - three other volumes of audit2 works: Hyman II (328114), and *Dorot ha-Rishonim* II (398671) and III (458756);
  - the line_verify Indexes of the release validation split: 288183, 327706, 328435, 331308, 336536 and 378494.
    The validation-split line_verify Indexes that are also audit2, test or another volume (256394, 398671, 458756)
    are counted under those rules.
- **Dropped page by page: 186 line_verify pages and 46 E2d3d eval pages.**
- **After exclusions: 292 pages in 13 Indexes.**

**Pages.**
- **Blocked by `wikisource_page_blocker`:** 9 pages, all of Mishneh Torah 1711486 that remain after the exclusions
  (`wikisource_rights_justification_missing`, the commentary rule). Its other 6 tranche pages were already dropped as
  line_verify or E2d3d pages. Falaquera 370788 (the reprint rule) is a release-test Index, held out anyway; neither
  build has a row from it.
- 63 pointed pages dropped (the Tanakh and *Siddur Torah Ohr*, among others).
- 25 pages give no line.
- **195 pages in 9 Indexes give lines.** Every row carries its `rights_justification_id`.

| Split | Index | Lines | Pages | Script | Rabbinic |
|---|---|---:|---:|---|---|
| dev | 1720479 *Qav ve-Naqi* (Lisbon 1492) | 0 | 0 | | yes |
| dev | 1734574 *Sippurei Ma'asiyot* (Lemberg 1902) | 257 | 28 | 242 square, 15 rashi | no |
| train | 286280 Gersonides, *Milḥamot ha-Shem* | 3,000 (capped) | 119 | square | yes |
| train | 336538 Hirsch, *Ḥorev* I | 481 | 16 | square | yes |
| train | 376147 Reines, *Sefer ha-Arakhim* | 165 | 5 | square | yes |
| train | 332590 Buber, *Midrash Tanḥuma* | 126 | 20 | square | yes |
| train | 1735654 Heidenheim, *Mishpetei ha-Te'amim* | 19 | 2 | square | no |
| train | 332490 Buber, *Sifrei de-Agadeta* | 11 | 1 | square | yes |
| train | 336448 Hirsch, *Iggerot Tzafon* | 7 | 3 | square | yes |
| train | 288180 *Be-Mamlekhet Kuzar* (NLI-origin scan) | 3 | 1 | square | no |

Totals: 3,812 train lines and 257 dev lines. Quality 3 gives 4,058 lines and quality 4 gives 11.

**Rabbinic counts.**

| | Indexes | Pages |
|---|---:|---:|
| Pool | 36 | 843 |
| After exclusions | 8 | 182 |
| In the output | 6 | 164 |

Rabbinic lines: 3,790 in train and 0 in dev.

**Dev.**
- **Qav ve-Naqi gives no line.** It stays in dev as decided, but stock Tesseract cannot read its Sephardic
  semi-cursive: the aligned lines' trigram shares are 0.19–0.65, and no line passes the gates.
- ***Sippurei Ma'asiyot* is the prose dev Index.** It is the only non-rabbinic narrative Index with lines left under
  policy C, square type and unpointed. Prose is plentiful in `bynli_lines_v2`, so holding it out costs training
  nothing scarce.
- **`wslines_v1` has no rabbinic dev line.** R8's rabbinic dev set comes from `rablines_v1` (heocr-lead,
  2026-11-11). `summary.json` records this under `rabbinic_dev`, from `--rabbinic-dev-source rablines_v1`.

**Drop reasons (lines):**

| Reason | Lines |
|---|---:|
| `below_min_score` | 1,060 |
| `outside_repertoire` | 172 |
| `span_crosses_paragraph` | 94 |
| `box_spans_two_rows` | 42 |
| `short_line` | 25 |
| `pointed_line` | 22 |
| `line_length_disagrees_with_ocr` | 16 |
| `out_of_text_order` | 16 |
| `taller_than_one_line` | 13 |
| `span_overlaps_another_line` | 11 |
| `label_disagrees_with_line_ocr` | 2 |
| `footnote_marker` | 1 |
| `outside_transcribed_crop` | 1 |

Most of `below_min_score` is print stock Tesseract misreads: Qav ve-Naqi, and Tanḥuma's notes (which are also
untranscribed on most of its pages).

**Verification.** `verify` and an independent check against the source files both pass:
- no row from a held-out Index, from 1711486 or 370788, from a line_verify page or from an E2d3d page;
- `wikisource_derivation_blocker` passes every row;
- no niqqud in a label;
- every row carries its licence and attribution;
- every image sha256 is non-null and matches its file.

Tests: `tests/test_wikisource_lines.py` (network- and engine-free; synthetic snapshot and OCR cache).
