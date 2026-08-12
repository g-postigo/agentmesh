from __future__ import annotations

import signal
import sys
import threading
import time
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


def test_stop_takes_the_child_down_with_it(tmp_path: Path) -> None:
    """A stop request must not wait for a long-running child to finish.

    Before this, the loop sat in proc.wait() and the child was never
    signalled, so `chatmesh watch` under a service manager never exited.
    """
    log = tmp_path / "w.log"
    child = [sys.executable, "-c", "import time; time.sleep(30)"]
    w = Watcher(child, log_path=log, min_restart_seconds=0.05)
    seen: list = []

    def stop_once_running() -> None:
        for _ in range(200):
            if w._proc is not None:
                seen.append(w._proc)
                break
            time.sleep(0.05)
        w._on_stop(signal.SIGTERM, None)

    stopper = threading.Thread(target=stop_once_running)
    stopper.start()
    started = time.monotonic()
    with pytest.raises(SystemExit) as exc:
        w.run()
    stopper.join()
    elapsed = time.monotonic() - started

    assert exc.value.code == 0
    assert elapsed < 20, "watcher waited for the child instead of stopping it"
    assert seen, "child never started"
    assert seen[0].poll() is not None, "child survived the watcher"
