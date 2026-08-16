#!/usr/bin/env python3
"""
check-bootstrap-read-parity.py - CI check for PLAN-AL8 D2/D3.

Three functions each perform an inline, _shared/-import-free read of
bundle-contract.json, for the reason PLAN-AL8 D2 records in
bundle_copy.py's read_bundle_contract docstring, preflight.py's module
docstring, and sync.py's installed_bundle_identity docstring: each
exists to decide whether the freshly-cloned or installed _shared/ can be
trusted, so none of the three may import from _shared/ to do it.

  - _shared/bundle_copy.py: read_bundle_contract(bundle_root)
  - _shared/preflight.py: _read_contract(bundle_path) (inlined copy)
  - plan-foundry-sync/lib/sync.py: installed_bundle_identity(shared)

Nothing else keeps them in step once someone edits one and forgets the
other two. This check runs the same fixture battery through all three
and fails on any divergence, mechanically, rather than depending on a
comment being noticed.

PLAN-AL8 D3 amendment: the fixture battery above is Python-to-Python and
would not have caught the drift that produced this PLAN - workflows/
sync.md restating the body of a sync.py function rather than calling
that function. This check also reads sync.md's two delegated call
sites (Step 2b's call to compute_preflight_verdict, Step 3a's call to
build_file_kind_ledger), confirms each names the real function with
the real argument count, and fails if either site carries the tell of
a reproduced body rather than a call. See PLAN-AL8's Context for why
this half guards against a restatement returning rather than
repairing one that is present today.

Exit 0 on success. Exit 1 and print each divergence to stderr on
failure.
"""
from __future__ import annotations

import ast
import importlib.util
import inspect
import json
import pathlib
import re
import sys
import tempfile

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SHARED_DIR = REPO_ROOT / ".claude" / "skills" / "_shared"
SYNC_LIB_DIR = REPO_ROOT / ".claude" / "skills" / "plan-foundry-sync" / "lib"
SYNC_MD_PATH = (
    REPO_ROOT / ".claude" / "skills" / "plan-foundry-sync" / "workflows" / "sync.md"
)

FIXTURES = {
    "valid_full": json.dumps(
        {"bundle": "plan_foundry", "schema_version": 3, "deprecations": [{"path": "x"}]}
    ),
    "valid_no_bundle": json.dumps({"schema_version": 1, "deprecations": []}),
    "empty_bundle": json.dumps({"bundle": "", "schema_version": 1}),
    "non_string_bundle": json.dumps({"bundle": 7}),
    "malformed_json": "{not json",
    "not_a_dict": json.dumps(["a", "list"]),
    "absent": None,
}

# PLAN-AL8 D3 amendment: one entry per delegated call site D1 introduced in
# sync.md. forbidden_import names a module a genuine call site never needs
# to import directly - its presence in the same fenced block is the tell
# of a reproduced body. forbid_comprehension flags a block that still
# builds the ledger filter inline, rather than through the delegated call.
MARKDOWN_CALL_SITES = (
    {
        "label": "sync.md Step 2b -> compute_preflight_verdict",
        "func_name": "compute_preflight_verdict",
        "forbidden_import": "preflight",
        "forbid_comprehension": False,
    },
    {
        "label": "sync.md Step 3a -> build_file_kind_ledger",
        "func_name": "build_file_kind_ledger",
        "forbidden_import": None,
        "forbid_comprehension": True,
    },
)


def _load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    # bundle_copy.py's dataclass fields resolve string annotations (from
    # __future__ import annotations) against sys.modules[cls.__module__],
    # so exec_module raises AttributeError on Python 3.12 unless the
    # module is registered here first - the standard importlib recipe,
    # and a real crash, not a hypothetical one: reproduced by loading the
    # real file this way before this line was added.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _make_bundle_root(case_dir: pathlib.Path, content):
    bundle_root = case_dir / "bundle"
    shared = bundle_root / ".claude" / "skills" / "_shared"
    shared.mkdir(parents=True)
    if content is not None:
        (shared / "bundle-contract.json").write_text(content, encoding="utf-8")
    return bundle_root, shared


