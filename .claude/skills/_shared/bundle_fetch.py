"""
bundle_fetch.py - clone the prod plan_foundry bundle on demand.

Used by init-plan-foundry and plan-foundry-sync under the AC6 model:
the bundle is not pre-installed on the user's machine; every install/sync
fetches a fresh shallow clone from the public URL into a transient
directory inside the target repo (so the operation works inside Claude
Code sessions whose filesystem write surface is scoped to the target).

The tmp clone is deleted by the caller after copy + version-pin write.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import stat
import subprocess

BUNDLE_URL = "https://github.com/kccastillo/plan_foundry"
TMP_DIRNAME = ".plan-foundry-tmp"


class BundleFetchError(Exception):
    """Raised when the bundle could not be cloned (network, auth, bad ref)."""


def _force_remove_tree(path: pathlib.Path) -> None:
    """rmtree that clears the readonly bit before retrying - Windows-safe.

    .git/objects/pack/*.idx and *.pack are marked read-only by git on Windows,
    so a plain shutil.rmtree(ignore_errors=True) silently leaves them in place.
    """

    def on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            return
        try:
            func(p)
        except OSError:
            return

    shutil.rmtree(path, onerror=on_error)


def clone_bundle(target_root: pathlib.Path, ref: str = "main") -> pathlib.Path:
    """Clone the public plan_foundry repo at `ref` into <target_root>/.plan-foundry-tmp/.

    Removes any pre-existing .plan-foundry-tmp/ first (idempotent across a
    crashed prior run). Returns the path to the clone. Raises BundleFetchError
    if the clone fails for any reason.
    """
    target_root = pathlib.Path(target_root)
    tmp = target_root / TMP_DIRNAME
    if tmp.exists():
        _force_remove_tree(tmp)
        if tmp.exists():
            raise BundleFetchError(
                f"could not remove stale {tmp} before clone (permission issue?)"
            )

    args = [
        "git",
        "clone",
        "--depth=1",
        "--branch",
        ref,
        BUNDLE_URL,
        str(tmp),
    ]
    try:
        res = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise BundleFetchError(f"git executable not found: {exc}") from exc

    if res.returncode != 0:
        raise BundleFetchError(
            f"git clone failed (exit {res.returncode}): {res.stderr.strip() or res.stdout.strip()}"
        )

    if not (tmp / ".claude").exists():
        raise BundleFetchError(
            f"clone succeeded but {tmp}/.claude missing - wrong ref '{ref}'?"
        )
    return tmp


def cleanup_tmp(target_root: pathlib.Path) -> bool:
    """Delete <target_root>/.plan-foundry-tmp/ if present. Returns True if removed."""
    target_root = pathlib.Path(target_root)
    tmp = target_root / TMP_DIRNAME
    if not tmp.exists():
        return False
    _force_remove_tree(tmp)
    return not tmp.exists()
