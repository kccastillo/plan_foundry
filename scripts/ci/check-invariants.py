#!/usr/bin/env python3
"""Executable assertions for the ARCHITECTURE.md Invariants Register.

The Invariants Register names load-bearing facts the harness depends on. It was
prose-only - nothing failed when an invariant broke, which is the exact
silent-erosion the register says it exists to prevent. This script makes the
mechanically-assertable invariants executable, so a tidy-up that drops one is
caught here instead of by a maintainer debugging red CI later.

Standalone:  python3 scripts/ci/check-invariants.py
In CI:       scripts/ci/run-all.sh dispatches it as the "foundry invariants" check.

Exit 0 when every assertion holds; exit 1 (with an "ERROR:" line) otherwise.
"""

import ast
import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

results = []  # (invariant_name, ok: bool, detail: str)


def record(name, ok, detail):
    results.append((name, ok, detail))


# --- Deterministic Projection ------------------------------------------------
# audit-foundry.py is a "deterministic projection" - it emits CI-compared
# output. Directory iteration (iterdir/glob/rglob/scandir/listdir) returns
# host filesystem order, which differs across machines - so every such call
# in this tool must be wrapped in sorted(). An inline "determinism-ok"
# comment opts out a genuinely order-independent call.
_ITER_NAMES = {"iterdir", "glob", "rglob", "scandir", "listdir"}
_DETERMINISM_SCOPED = (
    "scripts/audit-foundry.py",
)


def _unsorted_iterations(tree):
    sorted_first_args = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "sorted"
            and node.args
        ):
            sorted_first_args.add(id(node.args[0]))
    flagged = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        else:
            name = None
        if name in _ITER_NAMES and id(node) not in sorted_first_args:
            flagged.append(node.lineno)
    return flagged


def check_deterministic_projection():
    offenders = []
    for rel in _DETERMINISM_SCOPED:
        path = REPO_ROOT / rel
        if not path.is_file():
            offenders.append(f"{rel}: file missing")
            continue
        src = path.read_text(encoding="utf-8")
        lines = src.splitlines()
        try:
            tree = ast.parse(src, filename=rel)
        except SyntaxError as exc:
            # A syntax error here used to raise uncaught, which killed this
            # invariant AND skipped the remaining six (the failure never got
            # named - it was an opaque traceback at invariant one). Record it
            # as a FAILED offender instead, so the other invariants still run.
            offenders.append(f"{rel}: does not parse - {exc}")
            continue
        for lineno in _unsorted_iterations(tree):
            line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if "determinism-ok" in line:
                continue
            offenders.append(f"{rel}:{lineno} directory iteration not wrapped in sorted()")
    record(
        "Deterministic Projection",
        not offenders,
        "all directory iteration sorted" if not offenders else "; ".join(offenders),
    )


# --- Doc-Set Integrity -------------------------------------------------------
# The harness's design depends on these root docs existing. The set is the same
# in the source repo and in a consumer install, so the check is unconditional.
def check_doc_set_integrity():
    docs = ["CLAUDE.md", "ARCHITECTURE.md", "README.md"]
    missing = [d for d in docs if not (REPO_ROOT / d).is_file()]
    record(
        "Doc-Set Integrity",
        not missing,
        f"all {len(docs)} root docs present" if not missing else f"missing: {', '.join(missing)}",
    )


# --- Portable Bundle ---------------------------------------------------------
# The global-clone model (AC5) put the bundle at ~/.claude/plan_foundry/, which
# breaks sandboxed sessions whose only writable surface is the target repo. The
# install / sync / check skills must never reference that path again.
_GLOBAL_CLONE_TOKEN = ".claude/plan_foundry"
_BUNDLE_SKILL_DIRS = (
    ".claude/skills/init-plan-foundry",
    ".claude/skills/plan-foundry-sync",
    ".claude/skills/plan-foundry-check-current",
    ".claude/skills/plan-foundry-uninstall",
)


def check_portable_bundle():
    hits = []
    for rel in _BUNDLE_SKILL_DIRS:
        base = REPO_ROOT / rel
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if _GLOBAL_CLONE_TOKEN in text:
                hits.append(str(path.relative_to(REPO_ROOT)))
    record(
        "Portable Bundle",
        not hits,
        "no global-clone path references"
        if not hits
        else f"forbidden '{_GLOBAL_CLONE_TOKEN}' in: {', '.join(hits)}",
    )


# --- Subagent Permission Inheritance -----------------------------------------
# Subagents do not inherit the parent's Bash allowlist, so the executor agents
# must structurally deny Bash via disallowedTools.
_EXECUTOR_AGENTS = (
    "plan-executor.md",
    "plan-executor-sonnet.md",
    "plan-executor-opus.md",
)


