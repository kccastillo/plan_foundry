#!/usr/bin/env python3
"""
test_foundryreq_deletion_guard.py - tests for foundryreq_deletion_guard.py
and the .claude/hooks/pre-commit hook that invokes it (PLAN-AK7).

Every fixture is a throwaway `git init` directory the test creates and
tears down itself via tempfile.TemporaryDirectory -- no tmp_path/tmpdir
split, matching the convention already used by test_hooks_path.py in this
same directory. A fresh `git init` has neither `user.name` nor
`user.email`, and `git commit` fails without them for a reason unrelated to
the guard under test, so every fixture sets both locally before its first
commit.

Two families of test:
  - Pure-function tests (a-h) call check_staged_deletions() directly.
  - Hook-level tests (named with "hook_script" or "is_foundry_source" in
    their function name) invoke .claude/hooks/pre-commit itself as a
    subprocess via `git commit`, with `core.hooksPath` pointed at this
    repo's real .claude/hooks directory (absolute path -- a relative value
    resolves against the fixture repo, which has no such directory).
"""

import importlib.util
import pathlib
import shutil
import subprocess
import sys
import tempfile

_LIB_DIR = pathlib.Path(__file__).resolve().parent
_SHARED = _LIB_DIR.parent
_REPO_ROOT = _SHARED.parents[2]  # _shared -> skills -> .claude -> repo_root
_HOOKS_DIR = _REPO_ROOT / ".claude" / "hooks"

_spec = importlib.util.spec_from_file_location(
    "foundryreq_deletion_guard", _SHARED / "foundryreq_deletion_guard.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

check_staged_deletions = _mod.check_staged_deletions


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _init_repo(root: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=str(root), capture_output=True, check=True)


def _request_body(status: str) -> str:
    return f"---\ntitle: test\nintegration_status: {status}\n---\n\nbody\n"


def _commit_file(root: pathlib.Path, rel_path: str, content: str) -> None:
    full = root / rel_path
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel_path], cwd=str(root), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"add {rel_path}"], cwd=str(root), capture_output=True, check=True)


def _stage_deletion(root: pathlib.Path, rel_path: str) -> None:
    subprocess.run(["git", "rm", "-q", rel_path], cwd=str(root), capture_output=True, check=True)


# ---------------------------------------------------------------------------
# (a)-(h): pure-function tests against check_staged_deletions
# ---------------------------------------------------------------------------

def test_pending_deletion_is_flagged():
    """(a) committed pending FOUNDRYREQ, staged plain deletion -> flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/FOUNDRYREQ-alpha.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)

        violations = check_staged_deletions(root)
        assert len(violations) == 1
        assert violations[0] == {"path": rel, "integration_status": "pending"}


def test_integrated_deletion_is_not_flagged():
    """(b) same file at integration_status: integrated -> not flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/FOUNDRYREQ-beta.md"
        _commit_file(root, rel, _request_body("integrated"))
        _stage_deletion(root, rel)

        assert check_staged_deletions(root) == []


def test_rename_to_retired_is_not_flagged():
    """(c) pending file staged as a rename to Retired/, bytes unchanged -> not flagged (D2)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/FOUNDRYREQ-gamma.md"
        _commit_file(root, rel, _request_body("pending"))
        (root / "Retired").mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "mv", rel, "Retired/FOUNDRYREQ-gamma.md"],
            cwd=str(root), capture_output=True, check=True,
        )

        assert check_staged_deletions(root) == []


def test_never_committed_file_is_not_flagged():
    """(d) created and staged for deletion without ever being committed -> not flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        # Seed a HEAD so `git diff --cached` has a real commit to compare against.
        _commit_file(root, "README.md", "seed\n")

        rel = "Workbench/FOUNDRYREQ-delta.md"
        full = root / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(_request_body("pending"), encoding="utf-8")
        subprocess.run(["git", "add", rel], cwd=str(root), capture_output=True, check=True)
        subprocess.run(["git", "rm", "-q", "--cached", rel], cwd=str(root), capture_output=True, check=True)
        full.unlink()

        assert check_staged_deletions(root) == []


def test_non_matching_filename_is_not_flagged():
    """(e) pending file whose name does not match the FOUNDRYREQ/PTREQ glob -> not flagged."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/NOTES-epsilon.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)

        assert check_staged_deletions(root) == []


def test_ptreq_pending_deletion_is_flagged():
    """(f) pending PTREQ file staged for deletion -> flagged, proving the PTREQ half of the glob."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/PTREQ-zeta.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)

        violations = check_staged_deletions(root)
        assert len(violations) == 1
        assert violations[0]["path"] == rel


