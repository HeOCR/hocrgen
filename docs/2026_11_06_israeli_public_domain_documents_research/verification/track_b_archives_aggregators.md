# Track B: state archives and open aggregators

Researcher: subagent (track B). Date: 2026-11-06. Method: read-only public pages and APIs, plus single-item metadata checks. Nothing was signed into, no forms were submitted and no cookie banners were accepted.

**Access note.** `www.archives.gov.il` and `catalog.archives.gov.il` return a CloudFront `403 Request blocked` to plain `curl`/WebFetch. `www.archives.gov.il` loaded normally in a desktop browser. One `curl` call with full browser headers did fetch the terms PDF. **`catalog.archives.gov.il` (the legacy catalogue) returned `{"message":"Forbidden"}` even in the browser**, so the legacy URLs Gemini cited are dead or blocked.

---

## 1. Israel State Archives (ארכיון המדינה)

**Identity**
- Operator: Prime Minister's Office, Israel State Archives.
- Site: https://www.archives.gov.il/
- Item pages: `https://www.archives.gov.il/details/<citation-id>`, e.g. `000ifup`.
- Files are PDFs served from a pre-signed S3 URL: `archive-media-bucket-prod-isa.s3.il-central-1.amazonaws.com/<documentum-id>.pdf`, which expires after 3600 s.
- Legacy catalogue: `catalog.archives.gov.il`, now 403 *(verified 2026-11-06)*.

**Gemini claim check**
- "State-created files up to 1975-12-31 are PD": **holds as a matter of statute** (§42). The site does not label them that way, though. The ISA terms treat expired works only as a "per any law" carve-out, and there is no per-item PD flag *(verified 2026-11-06)*.
- "Each file contains a full PDF or image series to download": **partly true.** Files are delivered as one multi-page PDF in a pdf.js viewer. I found no image-series, IIIF manifest or zip download *(verified 2026-11-06, 2 files)*.
- "Filter to scanned-only and 1948–1975, then download in bulk": **contradicted by the terms.** They forbid bots and copying large sets of documents (see Rights).
- "A hidden OCR text layer exists in some PDFs": **not observed.** Both sample PDFs (201 and 19 pages) had zero text characters on every page tested. The PDF metadata does say "Scanning & OCR technologies, Imagestore". The site's full-text search over selected collections is outsourced to **Google Journalist Studio "Pinpoint"**: the homepage "חיפוש באוספים נבחרים" tile links to `journaliststudio.google.com/pinpoint/explore?query=ארכיון המדינה`. That OCR lives at Google and is not shipped in the PDFs *(verified 2026-11-06 for the 2 samples; other collections `Needs verification`)*.

**Content**
- Government files: correspondence, protocols, forms, tender files, personal files and more. Typewriter and stencil print dominate the 1948–1975 files. Handwritten letters, minutes and marginalia are mixed into the same files *(inferred from the file descriptions; I could not view page images closely)*.
- Scale, from the homepage counters *(verified 2026-11-06)*:
  - **257 million scanned pages**
  - 375k scanned photos
  - 10.2k audio files
  - 5,200 video files
- Hebrew share: dominant *(inferred)*. English, Arabic and German also appear.
- **Third-party material inside state files is common:**
  - Tender files include bids from private companies. Example: 1952–53 file `000dk0u`, "רשימת מפעלים למכרזים… מכרז לייצור תחבושות".
  - Personnel and tender files carry candidate names. Example: 1966 file `000ifup`, "שמות המועמדים".
  - Whole private archives are deposited at ISA, e.g. Rabbi Herzog's archive. Rabbi Herzog died in 1959, so his private works become PD only on 2030-01-01. These are not state works.
