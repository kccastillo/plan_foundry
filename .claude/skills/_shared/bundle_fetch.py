"""
bundle_fetch.py - clone the production plan_foundry bundle on demand.

Used by init-plan-foundry and plan-foundry-sync under the PLAN-AC6 model,
where the bundle is not pre-installed on the user's machine. Every install
and every sync fetches a fresh shallow clone from the public URL into a
transient directory inside the target repo, so the operation works inside
Claude Code sessions whose filesystem write surface is scoped to the target.

The caller deletes the transient clone after the copy and the version-pin
write.
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

    Git marks .git/objects/pack/*.idx and *.pack read-only on Windows, so a
    plain shutil.rmtree(ignore_errors=True) leaves those files in place
    without reporting an error.
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

    Removes any pre-existing .plan-foundry-tmp/ first, which makes the call
    idempotent across a crashed prior run. Returns the path to the clone, and
    raises BundleFetchError when the clone fails for any reason.
    """
    target_root = pathlib.Path(target_root)
    tmp = target_root / TMP_DIRNAME
    if tmp.exists():
        _force_remove_tree(tmp)
        if tmp.exists():
            raise BundleFetchError(
                f"could not remove stale {tmp} before clone - check the file permissions on that directory"
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
    """Delete <target_root>/.plan-foundry-tmp/ when present, and return True
    when the directory was removed.
    """
    target_root = pathlib.Path(target_root)
    tmp = target_root / TMP_DIRNAME
    if not tmp.exists():
        return False
    _force_remove_tree(tmp)
    return not tmp.exists()
