# Track A: Born-digital legislative and judicial sources (Copyright Act §6)

Researched 2026-11-06. This was read-only research. Downloads were limited to one-off sample files (about 12 PDF/DOC files, each under 2 MB) so I could inspect their metadata and text layers. I did not sign in, submit forms or accept cookies.

## Legal baseline (statute verified)

- **§6**, verified 2026-11-06 against the Hebrew Wikisource text of the Act (page "חוק זכות יוצרים"): there is no copyright "בחוקים, בתקנות, בדברי הכנסת ובהחלטות שיפוטיות" (in laws, regulations, Knesset proceedings and judicial decisions). The same applies to any governmental authority exercising judicial power.
- **§36** (verified): the State is first owner of works made by a State employee. That expressly includes "כל נושא משרה ... במוסד ממוסדות המדינה" (any office holder in a State institution). So Knesset staff output that is not §6 material is a State work, PD once it is 50 years old (§42, which means created on or before 1975-12-31).
- **Is "דברי הכנסת" plenary only?** *(inferred, strong)* Knesset Rules (תקנון הכנסת) §§38–39 define "דברי הכנסת" as the edited protocol of **plenary** sittings (quoted on he.wikipedia "דברי הכנסת", loaded 2026-11-06). Committee protocols are a separate record. **So §6 most likely does not cover committee protocols.** They are State works: PD if created on or before 1975, otherwise State copyright. The Knesset's own terms agree: they carve out only "חוקי מדינת ישראל ולדברי הכנסת" as PD (see Source 1). This needs counsel confirmation before relying on committee protocols from after 1975.
- **§6 says "laws" and "regulations" only.** Bills (הצעות חוק), notices in ילקוט הפרסומים and Knesset background papers are not named. *(inferred)* They are not §6 material: State works fall under the 1975 cutoff, and third-party material is private.

---

## Source 1: Knesset OData API (ParliamentInfo) and fs.knesset.gov.il documents

**Identity**
- Operator: the Knesset.
- Legacy OData v3 endpoint: `https://knesset.gov.il/Odata/ParliamentInfo.svc/` (verified 2026-11-06; the URL without the trailing slash redirects to it).
- Newer OData v4 endpoint: `https://knesset.gov.il/OdataV4/ParliamentInfo/` (verified 2026-11-06). It is faster, has 48 entity sets and adds `KNS_DocumentSecondaryLaw`, `KNS_PlenumVote`, `KNS_LawCorrections` and others.
- Landing page: `https://main.knesset.gov.il/Activity/Info/pages/databases.aspx` (loaded in the browser; it is behind a JS bot challenge, so curl fails). It says the service has run "ממרס 2017" (since March 2017) and links a developer manual at `.../Activity/Info/documents/KnessetOdataManual.docx` (not loaded).
- Files are served from `https://fs.knesset.gov.il/<knesset>/<Plenum|Committees|law>/...`.

**Gemini claim check.** Gemini said the API holds plenary, committee, bill and law documents, with PDF and Word side by side for most documents, so they are gold pairs.
- **Partly true.** The document types exist, and the scanned era really does have TIF + PDF + DOC triples.
- **The "gold pair" claim is false.** In the scanned era, the DOC is the **same OCR output** as the PDF's hidden text layer:
  - Verified on the 1949 plenary sitting: identical OCR errors in both, "ושוטד" for ושוטר and "היתד." for היתה. The DOC's author field is "imst", i.e. Imagestore.
  - Verified the same pattern on a Knesset-14 committee DOC (author "imst").
  - The PDF metadata reads "converted from original paper sources by Imagestore systems LTD", "Scanning & OCR".
- **The modern era has no PDFs of the protocols**, only DOC/DOCX. Verified on samples from Knessets 16, 20 and 25.
- **Gemini's claim that the Knesset Corpus covers "1948 onward" is also false** (see Source 2).

**Content** (counts from the v3 `$count` queries, verified 2026-11-06)

