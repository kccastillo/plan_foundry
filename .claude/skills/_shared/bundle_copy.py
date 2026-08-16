"""
bundle_copy.py - shared helper for init-plan-foundry and plan-foundry-sync.

Exposes:
  - BUNDLE_MANAGED_DIRS: tuple of the four top-level subdirs under .claude
    that the bundle owns (skills, agents, commands, hooks).
  - copy_bundle_managed(bundle_claude, target_claude) -> CopyReport
  - resolve_version(bundle_root) -> dict
  - write_version_file(bundle_root, target_claude, data=None) -> dict
  - read_version_file(target_claude) -> Optional[dict]
  - SYNC_INCOMPLETE_FILENAME: the incomplete-sync marker's filename.
  - mark_sync_incomplete(target_claude, previous_sha, target_sha) -> None
  - read_sync_incomplete(target_claude) -> Optional[dict]
  - clear_sync_incomplete(target_claude) -> None

Design rationale: PLAN-AC5 (2026-05-19). The bundle propagates to target
projects by copy, not symlink. This module is the single source of truth
for which paths under .claude/ are bundle-managed and how the version pin
is recorded.

Never deletes from target. Bundle files that no longer exist upstream are
listed in CopyReport.stale_in_target but left in place - explicit cleanup
is the user's call.

The install receipt is now bundle-namespaced (PLAN-AK5): each bundle installing
into a shared `.claude/` writes and reads its own receipt at
`.claude/.bundle-receipts/<bundle>.files`, because two bundles sharing the
legacy single-filename receipt would each overwrite the other's ownership
record, making a per-bundle divergence check impossible. The legacy
`.plan-foundry-bundle-files` path is still read as a fallback and never
deleted - see read_receipt's docstring for the adoption rule.

Required sync sequence (PLAN-AK6, supersedes the PLAN-AH7 Step 1 ordering
below - load-bearing, do not reorder):

    1. read the existing receipt (before the clone, alongside the existing
       pin read at sync.py:57)
    2. clone
    3. mark the incomplete-sync marker (first write to the target)
    4. copy
    5. classify
    6. quarantine
    7. sweep
    8. write the new receipt
    9. write the version pin (data pre-resolved via resolve_version, before
       the copy, so its `synced` timestamp and the receipt's sha describe
       the same moment)
    10. clear the incomplete-sync marker

The version pin is deliberately the second-to-last write and the marker
clear is the last: every step above the pin write is what makes the pin's
claim true, so a run that fails at any of them must not have advanced the
pin - PLAN-AK6 (2026-08-06), closing a defect where a crashed sync left the
pin naming a version the target never finished installing.

If the receipt is written any earlier than step 8 - in particular
immediately after the copy - then classify_stale's gone_upstream is always
empty, quarantine never fires on any consumer, and receipt_absent never
reports true. The mechanism would appear to work (report shape unchanged,
tests of shape still pass) while silently doing nothing. Every caller of
write_receipt must position the call at the end of this sequence.

PLAN-AH8: read_bundle_contract(bundle_root) below is deliberately duplicated
in _shared/preflight.py rather than shared via import. preflight.py must
stay import-free of this module - see this module's read_bundle_contract
docstring and preflight.py's module docstring for why. This looks like
removable redundancy and it is not.
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import os
import pathlib
import shutil
import stat
import subprocess
from typing import Optional

BUNDLE_MANAGED_DIRS = ("skills", "agents", "commands", "hooks")
VERSION_FILENAME = ".plan-foundry-bundle-version"


@dataclasses.dataclass
class CopyReport:
    files_copied: list[str] = dataclasses.field(default_factory=list)
    files_unchanged: list[str] = dataclasses.field(default_factory=list)
    project_additions: list[str] = dataclasses.field(default_factory=list)
    stale_in_target: list[str] = dataclasses.field(default_factory=list)
    shim_skipped: list[str] = dataclasses.field(default_factory=list)
    refused_not_ours: list[str] = dataclasses.field(default_factory=list)
    forced_overwrites: list[str] = dataclasses.field(default_factory=list)

    def summary(self) -> str:
        return (
            f"copied={len(self.files_copied)} "
            f"unchanged={len(self.files_unchanged)} "
            f"project_additions={len(self.project_additions)} "
            f"stale_in_target={len(self.stale_in_target)} "
            f"shim_skipped={len(self.shim_skipped)} "
            f"refused_not_ours={len(self.refused_not_ours)} "
            f"forced_overwrites={len(self.forced_overwrites)}"
        )


def _file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _files_equal(a: pathlib.Path, b: pathlib.Path) -> bool:
    try:
        sa = a.stat()
        sb = b.stat()
    except FileNotFoundError:
        return False
    if sa.st_size != sb.st_size:
        return False
    if sa.st_size > 1_048_576:
        return _file_sha256(a) == _file_sha256(b)
    return a.read_bytes() == b.read_bytes()


def _walk_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Return all regular file paths under root (relative paths from root)."""
    if not root.exists():
        return []
    out = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = pathlib.Path(dirpath) / name
            out.append(full.relative_to(root))
    return out


