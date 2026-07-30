"""
build_brief.py - Constructs audit briefs for the plan-pipeline orchestrator.

Usage (CLI):
    python build_brief.py <plan_path> <auditor> <iteration>

    auditor: "sufficiency" | "plan_safety"
    iteration: integer >= 1

Outputs the brief markdown to stdout.

The orchestrator runs this as a subprocess and captures stdout:
    python build_brief.py <plan_path> <auditor> <iteration> > /tmp/audit_brief_<plan-id>.md

Precondition check (PLAN-AE0, 2026-05-26):
    Before building any brief where audit_state.last_stage != none (i.e. any audit
    dispatch after the very first sufficiency run), the helper verifies that the prior
    audit produced the expected two-commit pair in git history:
        1. "plan-pipeline: audit_state update - <stage>:<outcome>"
        2. "plan-pipeline: record last_audit_commit for <plan-id>"

    This is belt-and-braces against the skip-pattern that motivated PLAN-AE0. The
    happy path is covered by audit_loop.apply_audit_outcome(); this check fires loudly
    if the helper was not called (or its second commit was omitted).

    AE0 grandfather cutoff: max(plan_created_date, AE0_SHIP_DATE="2026-05-26").
    PLANs whose audit cycle started before AE0 shipped are exempt from the check for
    that prior cycle. After AE0 has been in production for >=1 week without false
    positives, consider tightening to just plan_created_date.

    TODO(post-AE0-retire): once 'plan-pipeline: retired PLAN-AE0_*' commit exists,
    revise build_brief.py to derive AE0_ship_date dynamically via git log lookup;
    remove hardcoded fallback.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path


class OrchestratorException(Exception):
    """Raised when brief construction cannot proceed due to missing data or config errors."""
    pass


def _load_frontmatter(plan_path: Path) -> dict:
    """
    Parse YAML frontmatter from a PLAN file.
    Returns the frontmatter as a dict (subset - only fields needed for brief construction).
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


def _short_plan_id(plan_path: Path) -> str:
    """
    Derive the canonical short plan-id (PLAN-XX# from the AA-form), matching
    audit_loop.py's PLAN_ID_RE convention, with the full stem as fallback for
    non-AA ids. audit_loop writes .audit snapshots and `record last_audit_commit`
    commits keyed on this short id; build_brief must use the same to locate them.
    See PLAN-AE10.
    """
    m = re.match(r"(PLAN-[A-Z]{2}\d)_", plan_path.stem)
    return m.group(1) if m else plan_path.stem


def _audit_file_path(plan_path: Path, stage: str, iteration: int) -> Path:
    """
    Return the path to the audit JSON for the given plan, stage, and iteration.
    Workbench/.audit/<short-plan-id>-<stage>-<iter>.json - matches audit_loop.py's
    output naming exactly (short id + stage segment). See PLAN-AE10.
    """
    plan_id = _short_plan_id(plan_path)
    workbench_dir = plan_path.parent
    return workbench_dir / ".audit" / f"{plan_id}-{stage}-{iteration}.json"


def _load_prior_audit(plan_path: Path, stage: str, iteration: int) -> dict:
    """
    Load the prior iteration's audit JSON for the given stage.
    Raises OrchestratorException if missing.
    """
    prior_iter = iteration - 1
    audit_path = _audit_file_path(plan_path, stage, prior_iter)
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
            encoding="utf-8",
            errors="replace",
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
        fp = f.get("fingerprint", "-")
        code = f.get("code", "-")
        level = f.get("level", "-")
        category = f.get("category", "-")
        location = f.get("location", "-").replace("|", "\\|")
        message = f.get("message", "-").replace("|", "\\|")
        # Trim message to keep table readable
        if len(message) > 120:
            message = message[:117] + "..."
        lines.append(f"| `{fp}` | {code} | {level} | {category} | {location} | {message} |")

    return "\n".join(lines) + "\n"


