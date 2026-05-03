# Benchmark Ground-Truth Guidelines

These guidelines define the human-facing convention for future benchmark references in `hocrgen`. They do not make transcriptions or layout labels mandatory for current public or alpha exports. F2b remains planned for runtime ingestion, adjudication artifacts, and benchmark versioning gates.

## Scope

Benchmark ground truth is the reviewed reference layer used to evaluate OCR/HTR output against selected benchmark items. It is separate from source metadata, review decisions, release eligibility, and synthetic-generation metadata.

The benchmark ground-truth package has three parts:

- transcription references: normalized text for a benchmark item
- layout-label references: page, region, line, and optional word/reference geometry
- a reference manifest: a versioned index that links benchmark items to their references and review status

Public references are intended for release with public benchmark examples. Private adjudication notes can record reviewer discussion, uncertainty rationale, or sensitive source observations and must not be exported by default. Future hidden references may support private evaluation splits, but they must be distinguished from public references in manifests and release notes.

## Transcription Guidelines

### Text Order

Store text in Unicode logical order, not visual order. Hebrew and other right-to-left runs should appear in the order a reader would type and edit them. Do not reverse complete Hebrew lines to match their visual appearance in an image.

For mixed-language content, keep each script fragment in logical order and rely on Unicode bidi behavior for display. If the visual layout is ambiguous, preserve the most plausible reading order and add a review flag rather than encoding visual-order workarounds.

### Normalization

Transcription files must use UTF-8 text normalized to Unicode NFC. Do not use compatibility normalization that changes meaningful characters, punctuation, or presentation choices.

Normalize only the transcription text. Preserve the source image and source metadata as evidence, and record any correction or editorial decision in review/adjudication status rather than overwriting provenance.

### RTL and Bidi Behavior

Do not insert left-to-right or right-to-left marks unless they are necessary to preserve a meaningful mixed-direction sequence that cannot otherwise be read correctly by standard Unicode bidi handling. When direction marks are used, record that choice in the reference metadata or review notes.

Line and region order should follow reading order, not file-system order, capture order, or visual left-to-right sorting.

### Niqqud

If niqqud is visibly present and legible, transcribe it. If the mark is absent, do not infer it from context. If a mark is present but uncertain, keep the base letter and mark the span as uncertain in the reference metadata rather than guessing.

Do not add niqqud to normalize spelling, grammar, or modern readability. Do not remove visible niqqud only because a downstream model may ignore it.

### Punctuation

Transcribe visible punctuation as written. Preserve source punctuation choices where they are meaningful, including repeated punctuation, quote marks, parentheses, and end-of-line punctuation.

Do not modernize punctuation. If a mark may be punctuation, damage, or an ornament, mark the span as uncertain and send it to review.

### Numerals

Preserve the visible numeral system:

- Hebrew numerals remain Hebrew numerals.
- Arabic-script numerals remain Arabic-script numerals.
- Latin digits remain Latin digits.

Do not convert between numeral systems, expand values, or silently normalize dates. If a sequence mixes digits, separators, and Hebrew abbreviation marks, transcribe the visible characters in logical order.

### Latin Fragments and Mixed-Language Text

Transcribe Latin fragments as visible text, preserving case when legible. Mixed Hebrew, Arabic, Latin, and numeric text should remain in a single logical-order transcription unless the page structure clearly separates it into distinct regions or lines.

Foreign-language words should not be translated. If script identity is uncertain, keep the visible characters when possible and flag for review.

### Abbreviations

Transcribe abbreviations as written. Do not expand abbreviations, acronyms, contractions, titles, honorifics, or Hebrew abbreviation marks in the canonical transcription.

Expansions may be captured later as private adjudication notes or optional editorial metadata, but they are not part of the benchmark reference string used for primary OCR/HTR scoring.

### Uncertain, Illegible, Damaged, Deleted, or Marginal Text

The canonical transcription should contain only text that reviewers can justify from the image. Use structured span metadata for uncertain or non-standard content:

- `uncertain`: plausible but not fully confident
- `illegible`: visible text is present but cannot be read
- `damaged`: source damage affects the reading
- `deleted`: text appears intentionally crossed out or erased
- `marginal`: text is outside the main body flow

Do not invent replacement text for illegible spans. If a deletion remains readable, transcribe it and mark it as deleted. If marginal text has a clear reading position, include it in reading order and mark it as marginal; otherwise put it in a separate region with an explicit review flag.

### Line and Page Boundaries

Represent line breaks as reference structure, not by relying only on free-form newlines. A page-level text view may include newline separators for readability, but line-level references are the authority for boundaries.

Do not join words across a line or page boundary unless the source visibly indicates continuation. Multi-page items should preserve page order, page identifiers, and page-local line order.

## Layout-Label Guidelines

### Label Levels

Layout labels should support these levels:

- page: one record per page image
- region: logical blocks such as body text, margin notes, headings, tables, stamps, or non-text areas
- line: baseline text units used for reading order and transcription alignment
- word/reference: optional finer labels for high-value references, difficult mixed-direction text, or future hidden evaluation

Line-level geometry is the minimum useful target for benchmark OCR/HTR alignment. Word/reference-level labels are optional and should not block public references unless a benchmark task explicitly requires them.

