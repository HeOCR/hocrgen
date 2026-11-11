# 2026-11-11: Israeli court rulings: privacy scope and route

- Status: accepted (scope); the route is open pending the dataset licence check below
- Decided by:
  - **The privacy scope:** the maintainer (Shay Palachy Affek), 2026-11-11, relayed by heocr-lead. Asked about the scope proposed in data-collection's courts scout, he answered: "Yes, that scope".
  - **The route:** heocr-lead, 2026-11-11, applying `2026-11-10-legal-strategy.md`.
- Written by: `data-collection[claude/claude-code#shay-macbook-m4]@heocr/opensource`
- Context:
  - Copyright Act 2007 §6: judicial decisions have no copyright.
  - F8 decision 4 (`2026-11-06-f8-real-source-decisions.md`): automated access to government sites is allowed, but court rulings still need publication-ban screening.
  - The scout report, `tasks/modern-s6-scout/courts/report.md`, in the HeOCR agents workspace, 2026-11-11.

## Decision

1. **Scope: what may be taken.**
   - Only **judgments** (פסק-דין): no interim decisions (החלטה), orders or summaries.
   - Only these case types:
     - administrative appeals (עע"מ);
     - civil appeals (ע"א);
     - the High Court of Justice (בג"ץ).
2. **Exclusions,** applied before any text or image is read:
   - criminal appeals (ע"פ);
   - family leave to appeal (בע"מ);
   - any case whose name or parties include "פלוני" / "פלונית" / "אלמוני" / "אלמונית", or is otherwise marked anonymised;
   - any case under a publication ban or gag order, by a screen of the case metadata and the document text for publication-ban wording (e.g. "איסור פרסום", "חל איסור לפרסם", "נאסר פרסום", "בדלתיים סגורות"). A hit excludes the whole case.
   - The legally protected categories stay out even when they appear in an allowed case type: minors, sex-offence complainants, family and adoption matters, mental-health proceedings.
3. **Route.** A site's terms bind whoever downloads from that site (the HebrewBooks and NLI-API precedents in `2026-11-10-legal-strategy.md`).
   - **Not** `supremedecisions.court.gov.il`. Its terms of use (dated 5.10.2026) bar commercial use and threaten to block automated requests.
   - **Not** the lower-court Net HaMishpat FTP feed. It requires a signed undertaking. It stays out unless the maintainer signs one.
   - **Candidate:** the Hugging Face snapshot `LevMuchnik/SupremeCourtOfIsrael`, but only if its own licence is open and allows commercial use. See the findings below; no ingest until heocr-lead accepts them.
4. **Representation.** Rulings are born-digital (Word to PDF). Lines made from them are rendered captures, labelled from their text or glyph layer, as with Reshumot. They are reported as a **rendered stratum** in evaluation, never mixed with scans.
5. **Order.** Courts come after `reshumotlines_v2` and the OLB-aligned scanned Reshumot lines.

## Route findings (data-collection, 2026-11-11)

Checked from the Hugging Face API and the dataset card (`README.md`, sha256 `60941c18…45e`, last modified 2023-04-27):

- **Licence.**
  - The card's YAML says `license: openrail`, and the "Licensing Information" section reads "[More Information Needed]".
  - No licence text is in the repository: its files are `.gitattributes`, `README.md` and `cases_all.parquet`.
  - "OpenRAIL" is a family of licences with behavioural use restrictions, and the card does not say which variant or text applies.
  - So the terms that bind a downloader from this repository are **unknown**. By the iron rule (`2026-11-10-open-release-and-clean-inputs.md`), an unknown licence is out until clarified.
- **Content.**
  - The snapshot holds **text and metadata only, no PDFs or page images.**
  - Its `Path` and `FileName` fields point back to the court site, which this decision excludes.
  - So even with a clear licence, the snapshot gives no route to page images. Lines from it could only be rendered by HeOCR from the text, which makes them synthetic rendering, not publisher PDFs.
- **Provenance.** It was crawled from the Supreme Court site (2022; card created 2023-04-22) by Prof. Lev Muchnik (HUJI) and Dr. Inbal Yahav Shenberger (TAU), with Israel Innovation Authority grants.

**Consequence.** No compliant route to rulings' page images exists today. The options for the maintainer:

- (a) Ask the curators to state the licence. A CC0 or CC BY statement would allow text-only use, rendered by HeOCR.
- (b) Ask the Courts Administration (הנהלת בתי המשפט) for written permission for automated, commercial-capable access to the published judgments in the scope above.
- (c) Leave courts out.

Nothing is fetched until one of these resolves.
