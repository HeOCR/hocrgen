from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hocrgen.fetchers.nli_iiif import NliManifestCapture, NliRightsDecision, capture_from_payload, decide_nli_rights, nli_rights_metadata

# Scan-rights evidence for ground-truth datasets whose page images are NLI scans. The licence decision is the F8c
# gate (`decide_nli_rights` over a pinned `hocrgen.nli_iiif_manifest_capture.v1` capture); this module only binds a
# dataset page to a canvas listed in that capture.
SCAN_RIGHTS_NOT_OPEN = "scan_rights_not_open"
SCAN_NOT_MATCHED = "scan_not_matched"


@dataclass(frozen=True)
class NliScanEvidence:
    problem: str | None
    detail: str | None = None
    decision: NliRightsDecision | None = None
    capture: NliManifestCapture | None = None

    def metadata(self) -> dict[str, Any]:
        if self.decision is None:
            return {"decision": "rejected", "reason": self.detail or self.problem}
        return nli_rights_metadata(self.decision, self.capture)


def load_scan_capture(path: Path) -> NliManifestCapture:
    """Load a pinned NLI manifest capture.

    A multi-volume NLI record can list volume sequences without inline canvases. Such a capture carries a
    `volume_sequence` block (URL, canvas count, upstream sha256) for the pinned volume, and its canvas count is the
    one the licence gate sees, so the zero-canvas rule still applies to the volume actually used.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    capture = capture_from_payload(payload)
    volume = payload.get("volume_sequence")
    if volume is None:
        return capture
    if not isinstance(volume, dict) or not isinstance(volume.get("sequence_url"), str) or not volume.get("upstream_sha256"):
        raise ValueError("volume_sequence must record sequence_url and upstream_sha256")
    count = volume.get("canvas_count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("volume_sequence.canvas_count must be a non-negative integer")
    return dataclasses.replace(capture, canvas_count=count)


def nli_scan_evidence(root: Path, scan: dict[str, Any], *, canvas_id: str | None = None) -> NliScanEvidence:
    """Check that a page's scan is an NLI free-use scan bound to a canvas of the pinned capture."""

    reference = scan.get("manifest_capture")
    if not reference:
        return NliScanEvidence(SCAN_RIGHTS_NOT_OPEN, "no_nli_manifest_capture")
    try:
        capture = load_scan_capture(root / str(reference))
    except (OSError, ValueError) as exc:
        return NliScanEvidence(SCAN_RIGHTS_NOT_OPEN, f"nli_iiif_capture_invalid: {exc}")
    decision = decide_nli_rights(display_rights=None, capture=capture)
    if not decision.accepted:
        return NliScanEvidence(SCAN_RIGHTS_NOT_OPEN, decision.reason, decision, capture)
    if scan.get("license_url") and scan["license_url"] != decision.license_url:
        return NliScanEvidence(SCAN_RIGHTS_NOT_OPEN, "scan_license_url_disagrees_with_capture", decision, capture)
    wanted = canvas_id if canvas_id is not None else scan.get("iiif_canvas")
    selected = {entry.get("canvas_id") for entry in capture.selected_canvases}
    if not wanted or wanted not in selected:
        return NliScanEvidence(SCAN_NOT_MATCHED, "canvas_not_in_capture", decision, capture)
    return NliScanEvidence(None, None, decision, capture)
