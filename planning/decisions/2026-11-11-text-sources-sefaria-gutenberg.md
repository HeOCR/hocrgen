# Decision 2026-11-11: Sefaria and Project Gutenberg texts as F8f edition texts

- **Date:** 2026-11-11
- **Decided by:** heocr-lead, under the maintainer's standing ruling of 2026-11-06 (below). No new maintainer decision is needed: the scout's decision 1 (`tasks/r8-rabbinic-scout/report.md`, "heocr-lead decisions (2026-11-11)") records that Sefaria versions labelled Public Domain that cite a printing are public-domain text, which the iron rule allows.
- **Status:** accepted
- **Applies to:** the edition text the F8f aligner places on a scan (`hocrgen.tools.benyehuda_nli_alignment align`), and every line cut from such an alignment (`hocrgen.tools.benyehuda_nli_lines build`). First use: R8's rabbinic line set `rablines_v1` (lever 5(b), batch 1).
- **Builds on:**
  - the maintainer's ruling of 2026-11-06 that outside public-domain text may be used for training (below);
  - `2026-11-10-open-release-and-clean-inputs.md` (the iron rule for inputs);
  - `2026-11-10-legal-strategy.md` (Routes B and C, the per-item rights justification, Google hygiene).
- **Code:** `hocrgen.fetchers.text_sources` (licence gate, normaliser, text record); `align --text-source`; the line builder's text-source rows.

## The standing ruling this applies

The maintainer ruled on 2026-11-06, in the data-direction decisions that opened the F8 real-source work:

> "Outside public-domain text (e.g. Project Ben-Yehuda) may be used for training." (Shay Palachy Affek, 2026-11-06)

He also ruled, the same day, that public domain in Israel is enough, with US status recorded per item. That half is
cited in hocrgen as "PD in Israel is enough for acceptance (decision 2026-11-06)" in the legal strategy's
`work_public_domain` row. The ruling covered Project Ben-Yehuda, the first outside text source, and it was not
limited to it ("e.g."). This note applies it to two more sources. No repository file quotes the training half
verbatim. It is quoted here from heocr-lead's record of the maintainer's data-direction decisions of 2026-11-06.

## Decision

1. **Two more text sources.** Besides PBY (`pby`, unchanged), the aligner accepts:
   - **Sefaria** (`sefaria`): a Hebrew version saved from Sefaria's version download (`/download/version/<title> - he - <versionTitle>.json`), cross-checked against `/api/texts/versions/<title>`.
   - **Project Gutenberg** (`gutenberg`): a plain-text ebook, for the edition it was proofread from only.
2. **What is accepted (fail-closed, `decide_sefaria_licence`, `decide_gutenberg_licence`):**
   - a Sefaria version whose licence string is exactly Sefaria's public-domain label, `Public Domain`, **and** whose `versionSource` is the catalogue record of a printing (an NLI record, an Internet Archive item or a Project Gutenberg ebook) **and** whose version title names the printing's year;
   - Project Gutenberg #43740 (*Bet Nekhot ha-Halakhot o Toratan shel Rishonim* I, Frankfurt am Main 1881), whose RDF record says `Public domain in the USA.` and whose credits name "The Internet Archive/Canadian Libraries". It is accepted only on the scan it was proofread from, IA `betnekhothahalak01horouoft`. Another ebook needs an entry in `GUTENBERG_EDITIONS`, which names the scan it was proofread from.
3. **What is excluded:**
   - CC BY-NC (any non-commercial licence), by the iron rule;
   - `unknown`, by the iron rule (no licence evidence);
   - a `Public Domain` label with no printing named, such as Torat Emet, On Your Way, Daat and Mechon Mamre: the text cannot be tied to the scanned edition;
   - CC BY and CC BY-SA: attribution and share-alike are acceptable in principle (open-release decision, item 4), but these labels on Sefaria are mostly modern editions or translations. Each needs its own decision.
   - Any other label, CC0 included, until a decision names it. The gate matches the label string exactly.
