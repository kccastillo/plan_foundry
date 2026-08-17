"""Integration tests for plan-foundry-sync (AC6 model).

clone_bundle is monkeypatched to a pre-built fixture bundle so tests
do not hit the network. The fixture is a real on-disk git repo that
sync's bundle_copy + write_version_file can read.
"""

from __future__ import annotations

import json
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


@pytest.fixture(autouse=True)
def _restore_sys_path():
    """Undo per-test sys.path inserts before the next module runs.

    Several helpers below insert a fixture bundle's own `_shared/` at the
    front of sys.path and never remove it. Those entries outlive this module
    and carry a `preflight.py`, which silently satisfies the deliberate
    `pytest.raises(ImportError)` sanity guard in
    _shared/lib/test_preflight.py::test_preflight_resolves_from_clone_not_installed_copy.
    That test then passes without exercising what it claims to test.

    CI does not catch it because run-all.sh runs each test file in its own
    process; it appears only when the two files share one. Fixed here rather
    than by weakening the guard, because the guard is the point (PLAN-AJ6,
    found while running the suites together).
    """
    snapshot = list(sys.path)
    try:
        yield
    finally:
        sys.path[:] = snapshot


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


def _init_git_bundle_ah8(root: pathlib.Path, schema_version=2) -> pathlib.Path:
    """Build a fixture bundle whose _shared/ carries the PLAN-AH8 pre-flight
    surface: preflight.py and bundle-contract.json, alongside the post-AH2
    helpers _init_git_bundle already provides. Used by the pre-flight tests
    below, which need `import preflight` to resolve to real code (not
    ImportError-skip) so the version-step comparison actually runs.
    """
    bundle_root = root / "fixture-bundle-ah8"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    shared_dir = claude / "skills" / "_shared"
    shared_dir.mkdir(parents=True)
    for fname in (
        "bundle_copy.py",
        "merge_settings.py",
        "bundle-settings.json",
        "preflight.py",
        "bundle_semver.py",
    ):
        src = _REAL_SHARED / fname
        if src.exists():
            (shared_dir / fname).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    (shared_dir / "bundle-contract.json").write_text(
        '{"schema_version": %r, "deprecations": []}' % (schema_version,),
        encoding="utf-8",
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
        ["git", "commit", "--quiet", "-m", "ah8 init"], cwd=bundle_root, check=True
    )
    return bundle_root


@pytest.fixture
def patched_clone_ah8(monkeypatch, tmp_path):
    """Like patched_clone, but the fixture bundle carries preflight.py and
    bundle-contract.json so the PLAN-AH8 pre-flight actually runs instead of
    ImportError-skipping."""
    bundle_root = _init_git_bundle_ah8(tmp_path)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
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


