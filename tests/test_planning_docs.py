from __future__ import annotations

from pathlib import Path


CURRENT_COMPLETED_NOTATION = "F6f1"
PLANNING_FILES = [
    Path(".agent-plan.md"),
    Path("README.md"),
    Path("docs/HeOCR_hocrgen_long_term_roadmap.md"),
    Path("docs/pre_alpha_freeze_plan.md"),
    Path("CONTRIBUTING.md"),
    Path("docs/source_adapter_contribution_guide.md"),
    Path("docs/synthetic_asset_contribution_guide.md"),
    Path("docs/release_governance.md"),
    Path("docs/hocrsyngen_adapter_preflight_plan.md"),
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


def _roadmap_table_rows(roadmap: str) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in roadmap.splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or cells[0] in {"Milestone", "PR"} or cells[0].startswith("---"):
            continue
        rows[cells[0]] = cells
    return rows


def test_planning_docs_agree_on_current_and_next_notation() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    roadmap_rows = _roadmap_table_rows(roadmap)

    assert f"Last completed roadmap action on the current ref: `{CURRENT_COMPLETED_NOTATION}`" in agent_plan
    assert "`F1e` resolves the previously visible F1d benchmark/holdout source-group risk" in agent_plan
    assert "`F5a` now defines public beta publishability separately from operator trial success" in agent_plan
    assert "`F5b` now implements deliberate public beta packaging and handoff artifacts" in agent_plan
    assert "`F5c` now derives a public beta blocker-closure plan" in agent_plan
    assert "`F5d` now writes `manifests/public_beta_repo_owned_blocker_report.json`" in agent_plan
    assert "`F6a` now defines the post-F5 public beta closure roadmap" in agent_plan
    assert "`F6b` now records GitHub private vulnerability reporting" in agent_plan
    assert "`F6c` now evaluates current benchmark-reference evidence" in agent_plan
    assert "`F6d` now evaluates current privacy/review evidence" in agent_plan
    assert "`F6e` now evaluates current source-depth/composition evidence" in agent_plan
    assert "`F6f1` now records the hocrsyngen S6 handoff review" in agent_plan
    assert "| D3 | Expansion and benchmark formation | D3a | Benchmark subset v1 | completed |" in roadmap
    assert "| D4 | Expansion and benchmark formation | D4a, D4b | Richer synthetic generation, then synthetic diversity/reporting hardening | completed |" in roadmap
    assert "| D5 | Expansion and benchmark formation | D5a | Optional transcription-ready architecture | completed |" in roadmap
    assert "| E1 | Ecosystem maturity | E1a | Community contribution model | completed |" in roadmap
    assert "| E2 | Ecosystem maturity | E2a, E2b | Baselines/evaluation utilities, then live/cached NLI seed acquisition | completed |" in roadmap
    assert "| E3 | Ecosystem maturity | E3a | Annotation subset pilots | completed |" in roadmap
    assert "| E4 | Ecosystem maturity | E4a | Multi-release governance maturity | completed |" in roadmap
    assert "| F1 | Beta-scale acquisition trial | F1a, F1b, F1b2, F1b3, F1b4, F1c, F1d, F1e |" in roadmap
    assert "| F2 | Benchmark ground-truth foundation | F2a, F2b |" in roadmap
    assert "| F3 | Modern handwritten acquisition program | F3a, F3b |" in roadmap
    assert "| F4 | External synthetic provider integration | F4a, F4b, F4c, F4d, F4e |" in roadmap
    assert "| F5 | Public beta and publication readiness | F5a, F5b, F5c, F5d | Public beta gates, publication packaging, dataset-card, checksum/archive manifests, takedown-ready export handoff, blocker-closure sequencing, and repo-owned blocker reporting | completed-with-blockers |" in roadmap
    assert roadmap_rows["F6"][1] == "Public beta closure and external input integration"
    assert roadmap_rows["F6"][2].split(", ") == ["F6a", "F6b", "F6c", "F6d", "F6e", "F6f1", "F6f2", "F6g"]
    assert roadmap_rows["F6"][4] == "partial"
    assert "| F5a | F5 | Define public beta readiness gates over source depth, uniqueness, ground truth, review, and portability | no | completed |" in roadmap
    assert "| F5b | F5 | Implement public beta publication packaging and handoff workflow | no | completed | current ref public beta packaging and blocked handoff workflow |" in roadmap
    assert "| F5c | F5 | Close public beta readiness blocker sequencing and repo-owned handoff gaps | no | completed | current ref blocker-closure plan and takedown reporting config |" in roadmap
    assert "| F5d | F5 | Close repo-owned public beta readiness gates before external scale inputs | no | completed | current ref repo-owned blocker evidence and private-reporting settings check |" in roadmap
    expected_f6_pr_rows = {
        "F6a": ("completed", ["planning-only"]),
        "F6b": ("completed", ["verified", "takedown/removal"]),
        "F6c": ("completed", ["1 / 3", "reviewed/adjudicated"]),
        "F6d": ("completed", ["default-unresolved"]),
        "F6e": ("completed", ["public-profile", "operator-only"]),
        "F6f1": ("completed", ["hocrsyngen S6", "release/import metadata gap"]),
        "F6f2": ("planned", ["release/import metadata form", "generation_manifest.v1"]),
        "F6g": ("planned", ["privacy/review closure", "F6e-F6f2"]),
    }
    for pr_id, (status, note_tokens) in expected_f6_pr_rows.items():
        row = roadmap_rows[pr_id]
        assert row[1] == "F6"
        assert row[3] == "no"
        assert row[4] == status
        for token in note_tokens:
            assert token in row[5]
    assert f"The immediate implementation critical path after `{CURRENT_COMPLETED_NOTATION}` is:" in roadmap
    assert "Roadmap notation is location-based" in readme
    assert "`F5a`, `F5b`, `F5c`, `F5d`, `F6a`, `F6b`, `F6c`, `F6d`, `F6e`, and `F6f1` are complete on the current ref" in Path("docs/pre_alpha_freeze_plan.md").read_text(encoding="utf-8")


def test_f3_modern_handwritten_policy_and_intake_are_consistent_and_bounded() -> None:
    policy = Path("docs/modern_handwritten_acquisition_policy.md").read_text(encoding="utf-8")
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    contributing = Path("CONTRIBUTING.md").read_text(encoding="utf-8")
    source_guide = Path("docs/source_adapter_contribution_guide.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")
    policy_lower = policy.casefold()

    for required in [
        "F3a",
        "F3b",
        "contributor consent",
        "public-use release terms",
        "rights provenance",
        "contemporary privacy screening",
        "takedown/removal",
        "scanning/upload standards",
        "operator review",
        "composition targets",
        "demographic bands",
        "script style",
        "page type",
        "mixed-language",
        "modern real handwriting",
        "historical public sources",
        "synthetic data",
        "typed intake manifests",
        "HEOCR-CONSENT-OPEN",
    ]:
        assert required.casefold() in policy_lower

    for required_policy_boundary in [
        "does not collect samples",
        "does not add broad upload/acquisition automation",
        "does not add a default public-profile source",
        "does not claim public beta readiness",
        "Historical public-source rights and synthetic-provider manifests do not satisfy modern contributor-consent requirements.",
        "minor participation is out of scope for F3a/F3b",
        "takedown is prospective for hocrgen/HeOCR-controlled distribution",
        "cannot promise to revoke already distributed public copies",
        "consent/release terms version",
        "consent effective date",
        "consent scope",
        "normalized license id",
        "affected future release versions",
        "first/last release versions",
    ]:
        assert required_policy_boundary.casefold() in policy_lower

    assert "| F3 | Modern handwritten acquisition program | F3a, F3b |" in roadmap
    assert "| F3 | Modern handwritten acquisition program | F3a, F3b | Rights-clean modern Hebrew handwriting collection policy and operator acquisition workflow | completed |" in roadmap
    assert "| F3a | F3 | Define rights-clean modern handwritten Hebrew collection policy, consent, privacy, and takedown workflow | no | completed |" in roadmap
    assert "| F3b | F3 | Implement operator workflow for bounded modern handwriting acquisition and review | no | completed |" in roadmap
    assert "`F3b` implements the bounded operator workflow" in roadmap
    assert "`F3b`: hocrgen now validates operator-provided modern handwriting intake manifests" in agent_plan
    assert "`F3b` implements the bounded operator workflow" in readme
    assert "F3b does not add a default modern handwriting source" in release_governance
    assert "Do not collect contributor samples" in contributing
    assert "F3b `modern_handwriting_intake` manifest contract" in source_guide
    assert "implemented by the F3b `modern_handwriting_intake` adapter" in design


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
        "`F1e`",
        "`F2`",
        "`F3`",
        "`F4a`",
        "`F4b`",
        "`F4c`",
        "`F4d`",
        "`F4e`",
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


def test_f4c_hocrsyngen_metadata_gates_are_documented() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")
    synthetic_guide = Path("docs/synthetic_asset_contribution_guide.md").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, design, synthetic_guide])

    for required in [
        "`F4c`",
        "provider metadata",
        "offline manifest-batch",
        "no-network/no-REST/no-GPU/no-LLM/no-diffusion",
        "logical RTL",
        "Hebrew coverage",
        "source-health signals",
        "synthetic composition",
        "does not import hocrsyngen internals",
        "does not call the generator package",
    ]:
        assert required in combined


