# F8 — Real-source map and paired-text source intake

Status: `F8a` (this map and the F8 notation) is planning only. `F8b` is implemented on the current ref (review-only `wikisource_he_proofread`; see [`docs/wikisource_proofread_source.md`](../../docs/wikisource_proofread_source.md)). `F8b2` is completed (an operator-only inventory of every Wikisource Index through the F8b gate; see [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md)). `F8b3` is completed (decisions 9-12 applied to the Wikisource gates, converter v2 and coverage checks; see [F8b3 findings](#f8b3-findings-2026-11-06)). `F8b4` is completed (tool coverage checks by OCR alignment, crops of partial pages, labelled-section transclusion; see [F8b4 findings](#f8b4-findings-2026-11-06)). `F8b5` is completed (agent review of the coverage and crop residuals, multi-region crops, rename-aware attestation; see [F8b5 findings](#f8b5-findings-2026-11-06)). `F8b6` is completed (the rights residual through cited evidence, and `text_not_on_page`; see [F8b6 findings](#f8b6-findings-2026-11-06)). `F8b7` is completed (footnotes found not printed dropped from the pair text, editors' stand-ins mapped to the printed character, text the scan hides excluded from scoring, and a Korfu spot check; see [F8b7 findings](#f8b7-findings-2026-11-06)). `F8d` and `F8d2` are implemented (see [F8d findings](#f8d-findings-2026-11-06) and [F8d2 findings](#f8d2-findings-2026-11-06)). `F8d3` and `F8d3b` are implemented (per-line language tags for `pinkas_dataset_bgu`, and scope-neutral non-text lines; see [F8d3 findings](#f8d3-findings-2026-11-06)). `F8c` is completed (slug-keyed NLI rights and cached free-use printed-book seeds). `F8c2` is completed (an operator-only inventory of NLI printed Hebrew books by licence slug; see [`docs/nli_printed_inventory.md`](../../docs/nli_printed_inventory.md)). `F8e` is completed (review-only `reshumot_born_digital` and `knesset_committee_protocols_pre1976`; see [F8e findings](#f8e-findings-2026-11-06)). `F8e2` is completed (Reshumot text rebuilt from each page's glyph layer and verified line by line against its render, unverifiable lines cropped out; 796 of the 886 captured pages pass, against 180; see [F8e2 findings](#f8e2-findings-2026-11-07)). `F8f` is completed (an operator-only pilot aligning Project Ben-Yehuda texts to NLI free-use scans into silver pairs; see [F8f findings](#f8f-findings-2026-11-06)). `F8g` is completed (the real sources promoted into the public path under `real_source_composition.v2`; see [`docs/real_source_release_contract.md`](../../docs/real_source_release_contract.md) and [F8g findings](#f8g-findings-2026-11-06)). `F8g2` is completed (tranche hardening: size-aware splits, Pinkas canvas checks, the crop floor, Reshumot and Knesset growth, `wikisource_plain_text.v3`; see [F8g2 findings](#f8g2-findings-2026-11-07)). The maintainer answered the decisions list on 2026-11-06; see [`planning/decisions/2026-11-06-f8-real-source-decisions.md`](../decisions/2026-11-06-f8-real-source-decisions.md). Parent milestone: F8. Source proposals: `HeOCR/hocrgen#103` (`F8b`), `#104` (`F8c`), `#105` (`F8d`) and `#112` (`F8e`). Evidence was checked on 2026-11-06 against each source's own pages and APIs; the per-source notes are in [`docs/2026_11_06_israeli_public_domain_documents_research/verification/`](../../docs/2026_11_06_israeli_public_domain_documents_research/verification/).

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
| 7 | Project Ben-Yehuda public-domain dump texts aligned to NLI `public-domain-free-use` scans of the same edition | `printed_historical` books, 1880s–1930s Hebrew literature | 1 after human verification; silver until then | Text: dump `LICENSE` "public domain" (release `2026-03`). Scans: per item, the NLI manifest licence slug (decision 13) | text `PD-IL`; scan per item through the F8c gate; operator-only pilot, no source yet | `F8f` |

Scale, measured on 2026-11-06:

- **Wikisource:** 141 Index and 6,839 Page pages. Of these, 1,824 are at quality 3 (proofread) and 268 at quality 4 (validated by a second editor). Excluding the Birnbaum works (see below) leaves about 1,600 pages.
- **NLI:** the free-use pool is large; `F8c2` measured it (about 4,460 free-use printed Hebrew books with pages, about 0.53 million pages, in the 20,000 reachable search records; see [`docs/nli_printed_inventory.md`](../../docs/nli_printed_inventory.md)). Example: *Romemut El*, Zolkiew 1764, 208 pages; on 2026-11-06 its page images returned HTTP 500 at every size, so `F8c` lists it as an exploratory seed without a fixture. The Search API (`api2.nli.org.il`, key now available) returns no rights field, only an `accessRights` availability value, so each hit's rights still come from its manifest `license` slug.
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
| Project Ben-Yehuda as a source | Its dump is PD human-typed text (about 26k works), but with no scan links and no page alignment. `F8f` piloted matching and alignment into silver pairs; a `review_only` source waits for a human verification pass. |

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

These are rights or ground-truth calls, so they are the maintainer's. **Answered 2026-11-06:** 1, 2, 3, 4 and 7 were accepted. For 5, a legal opinion will be requested. For 6, printed Yiddish is in scope for training and character-level evaluation only. A later decision, 8, allows Pinkas' Hebrew lines full Hebrew scope, including word-level and language-level Hebrew evaluation, once each line carries an explicit language tag (wording clarified by the maintainer the same day). See the [decision record](../decisions/2026-11-06-f8-real-source-decisions.md).

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
- `F8b3` (completed): unlock the Wikisource pool under maintainer decisions 9-12. It resolves evidence gaps (cited death years and Index languages recorded by an agent, a pre-1856 publication presumption), makes the Commons tag, scan source and Google digitization provenance only, adds a Hebrew language gate, extends the converter to every construct used on admitted pages, checked against MediaWiki's own rendering, and records transcription coverage per page (`needs_crop` for partial pages, for `F8b4`). See [F8b3 findings](#f8b3-findings-2026-11-06).
- `F8b4` (completed): check transcription coverage at scale and crop partial pages (decisions 11 and 12). The operator-only `hocrgen.tools.wikisource_coverage` runs Tesseract on each page render only for line boxes, aligns the human text to them, and records a tool check (`checked_by: tool`, method, version and thresholds) with a crop of the transcribed region; a prior agent or human check overrides it. A partial page's candidate is the cropped sub-image plus the same text, with crop provenance; source health verifies the crop against its page. It also pins labelled-section transclusions (`{{#קטע}}`) and records `footnote_marker_style` per page (masking follow-up: `HeOCR/hocrgen#124`). See [F8b4 findings](#f8b4-findings-2026-11-06).
- `F8b5` (completed): resolve the residuals `F8b4` left. An agent checks the 53 `review_recommended` crops, the 61 `crop_unresolved` pages and the 74 undecided pages visually (`checked_by: agent`, geometry and scope facts, not attestations) and confirms, corrects or places each crop; a crop may be several regions (`regions_normalized`), whose pair image is the union box with everything outside the regions masked to the page background. It also fixes the 16 `quality_attribute_mismatch` drops (the attribute keeps an editor's name before a recorded rename) and records cited death years for the rights residual. See [F8b5 findings](#f8b5-findings-2026-11-06).
- `F8b6` (completed): resolve the Wikisource rights residual and exclude text-image mismatches, on the team lead's decisions of 2026-11-06 about `F8b5`'s open questions (decision 10: data gaps are not rights problems). It admits Korfu 1885 on two cited grounds, and extends the evidence file to creators the wikis do not name, corrections of parsed creators, publication years and additional grounds, so the unchanged gate admits four more Indexes. Pages whose text holds words the scan page does not show get the page reason `text_not_on_page`. See [F8b6 findings](#f8b6-findings-2026-11-06).
- `F8b7` (completed): harden the Wikisource pairs against text the page does not show (`HeOCR/hocrgen#130`, `#111`). The coverage tool looks for each footnote on the page by OCR boxes (localisation only) and flags the ones it cannot find; an agent compared the footnotes of every flagged or unchecked page with the page, and a footnote with no printed counterpart is dropped from the pair text (`unprinted_notes`), the rest of the page kept. Reviewed per-Index stand-in mappings apply after conversion (`{{!}}` and a typed `|` → paseq U+05C0), with the faithful conversion's checksum kept. Text not visible on the scan is kept in the reference and excluded from primary scoring (`illegible_on_scan` spans with boxes; Korfu p. 128's ink blot). A stratified spot check of 30 of the 207 tool-`full_page` Korfu pages agreed on all 30. See [F8b7 findings](#f8b7-findings-2026-11-06).
- `F8c` (completed): key the `nli` rights strategy on the IIIF `license` slug, and admit `public-domain-free-use` printed books as `printed_historical`. Images only. The three cached printed-book seeds stay in the exploratory catalog; promoting them to runnable seeds changes the NLI depth count and is a separate step.
- `F8c2` (completed): an operator-only inventory of NLI digitized printed Hebrew books by IIIF licence slug (`hocrgen.tools.nli_printed_inventory`), to measure the real free-use pool. Rights for every sampled book come from the unchanged F8c gate; a multi-volume manifest is gated per volume, as in `F8d2`. The full inventory stays outside the repo; the committed summary is [`docs/nli_printed_inventory.md`](../../docs/nli_printed_inventory.md) with per-book JSON. No seed, source, composition or `profile_open_v1` change. Findings, evidence captured 2026-11-06:
  - **Method.** Query `language,exact,heb` with `material_type=book` and `availability_type=online_and_api_access`: 38,756 records (`count_mode`). Only the first 400 pages (20,000 records) are reachable: deeper pages return page 1, `sort_field` is ignored, and date clauses silently drop the material and availability filters, so the API cannot be stratified by period. A seeded random sample of 40 pages was drawn from the window; 36 came back filtered (4 failed with repeated HTTP 502), giving 1,800 records and 1,766 `book` records, every manifest fetched.
  - **Licence slugs.** 1,061 books (60.1%) are the Google class `public-domain-non-commercial-use`; 697 (39.5%) are `public-domain-free-use`; 8 carry another slug: `no-license-subject-to-copyright` (5) and `non-commercial-use-license` (3). `F8c2` adds the latter to `NLI_NON_COMMERCIAL_SLUGS`, so the gate records it as `RESTRICTED-NONOPEN` rather than `UNKNOWN`; it was rejected either way.
  - **Pages.** 296 of the 697 free-use manifests (42%) expose no canvases: 179 have an empty sequence, and 117 list sequences by reference whose fetched volumes are also empty. 13 multi-volume free-use records have pages in some volumes. 401 books (22.7%, 95% CI 15.2-30.2%) are free-use with admissible pages: 48,004 pages in the sample, median 40 a book. In the reachable window that is about 4,460 books (95% CI 3,010-5,910) and 0.53 million pages (0.34-0.73 million); about 8,630 books and 1.03 million pages if the unreachable half looks the same.
  - **The result order is blocked**, not random: sampled pages 2-111 and 397 are all Google class, pages 119-247 almost all free-use, and pages 258-374 mixed. The extrapolation beyond the window is therefore weak.
  - **By period.** Free-use dominates the 16th and 17th centuries (35 of 41 and 33 of 56 books with pages). The Google class dominates the 19th and 20th (628 of 927, 365 of 550).
  - **Failures.** No manifest returned 403 or 500 (all 1,766 were HTTP 200); search pages needed 31 retries. 7 of 30 sampled free-use image services answered `info.json` with HTTP 415 ("Identifier … not supported"), so some free-use items may not serve images. The other 23 carried the blanket `nli-copying-prohibited` value, which decision 13 records as evidence only.
- `F8d`: fixture-backed `review_only` imports of the CC-BY-4.0 ground-truth datasets: `pinkas_dataset_bgu` (PAGE XML), and YidTakNL once its bundle is checked. YidTakNL is limited to training and character-level evaluation (decision 6). Scan provenance is verified first. **Implemented:** YidTakNL landed as `yidtaknl_vaybertaytsh_gt`; `pinkas_dataset_bgu` moved to `F8d2`.
- `F8d2`: NLI-matched ground truth. Admit `pinkas_dataset_bgu` once its scans are matched to an NLI free-use record, and match more YidTakNL works to NLI canvases page by page. **Implemented** (see [F8d2 findings](#f8d2-findings-2026-11-06)).
- `F8d3`: per-line language tags for `pinkas_dataset_bgu` (decision 8). A typed tag per PAGE XML line, a single scope derivation in which only a human `he` tag unlocks Hebrew evaluation, and an operator tool that proposes advisory tags for human review. **Implemented** (see [F8d3 findings](#f8d3-findings-2026-11-06)).
- `F8d3b`: two follow-ups to `F8d3`, both decided on 2026-11-06. **Implemented.**
  - **Scope-neutral non-text lines** (coordinator decision). A line with no Hebrew-script letter is classified from its pinned text, never from a tag. It never gets Hebrew scope itself, and it never keeps its page from `full_hebrew`.
  - **Full Hebrew scope** (the maintainer's clarification of decision 8). Human-tagged Hebrew lines get training, character-level, word-level Hebrew and language-level Hebrew evaluation, with nothing excluded. `F8d3` had kept `language_level_hebrew` excluded and called the scope `word_level_hebrew`; it is now `full_hebrew`.
- `F8e` (completed): born-digital and typewritten government print (Reshumot from about 2006, Knesset committee scans up to 1975), with automated access allowed (decision 4) and hard throttling. Committee protocols from 1976 on wait for the legal opinion (decision 5). See [F8e findings](#f8e-findings-2026-11-06).
- `F8e2` (completed): raise the Reshumot pass rate without weakening verification, defined by the team lead on 2026-11-07 from `F8g2`'s finding that only 180 of 886 captured pages pass and none from 2017 on. The text is rebuilt from each page's glyph layer (`hocrgen.parsers.pdf_glyphs`, pdfminer.six, operator-only) instead of `pdftotext`'s flow: glyphs a later opaque fill hides, clipped, in off optional content or painted twice are dropped; each glyph's character comes from a pinned table of TrueType outline hashes where the ToUnicode map is wrong; lines, column gutters, word gaps, letter-spaced names, superscript markers and labels follow from geometry (`pdf_glyph_geometry_logical.v1`, `hocrgen.parsers.pdf_geometry`). Every segment must round-trip through the forward Unicode bidi algorithm, every glyph must hold ink on the render and every inked pixel must be explained; lines that fail are left out and the page is cropped to the verified regions (decision 12). The F8e anchors and order checks still run on the kept text. See [F8e2 findings](#f8e2-findings-2026-11-07).
- `F8g` (completed): promote the real F8 sources into the public dataset path, defined by the team lead on 2026-11-06. It replaces the fixed 27 / 27 / 26 real-source allocation with `real_source_composition.v2` (per-source floors and caps, printed and handwritten floors, admitting every promoted source; the HASH entries wait for `F7d` in the same shape); keeps work, edition and manuscript groups whole across splits and benchmark/holdout checks, with a registry of works whose text feeds synthetic training (hocrsyngen S15a); moves `wikisource_he_proofread`, `yidtaknl_vaybertaytsh_gt`, `pinkas_dataset_bgu`, `reshumot_born_digital` and `knesset_committee_protocols_pre1976` to `allowed` in `profile_open_v1` and the three cached F8c printed books to runnable seeds, with every scope marker, licence and attribution carried into exports (per-item `release_terms`, paired text, `NOTICE.md`, attribution manifest); and packages the full pool outside git with a committed manifest and a hosting proposal. See [F8g findings](#f8g-findings-2026-11-06).
- `F8g2` (completed): harden the F8g tranche, defined by the team lead on 2026-11-07 from F8g's open items, with `HeOCR/hocrgen#134` folded in. It verifies the BGU Pinkas canvas bindings page by page (`docs/pinkas_canvas_match_checks.json`); replaces the per-group hash split with a size-aware, seeded assignment of whole groups per source and modality (`hocrgen.split.balance`, `size_aware_group_split.v1`), with benchmark splits pinned; admits text-region crops down to 32 px when their page passes the page thresholds; confirms the empty YidTakNL texts upstream; grows Reshumot and the Knesset protocols past their fixtures through `hocrgen.tools.real_tranche capture` (F8e gates unchanged); bumps the converter to `wikisource_plain_text.v3` (broken-link labels, versioned F8b7 changes, `text_derivation` provenance) and the tranche to `f8g2_real_tranche_v2`. See [F8g2 findings](#f8g2-findings-2026-11-07).
- `F8f` (completed): an operator-only pilot, `hocrgen.tools.benyehuda_nli_alignment`, that turns Project Ben-Yehuda public-domain texts into silver page–text pairs on NLI `public-domain-free-use` scans of the same edition. It matches catalogue editions to NLI records (rights through the unchanged F8c gate), aligns the PBY text to Tesseract line boxes (OCR for localization only, never as text), crops each page to its located region (decision 12), and writes a side-by-side review report. Every pair is `human_typed_edition_text_aligned`, `not_adjudicated` and `reference_eligible: false`. No source, profile or scoring change; a `review_only` source is a follow-up. See [F8f findings](#f8f-findings-2026-11-06).

## F8e2 findings (2026-11-07)

The method is in `hocrgen.parsers.pdf_glyphs` (extraction), `hocrgen.parsers.pdf_geometry` (conversion and checks) and `hocrgen.fetchers.government_print` (the gate, which re-derives every page). Real pinned pages for every rule are in `tests/fixtures/reshumot_glyph_pages/`.

- **The 706 failing pages, by cause** (F8g2 capture, 84 booklets, 2006-2026; a page may have several):
  - the F8e gate's first reason: `extraction_order_not_verified` 594, `pdf_not_born_digital` 112 (every cover carries the masthead emblem as an image; the 2020-2021 booklets also carry an added stamp);
  - F8e order codes: `missing_expected_phrase` 379, `reversed_hebrew_word` 228, `footnote_marker_merged_into_year` 199, `unbalanced_parentheses` 190, `glued_punctuation` 180, `latin_run_order_unverified` 139, `bidi_controls_present` 87, `control_characters_present` 76;
  - root causes found in the glyph layers: wrong ToUnicode entries for digits and the full stop (523 pages; the full stop is mapped to a space, U+FFFD, `פ`, `ר`, `ו` or `ב` in some subsets, `8` to `ר`, `3` to `ס`); a hidden tagged copy of the page under a white rectangle (178, from 2007 on, every other page), which `pdftotext` merges with the visible text; U+FEFF space glyphs (146); booklets with no space glyphs (86, mostly 2006-2010); the running footer painted twice (54); brackets whose ToUnicode names the drawn shape rather than the logical character (most 2006-2010 subsets).
- **Pass rate: 180 → 796 of 886 (20% → 90%)**; ספר החוקים 479 / 508, קובץ התקנות 317 / 378. No page that passed before fails. 2017-2026: 0 → 243 of 272.

  | Year | Pages | F8e gate | F8e2 | Cropped |
  | --- | --- | --- | --- | --- |
  | 2006 | 56 | 12 | 50 | 18 |
  | 2007 | 54 | 10 | 50 | 30 |
  | 2008 | 32 | 7 | 29 | 13 |
  | 2009 | 34 | 12 | 32 | 11 |
  | 2010 | 72 | 30 | 68 | 20 |
  | 2011 | 36 | 16 | 33 | 3 |
  | 2012 | 44 | 13 | 33 | 10 |
  | 2013 | 110 | 39 | 105 | 18 |
  | 2014 | 76 | 25 | 73 | 14 |
  | 2015 | 64 | 8 | 46 | 11 |
  | 2016 | 36 | 8 | 34 | 13 |
  | 2017 | 52 | 0 | 49 | 12 |
  | 2018 | 32 | 0 | 30 | 18 |
  | 2019 | 28 | 0 | 27 | 15 |
  | 2020 | 26 | 0 | 15 | 15 |
  | 2021 | 10 | 0 | 8 | 8 |
  | 2022 | 28 | 0 | 22 | 8 |
  | 2023 | 28 | 0 | 28 | 8 |
  | 2024 | 12 | 0 | 12 | 8 |
  | 2025 | 8 | 0 | 8 | 5 |
  | 2026 | 48 | 0 | 44 | 17 |

- **Crops (decision 12).** 275 admitted pages are cut to their verified regions (covers to exclude the emblem; others to leave out lines). The lines left out: a dash between two digits (343; one glyph draws both the hyphen, a number separator, and the en dash, a neutral, so `383–385` and `385-383` look the same printed), private-use symbols (103, form check boxes), a quote or prime between two left-to-right runs (67, coordinates `29º 32' 26.33"`), and segments that do not round-trip (12, Latin next to numbers).
- **The 90 pages still out:** no running footer to anchor (16: last pages, colophons); the gazette API's booklet number differs from the print (16: API 7011, print 7511); an API table-of-contents title differs from the print (14); nothing verified to keep (13: blank or image-only pages); the anchor line overlaps a stamp image or another excluded line (13); the API date differs from the print (7: API 2012-11-01, print 1.1.2012); the unchanged order heuristics (`unbalanced_parentheses` 7, all text continuing across a page break; `glued_punctuation` 4).
- **Glyph identity.** `src/hocrgen/data/reshumot/glyph_outlines.json` (`hocrgen.glyph_outline_identities.v1`) holds the 524 outlines of the capture. 9 outlines with conflicting ToUnicode readings were checked by an agent on rendered instances (the full stop and the digits 1, 3, 4, 5, 7, 8, 9 and the comma); 18 bracket outlines record their drawn shape from the glyf points. An outline not in the table makes its glyph unverified, so a new typeface fails loudly.
- **Independent spot checks.** An agent compared 24 then 12 admitted pages with their renders. No wrong letter or digit was found. The first check found broken letter-spaced names, misplaced labels and side headings, coordinates reordered and number ranges reversed; all are fixed or now cropped out. What remains is block order: a side heading whose first line is level with a body line is sometimes merged into it or read after it, and table cells are read row by row or column by column. Line text is verified; block order is a convention.
- **Tranche v3** (`f8e2_real_tranche_v3`): `real_tranche refresh-reshumot` rebuilds only the Reshumot snapshot of tranche v2 and copies every other source byte for byte. Reshumot grows from 182 to 798 pages (796 captured, 275 of them cropped, plus the 2 packaged F8e pages), 84 booklets, 141 MB. The tranche holds 2,611 pages, 1,033 MB and 7,813 files, and `verify` is ok.
- **Readiness on the tranche:** 2,615 real items ship (Reshumot 797: 637 / 80 / 80). Composition is unchanged at 105 counted / 80, because Reshumot is capped at 5. The other four blockers are unchanged.

## F8g2 findings (2026-11-07)

The guide is [`docs/real_source_release_contract.md`](../../docs/real_source_release_contract.md) (§2 and §4).

- **Tranche v2** (`f8g2_real_tranche_v2`): 1,995 pages, 910 MB, 5,689 files: Wikisource 1,455, YidTakNL 123, BGU Pinkas 30, Reshumot 182, Knesset 205.
- **Splits.** `size_aware_group_split.v1` places whole connected groups per `<source>:<content type>` stratum, in a seeded hash order, filling test and validation by item count and leaving the rest in train; benchmark splits and synthetic-training overlaps are pinned. The tranche run splits 1,622 / 186 / 194 (81.0 / 9.3 / 9.7%) against F8g's 65 / 34 / 1.5%. Wikisource is 79.9 / 10.0 / 10.0, Knesset 80.0 / 10.2 / 9.8, Reshumot 80.8 / 9.3 / 9.9, YidTakNL 90.2 / 1.6 / 8.1 (3 works); BGU Pinkas, one manuscript, stays whole in train. The function is pure, for E2d2's reference pool to reuse.
- **Pinkas canvas checks.** 6 of 30 pages verified by an agent against cached NLI canvas images (Pages 105, 112 and 134, both halves), no mismatch. The other 24 are recorded `not_verified`: their canvases were never cached and the NLI IIIF server answered HTTP 520 on 2026-11-07.
- **Crop floor.** The 9 Wikisource crops F8g dropped (83-199 px tall, one to five transcribed lines) are legitimate; `text_region_crop_minimum_height: 32` admits a crop whose page passes the page thresholds. All 9 now ship.
- **YidTakNL empty texts.** All 33 are 0 bytes upstream (re-fetched, HTTP 200, SHA-1 of nothing); the pages are covers, endpapers, blank leaves and 4 leaves with only mirrored show-through.
- **Reshumot.** 84 booklets (2006-2026), 886 pages: 180 pass the F8e gate (20%; ספר החוקים 30%, קובץ התקנות 7%). Nothing from 2017 on passes: the running footer extracts in visual order and the text carries U+FEFF (a `pdf_bidi` follow-up).
- **Knesset.** 18 protocols, Knesset 1-8 (1949-1974), 16 committees, 202 pages, all pass; 34 requests 15 s apart, never blocked. Colour rescans keep their embedded JPEG unchanged.
- **Wikisource v3 (#134).** Broken-link fragments render their label (4 pages); the fifth `|` (Pri Megadim p. 244) is an editor's expansion of the printed abbreviation ה"פ and is now `text_not_on_page`.
- **Readiness on the tranche:** 2,000 real items ship; composition passes with 105 counted / 80 (printed 68, handwritten 32). The other four blockers are unchanged.

## F8g findings (2026-11-06)

The guide is [`docs/real_source_release_contract.md`](../../docs/real_source_release_contract.md).

- **Contract.** `real_source_composition.v2` sets `min_real_items` 80, printed 30 and handwritten 25. The floors and caps per source are:

  | Source | Floor | Cap |
  | --- | --- | --- |
  | Wikisource | 20 | 40 |
  | YidTakNL | 5 | 15 |
  | BGU Pinkas | 10 | 30 |
  | NLI | 0 | 20 |
  | Reshumot | 0 | 5 |
  | Knesset | 0 | 10 |
  | `pinkas_open`, `biblia_open` | 0 | 15 each |

  Reshumot counts toward the total only: its pages are rendered, not scanned. The legacy image-only sources have no floor. The HASH entries are `not_promoted`.
- **Tranche.** It holds 1,610 pages (814 MB), materialized outside git from pinned caches and described by the committed `src/hocrgen/data/real_tranche/` manifest:
  - Wikisource: 1,457 pages from 58 Indexes, of them 240 crops;
  - YidTakNL: 123 pages. These are the 121 matched pages with text, captured from SURFdrive and verified by SHA-1, plus the 2 vendored 1781 pages. 33 matched pages have empty upstream text and are left out;
  - BGU Pinkas: 30 pages, from the Zenodo zip verified by MD5. The NLI manifest came from the F8d2 copy, verified by sha256, because NLI answered HTTP 520.
- **Readiness.** On the packaged fixtures, 21 real items ship, and composition is blocked on the floors. On the tranche:
  - 1,611 real items ship, and the composition gate passes, with 95 counted / 80 (printed 61, handwritten 32);
  - 9 Wikisource crops fail the unchanged normalize height threshold;
  - the other blockers are unchanged: synthetic scale 2 / 80, privacy review (4 legacy NLI and BiblIA items), benchmark references 1 / 3, and takedown verification.
- **Rights.** No rights fact changed. `wikisource_he_proofread` drops `requires_manual_review`, because its agent-recorded rights evidence is committed and replayed through the unchanged gate. The 28 BGU Pinkas pages beyond the fixture are bound to their NLI canvases by the F8d2 label rule, which was verified by eye on 3 pages.
- **Open.** These are left for follow-ups:
  - the splits are lumpy (whole groups; 65 / 34 / 1.5%); `F8g2` makes them size-aware (81 / 9 / 10);
  - Reshumot, Knesset and the NLI free-use pool need captures before they can grow past their fixtures; `F8g2` grows Reshumot (182) and Knesset (205), and NLI waits for its image server;
  - hosting is the maintainer's decision.

## F8b7 findings (2026-11-06)

Issues `HeOCR/hocrgen#130` (systematic text-not-on-page checks) and `#111` (editor stand-ins). The summary is [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md); the agent text reviews and spot checks are in [`docs/wikisource_page_checks.json`](../../docs/wikisource_page_checks.json), the tool's footnote checks in [`docs/wikisource_page_tool_checks.json`](../../docs/wikisource_page_tool_checks.json), the mappings in `src/hocrgen/data/wikisource/editor_standins.json`.

- **Funnel** (quality-3 / quality-4 pages; F8b6 → F8b7): eligible as full pages 1,161 / 56 → **1,159 / 56**; eligible as cropped pages 235 / 5 → **236 / 5**; `text_not_on_page` 12 / 1 → 13 / 1; pages passing every other gate 1,397 / 61 → 1,396 / 61. Reference-eligible quality-4 pages eligible now: 35 of 35, unchanged. The pair count barely moves, but the text of 53 pairs is corrected: 31 drop unprinted notes (37 notes), 21 carry the paseq (44 occurrences), 2 mask text the scan hides. The F8g tranche is regenerated with `hocrgen.tools.real_tranche materialize`, which now applies the text adjustments: 1,609 pages (Wikisource 1,456, of them 241 crops; 4,934 files), and the committed manifest is updated.
- **Unsigned editors' notes (#130.1).** Decision: drop the note, keep the page, when the rest of the text matches; a page with other words the page does not show stays `text_not_on_page`.
  - The tool's footnote check (OCR boxes only) located every note on 42 of the 132 pages with footnotes, flagged 47 and could not check 43 (short notes, or pages Tesseract reads badly). Flagged pages wait for review (`footnote_not_located`); none is left.
  - An agent reviewed all 90 flagged and unchecked pages. 29 of the 47 flagged pages and 9 of the 43 unchecked ones hold an unprinted note: 62 notes on 38 pages, mostly modern corrections (צ"ל), cross-references, identifications, translations and pointers to Wikipedia or a talk page. The tool's 18 false flags are printed notes it missed: Biblia Hebraica's one-line qere apparatus (read as page furniture), the Raavad's inset glosses in Mishneh Torah, small citation lines.
  - Of the six F8b6 pages that were `text_not_on_page` only for an unsigned note, the tool flagged two and could not check four; all six are pairs again.
  - The review found 6 more pages with words the page does not show: an editors' heading and introduction to compiled parallels (Tosefta pp. 116-117), a paraphrase and a placeholder for two Yiddish rubrics (Seliḥot p. 44), and three emendations of the print the editors' own notes describe (Korfu pp. 18, 182, 414).
  - An editor's heading that labels the footnote list (`==הערות==`, `==הערות שוליים==`) is now dropped by the converter (2 pages, both checked on the image and against MediaWiki).
- **Korfu spot check (#130.2).** 30 of the 207 tool-`full_page` Korfu pages, six alignment-score strata of five spread over the book: the coverage verdict agreed on all 30 (disagreement under 10% at 95% confidence). Text findings: p. 156 writes out an abbreviated refrain on fifteen lines (`text_not_on_page`); p. 90 loses two final letters to the gutter shadow (masked); pp. 78 and 356 carry unsigned notes (dropped).
- **Korfu p. 128 (#130.3).** Decision: mask the text, not the page. `illegible_on_scan` spans record the covered text by offsets in the pair text and boxes on the page; the reference keeps the text, the F2 record marks it `illegible` / `exclude_primary`, and item metadata lists it in `reference_normalization.excluded_spans` for evaluation to mask. Three spans (111 characters) on p. 128.
- **Editor stand-ins (#111).** `typed_pipe_as_paseq.v1` maps `|` between Hebrew words to U+05C0 in Seliḥot, Siddur Torah Ohr and Korfu: 49 occurrences on 23 pages (one `{{!}}`, the fixture's Seliḥot p. 34), 11 of them checked on 1920 px renders, all at Masoretic paseq or legarmeh positions. The page keeps the faithful conversion's checksum, and attestation is unchanged. The survey's other candidates (ASCII quotes for gershayim and geresh, colon for sof pasuq, hyphen for maqaf) are not mapped: the prints use one shape for both characters, or, for the hyphen, the occurrences are not checked yet. 5 more `|` are editors' broken link targets, not stand-ins; `F8g2` resolves them (`wikisource_plain_text.v3`). `primary.v1` keeps every such pair apart.

## F8b6 findings (2026-11-06)

Team-lead decisions on `F8b5`'s open questions, under maintainer decision 10, 2026-11-06:
1. admit Korfu on two cited grounds;
2. extend the evidence file to creators, publication years and anonymous markers, with the gate logic unchanged;
3. exclude pages whose text is not all on the page, as `text_not_on_page`, and keep them listed;
4. *Tzni'uta* needs nothing.

The evidence is in [`docs/wikisource_index_evidence.json`](../../docs/wikisource_index_evidence.json), and the summary is [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md).

- **Funnel** (quality-3 / quality-4 pages; F8b5 → F8b6):
  - Indexes admitted: 72 → 77; pages in admitted Indexes: 1,190 / 48 → 1,411 / 62.
  - **Eligible as full pages: 946 / 43 → 1,161 / 56.**
  - **Eligible as cropped pages: 241 / 5 → 235 / 5.** Nine cropped pages moved to `text_not_on_page`; new pages added 3.
  - Not paired as `text_not_on_page`: 12 / 1. Coverage not decided: 1. Empty text (`page_text_empty`): 2.
  - Reference-eligible quality-4 pages eligible now: 29 → 35 of 35.
- **Korfu 1885 (214 pages) is admitted on two grounds**, both recorded by an agent:
  - **A death year.** Joseph Nahamuli / Giuseppe Nacamulli, the translator and printer, died in 1886. The source is Columbia University Libraries' exhibition "The Jews of Corfu", linked to the 1885 translator through Encyclopaedia Judaica ("Corfu"); `evidence_kind: secondary_sources`.
  - **The transcribed text.** Every transcribed page is the traditional Hebrew Sephardic liturgy, or the Hebrew title page. Nachmuli's own Greek translation is on untranscribed pages, so it is in no pair (`additional_grounds`).
  - The coverage tool decided 213 of the 214 pages, 207 of them full. An agent checked the other 7 (6 the tool called partial, 1 it could not decide): an ink blot, a gutter shadow, a stamp and a scribble had misled the tool, and all 7 are full.
- **Four more Indexes, through the extended evidence file:**
  - ***Dorot ha-Rishonim* I** (10 pages): an added creator, Yitzhak Isaac Halevy, d. 1914 (Q8053923).
  - ***Artush*** (7 pages): an added editor, Abraham Berliner, d. 1915 (Q90649). The additional ground is that the 1279 Hebrew translation he edited is anonymous.
  - **Hebrewbooks 9418** (2 pages): Saadia Gaon d. 942 (Q328748) and an added translator, Judah ibn Tibbon, d. 1190 (Q745336). The parsed honorific "רבנו" is `not_a_creator`, and the publication year is 1562, from the first edition's title page in the photo-reprint.
  - ***Kol Machzike Hadas*** (2 pages): the editorial board is `anonymous` (an unsigned 1883 editorial), and three fragments of the Commons author sentence are `not_a_creator`. The basis is `anonymous_published_by_1955`.
- **`text_not_on_page` (13 pages, from the `F8b5` review notes).** In each, the text holds words the scan page does not show:
  - an editors' Hebrew paraphrase of a printed Yiddish rubric (Selihot pp. 26, 30, 58, 67);
  - a placeholder asking for a translation (Selihot p. 42);
  - a bracketed passage the editors' own note says is not printed (Selihot p. 10);
  - a footnote's continuation merged in from later pages (*Mishpetei ha-Te'amim* p. 14);
  - unsigned editors' notes with no printed counterpart (Luzzatto pp. 138, 149, 152; Siddur Torah Ohr pp. 192, 194; *Qav ve-Naqi* p. 15).

  Other pages can carry such unsigned notes too: the converter cannot tell them from printed footnotes, and only reviewed pages are flagged.
- **The converter, for the new pages:**
  - `{{חיריק ללא אות}}` (ZWJ and hiriq), `{{רווח בין אותיות}}` (letter-spaced text) and `{{שיר מנוקד}}` (a vocalised poem).
  - All 235 newly admitted pages match MediaWiki's `action=parse` token for token, 233 of them line for line; there are three new render fixtures.
- **Still rejected:** 10 Indexes, 79 pages. They are modern works, a creator who died after 1955, creators no source identifies, or the Ladino *Tehilim*.

## F8b5 findings (2026-11-06)

Evidence checked 2026-11-06; the committed summary is [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md), the agent checks and crops are in [`docs/wikisource_page_checks.json`](../../docs/wikisource_page_checks.json) and the tool checks in [`docs/wikisource_page_tool_checks.json`](../../docs/wikisource_page_tool_checks.json).

- **Funnel** (quality-3 / quality-4 pages; F8b4 → F8b5): Indexes admitted 68 → 72; pages passing every other gate 1,167 / 48 → 1,188 / 48; **eligible as full pages 837 / 43 → 946 / 43**; **eligible as cropped pages 196 / 4 → 241 / 5** (98 crops placed or confirmed by an agent, 29 of them multi-region); unreviewed `review_recommended` crops 53 → 0; `crop_unresolved` 61 → 0; coverage not decided 74 → 1. Reference-eligible quality-4 pages eligible now: 28 → 29 of 29.
- **Agent visual review of 188 pages** (annotated 960 px renders with the tool's boxes and a page-coordinate grid; every corrected or placed crop checked on a preview of the pair image): 89 `full_page`, 98 `partial_page`, 1 undecidable. Crops: 13 tool crops confirmed, 64 corrected, 21 placed; confidence 137 high, 51 medium, none low. The lead agent spot-checked 3 decisions (a two-region Luzzatto crop and two full verdicts on pages the tool called partial) and agreed with each.
  - Of the 53 `review_recommended` crops, 20 pages are full (two-column Rashi pages the tool misread) and 33 partial (13 crops confirmed, 20 corrected or placed). Of the 61 `crop_unresolved` pages, 14 are full and 47 partial. Of the 74 undecided pages, 55 are full and 18 partial; one cannot be decided (below).
  - **The tool's own region crops are proposals, not answers**: none of the 46 it placed was right as it stood. On Luzzatto the commentary quotes verse words as lemmas, so verse lines align and get a region; elsewhere a stray region lands on a catchword or in a variant apparatus. Region crops are now always flagged `review_recommended`; the applied ones are all agent crops.
  - Systematic misses the review corrected: Rashi-script commentary lines at the top of a block left out of the tool's crop; chapter headings between commentary blocks; Italian blocks absorbed by interpolation.
- **Multi-region crops** (`ocr_alignment_region_mask.v1` from the tool, `agent_visual_crop.v1` from an agent): the pair image is the regions' union box; every pixel outside the regions is set to the recorded `mask_fill` (the page background, the upper quartile of each channel under the box), and each region is pasted from the page unchanged. Masking keeps the regions where they stand on the page, so line geometry is the print's. Source health and acquisition rebuild the image from the page and compare it pixel for pixel.
- **`quality_attribute_mismatch` (16 pages) was our bug.** The `<pagequality user=...>` attribute keeps the name an editor had when setting the quality; the page history shows the account's current name. All 16 are global renames recorded on Meta: איתן96 → Eitan96 (2014-07-30, log 9259138; 3 pages of Hebrewbooks 38168) and Elendil 03 → J. Nord (2025-03-21, Meta log 59156686, local log 1749979; 13 pages of Baer's siddur). The inventory now records the rename log entries of an editor whose attribute differs (`user_renames`), and the gate accepts the attribute only through a recorded rename of the same account made after the edit.
- **Still not eligible**: `עמוד:ויכוח על חכמת הקבלה.pdf/47` (its text continues with about 6,000 characters an editor marked as coming from pages missing in the scan: coverage undecidable); 2 pages with empty text (`page_text_empty`: Luzzatto p. 499 and the *Safa Ahat* p. 3 cover).
- **Rights residual**: 19 Indexes / 320 pages → 15 / 314. Cited death years admit *Safa Ahat le-Khulanu* (translator Naftali Herz Neimanovitch, d. 1898, Wikidata Q25491331), *Or Hashem* Vilna 1905 (commentator Hayim Yirmeyahu Flensberg, d. 1914, Q117353685), *Hanokh* (translator Abraham Kahana, d. 1946, Q12403383) and Siddur Farhi 1917 (Hillel Farhi, d. 1940, Encyclopaedia Judaica). **Korfu (214 pages) is left for the maintainer**: the book is the traditional Hebrew Sephardic liturgy with a facing Greek translation; all 214 transcribed pages are the Hebrew pages, with no Greek. A Columbia University Libraries exhibition dates Giuseppe Nacamulli, the Corfu printer and founder of *Cronaca Israelitica*, 1821-1886, and Encyclopaedia Judaica names Joseph Nahamuli as that paper's printer and Greek translator; the identification is strong but rests on a secondary source (no Wikidata or NLI dates), so no death year is recorded. The other residual Indexes need facts the evidence file cannot record yet (creators the wikis do not name, a corrected publication year, an anonymous editorial), are modern works, or have creators no source identifies; the per-Index facts are in the PR.

## F8b4 findings (2026-11-06)

Evidence checked 2026-11-06; the committed summary is [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md) and the tool checks are [`docs/wikisource_page_tool_checks.json`](../../docs/wikisource_page_tool_checks.json).

- **Funnel** (quality-3 / quality-4 pages; F8b3 → F8b4): pages the converter renders 1,171 / 48 → 1,184 / 48; pages passing every other gate 1,154 / 48 → 1,167 / 48; **eligible as full pages 82 / 43 → 837 / 43**; **eligible as cropped pages 0 / 0 → 196 / 4** (53 of them on poorly read pages, flagged `review_recommended`); `partial_page` without a resolved crop (`crop_unresolved`) 25 / 5 (no crop existed) → 60 / 1; coverage not decided 1,047 / 0 → 74 / 0 (the tool's alignment too poor). Still dropped: 16 pages for `quality_attribute_mismatch` (attestation) and 1 for `page_text_empty`. Reference-eligible quality-4 pages eligible now: 25 → 28 of 29.
- **Validation against the 156 agent checks** (partial as the positive class): the tool decided 149; agreement 131 / 149 (87.9%); partial precision 21 / 31 (0.68), recall 21 / 29 decided (0.72), 21 / 31 overall (0.68); full-page precision 110 / 118 (0.93). The 8 missed partials are single untranscribed lines (a Latin heading inside a Hebrew page, a short footnote, a Judeo-German rubric replaced by a Hebrew paraphrase); the 10 extra partials are mostly title pages whose stamps, ornaments or imprints the tool crops away, which the agent counts outside the body. For the 31 agent-partial pages the tool placed 29 crops; 1 is unresolved (too much untranscribed text inside) and 1 page's text is not on the page at all.
- **Visual spot checks** (agent): 40 previously unchecked pages, stratified by tool outcome and Index (20 full, 14 partial, 6 undecided), the 25 decided pages with the lowest alignment score, and 10 crops of agent-partial pages. Full pages: 18 of 20 consistent, 1 miss (one untranscribed Italian line too thin for the unread-ink check), 1 uncertain (a block of unaligned lines on a poorly read page; a block rule added after the review now flags such blocks). Partial pages: 11 of 14 consistent, 3 benign (a scan edge or stamp counted, the crop is the body minus it); no crop seen cutting transcribed text away. One failure mode found and flagged: on a poorly read page, interpolation can absorb an untranscribed block set between transcribed ones (Luzzatto p. 82); crops on pages where under half the transcription aligns carry `review_recommended`.
- **Where the tool cannot decide**: Rashi and other ornate type and vocalised verse that Tesseract's Hebrew model reads badly: Luzzatto's commentary, *Sippurei Ma'asiyot*'s Rashi pages, 12 of the 13 *Qav ve-Naqi* transclusion pages, and several siddurim. `crop_unresolved` is led by Luzzatto (25 pages: verse and Italian blocks interleaved with the commentary), *Sefer ha-Mispar* (7) and *Sippurei Ma'asiyot* and the Seliḥot (6 each).
- **Transclusion**: the 13 `{{#קטע}}` pages convert, with 6 transcluded pages pinned by revision; all 13 match MediaWiki's rendering line for line.
- **Footnotes**: 118 / 2 converting pages carry footnotes written `[n]`; each records `footnote_marker_style: bracketed_index`.
- **Follow-ups**: human review of `review_recommended` crops and of `crop_unresolved` pages (a two-crop split for interleaved untranscribed blocks would resolve most Luzzatto pages); a Rashi-script OCR model for localisation would decide most of the 74 undecided pages; evaluation masking of footnote marks (`HeOCR/hocrgen#124`).

## F8b3 findings (2026-11-06)

Evidence checked 2026-11-06; the committed summary is [`docs/wikisource_index_inventory.md`](../../docs/wikisource_index_inventory.md).

- **Funnel** (quality-3 / quality-4 pages; F8b2 → F8b3): Indexes admitted 29 → 68; pages in admitted Indexes 624 / 27 → 1,184 / 48; pages the converter renders 231 / 12 → 1,171 / 48; pages passing every other gate 231 / 12 → 1,154 / 48. Of the 156 pages checked for coverage, 125 are `full_page` and 31 `partial_page`: **82 quality-3 and 43 quality-4 pages are eligible now** (25 of the 43 reference-eligible), and 25 / 5 are `needs_crop` (one partial page has an empty transcription and is rejected as `page_text_empty`). 1,047 quality-3 pages await a coverage check.
- **Evidence gaps.** Cited death years (Wikidata `P570`, with NLI authority ids) were recorded for 14 creators named only as plain text, among them Gersonides (1344), Everardus van der Hooght (1716), Nathan of Breslov (1844) and Nachman Goldstein of Tcherin (1894); Index languages for 16 plainly Hebrew Indexes the wikis leave unrecorded. Seven gaps were looked for and left open, each listed in the evidence file with the reason: among them Yosef Nachmuli of Korfu (the only Wikidata match died in 1785, so it is another man), Pseudo-Aristotle and the editor of *Sefer ha-Tapuah*, and the scan source of *Vikuah al Hokhmat ha-Kabbalah*.
- **Residual** (decision 10): 19 Indexes with 320 quality-3/4 pages stay unresolved, led by Korfu (214 pages: no death year for the 1885 translator, language unrecorded).
- **Converter.** On 313 pages rendered by MediaWiki, 299 match token for token; the other 14 differ only where the converter repairs editors' markup errors or drops editors' signed notes. Printed footnote marks (`*)`) are not typed by editors, so notes carry MediaWiki's `[n]`. The 13 pages that still fail use labelled-section transclusion (`{{#קטע:...}}`) and need the transcluded pages pinned.
- **Coverage.** Partial pages are concentrated: Luzzatto's Bereshit (the Bible verse and Italian translation are not transcribed), Buber's Tanhuma (his notes section is not), *Sippurei Ma'asiyot* (the Yiddish columns are not).

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
- **Scope.** One function, `line_scope_fields`, derives each line's scope. Only a human `he` tag gives `full_hebrew`; `agent_proposed`, untagged, stale and non-Hebrew lines stay `character_level_only`. The page stays `character_level_only` unless every line is `full_hebrew` (`F8d3b` exempts non-text lines). The entries' pinned page scope is unchanged. Per-line scope is exposed in candidate metadata and through `load_entry_line_scopes`. No scorer, profile or benchmark changes.
- **Proposals.** `python -m hocrgen.tools.pinkas_line_language propose` matches tokens against closed Western Yiddish and Hebrew marker lexicons (`pinkas_line_lexicon.v1`). It writes only `agent_proposed` tags and never overwrites a human tag. The committed proposals for the 79 fixture lines are 57 `he`, 13 `mixed`, 0 `yi` and 9 `unknown` (numerals and one empty line).
- **Review.** No line is human-tagged; a human reviewer has to confirm or override each line. Until then every fixture line is `character_level_only`.
- **Caveat.** The Yiddish passages in this pinkas sit inside Hebrew-framed entries, so lines are mostly `he` or `mixed`; no line is Yiddish throughout.
- **Non-text lines (`F8d3b`).** In `F8d3`, a page number or an empty line could only be `unknown`, so a page holding one never became `full_hebrew`. The coordinator answered on 2026-11-06: such lines are scope-neutral. A line with no letter in U+05D0–U+05EA (digits, punctuation, years, empty) is classified from its pinned text, not from a tag. It is never word-level evaluable itself, and the page rule ignores it. The page is `full_hebrew` once every text line is. In the fixture, 9 of the 79 lines are scope-neutral; they are the same 9 lines proposed `unknown`.

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

## F8f findings (2026-11-06)

The summary is [`docs/benyehuda_nli_alignment_pilot.md`](../../docs/benyehuda_nli_alignment_pilot.md), with per-candidate and per-page rows in [`docs/benyehuda_nli_alignment_pilot.json`](../../docs/benyehuda_nli_alignment_pilot.json).

- **Match rate.** 11 of 45 candidate editions (24%; 11 of 42 with an answer) match a `public-domain-free-use` scan with canvases. 13 found editions are Google class, 3 are free-use with no canvases, 15 have no NLI record, and 3 searches failed. Most editions up to 1905 are Google class; 10 of the 11 matches are from 1907–1938.
- **Edition evidence.** Each match is tied to its edition by title, publisher and year terms checked against the NLI record and manifest. The two aligned matches are confirmed by their page sequences. One match, Asaf Halevi's Dekel 1920 poems, is weak: PBY's edition string covers two books.
- **Alignment.** 277 pages of 10 works on 2 scans (Brainin's *Avraham Mapu*, 1928; 9 stories of Silman's *Sansinim*, 1929). 275 pages are `high` (alignment score at least 0.90), 2 `medium`; median strict character similarity 0.981. 230 pages crop cleanly; 47 are `needs_review` (catchwords merged into the last line, footnotes or other print lines inside the text block).
- **Differences PBY makes.** It drops running heads and page numbers (263 pages), catchwords (21), and the table of contents. It moves footnotes to the end of the work (24 pages) and normalizes the print's low-high quotes (73). It adds niqqud in quoted poems (22 pages; the print's niqqud is not measurable by OCR). It shows ו/י spelling variants (331 words against 55,084 identical, an upper bound). It omits one full page of Brainin (canvas 128).
- **Not reached.** The other 9 matches, including poetry, were not aligned because the NLI image server returned HTTP 520 for the rest of the run.

## Sequencing and non-goals

- Every **new** F8 source id (`F8b`, `F8d`, `F8d2`, `F8e`) starts `review_only` and outside `profile_open_v1`. Promotion is a later, explicit PR: `F8g` promoted them under `real_source_composition.v2`.
- `F8c` is different: it extends the existing `allowed` source `nli_any_use_permitted`. Its new printed items still reach `profile_open_v1` only through that source's seed vetting and the normal gates. Only `public-domain-free-use` maps to `open`.
- References enter only through F2 reference manifests, after human attestation and adjudication. `benchmark_v1` membership stays frozen.
- F8 adds no live crawling and no network-dependent CI. Fixtures are small and pinned.
- No privacy-review gate is added for public-domain historical sources (maintainer decision 2026-11-06). Modern material about living people, such as recent court rulings, still needs its legal screening; that is one reason the court rulings are deferred.
- F8 does not edit HASH. Two HASH corrections found during the mapping go to HASH separately: the `sivan22` candidate should be rejected, and a cited `MiDRASH-Project` GitHub org does not exist.