# The literal `shim_body` (preflight.py) opens every shim it generates with.
# Testing for it means "is the destination a shim we wrote", which is a fact
# about our own output rather than a guess about which of two files is richer.
SHIM_MARKER = "This surface is deprecated. Replaced by:"


def _is_shim(path: pathlib.Path) -> bool:
    """True when `path` holds a deprecation shim this bundle generated."""
    try:
        return SHIM_MARKER in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _shimmed_relpaths(deprecations) -> set:
    """Bundle-relative posix paths carrying a file-addressed ledger entry.

    kind: helper entries address a `file.py::symbol` and have no file-level
    path, so they are never shim-generated and never match a copy target.
    """
    out = set()
    for entry in deprecations or ():
        if entry.get("kind") not in ("skill", "reference", "hook"):
            continue
        path = entry.get("path", "")
        if path.startswith(".claude/"):
            out.add(path[len(".claude/"):])
    return out


def copy_bundle_managed(
    bundle_claude: pathlib.Path,
    target_claude: pathlib.Path,
    deprecations=None,
    receipt=None,
    force: bool = False,
) -> CopyReport:
    """Copy bundle/.claude/{skills,agents,commands,hooks}/ into target/.claude/.

    Never deletes from target. Returns a CopyReport summarising what
    happened to each file under the four bundle-managed dirs.

    `deprecations` is the ledger from read_bundle_contract()["deprecations"].
    When supplied, a bundle file carrying a file-addressed entry is NOT copied
    over a destination that exists and is not itself a shim - the target owns
    something richer at that path, and a shim advertising a successor product
    must never overwrite the successor. Those paths land in
    report.shim_skipped. Omitting the argument keeps the plain-copy behaviour.

    The ledger is passed in rather than read here because this function's
    contract is a copy over two trees, and both callers already hold the
    contract (PLAN-AJ6 D2).

    `receipt` (PLAN-AK5) is the caller's parsed install receipt (the dict
    read_receipt returns), or None. When None, every destination whose bytes
    differ from the incoming source is copied exactly as before and nothing
    new is recorded - the caller reports the unverified condition once, per
    D6, rather than listing every file. When a dict is supplied, a
    destination that exists, differs from the source, and either is absent
    from receipt["files"] or is present with a recorded sha256 that no
    longer matches the destination's current bytes is judged "not ours": with
    force=False it is skipped and its display string is appended to
    report.refused_not_ours, and with force=True it is copied and appended to
    both files_copied and forced_overwrites. A destination whose recorded
    sha256 still matches is copied as today, with nothing new recorded.

    A refused path is deliberately absent from files_copied, files_unchanged,
    project_additions and stale_in_target alike, so it never reaches
    classify_stale and is never misread as gone_upstream, and so a caller
    passing files_copied/files_unchanged to write_receipt cannot record a
    foreign file as this bundle's own. A forced overwrite is the opposite: it
    lands in files_copied and so enters the next receipt, which is what makes
    a resolved conflict self-clear.
    """
    bundle_claude = pathlib.Path(bundle_claude)
    target_claude = pathlib.Path(target_claude)
    shimmed = _shimmed_relpaths(deprecations)
    report = CopyReport()
    receipt_files = receipt.get("files", {}) if receipt is not None else None

    target_claude.mkdir(parents=True, exist_ok=True)

    for sub in BUNDLE_MANAGED_DIRS:
        bundle_sub = bundle_claude / sub
        target_sub = target_claude / sub
        if not bundle_sub.exists():
            continue

        bundle_files = set(_walk_files(bundle_sub))
        target_files = set(_walk_files(target_sub))

        for rel in sorted(bundle_files):
            src = bundle_sub / rel
            dst = target_sub / rel
            display = f"{sub}/{rel.as_posix()}"
            if dst.exists() and _files_equal(src, dst):
                report.files_unchanged.append(display)
                continue
            if display in shimmed and dst.exists() and not _is_shim(dst):
                report.shim_skipped.append(display)
                continue
            if receipt_files is not None and dst.exists():
                recorded = receipt_files.get(display)
                current = _file_sha256(dst)
                if recorded is None or recorded != current:
                    if force:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                        report.files_copied.append(display)
                        report.forced_overwrites.append(display)
                    else:
                        report.refused_not_ours.append(display)
                    continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            report.files_copied.append(display)

        for rel in sorted(target_files - bundle_files):
            display = f"{sub}/{rel.as_posix()}"
            if _is_under_known_subskill(rel, bundle_files):
                report.project_additions.append(display)
            else:
                report.stale_in_target.append(display)

    return report


