"""Decision 0017: heocr-eval's P-mod evaluation units are pinned out of train and refused as training input."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from hocrgen.config.loader import load_and_validate_bundle, package_root
from hocrgen.config.models import EvalReservedUnitsRegistry, EvalUnitStatus
from hocrgen.core.errors import StageExecutionError
from hocrgen.manifests.models import CuratedItemRecord
from hocrgen.package.common import copy_export_assets
from hocrgen.split.assign import _validate_leakage, assign_splits, eval_reserved_statuses
from hocrgen.split.balance import EVAL_RESERVED_SPLIT, SplitGroup, assign_group_splits, split_balance_report
from hocrgen.split.eval_reserved import (
    EvalReservedUnitError,
    governed_unit,
    refuse_eval_reserved_training_input,
    unit_from_identifier,
    unit_status,
)
from hocrgen.tools import benyehuda_nli_lines as bl
from hocrgen.tools import eval_reserved_units as tool
from hocrgen.tools import glyph_harvest as gh
from hocrgen.tools import wikisource_lines as wl

RESHUMOT, KNESSET = "reshumot_born_digital", "knesset_committee_protocols_pre1976"
POLICY = {"train": 0.8, "validation": 0.1, "test": 0.1}
V1_SHA256 = "184d3b77d80dc26330665271aa81e1eace722299aa2962f5b641970b9741562e"
V2_SHA256 = "a75ed6851e8d9a689994f4ec5c61bae46e4a75dc2e51648f7a5e494306c25be7"
V3_SHA256 = "36ab37e6f8936581ecc5647a590348c6cc244861fa50f1983dc5ccec3dad6d95"
V4_SHA256 = "c641b1e31e734fce09c1ec5833ac30b553bbef162b536c9f39b31a968d3a21a5"
V5_SHA256 = "873cef9c30b41ccace7720258f1dcfe9db83d78c67317edbff698960c5ac8a45"
CURRENT = "pmod_unit_split_v6.json"
CURRENT_SHA256 = "2519bc8fe5565570de41b064dc5ae3d9db7d30ed4a6d79e1224781089fc50aab"
# v2 = v1 unchanged plus the 121 born-digital 2005 booklets (all non_eval); 175 = 54 + 121
# v3 = v2 unchanged plus the mid-century scanned sources (eval = test + dev of midcentury_unit_split_v0):
# 8,211 scanned Reshumot booklets and 5,338 plenary sittings, every enumerated unit listed.
# v4 = v3 with reshumot_scanned from midcentury_unit_split_v1: 40 dev replacement queue units move non_eval -> eval
# (5 dev units retired, still eval): 160 = 120 + 40.
# v5 = v4 with the replacement walk applied (midcentury_unit_split_v2): 5 filled queue units become dev, the other 35
# return to non_eval: 125 = 160 - 35.
# v6 = v5 unchanged plus knesset_plenary_k13_25 (E2f7, R9): 3,411 K13-25 sittings; a 2% per-Knesset hold-out (min 3)
# is eval (78), the rest non_eval (3,333). Two enumerated rows have no sitting number and stay unassigned.
CURRENT_COUNTS = {RESHUMOT: (30, 175), KNESSET: (7, 13), "reshumot_scanned": (125, 8086), "knesset_plenary_k1_12": (60, 5278),
                  "knesset_plenary_k13_25": (78, 3333)}
EXPOSED = ("reshumot:kovetz_hatakanot_6609", "reshumot:sefer_hachukim_2110")


@pytest.fixture(scope="module")
def registry() -> EvalReservedUnitsRegistry:
    return load_and_validate_bundle().eval_reserved_units


def _split_copy() -> Path:
    (copy,) = tool.packaged_split_copies()
    return copy


# --- the registry ------------------------------------------------------------------------------------------------


def test_committed_registry_is_generated_from_the_committed_split_file(registry: EvalReservedUnitsRegistry) -> None:
    assert tool.check() == []
    copy = _split_copy()
    assert copy.name == registry.split_file.name == CURRENT
    assert registry.split_file.packaged_copy == f"data/eval/{copy.name}"
    assert hashlib.sha256(copy.read_bytes()).hexdigest() == registry.split_file.sha256 == CURRENT_SHA256
    # From v2 the schema field names the file format (v1) and split_version names the assignment.
    assert registry.split_file.split_version == "v6"
    assert registry.split_file.schema_version == "heocr_eval_unit_split.v1"
    # v6 states what it supersedes: v5 (v4, v3, v2, v1 before it), by pinned sha256
    data = json.loads(copy.read_text(encoding="utf-8"))
    assert data["supersedes"]["sha256"] == V5_SHA256
    modern = data["modern_knesset_coverage"]["knesset_plenary_k13_25"]
    assert {u["role"] for u in data["knesset_plenary_k13_25"]["eval"]} == {"holdout_modern_plenary"}
    assert sum(k["holdout"] for k in modern["per_knesset"].values()) == 78 and len(modern["unassigned_rows"]) == 2
    roles = {u["role"] for u in data["reshumot_scanned"]["eval"]}
    assert roles == {"test", "dev", "dev_retired"}
    assert data["midcentury_coverage"]["reshumot_scanned"]["enumerated"] == 8211
    assert data["midcentury_coverage"]["knesset_plenary_k1_12"]["enumerated"] == 5338
    assert registry.decision == "heocr-engine planning/decisions/0017"
    assert registry.owner.startswith("eval[")
    assert registry.unassigned_rule.startswith("Units in neither list are unassigned")
    counts = {source.source_id: (len(source.eval_units), len(source.non_eval_units)) for source in registry.sources}
    assert counts == CURRENT_COUNTS
    data = json.loads(copy.read_text(encoding="utf-8"))
    for source in registry.sources:
        for category, units in (("eval", source.eval_units), ("non_eval", source.non_eval_units)):
            assert units == sorted(unit["unit_id"] for unit in data[source.source_id][category])


def test_each_category_comes_straight_from_the_file(registry: EvalReservedUnitsRegistry) -> None:
    # v1 marks two booklets `status: exposed` and lists them as non_eval: they are open, not reserved.
    for unit in EXPOSED:
        assert registry.status(RESHUMOT, unit) is EvalUnitStatus.non_eval
    assert registry.status(RESHUMOT, "reshumot:sefer_hachukim_2580") is EvalUnitStatus.eval
    assert registry.status(RESHUMOT, "reshumot:sefer_hachukim_9999") is EvalUnitStatus.unassigned
    assert registry.status(RESHUMOT, None) is EvalUnitStatus.unassigned
    assert registry.status("wikisource_he_proofread", "anything") is None


def test_sync_writes_the_copy_and_the_registry(tmp_path: Path) -> None:
    split = tmp_path / CURRENT
    split.write_bytes(_split_copy().read_bytes())
    package, config = tmp_path / "pkg", tmp_path / "config"
    config.mkdir()
    (package / "data" / "eval").mkdir(parents=True)
    (package / "data" / "eval" / "pmod_unit_split_v0.json").write_text("{}", encoding="utf-8")  # an older copy goes
    summary = tool.sync(split, package=package, config_root=config)
    assert summary["units"] == {source: {"eval": e, "non_eval": n} for source, (e, n) in CURRENT_COUNTS.items()}
    assert [path.name for path in tool.packaged_split_copies(package)] == [CURRENT]
    assert tool.check(package=package, config_root=config) == []
    registry_file = config / "eval_reserved_units.yaml"
    registry_file.write_text(registry_file.read_text(encoding="utf-8").replace("knesset_protocol:398637\n", "", 1), encoding="utf-8")
    assert tool.check(package=package, config_root=config) != []


def _split_json(**overrides) -> bytes:
    data = json.loads(_split_copy().read_text(encoding="utf-8"))
    data.update(overrides)
    return json.dumps({key: value for key, value in data.items() if value is not None}).encode("utf-8")


@pytest.mark.parametrize(
    ("name", "payload", "message"),
    [
        ("pmod_unit_split_v6.json", _split_json(superseded_by="labels/pmod_unit_split_v7.json"), "superseded"),
        ("units.json", _split_json(), "is not pmod_unit_split"),
        ("pmod_unit_split_v7.json", _split_json(), "states split_version"),
        ("pmod_unit_split_v6.json", _split_json(usage="eval units are never training input."), "unassigned"),
        ("pmod_unit_split_v6.json", _split_json(tenders={"eval": [], "non_eval": []}), "does not map"),
        ("pmod_unit_split_v6.json", _split_json(owner=None), "no owner"),
        ("pmod_unit_split_v6.json",
         _split_json(knesset_committee_protocols_pre1976={"eval": [{"unit_id": "knesset_protocol:1"}] * 2, "non_eval": []}),
         "repeated unit_id"),
    ],
)
def test_sync_refuses_a_split_file_it_cannot_govern(name: str, payload: bytes, message: str) -> None:
    with pytest.raises(tool.SplitFileError, match=message):
        tool.registry_data(payload, name)


def test_registry_model_rejects_overlapping_or_misprefixed_units(registry: EvalReservedUnitsRegistry) -> None:
    data = registry.model_dump(mode="json")
    knesset = next(source for source in data["sources"] if source["source_id"] == KNESSET)
    knesset["non_eval_units"] = sorted(knesset["non_eval_units"] + [knesset["eval_units"][0]])
    with pytest.raises(ValidationError, match="both eval and non_eval"):
        EvalReservedUnitsRegistry.model_validate(data)
    knesset["non_eval_units"] = sorted(knesset["non_eval_units"][:-1] + ["reshumot:sefer_hachukim_1"])
    with pytest.raises(ValidationError, match="must start with"):
        EvalReservedUnitsRegistry.model_validate(data)


# --- unit ids ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("reshumot:kovetz_hatakanot_10333", (RESHUMOT, "reshumot:kovetz_hatakanot_10333")),
        ("reshumot:kovetz_hatakanot:10333", (RESHUMOT, "reshumot:kovetz_hatakanot_10333")),
        ("kovetz_hatakanot_10333__p0001", (RESHUMOT, "reshumot:kovetz_hatakanot_10333")),
        ("reshumot_kovetz_hatakanot_10333__p0001", (RESHUMOT, "reshumot:kovetz_hatakanot_10333")),  # the R4f form
        ("reshumot_born_digital:sefer_hachukim_2580__p0008", (RESHUMOT, "reshumot:sefer_hachukim_2580")),
        ("knesset_protocol:398637", (KNESSET, "knesset_protocol:398637")),
        ("knesset_committee:398637", (KNESSET, "knesset_protocol:398637")),
        ("knesset_committee_398637__p0001", (KNESSET, "knesset_protocol:398637")),
        ("knesset_committee_protocols_pre1976:knesset_committee_398637__p0001", (KNESSET, "knesset_protocol:398637")),
        ("ws_index_1711486__p0012", None),
        ("nli-990018546440205171", None),
        ("reshumot:other_series_1", None),
        (12345, None),
    ],
)
def test_unit_ids_from_every_id_shape(identifier, expected) -> None:
    assert unit_from_identifier(identifier) == expected


def test_every_tranche_v5_reshumot_and_knesset_item_maps_to_a_listed_unit(registry: EvalReservedUnitsRegistry) -> None:
    rows = [json.loads(line) for line in (package_root() / "data" / "real_tranche" / "tranche_items.jsonl").read_text(encoding="utf-8").splitlines()]
    governed = [row for row in rows if row["source_id"] in (RESHUMOT, KNESSET)]
    assert len(governed) == 1003
    statuses: Counter = Counter()
    units: dict[str, set[str]] = {}
    for row in governed:
        item = {"source_id": row["source_id"], "item_id": f"{row['source_id']}:{row['source_item_id']}",
                "source_item_id": row["source_item_id"], "source_group_id": row["source_group"]}
        unit, status = unit_status(item, registry)
        bare = unit_status({"source_id": row["source_id"], "source_item_id": row["source_item_id"]}, registry)
        assert bare[0].unit_id == unit.unit_id  # the page id alone is enough
        statuses[(row["source_id"], status.value)] += 1
        units.setdefault(status.value, set()).add(unit.unit_id)
    # Every captured unit is assigned; the tranche holds every eval unit of the split file.
    assert statuses == {(RESHUMOT, "eval"): 241, (RESHUMOT, "non_eval"): 557, (KNESSET, "eval"): 40, (KNESSET, "non_eval"): 165}
    # the tranche holds born-digital and committee items only; the scanned sources (v3) are not in it
    assert units["eval"] == {unit for source in registry.sources if source.source_id in (RESHUMOT, KNESSET) for unit in source.eval_units}


def test_fetcher_metadata_gives_the_unit_and_ambiguous_rows_are_refused() -> None:
    reshumot = {"source_id": RESHUMOT, "item_id": "x", "metadata": {"reshumot_series": "sefer_hachukim", "reshumot_booklet_number": "2580"}}
    assert governed_unit(reshumot).unit_id == "reshumot:sefer_hachukim_2580"
    knesset = {"source_id": KNESSET, "item_id": "y", "metadata": {"knesset_document_id": 398637}}
    assert governed_unit(knesset).unit_id == "knesset_protocol:398637"
    # A governed source without a derivable unit is unassigned, never open.
    assert governed_unit({"source_id": KNESSET, "item_id": "z"}).unit_id is None
    assert governed_unit({"source_id": "wikisource_he_proofread", "item_id": "wikisource_he_proofread:ws_1__p1"}) is None
    with pytest.raises(EvalReservedUnitError, match="more than one"):
        governed_unit({**reshumot, "source_item_id": "sefer_hachukim_2581__p0001"})


# --- the release split -------------------------------------------------------------------------------------------


def _curated(item_id: str, source_id: str, *, group: str | None = None, cluster: str | None = None,
             content_type: str = "printed_modern") -> CuratedItemRecord:
    return CuratedItemRecord.model_construct(
        item_id=item_id, source_id=source_id, source_item_id=item_id.split(":", 1)[1], source_url="",
        metadata={"content_type": content_type}, raw_metadata={}, dedupe_cluster_id=cluster,
        near_duplicate_cluster_id=None, source_group_id=group, split=None, split_group_id=None, is_synthetic=False,
    )


def _release_pool() -> list[CuratedItemRecord]:
    """The committed tranche's Reshumot and Knesset items, plus unassigned units and Wikisource filler."""

    rows = [json.loads(line) for line in (package_root() / "data" / "real_tranche" / "tranche_items.jsonl").read_text(encoding="utf-8").splitlines()]
    items = []
    for n, row in enumerate(row for row in rows if row["source_id"] in (RESHUMOT, KNESSET)):
        # Every seventh page has no source group (as the dedupe stage leaves a one-page group): its id must suffice.
        items.append(_curated(f"{row['source_id']}:{row['source_item_id']}", row["source_id"],
                              group=None if n % 7 == 0 else row["source_group"]))
    items += [_curated(f"{RESHUMOT}:sefer_hachukim_9999__p{page:04d}", RESHUMOT, group="reshumot:sefer_hachukim:9999") for page in range(1, 4)]
    items.append(_curated(f"{KNESSET}:mystery-page", KNESSET))  # no derivable unit: unassigned
    items += [_curated(f"wikisource_he_proofread:ws_{n}__p1", "wikisource_he_proofread", group=f"ws:{n}", content_type="printed_historical")
              for n in range(40)]
    # A Wikisource page that duplicates an eval Reshumot page rides along with it.
    items.append(_curated("wikisource_he_proofread:ws_dup__p1", "wikisource_he_proofread", cluster="dup-1", content_type="printed_historical"))
    items.append(_curated(f"{RESHUMOT}:sefer_hachukim_2580__p0001", RESHUMOT, group="reshumot:sefer_hachukim:2580", cluster="dup-1"))
    return items