def test_f4d_heocrsynth_export_handoff_is_documented() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")
    synthetic_guide = Path("docs/synthetic_asset_contribution_guide.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, design, synthetic_guide, release_governance])

    for required in [
        "`F4d`",
        "export-synthetic",
        "HeOCRsynth",
        "synthetic-only",
        "data/synthetic/<split>/<item_id>/",
        "PROJECT-SYNTHETIC",
        "synthetic disclosure",
        "hocrsyngen provider",
        "rendering metadata",
        "Hebrew coverage",
        "dataset_id: HeOCRsynth",
        "release_kind: synthetic_only",
        "real_items: 0",
        "raw generator",
        "mixed `HeOCR`",
    ]:
        assert required in combined


def test_f4e_shared_export_packaging_primitives_are_documented() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, release_governance])

    for required in [
        "`F4e`",
        "shared release export packaging primitives",
        "hocrgen.package.common",
        "alpha",
        "HeOCRsynth",
        "release-relative",
        "portable",
        "mixed `HeOCR`",
        "synthetic-only",
    ]:
        assert required in combined


def test_f5b_public_beta_packaging_contract_is_documented_and_bounded() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")

    for required_agent_plan in [
        "`F5a`: public beta readiness is now defined as a publishability contract",
        "`F5b`: `hocrgen export-public-beta` now packages",
        "larger validated hocrsyngen batch",
    ]:
        assert required_agent_plan in agent_plan

    for required_readme in [
        "operator trial success",
        "hocrgen export-public-beta --profile profile_open_v1 --dry-run",
        "larger validated hocrsyngen manifest batch",
        "valid statuses are only `pass` and `blocked`",
        "public_beta_blocker_closure_plan.json",
        "public_beta_repo_owned_blocker_report.json",
        "repo_owned_immediately_actionable",
        "external_input_dependent",
        "does not publish to `HeOCR`, Hugging Face, Kaggle, or `HeOCRsynth`",
    ]:
        assert required_readme in readme

    for required_roadmap in [
        "| Gate | Required evidence artifacts | Pass state | Blocker examples | F5b enforcement expectation |",
        "source depth and composition",
        "discover/source_depth_feasibility.json",
        "synthetic target scale",
        "larger validated hocrsyngen batch",
        "Current `2 / 80` fixture batch used as readiness evidence",
        "rights and provenance",
        "privacy and review",
        "Duplicate, source-group, split, and benchmark/holdout leakage",
        "benchmark_reference_status.json",
        "annotation expectations",
        "Portability, checksums, and archive",
        "SHA-256 digest",
        "public_beta_readiness_report.json",
        "public_beta_blocker_closure_plan.json",
        "public and private intake path",
    ]:
        assert required_roadmap.casefold() in roadmap.casefold()

    for non_goal in [
        "perform repository sync, upload, release tagging, or blocked publication-report emission",
        "publish or copy a public beta tree to `HeOCR`, Hugging Face, Kaggle, or another public host",
        "does not change current `export-alpha` or `export-synthetic` behavior",
        "does not relax rights, privacy, review, dedupe, split, benchmark, synthetic-cap, or export-portability gates",
    ]:
        assert non_goal.casefold() in roadmap.casefold()

    for required_governance in [
        "canonical F5a gate matrix",
        "manifests/public_beta_readiness_report.json",
        "manifests/public_beta_blocker_closure_plan.json",
        "manifests/public_beta_repo_owned_blocker_report.json",
        "src/hocrgen/config/public_beta.yaml",
        "status is `pass`",
        "`blocked` gate must stop repository sync, upload, release tagging, and publication reports",
        "SHA-256 checksum manifests",
        "archive manifests",
        "hocrgen export-public-beta",
    ]:
        assert required_governance in release_governance

    for required_design in [
        "manifests/public_beta_readiness_report.json",
        "manifests/public_beta_blocker_closure_plan.json",
        "manifests/public_beta_repo_owned_blocker_report.json",
        "`gate_id`, `status`, `evidence_paths`, and `rationale`",
        "Valid statuses are `pass` and `blocked`",
        "release-level SHA-256 checksum manifest",
        "archive manifest",
        "recomputes asset and archive digests",
        "do not meet the planned public beta synthetic target scale",
        "must not emit `manifests/publication_report.json`",
        "item/status-level repo-owned blocker evidence",
    ]:
        assert required_design in design

    assert "| F5a | F5 | Define public beta readiness gates over source depth, uniqueness, ground truth, review, and portability | no | completed | current ref public beta readiness gate contract |" in roadmap
    assert "| F5b | F5 | Implement public beta publication packaging and handoff workflow | no | completed | current ref public beta packaging and blocked handoff workflow |" in roadmap
    assert "| F5c | F5 | Close public beta readiness blocker sequencing and repo-owned handoff gaps | no | completed | current ref blocker-closure plan and takedown reporting config |" in roadmap
    assert "| F5d | F5 | Close repo-owned public beta readiness gates before external scale inputs | no | completed | current ref repo-owned blocker evidence and private-reporting settings check |" in roadmap
    assert "For F5a, the required planning notation is:" in release_governance
    assert "For F5b, the required planning notation is:" in release_governance
    assert "For F5c, the required planning notation is:" in release_governance
    assert "For F5d, the required planning notation is:" in release_governance
    assert "parent milestone: `F5 - Public beta and publication readiness`" in release_governance


