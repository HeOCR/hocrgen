# Even HaEzer training-line screen

The existing Tier B EH set failed its visual audit, including after the first edge screen. This **candidate** screen adds exact normalized OCR word agreement and rejects dark ink at the crop border, in addition to the earlier OCR geometry checks. It retains 266 original crops, identified by their image and label hashes in `screen.json`. It does not change the source labels or crops and does not admit them to a training round.

The first version of this stricter screen still admitted crops with adjacent-line bleed; the vertical-border check was added after inspecting that sample. A fresh sample was then drawn from the fixed screen, excluding all three prior samples, by SHA-256 order using the seed and exact exclusions in `audit.json`. Visual inspection found no confirmed word errors in the 32 crops. Some small adjacent glyph fragments and superscript marks remain; this is a training-label audit, not an OCR performance measurement. Independent review is advisable before pool use. No model was measured on a held-out set here.

Reproduce using the archived original Tier B training manifest and EH PNG crops (recovery procedure held by histpurge), and the original EH page OCR TSVs. The screen fails if the manifest or crop hashes differ; the receipt records the page OCR hashes so they must be checked against a reproduction. The source text is Public Domain as recorded in the source manifest. The tool does not read evaluation material.

```sh
python -m hocrgen.tools.phist_eh_screen --manifest TRAINING_MANIFEST --crops EH_PNG_DIRECTORY --ocr EH_PAGE_TSV_DIRECTORY --out screen.json
```

Before including any candidate in a round, histpurge must confirm the audit and source/contamination gates, rebuild the roster, keep the per-book share at most 8%, preserve the existing replay membership, and obtain the applicable CLEAN receipt. Neither the existing frozen roster nor the replay is modified here. Exact OCR agreement is conservative but cannot detect a shared OCR and label error or a mark missed by OCR; the selector must not be treated as automatic approval.

phistfix[openai/codex#shay-macbook-m4]@heocr/opensource