@pytest.mark.parametrize("seed", ["hocrgen-split-v1", "seed-a", "seed-b", "seed-c"])
def test_the_published_train_split_never_holds_an_eval_or_unassigned_unit(registry: EvalReservedUnitsRegistry, seed: str) -> None:
    items = _release_pool()
    outputs = assign_splits(items, [], POLICY, seed=seed, eval_reserved_units=registry)
    statuses = eval_reserved_statuses(items, registry)
    splits = {item.item_id: item.split for item in outputs.retained_items}
    constraints = {assignment.item_id: assignment.split_constraint for assignment in outputs.assignments}
    for item_id, (_, _, status) in statuses.items():
        if status in ("eval", "unassigned"):
            assert splits[item_id] == EVAL_RESERVED_SPLIT, item_id
            assert constraints[item_id] == "eval_reserved_unit"
        else:
            assert splits[item_id] != EVAL_RESERVED_SPLIT, item_id
    assert splits["wikisource_he_proofread:ws_dup__p1"] == EVAL_RESERVED_SPLIT
    train = [item for item in outputs.retained_items if item.split == "train"]
    assert train and all(statuses.get(item.item_id, (None, None, "open"))[2] in ("non_eval", "open") for item in train)
    # The non-reserved items are still balanced over the policy.
    strata = outputs.leakage_report["split_assignment"]["strata"]
    reshumot = strata[f"{RESHUMOT}:printed_modern"]
    assert sum(reshumot["items"].values()) == 557 and abs(reshumot["items"]["test"] - 55.7) <= 1
    report = outputs.leakage_report["eval_reserved_units"]
    assert report["split_file"]["sha256"] == CURRENT_SHA256 and report["leak_item_ids"] == []
    assert report["carried_item_ids"] == ["wikisource_he_proofread:ws_dup__p1"]
    assert report["sources"][RESHUMOT]["items"] == {"eval": 242, "non_eval": 557, "unassigned": 3}
    assert report["sources"][RESHUMOT]["reserved_units"]["unassigned"] == ["reshumot:sefer_hachukim_9999"]
    assert report["sources"][KNESSET]["reserved_units"]["unassigned"] == ["<unit not derivable>"]
    assert outputs.leakage_report["split_assignment"]["eval_reserved"]["items"] == 242 + 40 + 3 + 1 + 1
    assert outputs.leakage_report["status"] == "ok"


