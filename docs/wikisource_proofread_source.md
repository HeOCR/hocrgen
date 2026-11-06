# Hebrew Wikisource proofread-page source (F8b, F8b3, F8b4, F8b5, F8b6)

Source id `wikisource_he_proofread`, fetcher `wikisource_proofread`. Source proposal: `HeOCR/hocrgen#103`. Plan: [`planning/tasks/f8-real-source-map.md`](../planning/tasks/f8-real-source-map.md).

Each item is one ProofreadPage `עמוד:` (Page) page on he.wikisource.org at quality 3 or 4, paired with the same page of its Index's Commons PDF/DjVu file. The page text is human-made: typed and proofread by named Wikisource editors against that scan.

## Status and rights

- `status: review_only`, `default_public_release: false`, `requires_manual_review: true`. Included only in `profile_review_v1`; not in `profile_open_v1`.
- Page text: `CC-BY-SA-4.0` / `sharealike` (the site licence, maintainer decision 1, 2026-11-06). Share-alike applies to any reference file HeOCR releases from it. Attribution is "Hebrew Wikisource contributors" plus the pinned page permalink.
- Scan: rights per Commons file. Each item carries the Commons file title, its SHA-1, the file-page revision id and the licence templates.
- Privacy source default `clear`. No privacy-review gate: this is public-domain historical print. Manual review covers the agent-recorded rights evidence.

## Admission per Index

An Index is admitted when its record shows that the work is public domain in Israel and that the Index is Hebrew. The rules live in `hocrgen.fetchers.wikisource.index_exclusion_reasons`. Maintainer decisions 9 and 10 (2026-11-06, applied in F8b3) set what counts: missing Commons or Wikidata evidence is a data gap to resolve, not a rights problem.

1. **The work is public domain in Israel** (`work_rights.basis`):
   - `author_died_by_1955`: every recorded creator (author, editor, translator) has a death year of 1955 or earlier, with an evidence URL;
   - `presumed_pd_by_publication_age` (decision 10): the work was published in 1855 or earlier, with the publication year's evidence recorded (`work.published_year_evidence`). No death year is needed: its creators would have had to live more than 100 years after publication to still be protected;
   - `state_work_by_1975`: a state work created in 1975 or earlier, with the state body named;
   - `anonymous_published_by_1955`: an anonymous or pseudonymous work published in 1955 or earlier.
2. **The scan** (`scan_rights.basis`) is a `faithful_reproduction_of_pd_work`, or carries an `explicit_open_licence` (`CC0-1.0`, `PDM-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`). A faithful reproduction of a PD work needs no recorded scan source and no licence template. The Commons tag (`PD-US-*`, missing, or other) never decides the work's status. `scan_rights.scan_source` is recorded where it is known (`scan_source_origin`: `hebrewbooks`, `open_siddur_project`, `national_library_of_israel`, `internet_archive`, `unrecorded`), as provenance.
3. **Google-digitized scans are admitted** (decision 9) under the same check. `scan_rights.digitized_by_google` stays as recorded provenance (`scan_digitized_by_google` on each item).
4. **The Index is Hebrew** (team lead, F8b3): `work.language` must be `he`, read from the Index page's `שפה` field, else the Commons file's `language` field, else a fact recorded in the evidence file with its evidence. The English Index *She* (a Hebrew translation typed over an English scan) is rejected.

Real protection still excludes:

| Reason code | Rule |
| --- | --- |
| `excluded_birnbaum_work` | The Birnbaum Siddur (1949) and Haggadah (1953) are always excluded (Birnbaum died in 1988). |
| `creator_died_after_1955` | A recorded creator died after 1955. The publication-age presumption never overrides it. |
| `index_language_not_hebrew`, `index_language_unrecorded` | The Index language is not `he`, or no language is recorded. |
| `creators_missing`, `creator_death_year_missing`, `publication_year_missing`, `published_after_1855` | A data gap that is not resolved yet: a work after 1855 with no findable death year, or no publication year. These are reported as the residual, with what is missing. |
| `work_rights_basis_unsupported`, `work_rights_evidence_missing`, `state_work_evidence_missing`, `state_work_after_1975`, `named_creator_on_anonymous_basis`, `anonymous_work_after_1955` | Work evidence missing or outside Israel's terms. |
| `commons_file_unpinned` | No Commons SHA-1 or file-page revision id: the scan cannot be identified. |
| `scan_rights_basis_unsupported`, `scan_rights_evidence_missing`, `scan_licence_not_open` | The scan record is malformed. |

