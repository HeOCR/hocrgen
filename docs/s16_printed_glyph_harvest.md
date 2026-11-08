# S16: printed glyph harvest from real scans

`hocrgen.tools.glyph_harvest` cuts glyph images out of real scanned printed
Hebrew pages and writes them as a `printed_glyph_bank.v1` directory. hocrsyngen
reads that bank to compose synthetic book pages from real letterpress, with
exact gold. The contract is defined on the consumer side, in
`HeOCR/hocrsyngen` `docs/printed_glyph_bank_v1.md`.

## Why

On the 38 scored real printed pages the release pipeline (R3h + R4d + A1)
scores CER 0.898, and on font-rendered synthetic pages it scores 0.020 (see
`docs/e2d3b_validated_revision_evaluation.md` and heocr-engine
`docs/baselines.md`). Recognizer training has so far seen only TrueType
renders. A bank of real glyphs lets hocrsyngen render the same gold-controlled
text in the typefaces, wear and scan noise of the books we evaluate on.

## Sources

| Source | Unit | Labels | Rights | Selection |
| --- | --- | --- | --- | --- |
| `wikisource_he_proofread` | page | proofread page text (quality 3 or 4) | scans `faithful_reproduction_of_pd_work` (Commons PD-old), or CC0 1.0 / CC BY 4.0 by `scan_rights.licence` | release `train` split only, minus the scored reference pages |
| Ben-Yehuda on NLI free-use scans (F8f) | aligned line | PBY span text (silver line alignment, score ≥ 0.85) | NLI `public-domain-free-use`, PBY public domain | records whose rights decision is `accepted`; these pages are in no release split |

Not harvested:
- Reshumot: born-digital renders, not scans.
- YidTakNL: no line geometry yet.
- Knesset protocols: no text.
- Tender pages: restricted; never read.
- Any test or validation split page.

Wikisource images are 1920 px Commons renders of the same page files the
release uses at 960 px. The cached Tesseract TSVs (`*.heb.psm3.x2.tsv`) are in
that 1920 frame.

## Method

1. **Pair words.** Reference and OCR characters are aligned with difflib, and
   each reference word gets the one OCR word that holds most of its aligned
   characters. Tesseract text is used only to locate the word box; labels
   always come from the reference text.
2. **Cut glyphs.**
   - Each word box is binarized with Sauvola and split into connected
     components.
   - Components that overlap horizontally are merged, for example the leg of ה
     and ק, or the dots of `!`, `?`, `;` and `:`.
   - The word is kept only when its group count equals its character count, and
     when sizes and baseline seats are plausible (descenders below, the rest on
     the baseline).
   - Digit runs are matched in visual (left-to-right) order.
   - Words with niqqud, cantillation or Latin letters are skipped.
3. **Split typefaces.** Many books mix faces, for example square body type with
   Rashi-script commentary or square section numbers in a Rashi-script text.
   - Each letter's glyphs are split in two by shape.
   - Word co-occurrence decides which cluster of one letter goes with which
     cluster of another, and every word takes its majority face.
   - A book becomes `<style>-f0` and `<style>-f1` only when the words' votes
     agree. A face with too few glyphs is dropped rather than mixed in.
4. **Verify.** Within each face, a glyph is kept only when a nearest-centroid
   classifier built from that face's own glyphs picks its label. This removes
   glyphs from words that were paired with the wrong box.
   - A `"` or `״` glyph must hold two ticks: two major ink parts, or at least
     1.2× the face's median `'`/`׳` width (a third of the x-height when the face
     has fewer than five single ticks). Some books print single quotation marks
     where the transcription has `"`, and without this rule a lone tick was
     banked as `"`, so composed pages showed one tick under `"` gold
     (`implausible_double_marks`, since `s16-glyph-harvest-v2`).
5. **Write.**
   - Each glyph is written as a grayscale crop of the original pixels plus its
     own ink mask, its baseline inside the crop and its source word's x-height.
   - Each style gets metrics measured from its pages: x-height, line pitch,
     letter and word gaps, text block width, ink and paper grey.
   - Each style also gets ink-free paper patches and its `work_match_key`.

## Leakage

- Every harvested book is registered in `config/synthetic_training_works.yaml`
  under its work key: `commons_file:<sha1>` for Wikisource, `nli_record:<id>`
  for Ben-Yehuda. Any real item that shows the same book then stays in `train`.
- No glyph comes from a validation or test split page or from a scored
  reference page.

## Running

Operator-only. It needs the `glyphs` extra (numpy, scipy) and the local
real-source tranche.

```bash
pip install -e '.[glyphs]'
python -m hocrgen.tools.glyph_harvest --output BANK --bank-id pgb-v1 \
  --wikisource-snapshot SNAPSHOT --split-manifest release_split_manifest.json \
  --ocr-cache OCR_CACHE --renders RENDERS_1920 \
  --exclude-items-from refs/reference_manifest.json \
  --benyehuda-root F8F_ROOT
```

Tests: `tests/test_glyph_harvest.py` (network-free, toy shapes).
