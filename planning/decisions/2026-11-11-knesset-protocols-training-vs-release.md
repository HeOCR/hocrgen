# Decision 2026-11-11: Knesset committee protocols: train on all periods, publish only up to 1975

- **Date:** 2026-11-11
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Recorded by:** `lead[claude/claude-code#shay-macbook-m4]@heocr/opensource`
- **Status:** accepted
- **Full text:**
  - the analysis, verbatim: `docs/legal/2026-11-11_knesset_protocols_analysis.md`;
  - the prompt that produced it: `docs/legal/2026-11-11_knesset_protocols_prompt.md`;
  - the follow-up analysis (bills, evaluation use, memorisation, citations), verbatim: `docs/legal/2026-11-11_knesset_followup_analysis.md`;
  - the follow-up prompt: `docs/legal/2026-11-11_knesset_followup_prompt.md`.
- **Supersedes:** item 5 of `2026-11-06-f8-real-source-decisions.md`, which excluded committee protocols from 1976 on until a legal opinion arrived. The opinion has arrived, and this decision replaces that exclusion.
- **Builds on:** `2026-11-10-legal-strategy.md` and `2026-11-10-open-release-and-clean-inputs.md`.

## Decision

The analysis separates two activities across three periods:
- **Activity A:** training OCR models and releasing Apache-2.0 weights.
- **Activity B:** publishing line crops and transcriptions as a CC0 / CC BY-SA dataset.
- **The periods:**
  1. up to 1975-12-31;
  2. 1976-01-01 to 2008-05-24;
  3. 2008-05-25 onward.

The maintainer, 2026-11-11:

> "it drives my decision to pursue Activity A: Training OCR Models & Releasing Apache-2.0 Weights on all 3 periods, but Activity B: Publishing Line Crops & Transcriptions as a CC0 / CC BY-SA Dataset only for period 1"

| Period | Training and Apache-2.0 weights (A) | Published line crops and transcriptions (B) |
|---|---|---|
| 1. up to 1975-12-31 | yes | yes |
| 2. 1976-01-01 – 2008-05-24 | yes | **no** |
| 3. 2008-05-25 onward | yes | **no** |

## What this means in practice

1. **A new release scope: training only.** Committee protocols created from 1976 on may enter training lists. Their line crops, page images and transcriptions never enter a published dataset, glyph bank, benchmark or any other released artefact. The hocrgen export must refuse them, just as `refuse_eval_reserved_training_input` guards eval-reserved units. The scope marker and the guard are to be implemented.
2. **The period moves forward each year.** State copyright runs 50 years from creation and ends on 31 December (sections 42, 43 and 78(a)). So the protocols of year *Y* move into period 1 on 1 January of year *Y* + 51. The 1976 protocols move on 2027-01-01. The scope is derived from the session date, never fixed.
3. **Weights.** Models trained on period 2 or 3 protocols are released under Apache-2.0, with attribution in the model card and NOTICE: the Knesset website, as its terms of use ask of anyone quoting from it. The legal basis for this is fair use, section 19, plus the Ministry of Justice's 2022 opinion on machine learning, as the analysis reports.
4. **Evaluation.** Period 2 and 3 lines may serve as eval references only in the restricted, unpublished track (heocr-restricted-eval). Scores computed on them may be published. The follow-up analysis confirms this (Q7). Published benchmarks use period 1 only.
5. **Period 1 publication conditions, from the two analyses:**
   - publish only lines spoken by the committee chair, MKs, ministers, civil servants or Knesset staff;
   - exclude every line by a private speaker, and all attached or quoted third-party documents. A private person's copyright runs life + 70 years, not 50 years from creation.
6. **The privacy screen stays.** Protocols naming private persons are screened per page, as before, in every period and for both activities. The analysis calls this essential under the Protection of Privacy Law, Amendment 13.
7. **Access.** Fetching stays under F8 decision 4 (automated access to government sites), with hard throttling. Fetchers avoid the nested `$expand/$select` query shape that triggered the Knesset firewall on 2026-11-11.
8. **Not covered:**
   - **Bills.** Covered in Part 2 below.
   - **The Knesset plenary record (Divrei ha-Knesset).** It is unchanged: section 6, open, both activities.
   - **The Hebrew letter to the Knesset legal adviser** in the analysis. Not sent; only the maintainer sends outreach.

## Not adopted

The analysis suggests releasing single-word or glyph crops from period 2 and 3 protocols as a workaround (its "Path 1"). The decision above does not adopt that: period 2 and 3 material is not published in any form.

## Part 2: bills, and safeguards for training-only material (2026-11-11)

The maintainer, on the follow-up analysis:

> "as usual, I ascribe to his recommendations and suggestions"

### Bills (הצעות חוק)

| Bill type | Training and weights (A) | Published crops and text (B), up to 1975 | Published crops and text (B), 1976 on |
|---|---|---|---|
| (i) Government bills (Reshumot *Hatza'ot Hok*) | yes, all periods | yes | **only clauses enacted verbatim into law**. Explanatory notes and un-enacted text: training only |
| (ii) Private members' bills | yes, all periods | **only where MK or Knesset-staff authorship is clear**; prefer (i) and (iii) | **no**: training only |
| (iii) Committee bills | yes, all periods | yes | **only clauses enacted verbatim into law**. Explanatory notes and un-enacted text: training only |

- **"Enacted verbatim"** means a bill line matches the published text of the enacted law in *Sefer ha-Hukim*, exactly and per line. The match is recorded per line.
- **Bills printed inside the plenary record** (Divrei ha-Knesset, including its appendices) are section 6 material: (A) and (B) in every period. Text a speaker reads in from a private third party is excluded.
- **Being published in Reshumot doesn't make a document section 6 material.** Section 21 (works deposited for public inspection) doesn't allow republication either.
- **For modern legislative type in published datasets,** prefer *Sefer ha-Hukim*, *Kovetz ha-Takanot* and the plenary record. They are section 6 material in every period.

### Safeguards for every training-only input

These cover committee protocols from 1976 on, bill explanatory notes and un-enacted bill text from 1976 on, and private members' bills from 1976 on. They follow the analysis's memorisation guardrails (Q8):

1. **No language data from training-only text.** No word list, dawg, punctuation or number list, or n-gram or language model is built from it. Shipped dictionaries come only from published-scope text.
2. **Single-line crops only.** No multi-line or paragraph crops.
3. **Deduplicate.** Exact-duplicate lines are removed before training.
4. **A blank-image probe before every weight release.** Blank, noise and salt-and-pepper line images must decode to empty output or gibberish, never to a memorised phrase. This goes on the release checklist.

### Other items

- **Website terms.** The gov.il and Knesset browse-wrap terms defer to statutory fair use. They add no bar to training, or to publishing public-domain material.
- **data.gov.il.** Its licence is not CC0 and covers only datasets hosted there, so it opens nothing new.
- **The Knesset legal department's public-inquiry address,** per the follow-up analysis, is on `main.knesset.gov.il/About/Departments/pages/leg/ldcontact.aspx`. The address in the first analysis is withdrawn. Verify it on that page before any outreach. Only the maintainer sends outreach.
