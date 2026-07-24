#!/usr/bin/env python3
"""
regenerate_state.py — Single regeneration entrypoint for INDEX + Context Inputs.

Composes build_index and project_context_inputs so that keeping INDEX and the
LOG's Context Inputs table in sync is one action, not two (PLAN-AG5, D3 Option A
— check-only default).

Steps
-----
1. Regenerate INDEX.md + .index.json via build_index.build_index().
2. Check or reconcile the LOG's '## Context Inputs This Month' table via
   project_context_inputs.

Default behaviour (--check, D3 Option A)
    Regenerates INDEX (always a write; no authored content to lose).
    Runs the Context Inputs projector in check mode: reports dangling / missing
    rows and exits non-zero on drift, but does NOT touch the LOG.
    Use this as the standard pre-PR discipline: one command surfaces any lag.

Opt-in reconciliation (--write)
    Runs the Context Inputs projector in write mode: reconciles the LOG's
    Context Inputs table in place, preserving authored Advises and Notes cells
    on surviving rows and seeding Advises from frontmatter only on new rows.

Exit codes
----------
0   INDEX regenerated; Context Inputs table has no drift (--check) or was
    successfully reconciled (--write).
1   INDEX regenerated; Context Inputs drift detected (--check only).
    The LOG needs manual review or a --write pass.
2   Fatal error (INDEX regen failed or projector crashed).

Usage
-----
    python regenerate_state.py [workbench_dir] [--write]

    workbench_dir defaults to "Workbench" relative to the current working
    directory.
"""

import argparse
import sys
from pathlib import Path

# Both siblings live in the same scripts/ directory.
_SCRIPTS_DIR = Path(__file__).parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import build_index
import project_context_inputs


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Single regeneration entrypoint: refresh INDEX and check / "
            "reconcile the LOG's Context Inputs table in one command."
        )
    )
    parser.add_argument(
        "workbench_dir",
        nargs="?",
        default="Workbench",
        help="Path to the Workbench directory (default: Workbench)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=(
            "Reconcile the LOG Context Inputs table in place (default: "
            "check only per D3 Option A)"
        ),
    )
    args = parser.parse_args(argv)

    workbench = Path(args.workbench_dir).resolve()

    # -------------------------------------------------------------------------
    # Step 1: Regenerate INDEX.md + .index.json.
    # -------------------------------------------------------------------------
    try:
        build_index.build_index(workbench)
        print(f"INDEX regenerated from {workbench}.")
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: INDEX regeneration failed: {e}", file=sys.stderr)
        sys.exit(2)

    # -------------------------------------------------------------------------
    # Step 2: Context Inputs projection.
    # -------------------------------------------------------------------------
    try:
        log_path = project_context_inputs._locate_log(workbench)
    except FileNotFoundError as e:
        print(f"ERROR: Could not locate LOG file: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        if args.write:
            changed = project_context_inputs.render_write(log_path, workbench)
            if changed:
                print(
                    f"Context Inputs table reconciled in {log_path.name}."
                )
            else:
                print(
                    f"Context Inputs table already up to date in {log_path.name}."
                )
            sys.exit(0)
        else:
            # --check mode (default per D3 Option A).
            report = project_context_inputs.diff(log_path, workbench)
            dangling = report["dangling"]
            missing = report["missing"]
            if not dangling and not missing:
                print(
                    f"Context Inputs table in {log_path.name}: no drift detected."
                )
                sys.exit(0)
            else:
                print(
                    f"Context Inputs drift detected in {log_path.name} "
                    f"(dangling: {len(dangling)}, missing: {len(missing)}). "
                    f"Run with --write to reconcile."
                )
                if dangling:
                    print("  Dangling (in table, file not on disk):")
                    for name in dangling:
                        print(f"    - {name}")
                if missing:
                    print("  Missing (in-month on-disk input, not in table):")
                    for name in missing:
                        print(f"    - {name}")
                sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: Context Inputs projection failed: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
