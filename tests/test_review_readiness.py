from __future__ import annotations

import json
import shutil
from pathlib import Path

from hocrgen.cli import main
from hocrgen.config.loader import default_config_root


def test_classify_stage_assigns_expected_source_priors(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    fixture_seed = (Path(__file__).parent / "fixtures" / "nli" / "seeds_default.yaml").resolve()
    sources_path = config_root / "sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace(
            "package://data/nli/seeds.yaml", str(fixture_seed)
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "classify",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path),
            "--config-root",
            str(config_root),
        ]
    )
    assert exit_code == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    classified_items = json.loads((run_dir / "classify" / "classified_items.json").read_text(encoding="utf-8"))["items"]
    by_source = {item["source_id"]: item for item in classified_items}

    assert by_source["nli_any_use_permitted"]["period_class"] == "modern"
    assert by_source["nli_any_use_permitted"]["content_class"] == "handwritten"
    assert by_source["pinkas_open"]["period_class"] == "historical"
    assert by_source["pinkas_open"]["content_class"] == "handwritten"
    assert by_source["biblia_open"]["period_class"] == "historical"
    assert by_source["project_synthetic"]["period_class"] == "modern"
    assert by_source["project_synthetic"]["content_class"] == "printed"


def test_low_confidence_classification_routes_to_review(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    sources_path = config_root / "sources.yaml"
    updated_sources = sources_path.read_text(encoding="utf-8").replace(
        "  - handwritten_historical\n      - printed_historical",
        "  - handwritten_historical\n      - printed_historical\n      - manuscript_scan",
    )
    records_path = config_root / "biblia_low_conf_records.json"
    records_path.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "id": "biblia-low-conf-001",
                        "title": "Administrative fragment",
                        "source_url": "https://example.org/biblia/administrative-fragment",
                        "upstream_identifier": "administrative-fragment",
                        "collection": "BiblIA Open Packaged Subset",
                        "period": "historical",
                        "raw_rights": "PD-IL",
                        "asset_path": "package://data/biblia/assets/biblia_001.jpg",
                    }
                ]
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    updated_sources = updated_sources.replace("package://data/biblia/records.json", str(records_path))
    sources_path.write_text(updated_sources, encoding="utf-8")

    exit_code = main(
        [
            "review-export",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
            "--source",
            "biblia_open",
        ]
    )
    assert exit_code == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    review_required = json.loads((run_dir / "review" / "review_required_items.json").read_text(encoding="utf-8"))["items"]
    queue = json.loads((run_dir / "review" / "queue.json").read_text(encoding="utf-8"))["items"]

    assert len(review_required) == 1
    assert "content_conflicting_source_priors" in review_required[0]["classification_review_reasons"]
    assert queue[0]["suggested_decision"] == "needs_classification_review"


def test_privacy_modes_respect_release_and_review_behavior(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    profile_path = config_root / "profiles" / "profile_open_v1.yaml"

    exit_code = main(
        [
            "privacy-scan",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "conservative"),
            "--config-root",
            str(config_root),
            "--source",
            "nli_any_use_permitted",
        ]
    )
    assert exit_code == 0
    conservative_run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    conservative_items = json.loads((conservative_run_dir / "privacy_scan" / "privacy_scanned_items.json").read_text(encoding="utf-8"))["items"]
    assert conservative_items[0]["privacy_flag"] == "possible_personal_data"
    assert conservative_items[0]["privacy_decision"] == "review_required"

    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace('privacy_mode: conservative', 'privacy_mode: "off"'),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "privacy-scan",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "off"),
            "--config-root",
            str(config_root),
            "--source",
            "nli_any_use_permitted",
        ]
    )
    assert exit_code == 0
    off_run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    off_items = json.loads((off_run_dir / "privacy_scan" / "privacy_scanned_items.json").read_text(encoding="utf-8"))["items"]
    assert off_items[0]["privacy_flag"] == "clear"
    assert off_items[0]["privacy_decision"] == "release_ready"

    profile_path.write_text(
        profile_path.read_text(encoding="utf-8").replace('privacy_mode: "off"', 'privacy_mode: review'),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "privacy-scan",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "review"),
            "--config-root",
            str(config_root),
            "--source",
            "nli_any_use_permitted",
        ]
    )
    assert exit_code == 0
    review_run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    review_items = json.loads((review_run_dir / "privacy_scan" / "privacy_scanned_items.json").read_text(encoding="utf-8"))["items"]
    assert review_items[0]["privacy_flag"] == "possible_personal_data"
    assert review_items[0]["privacy_decision"] == "review_required"