def _is_under_known_subskill(
    rel: pathlib.Path, bundle_files: set[pathlib.Path]
) -> bool:
    """Heuristic: a target file is a project addition (vs stale) if its
    top-level subdir under the bundle-managed dir is NOT present in the bundle.
    Files under a bundle-known subskill that the bundle dropped are stale.

    Example under skills/:
      bundle has skills/foo/A.md, skills/foo/B.md.
      target has skills/foo/A.md, skills/foo/C.md, skills/myproj/X.md.
      - skills/foo/C.md -> stale (bundle owns skills/foo/, dropped C.md)
      - skills/myproj/X.md -> project addition (bundle doesn't own skills/myproj/)
    """
    parts = rel.parts
    if len(parts) < 2:
        # File directly under skills/ etc. - if bundle doesn't have it, treat
        # as project addition (bundle structure puts everything under a named
        # subdir).
        return True
    top = parts[0]
    bundle_tops = {p.parts[0] for p in bundle_files if p.parts}
    return top not in bundle_tops


CONTRACT_FILENAME = "bundle-contract.json"


def read_bundle_contract(bundle_root: pathlib.Path) -> dict:
    """Read <bundle_root>/.claude/skills/_shared/bundle-contract.json.

    Returns the parsed contract dict, or {"schema_version": "", "deprecations": []}
    when the file is absent, empty, or malformed JSON. Never raises. Read with
    encoding="utf-8".

    PLAN-AH8: this read is deliberately duplicated, not shared. The other copy
    lives inline in _shared/preflight.py. preflight.py must not import this
    module - by the time sync's pre-flight runs, "bundle_copy" is already
    bound in sys.modules to the consumer's installed copy (see sync.py's
    _import_local_helpers, called before the clone), so any import of
    bundle_copy from preflight silently returns pre-this-wave code instead of
    the freshly-cloned bundle's.

    A third instance of this same inline-read constraint lives in
    plan-foundry-sync/lib/sync.py's installed_bundle_identity, which reads
    the same bundle-contract.json for a narrower question - who owns the
    installed _shared/ - before anything under _shared/ can be trusted at
    all (PLAN-AL8 D2). scripts/ci/check-bootstrap-read-parity.py (PLAN-AL8
    D3) fails CI if this function, preflight.py's inlined copy, and
    installed_bundle_identity ever disagree on the same fixture input. The
    duplication is intentional and load-bearing - do not "simplify" it into
    a shared import later.
    """
    bundle_root = pathlib.Path(bundle_root)
    path = bundle_root / ".claude" / "skills" / "_shared" / CONTRACT_FILENAME
    try:
        import json

        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            return {"schema_version": "", "deprecations": []}
        if "schema_version" not in data:
            data["schema_version"] = ""
        if "deprecations" not in data:
            data["deprecations"] = []
        return data
    except (OSError, ValueError):
        return {"schema_version": "", "deprecations": []}


