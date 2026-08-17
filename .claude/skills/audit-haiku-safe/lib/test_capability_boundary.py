"""
test_capability_boundary.py - pytest tests for the executor-capability-boundary
lint module (PLAN-AK1).

Run with:
    python -m pytest .claude/skills/audit-haiku-safe/lib/test_capability_boundary.py

All tests use a synthetic repo scaffolded under tmp_path (monkeypatch.chdir),
never the live tree - the module resolves .claude/agents and .claude/skills
relative to the working directory.

Note on PLAN construction: synthetic PLANs with multi-line frontmatter use
explicit "\n".join(lines) rather than textwrap.dedent + f-string interpolation,
matching the sibling test modules' documented convention.
"""

import os

import pytest

from capability_boundary import lint_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(dir_path: str, name: str, content: str) -> str:
    """Write a file in dir_path (creating it if needed) and return its path."""
    os.makedirs(dir_path, exist_ok=True)
    path = os.path.join(dir_path, name)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(content)
    return path


def _make_plan(
    tmp_dir,
    step_lines,
    assigned_to='',
    acknowledgements=None,
    ack_form='block',
    plan_name='PLAN.md',
):
    """
    Write a synthetic PLAN. step_lines are inserted verbatim (joined by a
    blank line) under '## Steps' - callers supply their own numbering (or
    none, for the numbered-line-fallback fixtures).
    """
    fm_lines = [
        "---",
        "schema_version: 2",
        'title: "Test plan"',
        "type: plan",
        "status: ready",
    ]
    if assigned_to:
        fm_lines.append(f"assigned_to: {assigned_to}")
    if acknowledgements is not None:
        if ack_form == 'inline':
            fm_lines.append("audit_acknowledgements: [" + ", ".join(acknowledgements) + "]")
        else:
            fm_lines.append("audit_acknowledgements:")
            for code in acknowledgements:
                fm_lines.append(f"- {code}")
    fm_lines.append("---")
    frontmatter = "\n".join(fm_lines) + "\n"

    steps_body = "\n\n".join(step_lines)

    body = "\n".join([
        "",
        "## Objective",
        "Test objective.",
        "",
        "## Steps",
        steps_body,
        "",
        "## Verification",
        "- [ ] Verification item 1",
        "      `acceptance: python -m pytest tests/`",
        "",
    ])
    return _write_file(str(tmp_dir), plan_name, frontmatter + body)


def _make_repo(
    tmp_dir,
    skills=('execute-plan',),
    stub_skills=('execute-plan', 'retire', 'write-input', 'plan-pipeline', 'ideate'),
    agents=('plan-executor', 'plan-executor-sonnet', 'plan-executor-opus'),
    bash_denied=True,
):
    """
    Scaffold .claude/agents/<name>.md (skills: + disallowedTools:) and a
    .claude/skills/<name>/SKILL.md stub for every name in stub_skills.

    `skills` (the agent's preload list) and `stub_skills` (the directories
    scaffolded on disk) are deliberately different parameters: the prose
    patterns' existence filter reads the directory, the boundary rule reads
    the declaration. Call this more than once against the same tmp_dir (e.g.
    once per agent with a different `agents`/`skills` pair) to build a repo
    where different agents declare different preload lists.
    """
    agents_dir = os.path.join(str(tmp_dir), '.claude', 'agents')
    skills_dir = os.path.join(str(tmp_dir), '.claude', 'skills')
    os.makedirs(agents_dir, exist_ok=True)
    os.makedirs(skills_dir, exist_ok=True)

    skills_line = '[' + ', '.join(skills) + ']'
    disallowed_line = '[Bash, WebFetch, WebSearch]' if bash_denied else '[WebFetch, WebSearch]'

    for name in agents:
        content = "\n".join([
            "---",
            f"name: {name}",
            "model: sonnet",
            f"disallowedTools: {disallowed_line}",
            f"skills: {skills_line}",
            'description: "stub"',
            "---",
            "",
            f"# {name}",
            "",
        ])
        _write_file(agents_dir, f'{name}.md', content)

    for name in stub_skills:
        skill_dir = os.path.join(skills_dir, name)
        _write_file(skill_dir, 'SKILL.md', f"---\nname: {name}\n---\n\n# {name}\n")


