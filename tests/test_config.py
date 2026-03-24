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


def test_duplicate_profile_ids_fail(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    duplicate_profile = config_root / "profiles" / "profile_open_duplicate.yaml"
    duplicate_profile.write_text(
        (
            "id: profile_open_v1\n"
            "description: duplicate id fixture\n"
            "include_sources:\n"
            "  - nli_any_use_permitted\n"
            "exclude_sources: []\n"
            "allowed_rights_classifications:\n"
            "  - open\n"
            "synthetic_fraction_max: 0.0\n"
            "privacy_mode: conservative\n"
            "publish_targets: []\n"
            "split_policy:\n"
            "  train: 0.8\n"
            "  validation: 0.1\n"
            "  test: 0.1\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match='duplicate profile id "profile_open_v1"'):
        load_and_validate_bundle(config_root)
