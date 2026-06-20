"""
test_push_policy.py — Unit tests for get_push_policy().

Resolution order under test (PLAN-AC4 D6 post-state):
  1. PLAN frontmatter push_policy=auto  → returns "auto" (per-PLAN override wins).
  2. PLAN frontmatter push_policy=manual → returns "manual" (per-PLAN override wins).
  3. PLAN has no push_policy frontmatter  → returns "manual" (hard-coded default).
  4. PLAN frontmatter push_policy=invalid → warning + returns "manual" (default fallback).
  5. PLAN file unreadable / nonexistent  → returns "manual" (default fallback).

Run: python -m pytest .claude/skills/_shared/lib/test_push_policy.py
"""

import pathlib
import sys
import tempfile

# Make the module importable when running directly
_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from push_policy import get_push_policy  # noqa: E402


def _make_plan(tmp_dir: pathlib.Path, push_policy_value=None) -> pathlib.Path:
    """Write a minimal PLAN frontmatter file under tmp_dir.

    If push_policy_value is None, no push_policy field is written.
    Returns the PLAN file path.
    """
    plan_path = tmp_dir / "test-plan.md"
    lines = ["---", "schema_version: 2", "title: test"]
    if push_policy_value is not None:
        lines.append(f"push_policy: {push_policy_value}")
    lines.append("---")
    lines.append("")
    lines.append("# Test PLAN body")
    plan_path.write_text("\n".join(lines), encoding="utf-8")
    return plan_path


def test_plan_override_auto():
    """1: PLAN has push_policy=auto → returns 'auto'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        plan_path = _make_plan(tmp_path, push_policy_value="auto")
        result = get_push_policy(str(plan_path), repo_root=tmp_path)
        assert result == "auto", f"expected 'auto', got {result!r}"


def test_plan_override_manual():
    """2: PLAN has push_policy=manual → returns 'manual'."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        plan_path = _make_plan(tmp_path, push_policy_value="manual")
        result = get_push_policy(str(plan_path), repo_root=tmp_path)
        assert result == "manual", f"expected 'manual', got {result!r}"


def test_no_frontmatter_field_returns_default():
    """3: PLAN has no push_policy field → returns 'manual' (default)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        plan_path = _make_plan(tmp_path, push_policy_value=None)
        result = get_push_policy(str(plan_path), repo_root=tmp_path)
        assert result == "manual", f"expected 'manual', got {result!r}"


def test_invalid_frontmatter_value_returns_default():
    """4: PLAN has push_policy=bogus → warning + returns 'manual' (default)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        plan_path = _make_plan(tmp_path, push_policy_value="bogus")
        result = get_push_policy(str(plan_path), repo_root=tmp_path)
        assert result == "manual", f"expected 'manual' (invalid override falls through), got {result!r}"


def test_nonexistent_plan_returns_default():
    """5: PLAN file does not exist → returns 'manual' (default)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        plan_path = tmp_path / "no-such-plan.md"
        result = get_push_policy(str(plan_path), repo_root=tmp_path)
        assert result == "manual", f"expected 'manual', got {result!r}"


if __name__ == "__main__":
    tests = [
        test_plan_override_auto,
        test_plan_override_manual,
        test_no_frontmatter_field_returns_default,
        test_invalid_frontmatter_value_returns_default,
        test_nonexistent_plan_returns_default,
    ]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failures += 1
    sys.exit(0 if failures == 0 else 1)
