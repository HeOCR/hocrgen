"""NLI IIIF manifest captures and licence-slug rights decisions (F8c).

NLI rights are keyed on the IIIF manifest ``license`` URL slug. The slug is a controlled,
language-neutral NLI rights category; only ``public-domain-free-use`` maps to ``PD-IL`` / ``open``.
The item-page display string ("Any Use Permitted") stays supported for legacy seeds that carry no
manifest capture, and when both are present they must agree.

A manifest capture is a small, checksum-pinned JSON record of one upstream manifest fetch. It keeps
the HTTP status, the upstream canvas count and checksum, and a trimmed copy of the manifest (its
rights, attribution and descriptive fields plus only the canvases whose images were cached).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from hocrgen.utils.hashing import sha256_file

NLI_CAPTURE_FORMAT = "hocrgen.nli_iiif_manifest_capture.v1"
NLI_FREE_USE_DISPLAY = "Any Use Permitted"
NLI_FREE_USE_SLUG = "public-domain-free-use"
NLI_LICENSE_HOSTS = {"www.nli.org.il", "nli.org.il"}
NLI_LICENSE_PATH_PREFIX = "/contenteditors/pages-for-terms-of-use/"
NLI_LICENSE_URL_BASE = f"https://www.nli.org.il{NLI_LICENSE_PATH_PREFIX}"
NLI_FREE_USE_LICENSE_URL = f"{NLI_LICENSE_URL_BASE}{NLI_FREE_USE_SLUG}"

# Slugs whose NLI terms restrict use to non-commercial purposes. They map to RESTRICTED-NONOPEN
# (maintainer decision 4, 2026-11-06) and never enter profile_open_v1. The Google-digitized class is
# public-domain-non-commercial-use: personal non-commercial use, no redistribution.
NLI_NON_COMMERCIAL_SLUGS = frozenset(
    {
        "public-domain-non-commercial-use",
        "nli-non-commercial",
        "nli-non-commercial-research-teaching",
        "hebrew-manuscripts-public-domain-non-commercial-copying",
        # Seen on 3 printed books in the F8c2 inventory (2026-11-06); recorded as RESTRICTED-NONOPEN, not UNKNOWN.
        "non-commercial-use-license",
    }
)

RIGHTS_BASIS_LICENSE_SLUG = "iiif_manifest_license_slug"
RIGHTS_BASIS_DISPLAY_LEGACY = "item_page_display_string"

ACCEPTED_FREE_USE_SLUG = "nli_license_slug_free_use"
REASON_MANIFEST_HTTP_PREFIX = "nli_iiif_manifest_http"
REASON_MANIFEST_MISSING = "nli_iiif_manifest_missing"
REASON_ZERO_CANVASES = "nli_iiif_manifest_zero_canvases"
REASON_LICENSE_MISSING = "nli_license_missing"
REASON_LICENSE_AMBIGUOUS = "nli_license_ambiguous"
REASON_LICENSE_URL_UNRECOGNIZED = "nli_license_url_unrecognized"
REASON_DISPLAY_MISMATCH = "nli_license_display_mismatch"
REASON_NON_COMMERCIAL = "nli_license_non_commercial"
REASON_NOT_FREE_USE = "nli_license_not_free_use"
REASON_CAPTURE_INVALID = "nli_iiif_capture_invalid"
REASON_CAPTURE_CHECKSUM_MISMATCH = "nli_iiif_capture_checksum_mismatch"
REASON_CAPTURE_ASSET_MISMATCH = "nli_iiif_capture_asset_mismatch"

RESTRICTED_LICENSE_ID = "RESTRICTED-NONOPEN"
UNKNOWN_LICENSE_ID = "UNKNOWN"

TRIMMED_MANIFEST_KEYS = (
    "@context",
    "@id",
    "@type",
    "label",
    "license",
    "attribution",
    "logo",
    "related",
    "metadata",
    "viewingHint",
)


@dataclass(frozen=True)
class NliManifestCapture:
    manifest_url: str
    http_status: int
    canvas_count: int | None
    manifest: dict[str, Any] | None
    upstream_sha256: str | None = None
    captured_on: str | None = None
    selected_canvases: list[dict[str, Any]] = field(default_factory=list)

    @property
    def license_values(self) -> list[str] | None:
        if self.manifest is None:
            return None
        return manifest_license_values(self.manifest)

    @property
    def attribution(self) -> list[str]:
        if self.manifest is None:
            return []
        value = self.manifest.get("attribution")
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str)]
        return []


@dataclass(frozen=True)
class NliRightsDecision:
    """Outcome of the NLI rights gate for one item.

    ``accepted`` is False only for a definite rejection. Legacy display-string items keep the
    pre-F8c behaviour: their ``raw_rights_text`` is the display string and the normal source rights
    strategy decides, so ``gate_reason`` is None for them.
    """

    accepted: bool
    reason: str
    rights_basis: str
    raw_rights_text: str | None
    display_rights: str | None = None
    license_url: str | None = None
    license_slug: str | None = None
    normalized_license_hint: str | None = None

    @property
    def gate_reason(self) -> str | None:
        return None if self.accepted else self.reason

    def evidence(self) -> dict[str, Any]:
        return {
            "decision": "accepted" if self.accepted else "rejected",
            "display_rights": self.display_rights,
            "license_slug": self.license_slug,
            "license_url": self.license_url,
            "reason": self.reason,
            "rights_basis": self.rights_basis,
        }


def manifest_license_values(manifest: dict[str, Any]) -> list[str]:
    value = manifest.get("license")
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = [item for item in value if isinstance(item, str)]
    else:
        values = []
    return [item.strip() for item in values if item.strip()]


def manifest_canvases(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    canvases: list[dict[str, Any]] = []
    sequences = manifest.get("sequences")
    if not isinstance(sequences, list):
        return canvases
    for sequence in sequences:
        if not isinstance(sequence, dict):
            continue
        for canvas in sequence.get("canvases") or []:
            if isinstance(canvas, dict):
                canvases.append(canvas)
    return canvases


def canvas_image_service(canvas: dict[str, Any]) -> str | None:
    for image in canvas.get("images") or []:
        if not isinstance(image, dict):
            continue
        resource = image.get("resource") or {}
        service = resource.get("service") or {}
        service_id = service.get("@id") if isinstance(service, dict) else None
        if isinstance(service_id, str) and service_id:
            return service_id
    return None


def nli_license_slug(license_url: str) -> str | None:
    """Return the NLI rights slug of a licence URL, or None when it is not an NLI terms-of-use URL."""

    parsed = urlparse(license_url.strip())
    if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in NLI_LICENSE_HOSTS:
        return None
    path = parsed.path
    if not path.startswith(NLI_LICENSE_PATH_PREFIX):
        return None
    slug = path.removeprefix(NLI_LICENSE_PATH_PREFIX).strip("/")
    if not slug or "/" in slug:
        return None
    return slug.lower()


def decide_nli_rights(
    *,
    display_rights: str | None,
    capture: NliManifestCapture | None,
) -> NliRightsDecision:
    """Decide NLI item rights from the manifest licence slug, with the display string as legacy fallback."""

    display = (display_rights or "").strip() or None
    if capture is None:
        return NliRightsDecision(
            accepted=True,
            reason="nli_display_rights_legacy",
            rights_basis=RIGHTS_BASIS_DISPLAY_LEGACY,
            raw_rights_text=display,
            display_rights=display,
        )

    def reject(reason: str, *, license_url: str | None = None, slug: str | None = None, hint: str = UNKNOWN_LICENSE_ID):
        return NliRightsDecision(
            accepted=False,
            reason=reason,
            rights_basis=RIGHTS_BASIS_LICENSE_SLUG,
            raw_rights_text=license_url or display,
            display_rights=display,
            license_url=license_url,
            license_slug=slug,
            normalized_license_hint=hint,
        )

    if capture.http_status != 200:
        return reject(f"{REASON_MANIFEST_HTTP_PREFIX}_{capture.http_status}")
    if capture.manifest is None:
        return reject(REASON_MANIFEST_MISSING)
    licenses = sorted(set(capture.license_values or []))
    if not licenses:
        return reject(REASON_LICENSE_MISSING)
    if len(licenses) > 1:
        return reject(REASON_LICENSE_AMBIGUOUS, license_url=" | ".join(licenses))
    license_url = licenses[0]
    slug = nli_license_slug(license_url)
    if slug is None:
        return reject(REASON_LICENSE_URL_UNRECOGNIZED, license_url=license_url)
    canonical_url = f"{NLI_LICENSE_URL_BASE}{slug}"
    if slug == NLI_FREE_USE_SLUG:
        if display is not None and display != NLI_FREE_USE_DISPLAY:
            return reject(REASON_DISPLAY_MISMATCH, license_url=canonical_url, slug=slug)
    else:
        if display == NLI_FREE_USE_DISPLAY:
            return reject(REASON_DISPLAY_MISMATCH, license_url=canonical_url, slug=slug)
        if slug in NLI_NON_COMMERCIAL_SLUGS:
            return reject(f"{REASON_NON_COMMERCIAL}:{slug}", license_url=canonical_url, slug=slug, hint=RESTRICTED_LICENSE_ID)
        return reject(f"{REASON_NOT_FREE_USE}:{slug}", license_url=canonical_url, slug=slug)
    if not capture.canvas_count:
        return reject(REASON_ZERO_CANVASES, license_url=canonical_url, slug=slug)
    return NliRightsDecision(
        accepted=True,
        reason=ACCEPTED_FREE_USE_SLUG,
        rights_basis=RIGHTS_BASIS_LICENSE_SLUG,
        raw_rights_text=canonical_url,
        display_rights=display,
        license_url=canonical_url,
        license_slug=slug,
    )


def capture_from_payload(payload: Any) -> NliManifestCapture:
    """Build a capture from its JSON payload, raising ValueError when the record is malformed."""

    if not isinstance(payload, dict):
        raise ValueError("capture must be a JSON object")
    if payload.get("capture_format") != NLI_CAPTURE_FORMAT:
        raise ValueError(f"capture_format must be {NLI_CAPTURE_FORMAT}")
    manifest_url = payload.get("manifest_url")
    if not isinstance(manifest_url, str) or not manifest_url:
        raise ValueError("manifest_url is required")
    http_status = payload.get("http_status")
    if not isinstance(http_status, int) or isinstance(http_status, bool):
        raise ValueError("http_status must be an integer")
    manifest = payload.get("manifest")
    if manifest is not None and not isinstance(manifest, dict):
        raise ValueError("manifest must be an object or null")
    if http_status == 200 and manifest is None:
        raise ValueError("a 200 capture must include the manifest")
    canvas_count = payload.get("canvas_count")
    if canvas_count is not None and (not isinstance(canvas_count, int) or isinstance(canvas_count, bool) or canvas_count < 0):
        raise ValueError("canvas_count must be a non-negative integer or null")
    if http_status == 200 and canvas_count is None:
        raise ValueError("a 200 capture must record canvas_count")
    selected = payload.get("selected_canvases") or []
    if not isinstance(selected, list) or not all(isinstance(item, dict) for item in selected):
        raise ValueError("selected_canvases must be a list of objects")
    return NliManifestCapture(
        manifest_url=manifest_url,
        http_status=http_status,
        canvas_count=canvas_count,
        manifest=manifest,
        upstream_sha256=payload.get("upstream_sha256"),
        captured_on=payload.get("captured_on"),
        selected_canvases=list(selected),
    )


def load_nli_manifest_capture(path: Path) -> NliManifestCapture:
    return capture_from_payload(json.loads(path.read_text(encoding="utf-8")))


def capture_asset_problems(capture: NliManifestCapture, fixture_dir: Path, fixture_assets: list[str]) -> list[str]:
    """Return why the fixture's page images are not the pinned capture's images (empty when they are).

    Every image the fixture HTML references, which is what acquisition copies, must be bound to a
    selected canvas of the capture by its relative path and match that canvas's recorded sha256.
    """

    selected = {
        entry["asset"]: entry for entry in capture.selected_canvases if isinstance(entry.get("asset"), str)
    }
    problems: list[str] = []
    for reference in fixture_assets:
        entry = selected.get(reference)
        if entry is None:
            problems.append(f"unbound:{reference}")
            continue
        pinned = entry.get("sha256")
        if not isinstance(pinned, str) or not pinned:
            problems.append(f"unpinned:{reference}")
            continue
        asset_path = (fixture_dir / reference).resolve()
        if not asset_path.exists() or sha256_file(asset_path) != pinned:
            problems.append(f"checksum:{reference}")
    return problems


def trim_manifest(manifest: dict[str, Any], keep_canvas_ids: list[str]) -> dict[str, Any]:
    """Keep the rights, attribution and descriptive fields plus only the cached canvases."""

    trimmed = {key: manifest[key] for key in TRIMMED_MANIFEST_KEYS if key in manifest}
    wanted = set(keep_canvas_ids)
    sequences = []
    for sequence in manifest.get("sequences") or []:
        if not isinstance(sequence, dict):
            continue
        kept = [canvas for canvas in sequence.get("canvases") or [] if isinstance(canvas, dict) and canvas.get("@id") in wanted]
        sequences.append({key: sequence[key] for key in ("@id", "@type") if key in sequence} | {"canvases": kept})
    trimmed["sequences"] = sequences
    return trimmed


def nli_rights_metadata(decision: NliRightsDecision, capture: NliManifestCapture | None) -> dict[str, Any]:
    """Portable rights evidence for an NLI item: no local paths, only upstream URLs and counts."""

    evidence = decision.evidence()
    if capture is not None:
        evidence.update(
            {
                "iiif_attribution": capture.attribution,
                "iiif_canvas_count": capture.canvas_count,
                "iiif_manifest_captured_on": capture.captured_on,
                "iiif_manifest_http_status": capture.http_status,
                "iiif_manifest_upstream_sha256": capture.upstream_sha256,
                "iiif_manifest_url": capture.manifest_url,
            }
        )
    return evidence
