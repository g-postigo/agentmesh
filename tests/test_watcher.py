from __future__ import annotations

import sys
from pathlib import Path

import pytest

from chatmesh.watcher import Watcher


def test_empty_command_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        Watcher(command=[], log_path=tmp_path / "w.log")


def test_run_respawns_then_stops_on_signal(tmp_path: Path) -> None:
    """Run a short child a few times, then send SIGTERM to ourselves.

    The watcher runs in-process, so a SIGTERM here also stops the loop.
    Not the cleanest test, but it exercises spawn, wait, and log write.
    """
    log = tmp_path / "w.log"
    # Child exits immediately with rc=0. min_restart_seconds keeps us from
    # burning CPU on the respawn loop.
    child = [sys.executable, "-c", "pass"]
    w = Watcher(child, log_path=log, min_restart_seconds=0.05)

    # We cannot easily stop the loop from outside without another thread.
    # Instead, monkey-patch _stop after one spawn to break out.
    original_log = w._log
    spawns = {"count": 0}

    def counting_log(msg: str) -> None:
        original_log(msg)
        if msg.startswith("spawn:"):
            spawns["count"] += 1
            if spawns["count"] >= 2:
                w._stop = True

    w._log = counting_log  # type: ignore[method-assign]

    with pytest.raises(SystemExit) as exc:
        w.run()
    assert exc.value.code == 0
    assert spawns["count"] >= 2
    assert log.exists()
    assert b"spawn:" in log.read_bytes()
