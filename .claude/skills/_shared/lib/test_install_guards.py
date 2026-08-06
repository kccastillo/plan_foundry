"""Tests for the three install guards (PLAN-AJ6).

Raised from paper_trail_dev, which could not use the shipped installer: it is
the source of a sibling bundle forked from this one, so it owns tracked files
at paths plan_foundry treats as its own.

Each guard gets its positive case and its negative case. The negative cases
are the load-bearing half - a guard that fires on an ordinary consumer is
worse than no guard, because a check that cries wolf on a clean tree trains
people to ignore it.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import bundle_copy  # noqa: E402
import gitignore_entries  # noqa: E402
import preflight  # noqa: E402


def _git_repo(root: pathlib.Path) -> pathlib.Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@example.com"], cwd=str(root), check=True
    )
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(root), check=True)
    return root


def _commit_all(root: pathlib.Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True)
    subprocess.run(["git", "commit", "-qm", "x"], cwd=str(root), check=True)


def _write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


LEDGER = [
    {
        "path": ".claude/skills/convert-pdf/SKILL.md",
        "since": "v1.15.0",
        "removed_in": "v2.0.0",
        "replaced_by": "paper_trail bundle",
        "note": "moved out",
        "kind": "skill",
    }
]

SHIM_TEXT = (
    "---\nname: convert-pdf\ndescription: 'Deprecated'\n---\n\n"
    "This surface is deprecated. Replaced by: paper_trail bundle. "
    "Removed in: v2.0.0. moved out\n"
)


# ---------------------------------------------------------------------------
# Guard 1 - a deprecation shim never overwrites a richer file
# ---------------------------------------------------------------------------


def test_shim_does_not_overwrite_a_real_skill(tmp_path):
    """The failure that made a hand-rolled installer necessary."""
    bundle = tmp_path / "bundle" / ".claude"
    target = tmp_path / "target" / ".claude"
    _write(bundle / "skills" / "convert-pdf" / "SKILL.md", SHIM_TEXT)
    real = _write(
        target / "skills" / "convert-pdf" / "SKILL.md",
        "---\nname: convert-pdf\n---\n\nThe real, working skill body.\n",
    )

    report = bundle_copy.copy_bundle_managed(bundle, target, deprecations=LEDGER)

    assert "skills/convert-pdf/SKILL.md" in report.shim_skipped
    assert "The real, working skill body." in real.read_text(encoding="utf-8")
    assert "shim_skipped=1" in report.summary()


def test_shim_over_a_shim_still_copies(tmp_path):
    """Negative case: an already-shimmed target has nothing richer to protect,
    so an updated shim must still land."""
    bundle = tmp_path / "bundle" / ".claude"
    target = tmp_path / "target" / ".claude"
    _write(bundle / "skills" / "convert-pdf" / "SKILL.md", SHIM_TEXT)
    _write(
        target / "skills" / "convert-pdf" / "SKILL.md",
        SHIM_TEXT.replace("v2.0.0", "v1.99.0"),
    )

    report = bundle_copy.copy_bundle_managed(bundle, target, deprecations=LEDGER)

    assert report.shim_skipped == []
    assert "skills/convert-pdf/SKILL.md" in report.files_copied


def test_shim_copies_when_target_has_no_file(tmp_path):
    """Negative case: a fresh consumer gets the shim, which is the whole point
    of shipping one during the grace release."""
    bundle = tmp_path / "bundle" / ".claude"
    target = tmp_path / "target" / ".claude"
    _write(bundle / "skills" / "convert-pdf" / "SKILL.md", SHIM_TEXT)

    report = bundle_copy.copy_bundle_managed(bundle, target, deprecations=LEDGER)

    assert report.shim_skipped == []
    assert "skills/convert-pdf/SKILL.md" in report.files_copied


def test_no_ledger_means_plain_copy(tmp_path):
    """Negative case: omitting the argument preserves the pre-guard behaviour,
    so no existing caller changes meaning."""
    bundle = tmp_path / "bundle" / ".claude"
    target = tmp_path / "target" / ".claude"
    _write(bundle / "skills" / "convert-pdf" / "SKILL.md", SHIM_TEXT)
    _write(target / "skills" / "convert-pdf" / "SKILL.md", "richer\n")

    report = bundle_copy.copy_bundle_managed(bundle, target)

    assert report.shim_skipped == []
    assert "skills/convert-pdf/SKILL.md" in report.files_copied


def test_helper_kind_entry_never_matches_a_copy_target():
    """A kind: helper entry addresses file.py::symbol and has no file-level
    path, so it can never equal a copy destination."""
    entries = [
        {"path": ".claude/skills/_shared/bundle_copy.py::_helper", "kind": "helper"},
        {"path": ".claude/skills/convert-pdf/SKILL.md", "kind": "skill"},
    ]
    assert bundle_copy._shimmed_relpaths(entries) == {"skills/convert-pdf/SKILL.md"}


# ---------------------------------------------------------------------------
# Guard 2 - Step 0 detects a foreign bundle, not only our own name
# ---------------------------------------------------------------------------


def test_tracked_bundle_dir_is_a_foreign_bundle(tmp_path):
    """paper_trail_dev's actual shape: a repo whose .claude/skills is source."""
    target = _git_repo(tmp_path / "sibling")
    _write(target / ".claude" / "skills" / "own-skill" / "SKILL.md", "mine\n")
    _commit_all(target)

    result = preflight.detect_foreign_bundle(target)

    assert result is not None
    assert "foreign-bundle-detected" in result
    assert ".claude/skills" in result


