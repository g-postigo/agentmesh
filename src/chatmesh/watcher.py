from __future__ import annotations

import contextlib
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import NoReturn


class Watcher:
    def __init__(
        self,
        command: list[str],
        log_path: Path,
        min_restart_seconds: float = 2.0,
        stop_grace_seconds: float = 5.0,
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.command = command
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.min_restart_seconds = min_restart_seconds
        self.stop_grace_seconds = stop_grace_seconds
        self._stop = False
        self._proc: subprocess.Popen[bytes] | None = None

    def run(self) -> NoReturn:
        signal.signal(signal.SIGTERM, self._on_stop)
        signal.signal(signal.SIGINT, self._on_stop)

        while not self._stop:
            started = time.monotonic()
            self._log(f"spawn: {' '.join(self.command)}")
            with self.log_path.open("ab") as log:
                proc = subprocess.Popen(self.command, stdout=log, stderr=log)
                self._proc = proc
                try:
                    rc = self._wait(proc)
                finally:
                    self._proc = None
            self._log(f"exit rc={rc}")

            if self._stop:
                break

            elapsed = time.monotonic() - started
            if elapsed < self.min_restart_seconds:
                sleep = self.min_restart_seconds - elapsed
                self._log(f"restart in {sleep:.1f}s (child died fast)")
                time.sleep(sleep)

        sys.exit(0)

    def _wait(self, proc: subprocess.Popen[bytes]) -> int:
        """Wait for the child, taking it down with us if we were asked to stop.

        Polls instead of blocking on wait() so that a stop request is noticed
        even when the signal arrived while we were not looking, and so a child
        that ignores terminate still gets killed.
        """
        grace_until: float | None = None
        killed = False
        while True:
            try:
                return proc.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass
            if not self._stop:
                continue
            if grace_until is None:
                # Normally the signal handler already asked it to go. If the
                # signal landed before we stored the handle, this catches it.
                _terminate(proc)
                grace_until = time.monotonic() + self.stop_grace_seconds
            elif not killed and time.monotonic() >= grace_until:
                self._log("child ignored terminate, killing")
                with contextlib.suppress(OSError):
                    proc.kill()
                killed = True

    def _on_stop(self, signum: int, _frame: object) -> None:
        self._log(f"got signal {signum}, stopping")
        self._stop = True
        proc = self._proc
        if proc is not None:
            _terminate(proc)

    def _log(self, msg: str) -> None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.log_path.open("ab") as f:
            f.write(f"[watcher {ts}] {msg}\n".encode())


def _terminate(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is None:
        with contextlib.suppress(OSError):
            proc.terminate()