def test_f6_post_f5_closure_roadmap_is_documented_and_evidence_gated() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    release_governance = Path("docs/release_governance.md").read_text(encoding="utf-8")
    design = Path("docs/hocrgen_design_and_spec.md").read_text(encoding="utf-8")
    pre_alpha = Path("docs/pre_alpha_freeze_plan.md").read_text(encoding="utf-8")
    combined = "\n".join([agent_plan, readme, roadmap, release_governance, design, pre_alpha])

    for required in [
        "`F6a`",
        "planning-only",
        "Public beta closure and external input integration",
        "`F6b`",
        "`F6c`",
        "`F6d`",
        "`F6e`",
        "`F6f1`",
        "`F6f2`",
        "`F6g`",
        "verified private reporting path",
        "reviewed/adjudicated",
        "review/config/source-status changes",
        "default-unresolved review decision",
        "`privacy_review` blocked",
        "real public-profile source-depth/composition evidence",
        "larger validated hocrsyngen",
        "generation_manifest.v1",
        "installed-CLI adapter preflight",
        "release/import metadata",
        "provider, rendering, and Hebrew coverage metadata",
        "operator-only diagnostics",
        "privacy/review closure, source-depth, and synthetic-scale inputs",
        "2 / 80",
        "source-depth composition",
        "must remain blocked",
        "closes takedown/private reporting readiness with the verified GitHub private vulnerability reporting path",
        "separate governance PR explicitly changes",
        "adds no runtime behavior",
        "does not publish",
        "does not relax",
        "does not import hocrsyngen internals",
        "default release/export paths",
        "GPU/LLM/diffusion",
    ]:
        assert required in combined

    assert "| F6 | Public beta closure and external input integration | F6a, F6b, F6c, F6d, F6e, F6f1, F6f2, F6g |" in roadmap
    assert "For F6a, the required planning notation is:" in release_governance
    assert "For F6b, the required planning notation is:" in release_governance
    assert "For F6d, the required planning notation is:" in release_governance
    assert "For F6e, the required planning notation is:" in release_governance
    assert "For F6f1, the required planning notation is:" in release_governance
    assert "parent milestone: `F6 - Public beta closure and external input integration`" in release_governance
    assert "F6 does not permit hocrgen to import hocrsyngen internals" in design
    assert "hocrgen-owned import packet" in Path("docs/hocrsyngen_adapter_preflight_plan.md").read_text(encoding="utf-8")
    assert "Future implementation should follow F6" in pre_alpha


