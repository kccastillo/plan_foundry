#!/usr/bin/env python3
"""
run_install.py - Non-interactive CLI for the init-plan-foundry procedure.

Invoked from the cloned bundle (typically `.plan-foundry-tmp/`) by the
BOOTSTRAP.md procedure on first-contact installs. Equivalent to running
the /init-plan-foundry skill inside an already-installed project.

Usage:
    python3 .plan-foundry-tmp/.claude/skills/init-plan-foundry/lib/run_install.py
    python3 <bundle>/.claude/skills/init-plan-foundry/lib/run_install.py --target-root /path

By default:
- BUNDLE_PATH is detected from this script's own location (walk up to find
  `.claude/skills/init-plan-foundry/lib/run_install.py` -> bundle is 4 dirs up).
- TARGET_ROOT defaults to the parent of `.plan-foundry-tmp/` (i.e. the dir
  containing the temp clone). When the script is run from outside the
  conventional layout, pass `--target-root`.

Exits 0 on success, 1 on FAIL.
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

_THIS = pathlib.Path(__file__).resolve()


def _bundle_path_from_script() -> pathlib.Path:
    # .claude/skills/init-plan-foundry/lib/run_install.py -> bundle is 4 parents up
    return _THIS.parents[4]


def _default_target_root() -> pathlib.Path:
    """If bundle is at <target>/.plan-foundry-tmp/, target = <target>.

    Otherwise fall back to cwd.
    """
    bp = _bundle_path_from_script()
    if bp.name == ".plan-foundry-tmp":
        return bp.parent
    return pathlib.Path.cwd()


def _load_helpers(bundle_path: pathlib.Path):
    shared = bundle_path / ".claude" / "skills" / "_shared"
    sys.path.insert(0, str(shared))
    import bundle_copy  # noqa: E402

    return bundle_copy


def _step_settings(bundle_path: pathlib.Path, target_root: pathlib.Path) -> dict:
    """Step: merge bundle-settings.json into target_root/.claude/settings.json.

    Loads merge_settings from the bundle's _shared/ (mirrors _load_helpers so
    the helper always comes from the freshly-cloned bundle, not a potentially
    stale target install). Returns a merge report dict including 'status' key
    ("PASS" or "SKIPPED") for step_results.
    """
    shared = bundle_path / ".claude" / "skills" / "_shared"
    if str(shared) not in sys.path:
        sys.path.insert(0, str(shared))
    import merge_settings  # noqa: E402

    fragment = shared / "bundle-settings.json"
    target_settings = target_root / ".claude" / "settings.json"
    report = merge_settings.merge_bundle_settings(target_settings, fragment)
    report["status"] = "PASS" if report.get("changed") else "SKIPPED"
    return report


def _force_rmtree(path: pathlib.Path) -> None:
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


def _is_bundle_source(target_root: pathlib.Path) -> tuple[bool, str]:
    if target_root.name in ("plan_foundry", "plan_foundry_dev"):
        return True, f"basename={target_root.name}"
    git_config = target_root / ".git" / "config"
    if git_config.exists():
        text = git_config.read_text(encoding="utf-8", errors="replace")
        for marker in ("kccastillo/plan_foundry_dev", "kccastillo/plan_foundry"):
            if marker in text:
                return True, f"origin contains {marker}"
    return False, ""


def _detect_foreign(target_root: pathlib.Path, bundle_path: pathlib.Path):
    """Second half of Step 0: refuse a target that owns bundle content.

    _is_bundle_source matches this bundle's own name, so a repo shipping a
    different bundle passes it. Fail-open on an import error - a missing
    helper must not block an ordinary install (PLAN-AJ6 D3).
    """
    try:
        from preflight import detect_foreign_bundle
    except ImportError:
        return None
    return detect_foreign_bundle(target_root, bundle_path)


def _step_copy(bundle_copy, bundle_path, target_claude):
    """Step 2: copy bundle-managed paths into target/.claude/."""
    if target_claude.is_symlink():
        resolved = os.readlink(target_claude)
        if "plan_foundry" in str(resolved):
            target_claude.unlink()
            target_claude.mkdir(parents=True)
            precursor = "symlink-legacy"
        else:
            return None, f"symlink-target-mismatch: {target_claude} -> {resolved}"
    elif not target_claude.exists():
        target_claude.mkdir(parents=True)
        precursor = "absent"
    else:
        precursor = "real-dir"

    contract = bundle_copy.read_bundle_contract(bundle_path)
    report = bundle_copy.copy_bundle_managed(
        bundle_path / ".claude",
        target_claude,
        deprecations=contract.get("deprecations", []),
    )
    version = bundle_copy.write_version_file(bundle_path, target_claude)
    # PLAN-AH7 Step 4: a fresh install has no prior state to classify against,
    # so the receipt is simply written after the copy here (unlike sync.py,
    # which must write it at the END of the read-receipt/clone/copy/classify/
    # quarantine/sweep sequence - see bundle_copy.py's module docstring).
    bundle_copy.write_receipt(
        target_claude,
        report.files_copied + report.files_unchanged,
        version.get("sha", ""),
        bundle="plan_foundry",
    )
    return {"precursor": precursor, "report": report, "version": version}, ""


def _step_workbench(target_root: pathlib.Path) -> str:
    wb = target_root / "Workbench"
    if wb.exists():
        return "SKIPPED"
    wb.mkdir()
    (wb / ".gitkeep").write_text("", encoding="utf-8")
    return "PASS"


def _step_retired(target_root: pathlib.Path) -> str:
    rt = target_root / "Retired"
    if rt.exists():
        return "SKIPPED"
    rt.mkdir()
    (rt / ".gitkeep").write_text("", encoding="utf-8")
    return "PASS"


# REQUIRED_GITIGNORE_ENTRIES moved to _shared/gitignore_entries.py (PLAN-AH7
# Step 11) - the single source of truth, shared with plan-foundry-uninstall.
# Per PLAN-AD0 D2-A (2026-05-22): Retired/ is intentionally NOT in that list. Retired
# artefacts (PLAN bodies, rolled-over LOGs) are tracked so that fresh clones, CI containers,
# and web/mobile Claude Code sessions see the full ID ledger and historical record.


def _step_gitignore(target_root: pathlib.Path) -> tuple[str, list[str], bool, list]:
    from gitignore_entries import ensure_gitignore_entries

    status, added, skipped_tracked = ensure_gitignore_entries(target_root)
    gi = target_root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    legacy_bare = any(
        ln.strip() in (".claude", ".claude/") for ln in existing.splitlines()
    )
    return status, added, legacy_bare, skipped_tracked


def _step_repo_presence(target_root: pathlib.Path) -> tuple[str, str]:
    """
    Advisory-only check: is target_root a git working tree (FOUNDRYREQ
    horse-chestnut-brickhouse-20260805-1707)?

    Deliberately a different rev-parse subcommand from _step_hooks_path's
    `--git-dir`: `--git-dir` succeeds inside a bare repository and inside
    `.git/` itself, where there is no working tree for a scaffolded
    Workbench/ to be committed from. `--is-inside-work-tree` is the correct
    predicate for "does a commit have somewhere to attach to".

    Returns (status, note):
      PASS    - target_root is inside a git working tree. The note also
                distinguishes a target that IS the repository root from one
                that is merely a subdirectory of an enclosing repository -
                both give commits somewhere to attach to, so both are PASS,
                but the operator can tell which situation they are in.
      SKIPPED - target has no git repository (or git is unavailable), or
                the differentiating --show-toplevel probe itself failed.
                Never FAIL: this check warns and continues, it never blocks
                bootstrap and never runs `git init` on the consumer's
                behalf (that is a separate, larger decision - see
                PLAN-AK9 D3).
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(target_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return (
            "SKIPPED",
            "target has no git repository (git unavailable or call failed) - "
            "commits, retire history and the durability pass have nothing to "
            "attach to",
        )

    if proc.returncode != 0 or proc.stdout.strip() != "true":
        return (
            "SKIPPED",
            "target has no git repository - commits, retire history and the "
            "durability pass have nothing to attach to",
        )

    note = "target is inside a git working tree"
    try:
        top_proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(target_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if top_proc.returncode == 0 and top_proc.stdout.strip():
            toplevel = pathlib.Path(top_proc.stdout.strip()).resolve()
            resolved_target = target_root.resolve()
            if toplevel != resolved_target:
                note = (
                    f"target is a subdirectory of an enclosing git working "
                    f"tree rooted at {toplevel} - commits made here land in "
                    f"that repository, not one of its own"
                )
    except (OSError, subprocess.SubprocessError):
        pass  # differentiation is diagnostic detail only, never a gate

    return "PASS", note


def _step_hooks_path(target_root: pathlib.Path) -> tuple[str, str]:
    """
    Point the consumer repo's `core.hooksPath` at `.claude/hooks` (PLAN-AD2 D10).

    Non-clobbering: a consumer who already set a hooks path of their own keeps
    it and the conflict is reported. Must run after _step_gitattributes.
    """
    from hooks_path import ensure_hooks_path

    return ensure_hooks_path(target_root)


def _step_gitattributes(target_root: pathlib.Path) -> tuple[str, list[str]]:
    """
    Pin LF endings for `.claude/hooks/**` and `*.sh` in the consumer repo.

    Modelled on _step_gitignore: append-only, non-clobbering, idempotent. The
    pin lines and the reasoning live in _shared/gitattributes_pin.py so that
    init and plan-foundry-sync cannot drift apart. Per
    FOUNDRYREQ-plan_foundry_dev-20260727-1350.
    """
    from gitattributes_pin import ensure_gitattributes_pin

    return ensure_gitattributes_pin(target_root)


# Sentinel constants are defined in _shared/claude_md_block.py (single source of truth).
# They are mirrored here so that any existing external reference (e.g. run_install.SENTINEL_START)
# continues to resolve without drift. The string literals must match claude_md_block.py verbatim.
SENTINEL_START = "<!-- plan-foundry:init-plan-foundry:start -->"
SENTINEL_END = "<!-- plan-foundry:init-plan-foundry:end -->"


def _step_claude_md(bundle_path: pathlib.Path, target_root: pathlib.Path) -> tuple[str, str]:
    # _shared is on sys.path after _load_helpers() (bundle's _shared).
    # Also ensure the script-local _shared (.claude/skills/_shared relative to this file)
    # is on sys.path so claude_md_block is importable from the installed location too.
    _script_shared = _THIS.parent.parent.parent / "_shared"
    if str(_script_shared) not in sys.path:
        sys.path.insert(0, str(_script_shared))
    import claude_md_block  # noqa: E402

    operating_rules = (
        bundle_path
        / ".claude"
        / "skills"
        / "init-plan-foundry"
        / "operating-rules.md"
    ).read_text(encoding="utf-8")
    return claude_md_block.apply_operating_rules_block(target_root, operating_rules)


def run(target_root: pathlib.Path, bundle_path: pathlib.Path) -> dict:
    step_results: dict = {}
    diagnostics: list[str] = []

    # Step 0
    is_src, reason = _is_bundle_source(target_root)
    if is_src:
        step_results["step_0"] = "FAIL"
        diagnostics.append(f"bundle-source-init-refused: {reason}")
        return {
            "outcome": "exception",
            "payload": {"step_results": step_results, "summary": "refused: bundle source"},
            "diagnostics": diagnostics,
        }
    foreign = _detect_foreign(target_root, bundle_path)
    if foreign:
        step_results["step_0"] = "FAIL"
        diagnostics.append(foreign)
        return {
            "outcome": "exception",
            "payload": {"step_results": step_results, "summary": "refused: foreign bundle"},
            "diagnostics": diagnostics,
        }
    step_results["step_0"] = "PASS"

    # Step 0b: repository-presence check (advisory only - never fails bootstrap)
    rp_status, rp_note = _step_repo_presence(target_root)
    step_results["step_0b"] = rp_status
    diagnostics.append(f"repository presence: {rp_note}")

    # Step 1 (clone) is the caller's responsibility under BOOTSTRAP.md procedure;
    # run_install.py uses the already-cloned bundle.
    if not (bundle_path / ".claude").exists():
        step_results["step_1"] = "FAIL"
        diagnostics.append(f"bundle path missing .claude/: {bundle_path}")
        return {
            "outcome": "exception",
            "payload": {"step_results": step_results, "summary": "bundle invalid"},
            "diagnostics": diagnostics,
        }
    step_results["step_1"] = "PASS"

    bundle_copy = _load_helpers(bundle_path)
    target_claude = target_root / ".claude"

    # Step 2
    res, err = _step_copy(bundle_copy, bundle_path, target_claude)
    if err:
        step_results["step_2"] = "FAIL"
        diagnostics.append(err)
        return {
            "outcome": "exception",
            "payload": {"step_results": step_results, "summary": err},
            "diagnostics": diagnostics,
        }
    step_results["step_2"] = "PASS"
    diagnostics.append(
        f"precursor={res['precursor']}, copied={len(res['report'].files_copied)}, "
        f"unchanged={len(res['report'].files_unchanged)}, "
        f"version sha={res['version']['sha'][:8]}"
    )
    pinned_sha = res["version"]["sha"]
    precursor = res["precursor"]

    # Steps 3-7
    step_results["step_3"] = _step_workbench(target_root)
    step_results["step_5"] = _step_retired(target_root)
    gi_status, added, legacy, gi_skipped = _step_gitignore(target_root)
    step_results["step_6"] = gi_status
    if added:
        diagnostics.append(f"gitignore added: {added}")
    if gi_skipped:
        diagnostics.append(
            "gitignore entries NOT added because git already tracks content "
            f"under them - the target owns these paths: {gi_skipped}"
        )
    if legacy:
        diagnostics.append("legacy bare .claude line in .gitignore - consider removing")
    ga_status, ga_added = _step_gitattributes(target_root)
    step_results["step_6b"] = ga_status
    if ga_added:
        diagnostics.append(f"gitattributes pinned: {ga_added}")
    # Step 6c MUST follow 6b: wiring hooks before the line-ending pin is in
    # place would ship a CRLF-mangled hook that fails on every Windows consumer
    # while exiting 0 on all paths, so broken and working look identical.
    hp_status, hp_note = _step_hooks_path(target_root)
    step_results["step_6c"] = hp_status
    diagnostics.append(f"hooks path: {hp_note}")
    cmd_status, cmd_note = _step_claude_md(bundle_path, target_root)
    step_results["step_7"] = cmd_status
    diagnostics.append(f"CLAUDE.md: {cmd_note}")

    # Step 7b: merge bundle settings into target settings.json
    settings_report = _step_settings(bundle_path, target_root)
    step_results["step_7b"] = settings_report["status"]
    diagnostics.append(
        f"settings merge: {settings_report['status']} "
        f"(added={settings_report.get('entries_added', [])}, "
        f"already_present={settings_report.get('entries_already_present', [])})"
    )

    # Step 8: tmp cleanup - only if bundle was the conventional tmp clone
    if bundle_path.name == ".plan-foundry-tmp" and bundle_path.exists():
        _force_rmtree(bundle_path)
        step_results["step_8"] = "PASS"
        diagnostics.append(f"cleaned up {bundle_path}")
    else:
        step_results["step_8"] = "SKIPPED"
        diagnostics.append("bundle is not at .plan-foundry-tmp/ - caller manages cleanup")

    step_results["step_9"] = "PASS"
    diagnostics.append(
        "RESTART Claude Code for project-local skills to register. After restart, "
        "/plan-foundry-sync, /plan-foundry-check-current, /plan-foundry-uninstall "
        "and the rest of the plan_foundry skill suite will be available."
    )

    has_fail = any(v == "FAIL" for v in step_results.values())
    summary = (
        f"plan_foundry installed (precursor={precursor}, sha={pinned_sha[:8]}) - "
        f"RESTART Claude Code"
    )
    return {
        "outcome": "exception" if has_fail else "success",
        "payload": {"step_results": step_results, "summary": summary},
        "diagnostics": diagnostics,
    }


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-root",
        default=None,
        help="Target project root (default: parent of .plan-foundry-tmp/, else cwd).",
    )
    parser.add_argument(
        "--bundle-path",
        default=None,
        help="Path to the cloned bundle (default: derived from this script's location).",
    )
    args = parser.parse_args(argv)
    bundle_path = (
        pathlib.Path(args.bundle_path).expanduser().resolve()
        if args.bundle_path
        else _bundle_path_from_script()
    )
    target_root = (
        pathlib.Path(args.target_root).expanduser().resolve()
        if args.target_root
        else _default_target_root()
    )
    result = run(target_root, bundle_path)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result["outcome"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
