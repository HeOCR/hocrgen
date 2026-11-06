"""Per-line language tags for `pinkas_dataset_bgu` and the one place that turns them into evaluation scope.

Maintainer decision 8 (2026-11-06, clarified the same day): BGU Pinkas Hebrew lines may be used with full Hebrew
scope, including word-level and language-level Hebrew evaluation; Yiddish lines keep training and character-level
evaluation only. A line counts as Hebrew **only** through an explicit,
reviewable per-line tag; untagged lines keep `character_level_only`. Tags are never inferred from a heuristic here:
the operator proposal tool (`hocrgen.tools.pinkas_line_language`) writes `agent_proposed` tags, which are advisory
and never change scope. Only a `human` tag with language `he` gives its line full Hebrew scope (`full_hebrew`).

Tags live in a reviewable YAML sidecar next to the snapshot (`line_language_tags.yaml`), keyed by entry id and PAGE
XML line id, and bound to the annotation checksum and the exact line text they were made against. A tag whose
binding no longer matches is stale: its line falls back to `character_level_only` and source health reports it.

A line whose pinned text has no Hebrew-script letter (U+05D0-U+05EA: digits, punctuation, years, empty) is
scope-neutral (F8d3b, coordinator decision 2026-11-06). That is decided from the text, never from a tag: the line
never gets Hebrew scope itself, and it never keeps its page from `full_hebrew`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, ValidationError, model_validator

from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import BenchmarkGeometryRecord, ManifestModel

LINE_LANGUAGE_TAGS_FORMAT = "hocrgen.pinkas_line_language_tags.v1"
LINE_LANGUAGE_TAGS_SETTING = "line_language_tags_path"
DEFAULT_LINE_LANGUAGE_TAGS_PATH = "line_language_tags.yaml"
# The name the proposal tool records in `tagged_by`. A human tag may never carry it.
AGENT_PROPOSER_ID = "hocrgen.tools.pinkas_line_language"

LineLanguage = Literal["he", "yi", "mixed", "unknown"]
TagSource = Literal["human", "agent_proposed"]
ProposalConfidence = Literal["high", "medium", "low"]

CHARACTER_LEVEL_ONLY = "character_level_only"
FULL_HEBREW = "full_hebrew"
CHARACTER_LEVEL_USES = ("training", "character_level_evaluation")
FULL_HEBREW_USES = (
    "training",
    "character_level_evaluation",
    "word_level_hebrew_evaluation",
    "language_level_hebrew_evaluation",
)
CHARACTER_LEVEL_EXCLUSIONS = ("word_level", "language_level_hebrew")
# Decision 8, as the maintainer clarified it on 2026-11-06: a human-tagged Hebrew line is Hebrew, so nothing is
# excluded. The `language_level_hebrew` exclusion exists to keep Yiddish from being treated as Hebrew-language data.
FULL_HEBREW_EXCLUSIONS: tuple[str, ...] = ()

# Reason codes for a line's derived scope.
REASON_HUMAN_HEBREW = "human_tagged_he"
REASON_UNTAGGED = "untagged"
REASON_AGENT_PROPOSED = "agent_proposed_tag_is_advisory"
REASON_STALE = "tag_stale"
REASON_SCOPE_NEUTRAL = "scope_neutral_no_hebrew_letters"
HUMAN_NON_HEBREW_REASONS = {"yi": "human_tagged_yi", "mixed": "human_tagged_mixed", "unknown": "human_tagged_unknown"}


class LineLanguageProposal(ManifestModel):
    """What the proposal tool said about a line, kept for audit after a human confirms or overrides it."""

    method: str = Field(min_length=1)
    language: LineLanguage
    confidence: ProposalConfidence
    yiddish_markers: list[str] = Field(default_factory=list)
    hebrew_markers: list[str] = Field(default_factory=list)
    orthography_markers: list[str] = Field(default_factory=list)


class LineLanguageTag(ManifestModel):
    """One reviewable language tag for one PAGE XML line."""

    line_id: str = Field(min_length=1)
    text: str
    language: LineLanguage
    tag_source: TagSource
    tagged_by: str = Field(min_length=1)
    tagged_at: date
    rationale: str = Field(min_length=1)
    proposal: LineLanguageProposal | None = None

    @model_validator(mode="after")
    def _source_matches_tagger(self) -> LineLanguageTag:
        tagger = self.tagged_by.strip()
        if not tagger:
            raise ValueError("tagged_by must name who tagged the line")
        if self.tag_source == "agent_proposed" and tagger != AGENT_PROPOSER_ID:
            raise ValueError(f"agent_proposed tags must be tagged_by {AGENT_PROPOSER_ID}")
        if self.tag_source == "human" and tagger == AGENT_PROPOSER_ID:
            raise ValueError("a human tag must name the human reviewer in tagged_by, not the proposal tool")
        return self


class PageLineLanguageTags(ManifestModel):
    entry_id: str = Field(min_length=1)
    annotation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    lines: list[LineLanguageTag] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_line_ids(self) -> PageLineLanguageTags:
        seen: set[str] = set()
        for tag in self.lines:
            if tag.line_id in seen:
                raise ValueError(f"duplicate line tag {self.entry_id}:{tag.line_id}")
            seen.add(tag.line_id)
        return self


class LineLanguageTagFile(ManifestModel):
    format: Literal["hocrgen.pinkas_line_language_tags.v1"]
    source_id: str
    review_procedure: str = Field(min_length=1)
    proposal_method: str | None = None
    pages: list[PageLineLanguageTags] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_pages(self) -> LineLanguageTagFile:
        entry_ids = [page.entry_id for page in self.pages]
        if len(entry_ids) != len(set(entry_ids)):
            raise ValueError("duplicate entry_id in line language tags")
        return self

    def page(self, entry_id: str) -> PageLineLanguageTags | None:
        return next((page for page in self.pages if page.entry_id == entry_id), None)


class LineEvaluationScope(ManifestModel):
    """A line's derived evaluation scope: the record an evaluator reads before scoring that line."""

    entry_id: str
    line_id: str
    reading_order: int = Field(ge=1)
    language: LineLanguage | None = None
    tag_source: TagSource | None = None
    tagged_by: str | None = None
    evaluation_scope: Literal["character_level_only", "full_hebrew"]
    scope_neutral: bool = False
    allowed_uses: list[str]
    excluded_evaluations: list[str]
    reason: str
    geometry: BenchmarkGeometryRecord | None = None