def test_f6f1_hocrsyngen_adapter_preflight_plan_locks_operator_boundary() -> None:
    preflight_plan = Path("docs/hocrsyngen_adapter_preflight_plan.md").read_text(encoding="utf-8")

    for required_evidence in [
        "schema_version: template_catalog.v1",
        "schema_version: template_catalog.v2",
        "schema_version: contract_fixture_catalog.v1",
        "schema_version: contract_fixture_export.v1",
        "schema_version: generation_report.v1",
        "schema_version: validation_report.v1",
        "sample_count: 4",
        "page_count: 4",
        "hocrsyngen generation_manifest.v1 validation failed",
        "missing `provider_metadata`",
        "missing `samples.0.rendering_metadata`",
        "missing `samples.0.hebrew_coverage`",
        "missing `samples.1.rendering_metadata`",
        "missing `samples.1.hebrew_coverage`",
    ]:
        assert required_evidence in preflight_plan

    for required_contract in [
        "`hocrgen hocrsyngen-preflight`",
        "`--output-dir PATH`",
        "`--hocrsyngen-executable PATH_OR_NAME`",
        "`--mode fixture|generate`",
        "`--count N --seed S`",
        "`--rendering-coverage-report`",
        "`--report PATH`",
        "`--overwrite`",
        "`--timeout-seconds N`",
        "Exit `0`",
        "Exit `1`",
        "Exit `2`",
        "`release_eligible: false`",
    ]:
        assert required_contract in preflight_plan

    for required_boundary in [
        "status on this ref: completed (planning-only; no runtime behavior)",
        "two deliberately separate shapes",
        "The public hocrsyngen `generation_manifest.v1` shape",
        "The hocrgen-hardened fixture/import form",
        "The existing hocrgen adapter expects the hardened fixture/import form",
        "does not implement this command on this ref",
        "does not implement the preflight command on this ref",
        "does not change `project_synthetic`",
        "does not change `build-release`, `export-alpha`, `export-synthetic`, or `export-public-beta`",
        "must not call `project_synthetic`, `build-release`, `export-alpha`, `export-synthetic`, or `export-public-beta`",
        "call hocrsyngen CLI commands from default release/export paths",
        "not a request for hocrsyngen to mutate public manifest v1",
        "ask hocrsyngen to add hocrgen-owned release/import metadata fields to `generation_manifest.v1`",
        "`F6f2` should not start until hocrgen has a settled downstream import metadata form",
    ]:
        assert required_boundary in preflight_plan


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


