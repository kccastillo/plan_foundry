"""
Regression test for executor-return validation (Reeve hiccup H10).

The plan-pipeline orchestrator's section 4D `executing` re-entry step must validate
the executor's return contains a well-formed `<pipeline-result>` block before
treating `last_executor_outcome` as authoritative. This catches the class of
bug where the Claude Code task harness flags an invocation as `completed`
because it returned a terminal response - but the terminal response was a
rate-limit rejection rather than a real execution.

Structural test - asserts the dispatch.md workflow contains the required
validation language. Future change that removes the H10 protection would
fail this test.

Bug evidence: Reeve Plan C executor dispatch 2026-05-16 returned
`<status>completed</status>` with result text "You've hit your limit *
resets at 12:50am". 16 tokens used. No code written. Documented in
Workbench/202605160300_RESEARCH_hiccup-log.md section H10.
"""

from __future__ import annotations

import pathlib


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if (parent / ".claude" / "skills").is_dir():
            return parent
    raise RuntimeError("could not find repo root")


REPO_ROOT = _find_repo_root()
DISPATCH = REPO_ROOT / ".claude/skills/plan-pipeline/workflows/dispatch.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def test_dispatch_4D_has_executor_return_validation():
    """section 4D must mention executor-return validation as a pre-step."""
    text = _read(DISPATCH)
    assert "### 4D. `executing`" in text, "section 4D section missing"
    # Section content from section 4D to next "### "
    section = text.split("### 4D. `executing`", 1)[1].split("\n### ", 1)[0]
    lower = section.lower()
    assert "executor-return validation" in lower or "executor return validation" in lower, (
        "section 4D is missing executor-return validation step"
    )


def test_dispatch_4D_mentions_pipeline_result_block_check():
    """section 4D validation must specifically check for the <pipeline-result> block."""
    text = _read(DISPATCH)
    section = text.split("### 4D. `executing`", 1)[1].split("\n### ", 1)[0]
    assert "<pipeline-result>" in section, (
        "section 4D must reference the <pipeline-result> block as the validation target"
    )


def test_dispatch_4D_mentions_rate_limit_case():
    """section 4D must explicitly cover the rate-limit / empty / malformed case."""
    text = _read(DISPATCH)
    section = text.split("### 4D. `executing`", 1)[1].split("\n### ", 1)[0]
    lower = section.lower()
    # At least one of: "rate-limit", "rate limit", "hit your limit", "malformed", "empty"
    keywords = ["rate-limit", "rate limit", "hit your limit", "malformed", "empty"]
    assert any(kw in lower for kw in keywords), (
        "section 4D must enumerate at least one specific malformed-return case (rate-limit, empty, malformed)"
    )


def test_dispatch_4D_treats_malformed_as_exception():
    """section 4D must route a malformed return to outcome:exception, not progress to outcome-verifying."""
    text = _read(DISPATCH)
    section = text.split("### 4D. `executing`", 1)[1].split("\n### ", 1)[0]
    lower = section.lower()
    # Both `outcome: exception` and kanban-halt / WIP-commit pattern must appear
    assert "outcome: exception" in lower or "outcome:exception" in lower, (
        "section 4D malformed-return path must produce outcome:exception"
    )
    assert "kanban halt" in lower or "halt" in lower, (
        "section 4D malformed-return path must halt the pipeline"
    )
