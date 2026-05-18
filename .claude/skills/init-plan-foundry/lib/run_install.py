#!/usr/bin/env python3
"""
run_install.py — Non-interactive CLI for the init-plan-foundry procedure.

Invoked from the cloned bundle (typically `.plan-foundry-tmp/`) by the
BOOTSTRAP.md procedure on first-contact installs. Equivalent to running
the /init-plan-foundry skill inside an already-installed project.

Usage:
    python3 .plan-foundry-tmp/.claude/skills/init-plan-foundry/lib/run_install.py
    python3 <bundle>/.claude/skills/init-plan-foundry/lib/run_install.py --target-root /path

By default:
- BUNDLE_PATH is detected from this script's own location (walk up to find
  `.claude/skills/init-plan-foundry/lib/run_install.py` → bundle is 4 dirs up).
- TARGET_ROOT defaults to the parent of `.plan-foundry-tmp/` (i.e. the dir
  containing the temp clone). When the script is run from outside the
  conventional layout, pass `--target-root`.

Exits 0 on success, 1 on FAIL.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import re
import shutil
import stat
import subprocess
import sys

_THIS = pathlib.Path(__file__).resolve()


def _bundle_path_from_script() -> pathlib.Path:
    # .claude/skills/init-plan-foundry/lib/run_install.py → bundle is 4 parents up
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


def _step_copy(bundle_copy, bundle_path, target_claude):
    """Step 2: copy bundle-managed paths into target/.claude/."""
    if target_claude.is_symlink():
        resolved = os.readlink(target_claude)
        if "plan_foundry" in str(resolved):
            target_claude.unlink()
            target_claude.mkdir(parents=True)
            precursor = "symlink-legacy"
        else:
            return None, f"symlink-target-mismatch: {target_claude} → {resolved}"
    elif not target_claude.exists():
        target_claude.mkdir(parents=True)
        precursor = "absent"
    else:
        precursor = "real-dir"

    report = bundle_copy.copy_bundle_managed(bundle_path / ".claude", target_claude)
    version = bundle_copy.write_version_file(bundle_path, target_claude)
    return {"precursor": precursor, "report": report, "version": version}, ""


def _step_workbench(target_root: pathlib.Path) -> str:
    wb = target_root / "Workbench"
    if wb.exists():
        return "SKIPPED"
    wb.mkdir()
    (wb / ".gitkeep").write_text("", encoding="utf-8")
    return "PASS"


def _step_monthly_log(target_root: pathlib.Path) -> str:
    wb = target_root / "Workbench"
    yyyymm = datetime.datetime.now().strftime("%Y%m")
    pattern = re.compile(rf"_LOG_{yyyymm}\.md$")
    if any(pattern.search(p.name) for p in wb.glob("*.md") if p.is_file()):
        return "SKIPPED"
    now = datetime.datetime.now()
    stamp = now.strftime("%Y%m%d%H%M")
    iso_date = now.strftime("%Y-%m-%d")
    yyyy_mm = now.strftime("%Y-%m")
    month_name = now.strftime("%B %Y")
    body = f"""---
title: "Project Work Log — {month_name}"
type: log
month: {yyyy_mm}
status: open
created: {iso_date}
last_updated: {iso_date}
---

## Status Table

| Plan File | Title | Assigned | Priority | Status | Due |
|---|---|---|---|---|---|

## Recurring Task Tracker

| Task | Slug | Cadence | Last Done | Next Due | Status |
|---|---|---|---|---|---|

## Context Inputs This Month

| Input File | Type | From | Feeds Plan | Integrated? |
|---|---|---|---|---|

## Lessons Learned

