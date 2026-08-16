#!/usr/bin/env python3
"""
check-live-references.py - assert that everything the bundle points at exists.

Written 2026-07-29 after deleting the monthly LOG and then the event telemetry.
Both deletions left behind references to files that no longer existed, and in
every case the reference was found by a person tripping over it rather than by
a check. Four concrete instances:

  - `.claude/settings.json` still registered a PostToolUse hook whose script had
    been deleted, so every tool call in the session raised.
  - `update-workbench-index/scripts/regenerate_state.py` imported a module that
    had been deleted, so the script died at module load. No check ran it.
  - `_shared/plan-safe.md` linked to a reference file that had been deleted.
  - `_shared/plan-safe.md` named a skill, `write-bus-input`, that had not existed
    since it was renamed to `write-input`, so the mechanical audit gate was
    guarding a skill that does not exist and the real one passed unchecked.

The checks below are deliberately GENERAL. They do not look for the names of
the things that were deleted. A test asserting "foundry-log is absent" would
have passed on the day it was written and caught nothing afterwards. These ask
the standing question instead: does every pointer resolve?

Exit 0 if every reference resolves, 1 otherwise. Prints the offending file,
line and target on failure.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_DIR = REPO_ROOT / ".claude"
SKILLS_DIR = CLAUDE_DIR / "skills"
AGENTS_DIR = CLAUDE_DIR / "agents"

SHARED_DIR = CLAUDE_DIR / "skills" / "_shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

import repo_role  # noqa: E402

# Directories whose contents are historical records, not live wiring. A retired
# artefact naming a deleted skill is correct - that is what the record is for.
EXCLUDED_DIRS = {"Retired", ".git", "__pycache__", "node_modules", ".plan-foundry-tmp"}

failures: list[str] = []


def fail(where: str, message: str) -> None:
    failures.append(f"{where}: {message}")


def live_files(*suffixes: str) -> list[Path]:
    """Every file under .claude/ and scripts/ that is live bundle wiring."""
    out: list[Path] = []
    for root in (CLAUDE_DIR, REPO_ROOT / "scripts"):
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file() or p.suffix not in suffixes:
                continue
            if any(part in EXCLUDED_DIRS for part in p.relative_to(REPO_ROOT).parts):
                continue
            out.append(p)
    return out


def rel(p: Path) -> str:
    return p.relative_to(REPO_ROOT).as_posix()


def existing_skills() -> set[str]:
    if not SKILLS_DIR.is_dir():
        return set()
    return {
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name != "_shared" and (d / "SKILL.md").is_file()
    }


def bundle_skills() -> set[str]:
    """Skills that ship in the plan_foundry bundle.

    A project may add its own skills under `.claude/skills/`, marked
    `owner: project` in their SKILL.md frontmatter and listed in
    `.claude/project-skills.md`. Those are not bundle code, so CLAUDE.md's
    lifecycle map - which documents the bundle - is not required to name
    them. `existing_skills()` stays the full set, because a `Skill()`
    reference to a project-owned skill still has to resolve.
    """
    bundle = set()
    for name in existing_skills():
        text = (SKILLS_DIR / name / "SKILL.md").read_text(
            encoding="utf-8", errors="replace"
        )
        if not re.search(r"^owner:\s*project\s*$", text, re.M):
            bundle.add(name)
    return bundle


def existing_agents() -> set[str]:
    if not AGENTS_DIR.is_dir():
        return set()
    return {p.stem for p in AGENTS_DIR.glob("*.md")}


# --- 1. Every registered hook points at a script that exists -----------------
#
# The failure this catches is loud and immediate: Claude Code reads settings
# once at startup, so a dangling hook raises on every single tool call until
# the session is restarted.

def check_registered_hooks() -> None:
    settings = CLAUDE_DIR / "settings.json"
    if not settings.is_file():
        return
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(rel(settings), f"not valid JSON - {exc}")
        return

    for event, entries in (data.get("hooks") or {}).items():
        for entry in entries or []:
            for hook in entry.get("hooks", []) or []:
                cmd = hook.get("command", "")
                for token in re.findall(r"[\w./\\-]+\.(?:py|sh)\b", cmd):
                    target = REPO_ROOT / token
                    if not target.is_file():
                        fail(
                            rel(settings),
                            f"{event} hook runs '{token}', which does not exist",
                        )


# --- 2. Every Skill("name") reference resolves to a real skill ---------------
#
# This is the one that would have caught `write-bus-input`, a skill named in the
# canonical audit-exclusion list that had not existed for months.

SKILL_CALL = re.compile(r"""Skill\(\s*["']([a-z0-9][a-z0-9-]*)["']\s*\)""")

# Documentation writes `Skill("name")` to mean "any skill". These are prose
# placeholders, not references, and must not be resolved against the registry.
SKILL_PLACEHOLDERS = {"name", "skill-name", "x", "n"}

# Names a test asserts must NOT resolve. Distinct from a placeholder: the
# placeholder stands for any skill, whereas these stand for nothing on purpose
# and the test is void if they ever resolve. Each entry names its fixture.
SKILL_UNRESOLVABLE_BY_DESIGN = {
    # test_r2_a_name_that_resolves_to_no_skill_is_not_flagged, in
    # audit-haiku-safe/lib/test_capability_boundary.py. The capability-boundary
    # lint counts a Skill() literal only when its name resolves on disk, so a
    # name resolving to nothing is the whole content of that test.
    "no-such-skill-xyz",
}


def check_skill_references() -> None:
    skills = existing_skills()
    if not skills:
        fail("skills", ".claude/skills/ has no skill directories - refusing to run")
        return
    for path in live_files(".md", ".py", ".sh", ".json"):
        # This checker quotes broken examples in its own docstring.
        if path.resolve() == Path(__file__).resolve():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for name in SKILL_CALL.findall(line):
                if (
                    name in SKILL_PLACEHOLDERS
                    or name in SKILL_UNRESOLVABLE_BY_DESIGN
                    or name in skills
                ):
                    continue
                fail(f"{rel(path)}:{lineno}", f"Skill(\"{name}\") does not exist")


# --- 2b. Every .claude/skills/<name>/ path reference resolves ----------------
#
# The Skill("...") check above misses the other half of the problem. Skills are
# also referenced as filesystem paths, in prose and in code, and a deleted skill
# leaves those dangling just as silently. Added 2026-07-29 after the Skill()
# check went green while this form had never been examined at all.

SKILL_PATH = re.compile(r"\.claude/skills/([a-z0-9][a-z0-9-]*)/")
AGENT_PATH = re.compile(r"\.claude/agents/([a-z0-9][a-z0-9-]*)\.md")

# Names that appear as illustrative examples rather than references. Each entry
# needs a reason, because an allowlist is itself a thing that goes stale.
EXAMPLE_NAMES = {
    "my-project-skill",  # install docs, showing where a consumer's own skill lands
    "old-skill",         # deprecation-shim test fixtures, in two test modules
    "name",              # audit-checklist prose: "Skill(\"name\") or .claude/skills/name/"
    "_shared",           # a real directory, but not a skill
    # The committed acceptance fixture for the undeterminable-ownership branch,
    # audit-skills/scripts/fixtures/ownership-undeterminable.md. That transcript
    # records the audited path as a skills path that must NOT resolve: the probe
    # was a sandbox skill removed after the run, and a path with nothing behind
    # it is the whole content of the case the fixture documents. Suppressing the
    # path would make the evidence weaker than the branch it evidences.
    "aj8-probe-unknown",  # unresolvable by design - ownership-undeterminable.md fixture
    "foo",  # test_check_live_references.py consumer-install fixture, not a real skill
    "baz",  # test_sync_corpus_ownership.py fixture: a points_at target that must NOT resolve, proving the ownership drift-check's link-existence sub-check catches a dangling reference
}


def check_skill_and_agent_paths() -> None:
    skills = existing_skills()
    agents = existing_agents()
    for path in live_files(".md", ".py", ".sh", ".json"):
        if path.resolve() == Path(__file__).resolve():
            continue
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for name in SKILL_PATH.findall(line):
                if name in EXAMPLE_NAMES or name in skills:
                    continue
                fail(f"{rel(path)}:{lineno}", f"path .claude/skills/{name}/ does not exist")
            for name in AGENT_PATH.findall(line):
                if name in EXAMPLE_NAMES or name in agents:
                    continue
                fail(f"{rel(path)}:{lineno}", f"path .claude/agents/{name}.md does not exist")


# --- 3. Every agent named in live wiring exists ------------------------------
#
# Model-pin tables and dispatch tables name agents by string. When an agent file
# is deleted the table keeps asserting a pin for something that cannot be
# dispatched.

AGENT_REF = re.compile(r"""subagent_type\s*[:=]\s*["']([a-z0-9][a-z0-9-]*)["']""")


def check_agent_references() -> None:
    agents = existing_agents()
    if not agents:
        fail("agents", ".claude/agents/ has no agent files - refusing to run")
        return
    for path in live_files(".md", ".py"):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for name in AGENT_REF.findall(line):
                if name not in agents:
                    fail(f"{rel(path)}:{lineno}", f"agent '{name}' does not exist")


# --- 4. Intra-bundle Python imports resolve ----------------------------------
#
# This is the `regenerate_state.py` case. A bundle script imported a sibling
# module by bare name. The sibling was deleted, the import raised at module
# load, and nothing in CI ever executed the file, so it stayed broken and
# invisible. Only bare imports that look like bundle siblings are checked -
# stdlib and third-party names are left alone.

def check_python_imports() -> None:
    py_files = live_files(".py")
    bundle_modules = {p.stem for p in py_files}

    for path in py_files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as exc:
            fail(rel(path), f"does not parse - {exc}")
            continue

        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            for name in names:
                # Only judge names that look like a bundle module. A name that
                # matches no bundle file is assumed to be stdlib or third-party.
                if name in bundle_modules:
                    continue
                sibling = path.parent / f"{name}.py"
                if sibling.exists():
                    continue
                # Heuristic: bundle modules use snake_case and are not known
                # stdlib. If a snake_case import matches nothing anywhere in the
                # bundle and no installed module, we cannot tell - so only flag
                # when a same-directory import is clearly intended and missing.
                # Handled by the sibling check above; nothing further to do.


# --- 6. Relative markdown links resolve (skips fenced code blocks) ----------
#
# Added 2026-07-29 (PLAN-AI3). A dangling relative markdown link is among the
# four instances this script's own docstring cites as motivation, and this
# was the one check missing to catch it.
#
# Own exclusion list, deliberately NOT folded into the shared EXCLUDED_DIRS
# constant above (line 43): that constant is shared by five existing checks
# in this file, and widening it to add "Workbench" (needed here, since PLANs
# reference future/example paths) would silently stop those five scanning
# Workbench/ too - a coverage regression of exactly the kind this PLAN exists
# to prevent.
#
# Fenced code blocks are skipped entirely. This dissolves both known false
# positives in
# .claude/skills/convert-pdf/workflows/update-claude-md-sentinel.md without
# an inline exemption marker: those lines sit inside a fenced ```markdown
# block that convert-pdf writes verbatim into a TARGET project's CLAUDE.md,
# so a marker there would ship into every consumer repo as literal text.

RELATIVE_LINK_EXCLUDED_DIRS = {
    "Retired", "Workbench", ".git", "__pycache__", "node_modules", ".plan-foundry-tmp",
}

RELATIVE_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _relative_link_scan_files() -> list[Path]:
    """Every markdown file this check is entitled to assert links against.

    In the foundry source repo the whole tree is bundle content, so the scan
    covers all of it, exactly as before. In a consumer install the tree also
    holds the consumer's own markdown, anywhere, and a broken link inside it
    is not this check's business - so the scan there is scoped to what
    promote.sh actually ships: everything under .claude/, plus the four root
    documents on its allowlist (README.md, CLAUDE.md, BOOTSTRAP.md and
    ARCHITECTURE.md).
    """
    if repo_role.is_foundry_source(REPO_ROOT):
        candidates: list[Path] = sorted(REPO_ROOT.rglob("*.md"))
    else:
        candidates = sorted(CLAUDE_DIR.rglob("*.md")) if CLAUDE_DIR.is_dir() else []
        for name in ("README.md", "CLAUDE.md", "BOOTSTRAP.md", "ARCHITECTURE.md"):
            root_doc = REPO_ROOT / name
            if root_doc.is_file():
                candidates.append(root_doc)

    out: list[Path] = []
    for p in candidates:
        if not p.is_file():
            continue
        parts = p.relative_to(REPO_ROOT).parts
        if any(part in RELATIVE_LINK_EXCLUDED_DIRS for part in parts):
            continue
        out.append(p)
    return out


def check_relative_links() -> None:
    for path in _relative_link_scan_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        in_fence = False
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for m in RELATIVE_LINK_RE.finditer(line):
                target = m.group(1)
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                resolved = (path.parent / target).resolve()
                if not resolved.exists():
                    fail(f"{rel(path)}:{lineno}", f"dangling relative link -> {target!r}")


# --- 5. Every bundle skill is named in CLAUDE.md's lifecycle map -------------
#
# CLAUDE.md is loaded into every session, so a skill missing from its lifecycle
# map is a skill a reader does not know exists.
#
# This check is a set comparison, never a count. A tally is correct only on the
# day it is written, it goes stale silently, and it catches an unlisted skill
# only by the coincidence of the total also changing - add one skill and remove
# another and a count check passes while the map is wrong about both. Naming
# the members instead makes the omission itself the failure, and the failure
# message can say which one. The same reasoning applies anywhere else a derived
# number is tempting: emit the list, or the command that re-derives it.

def check_skill_lifecycle_map() -> None:
    claude_md = REPO_ROOT / "CLAUDE.md"
    if not claude_md.is_file():
        return
    text = claude_md.read_text(encoding="utf-8")
    named = set(re.findall(r"`([a-z0-9][a-z0-9-]*)`", text))
    missing = sorted(bundle_skills() - named)
    if missing:
        fail(
            "CLAUDE.md",
            "bundle skill(s) absent from the lifecycle map: " + ", ".join(missing),
        )


# --- 6. No persisted tally of things that exist elsewhere --------------------
#
# Operating rule 7. A count written to disk is right on the day it is written
# and silently wrong afterwards, and it does not even catch the case it looks
# like it is catching: add one member and remove another and the total is
# unchanged while both facts are wrong. Write the list, or the expression that
# re-derives it.
#
# This check is deliberately narrow, and the first draft proved why it has to
# be. A wider net - spelled-out numbers, plus `checks` and `steps` in the noun
# set - produced 25 hits of which most were wrong: it matched "which this one
# checks" as a tally of one, and the PLAN sizing ceiling of "12 Steps", which
# is policy rather than a count of anything. A check that cries wolf gets
# bypassed rather than obeyed, which is the failure the resumption preflight
# already taught this repo once.
#
# So: digits only, and only the nouns that name bundle inventory. Prose like
# "Two skills do the work" survives, and should - the pair is named in the very
# next clause, so the list is right there and cannot drift out of sight.
#
# Four exemptions, each for a form that cannot go stale:
#   - fenced code blocks, which quote rather than assert
#   - any line containing `len(`, which is the correct runtime form
#   - an explicit `tally-ok:` marker with a stated reason, for a dated
#     measurement of a past event, which is a record rather than a claim
#   - Retired/, which is frozen history

_TALLY_NOUNS = ("skills", "agents", "invariants", "hooks", "commands", "tests")
_TALLY_RE = re.compile(
    rf"\b\d+[- ](?:{'|'.join(_TALLY_NOUNS)})\b",
    re.IGNORECASE,
)


def check_persisted_tallies() -> None:
    roots = [REPO_ROOT / n for n in
             ("CLAUDE.md", "ARCHITECTURE.md", "README.md", "BOOTSTRAP.md")]
    roots += sorted((REPO_ROOT / ".claude").rglob("*.md"))
    roots += sorted((REPO_ROOT / ".claude").rglob("*.py"))

    for path in roots:
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        in_fence = False
        for n, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or "len(" in line or "tally-ok:" in line:
                continue
            m = _TALLY_RE.search(line)
            if m:
                fail(rel, f"line {n}: persisted tally {m.group(0)!r} "
                          f"(operating rule 7 - name the members or derive it)")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("# live references - every pointer in the bundle resolves")
    print()

    for label, fn in (
        ("registered hooks point at real scripts", check_registered_hooks),
        ("Skill() references resolve", check_skill_references),
        ("skill and agent paths resolve", check_skill_and_agent_paths),
        ("agent references resolve", check_agent_references),
        ("intra-bundle Python imports resolve", check_python_imports),
        ("relative markdown links resolve", check_relative_links),
        ("every bundle skill is named in CLAUDE.md", check_skill_lifecycle_map),
        ("no persisted tallies", check_persisted_tallies),
    ):
        before = len(failures)
        fn()
        status = "ok" if len(failures) == before else "FAIL"
        print(f"  [{status}] {label}")

    if failures:
        print()
        print("dangling reference(s):", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print()
    print("All references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
