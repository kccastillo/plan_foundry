"""
substrate_fidelity.py - Substrate-fidelity lint for audit-haiku-safe.

Exposes a single public function:

    lint_plan(plan_path, substrate_files=None) -> list[dict]

Each returned dict is a finding with fields:
    code       str   SFV001 | SFV002 | SFV003
    level      str   "error" | "warning"
    category   str   "substrate-fidelity"
    location   str   step number or "frontmatter"
    message    str   human-readable description
    suggested_fix str (optional)

Findings:
  SFV001 - Named entity in Steps not found in any declared substrate file.
  SFV002 - Private (_-prefixed) attribute used in Steps.
  SFV003 - Substrate-grammar constructs detected but substrate_files not declared.

Design constraints (per PLAN-AB4):
  - Pure filesystem reads via open() - no subprocess, no shell.
  - Uses tempfile-friendly paths: substrate_files may be a list of real or temp paths.
  - errors='replace' on all file reads (repo may contain non-UTF-8 bytes in test fixtures).
"""

from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Patterns for substrate-grammar detection
# ---------------------------------------------------------------------------

# SQL column refs: word.word (table.column) - excludes common false positives
# like URL paths and version strings.
_SQL_COL_RE = re.compile(r'\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b')

# Python imports: `from <module> import <symbol[, symbol]>`
_PY_IMPORT_RE = re.compile(r'from\s+(\S+)\s+import\s+([^\n]+)')

# Enum string literals: pattern like kind="value" or status="value"
# Also catches EventKind.VALUE or similar enum member refs
_ENUM_LITERAL_RE = re.compile(
    r'(?:kind|status|scope|type|category|role)\s*=\s*["\']([^"\']+)["\']'
)

# Private attribute: _identifier accessed via dot notation
_PRIVATE_ATTR_RE = re.compile(r'\._([a-z][a-z0-9_]*)\b')

# Stdlib module names to skip for import checks (non-exhaustive but covers common ones)
_STDLIB_MODULES = frozenset({
    'os', 'sys', 'io', 're', 'json', 'csv', 'math', 'time', 'datetime',
    'pathlib', 'typing', 'collections', 'itertools', 'functools', 'operator',
    'string', 'textwrap', 'logging', 'warnings', 'copy', 'abc', 'enum',
    'dataclasses', 'contextlib', 'inspect', 'types', 'weakref', 'gc',
    'threading', 'multiprocessing', 'subprocess', 'socket', 'struct',
    'hashlib', 'hmac', 'secrets', 'random', 'statistics', 'decimal',
    'fractions', 'tempfile', 'shutil', 'glob', 'fnmatch', 'stat', 'pickle',
    'shelve', 'sqlite3', 'zipfile', 'tarfile', 'gzip', 'bz2', 'lzma',
    'unittest', 'doctest', 'pdb', 'profile', 'timeit', 'traceback',
    'tracemalloc', 'platform', 'signal', 'errno', 'ctypes', 'xml', 'html',
    'http', 'urllib', 'email', 'mailbox', 'mimetypes', 'base64', 'binascii',
    'quopri', 'uu', 'codecs', 'unicodedata', 'readline', 'rlcompleter',
    'ast', 'dis', 'compileall', 'py_compile', 'importlib', 'pkgutil',
    'builtins', '__future__', 'concurrent', 'asyncio', 'queue', 'sched',
    '_thread', 'pprint', 'reprlib', 'numbers', 'array', 'bisect', 'heapq',
    'token', 'tokenize', 'keyword', 'parser', 'symbol', 'cProfile',
})

# SQL keyword signals for heuristic detection
_SQL_SIGNAL_RE = re.compile(
    r'\b(CREATE\s+TABLE|INSERT\s+INTO|SELECT\b|ALTER\s+TABLE|UPDATE\s+\w|DELETE\s+FROM)\b',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_text(path: str) -> str:
    """Read a file with errors='replace' to handle non-UTF-8 bytes."""
    with open(path, encoding='utf-8', errors='replace') as fh:
        return fh.read()


def _extract_steps_section(plan_text: str) -> str:
    """Return the text of the ## Steps section, or empty string if absent."""
    match = re.search(r'^##\s+Steps\s*\n(.*?)(?=^##\s|\Z)', plan_text, re.MULTILINE | re.DOTALL)
    if match:
        return match.group(1)
    return ''


def _extract_frontmatter_field(plan_text: str, field: str) -> str:
    """Return raw value of a frontmatter field (between --- delimiters) or empty string."""
    fm_match = re.match(r'^---\n(.*?)\n---', plan_text, re.DOTALL)
    if not fm_match:
        return ''
    fm_body = fm_match.group(1)
    pattern = re.compile(r'^' + re.escape(field) + r'\s*:\s*(.+)$', re.MULTILINE)
    m = pattern.search(fm_body)
    return m.group(1).strip() if m else ''


def _parse_substrate_files_from_frontmatter(plan_text: str) -> list[str]:
    """Parse substrate_files list from PLAN frontmatter (simple YAML list parse)."""
    fm_match = re.match(r'^---\n(.*?)\n---', plan_text, re.DOTALL)
    if not fm_match:
        return []
    fm_body = fm_match.group(1)
    # Match substrate_files block
    block_match = re.search(r'^substrate_files\s*:\s*(.*?)(?=^\S|\Z)', fm_body, re.MULTILINE | re.DOTALL)
    if not block_match:
        return []
    raw = block_match.group(1).strip()
    if not raw or raw in ('[]', ''):
        return []
    # Inline list: [a, b, c]
    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1]
        items = [x.strip().strip('"\'') for x in inner.split(',') if x.strip()]
        return [i for i in items if i]
    # Block list:
    #   - path/a
    #   - path/b
    items = []
    for line in raw.splitlines():
        m = re.match(r'^\s*-\s+(.+)', line)
        if m:
            items.append(m.group(1).strip().strip('"\''))
    return items


