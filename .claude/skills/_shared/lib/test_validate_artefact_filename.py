"""
test_validate_artefact_filename.py - Unit tests for classify_artefact_filename().

Covers all classification classes:
  - conforming: HANDOFF new-grammar, FOUNDRYREQ new-grammar
  - legacy_permitted: HANDOFF-NEXT-SESSION.md, HANDOFF-<scope>.md,
                      HANDOFF-<scope>-<YYYYMMDDHHMI>.md (retire-dest), OBSERVATION-*
  - malformed: missing datetime, missing slug, colon present
  - not-subject: filenames outside the validator's scope

Per PLAN-AH0 Step 8.

Run: python3 -m pytest .claude/skills/_shared/lib/test_validate_artefact_filename.py -q
"""

from __future__ import annotations

import pathlib
import sys

# Make the shared module importable when running from any working directory
_SHARED = pathlib.Path(__file__).resolve().parent.parent  # .claude/skills/_shared/
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from validate_artefact_filename import classify_artefact_filename  # noqa: E402


# ---------------------------------------------------------------------------
# Conforming - new-grammar HANDOFF
# ---------------------------------------------------------------------------

class TestConformingHandoff:
    def test_basic_handoff_new_grammar(self):
        result, reason = classify_artefact_filename("HANDOFF-20260712-1430-restructure-mandate.md")
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"

    def test_handoff_new_grammar_single_slug_word(self):
        result, reason = classify_artefact_filename("HANDOFF-20260724-0900-planning.md")
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"

    def test_handoff_new_grammar_multi_word_slug(self):
        result, reason = classify_artefact_filename("HANDOFF-20261231-2359-end-of-year-wrap-up.md")
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"

    def test_handoff_new_grammar_slug_with_digits(self):
        result, reason = classify_artefact_filename("HANDOFF-20260101-0001-plan-ah0-execution.md")
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Conforming - new-grammar FOUNDRYREQ
# ---------------------------------------------------------------------------

class TestConformingFoundryReq:
    def test_basic_foundryreq_new_grammar(self):
        result, reason = classify_artefact_filename(
            "FOUNDRYREQ-my-project-20260712-1402-handoff-filenames-date-slug.md"
        )
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"

    def test_foundryreq_single_origin_segment(self):
        result, reason = classify_artefact_filename(
            "FOUNDRYREQ-acme-20260724-0930-retire-bug.md"
        )
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"

    def test_foundryreq_origin_with_mixed_case_normalised(self):
        # The origin in the filename is already normalised at write time;
        # the validator accepts uppercase origin chars per the regex
        result, reason = classify_artefact_filename(
            "FOUNDRYREQ-MyProject-20260712-1430-feature-request.md"
        )
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"

    def test_foundryreq_multi_segment_origin(self):
        result, reason = classify_artefact_filename(
            "FOUNDRYREQ-plan-foundry-dev-20260724-1200-slugs-required.md"
        )
        assert result == "conforming", f"expected conforming, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Legacy permitted - HANDOFF-NEXT-SESSION.md
# ---------------------------------------------------------------------------

class TestLegacyHandoffNextSession:
    def test_handoff_next_session_exact(self):
        result, reason = classify_artefact_filename("HANDOFF-NEXT-SESSION.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"

    def test_handoff_next_session_case_insensitive(self):
        result, reason = classify_artefact_filename("handoff-next-session.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Legacy permitted - HANDOFF-<scope>.md (old grammar)
# ---------------------------------------------------------------------------

class TestLegacyHandoffOldScope:
    def test_handoff_old_scope_simple(self):
        result, reason = classify_artefact_filename("HANDOFF-dungeon-jaquays.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"

    def test_handoff_old_scope_single_word(self):
        result, reason = classify_artefact_filename("HANDOFF-restructure.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Legacy permitted - HANDOFF-<scope>-<YYYYMMDDHHMI>.md (retire destination)
# ---------------------------------------------------------------------------

class TestLegacyHandoffRetireDest:
    def test_handoff_retire_dest_next_session(self):
        result, reason = classify_artefact_filename("HANDOFF-NEXT-SESSION-202607230541.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"

    def test_handoff_retire_dest_old_scope(self):
        result, reason = classify_artefact_filename("HANDOFF-dungeon-jaquays-202607231300.md")
        # 'dungeon-jaquays' is the scope; 202607231300 is the 12-digit timestamp
        # Note: this might match the retire-dest pattern
        # scope = 'dungeon-jaquays', ts = '202607231300'
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"

    def test_handoff_retire_dest_simple_scope(self):
        result, reason = classify_artefact_filename("HANDOFF-main-202607140042.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Legacy permitted - OBSERVATION-*
# ---------------------------------------------------------------------------

class TestLegacyObservation:
    def test_observation_standard(self):
        result, reason = classify_artefact_filename(
            "OBSERVATION-20260712-1402-handoff-filenames-date-slug.md"
        )
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"

    def test_observation_non_standard_still_legacy(self):
        # Non-standard OBSERVATION format treated as legacy to avoid false positives
        result, reason = classify_artefact_filename("OBSERVATION-miscellaneous-note.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Malformed - HANDOFF attempts datetime grammar but is broken
# ---------------------------------------------------------------------------

class TestMalformedHandoff:
    def test_handoff_missing_slug(self):
        # Has datetime but no slug after it
        result, reason = classify_artefact_filename("HANDOFF-20260712-1430.md")
        assert result == "malformed", f"expected malformed, got {result!r}: {reason}"

    def test_handoff_colon_in_datetime(self):
        # Colon in time component - Windows-unsafe
        result, reason = classify_artefact_filename("HANDOFF-20260712-14:30-restructure.md")
        assert result == "malformed", f"expected malformed, got {result!r}: {reason}"

    def test_handoff_six_digit_prefix_is_legacy_scope(self):
        # A first segment of 6 digits is NOT an 8-digit datetime, so under forward-only
        # coexistence this is a valid old-grammar HANDOFF-<scope>.md (scope="202607-1430-some-slug"),
        # classified legacy_permitted - the CI scanner must not false-positive-red a legitimate
        # legacy filename. The malformed set per PLAN-AH0 Step 2/8 is {missing datetime, missing
        # slug, colon}; a wrong-length datetime is not a required malformed variant. The write-time
        # post-condition (which composes from a known-good datetime) is the enforcement point for
        # genuinely new handoffs. (PLAN-AH0 outcome-verifying reconciliation, 2026-07-24.)
        result, reason = classify_artefact_filename("HANDOFF-202607-1430-some-slug.md")
        assert result == "legacy_permitted", f"expected legacy_permitted, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Malformed - FOUNDRYREQ attempts grammar but is broken
# ---------------------------------------------------------------------------

class TestMalformedFoundryReq:
    def test_foundryreq_missing_slug(self):
        # Has origin and datetime but no slug
        result, reason = classify_artefact_filename("FOUNDRYREQ-acme-20260712-1430.md")
        assert result == "malformed", f"expected malformed, got {result!r}: {reason}"

    def test_foundryreq_colon_in_datetime(self):
        result, reason = classify_artefact_filename(
            "FOUNDRYREQ-acme-20260712-14:30-some-slug.md"
        )
        assert result == "malformed", f"expected malformed, got {result!r}: {reason}"

    def test_foundryreq_missing_origin_and_slug(self):
        # Only has the datetime, no origin before it, no slug after
        result, reason = classify_artefact_filename("FOUNDRYREQ-20260712-1430.md")
        assert result == "malformed", f"expected malformed, got {result!r}: {reason}"


# ---------------------------------------------------------------------------
# Not-subject - filenames outside the validator's scope
# ---------------------------------------------------------------------------

class TestNotSubject:
    def test_plan_file(self):
        result, reason = classify_artefact_filename("PLAN-AH0_artefact-naming-hardening.md")
        assert result is None, f"expected None (not-subject), got {result!r}: {reason}"

    def test_advice_file(self):
        result, reason = classify_artefact_filename("ADVICE-018_content-contract.md")
        assert result is None, f"expected None (not-subject), got {result!r}: {reason}"

    def test_research_file(self):
        result, reason = classify_artefact_filename("RESEARCH-001_observability-survey.md")
        assert result is None, f"expected None (not-subject), got {result!r}: {reason}"

    def test_index_file(self):
        result, reason = classify_artefact_filename("INDEX.md")
        assert result is None, f"expected None (not-subject), got {result!r}: {reason}"

    def test_log_file(self):
        result, reason = classify_artefact_filename("202607010000_LOG_202607.md")
        assert result is None, f"expected None (not-subject), got {result!r}: {reason}"
