from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.core.errors import ConfigValidationError


def test_load_and_validate_bundle_uses_committed_examples() -> None:
    bundle = load_and_validate_bundle()

    assert bundle.source_registry.version == 1
    assert "profile_open_v1" in bundle.profiles
    assert "profile_review_v1" in bundle.profiles
    assert len(bundle.licenses.licenses) >= 1


def test_invalid_profile_source_reference_fails(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    profile_path = config_root / "profiles" / "profile_open_v1.yaml"
    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace("nli_any_use_permitted", "unknown_source"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError):
        load_and_validate_bundle(config_root)
