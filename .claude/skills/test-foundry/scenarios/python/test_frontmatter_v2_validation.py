"""
test_frontmatter_v2_validation.py - scan all PLANs in Workbench/ for schema-v2
required fields. Fails if any PLAN is missing a required key.

Required v2 keys (intersection observed across the live Workbench PLANs):
    schema_version, title, type, status, assigned_to, priority, created,
    created_by, created_month, log_month, pipeline_phase, tags, files_touched
"""

from __future__ import annotations

import pathlib
import re
import time


REQUIRED_KEYS = (
    "schema_version",
    "title",
    "type",
    "status",
    "assigned_to",
    "priority",
    "created",
    "created_by",
    "created_month",
    "log_month",
    "pipeline_phase",
    "tags",
    "files_touched",
)


def _find_repo_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve()
    for candidate in [here.parent] + list(here.parents):
        if (candidate / "Workbench").is_dir():
            return candidate
    return pathlib.Path.cwd()


_FM_RE = re.compile(r"^---\n(.*?\n)---\n", re.DOTALL)
_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", re.MULTILINE)


def _extract_keys(text: str) -> set[str]:
    m = _FM_RE.match(text)
    if not m:
        return set()
    body = m.group(1)
    keys = set()
    for line in body.splitlines():
        # Only top-level keys (no leading whitespace).
        if line and not line.startswith((" ", "\t", "#")):
            km = _KEY_RE.match(line)
            if km:
                keys.add(km.group(1))
    return keys


def run() -> dict:
    started = time.monotonic()
    repo_root = _find_repo_root()
    workbench = repo_root / "Workbench"

    if not workbench.is_dir():
        return {
            "scenario": "test_frontmatter_v2_validation",
            "status": "skip",
            "symptoms": ["Workbench/ not found"],
            "diagnostics": str(workbench),
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    plan_files = sorted(workbench.glob("PLAN-*.md"))
    if not plan_files:
        return {
            "scenario": "test_frontmatter_v2_validation",
            "status": "skip",
            "symptoms": ["no PLAN files in Workbench/"],
            "diagnostics": "",
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    symptoms: list[str] = []
    diagnostics_lines: list[str] = [f"scanned {len(plan_files)} PLAN files"]

    for path in plan_files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            symptoms.append(f"{path.name}: read error: {exc}")
            continue
        keys = _extract_keys(text)
        missing = [k for k in REQUIRED_KEYS if k not in keys]
        if missing:
            symptoms.append(f"{path.name}: missing keys: {', '.join(missing)}")

    status = "fail" if symptoms else "pass"
    return {
        "scenario": "test_frontmatter_v2_validation",
        "status": status,
        "symptoms": symptoms,
        "diagnostics": "\n".join(diagnostics_lines),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(run(), indent=2))
