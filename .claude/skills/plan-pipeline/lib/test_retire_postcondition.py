"""
Regression test for the retire post-condition check (PLAN-AA2).

The plan-pipeline orchestrator's section 4F retire step must independently verify the
retire skill's success_criteria against the filesystem after the subagent
returns, before committing. This catches the 2026-05-13 class of bug where the
subagent self-reported success but `git rm`'d the file instead of moving it.

These tests are structural - they assert the dispatch.md workflow contains the
required post-condition language. A future change that removes the
post-condition check would fail these assertions.

Bug evidence: commits 84a4425 (PLAN-013), 3b823fc (PLAN-029-sketch-first),
494b2943 (HANDOFF-NEXT-SESSION) - three files git-rm'd instead of moved.
Recovered manually 2026-05-16 + bulk-recovered via
scripts/recover-deleted-retirees.py per PLAN-AA2.
"""

from __future__ import annotations

import pathlib


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / ".claude").is_dir() and (parent / "Workbench").is_dir():
            return parent
    raise RuntimeError("could not find repo root")


REPO_ROOT = _find_repo_root()
DISPATCH = REPO_ROOT / ".claude/skills/plan-pipeline/workflows/dispatch.md"
RETIRE_WORKFLOW = REPO_ROOT / ".claude/skills/retire/workflows/retire-file.md"
RETIRE_SKILL = REPO_ROOT / ".claude/skills/retire/SKILL.md"
PLAN_RETIRER = REPO_ROOT / ".claude/agents/plan-retirer.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_dispatch_4F_has_post_condition_check():
    """plan-pipeline dispatch section 4F must mention post-condition verification."""
    text = _read(DISPATCH)
    # Locate section 4F
    assert "### 4F. `complete`" in text or "4F. complete" in text, "section 4F section missing"
    # The section must reference post-condition verification (any phrasing)
    assert "post-condition" in text.lower() or "post_condition" in text.lower(), (
        "section 4F is missing post-condition language"
    )


def test_dispatch_4F_mentions_orchestrator_independent_verify():
    """The section 4F prose must establish that the orchestrator verifies independently of the subagent."""
    text = _read(DISPATCH)
    # Lowercase to be tolerant of phrasing variations
    lower = text.lower()
    # Required signals: filesystem stat / verify, source-doesnt-exist, destination-exists
    assert "retired/" in lower, "section 4F must reference the Retired/ destination"
    # Either "stat", "exists", or "verify" must appear in the section 4F region near the post-condition keyword
    assert any(keyword in lower for keyword in ("stat the source", "stat the destination", "assert it", "independently verify")), (
        "section 4F must specify independent filesystem verification"
    )


def test_retire_workflow_has_self_verify_step():
    """retire skill workflow must include a Self-verify step (worker self-check half of defense-in-depth)."""
    text = _read(RETIRE_WORKFLOW)
    assert "Self-verify" in text or "Self-verification" in text or "self-verif" in text.lower(), (
        "retire workflow is missing the Self-verify step"
    )


def test_retire_skill_success_criteria_mentions_self_verification():
    """retire SKILL.md success_criteria must reference the self-verification step."""
    text = _read(RETIRE_SKILL)
    # Extract success_criteria block
    assert "<success_criteria>" in text and "</success_criteria>" in text
    block = text.split("<success_criteria>", 1)[1].split("</success_criteria>", 1)[0]
    lower = block.lower()
    assert "self-verif" in lower or "post-condition" in lower or "non-zero size" in lower, (
        "success_criteria is missing self-verification/post-condition language"
    )


def test_plan_retirer_agent_mentions_post_condition_exception():
    """plan-retirer.md exception conditions must include post-condition violation."""
    text = _read(PLAN_RETIRER)
    lower = text.lower()
    assert "post-condition" in lower or "self-verif" in lower, (
        "plan-retirer.md does not document the post-condition exception condition"
    )
