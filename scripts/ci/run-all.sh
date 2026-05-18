#!/usr/bin/env bash
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
# WHAT IT CHECKS (post-PLAN-AC3: plugin marketplace abandoned):
#   - Skill Python tests (test_*.py) under .claude/skills/*/lib/
#   - INDEX freshness (build_index produces no diff)
#   - pre-commit hook script syntax
#   - promote.sh syntax
#   - Dogfood telemetry hook registered in .claude/settings.json
#   - audit-foundry.py exits clean (no error-severity findings)
#   - CLAUDE.md hard line-cap (T04: 150 lines)
#
# WHAT IT DOES NOT CHECK:
#   - LLM-driven scenarios (the test-foundry harness runs those out-of-CI;
#     they require a Claude Code session)
#   - Real prod-repo push (requires credentials + a real prod repo)

set -uo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
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

run_check() {
    local label="$1"; shift
    checks_run=$((checks_run + 1))
    group_start "$label"
    if "$@"; then
        group_end
        echo "PASS: $label"
    else
        local rc=$?
        group_end
        echo "FAIL: $label (exit $rc)" >&2
        failed=$((failed + 1))
    fi
}

# Synthetic check: INDEX freshness with volatile-field masking.
index_freshness_check() {
    python3 .claude/skills/update-workbench-index/scripts/build_index.py Workbench > /dev/null || return 1

    local tmpdir
    tmpdir="$(mktemp -d)"
    git show HEAD:Workbench/.index.json > "$tmpdir/committed.json" 2>/dev/null || echo '{}' > "$tmpdir/committed.json"
    cp Workbench/.index.json "$tmpdir/fresh.json"
    git show HEAD:Workbench/INDEX.md > "$tmpdir/committed.md" 2>/dev/null || echo '' > "$tmpdir/committed.md"
    cp Workbench/INDEX.md "$tmpdir/fresh.md"

    local result
    result=$(python3 - "$tmpdir" <<'PYEOF'
import json, re, sys, pathlib
tmpdir = pathlib.Path(sys.argv[1])

def strip_json(d):
    for key in ("generated_at", "recent_transitions", "recently_retired"):
        d.pop(key, None)
    alerts = d.get("alerts", {})
    for vkey in ("orphan_heartbeat", "executor_hung", "stuck_audits", "long_blocked", "verification_pending_too_long", "stuck_ideation"):
        if vkey in alerts:
            alerts[vkey] = []
    def canonicalize(obj):
        if isinstance(obj, dict):
            return {k: canonicalize(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [canonicalize(x) for x in obj]
        if isinstance(obj, str):
            return obj.replace("â€”", "—").replace("â€™", "’")
        return obj
    return canonicalize(d)

def strip_md(s):
    s = re.sub(r"_Generated: [^_]+_", "_Generated: <masked>_", s)
    s = re.sub(r"## Recent Activity.*?(?=\n## |\n### |\Z)", "## Recent Activity\n<masked>\n", s, flags=re.DOTALL)
    s = re.sub(r"## Recently Retired.*?(?=\n## |\n### |\Z)", "## Recently Retired\n<masked>\n", s, flags=re.DOTALL)
    s = s.replace("â€”", "—").replace("â€™", "’")
    return s

committed_json = json.loads((tmpdir / "committed.json").read_text(encoding="utf-8") or "{}")
fresh_json = json.loads((tmpdir / "fresh.json").read_text(encoding="utf-8"))
committed_json = strip_json(committed_json)
fresh_json = strip_json(fresh_json)
json_differs = json.dumps(committed_json, sort_keys=True) != json.dumps(fresh_json, sort_keys=True)

committed_md = strip_md((tmpdir / "committed.md").read_text(encoding="utf-8", errors="replace"))
fresh_md = strip_md((tmpdir / "fresh.md").read_text(encoding="utf-8", errors="replace"))
md_differs = committed_md != fresh_md

print("DIFFER" if (json_differs or md_differs) else "MATCH")
PYEOF
    )
    rm -rf "$tmpdir"

    if [ "$result" = "DIFFER" ]; then
        echo "INDEX is out of date relative to disk state (structural content differs). Run:" >&2
        echo "  python3 .claude/skills/update-workbench-index/scripts/build_index.py Workbench" >&2
        echo "Then re-stage and commit." >&2
        echo "" >&2
        echo "Diff (volatile fields masked from check, but shown raw here):" >&2
        git --no-pager diff Workbench/INDEX.md Workbench/.index.json >&2
        return 1
    fi
    return 0
}

pre_commit_hook_syntax() {
    bash -n scripts/git-hooks/pre-commit
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
    local cap=150
    if [ ! -f CLAUDE.md ]; then
        echo "CLAUDE.md not present — skipping line-cap check"
        return 0
    fi
    local lines
    lines=$(wc -l < CLAUDE.md)
    if [ "$lines" -gt "$cap" ]; then
        echo "CLAUDE.md is $lines lines — exceeds hard cap of $cap." >&2
        echo "Trim before merging. See maintain-claude-md skill for prune guidance." >&2
        return 1
    fi
    echo "CLAUDE.md: $lines lines (cap $cap; headroom $((cap - lines)))"
    return 0
}

dogfood_telemetry_hook_check() {
    # Asserts that .claude/settings.json registers the foundry-log hook
    # at the new canonical location (.claude/hooks/foundry-log.py).
    python3 - <<'PYEOF'
import json
import sys

with open(".claude/settings.json", encoding="utf-8") as f:
    settings = json.load(f)

post_tool_use = settings.get("hooks", {}).get("PostToolUse", [])
for entry in post_tool_use:
    for h in entry.get("hooks", []):
        cmd = h.get("command", "")
        if ".claude/hooks/foundry-log.py" in cmd or "hooks/foundry-log.py" in cmd:
            print(f"dogfood telemetry hook registered: {cmd}")
            sys.exit(0)

print("FAIL: .claude/settings.json does not register the foundry-log hook.", file=sys.stderr)
print("Expected a PostToolUse hook with command containing '.claude/hooks/foundry-log.py'.", file=sys.stderr)
sys.exit(1)
PYEOF
}

if [ "${1:-}" = "--list" ]; then
    cat <<EOF
Checks:
  - plan-pipeline tests: prompts_and_parsing
  - plan-pipeline tests: build_brief
  - write-plan tests: migrate_plan_ids
  - write-plan tests: next_id
  - _shared tests: push_policy
  - ideate tests
  - INDEX freshness
  - pre-commit hook syntax
  - promote.sh syntax
  - dogfood telemetry hook registered
  - audit-foundry clean
  - CLAUDE.md hard line-cap (150)
EOF
    exit 0
fi

echo "scripts/ci/run-all.sh — running plan_foundry checks"
echo "repo_root=$REPO_ROOT in_actions=$in_actions"
echo ""

# --- Skill Python tests ---
run_check "plan-pipeline: prompts_and_parsing" \
    python3 .claude/skills/plan-pipeline/lib/test_prompts_and_parsing.py

run_check "plan-pipeline: build_brief" \
    python3 .claude/skills/plan-pipeline/lib/test_build_brief.py

run_check "write-plan: migrate_plan_ids" \
    python3 .claude/skills/write-plan/scripts/test_migrate_plan_ids.py

run_check "write-plan: next_id" \
    python3 -m pytest .claude/skills/write-plan/scripts/test_next_id.py -q

run_check "_shared: push_policy" \
    python3 -m pytest .claude/skills/_shared/lib/test_push_policy.py -q

run_check "ideate: ideate" \
    python3 .claude/skills/ideate/lib/test_ideate.py

# --- INDEX freshness ---
run_check "INDEX freshness" index_freshness_check

# --- Shell syntax ---
run_check "pre-commit hook script syntax" pre_commit_hook_syntax
run_check "promote.sh syntax" promote_sh_syntax

# --- Dogfood telemetry hook ---
run_check "dogfood telemetry hook registered" dogfood_telemetry_hook_check

# --- Foundry audit ---
run_check "audit-foundry clean" \
    python3 scripts/audit-foundry.py --no-json-output

# --- CLAUDE.md line-cap (T04) ---
run_check "CLAUDE.md hard line-cap (150)" claude_md_line_cap_check

echo ""
if [ $failed -eq 0 ]; then
    echo "ci: ALL ${checks_run} CHECKS PASSED"
    exit 0
else
    echo "ci: ${failed}/${checks_run} CHECKS FAILED" >&2
    exit 1
fi