def test_sync_leaves_writing_style_supplement_untouched(
    patched_clone, tmp_path: pathlib.Path
):
    """FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1715: a project's
    .claude/writing-style-local.md sits outside the four bundle-managed
    dirs, so sync must not touch it, exactly like any other project-local
    .claude/ file."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    supplement = target / ".claude" / "writing-style-local.md"
    supplement.write_text(
        "## Additional banned words or phrases\n- utilise\n", encoding="utf-8"
    )

    result = sync_mod.sync(target)

    assert result["outcome"] == "success", result["summary"]
    assert supplement.read_text(encoding="utf-8") == (
        "## Additional banned words or phrases\n- utilise\n"
    )


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


# ---------------------------------------------------------------------------
# PLAN-AH7: receipt-backed quarantine, wired end to end through sync().
# ---------------------------------------------------------------------------


def test_existing_consumer_converges_across_two_new_code_syncs(
    patched_clone, tmp_path: pathlib.Path
):
    """A-7: an existing consumer converges across two syncs of the new code,
    and the crossing sync itself is not one of them.

    Counted from the consumer's side this is the THIRD sync, not the second.
    The crossing sync is executed by the consumer's already-installed
    (pre-AH7) sync.py, which has no read_receipt/classify/quarantine/
    write_receipt calls at all - running it would leave exactly the state
    `_init_target_via_copy` below produces (files present, version pin
    refreshed, no receipt on disk). That state stands in for the crossing
    sync here; only the two `sync_mod.sync()` calls that follow run the code
    this PLAN ships.
    """
    import bundle_copy

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    target_claude = target / ".claude"

    # Stands in for "the crossing sync": consumer installed pre-AH7 - files
    # on disk, version pin written, no receipt.
    _init_target_via_copy(bundle_root, target)
    assert bundle_copy.read_receipt(target_claude) is None

    # Sync #1 running the NEW code: receipt absent -> quarantines nothing,
    # but writes the first receipt (the bootstrap rule - absent must not
    # read as clean).
    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]
    assert result1["payload"]["quarantine"]["receipt_absent"] is True
    assert result1["payload"]["quarantine"]["gone_upstream_quarantined"] == []
    receipt1 = bundle_copy.read_receipt(target_claude)
    assert receipt1 is not None

    # Bundle drops a file between sync #1 and sync #2.
    dropped = bundle_root / ".claude" / "agents" / "an-agent.md"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop an-agent"], cwd=bundle_root, check=True
    )

    # Sync #2 running the NEW code: receipt from sync #1 now lets the
    # dropped file be correctly identified as gone_upstream and quarantined.
    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    assert result2["payload"]["quarantine"]["receipt_absent"] is False
    gone = [
        e["path"] for e in result2["payload"]["quarantine"]["gone_upstream_quarantined"]
    ]
    assert "agents/an-agent.md" in gone
    assert not (target_claude / "agents" / "an-agent.md").exists()
    quarantine_root = target_claude / bundle_copy.QUARANTINE_DIRNAME
    found = list(quarantine_root.glob("*/agents/an-agent.md"))
    assert len(found) == 1


def test_install_sync_uninstall_trio_converges(patched_clone, tmp_path: pathlib.Path):
    """A-8: the install -> sync -> uninstall trio still converges end to end,
    including the receipt and the quarantine tree (PLAN-AH7 Step 13 -
    uninstall previously knew neither and would leave both behind)."""
    import bundle_copy

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    target_claude = target / ".claude"

    # "Install": mirrors run_install.py's Step 2 (copy + version pin + receipt).
    report = bundle_copy.copy_bundle_managed(bundle_root / ".claude", target_claude)
    version = bundle_copy.write_version_file(bundle_root, target_claude)
    bundle_copy.write_receipt(
        target_claude, report.files_copied + report.files_unchanged, version["sha"]
    )
    assert bundle_copy.read_receipt(target_claude) is not None

    # "Sync": run the real sync once to establish a clean baseline.
    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]

    # Drop a bundle file and sync again so a quarantine directory is left
    # behind - the interesting case for uninstall to clean up.
    dropped = bundle_root / ".claude" / "commands" / "cmd.md"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "drop cmd"], cwd=bundle_root, check=True)
    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    quarantine_dir = target_claude / bundle_copy.QUARANTINE_DIRNAME
    assert quarantine_dir.exists() and any(quarantine_dir.iterdir())

    # "Uninstall": run the uninstall module against the target.
    uninstall_lib = _SYNC_LIB.parent.parent / "plan-foundry-uninstall" / "lib"
    if str(uninstall_lib) not in sys.path:
        sys.path.insert(0, str(uninstall_lib))
    import uninstall as uninstall_mod

    uresult = uninstall_mod.uninstall(target)
    assert uresult["outcome"] == "success"
    assert not (target_claude / "skills").exists()
    assert not (target_claude / bundle_copy.RECEIPT_FILENAME).exists()
    assert not quarantine_dir.exists()


# ---------------------------------------------------------------------------
# PLAN-AH8: pre-flight - the pre-sync break signal read from the clone, and
# in-flight PLAN protection.
# ---------------------------------------------------------------------------


def test_pin_predating_contract_warns_and_continues(
    patched_clone_ah8, tmp_path: pathlib.Path
):
    """A-6: a pin predating schema_version warns and continues. The crossing
    sync that installs this very protection must not be blocked by it, even
    when a PLAN happens to be in flight at the same time - pin_predates_contract
    never triggers the halt condition, which is gated on major_step."""
    target = tmp_path / "target"
    target.mkdir()
    target_claude = target / ".claude"
    target_claude.mkdir(parents=True)
    # A pre-AH8 pin - no schema_version key at all.
    (target_claude / ".plan-foundry-bundle-version").write_text(
        "sha=" + "a" * 40 + "\ntag=v1.0.0\nsynced=2026-01-01T00:00:00Z\n",
        encoding="utf-8",
    )
    workbench = target / "Workbench"
    workbench.mkdir()
    (workbench / "PLAN-INFLIGHT.md").write_text(
        '---\npipeline_phase: "executing"\n---\n\nbody\n', encoding="utf-8"
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert not (target / ".plan-foundry-tmp").exists()


def test_major_crossing_halts_and_allow_in_flight_overrides(
    patched_clone_ah8, tmp_path: pathlib.Path
):
    """A-7: a major crossing with an in-flight PLAN halts and names it;
    --allow-in-flight overrides."""
    bundle_root = patched_clone_ah8
    subprocess.run(["git", "tag", "v2.0.0"], cwd=bundle_root, check=True)

    target = tmp_path / "target"
    target.mkdir()
    target_claude = target / ".claude"
    target_claude.mkdir(parents=True)
    (target_claude / ".plan-foundry-bundle-version").write_text(
        "sha=" + "a" * 40 + "\ntag=v1.0.0\nsynced=2026-01-01T00:00:00Z\nschema_version=2\n",
        encoding="utf-8",
    )
    workbench = target / "Workbench"
    workbench.mkdir()
    (workbench / "PLAN-INFLIGHT.md").write_text(
        '---\npipeline_phase: "executing"\n---\n\nbody\n', encoding="utf-8"
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "blocked", result
    assert "Workbench/PLAN-INFLIGHT.md" in result["payload"]["in_flight_plans"]
    assert result["payload"]["blocked_reason"]
    assert not (target / ".plan-foundry-tmp").exists()

    # The pin is untouched by a blocked sync (it halted before
    # write_version_file), so the same major-crossing pin is still in
    # place. --allow-in-flight overrides the halt this time.
    result2 = sync_mod.sync(target, allow_in_flight=True)
    assert result2["outcome"] == "success", result2["summary"]
    assert not (target / ".plan-foundry-tmp").exists()


# ---------------------------------------------------------------------------
# PLAN-AH9: deprecation ledger cross-reference, shim-then-delete surfacing,
# dangling hook registrations, and the ledger-read degradation guard.
# ---------------------------------------------------------------------------


def _init_git_bundle_ah9(root: pathlib.Path, deprecations: list) -> pathlib.Path:
    """Like _init_git_bundle_ah8, but bundle-contract.json carries the given
    deprecations list instead of an empty array, so sync's Step 5 ledger
    cross-reference has something to match against."""
    bundle_root = root / "fixture-bundle-ah9"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    shared_dir = claude / "skills" / "_shared"
    shared_dir.mkdir(parents=True)
    for fname in (
        "bundle_copy.py",
        "merge_settings.py",
        "bundle-settings.json",
        "preflight.py",
        "bundle_semver.py",
    ):
        src = _REAL_SHARED / fname
        if src.exists():
            (shared_dir / fname).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    (shared_dir / "bundle-contract.json").write_text(
        json.dumps({"schema_version": 2, "deprecations": deprecations}),
        encoding="utf-8",
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
        ["git", "commit", "--quiet", "-m", "ah9 init"], cwd=bundle_root, check=True
    )
    return bundle_root


def _patched_clone_ah9(monkeypatch, tmp_path, deprecations):
    bundle_root = _init_git_bundle_ah9(tmp_path, deprecations)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    return bundle_root


def test_ledger_matched_quarantine_reports_replacement(monkeypatch, tmp_path: pathlib.Path):
    """A-3: a quarantined path carrying a ledger entry reports replaced_by
    and note, not a bare path. This is guarantee 4's acceptance coverage."""
    deprecations = [
        {
            "path": "agents/an-agent.md",
            "since": "v1.0.0",
            "removed_in": "v2.0.0",
            "replaced_by": "new-agent",
            "note": "superseded by new-agent",
            "kind": "reference",
        }
    ]
    bundle_root = _patched_clone_ah9(monkeypatch, tmp_path, deprecations)
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    # Sync #1: establishes the receipt.
    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]

    # Bundle drops the deprecated agent between sync #1 and sync #2.
    dropped = bundle_root / ".claude" / "agents" / "an-agent.md"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop deprecated agent"],
        cwd=bundle_root,
        check=True,
    )

    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    quarantined = result2["payload"]["quarantine"]["gone_upstream_quarantined"]
    match = [e for e in quarantined if e["path"] == "agents/an-agent.md"]
    assert len(match) == 1, quarantined
    assert match[0]["replaced_by"] == "new-agent"
    assert match[0]["note"] == "superseded by new-agent"


