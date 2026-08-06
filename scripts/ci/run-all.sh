#!/usr/bin/env bash
# ascii-exempt (D18): this file's prose comments carry em dashes, and
# check-shipped-ascii.py would otherwise flag every one of them.
#
# scripts/ci/run-all.sh — single entry point for plan_foundry CI.
#
# Runs every check we want green on every PR. Designed to run identically
# in two contexts:
#   - locally (developers can run it before pushing)
#   - in GitHub Actions (.github/workflows/checks.yml just shells out to this)
#
# Each check runs even if a previous one failed; final exit reflects the
# total failure count. This is more informative than short-circuiting.
#
# USAGE:
#   bash scripts/ci/run-all.sh                # run all checks
#   bash scripts/ci/run-all.sh --list         # list check names without running
#
# WHAT IT CHECKS: run `bash scripts/ci/run-all.sh --list` - the list is
# derived from this script's own run_check invocations (PLAN-AI3
# D20 Derive-Never-Restate), so it can never drift from what actually runs.
#
# WHAT IT DOES NOT CHECK:
#   - LLM-driven scenarios (the test-foundry harness runs those out-of-CI;
#     they require a Claude Code session)
#   - Real prod-repo push (requires credentials + a real prod repo)

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
# $0 resolves against the caller's cwd. Capture it as an absolute path BEFORE
# the cd below - a stale relative $0 would break the --list derivation once
# the script has changed directory (PLAN-AI3 Step 3).
SELF_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$REPO_ROOT"

# When this script runs inside GitHub Actions we get nicer log grouping if we
# emit ::group:: directives. Detect by environment variable.
in_actions=0
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
    in_actions=1
fi

group_start() {
    if [ "$in_actions" = "1" ]; then
        echo "::group::$1"
    else
        echo "── $1 ──"
    fi
}

group_end() {
    if [ "$in_actions" = "1" ]; then
        echo "::endgroup::"
    fi
}

failed=0
checks_run=0

# D4 (CI-Loud-Fail per PLAN-AC4). A check fails if EITHER the command exits
# non-zero OR its stderr emits a line starting with "ERROR" or "Error:". The
# second condition is defence-in-depth against silent-pass bugs like the one
# surfaced by PLAN-AC3 cleanup: audit-foundry.py raised SystemExit("ERROR: ...")
# at module load (exit code 1), but a prior bug path was an "error printed to
# stderr but script exited 0" pattern. We don't want the runner to be the
# weakest link — if any check emits an ERROR line, the build is red regardless
# of exit code.
# Is this the plan_foundry source repo, or a consumer install? A consumer receives
# an allowlisted subset of this tree (see scripts/promote.sh ALLOWLIST): the skills,
# agents, commands and hooks, plus a handful of scripts and this runner. Most of
# scripts/ci/ is NOT packaged.
is_foundry_source=0
if [ -f scripts/promote.sh ] && [ -f scripts/prod-repo.txt ]; then
    is_foundry_source=1
fi

run_check() {
    local label="$1"; shift

    # A check whose script was never packaged skips rather than fails. A consumer
    # running the documented entry point should never see a red line describing
    # their own repo as broken for a file they were never given. In the foundry
    # source repo the same absence is a real defect, so it still fails there and
    # this guard never fires.
    if [ "$is_foundry_source" = "0" ]; then
        local arg missing=""
        for arg in "$@"; do
            case "$arg" in
                *.py|*.sh)
                    if [ ! -e "$arg" ]; then missing="$arg"; break; fi
                    ;;
            esac
        done
        if [ -n "$missing" ]; then
            group_start "$label"
            group_end
            echo "SKIP: $label (not packaged in this install: $missing)"
            return 0
        fi
    fi

    checks_run=$((checks_run + 1))
    group_start "$label"

    local stderr_file rc stderr_has_error
    stderr_file="$(mktemp)"
    "$@" 2> "$stderr_file"
    rc=$?
    # Surface captured stderr to the human (so FAIL diagnostics remain visible).
    if [ -s "$stderr_file" ]; then
        cat "$stderr_file" >&2
    fi
    stderr_has_error=0
    if [ -s "$stderr_file" ] && grep -qE '^(ERROR|Error:)' "$stderr_file"; then
        stderr_has_error=1
    fi
    rm -f "$stderr_file"

    if [ "$rc" -ne 0 ]; then
        group_end
        echo "FAIL: $label (exit $rc)" >&2
        failed=$((failed + 1))
    elif [ "$stderr_has_error" = "1" ]; then
        group_end
        echo "FAIL: $label (exit 0 but stderr emitted ERROR/Error: line — D4 loud-fail)" >&2
        failed=$((failed + 1))
    else
        group_end
        echo "PASS: $label"
    fi
}

