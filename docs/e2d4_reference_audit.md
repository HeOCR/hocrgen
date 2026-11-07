# E2d4: an audit of the scored printed reference pages

> **Status (2026-11-07).** The agent audit is committed as **proposals**. The maintainer has decided 103 of them
> (all accepted), and a standing rule resolves 13 more ([E2d4b](#e2d4b-the-space-before-punctuation-rule)); 403
> are still undecided. Reference text has now changed by human decision on 6 scored pages, and by the rule on 5
> scored and 22 quality-3 pages; the E2d4b section has the new scores. The CER table under "Hypothetical impact" is still **hypothetical**.

## The rule (maintainer decision, 2026-11-07)

The reference pages are audited against their scans. An agent proposes corrections and a human confirms them.

- **An agent proposal is never attestation.** It never changes a reference by itself.
- **Only a human decision applies a correction.** A decision is `accepted`, `rejected` or `edited` (with the
  human's own text).

## Why

E2d3b found that Wikisource quality-4 ("validated") text lets OCR errors through. Of the 26 pages edited after
validation, 22 had validated text that disagreed with the scan. The 38 scored pages had never been checked this way.

## What was done

**The audit.** An agent read all 38 scored pages of the E2d3e pool (14 books, tranche `e2d3e_real_tranche_v5`)
against the pinned scans.

- **Reading.** Each page was read tile by tile on enlarged crops (columns right to left, then bands). The crops came
  from a 1920 px render of the same Commons file and page as the scored 960 px image. The reference was compared
  word by word, and unclear spots were zoomed 2–4×.
- **OCR as pointers only.** 74 tokens that Tesseract and R3h + blla both read the same other way were used as
  pointers. Each one was checked on the scan.
- **Conventions not reported:**
  - line breaks and paragraphing;
  - running heads and page numbers;
  - `[n]` footnote marks;
  - the glyph identity of quote marks, geresh and gershayim, maqaf and dashes;
  - the old typographic space before `:` or `.` (since E2d4b, the `space_before_punctuation.v1` rule removes it
    everywhere).
- **Splitting the work.** Three agent lanes split the books. The coordinating agent then spot-checked 16 proposals on
  their crops (12 at random among the high-confidence ones), and all 16 matched the print.
- **Out of scope.** Pages outside the 38, the release splits and `benchmark_v1` are unchanged. Nothing was published.

**The proposals: [`reference_audit_proposals.json`](./reference_audit_proposals.json)**
(`reference_audit_proposals.v1`, audit `e2d4_reference_audit_v1`).

- **Each page** is pinned to its `base_revision_id` and its `base_text_sha256`, the exact scored text. Each page
  records `audit_status` (`audited_with_findings` or `audited_no_findings`) and any `text_not_on_page_candidate`.
- **Each proposal** records:
  - the item id and the character span `[start, end)` in that text;
  - `current` and `proposed`, plus `context_before` and `context_after`, so it can be found without offsets;
  - a `category` and a `confidence` (`high`, `medium` or `low`);
  - a `region` box in normalised page coordinates;
  - a short note;
  - `status: agent_proposed` and `checked_by: agent`.
- **Licensing.** Wikisource text is CC BY-SA 4.0, so quoting the spans is fine. The scan crops stay out of git.

**The decisions: [`reference_audit_decisions.json`](./reference_audit_decisions.json)**
(`reference_audit_decisions.v2` since E2d4b; `v1`, as the review app exports it, holds human decisions only). Each
human decision records:

- `decision_id` (`decision:<proposal_id>:<reviewer>`), `proposal_id` and `item_id`;
- `decision`, plus `text` for `edited`;
- `reviewer`: a pseudonymous id, `rv_` and 8 lower-case letters or digits (`rv_3f9a01bc`), so no real name is ever
  recorded;
- `decided_at` (a date) and `checked_by: human`.

**Several reviewers.** Several reviewers may decide one proposal, one decision each. A proposal applies when at least
`min_reviewers` reviewers decided it and all of them agree: the same decision, and for `edited` the same text.
Reviewers who disagree leave it in `conflict`, and it is not applied. For now `min_reviewers` is 1, so one human
accept suffices while there is a single reviewer. Every applied outcome records its `reviewer_count` and reviewers,
so a two-reviewer rule (`--audit-min-reviewers 2`) can come later without changing the files.

The validator refuses a reviewer that is not an `rv_` id, `checked_by` other than `human` or `rule`, two decisions
by one reviewer on one proposal, an edit equal to the current text, and stale proposal ids. Rule decisions are
described under [E2d4b](#e2d4b-the-space-before-punctuation-rule).

**Applying them (`hocrgen.reference_audit`).** `wikisource_eval_references --audit-proposals P --audit-decisions D`
passes the audit to `scored_page_reference`, the one rule the evaluation and the split stage share.

- **Only human decisions change text.** Only agreed `accepted` and `edited` outcomes are applied, to the exact text the
  proposals were made on. A changed base text or revision, a moved span, or overlapping proposals fail closed.
  Without decisions, every reference file and the manifest are byte-identical to a run without the audit (tested).
- **Provenance.** A corrected reference records its provenance: `reference_audit_provenance` on the item and
  `reference_audit` in its adjudication record. The provenance holds the base revision and text checksum, the applied
  decision ids in text order, and the new `text_sha256`.
- **The corrected reference.** Its reviewers add `heocr:<rv id>` to the two Wikisource editors, and its
  `change_reason` lists the decisions. Its attestation is `two_editor_validated_human_corrected` (the uncorrected
  state is `two_editor_validated`). Footnote facts follow the corrected text when a human adds or removes `[n]`
  marks. A page with excluded spans refuses corrections.
- **Pending pages stay in the pool.** A page with undecided proposals keeps its current text, with any decided
  corrections applied. It is flagged `audit_pending`; `counts.audit_pending` and `reference_audit.states` give the
  totals.
- **The split weight is unchanged.** The split stage calls `scored_page_reference` without an audit.

`python -m hocrgen.tools.reference_audit` validates both files and prints counts only, including reviewers and
proposals by reviewer count. With `--snapshot-root` it also checks every span against the current scored text.

**Import bundle for a review app.** `--export-dir OUT --page-images DIR` writes three things, for example for the
online review app `HeOCR/heocr-review`, which reads these proposals and writes these decisions:

- `OUT/proposals.json`: the proposals, byte for byte;
- `OUT/crops/<proposal_id>.jpg`: the enlarged, outlined crop of each proposal, cut from any page-frame render of the
  pinned scan;
- `OUT/crops.json` (`reference_audit_crops.v1`): each crop's file, SHA-256 and size, the source image's SHA-256, and
  the crop box.

The bundle holds scan crops, so it stays outside git.

## Results

**Coverage.** All 38 pages were audited: 33 have proposals and 5 have none (`audited_no_findings`):

- Hebrewbooks 38168 p. 2;
- *Selihot* p. 38;
- Baer, *Seder Avodat Yisrael* p. 1;
- Luzzatto p. 60;
- *Masa ba-Arav* p. 5.

There are no `text_not_on_page` candidates.

**519 proposals**

| Category | High | Medium | Low | Total |
|---|---:|---:|---:|---:|
| `letter_confusion` | 30 | 41 | 10 | 81 |
| `word_join_split` | 0 | 0 | 0 | 0 |
| `punctuation` | 215 | 35 | 4 | 254 |
| `spacing` | 116 | 2 | 2 | 120 |
| `missing_text` | 7 | 16 | 3 | 26 |
| `extra_text` | 4 | 0 | 0 | 4 |
| `unprinted_editors_text` | 32 | 2 | 0 | 34 |
| **All** | **404** | **96** | **19** | **519** |

Three `train` books hold 445 of the proposals: *Toldoth Tannaim veAmoraim* I (213), *Hut ha-Meshulash* (117) and
*Masa ba-Arav* (115). The 10 validation + test pages have 27 proposals, only one of them high-confidence.

**What the proposals say**

- **Masa ba-Arav.** A space comes before a comma or full stop (`ודונג ,אם` where the print has `ודונג, אם`) on every
  page with body text, not only pp. 18–20. There are also plene spellings where the print is defective (`פורסם` for
  `פרסם`), and letter errors (`דוכום` for `דוכוס`, `סיסים` for `סוסים`, `ויתגגפו` for `ויתנגפו`).
- **Toldoth Tannaim veAmoraim I.**
  - Gershayim are dropped from Talmud folio numbers (`כב.` where the print has `כ"ב.`).
  - Punctuation is changed in citation lists, and heading full stops and commas are dropped.
  - Some word-level errors:
    - p. 407: `ועברה` for `ובאת`, `כא:` for `כט:`, a missing `הוו`, and an extra `רב`;
    - p. 33: `היה אמורא` for `אמוריה`;
    - p. 35: `לי מר` for `ליה למר`.
  - Two abbreviations are expanded (`רבי שמעון` for `ר"ש`).
  - About ten `הוא` read as `היא` on the print. These are marked medium, because the print's short stroke may be
    broken type.
- **Hut ha-Meshulash.**
  - The print's mid-height separator dots (`•`) are missing throughout.
  - Many abbreviations are expanded: `היה` for `הי׳`, and `בדיני שמים` for `בד״ש`. These are recorded as
    `unprinted_editors_text`.
  - Some clear letter errors: `בקפרו` for `בספרו`, `להמרש` for `להמדרש`, `אתשורוש` for `אחשורוש`.
- **Agadat ha-Melekh Artush p. 3.** Two editors' notes (`[מלה לא ברורה]`, `[כמה אותיות לא ברורות]`) stand where the
  print has only dots. Several names differ from the print (`לוט` for `לונו`).
- **Sefer ha-Mispar.** The reference leaves out the 14 printed footnote marks. They are proposed as `[n]` insertions
  at medium confidence, because leaving them out may be this page's convention.
- **Vikuah and the Korfu siddur.** Two references hold U+FB20, a presentation-form ayin, instead of U+05E2.
- **Hebrewbooks stamps.** Some proposals follow the print where the print itself looks wrong (`תכנם`, `אפינה`).
  Others add a Hebrewbooks digitisation stamp printed inside a title block. Both are marked medium or low, for the
  reviewer to decide.

No joined or split words were found on these 38 pages.

## Hypothetical impact (diagnostic only)

> **Hypothetical.** This is what the CER would be if every high-confidence proposal were accepted. No human has
> decided anything; real numbers change only after human decisions.

The same cached E2d3e predictions are scored under `primary.v1`. The 404 proposals were applied in memory on 24 pages,
and the reference grows from 50,686 to 50,813 characters.

| Engine | All 38: current | All 38: hypothetical | Δ | Val + test (10, diagnostic): current | Val + test: hypothetical | Δ |
|---|---:|---:|---:|---:|---:|---:|
| Tesseract 5.5.3 `heb`, psm 3 | 0.237 | 0.226 | −0.010 | 0.385 | 0.385 | −0.000 |
| R3d + R4d + A1 | 0.901 | 0.901 | +0.000 | 0.866 | 0.866 | +0.000 |
| R3g + R4d + A1 | 0.896 | 0.896 | +0.000 | 0.856 | 0.856 | +0.000 |
| R3h + R4d + A1 | 0.898 | 0.899 | +0.000 | 0.853 | 0.853 | +0.000 |
| R3h + blla (diagnostic) | 0.578 | 0.573 | −0.004 | 0.656 | 0.656 | +0.000 |

What the table shows:

- **Tesseract improves** by about one point on all pages: 477 fewer edits. Tesseract reads the print, and these
  corrections make the reference match the print.
- **R3d, R3g and R3h + R4d + A1 do not change.** Their CER is near 0.9, so the reference differences are lost in
  their own errors.
- **Validation + test barely moves.** Those pages have almost no high-confidence proposals.

The corrections matter for a fair reference, and more for a good engine than for the current R3 line.

## Human review

The packet is operator-only and outside git:
`tasks/real-source-mapping/intermediates/e2d4/review_packet/e2d4_review_packet.html`, with a Hebrew `README.he.md`.

- **What it is.** One self-contained HTML file that works offline from `file://`. It makes no network requests (a
  CSP forbids them) and renders RTL. It holds all 519 proposals, easiest first: high confidence, then spacing and
  punctuation first.
- **Each proposal** shows the enlarged crop with the region outlined, the current and proposed text with visible
  spaces and code points, the category, the confidence and the agent's note. A full-page view shows where the region
  is.
- **Controls.** Accept, reject and edit, with keyboard shortcuts that work in any keyboard layout. Progress is kept
  in the browser.
- **Reviewer id.** It makes a random `rv_` id on first use and keeps it in the browser. Decisions by other
  reviewers in an imported file are kept on export.
- **Output.** It exports `reference_audit_decisions.json` in exactly the committed format, and was checked against
  the validator. Replace `docs/reference_audit_decisions.json` with the export, then rebuild the references with
  `--audit-proposals` and `--audit-decisions`.

## Reproduction (operator)

```
# validate the committed files, and check every span against the tranche snapshot
python -m hocrgen.tools.reference_audit --snapshot-root <tranche>/sources/wikisource_he_proofread/snapshot
# rebuild the E2d3e reference set with the audit (pending pages flagged; human decisions applied)
python -m hocrgen.tools.wikisource_eval_references <snapshot> <out> --reference-manifest-id e2d3e_wikisource_printed_v6 \
  --split-manifest <release split_manifest.json> --items <items.json> \
  --audit-proposals docs/reference_audit_proposals.json --audit-decisions docs/reference_audit_decisions.json
```

With an empty decisions file and `--no-reference-rules`, the rebuilt set has 38 pages: 33 `audit_pending` and 5
`audited_no_findings`, with `human_corrected` 0. Its manifest and every transcription are byte-identical to E2d3e.
With the committed decisions and the rule, see [E2d4b](#e2d4b-the-space-before-punctuation-rule).

The operator scripts live in `intermediates/e2d4/scripts/`:

- `e2d4_tiles.py`: the reading tiles;
- `e2d4_consolidate.py`: the proposals file and crops;
- `e2d4_packet.py`: the packet;
- `e2d4_packet_check.py`: a headless offline check of the packet's export;
- `e2d4_hypothetical.py`: the table above.

The app import bundle was written with `--export-dir intermediates/e2d4/app_bundle --page-images intermediates/e2d4/hires`
(519 crops).

## E2d4b: the space-before-punctuation rule

**The decision (maintainer, 2026-11-07).** The maintainer reviewed 103 proposals in the online review app and accepted
all of them. All were high-confidence `spacing` proposals, and almost all moved a stray space from before a mark to
after it (`ודונג ,אם` → `ודונג, אם`). He then decided: "בעברית אין רווחים לפני נקודות פיסוק", so this kind of fix is
applied always and automatically, and rare wrong fixes are accepted. Decision record:
[`planning/decisions/2026-11-07-space-before-punctuation-rule.md`](../planning/decisions/2026-11-07-space-before-punctuation-rule.md).

**The rule** (`hocrgen.reference_rules`, `space_before_punctuation.v1`; `fix_space_before_punctuation(text) ->
(text, fixes)`):

- Horizontal whitespace immediately before a single `.` `,` `:` `;` `?` or `!` is removed. If a letter directly
  follows the mark, one space is inserted after it. Line breaks are never touched.
- It fires only after a Hebrew or Latin letter (past niqqud and cantillation), a geresh, gershayim or quote mark, or a
  closing bracket.
- It never touches dot runs or spaced-dot ellipses, a mark next to another mark, a mark before a digit, slash or
  backslash, or URLs and e-mail addresses. An NFC text stays NFC.

**Where it runs.** `wikisource_eval_references` applies it to every reference it writes: the scored quality-4 pool
and the quality-3 `single_reviewer` stratum.

- **Order.** It runs after the audit decisions, so proposal offsets keep referring to the unnormalized text.
- **Protected spans.** It leaves alone any span a human decided in the audit, for example a rejected fix, and the
  excluded spans, whose offsets move with the fixes.
- **Provenance.** Each item records `reference_rules_applied` (`[{rule, fixes}]`, also on each single-reviewer line).
  The adjudication record's `reference_rules` gives the rules, the decision record and the text checksum before the
  rule. `counts.reference_rule_fixes` gives the totals.
- **Opt-out.** `--no-reference-rules` reproduces a pre-rule set.
- **Split weight.** The split stage does not apply the rule, so the split weight is unchanged.

**Rule decisions** (`reference_audit_decisions.v2`). A still-undecided proposal that the rule makes exactly on the
page text is resolved by a rule decision:

- It records `checked_by: rule`, `rule`, `decision_record` and the id `rule:<rule>:<proposal_id>`, and names no
  reviewer. A proposal that a human decided takes no rule decision.
- It counts as decided for the page state, but never as human review. It adds no `heocr:` reviewer and no
  `two_editor_validated_human_corrected` attestation. It shows as `rule_corrected` or `human_and_rule_corrected`
  and is listed apart: `applied_rule_decisions` in the provenance, `rule_decisions` in the adjudication record.
- `min_reviewers` counts human reviewers only. `apply_reference_audit` re-checks each rule decision on the page text
  and fails closed if the rule does not make that change.

`python -m hocrgen.tools.reference_audit` gained three options:

- `--add-decisions EXPORT` merges a review-app export into the decisions file.
- `--rule-coverage --snapshot-root ROOT [--write-rule-decisions]` lists, or records, the proposals the rule covers.
- `--export-dir` now leaves out every proposal a human or the rule decided.

**Effect** (tranche v5 snapshot, the 38 scored pages and the 143-page quality-3 stratum):

- **Human decisions.** 103, all `accepted` by one reviewer, on 6 pages: *Masa ba-Arav* pp. 9, 15, 18, 19 and 20,
  and *Toldoth Tannaim veAmoraim* I p. 353. Those pages are now `two_editor_validated_human_corrected`. The rule
  makes exactly 98 of these 103. The other 5 are dash spacing and two inserted spaces after `א)`, `ב)`.
- **Rule decisions.** The rule covers **13 of the 416** proposals that were still undecided: 12 `' ,'` → `', '` and
  1 `' :'` → `': '`, all high-confidence `spacing`, on *Hut ha-Meshulash* pp. 11–12 and *Dorot ha-Rishonim* pp. 9–10.
  403 proposals stay undecided, and all 33 pages with findings stay `audit_pending`.
- **Rule fixes on the scored pool.** The 38 pre-audit texts hold 113 rule fixes. 98 are at human-accepted proposals
  and 13 at rule-decided ones. One is at a pending proposal that asks for a comma instead (*Dorot ha-Rishonim* p. 9).
  One is at no proposal (*Sefer ha-Mispar* p. 2, a `test` page). After the decisions, the rule step itself makes
  these last 2 fixes.
- **Rule fixes on the quality-3 stratum.** 118 fixes on 22 of the 143 pages.

**CER** (`primary.v1`, the cached E2d3e predictions re-scored):

- *before*: the E2d4 set, with no decisions and no rule;
- *human*: the 103 human decisions only;
- *after*: the human decisions, the rule decisions and the rule.

| Engine | All 38: before | human | after | Δ | Val + test (10): before | after | Q3 stratum (diagnostic): before | after |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Tesseract 5.5.3 `heb`, psm 3 | 0.2365 | 0.2327 | 0.2321 | −0.0044 | 0.3851 | 0.3849 | 0.3971 | 0.3965 |
| R3d + R4d + A1 | 0.9010 | 0.9011 | 0.9011 | +0.0000 | 0.8661 | 0.8661 | 0.9057 | 0.9057 |
| R3g + R4d + A1 | 0.8959 | 0.8959 | 0.8959 | −0.0000 | 0.8564 | 0.8564 | 0.9016 | 0.9016 |
| R3h + R4d + A1 | 0.8985 | 0.8985 | 0.8985 | +0.0000 | 0.8534 | 0.8534 | 0.9048 | 0.9048 |
| R3h + blla (diagnostic) | 0.5777 | 0.5746 | 0.5743 | −0.0034 | 0.6556 | 0.6556 | n/a | n/a |

What the table shows:

- **Tesseract** loses 223 edits on the scored pages: 194 from the human decisions and 29 from the rule.
- **R3h + blla** loses 171.
- **The R3 + R4d + A1 line** does not move.
- **Validation + test** gains only the *Sefer ha-Mispar* fix.

**Reproduction (operator).**

```
# merge a review-app export, then record the rule decisions (both write docs/reference_audit_decisions.json)
python -m hocrgen.tools.reference_audit --add-decisions <export>/reference_audit_decisions.json
python -m hocrgen.tools.reference_audit --rule-coverage --write-rule-decisions --decided-at 2026-11-07 \
  --snapshot-root <tranche>/sources/wikisource_he_proofread/snapshot
# rebuild the reference set as above; the rule is on by default (--no-reference-rules for the E2d4 set)
```
