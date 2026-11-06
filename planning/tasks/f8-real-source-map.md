# F8 — Real-source map and paired-text source intake

Status: `F8a` (this map and the F8 notation) is planning only. `F8b` is implemented on the current ref (review-only `wikisource_he_proofread`; see [`docs/wikisource_proofread_source.md`](../../docs/wikisource_proofread_source.md)). `F8b2` is completed (an operator-only inventory of every Wikisource Index through the F8b gate; see [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md)). `F8d` and `F8d2` are implemented (see [F8d findings](#f8d-findings-2026-11-06) and [F8d2 findings](#f8d2-findings-2026-11-06)). `F8d3` is implemented (per-line language tags for `pinkas_dataset_bgu`; see [F8d3 findings](#f8d3-findings-2026-11-06)). `F8c` is completed (slug-keyed NLI rights and cached free-use printed-book seeds). `F8e` is completed (review-only `reshumot_born_digital` and `knesset_committee_protocols_pre1976`; see [F8e findings](#f8e-findings-2026-11-06)). The maintainer answered the decisions list on 2026-11-06; see [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../decisions/2026-11-06-f8-real-source-decisions.md). Parent milestone: F8. Source proposals: `HeOCR/hocrgen#103` (`F8b`), `#104` (`F8c`), `#105` (`F8d`) and `#112` (`F8e`). Evidence was checked on 2026-11-06 against each source's own pages and APIs; the per-source notes are in [`docs/2026_11_06_israeli_public_domain_documents_research/verification/`](../../docs/2026_11_06_israeli_public_domain_documents_research/verification/).

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
| 3 | BGU Pinkas Dataset (Zenodo 3569694) | `handwritten_historical`, c. 1500–1800 cursive, 30 pages | 1: PAGE XML at word, line and page level | Zenodo licence field `cc-by-4.0` for the annotations. Scans: NLI Ms. Heb. 4°662 (Ktiv), `public-domain-free-use` | `CC-BY-4.0` / `open_with_attribution` | `F8d2` |
| 4 | YidTakNL Vaybertaytsh ground truth (figshare 10.6084/m9.figshare.25422844) | `printed_historical` Yiddish in Hebrew script, 1709–1781 | 1: Transkribus GT (human-corrected HTR), page-level plain text with JPEGs, no geometry | figshare licence CC BY 4.0 for the dataset. Scans per item: NLI `public-domain-free-use`, or HUC with no open licence | `CC-BY-4.0` / `open_with_attribution`; NLI-scanned pages only | `F8d`, `F8d2` |
| 5 | Reshumot (ספר החוקים, קובץ התקנות), about 2006 on | `printed_modern` gazette | 2: born-digital PDF | §6: no copyright in laws and regulations | `PD-IL` / `open` | `F8e` |
| 6 | Knesset committee protocols, 1949–1975 | `typewritten_historical` scans | 4 | §42: state works created on or before 1975 are PD | `PD-IL` / `open` | `F8e` |

Scale, measured on 2026-11-06:

- **Wikisource:** 141 Index and 6,839 Page pages. Of these, 1,824 are at quality 3 (proofread) and 268 at quality 4 (validated by a second editor). Excluding the Birnbaum works (see below) leaves about 1,600 pages.
- **NLI:** the free-use pool is large but unmeasured. Example: *Romemut El*, Zolkiew 1764, 208 pages; on 2026-11-06 its page images returned HTTP 500 at every size, so `F8c` lists it as an exploratory seed without a fixture. The Search API (`api2.nli.org.il`, key now available) returns no rights field, only an `accessRights` availability value, so each hit's rights still come from its manifest `license` slug.
- **BGU Pinkas:** 30 pages.
- **YidTakNL:** about 26k training words. The SURFdrive bundle holds 7 works: 320 page JPEGs and 320 page-level text files (some empty). 2 works (41 pages) are HUC scans and are excluded; the other 5 link to NLI records. The 1747 and JB 899 works (154 pages) match NLI free-use canvases page by page, and 1781 pages 7–8 were matched in `F8d`; 1737 and 1772 (101 pages) match no public NLI canvas.

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
6. **A `typewritten_historical` content type** is defined only when `F8e` lands. Defined in `F8e`: machine-typed pages such as the Knesset committee protocols up to 1975. The classifier counts it as `printed`; the declared content type keeps it distinct.

## Maintainer decisions needed

These are rights or ground-truth calls, so they are the maintainer's. **Answered 2026-11-06:** 1, 2, 3, 4 and 7 were accepted. For 5, a legal opinion will be requested. For 6, printed Yiddish is in scope for training and character-level evaluation only. A later decision, 8, allows Pinkas' Hebrew lines for word-level Hebrew evaluation, once each line carries an explicit language tag. See the [decision record](../decisions/2026-11-06-f8-real-source-decisions.md).

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
- `F8b2` (completed): an operator-only inventory of all 141 Wikisource Indexes through the unchanged F8b gates (`hocrgen.tools.wikisource_inventory`). It gathers creators and death years (Wikidata `P570`, Wikisource author pages, the Commons file page), licence templates, scan source and a Google-digitization check per Index, and records missing evidence as missing so the gate rejects it. The full pool stays outside the repo; the committed summary is [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md) with per-Index JSON. No fixture page, source or profile changes. Findings, evidence checked 2026-11-06:
  - 29 of 141 Indexes pass the Index gate: 624 quality-3 and 27 quality-4 pages of the 1,823 / 268 in total.
  - Of those 651 pages, 231 quality-3 and 12 quality-4 pages pass every page gate except transcription coverage, which the inventory does not assess. 4 quality-4 pages are reference-eligible (no text change after validation). 49 of the 231 are the English *She* Index.
  - 408 pages of admitted Indexes fail only on markup outside `wikisource_plain_text.v1`, mostly `{{קטן}}` (222 pages), `{{הערה}}` (39) and `{{גדול}}` (31). Supporting these in the converter is the largest single unlock.
  - The commonest Index rejection is `creator_death_year_missing` (67 Indexes, 682 pages): creators named only as plain text, with no author page or Wikidata link. The top Indexes to resolve, led by Korfu (214 pages) and *Milhamot Hashem* (Gersonides, 188 pages), are listed in the summary.
  - 5 Indexes (116 pages) are Google-digitized and held pending the maintainer's decision; 35 Indexes carry `google_digitization_unchecked` because their files have no text layer to check.
- `F8c` (completed): key the `nli` rights strategy on the IIIF `license` slug, and admit `public-domain-free-use` printed books as `printed_historical`. Images only. The three cached printed-book seeds stay in the exploratory catalog; promoting them to runnable seeds changes the NLI depth count and is a separate step.
- `F8d`: fixture-backed `review_only` imports of the CC-BY-4.0 ground-truth datasets: `pinkas_dataset_bgu` (PAGE XML), and YidTakNL once its bundle is checked. YidTakNL is limited to training and character-level evaluation (decision 6). Scan provenance is verified first. **Implemented:** YidTakNL landed as `yidtaknl_vaybertaytsh_gt`; `pinkas_dataset_bgu` moved to `F8d2`.
- `F8d2`: NLI-matched ground truth. Admit `pinkas_dataset_bgu` once its scans are matched to an NLI free-use record, and match more YidTakNL works to NLI canvases page by page. **Implemented** (see [F8d2 findings](#f8d2-findings-2026-11-06)).
- `F8d3`: per-line language tags for `pinkas_dataset_bgu` (decision 8). A typed tag per PAGE XML line, a single scope derivation in which only a human `he` tag unlocks word-level Hebrew evaluation, and an operator tool that proposes advisory tags for human review. **Implemented** (see [F8d3 findings](#f8d3-findings-2026-11-06)).
- `F8e` (completed): born-digital and typewritten government print (Reshumot from about 2006, Knesset committee scans up to 1975), with automated access allowed (decision 4) and hard throttling. Committee protocols from 1976 on wait for the legal opinion (decision 5). See [F8e findings](#f8e-findings-2026-11-06).

## F8d findings (2026-11-06)

**YidTakNL (`yidtaknl_vaybertaytsh_gt`, implemented).**

- **Format.** The SURFdrive share (public WebDAV) holds one folder per work, with page JPEGs and a `txt/` folder of page-level Transkribus plain-text exports. It has no PAGE XML, no line or word geometry, and no checksums. The sampled 1781 images are scans placed on an A4 300 dpi page (2479 × 3508 px).
- **Text.** The JOHD paper (10:35, 2024) says the first pass came from the Dybbuk HTR model, then both annotators "corrected and double-checked" it. So the text is human-corrected HTR. It is not attested or adjudicated under F2, and the adapter marks it `not_adjudicated`.
- **Scans, per item.**
  - The 1781 *Ampliatsye un' alteratsye* folder matches NLI 990021163940205171: 24 canvases and 24 JPEGs. The manifest licence is `public-domain-free-use`. Pages 7 and 8 were compared visually with the IIIF canvases and are the same scan.
  - The 1747 item (NLI 001294844) is also `public-domain-free-use`, with 16 canvases for 16 JPEGs. It was not compared visually in `F8d`; `F8d2` matched it.
  - The 1737, 1772 and JB 899 folders point to a 15-volume NLI record (990012586850205171, `public-domain-free-use`) whose top-level manifest has no canvases. They need per-volume matching before admission. `F8d2` matched JB 899; 1737 and 1772 do not match.
  - The two HUC Klau Library works (RBR O 128, RBR D 129) show "© 2021 HUC - Photography and Website by Ardon Bar-Hama" and no open licence. They are excluded. The figshare CC BY 4.0 grant covers the creators' work, not HUC's photographs.
- **Scope marker.** Every entry carries language `yi` and `usage_scope.evaluation_scope: character_level_only`, with allowed uses `training` and `character_level_evaluation`, and `word_level` and `language_level_hebrew` excluded (decision 6). The adapter refuses entries without that marker.
- **Fixture.** Two pages of the 1781 work: 640 px thumbnails, and the upstream text bytes unchanged, pinned by sha256. Page-level text has no coordinates to rescale. A metadata-only HUC entry proves the rejection.

**BGU Pinkas (`pinkas_dataset_bgu`, held in `F8d`; admitted in `F8d2`).**

- The two txt files in the zip are only the official split: 24 pages in `train_set.txt` and 6 in `test_set.txt`.
- The ICDAR 2019 paper says only that the pages are "manuscripts from the records of Frankfurt community", digitized as full-colour JPGs. Its acknowledgment credits a proof-reader and a segmenter.
- No source names the holding library, a shelfmark, the photographer, or permission to relicense the photographs. The JPEGs carry no EXIF.
- One lead, unverified: a secondary snippet places the Frankfurt community pinkas at NLI as Ms. Heb. 4°662, with a digital copy online. The page margins carry dates such as 1656–1657. The NLI catalogue is behind Cloudflare, so the record and its licence slug could not be checked.
- Rights are unclear, so no source, fetcher or fixture was added. To unblock it:
  - identify the manuscript and the scan source, for example the NLI record and its IIIF licence slug, plus a visual match;
  - or get a statement from the dataset authors.

  Whether the dataset's CC BY 4.0 can cover third-party photographs of a PD manuscript is a maintainer call.

## F8d2 findings (2026-11-06)

**BGU Pinkas (`pinkas_dataset_bgu`, implemented).**

- **Scan source.** The NLI Search API finds the manuscript as record 990000445290205171, "פנקס קהילת פראנקפורט דמיין", 1552–1802, 324 leaves. The MARC record gives call number `Ms. Heb. 662=24`, that is Ms. Heb. 4°662, so the F8d lead holds. MARC 500 says the volume holds 539 numbered documents, which matches the bracketed numbers in the margins. MARC 597 credits the NLI "Ktiv" project.
- **Scan rights.** The IIIF manifest's `license` is `public-domain-free-use`, and its attribution is the NLI Ktiv project. Both datasets decide scan rights with the F8c gate (`decide_nli_rights`) over pinned `hocrgen.nli_iiif_manifest_capture.v1` captures in each snapshot's `iiif/` folder. A page is admitted only if its canvas is listed in the capture.
- **Match.** The manifest has 330 two-page canvases labelled "Page N". Dataset "Page N_1" is the right half of canvas "Page N", and "Page N_2" is the left half. Pages 105_1, 105_2 and 112_1 were compared by eye with canvases at 1200 px.
- **Rights mapping.** Scan rights come from NLI's slug. Annotation rights are the dataset's CC BY 4.0 (Zenodo licence field). The attribution names both the dataset and the NLI scan.
- **Annotation.** PAGE 2018-07-15 with region, line and word polygons and text. The paper says the pages were annotated semi-automatically in Aletheia, then corrected by a Hebrew paleographer. Not attested or adjudicated under F2: `not_adjudicated`.
- **Language.** The line text mixes Hebrew and Yiddish. Entries are marked `["he", "yi"]`. They carry the same `character_level_only` scope as YidTakNL, as a conservative default. Decision 6 covers printed Yiddish only, so the scope for handwritten mixed Hebrew–Yiddish needs a maintainer decision.
- **Fixture.** Pages 105_1 and 112_1 (train split): 640 px thumbnails, and the upstream PAGE XML bytes gzipped (mtime 0, decompressed sha256 equals upstream). `parse_page_xml_lines` projects line polygons onto the thumbnail, scaling each axis by target/source size. Tests check every point against the unscaled parse.

**YidTakNL, more NLI matches.**

- **Method.** Each upstream page and each candidate NLI canvas was compared at 200 px:
  - both images cropped of white margins and autocontrasted;
  - compared by normalized cross-correlation at 48 × 72 px.

  Upstream checksums come from the share's WebDAV `oc:checksums` (SHA-1, MD5).
- **1747** (NLI 001294844): all 16 pages match canvases 1–16 in order (score min 0.981). Pages 1, 5, 7, 10 and 16 were checked by eye.
- **JB 899 (5th text)**: all 138 pages match, in order, volume sequence `IE143609452` of record 990012586850205171 (min 0.976). That sequence is labelled JB 899, although its canvas labels read `jpg_JB898_*`. Pages 1, 10, 70 and 138 were checked by eye.
- **1737 and 1772**: no page matches any public canvas (medians 0.26 and 0.19). Two volume sequences of the record (`IE205260980`, `IE205263142`) expose no canvases. JOHD 10:35 cites HebrewBooks copies of both works, so the images may come from there. They are not admitted.
- **Snapshot.**
  - 154 matched pages are listed in `matched_pages.jsonl`, pinned by the share's SHA-1 and byte count. They are never candidates; source health checks them.
  - Two more pages are vendored as entries: 1747 page 7 and JB 899 page 10.
  - The rejected HUC entry no longer credits an NLI scan.
  - The JB 899 record's top-level manifest has 0 canvases, which the F8c gate rejects. Its capture therefore also pins the volume sequence (138 canvases, upstream sha256), and the gate sees that count.

## F8d3 findings (2026-11-06)

**BGU Pinkas line language (`pinkas_dataset_bgu`, implemented).** The guide is [`docs/pinkas_dataset_source.md`](../../docs/pinkas_dataset_source.md).

- **Tags.** The sidecar `line_language_tags.yaml` holds one tag per PAGE XML line: `language` (`he`, `yi`, `mixed`, `unknown`), `tag_source` (`human`, `agent_proposed`), `tagged_by`, `tagged_at` and `rationale`. Each tag is bound to the annotation sha256 and the exact line text; a tag that no longer binds is stale.
- **Scope.** One function, `line_scope_fields`, derives each line's scope. Only a human `he` tag gives `word_level_hebrew`; `agent_proposed`, untagged, stale and non-Hebrew lines stay `character_level_only`. The page stays `character_level_only` unless every line is `word_level_hebrew`. The entries' pinned page scope is unchanged. Per-line scope is exposed in candidate metadata and through `load_entry_line_scopes`. No scorer, profile or benchmark changes.
- **Proposals.** `python -m hocrgen.tools.pinkas_line_language propose` matches tokens against closed Western Yiddish and Hebrew marker lexicons (`pinkas_line_lexicon.v1`). It writes only `agent_proposed` tags and never overwrites a human tag. The committed proposals for the 79 fixture lines are 57 `he`, 13 `mixed`, 0 `yi` and 9 `unknown` (numerals and one empty line).
- **Review.** No line is human-tagged; a human reviewer has to confirm or override each line. Until then every fixture line is `character_level_only`.
- **Caveat.** The Yiddish passages in this pinkas sit inside Hebrew-framed entries, so lines are mostly `he` or `mixed`; no line is Yiddish throughout. A page number or an empty line can only be `unknown`, so a page with one never becomes `word_level_hebrew` as a whole; its Hebrew lines still do.

## F8e findings (2026-11-06)

**Reshumot (`reshumot_born_digital`, implemented).** Fetcher `reshumot`, snapshot `src/hocrgen/data/reshumot/snapshot/`.

- **Scope.** Only ספר החוקים (FolderType 1) and קובץ התקנות (3), published on or after 2006-01-01, and only PDFs with born-digital evidence: an InDesign creator, embedded fonts and no page image. ילקוט הפרסומים, bills and the other series are rejected (`series_not_section_6`).
- **Images.** Pages are rendered by HeOCR with `pdftoppm` (poppler 26.07.0) at 150 dpi, 8-bit gray. Each image records `rendering.is_scan: false`, the renderer, its version, the dpi and a pixel checksum, so evaluation never mistakes it for a scan.
- **Bidi.** `pdftotext` writes each RTL line in a bidi-markup form: Hebrew in logical order, but digits, Latin letters and the neutrals next to them in visual order inside LRE … PDF. Stripping the control characters gives, for example, `התשע"ו*2016-`. `hocrgen.parsers.pdf_bidi` inverts the markup, and the result is then checked independently.
  - The checks: no control characters; no word that starts with a final letter form; Hebrew year then `-` and four digits; section numbers as `1.`; parentheses that never close early; Hebrew punctuation followed by a space.
  - It must also contain the booklet number, the date and the law titles that the gazette API lists for that page.
  - Any failure rejects the page's text with `extraction_order_not_verified` plus the check's reason code. The adapter re-derives the text from the committed `pdftotext` output on every run.
- **What the checks found** (all 12 pages of both booklets were run).
  - ספר החוקים 2580: pages 1, 2, 4 and 6 pass. Pages 3, 5 and 7 fail: signature blocks and tables come out merged and out of order. Page 8, the colophon with an ISSN, is flagged `latin_run_order_unverified`.
  - קובץ התקנות 7712: page 1 passes. Pages 2 to 4 fail, because their superscript footnote markers are glued to the year digits on the wrong side (`התשנ"ה-11995`).
  - So born-digital Reshumot text is not uniformly clean, and the per-page check is needed. Page-level reading order follows poppler's layout analysis: side headings and section numbers come out as blocks before the body text.
- **Fixture.** Pages 2 and 4 of ספר החוקים 2580 (16.8.2016), plus page 2 of קובץ התקנות 7712 (13.9.2016), which has no image and is kept to prove the rejection. Each entry pins the PDF's sha256, booklet number and date. The capture made 4 requests to gov.il.
- **Text status.** The text is tier 2 (`born_digital_pdf_text`), `not_adjudicated` and not reference-eligible until F2 attestation and adjudication.

**Knesset committee protocols (`knesset_committee_protocols_pre1976`, implemented).** Fetcher `knesset_committee`, snapshot `src/hocrgen/data/knesset_committees/snapshot/`.

- **Gates.** OData group type 23 (פרוטוקול ועדה) only, from an open session dated on or before 1975-12-31. The date in the document name must match the session date.
  - Sessions from 1976 on are rejected with `post_1975_committee_protocol_pending_legal_opinion` (decision 5).
  - Background material (group type 87, חומר רקע) is rejected with `committee_background_material_not_knesset_work`.
- **Images only.** Each page is the PDF's embedded 300 ppi bitonal CCITT scan, extracted losslessly with `pdfimages`. The PDFs' hidden Imagestore OCR layer is not carried, and an entry with text is rejected.
- **Correction to the verification note.** The 1952 file `2_ptv_399388.PDF` is the Economic Committee (ועדת הכלכלה, session 2026737, 1952-11-25), not the Finance Committee.
- **Fixture.** Pages 2 and 3 of that file, and page 2 of the Economic Committee session of 1975-12-31 (session 2037304, Knesset 8), the last admissible day. Two metadata-only entries prove the gates: the 1976-01-06 session and a background-material file. The capture made 9 Knesset requests, 10 to 15 s apart; the firewall did not block it.

## Sequencing and non-goals

- Every **new** F8 source id (`F8b`, `F8d`, `F8d2`, `F8e`) starts `review_only` and outside `profile_open_v1`. Promotion is a later, explicit PR.
- `F8c` is different: it extends the existing `allowed` source `nli_any_use_permitted`. Its new printed items still reach `profile_open_v1` only through that source's seed vetting and the normal gates. Only `public-domain-free-use` maps to `open`.
- References enter only through F2 reference manifests, after human attestation and adjudication. `benchmark_v1` membership stays frozen.
- F8 adds no live crawling and no network-dependent CI. Fixtures are small and pinned.
- No privacy-review gate is added for public-domain historical sources (maintainer decision 2026-11-06). Modern material about living people, such as recent court rulings, still needs its legal screening; that is one reason the court rulings are deferred.
- F8 does not edit HASH. Two HASH corrections found during the mapping go to HASH separately: the `sivan22` candidate should be rejected, and a cited `MiDRASH-Project` GitHub org does not exist.