| Entity | DOC | PDF | TIF scan ("PIC") | Other |
|---|---|---|---|---|
| `KNS_DocumentPlenumSession` (76,946 total) | 57,509 | 6,334 | 5,390 | 3,901 video, 4 XLS, 2 "PPT" |
| `KNS_DocumentCommitteeSession` (201,805 total) | 82,498 | 82,269 | 32,320 | 1,571 "PPT", 3,053 video, 91 XLS |
| `KNS_DocumentBill` (108,632 total) | 64,491 | 28,538 | 9,139 | 6,457 "PPT" |
| `KNS_DocumentLaw` (10,673 total) | 2,251 | 7,158 | 963 | 173 XLS, 128 "PPT" |

- `ApplicationDesc="PPT"` is mislabelled: the sampled rows point to `.PDF` files.
- `KNS_DocumentIsraelLaw` returns 0 rows.

**Eras, from samples (verified 2026-11-06):**

| Material | Period | What exists | Text |
|---|---|---|---|
| Plenary protocols | Knessets 1–12 (sampled 1949, 1961, 1977, 1988) | Triple per sitting: TIF scan + PDF + DOC | PDF = 400 dpi bitonal CCITT image with invisible OCR text; DOC = the same OCR |
| Plenary protocols | Knesset 13 onward (from 1992) | Born-digital DOCX/DOC, no PDF. The 1992 DOCX is authored by Knesset staff on the template "דברי הכנסת - תבנית" | Born-digital |
| Committee protocols | Knessets 2 and 8 (1952, 1974) | PDF + TIF only. **Typewritten** Hebrew; the 1952 page was viewed: 300 dpi bitonal, very poor OCR | Poor OCR |
| Committee protocols | Knesset 14 (1996) | PDF + TIF + DOC | DOC = OCR |
| Committee protocols | Knessets 20 and 25 | DOC only | Born-digital |

- **Committee "חומר רקע" (background material)** documents are mostly PDFs. Examples: `25_cs_bg_*.pdf`, `20_cs_bg_*.pdf`. They are submissions by ministries, NGOs and the public, so they are **not Knesset works and not §6**.
- **Laws:** "חוק - פרסום ברשומות" PDFs are copies of the Reshumot booklets.
  - Knesset 14 (1990s): scanned + OCR (Imagestore, 2008).
  - Knesset 20 (2016): **born-digital** (Adobe InDesign CS6, HadasaMFO fonts). For that law there is also a "חוק - נוסח לא רשמי" DOCX (unofficial text), i.e. a born-digital DOCX next to a born-digital PDF of the same law.

**Text availability**
- Scanned era: OCR only (tier 3). The TIF/PDF images are usable as tier 4.
- Modern era: born-digital DOC/DOCX. Rendering them would be our own rendering, not the printed page (between tiers 2 and 3).
- Reshumot law PDFs from about 2006 onward: real born-digital PDF (tier 2). The `pdftotext` output shows bidi/number-order artefacts, e.g. "התשע"ו‪1234 . . . 2016-".

**Access**
- Open OData with no key. JSON via `$format=json` (v3) or by default (v4). `$filter`, `$top`, `$skip` and `$count` work; `$apply`/groupby is not supported.
- **Rate limiting / WAF (verified 2026-11-06):** after about 100 small queries in roughly 10 minutes, every request returned "access denied … Status_Code:473". Adapters must throttle hard and cache.
- `main.knesset.gov.il` requires a JS challenge. `fs.knesset.gov.il` serves PDF/DOC directly, but TIF requests got a 247 challenge page.

**Rights.** Knesset terms, `https://main.knesset.gov.il/About/Pages/TermsOfUse.aspx` (loaded 2026-11-06, page dated 23.11.2025):
- §4.1 reserves copyright "למעט ביחס לחוקי מדינת ישראל ולדברי הכנסת ... אשר הינם נחלת הכלל" (except Israeli laws and Divrei HaKnesset, which are public domain).
- §2.3 forbids commercial use of site content without written permission. This is a contractual clause. It cannot add copyright to §6 material, but it bears on how we access the site. Maintainer decision.

