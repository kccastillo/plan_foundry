#!/usr/bin/env python3
"""
check_ownership_branch.py - assert each ownership branch behaved as the policy requires.

What this check is for. The ownership determination decides whether a defect found
in a skill is raised against the bundle or offered to the reader as a proposed fix,
and the three branches differ in what they are allowed to do rather than in what
they found. Each committed fixture is a captured audit run over a probe seeded with
one identical defect, so ownership is the only variable across the three, and the
difference in what happened to that defect is the whole content of each case.

What it asserts, and against what. Prose showing the right branch is not enough for
a check that runs with no model available, so each captured run ends with a fenced
JSON trailer emitted as part of the run. This reads the last such block and asserts
against it: the verdict the determination returned, the action that followed, and
that nothing was edited.

The property that separates the cases is `action`, never file mutation. audit-skills
reports and never patches, including where it is certain and where the branch permits
a proposal, so `files_edited` is empty in all three cases and this check asserts that
it is. A check demanding a non-empty `files_edited` on the consumer-owned case would
demand something the contract guarantees cannot happen, and would redden on a correct
artefact.

Where the fixtures come from. Each is a captured audit-skills run against a seeded
sandbox probe, out-of-CI because the skill is model-driven. They are evidence of a
run, so a failing fixture is repaired by re-running the case that produced it, never
by editing the committed file.

Usage:
    python3 .claude/skills/audit-skills/scripts/check_ownership_branch.py --case bundle-managed
    python3 .claude/skills/audit-skills/scripts/check_ownership_branch.py --case consumer-owned
    python3 .claude/skills/audit-skills/scripts/check_ownership_branch.py --case undeterminable

Exit 0 if the named case's fixture holds, 1 otherwise, with the reason named.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"
REPO_ROOT = Path(__file__).resolve().parents[4]

# case name -> (verdict classify_skill_ownership must have returned, action that follows)
CASES: dict[str, tuple[str, str]] = {
    "bundle-managed": ("bundle_managed", "raised"),
    "consumer-owned": ("consumer_owned", "proposed_fix"),
    "undeterminable": ("undeterminable", "raised"),
}

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)

HOW_TO_REGENERATE = (
    "A fixture here is evidence of a run, not a document. Repair it by re-running "
    "audit-skills out-of-CI against a probe seeded for this case and committing the "
    "captured output, never by hand-editing the committed file - an edited transcript "
    "records what someone wanted the run to say."
)


def rel(p: Path) -> str:
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(p)


def extract_trailer(text: str) -> tuple[dict | None, str | None]:
    """Return the last fenced json block parsed, or a reason it could not be."""
    blocks = JSON_FENCE_RE.findall(text)
    if not blocks:
        return None, "no fenced json trailer found - the run must emit one as its last block"
    try:
        data = json.loads(blocks[-1])
    except json.JSONDecodeError as exc:
        return None, f"the trailer does not parse as JSON - {exc}"
    if not isinstance(data, dict):
        return None, "the trailer must be a JSON object"
    return data, None


def check_case(case: str, failures: list[str]) -> None:
    expected_verdict, expected_action = CASES[case]
    path = FIXTURES / f"ownership-{case}.md"

    if not path.is_file():
        failures.append(f"no fixture at {rel(path)}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        failures.append(f"{rel(path)} is empty")
        return

    trailer, why = extract_trailer(text)
    if trailer is None:
        failures.append(f"{rel(path)}: {why}")
        return

    if trailer.get("audit_skills_trailer") != 1:
        failures.append(
            f"{rel(path)}: trailer is not version 1 of the audit-skills trailer schema"
        )

    run = trailer.get("run")
    if not isinstance(run, dict):
        failures.append(f"{rel(path)}: trailer carries no 'run' object")
    else:
        if run.get("case") != case:
            failures.append(
                f"{rel(path)}: trailer records case {run.get('case')!r}, "
                f"but this fixture is read as {case!r}"
            )
        date = run.get("date")
        if not isinstance(date, str) or not DATE_RE.match(date):
            failures.append(f"{rel(path)}: trailer carries no YYYY-MM-DD run date")

    findings = trailer.get("findings")
    if not isinstance(findings, list) or not findings:
        failures.append(f"{rel(path)}: trailer carries no findings")
        return

    for i, finding in enumerate(findings):
        where = f"{rel(path)}: findings[{i}]"
        if not isinstance(finding, dict):
            failures.append(f"{where} is not an object")
            continue

        skill = finding.get("skill")
        if not isinstance(skill, str) or not skill.strip():
            failures.append(f"{where} names no skill")

        verdict = finding.get("ownership")
        if verdict != expected_verdict:
            failures.append(
                f"{where} records ownership {verdict!r}, expected {expected_verdict!r} "
                f"for the {case} case"
            )

        signal = finding.get("signal")
        if not isinstance(signal, str) or not signal.strip():
            failures.append(
                f"{where} carries no signal string. The signal is what the "
                "determination returned alongside the verdict, and it is how a reader "
                "tells a mechanism's answer from a reasoned-out one."
            )

        action = finding.get("action")
        if action != expected_action:
            failures.append(
                f"{where} records action {action!r}, expected {expected_action!r} "
                f"for the {case} case"
            )

        edited = finding.get("files_edited")
        if edited != []:
            failures.append(
                f"{where} records files_edited {edited!r}. audit-skills reports and "
                "never patches, so this is empty in every case including the one that "
                "permits a proposed fix - a proposal is prose in the report, not a "
                "mutation."
            )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    argv = sys.argv[1:]
    case = None
    if "--case" in argv:
        idx = argv.index("--case")
        if idx + 1 < len(argv):
            case = argv[idx + 1]

    if case not in CASES:
        print(
            "ERROR: --case must name one of: " + ", ".join(sorted(CASES)),
            file=sys.stderr,
        )
        return 1

    print(f"# check_ownership_branch - the {case} branch behaved as the policy requires")
    print(f"  fixture: {rel(FIXTURES / f'ownership-{case}.md')}")
    print()

    failures: list[str] = []
    check_case(case, failures)

    if failures:
        print(f"ERROR: the {case} ownership fixture does not hold.", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)
        print(HOW_TO_REGENERATE, file=sys.stderr)
        return 1

    verdict, action = CASES[case]
    print(f"check_ownership_branch: {case} - verdict {verdict}, action {action}, nothing edited.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
