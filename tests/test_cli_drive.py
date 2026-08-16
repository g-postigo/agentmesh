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


def test_drive_requires_driver_flag(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["drive", "--config", str(cfg)])
    assert exc.value.code != 0


def test_drive_rejects_unknown_driver(tmp_path: Path) -> None:
    cfg = _write_config(tmp_path)
    with pytest.raises(SystemExit) as exc:
        main(["drive", "--config", str(cfg), "--driver", "openai"])
    assert exc.value.code != 0


def test_drive_accepts_echo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The no-LLM driver has to be reachable from the CLI, since it is the
    only way to try chatmesh without a Claude or Kimi login."""
    from chatmesh.drivers import DriverRunner, EchoDriver

    built = {}

    async def _fake_run(self) -> None:
        built["driver"] = self._driver

    monkeypatch.setattr(DriverRunner, "run", _fake_run)
    cfg = _write_config(tmp_path)
    assert main(["drive", "--config", str(cfg), "--driver", "echo"]) == 0
    assert isinstance(built["driver"], EchoDriver)
    assert built["driver"].agent_name == "alice"
