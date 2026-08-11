from __future__ import annotations

from pathlib import Path

import pytest

from chatmesh.cli import main


def _write_config(tmp_path: Path, name: str = "alice") -> Path:
    p = tmp_path / f"{name}.toml"
    p.write_text(
        f"""
broker_url = "nats://127.0.0.1:4222"
agent_name = "{name}"
sidecar_path = "{name}.jsonl"
log_path = "{name}.log"
""",
        encoding="utf-8",
    )
    return p


def test_no_subcommand_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code != 0


def test_publish_requires_body(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["publish", "--config", str(cfg), "--to", "bob", "--topic", "greet"])
    assert exc.value.code != 0


def test_watch_needs_command(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    rc = main(["watch", "--config", str(cfg)])
    assert rc == 2