def test_without_reserved_units_the_split_is_unchanged(registry: EvalReservedUnitsRegistry) -> None:
    items = [_curated(f"wikisource_he_proofread:ws_{n}__p{p}", "wikisource_he_proofread", group=f"ws:{n}") for n in range(30) for p in range(n % 3 + 1)]
    outputs = assign_splits(items, [], POLICY, eval_reserved_units=registry)
    assert "eval_reserved" not in outputs.leakage_report["split_assignment"]
    assert {item.split for item in outputs.retained_items} <= {"train", "validation", "test"}
    assert outputs.leakage_report["eval_reserved_units"]["sources"] == {}


def test_a_reserved_component_pinned_elsewhere_is_refused(registry: EvalReservedUnitsRegistry) -> None:
    items = [_curated(f"{RESHUMOT}:sefer_hachukim_2580__p0001", RESHUMOT, group="reshumot:sefer_hachukim:2580")]
    with pytest.raises(ValueError, match="pinned to both"):
        assign_splits(items, [], POLICY, pinned_splits={items[0].item_id: "test"}, eval_reserved_units=registry)
    items[0].metadata["scan_commons_file_sha1"] = "abc"
    with pytest.raises(ValueError, match="synthetic-training work"):
        assign_splits(items, [], POLICY, synthetic_training_keys={"commons_file:abc": ["glyphs:x"]}, eval_reserved_units=registry)


