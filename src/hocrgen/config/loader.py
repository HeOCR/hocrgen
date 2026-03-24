from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import json
import yaml
from pydantic import ValidationError

from hocrgen.config.models import LicenseRegistry, ReleaseProfile, SourceRegistry
from hocrgen.core.errors import ConfigValidationError


@dataclass(frozen=True)
class ConfigBundle:
    source_registry: SourceRegistry
    profiles: dict[str, ReleaseProfile]
    licenses: LicenseRegistry
    config_root: Path

    def resolve_path(self, reference: str | Path) -> Path:
        return resolve_path(reference, self.config_root)


def default_config_root() -> Path:
    return Path(files("hocrgen.config"))


def package_root() -> Path:
    return Path(files("hocrgen"))


def resolve_path(reference: str | Path, config_root: Path | None = None) -> Path:
    raw = Path(reference) if isinstance(reference, Path) else reference
    if isinstance(raw, Path):
        if raw.is_absolute():
            return raw
        if config_root is None:
            raise ConfigValidationError(f"cannot resolve relative path without config root: {raw}")
        return (config_root / raw).resolve()

    if raw.startswith("package://"):
        return (package_root() / raw.removeprefix("package://")).resolve()
    path = Path(raw)
    if path.is_absolute():
        return path
    if config_root is None:
        raise ConfigValidationError(f"cannot resolve relative path without config root: {reference}")
    return (config_root / path).resolve()


def load_yaml_file(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise ConfigValidationError(f"missing config file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigValidationError(f"invalid YAML in {path}: {exc}") from exc


def load_json_file(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ConfigValidationError(f"missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigValidationError(f"invalid JSON in {path}: {exc}") from exc


def _validate(model_name: str, model_type: type, data: Any, source_path: Path):
    try:
        return model_type.model_validate(data)
    except ValidationError as exc:
        raise ConfigValidationError(f"{model_name} validation failed for {source_path}", details=exc.errors()) from exc


def load_source_registry(config_root: Path | None = None) -> SourceRegistry:
    root = config_root or default_config_root()
    path = root / "sources.yaml"
    return _validate("source registry", SourceRegistry, load_yaml_file(path), path)


def load_license_registry(config_root: Path | None = None) -> LicenseRegistry:
    root = config_root or default_config_root()
    path = root / "licenses.yaml"
    return _validate("license registry", LicenseRegistry, load_yaml_file(path), path)


def load_profiles(config_root: Path | None = None) -> dict[str, ReleaseProfile]:
    root = config_root or default_config_root()
    profiles_dir = root / "profiles"
    if not profiles_dir.exists():
        raise ConfigValidationError(f"missing profiles directory: {profiles_dir}")

    profiles: dict[str, ReleaseProfile] = {}
    profile_paths: dict[str, Path] = {}
    for path in sorted(profiles_dir.glob("*.yaml")):
        profile = _validate("release profile", ReleaseProfile, load_yaml_file(path), path)
        if profile.id in profiles:
            original_path = profile_paths[profile.id]
            raise ConfigValidationError(
                f'duplicate profile id "{profile.id}" in {path} (already defined in {original_path})'
            )
        profiles[profile.id] = profile
        profile_paths[profile.id] = path

    if not profiles:
        raise ConfigValidationError(f"no release profiles found in {profiles_dir}")
    return profiles


def load_config_bundle(config_root: Path | None = None) -> ConfigBundle:
    root = config_root or default_config_root()
    return ConfigBundle(
        source_registry=load_source_registry(root),
        profiles=load_profiles(root),
        licenses=load_license_registry(root),
        config_root=root,
    )


def validate_bundle_references(bundle: ConfigBundle) -> None:
    source_ids = {source.id for source in bundle.source_registry.sources}
    for profile in bundle.profiles.values():
        unknown = (set(profile.include_sources) | set(profile.exclude_sources)) - source_ids
        if unknown:
            raise ConfigValidationError(
                f"profile {profile.id} references unknown source ids",
                details=[{"profile_id": profile.id, "unknown_source_ids": sorted(unknown)}],
            )


def load_and_validate_bundle(config_root: Path | None = None) -> ConfigBundle:
    bundle = load_config_bundle(config_root)
    validate_bundle_references(bundle)
    return bundle