# ---------------------------------------------------------------------------
# Clean / permitted cases
# ---------------------------------------------------------------------------

def test_clean_plan_no_findings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ["1. Read the file and edit it in place."])
    assert lint_plan(path) == []


def test_preloaded_skill_is_not_flagged(tmp_path, monkeypatch):
    """The D8 rule from the permitted side: a preloaded skill is never flagged."""
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ['1. Invoke Skill("execute-plan") on the target file.'])
    assert lint_plan(path) == []


# ---------------------------------------------------------------------------
# True positives
# ---------------------------------------------------------------------------

def test_executor_scoped_retire_is_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ['1. Invoke Skill("retire", ...) on the target file.'])
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['code'] == 'EBV001'
    assert findings[0]['level'] == 'error'
    assert 'Step 1' in findings[0]['location']
    assert 'plan-executor' in findings[0]['message']


def test_unlisted_skill_outside_the_four_names_is_flagged(tmp_path, monkeypatch):
    """
    The AJ8 regression: PLAN-AJ8's Steps directed the executor to run
    write-skill and audit-skills end to end - neither name is among the four
    executor-capability-boundary.md historically recorded, so a hard-coded
    name list would have passed both. The derived rule (D8) catches this
    because neither name is in plan-executor's preloaded skills, independent
    of any maintained list.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, stub_skills=('execute-plan', 'write-skill'))
    path = _make_plan(tmp_path, ['1. Invoke Skill("write-skill") to scaffold the new skill.'])
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['code'] == 'EBV001'


def test_orchestrator_scoped_retire_is_not_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. The orchestrator invokes Skill("retire", ...) on the target file after this PLAN completes.'],
    )
    assert lint_plan(path) == []


def test_preload_list_governs_not_a_name_list(tmp_path, monkeypatch):
    """
    Pins D8 against a regression to hard-coded names: change the agent's
    declared preload list and the check's verdict changes with it.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, skills=('execute-plan', 'retire'))
    path = _make_plan(tmp_path, ['1. Invoke Skill("retire") on the target file.'])
    assert lint_plan(path) == []


# ---------------------------------------------------------------------------
# D9 - tier resolution and unresolvable declaration
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "assigned_to,expected_agent",
    [
        ('', 'plan-executor'),
        ('haiku', 'plan-executor'),
        ('sonnet', 'plan-executor-sonnet'),
        ('opus', 'plan-executor-opus'),
    ],
)
def test_tier_resolution_selects_the_declared_agent(tmp_path, monkeypatch, assigned_to, expected_agent):
    monkeypatch.chdir(tmp_path)
    all_agents = ('plan-executor', 'plan-executor-sonnet', 'plan-executor-opus')
    # Only the expected agent declares 'retire' in its preload list.
    other_agents = tuple(a for a in all_agents if a != expected_agent)
    _make_repo(tmp_path, skills=('execute-plan', 'retire'), agents=(expected_agent,))
    _make_repo(tmp_path, skills=('execute-plan',), agents=other_agents)

    path = _make_plan(
        tmp_path,
        ['1. Invoke Skill("retire") on the target file.'],
        assigned_to=assigned_to,
    )
    assert lint_plan(path) == []


def test_unrecognised_assigned_to_falls_back_to_default_agent(tmp_path, monkeypatch):
    """The untested assigned_to fallback the input flagged."""
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Invoke Skill("retire") on the target file.'],
        assigned_to='gemini',
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert 'plan-executor' in findings[0]['message']


def test_missing_agent_file_warns_and_does_not_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join(str(tmp_path), '.claude', 'skills'), exist_ok=True)
    path = _make_plan(tmp_path, ['1. Invoke Skill("retire") on the target file.'])
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['code'] == 'EBV002'
    assert findings[0]['level'] == 'warning'
    assert 'EBV001' not in [f['code'] for f in findings]


