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
