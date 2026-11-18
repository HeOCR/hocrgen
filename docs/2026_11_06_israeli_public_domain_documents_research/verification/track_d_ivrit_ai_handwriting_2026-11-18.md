# Track D addendum: ivrit.ai handwriting sources (2026-11-18)

Updates row 8 of `track_d_transcribed_datasets.md` (2026-11-06: "Unknown (gated)", `UNKNOWN`). Task from heocr-lead,
approved by Shay on 2026-11-18. This was desk research only.
- Only public pages were read: the Hugging Face API metadata, the public dataset page, ivrit.ai's licence and FAQ pages,
  public GitHub repos, and the transcriptor's public stats endpoint.
- No gated terms were accepted, there was no sign-in, and no dataset file was downloaded.

Tags: *(verified 2026-11-18)* means the primary page or API was loaded and re-checked by data-collection. *(inferred)*
is a reading of the evidence. `not visible` means it can't be seen without accepting the gate.

## Rulings (Shay, via heocr-lead, 2026-11-18)

- **Gate accepted on 2026-11-18.** The lead accepted the Hugging Face gate of `ivrit-ai/hebrew-handwriting-ocr-benchmark`
  in Shay's own browser session, on Shay's instruction. This counts as accepting the ivrit.ai licence's terms.
- **Publishing per-engine scores counts as research** (decision 0023, open by default). ivrit.ai is not asked first.
- **Import.** A light job, run after that night's registered gate run, into heocr-restricted-eval only. The import keeps
  only image and gold text, and drops the writer block, notes, `user_id`s and fingerprints. The data never goes into
  training, HASH, the review app or any release. The benchmark's 10 writers are held out of all future training data.
- **Gold text.** Use the gated dataset only. The ungated `test_gold.jsonl` in the Space is not used.
- **Transcriptor corpus.** No request to ivrit.ai for now. Shay will ask once HeOCR has publications and traction.

## Verdicts (desk research, before the rulings)

| Source | Eval | Training | Verdict | What Shay must accept |
|---|---|---|---|---|
| `ivrit-ai/hebrew-handwriting-ocr-benchmark` (10 pages, 225 lines) | **Usable, with conditions** (see §1.8) | No: it is a test set, and its writers stay out of training | **Usable for eval once Shay accepts the gate.** Restricted only. Aggregate scores only. | The HF gate checkbox, sharing his HF account details, and the ivrit.ai licence (version not stated; v2 most likely). Better: first ask ivrit.ai in writing that v2 applies and that a public benchmark counts as research. |
| transcriptor.ivrit.ai volunteer corpus | n/a | Probably licensable once released | **Blocked: not released anywhere.** | Nothing for now. |

## 1. `ivrit-ai/hebrew-handwriting-ocr-benchmark` (Hugging Face)

### 1.1 Access
*(verified 2026-11-18)*
- The API record shows `gated: "auto"` and `license: other`, with `license_name: ivrit.ai` and `license_link: https://www.ivrit.ai/en/the-license/`.
- What stays closed without accepting the gate:
  - the raw README returns 401;
  - the datasets-server `/info` and `/first-rows` endpoints say they need authentication.
- The card text can be read on the public dataset page.

### 1.2 Licence version
- **The card does not name a version.** It links ivrit.ai's general licence page, and that page lists two versions. *(verified 2026-11-18)*
  - **v2 (October 1st, 2024)** is CC BY 4.0 with these additions:
    - The data "may only be used, modified and distributed for the express purpose of either (a) training AI models, or (b) academic research".
    - No deep-fakes of the people in the data.
    - No distribution against export controls or sanctions.
    - A no-warranty and no-liability disclaimer.
    - Where these terms conflict with CC BY, these terms win.
  - **v1 (June 30th, 2023)** is the same, but the only allowed purpose is training AI models.
  - Neither version has share-alike, a revocation clause, or any clause about trained weights or derivatives.
- The page says v2 is used for data collected through ivrit.ai's crowd efforts. The handwriting was crowd-collected, so **v2 is most likely** *(inferred)*.
- The FAQ says the limits "do not restrict the use of the material for commercial purposes". So this is a purpose limit, not NC. The FAQ is out of date: it still describes only v1's purpose.

### 1.3 Does a public benchmark fit the allowed purpose?
- **Unclear.** Under v2, scoring engines and publishing per-engine aggregate scores must count as "academic research". The licence does not define that term, and HeOCR is an open project, not a university. Under v1, evaluation is not an allowed purpose at all.
- **In favour:**
  - ivrit.ai run a public per-engine leaderboard on this same set.
  - The card says the licence "enables broad research and commercial use".
  - Aggregate scores don't redistribute the data.
- **Neither the licence nor the FAQ mentions** benchmarking, evaluation, or publishing results.
- **Recommendation:** ask ivrit.ai in writing before the first published score. Shay sends; we only draft.

### 1.4 Per-row `upstream_license`
- **Not visible.**
- One weak hint: the public `ivrit-ai/transcriptor` import script shows `--license CC-BY-4.0` in its example usage. That is an example, not row data.

### 1.5 What the gate asks for
*(verified 2026-11-18)*
- There is one checkbox: "I have read the license, and agree to its terms".
- Hugging Face also asks to share the account's details with ivrit.ai.
- Approval is automatic, and you must be signed in to accept.

### 1.6 Attribution owed
- **CC BY 4.0 credit:** name ivrit.ai, link the licence, and say what was changed.
- **Card citation:** `@misc{hebrew_handwriting_ocr_benchmark, author = {ivrit.ai}, year = {2026}, url = {https://huggingface.co/datasets/ivrit-ai/hebrew-handwriting-ocr-benchmark}}`.
- **Leaderboard citation** for the source corpus: `https://transcriptor.ivrit.ai`.

