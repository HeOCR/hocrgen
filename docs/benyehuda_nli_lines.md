# Real line sets from the Ben-Yehuda × NLI alignment

`hocrgen.tools.benyehuda_nli_lines` turns F8f alignments (`benyehuda_nli_alignment`) into line-image sets for
recognizer fine-tuning (R6 Tesseract and later), and measures whether OCR output could serve as line labels.

**Labels are always the Ben-Yehuda edition text the alignment placed on a line, never OCR output.** OCR localizes
lines (in the aligner) and, here, only chooses between candidate edition spans at a line's edges.

## Build

```bash
python -m hocrgen.tools.benyehuda_nli_lines build OUT \
  --root F8F_ROOT [--root F8F3_ROOT ...] --editions EDITIONS.json \
  --pointed REC=name ... --keep-pointed \
  --dev REC=name ... --max-lines-per-book 3000 [--cap-dev] [--no-images] \
  [--prefer-placer r6@73eb18e0 ...]
```

The input is one or more F8f roots, each laid out as follows:
- `out/<pby>/alignment.json`
- `pby/txt/m<pby>.txt`
- `work/<rec>/img/c<idx>.jpg`
- `work/<rec>/ocr/c<idx>.tsv`, the aligner's page OCR. A record placed by another model (`method.ocr_model`, e.g.
  `r6@73eb18e0`) keeps it in `work/<rec>/ocr-<ocr_model>/` (hocrgen#155). The builder reads the placer's own TSVs for
  span refinement and the line-OCR gate, and fails if they are missing rather than falling back to stock.
- optionally, second alignment passes in `out_<name>/<pby>/alignment.json` (e.g. `out_r6/`), which leave `out/` intact.

**One source per record.** A record aligned in more than one place (`out/` and `out_r6/`, or two roots) is ambiguous.
`--prefer-placer P` (repeatable, in order of preference) takes the source whose placer is `P`, for example
`--prefer-placer r6@73eb18e0` for the R6 second pass, or `stock` for `out/`. Without a preference that resolves it, the
build fails and names the sources. In v2, `summary.json` records each such choice in `ocr_placer_choice` (chosen and
skipped sources, with their placers and PBY ids). Manifest rows carry `alignment` (the alignment file, relative to its
root) and `page_ocr` (the OCR directory read). `score --page-ocr-root` reads `page_ocr`.

Line boxes in the alignment are in canvas pixels; they are converted to image pixels using canvas width / image
width (hocrgen#152).

The build writes these outputs:
- `{train,dev}/<rec>/<id>.png` and a matching `.gt.txt` per line;
- `manifest.jsonl`;
- `summary.json`.

Gates and drop reasons are listed in the module docstring.

### Schemas

**v1** (`--schema v1`): the set `bynli_lines_v1`. Pointed prints are dropped, and labels have niqqud removed.

**v2** adds the following:

- **Pointed stratum.** With `--keep-pointed`, labels of pointed prints keep the edition niqqud. A pointed book is
  dropped whole when its edition text is under-pointed against a fully pointed print, meaning more than 5% of shins
  are undotted or more than 1% of words carry no niqqud. Example: in Katzenelson's *Mahamadim* the Ben-Yehuda text
  leaves 88% of shins undotted, so its labels would miss marks the print shows. Mandelkern passes at 0.9%.
- **Per-book cap.** `--max-lines-per-book` keeps N lines per book, chosen by the sha256 of the line id, so the choice
  is deterministic and spread over the book. Dev books are held out whole and are uncapped unless `--cap-dev` is set.
- **Per-line fields.** Each line gets a `stratum` and an `ocr_placer`, the OCR that localized it for the aligner:
  - `method.ocr_model` if the alignment records one;
  - otherwise `tessdata:<dir>` from `--tessdata-dir` in `method.ocr_engine`;
  - otherwise `stock`.
- **Summary breakdowns.** `summary.json` adds these fields:
  - `lines_by_book_and_stratum`;
  - `lines_by_book_and_ocr_placer`;
  - `pointed_edition_check`;
  - `check_pointed`, which lists unflagged books whose edition text is pointed.

## Text sources: Sefaria and Project Gutenberg

Since 2026-11-11 the aligner also places Sefaria public-domain versions and Project Gutenberg ebooks, not only PBY
texts (`hocrgen.fetchers.text_sources`; decision
[`planning/decisions/2026-11-11-text-sources-sefaria-gutenberg.md`](../planning/decisions/2026-11-11-text-sources-sefaria-gutenberg.md)).

```bash
# 1. gate and normalise a saved Sefaria version download (or a Gutenberg ebook) into text/<work_id>.{txt,record.json}
python -m hocrgen.fetchers.text_sources sefaria --snapshot VERSION.json --versions-snapshot VERSIONS.json \
  --spec SPEC.json --work-id sefaria_leket_yosher --out-dir ROOT/text
python -m hocrgen.fetchers.text_sources gutenberg --snapshot pg43740.txt --rdf 43740.rdf --ebook 43740 \
  --ia-identifier betnekhothahalak01horouoft --spec SPEC.json --work-id gutenberg_43740 --out-dir ROOT/text
# 2. align it to an Internet Archive scan of the same edition
python -m hocrgen.tools.benyehuda_nli_alignment align --source ia --text-source sefaria \
  --text-record ROOT/text/sefaria_leket_yosher.record.json --text ROOT/text/sefaria_leket_yosher.txt \
  --manifest M.iiif3.json --ia-identifier ID --ia-metadata ID.json --wikidata-snapshots ROOT/wikidata \
  --as-of 2026-11-11 --work-dir ROOT/work/ID --out-dir ROOT/out/sefaria_leket_yosher --generated-on 2026-11-11
```

`SPEC.json` lists the contributors (name, role `author`/`editor`/`translator`/`annotator`, Wikidata QID), the
publication place and year, the `script`, optional top-level `parts` (Sefaria schema nodes, in order) and, for an
ancient compilation with a traditional attribution only, `anonymous_work` (a note and its evidence).

- **Licence gate (fail-closed).** A Sefaria version is accepted only with the licence string exactly `Public Domain`,
  a `versionSource` that is the catalogue record of a printing (NLI, IA or Gutenberg) and a year in its title.
  CC BY-NC, `unknown`, CC BY, CC BY-SA, CC0, any other label, and `Public Domain` with no printing are rejected.
  `python -m hocrgen.fetchers.text_sources gate VERSIONS.json ...` reports the decision on every version of a title.
  A Gutenberg ebook is accepted only for the scan it was proofread from (`GUTENBERG_EDITIONS`).
- **Normaliser.** Commentator anchors, footnotes and the dash after a bold opening quote are removed, tags unwrapped,
  entities decoded, niqqud removed; `׳ ״ — ־` and Sefaria's ASCII `'` `"` are kept as typed. Gutenberg text loses its
  framing, transcriber's note and markup, and its listed typo corrections are reverted to the print.
- **Rights.** `align` replays the licence gate and checks the text's sha256; the scan's `rights_justification`
  counts the record's editors and annotators as contributors.
- **Rows.** `out/<work_id>/` (`sefaria_<slug>`, `gutenberg_<n>`) and `text/<work_id>.txt` sit in the alignment root
  beside `out/<pby>/` and `pby/txt/`. Text-source rows add `work_id` (`pby_id` null), `text_source`,
  `text_version_title`, `text_version_source`, `text_licence`, `text_api_url`, `text_snapshot_sha256`, `script` and
  `parenthetical_similarity`. A line whose parenthesised group (a citation) does not match the line OCR at that place
  (< 0.85) is dropped as `parenthetical_differs_from_print`: Sefaria re-types citations, so the print's
  `(בר' ט' י"ג)` is `(בראשית ט' י"ג)` in the text. A line whose OCR shows a parenthesis, bracket or digit where the
  label has none is dropped as `print_marker_missing_from_label`: Sefaria keeps the print's note references
  (`(מ)`, `1)`) as anchors or footnotes, which the normaliser removes. PBY rows are unchanged.

## Reserved editions

`--reserve REC[=name]` holds an edition out whole: none of its lines are written to `train` or `dev`, they are
counted as `reserved_edition`, and `summary.json` lists the edition under `reserved_records`. A reserved edition is
the future source of rabbinic eval references or line_verify items, so nothing trained or tuned may see it.

This is the line-set counterpart of the "Reserved Indexes" section of `docs/wikisource_lines.md` (hocrgen#173,
branch `feat/wikisource-lines`), which waived the reserve for `wslines_v1` and put the obligation on the first
lever 5(b) batch. That batch reserves:

RESERVED_TABLE

## OCR-as-label measurement

```bash
python -m hocrgen.tools.benyehuda_nli_lines ocr LINES OCR_DIR [--tessdata-dir D] [--psm 13] [--records R ...]
python -m hocrgen.tools.benyehuda_nli_lines score LINES OCR_DIR OUT.json [--lexicon LEX.json] [--records R ...]
```

Use `--psm 13`, which reads each crop as one raw line, as lstmeval does. With `--psm 7`, both stock Tesseract and R6
return nothing on crops that carry a sliver of the neighbouring line: this happened on 473 of the 4,046 Brainin dev
lines.

On the v1 dev books (Silman and Brainin, 7,092 lines, psm 13, 2026-11-09):

| labeler | exact lines | CER | best 95%-exact keep-rule |
|---|---|---|---|
| stock `heb` | 13.0% | 5.98% | none |
| R6 | 69.5% | 1.25% | word conf ≥ 94, keeps 4.6% of lines |

No rule reaches 99%. R6's remaining errors are mostly its own letter confusions: כ/ב, ד/ר, ג/נ, י/ו and ס/ם. So the
decision is that whole-line OCR labels are not used, and labels stay the edition text.

Tests: `tests/test_benyehuda_nli_lines.py` (network-free; synthetic alignment root).