def _run_git(args: list[str], cwd: pathlib.Path) -> Optional[str]:
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def resolve_version(bundle_root: pathlib.Path) -> dict:
    """Compute the sha/tag/synced/schema_version dict for `bundle_root`,
    writing nothing.

    Read-only counterpart to write_version_file's own computation, split out
    (PLAN-AK6) so a caller that needs the sha before the pin is written -
    to name it in an incomplete-sync marker, or in a receipt written before
    the pin - can call this once and pass the result back to
    write_version_file(..., data=...). Calling resolve_version and
    write_version_file separately would compute `synced` twice and the pin's
    timestamp would disagree with whatever else recorded the first one.

    Tag is "" when no exact-match tag exists. schema_version is sourced from
    read_bundle_contract(bundle_root) and is "" when the incoming bundle
    carries no contract (predates PLAN-AH8) or the contract is malformed -
    the key is always present, never omitted, so the pin's shape stays
    stable across bundle versions.
    """
    bundle_root = pathlib.Path(bundle_root)
    sha = _run_git(["rev-parse", "HEAD"], bundle_root) or ""
    tag = _run_git(["describe", "--tags", "--exact-match"], bundle_root) or ""
    synced = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    schema_version = read_bundle_contract(bundle_root).get("schema_version", "")
    return {"sha": sha, "tag": tag, "synced": synced, "schema_version": schema_version}


def write_version_file(
    bundle_root: pathlib.Path,
    target_claude: pathlib.Path,
    data: Optional[dict] = None,
) -> dict:
    """Write target/.claude/.plan-foundry-bundle-version with sha/tag/synced/schema_version.

    Returns the dict that was written. When `data` is supplied it is written
    verbatim - the caller already resolved it via resolve_version(bundle_root)
    and this call must not recompute (see resolve_version's docstring for
    why: a second computation would give the pin's `synced` timestamp and
    whatever else the caller recorded first a different moment). When `data`
    is omitted, this call computes it itself via resolve_version(bundle_root),
    which is the exact behaviour every caller that predates this parameter
    already relies on - the existing positional signature and return value
    are unchanged.
    """
    bundle_root = pathlib.Path(bundle_root)
    target_claude = pathlib.Path(target_claude)
    data = data if data is not None else resolve_version(bundle_root)
    sha = data.get("sha", "")
    tag = data.get("tag", "")
    synced = data.get("synced", "")
    schema_version = data.get("schema_version", "")

    target_claude.mkdir(parents=True, exist_ok=True)
    target = target_claude / VERSION_FILENAME
    tmp = target.with_suffix(target.suffix + ".tmp")
    body = f"sha={sha}\ntag={tag}\nsynced={synced}\nschema_version={schema_version}\n"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)
    return data


def read_version_file(target_claude: pathlib.Path) -> Optional[dict]:
    """Read target/.claude/.plan-foundry-bundle-version; return parsed dict or None."""
    target_claude = pathlib.Path(target_claude)
    path = target_claude / VERSION_FILENAME
    if not path.exists():
        return None
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def bundle_version_string(target_claude: pathlib.Path) -> str:
    """Return a single human-readable version string for the pin at
    target_claude: the pin's tag, falling back to its sha, falling back to
    "" when no pin exists or both fields are empty. Builds on
    read_version_file rather than a second reader.
    """
    pin = read_version_file(target_claude)
    if pin is None:
        return ""
    tag = pin.get("tag", "")
    if tag:
        return tag
    return pin.get("sha", "")


# ---------------------------------------------------------------------------
# PLAN-AK6: the incomplete-sync marker. Written before the copy (the first
# write to the target) and cleared only after the version pin is written, so
# a run that starts and does not finish leaves a marker the next currency
# check reads ahead of any sha comparison. Never raises - the marker degrades
# to "absent" on any read failure, the same posture read_version_file takes.
# ---------------------------------------------------------------------------

SYNC_INCOMPLETE_FILENAME = ".plan-foundry-sync-incomplete"


def mark_sync_incomplete(
    target_claude: pathlib.Path, previous_sha: str, target_sha: str
) -> None:
    """Write target/.claude/.plan-foundry-sync-incomplete, naming the sha the
    run started from, the sha it is moving to, and when it started.

    Means: the last sync against this target started and did not finish.
    The repair is another sync - this marker is not a lock, does not block
    a later run, and is written through a `.tmp` sibling and os.replace, in
    the pin file's key-value format. Creates target_claude if absent. Never
    raises.
    """
    target_claude = pathlib.Path(target_claude)
    started = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    body = (
        f"previous_sha={previous_sha}\ntarget_sha={target_sha}\nstarted={started}\n"
    )
    target_claude.mkdir(parents=True, exist_ok=True)
    target = target_claude / SYNC_INCOMPLETE_FILENAME
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)


