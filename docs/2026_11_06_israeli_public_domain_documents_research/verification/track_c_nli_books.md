# Track C: National Library of Israel and printed-book collections

Researcher: Claude (subagent), 2026-11-06. Read-only. No sign-ins, forms, cookie banners or bulk downloads.

## How pages were loaded (read this first)

- **The live nli.org.il, hathitrust.org, babel/catalog.hathitrust.org and hebrewbooks.org pages are behind Cloudflare bot challenges.** curl and WebFetch got 403. The built-in browser got an interactive "Verify you are human" checkbox, which I did not click.
- So for those sites I read **Wayback Machine snapshots** (raw `id_` captures). Each claim gives the snapshot date. "(verified 2026-11-06, Wayback snapshot YYYY-MM-DD)" means I loaded that capture today. It does not mean I loaded the live page.
- These endpoints answered directly and were checked live today:
  - `iiif.nli.org.il` (NLI IIIF Presentation and Image API, no key);
  - `catalog.hathitrust.org/api/volumes/...` (Hathi Bib API);
  - `benyehuda.org`;
  - GitHub (`gh api`);
  - Zenodo API.
- `api.nli.org.il` (NLI Search API) is also behind Cloudflare. NLI's docs publish a guest API key, but I did not use it.

---

## 1. NLI Historical Jewish Press (JPress, "עיתונות יהודית היסטורית")

**Identity:**
- Operator: National Library of Israel, in partnership with Tel Aviv University.
- Portal: https://www.nli.org.il/he/discover/newspapers/jpress
- Titles and issues live under `https://www.nli.org.il/{he,en}/newspapers/{code}/...`, e.g. `/en/newspapers/mgd` for HaMagid.
- Runs on **Veridian**. URLs carry Veridian `e=-------en-20--1--img-txIN|txTI---` parameters, and `a=is&oid=hzf18620204-01&type=staticpdf` serves PDFs *(verified 2026-11-06, Wayback snapshot of the hzf issue page)*. Veridian announced an NLI relaunch on its platform *(inferred from a search-result title on veridiansoftware.com; page not loaded)*.

**Gemini claim check:**
- "Hundreds of thousands of Hebrew pages, 19th to mid-20th century, with OCR." **Understated.**
  - The JPress landing page shows "340 years, 6,750,145 pages, 30 languages, 1,030 titles" *(verified 2026-11-06, Wayback 2026-10-25)*.
  - The whole NLI newspaper platform showed "1,933 titles, 12,243,347 pages" *(Wayback 2025-01-03)*.
  - OCR exists: yes.
- "ABBYY OCR; ALTO XML with HPOS/VPOS per word; text downloadable via the NLI API or researcher XML dumps from the digitization lab." **Not supported.**
  - The project's own "About" page says OCR and article segmentation were done with Olive Software's **Active Paper**, with output stored as XML. It does not mention ALTO or ABBYY *(verified 2026-11-06, Wayback 2024-12-03 of `/he/discover/newspapers/jpress/about`)*.
  - The current Veridian viewer offers issue, page and article PDFs and a text panel. I found no public ALTO download or newspaper API endpoint.
  - A researcher route exists only case by case. For example, an Open University OMILab project was given "access to selected image and OCR output files at the back end of JPRESS" *(inferred, search snippet of openu.ac.il; not loaded)*.
  - **ALTO availability: `Needs verification`.** Ask NLI directly.

**Content:**
- Printed newspapers, 18th century to the present. Multilingual; Hebrew is a large subset.
- Sample PD titles:
  - HaMagid (מגיד), 1856–1903: "2,266 issues, 19,445 pages".
  - HaLevanon: 772 issues, 7,645 pages.
  - HaMelitz: 6,062 issues, 35,879 pages.
  - Havatzelet: 1,856 issues, 14,241 pages.
  - Ha-Am (Moscow): 140 issues, 1,188 pages.
  - Source: title pages *(verified 2026-11-06, Wayback 2026-10)*.
