from __future__ import annotations

from pathlib import Path


CURRENT_COMPLETED_NOTATION = "F1d"
PLANNING_FILES = [
    Path(".agent-plan.md"),
    Path("README.md"),
    Path("docs/HeOCR_hocrgen_long_term_roadmap.md"),
    Path("docs/pre_alpha_freeze_plan.md"),
    Path("CONTRIBUTING.md"),
    Path("docs/source_adapter_contribution_guide.md"),
    Path("docs/synthetic_asset_contribution_guide.md"),
    Path("docs/release_governance.md"),
]
STALE_BRANCH_LOCAL_PHRASES = [
    "this branch",
    "remains unmerged",
    "current planned PR",
]
E4A_COMPATIBILITY_ANCHORS = [
    "release_record.json",
    "release_summary.json",
    "item_manifest.json",
    "release_diff.json",
    "CHANGELOG.md",
    "schema_version",
]
E4A_SCHEMA_POLICY_INVARIANTS = [
    "additive",
    "new schema version or schema id",
    "release-relative",
    "portable",
]


def test_planning_docs_agree_on_current_and_next_notation() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")

    assert f"Last completed roadmap action on the current ref: `{CURRENT_COMPLETED_NOTATION}`" in agent_plan
    assert "next planned critical-path implementation should move to `F2` benchmark ground-truth foundations" in agent_plan
    assert f"| D3 | Expansion and benchmark formation | D3a | Benchmark subset v1 | completed |" in roadmap
    assert f"| D4 | Expansion and benchmark formation | D4a, D4b | Richer synthetic generation, then synthetic diversity/reporting hardening | completed |" in roadmap
    assert f"| D5 | Expansion and benchmark formation | D5a | Optional transcription-ready architecture | completed |" in roadmap
    assert f"| E1 | Ecosystem maturity | E1a | Community contribution model | completed |" in roadmap
    assert f"| E2 | Ecosystem maturity | E2a, E2b | Baselines/evaluation utilities, then live/cached NLI seed acquisition | completed |" in roadmap
    assert f"| E3 | Ecosystem maturity | E3a | Annotation subset pilots | completed |" in roadmap
    assert f"| E4 | Ecosystem maturity | E4a | Multi-release governance maturity | completed |" in roadmap
    assert "| F1 | Beta-scale acquisition trial | F1a, F1b, F1b2, F1b3, F1b4, F1c, F1d |" in roadmap
    assert "| F2 | Benchmark ground-truth foundation | F2a, F2b |" in roadmap
    assert "| F3 | Modern handwritten acquisition program | F3a, F3b |" in roadmap
    assert "| F4 | External synthetic provider integration | F4a, F4b, F4c, F4d |" in roadmap
    assert "| F5 | Public beta and publication readiness | F5a, F5b |" in roadmap
    assert f"The immediate acquisition implementation critical path after `{CURRENT_COMPLETED_NOTATION}` is:" in roadmap
    assert "Roadmap notation is location-based" in readme
    assert "`E4a` are complete on the current ref" in Path("docs/pre_alpha_freeze_plan.md").read_text(encoding="utf-8")


def test_f1a_beta_trial_plan_is_bounded_and_source_balanced() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    issue_template = Path(".github/ISSUE_TEMPLATE/beta_trial.yml").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, issue_template])

    for required in [
        "80 real",
        "80 synthetic",
        "27 NLI",
        "27 Pinkas",
        "26 BiblIA",
        "operator-only",
        "no broad live-source crawling",
        "no public beta export",
        "no release-candidate export",
        "no network-dependent CI",
    ]:
        assert required in combined

    assert "Pinkas/BiblIA source-depth feasibility" in issue_template
    assert "publication to Hugging Face or the GitHub dataset repo" in combined


def test_post_f1_roadmap_captures_outside_review_takeaways() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    issue_template = Path(".github/ISSUE_TEMPLATE/beta_trial.yml").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, issue_template])

    for required in [
        "gate-driven beta-readiness program",
        "near-duplicate/source-group leakage",
        "Benchmark ground-truth foundation",
        "Modern handwritten acquisition program",
        "External synthetic provider integration",
        "Public beta and publication readiness",
        "source-depth, uniqueness, ground-truth, review, and portability gates",
    ]:
        assert required in combined

    for required in [
        "`F1b`",
        "`F1b2`",
        "`F1b3`",
        "`F1b4`",
        "`F1c`",
        "`F1d`",
        "`F2`",
        "`F3`",
        "`F4a`",
        "`F4b`",
        "`F4c`",
        "`F4d`",
        "`F5`",
    ]:
        assert required in combined