def has_hebrew_letter(text: str) -> bool:
    """True if the text holds at least one Hebrew-script letter, U+05D0 (alef) to U+05EA (tav)."""

    return any("\u05d0" <= char <= "\u05ea" for char in text)


def line_scope_fields(tag: LineLanguageTag | None, line_text: str, *, stale: bool = False) -> dict[str, Any]:
    """Derive one line's scope from its pinned text and its tag. This is the only place a line's scope is decided.

    A line with no Hebrew-script letter is scope-neutral whatever its tag says: `character_level_only`, never
    `full_hebrew`, and ignored by the page rule. Otherwise full Hebrew scope (training, character-level, word-level
    Hebrew and language-level Hebrew evaluation, nothing excluded) needs `tag_source: human`
    **and** `language: he` on a tag that still binds to the line. Everything else, including every
    `agent_proposed` tag, keeps `character_level_only`.
    """

    if not has_hebrew_letter(line_text):
        return {
            "evaluation_scope": CHARACTER_LEVEL_ONLY,
            "scope_neutral": True,
            "allowed_uses": list(CHARACTER_LEVEL_USES),
            "excluded_evaluations": list(CHARACTER_LEVEL_EXCLUSIONS),
            "reason": REASON_SCOPE_NEUTRAL,
        }
    if tag is None or stale:
        reason = REASON_STALE if stale else REASON_UNTAGGED
    elif tag.tag_source != "human":
        reason = REASON_AGENT_PROPOSED
    elif tag.language == "he":
        return {
            "evaluation_scope": FULL_HEBREW,
            "scope_neutral": False,
            "allowed_uses": list(FULL_HEBREW_USES),
            "excluded_evaluations": list(FULL_HEBREW_EXCLUSIONS),
            "reason": REASON_HUMAN_HEBREW,
        }
    else:
        reason = HUMAN_NON_HEBREW_REASONS[tag.language]
    return {
        "evaluation_scope": CHARACTER_LEVEL_ONLY,
        "scope_neutral": False,
        "allowed_uses": list(CHARACTER_LEVEL_USES),
        "excluded_evaluations": list(CHARACTER_LEVEL_EXCLUSIONS),
        "reason": reason,
    }


def tag_binding_problem(tag: LineLanguageTag, line_text: str | None) -> str | None:
    """Return why a tag no longer binds to its line (unknown line id or changed text), or None."""

    if line_text is None:
        return "unknown_line_id"
    if tag.text != line_text:
        return "line_text_changed"
    return None


