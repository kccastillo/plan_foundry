"""
resume_preflight.py - Resumption drift preflight for plan_foundry orchestrators.

Originating PLAN: PLAN-AG4 (Deterministic branch/PR drift preflight on resumption,
2026-07-13).

Public function: check_resume_drift(repo_root, remote="origin", default_branch=None,
    branch=None, expected_plan_states=None, plan_glob="Workbench/PLAN-*.md",
    now=None) -> dict

Design (D1-D6 - PLAN-AG4):
  D1 - Read-only + fast: the preflight only fetches and reads (no commit, no push, no
    branch mutation). `git fetch` + a few `git rev-list`/`merge-base`/`symbolic-ref`
    queries + PLAN-frontmatter reads.
  D2 - Surfaced drift set: working-vs-remote (ahead/behind/diverged);
    working-vs-default (ahead/behind + prior-PR-merged -> restart-from-default);
    open PR state; on-disk PLAN pipeline_phase/status/last_executor_outcome compared
    against the persisted ## Plan-state baseline recorded by handoff-next-session.
  D3 - Halt-on-drift, silent-on-clean: any drift halts and emits a re-orientation
    summary requiring reconciliation; clean state proceeds silently.
  D4 - Pure helper mirroring push_guard.py: subprocess git queries + frontmatter reads
    -> a flat drift-report dict, unit-tested with mocked subprocess output (and tmp_path
    PLAN fixtures), plus one real-git-repo test.
  D5 - Composition: composes with the merged-PR restart rule and with the AG1
    durability-before-PR rule (start-of-session counterpart to that end-of-session rule).
  D6 - Persisted baseline (write side): handoff-next-session writes a machine-readable
    ## Plan-state baseline block into every handoff; rehydrate-handoff Step 0 reads it
    back as expected_plan_states. This closes the loop that makes PLAN-phase drift a
    genuine, firing axis rather than an informational snapshot.

Fail-open rationale (D1 - PLAN-AG4):
  If any git subprocess fails (offline, auth failure, missing remote, timeout), the
  affected axis returns checked=False with a notes entry containing "skipped". A
  checked=False axis NEVER contributes to drift. PLAN-snapshot reads are filesystem-only
  and always run. This mirrors push_guard.py's fail-open posture.

Desktop-only limitation:
  Claude Code mobile/web sessions do NOT load project-local .claude/{skills,hooks}.
  This helper only runs in desktop sessions where the skills are loaded. This is why
  the attachment surface is the resume skill/workflow (rehydrate-handoff Step 0) rather
  than a hook.

PR-state availability:
  Authoritative PR state via `gh pr list`. The `gh` CLI is part of this repo's CI
  baseline but may be absent in true-headless, non-CI sessions. When `gh` is unavailable
  or errors, pr_state.available=False and the git-only axes decide drift.

Merged-PR detection heuristic (degraded path - disclosed residual error modes):
  When gh/MCP is unavailable the helper uses a strictly-behind ancestry test:
  merged_into_default=True ONLY when ALL hold:
    (1) branch != default_branch
    (2) git rev-list <remote>/<default>..HEAD is EMPTY (HEAD is ancestor of default tip)
    (3) git rev-list HEAD..<remote>/<default> is NON-EMPTY (default is strictly ahead)
    (4) HEAD != <remote>/<default> tip (not identical - excludes fast-forward/at-tip)
  Residual error modes (disclosed in J2 sign-off, NOT guarded in code):
    - Behind-empty false positive: a stale branch with no unique commits merely behind
      default shares the identical strictly-behind topology of a genuine merge and reads
      as merged though it never was. The earlier ">= 1 unique commit" guard was
      self-contradictory (an ancestor HEAD has zero unique commits) and was removed
      (blocker S603).
    - Squash-merge false negative: the squash commit is not an ancestor of the branch
      tip, so the merge goes undetected.
    - Fast-forward-merge false negative: feature tip equals the default tip and is
      excluded by the HEAD != default tip condition.

Return dict keys (stable):
  drift           : bool
  clean           : bool (not drift)
  branch          : str
  default_branch  : str
  remote_compare  : dict (checked, ahead, behind, diverged, reason)
  default_compare : dict (checked, ahead, behind, merged_into_default, reason)
  pr_state        : dict (available, prs, reason)
  plan_states     : dict (relpath -> {pipeline_phase, status, last_executor_outcome})
  plan_drift      : list of {plan, field, expected, actual}
  summary         : str (empty when clean)
  notes           : list[str]
"""

