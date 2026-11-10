# F8f R7 hand-off: real line set `bynli_lines_v2`

On 2026-11-11 the f8f3 and f8f_ia real-line data was handed to heocr-synth-gen for R7. heocr-lead set the timing and the recipe; the maintainer had delegated R7 timing to the lead. Synth-gen built the final cut, `bynli_lines_v2`, on hocrgen 1921bbe (it includes #164 and #165; main has had only docs commits since).

The full record is [`f8f_r7_handoff.json`](f8f_r7_handoff.json). It has the exact command, the builder summary, per-book counts, the excluded and dropped lists and the release notices.

Every pair is silver: `human_typed_edition_text_aligned`, `not_adjudicated`, `reference_eligible: false`. The labels are OCR-localised Project Ben-Yehuda edition text, never OCR output.

## Recipe

- **Roots:**
  - `s16c-glyph-scale/intermediates/f8f2`: R6's books, including the Silman and Brainin dev books;
  - `real-source-mapping/intermediates/f8f/f8f3`;
  - `real-source-mapping/intermediates/f8f/f8f_ia`.
- **Book names:** `--editions f8f2_editions.json`.
- **Placer:** `--prefer-placer stock`. Nir David also has an R6 alignment, but the stock one is used.
- **Niqqud:** stripped from labels, and fully pointed prints are dropped, as in v1. `--keep-pointed` is off because R6's unicharset lacks most points. The pointed prints are named only so the builder can drop them.
- **`--unpointed`:** two records are unpointed prints whose edition text carries some niqqud, so their labels are stripped:
  - `mimitsrayimhusef00fran`;
  - Katzenelson, *Shirim* 1938 (`990013538860205171`).
- **Cap:** `--max-lines-per-book 6100`. That is 6,000 nudged up so that every R6 book keeps all its lines: Berashadsky has 6,076 and Citron 6,052. The cap trimmed four records:
  - Anna Karenina: 1,845 lines;
  - `kolsifreperetsbe01`: 10,088;
  - `kolsifreperetsbe03`: 13,785;
  - `sifrehazikhronot00mont`: 2,104.

## Set

| | |
|---|---|
| Lines | 102,478: 95,365 train and 7,113 dev, all unpointed |
| Records with lines | 33: 23 IA and 10 NLI |
| `manifest.jsonl` sha256 | `53dd7f1a10929ad4a60020ad7f42be62f27ee905cb7e6cfb0e319c5b2f5db7ca` (verified) |
| Images | written for every row; 0 have a null `image_sha256` |
| IA rows | all 75,545 have `scan_source`, `source_class` (`ia_library_scan_no_licence_field`) and `rights_justification_id`; 0 lack an id |
| R8 stragglers | none present |

**Dev (held out whole):**

| Book | Lines |
|---|---:|
| Brainin, 1928 | 4,046 |
| Silman, 1929 | 3,046 |
| Bodek, 1870 | 21 |

Three dev records give no lines:

- Bodek 1865: it sits in `out_alt/`, which the builder doesn't read (hocrgen#169).
- Nir David: it's a pointed print, so it is dropped.

**Dropped as pointed prints** (10,566 lines):

- f8f3: Hiawatha (NLI), Pines and Meyuhas;
- IA: `eretsyiraelsefer00goor` and `nirdavid01coheuoft`;
- R6 (as before): Katzenelson *Mahamadim* and Mandelkern *Shirei*.

So f8f3's only new train data in R7 is Anna Karenina (6,100 lines after the cap) and Frishman (72 lines).

**Weight:** Smolenskin's *Kol sifre* is three capped IA records, 17,689 lines in all. That is 18.5% of train.

## Excluded: 4 works without a rights justification

| IA item | PBY | Reason |
|---|---|---|
| hayehudimbelodzo00frenuoft | 58907 | no death year for Jacob Frenkel |
| p1toldothaemunot03menz | 58581 | no death year for Jacob Frenkel |
| hakhmatshimonben00kohn | 25753 | the Ben Sira Wikidata QID is the book, not the person |
| seferhaatsamim00ibne | 17928 | no publication place |

The back-fill on d614c6e justified 268 R7 works. Counting the R8 stragglers, the total is 277. The approved R8 follow-up is a PBY-QID correction file plus century-precision death years.

## Moved to R8

- **f8f3:**
  - Bachrach 1884 (confirmed, not aligned);
  - the 221 shortlisted groups not yet through the NLI gate;
  - the R6 second pass.
- **f8f_ia:** 3 books, 712 pages, aligned on bf3c1ff. They are kept in `f8f_ia/r8_stragglers/out/`, outside every build root's `out*/` dirs:
  - `bioretletoldotha01gott`;
  - `kevarpirezikhron00haco`;
  - `sifruthahisoriya11kaha`.
- **f8f_g:** all of it.
- **Alternate editions in `out_alt/`:** hocrgen#169.

11 IA books were skipped because neither reading direction cleared the 2-of-6 probe. The JSON lists them.

## Release notices

- **f8f3 and f8f2 scans:** from the collection of the National Library of Israel (מאוסף הספרייה הלאומית), each under the NLI "public domain – free use" terms. Each book's provenance has its NLI record id, manifest URL and attribution.
- **f8f_ia scans:** Internet Archive library scans of public-domain books, with no licence field. Each item's original IA conditions still apply.
  - The gate is `decide_ia_rights` (`planning/decisions/2026-11-09-internet-archive-library-scans.md`).
  - Each work also has its own `rights_justification` (`planning/decisions/2026-11-10-legal-strategy.md`).
- **Text:** the Project Ben-Yehuda public-domain dump, release 2026-03. Credit: "Project Ben-Yehuda volunteers", https://benyehuda.org.
