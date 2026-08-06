"""
test_claim_carry.py - unit tests for claim_carry.py (PLAN-AL1).

Run: python -m pytest .claude/skills/_shared/lib/test_claim_carry.py -q
"""

import pathlib
import sys

_PARENT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PARENT))

from claim_carry import (  # noqa: E402
    ESCALATION_THRESHOLD,
    diff_dropped,
    next_baseline,
    parse_claims,
    run_claim_checks,
)


# ---------------------------------------------------------------------------
# parse_claims
# ---------------------------------------------------------------------------

def test_parse_claims_with_check_line():
    text = """## Constraints & do-nots

CLAIM-audit-exit-code: the audit script exits 1 on defects.
check: "python -c \\"import sys; sys.exit(1)\\""

## Where things live
"""
    claims = parse_claims(text)
    assert "CLAIM-audit-exit-code" in claims
    entry = claims["CLAIM-audit-exit-code"]
    assert entry["nickname"] == "audit-exit-code"
    assert "exits 1" in entry["prose"]
    assert entry["check"] is not None
    assert "sys.exit(1)" in entry["check"]


def test_parse_claims_without_check_line():
    text = """## Blocking decisions

CLAIM-scope-collision: AA2 and AA3 overlap, unreconciled.
"""
    claims = parse_claims(text)
    assert claims["CLAIM-scope-collision"]["check"] is None


def test_parse_claims_ignores_id_outside_named_sections():
    text = """## Session roadmap

CLAIM-not-a-real-claim: this id is outside the two governed sections.

## Constraints & do-nots

Nothing here.
"""
    claims = parse_claims(text)
    assert "CLAIM-not-a-real-claim" not in claims


def test_parse_claims_empty_text():
    assert parse_claims("") == {}
    assert parse_claims(None) == {}


# ---------------------------------------------------------------------------
# diff_dropped
# ---------------------------------------------------------------------------

def test_diff_dropped_missing_without_removal_note():
    prior = {"CLAIM-foo": {"nickname": "foo", "prose": "x", "check": None}}
    successor_text = "## Constraints & do-nots\n\nNo mention of foo here.\n"
    assert diff_dropped(prior, successor_text) == ["CLAIM-foo"]


def test_diff_dropped_present_is_not_dropped():
    prior = {"CLAIM-foo": {"nickname": "foo", "prose": "x", "check": None}}
    successor_text = "## Constraints & do-nots\n\nCLAIM-foo: still true.\n"
    assert diff_dropped(prior, successor_text) == []


def test_diff_dropped_removal_note_clears_it():
    prior = {"CLAIM-foo": {"nickname": "foo", "prose": "x", "check": None}}
    successor_text = "## Constraints & do-nots\n\nCLAIM-foo removed - resolved upstream.\n"
    assert diff_dropped(prior, successor_text) == []


def test_diff_dropped_empty_prior():
    assert diff_dropped({}, "anything") == []
    assert diff_dropped(None, "anything") == []


# ---------------------------------------------------------------------------
# run_claim_checks
# ---------------------------------------------------------------------------

def test_run_claim_checks_passing_command_not_stale(tmp_path):
    claims = {
        "CLAIM-pass": {"nickname": "pass", "prose": "x", "check": "python -c \"import sys; sys.exit(0)\""}
    }
    results = run_claim_checks(claims, tmp_path)
    assert results["CLAIM-pass"]["checked"] is True
    assert results["CLAIM-pass"]["stale"] is False


def test_run_claim_checks_failing_command_is_stale(tmp_path):
    claims = {
        "CLAIM-fail": {"nickname": "fail", "prose": "x", "check": "python -c \"import sys; sys.exit(1)\""}
    }
    results = run_claim_checks(claims, tmp_path)
    assert results["CLAIM-fail"]["checked"] is True
    assert results["CLAIM-fail"]["stale"] is True


def test_run_claim_checks_command_not_found_is_stale(tmp_path):
    # A shell-resolved "command not found" (e.g. a script path that no longer
    # exists) is a NONZERO EXIT from the shell itself, not a Python-level
    # subprocess exception - and is legitimate staleness evidence (this is
    # exactly the report's "dropped-claim direction": a claim naming a script
    # path that has never existed under the current layout).
    claims = {
        "CLAIM-broken": {
            "nickname": "broken",
            "prose": "x",
            "check": "this-executable-does-not-exist-anywhere --flag",
        }
    }
    results = run_claim_checks(claims, tmp_path)
    assert results["CLAIM-broken"]["checked"] is True
    assert results["CLAIM-broken"]["stale"] is True


def test_run_claim_checks_bad_cwd_fails_open():
    # A genuine infrastructure failure (subprocess itself cannot start - here,
    # a repo_root that does not exist) IS fail-open: checked False, never stale.
    claims = {
        "CLAIM-nocwd": {"nickname": "nocwd", "prose": "x", "check": "python -c \"import sys; sys.exit(0)\""}
    }
    results = run_claim_checks(claims, "Z:/this-path-does-not-exist-anywhere-12345")
    assert results["CLAIM-nocwd"]["checked"] is False
    assert results["CLAIM-nocwd"]["stale"] is False


def test_run_claim_checks_freeform_claim_not_reverified(tmp_path):
    claims = {"CLAIM-freeform": {"nickname": "freeform", "prose": "x", "check": None}}
    results = run_claim_checks(claims, tmp_path)
    assert results["CLAIM-freeform"]["checked"] is False
    assert results["CLAIM-freeform"]["stale"] is False
    assert "D2" in results["CLAIM-freeform"]["reason"]


def test_run_claim_checks_empty_claims(tmp_path):
    assert run_claim_checks({}, tmp_path) == {}
    assert run_claim_checks(None, tmp_path) == {}


# ---------------------------------------------------------------------------
# next_baseline
# ---------------------------------------------------------------------------

def test_next_baseline_increments_carried_count():
    prior = {"CLAIM-foo": {"nickname": "foo", "check": "", "carried_count": 1}}
    current = {"CLAIM-foo": {"nickname": "foo", "prose": "x", "check": None}}
    baseline, escalated = next_baseline(prior, current)
    assert baseline["CLAIM-foo"]["carried_count"] == 2
    assert escalated == []


def test_next_baseline_new_id_starts_at_one():
    baseline, escalated = next_baseline({}, {"CLAIM-new": {"nickname": "new", "prose": "x", "check": None}})
    assert baseline["CLAIM-new"]["carried_count"] == 1
    assert escalated == []


def test_next_baseline_drops_absent_id():
    prior = {"CLAIM-gone": {"nickname": "gone", "check": "", "carried_count": 2}}
    baseline, escalated = next_baseline(prior, {})
    assert "CLAIM-gone" not in baseline
    assert escalated == []


def test_next_baseline_escalates_at_threshold():
    prior = {
        "CLAIM-repeat": {
            "nickname": "repeat",
            "check": "",
            "carried_count": ESCALATION_THRESHOLD - 1,
        }
    }
    current = {"CLAIM-repeat": {"nickname": "repeat", "prose": "x", "check": None}}
    baseline, escalated = next_baseline(prior, current)
    assert baseline["CLAIM-repeat"]["carried_count"] == ESCALATION_THRESHOLD
    assert escalated == ["CLAIM-repeat"]