def test_differing_bundle_contract_is_a_foreign_bundle(tmp_path):
    target = _git_repo(tmp_path / "sibling")
    bundle = tmp_path / "bundle"
    _write(
        target / ".claude" / "skills" / "_shared" / "bundle-contract.json",
        json.dumps({"schema_version": 2, "deprecations": [{"path": "theirs"}]}),
    )
    _write(
        bundle / ".claude" / "skills" / "_shared" / "bundle-contract.json",
        json.dumps({"schema_version": 2, "deprecations": []}),
    )

    result = preflight.detect_foreign_bundle(target, bundle)

    assert result is not None
    assert "bundle-contract.json" in result


def test_ordinary_consumer_is_not_foreign(tmp_path):
    """Negative case, and the one that matters most. A consumer with an
    untracked (gitignored) .claude/ must install without friction."""
    target = _git_repo(tmp_path / "consumer")
    _write(target / ".gitignore", ".claude/skills/\n")
    _write(target / "README.md", "a project\n")
    _commit_all(target)
    _write(target / ".claude" / "skills" / "write-plan" / "SKILL.md", "installed\n")

    assert preflight.detect_foreign_bundle(target) is None


def test_identical_contract_is_not_foreign(tmp_path):
    """Negative case: a consumer already synced from this bundle carries an
    identical contract, which is convergence rather than a second bundle."""
    target = _git_repo(tmp_path / "consumer")
    bundle = tmp_path / "bundle"
    same = json.dumps({"schema_version": 2, "deprecations": []})
    _write(target / ".claude" / "skills" / "_shared" / "bundle-contract.json", same)
    _write(bundle / ".claude" / "skills" / "_shared" / "bundle-contract.json", same)
    _write(target / ".gitignore", ".claude/skills/\n")
    _commit_all(target)

    assert preflight.detect_foreign_bundle(target, bundle) is None


def test_non_git_target_fails_open(tmp_path):
    """Fail-open: outside a repo the tracked-file signal cannot be evaluated,
    so it must not fire."""
    target = tmp_path / "plain"
    _write(target / ".claude" / "skills" / "x" / "SKILL.md", "x\n")

    assert preflight.detect_foreign_bundle(target) is None


# ---------------------------------------------------------------------------
# Guard 3 - never gitignore a directory that already holds tracked files
# ---------------------------------------------------------------------------


def test_tracked_dir_is_not_added_to_gitignore(tmp_path):
    target = _git_repo(tmp_path / "sibling")
    _write(target / ".claude" / "skills" / "own" / "SKILL.md", "mine\n")
    _commit_all(target)

    status, added, skipped = gitignore_entries.ensure_gitignore_entries(target)

    assert ".claude/skills/" in skipped
    assert ".claude/skills/" not in added
    body = (target / ".gitignore").read_text(encoding="utf-8")
    assert ".claude/skills/" not in body.splitlines()
    # The product stays tracked, which is the whole point.
    tracked = subprocess.run(
        ["git", "ls-files", "--", ".claude/skills"],
        cwd=str(target),
        capture_output=True,
        text=True,
    )
    assert "SKILL.md" in tracked.stdout


def test_untracked_dirs_are_still_ignored(tmp_path):
    """Negative case: the ordinary consumer still gets every entry."""
    target = _git_repo(tmp_path / "consumer")
    _write(target / "README.md", "a project\n")
    _commit_all(target)

    status, added, skipped = gitignore_entries.ensure_gitignore_entries(target)

    assert skipped == []
    assert status == "PASS"
    for entry in gitignore_entries.REQUIRED_GITIGNORE_ENTRIES:
        assert entry in added


def test_gitignore_is_idempotent(tmp_path):
    target = _git_repo(tmp_path / "consumer")
    _write(target / "README.md", "a project\n")
    _commit_all(target)

    gitignore_entries.ensure_gitignore_entries(target)
    status, added, skipped = gitignore_entries.ensure_gitignore_entries(target)

    assert status == "SKIPPED"
    assert added == []


def test_orchestrator_lock_is_gitignored():
    """The orchestrator lock's own docstring claims it is gitignored
    (FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1500); the required-entries
    tuple must actually carry it, not just the sibling heartbeat directory."""
    assert "Workbench/.orchestrator.lock" in gitignore_entries.REQUIRED_GITIGNORE_ENTRIES


def test_filter_tracked_fails_open_outside_a_repo(tmp_path):
    safe, skipped = gitignore_entries.filter_tracked(
        tmp_path, gitignore_entries.REQUIRED_GITIGNORE_ENTRIES
    )
    assert skipped == []
    assert len(safe) == len(gitignore_entries.REQUIRED_GITIGNORE_ENTRIES)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
