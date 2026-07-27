"""Integration tests for plan-foundry-sync (AC6 model).

clone_bundle is monkeypatched to a pre-built fixture bundle so tests
do not hit the network. The fixture is a real on-disk git repo that
sync's bundle_copy + write_version_file can read.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

_SYNC_LIB = pathlib.Path(__file__).resolve().parent
_SHARED = _SYNC_LIB.parent.parent / "_shared"  # .claude/skills/_shared
sys.path.insert(0, str(_SYNC_LIB))
sys.path.insert(0, str(_SHARED))

import sync as sync_mod  # noqa: E402


_REAL_SHARED = _SYNC_LIB.parent.parent / "_shared"  # .claude/skills/_shared (real)


def _init_git_bundle(root: pathlib.Path) -> pathlib.Path:
    """Build a fixture bundle (real git repo) suitable for sync's helpers.

    This is a post-AH2 bundle: it contains merge_settings.py and
    bundle-settings.json in _shared/.
    """
    bundle_root = root / "fixture-bundle"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    (claude / "skills" / "_shared").mkdir(parents=True)
    (claude / "skills" / "_shared" / "bundle_copy.py").write_text(
        (_REAL_SHARED / "bundle_copy.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Post-AH2: include merge helpers in the bundle
    (claude / "skills" / "_shared" / "merge_settings.py").write_text(
        (_REAL_SHARED / "merge_settings.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (claude / "skills" / "_shared" / "bundle-settings.json").write_text(
        (_REAL_SHARED / "bundle-settings.json").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (claude / "agents").mkdir(parents=True)
    (claude / "agents" / "an-agent.md").write_text("agent body\n")
    (claude / "commands").mkdir(parents=True)
    (claude / "commands" / "cmd.md").write_text("cmd body\n")
    (claude / "hooks").mkdir(parents=True)
    (claude / "hooks" / "hook.json").write_text("{}\n")

    subprocess.run(["git", "init", "--quiet"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=bundle_root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bundle_root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"], cwd=bundle_root, check=True
    )
    return bundle_root


def _init_git_bundle_pre_ah2(root: pathlib.Path) -> pathlib.Path:
    """Build a pre-AH2 fixture bundle - no merge_settings.py in _shared/.

    Used to simulate a target that was installed before AH2 shipped.
    The _shared/ only has bundle_copy.py (no merge_settings, no bundle-settings.json).
    """
    bundle_root = root / "fixture-bundle-pre-ah2"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    (claude / "skills" / "_shared").mkdir(parents=True)
    (claude / "skills" / "_shared" / "bundle_copy.py").write_text(
        (_REAL_SHARED / "bundle_copy.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Deliberately NO merge_settings.py or bundle-settings.json - pre-AH2 install
    (claude / "agents").mkdir(parents=True)
    (claude / "agents" / "an-agent.md").write_text("agent body\n")
    (claude / "commands").mkdir(parents=True)
    (claude / "commands" / "cmd.md").write_text("cmd body\n")
    (claude / "hooks").mkdir(parents=True)
    (claude / "hooks" / "hook.json").write_text("{}\n")

    subprocess.run(["git", "init", "--quiet"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=bundle_root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bundle_root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "pre-ah2 init"], cwd=bundle_root, check=True
    )
    return bundle_root


def _init_target_via_copy(bundle_root: pathlib.Path, target_root: pathlib.Path):
    """Simulate having previously run /init-plan-foundry."""
    sys.path.insert(0, str(bundle_root / ".claude" / "skills" / "_shared"))
    import bundle_copy

    target_claude = target_root / ".claude"
    bundle_copy.copy_bundle_managed(bundle_root / ".claude", target_claude)
    bundle_copy.write_version_file(bundle_root, target_claude)


@pytest.fixture
def patched_clone(monkeypatch, tmp_path):
    """Replace clone_bundle with a function that 'clones' from a fixture path."""
    bundle_root = _init_git_bundle(tmp_path)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()  # ensure bundle_fetch is sys.path-visible
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    return bundle_root


def test_sync_success_when_bundle_advances(patched_clone, tmp_path: pathlib.Path):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    new_file = bundle_root / ".claude" / "skills" / "new-skill" / "SKILL.md"
    new_file.parent.mkdir(parents=True)
    new_file.write_text("new skill body\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "add new-skill"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert "skills/new-skill/SKILL.md" in result["payload"]["files_copied"]
    assert (target / ".claude" / "skills" / "new-skill" / "SKILL.md").exists()
    assert result["payload"]["previous_sha"] != result["payload"]["new_sha"]
    assert not (target / ".plan-foundry-tmp").exists(), "tmp clone must be cleaned up"


def test_sync_refuses_when_claude_is_symlink(patched_clone, tmp_path: pathlib.Path):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    target_claude = target / ".claude"
    try:
        target_claude.symlink_to(bundle_root / ".claude", target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported on this platform/permission level")
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert "symlink" in result["summary"].lower()


def test_sync_refuses_when_version_file_absent(patched_clone, tmp_path: pathlib.Path):
    target = tmp_path / "target"
    (target / ".claude" / "skills").mkdir(parents=True)
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert "bundle-version" in result["summary"] or "version" in result["summary"]


def test_sync_refuses_when_claude_absent(patched_clone, tmp_path: pathlib.Path):
    target = tmp_path / "target"
    target.mkdir()
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert ".claude" in result["summary"]


def test_sync_preserves_project_additions(patched_clone, tmp_path: pathlib.Path):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    project_skill = target / ".claude" / "skills" / "myproj" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("project skill\n")

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert "skills/myproj/SKILL.md" in result["payload"]["project_additions"]
    assert project_skill.exists()
    assert not (target / ".plan-foundry-tmp").exists()


def test_sync_refreshes_claude_md_block_and_preserves_host_content(
    patched_clone, tmp_path: pathlib.Path
):
    """Behavioural acceptance: sync replaces a stale sentinel block while preserving all
    host-authored content above, below, and in separate sections around the block (S101/S601).

    The fixture bundle's operating-rules.md contains "operating rules\\n" (the text written
    by _init_git_bundle). The host CLAUDE.md is seeded with that text already replaced by
    stale text so the refresh is observable.
    """
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    # Import the shared helper to build a stale block using recognisably different text.
    # Use the installed _shared (already on sys.path via _SHARED above), not the fixture bundle's
    # _shared (which only contains bundle_copy.py).
    import claude_md_block  # noqa: E402 - on sys.path via _SHARED insertion at module top

    stale_rules = "# STALE operating rules\n\nThis text should be replaced by sync.\n"
    bundle_rules = "operating rules\n"  # matches what _init_git_bundle writes

    stale_block = claude_md_block.build_block(stale_rules)

    # Seed a host CLAUDE.md with substantial multi-section content around the stale block.
    host_above = "# Project\n\nThis is the project description.\n\n## Working style\n\nKeep it clean.\n\n"
    host_below = "\n## Caveats\n\nSome important caveats here.\n"
    host_content = host_above + stale_block + host_below
    (target / "CLAUDE.md").write_text(host_content, encoding="utf-8")

    result = sync_mod.sync(target)

    assert result["outcome"] == "success", result["summary"]

    # (a) All hand-authored sections survive verbatim.
    final = (target / "CLAUDE.md").read_text(encoding="utf-8")
    assert "# Project" in final
    assert "This is the project description." in final
    assert "## Working style" in final
    assert "Keep it clean." in final
    assert "## Caveats" in final
    assert "Some important caveats here." in final

    # (b) Block body has been refreshed to the bundle's operating-rules text.
    assert bundle_rules.strip() in final
    assert "STALE operating rules" not in final
    assert "This text should be replaced by sync." not in final

    # (c) Payload and summary assertions.
    assert result["payload"]["claude_md"]["status"] in ("PASS", "SKIPPED")
    assert "CLAUDE.md" in result["summary"]


def test_sync_malformed_markers_fail_non_destructive(
    patched_clone, tmp_path: pathlib.Path
):
    """Malformed sentinel markers: sync sets outcome=exception and leaves CLAUDE.md untouched (D5/S102)."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    import claude_md_block  # noqa: E402 - on sys.path via _SHARED insertion at module top

    # End marker appears before start marker - malformed.
    bad_content = (
        "# My project\n\n"
        f"{claude_md_block.SENTINEL_END}\nsome content\n{claude_md_block.SENTINEL_START}\n"
    )
    (target / "CLAUDE.md").write_text(bad_content, encoding="utf-8")
    original_bytes = (target / "CLAUDE.md").read_bytes()

    result = sync_mod.sync(target)

    # outcome is exception due to FAIL on CLAUDE.md.
    assert result["outcome"] == "exception", result["summary"]

    # CLAUDE.md is byte-for-byte unchanged (non-destructive per D5).
    assert (target / "CLAUDE.md").read_bytes() == original_bytes

    # Payload records the FAIL status.
    assert result["payload"]["claude_md"]["status"] == "FAIL"


