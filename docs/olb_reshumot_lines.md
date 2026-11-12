# Scanned Reshumot lines labelled with OLB text (`olbreshumotlines_v1`)

`hocrgen.tools.olb_reshumot_lines` cuts line images from the **scanned** booklets of ספר החוקים and קובץ התקנות
(1948 to mid-2005: ספר החוקים 1–1975, קובץ התקנות 1–6394) and labels each with the same-wording text of Hebrew
Wikisource's ספר החוקים הפתוח (OLB). It is the mid-century modern-print line set (decision 0018: new printed).

**The label is OLB text, and only where OCR evidence confirms that it equals the print.** The publisher's OCR layer
(Imagestore for ספר החוקים, ABBYY for קובץ התקנות) and stock Tesseract only *locate* lines and give evidence. Their
text is never a label and is never written out. Every row is `label_source: wikisource_olb_same_wording`,
`capture: scan`, `adjudication_status: not_adjudicated`, `reference_eligible: false`: silver training data, never an
evaluation reference.

## Pipeline

```bash
# OLB text (Wikisource API, 1 request/s, 20 titles per POST; pins revision id and content sha256)
PYTHONPATH=src python -m hocrgen.tools.olb_reshumot_lines olb-fetch --titles olb_titles.jsonl --out OLB
PYTHONPATH=src python -m hocrgen.tools.olb_reshumot_lines olb-index OLB
# the plan: OLB candidates per non_eval booklet of heocr-eval's midcentury split
PYTHONPATH=src python -m hocrgen.tools.olb_reshumot_lines plan --units units_enumerated.json \
  --split midcentury_unit_split_v0.json --split-sha256 SHA --olb OLB --out plan.json
# downloads (gov.il API, 1 request / 1.2 s, User-Agent "HeOCR-research/0.1 (+https://github.com/HeOCR)")
python -I olb_runner.py capture --plan plan.json --cache CACHE --series sefer_hachukim kovetz_hatakanot
# the build reads downloads: run it through a runner that puts src/ on sys.path itself, under python -I
python -I olb_runner.py build OUT --plan plan.json --split ... --split-sha256 SHA \
  --tasks TASKS --olb OLB --cache CACHE --shuffle-seed SEED --workers 8 --signature "<operator signature>"
python -I olb_runner.py verify OUT --split ... --split-sha256 SHA
```

Capture can run as several `--shard i/n` processes on one cache: they share one gap file (`throttle.json`), so the
host still sees at most one request per 1.2 s. A PDF is written atomically and counts as captured only while its
sha256 equals the one `capture_log.jsonl` pins; `build` reads only such files. (On a Python whose bundled CA store
lacks the gov.il chain, point `SSL_CERT_FILE` at a certifi bundle; verification stays on.)

`units_enumerated.json` is data-collection's enumeration of every scanned booklet (gov.il Reshumot search API, with
its quirks handled: Warn retries, the 200-result cap sliced by booklet-number prefix, unstable order unioned over
two passes, missing numbers probed). heocr-eval issues `midcentury_unit_split_v0.json` from it.

## Guards (all fail closed)

1. **Held-out booklets.** The source is `reshumot_scanned`; unit ids are `reshumot_scanned:<series>_<number>` and
   page ids `reshumot_scanned_<series>_<number>__p0001` (agreed with heocr-eval; never the bare born-digital
   `<series>_<n>` shape). Only booklets that heocr-eval's midcentury split lists `non_eval` are planned, fetched or
   read for train. Test booklets are never fetched. Dev booklets are fetched only by `capture-dev`, for the dev set,
   and their crops are never viewed. `refuse_eval_reserved_training_input` runs against the
   packaged registry on the selected booklets before anything is read and on the rows before anything is written,
   and `verify` runs it again. The registry must govern `reshumot_scanned` (heocr-eval's `pmod_unit_split_v2` puts
   every enumerated booklet in it); `training_registry` fails closed before that sync. The split file is pinned by
   sha256. Any input path (plan, split, OLB, cache, a PDF,
   the tasks directory) under `tasks/modern-s6-scout/midcentury_test/`, where the lead keeps eval's test-unit PDFs,
   is refused (`refuse_forbidden_path`, resolved, so symlinks and `..` do not escape).