# There is no run_guard. PLAN-AI3 specified a run_guard wrapper and a
# negative-test harness that broke each guard to prove it fails; both were
# cut on 2026-07-29 (commit 4596b1b) after the harness took CI from 25
# seconds to 12 minutes. Every check is registered with run_check. The
# scope cut and its measurements are recorded in the retired PLAN-AI3.
pre_commit_hook_syntax() {
    # .claude/hooks/pre-commit ships to every consumer as of PLAN-AK7 D4 -
    # promote.sh's DENYLIST is empty. Its CLAUDE.md-cap block is gated
    # internally by an is_foundry_source check instead of being withheld at
    # the file level, and the FOUNDRYREQ/PTREQ deletion guard it also carries
    # needs to reach every consumer.
    if [ ! -f .claude/hooks/pre-commit ]; then
        echo ".claude/hooks/pre-commit not present - skipping syntax check"
        return 0
    fi
    bash -n .claude/hooks/pre-commit
}

promote_sh_syntax() {
    if [ -f scripts/promote.sh ]; then
        bash -n scripts/promote.sh
    else
        echo "scripts/promote.sh not present — skipping syntax check"
        return 0
    fi
}

claude_md_line_cap_check() {
    local cap=175
    if [ ! -f CLAUDE.md ]; then
        echo "CLAUDE.md not present — skipping line-cap check"
        return 0
    fi
    local lines
    lines=$(wc -l < CLAUDE.md)
    if [ "$lines" -gt "$cap" ]; then
        echo "CLAUDE.md is $lines lines — exceeds hard cap of $cap." >&2
        echo "Trim before merging. See maintain-project-docs skill for prune guidance." >&2
        return 1
    fi
    echo "CLAUDE.md: $lines lines (cap $cap; headroom $((cap - lines)))"
    return 0
}

if [ "${1:-}" = "--list" ]; then
    echo "Checks:"
    # Derived from this script's own run_check invocations (PLAN-AI3
    # D20 Derive-Never-Restate) - never a hand-maintained second copy of the
    # list run-all.sh actually runs. The run_guard alternative is kept in the
    # pattern so a stray registration would still be enumerated rather than
    # silently omitted. Verified: the `run_check() {` definition line does
    # not match (no closing quote after the identifier).
    grep -oE '^run_(check|guard) "[^"]+"' "$SELF_PATH" | sed -E 's/^run_(check|guard) "(.*)"$/  - \2/'
    exit 0
fi

# Sourceable. When another script sources this file it gets the helper
# definitions (run_check and the inline guard functions) without running the
# suite. scripts/ci/test_loud_fail.py relies on this to exercise the real
# run_check rather than a copy of it.
if [ "${BASH_SOURCE[0]}" != "${0}" ]; then
    return 0
fi

echo "scripts/ci/run-all.sh — running plan_foundry checks"
echo "repo_root=$REPO_ROOT in_actions=$in_actions"
echo ""

# --- Skill Python tests ---
run_check "plan-pipeline: prompts_and_parsing" \
    python3 .claude/skills/plan-pipeline/lib/test_prompts_and_parsing.py

run_check "plan-pipeline: build_brief" \
    python3 .claude/skills/plan-pipeline/lib/test_build_brief.py

