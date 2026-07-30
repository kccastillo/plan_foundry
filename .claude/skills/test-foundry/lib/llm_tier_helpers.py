"""
llm_tier_helpers.py - prep/capture helpers for LLM-tier scenarios.

This module is a **prep/capture helper, not a driver**. The SKILL.md workflow body
in `skills/test-foundry/workflows/run-tests.md` is the driver: it iterates LLM
scenarios, calls `prep_scenario` here, then issues the parent-session `Skill(...)`
invocations enumerated in the scenario spec, then calls `capture_assertions` here.

The helpers in this module NEVER re-enter Claude reasoning themselves - they only
prepare on-disk fixtures and inspect on-disk state.

Public API:
    prep_scenario(spec_path: str | pathlib.Path) -> dict
    capture_assertions(scenario_id: str, expected: list[dict]) -> dict
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import time


def _read_frontmatter(path: pathlib.Path) -> dict[str, str]:
    """Tolerant inline YAML parse for top-level string/scalar frontmatter keys.

    Supports nested-key lookup via dotted form (handled by caller). Returns a flat
    dict mapping top-level keys to their raw scalar value (string). Nested keys
    are exposed via dotted form (`audit_state.last_outcome`).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return {}
    m = re.match(r"^---\n(.*?\n)---\n", text, re.DOTALL)
    if not m:
        return {}
    body = m.group(1)
    out: dict[str, str] = {}
    parent_stack: list[tuple[int, str]] = []  # (indent, key)
    for raw in body.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        # Compute indent.
        indent = len(raw) - len(raw.lstrip(" "))
        # Drop deeper parents.
        while parent_stack and parent_stack[-1][0] >= indent:
            parent_stack.pop()
        line = raw.strip()
        km = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        path_key = ".".join(p[1] for p in parent_stack + [(indent, key)])
        if val == "":
            # Could be a nested mapping; track on stack.
            parent_stack.append((indent, key))
        else:
            # Strip surrounding quotes if present.
            if (val.startswith('"') and val.endswith('"')) or (
                val.startswith("'") and val.endswith("'")
            ):
                val = val[1:-1]
            out[path_key] = val
    return out


def prep_scenario(spec_path) -> dict:
    """Read a scenario spec and prepare its fixtures on disk.

    The actual fixture content is described in the spec body in markdown. This
    helper does a best-effort prep: it parses the spec for a `## Fixture
    preparation` section and creates a temp dir whose path is returned. The
    SKILL workflow body is expected to read the spec for any additional setup
    instructions that can only be performed by Claude (e.g. seeding a specific
    minimal PLAN body).

    Returns:
        {
            "scenario_id": "<filename stem>",
            "spec_path": "<absolute spec path>",
            "tmpdir": "<absolute path to a fresh empty temp dir>",
            "spec_body": "<full markdown body of the spec>",
        }
    """
    spec_path = pathlib.Path(spec_path).resolve()
    if not spec_path.is_file():
        raise FileNotFoundError(f"scenario spec not found: {spec_path}")
    scenario_id = spec_path.stem
    spec_body = spec_path.read_text(encoding="utf-8", errors="replace")
    tmpdir = pathlib.Path(tempfile.mkdtemp(prefix=f"pft-{scenario_id}-"))
    return {
        "scenario_id": scenario_id,
        "spec_path": str(spec_path),
        "tmpdir": str(tmpdir),
        "spec_body": spec_body,
    }


def _check_path_exists(path: str) -> tuple[bool, str]:
    p = pathlib.Path(path)
    return (p.exists(), f"exists={p.exists()} path={path}")


def _check_path_absent(path: str) -> tuple[bool, str]:
    p = pathlib.Path(path)
    return (not p.exists(), f"exists={p.exists()} path={path}")


def _check_regular_file_nonzero(path: str) -> tuple[bool, str]:
    p = pathlib.Path(path)
    if not p.is_file():
        return (False, f"not a regular file: {path}")
    size = p.stat().st_size
    return (size > 0, f"size={size} path={path}")


def _check_frontmatter_key(path: str, key: str, expected: str) -> tuple[bool, str]:
    p = pathlib.Path(path)
    fm = _read_frontmatter(p)
    actual = fm.get(key)
    ok = actual == expected
    return (ok, f"key={key} expected={expected!r} actual={actual!r}")