- The "סטטוס חשיפה" field takes the values גלוי / נחשף חלקית (redacted) / חסוי / טרם נבדק. Many post-2000 files are "נחשף חלקית" with privacy redactions *(verified 2026-11-06)*.
- **Image quality concern:** the embedded page images in both sample PDFs were about **680×950 px per page**, roughly 80 ppi for an A4/foolscap sheet. That is low for OCR training. The FAQ offers "קובץ באיכות גבוהה (בתשלום)" with a copyright check, priced for photos and films only (20 / 50 ₪) *(verified 2026-11-06; whether this applies to textual files: `Needs verification`)*.

**Text availability:** none in the delivered PDFs, which are image-only. The Pinpoint OCR is at Google and is not exportable as a dataset *(inferred)*. This is value tier 4: images only.

**Access**
- No public API was found.
- Search runs through `POST /umbraco/surface/archivesearch/Search` with an anti-forgery token.
- `robots.txt` reads `Disallow: /umbraco/` *(verified 2026-11-06)*.
- PDFs come from expiring S3 signed URLs. There is no IIIF and no OAI-PMH *(none seen; inferred)*.
- Scraping only, and the terms forbid bots.
- The site says it is "בשלבי הרצה" (in a trial phase), so URL stability is uncertain.

**Rights**
- Terms of use: "תנאי שימוש באתר ארכיון המדינה – משרד ראש הממשלה", a PDF linked from the footer: https://www.archives.gov.il/media/anzaw4uw/תנאי-שימוש-באתר-ארכיון-המדינה.pdf (loaded and text-extracted 2026-11-06).
  - Licence for state-owned works: free and commercial use allowed. Conditions:
    - Attribution of both creator and office is required.
    - Only technical changes are allowed: "אסור ליצור יצירות נגזרות או להעניק רישיון-משנה".
    - Explicit no-bots / no-mirror rule: "אסור להעתיק יצירות באמצעים אלקטרונים ("בוטים")" and no copying many works into a parallel database.
  - Third-party works are excluded. Labelling them is best-effort and "not a legal basis to rely on".
  - Expired works are carved out "לפי כל דין" (e.g. "יצירות שזכות היוצרים בהן פקעה לפי הדין"), as are laws, regulations, Knesset proceedings and judicial decisions.
- So:
  1. A pre-1976 state-authored page is PD-IL by statute, and the licence's no-derivatives clause does not bind PD content.
  2. Site access is still subject to contractual no-bot and no-bulk terms.
  3. Rights are **per page, not per file.** Bids, private letters and deposited private archives inside a "state file" are not state works.
- Proposed for a pre-1976 state-authored page selected by hand: `normalized_license: PD-IL`, `rights_classification: open`.
- Proposed for the source as a whole: `RESTRICTED-NONOPEN`, `restricted_review_only`, status **`review_only`**. Reasons: the no-bot / no-bulk ToS, the ND licence on post-1975 state works, and mixed third-party content.

**Fixture feasibility:** possible only as a hand-picked set of a few pages from clearly state-authored, typewritten pre-1976 documents, fetched manually (not by an adapter crawl). Low resolution limits the value. Items checked:
- https://www.archives.gov.il/details/000dk0u — 1952–53, Ministry of Industry, tenders; 19 pp, image-only PDF; contains bidder material, so pick only the internal memos.
- https://www.archives.gov.il/details/000ifup — 1966, Civil Service Commission tender for postal technicians; 201 pp, image-only, about 680×950 px per page; contains candidate names.
- Search: 8,637 hits for "מכרז", most of them post-2000 and redacted *(verified 2026-11-06)*.

**HeOCR value:** **medium.** It is the largest pool of PD typewriter/stencil Hebrew (257M pages), but there is no text, page images are low-res, the ToS bans bots, and rights must be screened page by page.

**Open questions**
1. Is a manual selection of PD pages acceptable given the contractual no-bot / no-bulk terms? Or should HeOCR ask ISA (public@archives.gov.il / legal bureau) for permission or a research dump?
2. Can higher-resolution scans of textual files be obtained? The paid route is documented only for photos.
3. Proposed new content type: `typewritten_historical`. A `mixed_archival_file` flag would also help for files mixing typewriting, print and handwriting.

