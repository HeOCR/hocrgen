# hocrgen Normalization and Technical QA

Milestone 3 adds the first real normalization layer to `hocrgen`.

## Scope

The current normalize stage is intentionally conservative. It focuses on technical readiness rather than content curation:

- validating acquired assets exist and are non-empty
- decoding supported SVG, PNG, and JPEG inputs
- extracting width, height, file size, media type, vector/raster status, and `sha256`
- copying assets into a stable normalized layout
- generating preview copies for supported formats
- emitting deterministic QA manifests and summary reports

It does **not** yet implement:

- perceptual or semantic deduplication
- OCR/text extraction
- privacy review
- manual review queues
- release publication

## Workdir layout

The normalize stage writes artifacts under:

```text
.work/hocrgen/
  runs/
    <run_id>/
      normalize/
        normalized_items.json
        failed_items.json
        qa_report.json
        summary.json
        assets/
        thumbnails/
```

## Manifest behavior

`normalized_items.json` contains items that passed technical QA.

`failed_items.json` contains items that were normalized enough to report, but failed one or more QA checks.

Each normalized asset records:

- source asset path
- normalized asset path
- asset format
- media type
- width / height
- file size in bytes
- `sha256`
- whether the asset is vector
- normalization action
- preview generation result and path

## QA checks

The current QA rules include:

- file exists
- file is non-empty
- asset is decodable as a supported format
- dimensions are present
- minimum width / height thresholds are met
- minimum byte threshold is met
- asset format is allowed by config
- preview policy is satisfied when configured as required

Thresholds are configured in [`src/hocrgen/config/quality_thresholds.yaml`](../src/hocrgen/config/quality_thresholds.yaml).

## Preview generation

The current preview implementation is intentionally lightweight:

- for SVG, PNG, and JPEG assets, `hocrgen` writes a preview copy into `normalize/thumbnails/`
- for unsupported formats, preview generation is skipped with a structured reason

This keeps the pipeline deterministic and dependency-light while still giving later milestones a stable preview hook.