def test_leakage_validation_fails_a_reserved_item_outside_the_holdout(registry: EvalReservedUnitsRegistry) -> None:
    item = _curated(f"{KNESSET}:knesset_committee_398637__p0001", KNESSET).model_copy(update={"split": "train", "split_group_id": "g"})
    report = _validate_leakage([item], None, (eval_reserved_statuses([item], registry), registry))
    assert report["status"] == "error"
    assert report["eval_reserved_units"]["leak_item_ids"] == [item.item_id]


def test_balance_takes_reserved_groups_out_of_their_stratum() -> None:
    groups = [SplitGroup(group_id=f"g{n:02d}", size=1 + n % 4, stratum="s") for n in range(40)]
    reserved = [SplitGroup(group_id=f"r{n}", size=9, stratum="s", pinned_split=EVAL_RESERVED_SPLIT) for n in range(3)]
    alone = assign_group_splits(groups, POLICY)
    together = assign_group_splits([*groups, *reserved], POLICY)
    assert {key: together[key] for key in alone} == alone
    assert {together[group.group_id] for group in reserved} == {EVAL_RESERVED_SPLIT}
    report = split_balance_report([*groups, *reserved], together, POLICY)
    assert report["eval_reserved"]["items"] == 27 and report["eval_reserved"]["strata"] == {"s": {"items": 27, "groups": 3}}
    assert report["strata"]["s"]["item_count"] == sum(group.size for group in groups)
    with pytest.raises(ValueError, match="unknown split"):
        assign_group_splits([SplitGroup(group_id="x", size=1, stratum="s", pinned_split="reserved")], POLICY)


