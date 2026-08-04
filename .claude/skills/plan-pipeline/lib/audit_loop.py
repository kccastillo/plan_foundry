"""
audit_loop.py - Single helper for audit-loop housekeeping in plan-pipeline section 4B.

Bundles five previously-manual steps into one atomic call:
  1. Write auditor return JSON to Workbench/.audit/<plan-id>-<stage>-<iteration>.json
  2. Strip acknowledged findings (defensive; auditor may re-emit)
  3. Compute recurrence fingerprints (basis for [STUCK xN] badge)
  4. Mutate PLAN frontmatter (audit_state.last_stage, last_outcome, <stage>_iterations)
  5. Two git commits:
       - "plan-pipeline: audit_state update - <stage>:<outcome>"
       - "plan-pipeline: record last_audit_commit for <plan-id>"

Usage (library):
    from audit_loop import apply_audit_outcome
    result = apply_audit_outcome(plan_path, stage, audit_return_json, iteration)

Usage (CLI - invoked by dispatch.md orchestrator via subprocess):
    python audit_loop.py <plan_path> <stage> <audit_json_path> <iteration>
    # Outputs JSON result dict to stdout, and nothing else. Every git subprocess
    # this module runs captures its own output, so stdout carries the JSON alone
    # and `json.loads(result.stdout)` is safe. Do not merge stderr into that
    # stream when invoking the CLI - git writes CRLF and lock warnings there.

The orchestrator writes the auditor's <pipeline-result> JSON body to a temp file
(Workbench/.audit-tmp/<plan-id>-<stage>-<iteration>.json) before invoking the CLI,
to avoid shell-quoting hazards on long JSON bodies. The helper reads from disk.

Return dict schema:
    {
        "outcome": str,               # "success" | "revision_needed" | "exception"
        "review_text": str,           # payload.review_text from auditor return
        "audit_json_path": str,       # canonical snapshot path
        "stripped_count": int,        # count of acknowledged findings stripped
        "recurring_fingerprints": list[str],  # fingerprints recurring from prior iter
        "last_audit_commit": str,     # short SHA (8 chars) of the audit_state commit
        "plan_id": str,               # e.g. "PLAN-AE0"
    }

Recovery path (S2 from PLAN-AE0 Notes):
    If the helper crashes between commit 1 (audit_state update) and commit 2
    (record last_audit_commit), the PLAN's on-disk frontmatter will have new
    last_stage/last_outcome from the in-memory mutation but last_audit_commit
    will be empty. To recover:
      1. Run `git log --grep "plan-pipeline: audit_state update" -n 5 --format=%H %s`
         to find the SHA of commit 1.
      2. Re-run apply_audit_outcome with the same arguments - the helper writes the
         audit JSON (idempotent), re-applies frontmatter mutations, and tries both
         commits again. The first commit will fail if the file hasn't changed since
         commit 1; if so, skip it and proceed directly to the second commit.
      Alternatively, manually create the second commit:
         git add <plan_path>
         git commit -m "plan-pipeline: record last_audit_commit for <plan-id>"

PLAN-AE0, 2026-05-26
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLAN_ID_RE = re.compile(r"(PLAN-[A-Z]{2}\d)_")

# Hard ceiling on audit iterations per stage. Enforced in code at two points:
# here, when the counter is derived, and in build_brief.py, which refuses to
# build a brief for an iteration past the ceiling so the cap bites before the
# dispatch is paid for rather than after. Until PLAN-AI5 this value existed
# only in prose and no code path compared a counter to it.
MAX_ITERATIONS = 5

# Audit JSON filenames have used two forms: the current "<plan-id>-<stage>-<N>"
# and an older "<plan-id>-<stage>-iterN". Both are recognised when deriving the
# iteration so a PLAN audited under the old convention keeps its history.
_ITER_SUFFIX_RE = re.compile(r"-(?:iter)?(\d+)$")


# ---------------------------------------------------------------------------
# Helpers: plan-id extraction
# ---------------------------------------------------------------------------

def extract_plan_id(plan_path: Path) -> str:
    """Extract PLAN-XX0 id from the file's basename."""
    basename = plan_path.name
    m = PLAN_ID_RE.match(basename)
    if m:
        return m.group(1)
    # Fallback: stem without .md
    return plan_path.stem