def test_ebv002_is_independently_acknowledgeable(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    os.makedirs(os.path.join(str(tmp_path), '.claude', 'skills'), exist_ok=True)
    path = _make_plan(tmp_path, ['1. Invoke Skill("retire") on the target file.'])
    assert lint_plan(path, ack_codes=['EBV002']) == []


# ---------------------------------------------------------------------------
# D3 / D7 - acknowledgement suppression
# ---------------------------------------------------------------------------

def test_acknowledgement_suppresses_finding(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ['1. Invoke Skill("retire", ...) on the target file.'])
    assert lint_plan(path, ack_codes=['EBV001']) == []


@pytest.mark.parametrize("ack_form", ['block', 'inline'])
def test_frontmatter_acknowledgement_suppresses_finding(tmp_path, monkeypatch, ack_form):
    """
    D7 - the documented one-line invocation in 4e.4 passes no ack_codes, so
    this is what proves the escape hatch is reachable as documented.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Invoke Skill("retire", ...) on the target file.'],
        acknowledgements=['EBV001'],
        ack_form=ack_form,
    )
    assert lint_plan(path) == []


def test_explicit_empty_ack_codes_overrides_frontmatter(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Invoke Skill("retire", ...) on the target file.'],
        acknowledgements=['EBV001'],
    )
    findings = lint_plan(path, ack_codes=[])
    assert len(findings) == 1
    assert findings[0]['code'] == 'EBV001'


# ---------------------------------------------------------------------------
# Structural note, raw shell, prose patterns
# ---------------------------------------------------------------------------

def test_ideate_carries_its_structural_note(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ['1. Invoke Skill("ideate") to think this through.'])
    findings = lint_plan(path)
    assert len(findings) == 1
    assert 'no agent file' in findings[0]['message']


def test_raw_shell_invocation_is_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, bash_denied=True)
    path = _make_plan(
        tmp_path,
        ["1. Run bash -c 'python scripts/build.py' to regenerate the index."],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert 'raw bash/sh' in findings[0]['message']
    assert '<' not in findings[0]['message']


def test_raw_shell_not_flagged_when_bash_is_permitted(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, bash_denied=False)
    path = _make_plan(
        tmp_path,
        ["1. Run bash -c 'python scripts/build.py' to regenerate the index."],
    )
    assert lint_plan(path) == []


def test_prose_mention_of_a_skill_is_not_flagged(tmp_path, monkeypatch):
    """The D2 existence-plus-verb rule: a bare mention is a documentation edit."""
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ["1. Edit the retire skill's SKILL.md to add the post-condition note."],
    )
    assert lint_plan(path) == []


def test_prose_invocation_of_a_real_skill_is_flagged(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ["1. Invoke the write-input skill to record the finding."])
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['code'] == 'EBV001'


def test_forward_prose_pattern_captures_the_skill_name(tmp_path, monkeypatch):
    """
    Article-free, so _SKILL_PROSE_REVERSE_RE cannot match it. Pins the
    division of labour between the two prose patterns (Step 1): without it,
    the forward pattern could capture "the" on every phrasing and the suite
    would stay green because the reverse pattern and the existence filter
    cover for it.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ["1. Invoke write-input skill directly on the finding."])
    findings = lint_plan(path)
    assert len(findings) == 1
    assert 'write-input' in findings[0]['message']


def test_prose_match_on_a_nonexistent_skill_is_discarded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, stub_skills=('execute-plan',))
    path = _make_plan(tmp_path, ["1. Run the deploy skill to publish the artefact."])
    assert lint_plan(path) == []


# ---------------------------------------------------------------------------
# Scope of scan (D5) and location resolution
# ---------------------------------------------------------------------------

def test_fenced_block_is_skipped(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        [
            "1. Write the following literal content to a template file:\n"
            "```\nSkill(\"retire\")\n```",
        ],
    )
    assert lint_plan(path) == []


def test_verification_section_is_not_scanned(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ["1. Read the file and edit it in place."])
    with open(path, 'a', encoding='utf-8') as fh:
        fh.write('      `verify: python -c "import retire"`\n')
    assert lint_plan(path) == []