Per-item rights:
- **Plenary protocols (any year) and laws:** `normalized_license: PD-IL`, `rights_classification: open`, status **allowed**.
- **Committee protocols created on or before 1975-12-31** (Knessets 1–8, partly): PD-IL under §36/§42 (State work older than 50 years), open, **allowed**.
- **Committee protocols from 1976 on:** not clearly §6, and the Knesset reserves rights. `UNKNOWN`, **review_only** until counsel confirms.
- **Bills:** on or before 1975, PD-IL. Later bills: `UNKNOWN`, **review_only** *(inferred: bills are not "laws")*.
- **Background material:** `RESTRICTED-NONOPEN`, **blocked** unless cleared item by item.

**Fixture feasibility: yes.** Each document has a stable URL and a numeric ID. Samples checked:
- `https://fs.knesset.gov.il//1/Plenum/1_ptm_250009.pdf`: 1949 plenary, 19 pages, scanned + OCR, 1.86 MB. Its OCR DOC is `.../1/Plenum/1_ptm_254201.doc`.
- `https://fs.knesset.gov.il//2/Committees/2_ptv_399388.PDF`: 1952 Finance Committee, typewritten, 10 pages, 667 KB, PD under §42.
- `https://fs.knesset.gov.il/\20\law\20_lsr_348685.pdf`: 2016 Reshumot law, born-digital. Its unofficial DOCX is `.../20_lsh_348591.docx`.

**HeOCR value: medium-high.**
- Large rights-clean printed-page image sets for 1949–1992, plus a rare **typewriter** set (committee protocols up to 1975).
- No human ground truth, though. The text is OCR, or born-digital DOC without page images.

**Open questions**
1. Do we accept committee protocols from 1976 onward without a counsel opinion?
2. Should we add a content type `typewritten_historical` for the committee scans?
3. Is it acceptable to throttle around the WAF and the §2.3 "no commercial use" clause?

---

## Source 2: Knesset Corpus (Haifa CL Group / HUJI)

**Identity**
- Hugging Face: `https://huggingface.co/datasets/HaifaCLGroup/KnessetCorpus`. Verified via the HF API on 2026-11-06; last modified 2026-02-26; not gated. A mirror exists at `GiliGold/KnessetCorpus`.
- Code: `https://github.com/HaifaCLG/KnessetCorpus`. The repo has no licence file and was last pushed in 2023-11.
- Paper: Goldin et al., *Lang Resources & Evaluation* (2025), doi:10.1007/s10579-025-09833-4.

**Gemini claim check.** Gemini said it covers plenary and committee protocols from 1948 to recent years and that its IDs cross-reference easily to the API's PDFs.
- **The date range is false.** The README says "from 1992 to 2024", and the metadata files are `all_plenary_protocols_knessets_13-24.csv` and `..._committees_..._13-24.csv`.
- **Cross-referencing partly holds.** `protocol_name` is the Knesset file basename, e.g. `18_ptv_140671.doc` or `\13\Plenum\13_ptm_532132.docx`. The number in it is the OData `DocumentCommitteeSessionID` / `DocumentPlenumSessionID`, so it maps to `fs.knesset.gov.il` *(verified by pattern match)*.
- For that era, however, mostly **no PDF exists to map to**: Knesset 13 onward is DOC-only (Source 1).

**Content**
- Over 35 million sentences with speaker, faction and morphology metadata. About 4,700 sentences are manually annotated for NER/UD.
- `raw_protocols/` mirrors the original Knesset DOC/DOCX/PDF files:
  - `plenary_sessions.zip`: 13.4 GB
  - `committee_deliberations.zip`: 31.1 GB
  - Knesset 25 zips
- Text only, with no page images.

**Text availability.** Extracted text, with the flag `is_ocr_output` = false for all documents.
- *(inferred)* Some committee DOCs from Knessets 13–14 are in fact Imagestore OCR. A Knesset-14 committee DOC sampled from the API had author "imst" (Source 1). The flag may therefore be wrong for the earliest committees. `Needs verification`.

**Access.** HF dataset files and the `datasets` loader. The README also publishes an ElasticSearch/Kibana host with shared credentials. We did not use it, and HeOCR should not rely on it.

**Rights**
- README YAML says `license: cc-by-sa-4.0`. The body says the raw data "are copyright-free and are released under no license". The badge text reads "Creative Commons Attribution 4.0" but links to BY-SA 4.0, which is internally inconsistent.
- Proposed: annotations and derived corpus `CC-BY-SA-4.0` / `sharealike`. Underlying plenary text `PD-IL` (§6). Committee text follows the Source 1 analysis.