def test_mixed_case_prefix_is_flagged():
    """(g) mixed-case prefix (Foundryreq-*.md) staged for deletion -> flagged, proving case-insensitivity."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/Foundryreq-eta.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)

        violations = check_staged_deletions(root)
        assert len(violations) == 1
        assert violations[0]["path"] == rel


def test_transient_subdirectory_deletion_is_flagged():
    """(h) pending file under Workbench/transient/ staged for deletion -> flagged (recursive glob)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        rel = "Workbench/transient/FOUNDRYREQ-theta.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)

        violations = check_staged_deletions(root)
        assert len(violations) == 1
        assert violations[0]["path"] == rel


# ---------------------------------------------------------------------------
# Hook-level tests: invoke .claude/hooks/pre-commit itself via `git commit`
# ---------------------------------------------------------------------------

def test_hook_script_blocks_pending_and_allows_integrated():
    """
    A real commit attempt against the actual hook script (not the underlying
    Python function): a plain deletion of a pending-status request is
    rejected with the offending path printed; an integrated-status control
    case is allowed through. This is the test the Verification section's
    `acceptance:` item selects via `-k hook_script`.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        subprocess.run(
            ["git", "config", "core.hooksPath", _HOOKS_DIR.as_posix()],
            cwd=str(root), capture_output=True, check=True,
        )

        rel = "Workbench/FOUNDRYREQ-hook-pending.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)
        blocked = subprocess.run(
            ["git", "commit", "-q", "-m", "remove pending request"],
            cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert blocked.returncode != 0
        assert rel in (blocked.stdout + blocked.stderr)

        # The rejected commit left the deletion staged in the index (not just
        # the working tree), so `git checkout -- rel` alone is not enough - it
        # restores the working tree from an index that still has no entry for
        # rel. `git checkout HEAD -- rel` resets both the index and the
        # working tree from HEAD, fully unstaging the deletion before the
        # control case so it starts from a clean, committed state.
        subprocess.run(["git", "checkout", "HEAD", "--", rel], cwd=str(root), capture_output=True)

        rel2 = "Workbench/FOUNDRYREQ-hook-integrated.md"
        _commit_file(root, rel2, _request_body("integrated"))
        _stage_deletion(root, rel2)
        allowed = subprocess.run(
            ["git", "commit", "-q", "-m", "remove integrated request"],
            cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert allowed.returncode == 0, (allowed.stdout, allowed.stderr)


def test_is_foundry_source_gates_claude_md_cap_outside_dev_repo():
    """
    A fixture with no scripts/promote.sh (so is_foundry_source reads false)
    and an over-175-line CLAUDE.md still commits cleanly -- proving the
    CLAUDE.md-cap block is actually gated off outside this dev repo, rather
    than merely passing because the fixture happens to have no CLAUDE.md.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)
        subprocess.run(
            ["git", "config", "core.hooksPath", _HOOKS_DIR.as_posix()],
            cwd=str(root), capture_output=True, check=True,
        )

        claude_md = root / "CLAUDE.md"
        claude_md.write_text("\n".join(f"line {i}" for i in range(1, 300)) + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "CLAUDE.md"], cwd=str(root), capture_output=True, check=True)
        result = subprocess.run(
            ["git", "commit", "-q", "-m", "add oversized CLAUDE.md"],
            cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, (result.stdout, result.stderr)


def test_hook_script_fails_open_without_guard_module():
    """
    The hook copied alone into an isolated hooks dir (no ../skills/_shared/
    sibling) must degrade to inert rather than block every commit -- this is
    the branch that decides whether a consumer's commits work at all.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _init_repo(root)

        isolated_hooks = root / "hooks"
        isolated_hooks.mkdir()
        shutil.copy2(_HOOKS_DIR / "pre-commit", isolated_hooks / "pre-commit")
        subprocess.run(
            ["git", "config", "core.hooksPath", isolated_hooks.resolve().as_posix()],
            cwd=str(root), capture_output=True, check=True,
        )

        rel = "Workbench/FOUNDRYREQ-orphan.md"
        _commit_file(root, rel, _request_body("pending"))
        _stage_deletion(root, rel)
        result = subprocess.run(
            ["git", "commit", "-q", "-m", "remove pending request, no guard module present"],
            cwd=str(root), capture_output=True, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0, (result.stdout, result.stderr)


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
    print("all foundryreq_deletion_guard tests passed")
