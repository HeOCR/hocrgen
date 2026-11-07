# Decision 2026-11-07: a stray space before a punctuation mark is always fixed

- **Date:** 2026-11-07
- **Decided by:** the maintainer
- **Status:** accepted

Context: in the E2d4 reference audit ([`docs/e2d4_reference_audit.md`](../../docs/e2d4_reference_audit.md)) the maintainer reviewed 103 proposals in the online review app and accepted all of them. They were all `spacing` proposals at high confidence. Almost all moved a stray space from before a punctuation mark to after it (`ודונג ,אם` → `ודונג, אם`). His decision, verbatim:

> בעברית אין רווחים לפני נקודות פיסוק, עד כדי כך שאפשר לעשות את התיקונים מהסוג שאישרתי תמיד, ולסבול טעויות נדירות לכיוון השני.

That is: Hebrew puts no space before a punctuation mark, so this kind of fix is applied always and automatically, and rare wrong fixes are accepted.

## Decision

1. **The rule `space_before_punctuation.v1`** (`hocrgen.reference_rules.fix_space_before_punctuation`):
   - horizontal whitespace immediately before a single `.` `,` `:` `;` `?` or `!` is removed;
   - if a letter directly follows the mark, one space is inserted after it;
   - line breaks are never touched.
2. **It is conservative.** It fires only when the character before the space is a Hebrew or Latin letter (niqqud and cantillation are skipped), a geresh, gershayim or quote mark, or a closing bracket. It never touches:
   - dot runs or spaced-dot ellipses (`...`, `. . .`);
   - a mark next to another mark;
   - a mark before a digit, a slash or a backslash;
   - a URL or e-mail address.
3. **Scope.** The rule runs on every Wikisource-derived evaluation reference: the scored quality-4 pool and the quality-3 diagnostic stratum. It runs after the audit decisions, so audit offsets keep referring to the unnormalized text. Each item records `reference_rules_applied`.
4. **Audit proposals.** A still-undecided proposal that the rule makes exactly is resolved by a rule decision (`checked_by: rule`). It counts as decided, but it is not human review: no reviewer, no human attestation, and its own page states (`rule_corrected`, `human_and_rule_corrected`).
5. **Rare wrong fixes are accepted.** One example is a space that the print does have before a mark. A span that a human decided in the audit, for example rejected, is left as the human left it.

## Consequences

- A stray space before a mark is never reviewed one by one again: the review app's bundle skips rule-decided proposals.
- The rule changes reference text, so every E2d score after it is recomputed on the new references (see [`docs/e2d4_reference_audit.md`](../../docs/e2d4_reference_audit.md)). `--no-reference-rules` reproduces a pre-rule set.
- The split stage's reference weight is unchanged: it does not apply the rule.
- Any new rule needs its own maintainer decision and its own versioned name.