def test_the_export_refuses_a_reserved_item_outside_eval_reserved(tmp_path: Path) -> None:
    item = _curated(f"{RESHUMOT}:sefer_hachukim_2580__p0002", RESHUMOT).model_copy(update={"split": "train"})
    with pytest.raises(StageExecutionError, match="evaluation-reserved"):
        copy_export_assets([item], tmp_path / "data")
    assert not (tmp_path / "data").exists()


# --- the training-input builders -----------------------------------------------------------------------------------


def test_the_guard_refuses_eval_and_unassigned_units_and_names_them(registry: EvalReservedUnitsRegistry) -> None:
    open_rows = [{"record_id": "990018546440205171"}, {"source_id": RESHUMOT, "item_id": f"{RESHUMOT}:kovetz_hatakanot_10333__p0001"},
                 {"source_item_id": "kovetz_hatakanot_6609__p0003"}]  # an exposed booklet: non_eval, open
    assert refuse_eval_reserved_training_input(open_rows, builder="test", registry=registry) == 3
    with pytest.raises(EvalReservedUnitError) as excinfo:
        refuse_eval_reserved_training_input(
            [{"id": "a", "source_item_id": "sefer_hachukim_2580__p0001"}, {"id": "b", "page_id": "knesset_committee_999999__p0001"},
             {"id": "c", "source_id": KNESSET}],
            builder="test builder", registry=registry)
    message = str(excinfo.value)
    assert message.startswith("test builder: refused 3 input row(s)") and "decision 0017" in message
    assert CURRENT in message
    assert "reshumot:sefer_hachukim_2580 is eval" in message and "knesset_protocol:999999 is unassigned" in message


def test_benyehuda_nli_lines_refuses_a_reserved_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    row = {"record_id": "reshumot_sefer_hachukim_2580__p0001", "canvas_index": 0, "text": "שלום", "_root": tmp_path}
    # collect returns (best, drops, density, placer_choice, skipped_dirs, span_drops) since hocrgen#181
    monkeypatch.setattr(bl, "collect", lambda *args, **kwargs: (
        {("reshumot_sefer_hachukim_2580__p0001", 0, 0): row}, Counter(), {}, {}, [], Counter()))
    with pytest.raises(EvalReservedUnitError, match="benyehuda_nli_lines build: refused 1"):
        bl.main(["build", str(tmp_path / "set"), "--root", str(tmp_path)])
    assert not (tmp_path / "set").exists()


def test_wikisource_lines_refuses_a_reserved_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = {"index_key": "x", "source_item_id": "knesset_committee_398637__p0001"}
    monkeypatch.setattr(wl, "load_snapshot", lambda root: ({}, [page]))
    args = argparse.Namespace(out=str(tmp_path / "set"), snapshot=str(tmp_path))
    with pytest.raises(EvalReservedUnitError, match="wikisource_lines build: refused 1"):
        wl.build(args)
    assert not (tmp_path / "set").exists()


def test_glyph_harvest_refuses_a_reserved_unit_and_style(tmp_path: Path) -> None:
    unit = gh.Unit(style_id="r", page_id=f"{RESHUMOT}:sefer_hachukim_2580__p0002", image_path=tmp_path / "x.png",
                   reference_text="", ocr_words=[])
    with pytest.raises(EvalReservedUnitError, match="glyph_harvest: refused 1"):
        gh.harvest([unit])
    style = gh.StyleSource(style_id="r", source_id=RESHUMOT, work_id="reshumot:sefer_hachukim:2580", licence="PD")
    with pytest.raises(EvalReservedUnitError, match="glyph_harvest write_bank: refused 1"):
        gh.write_bank(tmp_path / "bank", bank_id="b", config={}, sources=[], exclusions=[], styles=[style],
                      glyphs_by_style={}, stats_by_style={})
    assert not (tmp_path / "bank").exists()


# --- scanned Reshumot and Knesset plenary (decisions 0017/0018) ----------------------------------------------------

SCANNED, PLENARY = "reshumot_scanned", "knesset_plenary_k1_12"


def _with_sources(registry: EvalReservedUnitsRegistry, **extra: dict) -> EvalReservedUnitsRegistry:
    """The packaged registry with these sources replaced by fixture lists: {source_id: {"eval": [...], "non_eval": [...]}}.
    (From v3 the packaged registry already governs them; the fixtures pin small, known lists.)"""
    data = registry.model_dump(mode="json")
    data["sources"] = [source for source in data["sources"] if source["source_id"] not in extra]
    for source_id, lists in extra.items():
        data["sources"].append({"source_id": source_id, "unit": tool.UNIT_NAMES[source_id],
                                "eval_units": sorted(lists.get("eval", [])),
                                "non_eval_units": sorted(lists.get("non_eval", []))})
    return EvalReservedUnitsRegistry.model_validate(data)


