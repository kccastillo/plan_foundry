"""
test_rigour_heuristics.py - Tests for the three Spec-Draft rigour heuristics.

Covers:
  Test 1 - H2 capacity-threshold brushing detected (47 tools, no Context ack) -> 1 warn
  Test 2 - H2 capacity-threshold acknowledged (47 tools, Context notes it) -> 0 findings
  Test 3 - H4 calling-convention checklist absent (pytest present, no conventions) -> 1 warn
  Test 4 - H4 calling-convention present (pytest + async/sync noted in Context) -> 0 findings
  Test 5 - H8 literal-heading violation (ambiguous prose) -> 1 warn
  Test 6 - H8 literal-heading conforming (correct MUST syntax) -> 0 findings
"""

import pytest
from rigour_heuristics import lint_plan


# ---------------------------------------------------------------------------
# Helper: build a minimal PLAN text with substitutable sections
# ---------------------------------------------------------------------------

def _make_plan(context: str = "", steps: str = "") -> str:
    lines = [
        "---",
        "schema_version: 2",
        "title: Test PLAN",
        "status: ready",
        "---",
        "",
        "## Objective",
        "",
        "Test plan for rigour heuristics.",
        "",
        "## Context",
        "",
        context,
        "",
        "## Steps",
        "",
        steps,
        "",
        "## Verification",
        "",
        "- [ ] Placeholder",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# H2 - Capacity ceiling (MCP tool count)
# ---------------------------------------------------------------------------

class TestH2CapacityCeiling:

    def test_brushing_detected_no_acknowledgement(self):
        """Test 1: 47 tools (>0.8*50=40), Context silent -> 1 RGH001 warn finding."""
        plan = _make_plan(
            context="This plan delivers a large MCP integration.",
            steps="Implement all 47 tools for the MCP server registration.",
        )
        findings = lint_plan(plan, capacity_thresholds={"MCP tool count": 50})
        rgh001 = [f for f in findings if f["code"] == "RGH001"]
        assert len(rgh001) == 1, f"Expected 1 RGH001 finding, got {len(rgh001)}: {rgh001}"
        assert rgh001[0]["level"] == "warning"
        assert "47" in rgh001[0]["message"]

    def test_brushing_acknowledged_no_finding(self):
        """Test 2: 47 tools, Context acknowledges the threshold -> 0 findings."""
        plan = _make_plan(
            context=(
                "This plan delivers 47 MCP tools. "
                "This brushes the ~50-tool degradation ceiling threshold. "
                "Research bot dispatched to confirm threshold relevance."
            ),
            steps="Implement all 47 tools for the MCP server registration.",
        )
        findings = lint_plan(plan, capacity_thresholds={"MCP tool count": 50})
        rgh001 = [f for f in findings if f["code"] == "RGH001"]
        assert len(rgh001) == 0, f"Expected 0 RGH001 findings, got {len(rgh001)}: {rgh001}"


# ---------------------------------------------------------------------------
# H4 - Calling-convention checklist
# ---------------------------------------------------------------------------

class TestH4CallingConvention:

    def test_checklist_absent_with_pytest_keyword(self):
        """Test 3: Steps mentions pytest, Context has no conventions -> 1 RGH002 warn."""
        plan = _make_plan(
            context="Standard spec with no convention notes.",
            steps="Run pytest to verify the implementation. All tests MUST pass.",
        )
        findings = lint_plan(plan)
        rgh002 = [f for f in findings if f["code"] == "RGH002"]
        assert len(rgh002) == 1, f"Expected 1 RGH002 finding, got {len(rgh002)}: {rgh002}"
        assert rgh002[0]["level"] == "warning"

    def test_checklist_present_no_finding(self):
        """Test 4: Steps mentions pytest, Context enumerates async/sync convention -> 0 findings."""
        plan = _make_plan(
            context=(
                "Calling conventions: all tests are sync (no async). "
                "Use pytest with tmp_path fixture. No asyncio required."
            ),
            steps="Run pytest to verify the implementation. All tests MUST pass.",
        )
        findings = lint_plan(plan)
        rgh002 = [f for f in findings if f["code"] == "RGH002"]
        assert len(rgh002) == 0, f"Expected 0 RGH002 findings, got {len(rgh002)}: {rgh002}"


# ---------------------------------------------------------------------------
# H8 - Literal-heading discipline
# ---------------------------------------------------------------------------

class TestH8LiteralHeading:

    def test_ambiguous_section_prose_detected(self):
        """Test 5: Step says 'should have a Notes section' -> 1 RGH003 warn."""
        plan = _make_plan(
            context="Standard spec.",
            steps=(
                "Write the output document. "
                "The document should have a Notes section with L-tier observations."
            ),
        )
        findings = lint_plan(plan)
        rgh003 = [f for f in findings if f["code"] == "RGH003"]
        assert len(rgh003) == 1, f"Expected 1 RGH003 finding, got {len(rgh003)}: {rgh003}"
        assert rgh003[0]["level"] == "warning"

    def test_literal_heading_syntax_no_finding(self):
        """Test 6: Step uses 'MUST include a `## Notes` heading' -> 0 findings."""
        plan = _make_plan(
            context="Standard spec.",
            steps=(
                "Write the output document. "
                "The output MUST include a `## Notes` heading with L-tier observations."
            ),
        )
        findings = lint_plan(plan)
        rgh003 = [f for f in findings if f["code"] == "RGH003"]
        assert len(rgh003) == 0, f"Expected 0 RGH003 findings, got {len(rgh003)}: {rgh003}"