def read_sync_incomplete(target_claude: pathlib.Path) -> Optional[dict]:
    """Read target/.claude/.plan-foundry-sync-incomplete.

    Returns the parsed {"previous_sha", "target_sha", "started"} dict, or
    None when the file is absent, unreadable, or malformed. Never raises -
    a marker that cannot be parsed is treated the same as no marker.
    """
    target_claude = pathlib.Path(target_claude)
    path = target_claude / SYNC_INCOMPLETE_FILENAME
    try:
        if not path.exists():
            return None
        out: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
        return out
    except (OSError, UnicodeDecodeError):
        return None


def clear_sync_incomplete(target_claude: pathlib.Path) -> None:
    """Remove target/.claude/.plan-foundry-sync-incomplete.

    A no-op when the marker is already absent. Never raises.
    """
    target_claude = pathlib.Path(target_claude)
    path = target_claude / SYNC_INCOMPLETE_FILENAME
    try:
        path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# PLAN-AH7: install receipt, three-set classification, quarantine, sweep.
#
# See the module docstring above for the required sequence these pieces must
# be called in. All of this is additive - copy_bundle_managed, write_version_file,
# read_version_file, _is_under_known_subskill and CopyReport.stale_in_target
# are untouched (D7).
# ---------------------------------------------------------------------------

RECEIPT_FILENAME = ".plan-foundry-bundle-files"
RECEIPT_DIRNAME = ".bundle-receipts"
QUARANTINE_DIRNAME = ".plan-foundry-quarantine"


def receipt_path(target_claude: pathlib.Path, bundle: str) -> pathlib.Path:
    """Return the namespaced receipt path for `bundle` under `target_claude`:
    <target_claude>/.bundle-receipts/<bundle>.files.

    Namespacing (PLAN-AK5 D4) is what makes a divergence check possible at
    all: two bundles installed into the same target both wrote the legacy
    single filename, so each sync overwrote the other's ownership record.
    """
    target_claude = pathlib.Path(target_claude)
    return target_claude / RECEIPT_DIRNAME / f"{bundle}.files"


def write_receipt(
    target_claude: pathlib.Path, relpaths: list, sha: str, bundle: str = ""
) -> dict:
    """Write the namespaced install receipt at
    target/.claude/.bundle-receipts/<bundle>.files.

    Header lines record `sha=` (the bundle sha this install/sync pinned to),
    `written=` (UTC ISO8601) and `bundle=` (the bundle identity this receipt
    belongs to), followed by one `<relpath>\\t<sha256>` line per installed
    file, sorted. `relpaths` are relative to `target_claude` (the same
    display strings CopyReport.files_copied/files_unchanged use, e.g.
    "skills/foo/SKILL.md"). `bundle` defaults to "" and is treated as
    "plan_foundry" inside this function, so a caller written before this
    parameter existed keeps working unchanged.

    Atomic via a `.tmp` sibling and os.replace, mirroring write_version_file.
    Read and write with encoding="utf-8". Creates .bundle-receipts/ if absent.

    MUST be called at the end of the sequence recorded in the module
    docstring - after classify/quarantine/sweep, and before the version pin
    write and the incomplete-sync marker clear that now follow it (PLAN-AK6).
    Never immediately after the copy - that is where an earlier revision of
    this sequence wrote the version pin, and where the natural reading would
    put this call; do not follow that instinct here.
    """
    bundle = bundle or "plan_foundry"
    target_claude = pathlib.Path(target_claude)
    written = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    entries: dict[str, str] = {}
    for rel in sorted(set(relpaths)):
        path = target_claude / rel
        try:
            entries[rel] = _file_sha256(path)
        except OSError:
            # File vanished between the copy and the receipt write - skip it
            # rather than raising; the receipt records what is actually there.
            continue

    lines = [f"sha={sha}", f"written={written}", f"bundle={bundle}"]
    for rel in sorted(entries):
        lines.append(f"{rel}\t{entries[rel]}")

    target = receipt_path(target_claude, bundle)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    body = "\n".join(lines) + "\n"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)
    return {"sha": sha, "written": written, "bundle": bundle, "files": entries}


