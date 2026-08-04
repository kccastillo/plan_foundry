#!/usr/bin/env python3
"""Determine who owns a skill directory, so audit-skills knows whether to
propose a fix or raise a request.

The rule: this repo fixes sure mechanical bugs on the spot, a consumer repo
raises. A consumer's `.claude/` is bundle-managed territory, so an edit there
is destroyed at the next sync and the defect returns.

The reference document that states the policy is
`.claude/skills/audit-skills/references/ownership.md`. This module is the
mechanism. Where the two disagree, the reference document is the policy and
this file is the bug.

Run: python3 -m pytest .claude/skills/audit-skills/lib/ -q
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

_SHARED = (
    pathlib.Path(__file__).resolve().parent.parent.parent / "_shared"
)
if str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import bundle_copy  # noqa: E402

# Verdicts, in the order the determination tries them.
FOUNDRY_SOURCE = "foundry_source"
BUNDLE_MANAGED = "bundle_managed"
CONSUMER_OWNED = "consumer_owned"
UNATTRIBUTED = "unattributed"
UNDETERMINABLE = "undeterminable"

_OWNER_PROJECT = re.compile(r"^owner:\s*project\s*$", re.M)


@dataclass
class Ownership:
    """The determination for one skill.

    `verdict` is one of the constants above. `signal` names the evidence that
    decided it, so a report can show its working. `may_propose_edit` is the
    only field a caller needs to branch on, and it is False for every verdict
    except FOUNDRY_SOURCE and CONSUMER_OWNED. `raise_to` names the request
    channel where one is identifiable, and is None where it is not.
    """

    skill: str
    verdict: str
    signal: str
    may_propose_edit: bool
    raise_to: Optional[str] = None
    notes: list = field(default_factory=list)


def is_foundry_source(repo_root: pathlib.Path) -> bool:
    """True when this working tree is plan_foundry itself rather than a
    project that installed it.

    Both markers are repo-local maintainer tooling that the promote allowlist
    does not ship, so a consumer never has them. `scripts/promote.sh` is on
    the allowlist for neither the dev nor the prod side, and
    `scripts/prod-repo.txt` carries the prod coordinates. Requiring both makes
    a stray copy of one file insufficient to flip the branch.
    """
    repo_root = pathlib.Path(repo_root)
    return (repo_root / "scripts" / "promote.sh").is_file() and (
        repo_root / "scripts" / "prod-repo.txt"
    ).is_file()


def _ledger_paths(repo_root: pathlib.Path) -> set:
    """Skill names named by the deprecation ledger.

    The ledger explains a path the receipt records but the bundle no longer
    ships. It is consulted second, never first: it says what the bundle
    dropped on purpose, which is a statement about the bundle rather than a
    record of what was installed here.
    """
    contract = (
        repo_root / ".claude" / "skills" / "_shared" / "bundle-contract.json"
    )
    names = set()
    try:
        data = json.loads(contract.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError):
        return names
    for entry in data.get("deprecations", []) or []:
        m = re.search(r"\.claude/skills/([a-z0-9][a-z0-9-]*)/", entry.get("path", ""))
        if m:
            names.add(m.group(1))
    return names


def _project_skills_names(repo_root: pathlib.Path) -> set:
    listing = repo_root / ".claude" / "project-skills.md"
    try:
        text = listing.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return set()
    return set(re.findall(r"`([a-z0-9][a-z0-9-]*)`", text))


def classify_skill_ownership(
    repo_root, skill_name: str, receipt: Optional[dict] = None
) -> Ownership:
    """Classify one skill directory under `<repo_root>/.claude/skills/`.

    Pass `receipt` to reuse a single read across a whole corpus. When it is
    omitted the receipt is read from disk. Note that None is also the value
    `bundle_copy.read_receipt` returns for an absent or corrupt receipt, so
    callers sweeping a corpus should read it once themselves and pass the
    result rather than relying on the default.
    """
    repo_root = pathlib.Path(repo_root)
    claude = repo_root / ".claude"
    skill_md = claude / "skills" / skill_name / "SKILL.md"

    if is_foundry_source(repo_root):
        return Ownership(
            skill=skill_name,
            verdict=FOUNDRY_SOURCE,
            signal="scripts/promote.sh and scripts/prod-repo.txt both present",
            may_propose_edit=True,
            notes=["This tree is the bundle source. Fix here, per operating rule 6."],
        )

    if receipt is None:
        receipt = bundle_copy.read_receipt(claude)

    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""

    if _OWNER_PROJECT.search(text) or skill_name in _project_skills_names(repo_root):
        return Ownership(
            skill=skill_name,
            verdict=CONSUMER_OWNED,
            signal="owner: project marker, or named in .claude/project-skills.md",
            may_propose_edit=True,
        )

    if receipt is None:
        return Ownership(
            skill=skill_name,
            verdict=UNDETERMINABLE,
            signal="no install receipt, or the receipt did not parse",
            may_propose_edit=False,
            raise_to="raise-foundry-request",
            notes=[
                "Failed closed. Absent evidence is not evidence of consumer "
                "ownership, so this is raised rather than fixed."
            ],
        )

    installed = set(receipt.get("files", {}).keys())
    prefix = f"skills/{skill_name}/"
    if any(rel.startswith(prefix) for rel in installed):
        return Ownership(
            skill=skill_name,
            verdict=BUNDLE_MANAGED,
            signal=".plan-foundry-bundle-files records this path",
            may_propose_edit=False,
            raise_to="raise-foundry-request",
        )

    if skill_name in _ledger_paths(repo_root):
        return Ownership(
            skill=skill_name,
            verdict=BUNDLE_MANAGED,
            signal="named in _shared/bundle-contract.json deprecations",
            may_propose_edit=False,
            raise_to="raise-foundry-request",
            notes=[
                "The receipt does not record this path and the ledger does. "
                "The bundle dropped it on purpose."
            ],
        )

    return Ownership(
        skill=skill_name,
        verdict=UNATTRIBUTED,
        signal="absent from the receipt and carries no consumer-owned marker",
        may_propose_edit=False,
        raise_to=None,
        notes=[
            "Could be another harness's bundle or an unmarked local skill. "
            "Add `owner: project` to its frontmatter to have it audited with "
            "fixes proposed."
        ],
    )


def classify_corpus(repo_root) -> list:
    """Classify every skill directory under `<repo_root>/.claude/skills/`."""
    repo_root = pathlib.Path(repo_root)
    skills_dir = repo_root / ".claude" / "skills"
    if not skills_dir.is_dir():
        return []
    receipt = bundle_copy.read_receipt(repo_root / ".claude")
    out = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir() or child.name == "_shared":
            continue
        if not (child / "SKILL.md").is_file():
            continue
        out.append(classify_skill_ownership(repo_root, child.name, receipt=receipt))
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path(os.getcwd())
    for own in classify_corpus(root):
        edit = "fix" if own.may_propose_edit else "raise"
        print(f"{own.skill}\t{own.verdict}\t{edit}\t{own.signal}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
