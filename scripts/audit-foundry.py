#!/usr/bin/env python3
"""
audit-foundry.py - Static audit of plan_foundry's bundle tree + Workbench state.

The mechanical sibling to the broad-sweep audit. Designed for two use modes:
  1. Maintainer-invoked (this script directly) - emits a human-readable
     summary + writes JSON findings under Workbench/.audit/.
  2. Test-harness invoked (PLAN-AA8 wired this in as a structural-integrity
     scenario) - consumes the JSON output.

Categories (PLAN-AC4 D3 post-state - path-patterns removed; it was specifically
a plugin-path linter with no bundle-era analogue):
  - frontmatter-v2  Every PLAN file has the load-bearing schema_v2 fields.
  - cross-refs      Markdown links resolve (relative paths only).

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
  0 - no findings of severity >= error
  1 - at least one finding of severity >= error
  2 - script error (CLI misuse, IO failure, etc.)

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
    """Walk up from this script's location looking for the bundle marker
    (`.claude/skills/plan-pipeline/SKILL.md`) or, failing that, a `.git/`
    directory. Per PLAN-AC4 D3 - the old marker `.claude-plugin/marketplace.json`
    was deleted by AC3 (plugin -> bundle pivot)."""
    current = Path(__file__).resolve().parent
    while current != current.parent:
        if (current / ".claude" / "skills" / "plan-pipeline" / "SKILL.md").exists():
            return current
        if (current / ".git").exists():
            return current
        current = current.parent
    raise SystemExit("ERROR: could not locate plan_foundry repo root.")


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

VALID_STATUS = {"ready", "in-progress", "blocked", "done", "cancelled", "partially-complete", "closed", "needs-revision"}

VALID_PIPELINE_PHASE = {
    "",  # empty = pre-pipeline or recurring
    "drafting",
    "drafted",
    "checked",
    "executing",
    "outcome-verifying",
    "complete",
}

# STATE_COHERENCE_FORBIDDEN covers only the `status` values with an explicit
# line in phase-state-machine.md's `### status` cheat sheet (PLAN-AL3 D1).
# It deliberately omits `blocked`, `partially-complete`, `cancelled`, and
# `closed` from VALID_STATUS: none of those carries a line in that section.
# `cancelled` in particular is not simply uncited - it has a line elsewhere,
# in the halt-and-abandon table rather than the `### status` cheat sheet -
# but D1 scoped this mapping to that one section, so `cancelled` is left out
# on the same basis as the other three rather than singled out.
STATE_COHERENCE_FORBIDDEN: dict[str, set[str]] = {
    # "After successful retire -> `status: done` (already set by
    # `execute-plan`; just confirm)." `execute-plan` only runs during
    # `executing`, which is reachable only after `checked`; `done` cannot
    # hold at any earlier phase.
    "done": {"drafting", "drafted", "checked"},
    # "Entering `executing` -> `status: in-progress`." The transition into
    # `executing` is the only place this value is set; `in-progress` cannot
    # hold at any earlier phase.
    "in-progress": {"drafting", "drafted", "checked"},
    # The same "Entering `executing` -> `status: in-progress`" line means
    # `ready` is always overwritten at that transition; `ready` cannot
    # survive into `executing` or any phase that follows.
    "ready": {"executing", "outcome-verifying", "complete"},
    # "Reverting from `executing`/`outcome-verifying` -> `drafted` ->
    # `status: needs-revision`." This is the only place the value is set,
    # and it always pairs with `pipeline_phase: drafted` in the same
    # transition; no other phase value is coherent with `needs-revision`.
    "needs-revision": {"drafting", "checked", "executing", "outcome-verifying", "complete"},
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

    # Widened 2026-07-29 (PLAN-AI3 Step 11) to also match the active
    # PLAN-[A-Z][A-Z][0-9] grammar (D2, plan-conventions.md "PLAN Identity
    # Policy"), not just the frozen historical PLAN-NNN form. Before this
    # widening, every active PLAN went unmatched and the required-key block
    # below was unreachable for any of them.
    # Widened 2026-08-03 (PLAN-AJ3) for the INPUT kind, which carries a datetime
    # rather than an allocated ID and so has no underscore separator. The same
    # alternation newly matches the datetime-grammar ADVICE files already on
    # disk, which the underscore-only form skipped silently.
    plan_pattern = re.compile(
        r"^(?P<kind>PLAN|INPUT|ADVICE|RESEARCH)-(?:\d{3,4}_|[A-Z]{2}\d_|\d{8}-\d{4}-)"
    )

    # The audit only enforces full schema_v2 fields on PLAN files. INPUT, and the
    # grandfathered ADVICE and RESEARCH, are looser-format context inputs (written
    # via write-input); checking their `type` field matches their filename prefix
    # is enough.
    type_for_prefix = {
        "PLAN": "plan",
        "INPUT": "input",
        "ADVICE": "advice",
        "RESEARCH": "research",
    }

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
        # Inputs have looser format (per write-input skill).
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
# Category: state-coherence
# ---------------------------------------------------------------------------

def check_state_coherence() -> list[Finding]:
    """Flag a PLAN whose `status` and `pipeline_phase` pairing is one
    phase-state-machine.md's `### status` cheat sheet proves impossible
    (PLAN-AL3 D1). Scoped to Workbench/*.md only, matching
    check_frontmatter_v2()'s scope (PLAN-AL3 D2) - Retired/ is frozen and
    out of scope for this check."""
    findings: list[Finding] = []
    workbench = REPO_ROOT / "Workbench"
    if not workbench.is_dir():
        return findings

    plan_pattern = re.compile(
        r"^(?P<kind>PLAN|INPUT|ADVICE|RESEARCH)-(?:\d{3,4}_|[A-Z]{2}\d_|\d{8}-\d{4}-)"
    )

    for plan_file in sorted(workbench.glob("*.md")):
        m = plan_pattern.match(plan_file.name)
        if not m or m.group("kind") != "PLAN":
            continue
        text = plan_file.read_text(encoding="utf-8")
        fm, _raw = _parse_frontmatter_text(text)
        if not fm:
            continue

        phase = fm.get("pipeline_phase")
        if not phase:
            # Empty/absent pipeline_phase is the accepted hand-executed-PLAN
            # escape valve (plan-conventions.md "Default for ad-hoc PLANs");
            # never checked against the table (PLAN-AL3 D1).
            continue

        status = fm.get("status")
        forbidden = STATE_COHERENCE_FORBIDDEN.get(status)
        if forbidden and phase in forbidden:
            rel = plan_file.relative_to(REPO_ROOT).as_posix()
            findings.append(Finding(
                category="state-coherence",
                severity="warn",
                file=rel,
                line=None,
                message=(
                    f"status={status!r} paired with pipeline_phase={phase!r} "
                    "is a pairing phase-state-machine.md's `### status` cheat "
                    "sheet proves impossible; see STATE_COHERENCE_FORBIDDEN "
                    "in scripts/audit-foundry.py for the citation."
                ),
            ))

    return findings


# ---------------------------------------------------------------------------
# Category: cross-refs
# ---------------------------------------------------------------------------

MARKDOWN_LINK_RE = re.compile(r"\[(?P<text>[^\]]*?)\]\((?P<target>[^)]+?)\)")

# Files to scan for cross-refs. Skips Workbench/ (PLANs may reference future paths)
# and Retired/ (frozen content).
CROSS_REF_DIRS = [".claude", "scripts"]
CROSS_REF_ROOT_FILES = ["README.md", "ARCHITECTURE.md", "CLAUDE.md"]


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
            files.extend(p for p in sorted(d.rglob("*.md")) if "/Retired/" not in p.as_posix())
    for fname in CROSS_REF_ROOT_FILES:
        p = REPO_ROOT / fname
        if p.exists():
            files.append(p)
    return files


def check_cross_refs() -> list[Finding]:
    findings: list[Finding] = []
    for source in _iter_markdown_files():
        text = source.read_text(encoding="utf-8")
        in_code_fence = False
        for line_num, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code_fence = not in_code_fence
                continue
            if in_code_fence:
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
                        message=f"Broken link: {target!r} -> {resolved.relative_to(REPO_ROOT) if str(resolved).startswith(str(REPO_ROOT)) else resolved} does not exist.",
                    ))
    return findings

# ---------------------------------------------------------------------------
# Category: artefact-filename  (PLAN-AH0 D5 - Hard-Validation)
# ---------------------------------------------------------------------------
#
# Classifies every HANDOFF / OBSERVATION / FOUNDRYREQ basename in
# Workbench/ and Retired/ via the shared validator.
# Only `malformed` produces a finding (severity: error); `conforming` and
# `legacy_permitted` are silent. Filenames outside the validator's scope
# (PLAN-*, INPUT-*, INDEX.md, etc.) are skipped without a finding.

def check_artefact_filenames() -> list[Finding]:
    findings: list[Finding] = []

    # Load the shared validator without hard-coding its path
    try:
        shared = REPO_ROOT / ".claude" / "skills" / "_shared"
        if str(shared) not in sys.path:
            sys.path.insert(0, str(shared))
        from validate_artefact_filename import classify_artefact_filename  # type: ignore
    except Exception as e:  # noqa: BLE001
        findings.append(Finding(
            category="artefact-filename",
            severity="error",
            file=".claude/skills/_shared/validate_artefact_filename.py",
            line=None,
            message=f"validator-unavailable: {type(e).__name__}: {e}",
        ))
        return findings

    scan_dirs = ["Workbench", "Retired"]
    prefixes = ("HANDOFF-", "OBSERVATION-", "FOUNDRYREQ-")

    for dirname in scan_dirs:
        d = REPO_ROOT / dirname
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            name = p.name
            # Only attempt classification for filenames that start with a known prefix
            if not any(name.upper().startswith(pfx) for pfx in prefixes):
                continue
            result, reason = classify_artefact_filename(name)
            if result == "malformed":
                findings.append(Finding(
                    category="artefact-filename",
                    severity="error",
                    file=p.relative_to(REPO_ROOT).as_posix(),
                    line=None,
                    message=f"malformed artefact filename: {reason}",
                ))
            # conforming and legacy_permitted are silent (no finding)
    return findings


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

# Category 'path-patterns' was removed by PLAN-AC4 D3. It was specifically a
# linter for cwd-relative `python plugins/<plugin>/...` invocations in
# markdown bodies that would break in consumer plugin installs. After
# PLAN-AC3 abandoned the plugin marketplace in favour of a portable bundle,
# the failure mode no longer exists (no plugins/ tree, no consumer install
# divergence). Future structural checks of the bundle's surface live in
# `cross-refs` or a new category, not here.

CATEGORIES = {
    "frontmatter-v2": check_frontmatter_v2,
    "cross-refs": check_cross_refs,
    "artefact-filename": check_artefact_filenames,
    "state-coherence": check_state_coherence,
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
            lines.append(f"- **[{f.severity}]** {loc} - {f.message}")
        lines.append("")
    return "\n".join(lines)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
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

    # Stable ordering - by category then by severity (errors first) then by file/line.
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
