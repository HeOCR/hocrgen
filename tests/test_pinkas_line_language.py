from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

import hocrgen.fetchers.pinkas_line_language as line_language_module
from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.core.errors import StageExecutionError
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.pinkas_dataset import (
    PageXmlLineRecord,
    PinkasDatasetImporter,
    load_entry_line_scopes,
    load_entry_page_lines,
    load_pinkas_dataset_snapshot,
)
from hocrgen.fetchers.pinkas_line_language import (
    AGENT_PROPOSER_ID,
    LineLanguageTag,
    LineLanguageTagFile,
    PageLineLanguageTags,
    derive_line_scopes,
    line_scope_fields,
    load_line_language_tags,
    page_scope_summary,
    tag_file_problems,
)
from hocrgen.manifests.models import BenchmarkBBoxRecord, BenchmarkGeometryRecord, BenchmarkPointRecord
from hocrgen.source_ops import _inspect_source
from hocrgen.tools import pinkas_line_language as tool

SOURCE_ID = "pinkas_dataset_bgu"
SNAPSHOT_ROOT = package_root() / "data" / "pinkas_dataset_bgu" / "snapshot"
PAGE_105 = "nli_990000445290205171__page105_right"
PAGE_112 = "nli_990000445290205171__page112_right"
SHA = "a" * 64
CHARACTER = {
    "evaluation_scope": "character_level_only",
    "allowed_uses": ["training", "character_level_evaluation"],
    "excluded_evaluations": ["word_level", "language_level_hebrew"],
}


def _tag(line_id: str = "l1", text: str = "שלום", language: str = "he", tag_source: str = "human", **extra) -> LineLanguageTag:
    tagged_by = extra.pop("tagged_by", "Reviewer Name" if tag_source == "human" else AGENT_PROPOSER_ID)
    return LineLanguageTag(
        line_id=line_id,
        text=text,
        language=language,
        tag_source=tag_source,
        tagged_by=tagged_by,
        tagged_at=date(2026, 11, 6),
        rationale=extra.pop("rationale", "checked against the scan"),
        **extra,
    )


def _line(line_id: str, text: str, reading_order: int) -> PageXmlLineRecord:
    points = [BenchmarkPointRecord(x=0, y=0), BenchmarkPointRecord(x=10, y=0), BenchmarkPointRecord(x=10, y=5)]
    geometry = BenchmarkGeometryRecord(type="bbox_polygon", bbox=BenchmarkBBoxRecord(x=0, y=0, width=10, height=5), polygon=points)
    return PageXmlLineRecord(line_id=line_id, region_id="r1", reading_order=reading_order, text=text, geometry=geometry)


def _copy_snapshot_config(tmp_path: Path) -> tuple[Path, Path]:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    shutil.copytree(SNAPSHOT_ROOT, config_root / "pinkas_snapshot")
    sources_path = config_root / "sources.yaml"
    payload = yaml.safe_load(sources_path.read_text(encoding="utf-8"))
    for source in payload["sources"]:
        if source["id"] == SOURCE_ID:
            source["settings"]["extra"]["pinkas_dataset_snapshot_root"] = "pinkas_snapshot"
    sources_path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return config_root, config_root / "pinkas_snapshot"


def _source(config_root: Path | None = None):
    bundle = load_and_validate_bundle(config_root) if config_root else load_and_validate_bundle()
    return bundle, next(source for source in bundle.source_registry.sources if source.id == SOURCE_ID)


def _set_human(root: Path, entry_id: str, line_ids: set[str], language: str = "he") -> None:
    path = root / "line_language_tags.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    for page in payload["pages"]:
        if page["entry_id"] != entry_id:
            continue
        for line in page["lines"]:
            if line["line_id"] in line_ids:
                line.update(language=language, tag_source="human", tagged_by="Test Reviewer", rationale="read against the scan")
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")


