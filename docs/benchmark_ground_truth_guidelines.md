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

Primary benchmark scoring should use the canonical transcription text after applying the reference `scoring_policy`. The default policy is:

- `uncertain`: include the visible text in canonical scoring, and report the span in a separate uncertainty count.
- `illegible`: exclude the span from primary scoring unless the benchmark task explicitly scores illegibility detection.
- `damaged`: include readable text in canonical scoring and retain the damage flag for secondary reporting.
- `deleted`: exclude from primary OCR/HTR scoring by default, because deleted text is not part of the final reading text; keep it available for specialist evaluation.
- `marginal`: include in primary scoring only when it has an explicit reading-order position; otherwise score it separately.

Reference files must make these choices explicit with span metadata so evaluators can reproduce the masking or inclusion decision instead of guessing from free text.

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

## Transcription Reference Contract

The first documented transcription reference shape is `benchmark_transcription_reference.v1`. `F2b` should validate this shape before a reference can be treated as benchmark-ready.

A transcription reference should contain:

- `schema_version`: `benchmark_transcription_reference.v1`
- `item_id`, `source_id`, and `source_item_id`: matching the benchmark reference manifest item
- `normalization`: at minimum `{ "unicode": "NFC", "text_order": "logical" }`
- `language_scripts`: script/language declarations used by the reference
- `scoring_policy`: explicit include/exclude behavior for uncertain, illegible, damaged, deleted, and marginal spans
- `pages`: ordered page records with page ids and optional page-level text views
- `lines`: page-local or item-global line records with stable ids, page ids, reading-order indexes, canonical text, and optional linked layout line ids
- `spans`: structured annotations anchored by line id and character offsets, with status values such as `uncertain`, `illegible`, `damaged`, `deleted`, and `marginal`
- `review`: reviewer/adjudication status for the transcription reference itself

Character offsets are counted over the NFC-normalized canonical line text. If a span is excluded from primary scoring and has no canonical characters, the span must still identify its line, its insertion position, its status, and a human-readable note. Do not represent excluded illegible text by inventing placeholder glyphs in the canonical text.

Example shape:

```json
{
  "schema_version": "benchmark_transcription_reference.v1",
  "item_id": "nli_any_use_permitted:nli-ms-001",
  "source_id": "nli_any_use_permitted",
  "source_item_id": "nli-ms-001",
  "normalization": {
    "unicode": "NFC",
    "text_order": "logical"
  },
  "language_scripts": [
    {
      "language": "he",
      "script": "Hebr",
      "direction": "rtl"
    }
  ],
  "scoring_policy": {
    "uncertain": "include_primary_and_report",
    "illegible": "exclude_primary",
    "damaged": "include_readable_and_report",
    "deleted": "exclude_primary",
    "marginal": "include_when_ordered_else_separate"
  },
  "pages": [
    {
      "page_id": "page-1",
      "reading_order": 1
    }
  ],
  "lines": [
    {
      "line_id": "line-1",
      "page_id": "page-1",
      "reading_order": 1,
      "text": "\u05e9\u05dc\u05d5\u05dd 123",
      "layout_line_id": "layout-line-1"
    }
  ],
  "spans": [
    {
      "span_id": "span-1",
      "line_id": "line-1",
      "start": 0,
      "end": 4,
      "status": "uncertain",
      "scoring": "include_primary_and_report",
      "note": "letters are faint but readable"
    }
  ],
  "review": {
    "status": "in_review",
    "reviewers": ["reviewer-id"]
  }
}
```

## Layout Reference Contract

The first documented layout reference shape is `benchmark_layout_reference.v1`. `F2b` should validate this shape before a layout reference can be treated as benchmark-ready.

A layout reference should contain:

- `schema_version`: `benchmark_layout_reference.v1`
- `item_id`, `source_id`, and `source_item_id`: matching the benchmark reference manifest item
- `coordinate_system`: pixel units, top-left origin, and axis direction declarations
- `assets`: one record per annotated release asset, with release-relative path, checksum, width, height, and page id
- `regions`: optional page-local region records with stable ids, page ids, labels, reading-order indexes, geometry, and flags
- `lines`: line records with stable ids, page ids, optional region ids, reading-order indexes, geometry, optional baseline geometry, optional linked transcription line ids, and flags
- `words` or `references`: optional finer geometry records when the benchmark task needs them
- `review`: reviewer/adjudication status for the layout reference itself