def test_helper_kind_entry_not_quarantine_matched(monkeypatch, tmp_path: pathlib.Path):
    """A-7: a kind: helper ledger entry is never quarantine-matched, even
    when its `path` string happens to equal a quarantined file path -
    kind: helper entries are never offered to the matcher at all."""
    deprecations = [
        {
            "path": "agents/an-agent.md",
            "since": "v1.0.0",
            "removed_in": "v2.0.0",
            "replaced_by": "new-agent",
            "note": "superseded by new-agent",
            "kind": "helper",
        }
    ]
    bundle_root = _patched_clone_ah9(monkeypatch, tmp_path, deprecations)
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]

    dropped = bundle_root / ".claude" / "agents" / "an-agent.md"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop agent"], cwd=bundle_root, check=True
    )

    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    quarantined = result2["payload"]["quarantine"]["gone_upstream_quarantined"]
    match = [e for e in quarantined if e["path"] == "agents/an-agent.md"]
    assert len(match) == 1, quarantined
    assert "replaced_by" not in match[0]
    assert "note" not in match[0]


def test_quarantined_hook_flagged_as_dangling_registration(
    monkeypatch, tmp_path: pathlib.Path
):
    """A-4: a quarantined hook still registered in settings.json is flagged
    as a dangling registration."""
    bundle_root = _patched_clone_ah9(monkeypatch, tmp_path, [])
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    settings_path = target / ".claude" / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"type": "command", "command": "python3 .claude/hooks/hook.json"}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]

    dropped = bundle_root / ".claude" / "hooks" / "hook.json"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop hook"], cwd=bundle_root, check=True
    )

    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    assert "hooks/hook.json" in result2["payload"]["dangling_hook_registrations"]


def test_ordinary_quarantined_hook_registration_structurally_removed(
    monkeypatch, tmp_path: pathlib.Path
):
    """PLAN-AK8 D1: a hook dropped via the ordinary (non-legacy) quarantine
    path has its settings.json registration structurally removed - not
    merely flagged - while a sibling hook the bundle still ships survives
    untouched."""
    bundle_root = _patched_clone_ah9(monkeypatch, tmp_path, [])

    # A second hook file the bundle keeps shipping, alongside the existing
    # hooks/hook.json this fixture bundle already ships.
    (bundle_root / ".claude" / "hooks" / "kept-hook.json").write_text(
        "{}\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "add kept hook"], cwd=bundle_root, check=True
    )

    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    settings_path = target / ".claude" / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"type": "command", "command": "python3 .claude/hooks/hook.json"},
                        {"type": "command", "command": "python3 .claude/hooks/kept-hook.json"},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]

    dropped = bundle_root / ".claude" / "hooks" / "hook.json"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop hook"], cwd=bundle_root, check=True
    )

    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    removed = result2["payload"]["dangling_hook_entries_removed"]
    assert any("hooks/hook.json" in c for c in removed), removed

    settings = json.loads(
        (target / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    commands = [h["command"] for h in settings["hooks"]["PostToolUse"]]
    assert "python3 .claude/hooks/hook.json" not in commands
    assert "python3 .claude/hooks/kept-hook.json" in commands


def test_settings_local_dangling_registration_reported_not_removed(
    monkeypatch, tmp_path: pathlib.Path
):
    """PLAN-AK8 D2: a hook registration living only in settings.local.json
    (never settings.json) for a path this sync quarantines is reported in
    dangling_hook_registrations_local, and settings.local.json itself is
    left byte-for-byte unmodified - sync must never write that file."""
    bundle_root = _patched_clone_ah9(monkeypatch, tmp_path, [])
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    settings_local_path = target / ".claude" / "settings.local.json"
    settings_local_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {"type": "command", "command": "python3 .claude/hooks/hook.json"}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]

    before_bytes = settings_local_path.read_bytes()

    dropped = bundle_root / ".claude" / "hooks" / "hook.json"
    dropped.unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop hook"], cwd=bundle_root, check=True
    )

    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    assert "hooks/hook.json" in result2["payload"]["dangling_hook_registrations_local"]
    assert settings_local_path.read_bytes() == before_bytes


