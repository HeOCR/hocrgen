# Printed-modern training lines from Reshumot (decision 0018)

`hocrgen.tools.reshumot_lines` cuts one image per verified line from the 150 dpi renders of a tranche's Reshumot
snapshot and labels it with the publisher's glyph-layer text of that line (`pdf_glyph_geometry_logical.v1`, F8e2 and
F8e3 in [`real_source_release_contract.md`](./real_source_release_contract.md)). It builds `reshumotlines_v1`, the
first new-printed (modern typography) real line set.

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

## Lines and split

- **Lines.** The kept units of the page verdict, in the committed text's order (`line_index` is the line number in
  `text/<entry>.txt`).
- **Crop.** The image is the line's glyph ink box plus 3 pt. Every pixel outside the line's own glyph boxes (plus 1.5 px)
  is set to white (`crop_method: unit_glyph_ink_mask.v1`), so the image shows only the labelled glyphs.
- **Line drops.** A line is dropped (`ink_overlaps_other_ink`) when its glyph boxes touch another line's glyphs, a page
  image, a rule or a coloured fill. A line without a letter or digit is dropped (`no_letters_or_digits`).
- **Split, by whole booklet.** Dev takes one booklet per (series, decade) stratum of the non-eval booklets: the first by
  `sha256(unit_id)` that passes the born-digital check and gives at least one line. Train takes every other passing
  booklet. `summary.json` records the method, the ranking and the picks under `dev_selection`.
- **Cap.** `--max-lines-per-booklet` (default 6100) caps each booklet, keeping lines by sha256 of the line id.
- **Node hint.** Every row and `tagger_units.json` entry carries `proposed_node_hint: new_printed`. It is a hint only;
  the maintainer's tagger decides the node.

## Output

`bynli_lines_v2` shape, so `make_lstmf` reads it unchanged: `{train,dev}/<series>_<number>/<id>.png` with a `.gt.txt`
each (logical order, one line), plus the following files:

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