def _check_git_log_substring(cwd: str, command: str, substring: str) -> tuple[bool, str]:
    # We only support the documented `git log --oneline -1` form to avoid arbitrary
    # shell invocation; anything else is rejected with a clear diagnostic.
    if not command.strip().startswith("git log"):
        return (False, f"unsupported command for git_log_substring: {command!r}")
    args = command.strip().split()
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    except Exception as exc:
        return (False, f"subprocess error: {exc}")
    out = proc.stdout or ""
    ok = substring in out
    return (ok, f"substring={substring!r} present={ok} stdout_head={out[:200]!r}")


def _check_string_equality(lhs: str, rhs: str) -> tuple[bool, str]:
    ok = lhs == rhs
    return (ok, f"byte_identical={ok} lhs_len={len(lhs)} rhs_len={len(rhs)}")


def _check_file_substring(path: str, substring: str) -> tuple[bool, str]:
    p = pathlib.Path(path)
    if not p.is_file():
        return (False, f"not a regular file: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    ok = substring in text
    return (ok, f"substring={substring!r} present={ok} path={path}")


def _check_file_regex(path: str, pattern: str) -> tuple[bool, str]:
    p = pathlib.Path(path)
    if not p.is_file():
        return (False, f"not a regular file: {path}")
    text = p.read_text(encoding="utf-8", errors="replace")
    try:
        # DOTALL so a `.*` across a table row spanning cells still matches.
        ok = re.search(pattern, text, re.DOTALL) is not None
    except re.error as exc:
        return (False, f"bad regex {pattern!r}: {exc}")
    return (ok, f"pattern={pattern!r} matched={ok} path={path}")


def capture_assertions(scenario_id: str, expected: list) -> dict:
    """Run the mechanical assertions enumerated for a scenario.

    `expected` is a list of dicts following the schemas documented in the
    `scenarios/llm/*.md` spec bodies. Recognised assertion kinds:

    - `path_exists`            - {"kind": "path_exists", "path": ...}
    - `path_absent`            - {"kind": "path_absent", "path": ...}
    - `regular_file_nonzero`   - {"kind": "regular_file_nonzero", "path": ...}
    - frontmatter check        - {"frontmatter_key": ..., "expected": ..., "path": ...}
    - `git_log_substring`      - {"kind": "git_log_substring", "cwd": ..., "command": ..., "expected_substring": ...}
    - `string_equality`        - {"kind": "string_equality", "lhs": ..., "rhs": ...}
    - `file_substring`         - {"kind": "file_substring", "path": ..., "expected_substring": ...}
    - `file_regex`             - {"kind": "file_regex", "path": ..., "expected_regex": ...}

    Returns:
        {
            "scenario": scenario_id,
            "status": "pass" | "fail",
            "symptoms": [str],
            "diagnostics": str,
            "duration_ms": int,
        }
    """
    started = time.monotonic()
    symptoms: list[str] = []
    diagnostics_lines: list[str] = []

    for i, item in enumerate(expected, start=1):
        kind = item.get("kind")
        # frontmatter check has its own shape (no `kind`).
        if "frontmatter_key" in item:
            ok, diag = _check_frontmatter_key(
                item["path"], item["frontmatter_key"], item["expected"]
            )
        elif kind == "path_exists":
            ok, diag = _check_path_exists(item["path"])
        elif kind == "path_absent":
            ok, diag = _check_path_absent(item["path"])
        elif kind == "regular_file_nonzero":
            ok, diag = _check_regular_file_nonzero(item["path"])
        elif kind == "git_log_substring":
            ok, diag = _check_git_log_substring(
                item["cwd"], item["command"], item["expected_substring"]
            )
        elif kind == "string_equality":
            ok, diag = _check_string_equality(item.get("lhs", ""), item.get("rhs", ""))
        elif kind == "file_substring":
            ok, diag = _check_file_substring(item["path"], item["expected_substring"])
        elif kind == "file_regex":
            ok, diag = _check_file_regex(item["path"], item["expected_regex"])
        else:
            ok, diag = False, f"unknown assertion kind: {kind!r}"
        diagnostics_lines.append(f"[{i}] {'PASS' if ok else 'FAIL'} {diag}")
        if not ok:
            symptoms.append(f"assertion {i} failed: {diag}")

    status = "fail" if symptoms else "pass"
    return {
        "scenario": scenario_id,
        "status": status,
        "symptoms": symptoms,
        "diagnostics": "\n".join(diagnostics_lines),
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
