from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hocrgen.benchmark import load_benchmark_config
from hocrgen.config.loader import default_config_root
from hocrgen.core.errors import ConfigValidationError


def _benchmark_config_root(tmp_path: Path, payload: dict) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    benchmark_root = tmp_path / "benchmark_data" / "benchmark_v1"
    benchmark_root.mkdir(parents=True)
    (benchmark_root / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return config_root


def _valid_payload() -> dict:
    return {
        "approved_items": [
            {
                "benchmark_split": "train",
                "item_id": "nli_any_use_permitted:nli-ms-seed-006",
                "rationale": "real exemplar",
            }
        ],
        "benchmark_id": "benchmark_v1",
        "description": "fixture benchmark",
        "review_bar": "explicit approval required",
        "selection_policy": "representative mixed",
        "stability_policy": {"splits": "stable"},
        "version": 1,
    }


def test_load_benchmark_config_accepts_valid_repo_tracked_config(tmp_path: Path) -> None:
    config = load_benchmark_config(_benchmark_config_root(tmp_path, _valid_payload()))

    assert config.benchmark_id == "benchmark_v1"
    assert len(config.approved_items) == 1


def test_load_benchmark_config_rejects_duplicate_approved_items(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["approved_items"].append(dict(payload["approved_items"][0]))

    with pytest.raises(ConfigValidationError, match="benchmark config validation failed"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))


def test_load_benchmark_config_rejects_invalid_split(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["approved_items"][0]["benchmark_split"] = "dev"

    with pytest.raises(ConfigValidationError, match="benchmark config validation failed"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))


def test_load_benchmark_config_rejects_empty_approved_items(tmp_path: Path) -> None:
    payload = _valid_payload()
    payload["approved_items"] = []

    with pytest.raises(ConfigValidationError, match="benchmark config validation failed"):
        load_benchmark_config(_benchmark_config_root(tmp_path, payload))
