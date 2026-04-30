from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from hocrgen.classify.heuristics import _content_class
from hocrgen.classify.heuristics import _language_class, _period_class, _quality, _source_allowed_types, classify_items
from hocrgen.config.loader import default_config_root, load_and_validate_bundle
from hocrgen.config.models import RightsClassification
from hocrgen.core.errors import ConfigValidationError, StageExecutionError
from hocrgen.manifests.models import (
    AcquiredAsset,
    CuratedItemRecord,
    NormalizedAssetRecord,
    PrivacyScannedItemRecord,
    ReviewDecisionRecord,
    ReviewOverrideRecord,
)
from hocrgen.privacy.rules import _field_text, apply_privacy_rules
from hocrgen.review.merge import ReviewData, load_review_data, merge_review_decisions, resolve_review_data_root
from hocrgen.review.queue import _split_group_id_pre_review, _suggested_decision, export_review_queue


def _curated_item(
    *,
    item_id: str,
    source_id: str,
    source_item_id: str,
    asset_hashes: list[str],
    title: str = "",
    metadata: dict[str, object] | None = None,
    is_synthetic: bool = False,
):
    acquired_assets = [
        AcquiredAsset(item_id=item_id, path=f"/tmp/{item_id}_{index}.svg", sha256=asset_hash)
        for index, asset_hash in enumerate(asset_hashes, start=1)
    ]
    normalized_assets = [
        NormalizedAssetRecord(
            item_id=item_id,
            source_asset_path=f"/tmp/{item_id}_{index}.svg",
            normalized_asset_path=f"/tmp/normalized/{item_id}_{index}.svg",
            asset_format="svg",
            media_type="image/svg+xml",
            width=100,
            height=50,
            file_size_bytes=128,
            sha256=asset_hash,
            is_vector=True,
            normalization_action="copied",
            preview_generated=True,
            preview_path=f"/tmp/preview/{item_id}_{index}.svg",
            preview_action="copied_from_normalized_asset",
        )
        for index, asset_hash in enumerate(asset_hashes, start=1)
    ]
    item = CuratedItemRecord(
        candidate_id=f"candidate-{item_id}",
        source_id=source_id,
        source_item_id=source_item_id,
        source_url=f"https://example.org/{item_id}",
        discovery_method="fixture",
        item_id=item_id,
        normalized_license="PD-IL",
        rights_classification="open",
        eligibility="accepted",
        eligibility_reason="eligible",
        is_synthetic=is_synthetic,
        provenance={"source_name": source_id},
        acquired_assets=acquired_assets,
        normalized_assets=normalized_assets,
        qa_status="passed",
        qa_fail_reasons=[],
        content_fingerprint=f"fingerprint:{item_id}",
        dedupe_cluster_id=None,
        dedupe_status="retained",
        canonical_item_id=item_id,
    )
    update = {"title": title, "metadata": metadata or {}, "provenance": {"source_name": source_id}}
    return item.model_copy(update=update)


def _classified_item(
    *,
    item_id: str,
    source_id: str,
    source_item_id: str,
    rights_classification: RightsClassification = RightsClassification.open,
    dedupe_cluster_id: str | None = None,
    provenance: dict[str, object] | None = None,
):
    base = _curated_item(
        item_id=item_id,
        source_id=source_id,
        source_item_id=source_item_id,
        asset_hashes=["asset"],
        title="fixture title",
        metadata={"description": "fixture description"},
    )
    return classify_items(
        [
            base.model_copy(
                update={
                    "rights_classification": rights_classification,
                    "dedupe_cluster_id": dedupe_cluster_id,
                    "provenance": provenance or {"source_name": source_id},
                }
            )
        ],
        load_and_validate_bundle(),
    ).classified_items[0]


