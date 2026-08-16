#!/usr/bin/env python3
"""
test_hooks_path.py - tests for the core.hooksPath wiring helper (PLAN-AD2 D10).

The properties that matter: it wires a fresh repo, it is idempotent across
repeated syncs, it never overwrites a consumer's own hooks path, and it is a
no-op outside a git repo rather than an error.
"""

import importlib.util
import pathlib
import subprocess
import sys
import tempfile

SHARED = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("hooks_path", SHARED / "hooks_path.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ensure_hooks_path = _mod.ensure_hooks_path
check_hooks_path = _mod.check_hooks_path
HOOKS_PATH_VALUE = _mod.HOOKS_PATH_VALUE


def _init_repo(root: pathlib.Path) -> None:
    subprocess.run(
        ["git", "init", "-q"], cwd=str(root), capture_output=True, check=True
    )


def test_wires_a_fresh_repo():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        assert check_hooks_path(root) == ""

        status, note = ensure_hooks_path(root)
        assert status == "PASS", (status, note)
        assert check_hooks_path(root) == HOOKS_PATH_VALUE


def test_idempotent():
    """Repeated syncs must not churn the config or report a change."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        ensure_hooks_path(root)

        status, note = ensure_hooks_path(root)
        assert status == "SKIPPED", (status, note)
        assert check_hooks_path(root) == HOOKS_PATH_VALUE


def test_never_clobbers_a_consumer_value():
    """
    A consumer with their own hooks path keeps it, and the conflict is reported.

    Silently redirecting a repo's hooks would be a worse failure than declining
    to wire ours - their hooks may be enforcing something we know nothing about.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        subprocess.run(
            ["git", "config", "--local", "core.hooksPath", ".githooks"],
            cwd=str(root),
            capture_output=True,
            check=True,
        )

        status, note = ensure_hooks_path(root)
        assert status == "FAIL", (status, note)
        assert ".githooks" in note, note
        assert check_hooks_path(root) == ".githooks", "consumer value must survive"


def test_non_git_directory_is_a_skip_not_an_error():
    """An installer running outside a git repo must not crash."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp) / "plain"
        root.mkdir()
        status, note = ensure_hooks_path(root)
        assert status == "SKIPPED", (status, note)
        assert "not a git repository" in note


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  [ok] {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  [FAIL] {name}: {exc}", file=sys.stderr)
    if failures:
        print(f"ERROR: {failures} test(s) failed", file=sys.stderr)
        sys.exit(1)
    print("all hooks_path tests passed")
