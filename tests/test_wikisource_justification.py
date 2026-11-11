"""Network-free tests for the Route C rights justification of Wikisource's Commons scans
(hocrgen.fetchers.wikisource_justification and hocrgen.tools.wikisource_rights_justification)."""

from __future__ import annotations

import copy
import datetime as dt
import json
from pathlib import Path

import pytest
from PIL import Image

from hocrgen.config.loader import load_and_validate_bundle, package_root
from hocrgen.fetchers import wikisource_justification as wj
from hocrgen.fetchers.base import StageOptions
from hocrgen.fetchers.wikisource import (
    WikisourceProofreadImporter,
    load_wikisource_snapshot,
    watermark_box_on_pair_image,
)
from hocrgen.manifests.models import ItemRecord
from hocrgen.tools import wikisource_rights_justification as tool

ROOT = Path(__file__).resolve().parents[1]
AS_OF = dt.date(2026, 11, 11)
SNAPSHOT_ROOT = package_root() / "data" / "wikisource" / "snapshot"


def _index(**changes) -> dict:
    index = {
        "index_key": "ws_index_1",
        "index_title": "מפתח:Book.pdf",
        "commons_file": {
            "title": "File:Book.pdf",
            "repository": "commons",
            "file_page_revision_id": 7,
            "sha1": "a" * 40,
            "page_count": 10,
            "source_field": "[http://www.hebrewbooks.org/1 HebrewBooks]",
            "institution_field": None,
            "provenance_text": None,
            "licence_templates": ["PD-scan|PD-old-auto-1923|deathyear=1900"],
            "categories": [],
        },
        "work": {
            "title": "ספר",
            "published_year": 1890,
            "published_year_evidence": "Commons date field: 1890",
            "language": "he",
            "creators": [{"name": "Author", "role": "author", "wikidata": "Q1", "death_year": 1900,
                          "death_year_evidence_url": "https://www.wikidata.org/wiki/Q1"}],
        },
        "work_rights": {"basis": "author_died_by_1955", "evidence": "Creators: Author (author, died 1900)."},
        "scan_rights": {"basis": "faithful_reproduction_of_pd_work", "licence": None,
                        "scan_source": {"name": "HebrewBooks", "url": "http://www.hebrewbooks.org/1",
                                        "evidence": "Commons source field: HebrewBooks"},
                        "evidence": "a faithful reproduction (decision 10).", "digitized_by_google": False,
                        "digitization_check": "No Google stamp on the inspected page render."},
        "gate": {"admitted": True, "reasons": []},
    }
    for path, value in changes.items():
        target = index
        *parents, last = path.split(".")
        for part in parents:
            target = target[part]
        target[last] = value
    return index


def _evidence(**changes) -> dict:
    evidence = {"index_key": "ws_index_1", "commons_file": "File:Book.pdf", "commons_file_sha1": "a" * 40,
                "file": {"repository": "commons", "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Book.pdf",
                         "description_url": "https://commons.wikimedia.org/wiki/File:Book.pdf", "sha1": "a" * 40,
                         "mime": "application/pdf"},
                "place": {"place": "Vilna", "source": "Commons city field"}}
    evidence.update(changes)
    return evidence


def _hygiene(*pages: tuple[int, bool, list | None]) -> dict:
    return wj.wikisource_hygiene_record(
        [{"scan_page": page, "render_sha256": "r" * 64, "render_width": 960, "render_height": 1500, "front_matter": front,
          "phrases": ["Usage guidelines"] if front else [], "google_watermark_bbox": box, "watermark_band": 0.1 if box else None}
         for page, front, box in pages],
        render_source="test",
    )