### Coordinate System and Units

Coordinates are measured in source-image pixel units after the normalized release asset is created. The origin is the top-left corner of the page image. `x` increases to the right and `y` increases downward.

Each label should declare the page asset it references, the image width and height used for annotation, and whether geometry uses bounding boxes, polygons, baselines, or a combination. Coordinates must not depend on local viewer state, crop tools, screen scaling, or absolute local paths.

### Reading Order

Every page, region, and line label should carry a deterministic reading-order index. Reading order follows the transcription policy: logical reading sequence, not visual left-to-right sorting.

When marginalia, side notes, headers, footers, tables, stamps, or mixed-direction fragments interrupt the page, use region-level structure and review flags to explain the chosen order.

### Multi-Page Items

Multi-page items must keep stable page ids and page-local coordinates. Item-level reading order combines page order with page-local region and line order.

Do not merge geometry across page boundaries. Cross-page continuations should be represented as separate page-local labels with a shared continuation or relation field when needed.

### Uncertainty and Review Flags

Layout labels can carry the same uncertainty vocabulary used for transcription spans. They may also use geometry-specific flags such as:

- `partial`: label covers only part of the visible text
- `estimated`: bounds are approximate
- `overlap`: regions or lines overlap materially
- `needs_adjudication`: reviewers disagree or evidence is insufficient

Uncertain geometry should remain reviewable; it should not be promoted to final public references without adjudication.

### Portability Constraints

All public layout-label references must use release-relative paths. Do not store absolute local filesystem paths, user-specific paths, external viewer URLs, or temporary workdir paths.

Geometry should be reproducible from exported release assets and manifests alone. If a label depends on a derived image, the derived image path and checksum must be release-relative and manifest-visible.

## Reference-Manifest Contract

The documented contract name for the first benchmark reference manifest is `benchmark_reference_manifest.v1`. `F2a` defines the contract at the documentation level; `F2b` should implement ingestion, validation, adjudication artifacts, and versioning gates.

A manifest should contain:

- `schema_version`: `benchmark_reference_manifest.v1`
- `benchmark_id`: for example `benchmark_v1`
- `reference_manifest_id`: stable id for this reference set
- `release_id` or release compatibility range when references are tied to exported assets
- `items`: one entry per referenced benchmark item

Each item entry should contain:

- `item_id`: hocrgen item id, matching benchmark and item manifests
- `source_id` and `source_item_id`: source identity linkage
- `benchmark_split`: the committed benchmark split when applicable
- `public_reference_status`: `not_available`, `draft`, `reviewed`, `adjudicated`, `corrected`, or `retired`
- `visibility`: `public`, `private_adjudication`, or `hidden_reference`
- `transcription_reference`: nullable release-relative path to the transcription reference
- `layout_label_references`: release-relative paths to layout-label references
- `reviewers`: reviewer ids or handles suitable for repository policy
- `adjudication_status`: `not_started`, `in_review`, `needs_adjudication`, `adjudicated`, or `blocked`
- `correction_of`: nullable prior reference id when correcting a published reference
- `superseded_by`: nullable replacement reference id
- `change_reason`: concise human-readable reason for corrections, retirement, or status changes

Example shape:

```json
{
  "schema_version": "benchmark_reference_manifest.v1",
  "benchmark_id": "benchmark_v1",
  "reference_manifest_id": "benchmark_v1_refs_0001",
  "items": [
    {
      "item_id": "nli_any_use_permitted:nli-ms-001",
      "source_id": "nli_any_use_permitted",
      "source_item_id": "nli-ms-001",
      "benchmark_split": "validation",
      "visibility": "public",
      "public_reference_status": "reviewed",
      "transcription_reference": "references/benchmark_v1/nli-ms-001/transcription.json",
      "layout_label_references": [
        "references/benchmark_v1/nli-ms-001/layout.json"
      ],
      "reviewers": ["reviewer-id"],
      "adjudication_status": "in_review",
      "correction_of": null,
      "superseded_by": null,
      "change_reason": "initial reviewed reference"
    }
  ]
}
```

### Public, Private, and Hidden References

Public references can ship with benchmark examples and may be used by downstream users for evaluation. Private adjudication notes can store reviewer disagreement, source-sensitive discussion, or temporary decision context; they must not be exposed as public release payloads. Hidden references are reserved for future private evaluation and must not be mixed with public references in the same scoring path unless the benchmark card explains the protocol.

### Corrections and Versioning

Published reference corrections must be auditable. A corrected reference should keep the old reference addressable, record `correction_of`, explain `change_reason`, and update `superseded_by` on the old reference when available.

Removing or retiring a benchmark reference is a benchmark-versioning event. It should not silently change benchmark scores, benchmark membership, or release portability. `F2b` should add the runtime gates that enforce these expectations.

## Non-Goals for F2a

This document does not:

- implement benchmark-reference ingestion
- implement adjudication storage or workflow automation
- make annotations mandatory for public or alpha exports
- change `benchmark_v1` membership
- add OCR engines, model training, LLM annotation, network workflows, or broad annotation tooling
- relax rights, privacy, review, dedupe, split, benchmark, synthetic-cap, or export-portability gates
