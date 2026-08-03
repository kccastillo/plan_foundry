"""
preflight.py - sync pre-flight: the pre-sync break signal read from the
clone itself, and the in-flight PLAN scan. PLAN-AH8, guarantee 2.

**This module must be self-contained. It must not import bundle_copy, and
it does not import any other _shared module either.** bundle_copy is
already bound in sys.modules to the consumer's *installed* copy by the time
sync's pre-flight runs (sync.py's _import_local_helpers imports it before
the clone even happens), so "import bundle_copy" here would silently
resolve to code that predates this wave rather than the freshly-cloned
bundle's - past the ImportError guard the caller wraps this import in,
surfacing as an AttributeError that crashes the sync on exactly the
consumer this module protects. Widening that guard to also catch
AttributeError is NOT the fix - it masks a dead mechanism rather than
making this one live. See bundle_copy.py's module docstring for the
mirrored statement of this same invariant.

Consequently the pin read and the bundle-contract read below are inlined
copies of bundle_copy.read_version_file and bundle_copy.read_bundle_contract
respectively, not imports. This duplication is deliberate and load-bearing -
a later tidy-up that collapses it into a shared import will silently kill
the pre-flight. The tag semver comparison is inlined too, for the same
reason: any import of a sibling _shared module carries the same
cache-poisoning risk if that module happens to already be in sys.modules
from an earlier, non-clone import in the same process (as pytest's
in-process test runs can produce).

Deriving the clone's own tag is also this module's job, and nothing records
it beforehand: bundle_fetch.clone_bundle returns a bare path, and
bundle_copy.write_version_file's own `git describe` runs only after the
copy. Inline `git describe --tags --exact-match` against bundle_path here,
mirroring the subprocess shape bundle_copy.py uses - not by calling
bundle_copy._run_git, which would work today (it predates the crossing) but
would reintroduce the forbidden import.

An empty clone tag is the common case, not an edge case: bundle_fetch
clones with --depth=1, so describe --exact-match resolves only when the
cloned ref is exactly a tagged commit. Most verdicts therefore rest on
schema_version alone, which is by design.

PLAN-AH9, guarantee 4: read_deprecations(bundle_root) and shim_body(entry)
below implement the deprecation ledger and shim-then-delete mechanism.
Full policy - the two address spaces (file-path vs. symbol-addressed
entries), the shim lifecycle, and the worked example - is
_shared/deprecation-policy.md.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
from typing import Optional

PIN_FILENAME = ".plan-foundry-bundle-version"
CONTRACT_FILENAME = "bundle-contract.json"

_IN_FLIGHT_PHASES = {
    "drafting",
    "drafted",
    "checked",
    "executing",
    "outcome-verifying",
}

_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def _parse_tag(tag: str) -> Optional[tuple[int, int, int]]:
    """Inlined tag parse - see module docstring for why this is not an
    import of bundle_semver.parse."""
    if not tag:
        return None
    match = _TAG_RE.match(tag)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _run_git(args: list, cwd: pathlib.Path) -> Optional[str]:
    """Inlined subprocess shape - mirrors bundle_copy._run_git without
    importing it."""
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


def _read_pin(target_claude: pathlib.Path) -> Optional[dict]:
    """Inlined copy of bundle_copy.read_version_file. Returns the parsed
    pin dict, or None when the pin file is absent. Never raises.
    """
    target_claude = pathlib.Path(target_claude)
    path = target_claude / PIN_FILENAME
    try:
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    out: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip()
    return out


def _read_contract(bundle_path: pathlib.Path) -> dict:
    """Inlined copy of bundle_copy.read_bundle_contract, pointed at the
    clone's own _shared/bundle-contract.json. Returns
    {"schema_version": "", "deprecations": []} when the file is absent,
    empty, or malformed JSON. Never raises.
    """
    bundle_path = pathlib.Path(bundle_path)
    path = bundle_path / ".claude" / "skills" / "_shared" / CONTRACT_FILENAME
    try:
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


def _derive_clone_tag(bundle_path: pathlib.Path) -> str:
    """git describe --tags --exact-match against the clone. "" when the
    cloned commit is not exactly a tagged commit - the common case under
    the --depth=1 clone, not an edge case.
    """
    return _run_git(["describe", "--tags", "--exact-match"], bundle_path) or ""


def _tag_step(pin_tag: str, clone_tag: str) -> Optional[str]:
    """Return "same", "minor" (covers minor and patch differences), "major",
    or None (either side underivable)."""
    if not pin_tag or not clone_tag:
        return None
    pin_parsed = _parse_tag(pin_tag)
    clone_parsed = _parse_tag(clone_tag)
    if pin_parsed is None or clone_parsed is None:
        return None
    if pin_parsed[0] != clone_parsed[0]:
        return "major"
    if pin_parsed != clone_parsed:
        return "minor"
    return "same"


def _parse_schema_version(value) -> Optional[int]:
    """An empty schema_version is underivable, not a comparable value.
    Empty, absent, and unparseable are treated identically - all return
    None here, never 0 or any other sentinel that could compare as
    "different" from a real value.
    """
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _schema_step(pin_schema, contract_schema) -> Optional[str]:
    """Return "same", "major" (any concrete schema_version difference is a
    major step - the field exists specifically to signal a breaking
    substrate change), or None (either side underivable)."""
    pin_val = _parse_schema_version(pin_schema)
    contract_val = _parse_schema_version(contract_schema)
    if pin_val is None or contract_val is None:
        return None
    return "same" if pin_val == contract_val else "major"


def _combine(tag_step: Optional[str], schema_step: Optional[str]) -> str:
    """Combination rule (Step 7): either signal indicating a major step
    yields major_step; unavailable only when both are underivable.
    Otherwise, when one signal is underivable, the verdict falls to the
    other signal alone.
    """
    if tag_step is None and schema_step is None:
        return "unavailable"
    if tag_step == "major" or schema_step == "major":
        return "major_step"
    if tag_step == "minor":
        return "minor_step"
    return "same"


def compare_against_clone(target_claude: pathlib.Path, bundle_path: pathlib.Path) -> str:
    """Compare the target's pin against the freshly-cloned bundle at
    bundle_path (per D13: the incoming version is on disk at bundle_path
    and must be read from there, not from a remote-latest query - sync()
    takes --ref and clones exactly that ref, so remote-latest would give a
    false halt on --ref v1.13.0 while remote is v2.0.0, and a silent pass
    on --ref main past an untagged major).

    Returns one of: "same", "minor_step", "major_step",
    "pin_predates_contract", "unavailable".
    """
    target_claude = pathlib.Path(target_claude)
    bundle_path = pathlib.Path(bundle_path)

    pin = _read_pin(target_claude)
    if pin is None:
        # No pin at all - sync() already refuses to run before this point
        # (its own pin-absent check precedes the clone), so this is a
        # defensive fallback, not the expected path. Underivable, not a
        # pre-contract pin.
        return "unavailable"
    if "schema_version" not in pin:
        # A pin written before this wave's Step 3 shipped the
        # schema_version= line. The crossing sync is precisely this case -
        # warn and continue is the caller's job, not this function's.
        return "pin_predates_contract"

    clone_tag = _derive_clone_tag(bundle_path)
    contract = _read_contract(bundle_path)

    tag_step = _tag_step(pin.get("tag", ""), clone_tag)
    schema_step = _schema_step(pin.get("schema_version", ""), contract.get("schema_version", ""))

    return _combine(tag_step, schema_step)


_VALID_DEPRECATION_KINDS = {"skill", "helper", "reference", "hook"}
_DEPRECATION_ENTRY_FIELDS = ("path", "since", "removed_in", "replaced_by", "note", "kind")


def read_deprecations(bundle_root: pathlib.Path) -> list:
    """Return the ledger's deprecation entries from bundle-contract.json.

    Builds on _read_contract (above), which already loads the contract and
    normalises a missing "deprecations" key to []. Does not re-derive the
    file read. Never raises - returns [] when the contract is absent or the
    array is missing (via _read_contract), and skips malformed entries
    individually rather than rejecting the whole ledger, so one bad entry
    does not blind the mechanism to the rest.

    An entry is well-formed when it is a dict carrying string values for
    all of {path, since, removed_in, replaced_by, note, kind} and `kind` is
    one of skill | helper | reference | hook.

    `kind` selects the entry's address space and is load-bearing, not
    descriptive (PLAN-AH9 Context, "A deprecation has two address
    spaces"): for kind in skill | reference | hook, `path` is a
    bundle-relative file path - the entry is shim-generated (shim_body,
    below) and quarantine-matched (plan-foundry-sync). For kind: helper,
    `path` is `file.py::symbol` - the entry is recorded for provenance and
    read by the deprecation policy only; it is never shim-generated and
    never offered to the quarantine matcher.
    """
    bundle_root = pathlib.Path(bundle_root)
    contract = _read_contract(bundle_root)
    raw = contract.get("deprecations", [])
    if not isinstance(raw, list):
        return []
    out = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        if any(key not in entry for key in _DEPRECATION_ENTRY_FIELDS):
            continue
        if not all(isinstance(entry[key], str) for key in _DEPRECATION_ENTRY_FIELDS):
            continue
        if entry["kind"] not in _VALID_DEPRECATION_KINDS:
            continue
        out.append(entry)
    return out


def shim_body(entry: dict) -> str:
    """Return the standin content a deprecated surface carries during its
    grace release: a one-line statement that the surface is deprecated,
    the replaced_by target, the removed_in version, and the note.

    Only entries with kind in skill | reference | hook may ever be passed
    here - a kind: helper entry's path is a file.py::symbol string with no
    file-level slot for a shim to occupy. The caller (scripts/generate-
    deprecation-shim.py) is responsible for rejecting a kind: helper entry
    before it reaches this function; this function also refuses one rather
    than silently producing nonsense output for a path that cannot exist.

    For kind: "skill" the body is valid SKILL.md frontmatter plus the
    deprecation text, so an agent invoking the deprecated skill gets a
    readable diagnostic instead of a missing-file error.
    """
    kind = entry.get("kind")
    if kind not in ("skill", "reference", "hook"):
        raise ValueError(
            "shim_body: kind %r has no file-path address for a shim to "
            "occupy (only skill | reference | hook are shim-generated)" % (kind,)
        )
    replaced_by = entry.get("replaced_by", "")
    removed_in = entry.get("removed_in", "")
    note = entry.get("note", "")
    diagnostic = (
        "This surface is deprecated. Replaced by: %s. Removed in: %s. %s\n"
        % (replaced_by, removed_in, note)
    )
    if kind == "skill":
        # The skill's name is its DIRECTORY, not the stem of the file. A skill
        # entry's path is `.claude/skills/<name>/SKILL.md`, so taking the stem
        # yields the literal "SKILL" for every skill, and a bundle shimming
        # more than one would ship several skills all claiming that name. Found
        # on the first real file-level use of this path, 2026-08-03; until then
        # only a kind: helper entry existed and this branch had never run
        # against a live ledger.
        parts = pathlib.PurePosixPath(entry.get("path", "")).parts
        name = parts[-2] if len(parts) >= 2 else pathlib.PurePosixPath(
            entry.get("path", "")
        ).stem
        return (
            "---\n"
            "name: %s\n"
            "description: 'Deprecated - replaced by %s. Removed in %s.'\n"
            "---\n\n%s" % (name, replaced_by, removed_in, diagnostic)
        )
    return diagnostic


BUNDLE_MANAGED_DIRS_FOR_DETECT = (
    ".claude/skills",
    ".claude/agents",
    ".claude/commands",
    ".claude/hooks",
)


def detect_foreign_bundle(target_root, bundle_root=None):
    """Return a diagnostic when the target owns bundle content of its own.

    The existing bundle-source guard matches this bundle's own name, so a
    repo called anything else passes it - which is how paper_trail_dev, the
    source of a sibling bundle forked from this one, reached the copy step
    that would have overwritten its tracked product (PLAN-AJ6 D3).

    Two signals, first hit wins:

    1. The target carries its own `_shared/bundle-contract.json` whose bytes
       differ from the incoming bundle's. Two contracts means two bundles.
    2. Git tracks files under a bundle-managed directory. A plain consumer
       gitignores those; a repo shipping `.claude/` content tracks them.

    Returns a one-line diagnostic string, or None when the target looks like
    an ordinary consumer. Fail-open on a missing git or a non-repo target:
    signal 2 cannot be evaluated, so it does not fire.
    """
    target_root = pathlib.Path(target_root)

    target_contract = (
        target_root / ".claude" / "skills" / "_shared" / "bundle-contract.json"
    )
    if bundle_root is not None and target_contract.is_file():
        incoming = (
            pathlib.Path(bundle_root)
            / ".claude"
            / "skills"
            / "_shared"
            / "bundle-contract.json"
        )
        if incoming.is_file():
            try:
                if target_contract.read_bytes() != incoming.read_bytes():
                    return (
                        "foreign-bundle-detected: the target carries its own "
                        ".claude/skills/_shared/bundle-contract.json and it differs "
                        "from this bundle's. Two contracts means two bundles, and "
                        "installing would overwrite the other one's install "
                        "machinery. Install a subset by hand, or wait for the "
                        "supported selective-install mode."
                    )
            except OSError:
                pass

    for rel in BUNDLE_MANAGED_DIRS_FOR_DETECT:
        if not (target_root / rel).exists():
            continue
        try:
            proc = subprocess.run(
                ["git", "ls-files", "--", rel],
                cwd=str(target_root),
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if proc.returncode == 0 and proc.stdout.strip():
            first = proc.stdout.strip().splitlines()[0]
            return (
                "foreign-bundle-detected: git tracks files under %s (for example "
                "%s). A consumer gitignores the bundle-managed directories; a repo "
                "that tracks them owns that content as source, and installing "
                "would overwrite it and then untrack the rest. Install a subset by "
                "hand, or wait for the supported selective-install mode."
                % (rel, first)
            )

    return None


def scan_in_flight_plans(target_root: pathlib.Path) -> list:
    """Return relative (posix) paths of Workbench/*.md whose frontmatter
    pipeline_phase is in {drafting, drafted, checked, executing,
    outcome-verifying}. Parses defensively - malformed or absent
    frontmatter yields no entry, never an exception.
    """
    target_root = pathlib.Path(target_root)
    workbench = target_root / "Workbench"
    out = []
    if not workbench.exists():
        return out
    for path in sorted(workbench.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        phase = _read_frontmatter_scalar(text, "pipeline_phase")
        if phase in _IN_FLIGHT_PHASES:
            out.append(path.relative_to(target_root).as_posix())
    return out


def _read_frontmatter_scalar(text: str, field: str) -> Optional[str]:
    """Extract a simple scalar YAML frontmatter field value. Returns the
    stripped value (quotes removed), or None if not found or the
    frontmatter block is malformed/absent. Never raises.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith(field + ":"):
            value = line[len(field) + 1 :].strip()
            if len(value) >= 2 and value[0] in ('"', "'") and value[-1] == value[0]:
                value = value[1:-1]
            return value if value else None
    return None