def test_a_hebrewbooks_scan_is_justified_from_evidence() -> None:
    result = wj.build_wikisource_rights_justification(_index(), _evidence(), as_of=AS_OF)
    assert result.accepted and result.failures == []
    record = result.record
    assert record["id"].startswith("rj:ws_index_1:") and len(record["id"].split(":")[-1]) == 12
    assert record["format"] == "hocrgen.rights_justification.v1"
    assert record["route"]["name"] == "wikimedia_commons"
    assert record["route"]["url"][0] == "https://upload.wikimedia.org/wikipedia/commons/a/ab/Book.pdf"
    assert record["route"]["sha1"] == {"file": "a" * 40}
    wpd = record["work_public_domain"]
    assert wpd["contributors"][0]["death_year_source"]["kind"] == "wikidata_p570"
    assert wpd["israel_status"]["basis"] == "author_died_over_70_years_ago"
    assert wpd["us_status"]["status"] == "pd_us"
    assert wpd["place"]["place"] == "Vilna"
    assert record["digitizer"]["name"] == "HebrewBooks"
    assert record["digitizer"]["google"]["status"] == "not_google"
    # Decision 3: HebrewBooks' site terms are recorded as found, and why they do not bind is stated.
    assert record["origin_label"]["holder"] == "HebrewBooks"
    assert "Wikimedia Commons (File:Book.pdf)" in record["why_not_binding"]
    assert record["route_terms"]["licence_templates"] == ["PD-scan|PD-old-auto-1923|deathyear=1900"]
    assert record["hygiene"] == "none"
    assert "decision 3" in record["decision_refs"][-1]
    assert record["summary"].startswith("Public-domain work (author d. 1900, recorded publication year 1890)")
    # The id is a digest of the record: rebuilding gives the same id.
    assert wj.build_wikisource_rights_justification(_index(), _evidence(), as_of=AS_OF).id == result.id


def test_the_1855_presumption_and_us_status_not_established() -> None:
    index = _index(**{"work.published_year": 1850, "work_rights": {"basis": "presumed_pd_by_publication_age", "evidence": "x"}})
    index["work"]["creators"].append({"name": "Unknown editor", "role": "editor", "wikidata": None, "death_year": None,
                                      "death_year_evidence_url": None})
    record = wj.build_wikisource_rights_justification(index, _evidence(), as_of=AS_OF).record
    status = record["work_public_domain"]["israel_status"]
    assert status["basis"] == "presumption_decision_10" and status["presumed_for"] == ["Unknown editor"]
    late = _index(**{"work.published_year": 1940})
    late["work"]["creators"][0]["death_year"] = 1941
    record = wj.build_wikisource_rights_justification(late, _evidence(), as_of=AS_OF).record
    assert record["work_public_domain"]["us_status"]["status"] == "not_established"  # recorded, never a rejection
    assert record["summary"].endswith("US status not established.")


@pytest.mark.parametrize(
    ("index", "evidence", "reason"),
    [
        (_index(**{"work.creators": [{"name": "Late", "role": "editor", "death_year": 1960,
                                      "death_year_evidence_url": "https://www.wikidata.org/wiki/Q2"}]}),
         _evidence(), "justification_index_not_admitted:creator_died_after_1955"),
        (_index(), None, "justification_rights_evidence_missing"),
        (_index(), _evidence(file={"sha1": "a" * 40, "mime": "application/pdf"}), "justification_file_url_missing"),
        (_index(), _evidence(file={**_evidence()["file"], "sha1": "b" * 40}), "justification_file_sha1_mismatch"),
        (_index(), _evidence(file={**_evidence()["file"], "mime": "text/html"}), "justification_not_a_scan_file:text/html"),
        (_index(**{"commons_file.licence_templates": ["Cc-by-nc-sa-4.0"]}), _evidence(),
         "justification_route_terms_restrictive:Cc-by-nc-sa-4.0"),
    ],
)
def test_the_gate_rejects_what_it_cannot_fill(index: dict, evidence: dict | None, reason: str) -> None:
    result = wj.build_wikisource_rights_justification(index, evidence, as_of=AS_OF)
    assert not result.accepted and result.record is None and result.reason == reason