def derive_line_scopes(entry_id: str, annotation_sha256: str, lines: list[Any], page_tags: PageLineLanguageTags | None) -> list[LineEvaluationScope]:
    """Derive the scope of every parsed PAGE XML line of one page, in reading order.

    `lines` are `PageXmlLineRecord`s. A page tag block made against another annotation checksum is stale as a whole;
    a line tag whose text differs from the parsed line is stale. Stale and missing tags give `character_level_only`.
    """

    page_stale = page_tags is not None and page_tags.annotation_sha256 != annotation_sha256
    tags = {tag.line_id: tag for tag in page_tags.lines} if page_tags is not None else {}
    scopes: list[LineEvaluationScope] = []
    for line in lines:
        tag = tags.get(line.line_id)
        stale = tag is not None and (page_stale or tag_binding_problem(tag, line.text) is not None)
        scopes.append(
            LineEvaluationScope(
                entry_id=entry_id,
                line_id=line.line_id,
                reading_order=line.reading_order,
                language=tag.language if tag is not None and not stale else None,
                tag_source=tag.tag_source if tag is not None and not stale else None,
                tagged_by=tag.tagged_by if tag is not None and not stale else None,
                geometry=line.geometry,
                **line_scope_fields(tag, line.text, stale=stale),
            )
        )
    return scopes


def page_scope_summary(scopes: list[LineEvaluationScope]) -> dict[str, Any]:
    """Summarize a page's line scopes. Scope-neutral lines (no Hebrew-script letter) are left out of the page rule.

    The page is `full_hebrew` only if it has at least one non-neutral line and every non-neutral line is
    `full_hebrew`. Otherwise it stays `character_level_only`, so any untagged, stale, advisory or non-Hebrew
    text line keeps the page conservative.
    """

    reasons: dict[str, int] = {}
    for scope in scopes:
        reasons[scope.reason] = reasons.get(scope.reason, 0) + 1
    text_lines = [scope for scope in scopes if not scope.scope_neutral]
    hebrew = [scope.line_id for scope in text_lines if scope.evaluation_scope == FULL_HEBREW]
    all_hebrew = bool(text_lines) and len(hebrew) == len(text_lines)
    return {
        "page_evaluation_scope": FULL_HEBREW if all_hebrew else CHARACTER_LEVEL_ONLY,
        "line_count": len(scopes),
        "full_hebrew_line_count": len(hebrew),
        "character_level_only_line_count": len(text_lines) - len(hebrew),
        "scope_neutral_line_count": len(scopes) - len(text_lines),
        "full_hebrew_line_ids": hebrew,
        "scope_neutral_line_ids": [scope.line_id for scope in scopes if scope.scope_neutral],
        "reasons": dict(sorted(reasons.items())),
    }


def line_language_tags_path(root: Path, snapshot: dict[str, Any]) -> Path:
    return root / str(snapshot.get(LINE_LANGUAGE_TAGS_SETTING) or DEFAULT_LINE_LANGUAGE_TAGS_PATH)


def load_line_language_tags(root: Path, snapshot: dict[str, Any]) -> LineLanguageTagFile | None:
    """Load and validate the snapshot's tag sidecar. A missing sidecar means every line is untagged.

    The sidecar is hand-edited, so unreadable files, YAML syntax errors and schema errors all raise
    `StageExecutionError` (naming the file, never its absolute path) for source health to record.
    """

    path = line_language_tags_path(root, snapshot)
    if not path.is_file():
        return None
    try:
        return LineLanguageTagFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError) as exc:
        raise StageExecutionError(f"invalid Pinkas line language tags in {path.name}: {exc}") from exc


def tag_file_problems(
    tag_file: LineLanguageTagFile, pages: dict[str, tuple[str, list[Any]]], skip_entry_ids: set[str] | frozenset[str] = frozenset()
) -> list[str]:
    """List every stale binding in the sidecar. `pages` maps entry id to (annotation sha256, parsed lines);
    `skip_entry_ids` names snapshot entries that were not parsed (excluded, or already failing another check)."""

    problems: list[str] = []
    for page_tags in tag_file.pages:
        if page_tags.entry_id in skip_entry_ids:
            continue
        if page_tags.entry_id not in pages:
            problems.append(f"{page_tags.entry_id}: unknown_entry_id")
            continue
        annotation_sha256, lines = pages[page_tags.entry_id]
        if page_tags.annotation_sha256 != annotation_sha256:
            problems.append(f"{page_tags.entry_id}: annotation_sha256_changed")
        texts = {line.line_id: line.text for line in lines}
        for tag in page_tags.lines:
            problem = tag_binding_problem(tag, texts.get(tag.line_id))
            if problem is not None:
                problems.append(f"{page_tags.entry_id}:{tag.line_id}: {problem}")
    return problems