def _finding_fingerprint(finding: dict) -> str:
    """8-char finding fingerprint. MUST stay in lockstep with
    audit_loop._compute_fingerprint and auditor-schema-v2.md (fingerprint
    definition). sha256(code|level|category|location)[:8]."""
    raw = f"{finding.get('code', '')}|{finding.get('level', '')}|{finding.get('category', '')}|{finding.get('location', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# AE0 grandfather cutoff constant
# ---------------------------------------------------------------------------

AE0_SHIP_DATE = "2026-05-26"
"""
Hardcoded AE0 ship date. Used as a minimum `--since` cutoff for the precondition
git log search so that PLANs whose audit cycle predates AE0 are exempt.

TODO(post-AE0-retire): derive this dynamically from:
    git log --grep="plan-pipeline: retired PLAN-AE0_" -n 1 --format=%cI
Once the retire commit exists, remove this hardcoded constant and derive via
subprocess. Until then, use this literal as the fallback.
"""


# ---------------------------------------------------------------------------
# Precondition check helpers
# ---------------------------------------------------------------------------

def _load_audit_state_from_plan(plan_path: Path) -> dict:
    """
    Parse audit_state block from PLAN frontmatter.
    Returns a dict with at least: last_stage, last_outcome, last_audit_commit.
    Uses a line-by-line parser to avoid PyYAML block parse ambiguity on nested keys.
    Falls back to empty dict on any parse failure (safe - caller interprets missing
    last_stage as 'none').
    """
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return {}

    if not text.startswith("---"):
        return {}

    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}

    fm_lines = parts[1].splitlines()

    # Find the audit_state block and parse its children
    in_audit_state = False
    audit_state: dict = {}
    for line in fm_lines:
        if re.match(r"^audit_state\s*:", line):
            in_audit_state = True
            continue
        if in_audit_state:
            # Child lines start with 2 spaces (standard YAML indent)
            m = re.match(r"^  (\w+)\s*:\s*(.*)$", line)
            if m:
                key = m.group(1)
                value = m.group(2).strip().strip('"').strip("'")
                audit_state[key] = value
            elif line and not line.startswith(" "):
                # Exited the audit_state block
                in_audit_state = False

    return audit_state


