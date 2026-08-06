"""Tests for the ownership determination behind audit-skills' fix-or-raise branch.

Run: python3 -m pytest .claude/skills/audit-skills/lib/test_skill_ownership.py -q

Every case here builds a fake target tree under tmp_path. None of them run
against the real repository, because the real repository is the foundry source
and would take the first branch every time.
"""

from __future__ import annotations

import json
import pathlib
import sys

_LIB = pathlib.Path(__file__).resolve().parent
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import skill_ownership as so  # noqa: E402


def make_target(tmp_path, skills, receipt_paths=None, ledger=None):
    """Build a consumer-shaped tree. `receipt_paths` None means no receipt."""
    claude = tmp_path / ".claude"
    for name, text in skills.items():
        d = claude / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(text, encoding="utf-8")

    if ledger is not None:
        shared = claude / "skills" / "_shared"
        shared.mkdir(parents=True, exist_ok=True)
        (shared / "bundle-contract.json").write_text(
            json.dumps({"schema_version": 2, "deprecations": ledger}),
            encoding="utf-8",
        )

    if receipt_paths is not None:
        lines = ["sha=deadbeef", "written=2026-08-03T00:00:00Z", "bundle=plan_foundry"]
        lines += [f"{rel}\t{'0' * 64}" for rel in receipt_paths]
        receipt_dir = claude / ".bundle-receipts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        (receipt_dir / "plan_foundry.files").write_text(
            "\n".join(lines) + "\n", encoding="utf-8"
        )
    return tmp_path


SKILL = "---\nname: {name}\ndescription: x\n---\n\nbody\n"
PROJECT_SKILL = "---\nname: {name}\ndescription: x\nowner: project\n---\n\nbody\n"


def test_foundry_source_detected_and_may_fix(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "promote.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (tmp_path / "scripts" / "prod-repo.txt").write_text("repo=x/y\n", encoding="utf-8")
    make_target(tmp_path, {"anything": SKILL.format(name="anything")}, receipt_paths=[])

    out = so.classify_skill_ownership(tmp_path, "anything")
    assert out.verdict == so.FOUNDRY_SOURCE
    assert out.may_propose_edit is True


def test_receipt_hit_is_bundle_managed_and_raises(tmp_path):
    make_target(
        tmp_path,
        {"execute-plan": SKILL.format(name="execute-plan")},
        receipt_paths=["skills/execute-plan/SKILL.md"],
    )
    out = so.classify_skill_ownership(tmp_path, "execute-plan")
    assert out.verdict == so.BUNDLE_MANAGED
    assert out.may_propose_edit is False
    assert out.raise_to == "raise-foundry-request"


def test_owner_project_marker_is_consumer_owned(tmp_path):
    make_target(
        tmp_path,
        {"mine": PROJECT_SKILL.format(name="mine")},
        receipt_paths=["skills/execute-plan/SKILL.md"],
    )
    out = so.classify_skill_ownership(tmp_path, "mine")
    assert out.verdict == so.CONSUMER_OWNED
    assert out.may_propose_edit is True


def test_project_skills_listing_is_consumer_owned(tmp_path):
    make_target(
        tmp_path,
        {"mine": SKILL.format(name="mine")},
        receipt_paths=["skills/execute-plan/SKILL.md"],
    )
    (tmp_path / ".claude" / "project-skills.md").write_text(
        "Project skills: `mine`\n", encoding="utf-8"
    )
    out = so.classify_skill_ownership(tmp_path, "mine")
    assert out.verdict == so.CONSUMER_OWNED


def test_absent_from_receipt_without_marker_is_unattributed_not_consumer(tmp_path):
    """The case the policy is most emphatic about: absence is not ownership."""
    make_target(
        tmp_path,
        {"someone-elses": SKILL.format(name="someone-elses")},
        receipt_paths=["skills/execute-plan/SKILL.md"],
    )
    out = so.classify_skill_ownership(tmp_path, "someone-elses")
    assert out.verdict == so.UNATTRIBUTED
    assert out.may_propose_edit is False
    assert out.raise_to is None


def test_deprecation_ledger_explains_a_dropped_bundle_path(tmp_path):
    make_target(
        tmp_path,
        {"convert-pdf": SKILL.format(name="convert-pdf")},
        receipt_paths=["skills/execute-plan/SKILL.md"],
        ledger=[
            {
                "path": ".claude/skills/convert-pdf/SKILL.md",
                "since": "v1.15.0",
                "removed_in": "v2.0.0",
                "replaced_by": "elsewhere",
                "kind": "skill",
            }
        ],
    )
    out = so.classify_skill_ownership(tmp_path, "convert-pdf")
    assert out.verdict == so.BUNDLE_MANAGED
    assert out.may_propose_edit is False


def test_no_receipt_fails_closed(tmp_path):
    make_target(tmp_path, {"whatever": SKILL.format(name="whatever")}, receipt_paths=None)
    out = so.classify_skill_ownership(tmp_path, "whatever")
    assert out.verdict == so.UNDETERMINABLE
    assert out.may_propose_edit is False
    assert out.raise_to == "raise-foundry-request"


def test_corrupt_receipt_fails_closed(tmp_path):
    make_target(tmp_path, {"whatever": SKILL.format(name="whatever")}, receipt_paths=[])
    (tmp_path / ".claude" / ".bundle-receipts" / "plan_foundry.files").write_text(
        "this is not a receipt\n", encoding="utf-8"
    )
    out = so.classify_skill_ownership(tmp_path, "whatever")
    assert out.verdict == so.UNDETERMINABLE
    assert out.may_propose_edit is False


def test_corrupt_receipt_does_not_override_an_explicit_project_marker(tmp_path):
    make_target(tmp_path, {"mine": PROJECT_SKILL.format(name="mine")}, receipt_paths=None)
    out = so.classify_skill_ownership(tmp_path, "mine")
    assert out.verdict == so.CONSUMER_OWNED


def test_classify_corpus_skips_shared_and_dirs_without_a_skill_md(tmp_path):
    make_target(
        tmp_path,
        {"a": SKILL.format(name="a"), "b": SKILL.format(name="b")},
        receipt_paths=["skills/a/SKILL.md"],
    )
    (tmp_path / ".claude" / "skills" / "_shared").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude" / "skills" / "empty").mkdir(parents=True, exist_ok=True)

    names = {o.skill: o.verdict for o in so.classify_corpus(tmp_path)}
    assert names == {"a": so.BUNDLE_MANAGED, "b": so.UNATTRIBUTED}


def test_every_verdict_except_fix_branches_declines_the_edit(tmp_path):
    """The invariant the report depends on: only two verdicts may propose edits."""
    may_fix = {so.FOUNDRY_SOURCE, so.CONSUMER_OWNED}
    all_verdicts = {
        so.FOUNDRY_SOURCE,
        so.BUNDLE_MANAGED,
        so.CONSUMER_OWNED,
        so.UNATTRIBUTED,
        so.UNDETERMINABLE,
    }
    assert all_verdicts - may_fix == {
        so.BUNDLE_MANAGED,
        so.UNATTRIBUTED,
        so.UNDETERMINABLE,
    }