4. **Scans are unchanged.** Every text is aligned to a scan that passes the existing scan gate: Route B (Internet Archive, `decide_ia_rights` plus the per-item `rights_justification`) or Route C (Wikimedia Commons, under its own gate). Route A, Google-class scans fetched through NLI's API, stays out. `align --text-source sefaria|gutenberg` accepts Internet Archive scans only for now, because Route B's tooling exists.
5. **Contributors and the rights justification.** The text record lists every author, editor, translator and annotator, each with a Wikidata QID; the rights justification reads each death year from a saved Wikidata snapshot (P570), as for PBY.
   - Editors count as authors for the Israeli status (legal strategy, "Per-item rights justification").
   - A work that is an ancient compilation with a traditional attribution only, such as Avot de-Rabbi Natan or the Mekhilta de-Rabbi Shimon, may be marked `anonymous_work`. It then needs no author. The edition must be published more than 70 years before the as-of year (Copyright Act 2007, s. 40), and every named contributor (the editor) must still meet s. 38.
6. **Digitizer.** When Sefaria typed the text (`digitizedBySefaria`), the record's `text_digitizer` is "Sefaria". No uploader e-mail address is ever recorded, requested or committed, for texts or scans. IA metadata snapshots drop `uploader` and redact every e-mail address. An IA item whose only evidence of a known source is an uploader address fails the IA gate's known-source condition (`ia_anonymous_upload_no_known_library`) and is not used.
7. **Silver only.** Every pair stays `human_typed_edition_text_aligned`, `not_adjudicated`, `reference_eligible: false`. OCR places the text and is never the label.

## Per-row provenance

Every alignment page report (`work`) and every line row of a text-source alignment carries:

| Field | Content |
|---|---|
| `text_source` | `sefaria` or `gutenberg` (PBY rows are unchanged and carry none of these fields) |
| `text_version_title` | The printing: Sefaria's `versionTitle`, or the edition a Gutenberg ebook was proofread from |
| `text_version_source` | The printing's catalogue record: Sefaria's `versionSource` (an NLI record URL), or the ebook URL |
| `text_licence` | The exact licence label: `Public Domain` (Sefaria) or `Public domain in the USA.` (Project Gutenberg) |
| `text_api_url` | The URL the text was fetched from (the Sefaria version download, or the Gutenberg UTF-8 text) |
| `text_snapshot_sha256` | sha256 of the saved raw response. The snapshot itself is kept with the alignment root (`snapshots/`) |
| `work_id` | `sefaria_<slug>` or `gutenberg_<ebook>`; `pby_id` is null |
| `script` | The script stratum of the edition's text: `square`, `rashi` or `mixed` |
| `rights_justification_id` | As for every Route B line: the scan's rights justification |

## Normalisation

The text is the edition's, normalised only where the digital form adds what the print does not show:

- Sefaria markup removed: commentator anchors (`<i data-commentator=…></i>`), footnote markers and footnote bodies (they are printed elsewhere on the page, and the aligner places only the main text), and the dash Sefaria puts after a comment's bold opening quote;
- other tags unwrapped (`<b>`, `<small>`, `<big>`, `<strong>`), `<br>` as a line break, HTML entities decoded;
- niqqud and cantillation removed (these are unpointed prints);
- kept: `׳ ״ — ־` and the ASCII `'` and `"` Sefaria types for geresh and gershayim;
- Project Gutenberg: the body between the START and END lines, without the transcriber's note. Its `*…*`, `/…/` and `_…_` markup is unwrapped. Each typo correction the note lists is reverted to the printed reading where the corrected reading occurs exactly once; the others are reported.

## Consequences

- R8 lever 5(b) batch 1 (`rablines_v1`) is built from Sefaria public-domain versions and PG #43740 on Internet Archive scans of the same editions. One dense, abbreviation-heavy edition is held out whole as the future rabbinic eval or line_verify source (`docs/benyehuda_nli_lines.md`, "Reserved editions").
- A release that ships these lines credits Sefaria and Project Gutenberg as text sources in its NOTICE, beside the scan route notices.