def test_f4a_synthetic_spinout_docs_keep_four_repo_boundary_visible() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    synthetic_guide = Path("docs/synthetic_asset_contribution_guide.md").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, synthetic_guide])

    for required in [
        "hocrsyngen",
        "HeOCRsynth",
        "generation_manifest.json",
        "candidate synthetic inputs",
        "PROJECT-SYNTHETIC",
        "synthetic disclosure",
        "fixture-backed",
        "no-GPU",
        "REST",
        "GPU",
        "LLM",
        "diffusion",
        "persona",
        "generator controls",
        "mixed real+synthetic",
        "synthetic-only",
    ]:
        assert required in combined

    for path in [
        Path("docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_chatgpt.md"),
        Path("docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_gemini_1.md"),
        Path("docs/2026_05_02_heocrsyn_spinout/hocrgen_synthetic_spinout_plan_amendment_by_gemini_2.md"),
    ]:
        assert path.exists()


def test_planning_docs_do_not_use_stale_branch_local_status_phrases() -> None:
    for path in PLANNING_FILES:
        text = path.read_text(encoding="utf-8").casefold()
        for phrase in STALE_BRANCH_LOCAL_PHRASES:
            assert phrase not in text, f"{path} contains stale planning phrase: {phrase}"


def test_e1a_contribution_docs_keep_safety_rails_visible() -> None:
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    source_guide = Path("docs/source_adapter_contribution_guide.md").read_text(encoding="utf-8")
    synthetic_guide = Path("docs/synthetic_asset_contribution_guide.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    contributing_lower = contributing.casefold()
    for required in [
        "source proposal workflow",
        "review policy",
        "synthetic asset contribution rules",
        "dataset issue taxonomy",
    ]:
        assert required in contributing_lower

    for required in [
        "hocrgen config validate",
        "policy filtering",
        "privacy screening",
        "review merge",
        "export portability",
    ]:
        assert required in readme

    assert "broad live crawling" in source_guide
    assert "Unknown rights" in release_governance
    assert "release profile synthetic fraction caps" in synthetic_guide
    assert "E1a" in release_governance


def test_e2a_evaluation_docs_keep_utility_scope_visible() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")

    for required in [
        "hocrgen evaluate-benchmark",
        "character error rate",
        "leaderboard_ready",
        "release-relative and portable",
    ]:
        assert required in readme

    assert "without adding model training infrastructure" in roadmap


def test_e2b_nli_batch_acquisition_docs_keep_seed_boundary_visible() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    source_guide = Path("docs/source_adapter_contribution_guide.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")

    for required in [
        "--seed-source runnable",
        "--seed-source all",
        "--max-items",
        "skipped seeds",
    ]:
        assert required in readme

    assert "It does not add broad site crawling" in roadmap
    assert "leaves CI/release validation network-free" in source_guide


def test_e3a_annotation_pilot_docs_keep_optional_scope_visible() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")

    for required in [
        "annotation_data/pilots/e3a_annotation_pilot/config.json",
        "annotation_pilot_manifest.json",
        "annotation_pilot_selection_audit.json",
        "Current public and alpha outputs still do not require transcriptions or layout labels.",
    ]:
        assert required in readme

    assert "not a full annotation-production workflow" in roadmap
    assert "must not make annotation files mandatory" in design


def test_e4a_governance_docs_keep_multi_release_controls_visible() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")

    for required in [
        "Version governance and compatibility",
        "Removal and takedown workflow",
        "Schema migration policy",
        "Source deprecation policy",
        "Benchmark stability guarantees",
    ]:
        assert required in release_governance

    for required in E4A_COMPATIBILITY_ANCHORS:
        assert required in readme
        assert required in release_governance
        assert required in design

    for required in E4A_SCHEMA_POLICY_INVARIANTS:
        assert required in readme
        assert required in release_governance
        assert required in design

    for required in [
        "GitHub private vulnerability reporting",
        "out-of-band private contact path",
        "avoid asking reporters to disclose sensitive details in a public issue",
        "human-readable audit rationale",
        "future schema work",
    ]:
        assert required in release_governance

    for text in [readme, release_governance, design]:
        assert "human" in text and "audit rationale" in text

    assert "Current alpha/public payload selection is unchanged." in roadmap
    assert "Release compatibility contract" in design
    assert "breaking serialized schema changes require a new schema version or schema id" in release_governance.casefold()
