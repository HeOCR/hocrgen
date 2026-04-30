from __future__ import annotations

from pathlib import Path


CURRENT_COMPLETED_NOTATION = "D3a"
NEXT_NOTATION = "D4a"
PLANNING_FILES = [
    Path(".agent-plan.md"),
    Path("README.md"),
    Path("docs/HeOCR_hocrgen_long_term_roadmap.md"),
    Path("docs/pre_alpha_freeze_plan.md"),
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

    assert f"Last merged roadmap action on the current ref: `{CURRENT_COMPLETED_NOTATION}`" in agent_plan
    assert f"next planned work is `{NEXT_NOTATION}`" in agent_plan
    assert f"| D3 | Expansion and benchmark formation | D3a | Benchmark subset v1 | completed |" in roadmap
    assert f"| D4 | Expansion and benchmark formation | D4a, D4b | Richer synthetic generation, then synthetic diversity/reporting hardening | next |" in roadmap
    assert f"The immediate implementation critical path after `{CURRENT_COMPLETED_NOTATION}` is:" in roadmap
    assert "Roadmap notation is location-based" in readme
    assert "The next planned milestone is `D4a`" in Path("docs/pre_alpha_freeze_plan.md").read_text(encoding="utf-8")


def test_planning_docs_do_not_use_stale_branch_local_status_phrases() -> None:
    for path in PLANNING_FILES:
        text = path.read_text(encoding="utf-8").casefold()
        for phrase in STALE_BRANCH_LOCAL_PHRASES:
            assert phrase not in text, f"{path} contains stale planning phrase: {phrase}"
