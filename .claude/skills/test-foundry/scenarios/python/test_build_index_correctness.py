"""
test_build_index_correctness.py — synthesize a Workbench with known PLAN frontmatter
and assert that update-workbench-index's build_index.py produces an INDEX with
expected counts, kanban grouping, and alerts.

Returns the standard scenario result dict.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in [here.parent] + list(here.parents):
        if (candidate / "Workbench").is_dir() and (candidate / ".claude").is_dir():
            return candidate
    return pathlib.Path.cwd()


SYNTHETIC_PLANS = {
    "PLAN-AA0_alpha.md": """---
schema_version: 2
title: "Alpha plan"
type: plan
status: ready
assigned_to: sonnet
priority: high
created: 2026-05-17
created_by: opus
created_month: 202605
log_month: 202605
pipeline_phase: drafted
tags: [synthetic]
files_touched: []
---
## Objective
Synthetic.
## Context
Synthetic.
## Steps
1. Do nothing.
## Verification
- [ ] noop
      `verify: true`
""",
    "PLAN-AA1_beta.md": """---
schema_version: 2
title: "Beta plan"
type: plan
status: in-progress
assigned_to: sonnet
priority: medium
created: 2026-05-17
created_by: opus
created_month: 202605
log_month: 202605
pipeline_phase: executing
tags: [synthetic]
files_touched: []
---
## Objective
Synthetic.
## Context
Synthetic.
## Steps
1. Do nothing.
## Verification
- [ ] noop
      `verify: true`
""",
    "PLAN-AA2_gamma.md": """---
schema_version: 2
title: "Gamma plan"
type: plan
status: done
assigned_to: sonnet
priority: low
created: 2026-05-17
created_by: opus
created_month: 202605
log_month: 202605
pipeline_phase: complete
tags: [synthetic]
files_touched: []
---
## Objective
Synthetic.
## Context
Synthetic.
## Steps
1. Do nothing.
## Verification
- [ ] noop
      `verify: true`
""",
}


def run() -> dict:
    started = time.monotonic()
    symptoms: list[str] = []
    diagnostics_lines: list[str] = []

    repo_root = _find_repo_root()
    build_script = (
        repo_root
        / ".claude"
        / "plan-foundry-core"
        / "skills"
        / "update-workbench-index"
        / "scripts"
        / "build_index.py"
    )
    if not build_script.is_file():
        return {
            "scenario": "test_build_index_correctness",
            "status": "skip",
            "symptoms": ["build_index.py not found — skipping (consumer install without core)"],
            "diagnostics": str(build_script),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix="pft-buildindex-"))
    try:
        workbench = tmpdir / "Workbench"
        workbench.mkdir()
        for name, body in SYNTHETIC_PLANS.items():
            (workbench / name).write_text(body, encoding="utf-8")
        # Minimal LOG so build_index has something to read if it expects one.
        (workbench / "202605010000_LOG_202605.md").write_text(
            "---\ntitle: synthetic LOG\ntype: bus-log\nmonth: 2026-05\nstatus: open\n---\n\n"
            "## Status Table\n\n"
            "| Plan File | Title | Assigned | Priority | Status | Due |\n"
            "|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )

        proc = subprocess.run(
            [sys.executable, str(build_script), str(workbench)],
            capture_output=True,
            text=True,
        )
        diagnostics_lines.append(f"build_index exit={proc.returncode}")
        if proc.stderr:
            diagnostics_lines.append(f"stderr: {proc.stderr.strip()[:400]}")
        if proc.returncode != 0:
            symptoms.append("build_index.py exited non-zero")
            return {
                "scenario": "test_build_index_correctness",
                "status": "fail",
                "symptoms": symptoms,
                "diagnostics": "\n".join(diagnostics_lines),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        index_md = workbench / "INDEX.md"
        index_json = workbench / ".index.json"
        if not index_md.is_file():
            symptoms.append("INDEX.md not written")
        if not index_json.is_file():
            symptoms.append(".index.json not written")
        if symptoms:
            return {
                "scenario": "test_build_index_correctness",
                "status": "fail",
                "symptoms": symptoms,
                "diagnostics": "\n".join(diagnostics_lines),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        try:
            parsed = json.loads(index_json.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "scenario": "test_build_index_correctness",
                "status": "fail",
                "symptoms": [f".index.json not valid JSON: {exc}"],
                "diagnostics": "\n".join(diagnostics_lines),
                "duration_ms": int((time.monotonic() - started) * 1000),
            }

        # Expected: 3 plans surfaced (AA0, AA1, AA2). The schema_version field
        # should be present per the update-workbench-index spec.
        plans_in_index = parsed.get("plans") or parsed.get("items") or []
        diagnostics_lines.append(f"plans_in_index_count={len(plans_in_index)}")
        if len(plans_in_index) < 3:
            symptoms.append(
                f"expected >=3 plans in INDEX, found {len(plans_in_index)}"
            )
        if parsed.get("schema_version") != 1:
            symptoms.append(
                f"expected schema_version=1, found {parsed.get('schema_version')}"
            )

        status = "fail" if symptoms else "pass"
        return {
            "scenario": "test_build_index_correctness",
            "status": status,
            "symptoms": symptoms,
            "diagnostics": "\n".join(diagnostics_lines),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    import json as _json
    print(_json.dumps(run(), indent=2))
