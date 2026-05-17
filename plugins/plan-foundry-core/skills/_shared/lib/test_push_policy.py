"""
test_push_policy.py — Unit tests for _shared/push_policy.py.

Covers all six resolution scenarios documented in PLAN-AB1 Step 6:

  1. PLAN frontmatter has push_policy=auto  → returns "auto".
  2. PLAN has no push_policy; marketplace.json has auto → returns "auto".
  3. Neither has push_policy → returns "manual" (hard-coded default).
  4. PLAN has manual, marketplace has auto → returns "manual" (PLAN wins).
  5. Invalid value (e.g. "yolo") in PLAN → warns to stderr, returns "manual".
  6. Missing marketplace.json → returns "manual".

Run: python -m pytest plugins/plan-foundry-core/skills/_shared/lib/test_push_policy.py
     or: python test_push_policy.py
"""

from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import textwrap

# Add _shared/ to the path so we can import push_policy directly.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import push_policy  # noqa: E402  (intentional path manipulation above)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(tmp_dir: pathlib.Path, slug: str, extra_frontmatter: str = "") -> pathlib.Path:
    """Write a minimal PLAN markdown file with optional extra frontmatter lines."""
    base_lines = [
        "---",
        "schema_version: 2",
        'title: "Test PLAN"',
        "type: plan",
        "status: ready",
    ]
    extra_lines = extra_frontmatter.splitlines() if extra_frontmatter else []
    closing = ["---", "", "## Objective", "", "Smoke test."]

    content = "\n".join(base_lines + extra_lines + closing) + "\n"
    p = tmp_dir / f"{slug}.md"
    p.write_text(content, encoding="utf-8")
    return p


def _make_marketplace(tmp_dir: pathlib.Path, push_policy_value=None) -> pathlib.Path:
    """Write a .claude-plugin/marketplace.json under tmp_dir.
    If push_policy_value is None, the field is omitted.
    """
    plugin_dir = tmp_dir / ".claude-plugin"
    plugin_dir.mkdir(exist_ok=True)
    data = {"name": "plan-foundry", "version": "0.1.0"}
    if push_policy_value is not None:
        data["push_policy"] = push_policy_value
    mp_path = plugin_dir / "marketplace.json"
    mp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return tmp_dir  # return the repo root (tmp_dir contains .claude-plugin/)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_plan_frontmatter_auto_wins():
    """Test 1: PLAN frontmatter push_policy=auto → returns 'auto'."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        repo_root = _make_marketplace(tmp, push_policy_value="manual")
        plan = _make_plan(tmp, "PLAN-T1", extra_frontmatter="push_policy: auto")
        result = push_policy.get_push_policy(str(plan), repo_root=repo_root)
    assert result == "auto", f"Expected 'auto', got {result!r}"


def test_marketplace_fallback_auto():
    """Test 2: PLAN has no push_policy; marketplace.json has auto → returns 'auto'."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        repo_root = _make_marketplace(tmp, push_policy_value="auto")
        plan = _make_plan(tmp, "PLAN-T2")  # no push_policy field
        result = push_policy.get_push_policy(str(plan), repo_root=repo_root)
    assert result == "auto", f"Expected 'auto', got {result!r}"


def test_default_manual_when_no_config():
    """Test 3: Neither PLAN nor marketplace.json has push_policy → returns 'manual'."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        repo_root = _make_marketplace(tmp)  # no push_policy in marketplace
        plan = _make_plan(tmp, "PLAN-T3")   # no push_policy in plan
        result = push_policy.get_push_policy(str(plan), repo_root=repo_root)
    assert result == "manual", f"Expected 'manual', got {result!r}"


def test_plan_manual_overrides_marketplace_auto():
    """Test 4: PLAN has manual, marketplace has auto → PLAN wins, returns 'manual'."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        repo_root = _make_marketplace(tmp, push_policy_value="auto")
        plan = _make_plan(tmp, "PLAN-T4", extra_frontmatter="push_policy: manual")
        result = push_policy.get_push_policy(str(plan), repo_root=repo_root)
    assert result == "manual", f"Expected 'manual', got {result!r}"


def test_invalid_plan_value_warns_and_falls_through():
    """Test 5: Invalid value in PLAN frontmatter → warns to stderr, returns 'manual'."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        repo_root = _make_marketplace(tmp)  # no push_policy in marketplace either
        plan = _make_plan(tmp, "PLAN-T5", extra_frontmatter="push_policy: yolo")

        stderr_capture = io.StringIO()
        orig_stderr = sys.stderr
        sys.stderr = stderr_capture
        try:
            result = push_policy.get_push_policy(str(plan), repo_root=repo_root)
        finally:
            sys.stderr = orig_stderr

    warning_text = stderr_capture.getvalue()
    assert result == "manual", f"Expected 'manual', got {result!r}"
    assert "yolo" in warning_text, (
        f"Expected warning mentioning 'yolo' in stderr, got: {warning_text!r}"
    )
    assert "WARNING" in warning_text.upper() or "warning" in warning_text.lower(), (
        f"Expected a warning in stderr, got: {warning_text!r}"
    )


def test_missing_marketplace_json_returns_manual():
    """Test 6: Missing marketplace.json (consumer without prod-repo config) → returns 'manual'."""
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        # Do NOT create .claude-plugin/marketplace.json
        plan = _make_plan(tmp, "PLAN-T6")  # no push_policy in plan
        # repo_root supplied explicitly so _resolve_repo_root does not walk up to
        # the real repo root (which has a marketplace.json).
        result = push_policy.get_push_policy(str(plan), repo_root=tmp)
    assert result == "manual", f"Expected 'manual', got {result!r}"


# ---------------------------------------------------------------------------
# Script entry-point (for direct execution without pytest)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        test_plan_frontmatter_auto_wins,
        test_marketplace_fallback_auto,
        test_default_manual_when_no_config,
        test_plan_manual_overrides_marketplace_auto,
        test_invalid_plan_value_warns_and_falls_through,
        test_missing_marketplace_json_returns_manual,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"  FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed.")
    sys.exit(0 if failed == 0 else 1)
