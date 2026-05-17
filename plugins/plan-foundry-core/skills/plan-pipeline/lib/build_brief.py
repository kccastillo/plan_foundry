"""
build_brief.py — Constructs audit briefs for the plan-pipeline orchestrator.

Usage (CLI):
    python build_brief.py <plan_path> <auditor> <iteration>

    auditor: "sufficiency" | "plan_safety"
    iteration: integer >= 1

Outputs the brief markdown to stdout.

The orchestrator runs this as a subprocess and captures stdout:
    python build_brief.py <plan_path> <auditor> <iteration> > /tmp/audit_brief_<plan-id>.md
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path


class OrchestratorException(Exception):
    """Raised when brief construction cannot proceed due to missing data or config errors."""
    pass


def _load_frontmatter(plan_path: Path) -> dict:
    """
    Parse YAML frontmatter from a PLAN file.
    Returns the frontmatter as a dict (subset — only fields needed for brief construction).
    """
    text = plan_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise OrchestratorException(f"PLAN file has no frontmatter: {plan_path}")

    # Extract the YAML block between the first two ---
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise OrchestratorException(f"PLAN file frontmatter is malformed: {plan_path}")

    frontmatter_text = parts[1].strip()
    body = parts[2].strip()

    # Minimal key-value parse (no PyYAML dependency assumption)
    fm = {}
    for line in frontmatter_text.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("#"):
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Remove inline comments
            if "#" in value:
                value = value[:value.index("#")].strip()
            # Strip quotes
            value = value.strip('"').strip("'")
            fm[key] = value

    fm["_body"] = body
    return fm


def _load_plan_title(plan_path: Path) -> str:
    """Extract the PLAN title from frontmatter."""
    fm = _load_frontmatter(plan_path)
    return fm.get("title", plan_path.stem)


def _load_plan_objective(plan_path: Path) -> str:
    """Extract the Objective section from the PLAN body."""
    text = plan_path.read_text(encoding="utf-8")
    match = re.search(r"^## Objective\s*\n(.*?)(?=^##|\Z)", text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return "(No Objective section found)"


def _audit_file_path(plan_path: Path, iteration: int) -> Path:
    """
    Return the path to the audit JSON for the given plan and iteration.
    Workbench/.audit/<plan-id>-<iter>.json
    """
    # plan-id = filename without .md
    plan_id = plan_path.stem
    # Workbench dir = parent of plan file
    workbench_dir = plan_path.parent
    return workbench_dir / ".audit" / f"{plan_id}-{iteration}.json"


def _load_prior_audit(plan_path: Path, iteration: int) -> dict:
    """
    Load the prior iteration's audit JSON.
    Raises OrchestratorException if missing.
    """
    prior_iter = iteration - 1
    audit_path = _audit_file_path(plan_path, prior_iter)
    if not audit_path.exists():
        raise OrchestratorException(
            f"Prior audit file not found: {audit_path}. "
            f"Cannot construct re-audit brief for iteration {iteration}."
        )
    with open(audit_path, encoding="utf-8") as f:
        return json.load(f)


def _get_git_diff(plan_path: Path, last_audit_commit: str) -> str:
    """
    Compute the unified diff of the PLAN file anchored at last_audit_commit.
    Returns the diff string (may be empty if no changes).
    Raises OrchestratorException if commit SHA is missing or git fails.
    """
    if not last_audit_commit:
        raise OrchestratorException(
            "audit_state.last_audit_commit is empty. "
            "Cannot anchor diff for re-audit brief. "
            "Ensure the orchestrator records the commit SHA after each audit_state write."
        )

    try:
        result = subprocess.run(
            ["git", "diff", last_audit_commit, "--", str(plan_path)],
            capture_output=True,
            text=True,
            cwd=str(plan_path.parent.parent),  # repo root (parent of Workbench)
            timeout=30,
        )
        if result.returncode != 0:
            raise OrchestratorException(
                f"git diff failed (exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout
    except FileNotFoundError:
        raise OrchestratorException("git not found on PATH. Cannot compute diff for re-audit brief.")
    except subprocess.TimeoutExpired:
        raise OrchestratorException("git diff timed out after 30 seconds.")


def _truncate_diff(diff: str, max_tokens: int = 3000) -> tuple[str, bool]:
    """
    Truncate diff to approximately max_tokens tokens.
    Uses a rough 4-chars-per-token heuristic.
    Returns (truncated_diff, was_truncated).
    """
    max_chars = max_tokens * 4  # rough heuristic
    if len(diff) <= max_chars:
        return diff, False
    return diff[:max_chars] + "\n[... DIFF TRUNCATED ...]", True


def _render_findings_table(findings: list) -> str:
    """Render a findings list as a markdown table."""
    if not findings:
        return "_No findings in prior iteration._\n"

    lines = [
        "| Fingerprint | Code | Level | Category | Location | Message |",
        "|---|---|---|---|---|---|",
    ]
    for f in findings:
        fp = f.get("fingerprint", "—")
        code = f.get("code", "—")
        level = f.get("level", "—")
        category = f.get("category", "—")
        location = f.get("location", "—").replace("|", "\\|")
        message = f.get("message", "—").replace("|", "\\|")
        # Trim message to keep table readable
        if len(message) > 120:
            message = message[:117] + "..."
        lines.append(f"| `{fp}` | {code} | {level} | {category} | {location} | {message} |")

    return "\n".join(lines) + "\n"


def build_audit_brief(
    plan_path: str | Path,
    auditor: str,
    iteration: int,
    audit_state: dict | None = None,
    max_iterations: int = 5,
) -> str:
    """
    Build the audit brief for the given PLAN and auditor.

    Args:
        plan_path: Path to the PLAN .md file.
        auditor: "sufficiency" or "plan_safety".
        iteration: Current audit iteration (1 = first time, 2+ = re-audit).
        audit_state: Dict with keys matching audit_state frontmatter block.
                     Required when iteration > 1.
        max_iterations: Gate value (brief warns if approaching limit).

    Returns:
        Markdown string to be used as the auditor's user-message content.

    Raises:
        OrchestratorException: On missing prior audit, missing commit SHA, or empty diff.
    """
    plan_path = Path(plan_path)
    if not plan_path.exists():
        raise OrchestratorException(f"PLAN file not found: {plan_path}")

    auditor_label = "Sufficiency Auditor" if auditor == "sufficiency" else "Plan-Safety Auditor"
    code_namespace = "S" if auditor == "sufficiency" else "H"

    title = _load_plan_title(plan_path)
    objective = _load_plan_objective(plan_path)
    plan_id = plan_path.stem

    if iteration == 1:
        # --- First-iteration brief ---
        brief = f"""# Audit Brief — {auditor_label}

