"""Fixture-backed review-only adapter for Hebrew Wikisource ProofreadPage pages (F8b).

Each item is one ``עמוד:`` (Page) page at quality 3 (proofread) or 4 (validated), paired with that page of
its Index's Commons PDF/DjVu file. The adapter reads a pinned snapshot only; it never calls the network and
never edits Wikisource or Commons.

Admission is per Index, on per-file evidence of both (a) the work being public domain in Israel and (b) clear
scan rights (maintainer decisions, 2026-11-06). No Commons licence template is enough on its own, files whose
only PD tag is ``PD-US-*`` are rejected, and the Birnbaum Siddur (1949) and Haggadah (1953) are excluded.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any

from hocrgen.config.loader import ConfigBundle, load_yaml_file
from hocrgen.config.models import SourceConfig
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.manifests.models import (
    AcquiredAsset,
    AcquiredItemRecord,
    AssetReference,
    BenchmarkTranscriptionReferenceRecord,
    CandidateRecord,
    EnrichedCandidateRecord,
)
from hocrgen.parsers.wikitext import (
    WIKITEXT_NORMALIZATION_VERSION,
    UnsupportedWikitextError,
    pagequality_level,
    wikitext_to_plain_text,
)
from hocrgen.utils.hashing import sha256_file
from hocrgen.utils.io import copy_file

WIKISOURCE_SNAPSHOT_SETTING = "wikisource_snapshot_root"
WIKISOURCE_SITE_URL = "https://he.wikisource.org"
TEXT_LICENSE = "CC-BY-SA-4.0"

ADMITTED_QUALITY_LEVELS = {3: "proofread", 4: "validated"}
PD_ISRAEL_DEATH_CUTOFF_YEAR = 1955
PD_ISRAEL_ANONYMOUS_PUBLICATION_CUTOFF_YEAR = 1955
PD_ISRAEL_STATE_WORK_CUTOFF_YEAR = 1975
WORK_RIGHTS_BASES = {"author_died_by_1955", "state_work_by_1975", "anonymous_published_by_1955"}
SCAN_RIGHTS_BASES = {"faithful_reproduction_of_pd_work", "explicit_open_licence"}
OPEN_SCAN_LICENCES = {"CC0-1.0", "PDM-1.0", "CC-BY-4.0", "CC-BY-SA-4.0"}
ANONYMOUS_CREATOR_ROLES = {"anonymous", "pseudonymous"}
# Page reasons that mean the pinned snapshot itself is broken; source health reports them as errors.
WIKISOURCE_INTEGRITY_REASONS = {"wikitext_missing", "wikitext_checksum_mismatch", "page_text_checksum_mismatch"}

# Maintainer decision (F8a decision 2, accepted 2026-11-06): not PD in Israel (Birnbaum died 1988).
EXCLUDED_INDEX_FILES = {
    "File:Philip Birnbaum - ha-Siddur ha-Shalem (The Daily Prayer Book,1949).pdf": "excluded_birnbaum_work",
    "File:Birnbaum Haggadah.pdf": "excluded_birnbaum_work",
}

# Team-lead hold (2026-11-06), pending a maintainer rights decision: Google-digitized scans are not admitted.
GOOGLE_DIGITIZATION_MARKERS = ("digitized by google", "google books", "books.google")
TRANSCRIPTION_COVERAGE_FULL = "full_page"

_LICENCE_TOKEN = re.compile(r"^(PD|CC|Cc-|GFDL|FAL|OGL|Copyrighted|Attribution)", re.IGNORECASE)
_BOT_NAME = re.compile(r"bot$", re.IGNORECASE)


def wikisource_snapshot_root(source: SourceConfig, bundle: ConfigBundle) -> Path:
    reference = source.settings.extra.get(WIKISOURCE_SNAPSHOT_SETTING)
    if not isinstance(reference, str) or not reference:
        raise StageExecutionError(f"{source.id} requires settings.extra.{WIKISOURCE_SNAPSHOT_SETTING}")
    return bundle.resolve_path(reference)


def load_wikisource_snapshot(root: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Load the snapshot descriptor, Index evidence records (by ``index_key``) and page records."""

    snapshot = load_yaml_file(root / "snapshot.yaml")
    payload = json.loads((root / str(snapshot.get("indexes_path", "indexes.json"))).read_text(encoding="utf-8"))
    indexes = {record["index_key"]: record for record in payload["indexes"]}
    pages_path = root / str(snapshot.get("pages_path", "pages.jsonl"))
    pages = [json.loads(line) for line in pages_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return snapshot, indexes, pages


# --- Index (Commons file) admission ------------------------------------------------------------------------


def licence_tokens(index: dict[str, Any]) -> list[str]:
    """Licence template names on the Commons file page, including those nested as PD-scan arguments."""

    tokens: list[str] = []
    for template in (index.get("commons_file") or {}).get("licence_templates") or []:
        for part in str(template).split("|"):
            name = part.strip()
            if name and "=" not in name and _LICENCE_TOKEN.match(name):
                tokens.append(name)
    return tokens


def scan_source_origin(index: dict[str, Any]) -> str:
    """Provenance label for where the Commons scan came from. Informational only; it gates nothing."""

    commons = index.get("commons_file") or {}
    haystack = " ".join(
        str(value)
        for value in (
            commons.get("title"),
            commons.get("source_field"),
            commons.get("institution_field"),
            commons.get("provenance_text"),
            *(commons.get("categories") or []),
        )
        if value
    ).casefold()
    if "hebrewbooks" in haystack:
        return "hebrewbooks"
    if "opensiddur" in haystack or "open siddur" in haystack:
        return "open_siddur_project"
    if "national library of israel" in haystack:
        return "national_library_of_israel"
    if "archive.org" in haystack:
        return "internet_archive"
    return "unrecorded"


def index_exclusion_reasons(index: dict[str, Any]) -> list[str]:
    """Every reason an Index cannot be admitted; empty when (a) the work and (b) the scan are both evidenced."""

    reasons: list[str] = []
    commons = index.get("commons_file") or {}
    excluded = EXCLUDED_INDEX_FILES.get(str(commons.get("title")))
    if excluded:
        reasons.append(excluded)
    if not commons.get("sha1") or not commons.get("file_page_revision_id"):
        reasons.append("commons_file_unpinned")
    tokens = licence_tokens(index)
    if not tokens:
        reasons.append("no_licence_template")
    elif all(token.upper().startswith("PD-US") for token in tokens):
        reasons.append("pd_us_only_licence")
    reasons.extend(_work_rights_reasons(index))
    reasons.extend(_scan_rights_reasons(index))
    return reasons


def index_exclusion_reason(index: dict[str, Any]) -> str | None:
    reasons = index_exclusion_reasons(index)
    return reasons[0] if reasons else None


def _work_rights_reasons(index: dict[str, Any]) -> list[str]:
    work = index.get("work") or {}
    rights = index.get("work_rights") or {}
    basis = rights.get("basis")
    if basis not in WORK_RIGHTS_BASES:
        return ["work_rights_basis_unsupported"]
    reasons: list[str] = []
    if not str(rights.get("evidence") or "").strip():
        reasons.append("work_rights_evidence_missing")
    creators = work.get("creators") or []
    if basis == "author_died_by_1955":
        if not creators:
            reasons.append("creators_missing")
        for creator in creators:
            death_year = creator.get("death_year")
            if not isinstance(death_year, int) or not creator.get("death_year_evidence_url"):
                reasons.append("creator_death_year_missing")
            elif death_year > PD_ISRAEL_DEATH_CUTOFF_YEAR:
                reasons.append("creator_died_after_1955")
    elif basis == "state_work_by_1975":
        created = work.get("created_year")
        if not isinstance(created, int) or not work.get("state_body"):
            reasons.append("state_work_evidence_missing")
        elif created > PD_ISRAEL_STATE_WORK_CUTOFF_YEAR:
            reasons.append("state_work_after_1975")
    else:
        published = work.get("published_year")
        if any(creator.get("role") not in ANONYMOUS_CREATOR_ROLES for creator in creators):
            reasons.append("named_creator_on_anonymous_basis")
        if not isinstance(published, int):
            reasons.append("publication_year_missing")
        elif published > PD_ISRAEL_ANONYMOUS_PUBLICATION_CUTOFF_YEAR:
            reasons.append("anonymous_work_after_1955")
    return sorted(set(reasons), key=reasons.index)


def _scan_rights_reasons(index: dict[str, Any]) -> list[str]:
    commons = index.get("commons_file") or {}
    rights = index.get("scan_rights") or {}
    basis = rights.get("basis")
    if basis not in SCAN_RIGHTS_BASES:
        return ["scan_rights_basis_unsupported"]
    reasons: list[str] = []
    if not str(rights.get("evidence") or "").strip():
        reasons.append("scan_rights_evidence_missing")
    if basis == "explicit_open_licence" and rights.get("licence") not in OPEN_SCAN_LICENCES:
        reasons.append("scan_licence_not_open")
    if basis == "faithful_reproduction_of_pd_work" and not (commons.get("source_field") or commons.get("institution_field")):
        reasons.append("scan_provenance_unrecorded")
    reasons.extend(_google_digitization_reasons(index))
    return reasons


def _google_digitization_reasons(index: dict[str, Any]) -> list[str]:
    """Hold Google-digitized scans until the maintainer decides on them.

    The stamp is on the page images, not reliably in Commons metadata, so the capture must record
    ``scan_rights.digitized_by_google`` after looking at the renders. Commons text naming Google also holds the file.
    """

    commons = index.get("commons_file") or {}
    rights = index.get("scan_rights") or {}
    haystack = " ".join(
        str(value)
        for value in (
            commons.get("source_field"),
            commons.get("institution_field"),
            commons.get("provenance_text"),
            rights.get("evidence"),
            *(commons.get("categories") or []),
        )
        if value
    ).casefold()
    if rights.get("digitized_by_google") is True or any(marker in haystack for marker in GOOGLE_DIGITIZATION_MARKERS):
        return ["google_digitized_scan_pending"]
    if rights.get("digitized_by_google") is not False:
        return ["google_digitization_unchecked"]
    return []


# --- Page admission and attestation ------------------------------------------------------------------------


def _quality_editors(page: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return (proofreader, validator): the history entries that set quality 3 and, for quality 4, 4."""

    history = page.get("quality_history") or []
    if not history:
        return None, None
    last = history[-1]
    if page.get("quality") == 4:
        validator = last if last.get("level") == 4 else None
        proofreader = next((entry for entry in reversed(history[:-1]) if entry.get("level") == 3), None)
        return proofreader, validator
    return (last if last.get("level") == 3 else None), None


def _is_named_human(entry: dict[str, Any]) -> bool:
    name = str(entry.get("user") or "")
    return bool(name) and int(entry.get("user_id") or 0) > 0 and "bot" not in (entry.get("user_groups") or []) and not _BOT_NAME.search(name)


def page_exclusion_reasons(page: dict[str, Any], indexes: dict[str, dict[str, Any]], root: Path) -> list[str]:
    reasons: list[str] = []
    index = indexes.get(str(page.get("index_key")))
    if index is None:
        reasons.append("index_not_in_snapshot")
    elif index_exclusion_reasons(index):
        reasons.append("index_not_admitted")
    quality = page.get("quality")
    if quality not in ADMITTED_QUALITY_LEVELS:
        reasons.append("quality_not_proofread")
        return reasons
    history = page.get("quality_history") or []
    if not history or history[-1].get("level") != quality:
        reasons.append("quality_history_mismatch")
    proofreader, validator = _quality_editors(page)
    editors = [proofreader] + ([validator] if quality == 4 else [])
    if proofreader is None:
        reasons.append("proofreader_missing")
    if quality == 4 and validator is None:
        reasons.append("validator_missing")
    present = [entry for entry in editors if entry is not None]
    if any(not _is_named_human(entry) for entry in present):
        reasons.append("quality_editor_not_named_human")
    if any(entry.get("pagequality_user_attribute") != entry.get("user") for entry in present):
        reasons.append("quality_attribute_mismatch")
    if proofreader and validator and proofreader.get("user") == validator.get("user"):
        reasons.append("validator_is_proofreader")
    coverage = page.get("transcription_coverage")
    if coverage is None:
        reasons.append("transcription_coverage_unrecorded")
    elif coverage != TRANSCRIPTION_COVERAGE_FULL:
        reasons.append("partial_page_transcription")
    reasons.extend(_page_text_reasons(page, root))
    return reasons


def page_exclusion_reason(page: dict[str, Any], indexes: dict[str, dict[str, Any]], root: Path) -> str | None:
    reasons = page_exclusion_reasons(page, indexes, root)
    return reasons[0] if reasons else None


def _page_text_reasons(page: dict[str, Any], root: Path) -> list[str]:
    wikitext_path = root / str(page.get("wikitext_path", ""))
    if not page.get("wikitext_path") or not wikitext_path.is_file():
        return ["wikitext_missing"]
    wikitext = wikitext_path.read_text(encoding="utf-8")
    if _sha256(wikitext) != page.get("wikitext_sha256"):
        return ["wikitext_checksum_mismatch"]
    if pagequality_level(wikitext) != page.get("quality"):
        return ["quality_tag_mismatch"]
    try:
        text = wikitext_to_plain_text(wikitext)
    except UnsupportedWikitextError:
        return ["wikitext_unsupported_markup"]
    if _sha256(text) != page.get("text_sha256"):
        return ["page_text_checksum_mismatch"]
    return []


def page_attestation(page: dict[str, Any]) -> dict[str, Any]:
    """Human-attestation facts for a page (maintainer decision 2, 2026-11-06).

    Quality 4 is human-attested and adjudication-eligible, but only while the pinned text is the text the
    validator saw: any later edit that changes the plain text removes adjudication eligibility.
    """

    proofreader, validator = _quality_editors(page)
    post_edits = [edit for edit in page.get("edits_after_quality_set") or [] if edit.get("text_changed")]
    if page.get("quality") == 4:
        unchanged = not post_edits and page.get("quality_set_text_sha256") == page.get("text_sha256")
        eligible = validator is not None and unchanged
        reason = None if eligible else "text_changed_after_validation"
        attestation = "two_editor_validated"
    else:
        eligible = False
        reason = "quality_3_single_reviewer"
        attestation = "single_reviewer_proofread"
    return {
        "human_attestation": attestation,
        "proofreader": _editor_record(proofreader),
        "validator": _editor_record(validator),
        "adjudication_eligible": eligible,
        "adjudication_ineligible_reason": reason,
        "text_changing_edits_after_quality_set": [
            {"revision_id": edit["revision_id"], "user": edit["user"], "timestamp": edit["timestamp"]} for edit in post_edits
        ],
    }


def _editor_record(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if entry is None:
        return None
    return {
        "user": entry["user"],
        "user_id": entry["user_id"],
        "revision_id": entry["revision_id"],
        "timestamp": entry["timestamp"],
    }


def page_permalink(page: dict[str, Any]) -> str:
    title = urllib.parse.quote(str(page["page_title"]).replace(" ", "_"), safe=":/")
    return f"{WIKISOURCE_SITE_URL}/w/index.php?title={title}&oldid={page['revision_id']}"


def page_plain_text(page: dict[str, Any], root: Path) -> str:
    """Derive the page's plain text from its pinned wikitext and check it against the pinned checksum."""

    wikitext = (root / page["wikitext_path"]).read_text(encoding="utf-8")
    text = wikitext_to_plain_text(wikitext)
    if _sha256(text) != page["text_sha256"]:
        raise StageExecutionError(f"Wikisource page text checksum mismatch for {page['source_item_id']}")
    return text


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class WikisourceProofreadImporter:
    """Packaged-static-records adapter over a pinned Hebrew Wikisource ProofreadPage snapshot."""

    def discover_candidates(self, source: SourceConfig, bundle: ConfigBundle, options: StageOptions) -> list[CandidateRecord]:
        root = wikisource_snapshot_root(source, bundle)
        snapshot, indexes, pages = load_wikisource_snapshot(root)
        candidates: list[CandidateRecord] = []
        for page in sorted(pages, key=lambda record: record["source_item_id"]):
            if page_exclusion_reasons(page, indexes, root):
                continue
            if options.max_items is not None and len(candidates) >= options.max_items:
                break
            candidates.append(
                CandidateRecord(
                    candidate_id=f"{source.id}:{page['source_item_id']}",
                    source_id=source.id,
                    source_item_id=page["source_item_id"],
                    source_url=page_permalink(page),
                    discovery_method="wikisource_snapshot_importer",
                    title=page["page_title"],
                    raw_metadata={
                        "snapshot_root": str(root),
                        "captured_at": snapshot.get("captured_at"),
                        "page": page,
                        "index": indexes[page["index_key"]],
                    },
                )
            )
        return candidates

    def fetch_candidate_metadata(self, source: SourceConfig, bundle: ConfigBundle, candidates, options: StageOptions) -> list[EnrichedCandidateRecord]:
        enriched: list[EnrichedCandidateRecord] = []
        for candidate in candidates:
            page = candidate.raw_metadata["page"]
            index = candidate.raw_metadata["index"]
            root = Path(candidate.raw_metadata["snapshot_root"])
            image = page["image"]
            commons = index["commons_file"]
            work = index["work"]
            enriched.append(
                EnrichedCandidateRecord(
                    **candidate.model_dump(),
                    raw_rights_text=TEXT_LICENSE,
                    asset_references=[
                        AssetReference(
                            reference=image["path"],
                            resolved_path=str((root / image["path"]).resolve()),
                            media_type=image["media_type"],
                        )
                    ],
                    metadata={
                        "collection": "Hebrew Wikisource ProofreadPage",
                        "period": "historical",
                        "content_type": "printed_historical",
                        "languages": ["he"],
                        "upstream_identifier": page["page_title"],
                        "source_group_id": f"wikisource:{page['index_key']}",
                        "wikisource_index_title": index["index_title"],
                        "wikisource_index_revision_id": index["index_revision_id"],
                        "wikisource_page_number": page["page_number"],
                        "wikisource_page_id": page["page_id"],
                        "wikisource_revision_id": page["revision_id"],
                        "wikisource_revision_timestamp": page["revision_timestamp"],
                        "wikisource_quality_level": page["quality"],
                        "wikisource_quality_label": ADMITTED_QUALITY_LEVELS[page["quality"]],
                        **page_attestation(page),
                        "text_license": TEXT_LICENSE,
                        "text_attribution": f"Hebrew Wikisource contributors, {page_permalink(page)}",
                        "text_normalization": WIKITEXT_NORMALIZATION_VERSION,
                        "page_text_ref": page["text_path"],
                        "page_text_sha256": page["text_sha256"],
                        "raw_wikitext_sha256": page["wikitext_sha256"],
                        "raw_wikitext_revision_sha1": page["revision_sha1"],
                        "work_title": work["title"],
                        "work_published_year": work.get("published_year"),
                        "work_creators": [
                            {"name": creator["name"], "role": creator["role"], "death_year": creator["death_year"]}
                            for creator in work.get("creators", [])
                        ],
                        "work_rights_basis": index["work_rights"]["basis"],
                        "scan_rights_basis": index["scan_rights"]["basis"],
                        "scan_licence": index["scan_rights"].get("licence"),
                        "scan_source_origin": scan_source_origin(index),
                        "scan_commons_file": commons["title"],
                        "scan_commons_file_sha1": commons["sha1"],
                        "scan_commons_file_page_revision_id": commons["file_page_revision_id"],
                        "scan_commons_licence_templates": commons["licence_templates"],
                        "scan_page_number": image["rendered_from"]["page"],
                        "transcription_coverage": page["transcription_coverage"],
                        "rights_evidence_checked_at": index["evidence_checked_at"],
                        "expected_asset_sha256": image["sha256"],
                    },
                )
            )
        return enriched

    def acquire_items(self, source: SourceConfig, bundle: ConfigBundle, items, output_dir, options: StageOptions) -> list[AcquiredItemRecord]:
        acquired_items: list[AcquiredItemRecord] = []
        for item in items:
            asset = item.asset_references[0]
            resolved = Path(asset.resolved_path or "")
            destination = output_dir / item.item_id / resolved.name
            copy_file(resolved, destination)
            digest = sha256_file(destination)
            expected = item.metadata.get("expected_asset_sha256")
            if expected and digest != expected:
                raise StageExecutionError(
                    f"Wikisource asset checksum mismatch for {item.item_id}: expected {expected}, got {digest}"
                )
            acquired_items.append(
                AcquiredItemRecord(
                    **item.model_dump(),
                    acquired_assets=[
                        AcquiredAsset(item_id=item.item_id, path=str(destination), sha256=digest, media_type=asset.media_type)
                    ],
                )
            )
        return acquired_items


# --- Operator-only F2 reference conversion -----------------------------------------------------------------


def page_reference_record(source_id: str, page: dict[str, Any], root: Path) -> BenchmarkTranscriptionReferenceRecord:
    """Convert one adjudication-eligible quality-4 page to a ``benchmark_transcription_reference.v1`` record.

    The record is a human-reviewed candidate reference (``review.status: reviewed``), not an adjudicated one:
    adjudication stays a separate human step. Lines are the rendered paragraphs, not printed lines.
    """

    attestation = page_attestation(page)
    if not attestation["adjudication_eligible"]:
        raise StageExecutionError(
            f"Wikisource page {page['source_item_id']} is not adjudication-eligible: {attestation['adjudication_ineligible_reason']}"
        )
    text = page_plain_text(page, root)
    paragraphs = [paragraph for paragraph in text.split("\n") if paragraph.strip()]
    reviewers = [f"wikisource:{attestation['proofreader']['user']}", f"wikisource:{attestation['validator']['user']}"]
    return BenchmarkTranscriptionReferenceRecord(
        schema_version="benchmark_transcription_reference.v1",
        item_id=f"{source_id}:{page['source_item_id']}",
        source_id=source_id,
        source_item_id=page["source_item_id"],
        normalization={"unicode": "NFC", "text_order": "logical"},
        language_scripts=[{"language": "he", "script": "Hebr", "direction": "rtl"}],
        scoring_policy={
            "uncertain": "include_primary_and_report",
            "illegible": "exclude_primary",
            "damaged": "include_readable_and_report",
            "deleted": "exclude_primary",
            "marginal": "include_when_ordered_else_separate",
        },
        pages=[{"page_id": "page-1", "reading_order": 1, "text": text}],
        lines=[
            {"line_id": f"line-{number}", "page_id": "page-1", "reading_order": number, "text": paragraph, "layout_line_id": None}
            for number, paragraph in enumerate(paragraphs, start=1)
        ],
        spans=[],
        review={
            "status": "reviewed",
            "reviewers": reviewers,
            "adjudicator": None,
            "adjudicated_at": None,
            "correction_of": None,
            "superseded_by": None,
            "change_reason": (
                f"Wikisource quality 4 at revision {page['revision_id']}: proofread by {reviewers[0]}, "
                f"validated by {reviewers[1]}; {WIKITEXT_NORMALIZATION_VERSION}; lines are rendered paragraphs"
            ),
        },
    )


def write_wikisource_reference_pool(source: SourceConfig, bundle: ConfigBundle, output_dir: Path) -> dict[str, Any]:
    """Operator-only: write F2 reference files for adjudication-eligible pages. Never touches ``benchmark_v1``."""

    root = wikisource_snapshot_root(source, bundle)
    _, indexes, pages = load_wikisource_snapshot(root)
    entries: list[dict[str, Any]] = []
    skipped: dict[str, int] = {}
    for page in sorted(pages, key=lambda record: record["source_item_id"]):
        reasons = page_exclusion_reasons(page, indexes, root)
        reason = reasons[0] if reasons else page_attestation(page)["adjudication_ineligible_reason"]
        if reason:
            skipped[reason] = skipped.get(reason, 0) + 1
            continue
        record = page_reference_record(source.id, page, root)
        relative = f"references/{page['source_item_id']}/transcription.json"
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n"
        path.write_text(payload, encoding="utf-8")
        entries.append(
            {
                "item_id": record.item_id,
                "path": relative,
                "sha256": _sha256(payload),
                "wikisource_revision_id": page["revision_id"],
                "adjudication_status": "needs_adjudication",
            }
        )
    manifest = {
        "schema_version": "wikisource_reference_pool.v1",
        "source_id": source.id,
        "text_license": TEXT_LICENSE,
        "reference_contract": "benchmark_transcription_reference.v1",
        "items": entries,
        "skipped": dict(sorted(skipped.items())),
    }
    (output_dir / "reference_pool.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest
