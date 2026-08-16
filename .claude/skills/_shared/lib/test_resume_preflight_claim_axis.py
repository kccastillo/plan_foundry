"""
test_resume_preflight_claim_axis.py - unit tests for the claim-drift axis
added to check_resume_drift() by PLAN-AL1 (closing FOUNDRYREQ-horse-chestnut-
brickhouse-20260805-1701).

Deliberately a separate file from test_resume_preflight.py (per that file's
own precedent of not being edited by this PLAN) so the pre-existing suite's
carefully ordered mock sequences are never touched.

Coverage:
  1. No `expected_claim_checks` passed -> claim_states == {}, existing
     fetch-failure behaviour (drift False, notes has 'skipped') unaffected.
  2. Fetch-failure path (git unavailable) with a stale claim -> claim_states
     reflects stale=True and top-level drift=True with a claim-specific
     summary line - this is the early-return branch PLAN-AL1's sufficiency
     audit forced onto the claim axis (Context D6/D8: claim checking has no
     git dependency, so it must not be skipped when git fetch fails).
  3. Fetch-failure path with only a passing claim -> drift stays False from
     the claim axis.

Run: python -m pytest .claude/skills/_shared/lib/test_resume_preflight_claim_axis.py -q
"""

import pathlib
import sys
from unittest.mock import MagicMock, patch

_HERE = pathlib.Path(__file__).resolve().parent
_PARENT = _HERE.parent  # .claude/skills/_shared/
sys.path.insert(0, str(_PARENT))

from resume_preflight import check_resume_drift  # noqa: E402


def _completed(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


def _fetch_fail():
    return _completed(returncode=1, stdout="", stderr="fetch failed: no remote")


def test_no_expected_claim_checks_is_a_no_op(tmp_path):
    """1: omitting expected_claim_checks behaves exactly like before this PLAN."""
    with patch("resume_preflight.subprocess.run", return_value=_fetch_fail()):
        result = check_resume_drift(str(tmp_path))
    assert result["claim_states"] == {}
    assert result["drift"] is False
    assert any("skipped" in n for n in result["notes"])


def test_fetch_failure_path_stale_claim_drifts(tmp_path):
    """2: git unavailable (early-return branch) + a stale claim still fires drift."""

    def _side_effect(args, **kwargs):
        if isinstance(args, str):
            # This is claim_carry.run_claim_checks's shell=True call.
            return _completed(returncode=1, stdout="", stderr="claim no longer holds")
        # Any git/gh call - force the fetch-failure early-return branch.
        return _fetch_fail()

    with patch("resume_preflight.subprocess.run", side_effect=_side_effect):
        result = check_resume_drift(
            str(tmp_path),
            expected_claim_checks={
                "CLAIM-stale-thing": {"nickname": "stale-thing", "check": "some-check-command"}
            },
        )
    assert result["claim_states"]["CLAIM-stale-thing"]["checked"] is True
    assert result["claim_states"]["CLAIM-stale-thing"]["stale"] is True
    assert result["drift"] is True
    assert "CLAIM-stale-thing" in result["summary"]


def test_fetch_failure_path_passing_claim_no_drift(tmp_path):
    """3: git unavailable + a currently-passing claim -> claim axis contributes no drift."""

    def _side_effect(args, **kwargs):
        if isinstance(args, str):
            return _completed(returncode=0, stdout="", stderr="")
        return _fetch_fail()

    with patch("resume_preflight.subprocess.run", side_effect=_side_effect):
        result = check_resume_drift(
            str(tmp_path),
            expected_claim_checks={
                "CLAIM-fine-thing": {"nickname": "fine-thing", "check": "some-check-command"}
            },
        )
    assert result["claim_states"]["CLAIM-fine-thing"]["checked"] is True
    assert result["claim_states"]["CLAIM-fine-thing"]["stale"] is False
    assert result["drift"] is False
