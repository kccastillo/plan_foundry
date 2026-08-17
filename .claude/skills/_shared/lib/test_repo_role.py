#!/usr/bin/env python3
"""
test_repo_role.py - tests for the source-repo detector shared by the CI checks.

The properties that matter: both markers are required rather than either one,
a tree with neither is a consumer install, and the Python detector agrees with
the bash detector inside scripts/ci/run-all.sh. The last of those is the one
worth having. run-all.sh cannot import Python before it decides whether to skip
a check, so the test is what stops the two implementations drifting apart and
leaving a check that skips in bash while running in Python.
"""

import importlib.util
import pathlib
import re

SHARED = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = SHARED.parent.parent.parent
_spec = importlib.util.spec_from_file_location("repo_role", SHARED / "repo_role.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

is_foundry_source = _mod.is_foundry_source
SOURCE_MARKERS = _mod.SOURCE_MARKERS


def _make_tree(root, markers):
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    for marker in markers:
        path = root / marker
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder\n", encoding="utf-8")


def test_both_markers_present_is_source(tmp_path):
    _make_tree(tmp_path, SOURCE_MARKERS)
    assert is_foundry_source(tmp_path) is True


def test_neither_marker_is_consumer(tmp_path):
    _make_tree(tmp_path, ())
    assert is_foundry_source(tmp_path) is False


def test_one_marker_only_is_consumer(tmp_path):
    """A half-populated tree resolves to consumer, which is the safe direction.

    A source-only assertion skipped in the source repo is caught by CI here. The
    same assertion run against a consumer repo is a red build the consumer has
    no way to fix, so the ambiguous case has to fall to the consumer side.
    """
    for marker in SOURCE_MARKERS:
        _make_tree(tmp_path, (marker,))
        assert is_foundry_source(tmp_path) is False
        (tmp_path / marker).unlink()


def test_a_marker_that_is_a_directory_does_not_count(tmp_path):
    for marker in SOURCE_MARKERS:
        (tmp_path / marker).mkdir(parents=True, exist_ok=True)
    assert is_foundry_source(tmp_path) is False


def test_the_tree_this_runs_in_resolves_to_a_role_without_error():
    """This test ships, so it cannot assert which role the host tree has.

    An earlier version asserted that the repository running it is the foundry
    source. That held here and failed inside the built bundle, where the same
    test runs against a consumer install. A promotion dry run is what caught it.
    """
    markers_present = [m for m in SOURCE_MARKERS if (REPO_ROOT / m).is_file()]
    expected = len(markers_present) == len(SOURCE_MARKERS)
    assert is_foundry_source(REPO_ROOT) is expected


def test_bash_and_python_detectors_use_the_same_markers():
    """run-all.sh sets is_foundry_source from its own test, so it must agree.

    The bash side reads as a pair of `[ -f <path> ]` tests joined by `&&`
    inside the `if` that assigns is_foundry_source. This test extracts the
    paths it names and compares them against SOURCE_MARKERS.
    """
    run_all = (REPO_ROOT / "scripts" / "ci" / "run-all.sh").read_text(
        encoding="utf-8", errors="replace"
    )
    block = re.search(
        r"is_foundry_source=0\s*\nif (.+?)\n\s*is_foundry_source=1", run_all, re.S
    )
    assert block, "could not locate the is_foundry_source assignment in run-all.sh"
    bash_markers = set(re.findall(r"\[ -f ([^\]]+?) \]", block.group(1)))
    assert bash_markers == set(SOURCE_MARKERS), (
        f"bash names {sorted(bash_markers)} and Python names {sorted(SOURCE_MARKERS)}"
    )


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-q"]))
