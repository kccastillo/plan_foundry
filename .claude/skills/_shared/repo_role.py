#!/usr/bin/env python3
"""repo_role.py - is this tree the plan_foundry source repo, or a consumer install?

A consumer receives an allowlisted subset of the source tree (see
scripts/promote.sh ALLOWLIST): the four .claude/ directories, a handful of
scripts, and the shipped root documents. Several CI checks have to behave
differently in the two cases, because a check that asserts a property of the
source repo produces a false failure against a repository that was never given
the file the property is about.

The rule those checks follow: in a consumer install a shipped check asserts
properties of the bundle, not properties of the consumer's own repository.

scripts/ci/run-all.sh implements the same test in bash, because it runs before
any Python is invoked and cannot import this module. test_repo_role.py asserts
the two implementations agree on their marker set, so they cannot drift.
"""
from __future__ import annotations

from pathlib import Path

# Present in the source repo and absent from every consumer install, because
# neither path is on promote.sh's allowlist. promote.sh is the allowlist itself
# and prod-repo.txt carries the push target, so shipping either would hand a
# consumer the means to push to the prod bundle.
SOURCE_MARKERS = ("scripts/promote.sh", "scripts/prod-repo.txt")


def is_foundry_source(repo_root) -> bool:
    """Return True when repo_root is the plan_foundry source repo.

    Both markers must be present. A tree carrying only one of them is treated
    as a consumer install, which is the safe direction: a check that skips a
    source-only assertion in the source repo is caught by CI there, and a check
    that runs a source-only assertion in a consumer repo is a red build nobody
    can fix.
    """
    root = Path(repo_root)
    return all((root / marker).is_file() for marker in SOURCE_MARKERS)