def test_settings_local_legacy_foundry_log_registration_reported(
    patched_clone, tmp_path: pathlib.Path
):
    """PLAN-AK8 D2: the historical foundry-log incident, replayed with the
    registration in settings.local.json instead of settings.json - covered
    by the same read-only local check, via LEGACY_ORPHAN_HOOK_MARKERS."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    _seed_legacy_foundry_log(target_claude)

    settings_local_path = target_claude / "settings.local.json"
    settings_local_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PostToolUse": [
                        {
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "python3 .claude/hooks/foundry-log.py",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    before_bytes = settings_local_path.read_bytes()

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    local_hits = result["payload"]["dangling_hook_registrations_local"]
    assert any("foundry-log.py" in m for m in local_hits), local_hits
    assert settings_local_path.read_bytes() == before_bytes


def test_ledger_unavailable_ref_predates_ah8(monkeypatch, tmp_path: pathlib.Path):
    """A-8 (first case): a --ref predating AH8 has no preflight module in
    the clone at all. Seeded via sys.modules, per the required mechanism -
    shaping a fixture bundle without preflight.py cannot produce this case,
    because test_sync.py:19 already put the real _shared/ on sys.path at
    module import time, so `import preflight` inside sync() would resolve
    the repo's own (post-AH9) module regardless of what the fixture bundle
    contains."""
    bundle_root = _init_git_bundle(tmp_path)  # pre-AH8 fixture (no preflight.py)
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    monkeypatch.setitem(sys.modules, "preflight", None)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"]["quarantine"]["ledger_unavailable"] == (
        "preflight module absent (ref predates AH8)"
    )
    assert any(
        "ledger_unavailable=preflight module absent (ref predates AH8)" in d
        for d in result["diagnostics"]
        if isinstance(d, str)
    )


def test_ledger_unavailable_ref_between_ah8_and_ah9(monkeypatch, tmp_path: pathlib.Path):
    """A-8 (second case): a --ref between AH8 and AH9 has preflight present
    but no read_deprecations attribute. Built as a stub module carrying
    only AH8's surface (compare_against_clone, scan_in_flight_plans), so
    getattr(preflight, "read_deprecations", None) resolves to None without
    raising."""
    bundle_root = tmp_path / "fixture-bundle-ah8-stub"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    shared_dir = claude / "skills" / "_shared"
    shared_dir.mkdir(parents=True)
    for fname in ("bundle_copy.py", "merge_settings.py", "bundle-settings.json"):
        src = _REAL_SHARED / fname
        (shared_dir / fname).write_text(
            src.read_text(encoding="utf-8"), encoding="utf-8"
        )
    # A stub preflight.py carrying only the AH8 surface - no
    # read_deprecations, simulating a --ref between AH8 and AH9.
    (shared_dir / "preflight.py").write_text(
        "from __future__ import annotations\n\n\n"
        "def compare_against_clone(target_claude, bundle_path):\n"
        "    return \"same\"\n\n\n"
        "def scan_in_flight_plans(target_root):\n"
        "    return []\n",
        encoding="utf-8",
    )
    (shared_dir / "bundle-contract.json").write_text(
        json.dumps({"schema_version": 2, "deprecations": []}), encoding="utf-8"
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
        ["git", "commit", "--quiet", "-m", "ah8-stub init"], cwd=bundle_root, check=True
    )

    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)
    # Force re-resolution against this fixture's stub module rather than
    # whatever is already cached in sys.modules from an earlier test in
    # this same pytest process (test_deprecation.py, or the AH9 tests
    # above, both import the real post-AH9 preflight).
    monkeypatch.delitem(sys.modules, "preflight", raising=False)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"]["quarantine"]["ledger_unavailable"] == (
        "preflight present, read_deprecations absent (ref between AH8 and AH9)"
    )


# ---------------------------------------------------------------------------
# Bundle identity: a sibling bundle installed at .claude/skills/_shared/.
#
# Two bundles descended from the same lineage ship helpers at the same path.
# Whichever synced last owns the directory, and sync.py binds bundle_copy,
# bundle_fetch and claude_md_block from it before the clone - so the foreign
# copy is what every later import in the process resolves to. Raised from
# paper_trail_dev, 2026-08-04.
# ---------------------------------------------------------------------------


def _write_contract(shared: pathlib.Path, body: str) -> None:
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "bundle-contract.json").write_text(body, encoding="utf-8")


def test_identity_reads_bundle_field(tmp_path: pathlib.Path):
    shared = tmp_path / "_shared"
    _write_contract(shared, '{"schema_version": 2, "bundle": "paper_trail"}')
    assert sync_mod.installed_bundle_identity(shared) == "paper_trail"


def test_identity_is_none_when_contract_absent(tmp_path: pathlib.Path):
    assert sync_mod.installed_bundle_identity(tmp_path / "nope") is None


def test_identity_is_none_when_field_absent(tmp_path: pathlib.Path):
    """The pre-identity state: every consumer installed before the field
    existed reads as None and is trusted, so the check adds no new failure
    mode for the population it is not about."""
    shared = tmp_path / "_shared"
    _write_contract(shared, '{"schema_version": 2, "deprecations": []}')
    assert sync_mod.installed_bundle_identity(shared) is None


def test_identity_is_none_when_contract_malformed(tmp_path: pathlib.Path):
    shared = tmp_path / "_shared"
    _write_contract(shared, "{not json at all")
    assert sync_mod.installed_bundle_identity(shared) is None


def test_this_bundle_declares_its_own_identity():
    """The shipped contract must name the bundle, or every consumer reads as
    pre-identity forever and the check never fires."""
    assert (
        sync_mod.installed_bundle_identity(sync_mod.installed_shared_dir())
        == sync_mod.BUNDLE_IDENTITY
    )


def test_foreign_shared_is_not_trusted_and_sync_still_succeeds(
    monkeypatch, tmp_path: pathlib.Path
):
    """A foreign _shared/ diverts helper loading to the clone, and the sync
    completes rather than crashing on the foreign signature."""
    bundle_root = _init_git_bundle(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    # The installed _shared/ belongs to another bundle.
    foreign = tmp_path / "foreign-shared"
    _write_contract(foreign, '{"schema_version": 2, "bundle": "paper_trail"}')
    monkeypatch.setattr(sync_mod, "installed_shared_dir", lambda: foreign)

    def fake_bootstrap(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    monkeypatch.setattr(sync_mod, "_bootstrap_clone", fake_bootstrap)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    notes = [d for d in result["diagnostics"] if isinstance(d, str) and "identity" in d]
    assert notes, result["diagnostics"]
    assert "paper_trail" in notes[0]
    assert not (target / ".plan-foundry-tmp").exists(), "tmp clone must be cleaned up"


def test_foreign_shared_does_not_clone_twice(monkeypatch, tmp_path: pathlib.Path):
    """The bootstrap clone is reused, not thrown away and re-fetched."""
    bundle_root = _init_git_bundle(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    # Resolve bundle_fetch before the diversion is installed, so this test
    # can count clone_bundle calls without itself taking the divert branch.
    sync_mod._import_local_helpers()
    import bundle_fetch

    foreign = tmp_path / "foreign-shared"
    _write_contract(foreign, '{"schema_version": 2, "bundle": "paper_trail"}')
    monkeypatch.setattr(sync_mod, "installed_shared_dir", lambda: foreign)

    calls = {"bootstrap": 0, "clone": 0}

    def fake_bootstrap(target_root, ref="main"):
        import shutil

        calls["bootstrap"] += 1
        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(bundle_root, tmp)
        return tmp

    monkeypatch.setattr(sync_mod, "_bootstrap_clone", fake_bootstrap)

    def counting_clone(target_root, ref="main"):
        calls["clone"] += 1
        return fake_bootstrap(target_root, ref)

    monkeypatch.setattr(bundle_fetch, "clone_bundle", counting_clone)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert calls == {"bootstrap": 1, "clone": 0}, calls


def test_own_shared_takes_the_ordinary_path(patched_clone, tmp_path: pathlib.Path):
    """No diversion, no diagnostic, when _shared/ is this bundle's."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert not [
        d for d in result["diagnostics"] if isinstance(d, str) and "bundle identity" in d
    ]


