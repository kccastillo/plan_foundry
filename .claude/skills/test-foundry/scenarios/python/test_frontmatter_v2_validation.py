"""
test_frontmatter_v2_validation.py - scan all PLANs in Workbench/ for schema-v2
required fields, and check that scripts/audit-foundry.py's VALID_STATUS enum
accepts every canonical status value from plan-conventions.md. Fails if any
PLAN is missing a required key, or if the two status vocabularies have
drifted apart.

Required v2 keys (intersection observed across the live Workbench PLANs):
    schema_version, title, type, status, assigned_to, priority, created,
    created_by, created_month, log_month, pipeline_phase, tags, files_touched
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import sys
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


_STATUS_SECTION_RE = re.compile(
    r"## PLAN Status Lifecycle\n(.*?)\n## ", re.DOTALL
)
_FENCE_RE = re.compile(r"```\n(.*?)\n```", re.DOTALL)


def _canonical_statuses(repo_root: pathlib.Path) -> list[str] | None:
    """Parse the canonical status enum straight out of plan-conventions.md's
    '## PLAN Status Lifecycle' fenced block, rather than hand-copying the
    list here - so this test still catches drift if that file's enum
    changes. Returns None if the file or the expected block is not found."""
    conventions = (
        repo_root
        / ".claude"
        / "skills"
        / "write-plan"
        / "references"
        / "plan-conventions.md"
    )
    if not conventions.is_file():
        return None
    text = conventions.read_text(encoding="utf-8", errors="replace")
    section = _STATUS_SECTION_RE.search(text)
    if not section:
        return None
    fence = _FENCE_RE.search(section.group(1))
    if not fence:
        return None
    tokens = re.split(r"->|\|", fence.group(1))
    return [t.strip().strip("`") for t in tokens if t.strip()]


def _valid_status_enum(repo_root: pathlib.Path) -> set[str] | None:
    """Import VALID_STATUS out of scripts/audit-foundry.py without a package
    import (the filename carries a hyphen). Returns None if the script is
    not present (e.g. a consumer install missing dev-only scripts)."""
    script = repo_root / "scripts" / "audit-foundry.py"
    if not script.is_file():
        return None
    spec = importlib.util.spec_from_file_location("audit_foundry_under_test", script)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    # Register before exec: audit-foundry.py declares module-level
    # dataclasses, and the dataclass decorator looks the module up in
    # sys.modules while processing the class body.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return set(getattr(module, "VALID_STATUS", set()))


def run() -> dict:
    started = time.monotonic()
    repo_root = _find_repo_root()
    workbench = repo_root / "Workbench"

    symptoms: list[str] = []
    diagnostics_lines: list[str] = []

    plan_files: list[pathlib.Path] = []
    if workbench.is_dir():
        plan_files = sorted(workbench.glob("PLAN-*.md"))
        diagnostics_lines.append(f"scanned {len(plan_files)} PLAN files")
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
    else:
        diagnostics_lines.append("Workbench/ not found - skipping required-key scan")

    canonical = _canonical_statuses(repo_root)
    if canonical is None:
        diagnostics_lines.append(
            "plan-conventions.md status-lifecycle block not found - skipping enum-coverage check"
        )
    else:
        valid_status = _valid_status_enum(repo_root)
        if valid_status is None:
            diagnostics_lines.append(
                "scripts/audit-foundry.py not found - skipping enum-coverage check"
            )
        else:
            uncovered = [s for s in canonical if s not in valid_status]
            if uncovered:
                symptoms.append(
                    "scripts/audit-foundry.py VALID_STATUS does not accept "
                    f"canonical plan-conventions.md status value(s): {', '.join(uncovered)}"
                )
            diagnostics_lines.append(f"canonical statuses checked: {', '.join(canonical)}")

    if symptoms:
        status = "fail"
    elif not plan_files and canonical is None:
        status = "skip"
        symptoms.append("nothing to check: no PLAN files and no canonical status list found")
    else:
        status = "pass"

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
