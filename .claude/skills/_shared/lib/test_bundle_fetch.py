"""Tests for bundle_fetch — mock subprocess.run so CI does not hit the network."""

from __future__ import annotations

import pathlib
import sys
import types

import pytest

_SHARED = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SHARED))

import bundle_fetch  # noqa: E402


def _fake_run_factory(rc=0, stderr="", stdout="", create_tree=True):
    """Build a subprocess.run replacement that simulates git clone."""

    def fake_run(args, **kwargs):
        if create_tree and rc == 0:
            # args: ["git","clone","--depth=1","--branch",ref,URL,tmp]
            tmp = pathlib.Path(args[-1])
            (tmp / ".claude" / "skills").mkdir(parents=True, exist_ok=True)
            (tmp / ".claude" / "agents").mkdir(parents=True, exist_ok=True)
        result = types.SimpleNamespace(
            returncode=rc, stdout=stdout, stderr=stderr, args=args
        )
        return result

    return fake_run


def test_clone_bundle_success(tmp_path, monkeypatch):
    monkeypatch.setattr(bundle_fetch.subprocess, "run", _fake_run_factory())
    out = bundle_fetch.clone_bundle(tmp_path, ref="main")
    assert out == tmp_path / ".plan-foundry-tmp"
    assert (out / ".claude").exists()


def test_clone_bundle_cleans_stale_tmp(tmp_path, monkeypatch):
    stale = tmp_path / ".plan-foundry-tmp"
    stale.mkdir()
    (stale / "stale-file.txt").write_text("old", encoding="utf-8")
    monkeypatch.setattr(bundle_fetch.subprocess, "run", _fake_run_factory())
    out = bundle_fetch.clone_bundle(tmp_path)
    assert out.exists()
    assert not (out / "stale-file.txt").exists()


def test_clone_bundle_propagates_git_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bundle_fetch.subprocess,
        "run",
        _fake_run_factory(rc=128, stderr="fatal: could not read from remote"),
    )
    with pytest.raises(bundle_fetch.BundleFetchError) as exc:
        bundle_fetch.clone_bundle(tmp_path)
    assert "git clone failed" in str(exc.value)


def test_clone_bundle_bad_ref(tmp_path, monkeypatch):
    # Simulate: git clone returns 0 but tmp/.claude missing (wrong branch).
    def fake_run(args, **kwargs):
        tmp = pathlib.Path(args[-1])
        tmp.mkdir(parents=True, exist_ok=True)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="", args=args)

    monkeypatch.setattr(bundle_fetch.subprocess, "run", fake_run)
    with pytest.raises(bundle_fetch.BundleFetchError) as exc:
        bundle_fetch.clone_bundle(tmp_path, ref="nonexistent")
    assert ".claude missing" in str(exc.value)


def test_clone_bundle_git_not_found(tmp_path, monkeypatch):
    def fake_run(args, **kwargs):
        raise FileNotFoundError("git: command not found")

    monkeypatch.setattr(bundle_fetch.subprocess, "run", fake_run)
    with pytest.raises(bundle_fetch.BundleFetchError) as exc:
        bundle_fetch.clone_bundle(tmp_path)
    assert "git executable not found" in str(exc.value)


def test_clone_bundle_uses_ref_arg(tmp_path, monkeypatch):
    captured = {}

    def fake_run(args, **kwargs):
        captured["args"] = list(args)
        (pathlib.Path(args[-1]) / ".claude").mkdir(parents=True, exist_ok=True)
        return types.SimpleNamespace(returncode=0, stdout="", stderr="", args=args)

    monkeypatch.setattr(bundle_fetch.subprocess, "run", fake_run)
    bundle_fetch.clone_bundle(tmp_path, ref="v0.5.0")
    assert "--branch" in captured["args"]
    branch_idx = captured["args"].index("--branch")
    assert captured["args"][branch_idx + 1] == "v0.5.0"


def test_cleanup_tmp_removes(tmp_path):
    tmp = tmp_path / ".plan-foundry-tmp"
    tmp.mkdir()
    (tmp / "x").write_text("hi", encoding="utf-8")
    assert bundle_fetch.cleanup_tmp(tmp_path) is True
    assert not tmp.exists()


def test_cleanup_tmp_absent_returns_false(tmp_path):
    assert bundle_fetch.cleanup_tmp(tmp_path) is False