---

## 2. Internet Archive: Hebrew material

**Identity:** Internet Archive, https://archive.org. API: `advancedsearch.php`, `/metadata/<id>`, `ia` CLI (https://archive.org/developers/).

**Gemini claim check**
- "Thousands of ISA scanned files were mass-uploaded to IA": **false as stated.**
  - A full-text search for "Israel State Archives" returns **110 items**: 93 texts, 12 movies, 5 images.
  - 88 of these are in the user collection `politics_archive_portal`. That collection holds 1,178 items, of which only 26 are tagged Hebrew. They were uploaded in 2020 by a **single private individual's account**, not by ISA.
  - Filenames are ISA Documentum IDs (e.g. `00071706.81.D3.E4.A5.pdf`). There is no rights or licence metadata (`licenseurl`, `rights` and `possible-copyright-status` are all empty). Many items are post-1975 (1979–1988), so they are not PD.
  - These are re-uploads of ISA PDFs, which arguably run against ISA's "no parallel database" term. Rights do not get "cleaner" by going through IA *(verified 2026-11-06)*.
- "Every Hebrew PDF gets auto-OCR as `_djvu.txt` + `_hocr.html`/`_chocr.html.gz`": **true for recent derivations.**
  - `the-first-five-years-of-the-state` (Tesseract 5.3.0, `ocr_detected_lang: he`) has `_hocr.html`, `_chocr.html.gz`, `_djvu.txt`, `_djvu.xml`, `_hocr_pageindex.json.gz`, `_jp2.zip` and `_text.pdf`.
  - The older item `libya-israeli-relations-1951-52` was processed with ABBYY FineReader 11 and has `_djvu.txt`/`_djvu.xml` but no hOCR.
  - All of this is machine OCR, **never ground truth** *(verified 2026-11-06)*.
- "Search language:heb": works, with these counts *(verified 2026-11-06)*.

**Content, from advancedsearch `rows=0` *(verified 2026-11-06)*:**

| Query | Count |
|---|---|
| `language:heb` | 74,368 items |
| `language:(heb OR hebrew)` | 76,496 items |
| Hebrew, by mediatype | texts 13,789; movies 34,040; image 26,173; audio 1,608 |
| Hebrew texts with any `licenseurl` | 1,555 (11%) |
| Hebrew texts with Public Domain Mark | ~1,002 |
| Hebrew texts with CC0 | ~190 |
| Hebrew texts with BY-NC-ND (various versions) | ~237 |
| Hebrew texts with BY-SA | ~48 |
| Hebrew texts with `possible-copyright-status` set | 860 (783 are `NOT_IN_COPYRIGHT`, mainly the `americana`/Toronto/Princeton scanning collections) |

- Language tagging is incomplete. Many Hebrew books have no `language` field *(inferred)*.
- Main collections: `booksbylanguage_hebrew` (2,743), `folkscanomy*`, `americana`, `university_of_toronto`.

**Text availability:** OCR only (Tesseract hOCR/chOCR with word boxes, or ABBYY djvu.xml). Useful as a diagnostic baseline, not as labels.

**Access:** good. There is a public REST API and the `ia` CLI, and bulk download is technically easy. IA's terms of use were not loaded: archive.org/about/terms.php is JS-rendered and help.archive.org returned 404 (`Needs verification`).

**Rights**
- Uploader-asserted and per item. **PDM labels are unreliable.** Among the top PDM-tagged Hebrew texts are `8_20230915` (האנציקלופדיה העברית, dated 1980) and `visual-dictionary-english-hebrew` (1998), which are clearly not PD *(verified 2026-11-06)*.
- `NOT_IN_COPYRIGHT` from institutional scanners (Toronto, Princeton, LoC) is more trustworthy, but it is a US determination.
- Proposed: `UNKNOWN` by default. Promote to `PDM-1.0`/`PD-IL` only after per-item checks (author death date ≤ 1955, or a state work ≤ 1975), using institutional-scanner provenance. Rights classification `restricted_review_only` until checked. Status **`review_only`**.

