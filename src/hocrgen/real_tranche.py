"""The promoted real tranche (F8g): a materialized, checksummed tree of source snapshots outside git.

The full promoted pool (about 1,650 pages, several hundred MB) never enters the repository. The operator command
``python -m hocrgen.tools.real_tranche`` materializes it from pinned operator caches into a release-relative tree:

    <tranche>/tranche.json                       the descriptor (schema, tranche id, per-source snapshot paths)
    <tranche>/SHA256SUMS                         every file in the tree, tranche-relative
    <tranche>/sources/<source_id>/snapshot/      the source's snapshot, in the packaged snapshot format

The repository commits only the manifest (``data/real_tranche/tranche_manifest.json`` and ``tranche_items.jsonl``:
ids, checksums, sizes and provenance, no page text). ``--real-tranche-root`` on the pipeline commands points each
tranche source at its materialized snapshot after checking the tree against that committed manifest; every other
source keeps its packaged snapshot, and every gate runs unchanged.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, package_root
from hocrgen.core.errors import ConfigValidationError

TRANCHE_SCHEMA = "hocrgen_real_tranche.v1"
TRANCHE_MANIFEST_SCHEMA = "hocrgen_real_tranche_manifest.v1"
TRANCHE_DESCRIPTOR = "tranche.json"
TRANCHE_CHECKSUMS = "SHA256SUMS"
COMMITTED_MANIFEST = "package://data/real_tranche/tranche_manifest.json"
TRANCHE_PATH_PREFIX = "tranche://"

# The snapshot-root setting each tranche source's fetcher reads (settings.extra).
SNAPSHOT_SETTINGS = {
    "wikisource_he_proofread": "wikisource_snapshot_root",
    "yidtaknl_vaybertaytsh_gt": "yidtaknl_snapshot_root",
    "pinkas_dataset_bgu": "pinkas_dataset_snapshot_root",
    "reshumot_born_digital": "government_print_snapshot_root",
    "knesset_committee_protocols_pre1976": "government_print_snapshot_root",
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_committed_manifest(path: Path | None = None) -> dict[str, Any] | None:
    manifest_path = path or package_root() / COMMITTED_MANIFEST.removeprefix("package://")
    if not manifest_path.is_file():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def tranche_problems(root: Path, manifest: dict[str, Any] | None) -> list[str]:
    """Why a materialized tree does not match the committed manifest (descriptor files, checksum list digest)."""

    descriptor_path = root / TRANCHE_DESCRIPTOR
    if not descriptor_path.is_file():
        return [f"missing {TRANCHE_DESCRIPTOR}"]
    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    if descriptor.get("schema") != TRANCHE_SCHEMA:
        problems.append(f"descriptor schema {descriptor.get('schema')!r} is not {TRANCHE_SCHEMA}")
    if manifest is None:
        return [*problems, "no committed tranche manifest"]
    if descriptor.get("tranche_id") != manifest.get("tranche_id"):
        problems.append(f"tranche id {descriptor.get('tranche_id')!r} != committed {manifest.get('tranche_id')!r}")
    checksums = root / TRANCHE_CHECKSUMS
    if not checksums.is_file():
        problems.append(f"missing {TRANCHE_CHECKSUMS}")
    elif sha256_path(checksums) != manifest.get("sha256sums_sha256"):
        problems.append(f"{TRANCHE_CHECKSUMS} differs from the committed manifest")
    for source_id, source in sorted((manifest.get("sources") or {}).items()):
        for relative, expected in sorted((source.get("snapshot_files") or {}).items()):
            path = root / relative
            if not path.is_file():
                problems.append(f"{source_id}: missing {relative}")
            elif sha256_path(path) != expected:
                problems.append(f"{source_id}: {relative} differs from the committed manifest")
    return problems


def verify_tranche_files(root: Path) -> list[str]:
    """Full check: every file listed in SHA256SUMS exists with its checksum, and no unlisted file is present."""

    listed: dict[str, str] = {}
    for line in (root / TRANCHE_CHECKSUMS).read_text(encoding="utf-8").splitlines():
        digest, _, relative = line.partition("  ")
        listed[relative] = digest
    problems = []
    for relative, digest in sorted(listed.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f"missing {relative}")
        elif sha256_path(path) != digest:
            problems.append(f"checksum mismatch {relative}")
    present = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != TRANCHE_CHECKSUMS
    }
    problems.extend(f"unlisted {relative}" for relative in sorted(present - set(listed)))
    return problems


def apply_real_tranche(bundle: ConfigBundle, root: Path, *, manifest_path: Path | None = None) -> ConfigBundle:
    """Point every tranche source at its materialized snapshot, after checking the tree against the manifest."""

    root = root.resolve()
    manifest = load_committed_manifest(manifest_path)
    problems = tranche_problems(root, manifest)
    if problems:
        raise ConfigValidationError("real tranche does not match the committed manifest", details=[{"problems": problems}])
    descriptor = json.loads((root / TRANCHE_DESCRIPTOR).read_text(encoding="utf-8"))
    snapshots = {source_id: entry["snapshot"] for source_id, entry in (descriptor.get("sources") or {}).items()}
    sources = []
    for source in bundle.source_registry.sources:
        snapshot = snapshots.get(source.id)
        if snapshot is None:
            sources.append(source)
            continue
        setting = SNAPSHOT_SETTINGS[source.id]
        extra = {**source.settings.extra, setting: str(root / snapshot)}
        sources.append(source.model_copy(update={"settings": source.settings.model_copy(update={"extra": extra})}))
    registry = bundle.source_registry.model_copy(update={"sources": sources})
    return dataclasses.replace(bundle, source_registry=registry, real_tranche_root=root)


def tranche_relative(path: Path, bundle: ConfigBundle) -> str | None:
    """A path inside the active tranche, written ``tranche://<relative>`` so no absolute local path is exported."""

    root = getattr(bundle, "real_tranche_root", None)
    if root is None:
        return None
    try:
        return TRANCHE_PATH_PREFIX + path.resolve().relative_to(root).as_posix()
    except ValueError:
        return None
