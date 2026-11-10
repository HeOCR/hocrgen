# HeOCR Contribution Channels Map

`E1b` maps every way people and organizations could contribute to HeOCR. It is a planning map. It does not open any upload form or collection flow, and it does not approve any source. Each channel that we decide to build needs its own roadmap notation and a bounded implementation PR. That PR keeps the gates in [`CONTRIBUTING.md`](../CONTRIBUTING.md), the [Modern Handwritten Acquisition Policy](./modern_handwritten_acquisition_policy.md) (`F3a`/`F3b`) and the [legal strategy](./legal/2026-11-10_legal_strategy.md).

`E1a` defined the safety rails for code, source, synthetic-asset and review contributions from developers. `E1b` widens the view to non-developers: writers, scanner owners, labellers, institutions, researchers, funders and users.

## The basic model

An OCR model learns which text matches which image. Every contribution supplies one or more of these:

| Supplies | Why it matters |
| --- | --- |
| Text | Raw material for synthetic rendering and language-model priors |
| Images | Real visual variation: scripts, paper, ink, devices, damage |
| Image+text pairs | Direct training and evaluation signal |
| Judgments about pairs | Verification, correction, layout and classification labels |
| Rights | Permission to release openly; often the real bottleneck |
| Resources | Compute, money, equipment, legal help, reach |
| Feedback from real use | Hard cases and corrections from actual users |

The main design idea: **when HeOCR supplies the text, the contributor only adds a real-world physical transformation.** The correct transcription then comes for free, and the text content is already cleared and contains no private information. Several of the most valuable channels below (`CC-B1`–`CC-B7`) follow this pattern.

## How to read each channel

Channel ids carry a `CC-` prefix (for example `CC-B4`) so they never clash with roadmap notation such as `E1a` or `F2a`.

Each channel lists:

- **Gives:** what HeOCR receives.
- **Transcription:** where the correct text comes from (`known`: we supplied it; `existing`: it already exists; `labelled`: a person produces it; `none`).
- **Gate:** the rights, consent or privacy step it needs.
- **Effort:** a rough build cost (`low`, `medium`, `high`).

## A. Text

Text feeds the `hocrsyngen` renderer and the language-model priors. It is not training data for real images on its own.

- **CC-A1. Contributors' own writing, released as CC0.** Typed into a box or uploaded as txt/doc/docx. Gives modern, everyday Hebrew. Transcription: known. Gate: an author attestation and a CC0 waiver; screening for personal data about third parties. Effort: low.
- **CC-A2. Organizations releasing text collections as CC0.** Nonprofit reports, newsletters, municipal notices, company blogs, course notes, and theses released by their authors. One agreement can cover thousands of documents. Gate: an institutional waiver signed by someone with authority; a check that the organization owns the rights to every document it releases. Effort: low per partner, but outreach takes time.
- **CC-A3. Leads to public-domain text.** For example legislation, Knesset records and court rulings (in Israel, Copyright Act 2007 §6 gives no copyright in laws, regulations, Knesset proceedings and judicial decisions, including those of other bodies exercising judicial power; verified in [`docs/2026_11_06_israeli_public_domain_documents_research/verification/track_a_legislative_judicial.md`](./2026_11_06_israeli_public_domain_documents_research/verification/track_a_legislative_judicial.md). Other government documents are State works under §36, protected for 50 years under §42, so tenders, reports and letters are not covered. Editorial additions in commercial legal databases, such as headnotes and summaries, are not §6 material. US status is recorded per item as usual.), and works by authors who died more than 70 years ago. Gate: the existing source-proposal workflow. Effort: low.
- **CC-A4. Real-world document types filled with made-up data.** Invoices, forms, menus, prescriptions, report cards and flyers, designed in common office or design tools and filled with fictional details. Gives layout variety. Gate: CC0, a check that no real data is present, and licence checks on the fonts and templates used. Effort: low.
- **CC-A5. Hard text.** Niqqud, mixed Hebrew, English and numbers with bidirectional runs, acronyms (ראשי תיבות), rare names and places, slang, and Aramaic. Gate: same as `CC-A1`/`CC-A2`. Effort: low.
- **CC-A6. Word lists and dictionaries** for post-correction and synthetic sampling. Gate: a licence check on each one; copyleft resources (for example Hspell is AGPL) may need separate handling or must be excluded. Effort: low.

## B. Real-world transformations of text HeOCR supplies

HeOCR renders cleared text (CC0 or public domain) into a PDF or a page. The contributor sends back a physical version of it. Transcription: known for every channel in this section. Common gate: a contributor consent and CC0 waiver for the image, stripped EXIF and device metadata, and a check that no unrelated content appears in the frame (faces, documents, room details).