**Mode:** first iteration
**PLAN:** {title}
**Plan ID:** {plan_id}
**Auditor:** {auditor}
**Iteration:** {iteration} of {max_iterations}

---

## Task

You are the **{auditor_label}**. Review the PLAN at the path provided and return a structured audit result using the v2 schema (codes `{code_namespace}001`–`{code_namespace}699`, `{code_namespace}999` for OTHER). See your SKILL.md for the full procedure.

---

## PLAN Summary

**Objective:**

{objective}

---

## Boundaries

- This is a **first-iteration audit** — no prior findings to reconcile.
- Apply all {"seven" if auditor == "sufficiency" else "five"} {"lenses" if auditor == "sufficiency" else "plan-safety criteria"} in full.
- Classify every finding with a code from `references/auditor-codes.md`.
- Return a `<pipeline-result>` JSON block per your SKILL.md output schema.
"""
        return brief

    else:
        # --- Re-audit brief ---
        if audit_state is None:
            raise OrchestratorException(
                f"audit_state is required for re-audit brief (iteration={iteration})"
            )

        last_audit_commit = audit_state.get("last_audit_commit", "")
        prior_audit = _load_prior_audit(plan_path, iteration)
        prior_findings = prior_audit.get("findings", [])

        # Acknowledged and disputed fingerprints (from PLAN frontmatter, passed via audit_state or separately)
        # These are not in audit_state itself; caller may pass them in audit_state under extra keys.
        acknowledged_fps = audit_state.get("_acknowledged_fingerprints", [])
        disputed_fps = audit_state.get("_disputed_fingerprints", [])

        # Filter: remove acknowledged findings from prior table (defensive; orchestrator also strips)
        visible_prior_findings = [
            f for f in prior_findings if f.get("fingerprint") not in acknowledged_fps
        ]

        # Compute diff
        diff_text = _get_git_diff(plan_path, last_audit_commit)
        if not diff_text.strip():
            raise OrchestratorException(
                f"git diff against commit {last_audit_commit} produced an empty diff. "
                "This likely means the PLAN was not modified since the last audit. "
                "Ensure the Human has revised the PLAN before re-auditing."
            )

        diff_truncated, was_truncated = _truncate_diff(diff_text)
        diff_size_warning = ""
        if len(diff_text) > 5000 * 4:
            diff_size_warning = "\n> **INDEX ALERT:** This diff exceeds 5000 tokens. It will be flagged as an oversized diff in the Workbench INDEX.\n"

        # Acknowledged list
        ack_section = ""
        if acknowledged_fps:
            ack_lines = "\n".join(f"- `{fp}`" for fp in acknowledged_fps)
            ack_section = f"""
