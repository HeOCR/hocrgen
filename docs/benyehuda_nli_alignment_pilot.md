# Project Ben-Yehuda texts on NLI free-use scans: alignment pilot (F8f)

This pilot turns human-typed public-domain texts from Project Ben-Yehuda (PBY) into **silver** page–text pairs on NLI scans of the same printed edition. The tool is the operator-only `hocrgen.tools.benyehuda_nli_alignment`; evidence was captured on 2026-11-06. The per-candidate match rows and the per-page alignment rows are in [`benyehuda_nli_alignment_pilot.json`](./benyehuda_nli_alignment_pilot.json). The scans, the full PBY texts, the OCR and the side-by-side review reports stay outside the repository.

Nothing here is a source, a seed or a release item. `profile_open_v1`, scoring and `benchmark_v1` are unchanged.

## Status of every pair

Every page pair carries:

- `text_provenance: human_typed_edition_text_aligned`
- `adjudication_status: not_adjudicated`
- `reference_eligible: false`
- `verification_status: needs_human_verification`

A pair becomes a reference only after a human verification pass and the normal F2 attestation and adjudication. Campaigns for that pass are allowed (decision of 2026-11-06).

**OCR is used only for localization.** Tesseract (`heb`, `--psm 3`) finds the printed lines and their boxes. The pair text is always the PBY text. No OCR text is written to the alignment output or the summary, only line geometry, letter counts and scores. The two-page test fixture keeps its Tesseract TSV, marked `localization_ocr`, so the test can re-run the alignment without a network.

## Rights

- **Text.** The PBY dump `LICENSE` (release `2026-03`) says the data files "are in the public domain". The dump holds only PBY's public-domain subset; the site also hosts works published with permission, and those are not in the dump. This is the evidence in the [track C note](./2026_11_06_israeli_public_domain_documents_research/verification/track_c_nli_books.md) §6.
- **Scans.** Rights are decided per item by the unchanged F8c gate (`decide_nli_rights`) on each IIIF manifest's `license` slug (decision 13). Only `public-domain-free-use` with canvases is matched. Google-class `public-domain-non-commercial-use` editions are rejected, as is every other slug.

## 1. Edition matching

PBY records its source edition only as free text (`source_edition`), with no scan link. The operator wrote 45 candidate editions from the catalogue:

- Each candidate is a pre-1950 printed edition named by `source_edition`, or by title, author and year.
- Each candidate has NLI Search API queries, the expected year with a tolerance, and title or publisher terms. The terms are compared on letter skeletons, so spelling variants such as מאנה and מאנדעלקערן still match.