Geometry records should declare whether they use `bbox`, `polygon`, `baseline`, or a combination. Bounding boxes use `{ "x", "y", "width", "height" }` in pixel units. Polygons use ordered `{ "x", "y" }` points in the same coordinate system. The referenced asset checksum and dimensions are part of the reference contract so F2b can detect stale labels after asset regeneration or export changes.

Example shape:

```json
{
  "schema_version": "benchmark_layout_reference.v1",
  "item_id": "nli_any_use_permitted:nli-ms-001",
  "source_id": "nli_any_use_permitted",
  "source_item_id": "nli-ms-001",
  "coordinate_system": {
    "units": "px",
    "origin": "top_left",
    "x_axis": "right",
    "y_axis": "down"
  },
  "assets": [
    {
      "asset_id": "page-1-image",
      "page_id": "page-1",
      "path": "assets/nli-ms-001/page-1.jpg",
      "sha256": "sha256-placeholder",
      "width": 1200,
      "height": 1800
    }
  ],
  "regions": [
    {
      "region_id": "region-1",
      "page_id": "page-1",
      "label": "body",
      "reading_order": 1,
      "geometry": {
        "type": "bbox",
        "bbox": {
          "x": 100,
          "y": 200,
          "width": 900,
          "height": 600
        }
      },
      "flags": []
    }
  ],
  "lines": [
    {
      "line_id": "layout-line-1",
      "page_id": "page-1",
      "region_id": "region-1",
      "reading_order": 1,
      "transcription_line_id": "line-1",
      "geometry": {
        "type": "bbox",
        "bbox": {
          "x": 120,
          "y": 220,
          "width": 700,
          "height": 52
        }
      },
      "flags": ["estimated"]
    }
  ],
  "review": {
    "status": "in_review",
    "reviewers": ["reviewer-id"]
  }
}
```

## Reference-Manifest Contract

The documented contract name for the first benchmark reference manifest is `benchmark_reference_manifest.v1`. `F2a` defines the contract at the documentation level; `F2b` should implement ingestion, validation, adjudication artifacts, and versioning gates.

A manifest should contain:

- `schema_version`: `benchmark_reference_manifest.v1`
- `benchmark_id`: for example `benchmark_v1`
- `reference_manifest_id`: stable id for this reference set
- `release_id` or release compatibility range when references are tied to exported assets
- `reference_contracts`: the expected transcription and layout reference schema versions
- `items`: one entry per referenced benchmark item

Each item entry should contain:

- `item_id`: hocrgen item id, matching benchmark and item manifests
- `source_id` and `source_item_id`: source identity linkage
- `benchmark_split`: the committed benchmark split when applicable
- `public_reference_status`: `not_available`, `draft`, `reviewed`, `adjudicated`, `corrected`, or `retired`
- `visibility`: `public`, `private_adjudication`, or `hidden_reference`
- `transcription_reference`: nullable object with release-relative `path`, `schema_version`, and optional checksum
- `layout_label_references`: objects with release-relative `path`, `schema_version`, optional checksum, and declared page ids
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
  "reference_contracts": {
    "transcription": "benchmark_transcription_reference.v1",
    "layout": "benchmark_layout_reference.v1"
  },
  "items": [
    {
      "item_id": "nli_any_use_permitted:nli-ms-001",
      "source_id": "nli_any_use_permitted",
      "source_item_id": "nli-ms-001",
      "benchmark_split": "validation",
      "visibility": "public",
      "public_reference_status": "reviewed",
      "transcription_reference": {
        "path": "references/benchmark_v1/nli-ms-001/transcription.json",
        "schema_version": "benchmark_transcription_reference.v1",
        "sha256": "sha256-placeholder"
      },
      "layout_label_references": [
        {
          "path": "references/benchmark_v1/nli-ms-001/layout.json",
          "schema_version": "benchmark_layout_reference.v1",
          "sha256": "sha256-placeholder",
          "page_ids": ["page-1"]
        }
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
