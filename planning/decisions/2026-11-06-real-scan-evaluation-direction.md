# Decision 2026-11-06: evaluation moves to real scans, with separate printed and handwritten tracks

- **Date:** 2026-11-06
- **Decided by:** the maintainer
- **Status:** accepted as a direction. It is not implemented, and current scoring is unchanged.
- **Implementation note (2026-11-06):** `E2d1` and `E2d2` add a printed modality track beside the unchanged synthetic headline; see the plan. The cutover itself (now `E2d4`, after `E2d3` refreshed the printed set on the F8g2 splits) is not implemented.
- **Plan:** [`planning/tasks/e2d-real-scan-evaluation.md`](../tasks/e2d-real-scan-evaluation.md)

## Decision

1. Evaluation should eventually run on real scanned text only, printed and handwritten. The eval set contains no synthetic text.
2. Printed Hebrew and handwritten Hebrew get separate evaluation tracks, and possibly separate pipelines.
3. Synthetic evaluation stays in use until enough real data exists. This is a transition: current scoring, profiles and reports are not changed by this decision.

## Consequences

- New evaluation work should keep printed and handwritten real references separable, for example by carrying a modality on every reference item.
- Synthetic gold remains the `evaluate-references` scored set for now. A later E2d PR, reviewed by the maintainer, will set the cutover criteria.
- The ground-truth rules are unchanged. Real references must be human-attested and adjudicated, and HTR or OCR output is never ground truth.