# --- the single scope derivation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag_source", "language", "expected_scope", "reason"),
    [
        ("human", "he", "word_level_hebrew", "human_tagged_he"),
        ("human", "yi", "character_level_only", "human_tagged_yi"),
        ("human", "mixed", "character_level_only", "human_tagged_mixed"),
        ("human", "unknown", "character_level_only", "human_tagged_unknown"),
        ("agent_proposed", "he", "character_level_only", "agent_proposed_tag_is_advisory"),
        ("agent_proposed", "yi", "character_level_only", "agent_proposed_tag_is_advisory"),
        ("agent_proposed", "mixed", "character_level_only", "agent_proposed_tag_is_advisory"),
        ("agent_proposed", "unknown", "character_level_only", "agent_proposed_tag_is_advisory"),
    ],
)
def test_every_tag_combination_derives_its_scope(tag_source: str, language: str, expected_scope: str, reason: str) -> None:
    fields = line_scope_fields(_tag(language=language, tag_source=tag_source))
    assert fields["evaluation_scope"] == expected_scope
    assert fields["reason"] == reason
    if expected_scope == "word_level_hebrew":
        assert fields["allowed_uses"] == ["training", "character_level_evaluation", "word_level_evaluation"]
        assert fields["excluded_evaluations"] == ["language_level_hebrew"]
    else:
        assert {key: fields[key] for key in CHARACTER} == CHARACTER
    # A stale tag never widens scope, whatever it says.
    assert line_scope_fields(_tag(language=language, tag_source=tag_source), stale=True) == {**CHARACTER, "reason": "tag_stale"}


def test_untagged_line_keeps_character_level_only() -> None:
    assert line_scope_fields(None) == {**CHARACTER, "reason": "untagged"}


def test_tag_records_are_typed_and_tie_source_to_tagger() -> None:
    with pytest.raises(ValidationError, match="agent_proposed tags must be tagged_by"):
        _tag(tag_source="agent_proposed", tagged_by="Some Person")
    with pytest.raises(ValidationError, match="must name the human reviewer"):
        _tag(tag_source="human", tagged_by=AGENT_PROPOSER_ID)
    with pytest.raises(ValidationError):
        _tag(tagged_by="   ")
    with pytest.raises(ValidationError):
        _tag(language="de")
    with pytest.raises(ValidationError):
        _tag(tag_source="heuristic")
    with pytest.raises(ValidationError):
        _tag(rationale="")
    with pytest.raises(ValidationError):
        _tag(confidence="high")  # extra fields are forbidden
    with pytest.raises(ValidationError, match="duplicate line tag"):
        PageLineLanguageTags(entry_id="p", annotation_sha256=SHA, lines=[_tag(), _tag()])
    page = PageLineLanguageTags(entry_id="p", annotation_sha256=SHA)
    with pytest.raises(ValidationError, match="duplicate entry_id"):
        LineLanguageTagFile(format="hocrgen.pinkas_line_language_tags.v1", source_id=SOURCE_ID, review_procedure="x", pages=[page, page])


def test_page_scope_stays_character_level_while_any_line_is_untagged_or_not_human_hebrew() -> None:
    lines = [_line("l1", "שלום", 1), _line("l2", "עולם", 2)]

    def summary(*tags: LineLanguageTag, sha: str = SHA) -> dict:
        scopes = derive_line_scopes("p", sha, lines, PageLineLanguageTags(entry_id="p", annotation_sha256=SHA, lines=list(tags)))
        return page_scope_summary(scopes)

    both_he = (_tag("l1", "שלום"), _tag("l2", "עולם"))
    assert summary(*both_he)["page_evaluation_scope"] == "word_level_hebrew"
    assert summary(*both_he)["word_level_hebrew_line_ids"] == ["l1", "l2"]
    # One line untagged.
    one = summary(_tag("l1", "שלום"))
    assert one["page_evaluation_scope"] == "character_level_only"
    assert one["reasons"] == {"human_tagged_he": 1, "untagged": 1}
    assert one["word_level_hebrew_line_ids"] == ["l1"]
    # One line human-tagged Yiddish, mixed or unknown.
    for language in ["yi", "mixed", "unknown"]:
        assert summary(_tag("l1", "שלום"), _tag("l2", "עולם", language=language))["page_evaluation_scope"] == "character_level_only"
    # One line only agent-proposed as Hebrew.
    advisory = summary(_tag("l1", "שלום"), _tag("l2", "עולם", tag_source="agent_proposed"))
    assert advisory["page_evaluation_scope"] == "character_level_only"
    assert advisory["reasons"] == {"agent_proposed_tag_is_advisory": 1, "human_tagged_he": 1}
    # A tag made against other text, or a page block made against another annotation, is stale.
    stale_text = summary(_tag("l1", "שלום"), _tag("l2", "עולם!"))
    assert stale_text["reasons"] == {"human_tagged_he": 1, "tag_stale": 1}
    stale_page = summary(*both_he, sha="b" * 64)
    assert stale_page["page_evaluation_scope"] == "character_level_only"
    assert stale_page["reasons"] == {"tag_stale": 2}
    # No tag block at all.
    assert page_scope_summary(derive_line_scopes("p", SHA, lines, None))["reasons"] == {"untagged": 2}
    assert page_scope_summary([])["page_evaluation_scope"] == "character_level_only"


