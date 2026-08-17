"""
test_falsifiability.py - pytest tests for the falsifiability lint module.

Covers the scenarios specified in PLAN-AB5 Step 5.
All tests use synthetic fixtures (tempfile.TemporaryDirectory + synthetic PLAN
content). No live repo files are read.

Run with:
    python -m pytest .claude/skills/audit-haiku-safe/lib/test_falsifiability.py

Note on PLAN construction: synthetic PLANs with multi-line frontmatter use
explicit "\n".join(lines) rather than textwrap.dedent + f-string interpolation.
This avoids the common-indent mangling gotcha when interpolated content has
zero leading whitespace (documented in PLAN-AB3 test helper warning, inherited
here per PLAN-AB5).
"""

import os
import tempfile

import pytest

from falsifiability import lint_plan


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
        ["verify: python -m pytest tests/",
         "acceptance: all(hasattr(f, 'x') or callable(f) for f in items)"]

    Implementation note: uses explicit "\n".join() for frontmatter construction
    to avoid textwrap.dedent + f-string indentation gotcha.
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


def _make_plan_with_steps_body(tmp_dir: str, steps_body: str, verify_lines: list[str],
                                plan_name: str = 'PLAN.md') -> str:
    """
    Write a minimal PLAN with custom Steps body and verify lines.
    Used for Test 7 (non-Verification body text must not be flagged).
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
        steps_body,
        "",
        "## Verification",
    ]
    body_parts.extend(verification_items)
    body_parts.append("")

    body = "\n".join(body_parts)
    return _write_file(tmp_dir, plan_name, frontmatter + body)


# ---------------------------------------------------------------------------
# Test 1 - Clean PLAN with no vacuous patterns: 0 findings
# ---------------------------------------------------------------------------

def test_clean_plan_no_findings():
    """Clean verify/acceptance lines with real conditions -> 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "verify: python -c \"import os; assert os.path.exists('plugins/')\"",
            "acceptance: python -m pytest plugins/plan-foundry-core/skills/audit-haiku-safe/lib/",
            "acceptance: all(hasattr(f, '_mcp_tool_name') for n,f in inspect.getmembers(state) if not n.startswith('_'))",
        ])

        findings = lint_plan(plan_path)
        assert findings == [], f"Expected 0 findings for a clean plan, got: {findings}"


# ---------------------------------------------------------------------------
# Test 2 - `or callable(f)` pattern: 1 finding
# ---------------------------------------------------------------------------

def test_or_callable_returns_warning():
    """`or callable(f)` in acceptance line -> at least 1 FAL001-a finding."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: all(hasattr(f, '_mcp_tool_name') or callable(f) for n,f in inspect.getmembers(state) if not n.startswith('_'))",
        ])

        findings = lint_plan(plan_path)
        fal_a = [f for f in findings if f['code'] == 'FAL001-a']
        assert len(fal_a) >= 1, f"Expected at least 1 FAL001-a finding, got: {findings}"
        assert fal_a[0]['level'] == 'warning'
        assert 'falsifiability-violation' in fal_a[0]['message']
        assert fal_a[0]['category'] == 'falsifiability'


# ---------------------------------------------------------------------------
# Test 3 - `or True` pattern: 1 finding
# ---------------------------------------------------------------------------

def test_or_true_returns_warning():
    """`or True` in verify line -> at least 1 FAL001-b finding."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "verify: python -c \"assert len(result) > 0 or True\"",
        ])

        findings = lint_plan(plan_path)
        fal_b = [f for f in findings if f['code'] == 'FAL001-b']
        assert len(fal_b) >= 1, f"Expected at least 1 FAL001-b finding, got: {findings}"
        assert fal_b[0]['level'] == 'warning'


# ---------------------------------------------------------------------------
# Test 4 - `hasattr(x, 'y') or z` (not eq check): 1 finding
# ---------------------------------------------------------------------------

