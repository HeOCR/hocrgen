# Decision 2026-11-10: everything is released openly; no licence-tainted inputs

- **Date:** 2026-11-10
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Status:** accepted
- **Applies to:** every dataset, glyph bank, line set, eval reference set and synthetic batch that HeOCR produces, and every input
  that enters them
- **Companion record:** heocr-engine decision 0014, which covers trained weights
- **Supersedes:** decision 2026-11-07 (real-pool hosting), the clause "each upload still needs the maintainer's approval". Its public-beta gates (`export-public-beta`) still apply.

**Context.** Large data products, including the F8f line sets and the S16 glyph banks, existed only on the operator machine. The
first idea was a private backup. The maintainer chose to publish instead, since HeOCR is an open project.

## Decision

> "הכל פתוח. כל משקל. תמיד. זו ההחלטה תמיד. זה הכלל. הכלל הקיים שמבקש אישור שלי הוא טעות" (Shay Palachy Affek, 2026-11-10)
> ("Everything is open. Every weight. Always. That is the decision, always. That is the rule. The existing rule asking for my approval is a mistake.")

1. **Open by default.** HeOCR's data products are published openly on Hugging Face (organisation `HeOCR`), with
   Zenodo as the archive (decision 2026-11-07, real-pool hosting). No per-release approval is needed.
2. **Internet Archive scans** (decision 2026-11-09) and lines cut from them are published **without an explicit
   licence**. A NOTICE states that the item's original conditions on IA still apply. Each line keeps its IA
   identifier, contributing library and `source_class`.
3. **NLI public-domain-free-use scans** keep their attribution to the National Library of Israel in the NOTICE and in
   every line's provenance.
4. **Attribution and share-alike are acceptable.** A CC BY or CC BY-SA input is credited, and its share-alike term is applied
   where it reaches the product (for example, Hebrew Wikisource text is CC BY-SA).
5. **Iron rule for the supply chain:**
   - **The rule:** no input may enter the pipeline if its licence would cast doubt on releasing the derived data or models openly. This covers fonts, scans, texts, banks and models.
   - **What is out:** non-commercial, no-derivatives, "personal use", proprietary or OS-bundled, and unknown terms.
   - **When licence evidence is missing:** an input without licence evidence stays out until the evidence exists.

## Consequences

- Rights gates, such as `decide_nli_rights` and `decide_ia_rights`, keep guarding what enters. The release step adds the NOTICE for each source class.
- A glyph bank is published once its provenance check passes. That check is under way as of 2026-11-10.
- Eval and leakage rules are unchanged. Eval works stay held out of training data, and eval pages are not tuned on.
- Unchanged: decision 2026-11-06 (tender pages). `heocr-restricted-eval` stays private, only aggregate metrics are published, and nothing from it enters any deposit. Those pages carry no open licence, so the iron rule keeps them out as well.
