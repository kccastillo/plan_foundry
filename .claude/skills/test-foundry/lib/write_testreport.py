#!/usr/bin/env python3
"""
write_testreport.py — write a TESTREPORT-NNN_<slug>.md from aggregated tier results.

Inputs (CLI):
    --slug <slug>          Optional human-readable slug; defaults to YYYY-MM-DD.
    --results-json <path>  Path to the aggregated results JSON (schema below).
    --testreports-dir <p>  Optional override of `Workbench/testreports/`.

Aggregated results JSON schema:
    {
        "schema_version": 1,
        "python_tier": {
            "schema_version": 1,
            "tier": "python",
            "scenarios": [ {scenario, status, symptoms, diagnostics, duration_ms}, ... ],
            "summary": { "passed": N, "failed": N, "skipped": N }
        },
        "llm_tier": {
            "scenarios": [ {scenario, status, symptoms, diagnostics, duration_ms}, ... ],
            "summary": { "passed": N, "failed": N, "skipped": N }
        },
        "summary": { "passed": N, "failed": N, "skipped": N }
    }

If `llm_tier` is absent (e.g. the Python tier was run standalone), it is treated as
zero scenarios. Per-scenario lines are written line-anchored as `PASS: <id>` / `FAIL: <id>`
so PLAN-AA8 acceptance grep works.

Side-effects:
    1. Allocates the next TESTREPORT ID via `next_testreport_id.allocate()`.
    2. Writes `Workbench/testreports/TESTREPORT-NNN_<slug>.md`.
    3. Writes `Workbench/.testreport-current` (one line: bare ID like "TESTREPORT-003").
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import subprocess
import sys

# Import sibling allocator without requiring package install.
_HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
import next_testreport_id  # noqa: E402


def _git_sha(repo_root: pathlib.Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _render_scenario_block(r: dict) -> str:
    marker = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}.get(r["status"], "FAIL")
    lines = [f"{marker}: {r['scenario']}"]
    lines.append(f"- Duration: {r.get('duration_ms', 0)} ms")
    if r.get("symptoms"):
        lines.append("- Symptoms:")
        for s in r["symptoms"]:
            lines.append(f"  - {s}")
    diag = r.get("diagnostics", "")
    if diag:
        lines.append("- Diagnostics:")
        for dl in diag.splitlines():
            lines.append(f"  {dl}")
    else:
        lines.append("- Diagnostics: (none)")
    return "\n".join(lines)


def render_testreport(testreport_id: str, slug: str, results: dict, git_sha: str) -> str:
    today = _dt.date.today().isoformat()
    py = results.get("python_tier", {"scenarios": [], "summary": {"passed": 0, "failed": 0, "skipped": 0}})
    llm = results.get("llm_tier", {"scenarios": [], "summary": {"passed": 0, "failed": 0, "skipped": 0}})
    py_sum = py.get("summary", {"passed": 0, "failed": 0, "skipped": 0})
    llm_sum = llm.get("summary", {"passed": 0, "failed": 0, "skipped": 0})
    total = {
        "passed": py_sum.get("passed", 0) + llm_sum.get("passed", 0),
        "failed": py_sum.get("failed", 0) + llm_sum.get("failed", 0),
        "skipped": py_sum.get("skipped", 0) + llm_sum.get("skipped", 0),
    }
    total_scenarios = (
        len(py.get("scenarios", [])) + len(llm.get("scenarios", []))
    )

    lines: list[str] = []
    lines.append("---")
    lines.append(f'title: "TESTREPORT-{testreport_id} — {slug}"')
    lines.append("type: testreport")
    lines.append(f"testreport_id: {testreport_id}")
    lines.append(f"created: {today}")
    lines.append(f"last_updated: {today}")
    lines.append("created_by: test-foundry")
    lines.append(f"git_sha: {git_sha}")
    lines.append(f"total_scenarios: {total_scenarios}")
    lines.append(f"passed: {total['passed']}")
    lines.append(f"failed: {total['failed']}")
    lines.append(f"skipped: {total['skipped']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# TESTREPORT-{testreport_id} — {slug}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Tier | Passed | Failed | Skipped |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Python | {py_sum.get('passed', 0)} | {py_sum.get('failed', 0)} | {py_sum.get('skipped', 0)} |"
    )
    lines.append(
        f"| LLM | {llm_sum.get('passed', 0)} | {llm_sum.get('failed', 0)} | {llm_sum.get('skipped', 0)} |"
    )
    lines.append(
        f"| **Total** | {total['passed']} | {total['failed']} | {total['skipped']} |"
    )
    lines.append("")
    lines.append("## Python tier")
    lines.append("")
    if py.get("scenarios"):
        for r in py["scenarios"]:
            lines.append(_render_scenario_block(r))
            lines.append("")
    else:
        lines.append("(no Python scenarios reported)")
        lines.append("")
    lines.append("## LLM tier")
    lines.append("")
    if llm.get("scenarios"):
        for r in llm["scenarios"]:
            lines.append(_render_scenario_block(r))
            lines.append("")
    else:
        lines.append("(no LLM scenarios reported)")
        lines.append("")
    lines.append("## Diagnostics")
    lines.append("")
    lines.append(f"- Git sha: {git_sha}")
    lines.append(f"- Generated: {today}")
    lines.append(f"- Harness: plan-foundry-test v0.2.1")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", default=None)
    parser.add_argument("--results-json", default=None, help="Path to aggregated results JSON")
    parser.add_argument("--testreports-dir", default=None)
    args = parser.parse_args(argv)

    repo_root = next_testreport_id.find_repo_root(pathlib.Path(__file__).parent)
    testreports_dir = (
        pathlib.Path(args.testreports_dir)
        if args.testreports_dir
        else repo_root / "Workbench" / "testreports"
    )
    testreports_dir.mkdir(parents=True, exist_ok=True)

    slug = args.slug or _dt.date.today().isoformat()

    if args.results_json:
        results = json.loads(pathlib.Path(args.results_json).read_text(encoding="utf-8"))
        # If the JSON looks like a python_tier-only emission, wrap it.
        if results.get("tier") == "python":
            results = {"schema_version": 1, "python_tier": results, "llm_tier": {"scenarios": [], "summary": {"passed": 0, "failed": 0, "skipped": 0}}}
    else:
        results = {
            "schema_version": 1,
            "python_tier": {"scenarios": [], "summary": {"passed": 0, "failed": 0, "skipped": 0}},
            "llm_tier": {"scenarios": [], "summary": {"passed": 0, "failed": 0, "skipped": 0}},
        }

    testreport_id = next_testreport_id.allocate(testreports_dir)
    target_path = testreports_dir / f"TESTREPORT-{testreport_id}_{slug}.md"
    if next_testreport_id.would_collide(target_path):
        print(f"refuse to overwrite existing TESTREPORT: {target_path}", file=sys.stderr)
        return 1

    git_sha = _git_sha(repo_root)
    content = render_testreport(testreport_id, slug, results, git_sha)
    target_path.write_text(content, encoding="utf-8")

    sidecar = repo_root / "Workbench" / ".testreport-current"
    sidecar.write_text(f"TESTREPORT-{testreport_id}\n", encoding="utf-8")

    print(f"wrote {target_path}")
    print(f"wrote {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