def test_hasattr_or_non_eq_returns_warning():
    """`hasattr(x, 'y') or some_var` (no equality check) -> at least 1 FAL001-d finding."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: all(hasattr(obj, 'name') or default_val for obj in items)",
        ])

        findings = lint_plan(plan_path)
        fal_d = [f for f in findings if f['code'] == 'FAL001-d']
        assert len(fal_d) >= 1, f"Expected at least 1 FAL001-d finding, got: {findings}"
        assert fal_d[0]['level'] == 'warning'


# ---------------------------------------------------------------------------
# Test 5 - Legitimate `or None` for absent check: 0 findings
# ---------------------------------------------------------------------------

def test_or_none_not_flagged():
    """`or None` is not a vacuous pattern -- should produce 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: python -c \"result = get_value() or None; assert result is not None\"",
            "verify: python -c \"val = config.get('key') or None; assert val\"",
        ])

        findings = lint_plan(plan_path)
        assert findings == [], (
            f"Expected 0 findings for legitimate `or None` usage, got: {findings}"
        )


# ---------------------------------------------------------------------------
# Test 6 - Multiple vacuous patterns in one PLAN: N findings
# ---------------------------------------------------------------------------

def test_multiple_patterns_returns_multiple_findings():
    """Multiple vacuous patterns across multiple verify/acceptance lines -> N findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: all(hasattr(f, 'x') or callable(f) for f in items)",  # FAL001-a
            "verify: python -c \"assert x > 0 or True\"",                        # FAL001-b
            "acceptance: any(True for x in result)",                              # FAL001-e
        ])

        findings = lint_plan(plan_path)
        assert len(findings) >= 2, (
            f"Expected at least 2 findings for multiple vacuous patterns, got {len(findings)}: {findings}"
        )
        codes = [f['code'] for f in findings]
        assert 'FAL001-a' in codes, f"FAL001-a (or callable) not found in findings: {findings}"
        assert 'FAL001-b' in codes, f"FAL001-b (or True) not found in findings: {findings}"


# ---------------------------------------------------------------------------
# Test 7 - Patterns inside non-Verification body text are NOT flagged
# ---------------------------------------------------------------------------

def test_vacuous_patterns_in_steps_not_flagged():
    """
    `or callable(f)` and `or True` appearing in the ## Steps body must NOT be
    flagged -- only verify: and acceptance: lines in ## Verification are scanned.
    """
    with tempfile.TemporaryDirectory() as tmp:
        steps_body = "\n".join([
            "1. For each function, check `hasattr(f, '_mcp_tool_name') or callable(f)`.",
            "2. Assert condition or True to see how the harness handles vacuous passes.",
            "3. Use `any(x or True for x in items)` pattern for demonstration.",
        ])
        plan_path = _make_plan_with_steps_body(
            tmp,
            steps_body=steps_body,
            verify_lines=[
                "verify: python -m pytest tests/",  # clean -- no vacuous pattern
            ],
        )

        findings = lint_plan(plan_path)
        assert findings == [], (
            f"Expected 0 findings -- vacuous patterns in Steps must not be flagged, "
            f"got: {findings}"
        )


# ---------------------------------------------------------------------------
# Test 8 - `any(callable(x) for x in ...)` vacuous via any: 1 finding
# ---------------------------------------------------------------------------

def test_any_with_callable_returns_warning():
    """`any(callable(x) for x in items)` -- callable is always True, vacuous via any."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(tmp, [
            "acceptance: python -c \"assert any(callable(x) for x in registered_tools)\"",
        ])

        findings = lint_plan(plan_path)
        # FAL001-e covers `any(... callable( ...)` as well as `any(... True ...)`.
        # callable() is always True for any function/class, so any() is vacuously True.
        fal_e = [f for f in findings if f['code'] == 'FAL001-e']
        assert len(fal_e) >= 1, (
            f"Expected at least 1 FAL001-e finding for `any(callable(x) for x in ...)`, "
            f"got: {findings}"
        )
        assert fal_e[0]['level'] == 'warning'
        assert fal_e[0]['category'] == 'falsifiability'
