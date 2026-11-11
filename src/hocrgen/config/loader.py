from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

import json
import yaml
from pydantic import ValidationError

from hocrgen.config.models import (
    EvalReservedUnitsRegistry,
    LicenseRegistry,
    PrivacyRules,
    PublicBetaGovernanceConfig,
    QualityThresholds,
    RealSourceContract,
    RealSourcePromotion,
    ReleaseProfile,
    SourceRegistry,
    SourceStatus,
    SyntheticTrainingWorkRegistry,
)
from hocrgen.core.errors import ConfigValidationError, StageExecutionError


@dataclass(frozen=True)
class ConfigBundle:
    source_registry: SourceRegistry
    profiles: dict[str, ReleaseProfile]
    licenses: LicenseRegistry
    quality_thresholds: QualityThresholds
    privacy_rules: PrivacyRules
    public_beta_governance: PublicBetaGovernanceConfig
    config_root: Path
    real_source_contract: RealSourceContract | None = None
    synthetic_training_works: SyntheticTrainingWorkRegistry | None = None
    # Decision 0017: P-mod evaluation units, pinned out of train and refused as training input.
    eval_reserved_units: EvalReservedUnitsRegistry | None = None
    # F8g: the materialized real tranche the tranche sources read from (``--real-tranche-root``), if any.
    real_tranche_root: Path | None = None

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


def load_quality_thresholds(config_root: Path | None = None) -> QualityThresholds:
    root = config_root or default_config_root()
    path = root / "quality_thresholds.yaml"
    return _validate("quality thresholds", QualityThresholds, load_yaml_file(path), path)


def load_privacy_rules(config_root: Path | None = None) -> PrivacyRules:
    root = config_root or default_config_root()
    path = root / "privacy_rules.yaml"
    return _validate("privacy rules", PrivacyRules, load_yaml_file(path), path)


def load_public_beta_governance(config_root: Path | None = None) -> PublicBetaGovernanceConfig:
    root = config_root or default_config_root()
    path = root / "public_beta.yaml"
    if config_root is not None and not path.exists():
        path = default_config_root() / "public_beta.yaml"
    return _validate("public beta governance", PublicBetaGovernanceConfig, load_yaml_file(path), path)


REAL_SOURCE_CONTRACT_FILE = "real_source_contract.yaml"


def load_real_source_contract(config_root: Path | None = None) -> RealSourceContract:
    """The F8g real-source composition contract; a config root without one falls back to the packaged contract."""

    root = config_root or default_config_root()
    path = root / REAL_SOURCE_CONTRACT_FILE
    if config_root is not None and not path.exists():
        path = default_config_root() / REAL_SOURCE_CONTRACT_FILE
    return _validate("real-source contract", RealSourceContract, load_yaml_file(path), path)


SYNTHETIC_TRAINING_WORKS_FILE = "synthetic_training_works.yaml"


def load_synthetic_training_works(config_root: Path | None = None) -> SyntheticTrainingWorkRegistry:
    """The F8g synthetic-training work registry; a config root without one falls back to the packaged registry."""

    root = config_root or default_config_root()
    path = root / SYNTHETIC_TRAINING_WORKS_FILE
    if config_root is not None and not path.exists():
        path = default_config_root() / SYNTHETIC_TRAINING_WORKS_FILE
    return _validate("synthetic-training work registry", SyntheticTrainingWorkRegistry, load_yaml_file(path), path)


EVAL_RESERVED_UNITS_FILE = "eval_reserved_units.yaml"


def load_eval_reserved_units(config_root: Path | None = None) -> EvalReservedUnitsRegistry:
    """The decision-0017 evaluation-reserved unit registry; a config root without one falls back to the packaged one."""

    root = config_root or default_config_root()
    path = root / EVAL_RESERVED_UNITS_FILE
    if config_root is not None and not path.exists():
        path = default_config_root() / EVAL_RESERVED_UNITS_FILE
    return _validate("eval-reserved unit registry", EvalReservedUnitsRegistry, load_yaml_file(path), path)