def test_modified_gone_upstream_file_is_preserved_not_quarantined(
    patched_clone, tmp_path: pathlib.Path
):
    """A path the receipt records but whose bytes no longer match what we
    wrote belongs to something else now - a sibling bundle that ships the
    same path, or the consumer's own edit. Moving it into
    .claude/.plan-foundry-quarantine/ would be taking someone else's live
    file."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    # Sync #1 establishes the receipt.
    assert sync_mod.sync(target)["outcome"] == "success"

    # The bundle drops the agent; something else rewrites the installed copy.
    (bundle_root / ".claude" / "agents" / "an-agent.md").unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop agent"], cwd=bundle_root, check=True
    )
    installed = target / ".claude" / "agents" / "an-agent.md"
    installed.write_text("another bundle content\n", encoding="utf-8")

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    q = result["payload"]["quarantine"]
    assert [e["path"] for e in q["modified_since_install_preserved"]] == [
        "agents/an-agent.md"
    ]
    assert [e["path"] for e in q["gone_upstream_quarantined"]] == []
    assert installed.exists(), "a file we no longer own must be left in place"
    assert installed.read_text(encoding="utf-8") == "another bundle content\n"


# ---------------------------------------------------------------------------
# Legacy orphan excision: foundry-log (skill + agent + hook) left the bundle
# before the install-receipt substrate existed, so the ordinary receipt-
# backed quarantine path can never reach it (see LEGACY_ORPHAN_DIRS/FILES
# and LEGACY_ORPHAN_HOOK_MARKERS in sync.py). Raised 2026-08-05 against a
# consumer stuck holding it forever; decision recorded in
# Workbench/.foundryreq-sweep/SEED.md - excision, not a shim.
# ---------------------------------------------------------------------------


def _seed_legacy_foundry_log(target_claude: pathlib.Path) -> None:
    skill_dir = target_claude / "skills" / "foundry-log"
    (skill_dir / "references").mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("foundry-log skill body\n", encoding="utf-8")
    (skill_dir / "references" / "log-schema.md").write_text(
        "schema body\n", encoding="utf-8"
    )
    (target_claude / "agents" / "foundry-log-summariser.md").write_text(
        "summariser agent body\n", encoding="utf-8"
    )
    (target_claude / "hooks" / "foundry-log.py").write_text(
        "# legacy hook\n", encoding="utf-8"
    )


def _seed_legacy_hook_registration(target_claude: pathlib.Path, extra: dict = None) -> None:
    settings_path = target_claude / "settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    settings.setdefault("permissions", {}).setdefault("allow", []).append("ConsumerTool")
    settings["hooks"] = {
        "PostToolUse": [
            {
                "hooks": [
                    {"type": "command", "command": "python3 .claude/hooks/foundry-log.py"}
                ]
            },
            {
                "matcher": "Bash",
                "hooks": [
                    {"type": "command", "command": "python3 .claude/hooks/consumer-hook.py"}
                ],
            },
        ]
    }
    if extra:
        settings.update(extra)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")


def test_legacy_orphans_quarantined_and_hook_entry_removed(
    patched_clone, tmp_path: pathlib.Path
):
    """A target holding all three foundry-log artefacts plus a settings.json
    hook registration: sync quarantines the artefacts (not deletes - same
    non-destructive contract as every other removal here) and structurally
    strips the dangling hook entry, while a sibling hook entry and other
    settings content survive untouched."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    _seed_legacy_foundry_log(target_claude)
    _seed_legacy_hook_registration(target_claude)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]

    # Artefacts are gone from the live tree.
    assert not (target_claude / "skills" / "foundry-log").exists()
    assert not (target_claude / "agents" / "foundry-log-summariser.md").exists()
    assert not (target_claude / "hooks" / "foundry-log.py").exists()

    # But recoverable - moved into quarantine, not deleted, same as every
    # other removal path in this module.
    quarantined = result["payload"]["quarantine"]["legacy_orphans_quarantined"]
    assert "skills/foundry-log/SKILL.md" in quarantined
    assert "skills/foundry-log/references/log-schema.md" in quarantined
    assert "agents/foundry-log-summariser.md" in quarantined
    assert "hooks/foundry-log.py" in quarantined
    import bundle_copy

    quarantine_root = target_claude / bundle_copy.QUARANTINE_DIRNAME
    assert list(quarantine_root.glob("*/agents/foundry-log-summariser.md"))

    # settings.json: the foundry-log hook entry is gone.
    settings = json.loads((target_claude / "settings.json").read_text(encoding="utf-8"))
    post_tool_use = settings["hooks"]["PostToolUse"]
    commands = [h["command"] for group in post_tool_use for h in group["hooks"]]
    assert "python3 .claude/hooks/foundry-log.py" not in commands

    # A sibling hook entry and unrelated permissions content survive.
    assert "python3 .claude/hooks/consumer-hook.py" in commands
    assert "ConsumerTool" in settings["permissions"]["allow"]
    assert "AskUserQuestion" in settings["permissions"]["deny"]

    removed = result["payload"]["dangling_hook_entries_removed"]
    assert any("foundry-log.py" in c for c in removed), removed


def test_legacy_orphans_absent_is_a_clean_noop(patched_clone, tmp_path: pathlib.Path):
    """A target that never had foundry-log: sync succeeds and reports
    nothing quarantined and nothing removed from settings.json."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"]["quarantine"]["legacy_orphans_quarantined"] == []
    assert result["payload"]["dangling_hook_entries_removed"] == []


def test_legacy_hook_entry_removed_even_when_human_already_deleted_files(
    patched_clone, tmp_path: pathlib.Path
):
    """A target where a human already deleted the foundry-log files by hand
    but left the settings.json hook entry behind: sync still strips the now-
    dangling registration. Idempotent on a second run."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    _seed_legacy_hook_registration(target_claude)
    # No _seed_legacy_foundry_log call - files never existed / already gone.

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"]["quarantine"]["legacy_orphans_quarantined"] == []
    removed = result["payload"]["dangling_hook_entries_removed"]
    assert any("foundry-log.py" in c for c in removed), removed

    settings = json.loads((target_claude / "settings.json").read_text(encoding="utf-8"))
    commands = [
        h["command"]
        for group in settings.get("hooks", {}).get("PostToolUse", [])
        for h in group["hooks"]
    ]
    assert not any("foundry-log.py" in c for c in commands)
    assert "python3 .claude/hooks/consumer-hook.py" in commands

    # Second sync is a clean no-op - nothing left to remove.
    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    assert result2["payload"]["dangling_hook_entries_removed"] == []