**Fixture feasibility.** Possible, but not useful on its own because it has no images.

**HeOCR value: low.** It is a text-only modern corpus. Its one use is as a cached mirror of Knesset raw DOCs, which spares the Knesset WAF.

**Open questions**
1. Is it worth using `raw_protocols` as an offline mirror instead of hitting `fs.knesset.gov.il`? That would be a 44 GB+ bulk download, which needs maintainer approval.

---

## Source 3: Reshumot (ספר החוקים, קובץ התקנות, ילקוט הפרסומים, הצעות חוק): Ministry of Justice on gov.il

**Identity**
- Unit page: `https://www.gov.il/he/departments/official_gazette` (loaded 2026-11-06).
- Collector: `https://www.gov.il/he/Departments/DynamicCollectors/gazette-official?skip=0&limit=10&FolderType=<n>`. Folder types:

| FolderType | Series |
|---|---|
| 1 | ספר החוקים |
| 2 | ילקוט הפרסומים |
| 3 | קובץ התקנות |
| 4 | חיקוקי שלטון מקומי |
| 5 | מכס |
| 6 | הצעות חוק הממשלה |
| 7 | מפתח תחיקה |
| 8 | הצעות חוק כנסת וממשלה (up to 2002) |
| 9, 12 | English translations |
| 10, 11 | דיני מדינת ישראל |

- Backend search API (undocumented): `POST https://pub-justice.openapi.gov.il/pub/moj/portal/rest/searchpredefinedapi/v1/SearchPredefinedApi/Reshumot/Search`.
  - Requires the header `x-client-id: 149a5bad-edde-49a6-9fb9-188bd17d4788`. This public ID is embedded in the collector page.
  - Body like `{"FolderType":"1","BookletYear":"17","skip":0}`.
  - Verified working 2026-11-06.
- Files: `https://free-justice.openapi.gov.il/free/moj/portal/rest/searchpredefinedapi/v1/SearchPredefinedApi/Documents/<opaque token>`. Characters in the token must be URL-encoded (`=` as `%3D`).

**Gemini claim check**
- **The access URL is wrong.** Gemini's Google-wrapped `gov.il/he/collectors/publications?officeId=c338b272-…` loads but shows "אין תוצאות" (no results, verified 2026-11-06). The real route is the `gazette-official` collector and the API above.
- **"Every booklet from 1948 is available as PDF"** holds for ספר החוקים: the earliest Hebrew year queried, תש"ט (1949), returns 25 booklets. Other series were not checked.
- **"Born-digital from 2000"** is inaccurate:
  - 1949 (booklet 10), 1997 (1644), 2001 (1818) and 2005 (1969) samples are all **bitonal 300–400 dpi CCITT scans with an OCR text layer**, reprocessed with PDFsharp in 2013–2015.
  - 2006 (booklet 2061), 2007, 2008, 2013, 2015, 2016 and 2026 (3579) samples are **born-digital InDesign** (verified 2026-11-06).
  - So the switch is around 2005/2006 (exact booklet `Needs verification`).
- **"JSON with full PDF paths"** is correct: the API returns the `Document[].FileName` URL, `Pages`, `PublishDate` and `DocSummary` (an HTML list of contents).

**Content**
- Every booklet of the official gazette, all printed Hebrew. Modern booklets use HadasaMFO fonts; older ones are scans of letterpress print.
- Browsing shows at most 200 results (`TotalResults: 200`, and `skip: 200` returns nothing), so the full scan has to be enumerated by `BookletYear`.
- `BookletYear` is an index: Hebrew year minus 5692 *(inferred from the points 17 = 1949, 50 = 1982, 94 = 2026)*.
- **Not every series is §6.** ילקוט הפרסומים is mostly notices: appointments, planning notices, company liquidations, inheritance and court notices. Some are submitted by private parties: gov.il runs a service to publish liquidation, partnership and dividend notices.
  - *(inferred)* §6 covers ספר החוקים and קובץ התקנות, including municipal by-laws, which count as regulations. It does not cover ילקוט הפרסומים notices or government bills.
  - Government notices and bills are State works, PD if on or before 1975. Private notices are mostly facts (§5), but authorship is mixed.
  - ילקוט הפרסומים also carries personal data: names in liquidations, insolvency and inheritance notices.