def test_a_google_file_names_google_and_needs_hygiene() -> None:
    index = _index(**{"scan_rights.digitized_by_google": True, "scan_rights.digitization_check": "Commons source names Google Books",
                      "scan_rights.scan_source": {"name": "Google Books", "url": None, "evidence": "Commons source field"},
                      "commons_file.source_field": "https://books.google.com/?id=x"})
    pending = wj.build_wikisource_rights_justification(index, _evidence(), as_of=AS_OF).record
    assert pending["digitizer"]["name"] == "Google" and pending["hygiene"] == "pending"
    assert pending["origin_label"]["label"] == "google_books_usage_guidelines"
    item = {"rights_justification": pending}
    assert wj.wikisource_derivation_blocker(item) == "google_hygiene_pending"
    hygiene = _hygiene((1, True, None), (5, False, [0.6, 0.95, 0.2, 0.03]), (6, False, None))
    record = wj.build_wikisource_rights_justification(index, _evidence(google_hygiene=hygiene), as_of=AS_OF).record
    assert record["hygiene"]["excluded_front_matter"][0]["scan_page"] == 1
    assert record["hygiene"]["watermark_boxes"] == [{"scan_page": 5, "google_watermark_bbox": [0.6, 0.95, 0.2, 0.03]}]
    assert record["hygiene"]["pages_without_watermark"] == [6]
    item = {"rights_justification": record}
    assert wj.wikisource_derivation_blocker(item) is None  # scan level
    assert wj.wikisource_derivation_blocker({**item, "scan_page": 1}) == "excluded_google_front_matter"
    assert wj.wikisource_derivation_blocker({**item, "scan_page": 5}) is None
    assert wj.wikisource_derivation_blocker({**item, "scan_page": 7}) == "google_hygiene_pending"  # never checked


def test_an_undecided_file_is_google_when_the_pass_finds_a_mark_and_not_detected_otherwise() -> None:
    index = _index(**{"scan_rights.digitized_by_google": None, "scan_rights.digitization_check": "Not decided"})
    assert wj.build_wikisource_rights_justification(index, _evidence(), as_of=AS_OF).record["hygiene"] == "pending"
    found = wj.build_wikisource_rights_justification(
        index, _evidence(google_hygiene=_hygiene((3, False, [0.6, 0.95, 0.2, 0.03]))), as_of=AS_OF).record
    assert found["digitizer"]["name"] == "Google" and "watermark on scan pages [3]" in found["digitizer"]["evidence"][0]
    clean = wj.build_wikisource_rights_justification(index, _evidence(google_hygiene=_hygiene((3, False, None))), as_of=AS_OF).record
    assert clean["digitizer"]["google"]["status"] == "not_detected" and clean["digitizer"]["name"] == "HebrewBooks"
    assert wj.wikisource_derivation_blocker({"rights_justification": clean, "scan_page": 3}) is None
    assert wj.wikisource_derivation_blocker({"rights_justification": clean, "scan_page": 4}) == "google_hygiene_pending"


def test_ia_google_identifiers_and_nli_origin() -> None:
    index = _index(**{"scan_rights.digitized_by_google": None, "commons_file.source_field": "{{IA|foo00goog}}",
                      "scan_rights.scan_source": {"name": "Internet Archive", "evidence": "Commons source field"}})
    record = wj.build_wikisource_rights_justification(index, _evidence(ia_item={"identifier": "foo00goog"}), as_of=AS_OF).record
    assert record["digitizer"]["name"] == "Google"
    nli = _index(**{"commons_file.source_field": "{{Institution:National Library of Israel}}",
                    "scan_rights.scan_source": {"name": "National Library of Israel", "evidence": "Commons source field"}})
    record = wj.build_wikisource_rights_justification(nli, _evidence(), as_of=AS_OF).record
    assert record["digitizer"]["name"] == "National Library of Israel"
    assert record["origin_label"]["holder"] == "National Library of Israel" and record["origin_label"]["checked"] is False
    assert "maintainer ruling on NLI-origin files" in record["decision_refs"][0]


