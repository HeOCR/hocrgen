# F8f R7 hand-off: Ben-Yehuda × NLI and IA real line set

Handed to heocr-synth-gen on 2026-11-11. heocr-lead set the timing (00:45): f8f3's aligned books plus f8f_ia's aligned books go now, and the rest goes to R8. The data, with the full per-book counts, the build command and the excluded and dropped lists, is in [`f8f_r7_handoff.json`](f8f_r7_handoff.json).

Every pair is silver: `human_typed_edition_text_aligned`, `not_adjudicated`, `reference_eligible: false`. It is OCR-localised Project Ben-Yehuda edition text, never OCR output.

## Set

The dry-run line build was run on hocrgen bf3c1ff with `--no-images`:

- 31 records give lines: 6 NLI and 25 IA.
- **114,813 lines:** 113,969 train and 844 dev.
- **Strata:**
  - train: 109,539 unpointed and 4,430 pointed;
  - dev: 21 unpointed and 823 pointed.
- **IA rows:** all 102,951 have `scan_source`, `source_class` (`ia_library_scan_no_licence_field`) and `rights_justification_id`. 0 are missing an id, and 0 lines were dropped as `ia_rights_justification_missing`.
- **Aligned pages behind the lines:**
  - f8f3: 7 books, 733 pages (600 high);
  - f8f_ia: 26 books, 4,628 pages (4,586 high).
- **IA books by era:**
  - pre-1900: 9 books;
  - 1900–1918: 11 books;
  - 1919–1948: 6 books.

## Dev (held out whole)

| Record | Book | Lines here |
|---|---|---:|
| 990010684570205171 | Bodek, Pe'er mi-Kedoshim, 1870 | 21 |
| 990010106660205171 | Bodek, 1865 | 0 (in `out_alt/`, which the builder does not read) |
| nirdavid01coheuoft | Shalom ha-Kohen, Nir David, 1834 (fully pointed) | 823 |
| 990020250940205171 | Silman, 1929 (R6 dev) | not in these roots |
| 990018546440205171 | Brainin, 1928 (R6 dev) | not in these roots |

There is no other dev data. Unpointed dev is thin in R7 (21 lines), because the Bodek pages are mostly low quality under stock Tesseract. Silman and Brainin stay held out from the R6 set.

## Pointed and unpointed flags

- **Pointed prints, kept with niqqud labels (`--keep-pointed`):**
  - Hiawatha, NLI 1922 (990013297040205171), 1,074 lines;
  - Pines, Sefer ha-Koah 1894 (990020403130205171, a partly pointed print), 1,965 lines;
  - Meyuhas, Bat Hayil 1901 (990018346960205171), 785 lines;
  - eretsyiraelsefer00goor (1903), 606 lines;
  - nirdavid01coheuoft (dev), 823 lines.
- **Meyuhas:** its PBY niqqud (72.7% of aligned spans) is weaker than the print's. The builder's `pointed_line_underpointed` gate drops lines whose labels lack niqqud, but the surviving labels may still under-point the print.
- **mimitsrayimhusef00fran (1862):** an unpointed print whose edition text carries some niqqud (0.15 per letter). It is passed as `--unpointed`, so labels are stripped.
- **Unchecked prints:** kolsifreperetsbe03 and kolsifreperetsbe05, igrothaasirmeiha00drey and masaleeretsyirae00lewi have no visual print check. Their edition niqqud is ≤ 0.007 per letter, under the 0.1 check.
- **Katzenelson, Shirim 1938 (990013538860205171):** this record is in R6's f8f2 set (1 train line), not in these roots. R7 leaves its R6 treatment unchanged.

## Weight

Smolenskin's *Kol sifre* (3 volumes) gives 41,562 lines, 36% of train. Consider `--max-lines-per-book` or per-book sampling.

## Excluded (4 works, no rights justification)

| IA item | PBY | Reason |
|---|---|---|
| hayehudimbelodzo00frenuoft | 58907 | no death year for Jacob Frenkel |
| p1toldothaemunot03menz | 58581 | no death year for Jacob Frenkel |
| hakhmatshimonben00kohn | 25753 | Ben Sira's Wikidata QID is the book, not the person |
| seferhaatsamim00ibne | 17928 | no publication place |

These are in `f8f_ia/out_excluded/`. The approved R8 follow-up is a PBY-QID correction file plus century-precision death years.

## Dropped to R8

- **f8f3:**
  - Bachrach 1884 (confirmed, not aligned);
  - the 221 shortlisted groups not yet through the NLI gate;
  - the R6 second pass.
- **f8f_ia:** 3 books whose IA manifests returned 504 until after the cutoff: bioretletoldotha01gott, kevarpirezikhron00haco and sifruthahisoriya11kaha.
- **f8f_g:** all of it (Google-digitised and other Route B/C scans).

11 IA books were skipped because neither reading direction cleared the 2-of-6 probe. The list is in the JSON.

## Release notices

- **f8f3 scans:** from the collection of the National Library of Israel (מאוסף הספרייה הלאומית), each under the NLI "public domain – free use" terms. Each book's provenance has its NLI record id, manifest URL and attribution.
- **f8f_ia scans:** Internet Archive library scans of public-domain books with no licence field. Each item's original IA conditions still apply. The gate is `decide_ia_rights` (decision `planning/decisions/2026-11-09-internet-archive-library-scans.md`). Each work also has its own `rights_justification` (decision `planning/decisions/2026-11-10-legal-strategy.md`).
- **Text:** Project Ben-Yehuda public-domain dump, release 2026-03. Credit: "Project Ben-Yehuda volunteers", https://benyehuda.org.