`pd_us_only_licence`, `no_licence_template`, `scan_provenance_unrecorded`, `google_digitized_scan_pending` and `google_digitization_unchecked` are no longer reasons (F8b3). Scans that came from HebrewBooks are admitted on the same check (maintainer decision 3).

## Pages, quality and attestation

- Only quality 3 (proofread) and 4 (validated) are admitted. Quality 0–2 is skipped (`quality_not_proofread`).
- The page history is read at capture time. Each quality change is recorded with its revision id, editor, user id and user groups. The editor who set quality 3 is the **proofreader**; for quality 4, the editor who set 4 is the **validator**.
- A page is rejected when:
  - an editor who set quality is not a named human (an empty name, an IP edit, the `bot` group, or a name ending in "bot");
  - the `<pagequality user=...>` attribute disagrees with the editor who made that revision. The attribute keeps the name the editor had at the time, and the history shows the account's current name, so a rename is followed (F8b5): the inventory records the global (Meta `gblrename`) and local (`renameuser`) rename log entries of an editor whose attribute differs (`user_renames`, with the log id and time), and the attribute matches when a recorded rename of the same account, made after the edit, leads from it to the current name;
  - the validator is also the proofreader, by username or by user id;
  - a check found words in its text that the scan page does not show (`text_not_on_page`, F8b6): an editor's paraphrase of a printed rubric, an editor's placeholder or note with no printed counterpart, or text merged in from other pages. Text and image do not match, so the page is not a pair; the check says what the text holds, and the summary lists the pages;
  - its transcription coverage was never recorded (`transcription_coverage_unrecorded`), or is not `full_page` / `partial_page` (`transcription_coverage_unknown`);
  - the pinned wikitext does not carry the recorded quality, or uses markup the converter does not support (`wikitext_unsupported_markup`).
