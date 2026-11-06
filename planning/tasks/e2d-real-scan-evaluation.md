# E2d — Real-scan evaluation with separate printed and handwritten tracks

Status: **planned direction only (2026-11-06).** Nothing is implemented, and current scoring is unchanged. Parent milestone: E2, Baselines and evaluation utilities. Decision record: [`planning/decisions/2026-11-06-real-scan-evaluation-direction.md`](../decisions/2026-11-06-real-scan-evaluation-direction.md).

## Direction

- **Real scans only, eventually.** The eval set will be real scanned Hebrew text, both printed and handwritten. It will contain no synthetic text.
- **Separate printed and handwritten tracks.** Printed and handwritten Hebrew are scored and reported separately. They may also need separate pipelines (segmentation and recognition); whether they do is decided later, on evidence.
- **A transition, not a cutover.** Synthetic evaluation (E2c4–E2c7: synthetic gold as the scored set, `primary.v1` as the headline) stays in use until there is enough real reference data. Until a later E2d PR changes it, every current score, profile, view and report stays as it is.

**Naming.** These are *modality* tracks. They are distinct from the existing open/proprietary `track` field in `evaluate-references` (heocr-engine decision 0005). The final field name is open; `modality` already appears as an unreviewed-text stratum.

## What it depends on

- Human-attested real references in `benchmark_transcription_reference.v1` form (F2), adjudicated before they are scored.
- **Handwritten:** human-attested HASH transcripts through `F7c`, and later `F7e` / `benchmark_v2`. New human transcription campaigns are allowed (maintainer decision 2026-11-06), so they are a valid way to produce these.
- **Printed:** real printed Hebrew scans with attested references. Candidate sources include printed items from NLI (`printed_modern`) and BiblIA (`printed_historical`). No printed real-reference source is selected yet.
- The existing rules still hold: HTR or OCR output is never ground truth, and `benchmark_v1` membership stays frozen.

## Open questions, for later E2d PRs

1. What counts as "enough real data" per track: page count, writer and source diversity, and confidence-interval width.
2. How a page is assigned to a track (for example from `content_class`), and how mixed printed/handwritten pages are handled.
3. Whether synthetic results stay available as a labelled diagnostic after the cutover. They are never part of the scored eval set.
4. How the switch is versioned so that results before and after it are never compared as if they were alike.

## Possible sequence (not started)

- `E2d1`: a contract for the modality tracks and the cutover criteria (planning).
- `E2d2`: real-reference scored sets per track, reported beside the synthetic scored set.
- `E2d3`: retire synthetic text from the scored eval set once both tracks meet the criteria.

Each step needs its own PR and maintainer review. This stub creates no notation in the roadmap tables and changes no gate.
