"""
rigour_heuristics.py - Spec-Draft rigour heuristics lint for audit-sufficiency.

DORMANT BY DESIGN - do not wire this without a PLAN that decides to.

Nothing calls lint_plan(). The only importer is test_rigour_heuristics.py beside
it. That is the state PLAN-AB2 shipped, not an unfinished wiring job. AB2's Q4
chose "plan-writer template change" over a lint in as many words ("Lint is
marginal complexity for a discipline that fits naturally in template"), its Step 4
specified audit-sufficiency Lens 8 as an eye-read prompt, and its Step 5 specified
only a test file. This module exists because that test file needed something to
import - see the PLAN's own Executor Notes for Step 5, which record it being
created as test infrastructure. The sibling module falsifiability.py landed in the
same commit (05a7f42) and WAS wired, into audit-haiku-safe Step 4c, so wiring
happened wherever a PLAN asked for it.

Wiring this later is a behaviour change and costs more than an import. Its RGH001
-RGH003 codes appear in neither auditor-codes register and are not admitted by the
findings[].code pattern in _shared/auditor-schema-v3.md, and its H2 check hard-codes
a 50-tool default rather than reading _shared/capacity-thresholds.md, so it cannot
see the Skill Listing Budget entry the registry also carries. All three would have
to be settled first.

Exposes a single public function:

    lint_plan(plan_text, capacity_thresholds=None) -> list[dict]

Each returned dict is a finding with fields:
    code       str   RGH001 | RGH002 | RGH003
    level      str   "warning"  (all rigour-heuristic findings are warn-severity)
    category   str   "rigour-heuristics"
    location   str   section name or "Steps"
    message    str   human-readable description
    suggested_fix str (optional)

Findings:
  RGH001 - H2 capacity-threshold brushing unacknowledged.
  RGH002 - H4 calling-convention checklist absent.
  RGH003 - H8 literal-heading discipline violation.

Design constraints (per PLAN-AB2):
  - Pure text analysis - no filesystem access, no subprocess.
  - errors='replace' on all file reads (caller's responsibility; this module
    operates on pre-read strings).
  - All findings are warn-severity: heuristics are advisory, not structural gates.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# H2: deliverable-count patterns - matches "N tools", "N MCP tools", etc.
_TOOL_COUNT_RE = re.compile(r'\b(\d+)\s+(?:MCP\s+)?tools?\b', re.IGNORECASE)

# H4: test/API/platform keywords in Steps
_TEST_KEYWORDS_RE = re.compile(
    r'\b(?:pytest|unittest|async\s+def|asyncio|aiohttp|httpx|requests\b|subprocess|'
    r'os\.path|posix|windows|fixture|conftest|mock|patch|monkeypatch)\b',
    re.IGNORECASE,
)

# Convention-enumeration signals in Context (presence means H4 checklist is filled)
_CONVENTION_SIGNALS_RE = re.compile(
    r'\b(?:async(?:io)?|sync(?:hronous)?|fixture|pytest-asyncio|'
    r'calling.?convention|test.?runner|posix|platform.?convention|'
    r'tmp_path|monkeypatch)\b',
    re.IGNORECASE,
)

# H8: ambiguous section-reference prose in Steps
_AMBIGUOUS_SECTION_RE = re.compile(
    r'\b(?:should\s+(?:have|include)\s+a[n]?\s+\w+(?:\s+\w+)?\s+(?:sub-?)?section|'
    r'(?:add|include)\s+a[n]?\s+\w+(?:\s+\w+)?\s+sub-?section)\b',
    re.IGNORECASE,
)

# Default MCP tool count threshold (from capacity-thresholds.md)
_DEFAULT_MCP_TOOL_THRESHOLD = 50
_THRESHOLD_FRACTION = 0.8


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_section(text: str, heading: str) -> str:
    """Return the body of a ## <heading> section, or empty string if absent."""
    pattern = re.compile(
        r'^##\s+' + re.escape(heading) + r'\s*\n(.*?)(?=^##\s|\Z)',
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    return m.group(1) if m else ''


def _make_finding(
    code: str,
    location: str,
    message: str,
    suggested_fix: str = '',
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        'code': code,
        'level': 'warning',
        'category': 'rigour-heuristics',
        'location': location,
        'message': message,
    }
    if suggested_fix:
        finding['suggested_fix'] = suggested_fix
    return finding


# ---------------------------------------------------------------------------
# H2 - Capacity ceiling check
# ---------------------------------------------------------------------------

def _check_h2_capacity(
    plan_text: str,
    capacity_thresholds: dict[str, int] | None,
) -> list[dict]:
    """Emit RGH001 if deliverable count brushes a known threshold without acknowledgement."""
    findings: list[dict] = []

    thresholds = capacity_thresholds if capacity_thresholds is not None else {
        'MCP tool count': _DEFAULT_MCP_TOOL_THRESHOLD,
    }

    steps_text = _extract_section(plan_text, 'Steps')
    context_text = _extract_section(plan_text, 'Context')

    for threshold_name, threshold_value in thresholds.items():
        trigger = threshold_value * _THRESHOLD_FRACTION
        # Look for tool-count mentions in the full plan text
        for m in _TOOL_COUNT_RE.finditer(plan_text):
            count = int(m.group(1))
            if count >= trigger:
                # Check if Context acknowledges it
                ack_pattern = re.compile(
                    r'\b(?:threshold|ceiling|degradation|brushe?s?|approach(?:es|ing)?)\b',
                    re.IGNORECASE,
                )
                if not ack_pattern.search(context_text):
                    findings.append(_make_finding(
                        code='RGH001',
                        location='Context',
                        message=(
                            f"capacity-threshold brushing unacknowledged: deliverable count {count} "
                            f"exceeds 0.8x {threshold_name} threshold of {threshold_value} "
                            f"but Context does not document it."
                        ),
                        suggested_fix=(
                            f"Add a note to the Context section: 'Deliverable count {count} brushes "
                            f"the {threshold_name} ceiling of {threshold_value}. Research bot dispatched "
                            f"to confirm threshold relevance.'"
                        ),
                    ))
                break  # one finding per threshold

    return findings


# ---------------------------------------------------------------------------
# H4 - Calling-convention checklist
# ---------------------------------------------------------------------------

def _check_h4_calling_convention(plan_text: str) -> list[dict]:
    """Emit RGH002 if Steps has test/API keywords but Context lacks convention enumeration."""
    findings: list[dict] = []

    steps_text = _extract_section(plan_text, 'Steps')
    context_text = _extract_section(plan_text, 'Context')

    if not _TEST_KEYWORDS_RE.search(steps_text):
        return findings  # H4 trigger not met

    if not _CONVENTION_SIGNALS_RE.search(context_text):
        findings.append(_make_finding(
            code='RGH002',
            location='Context',
            message=(
                "calling-convention checklist absent: Steps body contains test/API/platform keywords "
                "but Context does not enumerate calling conventions (async/sync posture, fixture "
                "patterns, platform conventions)."
            ),
            suggested_fix=(
                "Add a 'Calling conventions' sub-section to Context enumerating: test-runner async/sync "
                "posture, fixture patterns (e.g. tmp_path vs tmpdir), and any platform-specific notes."
            ),
        ))

    return findings


# ---------------------------------------------------------------------------
# H8 - Literal-heading discipline
# ---------------------------------------------------------------------------

def _check_h8_literal_heading(plan_text: str) -> list[dict]:
    """Emit RGH003 for each ambiguous section reference in Steps."""
    findings: list[dict] = []

    steps_text = _extract_section(plan_text, 'Steps')

    for m in _AMBIGUOUS_SECTION_RE.finditer(steps_text):
        findings.append(_make_finding(
            code='RGH003',
            location='Steps',
            message=(
                f"literal-heading violation: Step body specifies a deliverable section using ambiguous "
                f"prose ('{m.group(0).strip()}'). Use 'MUST include a `## X` heading' syntax instead."
            ),
            suggested_fix=(
                "Replace ambiguous section prose with literal heading syntax: "
                "'The output MUST include a `## Notes` heading.' (substitute the actual section name)."
            ),
        ))

    return findings


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------

def lint_plan(
    plan_text: str,
    capacity_thresholds: dict[str, int] | None = None,
) -> list[dict]:
    """
    Apply the three Spec-Draft rigour heuristics (H2, H4, H8) to a PLAN's text.

    Parameters
    ----------
    plan_text:
        Full text of the PLAN markdown file (pre-read by caller).
    capacity_thresholds:
        Optional override dict mapping threshold name -> int value.
        If None, uses the defaults from capacity-thresholds.md
        (currently: {'MCP tool count': 50}).

    Returns
    -------
    List of finding dicts (may be empty for a conforming plan).
    """
    findings: list[dict] = []
    findings.extend(_check_h2_capacity(plan_text, capacity_thresholds))
    findings.extend(_check_h4_calling_convention(plan_text))
    findings.extend(_check_h8_literal_heading(plan_text))
    return findings