def test_f2_benchmark_ground_truth_references_keep_scope_visible() -> None:
    guidelines = Path("docs/benchmark_ground_truth_guidelines.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")
    combined = "\n".join([guidelines, readme, roadmap])

    for required in [
        "Unicode logical order",
        "Unicode NFC",
        "right-to-left and bidi behavior",
        "niqqud",
        "Hebrew/Arabic/Latin numerals",
        "Latin fragments",
        "abbreviations",
        "uncertain or damaged text",
        "line/page boundaries",
        "page, region, line, and optional word/reference levels",
        "source-image pixel units",
        "release-relative paths",
        "benchmark_reference_manifest.v1",
        "benchmark_transcription_reference.v1",
        "benchmark_layout_reference.v1",
        "public_reference_status",
        "private_adjudication",
        "hidden_reference",
        "F2b implements",
        "benchmark_reference_status.json",
        "benchmark_reference_versioning.json",
        "F1e resolves the separate F1d benchmark/holdout leakage risk",
    ]:
        assert required in combined

    for required_non_goal in [
        "make annotations mandatory",
        "change `benchmark_v1` membership",
        "relax rights, privacy, review, dedupe, split, benchmark, synthetic-cap, or export-portability gates",
    ]:
        assert required_non_goal in guidelines

    for required in [
        "`schema_version`: `benchmark_transcription_reference.v1`",
        "`normalization`: at minimum",
        "`scoring_policy`: explicit include/exclude behavior",
        "`pages`: ordered page records",
        "`lines`: page-local or item-global line records",
        "`spans`: structured annotations anchored by line id and character offsets",
        "Character offsets are counted over the NFC-normalized canonical line text.",
        "`illegible`: exclude the span from primary scoring",
        "`deleted`: exclude from primary OCR/HTR scoring by default",
    ]:
        assert required in guidelines

    for required in [
        "`schema_version`: `benchmark_layout_reference.v1`",
        "`coordinate_system`: pixel units, top-left origin, and axis direction declarations",
        "`assets`: one record per annotated release asset, with release-relative path, checksum, width, height, and page id",
        "`regions`: optional page-local region records",
        "`lines`: line records with stable ids",
        "Bounding boxes use `{ \"x\", \"y\", \"width\", \"height\" }` in pixel units.",
        "referenced asset checksum and dimensions are part of the reference contract",
    ]:
        assert required in guidelines

    for required in [
        "`reference_contracts`: the expected transcription and layout reference schema versions",
        "`transcription_reference`: nullable object with release-relative `path`, `schema_version`, and optional checksum",
        "`layout_label_references`: objects with release-relative `path`, `schema_version`, optional checksum, and declared page ids",
        "\"reference_contracts\"",
        "\"schema_version\": \"benchmark_transcription_reference.v1\"",
        "\"schema_version\": \"benchmark_layout_reference.v1\"",
        "\"page_ids\": [\"page-1\"]",
    ]:
        assert required in guidelines

    for required in [
        "rejects non-portable absolute",
        "checks benchmark item/source/split linkage",
        "verifies layout asset path/checksum/dimension linkage",
        "does not make references mandatory",
        "does not change `benchmark_v1` membership",
    ]:
        assert required in combined
