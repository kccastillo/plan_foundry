"""
test_substrate_fidelity.py — pytest tests for the substrate-fidelity lint module.

8 tests covering the scenarios specified in PLAN-AB4 Step 7.
All tests use synthetic fixtures (tempfile.TemporaryDirectory + synthetic
substrate files) — no live repo files are read.

Run with:  python -m pytest plugins/plan-foundry-core/skills/audit-haiku-safe/lib/test_substrate_fidelity.py
"""

import os
import textwrap
import tempfile

import pytest

from substrate_fidelity import lint_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(dir_path: str, name: str, content: str) -> str:
    """Write a file in dir_path and return its absolute path."""
    path = os.path.join(dir_path, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    return path


def _make_plan(tmp_dir: str, substrate_files_decl: str, steps_body: str, plan_name: str = 'PLAN.md') -> str:
    """
    Write a minimal PLAN markdown file and return its path.

    substrate_files_decl: YAML snippet for the substrate_files field, e.g.
        "substrate_files: []"   or   "substrate_files:\n  - path/to/schema.py"

    Implementation note: substrate_files_decl may contain multi-line content
    where the embedded list items have zero leading whitespace. Cannot use
    textwrap.dedent + f-string interpolation around it — common-indent
    detection would mangle the leading-whitespace on every other line.
    Build the frontmatter with explicit string-join instead.
    """
    fm_lines = [
        "---",
        "schema_version: 2",
        'title: "Test plan"',
        "type: plan",
        "status: ready",
        substrate_files_decl,
        "---",
    ]
    frontmatter = "\n".join(fm_lines) + "\n"

    body_lines = [
        "",
        "## Objective",
        "Test objective.",
        "",
        "## Steps",
        steps_body,
        "",
        "## Verification",
        "- [ ] placeholder",
        "      `verify: true`",
        "",
    ]
    body = "\n".join(body_lines)

    return _write_file(tmp_dir, plan_name, frontmatter + body)


# ---------------------------------------------------------------------------
# Test 1 — Clean spec: PLAN with substrate_files, all referenced columns exist
# ---------------------------------------------------------------------------

def test_clean_spec_no_findings():
    """PLAN references columns that exist in the declared schema → 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = _write_file(tmp, 'schema.py', textwrap.dedent("""\
            # models
            class EventLog:
                id = Column(Integer)
                body = Column(Text)
                kind = Column(String)
        """))

        plan_path = _make_plan(
            tmp,
            substrate_files_decl=f'substrate_files:\n  - {schema_path}',
            steps_body='1. Query `SELECT event_log.body FROM event_log;`'
        )

        findings = lint_plan(plan_path)
        errors = [f for f in findings if f['level'] == 'error']
        assert errors == [], f"Expected 0 error findings, got: {errors}"


# ---------------------------------------------------------------------------
# Test 2 — Hallucinated column: Steps reference non_existent_column
# ---------------------------------------------------------------------------

def test_hallucinated_column_returns_error():
    """PLAN references non_existent_column → 1 SFV001 error finding."""
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = _write_file(tmp, 'schema.py', textwrap.dedent("""\
            class EventLog:
                id = Column(Integer)
                body = Column(Text)
        """))

        plan_path = _make_plan(
            tmp,
            substrate_files_decl=f'substrate_files:\n  - {schema_path}',
            steps_body='1. Query `SELECT event_log.non_existent_column FROM event_log;`'
        )

        findings = lint_plan(plan_path)
        sfv001 = [f for f in findings if f['code'] == 'SFV001']
        assert len(sfv001) >= 1, f"Expected at least 1 SFV001 finding, got: {findings}"
        assert 'non_existent_column' in sfv001[0]['message']


# ---------------------------------------------------------------------------
# Test 3 — Hallucinated enum value
# ---------------------------------------------------------------------------

def test_hallucinated_enum_value_returns_error():
    """PLAN references kind='not_a_real_enum_value' not in enums.py → 1 SFV001 error."""
    with tempfile.TemporaryDirectory() as tmp:
        enums_path = _write_file(tmp, 'enums.py', textwrap.dedent("""\
            from enum import Enum
            class EventKind(Enum):
                info = "info"
                warning = "warning"
                error = "error"
        """))

        plan_path = _make_plan(
            tmp,
            substrate_files_decl=f'substrate_files:\n  - {enums_path}',
            steps_body='1. Insert a row with kind="not_a_real_enum_value"'
        )

        findings = lint_plan(plan_path)
        sfv001 = [f for f in findings if f['code'] == 'SFV001']
        assert len(sfv001) >= 1, f"Expected at least 1 SFV001 finding, got: {findings}"
        assert 'not_a_real_enum_value' in sfv001[0]['message']


# ---------------------------------------------------------------------------
# Test 4 — Heuristic detection: no substrate_files but Steps have substrate grammar
# ---------------------------------------------------------------------------

def test_heuristic_detection_warn_when_no_substrate_declared():
    """PLAN with substrate_files: [] and SQL+import signals → 1 SFV003 warning."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(
            tmp,
            substrate_files_decl='substrate_files: []',
            steps_body=textwrap.dedent("""\
                1. Run `SELECT event_log.body FROM event_log;`
                2. Import: `from app.enums import EventKind`
            """)
        )

        findings = lint_plan(plan_path)
        sfv003 = [f for f in findings if f['code'] == 'SFV003']
        assert len(sfv003) == 1, f"Expected exactly 1 SFV003 warning, got: {findings}"
        assert sfv003[0]['level'] == 'warning'