@pytest.fixture(scope="module")
def extended(registry: EvalReservedUnitsRegistry) -> EvalReservedUnitsRegistry:
    return _with_sources(
        registry,
        reshumot_scanned={"eval": ["reshumot_scanned:sefer_hachukim_501"],
                          "non_eval": ["reshumot_scanned:sefer_hachukim_500"]},
        knesset_plenary_k1_12={"eval": ["plenary:K1_2"], "non_eval": ["plenary:K1_1"]},
    )


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("reshumot_scanned:sefer_hachukim_500", (SCANNED, "reshumot_scanned:sefer_hachukim_500")),
        ("reshumot_scanned:kovetz_hatakanot:0042", (SCANNED, "reshumot_scanned:kovetz_hatakanot_42")),
        ("reshumot_scanned_sefer_hachukim_500__p0003", (SCANNED, "reshumot_scanned:sefer_hachukim_500")),
        ("reshumot_scanned:reshumot_scanned_sefer_hachukim_500__p0003", (SCANNED, "reshumot_scanned:sefer_hachukim_500")),
        ("plenary:K1_1", (PLENARY, "plenary:K1_1")),
        ("plenary_K12_340__p0001", (PLENARY, "plenary:K12_340")),
        ("knesset_plenary_k1_12:plenary_K1_01__p0002", (PLENARY, "plenary:K1_1")),
        # The born-digital and committee shapes are unchanged and never collide with the new ones.
        ("reshumot:sefer_hachukim_500", (RESHUMOT, "reshumot:sefer_hachukim_500")),
        ("reshumot_sefer_hachukim_500__p0001", (RESHUMOT, "reshumot:sefer_hachukim_500")),
        ("knesset_committee_398637__p0001", (KNESSET, "knesset_protocol:398637")),
        ("plenary:K1", None),  # a look-alike: not a unit id (the guard still governs it, below)
    ],
)
def test_scanned_and_plenary_unit_ids(identifier, expected) -> None:
    assert unit_from_identifier(identifier) == expected


def test_registry_accepts_the_new_sources_and_refuses_a_booklet_in_both_reshumot_sources(
        registry: EvalReservedUnitsRegistry, extended: EvalReservedUnitsRegistry) -> None:
    assert extended.status(SCANNED, "reshumot_scanned:sefer_hachukim_500") is EvalUnitStatus.non_eval
    born_digital = next(source for source in registry.sources if source.source_id == RESHUMOT)
    shared = born_digital.non_eval_units[0].removeprefix("reshumot:")
    for category in ("eval", "non_eval"):
        with pytest.raises(ValidationError, match=f"booklet {shared} is listed in both"):
            _with_sources(registry, reshumot_scanned={category: [f"reshumot_scanned:{shared}"]})
    with pytest.raises(ValidationError, match="must start with 'reshumot_scanned:'"):
        _with_sources(registry, reshumot_scanned={"non_eval": ["reshumot:sefer_hachukim_500"]})
    with pytest.raises(ValidationError, match="must start with 'plenary:'"):
        _with_sources(registry, knesset_plenary_k1_12={"eval": ["knesset_protocol:1"]})


def test_scanned_booklets_pass_when_non_eval_and_are_refused_when_eval_or_unassigned(
        extended: EvalReservedUnitsRegistry) -> None:
    open_rows = [{"source_id": SCANNED, "page_id": "reshumot_scanned_sefer_hachukim_500__p0001"},
                 {"item_id": "reshumot_scanned:reshumot_scanned_sefer_hachukim_500__p0002"}]
    assert refuse_eval_reserved_training_input(open_rows, builder="test", registry=extended) == 2
    for row in ({"page_id": "reshumot_scanned_sefer_hachukim_501__p0001"},  # eval
                {"page_id": "reshumot_scanned_sefer_hachukim_502__p0001"},  # in neither list
                {"source_id": SCANNED, "page_id": "page-7"},  # no unit derivable
                {"page_id": "reshumot_scanned_other_series_5__p0001"}):  # a look-alike
        with pytest.raises(EvalReservedUnitError):
            refuse_eval_reserved_training_input([row], builder="test", registry=extended)
    # Metadata gives a scanned row its own unit, never a born-digital one.
    unit = governed_unit({"source_id": SCANNED, "metadata": {"reshumot_series": "sefer_hachukim",
                                                             "reshumot_booklet_number": "500"}})
    assert (unit.source_id, unit.unit_id) == (SCANNED, "reshumot_scanned:sefer_hachukim_500")
    # A row that names a scanned and a born-digital booklet is ambiguous and refused.
    with pytest.raises(EvalReservedUnitError, match="more than one governed"):
        governed_unit({"page_id": "reshumot_scanned_sefer_hachukim_500__p0001",
                       "unit_id": "reshumot:sefer_hachukim_500"})


