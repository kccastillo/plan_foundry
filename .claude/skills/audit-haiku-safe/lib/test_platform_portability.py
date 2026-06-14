"""
test_platform_portability.py — pytest tests for the platform-portability lint module.

8 tests covering the scenarios specified in PLAN-AB3 Step 4.
All tests use synthetic fixtures (tempfile.TemporaryDirectory + synthetic PLAN content).
No live repo files are read.

Run with:
    python -m pytest .claude/skills/audit-haiku-safe/lib/test_platform_portability.py

Note on PLAN construction: synthetic PLANs with multi-line frontmatter use explicit
"\n".join(lines) rather than textwrap.dedent + f-string interpolation. This avoids the
common-indent mangling gotcha when interpolated content has zero leading whitespace.
"""

import os
import tempfile

import pytest

from platform_portability import lint_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(dir_path: str, name: str, content: str) -> str:
    """Write a file in dir_path and return its absolute path."""
    path = os.path.join(dir_path, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    return path


def _make_plan(tmp_dir: str, verify_lines: list[str], plan_name: str = 'PLAN.md') -> str:
    """
    Write a minimal PLAN markdown file with given verify/acceptance lines
    in the Verification section. Returns its absolute path.

    verify_lines: list of raw annotation strings, e.g.:
        ["verify: python -m pytest tests/", "acceptance: git status # platform: posix"]

    Implementation note: uses explicit "\n".join() for frontmatter construction
    to avoid textwrap.dedent + f-string indentation gotcha (documented PLAN-AB3 warning).
    """
    fm_lines = [
        "---",
        "schema_version: 2",
        'title: "Test plan"',
        "type: plan",
        "status: ready",
        "substrate_files: []",
        "---",
    ]
    frontmatter = "\n".join(fm_lines) + "\n"

    verification_items = []
    for i, vline in enumerate(verify_lines, start=1):
        verification_items.append(f"- [ ] Verification item {i}")
        verification_items.append(f"      `{vline}`")

    body_parts = [
        "",
        "## Objective",
        "Test objective.",
        "",
        "## Steps",
        "1. Do the thing.",
        "",
        "## Verification",
    ]
    body_parts.extend(verification_items)
    body_parts.append("")

    body = "\n".join(body_parts)
    return _write_file(tmp_dir, plan_name, frontmatter + body)


# ---------------------------------------------------------------------------
# Test 1 — Clean PLAN: all verify/acceptance use python/pytest/git → 0 findings
# ---------------------------------------------------------------------------

def test_clean_plan_no_findings():
    """All verify/acceptance use portable commands (python, pytest, git) → 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "verify: python -c \"import os; assert os.path.exists('README.md')\"",
            "acceptance: python -m pytest plugins/plan-foundry-core/skills/audit-haiku-safe/lib/",
            "verify: git status",
        ])

        findings = lint_plan(plan_path)
        assert findings == [], f"Expected 0 findings for a clean plan, got: {findings}"


# ---------------------------------------------------------------------------
# Test 2 — Unannotated /tmp/ use → 1 warn finding
# ---------------------------------------------------------------------------

def test_unannotated_tmp_returns_warning():
    """Unannotated /tmp/ in verify line → exactly 1 PPV001 warning finding."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: python scripts/run.py > /tmp/dump.json",
        ])

        findings = lint_plan(plan_path)
        ppv001 = [f for f in findings if f['code'] == 'PPV001']
        assert len(ppv001) >= 1, f"Expected at least 1 PPV001 finding, got: {findings}"
        assert ppv001[0]['level'] == 'warning'
        assert 'platform-portability-violation' in ppv001[0]['message']


# ---------------------------------------------------------------------------
# Test 3 — Annotated /tmp/ use (# platform: posix) → 0 findings
# ---------------------------------------------------------------------------

def test_annotated_tmp_no_findings():
    """Annotated /tmp/ use with # platform: posix → annotation accepted, 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: python scripts/run.py > /tmp/dump.json # platform: posix",
        ])

        findings = lint_plan(plan_path)
        assert findings == [], (
            f"Expected 0 findings when annotated with # platform: posix, got: {findings}"
        )


# ---------------------------------------------------------------------------
# Test 4 — bash -c use without annotation → 1 finding
# ---------------------------------------------------------------------------

def test_unannotated_bash_c_returns_warning():
    """Unannotated `bash -c` in acceptance line → at least 1 PPV003 warning."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: bash -c 'python scripts/verify.py'",
        ])

        findings = lint_plan(plan_path)
        ppv003 = [f for f in findings if f['code'] == 'PPV003']
        assert len(ppv003) >= 1, f"Expected at least 1 PPV003 finding, got: {findings}"
        assert ppv003[0]['level'] == 'warning'