- **Partial pages are cropped, not dropped** (decision 12, F8b4). A `partial_page` transcription (for example commentary without the verse above it) pairs its text with a crop of the page image to the transcribed region (see [Crops](#crops-of-partial-pages-f8b4)). The item carries `needs_crop: true` and its `crop` provenance. A partial page without a crop is rejected and reported: `crop_unrecorded` (no tool crop for the pinned revision and scan), `crop_unresolved` (the tool could not place one) or `crop_geometry_invalid` (the box is not inside the page).
- Quality 4 is human-attested and **adjudication-eligible**, but only while the pinned plain text equals the text at the validating revision. Any later edit that changes the plain text sets `adjudication_eligible: false` with `text_changed_after_validation`. This holds even when the validator made the edit.
- Quality 3 is single-reviewer human proofreading (`quality_3_single_reviewer`): never adjudication-eligible.
- hocrgen never edits or attests Wikisource pages.

## Transcription coverage checks

Coverage is a scope fact, not an attestation: whether the text covers the whole printed page body. Running heads, page numbers, catchwords and signature marks are outside the body; footnotes and marginal notes are inside it. Each check records:

- `transcription_coverage` (`full_page` or `partial_page`) and, for a partial page, `missing`: what is not transcribed, in words (no page text);
- `checked_by` (`tool`, `agent` or `human`), the `checker`, `checked_at` and the `method`;
- the page revision and the Commons file SHA-1 it was made against. A check made on another revision or file is stale and not applied.

A human check overrides an agent check of the same page, and either overrides a tool check. Checks never change a quality level or a proofreader's attestation. The fixture pages' checks are in `pages.jsonl`; the inventory's agent and human checks are in [`wikisource_page_checks.json`](./wikisource_page_checks.json) and its tool checks in [`wikisource_page_tool_checks.json`](./wikisource_page_tool_checks.json).

### Tool checks: OCR used for localisation only (F8b4)

`hocrgen.tools.wikisource_coverage` checks coverage at scale. For each page it runs a local OCR engine, Tesseract with its Hebrew model, called as a subprocess (an operator tool, not a hocrgen dependency), **only to get line and word boxes**. It then aligns the page's human text to the OCR lines and records a check with `checked_by: tool`, the tool version, the method id (`tool_ocr_alignment_v1`), the OCR engine (version, model SHA-256, the pass used) and every threshold. OCR text is never stored, never merged into the reference and never used as text: a check holds boxes, counts and scores only, and a test asserts that no OCR or page text is in it.

- **Alignment.** Both texts are reduced to letters and digits (NFKC, no niqqud or cantillation, Hebrew final forms folded, `[n]` footnote marks dropped). Each OCR line is matched to the transcription by character-trigram votes on one diagonal band, so it matches only where the transcription has the same run of text in the same order, with bounded drift. Lines OCR misreads are recovered when they sit between two aligned lines (in Tesseract's order, or directly above and below in the same column) and the transcription has unmatched text of a fitting length between those lines' matches (`interpolated`). Untranscribed text interleaved with transcribed text has no such gap.
- **Unread print.** Bands of ink that no readable OCR line covers (a vocalised verse block Tesseract skipped, for example) count as untranscribed text. Thin bands (rules, niqqud rows), narrow ones (scan borders) and tall unbroken ones (illustrations, ornaments) are ignored.
- **Page furniture.** A short line above all transcribed lines (a running head) and short lines below them (page number, catchword, signature) are ignored, as are narrow, off-centre marks in the top or bottom band of the page (library and digitisation stamps); the crop still excludes them.
- **Verdict.** `full_page` when the untranscribed text-bearing lines are at most 4% of the text area (10% on a poorly read page, where under half the transcription aligns) with at most one such line and no unread print block; else `partial_page`. When too little of the transcription is located in the image (aligned and interpolated lines span under 60% of it, or aligned lines under 20%), the tool decides nothing (`outcome: alignment_too_poor`) and the page stays undecided.
- **Passes.** OCR runs on a greyscale 2× upscale of the 960 px Commons render: automatic layout first, then single-column layout, then automatic layout on a shading-flattened image, stopping at the first pass that decides the page with a resolvable crop; the best-aligned pass is kept.

### Crops of partial pages (F8b4)

The crop is the union of the aligned and interpolated line boxes plus a margin (0.6 median line heights), with the margin stopped halfway to any untranscribed region outside the union. It therefore contains all the transcribed text and as little untranscribed text as a rectangle can. Untranscribed regions left inside the box (for example a Latin heading between two Hebrew blocks) are listed as `untranscribed_inside`, in normalised page coordinates, so evaluation can mask them. A crop is `unresolved`, with a reason, when the transcription is not located well enough (`transcription_not_located`: aligned and interpolated lines span under 70% of it) or when untranscribed text inside the box exceeds 15% of its text area (`untranscribed_text_inside_crop`). The tool computes a crop for every page; it is applied only when the deciding check (tool, agent or human) says `partial_page`, so an agent's or human's partial verdict uses the tool's crop.

A page record's `crop` holds `status`, `reason`, `method` (`ocr_alignment_union_box.v1`), `box_normalized` (`[x0, y0, x1, y1]` as fractions of the page), `untranscribed_inside` and `located_by` (the tool, its version, the render URL and SHA-256 it ran on, the OCR engine and the alignment scores). In the packaged snapshot a resolved crop also carries `box_px` (the box in the pinned page image, rounded outward) and `asset`: the cropped sub-image, pinned by SHA-256. The candidate for a partial page is that crop plus the page's unchanged human text; its metadata `crop` names the source page image (path, SHA-256, size), the box, the method and how it was located.

**Multi-region crops** (F8b5). When untranscribed blocks are interleaved with the transcription (Luzzatto's verse and Italian translation between passages of commentary, a Yiddish half of a bilingual instruction line), one rectangle cannot leave them out. The crop then has `regions_normalized`: two to eight boxes, in reading order, whose union is `box_normalized`. The pair image is the union box with every pixel outside the regions set to `mask_fill` (the page background: the upper-quartile value of each RGB channel under the box) and each region pasted from the page unchanged, so the transcribed pixels are the page's own and stay where they are on the page. The packaged record adds `regions_px` and `mask_fill`. When its single box takes in too much untranscribed text, the tool proposes regions (`ocr_alignment_region_mask.v1`): one per block of transcribed lines that no untranscribed region lies inside, each with the crop margin stopped halfway to the untranscribed text. Tool region crops are always `review_recommended`: none of the 46 the tool placed in the F8b5 run was right as it stood.

**Agent and human crops** (F8b5). An agent or human check of a `partial_page` page may carry its own `crop`: `status: resolved`, method `agent_visual_crop.v1` (or `human_visual_crop.v1`), a `basis` (`tool_crop_confirmed`, `tool_crop_corrected` or `placed`), a box or regions, and optional `untranscribed_inside`. It wins over the tool's crop, is recorded as `located_by.checked_by: agent` with the render it was placed on, and is no longer `review_recommended`. Like the coverage verdict, it is a geometry fact, not an attestation of the text. F8b5's agent checks (`agent_crop_review_960px`) cover all 188 pages `F8b4` left `review_recommended`, `crop_unresolved` or undecided.

Source health checks every cropped page: the crop asset exists with its SHA-256, the box is inside the page image, and the asset is exactly the page image cut at the box (same size, same pixels; for a multi-region crop, the regions' pixels the page's and the rest `mask_fill`). Acquisition runs the same check. A failure gives `crop_asset_missing`, `crop_asset_checksum_mismatch`, `crop_geometry_mismatch`, `crop_mask_fill_invalid` or `crop_pixels_mismatch`.

### Reference normalisation facts (F8b4)

Each item's metadata, and each F2 reference-pool entry, records `reference_normalization`: `footnote_marker_style` is `bracketed_index` when the page has footnotes (each printed mark is written `[n]`, see below) and `null` otherwise, with `footnote_count`. Evaluation can mask the marks from this fact; E2c scoring is unchanged (follow-up: `HeOCR/hocrgen#124`).

## Wikitext to plain text (`wikisource_plain_text.v2`)

`hocrgen.parsers.wikitext.convert_wikitext` is a closed-world converter: every template it knows has a rendering written from its he.wikisource source, and anything else raises `UnsupportedWikitextError` (`wikitext_unsupported_markup`), so an unknown construct fails loudly rather than being dropped or guessed (decision 11). It returns the text, `size_spans` (counts of small and large type) and `features` (counts of footnotes, editors' notes dropped, citations, added quotation marks, tables, columns, hidden arguments and repaired markup errors), which each item records as `text_size_spans` and the inventory as `text_features`. The steps:

1. **The Page view.** Drop the ProofreadPage header and footer (`<pagequality>`, running heads, page numbers, `<references/>`). An editor's own `<noinclude>` inside the body is shown on the Page view and kept (for example a chapter heading); `<includeonly>` is not shown and dropped. HTML comments and `<section>` / `<קטע>` tags are dropped. `<nowiki>` text is kept literally.
2. **Templates** expand from the closed table `TEMPLATE_RENDERERS`:
   - styling wrappers keep their text (`ק`, `קטן`, `ג`, `גדול`, `גדול-מודגש`, `גג`, `קק`, `גודל גופן`, `הוראה למתפללים`, `מרווחות`, `ה`, `צבע גופן`, `עם-טעמים`, `גמט`); blocks (`מרכז`, `עם-ניקוד`, `שמאל`, `מר`, `עמודות`, `טקסט מנוקד`, `סוף`) end a paragraph;
   - tooltips keep the visible word only (`קיצור`, `ב`, `מונחון`, `אח"כ`); links keep their label (`דף ויקיפדיה`, `וק`, `מח`);
   - editors' citations and quotations render as MediaWiki shows them: `ממ` / `מ"מ`, `ממ זהר`, `ממ משנה`, `מקור`, `מצ`, `במצ`, `שם`, `צ`, `ציטוטון`, `צפ`, `צא`, `צמל`, `פסוק`, `הפניה לפסוקים` (with Module:גרשיים and the `מ"מ/ספר` book names, `src/hocrgen/data/wikisource/book_names.json`) and `הפניה-גמ1`. The Lua parts of these templates show nothing on the page;
   - Bible markup: `מ:פסוק` (the verse and chapter numbers as shown), `מ:פסק`, `מ:לגרמיה`, `מ:ירושלם`, `מ:ירושלמה`, `מ:קמץ`, `HIRIK WITHOUT LETTER`, `מ:טעמי המקרא`;
   - a bidi mark (`כ`, F8b5): it writes RLM or LRM, which step 8 removes, so it shows nothing;
   - title pages and running heads in the body (`דף שער` / `כו`, `כותרת רצה` / `rh`), Luzzatto's lemmas (`שדל:דה`), poems (`רן`), lists (`מיספור עברי`, `מ`), spacing (`רווח קשיח`, `ססס`, `סס`, `פפ`, `ש-רווח`, `ררר`) and anchors (`עוגן בשורה`, `סעיף`).
   - A positional parameter a template does not use is hidden, as MediaWiki hides it (counted as `hidden_arguments`); an unknown named parameter is rejected.
3. **Footnotes** (`{{הערה}}`, `<ref>`, `{{הערות שוליים}}`, `<references/>`): the mark becomes `[n]` in the body, numbered in order of first use, a named note reusing its number; each note becomes a line `[n] text` where the list stands, else after the body. That is the print's layout (mark in the body, note at the foot of the page). The printed mark itself (`*)`, `1)`, `(א`) is not typed by editors, so the MediaWiki number stands in for it. A `<ref follow=...>` continuation from the previous page is an unnumbered line before the notes. A note signed by a Wikisource editor ("ויקיעורך", "ויקי עורך") and `{{ביאור}}` explanations are not printed: they and their marks are dropped (`editor_notes_dropped`). Unsigned editors' notes cannot be told from printed footnotes and stay.
4. **Tables** (`{| ... |}`) and block HTML (`div`, `center`, `p`, table cells, list items, headings, `<poem>`) end paragraphs, so each cell or block is its own line, in source (logical) order.
5. Links keep their label; file and category links are dropped. Bold and italic quotes are dropped (four quotes keep one apostrophe, as in MediaWiki).
6. Paragraphs follow MediaWiki rendering: a single newline is a space, a blank line separates paragraphs, and headings, rules and blocks stand alone.
7. HTML tags are dropped (`<br>` becomes a newline), and entities are decoded.
8. Bidirectional control characters are removed and Unicode space separators become plain spaces. Unicode NFC; spaces are collapsed per line, with at most one blank line between paragraphs.

**Editors' markup errors** that MediaWiki shows literally, and the print does not, are rendered as printed and counted as `malformed_markup`: broken link brackets, a stray third brace, an unclosed template (`{{name|a}` is read as the call meant; any other unclosed opener is dropped), heading `=` signs after a bidi mark, and two mistyped template names (`קטם` for `קטן`, `:פסוק` for `מ:פסוק`) plus one broken citation (`שם מד`), each on one pinned page.

**Checked against MediaWiki.** `hocrgen.tools.wikisource_render_check` asks MediaWiki to render each pinned page body (`action=parse`) and compares its visible lines with the converter's, dropping display-only parts (the status banner, tooltips, footnote backlinks, TemplateStyles CSS) and tolerating the deliberate differences above. On 313 rendered pages of the F8b3 inventory, 299 match token for token and the other 14 differ only by those deliberate repairs and dropped editors' notes. The committed test fixtures under `tests/fixtures/wikisource_render/` cover every new construct.

`wikisource_plain_text.v2` keeps v1's text for v1's three fixture pages. It changes v1's text where v1 was wrong against MediaWiki's rendering: block HTML now ends a paragraph, and an editor's in-body `<noinclude>` (for example Bostenay's chapter headings) is kept.

**Labelled-section transclusion** (F8b4): `{{#קטע:title|section}}` (also `#section:` and `#lst:`) is replaced by that section of the transcluded page, as MediaWiki's Labelled Section Transclusion takes it: the text between `<section begin=name/>` (`<קטע התחלה=name/>`) and the matching end tag, the name matched literally (spaces included), several sections of one name joined, the target's `<noinclude>` parts left out and its `<includeonly>` parts kept. Nested calls are followed. Every transcluded page is pinned by revision id and SHA-256 (`transclusions` on the page record, files under `transcluded/`); a page not pinned, or a section not on it, is rejected. The 13 pages of the *Qav ve-Naqi* and Ibn Yaḥya Indexes that use it now convert. Their Bible text (*Miqra al pi ha-Masora*) adds `מ:דחי` (the first accent reading), `מ:אות-ג` (a large letter), `ר0`, `ר1`, `ר2` (verse-half breaks), `כו"ק` / `קו"כ` (ketiv and qere, both shown) and `מ:מקף אפור`; `מ:טעמי המקרא-סוף` closes the verse block and ends the paragraph. All 13 match MediaWiki's rendering line for line; one is a committed render fixture.

Known transcription conventions that differ from the print, kept as the editors wrote them:
- normalised punctuation (`.` for the printed mid-dot, `"` for printed `«»`);
- full niqqud where the editor typed it;
- column order on two-column pages;
- editors' citations normalised into templates (for example `(חולין קלא, א)` for a printed `(חולין קל"א)`), and quotation marks some citation templates add.

## Snapshot layout

`src/hocrgen/data/wikisource/snapshot/`:

- `snapshot.yaml`: the capture date, User-Agent and text licence evidence.
- `indexes.json`: Index records with Commons evidence (source field, institution, provenance text, licence templates, categories, SHA-1, file-page revision) and the recorded work and scan evidence.
- `pages.jsonl`: page records with:
  - the revision id, timestamp and MediaWiki SHA-1;
  - the quality history and edits after the quality was set;
  - wikitext and text checksums;
  - the image's own checksum and its render source (Commons file SHA-1, page and render URL).
- `wikitext/`: raw pinned wikitext. `transcluded/`: pinned wikitext of transcluded pages (F8b4). `text/`: derived plain text, whose SHA-256 excludes the file's final newline. `assets/`: page renders downscaled to 600 px wide, and the crops of partial pages (`*__crop.png`, F8b4).

Discovery and source health (`discover/source_health.json`) both check the packaged `text/` file that `page_text_ref` points to. The file must exist and must equal the derived text plus one final newline. A failure gives `page_text_file_missing` or `page_text_file_mismatch`. Source health reports admitted Indexes, Index exclusion counts by reason, page exclusion counts, missing or altered assets, and wikitext or text drift. Acquisition fails on an asset checksum mismatch.

## Operator-only F2 conversion

`hocrgen.fetchers.wikisource.write_wikisource_reference_pool(source, bundle, out_dir)` writes a `benchmark_transcription_reference.v1` file for each adjudication-eligible quality-4 page, plus `reference_pool.json` (`wikisource_reference_pool.v1`):

- `review.status` is `reviewed`, with the proofreader and validator as `wikisource:<user>` reviewers;
- each pool entry records the page's `reference_normalization` and the image it pairs with: the page image, or for a partial page the crop's box on it (F8b4);
- `adjudicator` is null, and each pool entry is `needs_adjudication`;
- lines are rendered paragraphs.

It never touches `benchmark_v1`. Adjudication, and any benchmark membership, are later human steps.

```bash
PYTHONPATH=src python -c 'from pathlib import Path; from hocrgen.config.loader import load_and_validate_bundle; from hocrgen.fetchers.wikisource import write_wikisource_reference_pool; b = load_and_validate_bundle(); s = next(x for x in b.source_registry.sources if x.id == "wikisource_he_proofread"); print(write_wikisource_reference_pool(s, b, Path("wikisource_reference_pool")))'
```

On the fixture, one page converts (Seliḥot p. 34). Bostenay p. 47 is skipped because its validator added a missing space 14 seconds after validating; Hyman p. 41 and the two cropped pages (Buber's *Tanhuma* p. 233, *Sippurei Ma'asiyot* p. 11, F8b4) are skipped as quality 3.

## Operator-only full inventory (F8b2, F8b3, F8b4, F8b5)

`hocrgen.tools.wikisource_inventory` runs every `מפתח:` Index on he.wikisource.org through the gates above. It is an operator tool: it calls the Wikisource, Commons, Wikipedia and Wikidata APIs, with a contact User-Agent, `maxlag` and a 0.5 s delay between uncached requests. CI never runs it, and it never edits any wiki.

For each Index it records:

- **creators**, from the Index fields (`מחבר`, `מתרגם`, `עורך`, `מאייר`, plus role markers such as `מתרגם:` in the title and notes) and the Commons `Author` / `Translator` / `Editor` / `Illustrator` fields;
- **death years**, from Wikidata `P570` or the Wikisource author page; for creators the wikis name only as plain text, from cited facts in [`wikisource_index_evidence.json`](./wikisource_index_evidence.json) (`--index-evidence`). A death year is never guessed: a creator who cannot be identified, or has no reliable year, keeps `death_year: null`;
- the **publication year** (the latest of the Commons date and the Index `שנה`; a Hebrew-letter year is read as its latest Gregorian year) and where it was read;
- the **language** and where it was read;
- the Commons licence templates, the scan source and the Google-digitization record (provenance).

Since F8b6 the evidence file can also fill these gaps, each with its source and recorder, for the unchanged gate to read:

- a **creator the wikis do not name** (`creators[].add: true`), with its cited death year; it is added only when no parsed creator has its name;
- **corrections** of creators parsed from free text (`creator_corrections`): `not_a_creator` drops a date or a fragment of a sentence, and `anonymous` marks an unsigned work (a newspaper's editorial board). A creator with a death year is never corrected;
- a **publication year** the wikis do not record (`published_year`), never replacing one they do;
- **additional grounds** (`additional_grounds`), shown on the Index record: facts that support the work's status beside the gate's basis, for example that every transcribed page is a traditional text centuries old.

The evidence file records each fact with its source URL (Wikidata, with the National Library of Israel authority id), `recorded_by` (`agent` or `human`), the recorder and the date. A recorded fact only fills a gap the tool left; it never replaces evidence the tool found. Facts looked for and not found are listed under `not_recorded` with the reason. The render checks recorded in the packaged snapshot, and the page render checks in [`wikisource_page_checks.json`](./wikisource_page_checks.json) (`--page-checks`), are applied. Pages of admitted Indexes are pinned into an operator snapshot root and run through `page_exclusion_reasons` and `page_attestation`.

```bash
# 1. pin every page (and its transcluded pages) into the operator snapshot
PYTHONPATH=src python -m hocrgen.tools.wikisource_inventory --work-dir <operator folder outside the repo> --checked-at 2026-11-06 \
  --index-evidence docs/wikisource_index_evidence.json --page-checks docs/wikisource_page_checks.json
# 2. tool coverage checks and crops (F8b4; needs a local tesseract with the heb model; --capture fetches the renders)
PYTHONPATH=src python -m hocrgen.tools.wikisource_coverage --inventory <work-dir>/wikisource_inventory.json --snapshot <work-dir>/snapshot \
  --renders <operator folder> --ocr-cache <operator folder> --capture --checked-at 2026-11-06 \
  --out <operator folder>/tool_checks.json --compact-out docs/wikisource_page_tool_checks.json
# 3. the committed summary, with agent, human and tool checks
PYTHONPATH=src python -m hocrgen.tools.wikisource_inventory --work-dir <work-dir> --checked-at 2026-11-06 \
  --index-evidence docs/wikisource_index_evidence.json --page-checks docs/wikisource_page_checks.json \
  --page-checks docs/wikisource_page_tool_checks.json \
  --summary-json docs/wikisource_index_inventory.json --summary-md docs/wikisource_index_inventory.md
PYTHONPATH=src python -m hocrgen.tools.wikisource_render_check --inventory <work-dir>/wikisource_inventory.json \
  --snapshot <work-dir>/snapshot --renders <operator folder> --capture --report <operator folder>/render_report.json
```

The raw API cache, the pinned page wikitext and text, the MediaWiki renderings, the Commons page renders, the OCR output and the full `wikisource_inventory.json` and tool checks stay in the operator folder. The committed tool checks hold geometry and scores only, no OCR or page text. Only the per-Index summary is committed: [`wikisource_index_inventory.md`](./wikisource_index_inventory.md) and its JSON, with ids, rights evidence, gate reasons and page counts, but no page text or images. A test replays every committed record through `index_exclusion_reasons` and re-renders the markdown.