## Acknowledged Findings (do not re-emit)

The Human has acknowledged the following fingerprints. Do **not** include these in your returned findings array.

{ack_lines}
"""

        # Disputed list
        dispute_section = ""
        if disputed_fps:
            disputed_in_prior = [
                f for f in prior_findings if f.get("fingerprint") in disputed_fps
            ]
            if disputed_in_prior:
                dispute_lines = "\n".join(
                    f"- `{f.get('fingerprint')}` — {f.get('code')} / {f.get('message', '')[:100]}"
                    for f in disputed_in_prior
                )
                dispute_section = f"""
## Disputed Findings (Human contests these)

The Human has disputed the following findings. Review the PLAN revision and classify each as `disputed-and-reaffirmed` (still valid) or `disputed-and-dropped` (withdrawn).

{dispute_lines}
"""

        brief = f"""# Audit Brief — {auditor_label}

**Mode:** re-audit
**PLAN:** {title}
**Plan ID:** {plan_id}
**Auditor:** {auditor}
**Iteration:** {iteration} of {max_iterations}
**Diff anchored at commit:** `{last_audit_commit}`

---

## Task

You are the **{auditor_label}** in **Re-Audit Mode**. Review the PLAN revision and:

1. Status each prior finding (resolved / still-present / disputed-and-reaffirmed / disputed-and-dropped).
2. Identify any new findings.
3. Do not re-emit acknowledged findings (listed below).

Apply {"all seven lenses" if auditor == "sufficiency" else "all five plan-safety criteria"} but focus primarily on the diff.

---

## Prior Findings ({len(prior_findings)} total, {len(visible_prior_findings)} shown after excluding acknowledged)

{_render_findings_table(visible_prior_findings)}
{ack_section}{dispute_section}
---

## PLAN Diff (since commit `{last_audit_commit}`)
{diff_size_warning}
```diff
{diff_truncated}
```

---

## Boundaries

- Status **every** prior finding shown above (even if unchanged).
- New findings use `status: new` (or omit the field).
- All findings use codes from `{code_namespace}001`–`{code_namespace}699` / `{code_namespace}999`.
- Return a `<pipeline-result>` JSON block per your SKILL.md output schema.
"""
        return brief


def main():
    """CLI entry point for smoke testing."""
    if len(sys.argv) < 4:
        print(
            "Usage: python build_brief.py <plan_path> <auditor> <iteration>",
            file=sys.stderr,
        )
        sys.exit(1)

    plan_path = Path(sys.argv[1])
    auditor = sys.argv[2]
    iteration = int(sys.argv[3])

    if auditor not in ("sufficiency", "plan_safety"):
        print(f"Error: auditor must be 'sufficiency' or 'plan_safety', got '{auditor}'", file=sys.stderr)
        sys.exit(1)

    try:
        brief = build_audit_brief(plan_path, auditor, iteration)
        print(brief)
    except OrchestratorException as e:
        print(f"OrchestratorException: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
