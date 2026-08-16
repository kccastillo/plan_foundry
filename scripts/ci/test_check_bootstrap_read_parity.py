#!/usr/bin/env python3
"""Meta-test for check-bootstrap-read-parity.py (PLAN-AL8 D3).

Copies the three real source files into a temp tree, breaks one copy so
it disagrees with the other two on a fixture, then runs the check script
as a subprocess against the broken tree and asserts it exits 1 and names
the diverged function. Proves the check catches real drift rather than
only ever reporting PASS.

PLAN-AL8 D3 amendment: a third test proves the sync.md-to-Python arm the
amendment adds fires on its own - all three Python functions agree with
each other in that test's tree, and only sync.md changes.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CHECK_SCRIPT = REPO_ROOT / "scripts" / "ci" / "check-bootstrap-read-parity.py"


def _copy_source_tree(tmp_path: pathlib.Path):
    shared_dst = tmp_path / ".claude" / "skills" / "_shared"
    sync_dst = tmp_path / ".claude" / "skills" / "plan-foundry-sync" / "lib"
    workflows_dst = tmp_path / ".claude" / "skills" / "plan-foundry-sync" / "workflows"
    shared_dst.mkdir(parents=True)
    sync_dst.mkdir(parents=True)
    workflows_dst.mkdir(parents=True)

    shutil.copy(
        REPO_ROOT / ".claude/skills/_shared/bundle_copy.py",
        shared_dst / "bundle_copy.py",
    )
    shutil.copy(
        REPO_ROOT / ".claude/skills/_shared/preflight.py",
        shared_dst / "preflight.py",
    )
    shutil.copy(
        REPO_ROOT / ".claude/skills/plan-foundry-sync/lib/sync.py",
        sync_dst / "sync.py",
    )
    shutil.copy(
        REPO_ROOT / ".claude/skills/plan-foundry-sync/workflows/sync.md",
        workflows_dst / "sync.md",
    )
    return shared_dst, sync_dst, workflows_dst


def _install_patched_check(tmp_path: pathlib.Path) -> pathlib.Path:
    check_copy = tmp_path / "scripts" / "ci" / "check-bootstrap-read-parity.py"
    check_copy.parent.mkdir(parents=True)
    check_text = CHECK_SCRIPT.read_text(encoding="utf-8")
    old_repo_root_line = (
        "REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent"
    )
    assert old_repo_root_line in check_text, "REPO_ROOT line moved - update this test"
    check_text = check_text.replace(
        old_repo_root_line,
        f"REPO_ROOT = pathlib.Path({str(tmp_path)!r})",
    )
    check_copy.write_text(check_text, encoding="utf-8")
    return check_copy


def test_check_fails_on_divergence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        shared_dst, sync_dst, _workflows_dst = _copy_source_tree(tmp_path)

        sync_text = (sync_dst / "sync.py").read_text(encoding="utf-8")
        needle = (
            "    value = data.get(\"bundle\")\n"
            "    return value if isinstance(value, str) and value else None"
        )
        assert needle in sync_text, "expected text not found in sync.py - check the source"
        broken = sync_text.replace(needle, "    return \"deliberately-wrong-for-test\"")
        (sync_dst / "sync.py").write_text(broken, encoding="utf-8")

        check_copy = _install_patched_check(tmp_path)

        result = subprocess.run(
            [sys.executable, str(check_copy)], capture_output=True, text=True
        )
        assert result.returncode == 1, (
            "expected the check to fail on a deliberately broken copy, got exit "
            f"{result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "installed_bundle_identity" in result.stderr

        # Second arm: breaking installed_bundle_identity alone never
        # exercises the read_bundle_contract vs _read_contract comparison,
        # which is the original PLAN-AH8 duplication both edited docstrings
        # are about. Break that one too and re-run.
        preflight_text = (shared_dst / "preflight.py").read_text(encoding="utf-8")
        pf_needle = "def _read_contract(bundle_path: pathlib.Path) -> dict:"
        assert pf_needle in preflight_text, "signature moved - update this test"
        (shared_dst / "preflight.py").write_text(
            preflight_text.replace(
                pf_needle, pf_needle + '\n    return {"drifted": True}'
            ),
            encoding="utf-8",
        )
        result = subprocess.run(
            [sys.executable, str(check_copy)], capture_output=True, text=True
        )
        assert result.returncode == 1, (
            "expected the check to fail once preflight._read_contract diverges, "
            f"got exit {result.returncode}\nstderr={result.stderr}"
        )
        assert "!= preflight._read_contract=" in result.stderr


def test_check_fails_on_markdown_reproduction() -> None:
    """PLAN-AL8 D3 amendment. All three Python functions agree with each
    other in this tree - only sync.md changes - so a failure here proves
    the sync.md arm runs on its own, not only alongside a Python
    divergence.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        _shared_dst, _sync_dst, workflows_dst = _copy_source_tree(tmp_path)

        sync_md_text = (workflows_dst / "sync.md").read_text(encoding="utf-8")
        needle = (
            "verdict, in_flight_plans, read_deprecations_fn, ledger_unavailable_reason = (\n"
            "    sync_lib.compute_preflight_verdict(bundle_path, target_claude, TARGET_ROOT)\n"
            ")"
        )
        assert needle in sync_md_text, (
            "expected delegated-call text not found in sync.md - check the source"
        )
        reproduced = (
            "import preflight  # reverted: reproducing compute_preflight_verdict's "
            "body inline instead of calling it\n\n"
            "verdict = preflight.compare_against_clone(target_claude, bundle_path)\n"
            "in_flight_plans = []\n"
            "if verdict == \"major_step\":\n"
            "    in_flight_plans = preflight.scan_in_flight_plans(TARGET_ROOT)"
        )
        broken_md = sync_md_text.replace(needle, reproduced)
        (workflows_dst / "sync.md").write_text(broken_md, encoding="utf-8")

        check_copy = _install_patched_check(tmp_path)

        result = subprocess.run(
            [sys.executable, str(check_copy)], capture_output=True, text=True
        )
        assert result.returncode == 1, (
            "expected the check to fail once sync.md reproduces "
            "compute_preflight_verdict's body instead of calling it, got exit "
            f"{result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
        assert "sync.md Step 2b" in result.stderr
        assert "never calls it" in result.stderr


if __name__ == "__main__":
    test_check_fails_on_divergence()
    test_check_fails_on_markdown_reproduction()
    print("test_check_bootstrap_read_parity: PASS")