def test_line_scopes_expose_tag_and_geometry_for_evaluation() -> None:
    lines = [_line("l1", "שלום", 1), _line("l2", "עולם", 2)]
    scopes = derive_line_scopes("p", SHA, lines, PageLineLanguageTags(entry_id="p", annotation_sha256=SHA, lines=[_tag("l1", "שלום")]))
    first, second = scopes
    assert (first.line_id, first.language, first.tag_source, first.tagged_by) == ("l1", "he", "human", "Reviewer Name")
    assert first.evaluation_scope == "word_level_hebrew" and first.geometry == lines[0].geometry
    assert (second.language, second.tag_source, second.evaluation_scope, second.reason) == (None, None, "character_level_only", "untagged")


def test_scope_module_never_imports_the_proposal_heuristic() -> None:
    source = Path(line_language_module.__file__).read_text(encoding="utf-8")
    assert "from hocrgen.tools" not in source and "import hocrgen.tools" not in source


# --- the committed proposal sidecar ---------------------------------------------------------------------------


def test_committed_sidecar_covers_every_fixture_line_with_advisory_proposals_only() -> None:
    snapshot, entries = load_pinkas_dataset_snapshot(SNAPSHOT_ROOT)
    assert snapshot["line_language_tags_path"] == "line_language_tags.yaml"
    tag_file = load_line_language_tags(SNAPSHOT_ROOT, snapshot)
    assert tag_file is not None and tag_file.source_id == SOURCE_ID
    pages = {}
    languages: dict[str, int] = {}
    for entry in entries:
        page = load_entry_page_lines(SNAPSHOT_ROOT, entry)
        pages[entry["entry_id"]] = (entry["annotation"]["sha256"], page.lines)
        page_tags = tag_file.page(entry["entry_id"])
        assert page_tags is not None
        assert [tag.line_id for tag in page_tags.lines] == [line.line_id for line in page.lines]
        for tag in page_tags.lines:
            # An agent never stands in for a human: every committed tag is an advisory proposal.
            assert tag.tag_source == "agent_proposed" and tag.tagged_by == AGENT_PROPOSER_ID
            assert tag.proposal is not None and tag.proposal.language == tag.language
            assert tag.rationale.startswith("pinkas_line_lexicon.v1 proposal")
            languages[tag.language] = languages.get(tag.language, 0) + 1
        scopes = load_entry_line_scopes(SNAPSHOT_ROOT, entry, tag_file)
        assert {scope.evaluation_scope for scope in scopes} == {"character_level_only"}
        assert {scope.reason for scope in scopes} == {"agent_proposed_tag_is_advisory"}
        assert page_scope_summary(scopes)["page_evaluation_scope"] == "character_level_only"
    assert tag_file_problems(tag_file, pages) == []
    assert languages == {"he": 57, "mixed": 13, "unknown": 9}


def test_rerunning_the_proposer_reproduces_the_committed_sidecar() -> None:
    tag_file, notes = tool.build_proposals(SNAPSHOT_ROOT, date(2026, 11, 6))
    assert notes == []
    assert tool.dump_tag_file(tag_file) == (SNAPSHOT_ROOT / "line_language_tags.yaml").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "language", "confidence"),
    [
        ("ונאם שמואל ב\"ר שניאר ז\"ל בינג", "he", "high"),
        ("ונא' הקטין יעקב בכרך", "he", "medium"),
        ("ונא' משה ווימפפן ג\"ק", "he", "low"),
        ("דז ער זאל קיין", "yi", "high"),
        ("ברענגט זאל", "yi", "medium"),
        ("הוט השררה אונ' דורך דעם על כל", "mixed", "high"),
        ("זא זאל דש בכן", "mixed", "medium"),
        ("סנדקית יולדות", "unknown", "low"),
        ("1656", "unknown", "high"),
        ("", "unknown", "high"),
    ],
)
def test_proposal_method_is_a_transparent_lexicon_match(text: str, language: str, confidence: str) -> None:
    proposal, rationale = tool.propose_line_language(text)
    assert (proposal.language, proposal.confidence) == (language, confidence)
    assert proposal.method == "pinkas_line_lexicon.v1"
    assert set(proposal.yiddish_markers) <= tool.YIDDISH_MARKERS
    assert set(proposal.hebrew_markers) <= tool.HEBREW_MARKERS
    assert rationale