# ---------------------------------------------------------------------------
# Test 5 — No substrate: PLAN with empty substrate_files and no substrate grammar
# ---------------------------------------------------------------------------

def test_no_substrate_no_signals_returns_zero_findings():
    """PLAN with substrate_files: [] and no SQL/import/enum signals → 0 findings."""
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = _make_plan(
            tmp,
            substrate_files_decl='substrate_files: []',
            steps_body='1. Write the README file.\n2. Run the lint script.'
        )

        findings = lint_plan(plan_path)
        assert findings == [], f"Expected 0 findings, got: {findings}"


# ---------------------------------------------------------------------------
# Test 6 — Multiple substrate files: entity matches in second file → no finding
# ---------------------------------------------------------------------------

def test_entity_in_second_substrate_file_no_finding():
    """Entity is absent from schema.py but present in models.py → 0 SFV001 errors."""
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = _write_file(tmp, 'schema.py', textwrap.dedent("""\
            class EventLog:
                id = Column(Integer)
        """))
        models_path = _write_file(tmp, 'models.py', textwrap.dedent("""\
            class EventLog:
                body = Column(Text)
                description = Column(Text)
        """))

        plan_path = _make_plan(
            tmp,
            substrate_files_decl=f'substrate_files:\n  - {schema_path}\n  - {models_path}',
            steps_body='1. Query `SELECT event_log.description FROM event_log;`'
        )

        findings = lint_plan(plan_path)
        sfv001 = [f for f in findings if f['code'] == 'SFV001']
        assert sfv001 == [], f"Expected 0 SFV001 findings (entity in second file), got: {sfv001}"


# ---------------------------------------------------------------------------
# Test 7 — Public-API-surface scope: _-prefixed private attribute → SFV002 error
# ---------------------------------------------------------------------------

def test_private_attribute_returns_sfv002():
    """Steps reference s._tools (private attribute) → 1 SFV002 error finding."""
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = _write_file(tmp, 'schema.py', '# empty schema\n')

        plan_path = _make_plan(
            tmp,
            substrate_files_decl=f'substrate_files:\n  - {schema_path}',
            steps_body='1. Verify the tool registry via `len(s._tools)` to count registered tools.'
        )

        findings = lint_plan(plan_path)
        sfv002 = [f for f in findings if f['code'] == 'SFV002']
        assert len(sfv002) >= 1, f"Expected at least 1 SFV002 finding, got: {findings}"
        assert '_tools' in sfv002[0]['message']
        assert sfv002[0]['level'] == 'error'


# ---------------------------------------------------------------------------
# Test 8 — Integration: mixed clean + hallucinated entities → one finding per hallucination
# ---------------------------------------------------------------------------

def test_integration_mixed_entities():
    """
    PLAN with:
      - real_column (exists in schema) → no finding
      - fake_column (absent) → SFV001
      - kind="ghost_status" (absent from enums) → SFV001
      - obj._internal (private attr) → SFV002
    Expect: exactly 3 findings, no false positives on real_column.
    """
    with tempfile.TemporaryDirectory() as tmp:
        schema_path = _write_file(tmp, 'schema.py', textwrap.dedent("""\
            class Session:
                id = Column(Integer)
                real_column = Column(Text)
        """))
        enums_path = _write_file(tmp, 'enums.py', textwrap.dedent("""\
            from enum import Enum
            class SessionKind(Enum):
                active = "active"
                closed = "closed"
        """))

        plan_path = _make_plan(
            tmp,
            substrate_files_decl=f'substrate_files:\n  - {schema_path}\n  - {enums_path}',
            steps_body=textwrap.dedent("""\
                1. Read session.real_column from the database.
                2. Also read session.fake_column which doesn't exist.
                3. Insert with kind="ghost_status" (not a real enum value).
                4. Verify via obj._internal attribute.
            """)
        )

        findings = lint_plan(plan_path)

        sfv001 = [f for f in findings if f['code'] == 'SFV001']
        sfv002 = [f for f in findings if f['code'] == 'SFV002']

        # Expect fake_column and ghost_status as SFV001
        sfv001_msgs = ' '.join(f['message'] for f in sfv001)
        assert 'fake_column' in sfv001_msgs, f"fake_column not flagged. findings: {findings}"
        assert 'ghost_status' in sfv001_msgs, f"ghost_status not flagged. findings: {findings}"

        # Expect _internal as SFV002
        assert len(sfv002) >= 1, f"Expected SFV002 for _internal, got: {findings}"
        assert '_internal' in sfv002[0]['message']

        # real_column must NOT be flagged
        for f in sfv001:
            assert 'real_column' not in f['message'], f"real_column was falsely flagged: {f}"
