#!/usr/bin/env python3
"""
audit-foundry.py — Static audit of plan-foundry's plugin tree + Workbench state.

The mechanical sibling to the broad-sweep audit. Designed for two use modes:
  1. Maintainer-invoked (this script directly) — emits a human-readable
     summary + writes JSON findings under Workbench/.audit/.
  2. Test-harness invoked (PLAN-AA8 — formerly PLAN-030 — will wire this in as a structural-
     integrity scenario) — consumes the JSON output.

Categories shipped in v1:
  - frontmatter-v2  Every PLAN file has the load-bearing schema_v2 fields.
  - cross-refs      Markdown links resolve (relative paths only).
  - path-patterns   Cwd-relative `python plugins/.../` invocations in
                    markdown contexts. Informational only — broken in
                    consumer install but fix lives in a follow-on PR.

Output:
  Default: human-readable markdown summary to stdout. JSON findings written
  to Workbench/.audit/audit-findings-<short-sha>.json (or `latest.json` if
  not in a git repo).

  --output json      Emit JSON findings to stdout instead of writing to disk.
  --output markdown  Emit markdown summary to stdout (default).
  --no-json-output   Skip writing the JSON findings file.
  --category NAME    Run only one category.
  --list             List available categories and exit.

Exit codes:
  0 — no findings of severity >= error
  1 — at least one finding of severity >= error
  2 — script error (CLI misuse, IO failure, etc.)

Run from anywhere inside the plan-foundry repo; the script resolves paths
relative to the repo root.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path


# ---------------------------------------------------------------------------
# Repo root discovery
# ---------------------------------------------------------------------------

def find_repo_root() -> Path:
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".claude-plugin" / "marketplace.json").exists():
            return current
        current = current.parent
    raise SystemExit("ERROR: could not locate plan-foundry repo root.")


REPO_ROOT = find_repo_root()


# ---------------------------------------------------------------------------
# Finding model
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"info": 0, "warn": 1, "error": 2}


@dataclass
class Finding:
    category: str
    severity: str  # "info" | "warn" | "error"
    file: str
    line: int | None
    message: str
    detail: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Category: frontmatter-v2
# ---------------------------------------------------------------------------

REQUIRED_FM_KEYS = [
    "schema_version",
    "title",
    "type",
    "status",
    "assigned_to",
    "priority",
    "created",
    "created_month",
    "log_month",
    "pipeline_phase",
    "tags",
    "files_touched",
]

VALID_STATUS = {"ready", "in_progress", "blocked", "done", "cancelled", "partially-complete", "closed"}

VALID_PIPELINE_PHASE = {
    "",  # empty = pre-pipeline or recurring
    "drafting",
    "drafted",
    "checked",
    "executing",
    "outcome-verifying",
    "complete",
}


def _parse_frontmatter_text(text: str) -> tuple[dict, str]:
    """Return (top-level scalar dict, raw frontmatter text). Mirrors build_index.py."""
    if not text.startswith("---"):
        return {}, ""
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, ""
    fm_text = parts[1]
    fm: dict = {}
    for line in fm_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or line.startswith(" ") or line.startswith("\t"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if " #" in value:
            value = value[:value.index(" #")].strip()
        value = value.strip('"').strip("'")
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        elif value.lower() in ("null", "~", ""):
            value = None
        fm[key] = value
    return fm, fm_text


def check_frontmatter_v2() -> list[Finding]:
    findings: list[Finding] = []
    workbench = REPO_ROOT / "Workbench"
    if not workbench.is_dir():
        return findings

    plan_pattern = re.compile(r"^(?P<kind>PLAN|ADVICE|RESEARCH)-\d{3}_")

    # The audit only enforces full schema_v2 fields on PLAN files. ADVICE and
    # RESEARCH are looser-format context inputs (written via write-input);
    # checking their `type` field matches their filename prefix is enough.
    type_for_prefix = {"PLAN": "plan", "ADVICE": "advice", "RESEARCH": "research"}

    for plan_file in sorted(workbench.glob("*.md")):
        m = plan_pattern.match(plan_file.name)
        if not m:
            continue
        prefix = m.group("kind")
        text = plan_file.read_text(encoding="utf-8")
        fm, _raw = _parse_frontmatter_text(text)

        rel = plan_file.relative_to(REPO_ROOT).as_posix()

        if not fm:
            findings.append(Finding(
                category="frontmatter-v2",
                severity="error",
                file=rel,
                line=None,
                message="No frontmatter parsed; file appears to lack a YAML front-matter block.",
            ))
            continue

        expected_type = type_for_prefix[prefix]
        if fm.get("type") != expected_type:
            findings.append(Finding(
                category="frontmatter-v2",
                severity="error",
                file=rel,
                line=None,
                message=f"type field is {fm.get('type')!r}, expected {expected_type!r} (matches filename prefix {prefix!r}).",
            ))
            continue

        # Only PLAN files get the full schema_v2 required-key check.
        # ADVICE and RESEARCH have looser format (per write-input skill).
        if prefix != "PLAN":
            continue

        # schema_version: must be present and == 2
        sv = fm.get("schema_version")
        try:
            sv_int = int(sv) if sv is not None else None
        except (ValueError, TypeError):
            sv_int = None
        if sv_int != 2:
            findings.append(Finding(
                category="frontmatter-v2",
                severity="error",
                file=rel,
                line=None,
                message=f"schema_version is {sv!r}; expected 2.",
            ))

        # Missing required keys
        for key in REQUIRED_FM_KEYS:
            if key not in fm:
                findings.append(Finding(
                    category="frontmatter-v2",
                    severity="warn",
                    file=rel,
                    line=None,
                    message=f"Missing required v2 field: {key!r}.",
                ))

        # Valid status
        status = fm.get("status")
        if status and status not in VALID_STATUS:
            findings.append(Finding(
                category="frontmatter-v2",
                severity="warn",
                file=rel,
                line=None,
                message=f"status={status!r} not in valid enum {sorted(VALID_STATUS)}.",
            ))

        # Valid pipeline_phase
        phase = fm.get("pipeline_phase")
        if phase is not None and phase not in VALID_PIPELINE_PHASE:
            findings.append(Finding(
                category="frontmatter-v2",
                severity="warn",
                file=rel,
                line=None,
                message=f"pipeline_phase={phase!r} not in valid enum {sorted(VALID_PIPELINE_PHASE - {''})}.",
            ))

    return findings


# ---------------------------------------------------------------------------
# Category: cross-refs
# ---------------------------------------------------------------------------

MARKDOWN_LINK_RE = re.compile(r"\[(?P<text>[^\]]*?)\]\((?P<target>[^)]+?)\)")

# Files to scan for cross-refs. Skips Workbench/ (PLANs may reference future paths)
# and Retired/ (frozen content).
CROSS_REF_DIRS = ["plugins", "scripts"]
CROSS_REF_ROOT_FILES = ["README.md", "ARCHITECTURE.md", "CLAUDE.md", "ROADMAP.md"]


def _resolve_link_target(source_file: Path, target: str) -> Path | None:
    """Given a markdown source file and a link target, return the resolved
    path if it's a relative file ref, or None if the link is external / not a
    file ref."""
    # Strip fragment anchors
    target = target.split("#", 1)[0]
    target = target.strip()
    if not target:
        return None
    # Skip URL schemes
    if "://" in target or target.startswith("mailto:") or target.startswith("#"):
        return None
    # Resolve relative to source file's directory
    return (source_file.parent / target).resolve()


def _iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for dirname in CROSS_REF_DIRS:
        d = REPO_ROOT / dirname
        if d.is_dir():
            files.extend(p for p in d.rglob("*.md") if "/Retired/" not in p.as_posix())
    for fname in CROSS_REF_ROOT_FILES:
        p = REPO_ROOT / fname
        if p.exists():
            files.append(p)
    return files


def check_cross_refs() -> list[Finding]:
    findings: list[Finding] = []
    for source in _iter_markdown_files():
        text = source.read_text(encoding="utf-8")
        for line_num, line in enumerate(text.splitlines(), start=1):
            # Skip code-fence lines crudely (don't try to track multi-line fences here)
            if line.strip().startswith("```"):
                continue
            for match in MARKDOWN_LINK_RE.finditer(line):
                target = match.group("target")
                resolved = _resolve_link_target(source, target)
                if resolved is None:
                    continue  # external / fragment / blank
                if not resolved.exists():
                    findings.append(Finding(
                        category="cross-refs",
                        severity="error",
                        file=source.relative_to(REPO_ROOT).as_posix(),
                        line=line_num,
                        message=f"Broken link: {target!r} → {resolved.relative_to(REPO_ROOT) if str(resolved).startswith(str(REPO_ROOT)) else resolved} does not exist.",
                    ))
    return findings


# ---------------------------------------------------------------------------
# Category: path-patterns
# ---------------------------------------------------------------------------

# Markdown contexts where a `python plugins/plan-foundry-core/...` invocation
# would silently break in a consumer install because:
#   - The plugin lives at ~/.claude/plugins/<plugin>/, not at plugins/<plugin>/.
#   - Claude Code does NOT expand ${CLAUDE_PLUGIN_ROOT} in markdown bodies
#     (upstream bug anthropics/claude-code#9354).
# The fix pattern is:
#   python "${CLAUDE_PLUGIN_ROOT:-plugins/plan-foundry-core}/skills/X/Y.py" args
# Bash parameter expansion at command-execution time uses the env var if set
# (consumer install) and falls back to the dogfood-relative path otherwise.
# See plugins/plan-foundry-core/skills/_shared/path-resolution.md for full
# rationale.

# Bare cwd-relative pattern — flagged as 'error' (broken in consumer install).
# Matches `python plugins/<plugin>/...` NOT wrapped in `${CLAUDE_PLUGIN_ROOT:-...}`.
PATH_PATTERN_RE = re.compile(
    r"python3?\s+\"?(?P<path>plugins/[\w-]+/(?:commands|skills|agents)/[\w./-]+\.py)"
)

# Allowed pattern — flag the prefix to skip those matches.
ALLOWED_PATTERN_RE = re.compile(
    r'\$\{CLAUDE_PLUGIN_ROOT:-plugins/[\w-]+\}'
)


def check_path_patterns() -> list[Finding]:
    findings: list[Finding] = []
    # path-resolution.md is the canonical doc showing the broken pattern as a
    # worked example before its fix; exempt it from this category.
    EXEMPT_FILES = {
        "plugins/plan-foundry-core/skills/_shared/path-resolution.md",
    }
    for source in _iter_markdown_files():
        rel = source.relative_to(REPO_ROOT).as_posix()
        if rel in EXEMPT_FILES:
            continue
        text = source.read_text(encoding="utf-8")
        for line_num, line in enumerate(text.splitlines(), start=1):
            if line.strip().startswith("```"):
                continue
            # Skip lines that already use the safe pattern.
            if ALLOWED_PATTERN_RE.search(line):
                continue
            for match in PATH_PATTERN_RE.finditer(line):
                findings.append(Finding(
                    category="path-patterns",
                    severity="error",
                    file=rel,
                    line=line_num,
                    message=(
                        f"Cwd-relative plugin path: {match.group('path')!r}. "
                        f"Breaks in consumer install. Rewrite as "
                        f"`python \"${{CLAUDE_PLUGIN_ROOT:-plugins/<plugin>}}/...\"` — "
                        f"see plugins/plan-foundry-core/skills/_shared/path-resolution.md."
                    ),
                ))
    return findings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

CATEGORIES = {
    "frontmatter-v2": check_frontmatter_v2,
    "cross-refs": check_cross_refs,
    "path-patterns": check_path_patterns,
}


def _git_short_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "nogit"


def render_markdown(findings: list[Finding]) -> str:
    by_cat: dict[str, list[Finding]] = {}
    for f in findings:
        by_cat.setdefault(f.category, []).append(f)
    by_sev: dict[str, int] = {"info": 0, "warn": 0, "error": 0}
    for f in findings:
        by_sev[f.severity] = by_sev.get(f.severity, 0) + 1

    lines: list[str] = []
    lines.append("# audit-foundry findings")
    lines.append("")
    lines.append(f"Total findings: **{len(findings)}**  (error: {by_sev['error']}, warn: {by_sev['warn']}, info: {by_sev['info']})")
    lines.append("")
    for cat in CATEGORIES:
        cat_findings = by_cat.get(cat, [])
        lines.append(f"## {cat}  ({len(cat_findings)})")
        lines.append("")
        if not cat_findings:
            lines.append("_No findings._")
            lines.append("")
            continue
        for f in cat_findings:
            loc = f.file + (f":{f.line}" if f.line else "")
            lines.append(f"- **[{f.severity}]** {loc} — {f.message}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--category",
        choices=list(CATEGORIES.keys()),
        help="Run only one category (default: all)",
    )
    parser.add_argument(
        "--output",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format for stdout (default: markdown)",
    )
    parser.add_argument(
        "--no-json-output",
        action="store_true",
        help="Skip writing the JSON findings file under Workbench/.audit/",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available categories and exit",
    )
    args = parser.parse_args()

    if args.list:
        for cat in CATEGORIES:
            print(cat)
        return 0

    categories_to_run = [args.category] if args.category else list(CATEGORIES.keys())
    findings: list[Finding] = []
    for cat in categories_to_run:
        findings.extend(CATEGORIES[cat]())

    # Stable ordering — by category then by severity (errors first) then by file/line.
    findings.sort(key=lambda f: (
        list(CATEGORIES.keys()).index(f.category),
        -SEVERITY_ORDER.get(f.severity, 0),
        f.file,
        f.line or 0,
    ))

    # Write JSON findings file (unless suppressed)
    if not args.no_json_output:
        audit_dir = REPO_ROOT / "Workbench" / ".audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        sha = _git_short_sha()
        json_path = audit_dir / f"audit-findings-{sha}.json"
        json_path.write_text(
            json.dumps({"findings": [asdict(f) for f in findings]}, indent=2),
            encoding="utf-8",
        )
        # Also write a stable `latest.json` for easy reference
        latest = audit_dir / "audit-findings-latest.json"
        latest.write_text(
            json.dumps({"findings": [asdict(f) for f in findings], "sha": sha}, indent=2),
            encoding="utf-8",
        )

    # Emit to stdout
    if args.output == "json":
        print(json.dumps({"findings": [asdict(f) for f in findings]}, indent=2))
    else:
        print(render_markdown(findings))

    error_count = sum(1 for f in findings if f.severity == "error")
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
