#!/usr/bin/env python3
"""
test_check_live_references.py - the relative-link scan is scoped to bundle
content in a consumer install, and stays whole-tree in the foundry source
repo.

check-live-references.py's relative-link check used to walk the entire
repository tree for markdown, so a consumer install with a stray broken link
anywhere in its own files failed a build over content this bundle has no
business asserting on. This proves the scoped behaviour holds in both
directions: a consumer install skips a broken link outside the bundle
surface and still catches one inside it, and the foundry source repo keeps
scanning everything, unchanged.

Run: python3 scripts/ci/test_check_live_references.py
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECK = REPO_ROOT / "scripts" / "ci" / "check-live-references.py"


def load_check():
    spec = importlib.util.spec_from_file_location("check_live_references", CHECK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _point_at(module, tmp_root: Path) -> tuple[Path, Path]:
    """Redirect the module's repo-root constants at a throwaway tree."""
    old_root = module.REPO_ROOT
    old_claude = module.CLAUDE_DIR
    module.REPO_ROOT = tmp_root
    module.CLAUDE_DIR = tmp_root / ".claude"
    return old_root, old_claude


def _restore(module, old_root: Path, old_claude: Path) -> None:
    module.REPO_ROOT = old_root
    module.CLAUDE_DIR = old_claude


def test_consumer_install_scan_skips_the_consumers_own_markdown():
    module = load_check()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        # No scripts/promote.sh or scripts/prod-repo.txt: repo_role reads
        # this tree as a consumer install, not the foundry source repo.
        skill_dir = tmp_root / ".claude" / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("bundle content\n", encoding="utf-8")
        (tmp_root / "README.md").write_text("shipped root doc\n", encoding="utf-8")
        docs = tmp_root / "docs"
        docs.mkdir()
        (docs / "random.md").write_text("the consumer's own page\n", encoding="utf-8")

        old_root, old_claude = _point_at(module, tmp_root)
        try:
            found = {
                p.relative_to(tmp_root).as_posix()
                for p in module._relative_link_scan_files()
            }
        finally:
            _restore(module, old_root, old_claude)

        assert "docs/random.md" not in found, found
        assert ".claude/skills/foo/SKILL.md" in found, found
        assert "README.md" in found, found


def test_source_repo_scan_still_covers_the_whole_tree():
    module = load_check()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        scripts = tmp_root / "scripts"
        scripts.mkdir()
        (scripts / "promote.sh").write_text("# marker\n", encoding="utf-8")
        (scripts / "prod-repo.txt").write_text("marker\n", encoding="utf-8")
        docs = tmp_root / "docs"
        docs.mkdir()
        (docs / "random.md").write_text("source-repo content\n", encoding="utf-8")

        old_root, old_claude = _point_at(module, tmp_root)
        try:
            found = {
                p.relative_to(tmp_root).as_posix()
                for p in module._relative_link_scan_files()
            }
        finally:
            _restore(module, old_root, old_claude)

        assert "docs/random.md" in found, found


def test_consumer_install_still_catches_a_broken_link_inside_the_bundle():
    module = load_check()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        skill_dir = tmp_root / ".claude" / "skills" / "foo"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "[dangling](../missing.md)\n", encoding="utf-8"
        )
        docs = tmp_root / "docs"
        docs.mkdir()
        (docs / "random.md").write_text(
            "[also dangling](./nope.md)\n", encoding="utf-8"
        )

        old_root, old_claude = _point_at(module, tmp_root)
        old_failures = module.failures
        module.failures = []
        try:
            module.check_relative_links()
            found_failures = list(module.failures)
        finally:
            _restore(module, old_root, old_claude)
            module.failures = old_failures

        joined = "\n".join(found_failures)
        assert "SKILL.md" in joined, joined
        assert "random.md" not in joined, joined


def main() -> int:
    tests = [
        test_consumer_install_scan_skips_the_consumers_own_markdown,
        test_source_repo_scan_still_covers_the_whole_tree,
        test_consumer_install_still_catches_a_broken_link_inside_the_bundle,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL: {t.__name__}: {exc}")
    if failed:
        print(f"{failed}/{len(tests)} test(s) failed")
        return 1
    print(f"all {len(tests)} test(s) passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
