"""
validate_artefact_filename.py — Shared filename validator for plan_foundry datetime-stamped artefacts.

Classifies a HANDOFF, FOUNDRYREQ, or OBSERVATION basename into one of three classes:

  conforming       — matches a current new-grammar pattern exactly
  legacy_permitted — a recognised legacy form (valid on read; never a new write target)
  malformed        — clearly attempts the new grammar but is broken

Any other basename (e.g. INDEX.md, PLAN-AH0_…, ADVICE-018_…) is returned as
(None, "not-subject") to signal the file is outside this validator's scope.

Usage:
    from validate_artefact_filename import classify_artefact_filename
    result, reason = classify_artefact_filename("HANDOFF-20260712-1430-restructure-mandate.md")
    # result: "conforming", reason: "HANDOFF new-grammar"

Public API:
    classify_artefact_filename(basename: str) -> tuple[str | None, str]
        Returns (class_str, reason_str) where class_str is one of:
            "conforming", "legacy_permitted", "malformed", or None (not-subject).

Reads: this module performs no file I/O. All logic is pure / dependency-free.
Per PLAN-AH0 D5 — Hard-Validation.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Grammar patterns
# ---------------------------------------------------------------------------

# YYYYMMDD-hhmm component: 8 digits, hyphen, 4 digits (no colon)
_DATETIME_PART = r"\d{8}-\d{4}"

# Lowercase-kebab slug: one or more lowercase-kebab words
_SLUG_PART = r"[a-z0-9]+(?:-[a-z0-9]+)*"

# HANDOFF new grammar: HANDOFF-YYYYMMDD-hhmm-<slug>.md
_HANDOFF_NEW = re.compile(
    r"^HANDOFF-(?P<datetime>\d{8}-\d{4})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$"
)

# FOUNDRYREQ new grammar: FOUNDRYREQ-<origin>-YYYYMMDD-hhmm-<slug>.md
# <origin> is one or more kebab-segments; datetime follows immediately after origin.
# We require at least one origin segment before the datetime.
_FOUNDRYREQ_NEW = re.compile(
    r"^FOUNDRYREQ-(?P<origin>[A-Za-z0-9](?:[A-Za-z0-9_-]*[A-Za-z0-9])?)"
    r"-(?P<datetime>\d{8}-\d{4})-(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.md$"
)

# HANDOFF-NEXT-SESSION.md — reserved unscoped default (legacy read/retire-only)
_HANDOFF_NEXT_SESSION = re.compile(r"^HANDOFF-NEXT-SESSION\.md$", re.IGNORECASE)

# HANDOFF-<scope>.md — old single-scope grammar (one non-datetime segment)
# A datetime-looking segment would be 8+ digits, so we exclude those.
# The scope is anything that does NOT look like a datetime (YYYYMMDD-hhmm starts with 8 digits).
_HANDOFF_OLD_SCOPE = re.compile(
    r"^HANDOFF-(?!(?:\d{8}-\d{4}))(?P<scope>[A-Za-z0-9][A-Za-z0-9_-]*)\.md$"
)

# HANDOFF-<scope>-<YYYYMMDDHHMI>.md — retire-destination timestamp form
# The retire timestamp is 12 digits (YYYYMMDDHHMI), appended after the scope segment.
# Encountered under Retired/ when rehydrate-handoff retires a file.
# The scope may itself contain hyphens (e.g. 'dungeon-jaquays'), so we use a greedy
# match for the scope-plus-timestamp body and require the last segment to be 12 digits.
_HANDOFF_RETIRE_DEST = re.compile(
    r"^HANDOFF-(?P<scope>.+)-(?P<ts>\d{12})\.md$"
)

# OBSERVATION-<datetime>-<slug>.md — legacy observation artefact (prior skill output)
_OBSERVATION = re.compile(
    r"^OBSERVATION-\d{8}-\d{4}-[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
)

# Colon-containing HANDOFF — definitely malformed (Windows-unsafe, violates grammar)
_HANDOFF_WITH_COLON = re.compile(r"^HANDOFF-.*:.*\.md$")

# FOUNDRYREQ with colon
_FOUNDRYREQ_WITH_COLON = re.compile(r"^FOUNDRYREQ-.*:.*\.md$")

# Any HANDOFF prefix at all (used to gate further malformed checks)
_HANDOFF_PREFIX = re.compile(r"^HANDOFF-", re.IGNORECASE)

# Any FOUNDRYREQ prefix at all
_FOUNDRYREQ_PREFIX = re.compile(r"^FOUNDRYREQ-", re.IGNORECASE)

# HANDOFF that starts with a datetime but is malformed (missing slug or datetime wrong)
# Matches: HANDOFF-<8digits>-<4digits>[-.md or end] — any HANDOFF that attempts a datetime
_HANDOFF_ATTEMPTS_DATETIME = re.compile(r"^HANDOFF-\d{8}-\d{4}", re.IGNORECASE)

# FOUNDRYREQ that attempts a datetime in some position
_FOUNDRYREQ_ATTEMPTS_DATETIME = re.compile(r"^FOUNDRYREQ-.*\d{8}-\d{4}", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def classify_artefact_filename(basename: str) -> tuple[str | None, str]:
    """Classify a filename basename into (class, reason).

    Returns:
        ("conforming", reason)       — valid new-grammar file
        ("legacy_permitted", reason) — recognised legacy form
        ("malformed", reason)        — attempts new grammar but is broken
        (None, "not-subject")        — outside this validator's scope

    The basename should be the filename only (no directory path).
    Case: HANDOFF and FOUNDRYREQ prefixes are matched case-insensitively for
    legacy_permitted detection; new-grammar conforming checks require exact case.
    """
    # ---- HANDOFF family ----
    if _HANDOFF_PREFIX.match(basename):
        # 1. Colon present → malformed regardless of anything else
        if _HANDOFF_WITH_COLON.match(basename):
            return ("malformed", "HANDOFF contains colon in datetime component — Windows-unsafe")

        # 2. Reserved default
        if _HANDOFF_NEXT_SESSION.match(basename):
            return ("legacy_permitted", "HANDOFF-NEXT-SESSION reserved default")

        # 3. Retire-destination timestamp form (12-digit suffix)
        if _HANDOFF_RETIRE_DEST.match(basename):
            return ("legacy_permitted", "HANDOFF retire-destination timestamp form")

        # 4. New grammar (datetime + slug) — conforming
        if _HANDOFF_NEW.match(basename):
            return ("conforming", "HANDOFF new-grammar (datetime + slug)")

        # 5. Old single-scope grammar — legacy permitted
        if _HANDOFF_OLD_SCOPE.match(basename):
            return ("legacy_permitted", "HANDOFF old-grammar (scope only, no datetime)")

        # 6. Attempts a datetime pattern but did not pass the new-grammar check → malformed
        if _HANDOFF_ATTEMPTS_DATETIME.match(basename):
            return ("malformed", "HANDOFF attempts datetime grammar but is missing slug or has wrong format")

        # 7. Any other HANDOFF- prefix — malformed (unrecognised form)
        return ("malformed", "HANDOFF with unrecognised format")

    # ---- FOUNDRYREQ family ----
    if _FOUNDRYREQ_PREFIX.match(basename):
        # 1. Colon present → malformed
        if _FOUNDRYREQ_WITH_COLON.match(basename):
            return ("malformed", "FOUNDRYREQ contains colon in datetime component — Windows-unsafe")

        # 2. New grammar — conforming
        if _FOUNDRYREQ_NEW.match(basename):
            return ("conforming", "FOUNDRYREQ new-grammar (origin + datetime + slug)")

        # 3. Attempts a datetime but did not pass → malformed
        if _FOUNDRYREQ_ATTEMPTS_DATETIME.match(basename):
            return ("malformed", "FOUNDRYREQ attempts datetime grammar but is missing slug or origin, or has wrong format")

        # 4. Any other FOUNDRYREQ prefix — malformed
        return ("malformed", "FOUNDRYREQ with unrecognised format")

    # ---- OBSERVATION (legacy) ----
    if basename.upper().startswith("OBSERVATION-"):
        if _OBSERVATION.match(basename):
            return ("legacy_permitted", "OBSERVATION legacy form (prior skill output)")
        # An OBSERVATION- prefix that doesn't match the known grammar
        # could be malformed, but the old skill had no strict grammar enforcement.
        # Treat as legacy_permitted to avoid false positives on existing files.
        return ("legacy_permitted", "OBSERVATION with non-standard format (treated as legacy)")

    # ---- Not in scope ----
    return (None, "not-subject")