run_check "write-plan: next_id" \
    python3 -m pytest .claude/skills/write-plan/scripts/test_next_id.py -q

run_check "_shared: push_policy" \
    python3 -m pytest .claude/skills/_shared/lib/test_push_policy.py -q

run_check "_shared: push_guard" \
    python3 -m pytest .claude/skills/_shared/lib/test_push_guard.py -q

run_check "_shared: orchestrator_lock" \
    python3 -m pytest .claude/skills/_shared/lib/test_orchestrator_lock.py -q

run_check "_shared: orchestrator_state_guard" \
    python3 -m pytest .claude/skills/_shared/lib/test_orchestrator_state_guard.py -q

run_check "_shared: resume_preflight" \
    python3 -m pytest .claude/skills/_shared/lib/test_resume_preflight.py -q

run_check "_shared: auditor_schema_code_pattern" \
    python3 -m pytest .claude/skills/_shared/lib/test_auditor_schema_code_pattern.py -q

run_check "_shared: hooks_path" \
    python3 .claude/skills/_shared/lib/test_hooks_path.py

run_check "_shared: gitattributes_pin" \
    python3 .claude/skills/_shared/lib/test_gitattributes_pin.py

# Catch-all sweep. Added 2026-07-27.
#
# Every run_check above names one test file by hand, while this script's own
# header has always claimed to run "Skill Python tests (test_*.py) under
# .claude/skills/*/lib/". Those two were not the same set, and the gap was
# invisible: a shared-asset test had been failing since two new assets landed
# earlier the same day, and CI reported green throughout because nothing
# enumerated it. That test has since been removed with the asset registry
# (PLAN-AJ4); the sweep it motivated stays.
#
# This sweep runs everything under .claude/skills/*/lib and */scripts, so a new
# test file is covered the moment it lands rather than when someone remembers
# to add a line here. The named checks above are kept: they give per-suite
# failure labels in CI output, which a single aggregate run does not.
run_check "skills: all python tests (catch-all)" \
    python3 -m pytest .claude/skills/*/lib .claude/skills/*/scripts -q

# D18 - ASCII At The Ship Boundary. The sweep that cleaned the shipped surface
# landed without this guard, so the rule was asserted and unchecked on the day
# it was written. Scope is derived from promote.sh rather than restated.
run_check "shipped surface ASCII (D18)" \
    python3 scripts/ci/check-shipped-ascii.py

run_check "_shared: validate_artefact_filename" \
    python3 -m pytest .claude/skills/_shared/lib/test_validate_artefact_filename.py -q

run_check "plan-pipeline: model_budget" \
    python3 .claude/skills/plan-pipeline/lib/test_model_budget.py

run_check "plan-pipeline: gate_halt_routing" \
    python3 -m pytest .claude/skills/plan-pipeline/lib/test_gate_halt_routing.py -q

run_check "handoff-next-session: readiness_gate_wiring" \
    python3 .claude/skills/handoff-next-session/lib/test_readiness_gate_wiring.py

run_check "audit-haiku-safe: sizing_wiring" \
    python3 .claude/skills/audit-haiku-safe/lib/test_sizing_wiring.py

run_check "ideate: ideate" \
    python3 .claude/skills/ideate/lib/test_ideate.py

run_check "utf8 stdout guard" \
    python3 scripts/test_utf8_stdout_guard.py

# scripts/test_generate_deprecation_shim.py sits under repo-root scripts/,
# which the .claude/skills/*/lib and */scripts catch-all sweep above does
# not cover (that glob is skills-scoped only). Root-level scripts/ test
# files are registered one by one here, not swept - this is that
# registration for PLAN-AH9's shim generator (Step 3a).
run_check "generate-deprecation-shim" \
    python3 -m pytest scripts/test_generate_deprecation_shim.py -q

