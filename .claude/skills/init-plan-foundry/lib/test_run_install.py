"""End-to-end tests for run_install.py against a fixture bundle and tmp target."""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_LIB = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(_LIB))

import run_install  # noqa: E402


def _build_fixture_bundle(root: pathlib.Path) -> pathlib.Path:
    """Build a minimal bundle that looks like a freshly-cloned plan_foundry repo."""
    bundle = root / ".plan-foundry-tmp"
    bundle.mkdir()
    claude = bundle / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "Operating rule A\nOperating rule B\n", encoding="utf-8"
    )
    (claude / "skills" / "_shared").mkdir(parents=True)
    _shared_src = pathlib.Path(__file__).resolve().parents[2] / "_shared"
    (claude / "skills" / "_shared" / "bundle_copy.py").write_text(
        (_shared_src / "bundle_copy.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (claude / "skills" / "_shared" / "merge_settings.py").write_text(
        (_shared_src / "merge_settings.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (claude / "skills" / "_shared" / "bundle-settings.json").write_text(
        (_shared_src / "bundle-settings.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (claude / "agents").mkdir(parents=True)
    (claude / "agents" / "an-agent.md").write_text("agent\n", encoding="utf-8")
    (claude / "commands").mkdir(parents=True)
    (claude / "commands" / "cmd.md").write_text("cmd\n", encoding="utf-8")
    (claude / "hooks").mkdir(parents=True)
    (claude / "hooks" / "hook.json").write_text("{}\n", encoding="utf-8")

    subprocess.run(["git", "init", "--quiet"], cwd=bundle, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=bundle, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bundle, check=True)
    subprocess.run(["git", "add", "-A"], cwd=bundle, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "init"], cwd=bundle, check=True)
    return bundle


def test_install_from_absent_target(tmp_path):
    bundle = _build_fixture_bundle(tmp_path)
    result = run_install.run(tmp_path, bundle)
    assert result["outcome"] == "success", result
    assert result["payload"]["step_results"]["step_2"] == "PASS"
    assert (tmp_path / ".claude" / "skills" / "init-plan-foundry").exists()
    assert (tmp_path / ".claude" / ".plan-foundry-bundle-version").exists()
    assert (tmp_path / "Workbench").exists()
    assert (tmp_path / "Retired").exists()
    assert (tmp_path / "CLAUDE.md").exists()
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "plan-foundry:init-plan-foundry:start" in text
    assert "Operating rule A" in text
    # Bundle dir should have been removed (it was at .plan-foundry-tmp/)
    assert not bundle.exists()


def test_install_refuses_in_bundle_source(tmp_path):
    bundle = _build_fixture_bundle(tmp_path)
    # Rename target dir to "plan_foundry" to trigger bundle-source detection.
    source = tmp_path.parent / "plan_foundry"
    if source.exists():
        pytest.skip("collision with real plan_foundry dir; rerun in isolated tmp")
    result = run_install.run(
        target_root=pathlib.Path("/tmp/plan_foundry") if sys.platform != "win32" else pathlib.Path("C:/plan_foundry"),
        bundle_path=bundle,
    )
    # We patched the target_root to a path whose basename is plan_foundry.
    assert result["outcome"] == "exception"
    assert "bundle-source-init-refused" in str(result["diagnostics"])


def test_install_idempotent(tmp_path):
    bundle = _build_fixture_bundle(tmp_path)
    run_install.run(tmp_path, bundle)
    # Rebuild bundle for second run (first run consumed it)
    bundle = _build_fixture_bundle(tmp_path)
    result = run_install.run(tmp_path, bundle)
    assert result["outcome"] == "success", result
    # CLAUDE.md should report "already current" or "replaced-block" — both fine
    diag_text = " ".join(str(d) for d in result["diagnostics"])
    assert "CLAUDE.md:" in diag_text


def test_install_appends_gitignore(tmp_path):
    bundle = _build_fixture_bundle(tmp_path)
    (tmp_path / ".gitignore").write_text("node_modules/\n*.log\n", encoding="utf-8")
    run_install.run(tmp_path, bundle)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert "node_modules/" in gi
    assert "*.log" in gi
    assert ".claude/skills/" in gi
    assert ".plan-foundry-tmp/" in gi


def test_install_preserves_existing_claude_md(tmp_path):
    bundle = _build_fixture_bundle(tmp_path)
    (tmp_path / "CLAUDE.md").write_text(
        "# My project\n\nWorking notes here.\n", encoding="utf-8"
    )
    run_install.run(tmp_path, bundle)
    text = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "My project" in text
    assert "Working notes here" in text
    assert "plan-foundry:init-plan-foundry:start" in text


def test_install_adds_askuserquestion_deny(tmp_path):
    """After install, target settings.json must have AskUserQuestion in permissions.deny."""
    import json

    bundle = _build_fixture_bundle(tmp_path)
    result = run_install.run(tmp_path, bundle)
    assert result["outcome"] == "success", result

    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists(), "settings.json was not created"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "AskUserQuestion" in settings.get("permissions", {}).get("deny", [])


def test_install_settings_merge_preserves_consumer_entries(tmp_path):
    """Consumer's own allow/deny entries and hooks must survive the settings merge."""
    import json

    bundle = _build_fixture_bundle(tmp_path)

    # Pre-seed a target settings.json with consumer-specific entries.
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    pre_settings = {
        "permissions": {
            "allow": ["Bash(git *)"],
            "deny": ["SomeTool"],
        },
        "hooks": {
            "PostToolUse": [{"type": "command", "command": "my-hook"}]
        },
    }
    settings_path = tmp_path / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(pre_settings, indent=2) + "\n", encoding="utf-8")

    result = run_install.run(tmp_path, bundle)
    assert result["outcome"] == "success", result

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    deny = settings.get("permissions", {}).get("deny", [])
    allow = settings.get("permissions", {}).get("allow", [])
    # Bundle deny merged in
    assert "AskUserQuestion" in deny
    # Consumer deny preserved
    assert "SomeTool" in deny
    # Consumer allow preserved
    assert "Bash(git *)" in allow
    # Consumer hooks preserved
    assert settings.get("hooks", {}).get("PostToolUse", [{}])[0].get("command") == "my-hook"