def test_blocked_items_are_excluded_from_split_and_release_outputs(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    privacy_path = config_root / "privacy_rules.yaml"
    privacy_rules = privacy_path.read_text(encoding="utf-8")
    privacy_rules = privacy_rules.replace(
        "rules:\n",
        "rules:\n  - id: block_biblia_fixture\n    flag: blocked_sensitive\n    patterns:\n      - Hebrew Bible\n    fields:\n      - title\n    applies_to_sources:\n      - biblia_open\n",
        1,
    )
    privacy_path.write_text(privacy_rules, encoding="utf-8")

    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "blocked"),
            "--config-root",
            str(config_root),
        ]
    )
    assert exit_code == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    blocked_items = json.loads((run_dir / "build_release" / "blocked_items.json").read_text(encoding="utf-8"))["items"]
    split_manifest = json.loads((run_dir / "build_release" / "split_manifest.json").read_text(encoding="utf-8"))["items"]
    item_manifest = json.loads((run_dir / "build_release" / "item_manifest.json").read_text(encoding="utf-8"))["items"]
    release_summary = json.loads((run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))

    assert len(blocked_items) == 1
    assert blocked_items[0]["source_id"] == "biblia_open"
    assert all(not item["item_id"].startswith("biblia_open:") for item in split_manifest)
    assert all(item["source_id"] != "biblia_open" for item in item_manifest)
    assert release_summary["blocked_count"] == 1


def test_build_release_applies_review_decisions_and_overrides(tmp_path: Path, capsys) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    fixture_seed = (Path(__file__).parent / "fixtures" / "nli" / "seeds_default.yaml").resolve()
    sources_path = config_root / "sources.yaml"
    sources_path.write_text(
        sources_path.read_text(encoding="utf-8").replace(
            "package://data/nli/seeds.yaml", str(fixture_seed)
        ),
        encoding="utf-8",
    )
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    (review_root / "manual_decisions" / "approve_biblia.json").write_text(
        json.dumps(
            {
                "decision": "approve",
                "item_id": "biblia_open:biblia-doc-001",
                "rationale": "Approved for public alpha",
                "review_item_id": "review:biblia_open:biblia-doc-001",
                "reviewer": "qa-1",
                "timestamp": "2026-04-21T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    exit_code = main(
        [
            "build-release",
            "--profile",
            "profile_open_v1",
            "--dry-run",
            "--workdir",
            str(tmp_path / "work"),
            "--config-root",
            str(config_root),
        ]
    )
    assert exit_code == 0
    run_dir = Path(json.loads(capsys.readouterr().out)["run_dir"])
    item_manifest = json.loads((run_dir / "build_release" / "item_manifest.json").read_text(encoding="utf-8"))["items"]
    review_required_items = json.loads((run_dir / "build_release" / "review_required_items.json").read_text(encoding="utf-8"))["items"]
    decision_audit = json.loads((run_dir / "build_release" / "decision_audit.json").read_text(encoding="utf-8"))["items"]
    release_summary = json.loads((run_dir / "build_release" / "release_summary.json").read_text(encoding="utf-8"))

    assert {item["item_id"] for item in item_manifest} == {
        "biblia_open:biblia-doc-001",
        "nli_any_use_permitted:nli-ms-seed-006",
        "pinkas_open:pinkas-ledger-001",
        "project_synthetic:synthetic-0",
    }
    assert review_required_items == []
    assert release_summary["review_approved_count"] == 1
    assert release_summary["review_rejected_count"] == 0
    assert release_summary["review_unresolved_count"] == 0
    assert release_summary["review_required_count"] == 0
    assert any(
        item["item_id"] == "biblia_open:biblia-doc-001"
        and item["decision_source"] == "manual_decision"
        and item["outcome"] == "release_ready"
        for item in decision_audit
    )