_extract_plan_id = extract_plan_id


# ---------------------------------------------------------------------------
# Helpers: PLAN frontmatter read/write
# ---------------------------------------------------------------------------

def _read_frontmatter_raw(plan_path: Path) -> tuple[str, str, str]:
    """
    Split a PLAN file into (pre_marker, frontmatter_text, body).
    pre_marker is '---\n', frontmatter_text is between the two ---, body is the rest.
    Raises ValueError if frontmatter is missing or malformed.
    """
    text = plan_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"PLAN file has no frontmatter: {plan_path}")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"PLAN file frontmatter is malformed: {plan_path}")
    # parts[0] is empty string (before the first ---), parts[1] is the YAML, parts[2] is body
    return parts[0], parts[1], parts[2]


def _write_frontmatter(plan_path: Path, fm: dict, body: str) -> None:
    """Write updated frontmatter back to the PLAN file."""
    fm_text = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
    new_text = f"---\n{fm_text}---{body}"
    plan_path.write_text(new_text, encoding="utf-8")


def _load_frontmatter(plan_path: Path) -> tuple[dict, str]:
    """
    Load PLAN frontmatter as a dict and return (fm_dict, body_text).
    body_text includes the leading newline after '---'.
    """
    _, fm_text, body = _read_frontmatter_raw(plan_path)
    fm = yaml.safe_load(fm_text) or {}
    return fm, body


# ---------------------------------------------------------------------------
# Helpers: fingerprint computation
# ---------------------------------------------------------------------------

def _compute_fingerprint(finding: dict) -> str:
    """
    Compute an 8-char fingerprint for a finding.
    sha256(code|level|category|location)[:8]
    """
    raw = f"{finding.get('code', '')}|{finding.get('level', '')}|{finding.get('category', '')}|{finding.get('location', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


# ---------------------------------------------------------------------------
# Helpers: iteration derivation
# ---------------------------------------------------------------------------

class AuditCeilingReached(Exception):
    """Raised when a stage would run past MAX_ITERATIONS."""


