# Anti-patterns

Flag each pattern below when it appears in any file the skill has in scope, either as a blocker (must be fixed) or as a warn (should be reviewed). Section D of the checklist applies to every in-scope file, not to CLAUDE.md and CONTEXT_CONSTITUTION.md alone.

## Blockers

### Natural-language linting
These are rules that describe formatting or style that tooling can enforce. Examples:
- "Use 2 spaces for indentation"
- "Use single quotes for strings"
- "Always include a trailing newline"
**Why blocker:** the rule spends instruction budget on a job an LLM does worse than a linter. Move the rule to `.eslintrc`, `.prettierrc`, `pyproject.toml`, or a `post_tool_use` hook in `settings.json`.

### AI-generated bloat
This is verbose generic guidance with no project specificity. Tells:
- Sentences starting with "It's important to..." / "Remember to..." / "Always make sure to..."
- Bullet lists of generic best practices ("Write clean code", "Add tests", "Handle errors")
- Hedging modifiers ("might", "should consider", "could be useful")
**Why blocker:** the guidance carries zero per-token signal. Either replace it with project-specific imperatives or delete the section.

### Codebase duplication
This is documentation of facts that are authoritative elsewhere:
- Dependency lists that duplicate `requirements.txt` / `package.json`
- Config schemas that duplicate the actual config file
- Module-by-module architecture descriptions Claude can derive by reading the code
**Why blocker:** the copy drifts silently when the source updates. Either move the content to `.claude/references/` as a pointer, or delete the content and let Claude read the source.

### Dead references
These are pointers to files, skills, or sections that no longer exist.
**Why blocker:** a dead pointer poisons context, because Claude follows the pointer, finds nothing, and may invent content to fill the gap.

## Warns

### Static maintenance smell
- Version numbers inline (likely to drift)
- "As of YYYY-MM" timestamps without an audit cadence
- "We recently switched to X" (will become stale)
**Why warn:** date the project, schedule a review, or move the statement to a versioned reference.

### Lost-in-the-middle risk
- Critical rules buried 60-80% into the file with no signal-boost markers
- Long mid-file sections with no headers (model attention drifts)
**Why warn:** restructure the file or add IMPORTANT markers.

### Caveat creep
- Caveats section growing past ~10 items
**Why warn:** a long caveats section likely holds some caveats that are now obvious from the code (delete those) and some that are subsystem-specific (move those to a subsystem reference).

### Subagent / delegation rules missing
- No documented threshold for when to delegate to a subagent
**Why warn:** Claude defaults to handling everything inline, which spends context on large searches.

## Not anti-patterns (do not flag)

- Working-style preferences (AU spelling, tone, review format) - these are the user's signal.
- Project-specific imperatives ("never modify schema.prisma directly") - these are the Trinity caveats, and they belong here.
- Pointers to references / skills - that is progressive disclosure working correctly.
- Long-but-load-bearing rules at top or bottom of file (instruction weighting deliberately uses the edges).