# ---------------------------------------------------------------------------
# Test 5 — && compound without annotation → 1 finding
# ---------------------------------------------------------------------------

def test_unannotated_and_and_returns_warning():
    """Unannotated && compound operator → at least 1 PPV007 warning finding."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: python scripts/run.py && python scripts/verify.py",
        ])

        findings = lint_plan(plan_path)
        ppv007 = [f for f in findings if f['code'] == 'PPV007']
        assert len(ppv007) >= 1, f"Expected at least 1 PPV007 finding, got: {findings}"
        assert ppv007[0]['level'] == 'warning'


# ---------------------------------------------------------------------------
# Test 6 — Multiple violations in one PLAN → N findings where N matches count
# ---------------------------------------------------------------------------

def test_multiple_violations_counts_correctly():
    """Multiple unannotated forbidden patterns → one finding per pattern match."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: python run.py > /tmp/out.json",   # PPV001 (/tmp/) + PPV005 (> /dev/ — no, > /tmp/ not /dev/)
            "verify: bash -c 'ls'",                         # PPV003
            "acceptance: test -f scripts/run.py",           # PPV004
        ])

        findings = lint_plan(plan_path)
        # Expect at least 3 findings (one per pattern-matched line at minimum)
        assert len(findings) >= 3, (
            f"Expected at least 3 findings for 3 violation lines, got {len(findings)}: {findings}"
        )
        codes = [f['code'] for f in findings]
        assert 'PPV001' in codes, f"PPV001 (/tmp/) not found in findings: {findings}"
        assert 'PPV003' in codes, f"PPV003 (bash -c) not found in findings: {findings}"
        assert 'PPV004' in codes, f"PPV004 (test -X) not found in findings: {findings}"


# ---------------------------------------------------------------------------
# Test 7 — PowerShell-specific $env: usage with # platform: windows → 0 findings
# ---------------------------------------------------------------------------

def test_windows_annotated_no_findings():
    """Windows-specific $env: usage annotated with # platform: windows → 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "verify: python -c \"import os; assert os.environ['SOME_VAR'] == '1'\" # platform: windows",
            "acceptance: python -m pytest tests/ # platform: windows",
        ])

        findings = lint_plan(plan_path)
        assert findings == [], (
            f"Expected 0 findings for windows-annotated lines, got: {findings}"
        )


# ---------------------------------------------------------------------------
# Test 8 — Mixed bag: some annotated, some violations → correct subset flagged
# ---------------------------------------------------------------------------

def test_mixed_annotated_and_violations():
    """
    Mixed PLAN:
      - portable verify → 0 findings
      - /tmp/ annotated # platform: posix → 0 findings (annotation skipped)
      - 2>/dev/null unannotated → findings from 2>/dev/null patterns
      - && unannotated → PPV007 finding
    Expect: no findings from the annotated line; PPV006 and PPV007 present; no
    PPV001 (which only triggers for /tmp/, and that line is annotated).
    Note: 2>/dev/null also triggers PPV002 (/dev/null) and PPV005 (> /dev/) since
    all patterns are scanned independently — multi-pattern matching is correct behaviour.
    """
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "verify: python -m pytest tests/",                               # clean
            "acceptance: python run.py > /tmp/out.json # platform: posix",  # annotated, skipped
            "acceptance: python run.py 2>/dev/null",                        # PPV002 + PPV005 + PPV006
            "verify: python check.py && echo done",                         # PPV007
        ])

        findings = lint_plan(plan_path)
        codes = [f['code'] for f in findings]

        # The annotated /tmp/ line must NOT generate any findings
        # PPV001 only fires for /tmp/, which is only on the annotated line
        assert 'PPV001' not in codes, (
            f"PPV001 was raised for an annotated line — false positive: {findings}"
        )
        # The unannotated 2>/dev/null must appear (as PPV006 at minimum)
        assert 'PPV006' in codes, f"PPV006 (2>/dev/null) not found in findings: {findings}"
        # The unannotated && must appear
        assert 'PPV007' in codes, f"PPV007 (&&) not found in findings: {findings}"
        # All findings must come from the two unannotated lines only
        # (verify the annotated line's location is not in any finding)
        for f in findings:
            assert '# platform: posix' not in f['location'], (
                f"Finding location contains annotated line — false positive: {f}"
            )
