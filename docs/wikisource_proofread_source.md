# Hebrew Wikisource proofread-page source (F8b)

Source id `wikisource_he_proofread`, fetcher `wikisource_proofread`. Source proposal: `HeOCR/hocrgen#103`. Plan: [`planning/tasks/f8-real-source-map.md`](../planning/tasks/f8-real-source-map.md).

Each item is one ProofreadPage `עמוד:` (Page) page on he.wikisource.org at quality 3 or 4, paired with the same page of its Index's Commons PDF/DjVu file. The page text is human-made: typed and proofread by named Wikisource editors against that scan.

## Status and rights

- `status: review_only`, `default_public_release: false`, `requires_manual_review: true`. Included only in `profile_review_v1`; not in `profile_open_v1`.
- Page text: `CC-BY-SA-4.0` / `sharealike` (the site licence, maintainer decision 1, 2026-11-06). Share-alike applies to any reference file HeOCR releases from it. Attribution is "Hebrew Wikisource contributors" plus the pinned page permalink.
- Scan: rights per Commons file. Each item carries the Commons file title, its SHA-1, the file-page revision id and the licence templates.
- Privacy source default `clear`. No privacy-review gate: this is public-domain historical print. Manual review covers the agent-recorded rights evidence.

## Admission per Index

An Index is admitted only when its record carries evidence of **both** of the following. The rules live in `hocrgen.fetchers.wikisource.index_exclusion_reasons`.

1. **The work is public domain in Israel** (`work_rights.basis`):
   - `author_died_by_1955`: every recorded creator (author, editor, translator) has a death year of 1955 or earlier, with an evidence URL;
   - `state_work_by_1975`: a state work created in 1975 or earlier, with the state body named;
   - `anonymous_published_by_1955`: an anonymous or pseudonymous work published in 1955 or earlier.
2. **The scan's rights are clear** (`scan_rights.basis`):
   - `faithful_reproduction_of_pd_work`, with the scan's source recorded on Commons; or
   - `explicit_open_licence`, with an open licence (`CC0-1.0`, `PDM-1.0`, `CC-BY-4.0`, `CC-BY-SA-4.0`).

A Commons licence template is never enough on its own. Further rules:

| Reason code | Rule |
| --- | --- |
| `excluded_birnbaum_work` | The Birnbaum Siddur (1949) and Haggadah (1953) are always excluded (Birnbaum died in 1988). |
| `pd_us_only_licence` | Every licence template on the file is a `PD-US-*` template. |
| `no_licence_template` | The file page has no licence template. |
| `commons_file_unpinned` | No Commons SHA-1 or file-page revision id. |
| `work_rights_basis_unsupported`, `creators_missing`, `creator_death_year_missing`, `creator_died_after_1955`, `state_work_evidence_missing`, `state_work_after_1975`, `named_creator_on_anonymous_basis`, `publication_year_missing`, `anonymous_work_after_1955`, `work_rights_evidence_missing` | Work evidence missing or outside Israel's terms. |
| `scan_rights_basis_unsupported`, `scan_rights_evidence_missing`, `scan_licence_not_open`, `scan_provenance_unrecorded` | Scan evidence missing or not open. |
| `google_digitized_scan_pending` | The scan is Google-digitized: `scan_rights.digitized_by_google` is true, or the Commons record mentions "Digitized by Google" or Google Books. This is a team-lead hold (2026-11-06) pending a maintainer rights decision. |
| `google_digitization_unchecked` | No one has recorded whether the scan is Google-digitized. The stamp is on the page images and often missing from Commons metadata, so the capture must look at the renders and record the answer. |

Scans that came from HebrewBooks are admitted on the same check (maintainer decision 3, accepted 2026-11-06). `scan_source_origin` (`hebrewbooks`, `open_siddur_project`, `national_library_of_israel`, `internet_archive`, `unrecorded`) is provenance only and gates nothing.

## Pages, quality and attestation

