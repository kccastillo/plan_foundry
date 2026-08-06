"""
capability_boundary.py - Executor-capability-boundary lint for audit-haiku-safe.

Exposes a single public function:

    lint_plan(plan_path, ack_codes=None) -> list[dict]

Each returned dict is a finding with fields:
    code          str   EBV001 | EBV002
    level         str   "error" (EBV001) | "warning" (EBV002)
    category      str   "capability-boundary"
    location      str   "Step <n>" / "## Steps" (EBV001) or the agent path (EBV002)
    message       str   human-readable description
    suggested_fix str   hint for how to re-author the Step

Design rule (D8, PLAN-AK1): what an executor Step may not do is derived from the
dispatched agent file's own `skills:` and `disallowedTools:` declarations, not
from a maintained list of skill names. A skill absent from the resolved agent's
preload list is excluded whether or not it appears in `_shared/plan-safe.md`'s
four recorded instances - those instances are what falls out of the rule, not
the rule itself.

Design constraints (per PLAN-AK1, matching the sibling lint modules):
  - Pure filesystem reads via open() - no subprocess, no shell.
  - errors='replace' on all file reads.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Tier resolution (D9)
# ---------------------------------------------------------------------------

# Transcribed from write-plan/references/assigned_to-field.md. An unrecognised
# assigned_to value (including 'human', per D9 - a PLAN re-tiered later must
# still be checked against something) falls back to _DEFAULT_AGENT.
_TIER_TO_AGENT: dict[str, str] = {
    '': 'plan-executor',
    'haiku': 'plan-executor',
    'sonnet': 'plan-executor-sonnet',
    'opus': 'plan-executor-opus',
}
_DEFAULT_AGENT = 'plan-executor'

_AGENTS_DIR = '.claude/agents'
_SKILLS_DIR = '.claude/skills'

# The one distinct diagnostic D8 keeps: ideate has no agent file at all, so a
# derived check catches it for a different reason than the other three named
# instances (which do have agent files, just not this skill in their preload).
_STRUCTURAL_NOTES: dict[str, str] = {
    'ideate': (
        'ideate has no agent file at all and cannot be dispatched to any '
        'subagent (plan-safe.md clause (c)).'
    ),
}

# Any skill-shaped name; membership is decided in lint_plan against the
# resolved agent's preloaded skills, not against an alternation of literals.
#
# Matching the literal is not on its own evidence that the executor is being
# asked to run it - see _governed_by_invocation and the run-versus-record
# rules below. The measured sweep of 2026-08-05 found this branch's lack of a
# verb requirement to be the dominant cause of false positives: the prose
# branches below have always required an invocation verb, and this one did not.
_SKILL_CALL_RE = re.compile(r'''Skill\s*\(\s*["'`]?([A-Za-z0-9_-]+)''')

# Matches article-free invocation prose: "invoke retire skill", "run the
# write-input skill's scaffolder". Does NOT reliably capture the name in the
# article-prefixed form - the lazy quantifier lets "the" win the capture group
# in "invoke the retire skill" - which is why _SKILL_PROSE_REVERSE_RE exists.
# Do not widen this pattern to cover the article-prefixed form; the two
# patterns divide the space deliberately (D2).
_SKILL_PROSE_RE = re.compile(
    r'\b(?:invoke|invokes|call|calls|run|runs|use|uses)\b[^.\n]{0,40}?\b([a-z][a-z0-9-]{2,})\b[^.\n]{0,20}?\bskill\b',
    re.IGNORECASE,
)

# Matches "invoke the write-input skill". The leading invocation verb is
# required, not optional: without it this fires on "edit the `retire` skill's
# SKILL.md", which is a documentation edit rather than a crossing.
_SKILL_PROSE_REVERSE_RE = re.compile(
    r'\b(?:invoke|invokes|call|calls|run|runs|use|uses)\s+the\s+`?([a-z][a-z0-9-]{2,})`?\s+skill\b',
    re.IGNORECASE,
)

# Raw shell invocation. Deliberately no capture group - its alternates match
# invocation syntax rather than a named operation, so the raw-shell branch
# emits a fixed operation string rather than interpolating a match.
_RAW_SHELL_RE = re.compile(
    r'\bBash\s*\(|\b(?:bash|sh)\s+-c\b|\brun\s+(?:a\s+)?(?:bash|shell)\b',
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# D2 attribution discrimination
# ---------------------------------------------------------------------------

_NON_EXECUTOR_MARKERS: tuple[str, ...] = (
    'orchestrator',
    'parent session',
    'parent-session',
    'the parent',
    'the human',
    'the operator',
    '[human]',
)


def _has_non_executor_marker(sentence: str) -> bool:
    """
    D2 discrimination heuristic: True when `sentence` attributes the action to
    somebody other than the executor.

    Two recorded failure modes (accepted deliberately, not engineered away):
      - False negative on a compound sentence ("The executor writes the file
        and then the orchestrator invokes `retire`") - a marker anywhere in
        the sentence suppresses the whole sentence, even a genuine executor-
        scoped violation sharing it. Accepted: this degrades to the pre-D2
        status quo (H302 read-by-eye), and a false positive on correct prose
        is worse under D4's error severity.
      - Attribution on a lead line with the operation in a sub-bullet is a
        distinct, unaddressed failure mode - see D2 in the PLAN Context.
    """
    lowered = sentence.lower()
    return any(marker in lowered for marker in _NON_EXECUTOR_MARKERS)


# ---------------------------------------------------------------------------
# Run-versus-record discrimination
# ---------------------------------------------------------------------------
#
# The distinction this section draws is between a Step that tells the executor
# to *run* a skill and one that tells it to *write the skill's name down* - as
# documentation prose for another skill's SKILL.md, as a child skill's or a
# slash-command's specified body, as a test fixture or assertion string, or
# inside an Edit's old_string/new_string block.
#
# This was measured, not guessed. A sweep classified every
# EBV001 hit across the whole PLAN corpus: 38 of 46 non-acknowledged findings
# failed for this one reason, and the failure mode the design had named in
# advance (attribution on a lead line, the operation in a sub-bullet) accounted
# for 2. The residual category was the whole story.
#
# Three rules, each with its own justification, rather than a wider list of
# markers - a wider list fails the same sweep the same way:
#
#   R1  A Skill(...) literal counts only when an invocation verb governs it, or
#       when it stands at the head of its sentence as a bare imperative. The
#       two prose branches have always required an invocation verb; the call
#       branch requiring none was an inconsistency rather than a decision.
#
#   R2  A Skill(...) literal counts only when the named skill exists on disk -
#       the same existence filter the prose branches already apply. A name that
#       resolves to nothing cannot be a crossing; it is a fixture or a plant.
#
#   R3  An authoring verb appearing anywhere earlier in the sentence than the
#       mention suppresses it, and so does a containing Edit diff block. An
#       authoring verb establishes the frame for everything after it, which is
#       why "earlier in the sentence" beats "nearest to the mention": in
#       `Replace the line "Invoke Skill(x)" with ...` the nearer verb is the
#       quoted one and the governing verb is Replace.
#
# The bias is deliberate and matches _has_non_executor_marker's: a false
# negative degrades to read-by-eye, a false positive blocks a correct PLAN.

_INVOCATION_VERBS: tuple[str, ...] = (
    'invoke', 'invokes', 'invoking',
    'call', 'calls', 'calling',
    'run', 'runs', 'running',
    'use', 'uses', 'using',
    'execute', 'executes', 'executing',
    'dispatch', 'dispatches', 'dispatching',
    'fire', 'fires', 'firing',
)

# Prepositions that govern an invocation without a verb of their own:
# "record the finding via Skill(...)", "retire it with Skill(...)". Measured
# addition - a genuine crossing in PLAN-AE4 used exactly this form and the
# verb-only rule missed it.
_GOVERNING_PREPOSITIONS: tuple[str, ...] = ('via', 'with', 'through', 'by')

# Verbs whose object is content being produced rather than an action being
# performed. The (?!-) guard is load-bearing: without it `write` matches inside
# the skill names `write-plan`, `write-input` and `write-skill`, so every
# genuine instruction to run one of those would suppress itself.
_AUTHORING_VERBS: tuple[str, ...] = (
    'write', 'writes', 'writing', 'written',
    'author', 'authors', 'authoring',
    'add', 'adds', 'adding',
    'insert', 'inserts', 'inserting',
    'specify', 'specifies', 'specifying',
    'document', 'documents', 'documenting',
    'describe', 'describes', 'describing',
    'quote', 'quotes', 'quoting', 'quoted',
    'replace', 'replaces', 'replacing',
    'rename', 'renames', 'renaming',
    'append', 'appends', 'appending',
    'define', 'defines', 'defining',
    'assert', 'asserts', 'asserting',
    'grep', 'greps', 'grepping',
    'edit', 'edits', 'editing',
    'remove', 'removes', 'removing',
    'delete', 'deletes', 'deleting',
    'create', 'creates', 'creating',
    'synthesise', 'synthesises', 'synthesize', 'synthesizes',
    'scaffold', 'scaffolds', 'scaffolding',
    'populate', 'populates', 'populating',
    'draft', 'drafts', 'drafting',
    'implement', 'implements', 'implementing',
)

# Prose that forbids an operation rather than instructing it. The raw-shell
# branch matched several of these: a Step saying the executor cannot run Bash
# contains the same tokens as one telling it to, and was read as the latter.
_PROHIBITION_RE = re.compile(
    r"\b(?:cannot|can't|must\s+not|may\s+not|never|does\s+not|do\s+not|don't|"
    r"denies|denied|without|instead\s+of|forbidden|prohibited)\b",
    re.IGNORECASE,
)

_INVOCATION_VERB_RE = re.compile(
    r'\b(?:' + '|'.join(_INVOCATION_VERBS + _GOVERNING_PREPOSITIONS) + r')\b(?!-)',
    re.IGNORECASE,
)
_AUTHORING_VERB_RE = re.compile(
    r'\b(?:' + '|'.join(_AUTHORING_VERBS) + r')\b(?!-)', re.IGNORECASE
)

# How far before the mention an invocation verb may sit and still govern it.
# Wide enough for "tells the sonnet executor to run Skill(...)", narrow enough
# that a verb belonging to an earlier clause does not reach across.
_GOVERNING_WINDOW = 60

# Edit-tool diff blocks. A skill name inside one is content being moved
# between two files, never an instruction to this executor.
_DIFF_BLOCK_RE = re.compile(r'\b(?:old_string|new_string)\b', re.IGNORECASE)


def _authoring_frame_before(text: str, mention_start: int) -> bool:
    """
    True when an authoring verb appears in `text` earlier than the mention at
    `mention_start`. Such a verb frames everything after it as content being
    produced (R3).

    Called at paragraph scope rather than sentence scope, because the frame is
    routinely set one sentence before the mention and holds over the whole
    bullet: `Create the slash command at <path>. Body: instruct the model to
    invoke Skill(...)`. Sentence scope alone left every finding of that shape
    standing, and that shape was most of what the sweep found.
    """
    return _AUTHORING_VERB_RE.search(text[:mention_start]) is not None


def _governed_by_invocation(text: str, mention_start: int) -> bool:
    """
    True when the mention at `mention_start` is governed by an invocation verb
    or preposition within _GOVERNING_WINDOW characters before it (R1).

    There is deliberately no allowance for a bare mention at the head of its
    sentence. `The Skill("write-plan") invocation pattern must work` is a
    sentence *about* a call, and a head allowance admitted exactly that.
    """
    window = text[max(0, mention_start - _GOVERNING_WINDOW):mention_start]
    return _INVOCATION_VERB_RE.search(window) is not None


# ---------------------------------------------------------------------------
# Internal helpers - file reads and frontmatter parsing
# ---------------------------------------------------------------------------

def _read_text(path: str) -> str:
    """Read a file with errors='replace' to handle non-UTF-8 bytes."""
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def _read_frontmatter_block(text: str) -> str:
    """Return the text between the opening '---' line and the next '---' line."""
    lines = text.split('\n')
    if not lines or lines[0].strip() != '---':
        return ''
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            return '\n'.join(lines[1:i])
    return ''


def _parse_flow_or_block_list(fm: str, field: str) -> Optional[list[str]]:
    """
    Return the parsed list value of a frontmatter field, accepting both the
    inline-flow form (`field: [a, b]`) and the block-sequence form
    (`field:` followed by `- a` / `- b` lines). Returns None when the field is
    absent entirely, distinct from an empty list.
    """
    lines = fm.split('\n')
    for i, line in enumerate(lines):
        m = re.match(rf'^{re.escape(field)}\s*:\s*(.*)$', line)
        if not m:
            continue
        rest = m.group(1).strip()
        if rest.startswith('['):
            inline = rest
            j = i
            while ']' not in inline and j + 1 < len(lines):
                j += 1
                inline += ' ' + lines[j].strip()
            if '[' not in inline or ']' not in inline:
                return []
            inner = inline[inline.find('[') + 1: inline.rfind(']')]
            return [c.strip().strip('"\'') for c in inner.split(',') if c.strip()]
        if rest:
            # A scalar on the same line as the key - treat as a single entry.
            return [rest.strip('"\'')]
        # Block-sequence form: subsequent '- <item>' lines.
        items: list[str] = []
        for j in range(i + 1, len(lines)):
            stripped = lines[j].strip()
            if stripped.startswith('- '):
                items.append(stripped[2:].strip().strip('"\''))
            elif stripped == '':
                continue
            else:
                break
        return items
    return None


def _read_acknowledgements(plan_text: str) -> list[str]:
    """
    Return the PLAN's audit_acknowledgements entries as bare code strings, or
    [] when the field is absent, empty or unparseable (D3). A parse failure
    returns [] deliberately - it fails toward emitting the finding rather than
    suppressing it. Accepts both the block-sequence and inline-flow forms,
    since both occur on disk today. No YAML library is imported - a bounded
    regex over the frontmatter block is sufficient, matching the sibling lint
    modules' pure-stdlib design.
    """
    fm = _read_frontmatter_block(plan_text)
    if not fm:
        return []
    result = _parse_flow_or_block_list(fm, 'audit_acknowledgements')
    return result if result is not None else []


def _read_assigned_to(plan_text: str) -> str:
    """Return the frontmatter assigned_to value, stripped and lowercased, or ''."""
    fm = _read_frontmatter_block(plan_text)
    if not fm:
        return ''
    m = re.search(r'^assigned_to\s*:\s*(.*)$', fm, re.MULTILINE)
    if not m:
        return ''
    return m.group(1).strip().strip('"\'').lower()


def _resolve_agent(plan_text: str) -> tuple[str, str]:
    """
    Return (agent_name, agent_path) for the PLAN's assigned_to value (D9). An
    unrecognised value - including 'human' - falls back to _DEFAULT_AGENT.
    """
    assigned_to = _read_assigned_to(plan_text)
    agent_name = _TIER_TO_AGENT.get(assigned_to, _DEFAULT_AGENT)
    agent_path = os.path.join(_AGENTS_DIR, f'{agent_name}.md')
    return agent_name, agent_path


def _read_agent_declaration(agent_path: str) -> tuple[Optional[list[str]], bool]:
    """
    Parse the agent file's frontmatter and return (preloaded_skills, bash_denied).

    preloaded_skills is None - distinct from [] - when the file is missing,
    unreadable, or carries no skills: field (the D9 EBV002 branch). bash_denied
    is True when the disallowedTools: value contains the token 'Bash'.
    """
    if not os.path.isfile(agent_path):
        return None, False
    text = _read_text(agent_path)
    fm = _read_frontmatter_block(text)
    if not fm:
        return None, False

    skills = _parse_flow_or_block_list(fm, 'skills')

    bash_denied = False
    m = re.search(r'^disallowedTools\s*:\s*(.*)$', fm, re.MULTILINE)
    if m and 'Bash' in m.group(1):
        bash_denied = True

    return skills, bash_denied


def _skill_exists(name: str) -> bool:
    """The prose patterns' on-disk existence filter, per D2."""
    return os.path.isfile(os.path.join(_SKILLS_DIR, name, 'SKILL.md'))


# ---------------------------------------------------------------------------
# Internal helpers - Steps-section extraction and sentence splitting
# ---------------------------------------------------------------------------

_STEPS_SECTION_RE = re.compile(r'^##\s+Steps\s*\n(.*?)(?=^##\s|\Z)', re.MULTILINE | re.DOTALL)


def _extract_steps_section(plan_text: str) -> str:
    """Return the text of the ## Steps section, or '' if absent (D5)."""
    match = _STEPS_SECTION_RE.search(plan_text)
    return match.group(1) if match else ''


# The leading-whitespace allowance is load-bearing. Without it a fence opened
# under a numbered step - the usual place a PLAN quotes an Edit's old_string -
# is not recognised, and every skill name inside the quoted block is read as an
# instruction to this executor. Two findings in the 2026-08-05 sweep were that
# and nothing else.
_FENCED_BLOCK_RE = re.compile(r'^[ \t]*```.*?^[ \t]*```', re.MULTILINE | re.DOTALL)


def _strip_fenced_blocks(text: str) -> str:
    """
    Blank out every fenced block (D5) - offset-preserving. Each matched block
    is replaced with a run of spaces/newlines of exactly the same length,
    rather than deleted, so every character position in the returned text
    still corresponds to the same position in the input.
    _step_number_for_offset depends on that correspondence.
    """
    def _blank(m: re.Match[str]) -> str:
        return ''.join(ch if ch == '\n' else ' ' for ch in m.group(0))

    return _FENCED_BLOCK_RE.sub(_blank, text)


_SENTENCE_RE = re.compile(r'\S[^\n]*?(?:[.!?](?=\s|$)|(?=\n)|$)')


def _split_sentences(text: str) -> list[tuple[str, int]]:
    """
    Return (sentence, offset) pairs, offset being the sentence's first
    character's index in `text`.

    The whitespace lookahead after the terminator is load-bearing and must
    not be relaxed: a sentence ends at '.', '!' or '?' only when whitespace
    or end-of-input follows, otherwise at a newline. Without it a dotted
    filename ends a sentence, stranding a non-executor marker in one fragment
    and the crossing in the next - an error-severity false positive on
    correctly-attributed prose, which is exactly what D2 exists to prevent.
    re.split cannot be used here because it discards the positions this
    function must return.
    """
    pairs: list[tuple[str, int]] = []
    for m in _SENTENCE_RE.finditer(text):
        sentence = m.group()
        if sentence.strip():
            pairs.append((sentence, m.start()))
    return pairs


_STEP_LINE_RE = re.compile(r'^(\d+)\.\s+')

# The other numbering style in use on disk: `### Step 7: <title>`. PLANs
# written this way carry ordinary numbered sentences in their prose, so the
# two styles must never be consulted together - see _step_line_pattern.
_STEP_HEADING_RE = re.compile(r'^#{2,4}\s+Step\s+(\d+)\b', re.IGNORECASE)


def _line_starts(lines: list[str]) -> list[int]:
    """Character offset of each line's first character."""
    starts: list[int] = []
    pos = 0
    for line in lines:
        starts.append(pos)
        pos += len(line) + 1  # +1 for the '\n' split() consumed
    return starts


def _step_line_pattern(lines: list[str]) -> re.Pattern[str]:
    """
    Choose the step-numbering style this PLAN uses, and return the pattern for
    it. Heading style wins whenever any `### Step N:` line is present.

    Consulting both styles is what produced the location bug this function was
    repaired for: a PLAN numbering its steps as headings still contains
    ordinary `2. ` lines in its prose, and the old single-pattern scan locked
    onto one of those and reported a plausible, wrong step number - worse than
    reporting none, because nothing about it looks unreliable.
    """
    if any(_STEP_HEADING_RE.match(line) for line in lines):
        return _STEP_HEADING_RE
    return _STEP_LINE_RE


def _step_number_for_offset(steps_text: str, offset: int) -> str:
    """
    Return the number of the step containing `offset`, in whichever numbering
    style this PLAN uses, or '## Steps' when no step line precedes (or
    contains) the match.

    Deliberately inclusive of the offset's own line: a match's sentence
    typically starts at the first non-whitespace character of its line, which
    for a top-level Step is the digit itself - excluding that line would
    always report the *previous* Step number instead of the containing one.
    """
    lines = steps_text.split('\n')
    starts = _line_starts(lines)
    pattern = _step_line_pattern(lines)

    containing_idx = 0
    for i, start in enumerate(starts):
        if start <= offset:
            containing_idx = i
        else:
            break

    for i in range(containing_idx, -1, -1):
        m = pattern.match(lines[i])
        if m:
            return m.group(1)
    return '## Steps'


def _containing_paragraph(steps_text: str, offset: int) -> tuple[str, int]:
    """
    Return (paragraph_text, paragraph_start_offset) for the contiguous run of
    non-blank lines around `offset`.

    Scoped to the paragraph rather than the whole step on purpose: a step may
    legitimately both edit a file and instruct an invocation, and suppressing
    the whole step on one diff block inside it would lose the second.

    Bounded by a step line as well as by a blank line. Many PLANs pack their
    numbered steps with no blank line between them, which makes the whole
    Steps section one paragraph and lets an authoring verb in step 1 suppress
    a genuine crossing in step 3. Expanding back to the step's own lead line
    and no further is also what makes the lead-line attribution case work: a
    sub-bullet inherits its step's framing, and nothing earlier.
    """
    lines = steps_text.split('\n')
    starts = _line_starts(lines)
    step_re = _step_line_pattern(lines)

    idx = 0
    for i, start in enumerate(starts):
        if start <= offset:
            idx = i
        else:
            break

    first = idx
    while (
        first > 0
        and lines[first - 1].strip()
        and not step_re.match(lines[first])
    ):
        first -= 1
    last = idx
    while (
        last + 1 < len(lines)
        and lines[last + 1].strip()
        and not step_re.match(lines[last + 1])
    ):
        last += 1
    return '\n'.join(lines[first:last + 1]), starts[first]


def _containing_step(steps_text: str, offset: int) -> tuple[str, int]:
    """
    Return (step_text, step_start_offset) for the step containing `offset`,
    spanning blank lines up to the next step line.

    The authoring frame is evaluated at this scope. A step that opens by
    naming the file it is writing frames every sub-bullet under it, however
    many blank lines away: `Step 5: Implement Apply. Where: lib/tidy_wip.py.
    What: for each row, dispatch Skill(...)`. Paragraph scope stopped at the
    blank line and read that dispatch as an instruction to the executor.

    The cost is a real false negative: a step that both authors a file and
    separately instructs an invocation loses the second. That is the same
    trade _has_non_executor_marker records - a false negative degrades to
    read-by-eye, a false positive blocks a correct PLAN.
    """
    lines = steps_text.split('\n')
    starts = _line_starts(lines)
    step_re = _step_line_pattern(lines)

    idx = 0
    for i, start in enumerate(starts):
        if start <= offset:
            idx = i
        else:
            break

    first = idx
    while first > 0 and not step_re.match(lines[first]):
        first -= 1
    last = idx
    while last + 1 < len(lines) and not step_re.match(lines[last + 1]):
        last += 1
    return '\n'.join(lines[first:last + 1]), starts[first]


def _make_finding(
    code: str,
    level: str,
    location: str,
    message: str,
    suggested_fix: str = '',
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        'code': code,
        'level': level,
        'category': 'capability-boundary',
        'location': location,
        'message': message,
    }
    if suggested_fix:
        finding['suggested_fix'] = suggested_fix
    return finding


_SUGGESTED_FIX = (
    'Re-author the Step to name the orchestrator as the actor (e.g. "the orchestrator '
    'retires <target>"), or move the operation out of executor scope entirely.'
)


# ---------------------------------------------------------------------------
# Main lint function
# ---------------------------------------------------------------------------

def lint_plan(plan_path: str, ack_codes: Optional[list[str]] = None) -> list[dict]:
    """
    Lint a PLAN's ## Steps section for executor-capability-boundary crossings.

    Parameters
    ----------
    plan_path:
        Path to the PLAN markdown file.
    ack_codes:
        Override for the PLAN's audit_acknowledgements. When None (the
        default), the PLAN's own frontmatter is read (D7) - the documented
        one-line invocation passes no ack_codes, so the default path must not
        depend on a caller remembering to pass anything. Pass [] explicitly to
        measure the raw heuristic regardless of what the PLAN has waived.

    Returns
    -------
    List of finding dicts (may be empty for a clean plan).
    """
    plan_text = _read_text(plan_path)

    if ack_codes is None:
        ack_codes = _read_acknowledgements(plan_text)

    agent_name, agent_path = _resolve_agent(plan_text)
    preloaded_skills, bash_denied = _read_agent_declaration(agent_path)

    if preloaded_skills is None:
        if 'EBV002' in ack_codes:
            return []
        assigned_to = _read_assigned_to(plan_text)
        return [_make_finding(
            'EBV002',
            'warning',
            agent_path,
            (
                f"capability-boundary-unresolved: could not read a skills: declaration from "
                f"{agent_path} (assigned_to: '{assigned_to}'), so no executor-capability check "
                f"ran for this PLAN."
            ),
            f"Repair {agent_path} so it declares a skills: list (and disallowedTools: where "
            f"relevant), or correct this PLAN's assigned_to value.",
        )]

    steps_text = _extract_steps_section(plan_text)
    stripped_text = _strip_fenced_blocks(steps_text)
    sentences = _split_sentences(stripped_text)

    skills_display = ', '.join(preloaded_skills) if preloaded_skills else '(none)'

    findings: list[dict] = []

    for sentence, offset in sentences:
        if _has_non_executor_marker(sentence):
            continue

        step_number = _step_number_for_offset(steps_text, offset)
        location = f'Step {step_number}' if step_number != '## Steps' else step_number

        # R3, block half: a diff block is content being moved between files.
        # Scoped to the paragraph, not the step - a step may legitimately both
        # edit a file and instruct an invocation.
        para, _para_start = _containing_paragraph(stripped_text, offset)
        if _DIFF_BLOCK_RE.search(para):
            continue

        # R1 and R3 are evaluated over the containing step.
        step_text, step_start = _containing_step(stripped_text, offset)

        def _not_authored(match_start: int) -> bool:
            """R3, for a match starting at `match_start` within this sentence."""
            return not _authoring_frame_before(
                step_text, offset + match_start - step_start
            )

        def _runs(match_start: int) -> bool:
            """R1 and R3 together, for the bare-literal branch. The two prose
            patterns embed an invocation verb in the pattern itself, so R1 is
            already satisfied for them and only R3 is applied there."""
            pos = offset + match_start - step_start
            return (
                _governed_by_invocation(step_text, pos)
                and not _authoring_frame_before(step_text, pos)
            )

        skill_name: Optional[str] = None
        call_match = _SKILL_CALL_RE.search(sentence)
        if call_match:
            # R2 as well: the name must resolve to a skill on disk, the same
            # existence filter the prose branches already apply.
            if _skill_exists(call_match.group(1)) and _runs(call_match.start()):
                skill_name = call_match.group(1)
        if skill_name is None:
            forward_match = _SKILL_PROSE_RE.search(sentence)
            if (
                forward_match
                and _skill_exists(forward_match.group(1))
                and _not_authored(forward_match.start(1))
            ):
                skill_name = forward_match.group(1)
            else:
                reverse_match = _SKILL_PROSE_REVERSE_RE.search(sentence)
                if (
                    reverse_match
                    and _skill_exists(reverse_match.group(1))
                    and _not_authored(reverse_match.start(1))
                ):
                    skill_name = reverse_match.group(1)

        if skill_name is not None:
            if skill_name in preloaded_skills:
                continue
            if 'EBV001' in ack_codes:
                continue
            note = _STRUCTURAL_NOTES.get(skill_name, '')
            message = (
                f"capability-boundary-violation: {location} asks the executor to invoke "
                f"'{skill_name}', which is not in {agent_name}'s preloaded skills "
                f"({skills_display}). Skill() from a subagent fails as a silent no-op, "
                f"so route this to the orchestrator (parent session)."
            )
            if note:
                message += f' {note}'
            findings.append(_make_finding('EBV001', 'error', location, message, _SUGGESTED_FIX))
            continue

        shell_match = _RAW_SHELL_RE.search(sentence)
        if shell_match and bash_denied:
            if 'EBV001' in ack_codes:
                continue
            if _PROHIBITION_RE.search(sentence):
                continue
            if _authoring_frame_before(
                step_text, offset + shell_match.start() - step_start
            ):
                continue
            message = (
                f"capability-boundary-violation: {location} asks the executor to run raw "
                f"bash/sh, which {agent_name} denies via disallowedTools. Route this to the "
                f"orchestrator (parent session)."
            )
            findings.append(_make_finding('EBV001', 'error', location, message, _SUGGESTED_FIX))

    return findings