The tool keeps `book` hits that satisfy the year and the terms, then gates up to four of them on their manifests. For each candidate it records the catalogue fields, the kept NLI records (with the manifest's publisher, date and extent), the licence decision and a note on why the edition is the same.

**Match rate: 11 of 45 candidates (24%).** There were 3 search failures (HTTP 502), so the rate is 11 of 42 (26%) over the candidates that got an answer.

| Outcome | Candidates |
| --- | ---: |
| matched: `public-domain-free-use` with canvases | 11 |
| edition found, Google-class `public-domain-non-commercial-use` | 13 |
| edition found, `public-domain-free-use` but no canvases | 3 |
| no NLI record of the edition | 15 |
| search failed (HTTP 502) | 3 |

How the 11 matches are tied to the edition:

| PBY works | NLI record (canvases) | Edition evidence |
| --- | --- | --- |
| Brainin, *Avraham Mapu: Hayav u-Sfarav* (3149) | 990018546440205171 (162) | Same title, Tushiya, Vilna and Warsaw, תרפ"ח (1928). **Confirmed by alignment.** |
| Silman, 9 stories from *Sansinim* (19081–19083, 19128–19133) | 990020250940205171 (180) | Same title and subtitle "שנים עשר סיפורים", Tarbut, 1929. **Confirmed by alignment.** |
| Frank, 73 Zohar legends (48085 …) | 990019385920205171 (206) | PBY's "ורשה: אחיאסף, תרפ"ד" matches the only Frank book from Ahiasaf in 1923/24, *Sefer Agadot ha-Zohar*. |
| Citron, *Me-Ahorei ha-Pargod* (104, 4096 …) | 990020495520205171 (436) | Same title, Vilna: Z. Matz, 1923–1925. |
| Berashadsky, stories (52 …) | 990020308000205171 (468) | PBY cites "סיפורים, תושיה, תר"ע". The NLI record is *Ketavim Aharonim* (Tushiya, 1910), whose title also names the Kaplan biography and Ben-Avigdor essay that PBY carries. |
| Katzenelson, *Mahamadim* (52734 …) | 990017258010205171 (232) | PBY "ברקאי, ורשה"; the NLI record is Barkai, Warsaw, 1923. |
| Katzenelson, *Shirim* (39977 …) | 990013538860205171 (296) | PBY "חובבי שירה, לודז'" (no year); the NLI record is Hovevei Shira, Lodz, 1938. |
| Tchernowitz, 8 essays (1580 …) | 990020522850205171 (280) | PBY "ירושלים: המדפיס, תרפ"ז"; the NLI record is *Im Shahar*, Ha-Madpis, 1927. |
| Mandelkern, 107 poems (62217 …) | 990013637480205171 (122) | PBY's "Leipzig : Selbstverlag des Verfassers" is NLI's publisher string verbatim (*Shirei Sfat Ever*, 1882). |
| Schatz, *Ehad me-Rabim* (7203) | 990020873500205171 (116) | Same title, Jerusalem, תרס"ז (1907). |
| Asaf Halevi (Alter Levin), Dekel 1920 (154 …) | 990019742530205171 (16) | Weak. PBY's "ירושלים: דקל, תר"ף" covers 99 works from two Dekel books; only *Shirei Am* (16 canvases) is free-use. The other book, *Megilat Kedem*, is Google class. |

The two aligned matches are confirmed by their page sequences aligning. The other nine are bibliographic matches until they are aligned.

**What the matching shows:**

- **Nineteenth-century editions are almost all Google class.** Of 15 candidates up to 1905, 10 found their edition at NLI. 8 of those were `public-domain-non-commercial-use`, 1 was free-use with no canvases, and only Mandelkern's 1882 poems matched. This agrees with `F8c2`.
- **Matches come from 1907–1938.** 10 of the 11 matches fall in that range.
- **Free-use without canvases is a real loss.** Bialik's *Dvarim she-be-al Pe* (1935, 86 PBY works), Shatz's *Al Gvul ha-Demama* (1929) and Kahanovsky's *Metropolin* (1892) are free-use with an empty manifest.
- **Most of the catalogue cannot be matched this way.** 21,205 of 26,455 PBY rows have a `source_edition`, but most are post-1948 collected editions (Dvir, Am Oved, Mosad Bialik) or periodical issues. Those are out of copyright range for NLI free-use scans, or not digitized as books.

## 2. Alignment

Each PBY work is aligned on its own against every canvas of its scan. The OCR is cached once per scan.

The method is order-preserving:

1. Both sides are reduced to letter skeletons. Niqqud, punctuation and final forms are normalized away. A loose form also drops ו and י and folds the letters Tesseract confuses on old print, such as ד/ר, ה/ח/ת and כ/ב.
2. Loose 8-grams that are unique on both sides become anchors.
3. The longest increasing chain of anchors keeps the reading order.
4. Each OCR line is refined against its PBY window with `difflib`.

Line classes:

- `matched` — a located line.
- `relocated_in_pby` — PBY has the line, but elsewhere: footnotes moved to the end of the work.
- `catchword` — the next page's first word, repeated at the foot of the page.
- `running_header` and `page_number`.
- `low_confidence_noise` — mean word confidence below 55.
- `unmatched_text` — print text PBY lacks at this place.

Each page records:

- its PBY span (character offsets into the PBY text file);
- `alignment_score`, the letter-weighted similarity of the located lines on the loose skeleton;
- `strict_char_similarity`, the same on the full letters, which mainly measures OCR error;
- per-line spans and boxes;
- the difference counts and classes;
- a decision-12 crop.

**The crop.** The pair image is always the located region: the union of the matched lines, padded by 0.35 of a line height, with the padding kept clear of untranscribed lines. Text PBY lacks therefore stays outside it. When an untranscribed line, or a catchword OCR merged into the last line, lies inside the region, the page is `needs_review` instead.

### Pages aligned

The pilot aligned **10 works on 2 scans: 277 pages.** The remaining matches (Frank, Citron, Katzenelson and the others) are left for the next run. The NLI image server answered HTTP 520 to every request during the run, so their scans could not be fetched.

| Work | Canvases | Aligned pages | Median score | Crop: cropped / needs review | PBY text covered by page spans |
| --- | ---: | ---: | ---: | --- | ---: |
| Brainin, *Avraham Mapu* (3149) | 162 | 145 | 0.987 | 105 / 40 | 97.9% |
| Silman, 9 stories of *Sansinim* (19081–19133) | 180 | 132 | 0.996 | 125 / 7 | 99.6–100% each |

**Quality distribution** over the 277 aligned pages:

- **Bins:** 275 `high` (alignment score 0.90 or more), 2 `medium` (0.80–0.90), 0 `low`.
- **Alignment score:** 249 pages at 0.98 or more, 21 at 0.96–0.98, 4 at 0.94–0.96, 3 lower (0.82, 0.88, 0.90).
- **Strict character similarity:** median 0.981, 10th percentile 0.954. The difference from the alignment score is mostly OCR error on the print, not PBY error; human verification decides which is which.
- **Crop:** 230 pages are cropped cleanly and 47 are `needs_review`. Of the 47:
  - 16 have a catchword merged into the last line by the OCR;
  - 13 have a footnote line inside the text block (`relocated_in_pby`);
  - 18 (plus 11 of the above) have other unlocated print lines inside the text block, such as marginal notes, small-type footnotes or OCR fragments.

The 17 Brainin canvases that did not align are:

- the cover, title and blank leaves;
- the table of contents (canvases 7–10), which PBY does not carry;
- canvas 128, a full page of body text that **PBY omits**: PBY joins the sentence across the missing page.

### Difference classes (pages carrying each)

| Class | Pages | What it is |
| --- | ---: | --- |
| `running_header_or_page_number_omitted` | 263 | The print's running head or page number; PBY never carries them. Always outside the crop. |
| `spelling_variant` | 160 | Aligned words that differ only in ו or י: 331 words, against 55,084 identical words. Part of this is OCR confusing ו, י and ן, so the count is an upper bound. |
| `quote_style_normalized` | 73 | The print's low-high quotes (`,,X"`) are normalized to `"X"` in PBY. |
| `print_text_not_in_pby_span` | 35 | Lines of the print PBY lacks at that place: the end of the preceding story, captions, unrecovered footnote lines. |
| `pby_text_not_located_on_print` | 25 | PBY letters between two pages, or inside a span, that no OCR line located. Usually OCR failure on small type. Once it was 2,149 letters before Brainin canvas 118, a likely gap in the scan. |
| `footnote_reformatted` | 24 | The print's footnotes appear in PBY as inline markers (`1נולד`) with the notes moved to the end of the work. |
| `pby_niqqud_present` | 22 | 5% or more of the span's words carry niqqud. Tesseract drops niqqud, so the print's niqqud is `not_measured_by_ocr`. Brainin's quoted poems are pointed in PBY. Silman's text has niqqud only in titles and a few words, 0.4–2.2% of words. |
| `catchword_omitted` | 21 | The printed catchword at the foot of the page, which PBY drops. |
| `span_overlaps_previous_page` | 2 | One is a table-of-contents page aligned to the chapter summary it repeats. |

## Main obstacles

1. **Rights, not text.** Most pre-1906 editions PBY typed from are Google-class at NLI. Several free-use records have no canvases.
2. **The catalogue's edition field is weak.**
   - It is free text, often only "city: publisher" with no title or year (for example 235 works from "ברלין: אשכול").
   - It often names a collected edition, while NLI holds the separate volumes.
   - Matching needs a person who knows the bibliography. The tool records the evidence but cannot decide alone.
3. **PBY is not page-faithful.** It drops running heads, catchwords, page numbers and the table of contents, moves footnotes to the end, and normalizes quotes. In one case it omitted a whole page. These are measurable, and the crop and the flags handle them, but every pair still needs a human check.
4. **The OCR limits what can be measured.**
   - Tesseract cannot see niqqud, so added niqqud is only measured on the PBY side.
   - Small type (footnotes, chapter summaries) and pages with marginal or two-column notes produce the `needs_review` pages.
   - Poetry and fully pointed texts were not reached in this run (Katzenelson's *Shirim* and Mandelkern's poems are matched but not aligned).
5. **Network.** The NLI image server refused requests above the image's native width (HTTP 403, handled by asking `info.json`), and then returned HTTP 520 for the rest of the run.

## Reproduce (operator only)

```bash
set -a; . ~/.config/heocr/nli.env; set +a   # NLI_API_KEY, never printed
python -m hocrgen.tools.benyehuda_nli_alignment match --candidates candidates.json \
  --catalogue pseudocatalogue.csv --out match.json --captured-on 2026-11-06
python -m hocrgen.tools.benyehuda_nli_alignment align --catalogue pseudocatalogue.csv \
  --pby-id 3149 --pby-text m3149.txt --manifest 990018546440205171.json \
  --manifest-url https://iiif.nli.org.il/IIIFv21/990018546440205171/manifest \
  --nli-record-id 990018546440205171 --work-dir work/990018546440205171 --out-dir out/3149 \
  --generated-on 2026-11-06            # writes alignment.json and review.html
python -m hocrgen.tools.benyehuda_nli_alignment summarize --match match.json \
  --alignments out/*/alignment.json --out docs/benyehuda_nli_alignment_pilot.json
```

The test fixture `tests/fixtures/benyehuda_nli/` holds two aligned Brainin pages (canvases 15–16). It contains:

- grayscale page images 800 px wide;
- the trimmed manifest capture, which passes the F8c gate;
- the PBY excerpt;
- the localization OCR;
- the expected alignment, which the test recomputes.

## Follow-ups

- **Verify.** A human verification campaign over the `review.html` reports. The reviewer confirms that the PBY span is exactly the text inside the crop box, and fixes the boundary words.
- **Align the other nine matches.** This includes poetry, to measure niqqud and line-structure differences.
- **Add a review-only source.** A `review_only` source would take verified pairs only. It would pin each page image, crop box and PBY span, and keep the silver status until verification is recorded. It is not added here.
