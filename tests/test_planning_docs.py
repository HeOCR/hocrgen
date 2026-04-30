from __future__ import annotations

from pathlib import Path


CURRENT_COMPLETED_NOTATION = "E1a"
NEXT_NOTATION = "E2a"
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


def test_planning_docs_agree_on_current_and_next_notation() -> None:
    agent_plan = Path(".agent-plan.md").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")
    roadmap = Path("docs/HeOCR_hocrgen_long_term_roadmap.md").read_text(encoding="utf-8")

    assert f"Last completed roadmap action on the current ref: `{CURRENT_COMPLETED_NOTATION}`" in agent_plan
    assert f"next planned work is `{NEXT_NOTATION}`" in agent_plan
    assert f"| D3 | Expansion and benchmark formation | D3a | Benchmark subset v1 | completed |" in roadmap
    assert f"| D4 | Expansion and benchmark formation | D4a, D4b | Richer synthetic generation, then synthetic diversity/reporting hardening | completed |" in roadmap
    assert f"| D5 | Expansion and benchmark formation | D5a | Optional transcription-ready architecture | completed |" in roadmap
    assert f"| E1 | Ecosystem maturity | E1a | Community contribution model | completed |" in roadmap
    assert f"The immediate implementation critical path after `{CURRENT_COMPLETED_NOTATION}` is:" in roadmap
    assert "Roadmap notation is location-based" in readme
    assert "The next planned milestone is `E2a`" in Path("docs/pre_alpha_freeze_plan.md").read_text(encoding="utf-8")


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