import pathlib
import subprocess


def check_resume_drift(
    repo_root,
    remote="origin",
    default_branch=None,
    branch=None,
    expected_plan_states=None,
    plan_glob="Workbench/PLAN-*.md",
    now=None,
):
    """Check for drift between on-disk state and expected state on session resume.

    Axes computed (in order):
      1. git fetch <remote>
      2. Resolve current branch (git rev-parse --abbrev-ref HEAD)
      3. Resolve default branch (git symbolic-ref refs/remotes/<remote>/HEAD)
      4. remote_compare: working branch vs its remote tracking ref
      5. pr_state: open/merged PRs via `gh pr list` (best-effort; fail-open)
      6. default_compare: working branch vs default branch (+ merged detection)
      7. plan_states: on-disk PLAN frontmatter snapshot
      8. plan_drift: mismatch vs expected_plan_states baseline (when supplied)

    Fail-open: any git subprocess failure marks that axis checked=False and adds a
    notes entry containing "skipped". A checked=False axis never contributes drift.

    Parameters
    ----------
    repo_root : str or Path
        Absolute path to the repository root. Passed as cwd to subprocess calls.
    remote : str
        The git remote to check against. Default: "origin".
    default_branch : str or None
        The default/main branch name. If None, resolved dynamically via symbolic-ref,
        falling back to "main" with a notes entry on failure.
    branch : str or None
        The current branch name. If None, resolved via git rev-parse --abbrev-ref HEAD.
    expected_plan_states : dict or None
        Mapping of relpath -> {field: expected_value} from the handoff's
        ## Plan-state baseline block. When supplied, plan_drift fires on mismatches.
        When absent/empty, plan_drift is [] (snapshot is informational only).
    plan_glob : str
        Glob pattern for PLAN files, relative to repo_root. Default: "Workbench/PLAN-*.md".
    now : unused (reserved for future time-sensitive checks)

    Returns
    -------
    dict with keys: drift, clean, branch, default_branch, remote_compare,
    default_compare, pr_state, plan_states, plan_drift, summary, notes.
    """
    repo_root = str(repo_root)
    notes = []

    # Initialise fail-open axis values
    _unchecked_compare = {"checked": False, "ahead": 0, "behind": 0, "reason": "skipped"}
    _unchecked_remote = {
        "checked": False, "ahead": 0, "behind": 0, "diverged": False,
        "reason": "skipped",
    }
    _unchecked_default = {
        "checked": False, "ahead": 0, "behind": 0, "merged_into_default": False,
        "reason": "skipped",
    }
    _unchecked_pr = {"available": False, "prs": [], "reason": "pr-state: skipped"}

    resolved_branch = branch or "HEAD"
    resolved_default = default_branch or "main"

    # ------------------------------------------------------------------
    # Step 1: git fetch <remote>
    # ------------------------------------------------------------------
    fetch_ok = False
    try:
        fetch_result = subprocess.run(
            ["git", "fetch", remote],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if fetch_result.returncode != 0:
            note = (
                f"fetch: skipped - git fetch {remote!r} exited "
                f"{fetch_result.returncode}: {fetch_result.stderr.strip()[:200]}"
            )
            notes.append(note)
        else:
            fetch_ok = True
    except subprocess.TimeoutExpired:
        notes.append(f"fetch: skipped - git fetch timed out after 30s")
    except (FileNotFoundError, OSError) as exc:
        notes.append(f"fetch: skipped - git not available: {exc}")

    if not fetch_ok:
        # All git-derived axes are unchecked; still run PLAN snapshot
        plan_states, plan_drift = _compute_plan_states(
            repo_root, plan_glob, expected_plan_states
        )
        drift = bool(plan_drift)
        summary_lines = []
        if plan_drift:
            for pd in plan_drift:
                summary_lines.append(
                    f"PLAN {pd['plan']} {pd['field']} disk={pd['actual']} baseline={pd['expected']}"
                )
        return {
            "drift": drift,
            "clean": not drift,
            "branch": resolved_branch,
            "default_branch": resolved_default,
            "remote_compare": dict(_unchecked_remote),
            "default_compare": dict(_unchecked_default),
            "pr_state": dict(_unchecked_pr),
            "plan_states": plan_states,
            "plan_drift": plan_drift,
            "summary": "\n".join(summary_lines),
            "notes": notes,
        }

    # ------------------------------------------------------------------
    # Step 2: Resolve branch
    # ------------------------------------------------------------------
    if branch is None:
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=repo_root,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if branch_result.returncode != 0:
                notes.append(
                    "branch-resolve: skipped - could not resolve current branch: "
                    + branch_result.stderr.strip()[:200]
                )
                # fall through with resolved_branch = "HEAD"
            else:
                resolved_branch = branch_result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            notes.append(f"branch-resolve: skipped - {exc}")

    # ------------------------------------------------------------------
    # Step 3: Resolve default branch dynamically
    # ------------------------------------------------------------------
    if default_branch is None:
        symref_name = f"refs/remotes/{remote}/HEAD"
        try:
            symref_result = subprocess.run(
                ["git", "symbolic-ref", symref_name],
                cwd=repo_root,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if symref_result.returncode == 0:
                # Strip the "refs/remotes/<remote>/" prefix
                prefix = f"refs/remotes/{remote}/"
                raw = symref_result.stdout.strip()
                if raw.startswith(prefix):
                    resolved_default = raw[len(prefix):]
                else:
                    resolved_default = raw
            else:
                notes.append(
                    "default-branch: fell back to 'main' - symbolic-ref unavailable"
                )
                resolved_default = "main"
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            notes.append(
                f"default-branch: fell back to 'main' - symbolic-ref unavailable: {exc}"
            )
            resolved_default = "main"

    # ------------------------------------------------------------------
    # Step 4: remote_compare - working branch vs its remote tracking ref
    # ------------------------------------------------------------------
    remote_compare = dict(_unchecked_remote)
    tracking_ref = f"{remote}/{resolved_branch}"
    try:
        rc_result = subprocess.run(
            ["git", "rev-list", "--left-right", "--count", f"{tracking_ref}...HEAD"],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if rc_result.returncode != 0:
            note = (
                f"remote-compare: skipped - tracking ref {tracking_ref!r} not found: "
                f"{rc_result.stderr.strip()[:200]}"
            )
            notes.append(note)
            remote_compare["reason"] = note
        else:
            parts = rc_result.stdout.strip().split()
            if len(parts) == 2:
                try:
                    rc_behind = int(parts[0])
                    rc_ahead = int(parts[1])
                    remote_compare = {
                        "checked": True,
                        "ahead": rc_ahead,
                        "behind": rc_behind,
                        "diverged": rc_behind > 0 and rc_ahead > 0,
                        "reason": (
                            f"branch is {rc_ahead} commit(s) ahead, {rc_behind} commit(s) "
                            f"behind {tracking_ref}"
                        ),
                    }
                except ValueError:
                    note = f"remote-compare: skipped - unexpected rev-list output {rc_result.stdout.strip()!r}"
                    notes.append(note)
                    remote_compare["reason"] = note
            else:
                note = f"remote-compare: skipped - unexpected rev-list output {rc_result.stdout.strip()!r}"
                notes.append(note)
                remote_compare["reason"] = note
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        note = f"remote-compare: skipped - rev-list failed: {exc}"
        notes.append(note)
        remote_compare["reason"] = note

    # ------------------------------------------------------------------
    # Step 5: pr_state - best-effort via `gh pr list`, computed BEFORE default_compare
    # ------------------------------------------------------------------
    pr_state = dict(_unchecked_pr)
    try:
        gh_result = subprocess.run(
            [
                "gh", "pr", "list",
                "--head", resolved_branch,
                "--state", "all",
                "--json", "number,state,isDraft,title",
            ],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if gh_result.returncode == 0:
            import json as _json
            try:
                prs = _json.loads(gh_result.stdout.strip())
                pr_state = {
                    "available": True,
                    "prs": prs,
                    "reason": f"gh pr list returned {len(prs)} PR(s)",
                }
            except Exception as parse_exc:
                note = f"pr-state: skipped - could not parse gh output: {parse_exc}"
                notes.append(note)
                pr_state = {"available": False, "prs": [], "reason": note}
        else:
            note = (
                f"pr-state: skipped - gh pr list exited {gh_result.returncode}: "
                f"{gh_result.stderr.strip()[:200]}"
            )
            notes.append(note)
            pr_state = {"available": False, "prs": [], "reason": note}
    except FileNotFoundError:
        note = "pr-state: skipped - gh CLI not found"
        notes.append(note)
        pr_state = {"available": False, "prs": [], "reason": note}
    except subprocess.TimeoutExpired:
        note = "pr-state: skipped - gh pr list timed out after 15s"
        notes.append(note)
        pr_state = {"available": False, "prs": [], "reason": note}
    except (OSError, Exception) as exc:
        note = f"pr-state: skipped - {exc}"
        notes.append(note)
        pr_state = {"available": False, "prs": [], "reason": note}

    # ------------------------------------------------------------------
    # Step 6: default_compare - working branch vs default branch + merged detection
    # ------------------------------------------------------------------
    default_compare = dict(_unchecked_default)
    default_tracking_ref = f"{remote}/{resolved_default}"
    merged_into_default = False
    merged_pr_number = None
    merged_via_heuristic = False

    try:
        dc_result = subprocess.run(
            [
                "git", "rev-list", "--left-right", "--count",
                f"{default_tracking_ref}...HEAD",
            ],
            cwd=repo_root,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        if dc_result.returncode != 0:
            note = (
                f"default-compare: skipped - tracking ref {default_tracking_ref!r} not found: "
                f"{dc_result.stderr.strip()[:200]}"
            )
            notes.append(note)
            default_compare["reason"] = note
        else:
            parts = dc_result.stdout.strip().split()
            if len(parts) == 2:
                try:
                    dc_behind = int(parts[0])
                    dc_ahead = int(parts[1])

                    # --- Merged detection (authoritative first, heuristic second) ---

                    # Authoritative: PR state MERGED
                    if pr_state.get("available") and pr_state.get("prs"):
                        for pr in pr_state["prs"]:
                            if pr.get("state") == "MERGED":
                                merged_into_default = True
                                merged_pr_number = pr.get("number")
                                break

                    # Degraded heuristic: strictly-behind ancestry test
                    # (only when authoritative path is unavailable or inconclusive)
                    if not merged_into_default and not pr_state.get("available"):
                        if resolved_branch != resolved_default:
                            # Check if HEAD is ancestor of remote/default tip.
                            # Equivalent to: git merge-base --is-ancestor HEAD <remote>/<default>
                            # returns 0. We implement it via rev-list: <default>..HEAD empty
                            # <=> HEAD is an ancestor of <default>.
                            ancestor_check = subprocess.run(
                                [
                                    "git", "rev-list",
                                    f"{default_tracking_ref}..HEAD",
                                ],
                                cwd=repo_root,
                                capture_output=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=30,
                            )
                            # Check if default is strictly ahead (git rev-list HEAD..<default>
                            # non-empty)
                            ahead_check = subprocess.run(
                                [
                                    "git", "rev-list",
                                    f"HEAD..{default_tracking_ref}",
                                ],
                                cwd=repo_root,
                                capture_output=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=30,
                            )

                            # Get HEAD and default tip SHAs to check non-identical
                            head_sha_result = subprocess.run(
                                ["git", "rev-parse", "HEAD"],
                                cwd=repo_root,
                                capture_output=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=10,
                            )
                            default_sha_result = subprocess.run(
                                ["git", "rev-parse", default_tracking_ref],
                                cwd=repo_root,
                                capture_output=True,
                                encoding="utf-8",
                                errors="replace",
                                timeout=10,
                            )

                            if (
                                ancestor_check.returncode == 0
                                and ahead_check.returncode == 0
                                and head_sha_result.returncode == 0
                                and default_sha_result.returncode == 0
                            ):
                                ancestor_commits = ancestor_check.stdout.strip()
                                ahead_commits = ahead_check.stdout.strip()
                                head_sha = head_sha_result.stdout.strip()
                                default_sha = default_sha_result.stdout.strip()

                                if (
                                    ancestor_commits == ""          # HEAD is ancestor of default
                                    and ahead_commits != ""         # default is strictly ahead
                                    and head_sha != default_sha     # not identical to default tip
                                ):
                                    merged_into_default = True
                                    merged_via_heuristic = True
                                    notes.append(
                                        "merged-detection: git-ancestry-heuristic "
                                        "(strictly-behind) - cannot exclude a behind-empty "
                                        "branch; see J2"
                                    )

                    default_compare = {
                        "checked": True,
                        "ahead": dc_ahead,
                        "behind": dc_behind,
                        "merged_into_default": merged_into_default,
                        "reason": (
                            f"branch is {dc_ahead} commit(s) ahead, {dc_behind} commit(s) "
                            f"behind {default_tracking_ref}"
                        ),
                    }
                except ValueError:
                    note = (
                        f"default-compare: skipped - unexpected rev-list output "
                        f"{dc_result.stdout.strip()!r}"
                    )
                    notes.append(note)
                    default_compare["reason"] = note
            else:
                note = (
                    f"default-compare: skipped - unexpected rev-list output "
                    f"{dc_result.stdout.strip()!r}"
                )
                notes.append(note)
                default_compare["reason"] = note
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        note = f"default-compare: skipped - {exc}"
        notes.append(note)
        default_compare["reason"] = note

    # ------------------------------------------------------------------
    # Step 7 + 8: PLAN snapshot and baseline comparison
    # ------------------------------------------------------------------
    plan_states, plan_drift = _compute_plan_states(
        repo_root, plan_glob, expected_plan_states
    )

    # ------------------------------------------------------------------
    # Aggregate drift
    # ------------------------------------------------------------------
    rc = remote_compare
    dc = default_compare

    drift_signals = []

    if rc.get("checked") and (rc.get("behind", 0) > 0 or rc.get("diverged", False)):
        if rc.get("behind", 0) > 0 and not rc.get("diverged", False):
            drift_signals.append(
                f"branch is {rc['behind']} commit(s) behind {tracking_ref}"
            )
        elif rc.get("diverged", False):
            drift_signals.append(
                f"branch has diverged from {tracking_ref}: "
                f"{rc['ahead']} ahead, {rc['behind']} behind"
            )

    if dc.get("merged_into_default"):
        if merged_pr_number is not None:
            drift_signals.append(
                f"PR #{merged_pr_number} merged into {resolved_default} "
                f"-> restart from {resolved_default}"
            )
        elif merged_via_heuristic:
            drift_signals.append(
                f"working branch {resolved_branch} appears merged into "
                f"{remote}/{resolved_default} (strictly-behind git-ancestry heuristic - "
                f"no PR number; cannot exclude a behind-empty branch) "
                f"-> restart from {resolved_default}"
            )
        else:
            drift_signals.append(
                f"branch appears merged into {resolved_default} "
                f"-> restart from {resolved_default}"
            )

    for pd in plan_drift:
        drift_signals.append(
            f"PLAN {pd['plan']} {pd['field']} disk={pd['actual']} baseline={pd['expected']}"
        )

    drift = bool(drift_signals)
    summary = "\n".join(drift_signals)

    return {
        "drift": drift,
        "clean": not drift,
        "branch": resolved_branch,
        "default_branch": resolved_default,
        "remote_compare": remote_compare,
        "default_compare": default_compare,
        "pr_state": pr_state,
        "plan_states": plan_states,
        "plan_drift": plan_drift,
        "summary": summary,
        "notes": notes,
    }


def _compute_plan_states(repo_root, plan_glob, expected_plan_states):
    """Read on-disk PLAN frontmatter and compute drift vs expected baseline.

    Returns (plan_states dict, plan_drift list).
    """
    import glob as _glob

    repo_path = pathlib.Path(repo_root)
    plan_states = {}

    # Glob PLAN files
    pattern = str(repo_path / plan_glob)
    found_files = _glob.glob(pattern)

    for abs_path in found_files:
        rel = str(pathlib.Path(abs_path).relative_to(repo_path)).replace("\\", "/")
        fields = _read_plan_frontmatter(abs_path)
        plan_states[rel] = fields

    # Compute drift vs baseline.
    # Absent and empty mean the same thing for these fields: _read_plan_frontmatter
    # returns None when a key is absent or blank, while the handoff baseline writer
    # renders the same condition as "". Comparing them raw fires drift on every PLAN
    # that has never entered the pipeline.
    def _norm(val):
        return "" if val is None else str(val).strip()

    plan_drift = []
    if expected_plan_states:
        for relpath, expected_fields in expected_plan_states.items():
            actual_fields = plan_states.get(relpath)
            if actual_fields is None:
                # PLAN not found on disk (retired/moved since baseline)
                for field, expected_val in expected_fields.items():
                    plan_drift.append(
                        {
                            "plan": relpath,
                            "field": field,
                            "expected": expected_val,
                            "actual": None,
                        }
                    )
            else:
                for field, expected_val in expected_fields.items():
                    actual_val = actual_fields.get(field)
                    if _norm(actual_val) != _norm(expected_val):
                        plan_drift.append(
                            {
                                "plan": relpath,
                                "field": field,
                                "expected": expected_val,
                                "actual": actual_val,
                            }
                        )

    return plan_states, plan_drift


def _nested_scalar(lines, key_idx, member):
    """Return the scalar value of `member` in the block mapping starting after key_idx.

    Scans only the immediately following indented lines and stops at the first
    line that is not indented, so a sibling top-level key is never read. Matches
    the member name exactly, so `outcome_subtype` never satisfies a request for
    `outcome`. Returns "" when the member is absent.
    """
    for line in lines[key_idx + 1:]:
        if not line.strip():
            continue
        if not line[:1].isspace():
            break
        stripped = line.strip()
        if stripped.startswith(f"{member}:"):
            return stripped[len(member) + 1:].strip()
    return ""


def _read_plan_frontmatter(abs_path):
    """Read pipeline_phase, status, last_executor_outcome from a PLAN file's YAML frontmatter.

    Returns dict with those three keys (None/empty string if absent or unreadable).
    """
    fields = {
        "pipeline_phase": None,
        "status": None,
        "last_executor_outcome": None,
    }
    try:
        with open(abs_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        # Extract YAML frontmatter between --- delimiters
        if not content.startswith("---"):
            return fields
        end = content.find("\n---", 3)
        if end == -1:
            return fields
        frontmatter = content[3:end]
        lines = frontmatter.splitlines()
        for idx, line in enumerate(lines):
            for key in ("pipeline_phase", "status", "last_executor_outcome"):
                if line.startswith(f"{key}:"):
                    val = line[len(f"{key}:"):].strip()
                    if not val:
                        # The executor writes last_executor_outcome as a block mapping,
                        # so the key line carries no inline value. Its nested `outcome:`
                        # member is the scalar the handoff baseline records, so collapse
                        # to that rather than reading the whole field as absent.
                        val = _nested_scalar(lines, idx, "outcome")
                    # Strip inline YAML string quotes if present
                    if (val.startswith('"') and val.endswith('"')) or (
                        val.startswith("'") and val.endswith("'")
                    ):
                        val = val[1:-1]
                    fields[key] = val if val else None
    except Exception:
        pass
    return fields
