#!/usr/bin/env python3
"""
recover-deleted-retirees.py — recover PLAN bodies deleted via the 2026-05-13 retire-skill bug.

The retire skill / plan-retirer haiku agent has, on confirmed occasions, executed
`git rm` instead of moving the target file to `Retired/`. This script extracts the
last-known-good version of each missing body from git history and writes it into
`Retired/` (which is gitignored, so the bodies live on-disk only for forensic
preservation per D3 "Numeric-Historical-Frozen" in PLAN-AA0).

Approach: for each filename, find the most-recent commit where the file was
deleted (`git log --diff-filter=D --name-only`); then extract the body from
the parent of that commit (`git show <sha>~1:<path>`); write binary to disk
to avoid Windows CRLF mangling.

Usage:
    python recover-deleted-retirees.py [inventory_json]

If `inventory_json` is omitted, defaults to the latest
`Workbench/.audit/recovery-inventory-*.json`.

The inventory JSON contains `{missing: [filename, ...]}`. The script writes a
recovery report to `Workbench/.audit/recovery-report-<sha>.json` with per-file
outcomes.

Design lineage: PLAN-AA2 (retire-postcondition-fix-and-body-recovery), one-shot
recovery per research finding C3 β (~30 files, single event, low parameter
complexity — sealed migration shape).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys


def find_deletion_commit(repo_root: pathlib.Path, path: str) -> str | None:
    """
    Find the most-recent commit that deleted `path` from the tree.

    Returns the commit SHA, or None if no deletion record exists in history.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "log",
            "--diff-filter=D",
            "--name-only",
            "--pretty=format:%H",
            "--",
            path,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    # Output format: alternating SHA lines and filename lines.
    # The first SHA is the most-recent deletion. We don't need to match
    # the filename because we asked git to filter by it.
    for line in result.stdout.splitlines():
        line = line.strip()
        # SHA lines are 40-char hex
        if len(line) == 40 and all(c in "0123456789abcdef" for c in line):
            return line
    return None