**Text availability**
- Up to about 2005: OCR only (tier 3).
- From about 2006: born-digital PDF with embedded Hebrew text (tier 2). Watch for bidi and number-order problems on extraction.
- No structured text format.

**Access.** An undocumented JSON API that uses a public client ID. There are no published docs, no documented rate limits and no bulk dump. Document URLs are opaque tokens whose long-term stability is `Needs verification`, so record booklet number and year as the stable key.

**Rights**
- gov.il terms, `https://www.gov.il/he/pages/gov_terms_of_use` (loaded 2026-11-06), say copyright in government publications "שייכות למדינת ישראל" (belongs to the State of Israel). §6 overrides that for laws and regulations.
- The terms also forbid accessing services "בכל דרך אחרת מלבד דרך הממשק" (any way other than the provided interface). Calling the backend API directly may conflict with that clause. Maintainer decision.

| Series | normalized_license | rights_classification | Status |
|---|---|---|---|
| ספר החוקים, קובץ התקנות (incl. local by-laws) | `PD-IL` | `open` | **allowed** |
| ילקוט הפרסומים, הצעות חוק, on or before 1975 | `PD-IL` (§42) | `open` | **allowed** |
| ילקוט הפרסומים and bills from 1976 on | `UNKNOWN` | — | **review_only** |

