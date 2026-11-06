"""Work-level leakage keys for real items (F8g).

A source group (``metadata.source_group_id``) keeps one source's pages of one work together: a Wikisource Index,
a YidTakNL work, the BGU Pinkas manuscript, a Reshumot booklet, a Knesset protocol. A work group goes further and
ties items of *different* sources that show the same physical edition or scan, or the same writer:

- ``nli_record:<id>`` (the id as the source records it): items whose scans come from one NLI record (an NLI seed, the YidTakNL pages and the BGU
  Pinkas pages matched to NLI canvases), so an NLI book and a dataset's pages of it never straddle splits;
- ``commons_file:<sha1>``: Wikisource pages of one Commons scan file (also any other source on that file);
- ``writer:<id>``: HASH writer groups (F7), so a writer's real letters never straddle splits.

These keys also match the synthetic-training registry (``config/synthetic_training_works.yaml``).
"""

from __future__ import annotations

import re
from typing import Any

NLI_RECORD_PATTERN = re.compile(r"NNL_ALEPH(\d{6,})")
NLI_HOLDING = "National Library of Israel"


def item_work_group_keys(item: Any) -> list[str]:
    metadata = item.metadata if isinstance(getattr(item, "metadata", None), dict) else {}
    keys: set[str] = set()
    for key in metadata.get("work_group_ids") or []:
        if isinstance(key, str) and ":" in key:
            keys.add(key)
    record_id = metadata.get("scan_record_id")
    if record_id and (metadata.get("scan_holding_institution") == NLI_HOLDING or "nli.org.il" in str(metadata.get("scan_license_url") or "")):
        keys.add(f"nli_record:{str(record_id).strip()}")
    if item.source_id == "nli_any_use_permitted":
        match = NLI_RECORD_PATTERN.search(str(getattr(item, "source_url", "") or ""))
        if match:
            keys.add(f"nli_record:{match.group(1)}")
    commons_sha1 = metadata.get("scan_commons_file_sha1")
    if commons_sha1:
        keys.add(f"commons_file:{commons_sha1}")
    writer = metadata.get("writer_group_id")
    if writer:
        keys.add(f"writer:{writer}")
    return sorted(keys)

