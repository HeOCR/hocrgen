# Hebrew Wikisource proofread-page source (F8b, F8b3)

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
  - the `<pagequality user=...>` attribute disagrees with the editor who made that revision;
  - the validator is also the proofreader, by username or by user id;
  - its transcription coverage was never recorded (`transcription_coverage_unrecorded`), or is not `full_page` / `partial_page` (`transcription_coverage_unknown`);
  - the pinned wikitext does not carry the recorded quality, or uses markup the converter does not support (`wikitext_unsupported_markup`).
- **Partial pages are kept** (decision 12). A `partial_page` transcription (for example commentary without the verse above it) is not rejected: the item carries `needs_crop: true`, and F8b4 crops the image to the transcribed region. Until then the F2 reference conversion skips it (`needs_crop`).
- Quality 4 is human-attested and **adjudication-eligible**, but only while the pinned plain text equals the text at the validating revision. Any later edit that changes the plain text sets `adjudication_eligible: false` with `text_changed_after_validation`. This holds even when the validator made the edit.
- Quality 3 is single-reviewer human proofreading (`quality_3_single_reviewer`): never adjudication-eligible.
- hocrgen never edits or attests Wikisource pages.

## Transcription coverage checks

Coverage is a scope fact, not an attestation: whether the text covers the whole printed page body. Running heads, page numbers, catchwords and signature marks are outside the body; footnotes and marginal notes are inside it. Each check records:

- `transcription_coverage` (`full_page` or `partial_page`) and, for a partial page, `missing`: what is not transcribed, in words (no page text);
- `checked_by` (`agent` or `human`), the `checker`, `checked_at` and the `method`;
- the page revision and the Commons file SHA-1 it was made against. A check made on another revision or file is stale and not applied.

A human check overrides an agent check of the same page. Agent checks never change a quality level or a proofreader's attestation. The fixture pages' checks are in `pages.jsonl`; the inventory's are in [`wikisource_page_checks.json`](./wikisource_page_checks.json).

## Wikitext to plain text (`wikisource_plain_text.v2`)

