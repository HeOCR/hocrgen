# F8 — Real-source map and paired-text source intake

Status: `F8a` (this map and the F8 notation) is planning only. `F8b` is implemented on the current ref (review-only `wikisource_he_proofread`; see [`docs/wikisource_proofread_source.md`](../../docs/wikisource_proofread_source.md)). `F8d` is partly implemented (YidTakNL only; see [F8d findings](#f8d-findings-2026-11-06)). `F8c` and `F8e` are planned. The maintainer answered the decisions list on 2026-11-06; see [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../decisions/2026-11-06-f8-real-source-decisions.md). Parent milestone: F8. Source proposals: `HeOCR/hocrgen#103` (`F8b`), `#104` (`F8c`) and `#105` (`F8d`). Evidence was checked on 2026-11-06 against each source's own pages and APIs; the per-source notes are in [`docs/2026_11_06_israeli_public_domain_documents_research/verification/`](../../docs/2026_11_06_israeli_public_domain_documents_research/verification/).

F8 maps real (non-synthetic) Hebrew document sources beyond HASH. It ranks them by what HeOCR lacks most: **real page images paired with human-made text**, for both printed and handwritten Hebrew. It supplies the printed real-reference source that [E2d](./e2d-real-scan-evaluation.md) says is "not yet selected". It changes no source, profile, licence, gate or score.

## Why now

- **hocrgen holds zero human-transcribed real pages.** The packaged `biblia_open` source is 26 Wikimedia Commons images of a c. 1300 Bible manuscript. `pinkas_open` is 27 Commons/WDL scans of community pinkasim. Neither carries any transcription, and neither comes from the BiblIA (Zenodo 5167263) or BGU Pinkas (Zenodo 3569694) ground-truth datasets that share their names. The `biblia_open` items are a manuscript, so E2d's mention of BiblIA as a `printed_historical` candidate does not hold for this subset.
- **No open printed-Hebrew ground truth on real scans was found**, apart from one printed-Yiddish set (`F8d`).
- The starting leads came from a Gemini conversation, archived in [`docs/2026_11_06_israeli_public_domain_documents_research/`](../../docs/2026_11_06_israeli_public_domain_documents_research/). About 20 of its claims proved wrong (see the verification notes). Nothing here relies on an unverified Gemini claim.

## Text tiers

Value is ranked by the text that comes with the image:

1. **Human text on a real scan**: typed or proofread against that page. Becomes a reference only after human attestation and adjudication (F2, E2d).
2. **Born-digital text**: a PDF whose embedded text is the source text. Rendered pages are not scans; bidi extraction must be checked.
3. **Machine OCR/HTR text.** Diagnostic only. **OCR and HTR output is never ground truth.**
4. **Images only.** Useful for unlabelled, layout or later human transcription work. New human transcription campaigns are allowed (maintainer decision 2026-11-06).

The text tier is recorded separately from the content type. A page's `content_type` says what it is; its text provenance says where its text came from.

## The map

### Shortlist (planned PRs)

| Rank | Source | Content | Text tier | Rights evidence (verified 2026-11-06) | Proposed mapping | PR |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Hebrew Wikisource proofread pages (ProofreadPage `עמוד:` / `מפתח:` namespaces) with their Commons scans | `printed_historical` books, mostly rabbinic, some vocalized | 1: page-level, human-proofread; no line geometry | Text: site licence CC BY-SA 4.0. Scans: per Commons file (`PD-old`, `PD-scan` seen) | text `CC-BY-SA-4.0` / `sharealike`; scan per file; `review_only` first | `F8b` |
| 2 | NLI IIIF items whose manifest `license` is `public-domain-free-use` | `printed_historical` books; the current `nli` seeds are all manuscripts | 4 | NLI rights page for the slug: may be used "for any purpose, including commercial use" | `PD-IL` / `open`, as `nli_any_use_permitted` today | `F8c` |
| 3 | BGU Pinkas Dataset (Zenodo 3569694) | `handwritten_historical`, c. 1500–1800 cursive, 30 pages | 1: PAGE XML at word, line and page level | Zenodo licence field `cc-by-4.0`. Scan provenance unverified: no holding library or photographer named | `CC-BY-4.0` / `open_with_attribution`; held | `F8d` |
| 4 | YidTakNL Vaybertaytsh ground truth (figshare 10.6084/m9.figshare.25422844) | `printed_historical` Yiddish in Hebrew script, 1709–1781 | 1: Transkribus GT (human-corrected HTR), page-level plain text with JPEGs, no geometry | figshare licence CC BY 4.0 for the dataset. Scans per item: NLI `public-domain-free-use`, or HUC with no open licence | `CC-BY-4.0` / `open_with_attribution`; NLI-scanned pages only | `F8d` |
| 5 | Reshumot (ספר החוקים, קובץ התקנות), about 2006 on | `printed_modern` gazette | 2: born-digital PDF | §6: no copyright in laws and regulations | `PD-IL` / `open` | `F8e` |
| 6 | Knesset committee protocols, 1949–1975 | typewritten scans | 4 | §42: state works created on or before 1975 are PD | `PD-IL` / `open` | `F8e` |

Scale, measured on 2026-11-06:

- **Wikisource:** 141 Index and 6,839 Page pages. Of these, 1,824 are at quality 3 (proofread) and 268 at quality 4 (validated by a second editor). Excluding the Birnbaum works (see below) leaves about 1,600 pages.
- **NLI:** the free-use pool is large but unmeasured. Example: *Romemut El*, Zolkiew 1764, 208 pages.
- **BGU Pinkas:** 30 pages.
- **YidTakNL:** about 26k training words. The SURFdrive bundle holds 7 works: 320 page JPEGs and 320 page-level text files (some empty). 2 works (41 pages) are HUC scans and are excluded; the other 5 link to NLI records.

### Review-only or deferred

| Source | Why not now |
| --- | --- |
| Supreme Court rulings (PDF + DOC + HTML, 1997 on; tier 2) | §6 makes rulings PD, but the site's terms ban commercial and automated use, and modern rulings need publication-ban screening. |
| Knesset plenary records, 1949–1992 | The DOC files are the same OCR as the PDFs (tier 3), not a gold pair. Committee protocols from 1976 on are outside §6 "דברי הכנסת" on the most likely reading. |
| Reshumot before about 2006, and ילקוט הפרסומים | Scans with an OCR layer (tier 3). ילקוט הפרסומים notices are not laws or regulations, so §6 does not cover them. |
| Israel State Archives | About 80 ppi image-only PDFs. The terms forbid derivative works, bots and copying large sets. Files mix in third-party material. |
| Internet Archive Hebrew (13,789 texts) | Rights metadata on about 11% of items, and Public Domain Mark labels are unreliable (a 1980 encyclopedia carries one). hOCR is machine OCR. |
| JPress newspapers (about 6.75M pages) | Rights are per title; the terms ban systematic copying of "a significant portion"; no public ALTO; OCR is tier 3. |
| NLI `public-domain-non-commercial-use` (Google-digitized PD books) | Non-commercial use only, with no redistribution. |
| HathiTrust Hebrew | `pdus` volumes are denied to users in Israel; Google-digitized sets forbid re-hosting. |
| BiblIA, Sofer Mahir, Princeton Geniza Project | Strong medieval human GT, but CC-BY-NC(-SA). |
| Project Ben-Yehuda | Its dump is PD human-typed text (about 26k works), but with no scan links and no page alignment. It is the text side of a future alignment pilot, which a human must verify. |

### Not pursued

| Source | Reason |
| --- | --- |
| mr.gov.il tender pages | Ruled out by the maintainer (issue #86, closed 2026-11-06). |
| data.gov.il tenders and exemptions; OpenBudget procurement | Metadata only; their only document links lead to mr.gov.il. |
| HebrewBooks.org | Personal, non-commercial licence; scraping forbidden. |
| Friedberg Genizah Project | Login portal; terms forbid downloading images. |
| Academy of the Hebrew Language "Ma'agarim" | Text only, all rights reserved, paid access. |
| Tolaat HaMishpat (תולעת המשפט) | Private company, no dumps, scraping forbidden. |
| HebHTR; HHD and its `sivan22` re-upload | No published data, or research-only upstream. |
| NLI posters and ephemera | Labelled `fair-use` by NLI, even 1920s items. HeOCR keeps NLI's label by default. |

## Decisions recorded here (routine, team lead)

1. **Key NLI rights on the IIIF manifest `license` slug** (`F8c`). The slug is language-neutral, and the display text differs between books ("Any Use Permitted") and newspapers. Only `public-domain-free-use` maps to `open`.
2. **Exclude the Birnbaum Siddur (1949) and Haggadah (1953)** from `F8b`. Their Commons files are tagged only `PD-US-not renewed`; Birnbaum died in 1988, so they are not PD in Israel. This removes about 470 proofread pages.
3. **Gate `F8b` on per-file rights evidence for both the work and the scan.** No Commons template is enough on its own. `PD-scan` concerns the reproduction, and `PD-old*` can rest on terms shorter than Israel's. Each Index needs:
   - evidence that the underlying work is PD in Israel: the author died on or before 1955-12-31, or the work is a state work created on or before 1975-12-31, or an anonymous or pseudonymous work published on or before 1955-12-31;
   - evidence of the scan's rights: a faithful reproduction of a PD work, or an explicit open licence.

   Files whose only PD tag is a `PD-US-*` one are rejected. Each Index is admitted separately.
4. **Non-commercial licences stay out of `profile_open_v1`.** They map to `RESTRICTED-NONOPEN` until an adapter needs finer values (`CC-BY-NC-4.0`, `CC-BY-NC-SA-4.0`).
5. **New source ids never reuse an existing name.** BGU's dataset becomes `pinkas_dataset_bgu`, distinct from `pinkas_open`. The existing ids stay unchanged, under E4 governance.
6. **A `typewritten_historical` content type** is defined only when `F8e` lands.

## Maintainer decisions needed

These are rights or ground-truth calls, so they are the maintainer's. **Answered 2026-11-06:** 1, 2, 3, 4 and 7 were accepted. For 5, a legal opinion will be requested. For 6, printed Yiddish is in scope for training and character-level evaluation only. See the [decision record](../decisions/2026-11-06-f8-real-source-decisions.md).

1. **Wikisource text licence.** Accept CC BY-SA 4.0 page text as references? Share-alike would then apply to the reference files we release. (`F8b`)
2. **Wikisource proofreading as human attestation.** Each quality change is a named human edit in the page history. The proposal: quality 4 (validated by a second editor) counts as human-attested and adjudication-eligible; quality 3 counts as single-reviewer human proofreading. An agent never edits or attests these pages. (`F8b`, E2d)
3. **Scans that came from HebrewBooks.** Several Commons files used by Wikisource were taken from HebrewBooks and are tagged `PD-old` / `PD-scan`. Accept them? HebrewBooks' terms bind whoever downloaded the file, not the work's PD status. (`F8b`)
4. **Government site terms.** The content is PD by §6 and §42, but the sites restrict access:
   - Reshumot's search runs on an undocumented gov.il API, under a "use only via the interface" clause.
   - The Supreme Court site bans automated requests.
   - The Knesset site has a non-commercial clause.
   - The State Archives forbid bots and derivative works.

   Until these are decided, there is no automated access. (`F8e`)
5. **Knesset committee protocols from 1976 on.** Get a legal opinion, or exclude them (default: exclude).
6. **Yiddish in Hebrew script.** Is printed Yiddish, as in YidTakNL, in HeOCR scope? HASH admits Yiddish handwriting; F7 v1 excludes it. (`F8d`)
7. **NLI Search API key.** Enumerating free-use books needs NLI's Search API, which requires sign-up. That is the maintainer's action. (`F8c`)

## Planned PRs

- `F8a`: this real-source map, the decisions above and the F8 notation (planning only).
- `F8b`: a fixture-backed `review_only` Wikisource source. It pins page revision ids and Commons file SHA-1s, and emits page-level text with its quality level and editor provenance. It is gated per Index on evidence that the work and the scan are public domain. HebrewBooks-sourced Index files are admitted under the same per-file check (decision 3).
  - Implemented. Findings while building it:
    - The Korfu 1885 siddur (213 proofread pages) is not admitted yet: no death date was found for its translator, Yosef Nachmuli, and its Commons file does not record the scan's origin.
    - Some validated pages are edited again after validation (2 of the 4 checked, both Bostenay). Such a page keeps quality 4 but loses adjudication eligibility until it is validated again.
- `F8c`: key the `nli` rights strategy on the IIIF `license` slug, and admit `public-domain-free-use` printed books as `printed_historical`. Images only.
- `F8d`: fixture-backed `review_only` imports of the CC-BY-4.0 ground-truth datasets: `pinkas_dataset_bgu` (PAGE XML), and YidTakNL once its bundle is checked. YidTakNL is limited to training and character-level evaluation (decision 6). Scan provenance is verified first. **Partly implemented:** YidTakNL landed as `yidtaknl_vaybertaytsh_gt`; `pinkas_dataset_bgu` is held (see below).
- `F8e`: born-digital and typewritten government print (Reshumot from about 2006, Knesset committee scans up to 1975), with automated access allowed (decision 4) and hard throttling. Committee protocols from 1976 on wait for the legal opinion (decision 5).

## F8d findings (2026-11-06)

**YidTakNL (`yidtaknl_vaybertaytsh_gt`, implemented).**

- **Format.** The SURFdrive share (public WebDAV) holds one folder per work, with page JPEGs and a `txt/` folder of page-level Transkribus plain-text exports. It has no PAGE XML, no line or word geometry, and no checksums. The sampled 1781 images are scans placed on an A4 300 dpi page (2479 × 3508 px).
- **Text.** The JOHD paper (10:35, 2024) says the first pass came from the Dybbuk HTR model, then both annotators "corrected and double-checked" it. So the text is human-corrected HTR. It is not attested or adjudicated under F2, and the adapter marks it `not_adjudicated`.
- **Scans, per item.**
  - The 1781 *Ampliatsye un' alteratsye* folder matches NLI 990021163940205171: 24 canvases and 24 JPEGs. The manifest licence is `public-domain-free-use`. Pages 7 and 8 were compared visually with the IIIF canvases and are the same scan.
  - The 1747 item (NLI 001294844) is also `public-domain-free-use`, with 16 canvases for 16 JPEGs. It was not compared visually.
  - The 1737, 1772 and JB 899 folders point to a 15-volume NLI record (990012586850205171, `public-domain-free-use`) whose top-level manifest has no canvases. They need per-volume matching before admission.
  - The two HUC Klau Library works (RBR O 128, RBR D 129) show "© 2021 HUC - Photography and Website by Ardon Bar-Hama" and no open licence. They are excluded. The figshare CC BY 4.0 grant covers the creators' work, not HUC's photographs.
- **Scope marker.** Every entry carries language `yi` and `usage_scope.evaluation_scope: character_level_only`, with allowed uses `training` and `character_level_evaluation`, and `word_level` and `language_level_hebrew` excluded (decision 6). The adapter refuses entries without that marker.
- **Fixture.** Two pages of the 1781 work: 640 px thumbnails, and the upstream text bytes unchanged, pinned by sha256. Page-level text has no coordinates to rescale. A metadata-only HUC entry proves the rejection.

**BGU Pinkas (`pinkas_dataset_bgu`, held).**

- The two txt files in the zip are only the official split: 24 pages in `train_set.txt` and 6 in `test_set.txt`.
- The ICDAR 2019 paper says only that the pages are "manuscripts from the records of Frankfurt community", digitized as full-colour JPGs. Its acknowledgment credits a proof-reader and a segmenter.
- No source names the holding library, a shelfmark, the photographer, or permission to relicense the photographs. The JPEGs carry no EXIF.
- One lead, unverified: a secondary snippet places the Frankfurt community pinkas at NLI as Ms. Heb. 4°662, with a digital copy online. The page margins carry dates such as 1656–1657. The NLI catalogue is behind Cloudflare, so the record and its licence slug could not be checked.
- Rights are unclear, so no source, fetcher or fixture was added. To unblock it:
  - identify the manuscript and the scan source, for example the NLI record and its IIIF licence slug, plus a visual match;
  - or get a statement from the dataset authors.

  Whether the dataset's CC BY 4.0 can cover third-party photographs of a PD manuscript is a maintainer call.

## Sequencing and non-goals

- Every **new** F8 source id (`F8b`, `F8d`, `F8e`) starts `review_only` and outside `profile_open_v1`. Promotion is a later, explicit PR.
- `F8c` is different: it extends the existing `allowed` source `nli_any_use_permitted`. Its new printed items still reach `profile_open_v1` only through that source's seed vetting and the normal gates. Only `public-domain-free-use` maps to `open`.
- References enter only through F2 reference manifests, after human attestation and adjudication. `benchmark_v1` membership stays frozen.
- F8 adds no live crawling and no network-dependent CI. Fixtures are small and pinned.
- No privacy-review gate is added for public-domain historical sources (maintainer decision 2026-11-06). Modern material about living people, such as recent court rulings, still needs its legal screening; that is one reason the court rulings are deferred.
- F8 does not edit HASH. Two HASH corrections found during the mapping go to HASH separately: the `sivan22` candidate should be rejected, and a cited `MiDRASH-Project` GitHub org does not exist.
