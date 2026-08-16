"""
claim_carry.py - Persistent identity for a handoff-carried claim.

Originating PLAN: PLAN-AL1 (Give a handoff-carried claim a persistent
identity: checkable staleness, a drop guard, and repeat escalation, 2026-08-06).
Closes FOUNDRYREQ-horse-chestnut-brickhouse-20260805-1701.

Design: a claim written into a handoff's `## Constraints & do-nots` or
`## Blocking decisions` section carries a stable `CLAIM-<kebab-nickname>` id
(author-assigned, reused verbatim on restatement - no allocator, no hash; see
`../handoff-next-session/references/claim-carry-gate.md`). A checkable claim
also carries a trailing `check: <shell command>` line (exit 0 = the claim
holds); a freeform claim does not and is never re-run (attestation, not tree
evidence, per the same reference).

Four functions, each a pure operation on already-read text / dicts - no git,
no file I/O of its own, matching `resume_preflight.py`'s existing shape so a
target predating this mechanism (or with no in-flight claims at all) degrades
to the empty case rather than breaking:

  parse_claims(handoff_text)                       -> dict[id, claim]
  diff_dropped(prior_claims, successor_text)        -> list[id]
  run_claim_checks(claims, repo_root, timeout=30)   -> dict[id, result]
  next_baseline(prior_baseline, current_claims)     -> (dict, list[id])

Escalation threshold: a claim whose `carried_count` reaches this many
consecutive unresolved carries must move to `## Blocking decisions` in the
next handoff (enforced by `write-handoff.md` Step 2.6e, not by this module).
Named once here rather than duplicated at each call site.
"""

import re
import subprocess

ESCALATION_THRESHOLD = 3

# A CLAIM line inside Constraints & do-nots / Blocking decisions looks like:
#   CLAIM-some-nickname: the claim's one-line prose
#   check: <shell command>          (optional, next non-blank line)
_CLAIM_LINE_RE = re.compile(
    r"CLAIM-(?P<id>[a-z0-9][a-z0-9-]*)\s*:\s*(?P<prose>[^\n]+)"
)
_CHECK_LINE_RE = re.compile(r'^\s*check:\s*"?(?P<cmd>.+?)"?\s*$')

_SECTION_HEADINGS = ("## Constraints & do-nots", "## Blocking decisions")


def _named_sections(handoff_text):
    """Yield the text of each Constraints & do-nots / Blocking decisions
    section (from its heading to the next H2 heading or end of file)."""
    lines = handoff_text.splitlines()
    idx = 0
    n = len(lines)
    while idx < n:
        line = lines[idx]
        stripped = line.strip()
        if stripped in _SECTION_HEADINGS:
            body = []
            idx += 1
            while idx < n and not lines[idx].startswith("## "):
                body.append(lines[idx])
                idx += 1
            yield "\n".join(body)
        else:
            idx += 1


def parse_claims(handoff_text):
    """Extract every CLAIM-<id> occurrence inside the two named sections.

    Returns {id: {"nickname": str, "prose": str, "check": str or None}}.
    An id appearing outside both named sections is ignored - claim identity
    is scoped to the two sections the gate governs.
    """
    claims = {}
    if not handoff_text:
        return claims
    for section_text in _named_sections(handoff_text):
        section_lines = section_text.splitlines()
        for i, line in enumerate(section_lines):
            m = _CLAIM_LINE_RE.search(line)
            if not m:
                continue
            claim_id = f"CLAIM-{m.group('id')}"
            prose = m.group("prose").strip()
            check_cmd = None
            if i + 1 < len(section_lines):
                cm = _CHECK_LINE_RE.match(section_lines[i + 1])
                if cm:
                    check_cmd = cm.group("cmd").strip()
            claims[claim_id] = {
                "nickname": m.group("id"),
                "prose": prose,
                "check": check_cmd,
            }
    return claims


def diff_dropped(prior_claims, successor_text):
    """Return the ids present in prior_claims that are silently missing from
    successor_text - present neither as a restatement nor an explicit
    removal note ("CLAIM-<id> ... removed", case-insensitive).
    """
    if not prior_claims:
        return []
    dropped = []
    text = successor_text or ""
    for claim_id in prior_claims:
        if claim_id in text:
            continue
        removal_re = re.compile(
            re.escape(claim_id) + r".{0,80}?removed", re.IGNORECASE | re.DOTALL
        )
        if removal_re.search(text):
            continue
        dropped.append(claim_id)
    return dropped


def run_claim_checks(claims, repo_root, timeout=30):
    """Run each checkable claim's `check:` command against repo_root.

    Fail-open, mirroring resume_preflight.py's existing subprocess pattern:
    an unrunnable or timed-out command is `checked: False` and NEVER counts
    as stale - only a confirmed non-zero exit does. A claim with no `check:`
    line is `checked: False` with a reason naming the D2 freeform scope
    limit, never re-run.

    Returns {id: {"checked": bool, "stale": bool, "reason": str (optional)}}.
    """
    results = {}
    if not claims:
        return results
    for claim_id, claim in claims.items():
        check_cmd = claim.get("check")
        if not check_cmd:
            results[claim_id] = {
                "checked": False,
                "stale": False,
                "reason": "freeform - not re-verified (D2)",
            }
            continue
        try:
            proc = subprocess.run(
                check_cmd,
                shell=True,
                cwd=str(repo_root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            results[claim_id] = {
                "checked": True,
                "stale": proc.returncode != 0,
            }
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            results[claim_id] = {
                "checked": False,
                "stale": False,
                "reason": f"check unrunnable - {exc}",
            }
    return results


def next_baseline(prior_baseline, current_claims):
    """Compute the successor `## Carried-claims baseline` mapping.

    For every id in current_claims, carry `carried_count` forward from
    prior_baseline plus one if present there, else start at 1. An id absent
    from current_claims (resolved or removed) is dropped from the new
    baseline entirely - no lingering entries for claims no longer carried.

    Returns (new_baseline dict, escalated ids list) where escalated ids are
    those whose carried_count now reaches ESCALATION_THRESHOLD.
    """
    prior_baseline = prior_baseline or {}
    new_baseline = {}
    escalated = []
    for claim_id, claim in current_claims.items():
        prior_entry = prior_baseline.get(claim_id)
        carried_count = (prior_entry.get("carried_count", 0) + 1) if prior_entry else 1
        new_baseline[claim_id] = {
            "nickname": claim.get("nickname", claim_id.replace("CLAIM-", "", 1)),
            "check": claim.get("check") or "",
            "carried_count": carried_count,
        }
        if carried_count >= ESCALATION_THRESHOLD:
            escalated.append(claim_id)
    return new_baseline, escalated
