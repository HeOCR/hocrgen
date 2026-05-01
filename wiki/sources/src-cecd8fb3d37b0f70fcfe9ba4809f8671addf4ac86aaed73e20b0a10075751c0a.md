---
schema_version: '1'
kind: source-summary
title: review decision.schema
page_id: src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a
status: active
review_state: machine-generated
source_refs:
- src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a
generated_by_run_ids:
- run-src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a-20260501T204813552754Z
last_generated_at: '2026-05-01T20:48:13+00:00'
last_reviewed_at: null
confidence: 1.0
related_pages: []
tags:
- source-summary
- json
provenance_links:
- source_id: src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a
  page_id: null
  run_id: null
  path_ref: state/manifests/sources/src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a.json
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: run-src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a-20260501T204813552754Z
  path_ref: null
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: null
  path_ref: schemas/review_decision.schema.json
  role: input
  note: null
contradictions: []
---

# review decision.schema

## Source

- Source ID: `src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a`
- Source type: `json`
- Registered path: `schemas/review_decision.schema.json`
- Source file: `schemas/review_decision.schema.json`

## Summary

This page records deterministic ingestion output for source `src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a`, a `json` file registered from `schemas/review_decision.schema.json`.

## Key Facts

- Source ID: `src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a`
- Source type: `json`
- Checksum: `cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a`
- Source ref: `schemas/review_decision.schema.json`
- Added at: `2026-05-01T20:48:02+00:00`
- Ingested at: `2026-05-01T20:48:13+00:00`

## Extract

```text
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://heocr.github.io/hocrgen/schemas/review_decision.schema.json",
  "title": "hocrgen review decision",
  "type": "object",
  "additionalProperties": false,
  "required": ["review_item_id", "item_id", "decision", "reviewer", "timestamp", "rationale"],
  "properties": {
    "review_item_id": { "type": "string" },
    "item_id": { "type": "string" },
    "decision": {
      "enum": ["approve", "reject", "needs_legal_review", "needs_privacy_review", "defer"]
    },
    "reviewer": { "type": "string" },
    "timestamp": { "type": "string" },
    "rationale": { "type": "string" },
    "notes": { "type": ["string", "null"] }
  }
}
```

## Provenance

- Manifest: `state/manifests/sources/src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a.json`
- Workspace source: `schemas/review_decision.schema.json`
- Run ID: `run-src-cecd8fb3d37b0f70fcfe9ba4809f8671addf4ac86aaed73e20b0a10075751c0a-20260501T204813552754Z`
- Pipeline version: `0.1.0a0`