def _parse_receipt_text(text: str) -> Optional[dict]:
    """Parse receipt file content shared by both the namespaced and legacy
    reads. Accepts the mandatory sha=/written= header lines followed by an
    optional bundle= line, then tab-separated relpath/sha256 body lines.
    Returns None on any malformed shape.
    """
    lines = text.splitlines()
    if len(lines) < 2:
        return None
    header: dict[str, str] = {}
    idx = 0
    for key_expected in ("sha", "written"):
        if idx >= len(lines) or "=" not in lines[idx]:
            return None
        key, _, value = lines[idx].partition("=")
        key = key.strip()
        if key != key_expected:
            return None
        header[key] = value.strip()
        idx += 1
    if idx < len(lines) and lines[idx].startswith("bundle="):
        key, _, value = lines[idx].partition("=")
        header[key.strip()] = value.strip()
        idx += 1
    files: dict[str, str] = {}
    for line in lines[idx:]:
        if not line.strip():
            continue
        if "\t" not in line:
            return None
        rel, _, digest = line.partition("\t")
        files[rel.strip()] = digest.strip()
    return {
        "sha": header.get("sha", ""),
        "written": header.get("written", ""),
        "bundle": header.get("bundle", ""),
        "files": files,
    }


def read_receipt(target_claude: pathlib.Path, bundle: str = "") -> Optional[dict]:
    """Read the install receipt for `bundle` under target_claude.

    Reads the namespaced path (.bundle-receipts/<bundle>.files) first.
    `bundle` defaults to "" and is treated as "plan_foundry" inside this
    function, so a caller written before this parameter existed keeps
    working unchanged.

    When the namespaced path is absent, falls back to the legacy
    .plan-foundry-bundle-files path (PLAN-AK5 D6) and applies this repo's
    three-case adoption rule:

      - No namespaced receipt and no legacy receipt: returns None. Nothing
        can be judged (pre-receipt install).
      - No namespaced receipt, a legacy receipt present, and the legacy
        receipt's sha header equals the sha this bundle's own version pin
        names (read_version_file(target_claude)): the pin is written only
        by this bundle, so the match proves the legacy receipt is ours. It
        is adopted and returned with an added key "adopted_from_legacy":
        True.
      - No namespaced receipt, a legacy receipt present, and its sha does
        not match the pin (or no pin exists at all): not trusted, returns
        None. A mismatch is evidence either of a sibling bundle writing to
        the shared legacy path, or of a prior run of this bundle that was
        interrupted between writing the receipt and writing the pin - both
        read the same as "not trusted", and the caller correctly degrades
        to unverified either way.

    This legacy read happens before a sync run refreshes the version pin,
    which is what makes the sha comparison meaningful - by the time the pin
    is rewritten to the incoming bundle's sha, a legacy receipt from this
    same bundle would no longer match it.

    Never raises on malformed input - any parse failure (missing header
    keys, a body line with no tab separator, undecodable bytes) returns None
    so callers take the "unknown" path (per the bootstrap rule: absent must
    not read as clean). Reads with encoding="utf-8", errors="replace" so
    arbitrary/corrupted content cannot raise a decode error.
    """
    bundle = bundle or "plan_foundry"
    target_claude = pathlib.Path(target_claude)
    try:
        namespaced = receipt_path(target_claude, bundle)
        if namespaced.exists():
            text = namespaced.read_text(encoding="utf-8", errors="replace")
            return _parse_receipt_text(text)

        legacy = target_claude / RECEIPT_FILENAME
        if not legacy.exists():
            return None
        text = legacy.read_text(encoding="utf-8", errors="replace")
        parsed = _parse_receipt_text(text)
        if parsed is None:
            return None
        pin = read_version_file(target_claude)
        if pin is None or pin.get("sha", "") != parsed.get("sha", ""):
            return None
        parsed["adopted_from_legacy"] = True
        return parsed
    except Exception:
        return None


@dataclasses.dataclass
class ClassifyResult:
    gone_upstream: list = dataclasses.field(default_factory=list)
    consumer_owned: list = dataclasses.field(default_factory=list)
    unknown: list = dataclasses.field(default_factory=list)


def _is_stale_by_heuristic(rel: str, bundle_files) -> bool:
    """Mirrors _is_under_known_subskill's stale/project-addition split, but
    operates on the full "sub/relpath" display strings classify_stale
    receives (e.g. "skills/foo/notes.md") rather than paths already relative
    to a single bundle-managed subdir. Used only by classify_stale's
    receipt-is-None ("unknown") branch. _is_under_known_subskill itself is
    left untouched per D7 - this is a separate, additive function.
    """
    parts = pathlib.PurePosixPath(rel).parts
    if len(parts) < 3:
        # Direct child of a bundle-managed dir (e.g. "agents/x.md") - the
        # existing heuristic calls this a project addition, not stale.
        return False
    sub, top = parts[0], parts[1]
    bundle_tops = {
        pathlib.PurePosixPath(p).parts[1]
        for p in bundle_files
        if pathlib.PurePosixPath(p).parts[:1] == (sub,)
        and len(pathlib.PurePosixPath(p).parts) >= 2
    }
    return top not in bundle_tops


