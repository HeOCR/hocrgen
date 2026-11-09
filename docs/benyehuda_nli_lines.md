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
  --dev REC=name ... --max-lines-per-book 3000 [--cap-dev] [--no-images]
```

The input is one or more F8f roots, each laid out as follows:
- `out/<pby>/alignment.json`
- `pby/txt/m<pby>.txt`
- `work/<rec>/img/c<idx>.jpg`
- `work/<rec>/ocr/c<idx>.tsv`

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
