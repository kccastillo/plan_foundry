"""
test_model_budget.py - guard the recalibrated pipeline-agent model budget
(2026-07-04). Asserts each .claude/agents/*.md `model:` pin matches the doctrine
so a future accidental re-tier (e.g. reverting the executor to Haiku, or dropping
plan-writer off Opus) is caught in CI.

Recalibration doctrine:
  - plan-writer          -> opus   (authoring is load-bearing; dispatched at high effort)
  - plan-executor        -> sonnet (execution floor is Sonnet; Haiku retired from execution)
  - plan-executor-sonnet -> sonnet
  - plan-executor-opus   -> opus
  - sufficiency-auditor  -> opus   (highest-judgement gate)
  - plan-safety-auditor  -> sonnet (mechanical; Sonnet 5 ample)
  - plan-retirer         -> haiku  (pure file-move)
  - survey-researcher    -> sonnet (light-judgement prior-art)

Run: python .claude/skills/plan-pipeline/lib/test_model_budget.py
"""

from __future__ import annotations

import pathlib
import re
import sys


def _repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / ".claude").is_dir() and (candidate / "Workbench").is_dir():
            return candidate
    return here.parents[4]


_AGENTS = _repo_root() / ".claude" / "agents"

EXPECTED = {
    "plan-writer": "opus",
    "plan-executor": "sonnet",
    "plan-executor-sonnet": "sonnet",
    "plan-executor-opus": "opus",
    "sufficiency-auditor": "opus",
    "plan-safety-auditor": "sonnet",
    "plan-retirer": "haiku",
    "survey-researcher": "sonnet",
}

_MODEL_RE = re.compile(r"^model:\s*(\S+)\s*$", re.MULTILINE)


def _model_of(agent: str) -> str | None:
    path = _AGENTS / f"{agent}.md"
    if not path.is_file():
        return None
    m = _MODEL_RE.search(path.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def test_agent_model_pins_match_recalibrated_budget():
    """Every named agent carries the recalibrated model tier."""
    bad = []
    for agent, expected in EXPECTED.items():
        actual = _model_of(agent)
        if actual != expected:
            bad.append(f"{agent}: expected model={expected!r}, got {actual!r}")
    assert not bad, "model-budget drift:\n  " + "\n  ".join(bad)


def test_default_executor_is_not_haiku():
    """The load-bearing recalibration: the default executor is Sonnet, not Haiku."""
    assert _model_of("plan-executor") == "sonnet", (
        "plan-executor default tier must be Sonnet (Haiku is retired as an execution tier)"
    )


def test_plan_writer_dispatch_sets_high_effort():
    """plan-writer's Opus pin is paired with a high-effort dispatch directive."""
    psm = (_repo_root() / ".claude/skills/plan-pipeline/references/phase-state-machine.md").read_text(encoding="utf-8")
    assert 'effort: "high"' in psm, (
        "phase-state-machine plan-writer dispatch snippet must pass effort: \"high\""
    )


_TESTS = [
    test_agent_model_pins_match_recalibrated_budget,
    test_default_executor_is_not_haiku,
    test_plan_writer_dispatch_sets_high_effort,
]


if __name__ == "__main__":
    failures = 0
    for t in _TESTS:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failures += 1
    sys.exit(0 if failures == 0 else 1)