def test_a_local_wikisource_file_is_route_c_with_its_repository_named() -> None:
    index = _index(**{"commons_file.repository": "he.wikisource", "commons_file.licence_templates": []})
    evidence = _evidence(file={**_evidence()["file"], "repository": "he.wikisource",
                               "url": "https://upload.wikimedia.org/wikisource/he/a/ab/Book.pdf"})
    record = wj.build_wikisource_rights_justification(index, evidence, as_of=AS_OF).record
    assert record["route"]["file_repository"] == "he.wikisource" and "local file repository" in record["route"]["note"]
    assert "Hebrew Wikisource's file repository" in record["summary"]
    assert record["route_terms"]["licence_templates"] == []  # decision 10: a missing template is recorded, not fatal


def test_the_blocker_fails_closed_without_a_registered_id(tmp_path: Path) -> None:
    record = wj.build_wikisource_rights_justification(_index(), _evidence(), as_of=AS_OF).record
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"items": [{"index_key": "ws_index_1", "accepted": True, "rights_justification": record}]}))
    assert wj.wikisource_derivation_blocker({}, path=registry) == "wikisource_rights_justification_missing"
    assert wj.wikisource_derivation_blocker({"rights_justification_id": "rj:ws_index_1:000000000000"}, path=registry) \
        == "wikisource_rights_justification_missing"
    assert wj.wikisource_derivation_blocker({"rights_justification_id": record["id"]}, path=registry) is None
    assert wj.wikisource_derivation_blocker({"rights_justification_id": record["id"], "commons_file_sha1": "b" * 40},
                                            path=registry) == "wikisource_rights_justification_missing"
    # The lookups the line builder calls to fill its rights_justification_id hook.
    assert wj.wikisource_rights_justification_id(index_key="ws_index_1", path=registry) == record["id"]
    assert wj.wikisource_rights_justification_id(commons_file="Book.pdf", sha1="a" * 40, path=registry) == record["id"]
    assert wj.wikisource_rights_justification_id(commons_file="File:Book.pdf", sha1="b" * 40, path=registry) is None


def test_watermark_masking_and_the_box_on_a_crop() -> None:
    image = Image.new("RGB", (100, 200), (240, 240, 230))
    for x in range(60, 80):
        for y in range(190, 196):
            image.putpixel((x, y), (10, 10, 10))
    masked = wj.mask_google_watermark(image, [0.6, 0.95, 0.2, 0.03])
    assert all(masked.getpixel((x, y)) == (240, 240, 230) for x in range(60, 80) for y in range(190, 196))
    assert masked.getpixel((10, 10)) == (240, 240, 230)
    assert watermark_box_on_pair_image({"google_watermark_bbox": [0.6, 0.95, 0.2, 0.03], "crop": None}) == [0.6, 0.95, 0.2, 0.03]
    on_crop = watermark_box_on_pair_image(
        {"google_watermark_bbox": [0.6, 0.9, 0.2, 0.05], "crop": {"box_normalized": [0.5, 0.5, 1.0, 1.0]}})
    assert on_crop == pytest.approx([0.2, 0.8, 0.4, 0.1])
    outside = {"google_watermark_bbox": [0.6, 0.95, 0.2, 0.03], "crop": {"box_normalized": [0, 0, 1, 0.5]}}
    assert watermark_box_on_pair_image(outside) is None