def test_plenary_sittings_follow_eval_non_eval_and_unassigned(extended: EvalReservedUnitsRegistry) -> None:
    assert unit_status({"page_id": "plenary_K1_1__p0001"}, extended)[1] is EvalUnitStatus.non_eval
    assert unit_status({"unit_id": "plenary:K1_2"}, extended)[1] is EvalUnitStatus.eval
    assert unit_status({"page_id": "plenary_K1_3__p0001"}, extended)[1] is EvalUnitStatus.unassigned
    assert refuse_eval_reserved_training_input([{"page_id": "plenary_K1_1__p0004"}], builder="t", registry=extended) == 1
    for row in ({"page_id": "plenary_K1_2__p0001"}, {"page_id": "plenary_K1_3__p0001"},
                {"source_id": PLENARY, "page_id": "page-1"}, {"page_id": "plenary:K1"}, {"page_id": "plenary_k1_1__p0001"}):
        with pytest.raises(EvalReservedUnitError):
            refuse_eval_reserved_training_input([row], builder="test", registry=extended)


def test_the_packaged_v3_registry_governs_scanned_and_plenary_rows(registry: EvalReservedUnitsRegistry) -> None:
    """From v3 the packaged registry lists every enumerated scanned booklet and plenary sitting: a non_eval row passes,
    an eval row (a mid-century test or dev unit) is refused, and a unit in neither list is unassigned and refused."""
    scanned, plenary = registry.source(SCANNED), registry.source(PLENARY)
    assert scanned is not None and plenary is not None
    assert (len(scanned.eval_units), len(scanned.non_eval_units)) == CURRENT_COUNTS[SCANNED]
    assert (len(plenary.eval_units), len(plenary.non_eval_units)) == CURRENT_COUNTS[PLENARY]
    to_page = {SCANNED: lambda u: f"{u.replace(':', '_')}__p0001", PLENARY: lambda u: f"plenary_{u.split(':', 1)[1]}__p0001"}
    for source in (scanned, plenary):
        page = to_page[source.source_id]
        open_row = {"page_id": page(source.non_eval_units[0])}
        assert unit_status(open_row, registry)[1] is EvalUnitStatus.non_eval
        assert refuse_eval_reserved_training_input([open_row], builder="test", registry=registry) == 1
        with pytest.raises(EvalReservedUnitError, match="is eval"):
            refuse_eval_reserved_training_input([{"page_id": page(source.eval_units[0])}], builder="test", registry=registry)
    for row in ({"page_id": "reshumot_scanned_sefer_hachukim_99999__p0001"}, {"page_id": "plenary_K99_1__p0001"}):
        assert unit_status(row, registry)[1] is EvalUnitStatus.unassigned
        with pytest.raises(EvalReservedUnitError, match="unassigned"):
            refuse_eval_reserved_training_input([row], builder="test", registry=registry)


def test_born_digital_and_committee_rows_behave_as_before(registry: EvalReservedUnitsRegistry,
                                                         extended: EvalReservedUnitsRegistry) -> None:
    rows = [{"page_id": f"{unit.removeprefix('reshumot:')}__p0001"}
            for source in registry.sources if source.source_id == RESHUMOT
            for unit in (*source.eval_units[:3], *source.non_eval_units[:3])]
    rows += [{"page_id": f"knesset_committee_{unit.removeprefix('knesset_protocol:')}__p0001"}
             for source in registry.sources if source.source_id == KNESSET
             for unit in (*source.eval_units[:3], *source.non_eval_units[:3])]
    rows += [{"page_id": "sefer_hachukim_999999__p0001"}, {"item_id": "ws_index_1__p0001"}]
    assert [unit_status(row, registry) for row in rows] == [unit_status(row, extended) for row in rows]
    assert tool.registry_data(_split_copy().read_bytes(), _split_copy().name) == registry.model_dump(mode="json")


def test_sync_maps_split_files_listing_the_new_sources() -> None:
    payload = _split_json(reshumot_scanned={"eval": [], "non_eval": [{"unit_id": "reshumot_scanned:sefer_hachukim_500"}]},
                          knesset_plenary_k1_12={"eval": [{"unit_id": "plenary:K1_2"}],
                                                 "non_eval": [{"unit_id": "plenary:K1_1"}]})
    data = tool.registry_data(payload, _split_copy().name)
    sources = {source["source_id"]: source for source in data["sources"]}
    assert sources[SCANNED]["non_eval_units"] == ["reshumot_scanned:sefer_hachukim_500"]
    assert sources[PLENARY]["eval_units"] == ["plenary:K1_2"] and sources[PLENARY]["unit"].startswith("one Knesset plenary")


# --- E2f7: born-digital Knesset plenary K13-25 and committee sessions K16-25 ------------------------------------------

PLENARY_MODERN, COMMITTEE_MODERN = "knesset_plenary_k13_25", "knesset_committee_protocols_k16plus"


@pytest.fixture(scope="module")
def modern(registry: EvalReservedUnitsRegistry) -> EvalReservedUnitsRegistry:
    return _with_sources(
        registry,
        knesset_plenary_k13_25={"eval": ["plenary:K13_2"], "non_eval": ["plenary:K13_1", "plenary:K25_7"]},
        knesset_committee_protocols_k16plus={"non_eval": ["committee:K16_2001", "committee:K25_4123456"]},
    )


