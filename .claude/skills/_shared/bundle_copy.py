"""
bundle_copy.py — shared helper for init-plan-foundry and plan-foundry-sync.

Exposes:
  - BUNDLE_MANAGED_DIRS: tuple of the four top-level subdirs under .claude
    that the bundle owns (skills, agents, commands, hooks).
  - copy_bundle_managed(bundle_claude, target_claude) -> CopyReport
  - write_version_file(bundle_root, target_claude) -> dict
  - read_version_file(target_claude) -> Optional[dict]

Design rationale: PLAN-AC5 (2026-05-19). The bundle propagates to target
projects by copy, not symlink. This module is the single source of truth
for which paths under .claude/ are bundle-managed and how the version pin
is recorded.

Never deletes from target. Bundle files that no longer exist upstream are
listed in CopyReport.stale_in_target but left in place — explicit cleanup
is the user's call.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import os
import pathlib
import shutil
import subprocess
from typing import Optional

BUNDLE_MANAGED_DIRS = ("skills", "agents", "commands", "hooks")
VERSION_FILENAME = ".plan-foundry-bundle-version"


@dataclasses.dataclass
class CopyReport:
    files_copied: list[str] = dataclasses.field(default_factory=list)
    files_unchanged: list[str] = dataclasses.field(default_factory=list)
    project_additions: list[str] = dataclasses.field(default_factory=list)
    stale_in_target: list[str] = dataclasses.field(default_factory=list)

    def summary(self) -> str:
        return (
            f"copied={len(self.files_copied)} "
            f"unchanged={len(self.files_unchanged)} "
            f"project_additions={len(self.project_additions)} "
            f"stale_in_target={len(self.stale_in_target)}"
        )


def _file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _files_equal(a: pathlib.Path, b: pathlib.Path) -> bool:
    try:
        sa = a.stat()
        sb = b.stat()
    except FileNotFoundError:
        return False
    if sa.st_size != sb.st_size:
        return False
    if sa.st_size > 1_048_576:
        return _file_sha256(a) == _file_sha256(b)
    return a.read_bytes() == b.read_bytes()


def _walk_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Return all regular file paths under root (relative paths from root)."""
    if not root.exists():
        return []
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = pathlib.Path(dirpath) / name
            out.append(full.relative_to(root))
    return out


def copy_bundle_managed(
    bundle_claude: pathlib.Path, target_claude: pathlib.Path
) -> CopyReport:
    """Copy bundle/.claude/{skills,agents,commands,hooks}/ into target/.claude/.

    Never deletes from target. Returns a CopyReport summarising what
    happened to each file under the four bundle-managed dirs.
    """
    bundle_claude = pathlib.Path(bundle_claude)
    target_claude = pathlib.Path(target_claude)
    report = CopyReport()

    target_claude.mkdir(parents=True, exist_ok=True)

    for sub in BUNDLE_MANAGED_DIRS:
        bundle_sub = bundle_claude / sub
        target_sub = target_claude / sub
        if not bundle_sub.exists():
            continue

        bundle_files = set(_walk_files(bundle_sub))
        target_files = set(_walk_files(target_sub))

        for rel in sorted(bundle_files):
            src = bundle_sub / rel
            dst = target_sub / rel
            display = f"{sub}/{rel.as_posix()}"
            if dst.exists() and _files_equal(src, dst):
                report.files_unchanged.append(display)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            report.files_copied.append(display)

        for rel in sorted(target_files - bundle_files):
            display = f"{sub}/{rel.as_posix()}"
            if _is_under_known_subskill(rel, bundle_files):
                report.project_additions.append(display)
            else:
                report.stale_in_target.append(display)

    return report


def _is_under_known_subskill(
    rel: pathlib.Path, bundle_files: set[pathlib.Path]
) -> bool:
    """Heuristic: a target file is a project addition (vs stale) if its
    top-level subdir under the bundle-managed dir is NOT present in the bundle.
    Files under a bundle-known subskill that the bundle dropped are stale.

    Example under skills/:
      bundle has skills/foo/A.md, skills/foo/B.md.
      target has skills/foo/A.md, skills/foo/C.md, skills/myproj/X.md.
      - skills/foo/C.md → stale (bundle owns skills/foo/, dropped C.md)
      - skills/myproj/X.md → project addition (bundle doesn't own skills/myproj/)
    """
    parts = rel.parts
    if len(parts) < 2:
        # File directly under skills/ etc. — if bundle doesn't have it, treat
        # as project addition (bundle structure puts everything under a named
        # subdir).
        return True
    top = parts[0]
    bundle_tops = {p.parts[0] for p in bundle_files if p.parts}
    return top not in bundle_tops


def _run_git(args: list[str], cwd: pathlib.Path) -> Optional[str]:
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def write_version_file(
    bundle_root: pathlib.Path, target_claude: pathlib.Path
) -> dict:
    """Write target/.claude/.plan-foundry-bundle-version with sha/tag/synced.

    Returns the dict that was written. Tag is "" when no exact-match tag exists.
    """
    bundle_root = pathlib.Path(bundle_root)
    target_claude = pathlib.Path(target_claude)
    sha = _run_git(["rev-parse", "HEAD"], bundle_root) or ""
    tag = _run_git(["describe", "--tags", "--exact-match"], bundle_root) or ""
    synced = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    data = {"sha": sha, "tag": tag, "synced": synced}
    target_claude.mkdir(parents=True, exist_ok=True)
    target = target_claude / VERSION_FILENAME
    tmp = target.with_suffix(target.suffix + ".tmp")
    body = f"sha={sha}\ntag={tag}\nsynced={synced}\n"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)
    return data


def read_version_file(target_claude: pathlib.Path) -> Optional[dict]:
    """Read target/.claude/.plan-foundry-bundle-version; return parsed dict or None."""
    target_claude = pathlib.Path(target_claude)
    path = target_claude / VERSION_FILENAME
    if not path.exists():
        return None
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out