- Only quality 3 (proofread) and 4 (validated) are admitted. Quality 0–2 is skipped (`quality_not_proofread`).
- The page history is read at capture time. Each quality change is recorded with its revision id, editor, user id and user groups. The editor who set quality 3 is the **proofreader**; for quality 4, the editor who set 4 is the **validator**.
- A page is rejected when:
  - an editor who set quality is not a named human (an empty name, an IP edit, the `bot` group, or a name ending in "bot");
  - the `<pagequality user=...>` attribute disagrees with the editor who made that revision;
  - the validator is also the proofreader;
  - the transcription covers only part of the page body (`partial_page_transcription`), or its coverage was never recorded (`transcription_coverage_unrecorded`);
  - the pinned wikitext does not carry the recorded quality.
- Quality 4 is human-attested and **adjudication-eligible**, but only while the pinned plain text equals the text at the validating revision. Any later edit that changes the plain text sets `adjudication_eligible: false` with `text_changed_after_validation`. This holds even when the validator made the edit.
- Quality 3 is single-reviewer human proofreading (`quality_3_single_reviewer`): never adjudication-eligible.
- hocrgen never edits or attests Wikisource pages.

## Wikitext to plain text (`wikisource_plain_text.v1`)

`hocrgen.parsers.wikitext.wikitext_to_plain_text` is a closed-world converter. Markup outside its set raises `UnsupportedWikitextError`, and the page is rejected (`wikitext_unsupported_markup`). Nothing is silently dropped or guessed. The steps run in this order:

1. Drop `<noinclude>` blocks: the `<pagequality>` tag, running header and footer, and `<references/>`. Running heads and page numbers are therefore not part of the page text.
2. Drop HTML comments and `<pagequality>`, `<section>` and `<קטע>` tags.
3. Reject `<ref>` footnotes, tables, math, galleries, `includeonly` and parser functions.
4. Expand templates from a closed table, checked with `action=expandtemplates`:
   - `ק`, `ג`, `מרכז` and `עם-ניקוד` keep their text; `מרכז` and `עם-ניקוד` are blocks.
   - `קיצור` keeps the printed abbreviation, not the editor's tooltip expansion.
   - `ש` is a line break, and `!` is a literal `|`.
   - `סוף` and `טקסט מנוקד` are dropped.
   - Any other template is rejected.
5. Links keep their label (`[[ברכות לט ב|ברכות לט:]]` becomes `ברכות לט:`). File and category links are dropped. Bold and italic quotes are dropped.
6. Paragraphs follow MediaWiki rendering: a single newline is a space, a blank line separates paragraphs, and headings and rules stand alone.
7. HTML tags are dropped (`<br>` becomes a newline), and entities are decoded (`&nbsp;` becomes a space).
8. Bidirectional control characters (U+200E, U+200F, U+202A–U+202E, U+2066–U+2069, U+FEFF) are removed. Wikitext is already in logical order.
9. Unicode NFC; spaces are collapsed per line, with at most one blank line between paragraphs.

Lines therefore follow rendered paragraphs, not printed lines, and there is no line geometry. The three fixture pages were checked against MediaWiki's own rendering (`action=parse`) at the pinned revisions. They match except for display-only parts: the ProofreadPage status banner, the automatic table of contents, and the hidden `קיצור` tooltips.

**Known limitation: partial-page detection is not automatic.** Some Indexes transcribe only part of each page. For example, the SD Luzzatto Bereshit pages carry the commentary but not the verse text above it. Nothing in the wikitext or the ProofreadPage metadata says so reliably. Each page record therefore carries `transcription_coverage`, set by the operator at capture time after comparing the page render with the text. Only `full_page` is admitted. Running heads, page numbers and catchwords count as outside the page body. Partial-page transcriptions are not wanted as references (team lead, 2026-11-06).

Known transcription conventions that differ from the print, kept as the editors wrote them:
- normalised punctuation (`.` for the printed mid-dot, `"` for printed `«»`);
- full niqqud where the editor typed it;
- column order on two-column pages.

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

Source health (`discover/source_health.json`) reports admitted Indexes, Index exclusion counts by reason, page exclusion counts, missing or altered assets, and wikitext or text drift. Acquisition fails on an asset checksum mismatch.

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
