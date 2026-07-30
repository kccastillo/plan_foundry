"""
falsifiability.py - Falsifiability lint for audit-haiku-safe.

Exposes a single public function:

    lint_plan(plan_path) -> list[dict]

Each returned dict is a finding with fields:
    code          str   FAL001
    level         str   "warning"
    category      str   "falsifiability"
    location      str   description of the verify/acceptance line
    message       str   human-readable description
    suggested_fix str   hint for how to write a falsifiable assertion

Findings are emitted when a verify: or acceptance: line in the PLAN's
Verification section contains a pattern that makes the assertion trivially
true - i.e. the condition can never fail regardless of the implementation
state under test.

Vacuous patterns detected (Q1 α blocklist from PLAN-AB5):
    FAL001-a  `or callable(<expr>)`   - callable() is True for any function/class
    FAL001-b  `or True`               - short-circuit always passes
    FAL001-c  `and True`              - identity; adds no constraint
    FAL001-d  `hasattr(<x>, <y>) or <non-eq-expr>`  - hasattr passes; the
              `or` branch is only reached if hasattr returns False, so the
              overall expression collapses to True for any object with the
              attribute (very common false-pass)
    FAL001-e  `any(... True ...)` where True appears as a literal inside
              the any() iterable - forces truthy element, always passes
    FAL001-f  `or x is not None and True` - the `and True` arm is a no-op,
              making the full expression vacuous whenever `or x is not None`
              is True

All findings are warn-severity (not blockers) - an operator may intentionally
write a vacuous pattern for documentation purposes and should have the
opportunity to acknowledge or rewrite it.

Design constraints (per PLAN-AB5):
  - Pure filesystem reads via open() - no subprocess, no shell.
  - errors='replace' on all file reads.
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Vacuous patterns
# ---------------------------------------------------------------------------

# Each entry: (sub_code_suffix, compiled_regex, one-line rationale, suggested_fix)
_VACUOUS_PATTERNS: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        'a',
        re.compile(r'\bor\s+callable\s*\('),
        '`or callable(...)` - callable() is True for any function or class; '
        'the `or` arm makes the whole condition always pass',
        'Remove the `or callable(...)` arm and assert the specific attribute or '
        'interface your code actually requires (e.g. hasattr(obj, "_mcp_tool_name")).',
    ),
    (
        'b',
        re.compile(r'\bor\s+True\b'),
        '`or True` - short-circuits to True unconditionally; '
        'the assertion can never fail',
        'Remove the `or True` term and write the real condition that must hold.',
    ),
    (
        'c',
        re.compile(r'\band\s+True\b'),
        '`and True` - identity operation; adds no constraint and may signal '
        'an incomplete assertion',
        'Remove the `and True` term; it adds nothing to the assertion.',
    ),
    (
        'd',
        re.compile(
            r'\bhasattr\s*\([^)]+\)\s+or\s+(?!\s*\w+\s*==)',
        ),
        '`hasattr(...) or <non-equality-expr>` - when hasattr is True the '
        '`or` branch is never reached; when it is False the assertion still '
        'passes via the `or` branch, making it vacuous',
        'Replace with a direct attribute access assertion, e.g. '
        '`all(hasattr(f, "_mcp_tool_name") for ...)` without the `or` fallback.',
    ),
    (
        'e',
        re.compile(r'\bany\s*\(.*(?:\bTrue\b|\bcallable\s*\().*\)'),
        '`any(... True ...)` or `any(callable(...) ...)` - a literal True or '
        'always-truthy callable() inside any() guarantees the result is always True',
        'Replace with a condition that evaluates each element, '
        'e.g. `any(hasattr(x, "_mcp_tool_name") for x in ...)`.',
    ),
    (
        'f',
        re.compile(r'\bor\s+\w[\w.]*\s+is\s+not\s+None\s+and\s+True\b'),
        '`or <x> is not None and True` - the `and True` is a no-op; '
        'combined with the `or`, this is vacuous whenever `<x> is not None`',
        'Remove the `and True` suffix and the `or` prefix if the intent '
        'is to test a specific condition.',
    ),
]


# Annotation that explicitly acknowledges a vacuous pattern
_WAIVE_ANNOTATION_RE = re.compile(
    r'#\s*falsifiability\s*:\s*waive',
    re.IGNORECASE,
)

# Lines that start a verify/acceptance annotation (in the Verification section)
_VERIFY_LINE_RE = re.compile(r'^\s*(verify|acceptance)\s*:\s*(.+)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_text(path: str) -> str:
    """Read a file with errors='replace' to handle non-UTF-8 bytes."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _extract_verification_section(plan_text: str) -> str:
    """Return the text of the ## Verification section, or empty string if absent."""
    match = re.search(
        r'^##\s+Verification\s*\n(.*?)(?=^##\s|\Z)',
        plan_text,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1)
    return ''


def _extract_verify_lines(verification_text: str) -> list[str]:
    """
    Extract all verify: and acceptance: annotation lines from a Verification section.

    These are the shell-runnable annotations that appear (typically indented
    with backticks) below each prose checkbox. We scan every line for the
    verify:/acceptance: prefix.
    """
    lines = []
    for line in verification_text.splitlines():
        # Strip markdown backtick wrappers and leading whitespace
        stripped = line.strip().lstrip('`').rstrip('`').strip()
        m = _VERIFY_LINE_RE.match(stripped)
        if m:
            lines.append(stripped)
    return lines


def _has_waive_annotation(line: str) -> bool:
    """Return True if the line has a # falsifiability: waive annotation."""
    return bool(_WAIVE_ANNOTATION_RE.search(line))


def _make_finding(
    sub_code: str,
    location: str,
    message: str,
    suggested_fix: str = '',
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        'code': f'FAL001-{sub_code}',
        'level': 'warning',
        'category': 'falsifiability',
        'location': location,
        'message': message,
    }
    if suggested_fix:
        finding['suggested_fix'] = suggested_fix
    return finding


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------

def lint_plan(plan_path: str) -> list[dict]:
    """
    Lint a PLAN file for falsifiability violations in its Verification section.

    Only verify: and acceptance: lines are scanned. Body text elsewhere in the
    PLAN (Steps, Context, etc.) is not examined - falsifiability only applies
    to assertions that are actually run to determine pass/fail.

    Parameters
    ----------
    plan_path:
        Path to the PLAN markdown file.

    Returns
    -------
    List of finding dicts (may be empty for a clean plan). Each finding has:
        code, level, category, location, message, suggested_fix.
    """
    plan_text = _read_text(plan_path)
    verification_text = _extract_verification_section(plan_text)
    verify_lines = _extract_verify_lines(verification_text)

    findings: list[dict] = []

    for line in verify_lines:
        # Skip lines with an explicit waive annotation
        if _has_waive_annotation(line):
            continue

        # Truncate location to 80 chars for readability
        truncated = line if len(line) <= 80 else line[:77] + '...'
        location = f'Verification - {truncated}'

        # Scan for each vacuous pattern
        for sub_code, pattern, rationale, fix in _VACUOUS_PATTERNS:
            if pattern.search(line):
                message = (
                    f'falsifiability-violation: {rationale}. '
                    f'This assertion may always pass regardless of implementation state.'
                )
                findings.append(_make_finding(sub_code, location, message, fix))

    return findings
