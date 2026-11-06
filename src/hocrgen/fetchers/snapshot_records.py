from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_yaml_file
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError


def snapshot_root_setting(source: SourceConfig, bundle: ConfigBundle, setting: str) -> Path:
    """Resolve a packaged snapshot root named by `settings.extra.<setting>`."""

    reference = source.settings.extra.get(setting)
    if not isinstance(reference, str) or not reference:
        raise StageExecutionError(f"{source.id} requires settings.extra.{setting}")
    return bundle.resolve_path(reference)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_snapshot(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load a pinned snapshot descriptor (`snapshot.yaml`) and its `entries.jsonl` records."""

    snapshot = load_yaml_file(root / "snapshot.yaml")
    return snapshot, load_jsonl(root / str(snapshot.get("entries_path", "entries.jsonl")))