def _grep_entity_in_files(entity: str, file_paths: list[str]) -> bool:
    """Return True if entity appears (as a literal substring) in any of the given files."""
    for path in file_paths:
        if not os.path.isfile(path):
            continue
        text = _read_text(path)
        if entity in text:
            return True
    return False


def _make_finding(code: str, level: str, location: str, message: str, suggested_fix: str = '') -> dict[str, Any]:
    finding: dict[str, Any] = {
        'code': code,
        'level': level,
        'category': 'substrate-fidelity',
        'location': location,
        'message': message,
    }
    if suggested_fix:
        finding['suggested_fix'] = suggested_fix
    return finding


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------

def lint_plan(plan_path: str, substrate_files: list[str] | None = None) -> list[dict]:
    """
    Lint a PLAN file for substrate-fidelity violations.

    Parameters
    ----------
    plan_path:
        Path to the PLAN markdown file.
    substrate_files:
        Override list of substrate file paths. If None, the function reads
        `substrate_files` from the PLAN frontmatter. Pass an explicit list
        (including empty list []) to override frontmatter.

    Returns
    -------
    List of finding dicts (may be empty for a clean plan).
    """
    plan_text = _read_text(plan_path)
    steps_text = _extract_steps_section(plan_text)

    # Resolve substrate_files
    if substrate_files is None:
        declared = _parse_substrate_files_from_frontmatter(plan_text)
    else:
        declared = list(substrate_files)

    findings: list[dict] = []

    if declared:
        # --- Path A: declared substrate - full entity extraction + grep ---
        # 1. SQL column refs
        for m in _SQL_COL_RE.finditer(steps_text):
            table, col = m.group(1), m.group(2)
            entity = col  # check the column name against substrate
            if not _grep_entity_in_files(entity, declared):
                findings.append(_make_finding(
                    code='SFV001',
                    level='error',
                    location='Steps',
                    message=f"substrate-fidelity-violation: column '{entity}' (from '{table}.{entity}') referenced in Steps but not found in any declared substrate file ({declared})",
                    suggested_fix="Verify the column name against the substrate file and correct the PLAN Steps."
                ))

        # 2. Python imports (non-stdlib)
        for m in _PY_IMPORT_RE.finditer(steps_text):
            module = m.group(1).split('.')[0]
            if module in _STDLIB_MODULES:
                continue
            symbols_raw = m.group(2)
            symbols = [s.strip().rstrip(',') for s in symbols_raw.split(',') if s.strip()]
            for sym in symbols:
                sym = sym.strip()
                if not sym:
                    continue
                if not _grep_entity_in_files(sym, declared):
                    findings.append(_make_finding(
                        code='SFV001',
                        level='error',
                        location='Steps',
                        message=f"substrate-fidelity-violation: import symbol '{sym}' (from '{module}') referenced in Steps but not found in any declared substrate file ({declared})",
                        suggested_fix="Verify the symbol exists in the substrate module and correct the import."
                    ))

        # 3. Enum string-literal values
        for m in _ENUM_LITERAL_RE.finditer(steps_text):
            value = m.group(1)
            if not _grep_entity_in_files(value, declared):
                findings.append(_make_finding(
                    code='SFV001',
                    level='error',
                    location='Steps',
                    message=f"substrate-fidelity-violation: enum/constrained-field value '{value}' referenced in Steps but not found in any declared substrate file ({declared})",
                    suggested_fix="Verify the enum value against the substrate file and correct the PLAN Steps."
                ))

        # 4. Private attribute access (_-prefixed)
        for m in _PRIVATE_ATTR_RE.finditer(steps_text):
            attr = '_' + m.group(1)
            findings.append(_make_finding(
                code='SFV002',
                level='error',
                location='Steps',
                message=f"substrate-fidelity-violation: '{attr}' is a private attribute (underscore-prefixed). The spec MUST author against documented public API surface only.",
                suggested_fix="Check the framework's documented public API for the equivalent public method/attribute."
            ))

    else:
        # --- Path B: no declared substrate - heuristic detection ---
        has_sql_signal = bool(_SQL_SIGNAL_RE.search(steps_text))
        has_import_signal = bool(_PY_IMPORT_RE.search(steps_text))
        has_enum_signal = bool(_ENUM_LITERAL_RE.search(steps_text))
        has_col_signal = bool(_SQL_COL_RE.search(steps_text))

        if has_sql_signal or has_import_signal or has_enum_signal or has_col_signal:
            findings.append(_make_finding(
                code='SFV003',
                level='warning',
                location='frontmatter',
                message=(
                    "substrate-files-undeclared: heuristic detected substrate-grammar constructs in Steps "
                    "(e.g. SQL column refs, Python imports, enum literals) but PLAN frontmatter has no "
                    "substrate_files declaration. Declare the substrate files or acknowledge that no "
                    "verification is needed."
                ),
                suggested_fix=(
                    "Add substrate_files: [path/to/schema.py, ...] to PLAN frontmatter, or acknowledge "
                    "this finding if no substrate ground-truth applies."
                )
            ))

    return findings
