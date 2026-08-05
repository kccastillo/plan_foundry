"""
platform_portability.py - Platform-portability lint for audit-haiku-safe.

Exposes a single public function:

    lint_plan(plan_path) -> list[dict]

Each returned dict is a finding with fields:
    code          str   PPV001-PPV007
    level         str   "warning"
    category      str   "platform-portability"
    location      str   description of the verify/acceptance line
    message       str   human-readable description
    suggested_fix str   portable alternative hint

Findings are emitted when a verify: or acceptance: line in the PLAN's
Verification section contains a forbidden POSIX-only pattern AND the line
carries no # platform: <posix|windows> annotation.

All findings are warn-severity (not blockers) - the CI baseline is POSIX-
compatible; the advisory surfaces for Windows consumers.

Design constraints (per PLAN-AB3):
  - Pure filesystem reads via open() - no subprocess, no shell.
  - errors='replace' on all file reads.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Forbidden patterns
# ---------------------------------------------------------------------------

# Each entry: (code, compiled_regex, one-line rationale, suggested_fix)
_FORBIDDEN_PATTERNS: list[tuple[str, re.Pattern[str], str, str]] = [
    (
        'PPV001',
        re.compile(r'/tmp/'),
        '/tmp/ - Linux-only temp path',
        'Use `python -c "import tempfile; ..."` or pytest tmp_path for portable temp files.',
    ),
    (
        'PPV002',
        re.compile(r'/dev/null'),
        '/dev/null - POSIX-only null device',
        'Suppress output with Python subprocess.DEVNULL or omit the redirect.',
    ),
    (
        'PPV003',
        re.compile(r'\bbash\s+-c\b'),
        'bash -c - explicitly invokes bash; unavailable or differently-pathed on Windows',
        'Rewrite as a Python one-liner (`python -c "..."`) or a pytest test.',
    ),
    (
        'PPV004',
        re.compile(r'\btest\s+-[a-zA-Z]\b'),
        'test -X - POSIX shell test builtin',
        'Use `python -c "import os; assert os.path.exists(...)"` or `pathlib.Path(...).exists()`.',
    ),
    (
        'PPV005',
        re.compile(r'>\s*/dev/'),
        '> /dev/ - redirect to /dev/ pseudo-device; POSIX-only',
        'Drop the redirect or use Python subprocess.DEVNULL.',
    ),
    (
        'PPV006',
        re.compile(r'2>/dev/null'),
        '2>/dev/null - POSIX stderr suppression',
        'Suppress stderr in Python with subprocess.DEVNULL, or annotate with # platform: posix.',
    ),
    (
        'PPV007',
        re.compile(r'&&'),
        '&& compound operator - works in bash but breaks PowerShell 5.1',
        'Split into separate verify: items, or annotate with # platform: posix.',
    ),
]

# Annotation pattern: trailing comment # platform: posix or # platform: windows
_PLATFORM_ANNOTATION_RE = re.compile(
    r'#\s*platform\s*:\s*(posix|windows)\s*$',
    re.IGNORECASE,
)

# Lines that start a verify/acceptance annotation (in the Verification section)
_VERIFY_LINE_RE = re.compile(r'^\s*(verify|acceptance)\s*:\s*(.+)', re.IGNORECASE)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_text(path: str) -> str:
    """Read a file with errors='replace' to handle non-UTF-8 bytes."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _extract_verification_section(plan_text: str) -> str:
    """Return the text of the ## Verification section, or empty string if absent."""
    match = re.search(
        r'^##\s+Verification\s*\n(.*?)(?=^##\s|\Z)',
        plan_text,
        re.MULTILINE | re.DOTALL,
    )
    if match:
        return match.group(1)
    return ''


def _extract_verify_lines(verification_text: str) -> list[str]:
    """
    Extract all verify: and acceptance: annotation lines from a Verification section.

    These are the shell-runnable annotations that appear (typically indented
    with backticks) below each prose checkbox. We scan every line for the
    verify:/acceptance: prefix.
    """
    lines = []
    for line in verification_text.splitlines():
        # Strip markdown backtick wrappers and leading whitespace
        stripped = line.strip().lstrip('`').rstrip('`').strip()
        m = _VERIFY_LINE_RE.match(stripped)
        if m:
            lines.append(stripped)
    return lines


def _has_platform_annotation(line: str) -> bool:
    """Return True if the line has a # platform: posix|windows annotation."""
    return bool(_PLATFORM_ANNOTATION_RE.search(line))


def _make_finding(
    code: str,
    location: str,
    message: str,
    suggested_fix: str = '',
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        'code': code,
        'level': 'warning',
        'category': 'platform-portability',
        'location': location,
        'message': message,
    }
    if suggested_fix:
        finding['suggested_fix'] = suggested_fix
    return finding


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------

def lint_plan(plan_path: str) -> list[dict]:
    """
    Lint a PLAN file for platform-portability violations in its Verification
    section.

    Parameters
    ----------
    plan_path:
        Path to the PLAN markdown file.

    Returns
    -------
    List of finding dicts (may be empty for a clean plan). Each finding has:
        code, level, category, location, message, suggested_fix.
    """
    plan_text = _read_text(plan_path)
    verification_text = _extract_verification_section(plan_text)
    verify_lines = _extract_verify_lines(verification_text)

    findings: list[dict] = []

    for line in verify_lines:
        # Skip lines with a platform annotation
        if _has_platform_annotation(line):
            continue

        # Scan for each forbidden pattern
        for code, pattern, rationale, fix in _FORBIDDEN_PATTERNS:
            if pattern.search(line):
                # Truncate location to 80 chars for readability
                truncated = line if len(line) <= 80 else line[:77] + '...'
                location = f'Verification - {truncated}'
                message = (
                    f'platform-portability-violation: {rationale} found in '
                    f'verify/acceptance line. Either rewrite to a portable form '
                    f'or annotate with # platform: <posix|windows>.'
                )
                findings.append(_make_finding(code, location, message, fix))

    return findings