def test_location_names_the_containing_step_not_the_first(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        [
            "1. Read the target file.",
            "2. Edit the target file in place.",
            '3. Invoke Skill("retire") on the target file.',
        ],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['location'] == 'Step 3'


def test_location_falls_back_when_no_numbered_line_precedes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['This paragraph invokes Skill("retire") before any numbered Step exists.'],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['location'] == '## Steps'


def test_dotted_filename_does_not_end_the_sentence(tmp_path, monkeypatch):
    """
    Sentence-boundary regression test: under a splitter that ends a sentence
    at any full stop, the orchestrator marker and the retire-skill match land
    in different fragments and the suppression fails.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ["1. The orchestrator runs `lib/capability_boundary.py` and then invokes the retire skill."],
    )
    assert lint_plan(path) == []


# ---------------------------------------------------------------------------
# Run-versus-record discrimination (measured 2026-08-05)
#
# Each test below pins one rule against the shape that motivated it. The
# shapes are taken from a measured sweep, not invented: the
# raw heuristic fired 59 times across the PLAN corpus and was wrong 40 of the
# 46 times it was not self-acknowledged.
# ---------------------------------------------------------------------------

def test_r1_a_literal_with_no_governing_verb_is_not_an_invocation(tmp_path, monkeypatch):
    """
    `The Skill("retire") invocation pattern must work` is a sentence about a
    call, not a call. Motivating shape: PLAN-016 Step 6.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Ensure each renamed SKILL.md keeps its name field. The `Skill("retire")` '
         'invocation pattern must work.'],
    )
    assert lint_plan(path) == []


def test_r1_a_governing_preposition_counts_as_invocation(tmp_path, monkeypatch):
    """
    `record the finding via Skill("retire")` has no invocation verb but is an
    instruction. Motivating shape: PLAN-AE4 Step 4, a genuine crossing the
    verb-only form of this rule missed.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Record the outcome as an input via `Skill("retire")`.'],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['code'] == 'EBV001'


def test_r2_a_name_that_resolves_to_no_skill_is_not_flagged(tmp_path, monkeypatch):
    """
    A negative-test plant (`Skill("no-such-skill-xyz")`) cannot be a crossing.
    The two prose branches have always applied this filter; the literal branch
    did not. Motivating shape: PLAN-AI3 Step 7.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(tmp_path, ['1. Invoke `Skill("no-such-skill-xyz")` on the fixture.'])
    assert lint_plan(path) == []


def test_r3_an_authoring_verb_earlier_in_the_step_suppresses(tmp_path, monkeypatch):
    """
    A step that opens by naming the file it writes frames every mention under
    it as that file's content. Motivating shape: PLAN-AC3 Step 14 and
    PLAN-AC5 Step 7, both specifying a slash-command body.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Create the slash command at `.claude/commands/x.md`. Its body is a '
         'one-line wrapper invoking `Skill("retire")`.'],
    )
    assert lint_plan(path) == []


def test_r3_the_authoring_frame_holds_across_a_blank_line_within_one_step(tmp_path, monkeypatch):
    """
    Paragraph scope stopped at the blank line and read the sub-bullet as an
    instruction. Motivating shape: PLAN-AD5 Step 5, which specifies the body
    of an authored Python function two paragraphs below its heading.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Implement the router.\n\n   **Where:** `lib/router.py`.\n\n'
         '   **What:** for each row, dispatch `Skill("retire", ...)` with the '
         'chosen frontmatter.'],
    )
    assert lint_plan(path) == []


