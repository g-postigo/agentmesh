from __future__ import annotations

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
    ) -> None:
        if not command:
            raise ValueError("command must not be empty")
        self.command = command
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.min_restart_seconds = min_restart_seconds
        self._stop = False

    def run(self) -> NoReturn:
        signal.signal(signal.SIGTERM, self._on_stop)
        signal.signal(signal.SIGINT, self._on_stop)

        while not self._stop:
            started = time.monotonic()
            self._log(f"spawn: {' '.join(self.command)}")
            with self.log_path.open("ab") as log:
                proc = subprocess.Popen(self.command, stdout=log, stderr=log)
                rc = proc.wait()
            self._log(f"exit rc={rc}")

            if self._stop:
                break

            elapsed = time.monotonic() - started
            if elapsed < self.min_restart_seconds:
                sleep = self.min_restart_seconds - elapsed
                self._log(f"restart in {sleep:.1f}s (child died fast)")
                time.sleep(sleep)

        sys.exit(0)

    def _on_stop(self, signum: int, _frame: object) -> None:
        self._log(f"got signal {signum}, stopping")
        self._stop = True

    def _log(self, msg: str) -> None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.log_path.open("ab") as f:
            f.write(f"[watcher {ts}] {msg}\n".encode())