def test_the_committed_justifications_replay_from_the_committed_inputs() -> None:
    committed = json.loads((ROOT / "docs" / "wikisource_rights_justifications.json").read_text(encoding="utf-8"))
    inventory = json.loads((ROOT / "docs" / "wikisource_index_inventory.json").read_text(encoding="utf-8"))
    evidence = json.loads((ROOT / "docs" / "wikisource_rights_evidence.json").read_text(encoding="utf-8"))
    rebuilt = tool.backfill(inventory, evidence, as_of=dt.date.fromisoformat(committed["as_of"]), inputs=committed["inputs"])
    assert rebuilt == committed
    # Every admitted Index, and every Index the rights rules (printed commentaries, later reprints) reject.
    rules = set(wj.RIGHTS_RULE_REASONS)
    listed = {i["index_key"] for i in inventory["indexes"] if i["gate"]["admitted"] or set(i["gate"]["reasons"]) & rules}
    assert {item["index_key"] for item in committed["items"]} == listed
    for item in committed["items"]:
        record = item["rights_justification"]
        if item["accepted"]:
            assert set(record) >= {"route", "work_public_domain", "faithful_reproduction", "digitizer", "origin_label",
                                   "why_not_binding", "route_terms", "hygiene", "decision_refs", "summary"}
            # Google is never left unhandled: a file where Google is not ruled out carries a hygiene record.
            if record["digitizer"]["google"]["status"] != "not_google":
                assert isinstance(record["hygiene"], dict), item["index_key"]
        else:
            assert record is None and item["reason"].startswith("justification_")
    # The evidence file holds ids, URLs, hashes and boxes only: no page text, no IA uploader addresses.
    text = json.dumps(evidence, ensure_ascii=False)
    assert "@" not in text.replace("@context", "")


def test_every_packaged_fixture_pair_points_to_its_justification() -> None:
    bundle = load_and_validate_bundle()
    source = next(s for s in bundle.source_registry.sources if s.id == "wikisource_he_proofread")
    importer = WikisourceProofreadImporter()
    candidates = importer.discover_candidates(source, bundle, StageOptions())
    assert candidates
    enriched = importer.fetch_candidate_metadata(source, bundle, candidates, StageOptions())
    for item in enriched:
        identifier = item.metadata["rights_justification_id"]
        assert identifier and identifier.startswith("rj:ws_index_")
        assert wj.wikisource_derivation_blocker(item.metadata) is None


def test_the_importer_drops_pages_whose_index_is_not_justified(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = next(s for s in bundle.source_registry.sources if s.id == "wikisource_he_proofread")
    committed = json.loads(wj.REGISTRY_PATH.read_text(encoding="utf-8"))
    _, indexes, _ = load_wikisource_snapshot(SNAPSHOT_ROOT)
    hyman = indexes["hyman_toldoth_1910_vol1"]["commons_file"]["title"]
    trimmed = copy.deepcopy(committed)
    trimmed["items"] = [item for item in trimmed["items"] if item["commons_file"] != hyman]
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps(trimmed, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(wj, "REGISTRY_PATH", registry)
    candidates = WikisourceProofreadImporter().discover_candidates(source, bundle, StageOptions())
    assert candidates and not any(c.source_item_id.startswith("hyman_toldoth_1910_vol1") for c in candidates)


def test_acquisition_masks_a_recorded_watermark(tmp_path: Path) -> None:
    bundle = load_and_validate_bundle()
    source = next(s for s in bundle.source_registry.sources if s.id == "wikisource_he_proofread")
    importer = WikisourceProofreadImporter()
    enriched = importer.fetch_candidate_metadata(source, bundle, importer.discover_candidates(source, bundle, StageOptions()), StageOptions())
    record = next(i for i in enriched if not i.metadata.get("crop"))
    item = ItemRecord(**record.model_dump(), item_id=record.candidate_id, normalized_license="CC-BY-SA-4.0",
                      rights_classification="sharealike", eligibility="review_required", eligibility_reason="fixture")
    item.metadata["google_watermark_bbox"] = [0.6, 0.93, 0.25, 0.05]
    acquired = importer.acquire_items(source, bundle, [item], tmp_path, StageOptions())[0]
    masked = acquired.metadata["google_watermark_masked"]
    assert masked["source_sha256"] == item.metadata["expected_asset_sha256"]
    assert acquired.acquired_assets[0].sha256 != masked["source_sha256"]