def test_sync_reports_clone_failure(monkeypatch, tmp_path: pathlib.Path):
    """If clone_bundle raises, sync surfaces the error and returns exception."""
    target = tmp_path / "target"
    target.mkdir()
    # Pre-populate target so we get past the version-file check.
    bundle_root = _init_git_bundle(tmp_path)
    _init_target_via_copy(bundle_root, target)

    sync_mod._import_local_helpers()
    import bundle_fetch

    def fake_clone(target_root, ref="main"):
        raise bundle_fetch.BundleFetchError("network unreachable")

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    result = sync_mod.sync(target)
    assert result["outcome"] == "exception"
    assert "network unreachable" in result["summary"]


# ---------------------------------------------------------------------------
# AH2: settings merge tests
# ---------------------------------------------------------------------------

def test_sync_adds_askuserquestion_deny(patched_clone, tmp_path: pathlib.Path):
    """After sync, target settings.json must contain AskUserQuestion in deny."""
    import json

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]

    settings_path = target / ".claude" / "settings.json"
    assert settings_path.exists(), "settings.json was not created by sync"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    deny = settings.get("permissions", {}).get("deny", [])
    assert "AskUserQuestion" in deny


def test_sync_pre_ah2_target_no_merge_settings_in_installed_shared(
    monkeypatch, tmp_path: pathlib.Path
):
    """Key bootstrap trap: target was installed from a pre-AH2 bundle (no merge_settings.py
    in target's installed _shared/). The fresh-clone bundle DOES have merge_settings.py.
    sync must load the helper from the fresh bundle, not the target's stale _shared/.

    If sync wrongly tries to import from the target's _shared/ (via _import_local_helpers),
    it would raise ImportError. This test verifies no ImportError and that the deny lands.
    """
    import json

    # Build the pre-AH2 bundle for initial target setup.
    pre_ah2_bundle = _init_git_bundle_pre_ah2(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(pre_ah2_bundle, target)

    # Verify the target's installed _shared/ does NOT have merge_settings.py.
    installed_merge = target / ".claude" / "skills" / "_shared" / "merge_settings.py"
    assert not installed_merge.exists(), (
        "Pre-AH2 target must NOT have merge_settings.py installed - "
        "pre-seeding it would mask the bootstrap trap"
    )

    # Now build a post-AH2 "fresh clone" that does have merge_settings.py.
    post_ah2_bundle = _init_git_bundle(tmp_path)

    def fake_clone_post_ah2(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(post_ah2_bundle, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone_post_ah2)

    # Should not raise; should succeed and merge the deny.
    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]

    settings_path = target / ".claude" / "settings.json"
    assert settings_path.exists(), "settings.json was not created"
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    deny = settings.get("permissions", {}).get("deny", [])
    assert "AskUserQuestion" in deny


def test_sync_settings_merge_preserves_consumer_entries(
    patched_clone, tmp_path: pathlib.Path
):
    """Consumer's own allow/deny entries and hooks must survive the settings merge."""
    import json

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    # Pre-seed consumer settings.
    settings_path = target / ".claude" / "settings.json"
    pre_settings = {
        "permissions": {
            "allow": ["Bash(git *)"],
            "deny": ["ConsumerTool"],
        },
        "hooks": {"PostToolUse": [{"type": "command", "command": "consumer-hook"}]},
    }
    settings_path.write_text(json.dumps(pre_settings, indent=2) + "\n", encoding="utf-8")

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    deny = settings.get("permissions", {}).get("deny", [])
    allow = settings.get("permissions", {}).get("allow", [])
    assert "AskUserQuestion" in deny
    assert "ConsumerTool" in deny
    assert "Bash(git *)" in allow
    assert settings.get("hooks", {}).get("PostToolUse", [{}])[0].get("command") == "consumer-hook"
