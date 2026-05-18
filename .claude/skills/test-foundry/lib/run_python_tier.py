#!/usr/bin/env python3
"""
run_python_tier.py — discover and execute Python-tier scenarios for test-foundry.

Each scenario module under `.claude/skills/test-foundry/scenarios/python/test_*.py` MUST
expose a synchronous `run() -> dict` callable. The returned dict shape:

    {
        "scenario": "<scenario_id>",
        "status": "pass" | "fail" | "skip",
        "symptoms": [list of human-readable symptom strings],
        "diagnostics": "<free-text diagnostic detail>",
        "duration_ms": <int>,
    }

Discovery is hand-rolled (no pytest dependency): glob `scenarios/python/test_*.py`,
import each module via importlib, call `run()`, accumulate.

Flags:
    --json              Emit JSON aggregate to stdout (default: human-readable).
    --output <path>     Write the JSON aggregate to <path> instead of stdout.
                        Avoids needing shell redirect from executor-side invocations
                        per `_shared/plan-safe.md` boundary (a).

Exit code is always 0 if discovery + execution completed (even with failing scenarios).
A non-zero exit is reserved for harness-level errors (no scenarios found, import failure
on a discovered module, etc).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
import time
import traceback


def find_repo_root(start: pathlib.Path) -> pathlib.Path:
    current = start.resolve()
    for candidate in [current] + list(current.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


def discover_scenarios(scenarios_dir: pathlib.Path) -> list[pathlib.Path]:
    if not scenarios_dir.is_dir():
        return []
    return sorted(scenarios_dir.glob("test_*.py"))


def load_module(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_one(path: pathlib.Path) -> dict:
    scenario_id = path.stem
    started = time.monotonic()
    try:
        module = load_module(path)
    except Exception as exc:
        return {
            "scenario": scenario_id,
            "status": "fail",
            "symptoms": [f"import error: {exc}"],
            "diagnostics": traceback.format_exc(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    run_fn = getattr(module, "run", None)
    if run_fn is None or not callable(run_fn):
        return {
            "scenario": scenario_id,
            "status": "fail",
            "symptoms": ["module exposes no callable `run()`"],
            "diagnostics": f"{path}: missing `run()`",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    try:
        result = run_fn()
    except Exception as exc:
        return {
            "scenario": scenario_id,
            "status": "fail",
            "symptoms": [f"run() raised: {exc}"],
            "diagnostics": traceback.format_exc(),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    if not isinstance(result, dict):
        return {
            "scenario": scenario_id,
            "status": "fail",
            "symptoms": ["run() did not return a dict"],
            "diagnostics": f"got: {type(result).__name__}",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }
    # Normalise: ensure required keys are present.
    result.setdefault("scenario", scenario_id)
    result.setdefault("symptoms", [])
    result.setdefault("diagnostics", "")
    if "duration_ms" not in result:
        result["duration_ms"] = int((time.monotonic() - started) * 1000)
    if result.get("status") not in {"pass", "fail", "skip"}:
        result["symptoms"] = list(result.get("symptoms", [])) + [
            f"invalid status: {result.get('status')!r}; coercing to fail"
        ]
        result["status"] = "fail"
    return result


def aggregate(results: list[dict]) -> dict:
    summary = {"passed": 0, "failed": 0, "skipped": 0}
    for r in results:
        if r["status"] == "pass":
            summary["passed"] += 1
        elif r["status"] == "fail":
            summary["failed"] += 1
        else:
            summary["skipped"] += 1
    return {
        "schema_version": 1,
        "tier": "python",
        "scenarios": results,
        "summary": summary,
    }


def render_human(aggregate_data: dict) -> str:
    lines = []
    lines.append("plan-foundry-test — Python tier")
    s = aggregate_data["summary"]
    lines.append(f"  passed: {s['passed']}  failed: {s['failed']}  skipped: {s['skipped']}")
    for r in aggregate_data["scenarios"]:
        marker = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}[r["status"]]
        lines.append(f"  [{marker}] {r['scenario']}  ({r['duration_ms']} ms)")
        for sym in r["symptoms"]:
            lines.append(f"      - {sym}")
        if r["diagnostics"]:
            head = r["diagnostics"].splitlines()[0] if r["diagnostics"] else ""
            lines.append(f"      diagnostics: {head}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run plan-foundry-test Python tier")
    parser.add_argument("--json", action="store_true", help="Emit JSON aggregate")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Write JSON aggregate to <path> instead of stdout (implies --json)",
    )
    args = parser.parse_args(argv)

    # Post-PLAN-AC3/AC5: resolve repo root from cwd (where the human invoked
    # the harness), not from this script's __file__ — which previously walked
    # parents and could land in a different repo when the bundle was
    # symlinked into a target. Post-AC5 the bundle is copied into each
    # target rather than symlinked, but the cwd-rooted resolution is still
    # the right behaviour (the script's __file__ now lives inside the
    # project's own `.claude/`, but that's a copy of the bundle and not
    # necessarily what the human ran the harness against if PLAN_FOUNDRY_BUNDLE_PATH
    # points elsewhere). The harness lives at
    # .claude/skills/test-foundry/scenarios/python/ relative to cwd.
    import os
    repo_root = pathlib.Path(os.getcwd())
    scenarios_dir = repo_root / ".claude" / "skills" / "test-foundry" / "scenarios" / "python"

    scenario_paths = discover_scenarios(scenarios_dir)
    results = [run_one(p) for p in scenario_paths]
    data = aggregate(results)

    want_json = args.json or args.output is not None
    if args.output:
        out_path = pathlib.Path(args.output)
        if not out_path.is_absolute():
            out_path = repo_root / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        # Also print a one-line confirmation to stdout for the executor's transcript.
        print(f"wrote {out_path}")
    elif want_json:
        print(json.dumps(data, indent=2))
    else:
        print(render_human(data))

    return 0


if __name__ == "__main__":
    sys.exit(main())
