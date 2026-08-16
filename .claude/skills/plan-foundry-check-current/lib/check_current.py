#!/usr/bin/env python3
"""
check_current.py - Currency check for plan_foundry (AC6 model).

Reads the target's `.claude/.plan-foundry-bundle-version` pin and compares
it to the bundle's current `HEAD` on the public remote via `git ls-remote`.

Single tier - there is no local bundle clone anymore. The local bundle was
removed by PLAN-AC6 (2026-05-19) when the bundle moved to on-demand network
clone.

Always exits 0; status is conveyed via JSON on stdout.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from typing import Optional

_SHARED = pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
import bundle_semver  # noqa: E402

BUNDLE_IDENTITY = "plan_foundry"


def _installed_bundle_identity(shared: pathlib.Path):
    """Return the `bundle` field of the installed _shared/bundle-contract.json.

    Inline, importing nothing from _shared/, for the reason given at length
    in plan-foundry-sync/lib/sync.py's installed_bundle_identity. None means
    absent or malformed or fieldless - the pre-identity state that every
    consumer installed before this field existed is in, which is trusted.
    """
    import json as _json

    path = pathlib.Path(shared) / "bundle-contract.json"
    try:
        data = _json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("bundle")
    return value if isinstance(value, str) and value else None


EXPECTED_REPO = "kccastillo/plan_foundry"
BUNDLE_URL = f"https://github.com/{EXPECTED_REPO}"
VERSION_FILENAME = ".plan-foundry-bundle-version"
SYNC_INCOMPLETE_FILENAME = ".plan-foundry-sync-incomplete"


def _run(args, cwd=None):
    try:
        p = subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError as exc:
        return 1, "", f"git not found: {exc}"
    except Exception as exc:  # noqa: BLE001
        return 1, "", str(exc)


def _short(sha: str) -> str:
    return sha[:8] if sha else ""


def _read_version_file(target_claude: pathlib.Path) -> dict | None:
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


def _read_sync_incomplete(target_claude: pathlib.Path) -> dict | None:
    """Read the PLAN-AK6 incomplete-sync marker, inline - matching this
    module's existing practice of reading the pin inline rather than
    importing bundle_copy. Returns None when absent, unreadable, or
    malformed; never raises."""
    path = target_claude / SYNC_INCOMPLETE_FILENAME
    try:
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
    except (OSError, UnicodeDecodeError):
        return None


def fetch_remote_head(url: str = BUNDLE_URL) -> tuple[str, str]:
    """Return (remote_sha, error). On success error == ''."""
    rc, out, err = _run(["git", "ls-remote", url, "HEAD"])
    if rc != 0:
        return "", err or "git ls-remote failed"
    # First field of the first line is the sha.
    first_line = out.splitlines()[0] if out else ""
    sha = first_line.split()[0] if first_line else ""
    if not sha:
        return "", "ls-remote returned no sha"
    return sha, ""


def fetch_remote_tags(url: str = BUNDLE_URL) -> tuple[list[str], str]:
    """Return (tags, error). On success error == ''.

    PLAN-AH8, guarantee 1: this answers "should I sync", a question about
    the remote - deliberately distinct from sync's own pre-flight
    (_shared/preflight.py), which compares against the cloned bundle it is
    about to install (per D13).
    """
    rc, out, err = _run(["git", "ls-remote", "--tags", url])
    if rc != 0:
        return [], err or "git ls-remote --tags failed"
    tags: list[str] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ref = parts[1]
        if not ref.startswith("refs/tags/"):
            continue
        tag = ref[len("refs/tags/") :]
        if tag.endswith("^{}"):
            tag = tag[:-3]
        tags.append(tag)
    return tags, ""


def _compare_version(pin_tag: str, highest_tag: Optional[str]) -> str:
    """Return one of current | behind_patch | behind_minor | behind_major |
    unavailable. Never returns "current" from an underivable state - an
    empty pin tag or an unparseable/absent highest tag is "unavailable",
    not a comparable value.
    """
    if not pin_tag or highest_tag is None:
        return "unavailable"
    pin_parsed = bundle_semver.parse(pin_tag)
    highest_parsed = bundle_semver.parse(highest_tag)
    if pin_parsed is None or highest_parsed is None:
        return "unavailable"
    if highest_parsed[0] > pin_parsed[0]:
        return "behind_major"
    if highest_parsed[0] < pin_parsed[0]:
        return "current"
    if highest_parsed[1] > pin_parsed[1]:
        return "behind_minor"
    if highest_parsed[1] < pin_parsed[1]:
        return "current"
    if highest_parsed[2] > pin_parsed[2]:
        return "behind_patch"
    return "current"


def check(target_root: pathlib.Path) -> dict:
    """Currency check, plus a note when _shared/ is another bundle's.

    The note is appended here rather than at each of _check_body's six
    returns, so no future return can forget it.
    """
    result = _check_body(target_root)
    owner = result.get("shared_dir_owner")
    if owner:
        result["message"] = (
            f"{result['message']} NOTE: .claude/skills/_shared/ belongs to "
            f"'{owner}', not '{BUNDLE_IDENTITY}' - two bundles are installed "
            "here and are overwriting each other's shared helpers. Run "
            "/plan-foundry-sync to reclaim it."
        ).strip()
    return result


def _check_body(target_root: pathlib.Path) -> dict:
    result = {
        "status": "unknown",
        "project_sha": "",
        "remote_sha": "",
        "ref": "HEAD",
        "message": "",
        "version_compare": "unavailable",
        "shared_dir_owner": "",
        "sync_incomplete": None,
    }
    target_claude = target_root / ".claude"
    installed_identity = _installed_bundle_identity(
        target_claude / "skills" / "_shared"
    )
    if installed_identity is not None and installed_identity != BUNDLE_IDENTITY:
        # Reported, not fatal: the pin this check reads is plan_foundry's own
        # file and stays readable, so the currency answer is still worth
        # giving. What it cannot promise is that the installed helpers under
        # _shared/ are the ones that pin describes. /plan-foundry-sync
        # repairs this.
        result["shared_dir_owner"] = installed_identity
    if not target_claude.exists():
        result["status"] = "not_initialised"
        result["message"] = (
            f"{target_claude} does not exist - run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["status"] = "legacy_symlink"
        result["message"] = (
            f"{target_claude} is a symlink (legacy AC3 install) - "
            "run /init-plan-foundry to migrate."
        )
        return result
    pin = _read_version_file(target_claude)
    if pin is None:
        result["status"] = "not_initialised"
        result["message"] = (
            f"{target_claude}/{VERSION_FILENAME} is absent - run /init-plan-foundry first."
        )
        return result

    project_sha = pin.get("sha", "")
    result["project_sha"] = _short(project_sha)

    # PLAN-AK6 D6: decided before the network call, so the answer survives
    # an offline consumer. A target part-way through a failed sync must not
    # read as "current" or "behind" - both understate what is wrong - so
    # this overrides `status` and `message` and returns immediately, ahead
    # of fetch_remote_head() below. remote_sha and version_compare stay at
    # their unavailable defaults; that is the cost of answering offline.
    marker = _read_sync_incomplete(target_claude)
    if marker is not None:
        result["sync_incomplete"] = marker
        result["status"] = "sync_incomplete"
        result["message"] = (
            f"a previous sync was moving to {_short(marker.get('target_sha', ''))} "
            "and did not finish - this project holds a partly applied bundle. "
            "Run /plan-foundry-sync again to complete it."
        )
        return result

    remote_sha, err = fetch_remote_head()
    if err:
        result["status"] = "remote_unreachable"
        result["message"] = (
            f"could not query remote {BUNDLE_URL}: {err}. "
            f"You are pinned at {_short(project_sha) or '(unknown)'}; "
            "run /plan-foundry-sync when network is available to refresh."
        )
        return result
    result["remote_sha"] = _short(remote_sha)

    if not project_sha:
        result["status"] = "unknown"
        result["message"] = "project version pin has empty sha - run /plan-foundry-sync."
        return result

    if project_sha == remote_sha or project_sha[:8] == remote_sha[:8]:
        result["status"] = "current"
        result["message"] = (
            f"project is up to date (pinned at {_short(project_sha)}, "
            f"remote HEAD {_short(remote_sha)})."
        )
        return result

    # PLAN-AH8 guarantee 1: the pre-sync break signal. Separate from `status`
    # above (which stays sha-based and untouched) - this compares the pin's
    # own tag against the remote's highest parsed tag, so a consumer can
    # tell a breaking sync from a routine one before running it. Degrades to
    # "unavailable" on an empty pin tag, an ls-remote failure, or zero
    # parseable remote tags - never fabricates "current" from an unknown
    # state.
    remote_tags, tags_err = fetch_remote_tags()
    highest_tag = bundle_semver.highest(remote_tags) if not tags_err else None
    result["version_compare"] = _compare_version(pin.get("tag", ""), highest_tag)

    result["status"] = "behind_or_diverged"
    result["message"] = (
        f"project pin {_short(project_sha)} differs from remote HEAD "
        f"{_short(remote_sha)} - run /plan-foundry-sync to update."
    )
    return result


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-root",
        default=None,
        help="Project root (default: current working directory).",
    )
    args = parser.parse_args(argv)
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else pathlib.Path.cwd().resolve()
    )
    result = check(target_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