def derive_next_iteration(audit_dir: Path, plan_id: str, stage: str) -> int:
    """
    Derive the iteration number for the audit about to be recorded.

    Reads the audit JSONs already on disk for this PLAN and stage, and returns
    one past the highest. Returns 1 when none exist. The caller does not supply
    this number: a caller that passed 1 every round would hold the counter at 1
    and overwrite each prior audit JSON in place.
    """
    prefix = f"{plan_id}-{stage}"
    highest = 0
    if audit_dir.is_dir():
        for path in audit_dir.glob(f"{prefix}-*.json"):
            match = _ITER_SUFFIX_RE.search(path.stem[len(prefix):])
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def apply_audit_outcome(
    plan_path: str | Path,
    stage: str,
    audit_return_json: str,
    iteration: int | None = None,
) -> dict:
    """
    Apply all audit-loop housekeeping for one auditor return.

    Args:
        plan_path:        Absolute path to the PLAN .md file.
        stage:            "sufficiency" or "plan_safety".
        audit_return_json: The full JSON string from the auditor's <pipeline-result> block.
        iteration:        Optional cross-check only. The iteration is derived from
                          the audit JSONs on disk. A supplied value that disagrees
                          with the derived one is reported back as iteration_mismatch.

    Returns:
        dict with keys: outcome, review_text, audit_json_path, stripped_count,
                        recurring_fingerprints, last_audit_commit, plan_id.

    Raises:
        subprocess.CalledProcessError: if any git command fails.
        ValueError: if plan_path or audit_return_json is invalid.
        yaml.YAMLError: if frontmatter is unparseable.
    """
    plan_path = Path(plan_path).resolve()
    plan_id = extract_plan_id(plan_path)

    # -----------------------------------------------------------------------
    # 1. Parse auditor return JSON
    # -----------------------------------------------------------------------
    try:
        audit_data = json.loads(audit_return_json)
    except json.JSONDecodeError as e:
        raise ValueError(f"audit_return_json is not valid JSON: {e}") from e

    outcome = audit_data.get("outcome", "")
    review_text = audit_data.get("payload", {}).get("review_text", "")
    findings = audit_data.get("diagnostics", {}).get("findings", [])
    # An auditor that omits the findings array disables recurrence detection
    # without failing anything, which is how the loop ran blind to its own
    # repetition for its whole history. Report the omission rather than
    # absorbing it. Distinguish "absent" from "present and empty": empty is a
    # clean audit, absent is a broken contract.
    findings_absent = "findings" not in audit_data.get("diagnostics", {})

    # -----------------------------------------------------------------------
    # 2. Write audit JSON snapshot to Workbench/.audit/
    # -----------------------------------------------------------------------
    workbench_dir = plan_path.parent  # typically Workbench/
    audit_dir = workbench_dir / ".audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    derived_iteration = derive_next_iteration(audit_dir, plan_id, stage)
    if iteration is not None and iteration != derived_iteration:
        iteration_mismatch = {"supplied": iteration, "derived": derived_iteration}
    else:
        iteration_mismatch = None
    iteration = derived_iteration
    ceiling_reached = iteration >= MAX_ITERATIONS

    audit_json_path = audit_dir / f"{plan_id}-{stage}-{iteration}.json"
    audit_json_path.write_text(audit_return_json, encoding="utf-8")

    # -----------------------------------------------------------------------
    # 3. Acknowledgement-stripping
    # -----------------------------------------------------------------------
    fm, body = _load_frontmatter(plan_path)

    # audit_acknowledgements carries two entry shapes, both shipped and both
    # written by a different party. apply_audit_action appends a dict keyed by
    # fingerprint when a human acks a specific finding. A bare code string is the
    # form audit-haiku-safe section 4d.2 reads for advisory suppression (PSZ001),
    # and is what an operator or orchestrator writes by hand. Reading only the
    # first shape raised AttributeError on the second and took the whole audit
    # loop down mid-round.
    ack_entries = fm.get("audit_acknowledgements", []) or []
    acked_fps = set()
    acked_codes = set()
    for entry in ack_entries:
        if isinstance(entry, dict):
            fp = entry.get("fingerprint", "")
            if fp:
                acked_fps.add(fp)
        elif isinstance(entry, str) and entry.strip():
            acked_codes.add(entry.strip())

    # Compute fingerprints for current findings; strip acknowledged ones
    current_fps: list[str] = []
    stripped_count = 0
    filtered_findings: list[dict] = []
    for finding in findings:
        fp = _compute_fingerprint(finding)
        if fp in acked_fps or finding.get("code", "") in acked_codes:
            stripped_count += 1
        else:
            current_fps.append(fp)
            filtered_findings.append(finding)

    # -----------------------------------------------------------------------
    # 4. Recurrence detection
    # -----------------------------------------------------------------------
    recurring_fingerprints: list[str] = []
    if iteration > 1:
        prior_audit_path = audit_dir / f"{plan_id}-{stage}-{iteration - 1}.json"
        if prior_audit_path.exists():
            try:
                with prior_audit_path.open(encoding="utf-8") as f:
                    prior_data = json.load(f)
                prior_findings = prior_data.get("diagnostics", {}).get("findings", [])
                prior_fps = {_compute_fingerprint(f) for f in prior_findings}
                recurring_fingerprints = [fp for fp in current_fps if fp in prior_fps]
            except (json.JSONDecodeError, OSError):
                # Tolerate absence or corruption - return empty list
                recurring_fingerprints = []

    # -----------------------------------------------------------------------
    # 5. Mutate PLAN frontmatter (audit_state fields)
    # -----------------------------------------------------------------------
    audit_state = fm.setdefault("audit_state", {})
    audit_state["last_stage"] = stage
    audit_state["last_outcome"] = outcome

    # Increment the stage-specific iteration counter
    stage_key = f"{stage}_iterations"
    audit_state[stage_key] = iteration

    # Write frontmatter back (last_audit_commit not yet known)
    _write_frontmatter(plan_path, fm, body)

    # -----------------------------------------------------------------------
    # 6. First git commit: audit_state update
    # -----------------------------------------------------------------------
    repo_root = plan_path.parent.parent  # Workbench/ -> repo root
    subprocess.run(
        ["git", "add", str(plan_path), str(audit_json_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
    )
    subprocess.run(
        ["git", "commit", "-m", f"plan-pipeline: audit_state update - {stage}:{outcome}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
    )

    # -----------------------------------------------------------------------
    # 7. Capture HEAD SHA
    # -----------------------------------------------------------------------
    sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
    )
    last_audit_commit = sha_result.stdout.strip()[:8]

    # -----------------------------------------------------------------------
    # 8. Mutate last_audit_commit in frontmatter
    # -----------------------------------------------------------------------
    # Re-read frontmatter to avoid clobbering any concurrent writes
    fm, body = _load_frontmatter(plan_path)
    fm.setdefault("audit_state", {})["last_audit_commit"] = last_audit_commit
    _write_frontmatter(plan_path, fm, body)

    # -----------------------------------------------------------------------
    # 9. Second git commit: record last_audit_commit
    # -----------------------------------------------------------------------
    subprocess.run(
        ["git", "add", str(plan_path)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
    )
    subprocess.run(
        ["git", "commit", "-m", f"plan-pipeline: record last_audit_commit for {plan_id}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=str(repo_root),
    )

    # -----------------------------------------------------------------------
    # 10. Return result dict
    # -----------------------------------------------------------------------
    return {
        "outcome": outcome,
        "review_text": review_text,
        "audit_json_path": str(audit_json_path),
        "stripped_count": stripped_count,
        "recurring_fingerprints": recurring_fingerprints,
        "iteration": iteration,
        "findings_absent": findings_absent,
        "iteration_mismatch": iteration_mismatch,
        "ceiling_reached": ceiling_reached,
        "last_audit_commit": last_audit_commit,
        "plan_id": plan_id,
    }


# ---------------------------------------------------------------------------
# CLI entry point (per SUF-ORC-001)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    import argparse

    parser = argparse.ArgumentParser(
        description=(
            "Apply audit-loop housekeeping for one auditor return. "
            "Outputs a JSON result dict to stdout."
        )
    )
    parser.add_argument("plan_path", help="Absolute path to the PLAN .md file")
    parser.add_argument(
        "stage",
        choices=["sufficiency", "plan_safety"],
        help="Audit stage being processed",
    )
    parser.add_argument(
        "audit_json_path",
        help=(
            "Path to a file containing the auditor's <pipeline-result> JSON body. "
            "The orchestrator writes the JSON to a temp file under Workbench/.audit-tmp/ "
            "before invoking to avoid shell-quoting hazards on long JSON bodies."
        ),
    )
    parser.add_argument(
        "iteration",
        type=int,
        nargs="?",
        default=None,
        help="Optional. Cross-check only - the iteration is derived from the audit "
             "JSONs already on disk, and a supplied value that disagrees is reported "
             "as iteration_mismatch rather than used.",
    )
    args = parser.parse_args()

    with open(args.audit_json_path, encoding="utf-8") as fh:
        audit_return_json = fh.read()

    result = apply_audit_outcome(
        args.plan_path,
        args.stage,
        audit_return_json,
        args.iteration,
    )
    print(json.dumps(result))
    sys.exit(0)
