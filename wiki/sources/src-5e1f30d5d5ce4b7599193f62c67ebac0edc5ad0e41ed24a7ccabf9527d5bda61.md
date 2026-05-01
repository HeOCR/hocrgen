---
schema_version: '1'
kind: source-summary
title: models
page_id: src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61
status: active
review_state: machine-generated
source_refs:
- src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61
generated_by_run_ids:
- run-src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61-20260501T204813591698Z
last_generated_at: '2026-05-01T20:48:13+00:00'
last_reviewed_at: null
confidence: 1.0
related_pages: []
tags:
- source-summary
- py
provenance_links:
- source_id: src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61
  page_id: null
  run_id: null
  path_ref: state/manifests/sources/src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61.json
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: run-src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61-20260501T204813591698Z
  path_ref: null
  role: generated-from
  note: null
- source_id: null
  page_id: null
  run_id: null
  path_ref: src/hocrgen/config/models.py
  role: input
  note: null
contradictions: []
---

# models

## Source

- Source ID: `src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61`
- Source type: `py`
- Registered path: `src/hocrgen/config/models.py`
- Source file: `src/hocrgen/config/models.py`

## Summary

This page records deterministic ingestion output for source `src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61`, a `py` file registered from `src/hocrgen/config/models.py`.

## Key Facts

- Source ID: `src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61`
- Source type: `py`
- Checksum: `5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61`
- Source ref: `src/hocrgen/config/models.py`
- Added at: `2026-05-01T20:48:04+00:00`
- Ingested at: `2026-05-01T20:48:13+00:00`

## Extract

```text
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SourceStatus(str, Enum):
    allowed = "allowed"
    review_only = "review_only"
    blocked = "blocked"


class SourceOperationalStatus(str, Enum):
    active = "active"
    frozen = "frozen"
    degraded = "degraded"


class RightsClassification(str, Enum):
    open = "open"
    open_with_attribution = "open_with_attribution"
    sharealike = "sharealike"
    restricted_review_only = "restricted_review_only"
    blocked = "blocked"


class PublishTarget(str, Enum):
    huggingface = "huggingface"
    github_dataset_repo = "github_dataset_repo"


class RasterFormat(str, Enum):
    png = "png"
    jpeg = "jpeg"


class PreviewGenerationMode(str, Enum):
    copy_if_supported = "copy_if_supported"
    skip = "skip"


class PrivacyFlag(str, Enum):
    clear = "clear"
    possible_personal_data = "possible_personal_data"
    needs_review = "needs_review"
    blocked_sensitive = "blocked_sensitive"


class RightsStrategy(ConfigBaseModel):
    type: Literal["exact_match", "contains", "manual_review"]
    values: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_values(self) -> "RightsStrategy":
        if self.type != "manual_review" and not self.values:
            raise ValueError("rights_strategy.values must not be empty unless type is manual_review")
        return self


class SourceSettings(ConfigBaseModel):
    seed_manifest: str | None = None
    records_path: str | None = None
    synthetic_batch_size: int | None = Field(default=None, ge=1)
    synthetic_seed: int | None = None
    template_ids: list[str] = Field(default_factory=list)
    font_manifest: str | None = None
    text_corpus_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SourceHealthExpectations(ConfigBaseModel):
    min_candidates: int | None = Field(default=None, ge=0)
    min_assets: int | None = Field(default=None, ge=0)
```

## Provenance

- Manifest: `state/manifests/sources/src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61.json`
- Workspace source: `src/hocrgen/config/models.py`
- Run ID: `run-src-5e1f30d5d5ce4b7599193f62c67ebac0edc5ad0e41ed24a7ccabf9527d5bda61-20260501T204813591698Z`
- Pipeline version: `0.1.0a0`
