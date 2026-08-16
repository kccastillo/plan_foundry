#!/usr/bin/env python3
"""
test_check_invariants.py - Doc-Set Integrity requires the root docs.

check_doc_set_integrity() requires CLAUDE.md, ARCHITECTURE.md, and README.md at
the repo root. The set is the same in the source repo and in a consumer install,
so the check is unconditional. This battery pins that behaviour: a complete set
passes, and a missing doc fails.

Run: python3 scripts/ci/test_check_invariants.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "ci" / "check-invariants.py"


def load_check():
    spec = importlib.util.spec_from_file_location("check_invariants", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_doc_set_check(module, tmp_root: Path):
    """Point the check at a throwaway tree and return its (ok, detail) result."""
    old_root = module.REPO_ROOT
    module.REPO_ROOT = tmp_root
    module.results = []
    try:
        module.check_doc_set_integrity()
    finally:
        module.REPO_ROOT = old_root
    name, ok, detail = module.results[-1]
    return ok, detail


def _write_docs(tmp_root: Path, names: list[str]) -> None:
    tmp_root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (tmp_root / name).write_text("placeholder\n", encoding="utf-8")


def test_full_doc_set_passes() -> None:
    module = load_check()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _write_docs(tmp_root, ["CLAUDE.md", "ARCHITECTURE.md", "README.md"])
        ok, detail = run_doc_set_check(module, tmp_root)
        assert ok, f"expected a complete root doc set to pass, got: {detail}"


def test_missing_doc_fails() -> None:
    module = load_check()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _write_docs(tmp_root, ["CLAUDE.md", "ARCHITECTURE.md"])
        ok, detail = run_doc_set_check(module, tmp_root)
        assert not ok, "expected a doc set missing README.md to fail"
        assert "README.md" in detail


def test_source_repo_uses_the_same_set() -> None:
    """A source-shaped tree (promote.sh present) is held to the same docs, no more."""
    module = load_check()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        _write_docs(tmp_root, ["CLAUDE.md", "ARCHITECTURE.md", "README.md"])
        scripts_dir = tmp_root / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "promote.sh").write_text("placeholder\n", encoding="utf-8")
        (scripts_dir / "prod-repo.txt").write_text("placeholder\n", encoding="utf-8")
        ok, detail = run_doc_set_check(module, tmp_root)
        assert ok, f"expected a source repo with the three root docs to pass, got: {detail}"


def test_this_repo_doc_set_passes() -> None:
    """This repo's real tree must satisfy the invariant."""
    module = load_check()
    ok, detail = run_doc_set_check(module, REPO_ROOT)
    assert ok, f"expected this repo's real doc set to pass, got: {detail}"


def main() -> int:
    tests = [
        test_full_doc_set_passes,
        test_missing_doc_fails,
        test_source_repo_uses_the_same_set,
        test_this_repo_doc_set_passes,
    ]
    failures = []
    for test in tests:
        try:
            test()
        except AssertionError as exc:
            failures.append(f"{test.__name__}: {exc}")

    if failures:
        print("test_check_invariants: FAILED", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1

    print("test_check_invariants: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