### 1.7 Scoring harness (`ivrit-ai/ocr-eval`)
- **The repo isn't public.** `github.com/ivrit-ai/ocr-eval` returns 404 *(verified 2026-11-18)*, and it isn't in the org's public repos. So its licence and code are unknown. The card names `run_ocr_eval.py` as the reference.
- **Their measure**, from the card and the leaderboard Space:
  - **Line CER** is edit distance against the gold line. Engines are ranked by median line CER with the 25th–75th percentile range shown, and micro CER (total edits over total reference characters) is reported too. Mean CER is not reported.
  - **Blank outputs** are "excluded from both and counted separately".
  - **Page mode** reports word coverage (the share of gold tokens that appear in the output, counted as a multiset) and page CER (gold lines joined in reading order).
- **Their normalisation** canonicalises punctuation and whitespace: quotes, dashes, maqaf, geresh and gershayim, ellipsis, Unicode spaces, and zero-width and bidi marks. It leaves Hebrew letters and niqqud untouched.
  - It does **not** remove niqqud or fold final letters.
  - It does not say whether NFC is applied, or how word coverage splits tokens.
- **Next to `line_fold_v1`:**
  - We can report a median and micro line CER that approximates theirs, labelled "ivrit.ai-style, re-implemented". We can't claim an exact match without their code.
  - We must also report blank counts and CER with blanks included. Dropping blanks flatters engines that return nothing on hard lines.

### 1.8 Privacy, and conditions for eval use
- **What the rows hold** (from the card; the rows themselves are not visible):
  - writer decade, age range, gender, native language and self-rated legibility;
  - `consent_given` and a free-text `additional_notes`;
  - `submitter_fingerprint`;
  - the transcribing volunteers' `user_id`s.
- The card says contributors consented. The uploader form's consent text covers research and development, including OCR and HTR training, under the ivrit.ai licence. The card also warns that images "may contain incidental personal content".
- **Duties.** The licence has no privacy clause apart from the deep-fake ban. It says nothing about deletion requests, re-identification, or passing on the metadata. So it creates no extra duty for us beyond CC BY and the purpose limit.
- **Our own rules still apply.** These are modern pages by living people, and personal data needs a consent path Shay has approved. So, if Shay accepts:
  1. Load images and gold text only. Drop the writer block, `additional_notes`, `user_id`s and fingerprints at import.
  2. Keep everything in heocr-restricted-eval. Never put it in HASH, the review app, any CC0 release, or any training list.
  3. Publish aggregate scores only. No images, crops or lines.
  4. Expect wide intervals: there are only 10 writers.
- **Exposure.** The public, ungated leaderboard Space (tagged MIT) contains `data/test_gold.jsonl`, 144,489 bytes per a HEAD request *(verified 2026-11-18; not downloaded)*. Its README calls this the benchmark's gold.
  - So the gold text sits outside the gate, and LLM-based readers may have seen it. Scores for those readers must carry that caveat.
  - We should not treat that file as MIT-licensed data, or use it to get around the gate. That is Shay's call.

## 2. transcriptor.ivrit.ai volunteer corpus

- **What it is.** The public stats endpoint reports 552 pages, 20,590 lines, 450 volunteers and 67 manuscripts *(verified 2026-11-18)*.
  - "Lines" counts transcriptions, not unique lines.
  - "Manuscripts" counts batches.
  - Each line is transcribed twice.
- **What's on the pages.** They come from a collection app: phone camera or upload, with a metadata form, 10–20 pages per writer, and decades from the 1950s onward. The card describes them as "mostly personal notes, school notebooks and forms", in ballpoint, photographed with phones. The repo README also shows an example archival batch (NLI, public-domain), so archival batches may be present too.
- **Licence.** Contributors are told the material will be made available under the ivrit.ai licence. There are no per-batch licences in public.
- **Downloadable?** No.
  - Of the org's 30 HF datasets, the benchmark is the only handwriting one. The rest are audio and text, under "ivrit.ai" or "ivrit.ai-v2", all gated.
  - No corpus release was found.
- **Training and open weights.** If the corpus is released under v1 or v2, training is allowed and commercial use isn't barred. No clause covers weights, and there is no share-alike, so Apache weights with attribution on the model card look compatible.
  - The data itself could never go into our CC0 data.
  - It is for the lead or Shay to decide whether a purpose-limited licence breaks our iron rule. The lead's reading: a purpose limit is not NC.
- **Overlap with the benchmark.** Yes. The card says the benchmark is drawn from this corpus, one page per writer fingerprint. Each writer gives 10–20 pages, so the same writers' other pages are probably in the corpus. If it is released, hold out the 10 benchmark **writers**, not just the 10 pages.
- **Compared with our H set.** It is a different domain.
  - **ivrit.ai:** modern writers from the 1950s to now, ballpoint, phone photos, notes and forms.
  - **H v1/v1.1:** mostly 18th–20th century archival manuscripts, professionally scanned.
  - So it would fill the modern-handwriting gap, which we can't fill with public-domain material *(inferred)*.

## 3. What this changes in track D row 8

Row 8 changes from `UNKNOWN` to **`RESTRICTED-PURPOSE` (ivrit.ai licence; CC BY 4.0 plus a purpose limit; gated)**:
- **Benchmark:** eval_only after Shay accepts the gate, under §1.8's conditions.
- **Corpus:** blocked until it is released.

— data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource
