from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from hocrgen.config.loader import ConfigBundle
from hocrgen.config.models import SourceConfig
from hocrgen.manifests.models import AcquiredItemRecord, CandidateRecord, EnrichedCandidateRecord, ItemRecord


@dataclass(frozen=True)
class StageOptions:
    source_filter: set[str] | None = None
    max_items: int | None = None
    synthetic_seed: int | None = None


class SourceAdapter(Protocol):
    def discover_candidates(
        self,
        source: SourceConfig,
        bundle: ConfigBundle,
        options: StageOptions,
    ) -> list[CandidateRecord]: ...

    def fetch_candidate_metadata(
        self,
        source: SourceConfig,
        bundle: ConfigBundle,
        candidates: Iterable[CandidateRecord],
        options: StageOptions,
    ) -> list[EnrichedCandidateRecord]: ...

    def acquire_items(
        self,
        source: SourceConfig,
        bundle: ConfigBundle,
        items: Iterable[ItemRecord],
        output_dir,
        options: StageOptions,
    ) -> list[AcquiredItemRecord]: ...