def test_unmodified_gone_upstream_file_is_still_quarantined(
    patched_clone, tmp_path: pathlib.Path
):
    """The ownership check must not disarm quarantine for the case it was
    built for: a dropped file still byte-identical to what we installed."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    assert sync_mod.sync(target)["outcome"] == "success"

    (bundle_root / ".claude" / "agents" / "an-agent.md").unlink()
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "drop agent"], cwd=bundle_root, check=True
    )

    result = sync_mod.sync(target)
    q = result["payload"]["quarantine"]
    assert [e["path"] for e in q["gone_upstream_quarantined"]] == ["agents/an-agent.md"]
    assert q["modified_since_install_preserved"] == []
    assert not (target / ".claude" / "agents" / "an-agent.md").exists()


# ---------------------------------------------------------------------------
# PLAN-AK6: a sync that does not finish leaves a target claiming it did.
#
# Two mechanisms tested here. (1) The handover: sync() re-execs the freshly
# cloned bundle's own sync.py before touching the target, so one generation
# of code performs the whole run - closing the version-skew crash reported
# against the gitignore-convergence call site. (2) Pin-last plus the
# incomplete-sync marker: the version pin is written after the receipt
# rather than after the copy, and a run that starts and does not finish
# leaves a marker naming what it was moving to.
# ---------------------------------------------------------------------------


def _init_git_bundle_stub_sync(root: pathlib.Path, sentinel: str) -> pathlib.Path:
    """Build a fixture bundle whose lib/sync.py is a stub declaring the
    handover flags through argparse - so its --help output carries both
    literals the probe reads - and prints a JSON document carrying
    `sentinel` before exiting zero. Proves the parent hands over and relays
    the child's result without needing the child to be a full sync."""
    bundle_root = root / "fixture-bundle-stub-sync"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    (claude / "skills" / "_shared").mkdir(parents=True)
    (claude / "skills" / "_shared" / "bundle_copy.py").write_text(
        (_REAL_SHARED / "bundle_copy.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    sync_lib_dir = claude / "skills" / "plan-foundry-sync" / "lib"
    sync_lib_dir.mkdir(parents=True)
    (sync_lib_dir / "sync.py").write_text(
        "import argparse, json, sys\n\n\n"
        "def main(argv=None):\n"
        "    parser = argparse.ArgumentParser()\n"
        "    parser.add_argument('--target-root')\n"
        "    parser.add_argument('--ref', default='main')\n"
        "    parser.add_argument('--allow-in-flight', action='store_true')\n"
        "    parser.add_argument('--prefetched-bundle')\n"
        "    parser.add_argument('--no-reexec', action='store_true')\n"
        "    parser.parse_args(argv)\n"
        "    print(json.dumps({\n"
        "        'outcome': 'success',\n"
        f"        'payload': {{'sentinel': {sentinel!r}}},\n"
        "        'summary': 'stub sync ran',\n"
        "        'diagnostics': [],\n"
        "    }))\n"
        "    return 0\n\n\n"
        "if __name__ == '__main__':\n"
        "    sys.exit(main())\n",
        encoding="utf-8",
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
        ["git", "commit", "--quiet", "-m", "stub sync init"], cwd=bundle_root, check=True
    )
    return bundle_root


def _init_git_bundle_arity_crash(root: pathlib.Path) -> pathlib.Path:
    """Build the fixture bundle that reproduces the reported crash: a
    version skew between an in-memory caller and a freshly cloned callee.

    Its lib/sync.py is the repository's own current sync.py, with its
    ensure_gitignore_entries call site edited to unpack four values instead
    of three, matching its own _shared/gitignore_entries.py stub (which
    returns four). The two halves of this fixture bundle are one generation
    and agree with each other; the caller under test stays the repository's
    own three-value sync_mod.sync(), which is the old generation the
    handover (D2) replaces before the crash site is ever reached.

    Its _shared/ also carries bundle_fetch.py and claude_md_block.py
    alongside bundle_copy.py, merge_settings.py and bundle-settings.json,
    because the child - this fixture's own lib/sync.py - resolves those
    three names through its own _import_local_helpers with no ImportError
    guard, and a missing one would exit the child non-zero before the
    arity crash is ever reached.
    """
    bundle_root = root / "fixture-bundle-arity-crash"
    claude = bundle_root / ".claude"
    (claude / "skills" / "init-plan-foundry").mkdir(parents=True)
    (claude / "skills" / "init-plan-foundry" / "operating-rules.md").write_text(
        "operating rules\n"
    )
    shared_dir = claude / "skills" / "_shared"
    shared_dir.mkdir(parents=True)
    for fname in (
        "bundle_copy.py",
        "merge_settings.py",
        "bundle-settings.json",
        "bundle_fetch.py",
        "claude_md_block.py",
    ):
        (shared_dir / fname).write_text(
            (_REAL_SHARED / fname).read_text(encoding="utf-8"), encoding="utf-8"
        )
    # The reported crash's callee: a gitignore_entries.py returning four
    # values from ensure_gitignore_entries.
    (shared_dir / "gitignore_entries.py").write_text(
        "REQUIRED_GITIGNORE_ENTRIES = ()\n\n\n"
        "def ensure_gitignore_entries(target_root, entries=REQUIRED_GITIGNORE_ENTRIES):\n"
        "    return 'SKIPPED', [], [], []\n",
        encoding="utf-8",
    )

    sync_lib_dir = claude / "skills" / "plan-foundry-sync" / "lib"
    sync_lib_dir.mkdir(parents=True)
    real_sync_src = (_SYNC_LIB / "sync.py").read_text(encoding="utf-8")
    three_value_call = (
        "            gi_status, gi_added, gi_skipped_tracked = (\n"
        "                gitignore_entries.ensure_gitignore_entries(target_root)\n"
        "            )\n"
    )
    four_value_call = (
        "            gi_status, gi_added, gi_skipped_tracked, _extra = (\n"
        "                gitignore_entries.ensure_gitignore_entries(target_root)\n"
        "            )\n"
    )
    assert three_value_call in real_sync_src, (
        "sync.py's ensure_gitignore_entries call site text moved - update "
        "this fixture builder's edit to match"
    )
    edited_sync_src = real_sync_src.replace(three_value_call, four_value_call, 1)
    (sync_lib_dir / "sync.py").write_text(edited_sync_src, encoding="utf-8")

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
        ["git", "commit", "--quiet", "-m", "arity crash init"], cwd=bundle_root, check=True
    )
    return bundle_root


def test_sync_hands_over_to_the_cloned_sync_and_relays_its_result(
    monkeypatch, tmp_path: pathlib.Path
):
    ordinary_bundle_root = _init_git_bundle(tmp_path)
    stub_bundle_root = _init_git_bundle_stub_sync(tmp_path, "sentinel-value-123")

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(stub_bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)

    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(ordinary_bundle_root, target)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"].get("sentinel") == "sentinel-value-123"
    assert any(
        "handover" in d for d in result["diagnostics"] if isinstance(d, str)
    ), result["diagnostics"]


def test_sync_survives_a_helper_whose_return_arity_changed(
    monkeypatch, tmp_path: pathlib.Path
):
    """The reported crash: a run whose cloned bundle changed a helper's
    return arity completes instead of raising ValueError."""
    ordinary_bundle_root = _init_git_bundle(tmp_path)
    arity_bundle_root = _init_git_bundle_arity_crash(tmp_path)

    def fake_clone(target_root, ref="main"):
        import shutil

        tmp = pathlib.Path(target_root) / ".plan-foundry-tmp"
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(arity_bundle_root, tmp)
        return tmp

    sync_mod._import_local_helpers()
    import bundle_fetch

    monkeypatch.setattr(bundle_fetch, "clone_bundle", fake_clone)

    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(ordinary_bundle_root, target)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]


