# Decision 2026-11-11: Knesset committee protocols: train on all periods, publish only up to 1975

- **Date:** 2026-11-11
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Recorded by:** `lead[claude/claude-code#shay-macbook-m4]@heocr/opensource`
- **Status:** accepted
- **Full text:**
  - the analysis, verbatim: `docs/legal/2026-11-11_knesset_protocols_analysis.md`;
  - the prompt that produced it: `docs/legal/2026-11-11_knesset_protocols_prompt.md`.
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
4. **Evaluation.** Period 2 and 3 lines may serve as eval references only in the restricted, unpublished track (heocr-restricted-eval). That is a lead interpretation: internal measurement is the same kind of use as training. Published benchmarks use period 1 only.
5. **Period 1 publication conditions, from the analysis:**
   - exclude attached or quoted third-party documents;
   - exclude long prepared statements by private persons. Those are life + 70 years, not State works.
6. **The privacy screen stays.** Protocols naming private persons are screened per page, as before, in every period and for both activities. The analysis calls this essential under the Protection of Privacy Law, Amendment 13.
7. **Access.** Fetching stays under F8 decision 4 (automated access to government sites), with hard throttling. Fetchers avoid the nested `$expand/$select` query shape that triggered the Knesset firewall on 2026-11-11.
8. **Not covered:**
   - **Bills from 1976 on.** The analysis does not analyse them separately. They stay unadmitted until the maintainer extends this decision to them.
   - **The Knesset plenary record (Divrei ha-Knesset).** It is unchanged: section 6, open, both activities.
   - **The Hebrew letter to the Knesset legal adviser** in the analysis. Not sent; only the maintainer sends outreach.

## Not adopted

The analysis suggests releasing single-word or glyph crops from period 2 and 3 protocols as a workaround (its "Path 1"). The decision above does not adopt that: period 2 and 3 material is not published in any form.
