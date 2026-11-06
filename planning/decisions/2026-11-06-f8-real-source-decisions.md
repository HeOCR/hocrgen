# Decision 2026-11-06: F8 real-source decisions

- **Date:** 2026-11-06
- **Decided by:** the maintainer
- **Status:** accepted, except item 3, which is open

These answer the "Maintainer decisions needed" list in [`planning/tasks/f8-real-source-map.md`](../tasks/f8-real-source-map.md).

## Decisions

1. **Wikisource text licence.** CC BY-SA 4.0 page text is accepted for references. Share-alike applies to the reference files HeOCR releases.
2. **Wikisource proofreading as human attestation.** The recommendation is accepted:
   - **Quality 4** (validated by a second editor) counts as human-attested and adjudication-eligible.
   - **Quality 3** (proofread) counts as single-reviewer human proofreading.
   - Each counts only with the named human editor recorded from the page history. An agent never edits or attests these pages.
3. **Commons scans that came from HebrewBooks.** *Open.* The maintainer asked what HebrewBooks' terms say. Until this is decided, `F8b` excludes Index files whose Commons source is HebrewBooks.
4. **Automated access to government sites is allowed.** This covers the Reshumot search API on gov.il, the Supreme Court decisions site, the Knesset site and the Israel State Archives. `F8e` is no longer deferred; it is planned.
   - Two things this decision does not cover. Court rulings still need publication-ban screening; that is a legal requirement, not a privacy review of public-domain material. The State Archives' no-derivative-works clause is a separate term, so ISA stays `review_only`.
   - Fetchers throttle hard; the Knesset firewall blocked an agent after about 100 queries.
5. **Knesset committee protocols from 1976 on.** A legal opinion will be requested. They stay excluded until it arrives. Committee protocols up to 1975 are state works, PD under §42.
6. **Printed Yiddish in Hebrew script is in scope, but only for training and character-level evaluation.** Yiddish uses the Hebrew alphabet, so its characters are valid targets. It is not used for word-level or language-level Hebrew evaluation. This applies to YidTakNL in `F8d`.
7. **NLI Search API key.** Request one. The agent handles the request and asks the maintainer only where it gets stuck.

## Consequences

- `F8b` is unblocked, except that HebrewBooks-sourced Index files stay excluded until item 3 is decided.
- `F8d` admits YidTakNL with a scope marker limiting it to training and character-level evaluation.
- `F8e` is planned rather than deferred. It covers Reshumot from about 2006 (born-digital) and Knesset committee scans up to 1975. Committee protocols from 1976 on wait for the legal opinion.
- The other rules are unchanged:
  - Every new F8 source id starts `review_only` and outside `profile_open_v1`.
  - OCR and HTR output is never ground truth.
  - `benchmark_v1` membership stays frozen.
