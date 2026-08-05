"""
bundle_copy.py - shared helper for init-plan-foundry and plan-foundry-sync.

Exposes:
  - BUNDLE_MANAGED_DIRS: tuple of the four top-level subdirs under .claude
    that the bundle owns (skills, agents, commands, hooks).
  - copy_bundle_managed(bundle_claude, target_claude) -> CopyReport
  - write_version_file(bundle_root, target_claude) -> dict
  - read_version_file(target_claude) -> Optional[dict]

Design rationale: PLAN-AC5 (2026-05-19). The bundle propagates to target
projects by copy, not symlink. This module is the single source of truth
for which paths under .claude/ are bundle-managed and how the version pin
is recorded.

Never deletes from target. Bundle files that no longer exist upstream are
listed in CopyReport.stale_in_target but left in place - explicit cleanup
is the user's call.

Required sync sequence (PLAN-AH7 Step 1 - load-bearing, do not reorder):

    1. read the existing receipt (before the clone, alongside the existing
       pin read at sync.py:57)
    2. clone
    3. copy
    4. classify
    5. quarantine
    6. sweep
    7. write the new receipt

If the receipt is written any earlier than step 7 - in particular,
immediately after the copy, which is where write_version_file sits and
where the natural reading would put it - then classify_stale's
gone_upstream is always empty, quarantine never fires on any consumer,
and receipt_absent never reports true. The mechanism would appear to work
(report shape unchanged, tests of shape still pass) while silently doing
nothing. Every caller of write_receipt must position the call at the end
of this sequence.

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

    def summary(self) -> str:
        return (
            f"copied={len(self.files_copied)} "
            f"unchanged={len(self.files_unchanged)} "
            f"project_additions={len(self.project_additions)} "
            f"stale_in_target={len(self.stale_in_target)} "
            f"shim_skipped={len(self.shim_skipped)}"
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
    """
    bundle_claude = pathlib.Path(bundle_claude)
    target_claude = pathlib.Path(target_claude)
    shimmed = _shimmed_relpaths(deprecations)
    report = CopyReport()

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
    the freshly-cloned bundle's. The duplication is intentional and
    load-bearing - do not "simplify" it into a shared import later.
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


def write_version_file(
    bundle_root: pathlib.Path, target_claude: pathlib.Path
) -> dict:
    """Write target/.claude/.plan-foundry-bundle-version with sha/tag/synced/schema_version.

    Returns the dict that was written. Tag is "" when no exact-match tag exists.
    schema_version is sourced from read_bundle_contract(bundle_root) and is ""
    when the incoming bundle carries no contract (predates PLAN-AH8) or the
    contract is malformed - the key is always written, never omitted, so the
    pin's shape stays stable across bundle versions.
    """
    bundle_root = pathlib.Path(bundle_root)
    target_claude = pathlib.Path(target_claude)
    sha = _run_git(["rev-parse", "HEAD"], bundle_root) or ""
    tag = _run_git(["describe", "--tags", "--exact-match"], bundle_root) or ""
    synced = datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    schema_version = read_bundle_contract(bundle_root).get("schema_version", "")

    data = {"sha": sha, "tag": tag, "synced": synced, "schema_version": schema_version}
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
# PLAN-AH7: install receipt, three-set classification, quarantine, sweep.
#
# See the module docstring above for the required sequence these pieces must
# be called in. All of this is additive - copy_bundle_managed, write_version_file,
# read_version_file, _is_under_known_subskill and CopyReport.stale_in_target
# are untouched (D7).
# ---------------------------------------------------------------------------

RECEIPT_FILENAME = ".plan-foundry-bundle-files"
QUARANTINE_DIRNAME = ".plan-foundry-quarantine"


def write_receipt(
    target_claude: pathlib.Path, relpaths: list, sha: str
) -> dict:
    """Write target/.claude/.plan-foundry-bundle-files - the install receipt.

    Header line records `sha=` (the bundle sha this install/sync pinned to)
    and `written=` (UTC ISO8601), followed by one `<relpath>\\t<sha256>` line
    per installed file, sorted. `relpaths` are relative to `target_claude`
    (the same display strings CopyReport.files_copied/files_unchanged use,
    e.g. "skills/foo/SKILL.md").

    Atomic via a `.tmp` sibling and os.replace, mirroring write_version_file.
    Read and write with encoding="utf-8".

    MUST be called at the end of the sequence recorded in the module
    docstring - after classify/quarantine/sweep, never immediately after the
    copy (that is where write_version_file sits, and where the natural
    reading would put this call - do not follow that instinct here).
    """
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

    lines = [f"sha={sha}", f"written={written}"]
    for rel in sorted(entries):
        lines.append(f"{rel}\t{entries[rel]}")

    target_claude.mkdir(parents=True, exist_ok=True)
    target = target_claude / RECEIPT_FILENAME
    tmp = target.with_suffix(target.suffix + ".tmp")
    body = "\n".join(lines) + "\n"
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, target)
    return {"sha": sha, "written": written, "files": entries}


def read_receipt(target_claude: pathlib.Path) -> Optional[dict]:
    """Read target/.claude/.plan-foundry-bundle-files - the install receipt.

    Returns {"sha": ..., "written": ..., "files": {relpath: sha256, ...}}, or
    None when the file is absent, empty, or its header is malformed.

    Never raises on malformed input - any parse failure (missing header keys,
    a body line with no tab separator, undecodable bytes) returns None so
    callers take the "unknown" path (per the bootstrap rule: absent must not
    read as clean). Reads with encoding="utf-8", errors="replace" so
    arbitrary/corrupted content cannot raise a decode error.
    """
    target_claude = pathlib.Path(target_claude)
    path = target_claude / RECEIPT_FILENAME
    try:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) < 2:
            return None
        header: dict[str, str] = {}
        for line in lines[:2]:
            if "=" not in line:
                return None
            key, _, value = line.partition("=")
            key = key.strip()
            if key not in ("sha", "written"):
                return None
            header[key] = value.strip()
        files: dict[str, str] = {}
        for line in lines[2:]:
            if not line.strip():
                continue
            if "\t" not in line:
                return None
            rel, _, digest = line.partition("\t")
            files[rel.strip()] = digest.strip()
        return {
            "sha": header.get("sha", ""),
            "written": header.get("written", ""),
            "files": files,
        }
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