@pytest.mark.parametrize(
    ("identifier", "expected"),
    [
        ("plenary:K13_1", (PLENARY_MODERN, "plenary:K13_1")),
        ("plenary_K25_007__p0003", (PLENARY_MODERN, "plenary:K25_7")),
        ("knesset_plenary_k13_25:plenary_K13_1__p0001", (PLENARY_MODERN, "plenary:K13_1")),
        ("plenary:K12_340", (PLENARY, "plenary:K12_340")),
        ("committee:K16_2001", (COMMITTEE_MODERN, "committee:K16_2001")),
        ("committee_K25_4123456__p0002", (COMMITTEE_MODERN, "committee:K25_4123456")),
        ("knesset_committee_protocols_k16plus:committee_K16_2001", (COMMITTEE_MODERN, "committee:K16_2001")),
        # the pre-1976 committee shapes are unchanged and never collide with the new one
        ("knesset_committee:398637", (KNESSET, "knesset_protocol:398637")),
        ("knesset_committee_398637__p0001", (KNESSET, "knesset_protocol:398637")),
        ("committee:398637", None),  # a look-alike: governed by the new source with no unit (below)
    ],
)
def test_modern_knesset_unit_ids(identifier, expected) -> None:
    assert unit_from_identifier(identifier) == expected


def test_modern_knesset_rows_follow_eval_non_eval_and_unassigned(modern: EvalReservedUnitsRegistry) -> None:
    assert unit_status({"page_id": "plenary_K13_1__p0001"}, modern)[1] is EvalUnitStatus.non_eval
    assert unit_status({"unit_id": "plenary:K13_2"}, modern)[1] is EvalUnitStatus.eval
    assert unit_status({"unit_id": "committee:K16_2001", "source_id": COMMITTEE_MODERN}, modern)[1] is EvalUnitStatus.non_eval
    assert refuse_eval_reserved_training_input(
        [{"unit_id": "plenary:K25_7"}, {"item_id": "committee_K25_4123456__p0001"}], builder="t", registry=modern) == 2
    for row in ({"unit_id": "plenary:K13_2"}, {"unit_id": "plenary:K14_9"}, {"unit_id": "committee:K17_1"},
                {"item_id": "committee:398637"}, {"source_id": COMMITTEE_MODERN, "item_id": "page-1"},
                {"source_id": PLENARY_MODERN, "item_id": "page-1"}):
        with pytest.raises(EvalReservedUnitError):
            refuse_eval_reserved_training_input([row], builder="t", registry=modern)
    # a K13+ sitting declared as the K1-12 source names two sources: refused, never let through
    with pytest.raises(EvalReservedUnitError, match="more than one"):
        unit_status({"source_id": PLENARY, "unit_id": "plenary:K13_1"}, modern)


def test_registry_refuses_a_sitting_outside_its_knesset_range(registry: EvalReservedUnitsRegistry) -> None:
    with pytest.raises(ValidationError, match="K<13-25>"):
        _with_sources(registry, knesset_plenary_k13_25={"non_eval": ["plenary:K12_1"]})
    with pytest.raises(ValidationError, match="K<1-12>"):
        _with_sources(registry, knesset_plenary_k1_12={"non_eval": ["plenary:K13_1"]})
    with pytest.raises(ValidationError, match="K<16-25>"):
        _with_sources(registry, knesset_committee_protocols_k16plus={"non_eval": ["committee:K15_1"]})


def test_sync_maps_split_files_listing_the_modern_knesset_sources() -> None:
    payload = _split_json(knesset_plenary_k13_25={"eval": [{"unit_id": "plenary:K13_2"}],
                                                  "non_eval": [{"unit_id": "plenary:K13_1"}]},
                          knesset_committee_protocols_k16plus={"eval": [], "non_eval": [{"unit_id": "committee:K16_1"}]})
    sources = {s["source_id"]: s for s in tool.registry_data(payload, _split_copy().name)["sources"]}
    assert sources[PLENARY_MODERN]["eval_units"] == ["plenary:K13_2"]
    assert sources[COMMITTEE_MODERN]["non_eval_units"] == ["committee:K16_1"]


def test_r9_row_shapes_are_governed_by_unit_id_and_source_id(modern: EvalReservedUnitsRegistry) -> None:
    """R9 rows (data-collection, 2026-11-13): unit_id + source_id; the line id and book match no governed shape."""
    plen = {"id": "K13_1_p00077_l03", "book": "K13_1", "unit_id": "plenary:K13_1", "source_id": PLENARY_MODERN,
            "knesset": 13, "sitting": 1, "document_id": 532132}
    comm = {"id": "K16_2001_p00001_l01", "book": "K16_2001", "unit_id": "committee:K16_2001",
            "source_id": COMMITTEE_MODERN, "knesset": 16, "sitting": 2001, "release_scope": "training_only"}
    assert refuse_eval_reserved_training_input([plen, comm], builder="r9", registry=modern) == 2
    assert unit_from_identifier(plen["id"]) is None and unit_from_identifier(plen["book"]) is None
    with pytest.raises(EvalReservedUnitError, match="is eval"):
        refuse_eval_reserved_training_input([{**plen, "unit_id": "plenary:K13_2"}], builder="r9", registry=modern)
    with pytest.raises(EvalReservedUnitError, match="unassigned"):
        refuse_eval_reserved_training_input([{**comm, "unit_id": "committee:K16_9"}], builder="r9", registry=modern)
