# Who owns this skill

`audit-skills` proposes fixes against some skills and raises requests against
others. This decides which. The mechanism is
[`../lib/skill_ownership.py`](../lib/skill_ownership.py). This document is the
policy, and where the two disagree the code is the bug.

## Why the branch exists

A consumer's `.claude/` is bundle-managed territory. A fix applied to a bundle file
there is overwritten at the next sync and the defect returns. So an auditor that
edited bundle files would produce work that disappears, and a consumer who believes a
defect is closed when it is not. The second is the real damage.

This bundle's own working tree is the opposite case. It is the source, so a sure
mechanical defect is fixed here on the spot with a test rather than filed.

## The authoritative signal

The install receipt at `.claude/.plan-foundry-bundle-files` is **authoritative**. It
records every path this bundle actually wrote into the target, which makes it a
record of what happened rather than an inference from what the bundle currently
ships. Read it with `read_receipt` in `_shared/bundle_copy.py`.

The deprecation ledger at `_shared/bundle-contract.json` is consulted **second**, and
only to explain a path the receipt records but the bundle no longer carries. It says
what the bundle dropped on purpose, which is a statement about the bundle rather than
a record of this install.

Nothing else is a signal. Do not infer ownership from a directory name, a writing
style, or whether a skill looks like something this bundle would ship.

## The verdicts

**foundry_source.** The working tree is the bundle source itself, detected by
`scripts/promote.sh` and `scripts/prod-repo.txt` both being present. Every skill here
is bundle source. Audit normally and propose fixes.

**bundle_managed.** The receipt records the path, or the deprecation ledger names it.
This is this bundle's file in someone else's repository. Audit it normally, propose no
edit, and emit the finding as a request through `raise-foundry-request`. Report it as
raised rather than fixed.

**consumer_owned.** Positive evidence that the skill is the consumer's own work: an
`owner: project` marker in its frontmatter, or a listing in
`.claude/project-skills.md`. Audit normally and propose fixes.

**unattributed.** On disk, absent from the receipt, carrying no consumer-owned marker.
This is the **third-party** case, and it is where most of the care goes. The skill may
belong to another harness's bundle, or it may be an unmarked local skill.

Report it as third-party-owned and propose no edit. Where the owning harness is
identifiable, emit the finding through that harness's request channel. Where it is
not, say so and stop. Do not guess at an owner.

Do not fall back to treating an unattributed skill as consumer-owned. A skill absent
from this bundle's receipt is not thereby the consumer's own work, and the fact that
this bundle did not install it says nothing about who did. The remedy for a local
skill caught by this is one line: add `owner: project` to its frontmatter and it is
audited with fixes proposed.

**undeterminable.** No receipt, or a receipt that did not parse.

## Fail closed

Where ownership cannot be determined, treat the skill as bundle-managed and raise
rather than fix.

The asymmetry is the whole argument. The cost of wrongly raising is one redundant
request, which a maintainer closes in a minute. The cost of wrongly fixing is work
destroyed at the next sync plus a consumer who believes a defect is closed when it is
not, and nothing surfaces either.

Absence of evidence is not evidence of consumer ownership. A missing receipt is the
bootstrap case and a corrupt one is a fault, and neither is permission.

## Reporting

Every finding in the report carries the verdict and the signal that produced it, so a
reader can check the branch rather than trust it. A finding against a skill that was
not fixed says which channel it was raised to, or that no channel was identifiable.
