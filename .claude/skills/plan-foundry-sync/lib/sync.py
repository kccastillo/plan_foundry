#!/usr/bin/env python3
"""
sync.py - Implementation of plan-foundry-sync (AC6 model).

Clones the public plan_foundry repo on demand into <target>/.plan-foundry-tmp/,
copies bundle-managed paths into <target>/.claude/, refreshes the version pin,
deletes the tmp clone. No reliance on any path outside the target.

Always exits 0; status conveyed via JSON on stdout.

PLAN-AH9, guarantee 4: shim-then-delete lifecycle. A deprecated surface
keeps its path and gains a shim body (preflight.shim_body,
scripts/generate-deprecation-shim.py) for at least one minor release; only
at the next major does the path disappear from the bundle, at which point
classify_stale (PLAN-AH7) sees it as gone_upstream and this module
quarantines it. The shim is what makes the eventual quarantine safe -
by the time a surface is quarantined, every consumer has had a release in
which invoking it told them what replaced it. This module cross-references
each quarantined path against the deprecation ledger (preflight.
read_deprecations) and, for a match among file-path-addressed entries
(kind: skill | reference | hook), reports replaced_by and note rather than
a bare path. kind: helper entries are symbol-addressed (file.py::symbol)
and are never offered to this match - they have no file-level path to
compare against.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
from typing import Optional


BUNDLE_IDENTITY = "plan_foundry"
TMP_DIRNAME = ".plan-foundry-tmp"

# Legacy orphan excision (2026-08-05, human decision recorded in
# Workbench/.foundryreq-sweep/SEED.md).
#
# foundry-log (skill + agent + PostToolUse hook) left the bundle at v1.14.0,
# before the install-receipt substrate (PLAN-AH7) existed. classify_stale's
# gone_upstream only ever reaches a path recorded in some past receipt, and
# no receipt was ever written while these paths still shipped - so the
# ordinary quarantine path can never see them, on any future sync, for any
# consumer who installed before AH7. That is permanent for this class, not a
# timing gap a later sync closes.
#
# This is a closed, one-off list for that specific historical gap, not a
# general mechanism. A surface removed the ordinary way (ledger entry in
# bundle-contract.json + shim release, PLAN-AH9) never needs an entry here,
# because its path lives in a receipt by the time it is dropped and
# classify_stale reaches it on its own. Do not add future removals to this
# list - give them a ledger entry and a shim instead.
LEGACY_ORPHAN_DIRS = ("skills/foundry-log",)
LEGACY_ORPHAN_FILES = (
    "agents/foundry-log-summariser.md",
    "hooks/foundry-log.py",
)
# Substring matched against a hook entry's "command" string in settings.json.
LEGACY_ORPHAN_HOOK_MARKERS = ("foundry-log.py",)


def installed_shared_dir() -> pathlib.Path:
    """The installed _shared/ this script sits beside.

    Layout: .claude/skills/plan-foundry-sync/lib/sync.py - _shared is two
    dirs up. A named function rather than an inline expression so a test can
    point it at a fixture tree.
    """
    return pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"


def installed_bundle_identity(shared: pathlib.Path) -> Optional[str]:
    """Return the `bundle` field of the installed _shared/bundle-contract.json.

    Returns None when the contract is absent, malformed, or carries no
    `bundle` field - the pre-identity state, which every consumer installed
    before this field existed is in. Never raises.

    Read inline with json + pathlib and NOTHING imported from _shared/. That
    is the whole point: this function exists to decide whether _shared/ can
    be trusted, so it cannot itself depend on _shared/. The same constraint
    produced the deliberate duplication of read_bundle_contract in
    _shared/preflight.py; this is the third instance of that pattern and,
    like the other two, must not be "simplified" into a shared import.
    """
    path = pathlib.Path(shared) / "bundle-contract.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("bundle")
    return value if isinstance(value, str) and value else None


def _legacy_orphan_relpaths(target_claude: pathlib.Path) -> list:
    """Every path on disk under `target_claude` matching the closed legacy-
    orphan list above, as "sub/relpath" display strings (same format as
    CopyReport's lists). A directory entry is expanded to its full file
    list, since quarantine() moves individual files, not directories.
    Present-on-disk only - a target that never had these, or one a human
    already cleaned up by hand, contributes nothing here.
    """
    target_claude = pathlib.Path(target_claude)
    out: list = []
    for rel in LEGACY_ORPHAN_FILES:
        if (target_claude / rel).is_file():
            out.append(rel)
    for rel_dir in LEGACY_ORPHAN_DIRS:
        dir_path = target_claude / rel_dir
        if dir_path.is_dir():
            for f in sorted(dir_path.rglob("*")):
                if f.is_file():
                    out.append(f"{rel_dir}/{f.relative_to(dir_path).as_posix()}")
    return sorted(out)


def _prune_empty_legacy_dirs(target_claude: pathlib.Path) -> None:
    """After quarantine() moves every file out of a LEGACY_ORPHAN_DIRS entry,
    remove the now-empty directory shell it leaves behind - quarantine()
    moves files, not directories, so without this a legacy dir with nothing
    left in it would still read as present. Bottom-up, os.rmdir only (never
    rmtree - a directory that still holds something, quarantined or not, is
    left alone rather than forced empty)."""
    target_claude = pathlib.Path(target_claude)
    for rel_dir in LEGACY_ORPHAN_DIRS:
        dir_path = target_claude / rel_dir
        if not dir_path.is_dir():
            continue
        for dirpath, _dirnames, _filenames in os.walk(dir_path, topdown=False):
            try:
                pathlib.Path(dirpath).rmdir()
            except OSError:
                pass  # not empty (something else landed here) - leave it


def _strip_dangling_hook_commands(target_root: pathlib.Path, markers) -> list:
    """Remove any hook entry from `target_root`/.claude/settings.json whose
    command string contains one of `markers`.

    A structured edit, not a file rewrite: parses the JSON, drops matching
    entries out of every `hooks.<event>` list (both the flat shape - an
    event list of `{"command": ...}` entries - and the nested shape actually
    shipped, `{"matcher": ..., "hooks": [{"command": ...}, ...]}`), and
    writes the result back. An inner `hooks` list left empty by a removal
    drops its parent group; an event list left empty drops the event key.
    Every other key in settings.json - permissions, unrelated hook entries,
    anything else the consumer holds - survives untouched apart from JSON
    re-serialisation.

    Idempotent and safe on a target that never had a matching entry, or one
    a human already edited out by hand: absent settings.json, absent hooks
    block, or no match are all no-ops that return []. Never raises on
    malformed JSON - treated the same as "no hooks block".
    """
    settings_path = pathlib.Path(target_root) / ".claude" / "settings.json"
    if not settings_path.exists():
        return []
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return []

    def _matches(command) -> bool:
        return isinstance(command, str) and any(m in command for m in markers)

    removed: list = []
    for event, groups in list(hooks.items()):
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                # Nested shape: {"matcher"?: ..., "hooks": [{"command": ...}]}
                kept_inner = []
                for inner in group["hooks"]:
                    command = inner.get("command") if isinstance(inner, dict) else None
                    if _matches(command):
                        removed.append(command)
                    else:
                        kept_inner.append(inner)
                if kept_inner:
                    group = dict(group, hooks=kept_inner)
                    kept_groups.append(group)
                # else: the group's only hook(s) matched - drop the whole group.
            elif isinstance(group, dict) and _matches(group.get("command")):
                # Flat shape: {"command": ...} directly in the event list.
                removed.append(group.get("command"))
            else:
                kept_groups.append(group)
        if kept_groups:
            hooks[event] = kept_groups
        else:
            del hooks[event]

    if not removed:
        return []
    if not hooks:
        del data["hooks"]
    settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return removed


def _bootstrap_clone(target_root: pathlib.Path, ref: str) -> pathlib.Path:
    """Clone the plan_foundry bundle without using the installed _shared/.

    Mirrors bundle_fetch.clone_bundle, deliberately duplicated for the one
    case that helper cannot serve: the installed _shared/ belongs to a
    different bundle, so bundle_fetch.BUNDLE_URL would point at that other
    bundle's repo and this sync would silently install the wrong product
    under plan_foundry's version pin. Raises RuntimeError on any failure;
    the caller converts that into the ordinary "could not fetch bundle"
    outcome.
    """
    tmp = pathlib.Path(target_root) / TMP_DIRNAME
    if tmp.exists():
        shutil.rmtree(tmp, onerror=_chmod_retry)
        if tmp.exists():
            raise RuntimeError(f"could not remove stale {tmp} before clone")
    args = [
        "git",
        "clone",
        "--depth=1",
        "--branch",
        ref,
        "https://github.com/kccastillo/plan_foundry",
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
        raise RuntimeError(f"git executable not found: {exc}") from exc
    if res.returncode != 0:
        raise RuntimeError(
            f"git clone failed (exit {res.returncode}): "
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    if not (tmp / ".claude").exists():
        raise RuntimeError(f"clone succeeded but {tmp}/.claude missing - bad ref '{ref}'?")
    return tmp


def _chmod_retry(func, p, _exc):
    """rmtree onerror handler - clear the readonly bit and retry (Windows)."""
    try:
        os.chmod(p, stat.S_IWRITE)
    except OSError:
        return
    try:
        func(p)
    except OSError:
        return


def _import_local_helpers(target_root: pathlib.Path = None, ref: str = "main"):
    """Bind bundle_copy, bundle_fetch and claude_md_block for this sync.

    Layout: .claude/skills/plan-foundry-sync/lib/sync.py - _shared is two dirs up.

    The installed _shared/ is used only when it belongs to this bundle.
    A consumer that also installs a sibling bundle descended from the same
    lineage can have the other bundle's _shared/ sitting at this path, and
    these three names are bound into sys.modules before the clone, so every
    later import of them anywhere in this process resolves to the foreign
    copy. The observed consequences run from a TypeError on a keyword the
    foreign copy_bundle_managed does not take, through to bundle_fetch
    cloning the other bundle's repo and installing it under plan_foundry's
    version pin without a word.

    On a mismatch the bundle is cloned first, by _bootstrap_clone, and all
    three names are bound from the clone instead. The clone is returned so
    the caller reuses it rather than fetching twice. Returns
    (bundle_copy, bundle_fetch, claude_md_block, prefetched_bundle, note).
    `prefetched_bundle` is None on the ordinary path.

    An installed contract with no `bundle` field is the pre-identity state
    (every consumer installed before the field existed) and is trusted, so
    this check adds no new failure mode for the population it is not about.
    Only a contract that names a *different* bundle diverts.
    """
    shared = installed_shared_dir()
    identity = installed_bundle_identity(shared)

    if identity is not None and identity != BUNDLE_IDENTITY:
        if target_root is None:
            raise RuntimeError(
                "installed .claude/skills/_shared/ belongs to "
                f"'{identity}', not '{BUNDLE_IDENTITY}', and no target_root "
                "was given to clone a trustworthy copy into"
            )
        note = (
            f"installed .claude/skills/_shared/ belongs to '{identity}', not "
            f"'{BUNDLE_IDENTITY}' - helpers loaded from the freshly-cloned "
            "bundle instead; the installed copy was not trusted"
        )
        prefetched = _bootstrap_clone(pathlib.Path(target_root), ref)
        clone_shared = prefetched / ".claude" / "skills" / "_shared"
        sys.path.insert(0, str(clone_shared))
        import bundle_copy  # noqa: E402
        import bundle_fetch  # noqa: E402
        import claude_md_block  # noqa: E402

        return bundle_copy, bundle_fetch, claude_md_block, prefetched, note

    sys.path.insert(0, str(shared))
    import bundle_copy  # noqa: E402
    import bundle_fetch  # noqa: E402
    import claude_md_block  # noqa: E402

    return bundle_copy, bundle_fetch, claude_md_block, None, None


# PLAN-AK6 D7: the ordered step names an in-flight sync appends to as it
# clears each boundary. The exception handler's `failed_step` is the first
# entry not yet in `steps_completed`, so this order must match the order the
# steps actually run in below.
_SYNC_STEPS_IN_ORDER = (
    "copy",
    "conflicts",
    "quarantine",
    "settings_merge",
    "gitignore",
    "gitattributes",
    "hooks_path",
    "claude_md",
    "receipt",
    "version_pin",
)


def _reexec_supported(clone_sync_path: pathlib.Path) -> bool:
    """True only when the clone's own sync.py, run with --help, exits zero
    and its stdout names both handover flags (PLAN-AK6 D3).

    The parent is old code invoking new code, so the calling convention has
    to be one the parent can verify before it relies on it - a --ref older
    than this PLAN has never heard of --prefetched-bundle or --no-reexec,
    and argparse would exit non-zero on the unknown flag. --help touches
    nothing and exists on every past ref. Any exception (missing file,
    non-executable, timeout) returns False - the fall-back floor for a
    clone predating the handover mechanism.
    """
    try:
        res = subprocess.run(
            [sys.executable, str(clone_sync_path), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return False
    if res.returncode != 0:
        return False
    return "--prefetched-bundle" in res.stdout and "--no-reexec" in res.stdout


def _reexec(
    clone_sync_path: pathlib.Path,
    target_root: pathlib.Path,
    ref: str,
    allow_in_flight: bool,
    prefetched_bundle: pathlib.Path,
    force_overwrite_diverged: bool = False,
) -> Optional[dict]:
    """Run the cloned bundle's own sync.py as a child process (PLAN-AK6 D2),
    handing it the clone already on disk (--prefetched-bundle) so it does
    not fetch a second time, and --no-reexec so it does not hand over again.

    Parses the child's stdout as the wire-format JSON result and returns it.
    Returns None when the child exits non-zero, its stdout does not parse,
    or the parsed value is not a dict carrying an "outcome" key - any of
    which means the handover did not produce a usable result, and the
    caller treats that as "nothing in the target was written" rather than
    falling back into the (potentially skewed) in-process path.

    `force_overwrite_diverged` (PLAN-AK5) is appended to the child's argv
    only when true, exactly as --allow-in-flight already is - a clone
    predating the flag would otherwise fail argparse on an unknown option.
    """
    args = [
        sys.executable,
        str(clone_sync_path),
        "--target-root",
        str(target_root),
        "--ref",
        ref,
        "--prefetched-bundle",
        str(prefetched_bundle),
        "--no-reexec",
    ]
    if allow_in_flight:
        args.append("--allow-in-flight")
    if force_overwrite_diverged:
        args.append("--force-overwrite-diverged")
    try:
        res = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return None
    if res.returncode != 0:
        return None
    try:
        parsed = json.loads(res.stdout)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict) or "outcome" not in parsed:
        return None
    return parsed


def compute_preflight_verdict(
    bundle_path: pathlib.Path,
    target_claude: pathlib.Path,
    target_root: pathlib.Path,
):
    """Import `preflight` from the freshly-cloned bundle's _shared/ (NOT
    the target's installed copy, which may predate this helper) under an
    ImportError guard, and compute the version-step verdict plus what the
    deprecation-ledger read (build_file_kind_ledger, below) needs from it.

    Returns (verdict, in_flight_plans, read_deprecations_fn,
    ledger_unavailable_reason).

    `verdict` is one of "same", "minor_step", "major_step",
    "pin_predates_contract", "unavailable" - see
    preflight.compare_against_clone's own docstring. `in_flight_plans` is
    populated only when `verdict` is "major_step". `read_deprecations_fn`
    is None, and `ledger_unavailable_reason` names why, in either of two
    cases: the clone predates the preflight helper entirely (ImportError
    on a --ref older than PLAN-AH8), or the clone's preflight predates
    read_deprecations (present module, absent attribute, a --ref between
    PLAN-AH8 and PLAN-AH9). Neither case raises.

    This is the wiring workflows/sync.md's Step 2b calls rather than
    reproducing (PLAN-AL8 D1) - the earlier inline copy in that file had
    drifted from this one, missing the ImportError guard and the
    pre-bound sentinel below.
    """
    bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
    if str(bundle_shared) not in sys.path:
        sys.path.insert(0, str(bundle_shared))
    verdict = "unavailable"
    in_flight_plans: list = []
    # PLAN-AH9 Step 5: bind the sentinel BEFORE the try, so the name always
    # exists in scope regardless of which branch runs. Two distinct
    # consumer cases hit this block: a --ref predating AH8 has no preflight
    # module in the clone at all (import preflight raises ImportError, and
    # because preflight was never bound, any later reference - including a
    # getattr(preflight, ...) guard - would raise NameError, not
    # AttributeError, if the sentinel were not pre-bound); a --ref between
    # AH8 and AH9 has preflight present but no read_deprecations attribute
    # (resolved via getattr below, not a widened except clause - see
    # preflight.py's own module docstring for why AttributeError must not
    # be caught here).
    preflight = None
    ledger_unavailable_reason: Optional[str] = None
    try:
        import preflight  # noqa: E402
    except ImportError:
        # Bundle predates the preflight helper - skip gracefully, do not
        # crash a sync.
        ledger_unavailable_reason = "preflight module absent (ref predates AH8)"

    if preflight is not None:
        verdict = preflight.compare_against_clone(target_claude, bundle_path)
        if verdict == "major_step":
            in_flight_plans = preflight.scan_in_flight_plans(target_root)

    # PLAN-AH9 Step 5 (second case): preflight present, read_deprecations
    # absent - a --ref between AH8 and AH9. getattr guards the attribute,
    # never a widened except AttributeError clause.
    read_deprecations_fn = (
        getattr(preflight, "read_deprecations", None) if preflight is not None else None
    )
    if read_deprecations_fn is None and ledger_unavailable_reason is None:
        ledger_unavailable_reason = (
            "preflight present, read_deprecations absent (ref between AH8 and AH9)"
        )
    return verdict, in_flight_plans, read_deprecations_fn, ledger_unavailable_reason


def build_file_kind_ledger(bundle_path: pathlib.Path, read_deprecations_fn) -> dict:
    """Read the deprecation ledger via `read_deprecations_fn` (the
    callable compute_preflight_verdict returns, or None when the clone
    predates it) and filter it to file-path-addressed entries only
    (kind: skill | reference | hook). A kind: helper entry's path is a
    file.py::symbol string that can never equal a quarantined file path,
    so it is never offered to a caller matching against on-disk paths.

    Returns {} when read_deprecations_fn is None or raises. Never raises.

    This is the read workflows/sync.md's Step 3a calls rather than
    reproducing (PLAN-AL8 D1).
    """
    ledger = []
    if read_deprecations_fn is not None:
        try:
            ledger = read_deprecations_fn(bundle_path) or []
        except Exception:
            ledger = []
    return {
        e["path"]: e
        for e in ledger
        if isinstance(e, dict) and e.get("kind") in ("skill", "reference", "hook")
    }


def sync(
    target_root: pathlib.Path,
    ref: str = "main",
    allow_in_flight: bool = False,
    prefetched_bundle: pathlib.Path = None,
    no_reexec: bool = False,
    force_overwrite_diverged: bool = False,
) -> dict:
    result: dict = {
        "outcome": "exception",
        "payload": {},
        "summary": "",
        "diagnostics": [],
    }

    target_claude = target_root / ".claude"
    if not target_claude.exists():
        result["summary"] = (
            f"{target_claude} does not exist - run /init-plan-foundry first."
        )
        return result
    if target_claude.is_symlink():
        result["summary"] = (
            f"{target_claude} is a symlink (legacy AC3 install) - "
            "run /init-plan-foundry to migrate this project."
        )
        return result

    try:
        (
            bundle_copy,
            bundle_fetch,
            claude_md_block,
            bootstrap_clone,
            identity_note,
        ) = _import_local_helpers(target_root, ref)
    except RuntimeError as exc:
        result["summary"] = f"could not fetch bundle: {exc}"
        result["diagnostics"].append({"step": "bootstrap-clone", "error": str(exc)})
        return result

    if identity_note:
        result["diagnostics"].append(f"bundle identity: {identity_note}")

    previous = bundle_copy.read_version_file(target_claude)
    if previous is None:
        if prefetched_bundle is not None or bootstrap_clone is not None:
            bundle_fetch.cleanup_tmp(target_root)
        result["summary"] = (
            f"{target_claude}/.plan-foundry-bundle-version is absent - "
            "run /init-plan-foundry first to record an initial pin."
        )
        return result
    previous_sha = previous.get("sha", "")

    # PLAN-AK6: report a marker left by an earlier, unfinished run. Never
    # blocks - the repair for an incomplete sync is another sync (D5).
    previous_run_incomplete = bundle_copy.read_sync_incomplete(target_claude)
    if previous_run_incomplete is not None:
        result["diagnostics"].append(
            "a previous sync was moving to "
            f"{previous_run_incomplete.get('target_sha', '')} (started "
            f"{previous_run_incomplete.get('started', '')}) and did not finish"
        )

    # PLAN-AH7 Step 1 (load-bearing ordering invariant): the receipt MUST be
    # read here, before the clone, alongside the existing pin read above -
    # never after the copy. See bundle_copy.py's module docstring for why.
    # PLAN-AK5: namespaced by bundle identity, with the legacy-adoption
    # fallback bundle_copy.read_receipt itself implements.
    receipt = bundle_copy.read_receipt(target_claude, bundle=BUNDLE_IDENTITY)
    ownership_unverified: Optional[str] = None
    if receipt is None:
        namespaced_path = bundle_copy.receipt_path(target_claude, BUNDLE_IDENTITY)
        legacy_path = target_claude / bundle_copy.RECEIPT_FILENAME
        if not namespaced_path.exists() and not legacy_path.exists():
            ownership_unverified = (
                "no install receipt found (namespaced or legacy) - every "
                "write proceeded unverified this run"
            )
        else:
            ownership_unverified = (
                "a legacy receipt at the shared path did not match this "
                "bundle's version pin, so it was not adopted - every write "
                "proceeded unverified this run"
            )

    if prefetched_bundle is not None:
        # Handed to us by a parent process's handover (PLAN-AK6 D2) - do not
        # clone again, and do not fall back to the identity-mismatch
        # bootstrap clone below either; a caller that supplies this already
        # holds the clone the whole run should use.
        bundle_path = prefetched_bundle
    elif bootstrap_clone is not None:
        # _import_local_helpers already cloned, to get trustworthy helpers.
        # Re-cloning here would throw that clone away and fetch the same ref
        # a second time.
        bundle_path = bootstrap_clone
    else:
        try:
            bundle_path = bundle_fetch.clone_bundle(target_root, ref=ref)
        except bundle_fetch.BundleFetchError as exc:
            result["summary"] = f"could not fetch bundle: {exc}"
            result["diagnostics"].append({"step": "clone", "error": str(exc)})
            return result

    # PLAN-AK6 D2/D3: hand over to the freshly-cloned bundle's own sync.py
    # before anything in the target is touched, so one generation of code
    # performs the whole run. Strictly before the pre-flight block below -
    # on the supported branch the child re-runs pre-flight itself, as the
    # generation that should own the verdict, so running it twice here would
    # be redundant rather than merely early.
    if not no_reexec:
        clone_sync = (
            bundle_path
            / ".claude"
            / "skills"
            / "plan-foundry-sync"
            / "lib"
            / "sync.py"
        )
        if _reexec_supported(clone_sync):
            reexec_result = _reexec(
                clone_sync,
                target_root,
                ref,
                allow_in_flight,
                bundle_path,
                force_overwrite_diverged=force_overwrite_diverged,
            )
            if reexec_result is not None:
                reexec_result.setdefault("diagnostics", [])
                reexec_result["diagnostics"].insert(
                    0,
                    "handover: ran the cloned bundle's own sync.py at "
                    f"{clone_sync.as_posix()}",
                )
                return reexec_result
            bundle_fetch.cleanup_tmp(target_root)
            result["outcome"] = "exception"
            result["summary"] = (
                "handover to the cloned bundle's sync.py failed before "
                "anything in the target was written"
            )
            return result
        result["diagnostics"].append(
            "handover: cloned bundle predates the handover mechanism - "
            "continuing in process; helper version skew between the "
            "installed helpers and the clone is possible on this run"
        )

    # PLAN-AH8 guarantee 2: the in-flight pre-flight, wired after the clone
    # and before copy_bundle_managed. compute_preflight_verdict (defined
    # above) carries the ImportError guard and the pre-bound sentinel;
    # PLAN-AL8 factored it out of this function so workflows/sync.md's
    # Step 2b calls the same code instead of reproducing it.
    (
        preflight_verdict,
        in_flight_plans,
        read_deprecations_fn,
        ledger_unavailable_reason,
    ) = compute_preflight_verdict(bundle_path, target_claude, target_root)

    if preflight_verdict == "major_step" and in_flight_plans and not allow_in_flight:
        # A deliberate refusal to proceed is not a crash - this is a third
        # outcome value, "blocked", distinct from "exception". Consumer-
        # visible contract change, declared in workflows/sync.md's
        # Reporting block and plan-foundry-sync/SKILL.md.
        bundle_fetch.cleanup_tmp(target_root)
        result["outcome"] = "blocked"
        result["payload"] = {
            "in_flight_plans": in_flight_plans,
            "blocked_reason": (
                "sync crosses a major version step (pin vs. the cloned "
                "bundle) while PLAN(s) are in flight"
            ),
        }
        result["diagnostics"].append(
            f"preflight: version_step=major_step in_flight={in_flight_plans}"
        )
        result["summary"] = (
            f"sync blocked: major version step with {len(in_flight_plans)} "
            "PLAN(s) in flight - re-run with --allow-in-flight to override"
        )
        return result

    result["diagnostics"].append(
        f"preflight: version_step={preflight_verdict} in_flight={in_flight_plans} "
        f"allow_in_flight={allow_in_flight}"
    )

    # Initialise settings_report and cmd variables before the try block so they
    # are always defined even if an exception occurs partway through.
    settings_report: dict = {}
    ga_status, ga_added = "SKIPPED", []
    hp_status, hp_note = "SKIPPED", "not attempted"
    cmd_status, cmd_note = "SKIPPED", "not reached"
    # PLAN-AK5: bound before the try block, alongside cmd_status/cmd_note,
    # for the same reason - the payload is assembled after the try and
    # outside the reach of its except clause, so an unbound name here would
    # escape sync() as a bare traceback instead of the JSON result this
    # module guarantees, including on the "operating-rules.md absent in
    # bundle" branch, which reaches this point without raising.
    change_status, removed_lines, added_lines = "unavailable", [], []
    gi_status, gi_added, gi_skipped_tracked = "SKIPPED", [], []
    # PLAN-AK6 D7: steps_completed and new must both be bound before the try
    # they are read from. `new` is what the except clause below reads
    # target_sha from - an exception raised before resolve_version() returns
    # would otherwise raise NameError out of the one path that exists to
    # stop a bare traceback reaching the consumer.
    steps_completed: list = []
    new: dict = {"sha": "", "tag": "", "synced": "", "schema_version": ""}
    quarantine_report: dict = {
        "receipt_absent": receipt is None,
        "gone_upstream_quarantined": [],
        "modified_since_install_preserved": [],
        "consumer_owned_preserved": [],
        "swept": [],
        "legacy_orphans_quarantined": [],
    }
    dangling_hook_registrations: list = []
    dangling_hook_registrations_local: list = []
    dangling_hook_entries_removed: list = []

    try:
        # PLAN-AK6 D4/D5: resolve the pin's data now (read-only), and mark
        # the run incomplete as the first write to the target - before
        # copy_bundle_managed, which is itself the first write of the old
        # ordering. The pin write itself moves to the end of this block.
        new = bundle_copy.resolve_version(bundle_path)
        bundle_copy.mark_sync_incomplete(target_claude, previous_sha, new["sha"])

        contract = bundle_copy.read_bundle_contract(bundle_path)
        report = bundle_copy.copy_bundle_managed(
            bundle_path / ".claude",
            target_claude,
            deprecations=contract.get("deprecations", []),
            receipt=receipt,
            force=force_overwrite_diverged,
        )
        steps_completed.append("copy")

        # PLAN-AK5 D7: write the standing conflicts file on every run, right
        # after the copy and before quarantine, so a run that raises later
        # still leaves a current conflicts file rather than the previous
        # run's. One refused path per line, sorted; written empty (not left
        # stale) when there are no refusals this run. Never deletes the file
        # - it self-clears by being rewritten empty.
        conflicts_path = bundle_copy.receipt_path(
            target_claude, BUNDLE_IDENTITY
        ).parent / f"{BUNDLE_IDENTITY}.conflicts"
        conflicts_path.parent.mkdir(parents=True, exist_ok=True)
        conflicts_tmp = conflicts_path.with_suffix(conflicts_path.suffix + ".tmp")
        conflicts_body = "\n".join(sorted(report.refused_not_ours))
        if conflicts_body:
            conflicts_body += "\n"
        conflicts_tmp.write_text(conflicts_body, encoding="utf-8")
        os.replace(conflicts_tmp, conflicts_path)
        steps_completed.append("conflicts")

        # Legacy orphan excision, computed before classify_stale so its
        # closed list of paths is excluded from the ordinary consumer_owned/
        # unknown classification below - these are positively identified,
        # not guessed at, so they must not also show up as "never touched".
        legacy_orphans = _legacy_orphan_relpaths(target_claude)

        # PLAN-AH7 Steps 6-10: classify -> quarantine -> sweep, strictly after
        # the copy and strictly before the receipt write at the end of this
        # try block (see the ordering invariant recorded above and in
        # bundle_copy.py's module docstring).
        bundle_files = set(report.files_copied) | set(report.files_unchanged)
        target_files = (
            bundle_files
            | set(report.project_additions)
            | set(report.stale_in_target)
        ) - set(legacy_orphans)
        classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)

        if receipt is None:
            quarantine_report["reason"] = (
                "no install receipt - nothing quarantined; a receipt is "
                "written by this sync and the next sync can act"
            )

        # PLAN-AH9 Step 5: the deprecation ledger, filtered to file-path-
        # addressed entries (kind: skill | reference | hook) before
        # matching. build_file_kind_ledger (defined above) is the same
        # function workflows/sync.md's Step 3a calls (PLAN-AL8 D1).
        file_kind_ledger = build_file_kind_ledger(bundle_path, read_deprecations_fn)
        quarantine_report["ledger_unavailable"] = ledger_unavailable_reason

        receipt_files = receipt.get("files", {}) if receipt else {}
        quarantine_details = []
        no_longer_ours = []
        to_quarantine = []
        for rel in classification.gone_upstream:
            src = target_claude / rel
            try:
                on_disk_hash = bundle_copy._file_sha256(src)
            except OSError:
                on_disk_hash = None
            recorded_hash = receipt_files.get(rel)
            modified = bool(
                on_disk_hash is not None
                and recorded_hash is not None
                and on_disk_hash != recorded_hash
            )
            detail = {
                "path": rel,
                "sha256": on_disk_hash,
                "modified_since_install": modified,
            }
            ledger_entry = file_kind_ledger.get(rel)
            if ledger_entry is not None:
                # Guarantee 4's acceptance coverage: a quarantined path
                # carrying a ledger entry reports replaced_by and note,
                # not a bare path.
                detail["replaced_by"] = ledger_entry.get("replaced_by", "")
                detail["note"] = ledger_entry.get("note", "")
            if modified:
                # The receipt says we installed this path; the bytes on disk
                # say what is there now is not what we wrote. Something else
                # owns it - a sibling bundle that ships the same path, or the
                # consumer's own edit - and moving it out would be taking
                # someone else's live file. Report it and leave it. This is
                # the case that made a sibling bundle's helpers disappear
                # into .claude/.plan-foundry-quarantine/ when the two bundles
                # overlapped on a path plan_foundry had since dropped.
                no_longer_ours.append(detail)
            else:
                quarantine_details.append(detail)
                to_quarantine.append(rel)
        # PLAN-AK8: the hook-path subset of to_quarantine, computed once
        # here (before both the diagnostic block below and the settings.json
        # strip further down) so neither recomputes the same filter. This is
        # the receipt-verified ownership signal that generalises the strip
        # beyond the closed legacy list: a hook the consumer added
        # themselves never appears in the receipt and never reaches
        # to_quarantine, so it is never a candidate here.
        hook_paths_to_strip = tuple(
            sorted(rel for rel in to_quarantine if rel.startswith("hooks/"))
        )

        # quarantine() is called with gone_upstream ONLY - never touches
        # consumer_owned - and now only the subset still byte-identical to
        # what the receipt records. Calls no delete primitive (shutil.move
        # only).
        bundle_copy.quarantine(target_claude, to_quarantine)
        quarantine_report["gone_upstream_quarantined"] = quarantine_details
        quarantine_report["modified_since_install_preserved"] = no_longer_ours
        quarantine_report["consumer_owned_preserved"] = classification.consumer_owned
        quarantine_report["unknown"] = classification.unknown

        # Legacy orphan excision (see LEGACY_ORPHAN_DIRS/FILES above): move
        # the closed list of positively-identified paths out, same
        # non-destructive quarantine() primitive as every other removal in
        # this module. No-op when none are present - a target that never
        # had them, or one already cleaned up by hand, contributes [].
        quarantine_report["legacy_orphans_quarantined"] = bundle_copy.quarantine(
            target_claude, legacy_orphans
        )
        _prune_empty_legacy_dirs(target_claude)

        # PLAN-AH9 Step 6: dangling hook registrations. .claude/settings.json
        # registers hooks by path and the settings merge below only adds
        # entries, so quarantining a dropped hook leaves a registration
        # pointing at a moved file, which errors on every tool call. Loud
        # rather than silent - a diagnostic, not a halt.
        dangling_hook_registrations = []
        target_settings_path = target_root / ".claude" / "settings.json"
        if target_settings_path.exists():
            try:
                settings_text = target_settings_path.read_text(encoding="utf-8")
            except OSError:
                settings_text = ""
            for rel in hook_paths_to_strip:
                if rel in settings_text:
                    dangling_hook_registrations.append(rel)

        # sweep_quarantine is the only function permitted to delete, and only
        # whole aged (>=30 day) quarantine directories.
        quarantine_report["swept"] = bundle_copy.sweep_quarantine(target_claude)
        steps_completed.append("quarantine")

        # Merge bundle settings fragment into target settings.json.
        # Load merge_settings from the freshly-cloned bundle's _shared/ (NOT
        # _import_local_helpers which resolves from the target's installed copy
        # and would fail ImportError on any pre-AH2 consumer that lacks the helper).
        bundle_shared = bundle_path / ".claude" / "skills" / "_shared"
        if str(bundle_shared) not in sys.path:
            sys.path.insert(0, str(bundle_shared))
        import merge_settings  # noqa: E402

        fragment_path = bundle_shared / "bundle-settings.json"
        target_settings = target_root / ".claude" / "settings.json"
        settings_report = merge_settings.merge_bundle_settings(target_settings, fragment_path)

        # Dangling hook registration strip, settings.json half (PLAN-AK8):
        # strip any hook entry still registered against either the closed
        # legacy-orphan marker list (LEGACY_ORPHAN_HOOK_MARKERS - regardless
        # of whether the script itself was found on disk this run, since a
        # human may already have deleted the files by hand but left the
        # registration behind) or any hook this run's ordinary
        # classify_stale/to_quarantine path just quarantined
        # (hook_paths_to_strip, computed above, receipt-verified so a
        # consumer-added hook is never touched). Runs every sync; idempotent;
        # a no-op once removed.
        dangling_hook_entries_removed = _strip_dangling_hook_commands(
            target_root, LEGACY_ORPHAN_HOOK_MARKERS + hook_paths_to_strip
        )

        # PLAN-AK8 D2: read-only detection of the same marker set against
        # .claude/settings.local.json. Sync is contractually forbidden to
        # WRITE this file (operating-rules.md: "never touched by sync"), but
        # a passive read for diagnostic purposes does not cross that
        # boundary - and this is exactly where the report's own incident
        # registration lived. Never repaired here; the diagnostics line
        # below tells the consumer why and that a session restart is needed
        # once they remove the entry by hand.
        dangling_hook_registrations_local = []
        target_settings_local_path = target_root / ".claude" / "settings.local.json"
        if target_settings_local_path.exists():
            try:
                settings_local_text = target_settings_local_path.read_text(
                    encoding="utf-8"
                )
            except OSError:
                settings_local_text = ""
            for marker in LEGACY_ORPHAN_HOOK_MARKERS + hook_paths_to_strip:
                if marker in settings_local_text:
                    dangling_hook_registrations_local.append(marker)

        steps_completed.append("settings_merge")

        # PLAN-AH7 Step 12: gitignore convergence for the two new paths this
        # PLAN adds (.plan-foundry-bundle-files, .plan-foundry-quarantine/).
        # Imported from the freshly-cloned bundle's _shared/ (now on sys.path
        # via bundle_shared above) under an ImportError guard, same pattern
        # as gitattributes_pin below - init-only is not sufficient, every
        # already-installed consumer needs this too.
        try:
            import gitignore_entries  # noqa: E402

            gi_status, gi_added, gi_skipped_tracked = (
                gitignore_entries.ensure_gitignore_entries(target_root)
            )
        except ImportError:
            gi_status, gi_added, gi_skipped_tracked = "SKIPPED", [], []
        steps_completed.append("gitignore")

        # Pin LF endings for hooks and shell scripts in the consumer repo.
        # Sync is the path by which the commit-msg hook actually arrives, so a
        # consumer who installed before the pin existed converges here rather
        # than only on a fresh install. Imported from the bundle for the same
        # reason as merge_settings: a pre-AH2 consumer has no local copy.
        try:
            import gitattributes_pin  # noqa: E402

            ga_status, ga_added = gitattributes_pin.ensure_gitattributes_pin(target_root)
        except ImportError:
            # Bundle predates the helper - skip gracefully, do not crash a sync.
            ga_status, ga_added = "SKIPPED", []
        steps_completed.append("gitattributes")

        # Wire core.hooksPath (D10). Ordered strictly after the pin above: a
        # hook wired before its line endings are guaranteed is a hook that
        # fails silently on Windows. Narrows D10's accepted weakness, since a
        # contributor who clones and syncs converges without re-running init.
        try:
            import hooks_path  # noqa: E402

            hp_status, hp_note = hooks_path.ensure_hooks_path(target_root)
        except ImportError:
            hp_status, hp_note = "SKIPPED", "bundle predates hooks_path helper"
        steps_completed.append("hooks_path")

        # Refresh the CLAUDE.md operating-rules block from the bundle.
        # Must be done inside the try block (before cleanup_tmp) while the bundle still exists.
        operating_rules_path = (
            bundle_path / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
        )
        try:
            operating_rules = operating_rules_path.read_text(encoding="utf-8")
            # PLAN-AK5: report a non-additive sentinel-block change before
            # applying it, while the clone is still on disk. Resolved via
            # getattr, not a direct attribute access - a refused write to
            # _shared/claude_md_block.py (this PLAN's own new divergence
            # check) can now leave an installed copy that predates this
            # function, and the module docstring's precedent for this
            # resolution style is preflight.read_deprecations above.
            block_change_report_fn = getattr(
                claude_md_block, "block_change_report", None
            )
            if block_change_report_fn is not None:
                block_report = block_change_report_fn(target_root, operating_rules)
                change_status = block_report.get("status", "unavailable")
                removed_lines = block_report.get("removed_lines", [])
                added_lines = block_report.get("added_lines", [])
            cmd_status, cmd_note = claude_md_block.apply_operating_rules_block(
                target_root, operating_rules
            )
        except OSError:
            # operating-rules.md absent in an old bundle - skip gracefully, do not crash.
            cmd_status, cmd_note = "SKIPPED", "operating-rules.md absent in bundle"
        steps_completed.append("claude_md")

        # PLAN-AH7 Step 5 (load-bearing ordering invariant): write the
        # receipt after classify/quarantine/sweep above, never immediately
        # after the copy. Records everything now installed (copied +
        # already-unchanged), so the next sync's read_receipt call can
        # distinguish "we installed this" from "the consumer added this".
        # PLAN-AK6 D4: the receipt is written last except for the version
        # pin, which now follows it - every step above is what makes the
        # pin's claim true, so a failure inside write_receipt must also
        # leave the pin honest.
        bundle_copy.write_receipt(
            target_claude,
            report.files_copied + report.files_unchanged,
            new["sha"],
            bundle=BUNDLE_IDENTITY,
        )
        steps_completed.append("receipt")

        bundle_copy.write_version_file(bundle_path, target_claude, data=new)
        steps_completed.append("version_pin")
        bundle_copy.clear_sync_incomplete(target_claude)
    except Exception as exc:
        failed_step = "unknown"
        for name in _SYNC_STEPS_IN_ORDER:
            if name not in steps_completed:
                failed_step = name
                break
        result["outcome"] = "exception"
        result["payload"] = {
            "steps_completed": steps_completed,
            "partially_applied": True,
            "failed_step": failed_step,
            "previous_sha": previous_sha,
            "target_sha": new.get("sha", ""),
            "incomplete_marker": (
                target_claude / bundle_copy.SYNC_INCOMPLETE_FILENAME
            ).as_posix(),
            "previous_run_incomplete": previous_run_incomplete,
        }
        result["diagnostics"].append(f"{type(exc).__name__}: {exc}")
        result["summary"] = (
            f"sync stopped part-way at step '{failed_step}' - the version "
            "pin was not advanced and the target is partially applied; "
            f"a marker at {result['payload']['incomplete_marker']} records "
            "it, and the repair is to run the sync again"
        )
        return result
    finally:
        bundle_fetch.cleanup_tmp(target_root)

    settings_status = "PASS" if settings_report.get("changed") else "SKIPPED"
    payload = {
        "ref": ref,
        "previous_sha": previous_sha,
        "new_sha": new["sha"],
        "tag": new["tag"],
        "synced": new["synced"],
        "files_copied": report.files_copied,
        "files_unchanged_count": len(report.files_unchanged),
        "project_additions": report.project_additions,
        "stale_in_target": report.stale_in_target,
        "refused_not_ours": report.refused_not_ours,
        "forced_overwrites": report.forced_overwrites,
        "ownership_unverified": ownership_unverified,
        "claude_md": {
            "status": cmd_status,
            "note": cmd_note,
            "change_status": change_status,
            "removed_lines": removed_lines,
            "added_lines": added_lines,
        },
        "settings_merge": {
            "status": settings_status,
            "entries_added": settings_report.get("entries_added", []),
            "entries_already_present": settings_report.get("entries_already_present", []),
        },
        "gitattributes": {"status": ga_status, "pins_added": ga_added},
        "hooks_path": {"status": hp_status, "note": hp_note},
        "gitignore_convergence": {
            "status": gi_status,
            "entries_added": gi_added,
            "entries_skipped_tracked": gi_skipped_tracked,
        },
        "shim_skipped": report.shim_skipped,
        "quarantine": quarantine_report,
        "dangling_hook_registrations": dangling_hook_registrations,
        "dangling_hook_registrations_local": dangling_hook_registrations_local,
        "dangling_hook_entries_removed": dangling_hook_entries_removed,
        "previous_run_incomplete": previous_run_incomplete,
    }
    short_prev = previous_sha[:8] if previous_sha else "(none)"
    short_new = new["sha"][:8] if new["sha"] else "(none)"
    result["diagnostics"].append(f"CLAUDE.md: {cmd_note}")
    result["diagnostics"].append(
        f"settings merge: {settings_status} "
        f"(added={settings_report.get('entries_added', [])}, "
        f"already_present={settings_report.get('entries_already_present', [])})"
    )
    result["diagnostics"].append(f"gitattributes: {ga_status} (pins_added={ga_added})")
    result["diagnostics"].append(f"hooks path: {hp_status} ({hp_note})")
    result["diagnostics"].append(
        f"gitignore convergence: {gi_status} (entries_added={gi_added}, "
        f"entries_skipped_tracked={gi_skipped_tracked})"
    )
    result["diagnostics"].append(
        f"quarantine: receipt_absent={quarantine_report['receipt_absent']} "
        f"gone_upstream={len(quarantine_report['gone_upstream_quarantined'])} "
        f"modified_since_install_preserved="
        f"{len(quarantine_report['modified_since_install_preserved'])} "
        f"consumer_owned_preserved={len(quarantine_report['consumer_owned_preserved'])} "
        f"swept={len(quarantine_report['swept'])} "
        f"legacy_orphans_quarantined={len(quarantine_report['legacy_orphans_quarantined'])} "
        f"ledger_unavailable={quarantine_report.get('ledger_unavailable')}"
    )
    if dangling_hook_registrations:
        result["diagnostics"].append(
            f"dangling hook registrations: {dangling_hook_registrations}"
        )
    if dangling_hook_registrations_local:
        result["diagnostics"].append(
            "dangling hook registrations found in .claude/settings.local.json "
            f"(sync cannot remove these - that file is never written by sync; "
            "remove the entry by hand and restart the session for the fix to "
            f"take effect): {dangling_hook_registrations_local}"
        )
    if dangling_hook_entries_removed:
        result["diagnostics"].append(
            f"dangling hook entries removed: {dangling_hook_entries_removed}"
        )
    if report.refused_not_ours:
        result["diagnostics"].append(
            "refused to overwrite (not ours - install is now mixed at these "
            f"paths): {report.refused_not_ours}"
        )
    if change_status == "non-additive":
        result["diagnostics"].append(
            f"CLAUDE.md sentinel block: non-additive - removed_lines={removed_lines}"
        )
    result["payload"] = payload
    result["summary"] = (
        f"synced {short_prev} -> {short_new} (ref={ref}): "
        f"{len(report.files_copied)} copied, "
        f"{len(report.files_unchanged)} unchanged, "
        f"{len(report.project_additions)} project additions preserved, "
        f"{len(report.stale_in_target)} stale"
        f", CLAUDE.md {cmd_status} ({cmd_note})"
        f", settings {settings_status}"
    )
    if report.refused_not_ours:
        result["summary"] += (
            f"; refused to overwrite {len(report.refused_not_ours)} path(s) "
            f"not written by this bundle: {report.refused_not_ours}"
        )
    if change_status == "non-additive":
        result["summary"] += "; CLAUDE.md sentinel block lost line(s) - see diagnostics"
    if cmd_status == "FAIL":
        result["outcome"] = "exception"
    else:
        result["outcome"] = "success"
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
        help="Target project root (default: current working directory).",
    )
    parser.add_argument(
        "--ref",
        default="main",
        help="Git ref to fetch - branch name, tag, or sha (default: main).",
    )
    parser.add_argument(
        "--allow-in-flight",
        action="store_true",
        default=False,
        help=(
            "Override the pre-flight halt on a major version step with "
            "in-flight PLANs (PLAN-AH8, outcome: blocked)."
        ),
    )
    parser.add_argument(
        "--prefetched-bundle",
        default=None,
        help=(
            "PLAN-AK6 handover: path to a bundle clone already on disk. "
            "When supplied, this run uses that path instead of cloning."
        ),
    )
    parser.add_argument(
        "--no-reexec",
        action="store_true",
        default=False,
        help=(
            "PLAN-AK6: run entirely in this process - never hand over to "
            "the cloned bundle's own sync.py. Set by the handover itself "
            "on the child it spawns, to guard against recursion."
        ),
    )
    parser.add_argument(
        "--force-overwrite-diverged",
        action="store_true",
        default=False,
        help=(
            "PLAN-AK5: overwrite a bundle-managed path this run judges 'not "
            "ours' (absent from the receipt, or diverged from its recorded "
            "sha256) instead of refusing it. Opt-in; never a default."
        ),
    )
    args = parser.parse_args(argv)
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else pathlib.Path.cwd().resolve()
    )
    prefetched_bundle = (
        pathlib.Path(args.prefetched_bundle).expanduser().resolve()
        if args.prefetched_bundle
        else None
    )
    result = sync(
        target_root,
        ref=args.ref,
        allow_in_flight=args.allow_in_flight,
        prefetched_bundle=prefetched_bundle,
        no_reexec=args.no_reexec,
        force_overwrite_diverged=args.force_overwrite_diverged,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
