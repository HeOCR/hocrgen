from __future__ import annotations

from dataclasses import dataclass

from hocrgen.config.models import LicenseEntry, ReleaseProfile, RightsClassification, SourceConfig


@dataclass(frozen=True)
class RightsResult:
    raw_text: str
    normalized_license: str
    rights_classification: RightsClassification


def normalize_rights(
    raw_text: str | None,
    source: SourceConfig,
    licenses: dict[str, LicenseEntry],
) -> RightsResult:
    text = (raw_text or "").strip()
    if text:
        lowered = text.casefold()
        for license_entry in licenses.values():
            aliases = [license_entry.id, *license_entry.aliases]
            if any(alias.casefold() == lowered for alias in aliases):
                return RightsResult(
                    raw_text=text,
                    normalized_license=license_entry.id,
                    rights_classification=license_entry.rights_classification,
                )

        strategy_values = [value.casefold() for value in source.rights_strategy.values]
        if source.rights_strategy.type == "exact_match" and lowered in strategy_values:
            return RightsResult(
                raw_text=text,
                normalized_license=source.normalized_license,
                rights_classification=source.rights_classification,
            )
        if source.rights_strategy.type == "contains" and any(value in lowered for value in strategy_values):
            return RightsResult(
                raw_text=text,
                normalized_license=source.normalized_license,
                rights_classification=source.rights_classification,
            )

    if source.rights_strategy.type == "manual_review":
        return RightsResult(
            raw_text=text,
            normalized_license=source.normalized_license,
            rights_classification=source.rights_classification,
        )

    unknown = licenses["UNKNOWN"]
    return RightsResult(raw_text=text, normalized_license=unknown.id, rights_classification=unknown.rights_classification)


def classify_eligibility(
    rights: RightsResult,
    profile: ReleaseProfile,
    public_release_allowed: bool,
) -> tuple[str, str]:
    if rights.normalized_license == "UNKNOWN" and not profile.allow_unknown_rights:
        return "rejected", "unknown_rights"
    if not public_release_allowed:
        return "rejected", "license_not_public"
    if rights.rights_classification not in profile.allowed_rights_classifications:
        return "rejected", f"rights_classification_not_allowed:{rights.rights_classification.value}"
    return "accepted", "allowed_by_profile"