def _check_fixture_parity(bundle_copy, preflight, sync, failures: list) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        for name, content in FIXTURES.items():
            case_dir = tmp_path / name
            case_dir.mkdir()
            bundle_root, shared = _make_bundle_root(case_dir, content)

            contract = bundle_copy.read_bundle_contract(bundle_root)
            inlined = preflight._read_contract(bundle_root)
            if contract != inlined:
                failures.append(
                    f"{name}: bundle_copy.read_bundle_contract={contract!r} != "
                    f"preflight._read_contract={inlined!r}"
                )

            identity = sync.installed_bundle_identity(shared)
            expected_identity = contract.get("bundle")
            if not (isinstance(expected_identity, str) and expected_identity):
                expected_identity = None
            if identity != expected_identity:
                failures.append(
                    f"{name}: sync.installed_bundle_identity={identity!r} != "
                    f"derived-from-read_bundle_contract={expected_identity!r}"
                )


def _fenced_python_blocks(markdown_text: str) -> list:
    return re.findall(r"```python\n(.*?)```", markdown_text, flags=re.DOTALL)


def _check_markdown_delegates(sync, failures: list) -> None:
    """PLAN-AL8 D3 amendment. Fails if sync.md names a delegated function
    without calling it, calls it with the wrong argument count, or
    carries the tell of a reproduced body sitting beside the call.
    """
    if not SYNC_MD_PATH.exists():
        failures.append(f"sync.md: expected file missing at {SYNC_MD_PATH}")
        return
    markdown_text = SYNC_MD_PATH.read_text(encoding="utf-8")
    blocks = _fenced_python_blocks(markdown_text)

    for site in MARKDOWN_CALL_SITES:
        func_name = site["func_name"]
        matching = [b for b in blocks if func_name in b]
        if len(matching) != 1:
            failures.append(
                f"{site['label']}: expected exactly one fenced python block in "
                f"sync.md naming {func_name}, found {len(matching)}"
            )
            continue
        block = matching[0]
        try:
            tree = ast.parse(block)
        except SyntaxError as exc:
            failures.append(
                f"{site['label']}: sync.md's fenced block does not parse - {exc}"
            )
            continue

        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == func_name
        ]
        if not calls:
            failures.append(
                f"{site['label']}: sync.md's block names {func_name} but never "
                "calls it - reads like a reproduced body, not a delegated call"
            )
            continue

        real_params = len(inspect.signature(getattr(sync, func_name)).parameters)
        for call in calls:
            shown_args = len(call.args) + len(call.keywords)
            if shown_args != real_params:
                failures.append(
                    f"{site['label']}: sync.md's call passes {shown_args} "
                    f"argument(s), sync.py's {func_name} takes {real_params}"
                )

        forbidden_import = site["forbidden_import"]
        if forbidden_import is not None and any(
            isinstance(node, ast.Import)
            and any(alias.name == forbidden_import for alias in node.names)
            for node in ast.walk(tree)
        ):
            failures.append(
                f"{site['label']}: sync.md's block still imports "
                f"{forbidden_import!r} directly - that belongs inside "
                f"{func_name}, not beside the call"
            )

        if site["forbid_comprehension"] and any(
            isinstance(node, (ast.DictComp, ast.ListComp, ast.SetComp, ast.GeneratorExp))
            for node in ast.walk(tree)
        ):
            failures.append(
                f"{site['label']}: sync.md's block still builds the result "
                f"inline with a comprehension - that belongs inside "
                f"{func_name}, not beside the call"
            )


def main() -> int:
    bundle_copy = _load_module("bundle_copy_ci", SHARED_DIR / "bundle_copy.py")
    preflight = _load_module("preflight_ci", SHARED_DIR / "preflight.py")
    sync = _load_module("sync_ci", SYNC_LIB_DIR / "sync.py")

    failures: list = []
    _check_fixture_parity(bundle_copy, preflight, sync, failures)
    _check_markdown_delegates(sync, failures)

    if failures:
        for line in failures:
            print(f"ERROR: {line}", file=sys.stderr)
        print(
            "ERROR: a bootstrap-read instance or a sync.md delegated call has "
            "drifted - see bundle_copy.read_bundle_contract, "
            "preflight._read_contract, sync.installed_bundle_identity, and "
            "workflows/sync.md's Step 2b and Step 3a call sites",
            file=sys.stderr,
        )
        return 1
    print(
        "bootstrap read parity: PASS (bundle_copy, preflight, sync agree on "
        "every fixture; sync.md delegates rather than reproduces)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