- Content type: `printed_historical`, plus `printed_modern` for post-1948 titles such as Davar.

**Text availability:** machine OCR only (Olive Active Paper, possibly re-processed for Veridian; `Needs verification`). Article-segmented. **OCR, so never gold.** Value is diagnostic and weak labels only.

**Access:**
- Web viewer; per-issue PDF (`type=staticpdf`); per-article PDF (`type=logicalsectionpdf`); page tiles (`type=pagetileimage`).
- No IIIF observed for newspapers. Veridian `f=XML` output is unconfirmed (`Needs verification`).
- No public bulk dump.
- **Terms prohibit systematic copying.** JPress terms, §2B: "It is expressly prohibited to systematically copy, download, or distribute a significant portion of any collection". The same section also bars retaining "substantial portions" *(verified 2026-11-06, Wayback 2026-10-27 of https://www.nli.org.il/en/discover/newspapers/jpress/terms-of-use)*.

**Rights:**
- **Rights are set per newspaper title.** §2A: "The applicable terms of use for each newspaper are displayed on the newspaper's page by clicking 'Usage Options – Further Information'" *(same snapshot)*. I found no per-issue statement. Whether issues can override their title is `Needs verification`.
- Observed per title *(Wayback snapshots, 2025-12 to 2026-10)*:
  - **HaMagid (`/en/newspapers/mgd`)** and **Ha-Am Moscow (`/en/newspapers/ham`)**: "You may use this item freely for any purpose and without any limitations. This item is part of the public domain…".
    - This is the PD/free-use text. It does **not** literally use the string "Any Use Permitted", which hocrgen's `exact_match` relies on.
  - **Davar (`/en/newspapers/dav`)**:
    - EN page, 2025-12: "non-commercial teaching and research purposes only".
    - HE page, 2026-10: stricter, "חל איסור על העתקה, פרסום, הפצה… ללא הסכמה מראש".
    - Rights holder: Machon Lavon.
    - So title statements change over time, and EN and HE can differ.
  - **HaLevanon, HaMelitz, Havatzelet**: no usage statement on the title page at all, although all are clearly PD by age. The label is missing, not restrictive.
- JPress §3B requires a credit line: "Historic Jewish Press website www.JPRESS.org.il, established by the National Library and Tel Aviv University, [Newspaper Name]."
- Proposed:
  - PD titles: `normalized_license: PD-IL`, `rights_classification: open_with_attribution` (the credit is a ToU duty).
  - Restricted titles: `RESTRICTED-NONOPEN`, `blocked`.
  - **Status: `review_only`**, because the systematic-copying ban needs written NLI permission before any harvest at scale, and labels are missing for some PD titles.

**Fixture feasibility:**
- A few page images from a PD-labelled title (HaMagid) are plausibly fine. The ban targets "a significant portion", and the credit line can be embedded.
- Checked:
  - https://www.nli.org.il/en/newspapers/mgd (PD free-use label)
  - https://www.nli.org.il/en/newspapers/ham (PD free-use label)
  - https://www.nli.org.il/he/newspapers/hzf/1862/02/04/01/page/5/ (HaTsfira 1862 issue page with PDF link; title page had no rights block in the 2025-01 snapshot)
- OCR from the text panel can go in the fixture as clearly flagged `ocr_machine` diagnostics.

**HeOCR value:** **medium.** It is the largest Hebrew historical-print image pool, and PD titles are clearly flagged. But there is no gold text, harvest at scale needs permission, and the OCR is old Olive output.

**Open questions:**
1. Do we ask NLI (copyright@ or the newspapers team) for permission to sample N pages per PD title, and/or for Veridian XML/OCR access?
2. For PD titles with no label, do we accept an age-based PD-IL determination (e.g. pre-1900 titles), or require an NLI label?
3. Should hocrgen's NLI rights strategy key on the stable licence slug rather than on display strings? See §2.

---

## 2. NLI digital collections generally (books, pamphlets, posters/ephemera, archives) and APIs

**Identity:**
- Catalog: https://www.nli.org.il/en/search
- Developer docs: https://www.nli.org.il/en/research-and-teach/open-library, with sub-pages `/search-api`, `/presentation-api` and `/image-api` *(verified 2026-11-06, Wayback 2024-12 / 2025-05)*.
- IIIF: `https://iiif.nli.org.il/IIIFv21/{RecordId}/manifest` and `.../DOCID/{DOCID}/manifest`; images at `https://iiif.nli.org.il/IIIFv21/{FL…}/{region}/{size}/0/default.jpg` (IIIF Image API 2, level 1) *(verified live 2026-11-06)*.
- The official GitHub repo `NationalLibraryofIsrael/API` is empty *(verified 2026-11-06)*.

**Gemini claim check:**
- "IIIF and OAI-PMH." IIIF holds (verified live). OAI-PMH is `Needs verification`; I found no NLI documentation of it.
- "Any PD item can be downloaded at full resolution with simple scripts." **Overstated**, for three reasons:
  1. Several book manifests return **0 canvases**. Examples: `990017916250205171` and `990020294270205171`, both labelled PD free-use; `990013152300205171`.
  2. A large class of PD books is labelled **non-commercial** because Google digitized them (below).
  3. The general NLI ToU says copyright in site material belongs to NLI "unless explicitly stated otherwise". It bars copying or redistribution "without the prior written consent of the National Library" *(verified 2026-11-06, Wayback 2025-09-26 of https://www.nli.org.il/en/at-your-service/terms-of-use)*. The per-item statement is the "explicitly stated otherwise" that opens items up.
- "Filter by Availability: online → access: free / PD." Facet names are unverifiable (the catalog UI is Cloudflare-blocked). See the licence-slug finding below instead.

**Key finding: a machine-readable rights hook.** Every IIIF manifest carries a `license` URL whose slug is a controlled NLI rights category *(verified live 2026-11-06 on about 25 manifests)*.

Slugs observed in manifests:

| `license` slug | Meaning (from NLI's own page) | Observed on | Proposed hocrgen mapping |
|---|---|---|---|
| `public-domain-free-use` | "may be used for any purpose, including commercial use" (Wayback 2026-10-20) | Books such as `001268237` (*Romemut El*, Zolkiew 1764, 208 canvases), Ktiv manuscripts, archive item `990037277000205171` (1909) | `PD-IL` / `open` / `allowed`. Same class as the existing `nli_any_use_permitted`; the item-page label for this class is "Any Use Permitted" (verified on book `990017916250205171`, Wayback 2024-11-12) |
| `public-domain-non-commercial-use` | Most likely the Google Books class. The `nli-research-google-books-public-domain` page says: "You may use the digital copy for personal non-commercial purposes. It is prohibited to distribute the digital copy to third parties." It also allows using "a portion of the digital copy for any purpose including commercial use". The restriction stems from "an agreement between the National Library and Google" (Wayback 2025-01-22). The slug-to-page link is *(inferred)* | Many 18th–20th-century Hebrew books: `990010941190205171` (1805, 152 canvases), `001835646` (1837, 524), `001088711` (Warsaw 1862, 608), `990019347240205171` (1902, 144), `001323985` (Sholem Aleichem, 1914, 76) | `RESTRICTED-NONOPEN` / `restricted_review_only` / `review_only`. Or a new value such as `PD-IL-NC-CONTRACT`. The "portion for any purpose" clause may permit small fixtures; maintainer call |
| `free-use-license` | NLI owns the copyright and "permits the use of the item for any purpose, including commercial use", with credit to creators (Wayback 2026-10-21) | (slug listed in the Wayback CDX; not seen in a sampled manifest) | Needs a new value, e.g. `NLI-FREE-USE-ATTRIBUTION`; `open_with_attribution` |
| `fair-use` | "This item is subject to copyright… made available… in reliance on the Fair Use doctrine" (Wayback 2026-10-25) | **Nearly all sampled ephemera and posters**, including 1924–1929 municipal notices (`997000928650405171`, `997001073240405171`, `997000916950405171`, `997001247430405171`) | `RESTRICTED-NONOPEN` / `blocked` |
| `no-license-subject-to-copyright` | (page not captured) | Archives: `990032538530205171` (1932–34), `990041997330205171` (1969) | `RESTRICTED-NONOPEN` / `blocked` |

Other slugs exist in Wayback CDX. Their pages were not read:
- `nli-non-commercial`
- `nli-non-commercial-research-teaching`
- `nli-research-teaching`
- `nli-copying-prohibited`
- `library-premises-fair-use-research-and-teaching`
- `no-restrictions-fair-use-research-and-teaching`
- `hebrew-manuscripts-public-domain-non-commercial-copying`
- `public-domain-photographs-free-use`
- `nli-public-domain`
- `nli-ownership`
- `upper-level-archive`

**Content:**
- Printed books from the 16th century on, pamphlets, posters/ephemera ("sheets"), archives, manuscripts.
- **New beyond `nli_any_use_permitted`:** all 27 current seeds are `/manuscripts/` items, so the existing adapter covers no printed material in practice. New scope would be:
  - `printed_historical`: `public-domain-free-use` Hebrew books. Example: `001268237` (1764).
  - Google-digitized PD books: a large pool, but non-commercial.
  - Posters and ephemera: almost all `fair-use`, even 1920s items, so **blocked unless HeOCR makes its own PD determination**. Under Copyright Act §40, an anonymous or pseudonymous work lasts 70 years from publication. Under §42, state works last 50 years. Municipal works are not state works. This would be HeOCR's own legal judgment against NLI's conservative label, and is a maintainer decision.
  - Archives with `public-domain-free-use`: mostly handwritten, so they overlap HASH and the "NLI archives" already covered.

**Text availability:** images only. No OCR exposed via IIIF. Hebrew books in Primo may have OCR in the PDF viewer (`Needs verification`).

**Access:**
- IIIF manifests and images: open, no key, worked from curl today.
- Some manifest IDs return 403 or 500, e.g. `/DOCID/NNL_ALEPH990017916250205171/manifest` gave 403 while `/990017916250205171/manifest` gave 200.
- Search API: `https://api.nli.org.il/openlibrary/search?api_key=…&query=…`, with `material_type`, `availability_type` and `output_format` parameters. It needs a key; NLI publishes a guest key with "limited access permissions" *(docs verified via Wayback 2025-05-23; endpoint Cloudflare-blocked today)*.
- No documented rights filter in the Search API. Whether a rights field is returned is `Needs verification`.
- Enumeration therefore needs Search API results, then a per-manifest `license` check.

**Rights:** per item, as in the table. A collection label is not trustworthy; even 1920s posters are marked `fair-use`.

**Fixture feasibility:**
- Yes, for `public-domain-free-use` items. Commit 1–3 downscaled page JPEGs plus the manifest and its `license` URL.
- Checked live:
  - https://iiif.nli.org.il/IIIFv21/001268237/manifest (*Romemut El*, 1764, PD free-use; `info.json` for FL89121331 is 2403×4027)
  - https://iiif.nli.org.il/IIIFv21/990003000580205171/manifest (Ketubbah, Jerusalem 1860, PD free-use, Ktiv attribution; `FL58252370/full/200,/0/default.jpg` returned 200)
  - https://iiif.nli.org.il/IIIFv21/001088711/manifest (counter-example: Google class, non-commercial)

**HeOCR value:** **high** for `printed_historical` images, plus the reliable rights slug. Still images-only, so tier 4. It can be upgraded to tier 1 via Ben-Yehuda alignment (§6).

**Open questions:**
1. Switch the `nli` rights strategy from display-string `exact_match: "Any Use Permitted"` to matching the IIIF `license` slug (`public-domain-free-use`)? The slug is language-neutral and stable. The display string differs between catalog items ("Any Use Permitted") and newspapers ("You may use this item freely…").
2. Is the Google-class "portion of the digital copy for any purpose" clause enough for small fixtures?
3. Do we want our own PD determination for pre-1955 NLI ephemera labelled `fair-use`, or do we respect NLI labels? I recommend respecting them by default.
4. Do we request a Search API key? It needs sign-up, so it is the maintainer's action.

---

## 3. Ktiv: International Collection of Digitized Hebrew Manuscripts (NLI)

**Identity:**
- NLI with the Friedberg Jewish Manuscript Society, plus partner libraries (BL, BnF and others).
- Current site: https://www.nli.org.il/en/discover/manuscripts/hebrew-manuscripts.
- The Gemini URL `web.nli.org.il/sites/nlis/he/manuscript` is the legacy site *(inferred)*.

**Gemini claim check:**
- "Almost 100,000 manuscripts; almost all absolutely PD." **The rights part is false.**
  - Per the Ktiv terms page: "each collection has set its own Terms of Use for the manuscripts it owns". The site also says appearing on the website does not mean free use *(search-index text of https://www.nli.org.il/en/discover/manuscripts/hebrew-manuscripts/terms-of-use; the Wayback capture is JS-rendered and empty, so I did not load the text myself)*.
  - Partner items such as JTS forbid copying or publishing the digital copy *(same source)*.
  - Scale: about 90,000 documents and 8M pages per IFLA (2014–18), and about 45,000 manuscripts and 4.5M images at launch *(inferred, search snippets)*.
- "IIIF manifest for every manuscript." Holds for the samples checked (live).

**Content:**
- Hebrew manuscripts, mostly medieval and early modern.
- **The share from the 18th century on is `Needs verification`.** It needs the Search API with date facets, which are Cloudflare-blocked.
- The hocrgen seeds already include 18th–20th-century ketubbot, e.g. Bozzolo 1794 and Tangier 1901.

**Text availability:**
- Ktiv itself: images only.
- External transcription sets are mostly medieval. Example: the BiblIA ground-truth dataset (Zenodo 5167263, **CC-BY-NC-SA-4.0**). Its HTR model (Zenodo 5468286) is CC-BY-SA-4.0. hocrgen's packaged `biblia_open` source is a third, unrelated thing: Commons image records with no transcriptions. So `biblia_open` does **not** cover the BiblIA ground truth, and that ground truth is non-commercial (see Track D §1). *(Corrected in F8a review.)* Tikkoun Sofrim (Zenodo 4736094) is crowd transcription of Tanhuma manuscripts and is a lead for the HTR track.
- I found no Ktiv-wide transcription layer.

**Access:** IIIF manifests (live). Rosetta viewer.

**Rights:**
- Per item and per owning institution.
- The IIIF `license` slug may not reflect a partner library's conditions. BL manuscript `990001286000205171` (15th–16th c.) has `license: public-domain-free-use` with attribution "From the collections of: THE BRITISH LIBRARY" *(verified live)*.
- A dedicated slug `hebrew-manuscripts-public-domain-non-commercial-copying` exists (Wayback CDX).
- **Verify the item-page text for partner items before trusting the slug.**
- Proposed: reuse `nli_any_use_permitted` (`manuscript_scan`); no new source needed. Partner-owned items should be `review_only` unless the item page itself says free use.

**Fixture feasibility:** already done in hocrgen (27 manuscript seeds). Checked: https://iiif.nli.org.il/IIIFv21/990003000580205171/manifest, and `990027114740205171` and `990001286000205171` (seeds 001 and 002).

**HeOCR value:** **medium** for HeOCR (it is mostly pre-18th century). It is also mostly out of scope for HASH, which is 18th century on.

**Open questions:**
1. Should HeOCR proper (not HASH) take pre-18th-century Ktiv images? There is no text, and BiblIA already provides the gold.
2. Should hocrgen check the item page, and not only the manifest, for partner-library items?

---

## 4. HebrewBooks.org

**Identity:** operated by "The Society for Preservation of Hebrew Books", a US 501(c)(3). https://hebrewbooks.org/. Terms: https://hebrewbooks.org/media/terms.html.

**Gemini claim check:**
- "65,000+ printed books, free PDF download." **The count holds:** "66,212 Classical Hebrew Books for Free Download" *(verified 2026-11-06, Wayback 2026-10-27 of the home page)*.
- **Reuse rights are wrong.** Downloads are licensed for personal use only.

**Content:** rabbinic and Torah literature, printed (plus some manuscripts). Mostly 16th–20th century, with many 20th-century American works. Nearly all Hebrew. Content type `printed_historical` / `printed_modern`.

**Text availability:** OCR. The site offers "OCR Search" across book contents, so the PDFs have a text layer *(inferred)*. Never gold.

**Access:** web and PDF only. The ToU bans "any scraper, robot, spider, or other automated mechanism to access the Site or download the Publications" *(verified, Wayback 2026-10-10)*.

**Rights:**
- The ToU covers both PD and permissioned books with no per-book distinction: "Certain of these Publications have entered the public domain; others have been provided… with the permission of the copyright owners". It grants a license "solely for your personal use", with "No commercial use" and no redistribution beyond free personal-use copies.
- No per-book rights field was seen on the home or about pages. Book pages were Cloudflare-blocked even in Wayback (`Needs verification`).
- **Legally unclear:** even PD-age books are wrapped in a contractual licence, and permissioned books are mixed in.
- Proposed: `RESTRICTED-NONOPEN` / `blocked`. Status **`blocked`**.

**Fixture feasibility:** no.

**HeOCR value:** **low** as a source. At most, use it as a pointer to identify editions, then fetch PD scans elsewhere (NLI `public-domain-free-use`, Internet Archive PDM).

**Open questions:** none, unless the Society grants written permission.

---

## 5. HathiTrust (Hebrew volumes)

**Identity:** HathiTrust Digital Library (hosted by the University of Michigan). https://www.hathitrust.org. Bib API: `https://catalog.hathitrust.org/api/volumes/{brief|full}/{idtype}/{id}.json` (live).

**Gemini claim check:**
- "Tens of thousands of Hebrew titles." The count is **`Needs verification`**. Catalog and full-text search are Cloudflare-blocked, and the authoritative route (the monthly Hathifiles TSV, about 1 GB) is a bulk download.
  - 2012/2015 HathiTrust slides reportedly list Hebrew at about 5% of content. That share is *unverified and implausibly high*, so do not rely on it.
- "Full datasets via HTRC." **Imprecise.**
  - Bulk text comes from the **HathiTrust Research Datasets**, which are separate from HTRC. They are "available to researchers to directly download in bulk for non-commercial research purposes" after an approval process.
  - Researchers outside the US get only the `*_world` sets.
  - Google-digitized sets need an institution-signed Google Distribution Agreement. Its terms include "May not be re-hosted" and "May not be shared with third parties".
  - Source: *(verified 2026-11-06, Wayback 2025-07-29 of the research-datasets page)*.

**Rights codes** (HathiTrust Access Determination PDF, *verified via Wayback 2025-04-15*):
- `1 pd`: public domain, full view for all.
- `9 pdus`: "Public domain only when viewed in the United States". Users in Israel are denied.
- `19 icus`: PD only outside the US.
- `5 und`: undetermined, denied.
- `2 ic`: in copyright.
- Access profile `google`: "PDF download only if logged in".
- The pd-vs-pdus cutoffs for non-US works have shifted over time (roughly 1898–1927 or 1873–1923 windows in older docs). Check per volume.
- Sample: Bib API for record 008399396, *Seder ha-Kinot* (Rödelheim 1880, `lang008=heb`), returned `nnc1.0038495767 pd Full view Columbia University` *(verified live 2026-11-06)*. Older mirrors listed it as pdus, so codes change as works age.

**Text availability:** OCR (Google or other), per page via the viewer and datasets. Never gold.

**Access:**
- The Acceptable Use Policy bans attempts to "automate download of material from HathiTrust… in bulk (including… page images, page text, or metadata)", except for Hathifiles and Datasets *(verified, Wayback 2026-05-27)*.
- HTRC Analytics gives non-consumptive, derived-data access only.

**Rights:**
- Per volume. Only `pd` volumes that are **not Google-digitized** are cleanly reusable from Israel.
- Proposed:
  - Non-Google `pd`: `PDM-1.0` or `PD-IL` after our own Israeli-term check; `open`.
  - Google-digitized `pd`: `RESTRICTED-NONOPEN` / `restricted_review_only`.
  - `pdus`, `ic`, `und`: `blocked` from Israel.
- **Status: `review_only`.**

**Fixture feasibility:**
- Possible for a non-Google `pd` Hebrew volume via the single-page viewer (no automation).
- I could not confirm the digitization agent for `nnc1.0038495767` (`Needs verification`). Record: https://catalog.hathitrust.org/Record/008399396.

**HeOCR value:** **low–medium.** It mostly duplicates NLI and Google Books holdings under worse terms for an Israeli project.

**Open questions:**
1. Should someone with US/institutional access run the Hebrew count (full-text search with `language:Hebrew`, `pd`, non-Google)?
2. Is it worth pursuing at all, given that NLI covers the same Google scans?

---

## 6. Project Ben-Yehuda (benyehuda.org)

**Identity:**
- Run by the association for computerizing Hebrew literature (Project Ben-Yehuda).
- Site: https://benyehuda.org.
- Dump: https://github.com/projectbenyehuda/public_domain_dump (latest release `2026-03`, 2026-03-07).
- API: https://benyehuda.org/page/api (key required, free self-service, "no more than 50 requests per minute").
- All *(verified 2026-11-06, live)*.

**Gemini claim check:**
- "Tens of thousands of works, all PD, hand-typed." **Mostly holds, with caveats.**
  - The site shows 66,963 works.
  - The dump README says "over twenty thousand public domain works". The 2026-03 `pseudocatalogue.csv` has 26,455 rows.
  - The **site is not all PD.** It hosts works whose rights expired "או שעבורן ניתנה רשות פרסום" (or that were published with permission). Only the PD subset is in the dump. Each work page carries a label such as "נחלת הכלל".
- "Dump in text/JSON with rich metadata." **Partly false.** Formats are txt (with and without niqqud) and HTML, plus a CSV catalogue (title, authors, translators, Wikidata URIs, genre, original language, `source_edition`). There is no JSON in the dump; the API returns JSON.
- "Some works link to scans of the original NLI edition." **False as stated.** `source_edition` is free text, present in 21,205 of 26,455 rows, and **contains no URLs**. Only 1,023 rows contain a Gregorian year (253 before 1930). The work page I checked (`/read/10`) has no scan link.

**Rights:**
- The dump LICENSE says: "The data files in this repository are in the public domain, so you are free to make any use of them". Credit is requested, not required.
- The GitHub licence field is "Other".
- The text is `PD-IL` / `open`. Status **`allowed` for the text**. The licence of any image pair is that of the **scan source**.

**Content:** literary Hebrew (poetry 13k, articles 7k, prose 3.5k…), mostly the Haskalah and Revival eras.

**Text availability:**
- Human-typed and proofread, at the work level.
- Not page- or line-aligned to any edition. Niqqud is sometimes added; page breaks and line breaks are not preserved; footnotes are reformatted *(inferred from the site's note that citations should not follow "המהדורה המודפסת שעליה התבססנו")*.

**Alignment feasibility (gold page pairs):** **feasible but labour-heavy, and it gives silver until checked.**
- Pipeline:
  1. Match a BY work to a PD scan of *the same edition*. The best candidates are NLI `public-domain-free-use` books or Internet Archive PDM uploads.
  2. OCR the scan.
  3. Fuzzy-align the BY text to page OCR (e.g. Smith–Waterman or passim-style).
  4. Cut per-page and per-line text.
  5. Human-verify the diffs before promoting to gold.
- Obstacles:
  - Most `source_edition` values are post-1948 collected-works editions (Dvir and similar). Their scans at NLI are likely copyright or `fair-use`.
  - Many pre-1930 first editions at NLI are Google-class, so non-commercial.
  - Niqqud and orthography normalization.
- Pilot candidates (from the catalogue):
  - ID 162, Kalman Schulman, *Safa Berura*, Vilna 1864.
  - ID 419, M. Z. Mane, *Kol Kitvei*, Warsaw 1913.
  - ID 104, S. L. Citron, *Me-Ahorei ha-Pargod*, Vilna 1923.
  - For each, find an NLI or IA scan and check its `license` slug.

**Fixture feasibility:** text yes (PD). An image–text pair only after a matching PD scan is found. Checked: https://benyehuda.org/read/10, the dump `LICENSE` and `README.md`, and the 2026-03 `pseudocatalogue.csv` (a single metadata file).

**HeOCR value:** **high** as the text side of an alignment pipeline. Low on its own (text-only).

**Open questions:**
1. Fund a 10-work alignment pilot, using NLI `public-domain-free-use` and IA scans only?
2. Contact BY volunteers to ask whether internal records note the exact edition and scan they typed from? Many volunteers type from NLI or HebrewBooks PDFs.

---

## Ranked summary

| Rank | Source | Text tier | Proposed licence / class | Status | HeOCR value | Note |
|---|---|---|---|---|---|---|
| 1 | NLI IIIF `public-domain-free-use` printed books (extends `nli_any_use_permitted` to `printed_historical`) | 4 (images) | `PD-IL` / `open` | allowed | high | Key on the manifest `license` slug, not the display string |
| 2 | Project Ben-Yehuda dump + PD scans (alignment) | 1 after verification | `PD-IL` text; scan's licence | allowed (text) | high | No scan links exist; edition matching is manual |
| 3 | JPress PD titles (HaMagid, Ha-Am…) | 3 (OCR) | `PD-IL` / `open_with_attribution` | review_only | medium | Per-title rights; systematic-copying ban; no public ALTO |
| 4 | Ktiv manuscripts | 4 | per item | already covered | medium | Partner rights are per owner; mostly pre-18th century |
| 5 | NLI Google-digitized PD books (`public-domain-non-commercial-use`) | 4 | `RESTRICTED-NONOPEN` (or new `PD-IL-NC-CONTRACT`) | review_only | medium | Large pool; NC plus no redistribution; "portion" clause |
| 6 | HathiTrust Hebrew `pd` (non-Google) | 3 | `PDM-1.0` / `open` (per volume) | review_only | low–medium | `pdus` blocked from Israel; count unverified |
| 7 | NLI posters/ephemera | 4 | `RESTRICTED-NONOPEN` (`fair-use`) | blocked | low (as labelled) | Even 1920s items are labelled `fair-use` |
| 8 | HebrewBooks.org | 3 | `RESTRICTED-NONOPEN` | blocked | low | Personal-use licence; anti-scraping ToU |

**Gemini claims that were wrong:**
- Ktiv "almost all PD".
- JPress "ALTO/ABBYY via API or dumps".
- "Any NLI PD item is fully downloadable by script" (non-commercial Google class; empty manifests).
- HebrewBooks free reuse.
- HathiTrust "datasets via HTRC" (it is Research Datasets, with Google and non-US limits).
- Ben-Yehuda "JSON dump with NLI scan links".
- JPress scale was understated.
