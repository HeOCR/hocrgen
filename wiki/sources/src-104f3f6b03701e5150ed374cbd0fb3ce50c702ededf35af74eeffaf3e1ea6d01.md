---
schema_version: '1'
kind: source-summary
title: merge
page_id: src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01
status: active
review_state: machine-generated
source_refs:
- src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01
generated_by_run_ids:
- run-src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01-20260501T204813615762Z
last_generated_at: '2026-05-01T20:48:13+00:00'
last_reviewed_at: null
confidence: 1.0
related_pages: []
tags:
- source-summary
- py
provenance_links:
- source_id: src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01
  page_id: null
  run_id: null
  path_ref: state/manifests/sources/src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01.json
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: run-src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01-20260501T204813615762Z
  path_ref: null
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: null
  path_ref: src/hocrgen/review/merge.py
  role: input
  note: null
contradictions: []
---

# merge

## Source

- Source ID: `src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01`
- Source type: `py`
- Registered path: `src/hocrgen/review/merge.py`
- Source file: `src/hocrgen/review/merge.py`

## Summary

This page records deterministic ingestion output for source `src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01`, a `py` file registered from `src/hocrgen/review/merge.py`.

## Key Facts

- Source ID: `src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01`
- Source type: `py`
- Checksum: `104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01`
- Source ref: `src/hocrgen/review/merge.py`
- Added at: `2026-05-01T20:48:05+00:00`
- Ingested at: `2026-05-01T20:48:13+00:00`

## Extract

```text
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from hocrgen.config.loader import default_config_root, load_json_file
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    PrivacyScannedItemRecord,
    ReviewDecisionAuditRecord,
    ReviewDecisionRecord,
    ReviewOverrideRecord,
    ReviewQueueRecord,
)


@dataclass(frozen=True)
class ReviewData:
    root: Path
    manual_decisions: list[ReviewDecisionRecord]
    allowlist: list[ReviewOverrideRecord]
    blocklist: list[ReviewOverrideRecord]


@dataclass(frozen=True)
class ReviewMergeOutputs:
    release_ready_items: list[PrivacyScannedItemRecord]
    unresolved_items: list[PrivacyScannedItemRecord]
    rejected_items: list[PrivacyScannedItemRecord]
    decision_audit: list[ReviewDecisionAuditRecord]
    summary: dict[str, object]


def _review_data_root_candidates(config_root: Path) -> list[Path]:
    config_root = config_root.resolve()
    candidates: list[Path] = []

    for parent in (config_root, *config_root.parents):
        candidate = parent / "review_data"
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def resolve_review_data_root(config_root: Path, explicit_config_root: Path | None = None) -> Path:
    resolved_config_root = explicit_config_root.resolve() if explicit_config_root is not None else config_root.resolve()

    for candidate in _review_data_root_candidates(resolved_config_root):
        if candidate.exists():
            return candidate

    if resolved_config_root == default_config_root().resolve():
        return resolved_config_root.parents[2] / "review_data"
    return resolved_config_root.parent / "review_data"


def load_review_data(config_root: Path, explicit_config_root: Path | None = None) -> ReviewData:
    root = resolve_review_data_root(config_root, explicit_config_root)
    review_data = ReviewData(
        root=root,
        manual_decisions=_load_records(root / "manual_decisions", ReviewDecisionRecord),
        allowlist=_load_records(root / "allowlists", ReviewOverrideRecord),
        blocklist=_load_records(root / "blocklists", ReviewOverrideRecord),
    )
    _validate_review_data(review_data)
    return review_data


def validate_review_data(config_root: Path, explicit_config_root: Path | None = None) -> ReviewData:
    return load_review_data(config_root, explicit_config_root)


def merge_review_decisions(
    *,
    release_ready_items: list[PrivacyScannedItemRecord],
    review_required_items: list[PrivacyScannedItemRecord],
    review_queue: list[ReviewQueueRecord],
```

## Provenance

- Manifest: `state/manifests/sources/src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01.json`
- Workspace source: `src/hocrgen/review/merge.py`
- Run ID: `run-src-104f3f6b03701e5150ed374cbd0fb3ce50c702ededf35af74eeffaf3e1ea6d01-20260501T204813615762Z`
- Pipeline version: `0.1.0a0`