def test_r3_the_authoring_frame_does_not_leak_between_steps(tmp_path, monkeypatch):
    """
    The counterpart to the test above, and the reason the frame is bounded by
    the step rather than run to the top of the section. Many PLANs pack their
    numbered steps with no blank line between them; without the bound, an
    authoring verb in step 1 suppressed a genuine crossing in step 3.
    Motivating shape: PLAN-AC8 Step 3.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Write the summary into `notes.md`.\n'
         '2. Record the findings as an input via `Skill("retire")`.'],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['location'] == 'Step 2'


def test_r3_a_diff_block_suppresses_but_only_its_own_paragraph(tmp_path, monkeypatch):
    """
    A skill name inside an Edit's old_string/new_string is content moving
    between two files. The suppression is paragraph-scoped on purpose: a step
    may both edit a file and instruct an invocation, and step-scoping the diff
    rule would lose the second.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Patch the file.\n   old_string: `invoke Skill("retire")`\n'
         '   new_string: `the orchestrator retires it`\n\n'
         '   Then invoke `Skill("write-input")` on the result.'],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert "'write-input'" in findings[0]['message']


def test_an_indented_fenced_block_is_stripped(tmp_path, monkeypatch):
    """
    The fence stripper required ``` at column 0, so a fence opened under a
    numbered step - the usual place a PLAN quotes an Edit's old_string - was
    never blanked. Motivating shape: both PLAN-032 Step 4 findings.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Replace the block below.\n\n   ```\n   Invoke `Skill("retire")` with '
         'no arguments.\n   ```'],
    )
    assert lint_plan(path) == []


def test_a_prohibition_is_not_an_instruction_to_run_shell(tmp_path, monkeypatch):
    """
    A step saying the executor cannot run Bash carries the same tokens as one
    telling it to. Motivating shapes: PLAN-AF9 and PLAN-AG1.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['1. Note that the executor cannot run `bash -c` here - use Read and Edit.'],
    )
    assert lint_plan(path) == []


def test_step_heading_style_locations_are_reported_correctly(tmp_path, monkeypatch):
    """
    A PLAN numbering its steps `### Step N:` still contains ordinary `N. `
    lines in its prose. Consulting both styles let the detector lock onto one
    of those and report a plausible, wrong step number - worse than reporting
    none. Motivating shape: PLAN-AC5, reported as Step 2 for a mention that
    sits in Step 7.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path)
    path = _make_plan(
        tmp_path,
        ['### Step 1: Prepare\n\nDo the following in order:\n\n'
         '1. Read the file.\n2. Check the frontmatter.',
         '### Step 7: Finish\n\nInvoke `Skill("retire")` on the target.'],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert findings[0]['location'] == 'Step 7'


def test_raw_shell_flagged_when_script_is_invoked_without_dash_c(tmp_path, monkeypatch):
    """The `bash <script>` form, backtick-quoted, is how a Step actually reads.

    Live instance: PLAN-AL3 Step 6 said ``Run `bash scripts/ci/run-all.sh``` and
    passed this lint, then failed plan-safety by eye. The `-c` alternative did not
    match because there is no `-c`, and the `run bash` alternative did not match
    because a backtick sits between the two words.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, bash_denied=True)
    path = _make_plan(
        tmp_path,
        ["1. Run `bash scripts/ci/run-all.sh` and fix anything it reports."],
    )
    findings = lint_plan(path)
    assert len(findings) == 1
    assert 'raw bash/sh' in findings[0]['message']


def test_shebang_mention_is_not_raw_shell(tmp_path, monkeypatch):
    """A Step may describe a hook's shebang without invoking a shell."""
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, bash_denied=True)
    path = _make_plan(
        tmp_path,
        ["1. Write the hook with a `#!/usr/bin/env bash` shebang, matching pre-commit."],
    )
    assert lint_plan(path) == []


def test_shell_command_named_as_a_description_is_not_flagged(tmp_path, monkeypatch):
    """A Step may name a shell command to say what it means, not to run it.

    Live instance: PLAN-AK3 names `bash scripts/ci/run-all.sh` as this repo's
    statement of what green means. An earlier widening of the raw-shell pattern
    matched the bare invocation with no verb in front of it and reported this at
    error severity against a correct PLAN.
    """
    monkeypatch.chdir(tmp_path)
    _make_repo(tmp_path, bash_denied=True)
    path = _make_plan(
        tmp_path,
        ["1. Record that `bash scripts/ci/run-all.sh` is the repo's definition of green."],
    )
    assert lint_plan(path) == []
