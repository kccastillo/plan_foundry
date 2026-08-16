"""
foundryreq_deletion_guard.py -- blocks an unintegrated FOUNDRYREQ/PTREQ request
file from being deleted out from under a commit.

Per PLAN-AK7 D1/D2. A request file's post-write lifecycle today is governed
entirely by prose (`integration_status: pending` -> `integrated` only via
plan-pipeline section 4F). Nothing on the bundle side stopped such a file
being deleted before it was integrated -- this module is the enforcement.

Mechanism (D1): inspect `git diff --cached --name-status -M` (rename
detection on). Only a plain deletion (status exactly `D`) is a candidate --
a rename (`R*`, e.g. the `retire` skill's own `git mv` closure path, D2) is
never flagged, because git itself reports an unchanged-bytes move as a
rename rather than a delete, at the default similarity threshold. The glob
match is evaluated fresh at every commit against `Workbench/` recursively
(a request file's lifecycle can relocate it to a documented subdirectory,
e.g. `Workbench/transient/` via plan-pipeline's `move-to-transient`
disposition) -- nothing here anchors to any one file's continued existence.

A matched, plainly-deleted path is read at HEAD (`git show HEAD:<path>`) and
its `integration_status` frontmatter value is checked. Anything other than
exactly `"integrated"` is flagged, including a missing key, an unparsable
frontmatter block, or a path that was never committed in the first place is
skipped silently (nothing committed, nothing to lose).

Escape hatches (D3), documented here and in the calling hook's own header
comment:
  (a) `git commit --no-verify`;
  (b) set `integration_status: integrated` on the file before deleting it.

Reads use `encoding="utf-8", errors="replace"`, matching this bundle's
general text-handling convention.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import yaml

# Case-insensitive prefix only, per D1 -- a bare re.I flag would also fold
# "Workbench" itself, which is not the intent. The (?:.*/)? segment is
# load-bearing: it scopes the guard recursively under Workbench/, covering
# documented relocation destinations such as Workbench/transient/.
_PATTERN = r"^Workbench/(?:.*/)?(?i:FOUNDRYREQ|PTREQ)-.*\.md$"

_REQUEST_PATH_RE = re.compile(_PATTERN)


def _git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout


def _parse_integration_status(text: str) -> str:
    """Return the frontmatter `integration_status` value, or "missing".

    Any failure mode -- no leading `---` markers, an unparsable YAML block,
    or a parsed mapping without the key -- is treated identically as
    "missing" (and therefore flagged): a request file that cannot be read is
    not confirmed integrated.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return "missing"
    end_idx = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = i
            break
    if end_idx is None:
        return "missing"
    front = "\n".join(lines[1:end_idx])
    try:
        data = yaml.safe_load(front)
    except yaml.YAMLError:
        return "missing"
    if not isinstance(data, dict):
        return "missing"
    value = data.get("integration_status")
    if value is None:
        return "missing"
    return str(value)


def check_staged_deletions(repo_root: Path) -> list[dict]:
    """Return a list of {"path": str, "integration_status": str} for every
    staged, plainly-deleted FOUNDRYREQ/PTREQ file under Workbench/ whose
    committed `integration_status` is not exactly "integrated".
    """
    violations: list[dict] = []
    diff_output = _git(repo_root, "diff", "--cached", "--name-status", "-M")
    for line in diff_output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        if status != "D":
            # Any rename code (R100, R95, ...) or other status is not a
            # plain delete -- out of scope per D2.
            continue
        if len(parts) < 2:
            continue
        path = parts[1]
        if not _REQUEST_PATH_RE.match(path):
            continue

        show_result = subprocess.run(
            ["git", "show", f"HEAD:{path}"],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        if show_result.returncode != 0:
            # Never committed at HEAD -- nothing durable is being lost.
            continue

        integration_status = _parse_integration_status(show_result.stdout)
        if integration_status != "integrated":
            violations.append({"path": path, "integration_status": integration_status})

    return violations


if __name__ == "__main__":
    repo_root_arg = Path(sys.argv[1])
    found = check_staged_deletions(repo_root_arg)
    for v in found:
        print(f"{v['path']}: integration_status={v['integration_status']}")
    sys.exit(1 if found else 0)
