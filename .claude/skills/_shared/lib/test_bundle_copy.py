"""Tests for bundle_copy module (PLAN-AC5, PLAN-AH7)."""

from __future__ import annotations

import datetime
import pathlib
import shutil
import subprocess
import sys

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SHARED))

import bundle_copy  # noqa: E402


def _make_bundle(root: pathlib.Path) -> pathlib.Path:
    """Build a minimal bundle .claude tree under root/.claude. Returns the .claude dir."""
    claude = root / ".claude"
    (claude / "skills" / "foo").mkdir(parents=True)
    (claude / "skills" / "foo" / "SKILL.md").write_text("foo skill body\n")
    (claude / "skills" / "foo" / "notes.md").write_text("foo notes\n")
    (claude / "skills" / "bar").mkdir(parents=True)
    (claude / "skills" / "bar" / "SKILL.md").write_text("bar skill body\n")
    (claude / "agents").mkdir(parents=True)
    (claude / "agents" / "an-agent.md").write_text("agent body\n")
    (claude / "commands").mkdir(parents=True)
    (claude / "commands" / "cmd.md").write_text("cmd body\n")
    (claude / "hooks").mkdir(parents=True)
    (claude / "hooks" / "hook.json").write_text("{}\n")
    return claude


def test_copy_into_empty_target(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert sorted(report.files_copied) == [
        "agents/an-agent.md",
        "commands/cmd.md",
        "hooks/hook.json",
        "skills/bar/SKILL.md",
        "skills/foo/SKILL.md",
        "skills/foo/notes.md",
    ]
    assert report.files_unchanged == []
    assert report.project_additions == []
    assert report.stale_in_target == []
    assert (target_claude / "skills" / "foo" / "SKILL.md").read_text() == "foo skill body\n"


def test_idempotent_second_run(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert report.files_copied == []
    assert len(report.files_unchanged) == 6


def test_project_addition_under_new_subskill_preserved(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    project_skill = target_claude / "skills" / "myproj" / "SKILL.md"
    project_skill.parent.mkdir(parents=True)
    project_skill.write_text("project-specific skill\n")
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert "skills/myproj/SKILL.md" in report.project_additions
    assert project_skill.exists()
    assert project_skill.read_text() == "project-specific skill\n"


def test_stale_in_target_reported_when_bundle_drops_file(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    (bundle_claude / "skills" / "foo" / "notes.md").unlink()
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert "skills/foo/notes.md" in report.stale_in_target
    assert (target_claude / "skills" / "foo" / "notes.md").exists()


def test_hand_edited_bundle_file_overwritten(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    target_file = target_claude / "skills" / "foo" / "SKILL.md"
    target_file.write_text("hand-edited content\n")
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert "skills/foo/SKILL.md" in report.files_copied
    assert target_file.read_text() == "foo skill body\n"


def test_missing_bundle_subdir_is_silently_skipped(tmp_path: pathlib.Path):
    bundle_claude = tmp_path / "bundle" / ".claude"
    (bundle_claude / "skills" / "only").mkdir(parents=True)
    (bundle_claude / "skills" / "only" / "S.md").write_text("only\n")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    assert report.files_copied == ["skills/only/S.md"]


def _init_git_bundle(root: pathlib.Path) -> pathlib.Path:
    bundle_root = root / "bundle"
    bundle_root.mkdir()
    subprocess.run(["git", "init", "--quiet"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=bundle_root, check=True
    )
    subprocess.run(["git", "config", "user.name", "Test"], cwd=bundle_root, check=True)
    (bundle_root / "marker.txt").write_text("v1\n")
    subprocess.run(["git", "add", "-A"], cwd=bundle_root, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "init"], cwd=bundle_root, check=True
    )
    return bundle_root


def test_write_and_read_version_file(tmp_path: pathlib.Path):
    bundle_root = _init_git_bundle(tmp_path)
    target_claude = tmp_path / "target" / ".claude"
    data = bundle_copy.write_version_file(bundle_root, target_claude)
    assert len(data["sha"]) == 40
    assert "synced" in data and data["synced"].endswith("Z")
    read = bundle_copy.read_version_file(target_claude)
    assert read is not None
    assert read["sha"] == data["sha"]
    assert read["synced"] == data["synced"]


def test_read_version_file_absent_returns_none(tmp_path: pathlib.Path):
    assert bundle_copy.read_version_file(tmp_path / "nothing") is None


def test_write_version_file_handles_non_git_bundle(tmp_path: pathlib.Path):
    bundle_root = tmp_path / "not-git"
    bundle_root.mkdir()
    target_claude = tmp_path / "target" / ".claude"
    data = bundle_copy.write_version_file(bundle_root, target_claude)
    assert data["sha"] == ""
    assert data["tag"] == ""


# ---------------------------------------------------------------------------
# PLAN-AH8: bundle-contract.json, schema_version pin field, version string.
# ---------------------------------------------------------------------------


def test_read_bundle_contract_returns_parsed_dict(tmp_path: pathlib.Path):
    bundle_root = tmp_path / "bundle"
    contract_dir = bundle_root / ".claude" / "skills" / "_shared"
    contract_dir.mkdir(parents=True)
    (contract_dir / "bundle-contract.json").write_text(
        '{"schema_version": 2, "deprecations": []}', encoding="utf-8"
    )
    contract = bundle_copy.read_bundle_contract(bundle_root)
    assert contract == {"schema_version": 2, "deprecations": []}


def test_read_bundle_contract_absent_degrades_empty(tmp_path: pathlib.Path):
    bundle_root = tmp_path / "bundle-with-no-contract"
    bundle_root.mkdir()
    contract = bundle_copy.read_bundle_contract(bundle_root)
    assert contract == {"schema_version": "", "deprecations": []}


def test_read_bundle_contract_malformed_json_degrades_empty(tmp_path: pathlib.Path):
    bundle_root = tmp_path / "bundle"
    contract_dir = bundle_root / ".claude" / "skills" / "_shared"
    contract_dir.mkdir(parents=True)
    (contract_dir / "bundle-contract.json").write_text("not json", encoding="utf-8")
    contract = bundle_copy.read_bundle_contract(bundle_root)
    assert contract == {"schema_version": "", "deprecations": []}


def test_pin_records_schema_version_and_degrades_empty(tmp_path: pathlib.Path):
    """A-8: the pin records schema_version, and an absent contract writes it
    empty rather than omitting it."""
    # A bundle with a contract present.
    bundle_root = _init_git_bundle(tmp_path)
    contract_dir = bundle_root / ".claude" / "skills" / "_shared"
    contract_dir.mkdir(parents=True)
    (contract_dir / "bundle-contract.json").write_text(
        '{"schema_version": 2, "deprecations": []}', encoding="utf-8"
    )
    target_claude = tmp_path / "target" / ".claude"
    data = bundle_copy.write_version_file(bundle_root, target_claude)
    assert data["schema_version"] == 2
    pin_text = (target_claude / bundle_copy.VERSION_FILENAME).read_text(encoding="utf-8")
    assert "schema_version=2" in pin_text

    # A bundle with no contract at all - the key is written empty, not omitted.
    no_contract_scope = tmp_path / "no-contract-scope"
    no_contract_scope.mkdir()
    bundle_root2 = _init_git_bundle(no_contract_scope)
    target_claude2 = tmp_path / "target2" / ".claude"
    data2 = bundle_copy.write_version_file(bundle_root2, target_claude2)
    assert data2["schema_version"] == ""
    pin_text2 = (target_claude2 / bundle_copy.VERSION_FILENAME).read_text(encoding="utf-8")
    assert "schema_version=" in pin_text2


def test_bundle_version_string_tag_then_sha_then_empty(tmp_path: pathlib.Path):
    """A-9: bundle_version_string returns tag, then sha, then empty."""
    # No pin at all.
    assert bundle_copy.bundle_version_string(tmp_path / "nothing") == ""

    # Pin with a tag - tag wins.
    target_claude = tmp_path / "target-with-tag" / ".claude"
    target_claude.mkdir(parents=True)
    (target_claude / bundle_copy.VERSION_FILENAME).write_text(
        "sha=abc123\ntag=v1.2.0\nsynced=2026-01-01T00:00:00Z\n", encoding="utf-8"
    )
    assert bundle_copy.bundle_version_string(target_claude) == "v1.2.0"

    # Pin with no tag - falls back to sha.
    target_claude2 = tmp_path / "target-no-tag" / ".claude"
    target_claude2.mkdir(parents=True)
    (target_claude2 / bundle_copy.VERSION_FILENAME).write_text(
        "sha=abc123\ntag=\nsynced=2026-01-01T00:00:00Z\n", encoding="utf-8"
    )
    assert bundle_copy.bundle_version_string(target_claude2) == "abc123"

    # Pin with neither tag nor sha - empty.
    target_claude3 = tmp_path / "target-neither" / ".claude"
    target_claude3.mkdir(parents=True)
    (target_claude3 / bundle_copy.VERSION_FILENAME).write_text(
        "sha=\ntag=\nsynced=2026-01-01T00:00:00Z\n", encoding="utf-8"
    )
    assert bundle_copy.bundle_version_string(target_claude3) == ""


# ---------------------------------------------------------------------------
# PLAN-AH7: install receipt, three-set classification, quarantine, sweep.
# ---------------------------------------------------------------------------


def test_dropped_skill_directory_is_quarantined(tmp_path: pathlib.Path):
    """A-1: a bundle that drops a whole skill directory quarantines exactly
    those files, and the skill is absent from the bundle-managed paths
    afterwards."""
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report1 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    bundle_copy.write_receipt(
        target_claude, report1.files_copied + report1.files_unchanged, "sha1"
    )

    # Bundle drops the whole "bar" skill directory.
    shutil.rmtree(bundle_claude / "skills" / "bar")

    report2 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    receipt = bundle_copy.read_receipt(target_claude)
    bundle_files = set(report2.files_copied) | set(report2.files_unchanged)
    target_files = (
        bundle_files | set(report2.project_additions) | set(report2.stale_in_target)
    )
    classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)
    assert classification.gone_upstream == ["skills/bar/SKILL.md"]

    moved = bundle_copy.quarantine(target_claude, classification.gone_upstream)
    assert moved == ["skills/bar/SKILL.md"]
    assert not (target_claude / "skills" / "bar" / "SKILL.md").exists()
    quarantine_root = target_claude / bundle_copy.QUARANTINE_DIRNAME
    found = list(quarantine_root.glob("*/skills/bar/SKILL.md"))
    assert len(found) == 1


def test_consumer_file_in_bundle_skill_dir_is_not_quarantined(tmp_path: pathlib.Path):
    """A-2: a consumer-authored file inside a bundle-owned skill directory is
    NOT quarantined. The false-positive case the receipt exists to fix."""
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report1 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    bundle_copy.write_receipt(
        target_claude, report1.files_copied + report1.files_unchanged, "sha1"
    )

    # Consumer adds their own file inside a bundle-owned skill dir ("foo").
    consumer_file = target_claude / "skills" / "foo" / "my-local-notes.md"
    consumer_file.write_text("consumer content\n", encoding="utf-8")

    report2 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    receipt = bundle_copy.read_receipt(target_claude)
    bundle_files = set(report2.files_copied) | set(report2.files_unchanged)
    target_files = (
        bundle_files | set(report2.project_additions) | set(report2.stale_in_target)
    )
    classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)

    assert "skills/foo/my-local-notes.md" not in classification.gone_upstream
    assert "skills/foo/my-local-notes.md" in classification.consumer_owned

    bundle_copy.quarantine(target_claude, classification.gone_upstream)
    assert consumer_file.exists()
    assert consumer_file.read_text(encoding="utf-8") == "consumer content\n"


def test_missing_receipt_quarantines_nothing(tmp_path: pathlib.Path):
    """A-3: a sync with no receipt quarantines nothing and reports why."""
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    # No receipt written - simulate a pre-AH7 consumer / corrupt receipt.
    assert bundle_copy.read_receipt(target_claude) is None

    (bundle_claude / "skills" / "bar" / "SKILL.md").unlink()
    (bundle_claude / "skills" / "bar").rmdir()

    report2 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    receipt = bundle_copy.read_receipt(target_claude)
    assert receipt is None

    bundle_files = set(report2.files_copied) | set(report2.files_unchanged)
    target_files = (
        bundle_files | set(report2.project_additions) | set(report2.stale_in_target)
    )
    classification = bundle_copy.classify_stale(bundle_files, target_files, receipt)
    assert classification.gone_upstream == []
    assert "skills/bar/SKILL.md" in classification.unknown

    moved = bundle_copy.quarantine(target_claude, classification.gone_upstream)
    assert moved == []
    assert (target_claude / "skills" / "bar" / "SKILL.md").exists()


def test_quarantine_moves_without_deleting(tmp_path: pathlib.Path):
    """A-4: quarantine() performs no deletion. Every source path exists at
    its quarantine destination with identical bytes, and the total file
    count under .claude/ is unchanged."""
    target_claude = tmp_path / "target" / ".claude"
    (target_claude / "skills" / "foo").mkdir(parents=True)
    f1 = target_claude / "skills" / "foo" / "a.md"
    f1.write_text("alpha content\n", encoding="utf-8")
    (target_claude / "agents").mkdir(parents=True)
    f2 = target_claude / "agents" / "b.md"
    f2.write_text("beta content\n", encoding="utf-8")

    before_count = sum(1 for p in target_claude.rglob("*") if p.is_file())

    moved = bundle_copy.quarantine(target_claude, ["skills/foo/a.md", "agents/b.md"])
    assert set(moved) == {"skills/foo/a.md", "agents/b.md"}

    after_count = sum(1 for p in target_claude.rglob("*") if p.is_file())
    assert after_count == before_count

    quarantine_root = target_claude / bundle_copy.QUARANTINE_DIRNAME
    stamp_dirs = list(quarantine_root.iterdir())
    assert len(stamp_dirs) == 1
    dest_a = stamp_dirs[0] / "skills" / "foo" / "a.md"
    dest_b = stamp_dirs[0] / "agents" / "b.md"
    assert dest_a.read_text(encoding="utf-8") == "alpha content\n"
    assert dest_b.read_text(encoding="utf-8") == "beta content\n"
    assert not f1.exists()
    assert not f2.exists()


def test_sweep_removes_only_aged_wellformed_dirs(tmp_path: pathlib.Path):
    """A-5: the sweep removes only aged, well-formed directories. Fixtures
    named 40 days ago, 5 days ago, and "not-a-timestamp"; only the first is
    removed."""
    target_claude = tmp_path / "target" / ".claude"
    quarantine_root = target_claude / bundle_copy.QUARANTINE_DIRNAME
    now = datetime.datetime.now(datetime.timezone.utc)
    old_stamp = (now - datetime.timedelta(days=40)).strftime("%Y%m%dT%H%M%SZ")
    recent_stamp = (now - datetime.timedelta(days=5)).strftime("%Y%m%dT%H%M%SZ")
    for name in (old_stamp, recent_stamp, "not-a-timestamp"):
        d = quarantine_root / name
        d.mkdir(parents=True)
        (d / "placeholder.txt").write_text("x\n", encoding="utf-8")

    swept = bundle_copy.sweep_quarantine(target_claude, max_age_days=30)

    assert swept == [old_stamp]
    assert not (quarantine_root / old_stamp).exists()
    assert (quarantine_root / recent_stamp).exists()
    assert (quarantine_root / "not-a-timestamp").exists()


def test_read_receipt_absent_returns_none(tmp_path: pathlib.Path):
    assert bundle_copy.read_receipt(tmp_path / "nothing") is None


def test_read_receipt_malformed_header_returns_none(tmp_path: pathlib.Path):
    target_claude = tmp_path / "target" / ".claude"
    target_claude.mkdir(parents=True)
    (target_claude / bundle_copy.RECEIPT_FILENAME).write_text(
        "not-a-valid-header-line\n", encoding="utf-8"
    )
    assert bundle_copy.read_receipt(target_claude) is None


# ---------------------------------------------------------------------------
# PLAN-AK6: resolve_version/write_version_file split, and the incomplete-
# sync marker.
# ---------------------------------------------------------------------------


def test_resolve_version_matches_write_version_file_keys_and_writes_nothing(
    tmp_path: pathlib.Path,
):
    bundle_root = _init_git_bundle(tmp_path)
    target_claude = tmp_path / "target" / ".claude"
    resolved = bundle_copy.resolve_version(bundle_root)
    assert set(resolved.keys()) == {"sha", "tag", "synced", "schema_version"}
    assert len(resolved["sha"]) == 40
    assert not (target_claude / bundle_copy.VERSION_FILENAME).exists()


def test_write_version_file_with_data_writes_exactly_the_supplied_dict(
    tmp_path: pathlib.Path,
):
    bundle_root = _init_git_bundle(tmp_path)
    target_claude = tmp_path / "target" / ".claude"
    supplied = {
        "sha": "a" * 40,
        "tag": "v9.9.9",
        "synced": "2026-01-01T00:00:00Z",
        "schema_version": 3,
    }
    written = bundle_copy.write_version_file(bundle_root, target_claude, data=supplied)
    assert written == supplied
    read = bundle_copy.read_version_file(target_claude)
    assert read["sha"] == supplied["sha"]
    assert read["tag"] == supplied["tag"]
    assert read["synced"] == supplied["synced"]
    assert read["schema_version"] == str(supplied["schema_version"])


def test_write_version_file_without_data_behaves_as_before(tmp_path: pathlib.Path):
    bundle_root = _init_git_bundle(tmp_path)
    target_claude = tmp_path / "target" / ".claude"
    data = bundle_copy.write_version_file(bundle_root, target_claude)
    resolved = bundle_copy.resolve_version(bundle_root)
    assert data["sha"] == resolved["sha"]
    assert data["tag"] == resolved["tag"]
    assert data["schema_version"] == resolved["schema_version"]


def test_mark_and_read_sync_incomplete_round_trips(tmp_path: pathlib.Path):
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.mark_sync_incomplete(target_claude, "a" * 40, "b" * 40)
    marker = bundle_copy.read_sync_incomplete(target_claude)
    assert marker is not None
    assert marker["previous_sha"] == "a" * 40
    assert marker["target_sha"] == "b" * 40
    assert "started" in marker


def test_read_sync_incomplete_returns_none_for_absent_or_unparseable_file(
    tmp_path: pathlib.Path,
):
    target_claude = tmp_path / "target" / ".claude"
    assert bundle_copy.read_sync_incomplete(target_claude) is None

    target_claude.mkdir(parents=True)
    (target_claude / bundle_copy.SYNC_INCOMPLETE_FILENAME).write_bytes(
        b"\xff\xfe not valid utf-8 \xff"
    )
    assert bundle_copy.read_sync_incomplete(target_claude) is None


def test_clear_sync_incomplete_removes_and_is_a_noop_on_second_call(
    tmp_path: pathlib.Path,
):
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.mark_sync_incomplete(target_claude, "a" * 40, "b" * 40)
    marker_path = target_claude / bundle_copy.SYNC_INCOMPLETE_FILENAME
    assert marker_path.exists()
    bundle_copy.clear_sync_incomplete(target_claude)
    assert not marker_path.exists()
    bundle_copy.clear_sync_incomplete(target_claude)  # no-op, does not raise
    assert not marker_path.exists()


def test_write_then_read_receipt_round_trips(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    written = bundle_copy.write_receipt(
        target_claude, report.files_copied + report.files_unchanged, "abc123"
    )
    read = bundle_copy.read_receipt(target_claude)
    assert read is not None
    assert read["sha"] == "abc123"
    assert read["files"] == written["files"]
    assert "skills/foo/SKILL.md" in read["files"]


# ---------------------------------------------------------------------------
# PLAN-AK5: namespaced receipt, legacy adoption, divergence-aware copy.
# ---------------------------------------------------------------------------


def test_write_receipt_puts_file_at_namespaced_path_with_bundle_header(
    tmp_path: pathlib.Path,
):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    bundle_copy.write_receipt(
        target_claude,
        report.files_copied + report.files_unchanged,
        "abc123",
        bundle="plan_foundry",
    )
    namespaced = bundle_copy.receipt_path(target_claude, "plan_foundry")
    assert namespaced.exists()
    text = namespaced.read_text(encoding="utf-8")
    assert "bundle=plan_foundry" in text
    assert not (target_claude / bundle_copy.RECEIPT_FILENAME).exists()


def test_read_receipt_round_trips_namespaced(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    written = bundle_copy.write_receipt(
        target_claude,
        report.files_copied + report.files_unchanged,
        "abc123",
        bundle="plan_foundry",
    )
    read = bundle_copy.read_receipt(target_claude, bundle="plan_foundry")
    assert read is not None
    assert read["sha"] == "abc123"
    assert read["bundle"] == "plan_foundry"
    assert read["files"] == written["files"]


def test_read_receipt_adopts_legacy_receipt_whose_sha_matches_pin(
    tmp_path: pathlib.Path,
):
    target_claude = tmp_path / "target" / ".claude"
    target_claude.mkdir(parents=True)
    (target_claude / bundle_copy.VERSION_FILENAME).write_text(
        "sha=" + "a" * 40 + "\ntag=\nsynced=2026-01-01T00:00:00Z\n", encoding="utf-8"
    )
    (target_claude / bundle_copy.RECEIPT_FILENAME).write_text(
        "sha=" + "a" * 40 + "\nwritten=2026-01-01T00:00:00Z\n"
        "skills/foo/SKILL.md\tdeadbeef\n",
        encoding="utf-8",
    )
    read = bundle_copy.read_receipt(target_claude)
    assert read is not None
    assert read["adopted_from_legacy"] is True
    assert read["files"]["skills/foo/SKILL.md"] == "deadbeef"


def test_read_receipt_returns_none_for_legacy_sha_mismatching_pin(
    tmp_path: pathlib.Path,
):
    target_claude = tmp_path / "target" / ".claude"
    target_claude.mkdir(parents=True)
    (target_claude / bundle_copy.VERSION_FILENAME).write_text(
        "sha=" + "b" * 40 + "\ntag=\nsynced=2026-01-01T00:00:00Z\n", encoding="utf-8"
    )
    (target_claude / bundle_copy.RECEIPT_FILENAME).write_text(
        "sha=" + "a" * 40 + "\nwritten=2026-01-01T00:00:00Z\n"
        "skills/foo/SKILL.md\tdeadbeef\n",
        encoding="utf-8",
    )
    assert bundle_copy.read_receipt(target_claude) is None


def test_read_receipt_returns_none_for_legacy_with_no_pin_at_all(
    tmp_path: pathlib.Path,
):
    target_claude = tmp_path / "target" / ".claude"
    target_claude.mkdir(parents=True)
    (target_claude / bundle_copy.RECEIPT_FILENAME).write_text(
        "sha=" + "a" * 40 + "\nwritten=2026-01-01T00:00:00Z\n"
        "skills/foo/SKILL.md\tdeadbeef\n",
        encoding="utf-8",
    )
    assert bundle_copy.read_receipt(target_claude) is None


def test_copy_bundle_managed_refuses_destination_diverged_from_receipt(
    tmp_path: pathlib.Path,
):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report1 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    written = bundle_copy.write_receipt(
        target_claude, report1.files_copied + report1.files_unchanged, "sha1"
    )
    # A sibling (or an operator) changes the file after the receipt was written.
    diverged = target_claude / "skills" / "foo" / "SKILL.md"
    diverged.write_text("someone else's content\n", encoding="utf-8")
    # The incoming bundle also changes that file, so a plain byte-compare
    # would otherwise copy it.
    (bundle_claude / "skills" / "foo" / "SKILL.md").write_text(
        "new bundle content\n", encoding="utf-8"
    )
    receipt = bundle_copy.read_receipt(target_claude)
    report2 = bundle_copy.copy_bundle_managed(
        bundle_claude, target_claude, receipt=receipt
    )
    assert "skills/foo/SKILL.md" in report2.refused_not_ours
    assert diverged.read_text(encoding="utf-8") == "someone else's content\n"
    assert "skills/foo/SKILL.md" not in report2.files_copied


def test_copy_bundle_managed_copies_destination_matching_receipt_sha(
    tmp_path: pathlib.Path,
):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report1 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    bundle_copy.write_receipt(
        target_claude, report1.files_copied + report1.files_unchanged, "sha1"
    )
    (bundle_claude / "skills" / "foo" / "SKILL.md").write_text(
        "new bundle content\n", encoding="utf-8"
    )
    receipt = bundle_copy.read_receipt(target_claude)
    report2 = bundle_copy.copy_bundle_managed(
        bundle_claude, target_claude, receipt=receipt
    )
    assert "skills/foo/SKILL.md" in report2.files_copied
    assert report2.refused_not_ours == []
    assert (
        target_claude / "skills" / "foo" / "SKILL.md"
    ).read_text(encoding="utf-8") == "new bundle content\n"


def test_copy_bundle_managed_refuses_destination_absent_from_receipt(
    tmp_path: pathlib.Path,
):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    # A receipt that never recorded this path at all (e.g. from before it
    # was added upstream).
    receipt = {"sha": "sha1", "written": "x", "files": {}}
    (bundle_claude / "skills" / "foo" / "SKILL.md").write_text(
        "new bundle content\n", encoding="utf-8"
    )
    report = bundle_copy.copy_bundle_managed(
        bundle_claude, target_claude, receipt=receipt
    )
    assert "skills/foo/SKILL.md" in report.refused_not_ours


def test_copy_bundle_managed_force_overwrites_a_refused_path(tmp_path: pathlib.Path):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    report1 = bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    bundle_copy.write_receipt(
        target_claude, report1.files_copied + report1.files_unchanged, "sha1"
    )
    diverged = target_claude / "skills" / "foo" / "SKILL.md"
    diverged.write_text("someone else's content\n", encoding="utf-8")
    (bundle_claude / "skills" / "foo" / "SKILL.md").write_text(
        "new bundle content\n", encoding="utf-8"
    )
    receipt = bundle_copy.read_receipt(target_claude)
    report2 = bundle_copy.copy_bundle_managed(
        bundle_claude, target_claude, receipt=receipt, force=True
    )
    assert "skills/foo/SKILL.md" in report2.forced_overwrites
    assert "skills/foo/SKILL.md" in report2.files_copied
    assert diverged.read_text(encoding="utf-8") == "new bundle content\n"


def test_copy_bundle_managed_with_receipt_none_copies_everything(
    tmp_path: pathlib.Path,
):
    bundle_claude = _make_bundle(tmp_path / "bundle")
    target_claude = tmp_path / "target" / ".claude"
    bundle_copy.copy_bundle_managed(bundle_claude, target_claude)
    diverged = target_claude / "skills" / "foo" / "SKILL.md"
    diverged.write_text("someone else's content\n", encoding="utf-8")
    (bundle_claude / "skills" / "foo" / "SKILL.md").write_text(
        "new bundle content\n", encoding="utf-8"
    )
    report = bundle_copy.copy_bundle_managed(bundle_claude, target_claude, receipt=None)
    assert report.refused_not_ours == []
    assert "skills/foo/SKILL.md" in report.files_copied
    assert diverged.read_text(encoding="utf-8") == "new bundle content\n"
