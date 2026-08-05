#!/usr/bin/env python3
"""
check_report_coverage.py - the committed corpus baseline names every installed skill.

What this check is for. audit-skills is model-driven and cannot run in CI, so what
CI can hold is the committed evidence of the last run. The claim being held is
coverage: a corpus audit that quietly skipped a skill reads exactly like one that
covered it, and the reader has no way to tell. Comparing the committed report
against the live corpus makes an omission visible.

What follows from that, deliberately. This check goes red when a skill is added or
retired, because at that moment the committed report stops describing the corpus. It
is a staleness signal rather than a defect in the report, and the repair is a fresh
run.

How to repair it. Re-run audit-skills over the corpus out-of-CI and commit the
captured output. Never hand-edit the committed report to add a missing name: the
report is evidence that an audit looked at each skill, and a name typed in afterwards
turns it into a claim that one did.

The check derives the corpus from disk rather than from any recorded list, and it
names the members it found missing rather than comparing totals. A total is unchanged
when one skill is added and another retired, while both facts are wrong.

Usage:
    python3 .claude/skills/audit-skills/scripts/check_report_coverage.py

Exit 0 if the committed report covers the live corpus, 1 otherwise.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parent / "fixtures" / "corpus-baseline-report.md"
REPO_ROOT = Path(__file__).resolve().parents[4]
SKILLS_DIR = REPO_ROOT / ".claude" / "skills"

JSON_FENCE_RE = re.compile(r"```json\s*\n(.*?)\n```", re.S)

HOW_TO_REGENERATE = (
    "Re-run audit-skills over the corpus out-of-CI - it is model-driven and needs a "
    "live session - and commit the captured report at the path above. Do not "
    "hand-edit the committed report to close this: the report is evidence that an "
    "audit looked at each skill, and a name added by hand is a claim that it did."
)


def rel(p: Path) -> str:
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(p)


def installed_skills() -> set[str]:
    """Every skill directory the harness would load, derived from disk."""
    if not SKILLS_DIR.is_dir():
        return set()
    return {
        d.name
        for d in SKILLS_DIR.iterdir()
        if d.is_dir() and d.name != "_shared" and (d / "SKILL.md").is_file()
    }


def trailer_findings(text: str, failures: list[str]) -> list[dict]:
    blocks = JSON_FENCE_RE.findall(text)
    if not blocks:
        failures.append(
            f"{rel(REPORT)}: no fenced json trailer - the run must emit one as its "
            "last block, and it is what a check can read without a model"
        )
        return []
    try:
        data = json.loads(blocks[-1])
    except json.JSONDecodeError as exc:
        failures.append(f"{rel(REPORT)}: the trailer does not parse as JSON - {exc}")
        return []
    if not isinstance(data, dict):
        failures.append(f"{rel(REPORT)}: the trailer must be a JSON object")
        return []
    if data.get("audit_skills_trailer") != 1:
        failures.append(
            f"{rel(REPORT)}: trailer is not version 1 of the audit-skills trailer schema"
        )
    run = data.get("run")
    if not isinstance(run, dict) or run.get("scope") != "corpus":
        failures.append(
            f"{rel(REPORT)}: the trailer's run scope must be 'corpus'. A report "
            "captured against one skill cannot evidence coverage of the corpus."
        )
    findings = data.get("findings")
    if not isinstance(findings, list) or not findings:
        failures.append(f"{rel(REPORT)}: the trailer carries no findings")
        return []
    return [f for f in findings if isinstance(f, dict)]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("# check_report_coverage - the committed baseline covers the live corpus")
    print(f"  report: {rel(REPORT)}")
    print()

    # The committed baseline describes plan_foundry's own corpus, captured against a
    # named commit of the source repo. Asserting it covers a consumer's corpus is
    # wrong by construction: a consumer may install project-local skills the report
    # was never taken against, and the documented remedy - re-running audit-skills
    # over the corpus - needs a live session they may not be in. So the coverage
    # assertion runs only where the baseline is authored.
    if not (REPO_ROOT / "scripts" / "promote.sh").is_file() or not (
        REPO_ROOT / "scripts" / "prod-repo.txt"
    ).is_file():
        print(
            "NOTICE: this is a consumer install, not the plan_foundry source repo. "
            "The committed baseline describes the source corpus, so coverage is not "
            "asserted here."
        )
        print("check_report_coverage: skipped (consumer install).")
        return 0

    failures: list[str] = []

    corpus = installed_skills()
    if not corpus:
        print(
            "ERROR: no skill directories found on disk - refusing to run. An empty "
            "corpus would make coverage trivially true.",
            file=sys.stderr,
        )
        return 1

    if not REPORT.is_file():
        print(f"ERROR: no corpus baseline report at {rel(REPORT)}.", file=sys.stderr)
        print(HOW_TO_REGENERATE, file=sys.stderr)
        return 1

    text = REPORT.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"ERROR: {rel(REPORT)} is empty.", file=sys.stderr)
        print(HOW_TO_REGENERATE, file=sys.stderr)
        return 1

    findings = trailer_findings(text, failures)
    reported = {
        f.get("skill")
        for f in findings
        if isinstance(f.get("skill"), str) and f.get("skill").strip()
    }

    missing_from_trailer = sorted(corpus - reported)
    if missing_from_trailer:
        failures.append(
            "installed skill(s) absent from the report's trailer: "
            + ", ".join(missing_from_trailer)
        )

    stale_in_trailer = sorted(reported - corpus)
    if stale_in_trailer:
        failures.append(
            "the trailer names skill(s) that are not installed: "
            + ", ".join(stale_in_trailer)
            + " - the report describes a corpus that no longer exists"
        )

    missing_from_prose = sorted(name for name in corpus if f"`{name}`" not in text)
    if missing_from_prose:
        failures.append(
            "installed skill(s) not named in the report body: "
            + ", ".join(missing_from_prose)
            + " - a trailer entry with no prose behind it is a row, not an audit"
        )

    edited = sorted(
        {
            f.get("skill")
            for f in findings
            if f.get("files_edited") not in ([], None)
        }
        - {None}
    )
    if edited:
        failures.append(
            "the trailer records file edits against: "
            + ", ".join(str(e) for e in edited)
            + " - audit-skills reports and never patches, so files_edited is empty "
            "for every finding"
        )

    if failures:
        print(f"ERROR: {rel(REPORT)} does not cover the live corpus.", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)
        print(HOW_TO_REGENERATE, file=sys.stderr)
        return 1

    print("check_report_coverage: every installed skill is named in the report and its trailer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