def test_proposal_reports_its_evidence() -> None:
    proposal, rationale = tool.propose_line_language("אם לא כשיהיה חיוב, כגון יאר צייט")
    assert proposal.hebrew_markers == ["אם", "לא"]
    assert proposal.orthography_markers == ["צייט"]
    assert "צייט" in rationale and "(low)" in rationale
    assert tool.tokenize("הנ״ל, אונ׳ (זה)") == ['הנ"ל', "אונ'", "זה"]
    assert set(tool.YIDDISH_MARKERS).isdisjoint(tool.HEBREW_MARKERS)


# --- the human review path ------------------------------------------------------------------------------------


def test_human_tags_unlock_word_level_hebrew_per_line_and_survive_reproposal(tmp_path: Path) -> None:
    config_root, root = _copy_snapshot_config(tmp_path)
    _set_human(root, PAGE_105, {"l12", "l14"})
    _set_human(root, PAGE_105, {"l0"}, language="yi")
    bundle, source = _source(config_root)
    importer = PinkasDatasetImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    metadata = {record.source_item_id: record.metadata for record in enriched}
    page = metadata[PAGE_105]
    assert page["evaluation_scope"] == "character_level_only"
    assert page["usage_scope"]["evaluation_scope"] == "character_level_only"
    assert page["line_scope_summary"]["word_level_hebrew_line_ids"] == ["l12", "l14"]
    assert page["line_scope_summary"]["reasons"] == {
        "agent_proposed_tag_is_advisory": 42,
        "human_tagged_he": 2,
        "human_tagged_yi": 1,
    }
    by_id = {line["line_id"]: line for line in page["line_scopes"]}
    assert by_id["l12"]["evaluation_scope"] == "word_level_hebrew" and by_id["l12"]["tagged_by"] == "Test Reviewer"
    assert by_id["l0"]["evaluation_scope"] == "character_level_only" and by_id["l0"]["reason"] == "human_tagged_yi"
    assert "geometry" not in by_id["l12"]
    assert metadata[PAGE_112]["line_scope_summary"]["word_level_hebrew_line_count"] == 0

    # Re-running the proposer keeps every human tag and refreshes only the advisory ones.
    assert tool.main(["propose", "--snapshot-root", str(root), "--tagged-at", "2026-11-07"]) == 0
    tag_file = load_line_language_tags(root, load_pinkas_dataset_snapshot(root)[0])
    tags = {tag.line_id: tag for tag in tag_file.page(PAGE_105).lines}
    assert (tags["l12"].tag_source, tags["l12"].tagged_by, tags["l12"].tagged_at) == ("human", "Test Reviewer", date(2026, 11, 6))
    assert (tags["l0"].language, tags["l0"].tag_source) == ("yi", "human")
    assert tags["l1"].tag_source == "agent_proposed" and tags["l1"].tagged_at == date(2026, 11, 7)

    checks, _, _ = _inspect_source(source, bundle)
    tag_check = next(check for check in checks if check["name"] == "pinkas_dataset_line_language_tags")
    assert tag_check["status"] == "ok"
    assert tag_check["actual"]["line_scopes"] == {"character_level_only": 77, "word_level_hebrew": 2}
    assert tag_check["actual"]["tags"]["human:he"] == 2


def test_whole_page_of_human_hebrew_tags_widens_the_page_scope(tmp_path: Path) -> None:
    config_root, root = _copy_snapshot_config(tmp_path)
    entry = next(entry for entry in load_pinkas_dataset_snapshot(root)[1] if entry["entry_id"] == PAGE_112)
    _set_human(root, PAGE_112, {line.line_id for line in load_entry_page_lines(root, entry).lines})
    bundle, source = _source(config_root)
    importer = PinkasDatasetImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    scopes = {record.source_item_id: record.metadata["evaluation_scope"] for record in enriched}
    assert scopes == {PAGE_105: "character_level_only", PAGE_112: "word_level_hebrew"}


