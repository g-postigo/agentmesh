"""End-to-end: what the GUI shows for messages sent by its own agent.

The GUI subscribes to `agent.outbox.>`, so anything it publishes comes
straight back to it. It used to drop everything carrying its own name,
which killed the duplicate but also hid messages published from the CLI.

Requires a running NATS broker on nats://127.0.0.1:4222.
Start it with:  docker compose -f broker/docker-compose.yml up -d
"""

from __future__ import annotations

import socket
import time
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from chatmesh import Envelope  # noqa: E402
from chatmesh.config import Config  # noqa: E402
from chatmesh.gui import build_app  # noqa: E402
from chatmesh.publisher import Publisher  # noqa: E402

BROKER_HOST = "127.0.0.1"
BROKER_PORT = 4222


def _broker_up() -> bool:
    try:
        with socket.create_connection((BROKER_HOST, BROKER_PORT), timeout=0.3):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _broker_up(), reason="no NATS broker on 127.0.0.1:4222")


def _cfg(tmp_path: Path) -> Config:
    return Config(
        broker_url=f"nats://{BROKER_HOST}:{BROKER_PORT}",
        agent_name="user",
        sidecar_path=tmp_path / "user.jsonl",
        log_path=tmp_path / "user.log",
    )


def _history_for(client: TestClient, body: str, tries: int = 40) -> list[dict]:
    """Poll, because the copy off the bus lands a moment after the reply."""
    found: list[dict] = []
    for _ in range(tries):
        found = [e for e in client.get("/history").json() if e.get("body") == body]
        if found:
            time.sleep(0.15)  # give a duplicate a chance to show up too
            return [e for e in client.get("/history").json() if e.get("body") == body]
        time.sleep(0.1)
    return found


def test_a_message_sent_from_the_gui_appears_once(tmp_path: Path):
    with TestClient(build_app(_cfg(tmp_path))) as client:
        time.sleep(1.0)  # let the nats worker connect and subscribe
        r = client.post("/send", json={"to": "broadcast", "topic": "t", "body": "only once"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        entries = _history_for(client, "only once")

    assert len(entries) == 1, entries
    assert entries[0]["to"] == "broadcast"


def test_a_message_published_outside_the_gui_still_shows(tmp_path: Path):
    """Same agent name, but the GUI never saw it, so it has to render."""
    cfg = _cfg(tmp_path)
    with TestClient(build_app(cfg)) as client:
        time.sleep(1.0)

        async def _publish() -> None:
            pub = Publisher(cfg)
            await pub.connect()
            await pub.publish(Envelope.new("user", "broadcast", "t", "from the cli"))
            await pub.close()

        client.portal.call(_publish)  # type: ignore[attr-defined]
        entries = _history_for(client, "from the cli")

    assert len(entries) == 1, entries
    assert entries[0]["from"] == "user"