def test_sync_falls_back_in_process_when_the_clone_predates_handover(
    patched_clone, tmp_path: pathlib.Path
):
    """_init_git_bundle carries no plan-foundry-sync/lib/sync.py at all, so
    the probe finds neither handover flag and the run falls back to today's
    in-process behaviour - an old ref is no worse off than before this
    PLAN."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert any(
        "predates the handover" in d
        for d in result["diagnostics"]
        if isinstance(d, str)
    ), result["diagnostics"]


def test_sync_does_not_advance_the_pin_when_a_later_step_fails(
    patched_clone, tmp_path: pathlib.Path, monkeypatch
):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    import bundle_copy
    import claude_md_block

    previous_pin = bundle_copy.read_version_file(target_claude)

    def _raise(*args, **kwargs):
        # Must not be OSError: sync.py's call site already wraps
        # apply_operating_rules_block in `except OSError`, which would
        # swallow it, leave the run successful, and leave this test
        # asserting against a run that never failed.
        raise RuntimeError("simulated claude_md failure")

    monkeypatch.setattr(claude_md_block, "apply_operating_rules_block", _raise)

    result = sync_mod.sync(target, no_reexec=True)

    assert result["outcome"] == "exception", result["summary"]
    assert "copy" in result["payload"]["steps_completed"]
    assert "version_pin" not in result["payload"]["steps_completed"]
    pin_after = bundle_copy.read_version_file(target_claude)
    assert pin_after["sha"] == previous_pin["sha"]


def test_sync_leaves_an_incomplete_marker_when_a_later_step_fails(
    patched_clone, tmp_path: pathlib.Path, monkeypatch
):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    import bundle_copy
    import claude_md_block

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated claude_md failure")

    monkeypatch.setattr(claude_md_block, "apply_operating_rules_block", _raise)

    result = sync_mod.sync(target, no_reexec=True)
    assert result["outcome"] == "exception", result["summary"]

    marker_path = target_claude / bundle_copy.SYNC_INCOMPLETE_FILENAME
    assert marker_path.exists()
    marker = bundle_copy.read_sync_incomplete(target_claude)
    assert marker is not None
    assert marker["target_sha"] == result["payload"]["target_sha"]


def test_sync_clears_the_incomplete_marker_on_a_completed_run(
    patched_clone, tmp_path: pathlib.Path
):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    # Advance the bundle so previous_sha != new_sha - otherwise the pin
    # write is a same-sha no-op and this test proves nothing about clearing.
    new_file = bundle_root / ".claude" / "skills" / "new-skill" / "SKILL.md"
    new_file.parent.mkdir(parents=True)
    new_file.write_text("new skill body\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "advance for marker-clear test"],
        cwd=bundle_root,
        check=True,
    )

    import bundle_copy

    previous_pin = bundle_copy.read_version_file(target_claude)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]

    marker_path = target_claude / bundle_copy.SYNC_INCOMPLETE_FILENAME
    assert not marker_path.exists()
    pin_after = bundle_copy.read_version_file(target_claude)
    assert pin_after["sha"] != previous_pin["sha"]
    assert pin_after["sha"] == result["payload"]["new_sha"]


def test_sync_reports_a_marker_left_by_a_previous_run(
    patched_clone, tmp_path: pathlib.Path
):
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    import bundle_copy

    bundle_copy.mark_sync_incomplete(target_claude, "a" * 40, "b" * 40)

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    previous_run_incomplete = result["payload"]["previous_run_incomplete"]
    assert previous_run_incomplete is not None
    assert previous_run_incomplete["target_sha"] == "b" * 40


# ---------------------------------------------------------------------------
# PLAN-AK5: sync refuses and reports a write it does not own, and reports a
# sentinel-block change that removes a line rather than replacing silently.
# ---------------------------------------------------------------------------


def _establish_receipt(bundle_root, target_claude, sha="sha1"):
    """Record a receipt for every path currently on disk, mirroring what a
    real sync's write_receipt call does at the end of a run."""
    import bundle_copy

    report = bundle_copy.copy_bundle_managed(bundle_root / ".claude", target_claude)
    bundle_copy.write_receipt(
        target_claude,
        report.files_copied + report.files_unchanged,
        sha,
        bundle="plan_foundry",
    )


