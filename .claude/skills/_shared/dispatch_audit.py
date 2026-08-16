"""
dispatch_audit.py - the compliance-join audit named in dispatch-authorisation.md
"Verifying compliance": read a session's subagent records and report the
tier and, where derivable, the concurrency of every discretionary dispatch.

This module reports. It never enforces. Nothing in here raises the process
exit code because a dispatch looks wrong - a wrong-looking dispatch is a
finding for the reader to act on, not a reason to fail a build. The CLI
below always exits 0 on a successful read, whatever the records show.

Two record shapes on disk, joined here:
  - <session-dir>/subagents/agent-<id>.meta.json carries agentType,
    description, toolUseId, spawnDepth, and the model the dispatcher
    requested (a short name such as "sonnet", or absent when no override
    was passed).
  - The sibling agent-<id>.jsonl carries the model that actually ran, on
    the "model" field of the "message" object in every assistant-role
    line (a full model id such as "claude-sonnet-5").

Concurrency - the other dial the ladder in dispatch-authorisation.md
names - is not in either record. This module derives it from each agent's
own <session-dir>/subagents/agent-<id>.jsonl: every line the harness
writes to a subagent transcript, including the initiating user turn,
carries a top-level "timestamp" field, so an agent's span is its first and
last timestamp. Concurrency for one dispatch is how many agents in the
session - counting itself - have a span that overlaps its span. This is
coarser than true wall-clock concurrency: a span also counts any idle gap
inside its own window as running, and an agent that was dispatched but
wrote no message has no timestamp and so no span. That agent's
concurrency is unavailable, never "1" - defaulting to the flattering
value is the reason this derivation exists.

Every read in this module tolerates absence: a missing directory, an
unreadable file, a malformed JSON line, or a record with no model field
each produce a note in the report rather than an exception. The records
this module reads live outside the repository under the user's home
directory, so a fresh clone or a CI runner will not have them, and running
this module there must not fail.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

_SHARED_DIR = pathlib.Path(__file__).resolve().parent
_DEFAULT_AGENTS_DIR = _SHARED_DIR.parents[1] / "agents"

_TIER_NAMES = ("opus", "sonnet", "haiku", "fable")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class DispatchRecord:
    agent_id: str
    agent_type: Optional[str]
    description: Optional[str]
    tool_use_id: Optional[str]
    spawn_depth: Optional[int]
    requested_tier: str
    requested_tier_source: str
    actual_tier: str
    actual_model_raw: Optional[str]
    tier_mismatch: Optional[bool]
    pipeline_fixed: bool
    concurrency_group_size: Optional[int]
    rung: str
    gaps: List[str] = field(default_factory=list)


@dataclass
class DispatchAuditReport:
    session_dir: Optional[str]
    session_id: Optional[str]
    project_slug: Optional[str]
    records: List[DispatchRecord]
    session_gaps: List[str] = field(default_factory=list)
    concurrency_available: bool = False


# ---------------------------------------------------------------------------
# Tier classification
# ---------------------------------------------------------------------------


def _tier_from_string(value: Optional[str]) -> str:
    """Map a model name - short ("sonnet") or full ("claude-sonnet-5") - to
    one of "opus", "sonnet", "haiku", "fable". Returns "unknown" for
    anything else, including None and the empty string, rather than
    raising."""
    if not value:
        return "unknown"
    lowered = value.lower()
    if "mythos" in lowered:
        return "fable"
    for tier in _TIER_NAMES:
        if tier in lowered:
            return tier
    return "unknown"


# ---------------------------------------------------------------------------
# Pipeline-fixed agent types (the exemption in dispatch-authorisation.md)
# ---------------------------------------------------------------------------


def load_pipeline_fixed_agents(agents_dir: pathlib.Path) -> Dict[str, Optional[str]]:
    """Read every .claude/agents/*.md frontmatter and return
    {agent name: pinned tier or None}.

    An agent type named here has its model tier fixed by the agent file the
    phase state machine dispatches through, per the pipeline-dispatch
    exemption in dispatch-authorisation.md: "the phase state machine and
    agent files fix those tiers". The list is never hard-coded - it is
    read fresh from the agents directory on every call, so a new pipeline
    agent is picked up the moment its file lands.
    """
    fixed: Dict[str, Optional[str]] = {}
    agents_dir = pathlib.Path(agents_dir)
    if not agents_dir.is_dir():
        return fixed
    for md_path in sorted(agents_dir.glob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end == -1:
            continue
        frontmatter = text[3:end]
        name_match = re.search(r"^name:\s*(.+)$", frontmatter, re.M)
        model_match = re.search(r"^model:\s*(.+)$", frontmatter, re.M)
        name = name_match.group(1).strip() if name_match else md_path.stem
        model_raw = model_match.group(1).strip().strip('"').strip("'") if model_match else None
        fixed[name] = _tier_from_string(model_raw) if model_raw else None
    return fixed


# ---------------------------------------------------------------------------
# Record-level reads (meta.json, sibling .jsonl)
# ---------------------------------------------------------------------------


def _agent_id_from_stem(stem: str) -> str:
    """Strip the "agent-" prefix shared by agent-<id>.meta.json and
    agent-<id>.jsonl, so both files resolve to the same key."""
    return stem[len("agent-") :] if stem.startswith("agent-") else stem


def _read_meta(meta_path: pathlib.Path) -> Tuple[dict, Optional[str]]:
    try:
        text = meta_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {}, f"could not read {meta_path.name}: {exc}"
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        return {}, f"{meta_path.name} is not valid JSON: {exc}"
    if not isinstance(obj, dict):
        return {}, f"{meta_path.name} did not contain a JSON object"
    return obj, None


def _read_actual_model(jsonl_path: pathlib.Path) -> Tuple[Optional[str], List[str]]:
    """Return (model id or None, notes). Scans every line for the first
    assistant message carrying a "model" field, skipping lines that fail
    to parse as JSON rather than stopping at the first one."""
    notes: List[str] = []
    if not jsonl_path.exists():
        notes.append(f"sibling {jsonl_path.name} not found")
        return None, notes
    try:
        text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        notes.append(f"could not read {jsonl_path.name}: {exc}")
        return None, notes

    malformed = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        message = obj.get("message")
        if isinstance(message, dict):
            model = message.get("model")
            if model:
                if malformed:
                    notes.append(
                        f"{malformed} malformed JSON line(s) in {jsonl_path.name} "
                        "skipped before a usable model field was found"
                    )
                return model, notes

    if malformed:
        notes.append(f"{malformed} malformed JSON line(s) in {jsonl_path.name} skipped")
    notes.append(f"no model field found in any assistant message in {jsonl_path.name}")
    return None, notes


# ---------------------------------------------------------------------------
# Concurrency - derived from subagent transcript timestamp spans, never
# guessed, and never defaulted to "1" when a span cannot be built.
# ---------------------------------------------------------------------------


def _parse_timestamp(raw: object) -> Optional[float]:
    """Parse one ISO-8601 timestamp, such as the "timestamp" field written
    on every subagent transcript line, into a POSIX time usable for span
    comparison. Returns None - never raises - when raw is not a parsable
    string."""
    if not isinstance(raw, str) or not raw:
        return None
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _read_agent_span(jsonl_path: pathlib.Path) -> Tuple[Optional[Tuple[float, float]], List[str]]:
    """Return ((first timestamp, last timestamp), notes) for one agent's
    own transcript. Scans every line for a top-level "timestamp" field,
    skipping lines that fail to parse as JSON or that carry no parsable
    timestamp rather than stopping at the first one. Returns (None, notes)
    - a missing span, not a guessed one - when the file is absent,
    unreadable, or yields no parsable timestamp at all."""
    notes: List[str] = []
    if not jsonl_path.exists():
        notes.append(f"sibling {jsonl_path.name} not found")
        return None, notes
    try:
        text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        notes.append(f"could not read {jsonl_path.name}: {exc}")
        return None, notes

    stamps: List[float] = []
    malformed = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        parsed = _parse_timestamp(obj.get("timestamp"))
        if parsed is not None:
            stamps.append(parsed)

    if malformed:
        notes.append(f"{malformed} malformed JSON line(s) in {jsonl_path.name} skipped while building its span")

    if not stamps:
        notes.append(f"no parsable timestamp found in {jsonl_path.name}")
        return None, notes

    return (min(stamps), max(stamps)), notes


def _spans_overlap(a: Tuple[float, float], b: Tuple[float, float]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def build_concurrency_map(
    subagents_dir: pathlib.Path,
) -> Tuple[Dict[str, int], Dict[str, List[str]], bool]:
    """Return (agent_id -> concurrent-dispatch count, agent_id -> notes,
    any_span_available).

    Concurrency for one dispatch is how many agents in this session -
    counting itself - have a span (see _read_agent_span) that overlaps its
    own span. any_span_available is False only when nothing under
    subagents_dir yielded a usable span at all. In that case the caller
    reports the concurrency dimension as unavailable for the whole session,
    rather than one dispatch at a time. An agent whose own span could not
    be built is simply absent from the returned map - its siblings can
    still resolve.
    """
    per_agent_notes: Dict[str, List[str]] = {}
    spans: Dict[str, Tuple[float, float]] = {}
    subagents_dir = pathlib.Path(subagents_dir)
    jsonl_paths = sorted(subagents_dir.glob("*.jsonl")) if subagents_dir.is_dir() else []
    for jsonl_path in jsonl_paths:
        agent_id = _agent_id_from_stem(jsonl_path.stem)
        span, notes = _read_agent_span(jsonl_path)
        if notes:
            per_agent_notes[agent_id] = notes
        if span is not None:
            spans[agent_id] = span

    if not spans:
        return {}, per_agent_notes, False

    mapping = {
        agent_id: sum(1 for other in spans.values() if _spans_overlap(span, other))
        for agent_id, span in spans.items()
    }
    return mapping, per_agent_notes, True


# ---------------------------------------------------------------------------
# Rung classification
# ---------------------------------------------------------------------------


def _rung_for(
    pipeline_fixed: bool, actual_tier: str, concurrency_group_size: Optional[int]
) -> str:
    """Classify one dispatch against the ladder in dispatch-authorisation.md.

    Pipeline-fixed dispatches and Fable are both outside the ladder, for
    different reasons named in that file and in fable-escalation-policy.md
    respectively, and both are reported as such rather than assigned a
    rung.
    """
    if pipeline_fixed:
        return "exempt (pipeline-fixed dispatch; tier fixed by the agent file)"
    if actual_tier == "fable":
        return "n/a (Fable sits outside the ladder; see fable-escalation-policy.md)"
    if actual_tier == "haiku":
        return "rung 1"
    if actual_tier == "unknown":
        return "unavailable (actual tier unknown)"
    if concurrency_group_size is None:
        return f"unavailable (concurrency unknown; actual tier is {actual_tier})"
    if actual_tier == "sonnet":
        return "rung 2" if concurrency_group_size <= 1 else "rung 3"
    if actual_tier == "opus":
        return "rung 3" if concurrency_group_size <= 1 else "rung 4"
    return "unavailable"


# ---------------------------------------------------------------------------
# Record assembly
# ---------------------------------------------------------------------------


def _build_record(
    meta_path: pathlib.Path,
    agents_fixed: Dict[str, Optional[str]],
    concurrency_map: Dict[str, int],
    concurrency_notes: Dict[str, List[str]],
) -> DispatchRecord:
    gaps: List[str] = []
    meta, meta_err = _read_meta(meta_path)
    if meta_err:
        gaps.append(meta_err)

    stem = meta_path.name[: -len(".meta.json")] if meta_path.name.endswith(".meta.json") else meta_path.stem
    agent_id = _agent_id_from_stem(stem)

    agent_type = meta.get("agentType")
    description = meta.get("description")
    tool_use_id = meta.get("toolUseId")
    spawn_depth = meta.get("spawnDepth")
    requested_model_field = meta.get("model")

    jsonl_path = meta_path.with_name(stem + ".jsonl")
    actual_model_raw, model_notes = _read_actual_model(jsonl_path)
    gaps.extend(model_notes)
    actual_tier = _tier_from_string(actual_model_raw)

    pipeline_fixed = agent_type in agents_fixed
    if requested_model_field:
        requested_tier = _tier_from_string(requested_model_field)
        requested_tier_source = "explicit override at dispatch"
    elif pipeline_fixed and agents_fixed.get(agent_type):
        requested_tier = agents_fixed[agent_type]
        requested_tier_source = f"pinned in .claude/agents/{agent_type}.md"
    else:
        requested_tier = "unspecified"
        requested_tier_source = "no override recorded; inherits the dispatching session's model"

    if requested_tier in ("unspecified", "unknown") or actual_tier == "unknown":
        tier_mismatch: Optional[bool] = None
    else:
        tier_mismatch = requested_tier != actual_tier
    if tier_mismatch:
        gaps.append(
            f"requested tier '{requested_tier}' ({requested_tier_source}) does not match "
            f"the tier that actually ran ('{actual_tier}')"
        )

    concurrency_group_size: Optional[int] = concurrency_map.get(agent_id)
    own_span_notes = concurrency_notes.get(agent_id, [])
    if concurrency_group_size is None:
        if own_span_notes:
            gaps.extend(f"concurrency unavailable - {note}" for note in own_span_notes)
        else:
            gaps.append(
                f"concurrency unavailable - no {stem}.jsonl transcript found to "
                "derive a timestamp span from"
            )
    else:
        gaps.extend(own_span_notes)

    rung = _rung_for(pipeline_fixed, actual_tier, concurrency_group_size)

    return DispatchRecord(
        agent_id=agent_id,
        agent_type=agent_type,
        description=description,
        tool_use_id=tool_use_id,
        spawn_depth=spawn_depth,
        requested_tier=requested_tier,
        requested_tier_source=requested_tier_source,
        actual_tier=actual_tier,
        actual_model_raw=actual_model_raw,
        tier_mismatch=tier_mismatch,
        pipeline_fixed=pipeline_fixed,
        concurrency_group_size=concurrency_group_size,
        rung=rung,
        gaps=gaps,
    )


# ---------------------------------------------------------------------------
# Session and project level entry points
# ---------------------------------------------------------------------------


def audit_session(
    session_dir: pathlib.Path,
    agents_dir: pathlib.Path = _DEFAULT_AGENTS_DIR,
) -> DispatchAuditReport:
    """Audit one session directory (the directory that holds subagents/)."""
    session_dir = pathlib.Path(session_dir)
    session_id = session_dir.name
    session_gaps: List[str] = []
    agents_fixed = load_pipeline_fixed_agents(pathlib.Path(agents_dir))

    subagents_dir = session_dir / "subagents"
    if not subagents_dir.is_dir():
        session_gaps.append(f"no subagents/ directory under {session_dir}")
        return DispatchAuditReport(
            session_dir=str(session_dir),
            session_id=session_id,
            project_slug=None,
            records=[],
            session_gaps=session_gaps,
            concurrency_available=False,
        )

    concurrency_map, concurrency_notes, any_span_available = build_concurrency_map(subagents_dir)
    if not any_span_available:
        session_gaps.append(
            "concurrency unavailable for this session - no subagent transcript "
            f"under {subagents_dir} yielded a usable timestamp span"
        )

    meta_paths = sorted(subagents_dir.glob("*.meta.json"))
    if not meta_paths:
        session_gaps.append(f"no *.meta.json records under {subagents_dir}")

    records = [
        _build_record(p, agents_fixed, concurrency_map, concurrency_notes) for p in meta_paths
    ]

    return DispatchAuditReport(
        session_dir=str(session_dir),
        session_id=session_id,
        project_slug=None,
        records=records,
        session_gaps=session_gaps,
        concurrency_available=any_span_available,
    )


def derive_project_slug(project_root: pathlib.Path) -> str:
    """Reproduce the harness's own project-directory naming: the absolute
    project path with every non-alphanumeric character replaced by a
    hyphen, one hyphen per character (so "D:\\projects\\plan_foundry_dev"
    becomes "D--projects-plan-foundry-dev").

    Uses os.path.abspath rather than pathlib's resolve() on purpose.
    resolve() walks the real filesystem on Windows and can silently correct
    the case of a path segment to whatever the disk actually stored, which
    would make the derived slug depend on machine-specific directory case
    rather than on the path string alone. abspath is purely lexical."""
    raw = os.path.abspath(str(project_root))
    return "".join(ch if ch.isalnum() else "-" for ch in raw)


def find_latest_session_dir(
    projects_dir: pathlib.Path,
) -> Tuple[Optional[pathlib.Path], List[str]]:
    """Return (most recently modified session directory carrying a
    subagents/ folder under projects_dir, notes). None with a note when
    projects_dir is absent or carries no such session."""
    notes: List[str] = []
    projects_dir = pathlib.Path(projects_dir)
    if not projects_dir.is_dir():
        notes.append(f"project directory not found: {projects_dir}")
        return None, notes
    candidates = [
        d
        for d in projects_dir.iterdir()
        if d.is_dir() and d.name != "memory" and (d / "subagents").is_dir()
    ]
    if not candidates:
        notes.append(f"no session directory with a subagents/ folder under {projects_dir}")
        return None, notes
    candidates.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return candidates[0], notes


def audit_project(
    project_root: Optional[pathlib.Path] = None,
    claude_projects_root: Optional[pathlib.Path] = None,
    agents_dir: Optional[pathlib.Path] = None,
    session_dir: Optional[pathlib.Path] = None,
) -> DispatchAuditReport:
    """Top-level entry point: resolve the project slug, pick a session
    directory, and audit it.

    project_root defaults to the current working directory. claude_projects_root
    defaults to ~/.claude/projects; pass it explicitly in tests so nothing
    here ever reads the real home directory. session_dir bypasses slug
    derivation and session selection entirely - pass it to name a session
    directly.
    """
    project_root = pathlib.Path(project_root) if project_root else pathlib.Path.cwd()
    agents_dir = pathlib.Path(agents_dir) if agents_dir else _DEFAULT_AGENTS_DIR
    if claude_projects_root is None:
        claude_projects_root = pathlib.Path.home() / ".claude" / "projects"
    else:
        claude_projects_root = pathlib.Path(claude_projects_root)

    slug = derive_project_slug(project_root)
    projects_dir = claude_projects_root / slug

    session_gaps: List[str] = []
    chosen_dir = pathlib.Path(session_dir) if session_dir else None
    if chosen_dir is None:
        chosen_dir, notes = find_latest_session_dir(projects_dir)
        session_gaps.extend(notes)

    if chosen_dir is None:
        return DispatchAuditReport(
            session_dir=None,
            session_id=None,
            project_slug=slug,
            records=[],
            session_gaps=session_gaps,
            concurrency_available=False,
        )

    report = audit_session(chosen_dir, agents_dir=agents_dir)
    report.project_slug = slug
    report.session_gaps = session_gaps + report.session_gaps
    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _format_table(report: DispatchAuditReport) -> str:
    lines: List[str] = []
    lines.append(f"session id: {report.session_id or '(none found)'}")
    lines.append(f"session dir: {report.session_dir or '-'}")
    lines.append(f"project slug: {report.project_slug or '-'}")
    if report.concurrency_available:
        lines.append("concurrency dimension: derived from subagent transcript timestamp spans")
    else:
        lines.append(
            "concurrency dimension: UNAVAILABLE for this session "
            "(see notes below) - report this gap, do not assume solitary dispatch"
        )
    lines.append("")

    if report.session_gaps:
        lines.append("session-level notes:")
        for gap in report.session_gaps:
            lines.append(f"  - {gap}")
        lines.append("")

    if not report.records:
        lines.append("no dispatch records found.")
        return "\n".join(lines)

    header = (
        f"{'agent_id':<20} {'agent_type':<26} {'requested':<10} {'actual':<9} "
        f"{'mismatch':<9} {'concurrency':<12} {'rung'}"
    )
    lines.append(header)
    lines.append("-" * len(header))
    for rec in report.records:
        if rec.tier_mismatch is True:
            mismatch = "YES"
        elif rec.tier_mismatch is False:
            mismatch = "no"
        else:
            mismatch = "-"
        concurrency = str(rec.concurrency_group_size) if rec.concurrency_group_size is not None else "unavailable"
        lines.append(
            f"{rec.agent_id[:20]:<20} {(rec.agent_type or '?')[:26]:<26} "
            f"{rec.requested_tier:<10} {rec.actual_tier:<9} {mismatch:<9} "
            f"{concurrency:<12} {rec.rung}"
        )

    per_dispatch_notes = [(rec.agent_id, gap) for rec in report.records for gap in rec.gaps]
    if per_dispatch_notes:
        lines.append("")
        lines.append("per-dispatch notes:")
        for agent_id, gap in per_dispatch_notes:
            lines.append(f"  - {agent_id}: {gap}")

    lines.append("")
    lines.append(f"dispatches reported: {len(report.records)}")
    return "\n".join(lines)


def _parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Report the tier and, where derivable, the concurrency of every "
            "subagent dispatch in a Claude Code session. Reports only; never "
            "exits non-zero because a dispatch looks wrong."
        )
    )
    parser.add_argument(
        "--session-dir",
        type=pathlib.Path,
        default=None,
        help="Audit this specific session directory instead of auto-selecting "
        "the most recently modified one for the current project.",
    )
    parser.add_argument(
        "--project-root",
        type=pathlib.Path,
        default=None,
        help="Project root used to derive the project slug under "
        "~/.claude/projects. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as JSON instead of a table.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    # Windows consoles default to cp1252; force UTF-8 stdout/stderr so a
    # non-ASCII agent description or path never crashes the report. PLAN-AF2
    # guard, applied here for the same reason it is applied across scripts/ci/.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = _parse_args(argv)
    report = audit_project(project_root=args.project_root, session_dir=args.session_dir)

    if args.json:
        print(json.dumps(dataclasses.asdict(report), indent=2, default=str))
    else:
        print(_format_table(report))

    return 0


if __name__ == "__main__":
    sys.exit(main())
