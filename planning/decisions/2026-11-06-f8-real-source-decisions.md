# Decision 2026-11-06: F8 real-source decisions

- **Date:** 2026-11-06
- **Decided by:** the maintainer
- **Status:** accepted

These answer the "Maintainer decisions needed" list in [`planning/tasks/f8-real-source-map.md`](../tasks/f8-real-source-map.md).

## Decisions

1. **Wikisource text licence.** CC BY-SA 4.0 page text is accepted for references. Share-alike applies to the reference files HeOCR releases.
2. **Wikisource proofreading as human attestation.** The recommendation is accepted:
   - **Quality 4** (validated by a second editor) counts as human-attested and adjudication-eligible.
   - **Quality 3** (proofread) counts as single-reviewer human proofreading.
   - Each counts only with the named human editor recorded from the page history. An agent never edits or attests these pages.
3. **Commons scans that came from HebrewBooks are accepted**, subject to the same per-file rights check as every other file. That means evidence that the underlying work is PD in Israel and that the scan's rights are clear; `PD-US-*`-only files are still rejected.
   - First the maintainer asked what HebrewBooks' terms say. They are a personal-use, non-commercial licence that bans automated access, covering a mix of PD and permissioned books. Those terms bind whoever downloads from HebrewBooks, and HeOCR does not access HebrewBooks.
   - The maintainer then accepted the recommendation, the same day.
4. **Automated access to government sites is allowed.** This covers the Reshumot search API on gov.il, the Supreme Court decisions site, the Knesset site and the Israel State Archives. `F8e` is no longer deferred; it is planned.
   - Two things this decision does not cover. Court rulings still need publication-ban screening; that is a legal requirement, not a privacy review of public-domain material. The State Archives' no-derivative-works clause is a separate term, so ISA stays `review_only`.
   - Fetchers throttle hard; the Knesset firewall blocked an agent after about 100 queries.
5. **Knesset committee protocols from 1976 on.** A legal opinion will be requested. They stay excluded until it arrives. Committee protocols up to 1975 are state works, PD under §42.
6. **Printed Yiddish in Hebrew script is in scope, but only for training and character-level evaluation.** Yiddish uses the Hebrew alphabet, so its characters are valid targets. It is not used for word-level or language-level Hebrew evaluation. This applies to YidTakNL in `F8d`.
7. **NLI Search API key.** Request one. The agent handles the request and asks the maintainer only where it gets stuck.
8. **Pinkas: Hebrew lines may be used with full Hebrew scope, including word-level and language-level Hebrew evaluation.** The BGU Pinkas text mixes Hebrew and Western Yiddish. Its **Hebrew lines** may be used for training, character-level evaluation, and word-level and language-level Hebrew evaluation, with nothing excluded. Its **Yiddish lines** keep the decision-6 scope: training and character-level evaluation only. Decided on the same day, after `F8d2` shipped a page-level `character_level_only` default.
   - **Clarified by the maintainer on 2026-11-06.** The first wording opened word-level Hebrew evaluation only, and `F8d3` kept `language_level_hebrew` excluded on Hebrew lines. A line tagged as Hebrew is Hebrew, so that exclusion was illogical. The `language_level_hebrew` exclusion exists to keep Yiddish from being treated as Hebrew-language data, so it does not apply to Hebrew lines. `F8d3b` implements this.
   - A line counts as Hebrew only through an explicit, reviewable per-line language tag. Until a line is tagged, it keeps the conservative `character_level_only` scope.
   - Tags are never inferred silently from a script or language heuristic.

9. **Google-digitized scans are accepted**, under the same per-file check as every other file. This covers Commons files stamped "Digitized by Google": Google's usage guidelines bind whoever downloads from Google Books, not the public-domain status of the work. NLI's own `public-domain-non-commercial-use` class stays out, because NLI states that restriction on the item itself.
10. **Data gaps are not rights problems.** A Wikisource Index is not rejected because evidence is missing from Commons or Wikidata when the work is in fact public domain. Missing evidence is resolved, not used as a reason to drop the Index:
    - **Death years** are looked up and recorded with a cited source.
    - **A work published on or before 1855** is presumed PD in Israel even when no creator death year is found. Its creators would have had to live more than 100 years after publication to still be protected.
    - **Scan provenance and licence templates:** a faithful reproduction of a public-domain work needs no recorded scan source or open-licence template. The Commons tag (`PD-US-*`, missing, or other) never decides the work's status in Israel; the work's own evidence does.
    - **Real protection still excludes.** For example, the Birnbaum works stay out: Birnbaum died in 1988.
11. **The text converter must handle every page.** No page is dropped for unsupported markup. The converter is extended until every construct used in admitted Indexes has a defined, tested rendering. Closed-world remains the safety rule during development: an unknown construct fails loudly so it gets implemented, never silently dropped. The open question is only the output form of each construct.
12. **Partial transcriptions are cropped, not dropped.** When a page's transcription covers only part of the page (for example commentary without the verse), the image is cropped to the transcribed region. The resulting sub-image and text form the pair. The crop is located by tooling (OCR may be used for localization only, never as text), recorded with its geometry and method, and reviewable.

13. **NLI: the per-item licence governs.** An NLI item's IIIF manifest `license` slug decides its rights. The image service's `info.json` `rights` value is ignored for rights, and is kept as recorded evidence only.
    - That value points to `nli-copying-prohibited` on the legacy `web.nli.org.il` domain.
    - It is identical on every image checked, including items NLI states are `public-domain-free-use`. It appears to be a server-wide default.
    - NLI's terms apply "unless explicitly stated otherwise", and the item statement is that explicit statement.
    - This applies to the existing `nli_any_use_permitted` seeds and to every F8 source that takes scan rights from NLI (`F8c`, `F8d`, `F8d2`).

## Consequences

- `F8b` is unblocked. HebrewBooks-sourced and Google-digitized Index files are admitted through the per-file rights check (decisions 3 and 9).
- The Wikisource pipeline (`F8b3` and after) resolves evidence gaps, extends the converter to every construct, and crops partial pages (decisions 10–12). The goal is that every quality-3/4 page of a public-domain Hebrew work becomes an image–text pair.
- `F8d` admits YidTakNL with a scope marker limiting it to training and character-level evaluation.
- `pinkas_dataset_bgu` needs per-line language tags before any line is used for word-level or language-level Hebrew evaluation (decision 8). This is follow-up work; the shipped page-level scope stays in force until then.
- `F8e` is planned rather than deferred. It covers Reshumot from about 2006 (born-digital) and Knesset committee scans up to 1975. Committee protocols from 1976 on wait for the legal opinion.
- The other rules are unchanged:
  - Every new F8 source id starts `review_only` and outside `profile_open_v1`.
  - OCR and HTR output is never ground truth.
  - `benchmark_v1` membership stays frozen.