# scripts/test_check_promote_version.py sits under repo-root scripts/, which
# the .claude/skills/*/lib and */scripts catch-all sweep above does not cover
# (that glob is skills-scoped only). Registered by hand per the same
# precedent as test_generate_deprecation_shim.py above. This pytest suite
# wraps scripts/check_promote_version.py, which is a repo-safety guard over
# promote.sh's version gates.
run_check "check_promote_version: sequence + right-size + criteria gates" \
    python3 -m pytest scripts/test_check_promote_version.py -q

# Registered by hand for the same reason as the line above. This suite wraps
# scripts/check_promote_clean.py, promote.sh's clean-tree guard: the bundle is
# built by copying files rather than by exporting a commit, so a dirty shipped
# file ships in a state no commit records. v1.16.0 shipped six such files.
run_check "check_promote_clean: shipped surface matches HEAD before promote" \
    python3 -m pytest scripts/test_check_promote_clean.py -q

# scripts/test_recover_deleted_retirees.py and scripts/ci/test_loud_fail.py
# both sit under scripts/ paths the catch-all sweeps above do not cover, and
# both were dead - never run by any CI invocation - until PLAN-AI3 (2026-07-29)
# surfaced it via check-check-registration.py. Registered by hand per the same
# root-level scripts/ precedent as test_generate_deprecation_shim.py above.
run_check "recover-deleted-retirees" \
    python3 -m pytest scripts/test_recover_deleted_retirees.py -q

run_check "test_loud_fail.py" \
    python3 scripts/ci/test_loud_fail.py

# scripts/ci/check-no-marginalia.py was ALSO dead - discovered 2026-07-29 by
# running Step 1's own coverage logic against the tree, not named in PLAN-AI3's
# original evidence bullets. Registered the same way as the two dead tests
# above.
run_check "no marginalia in reference documents" \
    python3 scripts/ci/check-no-marginalia.py

run_check "check-no-marginalia: fenced blocks are not commentary" \
    python3 scripts/ci/test_check_no_marginalia.py

run_check "register copies: working-with-the-human" \
    python3 scripts/ci/check-register-copies.py

# --- Shell syntax ---
run_check "pre-commit hook script syntax" pre_commit_hook_syntax
run_check "promote.sh syntax" promote_sh_syntax

# --- Dogfood telemetry hook ---

# --- Hook line endings (FOUNDRYREQ 20260727-1350) ---
# A CRLF shebang breaks a git hook silently on every Windows consumer, and the
# commit-msg hook exits 0 on all failure paths by design, so broken and working
# are outwardly identical. Byte-level assertion is the only thing that catches it.
run_check "hook line endings (LF + eol=lf pinned)"     python3 scripts/ci/check-hook-line-endings.py

# --- Foundry audit ---
run_check "audit-foundry clean" \
    python3 scripts/audit-foundry.py --no-json-output

# --- Foundry invariants (executable ARCHITECTURE.md register) ---
# --- Live references (every pointer in the bundle resolves) ---
# Added 2026-07-29. Deleting the monthly LOG and then the event telemetry
# each left dangling pointers that a person tripped over rather than a check:
# a registered hook whose script was gone, a script importing a deleted
# module, and a canonical audit list naming a skill renamed months earlier.
# This asks the standing question - does every pointer still resolve - rather
# than checking for the names of whatever happened to be deleted.
run_check "live references" \
    python3 scripts/ci/check-live-references.py

run_check "foundry invariants" \
    python3 scripts/ci/check-invariants.py

# --- Harness contract (the bundle has not drifted from its own assumptions) ---
# This bundle consumes harness capabilities rather than rebuilding them, and
# harness surfaces move. The register records what is assumed of each surface
# and how sure we are; this asserts every entry is complete and that no file
# has copied a guarded value out of it.
run_check "harness contract" \
    python3 scripts/ci/check-harness-contract.py

# --- Skill listing size (re-derives the figure, never records it) ---
run_check "skill listing size (caps)" \
    python3 scripts/ci/skill-listing-size.py --check-caps

# --- Mobile/web skill-loading claim (settled 2026-07-29, do NOT load) ---
# The bundle held two contradictory claims about whether mobile/web sessions
# read project-local .claude/{skills,agents,commands}/. Guards against the
# superseded "DO read/load" claim returning after correction.
run_check "mobile/web skill-loading claim" \
    python3 scripts/ci/check-mobile-web-claim.py