_(none carried forward)_
"""
    (wb / f"{stamp}_LOG_{yyyymm}.md").write_text(body, encoding="utf-8")
    return "PASS"


def _step_retired(target_root: pathlib.Path) -> str:
    rt = target_root / "Retired"
    if rt.exists():
        return "SKIPPED"
    rt.mkdir()
    (rt / ".gitkeep").write_text("", encoding="utf-8")
    return "PASS"


REQUIRED_GITIGNORE_ENTRIES = (
    "Retired/",
    "Workbench/.heartbeat/",
    ".plan-foundry-tmp/",
    ".claude/skills/",
    ".claude/agents/",
    ".claude/commands/",
    ".claude/hooks/",
    ".claude/.plan-foundry-bundle-version",
    ".claude/_foundry_log.jsonl",
)


def _step_gitignore(target_root: pathlib.Path) -> tuple[str, list[str], bool]:
    gi = target_root / ".gitignore"
    existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
    lines = existing.splitlines()
    line_set = {ln.strip() for ln in lines}
    added: list[str] = []
    for entry in REQUIRED_GITIGNORE_ENTRIES:
        if entry not in line_set:
            lines.append(entry)
            added.append(entry)
    legacy_bare = any(ln.strip() in (".claude", ".claude/") for ln in lines)
    if added:
        gi.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return "PASS", added, legacy_bare
    return "SKIPPED", [], legacy_bare


SENTINEL_START = "<!-- plan-foundry:init-plan-foundry:start -->"
SENTINEL_END = "<!-- plan-foundry:init-plan-foundry:end -->"


def _step_claude_md(bundle_path: pathlib.Path, target_root: pathlib.Path) -> tuple[str, str]:
    operating_rules = (
        bundle_path
        / ".claude"
        / "skills"
        / "init-plan-foundry"
        / "operating-rules.md"
    ).read_text(encoding="utf-8")
    block = (
        f"{SENTINEL_START}\n"
        "<!-- WARNING: content between these markers is managed by the plan_foundry init-plan-foundry skill. "
        "Re-running the skill replaces everything between the markers with the current operating-rules.md "
        "from the bundle. Do not hand-edit between markers — edits will be lost on re-run. -->\n\n"
        f"{operating_rules}\n"
        f"{SENTINEL_END}\n"
    )
    claude_md = target_root / "CLAUDE.md"
    if not claude_md.exists():
        stub = (
            "# CLAUDE.md\n\n"
            "This file provides guidance to Claude Code when working with this repository.\n\n"
            f"{block}"
        )
        claude_md.write_text(stub, encoding="utf-8")
        return "PASS", "created"
    text = claude_md.read_text(encoding="utf-8")
    start_count = text.count(SENTINEL_START)
    end_count = text.count(SENTINEL_END)
    if start_count == 0 and end_count == 0:
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        claude_md.write_text(text + sep + block, encoding="utf-8")
        return "PASS", "appended-block"
    if start_count == 1 and end_count == 1:
        s = text.find(SENTINEL_START)
        e = text.find(SENTINEL_END)
        if e < s:
            return "FAIL", "markers malformed (end before start)"
        e_line_end = text.find("\n", e)
        if e_line_end == -1:
            e_line_end = len(text)
        new_text = text[:s] + block + text[e_line_end + 1 :]
        body_between = text[s + len(SENTINEL_START) : e].strip("\n")
        if body_between == operating_rules.strip("\n") or text[s:e_line_end + 1] == block:
            return "SKIPPED", "already current"
        claude_md.write_text(new_text, encoding="utf-8")
        return "PASS", "replaced-block"
    return "FAIL", f"markers malformed (start_count={start_count}, end_count={end_count})"


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
    step_results["step_0"] = "PASS"

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
    step_results["step_4"] = _step_monthly_log(target_root)
    step_results["step_5"] = _step_retired(target_root)
    gi_status, added, legacy = _step_gitignore(target_root)
    step_results["step_6"] = gi_status
    if added:
        diagnostics.append(f"gitignore added: {added}")
    if legacy:
        diagnostics.append("legacy bare .claude line in .gitignore — consider removing")
    cmd_status, cmd_note = _step_claude_md(bundle_path, target_root)
    step_results["step_7"] = cmd_status
    diagnostics.append(f"CLAUDE.md: {cmd_note}")

    # Step 8: tmp cleanup — only if bundle was the conventional tmp clone
    if bundle_path.name == ".plan-foundry-tmp" and bundle_path.exists():
        _force_rmtree(bundle_path)
        step_results["step_8"] = "PASS"
        diagnostics.append(f"cleaned up {bundle_path}")
    else:
        step_results["step_8"] = "SKIPPED"
        diagnostics.append("bundle is not at .plan-foundry-tmp/ — caller manages cleanup")

    step_results["step_9"] = "PASS"
    diagnostics.append(
        "RESTART Claude Code for project-local skills to register. After restart, "
        "/plan-foundry-sync, /plan-foundry-check-current, /plan-foundry-uninstall "
        "and the rest of the plan_foundry skill suite will be available."
    )

    has_fail = any(v == "FAIL" for v in step_results.values())
    summary = (
        f"plan_foundry installed (precursor={precursor}, sha={pinned_sha[:8]}) — "
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