- **CC-B1. Print and scan.** They print the page at home or at work and scan it however they can. The odder the result, the better. Effort: low.
- **CC-B2. Photograph with a phone.** At an angle, in poor light, folded, crumpled, stained, behind glass. Effort: low.
- **CC-B3. Old and odd machines.** Photocopy of a photocopy, fax, receipt printer, label printer, dot-matrix printer, Hebrew typewriter. Effort: low.
- **CC-B4. Copy the text out by hand.** HeOCR provides the text; the contributor writes it, in block or cursive, with any pen and paper, at any speed. This gives handwriting with a known correct text and no private content, which may make it the strongest handwriting channel available. Gate: handwriting is still the contributor's personal trait, so it stays under the `F3a` consent, takedown and composition rules even though the content is cleared. Minors need parental consent. Effort: medium.
- **CC-B5. Alphabet and glyph sheets.** Each letter, final form and niqqud mark written many times on a template grid. Feeds real-glyph synthesis (the S16 glyph banks) directly. Gate: same as `CC-B4`. Effort: low.
- **CC-B6. Other surfaces.** Chalk, whiteboard, a photographed screen (moiré patterns), a projected slide, embroidery, engraving. Effort: low.
- **CC-B7. Screenshots.** HeOCR text rendered in different apps, browsers, fonts, dark mode and low resolution, for OCR of screen content. Gate: font and interface licences. Effort: low.

## C. Images

- **CC-C1. New, better, odder or more openly licensed scans of public-domain works.** Books, newspapers and ephemera the contributor owns. Transcription: none at first, labelled later. Gate: public-domain status, checked per work; an assurance that the scan itself is the contributor's own. No scans that would taint the licence (see the legal strategy). Effort: medium.
- **CC-C2. Institutions releasing scans openly, or running scan days.** Libraries, archives, universities, yeshivas, kibbutz and municipal archives, and publishers' public-domain backlists. Gate: an institutional rights statement or an open licence. Effort: high for each partner, but each partner can bring a lot.
- **CC-C3. Blank and background paper.** Empty old pages, paper textures, stains, bleed-through, yellowing. Makes synthetic pages more realistic. Transcription: none needed. Gate: CC0 and a check that the pages really are blank. Effort: low, and the rights risk is very low.
- **CC-C4. Photos of signs in public places,** for OCR of text in photos. Gate: not covered by §23 (which permits photographing architecture, sculpture and applied art permanently in a public place, not text or posters). Plain sign text — names, directions, short phrases — usually lacks the originality copyright needs, but logos, posters, artwork and longer texts on signs can be protected works, and §22 (incidental use) does not fit a dataset whose subject is the sign. Each sub-type needs a check under the legal strategy before intake (`CC-F2`). Also: blur faces and car plates, no private property interiors, and the same EXIF/privacy rules as section B. Effort: medium.

## D. Ready-made pairs

- **CC-D1. Typeset source plus printed PDF.** Publishers or authors who hold both versions of an openly releasable work. Perfect pairs with no labelling. Transcription: existing. Gate: an open release of both versions. Effort: low for each partner.
- **CC-D2. Existing transcriptions lined up with existing scans.** Project Ben-Yehuda, Hebrew Wikisource and archive transcriptions, plus their proofreading histories. Transcription: existing. Gate: the licences of both sides; this extends the current Ben-Yehuda and Wikisource alignment work. Effort: medium.
- **CC-D3. Old OCR output plus human corrections** held by institutions. Transcription: existing. Gate: an institutional release. Effort: medium.

## E. Labelling images HeOCR provides

All labelling channels need contributor terms that assign or waive rights in the labels (CC0), plus quality controls: overlapping assignments, known-answer check items and agreement scoring. Review capacity is scarce, so these channels should produce labels that automatic checks can accept or flag, and pass only disagreements to a human (see the hardest-first review principle in the review app).

- **CC-E1. Transcription** of a character, word, line, paragraph or page. Transcription: labelled. Effort: medium.
- **CC-E2. Approve or reject** an existing transcription. Effort: low.
- **CC-E3. Click the wrong word.** Faster than retyping, and it locates the error. Effort: low.
- **CC-E4. Pick the better of two transcriptions.** Easier and more consistent than an absolute rating. Effort: low.
- **CC-E5. Quick glyph decisions,** for example "is this ר or ד?". Can run as a game, or as a CAPTCHA-style widget on partner Hebrew websites. Effort: medium.
- **CC-E6. Layout labels.** Boxes for columns, headers, footnotes and tables, and reading order. Feeds segmentation and reading-order work. Effort: medium.
- **CC-E7. Classification.** Script (square, Rashi, cursive, regional styles), printed or handwritten, era, quality, niqqud present or absent. Effort: low.
- **CC-E8. Read the page aloud.** Speech recognition, for example through a partnership with an open Hebrew speech project, turns the recording into a draft that the contributor then corrects. The audio is discarded unless it is separately released. Effort: medium.
- **CC-E9. Old-handwriting readers.** Older contributors who can read old cursive and Yiddish-influenced hands that younger readers cannot. A targeted pool for `CC-E1`/`CC-E2` on historical handwriting. Effort: low once `CC-E1` exists.