def classify_stale(bundle_files, target_files, receipt: Optional[dict]) -> ClassifyResult:
    """Classify target-only paths (present in target, absent from the bundle)
    into the three cases the naive stale_in_target heuristic collapses into
    one false-positive-prone "stale" bucket:

      - gone_upstream: recorded in the receipt (we installed it), no longer
        shipped by the bundle, still present on disk - the bundle genuinely
        dropped it. This is the only set quarantine() should ever be given.
      - consumer_owned: on disk, absent from both the receipt and the
        bundle - the consumer's own file living inside a bundle-owned dir.
        Never touched.
      - unknown: populated only when receipt is None (bootstrap, or a
        corrupt/absent receipt) - holds what the pre-AH7 heuristic would
        have called stale. Report only; quarantine nothing (bootstrap rule -
        absent must not read as clean).

    `bundle_files` and `target_files` are sets of "sub/relpath" display
    strings (the same format as CopyReport's lists).
    """
    result = ClassifyResult()
    only_in_target = sorted(set(target_files) - set(bundle_files))

    if receipt is None:
        for rel in only_in_target:
            if _is_stale_by_heuristic(rel, bundle_files):
                result.unknown.append(rel)
        return result

    receipt_files = set(receipt.get("files", {}).keys())
    for rel in only_in_target:
        if rel in receipt_files:
            result.gone_upstream.append(rel)
        else:
            result.consumer_owned.append(rel)
    return result


def _force_rmtree(path: pathlib.Path) -> None:
    """rmtree that clears the readonly bit before retrying - Windows-safe.

    Mirrors the identical helper in bundle_fetch.py / run_install.py /
    uninstall.py. Kept local (not imported) to avoid a cross-module
    dependency for a five-line helper; all four copies are intentionally
    identical.
    """

    def on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
        except OSError:
            return
        try:
            func(p)
        except OSError:
            return

    shutil.rmtree(path, onerror=on_error)


def quarantine(target_claude: pathlib.Path, relpaths: list) -> list:
    """Move each path in `relpaths` to a timestamped quarantine directory.

    Moves .claude/<relpath> to
    .claude/.plan-foundry-quarantine/<UTC-YYYYMMDDTHHMMSSZ>/<relpath>,
    creating parent directories and preserving structure. All paths passed
    in a single call share one timestamp.

    Calls no delete primitive - shutil.move only. sweep_quarantine is the
    one function in this module permitted to delete, and only whole aged
    quarantine directories.

    Returns the list of relpaths actually moved (paths already absent from
    disk are skipped, not treated as an error).
    """
    target_claude = pathlib.Path(target_claude)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    dest_root = target_claude / QUARANTINE_DIRNAME / stamp
    moved: list = []
    for rel in relpaths:
        src = target_claude / rel
        if not src.exists():
            continue
        dst = dest_root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved.append(rel)
    return moved


def sweep_quarantine(target_claude: pathlib.Path, max_age_days: int = 30) -> list:
    """Remove quarantine subdirectories under
    .claude/.plan-foundry-quarantine/ whose timestamp name parses older than
    `max_age_days`. This is the only function in this module permitted to
    delete, and it only ever removes a whole aged quarantine directory -
    never an individual file.

    Directory names that do not parse as the UTC-YYYYMMDDTHHMMSSZ stamp
    written by quarantine() are skipped, never removed - an unparseable name
    is treated as "not provably aged", not as "safe to delete".

    Returns the list of swept directory names (for the sync report).
    """
    target_claude = pathlib.Path(target_claude)
    root = target_claude / QUARANTINE_DIRNAME
    if not root.exists():
        return []
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        days=max_age_days
    )
    swept: list = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            stamp = datetime.datetime.strptime(
                entry.name, "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            continue
        if stamp < cutoff:
            _force_rmtree(entry)
            swept.append(entry.name)
    return swept