def _privacy_scanned_item(**kwargs) -> PrivacyScannedItemRecord:
    classified = _classified_item(
        item_id=kwargs.pop("item_id", "pinkas_open:item"),
        source_id=kwargs.pop("source_id", "pinkas_open"),
        source_item_id=kwargs.pop("source_item_id", "folio-1"),
        rights_classification=kwargs.pop("rights_classification", RightsClassification.open),
        dedupe_cluster_id=kwargs.pop("dedupe_cluster_id", None),
        provenance=kwargs.pop("provenance", None),
    )
    return PrivacyScannedItemRecord(
        **classified.model_dump(),
        privacy_flag=kwargs.pop("privacy_flag", "clear"),
        privacy_reasons=kwargs.pop("privacy_reasons", []),
        privacy_decision=kwargs.pop("privacy_decision", "release_ready"),
    )


def _empty_review_data() -> ReviewData:
    return ReviewData(root=Path("/tmp/review_data"), manual_decisions=[], allowlist=[], blocklist=[])


def test_classification_private_branches_cover_unknown_and_confidence_paths() -> None:
    bundle = load_and_validate_bundle()

    assert _source_allowed_types(bundle, "missing_source") == []

    handwritten_template = _curated_item(
        item_id="project_synthetic:hand",
        source_id="project_synthetic",
        source_item_id="hand",
        asset_hashes=["a"],
        metadata={"synthetic_template_id": "handwritten_note"},
        is_synthetic=True,
    )
    assert _content_class(handwritten_template, bundle)[0] == "handwritten"

    printed_template = _curated_item(
        item_id="project_synthetic:printed",
        source_id="project_synthetic",
        source_item_id="printed",
        asset_hashes=["a"],
        metadata={"synthetic_template_id": "printed_letter"},
        is_synthetic=True,
    )
    assert _content_class(printed_template, bundle)[0] == "printed"

    printed_text = _curated_item(
        item_id="custom:printed",
        source_id="custom_source",
        source_item_id="printed",
        asset_hashes=["a"],
        title='דו"ח בדיקה',
    )
    assert _content_class(printed_text, bundle)[0] == "printed"

    printed_prior = _curated_item(
        item_id="custom:printed-prior",
        source_id="custom_source",
        source_item_id="printed-prior",
        asset_hashes=["a"],
        metadata={},
    )
    custom_bundle = replace(
        bundle,
        source_registry=bundle.source_registry.model_copy(
            update={
                "sources": bundle.source_registry.sources
                + [
                    bundle.source_registry.sources[0].model_copy(
                        update={
                            "id": "custom_source",
                            "allowed_content_types": ["printed_modern"],
                        }
                    )
                ]
            }
        ),
    )
    assert _content_class(printed_prior, custom_bundle)[0] == "printed"

    unknown_content = _curated_item(
        item_id="unknown:item",
        source_id="unknown_source",
        source_item_id="unknown",
        asset_hashes=["a"],
    )
    content_class, confidence, reasons = _content_class(unknown_content, bundle)
    assert (content_class, confidence) == ("mixed", 0.45)
    assert reasons == ["content_unknown"]

    year_inferred = _curated_item(
        item_id="custom:year",
        source_id="custom_source",
        source_item_id="year",
        asset_hashes=["a"],
        title="Memo 1984",
    )
    period_class, period_confidence, period_reasons = _period_class(year_inferred)
    assert (period_class, period_confidence) == ("modern", 0.7)
    assert period_reasons == ["period_inferred_from_year"]

    period_default = _curated_item(
        item_id="custom:period-default",
        source_id="custom_source",
        source_item_id="period-default",
        asset_hashes=["a"],
        title="Plain memo",
    )
    period_class, period_confidence, period_reasons = _period_class(period_default)
    assert (period_class, period_confidence) == ("modern", 0.6)
    assert period_reasons == ["period_source_prior_only"]

    hebrew_only = _curated_item(
        item_id="custom:hebrew",
        source_id="custom_source",
        source_item_id="hebrew",
        asset_hashes=["a"],
        title="שלום עולם",
    )
    assert _language_class(hebrew_only)[0] == "hebrew_only"

    language_non_hebrew = _curated_item(
        item_id="custom:latin",
        source_id="custom_source",
        source_item_id="latin",
        asset_hashes=["a"],
        title="Latin only",
    )
    language_class, language_confidence, language_reasons = _language_class(language_non_hebrew)
    assert (language_class, language_confidence) == ("mixed_language", 0.65)
    assert language_reasons == ["language_non_hebrew_title"]

    language_unknown_item = _curated_item(
        item_id="custom:lang-unknown",
        source_id="custom_source",
        source_item_id="lang-unknown",
        asset_hashes=["a"],
        title="12345",
    )
    language_class, language_confidence, language_reasons = _language_class(language_unknown_item)
    assert (language_class, language_confidence) == ("hebrew_only", 0.55)
    assert language_reasons == ["language_unknown"]

    medium_quality = _curated_item(
        item_id="custom:medium",
        source_id="custom_source",
        source_item_id="medium",
        asset_hashes=["a"],
    )
    medium_quality = medium_quality.model_copy(
        update={
            "normalized_assets": [
                medium_quality.normalized_assets[0].model_copy(update={"width": 700, "height": 900})
            ]
        }
    )
    assert _quality(medium_quality)[1] == "medium"

    low_quality = medium_quality.model_copy(update={"normalized_assets": []})
    assert _quality(low_quality)[1] == "low"

    classified = classify_items([unknown_content, low_quality], bundle)
    by_id = {item.item_id: item for item in classified.classified_items}
    assert "content_low_confidence" in by_id["unknown:item"].classification_review_reasons
    assert "period_low_confidence" in by_id["unknown:item"].classification_review_reasons
    assert "language_low_confidence" in by_id["unknown:item"].classification_review_reasons
    assert "quality_low" in by_id["custom:medium"].classification_review_reasons