def find_historical_path(repo_root: pathlib.Path, slug: str) -> str | None:
    """
    Search git history for any .md file path containing the given slug.
    Returns the first matching historical path, or None.

    This handles the case where a PLAN was originally under a timestamp-prefix
    name (e.g. Workbench/202604010000_PLAN_<slug>.md or Bus/...) before being
    renamed to PLAN-NNN_<slug>.md, then deleted. The LOG references the
    post-rename name but the body lives at the pre-rename path in history.
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "log",
            "--all",
            "--name-only",
            "--pretty=format:",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line.endswith(".md"):
            continue
        if slug in line:
            return line
    return None


def extract_body_pre_deletion(
    repo_root: pathlib.Path, sha: str, workbench_path: str
) -> bytes:
    """
    Extract the file body as it existed at <sha>~1 (the commit before deletion).
    Returns bytes (binary mode — avoids Windows CRLF translation).
    """
    result = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "show",
            f"{sha}~1:{workbench_path}",
        ],
        capture_output=True,
        check=True,
    )
    return result.stdout


def recover_one(repo_root: pathlib.Path, filename: str) -> dict:
    """
    Recover one missing body. Idempotent: if Retired/<filename> already exists,
    returns status 'already_present' without overwriting.

    Search order:
      1. Exact: Retired/<filename> on disk → already_present.
      2. Slug-on-disk: any file in Retired/ whose name contains the slug → slug_matched_present.
      3. Exact-path history: Workbench/<filename> ever deleted → recover from there.
      4. Slug history: any historical .md path containing the slug → recover from there.
      5. Otherwise → unrecoverable.
    """
    import re

    target = repo_root / "Retired" / filename
    if target.exists():
        return {
            "filename": filename,
            "status": "already_present",
            "source_sha": None,
            "source_path": None,
            "target_path": str(target.relative_to(repo_root)),
            "bytes_written": 0,
        }

    # extract slug for fuzzy matching
    m = re.match(r"^PLAN-[A-Z0-9]+_(.+)\.md$", filename)
    slug = m.group(1) if m else None

    # 2) slug match in existing Retired/ contents
    if slug:
        for f in (repo_root / "Retired").glob("*.md"):
            if slug in f.name and f.name != filename:
                return {
                    "filename": filename,
                    "status": "slug_matched_present",
                    "source_sha": None,
                    "source_path": str(f.relative_to(repo_root)),
                    "target_path": str(f.relative_to(repo_root)),
                    "bytes_written": 0,
                }

    # 3) exact-path history (Workbench/<filename>)
    workbench_path = f"Workbench/{filename}"
    sha = find_deletion_commit(repo_root, workbench_path)
    if sha is not None:
        try:
            body = extract_body_pre_deletion(repo_root, sha, workbench_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "wb") as f:
                f.write(body)
            return {
                "filename": filename,
                "status": "success",
                "source_sha": sha,
                "source_path": workbench_path,
                "target_path": str(target.relative_to(repo_root)),
                "bytes_written": len(body),
            }
        except subprocess.CalledProcessError:
            pass

    # 4) slug-based historical path search
    if slug:
        hist_path = find_historical_path(repo_root, slug)
        if hist_path:
            sha = find_deletion_commit(repo_root, hist_path)
            if sha is not None:
                try:
                    body = extract_body_pre_deletion(repo_root, sha, hist_path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "wb") as f:
                        f.write(body)
                    return {
                        "filename": filename,
                        "status": "success_via_slug_history",
                        "source_sha": sha,
                        "source_path": hist_path,
                        "target_path": str(target.relative_to(repo_root)),
                        "bytes_written": len(body),
                    }
                except subprocess.CalledProcessError:
                    pass
            else:
                # File exists in history but no deletion record — try latest version
                try:
                    result = subprocess.run(
                        [
                            "git",
                            "-C",
                            str(repo_root),
                            "log",
                            "--all",
                            "--pretty=format:%H",
                            "-n",
                            "1",
                            "--",
                            hist_path,
                        ],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                    sha = result.stdout.strip()
                    if sha:
                        body = subprocess.run(
                            [
                                "git",
                                "-C",
                                str(repo_root),
                                "show",
                                f"{sha}:{hist_path}",
                            ],
                            capture_output=True,
                            check=True,
                        ).stdout
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with open(target, "wb") as f:
                            f.write(body)
                        return {
                            "filename": filename,
                            "status": "success_via_slug_history_no_deletion",
                            "source_sha": sha,
                            "source_path": hist_path,
                            "target_path": str(target.relative_to(repo_root)),
                            "bytes_written": len(body),
                        }
                except subprocess.CalledProcessError:
                    pass

    return {
        "filename": filename,
        "status": "unrecoverable",
        "source_sha": None,
        "source_path": None,
        "target_path": None,
        "bytes_written": 0,
    }


def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    for candidate in [current] + list(current.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


def main(argv: list[str]) -> int:
    repo_root = find_repo_root(pathlib.Path(__file__).parent)

    if len(argv) >= 2:
        inventory_path = pathlib.Path(argv[1])
    else:
        # Default: pick the latest inventory in .audit/
        candidates = sorted((repo_root / "Workbench" / ".audit").glob("recovery-inventory-*.json"))
        if not candidates:
            print("Error: no inventory JSON found; pass path as argv[1]", file=sys.stderr)
            return 1
        inventory_path = candidates[-1]

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    missing = inventory.get("missing", [])
    if not missing:
        print("Nothing to recover (missing list empty).", file=sys.stderr)
        return 0

    print(f"Recovering {len(missing)} bodies from git history...", file=sys.stderr)
    results = []
    for fname in missing:
        result = recover_one(repo_root, fname)
        results.append(result)
        print(f"  [{result['status']:22}] {fname}", file=sys.stderr)

    # Summary
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    print(file=sys.stderr)
    print("Summary:", file=sys.stderr)
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}", file=sys.stderr)

    # Write report
    sha = subprocess.check_output(
        ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"], text=True
    ).strip()
    report_path = repo_root / "Workbench" / ".audit" / f"recovery-report-{sha}.json"
    report = {
        "sha": sha,
        "inventory_source": str(inventory_path.relative_to(repo_root)),
        "summary": by_status,
        "results": results,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written: {report_path.relative_to(repo_root)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