def test_sync_refuses_to_overwrite_a_path_it_did_not_write(
    patched_clone, tmp_path: pathlib.Path
):
    """FOUNDRYREQ-plan_foundry_dev-...-two-bundles-same-hook-path-silent-clobber:
    a path this bundle's own receipt does not vouch for is left alone, named
    in refused_not_ours, in the summary, and in the standing conflicts file.
    Exercised on both a hooks/ path and a skills/ path, since the reported
    defect and the mixed-generation-install case are not limited to hooks/."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"
    _establish_receipt(bundle_root, target_claude)

    # A sibling bundle (or a hand edit) overwrites two paths this bundle
    # installed - one under hooks/, one under skills/ (operating-rules.md is
    # read only as prose text by sync, never imported, so corrupting it here
    # cannot itself break the run).
    hook_path = target_claude / "hooks" / "hook.json"
    hook_path.write_text('{"owner": "someone-else"}\n', encoding="utf-8")
    skill_path = (
        target_claude / "skills" / "init-plan-foundry" / "operating-rules.md"
    )
    skill_path.write_text("someone else's content\n", encoding="utf-8")

    # The incoming bundle also changes both paths, so a plain byte-compare
    # would otherwise copy them straight over.
    (bundle_root / ".claude" / "hooks" / "hook.json").write_text(
        '{"v": 2}\n', encoding="utf-8"
    )
    (
        bundle_root / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
    ).write_text("new bundle content\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "bundle changes both diverged paths"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    refused = result["payload"]["refused_not_ours"]
    assert "hooks/hook.json" in refused
    assert "skills/init-plan-foundry/operating-rules.md" in refused
    assert hook_path.read_text(encoding="utf-8") == '{"owner": "someone-else"}\n'
    assert skill_path.read_text(encoding="utf-8") == "someone else's content\n"
    assert "hooks/hook.json" in result["summary"]

    conflicts_path = target_claude / ".bundle-receipts" / "plan_foundry.conflicts"
    conflicts_text = conflicts_path.read_text(encoding="utf-8")
    assert "hooks/hook.json" in conflicts_text
    assert "skills/init-plan-foundry/operating-rules.md" in conflicts_text


def test_sync_copies_its_own_unchanged_path_untouched(
    patched_clone, tmp_path: pathlib.Path
):
    """Control: a receipt recording the sha256 the file actually has does
    not disarm an ordinary upgrade of that same path."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"
    _establish_receipt(bundle_root, target_claude)

    (bundle_root / ".claude" / "hooks" / "hook.json").write_text(
        '{"v": 2}\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "bundle changes hook"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"]["refused_not_ours"] == []
    assert (target_claude / "hooks" / "hook.json").read_text(encoding="utf-8") == (
        '{"v": 2}\n'
    )


def test_sync_does_not_record_a_refused_path_in_the_new_receipt(
    patched_clone, tmp_path: pathlib.Path
):
    import bundle_copy

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"
    _establish_receipt(bundle_root, target_claude)

    (target_claude / "hooks" / "hook.json").write_text(
        '{"owner": "someone-else"}\n', encoding="utf-8"
    )
    (bundle_root / ".claude" / "hooks" / "hook.json").write_text(
        '{"v": 2}\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "bundle changes hook"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert "hooks/hook.json" in result["payload"]["refused_not_ours"]
    new_receipt = bundle_copy.read_receipt(target_claude, bundle="plan_foundry")
    assert "hooks/hook.json" not in new_receipt["files"]


def test_sync_re_reports_a_standing_conflict_and_clears_it_when_resolved(
    patched_clone, tmp_path: pathlib.Path
):
    """D7: a refusal re-reports on the next sync and the one after, and the
    standing conflicts file self-clears once the divergence is resolved."""
    import bundle_copy

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"
    _establish_receipt(bundle_root, target_claude)

    (target_claude / "hooks" / "hook.json").write_text(
        '{"owner": "someone-else"}\n', encoding="utf-8"
    )
    (bundle_root / ".claude" / "hooks" / "hook.json").write_text(
        '{"v": 2}\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "bundle changes hook"],
        cwd=bundle_root,
        check=True,
    )

    conflicts_path = target_claude / ".bundle-receipts" / "plan_foundry.conflicts"

    result1 = sync_mod.sync(target)
    assert result1["outcome"] == "success", result1["summary"]
    assert "hooks/hook.json" in result1["payload"]["refused_not_ours"]
    assert "hooks/hook.json" in conflicts_path.read_text(encoding="utf-8")

    result2 = sync_mod.sync(target)
    assert result2["outcome"] == "success", result2["summary"]
    assert "hooks/hook.json" in result2["payload"]["refused_not_ours"]
    assert "hooks/hook.json" in conflicts_path.read_text(encoding="utf-8")

    # Resolve the divergence by hand: write the bundle's own bytes and
    # record their sha256 in the receipt (standing in for an operator
    # repair, or --force-overwrite-diverged).
    resolved_bytes = (bundle_root / ".claude" / "hooks" / "hook.json").read_bytes()
    (target_claude / "hooks" / "hook.json").write_bytes(resolved_bytes)
    current_receipt = bundle_copy.read_receipt(target_claude, bundle="plan_foundry")
    current_receipt["files"]["hooks/hook.json"] = bundle_copy._file_sha256(
        target_claude / "hooks" / "hook.json"
    )
    bundle_copy.write_receipt(
        target_claude,
        list(current_receipt["files"].keys()),
        current_receipt["sha"],
        bundle="plan_foundry",
    )

    result3 = sync_mod.sync(target)
    assert result3["outcome"] == "success", result3["summary"]
    assert "hooks/hook.json" not in result3["payload"]["refused_not_ours"]
    assert conflicts_path.read_text(encoding="utf-8") == ""


def test_sync_reports_a_non_additive_sentinel_block_change(
    patched_clone, tmp_path: pathlib.Path
):
    import claude_md_block  # noqa: E402 - on sys.path via _SHARED insertion at module top

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    stale_block = claude_md_block.build_block("Rule one.\nRule two.\n")
    (target / "CLAUDE.md").write_text(stale_block, encoding="utf-8")

    (
        bundle_root / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
    ).write_text("Rule one.\nRule two changed.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "change operating rules"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    claude_md_payload = result["payload"]["claude_md"]
    assert claude_md_payload["change_status"] == "non-additive"
    assert "Rule two." in claude_md_payload["removed_lines"]


def test_sync_does_not_flag_a_purely_additive_sentinel_block_change(
    patched_clone, tmp_path: pathlib.Path
):
    import claude_md_block  # noqa: E402 - on sys.path via _SHARED insertion at module top

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    stale_block = claude_md_block.build_block("Rule one.\n")
    (target / "CLAUDE.md").write_text(stale_block, encoding="utf-8")

    (
        bundle_root / ".claude" / "skills" / "init-plan-foundry" / "operating-rules.md"
    ).write_text("Rule one.\nRule two.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "add a rule"], cwd=bundle_root, check=True
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    claude_md_payload = result["payload"]["claude_md"]
    assert claude_md_payload["change_status"] == "additive"
    assert claude_md_payload["removed_lines"] == []


def test_sync_on_a_target_with_no_receipt_copies_and_reports_ownership_unverified(
    patched_clone, tmp_path: pathlib.Path
):
    """The pre-receipt consumer: every file copies as before, nothing is
    refused, and the run names the condition rather than staying silent."""
    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)

    new_file = bundle_root / ".claude" / "skills" / "new-skill" / "SKILL.md"
    new_file.parent.mkdir(parents=True)
    new_file.write_text("new skill body\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "add new-skill"], cwd=bundle_root, check=True
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert "skills/new-skill/SKILL.md" in result["payload"]["files_copied"]
    assert result["payload"]["refused_not_ours"] == []
    assert result["payload"]["ownership_unverified"]


def test_sync_adopts_a_legacy_receipt_whose_sha_matches_the_pin(
    patched_clone, tmp_path: pathlib.Path
):
    """A target holding only the legacy receipt gets ownership protection on
    this run rather than the next."""
    import bundle_copy

    bundle_root = patched_clone
    target = tmp_path / "target"
    target.mkdir()
    _init_target_via_copy(bundle_root, target)
    target_claude = target / ".claude"

    pin = bundle_copy.read_version_file(target_claude)
    report = bundle_copy.copy_bundle_managed(bundle_root / ".claude", target_claude)
    lines = [f"sha={pin['sha']}", "written=2026-08-05T00:00:00Z"]
    for rel in sorted(set(report.files_copied + report.files_unchanged)):
        digest = bundle_copy._file_sha256(target_claude / rel)
        lines.append(f"{rel}\t{digest}")
    (target_claude / bundle_copy.RECEIPT_FILENAME).write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    diverged_rel = "hooks/hook.json"
    (target_claude / diverged_rel).write_text(
        '{"owner": "someone-else"}\n', encoding="utf-8"
    )
    (bundle_root / ".claude" / "hooks" / "hook.json").write_text(
        '{"v": 2}\n', encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "bundle changes hook"],
        cwd=bundle_root,
        check=True,
    )

    result = sync_mod.sync(target)
    assert result["outcome"] == "success", result["summary"]
    assert result["payload"]["ownership_unverified"] is None
    assert diverged_rel in result["payload"]["refused_not_ours"]