2. **The law's version.** An OLB page is a candidate for a booklet only through one of its `ח:תיבה` citations that
   points into it: the same series (`ס״ח`, `ק״ת`), the same Hebrew year, and a printed page inside the booklet's page
   range (volumes are paginated per Hebrew year; the range is estimated from the API page counts, with a slack of 12
   pages). A page whose header says `חוק קודם` / `חוק חדש` holds the *new* law: its "חוק קודם" citations never make it
   a candidate, so a same-titled successor law is never matched to the old booklet (the scout's booklet 435 case).
   Amendment marks are not trusted either way: the per-line match decides.
3. **Per-line exact match** (`accept_line`), under the comparison normaliser `olb_print_compare.v1` (`compare_key`):
   NFC, niqqud removed; quote, geresh, dash, maqaf and bracket glyphs folded; all spacing removed; the order of digit
   groups ignored (ABBYY writes multi-group numbers in visual order). OLB editorial notes (`ח:הערה`: "(בוטל)",
   "(נמחקה)", footnote references) are stripped when OLB is parsed. A located OLB word span is kept only when:
   - `both_exact` / `layer_exact` / `tesseract_exact`: a reading equals the span; or
   - `char_consensus` (only when both readings exist, each within CER 0.25): every character of the span is read by
     at least one reading; no deviation from the span is shared by both readings; neither reading inserts a digit or
     `*` (a footnote marker the other missed); the two readings never both insert something at the same place
     (whatever they read there); and neither reads anything beyond the span's ends.
   - An exact reading is overruled (`other_reading_sees_more`) when the other reading sees two or more characters,
     one a letter, beyond the span's ends: the crop then holds print the label lacks.

   A page without a text layer (some early קובץ התקנות files) has a single Tesseract reading, which must be exact.
4. **Footnote markers.** A marker the print adds (`*`, a lone 1–2 digit number, digits glued to a word's end) is
   stripped from the comparison, since OLB has no footnotes; the line is then dropped (`footnote_marker_in_print`)
   unless `--keep-footnote-lines` is given, because its label would lack a printed glyph.
5. **Niqqud.** A span with niqqud or cantillation is dropped (`pointed`).
6. **Eval 6-gram rule.** A line sharing a word 6-gram (Hebrew-letter words, logical order) with the committed text of
   an eval booklet of the P-mod split or a wave-1 page is dropped (`eval_ngram_overlap`); the count is in
   `summary.json`. The split defaults to the one hocrgen's eval-reserved registry is synced from
   (`registry_pmod_split`), so it cannot lag; a `--pmod-split` given by hand must be that file. The pool fails
   closed when the split names born-digital eval booklets but none of their pages is read.

## Lines

- **Location.** Lines come from the OCR layer (`pdftotext -bbox-layout`; words re-ordered right to left, which also
  undoes Imagestore's reversed `-raw` order), or from stock Tesseract (`heb`, `--psm 4`) on pages without a layer.
  The reading is located in the booklet's candidate OLB paragraphs by a trigram diagonal vote, a semi-global
  alignment in a window, and the word boundaries (one word either way) that minimise the edit distance; a line is
  located only within CER 0.35.
- **Visual-order layers.** Imagestore stores each word's characters in visual order; a layer whose Hebrew final
  letters sit at word starts is turned to logical order word by word (numbers kept whole).
- **Fitting to the ink.** The layer's word boxes come from invisible text set in another font: they sit low and
  stop short of a line's first or last letter. Every box is moved to its ink band (the run of inked rows through
  its centre, never past a neighbour's centre) and widened to the ink past its ends, up to the first blank gap of
  0.4 line heights. Fragments of one printed row are then joined (gap at most 0.9 line heights). A line whose ink
  runs into a neighbouring line with no blank row between them is dropped (`touches_neighbour_line`).
- **Second reading.** Stock Tesseract (`heb`, `--psm 7`) reads each located line's crop.
- **Page images.** `pdfimages`: the page's largest image (CCITT G4 at 400 dpi for ספר החוקים, 300 dpi for its 2015
  rescans; JBIG2 at 300 dpi for קובץ התקנות), skipping the low-resolution JPX overlays. Crops are cut at the scan's
  native resolution, from the line box padded by 0.22 of its height and clipped at the neighbouring lines.
- **Label.** The OLB span, with quote, geresh and dash glyphs folded to `"` `'` `-` (`olb_label_fold.v1`: the print's
  glyph shapes vary by era, so the label does not claim one); words and punctuation are OLB's. The raw span is kept
  in `olb_text`.
- **Drops.** `no_olb_span`, `ocr_disagrees_with_olb`, `single_reading_not_exact`, `other_reading_sees_more`,
  `footnote_marker_in_print`, `pointed`, `too_short` (fewer than 8 letters or digits, or one word), `merged_rows` (a
  box over 1.8 times the page's median line height), `touches_neighbour_line`, `eval_ngram_overlap`, `capped`.
- **Bias.** OCR agreement favours lines the OCR reads well. Every row records `match_evidence` (tier, the CER of
  each reading against the label, the stripped footnote markers, the locating distance), so the bias is measurable.

## Split and output

- **Validation split.** `build` keeps one non_eval booklet per (series, midcentury decade) stratum as its `dev`
  split (the first by `sha256(unit_id)`): a training-validation split, not an evaluation set.
- **Dev set (`capture-dev`, `dev-set`).** `olbreshumotlines_v1_dev` holds the Reshumot units that heocr-eval's
  `midcentury_unit_split_v0` reserves as `dev`; `dev-set` accepts exactly those and refuses test, non_eval and
  unlisted units. It is a **silver dev set (for decisions), not an eval reference; never report it as a test score**
  (every row `reference_eligible: false`). Lines are kept by the **layer-only rule** (`layer_exact_only.v1`): the
  publisher's text layer equals the OLB span, whatever Tesseract reads; each row records `tesseract_tier`
  (`exact` / `not_exact`) as a stratum, never as a filter. Scoring (the lead's decision): every dev line is scored;
  the `exact` and `not_exact` strata are reported separately; if the exact-only and all-lines verdicts differ in sign,
  the comparison is unresolved. The set's `README.md` states the selection bias and gives per-unit counts.
  ```bash
  python -I olb_runner.py capture-dev --units units_enumerated.json --split ... --split-sha256 SHA --dev-cache DEV_CACHE
  python -I olb_runner.py dev-set OUT_DEV --plan plan_dev.json --split ... --split-sha256 SHA --olb OLB \
    --dev-cache DEV_CACHE --units units_enumerated.json --shuffle-seed SEED --train OUT
  python -I olb_runner.py dev-overlap OUT --dev OUT_DEV
  ```
- **Retired dev units and the replacement queue (`fill-dev-queue`).** From `midcentury_unit_split_v1` on, the split
  file has the parts `test`, `dev`, `non_eval`, `dev_retired`, `dev_queue` (per stratum, each row with heocr-eval's
  `hash_rank`) and `dev_queue_fallback` (per stratum, an overlay on `non_eval` units; never read here). Retired units
  stay held out and leave the next dev version. `fill-dev-queue` walks one stratum's `dev_queue` in `hash_rank`
  order: it captures each unit (`capture-dev`'s throttle and User-Agent; `--reuse unit_id=path` for a PDF already
  captured), cuts it by the layer-only rule into a scratch directory that is deleted (no cap, no Tesseract gate,
  crops never kept or viewed), and fills a slot with the first units that keep at least one line. It stops when the
  slots are full and logs every unit tried (hash rank, pages, text-layer pages, layer-exact lines, filled or empty).
  When the queue runs out first, the log says `complete: false` and the command exits 2 (the caller then asks
  heocr-eval; the fallback queue is not used). `dev-set --fill-log LOG` (repeatable; each log complete, same split
  sha256) adds the filled units. The dev-set guard accepts `dev` units and the logged `dev_queue` units and refuses
  test, non_eval, `dev_retired` and unlisted units. Every row and the units file carry `split_source`
  (`<split>/dev`, or `<split>/dev_queue` with the queue's `hash_rank`).
  ```bash
  python -I olb_runner.py fill-dev-queue --split midcentury_unit_split_v1.json --split-sha256 SHA \
    --units units_enumerated.json --olb OLB --plan plan_dev.json --dev-cache DEV_CACHE \
    --stratum 'kovetz_hatakanot|1948-59' --slots 4 --log walk_1948_59.json
  python -I olb_runner.py dev-set OUT_DEV --fill-log walk_1948_59.json ... --units-doc olb_dev_units_v1.json
  ```
- **Yield.** `summary.json` reports per (series, decade) the candidate lines (located lines with an OLB span that
  reached the gate), the kept lines and the kept share, per tier (`yield`). Thin older decades are reported as they
  are; the match criteria are never relaxed to raise yield.
- **Checking.** The sample check of the set is an *agent audit (data-collection subagent)*, not human review.

## olbreshumotlines_v1.1_dev

The 55 remaining `dev` units of `midcentury_unit_split_v1` (sha256 `f9a49238…`) plus 5 `dev_queue` units in place of
the retired 215, 491, 499, 643 (kovetz_hatakanot|1948-59) and 3835 (kovetz_hatakanot|1970s): 592, 695, 648 and 555
(hash ranks 3, 6, 8, 10; ranks 0, 1, 2, 4, 5 and 9 have no text layer and rank 7 no layer-exact line) and 2719 (hash
rank 0). 3,325 lines from 60 units; the 3,254 lines of the kept units are byte-identical to `olbreshumotlines_v1_dev`,
which stays as it is (R8b was scored on it). The walk logs are in `olb_dev_units_v1.json` and in [`olb_reshumot_dev_v1.1_walks.json`](./olb_reshumot_dev_v1.1_walks.json). Two lines of the released
`olbreshumotlines_v1` train set share a word 6-gram with the new rows (enactment formulae); v1 is not rebuilt for it.

## olbreshumotlines_v1: the release recipe

1. `build` over every captured non_eval booklet (all four evidence tiers are cut).
2. `capture-dev` + `dev-set`: `olbreshumotlines_v1_dev` from the 60 Reshumot dev units of heocr-eval's
   `midcentury_unit_split_v0` (layer-only rule, no cap, crops never viewed; `olb_dev_units_v0.json`).
3. `dev-overlap`: train lines sharing a word 6-gram with a dev line leave the set.
4. Agent audit with escalation (the lead's rule: a tier whose Wilson 95% upper bound exceeds 2% gets 200 more lines;
   still over, it leaves v1), then `drop-tiers`. Round 1 (600 lines, 150 per tier) found 10/150 errors in
   `layer_exact` and in `char_consensus`: both left. Round 2 (+200 per remaining tier): `both_exact` 1/350
   (0.3%, upper 1.6%), `tesseract_exact` 3/350 (0.9%, upper 2.5%): `tesseract_exact` left. **v1 keeps
   `both_exact` only.** Every verdict is in [`olb_reshumot_lines_audit_v1.jsonl`](./olb_reshumot_lines_audit_v1.jsonl)
   (line id, unit, tier, stratum, verdict, error class; no label text).
5. `olb-reshumot/scripts/drop_eval_overlap.py`: lines sharing a word 6-gram with any target of heocr-eval's
   `check_train_overlap.py` leave the set; then `check_train_overlap.py` runs last on the final lists.

Error classes the audit found (all tiers): a mark or word beyond the span at the crop's edge (the layer box widened
to ink that belongs to a neighbour), print spacing in `8 (2)`-style references that OLB writes `8(2)`, a missed
quote or comma, a superscript footnote marker the readings missed, a cut first letter in letter-spaced signatures.
- **Shuffle.** `manifest.jsonl`, `train_list.txt` and `dev_list.txt` are shuffled with `--shuffle-seed` (recorded in
  `summary.json`), because `lstmtraining` does not shuffle.
- **Shape.** `bynli_lines_v2`: `{train,dev}/<series>_<number>/<id>.png` with a `.gt.txt` each, `manifest.jsonl` and
  `summary.json`.
- **Rows** carry the booklet (`unit_id`, `series`, `booklet_number`, `hebrew_year`, `year`, `decade`, `page`), the
  label and `olb_text`, `match_evidence`, the tier-A flags, the OLB page title, revision id and timestamp, the block
  and word span, the geometry, the image sha256 and the licences.

## Licences

- **Images:** PD-IL (Copyright Act 2007 section 6, laws and regulations). Status outside Israel is not asserted.
- **Labels:** OLB text, CC BY-SA 4.0, attributed to the Hebrew Wikisource contributors (ספר החוקים הפתוח). Every row
  names its page and pinned revision (`attribution_url`, an `oldid` permalink); `summary.json` lists them all
  (`olb_page_permalinks`). Weights trained on it follow heocr-engine decision 0016 (Apache-2.0, credit the text, no
  word list built from it); a published copy of the labels carries CC BY-SA 4.0.