def _disallowed_tools_region(text):
    """Return the disallowedTools key's lines from agent frontmatter.

    Agent frontmatter is not strict YAML - the description field carries
    unquoted colons - so the disallowedTools key is extracted directly rather
    than via a YAML parse. Handles both the flow form (`[Bash, ...]`) and an
    indented block list.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    region = []
    capturing = False
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("disallowedTools:"):
            capturing = True
            region.append(line)
        elif capturing:
            if line.startswith((" ", "\t")):
                region.append(line)
            else:
                break
    return "\n".join(region)


def check_subagent_permission_inheritance():
    bad = []
    for name in _EXECUTOR_AGENTS:
        path = REPO_ROOT / ".claude" / "agents" / name
        if not path.is_file():
            bad.append(f"{name}: missing")
            continue
        region = _disallowed_tools_region(path.read_text(encoding="utf-8"))
        if not re.search(r"\bBash\b", region):
            bad.append(f"{name}: disallowedTools does not deny Bash")
    record(
        "Subagent Permission Inheritance",
        not bad,
        "executor agents deny Bash" if not bad else "; ".join(bad),
    )


# --- Agent Frontmatter Portability -------------------------------------------
# Per ADVICE-009 (2026-05-24): the Anthropic harness loader silently drops
# agent files whose frontmatter carries fields outside its documented schema.
# `background: true` in particular was found shipping in prod and caused the
# three executor subagents to load as unknown in a transplanted consumer
# session. `run_in_background` is a property of the *dispatch call site*
# (plan-pipeline/workflows/dispatch.md), not the agent definition. Per
# ADVICE-010 section Layer 2 (2026-05-24): use an allowlist rather than a denylist so
# the entire class of fat-fingered or speculative frontmatter fields is caught,
# not just `background:`. The cost is one allowlist entry per legitimate new
# Anthropic-documented field - cheap, and forces docs-check before adding fields.
_AGENT_FRONTMATTER_ALLOWLIST = frozenset({
    "name", "model", "description", "tools", "disallowedTools", "skills",
})


def check_agent_frontmatter_portability():
    bad = []
    agents_dir = REPO_ROOT / ".claude" / "agents"
    for path in sorted(agents_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            continue
        for line in lines[1:]:
            stripped = line.rstrip()
            if stripped == "---":
                break
            # only top-level keys are checked - indented continuation lines
            # (block-scalar bodies, list items) are skipped
            if not line or line[0] in (" ", "\t"):
                continue
            m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:", line)
            if not m:
                continue
            key = m.group(1)
            if key not in _AGENT_FRONTMATTER_ALLOWLIST:
                bad.append(f"{path.name}: unknown frontmatter key '{key}' (allowlist: {sorted(_AGENT_FRONTMATTER_ALLOWLIST)})")
    record(
        "Agent Frontmatter Portability",
        not bad,
        "no unknown frontmatter keys in agent files" if not bad else "; ".join(bad),
    )


# --- Agent Description Quoting -----------------------------------------------
# Per ADVICE-009 (2026-05-26): the Anthropic harness loader silently drops
# agent files whose frontmatter `description:` value is an unquoted YAML scalar
# containing colon-space (`: `). The drop is silent, which is exactly what the
# invariants register exists to prevent. This check enforces that all
# `description:` fields are quoted (double-quote, single-quote, or block scalar)
# or do not contain unquoted `: ` patterns.


def _unquoted_description_offenders(paths):
    """Return a list of 'file:line: reason' strings for unquoted descriptions.

    Shared by the agent and skill checks. Extracted 2026-07-27: the agent
    variant of this walk had existed since ADVICE-009 while 16 of 27
    SKILL.md files carried the identical defect, because the checker was
    written for one directory and never widened. See
    FOUNDRYREQ-...-1955-skill-description-frontmatter-unquoted.
    """
    bad = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            continue
        for i, line in enumerate(lines[1:], start=1):
            if line.rstrip() == "---":
                break
            m = re.match(r"^description:\s*(.*)$", line)
            if not m:
                continue
            value = m.group(1)
            if value and value[0] in ('"', "'", ">", "|"):
                continue
            if ": " in value:
                bad.append(
                    f"{path.parent.name}/{path.name}:{i}: unquoted description "
                    f"contains ': ' (value: {value[:60]}"
                    f"{'...' if len(value) > 60 else ''})"
                )
    return bad


def check_skill_description_quoting():
    skills_dir = REPO_ROOT / ".claude" / "skills"
    bad = _unquoted_description_offenders(sorted(skills_dir.glob("*/SKILL.md")))
    record(
        "Skill Description Quoting",
        not bad,
        "all skill descriptions properly quoted" if not bad else "; ".join(bad),
    )


def check_agent_description_quoting():
    bad = []
    agents_dir = REPO_ROOT / ".claude" / "agents"
    for path in sorted(agents_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            continue
        for i, line in enumerate(lines[1:], start=1):
            if line.rstrip() == "---":
                break
            # match description: at start of line
            m = re.match(r"^description:\s*(.*)$", line)
            if not m:
                continue
            value = m.group(1)
            # if the value starts with a quote or block scalar indicator,
            # it is quoted and safe regardless of internal content
            if value and value[0] in ('"', "'", ">", "|"):
                continue
            # unquoted scalar: check for colon-space sequence
            if ": " in value:
                bad.append(
                    f"{path.name}:{i}: unquoted description contains ': ' "
                    f"(value: {value[:60]}{'...' if len(value) > 60 else ''})"
                )
    record(
        "Agent Description Quoting",
        not bad,
        "all agent descriptions properly quoted" if not bad else "; ".join(bad),
    )


def main():
    # Windows consoles default to cp1252, which cannot encode the em dashes and
    # box-drawing characters this script prints - the output mojibakes rather
    # than failing, so the corruption is easy to miss. Same guard as PLAN-AF2
    # applied to the five earlier CLI entry points.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    check_deterministic_projection()
    check_doc_set_integrity()
    check_portable_bundle()
    check_subagent_permission_inheritance()
    check_agent_frontmatter_portability()
    check_agent_description_quoting()
    check_skill_description_quoting()

    print("# foundry invariants - executable assertions for the ARCHITECTURE.md register")
    print()
    failed = 0
    for name, ok, detail in results:
        print(f"  [{'ok' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            failed += 1
    print()
    print("  PLAN ID Uniqueness     - covered by .claude/skills/write-plan/scripts/test_next_id.py")
    print("  Substrate Verification - covered by .claude/skills/audit-haiku-safe/lib/test_substrate_fidelity.py")
    print()
    if failed:
        print("ERROR: invariant assertion(s) failed.", file=sys.stderr)
        return 1
    print("All mechanically-asserted invariants hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
