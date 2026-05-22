#!/usr/bin/env python3
"""Foundry-keeper hook: deterministic event capture to unified JSONL log.

Registered as a PostToolUse hook. Captures skill calls, tool usage,
subagent dispatches, and other mechanical events. Manual events (hiccups)
are captured via the foundry-log skill, not this hook.

Log path: .claude/_foundry_log.jsonl (configurable via .claude/plan-foundry.config logPath).
"""
import datetime
import json
import pathlib
import sys

DEFAULT_LOG_PATH = pathlib.Path(".claude/_foundry_log.jsonl")
CONFIG_PATH = pathlib.Path(".claude/plan-foundry.config")
SCHEMA_VERSION = 1


def get_log_path() -> pathlib.Path:
    if CONFIG_PATH.exists():
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            custom = config.get("logPath")
            if custom:
                return pathlib.Path(custom)
        except (json.JSONDecodeError, OSError):
            pass
    return DEFAULT_LOG_PATH


def append_entry(log_path: pathlib.Path, entry: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0

    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = payload.get("session_id", "")
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response")
    log_path = get_log_path()

    base = {
        "ts": ts,
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
    }

    if tool_name == "Skill":
        ok = True
        if isinstance(tool_response, dict) and tool_response.get("error") is not None:
            ok = False
        entry = {
            **base,
            "kind": "skill_call",
            "skill": tool_input.get("skill", ""),
            "args": tool_input.get("args", ""),
            "ok": ok,
        }
        append_entry(log_path, entry)

    elif tool_name == "Agent":
        entry = {
            **base,
            "kind": "subagent_start",
            "agent": tool_input.get("subagent_type", tool_input.get("type", "")),
            "description": tool_input.get("description", "")[:120],
        }
        append_entry(log_path, entry)

    else:
        summary = ""
        if isinstance(tool_input, dict):
            for key in ("command", "file_path", "query", "prompt"):
                if key in tool_input:
                    summary = str(tool_input[key])[:120]
                    break
        entry = {
            **base,
            "kind": "tool_use",
            "tool": tool_name,
            "summary": summary,
        }
        append_entry(log_path, entry)

    return 0


if __name__ == "__main__":
    sys.exit(main())
