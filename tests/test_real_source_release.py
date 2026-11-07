"""F8g: the real-source composition contract, work-group leakage governance, release terms and the real tranche."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from pydantic import ValidationError

from hocrgen.benchmark import benchmark_holdout_leakage_artifact
from hocrgen.cli import main
from hocrgen.composition import item_modality
from hocrgen.config.loader import default_config_root, load_and_validate_bundle, package_root
from hocrgen.config.models import RealSourceContract, RealSourceModality, SyntheticTrainingWorkRegistry
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import BenchmarkLeakagePolicyRecord, CuratedItemRecord
from hocrgen.package.release_terms import attribution_manifest, item_release_terms, notice_doc, paired_text_for_item
from hocrgen.real_tranche import (
    TRANCHE_CHECKSUMS,
    apply_real_tranche,
    load_committed_manifest,
    tranche_problems,
    verify_tranche_files,
)
from hocrgen.source_ops import _format_health_path
from hocrgen.split.assign import _validate_leakage, assign_splits
from hocrgen.split.work_groups import item_work_group_keys
from hocrgen.tools import real_tranche as tranche_tool

CONTRACT_PATH = default_config_root() / "real_source_contract.yaml"
PROMOTED = (
    "wikisource_he_proofread",
    "yidtaknl_vaybertaytsh_gt",
    "pinkas_dataset_bgu",
    "reshumot_born_digital",
    "knesset_committee_protocols_pre1976",
)


def _contract_data() -> dict:
    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def _copy_config(tmp_path: Path) -> Path:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    return config_root


# --- the composition contract ----------------------------------------------------------------------------------


def test_packaged_contract_admits_every_promoted_source_with_floors_caps_and_modalities() -> None:
    bundle = load_and_validate_bundle()
    contract = bundle.real_source_contract
    assert contract.contract_id == "real_source_composition.v2"
    assert contract.min_real_items == 80
    assert contract.modality_floors == {RealSourceModality.printed: 30, RealSourceModality.handwritten: 25}
    for source_id in PROMOTED:
        entry = contract.entry(source_id)
        assert entry.promotion.value == "promoted"
        assert entry.planning_notation == "F8g"
        source = next(source for source in bundle.source_registry.sources if source.id == source_id)
        assert source.status.value == "allowed" and source.default_public_release is True
        assert source_id in bundle.profiles["profile_open_v1"].include_sources
    # The 27 / 27 / 26 legacy sources stay, with no floor; HASH waits for F7d with the same contract shape.
    assert {entry.source_id: entry.floor for entry in contract.sources if entry.promotion.value == "legacy"} == {
        "nli_any_use_permitted": 0,
        "pinkas_open": 0,
        "biblia_open": 0,
    }
    assert {entry.source_id for entry in contract.sources if entry.promotion.value == "not_promoted"} == {
        "hash_nli_any_use",
        "hash_public_domain",
    }
    assert contract.entry("reshumot_born_digital").counts_toward_modality_floors is False
    assert contract.entry("reshumot_born_digital").release_terms.rendered_not_scan is True
    assert contract.entry("yidtaknl_vaybertaytsh_gt").release_terms.evaluation_scope.value == "character_level_only"
    assert contract.entry("pinkas_dataset_bgu").release_terms.evaluation_scope.value == "per_line"
    assert contract.entry("wikisource_he_proofread").release_terms.share_alike is True


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["sources"][0].update(floor=50, cap=40), "exceeds cap"),
        (lambda data: next(s for s in data["sources"] if s["source_id"] == "hash_nli_any_use").update(floor=1), "not_promoted source cannot carry a floor"),
        (lambda data: data["sources"].append(dict(data["sources"][0])), "duplicate real-source contract entries"),
        (lambda data: data["modality_floors"].update(handwritten=79), "modality floors exceed min_real_items"),
        (lambda data: data.update(min_real_items=1000), "cannot be reached under the caps"),
        (lambda data: data["modality_content_types"]["handwritten"].append("printed_modern"), "maps to both"),
        (lambda data: data["sources"][0]["release_terms"].update(attribution_required=False), "share-alike terms always require attribution"),
    ],
)
def test_contract_model_rejects_incoherent_contracts(mutate, message: str) -> None:
    data = _contract_data()
    mutate(data)
    with pytest.raises(ValidationError, match=message):
        RealSourceContract.model_validate(data)


def test_contract_reachable_floor_check_counts_only_scan_sources() -> None:
    data = _contract_data()
    for entry in data["sources"]:
        if "printed" in entry["modalities"] and entry["source_id"] != "reshumot_born_digital":
            entry["cap"] = max(entry["floor"], 1)
    with pytest.raises(ValidationError, match="printed floor 30 cannot be reached"):
        RealSourceContract.model_validate(data)


@pytest.mark.parametrize(
    ("edit", "problem"),
    [
        ("drop_entry", "allowed_real_source_missing_from_contract"),
        ("unknown_source", "unknown_source"),
        ("licence", "release_terms_licence_mismatch"),
        ("hash_public", "not_promoted_source_is_public"),
        ("wikisource_review_only", "contract_source_not_public"),
    ],
)
def test_bundle_binds_the_contract_to_the_source_registry(tmp_path: Path, edit: str, problem: str) -> None:
    config_root = _copy_config(tmp_path)
    contract = _contract_data()
    if edit == "drop_entry":
        contract["sources"] = [entry for entry in contract["sources"] if entry["source_id"] != "knesset_committee_protocols_pre1976"]
    elif edit == "unknown_source":
        contract["sources"][-1]["source_id"] = "no_such_source"
    elif edit == "licence":
        contract["sources"][0]["release_terms"]["licence"] = "CC-BY-4.0"
    sources_path = config_root / "sources.yaml"
    sources = sources_path.read_text(encoding="utf-8")
    if edit == "hash_public":
        sources = sources.replace(
            "  - id: hash_nli_any_use\n    name: HASH (HeOCR/hash) NLI Any Use Permitted handwritten scans\n    fetcher: hash\n    status: review_only\n    default_public_release: false",
            "  - id: hash_nli_any_use\n    name: HASH (HeOCR/hash) NLI Any Use Permitted handwritten scans\n    fetcher: hash\n    status: allowed\n    default_public_release: true",
        )
    if edit == "wikisource_review_only":
        block = sources[sources.index("  - id: wikisource_he_proofread") :]
        block = block[: block.index("  - id: ", 5)]
        sources = sources.replace(block, block.replace("status: allowed", "status: review_only"))
    sources_path.write_text(sources, encoding="utf-8")
    (config_root / "real_source_contract.yaml").write_text(yaml.safe_dump(contract, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ConfigValidationError) as excinfo:
        load_and_validate_bundle(config_root)
    assert problem in json.dumps(excinfo.value.details)


def test_item_modality_prefers_the_declared_content_type() -> None:
    contract = load_and_validate_bundle().real_source_contract
    assert item_modality(SimpleNamespace(metadata={"content_type": "typewritten_historical"}, content_class="handwritten"), contract) == RealSourceModality.printed
    assert item_modality(SimpleNamespace(metadata={"content_type": "manuscript_scan"}), contract) == RealSourceModality.handwritten
    assert item_modality(SimpleNamespace(metadata={}, content_class="printed"), contract) == RealSourceModality.printed
    assert item_modality(SimpleNamespace(metadata={}, content_class="mixed"), contract) is None


# --- leakage governance --------------------------------------------------------------------------------------


def _curated(item_id: str, source_id: str, *, source_group_id: str | None = None, dedupe: str | None = None, **metadata) -> CuratedItemRecord:
    return CuratedItemRecord.model_construct(
        item_id=item_id,
        source_id=source_id,
        source_item_id=item_id.split(":", 1)[1],
        source_url="",
        metadata=metadata,
        raw_metadata={},
        dedupe_cluster_id=dedupe,
        near_duplicate_cluster_id=None,
        source_group_id=source_group_id,
        split=None,
        split_group_id=None,
        is_synthetic=False,
    )


def test_work_group_keys_tie_items_of_one_nli_record_commons_file_or_writer() -> None:
    yid = _curated("yidtaknl_vaybertaytsh_gt:p1", "yidtaknl_vaybertaytsh_gt", scan_record_id="001294844", scan_holding_institution="National Library of Israel")
    nli = SimpleNamespace(source_id="nli_any_use_permitted", source_url="https://www.nli.org.il/en/books/NNL_ALEPH990012682410205171", metadata={})
    ws = _curated("wikisource_he_proofread:p", "wikisource_he_proofread", scan_commons_file_sha1="abc")
    hash_item = _curated("hash_nli_any_use:x", "hash_nli_any_use", writer_group_id="creator-1", work_group_ids=["edition:x", "bad"])
    huc = _curated("yidtaknl_vaybertaytsh_gt:huc", "yidtaknl_vaybertaytsh_gt", scan_record_id="RBR O 128", scan_holding_institution="Hebrew Union College")
    assert item_work_group_keys(yid) == ["nli_record:001294844"]
    assert item_work_group_keys(nli) == ["nli_record:990012682410205171"]
    assert item_work_group_keys(ws) == ["commons_file:abc"]
    assert item_work_group_keys(hash_item) == ["edition:x", "writer:creator-1"]
    assert item_work_group_keys(huc) == []


def test_split_keeps_connected_groups_whole_across_sources() -> None:
    policy = load_and_validate_bundle().profiles["profile_open_v1"].split_policy
    items = [
        _curated(f"wikisource_he_proofread:index_a__p{n}", "wikisource_he_proofread", source_group_id="sg-index-a", scan_commons_file_sha1="sha-a")
        for n in range(12)
    ]
    # A second source showing the same Commons scan file joins the Index's component.
    items.append(_curated("other_source:page", "other_source", scan_commons_file_sha1="sha-a"))
    items += [_curated(f"pinkas_dataset_bgu:p{n}", "pinkas_dataset_bgu", source_group_id="sg-pinkas", scan_record_id="990000445290205171", scan_holding_institution="National Library of Israel") for n in range(5)]
    items.append(_curated("nli_any_use_permitted:pinkas-record", "nli_any_use_permitted", scan_record_id="990000445290205171", scan_holding_institution="National Library of Israel"))
    singleton = _curated("pinkas_open:loose", "pinkas_open")
    outputs = assign_splits([*items, singleton], [], policy)
    by_id = {item.item_id: item for item in outputs.retained_items}
    assert len({by_id[item.item_id].split for item in items[:13]}) == 1
    assert len({by_id[item.item_id].split_group_id for item in items[:13]}) == 1
    assert len({by_id[item.item_id].split for item in items[13:]}) == 1
    # A singleton keeps its F1d split group id.
    assert by_id["pinkas_open:loose"].split_group_id == "pinkas_open:loose"
    assignments = {assignment.item_id: assignment for assignment in outputs.assignments}
    assert assignments["other_source:page"].work_group_ids == ["commons_file:sha-a"]
    assert outputs.leakage_report["status"] == "ok"
    assert outputs.leakage_report["work_group_leaks"] == []


def test_synthetic_training_works_stay_in_train_with_their_whole_group() -> None:
    policy = load_and_validate_bundle().profiles["profile_open_v1"].split_policy
    items = [
        _curated(f"wikisource_he_proofread:w__p{n}", "wikisource_he_proofread", source_group_id=f"sg-{n % 40}", scan_commons_file_sha1=f"sha-{n % 40}")
        for n in range(80)
    ]
    keys = {f"commons_file:sha-{n}": [f"pby:{n}"] for n in range(40)}
    outputs = assign_splits(items, [], policy, synthetic_training_keys=keys)
    assert {item.split for item in outputs.retained_items} == {"train"}
    overlap = outputs.leakage_report["synthetic_training_overlap"]
    assert overlap["matched_item_count"] == 80 and overlap["holdout_leak_item_ids"] == []
    assert {assignment.split_constraint for assignment in outputs.assignments} == {"synthetic_training_overlap"}
    assert outputs.leakage_report["forced_train_group_count"] == 40
    # Without the registry the same items spread over the splits.
    assert {item.split for item in assign_splits(items, [], policy).retained_items} != {"train"}


def test_leakage_validation_reports_work_group_and_synthetic_training_leaks() -> None:
    first = _curated("a:1", "a", scan_commons_file_sha1="s").model_copy(update={"split": "train", "split_group_id": "g1"})
    second = _curated("b:1", "b", scan_commons_file_sha1="s").model_copy(update={"split": "test", "split_group_id": "g2"})
    report = _validate_leakage([first, second], {"b:1": ["pby:1"]})
    assert report["status"] == "error"
    assert report["work_group_leaks"] == [{"group_id": "commons_file:s", "splits": ["test", "train"]}]
    assert report["synthetic_training_overlap"]["holdout_leak_item_ids"] == ["b:1"]


def test_benchmark_leakage_covers_work_groups_and_synthetic_training_works() -> None:
    benchmark = _curated("nli_any_use_permitted:bench", "nli_any_use_permitted", scan_record_id="1", scan_holding_institution="National Library of Israel").model_copy(update={"split": "train"})
    other = _curated("yidtaknl_vaybertaytsh_gt:page", "yidtaknl_vaybertaytsh_gt", scan_record_id="1", scan_holding_institution="National Library of Israel").model_copy(update={"split": "train"})
    artifact = benchmark_holdout_leakage_artifact(
        benchmark_items=[SimpleNamespace(item_id=benchmark.item_id)],
        release_ready_items=[benchmark, other],
        removed_duplicate_items=[],
        policy=BenchmarkLeakagePolicyRecord(policy="block"),
        enforcement_context="build_release",
        synthetic_training_keys={"nli_record:1": ["pby:77"]},
    )
    kinds = {(risk["group_kind"], risk["group_id"]) for risk in artifact["unresolved_risks"]}
    assert ("work_group", "nli_record:1") in kinds
    assert ("synthetic_training_work", "pby:77") in kinds
    assert artifact["status"] == "blocked"


def test_synthetic_training_registry_is_packaged_empty_and_validated() -> None:
    registry = load_and_validate_bundle().synthetic_training_works
    assert registry.registry_id == "synthetic_training_works.v1"
    assert {producer.producer for producer in registry.producers} == {"HeOCR/hocrsyngen", "HeOCR/hletterscriptgen"}
    assert registry.works == [] and registry.match_keys() == {}
    base = registry.model_dump(mode="json")
    work = {"work_id": "pby:1", "producer": "HeOCR/hocrsyngen", "match_keys": ["nli_record:9"], "recorded_by": "agent", "recorded_at": "2026-11-06"}
    assert SyntheticTrainingWorkRegistry.model_validate({**base, "works": [work]}).match_keys() == {"nli_record:9": ["pby:1"]}
    with pytest.raises(ValidationError, match="unregistered producers"):
        SyntheticTrainingWorkRegistry.model_validate({**base, "works": [{**work, "producer": "someone"}]})
    with pytest.raises(ValidationError, match="duplicate"):
        SyntheticTrainingWorkRegistry.model_validate({**base, "works": [work, work]})
    with pytest.raises(ValidationError, match="must be <kind>:<value>"):
        SyntheticTrainingWorkRegistry.model_validate({**base, "works": [{**work, "match_keys": ["nokind"]}]})


# --- release terms, paired text and NOTICE ---------------------------------------------------------------------


def _export_item(source_id: str, *, licence: str, classification: str, metadata: dict, raw: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        item_id=f"{source_id}:x",
        source_id=source_id,
        source_url="https://example.org/x",
        normalized_license=licence,
        rights_classification=SimpleNamespace(value=classification),
        metadata=metadata,
        raw_metadata=raw or {},
    )


CHAR_SCOPE = {"evaluation_scope": "character_level_only", "allowed_uses": ["training", "character_level_evaluation"], "excluded_evaluations": ["word_level", "language_level_hebrew"]}


def test_release_terms_carry_each_promoted_source_scope_marker() -> None:
    contract = load_and_validate_bundle().real_source_contract
    ws = item_release_terms(
        _export_item("wikisource_he_proofread", licence="CC-BY-SA-4.0", classification="sharealike", metadata={"text_license": "CC-BY-SA-4.0", "text_attribution": "Hebrew Wikisource contributors, https://he.wikisource.org/w/index.php?oldid=1"}),
        contract,
    )
    assert (ws.share_alike, ws.attribution_required, ws.evaluation_scope, ws.paired_text) == (True, True, "full_hebrew", "page_text")
    yid = item_release_terms(
        _export_item("yidtaknl_vaybertaytsh_gt", licence="CC-BY-4.0", classification="open_with_attribution", metadata={"usage_scope": CHAR_SCOPE, "evaluation_scope": "character_level_only", "attribution_text": "Reshef and Gutschow", "text_reference": "t"}),
        contract,
    )
    assert yid.evaluation_scope == "character_level_only" and {"word_level", "language_level_hebrew"} <= set(yid.excluded_evaluations)
    pinkas = item_release_terms(
        _export_item("pinkas_dataset_bgu", licence="CC-BY-4.0", classification="open_with_attribution", metadata={"usage_scope": CHAR_SCOPE, "evaluation_scope": "character_level_only", "line_scope_summary": {"line_count": 3}, "attribution_text": "Kurar Barakat et al."}),
        contract,
    )
    assert pinkas.line_scope_summary == {"line_count": 3} and pinkas.paired_text == "page_xml"
    reshumot = item_release_terms(
        _export_item("reshumot_born_digital", licence="PD-IL", classification="open", metadata={"is_scan": False, "text_reference": "t"}),
        contract,
    )
    assert reshumot.rendered_not_scan is True and reshumot.text_licence == "PD-IL"


@pytest.mark.parametrize(
    ("source_id", "licence", "classification", "metadata", "problem"),
    [
        ("wikisource_he_proofread", "CC-BY-SA-4.0", "sharealike", {}, "attribution"),
        ("yidtaknl_vaybertaytsh_gt", "CC-BY-4.0", "open_with_attribution", {"attribution_text": "a"}, "character_level_only_scope_missing"),
        ("yidtaknl_vaybertaytsh_gt", "CC-BY-4.0", "open_with_attribution", {"attribution_text": "a", "evaluation_scope": "character_level_only", "usage_scope": {"evaluation_scope": "character_level_only", "excluded_evaluations": ["word_level"]}}, "character_level_exclusions_missing"),
        ("pinkas_dataset_bgu", "CC-BY-4.0", "open_with_attribution", {"attribution_text": "a"}, "per_line_scope_missing"),
        ("reshumot_born_digital", "PD-IL", "open", {"is_scan": True}, "rendered_not_scan_flag_missing"),
        ("knesset_committee_protocols_pre1976", "CC-BY-4.0", "open", {}, "licence CC-BY-4.0 != PD-IL"),
        ("hash_nli_any_use", "PD-IL", "open", {}, "source_not_promoted"),
    ],
)
def test_release_terms_refuse_items_that_cannot_carry_their_source_terms(source_id, licence, classification, metadata, problem) -> None:
    contract = load_and_validate_bundle().real_source_contract
    with pytest.raises((StageExecutionError, ValidationError), match=problem):
        item_release_terms(_export_item(source_id, licence=licence, classification=classification, metadata=metadata), contract)


def test_paired_text_is_read_and_checked_from_the_snapshot(tmp_path: Path) -> None:
    (tmp_path / "text").mkdir()
    (tmp_path / "text" / "p.txt").write_text("שורה\n", encoding="utf-8")
    page_sha = hashlib.sha256("שורה".encode()).hexdigest()
    item = _export_item("w", licence="x", classification="open", metadata={"page_text_ref": "text/p.txt", "page_text_sha256": page_sha}, raw={"snapshot_root": str(tmp_path)})
    assert paired_text_for_item(item).role == "page_text"
    item.metadata["page_text_sha256"] = "0" * 64
    with pytest.raises(StageExecutionError, match="paired text checksum mismatch"):
        paired_text_for_item(item)
    xml = b"<PcGts><TextLine/></PcGts>"
    (tmp_path / "a.xml.gz").write_bytes(gzip.compress(xml, mtime=0))
    item = _export_item("p", licence="x", classification="open", metadata={"annotation_reference": "a.xml.gz", "annotation_encoding": "gzip", "expected_annotation_sha256": hashlib.sha256(xml).hexdigest()}, raw={"snapshot_root": str(tmp_path)})
    assert paired_text_for_item(item).content == xml
    item.metadata["annotation_reference"] = "missing.xml.gz"
    with pytest.raises(StageExecutionError, match="paired text missing"):
        paired_text_for_item(item)
    with pytest.raises(StageExecutionError, match="no snapshot root"):
        paired_text_for_item(_export_item("y", licence="x", classification="open", metadata={"text_reference": "t"}))
    assert paired_text_for_item(_export_item("n", licence="x", classification="open", metadata={})) is None


def test_public_beta_export_ships_texts_terms_and_a_complete_notice(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "exports" / "public-beta-v0"
    assert main(["export-public-beta", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "work"), "--output-dir", str(output_dir)]) == 0
    capsys.readouterr()
    items = json.loads((output_dir / "manifests" / "item_manifest.json").read_text(encoding="utf-8"))["items"]
    by_source: dict[str, list[dict]] = {}
    for item in items:
        by_source.setdefault(item["source_id"], []).append(item)
    assert set(PROMOTED) <= set(by_source)
    for item in by_source["wikisource_he_proofread"] + by_source["yidtaknl_vaybertaytsh_gt"] + by_source["pinkas_dataset_bgu"] + by_source["reshumot_born_digital"]:
        assert len(item["exported_texts"]) == 1
        text = item["exported_texts"][0]
        path = output_dir / text["release_text_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == text["sha256"]
    assert all(not item["exported_texts"] for item in by_source["knesset_committee_protocols_pre1976"])
    assert {item["release_terms"]["evaluation_scope"] for item in by_source["yidtaknl_vaybertaytsh_gt"]} == {"character_level_only"}
    assert all(item["release_terms"]["share_alike"] for item in by_source["wikisource_he_proofread"])
    assert all(item["release_terms"]["rendered_not_scan"] for item in by_source["reshumot_born_digital"])
    assert all(item["release_terms"]["line_scope_summary"] for item in by_source["pinkas_dataset_bgu"])
    manifest = json.loads((output_dir / "manifests" / "attribution_manifest.json").read_text(encoding="utf-8"))
    sources = {source["source_id"]: source for source in manifest["sources"]}
    assert sources["wikisource_he_proofread"]["share_alike"] is True
    assert len(sources["wikisource_he_proofread"]["attributed_items"]) == len(by_source["wikisource_he_proofread"])
    assert all("Hebrew Wikisource contributors" in entry["attribution_text"] for entry in sources["wikisource_he_proofread"]["attributed_items"])
    assert sources["pinkas_dataset_bgu"]["attribution_required"] is True
    notice = (output_dir / "docs" / "NOTICE.md").read_text(encoding="utf-8")
    for source_id in PROMOTED:
        assert f"## `{source_id}`" in notice
    assert "CC BY-SA 4.0" in notice and "character-level" in notice and "not scans" in notice
    card = (output_dir / "docs" / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "## Real Source Composition" in card and "real_source_composition.v2" in card
    payload = (output_dir / "manifests" / "item_manifest.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in payload
    assert not re.search(r'"/(Users|home|private|tmp)/', payload)


def test_alpha_export_writes_notice_and_attribution(tmp_path: Path, capsys) -> None:
    output_dir = tmp_path / "alpha-v0"
    assert main(["export-alpha", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "work"), "--output-dir", str(output_dir), "--max-real-items", "40"]) == 0
    capsys.readouterr()
    assert (output_dir / "docs" / "NOTICE.md").is_file()
    manifest = json.loads((output_dir / "manifests" / "attribution_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema"] == "hocrgen_attribution_manifest.v1"
    assert {source["source_id"] for source in manifest["sources"]} >= {"wikisource_he_proofread", "pinkas_dataset_bgu"}


def test_notice_doc_renders_every_source_section() -> None:
    contract = load_and_validate_bundle().real_source_contract
    item = SimpleNamespace(
        item_id="wikisource_he_proofread:x",
        source_id="wikisource_he_proofread",
        source_url="u",
        exported_texts=[1],
        release_terms=SimpleNamespace(licence="CC-BY-SA-4.0", attribution_required=True, attribution_text="Hebrew Wikisource contributors", share_alike=True, evaluation_scope="full_hebrew", rendered_not_scan=False),
    )
    manifest = attribution_manifest([item], contract)
    assert manifest["sources"][0]["paired_text_count"] == 1
    assert "Share-alike: yes" in notice_doc(manifest, title="t")


# --- the real tranche --------------------------------------------------------------------------------------------


def _small_tranche(tmp_path: Path) -> tuple[Path, Path]:
    """A tranche tree built from the packaged Wikisource fixture snapshot, plus its manifest."""

    root = tmp_path / "tranche"
    snapshot = root / "sources" / "wikisource_he_proofread" / "snapshot"
    shutil.copytree(package_root() / "data" / "wikisource" / "snapshot", snapshot)
    tranche_tool.write_descriptor(root, created_at="2026-11-06", results={"wikisource_he_proofread": {"item_count": 5}}, inputs={"fixture": True})
    manifest, items = tranche_tool.build_manifest(root)
    manifest_dir = tmp_path / "manifest"
    manifest_dir.mkdir()
    (manifest_dir / "tranche_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root, manifest_dir / "tranche_manifest.json"


def test_apply_real_tranche_points_sources_at_the_checked_tree(tmp_path: Path) -> None:
    root, manifest_path = _small_tranche(tmp_path)
    bundle = apply_real_tranche(load_and_validate_bundle(), root, manifest_path=manifest_path)
    source = next(source for source in bundle.source_registry.sources if source.id == "wikisource_he_proofread")
    assert source.settings.extra["wikisource_snapshot_root"] == str((root / "sources" / "wikisource_he_proofread" / "snapshot").resolve())
    other = next(source for source in bundle.source_registry.sources if source.id == "yidtaknl_vaybertaytsh_gt")
    assert other.settings.extra["yidtaknl_snapshot_root"] == "package://data/yidtaknl/snapshot"
    # Source health writes tranche-relative paths, never the operator's absolute folder.
    assert _format_health_path(root / "sources" / "x", bundle) == "tranche://sources/x"
    assert verify_tranche_files(root) == []


def test_tranche_checks_detect_tampering(tmp_path: Path) -> None:
    root, manifest_path = _small_tranche(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pages = root / "sources" / "wikisource_he_proofread" / "snapshot" / "pages.jsonl"
    pages.write_text(pages.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    (root / "stray.bin").write_bytes(b"x")
    assert "wikisource_he_proofread: sources/wikisource_he_proofread/snapshot/pages.jsonl differs from the committed manifest" in tranche_problems(root, manifest)
    problems = verify_tranche_files(root)
    assert "unlisted stray.bin" in problems
    assert any(problem.startswith("checksum mismatch sources/wikisource_he_proofread/snapshot/pages.jsonl") for problem in problems)
    with pytest.raises(ConfigValidationError, match="does not match the committed manifest"):
        apply_real_tranche(load_and_validate_bundle(), root, manifest_path=manifest_path)
    assert tranche_problems(tmp_path / "nowhere", manifest) == ["missing tranche.json"]
    assert "no committed tranche manifest" in tranche_problems(root, None)
    (root / TRANCHE_CHECKSUMS).unlink()
    assert f"missing {TRANCHE_CHECKSUMS}" in tranche_problems(root, manifest)


def test_build_release_reads_a_tranche_through_the_cli(tmp_path: Path, monkeypatch, capsys) -> None:
    root, manifest_path = _small_tranche(tmp_path)
    monkeypatch.setattr("hocrgen.real_tranche.COMMITTED_MANIFEST", "package://does/not/matter")
    monkeypatch.setattr("hocrgen.real_tranche.load_committed_manifest", lambda path=None: json.loads(manifest_path.read_text(encoding="utf-8")))
    assert main(["build-release", "--profile", "profile_open_v1", "--dry-run", "--workdir", str(tmp_path / "work"), "--real-tranche-root", str(root)]) == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    health = (run_dir / "discover" / "source_health.json").read_text(encoding="utf-8")
    assert "tranche://sources/wikisource_he_proofread/snapshot" in health
    assert str(root) not in health


def test_committed_tranche_manifest_is_coherent_and_holds_no_page_text() -> None:
    manifest = load_committed_manifest()
    assert manifest["schema"] == "hocrgen_real_tranche_manifest.v1"
    assert manifest["tranche_id"] == tranche_tool.TRANCHE_ID
    lines = (package_root() / "data" / "real_tranche" / manifest["items_path"]).read_text(encoding="utf-8").splitlines()
    items = [json.loads(line) for line in lines]
    assert len(items) == manifest["item_count"] == sum(source["item_count"] for source in manifest["sources"].values())
    contract = load_and_validate_bundle().real_source_contract
    allowed_keys = {"source_id", "source_item_id", "source_group", "modality", "asset", "page_image", "text", "cropped", "quality", "provenance"}
    for item in items:
        assert set(item) <= allowed_keys
        entry = contract.entry(item["source_id"])
        assert entry is not None and item["modality"] in {modality.value for modality in entry.modalities}
        assert re.fullmatch(r"[0-9a-f]{64}", item["asset"]["sha256"])
        # Knesset scans are images only (F8g2); every other tranche item pairs a text.
        assert (item["text"] is None) == (item["source_id"] == "knesset_committee_protocols_pre1976")
        assert set(item["text"] or {}) <= {"path", "sha256", "sha256_without_final_newline"}
    assert {source_id: source["item_count"] for source_id, source in manifest["sources"].items()} == {
        "knesset_committee_protocols_pre1976": 205,
        "pinkas_dataset_bgu": 30,
        "reshumot_born_digital": 798,
        "wikisource_he_proofread": 1455,
        "yidtaknl_vaybertaytsh_gt": 123,
    }
    assert manifest["sources"]["pinkas_dataset_bgu"]["canvas_match_verified"] == 6
    assert manifest["sources"]["reshumot_born_digital"]["pages_passed"] == 796
    assert "not published" in manifest["hosting"]


def test_capture_verifies_every_download_against_its_pin(tmp_path: Path) -> None:
    plan = tranche_tool.yidtaknl_capture_plan()
    assert len(plan) == 154 and sum(1 for row in plan if not row["text_bytes"]) == 33
    with pytest.raises(RuntimeError, match="does not match its pinned SHA-1"):
        tranche_tool.capture_yidtaknl(tmp_path, delay=0, fetch=lambda url, headers: b"not the page")
    with pytest.raises(RuntimeError, match="Zenodo MD5"):
        tranche_tool.capture_pinkas(tmp_path, fetch=lambda url, headers: b"not the zip")


def test_offline_wikisource_replay_refuses_cache_misses(tmp_path: Path) -> None:
    client = tranche_tool.CacheOnlyClient(tmp_path)
    with pytest.raises(RuntimeError, match="not in the operator cache"):
        client("https://he.wikisource.org/w/api.php", {"action": "query"})