**Fixture feasibility: yes for ספר החוקים.** Samples checked:
- Booklet 3579 (2 Aug 2026, 8 pages, InDesign, born-digital): `.../Documents/doyMEPDd6FPUYFBsOgKR96C3ExvRZXnuU5ZF7+R3dXw=`
- Booklet 2061 (2006, InDesign, born-digital): `.../Documents/tPX8wESM0iYrtcgLLyI32OUQp4nGeFloD~bcqnBPlrc%3D`
- A 1949 booklet (תש"ט, scanned + OCR, 8 pages): `.../Documents/kHVF5p3PnFio~YJlID15pM2g4IwC5qnhiEVq6CjHuyY=`

**HeOCR value: high.**
- About 20 years of born-digital, rights-clean official Hebrew print with exact embedded text (a tier-2 gold-like pair once bidi is handled).
- Plus 1948–2005 scans as tier 3/4.

**Open questions**
1. Is calling the `pub-justice` API with the page's public client ID acceptable under the gov.il "via the interface" clause?
2. Should ילקוט הפרסומים be scoped to on-or-before-1975 only?
3. Booklets after 2006 are also mirrored on `fs.knesset.gov.il` (`*_lsr_*.pdf`). Which host should be canonical?

---

## Source 4: Israeli court rulings

### 4a. Supreme Court decisions site (Judiciary)

**Identity.** `https://supremedecisions.court.gov.il/`, operated by הנהלת בתי המשפט (the Courts Administration). Loaded in the browser 2026-11-06. Direct curl from here failed with a connection error, which looks like a WAF block.

**Content**
- The site says it holds Supreme Court judgments and decisions "החל משנת 1997" (from 1997), plus PD"I volumes from 2006 (vol. סא) onward.
- The case-year filter lists earlier years too, back to 1931 *(older coverage `Needs verification`)*.

**Text availability: born-digital.** Every document can be downloaded three ways from `/Home/Download?path=HebrewVerdicts%5C<..>&fileName=<..>&type=N`:

| type | Format |
|---|---|
| 2 | HTML |
| 4 | PDF |
| 5 | DOC |

- Verified on `07091870.w03`: a 32-page PDF made with Acrobat Distiller 6 / PScript5 (printed from Word), David, Miriam and FrankRuehl fonts embedded, no images. The DOC is 223 KB.
- This is a **real born-digital PDF + source DOC pair** (tier 2).

**Access**
- No documented API or bulk export. The site's JSON search backend was not explored.
- A third-party snapshot exists: `https://huggingface.co/datasets/LevMuchnik/SupremeCourtOfIsrael` (2022; 751,194 documents; text + metadata including `Path` / `FileName`, which map to the Download URL). It is labelled `license: openrail`, an odd choice for PD text.

**Rights**
- Rulings are PD under §6 (judicial decisions, including interim decisions).
- The site's terms, `https://www.court.gov.il/NGCS.Web.Site/Docs/WebTermsOfUse.pdf` (fetched 2026-11-06, dated 5.10.2026):
  - forbid "שימוש ... מסחריים" (commercial use);
  - reserve the right to block IPs "המבצעים פניות אוטומטיות" (that make automated requests);
  - assert State copyright in "פרסומי המשרד" (the office's publications).
- Proposed: `PD-IL`, `open`, status **review_only** until the maintainer decides on the automated-access clause and the privacy filter below.

**Legal note on privacy and publication bans.** Modern rulings concern living people.
- Minors, sexual-offence complainants and family/adoption matters are subject to publication bans (closed-doors rules under Courts Law §70, the Youth Law, adoption and family statutes, and case-specific gag orders).
- The court publishes anonymized versions, but anonymization errors happen.
- Any HeOCR sample should prefer published judgments (פסקי דין) in public-law or commercial cases. Exclude criminal, family and youth case types, and do not redistribute party names beyond what the court published.

**Fixture feasibility: yes**, with case-type screening. Sample checked: `https://supremedecisions.court.gov.il/Home/Download?path=HebrewVerdicts%5C07/870/091/w03&fileName=07091870.w03&type=4` (PDF) and `&type=5` (DOC). Pick fixture cases by hand.

**HeOCR value: medium-high.**
- Large volume of born-digital modern legal print with source DOC.
- Rights are clean, but it carries privacy and ToS overhead.

### 4b. "תולעת המשפט" (Tolaat HaMishpat), tl8.me

**Identity.** `https://tl8.me/` redirects to `https://תולעת-המשפט.קום` (verified 2026-11-06). It is run by the private company תולעת יודעת בע"מ (company no. 516711694, Haifa). The site describes itself as "מאגר משפטי פתוח וחינמי" (an open, free legal database).

**Gemini claim check**
- **The site exists.**
- **"Dump downloads" is false.** No dump exists. Its "אוספי נתונים" page holds registry datasets (vehicles, companies, NGOs and so on), not ruling dumps.
- Its terms state "אנחנו לא מרשים לכלי זחילה (scraping)" (scraping not allowed). API access is paid and limited to law firms, investigators and government bodies.
- The site says its content is copied from נט המשפט (Net HaMishpat, the courts' case system) plus **user-uploaded pleadings and protocols**. Pleadings are not §6 material.

**Rights / status.** Rulings are PD, but this site adds nothing of its own that we need, and its terms forbid scraping. `RESTRICTED-NONOPEN`, **blocked** as a source. Use the court site (4a) instead.

**HeOCR value: low.**

---

## Source 5: Hebrew Wikisource (he.wikisource.org)

### 5a. ProofreadPage scans with human-proofread pages (the important part)

**Identity.** `https://he.wikisource.org`, run by the Wikimedia community. API: `https://he.wikisource.org/w/api.php`.

**Gemini claim check.** Gemini did not mention ProofreadPage. Its only Wikisource claim was the Open Law Book XML dump (see 5b).

**Content (all verified via the API on 2026-11-06)**
- The **ProofreadPage extension is installed**. Namespaces: 104 `עמוד:` (Page) and 112 `מפתח:` (Index).
- Scale is **small**: **141 Index pages** and **6,839 Page pages**.

| Quality level | Hebrew category | Pages |
|---|---|---|
| 0 | ללא טקסט (no text) | 884 |
| 1 | לא בוצעה הגהה (not proofread) | 3,835 |
| 2 | בעייתי (problematic) | 26 |
| 3 | בוצעה הגהה (proofread) | 1,824 |
| 4 | מאומת (validated) | 268 |

- That is **about 2,092 human-proofread pages**.
- Largest proofread sets:

| Work | Proofread | Validated |
|---|---|---|
| Birnbaum Siddur 1949 | 274 | 133 |
| Korfu Sephardi siddur 1885 (vocalized) | 213 | — |
| Ralbag *Milhamot Hashem* | 188 | — |
| Hyman *Toldoth Tannaim veAmoraim* I–III (1910) | 287 | 81 |
| SD Luzzatto on Bereshit (1871) | 90 | — |
| *Bostenay* | 66 | — |
| Selichot | 63 | — |
| Buber *Tanhuma* (1885) | 55 | — |
| *Sippurei Ma'asiyot* (Lemberg) | 55 | — |
| *Biblia Hebraica* | 52 | — |
| Birnbaum Haggadah 1953 | — | 65 |

- Content type `printed_historical`, mostly rabbinic and some vocalized text. Nearly all is Hebrew; a few Ladino, Marathi and Esperanto items.
- The main namespace (262,294 articles) is mostly typed text **not** backed by scans.

**Text availability: human-proofread, page level.**
- Wikitext per Page that has to be converted to plain text. It contains `<pagequality>`, `<section>`/`<קטע>` tags, wikilinks, templates and headings.
- No line geometry. Alignment to lines has to be done downstream.

**Pairing.** Each `עמוד:<File>/<n>` corresponds to page *n* of a PDF/DjVu on Commons, so the image is the rendered file page. Thumbnail URL pattern `.../page<n>-<w>px-<file>.jpg` *(inferred, standard MediaWiki)*.

**Access**
- MediaWiki API: `prop=proofread`, `list=categorymembers` on the quality categories.
- Dumps: `https://dumps.wikimedia.org/hewikisource/latest/hewikisource-latest-pages-articles.xml.bz2`, 469 MB, dated 01-Nov-2026 (verified listing). Whether the Page namespace is included in pages-articles is *(inferred)*; `pages-meta-current` (510 MB) certainly includes it.
- Wikimedia API etiquette applies: a User-Agent and modest rates.

**Rights**
- Text: the site's rights info is "Creative Commons Attribution-Share Alike 4.0" (verified via `siteinfo` on 2026-11-06). Bare transcriptions of PD text arguably carry no new copyright, but treat them as `CC-BY-SA-4.0` / `sharealike` to be safe.
- Scans: rights are **per file on Commons**. Checked:
  - Hyman 1910: `PD-old`, `PD-scan`, source HebrewBooks. Hyman died 1937.
  - Korfu 1885: `PD-old`.
  - *Milhamot Hashem*: PD, Lewis Lamm edition, source HebrewBooks.
  - *Chotam Tocnit* (1879): PD.
- **Caveat: the Birnbaum Siddur 1949 and Haggadah 1953 are tagged only `PD-US-not renewed`.** Birnbaum died in 1988, so these are **not PD in Israel**. Exclude them, or treat them as `UNKNOWN` / review_only. That removes about 470 of the 2,092 proofread pages.
- Several Index files are modern works (e.g. "Ilan Sendowski …") and need their own rights check.
- Proposed: scans `PD-IL` or `PDM-1.0` per file, with the transcription as `CC-BY-SA-4.0`, `rights_classification: sharealike`, status **allowed per Index**. Gate on the Commons licence template (`PD-old*` or `PD-scan`; reject `PD-US-*`-only files).
  - **Superseded in F8a review:** a template alone is not enough. `PD-scan` concerns the reproduction, and `PD-old*` can rest on terms shorter than Israel's. `planning/tasks/f8-real-source-map.md` requires per-file evidence that the work is PD in Israel and that the scan's rights are clear.

**Fixture feasibility: yes, and easy and deterministic.** Pin the revision ID and the Commons file SHA1. Samples checked:
- `https://he.wikisource.org/wiki/עמוד:Aaron_Hyman._Toldoth_Tannaim_veAmoraim._I._1910.pdf/33` (quality 4, validated, 3.3 kB of text)
- `https://he.wikisource.org/wiki/עמוד:Seder_Tefilot_K'Minhag_K.K._Sefaradim_(Yosef_Nachmuli,_Korfu_1885).pdf/20` (quality 3, vocalized)
- `https://he.wikisource.org/wiki/עמוד:Milhamot_Hashem.pdf/20` (quality 3)

**HeOCR value: high in quality, small in scale.**
- It is the only source in this track with **human-proofread transcription paired with real scans**.
- About 1,600 rights-clean pages, page-level only.
- Overlap with existing HASH work: the scans live on Commons, but these are printed books, not the handwritten categories HASH covers.

**Open questions**
1. Accept CC BY-SA on the text (share-alike obligations for derived ground truth)?
2. Is there a policy for wikitext normalization, e.g. editor-added brackets or expanded abbreviations? That `Needs verification` per Index.
3. Exclude the Birnbaum works (US-only PD)?

### 5b. "ספר החוקים הפתוח" (Open Law Book) on Wikisource

**Identity.** `https://he.wikisource.org/wiki/ספר_החוקים_הפתוח` (loaded 2026-11-06; an index page about 886k characters long).

**Content**
- **6,184 main-namespace law and regulation pages** use the `ח:` templates (count by transclusion of `תבנית:ח:התחלה`, verified 2026-11-06).
- They are **consolidated current versions**. Each page's header links every amending Reshumot booklet PDF on `fs.knesset.gov.il`. Example: "חוק שעות עבודה ומנוחה" links `https://fs.knesset.gov.il/1/law/1_lsr_209133.pdf` and later amendments.

**Gemini claim check.** "Clean full text downloadable as an XML dump" is **true**: the same dump as 5a. But the text is consolidated, so it is **not page-aligned** to any single scan.

**Rights.** Law text is `PD-IL` (§6). Wiki edits are CC BY-SA 4.0. Every page carries a "not legal advice" banner (`תבנית:Legal`).

**HeOCR value: low.** Possible exception: laws never amended, whose text could be aligned to their original booklet PDF. The useful asset here is the per-law index of Reshumot PDF links.

---

## Ranked summary

| Rank | Source | Best tier | Proposed licence / class / status | Value | Key caveat |
|---|---|---|---|---|---|
| 1 | Hebrew Wikisource ProofreadPage (5a) | 1 (human-proofread page text + PD scan) | CC-BY-SA-4.0 text, PD-IL scans / sharealike / allowed per Index | High quality, small (~1.6k clean pages) | Exclude Birnbaum (PD-US only); page-level only; wikitext cleanup |
| 2 | Reshumot ספר החוקים / קובץ התקנות (3) | 2 (born-digital PDF, ~2006 on); 3/4 before | PD-IL / open / allowed | High | Undocumented API; gov.il "via interface" clause; bidi extraction |
| 3 | Supreme Court decisions (4a) | 2 (born-digital PDF + DOC + HTML, 1997 on) | PD-IL / open / review_only | Medium-high | ToS bans automated requests; privacy and publication bans |
| 4 | Knesset OData / fs.knesset (1) | 3/4 (1949–1992 scans + OCR); typewriter committee scans to 1975 | PD-IL for plenary, laws and pre-1976 committees / open / allowed; later committees UNKNOWN / review_only | Medium-high | DOC in the scanned era is OCR, not ground truth; WAF throttling; §2.3 non-commercial clause |
| 5 | Reshumot ילקוט הפרסומים / bills (3) | 2–4 | PD-IL to 1975; otherwise UNKNOWN / review_only | Medium | Not §6; personal data |
| 6 | Knesset Corpus (2) | text only | CC-BY-SA-4.0 / sharealike | Low | Covers 1992–2024, not 1948; no images |
| 7 | Wikisource Open Law Book (5b) | text only (consolidated) | PD-IL + CC-BY-SA / sharealike | Low | Not page-aligned |
| 8 | Tolaat HaMishpat (4b) | — | RESTRICTED-NONOPEN / blocked | Low | Private; no dumps; scraping banned |

**Gemini claims that were wrong:**
- The Reshumot URL is a dead Google-wrapped link.
- Reshumot is "born-digital from 2000": the switch is actually about 2006.
- Knesset "PDF + Word side by side gives a gold pair": in the scanned era the Word file is the same OCR.
- The Knesset Corpus covers "1948 on": it covers 1992–2024.
- Tolaat HaMishpat offers "dump downloads": it has none and forbids scraping.

**Proposed new vocabulary**
- `content_type: typewritten_historical` for the Knesset committee protocols, 1949 to about 1975.
- A separate text-origin field (`ocr` / `born_digital` / `human_proofread`) rather than more content types.