def test_source_health_flags_stale_and_malformed_sidecars(tmp_path: Path) -> None:
    bundle, source = _source()
    checks, _, _ = _inspect_source(source, bundle)
    tag_check = next(check for check in checks if check["name"] == "pinkas_dataset_line_language_tags")
    assert tag_check["status"] == "ok"
    assert tag_check["actual"] == {
        "tags": {"agent_proposed:he": 57, "agent_proposed:mixed": 13, "agent_proposed:unknown": 9},
        "line_scopes": {"character_level_only": 79, "word_level_hebrew": 0},
    }
    assert tool.main(["check"]) == 0

    config_root, root = _copy_snapshot_config(tmp_path)
    path = root / "line_language_tags.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["pages"][0]["lines"][0]["text"] += " x"
    payload["pages"][1]["lines"].append(dict(payload["pages"][1]["lines"][0], line_id="l999"))
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    bundle, source = _source(config_root)
    checks, candidate_count, _ = _inspect_source(source, bundle)
    assert candidate_count == 2
    failing = [check for check in checks if check["status"] == "error"]
    assert [check["name"] for check in failing] == ["pinkas_dataset_line_language_tags"]
    assert f"{PAGE_105}:l0: line_text_changed" in failing[0]["message"]
    assert f"{PAGE_112}:l999: unknown_line_id" in failing[0]["message"]
    assert tool.main(["check", "--snapshot-root", str(root)]) == 1

    payload["pages"][0]["lines"][0]["tag_source"] = "guessed"
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    checks, _, _ = _inspect_source(source, bundle)
    tag_check = next(check for check in checks if check["name"] == "pinkas_dataset_line_language_tags")
    assert tag_check["status"] == "error" and "invalid Pinkas line language tags" in tag_check["message"]
    with pytest.raises(StageExecutionError, match="invalid Pinkas line language tags"):
        load_line_language_tags(root, load_pinkas_dataset_snapshot(root)[0])
    assert tool.main(["check", "--snapshot-root", str(root)]) == 1


def test_missing_sidecar_leaves_every_line_untagged(tmp_path: Path) -> None:
    config_root, root = _copy_snapshot_config(tmp_path)
    (root / "line_language_tags.yaml").unlink()
    bundle, source = _source(config_root)
    importer = PinkasDatasetImporter()
    options = StageOptions()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, options), options)
    for record in enriched:
        assert record.metadata["evaluation_scope"] == "character_level_only"
        assert set(record.metadata["line_scope_summary"]["reasons"]) == {"untagged"}
    checks, _, _ = _inspect_source(source, bundle)
    tag_check = next(check for check in checks if check["name"] == "pinkas_dataset_line_language_tags")
    assert tag_check == {"name": "pinkas_dataset_line_language_tags", "status": "ok", "actual": {"tags": {}, "line_scopes": {"character_level_only": 79, "word_level_hebrew": 0}}}


def test_malformed_sidecar_yaml_is_a_recorded_failure_not_a_crash(tmp_path: Path) -> None:
    config_root, root = _copy_snapshot_config(tmp_path)
    (root / "line_language_tags.yaml").write_text("pages: [unclosed\n", encoding="utf-8")
    with pytest.raises(StageExecutionError, match="invalid Pinkas line language tags in line_language_tags.yaml"):
        load_line_language_tags(root, load_pinkas_dataset_snapshot(root)[0])
    bundle, source = _source(config_root)
    checks, candidate_count, _ = _inspect_source(source, bundle)
    assert candidate_count == 2
    tag_check = next(check for check in checks if check["name"] == "pinkas_dataset_line_language_tags")
    assert tag_check["status"] == "error" and str(tmp_path) not in tag_check["message"]
    assert tool.main(["check", "--snapshot-root", str(root)]) == 1


def test_reproposal_refuses_to_rebind_human_tags_to_a_changed_annotation(tmp_path: Path) -> None:
    _, root = _copy_snapshot_config(tmp_path)
    _set_human(root, PAGE_105, {"l12"})
    path = root / "line_language_tags.yaml"
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    payload["pages"][0]["annotation_sha256"] = "c" * 64
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    with pytest.raises(StageExecutionError, match="re-review them"):
        tool.build_proposals(root, date(2026, 11, 7))
    assert tool.main(["propose", "--snapshot-root", str(root)]) == 1
    assert path.read_text(encoding="utf-8") == before
    # The stale human tag gives no word-level scope meanwhile.
    entry = next(entry for entry in load_pinkas_dataset_snapshot(root)[1] if entry["entry_id"] == PAGE_105)
    scopes = load_entry_line_scopes(root, entry, load_line_language_tags(root, load_pinkas_dataset_snapshot(root)[0]))
    assert {scope.reason for scope in scopes} == {"tag_stale"}