## F. Rights and provenance research

- **CC-F1. Copyright-status research.** Author death dates, publication dates, publishers. Genealogists and librarians are well suited. Unblocks `CC-A3`, `CC-C1` and `CC-C2`. Effort: low.
- **CC-F2. Pro-bono legal help.** Israeli copyright opinions, CC0 consent templates, takedown procedure, approaches to institutions. Effort: low.
- **CC-F3. Metadata enrichment.** Dates, places, publishers, source collection. Effort: low.

## G. Evaluation and stress tests

- **CC-G1. "HeOCR fails on this" reports.** An image (public domain or CC0) as a hard test case, optionally with the correct text. A new evaluation reference is preferred over more training data. Effort: low.
- **CC-G2. Challenges and competitions,** such as "find a page that breaks the model", with any submission screened through the `CC-G1` gate. Effort: medium.
- **CC-G3. Domain evaluation.** An organization tests HeOCR on its own documents and reports the score, without sharing the documents. Effort: low.

## H. Feedback from real use

- **CC-H1. Opt-in donation at the point of use.** A user runs HeOCR on their own public-domain or CC0 document, corrects the output, and chooses to donate the pair. The donation is off by default, with an explicit rights attestation and a privacy screen. This can grow by itself as HeOCR gets used. Effort: high.
- **CC-H2. Integrations with a correction loop.** Wikisource and Ben-Yehuda proofreading tools, document-management and reference managers, a browser extension. Effort: medium for each integration.

## I. Engineering, compute and models

- **CC-I1. Code.** Source adapters, the review app, cleanup rules, documentation and translation (already covered by `E1a`).
- **CC-I2. Compute.** University clusters, cloud and open-model hosting grants, GPU time.
- **CC-I3. Volunteer CPU** running the synthetic generator, BOINC-style. Needs deterministic manifests and output checks.
- **CC-I4. Specialised models** for Rashi script, old newspapers, forms or handwriting, released under Apache-2.0 with disclosed training inputs that satisfy the licence rules.
- **CC-I5. Degradation and augmentation recipes.** Realistic physical models of ink, paper and lenses, contributed to `hocrsyngen`.

## J. Reach, community and funding

- **CC-J1. University course assignments and hackathons.**
- **CC-J2. Volunteer programs,** including high-school community-service hours (מחויבות אישית). Anyone under 18 needs a parental-consent process.
- **CC-J3. Community ambassadors.** The Haredi world (religious books, Rashi script), older adults, families with archives.
- **CC-J4. Partnerships** with open-knowledge and open-source organizations, libraries and open Hebrew speech projects.
- **CC-J5. Equipment and money.** Lending a book scanner, grants, sponsors, prizes.

## Strongest channels

Ranked by value relative to effort:

1. **`CC-B4` handwriting copied from text HeOCR supplies:** a known correct text and cleared content at once.
2. **`CC-D1` typeset source plus printed PDF:** perfect pairs at scale.
3. **`CC-H1` opt-in donation at the point of use:** grows with use.
4. **`CC-C3` blank and background paper:** almost free, with very low rights risk.
5. **`CC-E3`/`CC-E4` click-the-error and pick-the-better:** cheap labels that suit the hardest-first review queue.
6. **`CC-F1` rights research:** unblocks most image channels.
7. **`CC-B1`–`CC-B3` print, photograph and machine transformations:** cheap, and they cover real device variation with known text.

## Gates that apply to every channel

- **Consent and waiver:** a recorded CC0 waiver (or a recorded public-domain basis) for every contributed item, kept with the item's manifest entry.
- **No licence contamination:** nothing that would block open release of data (CC0) or weights (Apache-2.0); this follows the legal strategy, including the rule on how Google-class scans may enter.
- **Privacy:** stripped EXIF and device metadata; no third-party personal data; faces, plates and private documents in the frame are removed or the item is rejected.
- **Modern handwriting** always follows `F3a`/`F3b`, whatever the content.
- **Minors:** parental consent, and no identifying metadata.
- **Takedown:** every channel connects to the existing takedown and removal path.
- **Separate source families:** contributed real images, known-text physical transformations, and synthetic outputs each keep their own source ids, so composition caps and evaluation decontamination stay enforceable.
- **Evaluation data stays real:** known-text physical transformations (section B) count as real images, but each evaluation split must be decontaminated from the texts used to render them.

## Next steps

Each selected channel needs a roadmap notation before implementation. Likely first steps:

- a contributor consent and waiver template that covers sections A, B and E, reviewed with the legal help described in `CC-F2`;
- a known-text kit for `CC-B1`–`CC-B5`: the rendered PDFs, templates and an intake manifest schema that records the source text id, device and transformation;
- a pilot of `CC-C3` blank-paper intake.
