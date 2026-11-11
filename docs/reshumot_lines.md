# Printed-modern training lines from Reshumot (decision 0018)

`hocrgen.tools.reshumot_lines` cuts one image per verified line from the 150 dpi renders of a tranche's Reshumot
snapshot and labels it with the publisher's glyph-layer text of that line (`pdf_glyph_geometry_logical.v1`, F8e2 and
F8e3 in [`real_source_release_contract.md`](./real_source_release_contract.md)). It builds `reshumotlines_v1`, the
first new-printed (modern typography) real line set, and `reshumotlines_v2`, which adds the born-digital booklets of
2005 (see [v2](#v2-the-2005-born-digital-booklets)).

**The glyph layer is a silver training label, never an evaluation reference.** Every row records
`label_source: publisher_glyph_layer`, `capture: rendered`, `adjudication_status: not_adjudicated` and
`reference_eligible: false`. It is accepted only for truly born-digital PDFs: a scan with an OCR text layer is refused
whole.

## Build

```bash
python -I rl_runner.py build OUT --snapshot SNAP --pdf-cache CACHE/reshumot/pdf --page-layers LAYERS \
  --workers 6 --created-at YYYY-MM-DD --signature "<operator signature>"
python -I rl_runner.py verify OUT
```

The runner puts `src/` on `sys.path` and calls `hocrgen.tools.reshumot_lines.main`. `-I` ignores `PYTHONPATH`, and the
run reads downloaded files.

- `SNAP` is the tranche's `sources/reshumot_born_digital/snapshot` (`entries.jsonl`, `extraction/`, `text/`, `assets/`,
  `glyph_outlines.json`).
- `CACHE/reshumot/pdf` holds the captured PDFs (`<series>_<number>.pdf`). Each must match the sha256 its entries pin.
- `LAYERS` holds the glyph layer of every PDF page (`<series>_<number>__pNNNN.json[.gz]`, as F8e2 extracted them),
  not only the admitted pages. Without it, the tool extracts them with `hocrgen.parsers.pdf_glyphs` (the `pdf` extra).
  A layer of an admitted page must equal the tranche's committed extraction.
- Poppler's `pdfinfo`, `pdffonts` and `pdfimages` read the PDF metadata. Nothing is fetched.
- `--snapshot`, `--pdf-cache` and `--page-layers` may be repeated: the snapshots are read as one (a booklet may be in
  only one of them), and caches and layer folders are searched in order.
- `--keep-dev-from PRIOR/summary.json` keeps an earlier build's dev booklets (see [Lines and split](#lines-and-split)).
- `--exclude-6grams POOL` drops lines that share a word 6-gram with eval text (guard 7).
- `--shuffle-seed` (default `reshumotlines-v2`) sets the order of every list output (see [Output](#output)).

## Guards (all fail closed)

1. **Eval reserve (decision 0017).** Only booklets that `config/eval_reserved_units.yaml` lists as `non_eval` are read.
   Eval and unassigned booklets are counted from `entries.jsonl` metadata and never opened.
   `refuse_eval_reserved_training_input` runs on the selected pages before anything is read, and on the line rows
   before anything is written. `verify` runs it again on the manifest. Dev comes from non-eval booklets only.
2. **Born digital, per booklet** (`born_digital_check`, recorded under `booklets.<unit>.born_digital`). The booklet is
   refused when:
   - a Creator, Producer, XMP `CreatorTool` / `Producer` or history `softwareAgent` names OCR or scanning software
     (`ocr_producer`: ABBYY, FineReader, Tesseract, OmniPage, Paper Capture, ClearScan, OCRmyPDF, ReadIRIS, Nuance,
     Kofax, "scan", "capture", ...);
   - a page has text in an invisible render mode (3 or 7) over a page image covering at least half the page
     (`invisible_text_over_page_image`);
   - a page has invisible text and no visible text (`image_only_page_under_invisible_text`);
   - a page image covers 80% of a page or more, by its placement in the glyph layer or by `pdfimages -list` size and
     resolution (`full_page_image`);
   - it has no embedded fonts, a page's glyph layer is missing, or the PDF is not the pinned one.
3. **Page gate.** Each page passes the unchanged tranche gate (`reshumot_entry_exclusion_reasons`). Its text is
   re-derived (`convert_glyph_layer`, `page_verdict`) and must equal the committed text line for line.
4. **Glyphs.** Lines with a private-use, replacement, unassigned or `(cid:N)` code point, or a glyph issue, are dropped
   (`unmapped_or_private_glyph`).
5. **Niqqud.** A line with any niqqud or cantillation mark is dropped (`pointed`). Labels have niqqud stripped, which
   does nothing to the kept lines. Geresh, gershayim, maqaf and dashes stay as printed, with no other folds.
6. **Bidi and digit order.** heocr-eval's tier-A rules are vendored unchanged from
   `tasks/eval-domains/scripts/reshumot_candidates.py`, and their sha256 is pinned in `TIER_A_ORIGIN`. A local test
   compares the two when that file is present. A line flagged `compound_number`, `latin` or
   `bracket_order_or_balance` is kept only when `line_order_verified` holds:
   - the entry is `reading_order_verified: within_line`;
   - every segment round-trips through the forward bidi algorithm, with no segment issue and no ambiguous Latin-number
     join;
   - a line of several segments (a label joined to its line) also round-trips as a whole.

   Otherwise the line is dropped (`bidi_or_digit_order_unverified`). Each row records its tier-A flags.
7. **Eval text quoted in training lines** (heocr-eval's `line_set_condition` in `pmod_unit_split_v2.json`). Amendments
   quote the text they amend, so a line that shares any word 6-gram with a v1 eval booklet or a wave-1 page is dropped
   (`shares_word_6gram_with_eval_text`). The rule is heocr-eval's `tasks/eval-domains/scripts/ngram_overlap.py`
   (Hebrew-letter words in logical order), vendored with its sha256 pinned in `NGRAM_ORIGIN`; a local test compares
   the two. The pool (`heocr_eval_word_ngram_pool.v1`) holds only sha256 digests of the eval 6-grams, so no eval text
   reaches the tool or its output. `summary.json` records the pool, its sha256 and the count
   (`eval_text_overlap_filter`).

## Lines and split

- **Lines.** The kept units of the page verdict, in the committed text's order (`line_index` is the line number in
  `text/<entry>.txt`).
- **Crop.** The image is the line's glyph ink box plus 3 pt. Every pixel outside the line's own glyph boxes (plus 1.5 px)
  is set to white (`crop_method: unit_glyph_ink_mask.v1`), so the image shows only the labelled glyphs.
- **Line drops.** A line is dropped (`ink_overlaps_other_ink`) when its glyph boxes touch another line's glyphs, a page
  image, a rule or a coloured fill. A line without a letter or digit is dropped (`no_letters_or_digits`).
- **Split, by whole booklet.** Dev takes one booklet per (series, decade) stratum of the non-eval booklets: the first by
  `sha256(unit_id)` that passes the born-digital check and gives at least one line. Train takes every other passing
  booklet. `summary.json` records the method, the ranking and the picks under `dev_selection`. With
  `--keep-dev-from`, an earlier build's picks are kept first in their stratum while they still pass and give lines, so
  adding booklets never moves an earlier dev booklet (`dev_selection.pinned`).
- **Cap.** `--max-lines-per-booklet` (default 6100) caps each booklet, keeping lines by sha256 of the line id.
- **Node hint.** Every row and `tagger_units.json` entry carries `proposed_node_hint: new_printed`. It is a hint only;
  the maintainer's tagger decides the node.

## Output

`bynli_lines_v2` shape, so `make_lstmf` reads it unchanged: `{train,dev}/<series>_<number>/<id>.png` with a `.gt.txt`
each (logical order, one line), plus the following files:

- **Order.** lstmtraining reads its lists in order and does not shuffle, so every list output is in one seeded order:
  rows sorted by `sha256(seed + NUL + id)`. `manifest.jsonl`, `train.txt` and `dev.txt` (image paths, one per line)
  follow it, and `summary.json` records `shuffle_seed`. Builds with different seeds hold the same rows, byte for byte.

- **`manifest.jsonl`:** one row per line, with these fields:
  - identity: `id`, `split`, `book`, `record_id`, `unit_id`, `entry_id`;
  - booklet: `series`, `booklet_number`, `publish_date`, `page`;
  - label and checks: `text`, `tier_a_flags`, `line_order_verified`, `reading_order_verified`;
  - provenance: `label_source`, `capture`, `page_render`;
  - geometry: `bbox_page_pt`, `bbox_image`, `crop_box_image`;
  - image: `image`, `image_sha256`;
  - licence: `license: PD-IL`, `license_basis` (Copyright Act 2007 §6), `attribution` (Reshumot, State of Israel),
    `publisher_url`, `pdf_sha256`, `born_digital_check`.
- **`summary.json`:**
  - lines per booklet, split and series;
  - drop counts by reason (with `dropped_definitions`);
  - every booklet's born-digital check, publisher URL and drops;
  - the eval-reserved check (input units and pages by status, output rows by status);
  - `dev_selection`, the tier-A provenance, the label character inventory, `manifest_sha256`, `release_notice`, and the
    operator's `signature`.
- **`tagger_units.json`:** one entry per non-eval booklet. Each gives its unit id, series, date, split (`refused` for a
  booklet that failed the born-digital check), hint, line count, publisher URL and two rendered page images (the
  pages giving the most lines). The paths point into the snapshot's `assets/`.

## v2: the 2005 born-digital booklets

`reshumotlines_v1` read the F8g2 tranche capture, which filtered on `PublishDate ≥ 2006-01-01`. The born-digital era
starts in 2005 (ספר החוקים from booklet 1976, January 2005; קובץ התקנות from 6395, 30 June 2005; modern-s6-scout
report §2.2), and `PublishDate` is empty for most 2005 ספר החוקים listings, so v1 had none of them.
`hocrgen.tools.reshumot_capture` captures a whole span with the scout's fetcher fixes (report §7 item 1):

1. `enumerate`: every listing of each (FolderType, BookletYear), complete and order-free. Answers are collected as a
   set keyed by series, number and document URL, re-paged until the set holds `TotalResults`, with missing numbers
   looked up. A transient `Status: Warn` empty answer is retried after 30, 60 and 120 s. A year at the 200-result cap is
   sliced by `BookletNum` substring (`reshumot_enumerate_year`).
2. `fetch`: every listed file of the chosen numbers goes into a downloads folder of its own (untrusted), keyed by
   (series, number, sha256). A booklet listed twice (the 2015 PDFsharp rescan and the InDesign original) keeps both.
   Each file is decided born digital from the PDF itself (`reshumot_pdf_born_digital`, reusing `born_digital_check`),
   never from `PublishDate`.
3. `knesset-dates`: when the API's `PublishDate` is empty, the Knesset's `KNS_Law.PublicationDate` for the booklet
   number gives the date (laws only). A booklet whose laws disagree gets no date and is left out. The date source is
   recorded on the entry (`booklet.publish_date_source`) and on the expected phrase the gate checks against the running
   footer.
4. `select`, `materialize --extract-only`, `outline-table`, `materialize`. The span's snapshot is built with no
   packaged fixture. The F8e2 method and the page gate are unchanged except for the era floor, which moves from 2006 to
   2005 (`RESHUMOT_BORN_DIGITAL_FROM`; the PDF decides). The snapshot's glyph outline table is the packaged one,
   unchanged, plus the outlines it lacks. A new outline with conflicting readings stays unresolved, so its glyphs are
   unverified.
5. `new-booklets`: the list heocr-eval assigns (series, number, date, pages, sha256; one row per file). Nothing reads
   the new booklets before eval's assignment reaches `config/eval_reserved_units.yaml`.

The throttle allows at most one request per 1.2 s, with User-Agent `HeOCR-research/0.1 (+https://github.com/HeOCR)`.
Every command that reads a downloaded PDF runs under `python -I` through a runner that puts `src/` on `sys.path`.

v2 is built from both snapshots (tranche v5 for v1's booklets and the 2005 snapshot) with v1's options, plus
`--keep-dev-from` v1's summary, `--exclude-6grams` and `--shuffle-seed reshumotlines-v2`.