# --- assigned_to: human must not reach an executor ---
#
# The dispatch path resolves assigned_to through two prose surfaces. Neither
# carried a `human` branch until 2026-08-05, so such a PLAN was dispatched to
# an executor structurally unable to run its steps. This guards the branch.
run_check "assigned_to: human is not dispatched" \
    python3 scripts/ci/check-human-not-dispatched.py

# --- Skill standard and audit surface: acceptance fixtures (PLAN-AJ8) ---
#
# Three checks over committed evidence. None of them invokes an auditor and none
# needs a model: what they assert is that this repo produced the evidence its
# acceptance items claim, and that the evidence still describes the tree.
#
# Registration is explicit rather than swept. The catch-all above runs pytest over
# .claude/skills/*/lib and */scripts, and pytest collects only test_*.py, so a
# check_*.py sitting in those directories is run by nothing while CI still reports
# green. Renaming them to test_*.py to be swept would lose the per-check failure
# label and the argument string, which is the half that matters here: each
# invocation below is character-for-character the one PLAN-AJ8's corresponding
# acceptance item uses, so the two cannot drift into asserting different things
# under one name.
# Registered WITHOUT --require-measured, deliberately. The suite has one exit code,
# so a check that is red by design converts into a gate on every acceptance item that
# runs the whole suite - which is five PLANs' worth of unrelated work, and every
# consumer's CI on install. Without the flag this still fails on a fixture that is
# actually wrong and prints a NOTICE naming what is unmeasured. Pass the flag from a
# per-skill acceptance item when a measurement is genuinely required there.
run_check "write-skill: measured eval fixture" \
    python3 .claude/skills/write-skill/scripts/check_eval_fixture.py

run_check "audit-skills: ownership branch (bundle-managed)" \
    python3 .claude/skills/audit-skills/scripts/check_ownership_branch.py --case bundle-managed

run_check "audit-skills: ownership branch (consumer-owned)" \
    python3 .claude/skills/audit-skills/scripts/check_ownership_branch.py --case consumer-owned

run_check "audit-skills: ownership branch (undeterminable)" \
    python3 .claude/skills/audit-skills/scripts/check_ownership_branch.py --case undeterminable

run_check "audit-skills: corpus baseline covers the live corpus" \
    python3 .claude/skills/audit-skills/scripts/check_report_coverage.py

# --- CLAUDE.md line-cap (T04) ---
run_check "CLAUDE.md hard line-cap (175)" claude_md_line_cap_check

# --- Registration coverage (PLAN-AI3) ---
# check-check-registration.py guards the repo's registration completeness:
# every check-shaped file on disk is either named here or swept by the
# catch-all above. Its guard-fixture meta-check was removed with the
# negative-test harness on 2026-07-29.
run_check "check-check-registration.py" python3 scripts/ci/check-check-registration.py

# --- Writing lint (FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1702) ---
# Scans every markdown file this repo's writing-style.md governs (root docs,
# the skills corpus, Workbench prose - see check-writing-lint.py's own
# docstring for the register-derived scope and the Retired/ carve-out), held
# against a committed baseline the same way audit-foundry holds a large
# corpus at bay with a severity gate. A finding already in the baseline is
# backlog; a new one fails the run. Regenerate the baseline with
# `python3 scripts/ci/check-writing-lint.py --write-baseline`.
run_check "_shared: writing_lint (baseline-gated)" \
    python3 scripts/ci/check-writing-lint.py

run_check "check-writing-lint: baseline gate holds pre-existing findings" \
    python3 scripts/ci/test_check_writing_lint.py

echo ""
if [ $failed -eq 0 ]; then
    echo "ci: ALL ${checks_run} CHECKS PASSED"
    exit 0
else
    echo "ci: ${failed}/${checks_run} CHECKS FAILED" >&2
    exit 1
fi
