"""
test_audit_baseline_clean.py - invoke scripts/audit-foundry.py. Fails if non-zero
exit (i.e. any `error`-severity finding). `warn` and `info` findings do not
fail the scenario but are surfaced in diagnostics.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import time


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in [here.parent] + list(here.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


def run() -> dict:
    started = time.monotonic()
    repo_root = _find_repo_root()
    script = repo_root / "scripts" / "audit-foundry.py"

    if not script.is_file():
        return {
            "scenario": "test_audit_baseline_clean",
            "status": "skip",
            "symptoms": ["scripts/audit-foundry.py not present - likely a consumer install; skipping"],
            "diagnostics": str(script),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    diagnostics_lines = [f"exit={proc.returncode}"]
    if proc.stdout:
        diagnostics_lines.append(f"stdout: {proc.stdout.strip()[:600]}")
    if proc.stderr:
        diagnostics_lines.append(f"stderr: {proc.stderr.strip()[:400]}")

    if proc.returncode != 0:
        return {
            "scenario": "test_audit_baseline_clean",
            "status": "fail",
            "symptoms": [f"audit-foundry.py exited {proc.returncode}"],
            "diagnostics": "\n".join(diagnostics_lines),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    return {
        "scenario": "test_audit_baseline_clean",
        "status": "pass",
        "symptoms": [],
        "diagnostics": "\n".join(diagnostics_lines),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