def load_config_bundle(config_root: Path | None = None) -> ConfigBundle:
    root = config_root or default_config_root()
    return ConfigBundle(
        source_registry=load_source_registry(root),
        profiles=load_profiles(root),
        licenses=load_license_registry(root),
        quality_thresholds=load_quality_thresholds(root),
        privacy_rules=load_privacy_rules(root),
        public_beta_governance=load_public_beta_governance(root),
        config_root=root,
        real_source_contract=load_real_source_contract(root),
        synthetic_training_works=load_synthetic_training_works(root),
        eval_reserved_units=load_eval_reserved_units(root),
    )


def validate_bundle_references(bundle: ConfigBundle) -> None:
    from hocrgen.fetchers.modern_handwriting import validate_modern_intake_source_config

    source_ids = {source.id for source in bundle.source_registry.sources}
    for profile in bundle.profiles.values():
        unknown = (set(profile.include_sources) | set(profile.exclude_sources)) - source_ids
        if unknown:
            raise ConfigValidationError(
                f"profile {profile.id} references unknown source ids",
                details=[{"profile_id": profile.id, "unknown_source_ids": sorted(unknown)}],
            )
    unknown_privacy_sources = set(bundle.privacy_rules.source_defaults) - source_ids
    if unknown_privacy_sources:
        raise ConfigValidationError(
            "privacy rules reference unknown source ids",
            details=[{"unknown_source_ids": sorted(unknown_privacy_sources)}],
        )
    for rule in bundle.privacy_rules.rules:
        unknown_rule_sources = set(rule.applies_to_sources) - source_ids
        if unknown_rule_sources:
            raise ConfigValidationError(
                f"privacy rule {rule.id} references unknown source ids",
                details=[{"privacy_rule_id": rule.id, "unknown_source_ids": sorted(unknown_rule_sources)}],
            )
    validate_real_source_contract(bundle)
    for source in bundle.source_registry.sources:
        if source.fetcher == "modern_handwriting_intake":
            try:
                validate_modern_intake_source_config(source)
            except StageExecutionError as exc:
                raise ConfigValidationError(f"modern handwriting intake validation failed for {source.id}: {exc}") from exc


# Real sources outside the composition contract: synthetic and contributor-consent sources are not real scans of
# public-domain documents, and they are governed elsewhere (synthetic cap, F3 consent policy).
NON_CONTRACT_SOURCE_FETCHERS = {"hocrsyngen_manifest", "synthetic", "modern_handwriting_intake"}


def validate_real_source_contract(bundle: ConfigBundle) -> None:
    """Bind the F8g contract to the source registry (F8g).

    Every contract entry names a registered source; a promoted or legacy entry must be an ``allowed``, default-public
    source, and a not-promoted entry must not be. Every ``allowed`` real source in any profile must have an entry, so
    a newly promoted source cannot ship outside the composition contract.
    """

    contract = bundle.real_source_contract
    if contract is None:
        return
    sources = {source.id: source for source in bundle.source_registry.sources}
    problems: list[dict[str, Any]] = []
    for entry in contract.sources:
        source = sources.get(entry.source_id)
        if source is None:
            problems.append({"source_id": entry.source_id, "problem": "unknown_source"})
            continue
        public = source.status == SourceStatus.allowed and source.default_public_release
        if entry.promotion == RealSourcePromotion.not_promoted and public:
            problems.append({"source_id": entry.source_id, "problem": "not_promoted_source_is_public"})
        if entry.promotion != RealSourcePromotion.not_promoted and not public:
            problems.append({"source_id": entry.source_id, "problem": "contract_source_not_public"})
        if entry.release_terms.licence != source.normalized_license:
            problems.append(
                {
                    "source_id": entry.source_id,
                    "problem": "release_terms_licence_mismatch",
                    "contract_licence": entry.release_terms.licence,
                    "source_licence": source.normalized_license,
                }
            )
    profiled = {source_id for profile in bundle.profiles.values() for source_id in profile.include_sources}
    for source_id in sorted(profiled):
        source = sources.get(source_id)
        if source is None or source.fetcher in NON_CONTRACT_SOURCE_FETCHERS or source.status != SourceStatus.allowed:
            continue
        if contract.entry(source_id) is None:
            problems.append({"source_id": source_id, "problem": "allowed_real_source_missing_from_contract"})
    if problems:
        raise ConfigValidationError("real-source contract does not match the source registry", details=problems)


def load_and_validate_bundle(config_root: Path | None = None) -> ConfigBundle:
    bundle = load_config_bundle(config_root)
    validate_bundle_references(bundle)
    return bundle
