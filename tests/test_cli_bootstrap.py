from __future__ import annotations

from pathlib import Path

import pytest

from chatmesh.cli import _config_template, _find_repo_root, main


def test_config_template_has_required_keys():
    body = _config_template("alice")
    assert 'broker_url = "nats://127.0.0.1:4222"' in body
    assert 'agent_name = "alice"' in body
    assert 'sidecar_path = "alice.jsonl"' in body
    assert 'log_path = "alice.log"' in body


def test_find_repo_root_returns_none_outside_repo(tmp_path: Path):
    assert _find_repo_root(tmp_path) is None


def test_find_repo_root_walks_up(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")
    (tmp_path / "broker").mkdir()
    (tmp_path / "broker" / "docker-compose.yml").write_text("", encoding="utf-8")
    nested = tmp_path / "sub" / "deep"
    nested.mkdir(parents=True)
    assert _find_repo_root(nested) == tmp_path


def test_bootstrap_outside_repo_returns_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.chdir(tmp_path)
    rc = main(["bootstrap"])
    assert rc == 1


def test_config_template_lists_the_other_agents():
    assert 'peers = ["bob", "user"]' in _config_template("alice")
    assert 'peers = ["alice", "bob"]' in _config_template("user")
