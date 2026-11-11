# 2026-11-11: publisher text verified by a human counts as adjudicated

- Status: accepted
- Decided by: the maintainer (Shay Palachy Affek), 2026-11-11, in the heocr-lead session. Asked whether "gazette lines you check against the PDF's own text count as fully checked references", he answered: "YES".
- Written by: `lead[claude/claude-code#shay-macbook-m4]@heocr/opensource`
- Extends: `2026-11-07-line-verification-attestation.md` ("Yes, like quality 4": one human typed the candidate, and a second human verified it).
- Context: heocr-engine decisions 0017 and 0018. The new-printed evaluation wave of Reshumot laws and regulations is planned in heocr planning `tasks/eval-domains/pmod_set_plan.md`.

## Decision

1. **A new candidate provenance is adjudicated.** The candidate text is the **publisher's own text layer of a born-digital PDF**, i.e. the source the print was made from. A human verifies it against the printed page in heocr-review: the flagged lines are decided one by one, then the page is attested. A line or page verified this way is **adjudicated** and `reference_eligible: true`, the same standard as Wikisource quality 4 and the 2026-11-07 line-verification attestation.
2. **Status name.** The attestation status is recorded as `publisher_text_human_verified`, and it maps to `adjudication_status: adjudicated`.
3. **Guards that still apply:**
   - **(a)** The PDF must be truly born digital. A scanned PDF with an OCR text layer never qualifies, because OCR output is never a reference.
   - **(b)** The verifier is a human. Agents never verify.
   - **(c)** Mechanical flag rules (bidi or digit order, brackets, leaders, unmapped glyphs) decide only which lines get a closer look. They never decide text.
   - **(d)** An edit the human makes replaces the publisher text for that line, and is recorded as its own decision.
   - **(e)** One page attestation covers every capture of that printed page (rendered, print_scan, phone), because the printed text is identical.
4. **Scope.** This decision covers born-digital publisher text in general, with Reshumot as the first source. Each new source still needs its own rights record.
