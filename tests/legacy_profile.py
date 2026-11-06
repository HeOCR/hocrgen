"""Test helper: restore the pre-F8g ``profile_open_v1`` in a copied config root.

The B-phase fixture tests pin counts for the four original public sources (NLI fixture seeds, Pinkas, BiblIA and
the synthetic fixture batch). F8g added the promoted real sources to ``profile_open_v1``; those tests copy the
config and drop the promoted sources again, so they keep testing what they were written for. F8g behaviour is
tested against the packaged config in ``test_real_source_release.py``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

F8G_PROMOTED_SOURCES = (
    "wikisource_he_proofread",
    "yidtaknl_vaybertaytsh_gt",
    "pinkas_dataset_bgu",
    "reshumot_born_digital",
    "knesset_committee_protocols_pre1976",
)


def restrict_open_profile_to_legacy_sources(config_root: Path) -> None:
    path = config_root / "profiles" / "profile_open_v1.yaml"
    profile = yaml.safe_load(path.read_text(encoding="utf-8"))
    profile["include_sources"] = [source for source in profile["include_sources"] if source not in F8G_PROMOTED_SOURCES]
    path.write_text(yaml.safe_dump(profile, allow_unicode=True, sort_keys=False), encoding="utf-8")
