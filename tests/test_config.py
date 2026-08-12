from __future__ import annotations

from pathlib import Path

import pytest

from chatmesh.config import Config, ConfigError


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_minimum(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        """,
    )
    cfg = Config.load(cfg_path)
    assert cfg.broker_url == "nats://127.0.0.1:4222"
    assert cfg.agent_name == "alice"
    assert cfg.sidecar_path == (tmp_path / "inbox.jsonl").resolve()
    assert cfg.log_path == (tmp_path / "agent.log").resolve()
    assert cfg.ca_pin_path is None
    assert cfg.nkey_seed_path is None


def test_missing_key(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        'broker_url = "nats://127.0.0.1:4222"',
    )
    with pytest.raises(ConfigError):
        Config.load(cfg_path)


def test_bad_toml(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "cfg.toml", "not = valid = toml")
    with pytest.raises(ConfigError):
        Config.load(cfg_path)


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        Config.load(tmp_path / "does-not-exist.toml")


def test_peers_default_to_empty(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        """,
    )
    assert Config.load(cfg_path).peers == []


def test_peers_are_read_in_order(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        peers = ["bob", "user"]
        """,
    )
    assert Config.load(cfg_path).peers == ["bob", "user"]


def test_peers_must_be_strings(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        peers = ["bob", 3]
        """,
    )
    with pytest.raises(ConfigError):
        Config.load(cfg_path)


def test_durable_defaults_to_off(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        """,
    )
    assert Config.load(cfg_path).durable is False


def test_durable_reads_a_boolean(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        durable = true
        """,
    )
    assert Config.load(cfg_path).durable is True


def test_durable_rejects_a_string(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "cfg.toml",
        """
        broker_url = "nats://127.0.0.1:4222"
        agent_name = "alice"
        sidecar_path = "inbox.jsonl"
        log_path = "agent.log"
        durable = "yes"
        """,
    )
    with pytest.raises(ConfigError):
        Config.load(cfg_path)