def _check_audit_loop_precondition(
    plan_path: Path,
    plan_id: str,
    audit_state: dict,
    repo_root: Path,
) -> None:
    """
    Verify that the prior audit produced the expected two-commit pair in git history.

    Fires whenever audit_state.last_stage != none (i.e. whenever the PLAN has been
    through at least one audit dispatch). Skipped for sufficiency iter 1 (no prior).

    Per SUF-VAL-001 (PLAN-AE0): do NOT use --all-match (would require both patterns
    in every commit, producing an empty result with OR-only patterns). Instead, run
    a single git log with default OR semantics and post-filter pairs in Python.

    Per SUF-ASM-001 (PLAN-AE0): the precondition uses --since=max(plan_created,
    AE0_SHIP_DATE) so pre-AE0 PLANs are grandfathered.

    A Surface 3 human override is a third valid provenance artefact. It advances the
    stage on the human's decision rather than an auditor return, so apply_audit_outcome
    never runs and neither housekeeping commit exists; the override's own commit
    template is the record of that transition and no SHA-record commit is paired to it.

    Raises:
        SystemExit(2): if the commit-pair housekeeping is absent.
    """
    last_stage = audit_state.get("last_stage", "none") or "none"
    last_outcome = audit_state.get("last_outcome", "none") or "none"
    last_audit_commit = audit_state.get("last_audit_commit", "") or ""

    # Guard: if last_stage == none, there is no prior audit to check against.
    # This is sufficiency iter 1 - precondition is intentionally skipped.
    if last_stage == "none":
        return

    # Compute since cutoff: max(plan_created_date, AE0_SHIP_DATE)
    # plan_created_date is in frontmatter as "created: YYYY-MM-DD"
    plan_created = _parse_plan_created(plan_path)
    ae0_date = date.fromisoformat(AE0_SHIP_DATE)
    plan_date = date.fromisoformat(plan_created) if plan_created else ae0_date
    since_date = max(plan_date, ae0_date).isoformat()

    # Run git log with OR semantics (no --all-match) + two grep patterns.
    # Per SUF-VAL-001: do NOT use --all-match (empty result with disjoint patterns).
    try:
        git_result = subprocess.run(
            [
                "git", "log",
                "--grep", "plan-pipeline: audit_state update",
                "--grep", "plan-pipeline: record last_audit_commit",
                # A Surface 3 override advances the stage without an auditor return,
                # so it writes its own commit template instead of the pair above.
                "--grep", "plan-pipeline: human-override",
                "--since", f"{since_date} 00:00:00",
                "-n", "40",
                "--format=%H %s",
                # AG6: restrict to commits touching THIS plan file so a batch of other
                # plans' housekeeping commits cannot shadow the target's update commit
                # (update_pattern carries no plan_id). Both apply_audit_outcome commits
                # stage the plan file, so this filters cleanly. Idiom matches _get_git_diff.
                "--", str(plan_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(repo_root),
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        # Cannot verify - fail safe: allow the build to proceed with a warning.
        print(
            f"build_brief: precondition check skipped - git unavailable ({e})",
            file=sys.stderr,
        )
        return

    lines = [line.strip() for line in git_result.stdout.strip().splitlines() if line.strip()]
    # Parse into (sha, subject) tuples
    commits: list[tuple[str, str]] = []
    for line in lines:
        parts = line.split(" ", 1)
        sha = parts[0]
        subject = parts[1] if len(parts) > 1 else ""
        commits.append((sha, subject))

    # Post-filter: find most recent audit_state update for THIS plan_id.
    # Note: commit messages use plain hyphen " - " (not em-dash) for cross-platform
    # git log compatibility. Windows git subprocess stdout may mangle multi-byte chars.
    update_pattern = f"audit_state update - {last_stage}:{last_outcome}"
    # audit_loop.py writes its `record last_audit_commit for <short-id>` commit with
    # the short AA-form id; match the same here (build_brief otherwise uses the full
    # slugged stem, which never matches). See PLAN-AE10.
    record_pattern = f"record last_audit_commit for {_short_plan_id(plan_path)}"

    update_idx: int | None = None
    update_sha: str = ""
    for i, (sha, subject) in enumerate(commits):
        if update_pattern in subject:
            update_idx = i
            update_sha = sha
            break

    # A Surface 3 override advances the stage on the human's decision rather than on
    # an auditor return, so `apply_audit_outcome` never runs and neither housekeeping
    # commit is written. Its own template (`plan-pipeline: human-override <phase>
    # <stage> for <plan-filename>`) IS the provenance artefact for that transition.
    # Accept it, and do not look for a paired SHA-record commit: the override writes
    # no `last_audit_commit`, so demanding one would fail every overridden PLAN.
    # Without this branch a documented human lever leaves the PLAN in a state this
    # function refuses to read - found by dogfooding on PLAN-AI7, 2026-07-31.
    if update_idx is None:
        for sha, subject in commits:
            if "human-override" in subject and last_stage in subject:
                print(
                    f"build_brief: {last_stage} provenance satisfied by human override "
                    f"{sha[:8]} ({subject.strip()}); skipping the audit_state commit-pair "
                    f"check, which does not apply to the override path.",
                    file=sys.stderr,
                )
                return

    if update_idx is None:
        print(
            f"build_brief: housekeeping artefact missing - no recent "
            f"'audit_state update - {last_stage}:{last_outcome}' commit found for "
            f"{plan_id} since {since_date}; PLAN frontmatter claims "
            f"audit_state.last_stage={last_stage}, last_outcome={last_outcome}, "
            f"last_audit_commit={last_audit_commit} but git history disagrees. "
            f"Repair via audit_loop.apply_audit_outcome() or manually.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    # AG6: scan the (up to) two commits IMMEDIATELY NEWER than the update
    # commit (indices update_idx-1, update_idx-2) for the paired record commit.
    # The prior loop scanned from i=0 (newest) and broke as soon as
    # update_idx - i > 2, so under batch/interleaved housekeeping (>2 audit
    # commits newer than the target's update) it broke at i=0 before ever
    # reaching the real paired record at update_idx-1. See PLAN-AG6 / AF6 dogfood.
    pair_found = False
    for i in range(max(0, update_idx - 2), update_idx):
        _, subject = commits[i]
        if record_pattern in subject:
            pair_found = True
            break

    if not pair_found:
        print(
            f"build_brief: housekeeping skip detected - found audit_state update commit "
            f"{update_sha} for {plan_id} but no paired "
            f"'record last_audit_commit for {plan_id}' within 2 subsequent commits. "
            f"Repair via audit_loop.apply_audit_outcome() or manually create the "
            f"SHA-record commit. See PLAN-AE0 Notes for executor.",
            file=sys.stderr,
        )
        raise SystemExit(2)


def _parse_plan_created(plan_path: Path) -> str | None:
    """
    Extract the 'created: YYYY-MM-DD' field from PLAN frontmatter.
    Returns the date string or None if not found.
    """
    try:
        text = plan_path.read_text(encoding="utf-8")
    except OSError:
        return None

    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    for line in parts[1].splitlines():
        m = re.match(r"^created\s*:\s*(\d{4}-\d{2}-\d{2})", line)
        if m:
            return m.group(1)

    return None


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

    # ------------------------------------------------------------------
    # Iteration ceiling (PLAN-AI5 follow-up).
    # This is the enforcement point for MAX_ITERATIONS. It sits here rather
    # than in audit_loop.py because the orchestrator cannot dispatch an
    # auditor without a brief, so refusing to build one stops the loop
    # before the dispatch is paid for. Enforcing after the audit would halt
    # a loop that had already spent the tokens it was meant to save.
    # The iteration is derived from the audit JSONs on disk, not trusted
    # from the caller.
    # ------------------------------------------------------------------
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from audit_loop import derive_next_iteration

    _audit_dir = plan_path.parent / ".audit"
    _derived = derive_next_iteration(_audit_dir, _short_plan_id(plan_path), auditor)
    if _derived > max_iterations:
        raise OrchestratorException(
            f"audit loop did not converge after {max_iterations} iterations on "
            f"{auditor}. Refusing to build a brief for iteration {_derived}. "
            f"The PLAN needs a human decision, not another lap."
        )

    # ------------------------------------------------------------------
    # Precondition fingerprint check (PLAN-AE0, D3')
    # Fire whenever audit_state.last_stage != none. Skip only for
    # sufficiency iter 1 (the very first audit, where there is no prior).
    # ------------------------------------------------------------------
    _plan_audit_state = _load_audit_state_from_plan(plan_path)
    _last_stage = _plan_audit_state.get("last_stage", "none") or "none"
    if _last_stage != "none":
        # There has been at least one prior audit - check the commit-pair exists.
        _repo_root = plan_path.parent.parent  # Workbench/ parent = repo root
        _plan_id = plan_path.stem
        # Strip .md suffix from stem if present (stem already excludes it via Path.stem)
        _check_audit_loop_precondition(
            plan_path=plan_path,
            plan_id=_plan_id,
            audit_state=_plan_audit_state,
            repo_root=_repo_root,
        )

    auditor_label = "Sufficiency Auditor" if auditor == "sufficiency" else "Plan-Safety Auditor"
    code_namespace = "S" if auditor == "sufficiency" else "H"
    # PLAN-AG2: plan-safety's mechanical checks (audit-haiku-safe Steps 4a-4d)
    # emit four auxiliary code families the widened auditor-schema-v2 pattern
    # admits but which are outside the primary {code_namespace}### namespace.
    # Sufficiency never emits these - the clause is gated off for that auditor.
    aux = (
        " Plan-safety may also emit auxiliary families SFV###, PPV###, PSZ###, and FAL###(-a..-f)."
        if auditor != "sufficiency"
        else ""
    )

    title = _load_plan_title(plan_path)
    objective = _load_plan_objective(plan_path)
    plan_id = plan_path.stem

    if iteration == 1:
        # --- First-iteration brief ---
        brief = f"""# Audit Brief - {auditor_label}

**Mode:** first iteration
**PLAN:** {title}
**Plan ID:** {plan_id}
**Auditor:** {auditor}
**Iteration:** {iteration} of {max_iterations}

---

## Task

You are the **{auditor_label}**. Review the PLAN at the path provided and return a structured audit result using the v2 schema (codes `{code_namespace}001`-`{code_namespace}699`, `{code_namespace}999` for OTHER).{aux} See your SKILL.md for the full procedure.

---

## PLAN Summary

**Objective:**

{objective}

---

## Boundaries

- This is a **first-iteration audit** - no prior findings to reconcile.
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
        prior_audit = _load_prior_audit(plan_path, auditor, iteration)
        # audit_loop.py writes the raw auditor <pipeline-result> JSON, whose findings
        # live at diagnostics.findings. Older/normalised snapshots may use top-level
        # findings; read defensively so both shapes render. See PLAN-AG6 / RESEARCH-006.
        prior_findings = prior_audit.get("diagnostics", {}).get("findings")
        if not prior_findings:
            prior_findings = prior_audit.get("findings", [])

        # Acknowledged and disputed fingerprints (from PLAN frontmatter, passed via audit_state or separately)
        # These are not in audit_state itself; caller may pass them in audit_state under extra keys.
        acknowledged_fps = audit_state.get("_acknowledged_fingerprints", [])
        disputed_fps = audit_state.get("_disputed_fingerprints", [])

        # Populate fingerprint on any finding lacking one so ack-filter and
        # _render_findings_table see a real value (raw-shape on-disk findings carry none).
        for _f in prior_findings:
            if not _f.get("fingerprint"):
                _f["fingerprint"] = _finding_fingerprint(_f)

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
                    f"- `{f.get('fingerprint')}` - {f.get('code')} / {f.get('message', '')[:100]}"
                    for f in disputed_in_prior
                )
                dispute_section = f"""
## Disputed Findings (Human contests these)

The Human has disputed the following findings. Review the PLAN revision and classify each as `disputed-and-reaffirmed` (still valid) or `disputed-and-dropped` (withdrawn).

{dispute_lines}
"""

        brief = f"""# Audit Brief - {auditor_label}

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
- All findings use codes from `{code_namespace}001`-`{code_namespace}699` / `{code_namespace}999`.{aux}
- Return a `<pipeline-result>` JSON block per your SKILL.md output schema.
"""
        return brief


def main():
    """CLI entry point for smoke testing."""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    import argparse
    parser = argparse.ArgumentParser(
        description="Build an audit brief for the plan-pipeline orchestrator."
    )
    parser.add_argument("plan_path", help="Path to the PLAN .md file")
    parser.add_argument("auditor", choices=["sufficiency", "plan_safety"], help="Auditor type")
    parser.add_argument("iteration", type=int, help="Audit iteration number (1 = first)")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Write brief to this file path instead of stdout. "
             "Preferred over shell redirect - avoids silently empty files when "
             "the orchestrator omits the redirect.",
    )
    args = parser.parse_args()

    plan_path = Path(args.plan_path)

    try:
        # Re-audit briefs (iteration > 1) require the PLAN's audit_state (for the
        # prior-snapshot load + diff anchor). Load it from frontmatter so the CLI
        # can build re-audit briefs, not just first-iteration ones. See PLAN-AE10.
        audit_state = _load_audit_state_from_plan(plan_path) if args.iteration > 1 else None
        brief = build_audit_brief(plan_path, args.auditor, args.iteration, audit_state=audit_state)
        if args.output:
            Path(args.output).write_text(brief, encoding="utf-8")
        else:
            print(brief)
    except OrchestratorException as e:
        print(f"OrchestratorException: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