def test_config_validation_catches_unknown_privacy_sources(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    privacy_path = config_root / "privacy_rules.yaml"
    privacy_path.write_text(
        privacy_path.read_text(encoding="utf-8").replace(
            "source_defaults:\n  nli_any_use_permitted: clear",
            "source_defaults:\n  ghost_source: clear\n  nli_any_use_permitted: clear",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="privacy rules reference unknown source ids"):
        load_and_validate_bundle(config_root)


def test_config_validation_catches_unknown_rule_sources(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    shutil.copytree(default_config_root(), config_root)
    privacy_path = config_root / "privacy_rules.yaml"
    privacy_path.write_text(
        privacy_path.read_text(encoding="utf-8").replace(
            "    applies_to_sources:\n      - nli_any_use_permitted",
            "    applies_to_sources:\n      - ghost_source",
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="privacy rule modern_letter_review references unknown source ids"):
        load_and_validate_bundle(config_root)


def test_privacy_helpers_cover_source_url_and_period_filtering() -> None:
    bundle = load_and_validate_bundle()
    item = _classified_item(item_id="nli_any_use_permitted:item", source_id="nli_any_use_permitted", source_item_id="item")

    assert _field_text(item, "source_url") == item.source_url
    assert _field_text(item, "unknown-field") == ""

    blocked_item = item.model_copy(
        update={
            "period_class": "historical",
            "title": "מכתב אישי",
            "metadata": {"description": "מכתב אישי"},
        }
    )
    outputs = apply_privacy_rules([blocked_item], bundle, "profile_open_v1")
    assert outputs.scanned_items[0].privacy_flag.value == "clear"

    review_item = item.model_copy(update={"title": "מכתב פרטי"})
    outputs = apply_privacy_rules([review_item], bundle, "profile_open_v1")
    assert outputs.scanned_items[0].privacy_flag.value == "possible_personal_data"


def test_review_queue_policy_and_cluster_paths() -> None:
    blocked = _privacy_scanned_item(
        item_id="pinkas_open:blocked",
        privacy_flag="blocked_sensitive",
        privacy_decision="blocked",
    )
    review_only = _privacy_scanned_item(
        item_id="pinkas_open:review-only",
        provenance={"source_name": "pinkas_open", "source_status": "review_only"},
        dedupe_cluster_id="cluster-1",
    )
    restricted = _privacy_scanned_item(
        item_id="pinkas_open:restricted",
        rights_classification=RightsClassification.restricted_review_only,
    )

    assert _split_group_id_pre_review(review_only) == "cluster-1"
    assert _suggested_decision(["policy:review_only_source"]) == "needs_policy_review"

    outputs = export_review_queue([blocked, review_only, restricted])

    assert len(outputs.blocked_items) == 1
    assert {item.suggested_decision for item in outputs.review_queue} == {"needs_policy_review"}
    assert any("policy:review_only_source" in item.review_reasons for item in outputs.review_queue)
    assert any("policy:restricted_rights" in item.review_reasons for item in outputs.review_queue)


def test_review_merge_applies_manual_and_override_decisions(tmp_path: Path) -> None:
    auto_release = _privacy_scanned_item(item_id="pinkas_open:auto-release")
    manual_review = _privacy_scanned_item(
        item_id="biblia_open:manual-approve",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    allow_review = _privacy_scanned_item(
        item_id="biblia_open:allow-approve",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    deferred_review = _privacy_scanned_item(
        item_id="biblia_open:manual-defer",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([auto_release, manual_review, allow_review, deferred_review])

    config_root = tmp_path / "config"
    config_root.mkdir()
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    (review_root / "manual_decisions" / "approve.json").write_text(
        json.dumps(
            {
                "decision": "approve",
                "item_id": "biblia_open:manual-approve",
                "rationale": "Reviewed and approved",
                "review_item_id": "review:biblia_open:manual-approve",
                "reviewer": "qa-1",
                "timestamp": "2026-04-21T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (review_root / "manual_decisions" / "defer.json").write_text(
        json.dumps(
            {
                "decision": "defer",
                "item_id": "biblia_open:manual-defer",
                "rationale": "Need later pass",
                "review_item_id": "review:biblia_open:manual-defer",
                "reviewer": "qa-2",
                "timestamp": "2026-04-21T10:05:00Z",
            }
        ),
        encoding="utf-8",
    )
    (review_root / "allowlists" / "allow.json").write_text(
        json.dumps(
            {
                "item_id": "biblia_open:allow-approve",
                "rationale": "Known-safe exemplar",
                "review_item_id": "review:biblia_open:allow-approve",
                "reviewer": "qa-3",
                "timestamp": "2026-04-21T10:10:00Z",
            }
        ),
        encoding="utf-8",
    )
    (review_root / "blocklists" / "block.json").write_text(
        json.dumps(
            {
                "item_id": "pinkas_open:auto-release",
                "rationale": "Exclude from this release",
                "reviewer": "qa-4",
                "timestamp": "2026-04-21T10:15:00Z",
            }
        ),
        encoding="utf-8",
    )

    review_data = load_review_data(default_config_root(), config_root)
    merged = merge_review_decisions(
        release_ready_items=outputs.release_ready_items,
        review_required_items=outputs.review_required_items,
        review_queue=outputs.review_queue,
        review_data=review_data,
    )

    assert {item.item_id for item in merged.release_ready_items} == {
        "biblia_open:allow-approve",
        "biblia_open:manual-approve",
    }
    assert {item.item_id for item in merged.rejected_items} == {"pinkas_open:auto-release"}
    assert {item.item_id for item in merged.unresolved_items} == {"biblia_open:manual-defer"}
    assert merged.summary["review_approved_count"] == 2
    assert merged.summary["review_rejected_count"] == 1
    assert merged.summary["review_unresolved_count"] == 1
    audit_by_item = {item.item_id: item for item in merged.decision_audit}
    assert audit_by_item["biblia_open:manual-approve"].decision_source == "manual_decision"
    assert audit_by_item["biblia_open:allow-approve"].decision_source == "allowlist"
    assert audit_by_item["pinkas_open:auto-release"].decision_source == "blocklist"
    assert audit_by_item["biblia_open:manual-defer"].outcome == "unresolved"


def test_review_merge_emits_default_unresolved_audit_record() -> None:
    review_required = _privacy_scanned_item(
        item_id="biblia_open:needs-default-unresolved",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([review_required])
    merged = merge_review_decisions(
        release_ready_items=outputs.release_ready_items,
        review_required_items=outputs.review_required_items,
        review_queue=outputs.review_queue,
        review_data=load_review_data(default_config_root()),
    )

    assert {item.item_id for item in merged.unresolved_items} == {"biblia_open:needs-default-unresolved"}
    assert merged.summary["decision_source_counts"] == {"default_unresolved": 1}
    assert merged.decision_audit[0].decision_source == "default_unresolved"
    assert merged.decision_audit[0].outcome == "unresolved"
    assert merged.decision_audit[0].review_item_id == "review:biblia_open:needs-default-unresolved"


def test_review_data_validation_rejects_static_conflicts(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    (review_root / "manual_decisions" / "one.json").write_text(
        json.dumps(
            {
                "decision": "approve",
                "item_id": "biblia_open:item-1",
                "rationale": "first",
                "review_item_id": "review:biblia_open:item-1",
                "reviewer": "qa-1",
                "timestamp": "2026-04-21T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (review_root / "manual_decisions" / "two.json").write_text(
        json.dumps(
            {
                "decision": "reject",
                "item_id": "biblia_open:item-1",
                "rationale": "second",
                "review_item_id": "review:biblia_open:item-1",
                "reviewer": "qa-2",
                "timestamp": "2026-04-21T10:05:00Z",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="duplicate manual review decisions"):
        load_review_data(default_config_root(), config_root)


def test_review_data_validation_rejects_allowlist_blocklist_conflicts(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    payload = {
        "item_id": "biblia_open:item-1",
        "rationale": "conflict",
        "reviewer": "qa-1",
        "timestamp": "2026-04-21T10:00:00Z",
    }
    (review_root / "allowlists" / "allow.json").write_text(json.dumps(payload), encoding="utf-8")
    (review_root / "blocklists" / "block.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ConfigValidationError, match="allowlist/blocklist conflicts"):
        load_review_data(default_config_root(), config_root)


def test_review_data_validation_rejects_manual_override_conflicts(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    (review_root / "manual_decisions" / "decision.json").write_text(
        json.dumps(
            {
                "decision": "approve",
                "item_id": "biblia_open:item-1",
                "rationale": "manual",
                "review_item_id": "review:biblia_open:item-1",
                "reviewer": "qa-1",
                "timestamp": "2026-04-21T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (review_root / "allowlists" / "allow.json").write_text(
        json.dumps(
            {
                "item_id": "biblia_open:item-1",
                "rationale": "override",
                "reviewer": "qa-2",
                "timestamp": "2026-04-21T10:05:00Z",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="manual-decision/override conflicts"):
        load_review_data(default_config_root(), config_root)


def test_load_review_data_rejects_invalid_json_record(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    config_root.mkdir()
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    (review_root / "manual_decisions" / "bad.json").write_text(
        json.dumps({"item_id": "biblia_open:item-1"}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigValidationError, match="ReviewDecisionRecord validation failed"):
        load_review_data(default_config_root(), config_root)


def test_resolve_review_data_root_prefers_existing_repo_root_for_explicit_config_root(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    config_root = repo_root / "src" / "hocrgen" / "config"
    config_root.mkdir(parents=True)
    review_root = repo_root / "review_data"
    review_root.mkdir()

    resolved = resolve_review_data_root(config_root, config_root)

    assert resolved == review_root


def test_resolve_review_data_root_falls_back_for_default_config_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_default = tmp_path / "repo" / "src" / "hocrgen" / "config"
    fake_default.mkdir(parents=True)
    monkeypatch.setattr("hocrgen.review.merge.default_config_root", lambda: fake_default)

    resolved = resolve_review_data_root(fake_default)

    assert resolved == fake_default.parents[2] / "review_data"


def test_review_merge_rejects_stale_or_mismatched_decisions(tmp_path: Path) -> None:
    review_required = _privacy_scanned_item(
        item_id="biblia_open:queued-item",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([review_required])

    config_root = tmp_path / "config"
    config_root.mkdir()
    review_root = tmp_path / "review_data"
    (review_root / "manual_decisions").mkdir(parents=True)
    (review_root / "allowlists").mkdir(parents=True)
    (review_root / "blocklists").mkdir(parents=True)
    (review_root / "manual_decisions" / "bad.json").write_text(
        json.dumps(
            {
                "decision": "approve",
                "item_id": "biblia_open:queued-item",
                "rationale": "bad review id",
                "review_item_id": "review:biblia_open:other-item",
                "reviewer": "qa-1",
                "timestamp": "2026-04-21T10:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    review_data = load_review_data(default_config_root(), config_root)
    with pytest.raises(StageExecutionError, match="unknown review queue id"):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )


def test_review_merge_rejects_manual_decision_review_item_mismatch() -> None:
    queued = _privacy_scanned_item(
        item_id="biblia_open:queued",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([queued])
    review_data = replace(
        _empty_review_data(),
        manual_decisions=[
            ReviewDecisionRecord(
                review_item_id="review:biblia_open:other",
                item_id="biblia_open:queued",
                decision="approve",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="mismatch",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="unknown review queue id"):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )


def test_review_merge_rejects_unknown_manual_decision_item() -> None:
    review_data = replace(
        _empty_review_data(),
        manual_decisions=[
            ReviewDecisionRecord(
                review_item_id="review:biblia_open:missing-item",
                item_id="biblia_open:missing-item",
                decision="approve",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="missing",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="unknown review item"):
        merge_review_decisions(
            release_ready_items=[],
            review_required_items=[],
            review_queue=[],
            review_data=review_data,
        )


def test_review_merge_rejects_manual_decision_same_queue_different_item() -> None:
    queued_a = _privacy_scanned_item(
        item_id="biblia_open:queued-a",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    queued_b = _privacy_scanned_item(
        item_id="biblia_open:queued-b",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([queued_a, queued_b])
    review_data = replace(
        _empty_review_data(),
        manual_decisions=[
            ReviewDecisionRecord(
                review_item_id="review:biblia_open:queued-b",
                item_id="biblia_open:queued-a",
                decision="approve",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="mismatch",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="manual review decision review/item mismatch"):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )


def test_review_merge_rejects_allowlist_for_non_queued_item() -> None:
    review_data = replace(
        _empty_review_data(),
        allowlist=[
            ReviewOverrideRecord(
                item_id="biblia_open:not-queued",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="not queued",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="allowlist entry must target a review-queued item"):
        merge_review_decisions(
            release_ready_items=[],
            review_required_items=[],
            review_queue=[],
            review_data=review_data,
        )


def test_review_merge_rejects_allowlist_review_item_mismatch() -> None:
    queued = _privacy_scanned_item(
        item_id="biblia_open:queued",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([queued])
    review_data = replace(
        _empty_review_data(),
        allowlist=[
            ReviewOverrideRecord(
                item_id="biblia_open:queued",
                review_item_id="review:biblia_open:other",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="mismatch",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="allowlist review/item mismatch"):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )


def test_review_merge_rejects_blocklist_for_unknown_item() -> None:
    review_data = replace(
        _empty_review_data(),
        blocklist=[
            ReviewOverrideRecord(
                item_id="biblia_open:unknown",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="unknown",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="blocklist entry references unknown item"):
        merge_review_decisions(
            release_ready_items=[],
            review_required_items=[],
            review_queue=[],
            review_data=review_data,
        )


def test_review_merge_rejects_blocklist_review_id_without_queued_item() -> None:
    release_ready = _privacy_scanned_item(item_id="pinkas_open:release-ready")
    review_data = replace(
        _empty_review_data(),
        blocklist=[
            ReviewOverrideRecord(
                item_id="pinkas_open:release-ready",
                review_item_id="review:pinkas_open:release-ready",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="bad review id",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="blocklist review item id must target a review-queued item"):
        merge_review_decisions(
            release_ready_items=[release_ready],
            review_required_items=[],
            review_queue=[],
            review_data=review_data,
        )


def test_review_merge_rejects_blocklist_review_item_mismatch() -> None:
    queued = _privacy_scanned_item(
        item_id="biblia_open:queued",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([queued])
    review_data = replace(
        _empty_review_data(),
        blocklist=[
            ReviewOverrideRecord(
                item_id="biblia_open:queued",
                review_item_id="review:biblia_open:other",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="mismatch",
            )
        ],
    )

    with pytest.raises(StageExecutionError, match="blocklist review/item mismatch"):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )


def test_review_merge_records_manual_reject_and_review_blocklist() -> None:
    auto_release = _privacy_scanned_item(item_id="pinkas_open:auto-release")
    review_reject = _privacy_scanned_item(
        item_id="biblia_open:review-reject",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    review_block = _privacy_scanned_item(
        item_id="biblia_open:review-block",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([auto_release, review_reject, review_block])
    review_data = replace(
        _empty_review_data(),
        manual_decisions=[
            ReviewDecisionRecord(
                review_item_id="review:biblia_open:review-reject",
                item_id="biblia_open:review-reject",
                decision="reject",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="reject",
            )
        ],
        blocklist=[
            ReviewOverrideRecord(
                item_id="biblia_open:review-block",
                review_item_id="review:biblia_open:review-block",
                reviewer="qa-2",
                timestamp="2026-04-21T10:05:00Z",
                rationale="block",
            )
        ],
    )

    merged = merge_review_decisions(
        release_ready_items=outputs.release_ready_items,
        review_required_items=outputs.review_required_items,
        review_queue=outputs.review_queue,
        review_data=review_data,
    )

    assert {item.item_id for item in merged.rejected_items} == {
        "biblia_open:review-block",
        "biblia_open:review-reject",
    }
    assert merged.summary["review_rejected_count"] == 2
    audit_by_item = {item.item_id: item for item in merged.decision_audit}
    assert audit_by_item["biblia_open:review-reject"].decision_source == "manual_decision"
    assert audit_by_item["biblia_open:review-block"].decision_source == "blocklist"


def test_review_merge_rejects_override_queue_mismatch() -> None:
    queued_a = _privacy_scanned_item(
        item_id="biblia_open:queued-a",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    queued_b = _privacy_scanned_item(
        item_id="biblia_open:queued-b",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([queued_a, queued_b])
    review_data = replace(
        _empty_review_data(),
        allowlist=[
            ReviewOverrideRecord(
                item_id="biblia_open:queued-a",
                review_item_id="review:biblia_open:queued-b",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="mismatch",
            )
        ],
    )

    with pytest.raises(
        StageExecutionError,
        match=r"override review/item mismatch for review_item_id review:biblia_open:queued-b: expected item_id biblia_open:queued-a, got item_id biblia_open:queued-b",
    ):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )


def test_review_merge_rejects_override_review_id_for_different_item_without_item_match() -> None:
    queued = _privacy_scanned_item(
        item_id="biblia_open:queued-b",
        privacy_flag="needs_review",
        privacy_reasons=["metadata_signal"],
        privacy_decision="review_required",
    )
    outputs = export_review_queue([queued])
    review_data = replace(
        _empty_review_data(),
        allowlist=[
            ReviewOverrideRecord(
                item_id="biblia_open:queued-a",
                review_item_id="review:biblia_open:queued-b",
                reviewer="qa-1",
                timestamp="2026-04-21T10:00:00Z",
                rationale="mismatch",
            )
        ],
    )

    with pytest.raises(
        StageExecutionError,
        match=r"override review/item mismatch for item_id biblia_open:queued-a: review_item_id review:biblia_open:queued-b resolves to item_id biblia_open:queued-b",
    ):
        merge_review_decisions(
            release_ready_items=outputs.release_ready_items,
            review_required_items=outputs.review_required_items,
            review_queue=outputs.review_queue,
            review_data=review_data,
        )
