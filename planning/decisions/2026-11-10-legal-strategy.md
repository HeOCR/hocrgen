# Decision 2026-11-10: HeOCR's legal strategy for public-domain scans

- **Date:** 2026-11-10
- **Decided by:** the maintainer (Shay Palachy Affek)
- **Status:** accepted
- **Applies to:**
  - every scan HeOCR ingests, and every artefact derived from scans: training data, line crops, glyph banks, synthetic pages, benchmark page images and trained weights;
  - every rights gate and release NOTICE.
- **Full text:**
  - the strategy, verbatim: `docs/legal/2026-11-10_legal_strategy.md`;
  - the prompt that produced it: `docs/legal/2026-11-10_consultation_prompt.md`.
- **Builds on:**
  - the 2026-11-10 open-release decision (`2026-11-10-open-release-and-clean-inputs.md`);
  - heocr-engine decision 0014.
- **Supersedes:**
  - condition 2 of the 2026-11-09 Internet Archive decision ("not a Google scan");
  - item 2 of the 2026-11-10 open-release decision ("published without an explicit licence"), for the licence only. The NOTICE part stays.
- **Resolves:** the conflict between hocrgen decision 9 (2026-11-06, Google-digitized Commons files accepted) and the 2026-11-09 IA rule. Decision 9 stands.

## Decision

> "This is our legal strategy and outlook; I ascribe to it completely" (Shay Palachy Affek, 2026-11-10)

The maintainer adopted the analysis in `docs/legal/2026-11-10_legal_strategy.md` in full. Its operative rules for
HeOCR:

1. **No new right in a faithful scan.** A faithful photographic or mechanical scan of a public-domain printed book carries no new copyright in Israel (*Interlego*, Copyright Act 2007) or in the US (*Feist*, *Bridgeman*). HeOCR treats such scans as public domain.
2. **Route A is out: Google-digitized scans fetched from NLI.** NLI tags these "public domain, non-commercial use". Fetching them through NLI's IIIF API puts HeOCR in a contract with NLI, so they stay out of training and out of every published artefact.
   - NLI's own "public domain, free use" scans stay in, with attribution.
   - Route A reopens only with NLI's written waiver allowing CC0 / CC BY / Apache-2.0 release.
3. **Routes B and C are in: Google-digitized scans fetched from the Internet Archive or Wikimedia Commons.** They are accepted across the whole pipeline: training, line crops, glyph banks and benchmark page images. HeOCR has no contract with Google or NLI on these routes, and Google's front-page usage guidelines are requests, not a contract.
4. **Same edition on several routes: take it from B or C.** If an edition is on NLI as Route A and also on IA or Commons, ingest it only from IA or Commons. Record that URL and the file's sha256 as the source of record.
5. **Hygiene before any crop, glyph or benchmark page:**
   - Drop Google's front "usage guidelines" page, and crop out the "Digitized by Google" watermark, to avoid any suggestion of trademark endorsement. The fact that Google digitized the scan stays in the metadata.
   - Record per-item provenance:
     - book and edition ids, author death year, publication year;
     - acquisition route (`internet_archive` / `wikimedia_commons` / `nli_free_use`);
     - source URL and sha256;
     - digitizer, for example "Digitized by Google; retrieved via Internet Archive";
     - transcription source and its licence.
   - Ship the strategy's RIGHTS AND PROVENANCE NOTICE (section 6, step 3), adapted, and a `TAKEDOWN_POLICY.md`: a contested item is quarantined at once, and any removal is logged in a public changelog.
6. **Licences:**
   - page images, line crops and glyph banks: **CC0 1.0**, with HeOCR claiming no copyright in them;
   - HeOCR's own selection, alignment and annotation: **CC0 1.0** (or CC BY 4.0 where a product needs it);
   - weights: Apache-2.0, as before.
7. **Points for a qualified lawyer.** These are recorded and do not block work:
   - whether NLI's API terms bind HeOCR in Israel;
   - whether they reach model weights;
   - checking every contributor on a page (commentaries, approbations, editors) and each book's US status;
   - German §72 UrhG for full-page benchmarks on EU mirrors.

   The contributor and US-status check is done per item through the provenance fields.

## Why this matters

- **It is the foundation of the open release.** Every HeOCR artefact is released for any use, commercial use included, and has to stay releasable. This strategy says which scans meet that bar and why, so a release cannot be challenged later, or can be repaired quickly if it is.
- **It opens older printed Hebrew.** Most pre-1900 Hebrew scans at NLI were digitized by Google; earlier, 77 of 104 NLI candidates were Google-class. Many of the same editions are on the Internet Archive (`bub_gb_…`, `…goog`) or on Commons, and Routes B and C make them usable. Recognizing old print is HeOCR's main weakness.
- **It is one reference for every contributor.** Rights gates, adapters, NOTICEs and model cards follow this record instead of re-deciding rights case by case.

## Still open

- **Condition 4 of the 2026-11-09 IA decision** ("files that came from NLI, for example through Wikimedia Commons, stay under NLI's gate"). The strategy's reasoning, which is no contract on Routes B and C, also covers NLI-origin files on Commons or IA, but the strategy discusses only Google-digitized files there. Until the maintainer confirms, condition 4 stands.
- **The citations in the strategy have not been independently verified.** Check each one against its primary source before it appears in a public NOTICE.

## Consequences

- **The IA gate (`hocrgen.fetchers.ia_iiif.decide_ia_rights`)** accepts Google-digitized items (`bub_gb_…`, `…goog`, Google scanner or sponsor) with their own `source_class`. It records the digitizer, and still applies conditions 1, 3, 4 and 5.
- **The NLI gate (`decide_nli_rights`) is unchanged.** It still rejects `public-domain-non-commercial-use`, which is Route A.
- **Line building, glyph harvesting and benchmark export** drop Google cover pages and crop Google watermarks, and carry the provenance fields above.
- **The F8f scouting pass** searches IA and Commons for the Google-class NLI editions, the pre-1900 ones first.
- **pgb-v1 and pgb-v1b:**
  - Their Google-digitized source (Index 260883, via IA) becomes acceptable.
  - Their 2 Commons files from NLI wait on the condition-4 question.
  - The unnamed-scanner IA upload and the two unlicensed local files still lack evidence.
  - The banks stay quarantined in any case, because of eval contamination.
- **The pools get CC0 1.0** in place of the `PROJECT-SYNTHETIC` placeholder, with a NOTICE crediting NLI for the glyphs and Project Ben-Yehuda for the text.
- **A request to NLI for a written waiver on Route A** is drafted for the maintainer to send. Nothing is sent without him.