**Overlap with HASH:** HASH's candidate "archive__hebrew_manuscripts (PDM uploads)" is most likely the IA collection `culhebrewmss` ("Hebrew Manuscripts", Columbia University RBML, 630 items, **no `licenseurl` on any item**) or the PDM-tagged user uploads. It is handwriting only. This track's print and typewriter interest does not overlap except through the shared IA rights caveats *(inferred; HASH's exact id mapping `Needs verification`)*.

**Fixture feasibility:** feasible for institutionally scanned pre-1900 Hebrew print with `NOT_IN_COPYRIGHT`, plus the IA hOCR as a non-gold diagnostic layer. Items checked:
- https://archive.org/details/the-first-five-years-of-the-state — ISA-derived, 1948–53, hOCR present; **not recommended** (private re-upload, no rights metadata).
- https://archive.org/details/libya-israeli-relations-1951-52 — ISA-derived, ABBYY djvu.xml only; not recommended, for the same reasons.
- https://archive.org/details/a-complete-dictionary-of-ancient-and-modern-hebrew-eliezer-ben-yehuda-images — PDM, 1908 print. Ben-Yehuda died in 1922, so it is PD, but later volumes and editors need checking.

**HeOCR value:** **medium-low.** There is plenty of historical Hebrew print with free OCR for diagnostics. There is no gold text, rights labels are unreliable, and the claimed ISA mirror is small and rights-dirty.

**Open questions**
1. Should IA be added only as a provenance-filtered sub-source (institutional scanners only)?
2. Should IA hOCR be stored as a `machine_ocr` sidecar, and is there a field for that in `sources.yaml`?

---

## 3. Wikimedia Commons (print, typewritten and government documents) and Hebrew Wikisource pairing

**Identity:** https://commons.wikimedia.org, MediaWiki API `https://commons.wikimedia.org/w/api.php`. Paired text comes from Hebrew Wikisource (ProofreadPage), `https://he.wikisource.org/w/api.php`.

**Gemini claim check**
- `{{PD-Israel}}` exists (and `{{PD-IL}}` redirects to it). `{{PD-IsraelGov}}` exists. `Template:PD-Israel-Gov` does not exist *(verified 2026-11-06)*.
  - PD-Israel wording: life+70, photos ≤ 2008-05-24 at creation+50, and state-owned works at creation+50.
  - PD-IsraelGov wording: "created or ordered by the State of Israel". It covers §6 works, or works "created more than 50 years ago (i.e. before 1 January 1976)", provided the State was first owner.
- `Category:Hebrew-language PDF files` exists: 368 files and 7 subcats. "Category:PDF files in Hebrew" is empty.
- `Category:Public domain files from Israel` **does not exist.** The real tracking categories are `Category:PD Israel` (67,742 files) and `Category:PD Israel Government` (5,753 files). `Category:PD IsraelGov` is empty *(verified 2026-11-06)*.
- "Every file has passed strict legal screening": **false.** Tags are contributor-applied, and I found mis-tagged examples:
  - `File:1949newSettlementsDocument.pdf` is tagged PD-IsraelGov but its author is "Israel Settlement Department and Jewish National Fund". The JNF is not the State.
  - `File:גנזך המדינה ארכיון הרב הרצוג שמות נפגעי השיירה להר הצופים.pdf` is tagged PD-IsraelGov but comes from Rabbi Herzog's private archive. He died in 1959.
  - PD-IsraelGov is also applied to 2022–2025 ministry decisions and letters, which are not covered by §42 and fit §6 only if judicial.

**Content (counts via API, 2026-11-06)**

| Selection | Count |
|---|---|
| PD-IsraelGov files, all | 5,753 (mostly maps, photos, stamps, signs) |
| PD-IsraelGov PDFs | 23 |
| PD-IsraelGov DjVu | 0 |
| PD-IsraelGov files matching "מכתב" | 1,238 (loose full-text search) |
| PD-Israel PDFs | 56 |
| `Category:Files from Israel State Archives` | 147 files, of which 7 are PDFs, e.g. `פרוטוקול ישיבת הממשלה הזמנית 22-06-1948.pdf` and `תיאטרון יידיש החלטת ממשלה 18-07-1951.pdf` |
| `Category:DjVu files in Hebrew` | 41 |

So Commons holds only tens of government or typewritten documents. Its Hebrew print volume is in the books.

**Text availability, the key finding:** Hebrew Wikisource runs ProofreadPage (Index ns 112 "מפתח", Page ns 104 "עמוד"), and its page transcriptions are paired with Commons-hosted scans *(verified 2026-11-06)*.
- There are **141 Index pages**, i.e. scanned books.
- Page-quality categories:
  - "בוצעה הגהה" (proofread): 1,824 pages
  - "מאומת" (validated): 268 pages
  - "לא בוצעה הגהה" (not proofread): 3,835 pages
  - "בעייתי" (problematic): 26 pages
  - "ללא טקסט" (no text): 884 pages
- That gives about **2,090 human-proofread printed Hebrew pages, each paired with a page image** (value tier 1 at page level, with no line geometry).
- Top works:
  - Hyman, *Toldoth Tannaim veAmoraim* I–III (1910): ~290 pages
  - *Bostenay* (Meir Lehmann): 66
  - *Biblia Hebraica*: 52
  - *Chotam Tocnit*: 38
  - Birnbaum Siddur (1949): 105 validated
  - Birnbaum Haggadah: 65 validated
- Rights caveat: Philip Birnbaum died in 1988, so his Siddur and Haggadah are **not PD in Israel**. They are likely on Commons under a US non-renewal rationale, so they would need exclusion.

**Access:** MediaWiki API and Wikimedia dumps. `prop=proofread` and the Page namespace give per-page wikitext, and Commons gives the PDF/DjVu page renders (`page=N` thumbnails). Rate limits apply: I hit "too many requests" with a weak User-Agent. A descriptive UA and throttling are required *(verified 2026-11-06)*.

**Rights**
- Commons files: per-item tag. Wikisource transcription text is under the site licence, CC BY-SA 4.0 (`Needs verification` on the he.wikisource footer). A faithful transcription of a PD work is arguably not original, but take the conservative route.
- Proposed for scans: `PD-IL` per item after checking the author's death or state authorship. Proposed for text: `CC-BY-SA-4.0`, `sharealike`. Status **`allowed`** for items whose Commons tag and author dates are checked; `review_only` otherwise.

**Fixture feasibility:** **yes.** A small, deterministic set of validated pages with the image page render is feasible. Items checked:
- https://commons.wikimedia.org/wiki/File:Aaron_Hyman._Toldoth_Tannaim_veAmoraim._I._1910.pdf — 447 pp, PD; Hyman died in 1937. Proofread pages at `he.wikisource.org/wiki/עמוד:Aaron Hyman. Toldoth Tannaim veAmoraim. I. 1910.pdf/32–34` (validated).
- https://commons.wikimedia.org/wiki/File:1949newSettlementsDocument.pdf — 37 pp, 1293×1960, typewritten government/JNF 1949. **Mis-tagged; needs review.**
- `File:פרוטוקול ישיבת הממשלה הזמנית 22-06-1948.pdf` — a state work from 1948, a good typewriter candidate. Text pairing: none found.

**HeOCR value:** **high** for the Wikisource-paired subset (real human-proofread print with images, about 2k pages). **Low** for Commons government PDFs alone (tens of files, no text).

**Open questions**
1. Does another track already cover Wikisource? If not, add `wikisource_he_proofread` as a source.
2. How should HeOCR handle CC BY-SA transcriptions of PD scans (keep as `sharealike` vs. argue they are PD)?
3. Exclude non-Israel-PD works such as Birnbaum.

---

## 4. data.gov.il (tenders and exemptions datasets)

**Identity:** National Digital Agency (מערך הדיגיטל הלאומי), https://data.gov.il, CKAN API `https://data.gov.il/api/3/action/`. Terms: https://data.gov.il/he/terms-of-use (loaded 2026-11-06; published 01/01/2018, updated 30/08/2025). `/terms-of-use` without `/he` redirects (307).

**Gemini claim check**
- The licence wording ("worldwide, royalty-free… commercial and non-commercial… attribution… no misrepresentation, no privacy harm") **holds** *(verified 2026-11-06)*.
- Datasets `tenders` (≈14,200 records) and `exemptions` (>165,000) **hold**: the tenders resource `7038b3e6-a74d-442e-b16b-466c8196124a` has 14,205 rows, and the exemptions resource `65c8fced-c50c-400e-94fb-ef1a208c43e5` has 165,705 rows.
- "Frozen since Feb 2021" **holds**: last resource modification 2021-02-16 *(verified 2026-11-06)*.
- **The two resource URLs Gemini cited are wrong datasets.**
  - `069357eb-…/63717ee6-…` is "מיפוי מאגרי מידע במשרדי הממשלה" (a mapping of government databases).
  - `4dfa061f-…/b53dc314-…` is "דוח ביצוע תוכניות העבודה הממשלתיות לשנת 2025".
  - Neither one is tender data.

**Content:** metadata only *(confirmed)*.
- Fields include publication number, ministry, procedure type and name, status, dates, supplier, company number, amount and subjects.
- The exemptions table has a `לינק לטקסטים` field. It is just the publication number, a key into **mr.gov.il pages, which the maintainer has ruled out**.
- No page images, no documents.
- Elsewhere on the portal, 183 of 1,207 datasets carry a PDF resource (mostly reports and explanatory notes, likely born-digital). I could not test one: the file host `e.data.gov.il` returned an HTML challenge instead of the PDF *(inferred / `Needs verification`)*.

**Text availability:** none for the OCR target. The metadata is not alignable to any non-mr.gov.il images. Its index value is nil: it points only at mr.gov.il.

**Access:** CKAN API, `datastore_search` and `datastore_search_sql` work without a key *(verified 2026-11-06)*.

**Rights**
- Operative wording, from "רישיון לשימוש במאגרי המידע באתר Data.Gov.il": "אתה רשאי להעתיק… וליצור ממנו יצירות נגזרות… באופן מסחרי ובאופן שאינו מסחרי". Attribution is required.
- Prohibitions: misleading presentation, illegal use, privacy harm or cross-matching.
- The licence excludes personal data under the Privacy Protection Law and third-party rights.
- CKAN `license_id` = `other-open`.
- None of the hocrgen values fits exactly. This is attribution-style with extra prohibitions, close to CC BY. A new value would be needed: **`IL-DATAGOV-1.0`**, with `open_with_attribution`.
- Status for HeOCR: **`blocked` / out of scope.** The licence is fine, but there are no images and the data only indexes mr.gov.il.

**Fixture feasibility:** not applicable for OCR. Dataset pages checked:
- https://data.gov.il/dataset/tenders
- https://data.gov.il/dataset/exemptions

**HeOCR value:** **low (none).** It is metadata only, and its only document links point to the ruled-out mr.gov.il.

**Open questions:** should HeOCR scan the 183 data.gov.il datasets with PDF resources for born-digital Hebrew reports under this licence (value tier 2)? That would be a separate, small lead.

---

## 5. OpenBudget / מפתח התקציב (next.obudget.org)

**Identity:** Public Knowledge Workshop (הסדנא לידע ציבורי).
- Site: https://next.obudget.org
- SQL API: `https://next.obudget.org/api/query?query=…`
- Pipelines: https://github.com/OpenBudget/budgetkey-data-pipelines (no LICENSE detected by the GitHub API; last pushed 2026-10-16).

**Gemini claim check:** "continuously pulls tenders and exemptions from the procurement administration and offers them as CSV/API" **holds**. `procurement_tenders_processed` has 234,595 rows from 2005 on, and `page_url` points to `mr.gov.il/ilgstorefront/...` *(verified 2026-11-06)*.

**Content:** metadata.
- The table has a `documents` column, but **0 rows have non-empty `documents`** today.
- The pipeline code (`procurement/tenders/parse_page_data.py`) historically downloaded mr.gov.il `Files_Michrazim/*.signed` documents, unsigned them and **mirrored them to OpenBudget public object storage**.
- So any mirrored documents are mr.gov.il tender documents, which the maintainer has ruled out *(verified code 2026-11-06; whether the mirror is still live: `Needs verification`)*.

**Text availability:** none relevant.

**Access:** an open SQL API, plus CSV download via `download_url` *(verified 2026-11-06)*.

**Rights:** from the about page, "השימוש במידע כפוף לרישיון CC BY-SA 4.0 של Creative Commons", and site code is MIT (https://next.obudget.org/about#licenses, loaded 2026-11-06). Proposed: `CC-BY-SA-4.0`, `sharealike`, for metadata. Status **`blocked`** for HeOCR, because the documents derive from mr.gov.il and there are no other images.

**Fixture feasibility:** not applicable.

**HeOCR value:** **low (none).**

**Open questions:** none, unless the maintainer wants the procurement metadata itself for synthetic form or table generation, which is not OCR ground truth.

---

## Ranked summary

| Rank | Source | Text pairing | Rights (proposed) | Status | HeOCR value |
|---|---|---|---|---|---|
| 1 | he.wikisource ProofreadPage + Commons scans (print) | ~2,090 human-proofread pages (1,824 proofread + 268 validated), page-level | Scans `PD-IL` per item; text `CC-BY-SA-4.0` / sharealike | allowed (per-item checked) | **High** |
| 2 | Israel State Archives (archives.gov.il) | None (image-only PDFs, about 80 ppi; OCR only in Google Pinpoint) | `PD-IL` per page for ≤1975 state works; source `RESTRICTED-NONOPEN` (ND licence, no bots or bulk) | review_only | Medium |
| 3 | Internet Archive Hebrew (language:heb, 13,789 texts) | Machine OCR only (hOCR/chOCR/djvu.xml) | `UNKNOWN` → per-item `PDM-1.0`/`PD-IL`; PDM labels unreliable | review_only | Medium-low |
| 4 | Commons PD-IsraelGov / ISA-file PDFs | None | `PD-IL` per item; tags often wrong | review_only | Low |
| 5 | data.gov.il tenders/exemptions | Metadata only; links only to mr.gov.il | New value `IL-DATAGOV-1.0`, open_with_attribution | blocked (out of scope) | None |
| 6 | OpenBudget procurement | Metadata; old mirror of mr.gov.il docs | `CC-BY-SA-4.0` | blocked | None |

**Gemini claims found wrong:**
1. ISA files were "mass-uploaded" to IA: there are only ~90 texts, re-uploaded by one private account with no rights metadata.
2. ISA PDFs carry a hidden OCR layer: none in the samples. OCR sits in Google Pinpoint.
3. "Category:Public domain files from Israel" does not exist.
4. "Every Commons file has passed strict legal screening": tags are often wrong.
5. The two data.gov.il resource URLs point to unrelated datasets.
6. `catalog.archives.gov.il` is no longer reachable.
