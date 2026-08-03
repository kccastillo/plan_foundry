#!/usr/bin/env python3
"""
test_gitattributes_pin.py - tests for the consumer-repo LF pin helper.

Covers the three properties the FOUNDRYREQ actually depends on: the pin lands
in a repo that has no .gitattributes at all, it is append-only against one that
does, and it is idempotent so repeated syncs never accumulate duplicates.
"""

import importlib.util
import pathlib
import sys
import tempfile

SHARED = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "gitattributes_pin", SHARED / "gitattributes_pin.py"
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

ensure_gitattributes_pin = _mod.ensure_gitattributes_pin
check_gitattributes_pin = _mod.check_gitattributes_pin
REQUIRED = _mod.REQUIRED_GITATTRIBUTES_PINS


def test_creates_file_when_absent():
    """A consumer repo with no .gitattributes gets one carrying both pins."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        assert check_gitattributes_pin(root) == [p for p, _ in REQUIRED]

        status, added = ensure_gitattributes_pin(root)
        assert status == "PASS", status
        assert len(added) == 2, added

        text = (root / ".gitattributes").read_text(encoding="utf-8")
        assert "*.sh" in text
        assert ".claude/hooks/**" in text
        assert "eol=lf" in text
        assert check_gitattributes_pin(root) == []


def test_appends_without_clobbering():
    """Existing consumer content survives byte-for-byte; only pins are appended."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        original = "# consumer's own policy\n*.png binary\n*.md text\n"
        (root / ".gitattributes").write_text(original, encoding="utf-8")

        status, added = ensure_gitattributes_pin(root)
        assert status == "PASS", status

        text = (root / ".gitattributes").read_text(encoding="utf-8")
        assert text.startswith(original), "consumer content must be preserved verbatim"
        assert "*.png binary" in text
        assert check_gitattributes_pin(root) == []


def test_idempotent_across_repeated_syncs():
    """A second call is a no-op - repeated syncs must not accumulate duplicates."""
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ensure_gitattributes_pin(root)
        first = (root / ".gitattributes").read_text(encoding="utf-8")

        status, added = ensure_gitattributes_pin(root)
        assert status == "SKIPPED", status
        assert added == []
        assert (root / ".gitattributes").read_text(encoding="utf-8") == first

        assert first.count("*.sh") == 1
        assert first.count(".claude/hooks/**") == 1


def test_consumer_pin_for_same_pattern_is_left_alone():
    """
    A consumer who already pinned a pattern keeps their value, whatever it is.

    The helper ensures coverage, not agreement - silently rewriting a consumer's
    declared attribute would be exactly the clobbering the AH2 settings merge
    was written to avoid.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        (root / ".gitattributes").write_text("*.sh text eol=crlf\n", encoding="utf-8")

        status, added = ensure_gitattributes_pin(root)
        assert status == "PASS", status
        assert added == [line for pattern, line in REQUIRED if pattern == ".claude/hooks/**"]

        text = (root / ".gitattributes").read_text(encoding="utf-8")
        assert "*.sh text eol=crlf" in text, "consumer's own *.sh pin must survive"
        assert text.count("*.sh") == 1, "must not add a competing *.sh rule"


def test_written_file_uses_lf_endings():
    """
    The pin file itself must be written with LF.

    Writing the line-ending policy with CRLF on a Windows install would be an
    unusually pointed failure.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        ensure_gitattributes_pin(root)
        raw = (root / ".gitattributes").read_bytes()
        assert b"\r" not in raw, "the .gitattributes pin must be written LF-only"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  [ok] {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  [FAIL] {name}: {exc}", file=sys.stderr)
    if failures:
        print(f"ERROR: {failures} test(s) failed", file=sys.stderr)
        sys.exit(1)
    print("all gitattributes_pin tests passed")
