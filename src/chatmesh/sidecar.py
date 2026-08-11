from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from pathlib import Path

from chatmesh.envelope import Envelope
from chatmesh.errors import EnvelopeError


class Sidecar:
    def __init__(self, path: Path, dedup_size: int = 500) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_order: deque[str] = deque(maxlen=dedup_size)
        self._seen_set: set[str] = set()
        # Warm the dedup set from the tail of the existing file so a restart
        # does not re-accept messages we already saw.
        if self.path.exists():
            for env in _tail_envelopes(self.path, dedup_size):
                self._remember(env.msg_id)

    def has_seen(self, msg_id: str) -> bool:
        return msg_id in self._seen_set

    def append(self, env: Envelope) -> bool:
        if env.msg_id in self._seen_set:
            return False
        with self.path.open("ab") as f:
            f.write(env.to_json())
            f.write(b"\n")
        self._remember(env.msg_id)
        return True

    def read_new(self, since_offset: int = 0) -> Iterator[Envelope]:
        if not self.path.exists():
            return
        with self.path.open("rb") as f:
            f.seek(since_offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield Envelope.from_json(line)
                except EnvelopeError:
                    continue

    def _remember(self, msg_id: str) -> None:
        if len(self._seen_order) == self._seen_order.maxlen:
            evicted = self._seen_order[0]
            self._seen_set.discard(evicted)
        self._seen_order.append(msg_id)
        self._seen_set.add(msg_id)


def _tail_envelopes(path: Path, n: int) -> list[Envelope]:
    with path.open("rb") as f:
        lines = f.readlines()
    out: list[Envelope] = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(Envelope.from_json(line))
        except EnvelopeError:
            continue
    return out
