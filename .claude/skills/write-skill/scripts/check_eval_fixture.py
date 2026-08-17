#!/usr/bin/env python3
"""
check_eval_fixture.py - assert this repo produced a measured triggering fixture.

What this check is for. A skill's description is a match surface, and whether it
fires is a model's selection decision. There is no model in CI, so nothing here
re-runs the measurement. What it asserts is narrower and still worth having: that
the acceptance fixture exists, parses, carries both prompt sets, and records rates
that were measured rather than asserted.

Why that is the useful assertion. The failure this guards against is a skill
shipping with a description nobody ever tested, behind a sentence in a plan saying
triggering was proved. A fixture with a measured block and a run date is evidence
that the runs happened; a fixture without one is the claim the runs were meant to
replace. So the check reads the record and refuses to accept a fixture whose rates
appeared without a date, a run count, or a value.

Where the fixture comes from. Run the procedure in write-skill's
workflows/prove-triggering.md against a real skill in a live session, then write
the result into the fixture. Never hand-author the measured block.

Usage:
    python3 .claude/skills/write-skill/scripts/check_eval_fixture.py
    python3 .claude/skills/write-skill/scripts/check_eval_fixture.py --require-measured

Without --require-measured the fixture's shape is checked and the measured block is
optional; an absent fixture is reported as a NOTICE and exits 0, because a repo that
has not yet measured a skill is in a normal state rather than a broken one. With the
flag, the fixture must exist and its measured block must be present, complete, and
meet the thresholds the fixture itself declares.

That split is what makes the check safe to register in a suite with one exit code.
Registered without the flag it stays a visible line in every run naming what is not
yet measured, and it fails only on an artefact that is actually wrong - a fixture
that does not parse, has lost a prompt set, or carries a rate below its own floor.
Pass --require-measured when a caller genuinely requires the measurement to exist,
which is a per-skill acceptance question rather than a standing suite one.

Exit 0 if the fixture satisfies the checks, 1 otherwise, with the reason named.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "eval-fixture.json"
REPO_ROOT = Path(__file__).resolve().parents[4]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
PLACEHOLDER_RE = re.compile(r"<[^>]+>")

HOW_TO_PRODUCE_IT = (
    "Produce it by running the procedure in "
    "write-skill/workflows/prove-triggering.md against a real skill in a live "
    "session: dispatch each prompt in both sets as a fresh subagent, runs_per_query "
    "times, record which skill fired, and write the resulting rates into the fixture "
    "with the date of the run. Confirm the skill was in the listing with its "
    "description intact before trusting a low rate - a skill the harness never picked "
    "up and a skill described badly both measure zero. Do not hand-author the measured "
    "block; a rate nobody measured is the assertion this fixture exists to replace."
)


def rel(p: Path) -> str:
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(p)


def _string_list(value, label: str, failures: list[str]) -> None:
    if not isinstance(value, list) or not value:
        failures.append(f"'{label}' must be a non-empty list of prompts")
        return
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            failures.append(f"'{label}[{i}]' must be a non-empty string")
        elif PLACEHOLDER_RE.search(item):
            failures.append(
                f"'{label}[{i}]' still carries template placeholder text "
                f"({item.strip()[:60]!r}) - the fixture was copied from "
                "evals.json.template and never filled in"
            )


def _rate(value, label: str, failures: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        failures.append(f"'{label}' must be a number between 0 and 1")
        return None
    if not 0.0 <= float(value) <= 1.0:
        failures.append(f"'{label}' is {value}, which is outside 0 to 1")
        return None
    return float(value)


def check_shape(data: dict, failures: list[str]) -> None:
    skill = data.get("skill")
    if not isinstance(skill, str) or not skill.strip():
        failures.append("'skill' must name the skill the fixture measures")
    elif PLACEHOLDER_RE.search(skill):
        failures.append("'skill' still carries template placeholder text")

    _string_list(data.get("should_trigger"), "should_trigger", failures)
    _string_list(data.get("should_not_trigger"), "should_not_trigger", failures)

    thresholds = data.get("thresholds")
    if not isinstance(thresholds, dict):
        failures.append("'thresholds' must be an object")
        return
    _rate(thresholds.get("min_trigger_rate"), "thresholds.min_trigger_rate", failures)
    _rate(
        thresholds.get("max_false_trigger_rate"),
        "thresholds.max_false_trigger_rate",
        failures,
    )


def check_measured(data: dict, failures: list[str]) -> None:
    measured = data.get("measured")
    if not isinstance(measured, dict):
        failures.append(
            "'measured' is absent or not an object. --require-measured asserts the "
            "runs happened, and an absent block means they did not."
        )
        return

    run_date = measured.get("run_date")
    if not isinstance(run_date, str) or not DATE_RE.match(run_date):
        failures.append(
            "'measured.run_date' must be the YYYY-MM-DD the runs were dispatched. "
            "A rate with no date attached cannot be told apart from one carried "
            "forward from an older description."
        )

    runs = measured.get("runs_per_query")
    if isinstance(runs, bool) or not isinstance(runs, int) or runs < 1:
        failures.append(
            "'measured.runs_per_query' must be the number of dispatches per prompt "
            "that actually ran. A rate with no run count is not a measurement."
        )

    trigger = _rate(measured.get("trigger_rate"), "measured.trigger_rate", failures)
    false_trigger = _rate(
        measured.get("false_trigger_rate"), "measured.false_trigger_rate", failures
    )

    substitutes = measured.get("substitutes")
    if not isinstance(substitutes, list) or any(
        not isinstance(s, str) for s in substitutes
    ):
        failures.append(
            "'measured.substitutes' must be a list naming every skill that fired "
            "instead, empty when none did. The substitute names the collision, which "
            "is worth more than the miss."
        )

    thresholds = data.get("thresholds")
    if not isinstance(thresholds, dict):
        return
    floor = thresholds.get("min_trigger_rate")
    ceiling = thresholds.get("max_false_trigger_rate")
    if trigger is not None and isinstance(floor, (int, float)):
        if trigger < float(floor):
            failures.append(
                f"measured trigger rate {trigger} is below the fixture's own floor "
                f"{floor}: the description is missing the words a user types"
            )
    if false_trigger is not None and isinstance(ceiling, (int, float)):
        if false_trigger > float(ceiling):
            failures.append(
                f"measured false-trigger rate {false_trigger} is above the fixture's "
                f"own ceiling {ceiling}: the description captures work belonging "
                "elsewhere, and the exclusion belongs in the description itself"
            )


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    require_measured = "--require-measured" in sys.argv[1:]

    print("# check_eval_fixture - a measured triggering fixture exists and is well-formed")
    print(f"  fixture: {rel(FIXTURE)}")
    print(f"  require-measured: {'yes' if require_measured else 'no'}")
    print()

    raw = FIXTURE.read_text(encoding="utf-8", errors="replace") if FIXTURE.is_file() else ""

    if not raw.strip():
        absent = "no triggering fixture" if not FIXTURE.is_file() else "empty fixture"
        if require_measured:
            print(f"ERROR: {absent} at {rel(FIXTURE)}.", file=sys.stderr)
            print(HOW_TO_PRODUCE_IT, file=sys.stderr)
            return 1
        print(f"NOTICE: {absent} at {rel(FIXTURE)} - nothing is measured yet.")
        print(f"  {HOW_TO_PRODUCE_IT}")
        print()
        print("check_eval_fixture: no fixture to check (not an error without --require-measured).")
        return 0

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {rel(FIXTURE)} does not parse as JSON - {exc}", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print(f"ERROR: {rel(FIXTURE)} must hold a JSON object.", file=sys.stderr)
        return 1

    failures: list[str] = []
    check_shape(data, failures)
    if require_measured:
        check_measured(data, failures)

    if failures:
        print(f"ERROR: {rel(FIXTURE)} does not satisfy the check.", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print("", file=sys.stderr)
        print(HOW_TO_PRODUCE_IT, file=sys.stderr)
        return 1

    print("check_eval_fixture: clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
