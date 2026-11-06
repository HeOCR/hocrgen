# Decision 2026-11-06: the "no new human transcription campaign" rule is removed

- **Date:** 2026-11-06
- **Decided by:** the maintainer
- **Status:** accepted

## Decision

The rule that ruled out "any new human transcription campaign or labeling target" is removed. It came from the "Maintainer decisions" text in issue #86 (tender pages), which an agent wrote; #86 is now closed as unusable. In the maintainer's words:

> I don't remember dictating that rule, and anyway if I did, I remove it; we will have many new human transcription campaigns in the future, if we're lucky.

## Consequences

- `F7c` is no longer deferred on this rule. It is planned, and it needs human-attested HASH transcripts, which a new human transcription campaign may supply. See `planning/tasks/f7-hash-source-integration.md`.
- The ground-truth bar is unchanged. A transcript becomes a reference only with a human attestation (reviewer, method, base text, niqqud policy, text SHA-256) and adjudication. HTR or OCR output is never ground truth.