`hocrgen.parsers.wikitext.convert_wikitext` is a closed-world converter: every template it knows has a rendering written from its he.wikisource source, and anything else raises `UnsupportedWikitextError` (`wikitext_unsupported_markup`), so an unknown construct fails loudly rather than being dropped or guessed (decision 11). It returns the text, `size_spans` (counts of small and large type) and `features` (counts of footnotes, editors' notes dropped, citations, added quotation marks, tables, columns, hidden arguments and repaired markup errors), which each item records as `text_size_spans` and the inventory as `text_features`. The steps:

1. **The Page view.** Drop the ProofreadPage header and footer (`<pagequality>`, running heads, page numbers, `<references/>`). An editor's own `<noinclude>` inside the body is shown on the Page view and kept (for example a chapter heading); `<includeonly>` is not shown and dropped. HTML comments and `<section>` / `<קטע>` tags are dropped. `<nowiki>` text is kept literally.
2. **Templates** expand from the closed table `TEMPLATE_RENDERERS`:
   - styling wrappers keep their text (`ק`, `קטן`, `ג`, `גדול`, `גדול-מודגש`, `גג`, `קק`, `גודל גופן`, `הוראה למתפללים`, `מרווחות`, `ה`, `צבע גופן`, `עם-טעמים`, `גמט`); blocks (`מרכז`, `עם-ניקוד`, `שמאל`, `מר`, `עמודות`, `טקסט מנוקד`, `סוף`) end a paragraph;
   - tooltips keep the visible word only (`קיצור`, `ב`, `מונחון`, `אח"כ`); links keep their label (`דף ויקיפדיה`, `וק`, `מח`);
   - editors' citations and quotations render as MediaWiki shows them: `ממ` / `מ"מ`, `ממ זהר`, `ממ משנה`, `מקור`, `מצ`, `במצ`, `שם`, `צ`, `ציטוטון`, `צפ`, `צא`, `צמל`, `פסוק`, `הפניה לפסוקים` (with Module:גרשיים and the `מ"מ/ספר` book names, `src/hocrgen/data/wikisource/book_names.json`) and `הפניה-גמ1`. The Lua parts of these templates show nothing on the page;
   - Bible markup: `מ:פסוק` (the verse and chapter numbers as shown), `מ:פסק`, `מ:לגרמיה`, `מ:ירושלם`, `מ:ירושלמה`, `מ:קמץ`, `HIRIK WITHOUT LETTER`, `מ:טעמי המקרא`;
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

**Not supported yet:** `{{#קטע:...}}`, a labelled-section transclusion of another page's text (13 pages, in the *Qav ve-Naqi* and Ibn Yaḥya Indexes). Rendering it needs the transcluded pages pinned too.

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
- `wikitext/`: raw pinned wikitext. `text/`: derived plain text, whose SHA-256 excludes the file's final newline. `assets/`: page renders downscaled to 600 px wide.

Discovery and source health (`discover/source_health.json`) both check the packaged `text/` file that `page_text_ref` points to. The file must exist and must equal the derived text plus one final newline. A failure gives `page_text_file_missing` or `page_text_file_mismatch`. Source health reports admitted Indexes, Index exclusion counts by reason, page exclusion counts, missing or altered assets, and wikitext or text drift. Acquisition fails on an asset checksum mismatch.

## Operator-only F2 conversion

`hocrgen.fetchers.wikisource.write_wikisource_reference_pool(source, bundle, out_dir)` writes a `benchmark_transcription_reference.v1` file for each adjudication-eligible quality-4 page, plus `reference_pool.json` (`wikisource_reference_pool.v1`):

- `review.status` is `reviewed`, with the proofreader and validator as `wikisource:<user>` reviewers;
- `adjudicator` is null, and each pool entry is `needs_adjudication`;
- lines are rendered paragraphs.

It never touches `benchmark_v1`. Adjudication, and any benchmark membership, are later human steps.

```bash
PYTHONPATH=src python -c 'from pathlib import Path; from hocrgen.config.loader import load_and_validate_bundle; from hocrgen.fetchers.wikisource import write_wikisource_reference_pool; b = load_and_validate_bundle(); s = next(x for x in b.source_registry.sources if x.id == "wikisource_he_proofread"); print(write_wikisource_reference_pool(s, b, Path("wikisource_reference_pool")))'
```

On the fixture, one page converts (Seliḥot p. 34). Bostenay p. 47 is skipped because its validator added a missing space 14 seconds after validating; Hyman p. 41 is skipped as quality 3.

## Operator-only full inventory (F8b2, F8b3)

`hocrgen.tools.wikisource_inventory` runs every `מפתח:` Index on he.wikisource.org through the gates above. It is an operator tool: it calls the Wikisource, Commons, Wikipedia and Wikidata APIs, with a contact User-Agent, `maxlag` and a 0.5 s delay between uncached requests. CI never runs it, and it never edits any wiki.

For each Index it records:

- **creators**, from the Index fields (`מחבר`, `מתרגם`, `עורך`, `מאייר`, plus role markers such as `מתרגם:` in the title and notes) and the Commons `Author` / `Translator` / `Editor` / `Illustrator` fields;
- **death years**, from Wikidata `P570` or the Wikisource author page; for creators the wikis name only as plain text, from cited facts in [`wikisource_index_evidence.json`](./wikisource_index_evidence.json) (`--index-evidence`). A death year is never guessed: a creator who cannot be identified, or has no reliable year, keeps `death_year: null`;
- the **publication year** (the latest of the Commons date and the Index `שנה`; a Hebrew-letter year is read as its latest Gregorian year) and where it was read;
- the **language** and where it was read;
- the Commons licence templates, the scan source and the Google-digitization record (provenance).

The evidence file records each fact with its source URL (Wikidata, with the National Library of Israel authority id), `recorded_by` (`agent` or `human`), the recorder and the date. A recorded fact only fills a gap the tool left; it never replaces evidence the tool found. Facts looked for and not found are listed under `not_recorded` with the reason. The render checks recorded in the packaged snapshot, and the page render checks in [`wikisource_page_checks.json`](./wikisource_page_checks.json) (`--page-checks`), are applied. Pages of admitted Indexes are pinned into an operator snapshot root and run through `page_exclusion_reasons` and `page_attestation`.

```bash
PYTHONPATH=src python -m hocrgen.tools.wikisource_inventory --work-dir <operator folder outside the repo> --checked-at 2026-11-06 \
  --index-evidence docs/wikisource_index_evidence.json --page-checks docs/wikisource_page_checks.json \
  --summary-json docs/wikisource_index_inventory.json --summary-md docs/wikisource_index_inventory.md
PYTHONPATH=src python -m hocrgen.tools.wikisource_render_check --inventory <work-dir>/wikisource_inventory.json \
  --snapshot <work-dir>/snapshot --renders <operator folder> --capture --report <operator folder>/render_report.json
```

The raw API cache, the pinned page wikitext and text, the MediaWiki renderings and the full `wikisource_inventory.json` stay in the operator folder. Only the per-Index summary is committed: [`wikisource_index_inventory.md`](./wikisource_index_inventory.md) and its JSON, with ids, rights evidence, gate reasons and page counts, but no page text or images. A test replays every committed record through `index_exclusion_reasons` and re-renders the markdown.
