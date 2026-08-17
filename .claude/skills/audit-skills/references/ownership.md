# Who owns this skill

`audit-skills` proposes fixes against some skills and raises requests against
others, and this document states which branch applies to a skill. The mechanism is
[`../lib/skill_ownership.py`](../lib/skill_ownership.py). This document is the
policy, and where the policy and the code disagree the code is the defect.

## Why the branch exists

A consumer's `.claude/` is bundle-managed. A fix applied to a bundle file
there is overwritten at the next sync and the defect returns. An auditor that
edited bundle files would therefore produce work that disappears, and a consumer who
believes a defect is closed when it is not. The consumer's false belief is the real
damage.

This bundle's own working tree is the opposite case, because the working tree is the
source, so a sure mechanical defect is fixed here with a test rather than filed.

## The authoritative signal

The install receipt at `.claude/.bundle-receipts/plan_foundry.files` is
**authoritative**, and namespaced by bundle identity (`plan_foundry`) so a sibling
bundle sharing this consumer's `.claude/` cannot overwrite this bundle's own
record. The receipt records every path this bundle actually wrote into the
target, which makes it a record of what happened rather than an inference from
what the bundle currently ships. Read the receipt with
`read_receipt(claude, bundle="plan_foundry")` in `_shared/bundle_copy.py`. That
call falls back to the legacy `.plan-foundry-bundle-files` path, adopting that
file only when its own `sha` header matches this bundle's version pin.

The deprecation ledger at `_shared/bundle-contract.json` is consulted **second**, and
only to explain a path the receipt records but the bundle no longer carries. The ledger
states what the bundle dropped on purpose, which is a claim about the bundle rather
than a record of this install.

Nothing else is a signal. Do not infer ownership from a directory name, a writing
style, or whether a skill looks like something this bundle would ship.

## The verdicts

**foundry_source.** The working tree is the bundle source itself, detected by
`scripts/promote.sh` and `scripts/prod-repo.txt` both being present. Every skill here
is bundle source. Audit normally and propose fixes.

**bundle_managed.** The receipt records the path, or the deprecation ledger names the
path. The skill is this bundle's file in someone else's repository. Audit the skill
normally, propose no edit, and emit the finding as a request through
`raise-foundry-request`. Report the finding as raised rather than fixed.

**consumer_owned.** Positive evidence that the skill is the consumer's own work: an
`owner: project` marker in its frontmatter, or a listing in
`.claude/project-skills.md`. Audit normally and propose fixes.

**unattributed.** The skill is on disk, absent from the receipt, and carries no
consumer-owned marker. This is the **third-party** case, and this case needs the most
care. The skill may belong to another harness's bundle, or it may be an unmarked local
skill.

Report the skill as third-party-owned and propose no edit. Where the owning harness is
identifiable, emit the finding through that harness's request channel. Where no owning
harness is identifiable, say so and stop. Do not guess at an owner.

Do not fall back to treating an unattributed skill as consumer-owned. A skill absent
from this bundle's receipt is not thereby the consumer's own work, and the fact that
this bundle did not install it says nothing about who did. The remedy for a local
skill caught by this branch is one line: add `owner: project` to its frontmatter, and
the skill is then audited with fixes proposed.

**undeterminable.** No receipt exists, or the receipt did not parse.

## Fail closed

Where ownership cannot be determined, treat the skill as bundle-managed and raise
rather than fix.

The asymmetry is the whole argument. The cost of wrongly raising is one redundant
request, which a maintainer closes in a minute. The cost of wrongly fixing is work
destroyed at the next sync plus a consumer who believes a defect is closed when it is
not, and neither outcome surfaces anywhere.

Absence of evidence is not evidence of consumer ownership. A missing receipt is the
bootstrap case and a corrupt one is a fault, and neither one grants permission to fix.

## Reporting

Every finding in the report carries the verdict and the signal that produced it, so a
reader can check the branch rather than trusting the verdict. A finding against a skill
that was not fixed names the channel that received the finding, or states that no
channel was identifiable.
